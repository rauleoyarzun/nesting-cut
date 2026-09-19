# Task 19 — Niveles de esfuerzo y compactación de la última placa

## Archivos modificados

- `src/nesting/engine/packer.py` — reintentos por nivel de esfuerzo, `layout_cost`,
  compactación de la última placa (`_compact_last_sheet`), `UnknownEffortError`,
  `EFFORT_RESTARTS` calibrado por medición.
- `tests/engine/test_effort.py` — nuevo, tal cual el brief (12 tests).
- `src/nesting/cli.py` — el `pack()` de la CLI ahora comparte una `MaskCache`
  entre todos los `RasterOracle` que arma esa corrida.
- `bench/run_bench.py` — idem para el banco: una `MaskCache` nueva por archivo,
  compartida entre placas y reintentos de ese archivo (no entre archivos).

Se omitió el paso de commit de git del brief: este proyecto no usa git.

## 1. La caché de máscaras: el desperdicio conocido

**Diagnóstico.** `pack()` recibe una *fábrica* de oráculos (`oracle_factory:
Callable[[], Oracle]`) para no atarse a un motor concreto. Antes de esta
tarea, tanto la CLI como el banco pasaban la clase `RasterOracle` misma como
fábrica. Como `RasterOracle.__init__` crea una `MaskCache()` propia cuando no
se le pasa una, cada vez que `pack()` invoca `oracle_factory()` — una vez por
placa, y ahora una vez por cada intento de reordenamiento — se tira la caché
anterior y se vuelve a rasterizar cada combinación (pieza, ángulo, espejado)
desde cero. Las máscaras no dependen del estado de la placa, así que ese
trabajo es puro desperdicio.

**Diseño elegido.** En vez de cambiar la firma de `pack()` (el brief prohíbe
tocarla y además rompería el motor `ShelfOracle`, que no tiene ni necesita
caché), la caché se comparte armando la fábrica como una clausura que ya
lleva su `MaskCache` adentro:

```python
cache = MaskCache()
result = pack(parts, material, config, lambda: RasterOracle(cache=cache))
```

`pack()` sigue viendo exactamente el mismo `Callable[[], Oracle]` de siempre
y no sabe ni le importa que las instancias comparten caché por debajo. Esto
es la opción "la fábrica es un invocable que el llamador arma con su propia
caché", en vez de agregarle un parámetro de caché opcional a `pack()`. Se la
prefirió porque:

- No toca la firma pública de `pack()` (requisito explícito del brief).
- Mantiene a `pack()` completamente agnóstico del motor: un motor trivial sin
  caché (`ShelfOracle`) sigue pasándose tal cual, como la clase misma.
- Ata la vida de la caché exactamente a un llamado de `pack()` (la CLI hace
  una `MaskCache` por corrida; el banco hace una por archivo, no una para
  toda la corrida — los archivos no comparten geometría, así que compartir
  entre ellos solo gastaría memoria sin ahorrar tiempo).

Se aplicó en `src/nesting/cli.py` y `bench/run_bench.py` (función
`_new_raster_factory`). Los tests de `test_effort.py`, en cambio, siguen el
código del brief tal cual y pasan `RasterOracle` (la clase) directamente como
fábrica — no ejercitan la caché compartida, porque es una optimización de
tiempo, invisible para la corrección o el determinismo, que ya cubren esos
tests igual.

**Medición: ¿cuánto mejora una pasada?**

Con `bench/files/muestra.dxf`, material `mdf18`, `sep=6`, `borde=10`,
resolución 1 mm/px (los defaults del banco), una sola pasada golosa
(`effort="rapido"`, o sea `_pack_once` una vez):

| Escenario | Sin caché compartida | Con caché compartida | Mejora |
|---|---|---|---|
| `--copias 4` (48 piezas, 1 placa) | 46.24s | 46.50s | ~0% (ruido) |
| `--copias 6` (72 piezas, 2 placas) | 81.10s | 80.59s | ~0.6% |
| `--copias 4`, `effort="normal"` (4 reintentos, antes de calibrar) | 234.06s | 227.88s | ~2.6% |

La ganancia es real pero **modesta**, y crece con la cantidad de placas y de
reintentos — exactamente donde `oracle_factory()` se invoca más veces. No es
la optimización dominante (ver §2): el costo de rasterizar una pieza es
chico comparado con el de buscarle posición. Aun así se implementó porque
es gratis (ninguna pérdida de corrección, mismo resultado, menos trabajo) y
porque su beneficio crece con los reintentos que esta misma tarea agrega —
sin ella, cada uno de los 3-12 reintentos de `normal`/`lento` volvería a
rasterizar las mismas 96 combinaciones (pieza × ángulo × espejo) del
archivo de muestra.

## 2. Dónde se va el tiempo, y la región activa

Perfil de una pasada única (`cProfile`, `--copias 4`, 48 piezas, 8
orientaciones, resolución 1 mm/px, caché compartida), 48.35s totales:

| Función | Tiempo acumulado | % del total |
|---|---|---|
| `overlap_counts` / `fftconvolve` (correlaciones FFT, factibilidad + contacto) | 42.69s | 88.3% |
| — de eso, dentro de `best_position` (la de contacto/puntaje) | 23.63s | 48.9% |
| `rasterize` (construir las máscaras) | 2.70s | 5.6% |
| `binary_erosion`/`binary_dilation` (parte de `rasterize`, incluidas arriba) | ~1.5s+1.2s | ~5.6% |

Cada llamada a `best_placement` hace **dos** correlaciones FFT sobre toda la
ventana activa de la placa: una para saber qué posiciones son factibles
(`feasible_positions`), y otra para puntuar el contacto contra el material ya
puesto (`best_position`). Ese es el costo dominante, y no depende de la
caché de máscaras en absoluto — depende del tamaño de la placa/ventana de
búsqueda, no de si la máscara de la pieza ya estaba calculada. Por eso la
caché compartida (§1) ayuda poco: ataca un costo que ya era chico.

**Optimización de región activa.** Se instrumentó cada colocación de una
pasada (48 piezas, un único oráculo, caché compartida) para medir el tiempo
por pieza y el `frontier` (fila más alta ocupada) contra el que se recorta
la ventana de búsqueda:

| Pieza # | Tiempo | `frontier` antes | Filas totales de la placa |
|---|---|---|---|
| 0 | 0.19s | 0 | 2580 |
| 5 | 0.44s | 311 | 2580 |
| 16 | 0.84s | 988 | 2580 |
| 32 | 1.28s | 1807 | 2580 |
| 47 (última) | 1.55s | 2443 | 2580 |

El tiempo por colocación crece de forma prácticamente lineal con el
`frontier`, de 0.19s a 1.55s (~8x) — confirma que la optimización de región
activa **funciona como se espera**: las primeras piezas de una placa
buscan sobre una ventana chica y son mucho más baratas que las últimas, que
ya buscan casi sobre la placa entera. No es un techo artificial: es la
consecuencia esperada de que cada vez hay más placa ocupada para correlacionar
contra. La optimización no puede evitar ese crecimiento (la ventana de
búsqueda tiene que cubrir hasta donde ya hay material), pero sí evita pagar
el costo de la placa completa desde la primera pieza.

**Conclusión de esta sección:** el cuello de botella real es la correlación
FFT de factibilidad y contacto, proporcional al alto ya ocupado de la placa.
Cachear máscaras no lo toca; lo único que reduce el costo por reintento de
forma sustancial es reducir la cantidad de reintentos mismos — de ahí que la
calibración de `EFFORT_RESTARTS` (§3) sea lo que realmente define el
presupuesto de tiempo.

## 3. Calibración de `EFFORT_RESTARTS`

Referencia de tiempo: `bench/files/muestra.dxf`, material `mdf18`, `sep=6`,
`borde=10`, resolución 1 mm/px (`bench/run_bench.py` defaults), con la caché
de máscaras ya compartida.

### Tiempo de una sola pasada golosa (`rapido`)

| Copias | Piezas | Placas | Tiempo |
|---|---|---|---|
| 4 | 48 | 1 | 46.2s |
| 6 | 72 | 2 | 81.1s |

### Búsqueda del techo de `normal` (objetivo: < 5 min = 300s en ambas referencias)

| Reintentos | `--copias 4` | `--copias 6` | ¿Entra en 5 min? |
|---|---|---|---|
| 1 (`rapido`) | 46.2s | 81.1s | sí |
| 3 | 182.3s | 235.8s | **sí**, con ~64s de margen en el caso más duro |
| 4 | 234.1s* | 317.5s | **no** — ya supera los 300s en `--copias 6` |

\* Medido con la caché compartida y `effort="normal"` real, antes de fijar el
valor final de `EFFORT_RESTARTS["normal"]` (con la tabla en 4 reintentos en
ese momento); consistente con el 234.06s de la tabla de §1.

El tiempo por reintento es prácticamente lineal con la cantidad de piezas y
placas (una pasada más cuesta ~46s en `--copias 4` y ~81s en `--copias 6`,
consistente con 3 y 4 reintentos). **4 reintentos ya rompe el objetivo de 5
minutos en el escenario más duro** (317.5s > 300s), así que **3** es el
máximo que entra con margen en ambas referencias.

**`EFFORT_RESTARTS["normal"] = 3`** (no 10, como estimaba el brief sin medir).

### ¿`lento` compra algo medible?

Correr `lento` a escala completa muchas veces para ver si mejora sobre
`normal` es en sí carísimo (cada punto de la tabla anterior cuesta minutos).
Se lo verificó en un escenario sintético más chico y rápido, pero con la
misma mecánica: 20 piezas rectangulares de tamaños variados en una placa de
1000x1000mm (`sep=6`, `borde=10`, resolución 5 mm/px), elegidas para que el
conjunto quede cerca del punto de quiebre entre 2 placas, de forma que el
orden de inserción sí importe. Promedio sobre 10 semillas, para cada
cantidad de reintentos (todas las corridas usaron 2 placas):

| Reintentos | Alto medio en la última placa | Mejor costo observado |
|---|---|---|
| 1 | 830.0mm | (2, 830.0) |
| 3 | 816.0mm | (2, 790.0) |
| 6 | 803.0mm | (2, 780.0) |
| 12 | 800.0mm | (2, 780.0) |
| 24 | 787.0mm | (2, 770.0) |

La mejora es **monotónica y reproducible**: más reintentos siempre bajan (o
igualan) el alto promedio de la última placa. De 3 a 12 reintentos (el salto
de `normal` a la propuesta de `lento`) el promedio baja de 816mm a 800mm
(~2%) y el mejor resultado observado de 790mm a 780mm. Es una mejora modesta
pero real y medible — no es un nivel que "no compra nada".

Se verificó además a escala real, sobre `bench/files/muestra.dxf` con
`--copias 4` (el caso más barato de las dos referencias): con
`EFFORT_RESTARTS["lento"] = 12`, el alto usado en la última (única) placa
bajó de **2413.0mm** (con `normal = 3`) a **2322.0mm** (con `lento = 12`) —
91mm menos, ~3.8% de mejora, en la misma dirección y orden de magnitud que
el escenario sintético. El costo en tiempo fue **575.5s** (~9.6 minutos)
frente a los 182.3s de `normal` — ~3.2x, no exactamente 4x porque el tiempo
por pasada no es perfectamente constante entre reintentos (el margen de una
pasada varía algo según qué piezas quedaron pendientes), pero del orden
correcto.

**`EFFORT_RESTARTS["lento"] = 12`** (4x `normal`, no 120 como estimaba el
brief). Con 120 reintentos, a ~80s/pasada en el caso de `--copias 6`, la
pasada completa habría costado más de dos horas y media — totalmente fuera
de lo razonable para un nivel de esfuerzo que un usuario elige desde una CLI.

### Tabla final

| Nivel | `EFFORT_RESTARTS` | Tiempo medido / extrapolado (`--copias 4` / `--copias 6`) | Alto de la última placa (`--copias 4`) |
|---|---|---|---|
| `rapido` | 1 | 46.2s / 81.1s | — |
| `normal` | 3 | 182.3s / 235.8s | 2413.0mm |
| `lento` | 12 | **575.5s (medido)** / ~742s (extrapolado, ~12.4 min) | **2322.0mm (medido, -3.8%)** |

`lento` en `--copias 6` no se midió directamente (habría costado más de 12
minutos solo para ese punto); se extrapola desde el factor `normal`
`copias6/copias4 = 235.8/182.3 = 1.29x` aplicado al tiempo medido de `lento`
en `--copias 4`.

## 4. Ciclo TDD

### Paso 2 — test que falla

```
ImportError: cannot import name 'EFFORT_RESTARTS' from 'nesting.engine.packer'
```

### Paso 5 — `tests/engine/test_effort.py` en verde

```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 12 items

tests/engine/test_effort.py ............                                 [100%]

============================== 12 passed in 9.32s ==============================
```

(Corrido ya con `EFFORT_RESTARTS` en sus valores finales — `{"rapido": 1,
"normal": 3, "lento": 12}`.)

### Paso 6 — suite completa

```
........................................................................ [ 21%]
........................................................................ [ 43%]
........................................................................ [ 64%]
........................................................................ [ 86%]
.............................................                            [100%]
333 passed in 74.79s (0:01:14)
```

321 tests preexistentes + 12 de `test_effort.py` = 333, todos en verde.

### Verificación end-to-end

`bench/run_bench.py --copias 1` y `python -m nesting.cli` sobre
`bench/files/muestra.dxf` corrieron sin errores con el `effort="normal"` que
ahora es el default de `NestConfig`, confirmando que la caché compartida y
los reintentos quedaron bien conectados fuera de los tests unitarios.

## 5. Desviaciones respecto del brief

1. **`EFFORT_RESTARTS`**: el brief proponía `{"rapido": 1, "normal": 10,
   "lento": 120}` como estimación sin medir. Medido contra el objetivo real
   de 5 minutos para `normal` sobre `bench/files/muestra.dxf`, esos números
   eran completamente inviables (10 reintentos ya superan los 5 minutos por
   un margen enorme; 120 reintentos habrían costado más de dos horas y
   media). Se reemplazaron por `{"rapido": 1, "normal": 3, "lento": 12}`,
   calibrados con las mediciones de §3.
2. **Cómo se comparte la `MaskCache`**: el brief no lo pedía explícitamente
   (surgió de las instrucciones adicionales de esta tarea); se implementó
   sin tocar la firma de `pack()`, cambiando en cambio cómo la CLI y el
   banco construyen la fábrica de oráculos (ver §1). `test_effort.py` no
   ejercita esta ruta porque sigue el código del brief al pie de la letra
   (pasa `RasterOracle` directamente); la ganancia de tiempo se mide y se
   aprovecha en `cli.py`/`bench/run_bench.py`.
3. Se omitió el paso final de commit de git del brief (el proyecto no usa
   control de versiones).

Todo el resto del código (`layout_cost`, `pack`, `_perturb`,
`_compact_last_sheet`, `UnknownEffortError`, `COMPACTION_BOOST`) se
implementó tal cual el brief.

## 6. Corrección post-revisión (dos hallazgos)

### Hallazgo 1 (importante): `lento` podía dar peor resultado que `normal`

**Reproducción confirmada, antes del arreglo** (`muestra.dxf`,
`replicate(parts, 2)` -> 24 piezas, `sep=6`, `margin=10`, `resolution=3`,
`seed=1`):

```
layout_cost(normal) == (1, 1321.0)
layout_cost(lento)  == (1, 1324.0)   <- peor que normal
```

**Causa.** En `pack()`, `normal` perturbaba siempre desde el orden original
por área (`by_area`) — reintentos al azar — mientras que `lento` perturbaba
siempre desde el mejor conocido (`best_order`) — escalada de colina. Con la
misma semilla, ambas trayectorias divergían desde el primer paso, y no había
ninguna relación de superconjunto entre ellas: no hay razón estructural para
que 12 pasos de escalada superen a 3 reintentos al azar. `normal <= rapido`
y `lento <= rapido` sí se cumplían siempre porque los tres comparten la
primera pasada determinística; el hueco estaba solo entre `normal` y
`lento`.

**Arreglo.** `lento` ahora ejecuta primero, exactamente, los mismos
`EFFORT_RESTARTS["normal"] - 1` reintentos que ejecutaría `normal` — misma
base de perturbación (`by_area`) y mismo generador `rng`, consumido en la
misma secuencia (`_perturb` gasta `rng.randrange` la misma cantidad de veces
sin importar el contenido de la lista que recibe, solo depende de
`len(parts)`, así que el stream de `rng` avanza idéntico en ambos niveles
durante ese prefijo). Solo después de agotar el prefijo compartido, `lento`
pasa a perturbar desde `best_order` (escalada de colina) para el resto de
sus reintentos. Al terminar el prefijo, el estado de `lento` es
exactamente el resultado final que tendría `normal`; los reintentos
restantes solo pueden mantenerlo o mejorarlo (nunca empeorarlo, por el `if
candidate_cost < best_cost`). Así, `lento <= normal` queda garantizado por
construcción, igual que ya lo estaba `normal <= rapido`. El código en
`src/nesting/engine/packer.py` (función `pack`) lleva un comentario que
explica esta propiedad y cómo se garantiza.

**Verificación del consumo de `rng`:** se confirmó que, corriendo `normal` y
`lento` con la misma semilla, las primeras `EFFORT_RESTARTS["normal"] - 1`
`candidate_order` que produce `lento` son bit a bit idénticas a las que
produce `normal` (mismo largo de swaps, mismos índices sorteados), porque
ambas ejecutan `_perturb(by_area, rng)` en el mismo orden con el mismo `rng`.

**Reproducción después del arreglo** (misma configuración exacta):

```
layout_cost(normal) == (1, 1321.0)
layout_cost(lento)  == (1, 1300.0)   <- ahora nunca peor que normal
```

### Hallazgo 2 (menor): test que no probaba nada

`test_different_seeds_can_give_different_results` usaba 18 rectángulos
idénticos, donde cualquier orden de inserción da el mismo layout. La
aserción `a.placements != b.placements or a.total_utilization ==
b.total_utilization` se cumplía siempre por la segunda mitad del `or`, sin
ejercitar nunca la primera.

**Arreglo.** Se cambió el fixture a 43 piezas rectangulares de 10 tamaños
distintos — una cantidad elegida por búsqueda para caer justo antes del
punto de quiebre entre una y dos placas (con este material/sep/margen, 42
piezas siempre entran en una placa y 44 siempre necesitan dos; en 43 el
resultado depende de qué tan bueno sea el orden de inserción). Con este
fixture, semillas `1` y `2` producen `placements` distintos de forma
reproducible (se verificó también con otros pares de semillas: `1`/`99`,
`3`/`7`, `1`/`5`, todos difieren). La aserción quedó directa:
`a.placements != b.placements`, sin la cláusula `or` que la vaciaba.

### Tests agregados

Al final de `tests/engine/test_effort.py`:

- `test_effort_levels_are_monotonic`: sobre 3 conjuntos de piezas distintos
  (rectángulos, círculos, otro tamaño de rectángulo) y 3 semillas cada uno,
  con `resolution=5.0` (barato), verifica `layout_cost(lento) <=
  layout_cost(normal) <= layout_cost(rapido)`.
- `test_effort_levels_are_monotonic_on_the_reported_regression`: el caso
  exacto de la reproducción reportada (24 piezas de `muestra.dxf` via
  `replicate(parts, 2)`, `sep=6`, `margin=10`, `resolution=3`, `seed=1`),
  verificando la misma cadena de desigualdades.

No se tocó ningún test existente salvo `test_different_seeds_can_give_
different_results` (Hallazgo 2). No se borró ningún test.

### Docstring de `EFFORT_RESTARTS`

Se amplió para documentar honestamente qué compra cada nivel, con los
números medidos por el revisor: sobre 7 escenarios variados, `normal` empata
con `rapido` (mismo `layout_cost`) en 5 de los 7, pese a costar 3-4x más
tiempo. La ganancia no es gradual: aparece específicamente cuando el layout
está cerca de un punto de quiebre de placa, que es justo donde más vale la
pena — porque ahí es donde se ahorra una placa entera. Se documentó también
que `lento` sigue el mismo patrón un nivel más arriba, y que por eso conviene
usarlo cuando se sospecha que un trabajo está cerca de un quiebre, no como
un dial genérico de "mejor calidad".

### Verificación final

```
$ .venv/bin/pytest -q
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 64%]
........................................................................ [ 85%]
...............................................                          [100%]
335 passed
```

333 preexistentes + 2 tests nuevos (`test_effort_levels_are_monotonic`,
`test_effort_levels_are_monotonic_on_the_reported_regression`) = 335, todos
en verde. Ningún test fue borrado.

Se verificó a mano, además del caso de la reproducción, que `normal <=
rapido` sigue cumpliéndose en varios casos (incluyendo el fixture de 43
piezas del Hallazgo 2), con `resolution=5.0`: en todos los casos probados
(4 conjuntos de piezas x 6 semillas cada uno) se cumplió `lento <= normal <=
rapido` sin ninguna violación.
