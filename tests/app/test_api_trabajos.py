"""El ciclo de un trabajo, de punta a punta y con el motor de verdad."""

import time

import ezdxf
import pytest
from fastapi.testclient import TestClient

from nesting_app import rutas
from nesting_app.api import crear_app
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro

TOKEN = "token-de-prueba"


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    registro = Registro(tmp_path / "trabajos")
    app = crear_app(TOKEN, Deposito(tmp_path / "fuentes"), registro)
    with TestClient(app) as c:
        c.headers["X-Token"] = TOKEN
        yield c
    registro.cerrar()


def fuente_de(cliente, tmp_path, cuadrados=((0, 0, 200), (300, 0, 150))):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    for x, y, lado in cuadrados:
        msp.add_lwpolyline(
            [(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado)], close=True
        )
    ruta = tmp_path / "entrada.dxf"
    doc.saveas(ruta)
    return cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()["id"]


def esperar(cliente, trabajo_id, estados, limite=60.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        cuerpo = cliente.get(f"/api/trabajos/{trabajo_id}").json()
        if cuerpo["estado"] in estados:
            return cuerpo
        time.sleep(0.02)
    raise AssertionError(f"quedó en {cuerpo['estado']}, esperaba {estados}")


def test_el_ciclo_completo(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)

    creado = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id,
        "params": {"material": "mdf18", "sep": 3, "esfuerzo": "rapido"},
    })
    assert creado.status_code == 200

    cuerpo = esperar(cliente, creado.json()["id"], {"listo"})

    assert cuerpo["resultado"]["placas"] == 1
    assert 0 < cuerpo["resultado"]["total"] <= 1
    assert cuerpo["resultado"]["sobrante_mm"] > 0
    assert cuerpo["error"] is None


def test_los_tres_archivos_se_pueden_bajar(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "rapido"},
    }).json()["id"]
    esperar(cliente, trabajo_id, {"listo"})

    # El DXF se compara sin el salto de línea a propósito. ezdxf escribe en
    # modo texto, así que en Windows el archivo arranca con "  0\r\n" y en
    # macOS con "  0\n". Las dos cosas son DXF válido -- AutoCAD en Windows
    # escribe CRLF -- y cualquier lector acepta las dos. La versión anterior
    # comparaba los primeros cuatro bytes contra b"  0\n" y fallaba en
    # Windows por el \r, marcando como roto un archivo perfectamente bueno.
    for nombre, arranque in [
        ("salida.dxf", b"  0"),
        ("preview.png", b"\x89PNG"),
        ("diagnostico.png", b"\x89PNG"),
    ]:
        respuesta = cliente.get(f"/api/trabajos/{trabajo_id}/{nombre}")
        assert respuesta.status_code == 200, nombre
        assert respuesta.content.startswith(arranque), nombre

    dxf = cliente.get(f"/api/trabajos/{trabajo_id}/salida.dxf").content
    assert dxf[3:4] in (b"\n", b"\r"), "después del código de grupo va un salto de línea"


def test_el_nombre_de_archivo_no_sale_de_la_lista_permitida(cliente, tmp_path):
    """El nombre del archivo a bajar no puede venir del cliente sin filtrar:
    sólo salida.dxf, preview.png y diagnostico.png son válidos. Un nombre
    cualquiera, aunque exista de verdad en otro lado del disco, tiene que
    rebotar con 404 -- nunca con un 409 de 'todavía no lo produjo', que
    delataría que se llegó a mirar el sistema de archivos con ese nombre.
    """
    secreto = tmp_path / "secreto.txt"
    secreto.write_text("no debería poder leerse esto")

    fuente_id = fuente_de(cliente, tmp_path)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "rapido"},
    }).json()["id"]
    esperar(cliente, trabajo_id, {"listo"})

    for intento in ("secreto.txt", "salida.dxf.txt", "Salida.dxf"):
        respuesta = cliente.get(f"/api/trabajos/{trabajo_id}/{intento}")
        assert respuesta.status_code == 404, intento
        assert "no debería poder leerse esto" not in respuesta.text


def test_un_parametro_invalido_se_rechaza_nombrando_el_campo(cliente, tmp_path):
    """La interfaz pone el mensaje debajo del campo que lo tiene mal, así que
    necesita saber cuál es -- no alcanza con el texto."""
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "sep": -5},
    })

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["campo"] == "sep"


def test_un_material_que_no_existe_da_404(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "inventado"},
    })

    assert respuesta.status_code == 404


def test_cancelar_deja_el_trabajo_cancelado(cliente, tmp_path):
    """Con muchas piezas y esfuerzo lento hay tiempo de sobra para cortar."""
    cuadrados = [(i * 60 % 1500, (i * 60 // 1500) * 60, 50) for i in range(120)]
    fuente_id = fuente_de(cliente, tmp_path, cuadrados)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "lento"},
    }).json()["id"]

    esperar(cliente, trabajo_id, {"corriendo"})
    assert cliente.post(f"/api/trabajos/{trabajo_id}/cancelar").status_code == 200

    cuerpo = esperar(cliente, trabajo_id, {"cancelado"})
    assert cuerpo["resultado"] is None


def test_un_trabajo_cancelado_no_deja_archivos_para_bajar(cliente, tmp_path):
    cuadrados = [(i * 60 % 1500, (i * 60 // 1500) * 60, 50) for i in range(120)]
    fuente_id = fuente_de(cliente, tmp_path, cuadrados)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "lento"},
    }).json()["id"]
    esperar(cliente, trabajo_id, {"corriendo"})
    cliente.post(f"/api/trabajos/{trabajo_id}/cancelar")
    esperar(cliente, trabajo_id, {"cancelado"})

    assert cliente.get(f"/api/trabajos/{trabajo_id}/salida.dxf").status_code == 409


def test_el_avance_se_ve_mientras_corre(cliente, tmp_path):
    cuadrados = [(i * 60 % 1500, (i * 60 // 1500) * 60, 50) for i in range(120)]
    fuente_id = fuente_de(cliente, tmp_path, cuadrados)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "lento"},
    }).json()["id"]

    fin = time.monotonic() + 30
    visto = None
    while time.monotonic() < fin:
        cuerpo = cliente.get(f"/api/trabajos/{trabajo_id}").json()
        if cuerpo["avance"]:
            visto = cuerpo["avance"]
            break
        time.sleep(0.02)

    cliente.post(f"/api/trabajos/{trabajo_id}/cancelar")
    assert visto is not None
    assert visto["totales"] == 120
    assert visto["intentos"] == 12


def test_un_trabajo_que_no_existe_da_404(cliente):
    assert cliente.get("/api/trabajos/no-existe").status_code == 404
    assert cliente.post("/api/trabajos/no-existe/cancelar").status_code == 404


def test_bajar_un_archivo_de_un_trabajo_que_no_termino_da_409(cliente, tmp_path):
    cuadrados = [(i * 60 % 1500, (i * 60 // 1500) * 60, 50) for i in range(120)]
    fuente_id = fuente_de(cliente, tmp_path, cuadrados)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "lento"},
    }).json()["id"]

    respuesta = cliente.get(f"/api/trabajos/{trabajo_id}/salida.dxf")
    cliente.post(f"/api/trabajos/{trabajo_id}/cancelar")

    assert respuesta.status_code == 409


def test_un_archivo_sin_piezas_termina_en_error_no_en_bug(cliente, tmp_path):
    """Un DXF vacío es un problema del archivo, no del programa. La interfaz
    lo muestra como 'revisá esto', no como 'se rompió el programa'."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    ruta = tmp_path / "vacio.dxf"
    doc.saveas(ruta)
    fuente_id = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()["id"]

    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "rapido"},
    }).json()["id"]

    cuerpo = esperar(cliente, trabajo_id, {"error"})
    assert cuerpo["es_bug"] is False
    assert "pieza" in cuerpo["error"].lower()


def test_el_diagnostico_existe_aunque_el_trabajo_falle(cliente, tmp_path):
    """Es justamente cuando más sirve: el archivo no dio ninguna pieza y el
    usuario necesita ver qué se descartó."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    ruta = tmp_path / "vacio.dxf"
    doc.saveas(ruta)
    fuente_id = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()["id"]
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "rapido"},
    }).json()["id"]
    esperar(cliente, trabajo_id, {"error"})

    assert cliente.get(f"/api/trabajos/{trabajo_id}/diagnostico.png").status_code == 200


def test_la_resolucion_por_omision_de_la_api_es_uno():
    from nesting_app.api import ParamsEntrada

    assert ParamsEntrada(material="mdf18").a_params().resolucion == 1.0


def test_los_recortes_llegan_al_params():
    from nesting_app.api import ParamsEntrada

    entrada = ParamsEntrada(
        material="mdf18",
        recortes=[{"ancho": 600.0, "alto": 800.0, "cantidad": 2, "veta_cruzada": True}],
    )
    recortes = entrada.a_params().recortes

    assert len(recortes) == 1
    assert recortes[0].cantidad == 2
    assert recortes[0].veta_cruzada is True
