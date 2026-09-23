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

FINGERPRINT_DECIMALS = 2
"""La huella redondea a 0,01 mm (y mm²).

Es un filtro, no el juez: dos copias cuya área cayera justo a los dos lados
de un redondeo quedarían en clases distintas, y el efecto sería sólo que no
se emparejan -- nunca un acomodo equivocado. El juez es `congruence`.
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


def fingerprint(part: Part) -> tuple:
    """Área neta, perímetro, cantidad de agujeros y el área de cada uno.

    Descarta casi todo sin geometría exacta: dos piezas con huellas distintas
    no pueden ser congruentes, así que ni se comparan.
    """
    polygon = placed_polygon(part, Transform.identity())
    return (
        round(polygon.area, FINGERPRINT_DECIMALS),
        round(polygon.exterior.length, FINGERPRINT_DECIMALS),
        len(part.holes),
        tuple(sorted(round(Polygon(h).area, FINGERPRINT_DECIMALS) for h in part.holes)),
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
    buckets: dict[tuple, list[tuple[Part, list[Member]]]] = {}
    order: list[tuple[Part, list[Member]]] = []

    for part in parts:
        bucket = buckets.setdefault(fingerprint(part), [])
        for representative, members in bucket:
            g = congruence(part, representative, orientations)
            if g is not None:
                members.append(Member(part.id, g))
                break
        else:
            entry = (part, [Member(part.id, Transform.identity())])
            bucket.append(entry)
            order.append(entry)

    return [Clase(representative, tuple(members)) for representative, members in order]
