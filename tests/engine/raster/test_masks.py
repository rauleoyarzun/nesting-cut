import itertools
import math

import numpy as np
import pytest
from shapely import contains_xy
from shapely.geometry import Polygon

from nesting.engine.raster.masks import (
    DEFAULT_CACHE_BUDGET_BYTES,
    MaskCache,
    PartMasks,
    disk_kernel,
    rasterize,
)
from nesting.geometry.transform import apply_points
from nesting.model.entities import Transform
from nesting.model.part import Part

RES = 1.0


def rect_part(w, h, part_id=0):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def ring_part(outer, hole_margin, part_id=0):
    m = hole_margin
    return Part(
        part_id,
        ((0.0, 0.0), (outer, 0.0), (outer, outer), (0.0, outer)),
        (((m, m), (outer - m, m), (outer - m, outer - m), (m, outer - m)),),
        (part_id,),
    )


def test_disk_kernel_is_round_and_odd_sized():
    kernel = disk_kernel(3)
    assert kernel.shape == (7, 7)
    assert kernel[3, 3]
    assert not kernel[0, 0], "las esquinas quedan fuera del disco"


def test_disk_kernel_of_zero_radius_is_a_single_pixel():
    assert disk_kernel(0).shape == (1, 1)
    assert disk_kernel(0).all()


def test_occupied_and_clearance_have_the_same_shape():
    masks = rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=5.0)
    assert masks.occupied.shape == masks.clearance.shape


def test_occupied_area_matches_the_part_area():
    part = rect_part(100.0, 50.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)
    pixel_area = masks.occupied.sum() * RES * RES
    # rel se relaja de 0.05 a 0.12: la dilatacion de seguridad de un pixel
    # que agrega `rasterize` (Hallazgo 1) hace que un ring de 1 px alrededor
    # de todo el perimetro pase a estar ocupado, y para una pieza chica como
    # esta (100x50 mm) ese ring pesa proporcionalmente mas que para una
    # pieza grande. Es sobre-representacion -- el lado seguro -- asi que se
    # ajusta la tolerancia del test en vez de angostar la dilatacion (que ya
    # se probo insuficiente sin las diagonales: ver la verificacion contra
    # shapely en este mismo archivo).
    assert pixel_area == pytest.approx(part.area, rel=0.12)


def test_clearance_is_strictly_bigger_than_occupied():
    masks = rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=5.0)
    assert masks.clearance.sum() > masks.occupied.sum()
    assert np.all(masks.clearance | ~masks.occupied), "clearance contiene a occupied"


def test_clearance_grows_by_roughly_the_separation():
    part = rect_part(100.0, 100.0)
    masks = rasterize(part, 0.0, False, RES, sep=10.0)
    grown = masks.clearance.sum() * RES * RES
    # Un cuadrado de 100 dilatado 10 mm: 120x120 menos las esquinas redondeadas.
    # La cota superior se relaja un poco por encima de 14400 (120x120 exacto)
    # a proposito: el relleno inclusivo de Pillow, mas la dilatacion de
    # seguridad de un pixel que agrega `rasterize` (Hallazgo 1), sobre-
    # representan un poco el area real. Sobre-representar es el lado seguro
    # -- solo cuesta densidad de empaquetado -- mientras que sub-representar
    # permitiria que el motor superponga piezas, asi que esta cota se ajusta
    # a la geometria de produccion en vez de deformarla para achicar el
    # margen.
    assert 13000 < grown < 15300


def test_a_hole_is_not_occupied():
    part = ring_part(200.0, 50.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)
    pixel_area = masks.occupied.sum() * RES * RES
    # rel se relaja de 0.05 a 0.06 por el supermuestreo (cierre del
    # conservadurismo del rasterizado): para un cuadrado y un agujero
    # perfectamente alineados a la grilla, el relleno inclusivo de Pillow
    # sobra un pixel por lado tanto en el exterior como en el agujero (ver
    # `_to_pixels`). Antes, ese sobrante se colaba igual en los dos porque
    # se rasterizaba directo a la resolucion final. Ahora que se rasteriza
    # SUPERSAMPLE veces mas fino y se reduce con criterios opuestos
    # ("cualquiera" para el exterior, "todos" para el agujero -- ver
    # `rasterize`), ese pixel sobrante del agujero puede no completar un
    # bloque entero de reduccion y perderse, mientras que el del exterior
    # sobrevive con mas facilidad. El resultado neto es un poco mas de
    # sobre-representacion que antes para este caso puntual (medido:
    # ~5.35% en vez de ~4.7%) -- sigue siendo el lado seguro, solo cuesta
    # densidad, asi que se ajusta la tolerancia en vez de angostar el
    # supermuestreo (que existe justamente para eliminar los faltantes de
    # material real, ver test_occupied_never_under_represents_under_a_harsh_sweep).
    assert pixel_area == pytest.approx(200.0**2 - 100.0**2, rel=0.06)


def test_the_centre_of_a_hole_is_free_in_both_masks():
    """La propiedad de la spec 5.2: el agujero queda disponible."""
    part = ring_part(400.0, 100.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)

    row = int((200.0 - masks.origin[1]) / RES)
    col = int((200.0 - masks.origin[0]) / RES)
    assert not masks.occupied[row, col]
    assert not masks.clearance[row, col], "el centro del agujero esta lejos de la pared"


def test_the_wall_of_a_hole_projects_clearance_inwards():
    part = ring_part(400.0, 100.0)
    masks = rasterize(part, 0.0, False, RES, sep=20.0)

    # Un punto 10 mm adentro del agujero, o sea dentro de la banda de separacion.
    row = int((110.0 - masks.origin[1]) / RES)
    col = int((200.0 - masks.origin[0]) / RES)
    assert not masks.occupied[row, col]
    assert masks.clearance[row, col]


def test_rotating_ninety_degrees_swaps_the_dimensions():
    flat = rasterize(rect_part(200.0, 50.0), 0.0, False, RES, sep=0.0)
    upright = rasterize(rect_part(200.0, 50.0), 90.0, False, RES, sep=0.0)

    assert flat.occupied.shape[1] > flat.occupied.shape[0]
    assert upright.occupied.shape[0] > upright.occupied.shape[1]


def test_rotation_preserves_the_occupied_area():
    part = rect_part(200.0, 50.0)
    areas = [
        rasterize(part, angle, False, RES, sep=0.0).occupied.sum()
        for angle in (0.0, 37.0, 90.0, 213.0)
    ]
    assert max(areas) / min(areas) < 1.1


def test_mirroring_preserves_the_occupied_area():
    part = rect_part(200.0, 50.0)
    straight = rasterize(part, 0.0, False, RES, sep=0.0).occupied.sum()
    flipped = rasterize(part, 0.0, True, RES, sep=0.0).occupied.sum()
    assert straight == pytest.approx(flipped, rel=0.02)


def test_origin_places_the_part_where_the_formula_says():
    part = rect_part(100.0, 50.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)

    # El pixel correspondiente al punto (50, 25) del interior tiene que estar ocupado.
    row = int((25.0 - masks.origin[1]) / RES)
    col = int((50.0 - masks.origin[0]) / RES)
    assert masks.occupied[row, col]

    # Y un punto claramente afuera (en la zona de acolchado, no en la pieza), no.
    # Nota: se usa -3.0 en vez de -20.0 del brief original porque, con este
    # padding (sep=5.0 => pad=5px), -20 produce un indice negativo (-15) que
    # cae fuera de la grilla; numpy no lo rechaza, lo interpreta como indexado
    # circular (wraparound) y termina leyendo un pixel real dentro de la
    # pieza. -3.0 sigue estando fuera de la pieza pero dentro de la grilla
    # acolchada, así que evita el wraparound sin cambiar lo que se verifica.
    row = int((-3.0 - masks.origin[1]) / RES)
    col = int((-3.0 - masks.origin[0]) / RES)
    assert not masks.occupied[row, col]


def test_a_finer_resolution_produces_a_bigger_mask():
    part = rect_part(100.0, 100.0)
    coarse = rasterize(part, 0.0, False, 2.0, sep=5.0)
    fine = rasterize(part, 0.0, False, 0.5, sep=5.0)
    assert fine.occupied.shape[0] > coarse.occupied.shape[0]


def test_the_cache_returns_the_same_object_for_the_same_key():
    cache = MaskCache()
    part = rect_part(100.0, 50.0)
    first = cache.get(part, 0.0, False, RES, 5.0)
    second = cache.get(part, 0.0, False, RES, 5.0)
    assert first is second


def test_the_cache_distinguishes_angles_and_mirroring():
    cache = MaskCache()
    part = rect_part(200.0, 50.0)
    assert cache.get(part, 0.0, False, RES, 5.0) is not cache.get(part, 90.0, False, RES, 5.0)
    assert cache.get(part, 0.0, False, RES, 5.0) is not cache.get(part, 0.0, True, RES, 5.0)


def test_the_cache_evicts_the_oldest_entry_when_full():
    # La cache ahora se acota por bytes en vez de por cantidad de entradas
    # (Hallazgo 4). Se mide el peso de una entrada real y se fija un
    # presupuesto para ~2.5 entradas, para conservar el mismo comportamiento
    # que este test verificaba antes (evict del mas viejo al entrar una
    # tercera pieza con solo lugar para dos).
    parts = [rect_part(100.0, 50.0, part_id=i) for i in range(3)]
    probe = rasterize(parts[0], 0.0, False, RES, 5.0)
    entry_bytes = probe.occupied.nbytes + probe.clearance.nbytes

    cache = MaskCache(max_bytes=int(entry_bytes * 2.5))
    first = cache.get(parts[0], 0.0, False, RES, 5.0)
    cache.get(parts[1], 0.0, False, RES, 5.0)
    cache.get(parts[2], 0.0, False, RES, 5.0)
    assert cache.get(parts[0], 0.0, False, RES, 5.0) is not first


def test_the_cache_defaults_to_the_documented_byte_budget():
    cache = MaskCache()
    assert cache._max_bytes == DEFAULT_CACHE_BUDGET_BYTES


def test_the_cache_never_exceeds_its_byte_budget():
    """Hallazgo 4: acotar por cantidad de entradas es ciego al tamaño real
    de cada mascara. Con un presupuesto en bytes, sin importar cuantas
    piezas distintas se pidan, el total ocupado por la cache nunca supera
    el presupuesto configurado."""
    cache = MaskCache(max_bytes=50_000)
    parts = [rect_part(100.0, 50.0, part_id=i) for i in range(30)]
    for part in parts:
        cache.get(part, 0.0, False, RES, 5.0)

    total_bytes = sum(
        masks.occupied.nbytes + masks.clearance.nbytes
        for masks in cache._entries.values()
    )
    assert total_bytes <= 50_000
    assert len(cache._entries) < len(parts), "tiene que haber expulsado algunas"


def test_the_cache_keeps_at_least_one_entry_even_over_budget():
    """Una entrada mas pesada que todo el presupuesto no deja la cache
    vacia: siempre se conserva al menos la ultima insertada, para que una
    pieza legitimamente grande siga siendo usable."""
    part = rect_part(500.0, 500.0, part_id=0)
    masks = rasterize(part, 0.0, False, 1.0, sep=5.0)
    entry_bytes = masks.occupied.nbytes + masks.clearance.nbytes

    cache = MaskCache(max_bytes=entry_bytes // 2)
    cache.get(part, 0.0, False, 1.0, sep=5.0)
    assert len(cache._entries) == 1


def test_masks_are_boolean_arrays():
    masks = rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=5.0)
    assert masks.occupied.dtype == np.bool_
    assert masks.clearance.dtype == np.bool_
    assert isinstance(masks, PartMasks)


def test_the_cache_distinguishes_parts_that_share_an_id():
    """Hallazgo 2: la clave de la cache tiene que incluir la geometria, no
    solo `part.id`. Si dos `Part` distintos comparten id por error (dos
    piezas del mismo dibujo, un id reciclado, etc.), indexar solo por id
    devolveria la mascara equivocada sin ningun aviso."""
    cache = MaskCache()
    same_id = 7
    small = rect_part(50.0, 50.0, part_id=same_id)
    big = rect_part(200.0, 80.0, part_id=same_id)
    assert small.id == big.id

    small_masks = cache.get(small, 0.0, False, RES, 5.0)
    big_masks = cache.get(big, 0.0, False, RES, 5.0)

    assert small_masks is not big_masks
    assert small_masks.occupied.shape != big_masks.occupied.shape
    # Y pedir de nuevo la primera pieza tiene que devolver su propia mascara,
    # no la de la otra pieza con el mismo id.
    assert cache.get(small, 0.0, False, RES, 5.0) is small_masks


def test_rasterize_rejects_negative_sep():
    """Hallazgo 5: a diferencia de `resolution`, un `sep` negativo no se
    validaba y se comportaba como sep=0 en silencio."""
    with pytest.raises(ValueError, match="separaci"):
        rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=-1.0)


def test_rasterize_rejects_a_grid_that_would_be_too_big():
    """Hallazgo 3: una combinacion de pieza grande y resolucion fina no
    puede reservar una grilla arbitrariamente grande. Medido sin este
    chequeo: una pieza de 500x500 mm a 0.02 mm/px con sep=2 tarda 41.8 s y
    ocupa ~8.8 GB; a 0.01 mm/px el proceso muere por falta de memoria."""
    huge_part = rect_part(500.0, 500.0)
    with pytest.raises(ValueError, match="grilla"):
        rasterize(huge_part, 0.0, False, resolution=0.02, sep=2.0)


def _shapely_polygon_for(part: Part, angle: float, mirror: bool) -> Polygon:
    """The same transformed outer/holes `rasterize` uses, as an exact shapely polygon."""
    transform = Transform(angle, mirror, 0.0, 0.0)
    outer = apply_points(transform, part.outer)
    holes = [apply_points(transform, hole) for hole in part.holes]
    return Polygon(outer, holes)


def _triangle_part(part_id: int = 0) -> Part:
    return Part(part_id, ((0.0, 0.0), (140.0, 0.0), (60.0, 90.0)), (), (part_id,))


def _l_shape_part(part_id: int = 0) -> Part:
    """A concave L: not a convex hull, so a diagonal-adjacent reentrant corner is covered too."""
    outer = (
        (0.0, 0.0),
        (140.0, 0.0),
        (140.0, 60.0),
        (70.0, 60.0),
        (70.0, 110.0),
        (0.0, 110.0),
    )
    return Part(part_id, outer, (), (part_id,))


def _regular_polygon(
    center: tuple[float, float], radius: float, sides: int, start_angle: float = 0.0
) -> tuple[tuple[float, float], ...]:
    """A regular n-gon, used to approximate a smooth ring/circle for the tests below."""
    return tuple(
        (
            center[0] + radius * math.cos(start_angle + 2 * math.pi * i / sides),
            center[1] + radius * math.sin(start_angle + 2 * math.pi * i / sides),
        )
        for i in range(sides)
    )


def _many_sided_ring_part(part_id: int = 0) -> Part:
    """A ring made of many-sided polygons: the shape that reproduced Hallazgo 6.

    A 24-gon outer contour (radius 150) with an 18-gon hole (radius 70),
    concentric. Neither the outer boundary nor the hole wall is grid-aligned
    at most rotations, which is exactly the condition under which Pillow's
    scanline fill under- or over-covers by up to ~1 pixel (see the big
    comment in `rasterize`). Before Hallazgo 6's fix, the hole was subtracted
    with the same over-inclusive fill used for the outer contour, which -
    for some holes, angles and resolutions - erased pixels that are real
    material. This shape (with an off-center, thinner-walled hole; see
    `_off_center_ring_part` below) is where that was first observed.
    """
    center = (150.0, 150.0)
    outer = _regular_polygon(center, 150.0, 24)
    hole = _regular_polygon(center, 70.0, 18)
    return Part(part_id, outer, (hole,), (part_id,))


def _off_center_ring_part(part_id: int = 0) -> Part:
    """A many-sided ring whose hole is off-centre, so the wall thickness varies
    around the ring instead of staying uniform. A thin section of wall is
    exactly where a hole-subtraction that over-covers (the asymmetry
    Hallazgo 6 fixes) is most likely to eat through into real material."""
    outer = _regular_polygon((0.0, 0.0), 150.0, 9)
    hole = _regular_polygon((70.0, 0.0), 72.0, 23)
    return Part(part_id, outer, (hole,), (part_id,))


def _multi_hole_part(part_id: int = 0) -> Part:
    """Several holes of different sizes on the same part, including a small
    one -- small enough that the erosion the fix applies could plausibly eat
    it away entirely at a coarse resolution (see the "hole can vanish"
    comment in `rasterize`). That is a conservative outcome, not a bug, but
    it means this shape has to be checked at multiple resolutions too."""
    outer = ((0.0, 0.0), (300.0, 0.0), (300.0, 200.0), (0.0, 200.0))
    holes = (
        ((20.0, 20.0), (80.0, 20.0), (80.0, 80.0), (20.0, 80.0)),  # mediano, 60x60
        ((150.0, 50.0), (280.0, 50.0), (280.0, 150.0), (150.0, 150.0)),  # grande, 130x100
        ((100.0, 150.0), (112.0, 150.0), (112.0, 162.0), (100.0, 162.0)),  # chico, 12x12
    )
    return Part(part_id, outer, holes, (part_id,))


# Nota sobre "un agujero dentro de un agujero": el modelo `Part` no lo admite.
# `Part.holes` es una lista plana de anillos que se restan todos del mismo
# `outer`; no hay forma de anidar un tercer nivel (una isla de material adentro
# de un agujero) dentro de un mismo `Part`. Segun `nesting_tree.build_parts`,
# un contorno a profundidad 2 o mas se convierte en una pieza independiente en
# vez de quedar anidado -- por diseño, no es un caso que `rasterize` necesite
# manejar como parte de un solo `Part`.


def test_occupied_never_under_represents_the_exact_polygon():
    """Hallazgo 1 (CRITICO), la verificacion obligatoria del arreglo.

    La propiedad que todo el motor necesita: `occupied` nunca puede
    representar MENOS material del que hay. Sub-representar deja que el
    motor superponga piezas; sobre-representar solo cuesta densidad.

    Para muchas formas, angulos y resoluciones, con y sin espejado, se
    compara pixel por pixel contra shapely (la fuente de verdad geometrica):
    todo pixel cuyo centro cae dentro del poligono exacto tiene que estar
    marcado en `occupied`. Tiene que dar cero faltantes.
    """
    shapes = {
        "rectangulo": rect_part(120.0, 80.0),
        "triangulo": _triangle_part(),
        "L_concava": _l_shape_part(),
        "anillo": ring_part(160.0, 40.0),
        "anillo_muchos_lados": _many_sided_ring_part(),
        "anillo_descentrado": _off_center_ring_part(),
        "multi_agujero": _multi_hole_part(),
    }
    # 151.0 y 0.5 son, junto con mirror=False, la combinacion exacta del
    # Hallazgo 6: un poligono con agujeros donde `rasterize` restaba las
    # paredes de los agujeros con el mismo relleno inclusivo de Pillow que
    # usa el exterior, en vez de con la asimetria (dilatar exterior, erosionar
    # agujeros) que corrige eso. Antes del arreglo esta combinacion podia
    # borrar pixeles de material real cerca de la pared de un agujero.
    angles = (0.0, 17.0, 33.3, 45.0, 90.0, 137.0, 151.0, 180.0, 270.0)
    resolutions = (0.5, 1.0, 2.0)
    mirrors = (False, True)

    combos = 0
    total_pixels_checked = 0
    total_missing = 0
    worst: tuple[int, str, float, float, bool] | None = None

    for shape_name, part in shapes.items():
        for angle, resolution, mirror in itertools.product(angles, resolutions, mirrors):
            combos += 1
            masks = rasterize(part, angle, mirror, resolution, sep=0.0)
            poly = _shapely_polygon_for(part, angle, mirror)

            height, width = masks.occupied.shape
            cols = np.arange(width)
            rows = np.arange(height)
            xs = masks.origin[0] + (cols + 0.5) * resolution
            ys = masks.origin[1] + (rows + 0.5) * resolution
            grid_x, grid_y = np.meshgrid(xs, ys)

            inside_exact = contains_xy(poly, grid_x, grid_y)
            missing = inside_exact & ~masks.occupied
            missing_count = int(missing.sum())

            total_pixels_checked += int(inside_exact.size)
            total_missing += missing_count
            if missing_count and (worst is None or missing_count > worst[0]):
                worst = (missing_count, shape_name, angle, resolution, mirror)

    print(
        f"conservadurismo hallazgo 1: {combos} combinaciones, "
        f"{total_pixels_checked} pixeles evaluados, {total_missing} faltantes"
    )
    assert total_missing == 0, f"peor caso (faltantes, forma, angulo, resolucion, mirror): {worst}"


def _ring(n, r, ph=0.0, cx=0.0, cy=0.0):
    return tuple(
        (cx + r * math.cos(ph + 2 * math.pi * i / n),
         cy + r * math.sin(ph + 2 * math.pi * i / n))
        for i in range(n)
    )


HARSH_SHAPES = {
    "anillo 24/18": Part(0, _ring(24, 150), (_ring(18, 70),), (0,)),
    "anillo descentrado": Part(1, _ring(20, 150), (_ring(16, 60, cx=40, cy=25),), (1,)),
    "pared fina": Part(2, _ring(30, 100), (_ring(30, 94),), (2,)),
    "estrella 7": Part(3, tuple(_ring(14, 120 if i % 2 else 55, ph=0.3)[i] for i in range(14)), (), (3,)),
    "L con 3 agujeros": Part(
        4,
        ((0, 0), (240, 0), (240, 70), (90, 70), (90, 240), (0, 240)),
        (((15, 15), (45, 15), (45, 45), (15, 45)),
         ((60, 15), (78, 15), (78, 33), (60, 33)),
         ((15, 90), (60, 90), (60, 200), (15, 200))),
        (4,),
    ),
}


def test_occupied_never_under_represents_under_a_harsh_sweep():
    """Ismo Hallazgo 1, con un barrido mas exigente que el de arriba
    (resoluciones mas finas, mas angulos) que encontro faltantes reales
    cuando `rasterize` dependia solo de una dilatacion/erosion de seguridad
    de 1 pixel sobre el relleno directo de Pillow -- ver el arreglo de
    supermuestreo en `rasterize`.

    Ningun pixel cuyo centro cae dentro del poligono exacto puede faltar.
    Sub-representar deja que el motor coloque piezas demasiado cerca y que
    el verificador exacto rechace el layout entero; sobre-representar solo
    cuesta un poco de densidad. Por eso la cota es cero y no "casi cero".
    """
    missing = 0
    for part in HARSH_SHAPES.values():
        for angle in (0.0, 11.7, 29.0, 45.0, 62.5, 90.0, 151.0, 213.0, 270.0, 337.4):
            for resolution in (0.4, 0.5, 1.0, 2.0, 3.0):
                for mirror in (False, True):
                    masks = rasterize(part, angle, mirror, resolution, sep=4.0)
                    t = Transform(angle, mirror, 0.0, 0.0)
                    polygon = Polygon(
                        apply_points(t, part.outer),
                        [apply_points(t, hole) for hole in part.holes],
                    )
                    rows, cols = masks.occupied.shape
                    ys, xs = np.mgrid[0:rows, 0:cols]
                    inside = contains_xy(
                        polygon,
                        (masks.origin[0] + xs * resolution).ravel(),
                        (masks.origin[1] + ys * resolution).ravel(),
                    ).reshape(rows, cols)
                    missing += int((inside & ~masks.occupied).sum())

    assert missing == 0, f"faltan {missing} pixeles de material en la mascara"


def test_the_cache_survives_being_hammered_from_several_threads():
    """Las consultas de una pieza corren en hilos (fase 2 de pares y cartera).

    `warm` pide las máscaras antes desde un solo hilo, pero eso sólo evita
    altas concurrentes si todas las orientaciones entran en el presupuesto; a
    una resolución fina no entran, y los hilos terminan insertando y
    expulsando a la vez. Con un presupuesto chiquito eso pasa todo el
    tiempo: sin cerrojo, `move_to_end` sobre una clave recién expulsada
    levanta `KeyError` y `_nbytes` pierde sumas.
    """
    import sys
    from concurrent.futures import ThreadPoolExecutor

    from nesting.engine.raster.masks import _masks_nbytes

    # Cambiar de hilo cada microsegundo y no cada 5 ms: sin esto la carrera
    # existe igual, pero aparece de vez en cuando y no siempre.
    previo = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        cache = MaskCache(max_bytes=20_000)
        parts = [rect_part(40.0 + 3 * i, 30.0, part_id=i) for i in range(6)]
        pedidos = [(parts[(k * 7) % 6], (0.0, 90.0, 180.0, 270.0)[k % 4], bool(k % 3 == 0))
                   for k in range(3000)]

        def pedir(pedido):
            part, angle, mirror = pedido
            return cache.get(part, angle, mirror, RES, 5.0)

        with ThreadPoolExecutor(max_workers=8) as pool:
            resultados = list(pool.map(pedir, pedidos))
    finally:
        sys.setswitchinterval(previo)

    assert all(isinstance(m, PartMasks) for m in resultados)
    assert cache._nbytes == sum(_masks_nbytes(m) for m in cache._entries.values())
    assert cache._nbytes <= 20_000 or len(cache._entries) == 1
