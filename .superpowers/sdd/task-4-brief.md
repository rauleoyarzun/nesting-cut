### Task 4: Aplanado de curvas (`geometry/flatten.py`)

**Files:**
- Create: `src/nesting/geometry/flatten.py`
- Test: `tests/geometry/test_flatten.py`

**Interfaces:**
- Consumes: las primitivas de `nesting.model.entities` (Task 2)
- Produces: `flatten(e: Entity, tolerance: float) -> tuple[tuple[float, float], ...]`
  - Devuelve la polilínea que aproxima `e`, **incluyendo ambos extremos**.
  - Para `Circle` devuelve el anillo **sin repetir** el primer punto al final.
  - Garantía: la desviación máxima entre la curva real y la polilínea es ≤ `tolerance` (en mm).

**Este es el único lugar del proyecto donde se introduce aproximación geométrica.** Por eso la tolerancia es explícita y está testeada con una cota medible, no "a ojo".

**Fórmula para arcos y círculos.** Un arco de radio `r` partido en segmentos que abarcan `δ` radianes tiene una flecha (sagita) máxima de `r · (1 - cos(δ/2))`. Igualando a la tolerancia: `δ = 2 · arccos(1 - tol/r)`. La cantidad de segmentos es `ceil(barrido / δ)`. Si `tol ≥ r` el arco entero cabe en un segmento, pero igual se fuerza un mínimo de 8 segmentos por círculo completo para que las piezas no se vuelvan polígonos groseros.

**Método para Béziers: subdivisión recursiva con test de planitud.** Un Bézier cúbico está dentro de `tol` de su cuerda `p0→p3` cuando ambos puntos de control `p1` y `p2` están a distancia ≤ `tol` de esa recta. Es una condición conservadora (la curva siempre está dentro del casco convexo de sus controles), así que la garantía se cumple. Si no es plano, se subdivide en el parámetro medio por el algoritmo de De Casteljau y se recurre.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/geometry/test_flatten.py`:

```python
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
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/geometry/test_flatten.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.geometry.flatten'`.

- [ ] **Step 3: Escribir la implementación**

Archivo `src/nesting/geometry/flatten.py`:

```python
"""Curve -> polyline conversion with a bounded chord error.

This is the only place in the project that introduces geometric approximation,
which is why the tolerance is explicit and guaranteed rather than incidental.
The result feeds the nesting engine and the verifier; the output file is always
written from the exact entities instead.
"""

import math

from nesting.model.entities import Arc, Bezier, Circle, Entity, Line, Point, Polyline

MIN_CIRCLE_SEGMENTS = 8
"""A full circle never gets fewer segments than this, however loose the tolerance."""


def flatten(e: Entity, tolerance: float) -> tuple[Point, ...]:
    """Approximate `e` by a polyline whose deviation is at most `tolerance` mm.

    Both endpoints are always included. A `Circle` is returned as a ring whose
    first point is *not* repeated at the end; a closed `Polyline` does repeat it,
    matching how each one is normally consumed.
    """
    if tolerance <= 0.0:
        raise ValueError(f"la tolerancia debe ser positiva, se recibio {tolerance}")

    match e:
        case Line():
            return (e.start, e.end)

        case Polyline():
            if e.closed and e.points and e.points[0] != e.points[-1]:
                return tuple(e.points) + (e.points[0],)
            return tuple(e.points)

        case Circle():
            count = _segment_count(e.radius, 2 * math.pi, tolerance)
            count = max(count, MIN_CIRCLE_SEGMENTS)
            step = 2 * math.pi / count
            return tuple(
                (e.center[0] + e.radius * math.cos(i * step),
                 e.center[1] + e.radius * math.sin(i * step))
                for i in range(count)
            )

        case Arc():
            sweep = math.radians((e.end_angle - e.start_angle) % 360.0)
            if sweep == 0.0:
                sweep = 2 * math.pi
            count = _segment_count(e.radius, sweep, tolerance)
            start = math.radians(e.start_angle)
            step = sweep / count
            return tuple(
                (e.center[0] + e.radius * math.cos(start + i * step),
                 e.center[1] + e.radius * math.sin(start + i * step))
                for i in range(count + 1)
            )

        case Bezier():
            out: list[Point] = [e.p0]
            _subdivide_bezier(e.p0, e.p1, e.p2, e.p3, tolerance, out, depth=0)
            return tuple(out)

    raise TypeError(f"unsupported entity type: {type(e).__name__}")


def _segment_count(radius: float, sweep: float, tolerance: float) -> int:
    """Segments needed so the sagitta of each one stays within `tolerance`.

    A chord spanning `delta` radians on a circle of radius `r` bulges away from
    the arc by `r * (1 - cos(delta / 2))`. Solving for `delta` gives the widest
    step allowed.
    """
    if radius <= 0.0:
        return 1
    ratio = 1.0 - tolerance / radius
    if ratio <= -1.0:
        return 1
    delta = 2.0 * math.acos(max(-1.0, min(1.0, ratio)))
    if delta <= 0.0:
        return 1
    return max(1, math.ceil(sweep / delta))


MAX_BEZIER_DEPTH = 24
"""Recursion guard. At this depth a segment is 1/16M of the curve; a degenerate
curve that never passes the flatness test stops here instead of overflowing."""


def _subdivide_bezier(
    p0: Point, p1: Point, p2: Point, p3: Point,
    tolerance: float, out: list[Point], depth: int,
) -> None:
    """Append the flattened curve to `out`, excluding `p0` and including `p3`."""
    if depth >= MAX_BEZIER_DEPTH or _is_flat(p0, p1, p2, p3, tolerance):
        out.append(p3)
        return

    # De Casteljau split at t = 0.5.
    p01 = _midpoint(p0, p1)
    p12 = _midpoint(p1, p2)
    p23 = _midpoint(p2, p3)
    p012 = _midpoint(p01, p12)
    p123 = _midpoint(p12, p23)
    mid = _midpoint(p012, p123)

    _subdivide_bezier(p0, p01, p012, mid, tolerance, out, depth + 1)
    _subdivide_bezier(mid, p123, p23, p3, tolerance, out, depth + 1)


def _is_flat(p0: Point, p1: Point, p2: Point, p3: Point, tolerance: float) -> bool:
    """True when both control points lie within `tolerance` of the chord p0-p3.

    A Bezier curve is contained in the convex hull of its control points, so this
    is conservative: passing it guarantees the real deviation is within tolerance.
    """
    return (
        _point_line_distance(p1, p0, p3) <= tolerance
        and _point_line_distance(p2, p0, p3) <= tolerance
    )


def _point_line_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length == 0.0:
        return math.dist(p, a)
    return abs((p[0] - ax) * dy - (p[1] - ay) * dx) / length


def _midpoint(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/geometry/test_flatten.py -v`
Esperado: `14 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/geometry/flatten.py tests/geometry/test_flatten.py
git commit -m "feat: aplanado de curvas con error de cuerda acotado"
```

---

