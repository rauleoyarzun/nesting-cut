"""Qué piezas son copias de la misma forma, según lo que la corrida permite."""

from nesting.engine.iguales import (
    AREA_TOLERANCE_MM2,
    Clase,
    congruence,
    find_classes,
    fingerprint,
)
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import orientations
from nesting.geometry.transform import apply_points
from nesting.geometry.verify import placed_polygon
from nesting.model.entities import Transform
from nesting.model.part import Part
from nesting.model.sheet import Sheet

# Una L con los brazos de distinto largo: espejarla NO es girarla. Con los
# brazos iguales, la espejada sería la girada 90° y el test del espejo
# pasaría por la razón equivocada.
ELE = ((0.0, 0.0), (300.0, 0.0), (300.0, 60.0), (60.0, 60.0), (60.0, 200.0), (0.0, 200.0))

LIBRE = Sheet(2000.0, 2000.0, grain_tolerance=180.0)
CON_VETA = Sheet(2000.0, 2000.0, grain_tolerance=5.0)
CUATRO = NestConfig(angles=(0.0, 90.0, 180.0, 270.0), mirror=True)
SIN_ESPEJO = NestConfig(angles=(0.0, 90.0, 180.0, 270.0), mirror=False)


def pieza(part_id: int, t: Transform = Transform.identity(), holes=()) -> Part:
    return Part(
        part_id,
        apply_points(t, ELE),
        tuple(apply_points(t, h) for h in holes),
        (part_id,),
    )


def copias():
    """La original, una trasladada, una girada 90° y una espejada, todas
    dibujadas en otro lugar de la hoja como las dibujaría un usuario."""
    return [
        pieza(0),
        pieza(1, Transform(0.0, False, 1500.0, 40.0)),
        pieza(2, Transform(90.0, False, 700.0, 900.0)),
        pieza(3, Transform(0.0, True, 2500.0, -300.0)),
    ]


def ids(clase: Clase) -> list[int]:
    return [m.part_id for m in clase.members]


def test_con_la_corrida_libre_las_cuatro_son_de_la_misma_clase():
    clases = find_classes(copias(), orientations(LIBRE, CUATRO))

    assert len(clases) == 1
    assert ids(clases[0]) == [0, 1, 2, 3]
    assert clases[0].representative.id == 0


def test_con_la_veta_respetada_la_girada_90_no_es_igual():
    """Llevarla sobre la otra exigiría girarla 90°, que la veta prohíbe."""
    clases = find_classes(copias(), orientations(CON_VETA, CUATRO))

    grupos = sorted(ids(c) for c in clases)
    assert [2] in grupos
    assert [0, 1, 3] in grupos


def test_sin_espejo_la_espejada_no_es_igual():
    clases = find_classes(copias(), orientations(LIBRE, SIN_ESPEJO))

    grupos = sorted(ids(c) for c in clases)
    assert [3] in grupos
    assert [0, 1, 2] in grupos


def test_g_lleva_cada_miembro_sobre_la_representante():
    """Es la propiedad que la Tarea 4 necesita: colocar a un miembro con
    `T ∘ g` lo pone exactamente donde `T` pondría a la representante."""
    piezas = copias()
    por_id = {p.id: p for p in piezas}
    clase = find_classes(piezas, orientations(LIBRE, CUATRO))[0]
    objetivo = placed_polygon(clase.representative, Transform.identity())

    for miembro in clase.members:
        movida = placed_polygon(por_id[miembro.part_id], miembro.to_representative)
        assert movida.symmetric_difference(objetivo).area < AREA_TOLERANCE_MM2


def test_la_representante_se_lleva_a_si_misma_con_la_identidad():
    clase = find_classes(copias(), orientations(LIBRE, CUATRO))[0]
    assert clase.members[0].to_representative == Transform.identity()


def test_un_agujero_de_mas_cambia_la_huella():
    """La huella descarta sin geometría exacta: la misma L con un agujero no
    puede ni llegar a compararse con la maciza."""
    agujero = ((100.0, 10.0), (140.0, 10.0), (140.0, 40.0), (100.0, 40.0))
    maciza, agujereada = pieza(0), pieza(1, holes=(agujero,))

    assert fingerprint(maciza) != fingerprint(agujereada)
    assert len(find_classes([maciza, agujereada], orientations(LIBRE, CUATRO))) == 2


def test_la_misma_huella_no_alcanza_para_ser_iguales():
    """La espejada tiene exactamente la misma huella que la original (misma
    área, mismo perímetro, mismos agujeros), y sin espejo NO es igual: el
    juez es `congruence`, no la huella."""
    original = pieza(0)
    espejada = pieza(3, Transform(0.0, True, 2500.0, -300.0))

    assert fingerprint(original) == fingerprint(espejada)
    assert congruence(espejada, original, orientations(LIBRE, SIN_ESPEJO)) is None
    assert congruence(espejada, original, orientations(LIBRE, CUATRO)) is not None


def test_piezas_distintas_quedan_en_clases_distintas_y_en_orden():
    chica = Part(9, ((0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0)), (), (9,))
    clases = find_classes([pieza(0), chica, pieza(1, Transform(0.0, False, 900.0, 0.0))],
                          orientations(LIBRE, CUATRO))

    assert [ids(c) for c in clases] == [[0, 1], [9]]
