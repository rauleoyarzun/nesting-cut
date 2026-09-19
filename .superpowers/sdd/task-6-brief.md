### Task 6: Árbol de contención (`geometry/nesting_tree.py`)

**Files:**
- Modify: `src/nesting/model/part.py` — agregar `Part` y `Placement`
- Create: `src/nesting/geometry/nesting_tree.py`
- Test: `tests/geometry/test_nesting_tree.py`

**Interfaces:**
- Consumes: `Contour` de `nesting.model.part` (Task 5), `Transform` de `nesting.model.entities` (Task 2)
- Produces:
  - `Part(id: int, outer: tuple[Point, ...], holes: tuple[tuple[Point, ...], ...], entity_ids: tuple[int, ...])` con las propiedades `area: float` (área neta, exterior menos agujeros), `outer_area: float` y `bbox: tuple[float, float, float, float]` (minx, miny, maxx, maxy)
  - `Placement(part_id: int, sheet: int, transform: Transform)`
  - `build_parts(contours: Sequence[Contour]) -> list[Part]`

**La regla, de la spec §3.3:** la profundidad de contención decide qué es cada contorno.

| Profundidad | Significado |
|---|---|
| 0 (par) | Contorno exterior de una pieza |
| 1 (impar) | Agujero de la pieza que lo contiene |
| ≥2 (par) | **Pieza independiente**, se reubica en otro lado |

Un contorno de nivel ≥2 se convierte en su **propia** pieza: sus `entity_ids` viajan con ella, **no** con la pieza que la contenía en el dibujo original. Esto es lo que permite que el motor después la ponga en cualquier lado (spec §5.2).

**Robustez:** la contención se testea con el `representative_point()` del contorno interno, no con `contains()` polígono-contra-polígono. Motivo: dos anillos anidados que comparten un tramo de borde (pasa con geometría exportada) hacen fallar `contains()`, mientras que el punto representativo está garantizadamente en el interior.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/geometry/test_nesting_tree.py`:

```python
import pytest

from nesting.geometry.nesting_tree import build_parts
from nesting.model.part import Contour


def square(x0, y0, side, ids):
    return Contour(
        points=((x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)),
        entity_ids=tuple(ids),
    )


def test_a_single_square_is_one_part_with_no_holes():
    parts = build_parts([square(0, 0, 100, [0])])
    assert len(parts) == 1
    assert parts[0].holes == ()
    assert parts[0].entity_ids == (0,)
    assert parts[0].id == 0


def test_two_disjoint_squares_are_two_parts():
    parts = build_parts([square(0, 0, 10, [0]), square(50, 50, 10, [1])])
    assert len(parts) == 2
    assert all(p.holes == () for p in parts)


def test_a_contour_inside_another_becomes_a_hole():
    parts = build_parts([square(0, 0, 100, [0]), square(30, 30, 20, [1])])
    assert len(parts) == 1
    assert len(parts[0].holes) == 1
    assert sorted(parts[0].entity_ids) == [0, 1], "el agujero viaja con la pieza"


def test_depth_two_becomes_an_independent_part():
    """Exterior > agujero > isla. La isla es una pieza aparte."""
    contours = [square(0, 0, 100, [0]), square(20, 20, 60, [1]), square(40, 40, 20, [2])]
    parts = build_parts(contours)

    assert len(parts) == 2
    outer = next(p for p in parts if p.outer_area > 1000)
    island = next(p for p in parts if p.outer_area <= 1000)

    assert sorted(outer.entity_ids) == [0, 1]
    assert island.entity_ids == (2,), "la isla NO arrastra los ids del padre"
    assert island.holes == ()


def test_depth_three_is_a_hole_of_the_depth_two_part():
    contours = [
        square(0, 0, 200, [0]),
        square(20, 20, 160, [1]),
        square(40, 40, 120, [2]),
        square(60, 60, 80, [3]),
    ]
    parts = build_parts(contours)
    assert len(parts) == 2
    island = min(parts, key=lambda p: p.outer_area)
    assert len(island.holes) == 1
    assert sorted(island.entity_ids) == [2, 3]


def test_several_holes_in_one_part():
    contours = [
        square(0, 0, 100, [0]),
        square(10, 10, 10, [1]),
        square(40, 40, 10, [2]),
        square(70, 70, 10, [3]),
    ]
    parts = build_parts(contours)
    assert len(parts) == 1
    assert len(parts[0].holes) == 3
    assert sorted(parts[0].entity_ids) == [0, 1, 2, 3]


def test_net_area_subtracts_the_holes():
    parts = build_parts([square(0, 0, 100, [0]), square(30, 30, 20, [1])])
    assert parts[0].outer_area == pytest.approx(10000.0)
    assert parts[0].area == pytest.approx(10000.0 - 400.0)


def test_bbox():
    parts = build_parts([square(5, -3, 10, [0])])
    assert parts[0].bbox == pytest.approx((5.0, -3.0, 15.0, 7.0))


def test_part_ids_are_consecutive_from_zero():
    contours = [square(0, 0, 10, [0]), square(50, 0, 10, [1]), square(100, 0, 10, [2])]
    parts = build_parts(contours)
    assert sorted(p.id for p in parts) == [0, 1, 2]


def test_empty_input_produces_no_parts():
    assert build_parts([]) == []


def test_area_is_positive_regardless_of_winding_direction():
    clockwise = Contour(((0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)), (0,))
    parts = build_parts([clockwise])
    assert parts[0].outer_area == pytest.approx(100.0)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/geometry/test_nesting_tree.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.geometry.nesting_tree'`.

- [ ] **Step 3: Agregar `Part` y `Placement` al modelo**

Agregar al final de `src/nesting/model/part.py`:

```python
@dataclass(frozen=True)
class Part:
    """One piece to cut: an outer outline plus the holes that travel with it."""

    id: int
    outer: tuple[Point, ...]
    holes: tuple[tuple[Point, ...], ...]
    entity_ids: tuple[int, ...]
    """Every entity that moves rigidly with this part, outer and holes alike."""

    @property
    def outer_area(self) -> float:
        return _shoelace_area(self.outer)

    @property
    def area(self) -> float:
        """Net material area: the outline minus its holes."""
        return self.outer_area - sum(_shoelace_area(h) for h in self.holes)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.outer]
        ys = [p[1] for p in self.outer]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass(frozen=True)
class Placement:
    """Where one part ended up: which sheet, and the rigid transform to get there."""

    part_id: int
    sheet: int
    transform: Transform


def _shoelace_area(ring: tuple[Point, ...]) -> float:
    """Absolute enclosed area, independent of winding direction."""
    total = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0
```

Y ampliar el import del principio del archivo:

```python
from nesting.model.entities import Point, Transform
```

- [ ] **Step 4: Escribir el árbol de contención**

Archivo `src/nesting/geometry/nesting_tree.py`:

```python
"""Decide which contours are parts and which are holes.

Even nesting depth means material, odd means a hole, following the usual CAD
convention. A contour at depth two or deeper becomes an independent part rather
than staying nested where it happened to be drawn, so the engine is free to
place it anywhere.
"""

from collections.abc import Sequence

from shapely.geometry import Polygon
from shapely.strtree import STRtree

from nesting.model.part import Contour, Part


def build_parts(contours: Sequence[Contour]) -> list[Part]:
    """Group `contours` into parts by containment depth."""
    if not contours:
        return []

    polygons = [Polygon(c.points) for c in contours]
    polygons = [p if p.is_valid else p.buffer(0) for p in polygons]

    parents = _find_parents(polygons)
    depths = [_depth_of(i, parents) for i in range(len(contours))]

    # Holes are attached to the nearest enclosing contour, but only when that
    # contour is itself material (even depth). A depth-3 ring is a hole of the
    # depth-2 part, not of the depth-0 one.
    holes_by_owner: dict[int, list[int]] = {}
    for index, depth in enumerate(depths):
        if depth % 2 == 1:
            owner = parents[index]
            assert owner is not None, "an odd-depth contour always has a parent"
            holes_by_owner.setdefault(owner, []).append(index)

    parts: list[Part] = []
    for index, depth in enumerate(depths):
        if depth % 2 == 1:
            continue
        hole_indices = holes_by_owner.get(index, [])
        entity_ids = list(contours[index].entity_ids)
        for hole in hole_indices:
            entity_ids.extend(contours[hole].entity_ids)
        parts.append(
            Part(
                id=len(parts),
                outer=contours[index].points,
                holes=tuple(contours[h].points for h in hole_indices),
                entity_ids=tuple(entity_ids),
            )
        )
    return parts


def _find_parents(polygons: list[Polygon]) -> list[int | None]:
    """For each polygon, the index of the smallest polygon that encloses it."""
    tree = STRtree(polygons)
    parents: list[int | None] = [None] * len(polygons)

    for index, polygon in enumerate(polygons):
        # A representative point is guaranteed interior, which survives the
        # shared-boundary cases that make polygon-in-polygon containment fail.
        probe = polygon.representative_point()
        best: int | None = None
        best_area = float("inf")
        for candidate in tree.query(probe):
            candidate = int(candidate)
            if candidate == index:
                continue
            if not polygons[candidate].contains(probe):
                continue
            if polygons[candidate].area < best_area:
                best, best_area = candidate, polygons[candidate].area
        parents[index] = best

    return parents


def _depth_of(index: int, parents: Sequence[int | None]) -> int:
    depth = 0
    current = parents[index]
    while current is not None:
        depth += 1
        current = parents[current]
    return depth
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/geometry/test_nesting_tree.py -v`
Esperado: `11 passed`.

- [ ] **Step 6: Correr toda la suite para verificar que nada se rompió**

Run: `.venv/bin/pytest -q`
Esperado: `48 passed`.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/model/part.py src/nesting/geometry/nesting_tree.py tests/geometry/test_nesting_tree.py
git commit -m "feat: arbol de contencion para separar piezas de agujeros"
```

---

