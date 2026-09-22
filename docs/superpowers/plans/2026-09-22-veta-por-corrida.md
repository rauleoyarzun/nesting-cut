# Veta por corrida, y posiciones que la respetan — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la veta se vea y se pueda cambiar por corrida sin tocar el catálogo, y que con la veta respetada Posiciones quede fija en 0° y 180°, con un cartel apenas aparece un conflicto.

**Architecture:** `NestParams` gana `veta` (`"respetar"`, `"libre"` o `None` = la del material). Una sola función, `tolerancia_de_veta`, traduce eso a grados, y `a_supply` la aplica a la placa del material y a cada recorte. La CLI deja de armar su plan de placas a mano y pasa por `a_supply`. En la pantalla, un control de radio arranca con la veta del material; con "Respetar", el desplegable de Posiciones se bloquea en una opción oculta de dos ángulos y recuerda lo que había.

**Tech Stack:** Python 3.13, pytest. Interfaz en HTML/CSS/JavaScript a mano, sin framework; sus tests leen los archivos estáticos como texto y no corren navegador.

**Spec:** `docs/superpowers/specs/2026-09-22-veta-por-corrida-design.es.md`

## Global Constraints

- **TDD sin excepciones:** test que falla, correrlo para verlo fallar, implementación mínima, test que pasa, commit. Un paso por vez.
- **Todo texto de cara al usuario va en español**, con tildes y eñes. El signo de grado es `°` (U+00B0), nunca la palabra "grados" en un desplegable.
- **Idioma del código:** los identificadores van en inglés en `src/nesting/engine/`, `model/`, `io/` y `geometry/`, y en español en `params.py` y en todo `src/nesting_app/`. Los docstrings y comentarios son mixtos en todo el repo; **no es un hallazgo de revisión** que estén en un idioma u otro.
- **Nada de emojis.** `test_no_hay_emojis_en_la_interfaz` ya lo prohíbe.
- **Ningún token de color nuevo en `app.css`.** Los controles nuevos reusan `.opcion`, `.resumen`, `.cartel` y `.cartel-caja`, que ya existen.
- **`params.py` no puede arrastrar el motor.** `test_importar_los_parametros_no_arrastra_el_motor` verifica que importarlo no cargue `shapely`, `ezdxf`, `rhino3dm` ni `scipy`. `nesting.model.sheet` y `nesting.model.material` son livianos; nada más se importa.
- **Sin `veta`, nada cambia.** Con `veta=None`, cada tarea tiene que dejar el mismo plan de placas, el mismo layout y los mismos números que antes del plan.
- **Los tests de JavaScript miran cuerpos, no el archivo entero.** `tests/app/test_web_javascript.py` ya tiene `_cuerpo_de_funcion(js, "nombre")` y `_cuerpo_de_handler(js, "evento")`, que además borran los comentarios. Usarlos. `_cuerpo_de_funcion` corta en el primer `}` que arranca un renglón: ninguna función nueva puede tener un bloque anidado que cierre en la columna 0.
- **Correr la suite entera** (`.venv/bin/pytest`) al cerrar cada tarea, no sólo los tests nuevos. Tarda unos 7 minutos; `tests/app` solo tarda unos 10 segundos y sirve para iterar.
- **Nada de `Co-Authored-By` ni atribución en los mensajes de commit.**

## Mapa de archivos

| Archivo | Responsabilidad | Tarea |
|---|---|---|
| `src/nesting/model/material.py` | Gana `VETA_LIBRE` y `VETA_RESPETAR`, mudadas desde la interfaz. | 1 |
| `src/nesting_app/materials_store.py` | Reexporta las dos constantes en vez de definirlas. | 1 |
| `src/nesting/params.py` | `NestParams.veta`, `tolerancia_de_veta`, `a_supply` con la tolerancia de la corrida, `validar` con material. | 1, 2 |
| `src/nesting/cli.py` | `--veta`, plan de placas por `a_supply`, validación con material. | 3 |
| `src/nesting_app/api.py` | `ParamsEntrada.veta`; `crear_trabajo` valida con el material. | 4 |
| `src/nesting_app/web/index.html` | Control Veta, opción bloqueada de Posiciones, nota, cartel. | 5, 6 |
| `src/nesting_app/web/app.js` | Estado de la veta, bloqueo de Posiciones, cartel de conflicto. | 5, 6 |
| `src/nesting_app/web/info.js` | Globo de `veta`; el de `angulos` pierde la frase de la veta. | 7 |
| `README.md` / `README.es.md` | Fila de Veta en la tabla de opciones. | 7 |

---

### Task 1: La veta de la corrida llega al plan de placas

**Files:**
- Modify: `src/nesting/model/material.py`
- Modify: `src/nesting_app/materials_store.py:16-24`
- Modify: `src/nesting/params.py`
- Test: `tests/test_params.py`

**Interfaces:**
- Consumes: `Sheet`, `SheetSupply` de `nesting.model.sheet`; `Material.stock_sheet()`.
- Produces:
  - `nesting.model.material.VETA_LIBRE: float = 180.0` y `VETA_RESPETAR: float = 5.0`.
  - `nesting.params.Veta = Literal["respetar", "libre"]`.
  - `NestParams.veta: Veta | None = None`.
  - `nesting.params.tolerancia_de_veta(p: NestParams, material: Material) -> float`.
  - `a_supply(p, material)` aplica `tolerancia_de_veta` a `stock` y a cada recorte.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_params.py`:

```python
# --- la veta de la corrida -------------------------------------------------

from nesting.model.material import VETA_LIBRE, VETA_RESPETAR
from nesting.params import tolerancia_de_veta


def test_sin_veta_manda_la_del_material():
    assert tolerancia_de_veta(NestParams(material="mdf18"), MDF) == 180.0
    assert tolerancia_de_veta(NestParams(material="fenolico18"), FENOLICO) == 5.0


@pytest.mark.parametrize("material", [MDF, FENOLICO])
def test_respetar_pisa_a_cualquier_material(material):
    params = NestParams(material=material.name, veta="respetar")
    assert tolerancia_de_veta(params, material) == VETA_RESPETAR


@pytest.mark.parametrize("material", [MDF, FENOLICO])
def test_libre_pisa_a_cualquier_material(material):
    params = NestParams(material=material.name, veta="libre")
    assert tolerancia_de_veta(params, material) == VETA_LIBRE


def test_la_veta_de_la_corrida_llega_a_la_placa_del_material():
    params = NestParams(material="fenolico18", veta="libre")
    assert a_supply(params, FENOLICO).stock.grain_tolerance == VETA_LIBRE


def test_la_veta_de_la_corrida_llega_a_los_recortes():
    params = NestParams(
        material="mdf18", veta="respetar", recortes=(Recorte(600.0, 800.0),)
    )
    plan = a_supply(params, MDF)

    assert plan.scraps[0].grain_tolerance == VETA_RESPETAR
    assert plan.stock.grain_tolerance == VETA_RESPETAR


def test_sin_veta_el_plan_queda_igual_que_antes():
    """El contrato de todo el plan: sin tocar la veta, nada cambia."""
    params = NestParams(material="fenolico18", recortes=(Recorte(600.0, 800.0),))
    plan = a_supply(params, FENOLICO)

    assert plan.stock == FENOLICO.stock_sheet()
    assert plan.scraps[0].grain_tolerance == FENOLICO.grain_tolerance


def test_las_constantes_de_veta_viven_en_el_modelo():
    """El motor no puede importar la interfaz, así que las constantes que
    usa `tolerancia_de_veta` tienen que vivir de este lado. La interfaz las
    reexporta para no romper a quien ya las usaba."""
    from nesting_app import materials_store

    assert materials_store.VETA_LIBRE is VETA_LIBRE
    assert materials_store.VETA_RESPETAR is VETA_RESPETAR
```

- [ ] **Step 2: Correrlos para verlos fallar**

Run: `.venv/bin/pytest tests/test_params.py -v -k "veta"`
Expected: FAIL con `ImportError: cannot import name 'VETA_LIBRE' from 'nesting.model.material'`.

- [ ] **Step 3: Mudar las constantes al modelo**

En `src/nesting/model/material.py`, después de `from nesting.model.sheet import Sheet`, agregar:

```python
VETA_LIBRE = 180.0
"""La pieza gira libre. Típico del MDF.

Por convención del catálogo, cualquier valor de 90 o más equivale a rotación
libre; 180 es el que usa el catálogo que trae el programa.

Vive acá y no en `nesting_app.materials_store`, donde nació, porque
`nesting.params.tolerancia_de_veta` la necesita y el motor no puede importar
la interfaz sin invertir la dependencia que sostiene la arquitectura.
"""

VETA_RESPETAR = 5.0
"""Sólo 0 y 180 grados: corte cruzado bloqueado. Multilaminado, fenólico.

La pantalla repite este número como `TOLERANCIA_VETA` en `app.js`, para
saber sin preguntarle al servidor qué ángulos choca la veta. Si cambia acá,
cambia allá.
"""
```

En `src/nesting_app/materials_store.py`, reemplazar las líneas 16 a 24 (las dos definiciones con sus docstrings) y el `from nesting.model.material import Material, load_materials` por:

```python
from nesting.model.material import (  # noqa: F401 - reexportadas: api.py y los tests las leen de acá
    VETA_LIBRE,
    VETA_RESPETAR,
    Material,
    load_materials,
)
```

- [ ] **Step 4: `NestParams.veta`, `tolerancia_de_veta` y `a_supply`**

En `src/nesting/params.py`:

Cambiar los imports del principio a:

```python
from dataclasses import dataclass, replace
from typing import Literal

from nesting.engine.oracle import NestConfig
from nesting.model.material import VETA_LIBRE, VETA_RESPETAR, Material
from nesting.model.sheet import Sheet, SheetSupply
from nesting.tolerances import DEFAULT_CHAIN_TOL

DEFAULT_ANGLES: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)

Veta = Literal["respetar", "libre"]
"""Las dos palabras con que la interfaz y la CLI hablan de la veta."""
```

En `NestParams`, después de `recortes: tuple[Recorte, ...] = ()`, agregar:

```python
    veta: Veta | None = None
    """La veta de ESTA corrida. `None` es "la que diga el material".

    Es de la corrida y no del catálogo por lo mismo que los recortes: el
    catálogo dice lo que el material suele necesitar, y un trabajo concreto
    -- piezas que no se ven, un fenólico usado de base -- puede no
    necesitarlo. Ver `tolerancia_de_veta`.
    """
```

Agregar, antes de `def a_supply`:

```python
def tolerancia_de_veta(p: NestParams, material: Material) -> float:
    """Los grados de tolerancia que valen para esta corrida.

    La única traducción de `NestParams.veta` a grados. `a_supply` y
    `validar` pasan por acá, para que el plan de placas y la regla de los
    ángulos no puedan leer la veta de dos maneras distintas.
    """
    if p.veta is None:
        return material.grain_tolerance
    return VETA_RESPETAR if p.veta == "respetar" else VETA_LIBRE
```

Reemplazar el cuerpo de `a_supply` por:

```python
    tolerancia = tolerancia_de_veta(p, material)
    hojas = [
        Sheet(
            width=recorte.ancho,
            height=recorte.alto,
            grain_tolerance=tolerancia,
            cross_grain=recorte.veta_cruzada,
            scrap=True,
        )
        for recorte in p.recortes
        for _ in range(recorte.cantidad)
    ]
    hojas.sort(key=lambda hoja: hoja.area, reverse=True)
    return SheetSupply(
        stock=replace(material.stock_sheet(), grain_tolerance=tolerancia),
        scraps=tuple(hojas),
        material_name=material.name,
    )
```

y sumar al docstring de `a_supply` este párrafo al final:

```python
    La veta sale de `tolerancia_de_veta`, no de `material.grain_tolerance`:
    si la corrida dijo "no importa", un recorte de fenólico tampoco la
    respeta.
```

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/pytest tests/test_params.py tests/app/test_materials_store.py -v`
Expected: PASS, incluido `test_importar_los_parametros_no_arrastra_el_motor`.

- [ ] **Step 6: Correr la suite entera**

Run: `.venv/bin/pytest`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/model/material.py src/nesting_app/materials_store.py src/nesting/params.py tests/test_params.py
git commit -m "Parámetros: la veta es de la corrida, y el plan de placas la obedece"
```

---

### Task 2: `validar` frena una lista de ángulos que la veta deja vacía

Hoy, `angulos=(90,)` con un multilam termina en un `PartTooLargeError` que habla de medidas. Con el material a mano, `validar` lo frena antes y dice qué pasó.

**Files:**
- Modify: `src/nesting/params.py` (`FLAG_POR_CAMPO`, `validar`)
- Test: `tests/test_params.py`

**Interfaces:**
- Consumes: `tolerancia_de_veta` (Task 1); `allowed_angles(sheet, angles)` de `nesting.model.sheet`.
- Produces: `validar(p: NestParams, material: Material | None = None) -> None`. Con material, levanta `ParamsInvalidosError(ReglaRota("angulos", REGLA_VETA, p.angulos))` si ningún ángulo sobrevive a la veta. `FLAG_POR_CAMPO["angulos"] == "--angulos"`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_params.py`:

```python
from nesting.params import REGLA_VETA


def test_con_la_veta_respetada_un_solo_angulo_cruzado_se_rechaza():
    params = NestParams(material="fenolico18", angulos=(90.0,))

    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(params, FENOLICO)

    assert capturado.value.rota.campo == "angulos"
    assert capturado.value.rota.regla == REGLA_VETA
    assert capturado.value.rota.valor == (90.0,)


def test_con_la_veta_libre_el_mismo_angulo_pasa():
    validar(NestParams(material="fenolico18", angulos=(90.0,), veta="libre"), FENOLICO)


def test_la_veta_de_la_corrida_manda_sobre_la_del_material():
    params = NestParams(material="mdf18", angulos=(90.0,), veta="respetar")

    with pytest.raises(ParamsInvalidosError):
        validar(params, MDF)


def test_basta_un_angulo_que_sobreviva():
    """0,90,180,270 con veta: 90 y 270 se descartan, pero 0 y 180 quedan.
    Eso no es un error de la corrida: es lo que la pantalla ya bloquea."""
    validar(NestParams(material="fenolico18"), FENOLICO)


def test_sin_material_no_se_mira_la_veta():
    """La CLI valida dos veces: antes de leer el catálogo (sin material) y
    después (con material). La primera no puede saber nada de la veta."""
    validar(NestParams(material="fenolico18", angulos=(90.0,)))


def test_la_regla_de_la_veta_nombra_los_angulos_que_sirven():
    assert "0°" in REGLA_VETA and "180°" in REGLA_VETA


def test_el_mensaje_de_la_cli_para_la_veta_nombra_el_flag():
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(NestParams(material="fenolico18", angulos=(90.0,)), FENOLICO)

    assert mensaje_cli(capturado.value.rota).startswith("--angulos tiene que ser ")
```

Y en `test_todo_campo_con_regla_tiene_su_flag`, sumar `"angulos"` a la tupla:

```python
    for campo in ("copias", "sep", "borde", "tol_cierre", "resolucion", "angulos"):
```

- [ ] **Step 2: Correrlos para verlos fallar**

Run: `.venv/bin/pytest tests/test_params.py -v -k "veta or angulo or flag"`
Expected: FAIL con `ImportError: cannot import name 'REGLA_VETA'`.

- [ ] **Step 3: Implementar**

En `src/nesting/params.py`:

Cambiar el import de `nesting.model.sheet` a:

```python
from nesting.model.sheet import Sheet, SheetSupply, allowed_angles
```

Sumar `"angulos": "--angulos",` a `FLAG_POR_CAMPO`.

Agregar, antes de `def validar`:

```python
REGLA_VETA = "compatible con la veta: al menos un ángulo a 0° o 180°"
"""La regla que se rompe cuando la veta no deja ningún ángulo en pie.

Se redacta como las demás ("tiene que ser ...") porque sale por los mismos
dos caminos: `mensaje_cli` en la terminal y el `detail` del 422 en la API.
"""
```

Cambiar la firma y el docstring de `validar`, y agregar el chequeo al final:

```python
def validar(p: NestParams, material: Material | None = None) -> None:
    """Levanta `ParamsInvalidosError` en el primer parámetro que no cumple.

    El orden es el mismo que tenía `_validate_numeric_args` en `cli.py`, para
    que un comando con dos errores a la vez siga señalando el mismo primero.

    Con `material`, además, se fija que la veta deje en pie al menos uno de
    los ángulos pedidos. Sin él no puede saberlo: la CLI valida una vez antes
    de leer el catálogo y otra después.
    """
```

y, después del `for indice, recorte in enumerate(p.recortes, start=1):` con sus tres `if`, agregar:

```python
    if material is not None:
        # Contra la placa del material y no contra los recortes: si en ella
        # no sobrevive ningún ángulo, la primera pieza que no entre en un
        # recorte no tiene dónde ir, y el motor lo cuenta como una pieza
        # demasiado grande -- un mensaje sobre medidas para un problema de
        # ángulos.
        placa = Sheet(
            width=material.sheet_w,
            height=material.sheet_h,
            grain_tolerance=tolerancia_de_veta(p, material),
        )
        if not allowed_angles(placa, p.angulos):
            raise ParamsInvalidosError(ReglaRota("angulos", REGLA_VETA, p.angulos))
```

`tolerancia_de_veta` está definida más abajo en el mismo módulo; eso está bien porque se resuelve al llamar, no al importar.

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/pytest tests/test_params.py -v`
Expected: PASS.

- [ ] **Step 5: Correr la suite entera**

Run: `.venv/bin/pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/params.py tests/test_params.py
git commit -m "Parámetros: una lista de ángulos que la veta deja vacía se rechaza con su nombre"
```

---

### Task 3: La CLI gana `--veta` y arma el plan con `a_supply`

**Files:**
- Modify: `src/nesting/cli.py`
- Test: `tests/test_cli.py`, `tests/test_cli_full.py:104-111`

**Interfaces:**
- Consumes: `NestParams.veta`, `validar(p, material)`, `a_config`, `a_supply` (Tasks 1 y 2).
- Produces: flag `--veta {respetar,libre}`, por omisión `None` (la del material).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_cli.py`:

```python
# --- la veta de la corrida -------------------------------------------------


def catalogo_angosto(tmp_path, tolerancia):
    """Una placa de 500 x 1500: una pieza de 1200 x 100 sólo entra parada."""
    path = tmp_path / "angosto.yaml"
    path.write_text(
        f"angosto:\n  placa: [500, 1500]\n  tolerancia_veta: {tolerancia}\n",
        encoding="utf-8",
    )
    return path


def pieza_acostada(tmp_path):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    doc.modelspace().add_lwpolyline(
        [(0, 0), (1200, 0), (1200, 100), (0, 100)], close=True
    )
    path = tmp_path / "acostada.dxf"
    doc.saveas(path)
    return path


def test_con_la_veta_del_material_la_pieza_acostada_no_entra(tmp_path, capsys):
    code = run([
        pieza_acostada(tmp_path), "--material", "angosto",
        "--materiales", catalogo_angosto(tmp_path, 5), "-o", tmp_path / "o.dxf",
        "--esfuerzo", "rapido", "--resolucion", "2",
    ])

    assert code == 1
    assert "no entra" in capsys.readouterr().err


def test_veta_libre_deja_pararla(tmp_path):
    code = run([
        pieza_acostada(tmp_path), "--material", "angosto",
        "--materiales", catalogo_angosto(tmp_path, 5), "-o", tmp_path / "o.dxf",
        "--esfuerzo", "rapido", "--resolucion", "2", "--veta", "libre",
    ])

    assert code == 0


def test_veta_respetar_la_bloquea_en_un_material_libre(tmp_path, capsys):
    code = run([
        pieza_acostada(tmp_path), "--material", "angosto",
        "--materiales", catalogo_angosto(tmp_path, 180), "-o", tmp_path / "o.dxf",
        "--esfuerzo", "rapido", "--resolucion", "2", "--veta", "respetar",
    ])

    assert code == 1
    assert "no entra" in capsys.readouterr().err


def test_un_angulo_que_la_veta_descarta_se_rechaza_nombrando_el_flag(tmp_path, capsys):
    code = run([
        pieza_acostada(tmp_path), "--material", "angosto",
        "--materiales", catalogo_angosto(tmp_path, 5), "-o", tmp_path / "o.dxf",
        "--angulos", "90",
    ])

    assert code == 1
    err = capsys.readouterr().err
    assert "--angulos tiene que ser compatible con la veta" in err


def test_una_veta_desconocida_es_error_de_uso(tmp_path):
    with pytest.raises(SystemExit) as salida:
        run([
            pieza_acostada(tmp_path), "--material", "angosto",
            "--materiales", catalogo_angosto(tmp_path, 5), "-o", tmp_path / "o.dxf",
            "--veta", "cruzada",
        ])

    assert salida.value.code == 1
```

En `tests/test_cli_full.py`, `test_the_help_lists_every_flag`, sumar `"--veta"` a la tupla de flags.

- [ ] **Step 2: Correrlos para verlos fallar**

Run: `.venv/bin/pytest tests/test_cli.py tests/test_cli_full.py -v -k "veta or help"`
Expected: FAIL: `test_veta_libre_deja_pararla` sale con código 1 (`unrecognized arguments: --veta`), y el help no lista `--veta`.

- [ ] **Step 3: Implementar**

En `src/nesting/cli.py`:

Cambiar el import de `nesting.params` a:

```python
from nesting.params import (
    NestParams,
    ParamsInvalidosError,
    a_config,
    a_supply,
    mensaje_cli,
    validar,
)
```

Borrar el import `from nesting.engine.oracle import NestConfig` y el de `from nesting.model.sheet import SheetSupply`, que quedan sin uso.

En `_parse_args`, después de `--sin-espejo`, agregar:

```python
    parser.add_argument("--veta", choices=("respetar", "libre"), default=None,
                        help="respetar la veta (sólo 0 y 180 grados) o no; "
                             "por omisión, la que diga el material")
```

En `main`, reemplazar el bloque que arma `config = NestConfig(...)` (justo después de parsear `angles`) por:

```python
    # Los mismos parámetros que la primera validación, ahora con los ángulos
    # ya parseados y la veta de la corrida: son los que de verdad se usan.
    params = NestParams(
        material=args.material,
        sep=args.sep,
        borde=args.borde,
        copias=args.copias,
        angulos=angles,
        espejo=not args.sin_espejo,
        unidades=args.unidades,
        tol_cierre=args.tol_cierre,
        resolucion=args.resolucion,
        esfuerzo=args.esfuerzo,
        veta=args.veta,
    )
    try:
        # Segunda pasada, con el material: la única regla que falta es la de
        # la veta, que sin catálogo no se puede mirar.
        validar(params, material)
    except ParamsInvalidosError as error:
        print(f"error: {mensaje_cli(error.rota)}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    config = a_config(params)
```

Y reemplazar la línea

```python
        supply = SheetSupply(stock=material.stock_sheet(), material_name=material.name)
```

por

```python
        # Por `a_supply` y no a mano: es el que sabe aplicar la veta de la
        # corrida. Armarlo acá con `material.stock_sheet()` era la segunda
        # copia de una regla que ahora tiene una sola.
        supply = a_supply(params, material)
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/pytest tests/test_cli.py tests/test_cli_full.py -v`
Expected: PASS.

- [ ] **Step 5: Correr la suite entera**

Run: `.venv/bin/pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/cli.py tests/test_cli.py tests/test_cli_full.py
git commit -m "CLI: --veta, y el plan de placas sale de a_supply"
```

---

### Task 4: La API recibe `veta` y valida con el material

**Files:**
- Modify: `src/nesting_app/api.py` (`ParamsEntrada`, `crear_trabajo`)
- Test: `tests/app/test_api_trabajos.py`

**Interfaces:**
- Consumes: `NestParams.veta`, `validar(p, material)`.
- Produces: `ParamsEntrada.veta: Literal["respetar", "libre"] | None = None`. `POST /api/trabajos` con ángulos que la veta deja vacíos devuelve 422 con `detail.campo == "angulos"`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/app/test_api_trabajos.py`:

```python
def test_la_veta_llega_al_params():
    from nesting_app.api import ParamsEntrada

    assert ParamsEntrada(material="mdf18", veta="respetar").a_params().veta == "respetar"


def test_sin_veta_el_params_la_deja_en_manos_del_material():
    from nesting_app.api import ParamsEntrada

    assert ParamsEntrada(material="mdf18").a_params().veta is None


def test_una_veta_desconocida_se_rechaza(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "veta": "cruzada"},
    })

    assert respuesta.status_code == 422


def test_angulos_que_la_veta_deja_vacios_se_rechazan_en_su_campo(cliente, tmp_path):
    """La pantalla ya lo bloquea con el cartel; esto es la red de abajo, para
    un pedido armado a mano o una pantalla vieja."""
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id,
        "params": {"material": "fenolico18", "angulos": [90.0]},
    })

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["campo"] == "angulos"


def test_con_la_veta_libre_el_mismo_pedido_arranca(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id,
        "params": {"material": "fenolico18", "angulos": [90.0], "veta": "libre"},
    })

    assert respuesta.status_code == 200
```

- [ ] **Step 2: Correrlos para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_api_trabajos.py -v -k "veta"`
Expected: FAIL: `ParamsEntrada` no tiene `veta` (pydantic lo ignora y `a_params().veta` da `AttributeError` o `None`), y el pedido con `[90.0]` en fenólico devuelve 200.

- [ ] **Step 3: Implementar**

En `src/nesting_app/api.py`:

En `ParamsEntrada`, después de `recortes: list[RecorteEntrada] = ...`, agregar:

```python
    veta: Literal["respetar", "libre"] | None = None
```

y en `a_params`, pasar `veta=self.veta,` al final del `NestParams(...)`.

En `crear_trabajo`, mover la validación después de leer el catálogo y pasarle el material. El cuerpo queda:

```python
        params = pedido.params.a_params()
        try:
            materiales = materials_store.leer()
        except ValueError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        material = materiales.get(params.material)

        try:
            # Con el material, si existe: es lo que deja mirar la regla de la
            # veta. Si no existe, se valida lo demás igual y el 404 sale
            # abajo, como antes -- un pedido con dos errores sigue
            # señalando primero el mismo.
            validar(params, material)
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

        if material is None:
            raise HTTPException(
                status_code=404,
                detail=f"no existe ningún material llamado {params.material!r}",
            )

        trabajo = registro.crear(fuente, params, corredor.acomodar)
        return {"id": trabajo.id}
```

`corredor.acomodar` ya arma el plan con `a_supply(params, material)`, así que la veta llega al motor sin tocarlo.

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/pytest tests/app -v`
Expected: PASS, incluidos `test_un_parametro_invalido_se_rechaza_nombrando_el_campo` y `test_un_material_que_no_existe_da_404`.

- [ ] **Step 5: Correr la suite entera**

Run: `.venv/bin/pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app/api.py tests/app/test_api_trabajos.py
git commit -m "API: la veta viaja con los parámetros y se valida contra el material"
```

---

### Task 5: El control Veta en la pantalla

El control existe, arranca con la veta del material, vuelve a ella al cambiar de material, viaja con los parámetros y manda sobre la casilla de veta cruzada. El bloqueo de Posiciones y el cartel son la Task 6.

**Files:**
- Modify: `src/nesting_app/web/index.html` (después del campo Material)
- Modify: `src/nesting_app/web/app.js` (`parametros`, `ajustarVetaCruzada`, handler de `material`, `refrescarMateriales`)
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: `vetaPorMaterial` (ya existe en `app.js`), `ParamsEntrada.veta` (Task 4).
- Produces (en `app.js`): `vetaDeLaCorrida() -> "respetar" | "libre"`, `ponerVeta(veta)`. En el HTML: radios `#veta-respetar` y `#veta-libre` con `name="veta-corrida"`, y botón de información `data-info="veta"`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/app/test_web_javascript.py`:

```python
# --- la veta de la corrida -------------------------------------------------


def test_el_control_de_veta_existe_con_sus_dos_opciones(html):
    assert 'id="veta-respetar"' in html
    assert 'id="veta-libre"' in html
    assert html.count('name="veta-corrida"') == 2


def test_el_control_de_veta_va_pegado_al_material(html):
    """Elegir material y decidir la veta son la misma decisión: el material
    trae su veta, y acá se la confirma o se la cambia."""
    material = html.index('id="material"')
    veta = html.index('id="veta-respetar"')
    recortes = html.index('id="btn-agregar-recorte"')
    assert material < veta < recortes


def test_la_veta_viaja_con_los_parametros(js):
    assert "veta: vetaDeLaCorrida()" in _cuerpo_de_funcion(js, "parametros")


def test_la_veta_de_la_corrida_se_lee_del_control(js):
    assert '$("veta-respetar").checked' in _cuerpo_de_funcion(js, "vetaDeLaCorrida")


def test_la_veta_cruzada_mira_el_control_y_no_el_material(js):
    """Con "no importa" elegido a mano sobre un fenólico, la casilla tampoco
    cambiaría nada: tiene que apagarse igual que en un MDF."""
    cuerpo = _cuerpo_de_funcion(js, "ajustarVetaCruzada")

    assert "vetaDeLaCorrida()" in cuerpo
    assert "vetaPorMaterial" not in cuerpo


def test_poner_la_veta_marca_el_radio_y_ajusta_la_cruzada(js):
    cuerpo = _cuerpo_de_funcion(js, "ponerVeta")

    assert '"veta-respetar"' in cuerpo and '"veta-libre"' in cuerpo
    assert ".checked = true" in cuerpo
    assert "ajustarVetaCruzada()" in cuerpo


def test_refrescar_el_catalogo_pone_la_veta_del_material(js):
    """Refrescar pasa al arrancar y después de editar el catálogo: en los
    dos casos el control tiene que decir lo que dice el material, sin
    preguntar nada."""
    cuerpo = _cuerpo_de_funcion(js, "refrescarMateriales")

    assert "ponerVeta(" in cuerpo
    assert "pedirVeta(" not in cuerpo
```

- [ ] **Step 2: Correrlos para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -v -k "veta"`
Expected: FAIL: no existe `id="veta-respetar"`, y `_cuerpo_de_funcion` corta con `pytest.fail` porque no encuentra `vetaDeLaCorrida` ni `ponerVeta`.

- [ ] **Step 3: El HTML**

En `src/nesting_app/web/index.html`, inmediatamente después del `</div>` que cierra el `.campo` de Material (el que contiene `<select id="material">`) y antes del comentario "Pegado a Material y no al final del panel", agregar:

```html
    <!-- Debajo de Material y no con las opciones de giro: el material trae
         su veta y acá se la confirma o se la cambia para esta corrida, sin
         tocar el catálogo. Cambiar de material la vuelve a la suya. -->
    <div class="campo" role="radiogroup" aria-labelledby="etiqueta-veta">
      <div class="titulo-campo">
        <span id="etiqueta-veta" class="etiqueta">Veta</span>
        <button type="button" class="boton-info" data-info="veta" aria-label="Qué es Veta" aria-expanded="false"><svg viewBox="0 0 16 16" class="icono" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="6.25"></circle><path d="M8 7.5v3.5"></path><path d="M8 5v.01"></path></svg></button>
      </div>
      <label class="opcion">
        <input type="radio" name="veta-corrida" id="veta-respetar" value="respetar">
        <span><strong>Respetar</strong><small>Sólo 0° y 180°.</small></span>
      </label>
      <label class="opcion">
        <input type="radio" name="veta-corrida" id="veta-libre" value="libre" checked>
        <span><strong>No importa</strong><small>La pieza gira libre.</small></span>
      </label>
    </div>
```

Un `div` con `role="radiogroup"` y no un `fieldset`: el título del campo lleva al lado el botón de información, igual que los demás, y un `<legend>` tiene que ser el primer hijo directo del `fieldset`, así que no puede ir adentro de `.titulo-campo`.

- [ ] **Step 4: El JavaScript**

En `src/nesting_app/web/app.js`:

En `parametros()`, agregar como última propiedad:

```js
    veta: vetaDeLaCorrida(),
```

Reemplazar `ajustarVetaCruzada` y la línea `$("material").addEventListener("change", ajustarVetaCruzada);` por:

```js
function vetaDeLaCorrida() {
  return $("veta-respetar").checked ? "respetar" : "libre";
}

// Mira el control y no el material: con "no importa" elegido a mano sobre
// un fenólico, la casilla tampoco cambiaría nada.
function ajustarVetaCruzada() {
  const libre = vetaDeLaCorrida() === "libre";
  $("r-cruzada").disabled = libre;
  if (libre) $("r-cruzada").checked = false;
  $("etiqueta-cruzada").classList.toggle("deshabilitada", libre);
}

// Deja el control en `veta` y todo lo que depende de él al día. No
// pregunta nada: quien tiene que preguntar antes es `pedirVeta`.
function ponerVeta(veta) {
  $(veta === "respetar" ? "veta-respetar" : "veta-libre").checked = true;
  ajustarVetaCruzada();
}

$("material").addEventListener("change", () =>
  ponerVeta(vetaPorMaterial[$("material").value])
);
["veta-respetar", "veta-libre"].forEach((id) =>
  $(id).addEventListener("change", () => ponerVeta(vetaDeLaCorrida()))
);
```

(En la Task 6 estos dos handlers pasan a llamar a `pedirVeta`, que es la que puede mostrar el cartel.)

En `refrescarMateriales`, reemplazar la llamada `ajustarVetaCruzada();` por:

```js
  // Sin preguntar: refrescar pasa al arrancar y después de editar el
  // catálogo, y en los dos casos el control tiene que decir lo que dice el
  // material. El cartel es para cuando el usuario cambia algo a mano.
  ponerVeta(vetaPorMaterial[select.value] ?? "libre");
```

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/pytest tests/app -v`
Expected: PASS, incluidos `test_todo_id_que_busca_el_js_existe_en_el_html` y `test_la_casilla_de_veta_cruzada_se_apaga_en_un_material_sin_veta` (su cuerpo sigue teniendo `=== "libre"` y `$("r-cruzada").disabled`).

Los tests de los globos (`CLAVES_CON_GLOBO`) van a fallar porque el HTML tiene un `data-info="veta"` sin texto en `info.js`. Es esperado: lo cierra la Task 7. Si se prefiere cerrar la tarea en verde, agregar ya la clave a `info.js` con el texto de la Task 7, Step 3, y la clave a `CLAVES_CON_GLOBO`, y moverlo de la Task 7.

- [ ] **Step 6: Probarlo en la ventana**

Run: `.venv/bin/nest-app`

Elegir `mdf15`: el control dice "No importa". Elegir `multilam18`: dice "Respetar", y la casilla "Veta cruzada" del alta de recortes se habilita. Marcar "No importa" a mano: la casilla se apaga. Volver a elegir `multilam18`: el control vuelve a "Respetar".

- [ ] **Step 7: Commit**

```bash
git add src/nesting_app/web/index.html src/nesting_app/web/app.js tests/app/test_web_javascript.py
git commit -m "Pantalla: la veta se ve debajo del material y se cambia por corrida"
```

---

### Task 6: Posiciones obedece a la veta, con cartel en el conflicto

**Files:**
- Modify: `src/nesting_app/web/index.html` (desplegable de Posiciones, nota, cartel)
- Modify: `src/nesting_app/web/app.js`
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: `vetaDeLaCorrida`, `ponerVeta`, `ajustarVetaCruzada` (Task 5); `angulosElegidos`, `angulosValidos` (ya existen).
- Produces (en `app.js`): `TOLERANCIA_VETA = 5`, `respetaLaVeta(angulo) -> bool`, `bloquearPosiciones()`, `soltarPosiciones()`, `pedirVeta(veta, origen)` con `origen` en `"material" | "control"`, `mostrarCartelVeta(cuantas, origen)`. En el HTML: `<option value="veta" hidden>` en `#posiciones`, `#nota-veta`, `#cartel-veta`, `#titulo-veta`, `#texto-veta`, `#btn-veta-respetar`, `#btn-veta-libre`.

Nota sobre los tres caminos del spec (2.3): con la veta respetada, Posiciones queda deshabilitado y el campo Ángulos oculto, así que tipear ángulos personalizados que choquen con la veta no puede pasar. El conflicto sólo aparece al elegir un material con veta o al marcar "Respetar"; esos dos caminos son los que pasan por `pedirVeta`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/app/test_web_javascript.py`:

```python
def test_posiciones_tiene_la_opcion_bloqueada_de_la_veta(html):
    """Oculta: no se elige de la lista, la pone la veta. Y con el grado
    escrito como símbolo, igual que las demás."""
    opciones = _opciones_de_posiciones(html)
    assert re.search(r'<option value="veta" hidden>2 — 0° y 180°</option>', opciones)


def test_la_veta_tiene_su_nota_debajo_de_posiciones(html):
    posiciones = html.index('id="posiciones"')
    nota = html.index('id="nota-veta"')
    angulos = html.index('id="campo-angulos"')
    assert posiciones < nota < angulos


def test_con_la_opcion_de_la_veta_los_angulos_son_cero_y_ciento_ochenta(js):
    cuerpo = _cuerpo_de_funcion(js, "angulosElegidos")
    assert re.search(r'=== "veta"\)\s*return \[0, 180\]', cuerpo)


def test_la_tolerancia_de_la_pantalla_es_la_del_modelo(js):
    from nesting.model.material import VETA_RESPETAR

    assert f"const TOLERANCIA_VETA = {VETA_RESPETAR:g};" in js


def test_un_angulo_respeta_la_veta_si_cae_cerca_del_eje(js):
    cuerpo = _cuerpo_de_funcion(js, "respetaLaVeta")
    assert "% 180" in cuerpo
    assert "TOLERANCIA_VETA" in cuerpo


def test_bloquear_recuerda_lo_que_habia(js):
    cuerpo = _cuerpo_de_funcion(js, "bloquearPosiciones")

    assert "posicionesAntesDeVeta === null" in cuerpo
    assert 'value = "veta"' in cuerpo
    assert "disabled = true" in cuerpo
    assert '"campo-angulos"' in cuerpo
    assert '"nota-veta"' in cuerpo


def test_soltar_devuelve_lo_que_habia(js):
    cuerpo = _cuerpo_de_funcion(js, "soltarPosiciones")

    assert "value = posicionesAntesDeVeta" in cuerpo
    assert "posicionesAntesDeVeta = null" in cuerpo
    assert "disabled = false" in cuerpo
    assert '"personalizado"' in cuerpo


def test_poner_la_veta_bloquea_o_suelta(js):
    cuerpo = _cuerpo_de_funcion(js, "ponerVeta")
    assert "bloquearPosiciones()" in cuerpo
    assert "soltarPosiciones()" in cuerpo


def test_pedir_la_veta_muestra_el_cartel_solo_si_hay_conflicto(js):
    cuerpo = _cuerpo_de_funcion(js, "pedirVeta")

    assert 'veta === "respetar"' in cuerpo
    assert "respetaLaVeta" in cuerpo
    assert "mostrarCartelVeta(" in cuerpo
    assert "ponerVeta(veta)" in cuerpo


def test_el_cartel_dice_cuantas_posiciones_habia(js):
    cuerpo = _cuerpo_de_funcion(js, "mostrarCartelVeta")

    assert "Sólo se puede girar a 0° y 180°." in cuerpo
    assert "${cuantas} posiciones" in cuerpo
    assert "Este material respeta la veta" in cuerpo
    assert '"cartel-veta"' in cuerpo


def test_el_cartel_tiene_sus_dos_salidas_y_ninguna_es_cancelar(html):
    desde = html.index('id="cartel-veta"')
    cartel = html[desde:html.index("</div>\n</div>", desde)]

    assert 'id="btn-veta-respetar"' in cartel and "Usar 0° y 180°" in cartel
    assert 'id="btn-veta-libre"' in cartel and "No me importa la veta" in cartel
    assert "Cancelar" not in cartel


def test_los_botones_del_cartel_ponen_la_veta_que_dicen(js):
    limpio = _sin_comentarios(js)
    assert re.search(
        r'\$\("btn-veta-respetar"\)\.onclick = \(\) => \{[^}]*ponerVeta\("respetar"\)', limpio
    )
    assert re.search(
        r'\$\("btn-veta-libre"\)\.onclick = \(\) => \{[^}]*ponerVeta\("libre"\)', limpio
    )


def test_cambiar_material_o_la_veta_a_mano_pasa_por_pedir(js):
    limpio = _sin_comentarios(js)
    assert re.search(r'pedirVeta\(vetaPorMaterial\[\$\("material"\)\.value\], "material"\)', limpio)
    assert re.search(r'pedirVeta\(vetaDeLaCorrida\(\), "control"\)', limpio)
```

- [ ] **Step 2: Correrlos para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -v -k "veta or posiciones or cartel"`
Expected: FAIL: faltan la opción `veta`, `#nota-veta`, `#cartel-veta` y las funciones nuevas.

- [ ] **Step 3: El HTML**

En `src/nesting_app/web/index.html`, dentro de `<select id="posiciones" class="control">`, después de `<option value="personalizado">Personalizado</option>`, agregar:

```html
          <option value="veta" hidden>2 — 0° y 180°</option>
```

Después del `</div>` que cierra el `.desplegable` de Posiciones (dentro del mismo `.campo`), agregar:

```html
      <p id="nota-veta" class="resumen oculto">Con la veta respetada, sólo se gira a 0° y 180°.</p>
```

Después del `<div id="cartel-unidades" ...>...</div>` completo, agregar:

```html
<!-- Dos salidas y ninguna es "cancelar": no hay un estado neutro al que
     volver. O se respeta la veta y se gira a 0 y 180, o no se la respeta y
     quedan las posiciones que había. -->
<div id="cartel-veta" class="cartel oculto">
  <div class="cartel-caja">
    <h2 id="titulo-veta">Este material respeta la veta</h2>
    <p id="texto-veta"></p>
    <div class="fila">
      <span class="espaciador"></span>
      <button type="button" id="btn-veta-libre" class="boton secundario">No me importa la veta</button>
      <button type="button" id="btn-veta-respetar" class="boton primario">Usar 0° y 180°</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: El JavaScript**

En `src/nesting_app/web/app.js`:

En `angulosElegidos`, agregar como primera línea después de `const posiciones = $("posiciones").value;`:

```js
  if (posiciones === "veta") return [0, 180];
```

Reemplazar el bloque de la Task 5 (desde `function ponerVeta` hasta el `forEach` de los dos radios, inclusive) por:

```js
// El mismo número que `VETA_RESPETAR` en nesting/model/material.py. Está
// repetido para no preguntarle al servidor algo que no cambia; un test
// compara los dos.
const TOLERANCIA_VETA = 5;

// Lo que había en Posiciones antes de bloquearlo, para devolverlo al
// soltar. `null` mientras no está bloqueado.
let posicionesAntesDeVeta = null;

function respetaLaVeta(angulo) {
  const plegado = ((angulo % 180) + 180) % 180;
  return Math.min(plegado, 180 - plegado) <= TOLERANCIA_VETA + 1e-9;
}

function bloquearPosiciones() {
  if (posicionesAntesDeVeta === null) posicionesAntesDeVeta = $("posiciones").value;
  $("posiciones").value = "veta";
  $("posiciones").disabled = true;
  $("campo-angulos").classList.add("oculto");
  $("nota-veta").classList.remove("oculto");
}

function soltarPosiciones() {
  if (posicionesAntesDeVeta !== null) $("posiciones").value = posicionesAntesDeVeta;
  posicionesAntesDeVeta = null;
  $("posiciones").disabled = false;
  $("campo-angulos").classList.toggle("oculto", $("posiciones").value !== "personalizado");
  $("nota-veta").classList.add("oculto");
}

// Deja el control en `veta` y todo lo que depende de él al día. No
// pregunta nada: quien tiene que preguntar antes es `pedirVeta`.
function ponerVeta(veta) {
  $(veta === "respetar" ? "veta-respetar" : "veta-libre").checked = true;
  if (veta === "respetar") bloquearPosiciones();
  else soltarPosiciones();
  ajustarVetaCruzada();
}

// Lo que pasa cuando el USUARIO cambia algo: elige un material o marca un
// radio. Si pasar a "respetar" descartaría ángulos que eligió, se lo dice
// en ese momento y no al tocar Acomodar, después de haber cargado todo.
// Ya bloqueado (`posicionesAntesDeVeta !== null`) no hay nada que
// descartar. Con ángulos inválidos tampoco se pregunta: se bloquea, y el
// texto queda guardado para cuando se suelte.
function pedirVeta(veta, origen) {
  if (veta === "respetar" && posicionesAntesDeVeta === null && angulosValidos()) {
    const angulos = angulosElegidos();
    if (angulos.some((a) => !respetaLaVeta(a))) {
      mostrarCartelVeta(angulos.length, origen);
      return;
    }
  }
  ponerVeta(veta);
}

function mostrarCartelVeta(cuantas, origen) {
  $("titulo-veta").textContent = origen === "material"
    ? "Este material respeta la veta"
    : "Respetar la veta limita los giros";
  $("texto-veta").textContent =
    `Sólo se puede girar a 0° y 180°. Tenías elegidas ${cuantas} posiciones.`;
  $("cartel-veta").classList.remove("oculto");
}

$("btn-veta-respetar").onclick = () => {
  $("cartel-veta").classList.add("oculto");
  ponerVeta("respetar");
};
$("btn-veta-libre").onclick = () => {
  $("cartel-veta").classList.add("oculto");
  ponerVeta("libre");
};

$("material").addEventListener("change", () =>
  pedirVeta(vetaPorMaterial[$("material").value], "material")
);
["veta-respetar", "veta-libre"].forEach((id) =>
  $(id).addEventListener("change", () => pedirVeta(vetaDeLaCorrida(), "control"))
);
```

(`angulosElegidos` y `angulosValidos` están declaradas más abajo en el archivo, en la sección de acomodar; como son `function`, se pueden llamar desde acá.)

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/pytest tests/app -v`
Expected: PASS, incluidos `test_todo_id_que_busca_el_js_existe_en_el_html`, `test_cada_grado_del_desplegable_lleva_su_simbolo` y `test_el_desplegable_de_posiciones_tiene_sus_opciones`.

- [ ] **Step 6: Probarlo en la ventana**

Run: `.venv/bin/nest-app`

Recorrer estos casos y confirmar cada uno:

1. `mdf15`, Posiciones en 8. Elegir `multilam18`: sale el cartel "Este material respeta la veta · … Tenías elegidas 8 posiciones."
2. "Usar 0° y 180°": Posiciones muestra "2 — 0° y 180°" deshabilitado, con la nota debajo; la veta dice "Respetar".
3. Marcar "No importa": Posiciones vuelve a 8, habilitado, sin nota.
4. Marcar "Respetar" a mano con 8 elegidas: sale el cartel con el título "Respetar la veta limita los giros". "No me importa la veta": el control queda en "No importa" y Posiciones sigue en 8.
5. Personalizado con `0,180`, elegir `multilam18`: no sale cartel; bloquea directo. Volver a "No importa": Personalizado vuelve con `0,180` en el campo.
6. Con la veta respetada, acomodar un archivo: el trabajo arranca y el resultado sólo usa 0° y 180°.

- [ ] **Step 7: Commit**

```bash
git add src/nesting_app/web/index.html src/nesting_app/web/app.js tests/app/test_web_javascript.py
git commit -m "Pantalla: con la veta respetada, Posiciones se bloquea y avisa el conflicto"
```

---

### Task 7: Los textos: globo de Veta, globo de Ángulos y README

**Files:**
- Modify: `src/nesting_app/web/info.js` (`TEXTOS`)
- Modify: `tests/app/test_web_javascript.py` (`CLAVES_CON_GLOBO`)
- Modify: `README.md`, `README.es.md` (tabla de opciones)

**Interfaces:**
- Consumes: el `data-info="veta"` de la Task 5.
- Produces: la clave `"veta"` en `TEXTOS`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/app/test_web_javascript.py`, sumar `"veta"` a `CLAVES_CON_GLOBO`:

```python
CLAVES_CON_GLOBO = [
    "archivo", "material", "veta", "sep", "borde", "copias", "esfuerzo",
    "angulos", "posiciones", "tol-cierre", "resolucion", "espejo", "recortes",
]
```

Y agregar al final del archivo:

```python
def test_el_globo_de_angulos_ya_no_explica_la_veta(js_info):
    """Ahora la pantalla lo muestra: Posiciones se bloquea y dice por qué.
    Explicarlo además en el globo es contar dos veces lo mismo."""
    assert "veta" not in claves_y_textos(js_info)["angulos"]


def test_el_globo_de_veta_dice_que_es_de_esta_corrida(js_info):
    texto = claves_y_textos(js_info)["veta"]
    assert "catálogo" in texto
    assert "0° y 180°" in texto
```

- [ ] **Step 2: Correrlos para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -v -k "globo or info or claves"`
Expected: FAIL: falta la clave `veta` en `TEXTOS`, y el de `angulos` todavía nombra la veta.

(Si en la Task 5 ya se agregó la clave, sólo falla `test_el_globo_de_angulos_ya_no_explica_la_veta`.)

- [ ] **Step 3: Los textos**

En `src/nesting_app/web/info.js`, dentro de `TEXTOS`, después de la línea de `"material"`, agregar:

```js
  "veta": "Si hay que respetar la dirección de la veta de la placa. Arranca con lo que dice el material y se puede cambiar para esta corrida sin tocar el catálogo. Respetarla deja girar las piezas sólo a 0° y 180°.",
```

Y en la línea de `"angulos"`, borrar la última oración (`Si el material respeta la veta, sólo se usan 0° y 180°.`), dejando:

```js
  "angulos": "Las rotaciones que puede probar en cada pieza, separadas por comas. Menos ángulos es más rápido; sumar 45° suele ganar lugar en piezas largas.",
```

- [ ] **Step 4: README**

En `README.es.md`, en la tabla de "Opciones", agregar después de la fila de Material:

```markdown
| Veta | `--veta` | `respetar` (sólo 0° y 180°) o `libre`. Arranca con la del material y se cambia para esta corrida sin tocar el catálogo. Con la veta respetada, Posiciones queda fija en 0° y 180°. |
```

En `README.md`, en la tabla de "Options", la misma fila después de Material:

```markdown
| Veta | `--veta` | `respetar` (only 0° and 180°) or `libre`. Starts from the material's and can be changed for this run without touching the catalogue. With the grain respected, Posiciones is locked at 0° and 180°. |
```

En los dos README, en la fila de Ángulos, borrar la mención a la veta si la hay, y en la fila de Posiciones agregar al final: "Con la veta respetada queda fija en 0° y 180°." / "With the grain respected it is locked at 0° and 180°."

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/pytest tests/app -v`
Expected: PASS.

- [ ] **Step 6: Correr la suite entera**

Run: `.venv/bin/pytest`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/nesting_app/web/info.js tests/app/test_web_javascript.py README.md README.es.md
git commit -m "Textos: el globo de la veta, y el de ángulos deja de explicarla"
```

---

## Verificación final

- [ ] `.venv/bin/pytest` entero en verde.
- [ ] La corrida de la banqueta con la veta respetada sigue dando lo mismo que antes del plan (2 placas), y con `--veta libre` usa las 8 posiciones:

```bash
.venv/bin/nest bench/files/banqueta-alta.ai --material multilam18 --sep 8 --borde 5 --angulos 0,45,90,135,180,225,270,315 --esfuerzo rapido -o /tmp/veta-libre.dxf --veta libre
```

Expected: termina con código 0. El resultado todavía puede dar 2 placas: eso lo resuelve el plan de pares y cartera, no este. Lo que se verifica acá es que el DXF tenga piezas a 45°/90°, cosa que con la veta del material no podía pasar.
