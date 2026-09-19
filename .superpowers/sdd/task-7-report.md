# Task 7 report — El verificador exacto (`geometry/verify.py`)

## Archivos creados

- `src/nesting/geometry/verify.py` — implementación (`Violation`, `placed_polygon`, `verify`, `_check_pairs`), copiada tal cual del brief.
- `tests/geometry/test_verify.py` — los 12 tests del brief, sin cambios.

No se tocó ningún otro archivo (no se hizo commit por decisión del usuario, el proyecto no usa git).

## Ciclo TDD

### Step 2 — test que falla

```
$ .venv/bin/pytest tests/geometry/test_verify.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 0 items / 1 error

==================================== ERRORS ====================================
________________ ERROR collecting tests/geometry/test_verify.py ________________
ImportError while importing test module '/Users/raulo/cut-placement/tests/geometry/test_verify.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Cellar/python@3.13/3.13.5/Frameworks/Python.framework/Versions/3.13/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/geometry/test_verify.py:1: in <module>
    from nesting.geometry.verify import placed_polygon, verify
E   ModuleNotFoundError: No module named 'nesting.geometry.verify'
=========================== short test summary info ============================
ERROR tests/geometry/test_verify.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.04s ===============================
```

Falla como se esperaba: `ModuleNotFoundError: No module named 'nesting.geometry.verify'`.

### Step 4 — test que pasa (tras crear `src/nesting/geometry/verify.py`)

```
$ .venv/bin/pytest tests/geometry/test_verify.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 12 items

tests/geometry/test_verify.py ............                               [100%]

============================== 12 passed in 0.08s ==============================
```

`12 passed`, tal como preveía el brief. No hizo falta ningún ajuste sobre el código propuesto: pasó a la primera.

### Step 5 — suite completa

```
$ .venv/bin/pytest -q
........................................................................ [ 72%]
............................                                             [100%]
100 passed in 0.93s
```

`100 passed` (88 preexistentes + 12 nuevos de `test_verify.py`).

## Desviaciones respecto del brief

- **Conteo esperado en Step 5.** El brief dice "Esperado: `60 passed`", pero la base de código ya traía 88 tests en verde antes de esta tarea (según el enunciado de la tarea), así que el número real y correcto es `100 passed` (88 + 12). Es una discrepancia de redacción del brief (probablemente escrito contra un estado anterior del hito), no un problema de la implementación. No se investigó más porque el propio encargo de la tarea confirma "88 tests en verde" como línea de base.
- **Paso 6 (commit) omitido** por instrucción explícita: el proyecto no usa git.
- Ninguna otra desviación: `Violation`, `placed_polygon`, `verify` y `_check_pairs` quedaron exactamente como en el brief, incluyendo el mensaje `detail` en español y el manejo de `EPS` para la tolerancia de separación.

## Notas de diseño verificadas al leer el código

- El caso de pieza anidada en un agujero (`test_a_part_nested_inside_a_hole_is_valid`) funciona sin código especial: `placed_polygon` construye el `Polygon` del padre con sus `interiors` (holes), y `shapely` calcula `distance`/`intersects` contra la pared real del agujero.
- `usable.buffer(EPS).contains(polygon)` evita falsos positivos de borde por ruido de punto flotante, análogo a `sep - EPS` en separación.
- El `STRtree` se construye sobre los polígonos ya crecidos (`buffer(sep)`), así que solo los pares cuyo buffer se solapa llegan a los chequeos exactos de `intersects`/`distance`; sigue habiendo doble verificación exacta (no solo el buffer) antes de reportar una violación.

---

## Addendum — fix del falso negativo crítico y laguna defensiva (post-review)

### Qué se cambió

En `src/nesting/geometry/verify.py`:

1. **Hallazgo 1 (crítico) — franja útil fantasma con margen excesivo.**
   `usable = box(margin, margin, sheet_w - margin, sheet_h - margin)` normalizaba en
   silencio los límites invertidos cuando `margin` superaba la mitad de una dimensión
   de la placa, produciendo una caja fantasma en el centro que dejaba pasar piezas
   cuya holgura real al borde físico era menor a la pedida. Ahora `verify` calcula
   `usable_w = sheet_w - 2*margin` y `usable_h = sheet_h - 2*margin` por separado; si
   cualquiera de los dos es `<= 0`, el área útil se trata como vacía (`usable = None`)
   y **toda** pieza de esa placa se reporta `out_of_bounds`, con un `detail` que
   explica la causa real (el margen pedido no deja área útil) e incluye las medidas
   de placa, margen y anchos/altos útiles resultantes (incluso negativos), en vez de
   decir solo que la pieza "se sale".

2. **Hallazgo 2 (menor) — geometría de entrada no validada.**
   `placed_polygon` sigue sin validar (es una función pura de transformación), pero
   `verify` ahora chequea `polygon.is_valid` para cada colocación antes de someterla a
   `contains`/`intersects`/`distance`. Si el contorno es inválido (p. ej. un contorno
   tipo moño autointersectado), se agrega una `Violation` con `kind="invalid_geometry"`
   y un `detail` en español que nombra la pieza, y esa pieza se **excluye** de los
   chequeos de `out_of_bounds` y de los chequeos pareados (`_check_pairs`), porque el
   comportamiento de esos predicados de shapely no está garantizado sobre geometría
   inválida. Las piezas con agujeros (`interiors`) válidos no se ven afectadas: solo
   se filtra por `is_valid`, no por tener `interiors`.

   Se documentó el nuevo `kind` en el docstring de `Violation`.

Se agregaron 6 tests nuevos al final de `tests/geometry/test_verify.py` (sin tocar
los 12 existentes):

- `test_an_excessive_margin_leaves_no_usable_area_on_a_square_sheet` — repro exacta
  del hallazgo 1 (placa 200×200, margin=110) → `out_of_bounds` con `detail`
  mencionando que no queda área útil.
- `test_an_excessive_margin_on_a_single_axis_is_still_caught` — placa 1000×200,
  margin=110, pieza cayendo de lleno en la franja Y invertida `[90,110]` → también
  `out_of_bounds`.
- `test_a_margin_exactly_half_the_sheet_dimension_leaves_zero_usable_width` — caso
  límite exacto, placa 200×200, margin=100 (ancho útil cero) → `out_of_bounds`.
- `test_a_normal_margin_with_a_well_placed_part_still_has_no_violations` — margen
  normal, pieza bien colocada → `[]` (no regresión / no falso positivo).
- `test_a_self_intersecting_outline_is_reported_as_invalid_geometry` — contorno tipo
  moño → `kind == "invalid_geometry"`.
- `test_a_well_placed_part_with_holes_still_has_no_violations` — pieza con agujeros
  bien colocada → `[]` (el filtro de validez no rompe el caso de agujeros).

### Comandos y salida

```
$ .venv/bin/pytest tests/geometry/test_verify.py -v
============================= test session starts ==============================
collected 18 items

tests/geometry/test_verify.py ..................                         [100%]

============================== 18 passed in 0.10s ==============================
```

(12 preexistentes, sin modificar, + 6 nuevos — todos en verde.)

```
$ .venv/bin/pytest -q
........................................................................ [ 67%]
..................................                                       [100%]
```

106 tests en verde (100 preexistentes + 6 nuevos), sin fallos ni errores, exit code 0.

### Verificación manual

Caso de la reproducción crítica (placa 200×200, margin=110, pieza en el centro):

```
$ .venv/bin/python -c "
from nesting.geometry.verify import verify
from nesting.model.part import Part, Placement
from nesting.model.entities import Transform

def square_part(part_id, side, holes=()):
    return Part(id=part_id, outer=((0.0,0.0),(side,0.0),(side,side),(0.0,side)), holes=holes, entity_ids=(part_id,))

def at(part_id, x, y, sheet=0, angle=0.0, mirror=False):
    return Placement(part_id, sheet, Transform(angle, mirror, x, y))

result = verify([square_part(0, 20.0)], [at(0, 90.0, 90.0)], 200.0, 200.0, sep=5.0, margin=110.0)
for v in result:
    print(v)
"
Violation(kind='out_of_bounds', part_a=0, part_b=None, sheet=0, detail='la pieza 0 no se puede verificar contra el margen: con margen 110.0 mm en una placa de 200.0x200.0 mm no queda área útil (ancho útil -20.0 mm, alto útil -20.0 mm)')
```

Antes del fix esto devolvía `[]` (el falso negativo del hallazgo 1); ahora reporta
`out_of_bounds` con un `detail` que apunta a la causa real.

Caso de margen normal con pieza bien colocada (placa 1000×1000, margin=10):

```
$ .venv/bin/python -c "
... (mismo setup) ...
result2 = verify([square_part(0, 100.0)], [at(0, 100.0, 100.0)], 1000.0, 1000.0, sep=5.0, margin=10.0)
print(result2)
"
[]
```

Confirma que el arreglo no introduce falsos positivos en el caso normal.

### Notas

- No se tocó ningún test de los 12 originales.
- No se hizo commit (el proyecto no usa git).
- Los `detail` preexistentes se dejaron tal cual (sin tildes), conforme a la
  limpieza ortográfica pendiente aparte; los `detail` nuevos se escribieron con
  tildes correctas desde el arranque (p. ej. "área útil", "geometría inválida").
