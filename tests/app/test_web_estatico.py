"""Que la interfaz estática tenga lo que el JavaScript espera encontrar.

No es un test de aspecto: es un test de contrato. `app.js` busca elementos
por id, y un id que cambió de nombre no falla en ningún lado hasta que
alguien abre la pantalla y un botón no hace nada.
"""

import re

import pytest

from nesting_app import rutas

IDS_OBLIGATORIOS = [
    "pantalla-principal", "nombre-archivo", "btn-archivo", "resumen-archivo",
    "link-descartes", "material", "sep", "borde", "copias", "esfuerzo",
    "avanzadas", "btn-acomodar", "btn-cancelar", "btn-guardar",
    "barra-avance", "texto-avance", "resultado",
    "tab-preview", "tab-revision", "lienzo", "placa-actual",
    "pantalla-materiales", "tabla-materiales", "form-material",
    "m-nombre", "m-ancho", "m-alto", "m-veta-libre", "m-veta-respetar",
    "btn-guardar-material", "btn-cancelar-material", "btn-restaurar", "btn-volver",
    "cartel-unidades", "cartel-error", "texto-error", "detalle-error",
    # Los usa `app.js` y `materiales.js`. Si falta uno, el botón no hace nada
    # y no falla en ningún lado hasta que alguien lo aprieta.
    "btn-materiales", "cuenta-piezas", "pista-avance", "titulo-error",
    "btn-copiar-error", "btn-cerrar-error", "titulo-form", "error-material",
    "angulos", "tol-cierre", "resolucion", "espejo",
]


@pytest.fixture(scope="module")
def html():
    return (rutas.recurso("web") / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css():
    return (rutas.recurso("web") / "app.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("elemento_id", IDS_OBLIGATORIOS)
def test_esta_el_id_que_el_javascript_busca(html, elemento_id):
    assert f'id="{elemento_id}"' in html


def test_ningun_id_esta_repetido(html):
    ids = re.findall(r'id="([^"]+)"', html)
    repetidos = {i for i in ids if ids.count(i) > 1}
    assert not repetidos, f"ids repetidos: {repetidos}"


def test_el_html_declara_espanol(html):
    """Los correctores y los lectores de pantalla lo necesitan."""
    assert 'lang="es"' in html


def test_todo_campo_tiene_su_etiqueta(html):
    """Un input sin label es invisible para un lector de pantalla y su texto
    no se puede clickear para enfocarlo."""
    for campo in ("sep", "borde", "copias", "material", "esfuerzo",
                  "m-nombre", "m-ancho", "m-alto"):
        assert f'for="{campo}"' in html, f"falta el label de {campo}"


def test_los_botones_son_botones_de_verdad(html):
    """Un div con onclick no recibe foco con Tab ni se activa con Enter."""
    for boton in ("btn-acomodar", "btn-cancelar", "btn-guardar", "btn-volver"):
        assert re.search(rf'<button[^>]*id="{boton}"', html), boton


def test_los_tokens_de_color_estan_exactos(css):
    """Son los de la dirección D, elegida sobre cuatro maquetadas. Que estén
    acá y en un solo lugar es lo que permite cambiarlos sin cazar hexas."""
    for token, valor in [
        ("--fondo", "#F4F6F8"),
        ("--panel", "#FFFFFF"),
        ("--lienzo", "#EDF0F4"),
        ("--texto", "#111827"),
        ("--texto-2", "#606B7B"),
        ("--borde", "#E2E6EC"),
        ("--acento", "#047857"),
    ]:
        assert f"{token}: {valor}" in css, token


def test_las_medidas_usan_cifras_tabulares(css):
    """La interfaz es una grilla de medidas que se comparan entre sí, y en
    cifras proporcionales 1830 y 1220 no alinean."""
    assert "font-variant-numeric: tabular-nums" in css


def test_los_controles_miden_44_px(css):
    assert "--alto-control: 44px" in css


def test_no_hay_emojis_en_la_interfaz(html):
    """Los íconos son SVG con trazo. Un emoji se ve distinto en cada sistema
    y en una herramienta de taller queda fuera de lugar."""
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", html)


def test_el_css_se_carga_desde_el_html(html):
    assert 'href="app.css"' in html


def test_el_javascript_se_carga_desde_el_html(html):
    assert 'src="app.js"' in html
