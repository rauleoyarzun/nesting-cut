"""The arbiter: does a finished layout actually respect its own rules?

Works on exact shapely polygons, never on rasters, and knows nothing about any
engine. Every output is checked here before it is written, and the tests use it
as their oracle.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import Polygon, box
from shapely.strtree import STRtree

from nesting.geometry.transform import apply_points
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement
from nesting.model.sheet import Sheet

EPS = 1e-6
"""Numeric slack in mm, so a part placed at exactly `sep` is not flagged."""

OVERLAP_AREA_THRESHOLD_MM2 = 1e-6
"""Intersection area, in mm^2, above which an overlap is a real violation.

Two parts that are meant to touch along a shared edge (e.g. after a 90 degree
rotation) can end up with a sliver of phantom intersection purely from
floating-point noise, on the order of 1e-11 mm^2. A square micron (1e-6 mm^2)
doesn't exist for a 6 mm router bit cutting MDF, so it sits comfortably above
that noise floor (five orders of magnitude) while staying many orders of
magnitude below anything a real overlap would produce (a small but genuine
overlap is on the order of 1 mm^2 or more). This threshold cannot mask a real
overlap; it only ignores intersections too small to be physically meaningful.
"""


@dataclass(frozen=True)
class Violation:
    kind: str
    """One of "overlap", "separation", "out_of_bounds", "invalid_geometry".

    "invalid_geometry" means the placed part's own contour is not a valid
    polygon (e.g. a self-intersecting outline); shapely's predicates are not
    guaranteed to behave once that happens, so the piece is reported and
    excluded from the other checks rather than fed to them.
    """

    part_a: int
    part_b: int | None
    sheet: int
    detail: str
    """User-facing message, in Spanish."""


def placed_polygon(part: Part, t: Transform) -> Polygon:
    """The exact material footprint of `part` once `t` is applied."""
    return Polygon(
        apply_points(t, part.outer),
        [apply_points(t, hole) for hole in part.holes],
    )


def verify(
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheets: Sequence[Sheet],
    sep: float,
    margin: float,
) -> list[Violation]:
    """Revisa un layout terminado. Una lista vacía significa que está sano.

    `sheets` tiene que cubrir cada índice que usen las colocaciones: es lo
    que permite que cada pieza se verifique contra SU placa. Un recorte de
    600x800 y una placa de 1830x2600 aceptan piezas distintas, y verificar
    la primera contra la medida de la segunda es exactamente el "todo bien"
    equivocado que esta función existe para impedir.
    """
    if sep < 0 or margin < 0:
        # This is the arbiter: it must not trust whoever calls it. A negative
        # `sep` would silently disable the separation check below (a real
        # `distance` is never < 0, so `distance < sep - EPS` could never
        # fire), and a negative `margin` would grow the "usable" rectangle
        # past the physical sheet, both of which are exactly the kind of
        # silent, wrong "all clear" this function exists to prevent. This is
        # not a `Violation` -- it is not a problem with the layout, it is a
        # misuse of the verifier -- so it raises instead of being reported.
        raise ValueError(
            f"verify: 'sep' y 'margin' tienen que ser >= 0 (se recibió sep={sep!r}, "
            f"margin={margin!r})"
        )

    by_id = {p.id: p for p in parts}
    violations: list[Violation] = []

    by_sheet: dict[int, list[Placement]] = {}
    for placement in placements:
        by_sheet.setdefault(placement.sheet, []).append(placement)

    fuera_de_rango = [i for i in by_sheet if not (0 <= i < len(sheets))]
    if fuera_de_rango:
        raise ValueError(
            f"verify: hay colocaciones en la(s) placa(s) {sorted(fuera_de_rango)}, "
            f"pero se recibieron {len(sheets)} placa(s). No se puede verificar una "
            "pieza contra una placa que no se sabe qué medida tiene."
        )

    for sheet, sheet_placements in sorted(by_sheet.items()):
        hoja = sheets[sheet]
        # box() silently swaps inverted min/max bounds instead of raising or
        # producing an empty region, so a margin that consumes more than half
        # of either sheet dimension would otherwise yield a phantom "usable"
        # strip in the middle of the sheet. Guard for that explicitly: with no
        # positive usable area on either axis, the whole sheet is out of
        # bounds.
        usable_w = hoja.width - 2 * margin
        usable_h = hoja.height - 2 * margin
        usable = (
            box(margin, margin, hoja.width - margin, hoja.height - margin)
            if usable_w > 0 and usable_h > 0
            else None
        )

        polygons = [placed_polygon(by_id[p.part_id], p.transform) for p in sheet_placements]

        valid_placements: list[Placement] = []
        valid_polygons: list[Polygon] = []
        for placement, polygon in zip(sheet_placements, polygons):
            if not polygon.is_valid:
                violations.append(
                    Violation(
                        kind="invalid_geometry",
                        part_a=placement.part_id,
                        part_b=None,
                        sheet=sheet,
                        detail=(
                            f"la pieza {placement.part_id} tiene una geometría inválida "
                            "(el contorno se autointersecta) y no se puede verificar"
                        ),
                    )
                )
                continue
            valid_placements.append(placement)
            valid_polygons.append(polygon)

        for placement, polygon in zip(valid_placements, valid_polygons):
            if usable is None or not usable.buffer(EPS).contains(polygon):
                if usable is None:
                    detail = (
                        f"la pieza {placement.part_id} no se puede verificar contra el margen: "
                        f"con margen {margin} mm en una placa de {hoja.width}x{hoja.height} mm "
                        f"no queda área útil (ancho útil {usable_w} mm, alto útil "
                        f"{usable_h} mm)"
                    )
                else:
                    detail = (
                        f"la pieza {placement.part_id} se sale del área útil de la placa "
                        f"{sheet + 1} (margen {margin} mm)"
                    )
                violations.append(
                    Violation(
                        kind="out_of_bounds",
                        part_a=placement.part_id,
                        part_b=None,
                        sheet=sheet,
                        detail=detail,
                    )
                )

        violations.extend(_check_pairs(sheet, valid_placements, valid_polygons, sep))

    return violations


def _check_pairs(
    sheet: int,
    placements: Sequence[Placement],
    polygons: Sequence[Polygon],
    sep: float,
) -> list[Violation]:
    """Pairwise overlap and separation checks, narrowed by a spatial index."""
    violations: list[Violation] = []
    if len(polygons) < 2:
        return violations

    # Growing each polygon by `sep` turns "closer than sep" into "intersects",
    # so the index can discard the vast majority of pairs up front.
    tree = STRtree([p.buffer(sep) for p in polygons])
    seen: set[tuple[int, int]] = set()

    for i, polygon in enumerate(polygons):
        for j in tree.query(polygon):
            j = int(j)
            if j == i:
                continue
            pair = (min(i, j), max(i, j))
            if pair in seen:
                continue
            seen.add(pair)

            a_id = placements[i].part_id
            b_id = placements[j].part_id

            if polygon.intersects(polygons[j]):
                overlap_area = polygon.intersection(polygons[j]).area
                if overlap_area > OVERLAP_AREA_THRESHOLD_MM2:
                    violations.append(
                        Violation(
                            kind="overlap",
                            part_a=a_id,
                            part_b=b_id,
                            sheet=sheet,
                            detail=(
                                f"las piezas {a_id} y {b_id} se superponen en la placa {sheet + 1}"
                            ),
                        )
                    )
                    continue

            distance = polygon.distance(polygons[j])
            if distance < sep - EPS:
                violations.append(
                    Violation(
                        kind="separation",
                        part_a=a_id,
                        part_b=b_id,
                        sheet=sheet,
                        detail=(
                            f"las piezas {a_id} y {b_id} quedaron a {distance:.3f} mm "
                            f"en la placa {sheet + 1}; el mínimo pedido es {sep} mm"
                        ),
                    )
                )

    return violations
