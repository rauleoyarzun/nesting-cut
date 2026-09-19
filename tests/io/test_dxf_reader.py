import ezdxf
import pytest

from nesting.io.dxf_reader import SHEET_LAYER, UnknownUnitsError, read_dxf
from nesting.model.entities import Arc, Bezier, Circle, Line, Polyline


def make_doc(units=4):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units
    return doc


def save(doc, tmp_path, name="t.dxf"):
    path = tmp_path / name
    doc.saveas(path)
    return path


def test_reads_a_line(tmp_path):
    doc = make_doc()
    doc.modelspace().add_line((0, 0), (10, 5), dxfattribs={"layer": "CORTE", "color": 1})
    drawing = read_dxf(save(doc, tmp_path))

    assert len(drawing.entities) == 1
    line = drawing.entities[0]
    assert isinstance(line, Line)
    assert line.start == pytest.approx((0.0, 0.0))
    assert line.end == pytest.approx((10.0, 5.0))
    assert line.style.layer == "CORTE"
    assert line.style.aci == 1


def test_reads_circle_and_arc_natively(tmp_path):
    doc = make_doc()
    msp = doc.modelspace()
    msp.add_circle((1, 2), radius=3)
    msp.add_arc((0, 0), radius=5, start_angle=10, end_angle=80)
    drawing = read_dxf(save(doc, tmp_path))

    kinds = {type(e) for e in drawing.entities}
    assert kinds == {Circle, Arc}
    circle = next(e for e in drawing.entities if isinstance(e, Circle))
    assert circle.radius == pytest.approx(3.0)
    arc = next(e for e in drawing.entities if isinstance(e, Arc))
    assert arc.start_angle == pytest.approx(10.0)
    assert arc.end_angle == pytest.approx(80.0)


def test_reads_a_closed_lwpolyline_without_bulges(tmp_path):
    doc = make_doc()
    doc.modelspace().add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)], close=True
    )
    drawing = read_dxf(save(doc, tmp_path))

    assert len(drawing.entities) == 1
    poly = drawing.entities[0]
    assert isinstance(poly, Polyline)
    assert poly.closed is True
    assert len(poly.points) == 4


def test_a_spline_becomes_bezier_segments(tmp_path):
    doc = make_doc()
    doc.modelspace().add_spline([(0, 0), (10, 20), (20, 0), (30, 20)])
    drawing = read_dxf(save(doc, tmp_path))

    assert drawing.entities
    assert all(isinstance(e, Bezier) for e in drawing.entities)


def test_bezier_segments_are_continuous(tmp_path):
    """El final de cada Bezier es el arranque del siguiente."""
    doc = make_doc()
    doc.modelspace().add_spline([(0, 0), (10, 20), (20, 0), (30, 20)])
    beziers = read_dxf(save(doc, tmp_path)).entities

    for a, b in zip(beziers, beziers[1:]):
        assert a.p3 == pytest.approx(b.p0, abs=1e-9)


def test_millimetres_are_not_rescaled(tmp_path):
    doc = make_doc(units=4)
    doc.modelspace().add_line((0, 0), (100, 0))
    drawing = read_dxf(save(doc, tmp_path))
    assert drawing.entities[0].end == pytest.approx((100.0, 0.0))
    assert drawing.source_units == "mm"


def test_centimetres_are_scaled_to_millimetres(tmp_path):
    doc = make_doc(units=5)
    doc.modelspace().add_line((0, 0), (100, 0))
    drawing = read_dxf(save(doc, tmp_path))
    assert drawing.entities[0].end == pytest.approx((1000.0, 0.0))
    assert drawing.source_units == "cm"


def test_inches_are_scaled_to_millimetres(tmp_path):
    doc = make_doc(units=1)
    doc.modelspace().add_circle((0, 0), radius=1)
    drawing = read_dxf(save(doc, tmp_path))
    assert drawing.entities[0].radius == pytest.approx(25.4)


def test_unitless_file_without_override_raises(tmp_path):
    doc = make_doc(units=0)
    doc.modelspace().add_line((0, 0), (10, 0))
    with pytest.raises(UnknownUnitsError) as info:
        read_dxf(save(doc, tmp_path))
    assert "unidades" in str(info.value).lower()


def test_unitless_file_with_override_is_accepted(tmp_path):
    doc = make_doc(units=0)
    doc.modelspace().add_line((0, 0), (10, 0))
    drawing = read_dxf(save(doc, tmp_path), units_override="cm")
    assert drawing.entities[0].end == pytest.approx((100.0, 0.0))


def test_override_wins_over_the_declared_units(tmp_path):
    doc = make_doc(units=4)
    doc.modelspace().add_line((0, 0), (10, 0))
    drawing = read_dxf(save(doc, tmp_path), units_override="cm")
    assert drawing.entities[0].end == pytest.approx((100.0, 0.0))


def test_unsupported_entities_are_skipped_with_a_warning(tmp_path):
    doc = make_doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_text("600.00").set_placement((5, 5))
    drawing = read_dxf(save(doc, tmp_path))

    assert len(drawing.entities) == 1
    assert any("TEXT" in w for w in drawing.warnings)


def test_inserts_are_exploded(tmp_path):
    doc = make_doc()
    block = doc.blocks.new(name="PATA")
    block.add_line((0, 0), (10, 0))
    block.add_line((10, 0), (10, 10))
    doc.modelspace().add_blockref("PATA", insert=(100, 100))
    drawing = read_dxf(save(doc, tmp_path))

    assert len(drawing.entities) == 2
    assert all(isinstance(e, Line) for e in drawing.entities)
    xs = sorted(e.start[0] for e in drawing.entities)
    assert xs == pytest.approx([100.0, 110.0])


def test_true_colour_is_preserved(tmp_path):
    doc = make_doc()
    line = doc.modelspace().add_line((0, 0), (1, 0))
    line.rgb = (12, 34, 56)
    drawing = read_dxf(save(doc, tmp_path))
    assert drawing.entities[0].style.rgb == (12, 34, 56)


def test_an_empty_drawing_reads_as_empty(tmp_path):
    drawing = read_dxf(save(make_doc(), tmp_path))
    assert drawing.entities == []


def test_a_full_sweep_arc_becomes_a_circle(tmp_path):
    """Un ARC de barrido 360 grados (start == end) representa un circulo completo.

    Si se mapeara a `Arc`, la normalizacion de angulos de la transformacion
    rigida lo colapsaria a start == end y se escribiria degenerado en la
    salida. El lector debe convertirlo a `Circle` en el origen.
    """
    doc = make_doc()
    doc.modelspace().add_arc((3, 4), radius=7, start_angle=0, end_angle=360)
    drawing = read_dxf(save(doc, tmp_path))

    assert len(drawing.entities) == 1
    circle = drawing.entities[0]
    assert isinstance(circle, Circle)
    assert circle.center == pytest.approx((3.0, 4.0))
    assert circle.radius == pytest.approx(7.0)


def test_unitless_file_message_says_no_units_declared(tmp_path):
    """$INSUNITS = 0: el archivo no declara ninguna unidad."""
    doc = make_doc(units=0)
    doc.modelspace().add_line((0, 0), (10, 0))
    with pytest.raises(UnknownUnitsError) as info:
        read_dxf(save(doc, tmp_path))
    message = str(info.value).lower()
    assert "no declara unidades" in message
    assert "--unidades" in message


def test_unsupported_declared_unit_names_the_unit_and_code(tmp_path):
    """$INSUNITS = 3 (millas) es una unidad DXF valida pero no soportada: el
    mensaje tiene que nombrarla en vez de decir que el archivo no declara
    ninguna, y seguir sugiriendo --unidades."""
    doc = make_doc(units=3)
    doc.modelspace().add_line((0, 0), (10, 0))
    with pytest.raises(UnknownUnitsError) as info:
        read_dxf(save(doc, tmp_path))
    message = str(info.value).lower()
    assert "no declara unidades" not in message
    assert "millas" in message
    assert "3" in message
    assert "--unidades" in message


def test_entities_on_the_reserved_sheet_layer_are_recorded_as_discards(tmp_path):
    """Re-alimentar la salida del programa es el caso normal de esta capa, y
    el aviso solo. El diagnóstico tiene que poder decir cuántas y de qué tipo,
    aunque no haya geometría convertida que marcar."""
    doc = ezdxf.new(setup=True)
    doc.units = 4  # mm
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_lwpolyline(
        [(0, 0), (100, 0), (100, 50), (0, 50)], close=True,
        dxfattribs={"layer": SHEET_LAYER},
    )
    path = tmp_path / "con_placa.dxf"
    doc.saveas(path)

    drawing = read_dxf(path)

    discards = [d for d in drawing.discards if d.reason == "capa_placa"]
    assert len(discards) == 1
    assert any("_PLACA" in w for w in drawing.warnings)


def test_unsupported_entity_types_are_recorded_as_discards(tmp_path):
    doc = ezdxf.new(setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_text("una nota").set_placement((5, 5))
    path = tmp_path / "con_texto.dxf"
    doc.saveas(path)

    drawing = read_dxf(path)

    discards = [d for d in drawing.discards if d.reason == "tipo_no_soportado"]
    assert len(discards) == 1
    assert "TEXT" in discards[0].detail


def test_a_clean_dxf_records_no_discards(tmp_path):
    doc = ezdxf.new(setup=True)
    doc.units = 4
    doc.modelspace().add_line((0, 0), (10, 0))
    path = tmp_path / "limpio.dxf"
    doc.saveas(path)

    assert read_dxf(path).discards == []
