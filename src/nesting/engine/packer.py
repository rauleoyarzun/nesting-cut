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
from nesting.model.material import Material, allowed_angles
from nesting.model.part import Part, Placement


class PartTooLargeError(Exception):
    """A part does not fit on an empty sheet, so no layout can ever contain it."""


@dataclass
class PackResult:
    placements: list[Placement] = field(default_factory=list)
    sheets_used: int = 0
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


def orientations(material: Material, config: NestConfig) -> list[tuple[float, bool]]:
    """Every (angle, mirror) pair the material and config permit."""
    angles = allowed_angles(material, config.angles)
    result = [(a, False) for a in angles]
    if config.mirror:
        result.extend((a, True) for a in angles)
    return result


def _pack_once(
    order: Sequence[Part],
    material: Material,
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

    choices = orientations(material, config)
    remaining = list(order)
    sheet_area = material.sheet_w * material.sheet_h
    placed_area_per_sheet: list[float] = []

    sheet = 0
    total_ubicadas = 0
    while remaining:
        oracle = oracle_factory()
        oracle.reset(material.sheet_w, material.sheet_h, config)

        still_pending: list[Part] = []
        placed_area = 0.0
        placed_count = 0

        for part in remaining:
            spot = _best_over_orientations(oracle, part, choices)
            if spot is None:
                still_pending.append(part)
                continue
            angle, mirror, x, y = spot
            oracle.place(part, angle, mirror, x, y)
            result.placements.append(Placement(part.id, sheet, Transform(angle, mirror, x, y)))
            placed_area += part.area
            placed_count += 1
            if aviso is not None:
                aviso(total_ubicadas + placed_count, sheet + 1)

        # Guard on whether anything was placed on this sheet, not on how much
        # *area* it added: a placed part whose net area happens to be zero (a
        # self-intersecting contour whose signed area cancels, see Hallazgo 1)
        # would otherwise make `placed_area == 0.0` even though `still_pending`
        # is empty -- indexing `still_pending[0]` then crashed with
        # `IndexError`. Worse, when a sheet mixes such zero-area parts with
        # real ones that could not fit, the old guard blamed a real, fitting
        # part for the failure instead of just moving on to the next sheet.
        if placed_count == 0:
            _raise_too_large(still_pending[0], material, config, choices)

        placed_area_per_sheet.append(placed_area)
        total_ubicadas += placed_count
        remaining = still_pending
        sheet += 1

    result.sheets_used = sheet
    result.utilization = [area / sheet_area for area in placed_area_per_sheet]
    result.total_utilization = (
        sum(placed_area_per_sheet) / (sheet_area * sheet) if sheet else 0.0
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
    material: Material,
    config: NestConfig,
    choices: Sequence[tuple[float, bool]],
) -> None:
    """Report the smallest footprint the part can take, against the usable area.

    A single orientation is picked -- the one minimizing its own larger
    dimension (max(width, height)) -- rather than taking the min width and
    min height independently, which can mix two different orientations and
    describe a bounding box the part never actually has.
    """
    best_w = best_h = None
    best_max = float("inf")
    for angle, mirror in choices:
        x0, y0, x1, y1 = transformed_bbox(part, angle, mirror)
        w, h = x1 - x0, y1 - y0
        if max(w, h) < best_max:
            best_max = max(w, h)
            best_w, best_h = w, h

    usable_w = material.sheet_w - 2 * config.margin
    usable_h = material.sheet_h - 2 * config.margin
    raise PartTooLargeError(
        f"la pieza {part.id} no entra en una placa vacía: mide al menos "
        f"{best_w:.1f} x {best_h:.1f} mm en su mejor orientación, "
        f"y el área útil de la placa {material.name} es "
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
`NESTING 2.ai` (mdf15, sep 10, borde 10, 2.0 mm/px), medido en la Tarea 6:

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

    placas: int
    """Manda sobre todo lo demás: una placa menos siempre gana."""

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

    by_id = {p.id: p for p in parts}
    last_sheet = result.sheets_used - 1
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

    return CostoLayout(result.sheets_used, material, top)


def pack(
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    progreso: Callable[[Avance], bool] | None = None,
) -> PackResult:
    """Place every part, trying several insertion orders and keeping the best.

    `progreso`, si se pasa, se llama con un `Avance` despues de cada pieza
    ubicada y una vez mas al entrar en la compactacion final. Devolver
    `False` pide abandonar, y `pack` levanta `Cancelado`. No pasarlo deja el
    comportamiento exactamente como estaba: es lo que hace la CLI.
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
    best = _pack_once(best_order, material, config, oracle_factory, avisos_de(1))
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
            candidate_order, material, config, oracle_factory, avisos_de(i + 2)
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
        best, parts, material, config, oracle_factory,
        aviso_recuperacion if progreso is not None else None,
    )
    best = _compact_last_sheet(best, parts, material, config, oracle_factory)
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
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    aviso: Callable[[int, int], None] | None = None,
) -> PackResult:
    """Reintentar en las placas anteriores lo que quedó en la última.

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

    Un reempaque se acepta sólo si en su primera placa siguen estando TODAS
    las piezas que ya tenía y entró al menos una pendiente. Con esa regla el
    costo del layout no puede subir: las placas anteriores conservan sus
    piezas, la última pierde alguna (y si se queda sin ninguna, baja el
    conteo de placas, que es el primer campo de `CostoLayout`), y las que
    quedan en la última no se tocan, así que ni `material_ultima` ni
    `alto_ultima` pueden crecer.

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
            redone = _pack_once(orden, material, config, oracle_factory, aviso)

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
    sheets = result.sheets_used if quedan else ultima

    # La misma cuenta que hace `_pack_once`: áreas por placa y UNA división
    # al final. Si acá se sumaran fracciones ya divididas, el total podría
    # no coincidir con el que informa una corrida normal, y el usuario vería
    # dos números distintos para el mismo layout.
    sheet_area = material.sheet_w * material.sheet_h
    areas = [0.0] * sheets
    for p in placements:
        areas[p.sheet] += by_id[p.part_id].area

    return PackResult(
        placements=placements,
        sheets_used=sheets,
        utilization=[area / sheet_area for area in areas],
        total_utilization=sum(areas) / (sheet_area * sheets) if sheets else 0.0,
        seconds=result.seconds,
    )


def _compact_last_sheet(
    result: PackResult,
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """Re-pack the last sheet on its own, pulled harder towards the corner."""
    if result.sheets_used < 1:
        return result

    last = result.sheets_used - 1
    by_id = {p.id: p for p in parts}
    on_last = [by_id[p.part_id] for p in result.placements if p.sheet == last]
    if len(on_last) < 2:
        return result

    boosted = replace(
        config,
        weights=Weights(
            bottom_left=config.weights.bottom_left * COMPACTION_BOOST,
            contact=config.weights.contact,
        ),
    )
    order = sorted(on_last, key=lambda p: p.area, reverse=True)
    redone = _pack_once(order, material, boosted, oracle_factory)

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

    sheet_area = material.sheet_w * material.sheet_h
    result.placements = kept + moved
    result.utilization[last] = sum(p.area for p in on_last) / sheet_area
    return result
