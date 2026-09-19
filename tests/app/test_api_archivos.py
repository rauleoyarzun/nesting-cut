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
