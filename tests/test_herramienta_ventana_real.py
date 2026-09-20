"""El criterio de `herramientas/ventana_real.py`.

La herramienta abre una ventana y no corre en la suite, pero la parte que
decide si algo está roto es aritmética pura y sí se puede probar. Sin esto,
una herramienta de diagnóstico que dejó de detectar nada se ve igual que una
que no encuentra problemas -- que es el modo de falla más caro que tiene.

Los números de abajo no son inventados: son los que midió la herramienta en
la ventana real, antes y después de cada arreglo.
"""

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def herramienta():
    ruta = RAIZ / "herramientas" / "ventana_real.py"
    spec = importlib.util.spec_from_file_location("ventana_real", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def medida(vh=872, vw=980, body_h=872, body_w=980, principal_h=740,
           barra_top=796, barra_h=76, principal_visible=True):
    return {
        "vh": vh, "vw": vw,
        "body": {"top": 0, "h": body_h, "w": body_w},
        "principal": {"top": 56, "h": principal_h, "w": vw},
        "barra": {"top": barra_top, "h": barra_h, "w": vw},
        "principal_visible": principal_visible,
    }


def test_una_ventana_sana_no_tiene_nada_que_decir(herramienta):
    assert herramienta.problemas_de_medida("sana", medida()) == []


def test_la_pantalla_de_materiales_oculta_no_es_un_problema(herramienta):
    """Ahí `#pantalla-principal` está en display:none y mide 0 de alto. Es lo
    esperado, no el bug: el bug es medir 0 estando visible."""
    fallas = herramienta.problemas_de_medida(
        "en materiales", medida(principal_h=0, principal_visible=False)
    )
    assert fallas == []


def test_detecta_la_pantalla_principal_aplastada(herramienta):
    """Lo que reportó el usuario: volver de materiales después de
    redimensionar dejaba la principal en 0 px y el pie estirado ocupándolo
    todo. Números reales de esa corrida."""
    fallas = herramienta.problemas_de_medida(
        "de vuelta", medida(principal_h=0, barra_top=56, barra_h=816)
    )
    assert any("pantalla principal" in f for f in fallas)
    assert any("fila elástica" in f for f in fallas)


def test_detecta_la_barra_que_no_llega_al_borde(herramienta):
    """El síntoma de `min-height: 100vh`: el body se hacía más alto que la
    ventana y la barra de acción quedaba abajo del borde."""
    fallas = herramienta.problemas_de_medida(
        "desbordada", medida(vh=558, body_h=733, barra_top=657)
    )
    assert any("termina en" in f for f in fallas)
    assert any("el body mide 733" in f for f in fallas)


def test_detecta_la_columna_estirada_por_la_revision_ampliada(herramienta):
    """Una pista implícita de grilla es `auto` y crece hasta el contenido:
    con la revisión al 100% la columna se iba a 1800 px y se llevaba puesta
    la ventana."""
    fallas = herramienta.problemas_de_medida("ampliada", medida(body_w=2168))
    assert any("de ancho" in f for f in fallas)


def test_el_alto_tolerado_de_la_barra_deja_lugar_a_un_renglon_mas(herramienta):
    """76 px es lo que mide. El margen es para que un salto de línea en el
    texto del resultado no dispare una falsa alarma, y tiene que quedar muy
    lejos de los 636 px que medía rota."""
    assert 76 < herramienta.ALTO_ESPERADO_DE_LA_BARRA < 636
