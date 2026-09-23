"""Pares encastrados: dos copias de una pieza fundidas en una sola.

El motor de siempre ubica pieza por pieza y nunca vuelve atrás: cuando pone
el primer marco no sabe que conviene dejarle lugar al segundo en una
posición exacta. Acá se busca esa posición antes de acomodar nada -- todas
las posiciones relativas de golpe, por FFT --, y el par se le ofrece al
motor como una pieza más. El oráculo, las máscaras y el empacador no se
enteran de nada.

Spec: docs/superpowers/specs/2026-09-22-pares-y-cartera-design.es.md, sección 3.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import math

import numpy as np
from scipy.signal import fftconvolve
from shapely.geometry import LineString, Polygon
from shapely.ops import nearest_points, unary_union

from nesting.engine.iguales import Clase, Member, congruence
from nesting.engine.oracle import NestConfig, transformed_bbox
from nesting.engine.packer import PackResult
from nesting.engine.raster.masks import INFLACION_MAX_PX, MaskCache
from nesting.geometry.transform import componer
from nesting.geometry.verify import placed_polygon
from nesting.model.entities import Point, Transform
from nesting.model.part import Part, Placement

TIPOS_POR_CLASE: dict[str, int] = {"rapido": 0, "normal": 6, "lento": 10}
"""Cuántos tipos de par se guardan por clase, según el esfuerzo."""

MIN_SHEET_SHARE = 0.02
"""Una clase se empareja si su pieza ocupa al menos el 2% del área útil.

Un listón emparejado casi no gana lugar y sí multiplica combinaciones.
"""

MAX_PAIRED_CLASSES = 2
"""Cuántas clases se emparejan como máximo, las de pieza más grande primero."""

NEIGHBOUR_MM = 200.0
"""Dos candidatos de la misma orientación a menos de esto son el mismo encastre.

LA PRIMERA VERSIÓN DE LA SPEC DECÍA 60, Y SE MIDIÓ QUE NO ALCANZABA. Sin
supresión, los doscientos mejores candidatos son todos el mismo encastre
corrido un píxel (lo mostró el experimento de la spec). Con 60 mm, sobre el
marco de la banqueta, los seis tipos de `normal` salían todos de UNA familia
que se desliza de a 60 mm: 1812x450, 1511x560, 1571x545, 1634x529, 1697x513,
1816x510; el apilado (1055x879) recién aparecía séptimo, así que `normal`
nunca podía probar la combinación que gana. Medido al escribir el plan
(`rango2.py`): con 100 y 150 mm el apilado entra en los seis; con 200 mm la
familia colapsa a sus dos extremos (1812x450 y 1511x560) y la lista no
cambia hasta 300 mm. La spec quedó actualizada a 200, que es lo que este
valor usa hoy.
"""

CANDIDATES_PER_ORIENTATION = 15
"""Cuántos candidatos, ya suprimidos, se guardan por orientación de B."""

BRIDGE_RADIUS_MM = 1.0
"""Medio ancho del puente que une A con B, con puntas redondas.

Con puntas planas el puente no llegaba a fundirse con los dos polígonos en
el experimento, y la unión salía en dos pedazos. El cierre morfológico
(dilatar y erosionar) tampoco sirve: dos marcos que se tocan por una esquina
se vuelven a separar al erosionar.
"""

GAP_EPS = 1e-6
"""La misma holgura numérica que usa `verify`, para que un par a exactamente
`sep` no se descarte por ruido."""

SLIDE_MARGIN_MM = 0.01
"""Cuánto de más, sobre `sep`, se deja al deslizar B hacia A.

Los candidatos salen de la grilla rasterizada, y ahí el hueco real entre A y
B puede quedar hasta ~3 * resolución por encima de `sep` (la holgura
conservadora de las máscaras). Con una separación chica frente a la
resolución -- `sep` de 2 o 3 mm a 1 mm/px, o de 6 mm a 2 mm/px, medido sobre
la L de este módulo -- ese exceso solo alcanza para que TODOS los
candidatos superen `2 * sep` y `find_pair_types` no encuentre ningún tipo.

La corrección desliza B, en línea recta hacia A, hasta dejarlo a
`sep + SLIDE_MARGIN_MM` -- sólo si el candidato está dentro de
`slide_window`, lo que el raster pudo haber dejado de más. La prueba de que
esto no lo acerca de más: si `gap = a.distance(b)` es la distancia real (el
mínimo sobre TODOS los pares de puntos de A y B) y se mueve B rígidamente
una distancia δ a lo largo de la recta que une los dos puntos más cercanos,
la desigualdad triangular dice que CUALQUIER par de puntos, tras el
movimiento, queda a una distancia de al menos `distancia_original - δ`; y
como toda distancia original ya era `>= gap`, la nueva distancia mínima (que
es lo que mide `a.distance(b)` después) queda `>= gap - δ`. Eligiendo
`δ = gap - (sep + SLIDE_MARGIN_MM)` -- sólo cuando da positivo, o sea cuando
`gap` ya se pasó del margen -- esa cota es exactamente
`sep + SLIDE_MARGIN_MM`, así que el par nunca puede quedar más cerca que
`sep`. El margen de 0.01 mm es para no caer justo en el borde `gap == sep`
por ruido de coma flotante, igual que hace `GAP_EPS` del lado de abajo; el
chequeo exacto (`sep - GAP_EPS <= gap < 2 * sep`) sigue siendo el árbitro
después de deslizar.
"""


SLIDE_WINDOW_PX = 2 * INFLACION_MAX_PX + 2
"""Cuántos píxeles de más, sobre `sep`, puede dejar el raster entre A y B.

La holgura de las máscaras es `ceil(sep / resolución)` píxeles: hasta uno
de más por el redondeo. `occupied` se infla hasta `INFLACION_MAX_PX` por
lado, y son dos piezas: `2 * INFLACION_MAX_PX`. Y el desplazamiento de B
es entero, en píxeles: uno más. Con `INFLACION_MAX_PX = 2`, seis.
"""


def slide_window(sep: float, resolution: float) -> float:
    """Hasta dónde, sobre `sep`, un candidato es un encastre que el raster dejó flojo.

    Sólo esos se acercan (`SLIDE_MARGIN_MM`). Un candidato más lejos no es un
    encastre flojo sino otra cosa: acercarlo en línea recta arma un par
    distinto del que midió el raster, con una caja que no es la de
    `box_area`, y la lista deja de estar ordenada. Se descarta, como antes
    de que existiera el acercamiento.

    Nunca menos que `sep`: todo lo que ya estaba por debajo de `2 * sep`
    sigue entrando, así que la ventana no pierde ningún tipo de los que
    había antes del acercamiento.
    """
    return max(sep, SLIDE_WINDOW_PX * resolution)


@dataclass(frozen=True)
class PairType:
    """Una manera de encastrar dos copias: B relativa a A, con A en la identidad."""

    relative: Transform
    """Dónde va la copia B, en las coordenadas de la representante."""

    box_area: float
    """Área de la caja del par en mm², medida sobre las cajas en píxeles.

    Es la clave con la que se ordenan los tipos y las combinaciones. Sale de
    los píxeles y no de la geometría exacta porque así se calcula para todos
    los desplazamientos de una vez, sin rasterizar nada más; y como los tipos
    se aceptan en ese mismo orden, la lista queda ordenada por esta clave
    por construcción.
    """

    width: float
    """Ancho exacto de la caja de A ∪ B, en mm."""

    height: float
    orientation: tuple[float, bool]
    """La orientación de B con que se encontró (para la supresión de vecinos)."""

    offset_px: tuple[int, int]
    outer: tuple[Point, ...]
    """El contorno de A ∪ B ∪ puente, en las coordenadas de la representante."""

    holes: tuple[tuple[Point, ...], ...]
    """Los agujeros de A y de B, que siguen disponibles para piezas chicas."""

    def shape(self, part_id: int) -> Part:
        """La compuesta como una `Part` común, sin entidades de dibujo."""
        return Part(part_id, self.outer, self.holes, ())


def pairable_classes(
    classes: Sequence[Clase],
    usable_area: float,
    grain_respected: bool,
) -> list[Clase]:
    """Las clases que vale la pena emparejar, de pieza más grande a más chica.

    Con la veta respetada, una clase cuyos miembros llegan a la
    representante con un ángulo que no es múltiplo de 180 no se empareja: el
    ángulo final de un miembro es la suma del de la compuesta, el del par y
    el de `g`, y dos desvíos permitidos (3° + 3°) pueden sumar uno que no lo
    es. `verify` no mira la veta, así que nadie más lo atajaría.
    """
    elegibles = [
        c for c in classes
        if len(c.members) >= 2
        and c.representative.area >= MIN_SHEET_SHARE * usable_area
        and not (
            grain_respected
            and any(m.to_representative.angle_deg % 180.0 != 0.0 for m in c.members)
        )
    ]
    elegibles.sort(key=lambda c: c.representative.area, reverse=True)
    return elegibles[:MAX_PAIRED_CLASSES]


def b_orientations(
    choices: Sequence[tuple[float, bool]],
    grain_respected: bool,
) -> list[tuple[float, bool]]:
    """Las orientaciones de B relativas a A.

    Con la veta respetada, sólo 0° y 180° (y sus espejadas, si hay espejo):
    así la composición de la orientación del par (que ya filtra la veta de
    cada placa) con la de B sigue en el eje. Vale igual para un recorte de
    veta cruzada: 90° más 0° o 180° sigue en su eje.
    """
    if not grain_respected:
        return list(choices)
    return [(a, m) for a, m in choices if a % 180.0 == 0.0]


def union_with_bridge(
    a: Polygon, b: Polygon
) -> tuple[tuple[Point, ...], tuple[tuple[Point, ...], ...]] | None:
    """A ∪ B ∪ el puente entre sus dos puntos más cercanos, o None si no da
    un solo polígono.

    Los puntos más cercanos se buscan entre los polígonos y no entre sus
    contornos exteriores: si B cae adentro de un agujero de A, el punto de A
    más cercano está en el borde del agujero, y un puente al contorno
    exterior cruzaría el hueco entero.
    """
    qa, qb = nearest_points(a, b)
    bridge = LineString([qa, qb]).buffer(BRIDGE_RADIUS_MM)
    union = unary_union([a, b, bridge]).buffer(0)
    if union.geom_type != "Polygon":
        return None
    outer = tuple(union.exterior.coords)[:-1]
    holes = tuple(tuple(ring.coords)[:-1] for ring in union.interiors)
    return outer, holes


def _pixel_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    """(col0, fila0, col1, fila1) de lo ocupado, inclusivo."""
    filas = np.nonzero(mask.any(axis=1))[0]
    columnas = np.nonzero(mask.any(axis=0))[0]
    return int(columnas[0]), int(filas[0]), int(columnas[-1]), int(filas[-1])


def _fits(part: Part, fit_choices: Sequence[tuple[float, bool]],
          usable: tuple[float, float]) -> bool:
    usable_w, usable_h = usable
    for angle, mirror in fit_choices:
        x0, y0, x1, y1 = transformed_bbox(part, angle, mirror)
        if x1 - x0 <= usable_w + GAP_EPS and y1 - y0 <= usable_h + GAP_EPS:
            return True
    return False


def find_pair_types(
    representative: Part,
    b_choices: Sequence[tuple[float, bool]],
    fit_choices: Sequence[tuple[float, bool]],
    config: NestConfig,
    usable: tuple[float, float],
    how_many: int,
    cache: MaskCache,
) -> list[PairType]:
    """Hasta `how_many` tipos de par de `representative`, de menor a mayor caja.

    `b_choices` son las orientaciones de B relativas a A (ver
    `b_orientations`); `fit_choices`, las que la placa del Material permite
    para el par entero, contra las que se mira que entre en `usable` y que
    un tipo nuevo no sea congruente con uno ya aceptado.

    Las máscaras salen del mismo `MaskCache` y con la misma resolución y
    separación que usa la corrida: `A.occupied` correlacionado con
    `B.clearance` da cero exactamente donde B no toca el halo de A.
    """
    if how_many <= 0 or config.sep <= 0.0:
        # Sin separación no hay hueco de "menos de dos separaciones" donde
        # esconder el puente, y el puente le robaría lugar a otra pieza.
        return []

    res, sep = config.resolution, config.sep
    a_masks = cache.get(representative, 0.0, False, res, sep)
    a_occupied = a_masks.occupied.astype(np.float32)
    a_box = _pixel_box(a_masks.occupied)
    vecino_px = NEIGHBOUR_MM / res

    candidatos: list[tuple[float, float, bool, int, int]] = []
    for angle, mirror in b_choices:
        b_masks = cache.get(representative, angle, mirror, res, sep)
        clearance = b_masks.clearance.astype(np.float32)
        # overlap[k] = suma de A.occupied(x) * B.clearance(x - k): cero
        # donde B, corrida k píxeles, no toca a A.
        overlap = fftconvolve(a_occupied, clearance[::-1, ::-1], mode="full")
        filas, columnas = np.nonzero(overlap < 0.5)
        oy = filas - (clearance.shape[0] - 1)
        ox = columnas - (clearance.shape[1] - 1)

        b_box = _pixel_box(b_masks.occupied)
        x0 = np.minimum(a_box[0], b_box[0] + ox)
        y0 = np.minimum(a_box[1], b_box[1] + oy)
        x1 = np.maximum(a_box[2], b_box[2] + ox)
        y1 = np.maximum(a_box[3], b_box[3] + oy)
        area = (x1 - x0) * (y1 - y0)

        # Supresión de vecinos ANTES de truncar: sin esto, los quince
        # mejores de cada orientación son el mismo encastre corrido de a un
        # píxel, y los demás encastres no llegan a la lista.
        tomados: list[tuple[int, int]] = []
        for k in np.argsort(area, kind="stable"):
            u, v = int(ox[k]), int(oy[k])
            if any(abs(u - tu) < vecino_px and abs(v - tv) < vecino_px for tu, tv in tomados):
                continue
            tomados.append((u, v))
            candidatos.append((float(area[k]) * res * res, angle, mirror, u, v))
            if len(tomados) >= CANDIDATES_PER_ORIENTATION:
                break

    candidatos.sort()

    a_polygon = placed_polygon(representative, Transform.identity())
    aceptados: list[PairType] = []
    for box_area, angle, mirror, u, v in candidatos:
        # Sin segunda supresión acá: los candidatos de una misma orientación
        # ya salieron mutuamente separados por `vecino_px` en el paso de
        # arriba (la lista `tomados`), y `aceptados` es un subconjunto de
        # `candidatos`, así que dos aceptados de la misma orientación nunca
        # pueden estar más cerca que eso.
        b_masks = cache.get(representative, angle, mirror, res, sep)
        # El píxel [0, 0] de B cae en el de A corrido (u, v) píxeles.
        relative = Transform(
            angle, mirror,
            a_masks.origin[0] + u * res - b_masks.origin[0],
            a_masks.origin[1] + v * res - b_masks.origin[1],
        )
        b_polygon = placed_polygon(representative, relative)
        gap = a_polygon.distance(b_polygon)
        if gap >= sep + slide_window(sep, res):
            # Demasiado lejos para ser un encastre que el raster dejó flojo
            # (ver `slide_window`): acercarlo armaría otro par.
            continue
        if gap > sep + SLIDE_MARGIN_MM:
            # El candidato viene del raster: puede quedar unos píxeles más
            # lejos de lo que pide `sep`. Se acerca B en línea recta hasta
            # el margen (ver la prueba en `SLIDE_MARGIN_MM`) y se vuelve a
            # medir; el chequeo de abajo sigue siendo el árbitro.
            qa, qb = nearest_points(a_polygon, b_polygon)
            vx, vy = qa.x - qb.x, qa.y - qb.y
            norm = math.hypot(vx, vy)
            if norm > 0.0:
                delta = gap - (sep + SLIDE_MARGIN_MM)
                relative = Transform(
                    relative.angle_deg, relative.mirror,
                    relative.dx + delta * vx / norm,
                    relative.dy + delta * vy / norm,
                )
                b_polygon = placed_polygon(representative, relative)
                gap = a_polygon.distance(b_polygon)
        if not (sep - GAP_EPS <= gap < 2 * sep):
            continue

        unida = union_with_bridge(a_polygon, b_polygon)
        if unida is None:
            continue
        outer, holes = unida
        forma = Part(-1, outer, holes, ())
        if not _fits(forma, fit_choices, usable):
            continue
        if any(congruence(forma, t.shape(-2), fit_choices) is not None for t in aceptados):
            continue

        bx0, by0, bx1, by1 = a_polygon.union(b_polygon).bounds
        aceptados.append(
            PairType(
                relative=relative,
                box_area=box_area,
                width=bx1 - bx0,
                height=by1 - by0,
                orientation=(angle, mirror),
                offset_px=(u, v),
                outer=outer,
                holes=holes,
            )
        )
        if len(aceptados) >= how_many:
            break

    return aceptados


@dataclass(frozen=True)
class Composite:
    """Un par ya armado con dos piezas reales, listo para acomodarse."""

    part: Part
    """La forma del par (`PairType.shape`), con un id que no usa ninguna pieza real."""

    members: tuple[tuple[int, Transform], ...]
    """`(part_id, t)` por miembro: `t` lleva la pieza real a su lugar adentro
    del par, en las coordenadas de la compuesta."""


def make_composite(part_id: int, pair_type: PairType, first: Member, second: Member) -> Composite:
    """El par `pair_type` hecho con las piezas reales `first` (como A) y `second` (como B).

    El par se construyó con la representante: A en la identidad y B en
    `relative`. Una pieza real llega a la representante con su `g`, así que
    A termina en `g_A` y B en `relative ∘ g_B`.
    """
    return Composite(
        part=pair_type.shape(part_id),
        members=(
            (first.part_id, first.to_representative),
            (second.part_id, componer(pair_type.relative, second.to_representative)),
        ),
    )


def disassemble(
    result: PackResult,
    composites: Sequence[Composite],
    parts: Sequence[Part],
) -> PackResult:
    """Cambia cada compuesta colocada por sus dos miembros, con `T ∘ t`.

    Corre ANTES de verificar y antes de escribir nada: una compuesta nunca
    llega a `verify`, al DXF ni a la previsualización. `parts` son las
    piezas reales; el aprovechamiento se recalcula con ellas, porque el
    área de la compuesta incluye el puente, que no es material de nadie.
    """
    by_composite = {c.part.id: c for c in composites}
    if not by_composite:
        return result

    placements: list[Placement] = []
    for placement in result.placements:
        composite = by_composite.get(placement.part_id)
        if composite is None:
            placements.append(placement)
            continue
        for member_id, inner in composite.members:
            placements.append(
                Placement(member_id, placement.sheet, componer(placement.transform, inner))
            )

    # La misma cuenta que `_pack_once`: áreas por placa y UNA división al
    # final, para que el total coincida con el de una corrida sin pares.
    by_id = {p.id: p for p in parts}
    areas = [0.0] * len(result.sheets)
    for placement in placements:
        areas[placement.sheet] += by_id[placement.part_id].area
    area_total = sum(sheet.area for sheet in result.sheets)
    return PackResult(
        placements=placements,
        sheets=list(result.sheets),
        utilization=[area / sheet.area for area, sheet in zip(areas, result.sheets)],
        total_utilization=sum(areas) / area_total if area_total else 0.0,
        seconds=result.seconds,
    )
