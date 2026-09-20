"""Que la interfaz estática tenga lo que el JavaScript espera encontrar.

No es un test de aspecto: es un test de contrato. `app.js` busca elementos
por id, y un id que cambió de nombre no falla en ningún lado hasta que
alguien abre la pantalla y un botón no hace nada.
"""

import re
import unicodedata

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
    # Los rangos que faltaban dejaban pasar banderas, ⭐, ⌛ y ‼. Se mide por
    # categoría Unicode además de por rango: "So" (símbolo otro) cubre los
    # emojis sueltos sin tener que enumerar bloques a mano.
    sospechosos = [
        c for c in html
        if unicodedata.category(c) == "So" or "\U0001F000" <= c <= "\U0001FAFF"
    ]
    assert not sospechosos, f"hay símbolos que no son texto: {sospechosos}"


def test_la_cascara_no_crece_mas_que_la_ventana(css):
    """Con `min-height: 100vh` la fila `1fr` de la grilla crece hasta donde
    llegue el contenido: el body se hace más alto que la ventana y lo que se
    va abajo del borde es la barra de acción entera -- Acomodar, la barra de
    avance y Guardar DXF. Medido en una ventana de 558 px: el body daba 733.

    `height` fija la cáscara y deja que scrollee el panel de opciones, que
    para eso tiene `overflow-y: auto`."""
    cuerpo = css[css.index("\nbody {"):css.index("}", css.index("\nbody {"))]
    assert "height: 100vh" in cuerpo and "min-height: 100vh" not in cuerpo, (
        "el body volvió a min-height: la barra de acción se va abajo del "
        "borde de la ventana en cuanto el panel de opciones crece"
    )
    assert "min-height: 0" in css, (
        "sin min-height: 0 en el hijo de la grilla, fijar la altura del body "
        "no alcanza: el hijo tampoco baja de su contenido"
    )


@pytest.mark.parametrize("campo", ["tol-cierre", "resolucion"])
def test_los_numeros_no_nacen_invalidos(html, campo):
    """`step` se cuenta desde `min`, no desde cero. Con min=0.001 y step=0.01
    el valor por defecto 0.1 no cae en la grilla, así que el navegador marca
    el campo como inválido antes de que el usuario toque nada -- y al usar
    las flechas salta a 0.101. Lo mismo resolución: min=0.1, step=0.5, y el
    2 por defecto no es un paso válido.

    Son medidas que se escriben, no que se incrementan de a una: `any`."""
    linea = next(l for l in html.splitlines() if f'id="{campo}"' in l)
    assert 'step="any"' in linea, f"{campo} tiene un step que invalida su propio valor por defecto: {linea.strip()}"


def test_las_casillas_usan_el_acento_de_la_paleta(css):
    """Sin `accent-color` la casilla y los radios salen en el azul del
    sistema, que no es ningún color de la dirección D."""
    assert "accent-color: var(--acento)" in css


def test_el_css_se_carga_desde_el_html(html):
    assert 'href="app.css"' in html


def test_el_javascript_se_carga_desde_el_html(html):
    assert 'src="app.js"' in html
