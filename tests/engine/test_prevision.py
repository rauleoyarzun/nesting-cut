"""Cuántas consultas va a costar un acomodo: la aritmética, sin motor."""

import pytest

from nesting.engine.prevision import (
    TYPICAL_UTILIZATION,
    estimate_sheets,
    forecast_compaction,
    forecast_greedy_pass,
    forecast_pack,
    forecast_recovery,
)

UTIL = 1_000_000.0
"""Área útil de una placa de 1000 x 1000 sin margen."""


def test_el_aprovechamiento_tipico_es_el_de_la_spec():
    assert TYPICAL_UTILIZATION == 0.4


def test_lo_que_entra_en_el_aprovechamiento_tipico_es_una_placa():
    assert estimate_sheets(300_000.0, (), UTIL) == 1


def test_pasarse_del_aprovechamiento_tipico_abre_otra_placa():
    assert estimate_sheets(500_000.0, (), UTIL) == 2


def test_sin_piezas_igual_se_prevé_una_placa():
    """`forecast_greedy_pass` divide por la cantidad de placas: cero no
    puede salir nunca de acá."""
    assert estimate_sheets(0.0, (), UTIL) == 1


def test_los_recortes_cuentan_como_placas_antes_que_la_del_material():
    # El recorte de 500x500 útil absorbe 0.25e6 * 0.4 = 0.1e6; quedan
    # 0.35e6, que en placas del material son una más.
    assert estimate_sheets(450_000.0, (250_000.0,), UTIL) == 2


def test_un_recorte_que_alcanza_no_abre_placa_del_material():
    assert estimate_sheets(50_000.0, (250_000.0, 250_000.0), UTIL) == 1


def test_un_recorte_sin_area_util_no_resta_nada():
    """Un margen más grande que el recorte deja área útil negativa. Restarla
    haría que el recorte AGREGARA trabajo pendiente."""
    assert estimate_sheets(300_000.0, (-10_000.0,), UTIL) == 2


def test_una_placa_del_material_sin_area_util_no_divide_por_cero():
    assert estimate_sheets(300_000.0, (), 0.0) == 1


def test_una_placa_es_piezas_por_orientaciones():
    assert forecast_greedy_pass(10, 4, 1) == 40


def test_las_pendientes_se_vuelven_a_consultar_en_la_placa_siguiente():
    # Placa 1: las 10. Placa 2: la mitad que se estima que quedó.
    assert forecast_greedy_pass(10, 4, 2) == (10 + 5) * 4


def test_las_pendientes_se_redondean_para_arriba():
    # 10, ceil(20/3) = 7, ceil(10/3) = 4.
    assert forecast_greedy_pass(10, 4, 3) == (10 + 7 + 4) * 4


def test_sin_placas_anteriores_la_recuperacion_no_consulta():
    assert forecast_recovery([], 5) == 0


def test_la_recuperacion_paga_un_reempaque_y_un_derrame_por_placa_anterior():
    """Cada intento es un `_pack_once` con la placa anterior y las
    pendientes adelante: todas se consultan en la placa, y las que no
    entran se vuelven a consultar en la placa de derrame."""
    assert forecast_recovery([(6, 4)], 3) == (6 + 3) * 4 + 3 * 4


def test_la_recuperacion_usa_las_orientaciones_de_cada_placa():
    """Un recorte con la veta cruzada puede permitir otras orientaciones que
    la placa del material."""
    assert forecast_recovery([(6, 4), (2, 8)], 1) == (7 * 4 + 4) + (3 * 8 + 8)


def test_compactar_una_sola_pieza_no_consulta():
    """`_compact_last_sheet` sale antes con menos de dos piezas."""
    assert forecast_compaction(1, 4) == 0
    assert forecast_compaction(0, 4) == 0


def test_compactar_es_una_pasada_sobre_la_ultima_placa():
    assert forecast_compaction(3, 4) == 12


def test_la_prevision_de_arranque_suma_las_tres_fases():
    # Por pasada: (10 + 5) * 4 = 60, por 3 intentos = 180.
    # Recuperación: una placa anterior con 5, 5 en la última: (5+5)*4 + 5*4 = 60.
    # Compactación: 5 * 4 = 20.
    assert forecast_pack(10, 4, 2, 3) == 180 + 60 + 20


def test_una_placa_no_tiene_recuperacion():
    assert forecast_pack(10, 8, 1, 3) == 3 * 80 + 0 + 80


@pytest.mark.parametrize("sheets", [0, -1])
def test_la_prevision_de_arranque_no_divide_por_cero(sheets):
    assert forecast_pack(10, 4, sheets, 1) == forecast_pack(10, 4, 1, 1)
