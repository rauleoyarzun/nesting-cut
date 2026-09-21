import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    PartTooLargeError,
    orientations,
    pack,
    replicate,
)
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.model.material import Material
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply

FREE = Material("mdf", 1000.0, 1000.0, grain_tolerance=180.0)
GRAIN = Material("multilam", 1000.0, 1000.0, grain_tolerance=5.0)
CONFIG = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=False,
                    effort="rapido")
"""Esfuerzo fijo en una pasada golosa: estos tests verifican la estrategia base,
no la busqueda con reintentos que agrega la Task 19."""

PLAN_LIBRE = SheetSupply(stock=FREE.stock_sheet(), material_name=FREE.name)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def test_replicate_renumbers_ids_and_keeps_entity_ids():
    parts = [rect_part(0, 10.0, 10.0), rect_part(1, 20.0, 20.0)]
    copies = replicate(parts, 3)

    assert len(copies) == 6
    assert [p.id for p in copies] == [0, 1, 2, 3, 4, 5]
    assert copies[0].entity_ids == copies[2].entity_ids == copies[4].entity_ids


def test_replicate_with_one_copy_is_a_no_op():
    parts = [rect_part(0, 10.0, 10.0)]
    assert [p.id for p in replicate(parts, 1)] == [0]


def test_replicate_rejects_a_non_positive_count():
    with pytest.raises(ValueError):
        replicate([rect_part(0, 1.0, 1.0)], 0)


def test_orientations_without_mirroring():
    config = NestConfig(angles=(0.0, 90.0, 180.0, 270.0), mirror=False)
    assert orientations(FREE.stock_sheet(), config) == [
        (0.0, False), (90.0, False), (180.0, False), (270.0, False)
    ]


def test_orientations_with_mirroring_doubles_the_list():
    config = NestConfig(angles=(0.0, 90.0), mirror=True)
    assert orientations(FREE.stock_sheet(), config) == [
        (0.0, False), (90.0, False), (0.0, True), (90.0, True)
    ]


def test_grain_constraint_filters_the_orientations():
    config = NestConfig(angles=(0.0, 90.0, 180.0, 270.0), mirror=False)
    assert orientations(GRAIN.stock_sheet(), config) == [(0.0, False), (180.0, False)]


def test_a_single_part_fits_on_one_sheet():
    parts = [rect_part(0, 100.0, 100.0)]
    result = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert len(result.placements) == 1
    assert result.seconds >= 0.0


def test_parts_spill_onto_a_second_sheet():
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    result = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)

    assert result.sheets_used >= 2
    assert {p.sheet for p in result.placements} == set(range(result.sheets_used))


def test_a_part_bigger_than_the_sheet_is_reported():
    parts = [rect_part(0, 5000.0, 5000.0)]
    with pytest.raises(PartTooLargeError) as info:
        pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)
    assert "5000" in str(info.value)


def test_bigger_parts_are_placed_first():
    parts = [rect_part(0, 50.0, 50.0), rect_part(1, 400.0, 400.0)]
    result = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)
    assert result.placements[0].part_id == 1


def test_utilisation_is_reported_per_sheet_and_in_total():
    parts = [rect_part(i, 300.0, 300.0) for i in range(4)]
    result = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)

    assert len(result.utilization) == result.sheets_used
    assert all(0.0 < u <= 1.0 for u in result.utilization)
    assert 0.0 < result.total_utilization <= 1.0


def test_the_result_always_passes_the_verifier():
    """El invariante central: ningun motor puede producir una salida invalida."""
    parts = [rect_part(i, 180.0, 120.0) for i in range(20)]
    result = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)

    violations = verify(
        parts, result.placements, FREE.sheet_w, FREE.sheet_h,
        sep=CONFIG.sep, margin=CONFIG.margin,
    )
    assert violations == []


def test_packing_is_deterministic():
    parts = [rect_part(i, 180.0, 120.0) for i in range(10)]
    first = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)
    second = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)
    assert first.placements == second.placements


def test_an_empty_part_list_produces_an_empty_result():
    result = pack([], PLAN_LIBRE, CONFIG, ShelfOracle)
    assert result.sheets_used == 0
    assert result.placements == []
    assert result.total_utilization == 0.0


# --- Hallazgo 1: ruido de punto flotante en rotaciones de 90 grados ---


def test_90_degree_rotation_with_zero_separation_passes_verify():
    """Reproduccion exacta del hallazgo 1: con sep=0 y una rotacion forzada de
    90 grados, dos piezas que quedan tocandose en un borde compartido no
    deben generar un solapamiento fantasma."""
    parts = [rect_part(0, 500.0, 300.0), rect_part(1, 400.0, 250.0)]
    config = NestConfig(sep=0.0, margin=0.0, angles=(90.0,), mirror=False, effort="rapido")
    result = pack(parts, PLAN_LIBRE, config, ShelfOracle)

    violations = verify(
        parts, result.placements, FREE.sheet_w, FREE.sheet_h,
        sep=config.sep, margin=config.margin,
    )
    assert violations == []


def test_a_wide_sweep_of_sep_and_angle_combinations_passes_verify():
    """Barrido mas amplio del mismo estilo: varias separaciones y angulos,
    con y sin espejado, todos deben pasar la verificacion sin violaciones."""
    parts = [rect_part(i, 180.0, 120.0) for i in range(6)]

    for sep in (0.0, 0.5, 6.0):
        for angle in (0.0, 90.0, 180.0, 270.0, 45.0, 37.0):
            for mirror in (False, True):
                config = NestConfig(
                    sep=sep, margin=0.0, angles=(angle,), mirror=mirror, effort="rapido"
                )
                result = pack(parts, PLAN_LIBRE, config, ShelfOracle)
                violations = verify(
                    parts, result.placements, FREE.sheet_w, FREE.sheet_h,
                    sep=config.sep, margin=config.margin,
                )
                assert violations == [], (sep, angle, mirror, violations)


def test_part_too_large_error_message_matches_a_real_orientation():
    """Hallazgo 2: el mensaje no puede mezclar el ancho de una orientacion con
    el alto de otra. Para una pieza de 1200x100 con angulos (0, 90), la mejor
    orientacion es la que minimiza la dimension mas grande, y su mensaje debe
    mencionar el 1200 real de esa orientacion."""
    parts = [rect_part(0, 1200.0, 100.0)]
    config = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=False,
                         effort="rapido")
    small_sheet = Material("mdf", 960.0, 960.0, grain_tolerance=180.0)
    plan_chico = SheetSupply(
        stock=small_sheet.stock_sheet(), material_name=small_sheet.name
    )

    with pytest.raises(PartTooLargeError) as info:
        pack(parts, plan_chico, config, ShelfOracle)

    message = str(info.value)
    assert "1200" in message
    assert "100.0" in message


# --- Hallazgo 1b: una pieza de área neta cero no debe hacer explotar el packer ---


def test_a_zero_area_part_still_gets_placed_without_crashing():
    """Un Part cuyo contorno es un 'moño' autointersecante tiene área neta
    cero (la fórmula con signo cancela los dos lóbulos), pero su bounding box
    es real y el oráculo sí le encuentra lugar. El guard que decide si hay
    que reportar `PartTooLargeError` tiene que mirar cuántas piezas se
    colocaron, no cuánta área -- de lo contrario, con esta pieza como única
    pendiente, `still_pending` queda vacío y `still_pending[0]` revienta con
    `IndexError`."""
    bowtie = Part(0, ((0.0, 0.0), (100.0, 100.0), (100.0, 0.0), (0.0, 100.0)), (), (0,))
    assert bowtie.area == 0.0

    result = pack([bowtie], PLAN_LIBRE, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert len(result.placements) == 1


def test_el_resultado_dice_que_placa_fue_cada_indice():
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    result = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)

    assert len(result.sheets) == result.sheets_used
    assert all(h is PLAN_LIBRE.stock for h in result.sheets)


def test_sin_recortes_el_aprovechamiento_se_calcula_igual_que_siempre():
    """La cuenta pasó de un área única a un área por placa. Con todas las
    placas iguales tiene que dar exactamente lo mismo, o alguna corrida
    vieja cambió de número sin que nadie lo pidiera."""
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    result = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)

    area_placa = FREE.sheet_w * FREE.sheet_h
    for indice, fraccion in enumerate(result.utilization):
        area_en_placa = sum(
            p.area for p in parts
            for pl in result.placements
            if pl.part_id == p.id and pl.sheet == indice
        )
        assert fraccion == pytest.approx(area_en_placa / area_placa)

    total = sum(p.area for p in parts)
    assert result.total_utilization == pytest.approx(
        total / (area_placa * result.sheets_used)
    )


def test_orientations_toma_una_placa_y_respeta_su_veta():
    libre = orientations(FREE.stock_sheet(), CONFIG)
    con_veta = orientations(GRAIN.stock_sheet(), CONFIG)

    assert (90.0, False) in libre
    assert (90.0, False) not in con_veta
    assert (0.0, False) in con_veta


def test_orientations_mira_la_veta_de_cada_placa_y_no_la_del_material():
    """Dos placas del mismo material con la veta al revés permiten ángulos
    distintos. Si esto falla, las orientaciones se están calculando una vez
    por corrida en lugar de una por placa."""
    derecha = Sheet(500.0, 500.0, grain_tolerance=5.0)
    cruzada = Sheet(500.0, 500.0, grain_tolerance=5.0, cross_grain=True)

    assert (0.0, False) in orientations(derecha, CONFIG)
    assert (0.0, False) not in orientations(cruzada, CONFIG)
    assert (90.0, False) in orientations(cruzada, CONFIG)
