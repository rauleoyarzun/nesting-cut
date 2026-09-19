"""El callback de avance y la cancelación cooperativa."""

import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import Avance, Cancelado, EFFORT_RESTARTS, pack
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.model.material import Material
from nesting.model.part import Part

MATERIAL = Material("test", 1000.0, 1000.0, 180.0)


def cuadrado(part_id, lado=100.0):
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)),
        holes=(),
        entity_ids=(part_id,),
    )


def fabrica():
    cache = MaskCache()
    return lambda: RasterOracle(cache=cache)


def config(**cambios):
    base = {"sep": 5.0, "margin": 10.0, "effort": "rapido"}
    base.update(cambios)
    return NestConfig(**base)


def test_sin_callback_pack_se_comporta_igual_que_siempre():
    """La CLI no lo usa. Si pasarlo o no cambiara el resultado, el cambio
    estaría tocando el motor de verdad y no sólo observándolo."""
    piezas = [cuadrado(i) for i in range(6)]

    sin = pack(piezas, MATERIAL, config(), fabrica())
    con = pack(piezas, MATERIAL, config(), fabrica(), progreso=lambda a: True)

    assert sin.sheets_used == con.sheets_used
    assert [(p.part_id, p.sheet, p.transform) for p in sin.placements] == [
        (p.part_id, p.sheet, p.transform) for p in con.placements
    ]


def test_el_callback_se_llama_por_cada_pieza_ubicada():
    piezas = [cuadrado(i) for i in range(6)]
    avances = []

    pack(piezas, MATERIAL, config(), fabrica(), progreso=lambda a: avances.append(a) or True)

    ubicadas = [a for a in avances if not a.compactando]
    assert len(ubicadas) >= 6
    assert all(a.totales == 6 for a in ubicadas)


def test_las_piezas_ubicadas_solo_suben_dentro_de_un_intento():
    """Una barra que retrocede es peor que no tener barra."""
    piezas = [cuadrado(i) for i in range(8)]
    avances = []

    pack(piezas, MATERIAL, config(effort="normal"), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    por_intento = {}
    for a in avances:
        if a.compactando:
            continue
        previas = por_intento.get(a.intento, 0)
        assert a.ubicadas >= previas, f"el intento {a.intento} retrocedió"
        por_intento[a.intento] = a.ubicadas


def test_la_cantidad_de_intentos_se_sabe_desde_el_primer_aviso():
    """La interfaz necesita poder escribir 'intento 1 de 3' antes de que
    termine el primero. Sale de EFFORT_RESTARTS, no de haber terminado."""
    piezas = [cuadrado(i) for i in range(4)]
    avances = []

    pack(piezas, MATERIAL, config(effort="normal"), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    assert avances[0].intentos == EFFORT_RESTARTS["normal"]
    assert avances[0].intento == 1


def test_los_intentos_llegan_hasta_el_ultimo():
    piezas = [cuadrado(i) for i in range(4)]
    avances = []

    pack(piezas, MATERIAL, config(effort="normal"), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    intentos = {a.intento for a in avances if not a.compactando}
    assert intentos == set(range(1, EFFORT_RESTARTS["normal"] + 1))


def test_la_compactacion_final_se_avisa_aparte():
    """Es una sola pasada corta. Fingir un porcentaje ahí sería inventar."""
    piezas = [cuadrado(i) for i in range(4)]
    avances = []

    pack(piezas, MATERIAL, config(), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    assert any(a.compactando for a in avances)
    assert avances[-1].compactando


def test_devolver_False_cancela_y_levanta():
    piezas = [cuadrado(i) for i in range(20)]
    vistos = []

    def cortar(avance):
        vistos.append(avance)
        return len(vistos) < 3

    with pytest.raises(Cancelado):
        pack(piezas, MATERIAL, config(), fabrica(), progreso=cortar)

    assert len(vistos) == 3, "no puede seguir trabajando después del corte"


def test_cancelar_no_deja_el_resultado_a_medias():
    """Cancelar tiene que levantar, no devolver un PackResult incompleto que
    alguien podría escribir a un DXF creyendo que está entero."""
    piezas = [cuadrado(i) for i in range(20)]

    with pytest.raises(Cancelado):
        pack(piezas, MATERIAL, config(), fabrica(), progreso=lambda a: False)


def test_el_avance_nombra_la_placa_en_curso():
    """Con muchas piezas hacen falta varias placas, y el número de placa es
    lo único que le dice al usuario que el trabajo creció."""
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = []

    pack(piezas, MATERIAL, config(), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    placas = {a.placa for a in avances if not a.compactando}
    assert max(placas) >= 2
    assert min(placas) == 1


def test_sin_piezas_no_se_llama_al_callback():
    llamadas = []

    resultado = pack([], MATERIAL, config(), fabrica(),
                     progreso=lambda a: llamadas.append(a) or True)

    assert llamadas == []
    assert resultado.sheets_used == 0
