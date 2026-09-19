"""Contrato del JavaScript: que llame a las rutas que la API expone.

No corre un navegador -- eso quedó fuera de alcance a propósito. Verifica
que el archivo hable de las mismas rutas, campos e ids que el servidor y
la interfaz producen, que es la clase de desincronización que rompe la
pantalla en silencio: un endpoint que ya no se llama, un id mal tipeado
que hace que un botón no haga nada, un estado que el servidor manda y que
nadie contempla.
"""

import re

import pytest

from nesting_app import rutas


@pytest.fixture(scope="module")
def js():
    return (rutas.recurso("web") / "app.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html():
    return (rutas.recurso("web") / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("ruta", [
    "/api/materiales", "/api/archivos", "/api/archivos/local",
    "/api/analizar", "/api/trabajos",
])
def test_usa_la_ruta_que_la_api_expone(js, ruta):
    assert ruta in js


def test_manda_el_token_en_cada_pedido(js):
    assert "X-Token" in js


def test_lee_el_token_del_meta(js):
    """`desktop.py` lo inyecta ahí al servir la página. En la web lo va a
    poner el servidor con la sesión: este código no cambia."""
    assert 'name="token"' in js or "'token'" in js


def test_leer_el_token_no_depende_de_estar_en_escritorio(js):
    """El meta de escritorio (`EN_ESCRITORIO`) y el del token son cosas
    separadas: si la lectura del token quedara enredada con esa rama, la
    web -- que nunca pone `meta[name="escritorio"]` -- se quedaría sin
    token."""
    linea_token = next(l for l in js.splitlines() if 'meta[name="token"]' in l)
    assert "EN_ESCRITORIO" not in linea_token
    assert "pywebview" not in linea_token


@pytest.mark.parametrize("estado", ["listo", "cancelado", "error", "corriendo", "pendiente"])
def test_contempla_cada_estado_de_un_trabajo(js, estado):
    assert f'"{estado}"' in js or f"'{estado}'" in js


def test_distingue_un_bug_del_programa_de_un_error_del_dibujo(js):
    """Son dos mensajes distintos: uno manda a corregir el archivo, el otro
    dice que el problema es nuestro y ofrece copiar el detalle."""
    assert "es_bug" in js


def test_el_bug_del_programa_ofrece_copiar_el_detalle_tecnico(js):
    """El cartel de error genérico sabe mostrar un `detalleTecnico`
    opcional; que la rama de `es_bug` se lo pase es lo que hace que el
    botón "Copiar detalle" aparezca sólo cuando corresponde."""
    indice = js.index("es_bug")
    contexto = js[indice:indice + 400]
    assert "detalle_tecnico" in contexto


def test_reacciona_a_que_falten_las_unidades(js):
    assert "faltan_unidades" in js


def test_pone_el_error_de_un_parametro_debajo_de_su_campo(js):
    assert "data-error-de" in js


def test_sondea_con_un_intervalo_razonable(js):
    """Los trabajos tardan de 34 s a 9 minutos. Sondear cada 50 ms sería
    quemar CPU al pedo; cada 5 s se sentiría trabado."""
    intervalos = [int(n) for n in re.findall(r"SONDEO_MS\s*=\s*(\d+)", js)]
    assert intervalos, "no se encontró SONDEO_MS"
    assert 200 <= intervalos[0] <= 1000


def test_la_barra_de_avance_no_retrocede_al_empezar_un_intento_nuevo(js):
    """`nesting/engine/packer.py` reinicia el conteo de piezas ubicadas en
    cada intento nuevo -- a propósito, según su propio docstring de
    `Avance`. Una barra armada sólo con ubicadas/totales retrocedería justo
    ahí, y una barra que retrocede es peor que no tener barra: por eso el
    cálculo que fija el ancho tiene que mirar también el intento."""
    indice = js.index('"barra-avance"')
    contexto = js[max(0, indice - 400):indice]
    assert "intento" in contexto and "ubicadas" in contexto


def test_expone_su_estado_para_la_pantalla_de_materiales(js):
    assert "window.__nesting" in js


def test_expone_mostrar_materiales_para_que_la_tarea_siguiente_se_enganche(js):
    """La tabla, el alta y el borrado son de `materiales.js`; este archivo
    sólo tiene que saber mostrar y ocultar la pantalla para que esa otra
    pieza se pueda enganchar."""
    indice = js.index("window.__nesting")
    contexto = js[indice:indice + 300]
    assert "mostrarMateriales" in contexto


def test_no_asigna_src_o_href_con_una_ruta_de_api_directa(js):
    """`<img>` y `<a download>` son pedidos nativos del navegador: no pueden
    llevar el header `X-Token`, y el middleware de la API rechaza con 401
    todo lo que no lo traiga. Si algo vuelve a escribir `img.src = "/api/..."`
    o `a.href = "/api/..."` directamente, la previsualización y la descarga
    se rompen en silencio otra vez -- por eso el archivo tiene que traerse
    con `api()` y armar un blob (`createObjectURL`) en su lugar."""
    assert not re.search(r'\.(?:src|href)\s*=\s*(?:`|["\'])?/api/', js)


def test_usa_createobjecturl_y_lo_libera_con_revokeobjecturl(js):
    """Cada blob que se crea para una imagen o una descarga tiene que
    liberarse: si no, cambiar de solapa muchas veces deja blobs retenidos
    en memoria mientras la ventana esté abierta."""
    assert "createObjectURL" in js
    assert "revokeObjectURL" in js


def test_todo_id_que_busca_el_js_existe_en_el_html(js, html):
    """Un id que `$("...")` busca y no está en `index.html` no falla en
    ningún lado: el botón correspondiente simplemente se queda mudo, y
    nadie se entera hasta que alguien lo aprieta. Es el error más probable
    de este archivo, y el más fácil de atajar comparando los dos lados."""
    ids_del_html = set(re.findall(r'id="([^"]+)"', html))
    ids_que_busca_el_js = set(re.findall(r'\$\("([^"]+)"\)', js))
    faltantes = ids_que_busca_el_js - ids_del_html
    assert not faltantes, f"ids que $() busca y no están en index.html: {faltantes}"
