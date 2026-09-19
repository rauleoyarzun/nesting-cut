"""Las rutas de materiales, y el token que protege todas las rutas."""

import re

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nesting_app import materials_store, rutas
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


def test_sin_token_no_se_puede_hacer_nada(cliente):
    """El servidor escucha en localhost, pero cualquier página abierta en el
    navegador del usuario también puede hablarle a localhost."""
    del cliente.headers["X-Token"]

    assert cliente.get("/api/materiales").status_code == 401


def test_con_un_token_equivocado_tampoco(cliente):
    cliente.headers["X-Token"] = "otro"

    assert cliente.get("/api/materiales").status_code == 401


def test_listar_devuelve_el_catalogo_sembrado(cliente):
    datos = cliente.get("/api/materiales").json()

    nombres = [m["nombre"] for m in datos["materiales"]]
    assert "mdf18" in nombres
    assert "multilam18" in nombres


def test_cada_material_dice_su_veta_en_palabras(cliente):
    """La interfaz muestra dos opciones con nombre, nunca un número de
    grados. La traducción vive en la API para que no la haga el JavaScript."""
    datos = cliente.get("/api/materiales").json()
    por_nombre = {m["nombre"]: m for m in datos["materiales"]}

    assert por_nombre["mdf18"]["veta"] == "libre"
    assert por_nombre["multilam18"]["veta"] == "respetar"


def test_agregar(cliente):
    respuesta = cliente.post("/api/materiales", json={
        "nombre": "melamina18", "ancho": 1830, "alto": 2750, "veta": "libre",
    })

    assert respuesta.status_code == 200
    assert "melamina18" in [m["nombre"] for m in cliente.get("/api/materiales").json()["materiales"]]


def test_agregar_uno_repetido_da_409_con_mensaje(cliente):
    respuesta = cliente.post("/api/materiales", json={
        "nombre": "mdf18", "ancho": 100, "alto": 100, "veta": "libre",
    })

    assert respuesta.status_code == 409
    assert "mdf18" in respuesta.json()["detail"]


@pytest.mark.parametrize("campo, valor", [("ancho", 0), ("alto", -5), ("ancho", 0.0)])
def test_una_medida_que_no_es_positiva_se_rechaza(cliente, campo, valor):
    """Una placa de ancho cero no es un material, y dejarla entrar haría
    reventar el motor mucho más tarde con un mensaje que no la nombra."""
    cuerpo = {"nombre": "raro", "ancho": 100, "alto": 100, "veta": "libre"}
    cuerpo[campo] = valor

    assert cliente.post("/api/materiales", json=cuerpo).status_code == 422


def test_un_nombre_vacio_se_rechaza(cliente):
    respuesta = cliente.post("/api/materiales", json={
        "nombre": "  ", "ancho": 100, "alto": 100, "veta": "libre",
    })

    assert respuesta.status_code == 422


def test_una_veta_inventada_se_rechaza(cliente):
    respuesta = cliente.post("/api/materiales", json={
        "nombre": "raro", "ancho": 100, "alto": 100, "veta": "a_veces",
    })

    assert respuesta.status_code == 422


def test_editar(cliente):
    respuesta = cliente.put("/api/materiales/mdf18", json={
        "nombre": "mdf18", "ancho": 1830, "alto": 2750, "veta": "libre",
    })

    assert respuesta.status_code == 200
    assert materials_store.leer()["mdf18"].sheet_h == 2750.0


def test_editar_uno_que_no_existe_da_404(cliente):
    respuesta = cliente.put("/api/materiales/fantasma", json={
        "nombre": "fantasma", "ancho": 100, "alto": 100, "veta": "libre",
    })

    assert respuesta.status_code == 404


def test_borrar(cliente):
    assert cliente.delete("/api/materiales/mdf15").status_code == 200
    assert "mdf15" not in materials_store.leer()


def test_borrar_uno_que_no_existe_da_404(cliente):
    assert cliente.delete("/api/materiales/fantasma").status_code == 404


def test_restaurar(cliente):
    cliente.delete("/api/materiales/mdf18")

    assert cliente.post("/api/materiales/restaurar").status_code == 200
    assert "mdf18" in materials_store.leer()


def test_un_catalogo_corrupto_da_500_con_la_salida_adentro(cliente):
    """El mensaje tiene que nombrar la salida, porque el usuario no tiene
    ninguna otra forma de saber que se puede restaurar."""
    materials_store.ruta_catalogo().write_text("roto: [\n", encoding="utf-8")

    respuesta = cliente.get("/api/materiales")

    assert respuesta.status_code == 500
    assert "restaurar" in respuesta.json()["detail"].lower()


def test_ninguna_ruta_de_api_puede_saltarse_el_token(cliente):
    """No hay que confiar en que cada ruta nueva se acuerde de pedir el
    token: este test recorre TODAS las rutas que la app tiene registradas
    bajo /api/ -- las de hoy y las que se agreguen mañana, tengan método
    HTTP o sean WebSocket -- y confirma que todas, sin excepción, lo
    exigen.

    A propósito no filtra con `getattr(ruta, "methods", None) or ()`: una
    ruta WebSocket (`APIWebSocketRoute`) no tiene `.methods`, así que ese
    filtro la deja afuera en silencio -- se podría agregar una ruta así sin
    protección y este test seguiría en verde. Acá se clasifica cada ruta
    por si tiene `.methods` o no, y a las que no lo tienen se las verifica
    como WebSocket."""
    del cliente.headers["X-Token"]
    metodos = {"GET": cliente.get, "POST": cliente.post, "PUT": cliente.put, "DELETE": cliente.delete}

    rutas_http = set()
    rutas_ws = set()
    for ruta in cliente.app.routes:
        if not ruta.path.startswith("/api/"):
            continue
        camino = re.sub(r"\{[^}]+\}", "x", ruta.path)
        metodos_de_la_ruta = getattr(ruta, "methods", None)
        if metodos_de_la_ruta is None:
            rutas_ws.add(camino)
        else:
            for metodo in metodos_de_la_ruta:
                if metodo in metodos:
                    rutas_http.add((metodo, camino))

    assert rutas_http, "no se encontró ninguna ruta /api/ para verificar"
    for metodo, ruta in rutas_http:
        respuesta = metodos[metodo](ruta)
        assert respuesta.status_code == 401, f"{metodo} {ruta} no exige token"

    for ruta in rutas_ws:
        with pytest.raises(WebSocketDisconnect):
            with cliente.websocket_connect(ruta):
                pass


def test_una_ruta_websocket_bajo_api_no_se_puede_usar_sin_token(tmp_path, monkeypatch):
    """El middleware es ASGI puro justamente para cubrir este caso: un
    handshake de WebSocket bajo /api/ sin token tiene que cerrarse igual
    que se rechaza con 401 un pedido HTTP. Se agrega la ruta a mano acá
    porque hoy la app todavía no tiene ninguna."""
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    registro = Registro(tmp_path / "trabajos")
    app = crear_app(TOKEN, Deposito(tmp_path / "fuentes"), registro)

    @app.websocket("/api/ws")
    async def _ws_de_prueba(websocket):
        await websocket.accept()

    try:
        with TestClient(app) as cliente:
            with pytest.raises(WebSocketDisconnect):
                with cliente.websocket_connect("/api/ws"):
                    pass
    finally:
        registro.cerrar()


def test_openapi_json_no_esta_disponible(cliente):
    """`docs_url=None` y `redoc_url=None` apagan /docs y /redoc, pero no el
    esquema en sí: /openapi.json no empieza con /api/, así que el
    middleware de token ni lo mira. Sin `openapi_url=None` queda abierto y
    expone las seis rutas, sus métodos y los nombres exactos de cada campo
    a cualquier página que lo pida."""
    del cliente.headers["X-Token"]

    assert cliente.get("/openapi.json").status_code == 404
