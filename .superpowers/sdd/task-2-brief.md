### Task 2: Primitivas geométricas (`model/entities.py`)

**Files:**
- Create: `src/nesting/model/__init__.py`
- Create: `src/nesting/model/entities.py`
- Test: `tests/model/test_entities.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `Style(aci: int | None, rgb: tuple[int, int, int] | None, layer: str)`
  - `Line(start, end, style)` · `Arc(center, radius, start_angle, end_angle, style)` · `Circle(center, radius, style)` · `Bezier(p0, p1, p2, p3, style)` · `Polyline(points, closed, style)`
  - `Entity` — alias de unión de los cinco tipos anteriores
  - `Transform(angle_deg: float, mirror: bool, dx: float, dy: float)` con `Transform.identity()`

**Decisión de diseño:** el modelo **no** incluye `Ellipse` ni `Spline`. Los lectores convierten `ELLIPSE` y `SPLINE` a cadenas de `Bezier` cúbicas. Motivo: `Line`, `Arc`, `Circle`, `Bezier` y `Polyline` son todas **exactas bajo transformación rígida**; una elipse con ejes y parámetros no lo es sin código delicado. Un Bézier cúbico es exactamente un SPLINE de grado 3 en DXF, así que la ida y vuelta no pierde nada.

**Orden de la transformación:** primero espejar (reflexión `x → -x`), después rotar `angle_deg` CCW alrededor del origen, después trasladar `(dx, dy)`. Cualquier reflexión sobre cualquier eje se expresa como esta composición, así que un solo booleano alcanza.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/model/test_entities.py` (crear también `tests/model/__init__.py` vacío):

```python
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
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/model/test_entities.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.model'`.

- [ ] **Step 3: Escribir la implementación mínima**

Archivo `src/nesting/model/__init__.py`: vacío.

Archivo `src/nesting/model/entities.py`:

```python
"""Geometric primitives shared by every reader, the engine and the writer.

Only primitives that are *exact* under a rigid transform live here. Readers
convert ELLIPSE and SPLINE entities into chains of cubic `Bezier` segments.
"""

from dataclasses import dataclass

Point = tuple[float, float]


@dataclass(frozen=True)
class Style:
    """Source colour and layer, carried through untouched to the output."""

    aci: int | None
    """AutoCAD Color Index (1-255, 256 = BYLAYER). None when the source had no ACI."""

    rgb: tuple[int, int, int] | None
    """True colour. None when the source only specified an ACI."""

    layer: str


@dataclass(frozen=True)
class Line:
    start: Point
    end: Point
    style: Style


@dataclass(frozen=True)
class Arc:
    """Circular arc, swept counter-clockwise from `start_angle` to `end_angle`."""

    center: Point
    radius: float
    start_angle: float
    """Degrees, counter-clockwise from +X."""

    end_angle: float
    """Degrees, counter-clockwise from +X."""

    style: Style


@dataclass(frozen=True)
class Circle:
    center: Point
    radius: float
    style: Style


@dataclass(frozen=True)
class Bezier:
    """Cubic Bezier segment."""

    p0: Point
    p1: Point
    p2: Point
    p3: Point
    style: Style


@dataclass(frozen=True)
class Polyline:
    points: tuple[Point, ...]
    closed: bool
    style: Style


Entity = Line | Arc | Circle | Bezier | Polyline


@dataclass(frozen=True)
class Transform:
    """A rigid transform, applied in this order: mirror, rotate, translate.

    `mirror` reflects across the Y axis (x -> -x). Any reflection about any
    axis can be written as this reflection followed by a rotation, so a single
    boolean is enough.
    """

    angle_deg: float
    mirror: bool
    dx: float
    dy: float

    @staticmethod
    def identity() -> "Transform":
        return Transform(angle_deg=0.0, mirror=False, dx=0.0, dy=0.0)
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/model/test_entities.py -v`
Esperado: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/model tests/model
git commit -m "feat: primitivas geometricas y tipo Transform"
```

---

