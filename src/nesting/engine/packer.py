"""Strategy: what order, which rotations, and when to open a new sheet.

Knows nothing about how placement is computed. It talks to an `Oracle`, so the
same code drives the throwaway shelf engine and the real raster engine.
"""

import os
import random
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

from nesting.engine.oracle import NestConfig, Oracle, Weights, transformed_bbox
from nesting.engine.prevision import (
    estimate_sheets,
    forecast_pack,
    forecast_recovery,
)
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement
from nesting.model.sheet import Sheet, SheetSupply, allowed_angles


class PartTooLargeError(Exception):
    """A part does not fit on an empty sheet, so no layout can ever contain it."""


@dataclass
class PackResult:
    placements: list[Placement] = field(default_factory=list)
    sheets: list[Sheet] = field(default_factory=list)
    """Qué placa concreta fue cada índice, en orden.

    Sin esto, todo lo que viene después de `pack` -- el verificador, el
    escritor de DXF, la previsualización -- tendría que adivinar la medida
    de cada placa, y con recortes en juego adivinar es escribir un DXF
    equivocado.
    """

    utilization: list[float] = field(default_factory=list)
    """Fraction of each sheet covered by part material."""

    total_utilization: float = 0.0
    seconds: float = 0.0

    @property
    def sheets_used(self) -> int:
        """Cuántas placas tiene el layout. DERIVADO, no un campo aparte.

        Era un campo, y dos nociones de "última placa" convivían: este
        archivo usa `sheets_used - 1` en tres lugares y `layout_cost` usa
        `len(sheets) - 1`. Cuando no coincidían, `layout_cost` no fallaba:
        no encontraba ninguna colocación en su "última placa" y devolvía
        `CostoLayout(0, 0.0, 0.0)` en silencio, que empata con cualquier
        otro layout igual de roto. Unos fixtures de `test_effort.py` con
        `sheets_used=2` y `sheets=[]` ya hicieron exactamente eso.

        Derivarlo hace que las dos nociones sean una sola por construcción,
        y que un `PackResult` armado a mano no pueda mentir: quien quiera
        dos placas tiene que dar las dos placas.
        """
        return len(self.sheets)


@dataclass(frozen=True)
class Avance:
    """Dónde va el motor, para quien esté mirando.

    Lleva el intento además de las piezas porque `pack` corre varias pasadas
    completas y CADA UNA REINICIA el conteo de ubicadas. Una barra armada
    sólo con `ubicadas / totales` retrocedería al empezar el intento
    siguiente, y una barra que retrocede es peor que no tener barra.

    Las consultas son la otra mitad, y la que sirve para estimar el tiempo:
    contar piezas engaña, porque una pieza que no entra gasta sus consultas
    igual y las fases finales no ubican piezas nuevas. Ver
    `nesting/engine/prevision.py`.
    """

    intento: int
    intentos: int
    ubicadas: int
    totales: int
    placa: int
    compactando: bool = False
    consultas_hechas: int = 0
    """Llamadas a `Oracle.best_placement` desde que empezó `pack`, sumando
    todos los intentos y todas las fases. No se reinicia nunca."""

    consultas_previstas: int = 0
    """La mejor previsión del total en este momento. Nunca es menor que
    `consultas_hechas`, y en el último aviso de `pack` es igual.

    Tiene valor por omisión, igual que `consultas_hechas`, para que quien
    arma un `Avance` a mano con los cinco campos de siempre -- los corredores
    de mentira de `tests/app` -- no tenga que cambiar nada."""

    combinaciones: int = 0
    """Cuántas variantes prevé la cartera en total, base incluida.

    Cero mientras corre la base: la pantalla muestra entonces el texto de
    siempre (piezas ubicadas, placa en curso). Distinto de cero mientras se
    prueban las tandas, cuando varias variantes corren a la vez y "ubicadas
    de tantas" deja de tener sentido.
    """

    combinaciones_hechas: int = 0
    """Variantes terminadas, base incluida."""

    placa_minima: int = 0
    """Placas de la mejor variante terminada hasta ahora."""


class Cancelado(Exception):
    """El motor abandonó porque quien lo miraba se lo pidió.

    Es una excepción y no un `PackResult` a medias a propósito: un resultado
    incompleto se puede escribir a un DXF sin que nada avise, y ese DXF va a
    una fresadora.
    """


def replicate(parts: Sequence[Part], copies: int) -> list[Part]:
    """Repeat every part `copies` times, renumbering ids.

    The copies keep the original `entity_ids`, so they all draw the same source
    geometry at different places.
    """
    if copies < 1:
        raise ValueError(f"la cantidad de copias debe ser al menos 1, se recibió {copies}")

    out: list[Part] = []
    for _ in range(copies):
        for part in parts:
            out.append(
                Part(
                    id=len(out),
                    outer=part.outer,
                    holes=part.holes,
                    entity_ids=part.entity_ids,
                )
            )
    return out


def orientations(sheet: Sheet, config: NestConfig) -> list[tuple[float, bool]]:
    """Cada par (ángulo, espejo) que la veta de ESTA placa y el config permiten."""
    angles = allowed_angles(sheet, config.angles)
    result = [(a, False) for a in angles]
    if config.mirror:
        result.extend((a, True) for a in angles)
    return result


def probe_query_seconds(
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    clock: Callable[[], float] = time.perf_counter,
    threaded: bool = False,
) -> float | None:
    """Cuánto tarda UNA consulta en esta máquina, con estas opciones.

    Pregunta por la pieza más grande, en la primera orientación que la veta
    de la placa del Material permite, sobre una placa vacía. Mide CONSULTAS,
    no rasterizado: antes de largar el reloj se le pide al oráculo que
    prepare las máscaras de las orientaciones que se van a consultar
    (`warm`, si lo tiene). En la corrida cada máscara se rasteriza una vez y
    se reusa en cientos de consultas, así que su costo por consulta es casi
    nada; en la prueba, en cambio, pesaba lo mismo que la consulta, y
    `FACTOR_LLENO` tenía que absorberlo -- distinto en cada archivo, según
    cuánto cuesta rasterizar su pieza más grande. `reset` también queda
    afuera: se paga una vez por placa, no por consulta.

    Sin `threaded`, una sola consulta y no un promedio: tarda menos de un
    segundo, y el número vale en cualquier máquina porque se mide en ella.
    Es lo que cuesta una consulta en un proceso de la cartera, con un hilo.
    Devuelve `None` si no hay piezas o si la veta no deja ninguna orientación.

    Con `threaded=True` mide lo que cuesta una consulta en el proceso
    principal, donde corren en hilos (`QUERY_THREADS`): pregunta por TODAS
    las orientaciones de la pieza con `_query_orientations`, como hace la
    corrida, y divide el tiempo por cuántas son. Tarda más que una sola
    consulta, del orden de las orientaciones divididas por los hilos, más
    rasterizarlas todas antes (fuera del tiempo medido).
    """
    if not parts:
        return None
    choices = orientations(supply.stock, config)
    if not choices:
        return None
    part = max(parts, key=lambda p: p.area)
    oracle = oracle_factory()
    oracle.reset(supply.stock.width, supply.stock.height, config)
    consultadas = choices if threaded else choices[:1]
    warm = getattr(oracle, "warm", None)
    if warm is not None:
        warm(part, consultadas)
    if threaded:
        started = clock()
        _query_orientations(oracle, part, consultadas)
        return (clock() - started) / len(consultadas)
    angle, mirror = consultadas[0]
    started = clock()
    oracle.best_placement(part, angle, mirror)
    return clock() - started


def _pack_once(
    order: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    aviso: Callable[[int, int], None] | None = None,
    orientation_ranks: Mapping[int, int] | None = None,
) -> PackResult:
    """One greedy pass, placing `order` in exactly the order given.

    `aviso` recibe (piezas ubicadas hasta ahora en esta pasada, placa en
    curso empezando en 1) despues de cada pieza INTENTADA, haya entrado o
    no: una pieza que no entra gasta sus consultas igual, y sin aviso ni el
    contador de consultas ni el pedido de cancelar la verian. Puede levantar
    para abandonar: esta funcion no atrapa nada, asi que la excepcion sale
    limpia sin dejar estado a medias en el oraculo.

    `orientation_ranks`, si se pasa, dice para algunas piezas (por id) qué
    orientación tomar en vez de la mejor: 0 es la mejor, 1 la segunda, y
    así. Es la perturbación de orientaciones de `lento` (ver
    `cartera.VariantSource`); sin pasarlo, todo es exactamente como antes.
    """
    started = time.perf_counter()
    result = PackResult()

    if not order:
        result.seconds = time.perf_counter() - started
        return result

    remaining = list(order)
    usadas: list[Sheet] = []
    placed_area_per_sheet: list[float] = []

    # Dos contadores y no uno: `siguiente` avanza por el plan de placas y
    # `len(usadas)` cuenta las que de verdad recibieron algo. Dejan de ser
    # el mismo número apenas se saltea un recorte vacío (ver la guarda de
    # `placed_count == 0`), y las colocaciones tienen que llevar el segundo.
    siguiente = 0
    total_ubicadas = 0
    while remaining:
        hoja = supply.sheet(siguiente)
        siguiente += 1

        # Por placa y no por corrida: dos placas del mismo material pueden
        # tener la veta al revés y permitir ángulos distintos.
        choices = orientations(hoja, config)
        oracle = oracle_factory()
        oracle.reset(hoja.width, hoja.height, config)

        indice = len(usadas)
        still_pending: list[Part] = []
        en_esta_placa: list[Placement] = []
        placed_area = 0.0
        placed_count = 0

        for part in remaining:
            rank = orientation_ranks.get(part.id, 0) if orientation_ranks else 0
            spot = _best_over_orientations(oracle, part, choices, rank)
            if spot is None:
                still_pending.append(part)
            else:
                angle, mirror, x, y = spot
                oracle.place(part, angle, mirror, x, y)
                en_esta_placa.append(
                    Placement(part.id, indice, Transform(angle, mirror, x, y))
                )
                placed_area += part.area
                placed_count += 1
            if aviso is not None:
                aviso(total_ubicadas + placed_count, indice + 1)

        # Ver el comentario largo de la versión anterior: la guarda mira si
        # se colocó ALGO, no cuánta área, porque una pieza de área neta cero
        # dejaría `placed_area == 0.0` con `still_pending` vacío.
        if placed_count == 0:
            # Un recorte donde no entra ninguna pieza es normal -- un pedazo
            # de 100x100 no sirve para nada grande -- así que se saltea y no
            # llega a existir en el resultado: ni placa al 0% en la
            # previsualización, ni rectángulo vacío en el DXF. En una placa
            # del Material sigue siendo el error de siempre.
            #
            # LA CONDICIÓN MIRA LA POSICIÓN EN EL PLAN, NO `hoja.scrap`, Y LA
            # DIFERENCIA ES UN BUCLE INFINITO. Lo que hace seguro saltear no
            # es que la placa sea un recorte: es que la próxima vuelta vaya a
            # recibir una placa DISTINTA. Eso vale mientras queden recortes
            # por consumir, y deja de valer apenas `supply.sheet()` entra en
            # su placa infinita, que devuelve la misma para siempre. Los dos
            # `SheetSupply` que este mismo archivo arma adentro
            # (`_recuperar_de_la_ultima_placa` y `_compact_last_sheet`) pasan
            # un recorte COMO stock: con `if hoja.scrap` ahí, un reempaque
            # donde no entrara nada giraría sin fin en vez de levantar.
            if siguiente - 1 < len(supply.scraps):
                continue
            _raise_too_large(
                still_pending[0], hoja, config, choices, supply.material_name
            )

        result.placements.extend(en_esta_placa)
        usadas.append(hoja)
        placed_area_per_sheet.append(placed_area)
        total_ubicadas += placed_count
        remaining = still_pending

    result.sheets = usadas
    result.utilization = [
        area / hoja.area for area, hoja in zip(placed_area_per_sheet, usadas)
    ]
    area_total = sum(hoja.area for hoja in usadas)
    result.total_utilization = (
        sum(placed_area_per_sheet) / area_total if area_total else 0.0
    )
    result.seconds = time.perf_counter() - started
    return result


QUERY_THREADS = 4
"""Cuántos hilos consultan a la vez las orientaciones de una pieza (fase 2, idea B).

Sólo en el proceso principal, y nunca más que los núcleos de la máquina
(`query_threads`). Ahí corren solas la base, la recuperación y la
compactación, y scipy suelta el GIL en las FFT: medido sobre `bench/files`,
`rapido` tarda un 65% menos con el mismo layout (docs/superpowers/calibracion.md).

En los procesos de la cartera, uno solo: `cartera._init_worker` apaga los
hilos. Una tanda ya ocupa un núcleo por proceso, así que más hilos no suman
nada y sólo compiten por los mismos núcleos; y cada consulta en vuelo tiene
sus propios arreglos de FFT, así que con 4 hilos el pico de un proceso subió
de 1,1-1,2 GB a 1,6-2,0 GB (`rapido` sobre `bench/files`), y
`workers.MEMORY_PER_WORKER_BYTES`, que fija cuántos procesos entran en la
memoria, está medido con uno.
"""

_threads_allowed = True
_pool_lock = threading.Lock()
_pool: ThreadPoolExecutor | None = None
_pool_size = 0


def allow_query_threads(allowed: bool) -> None:
    """Prender o apagar los hilos de consulta en ESTE proceso.

    La cartera los apaga en cada proceso de su pool (`cartera._init_worker`).
    Apagarlos cierra el pool, si había uno.
    """
    global _threads_allowed
    _threads_allowed = allowed
    if not allowed:
        shutdown_query_pool()


def query_threads() -> int:
    """Cuántos hilos usa `_query_orientations` en este proceso: 1 es sin hilos."""
    if not _threads_allowed:
        return 1
    return max(1, min(QUERY_THREADS, os.cpu_count() or 1))


def _pool_for(n: int) -> ThreadPoolExecutor:
    """El pool de `n` hilos, uno solo por proceso.

    Se arma bajo cerrojo la primera vez, y se reusa mientras `n` no cambie.
    Si cambia (un test que toca `QUERY_THREADS`), el anterior se cierra
    esperando lo que tenga en vuelo y se arma otro: nunca quedan dos vivos.
    """
    global _pool, _pool_size
    with _pool_lock:
        if _pool is None or _pool_size != n:
            if _pool is not None:
                _pool.shutdown(wait=True)
            _pool = ThreadPoolExecutor(max_workers=n, thread_name_prefix="consultas")
            _pool_size = n
        return _pool


def shutdown_query_pool() -> None:
    """Cerrar el pool de consultas, si hay uno. El próximo pedido arma otro."""
    global _pool, _pool_size
    with _pool_lock:
        if _pool is not None:
            _pool.shutdown(wait=True)
        _pool, _pool_size = None, 0


def _query_orientations(oracle, part, choices):
    """Todas las consultas de una pieza, en el orden de `choices`.

    En `query_threads()` hilos, o acá mismo si es 1. Las máscaras se piden
    antes, desde este hilo (`warm`, si el oráculo lo tiene), para que los
    hilos no rastericen; `best_placement` es de sólo lectura sobre todo lo
    demás (la grilla, el árbitro), que es lo que el protocolo `Oracle` exige.
    """
    warm = getattr(oracle, "warm", None)
    if warm is not None:
        warm(part, choices)
    n = query_threads()
    if n <= 1 or len(choices) <= 1:
        return [oracle.best_placement(part, angle, mirror) for angle, mirror in choices]
    return list(_pool_for(n).map(lambda c: oracle.best_placement(part, c[0], c[1]), choices))


def _best_over_orientations(
    oracle: Oracle,
    part: Part,
    choices: Sequence[tuple[float, bool]],
    rank: int = 0,
) -> tuple[float, bool, float, float] | None:
    """Ask the oracle about every orientation and keep the best-scoring one.

    Con `rank > 0`, la `rank`-ésima mejor (o la peor que entra). Las
    consultas corren en hilos (`_query_orientations`), pero la elección se
    hace sobre los resultados en el orden de `choices`: en empate gana la
    primera, igual que antes.
    """
    answers = _query_orientations(oracle, part, choices)
    if rank == 0:
        best: tuple[float, bool, float, float] | None = None
        best_score = float("-inf")
        for (angle, mirror), spot in zip(choices, answers):
            if spot is None:
                continue
            x, y, score = spot
            if score > best_score:
                best_score = score
                best = (angle, mirror, x, y)
        return best

    spots = [
        (-spot[2], position, angle, mirror, spot[0], spot[1])
        for position, ((angle, mirror), spot) in enumerate(zip(choices, answers))
        if spot is not None
    ]
    if not spots:
        return None
    spots.sort()
    _, _, angle, mirror, x, y = spots[min(rank, len(spots) - 1)]
    return angle, mirror, x, y


def _raise_too_large(
    part: Part,
    sheet: Sheet,
    config: NestConfig,
    choices: Sequence[tuple[float, bool]],
    material_name: str,
) -> None:
    """Informa la huella más chica que la pieza puede tomar, contra el área útil.

    Se elige UNA orientación -- la que minimiza su propia dimensión mayor --
    en vez de tomar el ancho mínimo y el alto mínimo por separado, que
    pueden venir de dos orientaciones distintas y describir una caja que la
    pieza nunca tiene.
    """
    best_w = best_h = None
    best_max = float("inf")
    for angle, mirror in choices:
        x0, y0, x1, y1 = transformed_bbox(part, angle, mirror)
        w, h = x1 - x0, y1 - y0
        if max(w, h) < best_max:
            best_max = max(w, h)
            best_w, best_h = w, h

    usable_w = sheet.width - 2 * config.margin
    usable_h = sheet.height - 2 * config.margin
    raise PartTooLargeError(
        f"la pieza {part.id} no entra en una placa vacía: mide al menos "
        f"{best_w:.1f} x {best_h:.1f} mm en su mejor orientación, "
        f"y el área útil de la placa {material_name} es "
        f"{usable_w:.1f} x {usable_h:.1f} mm (margen {config.margin} mm)."
    )


COMPACTION_BOOST = 3.0
"""How much the bottom-left weight is multiplied by on the final compaction pass."""


class UnknownEffortError(Exception):
    """The requested effort level is not one of the three defined ones."""


@dataclass(frozen=True, order=True)
class CostoLayout:
    """Qué tan malo es un layout. Menor es mejor; se compara campo por campo.

    El orden de los campos ES el criterio, y por eso son campos con nombre y
    no una tupla: los dos lugares que informan el sobrante al usuario sacan
    `alto_ultima` por nombre, así que sumar un campo en el medio no puede
    volver a significar otra cosa en silencio.
    """

    placas_nuevas: int
    """Cuántas placas del Material hubo que abrir. Manda sobre todo lo demás.

    Los recortes NO se cuentan: son material que ya está pago, así que
    llenarlos no cuesta nada y el motor no tiene que evitarlo. Si contaran,
    el motor preferiría saltear un recorte de 600x800 y meter todo en una
    placa nueva -- una placa contra dos -- que es exactamente lo contrario
    de para qué existen los recortes.

    Sin recortes en el plan, este número es idéntico a `sheets_used`, y el
    costo entero da lo mismo que antes de que existieran.
    """

    material_ultima: float
    """Área de pieza que queda en la última placa, en mm².

    Es el segundo criterio, y no el alto, porque es el único que mide
    progreso hacia no necesitar esa placa: bajarlo a cero elimina una placa
    entera. El alto no mide eso -- entre un layout que deja 7 piezas en una
    fila de 308 mm y uno que deja 3 apiladas en 491 mm, el alto premia el de
    7 piezas aunque esté más lejos de poder tirar la placa. Sobre
    `NESTING 2.ai` ese desempate hacía que el motor descartara los layouts
    de 33/3 que él mismo encontraba.
    """

    alto_ultima: float
    """Hasta dónde llega el material en la última placa, en mm.

    Desempata entre layouts que dejan el mismo material: con la misma
    cantidad de pieza arriba, la que está más compactada deja la tira libre
    en un solo bloque en vez de en pedazos. `sheet_h - alto_ultima` es el
    "sobrante" que se le muestra al usuario.
    """


def layout_cost(result: PackResult, parts: Sequence[Part]) -> CostoLayout:
    """Qué tan malo es un layout. Menor es mejor."""
    if not result.placements:
        return CostoLayout(0, 0.0, 0.0)

    placas_nuevas = sum(1 for hoja in result.sheets if not hoja.scrap)
    by_id = {p.id: p for p in parts}
    last_sheet = len(result.sheets) - 1
    top = 0.0
    material = 0.0

    for placement in result.placements:
        if placement.sheet != last_sheet:
            continue
        part = by_id[placement.part_id]
        _, _, _, y1 = transformed_bbox(part, placement.transform.angle_deg,
                                       placement.transform.mirror)
        top = max(top, placement.transform.dy + y1)
        material += part.area

    return CostoLayout(placas_nuevas, material, top)


def _restarts_for(config: NestConfig) -> int:
    """Cuántas pasadas golosas prevé la cartera para esta config, o el error de siempre.

    Antes era `EFFORT_RESTARTS[config.effort]`. Ahora cada variante de la
    cartera es una pasada, así que son `planned_variants`: la base más las
    tandas de `config.workers`. `initial_forecast` lo usa para la previsión
    de arranque, que cuenta consultas TOTALES -- sumadas entre procesos, como
    las cuenta el avance --; la estimación previa de tiempo usa
    `cartera.wall_forecast` (Tarea 7), que las divide por los núcleos.
    """
    from nesting.engine.cartera import EFFORT_BATCHES, planned_variants

    if config.effort not in EFFORT_BATCHES:
        raise UnknownEffortError(
            f"nivel de esfuerzo {config.effort!r} desconocido; "
            f"use uno de {', '.join(EFFORT_BATCHES)}"
        )
    return planned_variants(config.effort, config.workers)


def _usable_area(sheet: Sheet, margin: float) -> float:
    return max(0.0, sheet.width - 2 * margin) * max(0.0, sheet.height - 2 * margin)


def initial_forecast(
    parts: Sequence[Part], supply: SheetSupply, config: NestConfig
) -> int:
    """Cuántas consultas se prevé que cueste `pack(parts, supply, config, ...)`, antes de correrlo.

    Es la misma cuenta con la que `pack` arranca su previsión, y la que usa
    la estimación de tiempo previa (`nesting_app.corredor.estimar_segundos`).
    Las orientaciones se cuentan sobre la placa del Material: un recorte con
    la veta cruzada puede permitir otras, pero la cantidad es la misma.
    """
    passes = _restarts_for(config)
    if not parts:
        return 0
    sheets = estimate_sheets(
        sum(p.area for p in parts),
        [_usable_area(s, config.margin) for s in supply.scraps],
        _usable_area(supply.stock, config.margin),
    )
    return forecast_pack(
        len(parts), len(orientations(supply.stock, config)), sheets, passes
    )


def pack(
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    progreso: Callable[[Avance], bool] | None = None,
) -> PackResult:
    """Acomoda todo probando la cartera de variantes; ver `nesting.engine.cartera`.

    La firma es la de siempre. `progreso`, si se pasa, recibe un `Avance`
    por pieza intentada durante la base, cada `cartera.QUERY_REPORT_EVERY`
    consultas durante las tandas, y durante el tramo final (recuperación y
    compactación) con `compactando=True`: al entrar, por pieza intentada y
    al terminar. Devolver `False` en cualquiera de
    esas llamadas pide abandonar, y `pack` levanta `Cancelado`. No pasarlo
    deja el comportamiento exactamente como estaba.

    `progreso` puede llamarse desde un hilo de consulta (`QUERY_THREADS`) y
    no desde el hilo que llamó a `pack`: nunca dos llamadas a la vez (van
    bajo el cerrojo del contador de consultas), pero tiene que volver
    rápido, porque mientras corre las demás consultas esperan para avisar.

    El resultado trae sólo piezas reales: las compuestas se desarman antes
    de volver.
    """
    # Import tardío: la cartera importa este módulo.
    from nesting.engine.cartera import run_portfolio

    return run_portfolio(parts, supply, config, oracle_factory, progreso).result


def _perturb(order: Sequence[Part], rng: random.Random) -> list[Part]:
    """Swap a few pairs, keeping the large-parts-first shape mostly intact."""
    shuffled = list(order)
    swaps = max(1, len(shuffled) // 6)
    for _ in range(swaps):
        i = rng.randrange(len(shuffled))
        j = rng.randrange(len(shuffled))
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
    return shuffled


def _recuperar_de_la_ultima_placa(
    result: PackResult,
    parts: Sequence[Part],
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    material_name: str,
    aviso: Callable[[int, int], None] | None = None,
    prever: Callable[[int, int], None] | None = None,
) -> PackResult:
    """Reintentar en las placas anteriores lo que quedó en la última.

    `material_name` es obligatorio y sólo sirve para el mensaje de un
    `PartTooLargeError`: el `SheetSupply` de una sola placa que se arma acá
    abajo lo lleva. Es un `str` y no el `SheetSupply` entero porque es lo
    único que se usa de él, y no tiene default para que un llamador nuevo no
    pueda olvidárselo en silencio.

    `aviso` se reenvía tal cual a cada `_pack_once` interno -- misma forma
    que la de `_pack_once`, ver su docstring -- así que puede levantar para
    abandonar a mitad de un reintento. Sin esto el tramo más lento de todo
    `pack` (un `_pack_once` completo por placa anterior, ver "CUÁNTO CUESTA"
    abajo) corría sordo: ni la barra de progreso se movía ni el botón de
    cancelar hacía nada durante esos segundos.

    `prever`, si se pasa, se llama antes de cada intento con (consultas que
    se prevé que cueste lo que queda de la recuperación, pendientes que
    quedan en la última placa). Se vuelve a llamar en cada intento porque la
    cuenta cambia: un intento que recupera algo paga OTRO sobre la misma
    placa, y las pendientes que quedan son menos.

    Es literalmente lo que el usuario hizo a mano: sacar un disco de la
    placa 2 y meterlo en un hueco de la placa 1.

    POR QUÉ NO ALCANZA CON VOLVER A PREGUNTARLE A LA PLACA YA ARMADA

    La idea intuitiva -- reconstruir la placa anterior tal cual quedó y
    preguntarle de nuevo si la pieza entra -- NO PUEDE RECUPERAR NADA NUNCA,
    y conviene dejarlo escrito para que no vuelva a intentarse. `_pack_once`
    prueba CADA pieza pendiente contra CADA placa: la que terminó en la
    última ya fue rechazada por la placa 0 cuando le tocó su turno. El
    estado de esa placa al final de la pasada es un superconjunto del que la
    rechazó (colocar sólo agrega material, nunca lo saca), y los dos
    oráculos son monótonos en ese sentido: si no entraba con menos material,
    menos todavía entra con más. Medido, además de razonado: sobre 45
    escenarios al azar multiplaca (30 con `ShelfOracle`, 15 con
    `RasterOracle`) y sobre `NESTING 2.ai`, esa versión recuperó CERO
    piezas.

    Lo que sí rompe la avaricia es cambiar el ORDEN DE INSERCIÓN, que es de
    donde salió el problema: la placa se vuelve a armar desde cero con la
    pieza pendiente ADELANTE DE TODO, así que la placa se construye
    alrededor de ella en vez de ofrecerle las sobras. Ahí sí aparecen
    layouts que la pasada golosa no puede alcanzar.

    QUÉ SE ACEPTA

    Un reempaque de UNA placa se acepta sólo si en su primera placa siguen
    estando TODAS las piezas que ya tenía y entró al menos una pendiente.
    Esa regla hace que empeorar sea improbable -- las placas anteriores
    conservan sus piezas y la última sólo pierde alguna -- pero YA NO LO
    GARANTIZA. Antes sí: vaciar la última placa bajaba el conteo de placas,
    el primer campo de `CostoLayout`, y eso dominaba cualquier otra cosa.
    Con `placas_nuevas` ese argumento se cayó: vaciar un RECORTE no baja el
    conteo, así que el desempate pasa a `material_ultima`, y la "última
    placa" del layout recuperado puede ser otra, con más material arriba que
    la que se vació.

    Por eso el resultado se compara contra el de entrada al final y se
    devuelve el original si salió más caro: lo que era una garantía razonada
    ahora es una verificada.

    CUÁNTO CUESTA

    Cada intento es un `_pack_once` completo sobre una placa -- unos 10 s
    sobre `NESTING 2.ai` a 2 mm/px con 31 piezas, o sea del mismo orden que
    toda la corrida. Por eso el orden de los intentos importa y la cuenta
    está acotada: por cada placa anterior se paga un intento, y sólo se paga
    OTRO si el anterior recuperó algo de verdad. Las pendientes van de la
    más chica a la más grande (la chica entra en más lugares) y las que no
    encabezan el intento igual viajan al final del orden, así que pueden
    entrar de arrastre sin costar un intento propio. Medido sobre 15
    escenarios raster al azar: probar una pendiente por intento recupera 4
    piezas con 46 intentos; esta versión recupera 3 con 18. Sobre
    `NESTING 2.ai` recupera la misma pieza que la versión cara, con 1
    intento en vez de 5.
    """
    if result.sheets_used < 2:
        return result

    by_id = {p.id: p for p in parts}
    ultima = result.sheets_used - 1
    en_ultima = [p for p in result.placements if p.sheet == ultima]
    if not en_ultima:
        return result

    # Las placas anteriores, cada una con sus ubicaciones EN EL ORDEN EN QUE
    # SE COLOCARON: ese orden es el que produjo un layout que se sabe que
    # entra, así que es el que se reusa al reempacar. Reordenar por área
    # daría otro layout, que podría no entrar.
    por_placa: dict[int, list[Placement]] = {}
    for p in result.placements:
        if p.sheet != ultima:
            por_placa.setdefault(p.sheet, []).append(p)

    pendientes = sorted((by_id[p.part_id] for p in en_ultima), key=lambda q: q.area)
    recuperadas: set[int] = set()

    for placa in range(ultima):
        if not pendientes:
            break
        anteriores = por_placa.get(placa, [])
        en_placa = [by_id[p.part_id] for p in anteriores]
        while pendientes:
            if prever is not None:
                prever(
                    forecast_recovery(
                        [
                            (
                                len(por_placa.get(k, [])),
                                len(orientations(result.sheets[k], config)),
                            )
                            for k in range(placa, ultima)
                        ],
                        len(pendientes),
                    ),
                    len(pendientes),
                )
            orden = [pendientes[0], *en_placa, *pendientes[1:]]
            try:
                redone = _pack_once(
                    orden,
                    SheetSupply(
                        stock=result.sheets[placa],
                        material_name=material_name,
                    ),
                    config,
                    oracle_factory,
                    aviso,
                )
            except PartTooLargeError:
                # NO es un trabajo imposible, y por eso no se propaga. El
                # plan que se arma acá tiene esta placa -- que puede ser un
                # recorte chico -- como stock INFINITO y sin recortes. Si
                # `pendientes[0]` no entra ahí, el reempaque derrama a una
                # segunda placa idéntica donde ya no entra nada, y como
                # `scraps` está vacío la guarda de recorte vacío no saltea:
                # `_pack_once` levanta. La pieza sí entra en la placa que
                # tiene ahora; lo único que pasó es que este intento de
                # rescate no sirvió.
                #
                # Se trata igual que "no entró ninguna pendiente": se corta
                # el bucle, la placa se deja exactamente como estaba y se
                # sigue con la siguiente. Propagarlo abortaba el trabajo
                # entero, con un mensaje que encima describía el recorte y
                # lo llamaba la placa del material.
                break

            en_primera = [p for p in redone.placements if p.sheet == 0]
            ids_primera = {p.part_id for p in en_primera}
            ya_estaban = {p.id for p in en_placa}
            ganadas = ids_primera - ya_estaban
            if not ganadas or not ya_estaban <= ids_primera:
                # O no entró ninguna pendiente, o para meterlas se cayó
                # alguna de las que ya estaban: no es una mejora, y la placa
                # se deja exactamente como estaba.
                break

            por_placa[placa] = [
                Placement(p.part_id, placa, p.transform) for p in en_primera
            ]
            en_placa = [by_id[p.part_id] for p in en_primera]
            recuperadas |= ganadas
            pendientes = [q for q in pendientes if q.id not in ganadas]

    if not recuperadas:
        return result

    placements: list[Placement] = []
    for placa in range(ultima):
        placements.extend(por_placa.get(placa, []))
    quedan = [p for p in en_ultima if p.part_id not in recuperadas]
    placements.extend(quedan)

    # La misma cuenta que hace `_pack_once`: áreas por placa y UNA división
    # al final. Si acá se sumaran fracciones ya divididas, el total podría
    # no coincidir con el que informa una corrida normal, y el usuario vería
    # dos números distintos para el mismo layout.
    sheets_finales = result.sheets if quedan else result.sheets[:ultima]
    areas = [0.0] * len(sheets_finales)
    for p in placements:
        areas[p.sheet] += by_id[p.part_id].area
    area_total = sum(h.area for h in sheets_finales)

    recuperado = PackResult(
        placements=placements,
        sheets=sheets_finales,
        utilization=[
            area / hoja.area for area, hoja in zip(areas, sheets_finales)
        ],
        total_utilization=sum(areas) / area_total if area_total else 0.0,
        seconds=result.seconds,
    )

    # La versión anterior devolvía esto sin compararlo, apoyada en un
    # argumento escrito: si la última placa se vacía baja el conteo de
    # placas, que es el primer campo del costo, así que nunca empeora. Con
    # `placas_nuevas` el argumento dejó de valer -- vaciar un RECORTE no baja
    # ese conteo, y la "última placa" pasa a ser otra, con posiblemente más
    # material arriba. Comparar cuesta dos recorridos de las colocaciones y
    # convierte una garantía razonada en una verificada.
    if layout_cost(recuperado, parts) > layout_cost(result, parts):
        return result
    return recuperado


def _compact_last_sheet(
    result: PackResult,
    parts: Sequence[Part],
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    material_name: str,
    aviso: Callable[[int, int], None] | None = None,
) -> PackResult:
    """Re-pack the last sheet on its own, pulled harder towards the corner.

    `material_name` es obligatorio y sólo nombra el material en un eventual
    `PartTooLargeError`; ver el docstring de
    `_recuperar_de_la_ultima_placa`, que lo recibe igual y por lo mismo.

    `aviso` se reenvía tal cual al `_pack_once` interno. Antes esta pasada
    corría sorda: ni el contador de consultas se movía ni cancelar la
    alcanzaba. `Cancelado` NO es `PartTooLargeError`, así que el `except`
    de abajo no lo atrapa y sale limpio.
    """
    if result.sheets_used < 1:
        return result

    last = result.sheets_used - 1
    by_id = {p.id: p for p in parts}
    on_last = [by_id[p.part_id] for p in result.placements if p.sheet == last]
    if len(on_last) < 2:
        return result

    # Después de la guarda de arriba y no antes: un `PackResult` armado a
    # mano con `sheets` vacío tiene que salir por ese `return`, no reventar
    # con `IndexError` dos líneas antes.
    hoja = result.sheets[last]

    boosted = replace(
        config,
        weights=Weights(
            bottom_left=config.weights.bottom_left * COMPACTION_BOOST,
            contact=config.weights.contact,
        ),
    )
    order = sorted(on_last, key=lambda p: p.area, reverse=True)
    try:
        redone = _pack_once(
            order,
            SheetSupply(stock=hoja, material_name=material_name),
            boosted,
            oracle_factory,
            aviso,
        )
    except PartTooLargeError:
        # Defensa en profundidad: NO hay un caso reproducido que llegue acá.
        # Las piezas que se reempacan ya estaban en esta misma placa, así
        # que cada una entra sola en ella y el derrame que sí se dispara en
        # `_recuperar_de_la_ultima_placa` (ver el comentario de su `except`)
        # no debería aparecer. Pero la función ya contempla el derrame con
        # `if redone.sheets_used != 1: return result`, y una excepción
        # esquivaría esa salida prevista para abortar el trabajo entero: si
        # alguna vez pasa, que sea "esta compactación no sirvió".
        return result

    if redone.sheets_used != 1:
        return result
    # Compara `.alto_ultima`, no el `CostoLayout` entero: la compactación
    # mueve las mismas piezas dentro de la misma placa, así que
    # `material_ultima` no cambia y comparar por ahí no desempataría nada.
    # El alto es lo único que esta pasada puede mejorar.
    if layout_cost(redone, parts).alto_ultima >= layout_cost(result, parts).alto_ultima:
        return result

    kept = [p for p in result.placements if p.sheet != last]
    moved = [Placement(p.part_id, last, p.transform) for p in redone.placements]

    result.placements = kept + moved
    result.utilization[last] = sum(p.area for p in on_last) / hoja.area
    return result
