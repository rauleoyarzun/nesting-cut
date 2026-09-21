"""Una placa concreta sobre la que se acomoda, y en qué orden vienen.

El motor solía recibir un `Material` y asumir que toda placa medía lo
mismo. Eso alcanzaba mientras las placas se compraran; no alcanza para los
recortes, que son de a uno y de cualquier medida. `Sheet` es la placa que
el motor tiene enfrente en este momento, y `SheetSupply` dice cuál es esa
placa en cada turno.
"""

from collections.abc import Sequence
from dataclasses import dataclass

GRAIN_EPS = 1e-9


@dataclass(frozen=True)
class Sheet:
    """Una placa concreta: su medida, su veta, y de dónde salió."""

    width: float
    height: float
    grain_tolerance: float
    """Grados que una pieza puede desviarse del eje de veta de ESTA placa.

    El rango útil real es 0 a 90: la distancia angular al eje nunca supera
    90 grados, así que cualquier valor de 90 o más equivale a rotación
    libre. Por convención se usa 180 para expresar "libre".
    """

    cross_grain: bool = False
    """La veta corre a lo ancho y no a lo alto.

    Un recorte de 600x800 puede tener la veta en cualquiera de los dos
    sentidos según cómo salió de la placa madre, y eso sólo lo sabe quien
    está mirando el pedazo. Marcarlo rota el eje 90 grados.
    """

    scrap: bool = False
    """Es un recorte: material que ya está pago.

    `layout_cost` cuenta sólo las placas que NO son recortes, porque llenar
    un recorte no cuesta nada y el motor no tiene que evitarlo.
    """

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True)
class SheetSupply:
    """Qué placa toca en cada turno. Los recortes se agotan; la del Material no.

    `sheet(i)` no levanta nunca: pasado el último recorte devuelve siempre
    la placa del Material. Es lo que hace que el bucle del packer pueda
    pedir placas hasta que no le queden piezas, sin llevar la cuenta de
    cuántas hay.
    """

    stock: Sheet
    scraps: tuple[Sheet, ...] = ()
    material_name: str = "del material"
    """Sólo para el mensaje de "esta pieza no entra en una placa vacía".

    `Sheet` no tiene nombre a propósito -- un recorte no lo tiene -- así que
    el mensaje nombra al material y no a la placa concreta que lo disparó.

    EN EL PLAN QUE ARMA QUIEN LLAMA AL MOTOR las dos cosas coinciden: un
    recorte vacío se saltea, así que el error sólo puede salir contra la
    placa del Material. NO COINCIDEN en los planes de una sola placa que
    `packer.py` se arma adentro para reempacar (la recuperación y la
    compactación): ahí el stock es una placa concreta del resultado, que
    puede ser un recorte de cualquier medida, y el mensaje describiría ESE
    recorte llamándolo el material. Por eso el motor no deja salir esos
    errores: los atrapa y trata el reempaque como un intento que no sirvió.
    """

    def sheet(self, index: int) -> Sheet:
        return self.scraps[index] if index < len(self.scraps) else self.stock


def allowed_angles(sheet: Sheet, angles: Sequence[float]) -> list[float]:
    """Deja sólo los ángulos que la veta de esta placa permite.

    Un ángulo se permite cuando cae dentro de `grain_tolerance` grados del
    eje de veta, que corre por 0 y 180 -- o por 90 y 270 si la placa está
    cruzada.
    """
    offset = 90.0 if sheet.cross_grain else 0.0
    return [
        a
        for a in angles
        if _distance_to_grain_axis(a - offset) <= sheet.grain_tolerance + GRAIN_EPS
    ]


def _distance_to_grain_axis(angle: float) -> float:
    folded = angle % 180.0
    return min(folded, 180.0 - folded)
