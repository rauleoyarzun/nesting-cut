"""Registrar un archivo y analizarlo, por las dos puertas."""

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


def dxf(tmp_path, unidades=4, nombre="entrada.dxf"):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = unidades
    doc.modelspace().add_lwpolyline([(0, 0), (200, 0), (200, 200), (0, 200)], close=True)
    ruta = tmp_path / nombre
    doc.saveas(ruta)
    return ruta


def test_registrar_una_ruta_local(cliente, tmp_path):
    respuesta = cliente.post("/api/archivos/local", json={"ruta": str(dxf(tmp_path))})

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "entrada.dxf"
    assert respuesta.json()["id"]


def test_registrar_una_subida(cliente, tmp_path):
    datos = dxf(tmp_path).read_bytes()

    respuesta = cliente.post(
        "/api/archivos", files={"archivo": ("entrada.dxf", datos, "application/dxf")}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "entrada.dxf"


def test_las_dos_puertas_dan_algo_que_se_analiza_igual(cliente, tmp_path):
    ruta = dxf(tmp_path)
    local = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()
    subido = cliente.post(
        "/api/archivos", files={"archivo": ("entrada.dxf", ruta.read_bytes(), "application/dxf")}
    ).json()

    for fuente in (local, subido):
        analisis = cliente.post("/api/analizar", json={"fuente_id": fuente["id"]}).json()
        assert analisis["piezas"] == 1


def test_una_ruta_que_no_existe_da_404(cliente, tmp_path):
    respuesta = cliente.post("/api/archivos/local", json={"ruta": str(tmp_path / "no.dxf")})

    assert respuesta.status_code == 404


def test_un_cdr_se_rechaza_con_un_mensaje_util(cliente):
    """Es el caso real: el usuario tiene .cdr y hay que decirle qué hacer,
    no sólo que no."""
    respuesta = cliente.post(
        "/api/archivos", files={"archivo": ("dibujo.cdr", b"RIFF", "application/octet-stream")}
    )

    assert respuesta.status_code == 415
    assert "CorelDRAW" in respuesta.json()["detail"]


def test_analizar_devuelve_piezas_avisos_y_descartes(cliente, tmp_path):
    fuente = cliente.post("/api/archivos/local", json={"ruta": str(dxf(tmp_path))}).json()

    analisis = cliente.post("/api/analizar", json={"fuente_id": fuente["id"]}).json()

    assert analisis["piezas"] == 1
    assert analisis["avisos"] == []
    assert analisis["descartes"] == []
    assert analisis["unidades"] == "mm"


def test_analizar_un_archivo_sin_unidades_pide_las_unidades(cliente, tmp_path):
    """No es un error: es una pregunta. El código 409 y la marca
    `faltan_unidades` son lo que le dice a la interfaz que muestre los cinco
    botones en vez de un cartel rojo."""
    ruta = dxf(tmp_path, unidades=0, nombre="sin_unidades.dxf")
    fuente = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()

    respuesta = cliente.post("/api/analizar", json={"fuente_id": fuente["id"]})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["faltan_unidades"] is True


def test_analizar_con_las_unidades_dadas_funciona(cliente, tmp_path):
    ruta = dxf(tmp_path, unidades=0, nombre="sin_unidades.dxf")
    fuente = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()

    analisis = cliente.post(
        "/api/analizar", json={"fuente_id": fuente["id"], "unidades": "mm"}
    ).json()

    assert analisis["piezas"] == 1


def dxf_contorno_abierto(tmp_path):
    """Tres lados de un cuadrado como líneas sueltas: no cierra."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    c = [(0, 0), (200, 0), (200, 200), (0, 200)]
    for i in range(3):
        msp.add_line(c[i], c[i + 1])
    ruta = tmp_path / "abierto.dxf"
    doc.saveas(ruta)
    return ruta


def test_analizar_un_contorno_abierto_da_400_no_500(cliente, tmp_path):
    """`OpenContourError` (como `OverlappingContourError` y
    `NonPlanarCurveError`) hereda de `Exception` a secas, no de `ValueError`.
    Antes, `/api/analizar` sólo atrapaba `ValueError`, así que esto se
    escapaba como un 500 con "Internal Server Error" en texto plano -- el
    mismo archivo que por `/api/trabajos` termina bien clasificado, con el
    mensaje en español."""
    fuente = cliente.post(
        "/api/archivos/local", json={"ruta": str(dxf_contorno_abierto(tmp_path))}
    ).json()

    respuesta = cliente.post("/api/analizar", json={"fuente_id": fuente["id"]})

    assert respuesta.status_code == 400
    assert "no cierran" in respuesta.json()["detail"]


def test_el_mensaje_del_contorno_abierto_nombra_el_control_no_el_flag_de_la_cli(
    cliente, tmp_path
):
    fuente = cliente.post(
        "/api/archivos/local", json={"ruta": str(dxf_contorno_abierto(tmp_path))}
    ).json()

    detalle = cliente.post(
        "/api/analizar", json={"fuente_id": fuente["id"]}
    ).json()["detail"]

    assert "--tol-cierre" not in detalle
    assert "Tolerancia de cierre" in detalle


def test_analizar_un_id_inventado_da_404(cliente):
    respuesta = cliente.post("/api/analizar", json={"fuente_id": "no-existe"})

    assert respuesta.status_code == 404


def test_la_interfaz_se_sirve_en_la_raiz(cliente):
    """Sin token: es la página que trae el token adentro."""
    del cliente.headers["X-Token"]

    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "<!doctype html>" in respuesta.text.lower()


def test_una_ruta_de_api_sigue_respondiendo_despues_de_montar_la_interfaz(cliente):
    """El montaje de la interfaz estática en `/` va al final, a propósito:
    si quedara antes, taparía todo lo que cuelga de /api/. Esto pega tanto
    a la raíz como a una ruta de la API en el mismo test para que una
    regresión en el orden del montaje lo rompa acá."""
    assert cliente.get("/").status_code == 200
    assert cliente.get("/api/materiales").status_code == 200


def test_la_revision_esta_disponible_apenas_se_analiza(cliente, tmp_path):
    """El pedido original: ver cuáles se descartaron sin tener que esperar el
    acomodo. La imagen se sirve desde la fuente, no desde un trabajo."""
    fuente_id = cliente.post(
        "/api/archivos/local", json={"ruta": str(dxf(tmp_path))}
    ).json()["id"]
    cliente.post("/api/analizar", json={"fuente_id": fuente_id, "tol_cierre": 0.1})

    respuesta = cliente.get(f"/api/archivos/{fuente_id}/diagnostico.png")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/png"
    assert respuesta.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_pedir_la_revision_antes_de_analizar_no_es_un_error(cliente, tmp_path):
    """409 y no 404: el archivo está registrado, lo que falta es el análisis.
    La pantalla distingue ese caso y lo explica en el lienzo en vez de abrir
    un cartel de error."""
    fuente_id = cliente.post(
        "/api/archivos/local", json={"ruta": str(dxf(tmp_path))}
    ).json()["id"]

    respuesta = cliente.get(f"/api/archivos/{fuente_id}/diagnostico.png")

    assert respuesta.status_code == 409
    assert "entrada.dxf" in respuesta.json()["detail"]


def test_la_revision_de_una_fuente_que_no_existe_da_404(cliente):
    respuesta = cliente.get("/api/archivos/no-existe/diagnostico.png")

    assert respuesta.status_code == 404


@pytest.mark.parametrize("nombre", [
    "salida.dxf", "preview.png", "app.js", "materials.yaml", "..%2F..%2Fapp.js",
])
def test_por_esta_ruta_no_sale_ningun_otro_archivo(cliente, tmp_path, nombre):
    """`nombre` se compara contra un único valor exacto. Esta ruta vive en la
    capa que en la versión web queda expuesta a internet."""
    fuente_id = cliente.post(
        "/api/archivos/local", json={"ruta": str(dxf(tmp_path))}
    ).json()["id"]
    cliente.post("/api/analizar", json={"fuente_id": fuente_id, "tol_cierre": 0.1})

    respuesta = cliente.get(f"/api/archivos/{fuente_id}/{nombre}")

    assert respuesta.status_code == 404


def test_la_revision_tambien_pide_el_token(tmp_path, monkeypatch):
    """Es una ruta nueva bajo /api/, y el middleware las cubre a todas por
    prefijo justamente para que agregar una no sea un agujero."""
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    registro = Registro(tmp_path / "trabajos")
    app = crear_app(TOKEN, Deposito(tmp_path / "fuentes"), registro)
    try:
        with TestClient(app) as sin_token:
            respuesta = sin_token.get("/api/archivos/lo-que-sea/diagnostico.png")
        assert respuesta.status_code == 401
    finally:
        registro.cerrar()
