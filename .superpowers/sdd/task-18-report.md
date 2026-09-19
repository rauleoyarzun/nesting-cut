# Informe — Tarea 18: `RasterOracle` e integración

## Estado

**DONE_WITH_CONCERNS.** El motor raster está conectado detrás de la interfaz
`Oracle` (CLI y banco incluidos), la suite completa corre en verde salvo 3
tests de `test_raster_oracle.py`, y el banco muestra una mejora real y grande
del motor raster sobre el trivial — pero no en los dos puntos de referencia
que dio el usuario (`--copias 1` y `--copias 6`), donde la comparación **empata
exactamente**, por un motivo matemático que se explica abajo con números.
Investigé a fondo por qué (tres experimentos de control separados) antes de
aceptar el resultado tal cual; no aflojé ningún test.

## Archivos creados

- `src/nesting/engine/raster/oracle.py` — `RasterOracle`, implementación
  exacta del Step 3 del brief.
- `tests/engine/raster/test_raster_oracle.py` — los 12 tests del brief,
  copiados verbatim.

## Archivos modificados

- `src/nesting/cli.py` — importa `RasterOracle` en vez de `ShelfOracle`,
  usa `RasterOracle` en la llamada a `pack`, agrega `--resolucion` (default
  1.0 mm/px) y lo pasa a `NestConfig`.
- `bench/run_bench.py` — importa `RasterOracle`; el bucle de `main` ahora
  corre `[("shelf", ShelfOracle), ("raster", RasterOracle)]` por archivo,
  guarda el `total_utilization` de `shelf` como base y calcula el delta en
  puntos porcentuales para `raster`. Mantuve el manejo de `FILE_ERRORS` que
  ya existía (no está en el snippet del brief, pero es necesario para no
  tirar abajo todo el banco si un archivo viene sucio).

## Ciclo TDD seguido

1. Escribí el test (`tests/engine/raster/test_raster_oracle.py`, verbatim
   del brief).
2. Confirmé que fallaba por `ModuleNotFoundError` (no existía
   `nesting.engine.raster.oracle`).
3. Escribí `src/nesting/engine/raster/oracle.py`, verbatim del Step 3 del
   brief (sin modificaciones — ver "Desviaciones" abajo sobre por qué no
   toqué nada pese a los 3 tests que quedan en rojo).
4. Corrí el test: **9 pasan, 3 fallan** (no los 12 esperados). Investigué
   antes de tocar nada.
5. Conecté la CLI (`src/nesting/cli.py`).
6. Conecté el banco (`bench/run_bench.py`).
7. Corrí el banco sobre `bench/files/muestra.dxf`.
8. Corrí toda la suite.
9. Omití el commit de git, según la salvedad del pedido.

## Salida de pytest — `test_raster_oracle.py` solo

```
$ .venv/bin/pytest tests/engine/raster/test_raster_oracle.py -v
...
FAILED tests/engine/raster/test_raster_oracle.py::test_the_first_part_lands_near_the_bottom_left_margin
FAILED tests/engine/raster/test_raster_oracle.py::test_a_small_part_is_nested_inside_a_big_hole
FAILED tests/engine/raster/test_raster_oracle.py::test_the_raster_engine_beats_the_shelf_engine_on_circles
========================= 3 failed, 9 passed in 1.69s ==========================
```

## Salida de pytest — suite completa

```
$ .venv/bin/pytest
...
FAILED tests/engine/raster/test_raster_oracle.py::test_the_first_part_lands_near_the_bottom_left_margin
FAILED tests/engine/raster/test_raster_oracle.py::test_a_small_part_is_nested_inside_a_big_hole
FAILED tests/engine/raster/test_raster_oracle.py::test_the_raster_engine_beats_the_shelf_engine_on_circles
3 failed, 317 passed in 38.02s
```

308 tests pre-existentes + 12 nuevos = 320. Todos los de `test_cli.py` y
`test_packer.py` pasan sin haber sido tocados, confirmando que la costura de
la spec §3.2 funciona: el packer, la CLI y el verificador no sabían ni
saben qué motor hay detrás del `Oracle`.

## La tabla del banco — el dato central

Comando exacto y salida, sobre `bench/files/muestra.dxf`, en los dos puntos
que dio el usuario como referencia:

```
$ .venv/bin/python bench/run_bench.py --copias 1
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
muestra.dxf             shelf          12       1    13.6%     0.0
muestra.dxf             raster         12       1    13.6%     5.3  (+0.0 pts)
```

```
$ .venv/bin/python bench/run_bench.py --copias 6
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
muestra.dxf             shelf          72       2    40.7%     0.0
muestra.dxf             raster         72       2    40.7%    70.8  (+0.0 pts)
```

Los aprovechamientos y la cantidad de placas de `shelf` coinciden
exactamente con la línea de base que dio el usuario (13.6%/1 placa y
40.7%/2 placas). Pero **`raster` empata con `shelf` en los dos casos**, no
lo supera. Investigué por qué antes de reportarlo como está — ver la
sección siguiente — y encontré que sí hay una mejora real y grande, sólo
que estos dos puntos de copia particulares no la muestran.

### Por qué empatan: la métrica es ciega a la calidad de empaque cuando
### ambos motores usan la misma cantidad de placas

`total_utilization` se define como `área total colocada / (área de placa ×
placas usadas)`. Cuando **ambos** motores logran colocar el 100% de las
piezas usando la **misma cantidad de placas**, esa fracción queda forzada a
ser idéntica sin importar qué tan prolijo sea el acomodo dentro de cada
placa — porque el numerador (área total de las piezas) y el denominador
(placas × área de placa) son los mismos para los dos motores.

Lo verifiqué desglosando el aprovechamiento por placa (no sólo el total),
para `--copias 6` (72 piezas, `sep=6, margin=10`, resolución 1.0 mm/px):

| motor  | placa 1 | placa 2 | total  | segundos |
|--------|---------|---------|--------|----------|
| shelf  | 52.3%   | 29.1%   | 40.7%  | 0.01     |
| raster | **59.1%** | 22.3% | 40.7%  | 72.3     |

Raster llena la **primera** placa un 13% más (relativo) que shelf — una
mejora real y medible en densidad de empaque — pero como ninguno de los dos
logra vaciar la segunda placa por completo, el total queda empatado por la
identidad matemática de arriba. La ganancia de raster existe, pero la
métrica agregada no la deja ver en este punto de copia específico.

### Dónde la mejora SÍ se ve con claridad: cuando cambia la cantidad de placas

Busqué el punto de copia donde `shelf` necesita una placa más que `raster`
— ahí la métrica deja de estar ciega. `shelf` pasa de 1 a 2 placas entre 3 y
4 copias (36 → 48 piezas). En ese punto:

```
$ .venv/bin/python bench/run_bench.py --copias 4
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
muestra.dxf             shelf          48       2    27.1%     0.0
muestra.dxf             raster         48       1    54.2%    44.4  (+27.1 pts)
```

Acá la diferencia es enorme y clara: **raster usa una sola placa donde
shelf necesita dos**, con el doble de aprovechamiento (54.2% contra 27.1%,
+27.1 puntos, +100% relativo). Esta es, a mi juicio, la evidencia real de
que el hito 3 valió la pena — más contundente que los dos puntos de
referencia originales, que resultaron caer justo en una zona de empate por
la razón matemática explicada arriba.

**Resumen de los tres puntos medidos** (`sep=6, margin=10`, resolución 1.0 mm/px):

| copias | piezas | shelf: placas / aprov. | raster: placas / aprov. | seg. raster |
|--------|--------|-------------------------|--------------------------|-------------|
| 1      | 12     | 1 / 13.6%               | 1 / 13.6% (empate)       | 5.3         |
| 4      | 48     | 2 / 27.1%               | **1 / 54.2%**            | 44.4        |
| 6      | 72     | 2 / 40.7%               | 2 / 40.7% (empate)       | 70.8        |

## Los 3 tests en rojo — investigación de causa raíz (no aflojé nada)

El usuario pidió explícitamente no aflojar el test de "raster le gana a
shelf" si no gana, sino investigar y reportar con números. Extendí ese
mismo criterio a los otros dos tests en rojo: dejé el archivo de test y la
implementación exactamente como los da el brief, y en vez de ajustar
tolerancias hice tres experimentos de control para entender la causa.

### 1. `test_the_first_part_lands_near_the_bottom_left_margin` — falla: x=32.0 en vez de ~20.0

Causa: `masks.py` (Tarea 15) dimensiona el arreglo de cada máscara con el
mínimo indispensable para alojar la dilatación de holgura (`pad =
ceil(sep/resolución) + 1`, sin ningún píxel de sobra) — una elección
deliberada de esa tarea para no gastar memoria de más. Pero eso significa
que, al usar correlación `"valid"` contra la grilla (que es exactamente lo
que el punto 2 de la consigna pide: "el borde lo garantiza la forma del
arreglo"), la posición factible más próxima al borde deja el **halo de
holgura completo** apenas adentro de la grilla — no sólo el material real.
Con `sep=10, margin=20, resolución=2` medí que el material real de la
primera pieza queda a `margin + pad·resolución = 20 + 12 = 32` mm del
borde, no a `margin` mm. Es una propiedad estructural de cómo se combinan
las Tareas 15 y 16 (no algo que dependa del tamaño o forma de la pieza), y
crece con `sep` en relación al `margin` — en este test puntual, `sep` es la
mitad de `margin`, así que el efecto es grande. No es un bug de mi código:
verifiqué que la fórmula de conversión píxel↔mundo del brief está aplicada
literalmente, y sin tocar `masks.py`/`search.py` no hay forma de eliminarlo
dentro del alcance de esta tarea.

### 2. `test_a_small_part_is_nested_inside_a_big_hole` — falla: la pieza chica NO cae en el agujero

Causa, confirmada con instrumentación directa de `contact_band`,
`overlap_counts` y `best_position`: el mismo `pad` ajustado (Tarea 15) que
causa el hallazgo anterior también deja **cero margen de sobra** para que
`contact_band` (Tarea 17) dibuje su anillo por fuera de la holgura — porque
`contact_band` dilata el arreglo de `clearance` que ya llega exactamente
hasta el borde de su propio arreglo. Medí para la pieza de 200×200 mm
(`sep=10, resolución=2`): el `contact_band` sólo consigue 36 píxeles no
nulos en total (contra un perímetro esperable de varios cientos), y son
artefactos de las esquinas redondeadas de la dilatación circular, no un
anillo real a lo largo de los lados rectos. Con eso confirmé el puntaje
real: la posición dentro del agujero anota `bl=0.73, contacto≈0`, y la
posición fuera del anillo (al costado, en la fila más baja posible) anota
`bl=0.998, contacto≈0` — el término de contacto nunca puede compensar la
diferencia de "abajo-izquierda" con los pesos default `(1.0, 1.0)`, porque
su contribución máxima medida en esta geometría es de sólo 0.11.

Igual, intenté una posible corrección local dentro de `oracle.py` (rellenar
el arreglo de `clearance` con ceros extra vía `np.pad` antes de pasarlo a
`contact_band`, manteniendo la coherencia de formas que exige
`best_position`). Confirmé que sí genera un anillo de contacto más grande
(587 → 748 píxeles no nulos para un círculo de prueba), pero **no cambié el
archivo final** por dos razones: (a) para el caso de la pieza rectangular
en el agujero el efecto es aún más chico en términos relativos y no alcanzó
para revertir el resultado en las pruebas que hice, y (b) para el caso de
los círculos (ver el punto 3) verifiqué que tampoco cambia el resultado —
así que hubiera sumado una desviación de código no trivial respecto del
Step 3 del brief, con el riesgo de desincronización de píxel que la propia
consigna advierte, sin conseguir que el test pase. Documento el hallazgo en
vez de parchearlo a ciegas.

### 3. `test_the_raster_engine_beats_the_shelf_engine_on_circles` — falla: empatan en 0.3158 exacto

Ya expliqué arriba la causa matemática general (empate cuando ambos motores
usan la misma cantidad de placas). Para este test puntual (14 círculos de
radio 120 mm, `sep=8, margin=15, resolución=2`, una sola placa de
1000×1000mm) hice tres experimentos de control para descartar que fuera un
bug mío:

1. **Sin la región activa** (búsqueda siempre sobre la placa completa, sin
   el recorte por frontera): mismo resultado exacto (12 círculos en la
   placa 1, 2 en la placa 2). La región activa no sacrifica calidad acá,
   como garantiza el punto 3 de la consigna.
2. **Con el parche de `np.pad` al `clearance`** (contacto genuinamente más
   fuerte, no artefacto de esquina): mismo resultado exacto, 12 y 2.
3. Con eso confirmé que el heurístico voraz (una pieza a la vez,
   `abajo-izquierda` + contacto) tiene un techo de 12 de 14 círculos en una
   placa para esta geometría específica, techo que no se mueve ni saltando
   la región activa ni mejorando el contacto. El empaquetamiento hexagonal
   ideal permitiría hasta ~17 en el área útil, pero alcanzarlo requeriría
   una estrategia global, no la colocación voraz secuencial que implementan
   `packer.py`/`scoring.py` (fuera del alcance de esta tarea).

Como ambos motores necesitan 2 placas para las 14 piezas, el total queda
matemáticamente empatado igual que en el caso del banco con `--copias 1` y
`--copias 6`. La Tarea 18 no cambia esto: es un test sintético que cae,
como esos dos puntos del banco, justo en una zona de empate por la métrica.
El banco con `--copias 4` (arriba) muestra que la ventaja real del motor
raster es contundente cuando el punto de comparación no cae en esa zona.

## Desviaciones respecto del brief

- **Omití el Step 9 (commit de git)**, según la instrucción explícita del
  pedido — este proyecto no usa git.
- **No modifiqué el código de `oracle.py`** pese a los 3 tests en rojo,
  después de investigar tres hipótesis de arreglo local y confirmar que
  ninguna resuelve el test más importante (el de los círculos) y que
  aumentan la complejidad/riesgo sin ese beneficio. Prioricé no "aflojar"
  ningún test, tal como pidió el usuario para el test de comparación, y
  extendí el mismo criterio a los otros dos.
- **Mantuve el manejo de `FILE_ERRORS`** en `bench/run_bench.py` (try/except
  alrededor de `run_one`) que ya existía en el archivo, porque el snippet
  del Step 6 del brief lo omite pero removerlo haría que un solo archivo
  sucio tirara abajo la medición completa del banco — una regresión de
  comportamiento no pedida.
- Usé `--copias 4` (no pedido por el brief) como corrida adicional del
  banco para poder mostrar con números un caso donde la ventaja del motor
  raster es inequívoca, dado que los dos puntos de referencia que dio el
  usuario cayeron en zona de empate.

## Recomendación

No es una recomendación para esta tarea (que pidió wiring, no ajuste de
pesos ni de `masks.py`), pero para que la Tarea 24 (calibración de pesos,
ya prevista) tenga margen real donde trabajar, valdría la pena que alguien
revise si `masks.py` debería dejar sistemáticamente un poco de holgura
extra en el arreglo (más allá de la estrictamente necesaria para `sep`),
para que `contact_band` pueda dibujar un anillo real en piezas de lados
rectos y no sólo en las esquinas redondeadas.

---

# Addendum — Tarea 18 (arreglo del defecto): el borde se cobraba dos veces

**Fecha:** 2026-09-18. Este addendum continúa el informe anterior (arriba),
que dejó los 3 tests en rojo sin tocar `oracle.py` a propósito. Esta sesión
implementó el arreglo que aquella "Recomendación" final ya anticipaba.

## Estado

**DONE_WITH_CONCERNS**, igual que antes pero con menos concerns: de los 3
tests rojos originales, **2 ahora pasan** (`test_the_first_part_lands_...` y
`test_a_small_part_is_nested_inside_a_big_hole`). El tercero
(`test_the_raster_engine_beats_the_shelf_engine_on_circles`) sigue en rojo,
y esta vez hay una prueba matemática (no sólo experimentos empíricos) de que
es geométricamente irrealizable con la resolución que usa ese test — ver
más abajo.

## El arreglo implementado

Dos cambios, ambos en `src/nesting/engine/raster/masks.py` y
`src/nesting/engine/raster/oracle.py`:

**1. Separar `occupied` (bordeado por `margin`) de `clearance` (que puede
sobresalir del área útil).** `PartMasks` ahora expone un campo nuevo,
`pad: int` — el mismo `pad` que `rasterize` ya calculaba para dimensionar su
propio arreglo, ahora accesible en vez de que el oráculo tuviera que
re-derivarlo a ojo. `RasterOracle._search` rellena la placa (ya recortada
por la región activa) con `pad` píxeles de cero en los cuatro lados antes de
correlacionar `clearance` en modo `"valid"`. Con el arreglo de la máscara de
tamaño `Hm = ho + 2·pad` (por construcción, para cualquier valor de `pad`),
una correlación válida contra una placa rellenada por `pad` de cada lado da
`filas + 2·pad − Hm + 1 = filas − ho + 1` posiciones — exactamente una por
cada posición donde el **material** (no la holgura) entra en el área útil.
El índice de esa correlación se desplaza por `-pad` antes de convertirlo a
mundo con `translation_for`, para que siga significando "pixel [0,0] de la
máscara en la placa sin rellenar", como ya asumían `translation_for` y
`place`.

Verificado a mano (`margin=20, sep=10, resolución=2`, pieza 100×50):
antes `x=32.0` (=`margin+pad·resolución`), ahora `x=20.0` exacto — el
material arranca en el margen, no en `margin+sep`.

**2. `place()` tenía un bug de indexado latente, expuesto por el cambio
anterior.** Una vez que `px`/`py` pueden ser negativos (el pixel [0,0] de
la máscara, que es sólo holgura vacía, puede caer legítimamente antes del
borde de la placa sin rellenar), un slice directo
`self._sheet[py:py+height, px:px+width]` con `py` o `px` negativo usa la
semántica de indexado negativo de Python/NumPy (cuenta desde el final) en
vez de fallar — así que habría estampado `occupied` en filas/columnas
equivocadas sin ningún error visible. Lo arreglé recortando el slice
destino a los límites reales de la placa y desplazando el slice fuente de
`occupied` para que coincida (ver comentario en el código).

**3. `contact_band` no tenía dónde dibujar el anillo — la misma causa que ya
había encontrado el informe anterior.** `clearance` llega, por diseño (`pad
= max(1, radius) + 1`), exactamente al borde de su propio arreglo — cero
píxeles de sobra para que `scoring.contact_band` dilate más allá y dibuje el
anillo de contacto (el informe anterior ya lo documentó: 36 píxeles no
nulos, puros artefactos de esquina redondeada, para una pieza de 200×200).
Sin este segundo arreglo, `test_a_small_part_is_nested_inside_a_big_hole`
seguía fallando incluso con el arreglo (1): la pieza chica se iba al costado
del agujero (`contacto≈0` en las dos posiciones, así que `abajo-izquierda`
solo decidía a favor de la posición de afuera).

Arreglo: moví `CONTACT_BAND_MM` (antes en `oracle.py`) a `masks.py`, agregué
`contact_band_px(resolution)`, y `rasterize` ahora suma esa cantidad a `pad`
(`pad = max(1, radius) + 1 + contact_band_px(resolution)`). `oracle.py`
importa la constante y el helper desde `masks.py` en vez de duplicarlos.
Esto **no** cambia la distancia mínima real entre piezas (verificado
directamente: forzando `contact_band_px` a 0 sin tocar nada más, la
distancia mínima entre dos círculos de prueba sigue siendo exactamente la
misma) — sólo le da a `contact_band` arreglo propio más grande para
dilatar, sin afectar la colisión real.

Con los dos arreglos, medí el `contact_band` de un círculo (radio 120,
`sep=8, resolución=2`): pasó de estar limitado por el borde (como en el
informe anterior) a **748 píxeles no nulos**, un anillo real, no sólo
esquinas.

## Verificación obligatoria

### 1. Suite completa

```
$ .venv/bin/pytest -q
...................................................................... [ ...]
1 failed, 319 passed in ~39s
FAILED tests/engine/raster/test_raster_oracle.py::test_the_raster_engine_beats_the_shelf_engine_on_circles
```

(320 tests en total — sin cambios de conteo. Antes: 3 failed, 317 passed.
Ahora: 1 failed, 319 passed. Cero regresiones en el resto de la suite.)

### 2. El banco — los dos motores en `--copias 1`, `--copias 4`, `--copias 6`

```
$ .venv/bin/python bench/run_bench.py --copias 1
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
muestra.dxf             shelf          12       1    13.6%     0.0
muestra.dxf             raster         12       1    13.6%     5.4  (+0.0 pts)

$ .venv/bin/python bench/run_bench.py --copias 4
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
muestra.dxf             shelf          48       2    27.1%     0.0
muestra.dxf             raster         48       1    54.2%    45.0  (+27.1 pts)

$ .venv/bin/python bench/run_bench.py --copias 6
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
muestra.dxf             shelf          72       2    40.7%     0.0
muestra.dxf             raster         72       2    40.7%    76.7  (+0.0 pts)
```

Los tres puntos coinciden exactamente con la línea de base de `shelf` que
dio el usuario (13.6%/1, 27.1%/2, 40.7%/2). `raster` en `--copias 1` y
`--copias 6` **sigue empatando** con `shelf` en el total — mismo motivo
matemático que ya documentó el informe anterior (cuando los dos motores
terminan usando la misma cantidad de placas, `total_utilization` es
`área_total_colocada / (área_placa · placas)`, idéntica para los dos sin
importar la calidad del acomodo dentro de cada placa). Lo re-verifiqué
desglosando por placa en `--copias 6`: `raster` llena la placa 1 al 60.0%
contra 52.3% de `shelf` (mejora real del ~15% relativo), pero como ninguno
vacía la placa 2 el total queda empatado en 40.7% de todos modos. El
arreglo de esta tarea **no** apunta a esa métrica agregada — apunta a que
el material llegue hasta el margen real, cosa que sí se ve en la corrida
`--copias 4`, donde `raster` pasa de necesitar la misma cantidad de placas
que `shelf` a necesitar una menos (2→1), duplicando el aprovechamiento
(27.1%→54.2%).

**Tiempo del motor raster:** confirmado que sigue en el orden del minuto
para 72 piezas (76.7s en `--copias 6`, similar a los 70.8s que ya medía el
informe anterior antes de este arreglo — el arreglo no lo empeoró ni lo
mejoró de forma perceptible, como es esperable: no toca la ruta caliente de
FFT, sólo agrega padding fijo a arreglos que ya existían). Dato para la
calibración posterior de esfuerzo/resolución que menciona la consigna.

### 3. A mano: la primera pieza cae sobre el margen

```
margin=20.0, sep=10.0, pieza 100×50mm, placa 1000×1000mm
primera pieza: x=20.0 y=20.0
```

Antes del arreglo: `x=32.0` (=`margin + pad·resolución` = `20 + 12`). Ahora:
exactamente `20.0` — el material arranca en el margen, no en `margin+sep`.

## El test que sigue en rojo: `test_the_raster_engine_beats_the_shelf_engine_on_circles`

Con los dos arreglos de arriba ya aplicados, este test **sigue fallando con
los mismos números exactos** que sin ningún arreglo: `raster` empaqueta 12
de 14 círculos en la placa 1 (deja 2 para la placa 2), igual que `shelf`
necesita 2 placas (9+5) — mismo empate matemático de la sección anterior, y
mismo resultado (12 y 2) que ya había medido el informe anterior *antes* de
que existiera este arreglo. Repetí sus tres experimentos de control con el
arreglo real ya puesto (no el parche experimental de antes) y agregué un
cuarto:

1. **Sin región activa** (búsqueda siempre sobre la placa entera): mismo
   resultado exacto, 12 y 2.
2. **Variando el peso de contacto** (`Weights(1.0, w)` para
   `w ∈ {1, 2, 5, 10, 20}`): con `w=5` se logran 13 en la placa 1 (mejor que
   12), pero **13 sigue necesitando una segunda placa** para el círculo 14
   — el empate matemático no se rompe por ese lado. Con `w∈{1,2,10,20}` da
   12 igual que el default.
3. **200 órdenes aleatorios distintos** de las 14 piezas (pesos default): el
   máximo alcanzado en la placa 1 en las 200 corridas fue 12, nunca más.
4. **150 combinaciones aleatorias de orden + pesos** (`bottom_left∈[0,2]`,
   `contact∈[0,5]`): el máximo encontrado fue 13 en la placa 1, nunca 14 (ni
   una sola placa).

**Encontré además la prueba matemática de por qué**, que el informe
anterior no tenía: resolví (con `scipy.optimize`, formulación
maximizar-la-mínima-distancia-por-pares) el empaquetamiento *óptimo* de 14
puntos en la caja de 730×730mm donde puede estar el centro de cada círculo
(sheet 1000×1000, `margin=15`, radio=120 ⟹ centro entre 135 y 865). La
mínima distancia entre centros que logra el óptimo global es
**254.708mm**. Medí por separado, con el motor ya arreglado, cuál es la
distancia mínima real que el propio raster acepta entre dos círculos
(colocando uno, pidiendo la mejor posición para el segundo): **254.0mm** —
6mm más que el mínimo teórico (240+8=248mm), por el margen de seguridad
deliberado que ya documenta `masks.py` (dilatación de seguridad de 1px +
sesgo conservador del supermuestreo), **sin relación con el arreglo de esta
tarea** (lo confirmé forzando `contact_band_px` a 0: la distancia sigue
siendo 254.0mm igual).

Como `254.708 > 254.0`, encajar los 14 círculos en una placa **sí es
posible en el plano continuo**, pero por un margen de sólo 0.7mm sobre
730mm de caja (0.1%). Redondeando la solución óptima a la grilla de 2mm que
usa el raster (`resolución=2.0`), la distancia mínima entre pares cae a
**253.5mm — por debajo del piso real de 254.0mm** — y probé 400
desplazamientos sub-píxel distintos de la misma solución antes de
redondear: ninguno recupera los 254mm. Es decir: la única configuración
matemáticamente óptima para 14 círculos en esa caja **no sobrevive la
cuantización de la propia grilla de 2mm**, aparte de que ningún algoritmo
voraz (con o sin backtracking limitado) la va a encontrar por las buenas.

En síntesis: el test le pide al motor una densidad que excede lo que la
geometría (a esta resolución, con estos márgenes de seguridad
pre-existentes de `masks.py`, ninguno tocado por esta tarea) permite. No es
un defecto de índices, de región activa ni de término de contacto — los
cuatro controles de arriba lo descartan — sino un límite geométrico duro.
No aflojé la aserción; la dejé como está y reporto esto en su lugar, tal
como pidió la consigna.

## Archivos modificados en esta sesión

- `src/nesting/engine/raster/masks.py` — nuevo campo `PartMasks.pad`, nueva
  constante `CONTACT_BAND_MM` y helper `contact_band_px()` (movidos desde
  `oracle.py`), `pad` en `rasterize` ahora incluye espacio para la
  dilatación de seguridad, para `sep` y para el margen de `contact_band`.
- `src/nesting/engine/raster/oracle.py` — `_search` rellena la placa con
  `masks.pad` ceros antes de correlacionar y desplaza el índice resultante;
  `place()` recorta el slice de estampado en vez de dejar que un índice
  negativo haga wraparound; importa `CONTACT_BAND_MM`/`contact_band_px`
  desde `masks.py` en vez de duplicarlos.

No borré ni aflojé ningún test. No usé git (el proyecto no lo usa).

---

# Informe de seguimiento (tarea nueva): test mal diseñado + métrica ciega

Fecha: 2026-09-18.

## Problema 1 — `test_the_raster_engine_beats_the_shelf_engine_on_circles`

Confirmado el diagnóstico del informe anterior: ese test exigía un
`total_utilization` que solo se alcanza a 0.7 mm del óptimo geométrico
global para 14 círculos r=120 en una placa de 1000×1000 (sep=8,
margin=15), holgura que no sobrevive la cuantización de la grilla de 2 mm.
Se reemplazó por dos tests en
`tests/engine/raster/test_raster_oracle.py`:

1. `test_the_raster_engine_fits_more_parts_on_a_single_sheet_than_the_shelf_engine`
   — misma config de 14 círculos. Cuenta cuántas piezas quedan en la
   `sheet == 0` de cada motor y exige `raster >= shelf + 2`. Medido: shelf
   9, raster 12. El docstring explica por qué esta es la métrica correcta:
   se traduce directamente en placas ahorradas, y no depende de alcanzar
   ningún óptimo.

2. `test_the_raster_engine_packs_the_first_sheet_denser_with_curved_and_concave_parts`
   — agrega un generador `notched_circle_part` (círculo con una cuña
   mordida: curvo Y cóncavo) y usa una mezcla de 12 círculos + 4 piezas
   mordidas, suficiente para desbordar a una segunda placa en los dos
   motores. Compara `utilization[0]` (primera placa) en vez de
   `total_utilization`, exigiendo `raster > shelf * 1.10`. Medido: shelf
   44.2%, raster 54.1%.

Ningún test nuevo depende de encontrar un óptimo geométrico; ambos dejan
margen amplio respecto de lo medido (2 piezas de margen sobre una
diferencia real de 3; 10% de margen sobre una diferencia real de ~22%).

No se borró ningún otro test.

## Problema 2 — `total_utilization` ciega para comparar motores

Se agregó `first_sheet_utilization` a `BenchResult` en `bench/run_bench.py`,
tomado de `PackResult.utilization[0]` (no se recalculó nada: el valor ya
venía calculado por `pack()`). Se agregó la columna "1ra placa" a la tabla
del banco, sin tocar las columnas existentes. Se documentó en los
docstrings de ambos campos por qué hacen falta los dos: `total_utilization`
mide lo que le cuesta al usuario (placas), y es ciega por construcción
cuando la cantidad de placas no cambia entre motores; `first_sheet_utilization`
mide qué tan bien empaqueta el motor, y sí distingue en ese caso.

## Verificación

`.venv/bin/pytest -q` completo: **321 passed**, cero rojos (era
`1 failed, 319 passed`; se sacó 1 test malo y se agregaron 2 nuevos: 319 − 1
+ 1(el que estaba roto, ahora reemplazado) + 2 = 321).

Banco (`bench/run_bench.py`) contra `bench/files/muestra.dxf`, material
`mdf18`, `--copias 1`, `4` y `6`:

```
=== copias=1 ===
archivo                 motor      piezas  placas   aprov.  1ra placa     seg
-----------------------------------------------------------------------------
muestra.dxf             shelf          12       1    13.6%      13.6%     0.0
muestra.dxf             raster         12       1    13.6%      13.6%     5.5  (+0.0 pts)

=== copias=4 ===
archivo                 motor      piezas  placas   aprov.  1ra placa     seg
-----------------------------------------------------------------------------
muestra.dxf             shelf          48       2    27.1%      43.6%     0.0
muestra.dxf             raster         48       1    54.2%      54.2%    45.9  (+27.1 pts)

=== copias=6 ===
archivo                 motor      piezas  placas   aprov.  1ra placa     seg
-----------------------------------------------------------------------------
muestra.dxf             shelf          72       2    40.7%      52.3%     0.0
muestra.dxf             raster         72       2    40.7%      60.0%    77.9  (+0.0 pts)
```

Nota honesta sobre el pedido de "confirmar que el raster gana en las tres
corridas": en `--copias 1` empatan (13.6% == 13.6%), no porque falte algo
sino porque con solo 12 piezas reales, la densidad total del job es tan
baja (13.6%) que las dos entran completas en una sola placa sin que ningún
motor tenga que decidir qué dejar afuera. Cuando un motor coloca el 100%
de las piezas en la única placa que usó, `first_sheet_utilization` es
igual a `total_utilization` por definición — no hay margen para que un
empaquetado más inteligente se note, porque no hubo nada que optimizar.
Es la misma lógica del Problema 2 aplicada al revés: la métrica nueva
distingue calidad de empaquetado, pero solo cuando hay presión de
empaquetado (sobra de piezas). En `--copias 4` y `--copias 6`, donde sí
hay esa presión, el raster gana con margen claro (54.2% vs 43.6%, y 60.0%
vs 52.3%). Se reporta así en vez de forzar los parámetros del banco para
maquillar un resultado en `--copias 1`.

## Archivos modificados en esta sesión

- `tests/engine/raster/test_raster_oracle.py` — se borró
  `test_the_raster_engine_beats_the_shelf_engine_on_circles` (el único test
  borrado, según lo pedido) y se agregaron `notched_circle_part()` y los
  dos tests nuevos descriptos arriba.
- `bench/run_bench.py` — nuevo campo `BenchResult.first_sheet_utilization`,
  poblado en `run_one()` desde `PackResult.utilization[0]`, nueva columna
  "1ra placa" en la tabla de `main()`, comentarios explicando por qué
  conviven las dos métricas.

No se usó git (el proyecto no lo usa). No se borró ningún otro test.
