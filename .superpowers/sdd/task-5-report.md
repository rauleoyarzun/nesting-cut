# Informe Tarea 5: Encadenado de contornos

## Archivos creados

- `src/nesting/model/part.py` — `Contour` y `OpenChain`, copiados literalmente del brief.
- `src/nesting/geometry/chaining.py` — `chain_contours` y helpers, del brief, con una corrección (ver "Desviaciones").
- `tests/geometry/test_chaining.py` — los 12 tests del brief, sin cambios.

## Ciclo TDD

### Paso 2: correr el test antes de implementar (falla esperada)

```
$ .venv/bin/pytest tests/geometry/test_chaining.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 0 items / 1 error

==================================== ERRORS ====================================
_______________ ERROR collecting tests/geometry/test_chaining.py _______________
ImportError while importing test module '<repo>/tests/geometry/test_chaining.py'.
Traceback:
tests/geometry/test_chaining.py:3: in <module>
    from nesting.geometry.chaining import chain_contours
E   ModuleNotFoundError: No module named 'nesting.geometry.chaining'
=========================== short test summary info ============================
ERROR tests/geometry/test_chaining.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.05s ===============================
```

Falla como se esperaba en el brief.

### Primera corrida tras implementar el código del brief tal cual (1 falla)

```
tests/geometry/test_chaining.py .......F....                             [100%]

_________ test_reversed_duplicate_segments_are_discarded _________
    assert duplicates == 1
E   assert 0 == 1
```

### Paso 5: correr el test después de la implementación corregida (pasa)

```
$ .venv/bin/pytest tests/geometry/test_chaining.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 12 items

tests/geometry/test_chaining.py ............                             [100%]

============================== 12 passed in 0.28s ==============================
```

### Suite completa del proyecto

```
$ .venv/bin/pytest
..........................................................               [100%]
58 passed in 1.00s
```

## Desviaciones respecto del brief

**`_drop_duplicates`: el cálculo del "punto medio" en la clave de deduplicación tenía un bug que rompía justamente el test que ejercita ese caso (`test_reversed_duplicate_segments_are_discarded`).**

El código del brief usaba:

```python
head = _snap(points[0], tol)
tail = _snap(points[-1], tol)
middle = _snap(points[len(points) // 2], tol)
key = (tuple(sorted((head, tail))), middle, len(points))
```

Para un segmento de 2 puntos, `len(points) // 2 == 1`, así que `middle` en realidad apunta al **último punto** (la cola), no a un punto invariante ante la inversión. Al invertir el mismo tramo, `points[1]` pasa a ser el extremo opuesto, así que `middle` cambia de valor y la clave deja de coincidir con la del original: el duplicado invertido no se detectaba (`duplicates == 0` en vez de `1`).

Esto no es una interpretación ambigua del brief ni una mejora estética: es el código exacto que el brief pide, ejercitado por el test exacto que el brief pide, y falla. Tuve que corregirlo para que el propio contrato del brief se cumpla.

**Corrección aplicada:** antes de tomar el "medio", pongo la lista de puntos en una dirección canónica (la que arranca por el extremo snapeado menor); así un tramo y su copia invertida seleccionan el mismo punto físico como "medio", sin importar la paridad de la cantidad de puntos.

```python
head = _snap(points[0], tol)
tail = _snap(points[-1], tol)
canonical = points if head <= tail else tuple(reversed(points))
middle = _snap(canonical[len(canonical) // 2], tol)
key = (min(head, tail), max(head, tail), middle, len(points))
```

Verificado manualmente contra el caso conflictivo: segmento original `[(0,0),(10,0)]` y su reverso `[(10,0),(0,0)]` producen ahora la misma clave. El resto de los tests (duplicado exacto, contornos con más de 2 puntos, splines aplanadas, etc.) siguen funcionando porque `canonical` para un tramo no invertido es el propio `points`, y la comparación de extremos snapeados es estable.

No hubo otras desviaciones: firmas de `Contour`, `OpenChain` y `chain_contours` idénticas al brief; se omitió el paso 6 (commit de git) según instrucción explícita, dado que el proyecto no usa git.

## Dudas pendientes

Ninguna que bloquee el avance. Cosas a tener presentes para tareas siguientes:

- El heurístico de deduplicación (extremos + un único punto medio + cantidad de puntos) es una aproximación: dos tramos distintos que por casualidad compartan extremos, cantidad de puntos y ese punto medio snapeado se tratarían como duplicados. Es el mismo riesgo que ya asumía el brief original; solo corregí el bug de invariancia ante inversión, no cambié el criterio de fondo.
- No verifiqué el comportamiento con `Arc`/`Bezier` reales (solo con las polilíneas aplanadas que exige la firma), ya que el aplanado es responsabilidad de un módulo anterior (`geometry/flatten.py`) y las pruebas de esta tarea operan directamente sobre `tuple[Point, ...]`.

---

## Addendum: fix de revisión (Hallazgo 1 crítico + Hallazgo 2 importante)

Ambos hallazgos de la revisión de código sobre `src/nesting/geometry/chaining.py` generaban geometría corrupta emitida sin ningún aviso (`OpenChain` ni error). Se corrigieron los dos, se agregaron 6 tests nuevos a `tests/geometry/test_chaining.py` (sin tocar los 12 existentes) y se verificó todo. No se hizo commit (el proyecto no usa git).

### Qué cambió

**Hallazgo 1 — `_find_unused_neighbour` sin criterio de desempate.**

Tomaba el primer candidato que devolvía `tree.query_ball_point`, sin desempate, así que un vértice compartido entre dos contornos distintos (pieza+agujero tangentes, dos piezas que se tocan en una esquina) podía enganchar con el contorno equivocado y fusionar dos piezas en un único "contorno" en forma de moño.

Cambié la firma para que reciba la cadena acumulada (`points`) en vez de solo el punto objetivo, y agregué desempate determinístico en dos niveles quando hay más de un candidato sin usar:

1. Si el extremo lejano de un candidato cae dentro de tolerancia del primer punto de la cadena (`points[0]`), ese candidato cierra la cadena actual y gana.
2. Si ninguno cierra, gana el candidato cuyo primer tramo forma el menor ángulo de giro respecto de la dirección de llegada (calculada con los dos últimos puntos de la cadena vs. los dos primeros puntos del candidato, ya orientado según el extremo por el que engancha).
3. Empate exacto de ángulo (o ningún punto de referencia disponible) se resuelve por el menor índice de tramo, para que el resultado no dependa del orden de iteración del KD-tree.

Se agregaron los helpers `_far_endpoint`, `_direction` y `_turn_angle`. `_extend_forward` ahora pasa `points` completo en vez de `points[-1]`.

**Hallazgo 2 — `_drop_duplicates` no deduplicaba anillos ya cerrados con cantidad par de puntos.**

Cuando el tramo ya llega cerrado (`head == tail` snapeado), la comparación `head <= tail` nunca desempata, así que `canonical` nunca se invertía, y la invariancia de `canonical[len//2]` ante la reversión solo se cumple con cantidad impar de puntos. Un anillo cerrado par y su copia invertida no se detectaban como duplicado.

Separé el caso: cuando `head == tail`, la clave se construye con la tupla ordenada de **todos** los puntos snapeados del anillo salvo el punto de cierre repetido (`points[:-1]`) más la cantidad de puntos (`len(points)`, incluyendo el cierre, para no confundir anillos de distinta cardinalidad). Excluir el punto de cierre repetido es necesario porque sin eso la rotación cambia cuál punto queda "duplicado" en la lista completa y rompe la invariancia ante rotación; usar el conjunto ordenado de los puntos restantes sí es invariante ante rotación y reversión, que es la simetría real de un anillo. Los tramos abiertos (`head != tail`) siguen usando la clave anterior (extremos + punto medio canonicalizado + cantidad de puntos), sin cambios de comportamiento. Se etiquetaron las dos ramas de clave (`"ring"` / `"open"`) para que nunca puedan colisionar entre sí.

### Tests agregados (`tests/geometry/test_chaining.py`, al final, 12 → 18)

Hallazgo 1:
- `test_two_triangles_touching_at_one_vertex_become_two_contours`: dos triángulos que solo comparten `(10,10)`, probado con las **720** permutaciones de `itertools.permutations` sobre los 6 tramos. Geometría elegida a propósito casi recta en cada triángulo (no un cruce tipo reloj de arena, que es ambiguo por naturaleza) para que el desempate por ángulo favorezca siempre la continuación correcta. Se verifica 2 contornos de 3 puntos, sin abiertos, sin duplicados, y que los `entity_ids` de cada contorno sean exactamente los de su propio triángulo.
- `test_square_with_touching_hole_becomes_two_contours`: cuadrado exterior con agujero cuadrado tangente en un vértice → 2 contornos, `entity_ids` sin mezclar.

Hallazgo 2:
- `test_closed_ring_with_even_point_count_dedupes_against_its_reverse`: anillo cerrado de 4 puntos (par) + su reverso → `duplicates == 1`, 1 contorno.
- `test_closed_ring_with_odd_point_count_still_dedupes_against_its_reverse`: control de no-regresión con 5 puntos (impar).
- `test_closed_ring_dedupes_against_a_rotated_copy`: mismo anillo arrancando por otro vértice → duplicado.
- `test_distinct_closed_rings_with_same_point_count_are_not_deduped`: no-falso-positivo, dos anillos distintos de igual cardinalidad no se deduplican.

### Comandos corridos

```
$ .venv/bin/pytest tests/geometry/test_chaining.py -v
============================= test session starts ==============================
collected 18 items

tests/geometry/test_chaining.py ..................                       [100%]

============================== 18 passed in 0.31s ==============================
```

```
$ .venv/bin/pytest -q
................................................................         [100%]
64 passed in 0.85s
```

(64 = 58 previos + 6 nuevos; ningún otro módulo se rompió.)

### Verificación manual de las 720 permutaciones del caso de los dos triángulos

Script ad hoc (`itertools.permutations(range(6))`) contra la geometría del test, contando cuántas producen exactamente 2 contornos de 3 puntos con `entity_ids` correctos y sin mezclar:

```
correctas: 720/720
```

Antes del fix (código con el bug del Hallazgo 1, primer-candidato-sin-desempate): **320/720 (44%) fallaban** (medido por el revisor sobre su propia geometría), es decir ~400/720 correctas por casualidad según el orden en que el KD-tree devolvía los vecinos. Después del fix: **720/720 correctas**, para las dos geometrías probadas (la del test de 6 tramos y, por separado, la del cuadrado con agujero).

### Notas / limitaciones

- El desempate por ángulo (nivel 2) es un heurístico, no una garantía geométrica universal: para una configuración verdaderamente ambigua por construcción (dos piezas que se cruzan en un punto formando un "reloj de arena" perfectamente simétrico, donde seguir derecho hacia la otra pieza es tan plausible como seguir la propia) ningún criterio local puede acertar siempre. Elegí la geometría del test de forma representativa de un caso de CAD normal (continuación propia casi recta, la ajena requiere un giro mucho más brusco), no adversaria, que es exactamente el escenario que describe el hallazgo del revisor.
- No se tocó ningún otro archivo del proyecto ni los 12 tests originales.

---

## Adenda: Hallazgo A (pérdida silenciosa de tramos) y Hallazgo B (clave de anillos demasiado permisiva)

### Resumen de los cambios en `src/nesting/geometry/chaining.py`

**A1 — invariante de contabilidad.**
- Nueva excepción `ChainingInvariantError` (subclase de `RuntimeError`), con mensaje en español que nombra explícitamente los ids perdidos y/o contados de más.
- Nueva función interna `_check_invariant(input_ids, contours, open_chains, duplicate_ids)`, llamada al final de `chain_contours` (en las dos rutas de salida, incluida la de `kept` vacío) antes de devolver: compara con `collections.Counter` el multiconjunto de `entity_ids` de entrada contra la unión de `entity_ids` de `Contour` + `OpenChain` + los descartados por duplicado, y explota si no coinciden.
- `_drop_duplicates` ahora devuelve `(kept, duplicate_ids)` — la lista de ids descartados, no solo un contador — para que el invariante tenga con qué comparar. Es un cambio de firma **interno** (la función es privada del módulo); la firma pública `chain_contours(...) -> (contours, open_chains, duplicates: int)` **no cambió**, precisamente para no romper los 18 tests protegidos que desempaquetan un 3-tuple (varios de ellos, incluido `test_empty_input`, comparan contra `([], [], 0)` literal).
- Los "contornos" degenerados (cierran geométricamente pero colapsan a menos de `MIN_CONTOUR_POINTS` puntos distintos) ya **no se descartan en silencio** en `_emit`: se emiten como `OpenChain` (con el `gap` real, que en este caso es chico, ya que sí llegaron a cerrar). Elegí esta opción (emitir como `OpenChain`) en vez de agregar un 4º valor de retorno porque un 4º valor de retorno hubiera roto el desempaquetado de 3 elementos que usan los 18 tests protegidos — no era compatible con la restricción de no tocarlos.

**A2 — desempate unificado.**
- Se eliminó la prioridad ciega "el candidato que cierra gana siempre" (`_find_unused_neighbour`) y el corte automático por `_is_closed` a mitad del recorrido en `_extend_forward`.
- Nueva función interna `_next_action(points, paths, used, tree, tol)`, que en cada paso decide entre: `("attach", index, at_tail)`, `("close", None, None)` o `None` (fin, no cierra). Reglas:
  - Un candidato de "cierre" (un tramo sin usar cuyo extremo lejano cae a `tol` del arranque) que produciría un anillo de menos de `MIN_CONTOUR_POINTS` puntos distintos **se excluye de la lista de candidatos**: nunca puede ganar, ni por índice ni por ángulo, porque directamente no compite.
  - Entre los candidatos que quedan (continuar con un tramo real, o cerrar ya mismo si la cola actual ya está a `tol` del arranque y el anillo resultante sería válido), se elige el de **menor ángulo de giro** respecto de la dirección de llegada — el mismo criterio angular que ya existía para desempatar entre tramos.
  - Empate exacto de ángulo entre dos tramos reales: gana el de menor índice (sin cambios respecto del comportamiento anterior).
  - Empate exacto de ángulo entre "cerrar" y un tramo real: gana cerrar (se le asigna una clave de desempate -1, menor que cualquier índice real). Justificación y verificación empírica: en `test_square_with_touching_hole_becomes_two_contours` el candidato de cierre y el tramo 4 del agujero empatan exactamente en 90°, y hace falta que gane el cierre para no fusionar el cuadrado exterior con el agujero — el test protegido sigue pasando con esta regla.
- `_extend_forward` ahora solo se detiene cuando `_next_action` devuelve `None` o `("close", ...)`; ya no corta apenas la cola entra en tolerancia del arranque a mitad de un tramo largo (caso "C"/espiral).

### Hallazgo B — clave de anillos bajo el grupo diedral

- Nueva función `_ring_shape_key(points, tol)`: en vez de `sorted(puntos snapeados)`, prueba las `n` rotaciones de la secuencia de puntos snapeados y las `n` rotaciones de su inversa, y se queda con el mínimo lexicográfico. Es O(n²) en la cantidad de puntos del anillo; comentario en el código explica por qué es aceptable (anillos individuales cortos) y que Booth resuelve esto en O(n) si algún día hace falta.
- `_drop_duplicates` usa esta clave para el caso `head == tail` (anillo ya cerrado en una sola entidad), reemplazando `sorted(...)`.

### Tests agregados (`tests/geometry/test_chaining.py`, 5 nuevos, los 18 originales sin tocar)

1. `test_spurious_returning_segment_does_not_steal_the_real_continuation` — bifurcación con tramo espurio que vuelve a 0.09 mm del arranque (Hallazgo A, crítico): el cuadrado real se reconstruye entero con sus 4 ids, el tramo espurio queda como `OpenChain` propio, nada se pierde.
2. `test_tight_c_shape_passing_near_its_own_start_does_not_split` — "C" muy cerrada de 5 tramos donde el tramo intermedio pasa a 0.054 mm del arranque pero el trazado sigue de largo: antes se partía en un contorno espurio de 3 puntos + un chain abierto separado; ahora queda como un solo `OpenChain` con los 5 ids.
3. `test_accounting_invariant_holds_across_several_scenarios` — corre el helper `_assert_all_ids_accounted_for` (verifica ids sin pérdidas ni repetidos) sobre 5 escenarios: cuadrado simple, cuadrado con agujero tangente, duplicado exacto, y los dos adversariales de arriba.
4. `test_invariant_checker_raises_on_a_manufactured_mismatch` — llama directo a `chaining._check_invariant` con una entrada armada a mano (le falta un id / le sobra un id) y verifica que `ChainingInvariantError` explota con el mensaje esperado. Ver más abajo por qué no se encontró una entrada real para `chain_contours` que dispare esto.
5. `test_square_and_bowtie_with_the_same_four_points_are_not_deduped` — Hallazgo B: un cuadrado y un moño con los mismos 4 puntos en otro orden ya no se deduplican (`duplicates == 0`, 2 contornos). Los tests de anillo rotado/invertido (ya existentes) se dejaron intactos y siguen pasando.

### Comandos y salida

```
$ .venv/bin/pytest tests/geometry/test_chaining.py -v
============================= test session starts ==============================
collected 23 items

tests/geometry/test_chaining.py .......................                  [100%]

============================== 23 passed in 0.32s ==============================
```

(23 = 18 originales + 5 nuevos, todos pasando.)

```
$ .venv/bin/pytest -q
............................................................ [69 tests]
69 passed in 1.09s
```

(69 = 64 previos + 5 nuevos; ningún otro módulo se rompió.)

### Verificación manual de las 720 permutaciones (post-cambio de desempate)

Mismo script ad hoc que antes, ahora contra el código con el desempate unificado (cierre compite por ángulo, ya no gana ciegamente):

```
720/720 permutaciones correctas
```

El criterio angular puro no empeoró el resultado: sigue siendo 720/720, porque en esta geometría (triángulo A casi recto, triángulo B casi recto y perpendicular) el giro de "seguir el propio triángulo" es siempre mucho menor que el de "saltar al otro triángulo", en las 720 combinaciones de orden.

### ¿Se logró disparar el invariante de contabilidad a través de `chain_contours` (no de la función interna)?

**No.** Con la estructura actual, la cuenta cierra por construcción: cada tramo de `kept` pasa por `used[i] = True` exactamente una vez antes de terminar en un `chain_ids` que se emite exactamente una vez (a `contours` o a `open_chains`, nunca a ambos ni a ninguno — los degenerados ahora van a `open_chains` en vez de perderse), y `_drop_duplicates` devuelve explícitamente, uno por uno, los ids que descarta. No encontré ninguna combinación de segmentos de entrada que deje un id sin pasar por ninguna de esas tres rutas. Por eso el test 4 de la lista de arriba prueba el mecanismo llamando directo a la función interna `_check_invariant` con una entrada manipulada a mano (a la que le falta un id, o le sobra uno) en vez de vía `chain_contours`: confirma que el chequeo efectivamente explota con el mensaje correcto cuando algo no cierra, sin necesidad de (ni ser capaz de) romper la invariante desde afuera.

---

## Adenda final: Hallazgo A3 (la guarda anti-degeneración descalificaba de más) + 2 lagunas de cobertura

Última vuelta sobre `src/nesting/geometry/chaining.py`. Un defecto (importante) y dos lagunas de cobertura (una importante, una menor). Los 23 tests protegidos de `tests/geometry/test_chaining.py` **no se tocaron**; se agregaron 3 tests nuevos al final (23 → 26).

### Qué cambió en `src/nesting/geometry/chaining.py`

**El defecto — `_next_action` sacaba al candidato de `candidates` por completo, no solo de la opción de cerrar.**

En la versión de la ronda anterior (Hallazgo A2), el bloque que arma `candidates` a partir de `raw_candidates` hacía, para cada candidato sin usar que toca la cola de la cadena:

```python
far = _far_endpoint(paths[index], at_tail)
if math.dist(far, start) <= tol:
    # ...
    if _ring_point_count(trial, tol) < MIN_CONTOUR_POINTS:
        continue          # <-- BUG: esto saca al candidato de TODA la competencia
candidates.append((index, at_tail))
```

El `continue` está *fuera* del `if`, así que cuando el extremo lejano de un candidato cae cerca del arranque (`start`) **y** cerrar ahí formaría un anillo degenerado (menos de `MIN_CONTOUR_POINTS` puntos distintos), el candidato se descarta enteramente — no solo como opción de cierre, sino también como adjunción normal. Si en ese punto era el único candidato, `_next_action` devolvía `None` en vez de una adjunción, y dos tramos físicamente conectados terminaban en dos `OpenChain` separados y sin relación aparente, cada uno con un `gap` engañoso (la longitud del propio tramo en vez de la distancia real al vecino).

Reproducción exacta del brief: `id0` = `(0,0)-(10,0)`, `id1` = `(10,0)-(0.08,0)`. Están conectados en `(10,0)`, pero el otro extremo de `id1` cae a 0.08 mm del arranque de `id0`, cerrando (si se usara para eso) un anillo de 2 puntos. Antes del fix: dos `OpenChain`, `(0,)` con `gap=10.0` y `(1,)` con `gap=9.92`. Se confirmó por mutación manual (revirtiendo el fix en una copia aparte del módulo) que efectivamente reproduce este resultado.

**Corrección aplicada:** se separó la pregunta "¿este candidato cierra la cadena (ahora mismo, sin adjuntar nada)?" de "¿puede este candidato adjuntarse como continuación?". La segunda pregunta ya no depende en absoluto de si su extremo lejano cae cerca del arranque: `candidates` pasa a ser, simplemente, todo lo que el KD-tree devuelve sin usar en la cola, sin ningún filtro adicional:

```python
candidates: list[tuple[int, bool]] = []
for endpoint_index in tree.query_ball_point(target, tol):
    index, which_end = divmod(endpoint_index, 2)
    if used[index]:
        continue
    candidates.append((index, which_end == 1))
```

La guarda anti-degeneración *sigue existiendo*, pero ahora vive únicamente donde corresponde: en el cálculo de `can_close` (la opción "cerrar sin consumir nada"), que ya comprobaba `_ring_point_count(points, tol) >= MIN_CONTOUR_POINTS` sobre los puntos acumulados *actuales* — sin cambios en esa parte. Si un candidato cuyo extremo lejano cae cerca del arranque efectivamente se adjunta (porque gana la competencia de ángulo o es la única opción), la cola queda entonces cerca del arranque; la próxima vez que se llame a `_next_action` sobre esa cola, `can_close` vuelve a evaluar el mismo criterio de no-degeneración con los puntos ya actualizados. No hace falta duplicar el chequeo por adelantado: es exactamente la misma cuenta, solo que hecha un paso después, cuando realmente hace falta.

Como consecuencia, el helper `_far_endpoint` quedó sin ningún llamador y se eliminó.

Cuidados explícitos para no reintroducir bugs de rondas anteriores (verificados, ver más abajo):
- Desempate determinístico ante empate exacto de ángulo (gana el menor índice de tramo, y "cerrar" sigue ganando empates contra una adjunción real): sin cambios en esa lógica, y `test_square_with_touching_hole_becomes_two_contours` (que depende de ese empate) sigue pasando.
- Invariante de contabilidad: sin cambios en `_check_invariant` ni en cómo se llama; se re-verificó con los 23+3 tests y con el fuzz de 600 casos.
- Dos triángulos tangentes: se volvió a correr el script de las 720 permutaciones — sigue 720/720.

### Laguna de cobertura 1 (importante) — el mecanismo central de A2 no estaba testeado

Se agregó `test_valid_non_degenerate_close_competes_by_angle_against_real_continuation`: un pentágono real de 5 tramos (`ids 0-4`) más un tramo espurio (`id 5`) que, en el tercer vértice del recorrido (`v2`), cerraría un anillo **válido** de 3 puntos (`v0, v1, v2` — no degenerado, a diferencia del test de bifurcación existente). En ese punto compiten por ángulo: adjuntar `id2` (el siguiente lado real del pentágono, giro suave) contra adjuntar `id5` (el tramo espurio, giro brusco de vuelta a `v0`, que además cierra un anillo válido ahí mismo). Debe ganar `id2`: el pentágono se reconstruye entero (1 contorno, 5 puntos, ids `{0,1,2,3,4}`) y `id5` queda aparte como `OpenChain` propio.

**Verificación por mutación:** se armó una copia del módulo con `_next_action` mutado para preferir incondicionalmente (sin competir por ángulo) cualquier candidato cuyo extremo lejano caiga cerca del arranque — exactamente la regresión al bug pre-A2 ("Hallazgo original punto 1") que describe el docstring de `_next_action`. Contra esa mutación, el test nuevo falla como se esperaba: los 6 tramos se fusionan en una sola cadena abierta, `entity_ids=(0, 1, 5, 4, 3, 2)`, en vez de reconocer el pentágono. Confirma que el test efectivamente ejercita — y protege — la competencia por ángulo entre cierre válido y continuación real.

### Laguna de cobertura 2 (menor) — la rama de `_emit` para un cierre degenerado que llega ya cerrado

Se agregó `test_already_closed_entity_with_too_few_points_becomes_an_open_chain`: una sola entidad que ya llega cerrada con menos de `MIN_CONTOUR_POINTS` puntos distintos, tipo polilínea de "ida y vuelta": `((0,0), (5,5), (0,0))`, `entity_id=42`. Verifica que no lance excepción, que el id no se pierda, y que salga como `OpenChain` (no como `Contour`, ya que 2 puntos distintos no encierran área). Esta ruta de `_emit` (la del `if gap > tol` es falso, pero el anillo resultante tiene `< MIN_CONTOUR_POINTS` puntos) solo se alcanzaba antes a través del walker (por ejemplo desde el propio `test_degenerate_close_candidate_is_still_a_valid_attachment` o `test_degenerate_contours_are_dropped`), nunca desde una entidad que llega cerrada de entrada, sin pasar por `_extend_forward`.

### Comandos y salida

```
$ .venv/bin/pytest tests/geometry/test_chaining.py -v
============================= test session starts ==============================
collected 26 items

tests/geometry/test_chaining.py ..........................               [100%]

============================== 26 passed in 0.30s ==============================
```

(26 = 23 originales, sin tocar, + 3 nuevos.)

```
$ .venv/bin/pytest -q
........................................................................ [100%]
72 passed in 0.76s
```

(72 = 69 previos + 3 nuevos; ningún otro módulo se rompió.)

### Verificación manual del caso de reproducción del brief

```
$ .venv/bin/python -c "
from nesting.geometry.chaining import chain_contours
segs = [(((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (0.08, 0.0)), 1)]
contours, open_chains, dup = chain_contours(segs, 0.1)
print('contours', contours)
print('open_chains', open_chains)
print('dup', dup)
"
contours []
open_chains [OpenChain(points=((0.0, 0.0), (10.0, 0.0), (0.08, 0.0)), entity_ids=(0, 1), gap=0.08)]
dup 0
```

Un solo `OpenChain`, `entity_ids=(0, 1)`, `gap=0.08` — exactamente lo esperado. Antes del fix daba dos `OpenChain` separados (`(0,)` gap 10.0 y `(1,)` gap 9.92), verificado por mutación (ver arriba).

### Verificación manual de las 720 permutaciones (dos triángulos tangentes)

```
720/720
```

Sin regresión respecto de la adenda anterior: el fix de esta ronda no toca el criterio de desempate por ángulo ni el de menor índice, solo qué candidatos entran a competir.

### Fuzz propio (600 casos, ≥ 500 pedidos)

Script ad hoc (`fuzz_chaining.py`, en el scratchpad de la sesión) que genera, por cada caso (semilla `1000+i`, `i` de 0 a 599), una mezcla aleatoria de:

- 0–2 pares de contornos anidados (polígono exterior + polígono interior, con lados en orden y sentido aleatorios),
- 0–2 pares de polígonos tangentes (comparten un vértice a propósito),
- 0–2 cadenas abiertas (random walks que no cierran),
- 0–3 duplicados (exactos o invertidos, de un tramo elegido al azar entre los ya generados),
- 0–3 segmentos degenerados (punto único, "ida y vuelta" corta, o segmento de longitud cero),

mezclados y barajados, y corre `chain_contours` sobre el resultado verificando: que no se lance `ChainingInvariantError`, que `len(accounted) + duplicates == len(input_ids)`, que no haya ids repetidos en la salida, que (con `duplicates == 0`) el conjunto de ids de salida coincida exactamente con el de entrada, y que ningún `Contour` tenga menos de 3 puntos.

```
$ .venv/bin/python fuzz_chaining.py
Fuzz: 600/600 casos OK
Ningun fallo del invariante de contabilidad ni excepcion inesperada.
```

### Notas

- No se tocó ningún otro archivo del proyecto ni los 23 tests originales.
- El único cambio de superficie pública es la eliminación de la función interna (privada, sin uso externo) `_far_endpoint`; la firma de `chain_contours` no cambió.

