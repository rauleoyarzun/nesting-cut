# Calibración

Dos corridas, con dos motores distintos:

- **2026-09-18 (Task 24), motor conservador.** La grilla del raster decidía
  las colisiones sola. Fijó `resolucion = 2.0 mm/px` y confirmó
  `contact = 1.0`. Queda más abajo, en «Anexo».
- **2026-09-21 (Tarea 6 del plan de densidad y colisión exacta), motor
  híbrido.** La grilla propone candidatos con halo optimista y
  `ArbitroExacto` (`src/nesting/engine/exact.py`) decide sobre los polígonos
  exactos. Es la corrida vigente y es la que cuenta este documento.

---

# Recalibración 2026-09-21 — motor híbrido

## Qué cambió debajo de la calibración

1. **El criterio.** `layout_cost` devolvía `(placas, alto de la última
   placa)`. Ahora devuelve `CostoLayout(placas, material_ultima,
   alto_ultima)`: primero placas, después cuánto material queda arriba en la
   última, y el alto sólo como desempate. El desempate viejo era
   activamente dañino, y esta corrida lo muestra con números (ver «Niveles
   de esfuerzo»).
2. **La separación.** Dejó de fijarla la grilla. Pedir 10 mm daba 16 mm
   reales a 2 mm/px; ahora da 10.00 mm a cualquier resolución.
3. **La pasada de recuperación** (Tarea 5) mueve a placas anteriores lo que
   quedó varado en la última.

Las dos primeras invalidan la calibración anterior: se calibró un peso
contra una métrica que el motor ya no persigue, y una resolución contra un
compromiso densidad/tiempo que ya no existe.

## Método

Cada celda es una corrida de `pack()` sobre un archivo, variando un solo
parámetro contra una configuración base, con `seed=0` y verificando el
resultado con `geometry/verify.py`. **Cero violaciones en todas las celdas
de las tablas de barrido de este documento** (la excepción son las corridas
de sensibilidad a la semilla, que comparan layouts y no llaman al
verificador).

Las corridas se hicieron con un script puntual sobre
`bench.run_bench.run_one` (mismo motor y mismos parámetros que barre
`bench/calibrate.py`), porque `bench/calibrate.py` aplica las mismas
`--copias` a todos los archivos y acá hizo falta una cantidad distinta por
archivo. El comando equivalente end to end es:

```bash
.venv/bin/python bench/calibrate.py --material mdf18 --copias 5
```

### Por qué hacen falta tantas copias

Una configuración sólo se distingue de otra si el trabajo **desborda la
primera placa**: con todo en una sola placa, tanto el aprovechamiento como
el material de la última son cocientes fijos que no dependen del acomodo.
Por eso `muestra.dxf` se corre a `--copias 8` (96 piezas) o `6` (72), y
`banqueta final raulo.ai` a `--copias 5` (200) o `4` (160).
`NESTING 2.ai` desborda con una sola copia.

### Archivos

| Archivo | Piezas (1 copia) | Origen |
|---|---|---|
| `NESTING 2.ai` | 36 | El trabajo real de referencia del plan (mdf15, sep 10, borde 10) |
| `bench/files/muestra.dxf` | 12 | Sintético, de `bench/make_sample.py`: curvas y concavidades para estresar el término de contacto |
| `bench/files/banqueta final raulo.ai` | 40 | Export real desde CorelDRAW (AI3) |
| `bench/files/banqueta raulo.3dm` | 0 | Modelo 3D del ensamblaje, no un layout de corte. No entra en la calibración |

### Qué mide el banco ahora

`bench/run_bench.py` y `bench/calibrate.py` reportaban aprovechamiento de la
primera placa y ordenaban por eso. **Se cambió en esta tarea**: `BenchResult`
suma `material_ultima_m2` y `tira_libre_mm`, y `calibrate._mejor` ordena por
`(placas, material en la última, segundos)`, el mismo orden que
`layout_cost`. Ordenar por una cifra que el motor no optimiza recomienda
valores que el motor después no elige — y eso pasó de verdad: en el barrido
de contacto sobre `banqueta final raulo.ai`, 0.5 y 0.8 empataron en
aprovechamiento de primera placa (61.00% las dos) y dejaron 0.781 m² y
0.859 m² en la última. El aprovechamiento de la primera placa se sigue
reportando: es la única columna con diferencias continuas cuando dos
configuraciones empatan en placas.

## Peso de contacto — **cambiado: 1.0 → 4.0**

`bottom_left` fijo en 1.0, resolución 2.0 mm/px.

### El piso funcional, primero

`tests/engine/raster/test_raster_oracle.py::test_a_small_part_is_nested_inside_a_big_hole`
verifica la ganancia de la spec §5.2: una pieza chica cae dentro del agujero
de una grande en vez de plancharse aparte. Bisección con el motor híbrido:

| contacto | ¿la pieza chica cae en el agujero? |
|---|---|
| 0.0, 0.25, 0.5, 0.6 | No |
| 0.7, 0.8, 0.9, 0.95, 1.0, 2.0, 4.0 | Sí |

El piso bajó un escalón (antes el corte estaba entre 0.7 y 0.8) pero sigue
ahí. **Todo candidato por debajo de 0.7 queda descartado**, y eso incluye
`contact = 0.0`, que es entre 1.6x y 4.8x más rápido y gana en dos de los
tres archivos.

### `NESTING 2.ai` — mdf15, sep 10, borde 10, 36 piezas

Esfuerzo `rapido`:

| contacto | placas | reparto | material última | tira libre | aprov. 1ª | seg |
|---|---|---|---|---|---|---|
| 0.0 | 2 | 34 / 2 | 0.0716 m² | 2365 mm | 53.61% | 15.1 |
| 0.5 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 25.9 |
| 0.8 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 26.2 |
| 1.0 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 37.5 |
| 2.0 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 24.8 |
| **4.0** | 2 | **34 / 2** | **0.0716 m²** | 2365 mm | 53.61% | 25.4 |
| 8.0 | 2 | 31 / 5 | 0.1789 m² | 2365 mm | 51.35% | 28.2 |
| 16.0 | 2 | 33 / 3 | 0.1172 m² | 2220 mm | 52.65% | 27.9 |

Esfuerzo `normal` (el default):

| contacto | reparto | material última | seg |
|---|---|---|---|
| 0.7 | 33 / 3 | 0.1106 m² | 48.9 |
| 0.8 | 33 / 3 | 0.1106 m² | 48.4 |
| 1.0 | 33 / 3 | 0.1106 m² | 48.8 |
| 2.0 | 32 / 4 | 0.1432 m² | 46.6 |
| **4.0** | **34 / 2** | **0.0716 m²** | 48.8 |

Esfuerzo `lento`:

| contacto | reparto | material última | seg |
|---|---|---|---|
| 0.8 | 35 / 1 | 0.1061 m² | 144.3 |
| 1.0 | 35 / 1 | 0.1061 m² | 140.1 |
| **4.0** | 34 / 2 | **0.0716 m²** | 177.8 |

(La última fila es el caso que muestra para qué sirve el criterio nuevo:
`4.0` deja **dos** piezas arriba contra **una** de `1.0`, y aun así gana,
porque esas dos piezas suman menos material que la única que deja `1.0`.
Lo que acerca a tirar la placa es el área, no el conteo.)

### `muestra.dxf` — mdf18, sep 6, borde 10, esfuerzo `rapido`

`--copias 8` (96 piezas):

| contacto | placas | reparto | material última | tira libre | aprov. 1ª | seg |
|---|---|---|---|---|---|---|
| 0.0 | 2 | 52 / 44 | 2.0284 m² | 466 mm | 65.83% | 47.7 |
| 0.5 | 2 | 51 / 45 | 2.0745 m² | 466 mm | 64.86% | 68.5 |
| 0.8 | 2 | 50 / 46 | 2.1206 m² | 466 mm | 63.90% | 99.2 |
| 1.0 | 2 | 50 / 46 | 2.1206 m² | 466 mm | 63.90% | 69.1 |
| 2.0 | 2 | 49 / 47 | 2.1667 m² | 370 mm | 62.93% | 69.7 |
| 4.0 | 2 | 50 / 46 | 2.1206 m² | 466 mm | 63.90% | 69.9 |

`--copias 6` (72 piezas):

| contacto | placas | reparto | material última | seg |
|---|---|---|---|---|
| 0.8 | 2 | 54 / 18 | 0.8298 m² | 38.0 |
| 1.0 | 2 | 52 / 20 | 0.9220 m² | 38.7 |
| 2.0 | 2 | 52 / 20 | 0.9220 m² | 60.2 |
| 4.0 | 2 | 52 / 20 | 0.9220 m² | 60.4 |

### `banqueta final raulo.ai` — mdf18, sep 6, borde 10, esfuerzo `rapido`

`--copias 5` (200 piezas):

| contacto | placas | reparto | material última | tira libre | aprov. 1ª | seg |
|---|---|---|---|---|---|---|
| 0.0 | 3 | 138 / 40 / 22 | 0.8167 m² | 1679 mm | 60.25% | 93.8 |
| 0.5 | 3 | 139 / 40 / 21 | 0.7809 m² | 1683 mm | 61.00% | 240.5 |
| 0.8 | 3 | 139 / 38 / 23 | 0.8591 m² | 1653 mm | 61.00% | 279.9 |
| 1.0 | 3 | 141 / 38 / 21 | 0.7842 m² | 1683 mm | 62.50% | 450.6 |
| 2.0 | 3 | 136 / 40 / 24 | 0.9014 m² | 1553 mm | 60.08% | 395.0 |
| **4.0** | 3 | 136 / 44 / 20 | **0.7582 m²** | 1703 mm | 61.36% | 398.3 |

`--copias 4` (160 piezas):

| contacto | placas | reparto | material última | seg |
|---|---|---|---|---|
| **0.8** | 2 | 116 / 44 | **2.0724 m²** | 227.8 |
| 1.0 | 2 | 113 / 47 | 2.1164 m² | 230.7 |
| 4.0 | 2 | 115 / 45 | 2.1147 m² | 308.0 |

### Cara a cara 4.0 contra 1.0 — las siete celdas

| celda | 1.0 | 4.0 | |
|---|---|---|---|
| `NESTING 2.ai` rapido | 0.1432 m² | **0.0716 m²** | gana 4.0 |
| `NESTING 2.ai` normal | 0.1106 m² | **0.0716 m²** | gana 4.0 |
| `NESTING 2.ai` lento | 0.1061 m² | **0.0716 m²** | gana 4.0 |
| `muestra.dxf` x8 | 2.1206 m² | 2.1206 m² | empate |
| `muestra.dxf` x6 | 0.9220 m² | 0.9220 m² | empate |
| `banqueta...` x5 | 0.7842 m² | **0.7582 m²** | gana 4.0 |
| `banqueta...` x4 | 2.1164 m² | **2.1147 m²** | gana 4.0 (apenas) |

Cinco victorias, dos empates, **ninguna derrota**. Y el tiempo es un empate:
el costo de la correlación FFT de contacto se paga o no según
`contact != 0.0` (ver `raster/scoring.py::best_position`), no según el valor
del peso; las diferencias de segundos de las tablas son del layout que salió,
no del peso.

### Un caso sintético donde sí decidió placas

48 rectángulos variados, generados con el mismo patrón que el fixture de
`tests/engine/test_effort.py::test_different_seeds_can_give_different_results`
(mismo material 1000x1000, sep 8, borde 15, esfuerzo `normal`) — **no** es
el fixture tal como quedó commiteado, que tiene 52 piezas, elegidas por una
razón distinta (que la salida siga siendo sensible a la semilla con los dos
pesos; ver el docstring del propio test). No quedó establecido si esta
corrida de 48 piezas reproduce el mismo resultado sobre las 52 del fixture
final — no se remidió sobre 52 antes de cerrar la tarea:

| contacto | semilla 1 | semilla 2 | semilla 3 | semilla 4 |
|---|---|---|---|---|
| 1.0 | 2 placas | 2 placas | 2 placas | 2 placas |
| 4.0 | **1 placa** | **1 placa** | 2 placas | 2 placas |

Es sintético, no un archivo real, pero es la única celda medida donde este
peso cambió lo que le cuesta al usuario — con la salvedad de la cantidad de
piezas, arriba.

### Lo que NO dicen estas tablas

No dicen que «más contacto es mejor». La respuesta **no es monótona**: 2.0
fue el peor de los candidatos que pasan el piso en 3 de las 5 celdas donde
se lo midió; sobre `NESTING 2.ai`, 8.0 y 16.0 son peores que 4.0; y 0.8 le
gana a 4.0 en dos celdas (`muestra.dxf` x6 y `banqueta...` x4), empata en
una (`muestra.dxf` x8) y pierde en cuatro. La cantidad de placas sobre
archivos reales fue idéntica con todos los pesos en las siete celdas.

Es decir: este peso no decide placas sobre los archivos medidos, decide
cuánto material queda arriba en la última, y ahí la respuesta parece una
lotería con un ganador consistente antes que una pendiente.

**Elegido: `contact = 4.0`** (antes 1.0). Es el mejor medido contra el
criterio que el motor realmente minimiza, no perdió nunca contra el valor
anterior, conserva el anidado en agujeros y no cuesta tiempo. No se sube más
porque 8.0 ya empeora.

## Resolución del raster — **sin cambios: 2.0 mm/px**

Contacto 1.0 (el vigente al momento de medir), esfuerzo `rapido`.

**Qué compra hoy.** Ya no compra separación: la decide `ArbitroExacto` sobre
los polígonos exactos, así que pedir 10 mm entrega 10.00 mm a cualquier
resolución. Lo único que queda en manos de la resolución es la finura de la
retícula de candidatos.

### `NESTING 2.ai` — mdf15, sep 10, borde 10

| mm/px | placas | reparto | material última | tira libre | aprov. 1ª | seg |
|---|---|---|---|---|---|---|
| 3.0 | 2 | 29 / 7 | 0.2538 m² | 2292 mm | 49.78% | 9.6 |
| **2.0** | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 36.8 |
| 1.0 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 110.4 |
| 0.5 | 2 | 31 / 5 | 0.1789 m² | 2365 mm | 51.35% | 646.2 |

### `muestra.dxf` — mdf18, `--copias 8`, sep 6, borde 10

| mm/px | placas | reparto | material última | aprov. 1ª | seg |
|---|---|---|---|---|---|
| 3.0 | 2 | 50 / 46 | 2.1206 m² | 63.90% | 51.7 |
| **2.0** | 2 | 50 / 46 | 2.1206 m² | 63.90% | 70.2 |
| 1.0 | 2 | 53 / 43 | 1.9823 m² | 66.80% | 413.5 |

### `banqueta final raulo.ai` — mdf18, `--copias 4`, sep 6, borde 10

| mm/px | placas | reparto | material última | aprov. 1ª | seg |
|---|---|---|---|---|---|
| 3.0 | 2 | 113 / 47 | 2.1229 m² | 56.76% | 74.6 |
| **2.0** | 2 | 113 / 47 | 2.1164 m² | 56.90% | 230.7 |
| 1.0 | 2 | 116 / 44 | 2.0090 m² | 59.15% | 1077.2 |

### La hipótesis del plan, confirmada a medias

El plan decía: «con el motor híbrido, 1 mm/px da el MISMO layout que 2 mm/px
y tarda 5x más». **Sobre `NESTING 2.ai` es exacto** — mismas cifras, mismo
reparto 32/4, 3.0x el tiempo. **Sobre los dos archivos del banco es falso**:
1.0 mm/px compra un 5-7% menos de material en la última placa, al precio de
4.7-5.9x el tiempo. Lo que no compra en ningún lado es una placa menos.

Y afinar no es un dial monótono: 0.5 mm/px sobre `NESTING 2.ai` dio **peor**
que 2.0 (31/5 contra 32/4) y 17.6x más lento. Una retícula más fina propone
candidatos distintos, no mejores.

**Elegido: se queda en `2.0 mm/px`.** Es la rodilla medida: engrosar a 3.0
empata en los dos archivos del banco pero se desploma en el de referencia
(29/7 contra 32/4), que es el caso apretado para el que se usa el programa;
afinar a 1.0 paga 5x el tiempo por un 5% de material en la última placa que
no cambia ninguna placa. Quien tenga un trabajo pegado a un salto de placa y
tiempo de sobra puede bajar a 1.0 a mano con `--resolucion`.

## Niveles de esfuerzo — **sin cambios: `{rapido: 1, normal: 3, lento: 12}`**

Contacto 1.0, resolución 2.0 mm/px.

### `NESTING 2.ai` — mdf15, sep 10, borde 10

| nivel | reintentos | reparto | material última | alto última | seg |
|---|---|---|---|---|---|
| rapido | 1 | 32 / 4 | 0.1432 m² | 235 mm | 37.7 |
| normal | 3 | 33 / 3 | 0.1106 m² | 308 mm | 48.3 |
| lento | 12 | 35 / 1 | 0.1061 m² | 491 mm | 136.2 |

**Esta tabla es la prueba de que el desempate viejo hacía daño.** Los
reintentos mejoran de forma monótona — de 4 piezas varadas a 1 — pero el
**alto** de la última placa **crece** con cada mejora. Con el costo viejo
`(placas, alto)`, `normal` y `lento` encontraban esos layouts y después los
tiraban, porque 308 mm y 491 mm puntúan peor que 235 mm. Parte del «empate»
que documentaba `EFFORT_RESTARTS` («normal empata con rapido en 5 de 7
escenarios») era eso: el esfuerzo extra sí encontraba algo y el costo lo
descartaba.

### `muestra.dxf` — mdf18, `--copias 8`

| nivel | reparto | material última | seg |
|---|---|---|---|
| rapido | 50 / 46 | 2.1206 m² | 70.1 |
| normal | 50 / 46 | 2.1206 m² | 132.1 |
| lento | 50 / 46 | 2.1206 m² | 401.9 |

Idénticos. La regla vieja se sostiene: el esfuerzo extra rinde cerca de un
salto de placa — donde está el archivo de referencia, con 1 a 4 piezas
varadas en la segunda placa — y no rinde lejos de uno. Lo que cambió es que
ahora, cuando rinde, se nota.

**No se tocó la tabla.** Los tiempos de la Task 19 que la fijaron no
cambiaron de signo, y el presupuesto de 5 minutos para `normal` se cumple
con holgura en los trabajos del tamaño contra el que se calibró (48.3 s en
el archivo de referencia, 132.1 s en `muestra.dxf --copias 8`). Lo que hay
que decir sin adornos es que ese presupuesto **no es universal**: una sola
pasada sobre `banqueta final raulo.ai --copias 5` (200 piezas) tarda
450.6 s, así que `normal` ahí se va muy por encima de los 5 minutos. Subir
`normal` a 4 o más empeoraría eso sin una ganancia medida que lo pague.

## El trabajo de referencia, de punta a punta

`NESTING 2.ai`, mdf15, sep 10, borde 10, esfuerzo `rapido`, resolución
2.0 mm/px, **cero violaciones** del verificador exacto:

| contacto | placas | reparto | material última | tira libre | seg |
|---|---|---|---|---|---|
| 1.0 (antes) | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 37.5 |
| **4.0 (ahora)** | 2 | **34 / 2** | **0.0716 m²** | 2365 mm | 25.4 |

(Las dos filas salen de la misma corrida del barrido de contacto, para que
los segundos sean comparables entre sí.)

Y por la CLI, con los valores por omisión ya cambiados:

```
$ .venv/bin/nest "NESTING 2.ai" --material mdf15 --sep 10 --borde 10 \
      --esfuerzo rapido -o cortado.dxf
Placa 1/2   aprovechamiento  53.6%
Placa 2/2   aprovechamiento   1.5%   <- sobrante útil ~1830x2365 mm
----------------------------------
36 piezas - 2 placas - 27.6% total - 24.8s
  material en la última placa: 0.072 m²  ·  tira libre: 2365 mm
```

El techo del plan (3.010 m² de piezas infladas contra 4.670 m² de área útil:
una sola placa exigiría empaquetar al 64.4%) sigue lejos: la placa 1 llega
al 53.61%.

## Resumen de valores fijados

| Parámetro | Antes | Ahora | ¿Cambió? |
|---|---|---|---|
| `Weights.contact` | 1.0 | **4.0** | Sí — nunca perdió contra 1.0 en 7 celdas, gana 5 |
| `Weights.bottom_left` | 1.0 | 1.0 | No — no se barrió, es la referencia contra la que se mide el contacto |
| `NestConfig.resolution` / `NestParams.resolucion` / `--resolucion` | 2.0 mm/px | 2.0 mm/px | No — 1.0 compra 5-7% de material en la última al precio de 5x el tiempo, y 0.5 empeora |
| `EFFORT_RESTARTS` | 1 / 3 / 12 | 1 / 3 / 12 | No — los tiempos que la fijaron no cambiaron de signo |
| Métrica de `bench/calibrate.py` | aprov. 1ª placa | `(placas, material última, seg)` | Sí — el orden de `layout_cost` |

---

# Anexo — corrida 2026-09-18 (Task 24), motor conservador

Se conserva porque explica de dónde salió `resolucion = 2.0` y porque su
razonamiento sobre el piso del anidado en agujeros sigue vigente en forma
(el umbral se volvió a medir arriba y bajó de ~0.8 a ~0.7).

Medido sobre `bench/files/` con el motor en el que la grilla decidía las
colisiones sola, ordenando por aprovechamiento de la primera placa.

## Peso de contacto (entonces)

`muestra.dxf`, `--copias 8`, resolución 1.0 mm/px:

| contacto | aprov. 1ª placa | segundos |
|---|---|---|
| 0.0 | 63.90% | 109.7 |
| 1.0 | 62.93% | 175.6 |
| 4.0 | 60.99% | 179.8 |

`banqueta final raulo.ai`, `--copias 5`:

| contacto | aprov. 1ª placa | segundos |
|---|---|---|
| 0.0 | 60.25% | 206.1 |
| 1.0 | 60.25% (idéntico) | 312.5 |

Conclusión de entonces: el promedio favorecía `0.0`, pero el anidado en
agujeros lo descartaba, y entre los que pasaban el piso `1.0` era el mejor
en aprovechamiento de primera placa. Con el motor híbrido y el criterio
nuevo esa comparación se rehízo entera y dio 4.0.

## Resolución (entonces)

`muestra.dxf`, `--copias 8`:

| mm/px | aprov. 1ª placa | segundos |
|---|---|---|
| 0.5 | (sólo tiempo, a `--copias 2`) | 160.9 |
| 1.0 | 62.93% | 175.6 |
| 2.0 | 62.93% (idéntico) | 36.5 |
| 3.0 | 60.02% | 15.0 |

`banqueta final raulo.ai`, `--copias 5`:

| mm/px | aprov. 1ª placa | segundos |
|---|---|---|
| 1.0 | 60.25% | 312.5 |
| 2.0 | 59.49% | 68.7 |

Eso fijó `2.0 mm/px`, con el argumento de que rasterizar conservador infla
el área y una grilla fina compra densidad. Ese argumento ya no aplica —la
separación la decide el árbitro exacto— pero el valor sobrevivió a la
remedición.

## Comparación contra la línea de base (entonces)

Resolución 1.0 mm/px, contacto 1.0, esfuerzo `rapido`.

| archivo | motor | placas | aprov. 1ª placa | aprov. total |
|---|---|---|---|---|
| `muestra.dxf` (x8) | shelf (bounding box) | 3 | 56.14% | 36.15% |
| `muestra.dxf` (x8) | raster | 2 | 62.93% | 54.23% |
| `banqueta final raulo.ai` (x5) | shelf (bounding box) | 3 | 54.87% | 42.24% |
| `banqueta final raulo.ai` (x5) | raster | 3 | 60.25% | 42.24% |

## Fase 2 de pares y cartera — acelerar una sola combinación

Criterio fijado antes de medir: al menos 30% menos de tiempo total de
`rapido` sobre `bench/files` (mdf18, valores por omisión de la CLI, 1 mm/px),
con todos los layouts idénticos (`bench/medir_rapido.py --comparar`).

| variante | total | baja | layouts idénticos | se queda |
|---|---|---|---|---|
| antes | 226.6 s | — | — | — |
| A: transformada de la placa reusada | 217.2 s | 4.1% | no (`banqueta-alta.ai`) | no |
| B: orientaciones en 4 hilos | 78.8 s | 65.2% | sí | sí |
| B después de la revisión (hilos sólo en el proceso principal) | 74.0 s | 67.3% | sí | sí |

Por archivo (segundos; la de base es la segunda corrida, la primera dio
58.0 / 158.5 / 10.6 = 227.1 s con las mismas huellas):

| archivo | antes | A | B | B revisada |
|---|---|---|---|---|
| `banqueta final raulo.ai` | 59.3 | 48.3 | 19.5 | 18.8 |
| `banqueta-alta.ai` | 156.8 | 159.0 (layout distinto) | 55.3 | 51.3 |
| `muestra.dxf` | 10.5 | 9.9 | 4.0 | 3.9 |

A no llega ni de lejos, y encima cambia un layout: la transformada de la
placa a un tamaño de FFT común no redondea igual que `fftconvolve`, y en
`banqueta-alta.ai` esa diferencia de redondeo alcanza para cambiar una
elección. B sí: scipy suelta el GIL en las FFT, y las 16 consultas de una
pieza son independientes.

Con `normal` y los núcleos por omisión (5 en esta máquina, por memoria) el
tiempo quedó parecido al de `rapido` en los tres archivos —la cota corta la
búsqueda antes de las tandas—, así que B baja lo mismo ahí: 11.2 → 4.0 s,
61.3 → 19.2 s y 163.9 → 53.9 s, con las mismas huellas.

La revisión midió además el pico de memoria de un proceso con `rapido`: de
1234 a 1613 MB en `muestra.dxf` y de 1133 a 1985 MB en `banqueta final
raulo.ai`, pasando de 1 a 4 hilos (cada consulta en vuelo tiene sus propios
arreglos de FFT). `workers.MEMORY_PER_WORKER_BYTES` (2300 MB) está medido
con un hilo, y 5 procesos con 4 hilos cada uno son 20 hilos sobre 14
núcleos. Por eso los hilos quedaron SÓLO en el proceso principal —la base,
la recuperación y la compactación, que corren solas— y los procesos de la
cartera consultan con uno (`cartera._init_worker` los apaga), así que el
tope de procesos sigue valiendo. La estimación previa usa dos costos por
consulta: el de los hilos para la base y el tramo final, y el de un hilo
para las tandas en procesos (`corredor.estimar_segundos`). `FACTOR_LLENO`
se volvió a medir con la prueba en hilos (`bench/calibrate.py
--factor-lleno`, las dos configuraciones de su docstring). La primera vez
dio 0.825, con factores de 0.51 a 1.99 y el test de ×2 al borde (el real
llegó a 1.90–1.94 veces el estimado). El motivo: la prueba cobraba el
rasterizado de todas las orientaciones, que en la corrida se paga una vez
por máscara. Ahora la prueba prepara las máscaras antes de largar el reloj
y mide sólo consultas. Con eso el factor dio 3.455 (seis factores de 3.08 a
6.08, cinco de ellos entre 3.08 y 4.39), y dentro de
`tests/test_calibration.py` el real quedó en 1.05, 1.02 y 1.00 veces el
estimado en tres corridas.

Máquina: Apple M4 Pro, 14 núcleos, 24 GB, fecha 2026-09-23.
