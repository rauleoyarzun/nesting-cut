# Task 3 Report: El árbitro exacto

## What Was Implemented

Created two new files implementing the exact collision arbiter:

1. **`tests/engine/test_exact.py`** (73 lines)
   - Complete test suite with all six tests from the brief
   - Tests cover: borde (margin) validation, exact separation measurement, out-of-bounds detection, cleanup, and concave polygon handling
   - All docstrings and comments preserved verbatim from the brief

2. **`src/nesting/engine/exact.py`** (84 lines)
   - `ArbitroExacto` class implementing exact collision detection on polygon geometry
   - Key features:
     - Margin validation against sheet boundaries (uses EPS tolerance)
     - Exact separation measurement using Shapely polygon distance
     - Bounding-box prefilter optimization to avoid expensive distance calculations
     - Support for complex shapes with holes (concave polygons)
   - Uses `placed_polygon()` from `verify.py` and `Transform` from model entities
   - Uses same `EPS = 1e-6` value as `verify.py` to ensure consistency

## TDD Evidence

### RED Phase - Initial Test Run
```bash
.venv/bin/python -m pytest tests/engine/test_exact.py -v
```

**Expected Failure:**
```
ERROR collecting tests/engine/test_exact.py
ImportError while importing test module
ModuleNotFoundError: No module named 'nesting.engine.exact'
```
✓ Failed as expected at import time (module did not exist yet).

### GREEN Phase - Tests Pass
```bash
.venv/bin/python -m pytest tests/engine/test_exact.py -v
```

**Result:**
```
============================= test session starts ==============================
collected 6 items

tests/engine/test_exact.py ......                                        [100%]

============================== 6 passed in 0.08s ===============================
```
✓ All six tests pass immediately after implementation.

## Full Suite Result

```bash
.venv/bin/python -m pytest -p no:warnings
```

**Result:**
```
1018 passed in 224.94s (0:03:44)
```

✓ Baseline: 1012 tests
✓ New tests: 6 tests  
✓ Expected: 1012 + 6 = 1018 ✓

## Files Changed

- **Created:** `src/nesting/engine/exact.py` (84 lines)
- **Created:** `tests/engine/test_exact.py` (73 lines)
- **Total:** 157 new lines

No modifications to existing files.

## Self-Review Findings

### Code Integrity
- ✓ Both files transcribed exactly from the brief, character-for-character
- ✓ All six tests present with complete docstrings
- ✓ All comments and docstrings explain *why*, not *what* (per project convention)
- ✓ No extra code, no YAGNI violations

### Consistency
- ✓ `EPS = 1e-6` matches `verify.py` exactly (critical for arbiter/verifier alignment)
- ✓ Uses `placed_polygon(part, Transform(...))` correctly
- ✓ Spanish user-facing strings use correct accentuation and ñ

### Test Coverage
- ✓ `test_una_pieza_sola_entra_si_respeta_el_borde` - margin validation
- ✓ `test_una_pieza_pisada_contra_el_borde_no_entra` - strict margin enforcement (9.9 != 10)
- ✓ `test_la_separacion_se_mide_exacta_ni_un_pelo_menos` - exact separation at EPS boundary
- ✓ `test_una_pieza_que_se_sale_por_arriba_no_entra` - y-axis margin check
- ✓ `test_limpiar_olvida_todo_lo_colocado` - state clearing works
- ✓ `test_una_pieza_puede_entrar_en_el_agujero_de_otra` - concave polygon support (holes)

### Test Output Quality
- ✓ Zero warnings (clean pytest output)
- ✓ Fast execution (6 tests in 0.08s)

## Concerns

None. Implementation follows the brief exactly, all tests pass, and full suite verifies no regressions.

## Commit

```
464d59e Árbitro de colisión sobre la geometría exacta
```

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## Arreglo: chequeo de superposición

Finding de la revisión: `ArbitroExacto._entra_poly` tenía un único chequeo de
proximidad, `poly.distance(otro) < s - EPS`. `distance` de shapely devuelve
`0.0` tanto para "apenas se tocan" como para "se superponen groseramente", y
con `sep=0.0` (valor legítimo: `params.py` solo rechaza `sep < 0`, y el CLI
acepta `--sep 0`) la comparación es siempre falsa (`0.0 < 0.0 - 1e-6`), así
que el árbitro aprobaba superposiciones arbitrariamente grandes. `verify.py`
no tiene ese agujero porque hace dos chequeos: primero área de intersección
contra `OVERLAP_AREA_THRESHOLD_MM2`, después separación. El árbitro ahora
hace el mismo par de chequeos, importando `OVERLAP_AREA_THRESHOLD_MM2` de
`verify.py` en vez de redefinirlo (igual que ya se hace con `placed_polygon`),
para que no puedan divergir.

### RED

Test agregado a `tests/engine/test_exact.py`:
`test_una_pieza_muy_superpuesta_con_sep_cero_no_entra` — con `sep=0.0`, una
pieza colocada exactamente sobre otra ya puesta no debe entrar.

```
$ .venv/bin/python -m pytest tests/engine/test_exact.py -v
...
tests/engine/test_exact.py .....F.                                       [100%]

=================================== FAILURES ===================================
_____________ test_una_pieza_muy_superpuesta_con_sep_cero_no_entra _____________

    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=0.0, margin=10.0)
    arbitro.agregar(cuadrado(100.0, part_id=0), 0.0, False, 10.0, 10.0)
>   assert not arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 10.0, 10.0)
E   assert not True

tests/engine/test_exact.py:68: AssertionError
=========================== short test summary info ============================
FAILED tests/engine/test_exact.py::test_una_pieza_muy_superpuesta_con_sep_cero_no_entra
========================= 1 failed, 6 passed in 0.07s ==========================
```

### Cambio

En `src/nesting/engine/exact.py`: se importa `OVERLAP_AREA_THRESHOLD_MM2`
desde `nesting.geometry.verify` (junto a `placed_polygon`, que ya se
importaba de ahí), y `_entra_poly` chequea primero intersección real por
área antes del chequeo de distancia, igual que `_check_pairs` en `verify.py`.

### GREEN

```
$ .venv/bin/python -m pytest tests/engine/test_exact.py -v
============================= test session starts ==============================
collected 7 items

tests/engine/test_exact.py .......                                       [100%]

============================== 7 passed in 0.06s ===============================
```

### Tests que cubren el cambio

```
$ .venv/bin/python -m pytest tests/engine/test_exact.py tests/engine/test_effort.py -p no:warnings
.......................                                                  [100%]
23 passed in 39.21s
```

### Concerns

Ninguno. La importación de `OVERLAP_AREA_THRESHOLD_MM2` desde `verify.py` no
presentó fricción: el módulo ya importaba `placed_polygon` del mismo archivo,
así que fue agregar un nombre a un import existente.
