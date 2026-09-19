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
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from nesting.engine.packer import Avance, Cancelado
from nesting.params import NestParams
from nesting_app.archivos import Fuente


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
    carpeta: Path


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
    _cancelar: threading.Event = field(default_factory=threading.Event, repr=False)


class TrabajoDesconocidoError(KeyError):
    def __str__(self) -> str:
        return self.args[0] if self.args else ""


Corredor = Callable[[Fuente, NestParams, Callable[[Avance], bool], Path], Resultado]

ERRORES_DEL_USUARIO = (ValueError, OSError, KeyError)
"""Lo que significa 'tu archivo o tus parámetros tienen un problema'.

Los lectores, el pipeline y el empacador levantan estos para lo que el
usuario puede arreglar. Cualquier otra cosa es un bug nuestro.
"""


class Registro:
    """Los trabajos de esta corrida del programa, y el hilo que los ejecuta."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._trabajos: dict[str, Trabajo] = {}
        self._cola: queue.Queue = queue.Queue()
        self._cerrando = threading.Event()
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()

    def crear(self, fuente: Fuente, params: NestParams, corredor: Corredor) -> Trabajo:
        trabajo = Trabajo(id=uuid.uuid4().hex)
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
        if self._cerrando.is_set():
            return
        self._cerrando.set()
        for trabajo in self._trabajos.values():
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

        def progreso(avance: Avance) -> bool:
            trabajo.avance = avance
            return not trabajo._cancelar.is_set()

        try:
            trabajo.resultado = corredor(fuente, params, progreso, propia)
        except Cancelado:
            trabajo.estado = Estado.CANCELADO
        except ERRORES_DEL_USUARIO as error:
            trabajo.error = str(error)
            trabajo.es_bug = False
            trabajo.estado = Estado.ERROR
        except Exception as error:  # noqa: BLE001 - se clasifica y se reporta
            trabajo.error = str(error) or type(error).__name__
            trabajo.detalle_tecnico = traceback.format_exc()
            trabajo.es_bug = True
            trabajo.estado = Estado.ERROR
        else:
            trabajo.estado = Estado.LISTO
