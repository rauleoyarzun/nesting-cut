"""El PNG que explica qué se descartó del dibujo, y dónde estaba.

Los avisos de texto dicen cuántas cosas se tiraron y por qué, pero no dónde:
en un dibujo de once metros, un tramo suelto de 12 mm -- o peor, uno de 24
micrones -- es literalmente invisible. Este dibujante resuelve ese problema
con dos vistas a la vez: el plano general, donde un círculo numerado ubica
cada descarte, y una tira de recuadros con un zoom fijo de
`ZOOM_WINDOW_MM` alrededor de cada uno, que es donde el descarte se ve de
verdad y se entiende qué era.

El fondo se arma con las piezas que el programa SÍ reconoció, no
re-aplanando el archivo: así lo que se ve dibujado es exactamente lo que el
motor va a acomodar, y no una segunda lectura del archivo que podría diferir
de la primera.
"""

from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from nesting.model.discard import Discard
from nesting.model.entities import Point
from nesting.model.part import Part

PLAN_W, PLAN_H = 1800, 1150
"""Tamaño del plano general, en píxeles."""

ZOOM_SIDE = 300
"""Lado de cada recuadro de zoom, en píxeles."""

MARGIN = 14
"""Aire entre elementos y contra el borde del lienzo, en píxeles."""

LABEL_H = 50
"""Alto reservado bajo cada recuadro para sus tres renglones de etiqueta."""

LEGEND_ROW_H = 26
"""Alto de cada renglón de la leyenda."""

ZOOM_WINDOW_MM = 80.0
"""Cuántos milímetros abarca un recuadro de zoom, de lado a lado.

Fijo a propósito, y no ajustado a cada descarte: con una ventana constante
los recuadros son comparables entre sí, y el usuario aprende de una vez qué
tan grande es lo que está mirando. Ajustarla haría que un tramo de 24
micrones y uno de 12 mm se vieran del mismo tamaño, que es justo la
distinción que el dibujo tiene que dejar clara.
"""

ZOOMS_PER_ROW = (PLAN_W - MARGIN) // (ZOOM_SIDE + MARGIN)
"""Cuántos recuadros entran por fila.

Se calcula, no se elige: fijado a mano quedaba en 6 y la sexta columna
terminaba 98 px fuera del lienzo, con el recuadro partido y su etiqueta
-- la que lleva la coordenada -- perdida entera.
"""
MAX_MARKS = 30
"""Cuántos descartes llegan a tener recuadro propio.

Un archivo muy sucio puede traer cientos; dibujarlos todos daría una imagen
de varios metros de alto que ningún visor abre cómodo. Se recorta la tira de
recuadros, nunca el conteo: el resumen al pie sigue informando el total real,
así que el usuario nunca cree haber visto todo cuando no es así.
"""

FONT_CANDIDATES = (
    "DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "Arial.ttf",
    "LiberationSans-Regular.ttf",
)
"""Tipografías a probar, en orden, para el texto del diagnóstico.

Hace falta una de verdad: la que trae Pillow por omisión no tiene 'á' ni 'ñ'
y las dibuja como el cuadradito de "glifo desconocido", lo que deja la
leyenda de un programa enteramente en español ilegible justo donde explica
por qué se descartó algo. `ImageFont.truetype` busca por nombre en los
directorios de fuentes del sistema además de aceptar rutas, así que la lista
cubre Linux y macOS sin preguntar en cuál está corriendo.
"""

BACKGROUND = (255, 255, 255)
BACKDROP = (170, 170, 170)
TEXT = (40, 40, 40)
MARK_RADIUS = 26
FONT_SIZE = 16
"""Cuerpo de la leyenda. Sobre un lienzo de 1800 px, menos de esto no se lee."""

ZOOM_FONT_SIZE = 13
"""Cuerpo de las etiquetas de los recuadros de zoom.

Más chico que la leyenda porque tiene que caber en los 300 px del
recuadro, y lo que dice -- la coordenada y el largo -- es justo el dato
que el usuario necesita completo para ir a buscar la cosa en su dibujo.
Recortarlo sería peor que achicarlo.
"""


def _font(size: int) -> ImageFont.FreeTypeFont:
    """La primera de `FONT_CANDIDATES` que exista, o la de Pillow como último
    recurso -- con acentos rotos, pero sin reventar el dibujo entero por una
    tipografía faltante."""
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _zoom_font() -> ImageFont.FreeTypeFont:
    return _font(ZOOM_FONT_SIZE)


def write_diagnostic(
    path: str | Path,
    parts: Sequence[Part],
    discards: Sequence[Discard],
) -> int:
    """Dibuja `discards` sobre el contorno de `parts` y guarda el PNG en `path`.

    Devuelve cuántos descartes se pudieron marcar sobre el plano, que es
    siempre <= `len(discards)`: los que no tienen geometría en XY (una cota de
    Rhino, un tipo de entidad DXF que el lector ni convierte) se cuentan en la
    leyenda pero no se pueden señalar en ningún lado.
    """
    outlines = _backdrop(parts, discards)
    markable = [d for d in discards if d.has_geometry][:MAX_MARKS]

    rows = (len(markable) + ZOOMS_PER_ROW - 1) // ZOOMS_PER_ROW
    zoom_band = rows * (ZOOM_SIDE + LABEL_H) + (MARGIN if rows else 0)
    legend = _legend_rows(discards)
    # Un renglón extra cuando `_draw_legend` va a cerrar con el total, que es
    # justo el que avisa que hay más descartes de los que se ven marcados:
    # sin reservarle alto quedaba dibujado fuera del lienzo.
    summary_rows = 1 if len(markable) < len(discards) else 0
    legend_band = (len(legend) + summary_rows) * LEGEND_ROW_H + 2 * MARGIN

    image = Image.new("RGB", (PLAN_W, PLAN_H + zoom_band + legend_band), BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = _font(FONT_SIZE)

    to_px = _projection(outlines)
    for outline in outlines:
        if len(outline) > 1:
            draw.line([to_px(p) for p in outline], fill=BACKDROP, width=1)

    for number, discard in enumerate(markable, 1):
        _draw_mark(draw, discard, number, to_px, font)
        _draw_zoom(image, draw, discard, number, outlines, font)

    _draw_legend(draw, legend, len(discards), len(markable), PLAN_H + zoom_band, font)

    image.save(path)
    return len(markable)


def _backdrop(
    parts: Sequence[Part], discards: Sequence[Discard]
) -> list[tuple[Point, ...]]:
    """Todo lo que se dibuja en gris: las piezas reconocidas y los descartes.

    Los descartes entran al fondo además de ir marcados porque sin ellos el
    encuadre podría dejar afuera justo lo que se quiere mostrar -- un
    rectángulo de placa, por ejemplo, suele ser lo más grande del archivo.
    """
    outlines: list[tuple[Point, ...]] = []
    for part in parts:
        outlines.append(_closed(part.outer))
        outlines.extend(_closed(hole) for hole in part.holes)
    outlines.extend(d.path for d in discards if d.has_geometry)
    return outlines


def _closed(ring: Sequence[Point]) -> tuple[Point, ...]:
    """Repite el primer punto al final, que es como se dibuja un anillo."""
    if not ring:
        return ()
    return (*ring, ring[0])


def _projection(outlines: Sequence[Sequence[Point]]):
    """Función mm -> píxeles que encuadra `outlines` dentro del plano general.

    Una caja de ancho o alto cero -- un dibujo vacío, o una pieza degenerada
    que colapsó a un punto -- haría una división por cero. Se le da un tamaño
    mínimo arbitrario: no hay encuadre correcto para algo sin extensión, pero
    sí hay uno que no revienta y deja ver que no hay nada.
    """
    points = [p for outline in outlines for p in outline]
    if not points:
        return lambda p: (PLAN_W / 2.0, PLAN_H / 2.0)

    x0, x1 = min(p[0] for p in points), max(p[0] for p in points)
    y0, y1 = min(p[1] for p in points), max(p[1] for p in points)
    width = max(x1 - x0, 1e-9)
    height = max(y1 - y0, 1e-9)
    scale = min((PLAN_W - 2 * MARGIN) / width, (PLAN_H - 2 * MARGIN) / height)

    def to_px(p: Point) -> tuple[float, float]:
        return (
            MARGIN + (p[0] - x0) * scale,
            PLAN_H - MARGIN - (p[1] - y0) * scale,
        )

    return to_px


def _draw_mark(
    draw: ImageDraw.ImageDraw, discard: Discard, number: int, to_px,
    font: ImageFont.FreeTypeFont,
) -> None:
    """Un círculo con guiones a los costados, sobre el plano general.

    Los guiones salen del círculo porque a esta escala el círculo puede caer
    encima de otras piezas y perderse; los guiones lo vuelven a hacer visible
    sin taparle nada.
    """
    centroid = discard.centroid
    assert centroid is not None, "solo se marca lo que tiene geometría"
    x, y = to_px(centroid)
    color = discard.style.color
    r = MARK_RADIUS
    draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=3)
    draw.line([x - r - 18, y, x - r - 4, y], fill=color, width=2)
    draw.line([x + r + 4, y, x + r + 18, y], fill=color, width=2)
    draw.text((x + r + 22, y - 8), str(number), fill=color, font=font)


def _draw_zoom(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    discard: Discard,
    number: int,
    outlines: Sequence[Sequence[Point]],
    font: ImageFont.FreeTypeFont,
) -> None:
    """El recuadro de zoom alrededor del descarte."""
    centroid = discard.centroid
    assert centroid is not None, "solo se marca lo que tiene geometría"
    cx, cy = centroid
    color = discard.style.color

    column = (number - 1) % ZOOMS_PER_ROW
    row = (number - 1) // ZOOMS_PER_ROW
    ox = MARGIN + column * (ZOOM_SIDE + MARGIN)
    oy = PLAN_H + MARGIN + row * (ZOOM_SIDE + LABEL_H)

    window = _zoom_window(discard)
    half = window / 2.0
    scale = ZOOM_SIDE / window

    def to_px(p: Point) -> tuple[float, float]:
        return (ox + ZOOM_SIDE / 2 + (p[0] - cx) * scale,
                oy + ZOOM_SIDE / 2 - (p[1] - cy) * scale)

    # El recorte se hace por caja envolvente, no por clipping exacto: Pillow
    # dibuja fuera del recuadro sin quejarse, así que primero se dibuja y
    # después se tapa lo que se salió, recuadro por recuadro.
    panel = Image.new("RGB", (ZOOM_SIDE, ZOOM_SIDE), BACKGROUND)
    inner = ImageDraw.Draw(panel)

    def shift(p: Point) -> tuple[float, float]:
        x, y = to_px(p)
        return (x - ox, y - oy)

    for outline in outlines:
        if len(outline) > 1 and _near(outline, cx, cy, half * 2):
            inner.line([shift(p) for p in outline], fill=BACKDROP, width=1)
    path = discard.path
    if len(path) > 1:
        inner.line([shift(p) for p in path], fill=color, width=4)
    for point in discard.points:
        px, py = shift(point)
        inner.ellipse([px - 4, py - 4, px + 4, py + 4], fill=color)

    image.paste(panel, (int(ox), int(oy)))
    draw.rectangle([ox, oy, ox + ZOOM_SIDE, oy + ZOOM_SIDE], outline=color, width=2)

    small = _zoom_font()
    label = f"{number}. {discard.style.label.split('(')[0].strip()}"
    detail = f"  {discard.detail}" if discard.detail else ""
    draw.text(
        (ox + 4, oy + ZOOM_SIDE + 4), _fit(label, small, ZOOM_SIDE),
        fill=color, font=small,
    )
    draw.text(
        (ox + 4, oy + ZOOM_SIDE + 19),
        _fit(f"({cx:.0f}, {cy:.0f}) mm{detail}", small, ZOOM_SIDE),
        fill=TEXT, font=small,
    )
    # En su propio renglón, nunca compartido: es el único texto que fija la
    # escala de lo que se está mirando, así que recortarlo no lo dejaría
    # incompleto sino mintiendo ("[ventana 299..." por 2990 mm).
    draw.text(
        (ox + 4, oy + ZOOM_SIDE + 34), _window_caption(window), fill=TEXT, font=small,
    )


def _window_caption(window: float) -> str:
    return f"ventana de {window:.0f} mm de lado"


def _zoom_window(discard: Discard) -> float:
    """Cuántos milímetros abarca el recuadro de este descarte.

    `ZOOM_WINDOW_MM` mientras el descarte entre, que es el caso que importa y
    el que mantiene los recuadros comparables entre sí. Un descarte más grande
    que la ventana -- el rectángulo del tamaño de la placa es el caso típico,
    con sus 1830 x 2600 mm -- daba un recuadro completamente vacío, que se lee
    como un error del programa y no como lo que es. Para esos se agranda la
    ventana hasta que entre, y la etiqueta dice siempre cuántos milímetros
    abarca, así el usuario nunca confunde las escalas.
    """
    if not discard.points:
        return ZOOM_WINDOW_MM
    xs = [p[0] for p in discard.points]
    ys = [p[1] for p in discard.points]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    return max(ZOOM_WINDOW_MM, span * 1.15)


def _fit(text: str, font: ImageFont.FreeTypeFont, width: int) -> str:
    """Recorta `text` hasta que entre en `width` píxeles.

    Medido con la tipografía real y no por cantidad de caracteres, que con una
    tipografía proporcional no dice nada: 'illi' y 'WWWW' ocupan lo mismo en
    caracteres y el triple de ancho uno que el otro.
    """
    if font.getbbox(text)[2] <= width:
        return text
    while text and font.getbbox(text + "...")[2] > width:
        text = text[:-1]
    return text + "..."


def _near(outline: Sequence[Point], cx: float, cy: float, reach: float) -> bool:
    return any(abs(p[0] - cx) <= reach and abs(p[1] - cy) <= reach for p in outline)


def _legend_rows(discards: Sequence[Discard]) -> list[tuple[str, tuple[int, int, int], int]]:
    """Un renglón por motivo presente, con su color y cuántos hubo.

    En el orden en que aparecieron, no alfabético: así la leyenda sigue el
    orden de las marcas numeradas y el ojo no tiene que saltar.
    """
    counts: dict[str, int] = {}
    styles: dict[str, tuple[str, tuple[int, int, int]]] = {}
    for discard in discards:
        counts[discard.reason] = counts.get(discard.reason, 0) + 1
        styles.setdefault(discard.reason, (discard.style.label, discard.style.color))
    return [(styles[r][0], styles[r][1], counts[r]) for r in styles]


def _draw_legend(
    draw: ImageDraw.ImageDraw,
    rows: Sequence[tuple[str, tuple[int, int, int], int]],
    total: int,
    marked: int,
    top: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    y = top + MARGIN
    if not rows:
        draw.text(
            (MARGIN, y), "No se descartó nada: el archivo entró entero.",
            fill=TEXT, font=font,
        )
        return

    for label, color, count in rows:
        draw.rectangle([MARGIN, y + 4, MARGIN + 14, y + 18], fill=color)
        draw.text((MARGIN + 24, y + 4), f"{count} x  {label}", fill=TEXT, font=font)
        y += LEGEND_ROW_H

    if marked < total:
        draw.text(
            (MARGIN, y + 4),
            f"Se descartaron {total} en total; hay {marked} con recuadro de zoom "
            f"(los que tienen contorno en XY, hasta {MAX_MARKS}).",
            fill=TEXT, font=font,
        )
