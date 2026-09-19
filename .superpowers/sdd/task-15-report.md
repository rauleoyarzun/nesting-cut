# Task 15 — Rasterizado de piezas (`engine/raster/masks.py`)

## Archivos creados

- `src/nesting/engine/raster/__init__.py` (vacío)
- `src/nesting/engine/raster/masks.py`
- `tests/engine/raster/__init__.py` (vacío)
- `tests/engine/raster/test_masks.py`

## Ciclo TDD

### Paso 2 — correr el test antes de implementar (falla como se esperaba)

```
$ .venv/bin/pytest tests/engine/raster/test_masks.py -v
============================= test session starts ==============================
collected 0 items / 1 error

==================================== ERRORS ====================================
______________ ERROR collecting tests/engine/raster/test_masks.py ______________
ImportError while importing test module '.../tests/engine/raster/test_masks.py'.
Traceback:
tests/engine/raster/test_masks.py:4: in <module>
    from nesting.engine.raster.masks import MaskCache, PartMasks, disk_kernel, rasterize
E   ModuleNotFoundError: No module named 'nesting.engine.raster.masks'
=========================== short test summary info ============================
ERROR tests/engine/raster/test_masks.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.10s ===============================
```

### Implementación (Paso 3)

Se implementó `masks.py` copiando el código exacto del brief. Al correr el
test por primera vez con la implementación literal, aparecieron **2 fallas**
reales (no atribuibles a un error de tipeo mío, confirmado byte a byte contra
el brief) — ver la sección "Desviaciones" más abajo:

```
$ .venv/bin/pytest tests/engine/raster/test_masks.py -v
tests/engine/raster/test_masks.py .....F......F.....                     [100%]

=================================== FAILURES ===================================
________________ test_clearance_grows_by_roughly_the_separation ________________
    assert 13000 < grown < 14400
E       assert np.float64(14517.0) < 14400

______________ test_origin_places_the_part_where_the_formula_says ______________
    assert not masks.occupied[row, col]
E       assert not np.True_

========================= 2 failed, 16 passed in 0.33s =========================
```

Tras aplicar las dos correcciones descritas abajo:

### Paso 4 — test dirigido, en verde

```
$ .venv/bin/pytest tests/engine/raster/test_masks.py -v
tests/engine/raster/test_masks.py ..................                     [100%]
============================== 18 passed in 0.33s ==============================
```

### Suite completa

```
$ .venv/bin/pytest
........................................................................ [ 27%]
........................................................................ [ 55%]
........................................................................ [ 83%]
...........................................                              [100%]
259 passed in 1.90s
```

241 tests previos + 18 nuevos = 259. Sin regresiones.

## Desviaciones respecto del brief (con motivo)

El brief presenta el código de `masks.py` y de `test_masks.py` como "exacto".
Los transcribí literalmente (verificado con `grep` contra el archivo del
brief) y, al ejecutarlos contra el Pillow instalado en este proyecto
(`12.3.0`) y con `numpy` estándar, dos casos fallan por razones ajenas a un
error de tipeo. Documento cada uno porque las cuatro decisiones de diseño
(grilla compartida, `origin`, convención de índices, re-rasterizado en cada
ángulo) se mantuvieron intactas — los ajustes son correcciones puntuales, no
cambios de arquitectura.

### 1. `ImageDraw.polygon` de Pillow es inclusivo en ambos bordes cuando un lado cae justo sobre una línea entera de la grilla

Comprobado empíricamente: dibujar un polígono cuyas coordenadas son enteros
exactos en una grilla de resolución entera (por ejemplo un rectángulo de
100×100 mm con resolución 1 mm, que es exactamente el caso de
`test_clearance_grows_by_roughly_the_separation`) rellena `(w+1) × (h+1)`
píxeles en vez de `w × h` — Pillow incluye tanto el borde de partida como el
de llegada del polígono, en vez de tratar el de llegada como abierto. Esto
infla el área "occupied" real (10201 en vez de 10000 para el ejemplo de
100×100), y esa inflación se propaga a la dilatación, empujando
`test_clearance_grows_by_roughly_the_separation` fuera de la cota superior
del test (14517 vs. el límite 14400).

**Corrección aplicada:** en `_to_pixels`, después de convertir a coordenadas
de píxel, cada anillo (contorno exterior o agujero) se contrae una fracción
insignificante (`1e-6` relativo) hacia su propio centroide
(`_nudge_off_grid_lines`). Esto rompe el empate de Pillow sin mover el
polígono de forma perceptible — verificado experimentalmente: un `eps` de
`1e-9` ya alcanza para eliminar la fila/columna extra en el caso de prueba.
Esta técnica es genérica (no depende de que la pieza sea un rectángulo) y no
toca ninguna de las cuatro fórmulas de diseño (grilla compartida, `origin`,
convención de índices, re-rasterizado por ángulo).

### 2. Un índice negativo de numpy hace *wraparound* en vez de fallar

`test_origin_places_the_part_where_the_formula_says` (versión original del
brief) consulta el punto `(-20.0, -20.0)` para una pieza de 100×50 mm con
`sep=5.0`. Con `pad = ceil(sep/resolución) = 5`, `origin = (-5, -5)` y la
grilla resultante mide 111×61 píxeles. El punto de prueba cae en el índice
`(-15, -15)`: como `abs(-15) < 61` y `< 111`, numpy no lanza `IndexError` —
interpreta el índice negativo como *wraparound* y lee la celda
`(61-15, 111-15) = (46, 96)`, que corresponde al punto mundial `(91, 41)`,
**dentro** del rectángulo. El test terminaba comparando un píxel realmente
ocupado, no uno "claramente afuera".

Esto es independiente del bug de Pillow: no depende de que el occupied esté
inflado, sino de la combinación específica de `pad=5` con un desplazamiento
de -20 mm, que hace que el índice negativo entre en el rango válido del
arreglo y aterrice justo en el interior de la pieza. No es corregible sin
tocar las fórmulas de `pad`/`origin`/`width`/`height` que las tareas
siguientes van a depender de (inflar el padding arbitrariamente para blindar
este único caso de prueba sería peor: cambiaría el comportamiento de
producción — memoria y performance — para resolver una coincidencia de un
test).

**Corrección aplicada:** en `tests/engine/raster/test_masks.py`, cambié el
punto de prueba "claramente afuera" de `(-20.0, -20.0)` a `(-3.0, -3.0)`.
Sigue estando fuera del contorno de la pieza (que empieza en `(0,0)`), pero
el índice resultante `(2, 2)` es positivo y cae dentro de la zona de
acolchado real de la grilla, así que no hay wraparound. La intención del
test (un punto fuera de la pieza no debe estar ocupado) se preserva
intacta; sólo cambia la magnitud del desplazamiento. Dejé un comentario en
el propio test explicando el motivo del cambio.

Ningún otro test ni la implementación de producción necesitaron cambios
además de estos dos puntos.

## Notas de implementación

- Las cuatro decisiones de diseño del enunciado (grilla única para
  `occupied`/`clearance`, fórmula de `origin`, convención `mask[fila,
  columna]` sin invertir nada, y re-rasterizado del polígono en cada ángulo
  en vez de rotar el bitmap) se implementaron exactamente como se
  especificaron.
- Se omitió el paso de commit de git indicado al final del brief, según lo
  pedido explícitamente (este proyecto no usa git).

---

## Addendum — arreglo de 5 hallazgos de code review (`masks.py`)

Sesión posterior: se corrigieron los 5 hallazgos reportados sobre este mismo
módulo. Ningún test existente se borró; se ajustaron 2 (con comentario
explicando el motivo) y se agregaron 7 nuevos. Suite completa: **266
passed** (259 previos + 7 nuevos).

### Hallazgo 1 (CRÍTICO) — `occupied` podía representar menos material del que hay

**1a.** Se quitó `_nudge_off_grid_lines` (la contracción de `1e-6` hacia el
centroide). Los anillos pasan a Pillow tal cual. Esa contracción se aplicaba
por igual a todo lado, no solo al caso alineado a la grilla que la motivó, y
en los lados diagonales empeoraba justo el problema que había que resolver
(medido: un rectángulo rotado 33° pasaba de 12 a 29 píxeles faltantes; un
triángulo sin rotar, de 0 a 12).

Se ajustó la cota superior de `test_clearance_grows_by_roughly_the_separation`
de `< 14400` a `< 15300`, con un comentario explicando que el relleno inclusivo de Pillow
sobre-representa un poco (lado seguro) y que por eso se adapta el test en
vez de deformar la geometría de producción.

**1b.** Se agregó una dilatación de seguridad de radio 1 (estructura 3×3
completa, con diagonales) sobre `occupied`, inmediatamente después de
rasterizar con Pillow y antes de calcular `clearance` (así `clearance`
también queda protegida, que es lo deseado). Se verificó empíricamente que
una estructura tipo "cruz" (4-conectada, `disk_kernel(1)`) **no alcanza**:
deja 28 píxeles faltantes contra shapely en el mismo barrido de
combinaciones; la estructura cuadrada de 3×3 (8-conectada) da cero
faltantes. Se documentó la asimetría en un comentario: sobre-representar
solo cuesta densidad, sub-representar rompe la correctitud del motor
completo.

Efecto colateral esperado y aceptado: el padding de la grilla se subió de
`max(1, radius)` a `max(1, radius) + 1` para dejarle lugar a esta dilatación
extra sin que se recorte contra el borde del arreglo.

Esto también obligó a relajar `test_occupied_area_matches_the_part_area` de
`rel=0.05` a `rel=0.12` (con comentario): para una pieza chica (100×50 mm),
el anillo de 1 píxel que agrega la dilatación de seguridad pesa
proporcionalmente más que en una pieza grande, y por la misma razón de
"sobre-representar es el lado seguro" se ajustó el test en vez de la
geometría.

**Verificación obligatoria (nuevo test):**
`test_occupied_never_under_represents_the_exact_polygon` compara, píxel por
píxel contra shapely, 4 formas (rectángulo, triángulo, L cóncava, anillo con
agujero) × 8 ángulos (0, 17, 33.3, 45, 90, 137, 180, 270) × 3 resoluciones
(0.5, 1, 2 mm/px) × con/sin espejado = **192 combinaciones**. Resultado
medido:

```
conservadurismo hallazgo 1: 192 combinaciones, 7346747 pixeles evaluados, 0 faltantes
```

Cero píxeles faltantes: todo píxel cuyo centro cae dentro del polígono
exacto queda marcado en `occupied`.

### Hallazgo 2 (IMPORTANTE) — la caché podía devolver la máscara de otra pieza

`MaskCache` indexaba por `part.id`. Se cambió la clave para incluir la
pieza entera (`Part` es un dataclass `frozen=True` de tuplas, ya hashable),
así la geometría entra en la identidad de la clave. Nuevo test:
`test_the_cache_distinguishes_parts_that_share_an_id`, con dos piezas de
distinta geometría y el mismo `id`.

### Hallazgo 3 (IMPORTANTE) — sin cota de tamaño de grilla

Se agregó `MAX_GRID_PIXELS = 600_000_000`, documentado como constante con
comentario: cubre la placa más grande del catálogo (mdf, 1830×2600 mm) a 0.1
mm/px (la resolución más fina razonable en este dominio) más acolchado de
separación (~480M píxeles), y rechaza con `ValueError` (mensaje en español
con las dimensiones de la pieza, la resolución pedida, cuántos píxeles
saldrían y la sugerencia de usar una resolución más gruesa) combinaciones
patológicas como la medida en el brief (500×500 mm a 0.02 mm/px, sep=2 →
~635M píxeles). Nuevo test:
`test_rasterize_rejects_a_grid_that_would_be_too_big`.

### Hallazgo 4 (IMPORTANTE) — el tope de la caché contaba entradas, no bytes

`MaskCache` pasó de `max_entries` a `max_bytes` (constante
`DEFAULT_CACHE_BUDGET_BYTES = 256 * 1024 * 1024`, 256 MiB). Cada `get` suma
`nbytes` de `occupied` + `clearance` de la entrada nueva y expulsa por
antigüedad (LRU, sin tocar el orden) hasta entrar en el presupuesto,
conservando siempre al menos la última entrada insertada (para que una
pieza legítimamente más grande que el presupuesto siga siendo usable en vez
de imposible de cachear). `test_the_cache_evicts_the_oldest_entry_when_full`
se adaptó (sin borrarse) para calibrar `max_bytes` a partir del peso real de
una entrada; se agregaron `test_the_cache_defaults_to_the_documented_byte_budget`,
`test_the_cache_never_exceeds_its_byte_budget` y
`test_the_cache_keeps_at_least_one_entry_even_over_budget`.

### Hallazgo 5 (MENOR) — `sep` negativo no se validaba

Se agregó `if sep < 0.0: raise ValueError(...)` en `rasterize`, mensaje en
español, análogo a la validación de `resolution`. Nuevo test:
`test_rasterize_rejects_negative_sep`.

### Verificación final

```
$ .venv/bin/pytest -q
266 passed in 1.93s
```

259 previos + 7 nuevos (`test_the_cache_defaults_to_the_documented_byte_budget`,
`test_the_cache_never_exceeds_its_byte_budget`,
`test_the_cache_keeps_at_least_one_entry_even_over_budget`,
`test_the_cache_distinguishes_parts_that_share_an_id`,
`test_rasterize_rejects_negative_sep`,
`test_rasterize_rejects_a_grid_that_would_be_too_big`,
`test_occupied_never_under_represents_the_exact_polygon`) = 266. Sin
regresiones. Ningún test se borró; 2 se ajustaron con comentario
(`test_clearance_grows_by_roughly_the_separation`,
`test_occupied_area_matches_the_part_area`) y uno más se adaptó al nuevo
parámetro de la caché sin cambiar lo que verifica
(`test_the_cache_evicts_the_oldest_entry_when_full`).

### Costo en área de la dilatación (pieza de 300 mm, 1 mm/px)

Medido comparando el `occupied` final (con la dilatación de seguridad)
contra el mismo `occupied` generado por Pillow crudo, sin la dilatación,
para un cuadrado de 300×300 mm a resolución 1 mm/px, sep=0:

```
area real:                              90000.0 mm²
area Pillow crudo (sin dilatacion):     90601.0 mm²  (+0.668% sobre el area real)
area final (con dilatacion de 1 px):    91809.0 mm²  (+2.010% sobre el area real)
crecimiento atribuible a la dilatacion: +1.333%
```

Es decir: la dilatación de seguridad por sí sola agrega ~1.33% de área sobre
lo que ya rasterizaba Pillow (que de por sí sobre-representaba ~0.67%), para
un total de ~2.01% de sobre-representación sobre el área real de la pieza a
esta resolución. El costo crece más rápido cuanto más chica es la pieza
(perímetro/área más alto): para la pieza de 100×50 mm usada en los tests, el
mismo efecto empuja el área "occupied" a ~9.2% sobre el área real, de ahí el
ajuste de tolerancia en `test_occupied_area_matches_the_part_area`.

## Hallazgo 6 (cierre): asimetría en el rasterizado de agujeros

### El problema

La dilatación de seguridad de 1 píxel (Hallazgo 1) corrige el sub-marcado de
Pillow en el **exterior**, pero antes de este cierre los agujeros se restaban
con el mismo relleno inclusivo de Pillow (`draw.polygon(hole, fill=0)` sobre
la misma imagen que el exterior) y después la dilatación de seguridad se
aplicaba sobre el resultado ya combinado. El exterior y los agujeros
contribuyen a `occupied` con signos opuestos: "cubrir de más" en el exterior
agranda la pieza (seguro), pero "cubrir de más" en un agujero borra material
real (peligroso) — el motor podría colocar una pieza más cerca de una pared
interior de lo permitido, y el verificador exacto rechazaría el layout.

Verificación manual (no con las formas del test original, que resultaron
tener paredes demasiado gruesas para exhibir el problema): con un anillo de
paredes finas y agujero descentrado, a resolución 1.0 mm/px, se encontraron
11 píxeles de material real sin marcar bajo el código anterior; con el
código nuevo, 0. Una búsqueda aleatoria más amplia sobre formas
adversariales (paredes finas, agujero descentrado, muchos lados) encontró
casos con miles de píxeles faltantes bajo el código anterior — siempre 0
bajo el nuevo.

### El arreglo

Se separó el rasterizado en dos máscaras independientes, cada una con la
operación morfológica que le corresponde:

```python
outer_image = Image.new("1", (width, height), 0)
ImageDraw.Draw(outer_image).polygon(_to_pixels(outer, origin, resolution), fill=1)
outer_mask = np.array(outer_image, dtype=bool)

holes_image = Image.new("1", (width, height), 0)
holes_draw = ImageDraw.Draw(holes_image)
for hole in holes:
    holes_draw.polygon(_to_pixels(hole, origin, resolution), fill=1)
holes_mask = np.array(holes_image, dtype=bool)

safety = np.ones((3, 3), dtype=bool)
outer_mask = binary_dilation(outer_mask, structure=safety)   # cubre de más: seguro
holes_mask = binary_erosion(holes_mask, structure=safety)    # cubre de menos: seguro

occupied = outer_mask & ~holes_mask
```

Un agujero más chico que el radio de erosión puede desaparecer por completo
(la erosión lo vacía a todo-`False`). Eso no es un bug: un agujero que
desaparece se trata como material macizo en vez de espacio libre, que es el
resultado conservador — la pieza simplemente no puede aprovecharse por
dentro de un agujero así de chico. Se dejó un comentario explícito en el
código para que no se confunda con una regresión.

### Test ampliado

`test_occupied_never_under_represents_the_exact_polygon` ahora incluye, además
de las 4 formas anteriores, tres formas nuevas con agujeros reales:

- `anillo_muchos_lados`: un 24-gono exterior (radio 150) con un 18-gono
  interior (radio 70), concéntrico.
- `anillo_descentrado`: un 9-gono exterior (radio 150) con un 23-gono interior
  (radio 72) descentrado, para que el grosor de la pared varíe alrededor del
  anillo en vez de ser uniforme — la condición bajo la que se detectó el
  faltante.
- `multi_agujero`: una pieza rectangular con tres agujeros de tamaños muy
  distintos (60×60, 130×100 y 12×12 mm), el último chico a propósito para
  ejercitar el caso límite de la erosión.

Un "agujero dentro de un agujero" no se agregó: el modelo `Part` no lo
admite. `Part.holes` es una lista plana de anillos que se restan todos del
mismo `outer`; un contorno a profundidad 2 o más se convierte en una pieza
independiente (`nesting_tree.build_parts`), no en una isla anidada dentro de
un mismo `Part`. Se dejó la nota en el test.

El barrido de ángulos se amplió para incluir 151.0° (junto con la resolución
0.5 mm/px y mirror=False ya presentes en el barrido), la combinación exacta
señalada como reproductora del problema.

### Verificación final

```
$ .venv/bin/pytest -q
266 passed in 3.32s
```

Sin regresiones (mismos 266 tests que antes de este cierre; ningún test
borrado). El chequeo de conservadurismo ampliado:

```
conservadurismo hallazgo 1: 378 combinaciones, 34349611 pixeles evaluados, 0 faltantes
```

(7 formas × 9 ángulos × 3 resoluciones × 2 mirrors = 378 combinaciones,
34.3 millones de píxeles comparados contra `shapely.contains_xy`, cero
faltantes.)

### Costo en área por la erosión de agujeros

Comparando el área de `occupied` antes y después de este cierre (mismo
exterior dilatado; la única diferencia es que el agujero se erosiona en vez
de restarse con el relleno inclusivo de Pillow directamente combinado con el
exterior):

- Para las formas realistas ejercitadas por el test (agujero rectangular
  alineado a los ejes, anillo de muchos lados concéntrico, anillo
  descentrado, y la pieza con tres agujeros de distinto tamaño), en **todos**
  los ángulos, resoluciones y valores de `sep` probados, el cambio medido es
  **0.000%**: la dilatación del código anterior (aplicada sobre el arreglo ya
  combinado) ya recuperaba, por crecimiento desde píxeles vecinos, lo mismo
  que la erosión separada recupera, siempre que la pared del agujero tenga
  grosor razonable frente a la resolución.
- El costo solo aparece con geometría adversarial: pared muy fina, agujero
  descentrado, resolución gruesa relativa al tamaño de la pieza. Una búsqueda
  aleatoria amplia sobre esas configuraciones patológicas encontró un peor
  caso de **+2.02%** de área `occupied` (hexágono exterior de radio 150 con
  un agujero casi circular de radio ~125 descentrado 10.6 mm, a 2 mm/px) —
  exactamente el tipo de caso que antes perdía material real y que ahora
  queda cubierto de más en su lugar, que es el lado seguro.

En síntesis: el costo típico es despreciable (0% en los casos ejercitados
por el test) y el peor caso encontrado, para geometría deliberadamente
patológica, es de apenas un par de puntos porcentuales — un precio bajo por
eliminar la posibilidad de borrar material real cerca de la pared de un
agujero.

---

## Cierre definitivo: supermuestreo (deja de depender de la semántica de relleno de Pillow)

### Por qué el cierre anterior no alcanzaba

El cierre de arriba asumía que el error de `PIL.ImageDraw.polygon` estaba
acotado a ~1 píxel, y lo compensaba con una única dilatación/erosión de
seguridad de radio 1 sobre el relleno directo a la resolución final. Un
barrido más exigente (más resoluciones, más ángulos, paredes finas y
agujeros descentrados) encontró que ese supuesto es falso:

```
500 combinaciones, 37.803.209 pixeles evaluados, FALTANTES 1767
peor caso: 94 faltantes en "L con 3 agujeros", angulo 11.7, resolucion 0.4 mm/px
```

El problema de fondo es depender de una semántica de relleno que Pillow no
especifica ni acota.

### El arreglo

`rasterize` ya no confía en que Pillow acierte al píxel a la resolución
final. Ahora:

1. Rasteriza con Pillow en una grilla `SUPERSAMPLE=4` veces más fina por
   lado (`fine_resolution = resolution / SUPERSAMPLE`).
2. Reduce a la grilla final con `numpy` (reshape a bloques `N×N` + `any`/
   `all` sobre los dos ejes de bloque):
   - Exterior: `_downsample_any` — cubre de más, que sigue siendo el lado
     seguro para el exterior.
   - Agujeros: `_downsample_all` — cubre de menos, que sigue siendo el lado
     seguro para lo que se resta.
3. Se mantiene la dilatación/erosión de seguridad de 1 píxel **final** sobre
   el resultado reducido. Con el error de Pillow ya en el orden de
   `1/SUPERSAMPLE` de píxel final, esa dilatación/erosión lo cubre con
   margen de sobra en vez de justo.

`MAX_GRID_PIXELS` pasó a acotar la grilla **fina** (la que Pillow rasteriza
de verdad, `SUPERSAMPLE**2` veces más pixeles que antes), no la final, para
no arriesgar memoria — ver el comentario junto a la constante en
`masks.py` para el razonamiento completo y por qué se mantuvo el mismo
valor numérico en vez de escalarlo.

Se agregó `tests/engine/raster/test_masks.py::test_occupied_never_under_represents_under_a_harsh_sweep`,
el barrido exacto que encontró los faltantes (5 formas adversariales × 10
ángulos × 5 resoluciones × 2 mirrors = 500 combinaciones), sin debilitar
ninguno de sus parámetros.

### Verificación

```
$ .venv/bin/pytest -q
267 passed in 17.02s
```

Sin tests borrados (los 266 anteriores siguen, más el nuevo del barrido
exigente). Un test existente (`test_a_hole_is_not_occupied`) necesitó
relajar su tolerancia de `rel=0.05` a `rel=0.06`: para un cuadrado y un
agujero perfectamente alineados a la grilla, la reducción por bloques con
criterios opuestos (`any`/`all`) desbalancea un poco el sobrante de 1 píxel
que el relleno inclusivo de Pillow ya agregaba de por sí en ese caso límite
alineado, dejando un poco más de sobre-representación que antes (~5.35% en
vez de ~4.7%). Sigue siendo el lado seguro (sobre-representar), así que se
ajustó la tolerancia con un comentario explicando por qué, en vez de
angostar el supermuestreo.

El barrido del brief, corrido directamente:

```
500 combinaciones, 86.257.404 pixeles evaluados, FALTANTES 0
```

### Costo medido

**Tiempo** — `rasterize` de una pieza cuadrada de 300×300 mm a 1 mm/px
(ángulo 33°, sep=4.0, 30 repeticiones tras warmup):

- Antes (sin supermuestreo): **~3.7 ms** por llamada.
- Ahora (`SUPERSAMPLE=4`): **~9.6 ms** por llamada.

≈2.6× más lento — bastante por debajo del 16× que predice `N²` en el peor
caso, porque el costo no lo domina el rasterizado de Pillow (que es C y
escala bien) sino las operaciones morfológicas y la reducción por bloques,
que corren sobre arrays más chicos.

**Densidad** — área de `occupied` vs. el área exacta del polígono, ambas a
1 mm/px, sep=4.0, sin rotar:

| Pieza | Antes | Ahora | Cambio |
|---|---|---|---|
| 300×300 mm (cuadrado, sin agujeros) | +2.01% | +2.01% | 0.00 p.p. |
| 100×50 mm (rectángulo, sin agujeros) | +9.18% | +9.18% | 0.00 p.p. |

Para estas dos piezas de referencia (rectangulares, sin agujeros, sin
rotar) el cambio es exactamente nulo: el exterior alineado a la grilla se
reduce con `any` sin perder el sobrante de Pillow, igual que antes. El
único costo de densidad medido en toda esta tarea aparece en piezas **con
agujeros** alineados a la grilla (ver `test_a_hole_is_not_occupied` arriba),
del orden de una fracción de punto porcentual — sigue siendo sobre-
representación, el lado seguro.

En síntesis: el supermuestreo cuesta ~2.6× en tiempo de rasterizado para
una pieza mediana-grande, y no mide costo adicional de densidad para
piezas sin agujeros; el costo de densidad que sí aparece (piezas con
agujero alineado) es de fracciones de punto porcentual. A cambio, elimina
por completo la dependencia de que Pillow acierte al píxel, que es lo que
dejaba escapar material real bajo un barrido más exigente.
