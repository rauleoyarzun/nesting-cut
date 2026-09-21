"""El criterio de `herramientas/globos_reales.py`.

La herramienta abre la ventana de escritorio de verdad y no corre en la
suite, pero la parte que decide si algo está roto es pura y sí se puede
probar. Sin esto, una herramienta de diagnóstico que dejó de detectar nada
se ve exactamente igual que una que no encuentra problemas -- que es el modo
de falla más caro que tiene.

Los números de abajo son los que se midieron en corridas reales de la
herramienta, no inventados: el panel de opciones mide 336 px de ancho y el
globo hasta 280 (`.panel-opciones` y `.globo-info` en `app.css`); el globo de
Resolución, con el panel scrolleado del todo, terminaba en 593 px de una
ventana de 692; y en la ventana mínima de 960x640 el de Material ocupaba de
x=98 a x=378.
"""

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def herramienta():
    ruta = RAIZ / "herramientas" / "globos_reales.py"
    spec = importlib.util.spec_from_file_location("globos_reales", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def icono(clave, w=16, h=16, tipo="BUTTON", enfocable=True):
    return {
        "clave": clave, "tipo": tipo, "enfocable": enfocable,
        "caja": None if w is None else {"x": 0, "y": 0, "w": w, "h": h, "der": w, "aba": h},
    }


def iconos_sanos(claves):
    return [icono(c) for c in claves]


def estado(visible=True, texto="algo de texto", x=350, y=100, w=280, h=90,
           vw=1100, vh=720, abiertos=("sep",), describedby=("sep",)):
    der, aba = x + w, y + h
    return {
        "visible": visible,
        "texto": texto,
        "caja": {"x": x, "y": y, "w": w, "h": h, "der": der, "aba": aba},
        "abiertos": list(abiertos),
        "describedby": list(describedby),
        "vw": vw, "vh": vh,
    }


# --- problemas_de_inventario ---

def test_inventario_sano_no_tiene_nada_que_decir(herramienta):
    assert herramienta.problemas_de_inventario(iconos_sanos(herramienta.CLAVES)) == []


def test_inventario_detecta_un_icono_faltante(herramienta):
    claves = [c for c in herramienta.CLAVES if c != "borde"]
    fallas = herramienta.problemas_de_inventario(iconos_sanos(claves))
    assert any("diez esperados" in f for f in fallas)


def test_inventario_detecta_un_icono_de_otro_tamano(herramienta):
    """El síntoma real: uno de los <svg> con un viewBox distinto, o dibujado
    en otra escala, pasaría cualquier revisión de sólo existencia."""
    iconos = iconos_sanos(herramienta.CLAVES)
    iconos[3] = icono(herramienta.CLAVES[3], w=20, h=20)
    fallas = herramienta.problemas_de_inventario(iconos)
    assert any("16x16" in f for f in fallas)


def test_inventario_detecta_un_icono_sin_svg_para_medir(herramienta):
    iconos = iconos_sanos(herramienta.CLAVES)
    iconos[0] = icono(herramienta.CLAVES[0], w=None)
    fallas = herramienta.problemas_de_inventario(iconos)
    assert any("no tiene un <svg>" in f for f in fallas)


def test_inventario_detecta_un_icono_que_no_es_boton(herramienta):
    iconos = iconos_sanos(herramienta.CLAVES)
    iconos[5] = icono(herramienta.CLAVES[5], tipo="A")
    fallas = herramienta.problemas_de_inventario(iconos)
    assert any("<button>" in f for f in fallas)


def test_inventario_detecta_un_icono_que_no_se_llega_con_tab(herramienta):
    iconos = iconos_sanos(herramienta.CLAVES)
    iconos[5] = icono(herramienta.CLAVES[5], enfocable=False)
    fallas = herramienta.problemas_de_inventario(iconos)
    assert any("<button>" in f for f in fallas)


# --- problemas_de_contenido ---

def test_contenido_sano_no_tiene_nada_que_decir(herramienta):
    assert herramienta.problemas_de_contenido(estado(), "Separación") == []


def test_contenido_detecta_el_globo_invisible(herramienta):
    fallas = herramienta.problemas_de_contenido(estado(visible=False), "Separación")
    assert any("Separación" in f and ("vacío" in f or "no se ve" in f) for f in fallas)


def test_contenido_detecta_el_texto_vacio(herramienta):
    fallas = herramienta.problemas_de_contenido(estado(texto="   "), "Separación")
    assert fallas != []


# --- problemas_de_apertura ---

def test_apertura_sana_no_tiene_nada_que_decir(herramienta):
    m = estado(texto="al menos el diámetro de la fresa", x=350)
    assert herramienta.problemas_de_apertura(m, "Separación", "sep", "fresa", boton_der=326) == []


def test_apertura_detecta_el_globo_que_no_salio_a_la_derecha(herramienta):
    """Con el panel de 336 px y el globo abriéndose pegado al ícono, si
    `ubicar()` no lo movió el globo queda a la izquierda del borde derecho
    del botón en vez de a su derecha."""
    m = estado(texto="fresa", x=100)
    fallas = herramienta.problemas_de_apertura(m, "Separación", "sep", "fresa", boton_der=326)
    assert any("a la derecha" in f for f in fallas)


def test_apertura_detecta_el_texto_equivocado(herramienta):
    m = estado(texto="el margen que se deja libre contra el filo")
    fallas = herramienta.problemas_de_apertura(m, "Separación", "sep", "fresa")
    assert any("el texto no es el de Separación" in f for f in fallas)


def test_apertura_detecta_que_quedo_abierto_otro_icono(herramienta):
    m = estado(texto="fresa", abiertos=("borde",))
    fallas = herramienta.problemas_de_apertura(m, "Separación", "sep", "fresa")
    assert any("quedó abierto" in f for f in fallas)


def test_apertura_detecta_dos_globos_abiertos_a_la_vez(herramienta):
    """El bug que "otro ícono cierra al anterior" evita: si `cerrar()` no se
    llamara antes de `abrir()`, quedarían dos claves en `aria-expanded`."""
    m = estado(texto="fresa", abiertos=("sep", "borde"))
    fallas = herramienta.problemas_de_apertura(m, "Separación", "sep", "fresa")
    assert any("quedó abierto" in f for f in fallas)


def test_apertura_detecta_el_aria_describedby_sucio(herramienta):
    m = estado(texto="fresa", describedby=("borde",))
    fallas = herramienta.problemas_de_apertura(m, "Separación", "sep", "fresa")
    assert any("aria-describedby" in f for f in fallas)


# --- problemas_de_cierre ---

def test_cierre_sano_no_tiene_nada_que_decir(herramienta):
    m = estado(visible=False, texto="", abiertos=(), describedby=())
    assert herramienta.problemas_de_cierre(m, "un clic afuera") == []


def test_cierre_detecta_que_el_globo_sigue_visible(herramienta):
    m = estado(visible=True, abiertos=(), describedby=())
    fallas = herramienta.problemas_de_cierre(m, "un clic afuera")
    assert any("un clic afuera no cerró" in f for f in fallas)


def test_cierre_detecta_el_aria_expanded_que_quedo_prendido(herramienta):
    m = estado(visible=False, abiertos=("sep",), describedby=())
    fallas = herramienta.problemas_de_cierre(m, "el mismo ícono")
    assert any("aria-expanded" in f for f in fallas)


def test_cierre_detecta_el_aria_describedby_que_no_se_limpio(herramienta):
    m = estado(visible=False, abiertos=(), describedby=("sep",))
    fallas = herramienta.problemas_de_cierre(m, "el mismo ícono")
    assert any("aria-describedby" in f for f in fallas)


# --- problemas_de_escape ---

def test_escape_sano_no_tiene_nada_que_decir(herramienta):
    m = estado(visible=False, abiertos=(), describedby=())
    assert herramienta.problemas_de_escape(m, foco_antes=True, foco_volvio=True) == []


def test_escape_detecta_que_no_hubo_foco_previo(herramienta):
    """Sin esto la revisión podría "pasar" sin haber probado nada: si el
    ícono nunca tuvo el foco, que el foco "vuelva" no dice nada."""
    m = estado(visible=False, abiertos=(), describedby=())
    fallas = herramienta.problemas_de_escape(m, foco_antes=False, foco_volvio=True)
    assert any("no probó nada" in f for f in fallas)


def test_escape_detecta_que_el_foco_no_volvio(herramienta):
    m = estado(visible=False, abiertos=(), describedby=())
    fallas = herramienta.problemas_de_escape(m, foco_antes=True, foco_volvio=False)
    assert any("foco no volvió" in f for f in fallas)


def test_escape_tambien_detecta_que_no_cerro(herramienta):
    m = estado(visible=True, abiertos=("esfuerzo",), describedby=("esfuerzo",))
    fallas = herramienta.problemas_de_escape(m, foco_antes=True, foco_volvio=True)
    assert any("no cerró" in f for f in fallas)


# --- problemas_de_encuadre ---

def test_encuadre_sano_no_tiene_nada_que_decir(herramienta):
    """El de Resolución, medido de verdad: con el panel scrolleado del todo
    terminaba en 593 px de una ventana de 692."""
    caja = {"x": 350, "y": 503, "w": 280, "h": 90, "der": 630, "aba": 593}
    assert herramienta.problemas_de_encuadre(caja, vw=980, vh=692, etiqueta="Resolución") == []


def test_encuadre_sano_material_en_la_ventana_minima(herramienta):
    """Medido de verdad en la ventana mínima de 960x640: el globo de
    Material iba de x=98 a x=378."""
    caja = {"x": 98, "y": 120, "w": 280, "h": 90, "der": 378, "aba": 210}
    assert herramienta.problemas_de_encuadre(caja, vw=960, vh=640, etiqueta="Material") == []


def test_encuadre_detecta_el_recorte_contra_el_borde_inferior(herramienta):
    """Lo que pasaba antes de que `ubicar()` lo corrigiera: el globo de
    Resolución, con el panel scrolleado del todo, se salía por abajo."""
    caja = {"x": 350, "y": 650, "w": 280, "h": 90, "der": 630, "aba": 740}
    fallas = herramienta.problemas_de_encuadre(caja, vw=980, vh=692, etiqueta="Resolución")
    assert any("se sale por abajo" in f for f in fallas)


def test_encuadre_detecta_el_recorte_contra_el_borde_derecho(herramienta):
    """Lo que pasaba en la ventana mínima antes de la corrección: el globo
    de Material se salía por la derecha."""
    caja = {"x": 700, "y": 120, "w": 280, "h": 90, "der": 980, "aba": 210}
    fallas = herramienta.problemas_de_encuadre(caja, vw=960, vh=640, etiqueta="Material")
    assert any("se sale por la derecha" in f for f in fallas)


def test_encuadre_detecta_el_recorte_contra_la_izquierda(herramienta):
    caja = {"x": -20, "y": 120, "w": 280, "h": 90, "der": 260, "aba": 210}
    fallas = herramienta.problemas_de_encuadre(caja, vw=960, vh=640, etiqueta="Archivo")
    assert any("se sale por la izquierda" in f for f in fallas)


def test_encuadre_detecta_el_recorte_contra_arriba(herramienta):
    caja = {"x": 100, "y": -10, "w": 280, "h": 90, "der": 380, "aba": 80}
    fallas = herramienta.problemas_de_encuadre(caja, vw=960, vh=640, etiqueta="Archivo")
    assert any("se sale por arriba" in f for f in fallas)


# --- problemas_de_casilla ---

def test_casilla_sana_no_tiene_nada_que_decir(herramienta):
    assert herramienta.problemas_de_casilla({"antes": True, "despues": True}) == []


def test_casilla_detecta_que_el_icono_la_dio_vuelta(herramienta):
    fallas = herramienta.problemas_de_casilla({"antes": True, "despues": False})
    assert any("dio vuelta la casilla" in f for f in fallas)
