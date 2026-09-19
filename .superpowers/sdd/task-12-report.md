# Task 12: Pipeline de preparación y packer — informe

## Archivos creados

- `src/nesting/pipeline.py` — `prepare_parts`, `OpenContourError`, y el helper privado `_flatten_closed`.
- `src/nesting/engine/packer.py` — `pack`, `PackResult`, `PartTooLargeError`, `replicate`, `orientations`.
- `tests/test_pipeline.py` — 9 tests, copiados del brief tal cual.
- `tests/engine/test_packer.py` — 14 tests, copiados del brief tal cual.

Se siguió el ciclo TDD del brief: tests primero, corrida en rojo, implementación, corrida en verde, suite completa. Se omitió el Step 7 (commit) porque el proyecto no usa git.

## Corridas de pytest

### Step 2 — tests recién escritos, deben fallar por import

```
$ .venv/bin/pytest tests/test_pipeline.py tests/engine/test_packer.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 0 items / 2 errors

==================================== ERRORS ====================================
___________________ ERROR collecting tests/test_pipeline.py ____________________
ImportError while importing test module '/Users/raulo/cut-placement/tests/test_pipeline.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Cellar/python@3.13/3.13.5/Frameworks/Python.framework/Versions/3.13/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_pipeline.py:5: in <module>
    from nesting.pipeline import OpenContourError, prepare_parts
E   ModuleNotFoundError: No module named 'nesting.pipeline'
_________________ ERROR collecting tests/engine/test_packer.py _________________
ImportError while importing test module '/Users/raulo/cut-placement/tests/engine/test_packer.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Cellar/python@3.13/3.13.5/Frameworks/Python.framework/Versions/3.13/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/engine/test_packer.py:4: in <module>
    from nesting.engine.packer import (
E   ModuleNotFoundError: No module named 'nesting.engine.packer'
=========================== short test summary info ============================
ERROR tests/test_pipeline.py
ERROR tests/engine/test_packer.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
============================== 2 errors in 0.16s ===============================
```

Coincide con lo esperado por el brief.

### Primera implementación (código del brief literal) — 2 fallas

Copiar `pipeline.py` y `packer.py` tal cual los da el brief deja pasar 21/23, con 2 fallas en `test_pipeline.py`, ambas del tipo `OpenContourError` disparándose donde no debía (un círculo suelto, y un círculo dentro de un cuadrado):

```
E           nesting.pipeline.OpenContourError: 1 contorno(s) no cierran. El mas cercano
a cerrar arranca en (50.000, 0.000) y termina en (49.240, -8.682), con un hueco de
8.716 mm. Revise el dibujo, o afloje la tolerancia con --tol-cierre.
...
E           nesting.pipeline.OpenContourError: 1 contorno(s) no cierran. El mas cercano
a cerrar arranca en (130.000, 100.000) y termina en (129.248, 93.324), con un hueco de
6.718 mm. Revise el dibujo, o afloje la tolerancia con --tol-cierre.

FAILED tests/test_pipeline.py::test_a_circle_becomes_one_part - nesting.pipel...
FAILED tests/test_pipeline.py::test_a_circle_inside_a_square_becomes_a_hole
========================= 2 failed, 21 passed in 0.31s =========================
```

Causa raíz: `flatten(Circle)` devuelve el anillo del círculo **sin repetir el primer punto al final** (así lo documenta `flatten.py` explícitamente). `chain_contours` sólo reconoce un tramo como ya cerrado cuando su primer y último punto coinciden dentro de `tol` (ver `tests/geometry/test_chaining.py::test_a_single_already_closed_ring_is_a_contour`, que pasa el anillo con el punto repetido). Un círculo solo, flateado con 36-158 segmentos, tiene un hueco entre el primer y el último punto del orden de varios milímetros (la cuerda entre dos muestras consecutivas) — muy por encima de `chain_tol` (0.1 mm) — así que `chain_contours` lo trataba como un contorno abierto.

**Fix:** se agregó `_flatten_closed` en `pipeline.py`, que cierra explícitamente el anillo (repite el primer punto) cuando la entidad es un `Circle`. Ningún otro tipo de entidad necesita este tratamiento: `Polyline` cerrada ya se cierra dentro de `flatten`, y un `Arc` de barrido completo (360°) cierra solo porque `flatten` calcula el punto final con la misma fórmula trigonométrica que el inicial, dando una distancia de cierre en el orden de `1e-14` mm.

### Segunda corrida — 1 falla (precisión de área)

Con el cierre de círculos arreglado, `test_a_circle_becomes_one_part` seguía fallando, pero ahora por precisión de área:

```
    def test_a_circle_becomes_one_part():
        parts, _ = prepare_parts(Drawing(entities=[Circle((0.0, 0.0), 50.0, STYLE)]))
        assert len(parts) == 1
>       assert parts[0].outer_area == pytest.approx(3.14159 * 50.0**2, rel=1e-3)
E       assert 7814.167995011865 == 7853.974999999999 ± 7.85397
E         Obtained: 7814.167995011865
E         Expected: 7853.974999999999 ± 7.85397

FAILED tests/test_pipeline.py::test_a_circle_becomes_one_part - assert 7814.1...
========================= 1 failed, 22 passed in 0.42s =========================
```

Causa raíz: `flatten` acota el **error de cuerda** (sagita), no el área encerrada, y ambos divergen rápido en una curva. Con `DEFAULT_FLATTEN_TOL = 0.2` mm (el valor que trae el brief), un círculo de radio 50 mm se aproxima con un polígono de 36 lados, cuyo área queda ~0.51% por debajo del área real — cinco veces más que la tolerancia relativa (`rel=1e-3`, 0.1%) que pide el test.

**Fix:** se bajó `DEFAULT_FLATTEN_TOL` a `0.02` mm (documentado en el propio módulo, con el porqué). Con ese valor el error de área para este caso queda en ~0.05%, con margen cómodo bajo el 0.1% pedido, y sigue siendo "muy por debajo de la resolución raster" (default `resolution=1.0` mm/px) que es el criterio que el propio brief usa para justificar la constante. Esta constante vive en `pipeline.py` (no en `flatten.py`, que no tiene default propio y siempre exige una tolerancia explícita), así que ajustarla es una decisión de esta tarea, no una modificación de un módulo de una tarea anterior.

### Step 5 — tests objetivo, verdes

```
$ .venv/bin/pytest tests/test_pipeline.py tests/engine/test_packer.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 23 items

tests/test_pipeline.py .........                                         [ 39%]
tests/engine/test_packer.py ..............                               [100%]

============================== 23 passed in 0.42s ==============================
```

### Step 6 — suite completa

```
$ .venv/bin/python -m pytest
........................................................................ [ 37%]
........................................................................ [ 74%]
.................................................                        [100%]
193 passed in 1.08s
```

170 tests preexistentes + 23 nuevos = 193, todos en verde.

## Desviaciones respecto del brief y por qué

1. **`_flatten_closed` (nueva función privada en `pipeline.py`, no está en el brief).** Necesaria porque `flatten(Circle)` no repite el primer punto y `chain_contours` sólo detecta un tramo ya cerrado cuando el primer y el último punto coinciden dentro de `tol`. Sin este cierre explícito, todo círculo suelto (sin otra entidad con la que encadenar) se reportaría como contorno abierto, lo cual contradice directamente `test_a_circle_becomes_one_part` y `test_a_circle_inside_a_square_becomes_a_hole`, ambos provistos por el propio brief. Se limita a `Circle` porque es el único tipo de entidad cuyo `flatten` no cierra el anillo por sí mismo (una `Polyline` cerrada ya viene cerrada de `flatten`; un `Arc` de 360° cierra solo, por construcción, con error de punto flotante despreciable).

2. **`DEFAULT_FLATTEN_TOL` bajado de `0.2` a `0.02` mm.** El valor del brief no alcanza la precisión de área (`rel=1e-3`) que pide `test_a_circle_becomes_one_part` para un círculo de radio 50 mm (el error real ronda 0.51%, cinco veces el límite). Se ajustó el valor, no el test (el test es parte de la especificación tal cual se pidió transcribir), y se documentó el porqué en el propio docstring de la constante.

Ambos cambios están confinados a `pipeline.py`, no tocan `flatten.py` ni `chaining.py` (Task 4 y Task 5, ya cerradas y con sus propios tests en verde), y ninguno de los dos afecta el comportamiento de `packer.py`, que se implementó literalmente como lo da el brief y pasó sus 14 tests sin cambios.

## Notas de diseño verificadas

- `ChainingInvariantError` y `OverlappingContourError` no se atrapan en ningún punto de `prepare_parts`: se propagan tal cual salen de `chain_contours` y `build_parts`, respectivamente.
- `pack` respeta el contrato estricto de `Oracle.place`: `_best_over_orientations` sólo llama a `best_placement` (que no muta estado) para cada orientación, y recién después de terminar esa comparación se llama a `place` una única vez, con el `(angle, mirror, x, y)` ganador exacto — sin ningún `place` intermedio entre medio.
- Una sola pasada por placa: las piezas se ordenan una vez por área descendente al entrar a `pack`, y cada placa procesa `remaining` en ese orden sin reordenar ni reintentar piezas que no entraron.
- `PartTooLargeError` se dispara únicamente cuando una placa recién abierta (`placed_area == 0.0`) no pudo alojar ninguna pieza, e informa las medidas mínimas de la pieza y el área útil de la placa.

## Estado final

`DONE`. 193/193 tests en verde (170 preexistentes + 23 nuevos). Dos desviaciones respecto del código literal del brief, ambas documentadas arriba con su causa raíz y confinadas a `pipeline.py`.

---

# Addendum: arreglo de 3 hallazgos post-revisión (ruido de punto flotante, mensaje de error inconsistente, campo muerto)

Sobre la implementación de arriba se detectaron y arreglaron tres hallazgos: uno crítico (ruido de punto flotante en rotaciones de 90° produciendo solapamientos fantasma) y dos importantes (mensaje de `PartTooLargeError` incoherente, y el campo muerto `PackResult.unplaced`).

## Hallazgo 1 (CRÍTICO) — ruido de punto flotante en rotaciones de 90°

**1a. `src/nesting/geometry/transform.py`.** `apply_point` llamaba a `math.cos`/`math.sin` sobre `math.radians(angle_deg)` sin excepción, y `math.cos(math.radians(90.0))` da `6.123e-17`, no 0 exacto. Se agregó `_cos_sin`, que detecta si el ángulo es un múltiplo exacto de 90° (dentro de `1e-9` en unidades de "cuartos de vuelta") y devuelve los valores exactos `(1,0)/(0,1)/(-1,0)/(0,-1)` de una tabla (`_QUARTER_TURN_TRIG`), en vez de pasar por `math.cos`/`math.sin`. Los ángulos que no son múltiplos de 90 siguen el camino trigonométrico normal, sin cambios de comportamiento. El comentario en el código explica el porqué (pi/2 no es representable exactamente en binario, y 90/180/270 son el caso más común del sistema, no uno exótico).

**1b. `src/nesting/geometry/verify.py`.** El criterio de solapamiento pasó de `polygon.intersects(other) and not polygon.touches(other)` a comparar el **área** de la intersección contra una constante nombrada, `OVERLAP_AREA_THRESHOLD_MM2 = 1e-6` (un micrón cuadrado). Justificación documentada en el propio código: el ruido de punto flotante vive en el orden de `1e-11` mm² (cinco órdenes de magnitud por debajo del umbral), y un solapamiento real —incluso uno chico— es del orden de 1 mm² o más (seis órdenes por encima); un micrón cuadrado no existe para una fresa de 6 mm en MDF. El umbral no puede enmascarar un solapamiento real: casos de contención total, piezas idénticas superpuestas y solapamientos parciales de ~1 mm² siguen dando área muy por encima del umbral y se siguen reportando (verificado con tests nuevos, ver abajo).

## Hallazgo 2 (IMPORTANTE) — mensaje de `PartTooLargeError`

`_raise_too_large` en `src/nesting/engine/packer.py` tomaba `min(widths)` y `min(heights)` de listas construidas independientemente sobre todas las orientaciones permitidas, así que podían venir de orientaciones distintas y describir una pieza que no existe (el caso medido: pieza de 1200×100 con `angles=(0, 90)` sobre placa útil 960×960 daba "mide al menos 100.0 x 100.0 mm", que sí entraría). Se cambió para elegir una única orientación: la que minimiza `max(ancho, alto)` (la que más cerca estuvo de entrar), y reportar su ancho y alto reales de esa misma orientación. El área útil de la placa se sigue informando igual que antes.

## Hallazgo 3 (IMPORTANTE) — `PackResult.unplaced` como campo muerto

Se confirmó por búsqueda en todo el proyecto (`grep -rn "unplaced"`) que el único código que asignaba o mutaba el campo era el `default_factory=list` de su propia definición; `pack()` sólo tiene dos desenlaces (coloca todo, abriendo placas, o lanza `PartTooLargeError` para toda la llamada), sin ningún camino de resultado parcial. Se eliminó el campo `unplaced` de `PackResult` en `src/nesting/engine/packer.py`. Las únicas referencias externas eran dos aserciones en `tests/engine/test_packer.py` (`test_a_single_part_fits_on_one_sheet` y `test_parts_spill_onto_a_second_sheet`); se quitó únicamente la línea `assert result.unplaced == []` de cada una, sin tocar el resto de esos tests.

## Tests agregados

- `tests/geometry/test_transform.py`: rotaciones exactas de 0/90/180/270/360° con `==` (sin aproximación), cuatro rotaciones de 90° sucesivas volviendo exactamente al punto original, y una verificación de que ángulos no múltiplos de 90 (45°, 37°) siguen usando `math.cos`/`math.sin` igual que antes.
- `tests/geometry/test_verify.py`: dos piezas que se tocan en un borde compartido con `sep=0` (simulando el ruido de ~`1e-11`–`1e-8` mm² con un solapamiento sintético de `1e-10` mm de ancho) sin violación; un solapamiento real de 1 mm² (`1mm x 1mm`) sí reportado; una pieza enteramente contenida en otra sigue reportando `overlap`.
- `tests/engine/test_packer.py`: la reproducción exacta del hallazgo 1 (`sep=0.0`, `margin=0.0`, `angles=(90.0,)`, `rect_part(0,500,300)` + `rect_part(1,400,250)`) pasando `verify` con cero violaciones; un barrido de 3 separaciones × 6 ángulos × 2 valores de espejado (36 combinaciones) todas pasando `verify`; y el mensaje de `PartTooLargeError` para una pieza de 1200×100 con `angles=(0,90)` mencionando "1200" y "100.0" (una orientación real).

## Corrida de la suite completa

```
$ .venv/bin/pytest
........................................................................ [ 35%]
........................................................................ [ 71%]
..........................................................               [100%]
202 passed in 1.10s
```

193 preexistentes + 9 nuevos = 202, todos en verde. Ningún test existente fue modificado salvo las dos líneas de `unplaced` señaladas arriba.

## Verificaciones manuales

**1. Reproducción del hallazgo 1 (antes daba `[Violation(kind='overlap', ...)]`, ahora cero violaciones):**

```
$ .venv/bin/python verify_repro.py
Hallazgo 1 repro -> violations: []
OK: cero violaciones
```

**2. Barrido de 45 combinaciones aleatorias** (4 materiales — mdf 1000×1000, multilam 1220×2440 con veta estricta, plywood 1525×1525, mdf_chico 600×600 —, `sep` en {0, 0.5, 2, 6}, `margin` en {0, 5, 20}, 7 conjuntos de ángulos incluyendo combinaciones con 37°/45° no múltiplos de 90, espejado sí/no, 3 a 10 piezas por corrida mezclando rectángulos, piezas cóncavas en L y piezas con agujero circundante):

```
$ .venv/bin/python random_sweep.py
[01] OK material=mdf_chico sep=0.0 margin=5.0 angles=(37.0, 90.0) mirror=False n_parts=6 sheets=2 violations=0
...
[45] OK material=plywood sep=0.0 margin=20.0 angles=(0.0, 45.0, 90.0) mirror=False n_parts=4 sheets=1 violations=0

Total combinaciones verificadas: 45
Combinaciones con violaciones: 0
OK: cero violaciones en todas las combinaciones
```

**3. Mensaje de `PartTooLargeError` para la pieza de 1200×100 con `angles=(0, 90)` sobre placa útil 920×920 (margen 20 sobre 960×960):**

```
$ .venv/bin/python too_large.py
Mensaje: la pieza 0 no entra en una placa vacia: mide al menos 1200.0 x 100.0 mm en su mejor orientacion, y el area util de la placa mdf es 920.0 x 920.0 mm (margen 20.0 mm).
```

El mensaje ahora es coherente: menciona 1200×100 mm, una orientación real de la pieza, en vez de mezclar el ancho de una orientación con el alto de otra.

## Estado final (addendum)

`DONE`. 202/202 tests en verde (193 preexistentes + 9 nuevos). Los tres hallazgos fueron arreglados, con doble capa en el hallazgo crítico (trigonometría exacta en `transform.py` + umbral de área en `verify.py`), y las tres verificaciones manuales pedidas dieron el resultado esperado.
