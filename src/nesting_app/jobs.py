"""Administrar trabajos. No hacerlos: eso es `corredor.py`.

La separación es deliberada. Con el motor adentro, cada test del ciclo de
vida -- crear, cancelar a mitad, dos a la vez, que el error quede bien
clasificado -- tardaría medio minuto. Con un corredor de mentira tardan
milisegundos, y el corredor de verdad se prueba aparte.

En escritorio corre un hilo. En la web se cambia por una cola de procesos
sin tocar nada de lo que está afuera de este archivo.
"""

import queue
import shutil
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from nesting.engine.packer import Avance, Cancelado
from nesting.engine.packer import PartTooLargeError, UnknownEffortError
from nesting.geometry.nesting_tree import OverlappingContourError
from nesting.io.dxf_reader import UnknownUnitsError
from nesting.io.rhino_reader import NonPlanarCurveError
from nesting.params import NestParams, ParamsInvalidosError
from nesting.pipeline import OpenContourError
from nesting_app.archivos import Fuente
from nesting_app.materials_store import MaterialDesconocidoError


class Estado(StrEnum):
    PENDIENTE = "pendiente"
    CORRIENDO = "corriendo"
    LISTO = "listo"
    CANCELADO = "cancelado"
    ERROR = "error"


@dataclass(frozen=True)
class Resultado:
    """Lo que se puede contar de un acomodo terminado."""

    placas: int
    aprovechamiento: list[float]
    total: float
    segundos: float
    sobrante_mm: float
    material_ultima_placa_m2: float
    """Cuánta pieza quedó en la última placa, en m².

    Va al lado de `sobrante_mm` porque las dos cifras compiten: el motor
    elige el layout que baja ésta, y eso a veces acorta la tira libre. Ver
    las dos juntas es lo que deja decidir si conviene para este trabajo.
    """
    carpeta: Path
    avisos: list[str] = field(default_factory=list)
    recortes_usados: int = 0
    """Cuántas de las placas del acomodo eran recortes.

    Va acá y no se recalcula en la pantalla porque el motor ya lo sabe:
    `PackResult.sheets` dice qué fue cada placa. Contarlo dos veces sería
    tener dos fuentes de verdad para el mismo número.

    Va último por la regla de los dataclass -- los campos con valor por
    omisión van después de los que no lo tienen -- y no porque importe
    menos que `placas`.
    """
    es_minimo: bool = False
    """El acomodo iguala la cota por área: con menos placas no entra.

    Lo calcula el corredor con `cartera.cota_minima`, que no informa nada con
    recortes. En falso no dice "se puede con menos": dice que no se sabe.
    """


ESPERA_MINIMA_S = 5.0
"""Segundos de medición antes de dar un número. Antes no hay datos."""

CONSULTAS_MINIMAS = 20
"""Consultas medidas antes de dar un número. Con la veta respetada una
pieza son 4 consultas: 20 son cinco piezas, lo mínimo para que una pieza
rara no decida sola."""

PESO_DE_LA_MUESTRA = 0.2
"""Cuánto pesa la muestra nueva en el promedio móvil de segundos por
consulta. Bajo a propósito: una consulta lenta aislada -- una pieza grande
contra una placa casi llena -- no tiene que mover el número mostrado."""


class EstimadorDeRestante:
    """Cuántos segundos le faltan a un trabajo, a partir de sus consultas.

        segundos_por_consulta = transcurrido / consultas_hechas
        restante = segundos_por_consulta * (consultas_previstas - consultas_hechas)

    con un promedio móvil exponencial sobre `segundos_por_consulta`.

    `transcurrido` y `consultas_hechas` se miden desde el PRIMER aviso y no
    desde que arrancó el trabajo: lo que pasa antes -- leer el archivo,
    preparar las piezas -- no son consultas, y medirlo cargaría ese tiempo a
    cada una. El reloj se inyecta para poder probarlo sin esperar.
    """

    def __init__(self, reloj: Callable[[], float] = time.monotonic) -> None:
        self._reloj = reloj
        self._referencia: tuple[float, int] | None = None
        self._por_consulta: float | None = None

    def actualizar(self, hechas: int, previstas: int) -> float | None:
        """Segundos que faltan, o `None` mientras no hay datos para decirlo."""
        ahora = self._reloj()
        if self._referencia is None:
            self._referencia = (ahora, hechas)
            return None
        desde, hechas_al_empezar = self._referencia
        transcurrido = ahora - desde
        medidas = hechas - hechas_al_empezar
        if transcurrido < ESPERA_MINIMA_S or medidas < CONSULTAS_MINIMAS:
            return None
        muestra = transcurrido / medidas
        if self._por_consulta is None:
            self._por_consulta = muestra
        else:
            self._por_consulta = (
                PESO_DE_LA_MUESTRA * muestra
                + (1 - PESO_DE_LA_MUESTRA) * self._por_consulta
            )
        return self._por_consulta * max(0, previstas - hechas)


@dataclass
class Trabajo:
    id: str
    estado: Estado = Estado.PENDIENTE
    avance: Avance | None = None
    avisos: list[str] = field(default_factory=list)
    error: str | None = None
    es_bug: bool = False
    """Si el error es del programa y no del dibujo del usuario.

    La interfaz los muestra distinto: uno manda a corregir el archivo, el
    otro dice que el problema es nuestro y ofrece copiar el detalle. Mezclar
    los dos hace que la gente busque durante media hora un defecto que no
    está en su dibujo.
    """
    resultado: Resultado | None = None
    detalle_tecnico: str | None = None
    restante_s: float | None = None
    """Segundos que faltan según `EstimadorDeRestante`, o `None` mientras
    no hay datos (los primeros 5 s o las primeras 20 consultas)."""
    _cancelar: threading.Event = field(default_factory=threading.Event, repr=False)


class TrabajoDesconocidoError(KeyError):
    def __str__(self) -> str:
        return self.args[0] if self.args else ""


class RegistroCerradoError(Exception):
    """Se pidió crear un trabajo después de que el registro ya cerró.

    Aceptarlo igual lo dejaría encolado sin nadie que lo consuma: el
    `Trabajo` quedaría en PENDIENTE para siempre, sin pasar a ERROR ni a
    CANCELADO, y una interfaz que sondee el estado esperaría sin ningún
    indicio. Mejor rechazarlo en el momento.
    """


Corredor = Callable[[Fuente, NestParams, Callable[[Avance], bool], Path], Resultado]

ERRORES_DEL_USUARIO = (
    ParamsInvalidosError,
    UnknownUnitsError,
    OpenContourError,
    OverlappingContourError,
    PartTooLargeError,
    UnknownEffortError,
    NonPlanarCurveError,
    MaterialDesconocidoError,
    OSError,
    ValueError,
)
"""Lo que significa 'tu archivo o tus parámetros tienen un problema'.

Es una lista explícita, no una regla general, porque una regla general se
equivoca fácil para el lado peligroso: culpar al usuario de un bug nuestro.

- `ParamsInvalidosError`, `UnknownUnitsError`, `OpenContourError`,
  `OverlappingContourError`, `PartTooLargeError`, `UnknownEffortError` y
  `NonPlanarCurveError` son las excepciones puntuales que el motor define
  para "tu archivo o tus parámetros tienen un problema": unidades no
  declaradas, un contorno que no cierra, piezas que se pisan, una pieza que
  no entra en la placa, un nivel de esfuerzo que no existe, una curva que no
  apoya en el plano XY.
- `OSError` es el entorno del usuario (no se pudo leer o escribir un
  archivo), no un defecto del programa.
- `ValueError` a secas queda porque los lectores y el pipeline lo usan en
  varios puntos para "tu archivo tiene un problema" sin una subclase
  dedicada.

Deliberadamente NO está `KeyError` a secas: es ambiguo. Un `KeyError` de un
diccionario interno del programa es un bug de verdad, y con la regla vieja
cualquiera de esos cae disfrazado de "revisá tu dibujo" -- exactamente lo
que `Trabajo.es_bug` existe para evitar.

`MaterialDesconocidoError` (`nesting_app.materials_store`) es la única
excepción de esta lista que sí hereda de `KeyError`, y está a propósito:
no es un diccionario interno reventando por un bug, es el material que el
usuario eligió desapareciendo del catálogo -- por ejemplo porque alguien lo
borró desde la pantalla de materiales mientras el trabajo esperaba en la
cola. Es exactamente la clase de caso "tu archivo o tus parámetros tienen
un problema" que esta lista existe para cubrir, y por eso se agrega por su
nombre en vez de relajar la exclusión general de `KeyError`.

`ChainingInvariantError` hereda de `RuntimeError`, no de nada de esta
lista, así que cae del lado del bug sin necesidad de excluirlo a mano. Y
ninguna de las excepciones marcadas como bug (`ChainingInvariantError`,
`UnknownPartError`, `InvalidEntityIdError`) hereda de nada de esta tupla:
se comprobó con `issubclass` contra cada una, no de memoria.
"""


class Registro:
    """Los trabajos de esta corrida del programa, y el hilo que los ejecuta."""

    def __init__(
        self, carpeta: Path, reloj: Callable[[], float] = time.monotonic
    ) -> None:
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._reloj = reloj
        self._trabajos: dict[str, Trabajo] = {}
        self._trabajos_lock = threading.Lock()
        self._cola: queue.Queue = queue.Queue()
        self._cerrando = threading.Event()
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()

    def crear(self, fuente: Fuente, params: NestParams, corredor: Corredor) -> Trabajo:
        trabajo = Trabajo(id=uuid.uuid4().hex)
        with self._trabajos_lock:
            # El chequeo, el alta y el `put` van bajo el mismo lock que usa
            # `cerrar()` para marcar el cierre, sacar su copia y encolar su
            # propio `None`. Si el `put` quedara afuera, un hilo podía pasar
            # el chequeo, cargar el trabajo en `self._trabajos`, y ser
            # desalojado antes de encolarlo; si en ese instante `cerrar()`
            # corría entero, encolaba su `None` primero, el trabajador lo
            # sacaba y terminaba, y el `put` de `crear()` llegaba después a
            # una cola sin consumidor: el trabajo quedaba en PENDIENTE para
            # siempre. Con todo bajo el mismo lock, un trabajo o bien queda
            # adentro a tiempo para que `cerrar()` lo cancele -- y su `put`
            # llega antes que el `None` de cierre, porque comparten lock --,
            # o bien `crear()` ya ve el cierre y lo rechaza. Nunca las dos
            # cosas a la vez ni ninguna.
            if self._cerrando.is_set():
                raise RegistroCerradoError(
                    "no se puede crear un trabajo: el registro ya cerró"
                )
            self._trabajos[trabajo.id] = trabajo
            self._cola.put((trabajo, fuente, params, corredor))
        return trabajo

    def obtener(self, trabajo_id: str) -> Trabajo:
        try:
            return self._trabajos[trabajo_id]
        except KeyError:
            raise TrabajoDesconocidoError(
                f"no hay ningún trabajo con el id {trabajo_id!r}"
            ) from None

    def cancelar(self, trabajo_id: str) -> None:
        """Pide abandonar. Que ya haya terminado no es un error.

        El usuario puede apretar cancelar justo cuando terminaba: esa
        carrera es normal y no tiene que explotarle en la cara.
        """
        self.obtener(trabajo_id)._cancelar.set()

    def cerrar(self) -> None:
        with self._trabajos_lock:
            if self._cerrando.is_set():
                return
            self._cerrando.set()
            # Copia adentro del lock. `crear()` puede seguir escribiendo en
            # `self._trabajos` desde otro hilo hasta el instante en que ve
            # `_cerrando` marcado, así que iterar el dict en vivo puede
            # reventar con "dictionary changed size during iteration".
            trabajos = list(self._trabajos.values())
            # Los `_cancelar.set()` van antes del `put(None)`, y los dos
            # bajo el mismo lock que protege el alta en `crear()`. Antes:
            # si un trabajo ya estaba en la cola pero el trabajador no lo
            # había sacado, marcarlo cancelado y recién después encolar el
            # `None` aseguraba que, al sacarlo, `_trabajar` ya lo viera
            # cancelado y no lo corriera. Ahora, además, el `put(None)`
            # bajo el mismo lock que el `put` de `crear()` garantiza que
            # llega a la cola después de cualquier trabajo que ya alcanzó
            # a entrar a `self._trabajos` (y por lo tanto a `trabajos`,
            # arriba): el trabajador nunca saca el `None` antes de que ese
            # trabajo esté también en la cola. `Queue.put` en una cola sin
            # límite nunca bloquea, así que esto no agrega espera bajo el
            # lock.
            for trabajo in trabajos:
                trabajo._cancelar.set()
            self._cola.put(None)
        self._hilo.join(timeout=5)
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def _trabajar(self) -> None:
        while True:
            pedido = self._cola.get()
            if pedido is None:
                return
            trabajo, fuente, params, corredor = pedido
            if trabajo._cancelar.is_set():
                trabajo.estado = Estado.CANCELADO
                continue
            self._correr(trabajo, fuente, params, corredor)

    def _correr(self, trabajo, fuente, params, corredor) -> None:
        trabajo.estado = Estado.CORRIENDO
        propia = self.carpeta / trabajo.id
        propia.mkdir(parents=True, exist_ok=True)

        estimador = EstimadorDeRestante(self._reloj)

        def progreso(avance: Avance) -> bool:
            trabajo.avance = avance
            trabajo.restante_s = estimador.actualizar(
                avance.consultas_hechas, avance.consultas_previstas
            )
            return not trabajo._cancelar.is_set()

        try:
            trabajo.resultado = corredor(fuente, params, progreso, propia)
            trabajo.avisos = list(trabajo.resultado.avisos)
        except Cancelado:
            trabajo.estado = Estado.CANCELADO
        except ERRORES_DEL_USUARIO as error:
            trabajo.error = str(error)
            trabajo.es_bug = False
            # Si el corredor llegó a generar avisos antes de fallar -- por
            # ejemplo, por qué no quedó ninguna pieza -- viajan colgados de
            # la excepción (ver `corredor._con_avisos`) y no hay que
            # perderlos: son la explicación de por qué no quedó nada.
            trabajo.avisos = list(getattr(error, "avisos", ()))
            trabajo.estado = Estado.ERROR
        except Exception as error:  # noqa: BLE001 - se clasifica y se reporta
            trabajo.error = str(error) or type(error).__name__
            trabajo.detalle_tecnico = traceback.format_exc()
            trabajo.es_bug = True
            trabajo.avisos = list(getattr(error, "avisos", ()))
            trabajo.estado = Estado.ERROR
        else:
            trabajo.estado = Estado.LISTO
