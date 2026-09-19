"""Lo que el programa tira, con la geometría suficiente para mostrárselo.

Cada sitio que descarta algo devuelve el objeto descartado, no un contador:
el aviso de texto sale de `len(...)` sobre la misma lista que dibuja el
diagnóstico, así que el número que se imprime y lo que se marca en la imagen
no pueden discrepar. Un contador por un lado y una lista por el otro sí
podrían, y esa clase de deriva -- el mensaje diciendo una cosa y el archivo
mostrando otra -- ya apareció una vez en este proyecto (los colores que la
previsualización mostraba bien y el DXF perdía).
"""

from dataclasses import dataclass, field

from nesting.model.entities import Point


@dataclass(frozen=True)
class DiscardStyle:
    """Cómo se nombra y se pinta un motivo de descarte."""

    label: str
    color: tuple[int, int, int]


DISCARD_STYLES: dict[str, DiscardStyle] = {
    "duplicada": DiscardStyle(
        "entidad duplicada (dibujada dos veces, una encima de la otra)",
        (220, 30, 30),
    ),
    "suelta": DiscardStyle(
        "tramo suelto (no encierra área, no puede ser el contorno de una pieza)",
        (30, 90, 220),
    ),
    "area_nula": DiscardStyle(
        "contorno de área nula o degenerada",
        (200, 120, 0),
    ),
    "no_es_curva": DiscardStyle(
        "objeto que no es una curva (cota, texto, sólido)",
        (140, 60, 190),
    ),
    "no_plana": DiscardStyle(
        "curva que no está apoyada en el plano XY",
        (0, 150, 130),
    ),
    "borde_lienzo": DiscardStyle(
        "borde del lienzo declarado en la cabecera del archivo",
        (120, 120, 120),
    ),
    "capa_placa": DiscardStyle(
        "entidad en la capa reservada para los contornos de placa",
        (90, 90, 40),
    ),
    "tipo_no_soportado": DiscardStyle(
        "tipo de entidad que no participa del nesting",
        (170, 100, 100),
    ),
    "contorno_placa": DiscardStyle(
        "rectángulo del tamaño exacto de la placa del material",
        (210, 60, 160),
    ),
}


@dataclass(frozen=True)
class Discard:
    """Una cosa que el programa no va a acomodar, y por qué.

    `points` es el contorno en XY, en milímetros, cuando existe. Hay descartes
    que no lo tienen -- una cota de Rhino, un tipo de entidad DXF que el
    lector ni convierte -- y se guardan igual con `points` vacío: que no se
    puedan marcar sobre el plano no es razón para esconderlos, porque el aviso
    de texto sí los cuenta y el usuario va a querer saber a qué corresponden.
    """

    reason: str
    points: tuple[Point, ...] = ()
    detail: str = ""
    closed: bool = False
    """Si `points` es un anillo y no un tramo abierto.

    Los contornos de este programa se guardan sin repetir el primer punto al
    final (ver `Contour`), asi que sin este dato un rectangulo se dibuja con
    un lado menos -- y un rectangulo al que le falta un lado se lee como
    geometria rota, que es justo el diagnostico equivocado.
    """
    style: DiscardStyle = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        style = DISCARD_STYLES.get(self.reason)
        if style is None:
            raise ValueError(
                f"motivo de descarte desconocido: {self.reason!r}. "
                f"Los conocidos son {', '.join(sorted(DISCARD_STYLES))}."
            )
        object.__setattr__(self, "style", style)

    @property
    def path(self) -> tuple[Point, ...]:
        """Los puntos tal como se dibujan, con el anillo ya cerrado."""
        if not self.closed or not self.points or self.points[0] == self.points[-1]:
            return self.points
        return (*self.points, self.points[0])

    @property
    def has_geometry(self) -> bool:
        return bool(self.points)

    @property
    def centroid(self) -> Point | None:
        """Dónde poner la marca. `None` cuando no hay nada que marcar."""
        if not self.points:
            return None
        return (
            sum(p[0] for p in self.points) / len(self.points),
            sum(p[1] for p in self.points) / len(self.points),
        )
