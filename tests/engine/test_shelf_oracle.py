import pytest

from nesting.engine.oracle import NestConfig, Oracle, transformed_bbox
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


CONFIG = NestConfig(sep=10.0, margin=20.0)


def test_transformed_bbox_of_an_unrotated_part():
    assert transformed_bbox(rect_part(0, 100.0, 50.0), 0.0, False) == pytest.approx(
        (0.0, 0.0, 100.0, 50.0)
    )


def test_transformed_bbox_swaps_dimensions_at_ninety_degrees():
    x0, y0, x1, y1 = transformed_bbox(rect_part(0, 100.0, 50.0), 90.0, False)
    assert (x1 - x0) == pytest.approx(50.0)
    assert (y1 - y0) == pytest.approx(100.0)


def test_transformed_bbox_of_a_mirrored_part():
    x0, y0, x1, y1 = transformed_bbox(rect_part(0, 100.0, 50.0), 0.0, True)
    assert (x0, y0, x1, y1) == pytest.approx((-100.0, 0.0, 0.0, 50.0))


def test_the_first_part_lands_on_the_margin():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    x0, y0, _, _ = transformed_bbox(part, 0.0, False)
    assert (x + x0, y + y0) == pytest.approx((20.0, 20.0))


def test_best_placement_does_not_mutate_state():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    first = oracle.best_placement(part, 0.0, False)
    second = oracle.best_placement(part, 0.0, False)
    assert first == second


def test_the_second_part_goes_to_the_right_with_the_separation():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    oracle.place(part, 0.0, False, x, y)
    x2, _, _ = oracle.best_placement(part, 0.0, False)

    assert (x2 - x) == pytest.approx(110.0), "100 de ancho mas 10 de separacion"


def test_a_new_shelf_opens_when_the_row_is_full():
    oracle = ShelfOracle()
    oracle.reset(300.0, 1000.0, CONFIG)   # util: 260 de ancho
    part = rect_part(0, 100.0, 50.0)

    placed = []
    for _ in range(3):
        result = oracle.best_placement(part, 0.0, False)
        assert result is not None
        x, y, _ = result
        oracle.place(part, 0.0, False, x, y)
        placed.append((x, y))

    assert placed[0][1] == pytest.approx(placed[1][1]), "las dos primeras comparten estante"
    assert placed[2][1] > placed[0][1], "la tercera abre estante nuevo"
    assert placed[2][0] == pytest.approx(placed[0][0]), "y vuelve al margen izquierdo"


def test_returns_none_when_the_part_does_not_fit_at_all():
    oracle = ShelfOracle()
    oracle.reset(100.0, 100.0, CONFIG)
    assert oracle.best_placement(rect_part(0, 500.0, 500.0), 0.0, False) is None


def test_returns_none_once_the_sheet_is_full():
    oracle = ShelfOracle()
    oracle.reset(200.0, 200.0, CONFIG)   # util: 160 x 160
    part = rect_part(0, 150.0, 150.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    oracle.place(part, 0.0, False, x, y)
    assert oracle.best_placement(part, 0.0, False) is None


def test_lower_placements_score_higher():
    oracle = ShelfOracle()
    oracle.reset(300.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    _, _, first_score = oracle.best_placement(part, 0.0, False)
    for _ in range(2):
        x, y, _ = oracle.best_placement(part, 0.0, False)
        oracle.place(part, 0.0, False, x, y)
    _, _, later_score = oracle.best_placement(part, 0.0, False)

    assert first_score > later_score


def test_reset_clears_previous_state():
    oracle = ShelfOracle()
    part = rect_part(0, 100.0, 50.0)

    oracle.reset(1000.0, 1000.0, CONFIG)
    x, y, _ = oracle.best_placement(part, 0.0, False)
    oracle.place(part, 0.0, False, x, y)

    oracle.reset(1000.0, 1000.0, CONFIG)
    assert oracle.best_placement(part, 0.0, False)[:2] == pytest.approx((x, y))


def test_a_full_shelf_layout_passes_the_verifier():
    """El test que importa: lo que produce el oraculo tiene que ser valido."""
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)

    parts = [rect_part(i, 100.0, 80.0) for i in range(12)]
    placements = []
    for part in parts:
        result = oracle.best_placement(part, 0.0, False)
        if result is None:
            continue
        x, y, _ = result
        oracle.place(part, 0.0, False, x, y)
        placements.append(Placement(part.id, 0, Transform(0.0, False, x, y)))

    assert len(placements) >= 8
    assert verify(parts, placements, 1000.0, 1000.0, sep=10.0, margin=20.0) == []


def test_rotated_parts_also_pass_the_verifier():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)

    parts = [rect_part(i, 200.0, 60.0) for i in range(6)]
    placements = []
    for index, part in enumerate(parts):
        angle = 90.0 if index % 2 else 0.0
        result = oracle.best_placement(part, angle, False)
        if result is None:
            continue
        x, y, _ = result
        oracle.place(part, angle, False, x, y)
        placements.append(Placement(part.id, 0, Transform(angle, False, x, y)))

    assert placements
    assert verify(parts, placements, 1000.0, 1000.0, sep=10.0, margin=20.0) == []


def test_place_rejects_a_position_from_a_different_angle():
    """Reproduce el caso del revisor: el x de la consulta a 90 grados colado en
    un place a 0 grados. El oraculo no puede commitear eso en silencio."""
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 60.0)

    x0, y0, _ = oracle.best_placement(part, 0.0, False)
    x90, y90, _ = oracle.best_placement(part, 90.0, False)
    assert (x0, y0) == pytest.approx((20.0, 20.0))
    assert (x90, y90) == pytest.approx((80.0, 20.0))

    with pytest.raises(ValueError) as exc_info:
        oracle.place(part, 0.0, False, x90, y0)

    message = str(exc_info.value)
    assert "80.0" in message, "tiene que mencionar la posicion recibida"
    assert "20.0" in message, "tiene que mencionar la posicion esperada"


def test_place_rejects_an_arbitrary_made_up_position():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 60.0)
    oracle.best_placement(part, 0.0, False)

    with pytest.raises(ValueError):
        oracle.place(part, 0.0, False, 999.0, 999.0)


def test_a_long_mixed_sequence_placed_correctly_still_passes_the_verifier():
    """El camino correcto -- place con el (x, y) que devolvio best_placement --
    tiene que seguir funcionando igual, incluso con piezas dispares, angulos
    mezclados (incluido uno que no es multiplo de 90) y alguna espejada."""
    oracle = ShelfOracle()
    oracle.reset(2000.0, 4000.0, CONFIG)

    angles = (0.0, 90.0, 180.0, 270.0, 37.0)
    mirrors = (False, True)

    parts = []
    placements = []
    for i in range(40):
        w = 40.0 + float((i * 7) % 90)
        h = 30.0 + float((i * 5) % 70)
        part = rect_part(i, w, h)
        angle = angles[i % len(angles)]
        mirror = mirrors[i % len(mirrors)]

        result = oracle.best_placement(part, angle, mirror)
        assert result is not None, f"la pieza {i} tendria que entrar en la placa"
        x, y, _ = result
        oracle.place(part, angle, mirror, x, y)

        parts.append(part)
        placements.append(Placement(part.id, 0, Transform(angle, mirror, x, y)))

    assert len(placements) == 40
    assert verify(parts, placements, 2000.0, 4000.0, sep=10.0, margin=20.0) == []


def test_shelf_oracle_satisfies_the_oracle_protocol():
    assert isinstance(ShelfOracle(), Oracle)


def test_a_failed_place_does_not_advance_the_oracles_state():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 60.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    with pytest.raises(ValueError):
        oracle.place(part, 0.0, False, x + 500.0, y)

    # El place invalido no puede haber dejado rastro: el correcto, llamado
    # justo despues, tiene que dar exactamente el mismo resultado que si el
    # intento fallido nunca hubiera ocurrido.
    oracle.place(part, 0.0, False, x, y)
    x2, y2, _ = oracle.best_placement(part, 0.0, False)

    reference = ShelfOracle()
    reference.reset(1000.0, 1000.0, CONFIG)
    rx, ry, _ = reference.best_placement(part, 0.0, False)
    reference.place(part, 0.0, False, rx, ry)
    rx2, ry2, _ = reference.best_placement(part, 0.0, False)

    assert (x, y) == pytest.approx((rx, ry))
    assert (x2, y2) == pytest.approx((rx2, ry2))
