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
) -> PackResult:
    """One greedy pass, placing `order` in exactly the order given."""
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

Measured against wall-clock, not guessed: see the Task 19 report
(`.superpowers/sdd/task-19-report.md`). A single greedy pass over
`bench/files/muestra.dxf` (mdf18, default sep/margin, 1 mm/px) took ~46s at
--copias 4 and ~81s at --copias 6, and `pack()`'s time scales linearly with
the restart count. `normal = 3` lands at 182s / 236s -- comfortably under
the project's 5-minute target for the harder of the two references, with
~20% of the budget still spare. `normal = 4` already crosses it (317s at
--copias 6), so 3 is the most this level can spend. `lento = 12` (4x normal)
is chosen for a real, monotonic drop in the compaction cost as restarts grow
(measured on a smaller synthetic scenario, since the reference file is too
slow to sweep at this multiplier): mean last-sheet height fell from 816mm at
3 restarts to 800mm at 12, with the best-of-N result improving 790mm -> 780mm
too. It costs roughly 4x normal's wall time in exchange.

What that time actually buys, honestly: a reviewer measured `normal` against
`rapido` over 7 varied scenarios and found `normal` ties `rapido` -- same
`layout_cost` -- in 5 of the 7, despite costing 3-4x as much wall time (the
`normal = 3` vs `rapido = 1` ratio above). The gain is not gradual; it does
not show up as "slightly better packing" most of the time. It shows up
specifically when the layout sits near a sheet breakpoint -- close enough to
the edge of needing one more sheet that a better insertion order avoids
opening it. That is also exactly the case where it is worth the most: saving
a whole sheet dwarfs the extra minutes spent finding the order that avoids
it. Away from a breakpoint, extra restarts mostly re-arrange the same sheet
count at a similar height, which is why the tie rate is so high. `lento`
follows the same pattern one level up (see `pack()`'s superset construction
below, which also guarantees `lento <= normal <= rapido` by construction,
never just by luck of the seed) -- it is worth reaching for when a job is
suspected to be near a breakpoint and the extra wall time is affordable, not
as a default "better quality" dial."""

COMPACTION_BOOST = 3.0
"""How much the bottom-left weight is multiplied by on the final compaction pass."""


class UnknownEffortError(Exception):
    """The requested effort level is not one of the three defined ones."""


def layout_cost(result: PackResult, parts: Sequence[Part]) -> tuple[int, float]:
    """How bad a layout is. Lower is better; compared as a tuple.

    Sheet count dominates. Between layouts using the same number of sheets, the
    one whose last sheet is most compacted wins, which leaves the offcut as one
    usable block instead of scattered strips.
    """
    if not result.placements:
        return (0, 0.0)

    by_id = {p.id: p for p in parts}
    last_sheet = result.sheets_used - 1
    top = 0.0

    for placement in result.placements:
        if placement.sheet != last_sheet:
            continue
        part = by_id[placement.part_id]
        _, _, _, y1 = transformed_bbox(part, placement.transform.angle_deg,
                                       placement.transform.mirror)
        top = max(top, placement.transform.dy + y1)

    return (result.sheets_used, top)


def pack(
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """Place every part, trying several insertion orders and keeping the best."""
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

    best_order = list(by_area)
    best = _pack_once(best_order, material, config, oracle_factory)
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
        candidate = _pack_once(candidate_order, material, config, oracle_factory)
        candidate_cost = layout_cost(candidate, parts)
        if candidate_cost < best_cost:
            best, best_cost, best_order = candidate, candidate_cost, candidate_order

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
    if layout_cost(redone, parts)[1] >= layout_cost(result, parts)[1]:
        return result

    kept = [p for p in result.placements if p.sheet != last]
    moved = [Placement(p.part_id, last, p.transform) for p in redone.placements]

    sheet_area = material.sheet_w * material.sheet_h
    result.placements = kept + moved
    result.utilization[last] = sum(p.area for p in on_last) / sheet_area
    return result
