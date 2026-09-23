"""Tiempo de `rapido` sobre bench/files, y la huella exacta de cada layout.

Es la vara de la fase 2 del plan de pares y cartera: una idea para acelerar
una sola combinación se queda sólo si baja el tiempo total al menos un 30% y
deja TODOS los layouts idénticos. La huella es el `repr` de las colocaciones
en orden -- id, placa, ángulo, espejo, dx, dy --, que es exactamente lo que
termina en el DXF.

    .venv/bin/python bench/medir_rapido.py --salida out/fase2/antes.tsv
    .venv/bin/python bench/medir_rapido.py --salida out/fase2/a.tsv --comparar out/fase2/antes.tsv
"""

import argparse
import hashlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import pack
from nesting.engine.raster.oracle import RasterOracleFactory
from nesting.io.ai_reader import read_ai
from nesting.io.dxf_reader import read_dxf
from nesting.model.sheet import Sheet, SheetSupply
from nesting.pipeline import prepare_parts

FILES_DIR = Path(__file__).parent / "files"

# Los valores por omisión de la CLI, sobre mdf18: lo que corre alguien que
# no toca nada.
CONFIG = NestConfig(sep=5.0, margin=10.0, angles=(0.0, 90.0, 180.0, 270.0),
                    mirror=True, resolution=1.0, effort="rapido", workers=1)
PLAN = SheetSupply(stock=Sheet(1830.0, 2600.0, grain_tolerance=180.0), material_name="mdf18")


@dataclass(frozen=True)
class Fila:
    archivo: str
    segundos: float
    huella: str


def archivos() -> list[Path]:
    return sorted(p for p in FILES_DIR.iterdir() if p.suffix.lower() in (".dxf", ".ai"))


def medir(rutas: list[Path]) -> list[Fila]:
    filas = []
    for ruta in rutas:
        dibujo = read_ai(ruta) if ruta.suffix.lower() == ".ai" else read_dxf(ruta)
        piezas, _, _ = prepare_parts(dibujo)
        empezo = time.perf_counter()
        resultado = pack(piezas, PLAN, CONFIG, RasterOracleFactory())
        segundos = time.perf_counter() - empezo
        layout = repr([(p.part_id, p.sheet, p.transform) for p in resultado.placements])
        filas.append(Fila(ruta.name, segundos, hashlib.sha256(layout.encode()).hexdigest()))
    return filas


def escribir(filas: list[Fila], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        "".join(f"{f.archivo}\t{f.segundos:.3f}\t{f.huella}\n" for f in filas), encoding="utf-8"
    )


def leer(origen: Path) -> list[Fila]:
    filas = []
    for linea in origen.read_text(encoding="utf-8").splitlines():
        archivo, segundos, huella = linea.split("\t")
        filas.append(Fila(archivo, float(segundos), huella))
    return filas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tiempo de rápido y huella de cada layout.")
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--comparar", type=Path, default=None,
                        help="un TSV anterior: informa la baja de tiempo y si los layouts son idénticos")
    args = parser.parse_args(argv)

    filas = medir(archivos())
    escribir(filas, args.salida)
    for f in filas:
        print(f"{f.archivo:<28}{f.segundos:>9.1f} s  {f.huella[:16]}")
    total = sum(f.segundos for f in filas)
    print(f"{'total':<28}{total:>9.1f} s")

    if args.comparar is None:
        return 0
    antes = {f.archivo: f for f in leer(args.comparar)}
    distintos = [f.archivo for f in filas if antes[f.archivo].huella != f.huella]
    total_antes = sum(antes[f.archivo].segundos for f in filas)
    baja = 1.0 - total / total_antes
    print(f"baja de tiempo: {baja * 100:.1f}%  (criterio: al menos 30%)")
    print("layouts idénticos" if not distintos else f"LAYOUTS DISTINTOS: {', '.join(distintos)}")
    return 0 if baja >= 0.30 and not distintos else 1


if __name__ == "__main__":
    raise SystemExit(main())
