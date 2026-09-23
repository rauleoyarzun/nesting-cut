"""Las consultas al oráculo: cuántas se hicieron y cuántas se prevén.

Una consulta es una llamada a `Oracle.best_placement`. Es la unidad con la
que se mide el avance y se estima el tiempo (spec de tiempo estimado, 2).
"""

import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    Avance,
    Cancelado,
    _compact_last_sheet,
    _pack_once,
    pack,
)
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.model.material import Material
from nesting.model.part import Part
from nesting.model.sheet import SheetSupply

MATERIAL = Material("test", 1000.0, 1000.0, 180.0)
PLAN = SheetSupply(stock=MATERIAL.stock_sheet(), material_name=MATERIAL.name)


def cuadrado(part_id, lado=100.0):
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)),
        holes=(),
        entity_ids=(part_id,),
    )


def rectangulo(part_id, ancho, alto):
    return Part(
        part_id, ((0.0, 0.0), (ancho, 0.0), (ancho, alto), (0.0, alto)), (), (part_id,)
    )


class Espia:
    """Envuelve un oráculo, cuenta cada `best_placement` y no cambia nada.

    Es la cuenta de verdad contra la que se compara lo que informa `pack`:
    si el motor contara por su lado (por ejemplo, piezas por orientaciones)
    y no las llamadas reales, este espía lo agarra.
    """

    def __init__(self, interno, cuenta):
        self._interno = interno
        self._cuenta = cuenta

    def reset(self, sheet_w, sheet_h, config):
        self._interno.reset(sheet_w, sheet_h, config)

    def best_placement(self, part, angle, mirror):
        self._cuenta[0] += 1
        return self._interno.best_placement(part, angle, mirror)

    def place(self, part, angle, mirror, x, y):
        self._interno.place(part, angle, mirror, x, y)


def fabrica_raster():
    cache = MaskCache()
    return lambda: RasterOracle(cache=cache)


def fabrica_espia(cuenta):
    cache = MaskCache()
    return lambda: Espia(RasterOracle(cache=cache), cuenta)


def config(**cambios):
    base = {"sep": 5.0, "margin": 10.0, "effort": "rapido"}
    base.update(cambios)
    return NestConfig(**base)


def correr(piezas, cfg, fabrica, plan=PLAN):
    avances = []
    pack(piezas, plan, cfg, fabrica, progreso=lambda a: avances.append(a) or True)
    return avances


def test_un_avance_armado_como_antes_trae_cero_consultas():
    """Los corredores de mentira de `tests/app` arman `Avance` con cinco
    argumentos. Tienen que seguir funcionando sin tocarlos."""
    avance = Avance(1, 1, 0, 10, 1)
    assert avance.consultas_hechas == 0
    assert avance.consultas_previstas == 0


def test_las_consultas_hechas_nunca_bajan():
    """No se reinician entre intentos ni entre fases: son la única cifra de
    avance que no retrocede al empezar el intento siguiente."""
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = correr(piezas, config(effort="normal"), fabrica_raster())

    hechas = [a.consultas_hechas for a in avances]
    assert hechas == sorted(hechas)
    assert hechas[0] > 0


def test_las_consultas_hechas_terminan_iguales_a_las_llamadas_reales():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    cuenta = [0]

    avances = correr(piezas, config(effort="normal"), fabrica_espia(cuenta))

    assert cuenta[0] > 0
    assert avances[-1].consultas_hechas == cuenta[0]


def test_contar_no_cambia_el_layout():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    cuenta = [0]
    sin = pack(piezas, PLAN, config(), fabrica_raster())
    con = pack(piezas, PLAN, config(), fabrica_espia(cuenta), progreso=lambda a: True)

    assert [(p.part_id, p.sheet, p.transform) for p in sin.placements] == [
        (p.part_id, p.sheet, p.transform) for p in con.placements
    ]


def test_una_pieza_que_no_entra_tambien_avisa():
    """Placa de 1000 con margen 10: entra un solo cuadrado de 600 por placa.
    Las dos que no entran en la placa 1 gastan sus consultas ahí, y el aviso
    tiene que salir igual para que el contador y el botón de cancelar las
    vean."""
    grandes = [cuadrado(i, lado=600.0) for i in range(3)]
    cfg = config(angles=(0.0,), mirror=False)
    avisos = []

    _pack_once(grandes, PLAN, cfg, ShelfOracle, lambda u, p: avisos.append((u, p)))

    assert avisos == [(1, 1), (1, 1), (1, 1), (2, 2), (2, 2), (3, 3)]


def test_la_compactacion_avisa():
    """Cuatro cuadrados chicos: una sola placa, así que la recuperación sale
    sin consultar y todo aviso de `compactando` después del de entrada es de
    la compactación (4 piezas) o el final."""
    piezas = [cuadrado(i) for i in range(4)]
    avances = correr(piezas, config(), fabrica_raster())

    compactando = [a for a in avances if a.compactando]
    assert len(compactando) == 1 + 4 + 1


def test_la_compactacion_se_cancela():
    piezas = [cuadrado(i) for i in range(4)]
    vistos = []

    def cortar(avance):
        vistos.append(avance)
        return sum(1 for a in vistos if a.compactando) < 2

    with pytest.raises(Cancelado):
        pack(piezas, PLAN, config(), fabrica_raster(), progreso=cortar)

    assert sum(1 for a in vistos if a.compactando) == 2


def test_compactar_reenvia_el_aviso_y_deja_pasar_cancelado():
    """El `except PartTooLargeError` de `_compact_last_sheet` no puede
    tragarse un `Cancelado`: sería un trabajo cancelado que termina LISTO."""
    piezas = [cuadrado(i) for i in range(4)]
    fabrica = fabrica_raster()
    armado = _pack_once(piezas, PLAN, config(), fabrica)

    def cancelar(ubicadas, placa):
        raise Cancelado("el trabajo se canceló")

    with pytest.raises(Cancelado):
        _compact_last_sheet(armado, piezas, config(), fabrica, MATERIAL.name, cancelar)


def test_sin_callback_no_hay_avisos_pero_el_resultado_es_el_mismo():
    piezas = [cuadrado(i) for i in range(4)]
    assert pack(piezas, PLAN, config(), fabrica_raster()).sheets_used == 1
