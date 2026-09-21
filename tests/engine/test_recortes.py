"""Qué pasa cuando el plan de placas tiene recortes adelante."""

import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    PartTooLargeError,
    CostoLayout,
    layout_cost,
    pack,
)
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply

CONFIG = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=False,
                    effort="rapido")

STOCK = Sheet(2000.0, 2000.0, grain_tolerance=180.0)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def recorte(w, h, **extra):
    return Sheet(w, h, grain_tolerance=180.0, scrap=True, **extra)


def test_el_recorte_se_llena_antes_que_la_placa_del_material():
    plan = SheetSupply(stock=STOCK, scraps=(recorte(500.0, 500.0),))
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert result.sheets[0].scrap is True


def test_un_recorte_donde_no_entra_nada_desaparece_del_resultado():
    """No es un error: un pedazo de 100x100 simplemente no sirve para esta
    pieza. Tiene que saltearse, no aparecer como una placa al 0%."""
    plan = SheetSupply(stock=STOCK, scraps=(recorte(100.0, 100.0),))
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert result.sheets[0].scrap is False
    assert len(result.utilization) == 1
    assert all(p.sheet == 0 for p in result.placements)


def test_se_saltean_varios_recortes_seguidos_sin_perder_la_cuenta():
    plan = SheetSupply(
        stock=STOCK,
        scraps=(recorte(100.0, 100.0), recorte(120.0, 90.0), recorte(500.0, 500.0)),
    )
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert (result.sheets[0].width, result.sheets[0].height) == (500.0, 500.0)
    assert result.placements[0].sheet == 0


def test_una_pieza_que_no_entra_en_ninguna_placa_sigue_siendo_error_duro():
    plan = SheetSupply(
        stock=STOCK, scraps=(recorte(100.0, 100.0),), material_name="mdf18"
    )
    piezas = [rect_part(0, 5000.0, 5000.0)]

    with pytest.raises(PartTooLargeError) as capturado:
        pack(piezas, plan, CONFIG, ShelfOracle)

    # Nombra la placa del Material, no el recorte de 100x100 que se salteó.
    assert "mdf18" in str(capturado.value)
    assert "1960.0 x 1960.0" in str(capturado.value)


def test_el_costo_no_cuenta_los_recortes():
    plan = SheetSupply(stock=STOCK, scraps=(recorte(500.0, 500.0),))
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert layout_cost(result, piezas).placas_nuevas == 0


def test_llenar_un_recorte_cuesta_menos_que_abrir_una_placa_nueva():
    """La decisión de diseño entera, en un assert: si esto se invierte, el
    motor va a preferir saltearse los recortes."""
    piezas = [rect_part(0, 400.0, 400.0)]

    con_recorte = pack(
        piezas, SheetSupply(stock=STOCK, scraps=(recorte(500.0, 500.0),)),
        CONFIG, ShelfOracle,
    )
    sin_recorte = pack(piezas, SheetSupply(stock=STOCK), CONFIG, ShelfOracle)

    assert layout_cost(con_recorte, piezas) < layout_cost(sin_recorte, piezas)


def test_el_aprovechamiento_de_un_recorte_se_mide_contra_su_area():
    plan = SheetSupply(stock=STOCK, scraps=(recorte(500.0, 500.0),))
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert result.utilization[0] == pytest.approx(160_000.0 / 250_000.0)


def test_una_placa_del_material_vacia_no_se_saltea_nunca():
    plan = SheetSupply(stock=Sheet(100.0, 100.0, grain_tolerance=180.0))
    piezas = [rect_part(0, 400.0, 400.0)]

    with pytest.raises(PartTooLargeError):
        pack(piezas, plan, CONFIG, ShelfOracle)


def test_un_recorte_usado_como_placa_infinita_no_cicla():
    """La guarda mira la posición en el plan, no `hoja.scrap`.

    `_recuperar_de_la_ultima_placa` y `_compact_last_sheet` arman
    `SheetSupply(stock=<una placa del resultado>)`, y esa placa puede ser un
    recorte. Ahí `supply.sheet(i)` devuelve el MISMO recorte para siempre:
    una guarda que saltee por `hoja.scrap` no llega nunca a una placa
    distinta y gira sin fin.

    OJO AL CORRERLO: con la guarda equivocada este test NO falla, CUELGA.
    Corralo con `timeout 60 .venv/bin/pytest ...` -- que se agote el tiempo
    es el resultado esperado antes del arreglo, y es información, no un
    problema del test.
    """
    plan = SheetSupply(stock=recorte(100.0, 100.0))
    piezas = [rect_part(0, 400.0, 400.0)]

    with pytest.raises(PartTooLargeError):
        pack(piezas, plan, CONFIG, ShelfOracle)


def test_sin_recortes_placas_nuevas_es_la_cantidad_de_placas():
    piezas = [rect_part(i, 900.0, 900.0) for i in range(6)]
    result = pack(piezas, SheetSupply(stock=STOCK), CONFIG, ShelfOracle)

    assert layout_cost(result, piezas).placas_nuevas == result.sheets_used


def test_el_costo_se_compara_campo_por_campo_en_orden():
    assert CostoLayout(0, 999.0, 999.0) < CostoLayout(1, 0.0, 0.0)
    assert CostoLayout(1, 10.0, 999.0) < CostoLayout(1, 20.0, 0.0)
    assert CostoLayout(1, 10.0, 5.0) < CostoLayout(1, 10.0, 6.0)


def test_la_recuperacion_no_acepta_un_layout_mas_caro():
    """La versión vieja aceptaba su resultado sin compararlo, apoyada en que
    vaciar la última placa baja el conteo de placas. Con `placas_nuevas` eso
    dejó de valer: vaciar un RECORTE no baja nada, y la "última placa" pasa
    a ser otra con más material arriba. La guarda es lo único que lo atrapa.
    """
    from nesting.engine.packer import PackResult, _recuperar_de_la_ultima_placa
    from nesting.model.entities import Transform
    from nesting.model.part import Placement

    grande = rect_part(0, 900.0, 900.0)
    chica = rect_part(1, 100.0, 100.0)
    nueva = Sheet(2000.0, 2000.0, grain_tolerance=180.0)
    sobra = recorte(500.0, 500.0)

    entrada = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 20.0, 20.0)),
            Placement(1, 1, Transform(0.0, False, 20.0, 20.0)),
        ],
        sheets_used=2,
        sheets=[nueva, sobra],
        utilization=[810_000.0 / nueva.area, 10_000.0 / sobra.area],
    )

    salida = _recuperar_de_la_ultima_placa(
        entrada, [grande, chica], CONFIG, ShelfOracle, None
    )

    assert layout_cost(salida, [grande, chica]) <= layout_cost(
        entrada, [grande, chica]
    )
