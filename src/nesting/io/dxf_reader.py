"""DXF -> the internal entity model, normalised to millimetres.

This is the canonical reader: `.ai` and `.3dm` are extra importers that produce
the same `Drawing`. Units are converted exactly once, here, so nothing below
`io/` ever needs to know about anything but millimetres.
"""

from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf import path as ezdxf_path
from ezdxf.entities import DXFEntity
from ezdxf.layouts import Modelspace

from nesting.model.discard import Discard
from nesting.model.entities import Arc, Bezier, Circle, Entity, Line, Point, Polyline, Style

UNIT_SCALES: dict[str, float] = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "ft": 304.8,
}

SHEET_LAYER = "_PLACA"
"""Reserved layer `dxf_writer.write_dxf` draws its sheet-outline rectangles on.

Feeding a file this tool wrote back into itself is a real workflow (checking
the result, or nesting it further alongside new parts), so entities on this
layer are skipped here rather than read as cuttable geometry: the layout's own
sheet-boundary rectangle would otherwise fully enclose every placed part and
`build_parts` would fold all of them into holes of one giant "part", instead
of the individual parts they actually are.
"""

# ezdxf's $INSUNITS codes we accept. 0 means "unspecified" and is deliberately
# absent: an unlabelled file must fail, not fall back to a guess.
_INSUNITS_TO_NAME: dict[int, str] = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}

SKIPPED_TYPES = frozenset(
    {
        "TEXT", "MTEXT", "DIMENSION", "HATCH", "POINT", "SOLID", "LEADER",
        "MLEADER", "ATTDEF", "ATTRIB", "IMAGE", "WIPEOUT", "MESH", "3DFACE",
    }
)

_FULL_SWEEP_TOLERANCE_DEG = 1e-9


class UnknownUnitsError(Exception):
    """The file's units cannot be used, for one of two different reasons:
    either it declares none at all ($INSUNITS == 0), or it declares a valid
    DXF unit ($INSUNITS != 0) that this program does not support (e.g. miles,
    microns, decimetres) -- see `_resolve_units`, which tells the two apart in
    its message rather than reporting every case as "no units declared"."""


_INSUNITS_NAMES: dict[int, str] = {
    1: "pulgadas", 2: "pies", 3: "millas", 4: "milímetros", 5: "centímetros",
    6: "metros", 7: "kilómetros", 8: "micropulgadas", 9: "mils", 10: "yardas",
    11: "angstroms", 12: "nanómetros", 13: "micrones", 14: "decímetros",
    15: "decámetros", 16: "hectómetros", 17: "gigámetros",
    18: "unidades astronómicas", 19: "años luz", 20: "parsecs",
    21: "pies de agrimensor (EE. UU.)", 22: "pulgadas de agrimensor (EE. UU.)",
    23: "yardas de agrimensor (EE. UU.)", 24: "millas de agrimensor (EE. UU.)",
}
"""Nombre en español de cada código `$INSUNITS` que define el formato DXF,
no solo los que `UNIT_SCALES` soporta. Se usa exclusivamente para nombrar,
en el mensaje de `UnknownUnitsError`, una unidad declarada que este programa
todavía no maneja -- nunca para convertir nada."""


@dataclass
class Drawing:
    """Everything a reader produces, already normalised to millimetres."""

    entities: list[Entity] = field(default_factory=list)
    source_units: str = "mm"
    warnings: list[str] = field(default_factory=list)
    discards: list[Discard] = field(default_factory=list)
    """Lo que el lector decidió no convertir, con geometría cuando la tiene.

    Paralelo a `warnings`, pero dibujable: cada aviso de "se ignoraron N ..."
    se arma con `len()` sobre el tramo correspondiente de esta lista, así que
    el número del mensaje y las marcas del diagnóstico salen del mismo hecho.
    """


def read_dxf(path: str | Path, units_override: str | None = None) -> Drawing:
    """Read `path` into a `Drawing`, scaling every coordinate to millimetres.

    Raises `UnknownUnitsError` when the file has no declared units ($INSUNITS
    == 0) and `units_override` is not given: a wrong guess ruins an entire
    sheet, so failing loudly is cheaper than inferring.
    """
    doc = ezdxf.readfile(str(path))
    units = _resolve_units(doc.units, units_override, path)
    scale = UNIT_SCALES[units]

    drawing = Drawing(source_units=units)
    skipped: dict[str, int] = {}

    sheet_outlines_skipped = 0
    for entity in _flatten_inserts(doc.modelspace()):
        kind = entity.dxftype()
        if entity.dxf.get("layer", "0") == SHEET_LAYER:
            sheet_outlines_skipped += 1
            drawing.discards.append(Discard(reason="capa_placa", detail=kind))
            continue
        if kind in SKIPPED_TYPES:
            skipped[kind] = skipped.get(kind, 0) + 1
            drawing.discards.append(Discard(reason="tipo_no_soportado", detail=kind))
            continue
        converted = _convert(entity, scale, doc)
        if converted is None:
            skipped[kind] = skipped.get(kind, 0) + 1
            drawing.discards.append(Discard(reason="tipo_no_soportado", detail=kind))
            continue
        drawing.entities.extend(converted)

    for kind, count in sorted(skipped.items()):
        drawing.warnings.append(
            f"se ignoraron {count} entidades de tipo {kind} (no participan del nesting)"
        )

    if sheet_outlines_skipped:
        drawing.warnings.append(
            f"se ignoraron {sheet_outlines_skipped} entidades en la capa {SHEET_LAYER!r}: "
            f"esta capa está reservada por esta herramienta para los contornos de la placa, "
            f"por eso no se trata su contenido como geometría de corte. Si esa geometría es "
            f"suya, muévala a otra capa."
        )

    return drawing


def _resolve_units(insunits: int, override: str | None, path: str | Path) -> str:
    if override is not None:
        if override not in UNIT_SCALES:
            raise ValueError(
                f"unidad desconocida {override!r}; use una de {sorted(UNIT_SCALES)}"
            )
        return override
    name = _INSUNITS_TO_NAME.get(insunits)
    if name is not None:
        return name
    if insunits == 0:
        raise UnknownUnitsError(
            f"el archivo {path} no declara unidades ($INSUNITS = 0). "
            f"Indique las unidades explícitamente con --unidades "
            f"({'|'.join(sorted(UNIT_SCALES))})."
        )
    declared = _INSUNITS_NAMES.get(insunits, f"código $INSUNITS {insunits}")
    raise UnknownUnitsError(
        f"el archivo {path} declara la unidad {declared} ($INSUNITS = {insunits}), "
        f"que este programa no soporta. Indique unas unidades soportadas "
        f"explícitamente con --unidades ({'|'.join(sorted(UNIT_SCALES))})."
    )


def _flatten_inserts(msp: Modelspace):
    """Yield every entity, expanding block references recursively."""
    stack = list(msp)
    while stack:
        entity = stack.pop()
        if entity.dxftype() == "INSERT":
            stack.extend(entity.virtual_entities())
        else:
            yield entity


def _convert(entity: DXFEntity, scale: float, doc) -> list[Entity] | None:
    """Convert one DXF entity, or return None when the type is not supported."""
    style = _style_of(entity, doc)
    kind = entity.dxftype()

    if kind == "LINE":
        return [Line(_pt(entity.dxf.start, scale), _pt(entity.dxf.end, scale), style)]

    if kind == "CIRCLE":
        return [Circle(_pt(entity.dxf.center, scale), entity.dxf.radius * scale, style)]

    if kind == "ARC":
        start_angle = entity.dxf.start_angle
        end_angle = entity.dxf.end_angle
        if _is_full_sweep(start_angle, end_angle):
            # A 360-degree ARC is a full circle. Mapping it to `Arc` would let
            # the rigid transform's angle normalisation collapse it to
            # start == end and write a degenerate arc to the output, so the
            # correct fix is here, at the source.
            return [Circle(_pt(entity.dxf.center, scale), entity.dxf.radius * scale, style)]
        return [
            Arc(
                center=_pt(entity.dxf.center, scale),
                radius=entity.dxf.radius * scale,
                start_angle=start_angle,
                end_angle=end_angle,
                style=style,
            )
        ]

    if kind in ("LWPOLYLINE", "POLYLINE"):
        if not _has_bulges(entity):
            if kind == "LWPOLYLINE":
                points = tuple((x * scale, y * scale) for x, y in entity.get_points("xy"))
            else:
                points = tuple(
                    (v.dxf.location.x * scale, v.dxf.location.y * scale)
                    for v in entity.vertices
                )
            return [Polyline(points, bool(entity.is_closed), style)]
        return _from_path(entity, scale, style)

    if kind in ("SPLINE", "ELLIPSE"):
        return _from_path(entity, scale, style)

    return None


def _is_full_sweep(start_angle: float, end_angle: float) -> bool:
    """True when an ARC's sweep covers the whole 360 degrees.

    Covers both `start == end` and the explicit `0 -> 360` form (and any
    other pair a full turn apart).
    """
    sweep = (end_angle - start_angle) % 360.0
    return sweep < _FULL_SWEEP_TOLERANCE_DEG or sweep > 360.0 - _FULL_SWEEP_TOLERANCE_DEG


def _has_bulges(entity: DXFEntity) -> bool:
    try:
        if entity.dxftype() == "LWPOLYLINE":
            return any(abs(p[4]) > 1e-12 for p in entity.get_points("xyseb"))
        return any(abs(v.dxf.bulge) > 1e-12 for v in entity.vertices)
    except (AttributeError, IndexError):
        return False


def _from_path(entity: DXFEntity, scale: float, style: Style) -> list[Entity]:
    """Convert any curve entity through ezdxf's Path into lines and cubic Beziers."""
    source = ezdxf_path.make_path(entity)
    out: list[Entity] = []
    current = _pt(source.start, scale)

    for command in source.commands():
        end = _pt(command.end, scale)
        name = type(command).__name__
        if name == "LineTo":
            out.append(Line(current, end, style))
        elif name == "Curve3To":
            control = _pt(command.ctrl, scale)
            # Degree elevation: a quadratic Bezier expressed as an equivalent
            # cubic one, so every curve in the model is a cubic `Bezier`.
            c1 = (
                current[0] + 2 / 3 * (control[0] - current[0]),
                current[1] + 2 / 3 * (control[1] - current[1]),
            )
            c2 = (
                end[0] + 2 / 3 * (control[0] - end[0]),
                end[1] + 2 / 3 * (control[1] - end[1]),
            )
            out.append(Bezier(current, c1, c2, end, style))
        elif name == "Curve4To":
            out.append(
                Bezier(current, _pt(command.ctrl1, scale), _pt(command.ctrl2, scale), end, style)
            )
        else:  # MoveTo, for multi-part paths
            current = end
            continue
        current = end

    return out


def _style_of(entity: DXFEntity, doc) -> Style:
    """Capture colour and layer exactly as the source had them."""
    aci = entity.dxf.get("color", 256)
    layer = entity.dxf.get("layer", "0")

    rgb: tuple[int, int, int] | None = getattr(entity, "rgb", None)
    if rgb is None:
        resolved = aci
        if resolved in (0, 256):  # BYBLOCK / BYLAYER
            try:
                resolved = doc.layers.get(layer).color
            except Exception:
                resolved = 7
        try:
            rgb = ezdxf.colors.aci2rgb(abs(resolved) if resolved else 7)
        except Exception:
            rgb = (255, 255, 255)

    return Style(aci=aci, rgb=tuple(rgb), layer=layer)


def _pt(v, scale: float) -> Point:
    return (float(v[0]) * scale, float(v[1]) * scale)
