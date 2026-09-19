"""From a freshly read drawing to the parts the engine will place.

Flatten every entity, chain the loose runs into closed contours, then resolve
containment. This is where a dirty export stops being geometry soup and becomes
a list of parts - or fails loudly enough that the user can go fix the drawing.
"""

import math
from collections.abc import Sequence

from nesting.geometry.chaining import MIN_CONTOUR_POINTS, chain_contours
from nesting.geometry.flatten import flatten
from nesting.geometry.nesting_tree import build_parts
from nesting.io.dxf_reader import Drawing
from nesting.model.discard import Discard
from nesting.model.entities import Circle, Entity, Point
from nesting.model.part import Part
from nesting.tolerances import DEFAULT_CHAIN_TOL, DEFAULT_FLATTEN_TOL

__all__ = ["DEFAULT_FLATTEN_TOL", "DEFAULT_CHAIN_TOL"]


class OpenContourError(Exception):
    """A run of segments never closed, so it cannot become a part."""


def prepare_parts(
    drawing: Drawing,
    flatten_tol: float = DEFAULT_FLATTEN_TOL,
    chain_tol: float = DEFAULT_CHAIN_TOL,
) -> tuple[list[Part], list[str], list[Discard]]:
    """Turn a drawing into parts, plus any warnings and what was discarded.

    Both lists are copies of the reader's, extended with what this stage
    itself threw out -- `drawing` is left exactly as the reader produced it,
    because it stays alive afterwards (the DXF writer reads the original
    entities out of it to recover their colours).

    Every warning about something dropped is built from `len()` of the
    matching discards, so the count the user reads and the marks the
    diagnostic draws can never tell different stories.
    """
    warnings = list(drawing.warnings)
    discards = list(drawing.discards)

    segments = [
        (_flatten_closed(entity, flatten_tol), index)
        for index, entity in enumerate(drawing.entities)
    ]

    contours, open_chains, duplicate_ids = chain_contours(segments, chain_tol)

    if duplicate_ids:
        discards.extend(
            Discard(
                reason="duplicada",
                points=segments[entity_id][0],
                detail=f"entidad {entity_id}",
                closed=True,
            )
            for entity_id in duplicate_ids
        )
        warnings.append(
            f"se descartaron {len(duplicate_ids)} entidades duplicadas o superpuestas"
        )

    # Un tramo de menos de MIN_CONTOUR_POINTS puntos es una recta suelta: no
    # encierra área con ninguna tolerancia de cierre, así que no puede ser el
    # contorno de ninguna pieza. Es resto de geometría (un segmento que no se
    # conecta con nada), no una pieza incompleta, así que se descarta con
    # aviso en vez de abortar todo el trabajo por su culpa. Una cadena de
    # MIN_CONTOUR_POINTS puntos o más sí tenía forma: que no cierre significa
    # que probablemente le falte un tramo a una pieza real, y cortarla
    # incompleta arruina material, así que eso sigue siendo un error duro.
    loose_ends = [c for c in open_chains if len(c.points) < MIN_CONTOUR_POINTS]
    unclosed = [c for c in open_chains if len(c.points) >= MIN_CONTOUR_POINTS]

    if loose_ends:
        discards.extend(
            Discard(
                reason="suelta",
                points=chain.points,
                detail=f"{_chain_length(chain.points):.3f} mm",
            )
            for chain in loose_ends
        )
        warnings.append(
            f"se descartaron {len(loose_ends)} tramo(s) suelto(s) de menos de "
            f"{MIN_CONTOUR_POINTS} puntos (no encierran área, así que no pueden "
            "ser el contorno de ninguna pieza)"
        )

    if unclosed:
        worst = min(unclosed, key=lambda c: c.gap)
        raise OpenContourError(
            f"{len(unclosed)} contorno(s) no cierran. "
            f"El más cercano a cerrar arranca en "
            f"({worst.points[0][0]:.3f}, {worst.points[0][1]:.3f}) y termina en "
            f"({worst.points[-1][0]:.3f}, {worst.points[-1][1]:.3f}), "
            f"con un hueco de {worst.gap:.3f} mm. "
            f"Revise el dibujo, o afloje la tolerancia con --tol-cierre."
        )

    parts, negligible = build_parts(contours)
    if negligible:
        discards.extend(
            Discard(reason="area_nula", points=contour.points, closed=True)
            for contour in negligible
        )
        warnings.append(
            f"se descartaron {len(negligible)} contorno(s) de área nula o degenerada"
        )
    return parts, warnings, discards


def _chain_length(points: Sequence[Point]) -> float:
    """Total length of an open run, in mm.

    It is the number that tells the two kinds of loose segment apart: a run of
    millimetres is a side that came off a real piece and is worth looking at,
    while a run of microns is a repeated vertex sitting on an outline that is
    already complete. They read identically in the warning text and call for
    completely different reactions from the user.
    """
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


PLATE_OUTLINE_TOLERANCE_MM = 1.0
"""How closely a part's rectangle must match the chosen material's sheet size
to be treated as a drawn plate outline rather than a real part. Mirrors
`CANVAS_BORDER_TOLERANCE_MM` in `ai_reader.py`, which solves the same kind of
problem (a rectangle that represents the drawing surface, not a piece to cut)
for a different rectangle -- there the CorelDRAW canvas/worktable border
against the file's own `%%BoundingBox`, here the sheet a user traces in their
drawing to preview how the nesting will look. Small enough that a
legitimately part-sized rectangle merely close to the sheet size is not
discarded by mistake.
"""


def discard_plate_outline(
    parts: list[Part], sheet_w: float, sheet_h: float
) -> tuple[list[Part], list[Part]]:
    """Drop any part that IS the material sheet's own rectangle, drawn as a part.

    Users trace a `sheet_w` x `sheet_h` rectangle in their CAD tool to preview
    how the nesting will fill the plate. That rectangle is not the drawing's
    canvas/worktable border (`ai_reader` already filters that against the
    file's own `%%BoundingBox`), so it survives reading as an ordinary part --
    and being exactly the sheet size, it can never fit inside the usable area
    (the sheet minus the edge margin), so it used to blow up the whole job
    with `PartTooLargeError`.

    The match is deliberately strict, the same way `ai_reader._is_canvas_border`
    is strict about the canvas border: axis-aligned, exactly four corners, no
    holes, and its two dimensions within `PLATE_OUTLINE_TOLERANCE_MM` of the
    sheet's -- in either orientation, since the sheet can be traced lying down
    or standing up (`sheet_w` x `sheet_h` or `sheet_h` x `sheet_w`). Anything
    less strict (e.g. "reaches the sheet's bounding box") would also catch a
    real, oddly-shaped part -- an L or a triangle -- that merely spans that
    same box, or a rectangle that is genuinely meant to be cut at that size
    but happens to carry holes.

    Returns the surviving parts alongside the discarded ones, so the caller
    (`cli.py`, which is the one that knows which material was chosen) can
    build both the warning message and the diagnostic mark -- this function
    has no message-building business living in `pipeline.py` on its own, the
    same way `build_parts` and `chain_contours` hand geometry, not messages,
    back to `prepare_parts`.
    """
    kept: list[Part] = []
    discarded: list[Part] = []
    for part in parts:
        if _is_plate_outline(part, sheet_w, sheet_h):
            discarded.append(part)
        else:
            kept.append(part)
    return kept, discarded


def _is_plate_outline(part: Part, sheet_w: float, sheet_h: float) -> bool:
    if part.holes:
        return False

    points = list(part.outer)
    if len(points) != 4:
        return False

    rounded = [(round(x, 6), round(y, 6)) for x, y in points]
    xs = sorted({p[0] for p in rounded})
    ys = sorted({p[1] for p in rounded})
    if len(xs) != 2 or len(ys) != 2:
        return False
    if set(rounded) != {(x, y) for x in xs for y in ys}:
        return False

    width = xs[1] - xs[0]
    height = ys[1] - ys[0]
    tol = PLATE_OUTLINE_TOLERANCE_MM
    return (abs(width - sheet_w) <= tol and abs(height - sheet_h) <= tol) or (
        abs(width - sheet_h) <= tol and abs(height - sheet_w) <= tol
    )


def _flatten_closed(entity: Entity, tolerance: float) -> tuple[Point, ...]:
    """Flatten `entity`, closing the ring when the entity is inherently a loop.

    `flatten` deliberately leaves a `Circle`'s first point unrepeated at the
    end (see its docstring), so a lone circle would otherwise look like an
    almost-but-not-quite-closed run to `chain_contours` - open by a chord's
    width instead of by the sub-millimetre gaps that function is meant to
    tolerate. A `Circle` never needs another entity to close it, so the seam
    is stitched here, once, right where the flattened points are produced.
    """
    points = flatten(entity, tolerance)
    if isinstance(entity, Circle) and points and points[0] != points[-1]:
        points = points + (points[0],)
    return points
