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

from dataclasses import dataclass

from nesting.engine.oracle import NestConfig
from nesting.tolerances import DEFAULT_CHAIN_TOL

DEFAULT_ANGLES: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)


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
    resolucion: float = 2.0
    esfuerzo: str = "normal"


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
}


def validar(p: NestParams) -> None:
    """Levanta `ParamsInvalidosError` en el primer parámetro que no cumple.

    El orden es el mismo que tenía `_validate_numeric_args` en `cli.py`, para
    que un comando con dos errores a la vez siga señalando el mismo primero.
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


def mensaje_cli(rota: ReglaRota) -> str:
    """La redacción de terminal, con el nombre del flag adentro."""
    return f"{FLAG_POR_CAMPO[rota.campo]} tiene que ser {rota.regla}, se recibió {rota.valor}"


def a_config(p: NestParams) -> NestConfig:
    """Traduce al vocabulario del motor. No valida: eso es `validar`."""
    return NestConfig(
        sep=p.sep,
        margin=p.borde,
        angles=tuple(p.angulos),
        mirror=p.espejo,
        resolution=p.resolucion,
        effort=p.esfuerzo,
    )
