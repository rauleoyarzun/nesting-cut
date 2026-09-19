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


def test_cerrar_no_revienta_si_entran_trabajos_al_mismo_tiempo(registro):
    """Reproduce el `RuntimeError: dictionary changed size during
    iteration` de `cerrar()` recorriendo `self._trabajos` mientras otro
    hilo llama a `crear()`. Es justo el escenario que el módulo espera:
    `cerrar()` se llama al apagar mientras pueden estar entrando pedidos."""
    arrancar = threading.Event()
    parar = threading.Event()
    errores = []

    def creador():
        arrancar.wait(timeout=5)
        while not parar.is_set():
            try:
                registro.crear(FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c))
            except RegistroCerradoError:
                return
            except Exception as error:  # noqa: BLE001 - lo que se busca detectar
                errores.append(error)
                return

    hilos = [threading.Thread(target=creador) for _ in range(8)]
    for h in hilos:
        h.start()
    arrancar.set()

    registro.cerrar()

    parar.set()
    for h in hilos:
        h.join(timeout=5)

    assert errores == []


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
