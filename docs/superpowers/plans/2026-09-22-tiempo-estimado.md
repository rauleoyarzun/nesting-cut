# Tiempo estimado, antes y durante el acomodo — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la pantalla diga cuánto falta mientras corre un acomodo ("Faltan aprox. 9 min · termina ~17:42") y cuánto va a tardar antes de arrancarlo ("Tarda aprox. 10 min" al lado de Acomodar).

**Architecture:** La unidad de trabajo pasa a ser la **consulta** (`Oracle.best_placement`). `pack` envuelve la fábrica de oráculos en un contador, así que ninguna fase se escapa de la cuenta, y cada `Avance` lleva `consultas_hechas` y `consultas_previstas`. La previsión es aritmética pura sobre conteos (`nesting/engine/prevision.py`) que el packer corrige por fases. El servidor (`nesting_app/jobs.py`) convierte consultas y reloj en segundos restantes; la ruta nueva `POST /api/estimar` mide una consulta real y la multiplica por la previsión y por `FACTOR_LLENO`. La pantalla redondea, estabiliza y muestra.

**Tech Stack:** Python 3.13, pytest. Interfaz en HTML/CSS/JavaScript a mano, sin framework; sus tests leen los archivos estáticos como texto y no corren navegador. Los casos de tabla del JavaScript corren las funciones con `node` si está en el PATH, y se saltean con motivo si no.

**Spec:** `docs/superpowers/specs/2026-09-22-tiempo-estimado-design.es.md`

**Depende de:** el plan de veta por corrida (spec `2026-09-22-veta-por-corrida-design.es.md`), que se ejecuta ANTES que éste. De él se usan, con estos nombres exactos: `nesting.model.material.VETA_LIBRE = 180.0` y `VETA_RESPETAR = 5.0`; `NestParams.veta`; `nesting.params.validar(p: NestParams, material: Material | None = None)`; `a_supply(p, material)` aplicando la veta de la corrida; `ParamsEntrada.veta` en `api.py`; y los radios `veta-respetar` / `veta-libre` (`name="veta-corrida"`) en `index.html`. Antes de la Tarea 1, verificar que están:

```bash
grep -n "VETA_LIBRE\|VETA_RESPETAR" src/nesting/model/material.py
grep -n "def validar\|def tolerancia_de_veta" src/nesting/params.py
grep -n 'id="veta-respetar"\|id="veta-libre"' src/nesting_app/web/index.html
```

Si alguno no aparece, parar y avisar: este plan no se puede ejecutar antes que aquél.

**Lo que viene después:** el plan de pares y cartera corre variantes en procesos paralelos y va a sumar `consultas_hechas` / `consultas_previstas` entre procesos, usando las funciones puras de `nesting/engine/prevision.py` por variante. Por eso esas funciones reciben conteos y no objetos del motor, y los dos campos de `Avance` se llaman exactamente `consultas_hechas: int` y `consultas_previstas: int`, con `0` por omisión.

## Global Constraints

- **TDD sin excepciones:** test que falla, correrlo para verlo fallar, implementación mínima, test que pasa, commit. Un paso por vez.
- **Todo texto de cara al usuario va en español**, con tildes y eñes.
- **Idioma del código:** los identificadores van en inglés en `src/nesting/engine/`, `model/`, `io/` y `geometry/`, y en español en `params.py` y en todo `src/nesting_app/`. Los **docstrings y comentarios** son mixtos en todo el repo y no hay una regla que seguir: `model/entities.py` y `model/part.py` están en inglés, `model/discard.py` entero en español, `model/material.py` mezclado. Escribir el docstring en el idioma en que se piensa mejor la explicación es lo que viene haciendo el repo. **No es un hallazgo de revisión** que un docstring esté en un idioma u otro. Excepción ya existente que este plan respeta: `Avance`, `Cancelado` y sus campos están en español dentro de `packer.py`, y los dos campos nuevos (`consultas_hechas`, `consultas_previstas`) los fija la spec con ese nombre.
- **Nada de emojis.** El test `test_no_hay_emojis_en_la_interfaz` ya lo prohíbe y no se relaja. El `…` (U+2026), el `·` (U+00B7) y el `~` que usan los textos nuevos no son emojis; ya hay `…` en "Compactando la última placa…".
- **Ningún token de color nuevo en `app.css`.** Se usan los que ya están: `--panel`, `--borde`, `--radio`, `--sombra`, `--texto`, `--texto-2`. Este plan no necesita tocar `app.css`: los dos textos nuevos usan la clase `texto-avance` que ya existe.
- **La CLI no gana ninguna bandera.** La estimación en la CLI está fuera de alcance (spec, 1). Si un paso te pide agregar un flag a `nesting/cli.py`, el paso está mal: pará y avisá. (`bench/calibrate.py` no es la CLI y sí gana opciones en la Tarea 6.)
- **Sin callback, nada cambia.** `pack` sin `progreso` -- lo que hace la CLI -- tiene que dar exactamente el mismo layout que antes del plan. Contar consultas observa al motor; no puede cambiar qué coloca. `tests/engine/test_progreso.py::test_sin_callback_pack_se_comporta_igual_que_siempre` lo fija y no se toca.
- **`bench/files/` no está versionado.** Todo test que dependa de `bench/files/banqueta-alta.ai` (o de cualquier otro archivo de ahí) se saltea con `pytest.skip` y un motivo que nombra el archivo y dónde ponerlo. Lo sintético (`bench/make_sample.py::write_sample`) se genera en `tmp_path` y no se saltea nunca.
- **Los tests de JavaScript miran cuerpos, no el archivo entero.** `tests/app/test_web_javascript.py` ya tiene `_cuerpo_de_funcion(js, "nombre")` y `_cuerpo_de_handler(js, "evento")`, que además borran los comentarios antes de mirar. Usarlos. Una aserción sobre el archivo entero (`assert "360" in js`) pasa por cualquier `360` perdido en un comentario, y hubo un test en un plan anterior que pasaba ANTES de implementar nada porque afirmaba `"disabled" in js`, una cadena que ya estaba en el botón de guardar. Los casos de tabla (redondeo, estabilidad, hora de fin) además **corren** las funciones con `node`, armando el programa con esos mismos cuerpos; sin `node` en el PATH se saltean con motivo, y los tests de texto siguen corriendo.
- **Correr la suite entera** (`.venv/bin/pytest`) al cerrar cada tarea, no sólo los tests nuevos. La Tarea 2 cambia cuándo se llama `aviso` y toca a todos los tests de avance.
- **Nada de `Co-Authored-By` ni atribución en los mensajes de commit.**

## Mapa de archivos

| Archivo | Responsabilidad | Tarea |
|---|---|---|
| `src/nesting/engine/prevision.py` | **Nuevo.** Aritmética pura: cuántas placas, cuántas consultas por pasada golosa, por recuperación y por compactación. Recibe conteos, no piezas. | 1 |
| `src/nesting/engine/packer.py` | `Avance` gana las consultas; el contador envuelve la fábrica; `aviso` por pieza intentada; la compactación avisa y se cancela; la previsión se corrige por fase; `initial_forecast` y `probe_query_seconds`. | 2, 3, 5 |
| `src/nesting_app/jobs.py` | `EstimadorDeRestante`, `Trabajo.restante_s`, `Registro(reloj=...)`. | 4 |
| `src/nesting_app/api.py` | Las consultas y `restante_s` en el estado del trabajo; ruta `POST /api/estimar`. | 4, 5 |
| `src/nesting_app/corredor.py` | `FACTOR_LLENO`, `estimar_segundos`, `estimar`. | 5, 6 |
| `bench/calibrate.py` | `measure_fill_factor` y el modo `--factor-lleno`. | 6 |
| `src/nesting_app/web/index.html` | `texto-restante` en la barra de abajo; `tiempo-estimado` al lado de Acomodar. | 7, 8 |
| `src/nesting_app/web/app.js` | Redondeo, estabilidad, hora de fin, pedido demorado a `/api/estimar`. | 7, 8 |
| `tests/engine/test_prevision.py` | **Nuevo.** Las funciones puras. | 1 |
| `tests/engine/test_consultas.py` | **Nuevo.** Conteo, previsión por fases, precisión sobre el bench, prueba de una consulta. | 2, 3, 5 |
| `tests/engine/test_progreso.py` | Una frase de un docstring que deja de ser cierta. | 2 |
| `tests/app/test_jobs.py`, `tests/app/test_api_trabajos.py`, `tests/app/test_corredor.py` | Estimador, API, estimación previa. | 4, 5 |
| `tests/test_calibration.py` | Medición del factor y la cota de ×2. | 6 |
| `tests/app/test_web_javascript.py` | Textos y casos de tabla del JavaScript. | 7, 8 |

---

### Task 1: La previsión, como aritmética pura

Módulo nuevo, sin tocar el motor. Al terminar, la suite pasa igual: nadie lo
usa todavía.

**Files:**
- Create: `src/nesting/engine/prevision.py`
- Test: `tests/engine/test_prevision.py` (nuevo)

**Interfaces:**
- Consumes: nada.
- Produces (todo en `nesting.engine.prevision`):
  - `TYPICAL_UTILIZATION: float = 0.4`
  - `estimate_sheets(parts_area: float, scrap_usable_areas: Sequence[float], stock_usable_area: float) -> int`
  - `forecast_greedy_pass(parts: int, orientations: int, sheets: int) -> int`
  - `forecast_recovery(previous_sheets: Sequence[tuple[int, int]], on_last: int) -> int` — cada tupla es `(piezas en esa placa, orientaciones de esa placa)`.
  - `forecast_compaction(on_last: int, orientations: int) -> int`
  - `forecast_pack(parts: int, orientations: int, sheets: int, passes: int) -> int`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/engine/test_prevision.py`:

```python
"""Cuántas consultas va a costar un acomodo: la aritmética, sin motor."""

import pytest

from nesting.engine.prevision import (
    TYPICAL_UTILIZATION,
    estimate_sheets,
    forecast_compaction,
    forecast_greedy_pass,
    forecast_pack,
    forecast_recovery,
)

UTIL = 1_000_000.0
"""Área útil de una placa de 1000 x 1000 sin margen."""


def test_el_aprovechamiento_tipico_es_el_de_la_spec():
    assert TYPICAL_UTILIZATION == 0.4


def test_lo_que_entra_en_el_aprovechamiento_tipico_es_una_placa():
    assert estimate_sheets(300_000.0, (), UTIL) == 1


def test_pasarse_del_aprovechamiento_tipico_abre_otra_placa():
    assert estimate_sheets(500_000.0, (), UTIL) == 2


def test_sin_piezas_igual_se_prevé_una_placa():
    """`forecast_greedy_pass` divide por la cantidad de placas: cero no
    puede salir nunca de acá."""
    assert estimate_sheets(0.0, (), UTIL) == 1


def test_los_recortes_cuentan_como_placas_antes_que_la_del_material():
    # El recorte de 500x500 útil absorbe 0.25e6 * 0.4 = 0.1e6; quedan
    # 0.35e6, que en placas del material son una más.
    assert estimate_sheets(450_000.0, (250_000.0,), UTIL) == 2


def test_un_recorte_que_alcanza_no_abre_placa_del_material():
    assert estimate_sheets(50_000.0, (250_000.0, 250_000.0), UTIL) == 1


def test_un_recorte_sin_area_util_no_resta_nada():
    """Un margen más grande que el recorte deja área útil negativa. Restarla
    haría que el recorte AGREGARA trabajo pendiente."""
    assert estimate_sheets(300_000.0, (-10_000.0,), UTIL) == 2


def test_una_placa_del_material_sin_area_util_no_divide_por_cero():
    assert estimate_sheets(300_000.0, (), 0.0) == 1


def test_una_placa_es_piezas_por_orientaciones():
    assert forecast_greedy_pass(10, 4, 1) == 40


def test_las_pendientes_se_vuelven_a_consultar_en_la_placa_siguiente():
    # Placa 1: las 10. Placa 2: la mitad que se estima que quedó.
    assert forecast_greedy_pass(10, 4, 2) == (10 + 5) * 4


def test_las_pendientes_se_redondean_para_arriba():
    # 10, ceil(20/3) = 7, ceil(10/3) = 4.
    assert forecast_greedy_pass(10, 4, 3) == (10 + 7 + 4) * 4


def test_sin_placas_anteriores_la_recuperacion_no_consulta():
    assert forecast_recovery([], 5) == 0


def test_la_recuperacion_paga_un_reempaque_y_un_derrame_por_placa_anterior():
    """Cada intento es un `_pack_once` con la placa anterior y las
    pendientes adelante: todas se consultan en la placa, y las que no
    entran se vuelven a consultar en la placa de derrame."""
    assert forecast_recovery([(6, 4)], 3) == (6 + 3) * 4 + 3 * 4


def test_la_recuperacion_usa_las_orientaciones_de_cada_placa():
    """Un recorte con la veta cruzada puede permitir otras orientaciones que
    la placa del material."""
    assert forecast_recovery([(6, 4), (2, 8)], 1) == (7 * 4 + 4) + (3 * 8 + 8)


def test_compactar_una_sola_pieza_no_consulta():
    """`_compact_last_sheet` sale antes con menos de dos piezas."""
    assert forecast_compaction(1, 4) == 0
    assert forecast_compaction(0, 4) == 0


def test_compactar_es_una_pasada_sobre_la_ultima_placa():
    assert forecast_compaction(3, 4) == 12


def test_la_prevision_de_arranque_suma_las_tres_fases():
    # Por pasada: (10 + 5) * 4 = 60, por 3 intentos = 180.
    # Recuperación: una placa anterior con 5, 5 en la última: (5+5)*4 + 5*4 = 60.
    # Compactación: 5 * 4 = 20.
    assert forecast_pack(10, 4, 2, 3) == 180 + 60 + 20


def test_una_placa_no_tiene_recuperacion():
    assert forecast_pack(10, 8, 1, 3) == 3 * 80 + 0 + 80


@pytest.mark.parametrize("sheets", [0, -1])
def test_la_prevision_de_arranque_no_divide_por_cero(sheets):
    assert forecast_pack(10, 4, sheets, 1) == forecast_pack(10, 4, 1, 1)
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_prevision.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting.engine.prevision'`

- [ ] **Step 3: Escribir `src/nesting/engine/prevision.py`**

```python
"""Cuántas consultas al oráculo va a costar un acomodo, antes de hacerlo.

Una consulta es una llamada a `Oracle.best_placement(part, angle, mirror)`.
Casi todo el tiempo de `pack` se va en eso, y cada consulta cuesta del mismo
orden sobre una misma placa y resolución. Por eso el tiempo se prevé en
consultas y no en piezas ubicadas: una pieza que no entra en la placa 1
gasta sus consultas igual y las vuelve a gastar en la placa 2, y las fases
finales no ubican piezas nuevas pero son una parte grande del tiempo.

Todo acá es aritmética sobre CONTEOS -- ni piezas, ni placas, ni oráculos --
a propósito: `packer.pack` la usa para una corrida, y el motor de pares y
cartera la va a usar por variante, sumando entre procesos. Recibir objetos
del motor obligaría a ese motor a fabricarlos sólo para preguntar.
"""

import math
from collections.abc import Sequence

TYPICAL_UTILIZATION = 0.4
"""Fracción del área útil que una placa termina cubriendo, para prever
cuántas placas va a abrir una corrida antes de correrla.

Sólo vale hasta que termina el primer intento: ahí la cantidad real de
placas reemplaza a esta estimación (ver `packer._Informe`). Es baja a
propósito: prever una placa de más sobreestima el tiempo, prever una de
menos lo subestima, y una espera más corta que la anunciada es la que
molesta.
"""


def estimate_sheets(
    parts_area: float,
    scrap_usable_areas: Sequence[float],
    stock_usable_area: float,
) -> int:
    """Cuántas placas se prevé abrir: primero los recortes, después las del material.

    Cada placa absorbe `TYPICAL_UTILIZATION` de su área útil. Nunca
    devuelve menos de 1, porque `forecast_greedy_pass` divide por esto.
    """
    remaining = parts_area
    sheets = 0
    for usable in scrap_usable_areas:
        if remaining <= 0:
            break
        sheets += 1
        remaining -= max(0.0, usable) * TYPICAL_UTILIZATION
    if remaining <= 0:
        return max(1, sheets)
    if stock_usable_area <= 0:
        return sheets + 1
    return sheets + math.ceil(remaining / (stock_usable_area * TYPICAL_UTILIZATION))


def forecast_greedy_pass(parts: int, orientations: int, sheets: int) -> int:
    """Consultas de una pasada golosa (`packer._pack_once`).

    En cada placa se consulta cada pieza pendiente en cada orientación. Se
    supone que las pendientes bajan parejo: en la placa `k` (desde 0) quedan
    `ceil(parts * (sheets - k) / sheets)`.
    """
    sheets = max(1, sheets)
    total = 0
    for k in range(sheets):
        pending = (parts * (sheets - k) + sheets - 1) // sheets
        total += pending * orientations
    return total


def forecast_recovery(previous_sheets: Sequence[tuple[int, int]], on_last: int) -> int:
    """Consultas de `packer._recuperar_de_la_ultima_placa`, un intento por placa anterior.

    `previous_sheets` es `(piezas en la placa, orientaciones de la placa)`
    por cada placa anterior a la última, y `on_last` las piezas que quedan
    en la última. Cada intento reempaca la placa con las pendientes
    adelante -- `(piezas + on_last) * orientaciones` -- y las pendientes que
    no entran se vuelven a consultar en la placa de derrame, `on_last *
    orientaciones` más.

    Es cota superior de UN intento por placa: las pendientes sólo bajan. Un
    intento que recupera algo paga otro sobre la misma placa; ése no está
    acá, y lo agrega quien llama cuando pasa (el packer vuelve a prever
    antes de cada intento).
    """
    return sum(
        (on_sheet + on_last) * orientations + on_last * orientations
        for on_sheet, orientations in previous_sheets
    )


def forecast_compaction(on_last: int, orientations: int) -> int:
    """Consultas de `packer._compact_last_sheet`: una pasada sobre la última placa.

    Con menos de dos piezas la compactación sale antes sin consultar nada.
    """
    if on_last < 2:
        return 0
    return on_last * orientations


def forecast_pack(parts: int, orientations: int, sheets: int, passes: int) -> int:
    """Consultas de un `pack` entero, antes de arrancar.

    `passes` pasadas golosas, la recuperación sobre `sheets - 1` placas
    anteriores y la compactación de la última, suponiendo las piezas
    repartidas parejo entre las placas.
    """
    sheets = max(1, sheets)
    per_sheet = math.ceil(parts / sheets)
    return (
        passes * forecast_greedy_pass(parts, orientations, sheets)
        + forecast_recovery([(per_sheet, orientations)] * (sheets - 1), per_sheet)
        + forecast_compaction(per_sheet, orientations)
    )
```

- [ ] **Step 4: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_prevision.py -v`
Expected: PASS, 20 tests

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/prevision.py tests/engine/test_prevision.py
git commit -m "Motor: la previsión de consultas, como aritmética pura sobre conteos"
```

---

### Task 2: El motor cuenta sus consultas

`Avance` gana los dos campos, `pack` cuenta cada `best_placement` de cada
fase, `aviso` se llama por cada pieza **intentada** (entre o no), y la
compactación avisa y se puede cancelar. En esta tarea `consultas_previstas`
todavía vale lo mismo que `consultas_hechas` (la previsión llega en la Tarea
3). Ningún layout cambia.

Por qué `aviso` pasa a llamarse también cuando la pieza NO entra: hoy una
placa donde las últimas 20 piezas no entran gasta `20 × orientaciones`
consultas sin avisar, así que el contador no se mueve, el tiempo restante se
congela y cancelar no llega hasta la primera pieza de la placa siguiente.

**Files:**
- Modify: `src/nesting/engine/packer.py` (`Avance`, clases nuevas después de `Cancelado`, `_pack_once`, `pack`, `_compact_last_sheet`)
- Modify: `tests/engine/test_progreso.py` (un docstring)
- Test: `tests/engine/test_consultas.py` (nuevo)

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces:
  - `Avance(intento, intentos, ubicadas, totales, placa, compactando=False, consultas_hechas: int = 0, consultas_previstas: int = 0)`
  - `_pack_once(order, supply, config, oracle_factory, aviso=None)`: `aviso(ubicadas, placa)` se llama después de cada pieza intentada.
  - `_compact_last_sheet(result, parts, config, oracle_factory, material_name, aviso: Callable[[int, int], None] | None = None) -> PackResult`
  - En `packer.py`, privados: `_QueryCounter` (atributo `count: int`), `_CountingOracle`, `_counting(oracle_factory, counter) -> Callable[[], Oracle]`, `_Informe(progreso, intentos, totales, consultas)` con `previstas: int`, `emitir(intento, ubicadas, placa, compactando=False)`, `aviso_de(intento)`, `aviso_final()`.
  - `pack` emite un `Avance` final con `compactando=True` después de la compactación.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/engine/test_consultas.py`:

```python
"""Las consultas al oráculo: cuántas se hicieron y cuántas se prevén.

Una consulta es una llamada a `Oracle.best_placement`. Es la unidad con la
que se mide el avance y se estima el tiempo (spec de tiempo estimado, 2).
"""

import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    Avance,
    Cancelado,
    _compact_last_sheet,
    _pack_once,
    pack,
)
from nesting.engine.raster.masks import MaskCache
from nesting.engine.raster.oracle import RasterOracle
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.model.material import Material
from nesting.model.part import Part
from nesting.model.sheet import SheetSupply

MATERIAL = Material("test", 1000.0, 1000.0, 180.0)
PLAN = SheetSupply(stock=MATERIAL.stock_sheet(), material_name=MATERIAL.name)


def cuadrado(part_id, lado=100.0):
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)),
        holes=(),
        entity_ids=(part_id,),
    )


def rectangulo(part_id, ancho, alto):
    return Part(
        part_id, ((0.0, 0.0), (ancho, 0.0), (ancho, alto), (0.0, alto)), (), (part_id,)
    )


class Espia:
    """Envuelve un oráculo, cuenta cada `best_placement` y no cambia nada.

    Es la cuenta de verdad contra la que se compara lo que informa `pack`:
    si el motor contara por su lado (por ejemplo, piezas por orientaciones)
    y no las llamadas reales, este espía lo agarra.
    """

    def __init__(self, interno, cuenta):
        self._interno = interno
        self._cuenta = cuenta

    def reset(self, sheet_w, sheet_h, config):
        self._interno.reset(sheet_w, sheet_h, config)

    def best_placement(self, part, angle, mirror):
        self._cuenta[0] += 1
        return self._interno.best_placement(part, angle, mirror)

    def place(self, part, angle, mirror, x, y):
        self._interno.place(part, angle, mirror, x, y)


def fabrica_raster():
    cache = MaskCache()
    return lambda: RasterOracle(cache=cache)


def fabrica_espia(cuenta):
    cache = MaskCache()
    return lambda: Espia(RasterOracle(cache=cache), cuenta)


def config(**cambios):
    base = {"sep": 5.0, "margin": 10.0, "effort": "rapido"}
    base.update(cambios)
    return NestConfig(**base)


def correr(piezas, cfg, fabrica, plan=PLAN):
    avances = []
    pack(piezas, plan, cfg, fabrica, progreso=lambda a: avances.append(a) or True)
    return avances


def test_un_avance_armado_como_antes_trae_cero_consultas():
    """Los corredores de mentira de `tests/app` arman `Avance` con cinco
    argumentos. Tienen que seguir funcionando sin tocarlos."""
    avance = Avance(1, 1, 0, 10, 1)
    assert avance.consultas_hechas == 0
    assert avance.consultas_previstas == 0


def test_las_consultas_hechas_nunca_bajan():
    """No se reinician entre intentos ni entre fases: son la única cifra de
    avance que no retrocede al empezar el intento siguiente."""
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = correr(piezas, config(effort="normal"), fabrica_raster())

    hechas = [a.consultas_hechas for a in avances]
    assert hechas == sorted(hechas)
    assert hechas[0] > 0


def test_las_consultas_hechas_terminan_iguales_a_las_llamadas_reales():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    cuenta = [0]

    avances = correr(piezas, config(effort="normal"), fabrica_espia(cuenta))

    assert cuenta[0] > 0
    assert avances[-1].consultas_hechas == cuenta[0]


def test_contar_no_cambia_el_layout():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    cuenta = [0]
    sin = pack(piezas, PLAN, config(), fabrica_raster())
    con = pack(piezas, PLAN, config(), fabrica_espia(cuenta), progreso=lambda a: True)

    assert [(p.part_id, p.sheet, p.transform) for p in sin.placements] == [
        (p.part_id, p.sheet, p.transform) for p in con.placements
    ]


def test_una_pieza_que_no_entra_tambien_avisa():
    """Placa de 1000 con margen 10: entra un solo cuadrado de 600 por placa.
    Las dos que no entran en la placa 1 gastan sus consultas ahí, y el aviso
    tiene que salir igual para que el contador y el botón de cancelar las
    vean."""
    grandes = [cuadrado(i, lado=600.0) for i in range(3)]
    cfg = config(angles=(0.0,), mirror=False)
    avisos = []

    _pack_once(grandes, PLAN, cfg, ShelfOracle, lambda u, p: avisos.append((u, p)))

    assert avisos == [(1, 1), (1, 1), (1, 1), (2, 2), (2, 2), (3, 3)]


def test_la_compactacion_avisa():
    """Cuatro cuadrados chicos: una sola placa, así que la recuperación sale
    sin consultar y todo aviso de `compactando` después del de entrada es de
    la compactación (4 piezas) o el final."""
    piezas = [cuadrado(i) for i in range(4)]
    avances = correr(piezas, config(), fabrica_raster())

    compactando = [a for a in avances if a.compactando]
    assert len(compactando) == 1 + 4 + 1


def test_la_compactacion_se_cancela():
    piezas = [cuadrado(i) for i in range(4)]
    vistos = []

    def cortar(avance):
        vistos.append(avance)
        return sum(1 for a in vistos if a.compactando) < 2

    with pytest.raises(Cancelado):
        pack(piezas, PLAN, config(), fabrica_raster(), progreso=cortar)

    assert sum(1 for a in vistos if a.compactando) == 2


def test_compactar_reenvia_el_aviso_y_deja_pasar_cancelado():
    """El `except PartTooLargeError` de `_compact_last_sheet` no puede
    tragarse un `Cancelado`: sería un trabajo cancelado que termina LISTO."""
    piezas = [cuadrado(i) for i in range(4)]
    fabrica = fabrica_raster()
    armado = _pack_once(piezas, PLAN, config(), fabrica)

    def cancelar(ubicadas, placa):
        raise Cancelado("el trabajo se canceló")

    with pytest.raises(Cancelado):
        _compact_last_sheet(armado, piezas, config(), fabrica, MATERIAL.name, cancelar)


def test_sin_callback_no_hay_avisos_pero_el_resultado_es_el_mismo():
    piezas = [cuadrado(i) for i in range(4)]
    assert pack(piezas, PLAN, config(), fabrica_raster()).sheets_used == 1
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_consultas.py -v`
Expected: FAIL. `test_un_avance_armado_como_antes_trae_cero_consultas` con
`AttributeError: 'Avance' object has no attribute 'consultas_hechas'`;
`test_una_pieza_que_no_entra_tambien_avisa` con una lista de 3 avisos en vez
de 6; `test_compactar_reenvia_el_aviso_y_deja_pasar_cancelado` con
`TypeError: _compact_last_sheet() takes 5 positional arguments but 6 were given`.

- [ ] **Step 3: Agregar los dos campos a `Avance`**

En `src/nesting/engine/packer.py`, reemplazar la clase `Avance` entera por:

```python
@dataclass(frozen=True)
class Avance:
    """Dónde va el motor, para quien esté mirando.

    Lleva el intento además de las piezas porque `pack` corre varias pasadas
    completas y CADA UNA REINICIA el conteo de ubicadas. Una barra armada
    sólo con `ubicadas / totales` retrocedería al empezar el intento
    siguiente, y una barra que retrocede es peor que no tener barra.

    Las consultas son la otra mitad, y la que sirve para estimar el tiempo:
    contar piezas engaña, porque una pieza que no entra gasta sus consultas
    igual y las fases finales no ubican piezas nuevas. Ver
    `nesting/engine/prevision.py`.
    """

    intento: int
    intentos: int
    ubicadas: int
    totales: int
    placa: int
    compactando: bool = False
    consultas_hechas: int = 0
    """Llamadas a `Oracle.best_placement` desde que empezó `pack`, sumando
    todos los intentos y todas las fases. No se reinicia nunca."""

    consultas_previstas: int = 0
    """La mejor previsión del total en este momento. Nunca es menor que
    `consultas_hechas`, y en el último aviso de `pack` es igual.

    Tiene valor por omisión, igual que `consultas_hechas`, para que quien
    arma un `Avance` a mano con los cinco campos de siempre -- los corredores
    de mentira de `tests/app` -- no tenga que cambiar nada."""
```

- [ ] **Step 4: Agregar el contador, el oráculo que cuenta y el informe**

En `src/nesting/engine/packer.py`, inmediatamente después de la clase
`Cancelado`, agregar:

```python
class _QueryCounter:
    """Cuántas consultas se les hicieron a los oráculos de UN `pack`.

    Un objeto y no un entero porque lo comparten todos los oráculos que la
    corrida crea -- uno por placa, por intento y por fase -- y cada uno
    tiene que sumar al mismo número.
    """

    def __init__(self) -> None:
        self.count = 0


class _CountingOracle:
    """Un oráculo que cuenta sus `best_placement` y en todo lo demás es el de adentro.

    Se envuelve la FÁBRICA en `pack` en vez de instrumentar cada fase: la
    recuperación y la compactación piden sus oráculos a la misma fábrica
    envuelta, así que ninguna consulta puede quedar fuera de la cuenta por
    olvidarse de pasar un contador.
    """

    def __init__(self, inner: Oracle, counter: _QueryCounter) -> None:
        self._inner = inner
        self._counter = counter

    def reset(self, sheet_w: float, sheet_h: float, config: NestConfig) -> None:
        self._inner.reset(sheet_w, sheet_h, config)

    def best_placement(
        self, part: Part, angle: float, mirror: bool
    ) -> tuple[float, float, float] | None:
        self._counter.count += 1
        return self._inner.best_placement(part, angle, mirror)

    def place(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        self._inner.place(part, angle, mirror, x, y)


def _counting(
    oracle_factory: Callable[[], Oracle], counter: _QueryCounter
) -> Callable[[], Oracle]:
    return lambda: _CountingOracle(oracle_factory(), counter)


class _Informe:
    """Arma cada `Avance` de un `pack` y corta si quien mira pide cancelar.

    Vive aparte porque `pack` avisa desde cuatro lugares -- la pasada
    golosa, la entrada al tramo final, la recuperación y la compactación --
    y los cuatro tienen que poner las mismas consultas y cortar igual.
    """

    def __init__(
        self,
        progreso: Callable[[Avance], bool] | None,
        intentos: int,
        totales: int,
        consultas: _QueryCounter,
    ) -> None:
        self._progreso = progreso
        self._intentos = intentos
        self._totales = totales
        self._consultas = consultas
        self.previstas = 0

    def emitir(
        self, intento: int, ubicadas: int, placa: int, compactando: bool = False
    ) -> None:
        if self._progreso is None:
            return
        hechas = self._consultas.count
        avance = Avance(
            intento,
            self._intentos,
            ubicadas,
            self._totales,
            placa,
            compactando,
            consultas_hechas=hechas,
            consultas_previstas=max(self.previstas, hechas),
        )
        if not self._progreso(avance):
            raise Cancelado("el trabajo se canceló")

    def aviso_de(self, intento: int) -> Callable[[int, int], None] | None:
        """El `aviso` de la pasada golosa número `intento`."""
        if self._progreso is None:
            return None

        def avisar(ubicadas: int, placa: int) -> None:
            self.emitir(intento, ubicadas, placa)

        return avisar

    def aviso_final(self) -> Callable[[int, int], None] | None:
        """El `aviso` de la recuperación y la compactación: "compactando".

        Las dos reportan con el mismo rótulo a propósito (ver el comentario
        en `pack`): para quien mira la barra las dos son reempaque de placas
        ya armadas. Lo que las distingue ahora son las consultas, no el
        texto.
        """
        if self._progreso is None:
            return None

        def avisar(ubicadas: int, placa: int) -> None:
            self.emitir(self._intentos, self._totales, 0, compactando=True)

        return avisar
```

- [ ] **Step 5: Avisar por cada pieza intentada en `_pack_once`**

En `_pack_once`, reemplazar el docstring y el `for part in remaining:` entero
por:

```python
    """One greedy pass, placing `order` in exactly the order given.

    `aviso` recibe (piezas ubicadas hasta ahora en esta pasada, placa en
    curso empezando en 1) despues de cada pieza INTENTADA, haya entrado o
    no: una pieza que no entra gasta sus consultas igual, y sin aviso ni el
    contador de consultas ni el pedido de cancelar la verian. Puede levantar
    para abandonar: esta funcion no atrapa nada, asi que la excepcion sale
    limpia sin dejar estado a medias en el oraculo.
    """
```

```python
        for part in remaining:
            spot = _best_over_orientations(oracle, part, choices)
            if spot is None:
                still_pending.append(part)
            else:
                angle, mirror, x, y = spot
                oracle.place(part, angle, mirror, x, y)
                en_esta_placa.append(
                    Placement(part.id, indice, Transform(angle, mirror, x, y))
                )
                placed_area += part.area
                placed_count += 1
            if aviso is not None:
                aviso(total_ubicadas + placed_count, indice + 1)
```

- [ ] **Step 6: Hacer que `_compact_last_sheet` avise y se cancele**

Cambiar la firma de `_compact_last_sheet` a:

```python
def _compact_last_sheet(
    result: PackResult,
    parts: Sequence[Part],
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    material_name: str,
    aviso: Callable[[int, int], None] | None = None,
) -> PackResult:
    """Re-pack the last sheet on its own, pulled harder towards the corner.

    `material_name` es obligatorio y sólo nombra el material en un eventual
    `PartTooLargeError`; ver el docstring de
    `_recuperar_de_la_ultima_placa`, que lo recibe igual y por lo mismo.

    `aviso` se reenvía tal cual al `_pack_once` interno. Antes esta pasada
    corría sorda: ni el contador de consultas se movía ni cancelar la
    alcanzaba. `Cancelado` NO es `PartTooLargeError`, así que el `except`
    de abajo no lo atrapa y sale limpio.
    """
```

y en su cuerpo, en la llamada a `_pack_once` que está dentro del `try`,
pasar el `aviso`:

```python
        redone = _pack_once(
            order,
            SheetSupply(stock=hoja, material_name=material_name),
            boosted,
            oracle_factory,
            aviso,
        )
```

- [ ] **Step 7: Contar en `pack` y avisar desde el informe**

En `pack`, borrar la función interna `avisos_de` entera (desde
`def avisos_de(intento: int)` hasta su `return avisar`) y poner en su lugar,
justo después de `totales = len(parts)`:

```python
    consultas = _QueryCounter()
    contado = _counting(oracle_factory, consultas)
    informe = _Informe(progreso, intentos, totales, consultas)
```

Reemplazar la primera pasada:

```python
    best_order = list(by_area)
    best = _pack_once(best_order, supply, config, contado, informe.aviso_de(1))
    best_cost = layout_cost(best, parts)
```

Dentro del `for i in range(EFFORT_RESTARTS[config.effort] - 1):`, reemplazar
la llamada a `_pack_once`:

```python
        candidate = _pack_once(
            candidate_order, supply, config, contado, informe.aviso_de(i + 2)
        )
```

Y reemplazar todo desde `if progreso is not None and not progreso(` hasta
`return best` (el final de la función) por:

```python
    informe.emitir(intentos, totales, 0, compactando=True)

    # Antes de compactar, y después del aviso de arriba a propósito: la
    # recuperación es la parte más lenta de este tramo final (un
    # `_pack_once` por placa anterior), así que quien mire la barra ya la ve
    # en "compactando" en vez de quedarse mirando el último aviso de la
    # pasada golosa.
    #
    # La recuperación reporta como "compactando" y no con una fase propia
    # a propósito: para quien mira la barra, "compactando" ya es verdad --
    # es reempaque de placas ya armadas, no la pasada golosa inicial. Lo que
    # distingue una fase de otra ahora son las consultas del `Avance`, que
    # el estimador de tiempo usa sin saber qué fase es.
    best = _recuperar_de_la_ultima_placa(
        best, parts, config, contado, supply.material_name, informe.aviso_final(),
    )
    best = _compact_last_sheet(
        best, parts, config, contado, supply.material_name, informe.aviso_final(),
    )
    # El último aviso: todo lo consultado ya está contado, así que quien
    # estime el tiempo ve cero restante en vez de quedarse con el último
    # aviso de la compactación.
    informe.emitir(intentos, totales, 0, compactando=True)
    best.seconds = time.perf_counter() - started
    return best
```

Actualizar el docstring de `pack`, reemplazando el párrafo que empieza con
`` `progreso`, si se pasa, `` por:

```python
    """Place every part, trying several insertion orders and keeping the best.

    `progreso`, si se pasa, se llama con un `Avance` despues de cada pieza
    que la pasada golosa intenta ubicar (entre o no), una vez con
    `compactando=True` al entrar al tramo final, otra vez por cada pieza que
    intentan la recuperacion (`_recuperar_de_la_ultima_placa`) y la
    compactacion (`_compact_last_sheet`), y una ultima vez al terminar. Cada
    `Avance` lleva las consultas hechas hasta ese momento, contadas sobre
    TODOS los oraculos que la corrida pidio a `oracle_factory`. Devolver
    `False` en cualquiera de esas llamadas pide abandonar, y `pack` levanta
    `Cancelado`. No pasarlo deja el layout exactamente como estaba: es lo
    que hace la CLI.
    """
```

- [ ] **Step 8: Corregir el docstring que deja de ser cierto**

En `tests/engine/test_progreso.py`, dentro de
`test_cancelar_durante_la_recuperacion_levanta`, reemplazar:

```python
    venir de dentro de la recuperación (`_compact_last_sheet` corre
    después y todavía no se instrumenta)."""
```

por:

```python
    venir de dentro de la recuperación (`_compact_last_sheet` también
    avisa, pero corre después)."""
```

- [ ] **Step 9: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_consultas.py tests/engine/test_progreso.py -v`
Expected: PASS. `test_la_compactacion_final_se_avisa_aparte` sigue verde
porque el aviso final es `compactando=True`.

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 10: Commit**

```bash
git add src/nesting/engine/packer.py tests/engine/test_consultas.py tests/engine/test_progreso.py
git commit -m "Motor: cuenta las consultas, avisa por pieza intentada y la compactación se cancela"
```

---

### Task 3: El motor prevé, y corrige la previsión por fase

`consultas_previstas` deja de ser una copia de las hechas. Se construye al
arrancar con `forecast_pack`, se corrige al terminar cada intento con lo que
costaron los intentos reales y con las placas reales, se vuelve a prever
antes de cada intento de la recuperación y al entrar a compactar, y termina
igual a las hechas.

Medido al escribir este plan, con un prototipo de esta misma cuenta sobre
el código actual (`consultas_previstas` después del primer intento contra
las llamadas reales, contadas con un espía):

| caso | placas | previstas tras el 1er intento | reales | error |
|---|---|---|---|---|
| 40 rectángulos al azar (semilla 1), `ShelfOracle`, 1000x1000, normal | 4 | 3056 | 3248 | −5,9% |
| `banqueta-alta.ai`, multilam18 (1220x2440, veta), sep 8, borde 5, 2 mm/px, normal | 2 | 928 | 928 | 0,0% |

La previsión de ARRANQUE sobre la banqueta da 1496 contra 928 reales (+61%):
estima 2 placas con 29 piezas en la segunda, y en la realidad la segunda
lleva una sola. Es lo esperable antes de correr nada; lo que la spec pide
afinado es la previsión después del primer intento.

**Files:**
- Modify: `src/nesting/engine/packer.py` (import de `prevision`, `_Informe`, funciones nuevas antes de `pack`, `pack`, `_recuperar_de_la_ultima_placa`)
- Test: `tests/engine/test_consultas.py`

**Interfaces:**
- Consumes: todo `nesting.engine.prevision` (Tarea 1); `_Informe`, `_counting`, `_QueryCounter`, `Avance.consultas_*` (Tarea 2).
- Produces:
  - `initial_forecast(parts: Sequence[Part], supply: SheetSupply, config: NestConfig) -> int` en `nesting.engine.packer`. Levanta `UnknownEffortError` con un esfuerzo desconocido.
  - `_recuperar_de_la_ultima_placa(result, parts, config, oracle_factory, material_name, aviso=None, prever: Callable[[int, int], None] | None = None)`: `prever(consultas_restantes_de_la_recuperacion, pendientes)` antes de cada intento.
  - `_Informe.corregir_tras_intentos(hechos: int, restantes_finales: int)` y `_Informe.prever_desde_ahora(restantes: int)`.
  - En `packer.py`, privados: `_restarts_for(config) -> int`, `_usable_area(sheet, margin) -> float`, `_compaction_forecast(result, config) -> int`, `_forecast_final_phases(result, config) -> int`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al import de `tests/engine/test_consultas.py`:

```python
import random
import sys
from pathlib import Path

from nesting.engine.packer import (
    UnknownEffortError,
    _recuperar_de_la_ultima_placa,
    initial_forecast,
)
from nesting.engine.prevision import forecast_pack
from nesting.io.ai_reader import read_ai
from nesting.io.dxf_reader import read_dxf
from nesting.model.material import VETA_RESPETAR
from nesting.pipeline import prepare_parts

RAIZ = Path(__file__).resolve().parents[2]
BANQUETA = RAIZ / "bench" / "files" / "banqueta-alta.ai"

sys.path.insert(0, str(RAIZ / "bench"))
from make_sample import write_sample  # noqa: E402
```

Y agregar al final del archivo:

```python
def test_la_prevision_de_arranque_de_un_caso_a_mano():
    """Diez cuadrados de 100 en una placa de 1000: área de piezas 1e5 contra
    980 x 980 x 0.4 = 384160 útiles, así que una placa. Cuatro ángulos con
    espejo son 8 orientaciones, y normal son 3 intentos."""
    piezas = [cuadrado(i) for i in range(10)]
    cfg = config(effort="normal")

    assert initial_forecast(piezas, PLAN, cfg) == forecast_pack(10, 8, 1, 3) == 320


def test_la_prevision_de_arranque_rechaza_un_esfuerzo_desconocido():
    with pytest.raises(UnknownEffortError):
        initial_forecast([cuadrado(0)], PLAN, config(effort="turbo"))


def test_sin_piezas_no_se_prevé_nada():
    assert initial_forecast([], PLAN, config()) == 0


def test_el_primer_aviso_trae_la_prevision_de_arranque():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    cfg = config(effort="normal")

    avances = correr(piezas, cfg, fabrica_raster())

    assert avances[0].consultas_previstas == initial_forecast(piezas, PLAN, cfg)


def test_las_previstas_nunca_quedan_por_debajo_de_las_hechas():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = correr(piezas, config(effort="normal"), fabrica_raster())

    assert all(a.consultas_previstas >= a.consultas_hechas for a in avances)


def test_el_ultimo_aviso_dice_que_no_falta_nada():
    piezas = [cuadrado(i, lado=400.0) for i in range(12)]
    avances = correr(piezas, config(effort="normal"), fabrica_raster())

    assert avances[-1].consultas_previstas == avances[-1].consultas_hechas


def test_al_entrar_a_compactar_la_prevision_es_exacta():
    """Una placa con cuatro cuadrados: no hay recuperación, y compactar es
    una pasada de 4 piezas por 8 orientaciones. Al entrar ya se sabe."""
    piezas = [cuadrado(i) for i in range(4)]
    avances = correr(piezas, config(), fabrica_raster())

    entrada = next(a for a in avances if a.compactando)
    assert entrada.consultas_previstas == entrada.consultas_hechas + 4 * 8
    assert avances[-1].consultas_hechas == entrada.consultas_hechas + 4 * 8


# El escenario de `test_recuperacion.py`, copiado y no importado para que
# este archivo no dependa de otro archivo de tests: una placa de 1000 con
# margen 20, una sola orientación, y ANGOSTA que la avaricia manda a la
# placa 2 (ver el comentario largo de allá).
ESTANTES = NestConfig(sep=10.0, margin=20.0, angles=(0.0,), mirror=False, effort="rapido")
PLACA_TRES = Material("mdf", 1000.0, 1000.0, grain_tolerance=180.0)
PLAN_TRES = SheetSupply(stock=PLACA_TRES.stock_sheet(), material_name=PLACA_TRES.name)
TRES = [
    rectangulo(0, 600.0, 450.0),
    rectangulo(1, 600.0, 400.0),
    rectangulo(2, 300.0, 520.0),
]


def test_la_recuperacion_preve_antes_de_cada_intento():
    """Placa 0 con 2 piezas, 1 pendiente, 1 orientación: el intento cuesta
    (2 + 1) consultas en la placa más 1 en el derrame."""
    goloso = _pack_once(TRES, PLAN_TRES, ESTANTES, ShelfOracle)
    assert goloso.sheets_used == 2
    previstos = []

    _recuperar_de_la_ultima_placa(
        goloso, TRES, ESTANTES, ShelfOracle, PLACA_TRES.name,
        None, lambda restantes, pendientes: previstos.append((restantes, pendientes)),
    )

    assert previstos[0] == (4, 1)


def _rectangulos_al_azar():
    rng = random.Random(1)
    return [
        rectangulo(i, float(rng.randint(80, 400)), float(rng.randint(80, 400)))
        for i in range(40)
    ]


def _caso(nombre, tmp_path):
    """(piezas, plan, config, fábrica) de cada caso del bench."""
    if nombre == "estantes":
        return (
            _rectangulos_al_azar(), PLAN, config(effort="normal"), ShelfOracle,
        )
    if nombre == "muestra":
        ruta = tmp_path / "muestra.dxf"
        write_sample(ruta)
        piezas, _, _ = prepare_parts(read_dxf(ruta))
        mdf18 = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
        return (
            piezas,
            SheetSupply(stock=mdf18.stock_sheet(), material_name=mdf18.name),
            NestConfig(sep=6.0, margin=10.0, effort="normal", resolution=3.0),
            fabrica_raster(),
        )
    if not BANQUETA.exists():
        pytest.skip(
            f"falta {BANQUETA}: bench/files/ no está versionado. Copiar ahí "
            "`BANQUETA ALTA NESTING.ai` con el nombre banqueta-alta.ai para "
            "correr este caso."
        )
    piezas, _, _ = prepare_parts(read_ai(BANQUETA))
    multilam = Material("multilam18", 1220.0, 2440.0, grain_tolerance=VETA_RESPETAR)
    # 2 mm/px y no 1: a 1 mm/px la corrida tarda 126 s, y este test corre
    # con la suite entera al cerrar cada tarea. La previsión cuenta
    # consultas, que no dependen de la resolución más que por el layout.
    return (
        piezas,
        SheetSupply(stock=multilam.stock_sheet(), material_name=multilam.name),
        NestConfig(sep=8.0, margin=5.0, effort="normal", resolution=2.0),
        fabrica_raster(),
    )


@pytest.mark.parametrize("nombre", ["estantes", "muestra", "banqueta-alta"])
def test_despues_del_primer_intento_la_prevision_erra_menos_de_un_cuarto(nombre, tmp_path):
    """Spec, 4: después del primer intento, el error de la previsión contra
    el total real es menor al 25% sobre los archivos del bench.

    El primer aviso del intento 2 es el primero que lleva la previsión
    corregida con lo que costó el intento 1 y con sus placas reales."""
    piezas, plan, cfg, fabrica = _caso(nombre, tmp_path)

    avances = correr(piezas, cfg, fabrica, plan=plan)

    tras_el_primero = next(a for a in avances if a.intento == 2 and not a.compactando)
    reales = avances[-1].consultas_hechas
    error = abs(tras_el_primero.consultas_previstas - reales) / reales
    assert error < 0.25, (
        f"{nombre}: previstas {tras_el_primero.consultas_previstas}, reales {reales}"
    )
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_consultas.py -v`
Expected: FAIL con `ImportError: cannot import name 'initial_forecast' from 'nesting.engine.packer'` (el módulo entero no carga).

- [ ] **Step 3: Importar la previsión y ampliar `_Informe`**

En `src/nesting/engine/packer.py`, agregar a los imports:

```python
from nesting.engine.prevision import (
    estimate_sheets,
    forecast_compaction,
    forecast_pack,
    forecast_recovery,
)
```

Agregar a `_Informe`, después de `aviso_final`:

```python
    def corregir_tras_intentos(self, hechos: int, restantes_finales: int) -> None:
        """Ya terminaron `hechos` pasadas golosas completas, y todo lo
        contado hasta acá es de ellas: los intentos que faltan se prevén
        como el promedio de los hechos, y las fases finales con las placas
        reales del mejor layout hasta ahora."""
        por_intento = self._consultas.count / hechos
        self.previstas = round(por_intento * self._intentos) + restantes_finales

    def prever_desde_ahora(self, restantes: int) -> None:
        """Lo que falta ya se sabe contar desde el estado actual."""
        self.previstas = self._consultas.count + restantes
```

- [ ] **Step 4: Agregar la previsión de arranque y la de las fases finales**

En `src/nesting/engine/packer.py`, inmediatamente antes de `def pack(`,
agregar:

```python
def _restarts_for(config: NestConfig) -> int:
    """Cuántas pasadas golosas corre este nivel de esfuerzo, o el error de siempre."""
    if config.effort not in EFFORT_RESTARTS:
        raise UnknownEffortError(
            f"nivel de esfuerzo {config.effort!r} desconocido; "
            f"use uno de {', '.join(EFFORT_RESTARTS)}"
        )
    return EFFORT_RESTARTS[config.effort]


def _usable_area(sheet: Sheet, margin: float) -> float:
    return max(0.0, sheet.width - 2 * margin) * max(0.0, sheet.height - 2 * margin)


def initial_forecast(
    parts: Sequence[Part], supply: SheetSupply, config: NestConfig
) -> int:
    """Cuántas consultas se prevé que cueste `pack(parts, supply, config, ...)`, antes de correrlo.

    Es la misma cuenta con la que `pack` arranca su previsión, y la que usa
    la estimación de tiempo previa (`nesting_app.corredor.estimar_segundos`).
    Las orientaciones se cuentan sobre la placa del Material: un recorte con
    la veta cruzada puede permitir otras, pero la cantidad es la misma.
    """
    passes = _restarts_for(config)
    if not parts:
        return 0
    sheets = estimate_sheets(
        sum(p.area for p in parts),
        [_usable_area(s, config.margin) for s in supply.scraps],
        _usable_area(supply.stock, config.margin),
    )
    return forecast_pack(
        len(parts), len(orientations(supply.stock, config)), sheets, passes
    )


def _compaction_forecast(result: PackResult, config: NestConfig) -> int:
    """Consultas de compactar la última placa de `result`, contadas sobre ella."""
    if result.sheets_used == 0:
        return 0
    last = result.sheets_used - 1
    on_last = sum(1 for p in result.placements if p.sheet == last)
    return forecast_compaction(on_last, len(orientations(result.sheets[last], config)))


def _forecast_final_phases(result: PackResult, config: NestConfig) -> int:
    """Consultas de la recuperación y la compactación sobre las placas reales de `result`."""
    if result.sheets_used == 0:
        return 0
    per_sheet = [0] * result.sheets_used
    for placement in result.placements:
        per_sheet[placement.sheet] += 1
    last = result.sheets_used - 1
    previous = [
        (per_sheet[i], len(orientations(result.sheets[i], config))) for i in range(last)
    ]
    return forecast_recovery(previous, per_sheet[last]) + _compaction_forecast(
        result, config
    )
```

- [ ] **Step 5: Que la recuperación prevea antes de cada intento**

Cambiar la firma de `_recuperar_de_la_ultima_placa` a:

```python
def _recuperar_de_la_ultima_placa(
    result: PackResult,
    parts: Sequence[Part],
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    material_name: str,
    aviso: Callable[[int, int], None] | None = None,
    prever: Callable[[int, int], None] | None = None,
) -> PackResult:
```

y agregar al docstring, después del párrafo de `aviso`:

```python
    `prever`, si se pasa, se llama antes de cada intento con (consultas que
    se prevé que cueste lo que queda de la recuperación, pendientes que
    quedan en la última placa). Se vuelve a llamar en cada intento porque la
    cuenta cambia: un intento que recupera algo paga OTRO sobre la misma
    placa, y las pendientes que quedan son menos.
```

En el cuerpo, dentro del `while pendientes:`, inmediatamente antes de la
línea `orden = [pendientes[0], *en_placa, *pendientes[1:]]`, agregar:

```python
            if prever is not None:
                prever(
                    forecast_recovery(
                        [
                            (
                                len(por_placa.get(k, [])),
                                len(orientations(result.sheets[k], config)),
                            )
                            for k in range(placa, ultima)
                        ],
                        len(pendientes),
                    ),
                    len(pendientes),
                )
```

- [ ] **Step 6: Prever en `pack`**

En `pack`, reemplazar el bloque inicial desde `if config.effort not in
EFFORT_RESTARTS:` hasta `intentos = EFFORT_RESTARTS[config.effort]`
(inclusive) por:

```python
    intentos = _restarts_for(config)

    started = time.perf_counter()
    if not parts:
        return PackResult(seconds=time.perf_counter() - started)

    rng = random.Random(config.seed)
    by_area = sorted(parts, key=lambda p: p.area, reverse=True)
```

(`totales = len(parts)` y las tres líneas de la Tarea 2 que crean
`consultas`, `contado` e `informe` quedan como están, a continuación.)
Inmediatamente después de `informe = _Informe(...)`, agregar:

```python
    informe.previstas = initial_forecast(parts, supply, config)
```

Después de `best_cost = layout_cost(best, parts)` (el de la primera pasada),
agregar:

```python
    informe.corregir_tras_intentos(1, _forecast_final_phases(best, config))
```

Cambiar la cabecera del bucle de reintentos a
`for i in range(intentos - 1):` y agregar, como última línea del cuerpo del
bucle (después del `if candidate_cost < best_cost:` y su asignación):

```python
        informe.corregir_tras_intentos(i + 2, _forecast_final_phases(best, config))
```

Y reemplazar el tramo desde `best = _recuperar_de_la_ultima_placa(` hasta
el `informe.emitir(intentos, totales, 0, compactando=True)` final
(inclusive) por:

```python
    choices_ultima = len(orientations(best.sheets[-1], config))

    def prever_recuperacion(restantes: int, pendientes: int) -> None:
        # Mientras dura la recuperación, la compactación se prevé con las
        # pendientes de ahora: la recuperación sólo puede sacar piezas de
        # la última placa, así que es cota superior.
        informe.prever_desde_ahora(
            restantes + forecast_compaction(pendientes, choices_ultima)
        )

    best = _recuperar_de_la_ultima_placa(
        best, parts, config, contado, supply.material_name,
        informe.aviso_final(), prever_recuperacion,
    )
    informe.prever_desde_ahora(_compaction_forecast(best, config))
    best = _compact_last_sheet(
        best, parts, config, contado, supply.material_name, informe.aviso_final(),
    )
    # El último aviso: todo lo consultado ya está contado, así que quien
    # estime el tiempo ve cero restante en vez de quedarse con el último
    # aviso de la compactación.
    informe.prever_desde_ahora(0)
    informe.emitir(intentos, totales, 0, compactando=True)
```

(`best.seconds = time.perf_counter() - started` y `return best` siguen
igual al final.)

- [ ] **Step 7: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_consultas.py -v`
Expected: PASS. `banqueta-alta` pasa si el archivo está en `bench/files/`
(unos 40 s) o sale `SKIPPED` con el motivo si no.

Si `test_despues_del_primer_intento_la_prevision_erra_menos_de_un_cuarto`
falla en algún caso: **no aflojar el 25%, que es de la spec.** Anotar el caso,
las previstas y las reales que imprime el mensaje, y parar a avisar.

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 8: Commit**

```bash
git add src/nesting/engine/packer.py tests/engine/test_consultas.py
git commit -m "Motor: prevé las consultas al arrancar y corrige la previsión en cada fase"
```

---

### Task 4: El servidor estima cuánto falta

`nesting_app.jobs` tiene el reloj, así que ahí se pasa de consultas a
segundos. El estado del trabajo gana `restante_s`, y el JSON del trabajo lo
expone junto con las consultas del avance.

Dos decisiones que la spec deja abiertas y que acá se fijan:

- **Desde cuándo se mide.** `transcurrido` y `consultas_hechas` se miden
  desde el PRIMER aviso, no desde que arrancó el trabajo. Entre arrancar y
  el primer aviso el corredor lee el archivo y prepara las piezas, que no
  son consultas: medir desde antes cargaría ese segundo a la cuenta de
  segundos por consulta. Los umbrales de 5 s y 20 consultas se cuentan
  desde ese mismo punto.
- **El promedio móvil arranca cuando se pasan los umbrales.** Las muestras
  de los primeros segundos son las más ruidosas; no se promedian.

**Files:**
- Modify: `src/nesting_app/jobs.py`
- Modify: `src/nesting_app/api.py` (`_avance_a_dict`, `ver_trabajo`)
- Test: `tests/app/test_jobs.py`, `tests/app/test_api_trabajos.py`

**Interfaces:**
- Consumes: `Avance.consultas_hechas`, `Avance.consultas_previstas` (Tarea 2).
- Produces:
  - En `nesting_app.jobs`: `ESPERA_MINIMA_S = 5.0`, `CONSULTAS_MINIMAS = 20`, `PESO_DE_LA_MUESTRA = 0.2`; `EstimadorDeRestante(reloj: Callable[[], float] = time.monotonic)` con `actualizar(hechas: int, previstas: int) -> float | None`.
  - `Trabajo.restante_s: float | None = None`.
  - `Registro(carpeta: Path, reloj: Callable[[], float] = time.monotonic)`.
  - JSON de `GET /api/trabajos/{id}`: `"restante_s"` a nivel del trabajo, y `"consultas_hechas"` / `"consultas_previstas"` dentro de `"avance"`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/app/test_jobs.py`, agregar `EstimadorDeRestante` al import de
`nesting_app.jobs`, y al final del archivo:

```python
class RelojFalso:
    """Un reloj que avanza sólo cuando el test lo dice."""

    def __init__(self):
        self.ahora = 0.0

    def __call__(self):
        return self.ahora


def test_el_primer_aviso_es_la_referencia_y_no_estima():
    estimador = EstimadorDeRestante(RelojFalso())
    assert estimador.actualizar(0, 1000) is None


def test_antes_de_cinco_segundos_no_hay_restante():
    reloj = RelojFalso()
    estimador = EstimadorDeRestante(reloj)
    estimador.actualizar(0, 1000)

    reloj.ahora = 4.9
    assert estimador.actualizar(500, 1000) is None


def test_antes_de_veinte_consultas_no_hay_restante():
    reloj = RelojFalso()
    estimador = EstimadorDeRestante(reloj)
    estimador.actualizar(0, 1000)

    reloj.ahora = 30.0
    assert estimador.actualizar(19, 1000) is None


def test_los_umbrales_se_cuentan_desde_el_primer_aviso():
    """Leer el archivo no son consultas: si el primer aviso llega a los 3 s
    con 16 consultas, a los 6 s todavía no pasaron 5 s de medición."""
    reloj = RelojFalso()
    estimador = EstimadorDeRestante(reloj)
    reloj.ahora = 3.0
    estimador.actualizar(16, 1000)

    reloj.ahora = 6.0
    assert estimador.actualizar(200, 1000) is None


def test_la_cuenta_es_segundos_por_consulta_por_consultas_que_faltan():
    reloj = RelojFalso()
    estimador = EstimadorDeRestante(reloj)
    estimador.actualizar(0, 1000)

    reloj.ahora = 10.0
    # 10 s / 100 consultas = 0.1 s por consulta, y faltan 900.
    assert estimador.actualizar(100, 1000) == pytest.approx(90.0)


def test_una_consulta_lenta_aislada_no_mueve_el_numero_entero():
    """El promedio móvil: la muestra nueva pesa 0.2 y el promedio 0.8."""
    reloj = RelojFalso()
    estimador = EstimadorDeRestante(reloj)
    estimador.actualizar(0, 300)
    reloj.ahora = 10.0
    assert estimador.actualizar(100, 300) == pytest.approx(20.0)

    # 20 s sin una sola consulta nueva: la muestra cruda sube a 0.3 s por
    # consulta, que daría 60 s. Con el promedio: 0.2*0.3 + 0.8*0.1 = 0.14.
    reloj.ahora = 30.0
    assert estimador.actualizar(100, 300) == pytest.approx(0.14 * 200)


def test_si_las_previstas_quedan_cortas_no_falta_nada():
    reloj = RelojFalso()
    estimador = EstimadorDeRestante(reloj)
    estimador.actualizar(0, 100)
    reloj.ahora = 10.0
    assert estimador.actualizar(150, 100) == 0.0


def test_un_avance_sin_consultas_nunca_estima():
    """Los corredores de mentira arman `Avance` sin consultas: todo queda en
    cero y el estimador no puede inventar nada."""
    reloj = RelojFalso()
    estimador = EstimadorDeRestante(reloj)
    estimador.actualizar(0, 0)
    reloj.ahora = 60.0
    assert estimador.actualizar(0, 0) is None


def test_el_registro_publica_el_restante_mientras_corre(tmp_path):
    """Los `Event` sincronizan exactamente los dos hechos que importan --
    que el corredor ya publicó cada aviso -- en vez de apostar a un
    `time.sleep`. El reloj falso lo mueve el propio corredor, en su hilo,
    que es el mismo en el que el estimador lo lee."""
    reloj = RelojFalso()
    registro = Registro(tmp_path / "trabajos", reloj=reloj)
    primero = threading.Event()
    seguir = threading.Event()
    segundo = threading.Event()
    suelto = threading.Event()

    def corredor(fuente, params, progreso, carpeta):
        progreso(Avance(1, 1, 0, 10, 1, consultas_hechas=0, consultas_previstas=1000))
        primero.set()
        seguir.wait(timeout=5)
        reloj.ahora = 10.0
        progreso(Avance(1, 1, 5, 10, 1, consultas_hechas=100, consultas_previstas=1000))
        segundo.set()
        suelto.wait(timeout=5)
        return resultado_falso(carpeta)

    try:
        trabajo = registro.crear(FUENTE, PARAMS, corredor)
        assert primero.wait(timeout=5), "el corredor nunca llegó al primer aviso"
        assert trabajo.restante_s is None
        seguir.set()
        assert segundo.wait(timeout=5), "el corredor nunca llegó al segundo aviso"
        assert trabajo.restante_s == pytest.approx(90.0)
    finally:
        seguir.set()
        suelto.set()
        registro.cerrar()


def test_un_trabajo_recien_creado_no_tiene_restante():
    assert Trabajo(id="x").restante_s is None
```

En `tests/app/test_api_trabajos.py`, agregar al final:

```python
def test_el_estado_del_trabajo_trae_las_consultas_y_el_restante(cliente, tmp_path):
    cuadrados = [(i * 60 % 1500, (i * 60 // 1500) * 60, 50) for i in range(120)]
    fuente_id = fuente_de(cliente, tmp_path, cuadrados)
    trabajo_id = cliente.post("/api/trabajos", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "esfuerzo": "lento"},
    }).json()["id"]

    fin = time.monotonic() + 30
    cuerpo = None
    while time.monotonic() < fin:
        cuerpo = cliente.get(f"/api/trabajos/{trabajo_id}").json()
        if cuerpo["avance"]:
            break
        time.sleep(0.02)

    cliente.post(f"/api/trabajos/{trabajo_id}/cancelar")
    avance = cuerpo["avance"]
    assert avance is not None
    assert avance["consultas_previstas"] >= avance["consultas_hechas"] > 0
    assert "restante_s" in cuerpo
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_jobs.py tests/app/test_api_trabajos.py -v`
Expected: FAIL. `test_jobs.py` entero con
`ImportError: cannot import name 'EstimadorDeRestante' from 'nesting_app.jobs'`;
`test_el_estado_del_trabajo_trae_las_consultas_y_el_restante` con
`KeyError: 'consultas_previstas'`.

- [ ] **Step 3: Escribir el estimador y conectarlo al registro**

En `src/nesting_app/jobs.py`, agregar `import time` a los imports.

Después de la clase `Resultado` y antes de `class Trabajo`, agregar:

```python
ESPERA_MINIMA_S = 5.0
"""Segundos de medición antes de dar un número. Antes no hay datos."""

CONSULTAS_MINIMAS = 20
"""Consultas medidas antes de dar un número. Con la veta respetada una
pieza son 4 consultas: 20 son cinco piezas, lo mínimo para que una pieza
rara no decida sola."""

PESO_DE_LA_MUESTRA = 0.2
"""Cuánto pesa la muestra nueva en el promedio móvil de segundos por
consulta. Bajo a propósito: una consulta lenta aislada -- una pieza grande
contra una placa casi llena -- no tiene que mover el número mostrado."""


class EstimadorDeRestante:
    """Cuántos segundos le faltan a un trabajo, a partir de sus consultas.

        segundos_por_consulta = transcurrido / consultas_hechas
        restante = segundos_por_consulta * (consultas_previstas - consultas_hechas)

    con un promedio móvil exponencial sobre `segundos_por_consulta`.

    `transcurrido` y `consultas_hechas` se miden desde el PRIMER aviso y no
    desde que arrancó el trabajo: lo que pasa antes -- leer el archivo,
    preparar las piezas -- no son consultas, y medirlo cargaría ese tiempo a
    cada una. El reloj se inyecta para poder probarlo sin esperar.
    """

    def __init__(self, reloj: Callable[[], float] = time.monotonic) -> None:
        self._reloj = reloj
        self._referencia: tuple[float, int] | None = None
        self._por_consulta: float | None = None

    def actualizar(self, hechas: int, previstas: int) -> float | None:
        """Segundos que faltan, o `None` mientras no hay datos para decirlo."""
        ahora = self._reloj()
        if self._referencia is None:
            self._referencia = (ahora, hechas)
            return None
        desde, hechas_al_empezar = self._referencia
        transcurrido = ahora - desde
        medidas = hechas - hechas_al_empezar
        if transcurrido < ESPERA_MINIMA_S or medidas < CONSULTAS_MINIMAS:
            return None
        muestra = transcurrido / medidas
        if self._por_consulta is None:
            self._por_consulta = muestra
        else:
            self._por_consulta = (
                PESO_DE_LA_MUESTRA * muestra
                + (1 - PESO_DE_LA_MUESTRA) * self._por_consulta
            )
        return self._por_consulta * max(0, previstas - hechas)
```

En `class Trabajo`, agregar el campo inmediatamente antes de `_cancelar`:

```python
    restante_s: float | None = None
    """Segundos que faltan según `EstimadorDeRestante`, o `None` mientras
    no hay datos (los primeros 5 s o las primeras 20 consultas)."""
```

En `class Registro`, cambiar `__init__` a:

```python
    def __init__(
        self, carpeta: Path, reloj: Callable[[], float] = time.monotonic
    ) -> None:
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._reloj = reloj
        self._trabajos: dict[str, Trabajo] = {}
        self._trabajos_lock = threading.Lock()
        self._cola: queue.Queue = queue.Queue()
        self._cerrando = threading.Event()
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()
```

y en `_correr`, reemplazar la función interna `progreso` por:

```python
        estimador = EstimadorDeRestante(self._reloj)

        def progreso(avance: Avance) -> bool:
            trabajo.avance = avance
            trabajo.restante_s = estimador.actualizar(
                avance.consultas_hechas, avance.consultas_previstas
            )
            return not trabajo._cancelar.is_set()
```

- [ ] **Step 4: Exponer las consultas y el restante en la API**

En `src/nesting_app/api.py`, dentro de `_avance_a_dict`, agregar las dos
claves al diccionario que devuelve, después de `"compactando"`:

```python
            "consultas_hechas": avance.consultas_hechas,
            "consultas_previstas": avance.consultas_previstas,
```

y en `ver_trabajo`, agregar al diccionario que devuelve, después de
`"avance": _avance_a_dict(trabajo.avance),`:

```python
            "restante_s": trabajo.restante_s,
```

- [ ] **Step 5: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/app/test_jobs.py tests/app/test_api_trabajos.py -v`
Expected: PASS

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app/jobs.py src/nesting_app/api.py tests/app/test_jobs.py tests/app/test_api_trabajos.py
git commit -m "Trabajos: el servidor estima cuánto falta a partir de las consultas y del reloj"
```

---

### Task 5: La estimación antes de arrancar

`POST /api/estimar` recibe lo mismo que la creación de un trabajo
(`PedidoTrabajo`: la fuente y `ParamsEntrada`, veta incluida) y devuelve
`{"segundos": float}` o `{"segundos": null}`.

    segundos = segundos_por_consulta_medido × consultas_previstas_al_arrancar × FACTOR_LLENO

La prueba de una consulta vive en el motor (`probe_query_seconds`) y no sabe
qué oráculo mide: recibe la fábrica. `FACTOR_LLENO` vive en el corredor, con
un valor provisional de 1.5 que la Tarea 6 reemplaza por el medido.

Para orientarse, medido al escribir este plan con el código actual: sobre
`banqueta-alta.ai` (multilam18, sep 8, borde 5) la prueba tarda ~0,11 s a
1 mm/px y ~0,018 s a 2 mm/px; la corrida real gasta 0,136 s y 0,033 s por
consulta (factores ~1,2 y ~1,8). Sobre la muestra sintética (mdf18,
2 mm/px, rápido) la estimación con 1.5 da 2,06 s contra 2,43 s reales.

`null`, y no un error, en todo lo que es "no se puede estimar": fuente
desconocida, material que no existe, parámetros que no validan, archivo que
no se lee o que no tiene piezas. La pantalla no muestra nada en esos casos;
el error de verdad lo va a dar Acomodar, con su cartel. Un bug del programa
NO se disfraza: sale como 500 y la pantalla tampoco muestra nada.

**Files:**
- Modify: `src/nesting/engine/packer.py` (`probe_query_seconds`)
- Modify: `src/nesting_app/corredor.py`
- Modify: `src/nesting_app/api.py`
- Test: `tests/engine/test_consultas.py`, `tests/app/test_corredor.py`, `tests/app/test_api_trabajos.py`

**Interfaces:**
- Consumes: `initial_forecast` (Tarea 3), `orientations`; del plan de veta: `validar(p, material)`, `a_supply(p, material)`.
- Produces:
  - `probe_query_seconds(parts: Sequence[Part], supply: SheetSupply, config: NestConfig, oracle_factory: Callable[[], Oracle], clock: Callable[[], float] = time.perf_counter) -> float | None` en `nesting.engine.packer`.
  - En `nesting_app.corredor`: `FACTOR_LLENO: float`, `estimar_segundos(piezas, supply, config) -> float | None`, `estimar(fuente: Fuente, params: NestParams) -> float | None`.
  - Ruta `POST /api/estimar` con cuerpo `PedidoTrabajo`, respuesta `{"segundos": float | None}`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/engine/test_consultas.py`, agregar `probe_query_seconds` al import
de `nesting.engine.packer`, y al final del archivo:

```python
class Anotador(ShelfOracle):
    """Un oráculo de estantes que anota qué le preguntaron."""

    def __init__(self, anotadas):
        super().__init__()
        self._anotadas = anotadas

    def best_placement(self, part, angle, mirror):
        self._anotadas.append((part.id, angle, mirror))
        return super().best_placement(part, angle, mirror)


def test_la_prueba_mide_una_consulta_con_la_pieza_mas_grande():
    chica, grande = cuadrado(0, 100.0), cuadrado(1, 300.0)
    anotadas = []
    tiempos = iter([10.0, 10.25])

    segundos = probe_query_seconds(
        [chica, grande], PLAN, config(), lambda: Anotador(anotadas),
        clock=lambda: next(tiempos),
    )

    assert segundos == pytest.approx(0.25)
    assert anotadas == [(1, 0.0, False)], "una sola consulta, la primera orientación"


def test_sin_orientaciones_permitidas_no_hay_prueba():
    con_veta = Material("veta", 1000.0, 1000.0, grain_tolerance=5.0)
    plan = SheetSupply(stock=con_veta.stock_sheet(), material_name=con_veta.name)

    assert probe_query_seconds(
        [cuadrado(0)], plan, config(angles=(90.0,)), ShelfOracle
    ) is None


def test_sin_piezas_no_hay_prueba():
    assert probe_query_seconds([], PLAN, config(), ShelfOracle) is None
```

En `tests/app/test_corredor.py`, agregar a los imports de arriba:

```python
from nesting.engine.oracle import NestConfig
from nesting.engine.packer import initial_forecast
from nesting.model.material import Material
from nesting.model.part import Part
from nesting.model.sheet import SheetSupply
```

y al final del archivo:

```python
MDF18 = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
PLAN_MDF18 = SheetSupply(stock=MDF18.stock_sheet(), material_name=MDF18.name)


def pieza_cuadrada(part_id, lado=200.0):
    return Part(
        part_id, ((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)), (), (part_id,)
    )


def test_la_estimacion_es_prueba_por_prevision_por_factor(monkeypatch):
    """La fórmula de la spec, 3.2, con la prueba fijada para que el número
    sea exacto."""
    piezas = [pieza_cuadrada(i) for i in range(5)]
    cfg = NestConfig(sep=5.0, margin=10.0, effort="rapido")
    monkeypatch.setattr(corredor, "probe_query_seconds", lambda *a, **k: 0.01)

    assert corredor.estimar_segundos(piezas, PLAN_MDF18, cfg) == pytest.approx(
        0.01 * initial_forecast(piezas, PLAN_MDF18, cfg) * corredor.FACTOR_LLENO
    )


def test_la_estimacion_mide_de_verdad_si_no_se_la_fija():
    piezas = [pieza_cuadrada(i) for i in range(3)]
    cfg = NestConfig(sep=5.0, margin=10.0, effort="rapido", resolution=4.0)

    assert corredor.estimar_segundos(piezas, PLAN_MDF18, cfg) > 0


def test_sin_piezas_no_hay_estimacion():
    assert corredor.estimar_segundos([], PLAN_MDF18, NestConfig()) is None


def test_estimar_lee_la_fuente_y_devuelve_segundos(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 150)]))

    segundos = corredor.estimar(fuente, params(resolucion=4.0))

    assert isinstance(segundos, float) and segundos > 0


def test_estimar_con_un_material_que_no_existe_da_none(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))

    assert corredor.estimar(fuente, NestParams(material="no-existe")) is None


def test_estimar_con_parametros_invalidos_da_none(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))

    assert corredor.estimar(fuente, params(sep=-1.0)) is None


def test_estimar_un_archivo_sin_piezas_da_none(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, []))

    assert corredor.estimar(fuente, params()) is None


def test_estimar_un_archivo_sin_unidades_da_none(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)], unidades=0))

    assert corredor.estimar(fuente, params()) is None
```

En `tests/app/test_api_trabajos.py`, agregar al final:

```python
def test_estimar_devuelve_segundos_para_una_fuente_leida(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/estimar", json={
        "fuente_id": fuente_id,
        "params": {"material": "mdf18", "esfuerzo": "rapido", "resolucion": 4},
    })

    assert respuesta.status_code == 200
    assert respuesta.json()["segundos"] > 0


def test_estimar_sin_fuente_devuelve_null(cliente):
    respuesta = cliente.post("/api/estimar", json={
        "fuente_id": "no-existe", "params": {"material": "mdf18"},
    })

    assert respuesta.status_code == 200
    assert respuesta.json() == {"segundos": None}


def test_estimar_con_parametros_invalidos_devuelve_null(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/estimar", json={
        "fuente_id": fuente_id, "params": {"material": "mdf18", "sep": -1},
    })

    assert respuesta.json() == {"segundos": None}


def test_estimar_con_un_material_que_no_existe_devuelve_null(cliente, tmp_path):
    fuente_id = fuente_de(cliente, tmp_path)

    respuesta = cliente.post("/api/estimar", json={
        "fuente_id": fuente_id, "params": {"material": "no-existe"},
    })

    assert respuesta.json() == {"segundos": None}


def test_estimar_exige_el_token(cliente):
    respuesta = cliente.post(
        "/api/estimar",
        json={"fuente_id": "x", "params": {"material": "mdf18"}},
        headers={"X-Token": "otro"},
    )

    assert respuesta.status_code == 401
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_consultas.py tests/app/test_corredor.py tests/app/test_api_trabajos.py -v`
Expected: FAIL. `test_consultas.py` con `ImportError: cannot import name 'probe_query_seconds'`;
los de `test_corredor.py` con `AttributeError: module 'nesting_app.corredor' has no attribute 'estimar_segundos'`;
los de `/api/estimar` con `405 != 200` (la ruta no existe y cae en el montaje estático).
`test_estimar_exige_el_token` puede pasar ya: el middleware corta todo `/api/`.

- [ ] **Step 3: Escribir `probe_query_seconds`**

En `src/nesting/engine/packer.py`, inmediatamente antes de `def pack(`,
agregar:

```python
def probe_query_seconds(
    parts: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    clock: Callable[[], float] = time.perf_counter,
) -> float | None:
    """Cuánto tarda UNA consulta en esta máquina, con estas opciones.

    Pregunta por la pieza más grande, en la primera orientación que la veta
    de la placa del Material permite, sobre una placa vacía. Incluye
    rasterizar la máscara si el oráculo lo hace: quien llama pasa una
    fábrica con caché nueva para que así sea, porque la corrida real también
    rasteriza cada orientación la primera vez. `reset` queda afuera del
    tiempo: se paga una vez por placa, no por consulta.

    Una sola consulta y no un promedio: tarda menos de un segundo, y el
    número vale en cualquier máquina porque se mide en ella. Devuelve `None`
    si no hay piezas o si la veta no deja ninguna orientación.
    """
    if not parts:
        return None
    choices = orientations(supply.stock, config)
    if not choices:
        return None
    part = max(parts, key=lambda p: p.area)
    oracle = oracle_factory()
    oracle.reset(supply.stock.width, supply.stock.height, config)
    angle, mirror = choices[0]
    started = clock()
    oracle.best_placement(part, angle, mirror)
    return clock() - started
```

- [ ] **Step 4: Escribir la estimación en el corredor**

En `src/nesting_app/corredor.py`, cambiar los imports:

```python
from nesting.engine.packer import (
    Avance,
    Cancelado,
    initial_forecast,
    layout_cost,
    pack,
    probe_query_seconds,
    replicate,
)
```

```python
from nesting.params import NestParams, a_config, a_supply, validar
```

```python
from nesting_app.jobs import ERRORES_DEL_USUARIO, Resultado
```

Después de `NOMBRE_DIAGNOSTICO = "diagnostico.png"`, agregar:

```python
FACTOR_LLENO = 1.5
"""Cuánto más cara es, en promedio, una consulta de la corrida que la de la prueba.

La prueba de `estimar_segundos` pregunta sobre una placa VACÍA, y una placa
vacía es el caso más barato: el árbitro exacto (`engine/exact.py`) verifica
candidatos contra las piezas ya colocadas, y ahí no hay ninguna. A medida
que la placa se llena, cada consulta verifica más candidatos contra más
vecinos. Este factor lleva el costo de la prueba al costo medio de una
consulta de la corrida.

PROVISIONAL. 1.5 es un valor de arranque para poder escribir los tests. La
calibración (`bench/calibrate.py --factor-lleno`) lo reemplaza por el
medido, con las mediciones acá mismo.
"""
```

Y después de la función `analizar`, agregar:

```python
def estimar_segundos(piezas, supply, config) -> float | None:
    """Cuántos segundos va a tardar `pack(piezas, supply, config, ...)`, antes de correrlo.

        segundos = segundos_por_consulta_medido
                   * consultas_previstas_al_arrancar
                   * FACTOR_LLENO

    La prueba usa una caché de máscaras nueva, así que incluye rasterizar;
    ver `probe_query_seconds`.
    """
    por_consulta = probe_query_seconds(
        piezas, supply, config, lambda: RasterOracle(cache=MaskCache())
    )
    if por_consulta is None:
        return None
    return por_consulta * initial_forecast(piezas, supply, config) * FACTOR_LLENO


def estimar(fuente: Fuente, params: NestParams) -> float | None:
    """La estimación previa de un acomodo, o `None` si no se puede estimar.

    Recorre lo mismo que `acomodar` hasta tener las piezas -- leer, preparar,
    descartar el contorno de la placa, replicar -- y no escribe nada.
    Todo lo que `jobs.ERRORES_DEL_USUARIO` llama "tu archivo o tus
    parámetros tienen un problema" da `None`: la pantalla no muestra nada, y
    el error de verdad lo va a dar Acomodar, con su cartel. Un bug del
    programa no está en esa tupla y sale como tal.
    """
    try:
        material = materials_store.leer().get(params.material)
        if material is None:
            return None
        validar(params, material)
        drawing = _leer(fuente, params.unidades)
        piezas, _, _ = prepare_parts(drawing, chain_tol=params.tol_cierre)
        piezas, _ = discard_plate_outline(piezas, material.sheet_w, material.sheet_h)
        return estimar_segundos(
            replicate(piezas, params.copias),
            a_supply(params, material),
            a_config(params),
        )
    except ERRORES_DEL_USUARIO:
        return None
```

(`UnidadesNoDeclaradasError` hereda de `ValueError`, que está en la tupla.)

- [ ] **Step 5: Agregar la ruta**

En `src/nesting_app/api.py`, dentro de `crear_app`, inmediatamente antes de
la sección `# --- trabajos ---`, agregar:

```python
    # --- estimación ---------------------------------------------------------

    @app.post("/api/estimar")
    def estimar(pedido: PedidoTrabajo) -> dict:
        """Cuánto va a tardar el acomodo, antes de arrancarlo.

        Recibe exactamente lo mismo que `POST /api/trabajos`, así que todo
        parámetro nuevo de la corrida -- la veta, los recortes -- entra en la
        estimación sin tocar esta ruta. Una fuente que no existe es un
        `null` y no un 404: la pantalla pide la estimación cada vez que
        cambia una opción, y no tiene nada que mostrar en ese caso.
        """
        try:
            fuente = deposito.obtener(pedido.fuente_id)
        except FuenteDesconocidaError:
            return {"segundos": None}
        return {"segundos": corredor.estimar(fuente, pedido.params.a_params())}
```

- [ ] **Step 6: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_consultas.py tests/app/test_corredor.py tests/app/test_api_trabajos.py -v`
Expected: PASS

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/engine/packer.py src/nesting_app/corredor.py src/nesting_app/api.py tests/engine/test_consultas.py tests/app/test_corredor.py tests/app/test_api_trabajos.py
git commit -m "Estimación previa: una consulta de prueba por la previsión, y la ruta /api/estimar"
```

---

### Task 6: Calibrar `FACTOR_LLENO` sobre el bench

`bench/calibrate.py` gana la medición: por cada archivo, la prueba de una
consulta, la previsión de arranque, las consultas y los segundos reales, y
el factor `segundos_por_consulta_real / segundos_por_consulta_de_la_prueba`.
La mediana de los factores va a `FACTOR_LLENO`, con la tabla en su
docstring. Y un test fija que la estimación previa cae dentro de ×2 del
tiempo real sobre un archivo chico.

**Los números del Step 6 son datos a medir, no huecos del plan.** El plan no
puede traerlos porque salen de correr el bench en la máquina donde se
ejecuta; lo que sí trae es el comando exacto, el formato en que se anotan y
los rangos esperados para detectar una medición rota.

**Files:**
- Modify: `bench/calibrate.py`
- Modify: `src/nesting_app/corredor.py` (`FACTOR_LLENO` y su docstring)
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `probe_query_seconds`, `initial_forecast`, `orientations`, `pack` (Tareas 3 y 5); `corredor.estimar_segundos` (Tarea 5); `VETA_LIBRE`, `VETA_RESPETAR` (plan de veta).
- Produces:
  - En `bench/calibrate.py`: `_parts_of(path: Path, copies: int = 1) -> list[Part]`, `FILA_FACTOR: str`, `measure_fill_factor(files: list[Path], material: Material, config: NestConfig, copies: int = 1) -> list[tuple]` — cada fila `(archivo, piezas, orientaciones, previstas al arrancar, consultas reales, s/consulta de la prueba, s/consulta real, factor, s reales)`.
  - Modo `bench/calibrate.py --factor-lleno` con `--sep`, `--borde`, `--resolucion`, `--esfuerzo`, `--posiciones`, `--veta`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_calibration.py`, agregar `_parts_of` y `measure_fill_factor`
al import de `calibrate`, y estos imports:

```python
from nesting.engine.packer import pack  # noqa: E402
from nesting.engine.raster.masks import MaskCache  # noqa: E402
from nesting.engine.raster.oracle import RasterOracle  # noqa: E402
from nesting.model.sheet import SheetSupply  # noqa: E402
from nesting_app import corredor  # noqa: E402
```

Y al final del archivo:

```python
def test_la_medicion_del_factor_lleno_da_una_fila_por_archivo(tmp_path):
    config = NestConfig(sep=6.0, margin=10.0, effort="rapido", resolution=4.0)

    rows = measure_fill_factor(sample(tmp_path), MATERIAL, config)

    assert len(rows) == 1
    nombre, piezas, orientaciones, previstas, reales, prueba, real, factor, segundos = rows[0]
    assert nombre == "muestra.dxf"
    assert piezas == 12
    assert orientaciones == 8
    assert previstas > 0 and reales > 0
    assert prueba > 0 and real > 0 and segundos > 0
    assert factor == real / prueba


def test_la_estimacion_previa_cae_dentro_de_por_dos_del_tiempo_real(tmp_path):
    """Spec, 4: la estimación previa cae dentro de x2 del tiempo real sobre
    un archivo chico. La muestra sintética: 12 piezas, una placa."""
    parts = _parts_of(sample(tmp_path)[0])
    supply = SheetSupply(stock=MATERIAL.stock_sheet(), material_name=MATERIAL.name)
    config = NestConfig(sep=6.0, margin=10.0, effort="rapido", resolution=2.0)

    estimado = corredor.estimar_segundos(parts, supply, config)
    cache = MaskCache()
    real = pack(parts, supply, config, lambda: RasterOracle(cache=cache)).seconds

    assert estimado / 2 <= real <= estimado * 2, (
        f"estimado {estimado:.2f} s, real {real:.2f} s"
    )
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/test_calibration.py -v`
Expected: FAIL con `ImportError: cannot import name '_parts_of' from 'calibrate'` (el módulo de tests entero no carga).

- [ ] **Step 3: Escribir la medición en `bench/calibrate.py`**

Agregar a los imports de arriba:

```python
import statistics
```

```python
from nesting.engine.packer import (
    initial_forecast,
    orientations,
    pack,
    probe_query_seconds,
    replicate,
)
from nesting.engine.raster.masks import MaskCache
from nesting.model.material import VETA_LIBRE, VETA_RESPETAR
from nesting.model.sheet import SheetSupply
```

y cambiar el import de `run_bench` a:

```python
from run_bench import FILE_ERRORS, FILES_DIR, run_one  # noqa: E402
```

Después de `compare_engines`, agregar:

```python
def _parts_of(path: Path, copies: int = 1) -> list:
    """Las piezas de un archivo del banco, replicadas `copies` veces."""
    from nesting.io.ai_reader import read_ai
    from nesting.io.dxf_reader import read_dxf
    from nesting.pipeline import prepare_parts

    drawing = read_ai(path) if path.suffix.lower() == ".ai" else read_dxf(path)
    parts, _, _ = prepare_parts(drawing)
    return replicate(parts, copies)


FILA_FACTOR = (
    "archivo, piezas, orientaciones, consultas previstas al arrancar, "
    "consultas reales, s/consulta de la prueba, s/consulta real, factor, s reales"
)
"""Forma de las filas de `measure_fill_factor`, en orden.

El factor es `s/consulta real / s/consulta de la prueba`: lo que
`nesting_app.corredor.FACTOR_LLENO` corrige. La previsión de arranque va al
lado para ver cuánto del error de la estimación previa es de la previsión
de consultas y cuánto del costo por consulta; el factor corrige sólo lo
segundo.
"""


def measure_fill_factor(
    files: list[Path], material: Material, config: NestConfig, copies: int = 1
) -> list[tuple]:
    """Una fila con la forma de `FILA_FACTOR` por cada archivo que se pudo medir."""
    rows = []
    for path in files:
        parts = _parts_of(path, copies)
        supply = SheetSupply(stock=material.stock_sheet(), material_name=material.name)
        probe = probe_query_seconds(
            parts, supply, config, lambda: RasterOracle(cache=MaskCache())
        )
        if probe is None:
            print(f"aviso: {path.name} no deja ninguna orientación con esta veta; se salta")
            continue
        forecast = initial_forecast(parts, supply, config)
        avances = []
        cache = MaskCache()
        try:
            result = pack(
                parts, supply, config, lambda: RasterOracle(cache=cache),
                progreso=lambda a: avances.append(a) or True,
            )
        except FILE_ERRORS as error:
            print(f"aviso: {path.name} no se pudo acomodar ({type(error).__name__}: {error}); se salta")
            continue
        real = avances[-1].consultas_hechas
        per_query = result.seconds / real
        rows.append((
            path.name, len(parts), len(orientations(supply.stock, config)),
            forecast, real, probe, per_query, per_query / probe, result.seconds,
        ))
    return rows


def _main_factor_lleno(args, material: Material, files: list[Path]) -> int:
    """El modo `--factor-lleno`: sólo mide, imprime la tabla y la mediana."""
    if args.veta is not None:
        material = replace(
            material,
            grain_tolerance=VETA_LIBRE if args.veta == "libre" else VETA_RESPETAR,
        )
    angles = tuple(i * 360.0 / args.posiciones for i in range(args.posiciones))
    config = NestConfig(
        sep=args.sep, margin=args.borde, angles=angles, mirror=True,
        resolution=args.resolucion, effort=args.esfuerzo,
    )
    print(
        f"FACTOR_LLENO  ({material.name}, veta {material.grain_tolerance:g} grados, "
        f"{args.posiciones} posiciones con espejo, sep {args.sep:g}, borde {args.borde:g}, "
        f"{args.resolucion:g} mm/px, esfuerzo {args.esfuerzo}, --copias {args.copias})"
    )
    print(
        f"{'archivo':<28}{'piezas':>7}{'orient.':>8}{'previstas':>10}{'reales':>8}"
        f"{'s/c prueba':>11}{'s/c real':>10}{'factor':>8}{'s reales':>10}"
    )
    print("-" * 100)
    rows = measure_fill_factor(files, material, config, copies=args.copias)
    for r in rows:
        print(
            f"{r[0]:<28}{r[1]:>7}{r[2]:>8}{r[3]:>10}{r[4]:>8}"
            f"{r[5]:>11.4f}{r[6]:>10.4f}{r[7]:>8.2f}{r[8]:>10.1f}"
        )
    if not rows:
        print("no se pudo medir ningún archivo", file=sys.stderr)
        return 1
    print(f"\n-> mediana del factor: {statistics.median(r[7] for r in rows):.2f}")
    print("Anotarla en src/nesting_app/corredor.py::FACTOR_LLENO con esta tabla al lado.")
    return 0
```

En `main`, agregar después de `parser.add_argument("--copias", ...)`:

```python
    parser.add_argument(
        "--factor-lleno", action="store_true",
        help="mide sólo FACTOR_LLENO (src/nesting_app/corredor.py); las opciones "
             "de abajo valen sólo en este modo",
    )
    parser.add_argument("--sep", type=float, default=6.0)
    parser.add_argument("--borde", type=float, default=10.0)
    parser.add_argument("--resolucion", type=float, default=1.0)
    parser.add_argument("--esfuerzo", choices=EFFORT_LEVELS, default="normal")
    parser.add_argument("--posiciones", type=int, default=4)
    parser.add_argument("--veta", choices=("respetar", "libre"), default=None)
```

y después del `if not files: ... return 1`, agregar:

```python
    if args.factor_lleno:
        return _main_factor_lleno(args, material, files)
```

- [ ] **Step 4: Correr los tests nuevos**

Run: `.venv/bin/pytest tests/test_calibration.py -v`
Expected: PASS. Con el 1.5 provisional, la muestra dio 2,06 s estimados
contra 2,43 s reales al escribir este plan.

- [ ] **Step 5: Correr la calibración**

Asegurarse de que la muestra sintética esté en el bench:

```bash
.venv/bin/python bench/make_sample.py
ls bench/files
```

Expected: al menos `muestra.dxf`; idealmente también `banqueta-alta.ai` y
`banqueta final raulo.ai`. Si falta `banqueta-alta.ai`, parar y pedirlo: es
el archivo sobre el que la spec midió 126 s y 651 s, y calibrar sin él deja
el factor medido sólo sobre la muestra sintética.

Correr las dos configuraciones de la spec, en este orden (juntas tardan del
orden de 20 a 30 minutos; la de 8 posiciones es la larga, la banqueta sola
tardó 651 s):

```bash
.venv/bin/python bench/calibrate.py --factor-lleno --material multilam18 \
  --sep 8 --borde 5 --resolucion 1 --esfuerzo normal --posiciones 4
```

```bash
.venv/bin/python bench/calibrate.py --factor-lleno --material multilam18 \
  --sep 8 --borde 5 --resolucion 1 --esfuerzo normal --posiciones 8 --veta libre
```

Expected: cada comando imprime una tabla con una fila por archivo y
`-> mediana del factor: X.XX`. Chequeos de cordura antes de anotar:

- La fila de `banqueta-alta.ai` con 4 posiciones tiene `orient.` 4 y
  `s reales` del orden de 126; con 8 posiciones y veta libre, `orient.` 16 y
  `s reales` del orden de 651. Si se van a más del doble, la corrida no es
  la de la spec: revisar sep, borde, resolución y material antes de seguir.
- Cada factor cae entre 0,8 y 3,0 (medido al escribir el plan: ~1,2 a
  1 mm/px sobre la banqueta). Un factor fuera de ese rango, o una fila con
  `aviso: ... se salta` para `banqueta-alta.ai`, es una medición rota:
  parar y avisar con la salida completa, sin anotar nada.

- [ ] **Step 6: Anotar el valor medido y la tabla**

En `src/nesting_app/corredor.py`, reemplazar el valor y el docstring de
`FACTOR_LLENO`. El valor es la mediana de TODOS los factores de las dos
tablas juntas (calcularla a mano sobre las filas; no es el promedio de las
dos medianas impresas). El docstring tiene exactamente esta forma, con las
dos tablas copiadas tal cual las imprimió cada comando, encabezado incluido,
y la fecha del día de la medición:

```python
FACTOR_LLENO = <la mediana de los factores de las dos tablas, con dos decimales>
"""Cuánto más cara es, en promedio, una consulta de la corrida que la de la prueba.

La prueba de `estimar_segundos` pregunta sobre una placa VACÍA, y una placa
vacía es el caso más barato: el árbitro exacto (`engine/exact.py`) verifica
candidatos contra las piezas ya colocadas, y ahí no hay ninguna. A medida
que la placa se llena, cada consulta verifica más candidatos contra más
vecinos. Este factor lleva el costo de la prueba al costo medio de una
consulta de la corrida.

MEDIDO EL <AAAA-MM-DD> con `bench/calibrate.py --factor-lleno` sobre
`bench/files/*` (multilam18, sep 8, borde 5, 1 mm/px, esfuerzo normal), en
la máquina del taller:

    <la tabla completa que imprimió el comando de 4 posiciones>

    <la tabla completa que imprimió el comando de 8 posiciones y veta libre>

Se usa la mediana de los factores de las dos tablas juntas, y no el
promedio, para que un archivo raro no mueva la estimación de todos. El
factor corrige sólo el costo por consulta: el error de la previsión de
consultas de arranque (columnas "previstas" contra "reales") es aparte, y
la previsión se corrige sola apenas termina el primer intento.

Para volver a medir: correr los dos comandos de arriba (ver
`bench/calibrate.py --help`) y reemplazar las dos tablas y el valor.
"""
```

Los `<...>` de este bloque son los datos que salen del Step 5, y **ninguno
puede quedar sin reemplazar**: un `<` en el archivo es un paso sin terminar.
Verificarlo:

```bash
grep -n "<la \|<AAAA" src/nesting_app/corredor.py
```

Expected: ninguna línea.

- [ ] **Step 7: Volver a correr la cota de ×2 con el valor medido, y la suite entera**

Run: `.venv/bin/pytest tests/test_calibration.py -v`
Expected: PASS. Si `test_la_estimacion_previa_cae_dentro_de_por_dos_del_tiempo_real`
falla con el valor medido: **no aflojar el ×2, que es de la spec, ni
retocar el factor para que pase.** Anotar el estimado y el real que imprime
el mensaje y parar a avisar: quiere decir que el costo por consulta de un
archivo chico se separa del de los grandes, y eso es una decisión de diseño.

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 8: Commit**

```bash
git add bench/calibrate.py src/nesting_app/corredor.py tests/test_calibration.py
git commit -m "Calibración: FACTOR_LLENO medido sobre el bench, con la tabla al lado"
```

---

### Task 7: La pantalla dice cuánto falta mientras corre

Debajo del texto de avance aparece "Calculando el tiempo…" hasta que el
servidor tiene datos, y después "Faltan aprox. 9 min · termina ~17:42".

Redondeo (spec, 3.1), en minutos, con 0 para "menos de 2 min":

| restante | minutos | ejemplo |
|---|---|---|
| menos de 120 s | 0 | "Faltan menos de 2 min" |
| de 120 a 600 s | de a 1 | 540 s: 9 |
| más de 600 s | de a 5, al menos 10 | 749 s: 10; 750 s: 15 |

"Menos de 2 min" va sin "aprox." y sin hora de fin: "termina ~17:42" a
partir de un 0 diría que ya terminó.

Estabilidad: el número mostrado baja libremente, y sólo sube si los
valores más altos se sostienen 5 segundos seguidos; un valor que vuelve a
quedar igual o por debajo reinicia la espera. La hora de fin se calcula
con el reloj local a partir del número ya estabilizado.

**Files:**
- Modify: `src/nesting_app/web/index.html` (barra de abajo)
- Modify: `src/nesting_app/web/app.js` (`estado`, funciones nuevas después de `textoDeAvance`, `corriendo`, `btn-acomodar`, `sondear`, `registrar`)
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: `restante_s` en el JSON del trabajo (Tarea 4).
- Produces (en `app.js`): `minutosRedondeados(segundos) -> number`, `textoDeRestante(minutos, ahora: Date) -> string`, `SUBIDA_SOSTENIDA_MS = 5000`, `estabilizar(previo, nuevo, ahora) -> {mostrado, subidaDesde}`, `actualizarRestante(restanteS)`, `estado.restante`; id `texto-restante` en `index.html`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/app/test_web_javascript.py`, agregar a los imports de arriba:

```python
import json
import shutil
import subprocess
```

Y al final del archivo:

```python
# --- tiempo restante ---------------------------------------------------------

requiere_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="estos casos corren las funciones de app.js de verdad y necesitan "
           "`node` en el PATH; los tests de texto de la misma función siguen "
           "corriendo sin él",
)


def _evaluar_en_node(js: str, funciones: list[str], constantes: list[str], expresion: str):
    """Arma un programa con las `constantes` y las `funciones` de `js`, tal
    como están en el archivo y sin comentarios, y devuelve lo que evalúa
    `expresion`, pasado por JSON.

    Las funciones salen de `_cuerpo_de_funcion`, que corta justo antes del
    `}` que las cierra: se lo devuelve acá. Las constantes tienen que estar
    declaradas en una sola línea, `const NOMBRE = valor;`."""
    limpio = _sin_comentarios(js)
    partes = []
    for nombre in constantes:
        hallazgo = re.search(rf"^const {nombre} = [^;\n]+;", limpio, re.M)
        if not hallazgo:
            pytest.fail(f"app.js ya no declara `const {nombre} = ...;` en una sola línea")
        partes.append(hallazgo.group(0))
    for nombre in funciones:
        partes.append(_cuerpo_de_funcion(js, nombre) + "\n}")
    partes.append(f"process.stdout.write(JSON.stringify({expresion}));")
    proceso = subprocess.run(
        ["node", "-e", "\n".join(partes)], capture_output=True, text=True, timeout=30
    )
    if proceso.returncode != 0:
        pytest.fail(f"node no pudo correr el programa armado:\n{proceso.stderr}")
    return json.loads(proceso.stdout)


def test_el_restante_tiene_su_lugar_en_la_barra_de_abajo(html):
    pie = html[html.index('<footer class="barra-accion">'):html.index("</footer>")]
    assert 'id="texto-restante"' in pie
    assert pie.index('id="texto-avance"') < pie.index('id="texto-restante"'), (
        "el tiempo va debajo del avance, no arriba"
    )
    assert re.search(r'id="texto-restante"[^>]*class="texto-avance oculto"', pie)


def test_sondear_le_pasa_el_restante_a_la_pantalla(js):
    assert "actualizarRestante(t.restante_s)" in _cuerpo_de_funcion(js, "sondear")


def test_sin_datos_dice_que_esta_calculando(js):
    cuerpo = _cuerpo_de_funcion(js, "actualizarRestante")
    assert "Calculando el tiempo…" in cuerpo
    assert 'typeof restanteS !== "number"' in cuerpo


def test_con_datos_redondea_estabiliza_y_escribe(js):
    cuerpo = _cuerpo_de_funcion(js, "actualizarRestante")
    assert "estabilizar(estado.restante, minutosRedondeados(restanteS)" in cuerpo
    assert "textoDeRestante(estado.restante.mostrado" in cuerpo


def test_el_restante_se_ve_solo_mientras_corre(js):
    assert '$("texto-restante").classList.toggle("oculto", !si)' in _cuerpo_de_funcion(
        js, "corriendo"
    )


def test_registrar_olvida_el_restante_del_trabajo_anterior(js):
    cuerpo = _cuerpo_de_funcion(js, "registrar")
    assert "estado.restante = null" in cuerpo
    assert '$("texto-restante").classList.add("oculto")' in cuerpo


def test_acomodar_arranca_el_restante_de_cero(js):
    """Sin esto, el número estabilizado del trabajo anterior -- que sólo baja
    libremente -- se quedaría mostrando un tiempo viejo hasta 5 segundos."""
    limpio = _sin_comentarios(js)
    inicio = limpio.index('$("btn-acomodar").onclick')
    fin = limpio.index('$("btn-cancelar").onclick')
    handler = limpio[inicio:fin]
    assert "estado.restante = null" in handler
    assert handler.index("estado.restante = null") < handler.index("corriendo(true)")


def test_el_redondeo_tiene_los_cortes_de_la_spec(js):
    cuerpo = _cuerpo_de_funcion(js, "minutosRedondeados")
    assert "segundos < 120" in cuerpo
    assert "segundos <= 600" in cuerpo
    assert "/ 300) * 5" in cuerpo


@requiere_node
def test_el_redondeo_caso_por_caso(js):
    casos = {
        0: 0, 119: 0, 120: 2, 149: 2, 150: 3, 540: 9, 600: 10,
        601: 10, 749: 10, 750: 15, 900: 15, 3600: 60,
    }
    obtenidos = _evaluar_en_node(
        js, ["minutosRedondeados"], [],
        f"{list(casos)}.map(minutosRedondeados)",
    )
    assert dict(zip(casos, obtenidos)) == casos


@requiere_node
def test_el_texto_del_restante_con_su_hora_de_fin(js):
    obtenidos = _evaluar_en_node(
        js, ["textoDeRestante"], [],
        "[textoDeRestante(9, new Date(2026, 8, 22, 17, 33)),"
        " textoDeRestante(15, new Date(2026, 8, 22, 23, 50)),"
        " textoDeRestante(0, new Date(2026, 8, 22, 17, 33))]",
    )
    assert obtenidos == [
        "Faltan aprox. 9 min · termina ~17:42",
        "Faltan aprox. 15 min · termina ~00:05",
        "Faltan menos de 2 min",
    ]


@requiere_node
def test_el_numero_baja_libre_y_sube_solo_si_se_sostiene(js):
    """Spec, 3.1: un número que salta de 8 a 12 y vuelve a 8 es peor que
    uno que se queda en 8."""
    mostrados = _evaluar_en_node(
        js, ["estabilizar"], ["SUBIDA_SOSTENIDA_MS"],
        """(() => {
          const vistos = [];
          let e = estabilizar(null, 8, 0);           vistos.push(e.mostrado);
          e = estabilizar(e, 12, 1000);              vistos.push(e.mostrado);
          e = estabilizar(e, 8, 2000);               vistos.push(e.mostrado);
          e = estabilizar(e, 12, 3000);              vistos.push(e.mostrado);
          e = estabilizar(e, 11, 7999);              vistos.push(e.mostrado);
          e = estabilizar(e, 12, 8000);              vistos.push(e.mostrado);
          e = estabilizar(e, 6, 8100);               vistos.push(e.mostrado);
          return vistos;
        })()""",
    )
    assert mostrados == [8, 8, 8, 8, 8, 12, 6]


def test_la_subida_se_sostiene_cinco_segundos(js):
    assert re.search(r"^const SUBIDA_SOSTENIDA_MS = 5000;", _sin_comentarios(js), re.M)
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -k "restante or redondeo or sostiene or baja_libre or calculando" -v`
Expected: FAIL. Los que usan `_cuerpo_de_funcion` con su `pytest.fail`
de "ya no declara `actualizarRestante`" (o `minutosRedondeados`, etc.; el
mensaje nombra `info.js` porque el helper se escribió para ese archivo, pero
la función que busca es la de `app.js`), y el del HTML con `AssertionError`.

- [ ] **Step 3: Agregar el lugar en la barra de abajo**

En `src/nesting_app/web/index.html`, dentro de `<div class="estado">`,
inmediatamente después de
`<p id="texto-avance" class="texto-avance oculto"></p>`, agregar:

```html
    <p id="texto-restante" class="texto-avance oculto"></p>
```

- [ ] **Step 4: Escribir las funciones del tiempo**

En `src/nesting_app/web/app.js`, dentro del objeto `estado`, después de
`recortes: [],`, agregar:

```js
  // El último número de minutos que se mostró, y desde cuándo el servidor
  // viene diciendo uno más alto. Ver `estabilizar()`.
  restante: null,
```

Inmediatamente después de la función `textoDeAvance`, agregar:

```js
// --- tiempo -----------------------------------------------------------------

// Para no fingir una precisión que no hay: de a 5 minutos arriba de 10, de
// a 1 entre 2 y 10, y abajo de 2 un "menos de 2 min", que acá es el 0. La
// hora de fin sale de este número ya redondeado y no del crudo, para que
// "9 min" y "termina ~17:42" cierren entre sí.
function minutosRedondeados(segundos) {
  if (segundos < 120) return 0;
  if (segundos <= 600) return Math.round(segundos / 60);
  return Math.max(10, Math.round(segundos / 300) * 5);
}

// Con 0 no hay hora de fin: "termina ~17:33" a las 17:33 diría que ya
// terminó.
function textoDeRestante(minutos, ahora) {
  if (minutos === 0) return "Faltan menos de 2 min";
  const fin = new Date(ahora.getTime() + minutos * 60000);
  const hh = String(fin.getHours()).padStart(2, "0");
  const mm = String(fin.getMinutes()).padStart(2, "0");
  return `Faltan aprox. ${minutos} min · termina ~${hh}:${mm}`;
}

const SUBIDA_SOSTENIDA_MS = 5000;

// El número mostrado baja libremente, pero sólo sube si los valores más
// altos se sostienen 5 segundos seguidos. Un número que salta de 8 a 12 y
// vuelve a 8 es peor que uno que se queda en 8: la gente planifica con él.
function estabilizar(previo, nuevo, ahora) {
  if (!previo || nuevo <= previo.mostrado) return { mostrado: nuevo, subidaDesde: null };
  const desde = previo.subidaDesde ?? ahora;
  if (ahora - desde >= SUBIDA_SOSTENIDA_MS) return { mostrado: nuevo, subidaDesde: null };
  return { mostrado: previo.mostrado, subidaDesde: desde };
}

// El servidor manda `null` durante los primeros 5 segundos o las primeras
// 20 consultas: antes de eso no hay datos, y un número inventado es peor
// que decir que se está calculando.
function actualizarRestante(restanteS) {
  if (typeof restanteS !== "number") {
    $("texto-restante").textContent = "Calculando el tiempo…";
    return;
  }
  estado.restante = estabilizar(estado.restante, minutosRedondeados(restanteS), Date.now());
  $("texto-restante").textContent = textoDeRestante(estado.restante.mostrado, new Date());
}
```

- [ ] **Step 5: Conectarlas**

En `corriendo(si)`, después de la línea de `texto-avance`, agregar:

```js
  $("texto-restante").classList.toggle("oculto", !si);
```

En el handler de `$("btn-acomodar").onclick`, dentro del `try`, reemplazar:

```js
    estado.trabajoId = creado.id;
    corriendo(true);
```

por:

```js
    estado.trabajoId = creado.id;
    estado.restante = null;
    $("texto-restante").textContent = "Calculando el tiempo…";
    corriendo(true);
```

En `sondear()`, inmediatamente después de
`if (t.avance) $("texto-avance").textContent = textoDeAvance(t.avance);`,
agregar:

```js
  if (t.estado === "corriendo") actualizarRestante(t.restante_s);
```

En `registrar()`, después de `$("texto-avance").classList.add("oculto");`,
agregar:

```js
  $("texto-restante").classList.add("oculto");
  estado.restante = null;
```

- [ ] **Step 6: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -v`
Expected: PASS. Sin `node` en el PATH, los tres casos `@requiere_node`
salen `SKIPPED` con el motivo y el resto pasa.

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos. `test_todo_id_que_busca_el_js_existe_en_el_html`
cubre `texto-restante`, y `test_no_hay_emojis_en_la_interfaz` sigue verde.

- [ ] **Step 7: Commit**

```bash
git add src/nesting_app/web/index.html src/nesting_app/web/app.js tests/app/test_web_javascript.py
git commit -m "Pantalla: cuánto falta y a qué hora termina, redondeado y sin saltos"
```

---

### Task 8: La pantalla dice cuánto va a tardar antes de arrancar

Al lado de Acomodar aparece "Tarda aprox. 10 min" (o "Tarda menos de
2 min"), con el mismo redondeo de la Tarea 7. Se recalcula 400 ms después
del último cambio en Posiciones, Ángulos, espejo, Esfuerzo, Resolución,
Material, Veta, Copias o Recortes, y cuando se termina de analizar un
archivo. Mientras calcula deja el valor anterior; si la ruta devuelve
`null` o falla, no muestra nada. No se pide mientras corre un trabajo: la
prueba de una consulta le robaría CPU, y el número no cambia porque las
opciones de un trabajo corriendo ya están fijadas.

**Files:**
- Modify: `src/nesting_app/web/index.html` (al lado de Acomodar)
- Modify: `src/nesting_app/web/app.js` (sección del tiempo, `corriendo`, `registrar`, `analizar`, `dibujarRecortes`)
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: `POST /api/estimar` (Tarea 5); `minutosRedondeados` (Tarea 7); `parametros()`, `postJson`, `estado.fuenteId` (ya existen); los ids `veta-respetar` / `veta-libre` (plan de veta).
- Produces (en `app.js`): `textoDeTarda(minutos) -> string`, `ESPERA_ESTIMACION_MS = 400`, `CONTROLES_QUE_PESAN`, `pedirEstimacion()`, `calcularEstimacion()`, `mostrarEstimacion(segundos)`; id `tiempo-estimado` en `index.html`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/app/test_web_javascript.py`, agregar al final:

```python
# --- tiempo estimado antes de arrancar ----------------------------------------

CONTROLES_QUE_PESAN = [
    "posiciones", "angulos", "espejo", "esfuerzo", "resolucion",
    "material", "veta-respetar", "veta-libre", "copias",
]
"""Spec, 3.2: Posiciones, Ángulos, espejo, Esfuerzo, Resolución, Material,
Veta, Copias. Recortes no tiene un control: se engancha en `dibujarRecortes`."""


def test_el_tiempo_estimado_va_al_lado_de_acomodar(html):
    pie = html[html.index('<footer class="barra-accion">'):html.index("</footer>")]
    acomodar = pie.index('id="btn-acomodar"')
    estimado = pie.index('id="tiempo-estimado"')
    cancelar = pie.index('id="btn-cancelar"')
    assert acomodar < estimado < cancelar
    assert re.search(r'id="tiempo-estimado"[^>]*class="texto-avance oculto"', pie)


def test_usa_la_ruta_de_estimar(js):
    assert '"/api/estimar"' in _cuerpo_de_funcion(js, "calcularEstimacion")


def test_la_estimacion_manda_lo_mismo_que_acomodar(js):
    cuerpo = _cuerpo_de_funcion(js, "calcularEstimacion")
    assert "fuente_id: estado.fuenteId" in cuerpo
    assert "params: parametros()" in cuerpo


def test_una_estimacion_que_llega_tarde_se_descarta(js):
    """Dos cambios seguidos disparan dos pedidos que pueden volver en
    cualquier orden. Sin el número, el viejo pisaría al nuevo."""
    cuerpo = _cuerpo_de_funcion(js, "calcularEstimacion")
    assert "++numeroDeEstimacion" in cuerpo
    assert "numero !== numeroDeEstimacion" in cuerpo


def test_no_se_estima_sin_archivo_ni_mientras_corre(js):
    cuerpo = _cuerpo_de_funcion(js, "calcularEstimacion")
    assert "!estado.fuenteId" in cuerpo
    assert '$("btn-acomodar").classList.contains("oculto")' in cuerpo


def test_si_la_ruta_falla_no_se_muestra_nada(js):
    cuerpo = _cuerpo_de_funcion(js, "calcularEstimacion")
    assert "catch" in cuerpo
    assert "mostrarError" not in cuerpo, "un 422 al tipear no merece un cartel"


def test_sin_numero_la_estimacion_se_esconde(js):
    cuerpo = _cuerpo_de_funcion(js, "mostrarEstimacion")
    assert 'typeof segundos !== "number"' in cuerpo
    assert 'classList.add("oculto")' in cuerpo
    assert "textoDeTarda(minutosRedondeados(segundos))" in cuerpo


def test_la_estimacion_espera_cuatrocientos_ms_al_ultimo_cambio(js):
    assert re.search(r"^const ESPERA_ESTIMACION_MS = 400;", _sin_comentarios(js), re.M)
    cuerpo = _cuerpo_de_funcion(js, "pedirEstimacion")
    assert "clearTimeout(temporizadorEstimacion)" in cuerpo
    assert "setTimeout(calcularEstimacion, ESPERA_ESTIMACION_MS)" in cuerpo


def test_los_controles_que_pesan_son_los_de_la_spec_y_existen(js, html):
    hallazgo = re.search(
        r"const CONTROLES_QUE_PESAN = \[([^\]]*)\]", _sin_comentarios(js)
    )
    assert hallazgo, "app.js ya no declara CONTROLES_QUE_PESAN"
    ids = re.findall(r'"([^"]+)"', hallazgo.group(1))
    assert sorted(ids) == sorted(CONTROLES_QUE_PESAN)
    ids_del_html = set(re.findall(r'id="([^"]+)"', html))
    faltantes = set(ids) - ids_del_html
    assert not faltantes, (
        f"ids que la estimación escucha y no están en index.html: {faltantes}. "
        "`$(id)` daría null y la pantalla entera dejaría de cargar"
    )


def test_cada_control_que_pesa_escucha_input_y_change(js):
    """`input` para lo que se tipea (Ángulos, Copias, Resolución), `change`
    para desplegables, casillas y radios."""
    limpio = _sin_comentarios(js)
    bucle = limpio[limpio.index("for (const id of CONTROLES_QUE_PESAN)"):]
    bucle = bucle[:bucle.index("\n}")]
    assert '["input", "change"]' in bucle
    assert "addEventListener(evento, pedirEstimacion)" in bucle


def test_agregar_o_quitar_un_recorte_recalcula(js):
    assert "pedirEstimacion()" in _cuerpo_de_funcion(js, "dibujarRecortes")


def test_terminar_de_analizar_un_archivo_recalcula(js):
    assert "pedirEstimacion()" in _cuerpo_de_funcion(js, "analizar")


def test_la_estimacion_no_se_ve_mientras_corre(js):
    cuerpo = _cuerpo_de_funcion(js, "corriendo")
    assert '$("tiempo-estimado").classList.toggle("oculto", si ||' in cuerpo


def test_registrar_borra_la_estimacion_del_archivo_anterior(js):
    assert "mostrarEstimacion(null)" in _cuerpo_de_funcion(js, "registrar")


@requiere_node
def test_el_texto_de_cuanto_tarda(js):
    obtenidos = _evaluar_en_node(
        js, ["textoDeTarda"], [], "[textoDeTarda(10), textoDeTarda(3), textoDeTarda(0)]"
    )
    assert obtenidos == ["Tarda aprox. 10 min", "Tarda aprox. 3 min", "Tarda menos de 2 min"]
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -k "estim or tarda or pesan or recorte_recalcula or analizar_un_archivo" -v`
Expected: FAIL. Los de `_cuerpo_de_funcion` porque las funciones no
existen; `test_el_tiempo_estimado_va_al_lado_de_acomodar` con `ValueError:
substring not found`; `test_los_controles_que_pesan_son_los_de_la_spec_y_existen`
con "app.js ya no declara CONTROLES_QUE_PESAN".

- [ ] **Step 3: Agregar el lugar al lado de Acomodar**

En `src/nesting_app/web/index.html`, dentro de `<footer class="barra-accion">`,
inmediatamente después del botón `btn-acomodar`, agregar:

```html
  <span id="tiempo-estimado" class="texto-avance oculto"></span>
```

- [ ] **Step 4: Escribir el pedido demorado**

En `src/nesting_app/web/app.js`, inmediatamente después de la función
`actualizarRestante` (Tarea 7), agregar:

```js
function textoDeTarda(minutos) {
  return minutos === 0 ? "Tarda menos de 2 min" : `Tarda aprox. ${minutos} min`;
}

// Quien elige 8 posiciones no sabe que acaba de quintuplicar la espera: la
// banqueta alta tarda 126 s con la veta y 651 s con giro libre y 8
// posiciones. Por eso el número se recalcula al cambiar cualquiera de las
// opciones que pesan, 400 ms después del último cambio para no pedir uno
// por cada tecla.
const ESPERA_ESTIMACION_MS = 400;
const CONTROLES_QUE_PESAN = ["posiciones", "angulos", "espejo", "esfuerzo", "resolucion", "material", "veta-respetar", "veta-libre", "copias"];
let temporizadorEstimacion = null;
let numeroDeEstimacion = 0;

function pedirEstimacion() {
  clearTimeout(temporizadorEstimacion);
  temporizadorEstimacion = setTimeout(calcularEstimacion, ESPERA_ESTIMACION_MS);
}

// Mientras calcula deja el valor anterior. No pide nada sin archivo ni con
// un trabajo corriendo: la prueba de una consulta le robaría CPU al
// trabajo. Un error -- un 422 por un ángulo a medio tipear, un 500 -- no
// abre ningún cartel: es un número de ayuda, y Acomodar va a dar el error
// de verdad si lo hay.
async function calcularEstimacion() {
  if (!estado.fuenteId || $("btn-acomodar").classList.contains("oculto")) return;
  const numero = ++numeroDeEstimacion;
  let segundos = null;
  try {
    const respuesta = await postJson("/api/estimar", {
      fuente_id: estado.fuenteId,
      params: parametros(),
    });
    segundos = respuesta.segundos;
  } catch (_) {
    segundos = null;
  }
  if (numero !== numeroDeEstimacion) return;
  mostrarEstimacion(segundos);
}

function mostrarEstimacion(segundos) {
  const lugar = $("tiempo-estimado");
  if (typeof segundos !== "number") {
    lugar.textContent = "";
    lugar.classList.add("oculto");
    return;
  }
  lugar.textContent = textoDeTarda(minutosRedondeados(segundos));
  lugar.classList.remove("oculto");
}

// El evento va en una variable y no como literal a propósito: los tests
// ubican los handlers en línea por su `addEventListener("change", ...)`, y
// un literal acá les ganaría de mano a los que buscan.
for (const id of CONTROLES_QUE_PESAN) {
  for (const evento of ["input", "change"]) $(id).addEventListener(evento, pedirEstimacion);
}
```

`CONTROLES_QUE_PESAN` tiene que seguir siendo un literal de cadenas entre
comillas dobles: el test lo lee con una expresión regular y compara sus ids
contra la spec y contra `index.html`. Un id que falte en el HTML no es un
detalle: `$(id)` daría `null`, el `addEventListener` reventaría al cargar y
la pantalla entera dejaría de funcionar.

- [ ] **Step 5: Conectarlo**

En `corriendo(si)`, después de la línea de `texto-restante` (Tarea 7),
agregar:

```js
  $("tiempo-estimado").classList.toggle("oculto", si || !$("tiempo-estimado").textContent);
```

En `registrar()`, después de `estado.restante = null;` (Tarea 7), agregar:

```js
  mostrarEstimacion(null);
```

En `analizar()`, dentro del `try`, inmediatamente después de
`mostrarRevision();`, agregar:

```js
    pedirEstimacion();
```

En `dibujarRecortes()`, reemplazar el final de la función:

```js
    fila.append(texto, quitar);
    lista.append(fila);
  });
}
```

por:

```js
    fila.append(texto, quitar);
    lista.append(fila);
  });
  pedirEstimacion();
}
```

(`pedirEstimacion` es una declaración de función, así que existe desde que
carga el archivo; `temporizadorEstimacion` es `let` y sólo existe después de
su línea, pero `dibujarRecortes` y `analizar` corren recién con un clic,
cuando el archivo ya cargó entero.)

- [ ] **Step 6: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -v`
Expected: PASS (con `node`; sin él, los casos `@requiere_node` salen
`SKIPPED`).

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos.

- [ ] **Step 7: Probarlo en la ventana de verdad**

Los tests leen el archivo como texto: no ven si el número aparece. Levantar
la aplicación (`.venv/bin/nest-app`), abrir `bench/files/banqueta-alta.ai`
(o la muestra sintética si no está), y verificar a mano:

1. Después de analizar aparece "Tarda aprox. N min" al lado de Acomodar.
2. Pasar Posiciones de 4 a 8 y Veta a "No importa": el número sube, unas
   cuatro o cinco veces (la spec midió 126 s contra 651 s).
3. Acomodar: el número de al lado desaparece, abajo dice "Calculando el
   tiempo…" y a los pocos segundos "Faltan aprox. N min · termina ~HH:MM".
4. Cancelar: el número de al lado vuelve.

Si algo de eso no pasa, es un bug de esta tarea aunque los tests estén
verdes: arreglarlo antes del commit.

- [ ] **Step 8: Commit**

```bash
git add src/nesting_app/web/index.html src/nesting_app/web/app.js tests/app/test_web_javascript.py
git commit -m "Pantalla: cuánto va a tardar, al lado de Acomodar, antes de arrancar"
```

---

## Qué queda fuera, a propósito

- **La barra de avance sigue midiendo piezas**, no consultas. La spec pide
  las dos cifras de tiempo; pasar la barra a consultas la haría retroceder
  cada vez que la previsión sube (al terminar el primer intento, o cuando
  la recuperación recupera algo), y una barra que retrocede es peor que no
  tener barra. Si se quiere, es un cambio aparte.
- **La CLI** no estima (spec, 1).
- **Un historial de corridas** para aprender la velocidad de la máquina
  (spec, 1): la prueba en vivo de `/api/estimar` alcanza.
