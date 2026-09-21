# Tarea 4: la grilla pasa a ser optimista y el árbitro decide

Commit: `788c7f9` — *La grilla propone y la geometría exacta dispone: separación
real, no inflada*

## Qué se implementó

### `masks.py`
- `INFLACION_MAX_PX = 2` y `radio_optimista(sep, resolution)`, textualmente como
  los da el brief (no se tocó el valor ni la fórmula).
- `PartMasks.holgura_optimista(radio_px)`, igual al brief más un párrafo sobre
  por qué el arreglo sale del mismo tamaño que `clearance` (un radio menor que
  el conservador nunca se sale de `pad`), que es lo que permite usar las dos
  holguras contra la misma ventana correlacionada.

### `scoring.py`
- Se separó `position_scores(feasible, sheet, band, weights) -> np.ndarray` de
  `best_position`, que queda como el argmax de esa función. Hacía falta porque
  el motor híbrido no se queda con la mejor posición: recorre las factibles en
  orden de puntaje. Con una sola definición compartida, el recorrido y el
  máximo no pueden discrepar sobre qué es "mejor posición" — que es
  exactamente el atajo (abajo-izquierda sin contacto) que el prototipo tomaba y
  que había que no copiar. `best_position` conserva su firma y su
  comportamiento; los tests de `test_scoring.py` no se tocaron.

### `oracle.py`
- `__init__`: `self._arbitro: ArbitroExacto | None = None` y
  `self._radio_optimista = 0`.
- `reset`: crea el árbitro y calcula el radio. Como `_pack_once` pide un
  oráculo nuevo por placa y lo resetea, el árbitro queda correctamente acotado
  a una placa.
- `place`: `self._arbitro.agregar(...)` después del `|=` sobre la grilla.
- `_search`: recibe ahora `part/angle/mirror` (el árbitro los necesita) y hace
  dos pasadas sobre la MISMA ventana ya padeada: primero con la holgura
  optimista y arbitraje, y si de ahí no sale nada, con `masks.clearance` sin
  arbitrar. La red de seguridad es obligatoria, no opcional.
- `_buscar_con` (nuevo) y `_mejores` (helper de módulo).

### Cómo quedó `_buscar_con`

```
_buscar_con(part, angle, mirror, masks, padded, holgura, *, arbitrar)
```

1. `feasible = feasible_positions(padded, holgura)`; corta si está vacío.
2. `score = position_scores(feasible, padded, _banda_de_contacto(masks), weights)`
   — el puntaje real, con término de contacto.
3. `arbitrar=False`: argmax directo, desplazado por `-pad`. Es el camino viejo,
   tal cual.
4. `arbitrar=True`: recorre los candidatos en orden de puntaje descendente, de a
   `CANDIDATOS_POR_TANDA`, hasta `MAX_CANDIDATOS`. Por cada uno convierte
   (fila, columna) a mm con `masks.translation_for(...) + margin` y le pregunta
   a `self._arbitro.entra(...)`. Devuelve el primero que pasa. Los ya mirados se
   tachan con `-inf` y la próxima tanda son los mejores de lo que queda.

`_mejores(valores, cuantos)` usa `argpartition` (O(n)) y recién ordena la tanda
(decenas de elementos): ordenar las cientos de miles de posiciones de una placa
para quedarse con 64 sería tirar casi todo el trabajo.

El argumento de corrección (por qué el conjunto optimista es un superconjunto
del factible real) quedó escrito **en el docstring de `_buscar_con`**, que es
adonde apunta `radio_optimista`. Incluye el corolario que no estaba en el
brief y que justifica la red de seguridad: la mejor posición conservadora
también es candidata en la pasada optimista y el árbitro la acepta seguro, así
que cualquier candidato devuelto antes puntúa al menos tan bien; lo único que
puede impedir llegar hasta ella es `MAX_CANDIDATOS`, y para eso está la segunda
pasada.

## Un hallazgo que no estaba previsto: la banda de contacto

El brief sugiere armar `feasible` y la banda "a partir del mismo arreglo de
holgura". Hacerlo literal — banda sobre la holgura optimista — **rompe
`test_a_small_part_is_nested_inside_a_big_hole`** (la ganancia de la spec 5.2):
la pieza chica dejaba de encastrar en el agujero de la grande y se iba al
costado.

La causa, medida sobre dos rectángulos de 100 mm a 2 mm/px (pieza vecina a
distancia real `d`, término de contacto normalizado):

| banda | 0-8 mm | 10 mm | 12 mm | 14 mm | 16 mm | 18 mm | 20 mm |
|---|---|---|---|---|---|---|---|
| sobre la holgura optimista | 0.239 | 0.119 | 0.000 | 0.000 | 0.000 | 0.000 | 0 |
| sobre `clearance` (la de siempre) | 0.215 | 0.215 | 0.215 | 0.215 | 0.215 | 0.107 | 0 |
| anillo ancho (hasta `clearance`+3 mm, desde la optimista) | 0.224 | 0.187 | 0.149 | 0.112 | 0.075 | 0.037 | 0 |

`contact_band` devuelve el anillo que queda *justo afuera* de la máscara que
recibe, así que la holgura optimista —que es fina— **se traga la zona de
contacto**: una vecina a la distancia pedida exacta puntúa la mitad, y de 12 mm
en adelante es invisible. Peor: el máximo cae en distancias que el árbitro
rechaza.

Se dejó la banda **sobre `clearance`, sin cambios respecto de antes**. La
restricción real del brief es de *forma* del arreglo, y se cumple sola: todas
las máscaras de una `PartMasks` viven en la misma grilla y dilatar no cambia el
tamaño. Todo esto está escrito en `_banda_de_contacto`, con los números.

Se midió también la variante del anillo ancho (monótona sobre el rango legal,
teóricamente la más correcta): pasa todos los tests igual, pero empaqueta
**peor** en el trabajo real (30 piezas en la primera placa contra 31). Como la
tarea es sobre separación y no sobre el término de contacto, se optó por no
cambiarle el significado. Queda anotado abajo como candidato a revisar.

## Evidencia TDD

### RED

```
$ .venv/bin/python -m pytest tests/engine/raster/test_raster_oracle.py -k separacion_real -v
...
        real = polys[0].distance(polys[1])
>       assert real == pytest.approx(10.0, abs=0.51), (
            f"la separación real quedó en {real:.2f} mm y se pidieron 10.00"
        )
E       AssertionError: la separación real quedó en 16.00 mm y se pidieron 10.00
E       assert 16.0 == 10.0 ± 0.51
E         Obtained: 16.0
E         Expected: 10.0 ± 0.51

tests/engine/raster/test_raster_oracle.py:312: AssertionError
=========================== short test summary info ============================
FAILED tests/engine/raster/test_raster_oracle.py::test_la_separacion_real_es_la_pedida_no_la_inflada
======================= 1 failed, 15 deselected in 0.81s =======================
```

Falla exactamente como el brief predice, y con el número exacto: 16.00 mm
cuando se piden 10. Es la inflación doble (2 px por lado x 2 mm/px x 2 piezas =
8 mm sobre los... 10 pedidos, que la grilla redondea a 16 medidos sobre los
polígonos exactos). La medición es sobre `placed_polygon`, no sobre la grilla,
así que el test no puede pasar "por construcción de la grilla".

### GREEN

```
$ .venv/bin/python -m pytest tests/engine/raster/test_raster_oracle.py -k separacion_real -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/Projects/cut-placement/.claude/worktrees/densidad-colision-exacta
configfile: pyproject.toml
plugins: anyio-4.15.1
collected 16 items / 15 deselected / 1 selected

tests/engine/raster/test_raster_oracle.py .                              [100%]

======================= 1 passed, 15 deselected in 0.69s =======================
```

### Segundo test: la red de seguridad, ejercitada de verdad

`test_si_se_agota_el_presupuesto_de_candidatos_se_cae_al_camino_conservador`
baja `MAX_CANDIDATOS` a 1 con `monkeypatch`. Medido antes de escribirlo:

```
tope=1024: pieza 1 en (120,10)  ->  separacion real 10.00
tope=4:    pieza 1 en (120,10)  ->  separacion real 10.00
tope=1:    pieza 1 en (126,10)  ->  separacion real 16.00
```

Con un solo candidato permitido, el mejor de la grilla optimista lo rechaza el
árbitro, no queda presupuesto, y la pieza **igual se coloca** — por el camino
conservador, con la separación inflada de siempre. El test afirma las dos
cosas: que se colocó, y que la separación es > 12 mm (o sea que efectivamente
vino del camino conservador y no del árbitro).

## Suites

```
$ .venv/bin/python -m pytest tests/engine -p no:warnings
153 passed in 73.11s (0:01:13)

$ .venv/bin/python -m pytest -p no:warnings
1021 passed in 245.67s (0:04:05)
```

1021 = los 1019 de base + los 2 tests nuevos. Ninguno se modificó ni se relajó.

## El trabajo real

```
$ time .venv/bin/python -m nesting.cli "/Users/raulo/Downloads/NESTING 2.ai" \
      --material mdf15 --sep 10 --borde 10 --esfuerzo rapido -o /tmp/hibrido.dxf
Placa 1/2   aprovechamiento  51.3%
Placa 2/2   aprovechamiento   3.8%   <- sobrante útil ~1830x2365 mm
----------------------------------
36 piezas - 2 placas - 27.6% total - 12.4s
  material en la última placa: 0.179 m²  ·  tira libre: 2365 mm
Escrito en /tmp/hibrido.dxf
.venv/bin/python -m nesting.cli ...  13.07s user 0.29s system 97% cpu 13.679 total
```

El CLI verifica y aborta sin escribir si hay violaciones; escribió, o sea que no
hubo. Contado aparte, con la misma configuración:

```
placa -> piezas: {0: 31, 1: 5}
placas: 2  total: 36  12.3s
violaciones: 0
  placa 0: separacion minima real 10.00 mm
  placa 1: separacion minima real 11.00 mm
```

**La separación mínima real es 10.00 mm exactos, contra los 16.00 de antes.**
Eso es lo que la tarea venía a entregar, y está entregado.

### Piezas por placa: 31/5, no 33/3 — por qué

Es peor que el prototipo y hay que decirlo. Matriz medida sobre el mismo
trabajo, con el mismo arnés (la línea "base conservador" reproduce exactamente
el 29/7 documentado, o sea que el arnés es fiel):

| variante | placa 1 | placa 2 | tiempo |
|---|---|---|---|
| base conservador (motor de hoy) | 29 | 7 | 18.7 s |
| híbrido, banda sobre `clearance` **(lo que se commiteó)** | **31** | **5** | 12.4 s |
| híbrido, banda ancha | 30 | 6 | 13.0 s |
| híbrido, banda sobre la holgura optimista (rompe el test del agujero) | 32 | 4 | 14.6 s |
| híbrido, `weights.contact = 0` | 34 | 2 | 7.5 s |
| base conservador, `weights.contact = 0` | 30 | 6 | 10.8 s |

La diferencia con el 33/3 del prototipo **no es del mecanismo híbrido: es del
término de contacto**. El prototipo ordenaba los candidatos sólo por
abajo-izquierda, que es justamente el atajo que se me indicó no copiar. Con el
contacto apagado, esta implementación da 34/2 — mejor que el prototipo, porque
además tiene la segunda pasada por frontera y la red de seguridad.

O sea: en este trabajo el término de contacto **cuesta** piezas, y ya las
costaba antes del cambio (30/6 -> 29/7 con el motor conservador). No es una
regresión que introduzca esta tarea. Pero ahora que el motor puede empaquetar
más apretado, el peso relativo `bottom_left`/`contact` merece una medición
propia; no la hice acá porque cambiar los pesos no es parte de esta tarea y
requiere su propia evidencia sobre varios trabajos, no sobre uno.

### Los topes de candidatos

`CANDIDATOS_POR_TANDA = 64` y `MAX_CANDIDATOS = 1024` están **bien** para este
trabajo, medido. Instrumentando `_buscar_con` sobre el archivo real:

```
tope= 1024 tanda=  64: {0: 31, 1: 5} viol=0  {'arb': 384, 'arb_none': 48, 'cons': 48, 'cons_none': 48}
tope= 4096 tanda=  64: idéntico
tope=16384 tanda= 256: idéntico
```

Las 48 veces que la pasada optimista no devolvió nada son las 48 veces que la
conservadora **tampoco** devolvió nada: son piezas que sencillamente no entran
(cambio de placa). El presupuesto nunca se agotó, y subirlo 16x no cambia una
sola pieza. No hay razón para tocar los valores.

## Archivos tocados

- `src/nesting/engine/raster/masks.py` — `INFLACION_MAX_PX`, `radio_optimista`,
  `PartMasks.holgura_optimista`.
- `src/nesting/engine/raster/oracle.py` — árbitro por placa, `_search` en dos
  pasadas, `_buscar_con`, `_banda_de_contacto`, `_mejores`.
- `src/nesting/engine/raster/scoring.py` — `position_scores` separado de
  `best_position`.
- `tests/engine/raster/test_raster_oracle.py` — los dos tests nuevos.

## Autorevisión

- **¿El argumento de corrección está donde un mantenedor lo va a encontrar?**
  Sí: en el docstring de `_buscar_con`, que es adonde apunta `radio_optimista`
  desde `masks.py`, y adonde apunta el docstring de clase de `RasterOracle`.
- **¿La red de seguridad funciona de verdad?** Sí, y hay un test que la toma
  (`MAX_CANDIDATOS = 1` -> 16.00 mm en vez de 10.00, pieza colocada igual).
  En el trabajo real no se activa nunca por presupuesto, que es lo deseable.
- **¿`best_placement` sigue sin efectos secundarios?** Sí. Al árbitro sólo se le
  pregunta (`entra`) durante la búsqueda; `agregar` está únicamente en `place`.
  `test_best_placement_does_not_mutate_state` sigue pasando. Lo único que
  `_buscar_con` muta es su propio arreglo de puntajes local.
- **¿La salida de los tests está limpia?** Sí: 1021 passed, sin warnings, sin
  skips nuevos, sin tests modificados.
- Se revisó que `masks.holgura_optimista` no necesite tocar `pad` (un radio
  menor que el conservador siempre entra), tal como venía indicado.

## Preocupaciones

1. **31/5 y no 33/3.** Documentado arriba con la matriz. Creo que la
   explicación (el término de contacto, no el mecanismo) está bien sustentada,
   pero si el objetivo era el número del prototipo, la palanca es el peso del
   contacto y eso amerita su propia tarea con su propia evidencia.
2. **La banda de contacto quedó "la de siempre", no la teóricamente ideal.**
   La variante monótona sobre el rango legal (anillo ancho) es más defendible
   en el papel y empaqueta una pieza peor en el único trabajo real que tengo.
   Preferí no cambiarle el significado al término de contacto dentro de una
   tarea sobre separación. Está medido y escrito por si se quiere revisitar.
3. **`holgura_optimista` se recalcula en cada `_search`** (una dilatación por
   llamada, y `best_placement` puede llamar dos veces). No cachear fue
   indicación del brief y el trabajo real terminó más rápido que antes
   (12.4 s contra 18.7 s del conservador), así que no lo toqué; si algún día
   aparece un trabajo donde la segunda pasada se vuelva frecuente, es el
   primer lugar donde mirar.
4. El costo del árbitro crece con las piezas ya colocadas en la placa (el
   prefiltro por caja lo acota, pero no lo elimina). En una placa mucho más
   poblada que ésta, las tandas pueden empezar a pesar.
