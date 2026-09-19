### Task 16: Búsqueda por FFT (`engine/raster/search.py`)

**Files:**
- Create: `src/nesting/engine/raster/search.py`
- Test: `tests/engine/raster/test_search.py`

**Interfaces:**
- Consumes: nada del proyecto, solo `numpy` y `scipy.signal`
- Produces:
  - `overlap_counts(sheet: np.ndarray, mask: np.ndarray) -> np.ndarray` — cuántos píxeles de `mask` solapan material, para **cada** posición. Forma `(Hs − Hm + 1, Ws − Wm + 1)`
  - `feasible_positions(sheet: np.ndarray, clearance: np.ndarray) -> np.ndarray` — booleano, `True` donde no hay solapamiento

**El truco central de la spec §5.3.** Probar posición por posición es inviable: una placa de 1830 × 2600 a 1 mm/px tiene 4,8 millones de posiciones. Una **correlación cruzada** las evalúa **todas de una vez**.

`scipy.signal.fftconvolve` calcula convolución, no correlación. La relación es: `correlación(A, B) = convolución(A, B invertida en ambos ejes)`. Con `mode="valid"` el resultado tiene exactamente una entrada por posición donde la máscara entra completa dentro de la placa, así que **los límites de la placa quedan garantizados por la forma del arreglo** — sin código de acotamiento.

**Umbral:** la FFT devuelve flotantes con ruido numérico del orden de `1e-10`. Un solapamiento real vale al menos `1.0`, así que el umbral `> 0.5` separa ambos casos con margen amplio.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/raster/test_search.py`:

```python
import numpy as np
import pytest

from nesting.engine.raster.search import feasible_positions, overlap_counts


def brute_force_overlap(sheet, mask):
    """Referencia directa, para contrastar contra la version por FFT."""
    rows = sheet.shape[0] - mask.shape[0] + 1
    cols = sheet.shape[1] - mask.shape[1] + 1
    out = np.zeros((rows, cols), dtype=int)
    for r in range(rows):
        for c in range(cols):
            window = sheet[r:r + mask.shape[0], c:c + mask.shape[1]]
            out[r, c] = int((window & mask).sum())
    return out


def test_overlap_counts_has_the_valid_correlation_shape():
    sheet = np.zeros((20, 30), dtype=bool)
    mask = np.zeros((5, 7), dtype=bool)
    assert overlap_counts(sheet, mask).shape == (16, 24)


def test_overlap_counts_matches_brute_force_on_a_small_case():
    rng = np.random.default_rng(0)
    sheet = rng.random((24, 28)) < 0.3
    mask = rng.random((6, 5)) < 0.5

    fast = np.rint(overlap_counts(sheet, mask)).astype(int)
    assert np.array_equal(fast, brute_force_overlap(sheet, mask))


def test_overlap_counts_matches_brute_force_on_several_random_cases():
    rng = np.random.default_rng(12345)
    for _ in range(10):
        sheet = rng.random((30, 26)) < 0.25
        mask = rng.random((7, 9)) < 0.6
        fast = np.rint(overlap_counts(sheet, mask)).astype(int)
        assert np.array_equal(fast, brute_force_overlap(sheet, mask))


def test_an_empty_sheet_gives_zero_overlap_everywhere():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((4, 4), dtype=bool)
    assert np.allclose(overlap_counts(sheet, mask), 0.0, atol=1e-6)


def test_everything_is_feasible_on_an_empty_sheet():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((4, 4), dtype=bool)
    assert feasible_positions(sheet, mask).all()


def test_nothing_is_feasible_on_a_full_sheet():
    sheet = np.ones((20, 20), dtype=bool)
    mask = np.ones((4, 4), dtype=bool)
    assert not feasible_positions(sheet, mask).any()


def test_a_single_occupied_pixel_blocks_exactly_the_overlapping_positions():
    sheet = np.zeros((20, 20), dtype=bool)
    sheet[10, 10] = True
    mask = np.ones((3, 3), dtype=bool)

    feasible = feasible_positions(sheet, mask)
    # Las 9 posiciones cuyo 3x3 cubre (10,10) quedan bloqueadas.
    assert feasible.sum() == feasible.size - 9
    assert not feasible[8, 8]
    assert not feasible[10, 10]
    assert feasible[7, 10]


def test_a_mask_with_a_hole_can_straddle_occupied_material():
    """La propiedad que habilita nestear dentro de agujeros."""
    sheet = np.zeros((20, 20), dtype=bool)
    sheet[10, 10] = True

    mask = np.ones((5, 5), dtype=bool)
    mask[2, 2] = False   # el centro de la mascara esta vacio

    feasible = feasible_positions(sheet, mask)
    assert feasible[8, 8], "el pixel ocupado cae justo en el hueco de la mascara"


def test_feasible_positions_returns_booleans():
    sheet = np.zeros((10, 10), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    assert feasible_positions(sheet, mask).dtype == np.bool_


def test_a_mask_larger_than_the_sheet_yields_no_positions():
    sheet = np.zeros((5, 5), dtype=bool)
    mask = np.ones((9, 9), dtype=bool)
    assert feasible_positions(sheet, mask).size == 0


def test_numerical_noise_does_not_create_false_collisions():
    """Placa grande y vacia: el ruido de la FFT no debe superar el umbral."""
    sheet = np.zeros((600, 800), dtype=bool)
    mask = np.ones((60, 40), dtype=bool)
    assert feasible_positions(sheet, mask).all()


def test_numerical_noise_does_not_hide_a_real_collision():
    sheet = np.zeros((600, 800), dtype=bool)
    sheet[300, 400] = True
    mask = np.ones((60, 40), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    assert not feasible[300, 400]
    assert not feasible[241, 361]


def test_rejects_a_non_boolean_sheet():
    with pytest.raises(TypeError):
        overlap_counts(np.zeros((5, 5), dtype=int), np.ones((2, 2), dtype=bool))
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/raster/test_search.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine.raster.search'`.

- [ ] **Step 3: Escribir la búsqueda**

Archivo `src/nesting/engine/raster/search.py`:

```python
"""Evaluate every candidate position at once, with one cross-correlation.

Testing positions one by one is hopeless: a 1830 x 2600 sheet at 1 mm per pixel
has 4.8 million of them. A single correlation answers all of them together.
"""

import numpy as np
from scipy.signal import fftconvolve

COLLISION_THRESHOLD = 0.5
"""A real overlap is at least 1.0; FFT noise is around 1e-10. This sits between."""


def overlap_counts(sheet: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """How many pixels of `mask` land on occupied material, for every position.

    The result has shape (Hs - Hm + 1, Ws - Wm + 1): one entry per position where
    the mask fits entirely inside the sheet. That means the sheet bounds are
    enforced by the array shape alone, with no explicit clamping anywhere.
    """
    if sheet.dtype != np.bool_ or mask.dtype != np.bool_:
        raise TypeError("sheet y mask tienen que ser arreglos booleanos")
    if mask.shape[0] > sheet.shape[0] or mask.shape[1] > sheet.shape[1]:
        return np.zeros((0, 0), dtype=float)

    # fftconvolve computes a convolution; flipping the mask on both axes turns
    # it into the correlation we actually want.
    return fftconvolve(
        sheet.astype(np.float32),
        mask[::-1, ::-1].astype(np.float32),
        mode="valid",
    )


def feasible_positions(sheet: np.ndarray, clearance: np.ndarray) -> np.ndarray:
    """True at every position where the clearance mask touches no material."""
    counts = overlap_counts(sheet, clearance)
    if counts.size == 0:
        return np.zeros((0, 0), dtype=bool)
    return counts < COLLISION_THRESHOLD
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/raster/test_search.py -v`
Esperado: `13 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/raster/search.py tests/engine/raster/test_search.py
git commit -m "feat: busqueda de posiciones factibles por correlacion FFT"
```

---

