"""Generate a synthetic stool-like DXF, so the bench has input from day one.

Shapes are deliberately curved and concave: a bounding-box engine wastes a lot
of room on them, which is exactly the gap the raster engine has to close.
"""

import math
from pathlib import Path

import ezdxf

SHEET_UNITS_MM = 4


def write_sample(path: str | Path, seats: int = 4, legs: int = 8) -> None:
    """Write a DXF with round seats and concave leg outlines."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = SHEET_UNITS_MM
    msp = doc.modelspace()

    cursor_x = 0.0
    for _ in range(seats):
        msp.add_circle((cursor_x + 150.0, 150.0), radius=150.0, dxfattribs={"color": 1})
        # Four mounting slots inside the seat: holes that free up material.
        for angle in (0, 90, 180, 270):
            rad = math.radians(angle)
            cx = cursor_x + 150.0 + 70.0 * math.cos(rad)
            cy = 150.0 + 70.0 * math.sin(rad)
            msp.add_lwpolyline(
                [(cx - 20, cy - 5), (cx + 20, cy - 5), (cx + 20, cy + 5), (cx - 20, cy + 5)],
                close=True,
                dxfattribs={"color": 3},
            )
        cursor_x += 320.0

    cursor_x = 0.0
    for _ in range(legs):
        msp.add_lwpolyline(_leg_outline(cursor_x, 400.0), close=True, dxfattribs={"color": 5})
        cursor_x += 220.0

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


def _leg_outline(x0: float, y0: float) -> list[tuple[float, float]]:
    """A concave leg: wide foot, narrow waist, wide shoulder."""
    profile = [
        (0.0, 0.0), (200.0, 0.0), (200.0, 60.0), (140.0, 90.0),
        (130.0, 300.0), (170.0, 340.0), (170.0, 420.0), (30.0, 420.0),
        (30.0, 340.0), (70.0, 300.0), (60.0, 90.0), (0.0, 60.0),
    ]
    return [(x0 + x, y0 + y) for x, y in profile]


if __name__ == "__main__":
    write_sample(Path(__file__).parent / "files" / "muestra.dxf")
    print("escrito bench/files/muestra.dxf")
