"""La cartera: variantes en un orden fijo, la mejor gana, y rápido no cambia."""

import math
from pathlib import Path

import pytest

from nesting.engine.cartera import (
    EFFORT_BATCHES,
    Variant,
    VariantSource,
    _Watch,
    cota_minima,
    evaluate,
    planned_variants,
    run_portfolio,
    smallest_combinations,
)
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    _compact_last_sheet,
    _pack_once,
    _recuperar_de_la_ultima_placa,
    layout_cost,
    pack,
)
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.verify import verify
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply

PLACA = Sheet(1000.0, 1000.0, grain_tolerance=180.0)
PLAN = SheetSupply(stock=PLACA, material_name="prueba")


def rect(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def siete():
    """Siete rectángulos de 400 x 300 en un área útil de 970 x 970: entran
    seis por placa, así que la base abre dos, y la cota por área es una. Es
    el caso más chico donde la cartera tiene algo que buscar. Son el 12,8%
    del área útil: la clase se empareja."""
    return [rect(i, 400.0, 300.0) for i in range(7)]


def config(**cambios):
    base = dict(sep=8.0, margin=15.0, angles=(0.0, 90.0), mirror=False,
                resolution=4.0, effort="normal", seed=0, workers=1)
    base.update(cambios)
    return NestConfig(**base)


# Las corridas usan la clase `RasterOracle` como fábrica, no una lambda que
# capture un `MaskCache`: con `workers > 1` la Tarea 6 manda la fábrica a
# otros procesos, y una lambda no viaja. Así estos tests no cambian cuando
# la tanda pasa a correr en paralelo.


class Espia:
    """Una fábrica que cuenta cada `best_placement`, la unidad de trabajo."""

    def __init__(self):
        self.consultas = 0
        self._cache = MaskCache()

    def __call__(self):
        espia, oraculo = self, RasterOracle(cache=self._cache)

        class Contado:
            def reset(self, *args):
                oraculo.reset(*args)

            def best_placement(self, *args):
                espia.consultas += 1
                return oraculo.best_placement(*args)

            def place(self, *args):
                oraculo.place(*args)

        return Contado()


NUNCA = _Watch(cancelled=lambda: False, best_new_sheets=lambda: 10**9,
               on_queries=lambda total: None)


# --- la cota --------------------------------------------------------------

def test_la_cota_es_el_area_de_las_piezas_sobre_el_area_util():
    assert cota_minima(siete(), PLAN, 15.0) == 1
    trece = [rect(i, 400.0, 300.0) for i in range(13)]
    assert cota_minima(trece, PLAN, 15.0) == math.ceil(13 * 120_000 / 970**2) == 2


def test_con_recortes_no_hay_cota():
    """Con placas de distinto tamaño, la cuenta honesta no es ésa."""
    con_recorte = SheetSupply(stock=PLACA, scraps=(Sheet(500.0, 500.0, 180.0, scrap=True),))
    assert cota_minima(siete(), con_recorte, 15.0) is None


# --- las combinaciones ------------------------------------------------------

def test_las_combinaciones_salen_de_menor_a_mayor_costo_y_desempatan_por_tipo():
    """Tres tipos de cajas 10, 20 y 30, cuatro miembros de caja 100. Con dos
    pares no sobra nadie; con uno sobran dos sueltos (200 más)."""
    combos = [c for _, c in smallest_combinations([10.0, 20.0, 30.0], 4, 100.0, False)]
    assert combos == [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2), (0,), (1,), (2,)]


def test_no_emparejar_es_la_combinacion_mas_cara_cuando_se_pide():
    combos = [c for _, c in smallest_combinations([10.0], 2, 100.0, True)]
    assert combos == [(0,), ()]


def test_sin_tipos_lo_unico_es_no_emparejar():
    assert list(smallest_combinations([], 4, 100.0, True)) == [(400.0, ())]


# --- las variantes ----------------------------------------------------------

def test_las_variantes_salen_en_el_mismo_orden_para_la_misma_semilla():
    uno, otro = VariantSource(siete(), PLAN, config()), VariantSource(siete(), PLAN, config())
    assert uno.base() == otro.base()
    assert uno.batch(1, 5, uno.base()) == otro.batch(1, 5, otro.base())


def test_la_base_es_la_pasada_de_hoy_por_area():
    fuente = VariantSource(siete() + [rect(9, 100.0, 50.0)], PLAN, config())
    base = fuente.base()
    assert base.index == 0 and base.kind == "base" and base.composites == ()
    assert [p.area for p in base.order] == sorted((p.area for p in base.order), reverse=True)


def test_la_primera_tanda_de_lento_es_la_de_normal():
    """Es lo que hace a normal prefijo de lento aunque lento busque diez
    tipos de par y normal seis."""
    normal = VariantSource(siete(), PLAN, config(effort="normal"))
    lento = VariantSource(siete(), PLAN, config(effort="lento"))
    assert normal.batch(1, 6, normal.base()) == lento.batch(1, 6, lento.base())


def test_primero_combinaciones_de_pares_y_despues_perturbaciones_de_orden():
    fuente = VariantSource(siete(), PLAN, config())
    tipos = [v.kind for v in fuente.batch(1, 200, fuente.base())]
    assert tipos[0] == "pares" and tipos[-1] == "orden"
    assert tipos == sorted(tipos, key=lambda t: t != "pares"), "no se intercalan"


def test_sin_clases_emparejables_la_tanda_es_de_perturbaciones():
    """Cuadrados de 100 x 100: el 1% del área útil, no se emparejan."""
    chicos = [rect(i, 100.0, 100.0) for i in range(20)]
    fuente = VariantSource(chicos, PLAN, config())
    assert {v.kind for v in fuente.batch(1, 4, fuente.base())} == {"orden"}


def test_la_tercera_tanda_perturba_orientaciones_de_la_mejor():
    fuente = VariantSource(siete() + [rect(9, 100.0, 50.0)], PLAN, config(effort="lento"))
    mejor = fuente.batch(1, 3, fuente.base())[0]
    tanda = fuente.batch(3, 3, mejor)

    assert {v.kind for v in tanda} == {"orientacion"}
    for variante in tanda:
        assert variante.order == mejor.order
        assert variante.composites == mejor.composites
        assert variante.orientation_ranks
        assert all(0 <= rango < 3 for _, rango in variante.orientation_ranks)


def test_cada_variante_de_pares_usa_cada_pieza_real_una_sola_vez():
    fuente = VariantSource(siete(), PLAN, config())
    for variante in fuente.batch(1, 10, fuente.base()):
        if variante.kind != "pares":
            continue
        miembros = [m for c in variante.composites for m, _ in c.members]
        sueltas = [p.id for p in variante.order if p.id < 7]
        assert sorted(miembros + sueltas) == list(range(7))


# --- evaluar ----------------------------------------------------------------

def test_una_variante_que_abre_mas_placas_que_la_mejor_se_corta():
    variante = Variant(1, "orden", tuple(siete()))
    ya_hay_una_de_cero = _Watch(cancelled=lambda: False, best_new_sheets=lambda: 0,
                                on_queries=lambda total: None)
    assert evaluate(variante, siete(), PLAN, config(), RasterOracle, ya_hay_una_de_cero) is None


def test_sin_corte_la_misma_variante_da_su_resultado():
    variante = Variant(1, "orden", tuple(siete()))
    resultado = evaluate(variante, siete(), PLAN, config(), RasterOracle, NUNCA)
    assert resultado is not None
    assert resultado.cost.placas_nuevas == 2


# --- run_portfolio ----------------------------------------------------------

def test_rapido_es_exactamente_la_pasada_de_siempre():
    """La garantía más importante del plan: rápido no cambia."""
    piezas = siete()
    cfg = config(effort="rapido")
    orden = sorted(piezas, key=lambda p: p.area, reverse=True)
    f = RasterOracle
    viejo = _pack_once(orden, PLAN, cfg, f)
    viejo = _recuperar_de_la_ultima_placa(viejo, piezas, cfg, f, PLAN.material_name)
    viejo = _compact_last_sheet(viejo, piezas, cfg, f, PLAN.material_name)

    nuevo = pack(piezas, PLAN, cfg, RasterOracle)

    assert nuevo.placements == viejo.placements
    assert nuevo.sheets == viejo.sheets
    assert nuevo.utilization == viejo.utilization


def test_si_la_base_alcanza_la_cota_no_se_prueba_nada_mas():
    cuatro = [rect(i, 400.0, 300.0) for i in range(4)]
    salida = run_portfolio(cuatro, PLAN, config(workers=3), RasterOracle)
    assert [v.kind for v in salida.evaluated] == ["base"]
    assert salida.lower_bound == 1 == salida.result.sheets_used


def test_normal_evalua_la_base_y_una_tanda_y_es_prefijo_de_lento():
    normal = run_portfolio(siete(), PLAN, config(effort="normal", workers=3), RasterOracle)
    lento = run_portfolio(siete(), PLAN, config(effort="lento", workers=3), RasterOracle)

    assert len(normal.evaluated) == planned_variants("normal", 3) == 4
    assert len(lento.evaluated) == planned_variants("lento", 3) == 10
    assert lento.evaluated[:4] == normal.evaluated


@pytest.mark.minimo_real
def test_con_pocos_nucleos_la_tanda_no_baja_del_minimo():
    """Decisión del usuario: el resultado no depende de la máquina. Con 4
    núcleos, normal prueba las mismas 12 variantes que con 12."""
    from nesting.engine.cartera import MIN_BATCH, batch_size

    assert MIN_BATCH == 12
    assert batch_size(1) == batch_size(4) == batch_size(12) == 12
    assert planned_variants("normal", 4) == planned_variants("normal", 12) == 13
    assert planned_variants("lento", 4) == 37


@pytest.mark.minimo_real
def test_con_mas_nucleos_que_el_minimo_la_tanda_crece():
    from nesting.engine.cartera import batch_size

    assert batch_size(14) == 14
    assert planned_variants("normal", 14) == 15


@pytest.mark.minimo_real
def test_rapido_no_paga_el_minimo():
    assert planned_variants("rapido", 4) == 1


def test_mas_esfuerzo_nunca_da_peor():
    costos = {
        e: layout_cost(pack(siete(), PLAN, config(effort=e, workers=2), RasterOracle), siete())
        for e in EFFORT_BATCHES
    }
    assert costos["lento"] <= costos["normal"] <= costos["rapido"]


def test_el_resultado_trae_solo_piezas_reales_y_verifica():
    piezas = siete()
    salida = run_portfolio(piezas, PLAN, config(effort="lento", workers=3), RasterOracle)
    resultado = salida.result

    assert sorted(p.part_id for p in resultado.placements) == list(range(7))
    assert verify(piezas, resultado.placements, resultado.sheets, sep=8.0, margin=15.0) == []


def test_el_avance_suma_consultas_y_nunca_retrocede():
    """Con `workers=1` todo corre en este proceso y el espía ve cada
    consulta: la cuenta del avance tiene que coincidir exacta. (En paralelo
    el espía viajaría a otros procesos y contaría allá.)"""
    avances = []
    espia = Espia()
    pack(siete(), PLAN, config(workers=1), espia,
         progreso=lambda a: avances.append(a) or True)

    hechas = [a.consultas_hechas for a in avances]
    assert hechas == sorted(hechas)
    assert all(a.consultas_previstas >= a.consultas_hechas for a in avances)
    assert hechas[-1] == espia.consultas


def test_el_avance_de_la_cartera_cuenta_combinaciones():
    avances = []
    pack(siete(), PLAN, config(workers=2), RasterOracle,
         progreso=lambda a: avances.append(a) or True)

    de_cartera = [a for a in avances if a.combinaciones]
    assert de_cartera, "la tanda tiene que avisar"
    assert all(a.combinaciones == planned_variants("normal", 2) for a in de_cartera)
    assert max(a.combinaciones_hechas for a in de_cartera) >= 2
    assert all(a.placa_minima >= 1 for a in de_cartera)


# --- reloj: cuántas pasadas cuesta la cartera, para el tiempo estimado ------

from nesting.engine.cartera import wall_forecast, wall_passes


def test_las_pasadas_de_reloj_multiplican_por_la_tanda_y_dividen_por_n():
    """Spec 6: el tiempo estimado previo multiplica por las variantes de la
    tanda y divide por N. Con la tanda de N variantes en N núcleos, cada
    tanda cuesta una pasada de reloj."""
    assert wall_passes("rapido", 12) == 1.0
    assert wall_passes("normal", 12) == 2.0
    assert wall_passes("lento", 4) == 4.0
    assert wall_passes("normal", 1) == 2.0


def test_la_prevision_de_reloj_suma_una_pasada_por_tanda_con_el_minimo_bajado():
    """Con `MIN_BATCH` bajado a 1 (el fixture `_tanda_minima_de_uno` de
    `tests/conftest.py`), la tanda es siempre de exactamente `N` variantes en
    `N` núcleos, así que cada tanda cuesta una pasada -- y por eso, acá, la
    previsión no depende de con cuántos núcleos se llame.

    Eso NO es una propiedad general de `wall_forecast`: con el `MIN_BATCH`
    real (12), una tanda por debajo de 12 núcleos reparte más de una
    variante por núcleo y sí depende de `N` (`ceil(batch_size(N) / N)` deja
    de ser 1) -- ver
    `test_la_prevision_de_reloj_a_escala_real_depende_de_n_por_debajo_del_minimo`."""
    rapido = wall_forecast(siete(), PLAN, config(effort="rapido", workers=4))
    normal = wall_forecast(siete(), PLAN, config(effort="normal", workers=4))
    lento = wall_forecast(siete(), PLAN, config(effort="lento", workers=4))

    pasada = normal - rapido
    assert pasada > 0
    assert lento == pytest.approx(rapido + 3 * pasada)
    assert wall_forecast(siete(), PLAN, config(effort="normal", workers=1)) == pytest.approx(normal)


@pytest.mark.minimo_real
def test_la_prevision_de_reloj_a_escala_real_depende_de_n_por_debajo_del_minimo():
    """Con el `MIN_BATCH` real (12) -- sin el fixture que lo baja a 1 --, la
    tanda tiene `batch_size(N)` variantes, no `N`: por debajo del mínimo son
    siempre 12, repartidas en `N` núcleos, y `ceil(12 / N)` sí depende de
    `N`. `wall_passes("normal", 4) == 4.0` porque `ceil(12 / 4) == 3` (una
    base + 3 vueltas), mientras que con `MIN_BATCH` bajado a 1 esa misma
    llamada da 2.0 (ver el test de arriba)."""
    assert wall_passes("rapido", 4) == 1.0
    assert wall_passes("normal", 1) == 13.0
    assert wall_passes("normal", 4) == 4.0
    assert wall_passes("normal", 12) == 2.0
    assert wall_passes("normal", 14) == 2.0
    assert wall_passes("lento", 4) == 10.0


def test_la_prevision_de_reloj_de_rapido_es_la_de_arranque():
    """Con una sola pasada no hay nada que repartir: la cuenta del plan 2
    tiene que salir intacta."""
    from nesting.engine.packer import initial_forecast

    cfg = config(effort="rapido", workers=4)
    assert wall_forecast(siete(), PLAN, cfg) == initial_forecast(siete(), PLAN, cfg)


# --- el orden de las combinaciones: primero las que entran como rectángulos ---

def _tipo_falso(w, h):
    from nesting.engine.pares import PairType
    from nesting.model.entities import Transform

    return PairType(relative=Transform.identity(), box_area=w * h, width=w, height=h,
                    orientation=(0.0, False), offset_px=(0, 0),
                    outer=((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), holes=())


def test_la_combinacion_que_entra_como_rectangulos_sale_antes_que_la_mas_chica():
    """Dos tipos: el de menor caja (1200 x 100) no entra en el área útil de
    970 x 970 de ninguna forma; el otro (600 x 300) sí, y al lado le queda
    lugar para el cuadrado suelto. Por área saldría primero el que no entra."""
    from nesting.engine.cartera import _PairPlan
    from nesting.engine.iguales import Clase, Member
    from nesting.model.entities import Transform

    piezas = [rect(0, 400.0, 300.0), rect(1, 400.0, 300.0), rect(5, 300.0, 300.0)]
    fuente = VariantSource(piezas, PLAN, config())
    clase = Clase(piezas[0], (Member(0, Transform.identity()), Member(1, Transform.identity())))
    fuente._plan = _PairPlan((clase,), ((_tipo_falso(1200.0, 100.0), _tipo_falso(600.0, 300.0)),))

    assert fuente.predicted_sheets(((0,),)) == 2
    assert fuente.predicted_sheets(((1,),)) == 1
    assert fuente._combinations(6, 2) == [((1,),), ((0,),)]


BANQUETA = Path(__file__).resolve().parents[2] / "bench" / "files" / "banqueta-alta.ai"


@pytest.mark.skipif(
    not BANQUETA.exists(),
    reason=f"falta {BANQUETA}: es un archivo de diseño del usuario y no se "
           "versiona (ver .gitignore). Copiá 'BANQUETA ALTA NESTING.ai' ahí.",
)
def test_en_la_banqueta_la_tanda_empieza_por_una_combinacion_que_entra_en_una_placa():
    """Ordenadas sólo por área, las doce primeras eran todas imposibles
    (Tarea 9): tres pares de la caja mínima, de 1809 de largo, no entran
    en 2430 de alto útil con nada más encima."""
    from nesting.engine.pares import TIPOS_POR_CLASE
    from nesting.io.ai_reader import read_ai
    from nesting.pipeline import prepare_parts

    piezas, _, _ = prepare_parts(read_ai(BANQUETA))
    plan = SheetSupply(stock=Sheet(1220.0, 2440.0, grain_tolerance=180.0), material_name="libre")
    cfg = NestConfig(sep=8.0, margin=5.0, angles=tuple(i * 45.0 for i in range(8)),
                     mirror=True, resolution=1.0, effort="normal", seed=0, workers=4)
    fuente = VariantSource(piezas, plan, cfg)
    tipos = fuente._pair_plan().types[0]

    def indice(w, h):
        return next(i for i, t in enumerate(tipos)
                    if sorted((t.width, t.height)) == pytest.approx(sorted((w, h)), abs=5.0))

    diagonal, apilado = indice(1508.0, 560.0), indice(1056.0, 875.0)
    combos = fuente._combinations(TIPOS_POR_CLASE["normal"], 12)

    assert fuente.predicted_sheets(combos[0]) == 1
    assert (tuple(sorted((diagonal, diagonal, apilado))),) in combos
