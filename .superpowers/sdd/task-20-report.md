# Tarea 20: Previsualización PNG — Informe

## Archivos creados

- `src/nesting/io/preview.py` — implementación de `write_preview`.
- `tests/io/test_preview.py` — los 7 tests del brief.

Ambos paquetes (`src/nesting/io/`, `tests/io/`) ya tenían `__init__.py`, así que no hizo falta crearlos.

## Ciclo TDD

### Paso 2: correr el test para verificar que falla

```
$ .venv/bin/pytest tests/io/test_preview.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 0 items / 1 error

==================================== ERRORS ====================================
__________________ ERROR collecting tests/io/test_preview.py ___________________
ImportError while importing test module '/Users/raulo/cut-placement/tests/io/test_preview.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Cellar/python@3.13/3.13.5/Frameworks/Python.framework/Versions/3.13/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/io/test_preview.py:3: in <module>
    from nesting.io.preview import write_preview
E   ModuleNotFoundError: No module named 'nesting.io.preview'
=========================== short test summary info ============================
ERROR tests/io/test_preview.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.06s ===============================
```

Falla como se esperaba (`ModuleNotFoundError`).

### Paso 4: correr el test para verificar que pasa

```
$ .venv/bin/pytest tests/io/test_preview.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 7 items

tests/io/test_preview.py .......                                         [100%]

=============================== warnings summary ===============================
tests/io/test_preview.py::test_a_part_is_actually_drawn
  /Users/raulo/cut-placement/tests/io/test_preview.py:52: DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.
    reds = sum(1 for pixel in image.getdata() if pixel == (255, 0, 0))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================= 7 passed, 1 warning in 0.87s =========================
```

7 passed, tal cual el brief. El warning de `Image.getdata` viene del propio texto del test provisto por el brief (`test_a_part_is_actually_drawn`), no de la implementación; no se tocó porque el código del test es el que especifica el brief textualmente.

### Suite completa

```
$ .venv/bin/pytest
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 63%]
........................................................................ [ 84%]
......................................................                   [100%]
=============================== warnings summary ===============================
tests/io/test_preview.py::test_a_part_is_actually_drawn
  /Users/raulo/cut-placement/tests/io/test_preview.py:52: DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.
    reds = sum(1 for pixel in image.getdata() if pixel == (255, 0, 0))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
342 passed, 1 warning in 116.68s (0:01:56)
```

342 = 335 preexistentes + 7 nuevos. Todo en verde.

## Desviaciones respecto del brief

Ninguna. El código de `src/nesting/io/preview.py` y `tests/io/test_preview.py` se copió tal cual lo especifica el brief (Paso 1 y Paso 3), sin modificaciones.

El **Paso 5 (commit de git) se omitió** por instrucción explícita: este proyecto no usa git.

## Notas sobre el eje Y

La conversión de coordenadas usa `origin_y - y * px_per_mm` (fila medida desde el borde inferior de la placa), que es la convención correcta: `fila = alto_px − y·escala`. El test `test_the_y_axis_is_not_flipped` lo verifica ubicando una pieza con `dy=50` (cerca del origen, "abajo" en el modelo) dentro de una placa de 1000×1000 y comprobando que la masa de píxeles rojos cae en la mitad inferior de la imagen. Pasa sin ajustes.

---

## Actualización: 3 hallazgos de code review corregidos (2026-09-18)

Se corrigieron los tres hallazgos reportados sobre `src/nesting/io/preview.py` (pieza anidada en un agujero que desaparece según el orden de la lista, `KeyError` crudo con `part_id` desconocido, y escala sin tope que genera un PNG que ni Pillow puede reabrir). No se usó git (el proyecto no lo usa) y no se borró ningún test existente.

### Hallazgo 1 — orden de dibujo por área descendente

En `write_preview` se ordenan los `placements` **solo para dibujar** (`sorted(placements, key=..., reverse=True)`), usando `Part.area` como clave, sin tocar el orden de la lista que recibió la función ni su firma. Se dejó un comentario explicando por qué una pieza anidada en un agujero es necesariamente más chica que su contenedora, y por qué no hay que "simplificar" ese orden de vuelta a la lista original.

### Hallazgo 2 — `part_id` desconocido

Se cambió el `by_id[placement.part_id]` directo por `by_id.get(...)`, acumulando los `part_id` que no aparecen en `parts` en `missing_ids` y saltando esa colocación (se sigue dibujando el resto). Al final, si hubo alguna, se avisa con `warnings.warn(...)` (no se usó `print`/`sys.stderr` porque no hay convención de logging propia dentro de `nesting.io`; `warnings.warn` es estándar de biblioteca, no ensucia stdout y es fácil de verificar con `pytest.warns`). El mensaje en español indica cuántas colocaciones se saltearon y un id de ejemplo.

### Hallazgo 3 — tope de píxeles del lienzo

Se agregó la constante `MAX_CANVAS_PIXELS = 80_000_000` (con comentario explicando que Pillow (`PIL.Image.MAX_IMAGE_PIXELS`, ~89.5 Mpx) se niega a *abrir* imágenes por encima de ese umbral, así que el tope se fijó cómodamente por debajo). Antes de crear el lienzo (`Image.new`), se calcula `total_pixels = width * height` y si supera el tope se lanza `ValueError` con un mensaje en español que incluye las dimensiones de la placa, el `px_per_mm` pedido, el tamaño de lienzo que resultaría (en px y Mpx), el límite, y una escala sugerida (`px_per_mm * sqrt(MAX_CANVAS_PIXELS / total_pixels)`).

### Tests agregados (al final de `tests/io/test_preview.py`, sin tocar los existentes)

- `test_a_part_nested_in_a_hole_is_drawn_small_before_big` / `..._big_before_small`: anillo 800×800 con hueco 200..600 y una pieza chica 100×100 centrada en el hueco, con el orden de `placements` invertido entre los dos tests. Ambos comprueban el píxel del centro de la **placa** (no del lienzo entero — el lienzo incluye la franja de utilización debajo, por eso se agregó el helper `_sheet_centre_pixel` usando `LABEL_BAND_PX`).
- `test_an_unknown_part_id_warns_but_still_draws_the_rest`: una colocación con `part_id=99` inexistente junto a una válida; se verifica con `pytest.warns(UserWarning, match="99")` y que la pieza válida se sigue dibujando.
- `test_a_scale_over_the_pixel_cap_raises`: `px_per_mm=50.0` sobre placa 1000×1000 → `pytest.raises(ValueError, match="px_per_mm")`.
- `test_a_reasonable_scale_is_not_blocked_by_the_cap`: escala default sobre una placa chica, confirma que sigue funcionando y que el lienzo resultante está por debajo de `MAX_CANVAS_PIXELS`.

### Verificación

```
$ .venv/bin/pytest
........................................................................ [ 20%]
........................................................................ [ 41%]
........................................................................ [ 62%]
........................................................................ [ 82%]
...........................................................              [100%]
347 passed, 2 warnings in 109.48s (0:01:56)
```

347 = 342 preexistentes + 5 tests nuevos (dos del hallazgo 1 en los dos órdenes, uno del hallazgo 2, dos del hallazgo 3). Los 2 warnings son `DeprecationWarning` de `Image.getdata` (patrón ya presente en un test preexistente, `test_a_part_is_actually_drawn`, replicado en el test nuevo de `part_id` desconocido) — no relacionados con esta corrección.

Verificación manual del hallazgo 1, en los dos órdenes posibles (anillo 800×800 con hueco 200..600, pieza chica 100×100 centrada en el hueco, mismo color para ambas):

- Pieza chica listada **antes** de la grande → píxel central `(0, 100, 200)` (color de la pieza, visible).
- Pieza chica listada **después** de la grande → píxel central `(0, 100, 200)` (mismo resultado).

Antes de la corrección, el primer caso hubiera dado `(232, 232, 232)` (`SHEET_FILL`, la pieza borrada por el relleno del agujero de la pieza grande).

## Estado final

Los tres hallazgos quedaron corregidos, con tests de regresión para cada uno, y la suite completa pasa en verde (347/347).
