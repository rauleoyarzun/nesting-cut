# Task 6 — Recalibrar los valores por omisión y contar la verdad

**Commit:** `3ff6cf5` — «Recalibrar con el motor híbrido y contar el objetivo nuevo»
**Suite:** 1028 pasan, **22 warnings** (no está limpia; detalle abajo).

---

## 0. Corrección previa al brief, y cómo se midió

El brief (Paso 1) manda correr
`bench/run_bench.py --resoluciones ... --esfuerzos ...`. **Esos flags no
existen** — `run_bench.py` sólo acepta `--material --copias --sep --borde
--unidades`, y su `main()` sólo barre `bench/files/*.dxf`. Confirmado leyendo
los dos scripts.

`bench/calibrate.py` sí barre contacto, resolución y esfuerzo, pero aplica
**las mismas `--copias` a todos los archivos**, y acá hizo falta una cantidad
distinta por archivo (ver §1). Así que:

- Las mediciones de este informe se tomaron con un script puntual sobre
  `bench.run_bench.run_one` / `pack()`, mismo motor y mismos parámetros que
  barre `calibrate.py`, variando un eje por vez.
- `bench/calibrate.py` **se corrió igual, end to end**, para verificar que la
  herramienta (con los cambios de esta tarea) funciona: §6.

`bench/files/` está en `.gitignore` y no existía en el worktree; se copiaron
los tres archivos desde el checkout principal.

### Comandos

```bash
# baseline y barridos (script puntual, en el scratchpad de la sesión)
.venv/bin/python scratchpad/barrer.py "/Users/raulo/Downloads/NESTING 2.ai" \
    --material mdf15 --sep 10 --borde 10 --esfuerzo rapido --resolucion 2.0 \
    --eje contacto --valores 0.0,0.5,0.8,1.0,2.0,4.0
.venv/bin/python scratchpad/barrer.py bench/files/muestra.dxf \
    --material mdf18 --copias 8 --sep 6 --borde 10 --esfuerzo rapido \
    --resolucion 2.0 --eje contacto --valores 0.0,0.5,0.8,1.0,2.0,4.0
.venv/bin/python scratchpad/barrer.py "bench/files/banqueta final raulo.ai" \
    --material mdf18 --copias 5 --sep 6 --borde 10 --esfuerzo rapido \
    --resolucion 2.0 --eje contacto --valores 0.0,0.5,0.8,1.0,2.0,4.0
#   ... y los mismos con --eje resolucion / --eje esfuerzo (ver tablas)

# bisección del piso de anidado en agujeros
.venv/bin/python scratchpad/agujero.py

# sensibilidad a la semilla del fixture de test_different_seeds
.venv/bin/python scratchpad/semillas.py

# la herramienta del repo, end to end
.venv/bin/python bench/calibrate.py --material mdf18 --copias 1

# suite
.venv/bin/python -m pytest
```

---

## 1. Por qué tantas copias

Una configuración sólo se distingue de otra si el trabajo **desborda la
primera placa**. Con todo en una placa, tanto `first_sheet_utilization` como
`material_ultima` son cocientes fijos que no dependen del acomodo. Por eso
`muestra.dxf` va a `--copias 8` (96 piezas) o `6` (72) y
`banqueta final raulo.ai` a `--copias 5` (200) o `4` (160). `NESTING 2.ai`
desborda con una copia.

Esto se ve en la corrida de `calibrate.py --copias 1` de §6: las 12 filas del
barrido dan **exactamente el mismo** material en la última placa.

---

## 2. Peso de contacto — **cambiado: 1.0 → 4.0**

### 2.1 El piso funcional, primero (bisección con el motor híbrido)

`tests/engine/raster/test_raster_oracle.py::test_a_small_part_is_nested_inside_a_big_hole`

| contacto | ¿la pieza chica cae en el agujero? |
|---|---|
| 0.0, 0.25, 0.5, 0.6 | **No** |
| 0.7, 0.8, 0.9, 0.95, 1.0, 2.0, 4.0 | Sí |

El corte bajó un escalón (antes estaba entre 0.7 y 0.8) pero **el piso sigue
existiendo**. `contact = 0.0` queda descartado por más que sea 1.6-4.8x más
rápido y gane el barrido en dos de los tres archivos. Esto **confirma la
trampa** que avisaba el brief.

### 2.2 `NESTING 2.ai` — mdf15, sep 10, borde 10, 36 piezas, resolución 2.0

Esfuerzo `rapido`:

| contacto | placas | reparto | mat. última | tira libre | aprov. 1ª | seg | viol |
|---|---|---|---|---|---|---|---|
| 0.0 | 2 | 34 / 2 | 0.0716 m² | 2365 mm | 53.61% | 15.1 | 0 |
| 0.5 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 25.9 | 0 |
| 0.8 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 26.2 | 0 |
| 1.0 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 37.5 | 0 |
| 2.0 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 24.8 | 0 |
| **4.0** | 2 | **34 / 2** | **0.0716 m²** | 2365 mm | 53.61% | 25.4 | 0 |
| 8.0 | 2 | 31 / 5 | 0.1789 m² | 2365 mm | 51.35% | 28.2 | 0 |
| 16.0 | 2 | 33 / 3 | 0.1172 m² | 2220 mm | 52.65% | 27.9 | 0 |

Esfuerzo `normal`:

| contacto | reparto | mat. última | seg | viol |
|---|---|---|---|---|
| 0.7 | 33 / 3 | 0.1106 m² | 48.9 | 0 |
| 0.8 | 33 / 3 | 0.1106 m² | 48.4 | 0 |
| 1.0 | 33 / 3 | 0.1106 m² | 48.8 | 0 |
| 2.0 | 32 / 4 | 0.1432 m² | 46.6 | 0 |
| **4.0** | **34 / 2** | **0.0716 m²** | 48.8 | 0 |

Esfuerzo `lento`:

| contacto | reparto | mat. última | tira libre | seg | viol |
|---|---|---|---|---|---|
| 0.8 | 35 / 1 | 0.1061 m² | 2108.9 mm | 144.3 | 0 |
| 1.0 | 35 / 1 | 0.1061 m² | 2108.9 mm | 140.1 | 0 |
| **4.0** | 34 / 2 | **0.0716 m²** | 2365 mm | 177.8 | 0 |

Esta última tabla es, por sí sola, una demostración del criterio nuevo: 4.0
deja **dos** piezas arriba contra **una** de 1.0 y aun así gana, porque esas
dos suman menos área. Lo que acerca a tirar la placa es el área, no el conteo.

### 2.3 `muestra.dxf` — mdf18, sep 6, borde 10, `rapido`, resolución 2.0

`--copias 8` (96 piezas):

| contacto | placas | reparto | mat. última | tira libre | aprov. 1ª | seg | viol |
|---|---|---|---|---|---|---|---|
| 0.0 | 2 | 52 / 44 | 2.0284 m² | 466 mm | 65.83% | 47.7 | 0 |
| 0.5 | 2 | 51 / 45 | 2.0745 m² | 466 mm | 64.86% | 68.5 | 0 |
| 0.8 | 2 | 50 / 46 | 2.1206 m² | 466 mm | 63.90% | 99.2 | 0 |
| 1.0 | 2 | 50 / 46 | 2.1206 m² | 466 mm | 63.90% | 69.1 | 0 |
| 2.0 | 2 | 49 / 47 | 2.1667 m² | 370 mm | 62.93% | 69.7 | 0 |
| 4.0 | 2 | 50 / 46 | 2.1206 m² | 466 mm | 63.90% | 69.9 | 0 |

`--copias 6` (72 piezas):

| contacto | placas | reparto | mat. última | seg | viol |
|---|---|---|---|---|---|
| **0.8** | 2 | 54 / 18 | **0.8298 m²** | 38.0 | 0 |
| 1.0 | 2 | 52 / 20 | 0.9220 m² | 38.7 | 0 |
| 2.0 | 2 | 52 / 20 | 0.9220 m² | 60.2 | 0 |
| 4.0 | 2 | 52 / 20 | 0.9220 m² | 60.4 | 0 |

### 2.4 `banqueta final raulo.ai` — mdf18, sep 6, borde 10, `rapido`, resolución 2.0

`--copias 5` (200 piezas):

| contacto | placas | reparto | mat. última | tira libre | aprov. 1ª | seg | viol |
|---|---|---|---|---|---|---|---|
| 0.0 | 3 | 138 / 40 / 22 | 0.8167 m² | 1679 mm | 60.25% | 93.8 | 0 |
| 0.5 | 3 | 139 / 40 / 21 | 0.7809 m² | 1683 mm | 61.00% | 240.5 | 0 |
| 0.8 | 3 | 139 / 38 / 23 | 0.8591 m² | 1653 mm | 61.00% | 279.9 | 0 |
| 1.0 | 3 | 141 / 38 / 21 | 0.7842 m² | 1683 mm | 62.50% | 450.6 | 0 |
| 2.0 | 3 | 136 / 40 / 24 | 0.9014 m² | 1553 mm | 60.08% | 395.0 | 0 |
| **4.0** | 3 | 136 / 44 / 20 | **0.7582 m²** | 1703 mm | 61.36% | 398.3 | 0 |

`--copias 4` (160 piezas):

| contacto | placas | reparto | mat. última | seg | viol |
|---|---|---|---|---|---|
| **0.8** | 2 | 116 / 44 | **2.0724 m²** | 227.8 | 0 |
| 1.0 | 2 | 113 / 47 | 2.1164 m² | 230.7 | 0 |
| 4.0 | 2 | 115 / 45 | 2.1147 m² | 308.0 | 0 |

### 2.5 Cara a cara 4.0 contra 1.0

| celda | 1.0 | 4.0 | |
|---|---|---|---|
| `NESTING 2.ai` rapido | 0.1432 | **0.0716** | gana 4.0 |
| `NESTING 2.ai` normal | 0.1106 | **0.0716** | gana 4.0 |
| `NESTING 2.ai` lento | 0.1061 | **0.0716** | gana 4.0 |
| `muestra.dxf` x8 | 2.1206 | 2.1206 | empate |
| `muestra.dxf` x6 | 0.9220 | 0.9220 | empate |
| `banqueta...` x5 | 0.7842 | **0.7582** | gana 4.0 |
| `banqueta...` x4 | 2.1164 | **2.1147** | gana 4.0 (apenas) |

**Cinco victorias, dos empates, ninguna derrota.** El tiempo es un empate: el
costo de la correlación FFT de contacto depende de `contact != 0.0`, no del
valor (`raster/scoring.py::best_position`), así que las diferencias de
segundos son del layout, no del peso (25.4 vs 37.5 a favor de 4.0 en un lado,
60.4 vs 38.7 en contra en otro).

### 2.6 La única celda donde este peso decidió placas

Fixture de `tests/engine/test_effort.py::test_different_seeds_can_give_different_results`
(rectángulos variados, material 1000x1000, sep 8, borde 15, `normal`), 48 piezas:

| contacto | semilla 1 | semilla 2 | semilla 3 | semilla 4 |
|---|---|---|---|---|
| 1.0 | 2 placas | 2 placas | 2 placas | 2 placas |
| 4.0 | **1 placa** | **1 placa** | 2 placas | 2 placas |

Sintético, pero es la única celda medida donde el peso cambió lo que le
cuesta al usuario.

### 2.7 Confirmación y refutación de la hipótesis del brief

- **Confirmado:** `contact = 1.0` cuesta piezas sobre `NESTING 2.ai` (32/4
  contra 34/2) y sobre `muestra.dxf` x8 (50/46 contra 52/44 de `contact=0`).
- **Refutado como enunciado general:** sobre `banqueta final raulo.ai` x5,
  `contact = 1.0` es el **segundo mejor** (0.7842 m²) y `contact = 0.0` es el
  **cuarto de seis** (0.8167 m²). El peso no «cuesta piezas» siempre.
- **Refutado que la ganancia de apagarlo sea inalcanzable de otro modo:** el
  34/2 que da `contact = 0` sobre el archivo de referencia también lo da
  `contact = 4.0`, **sin** perder el anidado en agujeros.

### 2.8 La ambigüedad que queda, dicha en voz alta

La respuesta **no es monótona y parece una lotería**:

- 2.0 fue el peor de los candidatos que pasan el piso en 3 de las 5 celdas
  donde se lo midió, estando entre 1.0 y 4.0.
- Sobre `NESTING 2.ai`, 8.0 (0.1789) y 16.0 (0.1172) son **peores** que 4.0
  (0.0716). No hay pendiente que seguir.
- 0.8 le gana a 4.0 en dos celdas, empata en una y pierde en cuatro. No es un
  candidato descartable, sólo peor que 4.0 en el balance.
- La cantidad de **placas** sobre archivos reales fue idéntica con todos los
  pesos en las siete celdas.

Elegí 4.0 igual porque es lo que dice la evidencia disponible (nunca perdió
contra el valor vigente, en 7 celdas, sobre el criterio que el motor de
verdad minimiza, sin costo en tiempo y sin romper la capacidad). Pero el
mecanismo es caótico: **si alguien repite esto sobre otros archivos y le da
0.8, no me sorprendería.** Lo que sí es sólido es la dirección descartada:
bajar el contacto por debajo de 0.7 rompe una capacidad real.

---

## 3. Resolución — **sin cambios: 2.0 mm/px**

Contacto 1.0 (el vigente al medir), `rapido`, cero violaciones en las 10 celdas.

### `NESTING 2.ai` (mdf15, sep 10, borde 10)

| mm/px | placas | reparto | mat. última | tira libre | aprov. 1ª | seg |
|---|---|---|---|---|---|---|
| 3.0 | 2 | 29 / 7 | 0.2538 m² | 2292 mm | 49.78% | 9.6 |
| **2.0** | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 36.8 |
| 1.0 | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 52.10% | 110.4 |
| 0.5 | 2 | 31 / 5 | 0.1789 m² | 2365 mm | 51.35% | 646.2 |

### `muestra.dxf` x8 (mdf18, sep 6, borde 10)

| mm/px | placas | reparto | mat. última | aprov. 1ª | seg |
|---|---|---|---|---|---|
| 3.0 | 2 | 50 / 46 | 2.1206 m² | 63.90% | 51.7 |
| **2.0** | 2 | 50 / 46 | 2.1206 m² | 63.90% | 70.2 |
| 1.0 | 2 | 53 / 43 | 1.9823 m² | 66.80% | 413.5 |

### `banqueta final raulo.ai` x4 (mdf18, sep 6, borde 10)

| mm/px | placas | reparto | mat. última | aprov. 1ª | seg |
|---|---|---|---|---|---|
| 3.0 | 2 | 113 / 47 | 2.1229 m² | 56.76% | 74.6 |
| **2.0** | 2 | 113 / 47 | 2.1164 m² | 56.90% | 230.7 |
| 1.0 | 2 | 116 / 44 | 2.0090 m² | 59.15% | 1077.2 |

(0.5 mm/px no se midió sobre los dos archivos del banco: a 1.0 ya tardaban
413 s y 1077 s, y 0.5 sobre el archivo de referencia salió 5.9x más caro que
1.0. El presupuesto de una sesión no lo aguanta y el resultado sobre el
archivo de referencia ya muestra que afinar no ayuda.)

### Veredicto

**La hipótesis del plan se confirma sobre el archivo de referencia y se
refuta sobre los del banco.**

- `NESTING 2.ai`: 1.0 mm/px da **las mismas cifras** que 2.0 (mismo reparto
  32/4, mismo material, misma tira) por 3.0x el tiempo. Exactamente lo que el
  plan predecía.
- `muestra.dxf` x8 y `banqueta` x4: 1.0 mm/px sí compra densidad — 6.5% y 5.1%
  menos material en la última placa — al precio de 5.9x y 4.7x el tiempo.
- En **ningún** archivo cambió la cantidad de placas.
- Afinar no es monótono: 0.5 mm/px sobre el archivo de referencia dio **peor**
  que 2.0 (31/5 contra 32/4) y 17.6x más lento. La retícula más fina propone
  candidatos **distintos**, no mejores.
- Engrosar a 3.0 empata en los dos del banco pero se desploma en el de
  referencia (29/7 contra 32/4).

Por eso 2.0 se queda: es la rodilla medida. El docstring ya no justifica el
valor por un compromiso densidad-vs-tiempo debido a la inflación del raster
(que dejó de existir: la separación la decide `ArbitroExacto` y da 10.00 mm a
cualquier resolución), sino por lo único que la resolución gobierna hoy, la
**finura de la búsqueda**.

---

## 4. Niveles de esfuerzo — **tabla sin cambios, nota reescrita**

Contacto 1.0, resolución 2.0.

### `NESTING 2.ai` (mdf15, sep 10, borde 10)

| nivel | reintentos | reparto | mat. última | **alto última** | seg |
|---|---|---|---|---|---|
| rapido | 1 | 32 / 4 | 0.1432 m² | 235 mm | 37.7 |
| normal | 3 | 33 / 3 | 0.1106 m² | 308 mm | 48.3 |
| lento | 12 | 35 / 1 | 0.1061 m² | 491 mm | 136.2 |

**Este es el hallazgo más nítido de la tarea.** Los reintentos mejoran de
forma monótona — de 4 piezas varadas a 1 — pero el **alto** de la última placa
**crece** con cada mejora. Con el costo viejo `(placas, alto)`, 308 mm y
491 mm puntúan **peor** que 235 mm: `normal` y `lento` encontraban esos
layouts y después los descartaban. Buena parte del «normal empata con rapido
en 5 de 7 escenarios» que documentaba `EFFORT_RESTARTS` era eso.

### `muestra.dxf` x8

| nivel | reparto | mat. última | seg |
|---|---|---|---|
| rapido | 50 / 46 | 2.1206 m² | 70.1 |
| normal | 50 / 46 | 2.1206 m² | 132.1 |
| lento | 50 / 46 | 2.1206 m² | 401.9 |

Idénticos. La regla vieja se sostiene (el esfuerzo rinde cerca de un salto de
placa y no lejos); lo que cambió es que **cuando rinde, ahora se nota**.

**No cambié la tabla** porque nada de lo que la fijó cambió de signo, y porque
subir `normal` empeoraría el presupuesto de tiempo sin una ganancia medida que
lo pague. Sí dejé dicho en el docstring que el objetivo de 5 minutos **no es
universal**: una sola pasada sobre `banqueta final raulo.ai --copias 5`
(200 piezas) tarda 450.6 s, así que `normal` ahí se va muy por encima.

---

## 5. Qué cambié, default por default

| Cosa | Antes | Ahora | Por qué |
|---|---|---|---|
| `Weights.contact` | 1.0 | **4.0** | §2.5: nunca perdió contra 1.0 en 7 celdas, 5 victorias. Piso de anidado respetado (§2.1). Sin costo en tiempo. |
| `NestConfig.resolution` | 2.0 | 2.0 | §3: 1.0 compra 5-7% de material en la última al precio de ~5x el tiempo y no cambia placas; 0.5 empeora; 3.0 se desploma en el archivo de referencia. |
| `NestParams.resolucion` | 2.0 | 2.0 | Idem — no hizo falta tocar `params.py`. |
| `EFFORT_RESTARTS` | 1/3/12 | 1/3/12 | §4. |
| `Weights.bottom_left` | 1.0 | 1.0 | No se barrió: es la referencia contra la que se mide el contacto. |
| Métrica de `bench/calibrate.py` | aprov. 1ª placa | `(placas, material última, seg)` | §6. |

### Prosa reescrita

- `NestConfig.resolution` (`src/nesting/engine/oracle.py`): el docstring
  justificaba 2.0 por un compromiso densidad-vs-tiempo nacido de la inflación
  del raster. Eso ya no existe. Ahora dice qué gobierna la resolución hoy
  (finura de la búsqueda, no separación) y trae la tabla nueva de 10 celdas.
- `Weights.contact` (mismo archivo): tabla nueva, piso rebisectado, y un
  párrafo explícito diciendo que **no es una tendencia**.
- `Weights` (docstring de clase): decía «Calibrated in Task 24».
- `EFFORT_RESTARTS` (`src/nesting/engine/packer.py`): §4.
- `docs/superpowers/calibracion.md`: reescrito. La corrida vieja queda como
  **Anexo** (explica de dónde salió 2.0 mm/px y su razonamiento sigue siendo
  útil como forma), y arriba va la recalibración con el motor híbrido.
- `README.md` y `README.es.md`: la promesa («las menos placas y la tira más
  grande posible») pasa a ser «menos placas → menos material en la última →
  con la misma cantidad, lo más compactada posible», en la cabecera y en la
  tabla «Busca»/«Aims for». El párrafo de resultados pasa de tres cifras a
  cuatro y explica que las dos últimas **compiten**. Cada uno en su idioma.
  De paso, el badge de tests y la línea de desarrollo pasaron de 856 a 1028 y
  de ~4 min a ~7 min, que era otra afirmación falsa.
- `bench/calibrate.py`: docstring de módulo, de los tres barridos y de
  `_mejor`.
- `bench/run_bench.py`: docstrings de los dos campos nuevos de `BenchResult`.

---

## 6. El banco medía una cosa y el motor optimizaba otra

`calibrate.py` ordenaba por `first_sheet_utilization`. **Eso ya no es lo que
el motor persigue**, y no es un detalle teórico: en el barrido de contacto
sobre `banqueta final raulo.ai` x5, los contactos 0.5 y 0.8 dan
**exactamente el mismo** aprovechamiento de primera placa (61.00%) y dejan
0.7809 m² y 0.8591 m² en la última. La métrica vieja no puede distinguirlos;
el motor sí.

Lo extendí, como el brief autorizaba:

- `BenchResult` suma `material_ultima_m2` y `tira_libre_mm`, sacados de
  `layout_cost`.
- Los tres barridos devuelven ahora una fila uniforme
  `(eje, aprov. 1ª, seg, placas, material última, tira libre)`.
- `_best_contact` → `_mejor`, que ordena por `(placas, material última,
  segundos)`: el mismo orden que `layout_cost`. La tira libre **no** entra
  como criterio: es la cifra que se le muestra al usuario, pero es justo la
  que la Tarea 1 sacó del segundo lugar.
- El aprovechamiento de la primera placa **se sigue reportando**: es la única
  columna con diferencias continuas cuando dos configuraciones empatan en
  placas.

Corrida real de la herramienta modificada (`--copias 1`, o sea sin desborde;
sirve como verificación de que funciona y como ilustración de §1 — las 12
filas dan el mismo material en la última placa):

```
Calibrando sobre 2 archivo(s) (--copias 1): muestra.dxf, banqueta final raulo.ai

PESO DE CONTACTO  (bottom_left fijo en 1.0, esfuerzo rapido, resolucion 2.0 mm/px)
  contacto  aprov. 1ra placa   seg. medio   placas  mat. ult. m2   tira mm
--------------------------------------------------------------------------
       0.0             19.5%          4.5        2        0.9255      1586
       0.5             19.5%          9.0        2        0.9255      1593
       1.0             19.5%         11.2        2        0.9255      1594
       2.0             19.5%         14.8        2        0.9255      1573
       4.0             19.5%         14.9        2        0.9255      1615

-> mejor contacto medido: 0.0

RESOLUCION DEL RASTER  (contact = mejor medido, esfuerzo rapido)
     mm/px  aprov. 1ra placa   seg. medio   placas  mat. ult. m2   tira mm
--------------------------------------------------------------------------
       0.5             19.5%        103.3        2        0.9255      1583
       1.0             19.5%         21.0        2        0.9255      1579
       2.0             19.5%          4.7        2        0.9255      1586
       3.0             19.5%          2.0        2        0.9255      1579

NIVELES DE ESFUERZO  (contact = mejor medido, resolucion 2.0 mm/px)
     nivel  aprov. 1ra placa   seg. medio   placas  mat. ult. m2   tira mm
--------------------------------------------------------------------------
    rapido             19.5%          4.8        2        0.9255      1586
    normal             19.5%          9.3        2        0.9255      1586
     lento             19.5%         29.5        2        0.9255      1635
```

---

## 7. El trabajo de referencia

`NESTING 2.ai`, mdf15, sep 10, borde 10, `rapido`, 2.0 mm/px:

| contacto | placas | reparto | mat. última | tira libre | seg | viol |
|---|---|---|---|---|---|---|
| 1.0 (antes) | 2 | 32 / 4 | 0.1432 m² | 2365 mm | 37.5 | 0 |
| **4.0 (ahora)** | 2 | **34 / 2** | **0.0716 m²** | 2365 mm | 25.4 | 0 |

Por la CLI, con los defaults ya cambiados:

```
$ .venv/bin/nest "NESTING 2.ai" --material mdf15 --sep 10 --borde 10 \
      --esfuerzo rapido -o cortado.dxf
Placa 1/2   aprovechamiento  53.6%
Placa 2/2   aprovechamiento   1.5%   <- sobrante útil ~1830x2365 mm
----------------------------------
36 piezas - 2 placas - 27.6% total - 24.8s
  material en la última placa: 0.072 m²  ·  tira libre: 2365 mm
```

(El DXF se escribió, o sea que la verificación pasó: el programa no escribe
uno que no haya verificado.)

El techo del plan sigue lejos: la placa 1 llega al 53.61% contra el 64.4% que
exigiría una sola placa.

---

## 8. Tests

### Modificados

- `tests/engine/test_effort.py::test_different_seeds_can_give_different_results`:
  el fixture pasa de 43 a 52 piezas. **Por qué, medido:** con contacto 4.0,
  43 piezas dan **un solo** layout entre las semillas 1-4 (con 1.0 dan 3), o
  sea que ninguna perturbación mejora al orden por área y `best` nunca se
  reemplaza. Con 52 piezas hay **4 layouts distintos entre 4 semillas con los
  dos pesos**. La aserción (`a.placements != b.placements`) no se ablandó: se
  corrigió el fixture para que vuelva a estar donde el orden de inserción
  decide, que es lo que el test dice que prueba.
- `tests/test_calibration.py::test_the_weight_sweep_respects_the_copies_argument`:
  desempaquetado posicional adaptado a la fila de 6 columnas. Misma aserción.

### Agregados

- `test_every_sweep_reports_what_the_engine_actually_minimises`: las filas
  traen material en la última y tira libre.
- `test_the_best_row_is_picked_with_the_engines_criterion_not_the_first_sheet`:
  con el orden anterior fallaría.
- `test_the_best_row_breaks_ties_by_time`.

### La suite, en limpio

```
$ .venv/bin/python -m pytest
1028 passed, 22 warnings in 416.62s (0:06:56)
```

**No está limpia de warnings.** Las 22 son todas `DeprecationWarning`, de dos
familias, ninguna introducida por esta tarea:

| # | Origen | Warning |
|---|---|---|
| 20 | Tests propios del proyecto (`tests/io/test_diagnostic.py`, `tests/io/test_preview.py`, `tests/test_cli.py`, `tests/test_icono.py`) | `Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.` |
| 2 | `fastapi`/`starlette` al importar `TestClient` | `Using httpx with starlette.testclient is deprecated; install httpx2 instead` y `The anyio.abc.BlockingPortal alias is deprecated` |

Las 20 de Pillow **son del código del proyecto** (sus tests) y se arreglan
cambiando `getdata()` por `get_flattened_data()`; las 2 restantes son de una
dependencia. No las toqué: quedan fuera del alcance de esta tarea y meter ese
cambio acá habría mezclado dos cosas en un commit. El dato relevante es que
la evidencia de la tarea anterior, tomada con `-p no:warnings`, **ocultaba
20 warnings del propio proyecto**.

---

## 9. Autorrevisión

- **¿Todos los números de los docstrings están medidos?** Sí. Crucé uno por
  uno contra las salidas guardadas de cada barrido. Los únicos números no
  medidos por mí son los que la nota de `EFFORT_RESTARTS` **cita** de la Task
  19 (46s/81s/317s), y están marcados como suyos.
- **¿Corriste `test_a_small_part_is_nested_inside_a_big_hole`?** Sí: bisección
  de 11 valores (§2.1) más el test real en la suite completa, dos veces, con
  el default nuevo.
- **¿Quedó prosa falsa?** Barrí «franja más grande» / «largest possible
  strip» en README, docs, src y bench: cero apariciones. Encontré y corregí de
  paso el conteo de tests (856 → 1028) y el tiempo de suite (~4 → ~7 min) en
  los dos README. Dejé a propósito el texto de ayuda de `--resolucion` en
  `cli.py`, en `web/info.js` y en la tabla de opciones de los README («más
  fino acomoda un poco mejor y tarda mucho más»): lo medido lo respalda, y
  cambiarlo desincronizaría el texto de la app con su spec y sus tests.
- **¿Está limpia la salida de la suite?** No. Ver §8.

---

## 10. Preocupaciones

1. **La elección de `contact = 4.0` descansa sobre una respuesta caótica.**
   4.0 no perdió nunca contra 1.0 en 7 celdas, y eso es lo mejor que tengo,
   pero 2.0 es peor que sus dos vecinos y 8.0/16.0 son peores que 4.0: el
   mecanismo no tiene pendiente. Si aparece un archivo nuevo, hay que
   remedir. Lo que **no** cambiaría es la parte sólida: por debajo de 0.7 se
   rompe el anidado en agujeros.
2. **0.8 quedó como segundo candidato vivo**, no descartado: gana en dos
   celdas. No lo elegí porque pierde en cuatro.
3. **`calibrate.py` sigue sin poder usar copias distintas por archivo**, que
   es lo que hace falta para que sus números discriminen. Con `--copias N`
   único, o un archivo no desborda o el otro tarda una eternidad. No lo
   arreglé (agregar ese flag es un cambio de interfaz que no pedía el brief),
   pero es la razón por la que las mediciones de este informe no salieron de
   la herramienta.
4. **No medí 0.5 mm/px sobre los dos archivos del banco.** A 1.0 ya tardaban
   413 s y 1077 s por celda. La conclusión sobre 0.5 se apoya sólo en el
   archivo de referencia (donde salió peor y 17.6x más lento).
5. **Los 20 warnings de Pillow son del proyecto** y siguen ahí.

---

## Arreglo: tres defectos de prosa en la calibración

Revisión de la Tarea 6 encontró tres defectos "Importante", los tres del
mismo tipo: un número o una afirmación en un docstring que la propia
evidencia de este informe no sostiene tal como estaba escrita. Ningún
valor calibrado cambió (`Weights.contact` sigue en 4.0, `NestConfig.resolution`
en 2.0, `EFFORT_RESTARTS` en 1/3/12); sólo se corrigió lo que la prosa dice
sobre esos valores.

### Hallazgo 1 — la ventaja de velocidad, mal repartida entre 0.0 y 0.5

`src/nesting/engine/oracle.py`, punto 1 del docstring de `Weights.contact`.
La tabla del §2.5 del informe (arriba) muestra que 0.5 tarda prácticamente
lo mismo que 4.0 sobre el archivo de referencia (25.9 s contra 25.4 s), y
el propio punto 2 del docstring explica por qué: el costo de la
correlación FFT de contacto se paga o no según `contact != 0.0`, no según
la magnitud del peso. Sólo 0.0 evita ese costo. El texto anterior le
atribuía la ventaja de velocidad a los dos valores por igual.

**Antes:**
> Así que 0.0 y 0.5 quedan descartados por más que sean 1.6-4.8x más
> rápidos y ganen en algunos archivos: bottom-left solo gana el argmax y
> la pieza chica se planta en el fondo-izquierda de la placa vacía.

**Después:**
> Así que 0.0 y 0.5 quedan descartados por el mismo piso: bottom-left solo
> gana el argmax y la pieza chica se planta en el fondo-izquierda de la
> placa vacía. La ventaja de velocidad es sólo de 0.0 -- 1.6-4.8x más
> rápido y gana el barrido en dos de los tres archivos -- porque el costo
> de la correlación FFT de contacto se paga o no según `contact != 0.0`
> (punto 2 más abajo), no según su magnitud: 0.5 tarda prácticamente lo
> mismo que 4.0 (25.9 s contra 25.4 s sobre el archivo de referencia).

`docs/superpowers/calibracion.md` ya tenía la afirmación bien acotada a
0.0 (línea 101-103 tras el arreglo) y no necesitó cambios.

### Hallazgo 2 — "48 piezas" citadas como el fixture, cuando el fixture tiene 52

`src/nesting/engine/oracle.py` (punto 4 del docstring de `Weights.contact`)
y `docs/superpowers/calibracion.md` (sección "Un caso sintético donde sí
decidió placas") describían la evidencia de la única celda donde el peso
cambió placas como "el fixture de
`test_different_seeds_can_give_different_results`... con 48 piezas". El
fixture, tal como está commiteado hoy, tiene 52 piezas
(`tests/engine/test_effort.py:171`, `range(52)`), y su propio docstring
explica por qué: 52 es la cantidad que sigue siendo sensible a la semilla
con los dos pesos (contacto 1.0 y 4.0 dan 4 layouts distintos entre 4
semillas). 48 no aparece en ningún otro lado del informe.

**No pude establecer, a partir de lo que quedó registrado en este informe,
si la corrida de 48 piezas reproduce el mismo resultado (1 placa contra 2)
sobre las 52 piezas del fixture final.** Lo que sí está bien establecido:
material (1000x1000), sep (8) y borde (15) de la corrida de 48 coinciden
exactamente con `base_config` del fixture (`tests/engine/test_effort.py:29`),
así que es una muestra generada con el mismo patrón de piezas que el
fixture, no un archivo distinto -- pero con una cantidad de piezas que ya
no es la que quedó commiteada. Los scripts puntuales de la sesión
(`scratchpad/semillas.py` y similares) no sobrevivieron al cierre de la
sesión que los corrió, así que no hay forma de re-verificar la corrida de
48 sin remedir, y este arreglo tiene explícitamente prohibido remedir. Por
eso el docstring deja la pregunta abierta en vez de adivinar una respuesta.

**Antes** (`oracle.py`, punto 4):
> UNA VEZ SÍ DECIDIÓ PLACAS, en un caso sintético justo en el quiebre: 48
> rectángulos variados (el fixture de
> `tests/engine/test_effort.py::test_different_seeds_can_give_different_results`,
> material de 1000x1000, sep 8, borde 15, esfuerzo normal) entran en UNA
> placa con contacto 4.0 y semillas 1 o 2, y necesitan DOS con contacto 1.0
> con las cuatro semillas probadas. Es un fixture sintético, no un archivo
> real, pero es la única celda medida donde este peso cambió lo que le
> cuesta al usuario.

**Después** (`oracle.py`, punto 4):
> UNA VEZ SÍ DECIDIÓ PLACAS, en un caso sintético justo en el quiebre: 48
> rectángulos variados, generados con el mismo patrón que el fixture de
> `tests/engine/test_effort.py::test_different_seeds_can_give_different_results`
> (mismo material de 1000x1000, sep 8, borde 15, esfuerzo normal) -- NO es
> el fixture tal como quedó en el repo, que tiene 52 piezas, elegidas por
> una razón distinta (que la Tarea 6 documenta en el docstring del propio
> test: que la salida siga siendo sensible a la semilla con los dos pesos).
> No quedó establecido, a partir de lo medido en la Tarea 6, si esta
> corrida de 48 sigue dando el mismo resultado sobre el fixture de 52
> piezas que terminó commiteado; lo que sí está medido es que estas 48
> piezas entran en UNA placa con contacto 4.0 y semillas 1 o 2, y necesitan
> DOS con contacto 1.0 en las cuatro semillas probadas. Es una muestra
> sintética, no un archivo real, pero es la única celda medida donde este
> peso cambió lo que le cuesta al usuario.

`docs/superpowers/calibracion.md` recibió el mismo arreglo en su sección
correspondiente (antes: "El fixture de
`test_different_seeds_can_give_different_results`... con 48 piezas";
después: "48 rectángulos variados, generados con el mismo patrón que el
fixture de... -- **no** es el fixture tal como quedó commiteado, que tiene
52 piezas... No quedó establecido si esta corrida de 48 piezas reproduce
el mismo resultado sobre las 52 del fixture final").

### Hallazgo 3 — la tabla de `EFFORT_RESTARTS` no decía a qué peso de contacto se midió

`src/nesting/engine/packer.py`, nota de `EFFORT_RESTARTS`. La tabla de
reintentos por nivel de esfuerzo (§4 del informe) se midió con
`contact = 1.0`, el peso vigente mientras corría esa parte de la Tarea 6,
antes de que la misma tarea recalibrara el default a 4.0. La nota no lo
decía, a diferencia de la nota vecina de `Weights.contact` en `oracle.py`,
que sí dice "MEDIDO EN LA TAREA 6 (contacto 1.0...)". Peor que la omisión:
hay evidencia directa, en el propio commit, de que el peso nuevo puede
cambiar lo que valen los reintentos.
`tests/engine/test_effort.py::test_different_seeds_can_give_different_results`
(líneas 157-163) registra que sobre las mismas 43 piezas que antes usaba
el fixture, subir contacto de 1.0 a 4.0 colapsó 3 layouts distintos entre
4 semillas a uno solo -- ninguna perturbación del orden de inserción
mejoraba al orden por área, así que el mejor de N intentos nunca se
reemplazaba. Eso es exactamente lo que hacen los reintentos de `normal` y
`lento`. No se remidió la tabla de esfuerzo con contacto 4.0, así que no
hay evidencia de si eso mismo pasa sobre archivos reales; se dejó dicho
como pregunta abierta, no como conclusión.

**Antes:**
> Sobre `NESTING 2.ai` (mdf15, sep 10, borde 10, 2.0 mm/px), medido en la
> Tarea 6:
>
> | nivel  | reparto | material última | alto última | seg   |
> |--------|---------|-----------------|-------------|-------|
> | rapido | 32 / 4  | 0.1432 m²       | 235 mm      | 37.7  |
> | normal | 33 / 3  | 0.1106 m²       | 308 mm      | 48.3  |
> | lento  | 35 / 1  | 0.1061 m²       | 491 mm      | 136.2 |
>
> [...]
>
> CUÁNDO SIGUE SIN COMPRAR NADA. [...] Lo que cambió es que ahora, cuando
> rinde, se nota.
>
> EL PRESUPUESTO DE 5 MINUTOS, HONESTAMENTE. [...]

**Después** (dos cambios: la frase que abre la tabla, y un párrafo nuevo
entre "CUÁNDO SIGUE SIN COMPRAR NADA" y "EL PRESUPUESTO DE 5 MINUTOS"):
> Sobre `NESTING 2.ai` (mdf15, sep 10, borde 10, 2.0 mm/px), medido en la
> Tarea 6 con `contact = 1.0` -- el peso vigente mientras se corrió este
> barrido, antes de que la misma Tarea 6 lo recalibrara a 4.0 (ver
> `Weights.contact` en `oracle.py`):
>
> [misma tabla]
>
> [...]
>
> CUÁNDO SIGUE SIN COMPRAR NADA. [...] Lo que cambió es que ahora, cuando
> rinde, se nota.
>
> LO QUE ESTA TABLA NO RESPONDE. Todo lo de arriba -- la tabla de la Tarea
> 6 y la de la Task 19 con la que se compara -- se midió con
> `contact = 1.0`. Esta misma Tarea 6 deja de usar ese valor: el default
> pasa a 4.0. El barrido de esfuerzo NO se volvió a correr con
> `contact = 4.0`, y hay una razón concreta para sospechar que el
> resultado podría no ser el mismo. En
> `tests/engine/test_effort.py::test_different_seeds_can_give_different_results`
> (líneas 157-163 de ese archivo), subir contacto de 1.0 a 4.0 sobre las
> mismas 43 piezas colapsó 3 layouts distintos entre 4 semillas a UNO
> SOLO: ninguna perturbación del orden de inserción mejoraba al orden por
> área, así que `best` nunca se reemplazaba. Eso es exactamente lo que los
> reintentos de `normal` y `lento` son -- perturbaciones del orden de
> inserción de las que se conserva la mejor -- así que si `contact = 4.0`
> aplana el espacio de búsqueda de la misma manera sobre archivos reales,
> los reintentos podrían estar comprando menos de lo que dice la tabla de
> arriba. No hay medición en ningún sentido: ni que lo confirme ni que lo
> descarte. La tabla y la conclusión "nada cambió de signo" quedan tal
> cual porque no hay evidencia para moverlas, no porque se haya verificado
> que siguen valiendo a `contact = 4.0`.
>
> EL PRESUPUESTO DE 5 MINUTOS, HONESTAMENTE. [...]

### Verificación

```
$ .venv/bin/python -m pytest tests/engine/test_effort.py tests/test_calibration.py tests/engine/raster/test_raster_oracle.py
41 passed in 375.62s (0:06:15)
```

```
$ grep -n "48" src/nesting/engine/oracle.py docs/superpowers/calibracion.md
```
Las únicas apariciones de "48" en esos dos archivos son, ahora, las que
explican por qué esa cantidad **no** es el fixture commiteado (52 piezas);
ninguna la sigue llamando "el fixture".

No se tocó `src/nesting/geometry/verify.py`, ningún test se debilitó, y
`Weights.contact`, `NestConfig.resolution` y `EFFORT_RESTARTS` quedaron con
los mismos valores.
