"""The seam that makes nesting engines interchangeable.

An oracle answers one question: given a part at a given angle, and the current
state of a sheet, where can it go and how good is that spot? A raster engine
answers it with bitmaps; a No-Fit-Polygon engine would answer it with polygon
regions. Everything above this interface - ordering, rotations, multi-sheet
spilling, effort levels, reporting - never learns which one is in use.

The clearance offset is deliberately the oracle's responsibility. A raster
engine dilates masks; an NFP engine would offset polygons. Doing it outside
would tie the whole design to one of them.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from nesting.geometry.transform import apply_points
from nesting.model.entities import Transform
from nesting.model.part import Part


@dataclass(frozen=True)
class Weights:
    """How a candidate position is scored.

    Recalibrated against the hybrid engine in Task 6 of the density and
    exact-collision plan; the measurements are in
    `docs/superpowers/calibracion.md`.
    """

    bottom_left: float = 1.0
    """Pull towards the bottom-left corner, so the leftover stays in one block."""

    contact: float = 4.0
    """Reward for perimeter resting against material already placed.

    This is the term that produces interlocking between curved parts. Without
    it, bottom-left alone just stacks and leaves gaps.

    RECALIBRADO EN LA TAREA 6 (1.0 -> 4.0). La calibración anterior se hizo
    contra el motor conservador y contra `first_sheet_utilization`, que ya no
    es lo que el motor optimiza: desde la Tarea 1 el criterio es
    `CostoLayout(placas_nuevas, material_ultima, alto_ultima)`. Se volvió a medir
    con el motor híbrido, sobre tres archivos, midiendo el material que queda
    en la última placa. Tabla completa en
    `docs/superpowers/calibracion.md`; lo que decidió:

    1. NO SE PUEDE APAGAR. El piso funcional sigue existiendo, apenas más
       abajo que antes: bisecando sobre
       `test_a_small_part_is_nested_inside_a_big_hole`, la pieza chica deja
       de caer en el agujero de la grande con contacto en {0.0, 0.25, 0.5,
       0.6} y vuelve a caer desde 0.7 en adelante (antes el corte estaba
       entre 0.7 y 0.8). Así que 0.0 y 0.5 quedan descartados por el mismo
       piso: bottom-left solo gana el argmax y la pieza chica se planta en
       el fondo-izquierda de la placa vacía. La ventaja de velocidad es sólo
       de 0.0 -- 1.6-4.8x más rápido y gana el barrido en dos de los tres
       archivos -- porque el costo de la correlación FFT de contacto se paga
       o no según `contact != 0.0` (punto 2 más abajo), no según su
       magnitud: 0.5 tarda prácticamente lo mismo que 4.0 (25.9 s contra
       25.4 s sobre el archivo de referencia).

    2. ENTRE LOS QUE PASAN EL PISO, 4.0 NUNCA PERDIÓ CONTRA 1.0. Siete
       celdas, repartidas entre tres archivos, dos materiales, tres niveles
       de esfuerzo y tres cantidades de copias. Material en la última placa,
       en m²:

       | celda                          | 1.0    | 4.0    |
       |--------------------------------|--------|--------|
       | `NESTING 2.ai` mdf15 rapido    | 0.1432 | 0.0716 |
       | `NESTING 2.ai` mdf15 normal    | 0.1106 | 0.0716 |
       | `NESTING 2.ai` mdf15 lento     | 0.1061 | 0.0716 |
       | `muestra.dxf` mdf18 x8 rapido  | 2.1206 | 2.1206 |
       | `muestra.dxf` mdf18 x6 rapido  | 0.9220 | 0.9220 |
       | `banqueta...ai` mdf18 x5 rap.  | 0.7842 | 0.7582 |
       | `banqueta...ai` mdf18 x4 rap.  | 2.1164 | 2.1147 |

       Cinco victorias y dos empates, ninguna derrota. Sobre `NESTING 2.ai`
       eso son 34 piezas en la placa 1 y 2 en la última, contra 32/4. El
       costo en tiempo es un empate: el barrido FFT de contacto se paga o no
       según `contact != 0.0` (ver `raster/scoring.py::best_position`), no
       según su valor, así que las diferencias de segundos medidas -- 25.4 s
       contra 37.5 s a favor de 4.0 sobre `NESTING 2.ai`, 60.4 s contra
       38.7 s en contra sobre `muestra.dxf` x6 -- son del layout que salió,
       no del peso.

    3. PERO NO ES UNA TENDENCIA, ES UNA LOTERÍA CON UN GANADOR CONSISTENTE.
       La respuesta no es monótona: 2.0 fue el peor de los candidatos que
       pasan el piso en 3 de las 5 celdas donde se lo midió, y subir más
       allá de 4.0 sobre `NESTING 2.ai` empeora (8.0 deja 0.1789 m² y 16.0
       deja 0.1172, contra 0.0716 de 4.0). 0.8 le gana a 4.0 en dos celdas,
       empata en una y pierde en cuatro. Y la cantidad de PLACAS -- el
       criterio que manda -- fue idéntica en las 7 celdas con todos los
       pesos. O sea: este peso no decide placas sobre los archivos medidos,
       decide cuánto queda arriba en la última, y ahí 4.0 es el que más
       veces quedó adelante, no el que sigue una pendiente.

    4. UNA VEZ SÍ DECIDIÓ PLACAS, en un caso sintético justo en el quiebre:
       48 rectángulos variados, generados con el mismo patrón que el fixture
       de
       `tests/engine/test_effort.py::test_different_seeds_can_give_different_results`
       (mismo material de 1000x1000, sep 8, borde 15, esfuerzo normal) --
       NO es el fixture tal como quedó en el repo, que tiene 52 piezas,
       elegidas por una razón distinta (que la Tarea 6 documenta en el
       docstring del propio test: que la salida siga siendo sensible a la
       semilla con los dos pesos). No quedó establecido, a partir de lo
       medido en la Tarea 6, si esta corrida de 48 sigue dando el mismo
       resultado sobre el fixture de 52 piezas que terminó commiteado; lo
       que sí está medido es que estas 48 piezas entran en UNA placa con
       contacto 4.0 y semillas 1 o 2, y necesitan DOS con contacto 1.0 en
       las cuatro semillas probadas. Es una muestra sintética, no un archivo
       real, pero es la única celda medida donde este peso cambió lo que le
       cuesta al usuario.

    Por eso 4.0 y no más: es el mejor medido, es el máximo del rango
    barrido que todavía mejora, y el escalón siguiente ya empeora.
    """

    def __post_init__(self) -> None:
        if self.bottom_left < 0:
            raise ValueError(
                f"bottom_left tiene que ser mayor o igual a cero, "
                f"recibido {self.bottom_left!r}"
            )
        if self.contact < 0:
            raise ValueError(
                f"contact tiene que ser mayor o igual a cero, "
                f"recibido {self.contact!r}"
            )


@dataclass(frozen=True)
class NestConfig:
    sep: float = 5.0
    """Minimum gap between parts, in mm."""

    margin: float = 10.0
    """Minimum gap between a part and the sheet edge, in mm."""

    angles: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)
    mirror: bool = True
    resolution: float = 2.0
    """Raster resolution in mm per pixel. Ignored by non-raster oracles.

    QUÉ COMPRA HOY. Ya no compra separación. Hasta la Tarea 3 la grilla
    decidía las colisiones sola, y como rasterizar conservador infla cada
    pieza, una grilla gruesa regalaba milímetros: pedir 10 mm de separación
    daba 16 mm reales a 2 mm/px. Ahora los candidatos los propone la grilla
    con halo optimista y los decide `ArbitroExacto` sobre los polígonos
    exactos (`engine/exact.py`), así que la separación entregada es la
    pedida -- 10.00 mm -- a cualquier resolución. Lo único que queda en
    manos de la resolución es la FINURA DE LA BÚSQUEDA: en qué retícula de
    posiciones se proponen los candidatos, y cuántos hay que puntuar.

    MEDIDO EN LA TAREA 6 (contacto 1.0, esfuerzo rapido, cero violaciones
    del verificador exacto en las 10 celdas), material que queda en la
    última placa y segundos:

    | archivo                       | 3.0 mm/px | 2.0 mm/px | 1.0 mm/px | 0.5 mm/px |
    |-------------------------------|-----------|-----------|-----------|-----------|
    | `NESTING 2.ai` (mdf15, sep 10)| 0.2538 m² | 0.1432 m² | 0.1432 m² | 0.1789 m² |
    |                               | 9.6 s     | 36.8 s    | 110.4 s   | 646.2 s   |
    | `muestra.dxf` x8 (mdf18)      | 2.1206 m² | 2.1206 m² | 1.9823 m² | (no medido)|
    |                               | 51.7 s    | 70.2 s    | 413.5 s   |           |
    | `banqueta final raulo.ai` x4  | 2.1229 m² | 2.1164 m² | 2.0090 m² | (no medido)|
    |                               | 74.6 s    | 230.7 s   | 1077.2 s  |           |

    POR QUÉ 2.0 SE QUEDA. Afinar a 1.0 mm/px no cambió nada sobre
    `NESTING 2.ai` (mismas cifras, exactamente el mismo reparto 32/4) y
    costó 3x el tiempo; sobre los dos archivos del banco sí compró densidad
    real (un 5-7% menos de material en la última placa) pero al precio de
    4.7-5.9x el tiempo. En ningún archivo cambió la cantidad de PLACAS, que
    es el criterio que manda. Y afinar más no es un dial monótono: 0.5 mm/px
    sobre `NESTING 2.ai` salió PEOR que 2.0 (31/5 contra 32/4) y 17.6x más
    lento -- una retícula más fina propone candidatos distintos, no
    mejores. Del otro lado, 3.0 mm/px empata en los dos archivos del banco
    pero se desploma en el de referencia (29/7 contra 32/4), que es
    justamente el caso apretado para el que se usa el programa.

    2.0 mm/px es entonces la rodilla medida: el punto donde engrosar ya
    arruina un caso real y afinar sólo paga tiempo. Quien tenga tiempo de
    sobra y un trabajo pegado a un salto de placa puede bajar a 1.0 a mano
    con `--resolucion`; como default, 5x el tiempo por un 5% de material en
    la última placa no se justifica.
    """

    effort: str = "normal"
    """One of "rapido", "normal", "lento"."""

    seed: int = 0
    workers: int = 1
    """Cuántas variantes por tanda prueba la cartera: la `N` de la spec.

    Es a la vez cuántos procesos corren a la par (Tarea 6 del plan de pares
    y cartera). Con 1 todo corre en el proceso que llama, sin crear nada: es
    el valor por omisión para que el motor, usado como biblioteca o desde un
    test, no dispare procesos que nadie pidió. La CLI y la interfaz pasan el
    valor que corresponde a la máquina (`nesting.params.nucleos_efectivos`).
    """

    weights: Weights = field(default_factory=Weights)


@runtime_checkable
class Oracle(Protocol):
    """Where can this part go on this sheet, and how good is that spot?"""

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        """Start a fresh, empty sheet."""
        ...

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        """Best (dx, dy, score) for this orientation, or None if it does not fit.

        Higher scores are better. Must NOT mutate state: the packer asks about
        several orientations before committing to one.
        """
        ...

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        """Commit a placement at exactly (x, y), so later queries see it occupied.

        An implementation MUST honour the (x, y) it is given rather than deriving
        a position of its own. If it cannot represent an arbitrary position - a
        shelf packer only tracks a cursor - it MUST validate the argument against
        the position it would have produced and raise `ValueError` on a mismatch.
        Silently committing a different position than the caller asked for
        desynchronises the oracle's state from the layout being built, and the
        parts placed afterwards overlap with no error anywhere.

        Precondition: (x, y) comes from a `best_placement` call for this same
        (part, angle, mirror), with no intervening `place`.
        """
        ...


def transformed_bbox(
    part: Part, angle: float, mirror: bool
) -> tuple[float, float, float, float]:
    """Bounding box of `part` at this orientation, before any translation."""
    points = apply_points(Transform(angle, mirror, 0.0, 0.0), part.outer)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))
