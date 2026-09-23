"""Las tandas en paralelo: el mismo resultado, y ningún proceso colgado."""

import multiprocessing

import pytest

from nesting.engine.cartera import (
    Variant,
    VariantSource,
    _Evaluator,
    _Progress,
    run_portfolio,
)
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import Cancelado, pack
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle, RasterOracleFactory
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply

PLAN = SheetSupply(stock=Sheet(1000.0, 1000.0, grain_tolerance=180.0), material_name="prueba")


def rect(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def siete():
    """El caso de `test_cartera.py`: la base abre dos placas, la cota es una."""
    return [rect(i, 400.0, 300.0) for i in range(7)]


def config(**cambios):
    base = dict(sep=8.0, margin=15.0, angles=(0.0, 90.0), mirror=False,
                resolution=4.0, effort="normal", seed=0, workers=4)
    base.update(cambios)
    return NestConfig(**base)


def sin_avance():
    return _Progress(None, totales=7, planned=5, initial_queries=1)


def test_el_pool_se_crea_con_spawn():
    """En Linux el contexto por omisión es `fork`; la spec pide que las tres
    plataformas se comporten igual."""
    assert _Evaluator(config(), RasterOracleFactory())._context.get_start_method() == "spawn"


def test_la_misma_tanda_da_lo_mismo_con_uno_y_con_cuatro_procesos():
    """El determinismo que la spec exige: el resultado no depende de cuándo
    termina cada proceso, porque se ordena por índice y se desempata por
    índice."""
    fuente = VariantSource(siete(), PLAN, config())
    tanda = fuente.batch(1, 4, fuente.base())

    def correr(procesos):
        with _Evaluator(config(), RasterOracleFactory(), processes=procesos) as evaluador:
            return evaluador.run(tanda, siete(), PLAN, 10**9, sin_avance())

    uno, cuatro = correr(1), correr(4)
    assert [(o.index, o.cost, o.packed.placements) for o in uno] == \
           [(o.index, o.cost, o.packed.placements) for o in cuatro]


def test_la_cartera_entera_da_lo_mismo_dos_veces_en_paralelo():
    una = run_portfolio(siete(), PLAN, config(effort="lento", workers=3), RasterOracleFactory())
    otra = run_portfolio(siete(), PLAN, config(effort="lento", workers=3), RasterOracleFactory())
    assert una.winner == otra.winner
    assert una.result.placements == otra.result.placements


def test_en_paralelo_tambien_se_corta_lo_que_ya_perdio():
    tanda = [Variant(1, "orden", tuple(siete())),
             Variant(2, "orden", tuple(reversed(siete())))]
    with _Evaluator(config(workers=2), RasterOracleFactory()) as evaluador:
        assert evaluador.run(tanda, siete(), PLAN, 0, sin_avance()) == []


def test_una_fabrica_que_no_viaja_se_rechaza_con_un_mensaje_claro():
    cache = MaskCache()
    tanda = [Variant(1, "orden", tuple(siete())),
             Variant(2, "orden", tuple(reversed(siete())))]
    with pytest.raises(TypeError, match="RasterOracleFactory"):
        with _Evaluator(config(workers=2), lambda: RasterOracle(cache=cache)) as evaluador:
            evaluador.run(tanda, siete(), PLAN, 10**9, sin_avance())


def test_las_consultas_de_todos_los_procesos_se_suman():
    avances = []
    pack(siete(), PLAN, config(workers=3), RasterOracleFactory(),
         progreso=lambda a: avances.append(a) or True)

    hechas = [a.consultas_hechas for a in avances]
    assert hechas == sorted(hechas), "la cuenta no puede retroceder"
    assert all(a.consultas_previstas >= a.consultas_hechas for a in avances)
    base = max(a.consultas_hechas for a in avances
               if not a.combinaciones and not a.compactando)
    de_tanda = [a for a in avances if a.combinaciones]
    assert de_tanda and de_tanda[-1].consultas_hechas > base, "la tanda tiene que sumar"


def test_cancelar_en_la_tanda_no_deja_ningun_proceso_vivo():
    def cortar_apenas_arranca_la_tanda(avance):
        return not avance.combinaciones

    with pytest.raises(Cancelado):
        pack(siete(), PLAN, config(workers=2), RasterOracleFactory(),
             progreso=cortar_apenas_arranca_la_tanda)

    assert multiprocessing.active_children() == []
