import math

import pytest

from nesting.geometry.flatten import flatten
from nesting.model.entities import Arc, Bezier, Circle, Line, Polyline, Style

STYLE = Style(aci=7, rgb=None, layer="0")


def max_deviation_from_circle(points, center, radius):
    """Mayor error radial de los puntos y de los puntos medios de cada cuerda."""
    worst = 0.0
    for p in points:
        worst = max(worst, abs(math.dist(p, center) - radius))
    for a, b in zip(points, points[1:]):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        worst = max(worst, abs(math.dist(mid, center) - radius))
    return worst


def test_line_returns_its_two_endpoints():
    pts = flatten(Line((0.0, 0.0), (3.0, 4.0), STYLE), tolerance=0.1)
    assert pts == ((0.0, 0.0), (3.0, 4.0))


def test_open_polyline_returns_its_points():
    poly = Polyline(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), closed=False, style=STYLE)
    assert flatten(poly, tolerance=0.1) == ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))


def test_closed_polyline_repeats_first_point_at_the_end():
    poly = Polyline(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)), closed=True, style=STYLE)
    pts = flatten(poly, tolerance=0.1)
    assert pts[-1] == pts[0]
    assert len(pts) == 4


def test_circle_does_not_repeat_the_first_point():
    pts = flatten(Circle((0.0, 0.0), 10.0, STYLE), tolerance=0.05)
    assert pts[0] != pts[-1]


def test_circle_respects_the_tolerance():
    center, radius, tol = (5.0, -3.0), 50.0, 0.05
    pts = flatten(Circle(center, radius, STYLE), tolerance=tol)
    ring = pts + (pts[0],)
    assert max_deviation_from_circle(ring, center, radius) <= tol + 1e-9


def test_circle_has_at_least_eight_segments_even_with_a_loose_tolerance():
    pts = flatten(Circle((0.0, 0.0), 1.0, STYLE), tolerance=100.0)
    assert len(pts) >= 8


def test_tighter_tolerance_produces_more_points():
    coarse = flatten(Circle((0.0, 0.0), 100.0, STYLE), tolerance=1.0)
    fine = flatten(Circle((0.0, 0.0), 100.0, STYLE), tolerance=0.01)
    assert len(fine) > len(coarse)


def test_arc_starts_and_ends_exactly_on_its_endpoints():
    arc = Arc((0.0, 0.0), 10.0, 0.0, 90.0, STYLE)
    pts = flatten(arc, tolerance=0.01)
    assert pts[0] == pytest.approx((10.0, 0.0), abs=1e-9)
    assert pts[-1] == pytest.approx((0.0, 10.0), abs=1e-9)


def test_arc_respects_the_tolerance():
    center, radius, tol = (0.0, 0.0), 80.0, 0.02
    pts = flatten(Arc(center, radius, 10.0, 200.0, STYLE), tolerance=tol)
    assert max_deviation_from_circle(pts, center, radius) <= tol + 1e-9


def test_arc_crossing_zero_degrees():
    """Un arco de 350 a 10 grados barre 20 grados, no 340."""
    pts = flatten(Arc((0.0, 0.0), 10.0, 350.0, 10.0, STYLE), tolerance=0.01)
    assert pts[0] == pytest.approx((10.0 * math.cos(math.radians(350)),
                                    10.0 * math.sin(math.radians(350))), abs=1e-9)
    assert pts[-1] == pytest.approx((10.0 * math.cos(math.radians(10)),
                                     10.0 * math.sin(math.radians(10))), abs=1e-9)
    # 20 grados con tolerancia fina no deberia necesitar muchisimos puntos.
    assert len(pts) < 50


def test_bezier_starts_and_ends_on_its_control_endpoints():
    bez = Bezier((0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), STYLE)
    pts = flatten(bez, tolerance=0.01)
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (10.0, 0.0)


def test_straight_bezier_collapses_to_two_points():
    """Si los controles estan sobre la cuerda, no hace falta subdividir."""
    bez = Bezier((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), STYLE)
    assert flatten(bez, tolerance=0.1) == ((0.0, 0.0), (3.0, 0.0))


def test_bezier_respects_the_tolerance():
    """Se compara contra una evaluacion densa de la curva real."""
    bez = Bezier((0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0), STYLE)
    tol = 0.05
    pts = flatten(bez, tolerance=tol)

    def evaluate(t):
        u = 1 - t
        return (
            u**3 * bez.p0[0] + 3 * u**2 * t * bez.p1[0] + 3 * u * t**2 * bez.p2[0] + t**3 * bez.p3[0],
            u**3 * bez.p0[1] + 3 * u**2 * t * bez.p1[1] + 3 * u * t**2 * bez.p2[1] + t**3 * bez.p3[1],
        )

    def distance_to_polyline(p):
        best = float("inf")
        for a, b in zip(pts, pts[1:]):
            best = min(best, _point_segment_distance(p, a, b))
        return best

    worst = max(distance_to_polyline(evaluate(i / 500)) for i in range(501))
    assert worst <= tol + 1e-9


def _point_segment_distance(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_squared))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def test_rejects_non_positive_tolerance():
    with pytest.raises(ValueError):
        flatten(Circle((0.0, 0.0), 1.0, STYLE), tolerance=0.0)


def _bezier_max_deviation(bez, pts, samples=2000):
    """Mayor distancia entre la curva real (muestreada densamente) y la polilinea."""

    def evaluate(t):
        u = 1 - t
        return (
            u**3 * bez.p0[0] + 3 * u**2 * t * bez.p1[0] + 3 * u * t**2 * bez.p2[0] + t**3 * bez.p3[0],
            u**3 * bez.p0[1] + 3 * u**2 * t * bez.p1[1] + 3 * u * t**2 * bez.p2[1] + t**3 * bez.p3[1],
        )

    def distance_to_polyline(p):
        best = float("inf")
        for a, b in zip(pts, pts[1:]):
            best = min(best, _point_segment_distance(p, a, b))
        return best

    return max(distance_to_polyline(evaluate(i / samples)) for i in range(samples + 1))


@pytest.mark.parametrize("tolerance", [0.001, 0.5])
def test_bezier_collinear_cusp_respects_the_tolerance(tolerance):
    """Caso del hallazgo: controles colineales con la cuerda pero mas alla de p3.

    Con distancia a la recta infinita, ambos controles caian sobre la recta y el
    test de planitud aprobaba de una, aunque la curva real se proyecta bien lejos
    del segmento p0-p3.
    """
    bez = Bezier((0.0, 0.0), (30.0, 0.0), (-30.0, 0.0), (0.0, 0.0), STYLE)
    pts = flatten(bez, tolerance=tolerance)
    assert _bezier_max_deviation(bez, pts) <= tolerance + 1e-9


@pytest.mark.parametrize("tolerance", [0.001, 0.5])
def test_bezier_collinear_cusp_smaller_variant_respects_the_tolerance(tolerance):
    bez = Bezier((0.0, 0.0), (5.0, 0.0), (-5.0, 0.0), (0.0, 0.0), STYLE)
    pts = flatten(bez, tolerance=tolerance)
    assert _bezier_max_deviation(bez, pts) <= tolerance + 1e-9


@pytest.mark.parametrize("tolerance", [0.001, 0.5])
def test_bezier_with_a_real_loop_respects_the_tolerance(tolerance):
    """Controles cruzados (no colineales) que producen un bucle real en la curva."""
    bez = Bezier((0.0, 0.0), (10.0, 10.0), (-10.0, 10.0), (0.0, 0.0), STYLE)
    pts = flatten(bez, tolerance=tolerance)
    assert _bezier_max_deviation(bez, pts) <= tolerance + 1e-9


@pytest.mark.parametrize("tolerance", [0.001, 0.5])
def test_degenerate_bezier_with_coincident_controls_does_not_overflow(tolerance):
    """Los cuatro puntos de control iguales: la curva es un punto, no debe reventar."""
    bez = Bezier((3.0, 4.0), (3.0, 4.0), (3.0, 4.0), (3.0, 4.0), STYLE)
    pts = flatten(bez, tolerance=tolerance)
    assert pts[0] == (3.0, 4.0)
    assert pts[-1] == (3.0, 4.0)
    assert _bezier_max_deviation(bez, pts) <= tolerance + 1e-9


def test_full_circle_arc_has_at_least_eight_segments_even_with_a_loose_tolerance():
    """Un Arc de barrido completo (0 a 360) no debe colapsar a casi 2 puntos."""
    arc = Arc((0.0, 0.0), 1.0, 0.0, 360.0, STYLE)
    pts = flatten(arc, tolerance=100.0)
    assert len(pts) >= 8
