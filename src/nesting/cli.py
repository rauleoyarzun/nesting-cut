"""Command line entry point: read, nest, verify, write."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    EFFORT_RESTARTS,
    PackResult,
    PartTooLargeError,
    layout_cost,
    pack,
    replicate,
)
from nesting.params import (
    NestParams,
    ParamsInvalidosError,
    mensaje_cli,
    validar,
)
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.nesting_tree import OverlappingContourError
from nesting.geometry.verify import verify
from nesting.io.ai_reader import read_ai
from nesting.io.dxf_reader import UNIT_SCALES, UnknownUnitsError, read_dxf
from nesting.io.diagnostic import write_diagnostic
from nesting.io.dxf_writer import write_dxf
from nesting.io.preview import write_preview
from nesting.io.rhino_reader import read_3dm
from nesting.model.discard import Discard
from nesting.model.material import DEFAULT_MATERIALS_PATH, Material, load_materials
from nesting.model.part import Part
from nesting.pipeline import (
    DEFAULT_CHAIN_TOL,
    OpenContourError,
    discard_plate_outline,
    prepare_parts,
)

EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_VERIFICATION_FAILED = 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        validar(
            NestParams(
                material=args.material,
                sep=args.sep,
                borde=args.borde,
                copias=args.copias,
                espejo=not args.sin_espejo,
                unidades=args.unidades,
                tol_cierre=args.tol_cierre,
                resolucion=args.resolucion,
                esfuerzo=args.esfuerzo,
            )
        )
    except ParamsInvalidosError as error:
        print(f"error: {mensaje_cli(error.rota)}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    if args.salida is None and args.diagnostico is None:
        print(
            "error: hay que pedir algo: -o/--salida para el DXF acomodado, "
            "--diagnostico para el PNG de revisión, o los dos.",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR

    # La previsualización dibuja el acomodo, y el acomodo solo corre cuando hay
    # un DXF que escribir. Sin esta comprobación, pedirla junto a --diagnostico
    # y sin -o la dejaba sin hacerse EN SILENCIO: el usuario esperaba un PNG
    # que nunca llegaba, sin una sola línea que lo explicara.
    if args.preview is not None and args.salida is None:
        print(
            "error: --preview dibuja cómo quedó el acomodo, así que necesita "
            "-o/--salida. Para revisar el archivo de entrada sin acomodar "
            "nada, use --diagnostico.",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR

    try:
        materials = load_materials(args.materiales)
    except (OSError, ValueError) as error:
        print(f"error: no se pudo leer el catálogo de materiales: {error}", file=sys.stderr)
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
            f"error: --angulos espera una lista de números separados por coma, "
            f"se recibió {args.angulos!r}",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR

    config = NestConfig(
        sep=args.sep,
        margin=args.borde,
        angles=angles,
        mirror=not args.sin_espejo,
        resolution=args.resolucion,
        effort=args.esfuerzo,
    )

    try:
        suffix = args.entrada.suffix.lower()
        if suffix == ".ai":
            drawing = read_ai(args.entrada)
        elif suffix == ".3dm":
            drawing = read_3dm(args.entrada, units_override=args.unidades)
        else:
            drawing = read_dxf(args.entrada, units_override=args.unidades)
        parts, warnings, discards = prepare_parts(drawing, chain_tol=args.tol_cierre)
        parts, plate_outlines = discard_plate_outline(
            parts, material.sheet_w, material.sheet_h
        )
        if plate_outlines:
            discards.extend(
                Discard(
                    reason="contorno_placa",
                    points=part.outer,
                    detail=f"{material.sheet_w:.0f} x {material.sheet_h:.0f} mm",
                    closed=True,
                )
                for part in plate_outlines
            )
            warnings.append(
                f"se ignoraron {len(plate_outlines)} rectángulo(s) del tamaño "
                f"exacto de la placa del material {args.material!r} "
                f"({material.sheet_w:.1f} x {material.sheet_h:.1f} mm); si "
                "alguno era una pieza de verdad, hay que cambiarle el tamaño."
            )
    # ChainingInvariantError (nesting.geometry.chaining) is deliberately NOT
    # caught here: it signals a bug inside the chaining module itself (an
    # input segment lost or double-counted), not a problem with the user's
    # drawing. Writing a DXF built on top of that would silently ship
    # incomplete geometry to the router, so it must propagate and crash
    # loudly instead of being folded into the input-error path below.
    except (UnknownUnitsError, OpenContourError, OverlappingContourError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except OSError as error:
        print(f"error: no se pudo leer {args.entrada}: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    for warning in warnings:
        print(f"aviso: {warning}")

    # Antes del acomodo a propósito, por dos motivos. Uno: si es lo único que
    # se pidió, el comando tiene que salir en un segundo, que es lo que lo
    # hace útil para iterar sobre un dibujo sucio. Dos: si la ruta del PNG
    # está mal, conviene enterarse ya y no después de medio minuto de trabajo
    # tirado. Y como todavía no se escribió nada más, fallar acá no puede
    # ocultarle al usuario un archivo que sí salió (el problema que tuvo
    # --preview en su momento).
    if args.diagnostico is not None:
        try:
            marked = write_diagnostic(args.diagnostico, parts, discards)
        except (OSError, ValueError) as error:
            print(
                f"error: no se pudo escribir el diagnóstico en "
                f"{args.diagnostico}: {error}. Verifique que el directorio de "
                "destino exista.",
                file=sys.stderr,
            )
            return EXIT_INPUT_ERROR
        print(f"Diagnóstico en {args.diagnostico}")
        if discards:
            print(
                f"  {len(discards)} descarte(s), {marked} marcado(s) sobre el dibujo"
            )
        else:
            print("  no se descartó nada: el archivo entró entero")

    if not parts:
        print(f"error: no se encontró ninguna pieza en {args.entrada}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    if args.salida is None:
        return EXIT_OK

    try:
        parts = replicate(parts, args.copias)
    except ValueError as error:
        # `validar` already rejects `--copias < 1` earlier, but
        # this stays as defense in depth: `replicate` is a public function of
        # the engine and should not be trusted blindly just because this is
        # currently its only caller.
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    try:
        # One `MaskCache` shared by every `RasterOracle` this `pack()` call
        # constructs (one per sheet, and one per retry attempt at effort
        # levels above "rapido"): masks depend only on
        # (part, angle, mirror, resolution, sep), never on sheet state, so
        # there is no reason to re-rasterize the same orientation for every
        # sheet or every retry.
        cache = MaskCache()
        result = pack(parts, material, config, lambda: RasterOracle(cache=cache))
    except (PartTooLargeError, ValueError) as error:
        # `rasterize` (nesting.engine.raster.masks) raises `ValueError` for a
        # resolution too fine to allocate a mask (e.g. --resolucion 0.005):
        # a clear, actionable Spanish message that used to escape uncaught
        # because this `try` only guarded against `PartTooLargeError`.
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    try:
        violations = verify(
            parts, result.placements, material.sheet_w, material.sheet_h,
            sep=config.sep, margin=config.margin,
        )
    except ValueError as error:
        # `verify` itself refuses a negative `sep`/`margin` (see Hallazgo 1b):
        # it is the arbiter and must not trust its callers, even though this
        # caller already validated the same values above.
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    if violations:
        print(
            f"error: la verificación geométrica encontró {len(violations)} problema(s). "
            f"No se escribió ningún archivo.",
            file=sys.stderr,
        )
        for violation in violations[:20]:
            print(f"  - {violation.detail}", file=sys.stderr)
        if len(violations) > 20:
            print(f"  ... y {len(violations) - 20} más", file=sys.stderr)
        if args.salida.exists():
            print(
                f"aviso: {args.salida} ya existía antes de esta corrida. "
                "No se lo modificó: ese archivo es de una corrida anterior y NO "
                "corresponde a esta verificación fallida.",
                file=sys.stderr,
            )
        return EXIT_VERIFICATION_FAILED

    try:
        write_dxf(
            args.salida, drawing, parts, result.placements,
            material.sheet_w, material.sheet_h,
        )
    except OSError as error:
        print(
            f"error: no se pudo escribir la salida en {args.salida}: {error}. "
            "Verifique que el directorio de destino exista.",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR

    if args.preview is not None:
        try:
            write_preview(
                args.preview, parts, result.placements,
                material.sheet_w, material.sheet_h, result.utilization,
                colors=_colors_by_part(drawing, parts),
            )
        except (ValueError, OSError) as error:
            # Cosmético, no estructural: el DXF (lo que de verdad va a la
            # fresadora) ya se escribió arriba, con éxito. Abortar acá con
            # error y código de entrada -- y sin llegar a imprimir el
            # resumen ni la línea "Escrito en ..." -- le hacía creer al
            # usuario que no salió nada. Se degrada a aviso y se sigue hasta
            # el resumen, con código 0.
            print(
                f"aviso: no se pudo escribir la previsualización en "
                f"{args.preview}: {error}"
            )
        else:
            print(f"Previsualización en {args.preview}")

    _print_summary(result, parts, material, len(parts), args.salida)
    return EXIT_OK


def _print_summary(
    result: PackResult, parts: Sequence[Part], material: Material,
    part_count: int, out_path: Path,
) -> None:
    costo = layout_cost(result, parts)
    used_height = costo.alto_ultima
    free_height = material.sheet_h - used_height

    for index, utilisation in enumerate(result.utilization):
        line = (
            f"Placa {index + 1}/{result.sheets_used}   "
            f"aprovechamiento {utilisation * 100:5.1f}%"
        )
        if index == result.sheets_used - 1 and free_height > 100.0:
            line += (
                f"   <- sobrante útil ~{material.sheet_w:.0f}x{free_height:.0f} mm"
            )
        print(line)

    print("-" * 34)
    print(
        f"{part_count} piezas - {result.sheets_used} placas - "
        f"{result.total_utilization * 100:.1f}% total - {result.seconds:.1f}s"
    )
    # Las dos cifras compiten: el criterio elige el layout que baja el
    # material de la última placa, y eso a veces acorta la tira libre a
    # cambio. Mostrar las dos es lo que deja decidir si conviene para este
    # trabajo, en vez de sólo ver la tira sin saber qué se resignó por ella.
    print(
        f"  material en la última placa: {costo.material_ultima / 1e6:.3f} m²"
        f"  ·  tira libre: {free_height:.0f} mm"
    )
    print(f"Escrito en {out_path}")


def _colors_by_part(drawing, parts: Sequence[Part]) -> dict[int, tuple[int, int, int]]:
    """Give each part the colour of its first source entity, for the preview."""
    colors: dict[int, tuple[int, int, int]] = {}
    for part in parts:
        if not part.entity_ids:
            continue
        rgb = drawing.entities[part.entity_ids[0]].style.rgb
        if rgb is not None:
            colors[part.id] = rgb
    return colors


class _ArgumentParser(argparse.ArgumentParser):
    """`argparse.ArgumentParser` whose usage errors exit 1, not 2.

    Exit code 2 is reserved by this program's own contract for
    `EXIT_VERIFICATION_FAILED`: "the geometric verification ran and found the
    layout unsound, so nothing was written". A usage error -- a missing
    required flag, a non-numeric `--copias`, an invalid `--unidades` -- never
    even reaches verification; it is an input error like any other, and
    argparse's default `sys.exit(2)` from `error()` would make it
    indistinguishable from a real verification failure to any script that
    only checks the exit code. `--help` is unaffected: it exits via
    `_HelpAction`, not through `error()`.
    """

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_INPUT_ERROR, f"{self.prog}: error: {message}\n")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = _ArgumentParser(
        prog="nest",
        description="Acomoda figuras vectoriales dentro de placas, minimizando el material.",
    )
    parser.add_argument(
        "entrada", type=Path,
        help="archivo de entrada (.dxf, .ai o .3dm)",
    )
    parser.add_argument("-o", "--salida", type=Path, default=None,
                        help="archivo DXF de salida (obligatorio salvo que se "
                             "pida solo --diagnostico)")
    parser.add_argument("--material", required=True, help="clave del catálogo de materiales")
    parser.add_argument(
        "--materiales", type=Path, default=DEFAULT_MATERIALS_PATH,
        help="ruta del catálogo de materiales (default: el que viene con el programa)",
    )
    parser.add_argument("--copias", type=int, default=1,
                        help="cuántas veces repetir todo el contenido del archivo")
    parser.add_argument("--sep", type=float, default=5.0,
                        help="separación mínima entre piezas, en mm")
    parser.add_argument("--borde", type=float, default=10.0,
                        help="margen contra el borde de la placa, en mm")
    parser.add_argument("--angulos", default="0,90,180,270",
                        help="ángulos candidatos, separados por coma")
    parser.add_argument("--sin-espejo", action="store_true", dest="sin_espejo",
                        help="no permitir piezas espejadas")
    parser.add_argument("--unidades", choices=sorted(UNIT_SCALES), default=None,
                        help="unidades del archivo de entrada, si no las declara")
    parser.add_argument("--tol-cierre", type=float, default=DEFAULT_CHAIN_TOL,
                        dest="tol_cierre",
                        help="tolerancia para unir extremos de contornos, en mm")
    parser.add_argument("--resolucion", type=float, default=2.0, dest="resolucion",
                        help="resolución del raster, en mm por píxel: más fino "
                             "acomoda un poco mejor pero tarda mucho más")
    parser.add_argument("--esfuerzo", choices=sorted(EFFORT_RESTARTS), default="normal",
                        help="cuánto tiempo dedicarle a mejorar el resultado")
    parser.add_argument("--preview", type=Path, default=None,
                        help="ruta del PNG de previsualización a generar")
    parser.add_argument("--diagnostico", type=Path, default=None,
                        help="ruta de un PNG que marca sobre el dibujo original "
                             "todo lo que el programa descartó y por qué; si es "
                             "lo único que se pide, no se acomoda nada y sale "
                             "en un segundo")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
