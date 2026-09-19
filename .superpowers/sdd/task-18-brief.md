### Task 18: `RasterOracle` e integración (`engine/raster/oracle.py`)

**Files:**
- Create: `src/nesting/engine/raster/oracle.py`
- Modify: `bench/run_bench.py` — correr los dos motores y comparar
- Modify: `src/nesting/cli.py` — usar `RasterOracle` en vez de `ShelfOracle`
- Test: `tests/engine/raster/test_raster_oracle.py`

**Interfaces:**
- Consumes: `MaskCache` (Task 15), `feasible_positions` (Task 16), `contact_band`/`best_position` (Task 17), `NestConfig`/`Oracle` (Task 11)
- Produces: `RasterOracle` — implementa el protocolo `Oracle`, más `CONTACT_BAND_MM = 3.0`

**El margen de placa desaparece como código.** La grilla cubre **solo el área útil** (la placa erosionada por `margin`). Como `feasible_positions` usa correlación `"valid"`, toda posición que devuelve tiene la máscara entera adentro de la grilla — o sea, adentro del área útil. El borde queda garantizado por la forma del arreglo.

**Conversión píxel ↔ mundo**, la única del motor:

```
dx = margin + px·res − origin.x          px = round((dx − margin + origin.x) / res)
dy = margin + py·res − origin.y          py = round((dy − margin + origin.y) / res)
```

**Región activa (spec §5.3).** La búsqueda se limita a las filas `[0 : frontera + alto_máscara]`, donde `frontera` es la fila más alta con material. Es seguro: cualquier posición por encima de esa franja está sobre placa vacía, así que tiene contacto cero y peor puntaje de abajo-izquierda que las de adentro. Si ahí no entra nada, se reintenta sobre la placa completa. Con la placa casi vacía —el caso de las primeras piezas— las correlaciones son diminutas.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/raster/test_raster_oracle.py`:

```python
import math
from dataclasses import replace

import pytest

from nesting.engine.oracle import NestConfig, Weights
from nesting.engine.packer import pack
from nesting.engine.raster.oracle import RasterOracle
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.geometry.verify import verify
from nesting.model.entities import Transform
from nesting.model.material import Material
from nesting.model.part import Part, Placement

MATERIAL = Material("test", 1000.0, 1000.0, grain_tolerance=180.0)
CONFIG = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=False, resolution=2.0)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def circle_part(part_id, radius, segments=48):
    ring = tuple(
        (radius * math.cos(2 * math.pi * i / segments),
         radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    )
    return Part(part_id, ring, (), (part_id,))


def ring_part(part_id, outer, inner):
    return Part(
        part_id,
        ((0.0, 0.0), (outer, 0.0), (outer, outer), (0.0, outer)),
        ((((outer - inner) / 2, (outer - inner) / 2),
          ((outer + inner) / 2, (outer - inner) / 2),
          ((outer + inner) / 2, (outer + inner) / 2),
          ((outer - inner) / 2, (outer + inner) / 2)),),
        (part_id,),
    )


def test_the_first_part_lands_near_the_bottom_left_margin():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    assert x == pytest.approx(20.0, abs=CONFIG.resolution)
    assert y == pytest.approx(20.0, abs=CONFIG.resolution)


def test_best_placement_does_not_mutate_state():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)
    assert oracle.best_placement(part, 0.0, False) == oracle.best_placement(part, 0.0, False)


def test_a_placed_part_blocks_its_own_position():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)
    part = rect_part(0, 100.0, 50.0)

    x, y, _ = oracle.best_placement(part, 0.0, False)
    oracle.place(part, 0.0, False, x, y)
    second = oracle.best_placement(part, 0.0, False)

    assert second is not None
    assert (second[0], second[1]) != (x, y)


def test_returns_none_when_the_part_cannot_fit():
    oracle = RasterOracle()
    oracle.reset(200.0, 200.0, CONFIG)
    assert oracle.best_placement(rect_part(0, 500.0, 500.0), 0.0, False) is None


def test_a_full_layout_passes_the_verifier():
    oracle = RasterOracle()
    oracle.reset(1000.0, 1000.0, CONFIG)

    parts = [rect_part(i, 140.0, 90.0) for i in range(20)]
    placements = []
    for part in parts:
        spot = oracle.best_placement(part, 0.0, False)
        if spot is None:
            continue
        x, y, _ = spot
        oracle.place(part, 0.0, False, x, y)
        placements.append(Placement(part.id, 0, Transform(0.0, False, x, y)))

    assert len(placements) >= 15
    assert verify(parts, placements, 1000.0, 1000.0, sep=CONFIG.sep, margin=CONFIG.margin) == []


def test_rotated_and_mirrored_layouts_pass_the_verifier():
    config = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=True, resolution=2.0)
    parts = [rect_part(i, 200.0, 70.0) for i in range(12)]
    result = pack(parts, MATERIAL, config, RasterOracle)

    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=config.sep, margin=config.margin) == []


def test_curved_parts_pass_the_verifier():
    parts = [circle_part(i, 90.0) for i in range(12)]
    result = pack(parts, MATERIAL, CONFIG, RasterOracle)
    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=CONFIG.sep, margin=CONFIG.margin) == []


def test_a_small_part_is_nested_inside_a_big_hole():
    """La ganancia de la spec 5.2, verificada end to end."""
    parts = [ring_part(0, 600.0, 400.0), rect_part(1, 200.0, 200.0)]
    result = pack(parts, MATERIAL, CONFIG, RasterOracle)

    assert result.sheets_used == 1
    assert len(result.placements) == 2
    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=CONFIG.sep, margin=CONFIG.margin) == []

    # La pieza chica tiene que haber caido adentro del agujero de la grande.
    from nesting.geometry.verify import placed_polygon
    big = placed_polygon(parts[0], result.placements[0].transform)
    small = placed_polygon(parts[1], result.placements[1].transform)
    hole = big.interiors[0]
    from shapely.geometry import Polygon
    assert Polygon(hole).contains(small)


def test_the_raster_engine_beats_the_shelf_engine_on_circles():
    """La prueba de que el hito 3 valio la pena, en numeros."""
    parts = [circle_part(i, 120.0) for i in range(14)]
    config = NestConfig(sep=8.0, margin=15.0, angles=(0.0,), mirror=False, resolution=2.0)

    shelf = pack(parts, MATERIAL, config, ShelfOracle)
    raster = pack(parts, MATERIAL, config, RasterOracle)

    assert raster.total_utilization > shelf.total_utilization * 1.15


def test_the_raster_engine_is_deterministic():
    parts = [rect_part(i, 140.0, 90.0) for i in range(10)]
    first = pack(parts, MATERIAL, CONFIG, RasterOracle)
    second = pack(parts, MATERIAL, CONFIG, RasterOracle)
    assert first.placements == second.placements


def test_contact_weight_produces_tighter_packing_than_bottom_left_alone():
    parts = [circle_part(i, 100.0) for i in range(12)]
    base = NestConfig(sep=8.0, margin=15.0, angles=(0.0,), mirror=False, resolution=2.0)

    bl_only = pack(parts, MATERIAL, replace(base, weights=Weights(1.0, 0.0)), RasterOracle)
    with_contact = pack(parts, MATERIAL, replace(base, weights=Weights(1.0, 1.0)),
                        RasterOracle)

    assert with_contact.total_utilization >= bl_only.total_utilization


def test_a_finer_resolution_does_not_break_the_verifier():
    parts = [circle_part(i, 80.0) for i in range(8)]
    config = NestConfig(sep=6.0, margin=10.0, angles=(0.0,), mirror=False, resolution=0.5)
    result = pack(parts, MATERIAL, config, RasterOracle)
    assert verify(parts, result.placements, MATERIAL.sheet_w, MATERIAL.sheet_h,
                  sep=config.sep, margin=config.margin) == []
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/raster/test_raster_oracle.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine.raster.oracle'`.

- [ ] **Step 3: Escribir el oráculo raster**

Archivo `src/nesting/engine/raster/oracle.py`:

```python
"""The real nesting engine: bitmap collision, FFT search, contact scoring.

Implements the same three-method `Oracle` protocol as the throwaway shelf
engine, so the packer, the CLI, the bench and the verifier are unchanged.
"""

import math

import numpy as np

from nesting.engine.oracle import NestConfig
from nesting.engine.raster.masks import MaskCache, PartMasks
from nesting.engine.raster.scoring import best_position, contact_band
from nesting.engine.raster.search import feasible_positions
from nesting.model.part import Part

CONTACT_BAND_MM = 3.0
"""How far beyond the clearance halo the contact term looks for material."""


class RasterOracle:
    """Collision by bitmap overlap, position search by cross-correlation."""

    def __init__(self, cache: MaskCache | None = None) -> None:
        self._cache = cache if cache is not None else MaskCache()
        self._config = NestConfig()
        self._sheet = np.zeros((0, 0), dtype=bool)
        self._frontier = 0
        """Highest row index reached by placed material, for the active region."""

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._config = config
        resolution = config.resolution

        # The grid covers ONLY the usable area, so "valid" correlation positions
        # are inside the margin by construction. No bounds code anywhere.
        usable_w = sheet_w - 2 * config.margin
        usable_h = sheet_h - 2 * config.margin
        cols = max(0, math.floor(usable_w / resolution))
        rows = max(0, math.floor(usable_h / resolution))

        self._sheet = np.zeros((rows, cols), dtype=bool)
        self._frontier = 0

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        masks = self._masks(part, angle, mirror)
        height = masks.clearance.shape[0]

        result = self._search(masks, limit_rows=self._frontier + height)
        if result is None and self._frontier + height < self._sheet.shape[0]:
            result = self._search(masks, limit_rows=self._sheet.shape[0])
        if result is None:
            return None

        px, py, score = result
        dx, dy = masks.translation_for(px, py)
        return (dx + self._config.margin, dy + self._config.margin, score)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        masks = self._masks(part, angle, mirror)
        px, py = self._to_pixels(masks, x, y)
        height, width = masks.occupied.shape

        self._sheet[py:py + height, px:px + width] |= masks.occupied
        self._frontier = max(self._frontier, py + height)

    def _search(self, masks: PartMasks, limit_rows: int) -> tuple[int, int, float] | None:
        """Search within the first `limit_rows` rows of the sheet."""
        rows = min(max(limit_rows, masks.clearance.shape[0]), self._sheet.shape[0])
        window = self._sheet[:rows]

        feasible = feasible_positions(window, masks.clearance)
        if feasible.size == 0:
            return None

        extra_px = max(1, round(CONTACT_BAND_MM / self._config.resolution))
        band = contact_band(masks.clearance, extra_px)
        return best_position(feasible, window, band, self._config.weights)

    def _masks(self, part: Part, angle: float, mirror: bool) -> PartMasks:
        return self._cache.get(
            part, angle, mirror, self._config.resolution, self._config.sep
        )

    def _to_pixels(self, masks: PartMasks, x: float, y: float) -> tuple[int, int]:
        """Inverse of `translation_for`, plus the margin offset."""
        resolution = self._config.resolution
        px = round((x - self._config.margin + masks.origin[0]) / resolution)
        py = round((y - self._config.margin + masks.origin[1]) / resolution)
        return (px, py)
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/raster/test_raster_oracle.py -v`
Esperado: `12 passed`.

- [ ] **Step 5: Conectar el motor real a la CLI**

En `src/nesting/cli.py`, reemplazar el import:

```python
from nesting.engine.raster.oracle import RasterOracle
```

(borrando `from nesting.engine.shelf_oracle import ShelfOracle`), y en la llamada a `pack`:

```python
        result = pack(parts, material, config, RasterOracle)
```

Además, agregar el flag de resolución a `_parse_args`:

```python
    parser.add_argument("--resolucion", type=float, default=1.0, dest="resolucion",
                        help="resolucion del raster, en mm por pixel")
```

y pasarlo al `NestConfig`:

```python
    config = NestConfig(
        sep=args.sep,
        margin=args.borde,
        angles=angles,
        mirror=not args.sin_espejo,
        resolution=args.resolucion,
    )
```

- [ ] **Step 6: Hacer que el banco compare los dos motores**

En `bench/run_bench.py`, agregar el import:

```python
from nesting.engine.raster.oracle import RasterOracle
```

y reemplazar el bucle de `main` por:

```python
    engines = [("shelf", ShelfOracle), ("raster", RasterOracle)]

    for path in files:
        baseline = None
        for name, factory in engines:
            result = run_one(path, material, config, factory, name, args.copias)
            flag = "  VIOLACIONES!" if result.violations else ""
            if name == "shelf":
                baseline = result.total_utilization
                delta = ""
            else:
                delta = f"  (+{(result.total_utilization - baseline) * 100:.1f} pts)"
            print(
                f"{result.name:<24}{result.engine:<10}{result.parts:>7}{result.sheets:>8}"
                f"{result.total_utilization * 100:>8.1f}%{result.seconds:>8.1f}{delta}{flag}"
            )
```

- [ ] **Step 7: Correr el banco y anotar la mejora**

```bash
.venv/bin/python bench/run_bench.py
```

Esperado: dos filas por archivo. La fila `raster` tiene que mostrar **mayor aprovechamiento** que la fila `shelf`, y **ninguna** con la marca `VIOLACIONES!`.
**Anotar ambos números: son la evidencia de que el hito 3 sirvió.**

- [ ] **Step 8: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: todos los tests pasan, incluidos los de `tests/test_cli.py`, que ahora ejercitan el motor raster sin haber cambiado.

- [ ] **Step 9: Commit**

```bash
git add src/nesting/engine/raster/oracle.py src/nesting/cli.py bench/run_bench.py tests/engine/raster/test_raster_oracle.py
git commit -m "feat: motor raster conectado detras de la interfaz Oracle"
```

**Hito 3 completo.** El motor real está adentro y la mejora está medida. Que los tests de la CLI y del packer pasaran sin tocarse es la prueba de que la costura de la spec §3.2 funciona: el día que exista un motor NFP, entra por el mismo lugar.

---

# Hito 4 — El producto

---

