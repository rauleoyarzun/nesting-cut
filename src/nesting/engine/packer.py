"""Strategy: what order, which rotations, and when to open a new sheet.

Knows nothing about how placement is computed. It talks to an `Oracle`, so the
same code drives the throwaway shelf engine and the real raster engine.
"""

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from nesting.engine.oracle import NestConfig, Oracle, Weights, transformed_bbox
from nesting.engine.prevision import (
    estimate_sheets,
    forecast_compaction,
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


class Cancelado(Exception):
    """El motor abandonó porque quien lo miraba se lo pidió.

    Es una excepción y no un `PackResult` a medias a propósito: un resultado
    incompleto se puede escribir a un DXF sin que nada avise, y ese DXF va a
    una fresadora.
    """


class _QueryCounter:
    """Cuántas consultas se les hicieron a los oráculos de UN `pack`.

    Un objeto y no un entero porque lo comparten todos los oráculos que la
    corrida crea -- uno por placa, por intento y por fase -- y cada uno
    tiene que sumar al mismo número.
    """

    def __init__(self) -> None:
        self.count = 0


class _CountingOracle:
    """Un oráculo que cuenta sus `best_placement` y en todo lo demás es el de adentro.

    Se envuelve la FÁBRICA en `pack` en vez de instrumentar cada fase: la
    recuperación y la compactación piden sus oráculos a la misma fábrica
    envuelta, así que ninguna consulta puede quedar fuera de la cuenta por
    olvidarse de pasar un contador.
    """

    def __init__(self, inner: Oracle, counter: _QueryCounter) -> None:
        self._inner = inner
        self._counter = counter

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._inner.reset(sheet_w, sheet_h, config)

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        self._counter.count += 1
        return self._inner.best_placement(part, angle, mirror)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        self._inner.place(part, angle, mirror, x, y)


def _counting(
    oracle_factory: Callable[[], Oracle], counter: _QueryCounter
) -> Callable[[], Oracle]:
    return lambda: _CountingOracle(oracle_factory(), counter)


class _Informe:
    """Arma cada `Avance` de un `pack` y corta si quien mira pide cancelar.

    Vive aparte porque `pack` avisa desde cuatro lugares -- la pasada
    golosa, la entrada al tramo final, la recuperación y la compactación --
    y los cuatro tienen que poner las mismas consultas y cortar igual.
    """

    def __init__(
        self,
        progreso: Callable[[Avance], bool] | None,
        intentos: int,
        totales: int,
        consultas: _QueryCounter,
    ) -> None:
        self._progreso = progreso
        self._intentos = intentos
        self._totales = totales
        self._consultas = consultas
        self.previstas = 0

    def emitir(
        self, intento: int, ubicadas: int, placa: int, compactando: bool = False
    ) -> None:
        if self._progreso is None:
            return
        hechas = self._consultas.count
        avance = Avance(
            intento,
            self._intentos,
            ubicadas,
            self._totales,
            placa,
            compactando,
            consultas_hechas=hechas,
            consultas_previstas=max(self.previstas, hechas),
        )
        if not self._progreso(avance):
            raise Cancelado("el trabajo se canceló")

    def corregir_tras_intentos(self, hechos: int, restantes_finales: int) -> None:
        """Ya terminaron `hechos` pasadas golosas completas, y todo lo
        contado hasta acá es de ellas: los intentos que faltan se prevén
        como el promedio de los hechos, y las fases finales con las placas
        reales del mejor layout hasta ahora."""
        por_intento = self._consultas.count / hechos
        self.previstas = round(por_intento * self._intentos) + restantes_finales

    def prever_desde_ahora(self, restantes: int) -> None:
        """Lo que falta ya se sabe contar desde el estado actual."""
        self.previstas = self._consultas.count + restantes

    def aviso_de(self, intento: int) -> Callable[[int, int], None] | None:
        """El `aviso` de la pasada golosa número `intento`."""
        if self._progreso is None:
            return None

        def avisar(ubicadas: int, placa: int) -> None:
            self.emitir(intento, ubicadas, placa)

        return avisar

    def aviso_final(self) -> Callable[[int, int], None] | None:
        """El `aviso` de la recuperación y la compactación: "compactando".

        Las dos reportan con el mismo rótulo a propósito (ver el comentario
        en `pack`): para quien mira la barra las dos son reempaque de placas
        ya armadas. Lo que las distingue ahora son las consultas, no el
        texto.
        """
        if self._progreso is None:
            return None

        def avisar(ubicadas: int, placa: int) -> None:
            self.emitir(self._intentos, self._totales, 0, compactando=True)

        return avisar


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
) -> float | None:
    """Cuánto tarda UNA consulta en esta máquina, con estas opciones.

    Pregunta por la pieza más grande, en la primera orientación que la veta
    de la placa del Material permite, sobre una placa vacía. Incluye
    rasterizar la máscara si el oráculo lo hace: quien llama pasa una
    fábrica con caché nueva para que así sea, porque la corrida real también
    rasteriza cada orientación la primera vez. `reset` queda afuera del
    tiempo: se paga una vez por placa, no por consulta.

    Una sola consulta y no un promedio: tarda menos de un segundo, y el
    número vale en cualquier máquina porque se mide en ella. Devuelve `None`
    si no hay piezas o si la veta no deja ninguna orientación.
    """
    if not parts:
        return None
    choices = orientations(supply.stock, config)
    if not choices:
        return None
    part = max(parts, key=lambda p: p.area)
    oracle = oracle_factory()
    oracle.reset(supply.stock.width, supply.stock.height, config)
    angle, mirror = choices[0]
    started = clock()
    oracle.best_placement(part, angle, mirror)
    return clock() - started


def _pack_once(
    order: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    aviso: Callable[[int, int], None] | None = None,
) -> PackResult:
    """One greedy pass, placing `order` in exactly the order given.

    `aviso` recibe (piezas ubicadas hasta ahora en esta pasada, placa en
    curso empezando en 1) despues de cada pieza INTENTADA, haya entrado o
    no: una pieza que no entra gasta sus consultas igual, y sin aviso ni el
    contador de consultas ni el pedido de cancelar la verian. Puede levantar
    para abandonar: esta funcion no atrapa nada, asi que la excepcion sale
    limpia sin dejar estado a medias en el oraculo.
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
            spot = _best_over_orientations(oracle, part, choices)
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


def _best_over_orientations(
    oracle: Oracle,
    part: Part,
    choices: Sequence[tuple[float, bool]],
) -> tuple[float, bool, float, float] | None:
    """Ask the oracle about every orientation and keep the best-scoring one."""
    best: tuple[float, bool, float, float] | None = None
    best_score = float("-inf")

    for angle, mirror in choices:
        spot = oracle.best_placement(part, angle, mirror)
        if spot is None:
            continue
        x, y, score = spot
        if score > best_score:
            best_score = score
            best = (angle, mirror, x, y)

    return best


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


EFFORT_RESTARTS: dict[str, int] = {"rapido": 1, "normal": 3, "lento": 12}
"""How many insertion orders each effort level tries.

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
superconjunto de reintentos más abajo), nunca por suerte de la semilla."""

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
    """Cuántas pasadas golosas corre este nivel de esfuerzo, o el error de siempre."""
    if config.effort not in EFFORT_RESTARTS:
        raise UnknownEffortError(
            f"nivel de esfuerzo {config.effort!r} desconocido; "
            f"use uno de {', '.join(EFFORT_RESTARTS)}"
        )
    return EFFORT_RESTARTS[config.effort]


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


def _compaction_forecast(result: PackResult, config: NestConfig) -> int:
    """Consultas de compactar la última placa de `result`, contadas sobre ella."""
    if result.sheets_used == 0:
        return 0
    last = result.sheets_used - 1
    on_last = sum(1 for p in result.placements if p.sheet == last)
    return forecast_compaction(on_last, len(orientations(result.sheets[last], config)))


def _forecast_final_phases(result: PackResult, config: NestConfig) -> int:
    """Consultas de la recuperación y la compactación sobre las placas reales de `result`."""
    if result.sheets_used == 0:
        return 0
    per_sheet = [0] * result.sheets_used
    for placement in result.placements:
        per_sheet[placement.sheet] += 1
    last = result.sheets_used - 1
    previous = [
        (per_sheet[i], len(orientations(result.sheets[i], config))) for i in range(last)
    ]
    return forecast_recovery(previous, per_sheet[last]) + _compaction_forecast(
        result, config
    )


def pack(
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    progreso: Callable[[Avance], bool] | None = None,
) -> PackResult:
    """Place every part, trying several insertion orders and keeping the best.

    `progreso`, si se pasa, se llama con un `Avance` despues de cada pieza
    que la pasada golosa intenta ubicar (entre o no), una vez con
    `compactando=True` al entrar al tramo final, otra vez por cada pieza que
    intentan la recuperacion (`_recuperar_de_la_ultima_placa`) y la
    compactacion (`_compact_last_sheet`), y una ultima vez al terminar. Cada
    `Avance` lleva las consultas hechas hasta ese momento, contadas sobre
    TODOS los oraculos que la corrida pidio a `oracle_factory`. Devolver
    `False` en cualquiera de esas llamadas pide abandonar, y `pack` levanta
    `Cancelado`. No pasarlo deja el layout exactamente como estaba: es lo
    que hace la CLI.
    """
    intentos = _restarts_for(config)

    started = time.perf_counter()
    if not parts:
        return PackResult(seconds=time.perf_counter() - started)

    rng = random.Random(config.seed)
    by_area = sorted(parts, key=lambda p: p.area, reverse=True)

    totales = len(parts)

    consultas = _QueryCounter()
    contado = _counting(oracle_factory, consultas)
    informe = _Informe(progreso, intentos, totales, consultas)
    informe.previstas = initial_forecast(parts, supply, config)

    best_order = list(by_area)
    best = _pack_once(best_order, supply, config, contado, informe.aviso_de(1))
    best_cost = layout_cost(best, parts)
    informe.corregir_tras_intentos(1, _forecast_final_phases(best, config))

    # Garantia: "lento" nunca puede ser peor que "normal", igual que "normal"
    # nunca puede ser peor que "rapido". Para "rapido"/"normal" esa garantia
    # sale gratis de que ambos comparten la misma primera pasada
    # deterministica y solo reemplazan `best` cuando estrictamente mejora.
    # Pero "normal" y "lento" corrian trayectorias que divergian desde el
    # primer paso -- "normal" siempre perturbaba desde `by_area` (reintentos
    # al azar) y "lento" siempre perturbaba desde `best_order` (escalada de
    # colina) -- y sin ningun superconjunto entre ambas, no habia forma de
    # garantizar `lento <= normal` por construccion; con la misma semilla
    # podian terminar en layouts no comparables.
    #
    # El arreglo: "lento" ejecuta primero, exactamente, los mismos
    # `EFFORT_RESTARTS["normal"] - 1` reintentos que haria "normal" -- misma
    # base de perturbacion (`by_area`) y mismo generador `rng`, consumido en
    # la misma secuencia -- y solo despues de agotar ese prefijo compartido
    # pasa a perturbar desde `best_order` (escalada de colina) para el resto
    # de sus reintentos. `_perturb` consume `rng.randrange` la misma
    # cantidad de veces sin importar el contenido de la lista que reciba
    # (depende solo de `len(parts)`), asi que el stream de `rng` avanza
    # exactamente igual en ambos niveles durante el prefijo compartido, y
    # las `candidate_order` de esos pasos resultan identicas byte a byte
    # entre una corrida en "normal" y una en "lento" con la misma semilla.
    # Al final del prefijo, el estado (`best`, `best_cost`, `best_order`) de
    # "lento" es entonces exactamente el mismo que el resultado final de
    # "normal". Los reintentos restantes de "lento" solo pueden mantenerlo o
    # mejorarlo (el `if candidate_cost < best_cost` de abajo nunca lo
    # empeora), asi que el costo final de "lento" no puede superar al de
    # "normal" -- queda garantizado por construccion, no por casualidad de
    # la semilla.
    shared_restarts = EFFORT_RESTARTS["normal"] - 1

    for i in range(intentos - 1):
        if config.effort == "lento" and i >= shared_restarts:
            perturb_base = best_order
        else:
            perturb_base = by_area
        candidate_order = _perturb(perturb_base, rng)
        candidate = _pack_once(
            candidate_order, supply, config, contado, informe.aviso_de(i + 2)
        )
        candidate_cost = layout_cost(candidate, parts)
        if candidate_cost < best_cost:
            best, best_cost, best_order = candidate, candidate_cost, candidate_order
        informe.corregir_tras_intentos(i + 2, _forecast_final_phases(best, config))

    informe.emitir(intentos, totales, 0, compactando=True)

    # Antes de compactar, y después del aviso de arriba a propósito: la
    # recuperación es la parte más lenta de este tramo final (un
    # `_pack_once` por placa anterior), así que quien mire la barra ya la ve
    # en "compactando" en vez de quedarse mirando el último aviso de la
    # pasada golosa.
    #
    # La recuperación reporta como "compactando" y no con una fase propia
    # a propósito: para quien mira la barra, "compactando" ya es verdad --
    # es reempaque de placas ya armadas, no la pasada golosa inicial. Lo que
    # distingue una fase de otra ahora son las consultas del `Avance`, que
    # el estimador de tiempo usa sin saber qué fase es.
    choices_ultima = len(orientations(best.sheets[-1], config))

    def prever_recuperacion(restantes: int, pendientes: int) -> None:
        # Mientras dura la recuperación, la compactación se prevé con las
        # pendientes de ahora: la recuperación sólo puede sacar piezas de
        # la última placa, así que es cota superior.
        informe.prever_desde_ahora(
            restantes + forecast_compaction(pendientes, choices_ultima)
        )

    best = _recuperar_de_la_ultima_placa(
        best, parts, config, contado, supply.material_name,
        informe.aviso_final(), prever_recuperacion,
    )
    informe.prever_desde_ahora(_compaction_forecast(best, config))
    best = _compact_last_sheet(
        best, parts, config, contado, supply.material_name, informe.aviso_final(),
    )
    # El último aviso: todo lo consultado ya está contado, así que quien
    # estime el tiempo ve cero restante en vez de quedarse con el último
    # aviso de la compactación.
    informe.prever_desde_ahora(0)
    informe.emitir(intentos, totales, 0, compactando=True)
    best.seconds = time.perf_counter() - started
    return best


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
