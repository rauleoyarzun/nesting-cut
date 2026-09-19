# Tarea 21 — informe de implementación

## Estado

Completa. Hito 4 cerrado: la CLI expone la tabla de flags completa (`--esfuerzo`,
`--preview`, y la validación de `--resolucion` que faltaba), y el resumen por
pantalla informa el sobrante útil de la última placa reusando `layout_cost`.

## Archivos modificados

- `src/nesting/cli.py`
  - Import de `EFFORT_RESTARTS` y `layout_cost` desde `nesting.engine.packer`,
    `write_preview` desde `nesting.io.preview`, `Material` desde
    `nesting.model.material` y `Part` desde `nesting.model.part`.
  - `NestConfig(...)` ahora pasa `effort=args.esfuerzo`.
  - Nuevos flags `--esfuerzo` (`choices=sorted(EFFORT_RESTARTS)`, default
    `"normal"`) y `--preview` (`Path`, default `None`).
  - Después de `write_dxf`, si `args.preview` fue dado, se llama a
    `write_preview(...)` envuelta en `try/except ValueError` — reportada como
    error de entrada (código 1) en vez de dejar que se propague, por el caso
    de un lienzo demasiado grande.
  - Nueva función `_colors_by_part(drawing, parts)` (helper para la vista
    previa, igual que en el brief).
  - `_print_summary` reescrita: recibe `parts` y `material`, calcula
    `_, used_height = layout_cost(result, parts)`, deriva
    `free_height = material.sheet_h - used_height` y agrega la línea de
    "sobrante util" en la última placa cuando ese sobrante supera 100 mm.
  - `_validate_numeric_args` gana una rama `--resolucion` (rechaza valores
    `<= 0`), en línea con las validaciones ya existentes de `--copias`,
    `--sep`, `--borde` y `--tol-cierre`. No estaba en el brief tal cual porque
    el brief no conocía todavía esa validación existente; se agregó por
    pedido explícito de la consigna.
- `tests/test_cli_full.py` (nuevo) — los 11 tests del brief más
  `test_resolution_must_be_positive` (agregado para cubrir la validación de
  `--resolucion` recién descripta).

## Desviaciones respecto del brief

- **`--resolucion` ya existía** en la CLI antes de esta tarea (el brief lo
  listaba como flag a agregar); solo se agregó su validación de rango.
- **`EFFORT_RESTARTS` no se tocó**: se usó tal cual estaba calibrado
  (`{"rapido": 1, "normal": 3, "lento": 12}`).
- **Se agregó un test extra** (`test_resolution_must_be_positive`) no
  presente en el brief, para cubrir la nueva validación pedida por la
  consigna actualizada.
- **Se omitió el Paso 9 del brief** (commit de git): el proyecto no usa git,
  según indicación explícita de la consigna.

## Ciclo TDD

### Paso 2 — correr el test antes de implementar (falla)

`tests/test_cli_full.py` se escribió primero (los 11 casos del brief + el
caso de validación de `--resolucion`). Salida de
`.venv/bin/pytest tests/test_cli_full.py -v` contra el código viejo:

```
FAILED tests/test_cli_full.py::test_every_effort_level_runs[rapido] - SystemExit: 1
FAILED tests/test_cli_full.py::test_every_effort_level_runs[normal] - SystemExit: 1
FAILED tests/test_cli_full.py::test_every_effort_level_runs[lento] - SystemExit: 1
FAILED tests/test_cli_full.py::test_preview_writes_a_png - SystemExit: 1
FAILED tests/test_cli_full.py::test_the_summary_reports_the_usable_offcut - AssertionError
FAILED tests/test_cli_full.py::test_resolution_must_be_positive - ZeroDivisionError: float division by zero
FAILED tests/test_cli_full.py::test_the_help_lists_every_flag - AssertionError: assert '--esfuerzo' in '...'
=========================== short test summary info ============================
7 failed, 5 passed in 14.16s
```

Confirma lo esperado: `--esfuerzo` y `--preview` no reconocidos, y
`--resolucion 0` provoca una división por cero cruda en vez de un error de
entrada prolijo.

### Paso 6 — correr el test después de implementar (pasa)

```
$ .venv/bin/pytest tests/test_cli_full.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 12 items

tests/test_cli_full.py ............                                      [100%]

============================= 12 passed in 17.10s ==============================
```

### Paso 8 — suite completa

```
$ .venv/bin/pytest
...
359 passed, 2 warnings in 130.54s (0:02:10)
```

(Las 2 advertencias son `DeprecationWarning` preexistentes de Pillow en
`tests/io/test_preview.py`, sin relación con esta tarea.)

## `--help`

```
usage: nest [-h] -o SALIDA --material MATERIAL [--materiales MATERIALES]
            [--copias COPIAS] [--sep SEP] [--borde BORDE] [--angulos ANGULOS]
            [--sin-espejo] [--unidades {cm,ft,in,m,mm}]
            [--tol-cierre TOL_CIERRE] [--resolucion RESOLUCION]
            [--esfuerzo {lento,normal,rapido}] [--preview PREVIEW]
            entrada

Acomoda figuras vectoriales dentro de placas, minimizando el material.

positional arguments:
  entrada               archivo DXF de entrada

options:
  -h, --help            show this help message and exit
  -o, --salida SALIDA   archivo DXF de salida
  --material MATERIAL   clave del catalogo de materiales
  --materiales MATERIALES
                        ruta del catalogo de materiales (default: el que viene
                        con el programa)
  --copias COPIAS       cuantas veces repetir todo el contenido del archivo
  --sep SEP             separacion minima entre piezas, en mm
  --borde BORDE         margen contra el borde de la placa, en mm
  --angulos ANGULOS     angulos candidatos, separados por coma
  --sin-espejo          no permitir piezas espejadas
  --unidades {cm,ft,in,m,mm}
                        unidades del archivo de entrada, si no las declara
  --tol-cierre TOL_CIERRE
                        tolerancia para unir extremos de contornos, en mm
  --resolucion RESOLUCION
                        resolucion del raster, en mm por pixel
  --esfuerzo {lento,normal,rapido}
                        cuanto tiempo dedicarle a mejorar el resultado
  --preview PREVIEW     ruta del PNG de previsualizacion a generar
```

## Prueba manual sobre la muestra del banco

Se usó `--esfuerzo rapido` (no `normal`) por el aviso de tiempos: `normal`
tarda ~3 minutos con esta muestra y `--copias 4`; para verificar que los
flags funcionan y que el preview sale bien, `rapido` alcanza.

```
$ .venv/bin/nest bench/files/muestra.dxf --material mdf18 --copias 3 --sep 6 \
    --borde 10 --esfuerzo rapido --preview /tmp/vista.png -o /tmp/resultado.dxf

Previsualizacion en /tmp/vista.png
Placa 1/1   aprovechamiento  40.7%   <- sobrante util ~1830x675 mm
----------------------------------
36 piezas - 1 placas - 40.7% total - 59.2s
Escrito en /tmp/resultado.dxf
```

Tiempo real de la corrida (`time`): 59.2 s reportados por la propia CLI,
1:00.25 de reloj de pared total incluyendo el arranque del intérprete.

Ambos archivos de salida se escribieron (`/tmp/resultado.dxf` y
`/tmp/vista.png`). Se abrió `/tmp/vista.png`: las 36 piezas (12 formas en T +
12 círculos + resto, tras `--copias 3`) están acomodadas de forma entrelazada
— las piezas en T se intercalan en distintas rotaciones/espejados, apoyadas
unas contra otras, y los círculos rellenan los huecos que quedan abajo — no
apiladas en filas simples. El renglón de la única placa usada muestra el
sobrante útil (`~1830x675 mm`), coherente con el 40.7% de aprovechamiento.

## Notas de diseño

- `_print_summary` reusa `layout_cost(result, parts)` en vez de recalcular la
  altura ocupada de la última placa — es la misma función que ya usa `pack()`
  internamente para comparar layouts, así que la cifra que ve el usuario es
  exactamente la misma que usa el motor para decidir cuál orden de inserción
  es mejor.
- El umbral de 100 mm para mostrar la línea de "sobrante util" viene del
  brief tal cual; no se le encontró justificación numérica adicional en el
  código existente, así que se dejó sin cambios.
- `write_preview` puede lanzar `ValueError` cuando la escala pedida
  produciría un lienzo mayor a `MAX_CANVAS_PIXELS` (guard de Pillow); ese
  `ValueError` ahora se atrapa en `main` y se reporta como
  `error: ...` por `stderr` con código de salida 1, igual que el resto de los
  errores de entrada — nunca deja explotar la excepción cruda.

---

## Addendum — corrección de 3 hallazgos de code review (2026-09-18)

### Estado

Completo. Suite completa: 362 passed, 0 failed (359 previos + 3 tests nuevos).
No se borró ningún test existente; se ajustó una aserción vacía (Hallazgo 3)
y se agregaron 3 tests nuevos al final de `tests/test_cli_full.py`.

### Hallazgo 1 (CRÍTICO) — traza cruda al escribir la previsualización

`src/nesting/cli.py`: el bloque que llama a `write_preview` solo atrapaba
`ValueError`. Se agregó `OSError` a la misma cláusula `except`, y se cambió
el mensaje para nombrar la ruta y el motivo, en la misma línea que el resto
de los errores de entrada/salida de `main` (p. ej. la escritura del DXF):

```python
except (ValueError, OSError) as error:
    print(
        f"error: no se pudo escribir la previsualizacion en "
        f"{args.preview}: {error}",
        file=sys.stderr,
    )
    return EXIT_INPUT_ERROR
```

### Hallazgo 2 (IMPORTANTE) — `--preview` creaba directorios en silencio

`src/nesting/io/preview.py`: se sacó la línea
`Path(path).parent.mkdir(parents=True, exist_ok=True)` de `write_preview`.
Ahora, si el directorio padre no existe (o es un archivo), `Image.save`
lanza `OSError`/`NotADirectoryError`, que se propaga y queda atrapado por el
fix del Hallazgo 1 en `cli.py`. Se revisó `tests/io/test_preview.py` y
`tests/test_cli_full.py`: ningún test existente dependía de la creación
automática de directorios (todos usan `tmp_path` con el padre ya existente),
así que no hubo que adaptar ningún test viejo.

### Hallazgo 3 (MENOR) — aserción vacía

`tests/test_cli_full.py::test_the_summary_reports_parts_sheets_and_time`:
`assert "s" in output` no verificaba nada (cualquier texto en español
contiene una "s"). Se revisó el formato real que imprime `_print_summary`
(`f"... - {result.seconds:.1f}s"`, p. ej. `"12 piezas - 1 placas - 40.7%
total - 0.1s"`) y se cambió por:

```python
assert re.search(r"\d+\.\d+s", output), (
    f"no se encontro un tiempo en segundos (ej. '0.1s') en: {output!r}"
)
```

### Tests nuevos (al final de `tests/test_cli_full.py`)

- `test_preview_whose_parent_is_a_file_exits_with_one_without_traceback`:
  crea un archivo regular como "directorio" padre de `--preview`, corre la
  CLI y verifica código 1, la ruta en `stderr`, ausencia de "Traceback" y
  que el archivo de preview no se creó.
- `test_preview_in_a_missing_directory_exits_with_one_and_does_not_create_it`:
  `--preview no_existe/vista.png` (directorio inexistente) → código 1,
  mensaje con la ruta, sin traza, y — a diferencia del comportamiento
  anterior — el directorio padre **no** se crea.
- `test_preview_with_a_valid_path_still_writes_the_png`: camino feliz sin
  cambios, para confirmar que el fix no rompió la escritura normal de la
  previsualización.

### Verificación manual del Hallazgo 1

Reproducción del caso del brief (archivo regular bloqueando el directorio
del `--preview`), corrida a mano contra el binario real vía
`python -m nesting.cli`:

```
$ touch bloqueador
$ python -m nesting.cli entrada.dxf --material test --materiales m.yaml \
      -o salida.dxf --preview bloqueador/vista.png --esfuerzo rapido
error: no se pudo escribir la previsualizacion en bloqueador/vista.png: [Errno 20] Not a directory: 'bloqueador/vista.png'
EXIT CODE: 1
```

Sin traceback, código de salida 1, mensaje en español con la ruta y el
motivo. (En macOS el error de sistema es `NotADirectoryError` en vez del
`FileExistsError` de Linux que aparece en el repro del brief — ambos son
subclases de `OSError`, así que el mismo `except` los atrapa igual.)

### Resultado de la suite completa

```
362 tests, 0 errors, 0 failures, 0 skipped  (via --junitxml, pytest 9.1.1)
```

(Nota: en este entorno, `pytest -q` no imprime la línea final de resumen
"N passed in Ys" — corte de la última línea de la salida capturada, no
relacionado con estos cambios; el conteo exacto se confirmó con
`--junitxml`.)

Archivos modificados:
- `/Users/raulo/cut-placement/src/nesting/cli.py`
- `/Users/raulo/cut-placement/src/nesting/io/preview.py`
- `/Users/raulo/cut-placement/tests/test_cli_full.py`
