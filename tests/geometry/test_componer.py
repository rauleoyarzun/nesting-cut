"""`componer(T, t)` tiene que ser, punto por punto, aplicar `t` y después `T`."""

import random

import pytest

from nesting.geometry.transform import apply_point, componer
from nesting.model.entities import Transform

ANGULOS = (0.0, 45.0, 90.0, 135.0, 180.0, 270.0, 33.3, 301.7)


def _al_azar(rng: random.Random) -> Transform:
    return Transform(
        angle_deg=rng.choice(ANGULOS),
        mirror=rng.random() < 0.5,
        dx=rng.uniform(-800.0, 800.0),
        dy=rng.uniform(-800.0, 800.0),
    )


def test_componer_es_aplicar_primero_la_de_adentro_y_despues_la_de_afuera():
    """La prueba que importa: si esto vale para doscientas transformaciones
    al azar, con y sin espejo en cada lado, la fórmula está bien. Una fórmula
    con el signo del ángulo al revés cuando `T` espeja pasa todos los casos
    sin espejo y falla la mitad de éstos."""
    rng = random.Random(20260922)
    for _ in range(200):
        exterior, interior = _al_azar(rng), _al_azar(rng)
        punto = (rng.uniform(-300.0, 300.0), rng.uniform(-300.0, 300.0))

        esperado = apply_point(exterior, apply_point(interior, punto))
        obtenido = apply_point(componer(exterior, interior), punto)

        assert obtenido == pytest.approx(esperado, abs=1e-6), (exterior, interior)


def test_la_identidad_no_cambia_nada_de_ningun_lado():
    t = Transform(90.0, True, 12.5, -3.0)
    assert componer(Transform.identity(), t) == t
    assert componer(t, Transform.identity()) == t


def test_dos_espejos_se_cancelan():
    espejo = Transform(0.0, True, 0.0, 0.0)
    assert componer(espejo, espejo).mirror is False


def test_el_angulo_queda_entre_0_y_360():
    """El DXF y el oráculo reciben este ángulo tal cual; uno de 450° o de
    -90° es correcto pero es un número que nadie espera ver."""
    tres_cuartos = Transform(270.0, False, 0.0, 0.0)
    assert componer(tres_cuartos, Transform(180.0, False, 0.0, 0.0)).angle_deg == 90.0
    espejada = Transform(0.0, True, 0.0, 0.0)
    assert componer(espejada, Transform(90.0, False, 0.0, 0.0)).angle_deg == 270.0
