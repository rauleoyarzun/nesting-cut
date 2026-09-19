# Task 10: Catálogo de Materiales — Reporte de Implementación

## Status: DONE

## Archivos Creados

1. **`tests/model/test_material.py`**
   - 10 tests para el catálogo de materiales
   - Cubre: Material dataclass, cálculo de ángulos permitidos, carga de YAML, validación de errores, ruta por defecto

2. **`materials.yaml`** (raíz del proyecto)
   - Catálogo de 4 materiales: mdf18, mdf15, multilam18, fenolico18
   - Cada material especifica placa [ancho, alto] en mm y tolerancia_veta en grados

3. **`src/nesting/model/material.py`**
   - `Material` dataclass frozen con: name, sheet_w, sheet_h, grain_tolerance
   - `load_materials(path)`: carga YAML, valida estructura, devuelve dict[str, Material]
   - `allowed_angles(material, angles)`: filtra ángulos permitidos según restricción de veta
   - `_distance_to_grain_axis(angle)`: calcula distancia angular al eje de veta (0° y 180°)
   - `DEFAULT_MATERIALS_PATH`: apunta correctamente a materials.yaml en raíz

## Verificación

### Ciclo TDD Completado

#### Step 1: Test escrito ✓
```bash
$ cat tests/model/test_material.py
# 10 test functions covering:
# - Free rotation (tolerance 180°)
# - Grain constraints (tolerance 5°)
# - Angles within tolerance range
# - Edge cases: 360°, negative angles, empty list
# - YAML loading and error reporting
```

#### Step 2: Test fallando (antes de implementar) ✓
```
ERROR collecting tests/model/test_material.py
ModuleNotFoundError: No module named 'nesting.model.material'
```

#### Step 3: Catálogo creado ✓
`materials.yaml` con 4 materiales en raíz del proyecto

#### Step 4: Implementación completada ✓
`src/nesting/model/material.py` con todas las interfaces solicitadas

#### Step 5: Tests pasando ✓
```
tests/model/test_material.py ..........                                  [100%]

============================== 10 passed in 0.03s ==============================
```

### Suite Completa del Proyecto

```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0

tests/geometry/test_chaining.py ..........................               [ 18%]
tests/geometry/test_flatten.py .......................                   [ 34%]
tests/geometry/test_nesting_tree.py ................                     [ 46%]
tests/geometry/test_transform.py ...............                         [ 56%]
tests/geometry/test_verify.py ..................                         [ 69%]
tests/io/test_dxf_reader.py ................                             [ 80%]
tests/io/test_dxf_writer.py .........                                    [ 87%]
tests/model/test_entities.py ......                                      [ 91%]
tests/model/test_material.py ..........                                  [ 98%]
tests/test_smoke.py ..                                                   [100%]

============================== 141 passed in 1.17s ==============================
```

**Resultado:** 131 tests preexistentes + 10 nuevos = **141 passed** ✓

## Verificación de Detalles Críticos

### DEFAULT_MATERIALS_PATH
```
Path: /Users/raulo/cut-placement/materials.yaml
Calculated via: Path(__file__).resolve().parents[3] / "materials.yaml"
  __file__ = /Users/raulo/cut-placement/src/nesting/model/material.py
  parents[3] = /Users/raulo/cut-placement
Exists: True ✓
```

### Catálogo Cargado
```
Loaded materials: ['mdf18', 'mdf15', 'multilam18', 'fenolico18']
mdf18 sheet_w: 1830.0 ✓
```

### Cálculo de Ángulos (ejemplos de tests)

1. **Rotación libre (grain_tolerance=180)**
   - Input: [0.0, 15.0, 90.0, 137.0, 180.0, 270.0]
   - Output: [0.0, 15.0, 90.0, 137.0, 180.0, 270.0] ✓

2. **Restricción de veta cruzado (grain_tolerance=5)**
   - Input: [0.0, 90.0, 180.0, 270.0]
   - Output: [0.0, 180.0] ✓
   
3. **Ángulos dentro de tolerancia**
   - Input: [0.0, 3.0, 8.0, 177.0, 183.0]
   - Output: [0.0, 3.0, 177.0, 183.0] ✓
   
4. **Casos borde**
   - 360° = 0° (mod 180): permitido ✓
   - -3° dentro de ±5° de 0°: permitido ✓
   - [] → [] (vacío) ✓

### Validación de Errores YAML

- Campo faltante `tolerancia_veta`: error nombra material + campo ✓
- Placa malformada `[100]` en lugar de `[100, 200]`: error nombra material + campo ✓

## Notas de Implementación

1. **GRAIN_EPS = 1e-9**: margin para comparaciones de punto flotante en el cálculo de distancia angular
2. **Fórmula de distancia**: `min(a % 180, 180 - (a % 180))` maneja correctamente ángulos negativos y > 360°
3. **Mensajes de error en español**: los requisitos especifican campo + nombre del material
4. **Dataclass frozen=True**: como especifica el brief (congruente con resto del proyecto)

## Deviaciones del Brief

Ninguna. Se siguió exactamente el código y estructura especificados.

---

## Addendum: endurecimiento de validación (hallazgos 1, 2 y 3)

### Status: DONE

### Cambios en `src/nesting/model/material.py`

- **Hallazgo 1 (errores crudos):** se agregó el helper `_as_float(value, *, name, field)` que convierte a `float` y, si falla, lanza `ValueError` en español nombrando el material, el campo (`placa.ancho`, `placa.alto` o `tolerancia_veta`) y el valor recibido. Se usa para `size[0]`, `size[1]` y `tolerancia_veta` en lugar de `float(...)` directo.
  - Se agregó también una validación de la raíz del YAML: si `raw` no es un `dict` (por ejemplo una lista o un string suelto), se lanza `ValueError` explicando que el catálogo tiene que ser un mapeo de `nombre: campos`. El caso de YAML vacío (`None` → `{}` vía `or {}`) sigue sin cambios y sigue cargando como catálogo vacío.
- **Hallazgo 2 (rangos no validados):** tras convertir a `float`, se valida:
  - `sheet_w > 0` y `sheet_h > 0` (estrictamente positivos), si no, `ValueError` nombrando material, campo `placa` y los valores recibidos.
  - `0 <= grain_tolerance <= 180`, si no, `ValueError` nombrando material, campo `tolerancia_veta` y el valor recibido.
- **Hallazgo 3 (documentación de la equivalencia oculta):** se documentó en el docstring del campo `grain_tolerance` de `Material`, en el docstring de `allowed_angles`, y en el comentario de cabecera de `materials.yaml` que el rango útil real es `[0, 90]` (por la fórmula `min(a mod 180, 180 - (a mod 180))`), y que `90` ya equivale a rotación libre igual que `180`, usado por convención.

### Tests agregados en `tests/model/test_material.py` (los 10 originales quedaron intactos)

11 tests nuevos (total 21), todos verificando que el mensaje de error nombra material/campo/valor según corresponda:

- `test_a_non_numeric_sheet_size_is_reported_clearly`
- `test_a_non_numeric_grain_tolerance_is_reported_clearly`
- `test_a_catalogue_whose_root_is_a_list_is_reported_clearly`
- `test_a_catalogue_whose_root_is_a_bare_string_is_reported_clearly`
- `test_a_negative_sheet_width_is_rejected`
- `test_a_zero_sheet_height_is_rejected`
- `test_a_negative_grain_tolerance_is_rejected`
- `test_a_grain_tolerance_over_180_is_rejected`
- `test_ninety_degrees_is_already_free_rotation_like_180` (documenta el contrato del hallazgo 3)
- `test_the_shipped_catalogue_has_all_four_materials` (no regresión)
- `test_a_catalogue_at_the_boundary_values_loads_fine` (no regresión, valores límite: `tolerancia_veta` 0 y 180, placas positivas chicas)

### Verificación

1. `.venv/bin/pytest tests/model/test_material.py -v` → **21 passed** (los 10 originales sin modificar + 11 nuevos).
2. `.venv/bin/pytest -q` → **152 passed**, exit code 0 (141 anteriores + 11 nuevos).
3. Verificación manual con `.venv/bin/python`:
   - Carga del catálogo real (`DEFAULT_MATERIALS_PATH`):
     ```
     OK, materiales cargados: ['fenolico18', 'mdf15', 'mdf18', 'multilam18']
     ```
   - `tolerancia_veta: -5` en un catálogo temporal:
     ```
     ValueError: el material 'roto' tiene 'tolerancia_veta' invalida: -5 (tiene que estar entre 0 y 180 grados inclusive)
     ```
   Ambos casos dieron el resultado esperado.

### Archivos modificados

- `/Users/raulo/cut-placement/src/nesting/model/material.py`
- `/Users/raulo/cut-placement/materials.yaml`
- `/Users/raulo/cut-placement/tests/model/test_material.py`
