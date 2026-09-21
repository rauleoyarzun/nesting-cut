from nesting.model.material import Material
from nesting.model.sheet import Sheet, SheetSupply, allowed_angles

LIBRE = Sheet(1000.0, 2000.0, grain_tolerance=180.0)
CON_VETA = Sheet(1000.0, 2000.0, grain_tolerance=5.0)
CRUZADA = Sheet(1000.0, 2000.0, grain_tolerance=5.0, cross_grain=True)


def test_el_area_es_ancho_por_alto():
    assert Sheet(600.0, 800.0, grain_tolerance=180.0).area == 480_000.0


def test_una_placa_sin_veta_permite_todos_los_angulos():
    assert allowed_angles(LIBRE, (0.0, 45.0, 90.0, 135.0)) == [0.0, 45.0, 90.0, 135.0]


def test_una_placa_con_veta_solo_permite_el_eje_largo():
    assert allowed_angles(CON_VETA, (0.0, 90.0, 180.0, 270.0)) == [0.0, 180.0]


def test_la_veta_cruzada_rota_el_eje_noventa_grados():
    """Es la razón de ser de la casilla: el mismo pedazo, girado, permite
    justo los ángulos que antes prohibía."""
    assert allowed_angles(CRUZADA, (0.0, 90.0, 180.0, 270.0)) == [90.0, 270.0]


def test_la_veta_cruzada_no_cambia_nada_en_una_placa_libre():
    cruzada_libre = Sheet(1000.0, 2000.0, grain_tolerance=180.0, cross_grain=True)
    angulos = (0.0, 45.0, 90.0, 135.0)
    assert allowed_angles(cruzada_libre, angulos) == list(angulos)


def test_el_plan_devuelve_los_recortes_y_despues_siempre_la_del_material():
    a = Sheet(600.0, 800.0, grain_tolerance=180.0, scrap=True)
    b = Sheet(450.0, 1200.0, grain_tolerance=180.0, scrap=True)
    stock = Sheet(1830.0, 2600.0, grain_tolerance=180.0)
    plan = SheetSupply(stock=stock, scraps=(a, b))

    assert plan.sheet(0) is a
    assert plan.sheet(1) is b
    assert plan.sheet(2) is stock
    assert plan.sheet(99) is stock


def test_un_plan_sin_recortes_es_siempre_la_placa_del_material():
    stock = Sheet(1830.0, 2600.0, grain_tolerance=180.0)
    plan = SheetSupply(stock=stock)
    assert plan.sheet(0) is stock is plan.sheet(7)


def test_la_placa_del_material_no_es_un_recorte_y_no_esta_cruzada():
    hoja = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0).stock_sheet()
    assert (hoja.width, hoja.height, hoja.grain_tolerance) == (1830.0, 2600.0, 180.0)
    assert hoja.scrap is False
    assert hoja.cross_grain is False
