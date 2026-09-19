"""El registro de motivos de descarte y su tipo."""

import pytest

from nesting.model.discard import DISCARD_STYLES, Discard


def test_every_reason_in_the_registry_has_a_label_and_a_colour():
    for reason, style in DISCARD_STYLES.items():
        assert style.label, f"{reason} no tiene etiqueta"
        assert len(style.color) == 3
        assert all(0 <= channel <= 255 for channel in style.color)


def test_colours_are_distinguishable_from_each_other():
    """Dos motivos del mismo color harían ilegible el diagnóstico.

    El punto entero del dibujo es que el usuario distinga de un vistazo por
    qué se descartó cada cosa, así que dos motivos no pueden compartir color.
    """
    colors = [style.color for style in DISCARD_STYLES.values()]
    assert len(set(colors)) == len(colors)


def test_a_discard_with_an_unknown_reason_is_rejected():
    """Un motivo sin entrada en el registro no se podría ni etiquetar ni pintar.

    Fallar acá, al construirlo, señala el sitio que lo emitió; dejarlo pasar
    lo haría reventar mucho más tarde, dentro del dibujante.
    """
    with pytest.raises(ValueError, match="motivo de descarte desconocido"):
        Discard(reason="inventado", points=(), detail="")


def test_a_discard_keeps_its_geometry_and_its_detail():
    discard = Discard(
        reason="suelta", points=((0.0, 0.0), (12.0, 0.0)), detail="12.000 mm"
    )
    assert discard.points == ((0.0, 0.0), (12.0, 0.0))
    assert discard.detail == "12.000 mm"
    assert discard.style.label


def test_a_discard_without_geometry_is_allowed():
    """Una cota de Rhino o un tipo DXF no soportado no tienen contorno en XY.

    Se cuentan y se listan igual: que no se puedan marcar sobre el plano no
    es razón para ocultarlos, porque el aviso de texto sí los menciona.
    """
    discard = Discard(reason="no_es_curva", points=(), detail="DimLinear")
    assert discard.points == ()
    assert not discard.has_geometry


def test_centroid_of_a_segment_is_its_middle():
    discard = Discard(reason="suelta", points=((0.0, 0.0), (10.0, 4.0)))
    assert discard.centroid == pytest.approx((5.0, 2.0))


def test_centroid_of_a_discard_without_geometry_is_none():
    assert Discard(reason="no_es_curva", points=()).centroid is None


def test_a_ring_discard_closes_its_own_loop():
    """Un contorno cerrado se guarda sin repetir el primer punto al final,
    igual que `Contour`. Dibujarlo tal cual deja el ultimo lado sin trazar:
    el rectangulo de placa salia con tres lados y el cuarto faltando, que se
    lee como geometria rota y no como lo que es.
    """
    ring = Discard(
        reason="contorno_placa",
        points=((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)),
        closed=True,
    )
    assert ring.path == (
        (0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0),
    )


def test_an_open_discard_is_not_closed_behind_its_back():
    """Un tramo suelto de 12 mm es una recta, no un triangulo degenerado."""
    segment = Discard(reason="suelta", points=((0.0, 0.0), (12.0, 0.0)))
    assert segment.path == ((0.0, 0.0), (12.0, 0.0))


def test_a_discard_without_geometry_has_an_empty_path():
    assert Discard(reason="no_es_curva", points=()).path == ()


def test_a_ring_already_carrying_its_closing_point_is_not_duplicated():
    """Las entidades duplicadas llegan ya cerradas desde `_flatten_closed`.

    Repetirles el primer punto otra vez dejaria un segmento de largo cero al
    final, que Pillow dibuja como un punto suelto encima del vertice.
    """
    ring = Discard(
        reason="duplicada",
        points=((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)),
        closed=True,
    )
    assert ring.path == ring.points
