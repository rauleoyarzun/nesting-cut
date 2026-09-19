"""Geometric primitives shared by every reader, the engine and the writer.

Only primitives that are *exact* under a rigid transform live here. Readers
convert ELLIPSE and SPLINE entities into chains of cubic `Bezier` segments.
"""

from dataclasses import dataclass

Point = tuple[float, float]


@dataclass(frozen=True)
class Style:
    """Source colour and layer, carried through untouched to the output."""

    aci: int | None
    """AutoCAD Color Index (1-255, 256 = BYLAYER). None when the source had no ACI."""

    rgb: tuple[int, int, int] | None
    """True colour. None when the source only specified an ACI."""

    layer: str


@dataclass(frozen=True)
class Line:
    start: Point
    end: Point
    style: Style


@dataclass(frozen=True)
class Arc:
    """Circular arc, swept counter-clockwise from `start_angle` to `end_angle`."""

    center: Point
    radius: float
    start_angle: float
    """Degrees, counter-clockwise from +X."""

    end_angle: float
    """Degrees, counter-clockwise from +X."""

    style: Style


@dataclass(frozen=True)
class Circle:
    center: Point
    radius: float
    style: Style


@dataclass(frozen=True)
class Bezier:
    """Cubic Bezier segment."""

    p0: Point
    p1: Point
    p2: Point
    p3: Point
    style: Style


@dataclass(frozen=True)
class Polyline:
    points: tuple[Point, ...]
    closed: bool
    style: Style


Entity = Line | Arc | Circle | Bezier | Polyline


@dataclass(frozen=True)
class Transform:
    """A rigid transform, applied in this order: mirror, rotate, translate.

    `mirror` reflects across the Y axis (x -> -x). Any reflection about any
    axis can be written as this reflection followed by a rotation, so a single
    boolean is enough.
    """

    angle_deg: float
    mirror: bool
    dx: float
    dy: float

    @staticmethod
    def identity() -> "Transform":
        return Transform(angle_deg=0.0, mirror=False, dx=0.0, dy=0.0)
