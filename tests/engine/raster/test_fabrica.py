"""La fábrica de oráculos que se puede mandar a otro proceso."""

import pickle

from nesting.engine.raster.oracle import RasterOracle, RasterOracleFactory


def test_cada_oraculo_de_una_fabrica_comparte_su_cache():
    fabrica = RasterOracleFactory()
    uno, otro = fabrica(), fabrica()
    assert isinstance(uno, RasterOracle)
    assert uno._cache is otro._cache is fabrica.cache


def test_viaja_sin_su_cache_y_del_otro_lado_arma_una_propia():
    """Un proceso `spawn` sólo recibe lo que se serializa. Mandar el caché
    lleno sería mandar cientos de MB que el otro proceso igual tiene que
    poder rehacer; mandarlo vacío es lo mismo que no mandarlo."""
    fabrica = RasterOracleFactory(max_bytes=1234)
    fabrica()  # llena el caché de este lado
    copia = pickle.loads(pickle.dumps(fabrica))
    assert copia._cache is None
    assert copia.cache is not fabrica.cache
    assert copia.cache._max_bytes == 1234
