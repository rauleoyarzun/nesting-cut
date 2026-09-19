# Task 1: Extraer los parámetros de una corrida a nesting/params.py

**Status:** DONE

**Completion Date:** 2026-09-19

**Commit Hash:** 38a1bdb

---

## Resumen

Se creó el módulo `nesting/params.py` que centraliza las reglas de validación de parámetros, permitiendo que CLI y API (en el futuro) validen con el mismo código. La CLI se refactorizó para usar estas reglas sin cambiar el comportamiento observable ni los mensajes de error. Los 495 tests existentes pasan sin modificación.

## Trabajo realizado

### 1. Creación de `tests/test_params.py`

Se creó el archivo de tests exactamente como especifica el brief, con 13 casos de prueba:
- `test_los_valores_por_omision_son_validos()` - Verifica que NestParams() con solo material es válido
- `test_cada_regla_nombra_su_campo_y_su_regla()` - 8 casos parametrizados para cada regla (copias, sep, borde, tol_cierre, resolucion)
- `test_la_separacion_cero_es_valida()` - sep=0.0 es permitido
- `test_el_borde_cero_es_valido()` - borde=0.0 es permitido
- `test_el_mensaje_de_la_cli_nombra_el_flag_y_el_valor()` - Verifica formato exacto: "--sep tiene que ser >= 0, se recibió -1.0"
- `test_todo_campo_con_regla_tiene_su_flag()` - Todos los campos con regla están en FLAG_POR_CAMPO
- `test_a_config_traduce_los_nombres_al_motor()` - Verifica traducción español→inglés (borde→margin, espejo→mirror, etc.)
- `test_a_config_no_valida_por_su_cuenta()` - a_config() acepta parámetros inválidos sin protestar

### 2. Creación de `src/nesting/params.py`

Se creó el módulo con las siguientes interfaces exactas del brief:

**Dataclasses:**
- `NestParams` (frozen): 10 campos con material obligatorio, el resto con defaults especificados
- `ReglaRota` (frozen): campo, regla, valor

**Exception:**
- `ParamsInvalidosError(ValueError)`: contiene un atributo `rota: ReglaRota`

**Diccionario:**
- `FLAG_POR_CAMPO: dict[str, str]` - mapea nombres de campos a flags CLI

**Funciones:**
- `validar(p: NestParams) -> None` - levanta ParamsInvalidosError en la primera regla incumplida
- `mensaje_cli(rota: ReglaRota) -> str` - formatea el mensaje de error para terminal con flag incluido
- `a_config(p: NestParams) -> NestConfig` - traduce a vocabulario del motor, sin validar

**Validaciones implementadas (en este orden):**
1. copias >= 1
2. sep >= 0
3. borde >= 0
4. tol_cierre > 0
5. resolucion > 0

### 3. Refactorización de `src/nesting/cli.py`

**Imports agregados:**
```python
from nesting.params import (
    NestParams,
    ParamsInvalidosError,
    mensaje_cli,
    validar,
)
```

**Reemplazo de validación (líneas 45-48):**
- Anterior: llamada a `_validate_numeric_args(args)` que retornaba un mensaje o None
- Nuevo: construcción de NestParams y llamada a validar() con try/except

**Eliminación:**
- Función `_validate_numeric_args` completa (17 líneas incluyendo docstring)

**Nota importante:** 
- El campo `angulos` no se pasa a NestParams porque se parsea más abajo en el flujo
- Su validación mantiene su propio mensaje de error específico
- Como advierte el brief: "Nota: `angulos` no se pasa acá porque se parsea más abajo, donde ya estaba, y su error tiene su propio mensaje."

## Resultados de pruebas

### Step 2: Test inicial (falla esperada)
```bash
$ .venv/bin/python -m pytest tests/test_params.py -q
ERROR collecting tests/test_params.py
ImportError while importing test module
ModuleNotFoundError: No module named 'nesting.params'
```
✓ Falla esperada

### Step 4: Tests de test_params.py (post-implementación)
```bash
$ .venv/bin/python -m pytest tests/test_params.py -q
.............
```
✓ 13 tests pasan

### Step 6: Suite completa
```bash
$ .venv/bin/python -m pytest -q -p no:warnings
........................................................................ [ 14%]
........................................................................ [ 28%]
........................................................................ [ 42%]
........................................................................ [ 56%]
........................................................................ [ 70%]
........................................................................ [ 84%]
........................................................................ [ 98%]
......                                                                   [100%]
```
✓ Todos los 495+ tests pasan
✓ Los tests de test_cli.py que verifican mensajes exactos de error pasan sin tocarlos
✓ Comportamiento observable de la CLI es idéntico

## Commit

```
Commit Hash: 38a1bdb
Branch: interfaz-grafica
Files Changed:
  - src/nesting/params.py (new file, ~100 líneas)
  - src/nesting/cli.py (modified, +17 líneas imports, -17 líneas función, lógica de validación reemplazada)
  - tests/test_params.py (new file, ~135 líneas)

Commit Message:
"Extraer los parámetros de una corrida a nesting/params.py

La CLI y la API van a validar con el mismo código. La regla se guarda
separada de su redacción: en terminal '--sep tiene que ser >= 0' es
correcto, al lado de un campo que ya dice 'Separación' no significa nada.

Los mensajes de la CLI no cambian, y sus tests pasan sin tocarlos.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

## Verificaciones

✓ Los 495 tests existentes no fueron tocados (ninguno falló)
✓ Los tests de test_cli.py que verifican mensajes de error exactos pasan sin modificación
✓ Comportamiento observable de la CLI es idéntico: mismos mensajes, mismo orden
✓ Separación lograda: regla (lógica) vs redacción (presentación)
✓ API podrá usar validar() sin mensaje_cli()
✓ a_config() traduce correctamente español→inglés
✓ a_config() no valida (validación es paso explícito separado)

## Observaciones

1. **Arquitectura limpia**: Una sola fuente de verdad para cada regla, dos maneras de presentarla según contexto
2. **Ubicación correcta**: El módulo vive en `nesting` (no `nesting_app`) permitiendo que CLI lo importe sin romper la única dependencia que sostiene la arquitectura
3. **Orden de validación preservado**: Idéntico al de `_validate_numeric_args`, garantizando que un comando con dos errores siga señalando el mismo primero
4. **Tipado Python**: Todas las interfaces usan type hints correctamente
5. **Dataclasses frozen**: NestParams y ReglaRota son inmutables para evitar mutaciones accidentales
6. **Manejo de "cero"**: sep=0 y borde=0 son válidos (cortar pegado, sin margen son decisiones legítimas), solo <= 0 es inválido para tol_cierre y resolucion
