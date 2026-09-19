"""Choose among the feasible positions.

Fitting is not enough. Bottom-left alone stacks parts and leaves gaps; the
contact term is what makes curved parts interlock, one leg settling into the
curve of the next.
"""

import numpy as np
from scipy.ndimage import binary_dilation

from nesting.engine.oracle import Weights
from nesting.engine.raster.masks import disk_kernel
from nesting.engine.raster.search import overlap_counts


def contact_band(clearance: np.ndarray, extra_px: int) -> np.ndarray:
    """The ring just outside the clearance halo.

    Where this ring overlaps material already placed, the part is nestled
    against it rather than merely not colliding with it.
    """
    if extra_px <= 0:
        return np.zeros_like(clearance)
    grown = binary_dilation(clearance, structure=disk_kernel(extra_px))
    return grown & ~clearance


def best_position(
    feasible: np.ndarray,
    sheet: np.ndarray,
    band: np.ndarray,
    weights: Weights,
) -> tuple[int, int, float] | None:
    """Pick the best feasible position. Returns (column, row, score), or None."""
    if feasible.size == 0 or not feasible.any():
        return None

    rows, cols = feasible.shape
    row_index, col_index = np.indices((rows, cols))
    # A fixed COLUMN_TIE_BREAK constant breaks down as soon as the plate is
    # wider than its inverse: with 0.001, that is any width past 1000 columns,
    # and a real plate is 1830 or 2600 columns at 1 mm/px (more at finer
    # resolutions). Past that point the column term can add up to more than
    # one full row, so a position further right in a lower row can outscore
    # one in a higher row - bottom-left stops being bottom-left. The width is
    # exactly the thing that varies, so no single constant is safe; instead
    # normalise the column term by the width itself, so it always lives in
    # [0, 1) - strictly less than one row - no matter how wide the plate is.
    raw = row_index + col_index / (cols + 1)
    span = rows + 1
    bottom_left = 1.0 - raw / span

    score = weights.bottom_left * bottom_left

    # With an empty sheet contact is zero everywhere, so the second correlation
    # would be pure cost. The opening placements of every sheet take this path.
    if weights.contact != 0.0 and sheet.any() and band.any():
        counts = overlap_counts(sheet, band)
        if counts.shape != feasible.shape:
            raise ValueError(
                f"la banda de contacto {counts.shape} y las posiciones "
                f"factibles {feasible.shape} tienen formas distintas: "
                "tienen que construirse a partir de la misma máscara"
            )
        score = score + weights.contact * (counts / band.sum())

    score = np.where(feasible, score, -np.inf)
    flat = int(np.argmax(score))
    row, col = divmod(flat, cols)
    return (col, row, float(score[row, col]))
