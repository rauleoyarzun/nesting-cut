"""Write the finished layout, by transforming the ORIGINAL entities.

Nothing flattened ever reaches the output file: a spline stays a spline, a
circle stays a circle, and colours and layers survive because they were never
touched in the first place.
"""

from collections.abc import Sequence
from pathlib import Path

import ezdxf

from nesting.geometry.transform import apply_entity
from nesting.io.dxf_reader import SHEET_LAYER, Drawing
from nesting.model.entities import Arc, Bezier, Circle, Entity, Line, Polyline, Style, Transform
from nesting.model.part import Part, Placement

# SHEET_LAYER (the layer holding the sheet outlines, kept apart from the cut
# geometry) is re-exported here from `dxf_reader`, which is where `read_dxf`
# needs the same name to skip these outlines on the way back in -- see its
# docstring for why that round trip matters.

DEFAULT_GAP = 100.0
"""Millimetres between sheets when laid out side by side."""


class UnknownPartError(Exception):
    """A `Placement` references a `part_id` absent from the given `parts`."""


class InvalidEntityIdError(Exception):
    """A `Part` references an `entity_id` outside the drawing's entity list."""


def write_dxf(
    path: str | Path,
    drawing: Drawing,
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheet_w: float,
    sheet_h: float,
    gap: float = DEFAULT_GAP,
) -> None:
    """Write every placed part into one DXF, sheets in a horizontal row."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4  # millimetres
    msp = doc.modelspace()

    if SHEET_LAYER not in doc.layers:
        doc.layers.add(SHEET_LAYER, color=8)

    sheet_count = max((p.sheet for p in placements), default=0) + 1
    for index in range(sheet_count):
        _draw_sheet_outline(msp, index * (sheet_w + gap), sheet_w, sheet_h)

    by_id = {p.id: p for p in parts}
    for placement in placements:
        part = by_id.get(placement.part_id)
        if part is None:
            raise UnknownPartError(
                f"la colocación referencia la pieza {placement.part_id}, que no "
                f"está en la lista de piezas recibida ({len(parts)} pieza(s); "
                f"ids válidos: {sorted(by_id)})"
            )
        offset_x = placement.sheet * (sheet_w + gap)
        moved = Transform(
            angle_deg=placement.transform.angle_deg,
            mirror=placement.transform.mirror,
            dx=placement.transform.dx + offset_x,
            dy=placement.transform.dy,
        )
        placed: list[Entity] = []
        for entity_id in part.entity_ids:
            if not (0 <= entity_id < len(drawing.entities)):
                raise InvalidEntityIdError(
                    f"la pieza {part.id} referencia la entidad {entity_id}, fuera "
                    f"de rango para el dibujo de entrada ({len(drawing.entities)} "
                    f"entidad(es); rango válido 0..{len(drawing.entities) - 1})"
                )
            placed.append(apply_entity(moved, drawing.entities[entity_id]))

        for item in _bezier_runs(placed):
            _emit(msp, doc, item)

    doc.saveas(str(path))


def _draw_sheet_outline(msp, x0: float, sheet_w: float, sheet_h: float) -> None:
    msp.add_lwpolyline(
        [(x0, 0.0), (x0 + sheet_w, 0.0), (x0 + sheet_w, sheet_h), (x0, sheet_h)],
        close=True,
        dxfattribs={"layer": SHEET_LAYER},
    )


def _bezier_runs(entities: Sequence[Entity]) -> list:
    """Group each chain of `Bezier` segments that continue one another.

    The curved part of a drawing arrives as a chain of cubic segments -- the
    pieces of ONE stroke in the source file, not loose curves. Emitting one
    SPLINE per segment hands the machine a part cut into dozens of unconnected
    entities, the same breakage as a contour cut into loose lines.

    A run only forms where one segment's end IS the next one's start, compared
    exactly: both points came out of the same source point through the same
    transform, so they are bit for bit identical whenever the source really
    joined them. Anything less strict would let this MOVE a point to make the
    join, which is the one thing the writer must never do.
    """
    runs: list = []
    for entity in entities:
        if (
            isinstance(entity, Bezier)
            and runs
            and isinstance(runs[-1], list)
            and runs[-1][-1].style == entity.style
            and runs[-1][-1].p3 == entity.p0
        ):
            runs[-1].append(entity)
        elif isinstance(entity, Bezier):
            runs.append([entity])
        else:
            runs.append(entity)
    return runs


def _emit(msp, doc, e) -> None:
    if isinstance(e, list):
        _emit_bezier_path(msp, doc, e)
        return

    attribs = _attribs(e.style, doc)

    match e:
        case Line():
            msp.add_line(e.start, e.end, dxfattribs=attribs)
        case Circle():
            msp.add_circle(e.center, e.radius, dxfattribs=attribs)
        case Arc():
            msp.add_arc(e.center, e.radius, e.start_angle, e.end_angle, dxfattribs=attribs)
        case Polyline():
            msp.add_lwpolyline(e.points, close=e.closed, dxfattribs=attribs)
        case Bezier():
            _emit_bezier_path(msp, doc, [e])
        case _:
            raise TypeError(f"unsupported entity type: {type(e).__name__}")


def _emit_bezier_path(msp, doc, curves: Sequence[Bezier]) -> None:
    """Write a chain of cubic Beziers as one clamped degree-3 B-spline.

    A single cubic Bezier is exactly such a spline over `[0, 1]`; a chain of
    `n` of them is the same thing over `[0, n]`, with each joint repeated as
    an interior knot of multiplicity 3. That multiplicity is what keeps the
    curve merely continuous there instead of smoothing the corner away, so
    the joined spline passes through exactly the same points as the segments
    it replaces -- a corner in the drawing stays a corner.
    """
    control: list = [curves[0].p0, curves[0].p1, curves[0].p2, curves[0].p3]
    for curve in curves[1:]:
        control.extend([curve.p1, curve.p2, curve.p3])

    knots = [0.0] * 4
    for joint in range(1, len(curves)):
        knots.extend([float(joint)] * 3)
    knots.extend([float(len(curves))] * 4)

    spline = msp.add_spline(degree=3, dxfattribs=_attribs(curves[0].style, doc))
    spline.control_points = control
    spline.knots = knots


_BYBLOCK_OR_BYLAYER = (0, 256)
"""The two ACI codes that do not name a colour at all -- they mean "look at
the block" (0) or "look at the layer" (256). `dxf_reader._style_of` always
fills `aci` with a real int (defaulting to 256), so an entity whose colour
actually comes from its layer is indistinguishable, by `aci` alone, from one
that carries a genuine explicit colour."""


def _attribs(style: Style, doc) -> dict:
    """Rebuild the source colour and layer on the output entity.

    `style.aci` is only trustworthy as a colour when it names one directly
    (any code other than BYBLOCK/BYLAYER); `dxf_reader` always resolves
    `style.rgb` to the *effective* colour regardless of where it came from
    (the entity's own true colour, or -- for BYBLOCK/BYLAYER -- its layer's
    colour at read time). Writing that resolved `rgb` straight onto the
    entity as a true colour, rather than re-deriving it from a freshly
    created layer (which starts out colourless and would have to somehow
    end up matching), is what makes the entity render correctly no matter
    what colour ends up on the layer it landed on -- including when several
    entities that started on different source layers, with different
    colours, get deduplicated onto the same output layer name.
    """
    if style.layer not in doc.layers:
        doc.layers.add(style.layer)

    attribs: dict = {"layer": style.layer}
    if style.aci is not None and style.aci not in _BYBLOCK_OR_BYLAYER:
        attribs["color"] = style.aci
    elif style.rgb is not None:
        attribs["true_color"] = ezdxf.colors.rgb2int(style.rgb)
    return attribs
