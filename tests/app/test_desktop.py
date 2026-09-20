"""El armado del servidor local, el puente de archivos y el autotest."""

from pathlib import Path
import sys
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
