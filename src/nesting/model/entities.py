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

    bulges: tuple[float, ...] = ()
    """Cuánto se arquea cada tramo, en la convención del DXF.

    `bulges[i]` es el del tramo que arranca en `points[i]`, y el último es el
    del tramo de cierre (solo cuenta si `closed`). El valor es
    `tan(barrido / 4)`, positivo cuando el arco gira en sentido antihorario:
    0 es una recta, 1 es media vuelta.

    Vacío significa "todos rectos", que es el caso de la enorme mayoría de la
    geometría y el único que existía antes de que esto se agregara: por eso
    es el valor por omisión, y por eso todo lo que construye una `Polyline`
    sin nombrarlo sigue significando exactamente lo mismo que significaba.

    Un arco que llega hasta acá es un arco de verdad hasta la salida: el CNC
    lo corta con una sola orden (G2/G3) en vez de con una cadena de rectas,
    y la pieza sigue siendo UNA entidad, no un contorno partido en pedazos.
    """

    def __post_init__(self) -> None:
        if self.bulges and len(self.bulges) != len(self.points):
            raise ValueError(
                f"bulges tiene {len(self.bulges)} valor(es) para "
                f"{len(self.points)} vértice(s): tiene que haber uno por "
                "vértice (el del tramo que arranca ahí), o ninguno"
            )


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
