"""Las pruebas que importan: seis marcos que sólo entran encastrados de a
pares, y con dos tipos de par distintos."""

import itertools
from pathlib import Path

import pytest

from nesting.engine.cartera import run_portfolio
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import PartTooLargeError, _pack_once, orientations
from nesting.engine.pares import TIPOS_POR_CLASE, b_orientations, find_pair_types
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracleFactory
from nesting.geometry.verify import verify
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply

# --- el caso sintético ------------------------------------------------------
#
# Medido al escribir el plan (ver la Tarea 9 del plan de pares y cartera):
# sin pares, 2 placas; ninguna combinación de tres pares de UN solo tipo
# entra en una; dos mezclas sí, y la de puesto 1 cae en la tanda de normal
# con dos núcleos.

ELE = ((0.0, 0.0), (600.0, 0.0), (600.0, 110.0), (110.0, 110.0), (110.0, 300.0), (0.0, 300.0))
PLACA = Sheet(1200.0, 690.0, grain_tolerance=180.0)
PLAN = SheetSupply(stock=PLACA, material_name="sintética")
UTIL = (PLACA.width - 10.0, PLACA.height - 10.0)


def seis():
    return [Part(i, ELE, (), (i,)) for i in range(6)]


def config(**cambios):
    base = dict(sep=8.0, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0), mirror=True,
                resolution=2.0, effort="normal", seed=0, workers=2)
    base.update(cambios)
    return NestConfig(**base)


def test_seis_eles_entran_en_una_placa_solo_con_pares_de_dos_tipos():
    piezas = seis()

    rapido = run_portfolio(piezas, PLAN, config(effort="rapido"), RasterOracleFactory())
    assert rapido.result.sheets_used == 2, "sin pares, la trampa tiene que atrapar a la pasada golosa"

    normal = run_portfolio(piezas, PLAN, config(), RasterOracleFactory())
    resultado = normal.result

    assert resultado.sheets_used == 1
    assert normal.lower_bound == 1, "y entonces se puede decir que no se puede con menos"
    tipos = {tipo for _, tipo in normal.winner.pair_types}
    assert len(tipos) >= 2, f"ganó una combinación de un solo tipo: {normal.winner.pair_types}"
    assert sorted(p.part_id for p in resultado.placements) == list(range(6))
    assert verify(piezas, resultado.placements, resultado.sheets, sep=8.0, margin=5.0) == []


@pytest.mark.lento
def test_el_caso_sintetico_necesita_mezclar_tipos():
    """La confirmación de que el caso de arriba es la trampa que dice ser, y
    no uno que un tipo solo ya resuelve: se prueban las 56 combinaciones de
    tres pares, cada una con una pasada golosa. Tarda del orden de 15 s."""
    cfg = config(effort="rapido")
    choices = orientations(PLACA, cfg)
    tipos = find_pair_types(seis()[0], b_orientations(choices, False), choices, cfg,
                            UTIL, TIPOS_POR_CLASE["normal"], MaskCache())
    fabrica = RasterOracleFactory()

    assert _pack_once(seis(), PLAN, cfg, fabrica).sheets_used == 2

    una_placa = []
    for combo in itertools.combinations_with_replacement(range(len(tipos)), 3):
        orden = sorted((tipos[t].shape(100 + k) for k, t in enumerate(combo)),
                       key=lambda p: p.area, reverse=True)
        try:
            placas = _pack_once(orden, PLAN, cfg, fabrica).sheets_used
        except PartTooLargeError:
            continue
        if placas == 1:
            una_placa.append(combo)

    puros = [c for c in una_placa if len(set(c)) == 1]
    assert puros == [], f"un solo tipo alcanza, la trampa no es tal: {puros}"
    assert una_placa, "ninguna mezcla de tres pares entra en una placa"


# --- la banqueta alta ---------------------------------------------------------

BANQUETA = Path(__file__).resolve().parents[2] / "bench" / "files" / "banqueta-alta.ai"

falta_la_banqueta = pytest.mark.skipif(
    not BANQUETA.exists(),
    reason=(
        f"falta {BANQUETA}: es un archivo de diseño del usuario y no se versiona "
        "(bench/files/ está en .gitignore). Copiá ahí 'BANQUETA ALTA NESTING.ai' "
        "con ese nombre para correr esta prueba."
    ),
)


def piezas_de_la_banqueta():
    from nesting.io.ai_reader import read_ai
    from nesting.pipeline import prepare_parts

    piezas, _, _ = prepare_parts(read_ai(BANQUETA))
    return piezas


def config_banqueta():
    """8 posiciones, sep 8, borde 5, 1 mm/px, normal, con `workers = 4` a
    propósito: la combinación que gana sale octava, y es `MIN_BATCH` el que
    garantiza que una máquina de 4 núcleos también la pruebe. Las pruebas que
    usan esto llevan `@pytest.mark.minimo_real`; sin la marca, el fixture de
    `tests/conftest.py` bajaría la tanda a 4 y la banqueta daría 2 placas."""
    return NestConfig(sep=8.0, margin=5.0, angles=tuple(i * 45.0 for i in range(8)),
                      mirror=True, resolution=1.0, effort="normal", seed=0, workers=4)


@pytest.mark.lento
@pytest.mark.minimo_real
@falta_la_banqueta
def test_la_banqueta_alta_entra_en_una_placa_libre():
    piezas = piezas_de_la_banqueta()
    assert len(piezas) == 57
    plan = SheetSupply(stock=Sheet(1220.0, 2440.0, grain_tolerance=180.0), material_name="libre")

    salida = run_portfolio(piezas, plan, config_banqueta(), RasterOracleFactory())

    assert salida.result.sheets_used == 1, (salida.winner.kind, salida.winner.pair_types)
    assert salida.lower_bound == 1
    assert verify(piezas, salida.result.placements, salida.result.sheets,
                  sep=8.0, margin=5.0) == []


@pytest.mark.lento
@falta_la_banqueta
def test_la_banqueta_alta_con_veta_son_dos_placas_y_no_dice_minimo():
    """Con la veta respetada, 1 placa es imposible (la columna de seis marcos
    a 0° y 180° mide 2530 mm contra 2430 útiles), y la cota por área sigue
    siendo 1: el cartel de mínimo no tiene que salir."""
    piezas = piezas_de_la_banqueta()
    plan = SheetSupply(stock=Sheet(1220.0, 2440.0, grain_tolerance=5.0),
                       material_name="multilam18")

    salida = run_portfolio(piezas, plan, config_banqueta(), RasterOracleFactory())

    assert salida.result.sheets_used == 2
    assert salida.lower_bound == 1 != salida.result.sheets_used
    assert verify(piezas, salida.result.placements, salida.result.sheets,
                  sep=8.0, margin=5.0) == []
