### Task 11: La interfaz `Oracle` y el motor trivial (`engine/oracle.py`, `engine/shelf_oracle.py`)

**Files:**
- Create: `src/nesting/engine/__init__.py`
- Create: `src/nesting/engine/oracle.py`
- Create: `src/nesting/engine/shelf_oracle.py`
- Test: `tests/engine/test_shelf_oracle.py`

**Interfaces:**
- Consumes: `Part` (Task 6), `Transform`, `apply_points` (Tasks 2-3)
- Produces:
  - `Weights(bottom_left: float = 1.0, contact: float = 1.0)`
  - `NestConfig(sep, margin, angles, mirror, resolution, effort, seed, weights)`
  - `Oracle` — `Protocol` con tres métodos
  - `transformed_bbox(part, angle, mirror) -> tuple[float, float, float, float]`
  - `ShelfOracle` — implementación por bounding box

**Esta es LA decisión estructural del proyecto (spec §3.2 y §4.3).** El contrato tiene exactamente tres operaciones:

```python
reset(sheet_w, sheet_h, config)                      # empezar una placa vacia
best_placement(part, angle, mirror) -> (x, y, score) | None
place(part, angle, mirror, x, y)                     # confirmar
```

`x` e `y` son directamente los componentes `dx`/`dy` de un `Transform`, así que no hay concepto de "origen de la pieza" filtrándose por la interfaz. `score` es "más alto es mejor". `best_placement` **no muta estado**; solo `place` lo hace — el packer consulta varios ángulos antes de decidir.

**El offset de separación vive adentro del oráculo** (restricción obligatoria de la spec §3.2): `ShelfOracle` separa bounding boxes por `sep`; `RasterOracle` (Task 17) dilatará máscaras. El packer nunca lo aplica.

**`ShelfOracle` empaqueta por estantes:** acumula piezas en una fila horizontal hasta que no entran más, y abre un estante nuevo por encima. Es deliberadamente malo — desperdicia todo el hueco entre el contorno curvo y su rectángulo. Existe para que el circuito completo funcione en el hito 2 y para que la mejora del motor real (hito 3) sea **medible contra una línea de base**.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/test_shelf_oracle.py` (crear también `tests/engine/__init__.py` vacío):

```python
import pytest

from nesting.engine.oracle import NestConfig, transformed_bbox
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


CONFIG = NestConfig(sep=10.0, margin=20.0)


def test_transformed_bbox_of_an_unrotated_part():
    assert transformed_bbox(rect_part(0, 100.0, 50.0), 0.0, False) == pytest.approx(
        (0.0, 0.0, 100.0, 50.0)
    )


def test_transformed_bbox_swaps_dimensions_at_ninety_degrees():
    x0, y0, x1, y1 = transformed_bbox(rect_part(0, 100.0, 50.0), 90.0, False)
    assert (x1 - x0) == pytest.approx(50.0)
    assert (y1 - y0) == pytest.approx(100.0)


def test_transformed_bbox_of_a_mirrored_part():
    x0, y0, x1, y1 = transformed_bbox(rect_part(0, 100.0, 50.0), 0.0, True)
    assert (x0, y0, x1, y1) == pytest.approx((-100.0, 0.0, 0.0, 50.0))


def test_the_first_part_lands_on_the_margin():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    x0, y0, _, _ = transformed_bbox(part, 0.0, False)
    assert (x + x0, y + y0) == pytest.approx((20.0, 20.0))


def test_best_placement_does_not_mutate_state():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    first = oracle.best_placement(part, 0.0, False)
    second = oracle.best_placement(part, 0.0, False)
    assert first == second


def test_the_second_part_goes_to_the_right_with_the_separation():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    oracle.place(part, 0.0, False, x, y)
    x2, _, _ = oracle.best_placement(part, 0.0, False)

    assert (x2 - x) == pytest.approx(110.0), "100 de ancho mas 10 de separacion"


def test_a_new_shelf_opens_when_the_row_is_full():
    oracle = ShelfOracle()
    oracle.reset(300.0, 1000.0, CONFIG)   # util: 260 de ancho
    part = rect_part(0, 100.0, 50.0)

    placed = []
    for _ in range(3):
        result = oracle.best_placement(part, 0.0, False)
        assert result is not None
        x, y, _ = result
        oracle.place(part, 0.0, False, x, y)
        placed.append((x, y))

    assert placed[0][1] == pytest.approx(placed[1][1]), "las dos primeras comparten estante"
    assert placed[2][1] > placed[0][1], "la tercera abre estante nuevo"
    assert placed[2][0] == pytest.approx(placed[0][0]), "y vuelve al margen izquierdo"


def test_returns_none_when_the_part_does_not_fit_at_all():
    oracle = ShelfOracle()
    oracle.reset(100.0, 100.0, CONFIG)
    assert oracle.best_placement(rect_part(0, 500.0, 500.0), 0.0, False) is None


def test_returns_none_once_the_sheet_is_full():
    oracle = ShelfOracle()
    oracle.reset(200.0, 200.0, CONFIG)   # util: 160 x 160
    part = rect_part(0, 150.0, 150.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    oracle.place(part, 0.0, False, x, y)
    assert oracle.best_placement(part, 0.0, False) is None


def test_lower_placements_score_higher():
    oracle = ShelfOracle()
    oracle.reset(300.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    _, _, first_score = oracle.best_placement(part, 0.0, False)
    for _ in range(2):
        x, y, _ = oracle.best_placement(part, 0.0, False)
        oracle.place(part, 0.0, False, x, y)
    _, _, later_score = oracle.best_placement(part, 0.0, False)

    assert first_score > later_score


def test_reset_clears_previous_state():
    oracle = ShelfOracle()
    part = rect_part(0, 100.0, 50.0)

    oracle.reset(1000.0, 1000.0, CONFIG)
    x, y, _ = oracle.best_placement(part, 0.0, False)
    oracle.place(part, 0.0, False, x, y)

    oracle.reset(1000.0, 1000.0, CONFIG)
    assert oracle.best_placement(part, 0.0, False)[:2] == pytest.approx((x, y))


def test_a_full_shelf_layout_passes_the_verifier():
    """El test que importa: lo que produce el oraculo tiene que ser valido."""
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)

    parts = [rect_part(i, 100.0, 80.0) for i in range(12)]
    placements = []
    for part in parts:
        result = oracle.best_placement(part, 0.0, False)
        if result is None:
            continue
        x, y, _ = result
        oracle.place(part, 0.0, False, x, y)
        placements.append(Placement(part.id, 0, Transform(0.0, False, x, y)))

    assert len(placements) >= 8
    assert verify(parts, placements, 1000.0, 1000.0, sep=10.0, margin=20.0) == []


def test_rotated_parts_also_pass_the_verifier():
    oracle = ShelfOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)

    parts = [rect_part(i, 200.0, 60.0) for i in range(6)]
    placements = []
    for index, part in enumerate(parts):
        angle = 90.0 if index % 2 else 0.0
        result = oracle.best_placement(part, angle, False)
        if result is None:
            continue
        x, y, _ = result
        oracle.place(part, angle, False, x, y)
        placements.append(Placement(part.id, 0, Transform(angle, False, x, y)))

    assert placements
    assert verify(parts, placements, 1000.0, 1000.0, sep=10.0, margin=20.0) == []
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/test_shelf_oracle.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine'`.

- [ ] **Step 3: Escribir la interfaz**

Archivo `src/nesting/engine/__init__.py`: vacío.

Archivo `src/nesting/engine/oracle.py`:

```python
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
from typing import Protocol

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
    """


@dataclass(frozen=True)
class NestConfig:
    sep: float = 5.0
    """Minimum gap between parts, in mm."""

    margin: float = 10.0
    """Minimum gap between a part and the sheet edge, in mm."""

    angles: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)
    mirror: bool = True
    resolution: float = 1.0
    """Raster resolution in mm per pixel. Ignored by non-raster oracles."""

    effort: str = "normal"
    """One of "rapido", "normal", "lento"."""

    seed: int = 0
    weights: Weights = field(default_factory=Weights)


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
        """Commit a placement, so later queries see this part as occupied."""
        ...


def transformed_bbox(
    part: Part, angle: float, mirror: bool
) -> tuple[float, float, float, float]:
    """Bounding box of `part` at this orientation, before any translation."""
    points = apply_points(Transform(angle, mirror, 0.0, 0.0), part.outer)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))

```

- [ ] **Step 4: Escribir el motor trivial**

Archivo `src/nesting/engine/shelf_oracle.py`:

```python
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
        x, y, _, _ = slot
        # Lower is better, then further left. The large multiplier keeps the
        # shelf ordering dominant over the position within a shelf.
        score = -(y * 1e6 + x)
        return (x, y, score)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        slot = self._next_slot(part, angle, mirror)
        if slot is None:
            raise ValueError("no hay lugar para la pieza en la placa actual")
        _, _, width, height = slot

        if y > self._shelf_y + 1e-9:
            # The caller took the slot on a fresh shelf, so advance to it.
            self._shelf_y = y
            self._shelf_height = 0.0
            self._cursor_x = self._config.margin

        self._cursor_x = self._cursor_x + width + self._config.sep
        self._shelf_height = max(self._shelf_height, height)

    def _next_slot(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float, float] | None:
        """Return (dx, dy, width, height) for the next free slot, or None."""
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
        return (cursor_x - bx0, shelf_y - by0, width, height)
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/test_shelf_oracle.py -v`
Esperado: `13 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/engine tests/engine
git commit -m "feat: interfaz Oracle y motor trivial por bounding box"
```

---

