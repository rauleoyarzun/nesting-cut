"""Measure the knobs that were left provisional: scoring weights, raster
resolution and effort.

Nothing here invents a number. Every value that ends up in the defaults comes
out of a run over the project's real files (`bench/files/`).

Metrica usada para comparar configuraciones entre si: `first_sheet_utilization`
(aprovechamiento de la PRIMERA placa), no `total_utilization`. Con el mismo
conjunto de piezas, `total_utilization` es area de piezas sobre area de placas
usadas -- si dos configuraciones necesitan la misma cantidad de placas, esa
metrica da identica por construccion aunque una haya empaquetado la primera
placa mucho mejor que la otra (ver el docstring de `BenchResult` en
`run_bench.py`). Por eso cada barrido tambien reporta la cantidad total de
placas usadas: en igualdad de aprovechamiento de la primera placa, menos
placas es siempre mejor.
"""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from nesting.engine.oracle import NestConfig, Weights
from nesting.engine.raster.oracle import RasterOracle
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.model.material import DEFAULT_MATERIALS_PATH, Material, load_materials

sys.path.insert(0, str(Path(__file__).parent))
from run_bench import FILES_DIR, run_one  # noqa: E402

CONTACT_CANDIDATES = (0.0, 0.5, 1.0, 2.0, 4.0)
RESOLUTION_CANDIDATES = (0.5, 1.0, 2.0, 3.0)
EFFORT_LEVELS = ("rapido", "normal", "lento")

# Extensiones que este barrido sabe leer y que sirven para calibrar. El
# `.3dm` del proyecto (`banqueta.3dm`) es el modelo 3D del ensamblaje
# armado, no un layout de corte plano: da 0 piezas (ver el Task 23 report),
# asi que deliberadamente no entra en este glob -- incluirlo no rompe nada
# (un archivo de 0 piezas mide 0% e infla para abajo el promedio en lugar de
# romper la corrida), pero tampoco aporta nada a la calibracion.
_GLOB_PATTERNS = ("*.dxf", "*.ai")


def _load_files(files_dir: Path) -> list[Path]:
    """Real files to calibrate against, skipping any that yield no parts.

    Filtrar aca -- una sola vez, antes de los barridos -- evita repetir el
    chequeo (y el aviso) en cada una de las decenas de combinaciones que
    corre cada barrido, y mantiene `sweep_weights`/`sweep_effort`/
    `sweep_resolution` simples: reciben una lista de archivos que ya se sabe
    que van a producir piezas.
    """
    from nesting.io.ai_reader import read_ai
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    candidates: list[Path] = []
    for pattern in _GLOB_PATTERNS:
        candidates.extend(sorted(files_dir.glob(pattern)))

    usable = []
    for path in candidates:
        drawing = read_ai(path) if path.suffix.lower() == ".ai" else read_dxf(path)
        parts, _, _ = prepare_parts(drawing)
        if parts:
            usable.append(path)
        else:
            print(f"aviso: {path.name} no tiene piezas, se salta de la calibracion")
    return usable


def sweep_weights(
    files: list[Path], material: Material, config: NestConfig, copies: int = 1
) -> list[tuple[float, float, float, int]]:
    """For each contact weight: mean first-sheet utilisation, mean seconds,
    total sheets across every file."""
    rows = []
    for contact in CONTACT_CANDIDATES:
        tuned = replace(config, weights=Weights(bottom_left=1.0, contact=contact))
        results = [
            run_one(path, material, tuned, RasterOracle, "raster", copies=copies)
            for path in files
        ]
        rows.append((
            contact,
            sum(r.first_sheet_utilization for r in results) / len(results),
            sum(r.seconds for r in results) / len(results),
            sum(r.sheets for r in results),
        ))
    return rows


def sweep_resolution(
    files: list[Path], material: Material, config: NestConfig, copies: int = 1
) -> list[tuple[float, float, float]]:
    """For each raster resolution: mean first-sheet utilisation and mean
    seconds.

    No mide `sheets` porque no es lo que este barrido busca: la resolucion
    afecta la calidad del empaquetado de forma continua (mas piezas
    entrando, o no, en la placa que ya esta abierta), y esa continuidad se ve
    en `first_sheet_utilization`, no en un conteo entero que solo cambia
    cuando se cruza un umbral.
    """
    rows = []
    for resolution in RESOLUTION_CANDIDATES:
        tuned = replace(config, resolution=resolution)
        results = [
            run_one(path, material, tuned, RasterOracle, "raster", copies=copies)
            for path in files
        ]
        rows.append((
            resolution,
            sum(r.first_sheet_utilization for r in results) / len(results),
            sum(r.seconds for r in results) / len(results),
        ))
    return rows


def sweep_effort(
    files: list[Path], material: Material, config: NestConfig, copies: int = 1
) -> list[tuple[str, float, float, int]]:
    """For each effort level: mean first-sheet utilisation, mean seconds and
    total sheets."""
    rows = []
    for effort in EFFORT_LEVELS:
        tuned = replace(config, effort=effort)
        results = [
            run_one(path, material, tuned, RasterOracle, "raster", copies=copies)
            for path in files
        ]
        rows.append((
            effort,
            sum(r.first_sheet_utilization for r in results) / len(results),
            sum(r.seconds for r in results) / len(results),
            sum(r.sheets for r in results),
        ))
    return rows


def compare_engines(
    files: list[Path], material: Material, config: NestConfig, copies: int = 1
) -> list[tuple[str, str, float, int]]:
    """Shelf vs. raster, per file: engine name, total utilisation, sheets."""
    rows = []
    for path in files:
        for name, factory in (("shelf", ShelfOracle), ("raster", RasterOracle)):
            result = run_one(path, material, config, factory, name, copies=copies)
            rows.append((path.name, name, result.total_utilization, result.sheets))
    return rows


def _best_contact(rows: list[tuple[float, float, float, int]]) -> float:
    """The contact weight with the best mean first-sheet utilisation.

    A la par, gana el que ademas haya sido mas rapido -- no hay ninguna
    razon para pagar mas tiempo por el mismo resultado.

    OJO: esta funcion solo mira el promedio agregado de los archivos del
    barrido. En la calibracion real (Task 24) ese promedio favorecia
    contact=0.0, pero un valor tan bajo rompe una capacidad concreta e
    independiente (una pieza chica dejaba de caer dentro del agujero de una
    grande, `test_a_small_part_is_nested_inside_a_big_hole`) que este barrido
    no ejercita. El valor elegido en `engine/oracle.py` no es ciegamente el
    que devuelve esta funcion -- ver `docs/superpowers/calibracion.md` para
    el razonamiento completo. Se deja la seleccion automatica igual, para
    una corrida futura sobre archivos distintos, pero el resultado hay que
    revisarlo contra ese mismo tipo de test antes de aceptarlo.
    """
    return min(rows, key=lambda row: (-row[1], row[2]))[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibra pesos, resolucion y niveles de esfuerzo.")
    parser.add_argument("--material", default="mdf18")
    parser.add_argument("--copias", type=int, default=1)
    args = parser.parse_args(argv)

    material = load_materials(DEFAULT_MATERIALS_PATH)[args.material]
    files = _load_files(FILES_DIR)
    if not files:
        print(f"no hay archivos utilizables en {FILES_DIR}", file=sys.stderr)
        return 1

    print(f"Calibrando sobre {len(files)} archivo(s) (--copias {args.copias}): "
          f"{', '.join(f.name for f in files)}\n")

    default_resolution = NestConfig().resolution
    print(f"PESO DE CONTACTO  (bottom_left fijo en 1.0, esfuerzo rapido, "
          f"resolucion {default_resolution} mm/px)")
    print(f"{'contacto':>10}{'aprov. 1ra placa':>18}{'seg. medio':>13}{'placas':>9}")
    print("-" * 50)
    weight_rows = sweep_weights(
        files, material, NestConfig(sep=6.0, margin=10.0, effort="rapido"), copies=args.copias
    )
    for contact, utilisation, seconds, sheets in weight_rows:
        print(f"{contact:>10.1f}{utilisation * 100:>17.1f}%{seconds:>13.1f}{sheets:>9}")

    best_contact = _best_contact(weight_rows)
    print(f"\n-> mejor contacto medido: {best_contact}")

    print("\nRESOLUCION DEL RASTER  (contact = mejor medido, esfuerzo rapido)")
    print(f"{'mm/px':>10}{'aprov. 1ra placa':>18}{'seg. medio':>13}")
    print("-" * 41)
    resolution_rows = sweep_resolution(
        files, material,
        NestConfig(
            sep=6.0, margin=10.0, effort="rapido",
            weights=Weights(bottom_left=1.0, contact=best_contact),
        ),
        copies=args.copias,
    )
    for resolution, utilisation, seconds in resolution_rows:
        print(f"{resolution:>10.1f}{utilisation * 100:>17.1f}%{seconds:>13.1f}")

    print(f"\nNIVELES DE ESFUERZO  (contact = mejor medido, "
          f"resolucion {default_resolution} mm/px)")
    print(f"{'nivel':>10}{'aprov. 1ra placa':>18}{'seg. medio':>13}{'placas':>9}")
    print("-" * 50)
    effort_rows = sweep_effort(
        files, material,
        NestConfig(sep=6.0, margin=10.0, weights=Weights(bottom_left=1.0, contact=best_contact)),
        copies=args.copias,
    )
    for effort, utilisation, seconds, sheets in effort_rows:
        print(f"{effort:>10}{utilisation * 100:>17.1f}%{seconds:>13.1f}{sheets:>9}")

    print("\nElegir el peso de contacto y la resolucion con mejor aprovechamiento de la")
    print("1ra placa y anotarlos en engine/oracle.py. Ajustar EFFORT_RESTARTS en")
    print("engine/packer.py para que 'normal' quede por debajo de 5 minutos y 'lento'")
    print("mejore de forma medible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
