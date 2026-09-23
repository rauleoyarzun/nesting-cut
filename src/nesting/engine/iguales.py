"""Qué piezas son copias de la misma forma, y cómo se lleva cada una sobre la otra.

Un archivo real trae los seis marcos de una banqueta dibujados donde cayeron:
corridos, algunos girados, alguno espejado. Para encastrarlos de a pares
(`pares.py`) hace falta saber que son la misma pieza, y además CÓMO llevar
cada uno sobre el que se tomó de modelo -- la `g` de la spec --, porque el
par se arma con el modelo y después hay que devolverle a cada pieza real su
lugar.

"Iguales" depende de la corrida y no sólo del dibujo: dos piezas son iguales
cuando una se lleva sobre la otra con una traslación más una orientación que
la corrida PERMITE. Con la veta respetada, un marco dibujado girado 90° no es
igual a uno acostado, porque llevarlo al otro rompería la veta.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import Polygon

from nesting.geometry.verify import placed_polygon
from nesting.model.entities import Transform
from nesting.model.part import Part

AREA_TOLERANCE_MM2 = 1.0
"""Diferencia simétrica, en mm², por debajo de la cual dos piezas son iguales.

Un milímetro cuadrado es nada para una fresa (una tira de 1 mm de ancho por
1 mm de largo) y es mucho para el ruido de coma flotante de girar y
trasladar, que da del orden de 1e-9 mm².
"""

FINGERPRINT_AREA_MM2 = 1.0
FINGERPRINT_PERIMETER_MM = 0.5
FINGERPRINT_RELATIVE = 1e-4
"""Cuánto pueden diferir dos huellas y seguir siendo candidatas a iguales.

Área (neta y de cada agujero): hasta `max(FINGERPRINT_AREA_MM2,
FINGERPRINT_RELATIVE * área)`. Perímetro: hasta `max(FINGERPRINT_PERIMETER_MM,
FINGERPRINT_RELATIVE * perímetro)`.

Antes la huella se redondeaba a 0,01 y se agrupaba por igualdad exacta, y
eso dependía de qué lado de un redondeo caía cada copia. El aplanado de
las curvas no da los mismos vértices en todas: los seis marcos de la
banqueta alta miden 97147,44, ,43, ,33 y ,32 mm², y quedaban en clases de 2,
1, 2 y 1. La huella es un filtro, no el juez: dejar pasar de más sólo cuesta
una llamada a `congruence`, que sigue siendo quien decide.
"""


@dataclass(frozen=True)
class Member:
    part_id: int
    to_representative: Transform
    """La `g` de la spec: aplicada a esta pieza, la deja encima de la
    representante (diferencia simétrica menor a `AREA_TOLERANCE_MM2`)."""


@dataclass(frozen=True)
class Clase:
    """Las copias de una misma forma. El primer miembro es la representante."""

    representative: Part
    members: tuple[Member, ...]


def fingerprint(part: Part) -> tuple[float, float, int, tuple[float, ...]]:
    """Área neta, perímetro, cantidad de agujeros y el área de cada uno, sin redondear.

    Descarta casi todo sin geometría exacta: dos piezas cuyas huellas no
    se parecen (`same_fingerprint`) no pueden ser congruentes, así que ni se
    comparan.
    """
    polygon = placed_polygon(part, Transform.identity())
    return (
        polygon.area,
        polygon.exterior.length,
        len(part.holes),
        tuple(sorted(Polygon(h).area for h in part.holes)),
    )


def _close(a: float, b: float, absolute: float) -> bool:
    return abs(a - b) <= max(absolute, FINGERPRINT_RELATIVE * max(abs(a), abs(b)))


def same_fingerprint(a: tuple, b: tuple) -> bool:
    """Si dos huellas se parecen lo bastante como para comparar las piezas.

    Misma cantidad de agujeros, y área, perímetro y cada agujero (de menor
    a mayor) dentro de la tolerancia de `FINGERPRINT_RELATIVE`.
    """
    area_a, perimeter_a, holes_a, hole_areas_a = a
    area_b, perimeter_b, holes_b, hole_areas_b = b
    return (
        holes_a == holes_b
        and _close(area_a, area_b, FINGERPRINT_AREA_MM2)
        and _close(perimeter_a, perimeter_b, FINGERPRINT_PERIMETER_MM)
        and all(_close(x, y, FINGERPRINT_AREA_MM2) for x, y in zip(hole_areas_a, hole_areas_b))
    )


def congruence(
    part: Part,
    target: Part,
    orientations: Sequence[tuple[float, bool]],
) -> Transform | None:
    """La primera `g`, en el orden de `orientations`, que lleva `part` sobre `target`.

    Para cada orientación se alinea el vértice inferior izquierdo de la caja
    de `part` ya girada con el de `target`, y se mide la diferencia
    simétrica. Alinear por la caja -- y no por el centroide -- es lo que usó
    el experimento, y alcanza: si dos piezas son congruentes bajo esa
    orientación, sus cajas coinciden.

    Por qué no basta con la caja sola: el experimento de la spec la probó
    primero, y dos marcos con la misma caja pero dibujados espejados uno del
    otro terminaban superpuestos al desarmar. La diferencia simétrica es la
    que distingue.
    """
    objetivo = placed_polygon(target, Transform.identity())
    tx0, ty0, _, _ = objetivo.bounds
    for angle, mirror in orientations:
        girada = placed_polygon(part, Transform(angle, mirror, 0.0, 0.0))
        qx0, qy0, _, _ = girada.bounds
        g = Transform(angle, mirror, tx0 - qx0, ty0 - qy0)
        movida = placed_polygon(part, g)
        if movida.symmetric_difference(objetivo).area < AREA_TOLERANCE_MM2:
            return g
    return None


def find_classes(
    parts: Sequence[Part],
    orientations: Sequence[tuple[float, bool]],
) -> list[Clase]:
    """Agrupa `parts` en clases de piezas iguales para esta corrida.

    `orientations` son las que la corrida permite -- las de
    `packer.orientations(placa, config)` --, que ya traen filtrada la veta
    y el espejo. Por eso con la veta respetada una copia girada 90° queda en
    una clase propia, y sin espejo una espejada también.
    """
    # Cada clase con la huella de su representante, en el orden en que
    # aparecieron. Una pieza se prueba contra las clases en ese orden y se
    # queda en la primera que la acepta: el resultado depende sólo del orden
    # de `parts`.
    classes: list[tuple[Part, tuple, list[Member]]] = []

    for part in parts:
        huella = fingerprint(part)
        for representative, representative_huella, members in classes:
            if not same_fingerprint(huella, representative_huella):
                continue
            g = congruence(part, representative, orientations)
            if g is not None:
                members.append(Member(part.id, g))
                break
        else:
            classes.append((part, huella, [Member(part.id, Transform.identity())]))

    return [Clase(representative, tuple(members)) for representative, _, members in classes]
