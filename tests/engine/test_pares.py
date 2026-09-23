"""Tipos de encastre de dos copias de una misma pieza."""

from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, Polygon

from nesting.engine.iguales import Clase, Member, congruence
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import orientations
from nesting.engine.pares import (
    MAX_PAIRED_CLASSES,
    TIPOS_POR_CLASE,
    b_orientations,
    find_pair_types,
    pairable_classes,
    slide_window,
    union_with_bridge,
)
from nesting.engine.raster.masks import MaskCache
from nesting.geometry.verify import placed_polygon
from nesting.model.entities import Transform
from nesting.model.part import Part
from nesting.model.sheet import Sheet

SEP = 8.0
LIBRE = Sheet(1200.0, 680.0, grain_tolerance=180.0)
CON_VETA = Sheet(1200.0, 680.0, grain_tolerance=5.0)
CONFIG = NestConfig(sep=SEP, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0),
                    mirror=True, resolution=2.0)
UTIL = (1190.0, 670.0)

# La L del caso sintético de la Tarea 9: 600 x 300, brazos de 110.
ELE = ((0.0, 0.0), (600.0, 0.0), (600.0, 110.0), (110.0, 110.0), (110.0, 300.0), (0.0, 300.0))

BANQUETA = Path(__file__).resolve().parents[2] / "bench" / "files" / "banqueta-alta.ai"


def ele(part_id=0, holes=()):
    return Part(part_id, ELE, holes, (part_id,))


def tipos(sheet=LIBRE, config=CONFIG, how_many=6, part=None):
    choices = orientations(sheet, config)
    respetada = sheet.grain_tolerance < 90.0
    return find_pair_types(
        part or ele(),
        b_orientations(choices, respetada),
        choices,
        config,
        UTIL,
        how_many,
        MaskCache(),
    )


def test_todo_candidato_queda_a_una_separacion_y_menos_de_dos():
    """El tope de 2·sep es lo que garantiza que el puente no le quita lugar
    a nadie: en un hueco de menos de dos separaciones no entra ninguna pieza."""
    encontrados = tipos()
    assert encontrados, "la L tiene que tener al menos un encastre"
    a = placed_polygon(ele(), Transform.identity())
    for tipo in encontrados:
        b = placed_polygon(ele(), tipo.relative)
        assert SEP - 1e-6 <= a.distance(b) < 2 * SEP, tipo


def test_sin_separacion_no_hay_tipos():
    """Sin separación no hay hueco de 'menos de dos separaciones' donde
    esconder el puente, y el puente le robaría lugar a otra pieza."""
    sin_sep = NestConfig(sep=0.0, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0),
                         mirror=True, resolution=2.0)
    assert tipos(config=sin_sep) == []


def test_encuentra_tipos_con_separaciones_chicas_frente_a_la_resolucion():
    """Los candidatos salen del raster, así que el hueco real puede quedar
    unos píxeles por encima de `sep`; sin deslizar B hacia A eso alcanzaba
    para que NINGÚN candidato pasara `gap < 2 * sep` con sep chico frente a
    la resolución (medido: 0 tipos en sep=2,3 a 1 mm/px y sep=6 a 2 mm/px)."""
    a = placed_polygon(ele(), Transform.identity())
    for sep in (2.0, 3.0, 4.0, 5.0, 8.0, 10.0):
        for res in (1.0, 2.0):
            config = NestConfig(sep=sep, margin=5.0,
                                angles=(0.0, 90.0, 180.0, 270.0),
                                mirror=True, resolution=res)
            encontrados = tipos(config=config)
            assert encontrados, (sep, res)
            for tipo in encontrados:
                b = placed_polygon(ele(), tipo.relative)
                gap = a.distance(b)
                assert sep <= gap < sep + 0.5, (sep, res, gap)


def _hueco_antes_de_acercar(tipo, part, config, cache):
    """El hueco exacto entre A y B donde el raster dejó a B, antes de acercarlo."""
    angle, mirror = tipo.orientation
    a_masks = cache.get(part, 0.0, False, config.resolution, config.sep)
    b_masks = cache.get(part, angle, mirror, config.resolution, config.sep)
    u, v = tipo.offset_px
    donde = Transform(angle, mirror,
                      a_masks.origin[0] + u * config.resolution - b_masks.origin[0],
                      a_masks.origin[1] + v * config.resolution - b_masks.origin[1])
    a = placed_polygon(part, Transform.identity())
    return a.distance(placed_polygon(part, donde))


def test_solo_se_acerca_lo_que_el_raster_pudo_haber_dejado_de_mas():
    """Un candidato a 80 mm de A (medido en la L, sep 8 a 2 mm/px, placa
    1200 x 690) no es un encastre que el raster dejó flojo: acercarlo 66 mm
    armaba otro par, de 924 x 372, que se quedaba con la caja en píxeles del
    candidato (282.112 mm² contra 343.728 reales) y desordenaba la lista."""
    for sep in (2.0, 3.0, 4.0, 5.0, 8.0, 10.0):
        for res in (1.0, 2.0):
            config = NestConfig(sep=sep, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0),
                                mirror=True, resolution=res)
            choices = orientations(LIBRE, config)
            cache = MaskCache()
            for tipo in find_pair_types(ele(), b_orientations(choices, False), choices,
                                        config, (1190.0, 680.0), 6, cache):
                hueco = _hueco_antes_de_acercar(tipo, ele(), config, cache)
                assert hueco < sep + slide_window(sep, res), (
                    sep, res, hueco, tipo.width, tipo.height)


def test_la_caja_con_que_se_ordena_es_la_del_par_de_verdad():
    """`box_area` sale de los píxeles del candidato; después de acercar B,
    la caja exacta sólo puede diferir en lo que se movió B y en la
    inflación de las máscaras, no en un par distinto."""
    choices = orientations(LIBRE, CONFIG)
    encontrados = find_pair_types(ele(), b_orientations(choices, False), choices, CONFIG,
                                  (1190.0, 680.0), 6, MaskCache())
    assert encontrados
    for tipo in encontrados:
        tolerancia = 2 * (tipo.width + tipo.height) * slide_window(SEP, CONFIG.resolution)
        assert abs(tipo.width * tipo.height - tipo.box_area) <= tolerancia, (
            tipo.width, tipo.height, tipo.box_area)


def test_los_tipos_salen_de_menor_a_mayor_caja():
    encontrados = tipos()
    cajas = [t.box_area for t in encontrados]
    assert cajas == sorted(cajas)


def test_la_busqueda_corta_es_prefijo_de_la_larga():
    """Es el contrato que hace a normal prefijo de lento."""
    cortos = tipos(how_many=TIPOS_POR_CLASE["normal"])
    largos = tipos(how_many=TIPOS_POR_CLASE["lento"])
    assert largos[:len(cortos)] == cortos


def test_ningun_tipo_es_congruente_con_otro():
    """El par (A, B en r) y el (A, B en r⁻¹) son la misma pieza vista desde
    el otro miembro: contarlos dos veces gastaba lugares de la lista."""
    encontrados = tipos(how_many=10)
    choices = orientations(LIBRE, CONFIG)
    for i, uno in enumerate(encontrados):
        for otro in encontrados[:i]:
            assert congruence(uno.shape(1), otro.shape(2), choices) is None


def test_con_la_veta_respetada_ningun_b_queda_a_90():
    encontrados = tipos(sheet=CON_VETA)
    assert encontrados
    assert all(t.relative.angle_deg % 180.0 == 0.0 for t in encontrados)


def test_b_orientations_filtra_a_0_y_180_con_la_veta_respetada():
    choices = [(0.0, False), (90.0, False), (180.0, False), (270.0, True)]
    assert b_orientations(choices, grain_respected=True) == [(0.0, False), (180.0, False)]
    assert b_orientations(choices, grain_respected=False) == choices


def test_sin_espejo_ningun_b_queda_espejado():
    sin_espejo = NestConfig(sep=SEP, margin=5.0, angles=(0.0, 90.0, 180.0, 270.0),
                            mirror=False, resolution=2.0)
    encontrados = tipos(config=sin_espejo)
    assert encontrados
    assert not any(t.relative.mirror for t in encontrados)


def test_todo_par_entra_en_el_area_util_en_alguna_orientacion():
    for tipo in tipos():
        w, h = sorted((tipo.width, tipo.height))
        assert w <= min(UTIL) and h <= max(UTIL), tipo


def test_la_compuesta_es_un_solo_poligono_y_conserva_los_agujeros():
    agujero = ((300.0, 20.0), (400.0, 20.0), (400.0, 80.0), (300.0, 80.0))
    con_agujero = ele(holes=(agujero,))
    tipo = tipos(part=con_agujero)[0]

    forma = tipo.shape(99)
    poligono = Polygon(forma.outer, forma.holes)
    assert poligono.is_valid
    assert len(forma.holes) == 2, "el agujero de A y el de B"
    a = placed_polygon(con_agujero, Transform.identity())
    b = placed_polygon(con_agujero, tipo.relative)
    # La compuesta es A, B y un puente chico: el área de más es la del puente.
    assert 0.0 < poligono.area - (a.area + b.area) < 4 * SEP * 2


def test_el_puente_une_dos_poligonos_que_no_se_tocan():
    a = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    b = Polygon([(110, 0), (210, 0), (210, 100), (110, 100)])
    unida = union_with_bridge(a, b)
    assert unida is not None
    outer, holes = unida
    assert Polygon(outer, holes).area > a.area + b.area
    assert holes == ()


def test_el_puente_no_alcanza_a_conectar_todo_devuelve_none():
    """El puente sólo conecta los dos puntos más cercanos: si `a` tiene un
    segundo pedazo lejos, ese pedazo queda sin conectar y la unión ya no es
    un solo polígono."""
    a = MultiPolygon([
        Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
        Polygon([(0, 50), (10, 50), (10, 60), (0, 60)]),
    ])
    b = Polygon([(20, 0), (30, 0), (30, 10), (20, 10)])
    assert union_with_bridge(a, b) is None


def test_solo_se_emparejan_las_clases_repetidas_y_grandes_hasta_dos():
    grande = Part(0, ((0, 0), (500, 0), (500, 400), (0, 400)), (), (0,))
    mediana = Part(2, ((0, 0), (400, 0), (400, 300), (0, 300)), (), (2,))
    otra = Part(4, ((0, 0), (300, 0), (300, 300), (0, 300)), (), (4,))
    listón = Part(6, ((0, 0), (300, 0), (300, 20), (0, 20)), (), (6,))
    sola = Part(8, ((0, 0), (600, 0), (600, 500), (0, 500)), (), (8,))
    identidad = Transform.identity()

    def clase(part, n):
        return Clase(part, tuple(Member(part.id + k, identidad) for k in range(n)))

    clases = [clase(otra, 2), clase(listón, 6), clase(sola, 1),
              clase(mediana, 3), clase(grande, 2)]
    util = 1190.0 * 2430.0

    elegidas = pairable_classes(clases, util, grain_respected=False)

    assert len(elegidas) == MAX_PAIRED_CLASSES
    assert [c.representative.id for c in elegidas] == [0, 2]


def test_con_la_veta_respetada_no_se_empareja_una_clase_con_miembros_girados():
    """Si una copia llega a la representante girada 3°, componerla con un
    par girado otros 3° la deja a 6°, fuera de una tolerancia de 5. Pasa sólo
    con ángulos personalizados, pero pasa, y nadie más lo revisa: `verify`
    no mira la veta."""
    pieza = Part(0, ((0, 0), (500, 0), (500, 400), (0, 400)), (), (0,))
    torcida = Clase(pieza, (Member(0, Transform.identity()),
                            Member(1, Transform(3.0, False, 0.0, 0.0))))
    assert pairable_classes([torcida], 1190.0 * 2430.0, grain_respected=True) == []
    assert pairable_classes([torcida], 1190.0 * 2430.0, grain_respected=False) == [torcida]


@pytest.mark.skipif(
    not BANQUETA.exists(),
    reason=f"falta {BANQUETA}: es un archivo de diseño del usuario y no se "
           "versiona (ver .gitignore). Copiá 'BANQUETA ALTA NESTING.ai' ahí.",
)
def test_sobre_el_marco_de_la_banqueta_aparecen_el_diagonal_y_el_apilado():
    from nesting.io.ai_reader import read_ai
    from nesting.pipeline import prepare_parts

    piezas, _, _ = prepare_parts(read_ai(BANQUETA))
    marco = max(piezas, key=lambda p: p.area)
    config = NestConfig(sep=8.0, margin=5.0, angles=tuple(i * 45.0 for i in range(8)),
                        mirror=True, resolution=1.0)
    placa = Sheet(1220.0, 2440.0, grain_tolerance=180.0)
    choices = orientations(placa, config)
    encontrados = find_pair_types(marco, choices, choices, config, (1210.0, 2430.0),
                                  TIPOS_POR_CLASE["normal"], MaskCache())

    def hay(w, h):
        return any(
            sorted((t.width, t.height)) == pytest.approx(sorted((w, h)), abs=5.0)
            for t in encontrados
        )

    assert hay(1511.0, 560.0), [(round(t.width), round(t.height)) for t in encontrados]
    assert hay(1055.0, 879.0), [(round(t.width), round(t.height)) for t in encontrados]
