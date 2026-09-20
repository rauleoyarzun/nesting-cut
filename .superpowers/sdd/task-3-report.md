# Task 3: Transformación rígida exacta — Informe de implementación

## Archivos creados

1. `src/nesting/geometry/__init__.py` (vacío)
2. `src/nesting/geometry/transform.py` (implementación principal)
3. `tests/geometry/__init__.py` (vacío)
4. `tests/geometry/test_transform.py` (suite de tests)

## Ciclo TDD

### Paso 2: Corrida inicial (test falla)

```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 0 items / 1 error

==================================== ERRORS ====================================
______________ ERROR collecting tests/geometry/test_transform.py _______________
ImportError while importing test module '<repo>/tests/geometry/test_transform.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Cellar/python@3.13/3.13.5/Frameworks/Python.framework/Versions/3.13/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level=0], package=None, level=0)
tests/geometry/test_transform.py:3: in <module>
    from nesting.geometry.transform import apply_entity, apply_point, apply_points
E   ModuleNotFoundError: No module named 'nesting.geometry.transform'
=========================== short test summary info ============================
ERROR tests/geometry/test_transform.py - ModuleNotFoundError: No module named 'nesting.geometry.transform'
```

**Resultado esperado:** FALLA con `ModuleNotFoundError`. ✓

### Paso 4: Corrida final (test pasa)

```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 15 items

tests/geometry/test_transform.py ...............                         [100%]

============================== 15 passed in 0.01s ==============================
```

**Resultado esperado:** 15 passed. ✓

## Detalles de implementación

La implementación en `src/nesting/geometry/transform.py` incluye:

- **`apply_point(t, p)`**: Aplica la transformación a un punto individual siguiendo el orden: espejo → rotación → traslación.
- **`apply_points(t, pts)`**: Aplica transformación a una secuencia de puntos, retornando tupla.
- **`apply_entity(t, e)`**: Manejo por pattern matching de cada tipo de entidad:
  - `Line`: Transforma ambos extremos.
  - `Circle`: Transforma el centro, mantiene el radio.
  - `Arc`: **Caso delicado** — cuando hay reflexión, invierte el sentido de barrido intercambiando extremos: `(start, end) → (180 - end, 180 - start)`. Los ángulos finales se normalizan con `_normalize_degrees()`.
  - `Bezier`: Transforma los cuatro puntos de control.
  - `Polyline`: Transforma todos los puntos, mantiene el flag `closed`.
- **`_normalize_degrees(a)`**: Pliega ángulos al rango [0, 360) usando módulo.

## Verificación del invariante Arc

El test `test_arc_endpoints_match_transformed_points` verifica que los extremos del arco transformado coincidan exactamente con los extremos originales transformados, incluso bajo rotación y reflexión combinadas. Este invariante garantiza que los arcos se cortan correctamente en el DXF final.

## Desviaciones respecto del brief

**Ninguna.** La implementación sigue exactamente el código del brief, incluyendo:
- Las firmas de funciones literales.
- La lógica de transformación de arcos.
- El orden de operaciones: espejo → rotación → traslación.
- La normalización de ángulos.

El step 5 del brief (commit de git) fue omitido por solicitud del usuario: *"Salvedad: el brief termina con un paso de commit de git. Omitilo. Este proyecto no usa git por decisión del usuario."*
