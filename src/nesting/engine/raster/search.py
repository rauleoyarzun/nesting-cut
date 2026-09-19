"""Evaluate every candidate position at once, with one cross-correlation.

Testing positions one by one is hopeless: a 1830 x 2600 sheet at 1 mm per pixel
has 4.8 million of them. A single correlation answers all of them together.
"""

import numpy as np
from scipy.signal import fftconvolve

COLLISION_THRESHOLD = 0.5
"""A real overlap is always exactly 1.0 or more; the only question is how much
FFT round-off noise can eat into that margin.

In float64, the noise stays around 1e-9 regardless of scale (measured up to
1830x2600 with a 300x300 mask, and up to 12000x16000 with a 2000x2000 mask).
That is nine orders of magnitude below this threshold, so it is safe at any
plate size this engine is likely to see.

float32 is NOT safe here: the noise grows with the array size and with how
much material is on the plate (not with the local window content), because
fftconvolve does one global FFT over the whole padded plate. Measured worst
case with a densely occupied plate: ~0.03 at 1830x2600/300x300, ~0.08-0.42 at
6000x8000/1000x1000, and at 12000x16000/2000x2000 the noise got large enough
to flip a *real* one-pixel overlap down to as low as 0.39 - below this very
threshold, i.e. a reproducible false negative (a collision reported as free).
That is why `overlap_counts` casts to float64, not float32, before calling
fftconvolve. See tests/engine/raster/test_search.py and the task-16 report
for the measurements.
"""


def overlap_counts(sheet: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """How many pixels of `mask` land on occupied material, for every position.

    The result has shape (Hs - Hm + 1, Ws - Wm + 1): one entry per position where
    the mask fits entirely inside the sheet. That means the sheet bounds are
    enforced by the array shape alone, with no explicit clamping anywhere.
    Whenever a dimension of that formula would be negative (the mask does not
    fit along that axis) it is clipped to 0 instead, independently per axis -
    so e.g. a mask that is too tall but not too wide still yields a result
    with the correct (0-height, real-width) shape rather than (0, 0).
    """
    if sheet.dtype != np.bool_ or mask.dtype != np.bool_:
        raise TypeError("sheet y mask tienen que ser arreglos booleanos")

    out_rows = sheet.shape[0] - mask.shape[0] + 1
    out_cols = sheet.shape[1] - mask.shape[1] + 1
    out_shape = (max(out_rows, 0), max(out_cols, 0))

    # fftconvolve collapses to a 1-D array when either input has a zero-sized
    # dimension, breaking the two-dimensional shape contract. Handle that (and
    # the "mask does not fit" case above) explicitly instead of letting it
    # reach fftconvolve: an empty mask, or an empty sheet, overlaps nothing.
    degenerate = (
        out_rows <= 0
        or out_cols <= 0
        or 0 in sheet.shape
        or 0 in mask.shape
    )
    if degenerate:
        return np.zeros(out_shape, dtype=float)

    # fftconvolve computes a convolution; flipping the mask on both axes turns
    # it into the correlation we actually want. float64 (not float32) keeps
    # the FFT round-off noise nine orders of magnitude below
    # COLLISION_THRESHOLD at any plate size - see the note above.
    return fftconvolve(
        sheet.astype(np.float64),
        mask[::-1, ::-1].astype(np.float64),
        mode="valid",
    )


def feasible_positions(sheet: np.ndarray, clearance: np.ndarray) -> np.ndarray:
    """True at every position where the clearance mask touches no material.

    Comparing against COLLISION_THRESHOLD works even on a degenerate,
    zero-sized `overlap_counts` result: it just produces an equally-shaped
    empty boolean array, preserving whatever 2-D shape `overlap_counts`
    returned instead of collapsing it to (0, 0).
    """
    return overlap_counts(sheet, clearance) < COLLISION_THRESHOLD
