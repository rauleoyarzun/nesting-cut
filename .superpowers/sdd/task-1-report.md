# Task 1 report: El criterio mira el material de la última placa

## Qué se implementó

`layout_cost` pasó de devolver `tuple[int, float]` a devolver un nuevo tipo
`CostoLayout(placas: int, material_ultima: float, alto_ultima: float)`, un
`@dataclass(frozen=True, order=True)`. El desempate entre layouts con la
misma cantidad de placas ahora mira primero cuánto material de pieza queda
en la última placa (`material_ultima`, en mm²) y sólo usa el alto
(`alto_ultima`, en mm) para desempatar cuando el material es igual.

Se arreglaron los tres consumidores existentes de `layout_cost` que
indexaban o desempaquetaban el resultado como tupla:

- `src/nesting/engine/packer.py`: `_compact_last_sheet` (línea ~456) pasó de
  `layout_cost(...)[1]` a `layout_cost(...).alto_ultima`, con un comentario
  nuevo explicando por qué compara sólo el alto y no el `CostoLayout`
  entero (la compactación mueve piezas dentro de la misma placa, así que
  `material_ultima` no cambia).
- `src/nesting/cli.py:301`: `_, used_height = layout_cost(...)` →
  `used_height = layout_cost(...).alto_ultima`.
- `src/nesting_app/corredor.py:305-311`: `_, alto_usado = layout_cost(...)`
  → `costo = layout_cost(...)`, y `sobrante_mm=material.sheet_h -
  costo.alto_ultima`.

Los dos lugares en `pack()` que ya comparaban el `layout_cost` completo
(`best_cost = layout_cost(...)`, `candidate_cost = layout_cost(...)`, y el
`if candidate_cost < best_cost`) no necesitaron cambios: `order=True` hace
que la comparación de objetos siga funcionando igual que con la tupla vieja.

## Evidencia TDD

**RED** — se agregaron primero los dos tests nuevos a
`tests/engine/test_effort.py` (con las aserciones y docstrings del brief,
verbatim; sólo se adaptaron los imports y la llamada a `rect_part`, cuya
firma local en este archivo es `rect_part(part_id, w, h)` en vez de
keywords), dejando `layout_cost` sin tocar:

```
.venv/bin/python -m pytest tests/engine/test_effort.py -k "material_en_la_ultima or alto_sigue_desempatando" -v
```

```
FAILED tests/engine/test_effort.py::test_el_costo_prefiere_dejar_menos_material_en_la_ultima_placa
FAILED tests/engine/test_effort.py::test_el_alto_sigue_desempatando_con_el_mismo_material
E       AttributeError: 'tuple' object has no attribute 'alto_ultima'
E       AttributeError: 'tuple' object has no attribute 'material_ultima'
======================= 2 failed, 14 deselected in 0.97s =======================
```

Ese es exactamente el fallo esperado: `layout_cost` seguía devolviendo una
tupla plana sin esos atributos, así que los nuevos tests no podían pasar
todavía por una razón ajena a la lógica del desempate.

**GREEN** — tras implementar `CostoLayout` y actualizar `layout_cost` y sus
tres consumidores:

```
.venv/bin/python -m pytest tests/engine/test_effort.py -k "material_en_la_ultima or alto_sigue_desempatando" -v
```

```
tests/engine/test_effort.py ..                                           [100%]
======================= 2 passed, 14 deselected in 0.81s =======================
```

```
.venv/bin/python -m pytest tests/engine/test_effort.py -v
```

```
tests/engine/test_effort.py ................                             [100%]
============================= 16 passed in 39.00s ==============================
```

## Suite completa

```
.venv/bin/python -m pytest -q
```

pytest 9.1.1 en este entorno no imprime la línea final de resumen
(`N passed in Xs`) al correr la suite completa — es una rareza previa del
entorno, no de este cambio: incluso corriendo `-p no:warnings` o con
`--collect-only`, esa última línea nunca aparece, pero sí aparecen todos
los `.` de progreso, `[100%]`, y el código de salida es `0`. Para verificar
sin depender de esa línea:

- Conteo de tests colectados por archivo (`pytest --collect-only -q`,
  sumando la columna de conteo por archivo): **1009**, contra el baseline
  de 1007 + 2 tests nuevos = 1009. Coincide exactamente.
- `grep -c "\[100%\]"` sobre la salida de `-q`: 1 (llegó al final).
- Conteo de caracteres `.` de progreso en la salida: 1009 (ningún `F` ni
  `E`, es decir cero fallos y cero errores).
- Código de salida del proceso `pytest`: `0`.

Con esas cuatro señales cruzadas (1009 recolectados, 1009 puntos verdes,
cero F/E, exit 0) doy la suite completa por verde: 1007 + 2 = 1009,
todos pasando.

## Archivos modificados

- `src/nesting/engine/packer.py` — nueva clase `CostoLayout`, `layout_cost`
  reescrita para devolverla, `_compact_last_sheet` actualizado.
- `src/nesting/cli.py` — `_print_summary` usa `.alto_ultima`.
- `src/nesting_app/corredor.py` — `acomodar` usa `.alto_ultima`.
- `tests/engine/test_effort.py` — imports nuevos (`PackResult`, `Transform`,
  `Placement`), dos tests nuevos del brief, y las líneas existentes que
  indexaban (`[0]`) o desempaquetaban por tupla (`sheets, height = ...`,
  `_, last_height = ...`) migradas a acceso por atributo.

## Autorevisión

- Todo lo del brief está implementado; nada extra (no toqué ninguna otra
  lógica de `pack()` ni de `_compact_last_sheet` más allá de la línea de
  comparación indicada).
- Los tres consumidores de `layout_cost` fuera de `packer.py` (cli.py,
  corredor.py) y todos los sitios en `test_effort.py` que indexaban la
  tupla fueron encontrados con `grep -rn "layout_cost" src tests` y
  corregidos; confirmé con un segundo `grep` tras el cambio que no queda
  ningún `[0]`/`[1]` ni desempaquetado posicional sobre `layout_cost(...)`.
  Nota: dos líneas que el brief mencionaba como indexadas (`:179`, `:209`)
  ya no indexaban en el archivo actual (guardan el `CostoLayout` completo
  en un dict) — drift de líneas del plan, no un caso real a arreglar, tal
  como anticipaba la decisión 1 del pedido.
- Los tests nuevos verifican comportamiento real: construyen dos
  `PackResult` con geometría explícita y comprueban que el desempate elige
  el de menor material en la última placa incluso cuando el alto favorece
  al otro (el caso exacto de `NESTING 2.ai`), y que con material igual el
  alto sigue desempatando. No restablecen la implementación, ejercitan la
  geometría real vía `transformed_bbox`.
- Sin warnings nuevos ni ruido: la salida de `test_effort.py -v` es
  limpia (16 passed, sin warnings).

## Concerns

Ninguno sobre el código de este task. Como observación aparte (no bloquea
nada): `pytest -q` no imprime su línea de resumen final al correr la suite
completa en este entorno (pytest 9.1.1), algo que ya existía antes de este
cambio y no tiene relación con `layout_cost`; lo dejo anotado por si afecta
a otros tasks de esta serie que necesiten leer esa línea para verificar.
