# Informe: Tarea 16 — Búsqueda por FFT (`engine/raster/search.py`)

## Archivos creados

- `src/nesting/engine/raster/search.py` — implementación (`overlap_counts`, `feasible_positions`, `COLLISION_THRESHOLD`).
- `tests/engine/raster/test_search.py` — 13 tests, copiados literalmente del brief.

Ambos directorios (`src/nesting/engine/raster/` y `tests/engine/raster/`) ya existían con `__init__.py` de tareas anteriores, así que no hizo falta crearlos.

## Ciclo TDD

### Paso 2: correr el test antes de implementar (debe fallar)

Comando: `.venv/bin/pytest tests/engine/raster/test_search.py -v`

```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 0 items / 1 error

==================================== ERRORS ====================================
_____________ ERROR collecting tests/engine/raster/test_search.py ______________
ImportError while importing test module '<repo>/tests/engine/raster/test_search.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Cellar/python@3.13/3.13.5/Frameworks/Python.framework/Versions/3.13/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/engine/raster/test_search.py:4: in <module>
    from nesting.engine.raster.search import feasible_positions, overlap_counts
E   ModuleNotFoundError: No module named 'nesting.engine.raster.search'
=========================== short test summary info ============================
ERROR tests/engine/raster/test_search.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.07s ===============================
```

Falla exactamente como esperaba el brief: `ModuleNotFoundError: No module named 'nesting.engine.raster.search'`.

### Paso 3: implementación

Se escribió `search.py` tal como lo especifica el brief, sin cambios: `overlap_counts` invierte la máscara en ambos ejes (`mask[::-1, ::-1]`) antes de pasarla a `fftconvolve` con `mode="valid"` (convolución con máscara invertida = correlación), valida que `sheet` y `mask` sean booleanos, y devuelve un arreglo `(0, 0)` si la máscara no entra en la placa. `feasible_positions` aplica el umbral `COLLISION_THRESHOLD = 0.5` sobre los conteos.

### Paso 4: correr el test después de implementar (debe pasar)

Comando: `.venv/bin/pytest tests/engine/raster/test_search.py -v`

```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 13 items

tests/engine/raster/test_search.py .............                         [100%]

============================== 13 passed in 0.54s ==============================
```

13/13 pasaron, tal como anticipaba el brief.

### Suite completa

Comando: `.venv/bin/pytest`

```
........................................................................ [ 25%]
........................................................................ [ 51%]
........................................................................ [ 77%]
................................................................         [100%]
280 passed in 16.94s
```

280 = 267 previos + 13 nuevos. Nada se rompió.

## Desviaciones respecto del brief

- **Paso 5 (commit) omitido**, según instrucción explícita: el proyecto no usa git (`git` ni siquiera está inicializado en este directorio).
- Ninguna otra desviación: el código de `search.py` y de `test_search.py` se copió literalmente del brief.

## Notas sobre los tres detalles señalados

1. **Inversión de la máscara**: implementada como `mask[::-1, ::-1]`, verificada por los tests de fuerza bruta (`test_overlap_counts_matches_brute_force_on_a_small_case` y la variante con 10 casos aleatorios), que habrían detectado un resultado espejado.
2. **Límites por forma del arreglo**: no hay ningún chequeo de rango en el código; `mode="valid"` garantiza la forma `(Hs-Hm+1, Ws-Wm+1)`, confirmada por `test_overlap_counts_has_the_valid_correlation_shape` y por el caso de máscara más grande que la placa (`test_a_mask_larger_than_the_sheet_yields_no_positions`, que devuelve tamaño 0 en vez de lanzar error).
3. **Umbral 0.5**: confirmado por `test_numerical_noise_does_not_create_false_collisions` (placa vacía grande de 600×800, sin falsos positivos) y `test_numerical_noise_does_not_hide_a_real_collision` (un solo píxel ocupado sigue bloqueando la posición correspondiente, sin que el ruido lo enmascare).

La propiedad de agujero (`test_a_mask_with_a_hole_can_straddle_occupied_material`) también pasó: una máscara de 5×5 con el centro vacío permite que un píxel ocupado quede en esa posición sin generar colisión.

---

## Adenda: fix del hallazgo "el umbral pierde margen a escala" (falsos negativos de colisión)

### Diagnóstico confirmado

`overlap_counts` casteaba a `float32` antes de `fftconvolve`. Medí el ruido de la FFT contra una tabla de sumas de área (integral image), método independiente y exacto, sobre una placa densamente ocupada con huecos de prueba dispersos (para sampleaar distintas posiciones/fases): algunas posiciones con solapamiento real exactamente 0, otras con exactamente 1 pixel de solapamiento real.

Resultados en `float32` (peor caso sobre 5 semillas, ~1000 posiciones de solapamiento-0 y ~140 de solapamiento-1 por corrida):

| Placa | Máscara | peor ruido (solap. real = 0) | peor valor (solap. real = 1) |
|---|---|---|---|
| 1830×2600 | 300×300 | 0.031 | 0.975 |
| 3000×4000 | 600×600 | 0.095 | 0.924 |
| 6000×8000 | 1000×1000 | 0.42 | 0.655 |
| 12000×16000 | 2000×2000 | 1.29 | **0** (falso negativo franco) |

Confirma el hallazgo: a 12000×16000 el ruido ya supera con creces `COLLISION_THRESHOLD = 0.5`, y un solapamiento real de un pixel se reporta como 0 (posición libre estando ocupada). El signo del problema es exactamente el descrito: el ruido depende del tamaño del arreglo y de la cantidad de material total en la placa, no del contenido local de la ventana.

### Medición de costo: `float64` vs `float32`, `fftconvolve` vs `oaconvolve`

Medido con `scipy` 1.18.1, 7 repeticiones por combinación, mediana en placas con densidad de ocupación ~40%:

| Escala | fftconvolve f32 | fftconvolve f64 | oaconvolve f32 | oaconvolve f64 |
|---|---|---|---|---|
| 1830×2600 / 300×300 (real) | 39.09 ms | 74.85 ms | 38.87 ms | **74.62 ms** |
| 3000×4000 / 600×600 | 147.13 ms | **227.31 ms** | 145.08 ms | 227.96 ms |
| 6000×8000 / 1000×1000 | 532.09 ms | **895.57 ms** | 537.36 ms | 894.37 ms |

Con `oaconvolve` verifiqué primero que da resultados **idénticos** a `fftconvolve` (`max|fft - oa| == 0.0` en `float32` y en `float64`, en las tres escalas) antes de compararlo por velocidad.

Contra la intuición de "overlap-and-add suele ganar cuando la placa es mucho más grande que la máscara": a las relaciones placa/máscara reales de este motor (mask entre ~1/6 y ~1/8 del lado de la placa, no una máscara diminuta), `oaconvolve` **no da ninguna ventaja consistente** sobre `fftconvolve` — las diferencias están dentro del ruido de medición (±1-2%), y en dos de las tres escalas `fftconvolve` fue el más rápido. La ventaja de `oaconvolve` solo aparece con relaciones mucho más extremas (probé placa 6000×8000 con máscara 100×100, relación ~60-80x: ahí sí gana por ~20%), que no es el caso típico de este motor.

**Combinación elegida: `fftconvolve` + `float64`** (la que ya estaba, solo cambiando el dtype). Es la más simple, y es la más rápida o empata con la más rápida entre las cuatro combinaciones con `float64` en las tres escalas medidas. A escala real (1830×2600 / 300×300): **74.85 ms por llamada** (vs. ~39 ms en el `float32` original — el fix casi duplica el costo de esta función, que es el punto caliente del motor, pero sigue en el orden de las decenas de milisegundos por llamada).

### Ruido medido con la combinación elegida (`fftconvolve` + `float64`)

Mismo método de medición (integral image + huecos de prueba dispersos, 5 semillas):

| Escala | peor ruido (solap. real = 0) | peor valor (solap. real = 1) |
|---|---|---|
| 1830×2600 / 300×300 (real) | 5.8×10⁻¹¹ | 1.0 (exacto) |
| 12000×16000 / 2000×2000 | 2.2×10⁻⁹ | 1.0 (exacto) |

El margen contra `COLLISION_THRESHOLD = 0.5` pasa de decimales (y de directamente cruzar el umbral a 12000×16000) a **nueve órdenes de magnitud**, sin depender de la escala.

### Cambios en `src/nesting/engine/raster/search.py`

- `overlap_counts`: castea a `np.float64` en lugar de `np.float32` antes de `fftconvolve`.
- `overlap_counts`: la forma de salida ahora se calcula por eje de forma independiente — `(max(Hs-Hm+1, 0), max(Ws-Wm+1, 0))` — en vez de colapsar siempre a `(0, 0)` cuando la máscara no entra. Además, maneja explícitamente el caso de una dimensión en cero (en la placa o en la máscara) devolviendo un arreglo 2-D de ceros con esa forma, en vez de dejar que `fftconvolve` lo colapse a un arreglo 1-D `(0,)`.
- `feasible_positions`: se sacó el chequeo especial `if counts.size == 0: return np.zeros((0, 0), ...)`, que forzaba la forma a `(0, 0)` y pisaba la forma real que ahora devuelve `overlap_counts`. La comparación `counts < COLLISION_THRESHOLD` funciona igual sobre un arreglo vacío de cualquier forma 2-D.
- Comentario de `COLLISION_THRESHOLD` actualizado con los valores reales medidos (antes decía "around 1e-10", que nunca fue cierto para el código que corría en `float32`; ahora documenta ~1e-9 en `float64` y por qué `float32` no era seguro).

### Tests agregados (`tests/engine/raster/test_search.py`, al final, sin tocar los 13 existentes)

1. `test_a_single_pixel_overlap_is_detected_as_collision_at_scale` — placa 6000×8000 densamente ocupada, máscara 1000×1000, un solapamiento real de exactamente un pixel; verifica que se detecta como colisión con la implementación corregida. El comentario que lo precede deja anotado que a 12000×16000/2000×2000 es donde `float32` fallaba de forma franca (valor 0 medido, ver tabla de diagnóstico arriba); se usa la escala menor para que el test corra en ~1 s en vez de varios segundos.
2. `test_numerical_noise_stays_far_below_threshold_on_a_large_occupied_sheet` — mismo tamaño, exige que el ruido en posiciones de solapamiento real 0 esté por debajo de `1e-6` (margen holgado frente al umbral de 0.5).
3. `test_a_sheet_with_a_zero_dimension_keeps_a_two_dimensional_shape`, `test_a_mask_with_a_zero_dimension_keeps_a_two_dimensional_shape`, `test_a_mask_larger_than_the_sheet_keeps_a_two_dimensional_shape`, `test_a_mask_too_tall_but_not_too_wide_keeps_the_real_width` — cubren los casos degenerados de forma, incluyendo el ejemplo (0, 5) señalado explícitamente en el hallazgo secundario.

### Verificación

`.venv/bin/pytest -q`: **286 passed** (280 previos + 6 nuevos), ~19 s. Ningún test existente fue modificado ni borrado.

(Nota al margen: con `addopts = "-q"` en `pyproject.toml` más un `-q` explícito en la línea de comandos, pytest 9.1.1 no imprime la línea final de resumen "`N passed in ...`" — verificado corriendo sin el `-q` extra. No es un problema del código de este proyecto, es solo un detalle de verbosidad de pytest a tener en cuenta al invocar la suite.)

