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

