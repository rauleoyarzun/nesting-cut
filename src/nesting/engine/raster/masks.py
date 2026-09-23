"""Turn an exact polygon into the two bitmaps the collision test needs.

The polygon stays the source of truth: these masks are a derived cache, rebuilt
from the polygon at every angle rather than rotated as images, which would
accumulate artefacts and quietly drift from the real geometry.
"""

import math
import threading
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, binary_erosion

from nesting.geometry.transform import apply_points
from nesting.model.entities import Point, Transform
from nesting.model.part import Part

# Factor de supermuestreo para el rasterizado (ver el comentario grande en
# `rasterize`): Pillow dibuja en una grilla SUPERSAMPLE veces mas fina por
# lado que la final, y despues se reduce a la resolucion pedida. 4 deja el
# error de Pillow en el orden de 1/4 de pixel final, muy por debajo del
# margen que da la dilatacion/erosion de seguridad de 1 pixel final -- y el
# barrido adversarial de `test_masks.py` (resoluciones de hasta 0.4 mm/px,
# angulos arbitrarios, agujeros descentrados y paredes finas) da cero
# faltantes con este valor. Subirlo reduciria el error de Pillow todavia
# mas, pero a costa de N**2 en tiempo y memoria de rasterizado; no hizo
# falta para pasar el barrido.
SUPERSAMPLE = 4

INFLACION_MAX_PX = 2
"""Cuántos píxeles finales, por lado, puede `occupied` extenderse más allá
del polígono exacto. Es el precio de que nunca sub-represente el material.

Se compone de dos pasos, uno cada uno:

  1. `_downsample_any`: un píxel final se marca si CUALQUIERA de sus
     SUPERSAMPLE**2 subpíxeles está marcado, así que el borde puede
     ganar un píxel final.
  2. La dilatación de seguridad de 3x3 sobre `outer_mask`: exactamente uno
     más, por construcción.

No es una estimación: es la cota de esos dos pasos. Medido sobre un cuadrado
de 100 mm, `occupied` mide 106 mm a 2 mm/px (3 mm por lado = 1.5 px, contra
esta cota de 2 px) y 103 mm a 1 mm/px.

Lo usa `radio_optimista` para saber cuánto puede recortar del halo de
holgura sin perder posiciones factibles. Si algún día cambia el pipeline de
rasterizado, este número tiene que cambiar con él, o el motor híbrido
empieza a descartar posiciones buenas en silencio.
"""

# Tope de pixeles de la grilla de rasterizado, para no comernos toda la
# memoria con una combinacion patologica de resolucion fina + pieza grande.
#
# Este tope se aplica a la grilla FINA (la que Pillow dibuja de verdad, ya
# multiplicada por SUPERSAMPLE**2), no a la final, porque es la fina la que
# determina cuanta memoria y tiempo de rasterizado hacen falta -- ver el
# comentario grande en `rasterize`.
#
# Criterio, medido con este mismo modulo ya con supermuestreo activado (ver
# el informe de la tarea 15): una pieza de 300x300 mm a 1 mm/px -- ya grande
# para el catalogo -- pide una grilla fina de apenas ~1.5 millones de
# pixeles y tarda unos pocos milisegundos. El tope
# anterior (600_000_000, pensado para la grilla final antes de supermuestrear)
# ya rechazaba la combinacion patologica de referencia -- una pieza de
# 500x500 mm a 0.02 mm/px con sep=2 -- sobre la grilla final; esa misma
# combinacion, ahora sobre la grilla fina, pide ~16x mas pixeles y sigue
# rechazada con margen de sobra. Se mantiene el mismo valor numerico: ya
# rechazaba lo patologico, y subirlo 16x para preservar el caso limite de
# placa completa a 0.1 mm/px (que nunca se ejercita en la practica: el
# tamano de placa mas grande del catalogo a la resolucion por defecto de
# 1 mm/px pide solo ~4.8 millones de pixeles finales, ~76 millones de
# pixeles finos) arriesgaria memoria en el caso patologico que este tope
# existe para cortar. Si algun dia hace falta rasterizar una placa entera a
# 0.1 mm/px, hay que subir este numero a proposito, con la memoria
# disponible en mente, no por accidente.
MAX_GRID_PIXELS = 600_000_000

# Presupuesto de memoria por defecto de MaskCache, en bytes. Del orden de
# unos cientos de MB: suficiente para cachear muchas piezas/orientaciones sin
# arriesgarse a que la caché sola se coma varios GB (ver Hallazgo 4).
DEFAULT_CACHE_BUDGET_BYTES = 256 * 1024 * 1024

CONTACT_BAND_MM = 3.0
"""How far beyond the clearance halo the contact term (`scoring.contact_band`)
looks for material already placed, to reward a part resting against it.

Lives here rather than in the oracle so that `rasterize` can size its own
padding to leave room for it (see `contact_band_px` and `pad` in `rasterize`
below). `contact_band` dilates `clearance` a little further out to draw that
ring; without this margin, `clearance` already reaches exactly to the edge of
its own array (by design -- `pad` there is sized just tight enough for
`clearance` itself, see the comment on `pad`), leaving no pixel "outside" to
draw the ring on, no matter how `contact_band` is implemented -- see
`test_contact_pulls_the_part_against_existing_material` in
tests/engine/raster/test_scoring.py, which spells out exactly that
requirement for whoever builds the mask it's given.
"""


def contact_band_px(resolution: float) -> int:
    """`CONTACT_BAND_MM` in pixels, at least 1 so the band never vanishes at
    a coarse resolution."""
    return max(1, round(CONTACT_BAND_MM / resolution))


def radio_optimista(sep: float, resolution: float) -> int:
    """Radio de holgura, en píxeles, que NO pierde ninguna posición factible.

    La holgura conservadora usa `ceil(sep / resolution)`, que sumada a la
    inflación de las DOS piezas involucradas exige `sep + 2 * inflación` de
    distancia real. Acá se recorta exactamente esa inflación doble, así el
    conjunto de candidatos pasa a ser un superconjunto del factible real
    -- ver el argumento completo en `RasterOracle._buscar_con`.

    Nunca baja de 0: con una separación chica frente a la resolución, el
    recorte se come el halo entero y el candidato queda a cargo del árbitro
    exacto, que es justamente quien sabe decidir.
    """
    holgura_mm = sep - 2 * INFLACION_MAX_PX * resolution
    if holgura_mm <= 0.0:
        return 0
    return math.floor(holgura_mm / resolution)


@dataclass(frozen=True)
class PartMasks:
    """The material footprint and its clearance halo, on one shared grid."""

    occupied: np.ndarray
    """True where there is real material. Stamped onto the sheet when placed."""

    clearance: np.ndarray
    """`occupied` dilated by the separation. Used to test collisions."""

    origin: Point
    """World coordinate of pixel [0, 0], for a part translated by (0, 0)."""

    resolution: float

    pad: int
    """Pixels of zero border that surround the material's tight bounding box
    on every side of this grid, the same `pad` used when the grid was built.

    `clearance` can use up to this many pixels beyond `occupied`'s tight
    footprint before the mask array's own edge would clip it (see `rasterize`
    for why that padding was sized this way). The oracle needs this same
    number to let a part's clearance halo hang off the edge of the usable
    area without also letting its material do the same — see
    `RasterOracle._search`. Exposed here instead of re-derived in the oracle
    from `radius`/`sep` so the two modules can't quietly compute two
    different numbers for the same padding.
    """

    def holgura_optimista(self, radio_px: int) -> np.ndarray:
        """`occupied` dilatado por `radio_px`, para la búsqueda de candidatos.

        Es `clearance` con el radio recortado: admite posiciones de más, que
        el árbitro exacto descarta. Se calcula acá y no se cachea porque
        depende del radio, y el radio depende de la config, no de la pieza.

        El arreglo sale del mismo tamaño que `clearance` -- dilatar `occupied`
        con un radio MENOR que el conservador nunca se sale de `pad`, que ya
        está dimensionado para el conservador -- así que las dos holguras se
        pueden usar indistintamente en la misma ventana correlacionada.
        """
        if radio_px <= 0:
            return self.occupied.copy()
        return binary_dilation(self.occupied, structure=disk_kernel(radio_px))

    def translation_for(self, px: int, py: int) -> Point:
        """The (dx, dy) that lands pixel [0, 0] of this mask on sheet pixel (px, py)."""
        return (
            px * self.resolution - self.origin[0],
            py * self.resolution - self.origin[1],
        )


def disk_kernel(radius_px: int) -> np.ndarray:
    """A round structuring element, so clearance is isotropic."""
    if radius_px <= 0:
        return np.ones((1, 1), dtype=bool)
    grid = np.ogrid[-radius_px:radius_px + 1, -radius_px:radius_px + 1]
    rows, cols = grid
    return (rows * rows + cols * cols) <= radius_px * radius_px


def _downsample_any(fine: np.ndarray, factor: int) -> np.ndarray:
    """Reduce `fine` by `factor` per side: a final pixel is set if ANY of its
    `factor x factor` sub-pixels is set. Usado para el exterior: cubrir de
    mas es el lado seguro (ver `rasterize`)."""
    height, width = fine.shape
    return fine.reshape(height // factor, factor, width // factor, factor).any(
        axis=(1, 3)
    )


def _downsample_all(fine: np.ndarray, factor: int) -> np.ndarray:
    """Reduce `fine` by `factor` per side: a final pixel is set only if ALL of
    its `factor x factor` sub-pixels are set. Usado para los agujeros: cubrir
    de menos es el lado seguro (ver `rasterize`)."""
    height, width = fine.shape
    return fine.reshape(height // factor, factor, width // factor, factor).all(
        axis=(1, 3)
    )


def rasterize(
    part: Part, angle: float, mirror: bool, resolution: float, sep: float
) -> PartMasks:
    """Build both masks for `part` at this orientation."""
    if resolution <= 0.0:
        raise ValueError(f"la resolución debe ser positiva, se recibió {resolution}")
    if sep < 0.0:
        raise ValueError(f"la separación (sep) debe ser >= 0, se recibió {sep}")

    transform = Transform(angle, mirror, 0.0, 0.0)
    outer = apply_points(transform, part.outer)
    holes = [apply_points(transform, hole) for hole in part.holes]

    radius = math.ceil(sep / resolution) if sep > 0.0 else 0
    # +1: espacio de sobra para la dilatacion de seguridad de `occupied`
    # (ver mas abajo) antes de dilatar de nuevo para `clearance`.
    # + contact_band_px(...): espacio de sobra DESPUES de `clearance`, para
    # que `scoring.contact_band` tenga donde dibujar el anillo de contacto
    # (ver `CONTACT_BAND_MM`). Sin este termino, `clearance` llega justo al
    # borde del arreglo y no queda ningun pixel afuera para esa banda.
    pad = max(1, radius) + 1 + contact_band_px(resolution)
    min_x = min(p[0] for p in outer)
    min_y = min(p[1] for p in outer)
    max_x = max(p[0] for p in outer)
    max_y = max(p[1] for p in outer)

    origin = (min_x - pad * resolution, min_y - pad * resolution)
    width = math.ceil((max_x - min_x) / resolution) + 2 * pad + 1
    height = math.ceil((max_y - min_y) / resolution) + 2 * pad + 1

    # Se rasteriza en una grilla SUPERSAMPLE veces mas fina que la final y
    # despues se reduce -- ver el comentario grande mas abajo sobre por que
    # no alcanza con confiar en que el relleno de Pillow acierte al pixel.
    fine_resolution = resolution / SUPERSAMPLE
    fine_width = width * SUPERSAMPLE
    fine_height = height * SUPERSAMPLE

    # El tope de tamano de grilla se aplica a la grilla FINA: es ella la que
    # Pillow rasteriza de verdad y la que domina memoria y tiempo (ver
    # MAX_GRID_PIXELS).
    fine_pixel_count = fine_width * fine_height
    if fine_pixel_count > MAX_GRID_PIXELS:
        raise ValueError(
            "la grilla de rasterizado es demasiado grande: la pieza mide "
            f"{max_x - min_x:.1f}x{max_y - min_y:.1f} mm y con resolución "
            f"{resolution} mm/px (supermuestreada x{SUPERSAMPLE} para "
            f"rasterizar) saldría una grilla fina de {fine_width}x{fine_height} "
            f"= {fine_pixel_count:,} píxeles (tope: {MAX_GRID_PIXELS:,}). "
            "Probá con una resolución más gruesa."
        )

    # El exterior y los agujeros se dibujan en mascaras SEPARADAS (no la misma
    # imagen con fill=1 / fill=0) porque cada uno necesita la operacion
    # morfologica opuesta despues -- ver el comentario grande mas abajo. Si
    # se dibujaran juntos no habria forma de tratarlos distinto.
    outer_image = Image.new("1", (fine_width, fine_height), 0)
    ImageDraw.Draw(outer_image).polygon(
        _to_pixels(outer, origin, fine_resolution), fill=1
    )
    outer_fine = np.array(outer_image, dtype=bool)

    holes_image = Image.new("1", (fine_width, fine_height), 0)
    holes_draw = ImageDraw.Draw(holes_image)
    for hole in holes:
        holes_draw.polygon(_to_pixels(hole, origin, fine_resolution), fill=1)
    holes_fine = np.array(holes_image, dtype=bool)

    # Reduccion de la grilla fina a la final. La direccion del criterio de
    # reduccion tiene que ser la misma que la de la dilatacion/erosion de
    # seguridad de mas abajo, por la misma razon: el exterior tiene que
    # cubrir de mas ("cualquiera" de los N*N subpixeles alcanza para
    # marcar el pixel final) y el agujero tiene que cubrir de menos ("todos"
    # los N*N subpixeles tienen que estar marcados). Ver `_downsample_any` /
    # `_downsample_all`.
    outer_mask = _downsample_any(outer_fine, SUPERSAMPLE)
    holes_mask = _downsample_all(holes_fine, SUPERSAMPLE)

    # Por que supermuestrear en primer lugar: Pillow rasteriza por scanline,
    # y su semantica de relleno exacta no esta especificada ni acotada por
    # ningun contrato -- version anterior de este modulo asumia que el error
    # estaba acotado a ~1 pixel FINAL y lo compensaba con una sola
    # dilatacion/erosion de seguridad de radio 1. Un barrido mas exigente
    # (mas resoluciones, mas angulos) encontro faltantes de material real de
    # todos modos (hasta 94 pixeles faltantes en una sola combinacion, sobre
    # una pieza en L con 3 agujeros). En vez de seguir cazando el proximo
    # angulo/resolucion que rompe el supuesto, se deja de depender de que
    # Pillow acierte al pixel: se rasteriza SUPERSAMPLE**2 veces mas fino y
    # se reduce con un criterio conservador, asi el error de Pillow queda en
    # el orden de 1/SUPERSAMPLE de pixel FINAL -- muy por debajo de la
    # dilatacion/erosion de seguridad de 1 pixel final, que ahora lo cubre
    # con margen de sobra en vez de justo.
    #
    # La propiedad que el motor entero necesita es que `occupied` nunca
    # represente MENOS material del que hay: sub-representar deja que el
    # motor superponga piezas contra una pared que en realidad esta ahi.
    # Sobre-representar es seguro, solo cuesta densidad de empaquetado. Pero
    # el exterior y los agujeros contribuyen a `occupied` con signos
    # opuestos, asi que "cubrir de mas" con el mismo relleno inclusivo de
    # Pillow en los dos significa cosas opuestas para esa propiedad:
    #
    #   - El exterior SUMA material: dilatarlo (cubrir de mas) solo agranda
    #     la pieza. Sigue siendo seguro, y ya estaba asi.
    #   - Un agujero RESTA material: si tambien se "cubre de mas" -- que es
    #     lo que el relleno inclusivo de Pillow hace por default -- se estaria
    #     restando de mas, es decir borrando pixeles que son material real.
    #     Eso es exactamente lo peligroso: el motor cree que ahi no hay nada
    #     y coloca otra pieza mas cerca de la pared de lo permitido.
    #
    # Por eso el agujero se EROSIONA en vez de dilatarse: encogerlo antes de
    # restarlo hace que cubra de MENOS, asi que nunca se borra material de
    # mas. La contrapartida (y es la contrapartida correcta) es que el
    # agujero queda un pixel mas chico por lado de lo que es en realidad --
    # sobre-representa el material solido, nunca lo sub-representa.
    #
    # Caso limite: un agujero mas chico que el radio de erosion puede
    # desaparecer por completo (la erosion lo vacia a todo-False). Eso NO es
    # un bug: un agujero que desaparece se trata como material macizo en vez
    # de espacio libre, que es el resultado conservador. La pieza
    # simplemente no puede aprovecharse por dentro de un agujero asi de
    # chico; nunca se genera la situacion peligrosa de creer que hay mas
    # espacio libre del que realmente hay.
    safety = np.ones((3, 3), dtype=bool)
    outer_mask = binary_dilation(outer_mask, structure=safety)
    holes_mask = binary_erosion(holes_mask, structure=safety)

    occupied = outer_mask & ~holes_mask

    clearance = (
        binary_dilation(occupied, structure=disk_kernel(radius))
        if radius > 0
        else occupied.copy()
    )

    return PartMasks(
        occupied=occupied,
        clearance=clearance,
        origin=origin,
        resolution=resolution,
        pad=pad,
    )


def _to_pixels(
    points: tuple[Point, ...], origin: Point, resolution: float
) -> list[tuple[float, float]]:
    """Map world points to (column, row). Row grows with y, as everything assumes.

    Pasan tal cual a Pillow, sin ninguna contraccion hacia el centroide. Una
    version anterior encogia los anillos por 1e-6 para que un lado alineado
    a la grilla no se auto-incluyera dos veces en el scanline de Pillow, pero
    esa contraccion se aplicaba a todo lado -- incluidos los diagonales -- y
    ahi empeoraba justo el problema que `rasterize` tiene que evitar: mas
    pixeles cuyo centro cae dentro del poligono exacto quedaban sin marcar
    (medido: un rectangulo rotado 33 grados pasaba de 12 a 29 pixeles
    faltantes). El relleno inclusivo de Pillow sobre-representa un poco en
    el caso alineado a la grilla, lo cual es el lado seguro; la dilatacion
    de seguridad en `rasterize` ya cubre el caso diagonal.
    """
    return [
        ((x - origin[0]) / resolution, (y - origin[1]) / resolution) for x, y in points
    ]


def _masks_nbytes(masks: PartMasks) -> int:
    """Bytes actually held by one cache entry (both arrays, not entry count)."""
    return masks.occupied.nbytes + masks.clearance.nbytes


class MaskCache:
    """Reuse masks across the many times the packer asks about the same orientation.

    Masks are the memory hot spot: a part with 24 allowed angles and mirroring
    has 48 entries, and each entry's size depends entirely on the part's
    bounding box and the resolution -- a sheet-sized part at a fine
    resolution can weigh tens of megabytes, while a small part weighs almost
    nothing. Bounding the cache by entry *count* is blind to that: a full
    cache of sheet-sized entries can be gigabytes. So the cache is bounded by
    *bytes* instead, and evicts least-recently-used entries until it fits.

    Es seguro entre hilos: las consultas de una pieza corren en hilos
    (`packer._query_orientations`), y `warm` sólo evita las altas
    concurrentes cuando todas las orientaciones de la pieza entran en el
    presupuesto. A una resolución fina no entran, y sin el cerrojo un hilo
    podía expulsar la clave que otro estaba por mover al final (`KeyError`)
    o dos altas a la vez perder una suma de `_nbytes`. El cerrojo cubre
    también el rasterizado: con `warm` adelante casi nunca se rasteriza desde
    un hilo, y así dos hilos no rasterizan la misma orientación dos veces.
    """

    def __init__(self, max_bytes: int = DEFAULT_CACHE_BUDGET_BYTES) -> None:
        self._entries: OrderedDict[tuple, PartMasks] = OrderedDict()
        self._max_bytes = max_bytes
        self._nbytes = 0
        self._lock = threading.Lock()

    def get(
        self, part: Part, angle: float, mirror: bool, resolution: float, sep: float
    ) -> PartMasks:
        # La pieza misma entra en la clave (no `part.id`) porque `Part` es un
        # dataclass frozen de tuplas, o sea hashable, y su geometria tiene
        # que formar parte de la identidad: si dos `Part` distintos
        # comparten `id` por error, indexar solo por `id` devolveria la
        # mascara de la pieza equivocada sin ningun aviso (Hallazgo 2).
        key = (part, angle, mirror, resolution, sep)
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached

            masks = rasterize(part, angle, mirror, resolution, sep)
            self._entries[key] = masks
            self._nbytes += _masks_nbytes(masks)
            while self._nbytes > self._max_bytes and len(self._entries) > 1:
                _, evicted = self._entries.popitem(last=False)
                self._nbytes -= _masks_nbytes(evicted)
            return masks
