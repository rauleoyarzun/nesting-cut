### Task 12: Pipeline de preparación y packer (`pipeline.py`, `engine/packer.py`)

**Files:**
- Create: `src/nesting/pipeline.py`
- Create: `src/nesting/engine/packer.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/engine/test_packer.py`

**Interfaces:**
- Consumes: `Drawing` (Task 8), `flatten` (Task 4), `chain_contours` (Task 5), `build_parts` (Task 6), `Oracle`/`NestConfig` (Task 11), `Material`/`allowed_angles` (Task 10)
- Produces:
  - `pipeline.prepare_parts(drawing, flatten_tol=0.2, chain_tol=0.1) -> tuple[list[Part], list[str]]` — piezas y avisos
  - `pipeline.OpenContourError(Exception)`
  - `packer.PackResult(placements, sheets_used, utilization, total_utilization, unplaced, seconds)`
  - `packer.PartTooLargeError(Exception)`
  - `packer.replicate(parts, copies) -> list[Part]`
  - `packer.orientations(material, config) -> list[tuple[float, bool]]`
  - `packer.pack(parts, material, config, oracle_factory) -> PackResult`

**`prepare_parts` es el puente entre `io/` y el motor:** aplana cada entidad, encadena los tramos en contornos cerrados y arma el árbol de contención. Si algún contorno no cierra, **falla** con las coordenadas del hueco y la distancia que falta (spec §6.3) — no sigue con geometría incompleta.

**`pack` es la estrategia, y es agnóstica al motor.** Recibe un `oracle_factory` (un invocable sin argumentos que devuelve un `Oracle` nuevo), así que sirve igual con `ShelfOracle` hoy y con `RasterOracle` en el hito 3, sin cambiar una línea.

**Una sola pasada por placa alcanza.** Las piezas van ordenadas por área descendente; colocar más piezas solo reduce el espacio libre, así que una pieza que no entró no va a entrar después en esa misma placa. Si una pieza no entra en una placa **vacía**, es más grande que el área útil: `PartTooLargeError` con nombre y medidas.

- [ ] **Step 1: Escribir los tests que fallan**

Archivo `tests/test_pipeline.py`:

```python
import pytest

from nesting.io.dxf_reader import Drawing
from nesting.model.entities import Arc, Circle, Line, Style
from nesting.pipeline import OpenContourError, prepare_parts

STYLE = Style(aci=7, rgb=(255, 255, 255), layer="0")


def square_lines(x0, y0, side):
    c = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)]
    return [Line(c[i], c[(i + 1) % 4], STYLE) for i in range(4)]


def test_four_loose_lines_become_one_part():
    parts, warnings = prepare_parts(Drawing(entities=square_lines(0, 0, 100)))
    assert len(parts) == 1
    assert parts[0].holes == ()
    assert warnings == []


def test_a_circle_becomes_one_part():
    parts, _ = prepare_parts(Drawing(entities=[Circle((0.0, 0.0), 50.0, STYLE)]))
    assert len(parts) == 1
    assert parts[0].outer_area == pytest.approx(3.14159 * 50.0**2, rel=1e-3)


def test_a_circle_inside_a_square_becomes_a_hole():
    entities = square_lines(0, 0, 200) + [Circle((100.0, 100.0), 30.0, STYLE)]
    parts, _ = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    assert len(parts[0].holes) == 1
    assert parts[0].area < parts[0].outer_area


def test_two_arcs_forming_a_circle_chain_together():
    entities = [
        Arc((0.0, 0.0), 50.0, 0.0, 180.0, STYLE),
        Arc((0.0, 0.0), 50.0, 180.0, 360.0, STYLE),
    ]
    parts, _ = prepare_parts(Drawing(entities=entities))
    assert len(parts) == 1


def test_an_open_contour_raises_with_the_gap_size():
    entities = square_lines(0, 0, 100)[:3]   # falta un lado
    with pytest.raises(OpenContourError) as info:
        prepare_parts(Drawing(entities=entities))
    message = str(info.value)
    assert "100" in message, "informa el tamano del hueco"
    assert "--tol-cierre" in message


def test_duplicate_lines_produce_a_warning_but_still_work():
    entities = square_lines(0, 0, 100) + [square_lines(0, 0, 100)[0]]
    parts, warnings = prepare_parts(Drawing(entities=entities))

    assert len(parts) == 1
    assert any("duplicad" in w for w in warnings)


def test_reader_warnings_are_carried_through():
    drawing = Drawing(entities=square_lines(0, 0, 100), warnings=["se ignoraron 1 TEXT"])
    _, warnings = prepare_parts(drawing)
    assert "se ignoraron 1 TEXT" in warnings


def test_entity_ids_point_back_into_the_drawing():
    drawing = Drawing(entities=square_lines(0, 0, 100))
    parts, _ = prepare_parts(drawing)
    assert sorted(parts[0].entity_ids) == [0, 1, 2, 3]


def test_an_empty_drawing_produces_no_parts():
    parts, _ = prepare_parts(Drawing(entities=[]))
    assert parts == []
```

Archivo `tests/engine/test_packer.py`:

```python
import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    PartTooLargeError,
    orientations,
    pack,
    replicate,
)
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.model.material import Material
from nesting.model.part import Part

FREE = Material("mdf", 1000.0, 1000.0, grain_tolerance=180.0)
GRAIN = Material("multilam", 1000.0, 1000.0, grain_tolerance=5.0)
CONFIG = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=False,
                    effort="rapido")
"""Esfuerzo fijo en una pasada golosa: estos tests verifican la estrategia base,
no la busqueda con reintentos que agrega la Task 19."""


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def test_replicate_renumbers_ids_and_keeps_entity_ids():
    parts = [rect_part(0, 10.0, 10.0), rect_part(1, 20.0, 20.0)]
    copies = replicate(parts, 3)

    assert len(copies) == 6
    assert [p.id for p in copies] == [0, 1, 2, 3, 4, 5]
    assert copies[0].entity_ids == copies[2].entity_ids == copies[4].entity_ids


def test_replicate_with_one_copy_is_a_no_op():
    parts = [rect_part(0, 10.0, 10.0)]
    assert [p.id for p in replicate(parts, 1)] == [0]


def test_replicate_rejects_a_non_positive_count():
    with pytest.raises(ValueError):
        replicate([rect_part(0, 1.0, 1.0)], 0)


def test_orientations_without_mirroring():
    config = NestConfig(angles=(0.0, 90.0, 180.0, 270.0), mirror=False)
    assert orientations(FREE, config) == [
        (0.0, False), (90.0, False), (180.0, False), (270.0, False)
    ]


def test_orientations_with_mirroring_doubles_the_list():
    config = NestConfig(angles=(0.0, 90.0), mirror=True)
    assert orientations(FREE, config) == [
        (0.0, False), (90.0, False), (0.0, True), (90.0, True)
    ]


def test_grain_constraint_filters_the_orientations():
    config = NestConfig(angles=(0.0, 90.0, 180.0, 270.0), mirror=False)
    assert orientations(GRAIN, config) == [(0.0, False), (180.0, False)]


def test_a_single_part_fits_on_one_sheet():
    parts = [rect_part(0, 100.0, 100.0)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert len(result.placements) == 1
    assert result.unplaced == []
    assert result.seconds >= 0.0


def test_parts_spill_onto_a_second_sheet():
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)

    assert result.sheets_used >= 2
    assert result.unplaced == []
    assert {p.sheet for p in result.placements} == set(range(result.sheets_used))


def test_a_part_bigger_than_the_sheet_is_reported():
    parts = [rect_part(0, 5000.0, 5000.0)]
    with pytest.raises(PartTooLargeError) as info:
        pack(parts, FREE, CONFIG, ShelfOracle)
    assert "5000" in str(info.value)


def test_bigger_parts_are_placed_first():
    parts = [rect_part(0, 50.0, 50.0), rect_part(1, 400.0, 400.0)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)
    assert result.placements[0].part_id == 1


def test_utilisation_is_reported_per_sheet_and_in_total():
    parts = [rect_part(i, 300.0, 300.0) for i in range(4)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)

    assert len(result.utilization) == result.sheets_used
    assert all(0.0 < u <= 1.0 for u in result.utilization)
    assert 0.0 < result.total_utilization <= 1.0


def test_the_result_always_passes_the_verifier():
    """El invariante central: ningun motor puede producir una salida invalida."""
    parts = [rect_part(i, 180.0, 120.0) for i in range(20)]
    result = pack(parts, FREE, CONFIG, ShelfOracle)

    violations = verify(
        parts, result.placements, FREE.sheet_w, FREE.sheet_h,
        sep=CONFIG.sep, margin=CONFIG.margin,
    )
    assert violations == []


def test_packing_is_deterministic():
    parts = [rect_part(i, 180.0, 120.0) for i in range(10)]
    first = pack(parts, FREE, CONFIG, ShelfOracle)
    second = pack(parts, FREE, CONFIG, ShelfOracle)
    assert first.placements == second.placements


def test_an_empty_part_list_produces_an_empty_result():
    result = pack([], FREE, CONFIG, ShelfOracle)
    assert result.sheets_used == 0
    assert result.placements == []
    assert result.total_utilization == 0.0
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/pytest tests/test_pipeline.py tests/engine/test_packer.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.pipeline'`.

- [ ] **Step 3: Escribir el pipeline de preparación**

Archivo `src/nesting/pipeline.py`:

```python
"""From a freshly read drawing to the parts the engine will place.

Flatten every entity, chain the loose runs into closed contours, then resolve
containment. This is where a dirty export stops being geometry soup and becomes
a list of parts - or fails loudly enough that the user can go fix the drawing.
"""

from nesting.geometry.chaining import chain_contours
from nesting.geometry.flatten import flatten
from nesting.geometry.nesting_tree import build_parts
from nesting.io.dxf_reader import Drawing
from nesting.model.part import Part

DEFAULT_FLATTEN_TOL = 0.2
"""Millimetres. Well below the raster resolution, so it never dominates error."""

DEFAULT_CHAIN_TOL = 0.1
"""Millimetres. Corel exports routinely leave gaps of a few microns."""


class OpenContourError(Exception):
    """A run of segments never closed, so it cannot become a part."""


def prepare_parts(
    drawing: Drawing,
    flatten_tol: float = DEFAULT_FLATTEN_TOL,
    chain_tol: float = DEFAULT_CHAIN_TOL,
) -> tuple[list[Part], list[str]]:
    """Turn a drawing into parts, returning them alongside any warnings."""
    warnings = list(drawing.warnings)

    segments = [
        (flatten(entity, flatten_tol), index)
        for index, entity in enumerate(drawing.entities)
    ]

    contours, open_chains, duplicates = chain_contours(segments, chain_tol)

    if duplicates:
        warnings.append(
            f"se descartaron {duplicates} entidades duplicadas o superpuestas"
        )

    if open_chains:
        worst = min(open_chains, key=lambda c: c.gap)
        raise OpenContourError(
            f"{len(open_chains)} contorno(s) no cierran. "
            f"El mas cercano a cerrar arranca en "
            f"({worst.points[0][0]:.3f}, {worst.points[0][1]:.3f}) y termina en "
            f"({worst.points[-1][0]:.3f}, {worst.points[-1][1]:.3f}), "
            f"con un hueco de {worst.gap:.3f} mm. "
            f"Revise el dibujo, o afloje la tolerancia con --tol-cierre."
        )

    return build_parts(contours), warnings
```

- [ ] **Step 4: Escribir el packer**

Archivo `src/nesting/engine/packer.py`:

```python
"""Strategy: what order, which rotations, and when to open a new sheet.

Knows nothing about how placement is computed. It talks to an `Oracle`, so the
same code drives the throwaway shelf engine and the real raster engine.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from nesting.engine.oracle import NestConfig, Oracle, transformed_bbox
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
    unplaced: list[int] = field(default_factory=list)
    seconds: float = 0.0


def replicate(parts: Sequence[Part], copies: int) -> list[Part]:
    """Repeat every part `copies` times, renumbering ids.

    The copies keep the original `entity_ids`, so they all draw the same source
    geometry at different places.
    """
    if copies < 1:
        raise ValueError(f"la cantidad de copias debe ser al menos 1, se recibio {copies}")

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


def pack(
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """Place every part, opening new sheets as needed."""
    started = time.perf_counter()
    result = PackResult()

    if not parts:
        result.seconds = time.perf_counter() - started
        return result

    choices = orientations(material, config)
    remaining = sorted(parts, key=lambda p: p.area, reverse=True)
    sheet_area = material.sheet_w * material.sheet_h
    placed_area_per_sheet: list[float] = []

    sheet = 0
    while remaining:
        oracle = oracle_factory()
        oracle.reset(material.sheet_w, material.sheet_h, config)

        still_pending: list[Part] = []
        placed_area = 0.0

        for part in remaining:
            spot = _best_over_orientations(oracle, part, choices)
            if spot is None:
                still_pending.append(part)
                continue
            angle, mirror, x, y = spot
            oracle.place(part, angle, mirror, x, y)
            result.placements.append(Placement(part.id, sheet, Transform(angle, mirror, x, y)))
            placed_area += part.area

        if placed_area == 0.0:
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
    """Report the smallest footprint the part can take, against the usable area."""
    widths, heights = [], []
    for angle, mirror in choices:
        x0, y0, x1, y1 = transformed_bbox(part, angle, mirror)
        widths.append(x1 - x0)
        heights.append(y1 - y0)

    usable_w = material.sheet_w - 2 * config.margin
    usable_h = material.sheet_h - 2 * config.margin
    raise PartTooLargeError(
        f"la pieza {part.id} no entra en una placa vacia: mide al menos "
        f"{min(widths):.1f} x {min(heights):.1f} mm en su mejor orientacion, "
        f"y el area util de la placa {material.name} es "
        f"{usable_w:.1f} x {usable_h:.1f} mm (margen {config.margin} mm)."
    )
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `.venv/bin/pytest tests/test_pipeline.py tests/engine/test_packer.py -v`
Esperado: `23 passed`.

- [ ] **Step 6: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos en verde.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/pipeline.py src/nesting/engine/packer.py tests/test_pipeline.py tests/engine/test_packer.py
git commit -m "feat: pipeline de preparacion y estrategia de empaquetado multi-placa"
```

---

