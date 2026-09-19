import math

from nesting.geometry.transform import apply_entity, apply_point, apply_points
from nesting.model.entities import Arc, Bezier, Circle, Line, Polyline, Style, Transform

STYLE = Style(aci=7, rgb=None, layer="0")


def approx(a, b, tol=1e-9):
    return abs(a - b) < tol


def test_identity_leaves_point_untouched():
    assert apply_point(Transform.identity(), (3.0, 4.0)) == (3.0, 4.0)


def test_translation():
    t = Transform(angle_deg=0.0, mirror=False, dx=10.0, dy=-5.0)
    assert apply_point(t, (1.0, 2.0)) == (11.0, -3.0)


def test_rotation_90_ccw():
    t = Transform(angle_deg=90.0, mirror=False, dx=0.0, dy=0.0)
    x, y = apply_point(t, (1.0, 0.0))
    assert approx(x, 0.0) and approx(y, 1.0)


def test_mirror_flips_x_only():
    t = Transform(angle_deg=0.0, mirror=True, dx=0.0, dy=0.0)
    assert apply_point(t, (3.0, 4.0)) == (-3.0, 4.0)


def test_mirror_happens_before_rotation():
    # Espejar (1,0) da (-1,0); rotarlo 90 CCW da (0,-1).
    t = Transform(angle_deg=90.0, mirror=True, dx=0.0, dy=0.0)
    x, y = apply_point(t, (1.0, 0.0))
    assert approx(x, 0.0) and approx(y, -1.0)


def test_mirroring_twice_is_identity():
    t = Transform(angle_deg=0.0, mirror=True, dx=0.0, dy=0.0)
    once = apply_point(t, (7.0, -2.0))
    twice = apply_point(t, once)
    assert twice == (7.0, -2.0)


def test_line_transforms_both_endpoints():
    t = Transform(angle_deg=0.0, mirror=False, dx=1.0, dy=1.0)
    line = apply_entity(t, Line((0.0, 0.0), (2.0, 3.0), STYLE))
    assert isinstance(line, Line)
    assert line.start == (1.0, 1.0)
    assert line.end == (3.0, 4.0)
    assert line.style is STYLE


def test_circle_keeps_radius():
    t = Transform(angle_deg=37.0, mirror=True, dx=5.0, dy=5.0)
    circle = apply_entity(t, Circle((0.0, 0.0), 4.0, STYLE))
    assert isinstance(circle, Circle)
    assert circle.radius == 4.0


def test_arc_rotation_adds_to_both_angles():
    t = Transform(angle_deg=30.0, mirror=False, dx=0.0, dy=0.0)
    arc = apply_entity(t, Arc((0.0, 0.0), 1.0, 0.0, 90.0, STYLE))
    assert isinstance(arc, Arc)
    assert approx(arc.start_angle, 30.0)
    assert approx(arc.end_angle, 120.0)


def test_arc_mirror_swaps_and_reflects_angles():
    # Reflejando x -> -x, un arco de 0 a 90 pasa a ir de 90 a 180.
    t = Transform(angle_deg=0.0, mirror=True, dx=0.0, dy=0.0)
    arc = apply_entity(t, Arc((0.0, 0.0), 1.0, 0.0, 90.0, STYLE))
    assert isinstance(arc, Arc)
    assert approx(arc.start_angle, 90.0)
    assert approx(arc.end_angle, 180.0)


def test_arc_endpoints_match_transformed_points():
    """El invariante que importa: los extremos del arco transformado son los
    extremos originales transformados."""
    t = Transform(angle_deg=57.0, mirror=True, dx=3.0, dy=-2.0)
    original = Arc((1.0, 1.0), 2.0, 20.0, 110.0, STYLE)
    moved = apply_entity(t, original)
    assert isinstance(moved, Arc)

    def endpoint(arc: Arc, angle: float) -> tuple[float, float]:
        rad = math.radians(angle)
        return (
            arc.center[0] + arc.radius * math.cos(rad),
            arc.center[1] + arc.radius * math.sin(rad),
        )

    expected_start = apply_point(t, endpoint(original, original.start_angle))
    expected_end = apply_point(t, endpoint(original, original.end_angle))
    # El espejado invierte el sentido, asi que los extremos se intercambian.
    got_start = endpoint(moved, moved.start_angle)
    got_end = endpoint(moved, moved.end_angle)

    assert approx(got_start[0], expected_end[0], 1e-9)
    assert approx(got_start[1], expected_end[1], 1e-9)
    assert approx(got_end[0], expected_start[0], 1e-9)
    assert approx(got_end[1], expected_start[1], 1e-9)


def test_bezier_transforms_all_four_control_points():
    t = Transform(angle_deg=0.0, mirror=False, dx=2.0, dy=0.0)
    bez = apply_entity(t, Bezier((0.0, 0.0), (1.0, 1.0), (2.0, 1.0), (3.0, 0.0), STYLE))
    assert isinstance(bez, Bezier)
    assert bez.p0 == (2.0, 0.0)
    assert bez.p3 == (5.0, 0.0)


def test_polyline_keeps_closed_flag():
    t = Transform(angle_deg=0.0, mirror=False, dx=0.0, dy=1.0)
    poly = apply_entity(t, Polyline(((0.0, 0.0), (1.0, 0.0)), True, STYLE))
    assert isinstance(poly, Polyline)
    assert poly.closed is True
    assert poly.points == ((0.0, 1.0), (1.0, 1.0))


def test_apply_points_returns_tuple():
    t = Transform(angle_deg=0.0, mirror=False, dx=1.0, dy=0.0)
    out = apply_points(t, [(0.0, 0.0), (1.0, 1.0)])
    assert out == ((1.0, 0.0), (2.0, 1.0))


def test_rotation_preserves_distances():
    t = Transform(angle_deg=123.456, mirror=True, dx=9.0, dy=-4.0)
    a, b = (0.0, 0.0), (3.0, 4.0)
    ta, tb = apply_point(t, a), apply_point(t, b)
    assert approx(math.dist(ta, tb), 5.0, 1e-9)


# --- Hallazgo 1: trigonometria exacta para multiplos de 90 grados ---


def test_90_degree_multiples_give_exact_coordinates():
    """math.cos(math.radians(90.0)) no es 0 exacto (6.123e-17); apply_point
    debe evitar ese ruido para los angulos de 0/90/180/270."""
    cases = {
        0.0: (1.0, 0.0),
        90.0: (0.0, 1.0),
        180.0: (-1.0, 0.0),
        270.0: (0.0, -1.0),
        360.0: (1.0, 0.0),
    }
    for angle, expected in cases.items():
        t = Transform(angle_deg=angle, mirror=False, dx=0.0, dy=0.0)
        assert apply_point(t, (1.0, 0.0)) == expected


def test_four_90_degree_rotations_return_exactly_to_the_original_point():
    t = Transform(angle_deg=90.0, mirror=False, dx=0.0, dy=0.0)
    p = (3.0, -2.0)
    for _ in range(4):
        p = apply_point(t, p)
    assert p == (3.0, -2.0)


def test_non_90_degree_multiples_still_use_ordinary_trigonometry():
    """Los angulos que no son multiplos de 90 no deben pasar por la tabla
    exacta, y siguen comportandose como antes (aproximados via math.cos/sin)."""
    t = Transform(angle_deg=45.0, mirror=False, dx=0.0, dy=0.0)
    x, y = apply_point(t, (1.0, 0.0))
    expected = math.sqrt(2.0) / 2.0
    assert approx(x, expected) and approx(y, expected)

    t37 = Transform(angle_deg=37.0, mirror=False, dx=0.0, dy=0.0)
    x37, y37 = apply_point(t37, (1.0, 0.0))
    rad37 = math.radians(37.0)
    assert approx(x37, math.cos(rad37)) and approx(y37, math.sin(rad37))


# --- Los arcos de una polilínea (`bulges`) tienen que moverse con ella. El
# espejado es el caso que importa: invierte el sentido de giro, y el signo
# del bulge ES el sentido de giro. ---

ARCO = Polyline(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0)), True, STYLE,
                bulges=(0.5, 0.0, -0.25))


def test_a_rotation_leaves_the_bulges_alone():
    movido = apply_entity(Transform(37.0, False, 5.0, -2.0), ARCO)
    assert movido.bulges == ARCO.bulges


def test_mirroring_flips_the_sign_of_every_bulge():
    espejado = apply_entity(Transform(0.0, True, 0.0, 0.0), ARCO)
    assert espejado.bulges == (-0.5, 0.0, 0.25)


def test_flattening_commutes_with_the_transform():
    """La invariante que sostiene todo: aplanar y después mover tiene que dar
    lo mismo que mover y después aplanar. Si no, el motor mide una cosa, el
    verificador otra y el archivo de salida trae una tercera."""
    from nesting.geometry.flatten import flatten

    for t in (Transform(0.0, False, 0.0, 0.0),
              Transform(90.0, False, 12.0, -3.0),
              Transform(37.0, True, -5.0, 8.0),
              Transform(180.0, True, 0.0, 0.0)):
        movido_despues = apply_points(t, flatten(ARCO, tolerance=0.01))
        movido_antes = flatten(apply_entity(t, ARCO), tolerance=0.01)

        assert len(movido_antes) == len(movido_despues), t
        for a, b in zip(movido_antes, movido_despues):
            assert approx(a[0], b[0], 1e-9) and approx(a[1], b[1], 1e-9), (t, a, b)
