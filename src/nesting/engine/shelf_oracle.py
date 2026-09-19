"""A deliberately poor nesting engine: bounding-box shelf packing.

Parts accumulate along a horizontal shelf until one no longer fits, then a new
shelf opens above. Every curve is reduced to its rectangle, so all the space
between an outline and its bounding box is wasted.

It exists so the whole pipeline can run end to end before the real engine is
written, and so the improvement from the raster engine is measurable against a
baseline rather than asserted.
"""

from nesting.engine.oracle import NestConfig, transformed_bbox
from nesting.model.part import Part

PLACE_TOLERANCE = 1e-6
"""Millimetres of slack when matching a committed position against the free slot."""


class ShelfOracle:
    """Implements the `Oracle` protocol by packing bounding boxes into rows."""

    def __init__(self) -> None:
        self._sheet_w = 0.0
        self._sheet_h = 0.0
        self._config = NestConfig()
        self._cursor_x = 0.0
        self._shelf_y = 0.0
        self._shelf_height = 0.0

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._sheet_w = sheet_w
        self._sheet_h = sheet_h
        self._config = config
        self._cursor_x = config.margin
        self._shelf_y = config.margin
        self._shelf_height = 0.0

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        slot = self._next_slot(part, angle, mirror)
        if slot is None:
            return None
        x, y, _, _, _ = slot
        # Lower is better, then further left. The large multiplier keeps the
        # shelf ordering dominant over the position within a shelf.
        score = -(y * 1e6 + x)
        return (x, y, score)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        slot = self._next_slot(part, angle, mirror)
        if slot is None:
            raise ValueError("no hay lugar para la pieza en la placa actual")
        slot_x, slot_y, width, height, shelf_y = slot

        if (
            abs(x - slot_x) > PLACE_TOLERANCE
            or abs(y - slot_y) > PLACE_TOLERANCE
        ):
            raise ValueError(
                f"place() recibió ({x!r}, {y!r}) pero el hueco libre para esta "
                f"pieza (part={part.id}, angle={angle}, mirror={mirror}) en el "
                f"estado actual del oráculo es ({slot_x!r}, {slot_y!r}). "
                "ShelfOracle solo puede commitear la posición que el propio "
                "cursor de estante habría producido: (x, y) tiene que venir de "
                "una llamada a best_placement con el mismo (part, angle, mirror) "
                "y sin ningún place() intermedio."
            )

        if shelf_y > self._shelf_y + PLACE_TOLERANCE:
            # The caller took the slot on a fresh shelf, so advance to it.
            self._shelf_y = shelf_y
            self._shelf_height = 0.0
            self._cursor_x = self._config.margin

        self._cursor_x = self._cursor_x + width + self._config.sep
        self._shelf_height = max(self._shelf_height, height)

    def _next_slot(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float, float, float] | None:
        """Return (dx, dy, width, height, shelf_y) for the next free slot, or None.

        `shelf_y` is the sheet-absolute y of the current shelf's bottom edge,
        before it gets folded into `dy` by the part's own bounding-box origin
        (`by0`, which is only 0 for an unmirrored, axis-aligned part). Callers
        that need to know whether a placement opened a new shelf must compare
        against `shelf_y`, not `dy`: a part rotated or mirrored so that `by0 !=
        0` has a `dy` that differs from the shelf's true position, even when it
        lands on the same shelf as the part before it.
        """
        margin = self._config.margin
        bx0, by0, bx1, by1 = transformed_bbox(part, angle, mirror)
        width, height = bx1 - bx0, by1 - by0

        usable_right = self._sheet_w - margin
        usable_top = self._sheet_h - margin

        cursor_x, shelf_y = self._cursor_x, self._shelf_y
        if cursor_x + width > usable_right + 1e-9:
            # Open a new shelf above the current one.
            cursor_x = margin
            shelf_y = shelf_y + self._shelf_height + self._config.sep
            if self._shelf_height == 0.0:
                shelf_y = self._shelf_y

        if cursor_x + width > usable_right + 1e-9:
            return None
        if shelf_y + height > usable_top + 1e-9:
            return None

        # Translate so the part's own bounding box lands at (cursor_x, shelf_y).
        return (cursor_x - bx0, shelf_y - by0, width, height, shelf_y)
