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
    "angulos", "tol-cierre", "resolucion", "espejo", "globo-info",
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


def test_el_catalogo_se_abre_desde_el_campo_material(html):
    """Arriba a la derecha, separado de todo, nadie lo encuentra: lo reportó
    el usuario. El momento en que a alguien le falta un material es el
    momento en que está eligiendo uno del selector, así que el botón va ahí.

    Que esté adentro de la pantalla principal además es lo que hace que se
    apague solo al entrar al catálogo, sin una línea que lo oculte aparte."""
    principal = html[html.index('<main id="pantalla-principal"'):html.index("</main>")]
    select = principal.index('<select id="material"')
    campo = principal[principal.rfind('<div class="campo">', 0, select):select]
    assert 'id="btn-materiales"' in campo, (
        "el botón del catálogo se fue del campo Material"
    )


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


@pytest.mark.parametrize("id_", [
    "controles-zoom", "btn-acercar", "btn-alejar", "btn-ajustar", "nivel-zoom",
])
def test_la_revision_tiene_con_que_acercarse(html, id_):
    """El diagnóstico se dibuja a 1800 px de ancho y el panel mide menos de
    300: al 20% que entra, las medidas de cada descarte son ilegibles justo
    cuando hay muchos -- 59 en el archivo que lo reportó."""
    assert f'id="{id_}"' in html


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


def _reglas(css):
    """(selector, cuerpo) por cada regla. Alcanza: este CSS no anida."""
    sin_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", sin_comentarios)
    ]


@pytest.mark.parametrize("selector,fila", [
    (".barra-superior", "1"), ("#pantalla-principal", "2"), (".barra-accion", "3"),
])
def test_cada_franja_esta_clavada_a_su_fila(css, selector, fila):
    """Sin `grid-row` explícito, la fila que le toca a cada hijo depende de
    cuántos hermanos estén en `display: none` -- y la pantalla de materiales
    oculta justamente al del medio. Medido en la ventana real: con materiales
    abierto, `.barra-accion` se corría a la fila `1fr` y pasaba de 76 px de
    alto a 636. Queda tapada, así que no se ve; el problema aparece al
    volver, porque WKWebView no re-ubica y la pantalla principal queda en
    0 px hasta que un resize fuerza el recálculo. Lo reportó el usuario."""
    assert re.search(rf"{re.escape(selector)}\s*\{{\s*grid-row:\s*{fila}\s*;", css), (
        f"{selector} ya no está clavado a la fila {fila}"
    )


def test_la_grilla_no_se_estira_con_su_contenido(css):
    """Una pista implícita es `auto`, y `auto` crece hasta el max-content de
    lo que tiene adentro. Con la revisión ampliada al 100% eso son 1800 px:
    en vez de recortar y dejar scrollear el lienzo, la columna se estiraba y
    se llevaba puesta la ventana entera."""
    cuerpo = css[css.index("\nbody {"):css.index("}", css.index("\nbody {"))]
    assert "grid-template-columns: minmax(0, 1fr)" in cuerpo


def test_ninguna_regla_le_saca_el_marco_a_un_select(css):
    """El `<input>` va envuelto en un `.control` que le dibuja el marco, así
    que el input se dibuja sin borde ni fondo propios. Un `<select>` NO va
    envuelto: él mismo es el marco.

    Mientras `select.control` estuvo en las dos reglas -- la que da el marco
    y la que lo saca -- ganaba la última, que tiene la misma especificidad, y
    Material y Esfuerzo quedaban dibujados como texto suelto: nada indicaba
    que se pudieran abrir. El usuario lo reportó así."""
    for selector, cuerpo in _reglas(css):
        if "select" not in selector:
            continue
        for despojo in ("border: 0", "border:0", "border: none", "background: none"):
            assert despojo not in cuerpo, (
                f"la regla `{selector}` le saca el marco a un select; sin marco "
                "no se distingue de un texto y nadie adivina que se abre"
            )


def test_cada_select_esta_dibujado_como_desplegable(html):
    """`appearance: none` borra la flecha que dibuja el sistema. Sin un
    reemplazo, el control queda idéntico a un campo de texto -- que es peor
    que no haber tocado nada, porque ahí al menos había una flecha."""
    selects = re.findall(r"<select\b", html)
    flechas = re.findall(r'class="icono flecha"', html)
    assert len(selects) == len(flechas) > 0, (
        f"hay {len(selects)} select y {len(flechas)} flechas: alguno quedó "
        "sin ninguna señal de que se despliega"
    )


def test_la_flecha_no_se_come_el_click(css):
    """Está dibujada encima del select, no al lado. Sin `pointer-events:
    none` el click sobre la flecha -- justo donde uno apunta para abrir un
    desplegable -- cae en el div y no abre nada."""
    flecha = next(c for sel, c in _reglas(css) if ".flecha" in sel and "position" in c)
    assert "pointer-events: none" in flecha


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


def test_la_pagina_no_le_pide_nada_a_ningun_servidor_de_afuera(html):
    """La tipografía venía de fonts.googleapis.com, o sea que cada vez que
    alguien abría el programa su IP y su user-agent viajaban a un servidor de
    Google sin que nadie le avisara -- en una herramienta de taller que por lo
    demás no habla con nadie. Y sin internet no cargaba.

    Lo notó una revisión de seguridad. Ahora la fuente la sirve el programa.
    """
    externos = re.findall(r'(?:href|src)="(https?://[^"]+)"', html)
    assert externos == [], f"la página carga cosas de afuera: {externos}"


def test_la_fuente_viaja_con_el_programa(css):
    ruta = rutas.recurso("web") / "fuentes"
    hoja = ruta / "plus-jakarta-sans.css"
    assert hoja.is_file()

    declarados = re.findall(r"url\(([^)]+\.woff2)\)", hoja.read_text(encoding="utf-8"))
    assert declarados, "la hoja de la fuente no declara ningún archivo"
    for nombre in declarados:
        assert not nombre.startswith("http"), f"{nombre} sigue apuntando afuera"
        assert (ruta / nombre).is_file(), f"falta {nombre}"

    # Los pesos que la interfaz usa de verdad, no los que vinieron de regalo.
    usados = {int(p) for p in re.findall(r"font-weight:\s*(\d+)", css)}
    disponibles = {int(p) for p in re.findall(r"-(\d+)-latin\.woff2", " ".join(declarados))}
    assert usados <= disponibles, f"faltan pesos: {sorted(usados - disponibles)}"


def test_viaja_la_licencia_de_la_fuente():
    """Plus Jakarta Sans es SIL Open Font License: se puede redistribuir, y
    la licencia exige que el aviso de copyright viaje con ella."""
    licencia = rutas.recurso("web") / "fuentes" / "LICENSE-fuente.txt"
    assert licencia.is_file()
    texto = licencia.read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in texto.upper()
    assert "Copyright" in texto


# --- los globos de ayuda ---------------------------------------------------

CLAVES_CON_GLOBO = [
    "archivo", "material", "sep", "borde", "copias", "esfuerzo",
    "angulos", "tol-cierre", "resolucion", "espejo",
]


@pytest.mark.parametrize("clave", CLAVES_CON_GLOBO)
def test_cada_opcion_tiene_su_boton_de_ayuda(html, clave):
    assert f'data-info="{clave}"' in html


@pytest.mark.parametrize("clave", CLAVES_CON_GLOBO)
def test_el_boton_de_ayuda_es_un_boton_y_se_anuncia(html, clave):
    """Adentro sólo hay un SVG con `aria-hidden`: sin `aria-label` un lector
    de pantalla anuncia un botón sin nombre. Y un `<span>` con onclick no
    recibe foco con Tab ni se activa con Enter."""
    etiqueta = re.search(rf'<button[^>]*data-info="{re.escape(clave)}"[^>]*>', html)
    assert etiqueta, f"el botón de {clave} no es un <button>"
    assert "aria-label=" in etiqueta.group(0), f"el botón de {clave} no tiene aria-label"
    assert 'aria-expanded="false"' in etiqueta.group(0), (
        f"el botón de {clave} arranca sin aria-expanded"
    )


def test_el_boton_de_espejadas_esta_afuera_de_su_casilla(html):
    """Un `<button>` adentro de un `<label>` hereda su clic: abrir la ayuda
    daría vuelta la casilla, que es justo lo contrario de lo que el usuario
    pidió al apretarla."""
    inicio = html.index('<label class="casilla">')
    cierre = html.index("</label>", inicio)
    assert 'data-info="espejo"' not in html[inicio:cierre], (
        "el botón de ayuda de las espejadas quedó adentro del <label>"
    )


def test_el_globo_se_dibuja_abajo_de_los_carteles(html):
    """`app.css` no usa `z-index` en ninguna regla: entre posicionados
    manda el orden del documento. Con el globo después de los carteles, uno
    abierto quedaría flotando por encima del cartel de error."""
    assert html.index('id="globo-info"') < html.index('id="cartel-unidades"')


def test_el_globo_no_atrapa_el_foco(html):
    """Es un texto de ayuda, no un diálogo: `role="tooltip"` y nada más."""
    globo = re.search(r'<div[^>]*id="globo-info"[^>]*>', html).group(0)
    assert 'role="tooltip"' in globo
