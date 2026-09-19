### Task 10: Catálogo de materiales (`model/material.py`)

**Files:**
- Create: `src/nesting/model/material.py`
- Create: `materials.yaml`
- Test: `tests/model/test_material.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `Material(name: str, sheet_w: float, sheet_h: float, grain_tolerance: float)`
  - `load_materials(path: str | Path) -> dict[str, Material]`
  - `allowed_angles(material: Material, angles: Sequence[float]) -> list[float]`
  - `DEFAULT_MATERIALS_PATH: Path`

**El parámetro que unifica la restricción de veta (spec §3.6).** Un ángulo está permitido cuando su desviación respecto de 0° o 180° es ≤ `grain_tolerance`. Con `180` queda todo habilitado (MDF); con `5` solo 0° y 180°, o sea corte cruzado bloqueado (multilaminado).

La distancia angular de `a` al eje de veta es `min(a mod 180, 180 - (a mod 180))`.

- [ ] **Step 1: Escribir el test que falla**

Archivo `tests/model/test_material.py`:

```python
import pytest

from nesting.model.material import Material, allowed_angles, load_materials

FREE = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
GRAIN = Material("multilam18", 1220.0, 2440.0, grain_tolerance=5.0)


def test_free_rotation_allows_every_angle():
    angles = [0.0, 15.0, 90.0, 137.0, 180.0, 270.0]
    assert allowed_angles(FREE, angles) == angles


def test_grain_constraint_keeps_only_zero_and_one_eighty():
    assert allowed_angles(GRAIN, [0.0, 90.0, 180.0, 270.0]) == [0.0, 180.0]


def test_grain_constraint_allows_angles_inside_the_tolerance():
    assert allowed_angles(GRAIN, [0.0, 3.0, 8.0, 177.0, 183.0]) == [0.0, 3.0, 177.0, 183.0]


def test_360_is_treated_as_zero():
    assert allowed_angles(GRAIN, [360.0]) == [360.0]


def test_negative_angles_are_handled():
    assert allowed_angles(GRAIN, [-3.0, -90.0]) == [-3.0]


def test_an_empty_angle_list_stays_empty():
    assert allowed_angles(GRAIN, []) == []


def test_loads_the_bundled_catalogue(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "mdf18:\n"
        "  placa: [1830, 2600]\n"
        "  tolerancia_veta: 180\n"
        "multilam18:\n"
        "  placa: [1220, 2440]\n"
        "  tolerancia_veta: 5\n",
        encoding="utf-8",
    )
    materials = load_materials(catalogue)

    assert set(materials) == {"mdf18", "multilam18"}
    assert materials["mdf18"].sheet_w == 1830.0
    assert materials["mdf18"].sheet_h == 2600.0
    assert materials["mdf18"].grain_tolerance == 180.0
    assert materials["mdf18"].name == "mdf18"
    assert materials["multilam18"].grain_tolerance == 5.0


def test_a_missing_field_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text("roto:\n  placa: [100, 200]\n", encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    assert "tolerancia_veta" in str(info.value)
    assert "roto" in str(info.value)


def test_a_malformed_sheet_size_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text("roto:\n  placa: [100]\n  tolerancia_veta: 5\n", encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    assert "placa" in str(info.value)


def test_the_shipped_catalogue_is_valid():
    from nesting.model.material import DEFAULT_MATERIALS_PATH
    materials = load_materials(DEFAULT_MATERIALS_PATH)
    assert "mdf18" in materials
    assert materials["mdf18"].sheet_w == 1830.0
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/pytest tests/model/test_material.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'nesting.model.material'`.

- [ ] **Step 3: Escribir el catálogo por defecto**

Archivo `materials.yaml` en la raíz del proyecto:

```yaml
# Catalogo de materiales.
#
# placa:            [ancho, alto] en milimetros
# tolerancia_veta:  cuantos grados puede desviarse una pieza del eje de la veta.
#                   180 = rotacion libre (la veta no importa, tipico de MDF)
#                     5 = solo 0 y 180 grados, corte cruzado bloqueado

mdf18:
  placa: [1830, 2600]
  tolerancia_veta: 180

mdf15:
  placa: [1830, 2600]
  tolerancia_veta: 180

multilam18:
  placa: [1220, 2440]
  tolerancia_veta: 5

fenolico18:
  placa: [1220, 2440]
  tolerancia_veta: 5
```

- [ ] **Step 4: Escribir el modelo de materiales**

Archivo `src/nesting/model/material.py`:

```python
"""The material catalogue: sheet size and grain constraint, together.

Choosing a material configures both at once, because they always change
together in practice.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_MATERIALS_PATH = Path(__file__).resolve().parents[3] / "materials.yaml"

GRAIN_EPS = 1e-9


@dataclass(frozen=True)
class Material:
    name: str
    sheet_w: float
    sheet_h: float
    grain_tolerance: float
    """Degrees a part may deviate from the grain axis. 180 means free rotation."""


def load_materials(path: str | Path) -> dict[str, Material]:
    """Read the YAML catalogue, failing loudly on a malformed entry."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    materials: dict[str, Material] = {}

    for name, spec in raw.items():
        if not isinstance(spec, dict):
            raise ValueError(f"el material {name!r} no es un bloque de campos")

        size = spec.get("placa")
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise ValueError(
                f"el material {name!r} necesita 'placa: [ancho, alto]' en milimetros"
            )
        if "tolerancia_veta" not in spec:
            raise ValueError(f"al material {name!r} le falta el campo 'tolerancia_veta'")

        materials[name] = Material(
            name=name,
            sheet_w=float(size[0]),
            sheet_h=float(size[1]),
            grain_tolerance=float(spec["tolerancia_veta"]),
        )

    return materials


def allowed_angles(material: Material, angles: Sequence[float]) -> list[float]:
    """Keep only the angles the material's grain constraint permits.

    An angle is allowed when it lies within `grain_tolerance` degrees of the
    grain axis, which runs along both 0 and 180 degrees.
    """
    return [a for a in angles if _distance_to_grain_axis(a) <= material.grain_tolerance + GRAIN_EPS]


def _distance_to_grain_axis(angle: float) -> float:
    folded = angle % 180.0
    return min(folded, 180.0 - folded)
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/pytest tests/model/test_material.py -v`
Esperado: `10 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/model/material.py materials.yaml tests/model/test_material.py
git commit -m "feat: catalogo de materiales con restriccion de veta"
```

---

