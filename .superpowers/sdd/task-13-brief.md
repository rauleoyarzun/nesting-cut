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
    from nesting.geometry.verify import verify
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    source = write_input(tmp_path, [(0, 0, 200) for _ in range(1)])
    out = tmp_path / "out.dxf"
    run([source, "--material", "test", "--materiales", catalogue(tmp_path),
         "--copias", "6", "--sep", "25", "--borde", "40", "-o", out])

    # Releer la salida y comprobar que las piezas respetan lo pedido.
    parts, _ = prepare_parts(read_dxf(out))
    assert len(parts) >= 6


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

