"""Decide which contours are parts and which are holes.

Even nesting depth means material, odd means a hole, following the usual CAD
convention. A contour at depth two or deeper becomes an independent part rather
than staying nested where it happened to be drawn, so the engine is free to
place it anywhere.
"""

from collections.abc import Sequence

from shapely.geometry import Polygon
from shapely.strtree import STRtree

from nesting.model.part import Contour, Part

# Fracción del área del agujero que toleramos como "derrame" fuera del contorno
# exterior. Existe para absorber el ruido de punto flotante de las operaciones
# booleanas de shapely (difference) sobre las mismas coordenadas que ya pasaron
# el chequeo de `representative_point()` — no para tolerar un desborde real.
# Una parte por millón es varios órdenes de magnitud más grande que el ruido de
# doble precisión esperable en estas geometrías, y varios órdenes más chica que
# cualquier desborde que valga la pena reportar.
_RELATIVE_OVERLAP_TOLERANCE = 1e-6

# Piso absoluto en mm² para cuando el agujero es tan chico que la tolerancia
# relativa de arriba queda por debajo del propio ruido de punto flotante
# (p.ej. un agujero de 0.01 mm² de área). Un milésimo de mm² equivale a un
# cuadrado de ~0.03 mm de lado: por debajo de cualquier tolerancia de corte CNC
# real, así que no puede corresponder a un desborde intencional del dibujo.
_ABSOLUTE_OVERLAP_TOLERANCE_MM2 = 1e-3

# Área mínima, en mm², para que un contorno se trate como geometría real en
# vez de ruido degenerado (spec §6.3: "Contorno de área cero o degenerado →
# se saltea, con aviso"). Cubre dos casos: un contorno colineal (todos sus
# puntos sobre una recta, como (0,0)-(100,0)-(50,0)) y un "moño"
# autointersecante cuyos dos lóbulos tienen orientación opuesta y su área con
# signo se cancela -- ambos midieron exactamente 0.0 mm² con `Polygon(...).area`
# en los casos que motivaron este arreglo, antes de la corrección de
# `buffer(0)` de más abajo (que "arreglaría" el moño a su área real, cuando lo
# que corresponde es saltearlo, no repararlo).
# El umbral queda muy por debajo del agujero más chico que este módulo
# considera legítimo (1e-6 mm², ver `test_tiny_hole_correctly_nested_does_not_raise`),
# y muy por encima del ruido de punto flotante de un cálculo de área que da
# exactamente 0.0: ninguna pieza ni agujero real de carpintería puede medir
# esto o menos.
_NEGLIGIBLE_CONTOUR_AREA_MM2 = 1e-9


class OverlappingContourError(Exception):
    """Un contorno se acepta como agujero pero solo se superpone parcialmente
    con su supuesto contorno exterior, en vez de estar anidado en él."""


def build_parts(contours: Sequence[Contour]) -> tuple[list[Part], list[Contour]]:
    """Group `contours` into parts by containment depth.

    Returns the parts alongside the input contours that were skipped for
    having a zero or degenerate area -- see `_NEGLIGIBLE_CONTOUR_AREA_MM2`.
    The contours themselves travel up rather than a ready-made message, the
    same way `chain_contours` reports its duplicates by id: it is the caller
    (`prepare_parts` in pipeline.py) that knows how to fold them into its
    list of warnings, so the message is built there, once -- from `len()` of
    this very list, which is also what the diagnostic drawing marks. Un
    contador aparte podria discrepar de lo que se dibuja; esto no.
    """
    if not contours:
        return [], []

    raw_polygons = [Polygon(c.points) for c in contours]
    kept = [
        i for i, polygon in enumerate(raw_polygons)
        if polygon.area > _NEGLIGIBLE_CONTOUR_AREA_MM2
    ]
    kept_set = set(kept)
    skipped = [c for i, c in enumerate(contours) if i not in kept_set]
    if not kept:
        return [], skipped

    contours = [contours[i] for i in kept]
    polygons = [raw_polygons[i] for i in kept]
    polygons = [p if p.is_valid else p.buffer(0) for p in polygons]

    parents = _find_parents(polygons)
    depths = [_depth_of(i, parents) for i in range(len(contours))]

    # Holes are attached to the nearest enclosing contour, but only when that
    # contour is itself material (even depth). A depth-3 ring is a hole of the
    # depth-2 part, not of the depth-0 one.
    holes_by_owner: dict[int, list[int]] = {}
    for index, depth in enumerate(depths):
        if depth % 2 == 1:
            owner = parents[index]
            assert owner is not None, "an odd-depth contour always has a parent"
            _assert_hole_is_contained(index, owner, contours, polygons)
            holes_by_owner.setdefault(owner, []).append(index)

    parts: list[Part] = []
    for index, depth in enumerate(depths):
        if depth % 2 == 1:
            continue
        hole_indices = holes_by_owner.get(index, [])
        entity_ids = list(contours[index].entity_ids)
        for hole in hole_indices:
            entity_ids.extend(contours[hole].entity_ids)
        parts.append(
            Part(
                id=len(parts),
                outer=contours[index].points,
                holes=tuple(contours[h].points for h in hole_indices),
                entity_ids=tuple(entity_ids),
            )
        )
    return parts, skipped


def _assert_hole_is_contained(
    hole_index: int,
    owner_index: int,
    contours: Sequence[Contour],
    polygons: list[Polygon],
) -> None:
    """Verify that a contour accepted as a hole is genuinely inside its owner.

    `_find_parents` only checks that the hole's `representative_point()` lands
    inside the owner, which is deliberately loose: it has to tolerate holes
    that are tangent to the owner along a shared edge or at a single point.
    But that same looseness also accepts a contour that merely *overlaps* its
    owner instead of nesting inside it. Since holes are subtracted from the
    owner's area, an unnoticed partial overlap silently corrupts the material
    area downstream — so this checks the actual polygons, not just the probe.
    """
    hole_polygon = polygons[hole_index]
    owner_polygon = polygons[owner_index]
    outside = hole_polygon.difference(owner_polygon)
    if outside.is_empty:
        return

    tolerance = max(
        _RELATIVE_OVERLAP_TOLERANCE * hole_polygon.area,
        _ABSOLUTE_OVERLAP_TOLERANCE_MM2,
    )
    if outside.area <= tolerance:
        return

    problem_point = outside.representative_point()
    minx, miny, maxx, maxy = outside.bounds
    raise OverlappingContourError(
        "Dos contornos se superponen parcialmente en vez de estar uno anidado "
        "dentro del otro: el contorno con entity_ids "
        f"{list(contours[hole_index].entity_ids)} se acepta como agujero del "
        f"contorno con entity_ids {list(contours[owner_index].entity_ids)}, "
        "pero una parte de área "
        f"{outside.area:.4g} mm² queda afuera de ese exterior. Zona "
        f"conflictiva cerca de ({problem_point.x:.2f}, {problem_point.y:.2f}), "
        f"dentro del rectángulo aproximado "
        f"({minx:.2f}, {miny:.2f})-({maxx:.2f}, {maxy:.2f}). Revisá esos "
        "entity_ids en el dibujo original."
    )


def _find_parents(polygons: list[Polygon]) -> list[int | None]:
    """For each polygon, the index of the smallest polygon that encloses it."""
    tree = STRtree(polygons)
    parents: list[int | None] = [None] * len(polygons)

    for index, polygon in enumerate(polygons):
        # A representative point is guaranteed interior, which survives the
        # shared-boundary cases that make polygon-in-polygon containment fail.
        probe = polygon.representative_point()
        best: int | None = None
        best_area = float("inf")
        for candidate in tree.query(probe):
            candidate = int(candidate)
            if candidate == index:
                continue
            # A genuine ancestor must have strictly greater area: a smaller
            # polygon cannot truly enclose a bigger one. Without this guard,
            # concentric contours sharing the same centroid (and thus the same
            # `representative_point()`) can make a deeply nested ring look
            # like it "contains" an outer ring's probe too, producing a
            # parent cycle and an infinite loop in `_depth_of`.
            if polygons[candidate].area <= polygon.area:
                continue
            if not polygons[candidate].contains(probe):
                continue
            if polygons[candidate].area < best_area:
                best, best_area = candidate, polygons[candidate].area
        parents[index] = best

    return parents


def _depth_of(index: int, parents: Sequence[int | None]) -> int:
    depth = 0
    current = parents[index]
    while current is not None:
        depth += 1
        current = parents[current]
    return depth
