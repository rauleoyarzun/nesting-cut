# Calibración — 2026-09-18

Medido con `bench/calibrate.py` (y, para el desborde de placa que hizo falta
forzar, con llamadas directas a `bench.run_bench.run_one` desde scripts
puntuales — ver la nota de alcance más abajo) sobre los archivos de
`bench/files/`.

## Archivos

| Archivo | Piezas (1 copia) | Origen |
|---|---|---|
| `muestra.dxf` | 12 (4 asientos + 8 patas cóncavas) | Sintético, generado por `bench/make_sample.py` — pensado a propósito con curvas y concavidades para estresar el término de contacto |
| `banqueta.ai` | 40 | Export real desde CorelDRAW (AI3) del proyecto de una banqueta |
| `banqueta.3dm` | 0 | Modelo 3D del ensamblaje armado (Task 23), no un layout de corte plano. No entra en `bench/calibrate.py` (su glob es `*.dxf` + `*.ai`) y no sirve para calibrar. |

## Nota de método: por qué hizo falta forzar desborde de placa

El aprovechamiento **total** es área de piezas sobre área de placas usadas:
con la misma cantidad de placas da **idéntico por construcción**, sea cual
sea la calidad del acomodo. Pero lo mismo le pasa a
**`first_sheet_utilization`** cuando *todas* las piezas entran en la primera
placa: en ese caso también es un cociente fijo (área total de piezas / área
de la placa), independiente de cómo se acomoden. Con `--copias 1` o `2` en
cualquiera de los dos archivos reales, todo entra en una sola placa, así que
**ninguna de las dos métricas distingue configuraciones** — se comprobó
midiendo (`contact=0.0` y `contact=0.5` dieron exactamente el mismo
`first_sheet_utilization`, 16 cifras significativas incluidas, que el
default en una corrida a `--copias 2` del archivo real).

Para que el acomodo importe hay que usar suficientes copias como para que el
área total supere el 100% de una placa, forzando una segunda placa y
obligando al empacador a decidir qué subconjunto de piezas deja en la
primera. Con eso:

- `muestra.dxf`: 12 piezas ocupan 13.56% de una placa mdf18 (1830×2600 mm) →
  hacen falta **8 copias** para pasar el 100% (108.5%).
- `banqueta.ai`: 40 piezas ocupan 25.34% → hacen falta **5
  copias** para pasar el 100% (126.7%).

Todo lo medido en este documento usa `--copias 8` para `muestra.dxf` y
`--copias 5` para el archivo real, salvo donde se indica lo contrario.

## Alcance de esta corrida (reducido a propósito)

La corrida original de `bench/calibrate.py --copias 2` (Paso 4 del brief)
se perdió: corrió en segundo plano varios minutos, pero al no usar salida sin
buffer ni quedar bajo vigilancia activa, el proceso se perdió sin dejar
registro antes de completarse la barrida completa (`lento` sobre el archivo
real solo, a 12 reintentos, tarda varios minutos). Además, `--copias 2` es
justo el caso descrito arriba donde la métrica no distingue nada, así que
esa corrida tampoco hubiese servido.

La corrida real que sí produjo los números de este documento usó scripts
puntuales (no interactivos, con flush inmediato a disco) contra
`bench.run_bench.run_one`, con el mismo motor/parámetros que
`bench/calibrate.py` sweepea, pero con alcance reducido para que terminara
en un tiempo razonable:

- **Peso de contacto:** barrido completo (0.0, 1.0, 4.0) sobre `muestra.dxf`
  a `--copias 8`; confirmación en los extremos (0.0 vs. 1.0) sobre el archivo
  real a `--copias 5`. No se corrieron 0.5 y 2.0 sobre archivos reales
  (sí están cubiertos por `tests/test_calibration.py`, con archivo sintético
  chico y resolución gruesa).
- **Resolución:** barrido completo (0.5, 1.0, 2.0, 3.0) sobre `muestra.dxf`
  a `--copias 8` — salvo 0.5, que a esa densidad hubiera sido
  impracticable (la grilla tiene 4x más celdas por lado que a 1.0 mm/px) y
  se midió aparte, solo el tiempo, a `--copias 2`. Confirmación en 1.0 vs.
  2.0 sobre el archivo real a `--copias 5`.
- **Niveles de esfuerzo:** los tres niveles sobre `muestra.dxf`, pero a
  `--copias 2` (no 8): `EFFORT_RESTARTS` ya está calibrado (Task 19, con
  este mismo archivo) y esta tabla es de confirmación, no de
  recalibración — no hacía falta pagar el desborde de placa, y `lento`
  (12 reintentos) sobre una placa ya llena hubiera sido demasiado lento para
  el presupuesto de esta sesión.
- **Línea de base (shelf vs. raster):** ambos archivos, a las mismas
  copias que su barrido principal (8 y 5 respectivamente).

Cada corrida es de un solo archivo (no el conjunto agregado de
`bench/calibrate.py`), pero usa la misma semilla (`seed=0`, el default),
el mismo material (`mdf18`) y varía un solo parámetro a la vez contra la
misma configuración base (`sep=6.0, margin=10.0, esfuerzo=rapido` salvo
donde se indica). `bench/calibrate.py` (Step 1) queda extendido con
`sweep_resolution` y con soporte de `--copias`, así que una corrida futura
con más presupuesto de tiempo puede repetir esto mismo end-to-end con
`.venv/bin/python bench/calibrate.py --material mdf18 --copias 5`.

## Peso de contacto

`bottom_left` fijo en 1.0, esfuerzo `rapido`, resolución 1.0 mm/px.

### `muestra.dxf`, `--copias 8` (96 piezas, 2 placas en los tres casos)

| contacto | aprov. 1ª placa | segundos |
|---|---|---|
| 0.0 | 63.90% | 109.7 |
| 1.0 (default) | 62.93% | 175.6 |
| 4.0 | 60.99% | 179.8 |

### `banqueta.ai`, `--copias 5` (200 piezas, 3 placas en ambos casos)

| contacto | aprov. 1ª placa | segundos |
|---|---|---|
| 0.0 | 60.25% | 206.1 |
| 1.0 (default) | 60.25% (idéntico) | 312.5 |

**Hallazgo, con los números en la mano:** subir el peso de contacto **no
mejora** el aprovechamiento de la primera placa en ninguno de los dos
archivos reales — en `muestra.dxf` lo empeora de forma monótona (63.9% →
62.9% → 61.0% al ir de 0.0 a 1.0 a 4.0) y en el archivo real da exactamente
igual. Además `contact=0.0` es más rápido en ambos (34-46% menos tiempo),
porque salta por completo la correlación de contacto
(`raster/scoring.py::best_position`, `if weights.contact != 0.0 and
sheet.any() and band.any()`). Tomado en aislado, esto diría "apagar el
término".

Pero hay una segunda medición que pesa más que el promedio agregado:
`tests/engine/raster/test_raster_oracle.py::test_a_small_part_is_nested_inside_a_big_hole`
verifica la ganancia concreta de la spec §5.2 (una pieza chica cae dentro
del agujero de una grande en vez de plancharse aparte). Se hizo una
bisección del peso de contacto sobre ese mismo caso:

| contacto | ¿la pieza chica cae en el agujero? |
|---|---|
| 0.0, 0.5 | No |
| 0.6, 0.7 | No |
| 0.8, 0.9, 0.95, 1.0, 2.0, 4.0 | Sí |

Por debajo de ~0.8, `bottom_left` solo le gana el argmax al término de
contacto y la pieza chica se va al fondo-izquierda de la placa vacía en vez
de meterse en el agujero — geométricamente válido, pero desperdicia
exactamente el espacio que el hito 3 promete recuperar. Esa capacidad pesa
más que un par de puntos de aprovechamiento agregado, así que **cualquier
candidato por debajo de 1.0 queda descartado**, sin importar lo que diga la
tabla de arriba.

**Elegido: `contact = 1.0`.** Es el candidato más chico que no rompe el
anidado en agujeros, y entre los que no lo rompen (1.0, 2.0, 4.0) es también
el mejor medido en `muestra.dxf` (62.9% contra 61.0% de `4.0`; `2.0` no se
midió sobre archivo real, pero la tendencia monótona de 1.0 a 4.0 no da
ninguna razón para esperar que le gane a 1.0). Se mantiene el valor
provisorio original — ahora por una razón medida, no por una elegida a
criterio.

## Resolución del raster

`contact = 1.0` (el elegido arriba), esfuerzo `rapido`.

### `muestra.dxf`, `--copias 8` (96 piezas, 2 placas en los cuatro casos salvo donde se indica)

| mm/px | aprov. 1ª placa | segundos | nota |
|---|---|---|---|
| 0.5 | (no medido a esta densidad) | 160.9 | medido solo el tiempo, a `--copias 2` (1 placa); ver más abajo |
| 1.0 (default anterior) | 62.93% | 175.6 | |
| 2.0 | 62.93% (idéntico) | 36.5 | 4.8× más rápido |
| 3.0 | 60.02% | 15.0 | 11.7× más rápido, pero pierde 2.9 puntos |

Para 0.5 mm/px la grilla tiene 4× más celdas por lado que a 1.0 (16× más
celdas en total), y sobre las 96 piezas de `muestra.dxf --copias 8` hubiera
sido impracticable dentro del presupuesto de esta sesión. Se midió el costo
en tiempo por separado, a `--copias 2` (24 piezas, cabe todo en 1 placa, no
sensible a la calidad del acomodo pero sí válido para el costo): 160.9 s
contra 33.0 s a 1.0 mm/px en la misma configuración — **4.9× más lento**,
consistente con la grilla más fina.

### `banqueta.ai`, `--copias 5` (200 piezas, 3 placas en ambos casos)

| mm/px | aprov. 1ª placa | segundos |
|---|---|---|
| 1.0 (default anterior) | 60.25% | 312.5 |
| 2.0 | 59.49% | 68.7 (4.5× más rápido) |

**Elegido: `resolucion = 2.0` mm/px** (antes 1.0). Pasar de 1.0 a 2.0 no
costó nada en `muestra.dxf` (idéntico al 16ª cifra) y costó 0.76 puntos en
el archivo real, a cambio de un 4.5-4.8× menos tiempo en los dos. Pasar a
3.0 pierde mucho más (2.9 puntos en `muestra.dxf`) por una ganancia de
velocidad que no hace falta. Ir más fino que 1.0 (0.5) sale 4.9× más caro en
tiempo por una ganancia de densidad que, según lo ya medido en la Task 15
(rasterizar conservador infla el área en +2% para una pieza de 300 mm y +9%
para una de 100×50 mm), es marginal en comparación. El verificador exacto
(`geometry/verify.py`) dio **cero violaciones** en todas las resoluciones
medidas: la resolución más gruesa cuesta densidad, nunca corrección, porque
la separación se valida sobre los polígonos exactos, no sobre la grilla.

Este cambio de default también deja el presupuesto de `EFFORT_RESTARTS`
(calibrado a 1.0 mm/px, ver `packer.py`) como una cota más floja de lo
necesario en vez de una ajustada: a 2.0 mm/px, cada nivel corre más rápido
que lo que se midió ahí, nunca más lento, así que el objetivo de 5 minutos
para `normal` sigue cumplido con más margen todavía.

## Niveles de esfuerzo

`EFFORT_RESTARTS` **no se tocó** — ya está calibrado con mediciones reales en
la Task 19 (ver `packer.py` y `.superpowers/sdd/task-19-report.md`), contra
un objetivo de ≤ 5 minutos para `normal`. Esta tabla es una confirmación
liviana, no una recalibración: se corrió sobre `muestra.dxf` a `--copias 2`
(no 8) para que `lento` no se comiera el presupuesto de esta sesión — a esa
cantidad de copias todo entra en una placa, así que el aprovechamiento no
distingue nada entre niveles (es exactamente el caso descrito en la nota de
método); lo que sí importa acá es el tiempo y que más esfuerzo nunca use más
placas.

| nivel | reintentos | aprov. 1ª placa | segundos | placas |
|---|---|---|---|---|
| rapido | 1 | 27.12% | 34.2 | 1 |
| normal | 3 | 27.12% (igual) | 66.9 | 1 |
| lento | 12 | 27.12% (igual) | 220.1 | 1 |

**Conclusión sobre la estimación original.** La spec §5.6 estimaba ~15-30 s
por pasada y `normal` en 3-5 min. La Task 19 (con el archivo real, no esta
tabla liviana) midió `normal = 3` en 182-236 s según la cantidad de copias —
dentro de la estimación, con margen. Lo medido acá (34.2 s / 66.9 s / 220.1 s
a `--copias 2`) es consistente con esa relación de tiempos (`normal` ≈ 2×
`rapido`, `lento` ≈ 6.4× `rapido`, algo por debajo del 12× nominal de
reintentos porque `lento` reusa el prefijo de reintentos de `normal` en vez
de volver a perturbar desde cero, ver el comentario de `pack()`). No cambia
la conclusión de la Task 19: `normal` es el punto donde el tiempo extra deja
de ser gratis, y `lento` solo se justifica cuando el layout está cerca de un
salto de placa.

## Comparación contra la línea de base

Mismos `--copias` que el barrido principal de cada archivo (8 para
`muestra.dxf`, 5 para el real), `contact = 1.0`, `resolucion = 1.0 mm/px`
(el valor vigente al momento de esta comparación), esfuerzo `rapido`.

| archivo | motor | placas | aprov. 1ª placa | aprov. total |
|---|---|---|---|---|
| `muestra.dxf` | shelf (bounding box) | 3 | 56.14% | 36.15% |
| `muestra.dxf` | raster | 2 | 62.93% | 54.23% |
| `banqueta.ai` | shelf (bounding box) | 3 | 54.87% | 42.24% |
| `banqueta.ai` | raster | 3 | 60.25% | 42.24% |

**Ganancia del motor raster:**

- `muestra.dxf`: +6.79 puntos en la primera placa, y además **una placa
  menos** (2 contra 3) — por eso el aprovechamiento *total* también sube
  18.08 puntos ahí (54.23% contra 36.15%), aunque esa métrica en general no
  sirva para comparar configuraciones a igualdad de placas.
- `banqueta.ai`: +5.38 puntos en la primera placa. Acá ambos
  motores necesitaron 3 placas, así que el aprovechamiento total queda
  idéntico (42.24%) por construcción — es exactamente el caso que
  `first_sheet_utilization` existe para no perder de vista.

## Resumen de valores fijados

| Parámetro | Provisorio | Medido | Cambiado |
|---|---|---|---|
| `Weights.contact` | 1.0 | 1.0 | No — confirmado con datos, no era una adivinanza |
| `NestConfig.resolution` / `--resolucion` | 1.0 mm/px | 2.0 mm/px | Sí |
| `EFFORT_RESTARTS` | — | — | No — fuera de alcance, ya calibrado en la Task 19 |
