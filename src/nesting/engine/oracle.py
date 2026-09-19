"""The seam that makes nesting engines interchangeable.

An oracle answers one question: given a part at a given angle, and the current
state of a sheet, where can it go and how good is that spot? A raster engine
answers it with bitmaps; a No-Fit-Polygon engine would answer it with polygon
regions. Everything above this interface - ordering, rotations, multi-sheet
spilling, effort levels, reporting - never learns which one is in use.

The clearance offset is deliberately the oracle's responsibility. A raster
engine dilates masks; an NFP engine would offset polygons. Doing it outside
would tie the whole design to one of them.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from nesting.geometry.transform import apply_points
from nesting.model.entities import Transform
from nesting.model.part import Part


@dataclass(frozen=True)
class Weights:
    """How a candidate position is scored. Calibrated in Task 24."""

    bottom_left: float = 1.0
    """Pull towards the bottom-left corner, so the leftover stays in one block."""

    contact: float = 1.0
    """Reward for perimeter resting against material already placed.

    This is the term that produces interlocking between curved parts. Without
    it, bottom-left alone just stacks and leaves gaps.

    Calibrated in Task 24 (`docs/superpowers/calibracion.md`) against the
    two real reference files (`bench/files/muestra.dxf` and the Corel
    export), at `--esfuerzo rapido` with enough `--copias` to force a real
    sheet-1/sheet-2 split -- otherwise `first_sheet_utilization` is pinned to
    the raw area ratio and cannot distinguish configurations at all.

    Two things came out of that sweep, and they point in different
    directions:

    1. On raw first-sheet utilisation alone, LOWER is better: on
       `muestra.dxf` it went 63.9% (contact=0.0) -> 62.9% (1.0) -> 61.0%
       (4.0), monotonically worse as contact grows; on the Corel file, 0.0
       and 1.0 tied exactly (60.25%). `contact=0.0` is also cheaper (it
       skips the whole FFT correlation per candidate position, see
       `raster/scoring.py::best_position`): 34-46% less wall time in both
       files. Taken alone, this would argue for turning the term OFF.

    2. But `test_a_small_part_is_nested_inside_a_big_hole` (the spec 5.2
       benefit) is a real functional regression once contact drops below
       ~0.8: a bisection over the candidate set found a small part stops
       falling into a large part's hole for contact in {0.0, 0.5} and
       starts working again at {0.8, 0.9, 0.95, 1.0, 2.0, 4.0}. Below that
       threshold bottom-left alone wins the position argmax and the small
       part sits at the sheet's bottom-left instead of inside the hole --
       geometrically valid, but wasting exactly the space `docs/.../hito 3`
       promises to reclaim. That capability matters more than a couple of
       points of aggregate utilisation, so any candidate under 1.0 is
       disqualified regardless of what the first metric says.

    `1.0` is the smallest candidate that clears the hole-nesting floor, and
    among the candidates that clear it (1.0, 2.0, 4.0) it is also the best
    on first-sheet utilisation (62.9% vs 61.0% at 4.0; 2.0 was not measured
    on the real files but the monotonic trend from 1.0 to 4.0 gives no
    reason to expect it beats 1.0). So the calibration keeps the original
    provisional value, now for a measured reason instead of a guessed one.
    """

    def __post_init__(self) -> None:
        if self.bottom_left < 0:
            raise ValueError(
                f"bottom_left tiene que ser mayor o igual a cero, "
                f"recibido {self.bottom_left!r}"
            )
        if self.contact < 0:
            raise ValueError(
                f"contact tiene que ser mayor o igual a cero, "
                f"recibido {self.contact!r}"
            )


@dataclass(frozen=True)
class NestConfig:
    sep: float = 5.0
    """Minimum gap between parts, in mm."""

    margin: float = 10.0
    """Minimum gap between a part and the sheet edge, in mm."""

    angles: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)
    mirror: bool = True
    resolution: float = 2.0
    """Raster resolution in mm per pixel. Ignored by non-raster oracles.

    Rasterizing conservatively (see `raster/masks.py`) inflates every part's
    effective area, and the cost is proportional to perimeter over area, so a
    finer resolution buys density at the price of time. Task 24
    (`docs/superpowers/calibracion.md`) swept `--resolucion` on the same two
    real files used for `Weights.contact` (same `--copias`, forcing a real
    sheet-1/sheet-2 split so `first_sheet_utilization` is actually
    sensitive): 1.0 -> 2.0 mm/px cost NOTHING on `muestra.dxf` (identical
    62.9% first-sheet utilisation) and 0.76 points on the real Corel export
    (60.25% -> 59.49%), for a 4.5-4.8x speedup in both. 1.0 -> 3.0 loses
    more (2.9 points on `muestra.dxf`) for a bigger, likely unnecessary,
    speedup. 1.0 -> 0.5 was measured for time only (a full utilisation sweep
    at 0.5 was outside this session's budget): ~4.9x SLOWER, consistent with
    the finer grid having ~4x the cells per axis. The exact verifier
    (`geometry/verify.py`) found zero violations at any of these -- coarser
    rasterizing costs density, never correctness, since separation is
    checked on the exact polygons regardless of the grid used to place them.
    2.0 is the calibrated default: a real, close-to-free win on one
    reference and a small, clearly-worth-it trade on the other. It also
    leaves the `EFFORT_RESTARTS` timings (calibrated at 1.0 mm/px, see
    `packer.py`) as a safe upper bound rather than a tight one -- every
    level now runs faster than what was measured there, never slower.
    """

    effort: str = "normal"
    """One of "rapido", "normal", "lento"."""

    seed: int = 0
    weights: Weights = field(default_factory=Weights)


@runtime_checkable
class Oracle(Protocol):
    """Where can this part go on this sheet, and how good is that spot?"""

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        """Start a fresh, empty sheet."""
        ...

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        """Best (dx, dy, score) for this orientation, or None if it does not fit.

        Higher scores are better. Must NOT mutate state: the packer asks about
        several orientations before committing to one.
        """
        ...

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        """Commit a placement at exactly (x, y), so later queries see it occupied.

        An implementation MUST honour the (x, y) it is given rather than deriving
        a position of its own. If it cannot represent an arbitrary position - a
        shelf packer only tracks a cursor - it MUST validate the argument against
        the position it would have produced and raise `ValueError` on a mismatch.
        Silently committing a different position than the caller asked for
        desynchronises the oracle's state from the layout being built, and the
        parts placed afterwards overlap with no error anywhere.

        Precondition: (x, y) comes from a `best_placement` call for this same
        (part, angle, mirror), with no intervening `place`.
        """
        ...


def transformed_bbox(
    part: Part, angle: float, mirror: bool
) -> tuple[float, float, float, float]:
    """Bounding box of `part` at this orientation, before any translation."""
    points = apply_points(Transform(angle, mirror, 0.0, 0.0), part.outer)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))
