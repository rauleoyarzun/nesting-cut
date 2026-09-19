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
cp "/Users/raulo/Downloads/banqueta final raulo.ai" bench/files/
.venv/bin/nest "bench/files/banqueta final raulo.ai" --material mdf18 --preview /tmp/banqueta.png -o /tmp/banqueta.dxf
```

Esperado: el archivo se lee y se nestea. **Abrir `/tmp/banqueta.png` y confirmar que las piezas se reconocen como piezas** (asientos redondos, patas), no como fragmentos sueltos.

Si aparece `error: N contorno(s) no cierran`, probar aflojando: `--tol-cierre 0.5`. Anotar qué tolerancia hizo falta — es información útil sobre la calidad del export.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/io/ai_reader.py src/nesting/cli.py tests/io/test_ai_reader.py
git commit -m "feat: lector de archivos .ai (AI3/PostScript)"
```

---

