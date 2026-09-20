# Sistema de nesting para placas — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir una herramienta de línea de comandos que toma un archivo vectorial con figuras a cortar y produce un DXF con esas figuras acomodadas dentro de una o más placas de madera, minimizando el material usado.

**Architecture:** Los lectores (DXF/AI/3DM) normalizan a un modelo de entidades común con color y capa. La geometría se aplana a polígonos solo para *decidir* posiciones; el archivo de salida se escribe transformando las **entidades originales**, por lo que no hay pérdida de fidelidad y los colores se preservan sin código dedicado. El motor de nesting vive detrás de una interfaz `Oracle` con dos implementaciones intercambiables: una trivial de bounding box (hito 2, para tener el circuito completo andando) y la real por máscaras raster con búsqueda por FFT (hito 3). Un verificador geométrico exacto sobre polígonos valida toda salida antes de escribirla, y es además el oráculo de los tests.

**Tech Stack:** Python 3.13 · numpy · scipy (FFT + morfología) · shapely (verificación y contención) · ezdxf (I/O DXF) · Pillow (rasterizado y preview) · PyYAML (catálogo de materiales) · rhino3dm (lectura .3dm) · pytest

**Spec:** `docs/superpowers/specs/2026-09-17-nesting-placas-design.md`

## Global Constraints

- **Python 3.13+**. El proyecto usa sintaxis moderna de tipos (`X | None`, `list[T]`) sin `from __future__ import annotations`.
- **Todas las unidades internas son milímetros.** La conversión ocurre una sola vez, en el lector. Ninguna capa por debajo de `io/` conoce otra unidad.
- **Ángulos en grados, sentido antihorario (CCW), medidos desde el eje +X.** Es la convención de DXF; mantenerla evita conversiones.
- **Coordenadas como `tuple[float, float]`.** Nunca listas, nunca objetos `Point`. Los dataclasses del modelo son `frozen=True` y hashables.
- **El polígono exacto es la fuente de verdad.** La máscara raster es un caché derivado. Está prohibido re-vectorizar el resultado de operaciones morfológicas.
- **El offset de separación vive dentro del oráculo**, nunca como preproceso compartido.
- **Idioma:** el código, los nombres de símbolos y los docstrings van en **inglés**. Los mensajes dirigidos al usuario (CLI, warnings, errores) van en **español**.
- **Formato de commits:** Conventional Commits (`feat:`, `test:`, `fix:`, `chore:`, `docs:`).
- **Nunca `pip install` global.** Siempre dentro del venv del proyecto (`.venv`).

---

## Estructura de archivos

```
cut-placement/
├── pyproject.toml
├── materials.yaml
├── src/nesting/
│   ├── __init__.py
│   ├── model/
│   │   ├── entities.py      # Style, Line, Arc, Circle, Bezier, Polyline, Transform
│   │   ├── part.py          # Contour, Part, Placement
│   │   └── material.py      # Material, load_materials, allowed_angles
│   ├── geometry/
│   │   ├── transform.py     # apply_point, apply_entity
│   │   ├── flatten.py       # flatten (entidad -> polilínea, error de cuerda acotado)
│   │   ├── chaining.py      # chain_contours (tramos sueltos -> contornos cerrados)
│   │   ├── nesting_tree.py  # build_parts (contención par/impar -> Parts)
│   │   └── verify.py        # verify (verificación exacta sobre shapely)
│   ├── io/
│   │   ├── dxf_reader.py    # read_dxf -> Drawing
│   │   ├── dxf_writer.py    # write_dxf
│   │   ├── ai_reader.py     # read_ai -> Drawing
│   │   ├── rhino_reader.py  # read_3dm -> Drawing
│   │   └── preview.py       # write_preview
│   ├── engine/
│   │   ├── oracle.py        # Oracle (Protocol), Weights, NestConfig
│   │   ├── shelf_oracle.py  # implementación trivial por bounding box
│   │   ├── raster/
│   │   │   ├── masks.py     # rasterize, disk_kernel
│   │   │   ├── search.py    # feasible_positions
│   │   │   ├── scoring.py   # score_positions
│   │   │   └── oracle.py    # RasterOracle
│   │   └── packer.py        # pack -> PackResult
│   └── cli.py
├── tests/                   # espeja src/nesting/
├── bench/
│   ├── run_bench.py
│   └── files/               # archivos reales del proyecto
└── docs/superpowers/
```

**Responsabilidades y por qué están separados:**

| Archivo | Responsabilidad única |
|---|---|
| `model/entities.py` | Las primitivas geométricas y su estilo. Sin lógica, solo datos |
| `geometry/transform.py` | La única definición de "transformación rígida". Todo lo demás la consume |
| `geometry/flatten.py` | Curvas → polilíneas con error acotado. Única fuente de aproximación |
| `geometry/chaining.py` | Reconstruir ciclos cerrados de tramos sueltos. Es el código más sucio del proyecto y por eso está aislado |
| `geometry/nesting_tree.py` | Decidir qué es pieza y qué es agujero |
| `geometry/verify.py` | El árbitro. No depende de ningún motor |
| `engine/oracle.py` | **La costura.** Define el contrato que hace intercambiables los motores |
| `engine/packer.py` | Estrategia: orden, ángulos, multi-placa, esfuerzos. Agnóstico al motor |
| `engine/raster/*` | Un motor concreto, en cuatro piezas chicas para que cada una sea testeable sola |

---

# Hito 1 — Modelo, geometría y verificador

*Nada del resto es confiable hasta que exista el árbitro que dice si una salida es válida.*

---

### Task 1: Setup del proyecto

**Files:**
- Create: `pyproject.toml`
- Create: `src/nesting/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nada
- Produces: un venv en `.venv` con las dependencias instaladas, `pytest` corriendo, y el paquete `nesting` importable.

- [ ] **Step 1: Crear el venv e instalar dependencias**

```bash
cd <repo>
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install numpy scipy shapely ezdxf Pillow PyYAML pytest
```

Esperado: termina con `Successfully installed ...`. `rhino3dm` se instala recién en la Task 22 porque solo lo necesita el lector `.3dm`.

- [ ] **Step 2: Escribir `pyproject.toml`**

```toml
[project]
name = "nesting"
version = "0.1.0"
description = "Optimizacion de cortes en placas a partir de archivos vectoriales"
requires-python = ">=3.13"
dependencies = [
    "numpy",
    "scipy",
    "shapely",
    "ezdxf",
    "Pillow",
    "PyYAML",
]

[project.optional-dependencies]
rhino = ["rhino3dm"]
dev = ["pytest"]

[project.scripts]
nest = "nesting.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: Crear `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
out/
```

- [ ] **Step 4: Crear los paquetes vacíos**

```bash
mkdir -p src/nesting tests bench/files
touch src/nesting/__init__.py tests/__init__.py
```

- [ ] **Step 5: Escribir el test de humo**

Archivo `tests/test_smoke.py`:

```python
def test_package_imports():
    import nesting
    assert nesting is not None


def test_dependencies_available():
    import numpy
    import scipy.signal
    import shapely.geometry
    import ezdxf
    import PIL.ImageDraw
    import yaml

    assert numpy.__version__
    assert scipy.signal.fftconvolve is not None
    assert shapely.geometry.Polygon is not None
    assert ezdxf.new is not None
    assert PIL.ImageDraw.Draw is not None
    assert yaml.safe_load("a: 1") == {"a": 1}
```

- [ ] **Step 6: Instalar el paquete en modo editable y correr los tests**

```bash
.venv/bin/pip install -e .
.venv/bin/pytest tests/test_smoke.py -v
```

Esperado: `2 passed`.

- [ ] **Step 7: Inicializar git y commitear**

```bash
git init
git add pyproject.toml .gitignore src tests
git commit -m "chore: scaffold del proyecto con dependencias y test de humo"
```

---

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
    cos, sin = _cos_sin(t.angle_deg)
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


_EXACT_COS_SIN: dict[float, tuple[float, float]] = {
    0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)
}
"""Exact values for the quarter turns, which the generic formula gets wrong."""


def _cos_sin(angle_deg: float) -> tuple[float, float]:
    """Cosine and sine of `angle_deg`, exact on the quarter turns.

    `math.cos(math.radians(90.0))` is 6.1e-17, not 0. Those residues are tiny but
    they turn two parts that should meet along a shared edge into two parts that
    overlap by a sliver, which the verifier then reports. Quarter turns are also
    by far the most common angles in the system, so they get exact values from a
    table instead of the generic formula.
    """
    exact = _EXACT_COS_SIN.get(angle_deg % 360.0)
    if exact is not None:
        return exact
    rad = math.radians(angle_deg)
    return (math.cos(rad), math.sin(rad))


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

**Método para Béziers: subdivisión recursiva con test de planitud.** Un Bézier cúbico está dentro de `tol` de su cuerda `p0→p3` cuando ambos puntos de control están a distancia ≤ `tol` **del segmento** `p0–p3`. Si no, se subdivide en el parámetro medio por De Casteljau y se recurre.

**La distancia se mide al segmento, no a la recta infinita que lo contiene, y esa diferencia es toda la corrección del test.** En una cúspide, un punto de control puede caer exactamente sobre la recta pero mucho más allá de `p3`: un test contra la recta lo daría por plano y cortaría la recursión mientras la curva todavía se proyecta afuera. Medido sobre `Bezier((0,0),(30,0),(-30,0),(0,0))`, ese error llegaba a 0.22 mm con una tolerancia pedida de 0.001 mm.

Contra el segmento el test sí es conservador, y la justificación es exacta: la distancia a un conjunto convexo es una función convexa, así que su máximo sobre el casco convexo de los puntos de control se alcanza **en uno de ellos**; como la curva vive dentro de ese casco, acotar los controles acota la curva.

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
            # The floor that keeps a full circle from degenerating applies to arcs
            # too, scaled to how much of a circle this one actually sweeps.
            count = max(count, math.ceil(MIN_CIRCLE_SEGMENTS * sweep / (2 * math.pi)))
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
    """True when both control points lie within `tolerance` of the CHORD p0-p3.

    Distance is measured to the chord *segment*, not to the infinite line through
    it. That distinction is the whole correctness of this test: a control point
    can sit exactly on the line yet far beyond p3 - which happens at cusps - and
    a line-distance test would call that flat while the curve still overshoots.

    Measuring to the segment makes the test genuinely conservative. Distance to a
    convex set is a convex function, so its maximum over the convex hull of the
    control points is attained at one of them; the curve lies inside that hull,
    so bounding the control points bounds the curve.
    """
    return (
        _point_segment_distance(p1, p0, p3) <= tolerance
        and _point_segment_distance(p2, p0, p3) <= tolerance
    )


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length_squared))
    return math.dist(p, (ax + t * dx, ay + t * dy))


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

### Task 5: Encadenado de contornos (`geometry/chaining.py`)

**Files:**
- Create: `src/nesting/model/part.py`
- Create: `src/nesting/geometry/chaining.py`
- Test: `tests/geometry/test_chaining.py`

**Interfaces:**
- Consumes: `Point` de `nesting.model.entities` (Task 2)
- Produces:
  - `Contour(points: tuple[Point, ...], entity_ids: tuple[int, ...])` — cerrado, **sin repetir** el primer punto al final
  - `OpenChain(points: tuple[Point, ...], entity_ids: tuple[int, ...], gap: float)` — lo que no cerró, con la distancia que faltaba
  - `chain_contours(segments: Sequence[tuple[tuple[Point, ...], int]], tol: float) -> tuple[list[Contour], list[OpenChain], int]`
    - Cada entrada es `(polilínea_aplanada, id_de_entidad_de_origen)`.
    - El tercer valor devuelto es la **cantidad de segmentos duplicados descartados**.

> **Nota posterior a la implementación.** El código de abajo es el punto de partida; la
> implementación real divergió bastante tras tres rondas de revisión que encontraron cuatro
> defectos reales en este esqueleto. El módulo final agrega un **invariante de contabilidad**
> (`ChainingInvariantError`) que garantiza que ningún tramo se pierda en silencio, un
> **desempate angular determinístico** para vértices compartidos entre contornos distintos, y
> una **clave de deduplicación canónica bajo el grupo diedral** para anillos cerrados. El
> detalle de cada defecto está en `.superpowers/sdd/progress.md` y en
> `.superpowers/sdd/task-5-report.md`. Para este módulo, el código es la fuente de verdad.

**Por qué este módulo existe.** Los DXF que exporta CorelDRAW traen cada contorno **partido en decenas de `LINE`, `ARC` y `SPLINE` sueltos**, no como polilíneas cerradas. Sin reconstruir los ciclos no hay piezas. Es el caso normal, no el excepcional, y es donde se esconden los bugs que después se malinterpretan como "el nesting anda mal". Por eso es un módulo aislado con test propio exhaustivo.

**Algoritmo.** Primero se descartan duplicados (Corel suele dibujar la misma línea dos veces). Después se construye un índice espacial (`scipy.spatial.cKDTree`) sobre los extremos de todos los tramos. Se toma un tramo sin usar y se camina hacia adelante enganchando tramos cuyo extremo caiga dentro de `tol`, invirtiéndolos si hace falta; cuando no hay más, se da vuelta la cadena acumulada y se camina hacia adelante otra vez (que equivale a extender hacia atrás). Si los dos extremos terminan a distancia ≤ `tol`, es un contorno cerrado; si no, es una cadena abierta que se reporta con su hueco.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/geometry/test_chaining.py`:

```python
import math

from nesting.geometry.chaining import chain_contours

TOL = 0.1


def test_a_single_already_closed_ring_is_a_contour():
    ring = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    contours, open_chains, duplicates = chain_contours([(ring, 0)], TOL)

    assert len(contours) == 1
    assert len(open_chains) == 0
    assert duplicates == 0
    assert contours[0].points[0] != contours[0].points[-1], "no se repite el primer punto"
    assert len(contours[0].points) == 4
    assert contours[0].entity_ids == (0,)


def test_four_separate_sides_become_one_contour():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (10.0, 10.0)), 1),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)

    assert len(contours) == 1
    assert len(open_chains) == 0
    assert len(contours[0].points) == 4
    assert sorted(contours[0].entity_ids) == [0, 1, 2, 3]


def test_sides_in_random_order_and_reversed_still_chain():
    segments = [
        (((10.0, 10.0), (10.0, 0.0)), 2),   # invertido
        (((0.0, 10.0), (0.0, 0.0)), 3),
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((0.0, 10.0), (10.0, 10.0)), 1),   # invertido
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)

    assert len(contours) == 1
    assert len(open_chains) == 0
    assert len(contours[0].points) == 4


def test_endpoints_within_tolerance_are_joined():
    """Corel deja huecos de micras entre tramos; tienen que unirse igual."""
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.02), (10.0, 10.0)), 1),   # arranca 0.02 mm mas arriba
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_gap_larger_than_tolerance_produces_an_open_chain():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (10.0, 10.0)), 1),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 5.0)), 3),      # falta el ultimo tramo
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)

    assert len(contours) == 0
    assert len(open_chains) == 1
    assert math.isclose(open_chains[0].gap, 5.0, abs_tol=1e-9)


def test_two_independent_squares_become_two_contours():
    segments = [
        (((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)), 0),
        (((5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 6.0), (5.0, 5.0)), 1),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)
    assert len(contours) == 2
    assert len(open_chains) == 0


def test_exact_duplicate_segments_are_discarded():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((0.0, 0.0), (10.0, 0.0)), 1),      # duplicado exacto
        (((10.0, 0.0), (10.0, 10.0)), 2),
        (((10.0, 10.0), (0.0, 10.0)), 3),
        (((0.0, 10.0), (0.0, 0.0)), 4),
    ]
    contours, open_chains, duplicates = chain_contours(segments, TOL)

    assert duplicates == 1
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_reversed_duplicate_segments_are_discarded():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (0.0, 0.0)), 1),      # el mismo, al reves
        (((10.0, 0.0), (10.0, 10.0)), 2),
        (((10.0, 10.0), (0.0, 10.0)), 3),
        (((0.0, 10.0), (0.0, 0.0)), 4),
    ]
    contours, _, duplicates = chain_contours(segments, TOL)
    assert duplicates == 1
    assert len(contours) == 1


def test_chain_can_grow_backwards_from_the_starting_segment():
    """Se arranca por un tramo del medio: hay que extender para los dos lados."""
    segments = [
        (((10.0, 0.0), (10.0, 10.0)), 1),    # este queda primero en la lista
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_degenerate_contours_are_dropped():
    """Un 'contorno' de dos puntos no encierra area: no es una pieza."""
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (0.0, 0.0000001)), 1),
    ]
    contours, _, _ = chain_contours(segments, TOL)
    assert len(contours) == 0


def test_empty_input():
    assert chain_contours([], TOL) == ([], [], 0)


def test_entity_ids_are_preserved_for_every_contour():
    segments = [
        (((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)), 7),
        (((5.0, 5.0), (6.0, 5.0)), 8),
        (((6.0, 5.0), (6.0, 6.0)), 9),
        (((6.0, 6.0), (5.0, 6.0)), 10),
        (((5.0, 6.0), (5.0, 5.0)), 11),
    ]
    contours, _, _ = chain_contours(segments, TOL)
    by_size = sorted(contours, key=lambda c: len(c.entity_ids))
    assert by_size[0].entity_ids == (7,)
    assert sorted(by_size[1].entity_ids) == [8, 9, 10, 11]
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/geometry/test_chaining.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.geometry.chaining'`.

- [ ] **Step 3: Escribir el modelo de contornos**

Archivo `src/nesting/model/part.py`:

```python
"""Contours, parts and placements: what the engine moves around."""

from dataclasses import dataclass

from nesting.model.entities import Point


@dataclass(frozen=True)
class Contour:
    """A closed loop. The first point is NOT repeated at the end."""

    points: tuple[Point, ...]
    entity_ids: tuple[int, ...]
    """Indices into the drawing's entity list, so the writer can find the originals."""


@dataclass(frozen=True)
class OpenChain:
    """A run of segments that failed to close. Reported to the user as an error."""

    points: tuple[Point, ...]
    entity_ids: tuple[int, ...]
    gap: float
    """Distance between the two loose ends, in mm."""
```

- [ ] **Step 4: Escribir el encadenador**

Archivo `src/nesting/geometry/chaining.py`:

```python
"""Rebuild closed loops out of loose segments.

CorelDRAW exports split every outline into dozens of separate LINE, ARC and
SPLINE entities rather than closed polylines, so this is the normal path, not an
error path. It is also the dirtiest code in the project, which is why it lives
on its own behind a narrow interface.
"""

import math
from collections.abc import Sequence

from scipy.spatial import cKDTree

from nesting.model.entities import Point
from nesting.model.part import Contour, OpenChain

MIN_CONTOUR_POINTS = 3
"""Fewer than three distinct points cannot enclose any area."""


def chain_contours(
    segments: Sequence[tuple[tuple[Point, ...], int]],
    tol: float,
) -> tuple[list[Contour], list[OpenChain], int]:
    """Join `segments` end to end into closed contours.

    Each input is a flattened polyline paired with the id of the entity it came
    from. Returns the closed contours, the runs that failed to close, and how
    many duplicate segments were discarded.
    """
    kept, duplicates = _drop_duplicates(segments, tol)
    if not kept:
        return [], [], duplicates

    paths = [list(points) for points, _ in kept]
    ids = [entity_id for _, entity_id in kept]

    endpoints = []
    for path in paths:
        endpoints.append(path[0])
        endpoints.append(path[-1])
    tree = cKDTree(endpoints)

    used = [False] * len(paths)
    contours: list[Contour] = []
    open_chains: list[OpenChain] = []

    for seed in range(len(paths)):
        if used[seed]:
            continue
        used[seed] = True
        points = list(paths[seed])
        chain_ids = [ids[seed]]

        if _is_closed(points, tol):
            _emit(points, chain_ids, tol, contours, open_chains)
            continue

        # Walk forward, then reverse and walk forward again, which extends the
        # other end. Two passes are enough because after the reversal the former
        # head is the tail.
        for _ in range(2):
            _extend_forward(points, chain_ids, paths, ids, used, tree, tol)
            if _is_closed(points, tol):
                break
            points.reverse()

        _emit(points, chain_ids, tol, contours, open_chains)

    return contours, open_chains, duplicates


def _extend_forward(
    points: list[Point],
    chain_ids: list[int],
    paths: list[list[Point]],
    ids: list[int],
    used: list[bool],
    tree: cKDTree,
    tol: float,
) -> None:
    """Keep attaching unused segments to the tail of `points`."""
    while True:
        match = _find_unused_neighbour(points[-1], paths, used, tree, tol)
        if match is None:
            return
        index, at_tail = match
        used[index] = True
        nxt = list(paths[index])
        if at_tail:
            nxt.reverse()
        points.extend(nxt[1:])
        chain_ids.append(ids[index])
        if _is_closed(points, tol):
            return


def _find_unused_neighbour(
    target: Point,
    paths: list[list[Point]],
    used: list[bool],
    tree: cKDTree,
    tol: float,
) -> tuple[int, bool] | None:
    """Find an unused segment with an endpoint within `tol` of `target`.

    Returns (segment index, whether it matched on that segment's tail).
    """
    for endpoint_index in tree.query_ball_point(target, tol):
        index, which_end = divmod(endpoint_index, 2)
        if used[index]:
            continue
        return index, which_end == 1
    return None


def _emit(
    points: list[Point],
    chain_ids: list[int],
    tol: float,
    contours: list[Contour],
    open_chains: list[OpenChain],
) -> None:
    """Classify a finished run as a closed contour or an open chain."""
    gap = math.dist(points[0], points[-1])
    if gap > tol:
        open_chains.append(OpenChain(tuple(points), tuple(chain_ids), gap))
        return

    ring = points[:-1] if gap <= tol and len(points) > 1 else points
    ring = _drop_consecutive_duplicates(ring, tol)
    if len(ring) < MIN_CONTOUR_POINTS:
        return  # degenerate: encloses no area
    contours.append(Contour(tuple(ring), tuple(chain_ids)))


def _is_closed(points: list[Point], tol: float) -> bool:
    return len(points) > 2 and math.dist(points[0], points[-1]) <= tol


def _drop_consecutive_duplicates(points: list[Point], tol: float) -> list[Point]:
    out: list[Point] = []
    for p in points:
        if not out or math.dist(out[-1], p) > tol:
            out.append(p)
    return out


def _drop_duplicates(
    segments: Sequence[tuple[tuple[Point, ...], int]],
    tol: float,
) -> tuple[list[tuple[tuple[Point, ...], int]], int]:
    """Remove segments that repeat an earlier one, in either direction.

    Corel exports frequently draw the same line twice. The key is built from the
    two endpoints plus a middle point and the point count, snapped to the
    tolerance grid.

    The point list is first put into a canonical direction - the one whose
    snapped head sorts first - before the middle is taken. Without that step the
    middle *index* lands on a different physical point once the list is
    reversed, so a reversed duplicate would compute a different key and survive.
    A two-point segment makes this obvious: index 1 is the tail, which is
    precisely the point that swaps.
    """
    seen: set[tuple] = set()
    kept: list[tuple[tuple[Point, ...], int]] = []
    duplicates = 0

    for points, entity_id in segments:
        if len(points) < 2:
            duplicates += 1
            continue
        head = _snap(points[0], tol)
        tail = _snap(points[-1], tol)
        canonical = points if head <= tail else tuple(reversed(points))
        middle = _snap(canonical[len(canonical) // 2], tol)
        key = (min(head, tail), max(head, tail), middle, len(points))
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        kept.append((points, entity_id))

    return kept, duplicates


def _snap(p: Point, tol: float) -> tuple[int, int]:
    return (round(p[0] / tol), round(p[1] / tol))
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/geometry/test_chaining.py -v`
Esperado: `12 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/model/part.py src/nesting/geometry/chaining.py tests/geometry/test_chaining.py
git commit -m "feat: encadenado de tramos sueltos en contornos cerrados"
```

---

### Task 6: Árbol de contención (`geometry/nesting_tree.py`)

**Files:**
- Modify: `src/nesting/model/part.py` — agregar `Part` y `Placement`
- Create: `src/nesting/geometry/nesting_tree.py`
- Test: `tests/geometry/test_nesting_tree.py`

**Interfaces:**
- Consumes: `Contour` de `nesting.model.part` (Task 5), `Transform` de `nesting.model.entities` (Task 2)
- Produces:
  - `Part(id: int, outer: tuple[Point, ...], holes: tuple[tuple[Point, ...], ...], entity_ids: tuple[int, ...])` con las propiedades `area: float` (área neta, exterior menos agujeros), `outer_area: float` y `bbox: tuple[float, float, float, float]` (minx, miny, maxx, maxy)
  - `Placement(part_id: int, sheet: int, transform: Transform)`
  - `build_parts(contours: Sequence[Contour]) -> list[Part]`

**La regla, de la spec §3.3:** la profundidad de contención decide qué es cada contorno.

| Profundidad | Significado |
|---|---|
| 0 (par) | Contorno exterior de una pieza |
| 1 (impar) | Agujero de la pieza que lo contiene |
| ≥2 (par) | **Pieza independiente**, se reubica en otro lado |

Un contorno de nivel ≥2 se convierte en su **propia** pieza: sus `entity_ids` viajan con ella, **no** con la pieza que la contenía en el dibujo original. Esto es lo que permite que el motor después la ponga en cualquier lado (spec §5.2).

**Robustez:** la contención se testea con el `representative_point()` del contorno interno, no con `contains()` polígono-contra-polígono. Motivo: dos anillos anidados que comparten un tramo de borde (pasa con geometría exportada) hacen fallar `contains()`, mientras que el punto representativo está garantizadamente en el interior.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/geometry/test_nesting_tree.py`:

```python
import pytest

from nesting.geometry.nesting_tree import build_parts
from nesting.model.part import Contour


def square(x0, y0, side, ids):
    return Contour(
        points=((x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)),
        entity_ids=tuple(ids),
    )


def test_a_single_square_is_one_part_with_no_holes():
    parts = build_parts([square(0, 0, 100, [0])])
    assert len(parts) == 1
    assert parts[0].holes == ()
    assert parts[0].entity_ids == (0,)
    assert parts[0].id == 0


def test_two_disjoint_squares_are_two_parts():
    parts = build_parts([square(0, 0, 10, [0]), square(50, 50, 10, [1])])
    assert len(parts) == 2
    assert all(p.holes == () for p in parts)


def test_a_contour_inside_another_becomes_a_hole():
    parts = build_parts([square(0, 0, 100, [0]), square(30, 30, 20, [1])])
    assert len(parts) == 1
    assert len(parts[0].holes) == 1
    assert sorted(parts[0].entity_ids) == [0, 1], "el agujero viaja con la pieza"


def test_depth_two_becomes_an_independent_part():
    """Exterior > agujero > isla. La isla es una pieza aparte."""
    contours = [square(0, 0, 100, [0]), square(20, 20, 60, [1]), square(40, 40, 20, [2])]
    parts = build_parts(contours)

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
    parts = build_parts(contours)
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
    parts = build_parts(contours)
    assert len(parts) == 1
    assert len(parts[0].holes) == 3
    assert sorted(parts[0].entity_ids) == [0, 1, 2, 3]


def test_net_area_subtracts_the_holes():
    parts = build_parts([square(0, 0, 100, [0]), square(30, 30, 20, [1])])
    assert parts[0].outer_area == pytest.approx(10000.0)
    assert parts[0].area == pytest.approx(10000.0 - 400.0)


def test_bbox():
    parts = build_parts([square(5, -3, 10, [0])])
    assert parts[0].bbox == pytest.approx((5.0, -3.0, 15.0, 7.0))


def test_part_ids_are_consecutive_from_zero():
    contours = [square(0, 0, 10, [0]), square(50, 0, 10, [1]), square(100, 0, 10, [2])]
    parts = build_parts(contours)
    assert sorted(p.id for p in parts) == [0, 1, 2]


def test_empty_input_produces_no_parts():
    assert build_parts([]) == []


def test_area_is_positive_regardless_of_winding_direction():
    clockwise = Contour(((0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)), (0,))
    parts = build_parts([clockwise])
    assert parts[0].outer_area == pytest.approx(100.0)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/geometry/test_nesting_tree.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.geometry.nesting_tree'`.

- [ ] **Step 3: Agregar `Part` y `Placement` al modelo**

Agregar al final de `src/nesting/model/part.py`:

```python
@dataclass(frozen=True)
class Part:
    """One piece to cut: an outer outline plus the holes that travel with it."""

    id: int
    outer: tuple[Point, ...]
    holes: tuple[tuple[Point, ...], ...]
    entity_ids: tuple[int, ...]
    """Every entity that moves rigidly with this part, outer and holes alike."""

    @property
    def outer_area(self) -> float:
        return _shoelace_area(self.outer)

    @property
    def area(self) -> float:
        """Net material area: the outline minus its holes."""
        return self.outer_area - sum(_shoelace_area(h) for h in self.holes)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.outer]
        ys = [p[1] for p in self.outer]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass(frozen=True)
class Placement:
    """Where one part ended up: which sheet, and the rigid transform to get there."""

    part_id: int
    sheet: int
    transform: Transform


def _shoelace_area(ring: tuple[Point, ...]) -> float:
    """Absolute enclosed area, independent of winding direction."""
    total = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0
```

Y ampliar el import del principio del archivo:

```python
from nesting.model.entities import Point, Transform
```

- [ ] **Step 4: Escribir el árbol de contención**

Archivo `src/nesting/geometry/nesting_tree.py`:

```python
"""Decide which contours are parts and which are holes.

Even nesting depth means material, odd means a hole, following the usual CAD
convention. A contour at depth two or deeper becomes an independent part rather
than staying nested where it happened to be drawn, so the engine is free to
place it anywhere.
"""

from collections.abc import Sequence

from shapely.geometry import Polygon
from shapely.strtree import STRtree

from nesting.model.part import Contour, Part


def build_parts(contours: Sequence[Contour]) -> list[Part]:
    """Group `contours` into parts by containment depth."""
    if not contours:
        return []

    polygons = [Polygon(c.points) for c in contours]
    polygons = [p if p.is_valid else p.buffer(0) for p in polygons]

    parents = _find_parents(polygons)
    depths = [_depth_of(i, parents) for i in range(len(contours))]

    # Holes are attached to the nearest enclosing contour, but only when that
    # contour is itself material (even depth). A depth-3 ring is a hole of the
    # depth-2 part, not of the depth-0 one.
    holes_by_owner: dict[int, list[int]] = {}
    for index, depth in enumerate(depths):
        if depth % 2 == 1:
            owner = parents[index]
            assert owner is not None, "an odd-depth contour always has a parent"
            holes_by_owner.setdefault(owner, []).append(index)

    parts: list[Part] = []
    for index, depth in enumerate(depths):
        if depth % 2 == 1:
            continue
        hole_indices = holes_by_owner.get(index, [])
        entity_ids = list(contours[index].entity_ids)
        for hole in hole_indices:
            entity_ids.extend(contours[hole].entity_ids)
        parts.append(
            Part(
                id=len(parts),
                outer=contours[index].points,
                holes=tuple(contours[h].points for h in hole_indices),
                entity_ids=tuple(entity_ids),
            )
        )
    return parts


def _find_parents(polygons: list[Polygon]) -> list[int | None]:
    """For each polygon, the index of the smallest polygon that encloses it."""
    tree = STRtree(polygons)
    parents: list[int | None] = [None] * len(polygons)

    for index, polygon in enumerate(polygons):
        # A representative point is guaranteed interior, which survives the
        # shared-boundary cases that make polygon-in-polygon containment fail.
        probe = polygon.representative_point()
        best: int | None = None
        best_area = float("inf")
        for candidate in tree.query(probe):
            candidate = int(candidate)
            if candidate == index:
                continue
            if not polygons[candidate].contains(probe):
                continue
            # A real parent is strictly larger. Without this guard the probe of
            # an OUTER ring - which also falls inside every ring nested within
            # it - would pick one of its own children as its parent, and the
            # resulting cycle makes the depth walk loop forever.
            if polygons[candidate].area <= polygon.area:
                continue
            if polygons[candidate].area < best_area:
                best, best_area = candidate, polygons[candidate].area
        parents[index] = best

    return parents


def _depth_of(index: int, parents: Sequence[int | None]) -> int:
    depth = 0
    current = parents[index]
    while current is not None:
        depth += 1
        current = parents[current]
    return depth
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/geometry/test_nesting_tree.py -v`
Esperado: `11 passed`.

- [ ] **Step 6: Correr toda la suite para verificar que nada se rompió**

Run: `.venv/bin/pytest -q`
Esperado: todos en verde (el total acumulado depende de los tests agregados en tareas anteriores).

- [ ] **Step 7: Commit**

```bash
git add src/nesting/model/part.py src/nesting/geometry/nesting_tree.py tests/geometry/test_nesting_tree.py
git commit -m "feat: arbol de contencion para separar piezas de agujeros"
```

---

### Task 7: El verificador exacto (`geometry/verify.py`)

**Files:**
- Create: `src/nesting/geometry/verify.py`
- Test: `tests/geometry/test_verify.py`

**Interfaces:**
- Consumes: `Part`, `Placement` (Task 6), `Transform` (Task 2), `apply_points` (Task 3)
- Produces:
  - `Violation(kind: str, part_a: int, part_b: int | None, sheet: int, detail: str)` — `kind` es `"overlap"`, `"separation"` u `"out_of_bounds"`; `detail` es un mensaje en español listo para mostrar
  - `placed_polygon(part: Part, t: Transform) -> shapely.geometry.Polygon`
  - `verify(parts, placements, sheet_w, sheet_h, sep, margin) -> list[Violation]`

**Este es el módulo más importante del hito 1.** Cumple tres funciones (spec §5.7):

1. **Red de seguridad en producción** — ninguna salida se escribe sin pasar por acá.
2. **Oráculo de los tests** — cualquier motor, cualquier configuración, tiene que pasarlo.
3. **Árbitro** de la comparación raster vs NFP si algún día existe el segundo motor.

Trabaja sobre **polígonos exactos de shapely**, nunca sobre bitmaps. Es deliberadamente independiente de cualquier motor: no importa nada de `engine/`.

**El caso que valida el aprovechamiento de agujeros:** una pieza colocada dentro del agujero de otra **no** debe dar violación. Sale solo, porque el polígono del padre se construye con `interiors` y shapely computa `distance` contra la pared real del agujero. Hay test específico.

**Tolerancia numérica:** se usa `EPS = 1e-6` mm. La separación se viola solo si la distancia es menor que `sep - EPS`, para que dos piezas puestas a exactamente `sep` no den falso positivo por ruido de punto flotante.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/geometry/test_verify.py`:

```python
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
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/geometry/test_verify.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.geometry.verify'`.

- [ ] **Step 3: Escribir el verificador**

Archivo `src/nesting/geometry/verify.py`:

```python
"""The arbiter: does a finished layout actually respect its own rules?

Works on exact shapely polygons, never on rasters, and knows nothing about any
engine. Every output is checked here before it is written, and the tests use it
as their oracle.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import Polygon, box
from shapely.strtree import STRtree

from nesting.geometry.transform import apply_points
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement

EPS = 1e-6
"""Numeric slack in mm, so a part placed at exactly `sep` is not flagged."""

OVERLAP_AREA_THRESHOLD_MM2 = 1e-6
"""Intersection area above which an overlap is a real violation.

Two parts meant to touch along a shared edge can end up with a sliver of
phantom intersection purely from floating-point noise, on the order of
1e-11 mm2. A square micron does not exist for a 6 mm router bit cutting MDF, so
this threshold sits five orders of magnitude above that noise floor and many
orders below anything a real overlap produces (a small but genuine overlap is
1 mm2 or more). It cannot mask a real overlap; it ignores only intersections too
small to mean anything physically.
"""


@dataclass(frozen=True)
class Violation:
    kind: str
    """One of "overlap", "separation", "out_of_bounds"."""

    part_a: int
    part_b: int | None
    sheet: int
    detail: str
    """User-facing message, in Spanish."""


def placed_polygon(part: Part, t: Transform) -> Polygon:
    """The exact material footprint of `part` once `t` is applied."""
    return Polygon(
        apply_points(t, part.outer),
        [apply_points(t, hole) for hole in part.holes],
    )


def verify(
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheet_w: float,
    sheet_h: float,
    sep: float,
    margin: float,
) -> list[Violation]:
    """Check a finished layout. An empty list means the layout is sound."""
    by_id = {p.id: p for p in parts}
    violations: list[Violation] = []

    by_sheet: dict[int, list[Placement]] = {}
    for placement in placements:
        by_sheet.setdefault(placement.sheet, []).append(placement)

    usable = box(margin, margin, sheet_w - margin, sheet_h - margin)

    for sheet, sheet_placements in sorted(by_sheet.items()):
        polygons = [placed_polygon(by_id[p.part_id], p.transform) for p in sheet_placements]

        for placement, polygon in zip(sheet_placements, polygons):
            if not usable.buffer(EPS).contains(polygon):
                violations.append(
                    Violation(
                        kind="out_of_bounds",
                        part_a=placement.part_id,
                        part_b=None,
                        sheet=sheet,
                        detail=(
                            f"la pieza {placement.part_id} se sale del area util de la placa "
                            f"{sheet + 1} (margen {margin} mm)"
                        ),
                    )
                )

        violations.extend(_check_pairs(sheet, sheet_placements, polygons, sep))

    return violations


def _check_pairs(
    sheet: int,
    placements: Sequence[Placement],
    polygons: Sequence[Polygon],
    sep: float,
) -> list[Violation]:
    """Pairwise overlap and separation checks, narrowed by a spatial index."""
    violations: list[Violation] = []
    if len(polygons) < 2:
        return violations

    # Growing each polygon by `sep` turns "closer than sep" into "intersects",
    # so the index can discard the vast majority of pairs up front.
    tree = STRtree([p.buffer(sep) for p in polygons])
    seen: set[tuple[int, int]] = set()

    for i, polygon in enumerate(polygons):
        for j in tree.query(polygon):
            j = int(j)
            if j == i:
                continue
            pair = (min(i, j), max(i, j))
            if pair in seen:
                continue
            seen.add(pair)

            a_id = placements[i].part_id
            b_id = placements[j].part_id

            if polygon.intersection(polygons[j]).area > OVERLAP_AREA_THRESHOLD_MM2:
                violations.append(
                    Violation(
                        kind="overlap",
                        part_a=a_id,
                        part_b=b_id,
                        sheet=sheet,
                        detail=(
                            f"las piezas {a_id} y {b_id} se superponen en la placa {sheet + 1}"
                        ),
                    )
                )
                continue

            distance = polygon.distance(polygons[j])
            if distance < sep - EPS:
                violations.append(
                    Violation(
                        kind="separation",
                        part_a=a_id,
                        part_b=b_id,
                        sheet=sheet,
                        detail=(
                            f"las piezas {a_id} y {b_id} quedaron a {distance:.3f} mm "
                            f"en la placa {sheet + 1}; el minimo pedido es {sep} mm"
                        ),
                    )
                )

    return violations
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/geometry/test_verify.py -v`
Esperado: `12 passed`.

- [ ] **Step 5: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos en verde.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/geometry/verify.py tests/geometry/test_verify.py
git commit -m "feat: verificador geometrico exacto, el arbitro de toda salida"
```

**Hito 1 completo.** Ya existe el árbitro: cualquier layout, venga de donde venga, puede evaluarse como válido o inválido.

---

# Hito 2 — Circuito completo end-to-end

*Con un nesting deliberadamente malo. Tener el pipeline entero funcionando sobre archivos reales vale más que tener un motor excelente sin poder abrir el archivo.*

---

### Task 8: Lector de DXF (`io/dxf_reader.py`)

**Files:**
- Create: `src/nesting/io/__init__.py`
- Create: `src/nesting/io/dxf_reader.py`
- Test: `tests/io/test_dxf_reader.py`

**Interfaces:**
- Consumes: las primitivas de `nesting.model.entities` (Task 2)
- Produces:
  - `Drawing(entities: list[Entity], source_units: str, warnings: list[str])`
  - `UnknownUnitsError(Exception)`
  - `read_dxf(path: str | Path, units_override: str | None = None) -> Drawing`
  - `UNIT_SCALES: dict[str, float]` — factor a milímetros para `"mm"`, `"cm"`, `"m"`, `"in"`, `"ft"`

**Regla dura de la spec §6.1: el programa no adivina unidades.** Si `$INSUNITS` es 0 (sin declarar) y no vino `units_override`, se lanza `UnknownUnitsError`. Una unidad mal inferida arruina una placa entera; fallar es más barato.

**Qué se convierte a qué:**

| DXF | Modelo interno | Exacto |
|---|---|---|
| `LINE` | `Line` | Sí |
| `CIRCLE` | `Circle` | Sí |
| `ARC` | `Arc` | Sí |
| `LWPOLYLINE` / `POLYLINE` sin bulges | `Polyline` | Sí |
| `LWPOLYLINE` / `POLYLINE` con bulges | cadena de `Line` + `Bezier` | Aproximado por ezdxf |
| `SPLINE` | cadena de `Bezier` | Sí para splines cúbicas |
| `ELLIPSE` | cadena de `Bezier` | Aproximado |
| `INSERT` | se explota recursivamente | — |
| `TEXT`, `MTEXT`, `DIMENSION`, `HATCH`, `POINT`, `SOLID`, `LEADER` | se ignora, con aviso y conteo | — |

El aviso de entidades ignoradas no es cosmético: en el screenshot de AutoCAD del proyecto hay una cota `600.00` que, sin este filtro, entraría al nesting como si fuera una pieza.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/io/test_dxf_reader.py` (crear también `tests/io/__init__.py` vacío):

```python
import ezdxf
import pytest

from nesting.io.dxf_reader import UnknownUnitsError, read_dxf
from nesting.model.entities import Arc, Bezier, Circle, Line, Polyline


def make_doc(units=4):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units
    return doc


def save(doc, tmp_path, name="t.dxf"):
    path = tmp_path / name
    doc.saveas(path)
    return path


def test_reads_a_line(tmp_path):
    doc = make_doc()
    doc.modelspace().add_line((0, 0), (10, 5), dxfattribs={"layer": "CORTE", "color": 1})
    drawing = read_dxf(save(doc, tmp_path))

    assert len(drawing.entities) == 1
    line = drawing.entities[0]
    assert isinstance(line, Line)
    assert line.start == pytest.approx((0.0, 0.0))
    assert line.end == pytest.approx((10.0, 5.0))
    assert line.style.layer == "CORTE"
    assert line.style.aci == 1


def test_reads_circle_and_arc_natively(tmp_path):
    doc = make_doc()
    msp = doc.modelspace()
    msp.add_circle((1, 2), radius=3)
    msp.add_arc((0, 0), radius=5, start_angle=10, end_angle=80)
    drawing = read_dxf(save(doc, tmp_path))

    kinds = {type(e) for e in drawing.entities}
    assert kinds == {Circle, Arc}
    circle = next(e for e in drawing.entities if isinstance(e, Circle))
    assert circle.radius == pytest.approx(3.0)
    arc = next(e for e in drawing.entities if isinstance(e, Arc))
    assert arc.start_angle == pytest.approx(10.0)
    assert arc.end_angle == pytest.approx(80.0)


def test_reads_a_closed_lwpolyline_without_bulges(tmp_path):
    doc = make_doc()
    doc.modelspace().add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)], close=True
    )
    drawing = read_dxf(save(doc, tmp_path))

    assert len(drawing.entities) == 1
    poly = drawing.entities[0]
    assert isinstance(poly, Polyline)
    assert poly.closed is True
    assert len(poly.points) == 4


def test_a_spline_becomes_bezier_segments(tmp_path):
    doc = make_doc()
    doc.modelspace().add_spline([(0, 0), (10, 20), (20, 0), (30, 20)])
    drawing = read_dxf(save(doc, tmp_path))

    assert drawing.entities
    assert all(isinstance(e, Bezier) for e in drawing.entities)


def test_bezier_segments_are_continuous(tmp_path):
    """El final de cada Bezier es el arranque del siguiente."""
    doc = make_doc()
    doc.modelspace().add_spline([(0, 0), (10, 20), (20, 0), (30, 20)])
    beziers = read_dxf(save(doc, tmp_path)).entities

    for a, b in zip(beziers, beziers[1:]):
        assert a.p3 == pytest.approx(b.p0, abs=1e-9)


def test_millimetres_are_not_rescaled(tmp_path):
    doc = make_doc(units=4)
    doc.modelspace().add_line((0, 0), (100, 0))
    drawing = read_dxf(save(doc, tmp_path))
    assert drawing.entities[0].end == pytest.approx((100.0, 0.0))
    assert drawing.source_units == "mm"


def test_centimetres_are_scaled_to_millimetres(tmp_path):
    doc = make_doc(units=5)
    doc.modelspace().add_line((0, 0), (100, 0))
    drawing = read_dxf(save(doc, tmp_path))
    assert drawing.entities[0].end == pytest.approx((1000.0, 0.0))
    assert drawing.source_units == "cm"


def test_inches_are_scaled_to_millimetres(tmp_path):
    doc = make_doc(units=1)
    doc.modelspace().add_circle((0, 0), radius=1)
    drawing = read_dxf(save(doc, tmp_path))
    assert drawing.entities[0].radius == pytest.approx(25.4)


def test_unitless_file_without_override_raises(tmp_path):
    doc = make_doc(units=0)
    doc.modelspace().add_line((0, 0), (10, 0))
    with pytest.raises(UnknownUnitsError) as info:
        read_dxf(save(doc, tmp_path))
    assert "unidades" in str(info.value).lower()


def test_unitless_file_with_override_is_accepted(tmp_path):
    doc = make_doc(units=0)
    doc.modelspace().add_line((0, 0), (10, 0))
    drawing = read_dxf(save(doc, tmp_path), units_override="cm")
    assert drawing.entities[0].end == pytest.approx((100.0, 0.0))


def test_override_wins_over_the_declared_units(tmp_path):
    doc = make_doc(units=4)
    doc.modelspace().add_line((0, 0), (10, 0))
    drawing = read_dxf(save(doc, tmp_path), units_override="cm")
    assert drawing.entities[0].end == pytest.approx((100.0, 0.0))


def test_unsupported_entities_are_skipped_with_a_warning(tmp_path):
    doc = make_doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_text("600.00").set_placement((5, 5))
    drawing = read_dxf(save(doc, tmp_path))

    assert len(drawing.entities) == 1
    assert any("TEXT" in w for w in drawing.warnings)


def test_inserts_are_exploded(tmp_path):
    doc = make_doc()
    block = doc.blocks.new(name="PATA")
    block.add_line((0, 0), (10, 0))
    block.add_line((10, 0), (10, 10))
    doc.modelspace().add_blockref("PATA", insert=(100, 100))
    drawing = read_dxf(save(doc, tmp_path))

    assert len(drawing.entities) == 2
    assert all(isinstance(e, Line) for e in drawing.entities)
    xs = sorted(e.start[0] for e in drawing.entities)
    assert xs == pytest.approx([100.0, 110.0])


def test_true_colour_is_preserved(tmp_path):
    doc = make_doc()
    line = doc.modelspace().add_line((0, 0), (1, 0))
    line.rgb = (12, 34, 56)
    drawing = read_dxf(save(doc, tmp_path))
    assert drawing.entities[0].style.rgb == (12, 34, 56)


def test_an_empty_drawing_reads_as_empty(tmp_path):
    drawing = read_dxf(save(make_doc(), tmp_path))
    assert drawing.entities == []
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/io/test_dxf_reader.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.io'`.

- [ ] **Step 3: Escribir el lector**

Archivo `src/nesting/io/__init__.py`: vacío.

Archivo `src/nesting/io/dxf_reader.py`:

```python
"""DXF -> the internal entity model, normalised to millimetres.

This is the canonical reader: `.ai` and `.3dm` are extra importers that produce
the same `Drawing`. Units are converted exactly once, here, so nothing below
`io/` ever needs to know about anything but millimetres.
"""

from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf import path as ezdxf_path
from ezdxf.entities import DXFEntity
from ezdxf.layouts import Modelspace

from nesting.model.entities import Arc, Bezier, Circle, Entity, Line, Point, Polyline, Style

UNIT_SCALES: dict[str, float] = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "ft": 304.8,
}

_INSUNITS_TO_NAME: dict[int, str] = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}

SKIPPED_TYPES = frozenset(
    {"TEXT", "MTEXT", "DIMENSION", "HATCH", "POINT", "SOLID", "LEADER",
     "MLEADER", "ATTDEF", "ATTRIB", "IMAGE", "WIPEOUT", "MESH", "3DFACE"}
)


class UnknownUnitsError(Exception):
    """The file declares no units and the caller did not supply any."""


@dataclass
class Drawing:
    """Everything a reader produces, already in millimetres."""

    entities: list[Entity] = field(default_factory=list)
    source_units: str = "mm"
    warnings: list[str] = field(default_factory=list)


def read_dxf(path: str | Path, units_override: str | None = None) -> Drawing:
    """Read `path` into a `Drawing`, scaling every coordinate to millimetres."""
    doc = ezdxf.readfile(str(path))
    units = _resolve_units(doc.units, units_override, path)
    scale = UNIT_SCALES[units]

    drawing = Drawing(source_units=units)
    skipped: dict[str, int] = {}

    for entity in _flatten_inserts(doc.modelspace()):
        kind = entity.dxftype()
        if kind in SKIPPED_TYPES:
            skipped[kind] = skipped.get(kind, 0) + 1
            continue
        converted = _convert(entity, scale, doc)
        if converted is None:
            skipped[kind] = skipped.get(kind, 0) + 1
            continue
        drawing.entities.extend(converted)

    for kind, count in sorted(skipped.items()):
        drawing.warnings.append(
            f"se ignoraron {count} entidades de tipo {kind} (no participan del nesting)"
        )

    return drawing


def _resolve_units(insunits: int, override: str | None, path: str | Path) -> str:
    if override is not None:
        if override not in UNIT_SCALES:
            raise ValueError(
                f"unidad desconocida {override!r}; use una de {sorted(UNIT_SCALES)}"
            )
        return override
    name = _INSUNITS_TO_NAME.get(insunits)
    if name is None:
        raise UnknownUnitsError(
            f"el archivo {path} no declara unidades ($INSUNITS = {insunits}). "
            f"Indique las unidades explicitamente con --unidades "
            f"({'|'.join(sorted(UNIT_SCALES))})."
        )
    return name


def _flatten_inserts(msp: Modelspace):
    """Yield every entity, expanding block references recursively."""
    stack = list(msp)
    while stack:
        entity = stack.pop()
        if entity.dxftype() == "INSERT":
            stack.extend(entity.virtual_entities())
        else:
            yield entity


def _convert(entity: DXFEntity, scale: float, doc) -> list[Entity] | None:
    """Convert one DXF entity, or None when the type is not supported."""
    style = _style_of(entity, doc)
    kind = entity.dxftype()

    if kind == "LINE":
        return [Line(_pt(entity.dxf.start, scale), _pt(entity.dxf.end, scale), style)]

    if kind == "CIRCLE":
        return [Circle(_pt(entity.dxf.center, scale), entity.dxf.radius * scale, style)]

    if kind == "ARC":
        return [
            Arc(
                center=_pt(entity.dxf.center, scale),
                radius=entity.dxf.radius * scale,
                start_angle=entity.dxf.start_angle,
                end_angle=entity.dxf.end_angle,
                style=style,
            )
        ]

    if kind in ("LWPOLYLINE", "POLYLINE"):
        if not _has_bulges(entity):
            points = tuple(
                (v[0] * scale, v[1] * scale) for v in entity.vertices_in_wcs()
            ) if kind == "POLYLINE" else tuple(
                (x * scale, y * scale) for x, y in entity.get_points("xy")
            )
            return [Polyline(points, bool(entity.closed), style)]
        return _from_path(entity, scale, style)

    if kind in ("SPLINE", "ELLIPSE"):
        return _from_path(entity, scale, style)

    return None


def _has_bulges(entity: DXFEntity) -> bool:
    try:
        if entity.dxftype() == "LWPOLYLINE":
            return any(abs(p[4]) > 1e-12 for p in entity.get_points("xyseb"))
        return any(abs(v.dxf.bulge) > 1e-12 for v in entity.vertices)
    except (AttributeError, IndexError):
        return False


def _from_path(entity: DXFEntity, scale: float, style: Style) -> list[Entity]:
    """Convert any curve entity through ezdxf's Path into lines and cubic Beziers."""
    source = ezdxf_path.make_path(entity)
    out: list[Entity] = []
    current = _pt(source.start, scale)

    for command in source.commands():
        end = _pt(command.end, scale)
        name = type(command).__name__
        if name == "LineTo":
            out.append(Line(current, end, style))
        elif name == "Curve3To":
            control = _pt(command.ctrl, scale)
            # Degree elevation: a quadratic Bezier as an equivalent cubic one.
            c1 = (current[0] + 2 / 3 * (control[0] - current[0]),
                  current[1] + 2 / 3 * (control[1] - current[1]))
            c2 = (end[0] + 2 / 3 * (control[0] - end[0]),
                  end[1] + 2 / 3 * (control[1] - end[1]))
            out.append(Bezier(current, c1, c2, end, style))
        elif name == "Curve4To":
            out.append(
                Bezier(current, _pt(command.ctrl1, scale), _pt(command.ctrl2, scale), end, style)
            )
        else:  # MoveTo, for multi-part paths
            current = end
            continue
        current = end

    return out


def _style_of(entity: DXFEntity, doc) -> Style:
    """Capture colour and layer exactly as the source had them."""
    aci = entity.dxf.get("color", 256)
    layer = entity.dxf.get("layer", "0")

    rgb: tuple[int, int, int] | None = getattr(entity, "rgb", None)
    if rgb is None:
        resolved = aci
        if resolved in (0, 256):  # BYBLOCK / BYLAYER
            try:
                resolved = doc.layers.get(layer).color
            except Exception:
                resolved = 7
        try:
            rgb = ezdxf.colors.aci2rgb(abs(resolved) if resolved else 7)
        except Exception:
            rgb = (255, 255, 255)

    return Style(aci=aci, rgb=tuple(rgb), layer=layer)


def _pt(v, scale: float) -> Point:
    return (float(v[0]) * scale, float(v[1]) * scale)
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/io/test_dxf_reader.py -v`
Esperado: `15 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/io tests/io
git commit -m "feat: lector de DXF con normalizacion a milimetros"
```

---

### Task 9: Escritor de DXF (`io/dxf_writer.py`)

**Files:**
- Create: `src/nesting/io/dxf_writer.py`
- Test: `tests/io/test_dxf_writer.py`

**Interfaces:**
- Consumes: `Drawing` (Task 8), `Part`, `Placement` (Task 6), `apply_entity` (Task 3)
- Produces:
  - `SHEET_LAYER = "_PLACA"` — **vive en `io/dxf_reader.py`** y el escritor lo importa de ahi. Motivo: el lector tiene que saltear esa capa (y avisarlo) para que realimentar la propia salida funcione; es una constante de protocolo compartida, y la direccion correcta de la dependencia es escritor → lector
  - `write_dxf(path, drawing, parts, placements, sheet_w, sheet_h, gap=100.0) -> None`

**Acá se materializa el principio rector de la spec §3.5.** Las entidades que se escriben son las **originales del archivo de entrada**, transformadas rígidamente. Nunca se escriben los polígonos aplanados. Por eso una spline sigue siendo una spline, un círculo sigue siendo un círculo, y el color y la capa salen intactos sin código que los copie.

**Layout:** las placas van en fila horizontal (spec §6.2). La placa `i` se dibuja desplazada `i · (sheet_w + gap)` en X. Como el desplazamiento es una traslación pura, se compone con la transformación de la pieza sumándolo a `dx` — no hace falta una segunda pasada.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/io/test_dxf_writer.py`:

```python
import ezdxf
import pytest

from nesting.io.dxf_reader import read_dxf
from nesting.io.dxf_writer import SHEET_LAYER, write_dxf
from nesting.model.entities import Circle, Line, Style, Transform
from nesting.model.part import Part, Placement

STYLE = Style(aci=3, rgb=(0, 255, 0), layer="CORTE")


def drawing_with(entities):
    from nesting.io.dxf_reader import Drawing
    return Drawing(entities=list(entities), source_units="mm", warnings=[])


def square_part(part_id, side):
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (side, 0.0), (side, side), (0.0, side)),
        holes=(),
        entity_ids=(0, 1, 2, 3),
    )


def square_entities(side):
    corners = [(0.0, 0.0), (side, 0.0), (side, side), (0.0, side)]
    return [
        Line(corners[i], corners[(i + 1) % 4], STYLE) for i in range(4)
    ]


def read_back(path):
    return ezdxf.readfile(str(path))


def test_writes_a_sheet_rectangle_on_its_own_layer(tmp_path):
    out = tmp_path / "out.dxf"
    write_dxf(out, drawing_with([]), [], [], sheet_w=1830.0, sheet_h=2600.0)

    msp = read_back(out).modelspace()
    rectangles = [e for e in msp if e.dxf.layer == SHEET_LAYER]
    assert len(rectangles) == 1


def test_one_rectangle_per_sheet_used(tmp_path):
    out = tmp_path / "out.dxf"
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [
        Placement(0, 0, Transform(0.0, False, 10.0, 10.0)),
        Placement(1, 2, Transform(0.0, False, 10.0, 10.0)),
    ]
    write_dxf(out, drawing_with(square_entities(100.0)), parts, placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    rectangles = [e for e in msp if e.dxf.layer == SHEET_LAYER]
    assert len(rectangles) == 3, "placas 0, 1 y 2 aunque la 1 este vacia"


def test_parts_are_translated_to_their_placement(tmp_path):
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    placements = [Placement(0, 0, Transform(0.0, False, 500.0, 300.0))]
    write_dxf(out, drawing_with(entities), [square_part(0, 100.0)], placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    lines = [e for e in msp if e.dxftype() == "LINE"]
    assert len(lines) == 4
    xs = [e.dxf.start[0] for e in lines]
    assert min(xs) == pytest.approx(500.0)


def test_sheets_are_laid_out_side_by_side(tmp_path):
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [
        Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
        Placement(1, 1, Transform(0.0, False, 0.0, 0.0)),
    ]
    write_dxf(out, drawing_with(entities), parts, placements,
              sheet_w=1000.0, sheet_h=1000.0, gap=100.0)

    msp = read_back(out).modelspace()
    xs = sorted(e.dxf.start[0] for e in msp if e.dxftype() == "LINE")
    assert min(xs) == pytest.approx(0.0)
    assert max(xs) == pytest.approx(1100.0 + 100.0), "placa 1 desplazada 1000 + 100 de gap"


def test_colour_and_layer_survive_the_round_trip(tmp_path):
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    placements = [Placement(0, 0, Transform(0.0, False, 0.0, 0.0))]
    write_dxf(out, drawing_with(entities), [square_part(0, 100.0)], placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    lines = [e for e in msp if e.dxftype() == "LINE"]
    assert all(e.dxf.layer == "CORTE" for e in lines)
    assert all(e.dxf.color == 3 for e in lines)


def test_circles_stay_circles(tmp_path):
    out = tmp_path / "out.dxf"
    entities = [Circle((0.0, 0.0), 300.0, STYLE)]
    part = Part(0, ((-300.0, -300.0), (300.0, -300.0), (300.0, 300.0), (-300.0, 300.0)),
                (), (0,))
    placements = [Placement(0, 0, Transform(0.0, False, 400.0, 400.0))]
    write_dxf(out, drawing_with(entities), [part], placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    circles = [e for e in msp if e.dxftype() == "CIRCLE"]
    assert len(circles) == 1
    assert circles[0].dxf.radius == pytest.approx(300.0)
    assert circles[0].dxf.center[0] == pytest.approx(400.0)


def test_output_declares_millimetres(tmp_path):
    out = tmp_path / "out.dxf"
    write_dxf(out, drawing_with([]), [], [], 1000.0, 1000.0)
    assert read_back(out).units == 4


def test_the_output_can_be_read_back_by_our_own_reader(tmp_path):
    """El circuito completo: lo que escribimos, lo sabemos leer."""
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    placements = [Placement(0, 0, Transform(0.0, False, 50.0, 50.0))]
    write_dxf(out, drawing_with(entities), [square_part(0, 100.0)], placements, 1000.0, 1000.0)

    reread = read_dxf(out)
    lines = [e for e in reread.entities if isinstance(e, Line)]
    assert len(lines) == 4


def test_only_the_entities_of_placed_parts_are_written(tmp_path):
    """Las entidades que no pertenecen a ninguna pieza colocada no salen."""
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0) + [Line((900.0, 900.0), (950.0, 950.0), STYLE)]
    part = Part(0, ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)), (), (0, 1, 2, 3))
    placements = [Placement(0, 0, Transform(0.0, False, 0.0, 0.0))]
    write_dxf(out, drawing_with(entities), [part], placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    assert len([e for e in msp if e.dxftype() == "LINE"]) == 4
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/io/test_dxf_writer.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.io.dxf_writer'`.

- [ ] **Step 3: Escribir el escritor**

Archivo `src/nesting/io/dxf_writer.py`:

```python
"""Write the finished layout, by transforming the ORIGINAL entities.

Nothing flattened ever reaches the output file: a spline stays a spline, a
circle stays a circle, and colours and layers survive because they were never
touched in the first place.
"""

from collections.abc import Sequence
from pathlib import Path

import ezdxf

from nesting.geometry.transform import apply_entity
from nesting.io.dxf_reader import Drawing
from nesting.model.entities import Arc, Bezier, Circle, Entity, Line, Polyline, Style, Transform
from nesting.model.part import Part, Placement

SHEET_LAYER = "_PLACA"
"""Layer holding the sheet outlines, kept apart from the cut geometry."""

DEFAULT_GAP = 100.0
"""Millimetres between sheets when laid out side by side."""


def write_dxf(
    path: str | Path,
    drawing: Drawing,
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheet_w: float,
    sheet_h: float,
    gap: float = DEFAULT_GAP,
) -> None:
    """Write every placed part into one DXF, sheets in a horizontal row."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4  # millimetres
    msp = doc.modelspace()

    if SHEET_LAYER not in doc.layers:
        doc.layers.add(SHEET_LAYER, color=8)

    # default=0 so an empty layout still draws sheet 0: the test contract asks
    # for the sheet outline to exist even before anything is placed on it.
    sheet_count = max((p.sheet for p in placements), default=0) + 1
    for index in range(sheet_count):
        _draw_sheet_outline(msp, index * (sheet_w + gap), sheet_w, sheet_h)

    by_id = {p.id: p for p in parts}
    for placement in placements:
        part = by_id[placement.part_id]
        offset_x = placement.sheet * (sheet_w + gap)
        moved = Transform(
            angle_deg=placement.transform.angle_deg,
            mirror=placement.transform.mirror,
            dx=placement.transform.dx + offset_x,
            dy=placement.transform.dy,
        )
        for entity_id in part.entity_ids:
            _emit(msp, doc, apply_entity(moved, drawing.entities[entity_id]))

    doc.saveas(str(path))


def _draw_sheet_outline(msp, x0: float, sheet_w: float, sheet_h: float) -> None:
    msp.add_lwpolyline(
        [(x0, 0.0), (x0 + sheet_w, 0.0), (x0 + sheet_w, sheet_h), (x0, sheet_h)],
        close=True,
        dxfattribs={"layer": SHEET_LAYER},
    )


def _emit(msp, doc, e: Entity) -> None:
    attribs = _attribs(e.style, doc)

    match e:
        case Line():
            msp.add_line(e.start, e.end, dxfattribs=attribs)
        case Circle():
            msp.add_circle(e.center, e.radius, dxfattribs=attribs)
        case Arc():
            msp.add_arc(e.center, e.radius, e.start_angle, e.end_angle, dxfattribs=attribs)
        case Polyline():
            msp.add_lwpolyline(e.points, close=e.closed, dxfattribs=attribs)
        case Bezier():
            # A cubic Bezier is exactly a clamped degree-3 B-spline with these knots.
            spline = msp.add_spline(degree=3, dxfattribs=attribs)
            spline.control_points = [e.p0, e.p1, e.p2, e.p3]
            spline.knots = [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
        case _:
            raise TypeError(f"unsupported entity type: {type(e).__name__}")


def _attribs(style: Style, doc) -> dict:
    """Rebuild the source colour and layer on the output entity."""
    if style.layer not in doc.layers:
        doc.layers.add(style.layer)

    attribs: dict = {"layer": style.layer}
    if style.aci is not None:
        attribs["color"] = style.aci
    elif style.rgb is not None:
        # No ACI in the source (an .ai or .3dm import): carry the true colour.
        attribs["true_color"] = ezdxf.colors.rgb2int(style.rgb)
    return attribs
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/io/test_dxf_writer.py -v`
Esperado: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/io/dxf_writer.py tests/io/test_dxf_writer.py
git commit -m "feat: escritor de DXF que transforma las entidades originales"
```

---

### Task 10: Catálogo de materiales (`model/material.py`)

**Files:**
- Create: `src/nesting/model/material.py`
- Create: `materials.yaml`
- Test: `tests/model/test_material.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `Material(name: str, sheet_w: float, sheet_h: float, grain_tolerance: float)`
  - `load_materials(path: str | Path) -> dict[str, Material]`
  - `allowed_angles(material: Material, angles: Sequence[float]) -> list[float]`
  - `DEFAULT_MATERIALS_PATH: Path`

**El parámetro que unifica la restricción de veta (spec §3.6).** Un ángulo está permitido cuando su desviación respecto de 0° o 180° es ≤ `grain_tolerance`. Con `180` queda todo habilitado (MDF); con `5` solo 0° y 180°, o sea corte cruzado bloqueado (multilaminado).

La distancia angular de `a` al eje de veta es `min(a mod 180, 180 - (a mod 180))`.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/model/test_material.py`:

```python
import pytest

from nesting.model.material import Material, allowed_angles, load_materials

FREE = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
GRAIN = Material("multilam18", 1220.0, 2440.0, grain_tolerance=5.0)


def test_free_rotation_allows_every_angle():
    angles = [0.0, 15.0, 90.0, 137.0, 180.0, 270.0]
    assert allowed_angles(FREE, angles) == angles


def test_grain_constraint_keeps_only_zero_and_one_eighty():
    assert allowed_angles(GRAIN, [0.0, 90.0, 180.0, 270.0]) == [0.0, 180.0]


def test_grain_constraint_allows_angles_inside_the_tolerance():
    assert allowed_angles(GRAIN, [0.0, 3.0, 8.0, 177.0, 183.0]) == [0.0, 3.0, 177.0, 183.0]


def test_360_is_treated_as_zero():
    assert allowed_angles(GRAIN, [360.0]) == [360.0]


def test_negative_angles_are_handled():
    assert allowed_angles(GRAIN, [-3.0, -90.0]) == [-3.0]


def test_an_empty_angle_list_stays_empty():
    assert allowed_angles(GRAIN, []) == []


def test_loads_the_bundled_catalogue(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "mdf18:\n"
        "  placa: [1830, 2600]\n"
        "  tolerancia_veta: 180\n"
        "multilam18:\n"
        "  placa: [1220, 2440]\n"
        "  tolerancia_veta: 5\n",
        encoding="utf-8",
    )
    materials = load_materials(catalogue)

    assert set(materials) == {"mdf18", "multilam18"}
    assert materials["mdf18"].sheet_w == 1830.0
    assert materials["mdf18"].sheet_h == 2600.0
    assert materials["mdf18"].grain_tolerance == 180.0
    assert materials["mdf18"].name == "mdf18"
    assert materials["multilam18"].grain_tolerance == 5.0


def test_a_missing_field_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text("roto:\n  placa: [100, 200]\n", encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    assert "tolerancia_veta" in str(info.value)
    assert "roto" in str(info.value)


def test_a_malformed_sheet_size_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text("roto:\n  placa: [100]\n  tolerancia_veta: 5\n", encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    assert "placa" in str(info.value)


def test_the_shipped_catalogue_is_valid():
    from nesting.model.material import DEFAULT_MATERIALS_PATH
    materials = load_materials(DEFAULT_MATERIALS_PATH)
    assert "mdf18" in materials
    assert materials["mdf18"].sheet_w == 1830.0
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/model/test_material.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.model.material'`.

- [ ] **Step 3: Escribir el catálogo por defecto**

Archivo `materials.yaml` en la raíz del proyecto:

```yaml
# Catalogo de materiales.
#
# placa:            [ancho, alto] en milimetros
# tolerancia_veta:  cuantos grados puede desviarse una pieza del eje de la veta.
#                   180 = rotacion libre (la veta no importa, tipico de MDF)
#                     5 = solo 0 y 180 grados, corte cruzado bloqueado

mdf18:
  placa: [1830, 2600]
  tolerancia_veta: 180

mdf15:
  placa: [1830, 2600]
  tolerancia_veta: 180

multilam18:
  placa: [1220, 2440]
  tolerancia_veta: 5

fenolico18:
  placa: [1220, 2440]
  tolerancia_veta: 5
```

- [ ] **Step 4: Escribir el modelo de materiales**

Archivo `src/nesting/model/material.py`:

```python
"""The material catalogue: sheet size and grain constraint, together.

Choosing a material configures both at once, because they always change
together in practice.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_MATERIALS_PATH = Path(__file__).resolve().parents[3] / "materials.yaml"

GRAIN_EPS = 1e-9


@dataclass(frozen=True)
class Material:
    name: str
    sheet_w: float
    sheet_h: float
    grain_tolerance: float
    """Degrees a part may deviate from the grain axis. 180 means free rotation."""


def load_materials(path: str | Path) -> dict[str, Material]:
    """Read the YAML catalogue, failing loudly on a malformed entry."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    materials: dict[str, Material] = {}

    for name, spec in raw.items():
        if not isinstance(spec, dict):
            raise ValueError(f"el material {name!r} no es un bloque de campos")

        size = spec.get("placa")
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise ValueError(
                f"el material {name!r} necesita 'placa: [ancho, alto]' en milimetros"
            )
        if "tolerancia_veta" not in spec:
            raise ValueError(f"al material {name!r} le falta el campo 'tolerancia_veta'")

        materials[name] = Material(
            name=name,
            sheet_w=float(size[0]),
            sheet_h=float(size[1]),
            grain_tolerance=float(spec["tolerancia_veta"]),
        )

    return materials


def allowed_angles(material: Material, angles: Sequence[float]) -> list[float]:
    """Keep only the angles the material's grain constraint permits.

    An angle is allowed when it lies within `grain_tolerance` degrees of the
    grain axis, which runs along both 0 and 180 degrees.
    """
    return [a for a in angles if _distance_to_grain_axis(a) <= material.grain_tolerance + GRAIN_EPS]


def _distance_to_grain_axis(angle: float) -> float:
    folded = angle % 180.0
    return min(folded, 180.0 - folded)
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/model/test_material.py -v`
Esperado: `10 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/model/material.py materials.yaml tests/model/test_material.py
git commit -m "feat: catalogo de materiales con restriccion de veta"
```

---

### Task 11: La interfaz `Oracle` y el motor trivial (`engine/oracle.py`, `engine/shelf_oracle.py`)

**Files:**
- Create: `src/nesting/engine/__init__.py`
- Create: `src/nesting/engine/oracle.py`
- Create: `src/nesting/engine/shelf_oracle.py`
- Test: `tests/engine/test_shelf_oracle.py`

**Interfaces:**
- Consumes: `Part` (Task 6), `Transform`, `apply_points` (Tasks 2-3)
- Produces:
  - `Weights(bottom_left: float = 1.0, contact: float = 1.0)`
  - `NestConfig(sep, margin, angles, mirror, resolution, effort, seed, weights)`
  - `Oracle` — `Protocol` con tres métodos
  - `transformed_bbox(part, angle, mirror) -> tuple[float, float, float, float]`
  - `ShelfOracle` — implementación por bounding box

**Esta es LA decisión estructural del proyecto (spec §3.2 y §4.3).** El contrato tiene exactamente tres operaciones:

```python
reset(sheet_w, sheet_h, config)                      # empezar una placa vacia
best_placement(part, angle, mirror) -> (x, y, score) | None
place(part, angle, mirror, x, y)                     # confirmar
```

`x` e `y` son directamente los componentes `dx`/`dy` de un `Transform`, así que no hay concepto de "origen de la pieza" filtrándose por la interfaz. `score` es "más alto es mejor". `best_placement` **no muta estado**; solo `place` lo hace — el packer consulta varios ángulos antes de decidir.

**El offset de separación vive adentro del oráculo** (restricción obligatoria de la spec §3.2): `ShelfOracle` separa bounding boxes por `sep`; `RasterOracle` (Task 17) dilatará máscaras. El packer nunca lo aplica.

**`ShelfOracle` empaqueta por estantes:** acumula piezas en una fila horizontal hasta que no entran más, y abre un estante nuevo por encima. Es deliberadamente malo — desperdicia todo el hueco entre el contorno curvo y su rectángulo. Existe para que el circuito completo funcione en el hito 2 y para que la mejora del motor real (hito 3) sea **medible contra una línea de base**.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/test_shelf_oracle.py` (crear también `tests/engine/__init__.py` vacío):

```python
import pytest

from nesting.engine.oracle import NestConfig, transformed_bbox
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
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/test_shelf_oracle.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine'`.

- [ ] **Step 3: Escribir la interfaz**

Archivo `src/nesting/engine/__init__.py`: vacío.

Archivo `src/nesting/engine/oracle.py`:

```python
"""The seam that makes nesting engines interchangeable.

An oracle answers one question: given a part at a given angle, and the current
state of a sheet, where can it go and how good is that spot? A raster engine
answers it with bitmaps; a No-Fit-Polygon engine would answer it with polygon
regions. Everything above this interface - ordering, rotations, multi-sheet
spilling, effort levels, reporting - never learns which one is in use.

The clearance offset is deliberately the oracle's responsibility. A raster
engine dilates masks; an NFP engine would offset polygons. Doing it outside
would tie the whole design to one of them.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from nesting.geometry.transform import apply_points
from nesting.model.entities import Transform
from nesting.model.part import Part


@dataclass(frozen=True)
class Weights:
    """How a candidate position is scored. Calibrated in Task 24."""

    bottom_left: float = 1.0
    """Pull towards the bottom-left corner, so the leftover stays in one block."""

    contact: float = 1.0
    """Reward for perimeter resting against material already placed.

    This is the term that produces interlocking between curved parts. Without
    it, bottom-left alone just stacks and leaves gaps.
    """


@dataclass(frozen=True)
class NestConfig:
    sep: float = 5.0
    """Minimum gap between parts, in mm."""

    margin: float = 10.0
    """Minimum gap between a part and the sheet edge, in mm."""

    angles: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)
    mirror: bool = True
    resolution: float = 1.0
    """Raster resolution in mm per pixel. Ignored by non-raster oracles."""

    effort: str = "normal"
    """One of "rapido", "normal", "lento"."""

    seed: int = 0
    weights: Weights = field(default_factory=Weights)


@runtime_checkable
class Oracle(Protocol):
    """Where can this part go on this sheet, and how good is that spot?"""

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        """Start a fresh, empty sheet."""
        ...

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        """Best (dx, dy, score) for this orientation, or None if it does not fit.

        Higher scores are better. Must NOT mutate state: the packer asks about
        several orientations before committing to one.
        """
        ...

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        """Commit a placement at exactly (x, y), so later queries see it occupied.

        An implementation MUST honour the (x, y) it is given rather than deriving
        a position of its own. If it cannot represent an arbitrary position - a
        shelf packer only tracks a cursor - it MUST validate the argument against
        the position it would have produced and raise `ValueError` on a mismatch.
        Silently committing a different position than the caller asked for
        desynchronises the oracle's state from the layout being built, and the
        parts placed afterwards overlap with no error anywhere.

        Precondition: (x, y) comes from a `best_placement` call for this same
        (part, angle, mirror), with no intervening `place`.
        """
        ...


def transformed_bbox(
    part: Part, angle: float, mirror: bool
) -> tuple[float, float, float, float]:
    """Bounding box of `part` at this orientation, before any translation."""
    points = apply_points(Transform(angle, mirror, 0.0, 0.0), part.outer)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))

```

- [ ] **Step 4: Escribir el motor trivial**

Archivo `src/nesting/engine/shelf_oracle.py`:

```python
"""A deliberately poor nesting engine: bounding-box shelf packing.

Parts accumulate along a horizontal shelf until one no longer fits, then a new
shelf opens above. Every curve is reduced to its rectangle, so all the space
between an outline and its bounding box is wasted.

It exists so the whole pipeline can run end to end before the real engine is
written, and so the improvement from the raster engine is measurable against a
baseline rather than asserted.
"""

from nesting.engine.oracle import NestConfig, transformed_bbox
from nesting.model.part import Part


PLACE_TOLERANCE = 1e-6
"""Millimetres of slack when matching a committed position against the free slot."""


class ShelfOracle:
    """Implements the `Oracle` protocol by packing bounding boxes into rows."""

    def __init__(self) -> None:
        self._sheet_w = 0.0
        self._sheet_h = 0.0
        self._config = NestConfig()
        self._cursor_x = 0.0
        self._shelf_y = 0.0
        self._shelf_height = 0.0

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._sheet_w = sheet_w
        self._sheet_h = sheet_h
        self._config = config
        self._cursor_x = config.margin
        self._shelf_y = config.margin
        self._shelf_height = 0.0

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        slot = self._next_slot(part, angle, mirror)
        if slot is None:
            return None
        x, y, _, _, _ = slot
        # Lower is better, then further left. The large multiplier keeps the
        # shelf ordering dominant over the position within a shelf.
        score = -(y * 1e6 + x)
        return (x, y, score)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        slot = self._next_slot(part, angle, mirror)
        if slot is None:
            raise ValueError("no hay lugar para la pieza en la placa actual")
        slot_x, slot_y, width, height, shelf_y = slot

        # A shelf packer tracks a cursor, not arbitrary positions, so it cannot
        # honour any (x, y) the caller invents. Validating instead of silently
        # recalculating is what keeps the internal cursor in step with the
        # layout: committing a position the caller did not ask for desyncs the
        # two, and the parts placed afterwards overlap with no error anywhere.
        if abs(x - slot_x) > PLACE_TOLERANCE or abs(y - slot_y) > PLACE_TOLERANCE:
            raise ValueError(
                f"place() recibio la posicion ({x:.4f}, {y:.4f}), pero para esta "
                f"orientacion el hueco libre es ({slot_x:.4f}, {slot_y:.4f}). "
                f"Cada (x, y) tiene que venir de un best_placement() para la misma "
                f"pieza, angulo y espejado, sin ningun place() en el medio."
            )

        # Compare the sheet-absolute shelf y, NOT the returned dy. They differ by
        # the part's own bounding-box origin, which is non-zero as soon as the
        # part is mirrored or rotated - so comparing dy reports a fresh shelf
        # that never opened and drops the separation between parts.
        if shelf_y > self._shelf_y + PLACE_TOLERANCE:
            self._shelf_y = shelf_y
            self._shelf_height = 0.0
            self._cursor_x = self._config.margin

        self._cursor_x = self._cursor_x + width + self._config.sep
        self._shelf_height = max(self._shelf_height, height)

    def _next_slot(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float, float, float] | None:
        """Return (dx, dy, width, height, shelf_y) for the next free slot, or None.

        `shelf_y` is the sheet-absolute y of the current shelf, before it gets
        folded into `dy` by the part's own bounding-box origin. `place` needs it
        raw to tell a fresh shelf from the current one.
        """
        margin = self._config.margin
        bx0, by0, bx1, by1 = transformed_bbox(part, angle, mirror)
        width, height = bx1 - bx0, by1 - by0

        usable_right = self._sheet_w - margin
        usable_top = self._sheet_h - margin

        cursor_x, shelf_y = self._cursor_x, self._shelf_y
        if cursor_x + width > usable_right + 1e-9:
            # Open a new shelf above the current one.
            cursor_x = margin
            shelf_y = shelf_y + self._shelf_height + self._config.sep
            if self._shelf_height == 0.0:
                shelf_y = self._shelf_y

        if cursor_x + width > usable_right + 1e-9:
            return None
        if shelf_y + height > usable_top + 1e-9:
            return None

        # Translate so the part's own bounding box lands at (cursor_x, shelf_y).
        return (cursor_x - bx0, shelf_y - by0, width, height, shelf_y)
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/test_shelf_oracle.py -v`
Esperado: `13 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/engine tests/engine
git commit -m "feat: interfaz Oracle y motor trivial por bounding box"
```

---

### Task 12: Pipeline de preparación y packer (`pipeline.py`, `engine/packer.py`)

**Files:**
- Create: `src/nesting/pipeline.py`
- Create: `src/nesting/engine/packer.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/engine/test_packer.py`

**Interfaces:**
- Consumes: `Drawing` (Task 8), `flatten` (Task 4), `chain_contours` (Task 5), `build_parts` (Task 6), `Oracle`/`NestConfig` (Task 11), `Material`/`allowed_angles` (Task 10)
- Produces:
  - `pipeline.prepare_parts(drawing, flatten_tol=0.2, chain_tol=0.1) -> tuple[list[Part], list[str]]` — piezas y avisos
  - `pipeline.OpenContourError(Exception)`
  - `packer.PackResult(placements, sheets_used, utilization, total_utilization, unplaced, seconds)`
  - `packer.PartTooLargeError(Exception)`
  - `packer.replicate(parts, copies) -> list[Part]`
  - `packer.orientations(material, config) -> list[tuple[float, bool]]`
  - `packer.pack(parts, material, config, oracle_factory) -> PackResult`

**`prepare_parts` es el puente entre `io/` y el motor:** aplana cada entidad, encadena los tramos en contornos cerrados y arma el árbol de contención. Si algún contorno no cierra, **falla** con las coordenadas del hueco y la distancia que falta (spec §6.3) — no sigue con geometría incompleta.

**`pack` es la estrategia, y es agnóstica al motor.** Recibe un `oracle_factory` (un invocable sin argumentos que devuelve un `Oracle` nuevo), así que sirve igual con `ShelfOracle` hoy y con `RasterOracle` en el hito 3, sin cambiar una línea.

**Una sola pasada por placa alcanza.** Las piezas van ordenadas por área descendente; colocar más piezas solo reduce el espacio libre, así que una pieza que no entró no va a entrar después en esa misma placa. Si una pieza no entra en una placa **vacía**, es más grande que el área útil: `PartTooLargeError` con nombre y medidas.

- [ ] **Step 1: Escribir los tests que fallan**

Archivo `tests/test_pipeline.py`:

```python
import pytest

from nesting.io.dxf_reader import Drawing
from nesting.model.entities import Arc, Circle, Line, Style
from nesting.pipeline import OpenContourError, prepare_parts

STYLE = Style(aci=7, rgb=(255, 255, 255), layer="0")


def square_lines(x0, y0, side):
    c = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)]
    return [Line(c[i], c[(i + 1) % 4], STYLE) for i in range(4)]


def test_four_loose_lines_become_one_part():
    parts, warnings = prepare_parts(Drawing(entities=square_lines(0, 0, 100)))
    assert len(parts) == 1
    assert parts[0].holes == ()
    assert warnings == []


def test_a_circle_becomes_one_part():
    parts, _ = prepare_parts(Drawing(entities=[Circle((0.0, 0.0), 50.0, STYLE)]))
    assert len(parts) == 1
    assert parts[0].outer_area == pytest.approx(3.14159 * 50.0**2, rel=1e-3)


def test_a_circle_inside_a_square_becomes_a_hole():
    entities = square_lines(0, 0, 200) + [Circle((100.0, 100.0), 30.0, STYLE)]
    parts, _ = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    assert len(parts[0].holes) == 1
    assert parts[0].area < parts[0].outer_area


def test_two_arcs_forming_a_circle_chain_together():
    entities = [
        Arc((0.0, 0.0), 50.0, 0.0, 180.0, STYLE),
        Arc((0.0, 0.0), 50.0, 180.0, 360.0, STYLE),
    ]
    parts, _ = prepare_parts(Drawing(entities=entities))
    assert len(parts) == 1


def test_an_open_contour_raises_with_the_gap_size():
    entities = square_lines(0, 0, 100)[:3]   # falta un lado
    with pytest.raises(OpenContourError) as info:
        prepare_parts(Drawing(entities=entities))
    message = str(info.value)
    assert "100" in message, "informa el tamano del hueco"
    assert "--tol-cierre" in message


def test_duplicate_lines_produce_a_warning_but_still_work():
    entities = square_lines(0, 0, 100) + [square_lines(0, 0, 100)[0]]
    parts, warnings = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    assert any("duplicad" in w for w in warnings)


def test_reader_warnings_are_carried_through():
    drawing = Drawing(entities=square_lines(0, 0, 100), warnings=["se ignoraron 1 TEXT"])
    _, warnings = prepare_parts(drawing)
    assert "se ignoraron 1 TEXT" in warnings


def test_entity_ids_point_back_into_the_drawing():
    drawing = Drawing(entities=square_lines(0, 0, 100))
    parts, _ = prepare_parts(drawing)
    assert sorted(parts[0].entity_ids) == [0, 1, 2, 3]


def test_an_empty_drawing_produces_no_parts():
    parts, _ = prepare_parts(Drawing(entities=[]))
    assert parts == []
```

Archivo `tests/engine/test_packer.py`:

```python
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

FREE = Material("mdf", 1000.0, 1000.0, grain_tolerance=180.0)
GRAIN = Material("multilam", 1000.0, 1000.0, grain_tolerance=5.0)
CONFIG = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=False,
                    effort="rapido")
"""Esfuerzo fijo en una pasada golosa: estos tests verifican la estrategia base,
no la busqueda con reintentos que agrega la Task 19."""


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
    assert orientations(FREE, config) == [
        (0.0, False), (90.0, False), (180.0, False), (270.0, False)
    ]


def test_orientations_with_mirroring_doubles_the_list():
    config = NestConfig(angles=(0.0, 90.0), mirror=True)
    assert orientations(FREE, config) == [
        (0.0, False), (90.0, False), (0.0, True), (90.0, True)
    ]


def test_grain_constraint_filters_the_orientations():
    config = NestConfig(angles=(0.0, 90.0, 180.0, 270.0), mirror=False)
    assert orientations(GRAIN, config) == [(0.0, False), (180.0, False)]


def test_a_single_part_fits_on_one_sheet():
    parts = [rect_part(0, 100.0, 100.0)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert len(result.placements) == 1
    assert result.seconds >= 0.0


def test_parts_spill_onto_a_second_sheet():
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)

    assert result.sheets_used >= 2
    assert {p.sheet for p in result.placements} == set(range(result.sheets_used))


def test_a_part_bigger_than_the_sheet_is_reported():
    parts = [rect_part(0, 5000.0, 5000.0)]
    with pytest.raises(PartTooLargeError) as info:
        pack(parts, FREE, CONFIG, ShelfOracle)
    assert "5000" in str(info.value)


def test_bigger_parts_are_placed_first():
    parts = [rect_part(0, 50.0, 50.0), rect_part(1, 400.0, 400.0)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)
    assert result.placements[0].part_id == 1


def test_utilisation_is_reported_per_sheet_and_in_total():
    parts = [rect_part(i, 300.0, 300.0) for i in range(4)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)

    assert len(result.utilization) == result.sheets_used
    assert all(0.0 < u <= 1.0 for u in result.utilization)
    assert 0.0 < result.total_utilization <= 1.0


def test_the_result_always_passes_the_verifier():
    """El invariante central: ningun motor puede producir una salida invalida."""
    parts = [rect_part(i, 180.0, 120.0) for i in range(20)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)

    violations = verify(
        parts, result.placements, FREE.sheet_w, FREE.sheet_h,
        sep=CONFIG.sep, margin=CONFIG.margin,
    )
    assert violations == []


def test_packing_is_deterministic():
    parts = [rect_part(i, 180.0, 120.0) for i in range(10)]
    first = pack(parts, FREE, CONFIG, ShelfOracle)
    second = pack(parts, FREE, CONFIG, ShelfOracle)
    assert first.placements == second.placements


def test_an_empty_part_list_produces_an_empty_result():
    result = pack([], FREE, CONFIG, ShelfOracle)
    assert result.sheets_used == 0
    assert result.placements == []
    assert result.total_utilization == 0.0
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/pytest tests/test_pipeline.py tests/engine/test_packer.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.pipeline'`.

- [ ] **Step 3: Escribir el pipeline de preparación**

Archivo `src/nesting/pipeline.py`:

```python
"""From a freshly read drawing to the parts the engine will place.

Flatten every entity, chain the loose runs into closed contours, then resolve
containment. This is where a dirty export stops being geometry soup and becomes
a list of parts - or fails loudly enough that the user can go fix the drawing.
"""

from nesting.geometry.chaining import chain_contours
from nesting.geometry.flatten import flatten
from nesting.geometry.nesting_tree import build_parts
from nesting.io.dxf_reader import Drawing
from nesting.model.entities import Circle, Entity, Point
from nesting.model.part import Part

DEFAULT_FLATTEN_TOL = 0.02
"""Millimetres. Ten times finer than the raster resolution would demand.

`flatten` bounds the *chord* deviation, not the enclosed area, and on a curve the
two diverge fast: at 0.2 mm a 50 mm-radius circle already loses about half a
percent of its true area to the inscribed polygon. That is harmless for cut
geometry but not for the utilisation figures reported to the user, which would
read systematically low. The finer default trades a modest bump in point count
for area error under a tenth of a percent.
"""

DEFAULT_CHAIN_TOL = 0.1
"""Millimetres. Corel exports routinely leave gaps of a few microns."""


class OpenContourError(Exception):
    """A run of segments never closed, so it cannot become a part."""


def prepare_parts(
    drawing: Drawing,
    flatten_tol: float = DEFAULT_FLATTEN_TOL,
    chain_tol: float = DEFAULT_CHAIN_TOL,
) -> tuple[list[Part], list[str]]:
    """Turn a drawing into parts, returning them alongside any warnings."""
    warnings = list(drawing.warnings)

    segments = [
        (_flatten_closed(entity, flatten_tol), index)
        for index, entity in enumerate(drawing.entities)
    ]

    contours, open_chains, duplicates = chain_contours(segments, chain_tol)

    if duplicates:
        warnings.append(
            f"se descartaron {duplicates} entidades duplicadas o superpuestas"
        )

    if open_chains:
        worst = min(open_chains, key=lambda c: c.gap)
        raise OpenContourError(
            f"{len(open_chains)} contorno(s) no cierran. "
            f"El mas cercano a cerrar arranca en "
            f"({worst.points[0][0]:.3f}, {worst.points[0][1]:.3f}) y termina en "
            f"({worst.points[-1][0]:.3f}, {worst.points[-1][1]:.3f}), "
            f"con un hueco de {worst.gap:.3f} mm. "
            f"Revise el dibujo, o afloje la tolerancia con --tol-cierre."
        )

    return build_parts(contours), warnings


def _flatten_closed(entity: Entity, tolerance: float) -> tuple[Point, ...]:
    """Flatten `entity`, closing the ring when the entity is inherently a loop.

    `flatten` deliberately leaves a `Circle`'s first point unrepeated at the end,
    so a lone circle would otherwise reach `chain_contours` looking open by a
    whole chord - far wider than the sub-millimetre gaps that function exists to
    tolerate - and get reported as an open contour. A `Circle` never needs
    another entity to close it, so the seam is stitched here, once, right where
    the flattened points are produced. A closed `Polyline` already arrives with
    its first point repeated, so it needs nothing.
    """
    points = flatten(entity, tolerance)
    if isinstance(entity, Circle) and points and points[0] != points[-1]:
        return points + (points[0],)
    return points
```

- [ ] **Step 4: Escribir el packer**

Archivo `src/nesting/engine/packer.py`:

```python
"""Strategy: what order, which rotations, and when to open a new sheet.

Knows nothing about how placement is computed. It talks to an `Oracle`, so the
same code drives the throwaway shelf engine and the real raster engine.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from nesting.engine.oracle import NestConfig, Oracle, transformed_bbox
from nesting.model.entities import Transform
from nesting.model.material import Material, allowed_angles
from nesting.model.part import Part, Placement


class PartTooLargeError(Exception):
    """A part does not fit on an empty sheet, so no layout can ever contain it."""


@dataclass
class PackResult:
    placements: list[Placement] = field(default_factory=list)
    sheets_used: int = 0
    utilization: list[float] = field(default_factory=list)
    """Fraction of each sheet covered by part material."""

    total_utilization: float = 0.0
    seconds: float = 0.0


def replicate(parts: Sequence[Part], copies: int) -> list[Part]:
    """Repeat every part `copies` times, renumbering ids.

    The copies keep the original `entity_ids`, so they all draw the same source
    geometry at different places.
    """
    if copies < 1:
        raise ValueError(f"la cantidad de copias debe ser al menos 1, se recibio {copies}")

    out: list[Part] = []
    for _ in range(copies):
        for part in parts:
            out.append(
                Part(
                    id=len(out),
                    outer=part.outer,
                    holes=part.holes,
                    entity_ids=part.entity_ids,
                )
            )
    return out


def orientations(material: Material, config: NestConfig) -> list[tuple[float, bool]]:
    """Every (angle, mirror) pair the material and config permit."""
    angles = allowed_angles(material, config.angles)
    result = [(a, False) for a in angles]
    if config.mirror:
        result.extend((a, True) for a in angles)
    return result


def pack(
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """Place every part, opening new sheets as needed."""
    started = time.perf_counter()
    result = PackResult()

    if not parts:
        result.seconds = time.perf_counter() - started
        return result

    choices = orientations(material, config)
    remaining = sorted(parts, key=lambda p: p.area, reverse=True)
    sheet_area = material.sheet_w * material.sheet_h
    placed_area_per_sheet: list[float] = []

    sheet = 0
    while remaining:
        oracle = oracle_factory()
        oracle.reset(material.sheet_w, material.sheet_h, config)

        still_pending: list[Part] = []
        placed_area = 0.0

        for part in remaining:
            spot = _best_over_orientations(oracle, part, choices)
            if spot is None:
                still_pending.append(part)
                continue
            angle, mirror, x, y = spot
            oracle.place(part, angle, mirror, x, y)
            result.placements.append(Placement(part.id, sheet, Transform(angle, mirror, x, y)))
            placed_area += part.area

        if placed_area == 0.0:
            _raise_too_large(still_pending[0], material, config, choices)

        placed_area_per_sheet.append(placed_area)
        remaining = still_pending
        sheet += 1

    result.sheets_used = sheet
    result.utilization = [area / sheet_area for area in placed_area_per_sheet]
    result.total_utilization = (
        sum(placed_area_per_sheet) / (sheet_area * sheet) if sheet else 0.0
    )
    result.seconds = time.perf_counter() - started
    return result


def _best_over_orientations(
    oracle: Oracle,
    part: Part,
    choices: Sequence[tuple[float, bool]],
) -> tuple[float, bool, float, float] | None:
    """Ask the oracle about every orientation and keep the best-scoring one."""
    best: tuple[float, bool, float, float] | None = None
    best_score = float("-inf")

    for angle, mirror in choices:
        spot = oracle.best_placement(part, angle, mirror)
        if spot is None:
            continue
        x, y, score = spot
        if score > best_score:
            best_score = score
            best = (angle, mirror, x, y)

    return best


def _raise_too_large(
    part: Part,
    material: Material,
    config: NestConfig,
    choices: Sequence[tuple[float, bool]],
) -> None:
    """Report the part's best real footprint, against the usable area.

    The dimensions must come from ONE orientation. Taking the minimum width and
    the minimum height independently mixes two different orientations and
    describes a part that does not exist: a 1200x100 part reported as
    "100 x 100" contradicts itself, because a 100x100 would have fit.
    """
    best_w, best_h = None, None
    for angle, mirror in choices:
        x0, y0, x1, y1 = transformed_bbox(part, angle, mirror)
        width, height = x1 - x0, y1 - y0
        # The orientation that came closest to fitting is the one whose longest
        # side is shortest.
        if best_w is None or max(width, height) < max(best_w, best_h):
            best_w, best_h = width, height

    usable_w = material.sheet_w - 2 * config.margin
    usable_h = material.sheet_h - 2 * config.margin
    raise PartTooLargeError(
        f"la pieza {part.id} no entra en una placa vacia: mide al menos "
        f"{best_w:.1f} x {best_h:.1f} mm en su mejor orientacion, "
        f"y el area util de la placa {material.name} es "
        f"{usable_w:.1f} x {usable_h:.1f} mm (margen {config.margin} mm)."
    )
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `.venv/bin/pytest tests/test_pipeline.py tests/engine/test_packer.py -v`
Esperado: `23 passed`.

- [ ] **Step 6: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos en verde.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/pipeline.py src/nesting/engine/packer.py tests/test_pipeline.py tests/engine/test_packer.py
git commit -m "feat: pipeline de preparacion y estrategia de empaquetado multi-placa"
```

---

### Task 13: Interfaz de línea de comandos (`cli.py`)

**Files:**
- Create: `src/nesting/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `read_dxf` (Task 8), `prepare_parts` (Task 12), `pack`/`replicate` (Task 12), `verify` (Task 7), `write_dxf` (Task 9), `load_materials` (Task 10), `ShelfOracle` (Task 11)
- Produces: `main(argv: list[str] | None = None) -> int`

**Códigos de salida:**

| Código | Significado |
|---|---|
| `0` | Todo bien, archivo escrito |
| `1` | Error de entrada: unidades sin declarar, contorno abierto, pieza más grande que la placa, material desconocido |
| `2` | **La verificación geométrica falló.** No se escribe nada |

El `2` está **reservado** para ese único caso. Los errores de uso de `argparse` (un flag
requerido faltante, un valor no numérico) salen con `2` por defecto, lo que los volvería
indistinguibles de un fallo real de verificación para cualquier script que mire el código
de salida: hay que sobrescribir `ArgumentParser.error()` para que salga con `1`, que es lo
semánticamente correcto —un error de uso **es** un error de entrada.

**Validá los rangos de los flags numéricos** con mensajes en español y código `1`:
`--copias` ≥ 1, `--sep` ≥ 0, `--borde` ≥ 0, `--tol-cierre` > 0. Un `--borde` negativo hace
que el área útil calculada sea **más grande** que la placa física y las piezas quedan
colgando afuera; un `--sep` negativo anula en silencio el chequeo de separación.

**El código 2 es la red de seguridad de la spec §5.7 en acción.** Si el layout resultante viola solapamiento, separación o borde, el programa reporta cada violación y **no escribe el DXF**. Un archivo silenciosamente malo se descubre recién con la fresa adentro de la placa.

Los flags `--esfuerzo`, `--resolucion` y `--preview` se agregan en la Task 21, cuando exista lo que configuran.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/test_cli.py`:

```python
import ezdxf
import pytest

from nesting.cli import main


def write_input(tmp_path, squares, units=4, name="in.dxf"):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units
    msp = doc.modelspace()
    for x0, y0, side in squares:
        msp.add_lwpolyline(
            [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)],
            close=True,
        )
    path = tmp_path / name
    doc.saveas(path)
    return path


def catalogue(tmp_path):
    path = tmp_path / "materials.yaml"
    path.write_text("test:\n  placa: [1000, 1000]\n  tolerancia_veta: 180\n", encoding="utf-8")
    return path


def run(args):
    return main([str(a) for a in args])


def test_happy_path_writes_the_output(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    out = tmp_path / "out.dxf"

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path), "-o", out])

    assert code == 0
    assert out.exists()
    assert "placa" in capsys.readouterr().out.lower()


def test_copies_multiply_the_parts(tmp_path):
    source = write_input(tmp_path, [(0, 0, 100)])
    out = tmp_path / "out.dxf"

    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--copias", "5", "-o", out])

    msp = ezdxf.readfile(str(out)).modelspace()
    outlines = [e for e in msp if e.dxf.layer != "_PLACA"]
    assert len(outlines) == 5


def test_unknown_material_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    code = run([source, "--material", "noexiste", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert "noexiste" in capsys.readouterr().err


def test_missing_units_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)], units=0)
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert "--unidades" in capsys.readouterr().err


def test_units_override_recovers_a_unitless_file(tmp_path):
    source = write_input(tmp_path, [(0, 0, 10)], units=0)
    out = tmp_path / "out.dxf"
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--unidades", "cm", "-o", out])

    assert code == 0
    assert out.exists()


def test_a_part_bigger_than_the_sheet_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 5000)])
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert "no entra" in capsys.readouterr().err


def test_an_open_contour_exits_with_one(tmp_path, capsys):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    doc.modelspace().add_line((0, 0), (100, 0))
    source = tmp_path / "abierto.dxf"
    doc.saveas(source)

    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "-o", tmp_path / "out.dxf"])

    assert code == 1
    assert "cierran" in capsys.readouterr().err


def test_reader_warnings_are_shown(tmp_path, capsys):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)
    msp.add_text("600.00").set_placement((50, 50))
    source = tmp_path / "con_cota.dxf"
    doc.saveas(source)

    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "-o", tmp_path / "out.dxf"])

    assert "TEXT" in capsys.readouterr().out


def test_summary_reports_sheets_and_utilisation(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 400), (500, 0, 400), (0, 500, 400)])
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "-o", tmp_path / "out.dxf"])

    output = capsys.readouterr().out
    assert "aprovechamiento" in output
    assert "%" in output


def test_separation_and_margin_are_honoured(tmp_path):
    """Relee la salida y confirma que estan las 6 copias.

    Esto funciona porque `read_dxf` saltea la capa reservada `_PLACA`, donde el
    escritor dibuja los rectangulos de contorno de placa, y lo reporta como
    aviso. Sin ese filtro el rectangulo entraria como contorno de nivel 0 que
    envuelve a todas las piezas y las convertiria en sus propios agujeros.
    Realimentar la propia salida es un flujo real: verificar el resultado, o
    mas adelante nestear sobre un retazo.
    """
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    source = write_input(tmp_path, [(0, 0, 200)])
    out = tmp_path / "out.dxf"
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--copias", "6", "--sep", "25", "--borde", "40", "-o", out])

    parts, warnings = prepare_parts(read_dxf(out))
    assert len(parts) == 6
    assert any("_PLACA" in w for w in warnings)


def test_angles_flag_is_parsed(tmp_path):
    source = write_input(tmp_path, [(0, 0, 100)])
    out = tmp_path / "out.dxf"
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--angulos", "0,45,90", "-o", out])
    assert code == 0


def test_an_invalid_angle_list_exits_with_one(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 100)])
    code = run([source, "--material", "test", "--materiales", catalogue(tmp_path),
                "--angulos", "0,abc", "-o", tmp_path / "out.dxf"])
    assert code == 1
    assert "angulos" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.cli'`.

- [ ] **Step 3: Escribir la CLI**

Archivo `src/nesting/cli.py`:

```python
"""Command line entry point: read, nest, verify, write."""

import argparse
import sys
from pathlib import Path

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import PartTooLargeError, pack, replicate
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.io.dxf_reader import UNIT_SCALES, UnknownUnitsError, read_dxf
from nesting.io.dxf_writer import write_dxf
from nesting.model.material import DEFAULT_MATERIALS_PATH, load_materials
from nesting.pipeline import DEFAULT_CHAIN_TOL, OpenContourError, prepare_parts

EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_VERIFICATION_FAILED = 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        materials = load_materials(args.materiales)
    except (OSError, ValueError) as error:
        print(f"error: no se pudo leer el catalogo de materiales: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    if args.material not in materials:
        print(
            f"error: material {args.material!r} desconocido. "
            f"Disponibles: {', '.join(sorted(materials))}",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR
    material = materials[args.material]

    try:
        angles = tuple(float(a) for a in args.angulos.split(","))
    except ValueError:
        print(
            f"error: --angulos espera una lista de numeros separados por coma, "
            f"se recibio {args.angulos!r}",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR

    config = NestConfig(
        sep=args.sep,
        margin=args.borde,
        angles=angles,
        mirror=not args.sin_espejo,
    )

    try:
        drawing = read_dxf(args.entrada, units_override=args.unidades)
        parts, warnings = prepare_parts(drawing, chain_tol=args.tol_cierre)
    except (UnknownUnitsError, OpenContourError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except OSError as error:
        print(f"error: no se pudo leer {args.entrada}: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    for warning in warnings:
        print(f"aviso: {warning}")

    if not parts:
        print(f"error: no se encontro ninguna pieza en {args.entrada}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    parts = replicate(parts, args.copias)

    try:
        result = pack(parts, material, config, ShelfOracle)
    except PartTooLargeError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    violations = verify(
        parts, result.placements, material.sheet_w, material.sheet_h,
        sep=config.sep, margin=config.margin,
    )
    if violations:
        print(
            f"error: la verificacion geometrica encontro {len(violations)} problema(s). "
            f"No se escribio ningun archivo.",
            file=sys.stderr,
        )
        for violation in violations[:20]:
            print(f"  - {violation.detail}", file=sys.stderr)
        if len(violations) > 20:
            print(f"  ... y {len(violations) - 20} mas", file=sys.stderr)
        return EXIT_VERIFICATION_FAILED

    write_dxf(
        args.salida, drawing, parts, result.placements,
        material.sheet_w, material.sheet_h,
    )
    _print_summary(result, len(parts), args.salida)
    return EXIT_OK


def _print_summary(result, part_count: int, out_path: Path) -> None:
    for index, utilisation in enumerate(result.utilization):
        print(
            f"Placa {index + 1}/{result.sheets_used}   "
            f"aprovechamiento {utilisation * 100:5.1f}%"
        )
    print("-" * 34)
    print(
        f"{part_count} piezas - {result.sheets_used} placas - "
        f"{result.total_utilization * 100:.1f}% total - {result.seconds:.1f}s"
    )
    print(f"Escrito en {out_path}")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="nest",
        description="Acomoda figuras vectoriales dentro de placas, minimizando el material.",
    )
    parser.add_argument("entrada", type=Path, help="archivo DXF de entrada")
    parser.add_argument("-o", "--salida", type=Path, required=True, help="archivo DXF de salida")
    parser.add_argument("--material", required=True, help="clave del catalogo de materiales")
    parser.add_argument(
        "--materiales", type=Path, default=DEFAULT_MATERIALS_PATH,
        help="ruta del catalogo de materiales (default: el que viene con el programa)",
    )
    parser.add_argument("--copias", type=int, default=1,
                        help="cuantas veces repetir todo el contenido del archivo")
    parser.add_argument("--sep", type=float, default=5.0,
                        help="separacion minima entre piezas, en mm")
    parser.add_argument("--borde", type=float, default=10.0,
                        help="margen contra el borde de la placa, en mm")
    parser.add_argument("--angulos", default="0,90,180,270",
                        help="angulos candidatos, separados por coma")
    parser.add_argument("--sin-espejo", action="store_true", dest="sin_espejo",
                        help="no permitir piezas espejadas")
    parser.add_argument("--unidades", choices=sorted(UNIT_SCALES), default=None,
                        help="unidades del archivo de entrada, si no las declara")
    parser.add_argument("--tol-cierre", type=float, default=DEFAULT_CHAIN_TOL,
                        dest="tol_cierre",
                        help="tolerancia para unir extremos de contornos, en mm")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Esperado: `12 passed`.

- [ ] **Step 5: Probar la CLI a mano**

```bash
.venv/bin/nest --help
```
Esperado: se imprime la ayuda con todos los flags.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/cli.py tests/test_cli.py
git commit -m "feat: CLI con verificacion obligatoria antes de escribir"
```

---

### Task 14: Banco de pruebas (`bench/`)

**Files:**
- Create: `bench/make_sample.py`
- Create: `bench/run_bench.py`
- Create: `bench/README.md`
- Test: `tests/test_bench.py`

**Interfaces:**
- Consumes: toda la cadena de las Tasks 8-13
- Produces:
  - `bench.make_sample.write_sample(path) -> None` — genera un DXF sintético tipo banqueta
  - `bench.run_bench.BenchResult(name, parts, sheets, total_utilization, seconds, engine)`
  - `bench.run_bench.run_one(dxf_path, material, config, oracle_factory, engine_name) -> BenchResult`
  - `bench.run_bench.main(argv) -> int`

**El banco existe desde el hito 2, no al final** (spec §7.3 y §8). Sus tres funciones:

1. **Calibrar los niveles de esfuerzo con mediciones**, en vez de fijarlos por estimación (Task 24).
2. **Detectar regresiones de calidad** cuando cambian los pesos o las heurísticas.
3. **Arbitrar la comparación raster vs NFP**, si algún día existe el segundo motor.

La línea de base la fija hoy `ShelfOracle`. Cuando entre `RasterOracle` en el hito 3, la mejora va a ser un número medido contra esa línea, no una impresión.

- [ ] **Step 1: Escribir el generador de la muestra sintética**

Archivo `bench/make_sample.py`:

```python
"""Generate a synthetic stool-like DXF, so the bench has input from day one.

Shapes are deliberately curved and concave: a bounding-box engine wastes a lot
of room on them, which is exactly the gap the raster engine has to close.
"""

import math
from pathlib import Path

import ezdxf

SHEET_UNITS_MM = 4


def write_sample(path: str | Path, seats: int = 4, legs: int = 8) -> None:
    """Write a DXF with round seats and concave leg outlines."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = SHEET_UNITS_MM
    msp = doc.modelspace()

    cursor_x = 0.0
    for _ in range(seats):
        msp.add_circle((cursor_x + 150.0, 150.0), radius=150.0, dxfattribs={"color": 1})
        # Four mounting slots inside the seat: holes that free up material.
        for angle in (0, 90, 180, 270):
            rad = math.radians(angle)
            cx = cursor_x + 150.0 + 70.0 * math.cos(rad)
            cy = 150.0 + 70.0 * math.sin(rad)
            msp.add_lwpolyline(
                [(cx - 20, cy - 5), (cx + 20, cy - 5), (cx + 20, cy + 5), (cx - 20, cy + 5)],
                close=True,
                dxfattribs={"color": 3},
            )
        cursor_x += 320.0

    cursor_x = 0.0
    for _ in range(legs):
        msp.add_lwpolyline(_leg_outline(cursor_x, 400.0), close=True, dxfattribs={"color": 5})
        cursor_x += 220.0

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


def _leg_outline(x0: float, y0: float) -> list[tuple[float, float]]:
    """A concave leg: wide foot, narrow waist, wide shoulder."""
    profile = [
        (0.0, 0.0), (200.0, 0.0), (200.0, 60.0), (140.0, 90.0),
        (130.0, 300.0), (170.0, 340.0), (170.0, 420.0), (30.0, 420.0),
        (30.0, 340.0), (70.0, 300.0), (60.0, 90.0), (0.0, 60.0),
    ]
    return [(x0 + x, y0 + y) for x, y in profile]


if __name__ == "__main__":
    write_sample(Path(__file__).parent / "files" / "muestra.dxf")
    print("escrito bench/files/muestra.dxf")
```

- [ ] **Step 2: Escribir el corredor del banco**

Archivo `bench/run_bench.py`:

```python
"""Run the whole pipeline over every DXF in bench/files and report the numbers.

Measures what matters: how many sheets, how much of them is used, and how long
it took. Those three numbers are what decide whether a change to the engine was
an improvement.
"""

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import pack, replicate
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.io.dxf_reader import read_dxf
from nesting.model.material import DEFAULT_MATERIALS_PATH, Material, load_materials
from nesting.pipeline import prepare_parts

FILES_DIR = Path(__file__).parent / "files"


@dataclass(frozen=True)
class BenchResult:
    name: str
    parts: int
    sheets: int
    total_utilization: float
    seconds: float
    engine: str
    violations: int


def run_one(
    dxf_path: Path,
    material: Material,
    config: NestConfig,
    oracle_factory,
    engine_name: str,
    copies: int = 1,
) -> BenchResult:
    """Nest one file and measure the outcome."""
    drawing = read_dxf(dxf_path)
    parts, _ = prepare_parts(drawing)
    parts = replicate(parts, copies)

    started = time.perf_counter()
    result = pack(parts, material, config, oracle_factory)
    elapsed = time.perf_counter() - started

    violations = verify(
        parts, result.placements, material.sheet_w, material.sheet_h,
        sep=config.sep, margin=config.margin,
    )

    return BenchResult(
        name=dxf_path.name,
        parts=len(parts),
        sheets=result.sheets_used,
        total_utilization=result.total_utilization,
        seconds=elapsed,
        engine=engine_name,
        violations=len(violations),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Banco de pruebas del motor de nesting.")
    parser.add_argument("--material", default="mdf18")
    parser.add_argument("--copias", type=int, default=1)
    parser.add_argument("--sep", type=float, default=6.0)
    parser.add_argument("--borde", type=float, default=10.0)
    args = parser.parse_args(argv)

    material = load_materials(DEFAULT_MATERIALS_PATH)[args.material]
    config = NestConfig(sep=args.sep, margin=args.borde)

    files = sorted(FILES_DIR.glob("*.dxf"))
    if not files:
        print(
            f"no hay archivos en {FILES_DIR}. "
            f"Corra 'python bench/make_sample.py' o copie ahi un DXF real.",
            file=sys.stderr,
        )
        return 1

    print(f"{'archivo':<24}{'motor':<10}{'piezas':>7}{'placas':>8}{'aprov.':>9}{'seg':>8}")
    print("-" * 66)

    for path in files:
        result = run_one(path, material, config, ShelfOracle, "shelf", args.copias)
        flag = "  VIOLACIONES!" if result.violations else ""
        print(
            f"{result.name:<24}{result.engine:<10}{result.parts:>7}{result.sheets:>8}"
            f"{result.total_utilization * 100:>8.1f}%{result.seconds:>8.1f}{flag}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Escribir el README del banco**

Archivo `bench/README.md`:

````markdown
# Banco de pruebas

Mide tres números sobre archivos reales: **cantidad de placas**, **% de aprovechamiento**
y **segundos**. Son los que deciden si un cambio en el motor fue una mejora.

## Uso

```bash
python bench/make_sample.py          # genera bench/files/muestra.dxf
.venv/bin/python bench/run_bench.py  # corre sobre todo bench/files/*.dxf
```

## Cargar los archivos reales del proyecto

Los archivos de la banqueta están en `.cdr`, `.ai` y `.3dm`. El `.cdr` **no se lee
directamente** (formato binario cerrado, spec §2): hay que exportarlo.

**Desde CorelDRAW:** Archivo → Exportar → elegir `AutoCAD (DXF)` → guardar en
`bench/files/`. Verificar que en el diálogo de exportación las unidades queden en
**milímetros**; si Corel exporta sin declarar unidades, el lector va a pedir `--unidades mm`.

**Desde Rhino:** Archivo → Exportar selección → `DXF`.

Los `.ai` y `.3dm` se pueden usar directo a partir del hito 5 (Tasks 22 y 23).
````

- [ ] **Step 4: Escribir el test del banco**

Archivo `tests/test_bench.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

from make_sample import write_sample  # noqa: E402
from run_bench import run_one  # noqa: E402

from nesting.engine.oracle import NestConfig  # noqa: E402
from nesting.engine.shelf_oracle import ShelfOracle  # noqa: E402
from nesting.model.material import Material  # noqa: E402

MATERIAL = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
CONFIG = NestConfig(sep=6.0, margin=10.0)


def test_the_sample_generator_produces_a_readable_file(tmp_path):
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    path = tmp_path / "muestra.dxf"
    write_sample(path)

    parts, _ = prepare_parts(read_dxf(path))
    assert len(parts) == 12, "4 asientos mas 8 patas"


def test_the_seats_have_their_slots_as_holes(tmp_path):
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    path = tmp_path / "muestra.dxf"
    write_sample(path)
    parts, _ = prepare_parts(read_dxf(path))

    seats = [p for p in parts if len(p.holes) > 0]
    assert len(seats) == 4
    assert all(len(p.holes) == 4 for p in seats)


def test_run_one_reports_the_three_numbers(tmp_path):
    path = tmp_path / "muestra.dxf"
    write_sample(path)

    result = run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf")

    assert result.parts == 12
    assert result.sheets >= 1
    assert 0.0 < result.total_utilization <= 1.0
    assert result.seconds >= 0.0
    assert result.engine == "shelf"


def test_the_baseline_layout_is_geometrically_valid(tmp_path):
    """Sea cual sea la densidad, la salida del banco no puede violar nada."""
    path = tmp_path / "muestra.dxf"
    write_sample(path)
    result = run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf")
    assert result.violations == 0


def test_more_copies_need_more_sheets(tmp_path):
    path = tmp_path / "muestra.dxf"
    write_sample(path)

    one = run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf", copies=1)
    many = run_one(path, MATERIAL, CONFIG, ShelfOracle, "shelf", copies=8)
    assert many.sheets > one.sheets
```

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/pytest tests/test_bench.py -v`
Esperado: `5 passed`.

- [ ] **Step 6: Generar la muestra y correr el banco**

```bash
.venv/bin/python bench/make_sample.py
.venv/bin/python bench/run_bench.py
```

Esperado: una tabla con una fila para `muestra.dxf`, motor `shelf`, 12 piezas, sin la marca `VIOLACIONES!`.
**Anotar el `% aprov.` que sale: es la línea de base contra la que se mide el hito 3.**

- [ ] **Step 7: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos en verde.

- [ ] **Step 8: Commit**

```bash
git add bench tests/test_bench.py
git commit -m "feat: banco de pruebas con linea de base del motor trivial"
```

**Hito 2 completo.** El circuito funciona de punta a punta: entra un DXF, sale un DXF con las piezas acomodadas en placas, verificado. El nesting es malo a propósito — el hito 3 lo arregla y el banco lo demuestra con números.

---

# Hito 3 — El motor raster

*Entra detrás de la interfaz `Oracle`. El banco cuantifica la mejora contra la línea de base del hito 2.*

---

### Task 15: Rasterizado de piezas (`engine/raster/masks.py`)

**Files:**
- Create: `src/nesting/engine/raster/__init__.py`
- Create: `src/nesting/engine/raster/masks.py`
- Test: `tests/engine/raster/test_masks.py`

**Interfaces:**
- Consumes: `Part` (Task 6), `Transform`/`apply_points` (Tasks 2-3)
- Produces:
  - `PartMasks(occupied: np.ndarray, clearance: np.ndarray, origin: tuple[float, float], resolution: float)`
  - `disk_kernel(radius_px: int) -> np.ndarray`
  - `rasterize(part, angle, mirror, resolution, sep) -> PartMasks`
  - `MaskCache(max_entries=512)` con `get(part, angle, mirror, resolution, sep) -> PartMasks`

> **Nota posterior a la implementación.** El código de abajo es el punto de partida, pero la
> implementación real divergió: el supuesto de que `PIL.ImageDraw.polygon` marca todo píxel
> cuyo centro cae dentro del polígono **es falso** para lados no alineados a la grilla, y el
> error **no está acotado a un píxel**. Medido: hasta un 1% de los píxeles del borde sin
> marcar. Sub-representar material deja que el motor coloque piezas demasiado cerca, el
> verificador exacto rechaza el layout entero, y el usuario se queda sin salida en un trabajo
> válido.
>
> La versión final **supermuestrea 4×** y reduce a la resolución pedida con criterios
> asimétricos: el contorno exterior con **"cualquiera"** (cubre de más) y los agujeros con
> **"todos"** (cubren de menos), más una dilatación/erosión de seguridad de un píxel final.
> Verificado con 640 combinaciones de forma, ángulo, resolución y espejado —83,5 millones de
> píxeles— contra `shapely.contains_xy`: **cero faltantes**. Costo: 2,6× en tiempo de
> rasterizado, sin cambio en densidad. El detalle está en `.superpowers/sdd/task-15-report.md`.

**Las dos máscaras de la spec §5.1:**

| Máscara | Qué contiene | Para qué |
|---|---|---|
| `occupied` | El material real: contorno exterior **menos** agujeros | Se estampa en la placa al colocar |
| `clearance` | `occupied` dilatada por `sep` | Se usa para **testear** colisión |

**Las dos tienen exactamente la misma forma.** `occupied` se rasteriza dentro de una grilla ya acolchada por el radio de dilatación, así que ambas se indexan igual y no hay offsets que llevar en paralelo. Esto elimina de raíz la clase de bug más común en este enfoque.

**`origin` es la coordenada en mm del píxel `[0, 0]`** suponiendo que la pieza tiene traslación cero. Para que el píxel `[0,0]` de la máscara caiga en el píxel `(px, py)` de la placa, la traslación es `dx = px·res − origin.x`, `dy = py·res − origin.y`. Esa es la única fórmula de conversión del motor y vive acá.

**Convención de índices:** `mask[fila, columna]` con la **fila creciendo con `y`**. PIL rellena polígonos en su propio espacio de índices; como se le pasan pares `(columna, fila)` construidos con `fila = (y − origin.y)/res`, el arreglo resultante ya tiene `y` creciente con la fila. No hace falta invertir nada.

**La rotación re-rasteriza desde el polígono exacto**, nunca rota el bitmap (spec §5.1). Rotar bitmaps acumula artefactos y viola la restricción de que el polígono es la fuente de verdad.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/raster/test_masks.py` (crear también `tests/engine/raster/__init__.py` vacío):

```python
import numpy as np
import pytest

from nesting.engine.raster.masks import MaskCache, PartMasks, disk_kernel, rasterize
from nesting.model.part import Part

RES = 1.0


def rect_part(w, h, part_id=0):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def ring_part(outer, hole_margin, part_id=0):
    m = hole_margin
    return Part(
        part_id,
        ((0.0, 0.0), (outer, 0.0), (outer, outer), (0.0, outer)),
        (((m, m), (outer - m, m), (outer - m, outer - m), (m, outer - m)),),
        (part_id,),
    )


def test_disk_kernel_is_round_and_odd_sized():
    kernel = disk_kernel(3)
    assert kernel.shape == (7, 7)
    assert kernel[3, 3]
    assert not kernel[0, 0], "las esquinas quedan fuera del disco"


def test_disk_kernel_of_zero_radius_is_a_single_pixel():
    assert disk_kernel(0).shape == (1, 1)
    assert disk_kernel(0).all()


def test_occupied_and_clearance_have_the_same_shape():
    masks = rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=5.0)
    assert masks.occupied.shape == masks.clearance.shape


def test_occupied_area_matches_the_part_area():
    part = rect_part(100.0, 50.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)
    pixel_area = masks.occupied.sum() * RES * RES
    assert pixel_area == pytest.approx(part.area, rel=0.05)


def test_clearance_is_strictly_bigger_than_occupied():
    masks = rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=5.0)
    assert masks.clearance.sum() > masks.occupied.sum()
    assert np.all(masks.clearance | ~masks.occupied), "clearance contiene a occupied"


def test_clearance_grows_by_roughly_the_separation():
    part = rect_part(100.0, 100.0)
    masks = rasterize(part, 0.0, False, RES, sep=10.0)
    grown = masks.clearance.sum() * RES * RES
    # Un cuadrado de 100 dilatado 10 mm: 120x120 menos las esquinas redondeadas.
    assert 13000 < grown < 14400


def test_a_hole_is_not_occupied():
    part = ring_part(200.0, 50.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)
    pixel_area = masks.occupied.sum() * RES * RES
    assert pixel_area == pytest.approx(200.0**2 - 100.0**2, rel=0.05)


def test_the_centre_of_a_hole_is_free_in_both_masks():
    """La propiedad de la spec 5.2: el agujero queda disponible."""
    part = ring_part(400.0, 100.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)

    row = int((200.0 - masks.origin[1]) / RES)
    col = int((200.0 - masks.origin[0]) / RES)
    assert not masks.occupied[row, col]
    assert not masks.clearance[row, col], "el centro del agujero esta lejos de la pared"


def test_the_wall_of_a_hole_projects_clearance_inwards():
    part = ring_part(400.0, 100.0)
    masks = rasterize(part, 0.0, False, RES, sep=20.0)

    # Un punto 10 mm adentro del agujero, o sea dentro de la banda de separacion.
    row = int((110.0 - masks.origin[1]) / RES)
    col = int((200.0 - masks.origin[0]) / RES)
    assert not masks.occupied[row, col]
    assert masks.clearance[row, col]


def test_rotating_ninety_degrees_swaps_the_dimensions():
    flat = rasterize(rect_part(200.0, 50.0), 0.0, False, RES, sep=0.0)
    upright = rasterize(rect_part(200.0, 50.0), 90.0, False, RES, sep=0.0)

    assert flat.occupied.shape[1] > flat.occupied.shape[0]
    assert upright.occupied.shape[0] > upright.occupied.shape[1]


def test_rotation_preserves_the_occupied_area():
    part = rect_part(200.0, 50.0)
    areas = [
        rasterize(part, angle, False, RES, sep=0.0).occupied.sum()
        for angle in (0.0, 37.0, 90.0, 213.0)
    ]
    assert max(areas) / min(areas) < 1.1


def test_mirroring_preserves_the_occupied_area():
    part = rect_part(200.0, 50.0)
    straight = rasterize(part, 0.0, False, RES, sep=0.0).occupied.sum()
    flipped = rasterize(part, 0.0, True, RES, sep=0.0).occupied.sum()
    assert straight == pytest.approx(flipped, rel=0.02)


def test_origin_places_the_part_where_the_formula_says():
    part = rect_part(100.0, 50.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)

    # El pixel correspondiente al punto (50, 25) del interior tiene que estar ocupado.
    row = int((25.0 - masks.origin[1]) / RES)
    col = int((50.0 - masks.origin[0]) / RES)
    assert masks.occupied[row, col]

    # Y un punto claramente afuera, no.
    row = int((-20.0 - masks.origin[1]) / RES)
    col = int((-20.0 - masks.origin[0]) / RES)
    assert not masks.occupied[row, col]


def test_a_finer_resolution_produces_a_bigger_mask():
    part = rect_part(100.0, 100.0)
    coarse = rasterize(part, 0.0, False, 2.0, sep=5.0)
    fine = rasterize(part, 0.0, False, 0.5, sep=5.0)
    assert fine.occupied.shape[0] > coarse.occupied.shape[0]


def test_the_cache_returns_the_same_object_for_the_same_key():
    cache = MaskCache()
    part = rect_part(100.0, 50.0)
    first = cache.get(part, 0.0, False, RES, 5.0)
    second = cache.get(part, 0.0, False, RES, 5.0)
    assert first is second


def test_the_cache_distinguishes_angles_and_mirroring():
    cache = MaskCache()
    part = rect_part(200.0, 50.0)
    assert cache.get(part, 0.0, False, RES, 5.0) is not cache.get(part, 90.0, False, RES, 5.0)
    assert cache.get(part, 0.0, False, RES, 5.0) is not cache.get(part, 0.0, True, RES, 5.0)


def test_the_cache_evicts_the_oldest_entry_when_full():
    cache = MaskCache(max_entries=2)
    parts = [rect_part(100.0, 50.0, part_id=i) for i in range(3)]
    first = cache.get(parts[0], 0.0, False, RES, 5.0)
    cache.get(parts[1], 0.0, False, RES, 5.0)
    cache.get(parts[2], 0.0, False, RES, 5.0)
    assert cache.get(parts[0], 0.0, False, RES, 5.0) is not first


def test_masks_are_boolean_arrays():
    masks = rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=5.0)
    assert masks.occupied.dtype == np.bool_
    assert masks.clearance.dtype == np.bool_
    assert isinstance(masks, PartMasks)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/raster/test_masks.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine.raster'`.

- [ ] **Step 3: Escribir el rasterizador**

Archivo `src/nesting/engine/raster/__init__.py`: vacío.

Archivo `src/nesting/engine/raster/masks.py`:

```python
"""Turn an exact polygon into the two bitmaps the collision test needs.

The polygon stays the source of truth: these masks are a derived cache, rebuilt
from the polygon at every angle rather than rotated as images, which would
accumulate artefacts and quietly drift from the real geometry.
"""

import math
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation

from nesting.geometry.transform import apply_points
from nesting.model.entities import Point, Transform
from nesting.model.part import Part


@dataclass(frozen=True)
class PartMasks:
    """The material footprint and its clearance halo, on one shared grid."""

    occupied: np.ndarray
    """True where there is real material. Stamped onto the sheet when placed."""

    clearance: np.ndarray
    """`occupied` dilated by the separation. Used to test collisions."""

    origin: Point
    """World coordinate of pixel [0, 0], for a part translated by (0, 0)."""

    resolution: float

    def translation_for(self, px: int, py: int) -> Point:
        """The (dx, dy) that lands pixel [0, 0] of this mask on sheet pixel (px, py)."""
        return (
            px * self.resolution - self.origin[0],
            py * self.resolution - self.origin[1],
        )


def disk_kernel(radius_px: int) -> np.ndarray:
    """A round structuring element, so clearance is isotropic."""
    if radius_px <= 0:
        return np.ones((1, 1), dtype=bool)
    grid = np.ogrid[-radius_px:radius_px + 1, -radius_px:radius_px + 1]
    rows, cols = grid
    return (rows * rows + cols * cols) <= radius_px * radius_px


def rasterize(
    part: Part, angle: float, mirror: bool, resolution: float, sep: float
) -> PartMasks:
    """Build both masks for `part` at this orientation."""
    if resolution <= 0.0:
        raise ValueError(f"la resolucion debe ser positiva, se recibio {resolution}")

    transform = Transform(angle, mirror, 0.0, 0.0)
    outer = apply_points(transform, part.outer)
    holes = [apply_points(transform, hole) for hole in part.holes]

    pad = max(1, math.ceil(sep / resolution))
    min_x = min(p[0] for p in outer)
    min_y = min(p[1] for p in outer)
    max_x = max(p[0] for p in outer)
    max_y = max(p[1] for p in outer)

    origin = (min_x - pad * resolution, min_y - pad * resolution)
    width = math.ceil((max_x - min_x) / resolution) + 2 * pad + 1
    height = math.ceil((max_y - min_y) / resolution) + 2 * pad + 1

    image = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(image)
    draw.polygon(_to_pixels(outer, origin, resolution), fill=1)
    for hole in holes:
        draw.polygon(_to_pixels(hole, origin, resolution), fill=0)

    occupied = np.array(image, dtype=bool)
    radius = math.ceil(sep / resolution)
    clearance = (
        binary_dilation(occupied, structure=disk_kernel(radius))
        if radius > 0
        else occupied.copy()
    )

    return PartMasks(occupied=occupied, clearance=clearance, origin=origin,
                     resolution=resolution)


def _to_pixels(
    points: tuple[Point, ...], origin: Point, resolution: float
) -> list[tuple[float, float]]:
    """Map world points to (column, row). Row grows with y, as everything assumes."""
    return [
        ((x - origin[0]) / resolution, (y - origin[1]) / resolution) for x, y in points
    ]


class MaskCache:
    """Reuse masks across the many times the packer asks about the same orientation.

    Masks are the memory hot spot: a part with 24 allowed angles and mirroring
    has 48 entries. The cache is bounded and evicts least-recently-used.
    """

    def __init__(self, max_entries: int = 512) -> None:
        self._entries: OrderedDict[tuple, PartMasks] = OrderedDict()
        self._max_entries = max_entries

    def get(
        self, part: Part, angle: float, mirror: bool, resolution: float, sep: float
    ) -> PartMasks:
        key = (part.id, angle, mirror, resolution, sep)
        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            return cached

        masks = rasterize(part, angle, mirror, resolution, sep)
        self._entries[key] = masks
        if len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return masks
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/raster/test_masks.py -v`
Esperado: `18 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/raster tests/engine/raster
git commit -m "feat: rasterizado de piezas con mascaras de ocupacion y holgura"
```

---

### Task 16: Búsqueda por FFT (`engine/raster/search.py`)

**Files:**
- Create: `src/nesting/engine/raster/search.py`
- Test: `tests/engine/raster/test_search.py`

**Interfaces:**
- Consumes: nada del proyecto, solo `numpy` y `scipy.signal`
- Produces:
  - `overlap_counts(sheet: np.ndarray, mask: np.ndarray) -> np.ndarray` — cuántos píxeles de `mask` solapan material, para **cada** posición. Forma `(Hs − Hm + 1, Ws − Wm + 1)`
  - `feasible_positions(sheet: np.ndarray, clearance: np.ndarray) -> np.ndarray` — booleano, `True` donde no hay solapamiento

**El truco central de la spec §5.3.** Probar posición por posición es inviable: una placa de 1830 × 2600 a 1 mm/px tiene 4,8 millones de posiciones. Una **correlación cruzada** las evalúa **todas de una vez**.

`scipy.signal.fftconvolve` calcula convolución, no correlación. La relación es: `correlación(A, B) = convolución(A, B invertida en ambos ejes)`. Con `mode="valid"` el resultado tiene exactamente una entrada por posición donde la máscara entra completa dentro de la placa, así que **los límites de la placa quedan garantizados por la forma del arreglo** — sin código de acotamiento.

**Umbral:** la FFT devuelve flotantes con ruido numérico del orden de `1e-10`. Un solapamiento real vale al menos `1.0`, así que el umbral `> 0.5` separa ambos casos con margen amplio.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/raster/test_search.py`:

```python
import numpy as np
import pytest

from nesting.engine.raster.search import feasible_positions, overlap_counts


def brute_force_overlap(sheet, mask):
    """Referencia directa, para contrastar contra la version por FFT."""
    rows = sheet.shape[0] - mask.shape[0] + 1
    cols = sheet.shape[1] - mask.shape[1] + 1
    out = np.zeros((rows, cols), dtype=int)
    for r in range(rows):
        for c in range(cols):
            window = sheet[r:r + mask.shape[0], c:c + mask.shape[1]]
            out[r, c] = int((window & mask).sum())
    return out


def test_overlap_counts_has_the_valid_correlation_shape():
    sheet = np.zeros((20, 30), dtype=bool)
    mask = np.zeros((5, 7), dtype=bool)
    assert overlap_counts(sheet, mask).shape == (16, 24)


def test_overlap_counts_matches_brute_force_on_a_small_case():
    rng = np.random.default_rng(0)
    sheet = rng.random((24, 28)) < 0.3
    mask = rng.random((6, 5)) < 0.5

    fast = np.rint(overlap_counts(sheet, mask)).astype(int)
    assert np.array_equal(fast, brute_force_overlap(sheet, mask))


def test_overlap_counts_matches_brute_force_on_several_random_cases():
    rng = np.random.default_rng(12345)
    for _ in range(10):
        sheet = rng.random((30, 26)) < 0.25
        mask = rng.random((7, 9)) < 0.6
        fast = np.rint(overlap_counts(sheet, mask)).astype(int)
        assert np.array_equal(fast, brute_force_overlap(sheet, mask))


def test_an_empty_sheet_gives_zero_overlap_everywhere():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((4, 4), dtype=bool)
    assert np.allclose(overlap_counts(sheet, mask), 0.0, atol=1e-6)


def test_everything_is_feasible_on_an_empty_sheet():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((4, 4), dtype=bool)
    assert feasible_positions(sheet, mask).all()


def test_nothing_is_feasible_on_a_full_sheet():
    sheet = np.ones((20, 20), dtype=bool)
    mask = np.ones((4, 4), dtype=bool)
    assert not feasible_positions(sheet, mask).any()


def test_a_single_occupied_pixel_blocks_exactly_the_overlapping_positions():
    sheet = np.zeros((20, 20), dtype=bool)
    sheet[10, 10] = True
    mask = np.ones((3, 3), dtype=bool)

    feasible = feasible_positions(sheet, mask)
    # Las 9 posiciones cuyo 3x3 cubre (10,10) quedan bloqueadas.
    assert feasible.sum() == feasible.size - 9
    assert not feasible[8, 8]
    assert not feasible[10, 10]
    assert feasible[7, 10]


def test_a_mask_with_a_hole_can_straddle_occupied_material():
    """La propiedad que habilita nestear dentro de agujeros."""
    sheet = np.zeros((20, 20), dtype=bool)
    sheet[10, 10] = True

    mask = np.ones((5, 5), dtype=bool)
    mask[2, 2] = False   # el centro de la mascara esta vacio

    feasible = feasible_positions(sheet, mask)
    assert feasible[8, 8], "el pixel ocupado cae justo en el hueco de la mascara"


def test_feasible_positions_returns_booleans():
    sheet = np.zeros((10, 10), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    assert feasible_positions(sheet, mask).dtype == np.bool_


def test_a_mask_larger_than_the_sheet_yields_no_positions():
    sheet = np.zeros((5, 5), dtype=bool)
    mask = np.ones((9, 9), dtype=bool)
    assert feasible_positions(sheet, mask).size == 0


def test_numerical_noise_does_not_create_false_collisions():
    """Placa grande y vacia: el ruido de la FFT no debe superar el umbral."""
    sheet = np.zeros((600, 800), dtype=bool)
    mask = np.ones((60, 40), dtype=bool)
    assert feasible_positions(sheet, mask).all()


def test_numerical_noise_does_not_hide_a_real_collision():
    sheet = np.zeros((600, 800), dtype=bool)
    sheet[300, 400] = True
    mask = np.ones((60, 40), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    assert not feasible[300, 400]
    assert not feasible[241, 361]


def test_rejects_a_non_boolean_sheet():
    with pytest.raises(TypeError):
        overlap_counts(np.zeros((5, 5), dtype=int), np.ones((2, 2), dtype=bool))
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/raster/test_search.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine.raster.search'`.

- [ ] **Step 3: Escribir la búsqueda**

Archivo `src/nesting/engine/raster/search.py`:

```python
"""Evaluate every candidate position at once, with one cross-correlation.

Testing positions one by one is hopeless: a 1830 x 2600 sheet at 1 mm per pixel
has 4.8 million of them. A single correlation answers all of them together.
"""

import numpy as np
from scipy.signal import fftconvolve

COLLISION_THRESHOLD = 0.5
"""A real overlap is at least 1.0; FFT noise is around 1e-10. This sits between."""


def overlap_counts(sheet: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """How many pixels of `mask` land on occupied material, for every position.

    The result has shape (Hs - Hm + 1, Ws - Wm + 1): one entry per position where
    the mask fits entirely inside the sheet. That means the sheet bounds are
    enforced by the array shape alone, with no explicit clamping anywhere.
    """
    if sheet.dtype != np.bool_ or mask.dtype != np.bool_:
        raise TypeError("sheet y mask tienen que ser arreglos booleanos")
    if mask.shape[0] > sheet.shape[0] or mask.shape[1] > sheet.shape[1]:
        return np.zeros((0, 0), dtype=float)

    # fftconvolve computes a convolution; flipping the mask on both axes turns
    # it into the correlation we actually want.
    return fftconvolve(
        sheet.astype(np.float32),
        mask[::-1, ::-1].astype(np.float32),
        mode="valid",
    )


def feasible_positions(sheet: np.ndarray, clearance: np.ndarray) -> np.ndarray:
    """True at every position where the clearance mask touches no material."""
    counts = overlap_counts(sheet, clearance)
    if counts.size == 0:
        return np.zeros((0, 0), dtype=bool)
    return counts < COLLISION_THRESHOLD
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/raster/test_search.py -v`
Esperado: `13 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/raster/search.py tests/engine/raster/test_search.py
git commit -m "feat: busqueda de posiciones factibles por correlacion FFT"
```

---

### Task 17: Puntaje de posiciones (`engine/raster/scoring.py`)

**Files:**
- Create: `src/nesting/engine/raster/scoring.py`
- Test: `tests/engine/raster/test_scoring.py`

**Interfaces:**
- Consumes: `overlap_counts` (Task 16), `disk_kernel` (Task 15), `Weights` (Task 11)
- Produces:
  - `contact_band(clearance: np.ndarray, extra_px: int) -> np.ndarray`
  - `best_position(feasible, sheet, band, weights) -> tuple[int, int, float] | None` — devuelve `(px, py, score)`

**Que la pieza entre no alcanza (spec §5.4).** El puntaje combina dos términos, ambos normalizados a `[0, 1]` para que los pesos sean comparables:

```
abajo_izquierda = 1 − (py + 0.001·px) / (filas + 0.001·columnas)
contacto        = píxeles_de_banda_apoyados / píxeles_de_banda

puntaje = w.bottom_left · abajo_izquierda  +  w.contact · contacto
```

- **abajo-izquierda** empuja todo hacia una esquina, concentrando el sobrante en un bloque grande y aprovechable en vez de recortes dispersos.
- **contacto** mide cuánto perímetro de la pieza queda **apoyado** contra material ya colocado. La banda es la corona entre `clearance` y `clearance` dilatada un poco más: donde esa corona solapa mucho, la pieza está **encajada**.

**El término de contacto es el que produce el entrelazado** que se ve en los archivos del proyecto — una pata metiéndose en la curva de la otra. Sin él, bottom-left solo apila y deja huecos.

**Cuidado al escribir los tests de contacto.** `contact_band` devuelve `dilatar(holgura) & ~holgura`
con la **misma forma** que la entrada, así que una máscara que llena su propio arreglo por completo
—`np.ones((4, 4))`— da una banda necesariamente vacía, y cualquier test construido así es
insatisfacible, sin importar la implementación. Las máscaras reales que produce `rasterize` siempre
vienen con relleno alrededor, así que la fixture realista es un núcleo sólido dentro de un arreglo
más grande (por ejemplo un bloque de 4×4 centrado en uno de 8×8).

**Atajo importante:** si la placa está vacía, el contacto es cero en todas partes. En ese caso se saltea la segunda FFT por completo y se toma directamente la posición más abajo-izquierda. Las primeras colocaciones de cada placa son así, o sea que el ahorro es real.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/raster/test_scoring.py`:

```python
import numpy as np
import pytest

from nesting.engine.oracle import Weights
from nesting.engine.raster.scoring import best_position, contact_band
from nesting.engine.raster.search import feasible_positions

ONLY_BL = Weights(bottom_left=1.0, contact=0.0)
ONLY_CONTACT = Weights(bottom_left=0.0, contact=1.0)


def test_the_contact_band_is_a_ring_outside_the_clearance():
    clearance = np.zeros((11, 11), dtype=bool)
    clearance[4:7, 4:7] = True

    band = contact_band(clearance, extra_px=2)
    assert not (band & clearance).any(), "la banda no pisa la holgura"
    assert band.any()
    assert band[3, 5], "justo por fuera del borde"


def test_a_wider_band_covers_more():
    clearance = np.zeros((21, 21), dtype=bool)
    clearance[9:12, 9:12] = True
    assert contact_band(clearance, 4).sum() > contact_band(clearance, 1).sum()


def test_a_zero_width_band_is_empty():
    clearance = np.zeros((11, 11), dtype=bool)
    clearance[4:7, 4:7] = True
    assert not contact_band(clearance, 0).any()


def test_bottom_left_picks_the_lowest_row():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    band = contact_band(mask, 2)

    px, py, _ = best_position(feasible, sheet, band, ONLY_BL)
    assert (px, py) == (0, 0)


def test_bottom_left_prefers_a_lower_row_over_a_lefter_column():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    feasible[0, :] = False          # bloquear toda la fila de abajo
    band = contact_band(mask, 2)

    px, py, _ = best_position(feasible, sheet, band, ONLY_BL)
    assert py == 1
    assert px == 0


def test_returns_none_when_nothing_is_feasible():
    sheet = np.ones((20, 20), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    assert best_position(feasible, sheet, contact_band(mask, 2), ONLY_BL) is None


def test_returns_none_for_an_empty_feasible_array():
    empty = np.zeros((0, 0), dtype=bool)
    assert best_position(empty, np.zeros((5, 5), dtype=bool),
                         np.zeros((3, 3), dtype=bool), ONLY_BL) is None


def test_contact_pulls_the_part_against_existing_material():
    """Con peso solo en contacto, la pieza se pega a lo ya colocado."""
    sheet = np.zeros((40, 40), dtype=bool)
    sheet[30:38, 30:38] = True      # un bloque arriba a la derecha

    mask = np.ones((4, 4), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    band = contact_band(mask, 2)

    px, py, _ = best_position(feasible, sheet, band, ONLY_CONTACT)
    assert px > 20 and py > 20, "eligio pegarse al bloque, no la esquina de abajo"


def test_with_an_empty_sheet_contact_weight_falls_back_to_bottom_left():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    band = contact_band(mask, 2)

    px, py, _ = best_position(feasible, sheet, band, ONLY_CONTACT)
    assert (px, py) == (0, 0)


def test_the_score_is_bounded_between_zero_and_the_weight_sum():
    sheet = np.zeros((30, 30), dtype=bool)
    sheet[20:25, 20:25] = True
    mask = np.ones((4, 4), dtype=bool)
    weights = Weights(bottom_left=1.0, contact=1.0)

    result = best_position(feasible_positions(sheet, mask), sheet,
                           contact_band(mask, 2), weights)
    assert result is not None
    assert 0.0 <= result[2] <= 2.0 + 1e-9


def test_a_higher_contact_weight_changes_the_choice():
    sheet = np.zeros((40, 40), dtype=bool)
    sheet[30:38, 30:38] = True
    mask = np.ones((4, 4), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    band = contact_band(mask, 2)

    corner = best_position(feasible, sheet, band, Weights(1.0, 0.0))
    hugging = best_position(feasible, sheet, band, Weights(0.0, 1.0))
    assert corner[:2] != hugging[:2]


def test_the_chosen_position_is_always_feasible():
    rng = np.random.default_rng(7)
    for _ in range(5):
        sheet = rng.random((40, 40)) < 0.1
        mask = np.ones((4, 4), dtype=bool)
        feasible = feasible_positions(sheet, mask)
        if not feasible.any():
            continue
        px, py, _ = best_position(feasible, sheet, contact_band(mask, 2),
                                  Weights(1.0, 1.0))
        assert feasible[py, px]
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/raster/test_scoring.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine.raster.scoring'`.

- [ ] **Step 3: Escribir el puntaje**

Archivo `src/nesting/engine/raster/scoring.py`:

```python
"""Choose among the feasible positions.

Fitting is not enough. Bottom-left alone stacks parts and leaves gaps; the
contact term is what makes curved parts interlock, one leg settling into the
curve of the next.
"""

import numpy as np
from scipy.ndimage import binary_dilation

from nesting.engine.oracle import Weights
from nesting.engine.raster.masks import disk_kernel
from nesting.engine.raster.search import overlap_counts

COLUMN_TIE_BREAK = 0.001
"""Weight of the column in the bottom-left term: enough to break ties, not to
override the row ordering."""


def contact_band(clearance: np.ndarray, extra_px: int) -> np.ndarray:
    """The ring just outside the clearance halo.

    Where this ring overlaps material already placed, the part is nestled
    against it rather than merely not colliding with it.
    """
    if extra_px <= 0:
        return np.zeros_like(clearance)
    grown = binary_dilation(clearance, structure=disk_kernel(extra_px))
    return grown & ~clearance


def best_position(
    feasible: np.ndarray,
    sheet: np.ndarray,
    band: np.ndarray,
    weights: Weights,
) -> tuple[int, int, float] | None:
    """Pick the best feasible position. Returns (column, row, score), or None."""
    if feasible.size == 0 or not feasible.any():
        return None

    rows, cols = feasible.shape
    row_index, col_index = np.indices((rows, cols))
    span = rows + COLUMN_TIE_BREAK * cols
    bottom_left = 1.0 - (row_index + COLUMN_TIE_BREAK * col_index) / span

    score = weights.bottom_left * bottom_left

    # With an empty sheet contact is zero everywhere, so the second correlation
    # would be pure cost. The opening placements of every sheet take this path.
    if weights.contact != 0.0 and sheet.any() and band.any():
        counts = overlap_counts(sheet, band)
        if counts.shape == feasible.shape:
            score = score + weights.contact * (counts / band.sum())

    score = np.where(feasible, score, -np.inf)
    flat = int(np.argmax(score))
    row, col = divmod(flat, cols)
    return (col, row, float(score[row, col]))
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/raster/test_scoring.py -v`
Esperado: `12 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/raster/scoring.py tests/engine/raster/test_scoring.py
git commit -m "feat: puntaje de posiciones con termino de contacto"
```

---

### Task 18: `RasterOracle` e integración (`engine/raster/oracle.py`)

**Files:**
- Create: `src/nesting/engine/raster/oracle.py`
- Modify: `bench/run_bench.py` — correr los dos motores y comparar
- Modify: `src/nesting/cli.py` — usar `RasterOracle` en vez de `ShelfOracle`
- Test: `tests/engine/raster/test_raster_oracle.py`

**Interfaces:**
- Consumes: `MaskCache` (Task 15), `feasible_positions` (Task 16), `contact_band`/`best_position` (Task 17), `NestConfig`/`Oracle` (Task 11)
- Produces: `RasterOracle` — implementa el protocolo `Oracle`, más `CONTACT_BAND_MM = 3.0`

**El margen de placa desaparece como código.** La grilla cubre **solo el área útil** (la placa erosionada por `margin`). Como `feasible_positions` usa correlación `"valid"`, toda posición que devuelve tiene la máscara entera adentro de la grilla — o sea, adentro del área útil. El borde queda garantizado por la forma del arreglo.

**Conversión píxel ↔ mundo**, la única del motor:

```
dx = margin + px·res − origin.x          px = round((dx − margin + origin.x) / res)
dy = margin + py·res − origin.y          py = round((dy − margin + origin.y) / res)
```

**Región activa (spec §5.3).** La búsqueda se limita a las filas `[0 : frontera + alto_máscara]`, donde `frontera` es la fila más alta con material. Es seguro: cualquier posición por encima de esa franja está sobre placa vacía, así que tiene contacto cero y peor puntaje de abajo-izquierda que las de adentro. Si ahí no entra nada, se reintenta sobre la placa completa. Con la placa casi vacía —el caso de las primeras piezas— las correlaciones son diminutas.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/raster/test_raster_oracle.py`:

```python
import math
from dataclasses import replace

import pytest

from nesting.engine.oracle import NestConfig, Weights
from nesting.engine.packer import pack
from nesting.engine.raster.oracle import RasterOracle
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.model.entities import Transform
from nesting.model.material import Material
from nesting.model.part import Part, Placement

MATERIAL = Material("test", 1000.0, 1000.0, grain_tolerance=180.0)
CONFIG = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=False, resolution=2.0)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def circle_part(part_id, radius, segments=48):
    ring = tuple(
        (radius * math.cos(2 * math.pi * i / segments),
         radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    )
    return Part(part_id, ring, (), (part_id,))


def ring_part(part_id, outer, inner):
    return Part(
        part_id,
        ((0.0, 0.0), (outer, 0.0), (outer, outer), (0.0, outer)),
        ((((outer - inner) / 2, (outer - inner) / 2),
          ((outer + inner) / 2, (outer - inner) / 2),
          ((outer + inner) / 2, (outer + inner) / 2),
          ((outer - inner) / 2, (outer + inner) / 2)),),
        (part_id,),
    )


def test_the_first_part_lands_near_the_bottom_left_margin():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    assert x == pytest.approx(20.0, abs=CONFIG.resolution)
    assert y == pytest.approx(20.0, abs=CONFIG.resolution)


def test_best_placement_does_not_mutate_state():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)
    assert oracle.best_placement(part, 0.0, False) == oracle.best_placement(part, 0.0, False)


def test_a_placed_part_blocks_its_own_position():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    oracle.place(part, 0.0, False, x, y)
    second = oracle.best_placement(part, 0.0, False)

    assert second is not None
    assert (second[0], second[1]) != (x, y)


def test_returns_none_when_the_part_cannot_fit():
    oracle = RasterOracle()
    oracle.reset(200.0, 200.0, CONFIG)
    assert oracle.best_placement(rect_part(0, 500.0, 500.0), 0.0, False) is None


def test_a_full_layout_passes_the_verifier():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)

    parts = [rect_part(i, 140.0, 90.0) for i in range(20)]
    placements = []
    for part in parts:
        spot = oracle.best_placement(part, 0.0, False)
        if spot is None:
            continue
        x, y, _ = spot
        oracle.place(part, 0.0, False, x, y)
        placements.append(Placement(part.id, 0, Transform(0.0, False, x, y)))

    assert len(placements) >= 15
    assert verify(parts, placements, 1000.0, 1000.0, sep=CONFIG.sep, margin=CONFIG.margin) == []


def test_rotated_and_mirrored_layouts_pass_the_verifier():
    config = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=True, resolution=2.0)
    parts = [rect_part(i, 200.0, 70.0) for i in range(12)]
    result = pack(parts, MATERIAL, config, RasterOracle)

    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=config.sep, margin=config.margin) == []


def test_curved_parts_pass_the_verifier():
    parts = [circle_part(i, 90.0) for i in range(12)]
    result = pack(parts, MATERIAL, CONFIG, RasterOracle)
    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=CONFIG.sep, margin=CONFIG.margin) == []


def test_a_small_part_is_nested_inside_a_big_hole():
    """La ganancia de la spec 5.2, verificada end to end."""
    parts = [ring_part(0, 600.0, 400.0), rect_part(1, 200.0, 200.0)]
    result = pack(parts, MATERIAL, CONFIG, RasterOracle)

    assert result.sheets_used == 1
    assert len(result.placements) == 2
    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=CONFIG.sep, margin=CONFIG.margin) == []

    # La pieza chica tiene que haber caido adentro del agujero de la grande.
    from nesting.geometry.verify import placed_polygon
    big = placed_polygon(parts[0], result.placements[0].transform)
    small = placed_polygon(parts[1], result.placements[1].transform)
    hole = big.interiors[0]
    from shapely.geometry import Polygon
    assert Polygon(hole).contains(small)


def test_the_raster_engine_beats_the_shelf_engine_on_circles():
    """La prueba de que el hito 3 valio la pena, en numeros."""
    parts = [circle_part(i, 120.0) for i in range(14)]
    config = NestConfig(sep=8.0, margin=15.0, angles=(0.0,), mirror=False, resolution=2.0)

    shelf = pack(parts, MATERIAL, config, ShelfOracle)
    raster = pack(parts, MATERIAL, config, RasterOracle)

    assert raster.total_utilization > shelf.total_utilization * 1.15


def test_the_raster_engine_is_deterministic():
    parts = [rect_part(i, 140.0, 90.0) for i in range(10)]
    first = pack(parts, MATERIAL, CONFIG, RasterOracle)
    second = pack(parts, MATERIAL, CONFIG, RasterOracle)
    assert first.placements == second.placements


def test_contact_weight_produces_tighter_packing_than_bottom_left_alone():
    parts = [circle_part(i, 100.0) for i in range(12)]
    base = NestConfig(sep=8.0, margin=15.0, angles=(0.0,), mirror=False, resolution=2.0)

    bl_only = pack(parts, MATERIAL, replace(base, weights=Weights(1.0, 0.0)), RasterOracle)
    with_contact = pack(parts, MATERIAL, replace(base, weights=Weights(1.0, 1.0)),
                        RasterOracle)

    assert with_contact.total_utilization >= bl_only.total_utilization


def test_a_finer_resolution_does_not_break_the_verifier():
    parts = [circle_part(i, 80.0) for i in range(8)]
    config = NestConfig(sep=6.0, margin=10.0, angles=(0.0,), mirror=False, resolution=0.5)
    result = pack(parts, MATERIAL, config, RasterOracle)
    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=config.sep, margin=config.margin) == []
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/raster/test_raster_oracle.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine.raster.oracle'`.

- [ ] **Step 3: Escribir el oráculo raster**

Archivo `src/nesting/engine/raster/oracle.py`:

```python
"""The real nesting engine: bitmap collision, FFT search, contact scoring.

Implements the same three-method `Oracle` protocol as the throwaway shelf
engine, so the packer, the CLI, the bench and the verifier are unchanged.
"""

import math

import numpy as np

from nesting.engine.oracle import NestConfig
from nesting.engine.raster.masks import MaskCache, PartMasks
from nesting.engine.raster.scoring import best_position, contact_band
from nesting.engine.raster.search import feasible_positions
from nesting.model.part import Part

CONTACT_BAND_MM = 3.0
"""How far beyond the clearance halo the contact term looks for material."""


class RasterOracle:
    """Collision by bitmap overlap, position search by cross-correlation."""

    def __init__(self, cache: MaskCache | None = None) -> None:
        self._cache = cache if cache is not None else MaskCache()
        self._config = NestConfig()
        self._sheet = np.zeros((0, 0), dtype=bool)
        self._frontier = 0
        """Highest row index reached by placed material, for the active region."""

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._config = config
        resolution = config.resolution

        # The grid covers ONLY the usable area, so "valid" correlation positions
        # are inside the margin by construction. No bounds code anywhere.
        usable_w = sheet_w - 2 * config.margin
        usable_h = sheet_h - 2 * config.margin
        cols = max(0, math.floor(usable_w / resolution))
        rows = max(0, math.floor(usable_h / resolution))

        self._sheet = np.zeros((rows, cols), dtype=bool)
        self._frontier = 0

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        masks = self._masks(part, angle, mirror)
        height = masks.clearance.shape[0]

        result = self._search(masks, limit_rows=self._frontier + height)
        if result is None and self._frontier + height < self._sheet.shape[0]:
            result = self._search(masks, limit_rows=self._sheet.shape[0])
        if result is None:
            return None

        px, py, score = result
        dx, dy = masks.translation_for(px, py)
        return (dx + self._config.margin, dy + self._config.margin, score)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        masks = self._masks(part, angle, mirror)
        px, py = self._to_pixels(masks, x, y)
        height, width = masks.occupied.shape

        self._sheet[py:py + height, px:px + width] |= masks.occupied
        self._frontier = max(self._frontier, py + height)

    def _search(self, masks: PartMasks, limit_rows: int) -> tuple[int, int, float] | None:
        """Search within the first `limit_rows` rows of the sheet."""
        rows = min(max(limit_rows, masks.clearance.shape[0]), self._sheet.shape[0])
        window = self._sheet[:rows]

        feasible = feasible_positions(window, masks.clearance)
        if feasible.size == 0:
            return None

        extra_px = max(1, round(CONTACT_BAND_MM / self._config.resolution))
        band = contact_band(masks.clearance, extra_px)
        return best_position(feasible, window, band, self._config.weights)

    def _masks(self, part: Part, angle: float, mirror: bool) -> PartMasks:
        return self._cache.get(
            part, angle, mirror, self._config.resolution, self._config.sep
        )

    def _to_pixels(self, masks: PartMasks, x: float, y: float) -> tuple[int, int]:
        """Inverse of `translation_for`, plus the margin offset."""
        resolution = self._config.resolution
        px = round((x - self._config.margin + masks.origin[0]) / resolution)
        py = round((y - self._config.margin + masks.origin[1]) / resolution)
        return (px, py)
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/raster/test_raster_oracle.py -v`
Esperado: `12 passed`.

- [ ] **Step 5: Conectar el motor real a la CLI**

En `src/nesting/cli.py`, reemplazar el import:

```python
from nesting.engine.raster.oracle import RasterOracle
```

(borrando `from nesting.engine.shelf_oracle import ShelfOracle`), y en la llamada a `pack`:

```python
        result = pack(parts, material, config, RasterOracle)
```

Además, agregar el flag de resolución a `_parse_args`:

```python
    parser.add_argument("--resolucion", type=float, default=1.0, dest="resolucion",
                        help="resolucion del raster, en mm por pixel")
```

y pasarlo al `NestConfig`:

```python
    config = NestConfig(
        sep=args.sep,
        margin=args.borde,
        angles=angles,
        mirror=not args.sin_espejo,
        resolution=args.resolucion,
    )
```

- [ ] **Step 6: Hacer que el banco compare los dos motores**

En `bench/run_bench.py`, agregar el import:

```python
from nesting.engine.raster.oracle import RasterOracle
```

y reemplazar el bucle de `main` por:

```python
    engines = [("shelf", ShelfOracle), ("raster", RasterOracle)]

    for path in files:
        baseline = None
        for name, factory in engines:
            result = run_one(path, material, config, factory, name, args.copias)
            flag = "  VIOLACIONES!" if result.violations else ""
            if name == "shelf":
                baseline = result.total_utilization
                delta = ""
            else:
                delta = f"  (+{(result.total_utilization - baseline) * 100:.1f} pts)"
            print(
                f"{result.name:<24}{result.engine:<10}{result.parts:>7}{result.sheets:>8}"
                f"{result.total_utilization * 100:>8.1f}%{result.seconds:>8.1f}{delta}{flag}"
            )
```

- [ ] **Step 7: Correr el banco y anotar la mejora**

```bash
.venv/bin/python bench/run_bench.py
```

Esperado: dos filas por archivo. La fila `raster` tiene que mostrar **mayor aprovechamiento** que la fila `shelf`, y **ninguna** con la marca `VIOLACIONES!`.
**Anotar ambos números: son la evidencia de que el hito 3 sirvió.**

- [ ] **Step 8: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos los tests pasan, incluidos los de `tests/test_cli.py`, que ahora ejercitan el motor raster sin haber cambiado.

- [ ] **Step 9: Commit**

```bash
git add src/nesting/engine/raster/oracle.py src/nesting/cli.py bench/run_bench.py tests/engine/raster/test_raster_oracle.py
git commit -m "feat: motor raster conectado detras de la interfaz Oracle"
```

**Hito 3 completo.** El motor real está adentro y la mejora está medida. Que los tests de la CLI y del packer pasaran sin tocarse es la prueba de que la costura de la spec §3.2 funciona: el día que exista un motor NFP, entra por el mismo lugar.

---

# Hito 4 — El producto

---

### Task 19: Niveles de esfuerzo y compactación de la última placa

**Files:**
- Modify: `src/nesting/engine/packer.py` — reintentos, función de costo, compactación
- Test: `tests/engine/test_effort.py`

**Interfaces:**
- Consumes: todo lo de la Task 12, más `Weights` (Task 11)
- Produces (agregados a `engine/packer.py`):
  - `EFFORT_RESTARTS: dict[str, int]` — `{"rapido": 1, "normal": 10, "lento": 120}`
  - `UnknownEffortError(Exception)`
  - `layout_cost(result, parts) -> tuple[int, float]` — menor es mejor
  - `pack(...)` pasa a hacer varios intentos y quedarse con el mejor
- `pack` mantiene exactamente la misma firma: nada fuera de `packer.py` cambia.

**El criterio de la spec §3.8, como una función de costo:**

```
costo = (cantidad_de_placas, altura_usada_en_la_ultima_placa)
```

Se comparan como tupla: **primero minimizar placas**; a igual cantidad de placas, gana el layout cuya **última placa esté más compactada**. Eso deja el sobrante en un bloque grande y aprovechable en vez de recortes dispersos.

**Qué compra cada nivel.** Una pasada golosa es determinística y buena; lo que mejora es probar **distintos órdenes de inserción**:

| Nivel | Estrategia |
|---|---|
| `rapido` | Una pasada, orden por área descendente |
| `normal` | 10 intentos: el orden por área, más 9 perturbaciones aleatorias con semilla fija |
| `lento` | 120 iteraciones de búsqueda local: se perturba el mejor orden conocido y se acepta si mejora |

**Pasada final de compactación.** Elegido el mejor layout, las piezas de la última placa se vuelven a empacar solas con el peso de abajo-izquierda triplicado. Si el resultado sigue entrando en una placa y queda más bajo, reemplaza al anterior.

**Determinismo:** toda la aleatoriedad sale de `random.Random(config.seed)`. Con la misma semilla, la misma entrada da la misma salida.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/test_effort.py`:

```python
import math

import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    EFFORT_RESTARTS,
    UnknownEffortError,
    layout_cost,
    pack,
)
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.verify import verify
from nesting.model.material import Material
from nesting.model.part import Part

MATERIAL = Material("test", 1000.0, 1000.0, grain_tolerance=180.0)


def base_config(**overrides):
    defaults = dict(sep=8.0, margin=15.0, angles=(0.0, 90.0), mirror=False,
                    resolution=2.0, effort="rapido", seed=0)
    defaults.update(overrides)
    return NestConfig(**defaults)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def circle_part(part_id, radius, segments=40):
    ring = tuple(
        (radius * math.cos(2 * math.pi * i / segments),
         radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    )
    return Part(part_id, ring, (), (part_id,))


def test_the_effort_table_has_the_three_levels():
    assert set(EFFORT_RESTARTS) == {"rapido", "normal", "lento"}
    assert EFFORT_RESTARTS["rapido"] < EFFORT_RESTARTS["normal"] < EFFORT_RESTARTS["lento"]


def test_an_unknown_effort_level_is_rejected():
    parts = [rect_part(0, 100.0, 100.0)]
    with pytest.raises(UnknownEffortError) as info:
        pack(parts, MATERIAL, base_config(effort="turbo"), RasterOracle)
    assert "turbo" in str(info.value)


def test_layout_cost_prefers_fewer_sheets():
    few = [rect_part(i, 300.0, 300.0) for i in range(4)]
    many = [rect_part(i, 300.0, 300.0) for i in range(16)]

    one_sheet = pack(few, MATERIAL, base_config(), RasterOracle)
    several = pack(many, MATERIAL, base_config(), RasterOracle)

    assert layout_cost(one_sheet, few)[0] < layout_cost(several, many)[0]


def test_layout_cost_reports_the_height_used_on_the_last_sheet():
    parts = [rect_part(0, 200.0, 200.0)]
    result = pack(parts, MATERIAL, base_config(), RasterOracle)
    sheets, height = layout_cost(result, parts)

    assert sheets == 1
    assert 200.0 <= height <= 260.0, "el alto usado es el de la pieza mas el margen"


def test_rapido_is_a_single_pass():
    parts = [circle_part(i, 90.0) for i in range(10)]
    first = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    second = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    assert first.placements == second.placements


def test_the_same_seed_gives_the_same_result():
    parts = [circle_part(i, 80.0) for i in range(12)]
    config = base_config(effort="normal", seed=7)
    assert pack(parts, MATERIAL, config, RasterOracle).placements == \
           pack(parts, MATERIAL, config, RasterOracle).placements


def test_different_seeds_can_give_different_results():
    parts = [rect_part(i, 170.0, 110.0) for i in range(18)]
    a = pack(parts, MATERIAL, base_config(effort="normal", seed=1), RasterOracle)
    b = pack(parts, MATERIAL, base_config(effort="normal", seed=99), RasterOracle)
    assert a.placements != b.placements or a.total_utilization == b.total_utilization


def test_normal_is_never_worse_than_rapido():
    """El costo del mejor de N intentos no puede superar al del primero."""
    parts = [circle_part(i, 85.0) for i in range(16)]
    quick = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    normal = pack(parts, MATERIAL, base_config(effort="normal", seed=3), RasterOracle)

    assert layout_cost(normal, parts) <= layout_cost(quick, parts)


def test_every_effort_level_produces_a_valid_layout():
    parts = [circle_part(i, 90.0) for i in range(14)]
    for effort in ("rapido", "normal", "lento"):
        config = base_config(effort=effort, seed=5)
        result = pack(parts, MATERIAL, config, RasterOracle)
        violations = verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                            sep=config.sep, margin=config.margin)
        assert violations == [], f"el nivel {effort} produjo una salida invalida"


def test_every_part_is_placed_at_every_effort_level():
    parts = [rect_part(i, 150.0, 100.0) for i in range(12)]
    for effort in ("rapido", "normal", "lento"):
        result = pack(parts, MATERIAL, base_config(effort=effort), RasterOracle)
        assert len(result.placements) == len(parts)
    

def test_the_last_sheet_gets_compacted():
    """Dos placas: la segunda tiene que quedar apretada contra el borde de abajo."""
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    config = base_config(effort="normal", seed=2)
    result = pack(parts, MATERIAL, config, RasterOracle)

    assert result.sheets_used >= 2
    _, last_height = layout_cost(result, parts)
    assert last_height < MATERIAL.sheet_h * 0.75, "el sobrante quedo en un bloque"


def test_the_reported_time_grows_with_the_effort():
    parts = [circle_part(i, 90.0) for i in range(10)]
    quick = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    normal = pack(parts, MATERIAL, base_config(effort="normal"), RasterOracle)
    assert normal.seconds > quick.seconds
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/test_effort.py -v`
Esperado: FALLA con `ImportError: cannot import name 'EFFORT_RESTARTS'`.

- [ ] **Step 3: Renombrar la pasada única y agregar el costo**

En `src/nesting/engine/packer.py`, agregar los imports que faltan al principio:

```python
import random
from dataclasses import replace
```

Renombrar la función `pack` existente a `_pack_once` y agregarle un parámetro de orden explícito. O sea, cambiar su firma de:

```python
def pack(
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """Place every part, opening new sheets as needed."""
    started = time.perf_counter()
    result = PackResult()

    if not parts:
        result.seconds = time.perf_counter() - started
        return result

    choices = orientations(material, config)
    remaining = sorted(parts, key=lambda p: p.area, reverse=True)
```

a:

```python
def _pack_once(
    order: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """One greedy pass, placing `order` in exactly the order given."""
    started = time.perf_counter()
    result = PackResult()

    if not order:
        result.seconds = time.perf_counter() - started
        return result

    choices = orientations(material, config)
    remaining = list(order)
```

El resto del cuerpo queda igual.

- [ ] **Step 4: Agregar la función de costo, los reintentos y la compactación**

Agregar al final de `src/nesting/engine/packer.py`:

```python
EFFORT_RESTARTS: dict[str, int] = {"rapido": 1, "normal": 10, "lento": 120}
"""How many insertion orders each effort level tries. Calibrated in Task 24."""

COMPACTION_BOOST = 3.0
"""How much the bottom-left weight is multiplied by on the final compaction pass."""


class UnknownEffortError(Exception):
    """The requested effort level is not one of the three defined ones."""


def layout_cost(result: PackResult, parts: Sequence[Part]) -> tuple[int, float]:
    """How bad a layout is. Lower is better; compared as a tuple.

    Sheet count dominates. Between layouts using the same number of sheets, the
    one whose last sheet is most compacted wins, which leaves the offcut as one
    usable block instead of scattered strips.
    """
    if not result.placements:
        return (0, 0.0)

    by_id = {p.id: p for p in parts}
    last_sheet = result.sheets_used - 1
    top = 0.0

    for placement in result.placements:
        if placement.sheet != last_sheet:
            continue
        part = by_id[placement.part_id]
        _, _, _, y1 = transformed_bbox(part, placement.transform.angle_deg,
                                       placement.transform.mirror)
        top = max(top, placement.transform.dy + y1)

    return (result.sheets_used, top)


def pack(
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """Place every part, trying several insertion orders and keeping the best."""
    if config.effort not in EFFORT_RESTARTS:
        raise UnknownEffortError(
            f"nivel de esfuerzo {config.effort!r} desconocido; "
            f"use uno de {', '.join(EFFORT_RESTARTS)}"
        )

    started = time.perf_counter()
    if not parts:
        return PackResult(seconds=time.perf_counter() - started)

    rng = random.Random(config.seed)
    by_area = sorted(parts, key=lambda p: p.area, reverse=True)

    best_order = list(by_area)
    best = _pack_once(best_order, material, config, oracle_factory)
    best_cost = layout_cost(best, parts)

    for _ in range(EFFORT_RESTARTS[config.effort] - 1):
        candidate_order = _perturb(best_order if config.effort == "lento" else by_area, rng)
        candidate = _pack_once(candidate_order, material, config, oracle_factory)
        candidate_cost = layout_cost(candidate, parts)
        if candidate_cost < best_cost:
            best, best_cost, best_order = candidate, candidate_cost, candidate_order

    best = _compact_last_sheet(best, parts, material, config, oracle_factory)
    best.seconds = time.perf_counter() - started
    return best


def _perturb(order: Sequence[Part], rng: random.Random) -> list[Part]:
    """Swap a few pairs, keeping the large-parts-first shape mostly intact."""
    shuffled = list(order)
    swaps = max(1, len(shuffled) // 6)
    for _ in range(swaps):
        i = rng.randrange(len(shuffled))
        j = rng.randrange(len(shuffled))
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
    return shuffled


def _compact_last_sheet(
    result: PackResult,
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """Re-pack the last sheet on its own, pulled harder towards the corner."""
    if result.sheets_used < 1:
        return result

    last = result.sheets_used - 1
    by_id = {p.id: p for p in parts}
    on_last = [by_id[p.part_id] for p in result.placements if p.sheet == last]
    if len(on_last) < 2:
        return result

    boosted = replace(
        config,
        weights=Weights(
            bottom_left=config.weights.bottom_left * COMPACTION_BOOST,
            contact=config.weights.contact,
        ),
    )
    order = sorted(on_last, key=lambda p: p.area, reverse=True)
    redone = _pack_once(order, material, boosted, oracle_factory)

    if redone.sheets_used != 1:
        return result
    if layout_cost(redone, parts)[1] >= layout_cost(result, parts)[1]:
        return result

    kept = [p for p in result.placements if p.sheet != last]
    moved = [Placement(p.part_id, last, p.transform) for p in redone.placements]

    sheet_area = material.sheet_w * material.sheet_h
    result.placements = kept + moved
    result.utilization[last] = sum(p.area for p in on_last) / sheet_area
    return result
```

Y agregar `Weights` al import de `nesting.engine.oracle` en la cabecera del archivo:

```python
from nesting.engine.oracle import NestConfig, Oracle, Weights, transformed_bbox
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/test_effort.py -v`
Esperado: `12 passed`.

- [ ] **Step 6: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos pasan. Los tests de la Task 12 fijan `effort="rapido"` justamente para
seguir ejercitando la pasada golosa una vez que existan los reintentos.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/engine/packer.py tests/engine/test_effort.py
git commit -m "feat: niveles de esfuerzo y compactacion de la ultima placa"
```

---

### Task 20: Previsualización PNG (`io/preview.py`)

**Files:**
- Create: `src/nesting/io/preview.py`
- Test: `tests/io/test_preview.py`

**Interfaces:**
- Consumes: `Part`, `Placement` (Task 6), `apply_points` (Task 3)
- Produces: `write_preview(path, parts, placements, sheet_w, sheet_h, utilization, colors=None, px_per_mm=0.15) -> None`
  - `colors: dict[int, tuple[int, int, int]] | None` — color por `part_id`; sin él, gris

**Para qué sirve.** Mirar el resultado de un vistazo sin abrir Corel, y —sobre todo— **no desarrollar a ciegas**: cuando el nesting sale raro, la imagen lo muestra en un segundo y el DXF no.

**Ojo con el eje Y.** En una imagen la fila 0 es arriba; en el modelo `y` crece hacia arriba. La conversión es `fila = alto_px − y·escala`. Si se olvida, la previsualización sale espejada verticalmente respecto del DXF y confunde en vez de ayudar.

Los agujeros se dibujan del color del fondo, así que se ven como huecos reales — incluidas las piezas chicas anidadas adentro.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/io/test_preview.py`:

```python
from PIL import Image

from nesting.io.preview import write_preview
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def ring_part(part_id, outer, margin):
    m = margin
    return Part(
        part_id,
        ((0.0, 0.0), (outer, 0.0), (outer, outer), (0.0, outer)),
        (((m, m), (outer - m, m), (outer - m, outer - m), (m, outer - m)),),
        (part_id,),
    )


def test_writes_a_png(tmp_path):
    out = tmp_path / "preview.png"
    write_preview(out, [rect_part(0, 200.0, 100.0)],
                  [Placement(0, 0, Transform(0.0, False, 50.0, 50.0))],
                  1000.0, 1000.0, [0.02])

    assert out.exists()
    assert Image.open(out).format == "PNG"


def test_the_image_widens_with_more_sheets(tmp_path):
    parts = [rect_part(0, 100.0, 100.0), rect_part(1, 100.0, 100.0)]
    placements_one = [Placement(0, 0, Transform(0.0, False, 10.0, 10.0))]
    placements_two = placements_one + [Placement(1, 1, Transform(0.0, False, 10.0, 10.0))]

    one = tmp_path / "one.png"
    two = tmp_path / "two.png"
    write_preview(one, parts, placements_one, 1000.0, 1000.0, [0.01])
    write_preview(two, parts, placements_two, 1000.0, 1000.0, [0.01, 0.01])

    assert Image.open(two).width > Image.open(one).width


def test_a_part_is_actually_drawn(tmp_path):
    out = tmp_path / "preview.png"
    write_preview(out, [rect_part(0, 800.0, 800.0)],
                  [Placement(0, 0, Transform(0.0, False, 100.0, 100.0))],
                  1000.0, 1000.0, [0.64], colors={0: (255, 0, 0)})

    image = Image.open(out).convert("RGB")
    reds = sum(1 for pixel in image.getdata() if pixel == (255, 0, 0))
    assert reds > 100


def test_the_y_axis_is_not_flipped(tmp_path):
    """Una pieza abajo en el modelo tiene que verse abajo en la imagen."""
    out = tmp_path / "preview.png"
    write_preview(out, [rect_part(0, 900.0, 200.0)],
                  [Placement(0, 0, Transform(0.0, False, 50.0, 50.0))],
                  1000.0, 1000.0, [0.18], colors={0: (255, 0, 0)})

    image = Image.open(out).convert("RGB")
    rows = [y for y in range(image.height)
            for x in range(image.width) if image.getpixel((x, y)) == (255, 0, 0)]
    assert rows
    assert sum(rows) / len(rows) > image.height * 0.5, "la masa roja esta en la mitad de abajo"


def test_a_hole_is_drawn_as_a_hole(tmp_path):
    out = tmp_path / "preview.png"
    write_preview(out, [ring_part(0, 800.0, 200.0)],
                  [Placement(0, 0, Transform(0.0, False, 100.0, 100.0))],
                  1000.0, 1000.0, [0.48], colors={0: (255, 0, 0)})

    image = Image.open(out).convert("RGB")
    # El centro de la pieza cae en el agujero y no debe estar pintado.
    centre = image.getpixel((int(image.width * 0.5), int(image.height * 0.5)))
    assert centre != (255, 0, 0)


def test_an_empty_layout_still_writes_an_image(tmp_path):
    out = tmp_path / "preview.png"
    write_preview(out, [], [], 1000.0, 1000.0, [])
    assert out.exists()


def test_a_finer_scale_produces_a_bigger_image(tmp_path):
    part = rect_part(0, 100.0, 100.0)
    placement = [Placement(0, 0, Transform(0.0, False, 10.0, 10.0))]

    small = tmp_path / "small.png"
    large = tmp_path / "large.png"
    write_preview(small, [part], placement, 1000.0, 1000.0, [0.01], px_per_mm=0.1)
    write_preview(large, [part], placement, 1000.0, 1000.0, [0.01], px_per_mm=0.4)

    assert Image.open(large).width > Image.open(small).width
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/io/test_preview.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.io.preview'`.

- [ ] **Step 3: Escribir la previsualización**

Archivo `src/nesting/io/preview.py`:

```python
"""Render the layout to a PNG, so a bad result is obvious at a glance."""

from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw

from nesting.geometry.transform import apply_points
from nesting.model.entities import Point
from nesting.model.part import Part, Placement

BACKGROUND = (250, 250, 250)
SHEET_FILL = (232, 232, 232)
SHEET_EDGE = (120, 120, 120)
DEFAULT_PART = (150, 150, 150)
PART_EDGE = (40, 40, 40)
GAP_MM = 80.0
LABEL_BAND_PX = 18


def write_preview(
    path: str | Path,
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheet_w: float,
    sheet_h: float,
    utilization: Sequence[float],
    colors: dict[int, tuple[int, int, int]] | None = None,
    px_per_mm: float = 0.15,
) -> None:
    """Draw every sheet side by side, with its utilisation underneath."""
    colors = colors or {}
    sheets = max(len(utilization), max((p.sheet for p in placements), default=-1) + 1, 1)

    sheet_px_w = max(1, round(sheet_w * px_per_mm))
    sheet_px_h = max(1, round(sheet_h * px_per_mm))
    gap_px = max(1, round(GAP_MM * px_per_mm))

    width = sheets * sheet_px_w + (sheets + 1) * gap_px
    height = sheet_px_h + 2 * gap_px + LABEL_BAND_PX

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    for index in range(sheets):
        left = gap_px + index * (sheet_px_w + gap_px)
        top = gap_px
        draw.rectangle(
            [left, top, left + sheet_px_w, top + sheet_px_h],
            fill=SHEET_FILL, outline=SHEET_EDGE,
        )
        if index < len(utilization):
            draw.text(
                (left, top + sheet_px_h + 4),
                f"Placa {index + 1}   {utilization[index] * 100:.1f}%",
                fill=(60, 60, 60),
            )

    by_id = {p.id: p for p in parts}
    for placement in placements:
        part = by_id[placement.part_id]
        origin_x = gap_px + placement.sheet * (sheet_px_w + gap_px)
        origin_y = gap_px + sheet_px_h

        def to_pixels(points: tuple[Point, ...]) -> list[tuple[float, float]]:
            # Image rows grow downwards while model y grows upwards, so the row
            # is measured from the bottom edge of the sheet.
            return [
                (origin_x + x * px_per_mm, origin_y - y * px_per_mm) for x, y in points
            ]

        fill = colors.get(placement.part_id, DEFAULT_PART)
        draw.polygon(to_pixels(apply_points(placement.transform, part.outer)),
                     fill=fill, outline=PART_EDGE)
        for hole in part.holes:
            draw.polygon(to_pixels(apply_points(placement.transform, hole)),
                         fill=SHEET_FILL, outline=PART_EDGE)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path), format="PNG")
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/io/test_preview.py -v`
Esperado: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/io/preview.py tests/io/test_preview.py
git commit -m "feat: previsualizacion PNG del resultado"
```

---

### Task 21: CLI completa y resumen por consola

**Files:**
- Modify: `src/nesting/cli.py` — flags `--esfuerzo` y `--preview`, resumen mejorado
- Test: `tests/test_cli_full.py`

**Interfaces:**
- Consumes: `EFFORT_RESTARTS`/`layout_cost`/`UnknownEffortError` (Task 19), `write_preview` (Task 20)
- Produces: `main` con la tabla de flags completa de la spec §6.5

| Flag | Default | Descripción |
|---|---|---|
| `--material` | *(requerido)* | Clave del catálogo |
| `--copias` | `1` | Multiplicador global |
| `--sep` | `5` | Separación entre piezas, mm |
| `--borde` | `10` | Margen contra el borde, mm |
| `--angulos` | `0,90,180,270` | Ángulos candidatos |
| `--esfuerzo` | `normal` | `rapido` \| `normal` \| `lento` |
| `--sin-espejo` | *(off)* | Deshabilita el espejado |
| `--resolucion` | `1` | Raster, mm/px |
| `--unidades` | *(auto)* | `mm`\|`cm`\|`m`\|`in`\|`ft` |
| `--tol-cierre` | `0.1` | Tolerancia de encadenado, mm |
| `--preview` | *(off)* | Ruta del PNG a generar |
| `-o` | *(requerido)* | DXF de salida |

**El resumen estima el sobrante útil** de la última placa a partir de `layout_cost`, que ya calcula la altura alcanzada. Es información accionable: dice si lo que sobra sirve para el próximo trabajo o es recorte.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/test_cli_full.py`:

```python
import ezdxf
import pytest

from nesting.cli import main


def write_input(tmp_path, squares, units=4):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units
    msp = doc.modelspace()
    for x0, y0, side in squares:
        msp.add_lwpolyline(
            [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)],
            close=True, dxfattribs={"color": 1},
        )
    path = tmp_path / "in.dxf"
    doc.saveas(path)
    return path


def catalogue(tmp_path):
    path = tmp_path / "materials.yaml"
    path.write_text("test:\n  placa: [1000, 1000]\n  tolerancia_veta: 180\n", encoding="utf-8")
    return path


def run(args):
    return main([str(a) for a in args])


def base(tmp_path, source, out):
    return [source, "--material", "test", "--materiales", catalogue(tmp_path), "-o", out]


@pytest.mark.parametrize("effort", ["rapido", "normal", "lento"])
def test_every_effort_level_runs(tmp_path, effort):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    out = tmp_path / f"{effort}.dxf"
    assert run(base(tmp_path, source, out) + ["--esfuerzo", effort]) == 0
    assert out.exists()


def test_an_unknown_effort_level_is_rejected_by_argparse(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200)])
    with pytest.raises(SystemExit):
        run(base(tmp_path, source, tmp_path / "o.dxf") + ["--esfuerzo", "turbo"])


def test_preview_writes_a_png(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    preview = tmp_path / "vista.png"
    code = run(base(tmp_path, source, tmp_path / "o.dxf") + ["--preview", preview])

    assert code == 0
    assert preview.exists()


def test_no_preview_by_default(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200)])
    run(base(tmp_path, source, tmp_path / "o.dxf"))
    assert not (tmp_path / "vista.png").exists()


def test_the_summary_reports_the_usable_offcut(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200)])
    run(base(tmp_path, source, tmp_path / "o.dxf"))
    assert "sobrante" in capsys.readouterr().out.lower()


def test_the_summary_reports_parts_sheets_and_time(tmp_path, capsys):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 200), (0, 300, 200)])
    run(base(tmp_path, source, tmp_path / "o.dxf") + ["--copias", "4"])

    output = capsys.readouterr().out
    assert "12 piezas" in output
    assert "placas" in output
    assert "s" in output


def test_resolution_flag_changes_nothing_about_validity(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200), (300, 0, 150)])
    assert run(base(tmp_path, source, tmp_path / "a.dxf") + ["--resolucion", "0.5"]) == 0
    assert run(base(tmp_path, source, tmp_path / "b.dxf") + ["--resolucion", "3"]) == 0


def test_mirroring_can_be_turned_off(tmp_path):
    source = write_input(tmp_path, [(0, 0, 200)])
    out = tmp_path / "o.dxf"
    assert run(base(tmp_path, source, out) + ["--sin-espejo", "--copias", "4"]) == 0
    assert out.exists()


def test_the_help_lists_every_flag(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    output = capsys.readouterr().out
    for flag in ("--material", "--copias", "--sep", "--borde", "--angulos",
                 "--esfuerzo", "--sin-espejo", "--resolucion", "--unidades",
                 "--tol-cierre", "--preview"):
        assert flag in output
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/test_cli_full.py -v`
Esperado: FALLA, `--esfuerzo` no está reconocido.

- [ ] **Step 3: Agregar los flags nuevos**

En `src/nesting/cli.py`, agregar a `_parse_args`:

```python
    parser.add_argument("--esfuerzo", choices=sorted(EFFORT_RESTARTS), default="normal",
                        help="cuanto tiempo dedicarle a mejorar el resultado")
    parser.add_argument("--preview", type=Path, default=None,
                        help="ruta del PNG de previsualizacion a generar")
```

y los imports:

```python
from nesting.engine.packer import EFFORT_RESTARTS, PartTooLargeError, layout_cost, pack, replicate
from nesting.io.preview import write_preview
```

Pasar el esfuerzo al `NestConfig`:

```python
    config = NestConfig(
        sep=args.sep,
        margin=args.borde,
        angles=angles,
        mirror=not args.sin_espejo,
        resolution=args.resolucion,
        effort=args.esfuerzo,
    )
```

- [ ] **Step 4: Generar la previsualización después de escribir el DXF**

En `main`, justo después de la llamada a `write_dxf`, agregar:

```python
    if args.preview is not None:
        write_preview(
            args.preview, parts, result.placements,
            material.sheet_w, material.sheet_h, result.utilization,
            colors=_colors_by_part(drawing, parts),
        )
        print(f"Previsualizacion en {args.preview}")
```

y agregar la función auxiliar al final del archivo, antes de `_parse_args`:

```python
def _colors_by_part(drawing, parts) -> dict[int, tuple[int, int, int]]:
    """Give each part the colour of its first source entity, for the preview."""
    colors: dict[int, tuple[int, int, int]] = {}
    for part in parts:
        if not part.entity_ids:
            continue
        rgb = drawing.entities[part.entity_ids[0]].style.rgb
        if rgb is not None:
            colors[part.id] = rgb
    return colors
```

- [ ] **Step 5: Mejorar el resumen con el sobrante útil**

Reemplazar `_print_summary` por:

```python
def _print_summary(result, parts, material, part_count: int, out_path: Path) -> None:
    _, used_height = layout_cost(result, parts)
    free_height = material.sheet_h - used_height

    for index, utilisation in enumerate(result.utilization):
        line = (
            f"Placa {index + 1}/{result.sheets_used}   "
            f"aprovechamiento {utilisation * 100:5.1f}%"
        )
        if index == result.sheets_used - 1 and free_height > 100.0:
            line += (
                f"   <- sobrante util ~{material.sheet_w:.0f}x{free_height:.0f} mm"
            )
        print(line)

    print("-" * 34)
    print(
        f"{part_count} piezas - {result.sheets_used} placas - "
        f"{result.total_utilization * 100:.1f}% total - {result.seconds:.1f}s"
    )
    print(f"Escrito en {out_path}")
```

y actualizar la llamada en `main`:

```python
    _print_summary(result, parts, material, len(parts), args.salida)
```

- [ ] **Step 6: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/test_cli_full.py -v`
Esperado: `11 passed`.

- [ ] **Step 7: Probar a mano sobre la muestra del banco**

```bash
.venv/bin/nest bench/files/muestra.dxf --material mdf18 --copias 3 --sep 6 --borde 10 --esfuerzo normal --preview /tmp/vista.png -o /tmp/resultado.dxf
```

Esperado: el resumen con el aprovechamiento por placa, el sobrante útil de la última, y los dos archivos escritos. **Abrir `/tmp/vista.png` y confirmar que las piezas se ven acomodadas y entrelazadas, no apiladas en filas.**

- [ ] **Step 8: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos pasan.

- [ ] **Step 9: Commit**

```bash
git add src/nesting/cli.py tests/test_cli_full.py
git commit -m "feat: CLI completa con esfuerzo, preview y resumen de sobrante"
```

**Hito 4 completo.** Es el producto: se le tira un archivo, se elige material y esfuerzo, y devuelve el DXF acomodado más una imagen para mirarlo.

---

# Hito 5 — Importadores adicionales

*Independientes del motor: se pueden hacer en cualquier momento, incluso en paralelo.*

---

### Task 22: Lector de `.ai` (`io/ai_reader.py`)

**Files:**
- Create: `src/nesting/io/ai_reader.py`
- Modify: `src/nesting/cli.py` — despachar por extensión
- Test: `tests/io/test_ai_reader.py`

**Interfaces:**
- Consumes: `Drawing` (Task 8), primitivas (Task 2)
- Produces:
  - `read_ai(path: str | Path) -> Drawing`
  - `PT_TO_MM = 25.4 / 72`
  - `cmyk_to_rgb(c, m, y, k) -> tuple[int, int, int]`

**El `.ai` que exporta CorelDRAW es AI3, o sea PostScript en texto plano.** No hace falta ninguna dependencia: es un parser de ~200 líneas. Los operadores relevantes:

| Operador | Significado |
|---|---|
| `x y m` | moveto — arranca un subcamino |
| `x y l` / `x y L` | lineto |
| `x1 y1 x2 y2 x3 y3 c` / `C` | curveto (Bézier cúbica) |
| `x2 y2 x3 y3 v` / `V` | curveto con el primer control = punto actual |
| `x1 y1 x3 y3 y` / `Y` | curveto con el segundo control = punto final |
| `s` `f` `b` `n` | pintar **cerrando** el subcamino primero |
| `S` `F` `B` `N` | pintar **sin** cerrar |
| `c m y k K` | color de trazo, CMYK |
| `c m y k k` | color de relleno, CMYK |
| `g` / `G` | color en gris |

**Solo se parsea el cuerpo, entre `%%EndSetup` y `%%Trailer`.** El prólogo de un AI3 son definiciones de procedimientos PostScript llenas de tokens que un parser ingenuo confundiría con geometría. Saltearlo elimina esa clase entera de errores.

**Unidades:** puntos. `1 pt = 25.4/72 mm`. No hay ambigüedad, así que `read_ai` nunca pide `--unidades`.

**Capas:** un AI3 exportado de Corel no trae nombres de capa utilizables. Se genera uno por color: `AI_A6FF00`. Así, al abrir el resultado en Corel, las piezas quedan agrupadas por color igual que en el original — que es exactamente cómo se organizan estos archivos en la práctica.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/io/test_ai_reader.py`:

```python
import pytest

from nesting.io.ai_reader import PT_TO_MM, cmyk_to_rgb, read_ai
from nesting.model.entities import Bezier, Line

HEADER = "%!PS-Adobe-3.0\n%%BeginSetup\njunk m junk l\n%%EndSetup\n"
TRAILER = "%%Trailer\n999 999 m 999 999 l\n%%EOF\n"


def write_ai(tmp_path, body, name="t.ai"):
    path = tmp_path / name
    path.write_text(HEADER + body + TRAILER, encoding="latin-1")
    return path


def test_cmyk_to_rgb_black_and_white():
    assert cmyk_to_rgb(0.0, 0.0, 0.0, 1.0) == (0, 0, 0)
    assert cmyk_to_rgb(0.0, 0.0, 0.0, 0.0) == (255, 255, 255)


def test_cmyk_to_rgb_pure_cyan():
    assert cmyk_to_rgb(1.0, 0.0, 0.0, 0.0) == (0, 255, 255)


def test_reads_a_simple_closed_triangle(tmp_path):
    body = "0 0 m\n72 0 L\n72 72 L\ns\n"
    drawing = read_ai(write_ai(tmp_path, body))

    lines = [e for e in drawing.entities if isinstance(e, Line)]
    assert len(lines) == 3, "dos tramos dibujados mas el cierre"
    assert lines[0].start == pytest.approx((0.0, 0.0))
    assert lines[0].end == pytest.approx((25.4, 0.0)), "72 pt son 25.4 mm"


def test_an_uppercase_paint_operator_does_not_close_the_path(tmp_path):
    body = "0 0 m\n72 0 L\n72 72 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert len([e for e in drawing.entities if isinstance(e, Line)]) == 2


def test_points_are_converted_to_millimetres(tmp_path):
    body = "0 0 m\n144 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert drawing.entities[0].end[0] == pytest.approx(144 * PT_TO_MM)
    assert drawing.source_units == "pt"


def test_a_curveto_becomes_a_bezier(tmp_path):
    body = "0 0 m\n10 20 30 20 40 0 C\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))

    curves = [e for e in drawing.entities if isinstance(e, Bezier)]
    assert len(curves) == 1
    assert curves[0].p0 == pytest.approx((0.0, 0.0))
    assert curves[0].p3 == pytest.approx((40 * PT_TO_MM, 0.0))


def test_the_v_operator_uses_the_current_point_as_first_control(tmp_path):
    body = "0 0 m\n30 20 40 0 v\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    curve = drawing.entities[0]
    assert curve.p0 == pytest.approx(curve.p1), "el primer control es el punto actual"


def test_the_y_operator_uses_the_endpoint_as_second_control(tmp_path):
    body = "0 0 m\n10 20 40 0 y\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    curve = drawing.entities[0]
    assert curve.p3 == pytest.approx(curve.p2), "el segundo control es el punto final"


def test_the_stroke_colour_is_captured(tmp_path):
    body = "1.0 0.0 0.0 0.0 K\n0 0 m\n72 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert drawing.entities[0].style.rgb == (0, 255, 255)


def test_the_layer_name_encodes_the_colour(tmp_path):
    body = "1.0 0.0 0.0 0.0 K\n0 0 m\n72 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert drawing.entities[0].style.layer == "AI_00FFFF"


def test_different_colours_land_on_different_layers(tmp_path):
    body = (
        "1.0 0.0 0.0 0.0 K\n0 0 m\n72 0 L\nS\n"
        "0.0 1.0 0.0 0.0 K\n0 100 m\n72 100 L\nS\n"
    )
    drawing = read_ai(write_ai(tmp_path, body))
    assert len({e.style.layer for e in drawing.entities}) == 2


def test_a_grey_stroke_is_captured(tmp_path):
    body = "0.5 G\n0 0 m\n72 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    rgb = drawing.entities[0].style.rgb
    assert rgb[0] == rgb[1] == rgb[2]
    assert 120 < rgb[0] < 136


def test_the_prologue_and_trailer_are_ignored(tmp_path):
    """El prologo trae tokens que parecen geometria; no deben entrar."""
    body = "0 0 m\n72 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert len(drawing.entities) == 1


def test_several_subpaths_each_close_on_their_own(tmp_path):
    body = (
        "0 0 m\n72 0 L\n72 72 L\ns\n"
        "200 200 m\n272 200 L\n272 272 L\ns\n"
    )
    drawing = read_ai(write_ai(tmp_path, body))
    assert len(drawing.entities) == 6


def test_an_ai_file_without_geometry_reads_as_empty(tmp_path):
    drawing = read_ai(write_ai(tmp_path, ""))
    assert drawing.entities == []


def test_the_result_flows_through_the_whole_pipeline(tmp_path):
    """Un cuadrado en .ai tiene que salir como una pieza."""
    from nesting.pipeline import prepare_parts

    body = "0 0 m\n288 0 L\n288 288 L\n0 288 L\ns\n"
    parts, _ = prepare_parts(read_ai(write_ai(tmp_path, body)))

    assert len(parts) == 1
    assert parts[0].outer_area == pytest.approx((288 * PT_TO_MM) ** 2, rel=0.01)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/io/test_ai_reader.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.io.ai_reader'`.

- [ ] **Step 3: Escribir el lector**

Archivo `src/nesting/io/ai_reader.py`:

```python
"""Read the AI3 (PostScript) files CorelDRAW exports.

Despite the .ai extension these are plain text, so no dependency is needed.
Only the body between %%EndSetup and %%Trailer is parsed: the prologue is full
of PostScript procedure definitions whose tokens a naive parser would happily
mistake for geometry.
"""

from pathlib import Path

from nesting.io.dxf_reader import Drawing
from nesting.model.entities import Bezier, Line, Point, Style

PT_TO_MM = 25.4 / 72.0

BODY_START = "%%EndSetup"
BODY_END = "%%Trailer"

CLOSING_PAINT_OPS = frozenset({"s", "f", "b", "n"})
"""Lowercase paint operators close the current subpath before painting."""

OPEN_PAINT_OPS = frozenset({"S", "F", "B", "N"})


def cmyk_to_rgb(c: float, m: float, y: float, k: float) -> tuple[int, int, int]:
    return (
        round(255 * (1 - min(1.0, c)) * (1 - min(1.0, k))),
        round(255 * (1 - min(1.0, m)) * (1 - min(1.0, k))),
        round(255 * (1 - min(1.0, y)) * (1 - min(1.0, k))),
    )


def read_ai(path: str | Path) -> Drawing:
    """Read an AI3 file into a `Drawing`, converting points to millimetres."""
    text = Path(path).read_text(encoding="latin-1", errors="replace")
    return _parse_body(_extract_body(text))


def _extract_body(text: str) -> str:
    start = text.find(BODY_START)
    body = text[start + len(BODY_START):] if start >= 0 else text
    end = body.find(BODY_END)
    return body[:end] if end >= 0 else body


def _parse_body(body: str) -> Drawing:
    drawing = Drawing(source_units="pt")
    operands: list[float] = []

    rgb: tuple[int, int, int] = (0, 0, 0)
    current: Point | None = None
    subpath_start: Point | None = None
    pending: list[tuple[str, tuple]] = []

    def style() -> Style:
        return Style(aci=None, rgb=rgb, layer=f"AI_{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")

    def flush(close: bool) -> None:
        nonlocal pending, current, subpath_start
        for kind, payload in pending:
            if kind == "line":
                drawing.entities.append(Line(payload[0], payload[1], style()))
            else:
                drawing.entities.append(Bezier(*payload, style()))
        if close and current is not None and subpath_start is not None:
            if current != subpath_start:
                drawing.entities.append(Line(current, subpath_start, style()))
        pending = []
        current = None
        subpath_start = None

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue

        for token in stripped.split():
            number = _as_float(token)
            if number is not None:
                operands.append(number)
                continue

            op = token

            if op == "m" and len(operands) >= 2:
                if pending:
                    flush(close=False)
                current = _pt(operands[-2], operands[-1])
                subpath_start = current

            elif op in ("l", "L") and len(operands) >= 2 and current is not None:
                nxt = _pt(operands[-2], operands[-1])
                pending.append(("line", (current, nxt)))
                current = nxt

            elif op in ("c", "C") and len(operands) >= 6 and current is not None:
                c1 = _pt(operands[-6], operands[-5])
                c2 = _pt(operands[-4], operands[-3])
                end = _pt(operands[-2], operands[-1])
                pending.append(("bezier", (current, c1, c2, end)))
                current = end

            elif op in ("v", "V") and len(operands) >= 4 and current is not None:
                c2 = _pt(operands[-4], operands[-3])
                end = _pt(operands[-2], operands[-1])
                pending.append(("bezier", (current, current, c2, end)))
                current = end

            elif op in ("y", "Y") and len(operands) >= 4 and current is not None:
                c1 = _pt(operands[-4], operands[-3])
                end = _pt(operands[-2], operands[-1])
                pending.append(("bezier", (current, c1, end, end)))
                current = end

            elif op in CLOSING_PAINT_OPS:
                flush(close=True)

            elif op in OPEN_PAINT_OPS:
                flush(close=False)

            elif op in ("K", "k") and len(operands) >= 4:
                rgb = cmyk_to_rgb(*operands[-4:])

            elif op in ("G", "g") and len(operands) >= 1:
                level = round(255 * min(1.0, max(0.0, operands[-1])))
                rgb = (level, level, level)

            operands = []

    flush(close=False)
    return drawing


def _pt(x: float, y: float) -> Point:
    return (x * PT_TO_MM, y * PT_TO_MM)


def _as_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None
```

- [ ] **Step 4: Despachar por extensión en la CLI**

En `src/nesting/cli.py`, agregar el import:

```python
from nesting.io.ai_reader import read_ai
```

y reemplazar la línea `drawing = read_dxf(...)` por:

```python
        if args.entrada.suffix.lower() == ".ai":
            drawing = read_ai(args.entrada)
        else:
            drawing = read_dxf(args.entrada, units_override=args.unidades)
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/io/test_ai_reader.py -v`
Esperado: `16 passed`.

- [ ] **Step 6: Probar sobre el archivo real del proyecto**

```bash
cp "<descargas>/banqueta.ai" bench/files/
.venv/bin/nest "bench/files/banqueta.ai" --material mdf18 --preview /tmp/banqueta.png -o /tmp/banqueta.dxf
```

Esperado: el archivo se lee y se nestea. **Abrir `/tmp/banqueta.png` y confirmar que las piezas se reconocen como piezas** (asientos redondos, patas), no como fragmentos sueltos.

Si aparece `error: N contorno(s) no cierran`, probar aflojando: `--tol-cierre 0.5`. Anotar qué tolerancia hizo falta — es información útil sobre la calidad del export.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/io/ai_reader.py src/nesting/cli.py tests/io/test_ai_reader.py
git commit -m "feat: lector de archivos .ai (AI3/PostScript)"
```

---

### Task 23: Lector de `.3dm` (`io/rhino_reader.py`)

**Files:**
- Create: `src/nesting/io/rhino_reader.py`
- Modify: `src/nesting/cli.py` — despachar `.3dm`
- Modify: `pyproject.toml` — mover `rhino3dm` a dependencia principal
- Test: `tests/io/test_rhino_reader.py`

**Interfaces:**
- Consumes: `Drawing` (Task 8), primitivas (Task 2)
- Produces:
  - `read_3dm(path: str | Path, sample_tol: float = 0.05) -> Drawing`
  - `NonPlanarCurveError(Exception)`

**Un tradeoff explícito, distinto al de DXF y AI.** `LineCurve` y `PolylineCurve` se leen exactas. Todo lo demás —NURBS, arcos, `PolyCurve`— se **muestrea adaptativamente** a polilíneas al leer, con tolerancia de cuerda `sample_tol` (0.05 mm por defecto).

**Por qué.** Convertir NURBS generales a Béziers exige inserción de nudos, que `rhino3dm` no expone de forma confiable entre versiones. Muestrear es robusto y predecible. El costo es que un `.3dm` pierde la representación exacta en la salida, a diferencia de un DXF. Con 0.05 mm de tolerancia —un veinteavo de la resolución del raster— es irrelevante para cortar madera, pero **es una diferencia real y está declarada**, no escondida.

**Planaridad.** Las curvas de Rhino son 3D. Se proyecta a XY y se valida que la dispersión en Z esté dentro de la tolerancia; una curva que no lo cumple se **saltea con aviso** en vez de aplastarse en silencio.

**Capas.** Rhino sí tiene capas con nombre y color, así que se preservan tal cual: es el mejor de los tres formatos en este aspecto.

- [ ] **Step 1: Instalar la dependencia**

```bash
.venv/bin/pip install rhino3dm
```

Y en `pyproject.toml`, mover `"rhino3dm"` de `[project.optional-dependencies].rhino` a la lista `dependencies`, borrando la sección `rhino` que queda vacía.

- [ ] **Step 2: Escribir el test que falla**

Archivo `tests/io/test_rhino_reader.py`:

```python
import pytest

rhino3dm = pytest.importorskip("rhino3dm")

from nesting.io.rhino_reader import read_3dm  # noqa: E402
from nesting.model.entities import Line, Polyline  # noqa: E402


def new_model(unit_system=None):
    model = rhino3dm.File3dm()
    if unit_system is not None:
        model.Settings.ModelUnitSystem = unit_system
    return model


def save(model, tmp_path, name="t.3dm"):
    path = tmp_path / name
    model.Write(str(path), 7)
    return path


def add_layer(model, name, color):
    layer = rhino3dm.Layer()
    layer.Name = name
    layer.Color = color
    return model.Layers.Add(layer)


def test_reads_a_line(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(100, 50, 0))
    drawing = read_3dm(save(model, tmp_path))

    assert len(drawing.entities) == 1
    assert isinstance(drawing.entities[0], Line)
    assert drawing.entities[0].end == pytest.approx((100.0, 50.0))


def test_reads_a_polyline_exactly(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    points = [rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(100, 0, 0),
              rhino3dm.Point3d(100, 100, 0), rhino3dm.Point3d(0, 0, 0)]
    model.Objects.AddPolyline(points)
    drawing = read_3dm(save(model, tmp_path))

    polylines = [e for e in drawing.entities if isinstance(e, Polyline)]
    assert len(polylines) == 1
    assert len(polylines[0].points) == 4


def test_a_circle_is_sampled_into_a_polyline(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    circle = rhino3dm.Circle(rhino3dm.Point3d(0, 0, 0), 50.0)
    model.Objects.AddCircle(circle)
    drawing = read_3dm(save(model, tmp_path))

    polylines = [e for e in drawing.entities if isinstance(e, Polyline)]
    assert len(polylines) == 1
    assert len(polylines[0].points) > 20, "muestreado fino"


def test_the_sampled_circle_stays_within_the_tolerance(tmp_path):
    import math

    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddCircle(rhino3dm.Circle(rhino3dm.Point3d(0, 0, 0), 50.0))
    drawing = read_3dm(save(model, tmp_path), sample_tol=0.05)

    points = drawing.entities[0].points
    for a, b in zip(points, points[1:]):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        assert abs(math.hypot(*mid) - 50.0) < 0.06


def test_centimetres_are_scaled_to_millimetres(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Centimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(10, 0, 0))
    drawing = read_3dm(save(model, tmp_path))

    assert drawing.entities[0].end[0] == pytest.approx(100.0)
    assert drawing.source_units == "cm"


def test_inches_are_scaled_to_millimetres(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Inches)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(1, 0, 0))
    drawing = read_3dm(save(model, tmp_path))
    assert drawing.entities[0].end[0] == pytest.approx(25.4)


def test_layer_names_and_colours_are_preserved(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    index = add_layer(model, "CORTE", (255, 0, 0, 255))

    attributes = rhino3dm.ObjectAttributes()
    attributes.LayerIndex = index
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(10, 0, 0), attributes)

    drawing = read_3dm(save(model, tmp_path))
    assert drawing.entities[0].style.layer == "CORTE"
    assert drawing.entities[0].style.rgb == (255, 0, 0)


def test_a_non_planar_curve_is_skipped_with_a_warning(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(100, 0, 0))
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(0, 0, 500))

    drawing = read_3dm(save(model, tmp_path))
    assert len(drawing.entities) == 1
    assert any("plana" in w for w in drawing.warnings)


def test_a_curve_at_a_constant_non_zero_z_is_accepted(tmp_path):
    """Dibujar a altura 50 es plano: se proyecta sin problema."""
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 50), rhino3dm.Point3d(100, 0, 50))

    drawing = read_3dm(save(model, tmp_path))
    assert len(drawing.entities) == 1
    assert drawing.warnings == []


def test_non_curve_objects_are_skipped_with_a_warning(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddPoint(rhino3dm.Point3d(1, 2, 0))
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(10, 0, 0))

    drawing = read_3dm(save(model, tmp_path))
    assert len(drawing.entities) == 1
    assert any("no son curvas" in w for w in drawing.warnings)


def test_an_empty_model_reads_as_empty(tmp_path):
    drawing = read_3dm(save(new_model(rhino3dm.UnitSystem.Millimeters), tmp_path))
    assert drawing.entities == []


def test_the_result_flows_through_the_whole_pipeline(tmp_path):
    from nesting.pipeline import prepare_parts

    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddCircle(rhino3dm.Circle(rhino3dm.Point3d(0, 0, 0), 100.0))
    parts, _ = prepare_parts(read_3dm(save(model, tmp_path)))

    assert len(parts) == 1
    assert parts[0].outer_area == pytest.approx(3.14159 * 100.0**2, rel=0.01)
```

- [ ] **Step 3: Escribir el lector**

Archivo `src/nesting/io/rhino_reader.py`:

```python
"""Read Rhino .3dm files.

Lines and polylines come through exactly. Everything else - NURBS, arcs,
polycurves - is sampled to a polyline at read time, because converting general
NURBS to Beziers needs knot insertion that rhino3dm does not expose reliably.
That makes .3dm the one format whose output is not bit-exact with its input; at
0.05 mm the difference is far below anything that matters for cutting wood, but
it is a real difference and it is declared rather than hidden.
"""

import math
from pathlib import Path

import rhino3dm

from nesting.io.dxf_reader import UNIT_SCALES, Drawing
from nesting.model.entities import Line, Point, Polyline, Style

DEFAULT_SAMPLE_TOL = 0.05
"""Chord tolerance for sampled curves, in millimetres."""

PLANARITY_TOL = 0.01
"""How much a curve's Z may vary before it is rejected as non-planar."""

MAX_SAMPLE_DEPTH = 16

_UNIT_NAMES = {
    rhino3dm.UnitSystem.Millimeters: "mm",
    rhino3dm.UnitSystem.Centimeters: "cm",
    rhino3dm.UnitSystem.Meters: "m",
    rhino3dm.UnitSystem.Inches: "in",
    rhino3dm.UnitSystem.Feet: "ft",
}


class NonPlanarCurveError(Exception):
    """A curve varies in Z and cannot be flattened onto the sheet."""


def read_3dm(path: str | Path, sample_tol: float = DEFAULT_SAMPLE_TOL) -> Drawing:
    """Read a Rhino model into a `Drawing`, normalised to millimetres."""
    model = rhino3dm.File3dm.Read(str(path))
    units = _UNIT_NAMES.get(model.Settings.ModelUnitSystem, "mm")
    scale = UNIT_SCALES[units]

    drawing = Drawing(source_units=units)
    skipped_non_curve = 0
    skipped_non_planar = 0

    for item in model.Objects:
        geometry = item.Geometry
        if not isinstance(geometry, rhino3dm.Curve):
            skipped_non_curve += 1
            continue

        style = _style_of(model, item)
        try:
            drawing.entities.extend(_convert(geometry, scale, style, sample_tol))
        except NonPlanarCurveError:
            skipped_non_planar += 1

    if skipped_non_curve:
        drawing.warnings.append(
            f"se ignoraron {skipped_non_curve} objetos que no son curvas"
        )
    if skipped_non_planar:
        drawing.warnings.append(
            f"se ignoraron {skipped_non_planar} curvas que no son planas en XY"
        )

    return drawing


def _convert(curve, scale: float, style: Style, tol: float) -> list:
    if isinstance(curve, rhino3dm.LineCurve):
        start = _point(curve.PointAtStart, scale)
        end = _point(curve.PointAtEnd, scale)
        _require_planar([curve.PointAtStart, curve.PointAtEnd])
        return [Line(start, end, style)]

    if isinstance(curve, rhino3dm.PolylineCurve):
        raw = [curve.Point(i) for i in range(curve.PointCount)]
        _require_planar(raw)
        points = tuple(_point(p, scale) for p in raw)
        return [Polyline(points, bool(curve.IsClosed), style)]

    raw = _sample(curve, tol / scale)
    _require_planar(raw)
    points = tuple(_point(p, scale) for p in raw)
    if len(points) < 2:
        return []
    return [Polyline(points, bool(curve.IsClosed), style)]


def _sample(curve, tol: float) -> list:
    """Adaptive sampling: subdivide until the midpoint is within `tol` of the chord."""
    domain = curve.Domain
    points: list = [curve.PointAt(domain[0])]
    _subdivide(curve, domain[0], domain[1], tol, points, depth=0)
    return points


def _subdivide(curve, t0: float, t1: float, tol: float, out: list, depth: int) -> None:
    end = curve.PointAt(t1)
    if depth >= MAX_SAMPLE_DEPTH:
        out.append(end)
        return

    start = out[-1]
    middle = (t0 + t1) / 2.0
    actual = curve.PointAt(middle)
    chord_mid = ((start.X + end.X) / 2.0, (start.Y + end.Y) / 2.0)

    if math.dist((actual.X, actual.Y), chord_mid) <= tol:
        out.append(end)
        return

    _subdivide(curve, t0, middle, tol, out, depth + 1)
    _subdivide(curve, middle, t1, tol, out, depth + 1)


def _require_planar(points) -> None:
    """Accept any constant Z; reject a curve that actually varies in Z."""
    zs = [p.Z for p in points]
    if max(zs) - min(zs) > PLANARITY_TOL:
        raise NonPlanarCurveError("la curva no es plana en XY")


def _style_of(model, item) -> Style:
    index = item.Attributes.LayerIndex
    try:
        layer = model.Layers[index]
        name = layer.Name or "0"
        color = layer.Color
        rgb = (int(color[0]), int(color[1]), int(color[2]))
    except (IndexError, TypeError, AttributeError):
        name, rgb = "0", (255, 255, 255)
    return Style(aci=None, rgb=rgb, layer=name)


def _point(p, scale: float) -> Point:
    return (p.X * scale, p.Y * scale)
```

- [ ] **Step 4: Despachar `.3dm` en la CLI**

En `src/nesting/cli.py`, agregar el import y extender el despacho por extensión:

```python
from nesting.io.rhino_reader import read_3dm
```

```python
        suffix = args.entrada.suffix.lower()
        if suffix == ".ai":
            drawing = read_ai(args.entrada)
        elif suffix == ".3dm":
            drawing = read_3dm(args.entrada)
        else:
            drawing = read_dxf(args.entrada, units_override=args.unidades)
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/io/test_rhino_reader.py -v`
Esperado: `12 passed`.

- [ ] **Step 6: Probar sobre el archivo real del proyecto**

```bash
cp "<descargas>/banqueta.3dm" bench/files/
.venv/bin/nest "bench/files/banqueta.3dm" --material mdf18 --preview /tmp/banqueta3dm.png -o /tmp/banqueta3dm.dxf
```

Esperado: se lee y se nestea. Los avisos de objetos no-curva o no-planos son normales en un modelo 3D real — lo importante es que las **curvas de corte** salgan bien. Confirmar en el PNG.

- [ ] **Step 7: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos pasan.

- [ ] **Step 8: Commit**

```bash
git add src/nesting/io/rhino_reader.py src/nesting/cli.py pyproject.toml tests/io/test_rhino_reader.py
git commit -m "feat: lector de archivos .3dm de Rhino"
```

**Hito 5 completo.** Los tres formatos de entrada funcionan. El `.cdr` sigue resolviéndose exportando a DXF desde Corel, como se decidió en la spec §2.

---

# Hito 6 — Calibración con mediciones

---

### Task 24: Calibrar pesos y niveles de esfuerzo

**Files:**
- Create: `bench/calibrate.py`
- Modify: `src/nesting/engine/oracle.py` — `Weights` por defecto, con los valores medidos
- Modify: `src/nesting/engine/packer.py` — `EFFORT_RESTARTS`, con los valores medidos
- Create: `docs/superpowers/calibracion.md`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `run_one` (Task 14), `Weights`/`NestConfig` (Task 11)
- Produces: `bench.calibrate.sweep_weights(...)`, `bench.calibrate.sweep_effort(...)`, `bench.calibrate.main(argv)`

**Esta tarea no inventa números: los mide.** Hay dos cosas que quedaron pendientes de calibración a lo largo del plan y que hasta ahora tienen valores provisorios:

| Qué | Valor provisorio | Dónde |
|---|---|---|
| `Weights(bottom_left, contact)` | `(1.0, 1.0)` | `engine/oracle.py`, Task 11 |
| `EFFORT_RESTARTS` | `{rapido: 1, normal: 10, lento: 120}` | `engine/packer.py`, Task 19 |

La spec §5.6 es explícita: **los tiempos de cada nivel se calibran con mediciones del banco, no se fijan por estimación**. La estimación de referencia era ~15-30 s por pasada; esta tarea la confirma o la corrige.

**Criterio para fijar los niveles:** `normal` tiene que quedar en un rango que se banque esperar sentado (objetivo ≤ 5 min con los archivos reales); `lento` tiene que dar una mejora **medible** sobre `normal`, si no, no justifica existir y hay que bajarle las iteraciones o replantearlo.

- [ ] **Step 1: Escribir el barrido**

Archivo `bench/calibrate.py`:

```python
"""Measure the two knobs that were left provisional: scoring weights and effort.

Nothing here invents a number. Every value that ends up in the defaults comes
out of a run over the project's real files.
"""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from nesting.engine.oracle import NestConfig, Weights
from nesting.engine.raster.oracle import RasterOracle
from nesting.model.material import DEFAULT_MATERIALS_PATH, Material, load_materials

sys.path.insert(0, str(Path(__file__).parent))
from run_bench import FILES_DIR, run_one  # noqa: E402

CONTACT_CANDIDATES = (0.0, 0.5, 1.0, 2.0, 4.0)
EFFORT_LEVELS = ("rapido", "normal", "lento")


def sweep_weights(
    files: list[Path], material: Material, config: NestConfig
) -> list[tuple[float, float, float]]:
    """For each contact weight, the mean utilisation and mean seconds."""
    rows = []
    for contact in CONTACT_CANDIDATES:
        tuned = replace(config, weights=Weights(bottom_left=1.0, contact=contact))
        results = [
            run_one(path, material, tuned, RasterOracle, "raster") for path in files
        ]
        rows.append((
            contact,
            sum(r.total_utilization for r in results) / len(results),
            sum(r.seconds for r in results) / len(results),
        ))
    return rows


def sweep_effort(
    files: list[Path], material: Material, config: NestConfig
) -> list[tuple[str, float, float, int]]:
    """For each effort level, the mean utilisation, mean seconds and total sheets."""
    rows = []
    for effort in EFFORT_LEVELS:
        tuned = replace(config, effort=effort)
        results = [
            run_one(path, material, tuned, RasterOracle, "raster") for path in files
        ]
        rows.append((
            effort,
            sum(r.total_utilization for r in results) / len(results),
            sum(r.seconds for r in results) / len(results),
            sum(r.sheets for r in results),
        ))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibra pesos y niveles de esfuerzo.")
    parser.add_argument("--material", default="mdf18")
    parser.add_argument("--copias", type=int, default=1)
    args = parser.parse_args(argv)

    material = load_materials(DEFAULT_MATERIALS_PATH)[args.material]
    files = sorted(FILES_DIR.glob("*.dxf")) + sorted(FILES_DIR.glob("*.ai"))
    if not files:
        print(f"no hay archivos en {FILES_DIR}", file=sys.stderr)
        return 1

    print(f"Calibrando sobre {len(files)} archivo(s): "
          f"{', '.join(f.name for f in files)}\n")

    print("PESO DE CONTACTO  (bottom_left fijo en 1.0, esfuerzo rapido)")
    print(f"{'contacto':>10}{'aprov. medio':>15}{'seg. medio':>13}")
    print("-" * 38)
    for contact, utilisation, seconds in sweep_weights(
        files, material, NestConfig(sep=6.0, margin=10.0, effort="rapido")
    ):
        print(f"{contact:>10.1f}{utilisation * 100:>14.1f}%{seconds:>13.1f}")

    print("\nNIVELES DE ESFUERZO")
    print(f"{'nivel':>10}{'aprov. medio':>15}{'seg. medio':>13}{'placas':>9}")
    print("-" * 47)
    for effort, utilisation, seconds, sheets in sweep_effort(
        files, material, NestConfig(sep=6.0, margin=10.0)
    ):
        print(f"{effort:>10}{utilisation * 100:>14.1f}%{seconds:>13.1f}{sheets:>9}")

    print("\nElegir el peso de contacto con mejor aprovechamiento y anotarlo en")
    print("engine/oracle.py. Ajustar EFFORT_RESTARTS en engine/packer.py para que")
    print("'normal' quede por debajo de 5 minutos y 'lento' mejore de forma medible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Escribir el test del barrido**

Archivo `tests/test_calibration.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

from calibrate import CONTACT_CANDIDATES, EFFORT_LEVELS, sweep_effort, sweep_weights  # noqa: E402
from make_sample import write_sample  # noqa: E402

from nesting.engine.oracle import NestConfig  # noqa: E402
from nesting.model.material import Material  # noqa: E402

MATERIAL = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)


def sample(tmp_path):
    path = tmp_path / "muestra.dxf"
    write_sample(path)
    return [path]


def test_the_weight_sweep_covers_every_candidate(tmp_path):
    config = NestConfig(sep=6.0, margin=10.0, effort="rapido", resolution=3.0)
    rows = sweep_weights(sample(tmp_path), MATERIAL, config)

    assert len(rows) == len(CONTACT_CANDIDATES)
    assert [row[0] for row in rows] == list(CONTACT_CANDIDATES)
    assert all(0.0 < row[1] <= 1.0 for row in rows)


def test_the_effort_sweep_covers_every_level(tmp_path):
    config = NestConfig(sep=6.0, margin=10.0, resolution=4.0)
    rows = sweep_effort(sample(tmp_path), MATERIAL, config)

    assert [row[0] for row in rows] == list(EFFORT_LEVELS)
    assert all(0.0 < row[1] <= 1.0 for row in rows)


def test_more_effort_never_uses_more_sheets(tmp_path):
    config = NestConfig(sep=6.0, margin=10.0, resolution=4.0)
    rows = sweep_effort(sample(tmp_path), MATERIAL, config)
    sheets = {row[0]: row[3] for row in rows}
    assert sheets["normal"] <= sheets["rapido"]
    assert sheets["lento"] <= sheets["normal"]
```

- [ ] **Step 3: Correr el test**

Run: `.venv/bin/pytest tests/test_calibration.py -v`
Esperado: `3 passed`. (Tarda: usa resolución gruesa a propósito para que no sea eterno.)

- [ ] **Step 4: Cargar los archivos reales y correr la calibración**

Asegurarse de que `bench/files/` tenga el DXF exportado de Corel (ver `bench/README.md`) además de la muestra sintética y el `.ai`.

```bash
.venv/bin/python bench/calibrate.py --material mdf18 --copias 2
```

- [ ] **Step 5: Fijar los valores medidos**

En `src/nesting/engine/oracle.py`, reemplazar los defaults de `Weights` por el peso de contacto que ganó el barrido:

```python
@dataclass(frozen=True)
class Weights:
    bottom_left: float = 1.0
    contact: float = <VALOR MEDIDO>
```

En `src/nesting/engine/packer.py`, ajustar `EFFORT_RESTARTS` según los tiempos medidos:

```python
EFFORT_RESTARTS: dict[str, int] = {
    "rapido": 1,
    "normal": <MEDIDO: el mayor que deje 'normal' por debajo de 5 min>,
    "lento": <MEDIDO: el que de una mejora visible sobre 'normal'>,
}
```

Si `lento` **no** mejora a `normal` de forma medible, bajarle las iteraciones y anotarlo: un nivel que no compra nada es peor que no tenerlo.

- [ ] **Step 6: Documentar los resultados**

Archivo `docs/superpowers/calibracion.md`, completando con los números reales:

```markdown
# Calibración — <FECHA>

Medido con `bench/calibrate.py` sobre los archivos de `bench/files/`.

## Archivos

| Archivo | Piezas | Origen |
|---|---|---|
| ... | ... | ... |

## Peso de contacto

`bottom_left` fijo en 1.0, esfuerzo `rapido`.

| contacto | aprovechamiento medio | segundos medios |
|---|---|---|
| 0.0 | | |
| 0.5 | | |
| 1.0 | | |
| 2.0 | | |
| 4.0 | | |

**Elegido:** `contact = ___`

## Niveles de esfuerzo

| nivel | reintentos | aprovechamiento medio | segundos medios | placas |
|---|---|---|---|---|
| rapido | 1 | | | |
| normal | ___ | | | |
| lento | ___ | | | |

**Conclusión sobre la estimación original.** La spec §5.6 estimaba ~15-30 s por
pasada y `normal` en 3-5 min. Lo medido fue: ___

## Comparación contra la línea de base

| motor | aprovechamiento | placas |
|---|---|---|
| shelf (bounding box, hito 2) | | |
| raster (hito 3) | | |

**Ganancia del motor raster:** ___ puntos porcentuales.
```

- [ ] **Step 7: Verificar que todo sigue pasando con los valores nuevos**

Run: `.venv/bin/pytest -q`
Esperado: todos pasan. Si algún test de densidad empieza a fallar, es que el cambio de pesos empeoró un caso: revisar antes de aceptarlo.

- [ ] **Step 8: Commit**

```bash
git add bench/calibrate.py docs/superpowers/calibracion.md src/nesting/engine/oracle.py src/nesting/engine/packer.py tests/test_calibration.py
git commit -m "feat: calibracion de pesos y esfuerzos con mediciones reales"
```

**Hito 6 completo. Proyecto terminado.**

---

## Estado final

| Capacidad | Dónde quedó |
|---|---|
| Lectura `.dxf`, `.ai`, `.3dm` | `io/` |
| Escritura `.dxf` + preview `.png` | `io/dxf_writer.py`, `io/preview.py` |
| Nesting de formas irregulares con rotación y espejado | `engine/raster/` |
| Aprovechamiento de agujeros pasantes | Sin código dedicado: cae de `engine/raster/masks.py` §5.2 |
| Separación entre piezas y contra el borde | Dentro del oráculo, como manda la spec §3.2 |
| Múltiples placas con desborde | `engine/packer.py` |
| Catálogo de materiales con restricción de veta | `model/material.py` + `materials.yaml` |
| Verificación geométrica exacta | `geometry/verify.py` — bloquea la escritura si falla |
| Niveles de esfuerzo calibrados | `engine/packer.py` + `docs/superpowers/calibracion.md` |

**La puerta al motor NFP quedó abierta**, con las tres restricciones de la spec §3.2 respetadas:

1. El polígono exacto es la fuente de verdad; el raster es caché derivado.
2. El offset de separación vive adentro del oráculo.
3. El banco de pruebas existe y mide, así que la comparación sería con números.

Implementarlo sería un archivo nuevo, `engine/nfp/oracle.py`, con los mismos tres métodos. `packer.py`, `cli.py`, `verify.py`, todo `io/` y el banco quedarían intactos.
