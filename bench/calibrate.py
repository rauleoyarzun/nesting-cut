"""Measure the knobs that were left provisional: scoring weights, raster
resolution and effort.

Nothing here invents a number. Every value that ends up in the defaults comes
out of a run over the project's real files (`bench/files/`).

Criterio para comparar configuraciones entre si (cambiado en la Tarea 6): el
MISMO que usa el motor, `CostoLayout(placas_nuevas, material_ultima, alto_ultima)`.
Cada barrido devuelve, por configuracion, placas totales, material medio en
la ultima placa y tira libre media, ademas del aprovechamiento de la primera
placa y el tiempo, y `_mejor` ordena por placas, despues por material en la
ultima, y desempata por tiempo.

Antes se ordenaba por `first_sheet_utilization`. Esa metrica no se tiro --
sigue siendo la unica columna con diferencias continuas cuando dos
configuraciones empatan en placas, y es la que distingue lo que
`total_utilization` no puede (area de piezas sobre area de placas usadas da
identica por construccion a igualdad de placas; ver el docstring de
`BenchResult` en `run_bench.py`) -- pero dejo de ser la que manda, porque no
es la que el motor optimiza: hubo configuraciones con aprovechamiento de
primera placa identico y el doble de material en la ultima.
"""

import argparse
import statistics
import sys
from dataclasses import replace
from pathlib import Path

from nesting.engine.oracle import NestConfig, Weights
from nesting.engine.packer import (
    initial_forecast,
    orientations,
    pack,
    probe_query_seconds,
    replicate,
)
from nesting.engine.raster.oracle import RasterOracle, RasterOracleFactory
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.model.material import DEFAULT_MATERIALS_PATH, VETA_LIBRE, VETA_RESPETAR, Material, load_materials
from nesting.model.sheet import SheetSupply

sys.path.insert(0, str(Path(__file__).parent))
from run_bench import FILE_ERRORS, FILES_DIR, run_one  # noqa: E402

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


FILA = "eje, aprov. 1ra placa, seg. medio, placas totales, material ultima (m2), tira libre (mm)"
"""Forma de las filas que devuelven los tres barridos, en orden.

Las dos ultimas columnas se agregaron en la Tarea 6 y son las que ahora
mandan al elegir (`_mejor`): desde la Tarea 1 el motor minimiza
`CostoLayout(placas_nuevas, material_ultima, alto_ultima)`, asi que un barrido que
ordenara por aprovechamiento de la primera placa estaria eligiendo por una
cifra que el motor no persigue. Se dejan igual las tres primeras columnas --
el aprovechamiento de la primera placa sigue siendo la unica que muestra
diferencias continuas cuando dos configuraciones empatan en placas, y el
tiempo sigue siendo el que decide los empates.
"""


def _fila(eje, results) -> tuple:
    """Una fila agregada a partir de los resultados por archivo. Ver `FILA`."""
    return (
        eje,
        sum(r.first_sheet_utilization for r in results) / len(results),
        sum(r.seconds for r in results) / len(results),
        sum(r.sheets for r in results),
        sum(r.material_ultima_m2 for r in results) / len(results),
        sum(r.tira_libre_mm for r in results) / len(results),
    )


def sweep_weights(
    files: list[Path], material: Material, config: NestConfig, copies: int = 1
) -> list[tuple]:
    """Una fila con la forma de `FILA` por cada peso de contacto candidato."""
    rows = []
    for contact in CONTACT_CANDIDATES:
        tuned = replace(config, weights=Weights(bottom_left=1.0, contact=contact))
        rows.append(_fila(contact, [
            run_one(path, material, tuned, RasterOracle, "raster", copies=copies)
            for path in files
        ]))
    return rows


def sweep_resolution(
    files: list[Path], material: Material, config: NestConfig, copies: int = 1
) -> list[tuple]:
    """Una fila con la forma de `FILA` por cada resolucion candidata.

    Hasta la Tarea 6 este barrido no devolvia `sheets` ni el material de la
    ultima placa, con el argumento de que la resolucion afecta la calidad de
    forma continua y eso solo se ve en `first_sheet_utilization`. El
    argumento era correcto para lo que la resolucion hacia entonces
    (tambien fijaba la separacion real), pero ahora la separacion la decide
    el arbitro exacto y lo unico que queda por saber de la resolucion es si
    mueve el layout: `material_ultima` es la cifra que lo dice, porque es la
    que el motor minimiza.
    """
    rows = []
    for resolution in RESOLUTION_CANDIDATES:
        tuned = replace(config, resolution=resolution)
        rows.append(_fila(resolution, [
            run_one(path, material, tuned, RasterOracle, "raster", copies=copies)
            for path in files
        ]))
    return rows


def sweep_effort(
    files: list[Path], material: Material, config: NestConfig, copies: int = 1
) -> list[tuple]:
    """Una fila con la forma de `FILA` por cada nivel de esfuerzo."""
    rows = []
    for effort in EFFORT_LEVELS:
        tuned = replace(config, effort=effort)
        rows.append(_fila(effort, [
            run_one(path, material, tuned, RasterOracle, "raster", copies=copies)
            for path in files
        ]))
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


def _parts_of(path: Path, copies: int = 1) -> list:
    """Las piezas de un archivo del banco, replicadas `copies` veces."""
    from nesting.io.ai_reader import read_ai
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    drawing = read_ai(path) if path.suffix.lower() == ".ai" else read_dxf(path)
    parts, _, _ = prepare_parts(drawing)
    return replicate(parts, copies)


FILA_FACTOR = (
    "archivo, piezas, orientaciones, consultas previstas al arrancar, "
    "consultas reales, s/consulta de la prueba, s/consulta real, factor, s reales"
)
"""Forma de las filas de `measure_fill_factor`, en orden.

El factor es `s/consulta real / s/consulta de la prueba`: lo que
`nesting_app.corredor.FACTOR_LLENO` corrige. La previsión de arranque va al
lado para ver cuánto del error de la estimación previa es de la previsión
de consultas y cuánto del costo por consulta; el factor corrige sólo lo
segundo.
"""


def measure_fill_factor(
    files: list[Path], material: Material, config: NestConfig, copies: int = 1
) -> list[tuple]:
    """Una fila con la forma de `FILA_FACTOR` por cada archivo que se pudo medir."""
    rows = []
    for path in files:
        parts = _parts_of(path, copies)
        supply = SheetSupply(stock=material.stock_sheet(), material_name=material.name)
        probe = probe_query_seconds(
            parts, supply, config, RasterOracleFactory()
        )
        if probe is None:
            print(f"aviso: {path.name} no deja ninguna orientación con esta veta; se salta")
            continue
        forecast = initial_forecast(parts, supply, config)
        avances = []
        try:
            result = pack(
                parts, supply, config, RasterOracleFactory(),
                progreso=lambda a: avances.append(a) or True,
            )
        except FILE_ERRORS as error:
            print(f"aviso: {path.name} no se pudo acomodar ({type(error).__name__}: {error}); se salta")
            continue
        real = avances[-1].consultas_hechas
        per_query = result.seconds / real
        rows.append((
            path.name, len(parts), len(orientations(supply.stock, config)),
            forecast, real, probe, per_query, per_query / probe, result.seconds,
        ))
    return rows


def _main_factor_lleno(args, material: Material, files: list[Path]) -> int:
    """El modo `--factor-lleno`: sólo mide, imprime la tabla y la mediana."""
    if args.veta is not None:
        material = replace(
            material,
            grain_tolerance=VETA_LIBRE if args.veta == "libre" else VETA_RESPETAR,
        )
    angles = tuple(i * 360.0 / args.posiciones for i in range(args.posiciones))
    config = NestConfig(
        sep=args.sep, margin=args.borde, angles=angles, mirror=True,
        resolution=args.resolucion, effort=args.esfuerzo,
    )
    print(
        f"FACTOR_LLENO  ({material.name}, veta {material.grain_tolerance:g} grados, "
        f"{args.posiciones} posiciones con espejo, sep {args.sep:g}, borde {args.borde:g}, "
        f"{args.resolucion:g} mm/px, esfuerzo {args.esfuerzo}, --copias {args.copias})"
    )
    print(
        f"{'archivo':<28}{'piezas':>7}{'orient.':>8}{'previstas':>10}{'reales':>8}"
        f"{'s/c prueba':>11}{'s/c real':>10}{'factor':>8}{'s reales':>10}"
    )
    print("-" * 100)
    rows = measure_fill_factor(files, material, config, copies=args.copias)
    for r in rows:
        print(
            f"{r[0]:<28}{r[1]:>7}{r[2]:>8}{r[3]:>10}{r[4]:>8}"
            f"{r[5]:>11.4f}{r[6]:>10.4f}{r[7]:>8.2f}{r[8]:>10.1f}"
        )
    if not rows:
        print("no se pudo medir ningún archivo", file=sys.stderr)
        return 1
    print(f"\n-> mediana del factor: {statistics.median(r[7] for r in rows):.2f}")
    print("Anotarla en src/nesting_app/corredor.py::FACTOR_LLENO con esta tabla al lado.")
    return 0


def _mejor(rows: list[tuple]) -> object:
    """El mejor eje de un barrido, con el MISMO criterio que usa el motor.

    Hasta la Tarea 6 esto ordenaba por aprovechamiento de la primera placa,
    desempatando por tiempo. Esa metrica ya no es la que el motor persigue:
    desde la Tarea 1 `layout_cost` minimiza
    `CostoLayout(placas_nuevas, material_ultima, alto_ultima)`, y las dos cosas se
    separan de verdad -- en el barrido de contacto sobre
    `banqueta final raulo.ai` (Tarea 6), contacto 0.5 y 0.8 empataron en
    aprovechamiento de la primera placa (61.00% las dos) y sin embargo
    dejaron 0.781 m2 y 0.859 m2 en la ultima: la metrica vieja no podia
    distinguirlas y el motor si. Un calibrador que ordena por una cifra que
    el motor no optimiza recomienda valores que el motor despues no elige.

    El orden es entonces: menos placas, menos material en la ultima, menos
    tiempo. La tira libre NO entra: es la cifra que se le muestra al usuario
    al lado de la otra, pero como criterio es justamente la que la Tarea 1
    saco del segundo lugar por premiar layouts mas lejos de poder tirar la
    placa.

    OJO: esta funcion solo mira los archivos del barrido, y hay una
    capacidad concreta que ninguno de ellos ejercita: que una pieza chica
    caiga dentro del agujero de una grande
    (`test_a_small_part_is_nested_inside_a_big_hole`). En la recalibracion
    de la Tarea 6 eso volvio a ser decisivo: contacto 0.0 gano el barrido en
    dos de los tres archivos y es hasta 4.8x mas rapido, pero rompe esa
    capacidad (se pierde por debajo de 0.7, bisectado) y quedo descartado
    igual. El valor de `engine/oracle.py` no es ciegamente el que devuelve
    esta funcion -- ver `docs/superpowers/calibracion.md` para el
    razonamiento completo. Se deja la seleccion automatica, para una corrida
    futura sobre archivos distintos, pero el resultado hay que revisarlo
    contra ese mismo test antes de aceptarlo.
    """
    return min(rows, key=lambda row: (row[3], row[4], row[2]))[0]


def _encabezado(eje: str) -> None:
    print(f"{eje:>10}{'aprov. 1ra placa':>18}{'seg. medio':>13}{'placas':>9}"
          f"{'mat. ult. m2':>14}{'tira mm':>10}")
    print("-" * 74)


def _imprimir(row: tuple) -> None:
    eje, utilisation, seconds, sheets, material_ultima, tira = row
    etiqueta = f"{eje:>10.1f}" if isinstance(eje, float) else f"{eje:>10}"
    print(f"{etiqueta}{utilisation * 100:>17.1f}%{seconds:>13.1f}{sheets:>9}"
          f"{material_ultima:>14.4f}{tira:>10.0f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibra pesos, resolucion y niveles de esfuerzo.")
    parser.add_argument("--material", default="mdf18")
    parser.add_argument("--copias", type=int, default=1)
    parser.add_argument(
        "--factor-lleno", action="store_true",
        help="mide sólo FACTOR_LLENO (src/nesting_app/corredor.py); las opciones "
             "de abajo valen sólo en este modo",
    )
    parser.add_argument("--sep", type=float, default=6.0)
    parser.add_argument("--borde", type=float, default=10.0)
    parser.add_argument("--resolucion", type=float, default=1.0)
    parser.add_argument("--esfuerzo", choices=EFFORT_LEVELS, default="normal")
    parser.add_argument("--posiciones", type=int, default=4)
    parser.add_argument("--veta", choices=("respetar", "libre"), default=None)
    args = parser.parse_args(argv)

    material = load_materials(DEFAULT_MATERIALS_PATH)[args.material]
    files = _load_files(FILES_DIR)
    if not files:
        print(f"no hay archivos utilizables en {FILES_DIR}", file=sys.stderr)
        return 1

    if args.factor_lleno:
        return _main_factor_lleno(args, material, files)

    print(f"Calibrando sobre {len(files)} archivo(s) (--copias {args.copias}): "
          f"{', '.join(f.name for f in files)}\n")

    default_resolution = NestConfig().resolution
    print(f"PESO DE CONTACTO  (bottom_left fijo en 1.0, esfuerzo rapido, "
          f"resolucion {default_resolution} mm/px)")
    _encabezado("contacto")
    weight_rows = sweep_weights(
        files, material, NestConfig(sep=6.0, margin=10.0, effort="rapido"), copies=args.copias
    )
    for row in weight_rows:
        _imprimir(row)

    best_contact = _mejor(weight_rows)
    print(f"\n-> mejor contacto medido: {best_contact}")

    print("\nRESOLUCION DEL RASTER  (contact = mejor medido, esfuerzo rapido)")
    _encabezado("mm/px")
    resolution_rows = sweep_resolution(
        files, material,
        NestConfig(
            sep=6.0, margin=10.0, effort="rapido",
            weights=Weights(bottom_left=1.0, contact=best_contact),
        ),
        copies=args.copias,
    )
    for row in resolution_rows:
        _imprimir(row)

    print(f"\nNIVELES DE ESFUERZO  (contact = mejor medido, "
          f"resolucion {default_resolution} mm/px)")
    _encabezado("nivel")
    effort_rows = sweep_effort(
        files, material,
        NestConfig(sep=6.0, margin=10.0, weights=Weights(bottom_left=1.0, contact=best_contact)),
        copies=args.copias,
    )
    for row in effort_rows:
        _imprimir(row)

    print("\nElegir el peso de contacto y la resolucion que dejen menos placas y, a")
    print("igualdad de placas, menos material en la ultima -- el mismo orden que usa")
    print("`layout_cost` -- y anotarlos en engine/oracle.py CON LA MEDICION AL LADO.")
    print("Antes de bajar el contacto, correr")
    print("tests/engine/raster/test_raster_oracle.py::test_a_small_part_is_nested_inside_a_big_hole:")
    print("este barrido no ejercita el anidado en agujeros y ese test es el que manda.")
    print("Ajustar EFFORT_BATCHES en engine/cartera.py para que 'normal' quede por")
    print("debajo de 5 minutos y 'lento' mejore de forma medible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
