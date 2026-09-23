"""Las tandas en paralelo: el mismo resultado, y ningún proceso colgado."""

import multiprocessing
import threading

import pytest

from nesting.engine import cartera
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
    # Cuatro posiciones, como en `test_cartera.py`: con 0° y 90° solos no se
    # empareja nada (`pares.orientations_closed`).
    base = dict(sep=8.0, margin=15.0, angles=(0.0, 90.0, 180.0, 270.0), mirror=False,
                resolution=4.0, effort="normal", seed=0, workers=4)
    base.update(cambios)
    return NestConfig(**base)


def sin_avance():
    return _Progress(None, totales=7, planned=5, initial_queries=1)


def test_el_pool_se_crea_con_spawn():
    """En Linux el contexto por omisión es `fork`; la spec pide que las tres
    plataformas se comporten igual."""
    assert _Evaluator(config(), RasterOracleFactory())._context.get_start_method() == "spawn"


def grande_y_chicas():
    """Una grande y cuatro chicas: la grande primero entra en una placa; las
    chicas primero se reparten por el fondo y la grande ya no entra, dos."""
    return [rect(0, 700.0, 700.0)] + [rect(i, 250.0, 250.0) for i in range(1, 5)]


def test_la_misma_tanda_da_lo_mismo_con_uno_y_con_cuatro_procesos():
    """El determinismo que la spec exige, y sólo ése.

    Qué variantes se cortan SÍ depende de cuándo termina cada una: en serie,
    la tercera ya ve a la segunda terminada con una placa y se corta; en
    paralelo arrancan juntas y puede que no. Lo que no depende de nada es
    lo que decide la cartera: la ganadora -- el mínimo por (costo, índice)
    -- y cuáles llegan a la menor cantidad de placas, que nunca se cortan.
    """
    piezas = grande_y_chicas()
    grande, chicas = piezas[0], piezas[1:]
    tanda = [
        Variant(1, "orden", tuple(chicas) + (grande,)),           # dos placas
        Variant(2, "orden", (grande,) + tuple(chicas)),           # una
        Variant(3, "orden", tuple(reversed(chicas)) + (grande,)),  # dos
        Variant(4, "orden", (grande,) + tuple(reversed(chicas))),  # una
    ]

    def correr(procesos):
        with _Evaluator(config(), RasterOracleFactory(), processes=procesos) as evaluador:
            return evaluador.run(tanda, piezas, PLAN, 10**9, sin_avance())

    def lo_que_decide(outcomes):
        ganadora = min(outcomes, key=lambda o: (o.cost, o.index))
        minimo = min(o.cost.placas_nuevas for o in outcomes)
        return (
            (ganadora.index, ganadora.cost, ganadora.packed.placements),
            {o.index for o in outcomes if o.cost.placas_nuevas == minimo},
        )

    uno, cuatro = correr(1), correr(4)
    assert len(uno) < len(tanda), "en serie algo se tiene que cortar, si no el test no prueba nada"
    assert lo_que_decide(uno) == lo_que_decide(cuatro)
    assert lo_que_decide(uno)[1] == {2, 4}


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
    with pytest.raises(TypeError, match="RasterOracleFactory"):
        _Evaluator(config(workers=2), lambda: RasterOracle(cache=cache))


def test_una_fabrica_que_no_viaja_se_rechaza_antes_de_la_base():
    """Enterarse después de una pasada entera -- minutos, en un trabajo
    real -- de algo que se sabía antes de arrancar."""
    pedidos = []

    def fabrica():
        pedidos.append(1)
        return RasterOracle()

    with pytest.raises(TypeError, match="RasterOracleFactory"):
        pack(siete(), PLAN, config(workers=2), fabrica)
    assert pedidos == []


def test_en_rapido_una_fabrica_que_no_viaja_sigue_sirviendo():
    """Rápido no prueba variantes, así que nunca arma el pool: no hay por
    qué pedirle a su fábrica que viaje."""
    cache = MaskCache()
    resultado = pack(siete(), PLAN, config(effort="rapido", workers=2),
                     lambda: RasterOracle(cache=cache))
    assert resultado.sheets_used == 2


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


def _llenar_la_cola(mensajes: int) -> int:
    """Corre en un proceso del pool: deja la cola de avisos llena y vuelve."""
    for total in range(mensajes):
        cartera._worker["reports"].put((1, total))
    return mensajes


def test_cerrar_no_se_cuelga_aunque_queden_avisos_sin_leer():
    """Un proceso que puso en una `multiprocessing.Queue` espera, al salir, a
    que su hilo alimentador vacíe todo en el pipe; si el pipe está lleno
    porque el principal ya no lee -- cancelaron --, esa espera no termina y
    `shutdown(wait=True)` se cuelga con el proceso vivo."""
    evaluador = _Evaluator(config(workers=2), RasterOracleFactory())
    # Sin `with`: el cierre corre en un hilo aparte, para poder ponerle un
    # tope en vez de colgar la suite si vuelve el problema.
    cerrar = threading.Thread(target=evaluador.__exit__, args=(None, None, None), daemon=True)
    try:
        evaluador._start_pool()
        assert evaluador._pool.submit(_llenar_la_cola, 20_000).result(timeout=30) == 20_000
        cerrar.start()
        cerrar.join(timeout=10)
        assert not cerrar.is_alive(), "cerrar el pool se colgó"
        assert multiprocessing.active_children() == []
    finally:
        for hijo in multiprocessing.active_children():
            hijo.kill()
