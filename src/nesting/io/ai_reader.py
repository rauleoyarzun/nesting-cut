"""Read the AI3 (PostScript) files CorelDRAW exports.

Despite the .ai extension these are plain text, so no dependency is needed.
Only the body between %%EndSetup and %%Trailer is parsed: the prologue is full
of PostScript procedure definitions whose tokens a naive parser would happily
mistake for geometry.
"""

import re
from pathlib import Path

from nesting.io.dxf_reader import Drawing
from nesting.model.discard import Discard
from nesting.model.entities import Bezier, Line, Point, Polyline, Style

PT_TO_MM = 25.4 / 72.0

BODY_START = "%%EndSetup"
BODY_END = "%%Trailer"

CLOSING_PAINT_OPS = frozenset({"s", "f", "b", "n"})
"""Lowercase paint operators close the current subpath before painting."""

OPEN_PAINT_OPS = frozenset({"S", "F", "B", "N"})

_BBOX_RE = re.compile(
    r"^%%BoundingBox:\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)",
    re.MULTILINE,
)
"""Matches the DSC `%%BoundingBox:` comment, not `%%HiResBoundingBox:`
(the `^` anchor requires the line to start with the shorter name)."""

CANVAS_BORDER_TOLERANCE_MM = 1.0
"""How closely a closed rectangular contour must hug the declared
%%BoundingBox to be treated as CorelDRAW's canvas/worktable border rather
than a real part. Small enough that a legitimately part-sized rectangle
close to, but not exactly, the canvas size is not discarded by mistake.
"""

_POINT_TOLERANCE_MM = 1e-6


def cmyk_to_rgb(c: float, m: float, y: float, k: float) -> tuple[int, int, int]:
    return (
        round(255 * (1 - min(1.0, c)) * (1 - min(1.0, k))),
        round(255 * (1 - min(1.0, m)) * (1 - min(1.0, k))),
        round(255 * (1 - min(1.0, y)) * (1 - min(1.0, k))),
    )


def read_ai(path: str | Path) -> Drawing:
    """Read an AI3 file into a `Drawing`, converting points to millimetres."""
    text = Path(path).read_text(encoding="latin-1", errors="replace")
    bbox_mm = _bbox_from_header(text)
    return _parse_body(_extract_body(text), bbox_mm)


def _bbox_from_header(text: str) -> tuple[float, float, float, float] | None:
    """Read the DSC `%%BoundingBox: llx lly urx ury`, in millimetres.

    That comment lives in the PostScript prologue, before %%EndSetup, which
    `_extract_body` deliberately skips when parsing geometry. So the header
    is read from the raw text here, separately, before that skip happens.
    Returns None when the file declares no bounding box (missing, or
    "atend").
    """
    match = _BBOX_RE.search(text)
    if not match:
        return None
    llx, lly, urx, ury = (float(g) for g in match.groups())
    return (llx * PT_TO_MM, lly * PT_TO_MM, urx * PT_TO_MM, ury * PT_TO_MM)


def _extract_body(text: str) -> str:
    start = text.find(BODY_START)
    body = text[start + len(BODY_START):] if start >= 0 else text
    end = body.find(BODY_END)
    return body[:end] if end >= 0 else body


def _is_canvas_border(
    corners: list[Point], bbox_mm: tuple[float, float, float, float]
) -> bool:
    """Is `corners` (a closed contour's vertices, in drawing order) exactly
    the axis-aligned rectangle described by `bbox_mm`?

    Deliberately strict: touching, or even spanning, the bounding box is not
    enough - the largest real part in almost any file touches its bounding
    box by definition, so that alone would discard legitimate geometry. The
    contour has to *be* the rectangle: exactly four corners, axis-aligned,
    with all four sides within `CANVAS_BORDER_TOLERANCE_MM` of the declared
    box.
    """
    points = list(corners)
    if len(points) > 1 and _same_point(points[0], points[-1]):
        points = points[:-1]
    if len(points) != 4:
        return False

    rounded = [(round(x, 6), round(y, 6)) for x, y in points]
    xs = sorted({p[0] for p in rounded})
    ys = sorted({p[1] for p in rounded})
    if len(xs) != 2 or len(ys) != 2:
        return False
    if set(rounded) != {(x, y) for x in xs for y in ys}:
        return False

    llx, lly, urx, ury = bbox_mm
    tol = CANVAS_BORDER_TOLERANCE_MM
    return (
        abs(xs[0] - llx) <= tol
        and abs(xs[1] - urx) <= tol
        and abs(ys[0] - lly) <= tol
        and abs(ys[1] - ury) <= tol
    )


def _same_point(a: Point, b: Point) -> bool:
    return abs(a[0] - b[0]) < _POINT_TOLERANCE_MM and abs(a[1] - b[1]) < _POINT_TOLERANCE_MM


def _parse_body(body: str, bbox_mm: tuple[float, float, float, float] | None) -> Drawing:
    drawing = Drawing(source_units="pt")
    operands: list[float] = []

    rgb: tuple[int, int, int] = (0, 0, 0)
    current: Point | None = None
    subpath_start: Point | None = None
    pending: list[tuple[str, tuple]] = []
    corner_points: list[Point] = []
    has_curve = False

    def style() -> Style:
        return Style(aci=None, rgb=rgb, layer=f"AI_{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")

    def flush(close: bool) -> None:
        nonlocal pending, current, subpath_start, corner_points, has_curve
        discard = False
        if close and not has_curve and bbox_mm is not None:
            closing_corners = list(corner_points)
            if (
                current is not None
                and subpath_start is not None
                and current != subpath_start
            ):
                closing_corners.append(subpath_start)
            discard = _is_canvas_border(closing_corners, bbox_mm)

        if discard:
            width = bbox_mm[2] - bbox_mm[0]
            height = bbox_mm[3] - bbox_mm[1]
            drawing.discards.append(
                Discard(
                    reason="borde_lienzo",
                    points=(
                        (bbox_mm[0], bbox_mm[1]), (bbox_mm[2], bbox_mm[1]),
                        (bbox_mm[2], bbox_mm[3]), (bbox_mm[0], bbox_mm[3]),
                    ),
                    detail=f"{width:.1f} x {height:.1f} mm",
                    closed=True,
                )
            )
            drawing.warnings.append(
                f"se ignoró un rectángulo de {width:.1f} x {height:.1f} mm que "
                "coincide con el borde del lienzo declarado en la cabecera "
                "(%%BoundingBox); si era una pieza de verdad, hay que sacarla "
                "de esa posición"
            )
        else:
            ops = list(pending)
            if (
                close
                and current is not None
                and subpath_start is not None
                and current != subpath_start
            ):
                ops.append(("line", (current, subpath_start)))
            drawing.entities.extend(_entities_of_subpath(ops, close, style()))
        pending = []
        current = None
        subpath_start = None
        corner_points = []
        has_curve = False

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue

        for token in stripped.split():
            number = _as_float(token)
            if number is not None:
                operands.append(number)
                continue

            op = token

            if op == "m" and len(operands) >= 2:
                if pending:
                    flush(close=False)
                current = _pt(operands[-2], operands[-1])
                subpath_start = current
                corner_points = [current]
                has_curve = False

            elif op in ("l", "L") and len(operands) >= 2 and current is not None:
                nxt = _pt(operands[-2], operands[-1])
                pending.append(("line", (current, nxt)))
                current = nxt
                corner_points.append(nxt)

            elif op in ("c", "C") and len(operands) >= 6 and current is not None:
                c1 = _pt(operands[-6], operands[-5])
                c2 = _pt(operands[-4], operands[-3])
                end = _pt(operands[-2], operands[-1])
                pending.append(("bezier", (current, c1, c2, end)))
                current = end
                has_curve = True

            elif op in ("v", "V") and len(operands) >= 4 and current is not None:
                c2 = _pt(operands[-4], operands[-3])
                end = _pt(operands[-2], operands[-1])
                pending.append(("bezier", (current, current, c2, end)))
                current = end
                has_curve = True

            elif op in ("y", "Y") and len(operands) >= 4 and current is not None:
                c1 = _pt(operands[-4], operands[-3])
                end = _pt(operands[-2], operands[-1])
                pending.append(("bezier", (current, c1, end, end)))
                current = end
                has_curve = True

            elif op in CLOSING_PAINT_OPS:
                flush(close=True)

            elif op in OPEN_PAINT_OPS:
                flush(close=False)

            elif op in ("K", "k") and len(operands) >= 4:
                rgb = cmyk_to_rgb(*operands[-4:])

            elif op in ("G", "g") and len(operands) >= 1:
                level = round(255 * min(1.0, max(0.0, operands[-1])))
                rgb = (level, level, level)

            operands = []

    flush(close=False)
    return drawing


def _entities_of_subpath(
    ops: list[tuple[str, tuple]], close: bool, style: Style
) -> list:
    """Turn one drawn subpath into as few entities as it can be written with.

    A subpath in the file is a single stroke: its segments are joined there,
    and they have to stay joined all the way to the output, because the DXF
    writer emits one entity per entity read. One `Line` per `l` operator used
    to turn a four-sided part into four loose LINEs in the output -- geometry
    a CAM tool sees as four separate cuts, and a drawing program as eight
    anchor points where the original had four.

    So every maximal run of straight segments collapses into ONE `Polyline`
    over the very same vertices (no node added, none moved), closed when the
    paint operator closed the subpath. A `Bezier` cannot be folded into a
    polyline without flattening it -- which is exactly the node inflation
    this is here to avoid -- and no DXF entity holds straight and curved
    pieces at once, so a subpath mixing both comes out as the few entities
    those runs need, still end to end.
    """
    runs: list[tuple[str, list]] = []
    for kind, payload in ops:
        if kind == "line":
            if runs and runs[-1][0] == "line":
                runs[-1][1].append(payload[1])
            else:
                runs.append(("line", [payload[0], payload[1]]))
        else:
            runs.append(("bezier", list(payload)))

    if close and len(runs) == 1 and runs[0][0] == "line":
        points = runs[0][1]
        if len(points) > 1 and _same_point(points[0], points[-1]):
            points = points[:-1]
        return [Polyline(tuple(points), True, style)]

    entities: list = []
    for kind, payload in runs:
        if kind == "bezier":
            entities.append(Bezier(*payload, style))
        elif len(payload) == 2:
            entities.append(Line(payload[0], payload[1], style))
        else:
            entities.append(Polyline(tuple(payload), False, style))
    return entities


def _pt(x: float, y: float) -> Point:
    return (x * PT_TO_MM, y * PT_TO_MM)


def _as_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None
