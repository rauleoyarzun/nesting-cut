### Task 9: Escritor de DXF (`io/dxf_writer.py`)

**Files:**
- Create: `src/nesting/io/dxf_writer.py`
- Test: `tests/io/test_dxf_writer.py`

**Interfaces:**
- Consumes: `Drawing` (Task 8), `Part`, `Placement` (Task 6), `apply_entity` (Task 3)
- Produces:
  - `SHEET_LAYER = "_PLACA"`
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

    sheet_count = max((p.sheet for p in placements), default=-1) + 1
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

