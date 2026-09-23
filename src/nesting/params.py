"""Los parámetros de una corrida, y las reglas que tienen que cumplir.

Vive en `nesting` y no en `nesting_app` a propósito: la CLI los usa, y el
motor no puede importar el paquete de la interfaz sin invertir la única
dependencia que sostiene toda la arquitectura.

La regla se guarda separada de su redacción. En una terminal, "--sep tiene
que ser >= 0" es el mensaje correcto; al lado de un campo de formulario que
ya dice "Separación", el mismo texto con un guión doble adelante no
significa nada. Una sola fuente de verdad para la regla, dos maneras de
contarla.
"""

from dataclasses import dataclass, replace
from typing import Literal

from nesting.engine import workers
from nesting.engine.oracle import NestConfig
from nesting.model.material import VETA_LIBRE, VETA_RESPETAR, Material
from nesting.model.sheet import Sheet, SheetSupply, allowed_angles
from nesting.tolerances import DEFAULT_CHAIN_TOL

DEFAULT_ANGLES: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)

Veta = Literal["respetar", "libre"]
"""Las dos palabras con que la interfaz y la CLI hablan de la veta."""


@dataclass(frozen=True)
class Recorte:
    """Un pedazo que sobró, para la corrida que viene y nada más.

    No es una entrada del catálogo: el catálogo describe lo que se compra,
    que se repite igual cada vez, y un recorte es de a uno y deja de existir
    cuando se cortó.
    """

    ancho: float
    alto: float
    cantidad: int = 1
    veta_cruzada: bool = False
    """La veta de este pedazo corre a lo ancho y no a lo alto."""


@dataclass(frozen=True)
class NestParams:
    """Todo lo que define una corrida, menos el archivo de entrada."""

    material: str
    sep: float = 5.0
    borde: float = 10.0
    copias: int = 1
    angulos: tuple[float, ...] = DEFAULT_ANGLES
    espejo: bool = True
    unidades: str | None = None
    tol_cierre: float = DEFAULT_CHAIN_TOL
    resolucion: float = 1.0
    esfuerzo: str = "normal"
    recortes: tuple[Recorte, ...] = ()
    veta: Veta | None = None
    """La veta de ESTA corrida. `None` es "la que diga el material".

    Es de la corrida y no del catálogo por lo mismo que los recortes: el
    catálogo dice lo que el material suele necesitar, y un trabajo concreto
    -- piezas que no se ven, un fenólico usado de base -- puede no
    necesitarlo. Ver `tolerancia_de_veta`.
    """

    nucleos: int | None = None
    """Cuántos núcleos usa la cartera. `None` es el valor por omisión de la
    máquina (`workers.machine().default`): todos menos dos, con el tope por
    memoria. Más núcleos prueban más combinaciones en el mismo tiempo."""


@dataclass(frozen=True)
class ReglaRota:
    """Qué campo incumplió qué regla, y con qué valor."""

    campo: str
    regla: str
    valor: object


class ParamsInvalidosError(ValueError):
    """Un parámetro no cumple su regla."""

    def __init__(self, rota: ReglaRota) -> None:
        super().__init__(f"{rota.campo} tiene que ser {rota.regla}, se recibió {rota.valor}")
        self.rota = rota


FLAG_POR_CAMPO: dict[str, str] = {
    "copias": "--copias",
    "sep": "--sep",
    "borde": "--borde",
    "tol_cierre": "--tol-cierre",
    "resolucion": "--resolucion",
    "angulos": "--angulos",
    "nucleos": "--nucleos",
}


REGLA_VETA = "compatible con la veta: al menos un ángulo a 0° o 180°"
"""La regla que se rompe cuando la veta no deja ningún ángulo en pie.

Se redacta como las demás ("tiene que ser ...") porque sale por los mismos
dos caminos: `mensaje_cli` en la terminal y el `detail` del 422 en la API.
"""


def validar(p: NestParams, material: Material | None = None) -> None:
    """Levanta `ParamsInvalidosError` en el primer parámetro que no cumple.

    El orden es el mismo que tenía `_validate_numeric_args` en `cli.py`, para
    que un comando con dos errores a la vez siga señalando el mismo primero.

    Con `material`, además, se fija que la veta deje en pie al menos uno de
    los ángulos pedidos. Sin él no puede saberlo: la CLI valida una vez antes
    de leer el catálogo y otra después.
    """
    if p.copias < 1:
        raise ParamsInvalidosError(ReglaRota("copias", ">= 1", p.copias))
    if p.sep < 0:
        raise ParamsInvalidosError(ReglaRota("sep", ">= 0", p.sep))
    if p.borde < 0:
        raise ParamsInvalidosError(ReglaRota("borde", ">= 0", p.borde))
    if p.tol_cierre <= 0:
        raise ParamsInvalidosError(ReglaRota("tol_cierre", "> 0", p.tol_cierre))
    if p.resolucion <= 0:
        raise ParamsInvalidosError(ReglaRota("resolucion", "> 0", p.resolucion))
    if p.nucleos is not None and p.nucleos < 1:
        raise ParamsInvalidosError(ReglaRota("nucleos", ">= 1", p.nucleos))
    for indice, recorte in enumerate(p.recortes, start=1):
        if recorte.ancho <= 0:
            raise ParamsInvalidosError(
                ReglaRota(f"recorte {indice}: ancho", "> 0", recorte.ancho)
            )
        if recorte.alto <= 0:
            raise ParamsInvalidosError(
                ReglaRota(f"recorte {indice}: alto", "> 0", recorte.alto)
            )
        if recorte.cantidad < 1:
            raise ParamsInvalidosError(
                ReglaRota(f"recorte {indice}: cantidad", ">= 1", recorte.cantidad)
            )
    if material is not None:
        # Contra la placa del material y no contra los recortes: si en ella
        # no sobrevive ningún ángulo, la primera pieza que no entre en un
        # recorte no tiene dónde ir, y el motor lo cuenta como una pieza
        # demasiado grande -- un mensaje sobre medidas para un problema de
        # ángulos.
        placa = Sheet(
            width=material.sheet_w,
            height=material.sheet_h,
            grain_tolerance=tolerancia_de_veta(p, material),
        )
        if not allowed_angles(placa, p.angulos):
            raise ParamsInvalidosError(ReglaRota("angulos", REGLA_VETA, p.angulos))


def mensaje_cli(rota: ReglaRota) -> str:
    """La redacción de terminal, con el nombre del flag adentro.

    Un campo sin flag -- los recortes, que sólo se cargan desde la interfaz
    -- se nombra tal cual en vez de romper con KeyError.
    """
    nombre = FLAG_POR_CAMPO.get(rota.campo, rota.campo)
    return f"{nombre} tiene que ser {rota.regla}, se recibió {rota.valor}"


def nucleos_efectivos(p: NestParams) -> tuple[int, str | None]:
    """Los núcleos que de verdad se usan, y el aviso si hubo que recortar.

    Un valor por encima del tope se acepta y se recorta al tope, con un
    aviso: rechazarlo haría que el mismo pedido ande en una máquina y falle
    en otra, y el usuario no eligió mal, eligió en otra computadora.
    """
    maquina = workers.machine()
    if p.nucleos is None:
        return maquina.default, None
    if p.nucleos > maquina.cap:
        return maquina.cap, (
            f"se pidieron {p.nucleos} núcleos y esta máquina da para "
            f"{maquina.cap} (por la cantidad de núcleos y la memoria): se "
            f"usan {maquina.cap}."
        )
    return p.nucleos, None


def a_config(p: NestParams) -> NestConfig:
    """Traduce al vocabulario del motor. No valida: eso es `validar`."""
    return NestConfig(
        sep=p.sep,
        margin=p.borde,
        angles=tuple(p.angulos),
        mirror=p.espejo,
        resolution=p.resolucion,
        effort=p.esfuerzo,
        workers=nucleos_efectivos(p)[0],
    )


def tolerancia_de_veta(p: NestParams, material: Material) -> float:
    """Los grados de tolerancia que valen para esta corrida.

    La única traducción de `NestParams.veta` a grados. `a_supply` y
    `validar` pasan por acá, para que el plan de placas y la regla de los
    ángulos no puedan leer la veta de dos maneras distintas.
    """
    if p.veta is None:
        return material.grain_tolerance
    return VETA_RESPETAR if p.veta == "respetar" else VETA_LIBRE


def a_supply(p: NestParams, material: Material) -> SheetSupply:
    """Arma el plan de placas: los recortes primero, la del Material después.

    Se ordenan de mayor a menor sin importar en qué orden se cargaron. Meter
    el grande primero evita que una pieza mediana quede varada porque el
    motor gastó el único recorte que la aceptaba en algo chico.

    La veta sale de `tolerancia_de_veta`, no de `material.grain_tolerance`:
    si la corrida dijo "no importa", un recorte de fenólico tampoco la
    respeta.
    """
    tolerancia = tolerancia_de_veta(p, material)
    hojas = [
        Sheet(
            width=recorte.ancho,
            height=recorte.alto,
            grain_tolerance=tolerancia,
            cross_grain=recorte.veta_cruzada,
            scrap=True,
        )
        for recorte in p.recortes
        for _ in range(recorte.cantidad)
    ]
    hojas.sort(key=lambda hoja: hoja.area, reverse=True)
    return SheetSupply(
        stock=replace(material.stock_sheet(), grain_tolerance=tolerancia),
        scraps=tuple(hojas),
        material_name=material.name,
    )
