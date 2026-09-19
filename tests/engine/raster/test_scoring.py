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
    """Con peso solo en contacto, la pieza se pega a lo ya colocado.

    La mascara lleva un margen de holgura alrededor del nucleo solido (igual
    que una mascara real de `rasterize`, que siempre sale con ese margen):
    sin el, `contact_band` no tiene donde dibujar el anillo -- un bloque que
    llena todo su propio arreglo no deja pixeles "afuera" dentro del mismo
    arreglo, sin importar la implementacion.
    """
    sheet = np.zeros((40, 40), dtype=bool)
    sheet[30:38, 30:38] = True      # un bloque arriba a la derecha

    mask = np.zeros((8, 8), dtype=bool)
    mask[2:6, 2:6] = True           # nucleo solido de 4x4 con margen alrededor
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
    """Misma mascara con margen que en el test anterior, y por el mismo motivo."""
    sheet = np.zeros((40, 40), dtype=bool)
    sheet[30:38, 30:38] = True
    mask = np.zeros((8, 8), dtype=bool)
    mask[2:6, 2:6] = True
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


def test_bottom_left_survives_a_real_scale_plate():
    """Reproduccion del hallazgo 1: 1200x2600, con COLUMN_TIE_BREAK fijo el
    desempate de columna terminaba pesando mas que una fila entera y ganaba
    la fila 1. Con el termino normalizado por ancho tiene que ganar la fila 0."""
    rows, cols = 1200, 2600
    feasible = np.zeros((rows, cols), dtype=bool)
    feasible[0, cols - 1] = True     # unica factible de la fila 0, ultima columna
    feasible[1, 0] = True            # factible de la fila 1, primera columna
    sheet = np.zeros((rows + 2, cols + 2), dtype=bool)
    band = np.zeros((3, 3), dtype=bool)

    px, py, _ = best_position(feasible, sheet, band, ONLY_BL)
    assert py == 0, "el desempate de columna no puede ganarle a la fila"
    assert px == cols - 1


@pytest.mark.parametrize("cols", [500, 1000, 2000, 4000, 8000])
def test_lower_row_always_wins_regardless_of_width(cols):
    rows = 300
    feasible = np.zeros((rows, cols), dtype=bool)
    feasible[0, cols - 1] = True     # fila mas baja, extremo derecho
    feasible[1, 0] = True            # fila mas alta, extremo izquierdo
    sheet = np.zeros((rows + 2, cols + 2), dtype=bool)
    band = np.zeros((3, 3), dtype=bool)

    px, py, _ = best_position(feasible, sheet, band, ONLY_BL)
    assert py == 0
    assert px == cols - 1


def test_tie_break_still_prefers_the_smaller_column_within_a_row():
    sheet = np.zeros((20, 20), dtype=bool)
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    feasible[0, :] = False           # bloquear toda la fila de abajo
    band = contact_band(mask, 2)

    px, py, _ = best_position(feasible, sheet, band, ONLY_BL)
    assert py == 1
    assert px == 0


def test_a_mismatched_band_shape_raises_value_error():
    sheet = np.zeros((20, 20), dtype=bool)
    sheet[10:15, 10:15] = True
    mask = np.ones((3, 3), dtype=bool)
    feasible = feasible_positions(sheet, mask)
    incompatible_band = np.ones((5, 5), dtype=bool)

    with pytest.raises(ValueError):
        best_position(feasible, sheet, incompatible_band, Weights(1.0, 1.0))


def test_weights_reject_a_negative_bottom_left():
    with pytest.raises(ValueError):
        Weights(bottom_left=-1.0, contact=1.0)


def test_weights_reject_a_negative_contact():
    with pytest.raises(ValueError):
        Weights(bottom_left=1.0, contact=-1.0)
