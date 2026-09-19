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

