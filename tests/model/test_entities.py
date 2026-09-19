import dataclasses

import pytest

from nesting.model.entities import (
    Arc,
    Bezier,
    Circle,
    Entity,
    Line,
    Polyline,
    Style,
    Transform,
)

STYLE = Style(aci=1, rgb=(255, 0, 0), layer="CORTE")


def test_style_is_frozen_and_hashable():
    assert hash(STYLE) is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        STYLE.layer = "OTRA"


def test_line_holds_endpoints_and_style():
    line = Line(start=(0.0, 0.0), end=(10.0, 5.0), style=STYLE)
    assert line.start == (0.0, 0.0)
    assert line.end == (10.0, 5.0)
    assert line.style.layer == "CORTE"


def test_arc_angles_are_degrees_ccw():
    arc = Arc(center=(0.0, 0.0), radius=5.0, start_angle=0.0, end_angle=90.0, style=STYLE)
    assert arc.start_angle == 0.0
    assert arc.end_angle == 90.0


def test_circle_and_bezier_and_polyline():
    circle = Circle(center=(1.0, 2.0), radius=3.0, style=STYLE)
    bezier = Bezier(p0=(0.0, 0.0), p1=(1.0, 1.0), p2=(2.0, 1.0), p3=(3.0, 0.0), style=STYLE)
    poly = Polyline(points=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), closed=True, style=STYLE)

    assert circle.radius == 3.0
    assert bezier.p3 == (3.0, 0.0)
    assert poly.closed is True
    assert len(poly.points) == 3


def test_every_primitive_is_an_entity():
    primitives = [
        Line((0.0, 0.0), (1.0, 1.0), STYLE),
        Arc((0.0, 0.0), 1.0, 0.0, 90.0, STYLE),
        Circle((0.0, 0.0), 1.0, STYLE),
        Bezier((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), STYLE),
        Polyline(((0.0, 0.0), (1.0, 0.0)), False, STYLE),
    ]
    for primitive in primitives:
        assert isinstance(primitive, Entity)


def test_transform_identity():
    identity = Transform.identity()
    assert identity.angle_deg == 0.0
    assert identity.mirror is False
    assert identity.dx == 0.0
    assert identity.dy == 0.0


# --- Un tramo de polilínea puede ser un arco: es como el DXF guarda un
# contorno con curvas en UNA entidad, sin nodos intermedios. `bulges` nace
# vacío, que significa "todo recto" -- el comportamiento de siempre. ---


def test_a_polyline_has_no_bulges_by_default():
    polyline = Polyline(((0.0, 0.0), (10.0, 0.0)), False, STYLE)
    assert polyline.bulges == ()


def test_a_bulge_per_vertex_is_accepted():
    polyline = Polyline(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0)), True, STYLE,
                        bulges=(0.0, 1.0, 0.0))
    assert polyline.bulges == (0.0, 1.0, 0.0)


def test_a_wrong_number_of_bulges_is_rejected():
    """Callar un desajuste acá deja tramos con la curvatura de otro."""
    with pytest.raises(ValueError, match="bulges"):
        Polyline(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0)), True, STYLE, bulges=(1.0,))
