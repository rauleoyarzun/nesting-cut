### Task 5: Encadenado de contornos (`geometry/chaining.py`)

**Files:**
- Create: `src/nesting/model/part.py`
- Create: `src/nesting/geometry/chaining.py`
- Test: `tests/geometry/test_chaining.py`

**Interfaces:**
- Consumes: `Point` de `nesting.model.entities` (Task 2)
- Produces:
  - `Contour(points: tuple[Point, ...], entity_ids: tuple[int, ...])` — cerrado, **sin repetir** el primer punto al final
  - `OpenChain(points: tuple[Point, ...], entity_ids: tuple[int, ...], gap: float)` — lo que no cerró, con la distancia que faltaba
  - `chain_contours(segments: Sequence[tuple[tuple[Point, ...], int]], tol: float) -> tuple[list[Contour], list[OpenChain], int]`
    - Cada entrada es `(polilínea_aplanada, id_de_entidad_de_origen)`.
    - El tercer valor devuelto es la **cantidad de segmentos duplicados descartados**.

**Por qué este módulo existe.** Los DXF que exporta CorelDRAW traen cada contorno **partido en decenas de `LINE`, `ARC` y `SPLINE` sueltos**, no como polilíneas cerradas. Sin reconstruir los ciclos no hay piezas. Es el caso normal, no el excepcional, y es donde se esconden los bugs que después se malinterpretan como "el nesting anda mal". Por eso es un módulo aislado con test propio exhaustivo.

**Algoritmo.** Primero se descartan duplicados (Corel suele dibujar la misma línea dos veces). Después se construye un índice espacial (`scipy.spatial.cKDTree`) sobre los extremos de todos los tramos. Se toma un tramo sin usar y se camina hacia adelante enganchando tramos cuyo extremo caiga dentro de `tol`, invirtiéndolos si hace falta; cuando no hay más, se da vuelta la cadena acumulada y se camina hacia adelante otra vez (que equivale a extender hacia atrás). Si los dos extremos terminan a distancia ≤ `tol`, es un contorno cerrado; si no, es una cadena abierta que se reporta con su hueco.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/geometry/test_chaining.py`:

```python
import math

from nesting.geometry.chaining import chain_contours

TOL = 0.1


def test_a_single_already_closed_ring_is_a_contour():
    ring = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    contours, open_chains, duplicates = chain_contours([(ring, 0)], TOL)

    assert len(contours) == 1
    assert len(open_chains) == 0
    assert duplicates == 0
    assert contours[0].points[0] != contours[0].points[-1], "no se repite el primer punto"
    assert len(contours[0].points) == 4
    assert contours[0].entity_ids == (0,)


def test_four_separate_sides_become_one_contour():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (10.0, 10.0)), 1),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)

    assert len(contours) == 1
    assert len(open_chains) == 0
    assert len(contours[0].points) == 4
    assert sorted(contours[0].entity_ids) == [0, 1, 2, 3]


def test_sides_in_random_order_and_reversed_still_chain():
    segments = [
        (((10.0, 10.0), (10.0, 0.0)), 2),   # invertido
        (((0.0, 10.0), (0.0, 0.0)), 3),
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((0.0, 10.0), (10.0, 10.0)), 1),   # invertido
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)

    assert len(contours) == 1
    assert len(open_chains) == 0
    assert len(contours[0].points) == 4


def test_endpoints_within_tolerance_are_joined():
    """Corel deja huecos de micras entre tramos; tienen que unirse igual."""
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.02), (10.0, 10.0)), 1),   # arranca 0.02 mm mas arriba
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_gap_larger_than_tolerance_produces_an_open_chain():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (10.0, 10.0)), 1),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 5.0)), 3),      # falta el ultimo tramo
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)

    assert len(contours) == 0
    assert len(open_chains) == 1
    assert math.isclose(open_chains[0].gap, 5.0, abs_tol=1e-9)


def test_two_independent_squares_become_two_contours():
    segments = [
        (((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)), 0),
        (((5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 6.0), (5.0, 5.0)), 1),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)
    assert len(contours) == 2
    assert len(open_chains) == 0


def test_exact_duplicate_segments_are_discarded():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((0.0, 0.0), (10.0, 0.0)), 1),      # duplicado exacto
        (((10.0, 0.0), (10.0, 10.0)), 2),
        (((10.0, 10.0), (0.0, 10.0)), 3),
        (((0.0, 10.0), (0.0, 0.0)), 4),
    ]
    contours, open_chains, duplicates = chain_contours(segments, TOL)

    assert duplicates == 1
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_reversed_duplicate_segments_are_discarded():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (0.0, 0.0)), 1),      # el mismo, al reves
        (((10.0, 0.0), (10.0, 10.0)), 2),
        (((10.0, 10.0), (0.0, 10.0)), 3),
        (((0.0, 10.0), (0.0, 0.0)), 4),
    ]
    contours, _, duplicates = chain_contours(segments, TOL)
    assert duplicates == 1
    assert len(contours) == 1


def test_chain_can_grow_backwards_from_the_starting_segment():
    """Se arranca por un tramo del medio: hay que extender para los dos lados."""
    segments = [
        (((10.0, 0.0), (10.0, 10.0)), 1),    # este queda primero en la lista
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_degenerate_contours_are_dropped():
    """Un 'contorno' de dos puntos no encierra area: no es una pieza."""
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (0.0, 0.0000001)), 1),
    ]
    contours, _, _ = chain_contours(segments, TOL)
    assert len(contours) == 0


def test_empty_input():
    assert chain_contours([], TOL) == ([], [], 0)


def test_entity_ids_are_preserved_for_every_contour():
    segments = [
        (((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)), 7),
        (((5.0, 5.0), (6.0, 5.0)), 8),
        (((6.0, 5.0), (6.0, 6.0)), 9),
        (((6.0, 6.0), (5.0, 6.0)), 10),
        (((5.0, 6.0), (5.0, 5.0)), 11),
    ]
    contours, _, _ = chain_contours(segments, TOL)
    by_size = sorted(contours, key=lambda c: len(c.entity_ids))
    assert by_size[0].entity_ids == (7,)
    assert sorted(by_size[1].entity_ids) == [8, 9, 10, 11]
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/geometry/test_chaining.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.geometry.chaining'`.

- [ ] **Step 3: Escribir el modelo de contornos**

Archivo `src/nesting/model/part.py`:

```python
"""Contours, parts and placements: what the engine moves around."""

from dataclasses import dataclass

from nesting.model.entities import Point


@dataclass(frozen=True)
class Contour:
    """A closed loop. The first point is NOT repeated at the end."""

    points: tuple[Point, ...]
    entity_ids: tuple[int, ...]
    """Indices into the drawing's entity list, so the writer can find the originals."""


@dataclass(frozen=True)
class OpenChain:
    """A run of segments that failed to close. Reported to the user as an error."""

    points: tuple[Point, ...]
    entity_ids: tuple[int, ...]
    gap: float
    """Distance between the two loose ends, in mm."""
```

- [ ] **Step 4: Escribir el encadenador**

Archivo `src/nesting/geometry/chaining.py`:

```python
"""Rebuild closed loops out of loose segments.

CorelDRAW exports split every outline into dozens of separate LINE, ARC and
SPLINE entities rather than closed polylines, so this is the normal path, not an
error path. It is also the dirtiest code in the project, which is why it lives
on its own behind a narrow interface.
"""

import math
from collections.abc import Sequence

from scipy.spatial import cKDTree

from nesting.model.entities import Point
from nesting.model.part import Contour, OpenChain

MIN_CONTOUR_POINTS = 3
"""Fewer than three distinct points cannot enclose any area."""


def chain_contours(
    segments: Sequence[tuple[tuple[Point, ...], int]],
    tol: float,
) -> tuple[list[Contour], list[OpenChain], int]:
    """Join `segments` end to end into closed contours.

    Each input is a flattened polyline paired with the id of the entity it came
    from. Returns the closed contours, the runs that failed to close, and how
    many duplicate segments were discarded.
    """
    kept, duplicates = _drop_duplicates(segments, tol)
    if not kept:
        return [], [], duplicates

    paths = [list(points) for points, _ in kept]
    ids = [entity_id for _, entity_id in kept]

    endpoints = []
    for path in paths:
        endpoints.append(path[0])
        endpoints.append(path[-1])
    tree = cKDTree(endpoints)

    used = [False] * len(paths)
    contours: list[Contour] = []
    open_chains: list[OpenChain] = []

    for seed in range(len(paths)):
        if used[seed]:
            continue
        used[seed] = True
        points = list(paths[seed])
        chain_ids = [ids[seed]]

        if _is_closed(points, tol):
            _emit(points, chain_ids, tol, contours, open_chains)
            continue

        # Walk forward, then reverse and walk forward again, which extends the
        # other end. Two passes are enough because after the reversal the former
        # head is the tail.
        for _ in range(2):
            _extend_forward(points, chain_ids, paths, ids, used, tree, tol)
            if _is_closed(points, tol):
                break
            points.reverse()

        _emit(points, chain_ids, tol, contours, open_chains)

    return contours, open_chains, duplicates


def _extend_forward(
    points: list[Point],
    chain_ids: list[int],
    paths: list[list[Point]],
    ids: list[int],
    used: list[bool],
    tree: cKDTree,
    tol: float,
) -> None:
    """Keep attaching unused segments to the tail of `points`."""
    while True:
        match = _find_unused_neighbour(points[-1], paths, used, tree, tol)
        if match is None:
            return
        index, at_tail = match
        used[index] = True
        nxt = list(paths[index])
        if at_tail:
            nxt.reverse()
        points.extend(nxt[1:])
        chain_ids.append(ids[index])
        if _is_closed(points, tol):
            return


def _find_unused_neighbour(
    target: Point,
    paths: list[list[Point]],
    used: list[bool],
    tree: cKDTree,
    tol: float,
) -> tuple[int, bool] | None:
    """Find an unused segment with an endpoint within `tol` of `target`.

    Returns (segment index, whether it matched on that segment's tail).
    """
    for endpoint_index in tree.query_ball_point(target, tol):
        index, which_end = divmod(endpoint_index, 2)
        if used[index]:
            continue
        return index, which_end == 1
    return None


def _emit(
    points: list[Point],
    chain_ids: list[int],
    tol: float,
    contours: list[Contour],
    open_chains: list[OpenChain],
) -> None:
    """Classify a finished run as a closed contour or an open chain."""
    gap = math.dist(points[0], points[-1])
    if gap > tol:
        open_chains.append(OpenChain(tuple(points), tuple(chain_ids), gap))
        return

    ring = points[:-1] if gap <= tol and len(points) > 1 else points
    ring = _drop_consecutive_duplicates(ring, tol)
    if len(ring) < MIN_CONTOUR_POINTS:
        return  # degenerate: encloses no area
    contours.append(Contour(tuple(ring), tuple(chain_ids)))


def _is_closed(points: list[Point], tol: float) -> bool:
    return len(points) > 2 and math.dist(points[0], points[-1]) <= tol


def _drop_consecutive_duplicates(points: list[Point], tol: float) -> list[Point]:
    out: list[Point] = []
    for p in points:
        if not out or math.dist(out[-1], p) > tol:
            out.append(p)
    return out


def _drop_duplicates(
    segments: Sequence[tuple[tuple[Point, ...], int]],
    tol: float,
) -> tuple[list[tuple[tuple[Point, ...], int]], int]:
    """Remove segments that repeat an earlier one, in either direction.

    Corel exports frequently draw the same line twice. The key is built from the
    two endpoints plus the middle point and the point count, snapped to the
    tolerance grid, and made order-independent so a reversed copy collides.
    """
    seen: set[tuple] = set()
    kept: list[tuple[tuple[Point, ...], int]] = []
    duplicates = 0

    for points, entity_id in segments:
        if len(points) < 2:
            duplicates += 1
            continue
        head = _snap(points[0], tol)
        tail = _snap(points[-1], tol)
        middle = _snap(points[len(points) // 2], tol)
        key = (tuple(sorted((head, tail))), middle, len(points))
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        kept.append((points, entity_id))

    return kept, duplicates


def _snap(p: Point, tol: float) -> tuple[int, int]:
    return (round(p[0] / tol), round(p[1] / tol))
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/geometry/test_chaining.py -v`
Esperado: `12 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/model/part.py src/nesting/geometry/chaining.py tests/geometry/test_chaining.py
git commit -m "feat: encadenado de tramos sueltos en contornos cerrados"
```

---

