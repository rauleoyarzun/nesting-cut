# Task 13: Interfaz de línea de comandos (`cli.py`) — Reporte

## Archivos creados / modificados

**Creados:**
- `src/nesting/cli.py` — punto de entrada `main(argv)`, siguiendo el Step 3 del brief.
- `tests/test_cli.py` — los 12 tests del Step 1 del brief, copiados literalmente.

**Modificados (fuera del alcance nominal del brief, ver "Desviaciones" abajo):**
- `src/nesting/io/dxf_reader.py` — se agregó la constante `SHEET_LAYER = "_PLACA"` y se hace que `read_dxf` ignore las entidades que están en esa capa.
- `src/nesting/io/dxf_writer.py` — `SHEET_LAYER` ahora se importa desde `dxf_reader` (fuente única) en lugar de definirse por duplicado; sigue re-exportado desde `dxf_writer` así que `from nesting.io.dxf_writer import SHEET_LAYER` (usado por `tests/io/test_dxf_writer.py`) no se rompe.

## Ciclo TDD

### Step 2: correr el test para verificar que falla

```
$ .venv/bin/pytest tests/test_cli.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 0 items / 1 error

==================================== ERRORS ====================================
______________________ ERROR collecting tests/test_cli.py ______________________
ImportError while importing test module '<repo>/tests/test_cli.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
.../importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_cli.py:4: in <module>
    from nesting.cli import main
E   ModuleNotFoundError: No module named 'nesting.cli'
=========================== short test summary info ============================
ERROR tests/test_cli.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.20s ===============================
```

Falla exactamente como predecía el brief.

### Step 3: implementación

`src/nesting/cli.py` sigue el código del brief, con dos agregados no contemplados ahí (ver más abajo): captura de `OverlappingContourError` junto a `UnknownUnitsError`/`OpenContourError`, y un comentario explícito sobre por qué `ChainingInvariantError` **no** se atrapa.

### Step 4: correr el test para verificar que pasa

Primera corrida, con la implementación tal cual el brief (sin el fix a `dxf_reader`): 11 de 12 pasan, falla `test_separation_and_margin_are_honoured`:

```
tests/test_cli.py .........F..                                           [100%]
FAILED tests/test_cli.py::test_separation_and_margin_are_honoured - assert 1 >= 6
```

Diagnóstico (ver "Desviaciones"): el test relee el propio DXF de salida con `read_dxf` + `prepare_parts`. Ese archivo trae, además de las 6 piezas, el rectángulo de la placa en la capa `_PLACA` (dibujado por `write_dxf`). Como `read_dxf` no distinguía esa capa de geometría real, `build_parts` veía un contorno exterior (la placa) conteniendo 6 contornos interiores, y los interpretaba como *agujeros* de una única pieza — de ahí `1 >= 6` en lugar de `6 >= 6`. Se corrigió `dxf_reader.py` para ignorar la capa `_PLACA` al leer (ver más abajo).

Corrida final, después del fix:

```
$ .venv/bin/pytest tests/test_cli.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>
configfile: pyproject.toml
collected 12 items

tests/test_cli.py ............                                           [100%]

============================== 12 passed in 0.44s ==============================
```

### Suite completa

```
$ .venv/bin/pytest -v
collected 214 items

tests/engine/test_packer.py .................                            [  7%]
tests/engine/test_shelf_oracle.py ..................                     [ 16%]
tests/geometry/test_chaining.py ..........................               [ 28%]
tests/geometry/test_flatten.py .......................                   [ 39%]
tests/geometry/test_nesting_tree.py ................                     [ 46%]
tests/geometry/test_transform.py ..................                      [ 55%]
tests/geometry/test_verify.py .....................                      [ 64%]
tests/io/test_dxf_reader.py ................                             [ 72%]
tests/io/test_dxf_writer.py .........                                    [ 76%]
tests/model/test_entities.py ......                                      [ 79%]
tests/model/test_material.py .....................                       [ 89%]
tests/test_cli.py ............                                           [ 94%]
tests/test_pipeline.py .........                                         [ 99%]
tests/test_smoke.py ..                                                   [100%]

============================= 214 passed in 1.34s ==============================
```

202 tests preexistentes + 12 nuevos de `test_cli.py` = 214, todos en verde.

### Step 5: prueba manual de `--help`

```
$ .venv/bin/nest --help
usage: nest [-h] -o SALIDA --material MATERIAL [--materiales MATERIALES]
            [--copias COPIAS] [--sep SEP] [--borde BORDE] [--angulos ANGULOS]
            [--sin-espejo] [--unidades {cm,ft,in,m,mm}]
            [--tol-cierre TOL_CIERRE]
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
```

Se imprimen todos los flags, en español. `nest` ya estaba disponible como script de consola (instalación editable existente, `[project.scripts] nest = "nesting.cli:main"` en `pyproject.toml`).

También se probó a mano el camino de salida 2, forzando (con un `verify` monkeypatcheado) una violación de solapamiento sobre un DXF real de 3 piezas en `mdf18`:

```
error: la verificacion geometrica encontro 1 problema(s). No se escribio ningun archivo.
  - pieza 0 y 1 se superponen (forzado para prueba manual)
exit code: 2
archivo escrito: False
```

Confirma que, ante una violación, no se escribe ningún archivo y se informa cada problema por stderr.

## Excepciones manejadas explícitamente (más allá del código del brief)

1. **`OverlappingContourError`** (`nesting.geometry.nesting_tree`, lanzada dentro de `build_parts`, que a su vez es invocada por `prepare_parts`): se atrapa junto con `UnknownUnitsError` y `OpenContourError`, con salida 1. Es un problema del dibujo del usuario (dos contornos que se superponen parcialmente en vez de anidar limpiamente).

2. **`ChainingInvariantError`** (`nesting.geometry.chaining`): deliberadamente **no** se atrapa. Se dejó un comentario en `cli.py`, justo antes del `except`, explicando que la omisión es intencional (es un bug interno de `chain_contours`, no un problema del archivo, y taparlo escribiría un DXF con geometría incompleta).

3. **`Violation(kind="invalid_geometry")`**: no requiere manejo especial — `verify()` ya devuelve esa violación en la misma lista que `overlap`/`separation`/`out_of_bounds`, y el bloque de reporte de la CLI cuenta y describe cualquier `Violation` sin distinguir por `kind`, así que ya cubre este caso sin código adicional.

## Desviaciones respecto del brief (y por qué)

1. **Se omitió el Step 6 (commit de git)**, por instrucción explícita: el proyecto no usa git.

2. **Se corrigió un defecto en `dxf_reader.py`/`dxf_writer.py`, fuera de los archivos nominales de la Task 13.**
   Motivo: el test `test_separation_and_margin_are_honoured` del propio brief relee el DXF que la CLI acaba de escribir (con `read_dxf` + `prepare_parts`) para verificar que las 6 copias efectivamente se ubicaron. Pero `write_dxf` dibuja el contorno de la placa en la capa `_PLACA` dentro del mismo modelspace que las piezas, y `read_dxf` no distinguía esa capa de geometría real. Al releer, el rectángulo de la placa (1000×1000) queda como contorno exterior de profundidad 0 y las 6 piezas colocadas adentro (profundidad 1) se interpretan como *agujeros* de una única pieza, así que `build_parts` devolvía 1 pieza en vez de 6 — esto es determinístico dado el margen configurado (toda pieza queda estrictamente adentro de su placa) y no depende de los parámetros elegidos por el test.
   Este comportamiento no es solo un problema del test: significa que alimentar la salida de la herramienta de vuelta a sí misma (para inspeccionarla, o para renestear agregando piezas nuevas) produce una lectura incorrecta en silencio. Se corrigió en la fuente (`read_dxf` ahora ignora las entidades en la capa reservada `_PLACA`, con un aviso en español si descarta alguna), en vez de debilitar el test o mockear la relectura, porque la Task 13 es explícitamente la que "cierra el circuito de punta a punta" y este es justamente un caso de ese circuito.
   Cambio quirúrgico: se agregó `SHEET_LAYER = "_PLACA"` a `dxf_reader.py` (antes solo vivía en `dxf_writer.py`) y se filtran esas entidades antes de convertirlas; `dxf_writer.py` ahora importa `SHEET_LAYER` desde `dxf_reader` en vez de duplicar el literal, para tener una única fuente de verdad. La API pública no cambió: `from nesting.io.dxf_writer import SHEET_LAYER` (usado por `tests/io/test_dxf_writer.py`) sigue funcionando porque queda re-exportado. Los 202 tests preexistentes (incluidos los de `dxf_reader` y `dxf_writer`) siguen en verde sin modificarse.

3. **Nada más cambió respecto del código del Step 3 del brief**, salvo las dos adiciones descriptas en la sección de excepciones (captura de `OverlappingContourError`, comentario sobre `ChainingInvariantError`) y usar `PackResult` como type hint explícito en `_print_summary` (cosmético, no estaba tipado en el brief).

## Códigos de salida verificados

| Código | Escenario probado |
|---|---|
| `0` | `test_happy_path_writes_the_output`, corrida manual con `mdf18` |
| `1` | material desconocido, unidades faltantes, pieza más grande que la placa, contorno abierto, lista de ángulos inválida (todos con test dedicado) + `OverlappingContourError` (sin test dedicado, pero mismo bloque `except`) |
| `2` | probado a mano con `verify` monkeypatcheado: se informan las violaciones por stderr y no se escribe el archivo |

---

## Adenda: cierre de tres huecos post-review (2026-09-18)

Se revisaron tres huecos señalados sobre `cli.py` / `dxf_reader.py`.

### Hueco 1 — aviso de la capa reservada `_PLACA`

Al leer `src/nesting/io/dxf_reader.py` se encontró que este hueco **ya estaba
cerrado**: el bloque `sheet_outlines_skipped` y el `drawing.warnings.append(...)`
correspondiente (mencionando la capa `_PLACA` y el conteo, en español) ya
existían en el archivo, agregados como parte de la Task 13 original (ver
sección "Desviaciones" arriba: la corrección de `dxf_reader.py` para el test
`test_separation_and_margin_are_honoured` incluyó ese aviso desde el principio,
aunque no había quedado documentado explícitamente en el resumen de esa
desviación). No se modificó código; se verificó a mano (ver más abajo) que el
aviso efectivamente aparece al releer un DXF escrito por la propia herramienta.

### Hueco 2 — test del código de salida 2

No existía ningún test que ejercitara la salida 2 (verificación geométrica
fallida, ningún archivo escrito). Se agregaron dos tests a `tests/test_cli.py`:

- `test_verification_failure_exits_with_two_and_writes_nothing`: parchea con
  `monkeypatch` la función `verify` tal como la importa `nesting.cli` (es
  decir, `nesting.cli.verify`, no `nesting.geometry.verify.verify` directamente)
  para que devuelva una `Violation` fabricada. Verifica: código de retorno `2`,
  el archivo de salida no existe, y el `detail` de la violación forzada aparece
  en `stderr`.
- `test_valid_layout_exits_with_zero_and_writes_the_file`: mismo layout válido
  sin parchear nada, para dejar el contraste explícito: código `0` y el archivo
  sí existe.

### Hueco 3 — test de `OverlappingContourError` en la CLI

No existía ningún test de este camino. Se agregó
`test_overlapping_contours_exit_with_one`: construye un DXF con dos
`LWPOLYLINE` cerradas — un rectángulo exterior de (0,0) a (300,300) y otro que
arranca adentro pero sobresale por un lado, de (100,100) a (350,250) — de modo
que el encadenado las toma como dos contornos y es `build_parts` (en
`nesting.geometry.nesting_tree`) el que detecta la superposición parcial y
lanza `OverlappingContourError`. Verifica código de retorno `1` y que
`"superpon"` aparezca en `stderr` (la excepción ya estaba atrapada en `cli.py`
en el mismo bloque `except` que `UnknownUnitsError`/`OpenContourError`, sin
necesidad de tocar `cli.py`).

### Punto a verificar: comentario sobre `ChainingInvariantError`

Confirmado: en `cli.py`, inmediatamente antes del bloque
`except (UnknownUnitsError, OpenContourError, OverlappingContourError)`, ya
existe un comentario explicando que `ChainingInvariantError` deliberadamente
**no** se atrapa (señala un bug interno del módulo de encadenado, no un
problema del dibujo del usuario, y debe explotar en vez de escribir un DXF con
geometría incompleta). No se lo tocó.

### Verificación

```
$ .venv/bin/pytest -q
217 passed in 1.29s
```

214 preexistentes + 3 nuevos (`test_overlapping_contours_exit_with_one`,
`test_verification_failure_exits_with_two_and_writes_nothing`,
`test_valid_layout_exits_with_zero_and_writes_the_file`) = 217, todos en verde.

Verificación manual (releer un DXF escrito por la propia herramienta):

```
cli exit code: 0
warnings al releer la salida propia:
 - se ignoraron 1 contornos de referencia de placa (capa '_PLACA', generados por este mismo programa)
```

No se modificó `dxf_reader.py` ni `cli.py`; el único archivo tocado fue
`tests/test_cli.py` (se agregaron los tres tests descriptos arriba, ninguno
existente se modificó ni se borró). No se hizo commit (el proyecto no usa
git).

---

## Adenda: seis hallazgos de robustez de la CLI (nesting, no arruinar material)

### Archivos modificados

- `src/nesting/cli.py`
  - Nueva `_validate_numeric_args`: valida `--copias >= 1`, `--sep >= 0`, `--borde >= 0`, `--tol-cierre > 0`, cada mensaje en español nombrando el flag, el valor recibido y lo esperado. Corre antes de leer el catálogo o el DXF, código de salida 1.
  - Nueva `_ArgumentParser(argparse.ArgumentParser)` que sobreescribe `error()` para salir con `EXIT_INPUT_ERROR` (1) en vez del 2 por default de argparse, con un comentario explicando que el 2 está reservado para `EXIT_VERIFICATION_FAILED`. `--help` no se tocó (sale por `_HelpAction`, no por `error()`).
  - `replicate(parts, args.copias)` ahora envuelto en `try/except ValueError` (defensa en profundidad, ya cubierto arriba por la validación pero `replicate` no debe asumirse confiable solo porque hoy tiene un único llamador).
  - La llamada a `verify(...)` ahora envuelta en `try/except ValueError`, para atrapar la nueva guarda defensiva de `verify` (ver abajo) junto con el resto de errores de entrada.
  - La escritura (`write_dxf`) ahora envuelta en `try/except OSError`, reportando la ruta y sugiriendo revisar que el directorio de destino exista (cubre `doc.saveas()` fallando con `FileNotFoundError` cuando el directorio no existe).
  - En el camino de `EXIT_VERIFICATION_FAILED` (código 2): si `args.salida` ya existía antes de la corrida, se agrega una línea a `stderr` avisando que ese archivo es de una corrida anterior y no corresponde a esta verificación fallida.

- `src/nesting/geometry/verify.py`
  - `verify()` ahora lanza `ValueError` (no una `Violation`) si `sep < 0` o `margin < 0`, con mensaje en español. Es un uso incorrecto del verificador, no un problema del layout: con `sep` negativo la comparación `distance < sep - EPS` nunca podía dispararse (la separación mínima quedaba anulada en silencio), y con `margin` negativo el "área útil" se extendía más allá de la placa física.

- `src/nesting/model/material.py`
  - `load_materials` ahora atrapa `yaml.YAMLError` (que no es subclase de `OSError` ni `ValueError`) alrededor de `yaml.safe_load`, y lo convierte en `ValueError` con mensaje en español que nombra el archivo. Antes, un YAML sintácticamente inválido (ej. un `[` sin cerrar) escapaba el `except (OSError, ValueError)` de la CLI y terminaba en traceback crudo.

- `src/nesting/io/dxf_reader.py`
  - Reescrito el aviso de la capa reservada `_PLACA`: ya no afirma que las entidades "fueron generadas por este mismo programa" (algo que `read_dxf` no verificó). Ahora dice el conteo, que la capa está **reservada** por la herramienta para los contornos de placa, que por eso se ignoró su contenido, y sugiere mover a otra capa la geometría propia si el usuario tenía algo legítimo ahí.

### Tests agregados

`tests/test_cli.py` (13 funciones nuevas, una parametrizada en 2 casos, sin tocar ninguna existente):
- `test_negative_borde_exits_with_one_and_writes_nothing`
- `test_negative_sep_exits_with_one`
- `test_non_positive_copias_exits_with_one_without_traceback` (`--copias 0` y `--copias -3`)
- `test_zero_tol_cierre_exits_with_one`
- `test_output_directory_that_does_not_exist_exits_with_one_without_traceback`
- `test_syntactically_invalid_yaml_catalogue_exits_with_one`
- `test_missing_required_flag_exits_with_one_not_two`
- `test_non_numeric_copias_exits_with_one_not_two`
- `test_help_still_exits_with_zero`
- `test_reserved_layer_warning_does_not_claim_authorship`
- `test_verification_failure_warns_about_a_pre_existing_output_file`

Nota de implementación: los errores de uso de `argparse` (flag requerido faltante, `--copias abc`) hacen que `_ArgumentParser.error()` llame `sys.exit(1)` **dentro** de `main()`, así que esos dos tests capturan `SystemExit` con `pytest.raises` en vez de leer un valor de retorno — a diferencia de la validación propia (`--borde`, `--sep`, etc.), que sí devuelve un `int` normal desde `main()`. Lo mismo para `--help` (sale con `SystemExit(0)`, sin tocarlo).

`tests/geometry/test_verify.py` (2 funciones nuevas, al final, sin tocar ninguna existente):
- `test_negative_sep_raises_value_error_instead_of_being_silently_ignored`
- `test_negative_margin_raises_value_error_instead_of_extending_the_sheet`

### Verificación

```
$ .venv/bin/pytest -q
231 passed
```

217 preexistentes + 14 nuevos (13 en `tests/test_cli.py`, contando la parametrización en 2 casos, + 2 en `tests/geometry/test_verify.py` — nota: 13 nombres de función nuevos, uno parametrizado da 2 casos, así que son 14 test cases nuevos en total en ambos archivos) = 231, todos en verde. Ningún test existente fue modificado ni borrado.

Verificación manual del caso crítico (Hallazgo 1): placa 200×200 mm, `--borde -20`, 4 copias de piezas de 90×90 mm.

```
$ .venv/bin/python -m nesting.cli /tmp/manual_check/in.dxf --material test \
    --materiales /tmp/manual_check/materials.yaml --borde -20 -o /tmp/manual_check/out.dxf
error: --borde tiene que ser >= 0, se recibio -20.0
$ echo "exit code: $?"
exit code: 1
$ ls /tmp/manual_check/out.dxf
ls: /tmp/manual_check/out.dxf: No such file or directory
```

Código de salida 1 (antes era 0 con verificación en verde y piezas colgando fuera de la placa), mensaje en español que nombra el flag `--borde`, el valor recibido y lo esperado, y ningún archivo escrito.

No se hizo commit (el proyecto no usa git).
