# Reporte — Tarea 11: interfaz `Oracle` y motor trivial `ShelfOracle`

## Archivos creados

- `src/nesting/engine/__init__.py` (vacío)
- `src/nesting/engine/oracle.py` — `Weights`, `NestConfig`, `Oracle` (Protocol), `transformed_bbox`
- `src/nesting/engine/shelf_oracle.py` — `ShelfOracle`
- `tests/engine/__init__.py` (vacío)
- `tests/engine/test_shelf_oracle.py` — 13 tests, tal como los especifica el brief

Todo el código, docstrings y nombres de símbolos quedaron en inglés; no hay mensajes al usuario en este módulo (el único mensaje visible, la excepción de `place`, está en español: "no hay lugar para la pieza en la placa actual").

## Ciclo TDD

### Paso 2 — correr el test antes de implementar (falla esperada)

```
$ .venv/bin/pytest tests/engine/test_shelf_oracle.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 0 items / 1 error

==================================== ERRORS ====================================
______________ ERROR collecting tests/engine/test_shelf_oracle.py ______________
ImportError while importing test module '/Users/raulo/cut-placement/tests/engine/test_shelf_oracle.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Cellar/python@3.13/3.13.5/Frameworks/Python.framework/Versions/3.13/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/engine/test_shelf_oracle.py:3: in <module>
    from nesting.engine.oracle import NestConfig, transformed_bbox
E   ModuleNotFoundError: No module named 'nesting.engine'
=========================== short test summary info ============================
ERROR tests/engine/test_shelf_oracle.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.04s ===============================
```

Coincide con lo esperado por el brief (`ModuleNotFoundError: No module named 'nesting.engine'`).

### Paso 5 — correr el test tras implementar (pasa)

```
$ .venv/bin/pytest tests/engine/test_shelf_oracle.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 13 items

tests/engine/test_shelf_oracle.py .............                          [100%]

============================== 13 passed in 0.08s ==============================
```

13 passed, tal como especifica el brief.

### Suite completa

```
$ .venv/bin/pytest
........................................................................ [ 43%]
........................................................................ [ 87%]
.....................                                                    [100%]
165 passed in 1.23s
```

165 = 152 tests previos + 13 nuevos de `test_shelf_oracle.py`. Ningún test existente se rompió.

## Desviaciones respecto del brief

Ninguna. El código de `oracle.py`, `shelf_oracle.py` y `test_shelf_oracle.py` se copió tal cual del brief, verificando antes que las firmas de `Part`, `Placement`, `Transform`, `apply_points` y `verify` en el proyecto coincidieran con lo que el brief asume (coinciden exactamente).

Se omitió el Paso 6 (commit de git) por instrucción explícita: el proyecto no usa git.

## Notas de diseño (para las tareas siguientes)

- `Oracle` es un `typing.Protocol` estructural, no una clase base: `ShelfOracle` lo implementa por duck typing, sin heredar de nada. Cualquier motor futuro (`RasterOracle`, NFP, etc.) solo necesita exponer `reset`/`best_placement`/`place` con esas firmas.
- `x`/`y` que devuelve `best_placement` son directamente `dx`/`dy` de un `Transform` — se verificó con `test_the_first_part_lands_on_the_margin`, que reconstruye la posición absoluta del bounding box sumando `x + x0` y comparándola contra el margen.
- `best_placement` no muta estado: `_next_slot` se recalcula desde el estado interno (`_cursor_x`, `_shelf_y`, `_shelf_height`) sin modificarlo; solo `place` avanza el cursor, y lo hace recalculando el slot internamente en vez de confiar en los `x, y` que le pasa el llamador (así, si el llamador coloca la pieza en el slot que efectivamente devolvió `best_placement`, el estado avanza de forma consistente).
- El offset de separación (`sep`) se aplica dentro del oráculo (como suma al `cursor_x` tras cada `place`, y como salto vertical entre estantes), nunca como preproceso externo — cumple la restricción de arquitectura del brief.
- El test más importante (`test_a_full_shelf_layout_passes_the_verifier`) confirma que el invariante central se sostiene: cualquier layout que produzca el oráculo pasa `verify()` sin violaciones, tanto sin rotación como con piezas rotadas 90°.

---

## Adenda — Fix del defecto crítico de contrato en `place(x, y)`

### El defecto

Tal como describía el reporte original, `place` "recalcula el slot internamente en vez de confiar en los `x, y` que le pasa el llamador" — pero eso mismo era el bug: el `x` recibido nunca se comparaba contra nada, solo se ignoraba. `y` se usaba con una comparación floja (`1e-9`) solo para decidir si abrir un estante nuevo. Un llamador podía pedir `place(part, 0.0, False, 80.0, 20.0)` (el `x` de una consulta a 90°) y el oráculo commiteaba igual, en la posición de 0°, dejando el estado interno desincronizado de la geometría real que el llamador cree haber colocado. La pieza siguiente termina superponiéndose sin que nada lo reporte.

### El arreglo

1. **`src/nesting/engine/oracle.py`**: docstring de `Oracle.place` reemplazado por el texto exacto del brief, dejando explícita la precondición y la obligación de validar cuando no se puede representar una posición arbitraria. Se agregó `runtime_checkable` al import de `typing` y se decoró `Oracle` con `@runtime_checkable`.

2. **`src/nesting/engine/shelf_oracle.py`**:
   - Nueva constante `PLACE_TOLERANCE = 1e-6`.
   - `place` ahora recalcula el hueco (`_next_slot`) y compara `(x, y)` recibidos contra `(slot_x, slot_y)` con `PLACE_TOLERANCE`; si no coinciden, lanza `ValueError` con un mensaje en español que muestra ambas posiciones y explica la precondición (de dónde tiene que salir `(x, y)`).
   - Al avanzar el cursor y detectar estante nuevo, se dejó de usar el `y` del llamador (y la tolerancia suelta `1e-9`) y se usa la información del propio hueco.
   - Se encontró en el camino un problema más sutil: `_next_slot` devolvía `(dx, dy, width, height)`, donde `dy = shelf_y - by0` ya viene traducido por el offset de la bounding box (`by0`) de esa pieza en particular. Para una pieza sin espejar y sin rotar, `by0 = 0` y `dy` coincide con la coordenada absoluta del estante — por eso los 13 tests originales (que nunca usan `mirror=True` ni ángulos que dejen `by0 != 0`, ni siquiera 180°/270° producen ese caso porque son simétricos alrededor del origen del rectángulo... en realidad sí lo hacen, pero esos tests no llegan a ejercer una segunda pieza en el mismo estante tras una con `by0 != 0`) nunca lo notaron. Pero al agregar el test de secuencia mixta con piezas espejadas y rotadas a ángulos no múltiplos de 90, comparar `y`/`dy` contra `self._shelf_y` daba falsos positivos de "estante nuevo" y rompía la separación entre piezas (`verify` reportaba `separation` de 0.000 mm). Se corrigió haciendo que `_next_slot` devuelva además el `shelf_y` crudo (la coordenada absoluta del estante, antes de restarle `by0`), y `place` usa ese valor — no `dy` — para decidir si abrió un estante nuevo. Esto no cambia ningún valor numérico que ya devolvía `best_placement` (`dx`, `dy` quedan igual), solo corrige el criterio interno de "¿es estante nuevo?".

### Tests agregados (18 en total en `test_shelf_oracle.py`, los 13 originales sin tocar)

- `test_place_rejects_a_position_from_a_different_angle` — reproduce el caso exacto del revisor (0° da `x=20.0`, 90° da `x=80.0`, `place` con el ángulo 0 y el `x` de 90° lanza `ValueError` mencionando ambas posiciones).
- `test_place_rejects_an_arbitrary_made_up_position` — una posición inventada también lanza `ValueError`.
- `test_a_long_mixed_sequence_placed_correctly_still_passes_the_verifier` — 40 piezas de tamaños dispares, ángulos `0/90/180/270/37` (uno no múltiplo de 90) y mitad espejadas, colocadas siempre con el `(x, y)` de `best_placement`; el layout resultante pasa `verify` con cero violaciones.
- `test_shelf_oracle_satisfies_the_oracle_protocol` — `isinstance(ShelfOracle(), Oracle)` es `True` ahora que el protocolo es `runtime_checkable`.
- `test_a_failed_place_does_not_advance_the_oracles_state` — tras un `place` fallido, el `place` correcto inmediatamente después da el mismo resultado que si el fallido nunca hubiera ocurrido (comparado contra un oráculo de referencia sin el intento fallido).

### Verificación

```
$ .venv/bin/pytest tests/engine/test_shelf_oracle.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 18 items

tests/engine/test_shelf_oracle.py ..................                     [100%]

============================== 18 passed in 0.10s ==============================
```

```
$ .venv/bin/pytest -q
........................................................................ [ 42%]
........................................................................ [ 84%]
..........................                                               [100%]
170 passed
```

170 = 165 previos + 5 nuevos. Ningún test existente se modificó ni se rompió.

### Verificación manual de los dos casos del revisor

```
=== Caso 1: reproduccion exacta del revisor ===
best_placement 0 grados  -> x=20.0, y=20.0
best_placement 90 grados -> x=80.0, y=20.0
OK: lanzo ValueError -> place() recibio (80.0, 20.0) pero el hueco libre para esta pieza (part=1, angle=0.0, mirror=False) en el estado actual del oraculo es (20.0, 20.0). ShelfOracle solo puede commitear la posicion que el propio cursor de estante habria producido: (x, y) tiene que venir de una llamada a best_placement con el mismo (part, angle, mirror) y sin ningun place() intermedio.

=== Caso 2: secuencia de 40 piezas mixtas por el camino correcto ===
piezas colocadas: 40
violaciones: []
isinstance(ShelfOracle(), Oracle) = True
```

El caso del revisor ahora lanza `ValueError` en vez de producir el overlap `Violation(kind='overlap', part_a=1, part_b=2, sheet=0)`, y la secuencia de 40 piezas mixtas por el camino correcto sigue pasando `verify` con cero violaciones.

### Desviaciones respecto del brief de esta tarea

Ninguna en el contrato pedido. La única extensión no listada explícitamente en el brief es el cambio del valor de retorno interno de `_next_slot` (de 4 a 5 elementos, agregando el `shelf_y` crudo) — necesario para que la detección de estante nuevo sea correcta también para piezas espejadas o rotadas a ángulos que dejan `by0 != 0`, un caso que el brief pedía cubrir explícitamente en el test de secuencia mixta. `_next_slot` es un método privado (`_`-prefijado), no forma parte del contrato de `Oracle` ni lo usa ningún test existente directamente, así que no es una desviación observable desde afuera.
