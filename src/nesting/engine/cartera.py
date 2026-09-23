"""La cartera: varias maneras de acomodar lo mismo, y quedarse con la mejor.

`pack()` delega acá. Una VARIANTE es una lista de piezas -- sueltas y
compuestas (pares encastrados, ver `pares.py`) --, un orden de inserción y,
opcionalmente, una perturbación de orientaciones. Cada una se acomoda con la
misma pasada golosa de siempre (`_pack_once`), y gana la de menor
`CostoLayout`, con desempate por índice de variante: el resultado no depende
de en qué orden terminan.

La base es la pasada de hoy y se evalúa primero, sola. Si ya alcanza la cota
por área no se busca nada más. Si no, se evalúan tandas de `config.workers`
variantes, en el orden fijo de la spec (4.1). Recuperación y compactación
corren una sola vez, sobre la ganadora y todavía con compuestas, y recién
después se desarma.

Spec: docs/superpowers/specs/2026-09-22-pares-y-cartera-design.es.md, sección 4.
"""

import heapq
import itertools
import math
import multiprocessing
import pickle
import queue
import random
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, replace

from nesting.engine import estantes, pares, prevision
from nesting.engine.iguales import Clase, find_classes
from nesting.engine.oracle import NestConfig, Oracle
from nesting.engine.packer import (
    Avance,
    Cancelado,
    CostoLayout,
    PackResult,
    PartTooLargeError,
    UnknownEffortError,
    _compact_last_sheet,
    _pack_once,
    _perturb,
    _recuperar_de_la_ultima_placa,
    _usable_area,
    initial_forecast,
    layout_cost,
    orientations,
)
from nesting.engine.raster.masks import MaskCache
from nesting.model.part import Part
from nesting.model.sheet import SheetSupply

EFFORT_BATCHES: dict[str, int] = {"rapido": 0, "normal": 1, "lento": 3}
"""Cuántas tandas de `NestConfig.workers` variantes se prueban después de la base.

Reemplaza a `EFFORT_RESTARTS` (1, 3 y 12 pasadas). Los reintentos de antes
sólo permutaban el orden de inserción, y seis copias idénticas permutadas
dan el mismo acomodo: sobre la banqueta alta esos reintentos no exploraban
nada (spec 1.1). Una tanda son `batch_size(N)` variantes: `N`, pero nunca
menos de `MIN_BATCH`. Con 12 núcleos o más, normal prueba `N` variantes en
el tiempo de una pasada; con menos, las mismas 12 en varias vueltas.

`lento <= normal <= rapido` sigue valiendo por construcción: con el mismo
`N` y la misma semilla, las variantes de `rapido` son un prefijo de las de
`normal`, y las de `normal` un prefijo de las de `lento` (ver
`VariantSource.batch`); y la ganadora sólo se reemplaza por una
estrictamente mejor. Con distinto `N` la garantía no aplica: más núcleos
exploran más.

HISTORIA: LA TABLA DE REINTENTOS QUE ESTO REEMPLAZA.

How many insertion orders each effort level tries.

Los tres números siguen siendo los de la Task 19
(`.superpowers/sdd/task-19-report.md`), que los midió contra reloj: una
pasada golosa sobre `bench/files/muestra.dxf` (mdf18, sep/margen por
omisión, 1 mm/px) tardaba ~46s a --copias 4 y ~81s a --copias 6, el tiempo
de `pack()` escala lineal con los reintentos, `normal = 4` ya cruzaba el
objetivo de 5 minutos (317s a --copias 6) y `lento = 12` mostraba una caída
monótona del costo de compactación al crecer los reintentos. Nada de eso
cambió de signo, y por eso la tabla no se tocó.

QUÉ SÍ CAMBIÓ, Y POR QUÉ ESTA NOTA SE REESCRIBIÓ. La versión anterior
cerraba con un dato que hoy engaña: "normal empata con rapido en 5 de 7
escenarios". Ese empate se midió con la función de costo vieja
`(placas, alto de la última)`, que NO PODÍA VER la diferencia entre los
layouts que estaba eligiendo -- peor, prefería el equivocado. Sobre
`NESTING 2.ai` (mdf15, sep 10, borde 10, 2.0 mm/px), medido en la Tarea 6
con `contact = 1.0` -- el peso vigente mientras se corrió este barrido,
antes de que la misma Tarea 6 lo recalibrara a 4.0 (ver `Weights.contact`
en `oracle.py`):

| nivel  | reparto | material última | alto última | seg   |
|--------|---------|-----------------|-------------|-------|
| rapido | 32 / 4  | 0.1432 m²       | 235 mm      | 37.7  |
| normal | 33 / 3  | 0.1106 m²       | 308 mm      | 48.3  |
| lento  | 35 / 1  | 0.1061 m²       | 491 mm      | 136.2 |

Los reintentos mejoran de verdad y de forma monótona -- de 4 piezas varadas
a 1 -- pero el ALTO de la última placa CRECE con cada mejora. Con el
desempate viejo, `normal` y `lento` encontraban esos layouts y después los
tiraban, porque 308 mm y 491 mm puntúan peor que 235 mm. Parte del "empate"
que esta nota reportaba era eso: el esfuerzo extra sí encontraba algo, y el
costo lo descartaba. Con `CostoLayout` (Tarea 1) la mejora se registra.

CUÁNDO SIGUE SIN COMPRAR NADA. Sobre `muestra.dxf` a --copias 8, los tres
niveles dieron exactamente el mismo layout (50/46, 2.1206 m²) por 70.1s,
132.1s y 401.9s. La regla vieja se sostiene: el esfuerzo extra rinde cerca
de un salto de placa -- que es donde está el archivo de referencia, con 1 a
4 piezas varadas en la segunda placa -- y no rinde lejos de uno. Lo que
cambió es que ahora, cuando rinde, se nota.

LO QUE ESTA TABLA NO RESPONDE. Todo lo de arriba -- la tabla de la Tarea 6
y la de la Task 19 con la que se compara -- se midió con `contact = 1.0`.
Esta misma Tarea 6 deja de usar ese valor: el default pasa a 4.0. El
barrido de esfuerzo NO se volvió a correr con contact = 4.0, y hay una
razón concreta para sospechar que el resultado podría no ser el mismo. En
`tests/engine/test_effort.py::test_different_seeds_can_give_different_results`
(líneas 157-163 de ese archivo), subir contacto de 1.0 a 4.0 sobre las
mismas 43 piezas colapsó 3 layouts distintos entre 4 semillas a UNO SOLO:
ninguna perturbación del orden de inserción mejoraba al orden por área, así
que `best` nunca se reemplazaba. Eso es exactamente lo que los reintentos
de `normal` y `lento` son -- perturbaciones del orden de inserción de las
que se conserva la mejor -- así que si `contact = 4.0` aplana el espacio de
búsqueda de la misma manera sobre archivos reales, los reintentos podrían
estar comprando menos de lo que dice la tabla de arriba. No hay medición en
ningún sentido: ni que lo confirme ni que lo descarte. La tabla y la
conclusión "nada cambió de signo" quedan tal cual porque no hay evidencia
para moverlas, no porque se haya verificado que siguen valiendo a
contact = 4.0.

EL PRESUPUESTO DE 5 MINUTOS, HONESTAMENTE. A 2.0 mm/px (el default entre la
Task 24 y los recortes; ver el último párrafo) `normal` salía mucho más
barato que lo medido en la Task 19: 48.3s sobre el archivo de referencia
(36 piezas) y 132.1s sobre `muestra.dxf` a --copias 8 (96 piezas). Pero el
objetivo no es universal: una sola pasada sobre `banqueta final raulo.ai`
a --copias 5 (200 piezas) ya tarda 450.6s,
o sea que `normal` ahí se va muy por encima de los 5 minutos. El objetivo
vale para trabajos del tamaño contra el que se calibró, no para cualquier
carga.

TODO LO DE ARRIBA SE MIDIÓ A 2.0 mm/px, QUE YA NO ES EL VALOR POR OMISIÓN.
Desde los recortes, `NestParams.resolucion` arranca en 1.0: cuatro veces los
píxeles del raster, así que cuatro veces el trabajo de rasterizar y de
buscar. Ninguno de los números de esta nota se volvió a medir a 1.0, y no
hay razón para creer que escalen de forma simple. Valen como comparación
entre niveles de esfuerzo a una misma resolución, no como pronóstico de
cuánto va a tardar una corrida con los valores de hoy.

`pack()` garantiza `lento <= normal <= rapido` por construcción (ver el
superconjunto de reintentos más abajo), nunca por suerte de la semilla.
"""

QUERY_REPORT_EVERY = 25
"""Cada cuántas consultas una variante informa su cuenta.

Informar cada consulta haría que el aviso cueste más que la consulta en las
placas vacías; cada 25, en la pasada más rápida medida, es un aviso cada
pocas décimas de segundo.
"""

POLL_SECONDS = 0.2
"""Cada cuánto el proceso principal junta los avisos de los procesos y
avisa. Es también cuánto puede tardar en notarse un "cancelar"."""

ORIENTATION_RANKS = 3
"""Entre cuántas orientaciones de mejor puntaje elige la perturbación de `lento`."""

ORIENTATION_TOP_SHARE = 0.1
"""Qué parte de las piezas, las de más área, se perturban en orientación."""

MIN_BATCH = 12
"""Cuántas variantes tiene, como mínimo, cada tanda, aunque haya menos núcleos.

Decisión del usuario (2026-09-22): el resultado no puede depender de la
máquina. Con tandas de `N` variantes, lo que se prueba dependía de cuántos
núcleos había: cuando se decidió esto, la combinación que ganaba en la
banqueta alta salía octava y una computadora de 4 núcleos no la encontraba
ni en lento. Con el orden por placas previstas (`_combinations`) hoy sale
tercera, pero la regla es la misma: con este mínimo, toda máquina de hasta
12 núcleos prueba exactamente las mismas variantes y da el mismo resultado;
una de 4 tarda unas tres veces más en normal, y el tiempo estimado lo avisa
antes de arrancar. Con más de 12 núcleos la tanda
crece a `N`: más núcleos exploran más, en el mismo tiempo.

Los tests lo bajan a 1 con el fixture `_tanda_minima_de_uno` de
`tests/conftest.py`, para que las cuentas chicas de siempre sigan valiendo;
los que prueban el mínimo de verdad llevan `@pytest.mark.minimo_real`.
"""

PREDICTION_POOL_FACTOR = 8
PREDICTION_POOL_MIN = 400
"""De cuántas combinaciones, las más baratas por área, se elige la tanda.

`_combinations` saca `max(PREDICTION_POOL_FACTOR * pedidas, PREDICTION_POOL_MIN)`
por costo, les calcula las placas previstas (`estantes.predicted_sheets`) y
las reordena por `(placas previstas, costo, tupla)`. En la banqueta alta la
primera combinación que entra en una placa quedaba fuera de las doce más
baratas:
el colchón tiene que alcanzar para que las que entran aparezcan aunque
haya muchas imposibles más baratas.
"""


def batch_size(workers: int) -> int:
    """Cuántas variantes tiene cada tanda: `N`, pero nunca menos de `MIN_BATCH`."""
    return max(1, workers, MIN_BATCH)


def cota_minima(parts: Sequence[Part], supply: SheetSupply, margin: float) -> int | None:
    """⌈área neta de las piezas / área útil de la placa del Material⌉.

    Con recortes no se informa: con placas de distinto tamaño la cuenta
    honesta no es ésta. Que el área permita menos placas no quiere decir que
    entren -- la banqueta con veta tiene cota 1 y el mínimo real es 2 --, así
    que sólo se usa en un sentido: si un layout la iguala, no hay nada que
    ganar en placas.
    """
    if supply.scraps or not parts:
        return None
    usable = (supply.stock.width - 2 * margin) * (supply.stock.height - 2 * margin)
    if usable <= 0:
        return None
    # El 1e-9 es para que un área que da justo k placas no suba a k+1 por
    # el ruido de la suma.
    return max(1, math.ceil(sum(p.area for p in parts) / usable - 1e-9))


def planned_variants(effort: str, workers: int) -> int:
    """Cuántas variantes prevé la cartera, base incluida, si no corta por la cota."""
    return 1 + EFFORT_BATCHES[effort] * batch_size(workers)


def wall_passes(effort: str, workers: int) -> float:
    """Cuántas pasadas golosas "de reloj" cuesta la cartera, para el tiempo estimado previo.

    La base es una pasada. Cada tanda son `workers` variantes repartidas en
    `workers` núcleos: la previsión de consultas se multiplica por las
    variantes de la tanda y se divide por `N` (spec de pares y cartera, 6).
    Es una cota de arriba: si la base iguala la cota por área, las tandas
    no corren.
    """
    n = max(1, workers)
    # Las variantes de una tanda se reparten en `n` núcleos: son
    # ⌈tanda / n⌉ vueltas, cada una del tiempo de una pasada.
    return 1.0 + EFFORT_BATCHES[effort] * math.ceil(batch_size(workers) / n)


def wall_forecast(parts: Sequence[Part], supply: SheetSupply, config: NestConfig) -> float:
    """Las consultas "de reloj" de la cartera: lo que tarda en un núcleo, contando el paralelo.

    Es la previsión de arranque del plan 2 para UNA pasada (con recuperación
    y compactación), más una pasada golosa por cada tanda: cada tanda son
    `N` variantes en `N` núcleos. `initial_forecast` cuenta consultas
    TOTALES, sumadas entre procesos, y sirve para la barra; ésta sirve para
    multiplicarla por los segundos que tarda una consulta en UN núcleo.
    """
    if not parts:
        return 0.0
    una = initial_forecast(parts, supply, replace(config, effort="rapido"))
    sheets = prevision.estimate_sheets(
        sum(p.area for p in parts),
        [_usable_area(s, config.margin) for s in supply.scraps],
        _usable_area(supply.stock, config.margin),
    )
    pasada = prevision.forecast_greedy_pass(
        len(parts), len(orientations(supply.stock, config)), sheets
    )
    return una + (wall_passes(config.effort, config.workers) - 1.0) * pasada


def smallest_combinations(
    type_areas: Sequence[float],
    members: int,
    loose_area: float,
    include_empty: bool,
) -> Iterator[tuple[float, tuple[int, ...]]]:
    """Cada multiconjunto de tipos de par para una clase, de menor a mayor costo.

    Un multiconjunto es una tupla no decreciente de índices de tipo, uno por
    par: `(0, 0, 1)` son dos pares del tipo 0 y uno del tipo 1. Su costo es
    la suma de las cajas de sus pares más la caja de cada miembro que queda
    suelto. Los empates se ordenan por la tupla, que es "por índice de tipo".

    Es perezoso a propósito: con veinte copias y diez tipos hay millones de
    multiconjuntos, y la cartera nunca necesita más que unas decenas. Como
    `type_areas` viene de menor a mayor (`find_pair_types` lo garantiza),
    subir un índice nunca baja el costo, y un montículo alcanza para
    sacarlos en orden sin generarlos todos.
    """
    max_pairs = members // 2 if type_areas else 0

    def cost(combo: tuple[int, ...]) -> float:
        return sum(type_areas[i] for i in combo) + (members - 2 * len(combo)) * loose_area

    heap: list[tuple[float, tuple[int, ...]]] = []
    seen: set[tuple[int, ...]] = set()
    for pairs in range(0 if include_empty else 1, max_pairs + 1):
        combo = (0,) * pairs
        heapq.heappush(heap, (cost(combo), combo))
        seen.add(combo)

    while heap:
        value, combo = heapq.heappop(heap)
        yield value, combo
        for i in range(len(combo)):
            bumped = combo[i] + 1
            if bumped < len(type_areas) and (i == len(combo) - 1 or bumped <= combo[i + 1]):
                following = combo[:i] + (bumped,) + combo[i + 1:]
                if following not in seen:
                    seen.add(following)
                    heapq.heappush(heap, (cost(following), following))


@dataclass(frozen=True)
class Variant:
    index: int
    kind: str
    """Uno de "base", "pares", "orden" u "orientacion"."""

    order: tuple[Part, ...]
    """Las piezas a acomodar, sueltas y compuestas, en orden de inserción."""

    composites: tuple[pares.Composite, ...] = ()
    pair_types: tuple[tuple[int, int], ...] = ()
    """(clase, tipo) de cada par, en el orden de `composites`."""

    orientation_ranks: tuple[tuple[int, int], ...] = ()
    """(id de pieza, rango) para la perturbación de orientaciones."""


@dataclass
class Outcome:
    index: int
    packed: PackResult
    """El acomodo tal como salió, todavía con compuestas."""

    cost: CostoLayout
    """El costo del acomodo YA DESARMADO, sobre las piezas reales: el área
    de una compuesta incluye su puente, que no es material de nadie."""

    queries: int


@dataclass
class PortfolioResult:
    result: PackResult
    """El ganador, con recuperación y compactación, desarmado: sólo piezas reales."""

    winner: Variant
    evaluated: list[Variant]
    lower_bound: int | None


@dataclass(frozen=True)
class _PairPlan:
    classes: tuple[Clase, ...]
    types: tuple[tuple[pares.PairType, ...], ...]


def _box_area(part: Part) -> float:
    x0, y0, x1, y1 = part.bbox
    return (x1 - x0) * (y1 - y0)


def _box_size(part: Part) -> tuple[float, float]:
    x0, y0, x1, y1 = part.bbox
    return (x1 - x0, y1 - y0)


def _build_pair_plan(
    parts: Sequence[Part], supply: SheetSupply, config: NestConfig, cache: MaskCache
) -> _PairPlan:
    stock = supply.stock
    usable_w = stock.width - 2 * config.margin
    usable_h = stock.height - 2 * config.margin
    if usable_w <= 0 or usable_h <= 0:
        return _PairPlan((), ())
    choices = orientations(stock, config)
    grain = stock.grain_tolerance < 90.0
    classes = pares.pairable_classes(find_classes(parts, choices), usable_w * usable_h, grain)
    how_many = pares.TIPOS_POR_CLASE[config.effort]
    kept_classes: list[Clase] = []
    kept_types: list[tuple[pares.PairType, ...]] = []
    for clase in classes:
        types = pares.find_pair_types(
            clase.representative, pares.b_orientations(choices, grain), choices,
            config, (usable_w, usable_h), how_many, cache,
        )
        if types:
            kept_classes.append(clase)
            kept_types.append(tuple(types))
    return _PairPlan(tuple(kept_classes), tuple(kept_types))


class VariantSource:
    """Las variantes, en el orden fijo de la spec (4.1).

    Depende sólo de las piezas, la config y la semilla -- y, para la tercera
    tanda de `lento`, de cuál fue la mejor hasta ahí, que a su vez depende
    sólo de lo mismo. Nunca del orden en que terminan los procesos.
    """

    def __init__(self, parts: Sequence[Part], supply: SheetSupply, config: NestConfig) -> None:
        self._parts = list(parts)
        self._supply = supply
        self._config = config
        self._by_area = sorted(parts, key=lambda p: p.area, reverse=True)
        self._rng = random.Random(config.seed)
        self._plan: _PairPlan | None = None
        # (área útil, si se puede girar 90°, cajas de las piezas no emparejadas)
        self._shelf_setup: (
            tuple[tuple[float, float], bool, tuple[tuple[float, float], ...]] | None
        ) = None
        self._used: set[tuple[tuple[int, ...], ...]] = set()
        self._next_index = 1
        self._next_id = max((p.id for p in parts), default=-1) + 1

    def base(self) -> Variant:
        return Variant(0, "base", tuple(self._by_area))

    def batch(self, number: int, size: int, best: Variant) -> list[Variant]:
        """La tanda `number` (1, 2 o 3), de `size` variantes.

        1 (normal y lento): combinaciones de pares con los primeros
          `TIPOS_POR_CLASE["normal"]` tipos, y si no alcanzan, perturbaciones
          de orden.
        2 (lento): combinaciones con los `TIPOS_POR_CLASE["lento"]` tipos que
          todavía no se probaron, y si no alcanzan, perturbaciones de orden.
        3 (lento): perturbaciones de orientación de `best`, la mejor hasta ahí
          -- la base si ningún par ayudó, la mejor combinación si alguna sí.

        La 1 es idéntica en normal y en lento: el mismo límite de tipos, los
        mismos tipos (el orden de `find_pair_types` es un contrato) y el mismo
        generador consumido igual. Eso hace a normal prefijo de lento.
        """
        if number >= 3:
            return [self._orientation_variant(best) for _ in range(size)]
        limit = pares.TIPOS_POR_CLASE["normal" if number == 1 else "lento"]
        variants = [self._pair_variant(c) for c in self._combinations(limit, size)]
        while len(variants) < size:
            variants.append(self._new("orden", tuple(_perturb(self._by_area, self._rng))))
        return variants

    def _new(self, kind: str, order: tuple[Part, ...], **rest) -> Variant:
        variant = Variant(self._next_index, kind, order, **rest)
        self._next_index += 1
        return variant

    def _pair_plan(self) -> _PairPlan:
        if self._plan is None:
            self._plan = _build_pair_plan(self._parts, self._supply, self._config, MaskCache())
        return self._plan

    def _combinations(self, type_limit: int, size: int) -> list[tuple[tuple[int, ...], ...]]:
        """Las `size` combinaciones siguientes que no se usaron, primero las que entran.

        Se toman las más baratas por área de cajas (`PREDICTION_POOL_FACTOR`),
        y se ordenan de forma estable por `(placas previstas, costo, tupla)`
        (spec 4.1, punto 2): de nada sirve probar la combinación de cajas más
        chicas si ni como rectángulos entra en las placas que se buscan.
        """
        plan = self._pair_plan()
        if not plan.classes:
            return []
        want = size + len(self._used)
        pool = max(want * PREDICTION_POOL_FACTOR, PREDICTION_POOL_MIN)
        streams = [
            (clase, [t.box_area for t in types[:type_limit]])
            for clase, types in zip(plan.classes, plan.types)
        ]
        if len(streams) == 1:
            clase, areas = streams[0]
            costed = [
                (cost, (combo,))
                for cost, combo in itertools.islice(
                    smallest_combinations(areas, len(clase.members),
                                          _box_area(clase.representative), False),
                    pool,
                )
            ]
        else:
            per_class = [
                list(itertools.islice(
                    smallest_combinations(areas, len(clase.members),
                                          _box_area(clase.representative), True),
                    pool + 1,
                ))
                for clase, areas in streams
            ]
            costed = sorted(
                (cost_a + cost_b, (combo_a, combo_b))
                for cost_a, combo_a in per_class[0]
                for cost_b, combo_b in per_class[1]
                if combo_a or combo_b
            )[:pool]
        ranked = sorted(
            costed, key=lambda item: (self.predicted_sheets(item[1]), item[0], item[1])
        )
        fresh = [combo for _, combo in ranked if combo not in self._used][:size]
        self._used.update(fresh)
        return fresh

    def predicted_sheets(self, combo: tuple[tuple[int, ...], ...]) -> int:
        """Las placas de un armado por estantes de las cajas grandes de `combo`.

        Las cajas son la de cada par (`PairType.width` x `height`), la de
        cada miembro suelto de cada clase emparejable (la caja de la
        representante), y la de toda otra pieza con al menos
        `pares.MIN_SHEET_SHARE` del área útil. Las piezas chicas no cuentan:
        van en los huecos. Es para ordenar, no un acomodo (ver `estantes`).
        """
        plan = self._pair_plan()
        if self._shelf_setup is None:
            stock, config = self._supply.stock, self._config
            usable = (stock.width - 2 * config.margin, stock.height - 2 * config.margin)
            can_turn = any(abs(angle % 180.0 - 90.0) < 1e-9
                           for angle, _ in orientations(stock, config))
            paired = {m.part_id for clase in plan.classes for m in clase.members}
            others = tuple(
                _box_size(p) for p in self._parts
                if p.id not in paired
                and p.area >= pares.MIN_SHEET_SHARE * usable[0] * usable[1]
            )
            self._shelf_setup = (usable, can_turn, others)
        usable, can_turn, others = self._shelf_setup
        boxes = list(others)
        for clase, types, choice in zip(plan.classes, plan.types, combo):
            boxes.extend((types[t].width, types[t].height) for t in choice)
            loose = len(clase.members) - 2 * len(choice)
            boxes.extend([_box_size(clase.representative)] * loose)
        return estantes.predicted_sheets(boxes, usable, self._config.sep, can_turn)

    def _pair_variant(self, combo: tuple[tuple[int, ...], ...]) -> Variant:
        plan = self._pair_plan()
        composites: list[pares.Composite] = []
        pair_types: list[tuple[int, int]] = []
        paired: set[int] = set()
        for class_index, (clase, choice) in enumerate(zip(plan.classes, combo)):
            for k, type_index in enumerate(choice):
                first, second = clase.members[2 * k], clase.members[2 * k + 1]
                composites.append(pares.make_composite(
                    self._next_id, plan.types[class_index][type_index], first, second,
                ))
                self._next_id += 1
                pair_types.append((class_index, type_index))
                paired.update((first.part_id, second.part_id))
        loose = [p for p in self._by_area if p.id not in paired]
        order = sorted([c.part for c in composites] + loose, key=lambda p: p.area, reverse=True)
        return self._new("pares", tuple(order), composites=tuple(composites),
                         pair_types=tuple(pair_types))

    def _orientation_variant(self, best: Variant) -> Variant:
        top = max(1, math.ceil(len(best.order) * ORIENTATION_TOP_SHARE))
        largest = sorted(best.order, key=lambda p: p.area, reverse=True)[:top]
        ranks = tuple((p.id, self._rng.randrange(ORIENTATION_RANKS)) for p in largest)
        return self._new("orientacion", best.order, composites=best.composites,
                         pair_types=best.pair_types, orientation_ranks=ranks)


# --- vigilar una variante mientras corre -------------------------------------

@dataclass
class _Watch:
    """Lo que una variante necesita saber de afuera mientras corre."""

    cancelled: Callable[[], bool]
    best_new_sheets: Callable[[], int]
    """Placas nuevas de la mejor variante terminada."""

    on_queries: Callable[[int], None]
    """Recibe el total de consultas de ESTA variante hasta ahora."""

    report_every: int = QUERY_REPORT_EVERY
    """Cada cuántas consultas se llama a `on_queries`. La base y el tramo
    final usan 1: ahí `on_queries` sólo anota, no avisa, y el aviso sale por
    el `aviso` de siempre, con la cuenta al día."""


def _never_beaten() -> int:
    return sys.maxsize


class _Beaten(Exception):
    """La variante ya abrió más placas que la mejor terminada: no puede ganar."""


class _QueryCounter:
    def __init__(self, watch: _Watch) -> None:
        self.total = 0
        self._reported = 0
        self._watch = watch

    def add(self) -> None:
        self.total += 1
        if self.total - self._reported >= self._watch.report_every:
            self.flush()

    def flush(self) -> None:
        if self.total != self._reported:
            self._reported = self.total
            self._watch.on_queries(self.total)


class _WatchedOracle:
    """Un oráculo que cuenta cada consulta y mira si hay que cancelar.

    La consulta es la unidad de trabajo del tiempo estimado (spec de tiempo
    estimado, 2): contarla acá, envolviendo al oráculo, la hace independiente
    de qué fase la pidió -- base, tanda, recuperación o compactación -- y de
    en qué proceso corre.
    """

    def __init__(self, inner: Oracle, counter: _QueryCounter, watch: _Watch) -> None:
        self._inner = inner
        self._counter = counter
        self._watch = watch

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._inner.reset(sheet_w, sheet_h, config)

    def best_placement(self, part: Part, angle: float, mirror: bool):
        if self._watch.cancelled():
            raise Cancelado("el trabajo se canceló")
        self._counter.add()
        return self._inner.best_placement(part, angle, mirror)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        self._inner.place(part, angle, mirror, x, y)


class _WatchedFactory:
    """La fábrica de siempre, más el corte de lo que ya perdió.

    `_pack_once` pide un oráculo por placa, así que contar los pedidos es
    contar placas abiertas. Si una variante abre más placas nuevas que la
    mejor terminada, no puede ganar -- `placas_nuevas` manda sobre todo lo
    demás -- y se abandona. Las placas nuevas abiertas son al menos las
    pedidas menos los recortes del plan, y la cuenta usa esa cota: nunca
    corta una variante que todavía podría ganar.
    """

    def __init__(self, inner: Callable[[], Oracle], counter: _QueryCounter,
                 watch: _Watch, scraps: int) -> None:
        self._inner = inner
        self._counter = counter
        self._watch = watch
        self._scraps = scraps
        self.opened = 0

    def __call__(self) -> Oracle:
        self.opened += 1
        if self.opened - self._scraps > self._watch.best_new_sheets():
            raise _Beaten()
        return _WatchedOracle(self._inner(), self._counter, self._watch)


def evaluate(
    variant: Variant,
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    factory: Callable[[], Oracle],
    watch: _Watch,
    aviso: Callable[[int, int], None] | None = None,
) -> Outcome | None:
    """Acomoda una variante. `None` si se cortó o si una compuesta no entra.

    La base no se corta nunca (se la llama con `_never_beaten`) y su
    `PartTooLargeError` sí se propaga: es el error de siempre, "esta pieza no
    entra en una placa vacía". En las demás variantes, una compuesta que el
    oráculo no logra ubicar ni en una placa vacía descarta la variante, no
    el trabajo: las piezas sueltas sí entran, como lo probó la base.
    """
    counter = _QueryCounter(watch)
    watched = _WatchedFactory(factory, counter, watch, len(supply.scraps))
    try:
        packed = _pack_once(
            list(variant.order), supply, config, watched, aviso,
            orientation_ranks=dict(variant.orientation_ranks) or None,
        )
    except _Beaten:
        counter.flush()
        return None
    except PartTooLargeError:
        if variant.kind == "base":
            raise
        counter.flush()
        return None
    counter.flush()
    real = pares.disassemble(packed, variant.composites, parts)
    return Outcome(variant.index, packed, layout_cost(real, parts), counter.total)


# --- avance -----------------------------------------------------------------

class _Progress:
    """Suma las consultas de todo `run_portfolio` y arma cada `Avance`.

    Tres fases: la base (el texto de siempre: piezas ubicadas y placa en
    curso), la cartera (variantes terminadas de tantas, y la placa mínima
    hasta ahora) y el tramo final (recuperación y compactación, que la
    pantalla muestra como "compactando").

    Las consultas se suman por variante y no se reinician nunca, así que
    `consultas_hechas` no retrocede; `consultas_previstas` se corrige a
    medida que se sabe más y nunca queda por debajo de las hechas.
    """

    def __init__(self, progreso: Callable[[Avance], bool] | None,
                 totales: int, planned: int, initial_queries: int) -> None:
        self._progreso = progreso
        self._totales = totales
        self._planned = planned
        self._queries: dict[object, int] = {}
        # La previsión de arranque del plan 2 (`initial_forecast`), que con
        # `_restarts_for` apuntando a `planned_variants` cuenta una pasada
        # por variante prevista, más la recuperación y la compactación.
        self._planned_queries = initial_queries
        self._phase = "base"
        self._ubicadas = 0
        self._placa = 1
        self._done = 0
        self._best_sheets = 0
        self.cancel_requested = False

    @property
    def queries(self) -> int:
        return sum(self._queries.values())

    def record(self, slot: object, total: int) -> None:
        # `max` y no asignación: en paralelo (Tarea 6) el total de una
        # variante llega dos veces, por la cola y con su resultado, y un
        # mensaje viejo de la cola puede llegar después del definitivo.
        self._queries[slot] = max(self._queries.get(slot, 0), total)

    @property
    def listening(self) -> bool:
        return self._progreso is not None

    def watch(self, slot: object, best_new_sheets: Callable[[], int],
              emit: bool = True) -> _Watch:
        """Lo que mira una variante mientras corre.

        Con `emit=True` (las tandas) cada `QUERY_REPORT_EVERY` consultas se
        anotan y se avisa. Con `emit=False` (la base y el tramo final) cada
        consulta se anota y NO se avisa: ahí avisa el `aviso` de siempre,
        uno por pieza intentada, que es lo que el plan 2 fijó y sus tests
        cuentan (1 al entrar + uno por pieza + 1 al terminar, en la
        compactación de una sola placa).
        """
        def on_queries(total: int) -> None:
            self.record(slot, total)
            if emit:
                self.emit()

        return _Watch(
            cancelled=lambda: self.cancel_requested,
            best_new_sheets=best_new_sheets,
            on_queries=on_queries,
            report_every=QUERY_REPORT_EVERY if emit else 1,
        )

    def placed(self, ubicadas: int, placa: int) -> None:
        """El `aviso` de `_pack_once` para la base."""
        self._ubicadas, self._placa = ubicadas, placa
        self.emit()

    def base_done(self, outcome: Outcome) -> None:
        self._phase = "cartera"
        self._done = 1
        self._best_sheets = outcome.packed.sheets_used
        # Ya se sabe cuánto costó una pasada de verdad: las que faltan se
        # prevén iguales, más una para el tramo final.
        self._planned_queries = outcome.queries * (self._planned + 1)

    def variant_done(self, outcome: Outcome | None) -> None:
        self._done += 1
        if outcome is not None:
            self._best_sheets = min(self._best_sheets, outcome.packed.sheets_used)
        self.emit()

    def final(self) -> None:
        self._phase = "final"
        self._planned_queries = self.queries + max(self._queries.get("base", 0), 1)
        self.emit()

    def finish(self) -> None:
        """El último aviso: todo lo consultado ya está contado.

        Sin esto, un tramo final más barato que la base (la previsión de
        `final` cuenta una pasada entera) dejaría el último `Avance` con
        previstas de más, y quien estime el tiempo vería trabajo pendiente
        en un `pack` que ya terminó. `Avance.consultas_previstas` promete
        que en el último aviso son iguales a las hechas.
        """
        self._planned_queries = self.queries
        self.emit()

    def emit(self) -> None:
        if self._progreso is None:
            return
        hechas = self.queries
        comunes = dict(
            intentos=self._planned,
            totales=self._totales,
            consultas_hechas=hechas,
            consultas_previstas=max(self._planned_queries, hechas),
        )
        if self._phase == "base":
            avance = Avance(intento=1, ubicadas=self._ubicadas, placa=self._placa, **comunes)
        elif self._phase == "cartera":
            avance = Avance(
                intento=min(self._done + 1, self._planned), ubicadas=0,
                placa=self._best_sheets, combinaciones=self._planned,
                combinaciones_hechas=self._done, placa_minima=self._best_sheets,
                **comunes,
            )
        else:
            avance = Avance(intento=self._planned, ubicadas=self._totales, placa=0,
                            compactando=True, **comunes)
        if not self._progreso(avance):
            self.cancel_requested = True
            raise Cancelado("el trabajo se canceló")


# --- evaluar tandas -----------------------------------------------------------

_worker: dict = {}
"""El estado de un proceso del pool: lo llena `_init_worker` una vez."""


def _init_worker(factory, cancel, best, reports) -> None:
    """Corre una vez en cada proceso nuevo del pool.

    La fábrica, el evento de cancelar, el mejor `placas_nuevas` y la cola de
    avisos llegan acá y no con cada variante: los objetos de sincronización
    de `multiprocessing` sólo se pueden pasar por herencia al crear el
    proceso, y la fábrica, pasada una sola vez, conserva su `MaskCache` entre
    todas las variantes que ese proceso evalúe.
    """
    # Un proceso que puso algo en una `multiprocessing.Queue` espera, al
    # salir, a que su hilo alimentador lo pase todo al pipe. Si el principal
    # dejó de leer (cancelaron) y el pipe se llenó, esa espera no termina y
    # `shutdown` se cuelga con el proceso vivo. Perder las últimas cuentas de
    # consultas al cerrar no le hace nada a nadie.
    reports.cancel_join_thread()
    _worker.update(factory=factory, cancel=cancel, best=best, reports=reports)


def _run_in_worker(variant: Variant, parts: Sequence[Part], supply: SheetSupply,
                   config: NestConfig) -> tuple[int, Outcome | None, int]:
    reports = _worker["reports"]
    last = [0]

    def on_queries(total: int) -> None:
        last[0] = total
        reports.put((variant.index, total))

    watch = _Watch(
        cancelled=_worker["cancel"].is_set,
        best_new_sheets=lambda: _worker["best"].value,
        on_queries=on_queries,
    )
    outcome = evaluate(variant, parts, supply, config, _worker["factory"], watch)
    # El total viaja también con el resultado: la cola es asíncrona, y el
    # último mensaje puede llegar después de que el principal vio terminar
    # a la variante.
    return variant.index, outcome, last[0]


class _Evaluator:
    """Evalúa tandas de variantes: acá mismo, o en un pool de procesos `spawn`.

    Con un proceso, o con una tanda de una sola variante, corre acá, una
    detrás de otra. Si no, en un `ProcessPoolExecutor` que se crea la
    primera vez que hace falta y se reusa entre tandas. Es un administrador
    de contexto para que el pool se cierre pase lo que pase -- cancelación
    incluida -- sin dejar ningún proceso vivo.
    """

    def __init__(self, config: NestConfig, factory: Callable[[], Oracle],
                 processes: int | None = None) -> None:
        self._config = config
        self._factory = factory
        self._processes = max(1, config.workers if processes is None else processes)
        # `spawn` en todas las plataformas: en Linux el por omisión es
        # `fork`, y un proceso hecho con fork hereda hilos y cerrojos a medio
        # tomar del principal (el servidor de la interfaz tiene varios).
        self._context = multiprocessing.get_context("spawn")
        self._pool: ProcessPoolExecutor | None = None
        self._cancel = None
        self._best = None
        self._reports = None
        # Acá y no al armar el pool: `run_portfolio` crea el evaluador antes
        # de la base, así que una fábrica que no viaja se rechaza antes de
        # gastar una pasada entera. Rápido no prueba variantes, nunca arma el
        # pool, y no tiene por qué pedirle nada a su fábrica.
        if self._processes > 1 and EFFORT_BATCHES.get(config.effort, 0) > 0:
            self._check_factory_travels()

    def __enter__(self) -> "_Evaluator":
        return self

    def __exit__(self, *exc) -> bool:
        if self._pool is not None:
            # Primero el evento: un proceso a mitad de una variante lo ve en
            # su próxima consulta y levanta `Cancelado`, así que `shutdown`
            # no espera a que termine una pasada entera.
            self._cancel.set()
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None
            self._reports.close()
            self._reports.join_thread()
        return False

    def run(self, batch: Sequence[Variant], parts: Sequence[Part], supply: SheetSupply,
            best_new_sheets: int, progress: _Progress) -> list[Outcome]:
        """Los resultados de la tanda que no se cortaron, en orden de índice."""
        if self._processes == 1 or len(batch) <= 1:
            return self._run_here(batch, parts, supply, best_new_sheets, progress)
        return self._run_in_pool(batch, parts, supply, best_new_sheets, progress)

    def _run_here(self, batch, parts, supply, best_new_sheets, progress) -> list[Outcome]:
        mejor = best_new_sheets
        outcomes: list[Outcome] = []
        for variant in batch:
            outcome = evaluate(
                variant, parts, supply, self._config, self._factory,
                progress.watch(("variante", variant.index), lambda: mejor),
            )
            progress.variant_done(outcome)
            if outcome is not None:
                outcomes.append(outcome)
                mejor = min(mejor, outcome.cost.placas_nuevas)
        return outcomes

    def _check_factory_travels(self) -> None:
        try:
            pickle.dumps(self._factory)
        except Exception as error:
            raise TypeError(
                "para probar variantes en paralelo, la fábrica de oráculos tiene "
                "que poder mandarse a otro proceso, y ésta no se puede serializar "
                "(una lambda que captura un MaskCache no se puede). Usá "
                "nesting.engine.raster.oracle.RasterOracleFactory, una clase, o "
                "NestConfig(workers=1)."
            ) from error

    def _start_pool(self) -> None:
        self._cancel = self._context.Event()
        self._best = self._context.Value("q", 0)
        self._reports = self._context.Queue()
        self._pool = ProcessPoolExecutor(
            max_workers=self._processes,
            mp_context=self._context,
            initializer=_init_worker,
            initargs=(self._factory, self._cancel, self._best, self._reports),
        )

    def _drain(self, progress: _Progress) -> None:
        while True:
            try:
                index, total = self._reports.get_nowait()
            except queue.Empty:
                return
            progress.record(("variante", index), total)

    def _run_in_pool(self, batch, parts, supply, best_new_sheets, progress) -> list[Outcome]:
        if self._pool is None:
            self._start_pool()
        # "Cortar lo que ya perdió": el menor `placas_nuevas` terminado. Sólo
        # lo escribe este proceso, y sólo para bajarlo; los del pool lo leen.
        self._best.value = best_new_sheets
        pending = {
            self._pool.submit(_run_in_worker, variant, list(parts), supply, self._config)
            for variant in batch
        }
        outcomes: list[Outcome] = []
        while pending:
            done, pending = wait(pending, timeout=POLL_SECONDS, return_when=FIRST_COMPLETED)
            self._drain(progress)
            for future in done:
                index, outcome, total = future.result()
                progress.record(("variante", index), total)
                progress.variant_done(outcome)
                if outcome is not None:
                    outcomes.append(outcome)
                    if outcome.cost.placas_nuevas < self._best.value:
                        self._best.value = outcome.cost.placas_nuevas
            if not done:
                # Nadie terminó en este intervalo, pero las consultas sí
                # subieron, y sólo avisando se entera el principal de que le
                # pidieron cancelar.
                progress.emit()
        self._drain(progress)
        return sorted(outcomes, key=lambda o: o.index)


def _finish(best: Outcome, winner: Variant, parts: Sequence[Part], supply: SheetSupply,
            config: NestConfig, factory: Callable[[], Oracle], progress: _Progress) -> PackResult:
    """Recuperación y compactación sobre la ganadora, todavía con compuestas, y desarmar.

    Avisa como avisaba `pack()` después del plan 2: una vez al entrar, una
    por pieza que la recuperación o la compactación intentan (su `aviso`), y
    una al terminar. Cancelar corta en cualquiera de esos avisos, y también
    en la próxima consulta (`_WatchedOracle`).
    """
    progress.final()
    watch = progress.watch("final", _never_beaten, emit=False)
    counter = _QueryCounter(watch)
    watched = _WatchedFactory(factory, counter, watch, 0)

    def aviso(ubicadas: int, placa: int) -> None:
        progress.emit()

    avisar = aviso if progress.listening else None
    working = list(winner.order)
    result = _recuperar_de_la_ultima_placa(best.packed, working, config, watched,
                                           supply.material_name, avisar)
    result = _compact_last_sheet(result, working, config, watched,
                                 supply.material_name, avisar)
    counter.flush()
    progress.finish()
    return pares.disassemble(result, winner.composites, parts)


def run_portfolio(
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    progreso: Callable[[Avance], bool] | None = None,
) -> PortfolioResult:
    """Acomoda `parts` probando la cartera que corresponde al esfuerzo."""
    if config.effort not in EFFORT_BATCHES:
        raise UnknownEffortError(
            f"nivel de esfuerzo {config.effort!r} desconocido; "
            f"use uno de {', '.join(EFFORT_BATCHES)}"
        )

    # Antes de la base: si la fábrica no puede viajar a los procesos, que se
    # sepa ya y no después de una pasada entera (ver `_Evaluator`).
    evaluator = _Evaluator(config, oracle_factory)
    started = time.perf_counter()
    lower = cota_minima(parts, supply, config.margin)
    source = VariantSource(parts, supply, config)
    base = source.base()
    if not parts:
        return PortfolioResult(PackResult(seconds=time.perf_counter() - started), base, [], lower)

    size = batch_size(config.workers)
    planned = planned_variants(config.effort, config.workers)
    progress = _Progress(progreso, len(parts), planned,
                         initial_forecast(parts, supply, config))

    best = evaluate(base, parts, supply, config, oracle_factory,
                    progress.watch("base", _never_beaten, emit=False), aviso=progress.placed)
    progress.base_done(best)
    winner = base
    evaluated = [base]

    with evaluator:
        for number in range(1, EFFORT_BATCHES[config.effort] + 1):
            if lower is not None and best.cost.placas_nuevas <= lower:
                break
            batch = source.batch(number, size, winner)
            by_index = {v.index: v for v in batch}
            for outcome in evaluator.run(batch, parts, supply, best.cost.placas_nuevas, progress):
                # Estrictamente menor: entre costos iguales gana el índice
                # más bajo, y `run` devuelve en orden de índice.
                if outcome.cost < best.cost:
                    best, winner = outcome, by_index[outcome.index]
            evaluated.extend(batch)

    result = _finish(best, winner, parts, supply, config, oracle_factory, progress)
    result.seconds = time.perf_counter() - started
    return PortfolioResult(result, winner, evaluated, lower)
