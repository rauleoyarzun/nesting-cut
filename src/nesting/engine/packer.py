"""Strategy: what order, which rotations, and when to open a new sheet.

Knows nothing about how placement is computed. It talks to an `Oracle`, so the
same code drives the throwaway shelf engine and the real raster engine.
"""

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from nesting.engine.oracle import NestConfig, Oracle, Weights, transformed_bbox
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement
from nesting.model.sheet import Sheet, SheetSupply, allowed_angles


class PartTooLargeError(Exception):
    """A part does not fit on an empty sheet, so no layout can ever contain it."""


@dataclass
class PackResult:
    placements: list[Placement] = field(default_factory=list)
    sheets_used: int = 0
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


@dataclass(frozen=True)
class Avance:
    """Dónde va el motor, para quien esté mirando.

    Lleva el intento además de las piezas porque `pack` corre varias pasadas
    completas y CADA UNA REINICIA el conteo de ubicadas. Una barra armada
    sólo con `ubicadas / totales` retrocedería al empezar el intento
    siguiente, y una barra que retrocede es peor que no tener barra.
    """

    intento: int
    intentos: int
    ubicadas: int
    totales: int
    placa: int
    compactando: bool = False


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


def _pack_once(
    order: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    aviso: Callable[[int, int], None] | None = None,
) -> PackResult:
    """One greedy pass, placing `order` in exactly the order given.

    `aviso` recibe (piezas ubicadas hasta ahora en esta pasada, placa en
    curso empezando en 1) despues de cada pieza ubicada. Puede levantar para
    abandonar: esta funcion no atrapa nada, asi que la excepcion sale limpia
    sin dejar estado a medias en el oraculo.
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
                continue
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
    result.sheets_used = len(usadas)
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

EL PRESUPUESTO DE 5 MINUTOS, HONESTAMENTE. A 2.0 mm/px (el default desde la
Task 24) `normal` sale mucho más barato que lo medido en la Task 19: 48.3s
sobre el archivo de referencia (36 piezas) y 132.1s sobre `muestra.dxf` a
--copias 8 (96 piezas). Pero el objetivo no es universal: una sola pasada
sobre `banqueta final raulo.ai` a --copias 5 (200 piezas) ya tarda 450.6s,
o sea que `normal` ahí se va muy por encima de los 5 minutos. El objetivo
vale para trabajos del tamaño contra el que se calibró, no para cualquier
carga.

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


def pack(
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    progreso: Callable[[Avance], bool] | None = None,
) -> PackResult:
    """Place every part, trying several insertion orders and keeping the best.

    `progreso`, si se pasa, se llama con un `Avance` despues de cada pieza
    ubicada durante la pasada golosa, una vez con `compactando=True` al
    entrar en la compactacion final, y ADEMAS muchas veces durante toda la
    recuperacion cancelable que corre antes de esa compactacion -- un aviso
    por cada pieza que `_recuperar_de_la_ultima_placa` intenta reubicar, no
    una sola llamada (ver su docstring). Devolver `False` en cualquiera de
    esas llamadas pide abandonar, y `pack` levanta `Cancelado`. No pasarlo
    deja el comportamiento exactamente como estaba: es lo que hace la CLI.
    """
    if config.effort not in EFFORT_RESTARTS:
        raise UnknownEffortError(
            f"nivel de esfuerzo {config.effort!r} desconocido; "
            f"use uno de {', '.join(EFFORT_RESTARTS)}"
        )

    started = time.perf_counter()
    if not parts:
        return PackResult(seconds=time.perf_counter() - started)

    rng = random.Random(config.seed)
    by_area = sorted(parts, key=lambda p: p.area, reverse=True)

    intentos = EFFORT_RESTARTS[config.effort]
    totales = len(parts)

    def avisos_de(intento: int) -> Callable[[int, int], None] | None:
        if progreso is None:
            return None

        def avisar(ubicadas: int, placa: int) -> None:
            if not progreso(Avance(intento, intentos, ubicadas, totales, placa)):
                raise Cancelado("el trabajo se canceló")

        return avisar

    best_order = list(by_area)
    best = _pack_once(best_order, supply, config, oracle_factory, avisos_de(1))
    best_cost = layout_cost(best, parts)

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

    for i in range(EFFORT_RESTARTS[config.effort] - 1):
        if config.effort == "lento" and i >= shared_restarts:
            perturb_base = best_order
        else:
            perturb_base = by_area
        candidate_order = _perturb(perturb_base, rng)
        candidate = _pack_once(
            candidate_order, supply, config, oracle_factory, avisos_de(i + 2)
        )
        candidate_cost = layout_cost(candidate, parts)
        if candidate_cost < best_cost:
            best, best_cost, best_order = candidate, candidate_cost, candidate_order

    if progreso is not None and not progreso(
        Avance(intentos, intentos, totales, totales, 0, compactando=True)
    ):
        raise Cancelado("el trabajo se canceló")

    # Antes de compactar, y después del aviso de arriba a propósito: la
    # recuperación es la parte más lenta de este tramo final (un
    # `_pack_once` por placa anterior), así que quien mire la barra ya la ve
    # en "compactando" en vez de quedarse mirando el último aviso de la
    # pasada golosa.
    #
    # La recuperación reporta como "compactando" y no con una fase propia
    # a propósito: `Avance` no tiene un campo para distinguirla (agregar
    # uno es una decisión de UI aparte, no algo que este aviso deba forzar)
    # y, para quien mira la barra, "compactando" ya es verdad -- es
    # reempaque de placas ya armadas, no la pasada golosa inicial. Lo único
    # que le faltaba a esa fase era poder cancelarse; el rótulo no cambia.
    def aviso_recuperacion(ubicadas: int, placa: int) -> None:
        if not progreso(Avance(intentos, intentos, totales, totales, 0, compactando=True)):
            raise Cancelado("el trabajo se canceló")

    best = _recuperar_de_la_ultima_placa(
        best, parts, config, oracle_factory, supply.material_name,
        aviso_recuperacion if progreso is not None else None,
    )
    best = _compact_last_sheet(
        best, parts, config, oracle_factory, supply.material_name
    )
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
        sheets_used=len(sheets_finales),
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
) -> PackResult:
    """Re-pack the last sheet on its own, pulled harder towards the corner.

    `material_name` es obligatorio y sólo nombra el material en un eventual
    `PartTooLargeError`; ver el docstring de
    `_recuperar_de_la_ultima_placa`, que lo recibe igual y por lo mismo.
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
