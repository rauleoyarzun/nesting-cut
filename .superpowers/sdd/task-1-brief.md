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

