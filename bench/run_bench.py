"""Run the whole pipeline over every DXF in bench/files and report the numbers.

Measures what matters: how many sheets, how much of them is used, and how long
it took. Those three numbers are what decide whether a change to the engine was
an improvement.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import PartTooLargeError, layout_cost, pack, replicate
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.nesting_tree import OverlappingContourError
from nesting.geometry.verify import verify
from nesting.io.ai_reader import read_ai
from nesting.io.dxf_reader import UNIT_SCALES, UnknownUnitsError, read_dxf
from nesting.io.rhino_reader import read_3dm
from nesting.model.material import DEFAULT_MATERIALS_PATH, Material, load_materials
from nesting.pipeline import OpenContourError, prepare_parts

FILES_DIR = Path(__file__).parent / "files"

# Excepciones que significan "este archivo tiene un problema", no "el banco
# tiene un bug". Los archivos reales vienen sucios -- unidades sin declarar,
# contornos abiertos, piezas que no entran en la placa -- y ninguno de esos
# casos puede tirar abajo la medicion de los demas archivos de la corrida.
#
# `ChainingInvariantError` (`nesting.geometry.chaining`) queda deliberadamente
# afuera de esta lista: senala un bug interno del proyecto, no un problema del
# archivo, y tiene que propagar y explotar ruidosamente en vez de quedar
# enmascarada como una fila de error mas.
FILE_ERRORS = (
    UnknownUnitsError,
    OpenContourError,
    OverlappingContourError,
    PartTooLargeError,
    OSError,
    ValueError,
)


def _new_raster_factory():
    """A fresh `RasterOracle` factory, backed by one `MaskCache` for a whole
    `pack()` call.

    Masks depend only on (part, angle, mirror, resolution, sep) -- never on
    sheet state -- so one cache shared by every `RasterOracle` `pack()`
    constructs (one per sheet, and one per retry once effort levels exist)
    avoids re-rasterizing the same orientation over and over. A closure
    keeps this a plain `Callable[[], Oracle]` from `pack()`'s point of view,
    so `pack()` itself stays engine-agnostic. Built fresh per file so the
    cache doesn't grow across unrelated files for the rest of the bench run.
    """
    cache = MaskCache()
    return lambda: RasterOracle(cache=cache)


@dataclass(frozen=True)
class BenchResult:
    name: str
    parts: int
    sheets: int
    total_utilization: float
    """Piezas / (area de placa * placas usadas), sobre TODAS las placas.

    Con el mismo conjunto de piezas para ambos motores, esta metrica solo
    puede cambiar si cambia la cantidad de placas: a igualdad de placas da
    identica por construccion, aunque un motor haya llenado la primera mucho
    mejor que el otro. Para el producto esta bien -- las placas son la plata
    que le cuesta al usuario -- pero para comparar motores y calibrar es
    ciega a la calidad del empaquetado. Por eso conviven con
    `first_sheet_utilization`, que si distingue.
    """

    first_sheet_utilization: float
    """Aprovechamiento de la primera placa unicamente (`PackResult.utilization[0]`).

    A diferencia de `total_utilization`, esta si cambia con la calidad del
    empaquetado aunque la cantidad de placas termine siendo la misma: mide
    que tan bien aprovecha el motor el espacio, no lo que le cuesta al
    usuario. Las dos metricas hacen falta porque miden cosas distintas.
    """

    seconds: float
    """Tiempo de `pack()` unicamente, tomado de `PackResult.seconds`.

    No incluye leer el DXF (`read_dxf`) ni preparar las piezas
    (`prepare_parts`): mide solo el empaquetado. Es una eleccion defendible
    -- es la parte que varia con el motor -- pero hay que tenerla clara
    porque este numero calibra los niveles de esfuerzo mas adelante. Ademas
    queda mejor a futuro: cuando el empaquetado haga varios reintentos
    internos, `PackResult.seconds` los va a cubrir a todos, que es
    exactamente lo que interesa medir.
    """
    engine: str
    violations: int

    material_ultima_m2: float = 0.0
    """Área de pieza que queda en la última placa, en m² (`CostoLayout.material_ultima`).

    Es el segundo criterio de `layout_cost` desde la Tarea 1, y se agregó acá
    en la Tarea 6 porque hasta entonces el banco medía una cosa y el motor
    optimizaba otra: `first_sheet_utilization` no distingue entre un layout
    que deja 4 piezas en la última placa y uno que deja 2, si la primera
    placa quedó igual de llena. Calibrar contra una métrica que el motor no
    persigue es calibrar a ciegas.
    """

    tira_libre_mm: float = 0.0
    """`sheet_h - CostoLayout.alto_ultima`: la tira libre de la última placa.

    Convive con `material_ultima_m2` porque las dos cifras compiten y el
    usuario ve las dos (ver `cli.py::_print_summary`). En los barridos de la
    Tarea 6 hubo configuraciones que dejaban la mitad de material en la
    última placa con exactamente la misma tira libre: sin esta columna al
    lado, esa diferencia no se ve.
    """


def run_one(
    dxf_path: Path,
    material: Material,
    config: NestConfig,
    oracle_factory,
    engine_name: str,
    copies: int = 1,
    units: str | None = None,
) -> BenchResult:
    """Nest one file and measure the outcome.

    Deja propagar cualquier excepcion tal cual: aislar los archivos que
    fallan del resto de la corrida es responsabilidad de quien llama
    (`main`), no de esta funcion.

    El formato se elige por extension, igual que hace `cli.py`: `.ai` y
    `.3dm` tienen su propio lector (ninguno de los dos acepta
    `units_override`, que solo tiene sentido para un DXF sin unidades
    declaradas), y cualquier otra extension pasa por `read_dxf`. Se agrego
    en la Tarea 24 para que el banco pueda medir contra los archivos reales
    del proyecto (`.ai` incluido), no solo contra el DXF sintetico.
    """
    suffix = dxf_path.suffix.lower()
    if suffix == ".ai":
        drawing = read_ai(dxf_path)
    elif suffix == ".3dm":
        drawing = read_3dm(dxf_path)
    else:
        drawing = read_dxf(dxf_path, units_override=units)
    parts, _, _ = prepare_parts(drawing)
    parts = replicate(parts, copies)

    result = pack(parts, material, config, oracle_factory)
    costo = layout_cost(result, parts)

    violations = verify(
        parts, result.placements, material.sheet_w, material.sheet_h,
        sep=config.sep, margin=config.margin,
    )

    return BenchResult(
        name=dxf_path.name,
        parts=len(parts),
        sheets=result.sheets_used,
        total_utilization=result.total_utilization,
        # `PackResult.utilization` ya trae el aprovechamiento por placa: se
        # reusa en vez de recalcularlo a partir de las placements.
        first_sheet_utilization=result.utilization[0] if result.utilization else 0.0,
        seconds=result.seconds,
        engine=engine_name,
        violations=len(violations),
        material_ultima_m2=costo.material_ultima / 1e6,
        tira_libre_mm=material.sheet_h - costo.alto_ultima,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Banco de pruebas del motor de nesting.")
    parser.add_argument("--material", default="mdf18")
    parser.add_argument("--copias", type=int, default=1)
    parser.add_argument("--sep", type=float, default=6.0)
    parser.add_argument("--borde", type=float, default=10.0)
    parser.add_argument(
        "--unidades", choices=sorted(UNIT_SCALES), default=None,
        help="unidades del archivo de entrada, para los que no las declaran",
    )
    args = parser.parse_args(argv)

    material = load_materials(DEFAULT_MATERIALS_PATH)[args.material]
    config = NestConfig(sep=args.sep, margin=args.borde)

    files = sorted(FILES_DIR.glob("*.dxf"))
    if not files:
        print(
            f"no hay archivos en {FILES_DIR}. "
            f"Corra '.venv/bin/python bench/make_sample.py' o copie ahí un DXF real.",
            file=sys.stderr,
        )
        return 1

    print(
        f"{'archivo':<24}{'motor':<10}{'piezas':>7}{'placas':>8}{'aprov.':>9}"
        f"{'1ra placa':>11}{'seg':>8}"
    )
    print("-" * 77)

    # Each entry makes a fresh factory per file: the shelf engine has no
    # cache to share, and the raster engine gets one `MaskCache` per file
    # (see `_new_raster_factory`), not one for the whole bench run.
    engines = [("shelf", lambda: ShelfOracle), ("raster", _new_raster_factory)]

    failed = 0
    for path in files:
        baseline = None
        for name, make_factory in engines:
            factory = make_factory()
            try:
                result = run_one(
                    path, material, config, factory, name, args.copias, args.unidades,
                )
            except FILE_ERRORS as error:
                # Un archivo sucio no puede tirar abajo la medicion de los demas:
                # se informa el motivo en una fila y se sigue con el resto.
                failed += 1
                print(f"{path.name:<24}{'ERROR':<10}{type(error).__name__}: {error}")
                continue

            flag = "  VIOLACIONES!" if result.violations else ""
            if name == "shelf":
                baseline = result.total_utilization
                delta = ""
            else:
                delta = f"  (+{(result.total_utilization - baseline) * 100:.1f} pts)"
            print(
                f"{result.name:<24}{result.engine:<10}{result.parts:>7}{result.sheets:>8}"
                f"{result.total_utilization * 100:>8.1f}%"
                f"{result.first_sheet_utilization * 100:>10.1f}%"
                f"{result.seconds:>8.1f}{delta}{flag}"
            )

    if failed:
        print(
            f"\n{failed} de {len(files)} archivo(s) no se pudieron medir "
            f"(ver las filas ERROR arriba).",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
