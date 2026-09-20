"""El ícono: que exista, que tenga los tamaños que cada sistema pide, y que
el empaquetado lo encuentre.

Un ícono roto o incompleto no rompe ningún test normal: se ve recién cuando
alguien mira la barra de tareas, y ahí ya está entregado.
"""

import importlib.util
from pathlib import Path

import pytest
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
ICO = RAIZ / "packaging" / "icono.ico"


@pytest.fixture(scope="module")
def generador():
    ruta = RAIZ / "herramientas" / "icono.py"
    spec = importlib.util.spec_from_file_location("icono", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_el_ico_trae_los_seis_tamanos(generador):
    """Windows saca uno distinto según el contexto: escritorio, barra de
    tareas, Alt-Tab. Con uno solo adentro reescala, y reescalar un ícono se
    nota."""
    with Image.open(ICO) as im:
        adentro = {lado for lado, _ in im.ico.sizes()}
    assert adentro == set(generador.TAMANOS_ICO)


def test_los_tamanos_chicos_usan_el_dibujo_simplificado(generador, monkeypatch):
    """A 16 y 32 px las cinco piezas de la versión grande quedan en bloques
    de dos o tres píxeles separados por ranuras de menos de uno: puré. Por
    eso hay un segundo dibujo, de tres piezas.

    La primera versión de este test comparaba el render chico contra el
    grande reescalado, y PASABA IGUAL con la bifurcación desactivada: el
    remuestreo por sí solo ya da píxeles distintos. Se verifica la decisión
    directamente, y aparte que esa decisión llegue al dibujo."""
    for lado in (16, 32, 48):
        assert generador.composicion(lado) is generador.SIMPLE
    for lado in (128, 256, 1024):
        assert generador.composicion(lado) is generador.DETALLADO

    con_bifurcacion = generador.dibujar(32)
    monkeypatch.setattr(generador, "UMBRAL_SIMPLE", 0)
    sin_bifurcacion = generador.dibujar(32)
    assert list(con_bifurcacion.getdata()) != list(sin_bifurcacion.getdata()), (
        "la elección de composición no llega al dibujo"
    )


def test_el_umbral_deja_los_chicos_de_un_lado_y_los_grandes_del_otro(generador):
    assert generador.SIMPLE is not generador.DETALLADO
    assert len(generador.SIMPLE) < len(generador.DETALLADO)
    assert 32 <= generador.UMBRAL_SIMPLE < 128


def test_el_icono_no_es_transparente_en_el_medio(generador):
    """El fondo redondeado es parte del ícono. Sin él quedan formas sueltas
    flotando sobre lo que haya atrás."""
    im = generador.dibujar(256).convert("RGBA")
    assert im.getpixel((128, 128))[3] == 255
    assert im.getpixel((2, 2))[3] == 0, "las esquinas tienen que estar redondeadas"


def test_el_spec_declara_el_icono():
    """Sin `icon=` el .exe sale con el ícono por defecto de PyInstaller, y
    eso no falla en ningún lado: se ve al entregarlo."""
    spec = (RAIZ / "packaging" / "nesting.spec").read_text(encoding="utf-8")
    assert "icon=ICONO" in spec
    assert 'icono.ico" if sys.platform == "win32"' in spec


def test_estan_los_dos_archivos_que_pide_cada_plataforma():
    assert ICO.is_file()
    assert (RAIZ / "packaging" / "icono.icns").is_file()


def test_la_pagina_declara_su_favicon():
    html = (RAIZ / "src" / "nesting_app" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'rel="icon"' in html and "icono.png" in html
    assert (RAIZ / "src" / "nesting_app" / "web" / "icono.png").is_file()
