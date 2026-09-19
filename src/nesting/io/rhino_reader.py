"""Read Rhino .3dm files.

Every straight piece comes through exactly, wherever it sits: a line, a
polyline, and each straight segment of a joined curve (a `PolyCurve`, which
is how Rhino stores a contour drawn as one piece). Only genuinely curved
pieces - arcs and NURBS - are sampled to a polyline at read time, because
converting general NURBS to Beziers needs knot insertion that rhino3dm does
not expose reliably. That makes .3dm the one format whose output is not
bit-exact with its input, and only along its curves; at 0.05 mm the
difference is far below anything that matters for cutting wood, but it is a
real difference and it is declared rather than hidden.

A joined curve stays one entity, as it was drawn, so the output keeps it
joined too -- see `_curve_points`.
"""

import math
from pathlib import Path

import rhino3dm

from nesting.io.dxf_reader import UNIT_SCALES, Drawing, UnknownUnitsError
from nesting.model.discard import Discard
from nesting.model.entities import Line, Point, Polyline, Style

DEFAULT_SAMPLE_TOL = 0.05
"""Chord tolerance for sampled curves, in millimetres."""

PLANARITY_TOL = 0.01
"""How much a curve's Z may vary before it is rejected as non-planar."""

MAX_SAMPLE_DEPTH = 16

# Los unicos sistemas de unidades de Rhino que este programa efectivamente
# sabe convertir -- deben coincidir con las claves de `UNIT_SCALES`.
_UNIT_NAMES = {
    rhino3dm.UnitSystem.Millimeters: "mm",
    rhino3dm.UnitSystem.Centimeters: "cm",
    rhino3dm.UnitSystem.Meters: "m",
    rhino3dm.UnitSystem.Inches: "in",
    rhino3dm.UnitSystem.Feet: "ft",
}

# Nombre en español de cada `rhino3dm.UnitSystem`, no solo los que
# `_UNIT_NAMES` soporta -- de los 27 valores que expone rhino3dm, este
# programa solo convierte 5. Se usa exclusivamente para nombrar, en el
# mensaje de `UnknownUnitsError`, una unidad declarada que no maneja --
# nunca para convertir nada. Espejo de `_INSUNITS_NAMES` en dxf_reader.py.
_UNIT_SYSTEM_NAMES: dict[int, str] = {
    0: "sin especificar", 1: "micrones", 2: "milímetros", 3: "centímetros",
    4: "metros", 5: "kilómetros", 6: "micropulgadas", 7: "mils",
    8: "pulgadas", 9: "pies", 10: "millas", 11: "unidades personalizadas",
    12: "angstroms", 13: "nanómetros", 14: "decímetros", 15: "decámetros",
    16: "hectómetros", 17: "megámetros", 18: "gigámetros", 19: "yardas",
    20: "puntos de imprenta", 21: "picas de imprenta", 22: "millas náuticas",
    23: "unidades astronómicas", 24: "años luz", 25: "parsecs",
    255: "sin especificar",
}


class NonPlanarCurveError(Exception):
    """A curve varies in Z and cannot be flattened onto the sheet.

    Carries the sampled 3D points that were rejected. The reader needs them to
    tell the user *which* curve this was: its XY shadow places it on the
    drawing and its Z range explains why it was dropped. Raising a bare
    message forced the caller to re-sample the curve to say anything useful,
    and a second sampling of the same curve can disagree with the first.
    """

    def __init__(self, message: str, points=()) -> None:
        super().__init__(message)
        self.points = tuple(points)


def read_3dm(
    path: str | Path,
    sample_tol: float = DEFAULT_SAMPLE_TOL,
    units_override: str | None = None,
) -> Drawing:
    """Read a Rhino model into a `Drawing`, normalised to millimetres.

    Raises `UnknownUnitsError` when the file's `ModelUnitSystem` is not one of
    the 5 this program can convert (see `_UNIT_NAMES`) and `units_override` is
    not given -- silently treating an unrecognised or undeclared unit system
    as millimetres would corrupt the whole sheet, exactly as it would for
    `read_dxf` (see `dxf_reader._resolve_units`).
    """
    model = rhino3dm.File3dm.Read(str(path))
    if model is None:
        raise OSError(
            f"el archivo {path} no es un .3dm válido, o está corrupto"
        )
    units = _resolve_units(model.Settings.ModelUnitSystem, units_override, path)
    scale = UNIT_SCALES[units]

    drawing = Drawing(source_units=units)
    skipped_non_curve = 0
    skipped_non_planar = 0

    for item in model.Objects:
        geometry = item.Geometry
        if not isinstance(geometry, rhino3dm.Curve):
            skipped_non_curve += 1
            # Sin puntos: una cota, un texto o un punto suelto no tienen
            # contorno en XY que marcar. Se registra igual para que el
            # diagnóstico pueda listarlo y el usuario sepa a qué corresponde
            # el aviso de texto, aunque no haya dónde señalar.
            drawing.discards.append(
                Discard(reason="no_es_curva", detail=type(geometry).__name__)
            )
            continue

        style = _style_of(model, item)
        try:
            drawing.entities.extend(_convert(geometry, scale, style, sample_tol))
        except NonPlanarCurveError as error:
            skipped_non_planar += 1
            drawing.discards.append(_non_planar_discard(error, scale))

    if skipped_non_curve:
        drawing.warnings.append(
            f"se ignoraron {skipped_non_curve} objetos que no son curvas"
        )
    if skipped_non_planar:
        drawing.warnings.append(
            f"se ignoraron {skipped_non_planar} curvas que no son planas en XY"
        )

    return drawing


def _resolve_units(
    unit_system, override: str | None, path: str | Path
) -> str:
    if override is not None:
        if override not in UNIT_SCALES:
            raise ValueError(
                f"unidad desconocida {override!r}; use una de {sorted(UNIT_SCALES)}"
            )
        return override

    name = _UNIT_NAMES.get(unit_system)
    if name is not None:
        return name

    code = int(unit_system)
    # 0 ("None") y 255 ("Unset") son los dos valores de rhino3dm.UnitSystem
    # que significan "no se declaró ninguna unidad" -- accedidos por su
    # código numérico, no por nombre, porque `None` es una palabra reservada
    # de Python y no se puede escribir `rhino3dm.UnitSystem.None`.
    if code in (0, 255):
        raise UnknownUnitsError(
            f"el archivo {path} no declara unidades (ModelUnitSystem = "
            f"{_UNIT_SYSTEM_NAMES.get(code, code)}). Indique las unidades "
            f"explícitamente con --unidades ({'|'.join(sorted(UNIT_SCALES))})."
        )
    declared = _UNIT_SYSTEM_NAMES.get(code, f"código ModelUnitSystem {code}")
    raise UnknownUnitsError(
        f"el archivo {path} declara la unidad {declared} "
        f"(ModelUnitSystem = {code}), que este programa no soporta. Indique "
        f"unas unidades soportadas explícitamente con --unidades "
        f"({'|'.join(sorted(UNIT_SCALES))})."
    )


def _convert(curve, scale: float, style: Style, tol: float) -> list:
    if isinstance(curve, rhino3dm.LineCurve):
        _require_planar([curve.PointAtStart, curve.PointAtEnd])
        start = _point(curve.PointAtStart, scale)
        end = _point(curve.PointAtEnd, scale)
        return [Line(start, end, style)]

    raw = _curve_pieces(curve, tol / scale)
    _require_planar([point for point, _ in raw])
    pieces = _drop_repeats([(_point(p, scale), bulge) for p, bulge in raw])

    # Una curva cerrada vuelve a su punto de partida, y ese punto repetido al
    # final sobra: `closed` ya lo dice, y escribirlo deja un tramo de largo
    # cero en la polilinea de salida. El bulge que queda último pasa a ser el
    # del tramo de cierre, que es exactamente lo que era.
    closed = bool(curve.IsClosed)
    if closed and len(pieces) > 2 and _same_point(pieces[0][0], pieces[-1][0]):
        pieces = pieces[:-1]

    if len(pieces) < 2:
        return []

    points = tuple(point for point, _ in pieces)
    bulges = tuple(bulge for _, bulge in pieces)
    # Sin un solo arco no se guarda nada: `()` es "todo recto", y es lo que
    # hace que un dibujo sin curvas salga byte por byte como salía antes.
    return [Polyline(points, closed, style, bulges if any(bulges) else ())]


def _curve_pieces(curve, tol: float) -> list[tuple[object, float]]:
    """Los vértices de `curve`, EXACTOS en todo tramo que sea recto o un arco.

    Devuelve pares `(vértice, bulge)`, donde el bulge es el del tramo que
    ARRANCA en ese vértice (ver `Polyline.bulges`); el último par cierra la
    lista con bulge 0, que es el que después pasa a ser el del tramo de cierre
    si la curva es cerrada.

    Una curva unida de Rhino es un `PolyCurve`: varios tramos que forman UN
    dibujo. Muestrearla entera por parámetro, como si fuera una curva
    cualquiera, ignora esa estructura y sale carísimo en los tramos rectos,
    que son la mayoría de lo que se corta: la subdivisión no cae en las
    esquinas, así que para acercarse a cada una mete una decena de nodos y
    aun así la redondea por una fracción de la tolerancia. Medido sobre un
    contorno de 6 vértices: 32 nodos, ninguna esquina exacta.

    Así que cada tramo se resuelve por lo que ES -- recta, polilínea o curva
    de verdad -- y solo lo genuinamente curvo se muestrea, cada uno en su
    propio dominio. La pieza sigue saliendo como una sola entidad: los tramos
    se concatenan, que es como estaban unidos en el archivo.
    """
    if isinstance(curve, rhino3dm.PolyCurve):
        pieces: list[tuple[object, float]] = []
        for index in range(curve.SegmentCount):
            # El vértice repetido de cada juntura lo saca `_drop_repeats`, ya
            # en milímetros, para que "el mismo punto" se decida en un solo
            # lugar y en una sola unidad.
            pieces.extend(_curve_pieces(curve.SegmentCurve(index), tol))
        return pieces

    if isinstance(curve, rhino3dm.PolylineCurve):
        return [(curve.Point(i), 0.0) for i in range(curve.PointCount)]

    if isinstance(curve, rhino3dm.LineCurve):
        return [(curve.PointAtStart, 0.0), (curve.PointAtEnd, 0.0)]

    # Grado 1 es una polilínea escrita como NURBS, que es como vienen los
    # tramos rectos de un `PolyCurve` guardado por Rhino. Con grado 1 cada
    # nudo corresponde a un punto de control, así que evaluar la curva en sus
    # nudos devuelve exactamente sus vértices -- sin tocar las coordenadas
    # homogéneas, que para una curva racional no son las del vértice.
    if isinstance(curve, rhino3dm.NurbsCurve) and curve.Degree == 1:
        return [(curve.PointAt(knot), 0.0) for knot in curve.Knots]

    bulge = _bulge_of(curve)
    if bulge is not None:
        return [(curve.PointAtStart, bulge), (curve.PointAtEnd, 0.0)]

    return [(point, 0.0) for point in _sample(curve, tol)]


def _bulge_of(curve) -> float | None:
    """El bulge de `curve` si es un arco de círculo, o None si no lo es.

    Un arco de verdad -- un filete, un redondeo -- no necesita ni un nodo
    intermedio: la polilínea del DXF lo guarda como tramo arqueado y el CNC
    lo corta con una sola orden. Poligonizarlo sería meter decenas de nodos
    para aproximar algo que se puede escribir exacto.

    El bulge es `tan(barrido / 4)`, con signo positivo antihorario, así que
    el sentido sale de hacia dónde mira la normal del plano del arco. Una
    circunferencia entera queda afuera a propósito: su barrido es una vuelta
    completa y `tan(90°)` no existe, además de que no tiene dos extremos
    distintos donde apoyar el tramo.
    """
    if curve.IsClosed or not curve.IsArc():
        return None
    arc = curve.TryGetArc()
    if arc is None:
        return None
    sweep = arc.AngleRadians
    if arc.Plane.ZAxis.Z < 0:
        sweep = -sweep
    return math.tan(sweep / 4.0)


_JOINT_TOLERANCE_MM = 1e-9
"""Cuándo dos puntos seguidos son el mismo punto: la juntura entre dos tramos
de una curva unida. Un nanómetro es ruido de punto flotante puro, muchos
órdenes por debajo de cualquier hueco real del dibujo (que tiene que llegar
al encadenado para que lo reporte, no desaparecer acá)."""


def _same_point(a: Point, b: Point) -> bool:
    return (
        abs(a[0] - b[0]) <= _JOINT_TOLERANCE_MM
        and abs(a[1] - b[1]) <= _JOINT_TOLERANCE_MM
    )


def _drop_repeats(pieces: list[tuple[Point, float]]) -> list[tuple[Point, float]]:
    """Saca los vértices repetidos consecutivos, que salen de las junturas.

    El que sobrevive se queda con el bulge del que llega: el repetido es el
    final del tramo anterior (bulge 0, no arranca nada) y el que llega es el
    arranque del siguiente, que es el que sabe si ese tramo es un arco.
    """
    kept: list[tuple[Point, float]] = []
    for point, bulge in pieces:
        if kept and _same_point(kept[-1][0], point):
            kept[-1] = (kept[-1][0], bulge)
        else:
            kept.append((point, bulge))
    return kept


def _sample(curve, tol: float) -> list:
    """Adaptive sampling: subdivide until the midpoint is within `tol` of the chord."""
    domain = curve.Domain
    points: list = [curve.PointAt(domain.T0)]
    _subdivide(curve, domain.T0, domain.T1, tol, points, depth=0)
    return points


def _subdivide(curve, t0: float, t1: float, tol: float, out: list, depth: int) -> None:
    end = curve.PointAt(t1)
    if depth >= MAX_SAMPLE_DEPTH:
        out.append(end)
        return

    start = out[-1]
    middle = (t0 + t1) / 2.0
    actual = curve.PointAt(middle)
    chord_mid = (
        (start.X + end.X) / 2.0,
        (start.Y + end.Y) / 2.0,
        (start.Z + end.Z) / 2.0,
    )

    if math.dist((actual.X, actual.Y, actual.Z), chord_mid) <= tol:
        out.append(end)
        return

    _subdivide(curve, t0, middle, tol, out, depth + 1)
    _subdivide(curve, middle, t1, tol, out, depth + 1)


def _require_planar(points) -> None:
    """Accept any constant Z; reject a curve that actually varies in Z."""
    zs = [p.Z for p in points]
    if max(zs) - min(zs) > PLANARITY_TOL:
        raise NonPlanarCurveError("la curva no es plana en XY", points)


def _non_planar_discard(error: NonPlanarCurveError, scale: float) -> Discard:
    """Turn a rejected curve into something the diagnostic can draw.

    The XY shadow is the curve with Z dropped -- which for a shape standing in
    a vertical plane collapses to a thin sliver, and that sliver is exactly
    the honest picture: that is all the footprint the sheet would ever see.
    The Z range goes in the detail text, because the sliver on its own looks
    like a stray line rather than a whole piece drawn upright.
    """
    zs = [p.Z * scale for p in error.points]
    return Discard(
        reason="no_plana",
        points=tuple(_point(p, scale) for p in error.points),
        detail=f"z va de {min(zs):.1f} a {max(zs):.1f} mm",
    )


def _style_of(model, item) -> Style:
    index = item.Attributes.LayerIndex
    try:
        if index < 0:
            raise IndexError
        layer = model.Layers[index]
        name = layer.Name or "0"
        color = layer.Color
        rgb = (int(color[0]), int(color[1]), int(color[2]))
    except (IndexError, TypeError, AttributeError):
        name, rgb = "0", (255, 255, 255)
    return Style(aci=None, rgb=rgb, layer=name)


def _point(p, scale: float) -> Point:
    return (p.X * scale, p.Y * scale)
