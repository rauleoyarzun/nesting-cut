# Interfaz gráfica del sistema de nesting — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poner una interfaz gráfica sobre el motor de nesting que ya existe, distribuible como programa de escritorio, cuya interfaz sirva sin cambios el día que se publique en la web.

**Architecture:** Un servidor HTTP local en Python expone el motor como una API por trabajos (mandar, preguntar cómo va, tomar el resultado). La interfaz es HTML/CSS/JS servido por ese mismo servidor y mostrado en una ventana nativa con webview. El paquete nuevo `nesting_app` conoce a `nesting`; nunca al revés.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, pywebview, PyInstaller. Sin framework de frontend: HTML, CSS y JavaScript a mano.

**Spec:** `docs/superpowers/specs/2026-09-19-interfaz-grafica-design.md`

## Global Constraints

- **`nesting` nunca importa `nesting_app`.** El motor no sabe que existe una interfaz. Si un test del motor tiene que cambiar para que entre la interfaz, el corte está mal puesto.
- **Los 495 tests que ya existen no se tocan.** Ni uno. Si alguno se rompe, el cambio está mal.
- **Todo mensaje de cara al usuario va en español**, con tildes y eñes, y dice qué hacer, no sólo qué falló. Es la convención de todo el proyecto.
- **La CLI no cambia su comportamiento observable.** Mismos mensajes, mismos códigos de salida (0 ok, 1 error de entrada, 2 verificación fallida).
- **TDD sin excepciones:** test que falla, correrlo para verlo fallar, implementación mínima, test que pasa, commit.
- **Tokens de diseño (dirección D · Moderno), exactos:** fondo `#F4F6F8`, panel `#FFFFFF`, fondo del dibujo `#EDF0F4`, texto `#111827`, texto secundario `#606B7B`, bordes `#E2E6EC` de 1 px, acento `#047857`, texto sobre acento `#FFFFFF`, radio 10 px (botones 8 px), alto de control 44 px, sombra `0 1px 2px rgba(17,24,39,.06), 0 4px 12px rgba(17,24,39,.05)`, tipografía Plus Jakarta Sans.
- **Toda medida en pantalla lleva `font-variant-numeric: tabular-nums`.**
- **El servidor escucha sólo en `127.0.0.1`**, con puerto pedido al sistema (`port 0`) y un token obligatorio en todo pedido a `/api/`.
- **Nada de emojis** en la interfaz ni en los mensajes. Íconos: SVG en línea con trazo.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `src/nesting/params.py` | **Nuevo.** Los parámetros de una corrida y sus reglas de validación. Vive en `nesting` y no en `nesting_app` porque la CLI también lo usa, y `nesting` no puede importar `nesting_app`. |
| `src/nesting/engine/packer.py` | **Modificar.** Sumar el callback de avance y cancelación. |
| `src/nesting/cli.py` | **Modificar.** Usar `params.py` en vez de su propia validación. |
| `src/nesting/model/material.py` | **Modificar.** `DEFAULT_MATERIALS_PATH` pasa por `rutas.py`. |
| `src/nesting_app/rutas.py` | **Nuevo.** Dónde están los datos y los recursos, congelado o no. |
| `src/nesting_app/materials_store.py` | **Nuevo.** El catálogo editable en la carpeta del usuario. |
| `src/nesting_app/archivos.py` | **Nuevo.** La puerta de plataforma: ruta local contra subida. |
| `src/nesting_app/jobs.py` | **Nuevo.** El registro de trabajos y el hilo que los corre. |
| `src/nesting_app/api.py` | **Nuevo.** Las rutas HTTP. |
| `src/nesting_app/desktop.py` | **Nuevo.** Levanta el servidor y abre la ventana. |
| `src/nesting_app/web/index.html` | **Nuevo.** El armazón de la interfaz. |
| `src/nesting_app/web/app.css` | **Nuevo.** Los tokens y todos los componentes. |
| `src/nesting_app/web/app.js` | **Nuevo.** El flujo completo. |

---

## Task 1: Los parámetros de una corrida, compartidos por CLI y API

**Files:**
- Create: `src/nesting/params.py`
- Modify: `src/nesting/cli.py` (reemplazar `_validate_numeric_args`)
- Test: `tests/test_params.py`

**Interfaces:**
- Consumes: `nesting.engine.oracle.NestConfig`, `nesting.pipeline.DEFAULT_CHAIN_TOL`
- Produces:
  - `NestParams` (dataclass congelada): `material: str`, `sep: float = 5.0`, `borde: float = 10.0`, `copias: int = 1`, `angulos: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)`, `espejo: bool = True`, `unidades: str | None = None`, `tol_cierre: float = 0.1`, `resolucion: float = 2.0`, `esfuerzo: str = "normal"`
  - `ReglaRota` (dataclass congelada): `campo: str`, `regla: str`, `valor: object`
  - `ParamsInvalidosError(ValueError)` con atributo `rota: ReglaRota`
  - `FLAG_POR_CAMPO: dict[str, str]` — de `"sep"` a `"--sep"`
  - `validar(p: NestParams) -> None` — levanta `ParamsInvalidosError`
  - `a_config(p: NestParams) -> NestConfig`
  - `mensaje_cli(rota: ReglaRota) -> str`

**Por qué existe esta tarea:** hoy las reglas viven en `_validate_numeric_args`, adentro de `cli.py`, y devuelven un mensaje ya armado con el nombre del flag adentro (`"--sep tiene que ser >= 0"`). La API necesita las mismas reglas pero no puede mostrar `--sep` al lado de un campo de formulario. La regla se separa de su redacción: una sola fuente de verdad, dos maneras de contarla.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_params.py`:

```python
"""Las reglas de los parámetros, que comparten la CLI y la API."""

import pytest

from nesting.params import (
    FLAG_POR_CAMPO,
    NestParams,
    ParamsInvalidosError,
    a_config,
    mensaje_cli,
    validar,
)


def p(**cambios):
    return NestParams(material="mdf18", **cambios)


def test_los_valores_por_omision_son_validos():
    validar(p())


@pytest.mark.parametrize(
    "cambio, campo, regla",
    [
        ({"copias": 0}, "copias", ">= 1"),
        ({"copias": -3}, "copias", ">= 1"),
        ({"sep": -0.1}, "sep", ">= 0"),
        ({"borde": -1.0}, "borde", ">= 0"),
        ({"tol_cierre": 0.0}, "tol_cierre", "> 0"),
        ({"tol_cierre": -1.0}, "tol_cierre", "> 0"),
        ({"resolucion": 0.0}, "resolucion", "> 0"),
        ({"resolucion": -2.0}, "resolucion", "> 0"),
    ],
)
def test_cada_regla_nombra_su_campo_y_su_regla(cambio, campo, regla):
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(p(**cambio))

    assert capturado.value.rota.campo == campo
    assert capturado.value.rota.regla == regla
    assert capturado.value.rota.valor == next(iter(cambio.values()))


def test_la_separacion_cero_es_valida():
    """Cortar pegado es una decisión legítima del usuario, no un error."""
    validar(p(sep=0.0))


def test_el_borde_cero_es_valido():
    validar(p(borde=0.0))


def test_el_mensaje_de_la_cli_nombra_el_flag_y_el_valor():
    """La CLI tiene que seguir diciendo exactamente lo que decía.

    Ese texto es contrato: hay tests de la CLI que lo verifican, y lo lee
    gente en una terminal donde 'sep' a secas no significa nada.
    """
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(p(sep=-1.0))

    assert mensaje_cli(capturado.value.rota) == "--sep tiene que ser >= 0, se recibió -1.0"


def test_todo_campo_con_regla_tiene_su_flag():
    """Un campo sin flag haría reventar a `mensaje_cli` con KeyError justo
    cuando el usuario ya se equivocó, que es el peor momento."""
    for campo in ("copias", "sep", "borde", "tol_cierre", "resolucion"):
        assert campo in FLAG_POR_CAMPO


def test_a_config_traduce_los_nombres_al_motor():
    """La interfaz habla en español y el motor en inglés. La traducción vive
    en un solo lugar para que no se desincronice."""
    config = a_config(p(sep=3.0, borde=7.0, espejo=False, resolucion=1.5, esfuerzo="lento"))

    assert config.sep == 3.0
    assert config.margin == 7.0
    assert config.mirror is False
    assert config.resolution == 1.5
    assert config.effort == "lento"
    assert config.angles == (0.0, 90.0, 180.0, 270.0)


def test_a_config_no_valida_por_su_cuenta():
    """`a_config` traduce, no juzga. Validar es un paso aparte y explícito,
    así el que llama no puede creer que traducir ya lo protegió."""
    config = a_config(p(sep=-5.0))
    assert config.sep == -5.0
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/test_params.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting.params'`

- [ ] **Step 3: Escribir la implementación mínima**

Crear `src/nesting/params.py`:

```python
"""Los parámetros de una corrida, y las reglas que tienen que cumplir.

Vive en `nesting` y no en `nesting_app` a propósito: la CLI los usa, y el
motor no puede importar el paquete de la interfaz sin invertir la única
dependencia que sostiene toda la arquitectura.

La regla se guarda separada de su redacción. En una terminal, "--sep tiene
que ser >= 0" es el mensaje correcto; al lado de un campo de formulario que
ya dice "Separación", el mismo texto con un guión doble adelante no
significa nada. Una sola fuente de verdad para la regla, dos maneras de
contarla.
"""

from dataclasses import dataclass, field

from nesting.engine.oracle import NestConfig

DEFAULT_ANGLES: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)


@dataclass(frozen=True)
class NestParams:
    """Todo lo que define una corrida, menos el archivo de entrada."""

    material: str
    sep: float = 5.0
    borde: float = 10.0
    copias: int = 1
    angulos: tuple[float, ...] = DEFAULT_ANGLES
    espejo: bool = True
    unidades: str | None = None
    tol_cierre: float = 0.1
    resolucion: float = 2.0
    esfuerzo: str = "normal"


@dataclass(frozen=True)
class ReglaRota:
    """Qué campo incumplió qué regla, y con qué valor."""

    campo: str
    regla: str
    valor: object


class ParamsInvalidosError(ValueError):
    """Un parámetro no cumple su regla."""

    def __init__(self, rota: ReglaRota) -> None:
        super().__init__(f"{rota.campo} tiene que ser {rota.regla}, se recibió {rota.valor}")
        self.rota = rota


FLAG_POR_CAMPO: dict[str, str] = {
    "copias": "--copias",
    "sep": "--sep",
    "borde": "--borde",
    "tol_cierre": "--tol-cierre",
    "resolucion": "--resolucion",
}


def validar(p: NestParams) -> None:
    """Levanta `ParamsInvalidosError` en el primer parámetro que no cumple.

    El orden es el mismo que tenía `_validate_numeric_args` en `cli.py`, para
    que un comando con dos errores a la vez siga señalando el mismo primero.
    """
    if p.copias < 1:
        raise ParamsInvalidosError(ReglaRota("copias", ">= 1", p.copias))
    if p.sep < 0:
        raise ParamsInvalidosError(ReglaRota("sep", ">= 0", p.sep))
    if p.borde < 0:
        raise ParamsInvalidosError(ReglaRota("borde", ">= 0", p.borde))
    if p.tol_cierre <= 0:
        raise ParamsInvalidosError(ReglaRota("tol_cierre", "> 0", p.tol_cierre))
    if p.resolucion <= 0:
        raise ParamsInvalidosError(ReglaRota("resolucion", "> 0", p.resolucion))


def mensaje_cli(rota: ReglaRota) -> str:
    """La redacción de terminal, con el nombre del flag adentro."""
    return f"{FLAG_POR_CAMPO[rota.campo]} tiene que ser {rota.regla}, se recibió {rota.valor}"


def a_config(p: NestParams) -> NestConfig:
    """Traduce al vocabulario del motor. No valida: eso es `validar`."""
    return NestConfig(
        sep=p.sep,
        margin=p.borde,
        angles=tuple(p.angulos),
        mirror=p.espejo,
        resolution=p.resolucion,
        effort=p.esfuerzo,
    )
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/test_params.py -q`
Expected: PASS, 13 tests

- [ ] **Step 5: Hacer que la CLI use las mismas reglas**

En `src/nesting/cli.py`, agregar al bloque de imports:

```python
from nesting.params import (
    NestParams,
    ParamsInvalidosError,
    mensaje_cli,
    validar,
)
```

Reemplazar la función `_validate_numeric_args` completa (con su docstring) por nada — se borra — y reemplazar su llamada al principio de `main`:

```python
    invalid = _validate_numeric_args(args)
    if invalid is not None:
        print(f"error: {invalid}", file=sys.stderr)
        return EXIT_INPUT_ERROR
```

por:

```python
    try:
        validar(
            NestParams(
                material=args.material,
                sep=args.sep,
                borde=args.borde,
                copias=args.copias,
                espejo=not args.sin_espejo,
                unidades=args.unidades,
                tol_cierre=args.tol_cierre,
                resolucion=args.resolucion,
                esfuerzo=args.esfuerzo,
            )
        )
    except ParamsInvalidosError as error:
        print(f"error: {mensaje_cli(error.rota)}", file=sys.stderr)
        return EXIT_INPUT_ERROR
```

Nota: `angulos` no se pasa acá porque se parsea más abajo, donde ya estaba, y su error tiene su propio mensaje.

- [ ] **Step 6: Correr TODA la suite**

Run: `.venv/bin/python -m pytest -q -p no:warnings`
Expected: PASS. Los tests de la CLI que verifican los mensajes de error numéricos tienen que seguir pasando **sin tocarlos**. Si alguno falla, el texto cambió y hay que arreglar `mensaje_cli`, no el test.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/params.py src/nesting/cli.py tests/test_params.py
git commit -m "Extraer los parámetros de una corrida a nesting/params.py

La CLI y la API van a validar con el mismo código. La regla se guarda
separada de su redacción: en terminal '--sep tiene que ser >= 0' es
correcto, al lado de un campo que ya dice 'Separación' no significa nada.

Los mensajes de la CLI no cambian, y sus tests pasan sin tocarlos.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Dónde están los datos y los recursos, congelado o no

**Files:**
- Create: `src/nesting_app/__init__.py`, `src/nesting_app/rutas.py`
- Modify: `src/nesting/model/material.py:13`
- Test: `tests/app/__init__.py`, `tests/app/test_rutas.py`

**Interfaces:**
- Produces:
  - `carpeta_datos() -> Path` — `%APPDATA%\nesting` en Windows, `~/Library/Application Support/nesting` en macOS, `~/.local/share/nesting` en el resto. La crea si no existe.
  - `recurso(nombre: str) -> Path` — un archivo que viaja con el programa (`materials.yaml`, la carpeta `web/`), funcione congelado o no.
  - `esta_congelado() -> bool`
  - `CARPETA_WEB: ...` se resuelve con `recurso("web")` desde `desktop.py` y `api.py`.

**Por qué existe esta tarea:** hoy `DEFAULT_MATERIALS_PATH` se calcula como `Path(__file__).resolve().parents[3] / "materials.yaml"`. Dentro de un ejecutable de PyInstaller esa cuenta no da, porque la estructura de carpetas del repo no existe: los recursos quedan bajo `sys._MEIPASS`. Este bug **no aparece en ningún test normal** — aparece cuando el usuario abre el programa. Se arregla ahora, antes de que haya nada construido encima.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/__init__.py` vacío y `tests/app/test_rutas.py`:

```python
"""Dónde están los datos y los recursos, corriendo del repo o congelado."""

import sys
from pathlib import Path

import pytest

from nesting_app import rutas


def test_la_carpeta_de_datos_se_crea_si_no_existe(tmp_path, monkeypatch):
    destino = tmp_path / "nesting"
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: destino)

    assert rutas.carpeta_datos() == destino
    assert destino.is_dir()


def test_la_carpeta_de_datos_se_puede_pedir_dos_veces(tmp_path, monkeypatch):
    destino = tmp_path / "nesting"
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: destino)

    rutas.carpeta_datos()
    assert rutas.carpeta_datos() == destino


def test_sin_congelar_los_recursos_salen_del_repo():
    """`materials.yaml` está en la raíz del proyecto, tres niveles sobre el
    paquete. Es la cuenta que hace hoy `DEFAULT_MATERIALS_PATH`."""
    assert not rutas.esta_congelado()

    catalogo = rutas.recurso("materials.yaml")
    assert catalogo.is_file()
    assert "mdf18" in catalogo.read_text(encoding="utf-8")


def test_congelado_los_recursos_salen_de_meipass(tmp_path, monkeypatch):
    """PyInstaller descomprime los recursos en `sys._MEIPASS` y NO reproduce
    la estructura del repo. La cuenta de `parents[3]` da cualquier cosa ahí,
    que es el bug que esta función existe para que no ocurra nunca.
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "materials.yaml").write_text("mdf18:\n", encoding="utf-8")

    assert rutas.esta_congelado()
    assert rutas.recurso("materials.yaml") == tmp_path / "materials.yaml"


def test_un_recurso_que_no_existe_se_queja_nombrandolo():
    """Un recurso faltante en un ejecutable congelado es un error de
    empaquetado, no del usuario. El mensaje tiene que decir cuál falta para
    que quien arme el paquete sepa qué agregarle."""
    with pytest.raises(FileNotFoundError, match="no_existe.yaml"):
        rutas.recurso("no_existe.yaml")


def test_la_carpeta_web_es_un_recurso():
    web = rutas.recurso("web")
    assert web.is_dir()


@pytest.mark.parametrize(
    "plataforma, variable, esperado",
    [
        ("win32", "APPDATA", "nesting"),
        ("darwin", None, "nesting"),
        ("linux", None, "nesting"),
    ],
)
def test_cada_plataforma_usa_su_carpeta(plataforma, variable, esperado, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", plataforma)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    base = rutas._base_de_datos()
    assert base.name == esperado
    assert tmp_path in base.parents
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_rutas.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting_app'`

- [ ] **Step 3: Escribir la implementación mínima**

Crear `src/nesting_app/__init__.py`:

```python
"""La interfaz gráfica sobre el motor de nesting.

Este paquete conoce a `nesting`. `nesting` no conoce a este. Esa dirección
es la que permite que la CLI, los tests del motor y el motor mismo sigan
existiendo sin saber que hay una interfaz, y la que va a permitir que el día
de mañana la misma API se sirva desde un servidor web en vez de desde una
ventana.
"""
```

Crear `src/nesting_app/rutas.py`:

```python
"""Dónde está cada cosa, corriendo del repo o dentro de un ejecutable.

PyInstaller no reproduce la estructura de carpetas del proyecto: descomprime
los recursos declarados en una carpeta temporal y deja su ruta en
`sys._MEIPASS`. Cualquier código que llegue a un archivo del proyecto
contando niveles sobre `__file__` funciona en desarrollo y falla al
congelar -- y falla recién cuando alguien abre el programa, porque ningún
test normal corre contra un ejecutable congelado.

Todo el acceso a archivos que viajan con el programa pasa por acá.
"""

import sys
from pathlib import Path

NOMBRE_APP = "nesting"


def esta_congelado() -> bool:
    """Si estamos adentro de un ejecutable armado con PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def _raiz_de_recursos() -> Path:
    if esta_congelado():
        return Path(sys._MEIPASS)  # noqa: SLF001 - así lo expone PyInstaller
    # src/nesting_app/rutas.py -> src/nesting_app -> src -> la raíz del repo
    return Path(__file__).resolve().parents[2]


def recurso(nombre: str) -> Path:
    """Un archivo o carpeta que viaja con el programa.

    Que falte no es un problema del usuario: es un error de empaquetado, y
    el mensaje lo nombra para que quien arme el paquete sepa qué agregar.
    """
    ruta = _raiz_de_recursos() / nombre
    if not ruta.exists():
        raise FileNotFoundError(
            f"falta el recurso {nombre!r} en {_raiz_de_recursos()}. "
            "Si esto pasa en el ejecutable, hay que agregarlo a los datos "
            "declarados en el .spec de PyInstaller."
        )
    return ruta


def _base_de_datos() -> Path:
    """La carpeta de datos del usuario que corresponde a esta plataforma."""
    if sys.platform == "win32":
        import os

        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / NOMBRE_APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NOMBRE_APP
    return Path.home() / ".local" / "share" / NOMBRE_APP


def carpeta_datos() -> Path:
    """Donde el programa guarda lo que es del usuario, creada si no estaba."""
    destino = _base_de_datos()
    destino.mkdir(parents=True, exist_ok=True)
    return destino
```

Crear la carpeta que los tests esperan:

```bash
mkdir -p src/nesting_app/web && touch src/nesting_app/web/.gitkeep
```

Corregir `src/nesting/model/material.py`, línea 13. Reemplazar:

```python
DEFAULT_MATERIALS_PATH = Path(__file__).resolve().parents[3] / "materials.yaml"
```

por:

```python
def _default_materials_path() -> Path:
    """Dónde está el catálogo que viene con el programa.

    Contar niveles sobre `__file__` funciona desde el repo y NO funciona
    dentro de un ejecutable congelado, donde PyInstaller deja los recursos
    en otro lado. `nesting_app.rutas` sabe distinguir los dos casos.

    La importación es perezosa a propósito: `nesting` no puede depender de
    `nesting_app` al importarse, o se invertiría la dependencia que sostiene
    toda la arquitectura. Acá se usa sólo si alguien pide el valor por
    omisión, y si el paquete de la interfaz no está (una instalación del
    motor a secas), se cae a la cuenta de siempre.
    """
    try:
        from nesting_app.rutas import recurso

        return recurso("materials.yaml")
    except (ImportError, FileNotFoundError):
        return Path(__file__).resolve().parents[3] / "materials.yaml"


DEFAULT_MATERIALS_PATH = _default_materials_path()
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/app/test_rutas.py -q`
Expected: PASS, 9 tests

- [ ] **Step 5: Correr TODA la suite**

Run: `.venv/bin/python -m pytest -q -p no:warnings`
Expected: PASS. `DEFAULT_MATERIALS_PATH` tiene que seguir resolviendo al mismo archivo que antes.

- [ ] **Step 6: Declarar el paquete nuevo**

En `pyproject.toml`, agregar a `dependencies`:

```toml
    "fastapi",
    "uvicorn",
    "pywebview",
```

Reinstalar para que `nesting_app` quede importable:

```bash
.venv/bin/pip install -e .
```

- [ ] **Step 7: Commit**

```bash
git add src/nesting_app pyproject.toml src/nesting/model/material.py tests/app
git commit -m "rutas.py: recursos y datos que funcionan congelados

DEFAULT_MATERIALS_PATH contaba niveles sobre __file__, cuenta que no da
adentro de un ejecutable de PyInstaller: los recursos quedan en
sys._MEIPASS y la estructura del repo no existe.

Ese bug no aparece en ningún test normal. Aparece cuando el usuario abre
el programa. Se arregla antes de construir nada encima.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: El catálogo de materiales, editable por el usuario

**Files:**
- Create: `src/nesting_app/materials_store.py`
- Test: `tests/app/test_materials_store.py`

**Interfaces:**
- Consumes: `nesting_app.rutas.carpeta_datos`, `nesting_app.rutas.recurso`, `nesting.model.material.load_materials`, `nesting.model.material.Material`
- Produces:
  - `VETA_LIBRE = 180.0`, `VETA_RESPETAR = 5.0`
  - `ruta_catalogo() -> Path` — `<carpeta de datos>/materials.yaml`, copiando el original la primera vez
  - `leer() -> dict[str, Material]`
  - `guardar(materiales: dict[str, Material]) -> None`
  - `agregar(m: Material) -> None` — levanta `MaterialDuplicadoError`
  - `editar(nombre: str, m: Material) -> None` — levanta `MaterialDesconocidoError`
  - `borrar(nombre: str) -> None` — levanta `MaterialDesconocidoError`
  - `restaurar() -> None` — vuelve al catálogo que trae el programa
  - `MaterialDuplicadoError(ValueError)`, `MaterialDesconocidoError(KeyError)`

**Por qué existe esta tarea:** el catálogo que trae el programa queda de sólo lectura adentro del ejecutable. El usuario compra en otro proveedor y necesita sus propias medidas.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/test_materials_store.py`:

```python
"""El catálogo de materiales que el usuario edita."""

import pytest

from nesting.model.material import Material
from nesting_app import materials_store as store


@pytest.fixture(autouse=True)
def catalogo_aislado(tmp_path, monkeypatch):
    """Cada test con su propia carpeta de datos, nunca la del usuario real."""
    monkeypatch.setattr(store.rutas, "_base_de_datos", lambda: tmp_path / "nesting")
    return tmp_path


def melamina():
    return Material(name="melamina18", sheet_w=1830.0, sheet_h=2750.0,
                    grain_tolerance=store.VETA_LIBRE)


def test_la_primera_vez_se_copia_el_catalogo_que_trae_el_programa():
    """Un catálogo vacío obligaría al usuario a tipear sus cuatro materiales
    antes de poder hacer nada. Arranca con los que ya conocemos."""
    materiales = store.leer()

    assert "mdf18" in materiales
    assert materiales["mdf18"].sheet_w == 1830.0
    assert materiales["mdf18"].sheet_h == 2600.0


def test_el_archivo_queda_en_la_carpeta_de_datos_no_adentro_del_programa():
    ruta = store.ruta_catalogo()

    assert ruta.name == "materials.yaml"
    assert ruta.parent == store.rutas.carpeta_datos()
    assert ruta.is_file()


def test_agregar_y_releer():
    store.agregar(melamina())

    materiales = store.leer()
    assert materiales["melamina18"].sheet_h == 2750.0
    assert materiales["melamina18"].grain_tolerance == store.VETA_LIBRE


def test_agregar_uno_que_ya_existe_se_rechaza():
    """Sin esto, agregar 'mdf18' pisaría en silencio las medidas de un
    material que el usuario ya estaba usando en trabajos anteriores."""
    with pytest.raises(store.MaterialDuplicadoError, match="mdf18"):
        store.agregar(Material("mdf18", 100.0, 100.0, store.VETA_LIBRE))


def test_editar_cambia_las_medidas():
    store.editar("mdf18", Material("mdf18", 1830.0, 2750.0, store.VETA_LIBRE))

    assert store.leer()["mdf18"].sheet_h == 2750.0


def test_editar_puede_renombrar():
    store.editar("mdf18", Material("mdf18mm", 1830.0, 2600.0, store.VETA_LIBRE))

    materiales = store.leer()
    assert "mdf18mm" in materiales
    assert "mdf18" not in materiales


def test_editar_uno_que_no_existe_se_queja():
    with pytest.raises(store.MaterialDesconocidoError, match="fantasma"):
        store.editar("fantasma", melamina())


def test_borrar():
    store.borrar("mdf15")

    assert "mdf15" not in store.leer()
    assert "mdf18" in store.leer()


def test_borrar_uno_que_no_existe_se_queja():
    with pytest.raises(store.MaterialDesconocidoError, match="fantasma"):
        store.borrar("fantasma")


def test_se_puede_borrar_hasta_el_ultimo():
    """Quedarse sin materiales es un estado válido y recuperable: está el
    botón de restaurar. Prohibirlo sería tratar al usuario de tonto."""
    for nombre in list(store.leer()):
        store.borrar(nombre)

    assert store.leer() == {}


def test_restaurar_vuelve_al_catalogo_original():
    store.borrar("mdf18")
    store.agregar(melamina())

    store.restaurar()

    materiales = store.leer()
    assert "mdf18" in materiales
    assert "melamina18" not in materiales


def test_un_catalogo_corrupto_se_queja_nombrando_el_archivo():
    """El usuario puede haber editado el YAML a mano. El mensaje tiene que
    decirle dónde está el archivo para que pueda arreglarlo o borrarlo."""
    store.leer()
    store.ruta_catalogo().write_text("esto: [no cierra\n", encoding="utf-8")

    with pytest.raises(ValueError, match="materials.yaml"):
        store.leer()


def test_restaurar_arregla_un_catalogo_corrupto():
    """Es la salida que se le ofrece al usuario cuando el archivo está roto,
    así que tiene que funcionar justamente en ese estado."""
    store.leer()
    store.ruta_catalogo().write_text("esto: [no cierra\n", encoding="utf-8")

    store.restaurar()

    assert "mdf18" in store.leer()


def test_la_veta_tiene_dos_valores_y_ninguno_es_un_numero_suelto():
    """La interfaz muestra dos opciones con nombre, no un campo de grados.
    Estos son los dos valores que esas opciones escriben."""
    assert store.VETA_LIBRE == 180.0
    assert store.VETA_RESPETAR == 5.0
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_materials_store.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting_app.materials_store'`

- [ ] **Step 3: Escribir la implementación mínima**

Crear `src/nesting_app/materials_store.py`:

```python
"""El catálogo de materiales que el usuario puede editar.

El catálogo que trae el programa queda de sólo lectura adentro del
ejecutable, así que la copia editable vive en la carpeta de datos del
usuario. La primera vez se siembra con el original: arrancar con una lista
vacía obligaría a tipear cuatro materiales antes de poder hacer nada.
"""

from dataclasses import replace
from pathlib import Path

import yaml

from nesting.model.material import Material, load_materials
from nesting_app import rutas

VETA_LIBRE = 180.0
"""La pieza gira libre. Típico del MDF.

Por convención del catálogo, cualquier valor de 90 o más equivale a rotación
libre; 180 es el que usa el catálogo que trae el programa.
"""

VETA_RESPETAR = 5.0
"""Sólo 0 y 180 grados: corte cruzado bloqueado. Multilaminado, fenólico."""


class MaterialDuplicadoError(ValueError):
    """Ya hay un material con ese nombre."""


class MaterialDesconocidoError(KeyError):
    """No hay ningún material con ese nombre."""

    def __str__(self) -> str:
        return self.args[0] if self.args else ""


def ruta_catalogo() -> Path:
    """El catálogo editable, sembrado con el original la primera vez."""
    destino = rutas.carpeta_datos() / "materials.yaml"
    if not destino.exists():
        destino.write_text(
            rutas.recurso("materials.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return destino


def leer() -> dict[str, Material]:
    """Lee el catálogo del usuario.

    Un YAML roto sale como `ValueError` con el nombre del archivo adentro:
    el usuario pudo haberlo editado a mano y necesita saber dónde está para
    arreglarlo, o para borrarlo y dejar que se siembre de nuevo.
    """
    ruta = ruta_catalogo()
    try:
        return load_materials(ruta)
    except ValueError as error:
        raise ValueError(
            f"el catálogo de materiales en {ruta} no se pudo leer: {error}. "
            "Se puede restaurar el catálogo original desde la pantalla de "
            "materiales."
        ) from error


def guardar(materiales: dict[str, Material]) -> None:
    """Escribe el catálogo entero. El orden alfabético lo hace diffeable."""
    crudo = {
        nombre: {
            "placa": [materiales[nombre].sheet_w, materiales[nombre].sheet_h],
            "tolerancia_veta": materiales[nombre].grain_tolerance,
        }
        for nombre in sorted(materiales)
    }
    ruta_catalogo().write_text(
        yaml.safe_dump(crudo, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def agregar(material: Material) -> None:
    materiales = leer()
    if material.name in materiales:
        raise MaterialDuplicadoError(
            f"ya existe un material llamado {material.name!r}; "
            "elegí otro nombre o editá el que está."
        )
    materiales[material.name] = material
    guardar(materiales)


def editar(nombre: str, material: Material) -> None:
    """Cambia un material, con o sin renombrarlo."""
    materiales = leer()
    if nombre not in materiales:
        raise MaterialDesconocidoError(f"no existe ningún material llamado {nombre!r}")
    if material.name != nombre and material.name in materiales:
        raise MaterialDuplicadoError(
            f"ya existe un material llamado {material.name!r}; "
            "elegí otro nombre."
        )
    del materiales[nombre]
    materiales[material.name] = material
    guardar(materiales)


def borrar(nombre: str) -> None:
    materiales = leer()
    if nombre not in materiales:
        raise MaterialDesconocidoError(f"no existe ningún material llamado {nombre!r}")
    del materiales[nombre]
    guardar(materiales)


def restaurar() -> None:
    """Vuelve al catálogo que trae el programa.

    Pisa el archivo sin leerlo: es la salida que se le ofrece al usuario
    cuando el suyo quedó ilegible, así que tiene que funcionar justamente en
    ese estado.
    """
    ruta_catalogo().write_text(
        rutas.recurso("materials.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/app/test_materials_store.py -q`
Expected: PASS, 14 tests

- [ ] **Step 5: Correr TODA la suite**

Run: `.venv/bin/python -m pytest -q -p no:warnings`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app/materials_store.py tests/app/test_materials_store.py
git commit -m "Catálogo de materiales editable en la carpeta del usuario

El que trae el programa queda de sólo lectura adentro del ejecutable.
La copia editable se siembra con el original la primera vez: arrancar
vacío obligaría a tipear cuatro materiales antes de poder hacer nada.

Restaurar pisa el archivo sin leerlo, porque es la salida que se ofrece
justamente cuando quedó ilegible.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Avance y cancelación en el motor

**Files:**
- Modify: `src/nesting/engine/packer.py` (`pack`, `_pack_once`)
- Test: `tests/engine/test_progreso.py`

**Interfaces:**
- Produces:
  - `Avance` (dataclass congelada): `intento: int`, `intentos: int`, `ubicadas: int`, `totales: int`, `placa: int`, `compactando: bool = False`
  - `Cancelado(Exception)` — el motor abandonó porque se lo pidieron
  - `pack(parts, material, config, oracle_factory, progreso: Callable[[Avance], bool] | None = None) -> PackResult`
    El callback devuelve `True` para seguir y `False` para abandonar. Si abandona, `pack` levanta `Cancelado`.

**Por qué existe esta tarea:** en una terminal, nueve minutos sin señales se bancan. En una ventana gráfica es un programa colgado, y el usuario lo mata desde el administrador de tareas. Es el único cambio al motor en todo el plan.

**Cuidado con el conteo:** `pack` corre `EFFORT_RESTARTS[config.effort]` pasadas completas y cada una reinicia las piezas ubicadas. Por eso `Avance` lleva el intento además de las piezas: un porcentaje que retrocede es peor que ninguno.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/engine/test_progreso.py`:

```python
"""El callback de avance y la cancelación cooperativa."""

import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import Avance, Cancelado, EFFORT_RESTARTS, pack
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.model.material import Material
from nesting.model.part import Part

MATERIAL = Material("test", 1000.0, 1000.0, 180.0)


def cuadrado(part_id, lado=100.0):
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)),
        holes=(),
        entity_ids=(part_id,),
    )


def fabrica():
    cache = MaskCache()
    return lambda: RasterOracle(cache=cache)


def config(**cambios):
    return NestConfig(sep=5.0, margin=10.0, effort="rapido", **cambios)


def test_sin_callback_pack_se_comporta_igual_que_siempre():
    """La CLI no lo usa. Si pasarlo o no cambiara el resultado, el cambio
    estaría tocando el motor de verdad y no sólo observándolo."""
    piezas = [cuadrado(i) for i in range(6)]

    sin = pack(piezas, MATERIAL, config(), fabrica())
    con = pack(piezas, MATERIAL, config(), fabrica(), progreso=lambda a: True)

    assert sin.sheets_used == con.sheets_used
    assert [(p.part, p.sheet) for p in sin.placements] == [
        (p.part, p.sheet) for p in con.placements
    ]


def test_el_callback_se_llama_por_cada_pieza_ubicada():
    piezas = [cuadrado(i) for i in range(6)]
    avances = []

    pack(piezas, MATERIAL, config(), fabrica(), progreso=lambda a: avances.append(a) or True)

    ubicadas = [a for a in avances if not a.compactando]
    assert len(ubicadas) >= 6
    assert all(a.totales == 6 for a in ubicadas)


def test_las_piezas_ubicadas_solo_suben_dentro_de_un_intento():
    """Una barra que retrocede es peor que no tener barra."""
    piezas = [cuadrado(i) for i in range(8)]
    avances = []

    pack(piezas, MATERIAL, config(effort="normal"), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    por_intento = {}
    for a in avances:
        if a.compactando:
            continue
        previas = por_intento.get(a.intento, 0)
        assert a.ubicadas >= previas, f"el intento {a.intento} retrocedió"
        por_intento[a.intento] = a.ubicadas


def test_la_cantidad_de_intentos_se_sabe_desde_el_primer_aviso():
    """La interfaz necesita poder escribir 'intento 1 de 3' antes de que
    termine el primero. Sale de EFFORT_RESTARTS, no de haber terminado."""
    piezas = [cuadrado(i) for i in range(4)]
    avances = []

    pack(piezas, MATERIAL, config(effort="normal"), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    assert avances[0].intentos == EFFORT_RESTARTS["normal"]
    assert avances[0].intento == 1


def test_los_intentos_llegan_hasta_el_ultimo():
    piezas = [cuadrado(i) for i in range(4)]
    avances = []

    pack(piezas, MATERIAL, config(effort="normal"), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    intentos = {a.intento for a in avances if not a.compactando}
    assert intentos == set(range(1, EFFORT_RESTARTS["normal"] + 1))


def test_la_compactacion_final_se_avisa_aparte():
    """Es una sola pasada corta. Fingir un porcentaje ahí sería inventar."""
    piezas = [cuadrado(i) for i in range(4)]
    avances = []

    pack(piezas, MATERIAL, config(), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    assert any(a.compactando for a in avances)
    assert avances[-1].compactando


def test_devolver_False_cancela_y_levanta():
    piezas = [cuadrado(i) for i in range(20)]
    vistos = []

    def cortar(avance):
        vistos.append(avance)
        return len(vistos) < 3

    with pytest.raises(Cancelado):
        pack(piezas, MATERIAL, config(), fabrica(), progreso=cortar)

    assert len(vistos) == 3, "no puede seguir trabajando después del corte"


def test_cancelar_no_deja_el_resultado_a_medias():
    """Cancelar tiene que levantar, no devolver un PackResult incompleto que
    alguien podría escribir a un DXF creyendo que está entero."""
    piezas = [cuadrado(i) for i in range(20)]

    with pytest.raises(Cancelado):
        pack(piezas, MATERIAL, config(), fabrica(), progreso=lambda a: False)


def test_el_avance_nombra_la_placa_en_curso():
    """Con muchas piezas hacen falta varias placas, y el número de placa es
    lo único que le dice al usuario que el trabajo creció."""
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = []

    pack(piezas, MATERIAL, config(), fabrica(),
         progreso=lambda a: avances.append(a) or True)

    placas = {a.placa for a in avances if not a.compactando}
    assert max(placas) >= 2
    assert min(placas) == 1


def test_sin_piezas_no_se_llama_al_callback():
    llamadas = []

    resultado = pack([], MATERIAL, config(), fabrica(),
                     progreso=lambda a: llamadas.append(a) or True)

    assert llamadas == []
    assert resultado.sheets_used == 0
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/engine/test_progreso.py -q`
Expected: FAIL con `ImportError: cannot import name 'Avance'`

- [ ] **Step 3: Escribir la implementación mínima**

En `src/nesting/engine/packer.py`, agregar después de la definición de `PackResult`:

```python
@dataclass(frozen=True)
class Avance:
    """Dónde va el motor, para quien esté mirando.

    Lleva el intento además de las piezas porque `pack` corre varias pasadas
    completas y CADA UNA REINICIA el conteo de ubicadas. Una barra armada
    sólo con `ubicadas / totales` retrocedería al empezar el intento
    siguiente, y una barra que retrocede es peor que no tener barra.
    """

    intento: int
    intentos: int
    ubicadas: int
    totales: int
    placa: int
    compactando: bool = False


class Cancelado(Exception):
    """El motor abandonó porque quien lo miraba se lo pidió.

    Es una excepción y no un `PackResult` a medias a propósito: un resultado
    incompleto se puede escribir a un DXF sin que nada avise, y ese DXF va a
    una fresadora.
    """
```

Cambiar la firma de `_pack_once` y su cuerpo. Reemplazar:

```python
def _pack_once(
    order: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """One greedy pass, placing `order` in exactly the order given."""
```

por:

```python
def _pack_once(
    order: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    aviso: Callable[[int, int], None] | None = None,
) -> PackResult:
    """One greedy pass, placing `order` in exactly the order given.

    `aviso` recibe (piezas ubicadas hasta ahora en esta pasada, placa en
    curso empezando en 1) despues de cada pieza ubicada. Puede levantar para
    abandonar: esta funcion no atrapa nada, asi que la excepcion sale limpia
    sin dejar estado a medias en el oraculo.
    """
```

Dentro del bucle de `_pack_once`, después de `placed_count += 1`, agregar:

```python
            if aviso is not None:
                aviso(total_ubicadas + placed_count, sheet + 1)
```

Y declarar el acumulador antes del `while remaining:`:

```python
    total_ubicadas = 0
```

y sumarlo al final de cada placa, justo antes de `remaining = still_pending`:

```python
        total_ubicadas += placed_count
```

Cambiar la firma de `pack`:

```python
def pack(
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    progreso: Callable[[Avance], bool] | None = None,
) -> PackResult:
    """Place every part, trying several insertion orders and keeping the best.

    `progreso`, si se pasa, se llama con un `Avance` despues de cada pieza
    ubicada y una vez mas al entrar en la compactacion final. Devolver
    `False` pide abandonar, y `pack` levanta `Cancelado`. No pasarlo deja el
    comportamiento exactamente como estaba: es lo que hace la CLI.
    """
```

Dentro de `pack`, después de `by_area = sorted(...)`, agregar el armador de avisos:

```python
    intentos = EFFORT_RESTARTS[config.effort]
    totales = len(parts)

    def avisos_de(intento: int) -> Callable[[int, int], None] | None:
        if progreso is None:
            return None

        def avisar(ubicadas: int, placa: int) -> None:
            if not progreso(Avance(intento, intentos, ubicadas, totales, placa)):
                raise Cancelado("el trabajo se canceló")

        return avisar
```

Reemplazar la primera pasada:

```python
    best = _pack_once(best_order, material, config, oracle_factory)
```

por:

```python
    best = _pack_once(best_order, material, config, oracle_factory, avisos_de(1))
```

Reemplazar la pasada de cada reintento dentro del `for i in range(...)`:

```python
        candidate = _pack_once(candidate_order, material, config, oracle_factory)
```

por:

```python
        candidate = _pack_once(
            candidate_order, material, config, oracle_factory, avisos_de(i + 2)
        )
```

Y antes de la compactación final:

```python
    best = _compact_last_sheet(best, parts, material, config, oracle_factory)
```

anteponer:

```python
    if progreso is not None and not progreso(
        Avance(intentos, intentos, totales, totales, 0, compactando=True)
    ):
        raise Cancelado("el trabajo se canceló")
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/engine/test_progreso.py -q`
Expected: PASS, 10 tests

- [ ] **Step 5: Correr TODA la suite**

Run: `.venv/bin/python -m pytest -q -p no:warnings`
Expected: PASS. **Ningún test existente puede haber cambiado.** `progreso` es opcional y la CLI no lo pasa.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/engine/packer.py tests/engine/test_progreso.py
git commit -m "pack(): callback de avance y cancelación cooperativa

Único cambio al motor en todo el trabajo de la interfaz. En terminal,
nueve minutos sin señales se bancan; en una ventana es un programa
colgado y el usuario lo mata desde el administrador de tareas.

El Avance lleva el intento además de las piezas porque pack corre varias
pasadas y cada una reinicia el conteo. Una barra que retrocede es peor
que no tener barra.

Cancelar levanta Cancelado en vez de devolver un PackResult a medias: un
resultado incompleto se puede escribir a un DXF sin que nada avise, y ese
DXF va a una fresadora.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: La puerta de plataforma para los archivos

**Files:**
- Create: `src/nesting_app/archivos.py`
- Test: `tests/app/test_archivos.py`

**Interfaces:**
- Consumes: `nesting_app.rutas`
- Produces:
  - `Fuente` (dataclass congelada): `id: str`, `ruta: Path`, `nombre: str`
  - `Deposito` — clase con `registrar_local(ruta: str | Path) -> Fuente`, `registrar_subida(nombre: str, datos: bytes) -> Fuente`, `obtener(fuente_id: str) -> Fuente`, `limpiar() -> None`, `carpeta: Path`
  - `FuenteDesconocidaError(KeyError)`
  - `ExtensionNoSoportadaError(ValueError)`
  - `EXTENSIONES = (".dxf", ".ai", ".3dm")`

**Por qué existe esta tarea:** en escritorio el diálogo nativo devuelve una ruta; en la web llega el contenido subido. Los dos caminos tienen que terminar en el mismo identificador para que nada del resto del sistema sepa dónde está corriendo. **Este es el único archivo de todo el proyecto que conoce esa diferencia.**

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/test_archivos.py`:

```python
"""La puerta que iguala 'una ruta local' y 'un archivo subido'."""

import pytest

from nesting_app.archivos import (
    Deposito,
    ExtensionNoSoportadaError,
    FuenteDesconocidaError,
)


@pytest.fixture
def deposito(tmp_path):
    return Deposito(tmp_path / "trabajo")


def test_una_ruta_local_se_registra_sin_copiar_el_contenido(deposito, tmp_path):
    """En escritorio el archivo ya está en el disco del usuario. Copiarlo
    duplicaría 500 KB por cada análisis sin ganar nada."""
    origen = tmp_path / "robot.ai"
    origen.write_text("%!PS-Adobe", encoding="utf-8")

    fuente = deposito.registrar_local(origen)

    assert fuente.ruta == origen
    assert fuente.nombre == "robot.ai"


def test_una_subida_se_guarda_en_la_carpeta_de_trabajo(deposito):
    fuente = deposito.registrar_subida("robot.ai", b"%!PS-Adobe")

    assert fuente.ruta.read_bytes() == b"%!PS-Adobe"
    assert fuente.ruta.parent.parent == deposito.carpeta
    assert fuente.nombre == "robot.ai"


def test_los_dos_caminos_devuelven_algo_que_se_usa_igual(deposito, tmp_path):
    """Es el punto entero del módulo: de acá para adelante nadie sabe si el
    archivo vino de un diálogo nativo o de un formulario."""
    origen = tmp_path / "a.dxf"
    origen.write_text("0\nSECTION\n", encoding="utf-8")

    local = deposito.registrar_local(origen)
    subida = deposito.registrar_subida("b.dxf", b"0\nSECTION\n")

    for fuente in (local, subida):
        assert deposito.obtener(fuente.id).ruta.is_file()


def test_cada_registro_tiene_su_propio_id(deposito):
    a = deposito.registrar_subida("x.dxf", b"a")
    b = deposito.registrar_subida("x.dxf", b"b")

    assert a.id != b.id
    assert deposito.obtener(a.id).ruta.read_bytes() == b"a"
    assert deposito.obtener(b.id).ruta.read_bytes() == b"b"


def test_un_id_que_no_existe_se_queja(deposito):
    with pytest.raises(FuenteDesconocidaError):
        deposito.obtener("no-existe")


def test_una_ruta_que_no_existe_se_queja_nombrandola(deposito, tmp_path):
    with pytest.raises(FileNotFoundError, match="fantasma.ai"):
        deposito.registrar_local(tmp_path / "fantasma.ai")


@pytest.mark.parametrize("nombre", ["dibujo.cdr", "foto.png", "notas.txt", "sin_extension"])
def test_una_extension_que_el_programa_no_lee_se_rechaza_temprano(deposito, nombre):
    """Rechazar acá le dice al usuario 'este formato no' de una. Dejarlo
    pasar lo hace fallar adentro del lector con un mensaje sobre sintaxis."""
    with pytest.raises(ExtensionNoSoportadaError, match="dxf"):
        deposito.registrar_subida(nombre, b"lo que sea")


def test_la_extension_no_distingue_mayusculas(deposito):
    fuente = deposito.registrar_subida("ROBOT.AI", b"%!PS-Adobe")
    assert fuente.nombre == "ROBOT.AI"


def test_una_subida_no_puede_escribir_fuera_de_la_carpeta(deposito):
    """Un nombre con '..' o con barras es un intento de escribir donde no
    corresponde. En la web eso llega de afuera; acá se corta siempre."""
    fuente = deposito.registrar_subida("../../afuera.dxf", b"x")

    assert deposito.carpeta in fuente.ruta.parents
    assert fuente.ruta.name == "afuera.dxf"


def test_limpiar_borra_todo(deposito):
    deposito.registrar_subida("a.dxf", b"a")
    deposito.limpiar()

    assert not deposito.carpeta.exists()


def test_limpiar_dos_veces_no_revienta(deposito):
    """Se llama al cerrar el programa y al arrancar. Que una de las dos
    encuentre la carpeta vacía es lo normal, no un error."""
    deposito.limpiar()
    deposito.limpiar()
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_archivos.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting_app.archivos'`

- [ ] **Step 3: Escribir la implementación mínima**

Crear `src/nesting_app/archivos.py`:

```python
"""La única parte del programa que sabe si corre en escritorio o en web.

En escritorio, el diálogo nativo devuelve una ruta del disco del usuario y
el archivo ya está ahí. En la web llega el contenido subido y hay que
guardarlo en algún lado. Los dos caminos terminan en un `Fuente` con un id,
y de ahí para adelante nadie vuelve a preguntar de dónde salió.

Mantener esa diferencia encerrada acá es lo que permite que la misma
interfaz y la misma API sirvan en los dos lados.
"""

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

EXTENSIONES = (".dxf", ".ai", ".3dm")
"""Lo que los lectores de `nesting.io` saben abrir.

`.cdr` no está y no va a estar: es formato binario cerrado de Corel, sin
parser libre confiable, y quedó fuera de alcance desde el diseño del motor.
"""


class FuenteDesconocidaError(KeyError):
    """No hay ninguna fuente registrada con ese id."""

    def __str__(self) -> str:
        return self.args[0] if self.args else ""


class ExtensionNoSoportadaError(ValueError):
    """El archivo no es de un formato que este programa sepa leer."""


@dataclass(frozen=True)
class Fuente:
    """Un archivo de entrada listo para leer, venga de donde venga."""

    id: str
    ruta: Path
    nombre: str
    """Cómo se llama para el usuario, que no siempre es `ruta.name`."""


def _verificar_extension(nombre: str) -> None:
    if Path(nombre).suffix.lower() not in EXTENSIONES:
        raise ExtensionNoSoportadaError(
            f"{nombre} no es un formato que este programa pueda leer. "
            f"Se aceptan {', '.join(EXTENSIONES)}. "
            "Un .cdr hay que exportarlo a DXF desde CorelDRAW primero."
        )


class Deposito:
    """Las fuentes vivas de esta corrida del programa."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta)
        self._fuentes: dict[str, Fuente] = {}

    def registrar_local(self, ruta: str | Path) -> Fuente:
        """Una ruta del disco del usuario. No se copia nada.

        El archivo ya existe donde el usuario lo tiene; duplicar medio mega
        por cada análisis no compraría nada.
        """
        ruta = Path(ruta)
        if not ruta.is_file():
            raise FileNotFoundError(f"no existe el archivo {ruta}")
        _verificar_extension(ruta.name)
        return self._registrar(ruta, ruta.name)

    def registrar_subida(self, nombre: str, datos: bytes) -> Fuente:
        """Contenido subido, que hay que guardar en algún lado.

        Cada subida va a su propia subcarpeta con nombre al azar: dos
        archivos que se llamen igual no se pisan, y el nombre que viene de
        afuera nunca se usa para elegir carpeta, sólo hoja.
        """
        _verificar_extension(nombre)
        fuente_id = uuid.uuid4().hex
        destino = self.carpeta / fuente_id
        destino.mkdir(parents=True, exist_ok=True)
        # `Path(nombre).name` descarta cualquier `..` o barra: un nombre que
        # llega de afuera no puede elegir dónde se escribe.
        archivo = destino / Path(nombre).name
        archivo.write_bytes(datos)
        return self._registrar(archivo, nombre, fuente_id=fuente_id)

    def obtener(self, fuente_id: str) -> Fuente:
        try:
            return self._fuentes[fuente_id]
        except KeyError:
            raise FuenteDesconocidaError(
                f"no hay ningún archivo registrado con el id {fuente_id!r}; "
                "puede que el programa se haya reiniciado. Volvé a elegirlo."
            ) from None

    def limpiar(self) -> None:
        """Borra todo lo subido. Se llama al arrancar y al cerrar."""
        shutil.rmtree(self.carpeta, ignore_errors=True)
        self._fuentes.clear()

    def _registrar(self, ruta: Path, nombre: str, fuente_id: str | None = None) -> Fuente:
        fuente = Fuente(id=fuente_id or uuid.uuid4().hex, ruta=ruta, nombre=nombre)
        self._fuentes[fuente.id] = fuente
        return fuente
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/app/test_archivos.py -q`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add src/nesting_app/archivos.py tests/app/test_archivos.py
git commit -m "archivos.py: la única puerta que sabe escritorio contra web

En escritorio el diálogo nativo devuelve una ruta; en web llega contenido
subido. Los dos terminan en un Fuente con id, y de ahí para adelante
nadie pregunta de dónde salió.

Encerrar esa diferencia acá es lo que permite que la misma interfaz y la
misma API sirvan en los dos lados.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: El registro de trabajos y el hilo que los corre

**Files:**
- Create: `src/nesting_app/jobs.py`
- Test: `tests/app/test_jobs.py`

**Interfaces:**
- Consumes: `nesting.params`, `nesting.engine.packer.Avance`, `nesting.engine.packer.Cancelado`, `nesting_app.archivos.Fuente`
- Produces:
  - `Estado` (StrEnum): `PENDIENTE`, `CORRIENDO`, `LISTO`, `CANCELADO`, `ERROR`
  - `Trabajo` (dataclass): `id`, `estado`, `avance: Avance | None`, `avisos: list[str]`, `error: str | None`, `es_bug: bool`, `resultado: Resultado | None`
  - `Resultado` (dataclass congelada): `placas: int`, `aprovechamiento: list[float]`, `total: float`, `segundos: float`, `sobrante_mm: float`, `carpeta: Path`
  - `Registro` — `crear(fuente, params) -> Trabajo`, `obtener(id) -> Trabajo`, `cancelar(id) -> None`, `cerrar() -> None`
  - `TrabajoDesconocidoError(KeyError)`
  - El trabajo real se ejecuta pasándole al `Registro` una función `corredor(fuente, params, progreso) -> Resultado`, para poder testear el registro sin correr el motor.

**Por qué existe esta tarea:** separar "administrar trabajos" de "hacer el trabajo". El registro se puede testear en milisegundos con un corredor falso; el corredor de verdad se testea aparte. Sin esa separación, cada test del ciclo de vida tardaría medio minuto.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/test_jobs.py`:

```python
"""El ciclo de vida de un trabajo, sin correr el motor."""

import threading
import time

import pytest

from nesting.engine.packer import Avance, Cancelado
from nesting_app.archivos import Fuente
from nesting_app.jobs import Estado, Registro, Resultado, TrabajoDesconocidoError
from nesting.params import NestParams

PARAMS = NestParams(material="mdf18")
FUENTE = Fuente(id="f1", ruta=None, nombre="robot.ai")


def resultado_falso(carpeta):
    return Resultado(placas=1, aprovechamiento=[0.477], total=0.477,
                     segundos=1.0, sobrante_mm=708.0, carpeta=carpeta)


def esperar(trabajo, estados, limite=5.0):
    """Espera a que el trabajo llegue a uno de `estados`."""
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if trabajo.estado in estados:
            return trabajo.estado
        time.sleep(0.005)
    raise AssertionError(f"el trabajo quedó en {trabajo.estado}, esperaba {estados}")


@pytest.fixture
def registro(tmp_path):
    r = Registro(tmp_path / "trabajos")
    yield r
    r.cerrar()


def test_un_trabajo_que_termina_queda_listo(registro):
    def corredor(fuente, params, progreso, carpeta):
        return resultado_falso(carpeta)

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    esperar(trabajo, {Estado.LISTO})

    assert trabajo.resultado.placas == 1
    assert trabajo.error is None


def test_el_avance_queda_disponible_mientras_corre(registro):
    suelto = threading.Event()

    def corredor(fuente, params, progreso, carpeta):
        progreso(Avance(intento=1, intentos=3, ubicadas=61, totales=93, placa=1))
        suelto.wait(timeout=5)
        return resultado_falso(carpeta)

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    esperar(trabajo, {Estado.CORRIENDO})
    time.sleep(0.05)

    assert trabajo.avance.ubicadas == 61
    assert trabajo.avance.intentos == 3
    suelto.set()
    esperar(trabajo, {Estado.LISTO})


def test_cancelar_hace_que_el_progreso_devuelva_False(registro):
    """Así es como el motor se entera: el callback le dice que pare."""
    visto = []
    arrancó = threading.Event()

    def corredor(fuente, params, progreso, carpeta):
        arrancó.set()
        for _ in range(200):
            if not progreso(Avance(1, 1, 0, 10, 1)):
                raise Cancelado("cancelado")
            visto.append(1)
            time.sleep(0.005)
        return resultado_falso(carpeta)

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    arrancó.wait(timeout=5)
    registro.cancelar(trabajo.id)
    esperar(trabajo, {Estado.CANCELADO})

    assert trabajo.resultado is None
    assert len(visto) < 200, "tenía que cortar antes de terminar"


def test_cancelar_uno_que_ya_terminó_no_revienta(registro):
    """El usuario puede apretar cancelar justo cuando terminaba. Eso es una
    carrera normal, no un error que deba explotar en la cara de nadie."""
    trabajo = registro.crear(FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c))
    esperar(trabajo, {Estado.LISTO})

    registro.cancelar(trabajo.id)

    assert trabajo.estado is Estado.LISTO


def test_un_error_del_usuario_queda_con_su_mensaje(registro):
    def corredor(fuente, params, progreso, carpeta):
        raise ValueError("el contorno no cierra por 0.8 mm")

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    esperar(trabajo, {Estado.ERROR})

    assert "0.8 mm" in trabajo.error
    assert trabajo.es_bug is False


def test_un_bug_del_programa_se_marca_como_tal(registro):
    """Un error inesperado no puede disfrazarse de 'revisá tu dibujo'.

    La interfaz muestra los dos distinto: uno manda al usuario a corregir
    algo, el otro le dice que el problema es del programa.
    """
    def corredor(fuente, params, progreso, carpeta):
        raise RuntimeError("índice fuera de rango")

    trabajo = registro.crear(FUENTE, PARAMS, corredor)
    esperar(trabajo, {Estado.ERROR})

    assert trabajo.es_bug is True
    assert "índice fuera de rango" in trabajo.error


def test_los_trabajos_corren_de_a_uno(registro):
    """En escritorio la interfaz ya deshabilita el botón, pero la API no
    puede confiar en eso: en la web sí va a llegar más de uno a la vez."""
    corriendo = []
    maximo = []
    traba = threading.Lock()

    def corredor(fuente, params, progreso, carpeta):
        with traba:
            corriendo.append(1)
            maximo.append(len(corriendo))
        time.sleep(0.05)
        with traba:
            corriendo.pop()
        return resultado_falso(carpeta)

    trabajos = [registro.crear(FUENTE, PARAMS, corredor) for _ in range(4)]
    for t in trabajos:
        esperar(t, {Estado.LISTO})

    assert max(maximo) == 1


def test_cada_trabajo_tiene_su_carpeta(registro):
    carpetas = []

    def corredor(fuente, params, progreso, carpeta):
        carpetas.append(carpeta)
        assert carpeta.is_dir()
        return resultado_falso(carpeta)

    a = registro.crear(FUENTE, PARAMS, corredor)
    b = registro.crear(FUENTE, PARAMS, corredor)
    esperar(a, {Estado.LISTO})
    esperar(b, {Estado.LISTO})

    assert carpetas[0] != carpetas[1]


def test_un_id_que_no_existe_se_queja(registro):
    with pytest.raises(TrabajoDesconocidoError):
        registro.obtener("no-existe")


def test_cerrar_borra_las_carpetas(registro, tmp_path):
    trabajo = registro.crear(FUENTE, PARAMS, lambda f, p, pr, c: resultado_falso(c))
    esperar(trabajo, {Estado.LISTO})

    registro.cerrar()

    assert not (tmp_path / "trabajos").exists()
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_jobs.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting_app.jobs'`

- [ ] **Step 3: Escribir la implementación mínima**

Crear `src/nesting_app/jobs.py`:

```python
"""Administrar trabajos. No hacerlos: eso es `corredor.py`.

La separación es deliberada. Con el motor adentro, cada test del ciclo de
vida -- crear, cancelar a mitad, dos a la vez, que el error quede bien
clasificado -- tardaría medio minuto. Con un corredor de mentira tardan
milisegundos, y el corredor de verdad se prueba aparte.

En escritorio corre un hilo. En la web se cambia por una cola de procesos
sin tocar nada de lo que está afuera de este archivo.
"""

import queue
import shutil
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from nesting.engine.packer import Avance, Cancelado
from nesting.params import NestParams
from nesting_app.archivos import Fuente


class Estado(StrEnum):
    PENDIENTE = "pendiente"
    CORRIENDO = "corriendo"
    LISTO = "listo"
    CANCELADO = "cancelado"
    ERROR = "error"


@dataclass(frozen=True)
class Resultado:
    """Lo que se puede contar de un acomodo terminado."""

    placas: int
    aprovechamiento: list[float]
    total: float
    segundos: float
    sobrante_mm: float
    carpeta: Path


@dataclass
class Trabajo:
    id: str
    estado: Estado = Estado.PENDIENTE
    avance: Avance | None = None
    avisos: list[str] = field(default_factory=list)
    error: str | None = None
    es_bug: bool = False
    """Si el error es del programa y no del dibujo del usuario.

    La interfaz los muestra distinto: uno manda a corregir el archivo, el
    otro dice que el problema es nuestro y ofrece copiar el detalle. Mezclar
    los dos hace que la gente busque durante media hora un defecto que no
    está en su dibujo.
    """
    resultado: Resultado | None = None
    detalle_tecnico: str | None = None
    _cancelar: threading.Event = field(default_factory=threading.Event, repr=False)


class TrabajoDesconocidoError(KeyError):
    def __str__(self) -> str:
        return self.args[0] if self.args else ""


Corredor = Callable[[Fuente, NestParams, Callable[[Avance], bool], Path], Resultado]

ERRORES_DEL_USUARIO = (ValueError, OSError, KeyError)
"""Lo que significa 'tu archivo o tus parámetros tienen un problema'.

Los lectores, el pipeline y el empacador levantan estos para lo que el
usuario puede arreglar. Cualquier otra cosa es un bug nuestro.
"""


class Registro:
    """Los trabajos de esta corrida del programa, y el hilo que los ejecuta."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._trabajos: dict[str, Trabajo] = {}
        self._cola: queue.Queue = queue.Queue()
        self._cerrando = threading.Event()
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()

    def crear(self, fuente: Fuente, params: NestParams, corredor: Corredor) -> Trabajo:
        trabajo = Trabajo(id=uuid.uuid4().hex)
        self._trabajos[trabajo.id] = trabajo
        self._cola.put((trabajo, fuente, params, corredor))
        return trabajo

    def obtener(self, trabajo_id: str) -> Trabajo:
        try:
            return self._trabajos[trabajo_id]
        except KeyError:
            raise TrabajoDesconocidoError(
                f"no hay ningún trabajo con el id {trabajo_id!r}"
            ) from None

    def cancelar(self, trabajo_id: str) -> None:
        """Pide abandonar. Que ya haya terminado no es un error.

        El usuario puede apretar cancelar justo cuando terminaba: esa
        carrera es normal y no tiene que explotarle en la cara.
        """
        self.obtener(trabajo_id)._cancelar.set()

    def cerrar(self) -> None:
        self._cerrando.set()
        for trabajo in self._trabajos.values():
            trabajo._cancelar.set()
        self._cola.put(None)
        self._hilo.join(timeout=5)
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def _trabajar(self) -> None:
        while True:
            pedido = self._cola.get()
            if pedido is None:
                return
            trabajo, fuente, params, corredor = pedido
            if trabajo._cancelar.is_set():
                trabajo.estado = Estado.CANCELADO
                continue
            self._correr(trabajo, fuente, params, corredor)

    def _correr(self, trabajo, fuente, params, corredor) -> None:
        trabajo.estado = Estado.CORRIENDO
        propia = self.carpeta / trabajo.id
        propia.mkdir(parents=True, exist_ok=True)

        def progreso(avance: Avance) -> bool:
            trabajo.avance = avance
            return not trabajo._cancelar.is_set()

        try:
            trabajo.resultado = corredor(fuente, params, progreso, propia)
        except Cancelado:
            trabajo.estado = Estado.CANCELADO
        except ERRORES_DEL_USUARIO as error:
            trabajo.error = str(error)
            trabajo.es_bug = False
            trabajo.estado = Estado.ERROR
        except Exception as error:  # noqa: BLE001 - se clasifica y se reporta
            trabajo.error = str(error) or type(error).__name__
            trabajo.detalle_tecnico = traceback.format_exc()
            trabajo.es_bug = True
            trabajo.estado = Estado.ERROR
        else:
            trabajo.estado = Estado.LISTO
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/app/test_jobs.py -q`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
git add src/nesting_app/jobs.py tests/app/test_jobs.py
git commit -m "jobs.py: administrar trabajos, separado de hacerlos

Con el motor adentro, cada test del ciclo de vida tardaría medio minuto.
Con un corredor de mentira tardan milisegundos, y el corredor de verdad
se prueba aparte.

Un error inesperado se marca como bug del programa, no como 'revisá tu
dibujo'. Mezclarlos hace que la gente busque media hora un defecto que
no está en su archivo.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: El corredor de verdad, que sí usa el motor

**Files:**
- Create: `src/nesting_app/corredor.py`
- Test: `tests/app/test_corredor.py`

**Interfaces:**
- Consumes: todo el pipeline del motor, `nesting_app.jobs.Resultado`, `nesting_app.materials_store`
- Produces:
  - `analizar(fuente: Fuente, unidades: str | None, tol_cierre: float) -> Analisis`
  - `Analisis` (dataclass congelada): `piezas: int`, `avisos: list[str]`, `descartes: list[dict]`, `unidades: str`
  - `acomodar(fuente, params, progreso, carpeta) -> Resultado` — la firma de `Corredor`
  - `VerificacionFallidaError(ValueError)` con atributo `violaciones: list[str]`
  - `UnidadesNoDeclaradasError(ValueError)` — reexporta `UnknownUnitsError` con el contexto de la interfaz
  - Escribe en `carpeta`: `salida.dxf`, `preview.png`, `diagnostico.png`

**Por qué existe esta tarea:** es el puente entre el registro de trabajos y el motor. Se prueba aparte del registro porque acá los tests sí tardan.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/test_corredor.py`:

```python
"""El corredor: de un archivo de entrada a un DXF acomodado."""

import ezdxf
import pytest

from nesting.params import NestParams
from nesting_app import corredor
from nesting_app.archivos import Deposito


@pytest.fixture(autouse=True)
def catalogo_aislado(tmp_path, monkeypatch):
    from nesting_app import materials_store, rutas

    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    materials_store.leer()


@pytest.fixture
def deposito(tmp_path):
    return Deposito(tmp_path / "fuentes")


def dxf_con(tmp_path, cuadrados, unidades=4, nombre="entrada.dxf"):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = unidades
    msp = doc.modelspace()
    for x, y, lado in cuadrados:
        msp.add_lwpolyline(
            [(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado)], close=True
        )
    ruta = tmp_path / nombre
    doc.saveas(ruta)
    return ruta


def params(**cambios):
    return NestParams(material="mdf18", esfuerzo="rapido", **cambios)


def test_analizar_cuenta_las_piezas(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))

    analisis = corredor.analizar(fuente, unidades=None, tol_cierre=0.1)

    assert analisis.piezas == 2
    assert analisis.unidades == "mm"


def test_analizar_devuelve_los_descartes_dibujables(tmp_path, deposito):
    """Es lo que alimenta el link '3 descartes' de la pantalla principal."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (200, 0), (200, 200), (0, 200)], close=True)
    msp.add_line((400, 400), (412, 400))
    ruta = tmp_path / "sucio.dxf"
    doc.saveas(ruta)
    fuente = deposito.registrar_local(ruta)

    analisis = corredor.analizar(fuente, unidades=None, tol_cierre=0.1)

    assert len(analisis.descartes) == 1
    assert analisis.descartes[0]["motivo"] == "suelta"
    assert "12.000 mm" in analisis.descartes[0]["detalle"]


def test_analizar_un_archivo_sin_unidades_se_queja_de_forma_reconocible(tmp_path, deposito):
    """La interfaz atrapa justo este error para mostrar la pregunta con los
    cinco botones, así que tiene que poder distinguirlo de cualquier otro."""
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 100)], unidades=0))

    with pytest.raises(corredor.UnidadesNoDeclaradasError):
        corredor.analizar(fuente, unidades=None, tol_cierre=0.1)


def test_analizar_con_unidades_dadas_sigue_adelante(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 100)], unidades=0))

    analisis = corredor.analizar(fuente, unidades="mm", tol_cierre=0.1)

    assert analisis.piezas == 1


def test_acomodar_escribe_los_tres_archivos(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))
    salida = tmp_path / "trabajo"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert (salida / "salida.dxf").is_file()
    assert (salida / "preview.png").is_file()
    assert (salida / "diagnostico.png").is_file()
    assert resultado.placas == 1
    assert resultado.carpeta == salida


def test_acomodar_informa_el_sobrante(tmp_path, deposito):
    """Es el número que el usuario va a mirar primero: cuánta placa le queda
    entera para el próximo trabajo."""
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert resultado.sobrante_mm > 2000


def test_acomodar_llama_al_progreso(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))
    salida = tmp_path / "t"
    salida.mkdir()
    avances = []

    corredor.acomodar(fuente, params(), lambda a: avances.append(a) or True, salida)

    assert avances
    assert avances[0].totales == 2


def test_acomodar_respeta_las_copias(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()
    avances = []

    corredor.acomodar(fuente, params(copias=3), lambda a: avances.append(a) or True, salida)

    assert avances[0].totales == 3


def test_si_la_verificacion_falla_no_queda_ningun_dxf(tmp_path, deposito, monkeypatch):
    """Es la regla más dura del motor y no se ablanda acá: un layout no
    verificado no se escribe, porque ese archivo va a una fresadora."""
    from nesting.geometry.verify import Violation

    monkeypatch.setattr(
        corredor, "verify",
        lambda *a, **k: [Violation(detail="las piezas 1 y 2 se pisan")],
    )
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    with pytest.raises(corredor.VerificacionFallidaError) as capturado:
        corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert "se pisan" in capturado.value.violaciones[0]
    assert not (salida / "salida.dxf").exists()


def test_el_contorno_de_placa_se_descarta_igual_que_en_la_cli(tmp_path, deposito):
    """Los archivos reales del usuario traen dibujado el rectángulo de la
    placa. Si la interfaz no lo descartara, fallaría donde la CLI anda."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (1830, 0), (1830, 2600), (0, 2600)], close=True)
    msp.add_lwpolyline([(2000, 0), (2100, 0), (2100, 100), (2000, 100)], close=True)
    ruta = tmp_path / "con_placa.dxf"
    doc.saveas(ruta)
    fuente = deposito.registrar_local(ruta)
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(fuente, params(), lambda a: True, salida)

    assert resultado.placas == 1
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_corredor.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting_app.corredor'`

- [ ] **Step 3: Escribir la implementación mínima**

Crear `src/nesting_app/corredor.py`:

```python
"""De un archivo de entrada a un DXF acomodado, con sus dos imágenes.

Es el mismo recorrido que hace `cli.py`, con dos diferencias: informa el
avance, y deja los resultados en una carpeta en vez de donde el usuario
dijo. Guardar donde el usuario quiere es un paso posterior y explícito.
"""

from dataclasses import dataclass
from pathlib import Path

from nesting.engine.packer import Avance, layout_cost, pack, replicate
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.geometry.verify import verify
from nesting.io.ai_reader import read_ai
from nesting.io.diagnostic import write_diagnostic
from nesting.io.dxf_reader import UnknownUnitsError, read_dxf
from nesting.io.dxf_writer import write_dxf
from nesting.io.preview import write_preview
from nesting.io.rhino_reader import read_3dm
from nesting.model.discard import Discard
from nesting.params import NestParams, a_config
from nesting.pipeline import discard_plate_outline, prepare_parts
from nesting_app import materials_store
from nesting_app.archivos import Fuente
from nesting_app.jobs import Resultado

NOMBRE_DXF = "salida.dxf"
NOMBRE_PREVIEW = "preview.png"
NOMBRE_DIAGNOSTICO = "diagnostico.png"


class UnidadesNoDeclaradasError(ValueError):
    """El archivo no dice en qué unidades está.

    Se distingue del resto a propósito: en la CLI es un error y en la
    interfaz es una pregunta con cinco botones. Que tenga su propio tipo es
    lo que le permite a la API mostrar la pregunta en vez del error.
    """


class VerificacionFallidaError(ValueError):
    """El árbitro geométrico encontró el acomodo inválido.

    No se escribió ningún archivo, y eso es lo primero que hay que decirle
    al usuario: lo que va a la fresadora no puede salir de un layout que no
    verificó.
    """

    def __init__(self, violaciones: list[str]) -> None:
        super().__init__(
            f"la verificación geométrica encontró {len(violaciones)} problema(s). "
            "No se escribió ningún archivo."
        )
        self.violaciones = violaciones


@dataclass(frozen=True)
class Analisis:
    """Lo que se sabe del archivo antes de acomodar nada."""

    piezas: int
    avisos: list[str]
    descartes: list[dict]
    unidades: str


def _leer(fuente: Fuente, unidades: str | None):
    sufijo = fuente.ruta.suffix.lower()
    try:
        if sufijo == ".ai":
            return read_ai(fuente.ruta)
        if sufijo == ".3dm":
            return read_3dm(fuente.ruta, units_override=unidades)
        return read_dxf(fuente.ruta, units_override=unidades)
    except UnknownUnitsError as error:
        raise UnidadesNoDeclaradasError(str(error)) from error


def _a_dict(descarte: Discard) -> dict:
    """Un descarte en la forma que la interfaz sabe dibujar."""
    centro = descarte.centroid
    return {
        "motivo": descarte.reason,
        "etiqueta": descarte.style.label,
        "color": list(descarte.style.color),
        "detalle": descarte.detail,
        "puntos": [list(p) for p in descarte.path],
        "centro": list(centro) if centro else None,
    }


def analizar(fuente: Fuente, unidades: str | None, tol_cierre: float) -> Analisis:
    """Lee el archivo y cuenta qué hay, sin acomodar nada. Tarda ~1 segundo."""
    drawing = _leer(fuente, unidades)
    piezas, avisos, descartes = prepare_parts(drawing, chain_tol=tol_cierre)
    return Analisis(
        piezas=len(piezas),
        avisos=list(avisos),
        descartes=[_a_dict(d) for d in descartes],
        unidades=drawing.source_units,
    )


def acomodar(
    fuente: Fuente,
    params: NestParams,
    progreso,
    carpeta: Path,
) -> Resultado:
    """El recorrido completo. Deja tres archivos en `carpeta`."""
    materiales = materials_store.leer()
    material = materiales[params.material]

    drawing = _leer(fuente, params.unidades)
    piezas, avisos, descartes = prepare_parts(drawing, chain_tol=params.tol_cierre)
    piezas, contornos_placa = discard_plate_outline(
        piezas, material.sheet_w, material.sheet_h
    )
    if contornos_placa:
        avisos.append(
            f"se ignoraron {len(contornos_placa)} rectángulo(s) del tamaño exacto "
            f"de la placa; si alguno era una pieza de verdad, hay que cambiarle "
            "el tamaño."
        )
        descartes.extend(
            Discard(
                reason="contorno_placa",
                points=parte.outer,
                detail=f"{material.sheet_w:.0f} x {material.sheet_h:.0f} mm",
                closed=True,
            )
            for parte in contornos_placa
        )

    write_diagnostic(carpeta / NOMBRE_DIAGNOSTICO, piezas, descartes)

    if not piezas:
        raise ValueError(
            f"no se encontró ninguna pieza en {fuente.nombre}. "
            "Mirá la revisión para ver qué se descartó y por qué."
        )

    piezas = replicate(piezas, params.copias)
    config = a_config(params)
    cache = MaskCache()
    resultado = pack(
        piezas, material, config, lambda: RasterOracle(cache=cache), progreso=progreso
    )

    violaciones = verify(
        piezas, resultado.placements, material.sheet_w, material.sheet_h,
        sep=config.sep, margin=config.margin,
    )
    if violaciones:
        # Antes de escribir nada, y sin escribir nada. Esta es la regla más
        # dura del motor y no se ablanda por venir de una interfaz.
        raise VerificacionFallidaError([v.detail for v in violaciones])

    write_dxf(
        carpeta / NOMBRE_DXF, drawing, piezas, resultado.placements,
        material.sheet_w, material.sheet_h,
    )
    write_preview(
        carpeta / NOMBRE_PREVIEW, piezas, resultado.placements,
        material.sheet_w, material.sheet_h, resultado.utilization,
        colors=_colores(drawing, piezas),
    )

    _, alto_usado = layout_cost(resultado, piezas)
    return Resultado(
        placas=resultado.sheets_used,
        aprovechamiento=list(resultado.utilization),
        total=resultado.total_utilization,
        segundos=resultado.seconds,
        sobrante_mm=material.sheet_h - alto_usado,
        carpeta=carpeta,
    )


def _colores(drawing, piezas) -> dict[int, tuple[int, int, int]]:
    """El color de la primera entidad de cada pieza, para la previsualización."""
    colores: dict[int, tuple[int, int, int]] = {}
    for pieza in piezas:
        if not pieza.entity_ids:
            continue
        rgb = drawing.entities[pieza.entity_ids[0]].style.rgb
        if rgb is not None:
            colores[pieza.id] = rgb
    return colores
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/app/test_corredor.py -q`
Expected: PASS, 10 tests

- [ ] **Step 5: Correr TODA la suite**

Run: `.venv/bin/python -m pytest -q -p no:warnings`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app/corredor.py tests/app/test_corredor.py
git commit -m "corredor.py: el pipeline completo, informando avance

Mismo recorrido que cli.py con dos diferencias: informa el avance, y deja
los resultados en una carpeta en vez de donde el usuario dijo. Guardar
donde el usuario quiere es un paso posterior y explícito.

La verificación geométrica sigue siendo condición para escribir: un
layout que no verificó no produce archivo, venga de donde venga el
pedido.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: La API — servidor, token, materiales, archivos y análisis

**Files:**
- Create: `src/nesting_app/api.py`
- Test: `tests/app/test_api_materiales.py`, `tests/app/test_api_archivos.py`

**Interfaces:**
- Consumes: `materials_store`, `archivos.Deposito`, `corredor`, `rutas`
- Produces:
  - `crear_app(token: str, deposito: Deposito, registro: Registro) -> FastAPI`
  - Rutas: `GET/POST /api/materiales`, `PUT/DELETE /api/materiales/{nombre}`, `POST /api/materiales/restaurar`, `POST /api/archivos`, `POST /api/archivos/local`, `POST /api/analizar`
  - La interfaz estática se sirve en `/`
  - Todo pedido a `/api/` exige la cabecera `X-Token`

**Por qué el token:** el servidor escucha en `127.0.0.1`, pero eso no lo protege de una página abierta en el navegador del usuario, que también puede hablarle a localhost. Sin token, cualquier sitio podría mandarle trabajos al programa y leer las rutas de sus archivos.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/test_api_materiales.py`:

```python
"""Las rutas de materiales, y el token que protege todas las rutas."""

import pytest
from fastapi.testclient import TestClient

from nesting_app import materials_store, rutas
from nesting_app.api import crear_app
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro

TOKEN = "token-de-prueba"


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    registro = Registro(tmp_path / "trabajos")
    app = crear_app(TOKEN, Deposito(tmp_path / "fuentes"), registro)
    with TestClient(app) as c:
        c.headers["X-Token"] = TOKEN
        yield c
    registro.cerrar()


def test_sin_token_no_se_puede_hacer_nada(cliente):
    """El servidor escucha en localhost, pero cualquier página abierta en el
    navegador del usuario también puede hablarle a localhost."""
    del cliente.headers["X-Token"]

    assert cliente.get("/api/materiales").status_code == 401


def test_con_un_token_equivocado_tampoco(cliente):
    cliente.headers["X-Token"] = "otro"

    assert cliente.get("/api/materiales").status_code == 401


def test_listar_devuelve_el_catalogo_sembrado(cliente):
    datos = cliente.get("/api/materiales").json()

    nombres = [m["nombre"] for m in datos["materiales"]]
    assert "mdf18" in nombres
    assert "multilam18" in nombres


def test_cada_material_dice_su_veta_en_palabras(cliente):
    """La interfaz muestra dos opciones con nombre, nunca un número de
    grados. La traducción vive en la API para que no la haga el JavaScript."""
    datos = cliente.get("/api/materiales").json()
    por_nombre = {m["nombre"]: m for m in datos["materiales"]}

    assert por_nombre["mdf18"]["veta"] == "libre"
    assert por_nombre["multilam18"]["veta"] == "respetar"


def test_agregar(cliente):
    respuesta = cliente.post("/api/materiales", json={
        "nombre": "melamina18", "ancho": 1830, "alto": 2750, "veta": "libre",
    })

    assert respuesta.status_code == 200
    assert "melamina18" in [m["nombre"] for m in cliente.get("/api/materiales").json()["materiales"]]


def test_agregar_uno_repetido_da_409_con_mensaje(cliente):
    respuesta = cliente.post("/api/materiales", json={
        "nombre": "mdf18", "ancho": 100, "alto": 100, "veta": "libre",
    })

    assert respuesta.status_code == 409
    assert "mdf18" in respuesta.json()["detail"]


@pytest.mark.parametrize("campo, valor", [("ancho", 0), ("alto", -5), ("ancho", 0.0)])
def test_una_medida_que_no_es_positiva_se_rechaza(cliente, campo, valor):
    """Una placa de ancho cero no es un material, y dejarla entrar haría
    reventar el motor mucho más tarde con un mensaje que no la nombra."""
    cuerpo = {"nombre": "raro", "ancho": 100, "alto": 100, "veta": "libre"}
    cuerpo[campo] = valor

    assert cliente.post("/api/materiales", json=cuerpo).status_code == 422


def test_un_nombre_vacio_se_rechaza(cliente):
    respuesta = cliente.post("/api/materiales", json={
        "nombre": "  ", "ancho": 100, "alto": 100, "veta": "libre",
    })

    assert respuesta.status_code == 422


def test_una_veta_inventada_se_rechaza(cliente):
    respuesta = cliente.post("/api/materiales", json={
        "nombre": "raro", "ancho": 100, "alto": 100, "veta": "a_veces",
    })

    assert respuesta.status_code == 422


def test_editar(cliente):
    respuesta = cliente.put("/api/materiales/mdf18", json={
        "nombre": "mdf18", "ancho": 1830, "alto": 2750, "veta": "libre",
    })

    assert respuesta.status_code == 200
    assert materials_store.leer()["mdf18"].sheet_h == 2750.0


def test_editar_uno_que_no_existe_da_404(cliente):
    respuesta = cliente.put("/api/materiales/fantasma", json={
        "nombre": "fantasma", "ancho": 100, "alto": 100, "veta": "libre",
    })

    assert respuesta.status_code == 404


def test_borrar(cliente):
    assert cliente.delete("/api/materiales/mdf15").status_code == 200
    assert "mdf15" not in materials_store.leer()


def test_borrar_uno_que_no_existe_da_404(cliente):
    assert cliente.delete("/api/materiales/fantasma").status_code == 404


def test_restaurar(cliente):
    cliente.delete("/api/materiales/mdf18")

    assert cliente.post("/api/materiales/restaurar").status_code == 200
    assert "mdf18" in materials_store.leer()


def test_un_catalogo_corrupto_da_500_con_la_salida_adentro(cliente):
    """El mensaje tiene que nombrar la salida, porque el usuario no tiene
    ninguna otra forma de saber que se puede restaurar."""
    materials_store.ruta_catalogo().write_text("roto: [\n", encoding="utf-8")

    respuesta = cliente.get("/api/materiales")

    assert respuesta.status_code == 500
    assert "restaurar" in respuesta.json()["detail"].lower()
```

Crear `tests/app/test_api_archivos.py`:

```python
"""Registrar un archivo y analizarlo, por las dos puertas."""

import ezdxf
import pytest
from fastapi.testclient import TestClient

from nesting_app import rutas
from nesting_app.api import crear_app
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro

TOKEN = "token-de-prueba"


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    registro = Registro(tmp_path / "trabajos")
    app = crear_app(TOKEN, Deposito(tmp_path / "fuentes"), registro)
    with TestClient(app) as c:
        c.headers["X-Token"] = TOKEN
        yield c
    registro.cerrar()


def dxf(tmp_path, unidades=4, nombre="entrada.dxf"):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = unidades
    doc.modelspace().add_lwpolyline([(0, 0), (200, 0), (200, 200), (0, 200)], close=True)
    ruta = tmp_path / nombre
    doc.saveas(ruta)
    return ruta


def test_registrar_una_ruta_local(cliente, tmp_path):
    respuesta = cliente.post("/api/archivos/local", json={"ruta": str(dxf(tmp_path))})

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "entrada.dxf"
    assert respuesta.json()["id"]


def test_registrar_una_subida(cliente, tmp_path):
    datos = dxf(tmp_path).read_bytes()

    respuesta = cliente.post(
        "/api/archivos", files={"archivo": ("entrada.dxf", datos, "application/dxf")}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "entrada.dxf"


def test_las_dos_puertas_dan_algo_que_se_analiza_igual(cliente, tmp_path):
    ruta = dxf(tmp_path)
    local = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()
    subido = cliente.post(
        "/api/archivos", files={"archivo": ("entrada.dxf", ruta.read_bytes(), "application/dxf")}
    ).json()

    for fuente in (local, subido):
        analisis = cliente.post("/api/analizar", json={"fuente_id": fuente["id"]}).json()
        assert analisis["piezas"] == 1


def test_una_ruta_que_no_existe_da_404(cliente, tmp_path):
    respuesta = cliente.post("/api/archivos/local", json={"ruta": str(tmp_path / "no.dxf")})

    assert respuesta.status_code == 404


def test_un_cdr_se_rechaza_con_un_mensaje_util(cliente):
    """Es el caso real: el usuario tiene .cdr y hay que decirle qué hacer,
    no sólo que no."""
    respuesta = cliente.post(
        "/api/archivos", files={"archivo": ("dibujo.cdr", b"RIFF", "application/octet-stream")}
    )

    assert respuesta.status_code == 415
    assert "CorelDRAW" in respuesta.json()["detail"]


def test_analizar_devuelve_piezas_avisos_y_descartes(cliente, tmp_path):
    fuente = cliente.post("/api/archivos/local", json={"ruta": str(dxf(tmp_path))}).json()

    analisis = cliente.post("/api/analizar", json={"fuente_id": fuente["id"]}).json()

    assert analisis["piezas"] == 1
    assert analisis["avisos"] == []
    assert analisis["descartes"] == []
    assert analisis["unidades"] == "mm"


def test_analizar_un_archivo_sin_unidades_pide_las_unidades(cliente, tmp_path):
    """No es un error: es una pregunta. El código 409 y la marca
    `faltan_unidades` son lo que le dice a la interfaz que muestre los cinco
    botones en vez de un cartel rojo."""
    ruta = dxf(tmp_path, unidades=0, nombre="sin_unidades.dxf")
    fuente = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()

    respuesta = cliente.post("/api/analizar", json={"fuente_id": fuente["id"]})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["faltan_unidades"] is True


def test_analizar_con_las_unidades_dadas_funciona(cliente, tmp_path):
    ruta = dxf(tmp_path, unidades=0, nombre="sin_unidades.dxf")
    fuente = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()

    analisis = cliente.post(
        "/api/analizar", json={"fuente_id": fuente["id"], "unidades": "mm"}
    ).json()

    assert analisis["piezas"] == 1


def test_analizar_un_id_inventado_da_404(cliente):
    respuesta = cliente.post("/api/analizar", json={"fuente_id": "no-existe"})

    assert respuesta.status_code == 404


def test_la_interfaz_se_sirve_en_la_raiz(cliente):
    """Sin token: es la página que trae el token adentro."""
    del cliente.headers["X-Token"]

    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "<!doctype html>" in respuesta.text.lower()
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/python -m pytest tests/app/test_api_materiales.py tests/app/test_api_archivos.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting_app.api'`

- [ ] **Step 3: Escribir la implementación mínima**

Crear `src/nesting_app/api.py`:

```python
"""Las rutas HTTP. La misma API sirve en escritorio y en la web.

El servidor escucha sólo en 127.0.0.1, pero eso no alcanza: cualquier
página abierta en el navegador del usuario también puede hablarle a
localhost. Por eso toda ruta bajo /api/ exige un token que sólo conoce la
ventana, porque se lo pasamos al cargarla.
"""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from nesting.model.material import Material
from nesting_app import corredor, materials_store, rutas
from nesting_app.archivos import (
    Deposito,
    ExtensionNoSoportadaError,
    FuenteDesconocidaError,
)
from nesting_app.jobs import Registro

VETA_POR_NOMBRE = {
    "libre": materials_store.VETA_LIBRE,
    "respetar": materials_store.VETA_RESPETAR,
}


def _nombre_de_veta(grados: float) -> str:
    """De grados a la palabra que muestra la interfaz.

    Cualquier valor de 90 o más equivale a rotación libre, por cómo se
    calcula la distancia al eje de veta. La traducción vive acá para que el
    JavaScript no tenga que saber esa regla.
    """
    return "libre" if grados >= 90 else "respetar"


class MaterialEntrada(BaseModel):
    nombre: str
    ancho: float = Field(gt=0)
    alto: float = Field(gt=0)
    veta: Literal["libre", "respetar"]

    @field_validator("nombre")
    @classmethod
    def _nombre_no_vacio(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("el material necesita un nombre")
        return limpio

    def a_material(self) -> Material:
        return Material(
            name=self.nombre,
            sheet_w=self.ancho,
            sheet_h=self.alto,
            grain_tolerance=VETA_POR_NOMBRE[self.veta],
        )


class RutaLocal(BaseModel):
    ruta: str


class PedidoAnalisis(BaseModel):
    fuente_id: str
    unidades: str | None = None
    tol_cierre: float = Field(default=0.1, gt=0)


def crear_app(token: str, deposito: Deposito, registro: Registro) -> FastAPI:
    app = FastAPI(title="nesting", docs_url=None, redoc_url=None)

    def exigir_token(x_token: Annotated[str | None, Header()] = None) -> None:
        if x_token != token:
            raise HTTPException(status_code=401, detail="token inválido o ausente")

    protegido = [Depends(exigir_token)]

    # --- materiales ---------------------------------------------------------

    @app.get("/api/materiales", dependencies=protegido)
    def listar_materiales() -> dict:
        try:
            materiales = materials_store.leer()
        except ValueError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {
            "materiales": [
                {
                    "nombre": m.name,
                    "ancho": m.sheet_w,
                    "alto": m.sheet_h,
                    "veta": _nombre_de_veta(m.grain_tolerance),
                }
                for m in sorted(materiales.values(), key=lambda m: m.name)
            ]
        }

    @app.post("/api/materiales", dependencies=protegido)
    def agregar_material(entrada: MaterialEntrada) -> dict:
        try:
            materials_store.agregar(entrada.a_material())
        except materials_store.MaterialDuplicadoError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"ok": True}

    @app.put("/api/materiales/{nombre}", dependencies=protegido)
    def editar_material(nombre: str, entrada: MaterialEntrada) -> dict:
        try:
            materials_store.editar(nombre, entrada.a_material())
        except materials_store.MaterialDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except materials_store.MaterialDuplicadoError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"ok": True}

    @app.delete("/api/materiales/{nombre}", dependencies=protegido)
    def borrar_material(nombre: str) -> dict:
        try:
            materials_store.borrar(nombre)
        except materials_store.MaterialDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"ok": True}

    @app.post("/api/materiales/restaurar", dependencies=protegido)
    def restaurar_materiales() -> dict:
        materials_store.restaurar()
        return {"ok": True}

    # --- archivos -----------------------------------------------------------

    @app.post("/api/archivos/local", dependencies=protegido)
    def registrar_local(pedido: RutaLocal) -> dict:
        try:
            fuente = deposito.registrar_local(pedido.ruta)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ExtensionNoSoportadaError as error:
            raise HTTPException(status_code=415, detail=str(error)) from error
        return {"id": fuente.id, "nombre": fuente.nombre}

    @app.post("/api/archivos", dependencies=protegido)
    async def subir_archivo(archivo: Annotated[UploadFile, File()]) -> dict:
        try:
            fuente = deposito.registrar_subida(
                archivo.filename or "sin_nombre", await archivo.read()
            )
        except ExtensionNoSoportadaError as error:
            raise HTTPException(status_code=415, detail=str(error)) from error
        return {"id": fuente.id, "nombre": fuente.nombre}

    # --- análisis -----------------------------------------------------------

    @app.post("/api/analizar", dependencies=protegido)
    def analizar(pedido: PedidoAnalisis) -> dict:
        try:
            fuente = deposito.obtener(pedido.fuente_id)
        except FuenteDesconocidaError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        try:
            analisis = corredor.analizar(fuente, pedido.unidades, pedido.tol_cierre)
        except corredor.UnidadesNoDeclaradasError as error:
            # 409 y no 400: no es que el pedido esté mal armado, es que falta
            # un dato que sólo el usuario puede dar. La interfaz lo distingue
            # por la marca y muestra la pregunta con los cinco botones.
            raise HTTPException(
                status_code=409,
                detail={"faltan_unidades": True, "mensaje": str(error)},
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "piezas": analisis.piezas,
            "avisos": analisis.avisos,
            "descartes": analisis.descartes,
            "unidades": analisis.unidades,
        }

    _montar_interfaz(app)
    return app


def _montar_interfaz(app: FastAPI) -> None:
    """La interfaz estática, servida desde la raíz.

    Va al final para que ninguna ruta de /api/ quede tapada por el montaje.
    """
    web = rutas.recurso("web")
    app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
```

- [ ] **Step 4: Crear un `index.html` mínimo para que el montaje funcione**

`src/nesting_app/web/index.html`:

```html
<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><title>Nesting</title></head>
<body></body>
</html>
```

Y borrar el `.gitkeep` que había quedado de la Task 2.

- [ ] **Step 5: Correr los tests y verlos pasar**

Run: `.venv/bin/python -m pytest tests/app/test_api_materiales.py tests/app/test_api_archivos.py -q`
Expected: PASS, 25 tests

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app/api.py src/nesting_app/web/index.html tests/app/test_api_materiales.py tests/app/test_api_archivos.py
git rm --cached src/nesting_app/web/.gitkeep 2>/dev/null || true
git commit -m "API: token, materiales, archivos y análisis

Todo pedido a /api/ exige un token. Escuchar sólo en 127.0.0.1 no alcanza:
cualquier página abierta en el navegador del usuario también puede
hablarle a localhost.

Un archivo sin unidades declaradas devuelve 409 con faltan_unidades, no
400: no es un pedido mal armado, es un dato que sólo el usuario puede
dar. La interfaz lo distingue para mostrar la pregunta y no un error.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: La API — trabajos y sus archivos

**Files:**
- Modify: `src/nesting_app/api.py`
- Test: `tests/app/test_api_trabajos.py`

**Interfaces:**
- Produces, agregadas a `crear_app`:
  - `POST /api/trabajos` → `{"id": str}`
  - `GET /api/trabajos/{id}` → `{"estado", "avance", "avisos", "error", "es_bug", "resultado"}`
  - `POST /api/trabajos/{id}/cancelar`
  - `GET /api/trabajos/{id}/salida.dxf`, `/preview.png`, `/diagnostico.png`

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/test_api_trabajos.py`:

```python
"""El ciclo de un trabajo, de punta a punta y con el motor de verdad."""

import time

import ezdxf
import pytest
from fastapi.testclient import TestClient

from nesting_app import rutas
from nesting_app.api import crear_app
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro

TOKEN = "token-de-prueba"


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    registro = Registro(tmp_path / "trabajos")
    app = crear_app(TOKEN, Deposito(tmp_path / "fuentes"), registro)
    with TestClient(app) as c:
        c.headers["X-Token"] = TOKEN
        yield c
    registro.cerrar()


def fuente_de(cliente, tmp_path, cuadrados=((0, 0, 200), (300, 0, 150))):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    msp = doc.modelspace()
    for x, y, lado in cuadrados:
        msp.add_lwpolyline(
            [(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado)], close=True
        )
    ruta = tmp_path / "entrada.dxf"
    doc.saveas(ruta)
    return cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()["id"]


def esperar(cliente, trabajo_id, estados, limite=60.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        cuerpo = cliente.get(f"/api/trabajos/{trabajo_id}").json()
        if cuerpo["estado"] in estados:
            return cuerpo
        time.sleep(0.02)
    raise AssertionError(f"quedó en {cuerpo['estado']}, esperaba {estados}")


def test_el_ciclo_completo(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)

    creado = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id,
        "params": {"material": "mdf18", "sep": 3, "esfuerzo": "rapido"},
    })
    assert creado.status_code == 200

    cuerpo = esperar(cliente, creado.json()["id"], {"listo"})

    assert cuerpo["resultado"]["placas"] == 1
    assert 0 < cuerpo["resultado"]["total"] <= 1
    assert cuerpo["resultado"]["sobrante_mm"] > 0
    assert cuerpo["error"] is None


def test_los_tres_archivos_se_pueden_bajar(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "rapido"},
    }).json()["id"]
    esperar(cliente, trabajo_id, {"listo"})

    for nombre, arranque in [
        ("salida.dxf", b"  0\r\nSECTION"),
        ("preview.png", b"\x89PNG"),
        ("diagnostico.png", b"\x89PNG"),
    ]:
        respuesta = cliente.get(f"/api/trabajos/{trabajo_id}/{nombre}")
        assert respuesta.status_code == 200, nombre
        assert respuesta.content[:4] == arranque[:4], nombre


def test_un_parametro_invalido_se_rechaza_nombrando_el_campo(cliente, tmp_path):
    """La interfaz pone el mensaje debajo del campo que lo tiene mal, así que
    necesita saber cuál es -- no alcanza con el texto."""
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "sep": -5},
    })

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["campo"] == "sep"


def test_un_material_que_no_existe_da_404(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "inventado"},
    })

    assert respuesta.status_code == 404


def test_cancelar_deja_el_trabajo_cancelado(cliente, tmp_path):
    """Con muchas piezas y esfuerzo lento hay tiempo de sobra para cortar."""
    cuadrados = [(i * 60 % 1500, (i * 60 // 1500) * 60, 50) for i in range(120)]
    fuente_id = fuente_de(cliente, tmp_path, cuadrados)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "lento"},
    }).json()["id"]

    esperar(cliente, trabajo_id, {"corriendo"})
    assert cliente.post(f"/api/trabajos/{trabajo_id}/cancelar").status_code == 200

    cuerpo = esperar(cliente, trabajo_id, {"cancelado"})
    assert cuerpo["resultado"] is None


def test_un_trabajo_cancelado_no_deja_archivos_para_bajar(cliente, tmp_path):
    cuadrados = [(i * 60 % 1500, (i * 60 // 1500) * 60, 50) for i in range(120)]
    fuente_id = fuente_de(cliente, tmp_path, cuadrados)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "lento"},
    }).json()["id"]
    esperar(cliente, trabajo_id, {"corriendo"})
    cliente.post(f"/api/trabajos/{trabajo_id}/cancelar")
    esperar(cliente, trabajo_id, {"cancelado"})

    assert cliente.get(f"/api/trabajos/{trabajo_id}/salida.dxf").status_code == 409


def test_el_avance_se_ve_mientras_corre(cliente, tmp_path):
    cuadrados = [(i * 60 % 1500, (i * 60 // 1500) * 60, 50) for i in range(120)]
    fuente_id = fuente_de(cliente, tmp_path, cuadrados)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "lento"},
    }).json()["id"]

    fin = time.monotonic() + 30
    visto = None
    while time.monotonic() < fin:
        cuerpo = cliente.get(f"/api/trabajos/{trabajo_id}").json()
        if cuerpo["avance"]:
            visto = cuerpo["avance"]
            break
        time.sleep(0.02)

    cliente.post(f"/api/trabajos/{trabajo_id}/cancelar")
    assert visto is not None
    assert visto["totales"] == 120
    assert visto["intentos"] == 12


def test_un_trabajo_que_no_existe_da_404(cliente):
    assert cliente.get("/api/trabajos/no-existe").status_code == 404
    assert cliente.post("/api/trabajos/no-existe/cancelar").status_code == 404


def test_bajar_un_archivo_de_un_trabajo_que_no_termino_da_409(cliente, tmp_path):
    cuadrados = [(i * 60 % 1500, (i * 60 // 1500) * 60, 50) for i in range(120)]
    fuente_id = fuente_de(cliente, tmp_path, cuadrados)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "lento"},
    }).json()["id"]

    respuesta = cliente.get(f"/api/trabajos/{trabajo_id}/salida.dxf")
    cliente.post(f"/api/trabajos/{trabajo_id}/cancelar")

    assert respuesta.status_code == 409


def test_un_archivo_sin_piezas_termina_en_error_no_en_bug(cliente, tmp_path):
    """Un DXF vacío es un problema del archivo, no del programa. La interfaz
    lo muestra como 'revisá esto', no como 'se rompió el programa'."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    ruta = tmp_path / "vacio.dxf"
    doc.saveas(ruta)
    fuente_id = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()["id"]

    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "rapido"},
    }).json()["id"]

    cuerpo = esperar(cliente, trabajo_id, {"error"})
    assert cuerpo["es_bug"] is False
    assert "pieza" in cuerpo["error"].lower()


def test_el_diagnostico_existe_aunque_el_trabajo_falle(cliente, tmp_path):
    """Es justamente cuando más sirve: el archivo no dio ninguna pieza y el
    usuario necesita ver qué se descartó."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    ruta = tmp_path / "vacio.dxf"
    doc.saveas(ruta)
    fuente_id = cliente.post("/api/archivos/local", json={"ruta": str(ruta)}).json()["id"]
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "rapido"},
    }).json()["id"]
    esperar(cliente, trabajo_id, {"error"})

    assert cliente.get(f"/api/trabajos/{trabajo_id}/diagnostico.png").status_code == 200
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_api_trabajos.py -q`
Expected: FAIL — las rutas de trabajos no existen, da 404 donde espera 200

- [ ] **Step 3: Escribir la implementación mínima**

En `src/nesting_app/api.py`, agregar a los imports:

```python
from nesting.params import NestParams, ParamsInvalidosError, validar
from nesting_app.jobs import Estado, TrabajoDesconocidoError
```

Agregar los modelos, después de `PedidoAnalisis`:

```python
class ParamsEntrada(BaseModel):
    """Los parámetros tal como los manda la interfaz.

    Las reglas de rango NO están acá: viven en `nesting.params.validar`, que
    es el mismo código que usa la CLI. Pydantic sólo verifica que los tipos
    sean los que son.
    """

    material: str
    sep: float = 5.0
    borde: float = 10.0
    copias: int = 1
    angulos: list[float] = Field(default_factory=lambda: [0.0, 90.0, 180.0, 270.0])
    espejo: bool = True
    unidades: str | None = None
    tol_cierre: float = 0.1
    resolucion: float = 2.0
    esfuerzo: str = "normal"

    def a_params(self) -> NestParams:
        return NestParams(
            material=self.material,
            sep=self.sep,
            borde=self.borde,
            copias=self.copias,
            angulos=tuple(self.angulos),
            espejo=self.espejo,
            unidades=self.unidades,
            tol_cierre=self.tol_cierre,
            resolucion=self.resolucion,
            esfuerzo=self.esfuerzo,
        )


class PedidoTrabajo(BaseModel):
    fuente_id: str
    params: ParamsEntrada


ARCHIVOS_DEL_RESULTADO = {
    "salida.dxf": "application/dxf",
    "preview.png": "image/png",
    "diagnostico.png": "image/png",
}
```

Agregar las rutas dentro de `crear_app`, antes de `_montar_interfaz(app)`:

```python
    # --- trabajos -----------------------------------------------------------

    def _avance_a_dict(avance) -> dict | None:
        if avance is None:
            return None
        return {
            "intento": avance.intento,
            "intentos": avance.intentos,
            "ubicadas": avance.ubicadas,
            "totales": avance.totales,
            "placa": avance.placa,
            "compactando": avance.compactando,
        }

    @app.post("/api/trabajos", dependencies=protegido)
    def crear_trabajo(pedido: PedidoTrabajo) -> dict:
        try:
            fuente = deposito.obtener(pedido.fuente_id)
        except FuenteDesconocidaError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        params = pedido.params.a_params()
        try:
            validar(params)
        except ParamsInvalidosError as error:
            # El campo va aparte del mensaje para que la interfaz pueda poner
            # el texto justo debajo del control que lo tiene mal.
            raise HTTPException(
                status_code=422,
                detail={
                    "campo": error.rota.campo,
                    "mensaje": f"tiene que ser {error.rota.regla}",
                    "valor": error.rota.valor,
                },
            ) from error

        try:
            materiales = materials_store.leer()
        except ValueError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        if params.material not in materiales:
            raise HTTPException(
                status_code=404,
                detail=f"no existe ningún material llamado {params.material!r}",
            )

        trabajo = registro.crear(fuente, params, corredor.acomodar)
        return {"id": trabajo.id}

    @app.get("/api/trabajos/{trabajo_id}", dependencies=protegido)
    def ver_trabajo(trabajo_id: str) -> dict:
        try:
            trabajo = registro.obtener(trabajo_id)
        except TrabajoDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        resultado = None
        if trabajo.resultado is not None:
            resultado = {
                "placas": trabajo.resultado.placas,
                "aprovechamiento": trabajo.resultado.aprovechamiento,
                "total": trabajo.resultado.total,
                "segundos": trabajo.resultado.segundos,
                "sobrante_mm": trabajo.resultado.sobrante_mm,
            }
        return {
            "estado": str(trabajo.estado),
            "avance": _avance_a_dict(trabajo.avance),
            "avisos": trabajo.avisos,
            "error": trabajo.error,
            "es_bug": trabajo.es_bug,
            "detalle_tecnico": trabajo.detalle_tecnico,
            "resultado": resultado,
        }

    @app.post("/api/trabajos/{trabajo_id}/cancelar", dependencies=protegido)
    def cancelar_trabajo(trabajo_id: str) -> dict:
        try:
            registro.cancelar(trabajo_id)
        except TrabajoDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"ok": True}

    @app.get("/api/trabajos/{trabajo_id}/{nombre}", dependencies=protegido)
    def bajar_archivo(trabajo_id: str, nombre: str) -> FileResponse:
        if nombre not in ARCHIVOS_DEL_RESULTADO:
            raise HTTPException(status_code=404, detail=f"no existe {nombre!r}")
        try:
            trabajo = registro.obtener(trabajo_id)
        except TrabajoDesconocidoError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        # El diagnóstico se escribe ANTES de acomodar, así que existe aunque
        # el trabajo haya fallado -- y es justo cuando más sirve, porque el
        # usuario necesita ver qué se descartó.
        carpeta = registro.carpeta / trabajo_id
        archivo = carpeta / nombre
        if not archivo.is_file():
            raise HTTPException(
                status_code=409,
                detail=f"el trabajo está en estado {trabajo.estado} y todavía "
                       f"no produjo {nombre}",
            )
        return FileResponse(
            archivo, media_type=ARCHIVOS_DEL_RESULTADO[nombre], filename=nombre
        )
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/app/test_api_trabajos.py -q`
Expected: PASS, 11 tests

- [ ] **Step 5: Correr TODA la suite**

Run: `.venv/bin/python -m pytest -q -p no:warnings`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app/api.py tests/app/test_api_trabajos.py
git commit -m "API: trabajos, avance, cancelar y bajar los archivos

Un parámetro inválido devuelve el campo aparte del mensaje, para que la
interfaz ponga el texto debajo del control que lo tiene mal.

El diagnóstico se puede bajar aunque el trabajo haya fallado: se escribe
antes de acomodar, y es justo cuando más sirve.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: El armazón de la interfaz y sus estilos

**Files:**
- Modify: `src/nesting_app/web/index.html`
- Create: `src/nesting_app/web/app.css`
- Test: `tests/app/test_web_estatico.py`

**Interfaces:**
- Produces: el HTML con todos los ids que `app.js` va a usar. **Los nombres de acá son contrato para la Task 11.**
  - Pantalla principal: `#pantalla-principal`, `#nombre-archivo`, `#btn-archivo`, `#resumen-archivo`, `#link-descartes`, `#material`, `#sep`, `#borde`, `#copias`, `#esfuerzo`, `#avanzadas`, `#btn-acomodar`, `#btn-cancelar`, `#btn-guardar`, `#barra-avance`, `#texto-avance`, `#resultado`, `#tab-preview`, `#tab-revision`, `#lienzo`, `#placa-actual`
  - Materiales: `#pantalla-materiales`, `#tabla-materiales`, `#form-material`, `#m-nombre`, `#m-ancho`, `#m-alto`, `#m-veta-libre`, `#m-veta-respetar`, `#btn-guardar-material`, `#btn-cancelar-material`, `#btn-restaurar`, `#btn-volver`
  - Carteles: `#cartel-unidades`, `#cartel-error`, `#texto-error`, `#detalle-error`
  - Clases de estado: `.oculto`, `.error`, `.campo-con-error`

**Por qué esta tarea va antes que el JavaScript:** el HTML define los nombres. Escribir el JS primero obliga a inventarlos dos veces.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/test_web_estatico.py`:

```python
"""Que la interfaz estática tenga lo que el JavaScript espera encontrar.

No es un test de aspecto: es un test de contrato. `app.js` busca elementos
por id, y un id que cambió de nombre no falla en ningún lado hasta que
alguien abre la pantalla y un botón no hace nada.
"""

import re

import pytest

from nesting_app import rutas

IDS_OBLIGATORIOS = [
    "pantalla-principal", "nombre-archivo", "btn-archivo", "resumen-archivo",
    "link-descartes", "material", "sep", "borde", "copias", "esfuerzo",
    "avanzadas", "btn-acomodar", "btn-cancelar", "btn-guardar",
    "barra-avance", "texto-avance", "resultado",
    "tab-preview", "tab-revision", "lienzo", "placa-actual",
    "pantalla-materiales", "tabla-materiales", "form-material",
    "m-nombre", "m-ancho", "m-alto", "m-veta-libre", "m-veta-respetar",
    "btn-guardar-material", "btn-cancelar-material", "btn-restaurar", "btn-volver",
    "cartel-unidades", "cartel-error", "texto-error", "detalle-error",
    # Los usa `app.js` y `materiales.js`. Si falta uno, el botón no hace nada
    # y no falla en ningún lado hasta que alguien lo aprieta.
    "btn-materiales", "cuenta-piezas", "pista-avance", "titulo-error",
    "btn-copiar-error", "btn-cerrar-error", "titulo-form", "error-material",
    "angulos", "tol-cierre", "resolucion", "espejo",
]


@pytest.fixture(scope="module")
def html():
    return (rutas.recurso("web") / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css():
    return (rutas.recurso("web") / "app.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("elemento_id", IDS_OBLIGATORIOS)
def test_esta_el_id_que_el_javascript_busca(html, elemento_id):
    assert f'id="{elemento_id}"' in html


def test_ningun_id_esta_repetido(html):
    ids = re.findall(r'id="([^"]+)"', html)
    repetidos = {i for i in ids if ids.count(i) > 1}
    assert not repetidos, f"ids repetidos: {repetidos}"


def test_el_html_declara_espanol(html):
    """Los correctores y los lectores de pantalla lo necesitan."""
    assert 'lang="es"' in html


def test_todo_campo_tiene_su_etiqueta(html):
    """Un input sin label es invisible para un lector de pantalla y su texto
    no se puede clickear para enfocarlo."""
    for campo in ("sep", "borde", "copias", "material", "esfuerzo",
                  "m-nombre", "m-ancho", "m-alto"):
        assert f'for="{campo}"' in html, f"falta el label de {campo}"


def test_los_botones_son_botones_de_verdad(html):
    """Un div con onclick no recibe foco con Tab ni se activa con Enter."""
    for boton in ("btn-acomodar", "btn-cancelar", "btn-guardar", "btn-volver"):
        assert re.search(rf'<button[^>]*id="{boton}"', html), boton


def test_los_tokens_de_color_estan_exactos(css):
    """Son los de la dirección D, elegida sobre cuatro maquetadas. Que estén
    acá y en un solo lugar es lo que permite cambiarlos sin cazar hexas."""
    for token, valor in [
        ("--fondo", "#F4F6F8"),
        ("--panel", "#FFFFFF"),
        ("--lienzo", "#EDF0F4"),
        ("--texto", "#111827"),
        ("--texto-2", "#606B7B"),
        ("--borde", "#E2E6EC"),
        ("--acento", "#047857"),
    ]:
        assert f"{token}: {valor}" in css, token


def test_las_medidas_usan_cifras_tabulares(css):
    """La interfaz es una grilla de medidas que se comparan entre sí, y en
    cifras proporcionales 1830 y 1220 no alinean."""
    assert "font-variant-numeric: tabular-nums" in css


def test_los_controles_miden_44_px(css):
    assert "--alto-control: 44px" in css


def test_no_hay_emojis_en_la_interfaz(html):
    """Los íconos son SVG con trazo. Un emoji se ve distinto en cada sistema
    y en una herramienta de taller queda fuera de lugar."""
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", html)


def test_el_css_se_carga_desde_el_html(html):
    assert 'href="app.css"' in html


def test_el_javascript_se_carga_desde_el_html(html):
    assert 'src="app.js"' in html
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_web_estatico.py -q`
Expected: FAIL — faltan casi todos los ids y no existe `app.css`

- [ ] **Step 3: Escribir el HTML**

Reemplazar `src/nesting_app/web/index.html` completo:

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Nesting</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="app.css">
</head>
<body>

<header class="barra-superior">
  <span class="marca">Nesting</span>
  <span class="espaciador"></span>
  <button type="button" id="btn-materiales" class="boton secundario">Materiales</button>
</header>

<main id="pantalla-principal">
  <section class="panel-opciones">
    <div class="campo">
      <span class="etiqueta">Archivo</span>
      <div class="caja-archivo">
        <svg viewBox="0 0 16 16" class="icono" aria-hidden="true"><path d="M9 1.5H4.5A1.5 1.5 0 0 0 3 3v10a1.5 1.5 0 0 0 1.5 1.5h7A1.5 1.5 0 0 0 13 13V5.5z"></path><path d="M9 1.5V5.5H13"></path></svg>
        <span id="nombre-archivo" class="nombre-archivo">Ningún archivo elegido</span>
        <button type="button" id="btn-archivo" class="enlace">Elegir</button>
      </div>
      <p id="resumen-archivo" class="resumen oculto">
        <span id="cuenta-piezas" class="medida">0</span> piezas
        <button type="button" id="link-descartes" class="enlace oculto"></button>
      </p>
    </div>

    <div class="campo">
      <label class="etiqueta" for="material">Material</label>
      <select id="material" class="control"></select>
    </div>

    <div class="campo">
      <label class="etiqueta" for="sep">Separación</label>
      <div class="control con-unidad">
        <input id="sep" type="number" min="0" step="0.5" value="5" class="medida">
        <span class="unidad">mm</span>
      </div>
      <p class="error-campo oculto" data-error-de="sep"></p>
    </div>

    <div class="campo">
      <label class="etiqueta" for="borde">Borde</label>
      <div class="control con-unidad">
        <input id="borde" type="number" min="0" step="1" value="10" class="medida">
        <span class="unidad">mm</span>
      </div>
      <p class="error-campo oculto" data-error-de="borde"></p>
    </div>

    <div class="campo">
      <label class="etiqueta" for="copias">Copias</label>
      <div class="control">
        <input id="copias" type="number" min="1" step="1" value="1" class="medida">
      </div>
      <p class="error-campo oculto" data-error-de="copias"></p>
    </div>

    <div class="campo">
      <label class="etiqueta" for="esfuerzo">Esfuerzo</label>
      <select id="esfuerzo" class="control">
        <option value="rapido">Rápido — una pasada</option>
        <option value="normal" selected>Normal — tres pasadas</option>
        <option value="lento">Lento — doce pasadas</option>
      </select>
    </div>

    <span class="espaciador"></span>

    <details id="avanzadas" class="avanzadas">
      <summary>Opciones avanzadas</summary>
      <div class="campo">
        <label class="etiqueta" for="angulos">Ángulos</label>
        <div class="control"><input id="angulos" type="text" value="0,90,180,270"></div>
      </div>
      <div class="campo">
        <label class="etiqueta" for="tol-cierre">Tolerancia de cierre</label>
        <div class="control con-unidad">
          <input id="tol-cierre" type="number" min="0.001" step="0.01" value="0.1" class="medida">
          <span class="unidad">mm</span>
        </div>
        <p class="error-campo oculto" data-error-de="tol_cierre"></p>
      </div>
      <div class="campo">
        <label class="etiqueta" for="resolucion">Resolución</label>
        <div class="control con-unidad">
          <input id="resolucion" type="number" min="0.1" step="0.5" value="2" class="medida">
          <span class="unidad">mm/px</span>
        </div>
        <p class="error-campo oculto" data-error-de="resolucion"></p>
      </div>
      <label class="casilla"><input id="espejo" type="checkbox" checked> Permitir piezas espejadas</label>
    </details>
  </section>

  <section class="panel-dibujo">
    <div class="solapas">
      <button type="button" id="tab-preview" class="solapa activa">Previsualización</button>
      <button type="button" id="tab-revision" class="solapa">Revisión</button>
      <span class="espaciador"></span>
      <span id="placa-actual" class="medida placa-actual"></span>
    </div>
    <div id="lienzo" class="lienzo"></div>
  </section>
</main>

<footer class="barra-accion">
  <button type="button" id="btn-acomodar" class="boton primario">Acomodar</button>
  <button type="button" id="btn-cancelar" class="boton secundario oculto">Cancelar</button>
  <div class="estado">
    <div class="pista-avance oculto" id="pista-avance">
      <div id="barra-avance" class="barra-avance"></div>
    </div>
    <p id="texto-avance" class="texto-avance oculto"></p>
    <p id="resultado" class="resultado oculto"></p>
  </div>
  <button type="button" id="btn-guardar" class="boton secundario" disabled>Guardar DXF…</button>
</footer>

<section id="pantalla-materiales" class="pantalla-materiales oculto">
  <div class="cabecera-materiales">
    <button type="button" id="btn-volver" class="enlace">Volver</button>
    <h1>Materiales</h1>
  </div>
  <div class="cuerpo-materiales">
    <div class="lado-tabla">
      <table class="tabla">
        <thead>
          <tr><th>Nombre</th><th class="der">Ancho</th><th class="der">Alto</th><th>Veta</th><th></th></tr>
        </thead>
        <tbody id="tabla-materiales"></tbody>
      </table>
      <p class="resumen">
        Se guardan en tu carpeta de usuario, no adentro del programa.
        <button type="button" id="btn-restaurar" class="enlace">Restaurar el catálogo original</button>
      </p>
    </div>
    <form id="form-material" class="form-material">
      <h2 id="titulo-form">Nuevo material</h2>
      <div class="campo">
        <label class="etiqueta" for="m-nombre">Nombre</label>
        <div class="control"><input id="m-nombre" type="text" required></div>
      </div>
      <div class="fila">
        <div class="campo">
          <label class="etiqueta" for="m-ancho">Ancho</label>
          <div class="control con-unidad">
            <input id="m-ancho" type="number" min="1" step="1" required class="medida">
            <span class="unidad">mm</span>
          </div>
        </div>
        <div class="campo">
          <label class="etiqueta" for="m-alto">Alto</label>
          <div class="control con-unidad">
            <input id="m-alto" type="number" min="1" step="1" required class="medida">
            <span class="unidad">mm</span>
          </div>
        </div>
      </div>
      <fieldset class="campo">
        <legend class="etiqueta">Veta</legend>
        <label class="opcion">
          <input type="radio" name="veta" id="m-veta-libre" value="libre" checked>
          <span><strong>La veta no importa</strong><small>La pieza gira libre. Típico del MDF.</small></span>
        </label>
        <label class="opcion">
          <input type="radio" name="veta" id="m-veta-respetar" value="respetar">
          <span><strong>Respetar la veta</strong><small>Sólo 0 y 180 grados. Multilaminado, fenólico.</small></span>
        </label>
      </fieldset>
      <p id="error-material" class="error-campo oculto"></p>
      <div class="fila">
        <button type="submit" id="btn-guardar-material" class="boton primario crece">Guardar</button>
        <button type="button" id="btn-cancelar-material" class="boton secundario">Cancelar</button>
      </div>
    </form>
  </div>
</section>

<div id="cartel-unidades" class="cartel oculto">
  <div class="cartel-caja">
    <h2>¿En qué unidades está este archivo?</h2>
    <p>El archivo no lo declara, y adivinar arruinaría la placa entera.</p>
    <div class="fila">
      <button type="button" class="boton secundario" data-unidad="mm">mm</button>
      <button type="button" class="boton secundario" data-unidad="cm">cm</button>
      <button type="button" class="boton secundario" data-unidad="m">m</button>
      <button type="button" class="boton secundario" data-unidad="in">in</button>
      <button type="button" class="boton secundario" data-unidad="ft">ft</button>
    </div>
  </div>
</div>

<div id="cartel-error" class="cartel oculto">
  <div class="cartel-caja">
    <h2 id="titulo-error">No se pudo</h2>
    <p id="texto-error"></p>
    <pre id="detalle-error" class="detalle oculto"></pre>
    <div class="fila">
      <span class="espaciador"></span>
      <button type="button" id="btn-copiar-error" class="boton secundario oculto">Copiar detalle</button>
      <button type="button" id="btn-cerrar-error" class="boton primario">Entendido</button>
    </div>
  </div>
</div>

<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Escribir el CSS**

Crear `src/nesting_app/web/app.css`:

```css
/* Dirección D · Moderno. Los tokens viven acá y en ningún otro lado:
   cambiar el acento tiene que ser cambiar una línea, no cazar hexas. */
:root {
  --fondo: #F4F6F8;
  --panel: #FFFFFF;
  --lienzo: #EDF0F4;
  --texto: #111827;
  --texto-2: #606B7B;
  --borde: #E2E6EC;
  --acento: #047857;
  --sobre-acento: #FFFFFF;
  --rojo: #B42318;
  --radio: 10px;
  --radio-boton: 8px;
  --alto-control: 44px;
  --sombra: 0 1px 2px rgba(17,24,39,.06), 0 4px 12px rgba(17,24,39,.05);
  --fuente: "Plus Jakarta Sans", system-ui, sans-serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  grid-template-rows: auto 1fr auto;
  font-family: var(--fuente);
  color: var(--texto);
  background: var(--fondo);
  font-size: 14px;
}

.oculto { display: none !important; }
.espaciador { flex-grow: 1; }

/* La interfaz es una grilla de medidas que se comparan entre sí. En cifras
   proporcionales 1830 y 1220 no alinean y la columna se lee torcida. */
.medida, .tabla td, .placa-actual { font-variant-numeric: tabular-nums; }

/* --- barras --- */
.barra-superior, .barra-accion {
  display: flex; align-items: center; gap: 14px;
  padding: 0 16px; background: var(--panel);
}
.barra-superior { height: 56px; border-bottom: 1px solid var(--borde); }
.barra-accion { min-height: 76px; border-top: 1px solid var(--borde); }
.marca { font-weight: 700; font-size: 15px; }

/* --- pantalla principal --- */
#pantalla-principal { display: flex; min-height: 0; }

.panel-opciones {
  width: 336px; flex-shrink: 0; padding: 20px 18px;
  display: flex; flex-direction: column; gap: 16px;
  background: var(--panel); border-right: 1px solid var(--borde);
  overflow-y: auto;
}

.panel-dibujo { flex-grow: 1; min-width: 0; display: flex; flex-direction: column; }
.solapas {
  display: flex; align-items: flex-end; gap: 22px;
  padding: 16px 20px 0; border-bottom: 1px solid var(--borde);
}
.solapa {
  padding: 0 2px 10px; border: 0; border-bottom: 2px solid transparent;
  background: none; font: inherit; font-weight: 500; color: var(--texto-2);
  cursor: pointer;
}
.solapa.activa { color: var(--texto); font-weight: 600; border-bottom-color: var(--acento); }
.placa-actual { padding-bottom: 10px; font-size: 12px; color: var(--texto-2); }
.lienzo {
  flex-grow: 1; min-height: 0; display: flex; align-items: center;
  justify-content: center; padding: 16px; background: var(--lienzo);
}
.lienzo img, .lienzo svg { max-width: 100%; max-height: 100%; object-fit: contain; }

/* --- controles --- */
.campo { display: flex; flex-direction: column; gap: 6px; border: 0; margin: 0; padding: 0; }
.etiqueta { font-size: 13px; font-weight: 600; color: var(--texto-2); padding: 0; }

.control, select.control, .caja-archivo {
  display: flex; align-items: center; height: var(--alto-control);
  padding: 0 12px; background: var(--panel);
  border: 1px solid var(--borde); border-radius: var(--radio);
}
.control input, select.control {
  flex-grow: 1; min-width: 0; border: 0; outline: none; background: none;
  font: inherit; color: var(--texto);
}
select.control { padding: 0 12px; appearance: none; cursor: pointer; }
.control:focus-within { border-color: var(--acento); box-shadow: 0 0 0 3px rgba(4,120,87,.12); }
.unidad { padding-left: 8px; font-size: 12px; color: var(--texto-2); }
.campo-con-error .control { border-color: var(--rojo); }
.error-campo { margin: 0; font-size: 12px; color: var(--rojo); }

.caja-archivo { gap: 8px; }
.nombre-archivo { flex-grow: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.icono { width: 16px; height: 16px; fill: none; stroke: var(--texto-2); stroke-width: 1.5; }
.resumen { margin: 0; font-size: 12px; color: var(--texto-2); }

.enlace {
  border: 0; background: none; padding: 0; font: inherit; font-size: 12px;
  font-weight: 600; color: var(--acento); cursor: pointer; text-decoration: underline;
}

.boton {
  height: var(--alto-control); padding: 0 18px; border-radius: var(--radio-boton);
  font: inherit; font-weight: 600; cursor: pointer; border: 1px solid transparent;
}
.boton.primario { background: var(--acento); color: var(--sobre-acento); border-color: var(--acento); }
.boton.secundario { background: var(--panel); color: var(--texto); border-color: var(--borde); }
.boton:disabled { opacity: .5; cursor: not-allowed; }
.boton.crece { flex-grow: 1; }

.avanzadas { border-top: 1px solid var(--borde); padding-top: 12px; }
.avanzadas summary {
  cursor: pointer; font-size: 13px; font-weight: 600; color: var(--texto-2);
  list-style: none;
}
.avanzadas summary::-webkit-details-marker { display: none; }
.avanzadas summary::before { content: "› "; }
.avanzadas[open] summary::before { content: "⌄ "; }
.avanzadas > .campo { margin-top: 14px; }
.casilla { display: flex; gap: 8px; align-items: center; margin-top: 14px; font-size: 13px; }

/* --- avance y resultado --- */
.estado { flex-grow: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.pista-avance { height: 6px; background: var(--borde); border-radius: 3px; overflow: hidden; }
.barra-avance { height: 100%; width: 0; background: var(--acento); transition: width .2s ease; }
.texto-avance, .resultado { margin: 0; font-size: 13px; }
.texto-avance { color: var(--texto-2); }
.resultado strong { font-variant-numeric: tabular-nums; }

/* --- materiales --- */
.pantalla-materiales {
  position: fixed; inset: 56px 0 0 0; background: var(--fondo);
  display: flex; flex-direction: column; padding: 20px 24px; overflow-y: auto;
}
.cabecera-materiales { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.cabecera-materiales h1 { margin: 0; font-size: 20px; }
.cuerpo-materiales { display: flex; gap: 22px; align-items: flex-start; }
.lado-tabla { flex-grow: 1; min-width: 0; }
.tabla { width: 100%; border-collapse: collapse; }
.tabla th {
  text-align: left; padding: 0 10px 10px; font-size: 13px;
  font-weight: 600; color: var(--texto-2);
}
.tabla th.der, .tabla td.der { text-align: right; }
.tabla td { padding: 12px 10px; border-top: 1px solid var(--borde); }
.insignia {
  display: inline-block; padding: 2px 9px; font-size: 11px;
  border: 1px solid var(--borde); border-radius: var(--radio-boton); color: var(--texto-2);
}
.insignia.respetar { border-color: var(--acento); color: var(--acento); font-weight: 600; }
.icono-boton {
  width: 32px; height: 32px; border: 0; background: none; cursor: pointer;
  color: var(--texto-2); border-radius: var(--radio-boton);
}
.icono-boton:hover { background: var(--lienzo); }

.form-material {
  width: 320px; flex-shrink: 0; padding: 18px; background: var(--panel);
  border: 1px solid var(--borde); border-radius: var(--radio);
  box-shadow: var(--sombra); display: flex; flex-direction: column; gap: 14px;
}
.form-material h2 { margin: 0; font-size: 15px; }
.fila { display: flex; gap: 10px; }
.fila > .campo { flex-grow: 1; }
.opcion {
  display: flex; gap: 10px; padding: 10px 12px; cursor: pointer;
  border: 1px solid var(--borde); border-radius: var(--radio);
}
.opcion:has(input:checked) { border-color: var(--acento); }
.opcion span { display: flex; flex-direction: column; gap: 2px; }
.opcion small { color: var(--texto-2); font-size: 11px; }

/* --- carteles --- */
.cartel {
  position: fixed; inset: 0; background: rgba(17,24,39,.45);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.cartel-caja {
  width: min(520px, 100%); padding: 22px; background: var(--panel);
  border-radius: var(--radio); box-shadow: var(--sombra);
  display: flex; flex-direction: column; gap: 14px;
}
.cartel-caja h2 { margin: 0; font-size: 17px; }
.cartel-caja p { margin: 0; color: var(--texto-2); }
.cartel.error .cartel-caja h2 { color: var(--rojo); }
.detalle {
  margin: 0; max-height: 180px; overflow: auto; padding: 12px;
  background: var(--lienzo); border-radius: var(--radio);
  font-size: 11px; white-space: pre-wrap;
}
```

- [ ] **Step 5: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/app/test_web_estatico.py -q`
Expected: PASS, 47 tests

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app/web tests/app/test_web_estatico.py
git commit -m "Interfaz: armazón HTML y los estilos de la dirección D

El HTML define los nombres que el JavaScript va a buscar, así que va
primero: al revés habría que inventarlos dos veces.

El test no verifica aspecto sino contrato. Un id que cambia de nombre no
falla en ningún lado hasta que alguien abre la pantalla y un botón no
hace nada.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: El flujo principal en JavaScript

**Files:**
- Create: `src/nesting_app/web/app.js`
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: los ids de la Task 10 y las rutas de las Tasks 8 y 9
- Produces: `window.__nesting` con `{ api, estado, refrescarMateriales, mostrarMateriales }` para que la Task 12 se enganche y para poder probar piezas sueltas

**El token:** `desktop.py` va a servir un `index.html` con `<meta name="token" content="...">` inyectado. El JavaScript lo lee de ahí y lo manda en `X-Token`. En la web ese meta lo pondrá el servidor con la sesión del usuario: el JavaScript no cambia.

**El sondeo:** cada 400 ms mientras hay un trabajo corriendo. Con trabajos de 34 s a 9 minutos, más frecuente no aporta y menos se siente lento.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/test_web_javascript.py`:

```python
"""Contrato del JavaScript: que llame a las rutas que la API expone.

No corre un navegador -- eso quedó fuera de alcance a propósito. Verifica
que el archivo hable de las mismas rutas y campos que el servidor produce,
que es la clase de desincronización que rompe la pantalla en silencio.
"""

import re

import pytest

from nesting_app import rutas


@pytest.fixture(scope="module")
def js():
    return (rutas.recurso("web") / "app.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("ruta", [
    "/api/materiales", "/api/archivos", "/api/archivos/local",
    "/api/analizar", "/api/trabajos",
])
def test_usa_la_ruta_que_la_api_expone(js, ruta):
    assert ruta in js


def test_manda_el_token_en_cada_pedido(js):
    assert "X-Token" in js


def test_lee_el_token_del_meta(js):
    """`desktop.py` lo inyecta ahí al servir la página. En la web lo va a
    poner el servidor con la sesión: este código no cambia."""
    assert 'name="token"' in js or "'token'" in js


@pytest.mark.parametrize("estado", ["listo", "cancelado", "error", "corriendo"])
def test_contempla_cada_estado_de_un_trabajo(js, estado):
    assert f'"{estado}"' in js or f"'{estado}'" in js


def test_distingue_un_bug_del_programa_de_un_error_del_dibujo(js):
    """Son dos mensajes distintos: uno manda a corregir el archivo, el otro
    dice que el problema es nuestro."""
    assert "es_bug" in js


def test_reacciona_a_que_falten_las_unidades(js):
    assert "faltan_unidades" in js


def test_pone_el_error_de_un_parametro_debajo_de_su_campo(js):
    assert "data-error-de" in js


def test_sondea_con_un_intervalo_razonable(js):
    """Los trabajos tardan de 34 s a 9 minutos. Sondear cada 50 ms sería
    quemar CPU al pedo; cada 5 s se sentiría trabado."""
    intervalos = [int(n) for n in re.findall(r"SONDEO_MS\s*=\s*(\d+)", js)]
    assert intervalos, "no se encontró SONDEO_MS"
    assert 200 <= intervalos[0] <= 1000


def test_el_avance_se_arma_con_intento_y_piezas(js):
    """Una barra hecha sólo con ubicadas/totales retrocedería en cada
    intento nuevo, y una barra que retrocede es peor que no tener barra."""
    assert "intento" in js and "ubicadas" in js


def test_expone_su_estado_para_la_pantalla_de_materiales(js):
    assert "window.__nesting" in js
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_web_javascript.py -q`
Expected: FAIL con `FileNotFoundError` — no existe `app.js`

- [ ] **Step 3: Escribir el JavaScript**

Crear `src/nesting_app/web/app.js`:

```javascript
"use strict";

/* El cliente de la API y el flujo de la pantalla principal.
 *
 * Nada acá sabe si está corriendo en una ventana de escritorio o en un
 * navegador contra un servidor remoto. Esa diferencia vive en el servidor
 * (nesting_app/archivos.py) y en cómo llega el token. */

const SONDEO_MS = 400;

const TOKEN = document.querySelector('meta[name="token"]')?.content || "";
const EN_ESCRITORIO = document.querySelector('meta[name="escritorio"]')?.content === "1";

const $ = (id) => document.getElementById(id);

const estado = {
  fuenteId: null,
  nombreArchivo: null,
  unidades: null,
  trabajoId: null,
  sondeo: null,
  terminado: false,
  descartes: 0,
};

// --- el cliente HTTP --------------------------------------------------------

async function api(ruta, opciones = {}) {
  const respuesta = await fetch(ruta, {
    ...opciones,
    headers: { "X-Token": TOKEN, ...(opciones.headers || {}) },
  });
  if (!respuesta.ok) {
    let detalle = respuesta.statusText;
    try {
      detalle = (await respuesta.json()).detail;
    } catch (_) { /* el cuerpo no era JSON; queda el statusText */ }
    const error = new Error(typeof detalle === "string" ? detalle : "");
    error.estado = respuesta.status;
    error.detalle = detalle;
    throw error;
  }
  return respuesta;
}

const apiJson = async (ruta, opciones) => (await api(ruta, opciones)).json();

const postJson = (ruta, cuerpo) =>
  apiJson(ruta, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });

// --- carteles ---------------------------------------------------------------

function mostrarError(titulo, texto, detalleTecnico) {
  $("titulo-error").textContent = titulo;
  $("texto-error").textContent = texto;
  const detalle = $("detalle-error");
  detalle.textContent = detalleTecnico || "";
  detalle.classList.toggle("oculto", !detalleTecnico);
  $("btn-copiar-error").classList.toggle("oculto", !detalleTecnico);
  $("cartel-error").classList.remove("oculto");
  $("cartel-error").classList.add("error");
}

$("btn-cerrar-error").onclick = () => $("cartel-error").classList.add("oculto");
$("btn-copiar-error").onclick = () =>
  navigator.clipboard?.writeText($("detalle-error").textContent);

function limpiarErroresDeCampo() {
  document.querySelectorAll("[data-error-de]").forEach((p) => {
    p.classList.add("oculto");
    p.closest(".campo")?.classList.remove("campo-con-error");
  });
}

function marcarCampo(campo, mensaje) {
  const p = document.querySelector(`[data-error-de="${campo}"]`);
  if (!p) return mostrarError("Un parámetro no sirve", `${campo}: ${mensaje}`);
  p.textContent = mensaje;
  p.classList.remove("oculto");
  p.closest(".campo")?.classList.add("campo-con-error");
}

// --- elegir el archivo ------------------------------------------------------

$("btn-archivo").onclick = async () => {
  try {
    if (EN_ESCRITORIO) {
      // El diálogo nativo lo abre pywebview y devuelve una ruta de verdad.
      const rutas = await window.pywebview.api.elegir_archivo();
      if (!rutas || !rutas.length) return;
      await registrar(await postJson("/api/archivos/local", { ruta: rutas[0] }));
    } else {
      const entrada = document.createElement("input");
      entrada.type = "file";
      entrada.accept = ".dxf,.ai,.3dm";
      entrada.onchange = async () => {
        const datos = new FormData();
        datos.append("archivo", entrada.files[0]);
        await registrar(await apiJson("/api/archivos", { method: "POST", body: datos }));
      };
      entrada.click();
    }
  } catch (error) {
    mostrarError("No se pudo abrir el archivo", error.message);
  }
};

async function registrar(fuente) {
  estado.fuenteId = fuente.id;
  estado.nombreArchivo = fuente.nombre;
  estado.unidades = null;
  $("nombre-archivo").textContent = fuente.nombre;
  await analizar();
}

// --- analizar ---------------------------------------------------------------

async function analizar() {
  try {
    const analisis = await postJson("/api/analizar", {
      fuente_id: estado.fuenteId,
      unidades: estado.unidades,
      tol_cierre: Number($("tol-cierre").value),
    });
    estado.descartes = analisis.descartes.length;
    $("cuenta-piezas").textContent = analisis.piezas;
    $("resumen-archivo").classList.remove("oculto");
    const link = $("link-descartes");
    link.textContent = `· ${analisis.descartes.length} descartes`;
    link.classList.toggle("oculto", analisis.descartes.length === 0);
    mostrarRevision();
  } catch (error) {
    if (error.estado === 409 && error.detalle?.faltan_unidades) {
      // No es un error: es una pregunta. Por eso tiene cartel propio.
      $("cartel-unidades").classList.remove("oculto");
      return;
    }
    mostrarError("No se pudo leer el archivo", error.message);
  }
}

document.querySelectorAll("[data-unidad]").forEach((boton) => {
  boton.onclick = async () => {
    estado.unidades = boton.dataset.unidad;
    $("cartel-unidades").classList.add("oculto");
    await analizar();
  };
});

// --- solapas ----------------------------------------------------------------

function mostrarImagen(nombre) {
  if (!estado.trabajoId) return;
  $("lienzo").innerHTML = "";
  const img = new Image();
  img.src = `/api/trabajos/${estado.trabajoId}/${nombre}?t=${Date.now()}`;
  img.alt = nombre === "preview.png" ? "Cómo quedó el acomodo" : "Qué se descartó";
  $("lienzo").append(img);
}

const mostrarRevision = () => {
  $("tab-revision").classList.add("activa");
  $("tab-preview").classList.remove("activa");
  mostrarImagen("diagnostico.png");
};

$("tab-preview").onclick = () => {
  $("tab-preview").classList.add("activa");
  $("tab-revision").classList.remove("activa");
  mostrarImagen("preview.png");
};
$("tab-revision").onclick = mostrarRevision;
$("link-descartes").onclick = mostrarRevision;

// --- acomodar ---------------------------------------------------------------

function parametros() {
  return {
    material: $("material").value,
    sep: Number($("sep").value),
    borde: Number($("borde").value),
    copias: Number($("copias").value),
    angulos: $("angulos").value.split(",").map(Number),
    espejo: $("espejo").checked,
    unidades: estado.unidades,
    tol_cierre: Number($("tol-cierre").value),
    resolucion: Number($("resolucion").value),
    esfuerzo: $("esfuerzo").value,
  };
}

function corriendo(si) {
  $("btn-acomodar").classList.toggle("oculto", si);
  $("btn-cancelar").classList.toggle("oculto", !si);
  $("pista-avance").classList.toggle("oculto", !si);
  $("texto-avance").classList.toggle("oculto", !si);
  $("resultado").classList.toggle("oculto", si);
  $("btn-guardar").disabled = si || !estado.terminado;
}

$("btn-acomodar").onclick = async () => {
  if (!estado.fuenteId) {
    return mostrarError("Falta el archivo", "Elegí un archivo antes de acomodar.");
  }
  limpiarErroresDeCampo();
  estado.terminado = false;
  try {
    const creado = await postJson("/api/trabajos", {
      fuente_id: estado.fuenteId,
      params: parametros(),
    });
    estado.trabajoId = creado.id;
    corriendo(true);
    estado.sondeo = setInterval(sondear, SONDEO_MS);
  } catch (error) {
    if (error.estado === 422 && error.detalle?.campo) {
      return marcarCampo(error.detalle.campo, error.detalle.mensaje);
    }
    mostrarError("No se pudo arrancar", error.message);
  }
};

$("btn-cancelar").onclick = () =>
  api(`/api/trabajos/${estado.trabajoId}/cancelar`, { method: "POST" });

async function sondear() {
  let t;
  try {
    t = await apiJson(`/api/trabajos/${estado.trabajoId}`);
  } catch (error) {
    clearInterval(estado.sondeo);
    corriendo(false);
    return mostrarError("Se perdió el trabajo", error.message);
  }

  if (t.avance) $("texto-avance").textContent = textoDeAvance(t.avance);
  if (t.avance && !t.avance.compactando) {
    const porcentaje = t.avance.totales
      ? (100 * t.avance.ubicadas) / t.avance.totales
      : 0;
    $("barra-avance").style.width = `${porcentaje}%`;
  }

  if (t.estado === "corriendo" || t.estado === "pendiente") return;

  clearInterval(estado.sondeo);
  corriendo(false);

  if (t.estado === "listo") return terminar(t);
  if (t.estado === "cancelado") {
    $("resultado").textContent = "Cancelado. No se escribió ningún archivo.";
    $("resultado").classList.remove("oculto");
    return;
  }
  if (t.estado === "error") {
    mostrarRevision();
    if (t.es_bug) {
      return mostrarError(
        "Se rompió el programa",
        "Esto no es un problema de tu dibujo: es un error nuestro. " +
          "Copiá el detalle y pasalo.",
        t.detalle_tecnico
      );
    }
    mostrarError("No se pudo acomodar", t.error);
  }
}

function textoDeAvance(a) {
  if (a.compactando) return "Compactando la última placa…";
  const intento = a.intentos > 1 ? `Intento ${a.intento} de ${a.intentos} · ` : "";
  return `${intento}ubicadas ${a.ubicadas} de ${a.totales} · placa ${a.placa}`;
}

function terminar(t) {
  estado.terminado = true;
  $("btn-guardar").disabled = false;
  // El DXF vive en una carpeta temporal hasta que el usuario lo guarda.
  window.pywebview?.api?.marcar_sin_guardar(true);
  const r = t.resultado;
  const placas = r.placas === 1 ? "1 placa" : `${r.placas} placas`;
  $("resultado").innerHTML =
    `<strong>${placas}</strong> · <strong>${(100 * r.total).toFixed(1)}%</strong> ` +
    `aprovechado · sobrante <strong>${r.sobrante_mm.toFixed(0)} mm</strong>`;
  $("resultado").classList.remove("oculto");
  $("placa-actual").textContent = `${r.placas} placa${r.placas === 1 ? "" : "s"}`;
  $("tab-preview").click();
  if (t.avisos.length) console.info("avisos:", t.avisos);
}

// --- guardar ----------------------------------------------------------------

$("btn-guardar").onclick = async () => {
  const url = `/api/trabajos/${estado.trabajoId}/salida.dxf`;
  const sugerido = (estado.nombreArchivo || "salida").replace(/\.[^.]+$/, "") + "_acomodado.dxf";
  if (EN_ESCRITORIO) {
    // Diálogo nativo: el usuario elige la carpeta de su proyecto, que es
    // donde este archivo tiene que ir.
    const destino = await window.pywebview.api.elegir_destino(sugerido);
    if (!destino) return;
    const datos = new Uint8Array(await (await api(url)).arrayBuffer());
    await window.pywebview.api.guardar(destino, Array.from(datos));
    $("resultado").insertAdjacentHTML("beforeend", ` · guardado`);
    return;
  }
  const a = document.createElement("a");
  a.href = url;
  a.download = sugerido;
  a.click();
};

// --- arranque ---------------------------------------------------------------

async function refrescarMateriales() {
  const datos = await apiJson("/api/materiales");
  const select = $("material");
  const elegido = select.value;
  select.innerHTML = "";
  for (const m of datos.materiales) {
    const opcion = document.createElement("option");
    opcion.value = m.nombre;
    opcion.textContent = `${m.nombre} — ${m.ancho} × ${m.alto}`;
    select.append(opcion);
  }
  if (elegido) select.value = elegido;
  return datos.materiales;
}

window.__nesting = { api, apiJson, postJson, estado, refrescarMateriales, mostrarError, $ };

refrescarMateriales().catch((error) =>
  mostrarError("No se pudo leer el catálogo de materiales", error.message)
);
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/app/test_web_javascript.py -q`
Expected: PASS, 15 tests

- [ ] **Step 5: Commit**

```bash
git add src/nesting_app/web/app.js tests/app/test_web_javascript.py
git commit -m "Interfaz: el flujo principal en JavaScript

Nada acá sabe si corre en una ventana o en un navegador remoto. Esa
diferencia vive en el servidor y en cómo llega el token.

El avance se arma con intento y piezas: una barra hecha sólo con
ubicadas/totales retrocedería al empezar cada intento nuevo.

Un bug del programa y un problema del dibujo se muestran distinto. El
primero ofrece copiar el detalle; el segundo manda a corregir el archivo.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 12: La pantalla de materiales

**Files:**
- Create: `src/nesting_app/web/materiales.js`
- Modify: `src/nesting_app/web/index.html` (sumar el `<script src="materiales.js">`)
- Test: agregar a `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: `window.__nesting` de la Task 11

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `tests/app/test_web_javascript.py`:

```python
@pytest.fixture(scope="module")
def js_materiales():
    return (rutas.recurso("web") / "materiales.js").read_text(encoding="utf-8")


def test_materiales_usa_los_cuatro_verbos(js_materiales):
    for verbo in ("POST", "PUT", "DELETE"):
        assert verbo in js_materiales
    assert "/api/materiales/restaurar" in js_materiales


def test_materiales_pide_confirmacion_antes_de_borrar(js_materiales):
    """Borrar un material que se usa en trabajos anteriores no se deshace."""
    assert "confirm" in js_materiales


def test_materiales_muestra_la_veta_en_palabras(js_materiales):
    """La interfaz nunca muestra grados: nadie sabe qué significa 5."""
    assert "libre" in js_materiales and "respetar" in js_materiales
    assert "180" not in js_materiales


def test_materiales_refresca_el_desplegable_de_la_pantalla_principal(js_materiales):
    """Agregar un material y no verlo en la lista de al lado haría pensar
    que no se guardó."""
    assert "refrescarMateriales" in js_materiales
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_web_javascript.py -q`
Expected: FAIL con `FileNotFoundError` — no existe `materiales.js`

- [ ] **Step 3: Escribir el JavaScript**

Crear `src/nesting_app/web/materiales.js`:

```javascript
"use strict";

/* La pantalla de materiales: tabla, alta, edición y baja.
 *
 * La veta se muestra siempre en palabras. Un campo de grados entre 0 y 180
 * es exacto y no le dice nada a nadie: quien compra multilaminado sabe que
 * hay que respetar la veta, no que eso son 5 grados. */

const { apiJson, postJson, refrescarMateriales, mostrarError, $ } = window.__nesting;

let editando = null;

const LAPIZ = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 2.5l2 2L6 12l-3 1 1-3z"></path></svg>';
const TACHO = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 4h11"></path><path d="M6 4V2.5h4V4"></path><path d="M4 4l.6 9.5h6.8L12 4"></path></svg>';

const ETIQUETA_VETA = { libre: "No importa", respetar: "Respetar" };

$("btn-materiales").onclick = async () => {
  $("pantalla-materiales").classList.remove("oculto");
  await dibujarTabla();
};

$("btn-volver").onclick = () => {
  $("pantalla-materiales").classList.add("oculto");
  limpiarFormulario();
};

async function dibujarTabla() {
  let materiales;
  try {
    materiales = (await apiJson("/api/materiales")).materiales;
  } catch (error) {
    return mostrarError("No se pudo leer el catálogo", error.message);
  }

  const cuerpo = $("tabla-materiales");
  cuerpo.innerHTML = "";
  for (const m of materiales) {
    const fila = document.createElement("tr");
    fila.innerHTML =
      `<td>${m.nombre}</td>` +
      `<td class="der">${m.ancho}</td>` +
      `<td class="der">${m.alto}</td>` +
      `<td><span class="insignia ${m.veta}">${ETIQUETA_VETA[m.veta]}</span></td>` +
      `<td class="der"></td>`;

    const acciones = fila.lastElementChild;
    acciones.append(
      botonIcono(LAPIZ, `Editar ${m.nombre}`, () => cargarEnFormulario(m)),
      botonIcono(TACHO, `Borrar ${m.nombre}`, () => borrar(m.nombre))
    );
    cuerpo.append(fila);
  }
  await refrescarMateriales();
}

function botonIcono(svg, titulo, alClickear) {
  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "icono-boton";
  boton.setAttribute("aria-label", titulo);
  boton.innerHTML = svg;
  boton.onclick = alClickear;
  return boton;
}

function cargarEnFormulario(m) {
  editando = m.nombre;
  $("titulo-form").textContent = `Editar ${m.nombre}`;
  $("m-nombre").value = m.nombre;
  $("m-ancho").value = m.ancho;
  $("m-alto").value = m.alto;
  $(m.veta === "libre" ? "m-veta-libre" : "m-veta-respetar").checked = true;
}

function limpiarFormulario() {
  editando = null;
  $("titulo-form").textContent = "Nuevo material";
  $("form-material").reset();
  $("error-material").classList.add("oculto");
}

$("btn-cancelar-material").onclick = limpiarFormulario;

$("form-material").onsubmit = async (evento) => {
  evento.preventDefault();
  $("error-material").classList.add("oculto");
  const cuerpo = {
    nombre: $("m-nombre").value.trim(),
    ancho: Number($("m-ancho").value),
    alto: Number($("m-alto").value),
    veta: $("m-veta-libre").checked ? "libre" : "respetar",
  };
  try {
    if (editando) {
      await apiJson(`/api/materiales/${encodeURIComponent(editando)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo),
      });
    } else {
      await postJson("/api/materiales", cuerpo);
    }
  } catch (error) {
    $("error-material").textContent = error.message || "No se pudo guardar.";
    $("error-material").classList.remove("oculto");
    return;
  }
  limpiarFormulario();
  await dibujarTabla();
};

async function borrar(nombre) {
  // Borrar no se deshace, y el material puede estar en uso en trabajos que
  // el usuario todavía no repitió.
  if (!confirm(`¿Borrar el material "${nombre}"? No se puede deshacer.`)) return;
  try {
    await apiJson(`/api/materiales/${encodeURIComponent(nombre)}`, { method: "DELETE" });
  } catch (error) {
    return mostrarError("No se pudo borrar", error.message);
  }
  await dibujarTabla();
}

$("btn-restaurar").onclick = async () => {
  if (!confirm("¿Volver al catálogo original? Se pierden los materiales que agregaste."))
    return;
  try {
    await postJson("/api/materiales/restaurar", {});
  } catch (error) {
    return mostrarError("No se pudo restaurar", error.message);
  }
  limpiarFormulario();
  await dibujarTabla();
};
```

En `index.html`, después del `<script src="app.js"></script>`, agregar:

```html
<script src="materiales.js"></script>
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/python -m pytest tests/app/test_web_javascript.py -q`
Expected: PASS, 19 tests

- [ ] **Step 5: Commit**

```bash
git add src/nesting_app/web tests/app/test_web_javascript.py
git commit -m "Interfaz: la pantalla de materiales

La veta se muestra siempre en palabras. Un campo de grados entre 0 y 180
es exacto y no le dice nada a nadie: quien compra multilaminado sabe que
hay que respetar la veta, no que eso son 5 grados.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 13: La ventana de escritorio

**Files:**
- Create: `src/nesting_app/desktop.py`
- Modify: `pyproject.toml` (agregar el comando `nest-app`)
- Test: `tests/app/test_desktop.py`

**Interfaces:**
- Produces:
  - `servidor(deposito, registro) -> tuple[str, int, str]` — devuelve `(token, puerto, url)`, ya escuchando
  - `Puente` — la clase que pywebview expone al JavaScript: `elegir_archivo()`, `elegir_destino(sugerido)`, `guardar(destino, datos)`
  - `falta_webview2() -> bool`
  - `main(argv=None) -> int` — con `--autotest`
  - El `index.html` se sirve con `<meta name="token">` y `<meta name="escritorio">` inyectados

**Por qué `--autotest`:** los bugs de empaquetado —rutas que no resuelven, un módulo que PyInstaller no encontró— no aparecen en ningún test normal. Aparecen cuando el usuario abre el programa. Esta bandera los agarra en la máquina que compila.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/app/test_desktop.py`:

```python
"""El armado del servidor local, el puente de archivos y el autotest."""

import sys
import urllib.request

import pytest

from nesting_app import desktop, rutas
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    registro = Registro(tmp_path / "trabajos")
    token, puerto, url = desktop.servidor(Deposito(tmp_path / "fuentes"), registro)
    yield token, puerto, url
    registro.cerrar()
    desktop.apagar()


def test_escucha_solo_en_localhost(servidor):
    """Escuchar en 0.0.0.0 expondría el programa a toda la red local: la
    máquina de al lado podría mandarle trabajos y leer rutas de archivos."""
    _, _, url = servidor
    assert url.startswith("http://127.0.0.1:")


def test_el_puerto_lo_elige_el_sistema(servidor):
    """Un puerto fijo choca el día que el usuario tenga otra cosa escuchando
    ahí, y el programa no abriría sin decir por qué."""
    _, puerto, _ = servidor
    assert puerto > 0


def test_el_token_es_largo_y_distinto_en_cada_arranque(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    tokens = set()
    for i in range(3):
        registro = Registro(tmp_path / f"t{i}")
        token, _, _ = desktop.servidor(Deposito(tmp_path / f"f{i}"), registro)
        tokens.add(token)
        registro.cerrar()
        desktop.apagar()

    assert len(tokens) == 3
    assert all(len(t) >= 32 for t in tokens)


def test_la_pagina_trae_el_token_adentro(servidor):
    """Es cómo lo recibe el JavaScript. En la web lo va a inyectar el
    servidor con la sesión del usuario, sin tocar el JavaScript."""
    token, _, url = servidor

    html = urllib.request.urlopen(url, timeout=5).read().decode("utf-8")

    assert f'name="token" content="{token}"' in html
    assert 'name="escritorio" content="1"' in html


def test_sin_token_la_api_rechaza(servidor):
    _, _, url = servidor

    with pytest.raises(Exception) as capturado:
        urllib.request.urlopen(f"{url}/api/materiales", timeout=5)

    assert "401" in str(capturado.value)


def test_con_token_la_api_responde(servidor):
    token, _, url = servidor
    pedido = urllib.request.Request(f"{url}/api/materiales", headers={"X-Token": token})

    respuesta = urllib.request.urlopen(pedido, timeout=5)

    assert respuesta.status == 200


def test_autotest_sale_con_cero(tmp_path, monkeypatch, capsys):
    """La prueba que corre sobre el ejecutable congelado. Los bugs de
    empaquetado no aparecen en ningún otro test."""
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")

    assert desktop.main(["--autotest"]) == 0
    assert "ok" in capsys.readouterr().out.lower()


def test_autotest_falla_si_falta_un_recurso(tmp_path, monkeypatch, capsys):
    """Es exactamente el modo en que rompe un ejecutable mal armado."""
    monkeypatch.setattr(rutas, "_base_de_datos", lambda: tmp_path / "datos")
    monkeypatch.setattr(
        rutas, "recurso",
        lambda nombre: (_ for _ in ()).throw(FileNotFoundError(f"falta {nombre}")),
    )

    assert desktop.main(["--autotest"]) == 1
    assert "falta" in capsys.readouterr().err.lower()


def test_webview2_solo_se_verifica_en_windows(monkeypatch):
    """En Mac y Linux la pregunta no tiene sentido y tiene que dar False sin
    tocar el registro de Windows."""
    monkeypatch.setattr(sys, "platform", "darwin")
    assert desktop.falta_webview2() is False


def test_el_puente_rechaza_guardar_fuera_de_lo_que_el_usuario_eligio(tmp_path):
    """El destino lo elige el usuario en un diálogo nativo. Aceptar una ruta
    que el JavaScript arme sola sería dejarlo escribir donde quiera."""
    puente = desktop.Puente()

    with pytest.raises(PermissionError):
        puente.guardar(str(tmp_path / "no_elegido.dxf"), [1, 2, 3])


def test_el_puente_guarda_lo_que_el_usuario_eligio(tmp_path):
    puente = desktop.Puente()
    destino = tmp_path / "elegido.dxf"
    puente._autorizar(str(destino))

    puente.guardar(str(destino), [65, 66])

    assert destino.read_bytes() == b"AB"


def test_arranca_sin_nada_pendiente_de_guardar():
    assert desktop.Puente().hay_sin_guardar is False


def test_la_interfaz_puede_marcar_que_hay_algo_sin_guardar():
    """El DXF vive en una carpeta temporal hasta que el usuario lo guarda.
    Cerrar el programa sin guardarlo pierde media hora de acomodo, y sin
    este aviso se pierde en silencio."""
    puente = desktop.Puente()

    puente.marcar_sin_guardar(True)
    assert puente.hay_sin_guardar is True

    puente.marcar_sin_guardar(False)
    assert puente.hay_sin_guardar is False


def test_guardar_deja_de_marcar_pendiente(tmp_path):
    """Guardar es justamente lo que resuelve el pendiente. Que el JavaScript
    tenga que acordarse de avisarlo aparte sería una forma de olvidarse."""
    puente = desktop.Puente()
    puente.marcar_sin_guardar(True)
    destino = tmp_path / "elegido.dxf"
    puente._autorizar(str(destino))

    puente.guardar(str(destino), [65])

    assert puente.hay_sin_guardar is False
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/bin/python -m pytest tests/app/test_desktop.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting_app.desktop'`

- [ ] **Step 3: Escribir la implementación mínima**

Crear `src/nesting_app/desktop.py`:

```python
"""Levanta el servidor local y abre la ventana.

Es el único archivo del paquete que sabe de ventanas. Sacándolo, lo que
queda es un servidor HTTP que sirve exactamente igual detrás de un dominio.
"""

import argparse
import secrets
import sys
import threading
import urllib.request
from pathlib import Path

import uvicorn

from nesting_app import rutas
from nesting_app.api import crear_app
from nesting_app.archivos import Deposito
from nesting_app.jobs import Registro

_servidor: uvicorn.Server | None = None
_hilo: threading.Thread | None = None


def falta_webview2() -> bool:
    """Si en Windows falta el runtime de WebView2.

    Sin él la ventana abre en blanco y el usuario no tiene forma de adivinar
    qué pasó. Windows 11 lo trae siempre y Windows 10 casi siempre, pero
    'casi' no sirve cuando el programa se lo mandás a otra persona.
    """
    if sys.platform != "win32":
        return False
    import winreg

    claves = [
        r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
        r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
        r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    ]
    for clave in claves:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, clave) as k:
                if winreg.QueryValueEx(k, "pv")[0] not in ("", "0.0.0.0"):
                    return False
        except OSError:
            continue
    return True


class _ConToken:
    """Sirve `index.html` con el token inyectado, y el resto sin tocar.

    El token viaja en un `<meta>` y no en la URL: una URL queda en el
    historial y en cualquier `Referer` que la página mande.
    """

    def __init__(self, app, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] in ("/", "/index.html"):
            html = (rutas.recurso("web") / "index.html").read_text(encoding="utf-8")
            html = html.replace(
                "<head>",
                f'<head>\n<meta name="token" content="{self.token}">'
                f'\n<meta name="escritorio" content="1">',
                1,
            )
            cuerpo = html.encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", str(len(cuerpo)).encode()),
                    (b"cache-control", b"no-store"),
                ],
            })
            await send({"type": "http.response.body", "body": cuerpo})
            return
        await self.app(scope, receive, send)


class Puente:
    """Lo que pywebview le expone al JavaScript: diálogos nativos.

    Guardar sólo acepta rutas que salieron de un diálogo que el usuario vio.
    Sin esa lista, el JavaScript podría armar cualquier ruta y escribir
    donde quisiera -- y el JavaScript es justamente la parte que, en la
    versión web, va a correr contra contenido que no controlamos.
    """

    def __init__(self) -> None:
        self._autorizadas: set[str] = set()
        self.ventana = None
        self.hay_sin_guardar = False
        """Si hay un DXF acomodado que todavía no se guardó a ningún lado.

        El resultado vive en una carpeta temporal que se borra al cerrar. Sin
        este aviso, cerrar la ventana tira media hora de acomodo sin decir
        una palabra.
        """

    def marcar_sin_guardar(self, valor: bool) -> None:
        self.hay_sin_guardar = bool(valor)

    def _autorizar(self, destino: str) -> None:
        self._autorizadas.add(str(Path(destino).resolve()))

    def elegir_archivo(self) -> list[str]:
        import webview

        elegidos = self.ventana.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("Dibujos vectoriales (*.dxf;*.ai;*.3dm)",),
        )
        return list(elegidos or [])

    def elegir_destino(self, sugerido: str) -> str | None:
        import webview

        elegido = self.ventana.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=sugerido
        )
        if not elegido:
            return None
        destino = elegido if isinstance(elegido, str) else elegido[0]
        self._autorizar(destino)
        return destino

    def guardar(self, destino: str, datos: list[int]) -> None:
        if str(Path(destino).resolve()) not in self._autorizadas:
            raise PermissionError(
                "ese destino no salió de un diálogo de guardado"
            )
        Path(destino).write_bytes(bytes(datos))
        # Guardar es lo que resuelve el pendiente. Dejar que el JavaScript se
        # acuerde de avisarlo aparte sería una forma de olvidarse.
        self.hay_sin_guardar = False


def servidor(deposito: Deposito, registro: Registro) -> tuple[str, int, str]:
    """Arranca uvicorn en un hilo y devuelve (token, puerto, url)."""
    global _servidor, _hilo

    token = secrets.token_urlsafe(32)
    app = _ConToken(crear_app(token, deposito, registro), token)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    _servidor = uvicorn.Server(config)
    _hilo = threading.Thread(target=_servidor.run, daemon=True)
    _hilo.start()

    while not _servidor.started:
        if not _hilo.is_alive():
            raise RuntimeError("el servidor local no pudo arrancar")
    puerto = _servidor.servers[0].sockets[0].getsockname()[1]
    return token, puerto, f"http://127.0.0.1:{puerto}"


def apagar() -> None:
    global _servidor
    if _servidor is not None:
        _servidor.should_exit = True
        if _hilo is not None:
            _hilo.join(timeout=5)
        _servidor = None


def _autotest() -> int:
    """Arranca todo y pide una ruta. Sale 0 si el paquete está bien armado.

    Los bugs de empaquetado -- una ruta que no resuelve, un módulo que
    PyInstaller no encontró, `materials.yaml` que no está donde el código lo
    busca -- no aparecen en ningún test normal: aparecen cuando el usuario
    abre el programa. Esto los agarra en la máquina que compila.
    """
    registro = Registro(Path(rutas.carpeta_datos()) / "autotest")
    try:
        token, _, url = servidor(Deposito(Path(rutas.carpeta_datos()) / "autotest-f"), registro)
        pedido = urllib.request.Request(
            f"{url}/api/materiales", headers={"X-Token": token}
        )
        with urllib.request.urlopen(pedido, timeout=10) as respuesta:
            if respuesta.status != 200:
                raise RuntimeError(f"la API respondió {respuesta.status}")
        urllib.request.urlopen(url, timeout=10).read()
    except Exception as error:  # noqa: BLE001 - es el punto del autotest
        print(f"autotest FALLÓ: {error}", file=sys.stderr)
        return 1
    finally:
        registro.cerrar()
        apagar()
    print("autotest ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nest-app")
    parser.add_argument(
        "--autotest", action="store_true",
        help="arranca todo, pide una ruta y sale; para verificar el ejecutable",
    )
    args = parser.parse_args(argv)

    if args.autotest:
        return _autotest()

    if falta_webview2():
        print(
            "Falta el runtime de WebView2, que es lo que dibuja la ventana.\n"
            "Se baja gratis de https://go.microsoft.com/fwlink/p/?LinkId=2124703",
            file=sys.stderr,
        )
        return 1

    import webview

    carpeta = rutas.carpeta_datos()
    deposito = Deposito(carpeta / "fuentes")
    deposito.limpiar()  # restos de una corrida anterior que terminó mal
    registro = Registro(carpeta / "trabajos")
    _, _, url = servidor(deposito, registro)

    puente = Puente()
    ventana = webview.create_window(
        "Nesting", url, width=1100, height=720, min_size=(960, 640), js_api=puente
    )
    puente.ventana = ventana

    def al_cerrar() -> bool:
        """Devolver False cancela el cierre."""
        if not puente.hay_sin_guardar:
            return True
        return ventana.create_confirmation_dialog(
            "Hay un acomodo sin guardar",
            "El DXF todavía no se guardó en ningún lado y se va a perder. "
            "¿Cerrar igual?",
        )

    ventana.events.closing += al_cerrar
    try:
        webview.start()
    finally:
        registro.cerrar()
        deposito.limpiar()
        apagar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

En `pyproject.toml`, agregar bajo `[project.scripts]`:

```toml
nest-app = "nesting_app.desktop:main"
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `.venv/bin/pip install -e . && .venv/bin/python -m pytest tests/app/test_desktop.py -q`
Expected: PASS, 14 tests

- [ ] **Step 5: Correr TODA la suite y abrir la ventana a mano**

Run: `.venv/bin/python -m pytest -q -p no:warnings`
Expected: PASS

Run: `.venv/bin/nest-app`
Expected: se abre una ventana. Verificar a mano, con `files/robot.ai`:
1. Elegir el archivo abre el diálogo nativo del sistema.
2. Aparece "93 piezas · 3 descartes".
3. El link de descartes muestra la imagen de revisión con los círculos.
4. Acomodar con separación 3 y esfuerzo rápido muestra el avance y termina en ~34 s.
5. El resultado dice 1 placa, 47,7%, sobrante ~708 mm.
6. Guardar DXF abre "Guardar como" y escribe donde se le indique.
7. Cancelar a mitad de una corrida en lento la corta en menos de un segundo.
8. Cerrar la ventana con un acomodo sin guardar pregunta antes de cerrar.
9. Cerrar después de guardar no pregunta nada.

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app/desktop.py pyproject.toml tests/app/test_desktop.py
git commit -m "desktop.py: la ventana, el puerto libre y el token

Único archivo del paquete que sabe de ventanas. Sacándolo queda un
servidor HTTP que sirve igual detrás de un dominio.

El token viaja en un meta y no en la URL: una URL queda en el historial
y en cualquier Referer que la página mande. Guardar sólo acepta rutas que
salieron de un diálogo que el usuario vio.

--autotest arranca todo y pide una ruta. Los bugs de empaquetado no
aparecen en ningún test normal: aparecen cuando el usuario abre el
programa.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 14: Empaquetado para Mac

**Files:**
- Create: `packaging/nesting.spec`, `packaging/construir.sh`
- Modify: `pyproject.toml` (`pyinstaller` en las dependencias de desarrollo)

**Interfaces:**
- Produces: `dist/Nesting/` y `dist/Nesting-mac-arm64.zip`

**Lo que queda pendiente y es decisión del usuario:** el `.exe` de Windows. PyInstaller no compila cruzado y este Mac es ARM, así que hace falta una máquina Windows x64 — GitHub Actions, una VM con Parallels, o una PC prestada. La spec deja esa decisión abierta a propósito. **Esta tarea no la toma.**

- [ ] **Step 1: Escribir el archivo de PyInstaller**

Crear `packaging/nesting.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
"""Cómo se arma el ejecutable.

Modo CARPETA, no archivo único: el modo de archivo único se autodescomprime
en cada arranque, y con 300 MB de scipy y rhino3dm eso son varios segundos
de nada cada vez que alguien abre el programa.
"""

from pathlib import Path

RAIZ = Path(SPECPATH).parent

# Los recursos que `rutas.recurso()` va a buscar. Que falte alguno rompe el
# programa recién cuando el usuario lo abre, por eso existe `--autotest`.
datos = [
    (str(RAIZ / "materials.yaml"), "."),
    (str(RAIZ / "src" / "nesting_app" / "web"), "web"),
]

# scipy y rhino3dm cargan cosas que PyInstaller no ve siguiendo imports.
ocultos = [
    "scipy._lib.array_api_compat.numpy.fft",
    "scipy.special._special_ufuncs",
    "rhino3dm._rhino3dm",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

a = Analysis(
    [str(RAIZ / "src" / "nesting_app" / "desktop.py")],
    pathex=[str(RAIZ / "src")],
    datas=datos,
    hiddenimports=ocultos,
    excludes=["tkinter", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Nesting",
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="Nesting",
)
```

- [ ] **Step 2: Escribir el script de construcción**

Crear `packaging/construir.sh`:

```bash
#!/usr/bin/env bash
# Arma el ejecutable y lo verifica antes de comprimirlo.
#
# El paso de verificación no es opcional: un paquete al que le falta un
# recurso o un módulo oculto se ve perfecto acá y falla en la máquina del
# que lo recibe.
set -euo pipefail

cd "$(dirname "$0")/.."
RAIZ="$PWD"

echo "== limpiando =="
rm -rf build dist

echo "== construyendo =="
.venv/bin/pyinstaller --noconfirm --distpath dist --workpath build packaging/nesting.spec

echo "== verificando el paquete =="
if [[ "$OSTYPE" == "darwin"* ]]; then
  ./dist/Nesting/Nesting --autotest
else
  ./dist/Nesting/Nesting.exe --autotest
fi

echo "== comprimiendo =="
PLATAFORMA="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
cd dist && zip -qr "Nesting-${PLATAFORMA}.zip" Nesting && cd "$RAIZ"

echo
du -sh dist/Nesting
ls -lh dist/*.zip
```

Hacerlo ejecutable:

```bash
chmod +x packaging/construir.sh
```

En `pyproject.toml`, cambiar las dependencias de desarrollo:

```toml
dev = ["pytest", "pyinstaller"]
```

- [ ] **Step 3: Instalar y construir**

```bash
.venv/bin/pip install -e ".[dev]"
./packaging/construir.sh
```

Expected: termina con `autotest ok` y muestra el peso. Si `--autotest` falla nombrando un recurso, agregarlo a `datos` en el `.spec`; si falla con `ModuleNotFoundError`, agregarlo a `ocultos`.

- [ ] **Step 4: Probar el paquete a mano**

```bash
open dist/Nesting/Nesting
```

Expected: la ventana abre y el recorrido completo funciona igual que con `nest-app`. **Sobre todo el desplegable de materiales**, que es el que depende de la ruta que se arregló en la Task 2.

- [ ] **Step 5: Anotar el peso medido**

En la spec, sección 6, reemplazar "Peso estimado: 250-400 MB en disco, 100-150 MB comprimido. A medir." por los números reales que imprimió el script.

- [ ] **Step 6: Commit**

```bash
git add packaging pyproject.toml docs/superpowers/specs/2026-09-19-interfaz-grafica-design.md
echo "build/" >> .gitignore
echo "dist/" >> .gitignore
git add .gitignore
git commit -m "Empaquetado para Mac, con verificación antes de comprimir

Modo carpeta y no archivo único: el archivo único se autodescomprime en
cada arranque, y con 300 MB eso son varios segundos cada vez.

El script corre --autotest sobre el paquete armado antes de comprimirlo.
Un paquete al que le falta un recurso se ve perfecto en la máquina que lo
compiló y falla en la del que lo recibe.

El .exe de Windows queda pendiente: PyInstaller no compila cruzado y este
Mac es ARM. Hace falta una máquina Windows x64 y esa decisión es del
usuario.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Qué queda afuera de este plan

- **El `.exe` de Windows.** Necesita una máquina Windows x64. La decisión entre GitHub Actions, una VM o una PC prestada quedó abierta a propósito hasta tener el programa funcionando.
- **Instalador (.msi / setup.exe).** Se suma después sin tocar una línea del programa.
- **Firmar el ejecutable.** Sin firma, Windows muestra la advertencia de SmartScreen la primera vez.
- **Cantidades por pieza.** Toca el motor además de la interfaz.
- **Acomodar a mano.** Exige verificación de colisiones en vivo.
- **Tests automáticos de la interfaz en un navegador.** Lo que hay son tests de contrato sobre el HTML y el JavaScript, más la lista de verificación manual de la Task 13.
- **La versión web.** Este plan la deja alcanzable: desplegar, sumar usuarios y aislamiento, y cambiar el hilo único por una cola de procesos. Nada de eso toca la interfaz.
