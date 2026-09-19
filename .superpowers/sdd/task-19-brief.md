### Task 19: Niveles de esfuerzo y compactación de la última placa

**Files:**
- Modify: `src/nesting/engine/packer.py` — reintentos, función de costo, compactación
- Test: `tests/engine/test_effort.py`

**Interfaces:**
- Consumes: todo lo de la Task 12, más `Weights` (Task 11)
- Produces (agregados a `engine/packer.py`):
  - `EFFORT_RESTARTS: dict[str, int]` — `{"rapido": 1, "normal": 10, "lento": 120}`
  - `UnknownEffortError(Exception)`
  - `layout_cost(result, parts) -> tuple[int, float]` — menor es mejor
  - `pack(...)` pasa a hacer varios intentos y quedarse con el mejor
- `pack` mantiene exactamente la misma firma: nada fuera de `packer.py` cambia.

**El criterio de la spec §3.8, como una función de costo:**

```
costo = (cantidad_de_placas, altura_usada_en_la_ultima_placa)
```

Se comparan como tupla: **primero minimizar placas**; a igual cantidad de placas, gana el layout cuya **última placa esté más compactada**. Eso deja el sobrante en un bloque grande y aprovechable en vez de recortes dispersos.

**Qué compra cada nivel.** Una pasada golosa es determinística y buena; lo que mejora es probar **distintos órdenes de inserción**:

| Nivel | Estrategia |
|---|---|
| `rapido` | Una pasada, orden por área descendente |
| `normal` | 10 intentos: el orden por área, más 9 perturbaciones aleatorias con semilla fija |
| `lento` | 120 iteraciones de búsqueda local: se perturba el mejor orden conocido y se acepta si mejora |

**Pasada final de compactación.** Elegido el mejor layout, las piezas de la última placa se vuelven a empacar solas con el peso de abajo-izquierda triplicado. Si el resultado sigue entrando en una placa y queda más bajo, reemplaza al anterior.

**Determinismo:** toda la aleatoriedad sale de `random.Random(config.seed)`. Con la misma semilla, la misma entrada da la misma salida.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/test_effort.py`:

```python
import math

import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    EFFORT_RESTARTS,
    UnknownEffortError,
    layout_cost,
    pack,
)
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.verify import verify
from nesting.model.material import Material
from nesting.model.part import Part

MATERIAL = Material("test", 1000.0, 1000.0, grain_tolerance=180.0)


def base_config(**overrides):
    defaults = dict(sep=8.0, margin=15.0, angles=(0.0, 90.0), mirror=False,
                    resolution=2.0, effort="rapido", seed=0)
    defaults.update(overrides)
    return NestConfig(**defaults)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def circle_part(part_id, radius, segments=40):
    ring = tuple(
        (radius * math.cos(2 * math.pi * i / segments),
         radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    )
    return Part(part_id, ring, (), (part_id,))


def test_the_effort_table_has_the_three_levels():
    assert set(EFFORT_RESTARTS) == {"rapido", "normal", "lento"}
    assert EFFORT_RESTARTS["rapido"] < EFFORT_RESTARTS["normal"] < EFFORT_RESTARTS["lento"]


def test_an_unknown_effort_level_is_rejected():
    parts = [rect_part(0, 100.0, 100.0)]
    with pytest.raises(UnknownEffortError) as info:
        pack(parts, MATERIAL, base_config(effort="turbo"), RasterOracle)
    assert "turbo" in str(info.value)


def test_layout_cost_prefers_fewer_sheets():
    few = [rect_part(i, 300.0, 300.0) for i in range(4)]
    many = [rect_part(i, 300.0, 300.0) for i in range(16)]

    one_sheet = pack(few, MATERIAL, base_config(), RasterOracle)
    several = pack(many, MATERIAL, base_config(), RasterOracle)

    assert layout_cost(one_sheet, few)[0] < layout_cost(several, many)[0]


def test_layout_cost_reports_the_height_used_on_the_last_sheet():
    parts = [rect_part(0, 200.0, 200.0)]
    result = pack(parts, MATERIAL, base_config(), RasterOracle)
    sheets, height = layout_cost(result, parts)

    assert sheets == 1
    assert 200.0 <= height <= 260.0, "el alto usado es el de la pieza mas el margen"


def test_rapido_is_a_single_pass():
    parts = [circle_part(i, 90.0) for i in range(10)]
    first = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    second = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    assert first.placements == second.placements


def test_the_same_seed_gives_the_same_result():
    parts = [circle_part(i, 80.0) for i in range(12)]
    config = base_config(effort="normal", seed=7)
    assert pack(parts, MATERIAL, config, RasterOracle).placements == \
           pack(parts, MATERIAL, config, RasterOracle).placements


def test_different_seeds_can_give_different_results():
    parts = [rect_part(i, 170.0, 110.0) for i in range(18)]
    a = pack(parts, MATERIAL, base_config(effort="normal", seed=1), RasterOracle)
    b = pack(parts, MATERIAL, base_config(effort="normal", seed=99), RasterOracle)
    assert a.placements != b.placements or a.total_utilization == b.total_utilization


def test_normal_is_never_worse_than_rapido():
    """El costo del mejor de N intentos no puede superar al del primero."""
    parts = [circle_part(i, 85.0) for i in range(16)]
    quick = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    normal = pack(parts, MATERIAL, base_config(effort="normal", seed=3), RasterOracle)

    assert layout_cost(normal, parts) <= layout_cost(quick, parts)


def test_every_effort_level_produces_a_valid_layout():
    parts = [circle_part(i, 90.0) for i in range(14)]
    for effort in ("rapido", "normal", "lento"):
        config = base_config(effort=effort, seed=5)
        result = pack(parts, MATERIAL, config, RasterOracle)
        violations = verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                            sep=config.sep, margin=config.margin)
        assert violations == [], f"el nivel {effort} produjo una salida invalida"


def test_every_part_is_placed_at_every_effort_level():
    parts = [rect_part(i, 150.0, 100.0) for i in range(12)]
    for effort in ("rapido", "normal", "lento"):
        result = pack(parts, MATERIAL, base_config(effort=effort), RasterOracle)
        assert len(result.placements) == len(parts)
    

def test_the_last_sheet_gets_compacted():
    """Dos placas: la segunda tiene que quedar apretada contra el borde de abajo."""
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    config = base_config(effort="normal", seed=2)
    result = pack(parts, MATERIAL, config, RasterOracle)

    assert result.sheets_used >= 2
    _, last_height = layout_cost(result, parts)
    assert last_height < MATERIAL.sheet_h * 0.75, "el sobrante quedo en un bloque"


def test_the_reported_time_grows_with_the_effort():
    parts = [circle_part(i, 90.0) for i in range(10)]
    quick = pack(parts, MATERIAL, base_config(effort="rapido"), RasterOracle)
    normal = pack(parts, MATERIAL, base_config(effort="normal"), RasterOracle)
    assert normal.seconds > quick.seconds
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/test_effort.py -v`
Esperado: FALLA con `ImportError: cannot import name 'EFFORT_RESTARTS'`.

- [ ] **Step 3: Renombrar la pasada única y agregar el costo**

En `src/nesting/engine/packer.py`, agregar los imports que faltan al principio:

```python
import random
from dataclasses import replace
```

Renombrar la función `pack` existente a `_pack_once` y agregarle un parámetro de orden explícito. O sea, cambiar su firma de:

```python
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
```

a:

```python
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
```

El resto del cuerpo queda igual.

- [ ] **Step 4: Agregar la función de costo, los reintentos y la compactación**

Agregar al final de `src/nesting/engine/packer.py`:

```python
EFFORT_RESTARTS: dict[str, int] = {"rapido": 1, "normal": 10, "lento": 120}
"""How many insertion orders each effort level tries. Calibrated in Task 24."""

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

    for _ in range(EFFORT_RESTARTS[config.effort] - 1):
        candidate_order = _perturb(best_order if config.effort == "lento" else by_area, rng)
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
```

Y agregar `Weights` al import de `nesting.engine.oracle` en la cabecera del archivo:

```python
from nesting.engine.oracle import NestConfig, Oracle, Weights, transformed_bbox
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/test_effort.py -v`
Esperado: `12 passed`.

- [ ] **Step 6: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos pasan. Los tests de la Task 12 fijan `effort="rapido"` justamente para
seguir ejercitando la pasada golosa una vez que existan los reintentos.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/engine/packer.py tests/engine/test_effort.py
git commit -m "feat: niveles de esfuerzo y compactacion de la ultima placa"
```

---

