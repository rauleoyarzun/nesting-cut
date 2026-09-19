### Task 15: Rasterizado de piezas (`engine/raster/masks.py`)

**Files:**
- Create: `src/nesting/engine/raster/__init__.py`
- Create: `src/nesting/engine/raster/masks.py`
- Test: `tests/engine/raster/test_masks.py`

**Interfaces:**
- Consumes: `Part` (Task 6), `Transform`/`apply_points` (Tasks 2-3)
- Produces:
  - `PartMasks(occupied: np.ndarray, clearance: np.ndarray, origin: tuple[float, float], resolution: float)`
  - `disk_kernel(radius_px: int) -> np.ndarray`
  - `rasterize(part, angle, mirror, resolution, sep) -> PartMasks`
  - `MaskCache(max_entries=512)` con `get(part, angle, mirror, resolution, sep) -> PartMasks`

**Las dos máscaras de la spec §5.1:**

| Máscara | Qué contiene | Para qué |
|---|---|---|
| `occupied` | El material real: contorno exterior **menos** agujeros | Se estampa en la placa al colocar |
| `clearance` | `occupied` dilatada por `sep` | Se usa para **testear** colisión |

**Las dos tienen exactamente la misma forma.** `occupied` se rasteriza dentro de una grilla ya acolchada por el radio de dilatación, así que ambas se indexan igual y no hay offsets que llevar en paralelo. Esto elimina de raíz la clase de bug más común en este enfoque.

**`origin` es la coordenada en mm del píxel `[0, 0]`** suponiendo que la pieza tiene traslación cero. Para que el píxel `[0,0]` de la máscara caiga en el píxel `(px, py)` de la placa, la traslación es `dx = px·res − origin.x`, `dy = py·res − origin.y`. Esa es la única fórmula de conversión del motor y vive acá.

**Convención de índices:** `mask[fila, columna]` con la **fila creciendo con `y`**. PIL rellena polígonos en su propio espacio de índices; como se le pasan pares `(columna, fila)` construidos con `fila = (y − origin.y)/res`, el arreglo resultante ya tiene `y` creciente con la fila. No hace falta invertir nada.

**La rotación re-rasteriza desde el polígono exacto**, nunca rota el bitmap (spec §5.1). Rotar bitmaps acumula artefactos y viola la restricción de que el polígono es la fuente de verdad.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/engine/raster/test_masks.py` (crear también `tests/engine/raster/__init__.py` vacío):

```python
import numpy as np
import pytest

from nesting.engine.raster.masks import MaskCache, PartMasks, disk_kernel, rasterize
from nesting.model.part import Part

RES = 1.0


def rect_part(w, h, part_id=0):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def ring_part(outer, hole_margin, part_id=0):
    m = hole_margin
    return Part(
        part_id,
        ((0.0, 0.0), (outer, 0.0), (outer, outer), (0.0, outer)),
        (((m, m), (outer - m, m), (outer - m, outer - m), (m, outer - m)),),
        (part_id,),
    )


def test_disk_kernel_is_round_and_odd_sized():
    kernel = disk_kernel(3)
    assert kernel.shape == (7, 7)
    assert kernel[3, 3]
    assert not kernel[0, 0], "las esquinas quedan fuera del disco"


def test_disk_kernel_of_zero_radius_is_a_single_pixel():
    assert disk_kernel(0).shape == (1, 1)
    assert disk_kernel(0).all()


def test_occupied_and_clearance_have_the_same_shape():
    masks = rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=5.0)
    assert masks.occupied.shape == masks.clearance.shape


def test_occupied_area_matches_the_part_area():
    part = rect_part(100.0, 50.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)
    pixel_area = masks.occupied.sum() * RES * RES
    assert pixel_area == pytest.approx(part.area, rel=0.05)


def test_clearance_is_strictly_bigger_than_occupied():
    masks = rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=5.0)
    assert masks.clearance.sum() > masks.occupied.sum()
    assert np.all(masks.clearance | ~masks.occupied), "clearance contiene a occupied"


def test_clearance_grows_by_roughly_the_separation():
    part = rect_part(100.0, 100.0)
    masks = rasterize(part, 0.0, False, RES, sep=10.0)
    grown = masks.clearance.sum() * RES * RES
    # Un cuadrado de 100 dilatado 10 mm: 120x120 menos las esquinas redondeadas.
    assert 13000 < grown < 14400


def test_a_hole_is_not_occupied():
    part = ring_part(200.0, 50.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)
    pixel_area = masks.occupied.sum() * RES * RES
    assert pixel_area == pytest.approx(200.0**2 - 100.0**2, rel=0.05)


def test_the_centre_of_a_hole_is_free_in_both_masks():
    """La propiedad de la spec 5.2: el agujero queda disponible."""
    part = ring_part(400.0, 100.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)

    row = int((200.0 - masks.origin[1]) / RES)
    col = int((200.0 - masks.origin[0]) / RES)
    assert not masks.occupied[row, col]
    assert not masks.clearance[row, col], "el centro del agujero esta lejos de la pared"


def test_the_wall_of_a_hole_projects_clearance_inwards():
    part = ring_part(400.0, 100.0)
    masks = rasterize(part, 0.0, False, RES, sep=20.0)

    # Un punto 10 mm adentro del agujero, o sea dentro de la banda de separacion.
    row = int((110.0 - masks.origin[1]) / RES)
    col = int((200.0 - masks.origin[0]) / RES)
    assert not masks.occupied[row, col]
    assert masks.clearance[row, col]


def test_rotating_ninety_degrees_swaps_the_dimensions():
    flat = rasterize(rect_part(200.0, 50.0), 0.0, False, RES, sep=0.0)
    upright = rasterize(rect_part(200.0, 50.0), 90.0, False, RES, sep=0.0)

    assert flat.occupied.shape[1] > flat.occupied.shape[0]
    assert upright.occupied.shape[0] > upright.occupied.shape[1]


def test_rotation_preserves_the_occupied_area():
    part = rect_part(200.0, 50.0)
    areas = [
        rasterize(part, angle, False, RES, sep=0.0).occupied.sum()
        for angle in (0.0, 37.0, 90.0, 213.0)
    ]
    assert max(areas) / min(areas) < 1.1


def test_mirroring_preserves_the_occupied_area():
    part = rect_part(200.0, 50.0)
    straight = rasterize(part, 0.0, False, RES, sep=0.0).occupied.sum()
    flipped = rasterize(part, 0.0, True, RES, sep=0.0).occupied.sum()
    assert straight == pytest.approx(flipped, rel=0.02)


def test_origin_places_the_part_where_the_formula_says():
    part = rect_part(100.0, 50.0)
    masks = rasterize(part, 0.0, False, RES, sep=5.0)

    # El pixel correspondiente al punto (50, 25) del interior tiene que estar ocupado.
    row = int((25.0 - masks.origin[1]) / RES)
    col = int((50.0 - masks.origin[0]) / RES)
    assert masks.occupied[row, col]

    # Y un punto claramente afuera, no.
    row = int((-20.0 - masks.origin[1]) / RES)
    col = int((-20.0 - masks.origin[0]) / RES)
    assert not masks.occupied[row, col]


def test_a_finer_resolution_produces_a_bigger_mask():
    part = rect_part(100.0, 100.0)
    coarse = rasterize(part, 0.0, False, 2.0, sep=5.0)
    fine = rasterize(part, 0.0, False, 0.5, sep=5.0)
    assert fine.occupied.shape[0] > coarse.occupied.shape[0]


def test_the_cache_returns_the_same_object_for_the_same_key():
    cache = MaskCache()
    part = rect_part(100.0, 50.0)
    first = cache.get(part, 0.0, False, RES, 5.0)
    second = cache.get(part, 0.0, False, RES, 5.0)
    assert first is second


def test_the_cache_distinguishes_angles_and_mirroring():
    cache = MaskCache()
    part = rect_part(200.0, 50.0)
    assert cache.get(part, 0.0, False, RES, 5.0) is not cache.get(part, 90.0, False, RES, 5.0)
    assert cache.get(part, 0.0, False, RES, 5.0) is not cache.get(part, 0.0, True, RES, 5.0)


def test_the_cache_evicts_the_oldest_entry_when_full():
    cache = MaskCache(max_entries=2)
    parts = [rect_part(100.0, 50.0, part_id=i) for i in range(3)]
    first = cache.get(parts[0], 0.0, False, RES, 5.0)
    cache.get(parts[1], 0.0, False, RES, 5.0)
    cache.get(parts[2], 0.0, False, RES, 5.0)
    assert cache.get(parts[0], 0.0, False, RES, 5.0) is not first


def test_masks_are_boolean_arrays():
    masks = rasterize(rect_part(100.0, 50.0), 0.0, False, RES, sep=5.0)
    assert masks.occupied.dtype == np.bool_
    assert masks.clearance.dtype == np.bool_
    assert isinstance(masks, PartMasks)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/engine/raster/test_masks.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.engine.raster'`.

- [ ] **Step 3: Escribir el rasterizador**

Archivo `src/nesting/engine/raster/__init__.py`: vacío.

Archivo `src/nesting/engine/raster/masks.py`:

```python
"""Turn an exact polygon into the two bitmaps the collision test needs.

The polygon stays the source of truth: these masks are a derived cache, rebuilt
from the polygon at every angle rather than rotated as images, which would
accumulate artefacts and quietly drift from the real geometry.
"""

import math
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation

from nesting.geometry.transform import apply_points
from nesting.model.entities import Point, Transform
from nesting.model.part import Part


@dataclass(frozen=True)
class PartMasks:
    """The material footprint and its clearance halo, on one shared grid."""

    occupied: np.ndarray
    """True where there is real material. Stamped onto the sheet when placed."""

    clearance: np.ndarray
    """`occupied` dilated by the separation. Used to test collisions."""

    origin: Point
    """World coordinate of pixel [0, 0], for a part translated by (0, 0)."""

    resolution: float

    def translation_for(self, px: int, py: int) -> Point:
        """The (dx, dy) that lands pixel [0, 0] of this mask on sheet pixel (px, py)."""
        return (
            px * self.resolution - self.origin[0],
            py * self.resolution - self.origin[1],
        )


def disk_kernel(radius_px: int) -> np.ndarray:
    """A round structuring element, so clearance is isotropic."""
    if radius_px <= 0:
        return np.ones((1, 1), dtype=bool)
    grid = np.ogrid[-radius_px:radius_px + 1, -radius_px:radius_px + 1]
    rows, cols = grid
    return (rows * rows + cols * cols) <= radius_px * radius_px


def rasterize(
    part: Part, angle: float, mirror: bool, resolution: float, sep: float
) -> PartMasks:
    """Build both masks for `part` at this orientation."""
    if resolution <= 0.0:
        raise ValueError(f"la resolucion debe ser positiva, se recibio {resolution}")

    transform = Transform(angle, mirror, 0.0, 0.0)
    outer = apply_points(transform, part.outer)
    holes = [apply_points(transform, hole) for hole in part.holes]

    pad = max(1, math.ceil(sep / resolution))
    min_x = min(p[0] for p in outer)
    min_y = min(p[1] for p in outer)
    max_x = max(p[0] for p in outer)
    max_y = max(p[1] for p in outer)

    origin = (min_x - pad * resolution, min_y - pad * resolution)
    width = math.ceil((max_x - min_x) / resolution) + 2 * pad + 1
    height = math.ceil((max_y - min_y) / resolution) + 2 * pad + 1

    image = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(image)
    draw.polygon(_to_pixels(outer, origin, resolution), fill=1)
    for hole in holes:
        draw.polygon(_to_pixels(hole, origin, resolution), fill=0)

    occupied = np.array(image, dtype=bool)
    radius = math.ceil(sep / resolution)
    clearance = (
        binary_dilation(occupied, structure=disk_kernel(radius))
        if radius > 0
        else occupied.copy()
    )

    return PartMasks(occupied=occupied, clearance=clearance, origin=origin,
                     resolution=resolution)


def _to_pixels(
    points: tuple[Point, ...], origin: Point, resolution: float
) -> list[tuple[float, float]]:
    """Map world points to (column, row). Row grows with y, as everything assumes."""
    return [
        ((x - origin[0]) / resolution, (y - origin[1]) / resolution) for x, y in points
    ]


class MaskCache:
    """Reuse masks across the many times the packer asks about the same orientation.

    Masks are the memory hot spot: a part with 24 allowed angles and mirroring
    has 48 entries. The cache is bounded and evicts least-recently-used.
    """

    def __init__(self, max_entries: int = 512) -> None:
        self._entries: OrderedDict[tuple, PartMasks] = OrderedDict()
        self._max_entries = max_entries

    def get(
        self, part: Part, angle: float, mirror: bool, resolution: float, sep: float
    ) -> PartMasks:
        key = (part.id, angle, mirror, resolution, sep)
        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            return cached

        masks = rasterize(part, angle, mirror, resolution, sep)
        self._entries[key] = masks
        if len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return masks
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/engine/raster/test_masks.py -v`
Esperado: `18 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/raster tests/engine/raster
git commit -m "feat: rasterizado de piezas con mascaras de ocupacion y holgura"
```

---

