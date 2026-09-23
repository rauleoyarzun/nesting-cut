"""Fixtures para toda la suite."""

import pytest


@pytest.fixture(autouse=True)
def _tanda_minima_de_uno(request, monkeypatch):
    """Baja `cartera.MIN_BATCH` a 1 salvo en los tests `minimo_real`.

    Con el mínimo de verdad (12), cada `pack()` en normal son trece pasadas
    y la suite tardaría horas; y las cuentas chicas de los tests (`workers=3`
    son cuatro variantes) dejarían de valer. El mínimo se prueba aparte, con
    la marca.

    El fixture es `autouse`, así que corre en todos los tests e importa
    `cartera` -- y con ella el motor -- en cada uno, toquen el motor o no.
    El import va adentro sólo para que cargar este `conftest.py` no lo
    haga antes de que pytest junte los tests.
    """
    if request.node.get_closest_marker("minimo_real"):
        return
    from nesting.engine import cartera

    monkeypatch.setattr(cartera, "MIN_BATCH", 1)
