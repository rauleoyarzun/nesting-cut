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


# --- Hallazgo: el umbral pierde margen a escala (float32 -> float64) -------
#
# `overlap_counts` casteaba a float32 antes de fftconvolve. El ruido de la
# FFT en float32 crece con el tamano del arreglo y con la cantidad de
# material en la placa (no con el contenido local de la ventana), porque
# fftconvolve hace una unica FFT global sobre toda la placa. Medido contra
# una tabla de sumas de area (metodo independiente, ver script de medicion
# del informe de la tarea 16):
#
#   placa            mascara      peor ruido (solap.=0)   peor valor (solap.=1)
#   1830x2600        300x300      ~0.03                    ~0.98
#   6000x8000        1000x1000    ~0.08-0.42               ~0.65-0.87
#   12000x16000      2000x2000    ~0.3-0.6                 0.388-0.518 (!!)
#
# A 12000x16000, en 2 de 5 semillas aleatorias un solapamiento real de UN
# pixel midio por debajo de COLLISION_THRESHOLD (hasta 0.388): la posicion se
# reportaba como libre estando ocupada. Con float64 el ruido se mantiene en
# ~1e-9 sin importar la escala, y un solapamiento real siempre mide ~1.0.
#
# Los dos tests de abajo usan 6000x8000/1000x1000 en vez de 12000x16000 para
# que corran en un tiempo razonable (~1 s cada uno en float64). A partir de
# 12000x16000 con mascara 2000x2000 es donde float32 empezaba a fallar de
# forma reproducible (falso negativo de colision); a 6000x8000/1000x1000 la
# degradacion ya es grande (ruido hasta ~0.42, valores reales de colision tan
# bajos como ~0.65) pero float32 todavia no cruzaba el umbral en las
# semillas probadas — por eso el informe recomienda 12000x16000 para ver el
# fallo franco, y esta suite se queda en la escala mas chica que ya alcanza
# para ejercitar el mismo codigo con el fix.

def test_a_single_pixel_overlap_is_detected_as_collision_at_scale():
    """El caso que fallaba: solapamiento real de exactamente un pixel, en una
    placa grande y densamente ocupada, con una mascara grande. Con float64
    tiene que detectarse como colision."""
    sheet = np.ones((6000, 8000), dtype=bool)
    mask = np.ones((1000, 1000), dtype=bool)

    # Se despeja un hueco del tamano de la mascara (mas margen) y se deja un
    # unico pixel ocupado en su esquina superior izquierda: la posicion de la
    # mascara anclada justo ahi cubre ese pixel y nada mas -> solapamiento
    # real == 1.
    pad = 5
    gap_h = mask.shape[0] + 2 * pad
    gap_w = mask.shape[1] + 2 * pad
    r0, c0 = 2000, 3000
    sheet[r0:r0 + gap_h, c0:c0 + gap_w] = False
    sheet[r0 + pad, c0 + pad] = True

    feasible = feasible_positions(sheet, mask)
    assert not feasible[r0 + pad, c0 + pad]


def test_numerical_noise_stays_far_below_threshold_on_a_large_occupied_sheet():
    """A la misma escala, con la placa densamente ocupada, el ruido de la FFT
    en float64 se mantiene muy por debajo del umbral (margen holgado de
    nueve ordenes de magnitud), sin importar cuanto material haya en la
    placa."""
    sheet = np.ones((6000, 8000), dtype=bool)
    mask = np.ones((1000, 1000), dtype=bool)

    # Hueco totalmente despejado, del tamano de la mascara mas margen: toda
    # posicion completamente dentro de el tiene solapamiento real == 0.
    pad = 5
    gap_h = mask.shape[0] + 2 * pad
    gap_w = mask.shape[1] + 2 * pad
    r0, c0 = 2000, 3000
    sheet[r0:r0 + gap_h, c0:c0 + gap_w] = False

    counts = overlap_counts(sheet, mask)
    zero_rows = gap_h - mask.shape[0] + 1
    zero_cols = gap_w - mask.shape[1] + 1
    zero_region = counts[r0:r0 + zero_rows, c0:c0 + zero_cols]

    assert np.max(np.abs(zero_region)) < 1e-6  # margen holgado vs. 0.5


# --- Hallazgo menor: forma del resultado en entradas degeneradas -----------

def test_a_sheet_with_a_zero_dimension_keeps_a_two_dimensional_shape():
    sheet = np.zeros((0, 20), dtype=bool)
    mask = np.ones((5, 5), dtype=bool)
    result = overlap_counts(sheet, mask)
    assert result.ndim == 2
    assert result.shape == (0, 16)


def test_a_mask_with_a_zero_dimension_keeps_a_two_dimensional_shape():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((0, 5), dtype=bool)
    result = overlap_counts(sheet, mask)
    assert result.ndim == 2
    assert result.shape == (21, 16)


def test_a_mask_larger_than_the_sheet_keeps_a_two_dimensional_shape():
    sheet = np.zeros((5, 5), dtype=bool)
    mask = np.ones((9, 9), dtype=bool)
    result = overlap_counts(sheet, mask)
    assert result.ndim == 2
    assert result.shape == (0, 0)


def test_a_mask_too_tall_but_not_too_wide_keeps_the_real_width():
    """La forma documentada es (Hs-Hm+1, Ws-Wm+1); si la mascara no entra en
    un eje, ese eje se recorta a 0, pero el otro eje conserva su valor real
    en vez de colapsar todo a (0, 0)."""
    sheet = np.zeros((5, 9), dtype=bool)
    mask = np.ones((9, 5), dtype=bool)  # demasiado alta (9 > 5), entra en ancho (5 <= 9)
    result = overlap_counts(sheet, mask)
    assert result.ndim == 2
    assert result.shape == (0, 5)
