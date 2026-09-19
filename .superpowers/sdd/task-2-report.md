# Task 2: Primitivas geométricas - Report

## Summary
Task 2 has been completed successfully following the TDD cycle. All geometric primitives and the `Transform` class have been implemented with 100% test pass rate.

## Files Created

1. **`tests/model/__init__.py`** - Empty package initialization file for the model tests directory

2. **`tests/model/test_entities.py`** - Complete test suite with 6 test functions covering:
   - Style immutability and hashability
   - Line primitive with endpoints and style
   - Arc with angles in degrees counter-clockwise
   - Circle, Bezier, and Polyline primitives
   - Entity type union validation
   - Transform identity factory method

3. **`src/nesting/model/__init__.py`** - Empty package initialization file for the model module

4. **`src/nesting/model/entities.py`** - Core implementation containing:
   - `Point` type alias: `tuple[float, float]`
   - `Style` dataclass: source colour and layer information
   - `Line` dataclass: geometric line segment
   - `Arc` dataclass: circular arc with counter-clockwise angles
   - `Circle` dataclass: geometric circle
   - `Bezier` dataclass: cubic Bezier segment
   - `Polyline` dataclass: sequence of connected points
   - `Entity` type union: `Line | Arc | Circle | Bezier | Polyline`
   - `Transform` dataclass: rigid transformation (mirror, rotate, translate)

## TDD Cycle Results

### Step 2: Initial Test Run (FAILED - Expected)
```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 0 items / 1 error

==================================== ERRORS ====================================
________________ ERROR collecting tests/model/test_entities.py _________________
ImportError while importing test module '/Users/raulo/cut-placement/tests/model/test_entities.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Cellar/python@3.13/3.13.5/Frameworks/Python.framework/Versions/3.13/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level=0], package='')
/Users/raulo/cut-placement/tests/model/test_entities.py:5: in <module>
    from nesting.model.entities import (
E   ModuleNotFoundError: No module named 'nesting.model'
=========================== short test summary info ============================
ERROR tests/model/test_entities.py - ModuleNotFoundError: No module named 'nesting.model'
```

### Step 4: Final Test Run (PASSED)
```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
collected 6 items

tests/model/test_entities.py ......                                      [100%]

============================== 6 passed in 0.01s ===============================
```

### Full Test Suite Verification
```
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/raulo/cut-placement
configfile: pyproject.toml
testpaths: tests
collected 8 items

tests/model/test_entities.py ......                                      [ 75%]
tests/test_smoke.py ..                                                   [100%]

============================== 8 passed in 1.02s ===============================
```

## Implementation Details

### Design Decisions Implemented as per Brief

1. **No Ellipse or Spline**: Deliberately excluded because only primitives that are *exact* under rigid transformation are included. Readers will convert ELLIPSE and SPLINE to chains of cubic Bezier segments.

2. **Transform Order**: Implemented as specified:
   - First: mirror (reflection x → -x across Y axis)
   - Second: rotate by `angle_deg` counter-clockwise around origin
   - Third: translate by `(dx, dy)`
   
   This composition allows any reflection about any axis to be expressed with a single boolean flag.

3. **Frozen Dataclasses**: All dataclasses use `frozen=True` to ensure immutability and hashability, making them suitable as keys in dictionaries and sets.

4. **Type Alias for Coordinates**: Used `Point = tuple[float, float]` throughout to standardize coordinate representation.

5. **Entity Union Type**: Created `Entity` as a type union alias, making it easy for downstream code to work with any of the five primitive types.

## Deviations from Brief

**None.** The implementation follows the brief specification exactly, using all required field names, class names, and function signatures.

## Compliance Checklist

- ✅ All 6 test functions pass
- ✅ Dataclasses are frozen and hashable
- ✅ All field names match specification exactly
- ✅ Transform.identity() returns correct default values
- ✅ Entity type union properly defined
- ✅ Angles in degrees, counter-clockwise from +X axis
- ✅ Coordinates as tuple[float, float]
- ✅ Python 3.13+ modern type syntax used
- ✅ English docstrings and code
- ✅ No git commit created (as per instructions)

## Ready for Next Task

The geometric primitives foundation is complete and ready for consumption by file readers, the nesting engine, and output writers.
