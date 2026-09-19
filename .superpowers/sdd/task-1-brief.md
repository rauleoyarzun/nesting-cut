### Task 1: Setup del proyecto

**Files:**
- Create: `pyproject.toml`
- Create: `src/nesting/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nada
- Produces: un venv en `.venv` con las dependencias instaladas, `pytest` corriendo, y el paquete `nesting` importable.

- [ ] **Step 1: Crear el venv e instalar dependencias**

```bash
cd /Users/raulo/cut-placement
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install numpy scipy shapely ezdxf Pillow PyYAML pytest
```

Esperado: termina con `Successfully installed ...`. `rhino3dm` se instala recién en la Task 22 porque solo lo necesita el lector `.3dm`.

- [ ] **Step 2: Escribir `pyproject.toml`**

```toml
[project]
name = "nesting"
version = "0.1.0"
description = "Optimizacion de cortes en placas a partir de archivos vectoriales"
requires-python = ">=3.13"
dependencies = [
    "numpy",
    "scipy",
    "shapely",
    "ezdxf",
    "Pillow",
    "PyYAML",
]

[project.optional-dependencies]
rhino = ["rhino3dm"]
dev = ["pytest"]

[project.scripts]
nest = "nesting.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: Crear `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
out/
```

- [ ] **Step 4: Crear los paquetes vacíos**

```bash
mkdir -p src/nesting tests bench/files
touch src/nesting/__init__.py tests/__init__.py
```

- [ ] **Step 5: Escribir el test de humo**

Archivo `tests/test_smoke.py`:

```python
def test_package_imports():
    import nesting
    assert nesting is not None


def test_dependencies_available():
    import numpy
    import scipy.signal
    import shapely.geometry
    import ezdxf
    import PIL.ImageDraw
    import yaml

    assert numpy.__version__
    assert scipy.signal.fftconvolve is not None
    assert shapely.geometry.Polygon is not None
    assert ezdxf.new is not None
    assert PIL.ImageDraw.Draw is not None
    assert yaml.safe_load("a: 1") == {"a": 1}
```

- [ ] **Step 6: Instalar el paquete en modo editable y correr los tests**

```bash
.venv/bin/pip install -e .
.venv/bin/pytest tests/test_smoke.py -v
```

Esperado: `2 passed`.

- [ ] **Step 7: Inicializar git y commitear**

```bash
git init
git add pyproject.toml .gitignore src tests
git commit -m "chore: scaffold del proyecto con dependencias y test de humo"
```

---

