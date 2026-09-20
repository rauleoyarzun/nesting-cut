# Informe — Task 14: Banco de pruebas (`bench/`)

## Archivos creados

- `bench/make_sample.py` — generador de la muestra sintética (`write_sample`).
- `bench/run_bench.py` — corredor del banco (`BenchResult`, `run_one`, `main`).
- `bench/README.md` — instrucciones de uso y de carga de los archivos reales.
- `tests/test_bench.py` — 5 tests sobre el generador y el corredor.
- `bench/files/muestra.dxf` — muestra generada por `make_sample.py` (Step 6).
- `bench/files/banqueta.ai` — copiado desde `~/Downloads/` (paso extra).
- `bench/files/banqueta.3dm` — copiado desde `~/Downloads/` (paso extra).

Todos los archivos siguen el contenido exacto del brief (`task-14-brief.md`, Steps 1-4),
sin modificaciones: las interfaces consumidas (`read_dxf`, `prepare_parts`, `pack`,
`replicate`, `ShelfOracle`, `NestConfig`, `load_materials`, `DEFAULT_MATERIALS_PATH`,
`Material`, `verify`) coinciden en firma con el código actual del proyecto, verificado
por lectura directa antes de escribir. `PackResult` no tiene campo `unplaced` y el
brief tampoco lo usa, así que no hubo que tocar nada por esa salvedad.

## `banqueta.cdr`

No se copió: es formato binario cerrado de Corel y no se puede leer ni mover a un
lugar donde el banco lo procesaría por error (el banco solo mira `*.dxf`, así que
tampoco haría falta). Queda pendiente de que el usuario lo exporte a DXF a mano desde
CorelDRAW, como indica `bench/README.md`.

## Paso extra: `.ai` y `.3dm` en `bench/files/`

Copiados tal cual desde `<descargas>/`. Se confirmó que `run_bench.py` los
ignora (usa `FILES_DIR.glob("*.dxf")`) corriendo el banco con ambos archivos ya
presentes: la tabla de salida no cambió, sin errores ni advertencias.

## Step 5 — Tests del banco

Comando: `.venv/bin/pytest tests/test_bench.py -v`

```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 5 items

tests/test_bench.py .....                                                [100%]

============================== 5 passed in 0.41s ===============================
```

Coincide con lo esperado por el brief: `5 passed`.

## Step 6 — Generar la muestra y correr el banco

Comandos:
```
.venv/bin/python bench/make_sample.py
.venv/bin/python bench/run_bench.py
```

Salida:
```
escrito bench/files/muestra.dxf
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
muestra.dxf             shelf          12       1    13.6%     0.0
```

**Línea de base del motor trivial (`ShelfOracle`): 12 piezas, 1 placa, 13.6% de
aprovechamiento, ~0.0 s.** Sin marca `VIOLACIONES!`.

Este número coincide, en el mismo orden de magnitud y prácticamente exacto, con el
dato de referencia dado (13.6% sobre un DXF sintético similar de 12 piezas curvas y
cóncavas). Confirma que el generador está produciendo geometría representativa del
desperdicio que el motor raster tendrá que cerrar en el hito 3.

Se corrió una segunda vez después de copiar `.ai`/`.3dm` a `bench/files/`, para
confirmar que no rompen la corrida: misma tabla, mismo resultado.

## Step 7 — Suite completa

Comando: `.venv/bin/pytest`

```
========================= test session starts =========================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 236 items

........................................................................ [ 30%]
........................................................................ [ 61%]
........................................................................ [ 91%]
....................                                                     [100%]

============================== 236 passed in 1.51s ==============================
```

236 = 231 preexistentes + 5 nuevos de `tests/test_bench.py`. Todo en verde.

## Step 8 — Commit

**Omitido a pedido explícito**: el proyecto no usa git por decisión del usuario.

## Desviaciones respecto del brief

Ninguna en el código de `bench/` ni en los tests: se copiaron literalmente los
bloques de código del brief. Las únicas adiciones fuera del brief son las pedidas
aparte por el usuario:

1. Copia de `banqueta.ai` y `banqueta.3dm` a `bench/files/`
   (sus lectores llegan en tasks posteriores; no afectan la corrida actual).
2. `banqueta.cdr` no se copió ni se procesó, por ser formato binario
   cerrado — requiere exportación manual a DXF, tal como documenta
   `bench/README.md`.
3. Se omitió el Step 8 (commit de git) por instrucción explícita.

## Estado

**DONE.** Los 236 tests pasan, el banco corre de punta a punta sobre `muestra.dxf`
sin violaciones, y la línea de base (12 piezas, 1 placa, 13.6% de aprovechamiento,
~0.0 s) queda registrada para medir la mejora del motor raster en el hito 3.

---

# Adenda — Corrección de 4 hallazgos del banco (2026-09-18)

Se corrigieron los 4 hallazgos reportados sobre `bench/run_bench.py` y `bench/README.md`,
sin tocar ninguno de los 5 tests originales de `tests/test_bench.py`.

## Hallazgo 1 — Aislamiento por archivo

`main` ahora envuelve cada llamada a `run_one` en un `try/except` sobre una tupla
`FILE_ERRORS = (UnknownUnitsError, OpenContourError, OverlappingContourError,
PartTooLargeError, OSError, ValueError)`. Si un archivo falla por alguna de esas
razones, se imprime una fila `ERROR` con el nombre del archivo y el motivo, y la
corrida sigue con el resto. `ChainingInvariantError` queda deliberadamente fuera de
la tupla (comentario explícito en el código) y propaga sin atraparse. El código de
salida de `main` es `1` si algún archivo falló, `0` si todos midieron bien.

Se eligió dejar que `run_one` siga lanzando excepciones tal cual (documentado en su
docstring) y manejar el aislamiento solo en `main`, en vez de agregar un campo
`error` a `BenchResult`.

## Hallazgo 2 — Flag `--unidades`

Se agregó `--unidades` a `run_bench.py` con las mismas opciones que la CLI principal
(`choices=sorted(UNIT_SCALES)`), pasado a `read_dxf` como `units_override` a través de
un nuevo parámetro `units` en `run_one`.

## Hallazgo 3 — README

Los dos comandos de la sección "Uso" ahora usan `.venv/bin/python` (antes el primero
decía `python bench/make_sample.py`). Se agregó una nota explícita de que el banco
hoy solo lee `.dxf`, que `--unidades mm` es la forma correcta de resolver un DXF sin
unidades desde el banco (no un flag inexistente), y que `.ai`/`.3dm` ya están copiados
en `bench/files/` esperando sus lectores (hito 5, Tasks 22 y 23).

## Hallazgo 4 — Un solo reloj

Se eliminó el `time.perf_counter()` propio de `run_one`; ahora usa `result.seconds`
de `PackResult` directamente. El docstring del campo `seconds` de `BenchResult`
documenta que mide solo el empaquetado (`pack()`), sin lectura del DXF ni
`prepare_parts`, y por qué eso es lo que interesa medir (cubre reintentos futuros del
empaquetador).

## Tests agregados (10 en total en `tests/test_bench.py`, 5 nuevos)

1. `test_a_corrupt_file_does_not_abort_the_run` — carpeta con un DXF corrupto que
   ordena antes que uno válido: la corrida informa el `ERROR` y sigue midiendo el
   válido (verifica piezas y placas del válido en la salida).
2. `test_a_dxf_without_declared_units_is_reported_as_an_error` — DXF con
   `$INSUNITS = 0`: se informa como error de archivo, no aborta la corrida.
3. `test_the_same_file_measures_once_units_are_given` — mismo DXF, con
   `--unidades mm`: ahora mide sin error.
4. `test_run_one_lets_chaining_invariant_errors_through` — parchea
   `nesting.pipeline.chain_contours` para lanzar `ChainingInvariantError` y verifica
   con `pytest.raises` que `run_one` no la atrapa.
5. `test_run_one_reports_the_seconds_from_pack_result` — parchea `run_bench.pack`
   para devolver un `PackResult` con `seconds` reconocible (`12345.678`) y verifica
   que `run_one` lo propaga sin recalcularlo.

## Verificación

**1. Suite completa:**

```
$ .venv/bin/pytest
241 passed in 1.56s
```

(236 preexistentes, sin tocar, + 5 nuevos de esta adenda.)

**2. Comandos del README, copiados y pegados tal cual quedaron:**

```
$ .venv/bin/python bench/make_sample.py
escrito bench/files/muestra.dxf

$ .venv/bin/python bench/run_bench.py
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
muestra.dxf             shelf          12       1    13.6%     0.0
```

**3. `--copias 6`:**

```
$ .venv/bin/python bench/run_bench.py --copias 6
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
muestra.dxf             shelf          72       2    40.7%     0.0
```

72 piezas, 2 placas, 40.7% — igual que antes de los cambios.

**4. Aislamiento por archivo, carpeta con 1 DXF válido + 1 corrupto**
(`corrupto.dxf` ordena antes que `muestra.dxf`, apuntando `FILES_DIR` a una carpeta
temporal vía monkeypatch, igual que en el test 1):

```
stdout:
archivo                 motor      piezas  placas   aprov.     seg
------------------------------------------------------------------
corrupto.dxf            ERROR     OSError: File '.../corrupto.dxf' is not a DXF file.
muestra.dxf             shelf          12       1    13.6%     0.0

stderr:
1 de 2 archivo(s) no se pudieron medir (ver las filas ERROR arriba).
(codigo de salida: 1)
```

El archivo corrupto se informa como `ERROR` sin abortar, el archivo válido se sigue
midiendo con sus números normales, y el código de salida distingue la corrida
parcialmente fallida.

## Estado

**DONE.** Los 4 hallazgos quedaron corregidos, los 5 tests originales no se tocaron,
se agregaron los 5 tests pedidos, y las 4 verificaciones del enunciado se ejecutaron
con éxito.
