import pytest

from nesting.geometry.nesting_tree import OverlappingContourError, build_parts
from nesting.model.part import Contour


def square(x0, y0, side, ids):
    return Contour(
        points=((x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)),
        entity_ids=tuple(ids),
    )


def test_a_single_square_is_one_part_with_no_holes():
    parts, _ = build_parts([square(0, 0, 100, [0])])
    assert len(parts) == 1
    assert parts[0].holes == ()
    assert parts[0].entity_ids == (0,)
    assert parts[0].id == 0


def test_two_disjoint_squares_are_two_parts():
    parts, _ = build_parts([square(0, 0, 10, [0]), square(50, 50, 10, [1])])
    assert len(parts) == 2
    assert all(p.holes == () for p in parts)


def test_a_contour_inside_another_becomes_a_hole():
    parts, _ = build_parts([square(0, 0, 100, [0]), square(30, 30, 20, [1])])
    assert len(parts) == 1
    assert len(parts[0].holes) == 1
    assert sorted(parts[0].entity_ids) == [0, 1], "el agujero viaja con la pieza"


def test_depth_two_becomes_an_independent_part():
    """Exterior > agujero > isla. La isla es una pieza aparte."""
    contours = [square(0, 0, 100, [0]), square(20, 20, 60, [1]), square(40, 40, 20, [2])]
    parts, _ = build_parts(contours)

    assert len(parts) == 2
    outer = next(p for p in parts if p.outer_area > 1000)
    island = next(p for p in parts if p.outer_area <= 1000)

    assert sorted(outer.entity_ids) == [0, 1]
    assert island.entity_ids == (2,), "la isla NO arrastra los ids del padre"
    assert island.holes == ()


def test_depth_three_is_a_hole_of_the_depth_two_part():
    contours = [
        square(0, 0, 200, [0]),
        square(20, 20, 160, [1]),
        square(40, 40, 120, [2]),
        square(60, 60, 80, [3]),
    ]
    parts, _ = build_parts(contours)
    assert len(parts) == 2
    island = min(parts, key=lambda p: p.outer_area)
    assert len(island.holes) == 1
    assert sorted(island.entity_ids) == [2, 3]


def test_several_holes_in_one_part():
    contours = [
        square(0, 0, 100, [0]),
        square(10, 10, 10, [1]),
        square(40, 40, 10, [2]),
        square(70, 70, 10, [3]),
    ]
    parts, _ = build_parts(contours)
    assert len(parts) == 1
    assert len(parts[0].holes) == 3
    assert sorted(parts[0].entity_ids) == [0, 1, 2, 3]


def test_net_area_subtracts_the_holes():
    parts, _ = build_parts([square(0, 0, 100, [0]), square(30, 30, 20, [1])])
    assert parts[0].outer_area == pytest.approx(10000.0)
    assert parts[0].area == pytest.approx(10000.0 - 400.0)


def test_bbox():
    parts, _ = build_parts([square(5, -3, 10, [0])])
    assert parts[0].bbox == pytest.approx((5.0, -3.0, 15.0, 7.0))


def test_part_ids_are_consecutive_from_zero():
    contours = [square(0, 0, 10, [0]), square(50, 0, 10, [1]), square(100, 0, 10, [2])]
    parts, _ = build_parts(contours)
    assert sorted(p.id for p in parts) == [0, 1, 2]


def test_empty_input_produces_no_parts():
    assert build_parts([]) == ([], [])


def test_area_is_positive_regardless_of_winding_direction():
    clockwise = Contour(((0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)), (0,))
    parts, _ = build_parts([clockwise])
    assert parts[0].outer_area == pytest.approx(100.0)


# --- Detección de geometría inválida: agujero que solo se superpone parcialmente ---


def rect(x0, y0, x1, y1, ids):
    return Contour(points=((x0, y0), (x1, y0), (x1, y1), (x0, y1)), entity_ids=tuple(ids))


def test_partially_overlapping_contour_raises_instead_of_becoming_a_hole():
    """Reproducción del hallazgo: el 'agujero' sale del exterior por x=30.

    Su representative_point (22.5, 17.5) cae dentro del exterior, así que el
    chequeo de contención por punto lo aceptaría como agujero. El chequeo de
    contención real tiene que rechazarlo.
    """
    exterior = rect(0, 0, 30, 30, [0])
    overflowing = rect(10, 10, 35, 25, [1])

    with pytest.raises(OverlappingContourError) as excinfo:
        build_parts([exterior, overflowing])

    message = str(excinfo.value)
    assert "0" in message
    assert "1" in message


def test_hole_tangent_to_exterior_along_a_shared_edge_is_not_rejected():
    """Agujero tangente por dentro: comparte un tramo del borde izquierdo."""
    exterior = square(0, 0, 100, [0])
    tangent_hole = rect(0, 20, 50, 80, [1])

    parts, _ = build_parts([exterior, tangent_hole])

    assert len(parts) == 1
    assert len(parts[0].holes) == 1


def test_hole_touching_exterior_boundary_at_a_single_point_is_not_rejected():
    """Un rombo cuyo vértice inferior toca el borde exterior en un solo punto."""
    exterior = square(0, 0, 100, [0])
    diamond = Contour(
        points=((50.0, 0.0), (60.0, 10.0), (50.0, 20.0), (40.0, 10.0)),
        entity_ids=(1,),
    )

    parts, _ = build_parts([exterior, diamond])

    assert len(parts) == 1
    assert len(parts[0].holes) == 1


def test_deep_concentric_rings_do_not_raise():
    """Seis anillos concéntricos bien anidados, ninguno debe disparar el error."""
    sizes_and_offsets = [
        (200, 0),
        (190, 5),
        (180, 10),
        (170, 15),
        (160, 20),
        (150, 25),
    ]
    contours = [
        square(offset, offset, side, [i]) for i, (side, offset) in enumerate(sizes_and_offsets)
    ]

    parts, _ = build_parts(contours)

    assert len(parts) >= 1  # no explota; la jerarquía exacta no es lo que se prueba acá


def test_tiny_hole_correctly_nested_does_not_raise():
    """Un agujero de área minúscula, bien anidado, no debe disparar falsos positivos
    por el piso absoluto de tolerancia."""
    exterior = square(0, 0, 100, [0])
    tiny_hole = square(50, 50, 0.001, [1])

    parts, _ = build_parts([exterior, tiny_hole])

    assert len(parts) == 1
    assert len(parts[0].holes) == 1


# --- Hallazgo 1: contorno de área cero o degenerado ---


def test_a_collinear_contour_is_skipped_with_a_warning_instead_of_crashing():
    """Reproducción exacta del hallazgo: un anillo colineal junto a una pieza
    legítima. Antes se colaba hasta el chequeo de contención y terminaba
    rechazado como si se autointersecara -- un mensaje engañoso para una
    geometría que en realidad es colineal, no autointersecante."""
    legit = square(0, 0, 100, [0])
    collinear = Contour(points=((0.0, 0.0), (100.0, 0.0), (50.0, 0.0)), entity_ids=(1,))

    parts, skipped = build_parts([legit, collinear])

    assert len(parts) == 1
    assert sorted(parts[0].entity_ids) == [0]
    assert len(skipped) == 1


def test_all_contours_degenerate_returns_no_parts_instead_of_crashing():
    """Un 'moño' autointersecante (dos lóbulos con orientación opuesta) tiene
    área neta cero según la fórmula con signo, igual que un anillo colineal.
    Si es la única entrada, build_parts debe devolver una lista vacía, no
    reventar."""
    bowtie = Contour(
        points=((0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0)),
        entity_ids=(0,),
    )

    parts, skipped = build_parts([bowtie])

    assert parts == []
    assert len(skipped) == 1


def test_skipped_contours_come_back_whole_not_merely_counted():
    """Para marcarlo en el diagnóstico hace falta el contorno, no el número.

    Un contorno de área nula igual ocupa un lugar del dibujo, y el usuario
    necesita saber cuál es: casi siempre es un trazo mal cerrado que él quería
    como pieza.
    """
    legit = square(0, 0, 100, [0])
    collinear = Contour(points=((0.0, 0.0), (100.0, 0.0), (50.0, 0.0)), entity_ids=(1,))

    _, skipped = build_parts([legit, collinear])

    assert [c.entity_ids for c in skipped] == [(1,)]
    assert skipped[0].points == collinear.points
