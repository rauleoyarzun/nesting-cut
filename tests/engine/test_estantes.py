"""La predicción de placas por estantes con que la cartera ordena las combinaciones."""

from nesting.engine.estantes import predicted_sheets

# El área útil de la banqueta alta (1220 x 2440 con borde 5) y las cajas
# medidas en la Tarea 9 del plan de pares y cartera.
UTIL = (1210.0, 2430.0)
SEP = 8.0
MINIMA = (1809.0, 451.0)
DIAGONAL = (1508.0, 560.0)
APILADO = (1056.0, 875.0)
MARCO = (1055.0, 450.0)


def placas(*cajas, can_turn=True):
    return predicted_sheets(list(cajas), UTIL, SEP, can_turn)


def test_dos_diagonales_y_un_apilado_entran_en_una():
    assert placas(DIAGONAL, DIAGONAL, APILADO) == 1


def test_dos_diagonales_y_dos_marcos_sueltos_entran_en_una():
    assert placas(DIAGONAL, DIAGONAL, MARCO, MARCO) == 1


def test_minima_diagonal_y_apilado_son_dos():
    """La que midió el plan como ganadora con las cajas de antes; con las de
    ahora, la columna de la mínima (1809) más la del apilado (875) se pasa
    del alto útil."""
    assert placas(MINIMA, DIAGONAL, APILADO) == 2


def test_tres_de_un_solo_tipo_son_dos():
    assert placas(MINIMA, MINIMA, MINIMA) == 2
    assert placas(DIAGONAL, DIAGONAL, DIAGONAL) == 2
    assert placas(APILADO, APILADO, APILADO) == 2


def test_sin_girar_la_diagonal_no_entra():
    """1508 no entra en 1210 sin girar: cada diagonal cuenta su placa propia,
    y el apilado, que sí entra, va en una placa aparte."""
    assert placas(DIAGONAL, DIAGONAL, APILADO, can_turn=False) == 3
    assert placas(APILADO, can_turn=False) == 1


def test_una_caja_que_no_entra_en_ninguna_orientacion_cuenta_una_placa_y_no_levanta():
    assert placas((3000.0, 3000.0)) == 1
    assert placas((3000.0, 3000.0), MARCO) == 2


def test_sin_cajas_no_hay_placas():
    assert predicted_sheets([], UTIL, SEP, True) == 0


def test_girar_elige_la_orientacion_que_entra_a_lo_ancho():
    # 2000 x 500 no entra a lo ancho: parada (500 x 2000) sí, dos por estante.
    assert placas((2000.0, 500.0), (2000.0, 500.0)) == 1
    assert placas((2000.0, 500.0), (2000.0, 500.0), can_turn=False) == 2


def test_si_entran_las_dos_orientaciones_se_toma_la_mas_baja():
    # 800 x 1100 entra a lo ancho parada y acostada; acostada (1100 x 800),
    # una por estante, son 3 * 800 + 2 * 8 = 2416 de alto: una placa.
    # Parada serían 3 * 1100: dos.
    assert placas((800.0, 1100.0), (800.0, 1100.0), (800.0, 1100.0)) == 1
    assert placas((800.0, 1100.0), (800.0, 1100.0), (800.0, 1100.0), can_turn=False) == 2


def test_cada_caja_va_al_primer_estante_donde_entra_a_lo_ancho():
    # Estante 1 (alto 900): 700 de ancho; queda lugar para 502. Estante 2
    # (alto 800): 1000. La de 500 x 100 vuelve al estante 1.
    assert predicted_sheets([(700.0, 900.0), (1000.0, 800.0), (500.0, 100.0)],
                            (1210.0, 1720.0), 8.0, False) == 1
    # El segundo estante llega a 900 + 8 + 800 = 1708: con 1707 de alto
    # útil ya no entra y abre otra placa.
    assert predicted_sheets([(700.0, 900.0), (1000.0, 800.0)],
                            (1210.0, 1707.0), 8.0, False) == 2
