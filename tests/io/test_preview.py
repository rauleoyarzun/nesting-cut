import pytest
from PIL import Image

from nesting.io.preview import (
    BACKGROUND,
    GAP_MM,
    LABEL_BAND_PX,
    LABEL_FONT,
    MAX_CANVAS_PIXELS,
    label_lines,
    write_preview,
)
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement
from nesting.model.sheet import Sheet


HOJA = Sheet(1000.0, 1000.0, grain_tolerance=180.0)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def ring_part(part_id, outer, margin):
    m = margin
    return Part(
        part_id,
        ((0.0, 0.0), (outer, 0.0), (outer, outer), (0.0, outer)),
        (((m, m), (outer - m, m), (outer - m, outer - m), (m, outer - m)),),
        (part_id,),
    )


def test_writes_a_png(tmp_path):
    out = tmp_path / "preview.png"
    write_preview(out, [rect_part(0, 200.0, 100.0)],
                  [Placement(0, 0, Transform(0.0, False, 50.0, 50.0))],
                  [HOJA], [0.02])

    assert out.exists()
    assert Image.open(out).format == "PNG"


def test_the_image_widens_with_more_sheets(tmp_path):
    parts = [rect_part(0, 100.0, 100.0), rect_part(1, 100.0, 100.0)]
    placements_one = [Placement(0, 0, Transform(0.0, False, 10.0, 10.0))]
    placements_two = placements_one + [Placement(1, 1, Transform(0.0, False, 10.0, 10.0))]

    one = tmp_path / "one.png"
    two = tmp_path / "two.png"
    write_preview(one, parts, placements_one, [HOJA], [0.01])
    write_preview(two, parts, placements_two, [HOJA] * 2, [0.01, 0.01])

    assert Image.open(two).width > Image.open(one).width


def test_a_part_is_actually_drawn(tmp_path):
    out = tmp_path / "preview.png"
    write_preview(out, [rect_part(0, 800.0, 800.0)],
                  [Placement(0, 0, Transform(0.0, False, 100.0, 100.0))],
                  [HOJA], [0.64], colors={0: (255, 0, 0)})

    image = Image.open(out).convert("RGB")
    reds = sum(1 for pixel in image.getdata() if pixel == (255, 0, 0))
    assert reds > 100


def test_the_y_axis_is_not_flipped(tmp_path):
    """Una pieza abajo en el modelo tiene que verse abajo en la imagen."""
    out = tmp_path / "preview.png"
    write_preview(out, [rect_part(0, 900.0, 200.0)],
                  [Placement(0, 0, Transform(0.0, False, 50.0, 50.0))],
                  [HOJA], [0.18], colors={0: (255, 0, 0)})

    image = Image.open(out).convert("RGB")
    rows = [y for y in range(image.height)
            for x in range(image.width) if image.getpixel((x, y)) == (255, 0, 0)]
    assert rows
    assert sum(rows) / len(rows) > image.height * 0.5, "la masa roja esta en la mitad de abajo"


def test_a_hole_is_drawn_as_a_hole(tmp_path):
    out = tmp_path / "preview.png"
    write_preview(out, [ring_part(0, 800.0, 200.0)],
                  [Placement(0, 0, Transform(0.0, False, 100.0, 100.0))],
                  [HOJA], [0.48], colors={0: (255, 0, 0)})

    image = Image.open(out).convert("RGB")
    # El centro de la pieza cae en el agujero y no debe estar pintado.
    centre = image.getpixel((int(image.width * 0.5), int(image.height * 0.5)))
    assert centre != (255, 0, 0)


def test_an_empty_layout_still_writes_an_image(tmp_path):
    out = tmp_path / "preview.png"
    write_preview(out, [], [], [HOJA], [])
    assert out.exists()


def test_a_finer_scale_produces_a_bigger_image(tmp_path):
    part = rect_part(0, 100.0, 100.0)
    placement = [Placement(0, 0, Transform(0.0, False, 10.0, 10.0))]

    small = tmp_path / "small.png"
    large = tmp_path / "large.png"
    write_preview(small, [part], placement, [HOJA], [0.01], px_per_mm=0.1)
    write_preview(large, [part], placement, [HOJA], [0.01], px_per_mm=0.4)

    assert Image.open(large).width > Image.open(small).width


def _nested_in_hole_scene():
    """Anillo 800x800 con hueco 200..600, y una pieza chica de 100x100
    centrada exactamente en ese hueco. Ambas piezas quedan centradas en la
    placa de 1000x1000 mm (igual que en test_a_hole_is_drawn_as_a_hole)."""
    ring = ring_part(0, 800.0, 200.0)
    small = rect_part(1, 100.0, 100.0)
    ring_placement = Placement(0, 0, Transform(0.0, False, 100.0, 100.0))
    # El centro del hueco del anillo cae en la coordenada de placa (500, 500);
    # centramos ahi el rectangulo chico (que mide 100x100, centro local (50,50)).
    small_placement = Placement(1, 0, Transform(0.0, False, 450.0, 450.0))
    return [ring, small], ring_placement, small_placement


def _sheet_centre_pixel(image):
    """El centro de LA PLACA, no del lienzo entero: el lienzo incluye la
    franja de texto de utilizacion debajo de la placa, asi que su propio
    centro vertical queda corrido respecto del centro de la placa."""
    return (image.width // 2, (image.height - LABEL_BAND_PX) // 2)


def test_a_part_nested_in_a_hole_is_drawn_small_before_big(tmp_path):
    """Hallazgo 1: si la pieza chica aparece ANTES que la grande en la lista
    de colocaciones, antes se perdia por completo detras del relleno del
    hueco de la pieza grande."""
    parts, ring_placement, small_placement = _nested_in_hole_scene()
    out = tmp_path / "preview.png"
    write_preview(out, parts, [small_placement, ring_placement],
                  [HOJA], [0.48], colors={0: (255, 0, 0), 1: (0, 0, 255)})

    image = Image.open(out).convert("RGB")
    centre = image.getpixel(_sheet_centre_pixel(image))
    assert centre == (0, 0, 255)


def test_a_part_nested_in_a_hole_is_drawn_big_before_small(tmp_path):
    """Mismo caso que el anterior pero con el orden de colocaciones invertido:
    tiene que verse igual, porque el orden de dibujo no depende del orden de
    la lista que recibe la funcion."""
    parts, ring_placement, small_placement = _nested_in_hole_scene()
    out = tmp_path / "preview.png"
    write_preview(out, parts, [ring_placement, small_placement],
                  [HOJA], [0.48], colors={0: (255, 0, 0), 1: (0, 0, 255)})

    image = Image.open(out).convert("RGB")
    centre = image.getpixel(_sheet_centre_pixel(image))
    assert centre == (0, 0, 255)


def test_an_unknown_part_id_warns_but_still_draws_the_rest(tmp_path):
    out = tmp_path / "preview.png"
    part = rect_part(0, 800.0, 800.0)
    known = Placement(0, 0, Transform(0.0, False, 100.0, 100.0))
    unknown = Placement(99, 0, Transform(0.0, False, 100.0, 100.0))

    with pytest.warns(UserWarning, match="99"):
        write_preview(out, [part], [known, unknown],
                      [HOJA], [0.64], colors={0: (255, 0, 0)})

    image = Image.open(out).convert("RGB")
    reds = sum(1 for pixel in image.getdata() if pixel == (255, 0, 0))
    assert reds > 100


def test_a_negative_sheet_index_raises_instead_of_drawing_on_another_sheet(tmp_path):
    """Hallazgo A: un indice negativo no debe indexar desde el final en
    silencio, tiene que levantar como los otros dos consumidores."""
    out = tmp_path / "preview.png"
    part = rect_part(0, 200.0, 100.0)
    placement = Placement(0, -1, Transform(0.0, False, 50.0, 50.0))

    with pytest.raises(ValueError, match="-1"):
        write_preview(out, [part], [placement], [HOJA], [0.02])


def test_a_sheet_index_past_the_end_raises_value_error(tmp_path):
    """Hallazgo A: el IndexError de una placa fuera de rango tiene que
    convertirse en ValueError, que es lo que cli.py y corredor.py atrapan
    para degradar el fallo de la vista previa a un aviso."""
    out = tmp_path / "preview.png"
    part = rect_part(0, 200.0, 100.0)
    placement = Placement(0, 1, Transform(0.0, False, 50.0, 50.0))

    with pytest.raises(ValueError, match="1"):
        write_preview(out, [part], [placement], [HOJA], [0.02])


def test_a_scale_over_the_pixel_cap_raises(tmp_path):
    out = tmp_path / "preview.png"
    with pytest.raises(ValueError, match="px_per_mm"):
        write_preview(out, [], [], [HOJA], [], px_per_mm=50.0)


def test_a_reasonable_scale_is_not_blocked_by_the_cap(tmp_path):
    out = tmp_path / "preview.png"
    write_preview(out, [rect_part(0, 200.0, 100.0)],
                  [Placement(0, 0, Transform(0.0, False, 50.0, 50.0))],
                  [HOJA], [0.02])

    assert out.exists()
    image = Image.open(out)
    assert image.width * image.height <= MAX_CANVAS_PIXELS


def test_el_lienzo_acomoda_placas_de_medidas_distintas(tmp_path):
    from PIL import Image

    from nesting.model.sheet import Sheet

    hojas = [
        Sheet(600.0, 800.0, grain_tolerance=180.0, scrap=True),
        Sheet(1830.0, 2600.0, grain_tolerance=180.0),
    ]
    salida = tmp_path / "preview.png"
    write_preview(salida, [], [], hojas, [0.0, 0.0], px_per_mm=0.1)

    with Image.open(salida) as imagen:
        ancho, alto = imagen.size

    # El ancho suma los dos anchos más tres separaciones; el alto lo pone la
    # placa más alta, no la primera.
    assert ancho == pytest.approx(round(600 * 0.1) + round(1830 * 0.1) + 3 * 8, abs=4)
    assert alto > round(2600 * 0.1)


# --- la franja de etiquetas con placas de anchos distintos ---

RECORTE_CHICO = Sheet(300.0, 400.0, grain_tolerance=180.0, scrap=True)
RECORTE_MEDIANO = Sheet(450.0, 400.0, grain_tolerance=180.0, scrap=True)
PLACA_ENTERA = Sheet(1830.0, 2600.0, grain_tolerance=180.0)
ESCENA_RECORTES = [RECORTE_CHICO, RECORTE_MEDIANO, PLACA_ENTERA]


def test_la_etiqueta_entra_en_el_ancho_de_su_placa():
    """El caso estrella de la rama: dos recortes chicos y una placa entera.

    A 0.15 px/mm el recorte de 300 mm mide 45 px y la etiqueta de una sola
    línea medía 65: se metía adentro de la placa siguiente y la franja salía
    `Placa 1  72.0Placa 2  77.0%`. Ninguna línea puede ser más ancha que la
    placa que rotula.
    """
    for indice, hoja in enumerate(ESCENA_RECORTES):
        ancho_px = round(hoja.width * 0.15)
        lineas = label_lines(indice, hoja, 0.72, ancho_px)
        assert lineas
        for linea in lineas:
            assert LABEL_FONT.getlength(linea) <= ancho_px, (indice, linea)


def test_la_etiqueta_dice_cuando_la_placa_es_un_recorte():
    """El PNG es lo que el usuario mira y lo que manda al taller: si no dice
    cuál placa era un recorte, el dato sólo existe en la línea de texto de la
    pantalla y se pierde en el camino."""
    recorte = label_lines(0, RECORTE_CHICO, 0.72, round(300 * 0.15))
    entera = label_lines(2, PLACA_ENTERA, 0.72, round(1830 * 0.15))

    assert any("recorte" in linea for linea in recorte)
    assert not any("recorte" in linea for linea in entera)
    assert any("Placa 1" in linea for linea in recorte)
    assert any("72.0%" in linea for linea in entera)


def test_las_etiquetas_no_invaden_la_separacion_entre_placas(tmp_path):
    """Lo mismo, pero mirando el PNG: en las columnas de separación entre una
    placa y la siguiente no puede haber tinta. Con la etiqueta de una sola
    línea, la de la placa 1 cruzaba entera esa separación y se solapaba con
    la de la placa 2."""
    salida = tmp_path / "preview.png"
    write_preview(salida, [], [], ESCENA_RECORTES, [0.72, 0.77, 1.0])

    imagen = Image.open(salida).convert("RGB")
    gap_px = max(1, round(GAP_MM * 0.15))
    anchos = [round(h.width * 0.15) for h in ESCENA_RECORTES]

    x = gap_px
    separaciones = []
    for ancho in anchos:
        # +1 para saltear el borde dibujado de la placa, que cae justo en
        # `x + ancho` y es tinta legítima.
        separaciones.append((x + ancho + 1, x + ancho + gap_px))
        x += ancho + gap_px

    for desde, hasta in separaciones:
        for px in range(desde, min(hasta, imagen.width)):
            columna = {imagen.getpixel((px, y)) for y in range(imagen.height)}
            assert columna == {BACKGROUND}, f"hay tinta en la separación, x={px}"
