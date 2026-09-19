### Task 3: Transformación rígida exacta (`geometry/transform.py`)

**Files:**
- Create: `src/nesting/geometry/__init__.py`
- Create: `src/nesting/geometry/transform.py`
- Test: `tests/geometry/test_transform.py`

**Interfaces:**
- Consumes: `Transform`, `Entity` y las cinco primitivas de `nesting.model.entities` (Task 2)
- Produces:
  - `apply_point(t: Transform, p: tuple[float, float]) -> tuple[float, float]`
  - `apply_entity(t: Transform, e: Entity) -> Entity`
  - `apply_points(t: Transform, pts: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]`

**El caso delicado es `Arc`.** Un arco DXF siempre barre en sentido antihorario de `start_angle` a `end_angle`. Bajo rotación de θ los dos ángulos suman θ. Bajo reflexión `x → -x`, un punto en ángulo α va a `180° - α`, lo que **invierte el sentido de barrido**: para que el arco siga siendo CCW hay que intercambiar los extremos. O sea `(start, end) → (180 - end, 180 - start)`. Si esto se hace mal, los arcos salen "al revés" en el DXF final y el corte queda mal: por eso tiene test propio.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/geometry/test_transform.py` (crear también `tests/geometry/__init__.py` vacío):

```python
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
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/geometry/test_transform.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.geometry'`.

- [ ] **Step 3: Escribir la implementación**

Archivo `src/nesting/geometry/__init__.py`: vacío.

Archivo `src/nesting/geometry/transform.py`:

```python
"""The single definition of what a rigid transform does to geometry.

Everything that moves a part goes through here, so that the raster engine, the
verifier and the DXF writer can never disagree about what "rotated 90 degrees
and mirrored" means.
"""

import math
from collections.abc import Sequence

from nesting.model.entities import (
    Arc,
    Bezier,
    Circle,
    Entity,
    Line,
    Point,
    Polyline,
    Transform,
)


def apply_point(t: Transform, p: Point) -> Point:
    """Apply `t` to a single point: mirror, then rotate, then translate."""
    x, y = p
    if t.mirror:
        x = -x
    rad = math.radians(t.angle_deg)
    cos, sin = math.cos(rad), math.sin(rad)
    return (x * cos - y * sin + t.dx, x * sin + y * cos + t.dy)


def apply_points(t: Transform, pts: Sequence[Point]) -> tuple[Point, ...]:
    return tuple(apply_point(t, p) for p in pts)


def apply_entity(t: Transform, e: Entity) -> Entity:
    """Apply `t` to an entity, keeping its exact representation and style."""
    match e:
        case Line():
            return Line(apply_point(t, e.start), apply_point(t, e.end), e.style)

        case Circle():
            return Circle(apply_point(t, e.center), e.radius, e.style)

        case Arc():
            start, end = e.start_angle, e.end_angle
            if t.mirror:
                # Reflecting x -> -x maps angle a to 180 - a, which reverses the
                # sweep direction. DXF arcs are always counter-clockwise, so the
                # endpoints must be swapped to keep that invariant.
                start, end = 180.0 - end, 180.0 - start
            return Arc(
                center=apply_point(t, e.center),
                radius=e.radius,
                start_angle=_normalize_degrees(start + t.angle_deg),
                end_angle=_normalize_degrees(end + t.angle_deg),
                style=e.style,
            )

        case Bezier():
            return Bezier(
                apply_point(t, e.p0),
                apply_point(t, e.p1),
                apply_point(t, e.p2),
                apply_point(t, e.p3),
                e.style,
            )

        case Polyline():
            return Polyline(apply_points(t, e.points), e.closed, e.style)

    raise TypeError(f"unsupported entity type: {type(e).__name__}")


def _normalize_degrees(a: float) -> float:
    """Fold an angle into [0, 360)."""
    return a % 360.0
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/geometry/test_transform.py -v`
Esperado: `15 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/geometry tests/geometry
git commit -m "feat: transformacion rigida exacta sobre entidades"
```

---

