"""Las reglas de los parámetros, que comparten la CLI y la API."""

import pytest

from nesting.params import (
    FLAG_POR_CAMPO,
    NestParams,
    ParamsInvalidosError,
    a_config,
    mensaje_cli,
    validar,
)


def p(**cambios):
    return NestParams(material="mdf18", **cambios)


def test_los_valores_por_omision_son_validos():
    validar(p())


@pytest.mark.parametrize(
    "cambio, campo, regla",
    [
        ({"copias": 0}, "copias", ">= 1"),
        ({"copias": -3}, "copias", ">= 1"),
        ({"sep": -0.1}, "sep", ">= 0"),
        ({"borde": -1.0}, "borde", ">= 0"),
        ({"tol_cierre": 0.0}, "tol_cierre", "> 0"),
        ({"tol_cierre": -1.0}, "tol_cierre", "> 0"),
        ({"resolucion": 0.0}, "resolucion", "> 0"),
        ({"resolucion": -2.0}, "resolucion", "> 0"),
    ],
)
def test_cada_regla_nombra_su_campo_y_su_regla(cambio, campo, regla):
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(p(**cambio))

    assert capturado.value.rota.campo == campo
    assert capturado.value.rota.regla == regla
    assert capturado.value.rota.valor == next(iter(cambio.values()))


def test_la_separacion_cero_es_valida():
    """Cortar pegado es una decisión legítima del usuario, no un error."""
    validar(p(sep=0.0))


def test_el_borde_cero_es_valido():
    validar(p(borde=0.0))


def test_el_mensaje_de_la_cli_nombra_el_flag_y_el_valor():
    """La CLI tiene que seguir diciendo exactamente lo que decía.

    Ese texto es contrato: hay tests de la CLI que lo verifican, y lo lee
    gente en una terminal donde 'sep' a secas no significa nada.
    """
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(p(sep=-1.0))

    assert mensaje_cli(capturado.value.rota) == "--sep tiene que ser >= 0, se recibió -1.0"


def test_todo_campo_con_regla_tiene_su_flag():
    """Un campo sin flag haría reventar a `mensaje_cli` con KeyError justo
    cuando el usuario ya se equivocó, que es el peor momento."""
    for campo in ("copias", "sep", "borde", "tol_cierre", "resolucion"):
        assert campo in FLAG_POR_CAMPO


def test_a_config_traduce_los_nombres_al_motor():
    """La interfaz habla en español y el motor en inglés. La traducción vive
    en un solo lugar para que no se desincronice."""
    config = a_config(p(sep=3.0, borde=7.0, espejo=False, resolucion=1.5, esfuerzo="lento"))

    assert config.sep == 3.0
    assert config.margin == 7.0
    assert config.mirror is False
    assert config.resolution == 1.5
    assert config.effort == "lento"
    assert config.angles == (0.0, 90.0, 180.0, 270.0)


def test_a_config_no_valida_por_su_cuenta():
    """`a_config` traduce, no juzga. Validar es un paso aparte y explícito,
    así el que llama no puede creer que traducir ya lo protegió."""
    config = a_config(p(sep=-5.0))
    assert config.sep == -5.0
