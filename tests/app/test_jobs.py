"""El ciclo de vida de un trabajo, sin correr el motor."""

import threading
import time

import pytest

from nesting.engine.packer import Avance, Cancelado
from nesting_app.archivos import Fuente
from nesting_app.jobs import (
    Estado,
    Registro,
    RegistroCerradoError,
    Resultado,
    Trabajo,
    TrabajoDesconocidoError,
)
from nesting.params import NestParams

PARAMS = NestParams(material="mdf18")
FUENTE = Fuente(id="f1", ruta=None, nombre="robot.ai")


def resultado_falso(carpeta):
    return Resultado(placas=1, aprovechamiento=[0.477], total=0.477,
                     segundos=1.0, sobrante_mm=708.0, carpeta=carpeta)


def esperar(trabajo, estados, limite=5.0):
    """Espera a que el trabajo llegue a uno de `estados`."""
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if trabajo.estado in estados:
            return trabajo.estado
        time.sleep(0.005)
    raise AssertionError(f"el trabajo quedó en {trabajo.estado}, esperaba {estados}")


@pytest.fixture
def registro(tmp_path):
    r = Registro(tmp_path / "trabajos")
    yield r
    r.cerrar()


def test_un_trabajo_que_termina_queda_listo(registro):
    def corredor(fuente, params, progreso, carpeta):
        return resultado_falso(carpeta)

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    esperar(trabajo, {Estado.LISTO})

    assert trabajo.resultado.placas == 1
    assert trabajo.error is None


def test_el_avance_queda_disponible_mientras_corre(registro):
    avanzó = threading.Event()
    suelto = threading.Event()

    def corredor(fuente, params, progreso, carpeta):
        progreso(Avance(intento=1, intentos=3, ubicadas=61, totales=93, placa=1))
        avanzó.set()
        suelto.wait(timeout=5)
        return resultado_falso(carpeta)

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    # Un `time.sleep` fijo acá sería apostar a que la máquina alcanzó a
    # correr el hilo del trabajo en ese lapso; con la máquina cargada, no
    # siempre pasa. El `Event` espera exactamente el hecho que importa: que
    # el corredor ya haya publicado su avance.
    assert avanzó.wait(timeout=5), "el corredor nunca llegó a avisar del avance"

    assert trabajo.avance.ubicadas == 61
    assert trabajo.avance.intentos == 3
    suelto.set()
    esperar(trabajo, {Estado.LISTO})


def test_cancelar_hace_que_el_progreso_devuelva_False(registro):
    """Así es como el motor se entera: el callback le dice que pare."""
    visto = []
    arrancó = threading.Event()

    def corredor(fuente, params, progreso, carpeta):
        arrancó.set()
        for _ in range(200):
            if not progreso(Avance(1, 1, 0, 10, 1)):
                raise Cancelado("cancelado")
            visto.append(1)
            time.sleep(0.005)
        return resultado_falso(carpeta)

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    arrancó.wait(timeout=5)
    registro.cancelar(trabajo.id)
    esperar(trabajo, {Estado.CANCELADO})

    assert trabajo.resultado is None
    # Si `cancelar` no cortara nada, el bucle llegaría a las 200 vueltas
    # (con 0.005s cada una, un segundo) y el trabajo terminaría LISTO en vez
    # de CANCELADO: el `esperar` de arriba ya habría reventado por timeout.
    # Esta aserción es el segundo cinturón: incluso si algún día `esperar`
    # se vuelve más laxo, acá queda registrado que el corte fue temprano y
    # no una casualidad de haber llegado justo al final.
    assert len(visto) < 200, "tenía que cortar antes de terminar"


def test_cancelar_uno_que_ya_terminó_no_revienta(registro):
    """El usuario puede apretar cancelar justo cuando terminaba. Eso es una
    carrera normal, no un error que deba explotar en la cara de nadie."""
    trabajo = registro.crear(FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c))
    esperar(trabajo, {Estado.LISTO})

    registro.cancelar(trabajo.id)

    assert trabajo.estado is Estado.LISTO


def test_un_error_del_usuario_queda_con_su_mensaje(registro):
    def corredor(fuente, params, progreso, carpeta):
        raise ValueError("el contorno no cierra por 0.8 mm")

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    esperar(trabajo, {Estado.ERROR})

    assert "0.8 mm" in trabajo.error
    assert trabajo.es_bug is False


def test_un_bug_del_programa_se_marca_como_tal(registro):
    """Un error inesperado no puede disfrazarse de 'revisá tu dibujo'.

    La interfaz muestra los dos distinto: uno manda al usuario a corregir
    algo, el otro le dice que el problema es del programa.
    """
    def corredor(fuente, params, progreso, carpeta):
        raise RuntimeError("índice fuera de rango")

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    esperar(trabajo, {Estado.ERROR})

    assert trabajo.es_bug is True
    assert "índice fuera de rango" in trabajo.error


def test_los_trabajos_corren_de_a_uno(registro):
    """En escritorio la interfaz ya deshabilita el botón, pero la API no
    puede confiar en eso: en la web sí va a llegar más de uno a la vez."""
    corriendo = []
    maximo = []
    traba = threading.Lock()

    def corredor(fuente, params, progreso, carpeta):
        with traba:
            corriendo.append(1)
            maximo.append(len(corriendo))
        time.sleep(0.05)
        with traba:
            corriendo.pop()
        return resultado_falso(carpeta)

    trabajos = [registro.crear(FUENTE, PARAMS, corredor) for _ in range(4)]
    for t in trabajos:
        esperar(t, {Estado.LISTO})

    assert max(maximo) == 1


def test_cada_trabajo_tiene_su_carpeta(registro):
    carpetas = []

    def corredor(fuente, params, progreso, carpeta):
        carpetas.append(carpeta)
        assert carpeta.is_dir()
        return resultado_falso(carpeta)

    a = registro.crear(FUENTE, PARAMS, corredor)
    b = registro.crear(FUENTE, PARAMS, corredor)
    esperar(a, {Estado.LISTO})
    esperar(b, {Estado.LISTO})

    assert carpetas[0] != carpetas[1]


def test_un_id_que_no_existe_se_queja(registro):
    with pytest.raises(TrabajoDesconocidoError):
        registro.obtener("no-existe")


def test_cerrar_borra_las_carpetas(registro, tmp_path):
    trabajo = registro.crear(FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c))
    esperar(trabajo, {Estado.LISTO})

    registro.cerrar()

    assert not (tmp_path / "trabajos").exists()


def test_cerrar_dos_veces_no_revienta(registro):
    """`cerrar()` se va a llamar al salir del programa, y puede llegar
    después de que algo ya haya fallado y también haya intentado cerrar."""
    trabajo = registro.crear(FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c))
    esperar(trabajo, {Estado.LISTO})

    registro.cerrar()
    registro.cerrar()  # no debe reventar ni colgarse


def test_cerrar_no_deja_el_hilo_vivo(registro):
    trabajo = registro.crear(FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c))
    esperar(trabajo, {Estado.LISTO})

    registro.cerrar()

    assert not registro._hilo.is_alive()


class _DiccionarioConIntruso(dict):
    """Un `dict` cuyo `values()` fuerza, de forma determinística, la
    interleaving que rompe a `cerrar()` cuando recorre `self._trabajos`
    sin protegerse de una inserción concurrente.

    Después de entregar el primer elemento, lanza un hilo que intenta
    colarse insertando una clave nueva directamente en el diccionario --
    bajo el mismo `_trabajos_lock` que usa `crear()` para su propia alta,
    pero sin pasar por el chequeo de `_cerrando` -- y espera (con límite)
    a que ese intento termine antes de seguir iterando. No se usa el
    `crear()` público a propósito: `cerrar()` ya marcó `_cerrando` antes
    de empezar a iterar, así que cualquier llamada real a `crear()` acá
    se rechazaría de entrada y nunca llegaría a tocar el diccionario, sin
    que eso diga nada sobre si la iteración está protegida. Lo que se
    modela es el hilo que ya pasó ese chequeo y solo le falta escribir --
    la misma ventana que motiva el punto 1 -- representado en su forma
    más directa: tomar el lock y escribir.

    - Si `cerrar()` recorre el diccionario en vivo (sin lock ni copia),
      el intruso toma el lock (nada se lo impide) y entra en
      microsegundos. La espera lo confirma casi al instante, y el
      `next()` siguiente encuentra el diccionario ya mutado --
      `RuntimeError: dictionary changed size during iteration`, siempre,
      sin depender del scheduler.
    - Si `cerrar()` sostiene `self._trabajos_lock` mientras copia (el
      arreglo de este commit), el intruso queda bloqueado en su propio
      `with lock:` y no puede terminar hasta que `cerrar()` suelte la
      copia. La espera agota su plazo sin que nada haya cambiado, la
      iteración sigue en paz, y recién después el intruso se destraba e
      inserta sin problema (ya terminó la iteración).

    Ninguna de las dos ramas depende de ganar una carrera contra el
    intérprete: la que gana depende únicamente de si el lock protege la
    copia, que es justo lo que este test quiere demostrar.
    """

    def __init__(self, *args, lock, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = lock
        self.intruso_insertado = threading.Event()
        self.intruso_terminado = threading.Event()

    def values(self):
        it = iter(dict.values(self))
        try:
            primero = next(it)
        except StopIteration:
            return
        yield primero

        def intruso():
            with self._lock:
                self["intruso"] = Trabajo(id="intruso")
            self.intruso_insertado.set()
            self.intruso_terminado.set()

        threading.Thread(target=intruso, daemon=True).start()
        # Si el lock protege la copia, esto agota el plazo sin que
        # `intruso_terminado` se dispare -- eso es lo esperado, no una
        # falla. Si no la protege, el intruso ya insertó antes de que
        # termine la espera.
        self.intruso_terminado.wait(timeout=2.0)

        yield from it


def test_cerrar_no_revienta_si_entran_trabajos_al_mismo_tiempo(registro):
    """Protege contra regresión del bug donde `cerrar()` recodía
    `self._trabajos` en vivo, sin lock ni copia, y reventaba con
    `RuntimeError: dictionary changed size during iteration` si otro
    hilo insertaba ahí mismo.

    El bug ya está reparado (la copia está protegida por el lock que
    también protege el alta en `crear()`), así que hoy no hay forma de
    que un escenario real llegue a la situación de modificación concurrente:
    `crear()` hiere el diccionario bajo el mismo lock que `cerrar()` usa para
    copiarlo, así que son mutuamente excluidos.

    Este test se instrumenta para forzar esa interleaving de todas formas,
    como guardia estructural: si alguien saca el lock de adentro del `with`
    en `cerrar()`, esto lo detecta. Usa un diccionario personalizado
    (`_DiccionarioConIntruso`) que inyecta una modificación concurrente
    durante su propia iteración, de forma determinística (ver
    `_DiccionarioConIntruso` para el detalle)."""
    trabajo = registro.crear(FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c))
    esperar(trabajo, {Estado.LISTO})

    intruso = _DiccionarioConIntruso(registro._trabajos, lock=registro._trabajos_lock)
    registro._trabajos = intruso

    registro.cerrar()  # no debe reventar

    # El intruso pudo haber quedado bloqueado hasta recién ahora si el
    # lock protegía la copia; se le da margen para que termine de una vez
    # que `cerrar()` ya soltó todo.
    assert intruso.intruso_terminado.wait(timeout=5), "el intruso nunca terminó"
    assert intruso.intruso_insertado.is_set()


def test_ventana_entre_alta_y_encolado_no_deja_trabajo_huerfano(registro):
    """El bug que este commit corrige: `crear()` cargaba el trabajo en
    `self._trabajos` y encolaba (`self._cola.put`) como dos pasos
    separados, el segundo afuera del lock. Si un hilo pasaba el chequeo y
    el alta, y era desalojado justo antes de su `put`, y en ese instante
    `cerrar()` corría entero -- marcaba `_cerrando`, copiaba la lista (que
    ya incluía ese trabajo), encolaba su propio `None`, y el trabajador lo
    sacaba y terminaba --, el `put` del primer hilo llegaba después a una
    cola sin consumidor: el trabajo quedaba en el diccionario, en
    PENDIENTE, para siempre.

    Fuerza esa ventana demorando el `put` real de la cola con un `Event`,
    pero solo para el `put` de `crear()` (detecta si el item es `None`
    para no retrasar el cierre). Dispara `cerrar()` desde otro hilo
    mientras `crear()` sigue adentro de su sección crítica. Con el alta y
    el `put` bajo el mismo lock, `cerrar()` no puede avanzar hasta que
    `crear()` termine -- eso se verifica explícitamente --, así que el
    trabajo entra a la cola antes de que exista el `None` de cierre y
    nunca queda huérfano.

    NO es determinístico: medido contra el código con el bug adentro,
    detecta 23 de 30 corridas. Lo que queda librado al planificador es el
    orden en que arrancan los dos hilos. Se deja así en vez de prometer
    determinismo que no tiene, porque 23 de 30 en cada corrida de la suite
    es protección real, y porque el escenario se verificó además a mano.
    """
    cola = registro._cola
    put_original = cola.put
    alcanzó_el_put = threading.Event()
    seguir = threading.Event()

    def put_demorado(item, *args, **kwargs):
        # No retrasar el None de cerrar(), solo la tupla de crear().
        if item is None:
            return put_original(item, *args, **kwargs)
        alcanzó_el_put.set()
        seguir.wait(timeout=5)
        return put_original(item, *args, **kwargs)

    cola.put = put_demorado

    resultado: dict = {}

    def crear_en_otro_hilo():
        try:
            resultado["trabajo"] = registro.crear(
                FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c)
            )
        except RegistroCerradoError as error:
            resultado["error"] = error

    hilo_creador = threading.Thread(target=crear_en_otro_hilo)
    hilo_creador.start()
    assert alcanzó_el_put.wait(timeout=5), "crear() nunca llegó al put"

    hilo_cerrando = threading.Thread(target=registro.cerrar)
    hilo_cerrando.start()

    # `crear()` sigue bloqueado en el `put` demorado, y por lo tanto sigue
    # sosteniendo `self._trabajos_lock`: `cerrar()` no tiene forma de
    # avanzar todavía. Esto no es una apuesta de timing -- mientras
    # `seguir` no se dispare, `crear()` no puede haber soltado el lock.
    hilo_cerrando.join(timeout=0.2)
    assert hilo_cerrando.is_alive(), (
        "cerrar() debería estar esperando el lock mientras crear() sigue "
        "bloqueado en su propio put demorado"
    )

    seguir.set()
    hilo_creador.join(timeout=5)
    hilo_cerrando.join(timeout=5)
    assert not hilo_cerrando.is_alive()

    assert "error" not in resultado, (
        f"crear() no debía rechazarse acá, y se rechazó con {resultado.get('error')!r}"
    )
    trabajo = resultado["trabajo"]
    estado_final = esperar(
        trabajo, {Estado.LISTO, Estado.CANCELADO, Estado.ERROR}
    )
    assert estado_final is not Estado.PENDIENTE, (
        "el trabajo quedó huérfano: nunca salió de PENDIENTE ni se rechazó"
    )


def test_crear_despues_de_cerrar_levanta_registro_cerrado(registro):
    registro.cerrar()

    with pytest.raises(RegistroCerradoError):
        registro.crear(FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c))


def test_key_error_interno_se_marca_como_bug(registro):
    """Un `KeyError` de un diccionario interno del programa es un bug de
    verdad, no algo que el usuario pueda arreglar en su dibujo."""
    def corredor(fuente, params, progreso, carpeta):
        raise KeyError("clave_interna")

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    esperar(trabajo, {Estado.ERROR})

    assert trabajo.es_bug is True


def test_value_error_se_marca_como_error_del_usuario(registro):
    def corredor(fuente, params, progreso, carpeta):
        raise ValueError("el contorno no cierra")

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    esperar(trabajo, {Estado.ERROR})

    assert trabajo.es_bug is False
