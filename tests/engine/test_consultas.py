"""Las consultas al oráculo: cuántas se hicieron y cuántas se prevén.

Una consulta es una llamada a `Oracle.best_placement`. Es la unidad con la
que se mide el avance y se estima el tiempo (spec de tiempo estimado, 2).
"""

import random
import sys
from pathlib import Path

import pytest

from nesting.engine.cartera import planned_variants
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    Avance,
    Cancelado,
    UnknownEffortError,
    _compact_last_sheet,
    _pack_once,
    _recuperar_de_la_ultima_placa,
    initial_forecast,
    pack,
    probe_query_seconds,
)
from nesting.engine.prevision import forecast_pack
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.io.ai_reader import read_ai
from nesting.io.dxf_reader import read_dxf
from nesting.model.material import VETA_RESPETAR, Material
from nesting.model.part import Part
from nesting.model.sheet import SheetSupply
from nesting.pipeline import prepare_parts

RAIZ = Path(__file__).resolve().parents[2]
BANQUETA = RAIZ / "bench" / "files" / "banqueta-alta.ai"

sys.path.insert(0, str(RAIZ / "bench"))
from make_sample import write_sample  # noqa: E402

MATERIAL = Material("test", 1000.0, 1000.0, 180.0)
PLAN = SheetSupply(stock=MATERIAL.stock_sheet(), material_name=MATERIAL.name)


def cuadrado(part_id, lado=100.0):
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)),
        holes=(),
        entity_ids=(part_id,),
    )


def rectangulo(part_id, ancho, alto):
    return Part(
        part_id, ((0.0, 0.0), (ancho, 0.0), (ancho, alto), (0.0, alto)), (), (part_id,)
    )


class Espia:
    """Envuelve un oráculo, cuenta cada `best_placement` y no cambia nada.

    Es la cuenta de verdad contra la que se compara lo que informa `pack`:
    si el motor contara por su lado (por ejemplo, piezas por orientaciones)
    y no las llamadas reales, este espía lo agarra.
    """

    def __init__(self, interno, cuenta):
        self._interno = interno
        self._cuenta = cuenta

    def reset(self, sheet_w, sheet_h, config):
        self._interno.reset(sheet_w, sheet_h, config)

    def best_placement(self, part, angle, mirror):
        self._cuenta[0] += 1
        return self._interno.best_placement(part, angle, mirror)

    def place(self, part, angle, mirror, x, y):
        self._interno.place(part, angle, mirror, x, y)


def fabrica_raster():
    cache = MaskCache()
    return lambda: RasterOracle(cache=cache)


def fabrica_espia(cuenta):
    cache = MaskCache()
    return lambda: Espia(RasterOracle(cache=cache), cuenta)


def config(**cambios):
    base = {"sep": 5.0, "margin": 10.0, "effort": "rapido"}
    base.update(cambios)
    return NestConfig(**base)


def correr(piezas, cfg, fabrica, plan=PLAN):
    avances = []
    pack(piezas, plan, cfg, fabrica, progreso=lambda a: avances.append(a) or True)
    return avances


def test_un_avance_armado_como_antes_trae_cero_consultas():
    """Los corredores de mentira de `tests/app` arman `Avance` con cinco
    argumentos. Tienen que seguir funcionando sin tocarlos."""
    avance = Avance(1, 1, 0, 10, 1)
    assert avance.consultas_hechas == 0
    assert avance.consultas_previstas == 0


def test_las_consultas_hechas_nunca_bajan():
    """No se reinician entre intentos ni entre fases: son la única cifra de
    avance que no retrocede al empezar el intento siguiente."""
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = correr(piezas, config(effort="normal"), fabrica_raster())

    hechas = [a.consultas_hechas for a in avances]
    assert hechas == sorted(hechas)
    assert hechas[0] > 0


def test_las_consultas_hechas_terminan_iguales_a_las_llamadas_reales():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    cuenta = [0]

    avances = correr(piezas, config(effort="normal"), fabrica_espia(cuenta))

    assert cuenta[0] > 0
    assert avances[-1].consultas_hechas == cuenta[0]


def test_contar_no_cambia_el_layout():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    cuenta = [0]
    sin = pack(piezas, PLAN, config(), fabrica_raster())
    con = pack(piezas, PLAN, config(), fabrica_espia(cuenta), progreso=lambda a: True)

    assert [(p.part_id, p.sheet, p.transform) for p in sin.placements] == [
        (p.part_id, p.sheet, p.transform) for p in con.placements
    ]


def test_una_pieza_que_no_entra_tambien_avisa():
    """Placa de 1000 con margen 10: entra un solo cuadrado de 600 por placa.
    Las dos que no entran en la placa 1 gastan sus consultas ahí, y el aviso
    tiene que salir igual para que el contador y el botón de cancelar las
    vean."""
    grandes = [cuadrado(i, lado=600.0) for i in range(3)]
    cfg = config(angles=(0.0,), mirror=False)
    avisos = []

    _pack_once(grandes, PLAN, cfg, ShelfOracle, lambda u, p: avisos.append((u, p)))

    assert avisos == [(1, 1), (1, 1), (1, 1), (2, 2), (2, 2), (3, 3)]


def test_la_compactacion_avisa():
    """Cuatro cuadrados chicos: una sola placa, así que la recuperación sale
    sin consultar y todo aviso de `compactando` después del de entrada es de
    la compactación (4 piezas) o el final."""
    piezas = [cuadrado(i) for i in range(4)]
    avances = correr(piezas, config(), fabrica_raster())

    compactando = [a for a in avances if a.compactando]
    assert len(compactando) == 1 + 4 + 1


def test_la_compactacion_se_cancela():
    piezas = [cuadrado(i) for i in range(4)]
    vistos = []

    def cortar(avance):
        vistos.append(avance)
        return sum(1 for a in vistos if a.compactando) < 2

    with pytest.raises(Cancelado):
        pack(piezas, PLAN, config(), fabrica_raster(), progreso=cortar)

    assert sum(1 for a in vistos if a.compactando) == 2


def test_compactar_reenvia_el_aviso_y_deja_pasar_cancelado():
    """El `except PartTooLargeError` de `_compact_last_sheet` no puede
    tragarse un `Cancelado`: sería un trabajo cancelado que termina LISTO."""
    piezas = [cuadrado(i) for i in range(4)]
    fabrica = fabrica_raster()
    armado = _pack_once(piezas, PLAN, config(), fabrica)

    def cancelar(ubicadas, placa):
        raise Cancelado("el trabajo se canceló")

    with pytest.raises(Cancelado):
        _compact_last_sheet(armado, piezas, config(), fabrica, MATERIAL.name, cancelar)


def test_sin_callback_no_hay_avisos_pero_el_resultado_es_el_mismo():
    piezas = [cuadrado(i) for i in range(4)]
    assert pack(piezas, PLAN, config(), fabrica_raster()).sheets_used == 1


def test_la_prevision_de_arranque_de_un_caso_a_mano():
    """Diez cuadrados de 100 en una placa de 1000: área de piezas 1e5 contra
    980 x 980 x 0.4 = 384160 útiles, así que una placa. Cuatro ángulos con
    espejo son 8 orientaciones, y normal son `planned_variants('normal', 1)`
    pasadas."""
    piezas = [cuadrado(i) for i in range(10)]
    cfg = config(effort="normal")

    assert initial_forecast(piezas, PLAN, cfg) == forecast_pack(
        10, 8, 1, planned_variants("normal", 1)
    )


def test_la_prevision_de_arranque_rechaza_un_esfuerzo_desconocido():
    with pytest.raises(UnknownEffortError):
        initial_forecast([cuadrado(0)], PLAN, config(effort="turbo"))


def test_sin_piezas_no_se_prevé_nada():
    assert initial_forecast([], PLAN, config()) == 0


def test_el_primer_aviso_trae_la_prevision_de_arranque():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    cfg = config(effort="normal")

    avances = correr(piezas, cfg, fabrica_raster())

    assert avances[0].consultas_previstas == initial_forecast(piezas, PLAN, cfg)


def test_las_previstas_nunca_quedan_por_debajo_de_las_hechas():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = correr(piezas, config(effort="normal"), fabrica_raster())

    assert all(a.consultas_previstas >= a.consultas_hechas for a in avances)


def test_el_ultimo_aviso_dice_que_no_falta_nada():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = correr(piezas, config(effort="normal"), fabrica_raster())

    assert avances[-1].consultas_previstas == avances[-1].consultas_hechas


def test_al_entrar_a_compactar_la_prevision_es_exacta():
    """Una placa con cuatro cuadrados: no hay recuperación, y compactar es
    una pasada de 4 piezas por 8 orientaciones. Al entrar ya se sabe."""
    piezas = [cuadrado(i) for i in range(4)]
    avances = correr(piezas, config(), fabrica_raster())

    entrada = next(a for a in avances if a.compactando)
    assert entrada.consultas_previstas == entrada.consultas_hechas + 4 * 8
    assert avances[-1].consultas_hechas == entrada.consultas_hechas + 4 * 8


# El escenario de `test_recuperacion.py`, copiado y no importado para que
# este archivo no dependa de otro archivo de tests: una placa de 1000 con
# margen 20, una sola orientación, y ANGOSTA que la avaricia manda a la
# placa 2 (ver el comentario largo de allá).
ESTANTES = NestConfig(sep=10.0, margin=20.0, angles=(0.0,), mirror=False, effort="rapido")
PLACA_TRES = Material("mdf", 1000.0, 1000.0, grain_tolerance=180.0)
PLAN_TRES = SheetSupply(stock=PLACA_TRES.stock_sheet(), material_name=PLACA_TRES.name)
TRES = [
    rectangulo(0, 600.0, 450.0),
    rectangulo(1, 600.0, 400.0),
    rectangulo(2, 300.0, 520.0),
]


def test_la_recuperacion_preve_antes_de_cada_intento():
    """Placa 0 con 2 piezas, 1 pendiente, 1 orientación: el intento cuesta
    (2 + 1) consultas en la placa más 1 en el derrame."""
    goloso = _pack_once(TRES, PLAN_TRES, ESTANTES, ShelfOracle)
    assert goloso.sheets_used == 2
    previstos = []

    _recuperar_de_la_ultima_placa(
        goloso, TRES, ESTANTES, ShelfOracle, PLACA_TRES.name,
        None, lambda restantes, pendientes: previstos.append((restantes, pendientes)),
    )

    assert previstos[0] == (4, 1)


def _rectangulos_al_azar():
    rng = random.Random(1)
    return [
        rectangulo(i, float(rng.randint(80, 400)), float(rng.randint(80, 400)))
        for i in range(40)
    ]


def _caso(nombre, tmp_path):
    """(piezas, plan, config, fábrica) de cada caso del bench."""
    if nombre == "estantes":
        return (
            _rectangulos_al_azar(), PLAN, config(effort="normal"), ShelfOracle,
        )
    if nombre == "muestra":
        ruta = tmp_path / "muestra.dxf"
        write_sample(ruta)
        piezas, _, _ = prepare_parts(read_dxf(ruta))
        mdf18 = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
        return (
            piezas,
            SheetSupply(stock=mdf18.stock_sheet(), material_name=mdf18.name),
            NestConfig(sep=6.0, margin=10.0, effort="normal", resolution=3.0),
            fabrica_raster(),
        )
    if not BANQUETA.exists():
        pytest.skip(
            f"falta {BANQUETA}: bench/files/ no está versionado. Copiar ahí "
            "`BANQUETA ALTA NESTING.ai` con el nombre banqueta-alta.ai para "
            "correr este caso."
        )
    piezas, _, _ = prepare_parts(read_ai(BANQUETA))
    multilam = Material("multilam18", 1220.0, 2440.0, grain_tolerance=VETA_RESPETAR)
    # 2 mm/px y no 1: a 1 mm/px la corrida tarda 126 s, y este test corre
    # con la suite entera al cerrar cada tarea. La previsión cuenta
    # consultas, que no dependen de la resolución más que por el layout.
    return (
        piezas,
        SheetSupply(stock=multilam.stock_sheet(), material_name=multilam.name),
        NestConfig(sep=8.0, margin=5.0, effort="normal", resolution=2.0),
        fabrica_raster(),
    )


@pytest.mark.parametrize("nombre", ["estantes", "muestra", "banqueta-alta"])
def test_despues_del_primer_intento_la_prevision_erra_menos_de_un_cuarto(nombre, tmp_path):
    """Spec, 4: después del primer intento, el error de la previsión contra
    el total real es menor al 25% sobre los archivos del bench.

    El primer aviso después de la base es el primero que lleva la previsión
    corregida con lo que costó la base. Con la cartera puede ser uno de la
    tanda (`combinaciones_hechas >= 1`) o, si la base ya igualó la cota por
    área y no se busca nada más -- `muestra` --, la entrada al tramo final."""
    piezas, plan, cfg, fabrica = _caso(nombre, tmp_path)

    avances = correr(piezas, cfg, fabrica, plan=plan)

    tras_el_primero = next(
        a for a in avances if a.combinaciones_hechas >= 1 or a.compactando
    )
    reales = avances[-1].consultas_hechas
    error = abs(tras_el_primero.consultas_previstas - reales) / reales
    assert error < 0.25, (
        f"{nombre}: previstas {tras_el_primero.consultas_previstas}, reales {reales}"
    )


class Anotador(ShelfOracle):
    """Un oráculo de estantes que anota qué le preguntaron."""

    def __init__(self, anotadas):
        super().__init__()
        self._anotadas = anotadas

    def best_placement(self, part, angle, mirror):
        self._anotadas.append((part.id, angle, mirror))
        return super().best_placement(part, angle, mirror)


def test_la_prueba_mide_una_consulta_con_la_pieza_mas_grande():
    chica, grande = cuadrado(0, 100.0), cuadrado(1, 300.0)
    anotadas = []
    tiempos = iter([10.0, 10.25])

    segundos = probe_query_seconds(
        [chica, grande], PLAN, config(), lambda: Anotador(anotadas),
        clock=lambda: next(tiempos),
    )

    assert segundos == pytest.approx(0.25)
    assert anotadas == [(1, 0.0, False)], "una sola consulta, la primera orientación"


def test_sin_orientaciones_permitidas_no_hay_prueba():
    con_veta = Material("veta", 1000.0, 1000.0, grain_tolerance=5.0)
    plan = SheetSupply(stock=con_veta.stock_sheet(), material_name=con_veta.name)

    assert probe_query_seconds(
        [cuadrado(0)], plan, config(angles=(90.0,)), ShelfOracle
    ) is None


def test_sin_piezas_no_hay_prueba():
    assert probe_query_seconds([], PLAN, config(), ShelfOracle) is None
