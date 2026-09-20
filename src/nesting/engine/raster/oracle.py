"""The real nesting engine: bitmap collision, FFT search, contact scoring.

Implements the same three-method `Oracle` protocol as the throwaway shelf
engine, so the packer, the CLI, the bench and the verifier are unchanged.
"""

import math

import numpy as np

from nesting.engine.oracle import NestConfig
from nesting.engine.raster.masks import MaskCache, PartMasks, contact_band_px
from nesting.engine.raster.scoring import best_position, contact_band
from nesting.engine.raster.search import feasible_positions
from nesting.model.part import Part


MAX_SHEET_PIXELS = 200_000_000
"""Tope de la grilla de la PLACA, distinta de la de las piezas (MAX_GRID_PIXELS
en masks.py) y con su propio presupuesto.

Sin este tope, `reset` aloca lo que le pidan. Con resolución 0.005 mm/px sobre
una placa de 1000x1000 pide 196000x196000 = 35.8 GiB. En macOS y Linux eso NO
falla: el sistema entrega memoria virtual sin respaldarla, y `np.zeros` usa
calloc, que recibe páginas en cero de forma perezosa. El programa seguía
adelante y recién más tarde chocaba con el tope de la grilla de las piezas,
que sí levanta un ValueError con mensaje claro. O sea que el mensaje bueno
salía POR CASUALIDAD, por el orden de las dos asignaciones.

En Windows no hay sobrecompromiso: la asignación falla en el acto con
`MemoryError`, que no es ninguno de los errores que `nesting_app.jobs`
clasifica como problema del usuario. Resultado: alguien que escribía una
resolución muy fina veía "se rompió el programa" con un traceback, por una
decisión enteramente suya. Lo encontró la primera corrida de los tests en
Windows.

El tope se chequea acá, donde está la asignación, así que las dos plataformas
se comportan igual y el error sale antes de reservar un solo byte.

El valor, medido sobre la placa más grande del catálogo (1830x2600, margen 10,
o sea 1810x2580 mm útiles), en píxeles de la grilla -- un byte cada uno:

    2 mm/px (el valor por omisión)      1,2 M     1 MB
    1 mm/px                             4,7 M     4 MB
    0,5 mm/px                            19 M    18 MB
    0,25 mm/px                           75 M    71 MB
    0,2 mm/px                           117 M   111 MB
    0,1 mm/px                           467 M   445 MB   <- rechazada

200 millones (unos 190 MB) deja pasar hasta 0,2 mm/px en la placa más grande
y rechaza de ahí para abajo. Para cortar madera eso ya es absurdo: la fresa
más fina del taller mide varios milímetros, así que una grilla más fina que
medio milímetro no cambia ningún corte, sólo consume memoria.
"""


class RasterOracle:
    """Collision by bitmap overlap, position search by cross-correlation."""

    def __init__(self, cache: MaskCache | None = None) -> None:
        self._cache = cache if cache is not None else MaskCache()
        self._config = NestConfig()
        self._sheet = np.zeros((0, 0), dtype=bool)
        self._frontier = 0
        """Highest row index reached by placed material, for the active region."""

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._config = config
        resolution = config.resolution

        # The grid covers ONLY the usable area, so "valid" correlation positions
        # are inside the margin by construction. No bounds code anywhere.
        usable_w = sheet_w - 2 * config.margin
        usable_h = sheet_h - 2 * config.margin
        cols = max(0, math.floor(usable_w / resolution))
        rows = max(0, math.floor(usable_h / resolution))

        if rows * cols > MAX_SHEET_PIXELS:
            raise ValueError(
                "la grilla de la placa es demasiado grande: una placa de "
                f"{sheet_w:.0f}x{sheet_h:.0f} mm a resolución {resolution} mm/px "
                f"necesita {cols}x{rows} = {rows * cols:,} píxeles "
                f"(tope: {MAX_SHEET_PIXELS:,}). "
                "Probá con una resolución más gruesa."
            )

        self._sheet = np.zeros((rows, cols), dtype=bool)
        self._frontier = 0

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        masks = self._masks(part, angle, mirror)
        height = masks.clearance.shape[0]

        result = self._search(masks, limit_rows=self._frontier + height)
        if result is None and self._frontier + height < self._sheet.shape[0]:
            result = self._search(masks, limit_rows=self._sheet.shape[0])
        if result is None:
            return None

        px, py, score = result
        dx, dy = masks.translation_for(px, py)
        return (dx + self._config.margin, dy + self._config.margin, score)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        masks = self._masks(part, angle, mirror)
        px, py = self._to_pixels(masks, x, y)
        height, width = masks.occupied.shape

        # `px`/`py` locate mask pixel [0, 0], which - now that `_search` pads
        # the sheet before correlating (see its docstring) - can legitimately
        # fall just before the sheet's own [0, 0] (up to `masks.pad` pixels
        # negative): that is the zero-padding region, never real material,
        # since `occupied` never uses those outermost `pad` pixels of its own
        # array (see `PartMasks.pad`). A plain `self._sheet[py:...]` slice
        # would silently wrap on a negative start (numpy/Python slicing
        # semantics), stamping the wrong rows/columns instead of erroring, so
        # both ends are clipped explicitly here and the source slice of
        # `occupied` is shifted to match - it stamps nothing but zeros there
        # regardless, but this keeps the two slices' shapes aligned.
        dst_row0, dst_col0 = max(py, 0), max(px, 0)
        dst_row1 = min(py + height, self._sheet.shape[0])
        dst_col1 = min(px + width, self._sheet.shape[1])
        src_row0, src_col0 = dst_row0 - py, dst_col0 - px
        src_row1 = src_row0 + max(dst_row1 - dst_row0, 0)
        src_col1 = src_col0 + max(dst_col1 - dst_col0, 0)

        self._sheet[dst_row0:dst_row1, dst_col0:dst_col1] |= (
            masks.occupied[src_row0:src_row1, src_col0:src_col1]
        )
        self._frontier = max(self._frontier, py + height)

    def _search(self, masks: PartMasks, limit_rows: int) -> tuple[int, int, float] | None:
        """Search within the first `limit_rows` rows of the sheet.

        `margin` and `sep` are different constraints: `margin` bounds the
        *material*, `sep` (via `clearance`, material dilated by the
        separation) only matters against other material already on the
        sheet. Correlating `clearance` in "valid" mode against the bare
        usable-area window would demand that the whole clearance halo -
        including the part that has nothing to collide with beyond the
        sheet's edge - land inside that area too, which double-charges the
        edge: material would need to sit `margin + sep` from the physical
        border instead of `margin`.

        The fix is to pad the window with `masks.pad` pixels of zeros on
        every side before correlating. `clearance` can then use that
        padding for its halo without it costing anything (padding is zero,
        never a collision), while `occupied` - always `masks.pad` pixels
        narrower than `clearance`'s own array on every side, by
        construction (see `PartMasks.pad`) - ends up exactly bounded by the
        real, unpadded area. A "valid" correlation of shape `(Hm, Wm)`
        against a window padded by `pad` on every side has
        `rows + 2*pad - Hm + 1 == rows - (Hm - 2*pad) + 1` output rows,
        i.e. exactly one entry per position where the material's own tight
        footprint (Hm - 2*pad rows) fits in the unpadded window - same for
        columns.

        The output index (i, j) of that padded correlation directly gives
        the position of that tight footprint in the unpadded window (see
        the task-18 report for the arithmetic), while `translation_for` and
        `place` both work in "mask [0, 0] pixel, unpadded-window frame"
        terms - `pad` pixels before that. So (i, j) is shifted by `-pad`
        before it leaves this method.
        """
        pad = masks.pad
        rows = min(max(limit_rows, masks.clearance.shape[0]), self._sheet.shape[0])
        window = self._sheet[:rows]
        padded = np.pad(window, pad, mode="constant", constant_values=False)

        feasible = feasible_positions(padded, masks.clearance)
        if feasible.size == 0:
            return None

        extra_px = contact_band_px(self._config.resolution)
        band = contact_band(masks.clearance, extra_px)
        result = best_position(feasible, padded, band, self._config.weights)
        if result is None:
            return None
        px, py, score = result
        return (px - pad, py - pad, score)

    def _masks(self, part: Part, angle: float, mirror: bool) -> PartMasks:
        return self._cache.get(
            part, angle, mirror, self._config.resolution, self._config.sep
        )

    def _to_pixels(self, masks: PartMasks, x: float, y: float) -> tuple[int, int]:
        """Inverse of `translation_for`, plus the margin offset."""
        resolution = self._config.resolution
        px = round((x - self._config.margin + masks.origin[0]) / resolution)
        py = round((y - self._config.margin + masks.origin[1]) / resolution)
        return (px, py)
