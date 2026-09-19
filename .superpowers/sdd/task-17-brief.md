### Task 17: Puntaje de posiciones (`engine/raster/scoring.py`)

**Files:**
- Create: `src/nesting/engine/raster/scoring.py`
- Test: `tests/engine/raster/test_scoring.py`

**Interfaces:**
- Consumes: `overlap_counts` (Task 16), `disk_kernel` (Task 15), `Weights` (Task 11)
- Produces:
  - `contact_band(clearance: np.ndarray, extra_px: int) -> np.ndarray`
  - `best_position(feasible, sheet, band, weights) -> tuple[int, int, float] | None` — devuelve `(px, py, score)`

**Que la pieza entre no alcanza (spec §5.4).** El puntaje combina dos términos, ambos normalizados a `[0, 1]` para que los pesos sean comparables:

```
abajo_izquierda = 1 − (py + 0.001·px) / (filas + 0.001·columnas)
contacto        = píxeles_de_banda_apoyados / píxeles_de_banda

puntaje = w.bottom_left · abajo_izquierda  +  w.contact · contacto
```

- **abajo-izquierda** empuja todo hacia una esquina, concentrando el sobrante en un bloque grande y aprovechable en vez de recortes dispersos.
- **contacto** mide cuánto perímetro de la pieza queda **apoyado** contra material ya colocado. La banda es la corona entre `clearance` y `clearance` dilatada un poco más: donde esa corona solapa mucho, la pieza está **encajada**.

**El término de contacto es el que produce el entrelazado** que se ve en los archivos del proyecto — una pata metiéndose en la curva de la otra. Sin él, bottom-left solo apila y deja huecos.

**Atajo importante:** si la placa está vacía, el contacto es cero en todas partes. En ese caso se saltea la segunda FFT por completo y se toma directamente la posición más abajo-izquierda. Las primeras colocaciones de cada placa son así, o sea que el ahorro es real.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/raster/test_scoring.py`:

```python
import numpy as np
import pytest

from nesting.engine.oracle import Weights
from nesting.engine.raster.scoring import best_position, contact_band
from nesting.engine.raster.search import feasible_positions

ONLY_BL = Weights(bottom_left=1.0, contact=0.0)
ONLY_CONTACT = Weights(bottom_left=0.0, contact=1.0)


def test_the_contact_band_is_a_ring_outside_the_clearance():
    clearance = np.zeros((11, 11), dtype=bool)
    clearance[4:7, 4:7] = True

    band = contact_band(clearance, extra_px=2)
    assert not (band & clearance).any(), "la banda no pisa la holgura"
    assert band.any()
    assert band[3, 5], "justo por fuera del borde"


def test_a_wider_band_covers_more():
    clearance = np.zeros((21, 21), dtype=bool)
    clearance[9:12, 9:12] = True
    assert contact_band(clearance, 4).sum() > contact_band(clearance, 1).sum()


def test_a_zero_width_band_is_empty():
    clearance = np.zeros((11, 11), dtype=bool)
    clearance[4:7, 4:7] = True
    assert not contact_band(clearance, 0).any()


def test_bottom_left_picks_the_lowest_row():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    band = contact_band(mask, 2)

    px, py, _ = best_position(feasible, sheet, band, ONLY_BL)
    assert (px, py) == (0, 0)


def test_bottom_left_prefers_a_lower_row_over_a_lefter_column():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    feasible[0, :] = False          # bloquear toda la fila de abajo
    band = contact_band(mask, 2)

    px, py, _ = best_position(feasible, sheet, band, ONLY_BL)
    assert py == 1
    assert px == 0


def test_returns_none_when_nothing_is_feasible():
    sheet = np.ones((20, 20), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    assert best_position(feasible, sheet, contact_band(mask, 2), ONLY_BL) is None


def test_returns_none_for_an_empty_feasible_array():
    empty = np.zeros((0, 0), dtype=bool)
    assert best_position(empty, np.zeros((5, 5), dtype=bool),
                         np.zeros((3, 3), dtype=bool), ONLY_BL) is None


def test_contact_pulls_the_part_against_existing_material():
    """Con peso solo en contacto, la pieza se pega a lo ya colocado."""
    sheet = np.zeros((40, 40), dtype=bool)
    sheet[30:38, 30:38] = True      # un bloque arriba a la derecha

    mask = np.ones((4, 4), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    band = contact_band(mask, 2)

    px, py, _ = best_position(feasible, sheet, band, ONLY_CONTACT)
    assert px > 20 and py > 20, "eligio pegarse al bloque, no la esquina de abajo"


def test_with_an_empty_sheet_contact_weight_falls_back_to_bottom_left():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    band = contact_band(mask, 2)

    px, py, _ = best_position(feasible, sheet, band, ONLY_CONTACT)
    assert (px, py) == (0, 0)


def test_the_score_is_bounded_between_zero_and_the_weight_sum():
    sheet = np.zeros((30, 30), dtype=bool)
    sheet[20:25, 20:25] = True
    mask = np.ones((4, 4), dtype=bool)
    weights = Weights(bottom_left=1.0, contact=1.0)

    result = best_position(feasible_positions(sheet, mask), sheet,
                           contact_band(mask, 2), weights)
    assert result is not None
    assert 0.0 <= result[2] <= 2.0 + 1e-9


def test_a_higher_contact_weight_changes_the_choice():
    sheet = np.zeros((40, 40), dtype=bool)
    sheet[30:38, 30:38] = True
    mask = np.ones((4, 4), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    band = contact_band(mask, 2)

    corner = best_position(feasible, sheet, band, Weights(1.0, 0.0))
    hugging = best_position(feasible, sheet, band, Weights(0.0, 1.0))
    assert corner[:2] != hugging[:2]


def test_the_chosen_position_is_always_feasible():
    rng = np.random.default_rng(7)
    for _ in range(5):
        sheet = rng.random((40, 40)) < 0.1
        mask = np.ones((4, 4), dtype=bool)
        feasible = feasible_positions(sheet, mask)
        if not feasible.any():
            continue
        px, py, _ = best_position(feasible, sheet, contact_band(mask, 2),
                                  Weights(1.0, 1.0))
        assert feasible[py, px]
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/raster/test_scoring.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine.raster.scoring'`.

- [ ] **Step 3: Escribir el puntaje**

Archivo `src/nesting/engine/raster/scoring.py`:

```python
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

COLUMN_TIE_BREAK = 0.001
"""Weight of the column in the bottom-left term: enough to break ties, not to
override the row ordering."""


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
    span = rows + COLUMN_TIE_BREAK * cols
    bottom_left = 1.0 - (row_index + COLUMN_TIE_BREAK * col_index) / span

    score = weights.bottom_left * bottom_left

    # With an empty sheet contact is zero everywhere, so the second correlation
    # would be pure cost. The opening placements of every sheet take this path.
    if weights.contact != 0.0 and sheet.any() and band.any():
        counts = overlap_counts(sheet, band)
        if counts.shape == feasible.shape:
            score = score + weights.contact * (counts / band.sum())

    score = np.where(feasible, score, -np.inf)
    flat = int(np.argmax(score))
    row, col = divmod(flat, cols)
    return (col, row, float(score[row, col]))
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/raster/test_scoring.py -v`
Esperado: `12 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/raster/scoring.py tests/engine/raster/test_scoring.py
git commit -m "feat: puntaje de posiciones con termino de contacto"
```

---

