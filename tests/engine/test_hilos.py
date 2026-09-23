"""Las orientaciones en hilos dan exactamente el mismo layout."""

import pytest

from nesting.engine import packer
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import _pack_once
from nesting.engine.raster.oracle import RasterOracleFactory
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply


@pytest.mark.parametrize("ranks", [None, {1: 2, 4: 1, 7: 5}], ids=["mejor", "con_rangos"])
def test_uno_o_cuatro_hilos_dan_el_mismo_layout(monkeypatch, ranks):
    piezas = [Part(i, ((0, 0), (300 + 7 * i, 0), (300, 90 + 5 * i), (0, 120)), (), (i,))
              for i in range(10)]
    plan = SheetSupply(stock=Sheet(1000.0, 1000.0, grain_tolerance=180.0))
    config = NestConfig(sep=5.0, margin=10.0, resolution=4.0, effort="rapido")

    monkeypatch.setattr(packer, "QUERY_THREADS", 1)
    monkeypatch.setattr(packer, "_query_pool", None)
    uno = _pack_once(piezas, plan, config, RasterOracleFactory(), orientation_ranks=ranks)
    monkeypatch.setattr(packer, "QUERY_THREADS", 4)
    monkeypatch.setattr(packer, "_query_pool", None)
    cuatro = _pack_once(piezas, plan, config, RasterOracleFactory(), orientation_ranks=ranks)

    assert uno.placements
    assert uno.placements == cuatro.placements
