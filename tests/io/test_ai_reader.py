import pytest

from nesting.io.ai_reader import PT_TO_MM, cmyk_to_rgb, read_ai
from nesting.model.entities import Bezier, Line, Polyline

HEADER = "%!PS-Adobe-3.0\n%%BeginSetup\njunk m junk l\n%%EndSetup\n"
TRAILER = "%%Trailer\n999 999 m 999 999 l\n%%EOF\n"


def write_ai(tmp_path, body, name="t.ai"):
    path = tmp_path / name
    path.write_text(HEADER + body + TRAILER, encoding="latin-1")
    return path


def only_contour(drawing):
    """Los vertices del unico contorno del dibujo.

    Un subtrazo de rectas sale como UNA polilinea sobre sus propios vertices
    (ver `_entities_of_subpath`), asi que contar vertices es lo que contar
    entidades `Line` sueltas decia antes: cuantas esquinas sobrevivieron.
    """
    contours = [e for e in drawing.entities if isinstance(e, Polyline)]
    assert len(contours) == 1, f"se esperaba un solo contorno, hay {len(contours)}"
    return contours[0].points


def test_cmyk_to_rgb_black_and_white():
    assert cmyk_to_rgb(0.0, 0.0, 0.0, 1.0) == (0, 0, 0)
    assert cmyk_to_rgb(0.0, 0.0, 0.0, 0.0) == (255, 255, 255)


def test_cmyk_to_rgb_pure_cyan():
    assert cmyk_to_rgb(1.0, 0.0, 0.0, 0.0) == (0, 255, 255)


def test_reads_a_simple_closed_triangle(tmp_path):
    body = "0 0 m\n72 0 L\n72 72 L\ns\n"
    drawing = read_ai(write_ai(tmp_path, body))

    contour = only_contour(drawing)
    assert len(contour) == 3, "los tres vertices del triangulo"
    assert drawing.entities[0].closed, "el operador 's' cierra el trazo"
    assert contour[0] == pytest.approx((0.0, 0.0))
    assert contour[1] == pytest.approx((25.4, 0.0)), "72 pt son 25.4 mm"


def test_an_uppercase_paint_operator_does_not_close_the_path(tmp_path):
    body = "0 0 m\n72 0 L\n72 72 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert not drawing.entities[0].closed
    assert len(only_contour(drawing)) == 3, "dos tramos, tres vertices, sin cierre"


def test_points_are_converted_to_millimetres(tmp_path):
    body = "0 0 m\n144 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert drawing.entities[0].end[0] == pytest.approx(144 * PT_TO_MM)
    assert drawing.source_units == "pt"


def test_a_curveto_becomes_a_bezier(tmp_path):
    body = "0 0 m\n10 20 30 20 40 0 C\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))

    curves = [e for e in drawing.entities if isinstance(e, Bezier)]
    assert len(curves) == 1
    assert curves[0].p0 == pytest.approx((0.0, 0.0))
    assert curves[0].p3 == pytest.approx((40 * PT_TO_MM, 0.0))


def test_the_v_operator_uses_the_current_point_as_first_control(tmp_path):
    body = "0 0 m\n30 20 40 0 v\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    curve = drawing.entities[0]
    assert curve.p0 == pytest.approx(curve.p1), "el primer control es el punto actual"


def test_the_y_operator_uses_the_endpoint_as_second_control(tmp_path):
    body = "0 0 m\n10 20 40 0 y\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    curve = drawing.entities[0]
    assert curve.p3 == pytest.approx(curve.p2), "el segundo control es el punto final"


def test_the_stroke_colour_is_captured(tmp_path):
    body = "1.0 0.0 0.0 0.0 K\n0 0 m\n72 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert drawing.entities[0].style.rgb == (0, 255, 255)


def test_the_layer_name_encodes_the_colour(tmp_path):
    body = "1.0 0.0 0.0 0.0 K\n0 0 m\n72 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert drawing.entities[0].style.layer == "AI_00FFFF"


def test_different_colours_land_on_different_layers(tmp_path):
    body = (
        "1.0 0.0 0.0 0.0 K\n0 0 m\n72 0 L\nS\n"
        "0.0 1.0 0.0 0.0 K\n0 100 m\n72 100 L\nS\n"
    )
    drawing = read_ai(write_ai(tmp_path, body))
    assert len({e.style.layer for e in drawing.entities}) == 2


def test_a_grey_stroke_is_captured(tmp_path):
    body = "0.5 G\n0 0 m\n72 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    rgb = drawing.entities[0].style.rgb
    assert rgb[0] == rgb[1] == rgb[2]
    assert 120 < rgb[0] < 136


def test_the_prologue_and_trailer_are_ignored(tmp_path):
    """El prologo trae tokens que parecen geometria; no deben entrar."""
    body = "0 0 m\n72 0 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))
    assert len(drawing.entities) == 1


def test_several_subpaths_each_close_on_their_own(tmp_path):
    body = (
        "0 0 m\n72 0 L\n72 72 L\ns\n"
        "200 200 m\n272 200 L\n272 272 L\ns\n"
    )
    drawing = read_ai(write_ai(tmp_path, body))
    assert len(drawing.entities) == 2, "un contorno por subtrazo, no uno por segmento"


def test_an_ai_file_without_geometry_reads_as_empty(tmp_path):
    drawing = read_ai(write_ai(tmp_path, ""))
    assert drawing.entities == []


def test_the_result_flows_through_the_whole_pipeline(tmp_path):
    """Un cuadrado en .ai tiene que salir como una pieza."""
    from nesting.pipeline import prepare_parts

    body = "0 0 m\n288 0 L\n288 288 L\n0 288 L\ns\n"
    parts, _, _ = prepare_parts(read_ai(write_ai(tmp_path, body)))

    assert len(parts) == 1
    assert parts[0].outer_area == pytest.approx((288 * PT_TO_MM) ** 2, rel=0.01)


# --- El %%BoundingBox declarado en la cabecera es el borde de la mesa de
# trabajo que CorelDRAW exporta como geometria real, no una pieza. Estos
# tests cubren cuando el lector debe descartarlo (y avisar) y, sobre todo,
# cuando NO debe hacerlo. ---

BBOX_PT = (0, 0, 100, 200)


def write_ai_with_bbox(tmp_path, body, bbox=BBOX_PT, name="bbox.ai"):
    header = (
        "%!PS-Adobe-3.0\n"
        f"%%BoundingBox:{bbox[0]} {bbox[1]} {bbox[2]} {bbox[3]}\n"
        "%%BeginSetup\njunk m junk l\n%%EndSetup\n"
    )
    path = tmp_path / name
    path.write_text(header + body + TRAILER, encoding="latin-1")
    return path


def test_a_rectangle_matching_the_declared_bbox_is_discarded_with_a_warning(tmp_path):
    body = (
        "0 0 m\n100 0 L\n100 200 L\n0 200 L\ns\n"  # el borde de la mesa
        "40 40 m\n60 40 L\n60 60 L\n40 60 L\ns\n"  # una pieza chica adentro
    )
    drawing = read_ai(write_ai_with_bbox(tmp_path, body))

    corners = only_contour(drawing)
    assert len(corners) == 4, "solo la pieza chica, no el rectangulo de la mesa"
    assert all(max(abs(c) for c in corner) < 30 for corner in corners), (
        "ningun vertice remanente debe pertenecer al rectangulo de la mesa"
    )
    assert len(drawing.warnings) == 1
    assert "rectángulo" in drawing.warnings[0]
    assert "BoundingBox" in drawing.warnings[0]


def test_a_non_rectangular_shape_spanning_the_bbox_is_not_discarded(tmp_path):
    """Un triangulo que toca los cuatro bordes del bbox no es un rectangulo."""
    body = "0 0 m\n100 0 L\n0 200 L\ns\n"
    drawing = read_ai(write_ai_with_bbox(tmp_path, body))

    assert len(only_contour(drawing)) == 3
    assert drawing.warnings == []


def test_an_l_shape_reaching_all_four_edges_is_not_discarded(tmp_path):
    """Una forma en L con seis esquinas tampoco es un rectangulo."""
    body = "0 0 m\n100 0 L\n100 100 L\n50 100 L\n50 200 L\n0 200 L\ns\n"
    drawing = read_ai(write_ai_with_bbox(tmp_path, body))

    assert len(only_contour(drawing)) == 6
    assert drawing.warnings == []


def test_a_rectangle_matching_only_three_sides_is_not_discarded(tmp_path):
    body = "0 0 m\n80 0 L\n80 200 L\n0 200 L\ns\n"  # el lado derecho esta adentro
    drawing = read_ai(write_ai_with_bbox(tmp_path, body))

    assert len(only_contour(drawing)) == 4
    assert drawing.warnings == []


def test_a_correctly_sized_but_shifted_rectangle_is_not_discarded(tmp_path):
    body = "10 10 m\n110 10 L\n110 210 L\n10 210 L\ns\n"
    drawing = read_ai(write_ai_with_bbox(tmp_path, body))

    assert len(only_contour(drawing)) == 4
    assert drawing.warnings == []


def test_no_bbox_declared_means_nothing_is_discarded(tmp_path):
    body = "0 0 m\n100 0 L\n100 200 L\n0 200 L\ns\n"
    drawing = read_ai(write_ai(tmp_path, body))  # HEADER no declara %%BoundingBox

    assert len(only_contour(drawing)) == 4
    assert drawing.warnings == []


def test_a_rotated_rectangle_enclosing_the_bbox_is_not_discarded(tmp_path):
    """Un rombo (rectangulo rotado) que envuelve el mismo bbox no esta
    alineado a los ejes: no debe descartarse."""
    body = "50 0 m\n100 100 L\n50 200 L\n0 100 L\ns\n"
    drawing = read_ai(write_ai_with_bbox(tmp_path, body))

    assert len(only_contour(drawing)) == 4
    assert drawing.warnings == []


def test_the_canvas_border_is_recorded_as_a_discard_with_its_rectangle(tmp_path):
    """El borde de la mesa es la marca MÁS grande del diagnóstico y la que más
    tranquiliza: el usuario ve que lo que se tiró es el marco, no una pieza."""
    body = (
        "0 0 m\n100 0 L\n100 200 L\n0 200 L\ns\n"
        "40 40 m\n60 40 L\n60 60 L\n40 60 L\ns\n"
    )
    drawing = read_ai(write_ai_with_bbox(tmp_path, body))

    discards = [d for d in drawing.discards if d.reason == "borde_lienzo"]
    assert len(discards) == 1
    xs = [p[0] for p in discards[0].points]
    ys = [p[1] for p in discards[0].points]
    # El cuerpo del .ai está en puntos PostScript; el descarte sale en mm,
    # como toda la geometría que cruza la frontera del lector.
    assert (min(xs), max(xs)) == pytest.approx((0.0, 100.0 * PT_TO_MM))
    assert (min(ys), max(ys)) == pytest.approx((0.0, 200.0 * PT_TO_MM))


def test_a_file_without_a_canvas_border_records_no_discards(tmp_path):
    body = "40 40 m\n60 40 L\n60 60 L\n40 60 L\ns\n"
    assert read_ai(write_ai_with_bbox(tmp_path, body)).discards == []


# --- Un subtrazo de .ai es UN trazo dibujado: los segmentos que lo forman
# estan unidos en el archivo original. Partirlo en una entidad suelta por
# segmento llega intacto al DXF de salida, donde cada recta queda como una
# entidad LINE independiente: la maquina ve tramos sueltos en vez del
# contorno de una pieza, y el dibujo muestra dos nodos superpuestos en cada
# vertice. ---


def test_a_closed_subpath_of_straight_segments_is_one_polyline(tmp_path):
    from nesting.model.entities import Polyline

    body = "0 0 m\n72 0 L\n72 72 L\n0 72 L\ns\n"
    drawing = read_ai(write_ai(tmp_path, body))

    assert len(drawing.entities) == 1, "un trazo dibujado, una entidad"
    polyline = drawing.entities[0]
    assert isinstance(polyline, Polyline)
    assert polyline.closed
    assert [(round(x, 9), round(y, 9)) for x, y in polyline.points] == [
        (0.0, 0.0), (25.4, 0.0), (25.4, 25.4), (0.0, 25.4)
    ], "los 4 vertices del original, sin repetir el de cierre"


def test_an_open_subpath_of_several_segments_is_one_open_polyline(tmp_path):
    from nesting.model.entities import Polyline

    body = "0 0 m\n72 0 L\n72 72 L\nS\n"
    drawing = read_ai(write_ai(tmp_path, body))

    assert len(drawing.entities) == 1
    assert isinstance(drawing.entities[0], Polyline)
    assert not drawing.entities[0].closed
    assert len(drawing.entities[0].points) == 3


def test_a_subpath_mixing_lines_and_curves_stays_end_to_end(tmp_path):
    """No hay entidad DXF que mezcle rectas y curvas, asi que un trazo mixto
    sale como varias; lo que no puede pasar es que se corte la cadena."""
    from nesting.model.entities import Bezier, Polyline

    body = "0 0 m\n72 0 L\n72 72 L\n100 100 130 100 144 72 C\n144 0 L\ns\n"
    drawing = read_ai(write_ai(tmp_path, body))

    kinds = [type(e).__name__ for e in drawing.entities]
    assert kinds == ["Polyline", "Bezier", "Polyline"], kinds

    def ends(entity):
        if isinstance(entity, Bezier):
            return entity.p0, entity.p3
        if isinstance(entity, Polyline):
            return entity.points[0], entity.points[-1]
        return entity.start, entity.end

    for before, after in zip(drawing.entities, drawing.entities[1:]):
        assert ends(before)[1] == pytest.approx(ends(after)[0]), "la cadena no se corta"
    first, last = ends(drawing.entities[0])[0], ends(drawing.entities[-1])[1]
    assert last == pytest.approx(first), "el operador 's' cierra el trazo"
