"""El árbitro exacto: la última palabra sobre si una pieza entra.

La grilla de raster sobre-representa cada pieza a propósito (ver
`raster/masks.py`), así que no puede contestar esta pregunta sin regalar
milímetros. Este módulo la contesta sobre los polígonos exactos.
"""

import pytest

from nesting.engine.exact import ArbitroExacto
from nesting.model.part import Part


def cuadrado(lado: float, part_id: int = 0) -> Part:
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)),
        holes=(),
        entity_ids=(),
    )


def test_una_pieza_sola_entra_si_respeta_el_borde():
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    assert arbitro.entra(cuadrado(100.0), 0.0, False, 10.0, 10.0)


def test_una_pieza_pisada_contra_el_borde_no_entra():
    """El borde es material perdido, no negociable: 9.9 mm no son 10."""
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    assert not arbitro.entra(cuadrado(100.0), 0.0, False, 9.9, 10.0)


def test_la_separacion_se_mide_exacta_ni_un_pelo_menos():
    """A exactamente `sep` entra; un décimo de milímetro menos, no.

    Es la razón de existir del módulo: la grilla a 2 mm/px contesta que no
    entra hasta los 16 mm.
    """
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    arbitro.agregar(cuadrado(100.0, part_id=0), 0.0, False, 10.0, 10.0)
    # La primera ocupa x de 10 a 110. A x=120 quedan exactamente 10 mm.
    assert arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 120.0, 10.0)
    assert not arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 119.9, 10.0)


def test_una_pieza_que_se_sale_por_arriba_no_entra():
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    assert not arbitro.entra(cuadrado(100.0), 0.0, False, 10.0, 895.0)


def test_limpiar_olvida_todo_lo_colocado():
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    arbitro.agregar(cuadrado(100.0, part_id=0), 0.0, False, 10.0, 10.0)
    assert not arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 115.0, 10.0)
    arbitro.limpiar()
    assert arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 115.0, 10.0)


def test_una_pieza_puede_entrar_en_el_agujero_de_otra():
    """Es el caso 'with concave': el hueco interno de una pieza es espacio
    libre real, no material."""
    anillo = Part(
        id=0,
        outer=((0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)),
        holes=((((50.0, 50.0), (350.0, 50.0), (350.0, 350.0), (50.0, 350.0))),),
        entity_ids=(),
    )
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    arbitro.agregar(anillo, 0.0, False, 10.0, 10.0)
    # El agujero va de 60 a 360 en la placa. Un cuadrado de 100 centrado adentro
    # queda a 90 mm de cada pared: entra con holgura.
    assert arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 170.0, 170.0)
