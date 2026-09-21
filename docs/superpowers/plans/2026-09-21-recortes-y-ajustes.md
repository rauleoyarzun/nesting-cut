# Recortes de placa, y cuatro ajustes de interfaz — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que se puedan cargar placas sueltas para la sesión actual y el acomodo las llene antes de abrir una placa del Material, más cuatro ajustes de interfaz (resolución 1 mm/px por omisión, ángulos por cantidad de posiciones, solapas dadas vuelta, zoom de rueda continuo).

**Architecture:** El motor deja de recibir un `Material` y pasa a recibir un `SheetSupply`: una lista finita de recortes seguida de una placa infinita. `PackResult` lleva qué placa fue cada índice, y `verify`, el escritor de DXF y el de preview dejan de asumir una medida única. El costo del layout pasa a contar sólo las placas del Material, porque un recorte es material ya pago.

**Tech Stack:** Python 3.13, pytest. Interfaz en HTML/CSS/JavaScript a mano, sin framework; sus tests leen los archivos estáticos como texto y no corren navegador.

**Spec:** `docs/superpowers/specs/2026-09-21-recortes-y-ajustes-design.es.md`

## Global Constraints

- **TDD sin excepciones:** test que falla, correrlo para verlo fallar, implementación mínima, test que pasa, commit. Un paso por vez.
- **Todo texto de cara al usuario va en español**, con tildes y eñes. Los nombres y docstrings del motor (`src/nesting/`) siguen la mezcla que ya tiene el repo: identificadores en inglés en `engine/`, `model/`, `io/` y `geometry/`; en español en `params.py` y en todo `src/nesting_app/`.
- **Nada de emojis.** El test `test_no_hay_emojis_en_la_interfaz` ya lo prohíbe y no se relaja. El `✕` del botón de quitar es U+2715, no un emoji; si el test lo rechaza, usar un SVG en línea con trazo como el resto de los íconos.
- **Ningún token de color nuevo en `app.css`.** Se usan los que ya están: `--panel`, `--borde`, `--radio`, `--sombra`, `--texto`, `--texto-2`.
- **La CLI no gana ninguna bandera.** Cambia por dentro (arma el `SheetSupply`, pasa `sheets` a `verify`/`write_dxf`/`write_preview`, default de `--resolucion`), pero su superficie de flags queda igual. Si un paso te pide agregar `--recorte`, el paso está mal: pará y avisá.
- **`verify()` es el árbitro y no confía en quien lo llama.** Sigue levantando `ValueError` ante un `sep`/`margin` negativo, y suma el mismo trato para una lista de placas que no cubra los índices que usan las colocaciones.
- **Sin recortes, nada cambia.** Después de cada tarea, una corrida sin recortes tiene que dar el mismo layout, el mismo costo y los mismos números que antes del plan. Las tareas 2 y 4 son puramente mecánicas y no pueden mover un resultado.
- **Los tests de JavaScript miran cuerpos, no el archivo entero.** `tests/app/test_web_javascript.py` ya tiene `_cuerpo_de_funcion(js, "nombre")` (línea 701) y `_cuerpo_de_handler(js, "evento")` (línea 743), que además borran los comentarios antes de mirar. Usarlos. Una aserción sobre el archivo entero (`assert "360" in js`) pasa por cualquier `360` perdido en un comentario, y hubo un test en la primera versión de este plan que pasaba ANTES de implementar nada porque afirmaba `"disabled" in js`, una cadena que ya estaba en el botón de guardar.
- **Correr la suite entera** (`.venv/bin/pytest`) al cerrar cada tarea, no sólo los tests nuevos. Los cambios de firma de las tareas 2 y 4 tocan muchos archivos de test.
- **Nada de `Co-Authored-By` ni atribución en los mensajes de commit.**

## Mapa de archivos

| Archivo | Responsabilidad | Tarea |
|---|---|---|
| `src/nesting/model/sheet.py` | **Nuevo.** Qué es una placa concreta (`Sheet`), en qué orden vienen (`SheetSupply`), y qué ángulos permite su veta (`allowed_angles`). | 1 |
| `src/nesting/model/material.py` | Entrada del catálogo. Gana `stock_sheet()`, pierde `allowed_angles`. | 1, 2 |
| `src/nesting/engine/packer.py` | Estrategia. Pasa a hablar en placas en vez de en un material. | 2, 3 |
| `src/nesting/geometry/verify.py` | El árbitro. Cada colocación contra **su** placa. | 4 |
| `src/nesting/io/dxf_writer.py` | Offsets acumulados. | 4 |
| `src/nesting/io/preview.py` | Offsets acumulados, placas alineadas abajo. | 4 |
| `src/nesting/params.py` | `Recorte`, sus reglas, y `a_supply()`. | 5 |
| `src/nesting/cli.py` | Arma el `SheetSupply` sin recortes. Default de resolución. | 2, 4, 5 |
| `src/nesting_app/api.py` | `RecorteEntrada`, serializa `recortes_usados`. | 5, 6 |
| `src/nesting_app/jobs.py` | `Resultado.recortes_usados`. | 6 |
| `src/nesting_app/corredor.py` | Arma el `SheetSupply` con los recortes del pedido. | 2, 4, 6 |
| `src/nesting_app/web/index.html` | Bloque de recortes, desplegable de posiciones, solapas, `value="1"`. | 5, 7, 8, 9 |
| `src/nesting_app/web/app.js` | `estado.recortes`, `angulosElegidos()`, zoom continuo. | 7, 8, 9 |
| `src/nesting_app/web/app.css` | Lista de recortes y fila de alta. | 7 |
| `src/nesting_app/web/info.js` | Globos de `recortes` y `posiciones`; el de `resolucion` reescrito. | 10 |
| `README.md` / `README.es.md` | Fila de Recortes, nuevo default de resolución. | 10 |

---

### Task 1: `Sheet` y `SheetSupply`

Modelo puro, sin tocar el motor todavía. Al terminar esta tarea el paquete
compila igual y la suite pasa igual: nadie usa `Sheet` aún.

**Files:**
- Create: `src/nesting/model/sheet.py`
- Modify: `src/nesting/model/material.py`
- Test: `tests/model/test_sheet.py` (nuevo)

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces:
  - `Sheet(width: float, height: float, grain_tolerance: float, cross_grain: bool = False, scrap: bool = False)`, frozen dataclass, con `area: float` como `@property`.
  - `SheetSupply(stock: Sheet, scraps: tuple[Sheet, ...] = (), material_name: str = "del material")`, frozen dataclass, con `sheet(index: int) -> Sheet`.
  - `allowed_angles(sheet: Sheet, angles: Sequence[float]) -> list[float]` en `nesting.model.sheet`.
  - `Material.stock_sheet() -> Sheet`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/model/test_sheet.py`:

```python
from nesting.model.material import Material
from nesting.model.sheet import Sheet, SheetSupply, allowed_angles

LIBRE = Sheet(1000.0, 2000.0, grain_tolerance=180.0)
CON_VETA = Sheet(1000.0, 2000.0, grain_tolerance=5.0)
CRUZADA = Sheet(1000.0, 2000.0, grain_tolerance=5.0, cross_grain=True)


def test_el_area_es_ancho_por_alto():
    assert Sheet(600.0, 800.0, grain_tolerance=180.0).area == 480_000.0


def test_una_placa_sin_veta_permite_todos_los_angulos():
    assert allowed_angles(LIBRE, (0.0, 45.0, 90.0, 135.0)) == [0.0, 45.0, 90.0, 135.0]


def test_una_placa_con_veta_solo_permite_el_eje_largo():
    assert allowed_angles(CON_VETA, (0.0, 90.0, 180.0, 270.0)) == [0.0, 180.0]


def test_la_veta_cruzada_rota_el_eje_noventa_grados():
    """Es la razón de ser de la casilla: el mismo pedazo, girado, permite
    justo los ángulos que antes prohibía."""
    assert allowed_angles(CRUZADA, (0.0, 90.0, 180.0, 270.0)) == [90.0, 270.0]


def test_la_veta_cruzada_no_cambia_nada_en_una_placa_libre():
    cruzada_libre = Sheet(1000.0, 2000.0, grain_tolerance=180.0, cross_grain=True)
    angulos = (0.0, 45.0, 90.0, 135.0)
    assert allowed_angles(cruzada_libre, angulos) == list(angulos)


def test_el_plan_devuelve_los_recortes_y_despues_siempre_la_del_material():
    a = Sheet(600.0, 800.0, grain_tolerance=180.0, scrap=True)
    b = Sheet(450.0, 1200.0, grain_tolerance=180.0, scrap=True)
    stock = Sheet(1830.0, 2600.0, grain_tolerance=180.0)
    plan = SheetSupply(stock=stock, scraps=(a, b))

    assert plan.sheet(0) is a
    assert plan.sheet(1) is b
    assert plan.sheet(2) is stock
    assert plan.sheet(99) is stock


def test_un_plan_sin_recortes_es_siempre_la_placa_del_material():
    stock = Sheet(1830.0, 2600.0, grain_tolerance=180.0)
    plan = SheetSupply(stock=stock)
    assert plan.sheet(0) is stock is plan.sheet(7)


def test_la_placa_del_material_no_es_un_recorte_y_no_esta_cruzada():
    hoja = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0).stock_sheet()
    assert (hoja.width, hoja.height, hoja.grain_tolerance) == (1830.0, 2600.0, 180.0)
    assert hoja.scrap is False
    assert hoja.cross_grain is False
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/model/test_sheet.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting.model.sheet'`

- [ ] **Step 3: Escribir `src/nesting/model/sheet.py`**

```python
"""Una placa concreta sobre la que se acomoda, y en qué orden vienen.

El motor solía recibir un `Material` y asumir que toda placa medía lo
mismo. Eso alcanzaba mientras las placas se compraran; no alcanza para los
recortes, que son de a uno y de cualquier medida. `Sheet` es la placa que
el motor tiene enfrente en este momento, y `SheetSupply` dice cuál es esa
placa en cada turno.
"""

from collections.abc import Sequence
from dataclasses import dataclass

GRAIN_EPS = 1e-9


@dataclass(frozen=True)
class Sheet:
    """Una placa concreta: su medida, su veta, y de dónde salió."""

    width: float
    height: float
    grain_tolerance: float
    """Grados que una pieza puede desviarse del eje de veta de ESTA placa.

    El rango útil real es 0 a 90: la distancia angular al eje nunca supera
    90 grados, así que cualquier valor de 90 o más equivale a rotación
    libre. Por convención se usa 180 para expresar "libre".
    """

    cross_grain: bool = False
    """La veta corre a lo ancho y no a lo alto.

    Un recorte de 600x800 puede tener la veta en cualquiera de los dos
    sentidos según cómo salió de la placa madre, y eso sólo lo sabe quien
    está mirando el pedazo. Marcarlo rota el eje 90 grados.
    """

    scrap: bool = False
    """Es un recorte: material que ya está pago.

    `layout_cost` cuenta sólo las placas que NO son recortes, porque llenar
    un recorte no cuesta nada y el motor no tiene que evitarlo.
    """

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True)
class SheetSupply:
    """Qué placa toca en cada turno. Los recortes se agotan; la del Material no.

    `sheet(i)` no levanta nunca: pasado el último recorte devuelve siempre
    la placa del Material. Es lo que hace que el bucle del packer pueda
    pedir placas hasta que no le queden piezas, sin llevar la cuenta de
    cuántas hay.
    """

    stock: Sheet
    scraps: tuple[Sheet, ...] = ()
    material_name: str = "del material"
    """Sólo para el mensaje de "esta pieza no entra en una placa vacía".

    `Sheet` no tiene nombre a propósito -- un recorte no lo tiene -- pero
    ese mensaje nombra el material, y siempre se levanta contra la placa
    del Material, así que el nombre siempre corresponde.
    """

    def sheet(self, index: int) -> Sheet:
        return self.scraps[index] if index < len(self.scraps) else self.stock


def allowed_angles(sheet: Sheet, angles: Sequence[float]) -> list[float]:
    """Deja sólo los ángulos que la veta de esta placa permite.

    Un ángulo se permite cuando cae dentro de `grain_tolerance` grados del
    eje de veta, que corre por 0 y 180 -- o por 90 y 270 si la placa está
    cruzada.
    """
    offset = 90.0 if sheet.cross_grain else 0.0
    return [
        a
        for a in angles
        if _distance_to_grain_axis(a - offset) <= sheet.grain_tolerance + GRAIN_EPS
    ]


def _distance_to_grain_axis(angle: float) -> float:
    folded = angle % 180.0
    return min(folded, 180.0 - folded)
```

- [ ] **Step 4: Agregar `stock_sheet()` a `Material` y delegar `allowed_angles`**

En `src/nesting/model/material.py`, agregar el import y el método, y
reemplazar el cuerpo de `allowed_angles` por una delegación. La función vieja
queda un solo paso más (la borra la Tarea 2): delegar en vez de duplicar la
matemática de la veta es lo que evita que las dos versiones se separen.

Agregar arriba, junto a los otros imports:

```python
from nesting.model.sheet import Sheet, allowed_angles as _allowed_angles_de_placa
```

Agregar dentro de `class Material`, después del campo `grain_tolerance`:

```python
    def stock_sheet(self) -> Sheet:
        """La placa que se abre cuando hay que comprar material."""
        return Sheet(
            width=self.sheet_w,
            height=self.sheet_h,
            grain_tolerance=self.grain_tolerance,
        )
```

Reemplazar el cuerpo de `allowed_angles` (dejando su docstring tal cual) por:

```python
    return _allowed_angles_de_placa(material.stock_sheet(), angles)
```

y borrar `_distance_to_grain_axis` y `GRAIN_EPS` de `material.py`, que ya no
se usan ahí.

- [ ] **Step 5: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/model/test_sheet.py -v`
Expected: PASS, 8 tests

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos nuevos. `tests/model/test_material.py` sigue verde
porque `allowed_angles` delega y da los mismos resultados.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/model/sheet.py src/nesting/model/material.py tests/model/test_sheet.py
git commit -m "Modelo: Sheet y SheetSupply, la placa concreta y en qué orden viene"
```

---

### Task 2: El packer habla en placas

Cambio de firma puro. Al terminar, `pack()` recibe un `SheetSupply` y
`PackResult` sabe qué placa fue cada índice — pero nadie le pasa recortes
todavía, así que **ningún resultado cambia**. Esa es la propiedad que hay que
cuidar y la que un test fija.

**Files:**
- Modify: `src/nesting/engine/packer.py`
- Modify: `src/nesting/model/material.py` (borrar `allowed_angles`)
- Modify: `src/nesting/cli.py:219`
- Modify: `src/nesting_app/corredor.py:256`
- Modify: `tests/engine/test_packer.py`, `tests/engine/test_effort.py`, `tests/engine/test_progreso.py`, `tests/engine/test_recuperacion.py`, `tests/test_calibration.py` (mecánico: envolver el `Material` en un `SheetSupply`)
- Modify: `tests/model/test_material.py` (los tests de `allowed_angles` se mudaron a `test_sheet.py` en la Tarea 1; borrarlos de acá)
- Test: `tests/engine/test_packer.py`

**Interfaces:**
- Consumes: `Sheet`, `SheetSupply`, `allowed_angles`, `Material.stock_sheet()` (Tarea 1).
- Produces:
  - `pack(parts, supply: SheetSupply, config, oracle_factory, progreso=None) -> PackResult`
  - `_pack_once(order, supply: SheetSupply, config, oracle_factory, aviso=None) -> PackResult`
  - `PackResult.sheets: list[Sheet]` — la placa de cada índice, en orden.
  - `orientations(sheet: Sheet, config: NestConfig) -> list[tuple[float, bool]]`

- [ ] **Step 1: Escribir el test que fija "nada cambia"**

Agregar al final de `tests/engine/test_packer.py`:

```python
from nesting.model.sheet import Sheet, SheetSupply

PLAN_LIBRE = SheetSupply(stock=FREE.stock_sheet(), material_name=FREE.name)


def test_el_resultado_dice_que_placa_fue_cada_indice():
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    result = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)

    assert len(result.sheets) == result.sheets_used
    assert all(h is PLAN_LIBRE.stock for h in result.sheets)


def test_sin_recortes_el_aprovechamiento_se_calcula_igual_que_siempre():
    """La cuenta pasó de un área única a un área por placa. Con todas las
    placas iguales tiene que dar exactamente lo mismo, o alguna corrida
    vieja cambió de número sin que nadie lo pidiera."""
    parts = [rect_part(i, 400.0, 400.0) for i in range(6)]
    result = pack(parts, PLAN_LIBRE, CONFIG, ShelfOracle)

    area_placa = FREE.sheet_w * FREE.sheet_h
    for indice, fraccion in enumerate(result.utilization):
        area_en_placa = sum(
            p.area for p in parts
            for pl in result.placements
            if pl.part_id == p.id and pl.sheet == indice
        )
        assert fraccion == pytest.approx(area_en_placa / area_placa)

    total = sum(p.area for p in parts)
    assert result.total_utilization == pytest.approx(
        total / (area_placa * result.sheets_used)
    )


def test_orientations_toma_una_placa_y_respeta_su_veta():
    libre = orientations(FREE.stock_sheet(), CONFIG)
    con_veta = orientations(GRAIN.stock_sheet(), CONFIG)

    assert (90.0, False) in libre
    assert (90.0, False) not in con_veta
    assert (0.0, False) in con_veta


def test_orientations_mira_la_veta_de_cada_placa_y_no_la_del_material():
    """Dos placas del mismo material con la veta al revés permiten ángulos
    distintos. Si esto falla, las orientaciones se están calculando una vez
    por corrida en lugar de una por placa."""
    derecha = Sheet(500.0, 500.0, grain_tolerance=5.0)
    cruzada = Sheet(500.0, 500.0, grain_tolerance=5.0, cross_grain=True)

    assert (0.0, False) in orientations(derecha, CONFIG)
    assert (0.0, False) not in orientations(cruzada, CONFIG)
    assert (90.0, False) in orientations(cruzada, CONFIG)
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_packer.py -k "placa or aprovechamiento or orientations" -v`
Expected: FAIL. `test_el_resultado_dice_que_placa_fue_cada_indice` con
`AttributeError: 'PackResult' object has no attribute 'sheets'`; los de
`orientations` con `AttributeError: 'Sheet' object has no attribute 'sheet_w'`.

- [ ] **Step 3: Cambiar `PackResult` y `orientations`**

En `src/nesting/engine/packer.py`, agregar al import de modelo:

```python
from nesting.model.sheet import Sheet, SheetSupply, allowed_angles
```

y sacar `allowed_angles` del import de `nesting.model.material` (queda
importado sólo `Material`, que todavía usan las firmas de `_recuperar...` y
`_compact_last_sheet` hasta el paso 5).

En `PackResult`, agregar el campo después de `sheets_used`:

```python
    sheets: list[Sheet] = field(default_factory=list)
    """Qué placa concreta fue cada índice, en orden.

    Sin esto, todo lo que viene después de `pack` -- el verificador, el
    escritor de DXF, la previsualización -- tendría que adivinar la medida
    de cada placa, y con recortes en juego adivinar es escribir un DXF
    equivocado.
    """
```

Reemplazar `orientations`:

```python
def orientations(sheet: Sheet, config: NestConfig) -> list[tuple[float, bool]]:
    """Cada par (ángulo, espejo) que la veta de ESTA placa y el config permiten."""
    angles = allowed_angles(sheet, config.angles)
    result = [(a, False) for a in angles]
    if config.mirror:
        result.extend((a, True) for a in angles)
    return result
```

- [ ] **Step 4: Reescribir el bucle de `_pack_once`**

Reemplazar la firma y el cuerpo desde `choices = orientations(...)` hasta el
cálculo de `total_utilization`. La firma pasa a:

```python
def _pack_once(
    order: Sequence[Part],
    supply: SheetSupply,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
    aviso: Callable[[int, int], None] | None = None,
) -> PackResult:
```

y el cuerpo, desde donde hoy dice `choices = orientations(material, config)`:

```python
    remaining = list(order)
    usadas: list[Sheet] = []
    placed_area_per_sheet: list[float] = []

    # Dos contadores y no uno: `siguiente` avanza por el plan de placas y
    # `len(usadas)` cuenta las que de verdad recibieron algo. Hoy son el
    # mismo número; en cuanto la Tarea 3 permita saltear un recorte vacío,
    # dejan de serlo, y las colocaciones tienen que llevar el segundo.
    siguiente = 0
    total_ubicadas = 0
    while remaining:
        hoja = supply.sheet(siguiente)
        siguiente += 1

        # Por placa y no por corrida: dos placas del mismo material pueden
        # tener la veta al revés y permitir ángulos distintos.
        choices = orientations(hoja, config)
        oracle = oracle_factory()
        oracle.reset(hoja.width, hoja.height, config)

        indice = len(usadas)
        still_pending: list[Part] = []
        en_esta_placa: list[Placement] = []
        placed_area = 0.0
        placed_count = 0

        for part in remaining:
            spot = _best_over_orientations(oracle, part, choices)
            if spot is None:
                still_pending.append(part)
                continue
            angle, mirror, x, y = spot
            oracle.place(part, angle, mirror, x, y)
            en_esta_placa.append(
                Placement(part.id, indice, Transform(angle, mirror, x, y))
            )
            placed_area += part.area
            placed_count += 1
            if aviso is not None:
                aviso(total_ubicadas + placed_count, indice + 1)

        # Ver el comentario largo de la versión anterior: la guarda mira si
        # se colocó ALGO, no cuánta área, porque una pieza de área neta cero
        # dejaría `placed_area == 0.0` con `still_pending` vacío.
        if placed_count == 0:
            _raise_too_large(
                still_pending[0], hoja, config, choices, supply.material_name
            )

        result.placements.extend(en_esta_placa)
        usadas.append(hoja)
        placed_area_per_sheet.append(placed_area)
        total_ubicadas += placed_count
        remaining = still_pending

    result.sheets = usadas
    result.sheets_used = len(usadas)
    result.utilization = [
        area / hoja.area for area, hoja in zip(placed_area_per_sheet, usadas)
    ]
    area_total = sum(hoja.area for hoja in usadas)
    result.total_utilization = (
        sum(placed_area_per_sheet) / area_total if area_total else 0.0
    )
    result.seconds = time.perf_counter() - started
    return result
```

Y `_raise_too_large` pasa a recibir la placa y el nombre:

```python
def _raise_too_large(
    part: Part,
    sheet: Sheet,
    config: NestConfig,
    choices: Sequence[tuple[float, bool]],
    material_name: str,
) -> None:
    """Informa la huella más chica que la pieza puede tomar, contra el área útil.

    Se elige UNA orientación -- la que minimiza su propia dimensión mayor --
    en vez de tomar el ancho mínimo y el alto mínimo por separado, que
    pueden venir de dos orientaciones distintas y describir una caja que la
    pieza nunca tiene.
    """
    best_w = best_h = None
    best_max = float("inf")
    for angle, mirror in choices:
        x0, y0, x1, y1 = transformed_bbox(part, angle, mirror)
        w, h = x1 - x0, y1 - y0
        if max(w, h) < best_max:
            best_max = max(w, h)
            best_w, best_h = w, h

    usable_w = sheet.width - 2 * config.margin
    usable_h = sheet.height - 2 * config.margin
    raise PartTooLargeError(
        f"la pieza {part.id} no entra en una placa vacía: mide al menos "
        f"{best_w:.1f} x {best_h:.1f} mm en su mejor orientación, "
        f"y el área útil de la placa {material_name} es "
        f"{usable_w:.1f} x {usable_h:.1f} mm (margen {config.margin} mm)."
    )
```

- [ ] **Step 5: Pasar el `SheetSupply` por `pack`, la recuperación y la compactación**

En `pack`, cambiar el parámetro `material: Material` por `supply: SheetSupply`
y reemplazar las tres llamadas internas (`_pack_once` de la primera pasada, el
`_pack_once` del bucle de reintentos, y las dos de abajo) para que pasen
`supply`. Las llamadas de abajo quedan:

```python
    best = _recuperar_de_la_ultima_placa(
        best, parts, config, oracle_factory,
        aviso_recuperacion if progreso is not None else None,
    )
    best = _compact_last_sheet(best, parts, config, oracle_factory)
```

En `_recuperar_de_la_ultima_placa`, sacar el parámetro `material` y reempacar
cada placa contra la suya:

```python
            redone = _pack_once(
                orden,
                SheetSupply(stock=result.sheets[placa]),
                config,
                oracle_factory,
                aviso,
            )
```

y al armar el `PackResult` de salida, reemplazar el bloque del área única:

```python
    sheets_finales = result.sheets if quedan else result.sheets[:ultima]
    areas = [0.0] * len(sheets_finales)
    for p in placements:
        areas[p.sheet] += by_id[p.part_id].area
    area_total = sum(h.area for h in sheets_finales)

    return PackResult(
        placements=placements,
        sheets_used=len(sheets_finales),
        sheets=sheets_finales,
        utilization=[
            area / hoja.area for area, hoja in zip(areas, sheets_finales)
        ],
        total_utilization=sum(areas) / area_total if area_total else 0.0,
        seconds=result.seconds,
    )
```

(La variable local `sheets` que había se reemplaza por `sheets_finales`; la
línea `sheets = result.sheets_used if quedan else ultima` se borra.)

En `_compact_last_sheet`, sacar `material` y usar la placa:

```python
    hoja = result.sheets[last]
    ...
    redone = _pack_once(order, SheetSupply(stock=hoja), boosted, oracle_factory)
    ...
    result.utilization[last] = sum(p.area for p in on_last) / hoja.area
```

Borrar el import de `Material` de `packer.py` si ya no queda ningún uso.

- [ ] **Step 6: Borrar `allowed_angles` de `material.py` y actualizar a los que llaman**

En `src/nesting/model/material.py`, borrar la función `allowed_angles` entera
y su import de delegación. `Material` queda con `load_materials` y
`stock_sheet()`.

En `src/nesting/cli.py:219`, reemplazar:

```python
        result = pack(parts, material, config, lambda: RasterOracle(cache=cache))
```

por:

```python
        supply = SheetSupply(stock=material.stock_sheet(), material_name=material.name)
        result = pack(parts, supply, config, lambda: RasterOracle(cache=cache))
```

y agregar `from nesting.model.sheet import SheetSupply` a los imports.

En `src/nesting_app/corredor.py:256`, el mismo cambio:

```python
        supply = SheetSupply(stock=material.stock_sheet(), material_name=material.name)
        resultado = pack(
            piezas, supply, config, lambda: RasterOracle(cache=cache), progreso=progreso
        )
```

con su import.

En los tests de `tests/engine/` y `tests/test_calibration.py`, reemplazar cada
`pack(parts, MATERIAL, ...)` por `pack(parts, SheetSupply(stock=MATERIAL.stock_sheet(), material_name=MATERIAL.name), ...)`.
Donde el test tenga varias llamadas, definir una constante arriba del archivo
como `PLAN_LIBRE` en el paso 1 y usarla.

En `tests/model/test_material.py`, borrar los tests de `allowed_angles`: se
mudaron a `tests/model/test_sheet.py` en la Tarea 1. Si alguno cubría un caso
que `test_sheet.py` no tiene (por ejemplo tolerancia exactamente 90), moverlo
tal cual en vez de perderlo.

- [ ] **Step 7: Correr los tests nuevos y la suite entera**

Run: `.venv/bin/pytest tests/engine/test_packer.py -v`
Expected: PASS

Run: `.venv/bin/pytest`
Expected: PASS, sin fallos. **Si algún test de motor cambió de número
esperado, no lo actualices: significa que el cambio mecánico movió un
resultado y hay un error en el paso 4 o 5.**

- [ ] **Step 8: Commit**

```bash
git add -A src tests
git commit -m "Motor: pack recibe un plan de placas en vez de un material

PackResult lleva qué placa fue cada índice, las orientaciones se calculan
por placa y el aprovechamiento se calcula contra el área de cada una. Sin
recortes todavía: ningún resultado cambia, y los tests lo fijan."
```

---

### Task 3: Los recortes cambian el layout

Acá cambia el comportamiento: los recortes se llenan primero, los que no
sirven se saltean, y el costo deja de contarlos.

**Files:**
- Modify: `src/nesting/engine/packer.py`
- Test: `tests/engine/test_recortes.py` (nuevo)

**Interfaces:**
- Consumes: todo lo de la Tarea 2.
- Produces:
  - `CostoLayout(placas_nuevas: int, material_ultima: float, alto_ultima: float)` — el campo `placas` se renombró a `placas_nuevas`.
  - `layout_cost(result: PackResult, parts: Sequence[Part]) -> CostoLayout` (misma firma).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/engine/test_recortes.py`:

```python
"""Qué pasa cuando el plan de placas tiene recortes adelante."""

import pytest

from nesting.engine.oracle import NestConfig
from nesting.engine.packer import (
    PartTooLargeError,
    CostoLayout,
    layout_cost,
    pack,
)
from nesting.engine.shelf_oracle import ShelfOracle
from nesting.model.part import Part
from nesting.model.sheet import Sheet, SheetSupply

CONFIG = NestConfig(sep=10.0, margin=20.0, angles=(0.0, 90.0), mirror=False,
                    effort="rapido")

STOCK = Sheet(2000.0, 2000.0, grain_tolerance=180.0)


def rect_part(part_id, w, h):
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def recorte(w, h, **extra):
    return Sheet(w, h, grain_tolerance=180.0, scrap=True, **extra)


def test_el_recorte_se_llena_antes_que_la_placa_del_material():
    plan = SheetSupply(stock=STOCK, scraps=(recorte(500.0, 500.0),))
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert result.sheets[0].scrap is True


def test_un_recorte_donde_no_entra_nada_desaparece_del_resultado():
    """No es un error: un pedazo de 100x100 simplemente no sirve para esta
    pieza. Tiene que saltearse, no aparecer como una placa al 0%."""
    plan = SheetSupply(stock=STOCK, scraps=(recorte(100.0, 100.0),))
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert result.sheets[0].scrap is False
    assert len(result.utilization) == 1
    assert all(p.sheet == 0 for p in result.placements)


def test_se_saltean_varios_recortes_seguidos_sin_perder_la_cuenta():
    plan = SheetSupply(
        stock=STOCK,
        scraps=(recorte(100.0, 100.0), recorte(120.0, 90.0), recorte(500.0, 500.0)),
    )
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert result.sheets_used == 1
    assert (result.sheets[0].width, result.sheets[0].height) == (500.0, 500.0)
    assert result.placements[0].sheet == 0


def test_una_pieza_que_no_entra_en_ninguna_placa_sigue_siendo_error_duro():
    plan = SheetSupply(
        stock=STOCK, scraps=(recorte(100.0, 100.0),), material_name="mdf18"
    )
    piezas = [rect_part(0, 5000.0, 5000.0)]

    with pytest.raises(PartTooLargeError) as capturado:
        pack(piezas, plan, CONFIG, ShelfOracle)

    # Nombra la placa del Material, no el recorte de 100x100 que se salteó.
    assert "mdf18" in str(capturado.value)
    assert "1960.0 x 1960.0" in str(capturado.value)


def test_el_costo_no_cuenta_los_recortes():
    plan = SheetSupply(stock=STOCK, scraps=(recorte(500.0, 500.0),))
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert layout_cost(result, piezas).placas_nuevas == 0


def test_llenar_un_recorte_cuesta_menos_que_abrir_una_placa_nueva():
    """La decisión de diseño entera, en un assert: si esto se invierte, el
    motor va a preferir saltearse los recortes."""
    piezas = [rect_part(0, 400.0, 400.0)]

    con_recorte = pack(
        piezas, SheetSupply(stock=STOCK, scraps=(recorte(500.0, 500.0),)),
        CONFIG, ShelfOracle,
    )
    sin_recorte = pack(piezas, SheetSupply(stock=STOCK), CONFIG, ShelfOracle)

    assert layout_cost(con_recorte, piezas) < layout_cost(sin_recorte, piezas)


def test_el_aprovechamiento_de_un_recorte_se_mide_contra_su_area():
    plan = SheetSupply(stock=STOCK, scraps=(recorte(500.0, 500.0),))
    piezas = [rect_part(0, 400.0, 400.0)]

    result = pack(piezas, plan, CONFIG, ShelfOracle)

    assert result.utilization[0] == pytest.approx(160_000.0 / 250_000.0)


def test_una_placa_del_material_vacia_no_se_saltea_nunca():
    """Saltear una placa infinita sería un bucle sin fin. La guarda tiene
    que mirar `scrap`, no "quedó vacía"."""
    plan = SheetSupply(stock=Sheet(100.0, 100.0, grain_tolerance=180.0))
    piezas = [rect_part(0, 400.0, 400.0)]

    with pytest.raises(PartTooLargeError):
        pack(piezas, plan, CONFIG, ShelfOracle)


def test_sin_recortes_placas_nuevas_es_la_cantidad_de_placas():
    piezas = [rect_part(i, 900.0, 900.0) for i in range(6)]
    result = pack(piezas, SheetSupply(stock=STOCK), CONFIG, ShelfOracle)

    assert layout_cost(result, piezas).placas_nuevas == result.sheets_used


def test_el_costo_se_compara_campo_por_campo_en_orden():
    assert CostoLayout(0, 999.0, 999.0) < CostoLayout(1, 0.0, 0.0)
    assert CostoLayout(1, 10.0, 999.0) < CostoLayout(1, 20.0, 0.0)
    assert CostoLayout(1, 10.0, 5.0) < CostoLayout(1, 10.0, 6.0)
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/engine/test_recortes.py -v`
Expected: FAIL. El de saltear con
`PartTooLargeError` (todavía no se saltea) y los de costo con
`AttributeError: 'CostoLayout' object has no attribute 'placas_nuevas'`.

- [ ] **Step 3: Saltear el recorte donde no entró nada**

En `_pack_once`, reemplazar la guarda:

```python
        if placed_count == 0:
            # Un recorte donde no entra ninguna pieza es normal -- un pedazo
            # de 100x100 no sirve para nada grande -- así que se saltea y no
            # llega a existir en el resultado: ni placa al 0% en la
            # previsualización, ni rectángulo vacío en el DXF. En una placa
            # del Material, en cambio, sigue siendo el error de siempre: esa
            # placa es infinita, y saltearla sería un bucle sin fin.
            if hoja.scrap:
                continue
            _raise_too_large(
                still_pending[0], hoja, config, choices, supply.material_name
            )
```

- [ ] **Step 4: Renombrar el campo del costo y contarlo**

En `CostoLayout`, renombrar el primer campo y reescribir su docstring:

```python
    placas_nuevas: int
    """Cuántas placas del Material hubo que abrir. Manda sobre todo lo demás.

    Los recortes NO se cuentan: son material que ya está pago, así que
    llenarlos no cuesta nada y el motor no tiene que evitarlo. Si contaran,
    el motor preferiría saltear un recorte de 600x800 y meter todo en una
    placa nueva -- una placa contra dos -- que es exactamente lo contrario
    de para qué existen los recortes.

    Sin recortes en el plan, este número es idéntico a `sheets_used`, y el
    costo entero da lo mismo que antes de que existieran.
    """
```

En `layout_cost`, reemplazar las dos primeras líneas del cuerpo útil:

```python
    if not result.placements:
        return CostoLayout(0, 0.0, 0.0)

    placas_nuevas = sum(1 for hoja in result.sheets if not hoja.scrap)
    by_id = {p.id: p for p in parts}
    last_sheet = len(result.sheets) - 1
```

y la línea final:

```python
    return CostoLayout(placas_nuevas, material, top)
```

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/pytest tests/engine/test_recortes.py -v`
Expected: PASS, 10 tests

Run: `.venv/bin/pytest tests/engine -v`
Expected: PASS

- [ ] **Step 6: Escribir el test de la guarda de la recuperación**

Agregar a `tests/engine/test_recortes.py`:

```python
def test_la_recuperacion_no_acepta_un_layout_mas_caro():
    """La versión vieja aceptaba su resultado sin compararlo, apoyada en que
    vaciar la última placa baja el conteo de placas. Con `placas_nuevas` eso
    dejó de valer: vaciar un RECORTE no baja nada, y la "última placa" pasa
    a ser otra con más material arriba. La guarda es lo único que lo atrapa.
    """
    from nesting.engine.packer import PackResult, _recuperar_de_la_ultima_placa
    from nesting.model.entities import Transform
    from nesting.model.part import Placement

    grande = rect_part(0, 900.0, 900.0)
    chica = rect_part(1, 100.0, 100.0)
    nueva = Sheet(2000.0, 2000.0, grain_tolerance=180.0)
    sobra = recorte(500.0, 500.0)

    entrada = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 20.0, 20.0)),
            Placement(1, 1, Transform(0.0, False, 20.0, 20.0)),
        ],
        sheets_used=2,
        sheets=[nueva, sobra],
        utilization=[810_000.0 / nueva.area, 10_000.0 / sobra.area],
    )

    salida = _recuperar_de_la_ultima_placa(
        entrada, [grande, chica], CONFIG, ShelfOracle, None
    )

    assert layout_cost(salida, [grande, chica]) <= layout_cost(
        entrada, [grande, chica]
    )
```

- [ ] **Step 7: Correr el test para verlo fallar**

Run: `.venv/bin/pytest tests/engine/test_recortes.py::test_la_recuperacion_no_acepta_un_layout_mas_caro -v`
Expected: FAIL con el `assert` del final: la recuperación mueve la pieza chica
a la placa 0, la placa 1 (el recorte) desaparece, `placas_nuevas` sigue en 1 y
`material_ultima` sube de 10 000 a 820 000.

- [ ] **Step 8: Agregar la guarda**

En `_recuperar_de_la_ultima_placa`, reemplazar el `return PackResult(...)` del
final por:

```python
    recuperado = PackResult(
        placements=placements,
        sheets_used=len(sheets_finales),
        sheets=sheets_finales,
        utilization=[
            area / hoja.area for area, hoja in zip(areas, sheets_finales)
        ],
        total_utilization=sum(areas) / area_total if area_total else 0.0,
        seconds=result.seconds,
    )

    # La versión anterior devolvía esto sin compararlo, apoyada en un
    # argumento escrito: si la última placa se vacía baja el conteo de
    # placas, que es el primer campo del costo, así que nunca empeora. Con
    # `placas_nuevas` el argumento dejó de valer -- vaciar un RECORTE no baja
    # ese conteo, y la "última placa" pasa a ser otra, con posiblemente más
    # material arriba. Comparar cuesta dos recorridos de las colocaciones y
    # convierte una garantía razonada en una verificada.
    if layout_cost(recuperado, parts) > layout_cost(result, parts):
        return result
    return recuperado
```

Y actualizar la sección "QUÉ SE ACEPTA" de la docstring para que deje de
afirmar que el costo no puede subir por construcción, y diga en cambio que la
regla interna lo hace improbable y la guarda final lo garantiza.

- [ ] **Step 9: Correr los tests**

Run: `.venv/bin/pytest tests/engine/test_recortes.py -v`
Expected: PASS, 11 tests

Run: `.venv/bin/pytest`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add -A src tests
git commit -m "Motor: los recortes se llenan primero y no cuentan como placa

Un recorte donde no entra nada se saltea en vez de abortar. CostoLayout
cuenta sólo las placas del Material, y la recuperación pasa a comparar
costos: su garantía razonada dejó de valer cuando la última placa puede
ser un recorte que se vacía."
```

---

### Task 4: `verify`, DXF y preview por placa

Cambio de firma mecánico, como la Tarea 2: al terminar, nada cambió para una
corrida sin recortes. El test que importa es el de `verify`.

**Files:**
- Modify: `src/nesting/geometry/verify.py:61-135`
- Modify: `src/nesting/io/dxf_writer.py:35-95`
- Modify: `src/nesting/io/preview.py:28-99`
- Modify: `src/nesting/cli.py:229,261,275`
- Modify: `src/nesting_app/corredor.py:260,271,282`
- Modify: `tests/geometry/test_verify.py`, `tests/io/test_dxf_writer.py`, `tests/io/test_preview.py` (mecánico)
- Test: los tres archivos de test de arriba

**Interfaces:**
- Consumes: `Sheet` (Tarea 1), `PackResult.sheets` (Tarea 2).
- Produces:
  - `verify(parts, placements, sheets: Sequence[Sheet], sep: float, margin: float) -> list[Violation]`
  - `write_dxf(path, drawing, parts, placements, sheets: Sequence[Sheet], gap=DEFAULT_GAP) -> None`
  - `write_preview(path, parts, placements, sheets: Sequence[Sheet], utilization, colors=None, px_per_mm=0.15) -> None`

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/geometry/test_verify.py`:

```python
from nesting.model.sheet import Sheet


def test_una_pieza_que_se_sale_de_su_recorte_es_violacion():
    """El test que impide que un DXF malo llegue a la fresadora: la pieza
    entra holgada en la placa del Material, pero está en un recorte de
    600x800 y se le va afuera."""
    pieza = Part(0, ((0.0, 0.0), (700.0, 0.0), (700.0, 700.0), (0.0, 700.0)), (), (0,))
    hojas = [Sheet(600.0, 800.0, grain_tolerance=180.0, scrap=True)]
    colocaciones = [Placement(0, 0, Transform(0.0, False, 10.0, 10.0))]

    violaciones = verify([pieza], colocaciones, hojas, sep=0.0, margin=0.0)

    assert len(violaciones) == 1
    assert violaciones[0].kind == "out_of_bounds"


def test_la_misma_pieza_en_una_placa_grande_no_es_violacion():
    pieza = Part(0, ((0.0, 0.0), (700.0, 0.0), (700.0, 700.0), (0.0, 700.0)), (), (0,))
    hojas = [Sheet(1830.0, 2600.0, grain_tolerance=180.0)]
    colocaciones = [Placement(0, 0, Transform(0.0, False, 10.0, 10.0))]

    assert verify([pieza], colocaciones, hojas, sep=0.0, margin=0.0) == []


def test_cada_placa_se_verifica_contra_su_propia_medida():
    """Dos placas distintas, la misma pieza en la misma posición: entra en
    una y no en la otra."""
    pieza_a = Part(0, ((0.0, 0.0), (700.0, 0.0), (700.0, 700.0), (0.0, 700.0)), (), (0,))
    pieza_b = Part(1, ((0.0, 0.0), (700.0, 0.0), (700.0, 700.0), (0.0, 700.0)), (), (1,))
    hojas = [
        Sheet(1830.0, 2600.0, grain_tolerance=180.0),
        Sheet(600.0, 800.0, grain_tolerance=180.0, scrap=True),
    ]
    colocaciones = [
        Placement(0, 0, Transform(0.0, False, 10.0, 10.0)),
        Placement(1, 1, Transform(0.0, False, 10.0, 10.0)),
    ]

    violaciones = verify([pieza_a, pieza_b], colocaciones, hojas, sep=0.0, margin=0.0)

    assert [v.sheet for v in violaciones] == [1]


def test_verify_rechaza_una_lista_de_placas_que_no_cubre_las_colocaciones():
    """El árbitro no confía en quien lo llama: verificar la placa 3 contra
    una lista de dos es un `IndexError` en el mejor caso y un 'todo bien'
    equivocado en el peor."""
    pieza = Part(0, ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)), (), (0,))
    hojas = [Sheet(1000.0, 1000.0, grain_tolerance=180.0)]
    colocaciones = [Placement(0, 3, Transform(0.0, False, 10.0, 10.0))]

    with pytest.raises(ValueError, match="placa"):
        verify([pieza], colocaciones, hojas, sep=0.0, margin=0.0)
```

Agregar a `tests/io/test_dxf_writer.py`:

```python
def test_las_placas_de_anchos_distintos_no_se_pisan(tmp_path):
    """Con el offset viejo (indice * (ancho + gap)) la segunda placa se
    dibujaba encima de la primera en cuanto los anchos dejaban de ser
    iguales."""
    import ezdxf

    from nesting.io.dxf_writer import SHEET_LAYER
    from nesting.model.sheet import Sheet

    hojas = [
        Sheet(600.0, 800.0, grain_tolerance=180.0, scrap=True),
        Sheet(1830.0, 2600.0, grain_tolerance=180.0),
    ]
    salida = tmp_path / "salida.dxf"
    write_dxf(salida, drawing_with([]), [], [], hojas)

    doc = ezdxf.readfile(str(salida))
    contornos = [
        e for e in doc.modelspace() if e.dxf.layer == SHEET_LAYER
    ]
    assert len(contornos) == 2
    xs = [[p[0] for p in c.get_points("xy")] for c in contornos]
    assert max(xs[0]) == pytest.approx(600.0)
    assert min(xs[1]) >= max(xs[0])
```

`drawing_with`, `square_part` y `square_entities` son los helpers que ya
existen en ese archivo (líneas 12-33). No crear otros.

Agregar a `tests/io/test_preview.py`:

```python
def test_el_lienzo_acomoda_placas_de_medidas_distintas(tmp_path):
    from PIL import Image

    from nesting.model.sheet import Sheet

    hojas = [
        Sheet(600.0, 800.0, grain_tolerance=180.0, scrap=True),
        Sheet(1830.0, 2600.0, grain_tolerance=180.0),
    ]
    salida = tmp_path / "preview.png"
    write_preview(salida, [], [], hojas, [0.0, 0.0], px_per_mm=0.1)

    with Image.open(salida) as imagen:
        ancho, alto = imagen.size

    # El ancho suma los dos anchos más tres separaciones; el alto lo pone la
    # placa más alta, no la primera.
    assert ancho == pytest.approx(round(600 * 0.1) + round(1830 * 0.1) + 3 * 8, abs=4)
    assert alto > round(2600 * 0.1)
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/geometry/test_verify.py tests/io/test_dxf_writer.py tests/io/test_preview.py -v`
Expected: FAIL con `TypeError` por la cantidad de argumentos en las tres
firmas nuevas.

- [ ] **Step 3: `verify` por placa**

En `src/nesting/geometry/verify.py`, cambiar la firma y mover el cálculo del
área útil adentro del bucle:

```python
def verify(
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheets: Sequence[Sheet],
    sep: float,
    margin: float,
) -> list[Violation]:
    """Revisa un layout terminado. Una lista vacía significa que está sano.

    `sheets` tiene que cubrir cada índice que usen las colocaciones: es lo
    que permite que cada pieza se verifique contra SU placa. Un recorte de
    600x800 y una placa de 1830x2600 aceptan piezas distintas, y verificar
    la primera contra la medida de la segunda es exactamente el "todo bien"
    equivocado que esta función existe para impedir.
    """
    if sep < 0 or margin < 0:
        raise ValueError(
            f"verify: 'sep' y 'margin' tienen que ser >= 0 (se recibió sep={sep!r}, "
            f"margin={margin!r})"
        )

    by_id = {p.id: p for p in parts}
    violations: list[Violation] = []

    by_sheet: dict[int, list[Placement]] = {}
    for placement in placements:
        by_sheet.setdefault(placement.sheet, []).append(placement)

    fuera_de_rango = [i for i in by_sheet if not (0 <= i < len(sheets))]
    if fuera_de_rango:
        raise ValueError(
            f"verify: hay colocaciones en la(s) placa(s) {sorted(fuera_de_rango)}, "
            f"pero se recibieron {len(sheets)} placa(s). No se puede verificar una "
            "pieza contra una placa que no se sabe qué medida tiene."
        )

    for sheet, sheet_placements in sorted(by_sheet.items()):
        hoja = sheets[sheet]
        # box() da vuelta en silencio unos límites invertidos en vez de
        # levantar, así que un margen que se come más de la mitad de
        # cualquiera de las dos medidas produciría una franja "útil"
        # fantasma en el medio de la placa.
        usable_w = hoja.width - 2 * margin
        usable_h = hoja.height - 2 * margin
        usable = (
            box(margin, margin, hoja.width - margin, hoja.height - margin)
            if usable_w > 0 and usable_h > 0
            else None
        )

        polygons = [placed_polygon(by_id[p.part_id], p.transform) for p in sheet_placements]
        ...
```

El resto del bucle queda igual, con dos reemplazos en el mensaje de
`usable is None`: `{sheet_w}x{sheet_h}` pasa a `{hoja.width}x{hoja.height}`.

Agregar el import `from nesting.model.sheet import Sheet`.

- [ ] **Step 4: Offsets acumulados en el DXF**

En `src/nesting/io/dxf_writer.py`:

```python
def write_dxf(
    path: str | Path,
    drawing: Drawing,
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheets: Sequence[Sheet],
    gap: float = DEFAULT_GAP,
) -> None:
    """Escribe cada pieza colocada en un DXF, las placas en una fila horizontal."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4  # millimetres
    msp = doc.modelspace()

    if SHEET_LAYER not in doc.layers:
        doc.layers.add(SHEET_LAYER, color=8)

    # Acumulado y no `indice * (ancho + gap)`: con anchos distintos, esa
    # multiplicación pone la placa 1 encima de la 0.
    offsets: list[float] = []
    x = 0.0
    for hoja in sheets:
        offsets.append(x)
        x += hoja.width + gap

    for hoja, x0 in zip(sheets, offsets):
        _draw_sheet_outline(msp, x0, hoja.width, hoja.height)
```

y en el bucle de colocaciones, reemplazar el cálculo de `offset_x`:

```python
        if not (0 <= placement.sheet < len(offsets)):
            raise UnknownPartError(
                f"la colocación de la pieza {placement.part_id} dice estar en la "
                f"placa {placement.sheet}, pero se recibieron {len(sheets)} placa(s)."
            )
        offset_x = offsets[placement.sheet]
```

Borrar la línea `sheet_count = max(...)`. Agregar el import de `Sheet`.

- [ ] **Step 5: Offsets acumulados y alineación abajo en el preview**

En `src/nesting/io/preview.py`, reemplazar desde la firma hasta el bucle de
dibujo de placas:

```python
def write_preview(
    path: str | Path,
    parts: Sequence[Part],
    placements: Sequence[Placement],
    sheets: Sequence[Sheet],
    utilization: Sequence[float],
    colors: dict[int, tuple[int, int, int]] | None = None,
    px_per_mm: float = 0.15,
) -> None:
    """Dibuja cada placa una al lado de la otra, con su aprovechamiento abajo."""
    colors = colors or {}

    anchos_px = [max(1, round(h.width * px_per_mm)) for h in sheets]
    altos_px = [max(1, round(h.height * px_per_mm)) for h in sheets]
    gap_px = max(1, round(GAP_MM * px_per_mm))
    alto_max_px = max(altos_px, default=1)

    width = sum(anchos_px) + (len(sheets) + 1) * gap_px
    height = alto_max_px + 2 * gap_px + LABEL_BAND_PX

    total_pixels = width * height
    if total_pixels > MAX_CANVAS_PIXELS:
        suggested = px_per_mm * (MAX_CANVAS_PIXELS / total_pixels) ** 0.5
        raise ValueError(
            f"las {len(sheets)} placa(s) con px_per_mm={px_per_mm} generarían un "
            f"lienzo de {width}x{height} px (~{total_pixels / 1e6:.1f} Mpx), por "
            f"encima del límite de {MAX_CANVAS_PIXELS / 1e6:.1f} Mpx que admite "
            f"esta función (Pillow luego se niega a abrir imágenes más grandes "
            f"que eso). Use un px_per_mm de a lo sumo {suggested:.4f}."
        )

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    # Las placas se alinean ABAJO y no arriba: el motor apoya las piezas
    # contra el borde inferior, y con placas de altos distintos alinearlas
    # arriba las dejaría flotando sobre nada. Con todas iguales da
    # exactamente lo mismo que antes.
    piso = gap_px + alto_max_px
    izquierdas: list[int] = []
    x = gap_px
    for ancho_px in anchos_px:
        izquierdas.append(x)
        x += ancho_px + gap_px

    for index, (left, ancho_px, alto_px) in enumerate(
        zip(izquierdas, anchos_px, altos_px)
    ):
        draw.rectangle(
            [left, piso - alto_px, left + ancho_px, piso],
            fill=SHEET_FILL, outline=SHEET_EDGE,
        )
        if index < len(utilization):
            draw.text(
                (left, piso + 4),
                f"Placa {index + 1}   {utilization[index] * 100:.1f}%",
                fill=(60, 60, 60),
            )
```

y en el bucle de piezas, reemplazar el cálculo de origen:

```python
        origin_x = izquierdas[placement.sheet]
        origin_y = piso
```

Borrar la línea `sheets = max(len(utilization), ...)`. Agregar el import de
`Sheet`.

- [ ] **Step 6: Actualizar a los que llaman**

En `src/nesting/cli.py`, las tres llamadas:

```python
        violations = verify(
            parts, result.placements, result.sheets,
            sep=config.sep, margin=config.margin,
        )
```

```python
        write_dxf(args.salida, drawing, parts, result.placements, result.sheets)
```

```python
            write_preview(
                args.preview, parts, result.placements,
                result.sheets, result.utilization,
                colors=_colors_by_part(drawing, parts),
            )
```

En `_print_summary`, reemplazar las dos referencias al material por la última
placa usada:

```python
    ultima = result.sheets[-1] if result.sheets else material.stock_sheet()
    free_height = ultima.height - used_height
```

y en la línea del sobrante, `{material.sheet_w:.0f}` pasa a `{ultima.width:.0f}`.

En `src/nesting_app/corredor.py`, los mismos tres reemplazos, con
`resultado.sheets` en lugar de `result.sheets`, y en el `Resultado` del final:

```python
        sobrante_mm=(
            resultado.sheets[-1].height - costo.alto_ultima
            if resultado.sheets else 0.0
        ),
```

En los tests de `tests/geometry/test_verify.py`, `tests/io/test_dxf_writer.py`
y `tests/io/test_preview.py`, reemplazar cada par `sheet_w, sheet_h` por una
lista de `Sheet` con esa medida, una por placa que use el test.

- [ ] **Step 7: Correr los tests**

Run: `.venv/bin/pytest tests/geometry/test_verify.py tests/io/test_dxf_writer.py tests/io/test_preview.py -v`
Expected: PASS

Run: `.venv/bin/pytest`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add -A src tests
git commit -m "IO: verify, DXF y preview trabajan placa por placa

verify recibe la lista de placas y chequea cada colocación contra la suya,
que es lo que impide que una pieza que se sale de un recorte pase por
buena. Los dos escritores acumulan el offset horizontal en vez de
multiplicar por un ancho fijo, y el preview alinea las placas abajo."
```

---

### Task 5: `Recorte`, `a_supply()` y resolución 1 mm/px

**Files:**
- Modify: `src/nesting/params.py`
- Modify: `src/nesting/cli.py:395`
- Modify: `src/nesting_app/api.py`
- Modify: `src/nesting_app/web/index.html`
- Test: `tests/test_params.py`

**Interfaces:**
- Consumes: `Sheet`, `SheetSupply` (Tarea 1); `Material.stock_sheet()` (Tarea 1).
- Produces:
  - `Recorte(ancho: float, alto: float, cantidad: int = 1, veta_cruzada: bool = False)`
  - `NestParams.recortes: tuple[Recorte, ...] = ()`
  - `NestParams.resolucion: float = 1.0`
  - `a_supply(p: NestParams, material: Material) -> SheetSupply`
  - `RecorteEntrada` en `api.py`, con `a_recorte() -> Recorte`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_params.py`:

```python
from nesting.model.material import Material
from nesting.params import Recorte, a_supply

MDF = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
FENOLICO = Material("fenolico18", 1220.0, 2440.0, grain_tolerance=5.0)


def test_la_resolucion_por_omision_es_uno():
    assert NestParams(material="mdf18").resolucion == 1.0


def test_sin_recortes_el_plan_es_una_sola_placa_infinita():
    plan = a_supply(NestParams(material="mdf18"), MDF)

    assert plan.scraps == ()
    assert plan.sheet(0) == plan.sheet(5) == MDF.stock_sheet()
    assert plan.material_name == "mdf18"


def test_la_cantidad_se_expande_a_una_placa_por_unidad():
    params = NestParams(material="mdf18", recortes=(Recorte(600.0, 800.0, cantidad=3),))
    plan = a_supply(params, MDF)

    assert len(plan.scraps) == 3
    assert all(h.width == 600.0 and h.height == 800.0 for h in plan.scraps)
    assert all(h.scrap for h in plan.scraps)


def test_los_recortes_se_ordenan_de_mayor_a_menor():
    """Si el chico fuera primero, una pieza mediana que sólo entra en el
    grande podría quedar varada porque el grande se llenó de piezas que
    también entraban en el chico."""
    params = NestParams(
        material="mdf18",
        recortes=(Recorte(300.0, 300.0), Recorte(900.0, 900.0), Recorte(600.0, 600.0)),
    )
    plan = a_supply(params, MDF)

    assert [h.width for h in plan.scraps] == [900.0, 600.0, 300.0]


def test_los_recortes_heredan_la_veta_del_material():
    params = NestParams(material="fenolico18", recortes=(Recorte(600.0, 800.0),))
    plan = a_supply(params, FENOLICO)

    assert plan.scraps[0].grain_tolerance == 5.0
    assert plan.scraps[0].cross_grain is False


def test_la_veta_cruzada_viaja_al_plan():
    params = NestParams(
        material="fenolico18", recortes=(Recorte(600.0, 800.0, veta_cruzada=True),)
    )
    assert a_supply(params, FENOLICO).scraps[0].cross_grain is True


def test_un_recorte_mas_grande_que_la_placa_se_acepta():
    params = NestParams(material="mdf18", recortes=(Recorte(3000.0, 3000.0),))
    assert a_supply(params, MDF).scraps[0].width == 3000.0


@pytest.mark.parametrize("recorte, campo, regla", [
    (Recorte(0.0, 800.0), "recorte 1: ancho", "> 0"),
    (Recorte(600.0, -1.0), "recorte 1: alto", "> 0"),
    (Recorte(600.0, 800.0, cantidad=0), "recorte 1: cantidad", ">= 1"),
])
def test_validar_rechaza_un_recorte_invalido(recorte, campo, regla):
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(NestParams(material="mdf18", recortes=(recorte,)))

    assert capturado.value.rota.campo == campo
    assert capturado.value.rota.regla == regla


def test_el_error_dice_cual_de_la_lista():
    params = NestParams(
        material="mdf18", recortes=(Recorte(600.0, 800.0), Recorte(0.0, 800.0))
    )
    with pytest.raises(ParamsInvalidosError) as capturado:
        validar(params)

    assert capturado.value.rota.campo == "recorte 2: ancho"


def test_mensaje_cli_no_se_rompe_con_un_campo_que_no_tiene_flag():
    """Los recortes no vienen de la CLI, así que no tienen flag. Un
    `FLAG_POR_CAMPO[campo]` crudo levantaría KeyError si alguien llegara
    igual hasta acá."""
    rota = ReglaRota("recorte 1: ancho", "> 0", 0.0)
    assert "recorte 1: ancho" in mensaje_cli(rota)
```

Actualizar el import del archivo para incluir `ReglaRota` y `mensaje_cli` si
no están.

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/test_params.py -v`
Expected: FAIL con `ImportError: cannot import name 'Recorte'`

- [ ] **Step 3: Escribir `Recorte`, las reglas y `a_supply`**

En `src/nesting/params.py`, agregar los imports:

```python
from nesting.model.material import Material
from nesting.model.sheet import Sheet, SheetSupply
```

y el tipo, antes de `NestParams`:

```python
@dataclass(frozen=True)
class Recorte:
    """Un pedazo que sobró, para la corrida que viene y nada más.

    No es una entrada del catálogo: el catálogo describe lo que se compra,
    que se repite igual cada vez, y un recorte es de a uno y deja de existir
    cuando se cortó.
    """

    ancho: float
    alto: float
    cantidad: int = 1
    veta_cruzada: bool = False
    """La veta de este pedazo corre a lo ancho y no a lo alto."""
```

En `NestParams`, cambiar el default de resolución y agregar el campo:

```python
    resolucion: float = 1.0
    esfuerzo: str = "normal"
    recortes: tuple[Recorte, ...] = ()
```

Agregar al final de `validar`:

```python
    for indice, recorte in enumerate(p.recortes, start=1):
        if recorte.ancho <= 0:
            raise ParamsInvalidosError(
                ReglaRota(f"recorte {indice}: ancho", "> 0", recorte.ancho)
            )
        if recorte.alto <= 0:
            raise ParamsInvalidosError(
                ReglaRota(f"recorte {indice}: alto", "> 0", recorte.alto)
            )
        if recorte.cantidad < 1:
            raise ParamsInvalidosError(
                ReglaRota(f"recorte {indice}: cantidad", ">= 1", recorte.cantidad)
            )
```

Cambiar `mensaje_cli` para que no dependa de que el campo tenga flag:

```python
def mensaje_cli(rota: ReglaRota) -> str:
    """La redacción de terminal, con el nombre del flag adentro.

    Un campo sin flag -- los recortes, que sólo se cargan desde la interfaz
    -- se nombra tal cual en vez de romper con KeyError.
    """
    nombre = FLAG_POR_CAMPO.get(rota.campo, rota.campo)
    return f"{nombre} tiene que ser {rota.regla}, se recibió {rota.valor}"
```

Y agregar `a_supply` al final del archivo:

```python
def a_supply(p: NestParams, material: Material) -> SheetSupply:
    """Arma el plan de placas: los recortes primero, la del Material después.

    Se ordenan de mayor a menor sin importar en qué orden se cargaron. Meter
    el grande primero evita que una pieza mediana quede varada porque el
    motor gastó el único recorte que la aceptaba en algo chico.
    """
    hojas = [
        Sheet(
            width=recorte.ancho,
            height=recorte.alto,
            grain_tolerance=material.grain_tolerance,
            cross_grain=recorte.veta_cruzada,
            scrap=True,
        )
        for recorte in p.recortes
        for _ in range(recorte.cantidad)
    ]
    hojas.sort(key=lambda hoja: hoja.area, reverse=True)
    return SheetSupply(
        stock=material.stock_sheet(),
        scraps=tuple(hojas),
        material_name=material.name,
    )
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/pytest tests/test_params.py -v`
Expected: PASS

- [ ] **Step 5: Bajar el default de resolución en los otros tres lugares**

En `src/nesting/cli.py:395`, `default=2.0` pasa a `default=1.0`.

En `src/nesting_app/api.py`, en `ParamsEntrada`, `resolucion: float = 2.0`
pasa a `resolucion: float = 1.0`, y se agrega el tipo de entrada y el campo:

```python
class RecorteEntrada(BaseModel):
    ancho: float
    alto: float
    cantidad: int = 1
    veta_cruzada: bool = False

    def a_recorte(self) -> Recorte:
        return Recorte(
            ancho=self.ancho,
            alto=self.alto,
            cantidad=self.cantidad,
            veta_cruzada=self.veta_cruzada,
        )
```

En `ParamsEntrada`, agregar `recortes: list[RecorteEntrada] = Field(default_factory=list)`
y en `a_params()`, `recortes=tuple(r.a_recorte() for r in self.recortes)`.

En `src/nesting_app/web/index.html`, el campo de resolución pasa a
`value="1"`.

- [ ] **Step 6: Escribir el test del default en la API y en el HTML**

Agregar a `tests/app/test_api_trabajos.py`:

```python
def test_la_resolucion_por_omision_de_la_api_es_uno():
    from nesting_app.api import ParamsEntrada

    assert ParamsEntrada(material="mdf18").a_params().resolucion == 1.0


def test_los_recortes_llegan_al_params():
    from nesting_app.api import ParamsEntrada

    entrada = ParamsEntrada(
        material="mdf18",
        recortes=[{"ancho": 600.0, "alto": 800.0, "cantidad": 2, "veta_cruzada": True}],
    )
    recortes = entrada.a_params().recortes

    assert len(recortes) == 1
    assert recortes[0].cantidad == 2
    assert recortes[0].veta_cruzada is True
```

Agregar a `tests/app/test_web_javascript.py`:

```python
def test_el_campo_de_resolucion_arranca_en_uno(html):
    assert re.search(r'id="resolucion"[^>]*value="1"', html)
```

- [ ] **Step 7: Correr los tests y la suite**

Run: `.venv/bin/pytest tests/app/test_api_trabajos.py tests/app/test_web_javascript.py tests/test_params.py -v`
Expected: PASS

Run: `.venv/bin/pytest`
Expected: PASS. Si `tests/test_cli.py` o `tests/test_cli_full.py` fijaban 2.0
como default de `--resolucion`, actualizar ese número: es el cambio pedido, no
una regresión.

- [ ] **Step 8: Commit**

```bash
git add -A src tests
git commit -m "Parámetros: Recorte, a_supply y resolución 1 mm/px por omisión

Los recortes son un parámetro de la corrida, no una entrada del catálogo.
a_supply expande la cantidad, hereda la veta del material y ordena de
mayor a menor. mensaje_cli deja de romperse con un campo sin flag."
```

---

### Task 6: El corredor arma el plan, y el reparto llega a la pantalla

**Files:**
- Modify: `src/nesting_app/corredor.py`
- Modify: `src/nesting_app/jobs.py:42-58`
- Modify: `src/nesting_app/api.py:376-382`
- Test: `tests/app/test_corredor.py`, `tests/app/test_api_trabajos.py`

**Interfaces:**
- Consumes: `a_supply` (Tarea 5), `PackResult.sheets` (Tarea 2).
- Produces: `Resultado.recortes_usados: int`, y la clave `"recortes_usados"` en el JSON de `/api/trabajos/{id}`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/app/test_corredor.py`:

Agregar `Recorte` al import de `nesting.params` que ya tiene el archivo.

```python
def test_el_resultado_cuenta_cuantos_recortes_se_usaron(tmp_path, deposito):
    """El reparto lo cuenta el motor, que ya sabe qué placa fue cada una.
    Si lo recontara la pantalla, serían dos fuentes de verdad para el mismo
    número."""
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200), (300, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(
        fuente,
        params(recortes=(Recorte(700.0, 700.0),), resolucion=4.0),
        lambda a: True,
        salida,
    )

    assert resultado.placas == 1
    assert resultado.recortes_usados == 1


def test_sin_recortes_el_reparto_es_cero(tmp_path, deposito):
    fuente = deposito.registrar_local(dxf_con(tmp_path, [(0, 0, 200)]))
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(
        fuente, params(resolucion=4.0), lambda a: True, salida
    )

    assert resultado.recortes_usados == 0
```

`deposito`, `dxf_con` y `params(**cambios)` son los helpers y fixtures que ese
archivo ya tiene (líneas 23-54). Las dos piezas de 200 mm entran de sobra en
un recorte de 700x700 con el borde de 10 mm por omisión, así que el acomodo
cierra en una sola placa y esa placa es el recorte.

Agregar a `tests/app/test_api_trabajos.py`:

```python
def test_el_json_del_trabajo_trae_el_reparto_de_placas():
    from nesting_app.jobs import Resultado

    resultado = Resultado(
        placas=3, aprovechamiento=[0.5, 0.5, 0.5], total=0.5, segundos=1.0,
        sobrante_mm=100.0, material_ultima_placa_m2=0.1,
        carpeta=Path("/tmp"), recortes_usados=2,
    )
    assert resultado.recortes_usados == 2
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_corredor.py -k recorte -v`
Expected: FAIL con `TypeError: NestParams.__init__() got an unexpected keyword`
o `AttributeError: 'Resultado' object has no attribute 'recortes_usados'`.

- [ ] **Step 3: Agregar el campo a `Resultado`**

En `src/nesting_app/jobs.py`, agregar después de `avisos`:

```python
    recortes_usados: int = 0
    """Cuántas de las placas del acomodo eran recortes.

    Va acá y no se recalcula en la pantalla porque el motor ya lo sabe:
    `PackResult.sheets` dice qué fue cada placa. Contarlo dos veces sería
    tener dos fuentes de verdad para el mismo número.

    Va último por la regla de los dataclass -- los campos con valor por
    omisión van después de los que no lo tienen -- y no porque importe
    menos que `placas`.
    """
```

- [ ] **Step 4: Armar el plan con los recortes en el corredor**

En `src/nesting_app/corredor.py`, cambiar el import de `nesting.params` a
`from nesting.params import NestParams, a_config, a_supply` y reemplazar la
construcción del `SheetSupply` que dejó la Tarea 2:

```python
        supply = a_supply(params, material)
        resultado = pack(
            piezas, supply, config, lambda: RasterOracle(cache=cache), progreso=progreso
        )
```

y en el `Resultado` del final, agregar:

```python
        recortes_usados=sum(1 for hoja in resultado.sheets if hoja.scrap),
```

- [ ] **Step 5: Serializarlo en la API**

En `src/nesting_app/api.py`, agregar la clave al diccionario del resultado:

```python
                "recortes_usados": trabajo.resultado.recortes_usados,
```

- [ ] **Step 6: Fijar que un recorte no convierte una pieza en contorno de placa**

Es una decisión del spec (sección 2.7) que se toma **no** haciendo nada, y
por eso necesita un test: sin él, el próximo que lea el código va a
"arreglar" la inconsistencia y va a hacer desaparecer piezas.

Agregar a `tests/app/test_corredor.py`:

```python
def test_una_pieza_del_tamano_de_un_recorte_no_se_descarta(tmp_path, deposito):
    """`discard_plate_outline` tira los rectángulos del tamaño exacto de la
    placa, porque son la previsualización que alguien dibujó en su CAD.
    Mirar también las medidas de los recortes parece consistente y es una
    trampa: con 1830x2600 el choque es improbable, pero una medida de
    recorte ES una medida de pieza. Esta pieza de 600x800 tiene que
    sobrevivir a que haya un recorte de 600x800 cargado."""
    ruta = dxf_con(tmp_path, [])
    import ezdxf

    doc = ezdxf.readfile(str(ruta))
    doc.modelspace().add_lwpolyline(
        [(0, 0), (600, 0), (600, 800), (0, 800)], close=True
    )
    doc.saveas(ruta)

    fuente = deposito.registrar_local(ruta)
    salida = tmp_path / "t"
    salida.mkdir()

    resultado = corredor.acomodar(
        fuente,
        params(recortes=(Recorte(600.0, 800.0),), resolucion=4.0),
        lambda a: True,
        salida,
    )

    # Si se hubiera descartado, no quedaría ninguna pieza y `acomodar`
    # habría levantado "no se encontró ninguna pieza".
    assert resultado.placas == 1
```

- [ ] **Step 7: Correr el test**

Run: `.venv/bin/pytest tests/app/test_corredor.py -k recorte -v`
Expected: PASS sin tocar `discard_plate_outline`. **Si falla, no cambies el
test: significa que alguna tarea anterior le pasó las medidas de los recortes
a esa función, y eso hay que revertirlo.**

- [ ] **Step 8: Correr los tests y la suite**

Run: `.venv/bin/pytest tests/app -v`
Expected: PASS

Run: `.venv/bin/pytest`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add -A src tests
git commit -m "Corredor: arma el plan con los recortes del pedido

Resultado lleva cuántas placas eran recortes, calculado por el motor que
ya lo sabe, y la API lo serializa para que la pantalla no tenga que
recontarlo. Un test fija que discard_plate_outline sigue mirando sólo la
placa del Material: mirar las medidas de los recortes haría desaparecer
piezas reales sin aviso."
```

---

### Task 7: La pantalla — el bloque de recortes

**Files:**
- Modify: `src/nesting_app/web/index.html`
- Modify: `src/nesting_app/web/app.js`
- Modify: `src/nesting_app/web/app.css`
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: la clave `recortes` que `ParamsEntrada` acepta (Tarea 5), `recortes_usados` del JSON (Tarea 6).
- Produces: `estado.recortes` en `window.__nesting.estado`, ids `lista-recortes`, `alta-recorte`, `r-ancho`, `r-alto`, `r-cantidad`, `r-cruzada`, `btn-agregar-recorte`, `btn-confirmar-recorte`, `btn-cancelar-recorte`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/app/test_web_javascript.py`:

```python
def test_los_recortes_viven_en_el_estado_de_la_sesion(js):
    assert "recortes: []" in js or "recortes: [ ]" in js


def test_registrar_no_borra_los_recortes(js):
    """Cambiar de archivo no tira los pedazos que hay contra la pared. Se
    pierden al cerrar el programa, no al abrir otro dibujo."""
    assert "recortes" not in _cuerpo_de_funcion(js, "registrar")


def test_los_recortes_se_mandan_con_los_parametros(js):
    assert "recortes: estado.recortes" in _cuerpo_de_funcion(js, "parametros")


def test_la_casilla_de_veta_cruzada_se_apaga_en_un_material_sin_veta(js):
    """Mira el cuerpo de la función y no el archivo: la primera versión de
    este test afirmaba `"disabled" in js`, y esa cadena ya estaba en el
    botón de guardar -- pasaba antes de que la casilla existiera."""
    cuerpo = _cuerpo_de_funcion(js, "ajustarVetaCruzada")

    assert '=== "libre"' in cuerpo
    assert '$("r-cruzada").disabled' in cuerpo


def test_el_bloque_de_recortes_tiene_sus_controles(html):
    for id_ in [
        "lista-recortes", "alta-recorte", "r-ancho", "r-alto", "r-cantidad",
        "r-cruzada", "btn-agregar-recorte", "btn-confirmar-recorte",
        "btn-cancelar-recorte",
    ]:
        assert f'id="{id_}"' in html, id_


def test_el_reparto_de_placas_se_muestra_al_terminar(js):
    assert "recortes_usados" in js
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -k recorte -v`
Expected: FAIL, todos, con `AssertionError`.

- [ ] **Step 3: Agregar el bloque al HTML**

En `src/nesting_app/web/index.html`, después del `<div class="campo">` del
Material y antes del de Separación:

```html
    <div class="campo">
      <!-- Debajo de Material y no en Opciones avanzadas: un recorte cambia
           sobre qué se corta, igual que el material. No es un ajuste fino. -->
      <div class="renglon-etiqueta">
        <span class="titulo-campo">
          <span class="etiqueta">Recortes</span>
          <button type="button" class="boton-info" data-info="recortes" aria-label="Qué es Recortes" aria-expanded="false"><svg viewBox="0 0 16 16" class="icono" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="6.25"></circle><path d="M8 7.5v3.5"></path><path d="M8 5v.01"></path></svg></button>
        </span>
        <button type="button" id="btn-agregar-recorte" class="enlace">Agregar</button>
      </div>
      <ul id="lista-recortes" class="lista-recortes"></ul>
      <div id="alta-recorte" class="alta-recorte oculto">
        <div class="fila">
          <div class="control con-unidad">
            <input id="r-ancho" type="number" min="1" step="1" class="medida" aria-label="Ancho del recorte">
            <span class="unidad">mm</span>
          </div>
          <div class="control con-unidad">
            <input id="r-alto" type="number" min="1" step="1" class="medida" aria-label="Alto del recorte">
            <span class="unidad">mm</span>
          </div>
          <div class="control">
            <input id="r-cantidad" type="number" min="1" step="1" value="1" class="medida" aria-label="Cuántos recortes de esta medida">
          </div>
        </div>
        <label class="casilla" id="etiqueta-cruzada">
          <input id="r-cruzada" type="checkbox"> Veta cruzada
        </label>
        <div class="fila">
          <button type="button" id="btn-confirmar-recorte" class="boton secundario">Agregar</button>
          <button type="button" id="btn-cancelar-recorte" class="enlace">Cancelar</button>
        </div>
      </div>
      <p class="error-campo oculto" data-error-de="recortes"></p>
    </div>
```

- [ ] **Step 4: Escribir el JavaScript**

En `src/nesting_app/web/app.js`, agregar `recortes: []` al objeto `estado`
(después de `descartes: 0,`), con el comentario:

```js
  // Sobrevive a cambiar de archivo y se pierde al cerrar el programa:
  // `registrar()` no lo toca a propósito. Un recorte anotado tres semanas
  // después ya se cortó o se traspapeló, así que guardarlo en disco sería
  // guardar una mentira.
  recortes: [],
```

Agregar una sección nueva, después de `// --- elegir el archivo ---`:

```js
// --- recortes ---------------------------------------------------------------

function dibujarRecortes() {
  const lista = $("lista-recortes");
  lista.innerHTML = "";
  estado.recortes.forEach((r, indice) => {
    const fila = document.createElement("li");
    const texto = document.createElement("span");
    texto.textContent =
      `${r.ancho} × ${r.alto} mm  ×${r.cantidad}` +
      (r.veta_cruzada ? " · veta cruzada" : "");
    const quitar = document.createElement("button");
    quitar.type = "button";
    quitar.className = "enlace";
    quitar.setAttribute(
      "aria-label", `Quitar el recorte de ${r.ancho} por ${r.alto}`
    );
    quitar.textContent = "✕";
    quitar.onclick = () => {
      estado.recortes.splice(indice, 1);
      dibujarRecortes();
    };
    fila.append(texto, quitar);
    lista.append(fila);
  });
}

function abrirAltaRecorte(abierta) {
  $("alta-recorte").classList.toggle("oculto", !abierta);
  $("btn-agregar-recorte").classList.toggle("oculto", abierta);
  if (abierta) $("r-ancho").focus();
}

$("btn-agregar-recorte").onclick = () => abrirAltaRecorte(true);
$("btn-cancelar-recorte").onclick = () => abrirAltaRecorte(false);

$("btn-confirmar-recorte").onclick = () => {
  const ancho = Number($("r-ancho").value);
  const alto = Number($("r-alto").value);
  const cantidad = Number($("r-cantidad").value);
  limpiarErroresDeCampo();
  if (!(ancho > 0) || !(alto > 0) || !(cantidad >= 1)) {
    return marcarCampo(
      "recortes",
      "poné un ancho y un alto mayores que cero, y al menos una unidad"
    );
  }
  estado.recortes.push({
    ancho,
    alto,
    cantidad,
    veta_cruzada: $("r-cruzada").checked,
  });
  $("r-ancho").value = "";
  $("r-alto").value = "";
  $("r-cantidad").value = "1";
  $("r-cruzada").checked = false;
  abrirAltaRecorte(false);
  dibujarRecortes();
};

// En un material de veta libre la casilla no cambiaría nada, así que se
// apaga en vez de quedar marcable y muda. Los recortes YA cargados
// conservan su bandera: en un material libre no hace daño (todos los
// ángulos están permitidos igual), y si se vuelve a un material con veta
// tiene que seguir valiendo lo que el usuario dijo del pedazo.
let vetaPorMaterial = {};

function ajustarVetaCruzada() {
  const libre = vetaPorMaterial[$("material").value] === "libre";
  $("r-cruzada").disabled = libre;
  if (libre) $("r-cruzada").checked = false;
  $("etiqueta-cruzada").classList.toggle("deshabilitada", libre);
}

$("material").addEventListener("change", ajustarVetaCruzada);
```

En `parametros()`, agregar:

```js
    recortes: estado.recortes,
```

En `refrescarMateriales()`, poblar el mapa y ajustar la casilla, justo antes
del `return`:

```js
  vetaPorMaterial = Object.fromEntries(
    datos.materiales.map((m) => [m.nombre, m.veta])
  );
  ajustarVetaCruzada();
```

En `terminar()`, cambiar la línea de las placas:

```js
  const r = t.resultado;
  const nuevas = r.placas - r.recortes_usados;
  const placas =
    r.recortes_usados > 0
      ? `${r.placas} placas (${r.recortes_usados} recorte${
          r.recortes_usados === 1 ? "" : "s"
        } + ${nuevas} nueva${nuevas === 1 ? "" : "s"})`
      : r.placas === 1
        ? "1 placa"
        : `${r.placas} placas`;
```

Agregar `dibujarRecortes` al objeto `window.__nesting`.

- [ ] **Step 5: Agregar el CSS**

En `src/nesting_app/web/app.css`, al final de la sección de campos:

```css
.lista-recortes {
  list-style: none;
  margin: 0.25rem 0 0;
  padding: 0;
  display: grid;
  gap: 0.125rem;
}

.lista-recortes li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--texto-2);
}

.lista-recortes li span {
  flex: 1;
}

.alta-recorte {
  display: grid;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding: 0.625rem;
  background: var(--panel);
  border: 1px solid var(--borde);
  border-radius: var(--radio);
}

.casilla.deshabilitada {
  opacity: 0.45;
}
```

- [ ] **Step 6: Correr los tests**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -v`
Expected: PASS

Run: `.venv/bin/pytest tests/app -v`
Expected: PASS. Si `test_no_hay_emojis_en_la_interfaz` rechaza el `✕`,
reemplazarlo por un SVG en línea con dos trazos cruzados, como los demás
íconos del archivo.

- [ ] **Step 7: Commit**

```bash
git add -A src tests
git commit -m "Pantalla: cargar recortes para la sesión actual

Debajo de Material, porque un recorte cambia sobre qué se corta. Viven en
estado.recortes: sobreviven a cambiar de archivo y se pierden al cerrar.
La casilla de veta cruzada se apaga en un material de veta libre."
```

---

### Task 8: La pantalla — ángulos por cantidad de posiciones

**Files:**
- Modify: `src/nesting_app/web/index.html`
- Modify: `src/nesting_app/web/app.js:481-497`
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `angulosElegidos()` en lugar de `angulosDelCampo()`; id `posiciones` y id `campo-angulos`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/app/test_web_javascript.py`:

```python
def _opciones_de_posiciones(html: str) -> str:
    """El `<select id="posiciones">` solo, sin el resto de la página.

    Buscar `value="4"` en el HTML entero pasaría por cualquier campo
    numérico que tenga un 4 adelante."""
    desde = html.index('id="posiciones"')
    return html[desde : html.index("</select>", desde)]


@pytest.mark.parametrize("valor", ["4", "8", "16", "personalizado"])
def test_el_desplegable_de_posiciones_tiene_las_cuatro_opciones(html, valor):
    assert f'value="{valor}"' in _opciones_de_posiciones(html)


def test_las_posiciones_arrancan_en_cuatro(html):
    assert re.search(
        r'<option value="4"[^>]*selected', _opciones_de_posiciones(html)
    )


def test_las_posiciones_se_reparten_en_la_vuelta_entera(js):
    """4 posiciones son 0/90/180/270 y 16 son cada 22,5 grados. La cuenta
    tiene que ser i * 360 / n, no una tabla de ángulos escrita a mano: una
    tabla se desincroniza de las etiquetas del desplegable en cuanto
    alguien agregue 32."""
    cuerpo = _cuerpo_de_funcion(js, "angulosElegidos")

    assert "360" in cuerpo
    assert "Array.from" in cuerpo


def test_personalizado_revela_el_campo_de_texto(js):
    cuerpo = _cuerpo_de_funcion(js, "angulosElegidos")
    assert '"personalizado"' in cuerpo
    assert "campo-angulos" in js


def test_el_campo_de_angulos_sigue_validandose(js):
    """Sólo en la rama Personalizado, pero con el mismo error debajo del
    campo que tenía antes."""
    assert "angulosElegidos" in _cuerpo_de_funcion(js, "angulosValidos")
    assert '"angulos"' in js
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -k "posiciones or personalizado" -v`
Expected: FAIL con `AssertionError`.

- [ ] **Step 3: Agregar el desplegable al HTML**

En `src/nesting_app/web/index.html`, dentro de `<details id="avanzadas">`,
antes del campo de Ángulos:

```html
      <div class="campo">
        <div class="titulo-campo">
          <label class="etiqueta" for="posiciones">Posiciones</label>
          <button type="button" class="boton-info" data-info="posiciones" aria-label="Qué es Posiciones" aria-expanded="false"><svg viewBox="0 0 16 16" class="icono" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="6.25"></circle><path d="M8 7.5v3.5"></path><path d="M8 5v.01"></path></svg></button>
        </div>
        <div class="desplegable">
          <select id="posiciones" class="control">
            <option value="4" selected>4 — 0, 90, 180, 270</option>
            <option value="8">8 — cada 45°</option>
            <option value="16">16 — cada 22,5°</option>
            <option value="personalizado">Personalizado</option>
          </select>
          <svg viewBox="0 0 16 16" class="icono flecha" aria-hidden="true"><path d="M4 6.5l4 4 4-4"></path></svg>
        </div>
      </div>
```

y al `<div class="campo">` que contiene el input `angulos`, agregarle
`id="campo-angulos"` y la clase `oculto`:

```html
      <div class="campo oculto" id="campo-angulos">
```

- [ ] **Step 4: Reemplazar `angulosDelCampo` por `angulosElegidos`**

En `src/nesting_app/web/app.js`, reemplazar las dos funciones y su comentario:

```js
// Las posiciones son el camino normal: 4, 8 o 16 repartidas en la vuelta
// entera. El campo de texto libre queda para "Personalizado", que es el
// único que puede traer basura -- un "9o" en vez de "90" daba `NaN`,
// `JSON.stringify` lo mandaba como `null`, y el servidor devolvía el 422
// crudo de pydantic. Se corta acá, con el mismo cartel debajo del campo
// que usan los demás parámetros.
function angulosElegidos() {
  const posiciones = $("posiciones").value;
  if (posiciones !== "personalizado") {
    const n = Number(posiciones);
    return Array.from({ length: n }, (_, i) => (i * 360) / n);
  }
  return $("angulos")
    .value.split(",")
    .map((t) => t.trim())
    .filter((t) => t !== "")
    .map(Number);
}

function angulosValidos() {
  const lista = angulosElegidos();
  return lista.length > 0 && lista.every(Number.isFinite);
}

$("posiciones").onchange = () => {
  $("campo-angulos").classList.toggle(
    "oculto", $("posiciones").value !== "personalizado"
  );
};
```

En `parametros()`, `angulos: angulosDelCampo()` pasa a
`angulos: angulosElegidos()`.

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -v`
Expected: PASS. El test `test_los_angulos_se_validan_antes_de_mandarlos` que
ya existía tiene que seguir pasando; si nombra `angulosDelCampo`, actualizarlo
al nombre nuevo.

- [ ] **Step 6: Commit**

```bash
git add -A src tests
git commit -m "Pantalla: ángulos por cantidad de posiciones

4, 8 o 16 repartidas en la vuelta entera, arrancando en 4. El campo de
texto libre queda detrás de Personalizado, con su misma validación."
```

---

### Task 9: La pantalla — solapas y zoom continuo

**Files:**
- Modify: `src/nesting_app/web/index.html`
- Modify: `src/nesting_app/web/app.js:336-420`
- Test: `tests/app/test_web_javascript.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `aplicarNuevoZoom(siguiente, clienteX, clienteY)`, `enPixeles(evento)`, constantes `ZOOM_MIN`, `ZOOM_MAX`, `SENSIBILIDAD`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/app/test_web_javascript.py`:

```python
def test_la_revision_esta_a_la_izquierda_del_resultado(html):
    assert html.index('id="tab-revision"') < html.index('id="tab-preview"')


def test_la_solapa_se_llama_resultado(html):
    assert ">Resultado<" in html
    assert "Previsualización" not in html


def test_la_rueda_no_salta_por_la_escalera(js):
    """La escalera queda para los botones. Cada evento de rueda avanzaba un
    escalón entero, y un gesto de trackpad manda decenas: iba de 25% a 600%
    de un toque."""
    handler = _cuerpo_de_handler(js, "wheel")

    assert "acercar(" not in handler
    assert "zoomContinuo" in handler


def test_la_rueda_normaliza_el_modo_del_delta(js):
    """Firefox reporta líneas y no píxeles: sin normalizar, el mismo gesto
    da un salto distinto en cada navegador."""
    assert "deltaMode" in _cuerpo_de_funcion(js, "enPixeles")


def test_el_zoom_de_la_rueda_esta_acotado(js):
    cuerpo = _cuerpo_de_funcion(js, "zoomContinuo")
    assert "ZOOM_MIN" in cuerpo and "ZOOM_MAX" in cuerpo


def test_los_botones_siguen_usando_la_escalera(js):
    assert "proximoPaso" in _cuerpo_de_funcion(js, "acercar")
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -k "solapa or revision or rueda or zoom" -v`
Expected: FAIL. El de orden de solapas y el de "Resultado" por `AssertionError`;
los de rueda porque el handler todavía llama a `acercar(`.

- [ ] **Step 3: Dar vuelta las solapas**

En `src/nesting_app/web/index.html`, reemplazar los dos botones de solapa:

```html
      <button type="button" id="tab-revision" class="solapa">Revisión</button>
      <button type="button" id="tab-preview" class="solapa activa">Resultado</button>
```

Los ids no cambian: `tab-preview` sigue siendo el de la imagen `preview.png`
que sirve el servidor, y renombrarlo sería churn en cinco archivos sin nada a
cambio.

- [ ] **Step 4: Extraer el anclaje del zoom y hacer la rueda continua**

En `src/nesting_app/web/app.js`, reemplazar `acercar` por dos funciones y
agregar las constantes, justo después de `proximoPaso`:

```js
const ZOOM_MIN = 0.1;
const ZOOM_MAX = PASOS_ZOOM[PASOS_ZOOM.length - 1];

// Cuánto zoom por píxel de scroll. Con 0.0015, una muesca de rueda típica
// (100 px) mueve el zoom un 16% y un gesto de trackpad completo recorre el
// rango sin pasarse. Es un número de tacto: se ajusta probándolo.
const SENSIBILIDAD = 0.0015;

// `deltaY` no viene en píxeles en todos lados: Firefox reporta líneas
// (deltaMode 1) y hay quien reporta páginas (2). Sin normalizar, el mismo
// gesto salta distinto en cada navegador.
const PIXELES_POR_MODO = [1, 16, 100];
function enPixeles(e) {
  return e.deltaY * (PIXELES_POR_MODO[e.deltaMode] ?? 1);
}

// El anclaje al cursor lo comparten la rueda y los botones: sin esto el
// zoom se va siempre al centro y perseguir un detalle es un juego de
// paciencia.
function aplicarNuevoZoom(siguiente, clienteX, clienteY) {
  const img = imagenDelLienzo();
  if (!img || siguiente === null) return;
  const lienzo = $("lienzo");
  const antes = zoom ?? escalaAjustada(img);
  if (siguiente === antes) return;

  const caja = img.getBoundingClientRect();
  const enImagenX = (clienteX - caja.left) / antes;
  const enImagenY = (clienteY - caja.top) / antes;

  zoom = siguiente;
  aplicarZoom();

  const nueva = img.getBoundingClientRect();
  lienzo.scrollLeft += nueva.left + enImagenX * zoom - clienteX;
  lienzo.scrollTop += nueva.top + enImagenY * zoom - clienteY;
}

// Los botones y el doble clic siguen con la escalera: ahí los números
// redondos sirven, y un clic es un paso, no un gesto.
function acercar(direccion, clienteX, clienteY) {
  const img = imagenDelLienzo();
  if (!img) return;
  const antes = zoom ?? escalaAjustada(img);
  aplicarNuevoZoom(proximoPaso(antes, direccion), clienteX, clienteY);
}

function zoomContinuo(delta, clienteX, clienteY) {
  const img = imagenDelLienzo();
  if (!img) return;
  const antes = zoom ?? escalaAjustada(img);
  const siguiente = Math.min(
    ZOOM_MAX, Math.max(ZOOM_MIN, antes * Math.exp(-delta * SENSIBILIDAD))
  );
  aplicarNuevoZoom(siguiente, clienteX, clienteY);
}
```

y reemplazar el handler de la rueda:

```js
$("lienzo").addEventListener("wheel", (e) => {
  if (!imagenDelLienzo()) return;
  // `preventDefault` sólo cuando hay imagen: si no, se come el scroll del
  // mensaje de texto que el lienzo muestra cuando todavía no hay nada.
  e.preventDefault();
  zoomContinuo(enPixeles(e), e.clientX, e.clientY);
}, { passive: false });
```

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -v`
Expected: PASS. Los tests que ya existían
`test_el_zoom_arranca_ajustado_en_cada_imagen` y
`test_la_rueda_acerca_donde_esta_el_cursor` tienen que seguir pasando; si el
segundo buscaba `acercar(` adentro del handler, actualizarlo para que busque
el anclaje en `aplicarNuevoZoom`.

- [ ] **Step 6: Commit**

```bash
git add -A src tests
git commit -m "Pantalla: Revisión primero, Resultado después, y zoom de rueda continuo

La rueda multiplica por un factor exponencial en deltaY, normalizado por
deltaMode y acotado. Los botones y el doble clic conservan la escalera."
```

---

### Task 10: Globos de ayuda y README

**Files:**
- Modify: `src/nesting_app/web/info.js`
- Modify: `README.md`, `README.es.md`
- Modify: `src/nesting/engine/packer.py` (la nota de tiempos)
- Test: `tests/app/test_web_javascript.py` (o el archivo de tests de `info.js` si existe uno aparte)

**Interfaces:**
- Consumes: los `data-info="recortes"` y `data-info="posiciones"` que dejaron las tareas 7 y 8.
- Produces: nada que consuma otra tarea.

- [ ] **Step 1: Escribir el test que falla**

No hay test nuevo que escribir: `test_cada_boton_del_html_tiene_su_texto_y_al_reves`
(`tests/app/test_web_javascript.py:817`) ya compara los dos conjuntos, y las
tareas 7 y 8 dejaron dos botones `data-info` sin texto. Correrlo para verlo
fallar:

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -k boton_del_html -v`
Expected: FAIL con `sólo en el HTML: ['posiciones', 'recortes']`

- [ ] **Step 2: Escribir los dos globos y reescribir el de resolución**

En `src/nesting_app/web/info.js`, agregar al mapa de textos:

**El formato del literal `TEXTOS` no es libre:** `claves_y_textos()` en
`tests/app/test_web_javascript.py:653` lo parsea con una expresión regular, y
otro test obliga a que siga siendo parseable. Eso significa **clave entre
comillas y un par clave/valor por línea**, sin concatenar con `+` y sin
partir en varias líneas. Las entradas nuevas van así, cada una en un renglón:

```js
  "recortes": "Pedazos que te sobraron y querés usar antes de abrir una placa nueva. Valen sólo para esta sesión: no se guardan en el catálogo y se pierden al cerrar. El acomodo los llena primero, del más grande al más chico, y recién después abre placas del Material. Uno donde no entre ninguna pieza se saltea.",
  "posiciones": "En cuántas posiciones puede girar cada pieza, repartidas en la vuelta entera: 4 son 0, 90, 180 y 270; 8 agrega las diagonales; 16 va cada 22,5 grados. Más posiciones ganan lugar y tardan más. La veta del material puede prohibir algunas. Personalizado te deja escribir la lista a mano.",
```

y reemplazar el renglón de `resolucion`, que hoy nombra 2 mm como buen punto,
por uno que nombre el valor por omisión nuevo:

```js
  "resolucion": "Cuántos milímetros mide cada píxel con el que el programa \"ve\" la placa. Más fino acomoda mejor y tarda mucho más: bajar de 2 a 1 cuadruplica el trabajo. Arranca en 1; si un archivo grande tarda demasiado, subirlo a 2 es lo primero que conviene probar.",
```

- [ ] **Step 3: Correr el test**

Run: `.venv/bin/pytest tests/app/test_web_javascript.py -v`
Expected: PASS. Si falla el test que vigila el formato del literal, la entrada
nueva se partió en varias líneas o le faltan las comillas en la clave.

- [ ] **Step 4: Actualizar la nota de tiempos del packer**

En `src/nesting/engine/packer.py`, en el docstring de `EFFORT_RESTARTS`, en el
párrafo "EL PRESUPUESTO DE 5 MINUTOS, HONESTAMENTE", agregar al final:

```
TODO LO DE ARRIBA SE MIDIÓ A 2.0 mm/px, QUE YA NO ES EL VALOR POR OMISIÓN.
Desde los recortes, `NestParams.resolucion` arranca en 1.0: cuatro veces los
píxeles del raster, así que cuatro veces el trabajo de rasterizar y de
buscar. Ninguno de los números de esta nota se volvió a medir a 1.0, y no
hay razón para creer que escalen de forma simple. Valen como comparación
entre niveles de esfuerzo a una misma resolución, no como pronóstico de
cuánto va a tardar una corrida con los valores de hoy.
```

- [ ] **Step 5: Actualizar los dos README**

En `README.es.md`, en la tabla de opciones, agregar estas dos filas (adaptando
las columnas a las que la tabla ya tenga) y editar la de Resolución:

| Opción | Qué hace | Por omisión |
|---|---|---|
| Recortes | Pedazos sueltos que ya tenés y querés usar antes de abrir una placa nueva. Se cargan con medida y cantidad, se llenan del más grande al más chico, y valen sólo mientras el programa está abierto: no van al catálogo. **Sólo en la interfaz; la CLI no los acepta.** | ninguno |
| Posiciones | En cuántas posiciones puede girar cada pieza, repartidas en la vuelta entera: 4, 8 o 16. `Personalizado` revela el campo Ángulos para escribir la lista a mano. | 4 |
| Resolución | Milímetros por píxel con los que el motor prueba dónde entra cada pieza. Bajar de 2 a 1 cuadruplica el trabajo. | 1 mm/px |

En la fila de `Ángulos`, agregar que ahora vive detrás de `Posiciones →
Personalizado`.

En la sección de la CLI, cambiar el default de `--resolucion` a 1.0. **No
agregar ninguna bandera de recortes**: la CLI no los acepta, y documentar una
que no existe es peor que no documentarla.

En `README.md`, las mismas tres filas y los mismos dos cambios, en inglés.

- [ ] **Step 6: Correr la suite entera**

Run: `.venv/bin/pytest`
Expected: PASS, todo.

- [ ] **Step 7: Commit**

```bash
git add -A src tests README.md README.es.md
git commit -m "Globos de Recortes y Posiciones, y la nota de tiempos al día

El globo de Resolución nombraba 2 mm/px como valor por omisión. La nota de
EFFORT_RESTARTS dice ahora a qué resolución se midió y que el default ya
no es esa: sus números valen para comparar esfuerzos, no para pronosticar
cuánto tarda una corrida de hoy."
```

---

## Verificación final

Antes de dar el trabajo por terminado, con la suite en verde:

- [ ] Correr una corrida real sin recortes y comparar contra una corrida de
      antes del plan (`git stash` sobre el mismo archivo y material): mismas
      placas, mismo aprovechamiento, mismo sobrante. Si difieren, alguna de
      las tareas 2 o 4 movió algo que no debía.
- [ ] Correr una corrida con dos recortes chicos y confirmar en la
      previsualización que se llenaron primero y que las medidas de los
      rectángulos son las cargadas.
- [ ] Abrir el DXF resultante en un visor y confirmar que las placas no se
      pisan y que cada contorno tiene su medida.
- [ ] Cargar un recorte donde no entre ninguna pieza y confirmar que no
      aparece en la previsualización.
- [ ] Con el material en fenólico, cargar un recorte con veta cruzada y
      confirmar que las piezas ahí salen giradas 90 grados respecto de las de
      la placa entera.
- [ ] Cambiar a mdf18 y confirmar que la casilla de veta cruzada queda apagada.
- [ ] Probar el zoom con trackpad y con rueda: que se pueda parar en un valor
      intermedio y volver al mismo lugar deshaciendo el gesto.
