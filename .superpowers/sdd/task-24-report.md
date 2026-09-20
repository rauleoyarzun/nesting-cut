# Task 24 — Informe

## Estado

Completa. Los dos parámetros pendientes de calibración quedaron medidos
contra los archivos reales del proyecto (`muestra.dxf` y `banqueta final
raulo.ai`), documentados en `docs/superpowers/calibracion.md`, y fijados en
el código donde correspondía.

## Qué se entregó

- `bench/calibrate.py`: el barrido del brief (`sweep_weights`, `sweep_effort`,
  `main`), extendido con `sweep_resolution` (no estaba en el brief; se agregó
  porque el barrido de resolución también estaba pendiente, per la
  instrucción del pedido), soporte real de `--copias` en los tres barridos
  (el brief lo parseaba pero no lo usaba), y una carga de archivos
  (`_load_files`) que filtra cualquier archivo sin piezas antes de barrer
  (protege contra el `.3dm` de 0 piezas sin que haga falta excluirlo a mano;
  de todos modos su glob es solo `*.dxf` + `*.ai`).
- `bench/run_bench.py`: `run_one` ahora despacha por extensión (`.ai` ->
  `read_ai`, `.3dm` -> `read_3dm`, resto -> `read_dxf`), igual que `cli.py`.
  Sin este cambio `bench/calibrate.py` no podía leer el `.ai` real en
  absoluto (el `run_one` de antes solo sabía `read_dxf`). No estaba en la
  lista de archivos del brief para esta tarea, pero era necesario para que
  el Paso 4 (calibrar contra el archivo real) fuera posible.
- `bench/README.md`: actualizado — decía "el banco todavía no lee `.ai`/`.3dm`",
  ya no es cierto.
- `tests/test_calibration.py`: los tests del brief más
  `test_the_resolution_sweep_covers_every_candidate` y
  `test_the_weight_sweep_respects_the_copies_argument` (agregados porque
  extendí la interfaz con `sweep_resolution` y con `copies`). 5 tests, todos
  en verde.
- `src/nesting/engine/oracle.py`: `Weights.contact` queda en `1.0` (sin
  cambios de valor, pero con docstring nuevo que documenta la medición) y
  `NestConfig.resolution` pasa de `1.0` a `2.0` mm/px.
- `src/nesting/cli.py`: default de `--resolucion` pasa de `1.0` a `2.0`, para
  que coincida con `NestConfig` (son dos defaults independientes; sin este
  cambio la CLI seguiría arrancando en 1.0 aunque la librería cambiara).
- `docs/superpowers/calibracion.md`: los números reales, con las tablas de
  cada barrido, el archivo/copias usado en cada uno, y la comparación
  shelf-vs-raster.
- `EFFORT_RESTARTS` (`engine/packer.py`): **sin tocar**, como pedía el
  encargo — ya estaba calibrado con mediciones (Task 19) y la instrucción
  fue explícita en no recalibrarlo.

## Peso de contacto: se midió, y la medición casi lleva a la conclusión
equivocada

Medido a `--esfuerzo rapido` sobre los dos archivos reales, con suficientes
`--copias` para forzar una segunda placa (con menos copias, tanto
`total_utilization` como `first_sheet_utilization` quedan fijas por la
cantidad de placas y no distinguen nada — lo comprobé antes de confiar en
los primeros números):

- `muestra.dxf` (`--copias 8`, 96 piezas, 2 placas): 63.9% (`contact=0.0`) →
  62.9% (`1.0`, el default) → 61.0% (`4.0`). Monótono, y en la dirección
  contraria a la que se esperaba.
- `banqueta.ai` (`--copias 5`, 200 piezas, 3 placas): 0.0 y 1.0
  dieron el mismo número exacto (60.25%).

Tomado solo, esto dice "bajar el peso a 0". Pero antes de aceptarlo corrí
`tests/engine/raster/test_a_small_part_is_nested_inside_a_big_hole` (la
ganancia concreta de la spec §5.2) con distintos pesos de contacto, y
encontré que **por debajo de ~0.8 esa pieza deja de caer en el agujero**: el
término de contacto deja de poder ganarle a `bottom_left` en esa geometría
puntual, y la pieza chica se va al fondo de la placa vacía en vez de
aprovechar el agujero. Eso es una regresión funcional real, no un matiz de
promedio.

**Conclusión: `contact = 1.0` se queda como está.** Es el valor más chico
que no rompe el anidado en agujeros, y entre los que no lo rompen (1.0, 2.0,
4.0) también es el mejor medido. El valor no cambió, pero antes era una
estimación y ahora es una medición — incluyendo la medición de que la
métrica agregada, sola, hubiera recomendado mal.

## Resolución: sí se cambió

Medido en las mismas condiciones (mismos archivos, mismas copias,
`contact=1.0`):

- `muestra.dxf`: 1.0→2.0 mm/px no costó nada (62.9% idéntico), 4.8× más
  rápido. 1.0→3.0 perdió 2.9 puntos.
- `banqueta.ai`: 1.0→2.0 perdió 0.76 puntos, 4.5× más rápido.
- 0.5 mm/px: no se llegó a medir el aprovechamiento a la densidad de copias
  usada arriba (hubiera sido impracticable en el tiempo de esta sesión); se
  midió el costo en tiempo aparte (a menos copias) y salió ~4.9× más lento
  que 1.0 mm/px, consistente con que la grilla tiene 4× más celdas por lado.
  Ya había una medición previa (Task 15) de que rasterizar conservador infla
  el área +2%/+9% según el tamaño de pieza — la ganancia de densidad que
  compraría 0.5 es marginal frente a ese costo.
- El verificador exacto dio cero violaciones en todas las resoluciones
  medidas: la resolución más gruesa cuesta densidad, nunca corrección.

**`resolucion` (default de `NestConfig` y de `--resolucion`) pasa de `1.0` a
`2.0` mm/px.** Es una ganancia casi gratis en un archivo real y un
intercambio chico y claramente favorable en el otro.

## Niveles de esfuerzo: no se tocaron (fuera de alcance, por instrucción explícita)

`EFFORT_RESTARTS` ya estaba calibrado con mediciones reales en la Task 19.
Corrí los tres niveles sobre `muestra.dxf` como confirmación liviana (no
recalibración), a `--copias 2` en vez de 8 para no pagar el costo de
`lento` (12 reintentos) sobre una placa ya forzada a desbordar — a esa
cantidad de copias el aprovechamiento no distingue nada entre niveles (mismo
motivo que arriba: todo entra en 1 placa), así que la tabla de esta tarea
solo aporta los tiempos: rápido 34.2s, normal 66.9s, lento 220.1s. Consistente
con lo que documenta `packer.py` de la Task 19.

## Comparación motor raster vs. trivial (shelf)

Mismas copias que el barrido principal de cada archivo:

| archivo | shelf: placas / 1ª placa | raster: placas / 1ª placa |
|---|---|---|
| `muestra.dxf` | 3 / 56.14% | 2 / 62.93% |
| `banqueta.ai` | 3 / 54.87% | 3 / 60.25% |

El raster gana en los dos: +6.79 puntos y una placa menos en el archivo
sintético, +5.38 puntos (misma cantidad de placas) en el real.

## Desviación de alcance respecto del pedido original — con motivo

La corrida `bench/calibrate.py --copias 2` (tal como la pide el Paso 4 del
brief, literal) se lanzó dos veces:

1. La primera corrida se perdió: quedó en segundo plano varios minutos
   (barría los tres niveles de esfuerzo, incluido `lento` a 12 reintentos,
   sobre el archivo real) sin salida sin buffer ni vigilancia activa, y el
   proceso se cayó sin dejar ningún resultado escrito.
2. Al investigar qué había pasado, encontré algo más importante: **a
   `--copias 2` ninguna de las dos métricas (`total_utilization` ni
   `first_sheet_utilization`) distingue nada entre configuraciones**,
   porque con esa cantidad de copias todo entra en una sola placa y ambas
   métricas quedan fijadas por el área total de piezas, sin importar cómo
   se acomoden (lo confirmé viendo `contact=0.0` y `contact=0.5` devolver
   exactamente el mismo número, 16 cifras significativas, en una corrida
   real). Es el mismo fenómeno que el pedido advertía para
   `total_utilization` a igualdad de placas, pero se extiende también a
   `first_sheet_utilization` en cuanto nada desborda.

Por los dos motivos, re-corrí todo con guiones puntuales (no
`bench/calibrate.py --copias 2` tal cual) contra `bench.run_bench.run_one`,
con salida sin buffer y bajo vigilancia activa esta vez, usando `--copias 8`
para `muestra.dxf` y `--copias 5` para el archivo real (las copias mínimas
que superan el 100% del área de una placa mdf18 para cada archivo, así el
empacador de verdad tiene que decidir qué deja afuera de la primera placa).
El alcance quedó reducido del barrido combinatorio completo del brief
(5 contactos × 2 archivos, 4 resoluciones × 2 archivos, 3 esfuerzos × 2
archivos) a un subconjunto representativo — el detalle exacto de qué se
corrió sobre cada archivo, y por qué, está en
`docs/superpowers/calibracion.md` bajo "Alcance de esta corrida". Nada de
esto quedó a ciegas: cada número reportado en este informe y en
`calibracion.md` es de una corrida real, con su archivo, sus copias y su
tiempo anotados.

## Verificación

- `tests/test_calibration.py`: 5 passed.
- `tests/engine/raster/test_raster_oracle.py`: 13 passed (incluye
  `test_a_small_part_is_nested_inside_a_big_hole`, el test que motivó
  mantener `contact=1.0`).
- Suite completa (`.venv/bin/pytest -q`): **407 passed, 0 failed** (exit
  code 0), sin regresiones por los cambios de default. Ningún test de
  densidad se rompió con `resolucion=2.0` ni con la confirmación de
  `contact=1.0`. (402 preexistentes + 5 de `tests/test_calibration.py`; el
  número de base mencionado en el encargo, 398, corresponde a un punto algo
  anterior del proyecto.)

## Valores fijados (resumen)

| Parámetro | Antes | Después | ¿Cambió? |
|---|---|---|---|
| `Weights.contact` | 1.0 | 1.0 | No — confirmado con datos |
| `NestConfig.resolution` | 1.0 mm/px | 2.0 mm/px | Sí |
| `--resolucion` (CLI) | 1.0 mm/px | 2.0 mm/px | Sí (mismo motivo, default independiente) |
| `EFFORT_RESTARTS` | `{1, 3, 12}` | `{1, 3, 12}` | No — fuera de alcance |
