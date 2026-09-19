"""Render the layout to a PNG, so a bad result is obvious at a glance."""

import warnings
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw

from nesting.geometry.transform import apply_points
from nesting.model.entities import Point
from nesting.model.part import Part, Placement

BACKGROUND = (250, 250, 250)
SHEET_FILL = (232, 232, 232)
SHEET_EDGE = (120, 120, 120)
DEFAULT_PART = (150, 150, 150)
PART_EDGE = (40, 40, 40)
GAP_MM = 80.0
LABEL_BAND_PX = 18

# Pillow itself refuses to *open* an image above roughly 89.5 Mpx
# (PIL.Image.MAX_IMAGE_PIXELS, its decompression-bomb guard), so writing a
# canvas bigger than that produces a PNG this same project cannot read back.
# Stay comfortably under that line rather than riding right up to it.
MAX_CANVAS_PIXELS = 80_000_000


def write_preview(
    path: str | Path,
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheet_w: float,
    sheet_h: float,
    utilization: Sequence[float],
    colors: dict[int, tuple[int, int, int]] | None = None,
    px_per_mm: float = 0.15,
) -> None:
    """Draw every sheet side by side, with its utilisation underneath."""
    colors = colors or {}
    sheets = max(len(utilization), max((p.sheet for p in placements), default=-1) + 1, 1)

    sheet_px_w = max(1, round(sheet_w * px_per_mm))
    sheet_px_h = max(1, round(sheet_h * px_per_mm))
    gap_px = max(1, round(GAP_MM * px_per_mm))

    width = sheets * sheet_px_w + (sheets + 1) * gap_px
    height = sheet_px_h + 2 * gap_px + LABEL_BAND_PX

    total_pixels = width * height
    if total_pixels > MAX_CANVAS_PIXELS:
        suggested = px_per_mm * (MAX_CANVAS_PIXELS / total_pixels) ** 0.5
        raise ValueError(
            f"la placa de {sheet_w:.0f}x{sheet_h:.0f} mm con px_per_mm={px_per_mm} "
            f"generaría un lienzo de {width}x{height} px (~{total_pixels / 1e6:.1f} Mpx), "
            f"por encima del límite de {MAX_CANVAS_PIXELS / 1e6:.1f} Mpx que admite esta "
            f"función (Pillow luego se niega a abrir imágenes más grandes que eso). "
            f"Use un px_per_mm de a lo sumo {suggested:.4f} para esta placa."
        )

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    for index in range(sheets):
        left = gap_px + index * (sheet_px_w + gap_px)
        top = gap_px
        draw.rectangle(
            [left, top, left + sheet_px_w, top + sheet_px_h],
            fill=SHEET_FILL, outline=SHEET_EDGE,
        )
        if index < len(utilization):
            draw.text(
                (left, top + sheet_px_h + 4),
                f"Placa {index + 1}   {utilization[index] * 100:.1f}%",
                fill=(60, 60, 60),
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

        origin_x = gap_px + placement.sheet * (sheet_px_w + gap_px)
        origin_y = gap_px + sheet_px_h

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
