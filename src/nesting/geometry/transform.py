"""The single definition of what a rigid transform does to geometry.

Everything that moves a part goes through here, so that the raster engine, the
verifier and the DXF writer can never disagree about what "rotated 90 degrees
and mirrored" means.
"""

import math
from collections.abc import Sequence

from nesting.model.entities import (
    Arc,
    Bezier,
    Circle,
    Entity,
    Line,
    Point,
    Polyline,
    Transform,
)


_QUARTER_TURN_TRIG: tuple[tuple[float, float], ...] = (
    (1.0, 0.0),   # 0 degrees
    (0.0, 1.0),   # 90 degrees
    (-1.0, 0.0),  # 180 degrees
    (0.0, -1.0),  # 270 degrees
)


def _cos_sin(angle_deg: float) -> tuple[float, float]:
    """cos/sin of `angle_deg`, exact for multiples of 90 degrees.

    `math.cos(math.radians(90.0))` is `6.123e-17`, not exactly 0, because pi/2
    has no exact binary floating-point representation. That noise is tiny in
    absolute terms, but it means two parts meant to share an edge after a 90
    degree rotation end up overlapping by a sliver instead of touching exactly
    -- and 90/180/270 degree rotations are the single most common case in this
    system, not an exotic corner. Short-circuit those exact multiples with a
    lookup table instead of trusting `math.cos`/`math.sin`, which removes the
    dominant source of noise for everything downstream: raster masks, the
    verifier and the DXF geometry we write out.
    """
    quarter_turns = angle_deg / 90.0
    nearest = round(quarter_turns)
    if abs(quarter_turns - nearest) < 1e-9:
        return _QUARTER_TURN_TRIG[nearest % 4]
    rad = math.radians(angle_deg)
    return math.cos(rad), math.sin(rad)


def apply_point(t: Transform, p: Point) -> Point:
    """Apply `t` to a single point: mirror, then rotate, then translate."""
    x, y = p
    if t.mirror:
        x = -x
    cos, sin = _cos_sin(t.angle_deg)
    return (x * cos - y * sin + t.dx, x * sin + y * cos + t.dy)


def apply_points(t: Transform, pts: Sequence[Point]) -> tuple[Point, ...]:
    return tuple(apply_point(t, p) for p in pts)


def componer(outer: Transform, inner: Transform) -> Transform:
    """La transformación que aplica `inner` y después `outer`.

    Es lo que hace falta para desarmar una pieza compuesta: el par se colocó
    con `outer`, y cada miembro estaba adentro del par en `inner`, así que el
    miembro termina en `componer(outer, inner)`.

    Por qué la fórmula es ésta. `apply_point` hace p -> R(a)·M·p + d, con M el
    espejo x -> -x. Encadenar las dos da

        R(A)·M_A·(R(a)·M_a·p + d_a) + d_A
      = R(A)·M_A·R(a)·M_a·p + (R(A)·M_A·d_a + d_A)

    y un espejo invierte el sentido de una rotación: M·R(a) = R(-a)·M. Así
    que el ángulo es A + a sin espejo afuera y A - a con espejo afuera, el
    espejo resultante es el "o exclusivo" de los dos, y la traslación es
    aplicar `outer` entero al punto (d_a). Verificado numéricamente en
    `tests/geometry/test_componer.py` y, antes, en el experimento de la
    spec, donde componer por las cajas en vez de por esta fórmula dejaba
    piezas superpuestas.
    """
    angle = outer.angle_deg + (-inner.angle_deg if outer.mirror else inner.angle_deg)
    dx, dy = apply_point(outer, (inner.dx, inner.dy))
    return Transform(
        angle_deg=angle % 360.0,
        mirror=outer.mirror != inner.mirror,
        dx=dx,
        dy=dy,
    )


def apply_entity(t: Transform, e: Entity) -> Entity:
    """Apply `t` to an entity, keeping its exact representation and style."""
    match e:
        case Line():
            return Line(apply_point(t, e.start), apply_point(t, e.end), e.style)

        case Circle():
            return Circle(apply_point(t, e.center), e.radius, e.style)

        case Arc():
            start, end = e.start_angle, e.end_angle
            if t.mirror:
                # Reflecting x -> -x maps angle a to 180 - a, which reverses the
                # sweep direction. DXF arcs are always counter-clockwise, so the
                # endpoints must be swapped to keep that invariant.
                start, end = 180.0 - end, 180.0 - start
            return Arc(
                center=apply_point(t, e.center),
                radius=e.radius,
                start_angle=_normalize_degrees(start + t.angle_deg),
                end_angle=_normalize_degrees(end + t.angle_deg),
                style=e.style,
            )

        case Bezier():
            return Bezier(
                apply_point(t, e.p0),
                apply_point(t, e.p1),
                apply_point(t, e.p2),
                apply_point(t, e.p3),
                e.style,
            )

        case Polyline():
            # Espejar invierte el sentido de giro, y el signo del bulge ES el
            # sentido de giro (positivo = antihorario). Rotar y trasladar no
            # lo tocan: un arco antihorario sigue siéndolo. Sin esta vuelta de
            # signo, una pieza espejada saldría con cada arco para el lado
            # contrario -- la pieza equivocada, cortada en material de verdad.
            bulges = tuple(-b for b in e.bulges) if t.mirror else e.bulges
            return Polyline(apply_points(t, e.points), e.closed, e.style, bulges)

    raise TypeError(f"unsupported entity type: {type(e).__name__}")


def _normalize_degrees(a: float) -> float:
    """Fold an angle into [0, 360)."""
    return a % 360.0
