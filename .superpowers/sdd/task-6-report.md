# Task 6: Árbol de contención — informe

## Archivos tocados

- `src/nesting/model/part.py` — ampliado el import (`Point, Transform`), agregadas las clases `Part` y `Placement` y el helper `_shoelace_area`. No se tocó `Contour` ni `OpenChain`.
- `src/nesting/geometry/nesting_tree.py` — nuevo. `build_parts`, `_find_parents`, `_depth_of`.
- `tests/geometry/test_nesting_tree.py` — nuevo, 11 tests, copiados literalmente del brief.

## Ciclo TDD

### Paso 2 — test corriendo antes de implementar (falla como se esperaba)

```
$ .venv/bin/pytest tests/geometry/test_nesting_tree.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 0 items / 1 error

==================================== ERRORS ====================================
_____________ ERROR collecting tests/geometry/test_nesting_tree.py _____________
ImportError while importing test module '/Users/raulo/cut-placement/tests/geometry/test_nesting_tree.py'.
...
E   ModuleNotFoundError: No module named 'nesting.geometry.nesting_tree'
=========================== short test summary info ============================
ERROR tests/geometry/test_nesting_tree.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.04s ==============================
```

Coincide con lo esperado por el brief.

### Paso 4/5 — implementación literal del brief, primer intento: CUELGA

Al implementar `Part`, `Placement` y `nesting_tree.py` copiando el código del brief tal cual, `pytest tests/geometry/test_nesting_tree.py -v` no terminaba: quedaba en un loop de CPU al 99% sin salida, incluso después de más de 2 minutos. Investigué con `sample` (macOS) sobre el proceso colgado y con un script de reproducción directo (bypaseando pytest) usando `signal.alarm` para capturar el stack en el momento del cuelgue.

El `traceback.print_stack` en el momento del alarm mostró el punto exacto:

```
File ".../nesting_tree.py", line 26, in build_parts
    depths = [_depth_of(i, parents) for i in range(len(contours))]
File ".../nesting_tree.py", line 84, in _depth_of
    while current is not None:
```

Causa raíz encontrada por inspección directa: el test `test_depth_two_becomes_an_independent_part` arma tres cuadrados **concéntricos** (mismo centro geométrico, offset de 20mm cada uno: (0,0,100), (20,20,60), (40,40,20), los tres centrados en (50,50)). Con esa geometría, `Polygon.representative_point()` de shapely devuelve el **mismo punto (50,50)** para los tres contornos (para un rectángulo, el punto representativo coincide con el centroide). Verificado en consola:

```
0 probe POINT (50 50) area 10000.0
  candidate 0 contains True area 10000.0
  candidate 1 contains True area 3600.0
  candidate 2 contains True area 400.0
1 probe POINT (50 50) area 3600.0
  candidate 0 contains True area 10000.0
  candidate 1 contains True area 3600.0
  candidate 2 contains True area 400.0
2 probe POINT (50 50) area 400.0
  candidate 0 contains True area 10000.0
  candidate 1 contains True area 3600.0
  candidate 2 contains True area 400.0
```

El algoritmo del brief elige como "padre" al contenedor de **menor área** que contiene el punto de prueba, sin exigir que ese contenedor sea realmente más grande que el propio contorno. Como el punto de prueba del cuadrado exterior (índice 0) también cae dentro del cuadrado más interno (índice 2, porque son concéntricos), el algoritmo asigna `parents[0] = 2`. De igual modo `parents[1] = 2` y `parents[2] = 1`. Esto produce un ciclo `1 → 2 → 1 → ...` que `_depth_of` recorre para siempre.

## Desviación respecto del brief (con motivo)

Agregué una guarda en `_find_parents`: un candidato solo puede ser padre si su área es **estrictamente mayor** que la del contorno evaluado (`if polygons[candidate].area <= polygon.area: continue`). Es una condición necesaria de cualquier contención real (un polígono no puede contener genuinamente a otro más grande), así que descarta exactamente los falsos positivos que produce la coincidencia del punto representativo en contornos concéntricos, sin afectar ningún caso de contención legítima. Con la guarda, los 11 tests —incluidos los de profundidad 2 y 3, que están armados justamente con contornos concéntricos— pasan y dan la jerarquía esperada por el brief.

Diff conceptual en `_find_parents` (dentro del `for candidate in tree.query(probe)`):

```python
if candidate == index:
    continue
# Un ancestro genuino tiene área estrictamente mayor: un polígono más chico
# no puede contener realmente a uno más grande. Sin esta guarda, contornos
# concéntricos que comparten el mismo centroide (y por lo tanto el mismo
# representative_point()) hacen que un anillo bien anidado "contenga" el
# punto de prueba de un anillo exterior, generando un ciclo de padres y un
# loop infinito en _depth_of.
if polygons[candidate].area <= polygon.area:
    continue
if not polygons[candidate].contains(probe):
    continue
```

No se modificó ninguna firma pública, ni la regla de profundidad, ni el criterio de robustez pedido (seguir usando `representative_point()` en vez de `contains()` polígono-contra-polígono). El resto del código es idéntico al del brief.

## Paso 5 — test del módulo, ya con el fix: PASA

```
$ .venv/bin/pytest tests/geometry/test_nesting_tree.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 11 items

tests/geometry/test_nesting_tree.py ...........                          [100%]

============================== 11 passed in 0.04s ==============================
```

## Paso 6 — suite completa

```
$ .venv/bin/pytest --tb=short
........................................................................ [ 86%]
...........                                                              [100%]
83 passed in 0.78s
```

72 tests preexistentes + 11 nuevos = 83 passed. El brief anticipaba "48 passed" en este paso, pero esa cifra corresponde al estado del proyecto en el momento en que se escribió el brief; el enunciado de la tarea (que ya venía con "72 tests en verde" antes de empezar) deja claro que el número real de base es 72, así que 83 es la cifra correcta para este repo. No es una desviación de comportamiento, solo una discrepancia de un número desactualizado en el texto del brief.

## Paso 7 — commit

Omitido a pedido explícito: el proyecto no usa git.

---

# Adenda: detección de geometría inválida (agujero parcialmente superpuesto)

## Hallazgo original

`_find_parents` decide contención con `representative_point()` del contorno
interno — un criterio deliberado para tolerar anillos que comparten un tramo
de borde con su contenedor (ver el desvío del TDD arriba: es justamente lo que
hizo falta para no romper con contornos concéntricos). Pero ese mismo criterio
acepta como agujero pleno a un contorno que solo se **superpone
parcialmente** con su supuesto exterior: si el punto de prueba cae adentro,
alcanza, aunque buena parte del contorno esté afuera. El área "agujero" que se
resta después (`Part.area`) queda mal calculada sin ningún aviso, y esa área
alimenta cuánto material hace falta comprar.

## Cambios

- `src/nesting/geometry/nesting_tree.py`:
  - Nueva excepción `OverlappingContourError(Exception)`, exportada desde el
    módulo, con mensaje en español.
  - Nueva función `_assert_hole_is_contained(hole_index, owner_index,
    contours, polygons)`, llamada desde `build_parts` justo antes de agregar
    cada índice a `holes_by_owner` (es decir, en el mismo punto donde hoy se
    decide "este contorno de profundidad impar es agujero de tal owner").
    Calcula `hole_polygon.difference(owner_polygon)` (con shapely) y compara
    su área contra una tolerancia; si la excede, arma el mensaje de error con
    los `entity_ids` de agujero y exterior, un punto representativo de la
    zona conflictiva y su bounding box aproximado, y lanza
    `OverlappingContourError`.
  - No se tocó la firma de `build_parts` ni el criterio de
    `representative_point()` en `_find_parents` — ese sigue existiendo tal
    cual, porque es lo que permite que un agujero tangente por borde o por un
    solo punto llegue a candidatearse como agujero en primer lugar. El chequeo
    nuevo es una segunda verificación, más estricta, que corre *después* de
    que `_find_parents` ya decidió el padre.

### Umbrales elegidos

```python
_RELATIVE_OVERLAP_TOLERANCE = 1e-6       # una parte en un millón del área del agujero
_ABSOLUTE_OVERLAP_TOLERANCE_MM2 = 1e-3   # piso absoluto, mm²
tolerance = max(_RELATIVE_OVERLAP_TOLERANCE * hole_polygon.area,
                _ABSOLUTE_OVERLAP_TOLERANCE_MM2)
```

Se rechaza cuando `outside.area > tolerance`, donde `outside` es la parte del
agujero que cae fuera del exterior.

- **Relativa (`1e-6`)**: una parte en un millón del área del propio agujero.
  Para geometrías con coordenadas en el rango normal de un dibujo CNC (cientos
  a miles de mm), el ruido de punto flotante de una operación booleana de
  shapely en doble precisión es muchísimo más chico que eso — así que esta
  tolerancia absorbe el ruido sin abrir la puerta a un desborde real, que en
  los casos que importa detectar es varios órdenes de magnitud más grande (en
  la reproducción del hallazgo, el desborde es el 20% del área del agujero,
  no una parte en un millón).
- **Absoluta (`1e-3` mm²)**: piso para cuando el agujero mismo es diminuto y
  la tolerancia relativa colapsaría por debajo del ruido de punto flotante
  (p.ej. un agujero de 0.0001 mm²: el 1e-6 de eso es 1e-10, menor que el ruido
  esperable de la resta booleana). Un milésimo de mm² es un cuadrado de
  ~0.03 mm de lado — muy por debajo de cualquier tolerancia de corte CNC real,
  así que nunca corresponde a un desborde intencional del dibujo, solo a
  ruido numérico.

Ambas constantes están declaradas con nombre y comentario en el módulo, junto
a la definición de `OverlappingContourError`.

## Tests agregados (`tests/geometry/test_nesting_tree.py`, al final, sin tocar los 11 originales)

1. `test_partially_overlapping_contour_raises_instead_of_becoming_a_hole` —
   reproduce exactamente el caso del hallazgo (exterior (0,0)-(30,30), agujero
   (10,10)-(35,25)); verifica que lanza `OverlappingContourError` y que el
   mensaje menciona los `entity_ids` de ambos contornos (0 y 1 en el test).
2. `test_hole_tangent_to_exterior_along_a_shared_edge_is_not_rejected` —
   agujero que comparte un tramo del borde izquierdo del exterior (tangente
   por dentro); no debe lanzar.
3. `test_hole_touching_exterior_boundary_at_a_single_point_is_not_rejected` —
   un rombo cuyo vértice inferior toca el borde exterior en un solo punto; no
   debe lanzar.
4. `test_deep_concentric_rings_do_not_raise` — seis anillos concéntricos bien
   anidados (profundidad par/impar alternada); no debe lanzar.
5. `test_tiny_hole_correctly_nested_does_not_raise` — agujero de 0.001×0.001
   bien anidado, para confirmar que el piso absoluto de tolerancia no genera
   falsos positivos en agujeros diminutos.

## Resultado de los tests

### `pytest tests/geometry/test_nesting_tree.py -v`

```
$ .venv/bin/pytest tests/geometry/test_nesting_tree.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 16 items

tests/geometry/test_nesting_tree.py ................                     [100%]

============================== 16 passed in 0.08s ==============================
```

11 originales (sin modificar) + 5 nuevos = 16 passed.

### `pytest -q` (suite completa)

```
$ .venv/bin/pytest -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 88 items

tests/geometry/test_chaining.py ..........................               [ 29%]
tests/geometry/test_flatten.py .......................                   [ 55%]
tests/geometry/test_nesting_tree.py ................                     [ 73%]
tests/geometry/test_transform.py ...............                         [ 90%]
tests/model/test_entities.py ......                                      [ 97%]
tests/test_smoke.py ..                                                   [100%]

============================== 88 passed in 0.77s ==============================
```

(Nota: con `-q` puro este pytest 9.1.1 en este entorno no imprime la línea de
resumen final "N passed" en la captura de salida, aunque sí imprime los `.` de
progreso y el exit code es 0 — usé `-v` para confirmar el conteo con la línea
de resumen visible. 72 preexistentes + 16 de `test_nesting_tree.py` = 88.)

## Verificación manual (`python -c`)

**Caso 1 — repro del hallazgo (debe lanzar):**

```
=== Caso 1: repro del desborde (debe lanzar) ===
OverlappingContourError: Dos contornos se superponen parcialmente en vez de estar uno anidado dentro del otro: el contorno con entity_ids [20] se acepta como agujero del contorno con entity_ids [10], pero una parte de área 75 mm² queda afuera de ese exterior. Zona conflictiva cerca de (32.50, 17.50), dentro del rectángulo aproximado (30.00, 10.00)-(35.00, 25.00). Revisá esos entity_ids en el dibujo original.
```

Lanza como se esperaba, con los `entity_ids` (10 y 20 en esta prueba manual)
y coordenadas aproximadas de la zona conflictiva.

**Caso 2 — agujero tangente por borde compartido (NO debe lanzar):**

```
=== Caso 2: agujero tangente por borde compartido (NO debe lanzar) ===
OK, no lanzo. parts: 1 holes: 1
```

No lanza, y el agujero tangente se sigue aceptando como agujero de la pieza,
tal como antes del cambio — confirma que no se rompió el caso que
`representative_point()` existe para tolerar.

## Archivos tocados en esta adenda

- `src/nesting/geometry/nesting_tree.py` — agregado `OverlappingContourError`,
  las constantes de tolerancia y `_assert_hole_is_contained`; una línea nueva
  dentro de `build_parts` que la invoca. No se tocó la firma de `build_parts`
  ni `_find_parents`.
- `tests/geometry/test_nesting_tree.py` — agregados 5 tests al final; los 11
  originales quedaron intactos.
