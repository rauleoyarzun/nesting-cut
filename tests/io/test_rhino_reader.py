import pytest

rhino3dm = pytest.importorskip("rhino3dm")

from nesting.io.rhino_reader import read_3dm  # noqa: E402
from nesting.model.entities import Line, Polyline  # noqa: E402


def new_model(unit_system=None):
    model = rhino3dm.File3dm()
    if unit_system is not None:
        model.Settings.ModelUnitSystem = unit_system
    return model


def save(model, tmp_path, name="t.3dm"):
    path = tmp_path / name
    model.Write(str(path), 7)
    return path


def add_layer(model, name, color):
    layer = rhino3dm.Layer()
    layer.Name = name
    layer.Color = color
    return model.Layers.Add(layer)


def test_reads_a_line(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(100, 50, 0))
    drawing = read_3dm(save(model, tmp_path))

    assert len(drawing.entities) == 1
    assert isinstance(drawing.entities[0], Line)
    assert drawing.entities[0].end == pytest.approx((100.0, 50.0))


def test_reads_a_polyline_exactly(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    points = [rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(100, 0, 0),
              rhino3dm.Point3d(100, 100, 0), rhino3dm.Point3d(0, 0, 0)]
    model.Objects.AddPolyline(points)
    drawing = read_3dm(save(model, tmp_path))

    polylines = [e for e in drawing.entities if isinstance(e, Polyline)]
    assert len(polylines) == 1
    assert polylines[0].closed
    assert len(polylines[0].points) == 3, (
        "los 3 vertices distintos: el cierre lo dice `closed`, y repetir el "
        "primer punto al final deja un tramo de largo cero en la salida"
    )


def test_a_circle_is_sampled_into_a_polyline(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    circle = rhino3dm.Circle(rhino3dm.Point3d(0, 0, 0), 50.0)
    model.Objects.AddCircle(circle)
    drawing = read_3dm(save(model, tmp_path))

    polylines = [e for e in drawing.entities if isinstance(e, Polyline)]
    assert len(polylines) == 1
    assert len(polylines[0].points) > 20, "muestreado fino"


def test_the_sampled_circle_stays_within_the_tolerance(tmp_path):
    import math

    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddCircle(rhino3dm.Circle(rhino3dm.Point3d(0, 0, 0), 50.0))
    drawing = read_3dm(save(model, tmp_path), sample_tol=0.05)

    points = drawing.entities[0].points
    for a, b in zip(points, points[1:]):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        assert abs(math.hypot(*mid) - 50.0) < 0.06


def test_centimetres_are_scaled_to_millimetres(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Centimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(10, 0, 0))
    drawing = read_3dm(save(model, tmp_path))

    assert drawing.entities[0].end[0] == pytest.approx(100.0)
    assert drawing.source_units == "cm"


def test_inches_are_scaled_to_millimetres(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Inches)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(1, 0, 0))
    drawing = read_3dm(save(model, tmp_path))
    assert drawing.entities[0].end[0] == pytest.approx(25.4)


def test_layer_names_and_colours_are_preserved(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    index = add_layer(model, "CORTE", (255, 0, 0, 255))

    attributes = rhino3dm.ObjectAttributes()
    attributes.LayerIndex = index
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(10, 0, 0), attributes)

    drawing = read_3dm(save(model, tmp_path))
    assert drawing.entities[0].style.layer == "CORTE"
    assert drawing.entities[0].style.rgb == (255, 0, 0)


def test_a_non_planar_curve_is_skipped_with_a_warning(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(100, 0, 0))
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(0, 0, 500))

    drawing = read_3dm(save(model, tmp_path))
    assert len(drawing.entities) == 1
    assert any("plana" in w for w in drawing.warnings)


def test_a_curve_at_a_constant_non_zero_z_is_accepted(tmp_path):
    """Dibujar a altura 50 es plano: se proyecta sin problema."""
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 50), rhino3dm.Point3d(100, 0, 50))

    drawing = read_3dm(save(model, tmp_path))
    assert len(drawing.entities) == 1
    assert drawing.warnings == []


def test_non_curve_objects_are_skipped_with_a_warning(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddPoint(rhino3dm.Point3d(1, 2, 0))
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(10, 0, 0))

    drawing = read_3dm(save(model, tmp_path))
    assert len(drawing.entities) == 1
    assert any("no son curvas" in w for w in drawing.warnings)


def test_a_circle_standing_in_the_xz_plane_is_rejected_as_non_planar(tmp_path):
    """Regression test for a real bug found on `bench/files/banqueta.3dm`.

    A full circle lying in the XZ plane (Y constant, X and Z both varying)
    projects onto a degenerate back-and-forth *line* in XY once Y is dropped.
    The old chord-tolerance check compared only the X,Y coordinates of the
    adaptively-sampled midpoint against the X,Y chord midpoint, so at the
    quarter points of this particular circle cos(pi/2) happens to equal the
    average of cos(0) and cos(pi) exactly - the XY check passed after a
    single subdivision, and the curve was silently accepted as "planar" and
    flattened into a 3-point sausage with no warning at all. Comparing the
    full 3D point to the 3D chord midpoint catches the real Z excursion at
    the same quarter points and forces further subdivision, so
    `_require_planar` sees the true Z spread and rejects the curve.
    """
    import math

    model = new_model(rhino3dm.UnitSystem.Millimeters)
    circle = rhino3dm.Circle(rhino3dm.Point3d(0, 0, 0), 50.0)
    curve = circle.ToNurbsCurve()
    xform = rhino3dm.Transform.Rotation(
        math.pi / 2, rhino3dm.Vector3d(1, 0, 0), rhino3dm.Point3d(0, 0, 0)
    )
    curve.Transform(xform)
    model.Objects.AddCurve(curve)

    drawing = read_3dm(save(model, tmp_path))
    assert drawing.entities == []
    assert any("plana" in w for w in drawing.warnings)


def test_an_empty_model_reads_as_empty(tmp_path):
    drawing = read_3dm(save(new_model(rhino3dm.UnitSystem.Millimeters), tmp_path))
    assert drawing.entities == []


# --- Hallazgo 2: unidades no soportadas o no declaradas no se deben adivinar ---


def test_an_unsupported_unit_system_raises_instead_of_assuming_millimetres(tmp_path):
    """Yardas es uno de los 22 sistemas de `rhino3dm.UnitSystem` que
    `_UNIT_NAMES` no soporta. Antes del arreglo, esto se leía en silencio
    como si fuera milímetros."""
    from nesting.io.dxf_reader import UnknownUnitsError

    model = new_model(rhino3dm.UnitSystem.Yards)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(1, 0, 0))

    with pytest.raises(UnknownUnitsError) as info:
        read_3dm(save(model, tmp_path))
    assert "yardas" in str(info.value)


def test_an_unset_unit_system_raises_instead_of_assuming_millimetres(tmp_path):
    from nesting.io.dxf_reader import UnknownUnitsError

    model = new_model(rhino3dm.UnitSystem.Unset)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(1, 0, 0))

    with pytest.raises(UnknownUnitsError):
        read_3dm(save(model, tmp_path))


def test_units_override_lets_an_unsupported_unit_system_be_read(tmp_path):
    """--unidades tiene que servir también para .3dm, igual que para .dxf."""
    model = new_model(rhino3dm.UnitSystem.Yards)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(1, 0, 0))

    drawing = read_3dm(save(model, tmp_path), units_override="cm")
    assert drawing.entities[0].end[0] == pytest.approx(10.0)
    assert drawing.source_units == "cm"


def test_a_file_that_is_not_a_valid_3dm_raises_a_clear_error(tmp_path):
    """`rhino3dm.File3dm.Read` devuelve `None` para un archivo que no es un
    .3dm valido; antes esto reventaba con un AttributeError crudo al acceder
    a `model.Settings`."""
    path = tmp_path / "not_really_a_3dm.3dm"
    path.write_bytes(b"esto no es un archivo .3dm, es basura de prueba")

    with pytest.raises(OSError) as info:
        read_3dm(path)
    assert str(path) in str(info.value)


def test_the_result_flows_through_the_whole_pipeline(tmp_path):
    from nesting.pipeline import prepare_parts

    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddCircle(rhino3dm.Circle(rhino3dm.Point3d(0, 0, 0), 100.0))
    parts, _, _ = prepare_parts(read_3dm(save(model, tmp_path)))

    assert len(parts) == 1
    assert parts[0].outer_area == pytest.approx(3.14159 * 100.0**2, rel=0.01)


# --- Qué se descartó, con geometría suficiente para mostrarlo -----------------


def test_a_non_curve_object_is_recorded_as_a_discard(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddPoint(rhino3dm.Point3d(1, 2, 0))
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(10, 0, 0))

    drawing = read_3dm(save(model, tmp_path))

    discards = [d for d in drawing.discards if d.reason == "no_es_curva"]
    assert len(discards) == len(drawing.entities) - 0 - 0  # sanity: hay uno
    assert len(discards) == 1
    assert "Point" in discards[0].detail, "el detalle nombra el tipo de objeto"


def test_a_non_planar_curve_discard_carries_its_xy_shadow_and_z_range(tmp_path):
    """La sombra en XY es lo que ubica la curva en el plano; el rango de Z es
    lo que explica por qué se descartó. Sin el Z el usuario ve una línea
    delgada en el dibujo y no entiende qué tiene de malo."""
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 7, 0), rhino3dm.Point3d(100, 7, 500))

    drawing = read_3dm(save(model, tmp_path))

    discards = [d for d in drawing.discards if d.reason == "no_plana"]
    assert len(discards) == 1
    xs = [p[0] for p in discards[0].points]
    assert min(xs) == pytest.approx(0.0) and max(xs) == pytest.approx(100.0)
    assert all(p[1] == pytest.approx(7.0) for p in discards[0].points)
    assert "500" in discards[0].detail, f"el detalle debe nombrar el Z: {discards[0].detail}"


def test_the_discard_count_matches_the_warning_text(tmp_path):
    """El aviso y la imagen tienen que salir de la misma lista.

    Si el texto dice 2 y el dibujo marca 1, el usuario pierde la confianza en
    los dos. El aviso se construye con `len()` sobre los descartes justamente
    para que no puedan discrepar.
    """
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddPoint(rhino3dm.Point3d(1, 2, 0))
    model.Objects.AddPoint(rhino3dm.Point3d(3, 4, 0))
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(10, 0, 0))

    drawing = read_3dm(save(model, tmp_path))

    assert any("se ignoraron 2 objetos que no son curvas" in w for w in drawing.warnings)
    assert len([d for d in drawing.discards if d.reason == "no_es_curva"]) == 2


def test_a_clean_drawing_records_no_discards(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddLine(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(10, 0, 0))

    assert read_3dm(save(model, tmp_path)).discards == []


# --- Una curva "unida" de Rhino (PolyCurve) es UNA pieza hecha de varios
# tramos. Muestrearla por parametro, como si fuera una curva cualquiera,
# ignora esa estructura: los tramos rectos salen con nodos de mas y las
# esquinas quedan redondeadas por debajo de la tolerancia. Estos tests fijan
# que los tramos rectos salgan exactos y que la pieza siga siendo una sola
# entidad. ---


def polycurve_of_lines(points):
    curve = rhino3dm.PolyCurve()
    for start, end in zip(points, points[1:]):
        curve.AppendSegment(
            rhino3dm.LineCurve(
                rhino3dm.Point3d(start[0], start[1], 0),
                rhino3dm.Point3d(end[0], end[1], 0),
            )
        )
    return curve


HEX_NUT = [(0, 0), (100, 0), (100, 40), (60, 40), (60, 100), (0, 100), (0, 0)]


def test_a_polycurve_of_straight_segments_keeps_its_exact_vertices(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddCurve(polycurve_of_lines(HEX_NUT), None)
    drawing = read_3dm(save(model, tmp_path))

    assert len(drawing.entities) == 1, "la curva unida es una sola entidad"
    polyline = drawing.entities[0]
    assert isinstance(polyline, Polyline)
    assert polyline.closed
    assert [
        (round(x, 9), round(y, 9)) for x, y in polyline.points
    ] == [(float(x), float(y)) for x, y in HEX_NUT[:-1]], (
        "los vertices originales, sin agregar ni mover ninguno"
    )


def test_a_polycurve_mixing_a_curve_keeps_the_straight_corners_exact(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    curve = polycurve_of_lines([(0, 0), (100, 0), (100, 50)])
    arc = rhino3dm.Arc(
        rhino3dm.Point3d(100, 50, 0), rhino3dm.Point3d(50, 90, 0), rhino3dm.Point3d(0, 50, 0)
    )
    curve.AppendSegment(rhino3dm.NurbsCurve.CreateFromArc(arc))
    curve.AppendSegment(
        rhino3dm.LineCurve(rhino3dm.Point3d(0, 50, 0), rhino3dm.Point3d(0, 0, 0))
    )
    model.Objects.AddCurve(curve, None)
    drawing = read_3dm(save(model, tmp_path))

    assert len(drawing.entities) == 1, "sigue siendo una sola pieza, no cinco tramos"
    points = [(round(x, 6), round(y, 6)) for x, y in drawing.entities[0].points]
    for corner in [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]:
        assert corner in points, f"la esquina {corner} tiene que estar exacta"
    straight_run = points[: points.index((100.0, 50.0)) + 1]
    assert straight_run == [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)], (
        "los dos tramos rectos no llevan ni un nodo de mas"
    )


# --- Un arco de verdad (un filete, un redondeo) no tiene por qué salir
# poligonizado: la polilínea del DXF sabe guardar tramos arqueados, y el CNC
# los corta con una sola orden. La pieza sigue siendo UNA entidad. ---


def arc_segment(start, through, end):
    return rhino3dm.NurbsCurve.CreateFromArc(
        rhino3dm.Arc(rhino3dm.Point3d(*start, 0), rhino3dm.Point3d(*through, 0),
                     rhino3dm.Point3d(*end, 0))
    )


def polycurve_with_arc():
    curve = rhino3dm.PolyCurve()
    curve.AppendSegment(rhino3dm.LineCurve(rhino3dm.Point3d(0, 0, 0),
                                           rhino3dm.Point3d(100, 0, 0)))
    curve.AppendSegment(arc_segment((100, 0), (110, 25), (100, 50)))
    curve.AppendSegment(rhino3dm.LineCurve(rhino3dm.Point3d(100, 50, 0),
                                           rhino3dm.Point3d(0, 50, 0)))
    curve.AppendSegment(rhino3dm.LineCurve(rhino3dm.Point3d(0, 50, 0),
                                           rhino3dm.Point3d(0, 0, 0)))
    return curve


def test_an_arc_segment_stays_an_arc_inside_the_polyline(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddCurve(polycurve_with_arc(), None)
    drawing = read_3dm(save(model, tmp_path))

    assert len(drawing.entities) == 1, "sigue siendo una sola pieza"
    polyline = drawing.entities[0]
    assert [(round(x, 6), round(y, 6)) for x, y in polyline.points] == [
        (0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)
    ], "el arco no agrega ni un nodo: son los 4 vertices del contorno"
    assert polyline.bulges[0] == 0.0, "el primer tramo es recto"
    assert polyline.bulges[1] != 0.0, "el segundo es el arco"
    assert polyline.bulges[2] == polyline.bulges[3] == 0.0


def distance_to_path(point, path):
    """Distancia de `point` a la poligonal `path`, midiendo a los SEGMENTOS.

    Medir sólo a los vértices confunde "la curva se movió" con "el muestreo
    de la curva es grueso": entre dos vértices de un arco de 55 mm hay
    milímetros de aire, y ese aire no es un error de la geometría.
    """
    import math

    worst = float("inf")
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        dx, dy = bx - ax, by - ay
        length_squared = dx * dx + dy * dy
        if length_squared == 0.0:
            worst = min(worst, math.dist(point, (ax, ay)))
            continue
        t = ((point[0] - ax) * dx + (point[1] - ay) * dy) / length_squared
        t = max(0.0, min(1.0, t))
        worst = min(worst, math.dist(point, (ax + t * dx, ay + t * dy)))
    return worst


def test_the_arc_of_the_polyline_lands_on_the_original_curve(tmp_path):
    """Que no agregue nodos no sirve de nada si mueve la curva.

    Un bulge con el signo cambiado pasaría los tests de estructura sin
    problema y dejaría el arco para el otro lado: acá se mide contra la
    curva de Rhino, punto por punto.
    """
    from nesting.geometry.flatten import flatten

    source = polycurve_with_arc()
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddCurve(source, None)
    drawing = read_3dm(save(model, tmp_path))

    flattened = flatten(drawing.entities[0], tolerance=0.01)
    domain = source.Domain
    worst = 0.0
    for i in range(4001):
        q = source.PointAt(domain.T0 + (domain.T1 - domain.T0) * i / 4000)
        worst = max(worst, distance_to_path((q.X, q.Y), flattened))
    assert worst < 0.01, f"el contorno se corrió {worst:.4f} mm del original"


def test_a_lone_arc_becomes_a_two_point_arced_polyline(tmp_path):
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddCurve(arc_segment((0, 0), (5, -5), (10, 0)), None)
    drawing = read_3dm(save(model, tmp_path))

    polyline = drawing.entities[0]
    assert len(polyline.points) == 2
    assert polyline.bulges[0] == pytest.approx(1.0), "media vuelta antihoraria"


def test_a_drawing_without_arcs_carries_no_bulges(tmp_path):
    """Lo que no tiene arcos tiene que salir EXACTAMENTE como antes."""
    model = new_model(rhino3dm.UnitSystem.Millimeters)
    model.Objects.AddCurve(polycurve_of_lines(HEX_NUT), None)
    drawing = read_3dm(save(model, tmp_path))
    assert drawing.entities[0].bulges == ()
