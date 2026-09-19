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
