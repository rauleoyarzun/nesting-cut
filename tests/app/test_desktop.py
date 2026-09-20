"""El armado del servidor local, el puente de archivos y el autotest."""

from pathlib import Path
import sys
import threading
import urllib.request

import pytest

from nesting_app import desktop, rutas
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    registro = Registro(tmp_path / "trabajos")
    token, puerto, url = desktop.servidor(Deposito(tmp_path / "fuentes"), registro)
    yield token, puerto, url
    registro.cerrar()
    desktop.apagar()


def test_escucha_solo_en_localhost(servidor):
    """Escuchar en 0.0.0.0 expondría el programa a toda la red local: la
    máquina de al lado podría mandarle trabajos y leer rutas de archivos."""
    _, _, url = servidor
    assert url.startswith("http://127.0.0.1:")


def test_el_puerto_lo_elige_el_sistema(servidor):
    """Un puerto fijo choca el día que el usuario tenga otra cosa escuchando
    ahí, y el programa no abriría sin decir por qué."""
    _, puerto, _ = servidor
    assert puerto > 0


def test_el_token_es_largo_y_distinto_en_cada_arranque(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    tokens = set()
    for i in range(3):
        registro = Registro(tmp_path / f"t{i}")
        token, _, _ = desktop.servidor(Deposito(tmp_path / f"f{i}"), registro)
        tokens.add(token)
        registro.cerrar()
        desktop.apagar()

    assert len(tokens) == 3
    assert all(len(t) >= 32 for t in tokens)


def test_la_pagina_trae_el_token_adentro(servidor):
    """Es cómo lo recibe el JavaScript. En la web lo va a inyectar el
    servidor con la sesión del usuario, sin tocar el JavaScript."""
    token, _, url = servidor

    html = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")

    assert f'name="token" content="{token}"' in html
    assert 'name="escritorio" content="1"' in html


def test_sin_token_la_api_rechaza(servidor):
    _, _, url = servidor

    with pytest.raises(Exception) as capturado:
        urllib.request.urlopen(f"{url}/api/materiales", timeout=5)

    assert "401" in str(capturado.value)


def test_con_token_la_api_responde(servidor):
    token, _, url = servidor
    pedido = urllib.request.Request(f"{url}/api/materiales", headers={"X-Token": token})

    respuesta = urllib.request.urlopen(pedido, timeout=5)

    assert respuesta.status == 200


def test_autotest_sale_con_cero(tmp_path, monkeypatch, capsys):
    """La prueba que corre sobre el ejecutable congelado. Los bugs de
    empaquetado no aparecen en ningún otro test."""
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")

    assert desktop.main(["--autotest"]) == 0
    assert "ok" in capsys.readouterr().out.lower()


def test_autotest_falla_si_falta_un_recurso(tmp_path, monkeypatch, capsys):
    """Es exactamente el modo en que rompe un ejecutable mal armado."""
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    monkeypatch.setattr(
        rutas, "recurso",
        lambda nombre: (_ for _ in ()).throw(FileNotFoundError(f"falta {nombre}")),
    )

    assert desktop.main(["--autotest"]) == 1
    assert "falta" in capsys.readouterr().err.lower()


def test_el_autotest_carga_el_motor_de_la_ventana(tmp_path, monkeypatch):
    """El agujero por el que se coló el bug que le llegó al primer usuario.

    El autotest arrancaba el servidor, pedía una ruta, decía "ok" y salía 0
    sin haber tocado una sola línea del stack de la ventana: `import webview`
    estaba en la rama de `main()` que el autotest justamente no toma. El .exe
    se armaba con el check en verde y reventaba al abrirlo.
    """
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    llamadas = []
    monkeypatch.setattr(desktop, "motor_de_ventana", lambda: llamadas.append(1))

    assert desktop.main(["--autotest"]) == 0
    assert llamadas == [1]


def test_el_autotest_falla_si_el_motor_de_la_ventana_no_carga(
    tmp_path, monkeypatch, capsys
):
    """Que falle es todo el punto: es lo que tiene que frenar al paquete
    antes de que salga de la máquina que lo arma."""
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")

    def explota():
        raise desktop.VentanaNoDisponible("el motor de la ventana no cargó")

    monkeypatch.setattr(desktop, "motor_de_ventana", explota)

    assert desktop.main(["--autotest"]) == 1
    assert "el motor de la ventana no cargó" in capsys.readouterr().err


def test_desmarcar_zona_internet_borra_la_marca_de_las_dll(tmp_path, monkeypatch):
    """La marca que Windows le pone a todo lo que sale de un .zip bajado.

    .NET se niega a cargar un assembly marcado así, y eso es exactamente lo
    que rompió en la máquina del primer usuario: el programa arrancaba (a
    Python la marca no le importa) y moría al cargar Python.Runtime.dll.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    (tmp_path / "pythonnet" / "runtime").mkdir(parents=True)
    (tmp_path / "pythonnet" / "runtime" / "Python.Runtime.dll").write_bytes(b"")
    (tmp_path / "clr_loader.dll").write_bytes(b"")
    (tmp_path / "materials.yaml").write_bytes(b"")
    borrados = []
    monkeypatch.setattr(desktop.os, "remove", borrados.append)

    assert desktop.desmarcar_zona_internet(tmp_path) == 2
    assert all(ruta.endswith(":Zone.Identifier") for ruta in borrados)
    assert any("Python.Runtime.dll" in ruta for ruta in borrados)
    assert not any("materials.yaml" in ruta for ruta in borrados)


def test_desmarcar_zona_internet_no_toca_nada_fuera_de_windows(tmp_path, monkeypatch):
    """`Zone.Identifier` es un flujo alternativo de NTFS. En Mac, el nombre
    con dos puntos es un archivo común y borrarlo sería borrar otra cosa."""
    monkeypatch.setattr(sys, "platform", "darwin")
    (tmp_path / "algo.dll").write_bytes(b"")
    borrados = []
    monkeypatch.setattr(desktop.os, "remove", borrados.append)

    assert desktop.desmarcar_zona_internet(tmp_path) == 0
    assert borrados == []


def test_desmarcar_zona_internet_sigue_cuando_un_archivo_no_se_deja(
    tmp_path, monkeypatch
):
    """Lo normal es que la marca no esté: ahí `os.remove` tira
    FileNotFoundError por cada archivo. Y en una carpeta de sólo lectura tira
    PermissionError. Ninguno de los dos puede impedir que el programa abra:
    si la marca sigue estando, el mensaje de `motor_de_ventana` explica cómo
    sacarla a mano."""
    monkeypatch.setattr(sys, "platform", "win32")
    (tmp_path / "primera.dll").write_bytes(b"")
    (tmp_path / "segunda.dll").write_bytes(b"")
    intentos = []

    def negarse(ruta):
        intentos.append(ruta)
        raise PermissionError(ruta)

    monkeypatch.setattr(desktop.os, "remove", negarse)

    assert desktop.desmarcar_zona_internet(tmp_path) == 0
    assert len(intentos) == 2


def test_el_motor_de_la_ventana_desmarca_antes_de_cargar(monkeypatch):
    """Al revés no sirve de nada: para cuando .NET rechazó el assembly, el
    error ya está tirado."""
    orden = []
    monkeypatch.setattr(
        desktop, "desmarcar_zona_internet", lambda: orden.append("desmarcar")
    )

    desktop.motor_de_ventana(inicializar=lambda: orden.append("cargar"))

    assert orden == ["desmarcar", "cargar"]


def test_el_motor_de_la_ventana_explica_la_marca_de_internet(monkeypatch):
    """El usuario recibió un renglón que no nombra ni la causa ni la salida.
    Esto es lo que tendría que haber leído en su lugar."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(desktop, "desmarcar_zona_internet", lambda: 0)

    def explota():
        raise RuntimeError(
            "Failed to resolve Python.Runtime.Loader.Initialize from "
            r"C:\Nesting\_internal\pythonnet\runtime\Python.Runtime.dll"
        )

    with pytest.raises(desktop.VentanaNoDisponible) as capturado:
        desktop.motor_de_ventana(inicializar=explota)

    mensaje = str(capturado.value)
    assert "Unblock-File" in mensaje
    # El error de abajo no se pierde: es lo único que distingue este caso de
    # cualquier otra cosa que no cargue.
    assert "Failed to resolve" in mensaje


def test_el_aviso_se_ve_aunque_no_haya_consola(monkeypatch):
    """El .exe se arma con `console=False` -- si no, queda una ventana negra
    detrás del programa --, y eso hace que stdout y stderr no vayan a ningún
    lado. Un print ahí es un programa que se cierra sin decir nada, que para
    el que lo recibió es peor que el error feo."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(rutas, "esta_congelado", lambda: True)
    carteles = []
    monkeypatch.setattr(desktop, "_cartel", carteles.append)

    desktop.avisar("la ventana no abrió")

    assert carteles == ["la ventana no abrió"]


def test_el_aviso_desde_la_terminal_no_abre_un_cartel(monkeypatch, capsys):
    """Corriendo del repo la salida se ve, y un modal sería una molestia."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(rutas, "esta_congelado", lambda: False)
    carteles = []
    monkeypatch.setattr(desktop, "_cartel", carteles.append)

    desktop.avisar("la ventana no abrió")

    assert carteles == []
    assert "la ventana no abrió" in capsys.readouterr().err


def test_el_usuario_se_entera_de_que_la_ventana_no_abrio(monkeypatch):
    """Es el caso que llegó reportado: doble click y nada."""
    monkeypatch.setattr(desktop, "falta_webview2", lambda: False)

    def explota():
        raise desktop.VentanaNoDisponible("la parte de .NET no cargó")

    monkeypatch.setattr(desktop, "motor_de_ventana", explota)
    avisos = []
    monkeypatch.setattr(desktop, "avisar", avisos.append)

    assert desktop.main([]) == 1
    assert avisos == ["la parte de .NET no cargó"]


def test_el_motor_de_la_ventana_deja_un_backend_elegido():
    """Sin backend no hay ventana, y `import webview` solo no lo carga: el
    que lo elige -- y el que abajo termina en pythonnet y en .NET, que es
    donde rompió en Windows -- es `initialize()`."""
    # Por sys.modules y no por `webview.guilib`: el paquete pisa ese nombre
    # con None, así que el atributo no es el módulo.
    import importlib

    desktop.motor_de_ventana()

    assert importlib.import_module("webview.guilib").guilib is not None


def test_webview2_solo_se_verifica_en_windows(monkeypatch):
    """En Mac y Linux la pregunta no tiene sentido y tiene que dar False sin
    tocar el registro de Windows."""
    monkeypatch.setattr(sys, "platform", "darwin")
    assert desktop.falta_webview2() is False


def test_el_puente_rechaza_guardar_fuera_de_lo_que_el_usuario_eligio(tmp_path):
    """El destino lo elige el usuario en un diálogo nativo. Aceptar una ruta
    que el JavaScript arme sola sería dejarlo escribir donde quiera."""
    puente = desktop.Puente()

    with pytest.raises(PermissionError):
        puente.guardar(str(tmp_path / "no_elegido.dxf"), [1, 2, 3])


def test_el_puente_guarda_lo_que_el_usuario_eligio(tmp_path):
    puente = desktop.Puente()
    destino = tmp_path / "elegido.dxf"
    puente._autorizar(str(destino))

    puente.guardar(str(destino), [65, 66])

    assert destino.read_bytes() == b"AB"


def test_arranca_sin_nada_pendiente_de_guardar():
    assert desktop.Puente().hay_sin_guardar is False


def test_la_interfaz_puede_marcar_que_hay_algo_sin_guardar():
    """El DXF vive en una carpeta temporal hasta que el usuario lo guarda.
    Cerrar el programa sin guardarlo pierde media hora de acomodo, y sin
    este aviso se pierde en silencio."""
    puente = desktop.Puente()

    puente.marcar_sin_guardar(True)
    assert puente.hay_sin_guardar is True

    puente.marcar_sin_guardar(False)
    assert puente.hay_sin_guardar is False


def test_el_puente_rechaza_guardar_a_traves_de_un_symlink(tmp_path):
    """Si en el destino elegido ya hay un enlace simbólico, `resolve()` lo
    sigue en silencio y autoriza -- y después escribe -- el archivo al que
    apunta, no el que el usuario vio en el diálogo. Tiene que rechazarse, y
    la víctima no puede haber cambiado."""
    import os

    victima = tmp_path / "victima.txt"
    victima.write_text("dato sensible original")
    elegido = tmp_path / "elegido.dxf"
    os.symlink(victima, elegido)

    puente = desktop.Puente()
    puente._autorizar(str(elegido))

    with pytest.raises(PermissionError):
        puente.guardar(str(elegido), [65, 66])

    assert victima.read_text() == "dato sensible original"


def test_el_puente_rechaza_symlink_creado_despues_de_autorizar(tmp_path):
    """El enlace puede aparecer en el hueco entre elegir el destino y
    guardar. El chequeo tiene que hacerse en `guardar`, no sólo confiar en
    lo que había en el momento de `_autorizar`."""
    import os

    victima = tmp_path / "victima.txt"
    victima.write_text("dato sensible original")
    destino = tmp_path / "elegido.dxf"

    puente = desktop.Puente()
    puente._autorizar(str(destino))
    os.symlink(victima, destino)

    with pytest.raises(PermissionError):
        puente.guardar(str(destino), [65, 66])

    assert victima.read_text() == "dato sensible original"


def test_el_puente_rechaza_guardar_a_traves_de_un_hard_link(tmp_path):
    """Un hard link no es un symlink: `is_symlink()` da False y el chequeo
    de arriba lo deja pasar. Pero `elegido` y `victima` son dos nombres del
    mismo inodo, así que escribir en uno escribe en el otro -- y encima el
    selector de archivos no tiene forma de marcarlo, porque a simple vista
    es un archivo común. Tiene que rechazarse, y la víctima no puede haber
    cambiado."""
    import os

    if sys.platform == "win32":
        pytest.skip("el chequeo de hard links no corre en Windows")

    victima = tmp_path / "cliente_importante.txt"
    victima.write_text("CONTRATO ORIGINAL - NO TOCAR")
    elegido = tmp_path / "pieza.dxf"
    os.link(victima, elegido)

    puente = desktop.Puente()
    puente._autorizar(str(elegido))

    with pytest.raises(PermissionError):
        puente.guardar(str(elegido), list(b"DXF FALSO"))

    assert victima.read_text() == "CONTRATO ORIGINAL - NO TOCAR"


def test_el_puente_permite_sobrescribir_un_archivo_comun_existente(tmp_path):
    """El chequeo de hard links no puede romper el caso normal: sobrescribir
    un archivo propio, que tiene un único nombre (`st_nlink == 1`), tiene
    que seguir funcionando."""
    puente = desktop.Puente()
    destino = tmp_path / "elegido.dxf"
    destino.write_text("version vieja")
    puente._autorizar(str(destino))

    puente.guardar(str(destino), list(b"version nueva"))

    assert destino.read_bytes() == b"version nueva"


def test_el_puente_permite_guardar_un_archivo_que_todavia_no_existe(tmp_path):
    """Si el destino no existe todavía -- el caso normal al guardar -- no
    hay inodo que consultar, y el chequeo de hard links no tiene que
    interponerse."""
    puente = desktop.Puente()
    destino = tmp_path / "nuevo.dxf"
    puente._autorizar(str(destino))

    puente.guardar(str(destino), list(b"contenido"))

    assert destino.read_bytes() == b"contenido"


def test_guardar_deja_de_marcar_pendiente(tmp_path):
    """Guardar es justamente lo que resuelve el pendiente. Que el JavaScript
    tenga que acordarse de avisarlo aparte sería una forma de olvidarse."""
    puente = desktop.Puente()
    puente.marcar_sin_guardar(True)
    destino = tmp_path / "elegido.dxf"
    puente._autorizar(str(destino))

    puente.guardar(str(destino), [65])

    assert puente.hay_sin_guardar is False


def test_los_dialogos_usan_la_api_vigente_de_pywebview():
    """`OPEN_DIALOG` y `SAVE_DIALOG` están deprecados: cada llamada imprime
    un aviso y van a desaparecer. En el paquete armado esa consola no se ve,
    así que el día que pywebview los saque nos enteraríamos por un diálogo
    que deja de abrir -- justo el que elige el archivo o el que guarda el
    DXF, o sea el programa entero."""
    import webview

    # Sin los comentarios: el comentario que explica POR QUÉ no se usan los
    # nombres viejos los nombra, y un test que se agarra de eso falla por el
    # motivo equivocado.
    fuente = "\n".join(
        linea.split("#")[0]
        for linea in Path(desktop.__file__).read_text(encoding="utf-8").splitlines()
    )
    for viejo in ("OPEN_DIALOG", "SAVE_DIALOG"):
        assert viejo not in fuente, f"webview.{viejo} está deprecado"
    assert "webview.FileDialog.OPEN" in fuente
    assert "webview.FileDialog.SAVE" in fuente
    # Que los nombres nuevos existan de verdad en la versión instalada: sin
    # esto el test pasaría igual con un typo.
    assert webview.FileDialog.OPEN and webview.FileDialog.SAVE


# --- cerrar la ventana con un acomodo sin guardar ---------------------------


class PuenteFalso:
    def __init__(self, hay_sin_guardar=True):
        self.hay_sin_guardar = hay_sin_guardar


def test_sin_nada_en_riesgo_la_ventana_cierra_sin_preguntar():
    preguntas = []
    cierre = desktop.CierreSeguro(
        PuenteFalso(hay_sin_guardar=False),
        preguntar=lambda: preguntas.append(1) or True,
        cerrar=lambda: None,
    )

    assert cierre.puede_cerrar() is True
    assert preguntas == [], "preguntó por un acomodo que ya estaba guardado"


def test_el_hilo_que_cierra_queda_libre_para_dibujar_el_dialogo():
    """El bug que reportó el usuario: la app se colgaba al cerrar después de
    acomodar.

    `preguntar` acá imita la forma exacta del diálogo de pywebview en macOS:
    encola el dibujo en el run loop del hilo que pidió cerrar y después
    espera un semáforo. Si `puede_cerrar()` lo llamara sin salirse de ese
    hilo, ese hilo quedaría esperando a que se libere algo que sólo él puede
    liberar, y el programa no cierra nunca más.
    """
    import queue as _queue

    run_loop = _queue.Queue()
    contestado = threading.Event()
    cerrado = threading.Event()

    def preguntar():
        listo = threading.Semaphore(0)
        run_loop.put(listo.release)          # AppHelper.callAfter(...)
        adquirido = listo.acquire(timeout=3)  # semaphore.acquire()
        assert adquirido, (
            "el diálogo no llegó a dibujarse: se preguntó desde el mismo "
            "hilo que tiene que atender el run loop"
        )
        contestado.set()
        return True

    cierre = desktop.CierreSeguro(PuenteFalso(), preguntar, cerrado.set)

    # Este es "el hilo principal de Cocoa". Tiene que volver enseguida.
    assert cierre.puede_cerrar() is False, "el primer cierre no se cancela"

    # Y recién ahora puede atender su run loop, que es lo que en la versión
    # con el bug quedaba bloqueado.
    run_loop.get(timeout=3)()

    assert contestado.wait(3), "el diálogo nunca contestó"
    assert cerrado.wait(3), "aceptó perder el acomodo y la ventana no cerró"
    assert cierre.puede_cerrar() is True, "el cierre confirmado no pasa"


def test_si_el_usuario_dice_que_no_la_ventana_no_cierra_y_puede_reintentar():
    veces = []

    def preguntar():
        veces.append(1)
        return False

    cerrado = threading.Event()
    cierre = desktop.CierreSeguro(
        PuenteFalso(), preguntar, cerrado.set, en_hilo=lambda f: f()
    )

    assert cierre.puede_cerrar() is False
    assert not cerrado.is_set(), "cerró una ventana que el usuario quiso dejar abierta"
    assert cierre.puede_cerrar() is False
    assert len(veces) == 2, (
        "el segundo intento de cerrar no vuelve a preguntar: el usuario "
        "queda sin forma de salir"
    )


def test_dos_clicks_seguidos_no_abren_dos_dialogos():
    """El diálogo tarda en aparecer y la gente hace click de nuevo."""
    abiertos = []
    soltar = threading.Event()

    def preguntar():
        abiertos.append(1)
        soltar.wait(3)
        return False

    cierre = desktop.CierreSeguro(PuenteFalso(), preguntar, lambda: None)
    cierre.puede_cerrar()
    cierre.puede_cerrar()
    cierre.puede_cerrar()
    soltar.set()

    assert abiertos == [1], f"se abrieron {len(abiertos)} diálogos encima"


def test_si_el_dialogo_falla_la_ventana_igual_cierra(capsys):
    """La alternativa sería una ventana que no cierra nunca y un usuario sin
    forma de salir. Un DXF se vuelve a generar apretando Acomodar."""
    def preguntar():
        raise RuntimeError("no hay pantalla")

    cerrado = threading.Event()
    cierre = desktop.CierreSeguro(
        PuenteFalso(), preguntar, cerrado.set, en_hilo=lambda f: f()
    )

    assert cierre.puede_cerrar() is False
    assert cerrado.is_set(), "el programa quedó trabado por un diálogo que falló"
    assert "no hay pantalla" in capsys.readouterr().err, (
        "el fallo se tragó sin dejar rastro"
    )


# --- que el servidor sólo le conteste a su propia ventana -------------------


def _pedir(app, ruta="/", cabeceras=None, tipo="http"):
    """Corre un pedido ASGI contra `app` y devuelve (estado, cuerpo)."""
    import asyncio

    scope = {
        "type": tipo, "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "path": ruta, "raw_path": ruta.encode(),
        "query_string": b"", "root_path": "", "scheme": "http",
        "headers": [(k.lower().encode(), v.encode())
                    for k, v in (cabeceras or {}).items()],
        "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", 8000),
    }
    recibidos = []

    async def send(mensaje):
        recibidos.append(mensaje)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    asyncio.run(app(scope, receive, send))
    estado = next((m.get("status") for m in recibidos if "status" in m), None)
    cuerpo = b"".join(m.get("body", b"") for m in recibidos)
    return estado, cuerpo, recibidos


async def _interior(scope, receive, send):
    """Lo que hay detrás de la cerradura. Si contesta, es que pasó."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"el token secreto"})


@pytest.mark.parametrize("host", [
    "127.0.0.1:53000", "127.0.0.1", "localhost:53000", "LOCALHOST:53000",
    "[::1]:53000",
])
def test_la_ventana_de_verdad_entra(host):
    app = desktop._SoloDesdeEstaVentana(_interior)
    estado, cuerpo, _ = _pedir(app, cabeceras={"Host": host})
    assert estado == 200, host
    assert b"secreto" in cuerpo


@pytest.mark.parametrize("host", [
    "evil.attacker.com",
    "evil.attacker.com:53000",
    "localtest.me:53000",          # un dominio que de verdad resuelve a 127.0.0.1
    "127.0.0.1.evil.com",          # el prefijo no alcanza
    "evil.com:53000@127.0.0.1",
    "",
])
def test_un_pedido_rebindeado_rebota(host):
    """El ataque completo, reproducido antes de escribir esta defensa: una
    página cualquiera que el usuario visite pone el TTL de su DNS en cero y
    rebindea su dominio a 127.0.0.1. Para el navegador sigue siendo el mismo
    origen, así que la deja leer las respuestas -- y `GET /` devuelve el token
    en un `<meta>` sin pedir nada a cambio, porque es como arranca la
    interfaz. Con ese token se encadena `POST /api/archivos/local`, que acepta
    cualquier ruta del disco, y sale el dibujo del usuario.

    Lo que lo corta es el `Host`: después del rebinding el navegador sigue
    mandando el dominio del atacante. Y no lo puede falsificar, porque `Host`
    es una cabecera prohibida para el JavaScript.
    """
    app = desktop._SoloDesdeEstaVentana(_interior)
    estado, cuerpo, _ = _pedir(app, cabeceras={"Host": host})
    assert estado == 403, host
    assert b"secreto" not in cuerpo, "se filtró el contenido protegido"


def test_un_origen_ajeno_rebota_aunque_el_host_este_bien():
    """Segunda cerradura, por si alguna vez se llega con el Host correcto
    desde otra página."""
    app = desktop._SoloDesdeEstaVentana(_interior)
    estado, _, _ = _pedir(app, cabeceras={
        "Host": "127.0.0.1:53000", "Origin": "https://evil.attacker.com"})
    assert estado == 403


def test_el_origen_propio_pasa():
    app = desktop._SoloDesdeEstaVentana(_interior)
    estado, _, _ = _pedir(app, cabeceras={
        "Host": "127.0.0.1:53000", "Origin": "http://127.0.0.1:53000"})
    assert estado == 200


def test_un_websocket_rebindeado_se_cierra():
    """El scope de websocket no pasa por el mismo camino de respuesta, así
    que se cubre aparte: cerrar, no contestar 403."""
    app = desktop._SoloDesdeEstaVentana(_interior)
    _, _, mensajes = _pedir(app, cabeceras={"Host": "evil.attacker.com"},
                            tipo="websocket")
    assert mensajes == [{"type": "websocket.close", "code": 1008}]


def test_la_cerradura_esta_por_afuera_de_la_que_entrega_el_token():
    """El orden importa y no es intercambiable: la página que trae el token
    es justamente lo que el atacante quiere leer, así que tiene que quedar
    DETRÁS de la cerradura."""
    fuente = Path(desktop.__file__).read_text(encoding="utf-8")
    armado = next(l for l in fuente.splitlines() if "app = _SoloDesdeEstaVentana" in l)
    assert "_ConToken" in armado, (
        "el chequeo de Host dejó de envolver a lo que sirve el token"
    )
