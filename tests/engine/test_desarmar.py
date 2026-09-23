"""Una compuesta se acomoda como una pieza y se desarma en sus dos miembros."""

import pytest
from shapely.ops import unary_union

from nesting.engine.iguales import find_classes
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import PackResult, _pack_once, orientations
from nesting.engine.pares import (
    b_orientations,
    disassemble,
    find_pair_types,
    make_composite,
)
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.transform import apply_points
from nesting.geometry.verify import placed_polygon, verify
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement
from nesting.model.sheet import Sheet, SheetSupply

ELE = ((0.0, 0.0), (600.0, 0.0), (600.0, 110.0), (110.0, 110.0), (110.0, 300.0), (0.0, 300.0))
PLACA = Sheet(1400.0, 1400.0, grain_tolerance=180.0)
PLAN = SheetSupply(stock=PLACA, material_name="prueba")


def config(espejo):
    return NestConfig(sep=8.0, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0),
                      mirror=espejo, resolution=2.0, effort="rapido")


def dibujada(part_id, t):
    """Una copia de la L tal como la dibujaría un usuario: en otro lugar,
    y girada o espejada."""
    return Part(part_id, apply_points(t, ELE), (), (part_id,))


def armar(espejo, segunda):
    cfg = config(espejo)
    piezas = [dibujada(0, Transform.identity()), dibujada(1, segunda)]
    choices = orientations(PLACA, cfg)
    clase = find_classes(piezas, choices)[0]
    assert len(clase.members) == 2, "las dos copias tienen que ser de la misma clase"
    tipo = find_pair_types(clase.representative, b_orientations(choices, False), choices,
                           cfg, (1390.0, 1390.0), 1, MaskCache())[0]
    compuesta = make_composite(100, tipo, clase.members[0], clase.members[1])
    return cfg, piezas, compuesta


@pytest.mark.parametrize("espejo, segunda", [
    (True, Transform(90.0, True, 2000.0, 500.0)),
    (False, Transform(270.0, False, -900.0, 1200.0)),
])
def test_las_piezas_reales_desarmadas_verifican(espejo, segunda):
    """La prueba que importa: el árbitro, mirando sólo las piezas reales,
    no encuentra nada. Con espejo la segunda copia está dibujada espejada
    y girada; sin espejo, sólo girada."""
    cfg, piezas, compuesta = armar(espejo, segunda)
    cache = MaskCache()
    acomodado = _pack_once([compuesta.part], PLAN, cfg, lambda: RasterOracle(cache=cache))

    real = disassemble(acomodado, [compuesta], piezas)

    assert sorted(p.part_id for p in real.placements) == [0, 1]
    assert verify(piezas, real.placements, real.sheets, sep=cfg.sep, margin=cfg.margin) == []


def test_los_miembros_ocupan_la_compuesta_salvo_el_puente():
    cfg, piezas, compuesta = armar(True, Transform(180.0, True, 50.0, 3000.0))
    colocada = Transform(90.0, True, 700.0, 20.0)
    resultado = PackResult(placements=[Placement(100, 0, colocada)], sheets=[PLACA])

    real = disassemble(resultado, [compuesta], piezas)

    por_id = {p.id: p for p in piezas}
    miembros = unary_union([placed_polygon(por_id[p.part_id], p.transform)
                            for p in real.placements])
    par = placed_polygon(compuesta.part, colocada)
    # El puente mide a lo sumo 2·sep de largo y 2 mm de ancho, con puntas
    # redondas: menos de 40 mm². Un miembro mal compuesto erra por miles.
    assert par.symmetric_difference(miembros).area < 40.0


def test_el_aprovechamiento_se_recalcula_sin_el_puente():
    cfg, piezas, compuesta = armar(True, Transform(0.0, False, 900.0, 0.0))
    resultado = PackResult(placements=[Placement(100, 0, Transform(0.0, False, 10.0, 10.0))],
                           sheets=[PLACA], utilization=[0.99], total_utilization=0.99)

    real = disassemble(resultado, [compuesta], piezas)

    esperado = sum(p.area for p in piezas) / PLACA.area
    assert real.utilization == [pytest.approx(esperado)]
    assert real.total_utilization == pytest.approx(esperado)


def test_sin_compuestas_se_devuelve_el_mismo_resultado():
    """La base no tiene pares: desarmarla no puede tocar un solo número."""
    resultado = PackResult(placements=[Placement(0, 0, Transform.identity())], sheets=[PLACA])
    assert disassemble(resultado, [], [dibujada(0, Transform.identity())]) is resultado


def test_las_sueltas_quedan_donde_estaban_y_en_su_orden():
    cfg, piezas, compuesta = armar(True, Transform(0.0, False, 900.0, 0.0))
    suelta = Part(7, ((0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0)), (), (7,))
    antes = Placement(7, 0, Transform(0.0, False, 1200.0, 1200.0))
    resultado = PackResult(
        placements=[antes, Placement(100, 0, Transform.identity())], sheets=[PLACA],
    )

    real = disassemble(resultado, [compuesta], piezas + [suelta])

    assert real.placements[0] == antes
    assert [p.part_id for p in real.placements[1:]] == [0, 1]
