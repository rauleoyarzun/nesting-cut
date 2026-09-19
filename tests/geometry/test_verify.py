import pytest

from nesting.geometry.verify import placed_polygon, verify
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement


def square_part(part_id, side, holes=()):
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (side, 0.0), (side, side), (0.0, side)),
        holes=holes,
        entity_ids=(part_id,),
    )


def at(part_id, x, y, sheet=0, angle=0.0, mirror=False):
    return Placement(part_id, sheet, Transform(angle, mirror, x, y))


SHEET_W, SHEET_H = 1000.0, 1000.0


def test_a_single_well_placed_part_has_no_violations():
    parts = [square_part(0, 100.0)]
    placements = [at(0, 100.0, 100.0)]
    assert verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


def test_overlapping_parts_are_reported():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [at(0, 100.0, 100.0), at(1, 150.0, 150.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)

    assert len(violations) == 1
    assert violations[0].kind == "overlap"
    assert {violations[0].part_a, violations[0].part_b} == {0, 1}


def test_parts_closer_than_the_separation_are_reported():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    # Hay 3 mm de luz entre ellas, pero se pidieron 5.
    placements = [at(0, 100.0, 100.0), at(1, 203.0, 100.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)

    assert len(violations) == 1
    assert violations[0].kind == "separation"


def test_exactly_the_requested_separation_is_accepted():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [at(0, 100.0, 100.0), at(1, 205.0, 100.0)]
    assert verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


def test_a_part_outside_the_margin_is_reported():
    parts = [square_part(0, 100.0)]
    placements = [at(0, 5.0, 100.0)]   # el margen pedido es 10
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)

    assert len(violations) == 1
    assert violations[0].kind == "out_of_bounds"
    assert violations[0].part_a == 0


def test_a_part_past_the_far_edge_is_reported():
    parts = [square_part(0, 100.0)]
    placements = [at(0, 950.0, 100.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)
    assert [v.kind for v in violations] == ["out_of_bounds"]


def test_parts_on_different_sheets_never_collide():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [at(0, 100.0, 100.0, sheet=0), at(1, 100.0, 100.0, sheet=1)]
    assert verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


def test_a_part_nested_inside_a_hole_is_valid():
    """El aprovechamiento de agujeros de la spec 5.2, verificado de punta a punta."""
    ring = Part(
        id=0,
        outer=((0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)),
        holes=(((50.0, 50.0), (350.0, 50.0), (350.0, 350.0), (50.0, 350.0)),),
        entity_ids=(0,),
    )
    inner = square_part(1, 100.0)
    placements = [at(0, 100.0, 100.0), at(1, 250.0, 250.0)]

    assert verify([ring, inner], placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


def test_a_part_too_close_to_the_wall_of_a_hole_is_reported():
    ring = Part(
        id=0,
        outer=((0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)),
        holes=(((50.0, 50.0), (350.0, 50.0), (350.0, 350.0), (50.0, 350.0)),),
        entity_ids=(0,),
    )
    inner = square_part(1, 100.0)
    # La pieza interna queda a 2 mm de la pared del agujero.
    placements = [at(0, 100.0, 100.0), at(1, 152.0, 250.0)]
    violations = verify([ring, inner], placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)

    assert [v.kind for v in violations] == ["separation"]


def test_rotation_is_taken_into_account():
    """Rotada 45 grados, la diagonal se sale del margen."""
    parts = [square_part(0, 100.0)]
    placements = [at(0, 40.0, 500.0, angle=45.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)
    assert [v.kind for v in violations] == ["out_of_bounds"]


def test_placed_polygon_applies_the_transform_and_keeps_holes():
    ring = Part(
        id=0,
        outer=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
        holes=(((25.0, 25.0), (75.0, 25.0), (75.0, 75.0), (25.0, 75.0)),),
        entity_ids=(0,),
    )
    polygon = placed_polygon(ring, Transform(0.0, False, 10.0, 20.0))

    assert len(polygon.interiors) == 1
    assert polygon.area == 100.0 * 100.0 - 50.0 * 50.0
    assert polygon.bounds == (10.0, 20.0, 110.0, 120.0)


def test_every_violation_carries_a_readable_detail():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [at(0, 100.0, 100.0), at(1, 150.0, 150.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)
    assert violations[0].detail
    assert violations[0].sheet == 0


def test_an_excessive_margin_leaves_no_usable_area_on_a_square_sheet():
    """Reproduccion del hallazgo 1: margen 110 en una placa de 200x200.

    shapely.box() normaliza en silencio los limites invertidos y produce una
    franja fantasma en el centro de la placa; una pieza que cae ahi no puede
    pasar la verificacion con cero violaciones.
    """
    parts = [square_part(0, 20.0)]
    placements = [at(0, 90.0, 90.0)]
    violations = verify(parts, placements, 200.0, 200.0, sep=5.0, margin=110.0)

    assert [v.kind for v in violations] == ["out_of_bounds"]
    assert "área útil" in violations[0].detail or "area util" in violations[0].detail
    assert "no queda" in violations[0].detail


def test_an_excessive_margin_on_a_single_axis_is_still_caught():
    """Placa 1000x200 con margen 110: la franja fantasma invertida solo aparece en Y.

    La pieza cae de lleno en la franja Y invertida [90, 110] que shapely.box()
    produciria en silencio, aunque su holgura real a los bordes superior e
    inferior (95 mm y 85 mm) es menor que el margen pedido.
    """
    parts = [square_part(0, 10.0)]
    placements = [at(0, 500.0, 95.0)]
    violations = verify(parts, placements, 1000.0, 200.0, sep=5.0, margin=110.0)

    assert [v.kind for v in violations] == ["out_of_bounds"]


def test_a_margin_exactly_half_the_sheet_dimension_leaves_zero_usable_width():
    parts = [square_part(0, 20.0)]
    placements = [at(0, 100.0, 100.0)]
    violations = verify(parts, placements, 200.0, 200.0, sep=5.0, margin=100.0)

    assert [v.kind for v in violations] == ["out_of_bounds"]


def test_a_normal_margin_with_a_well_placed_part_still_has_no_violations():
    """El arreglo del hallazgo 1 no puede convertirse en un falso positivo."""
    parts = [square_part(0, 100.0)]
    placements = [at(0, 100.0, 100.0)]
    assert verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


def test_a_self_intersecting_outline_is_reported_as_invalid_geometry():
    bowtie = Part(
        id=0,
        outer=((0.0, 0.0), (100.0, 100.0), (100.0, 0.0), (0.0, 100.0)),
        holes=(),
        entity_ids=(0,),
    )
    placements = [at(0, 100.0, 100.0)]
    violations = verify([bowtie], placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)

    assert [v.kind for v in violations] == ["invalid_geometry"]
    assert "0" in violations[0].detail
    assert violations[0].part_a == 0


def test_a_well_placed_part_with_holes_still_has_no_violations():
    ring = Part(
        id=0,
        outer=((0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)),
        holes=(((50.0, 50.0), (350.0, 50.0), (350.0, 350.0), (50.0, 350.0)),),
        entity_ids=(0,),
    )
    inner = square_part(1, 100.0)
    placements = [at(0, 100.0, 100.0), at(1, 250.0, 250.0)]

    assert verify([ring, inner], placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


# --- Hallazgo 1b: umbral de area para el solapamiento ---


def test_two_parts_touching_on_a_shared_edge_with_zero_sep_is_not_a_violation():
    """Emula el ruido de punto flotante del hallazgo 1: dos piezas que deberian
    tocarse exactamente en un borde compartido terminan con una franja de
    interseccion minuscula (muy por debajo del umbral de area). Con sep=0 eso
    no debe reportarse como solapamiento ni como separacion insuficiente."""
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    # 1e-10 mm de solapamiento en X a lo largo de un borde compartido de
    # 100 mm: area ~1e-8 mm^2, muy por debajo de OVERLAP_AREA_THRESHOLD_MM2
    # (1e-6 mm^2) y del mismo orden que el ruido real de una rotacion de 90
    # grados sin corregir (~1e-11 mm^2).
    placements = [at(0, 100.0, 100.0), at(1, 200.0 - 1e-10, 100.0)]
    assert verify(parts, placements, SHEET_W, SHEET_H, sep=0.0, margin=10.0) == []


def test_a_small_but_real_overlap_is_still_reported():
    """Un solapamiento real del orden de 1 mm^2 tiene que seguir violando,
    muy por encima del umbral de ruido de punto flotante."""
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    # Las piezas se superponen en una franja de 1 mm x 1 mm = 1 mm^2.
    placements = [at(0, 100.0, 100.0), at(1, 199.0, 199.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=0.0, margin=10.0)

    assert [v.kind for v in violations] == ["overlap"]


def test_a_part_fully_contained_in_another_is_still_reported():
    parts = [square_part(0, 200.0), square_part(1, 50.0)]
    placements = [at(0, 100.0, 100.0), at(1, 110.0, 110.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=0.0, margin=10.0)

    assert [v.kind for v in violations] == ["overlap"]


# --- Hallazgo 1b: verify no debe confiar en un sep/margin negativo ---


def test_negative_sep_raises_value_error_instead_of_being_silently_ignored():
    parts = [square_part(0, 100.0)]
    placements = [at(0, 100.0, 100.0)]

    with pytest.raises(ValueError):
        verify(parts, placements, SHEET_W, SHEET_H, sep=-1.0, margin=10.0)


def test_negative_margin_raises_value_error_instead_of_extending_the_sheet():
    parts = [square_part(0, 100.0)]
    placements = [at(0, 100.0, 100.0)]

    with pytest.raises(ValueError):
        verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=-1.0)
