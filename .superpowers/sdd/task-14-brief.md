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

