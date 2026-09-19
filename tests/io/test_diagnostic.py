"""El PNG que muestra QUÉ se descartó y DÓNDE, sobre el dibujo original."""

from PIL import Image

from nesting.io.diagnostic import MAX_MARKS, write_diagnostic
from nesting.model.discard import DISCARD_STYLES, Discard
from nesting.model.part import Part


def square_part(x0, y0, side, part_id=0):
    outer = (
        (x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side),
    )
    return Part(id=part_id, outer=outer, holes=(), entity_ids=(part_id,))


def ink(path):
    """Cuántos píxeles no son fondo blanco."""
    with Image.open(path) as image:
        return sum(1 for pixel in image.convert("RGB").getdata() if pixel != (255, 255, 255))


def colors_in(path):
    with Image.open(path) as image:
        return {pixel for pixel in image.convert("RGB").getdata()}


def test_writes_a_png(tmp_path):
    out = tmp_path / "d.png"
    write_diagnostic(out, [square_part(0, 0, 100)], [])

    with Image.open(out) as image:
        assert image.format == "PNG"
        assert image.width > 0 and image.height > 0


def test_a_discard_with_geometry_is_painted_in_the_colour_of_its_reason(tmp_path):
    out = tmp_path / "d.png"
    discard = Discard(reason="suelta", points=((10.0, 50.0), (22.0, 50.0)), detail="12.000 mm")

    write_diagnostic(out, [square_part(0, 0, 100)], [discard])

    assert DISCARD_STYLES["suelta"].color in colors_in(out)


def test_two_reasons_are_told_apart_by_colour(tmp_path):
    out = tmp_path / "d.png"
    discards = [
        Discard(reason="suelta", points=((10.0, 50.0), (22.0, 50.0))),
        Discard(reason="duplicada", points=((60.0, 20.0), (80.0, 20.0))),
    ]
    write_diagnostic(out, [square_part(0, 0, 100)], discards)

    present = colors_in(out)
    assert DISCARD_STYLES["suelta"].color in present
    assert DISCARD_STYLES["duplicada"].color in present


def test_a_discard_without_geometry_still_reaches_the_legend(tmp_path):
    """Una cota de Rhino no se puede marcar sobre el plano, pero el aviso de
    texto sí la cuenta. Omitirla de la imagen dejaría al usuario buscando una
    marca que no existe."""
    out = tmp_path / "d.png"
    discard = Discard(reason="no_es_curva", points=(), detail="DimLinear")

    write_diagnostic(out, [square_part(0, 0, 100)], [discard])

    assert DISCARD_STYLES["no_es_curva"].color in colors_in(out)


def test_a_clean_drawing_still_produces_a_file(tmp_path):
    """Correrlo sobre un archivo sano es el caso que confirma que está sano.

    Si no escribiera nada, el usuario no podría distinguir "no se descartó
    nada" de "el comando falló".
    """
    out = tmp_path / "d.png"
    write_diagnostic(out, [square_part(0, 0, 100)], [])

    assert out.exists()
    with Image.open(out) as image:
        assert image.width > 0


def test_a_drawing_with_no_geometry_at_all_does_not_crash(tmp_path):
    """Caja envolvente de tamaño cero: la escala sería una división por cero."""
    out = tmp_path / "d.png"
    write_diagnostic(out, [], [])

    assert out.exists()


def test_every_point_of_the_drawing_collapsing_to_one_spot_does_not_crash(tmp_path):
    """Otra caja de tamaño cero, esta con contenido: una pieza degenerada."""
    out = tmp_path / "d.png"
    degenerate = Part(id=0, outer=((5.0, 5.0), (5.0, 5.0), (5.0, 5.0)), holes=(), entity_ids=(0,))

    write_diagnostic(out, [degenerate], [])

    assert out.exists()


def test_the_number_of_zoom_panels_is_capped(tmp_path):
    """Mil descartes harían una imagen de metros de alto que nadie abre.

    Se recortan los recuadros, no la lista: el resumen sigue diciendo el total
    real, así que el usuario sabe que hay más de lo que ve.
    """
    out = tmp_path / "d.png"
    many = [
        Discard(reason="suelta", points=((float(i), 0.0), (float(i) + 1.0, 0.0)))
        for i in range(MAX_MARKS + 25)
    ]

    marks = write_diagnostic(out, [square_part(0, 0, 100)], many)

    assert marks == MAX_MARKS
    with Image.open(out) as image:
        assert image.height < 6000, "la imagen tiene que seguir siendo abrible"


def test_it_reports_how_many_marks_it_drew(tmp_path):
    out = tmp_path / "d.png"
    discards = [
        Discard(reason="suelta", points=((10.0, 50.0), (22.0, 50.0))),
        Discard(reason="no_es_curva", points=()),
    ]

    assert write_diagnostic(out, [square_part(0, 0, 100)], discards) == 1, (
        "solo se marca lo que tiene geometría; el resto va al resumen"
    )


def test_holes_are_part_of_the_backdrop(tmp_path):
    """El fondo es el dibujo entero, no solo los contornos exteriores: si un
    descarte cae adentro de un agujero, el usuario tiene que ver el agujero."""
    out = tmp_path / "d.png"
    hole = ((40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0))
    part = Part(
        id=0,
        outer=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
        holes=(hole,), entity_ids=(0,),
    )

    write_diagnostic(out, [part], [])
    with_hole = ink(out)

    write_diagnostic(out, [Part(id=0, outer=part.outer, holes=(), entity_ids=(0,))], [])
    without_hole = ink(out)

    assert with_hole > without_hole, "el agujero tiene que sumar trazo al fondo"


# --- Tipografía --------------------------------------------------------------


def render(text, font):
    from PIL import ImageDraw

    image = Image.new("RGB", (220, 34), (255, 255, 255))
    ImageDraw.Draw(image).text((2, 2), text, font=font, fill=(0, 0, 0))
    return list(image.convert("RGB").getdata())


def test_the_font_can_draw_spanish_accents_and_enes():
    """Toda la interfaz de este programa está en español.

    La tipografía por omisión de Pillow dibuja 'á' y 'ñ' como un cuadradito
    vacío -- el mismo cuadradito que usa para cualquier glifo que le falta.
    Se compara contra un carácter que ninguna tipografía latina tiene: si
    salen iguales, las dos son el cuadradito y la leyenda es ilegible.
    """
    from nesting.io.diagnostic import _font

    font = _font(16)
    missing = render("水水水水", font)

    for accented in ("ñññ", "ááá", "óóó", "ééé"):
        assert render(accented, font) != missing, (
            f"{accented!r} sale como el glifo de 'carácter desconocido'"
        )


def test_accented_text_renders_differently_from_its_unaccented_twin():
    from nesting.io.diagnostic import _font

    font = _font(16)
    assert render("año", font) != render("ano", font)


def test_the_legend_text_is_actually_legible_at_full_size(tmp_path):
    """Una leyenda en cuerpo 8 sobre un lienzo de 1800 px no se lee.

    Se mide la altura real de la línea que dibuja Pillow, que es lo que
    determina si el renglón se lee o no.
    """
    from nesting.io.diagnostic import LEGEND_ROW_H, _font

    box = _font(16).getbbox("rectángulo del tamaño exacto")
    height = box[3] - box[1]
    assert height >= 10, f"la tipografía quedó en {height} px de alto"
    assert height < LEGEND_ROW_H, "el renglón no puede ser más alto que su fila"


def test_a_typical_zoom_label_fits_without_being_cut():
    """La etiqueta del recuadro es la que lleva la coordenada y el largo.

    Truncarla justo ahí ('[ventana ...') le saca al usuario el dato que
    necesita para ir a buscar la cosa en su dibujo.
    """
    from nesting.io.diagnostic import ZOOM_SIDE, _fit, _zoom_font

    label = "(11237, 225) mm  0.024 mm  [ventana 80 mm]"
    assert _fit(label, _zoom_font(), ZOOM_SIDE) == label


def test_a_genuinely_long_label_is_still_cut_rather_than_overflowing():
    from nesting.io.diagnostic import ZOOM_SIDE, _fit, _zoom_font

    long_label = "x" * 400
    cut = _fit(long_label, _zoom_font(), ZOOM_SIDE)

    assert cut.endswith("...")
    assert _zoom_font().getbbox(cut)[2] <= ZOOM_SIDE


def test_no_zoom_panel_falls_off_the_right_edge():
    """Un recuadro que empieza dentro del lienzo pero termina afuera se ve
    cortado por la mitad, y su etiqueta -- la que lleva la coordenada -- se
    pierde entera."""
    from nesting.io.diagnostic import MARGIN, PLAN_W, ZOOM_SIDE, ZOOMS_PER_ROW

    last_column_right = MARGIN + (ZOOMS_PER_ROW - 1) * (ZOOM_SIDE + MARGIN) + ZOOM_SIDE
    assert last_column_right <= PLAN_W


def test_the_summary_line_of_the_legend_is_inside_the_image(tmp_path):
    """El renglón que dice el total va después de la leyenda; si no se le
    reserva alto, queda cortado por el borde de abajo -- y es justo el que
    avisa que hay más descartes de los que se ven."""
    from nesting.io.diagnostic import LEGEND_ROW_H

    out = tmp_path / "d.png"
    many = [
        Discard(reason="suelta", points=((float(i), 0.0), (float(i) + 1.0, 0.0)))
        for i in range(MAX_MARKS + 5)
    ]
    write_diagnostic(out, [square_part(0, 0, 100)], many)

    with Image.open(out) as image:
        bottom = image.convert("RGB").crop((0, image.height - LEGEND_ROW_H, image.width, image.height))
    assert any(p != (255, 255, 255) for p in bottom.getdata()), (
        "la última franja quedó en blanco: el renglón se dibujó fuera del lienzo"
    )


def test_the_window_size_is_never_truncated():
    """'[ventana 299...' se lee como 299 mm cuando en realidad son 2990.

    Es el único texto del recuadro que fija la escala de lo que se está
    mirando, así que truncarlo no lo deja incompleto: lo deja mintiendo.
    """
    from nesting.io.diagnostic import ZOOM_SIDE, _fit, _window_caption, _zoom_font

    font = _zoom_font()
    for window in (80.0, 2990.0, 123456.0):
        caption = _window_caption(window)
        assert _fit(caption, font, ZOOM_SIDE) == caption


def test_an_oversized_discard_gets_a_window_that_contains_it():
    """El rectángulo de placa mide 1830 x 2600: en una ventana fija de 80 mm
    el recuadro sale vacío, que se lee como un error del programa."""
    from nesting.io.diagnostic import _zoom_window

    plate = Discard(
        reason="contorno_placa",
        points=((0.0, 0.0), (1830.0, 0.0), (1830.0, 2600.0), (0.0, 2600.0)),
    )
    assert _zoom_window(plate) > 2600.0


def test_a_small_discard_keeps_the_fixed_window():
    """Los chicos tienen que seguir siendo comparables entre sí."""
    from nesting.io.diagnostic import ZOOM_WINDOW_MM, _zoom_window

    small = Discard(reason="suelta", points=((0.0, 0.0), (12.0, 0.0)))
    assert _zoom_window(small) == ZOOM_WINDOW_MM


def test_a_ring_discard_is_drawn_with_all_its_sides(tmp_path):
    """Integración de la propiedad `path`: el recuadro tiene que mostrar el
    cuarto lado, no tres lados y un hueco."""
    square = ((0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0))
    closed_out = tmp_path / "cerrado.png"
    open_out = tmp_path / "abierto.png"

    write_diagnostic(
        closed_out, [], [Discard(reason="area_nula", points=square, closed=True)]
    )
    write_diagnostic(
        open_out, [], [Discard(reason="area_nula", points=square, closed=False)]
    )

    color = DISCARD_STYLES["area_nula"].color
    def painted(path):
        with Image.open(path) as image:
            return sum(1 for p in image.convert("RGB").getdata() if p == color)

    assert painted(closed_out) > painted(open_out), (
        "el lado que cierra el anillo no se dibujó"
    )
