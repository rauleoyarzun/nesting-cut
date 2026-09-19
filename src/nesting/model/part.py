"""Contours, parts and placements: what the engine moves around."""

from dataclasses import dataclass

from nesting.model.entities import Point, Transform


@dataclass(frozen=True)
class Contour:
    """A closed loop. The first point is NOT repeated at the end."""

    points: tuple[Point, ...]
    entity_ids: tuple[int, ...]
    """Indices into the drawing's entity list, so the writer can find the originals."""


@dataclass(frozen=True)
class OpenChain:
    """A run of segments that failed to close. Reported to the user as an error."""

    points: tuple[Point, ...]
    entity_ids: tuple[int, ...]
    gap: float
    """Distance between the two loose ends, in mm."""


@dataclass(frozen=True)
class Part:
    """One piece to cut: an outer outline plus the holes that travel with it."""

    id: int
    outer: tuple[Point, ...]
    holes: tuple[tuple[Point, ...], ...]
    entity_ids: tuple[int, ...]
    """Every entity that moves rigidly with this part, outer and holes alike."""

    @property
    def outer_area(self) -> float:
        return _shoelace_area(self.outer)

    @property
    def area(self) -> float:
        """Net material area: the outline minus its holes."""
        return self.outer_area - sum(_shoelace_area(h) for h in self.holes)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.outer]
        ys = [p[1] for p in self.outer]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass(frozen=True)
class Placement:
    """Where one part ended up: which sheet, and the rigid transform to get there."""

    part_id: int
    sheet: int
    transform: Transform


def _shoelace_area(ring: tuple[Point, ...]) -> float:
    """Absolute enclosed area, independent of winding direction."""
    total = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0
