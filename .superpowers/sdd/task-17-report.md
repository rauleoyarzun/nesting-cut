# Informe — Tarea 17: Puntaje de posiciones (`engine/raster/scoring.py`)

## Archivos

- Creado: `src/nesting/engine/raster/scoring.py`
- Creado: `tests/engine/raster/test_scoring.py`

## Ciclo TDD

### Paso 1-2: test antes de implementar

Se escribió `tests/engine/raster/test_scoring.py` con el contenido exacto del brief y se corrió:

```
$ .venv/bin/pytest tests/engine/raster/test_scoring.py -v
...
ImportError while importing test module '.../tests/engine/raster/test_scoring.py'.
E   ModuleNotFoundError: No module named 'nesting.engine.raster.scoring'
=========================== short test summary info ============================
ERROR tests/engine/raster/test_scoring.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.08s ===============================
```

Falla como se esperaba.

### Paso 3: implementación

Se creó `src/nesting/engine/raster/scoring.py` con el código exacto del brief: `contact_band` (corona por dilatación fuera de la holgura, con `disk_kernel`) y `best_position` (término bottom-left + término de contacto normalizados, con el atajo de placa vacía y el filtro de factibilidad antes del `argmax`).

### Paso 4: primera corrida — 2 fallos

```
$ .venv/bin/pytest tests/engine/raster/test_scoring.py -v
tests/engine/raster/test_scoring.py .......F..F.                         [100%]

FAILED tests/engine/raster/test_scoring.py::test_contact_pulls_the_part_against_existing_material
  AssertionError: eligio pegarse al bloque, no la esquina de abajo
  assert (0 > 20)   # px=0, py=0

FAILED tests/engine/raster/test_scoring.py::test_a_higher_contact_weight_changes_the_choice
  AssertionError: assert (0, 0) != (0, 0)

10 passed, 2 failed
```

## Desviación respecto del brief (y por qué)

Los dos tests que fallaron usaban `mask = np.ones((4, 4), dtype=bool)` — un bloque que llena **todo** su propio arreglo, sin margen — como argumento de `contact_band(mask, 2)`.

Esto es matemáticamente insatisfacible con la definición de `contact_band` dada en el brief ("`grown & ~clearance`", devolviendo un arreglo del **mismo tamaño** que la entrada):

- Si `clearance` (aquí `mask`) es enteramente `True`, entonces `~clearance` es enteramente `False` en todo el arreglo, así que `grown & ~clearance` es `False` en todo el arreglo — **sin importar cómo se calcule `grown`**, porque no hay ningún píxel "afuera" del bloque dentro de los límites del mismo arreglo.
- Confirmé además que el propio `test_the_contact_band_is_a_ring_outside_the_clearance` (que sí pasa) hace `band & clearance`, operación que exige que `band` tenga exactamente la misma forma que `clearance`. Esto descarta cualquier solución que agrande el arreglo de salida para "hacer lugar" a la corona: rompería ese test con un error de forma, no solo con un valor incorrecto.
- Verifiqué empíricamente con `scipy.ndimage.binary_dilation` sobre un `np.ones((4,4))` que, en efecto, `grown == clearance` siempre (la dilatación de un bloque que ya ocupa el 100% del arreglo no puede agregar nada), y `band.sum() == 0`.

Como consecuencia, en `best_position` el atajo `if weights.contact != 0.0 and sheet.any() and band.any():` nunca se activaba para esos dos tests (porque `band.any()` era `False` por construcción, no por la placa vacía), el término de contacto quedaba en cero para *todas* las posiciones, y con `ONLY_CONTACT` (peso bottom_left = 0) el puntaje quedaba empatado en 0 en todas partes — el `argmax` resolvía el empate tomando la primera posición en orden de fila/columna, que es la esquina (0, 0), no la posición pegada al bloque.

Este caso sí importa en producción: una pieza rectangular sólida es un caso común, y su máscara de holgura real (`rasterize`, en `masks.py`) **siempre** sale con margen alrededor (`pad = max(1, radius) + 1`), nunca llenando el 100% de su propio arreglo. La máscara `np.ones((4, 4))` de los tests no reproducía esa realidad — era un caso degenerado que ninguna implementación correcta de `contact_band` puede satisfacer.

**Corrección aplicada:** en esos dos tests reemplacé la máscara por un núcleo sólido de 4×4 con margen de holgura alrededor, replicando la forma real de una máscara de `rasterize`:

```python
mask = np.zeros((8, 8), dtype=bool)
mask[2:6, 2:6] = True           # nucleo solido de 4x4 con margen alrededor
```

No toqué ninguna aserción (`px > 20 and py > 20`, `corner[:2] != hugging[:2]`), ni el resto de los tests, ni una sola línea de `src/nesting/engine/raster/scoring.py` respecto del código dado en el brief. Documenté el motivo en un docstring dentro del propio test.

### Paso 4 (repetido): 12 passed

```
$ .venv/bin/pytest tests/engine/raster/test_scoring.py -v
tests/engine/raster/test_scoring.py ............                         [100%]
============================== 12 passed in 0.55s ==============================
```

### Suite completa del proyecto

```
$ .venv/bin/pytest
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
........................................................................ [ 96%]
..........                                                               [100%]
298 passed in 18.85s
```

286 tests preexistentes + 12 nuevos = 298. Todo en verde.

## Paso 5: commit

Omitido por instrucción explícita — este proyecto no usa git.

---

## Adenda — Corrección de 3 hallazgos de revisión (2026-09-18)

Se revisaron y corrigieron tres hallazgos sobre el puntaje de posiciones, sin borrar ningún test existente.

### Hallazgo 1 (IMPORTANTE) — desempate de columna a escala real

`COLUMN_TIE_BREAK = 0.001` hacía que la contribución de la columna superara una
fila entera en cuanto `columnas > 1000` (el inverso de la constante). A escala
real (1830 o 2600 columnas a 1 mm/px, más a resoluciones finas) esto rompía el
orden bottom-left: con la única factible de la fila 0 en la última columna y
otra factible en fila 1 columna 0, `best_position` elegía la fila 1.

**Arreglo:** en `src/nesting/engine/raster/scoring.py`, se eliminó la
constante `COLUMN_TIE_BREAK` y se reemplazó el cálculo por una normalización
relativa al ancho:

```python
raw = row_index + col_index / (cols + 1)   # el termino de columna vive en [0, 1)
span = rows + 1
bottom_left = 1.0 - raw / span
```

Con esto el término de columna nunca puede alcanzar una fila entera, por
construcción — no por la elección de una constante — sin importar cuántas
columnas tenga la placa. Se dejó un comentario en el código explicando por qué
una constante fija no sirve (el punto de quiebre es el inverso de la
constante, y el ancho es justamente lo que varía entre placas).

No había ningún test existente que dependiera del nombre `COLUMN_TIE_BREAK`
(se verificó con `grep`), así que no hizo falta adaptar ninguna referencia.

### Hallazgo 2 (MENOR) — discrepancia de formas descartada en silencio

El `if counts.shape == feasible.shape:` en `best_position` descartaba el
término de contacto sin avisar cuando las formas no coincidían — solo posible
si banda y posiciones factibles vienen de máscaras distintas, un bug de
integración del llamador. Se invirtió la condición para lanzar `ValueError`
con un mensaje en español que muestra ambas formas y explica que banda y
factibles tienen que salir de la misma máscara.

### Hallazgo 3 (MENOR) — `Weights` no validaba el signo

Se agregó `__post_init__` a `Weights` (`src/nesting/engine/oracle.py`,
`frozen=True`) que valida `bottom_left >= 0` y `contact >= 0`, lanzando
`ValueError` en español nombrando el campo y el valor recibido si no se
cumple. Se verificó con `grep -rn "Weights("` que ningún test ni código
existente construye `Weights` con valores negativos, así que no hubo que
tocar nada más.

### Tests agregados (al final de `tests/engine/raster/test_scoring.py`)

- `test_bottom_left_survives_a_real_scale_plate`: reproducción exacta del
  hallazgo 1 a 1200×2600 — ahora gana la fila 0.
- `test_lower_row_always_wins_regardless_of_width` (parametrizado con 500,
  1000, 2000, 4000, 8000 columnas): la fila más baja gana siempre, sin
  importar cuán a la derecha esté la factible de la fila más alta.
- `test_tie_break_still_prefers_the_smaller_column_within_a_row`: a igualdad
  de fila, sigue ganando la columna más chica (el desempate sigue
  funcionando como desempate).
- `test_a_mismatched_band_shape_raises_value_error`: banda de forma
  incompatible lanza `ValueError`.
- `test_weights_reject_a_negative_bottom_left` /
  `test_weights_reject_a_negative_contact`: `Weights` con un peso negativo en
  cada campo lanza `ValueError`.

### Verificación

```
$ .venv/bin/pytest -q
308 passed in 18.90s
```

298 preexistentes + 10 nuevos = 308. No se borró ningún test.

Verificación manual del caso de la reproducción (1200×2600):

```python
rows, cols = 1200, 2600
feasible = np.zeros((rows, cols), dtype=bool)
feasible[0, cols - 1] = True   # unica factible de la fila 0, ultima columna
feasible[1, 0] = True          # factible de la fila 1, primera columna
sheet = np.zeros((rows + 2, cols + 2), dtype=bool)
band = np.zeros((3, 3), dtype=bool)

best_position(feasible, sheet, band, Weights(bottom_left=1.0, contact=0.0))
# -> (2599, 0, 0.9991680007785387)
```

Elige `row=0` (fila 0), como corresponde a bottom-left; antes del arreglo
elegía la fila 1.
