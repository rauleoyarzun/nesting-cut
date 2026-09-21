"""La última palabra sobre si una pieza entra en una posición.

La grilla de raster (`raster/masks.py`) sobre-representa cada pieza a
propósito: nunca puede decir que hay material donde no lo hay, pero sí dice
que lo hay donde no llega. Esa asimetría es lo que la hace segura, y también
lo que le impide contestar esta pregunta sin regalar milímetros -- medido, a
2 mm/px deja 16 mm entre dos piezas cuando se le piden 10.

Acá se contesta sobre los polígonos exactos. Cuesta ~312 µs por consulta
entre dos piezas de ~900 vértices, así que sirve como árbitro de unos pocos
candidatos, nunca como buscador de posiciones: un barrido de la placa entera
son millones de consultas. Ese reparto de tareas -- la grilla busca, esto
arbitra -- es toda la arquitectura del motor híbrido.
"""

from shapely.geometry import Polygon

from nesting.geometry.verify import OVERLAP_AREA_THRESHOLD_MM2, placed_polygon
from nesting.model.entities import Transform
from nesting.model.part import Part

EPS = 1e-6
"""Tolerancia contra el ruido de punto flotante.

`verify.py` usa la misma para la misma comparación. Tienen que coincidir: si
el árbitro fuera más permisivo que el verificador, aceptaría layouts que
después el verificador rechaza, y el usuario vería fallar un trabajo que el
motor dio por bueno.
"""


class ArbitroExacto:
    """Los polígonos ya colocados en UNA placa, y si entra uno más."""

    def __init__(self, sheet_w: float, sheet_h: float, sep: float, margin: float) -> None:
        if sep < 0 or margin < 0:
            raise ValueError(
                f"sep y margin tienen que ser >= 0 (se recibió sep={sep!r}, "
                f"margin={margin!r})"
            )
        self._sheet_w = sheet_w
        self._sheet_h = sheet_h
        self._sep = sep
        self._margin = margin
        self._colocados: list[tuple[Polygon, tuple[float, float, float, float]]] = []

    def limpiar(self) -> None:
        """Vaciar la placa, para reusar el árbitro en la siguiente."""
        self._colocados.clear()

    def entra(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> bool:
        """¿La pieza en esa posición respeta borde y separación, exactos?"""
        poly = placed_polygon(part, Transform(angle, mirror, x, y))
        return self._entra_poly(poly)

    def agregar(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        """Dar por colocada la pieza. No revalida: el llamador ya preguntó."""
        poly = placed_polygon(part, Transform(angle, mirror, x, y))
        self._colocados.append((poly, poly.bounds))

    def _entra_poly(self, poly: Polygon) -> bool:
        minx, miny, maxx, maxy = poly.bounds
        m = self._margin
        if (
            minx < m - EPS
            or miny < m - EPS
            or maxx > self._sheet_w - m + EPS
            or maxy > self._sheet_h - m + EPS
        ):
            return False

        # Prefiltro por caja: `distance` sobre polígonos de ~900 vértices
        # cuesta ~312 µs, y comparar cuatro números cuesta nada. Sin esto,
        # colocar la pieza número 30 pagaría 30 consultas caras, la mayoría
        # contra piezas que están al otro lado de la placa.
        s = self._sep
        for otro, (omin_x, omin_y, omax_x, omax_y) in self._colocados:
            if maxx + s < omin_x or omax_x + s < minx:
                continue
            if maxy + s < omin_y or omax_y + s < miny:
                continue
            # `distance` sola no alcanza: shapely la devuelve 0.0 tanto para
            # "apenas se tocan" como para "una pieza atropella a la otra", y
            # con sep=0.0 (valor legítimo, el CLI lo acepta) la comparación
            # `0.0 < 0.0 - EPS` es siempre falsa -- cualquier superposición,
            # por grande que sea, pasaría. Por eso primero se mira el área de
            # la intersección, igual que `verify.py`: si de verdad se pisan,
            # no entra, sin importar `sep`.
            if poly.intersects(otro):
                if poly.intersection(otro).area > OVERLAP_AREA_THRESHOLD_MM2:
                    return False
            if poly.distance(otro) < s - EPS:
                return False
        return True
