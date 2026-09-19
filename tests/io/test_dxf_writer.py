import ezdxf
import pytest

from nesting.io.dxf_reader import read_dxf
from nesting.io.dxf_writer import SHEET_LAYER, write_dxf
from nesting.model.entities import Arc, Bezier, Circle, Line, Polyline, Style, Transform
from nesting.model.part import Part, Placement

STYLE = Style(aci=3, rgb=(0, 255, 0), layer="CORTE")


def drawing_with(entities):
    from nesting.io.dxf_reader import Drawing
    return Drawing(entities=list(entities), source_units="mm", warnings=[])


def square_part(part_id, side):
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (side, 0.0), (side, side), (0.0, side)),
        holes=(),
        entity_ids=(0, 1, 2, 3),
    )


def square_entities(side):
    corners = [(0.0, 0.0), (side, 0.0), (side, side), (0.0, side)]
    return [
        Line(corners[i], corners[(i + 1) % 4], STYLE) for i in range(4)
    ]


def read_back(path):
    return ezdxf.readfile(str(path))


def test_writes_a_sheet_rectangle_on_its_own_layer(tmp_path):
    out = tmp_path / "out.dxf"
    write_dxf(out, drawing_with([]), [], [], sheet_w=1830.0, sheet_h=2600.0)

    msp = read_back(out).modelspace()
    rectangles = [e for e in msp if e.dxf.layer == SHEET_LAYER]
    assert len(rectangles) == 1


def test_one_rectangle_per_sheet_used(tmp_path):
    out = tmp_path / "out.dxf"
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [
        Placement(0, 0, Transform(0.0, False, 10.0, 10.0)),
        Placement(1, 2, Transform(0.0, False, 10.0, 10.0)),
    ]
    write_dxf(out, drawing_with(square_entities(100.0)), parts, placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    rectangles = [e for e in msp if e.dxf.layer == SHEET_LAYER]
    assert len(rectangles) == 3, "placas 0, 1 y 2 aunque la 1 este vacia"


def test_parts_are_translated_to_their_placement(tmp_path):
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    placements = [Placement(0, 0, Transform(0.0, False, 500.0, 300.0))]
    write_dxf(out, drawing_with(entities), [square_part(0, 100.0)], placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    lines = [e for e in msp if e.dxftype() == "LINE"]
    assert len(lines) == 4
    xs = [e.dxf.start[0] for e in lines]
    assert min(xs) == pytest.approx(500.0)


def test_sheets_are_laid_out_side_by_side(tmp_path):
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [
        Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
        Placement(1, 1, Transform(0.0, False, 0.0, 0.0)),
    ]
    write_dxf(out, drawing_with(entities), parts, placements,
              sheet_w=1000.0, sheet_h=1000.0, gap=100.0)

    msp = read_back(out).modelspace()
    xs = sorted(e.dxf.start[0] for e in msp if e.dxftype() == "LINE")
    assert min(xs) == pytest.approx(0.0)
    assert max(xs) == pytest.approx(1100.0 + 100.0), "placa 1 desplazada 1000 + 100 de gap"


def test_colour_and_layer_survive_the_round_trip(tmp_path):
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    placements = [Placement(0, 0, Transform(0.0, False, 0.0, 0.0))]
    write_dxf(out, drawing_with(entities), [square_part(0, 100.0)], placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    lines = [e for e in msp if e.dxftype() == "LINE"]
    assert all(e.dxf.layer == "CORTE" for e in lines)
    assert all(e.dxf.color == 3 for e in lines)


def test_circles_stay_circles(tmp_path):
    out = tmp_path / "out.dxf"
    entities = [Circle((0.0, 0.0), 300.0, STYLE)]
    part = Part(0, ((-300.0, -300.0), (300.0, -300.0), (300.0, 300.0), (-300.0, 300.0)),
                (), (0,))
    placements = [Placement(0, 0, Transform(0.0, False, 400.0, 400.0))]
    write_dxf(out, drawing_with(entities), [part], placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    circles = [e for e in msp if e.dxftype() == "CIRCLE"]
    assert len(circles) == 1
    assert circles[0].dxf.radius == pytest.approx(300.0)
    assert circles[0].dxf.center[0] == pytest.approx(400.0)


def test_output_declares_millimetres(tmp_path):
    out = tmp_path / "out.dxf"
    write_dxf(out, drawing_with([]), [], [], 1000.0, 1000.0)
    assert read_back(out).units == 4


def test_the_output_can_be_read_back_by_our_own_reader(tmp_path):
    """El circuito completo: lo que escribimos, lo sabemos leer."""
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    placements = [Placement(0, 0, Transform(0.0, False, 50.0, 50.0))]
    write_dxf(out, drawing_with(entities), [square_part(0, 100.0)], placements, 1000.0, 1000.0)

    reread = read_dxf(out)
    lines = [e for e in reread.entities if isinstance(e, Line)]
    assert len(lines) == 4


def test_only_the_entities_of_placed_parts_are_written(tmp_path):
    """Las entidades que no pertenecen a ninguna pieza colocada no salen."""
    out = tmp_path / "out.dxf"
    entities = square_entities(100.0) + [Line((900.0, 900.0), (950.0, 950.0), STYLE)]
    part = Part(0, ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)), (), (0, 1, 2, 3))
    placements = [Placement(0, 0, Transform(0.0, False, 0.0, 0.0))]
    write_dxf(out, drawing_with(entities), [part], placements, 1000.0, 1000.0)

    msp = read_back(out).modelspace()
    assert len([e for e in msp if e.dxftype() == "LINE"]) == 4


def test_unknown_part_id_raises_a_clear_error(tmp_path):
    from nesting.io.dxf_writer import UnknownPartError

    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    placements = [Placement(99, 0, Transform(0.0, False, 0.0, 0.0))]
    with pytest.raises(UnknownPartError) as info:
        write_dxf(out, drawing_with(entities), [square_part(0, 100.0)], placements,
                  1000.0, 1000.0)
    assert "99" in str(info.value)


def test_out_of_range_entity_id_raises_a_clear_error(tmp_path):
    from nesting.io.dxf_writer import InvalidEntityIdError

    out = tmp_path / "out.dxf"
    entities = square_entities(100.0)
    part = Part(0, ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)), (), (0, 1, 2, 42))
    placements = [Placement(0, 0, Transform(0.0, False, 0.0, 0.0))]
    with pytest.raises(InvalidEntityIdError) as info:
        write_dxf(out, drawing_with(entities), [part], placements, 1000.0, 1000.0)
    assert "42" in str(info.value)


# --- Hallazgo 6: el camino de escritura real (Bezier, Arc, Polyline, color) ---
#
# `test_circles_stay_circles` y `test_colour_and_layer_survive_the_round_trip`
# (arriba) son, hasta este punto, la unica cobertura de ida y vuelta -- y
# ninguna de las dos ejercita el tipo de entidad que de verdad domina un
# archivo real (Bezier/SPLINE), ni el caso BYLAYER/BYBLOCK que el Hallazgo 3
# rompia. Los tests de abajo cierran ese hueco: no solo verifican el tipo de
# entidad de salida, sino que los puntos de control / angulos / color
# efectivamente vuelven.


def one_entity_part_and_placement(entity, side=100.0, transform=None):
    """Un Part de una sola entidad, colocado con `transform` (identidad si
    no se especifica), listo para pasar a `write_dxf`."""
    part = Part(0, ((0.0, 0.0), (side, 0.0), (side, side), (0.0, side)), (), (0,))
    placement = Placement(0, 0, transform or Transform.identity())
    return part, placement


def test_a_bezier_round_trips_with_the_same_control_points(tmp_path):
    """Una Bezier cubica se escribe como SPLINE grado 3 (ver `_emit`); al
    releerla con `read_dxf`, `_from_path` la reconvierte en Bezier. No basta
    con que el tipo de entidad sea el correcto -- los 4 puntos de control
    tienen que ser, dentro de una tolerancia numerica chica, los mismos que
    se escribieron."""
    out = tmp_path / "out.dxf"
    bezier = Bezier((0.0, 0.0), (10.0, 40.0), (30.0, 40.0), (40.0, 0.0), STYLE)
    part, placement = one_entity_part_and_placement(bezier)

    write_dxf(out, drawing_with([bezier]), [part], [placement], 1000.0, 1000.0)

    reread = read_dxf(out)
    beziers = [e for e in reread.entities if isinstance(e, Bezier)]
    assert len(beziers) == 1
    result = beziers[0]
    assert result.p0 == pytest.approx(bezier.p0, abs=1e-6)
    assert result.p1 == pytest.approx(bezier.p1, abs=1e-6)
    assert result.p2 == pytest.approx(bezier.p2, abs=1e-6)
    assert result.p3 == pytest.approx(bezier.p3, abs=1e-6)


def test_an_arc_round_trips_with_the_same_geometry(tmp_path):
    out = tmp_path / "out.dxf"
    arc = Arc(center=(50.0, 50.0), radius=30.0, start_angle=10.0, end_angle=100.0, style=STYLE)
    part, placement = one_entity_part_and_placement(arc)

    write_dxf(out, drawing_with([arc]), [part], [placement], 1000.0, 1000.0)

    reread = read_dxf(out)
    arcs = [e for e in reread.entities if isinstance(e, Arc)]
    assert len(arcs) == 1
    result = arcs[0]
    assert result.center == pytest.approx(arc.center)
    assert result.radius == pytest.approx(arc.radius)
    assert result.start_angle == pytest.approx(arc.start_angle)
    assert result.end_angle == pytest.approx(arc.end_angle)


def test_a_mirrored_arc_round_trips_with_the_swapped_endpoints(tmp_path):
    """El caso historicamente fragil del proyecto: espejar un Arc invierte el
    sentido del arco, asi que `apply_entity` intercambia start/end (ver su
    docstring). La escritura tiene que llevarse ese arco ya transformado
    -- `write_dxf` transforma antes de emitir -- y la relectura tiene que
    reproducir exactamente esos angulos, no los originales sin espejar."""
    out = tmp_path / "out.dxf"
    arc = Arc(center=(0.0, 0.0), radius=20.0, start_angle=10.0, end_angle=100.0, style=STYLE)
    mirrored = Transform(angle_deg=0.0, mirror=True, dx=200.0, dy=200.0)
    part, placement = one_entity_part_and_placement(arc, transform=mirrored)

    write_dxf(out, drawing_with([arc]), [part], [placement], 1000.0, 1000.0)

    from nesting.geometry.transform import apply_entity
    expected = apply_entity(mirrored, arc)

    reread = read_dxf(out)
    arcs = [e for e in reread.entities if isinstance(e, Arc)]
    assert len(arcs) == 1
    result = arcs[0]
    assert result.center == pytest.approx(expected.center)
    assert result.start_angle == pytest.approx(expected.start_angle)
    assert result.end_angle == pytest.approx(expected.end_angle)


def test_a_closed_polyline_round_trips(tmp_path):
    out = tmp_path / "out.dxf"
    points = ((0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0))
    polyline = Polyline(points, closed=True, style=STYLE)
    part, placement = one_entity_part_and_placement(polyline)

    write_dxf(out, drawing_with([polyline]), [part], [placement], 1000.0, 1000.0)

    reread = read_dxf(out)
    polylines = [e for e in reread.entities if isinstance(e, Polyline)]
    assert len(polylines) == 1
    result = polylines[0]
    assert result.closed is True
    assert sorted(result.points) == pytest.approx(sorted(points))


def test_a_byalyer_entity_on_a_coloured_layer_keeps_its_colour(tmp_path):
    """Hallazgo 3: una entidad BYLAYER (aci=256) en una capa que en el
    origen tenia color propio (ACI 1, rojo) se leia como color=BYLAYER en
    una capa nueva sin color -- el rojo se perdia. `_style_of` en
    `dxf_reader` ya resuelve `rgb` al color efectivo de la capa en el
    momento de leer, asi que ese rojo tiene que sobrevivir la ida y vuelta."""
    out = tmp_path / "out.dxf"
    red_from_layer = ezdxf.colors.aci2rgb(1)
    style = Style(aci=256, rgb=red_from_layer, layer="ROJA")
    line = Line((0.0, 0.0), (100.0, 0.0), style)
    part, placement = one_entity_part_and_placement(line)

    write_dxf(out, drawing_with([line]), [part], [placement], 1000.0, 1000.0)

    reread = read_dxf(out)
    lines = [e for e in reread.entities if isinstance(e, Line)]
    assert len(lines) == 1
    assert lines[0].style.rgb == red_from_layer


def test_a_true_colour_entity_with_byalyer_aci_keeps_its_true_colour(tmp_path):
    """Hallazgo 3, segundo caso de la tabla: una entidad con color verdadero
    (0,128,255) pero ACI BYLAYER se leia como color=BYLAYER, descartando el
    color verdadero por completo."""
    out = tmp_path / "out.dxf"
    true_colour = (0, 128, 255)
    style = Style(aci=256, rgb=true_colour, layer="0")
    line = Line((0.0, 0.0), (100.0, 0.0), style)
    part, placement = one_entity_part_and_placement(line)

    write_dxf(out, drawing_with([line]), [part], [placement], 1000.0, 1000.0)

    reread = read_dxf(out)
    lines = [e for e in reread.entities if isinstance(e, Line)]
    assert len(lines) == 1
    assert lines[0].style.rgb == true_colour


# --- Una pieza curva llega como una cadena de Bezier que se continuan una a
# otra: son los tramos de UN trazo del archivo de origen, no curvas sueltas.
# Escribir una SPLINE por tramo deja la pieza partida en decenas de entidades
# inconexas, que es el mismo problema que un contorno partido en rectas
# sueltas. ---


def test_a_chain_of_beziers_is_written_as_one_spline(tmp_path):
    first = Bezier((0.0, 0.0), (10.0, 20.0), (30.0, 20.0), (40.0, 0.0), STYLE)
    second = Bezier((40.0, 0.0), (50.0, -20.0), (70.0, -20.0), (80.0, 0.0), STYLE)
    part = Part(id=0, outer=((0.0, 0.0), (40.0, 0.0), (80.0, 0.0)), holes=(),
                entity_ids=(0, 1))

    out = tmp_path / "out.dxf"
    write_dxf(out, drawing_with([first, second]), [part],
              [Placement(0, 0, Transform.identity())], 1000.0, 1000.0)

    splines = [e for e in read_back(out).modelspace() if e.dxftype() == "SPLINE"]
    assert len(splines) == 1, "los dos tramos son un solo trazo"
    control = [(round(p[0], 9), round(p[1], 9)) for p in splines[0].control_points]
    assert control == [
        (0.0, 0.0), (10.0, 20.0), (30.0, 20.0),
        (40.0, 0.0),
        (50.0, -20.0), (70.0, -20.0), (80.0, 0.0),
    ], "los mismos puntos de control, con la juntura una sola vez"
    assert splines[0].dxf.degree == 3
    assert list(splines[0].knots) == [0.0] * 4 + [1.0] * 3 + [2.0] * 4, (
        "nudos interiores de multiplicidad 3: cada juntura es un nodo del trazo"
    )


def test_beziers_that_do_not_meet_stay_separate(tmp_path):
    first = Bezier((0.0, 0.0), (10.0, 20.0), (30.0, 20.0), (40.0, 0.0), STYLE)
    apart = Bezier((100.0, 0.0), (110.0, 20.0), (130.0, 20.0), (140.0, 0.0), STYLE)
    part = Part(id=0, outer=((0.0, 0.0), (40.0, 0.0), (140.0, 0.0)), holes=(),
                entity_ids=(0, 1))

    out = tmp_path / "out.dxf"
    write_dxf(out, drawing_with([first, apart]), [part],
              [Placement(0, 0, Transform.identity())], 1000.0, 1000.0)

    splines = [e for e in read_back(out).modelspace() if e.dxftype() == "SPLINE"]
    assert len(splines) == 2, "unir lo que no se toca inventaria geometria"


# --- Un arco dentro de una polilínea (`bulges`) tiene que llegar al archivo
# COMO arco: el CNC lo corta con una sola orden en vez de con una cadena de
# rectas, y la pieza sigue siendo una entidad. ---

ARQUEADA = Polyline(
    ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
    True, STYLE, bulges=(0.5, 0.0, 0.0, 0.0),
)


def arc_part():
    return Part(id=0, outer=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
                holes=(), entity_ids=(0,))


def written_polyline(tmp_path, transform):
    out = tmp_path / "out.dxf"
    write_dxf(out, drawing_with([ARQUEADA]), [arc_part()],
              [Placement(0, 0, transform)], 1000.0, 1000.0)
    return [
        e for e in read_back(out).modelspace()
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == STYLE.layer
    ]


def test_a_bulged_polyline_keeps_its_arcs_in_the_output(tmp_path):
    written = written_polyline(tmp_path, Transform.identity())

    assert len(written) == 1, "una sola entidad, con arco y todo"
    assert written[0].closed
    assert [round(p[4], 9) for p in written[0].get_points("xyseb")] == [
        0.5, 0.0, 0.0, 0.0
    ]


def test_a_mirrored_part_writes_the_mirrored_arc(tmp_path):
    written = written_polyline(tmp_path, Transform(0.0, True, 0.0, 0.0))
    assert [round(p[4], 9) for p in written[0].get_points("xyseb")] == [
        -0.5, 0.0, 0.0, 0.0
    ], "espejar invierte el sentido de giro del arco"


def test_a_polyline_without_bulges_is_written_exactly_as_before(tmp_path):
    recta = Polyline(((0.0, 0.0), (100.0, 0.0), (100.0, 100.0)), True, STYLE)
    out = tmp_path / "out.dxf"
    write_dxf(out, drawing_with([recta]), [arc_part()],
              [Placement(0, 0, Transform.identity())], 1000.0, 1000.0)

    written = [
        e for e in read_back(out).modelspace()
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == STYLE.layer
    ]
    assert len(written) == 1
    assert all(p[4] == 0.0 for p in written[0].get_points("xyseb"))
