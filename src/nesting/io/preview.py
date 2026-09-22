"""Render the layout to a PNG, so a bad result is obvious at a glance."""

import warnings
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from nesting.geometry.transform import apply_points
from nesting.model.entities import Point
from nesting.model.part import Part, Placement
from nesting.model.sheet import Sheet

BACKGROUND = (250, 250, 250)
SHEET_FILL = (232, 232, 232)
SHEET_EDGE = (120, 120, 120)
DEFAULT_PART = (150, 150, 150)
PART_EDGE = (40, 40, 40)
GAP_MM = 80.0
LABEL_BAND_PX = 18
"""Alto de la franja de texto de abajo cuando la etiqueta entra en UNA línea.

Cada línea de más agrega `LABEL_LINE_PX`."""

LABEL_LINE_PX = 11
LABEL_COLOR = (60, 60, 60)
LABEL_FONT = ImageFont.load_default()
LABEL_SEP = "   "


def label_lines(
    index: int, sheet: Sheet, fraction: float, width_px: int
) -> list[str]:
    """El rótulo de una placa, partido en líneas que entran en `width_px`.

    Dice tres cosas -- qué número de placa es, si es un recorte, y cuánto se
    aprovechó -- y las acomoda en cuantas líneas hagan falta para no pasarse
    del ancho de SU placa.

    Antes era una sola línea y alcanzaba, porque todas las placas medían lo
    mismo que el Material: cientos de píxeles de ancho. Con recortes no: a
    0.15 px/mm un recorte de 300 mm son 45 px y la línea entera medía 65, así
    que se metía adentro de la placa siguiente y la franja quedaba ilegible
    (`Placa 1  72.0Placa 2  77.0%`). Partirla es lo que la vuelve a hacer
    legible SIN achicar la letra ni recortar el texto, que en una imagen que
    va al taller es lo último que conviene hacer.

    Que diga "recorte" y no sólo el número es la otra mitad: la pantalla arma
    "2 placas (1 recorte + 1 nueva)", pero el PNG es lo que el usuario mira y
    lo que manda al taller, y ahí el dato no estaba en ningún lado. Compite
    con lo anterior -- es texto de más justo donde ya no entraba -- y por eso
    va en su propia línea cuando no entra al lado del resto.

    Un token suelto más ancho que la placa (una placa de 20 px: ni "Placa 1"
    entra) se deja igual en su línea: partir una palabra al medio o cortarla
    con puntos suspensivos sería menos legible que dejarla asomar.
    """
    tokens = [f"Placa {index + 1}"]
    if sheet.scrap:
        tokens.append("recorte")
    tokens.append(f"{fraction * 100:.1f}%")

    lines: list[str] = []
    current = tokens[0]
    for token in tokens[1:]:
        candidate = f"{current}{LABEL_SEP}{token}"
        if LABEL_FONT.getlength(candidate) > width_px:
            lines.append(current)
            current = token
        else:
            current = candidate
    lines.append(current)
    return lines

# Pillow itself refuses to *open* an image above roughly 89.5 Mpx
# (PIL.Image.MAX_IMAGE_PIXELS, its decompression-bomb guard), so writing a
# canvas bigger than that produces a PNG this same project cannot read back.
# Stay comfortably under that line rather than riding right up to it.
MAX_CANVAS_PIXELS = 80_000_000


def write_preview(
    path: str | Path,
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheets: Sequence[Sheet],
    utilization: Sequence[float],
    colors: dict[int, tuple[int, int, int]] | None = None,
    px_per_mm: float = 0.15,
) -> None:
    """Dibuja cada placa una al lado de la otra, con su aprovechamiento abajo."""
    colors = colors or {}

    anchos_px = [max(1, round(h.width * px_per_mm)) for h in sheets]
    altos_px = [max(1, round(h.height * px_per_mm)) for h in sheets]
    gap_px = max(1, round(GAP_MM * px_per_mm))
    alto_max_px = max(altos_px, default=1)

    etiquetas = {
        index: label_lines(index, hoja, utilization[index], anchos_px[index])
        for index, hoja in enumerate(sheets)
        if index < len(utilization)
    }
    banda_px = LABEL_BAND_PX + LABEL_LINE_PX * (
        max((len(l) for l in etiquetas.values()), default=1) - 1
    )

    width = sum(anchos_px) + (len(sheets) + 1) * gap_px
    height = alto_max_px + 2 * gap_px + banda_px

    total_pixels = width * height
    if total_pixels > MAX_CANVAS_PIXELS:
        suggested = px_per_mm * (MAX_CANVAS_PIXELS / total_pixels) ** 0.5
        raise ValueError(
            f"las {len(sheets)} placa(s) con px_per_mm={px_per_mm} generarían un "
            f"lienzo de {width}x{height} px (~{total_pixels / 1e6:.1f} Mpx), por "
            f"encima del límite de {MAX_CANVAS_PIXELS / 1e6:.1f} Mpx que admite "
            f"esta función (Pillow luego se niega a abrir imágenes más grandes "
            f"que eso). Use un px_per_mm de a lo sumo {suggested:.4f}."
        )

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    # Las placas se alinean ABAJO y no arriba: el motor apoya las piezas
    # contra el borde inferior, y con placas de altos distintos alinearlas
    # arriba las dejaría flotando sobre nada. Con todas iguales da
    # exactamente lo mismo que antes.
    piso = gap_px + alto_max_px
    izquierdas: list[int] = []
    x = gap_px
    for ancho_px in anchos_px:
        izquierdas.append(x)
        x += ancho_px + gap_px

    for index, (left, ancho_px, alto_px) in enumerate(
        zip(izquierdas, anchos_px, altos_px)
    ):
        draw.rectangle(
            [left, piso - alto_px, left + ancho_px, piso],
            fill=SHEET_FILL, outline=SHEET_EDGE,
        )
        for renglon, linea in enumerate(etiquetas.get(index, ())):
            draw.text(
                (left, piso + 4 + renglon * LABEL_LINE_PX),
                linea,
                fill=LABEL_COLOR,
                font=LABEL_FONT,
            )

    by_id = {p.id: p for p in parts}
    missing_ids: list[int] = []

    # Draw largest-area parts first (descending), regardless of the order
    # `placements` happens to be in. A part that nests inside another part's
    # hole is necessarily smaller than the part containing it, so this order
    # guarantees the containing part - and the hole punched through it - gets
    # painted onto the canvas before the nested part is drawn on top of it.
    # Do NOT switch this back to drawing in list order "for simplicity": with
    # nothing in the model guaranteeing placement order, that makes whether a
    # nested part survives on screen a coin flip - the container's hole-fill
    # can land on top of it and erase it, even though the DXF output is fine.
    for placement in sorted(
        placements, key=lambda pl: by_id[pl.part_id].area if pl.part_id in by_id else 0.0,
        reverse=True,
    ):
        part = by_id.get(placement.part_id)
        if part is None:
            missing_ids.append(placement.part_id)
            continue

        # ValueError a propósito: cli.py y corredor.py atrapan
        # (ValueError, OSError) alrededor de write_preview para degradar un
        # fallo de la vista previa a un aviso (el DXF ya se escribió bien).
        # Un IndexError -- o, peor, un índice negativo indexando en silencio
        # desde el final -- se les escapa de esa red.
        if not (0 <= placement.sheet < len(izquierdas)):
            raise ValueError(
                f"la colocación de la pieza {placement.part_id} dice estar en "
                f"la placa {placement.sheet}, pero se recibieron "
                f"{len(sheets)} placa(s)."
            )

        origin_x = izquierdas[placement.sheet]
        origin_y = piso

        def to_pixels(points: tuple[Point, ...]) -> list[tuple[float, float]]:
            # Image rows grow downwards while model y grows upwards, so the row
            # is measured from the bottom edge of the sheet.
            return [
                (origin_x + x * px_per_mm, origin_y - y * px_per_mm) for x, y in points
            ]

        fill = colors.get(placement.part_id, DEFAULT_PART)
        draw.polygon(to_pixels(apply_points(placement.transform, part.outer)),
                     fill=fill, outline=PART_EDGE)
        for hole in part.holes:
            draw.polygon(to_pixels(apply_points(placement.transform, hole)),
                         fill=SHEET_FILL, outline=PART_EDGE)

    if missing_ids:
        warnings.warn(
            f"se saltearon {len(missing_ids)} colocación(es) con part_id "
            f"desconocido (ej.: {missing_ids[0]}); la vista previa no incluye "
            f"esas piezas.",
            stacklevel=2,
        )

    image.save(str(path), format="PNG")
