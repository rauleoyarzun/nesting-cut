# Informe Tarea 5: Pasada de recuperación entre placas

## Resumen

Se implementó `_recuperar_de_la_ultima_placa` en `src/nesting/engine/packer.py`,
llamada desde `pack` justo antes de `_compact_last_sheet`, más los tres tests de
`tests/engine/test_recuperacion.py`, escritos completos (el brief los dejaba en `...`).

**La implementación NO es la del brief, y eso es el hallazgo central de la tarea:
el algoritmo del brief no puede recuperar una sola pieza, nunca.** Está probado
abajo por razonamiento y por medición, incluida una corrida del código del brief
verbatim contra los tres tests. En su lugar se implementó una variante que sí
recupera, con el mismo nombre, la misma firma y el mismo punto de llamada.

## El hallazgo: la versión del brief es un no-op demostrable

El brief reconstruye la placa anterior tal cual quedó (replay de `oracle.place`) y
le vuelve a preguntar si la pieza pendiente entra. Eso no puede funcionar:

1. `_pack_once` prueba **cada** pieza pendiente contra **cada** placa: la que
   terminó en la última ya fue rechazada por la placa 0 cuando le tocó su turno.
2. El estado de la placa 0 al final de la pasada es un **superconjunto** del que la
   rechazó: colocar sólo agrega material, nunca lo saca.
3. Los dos oráculos son **monótonos** en ese sentido — `ShelfOracle` avanza un
   cursor que nunca retrocede, y `RasterOracle` marca píxeles que nunca se borran y
   registra polígonos en el árbitro que nunca se sacan. Si la pieza no entraba con
   menos material, menos entra con más.

O sea que el "hueco que abren las piezas colocadas después", que es la premisa del
brief y del docstring del primer test, no existe: las piezas posteriores no abren
huecos, sólo los cierran.

Medición (script en el scratchpad de la sesión, `probe.py`), con exactamente el
código del brief:

| motor | escenarios al azar multiplaca | piezas recuperadas |
|---|---|---|
| `ShelfOracle` | 30 | **0** |
| `RasterOracle` | 15 | **0** |
| `NESTING 2.ai` real | 1 | **0** |

## Lo que sí funciona: cambiar el orden de inserción

El problema no es la falta de espacio: es el **orden**. La pieza se rechazó porque
llegó última a una placa armada para otras. Si la placa se rearma desde cero con
esa pieza **adelante de todo**, la placa se construye alrededor de ella y aparecen
layouts que la pasada golosa no puede alcanzar.

Algoritmo implementado, por cada placa anterior:

1. `orden = [pendiente más chica] + [piezas de la placa, en el orden en que se
   colocaron] + [el resto de las pendientes]`, y un `_pack_once` con ese orden.
   Las pendientes que no encabezan viajan igual al final, así que pueden entrar
   "de arrastre" sin costar un intento propio.
2. Se acepta el reempaque **sólo** si en su primera placa siguen estando todas las
   piezas que ya tenía y entró al menos una pendiente.
3. Si aceptó, se repite (la siguiente pendiente más chica pasa al frente). Si no,
   se corta y la placa queda exactamente como estaba.

Con esa regla de aceptación el costo **no puede subir**: las placas anteriores
conservan sus piezas, la última sólo pierde, y las que quedan en la última no se
mueven, así que ni `material_ultima` ni `alto_ultima` crecen; si la última se vacía,
baja `placas`, que es el primer campo de `CostoLayout`.

Por qué esta variante y no "un `_pack_once` por pieza pendiente" (medido sobre los
mismos 15 escenarios raster):

| variante | piezas recuperadas | intentos (cada uno = un `_pack_once`) |
|---|---|---|
| una pendiente por intento | 4 | 46 |
| un intento por placa, sin repetir | 2 | 15 |
| **la implementada** (repite mientras recupere) | **3** | **18** |

Sobre `NESTING 2.ai` la variante cara y la implementada recuperan **la misma
pieza**; la cara paga 5 reempaques (53 s) y la implementada 2 (24 s).

## Los tres tests, y por qué ninguno pasa en el vacío

`tests/engine/test_recuperacion.py`, `ShelfOracle` con una sola orientación para que
el escenario sea reproducible a mano (960x960 mm útiles, sep 10).

Piezas: `ANCHA` 600x450, `MEDIA` 600x400, `ANGOSTA` 300x520.
Pasada golosa (área descendente): `ANCHA` abre el estante y=20 y deja el cursor en
x=630; `MEDIA` no entra a su derecha y abre el estante y=480; `ANGOSTA` entra a lo
ancho (630+300 ≤ 980) pero no a lo alto (480+520 > 980), y un estante nuevo
arrancaría en y=890, donde tampoco entra → **se va a la placa 2**. Con `ANGOSTA`
adelante las tres entran en una sola placa.

1. **`test_una_pieza_de_la_ultima_placa_vuelve_a_la_primera_si_entra`** — el
   load-bearing. Primero **afirma que la avaricia falla** (`_pack_once` da 2 placas
   y `ANGOSTA` queda en la placa 1), y recién después que la recuperación la trae a
   la placa 0. Cierra con `verify()` sobre el layout recuperado (cero violaciones) y
   con `pack()` de punta a punta devolviendo una sola placa.
   *No puede pasar en el vacío*: las dos primeras aserciones fallan si el escenario
   deja de defender a la avaricia, y la tercera falla si la recuperación no mueve la
   pieza. Verificado a mano: contra el código del brief da `[1] == [0]`, o sea que
   la pieza realmente termina en la placa 2 sin la recuperación.
2. **`test_si_la_ultima_placa_queda_vacia_se_descarta`** — exige `sheets_used == 1`,
   que ninguna ubicación mencione la placa 1, y la aritmética del aprovechamiento:
   `utilization == [suma de áreas / área de placa]` (una sola entrada, no dos) y
   `total_utilization` igual a esa entrada (no promediado sobre dos placas), más que
   `seconds` se arrastre sin tocar.
   *No puede pasar en el vacío*: sin recuperación `sheets_used` es 2 y la primera
   aserción cae; y si se recalculara el aprovechamiento como el brief (sumando
   fracciones ya divididas) o dejando la fila de la placa vacía, caen las otras.
3. **`test_la_recuperacion_nunca_empeora_el_costo`** — propiedad sobre 50 escenarios
   al azar (30 `ShelfOracle` + 20 `RasterOracle`, rectángulos al azar sobre una placa
   de 800x800): de los que dan más de una placa, en todos exige
   `layout_cost(después) <= layout_cost(antes)`, conservación exacta del conjunto de
   piezas, que no queden placas vacías, y `verify()` sin violaciones.
   *No puede pasar en el vacío*: termina con `multiplaca >= 10` y `recuperaron >= 1`,
   así que una función que no hace nada falla la última. Medido al escribirlo: 32
   escenarios multiplaca, **14 con mejora estricta** del costo. El piso se dejó en 1
   a propósito, para que defienda "no es un no-op" sin romperse ante un cambio
   legítimo de heurística.

## Evidencia TDD

### ROJO 1 — los tests antes de que exista la función

```
$ .venv/bin/python -m pytest tests/engine/test_recuperacion.py -v
collected 0 items / 1 error
E   ImportError: cannot import name '_recuperar_de_la_ultima_placa' from
    'nesting.engine.packer'
=========================== short test summary info ============================
ERROR tests/engine/test_recuperacion.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

Esperado: la función no existe todavía.

### ROJO 2 — los tests contra el código del brief, verbatim

Se pegó el bloque del brief tal cual en `packer.py` (después se revirtió) y se
corrieron los mismos tres tests. Esta es la prueba de que el brief es un no-op:

```
$ .venv/bin/python -m pytest tests/engine/test_recuperacion.py -v
FFF                                                                      [100%]
________ test_una_pieza_de_la_ultima_placa_vuelve_a_la_primera_si_entra ________
>       assert [p.sheet for p in recuperado.placements if p.part_id == ANGOSTA.id] == [0]
E       assert [1] == [0]
E         At index 0 diff: 1 != 0
_______________ test_si_la_ultima_placa_queda_vacia_se_descarta ________________
>       assert recuperado.sheets_used == 1
E       assert 2 == 1
E        +  where 2 = PackResult(..., sheets_used=2,
E             utilization=[0.51, 0.156], total_utilization=0.333, ...).sheets_used
_______________ test_la_recuperacion_nunca_empeora_el_costo ____________________
>       assert recuperaron >= 1
E       assert 0 >= 1
=========================== short test summary info ============================
FAILED tests/engine/test_recuperacion.py::test_una_pieza_de_la_ultima_placa_vuelve_a_la_primera_si_entra
FAILED tests/engine/test_recuperacion.py::test_si_la_ultima_placa_queda_vacia_se_descarta
FAILED tests/engine/test_recuperacion.py::test_la_recuperacion_nunca_empeora_el_costo
============================== 3 failed in 1.72s ===============================
```

Notar el tercero: `recuperaron == 0` sobre 32 escenarios multiplaca al azar. La
propiedad "no empeora" la cumple, claro — no hace nada.

### VERDE — con la implementación

```
$ .venv/bin/python -m pytest tests/engine/test_recuperacion.py -v
collected 3 items

tests/engine/test_recuperacion.py ...                                    [100%]

============================== 3 passed in 1.99s ===============================
```

Sin warnings: `-W error` también pasa limpio.

### Suite completa

```
$ .venv/bin/python -m pytest
1024 passed, 22 warnings in 314.05s (0:05:14)
```

Base 1021 + los 3 nuevos. Los 22 warnings son los de siempre
(`Image.Image.getdata` deprecado en Pillow, en `tests/io/test_preview.py`,
`tests/test_cli.py` y `tests/test_icono.py`); ninguno sale del código de esta tarea.

## La corrida real

```
$ .venv/bin/python -m nesting.cli "/Users/raulo/Downloads/NESTING 2.ai" \
      --material mdf15 --sep 10 --borde 10 --esfuerzo rapido -o /tmp/recuperacion.dxf
Placa 1/2   aprovechamiento  52.1%
Placa 2/2   aprovechamiento   3.0%   <- sobrante útil ~1830x2365 mm
----------------------------------
36 piezas - 2 placas - 27.6% total - 35.8s
  material en la última placa: 0.143 m²  ·  tira libre: 2365 mm
Escrito en /tmp/recuperacion.dxf
```

Antes (misma corrida sobre el commit anterior, `/tmp/recuperacion-baseline.dxf`):

```
Placa 1/2   aprovechamiento  51.3%
Placa 2/2   aprovechamiento   3.8%   <- sobrante útil ~1830x2365 mm
----------------------------------
36 piezas - 2 placas - 27.6% total - 11.7s
  material en la última placa: 0.179 m²  ·  tira libre: 2365 mm
```

Piezas por placa, contadas aparte sobre el mismo layout:

```
placas 2 por placa [(0, 32), (1, 4)] 34.9s
violaciones 0
```

O sea: **31/5 pasa a 32/4**, el material de la última placa baja de 0.179 a
0.143 m² (-20%), cero violaciones. Es exactamente el movimiento que el usuario hizo
a mano: un disco de la placa 2 a un hueco de la placa 1.

**El costo en tiempo, que es la contra: 11.7 s → 35.8 s (3.1x).** Son dos
reempaques de placa a ~12 s cada uno: el primero recupera el disco, el segundo
confirma que no entra ninguno más. No lo escondo: es un empeoramiento material en
tiempo. Lo que lo hace aceptable, y por qué se eligió igual:

- La pasada corre **una sola vez por `pack()`**, no una por reintento, así que el
  sobrecosto es constante y no escala con `--esfuerzo`: en `normal` (3 pasadas,
  ~35 s de base) queda en ~60 s, y en `lento` (~140 s) es ruido. El peor caso
  relativo es justamente `rapido`, que es el que se midió.
- Está acotado por construcción: un intento por placa anterior, y un intento extra
  **sólo después de uno que recuperó algo de verdad**. El techo es
  `(placas - 1) + piezas recuperadas` reempaques.
- Bajarlo a 1 intento por placa (~24 s totales) recupera lo mismo en este archivo
  pero la mitad en los escenarios al azar (2 vs 3 de 4). Queda como la palanca
  obvia si el tiempo pesa más que la densidad.

## Archivos tocados

- `src/nesting/engine/packer.py` — `_recuperar_de_la_ultima_placa` nueva (+ el
  docstring que deja escrito por qué la versión intuitiva no puede funcionar, para
  que no se reintente), y la llamada en `pack`.
- `tests/engine/test_recuperacion.py` — nuevo, los tres tests.

Commit: `9e5e67e` "Reintentar en las placas anteriores lo que quedó en la última".

## Autorrevisión

- **¿Los tests prueban lo que su nombre dice?** Sí, y los tres fallan contra el
  código del brief, que es la prueba más dura de que no pasan en el vacío.
- **¿El escenario del primer test derrota de verdad a la avaricia?** Sí, y está
  afirmado dentro del test (`goloso.sheets_used == 2` y `ANGOSTA` en la placa 1),
  no sólo comprobado a mano.
- **¿La aritmética del aprovechamiento al descartar una placa?** Se hace igual que
  en `_pack_once`: áreas por placa y **una** división al final, en vez de sumar
  fracciones ya divididas como hacía el brief. El segundo test lo fija con valores
  exactos. `_compact_last_sheet`, que corre después y reescribe
  `utilization[última]`, sigue viendo una lista del largo correcto.
- **¿Puede la recuperación producir un layout inválido?** Las ubicaciones salen de
  `_pack_once` → oráculo → árbitro exacto, así que es válido por construcción; igual
  se afirma con `verify()` real en el test 1 y en los 32 escenarios del test 3.
- **¿Salida de pytest limpia?** Sí, verificado con `pytest` a secas y con `-W error`.
- **Terminación**: cada vuelta del `while` o corta o saca al menos una pieza de
  `pendientes` (las ganadas son siempre pendientes), así que no puede colgarse.
- **`PartTooLargeError` durante un reempaque**: imposible. Toda pieza de `orden` ya
  se colocó alguna vez, así que la primera de cada placa siempre entra y el guard
  `placed_count == 0` no puede dispararse.

## Preocupaciones

1. **Tiempo**: 3.1x en `rapido` sobre el archivo real (detalle y palanca arriba). Es
   lo único que empeoró.
2. **La barra de progreso se congela más tiempo.** La recuperación no emite
   `Avance`: la llamada se puso **después** del aviso `compactando=True` para que la
   UI ya esté en ese estado, pero son ~24 s sin novedades donde antes eran ~1 s. Por
   el mismo motivo, un pedido de cancelación durante la recuperación no se atiende
   hasta que termina. Precedente: `_compact_last_sheet` ya era silenciosa. Si se
   quiere arreglar, hace falta un campo nuevo en `Avance` (`recuperando`), que toca
   la app y sus tests, y quedaba fuera del alcance de esta tarea.
3. **Desviación del plan**: el algoritmo no es el del brief. El nombre, la firma y
   el punto de llamada sí lo son, y el `CostoLayout` no puede empeorar, pero si el
   plan se revisa contra el brief hay que leer esta sección y no el diff a secas.
4. La heurística "la más chica adelante" es razonable pero no óptima: sobre los
   escenarios al azar deja 1 de 4 piezas sin recuperar respecto de probarlas todas.
   Recuperarla cuesta 2.5x más reempaques.

## Arreglo: cancelación durante la recuperación

Hallazgo de la revisión: la preocupación #2 de arriba se cerró como "necesita un
campo nuevo en `Avance`, fuera de alcance", pero eso sólo vale para la mitad de
mostrar "recuperando" en la barra. La mitad de **cancelación** no necesitaba nada
nuevo: `_pack_once` ya acepta `aviso`, `pack` ya arma callbacks que cancelan vía
`avisos_de`, y `Avance.compactando` ya existe y ya se pone en `True` para este
tramo. Lo único que faltaba era pasarle un `aviso` a
`_recuperar_de_la_ultima_placa` en vez de dejarlo en `None`. La etiqueta
"recuperando" en la UI sigue fuera de alcance; lo que se arregla acá es que el
motor deje de estar sordo, no cómo se llama la fase.

### RED

Test nuevo en `tests/engine/test_progreso.py`,
`test_cancelar_durante_la_recuperacion_levanta`: dejar pasar el primer aviso
`compactando=True` (el que anuncia la entrada al tramo final) y cortar en el
segundo, que sólo puede salir de dentro de `_recuperar_de_la_ultima_placa`
porque `_compact_last_sheet` corre después y sigue sin instrumentar.

```
$ .venv/bin/python -m pytest tests/engine/test_progreso.py::test_cancelar_durante_la_recuperacion_levanta -v
======================= test session starts ========================
collected 1 item

tests/engine/test_progreso.py F                                  [100%]

============================= FAILURES ==============================
______ test_cancelar_durante_la_recuperacion_levanta ______

    with pytest.raises(Cancelado):
E       Failed: DID NOT RAISE Cancelado

tests/engine/test_progreso.py:169: Failed
======================== 1 failed in 4.21s ==========================
```

Falla por el motivo correcto: sin `aviso`, la recuperación corre entera y
`pack` termina normalmente en vez de cancelarse.

### Implementación

- `_recuperar_de_la_ultima_placa` recibe `aviso: Callable[[int, int], None] |
  None = None` y lo reenvía tal cual a su único `_pack_once` interno — misma
  forma que ya usa `_pack_once`, sin inventar un mecanismo paralelo.
- `pack` arma `aviso_recuperacion`, que reporta
  `Avance(intentos, intentos, totales, totales, 0, compactando=True)` — el
  mismo `Avance` que ya se manda al entrar al tramo final — y levanta
  `Cancelado` si `progreso` devuelve `False`, igual que hace `avisos_de` para
  las pasadas golosas. Se lo pasa a `_recuperar_de_la_ultima_placa` antes de
  llamar a `_compact_last_sheet` (que sigue sin tocarse: cubre ~1 s, es un
  problema distinto).
- Comentario en el punto de llamada explicando por qué se reporta como
  `compactando` y no como una fase propia: `Avance` no tiene campo para
  distinguirla, agregar uno es una decisión de UI aparte, y para quien mira
  la barra "compactando" ya es una descripción verdadera de un reempaque
  sobre placas ya armadas.
- Ningún cambio en `Avance`, en `src/nesting_app/`, ni en el algoritmo de
  recuperación en sí.

### GREEN

```
$ .venv/bin/python -m pytest tests/engine/test_progreso.py::test_cancelar_durante_la_recuperacion_levanta -v
======================= test session starts ========================
collected 1 item

tests/engine/test_progreso.py .                                  [100%]

============================== 1 passed in 2.66s ===============================
```

### Tests de cobertura

```
$ .venv/bin/python -m pytest tests/engine/test_recuperacion.py tests/engine/test_packer.py tests/engine/test_effort.py tests/engine/test_progreso.py -v
======================= test session starts ========================
collected 48 items

tests/engine/test_recuperacion.py ...                            [  6%]
tests/engine/test_packer.py ..................                   [ 43%]
tests/engine/test_effort.py ................                     [ 77%]
tests/engine/test_progreso.py ...........                        [100%]

============================== 48 passed in 49.93s ===============================
```

También corrida `tests/app/test_jobs.py` (usa `Cancelado` desde la capa de la
app, no tocada) como chequeo extra: 17 tests, todos verdes.

### Preocupación #2 actualizada

Queda resuelta la mitad de cancelación: un watcher que devuelve `False`
durante la recuperación corta el trabajo en el siguiente aviso, sin esperar a
que termine el tramo entero (~24 s en el job de referencia). Sigue pendiente,
y sigue genuinamente fuera de alcance, la etiqueta "recuperando" en la UI —
la barra se mueve pero se sigue leyendo como "compactando" durante esta fase.
