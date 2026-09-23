"""Fixtures para toda la suite."""

import pytest


@pytest.fixture(autouse=True)
def _tanda_minima_de_uno(request, monkeypatch):
    """Baja `cartera.MIN_BATCH` a 1 salvo en los tests `minimo_real`.

    Con el mínimo de verdad (12), cada `pack()` en normal son trece pasadas
    y la suite tardaría horas; y las cuentas chicas de los tests (`workers=3`
    son cuatro variantes) dejarían de valer. El mínimo se prueba aparte, con
    la marca. Se importa adentro para que un test que no toca el motor no
    lo cargue.
    """
    if request.node.get_closest_marker("minimo_real"):
        return
    from nesting.engine import cartera

    monkeypatch.setattr(cartera, "MIN_BATCH", 1)
