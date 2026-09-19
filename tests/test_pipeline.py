import pytest

from nesting.io.dxf_reader import Drawing
from nesting.model.entities import Arc, Circle, Line, Style
from nesting.model.part import Part
from nesting.pipeline import OpenContourError, discard_plate_outline, prepare_parts

STYLE = Style(aci=7, rgb=(255, 255, 255), layer="0")


def square_lines(x0, y0, side):
    c = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)]
    return [Line(c[i], c[(i + 1) % 4], STYLE) for i in range(4)]


def test_four_loose_lines_become_one_part():
    parts, warnings, _ = prepare_parts(Drawing(entities=square_lines(0, 0, 100)))
    assert len(parts) == 1
    assert parts[0].holes == ()
    assert warnings == []


def test_a_circle_becomes_one_part():
    parts, _, _ = prepare_parts(Drawing(entities=[Circle((0.0, 0.0), 50.0, STYLE)]))
    assert len(parts) == 1
    assert parts[0].outer_area == pytest.approx(3.14159 * 50.0**2, rel=1e-3)


def test_a_circle_inside_a_square_becomes_a_hole():
    entities = square_lines(0, 0, 200) + [Circle((100.0, 100.0), 30.0, STYLE)]
    parts, _, _ = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    assert len(parts[0].holes) == 1
    assert parts[0].area < parts[0].outer_area


def test_two_arcs_forming_a_circle_chain_together():
    entities = [
        Arc((0.0, 0.0), 50.0, 0.0, 180.0, STYLE),
        Arc((0.0, 0.0), 50.0, 180.0, 360.0, STYLE),
    ]
    parts, _, _ = prepare_parts(Drawing(entities=entities))
    assert len(parts) == 1


def test_an_open_contour_raises_with_the_gap_size():
    entities = square_lines(0, 0, 100)[:3]   # falta un lado
    with pytest.raises(OpenContourError) as info:
        prepare_parts(Drawing(entities=entities))
    message = str(info.value)
    assert "100" in message, "informa el tamano del hueco"
    assert "--tol-cierre" in message


def test_duplicate_lines_produce_a_warning_but_still_work():
    entities = square_lines(0, 0, 100) + [square_lines(0, 0, 100)[0]]
    parts, warnings, _ = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    assert any("duplicad" in w for w in warnings)


def test_reader_warnings_are_carried_through():
    drawing = Drawing(entities=square_lines(0, 0, 100), warnings=["se ignoraron 1 TEXT"])
    _, warnings, _ = prepare_parts(drawing)
    assert "se ignoraron 1 TEXT" in warnings


def test_entity_ids_point_back_into_the_drawing():
    drawing = Drawing(entities=square_lines(0, 0, 100))
    parts, _, _ = prepare_parts(drawing)
    assert sorted(parts[0].entity_ids) == [0, 1, 2, 3]


def test_an_empty_drawing_produces_no_parts():
    parts, _, _ = prepare_parts(Drawing(entities=[]))
    assert parts == []


def test_a_collinear_contour_is_skipped_with_a_warning_instead_of_corrupting_the_job():
    """Arreglos finales, punto 1: un anillo colineal (área cero) junto a una
    pieza legítima ya no debe hacer perder el trabajo entero -- se saltea,
    con un aviso, y la pieza real se sigue procesando normalmente."""
    collinear = [
        Line((0.0, 0.0), (100.0, 0.0), STYLE),
        Line((100.0, 0.0), (50.0, 0.0), STYLE),
        Line((50.0, 0.0), (0.0, 0.0), STYLE),
    ]
    entities = square_lines(0, 0, 200) + collinear
    parts, warnings, _ = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    assert sorted(parts[0].entity_ids) == [0, 1, 2, 3]
    assert any("área" in w for w in warnings)


def test_a_two_point_loose_end_is_skipped_with_a_warning_alongside_a_good_part():
    """Arreglo archivos reales, problema 1: un tramo suelto de 2 puntos (una
    recta que no puede encerrar área) no debe tirar abajo una pieza real que
    sí cierra -- se saltea con aviso, en vez de lanzar OpenContourError."""
    entities = square_lines(0, 0, 100) + [Line((500.0, 500.0), (512.0, 500.0), STYLE)]
    parts, warnings, _ = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    assert sorted(parts[0].entity_ids) == [0, 1, 2, 3]
    assert any("suelto" in w for w in warnings)


def test_several_loose_ends_are_counted_correctly_in_the_warning():
    loose = [
        Line((500.0, 500.0), (512.0, 500.0), STYLE),
        Line((600.0, 600.0), (600.024, 600.0), STYLE),
        Line((700.0, 700.0), (700.0, 712.0), STYLE),
    ]
    entities = square_lines(0, 0, 100) + loose
    parts, warnings, _ = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    warning = next(w for w in warnings if "suelto" in w)
    assert "3" in warning


def test_a_real_open_chain_of_three_or_more_points_still_raises():
    """La protección que no hay que perder: una cadena que sí tenía forma
    (3+ puntos) y no cierra sigue siendo un error duro, porque probablemente
    le falte un tramo a una pieza real y cortarla incompleta arruina material."""
    entities = [
        Line((0.0, 0.0), (100.0, 0.0), STYLE),
        Line((100.0, 0.0), (100.0, 100.0), STYLE),
    ]
    with pytest.raises(OpenContourError):
        prepare_parts(Drawing(entities=entities))


def test_a_drawing_of_only_loose_ends_returns_no_parts_without_raising():
    entities = [
        Line((500.0, 500.0), (512.0, 500.0), STYLE),
        Line((600.0, 600.0), (600.024, 600.0), STYLE),
    ]
    parts, warnings, _ = prepare_parts(Drawing(entities=entities))

    assert parts == []
    assert any("suelto" in w for w in warnings)


def _rect_part(width, height, holes=(), part_id=0):
    outer = ((0.0, 0.0), (width, 0.0), (width, height), (0.0, height))
    return Part(id=part_id, outer=outer, holes=holes, entity_ids=(part_id,))


def test_a_part_matching_the_plate_size_exactly_is_discarded():
    """Arreglo archivos reales, problema 2: un rectángulo dibujado del tamaño
    exacto de la placa (ancho x alto de material) es el contorno de placa que
    el usuario traza para previsualizar el acomodo, no una pieza."""
    parts = [_rect_part(1830.0, 2600.0), _rect_part(300.0, 200.0, part_id=1)]
    kept, discarded = discard_plate_outline(parts, sheet_w=1830.0, sheet_h=2600.0)

    assert len(discarded) == 1
    assert [p.id for p in kept] == [1]


def test_a_plate_sized_rectangle_rotated_is_also_discarded():
    """La placa puede estar dibujada acostada o parada: alto x ancho también
    cuenta."""
    parts = [_rect_part(2600.0, 1830.0)]
    kept, discarded = discard_plate_outline(parts, sheet_w=1830.0, sheet_h=2600.0)

    assert len(discarded) == 1
    assert kept == []


def test_a_rectangle_of_a_different_size_is_not_discarded():
    parts = [_rect_part(500.0, 400.0)]
    kept, discarded = discard_plate_outline(parts, sheet_w=1830.0, sheet_h=2600.0)

    assert len(discarded) == 0
    assert kept == parts


def test_a_non_rectangular_part_spanning_the_plate_bbox_is_not_discarded():
    """Una L cuya caja envolvente coincide con la placa no es un rectángulo,
    así que no puede confundirse con el contorno de placa."""
    l_shape = (
        (0.0, 0.0), (1830.0, 0.0), (1830.0, 100.0),
        (100.0, 100.0), (100.0, 2600.0), (0.0, 2600.0),
    )
    parts = [Part(id=0, outer=l_shape, holes=(), entity_ids=(0,))]
    kept, discarded = discard_plate_outline(parts, sheet_w=1830.0, sheet_h=2600.0)

    assert len(discarded) == 0
    assert kept == parts


def test_a_plate_sized_rectangle_with_holes_is_not_discarded():
    """Una pieza rectangular del tamaño de la placa pero con agujeros es una
    pieza de verdad -- el contorno de placa que dibuja el usuario para
    previsualizar no tiene agujeros."""
    hole = ((800.0, 1200.0), (900.0, 1200.0), (900.0, 1300.0), (800.0, 1300.0))
    parts = [_rect_part(1830.0, 2600.0, holes=(hole,))]
    kept, discarded = discard_plate_outline(parts, sheet_w=1830.0, sheet_h=2600.0)

    assert len(discarded) == 0
    assert kept == parts


def test_a_normal_job_without_a_plate_outline_loses_no_parts():
    parts = [_rect_part(300.0, 200.0), _rect_part(150.0, 150.0, part_id=1)]
    kept, discarded = discard_plate_outline(parts, sheet_w=1830.0, sheet_h=2600.0)

    assert len(discarded) == 0
    assert kept == parts


# --- Qué se descartó, dibujable ----------------------------------------------


def test_prepare_parts_reports_duplicate_entities_as_discards():
    """El caso del archivo real: un lado de una pieza dibujado dos veces.

    Lo que el usuario necesita ver no es "se descartaron 2" sino dónde están
    esos 12 mm, porque a la escala del dibujo entero son invisibles.
    """
    entities = square_lines(0, 0, 100) + [square_lines(0, 0, 100)[0]]

    parts, warnings, discards = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    duplicates = [d for d in discards if d.reason == "duplicada"]
    assert len(duplicates) == 1
    assert duplicates[0].points == ((0.0, 0.0), (100.0, 0.0))
    assert any("duplicadas" in w for w in warnings)


def test_a_loose_two_point_segment_becomes_a_discard_with_its_length():
    """El largo es el dato que decide: 12 mm es un lado que sobró, 0.024 mm es
    un vértice repetido. Son problemas distintos y el usuario los trata
    distinto, así que el detalle los distingue."""
    entities = square_lines(0, 0, 100) + [Line((500.0, 500.0), (512.0, 500.0), STYLE)]

    _, _, discards = prepare_parts(Drawing(entities=entities))

    loose = [d for d in discards if d.reason == "suelta"]
    assert len(loose) == 1
    assert loose[0].points == ((500.0, 500.0), (512.0, 500.0))
    assert "12.000 mm" in loose[0].detail


def test_a_degenerate_contour_becomes_a_discard():
    collinear = [
        Line((0.0, 0.0), (100.0, 0.0), STYLE),
        Line((100.0, 0.0), (50.0, 0.0), STYLE),
        Line((50.0, 0.0), (0.0, 0.0), STYLE),
    ]
    entities = square_lines(500, 500, 100) + collinear

    parts, warnings, discards = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    assert [d.reason for d in discards] == ["area_nula"]
    assert any("área nula" in w for w in warnings)


def test_reader_discards_travel_through_prepare_parts_untouched():
    """`prepare_parts` copia los avisos del lector; los descartes tienen que
    viajar igual, o el diagnóstico perdería todo lo que detectó el lector."""
    from nesting.model.discard import Discard

    drawing = Drawing(entities=square_lines(0, 0, 100))
    drawing.discards.append(Discard(reason="no_es_curva", detail="DimLinear"))

    _, _, discards = prepare_parts(drawing)

    assert [d.detail for d in discards] == ["DimLinear"]


def test_prepare_parts_does_not_mutate_the_drawing_it_was_given():
    """Misma política que con `warnings`: se copia, no se escribe encima.

    El `Drawing` sigue vivo después -- el escritor de DXF lo usa para sacar
    los colores originales -- así que ensuciarlo con descartes de una etapa
    posterior lo dejaría distinto de lo que el lector produjo.
    """
    entities = square_lines(0, 0, 100) + [square_lines(0, 0, 100)[0]]
    drawing = Drawing(entities=entities)

    _, _, discards = prepare_parts(drawing)

    assert discards, "la prueba no sirve si no se descartó nada"
    assert drawing.discards == []


def test_the_discarded_plate_outline_comes_back_whole_not_counted():
    parts = [_rect_part(1830.0, 2600.0), _rect_part(300.0, 200.0, part_id=1)]

    kept, discarded = discard_plate_outline(parts, sheet_w=1830.0, sheet_h=2600.0)

    assert [p.id for p in kept] == [1]
    assert [p.id for p in discarded] == [0]
