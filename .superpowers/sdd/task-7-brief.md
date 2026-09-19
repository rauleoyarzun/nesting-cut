### Task 7: El verificador exacto (`geometry/verify.py`)

**Files:**
- Create: `src/nesting/geometry/verify.py`
- Test: `tests/geometry/test_verify.py`

**Interfaces:**
- Consumes: `Part`, `Placement` (Task 6), `Transform` (Task 2), `apply_points` (Task 3)
- Produces:
  - `Violation(kind: str, part_a: int, part_b: int | None, sheet: int, detail: str)` — `kind` es `"overlap"`, `"separation"` u `"out_of_bounds"`; `detail` es un mensaje en español listo para mostrar
  - `placed_polygon(part: Part, t: Transform) -> shapely.geometry.Polygon`
  - `verify(parts, placements, sheet_w, sheet_h, sep, margin) -> list[Violation]`

**Este es el módulo más importante del hito 1.** Cumple tres funciones (spec §5.7):

1. **Red de seguridad en producción** — ninguna salida se escribe sin pasar por acá.
2. **Oráculo de los tests** — cualquier motor, cualquier configuración, tiene que pasarlo.
3. **Árbitro** de la comparación raster vs NFP si algún día existe el segundo motor.

Trabaja sobre **polígonos exactos de shapely**, nunca sobre bitmaps. Es deliberadamente independiente de cualquier motor: no importa nada de `engine/`.

**El caso que valida el aprovechamiento de agujeros:** una pieza colocada dentro del agujero de otra **no** debe dar violación. Sale solo, porque el polígono del padre se construye con `interiors` y shapely computa `distance` contra la pared real del agujero. Hay test específico.

**Tolerancia numérica:** se usa `EPS = 1e-6` mm. La separación se viola solo si la distancia es menor que `sep - EPS`, para que dos piezas puestas a exactamente `sep` no den falso positivo por ruido de punto flotante.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/geometry/test_verify.py`:

```python
from nesting.geometry.verify import placed_polygon, verify
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement


def square_part(part_id, side, holes=()):
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (side, 0.0), (side, side), (0.0, side)),
        holes=holes,
        entity_ids=(part_id,),
    )


def at(part_id, x, y, sheet=0, angle=0.0, mirror=False):
    return Placement(part_id, sheet, Transform(angle, mirror, x, y))


SHEET_W, SHEET_H = 1000.0, 1000.0


def test_a_single_well_placed_part_has_no_violations():
    parts = [square_part(0, 100.0)]
    placements = [at(0, 100.0, 100.0)]
    assert verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


def test_overlapping_parts_are_reported():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [at(0, 100.0, 100.0), at(1, 150.0, 150.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)

    assert len(violations) == 1
    assert violations[0].kind == "overlap"
    assert {violations[0].part_a, violations[0].part_b} == {0, 1}


def test_parts_closer_than_the_separation_are_reported():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    # Hay 3 mm de luz entre ellas, pero se pidieron 5.
    placements = [at(0, 100.0, 100.0), at(1, 203.0, 100.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)

    assert len(violations) == 1
    assert violations[0].kind == "separation"


def test_exactly_the_requested_separation_is_accepted():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [at(0, 100.0, 100.0), at(1, 205.0, 100.0)]
    assert verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


def test_a_part_outside_the_margin_is_reported():
    parts = [square_part(0, 100.0)]
    placements = [at(0, 5.0, 100.0)]   # el margen pedido es 10
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)

    assert len(violations) == 1
    assert violations[0].kind == "out_of_bounds"
    assert violations[0].part_a == 0


def test_a_part_past_the_far_edge_is_reported():
    parts = [square_part(0, 100.0)]
    placements = [at(0, 950.0, 100.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)
    assert [v.kind for v in violations] == ["out_of_bounds"]


def test_parts_on_different_sheets_never_collide():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [at(0, 100.0, 100.0, sheet=0), at(1, 100.0, 100.0, sheet=1)]
    assert verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


def test_a_part_nested_inside_a_hole_is_valid():
    """El aprovechamiento de agujeros de la spec 5.2, verificado de punta a punta."""
    ring = Part(
        id=0,
        outer=((0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)),
        holes=(((50.0, 50.0), (350.0, 50.0), (350.0, 350.0), (50.0, 350.0)),),
        entity_ids=(0,),
    )
    inner = square_part(1, 100.0)
    placements = [at(0, 100.0, 100.0), at(1, 250.0, 250.0)]

    assert verify([ring, inner], placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0) == []


def test_a_part_too_close_to_the_wall_of_a_hole_is_reported():
    ring = Part(
        id=0,
        outer=((0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)),
        holes=(((50.0, 50.0), (350.0, 50.0), (350.0, 350.0), (50.0, 350.0)),),
        entity_ids=(0,),
    )
    inner = square_part(1, 100.0)
    # La pieza interna queda a 2 mm de la pared del agujero.
    placements = [at(0, 100.0, 100.0), at(1, 152.0, 250.0)]
    violations = verify([ring, inner], placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)

    assert [v.kind for v in violations] == ["separation"]


def test_rotation_is_taken_into_account():
    """Rotada 45 grados, la diagonal se sale del margen."""
    parts = [square_part(0, 100.0)]
    placements = [at(0, 40.0, 500.0, angle=45.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)
    assert [v.kind for v in violations] == ["out_of_bounds"]


def test_placed_polygon_applies_the_transform_and_keeps_holes():
    ring = Part(
        id=0,
        outer=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
        holes=(((25.0, 25.0), (75.0, 25.0), (75.0, 75.0), (25.0, 75.0)),),
        entity_ids=(0,),
    )
    polygon = placed_polygon(ring, Transform(0.0, False, 10.0, 20.0))

    assert len(polygon.interiors) == 1
    assert polygon.area == 100.0 * 100.0 - 50.0 * 50.0
    assert polygon.bounds == (10.0, 20.0, 110.0, 120.0)


def test_every_violation_carries_a_readable_detail():
    parts = [square_part(0, 100.0), square_part(1, 100.0)]
    placements = [at(0, 100.0, 100.0), at(1, 150.0, 150.0)]
    violations = verify(parts, placements, SHEET_W, SHEET_H, sep=5.0, margin=10.0)
    assert violations[0].detail
    assert violations[0].sheet == 0
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/geometry/test_verify.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.geometry.verify'`.

- [ ] **Step 3: Escribir el verificador**

Archivo `src/nesting/geometry/verify.py`:

```python
"""The arbiter: does a finished layout actually respect its own rules?

Works on exact shapely polygons, never on rasters, and knows nothing about any
engine. Every output is checked here before it is written, and the tests use it
as their oracle.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import Polygon, box
from shapely.strtree import STRtree

from nesting.geometry.transform import apply_points
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement

EPS = 1e-6
"""Numeric slack in mm, so a part placed at exactly `sep` is not flagged."""


@dataclass(frozen=True)
class Violation:
    kind: str
    """One of "overlap", "separation", "out_of_bounds"."""

    part_a: int
    part_b: int | None
    sheet: int
    detail: str
    """User-facing message, in Spanish."""


def placed_polygon(part: Part, t: Transform) -> Polygon:
    """The exact material footprint of `part` once `t` is applied."""
    return Polygon(
        apply_points(t, part.outer),
        [apply_points(t, hole) for hole in part.holes],
    )


def verify(
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheet_w: float,
    sheet_h: float,
    sep: float,
    margin: float,
) -> list[Violation]:
    """Check a finished layout. An empty list means the layout is sound."""
    by_id = {p.id: p for p in parts}
    violations: list[Violation] = []

    by_sheet: dict[int, list[Placement]] = {}
    for placement in placements:
        by_sheet.setdefault(placement.sheet, []).append(placement)

    usable = box(margin, margin, sheet_w - margin, sheet_h - margin)

    for sheet, sheet_placements in sorted(by_sheet.items()):
        polygons = [placed_polygon(by_id[p.part_id], p.transform) for p in sheet_placements]

        for placement, polygon in zip(sheet_placements, polygons):
            if not usable.buffer(EPS).contains(polygon):
                violations.append(
                    Violation(
                        kind="out_of_bounds",
                        part_a=placement.part_id,
                        part_b=None,
                        sheet=sheet,
                        detail=(
                            f"la pieza {placement.part_id} se sale del area util de la placa "
                            f"{sheet + 1} (margen {margin} mm)"
                        ),
                    )
                )

        violations.extend(_check_pairs(sheet, sheet_placements, polygons, sep))

    return violations


def _check_pairs(
    sheet: int,
    placements: Sequence[Placement],
    polygons: Sequence[Polygon],
    sep: float,
) -> list[Violation]:
    """Pairwise overlap and separation checks, narrowed by a spatial index."""
    violations: list[Violation] = []
    if len(polygons) < 2:
        return violations

    # Growing each polygon by `sep` turns "closer than sep" into "intersects",
    # so the index can discard the vast majority of pairs up front.
    tree = STRtree([p.buffer(sep) for p in polygons])
    seen: set[tuple[int, int]] = set()

    for i, polygon in enumerate(polygons):
        for j in tree.query(polygon):
            j = int(j)
            if j == i:
                continue
            pair = (min(i, j), max(i, j))
            if pair in seen:
                continue
            seen.add(pair)

            a_id = placements[i].part_id
            b_id = placements[j].part_id

            if polygon.intersects(polygons[j]) and not polygon.touches(polygons[j]):
                violations.append(
                    Violation(
                        kind="overlap",
                        part_a=a_id,
                        part_b=b_id,
                        sheet=sheet,
                        detail=(
                            f"las piezas {a_id} y {b_id} se superponen en la placa {sheet + 1}"
                        ),
                    )
                )
                continue

            distance = polygon.distance(polygons[j])
            if distance < sep - EPS:
                violations.append(
                    Violation(
                        kind="separation",
                        part_a=a_id,
                        part_b=b_id,
                        sheet=sheet,
                        detail=(
                            f"las piezas {a_id} y {b_id} quedaron a {distance:.3f} mm "
                            f"en la placa {sheet + 1}; el minimo pedido es {sep} mm"
                        ),
                    )
                )

    return violations
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/geometry/test_verify.py -v`
Esperado: `12 passed`.

- [ ] **Step 5: Correr toda la suite**

Run: `.venv/bin/pytest -q`
Esperado: `60 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/geometry/verify.py tests/geometry/test_verify.py
git commit -m "feat: verificador geometrico exacto, el arbitro de toda salida"
```

**Hito 1 completo.** Ya existe el árbitro: cualquier layout, venga de donde venga, puede evaluarse como válido o inválido.

---

# Hito 2 — Circuito completo end-to-end

*Con un nesting deliberadamente malo. Tener el pipeline entero funcionando sobre archivos reales vale más que tener un motor excelente sin poder abrir el archivo.*

---

