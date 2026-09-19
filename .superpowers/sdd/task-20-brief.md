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

