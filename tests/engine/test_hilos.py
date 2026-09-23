"""Las orientaciones en hilos: el mismo layout, y sólo en el proceso principal."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor

import pytest

from nesting.engine import cartera, packer
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import _pack_once
from nesting.engine.raster.oracle import RasterOracleFactory
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply


@pytest.fixture(autouse=True)
def sin_pools_colgados():
    """Cada test arranca y termina sin pool de consultas vivo."""
    packer.shutdown_query_pool()
    yield
    packer.allow_query_threads(True)
    packer.shutdown_query_pool()


@pytest.mark.parametrize("ranks", [None, {1: 2, 4: 1, 7: 5}], ids=["mejor", "con_rangos"])
def test_uno_o_cuatro_hilos_dan_el_mismo_layout(monkeypatch, ranks):
    piezas = [Part(i, ((0, 0), (300 + 7 * i, 0), (300, 90 + 5 * i), (0, 120)), (), (i,))
              for i in range(10)]
    plan = SheetSupply(stock=Sheet(1000.0, 1000.0, grain_tolerance=180.0))
    config = NestConfig(sep=5.0, margin=10.0, resolution=4.0, effort="rapido")
    monkeypatch.setattr(packer.os, "cpu_count", lambda: 8)

    monkeypatch.setattr(packer, "QUERY_THREADS", 1)
    assert packer.query_threads() == 1
    uno = _pack_once(piezas, plan, config, RasterOracleFactory(), orientation_ranks=ranks)
    monkeypatch.setattr(packer, "QUERY_THREADS", 4)
    assert packer.query_threads() == 4
    cuatro = _pack_once(piezas, plan, config, RasterOracleFactory(), orientation_ranks=ranks)
    packer.allow_query_threads(False)
    apagados = _pack_once(piezas, plan, config, RasterOracleFactory(), orientation_ranks=ranks)

    assert uno.placements
    assert uno.placements == cuatro.placements == apagados.placements


def test_el_proceso_principal_usa_hasta_cuatro_hilos_y_nunca_mas_que_los_nucleos(monkeypatch):
    monkeypatch.setattr(packer.os, "cpu_count", lambda: 14)
    assert packer.query_threads() == 4
    monkeypatch.setattr(packer.os, "cpu_count", lambda: 2)
    assert packer.query_threads() == 2
    monkeypatch.setattr(packer.os, "cpu_count", lambda: None)
    assert packer.query_threads() == 1


def test_apagarlos_deja_un_hilo_y_cierra_el_pool(monkeypatch):
    monkeypatch.setattr(packer.os, "cpu_count", lambda: 14)
    pool = packer._pool_for(4)
    assert packer._pool_for(4) is pool, "se reusa mientras no cambie la cantidad"

    packer.allow_query_threads(False)

    assert packer.query_threads() == 1
    assert packer._pool is None
    with pytest.raises(RuntimeError):
        pool.submit(int)


def test_cambiar_la_cantidad_cierra_el_pool_anterior():
    tres = packer._pool_for(3)
    dos = packer._pool_for(2)

    assert dos is not tres
    assert packer._pool is dos
    with pytest.raises(RuntimeError):
        tres.submit(int)


def test_un_proceso_de_la_cartera_consulta_con_un_solo_hilo():
    """El inicializador del pool de la cartera los apaga: la tanda ya ocupa
    un núcleo por proceso, y la memoria por proceso está medida sin hilos."""
    contexto = multiprocessing.get_context("spawn")
    reports = contexto.Queue()
    try:
        with ProcessPoolExecutor(
            max_workers=1, mp_context=contexto, initializer=cartera._init_worker,
            initargs=(RasterOracleFactory(), contexto.Event(), contexto.Value("q", 0), reports),
        ) as pool:
            assert pool.submit(packer.query_threads).result(timeout=60) == 1
    finally:
        reports.close()
        reports.join_thread()
