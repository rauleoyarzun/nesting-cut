"""Lo que quedó en la última placa se reintenta en las anteriores.

El motor coloca de forma golosa y no vuelve atrás: una pieza que no entró
cuando le tocó se va a la placa siguiente aunque las piezas colocadas
DESPUÉS hayan dejado un hueco donde sí entra. Esta pasada cierra eso.
"""

import random

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    _pack_once,
    _recuperar_de_la_ultima_placa,
    layout_cost,
    pack,
)
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.model.material import Material
from nesting.model.part import Part
from nesting.model.sheet import SheetSupply

PLACA = Material("mdf", 1000.0, 1000.0, grain_tolerance=180.0)
PLAN_LIBRE = SheetSupply(stock=PLACA.stock_sheet(), material_name=PLACA.name)
CONFIG = NestConfig(sep=10.0, margin=20.0, angles=(0.0,), mirror=False, effort="rapido")
"""Una sola orientación a propósito: el escenario de abajo está calculado a
mano contra el cursor de estantes, y una rotación libre lo volvería
irreproducible sin agregar nada a lo que el test prueba."""


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


# Área útil: 960 x 960 mm (placa de 1000 con margen 20), separación 10.
#
# Orden goloso (área descendente): ANCHA, MEDIA, ANGOSTA.
#   ANCHA  (600x450) abre el estante y=20, deja el cursor en x=630.
#   MEDIA  (600x400) no entra a su derecha (630+600 > 980), así que abre el
#          estante y=480 y deja el cursor en x=630.
#   ANGOSTA (300x520) sí entra a lo ancho (630+300 <= 980) pero no a lo alto
#          (480+520 > 980), y un estante nuevo arrancaría en y=890, donde
#          tampoco entra. Se va a la placa 2.
#
# Con ANGOSTA adelante, en cambio, las tres entran en una sola placa:
#   ANGOSTA en (20,20) deja el cursor en x=330 y el estante de alto 520;
#   ANCHA entra a su derecha en (330,20); MEDIA abre el estante y=550 y
#   entra (550+400 <= 980).
ANCHA = rect_part(0, 600.0, 450.0)
MEDIA = rect_part(1, 600.0, 400.0)
ANGOSTA = rect_part(2, 300.0, 520.0)
TRES = [ANCHA, MEDIA, ANGOSTA]


def test_una_pieza_de_la_ultima_placa_vuelve_a_la_primera_si_entra():
    """Escenario armado para que la avaricia falle: una pieza ancha se
    coloca primero y ocupa el centro, una angosta no entra al lado, y
    recién las siguientes dejan libre la franja donde la angosta sí cabe."""
    goloso = _pack_once(TRES, PLAN_LIBRE, CONFIG, ShelfOracle)

    # Sin esto el test sería teatro: hay que ver a la avaricia fallar.
    assert goloso.sheets_used == 2
    assert [p.sheet for p in goloso.placements if p.part_id == ANGOSTA.id] == [1]

    recuperado = _recuperar_de_la_ultima_placa(
        goloso, TRES, CONFIG, ShelfOracle, PLACA.name
    )

    assert [p.sheet for p in recuperado.placements if p.part_id == ANGOSTA.id] == [0]
    assert {p.part_id for p in recuperado.placements} == {p.id for p in TRES}
    assert verify(
        TRES, recuperado.placements, recuperado.sheets,
        sep=CONFIG.sep, margin=CONFIG.margin,
    ) == []

    # Y de punta a punta: `pack` tiene que devolver una sola placa.
    assert pack(TRES, PLAN_LIBRE, CONFIG, ShelfOracle).sheets_used == 1


def test_si_la_ultima_placa_queda_vacia_se_descarta():
    """Recuperar la última pieza de la última placa tiene que bajar el
    conteo de placas, no dejar una placa vacía en el resultado."""
    goloso = _pack_once(TRES, PLAN_LIBRE, CONFIG, ShelfOracle)
    assert goloso.sheets_used == 2

    recuperado = _recuperar_de_la_ultima_placa(
        goloso, TRES, CONFIG, ShelfOracle, PLACA.name
    )

    assert recuperado.sheets_used == 1
    assert all(p.sheet == 0 for p in recuperado.placements)

    # El aprovechamiento se recalcula sobre las placas que quedaron, con la
    # misma cuenta que hace `_pack_once`: si quedara la fila de la placa
    # vacía, o si el total se promediara sobre dos placas, el usuario vería
    # un número que no corresponde a ningún layout.
    area_placa = PLACA.sheet_w * PLACA.sheet_h
    esperado = sum(p.area for p in TRES) / area_placa
    assert recuperado.utilization == [esperado]
    assert recuperado.total_utilization == esperado
    assert recuperado.seconds == goloso.seconds


def _escenario_al_azar(seed, motor):
    """Piezas rectangulares al azar sobre una placa chica, y su motor."""
    rng = random.Random(seed)
    material = Material("mdf", 800.0, 800.0, grain_tolerance=180.0)
    plan = SheetSupply(stock=material.stock_sheet(), material_name=material.name)
    config = NestConfig(sep=10.0, margin=10.0, angles=(0.0, 90.0), mirror=False,
                        effort="rapido", resolution=4.0)
    parts = [
        rect_part(i, rng.uniform(80.0, 380.0), rng.uniform(80.0, 380.0))
        for i in range(rng.randrange(6, 14))
    ]
    if motor == "shelf":
        return parts, plan, material, config, ShelfOracle

    cache = MaskCache()

    def factory():
        return RasterOracle(cache=cache)

    return parts, plan, material, config, factory


def test_la_recuperacion_nunca_empeora_el_costo():
    """Propiedad, no ejemplo: sobre varios escenarios al azar, el costo
    después de recuperar es <= al de antes."""
    recuperaron = 0
    multiplaca = 0

    for motor, semillas in (("shelf", range(30)), ("raster", range(20))):
        for seed in semillas:
            parts, plan, material, config, factory = _escenario_al_azar(seed, motor)
            antes = _pack_once(
                sorted(parts, key=lambda p: p.area, reverse=True),
                plan, config, factory,
            )
            if antes.sheets_used < 2:
                continue
            multiplaca += 1

            despues = _recuperar_de_la_ultima_placa(
                antes, parts, config, factory, material.name
            )

            caso = (motor, seed)
            assert layout_cost(despues, parts) <= layout_cost(antes, parts), caso
            # Ninguna pieza puede perderse ni duplicarse por el camino.
            ids = sorted(p.part_id for p in despues.placements)
            assert ids == sorted(p.id for p in parts), caso
            assert despues.sheets_used == len({p.sheet for p in despues.placements}), caso
            assert verify(
                parts, despues.placements, despues.sheets,
                sep=config.sep, margin=config.margin,
            ) == [], caso

            if layout_cost(despues, parts) < layout_cost(antes, parts):
                recuperaron += 1

    # Sin esto la propiedad la cumpliría también una función que no hace
    # nada: hace falta que en algún escenario la recuperación haya movido
    # algo de verdad. El piso es 1 y no el número medido (32 escenarios
    # multiplaca, 14 con mejora estricta al escribir esto) para que un
    # cambio legítimo de heurística no lo rompa: lo que se defiende acá es
    # que la pasada NO sea un no-op, no cuánto recupera.
    assert multiplaca >= 10
    assert recuperaron >= 1
