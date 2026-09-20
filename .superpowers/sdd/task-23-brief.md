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

