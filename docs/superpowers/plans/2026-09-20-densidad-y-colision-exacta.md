# Densidad de acomodo y colisión exacta — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el motor acomode las piezas lo más juntas posible respetando la separación **real** pedida, que elija el layout que deja menos material en la última placa, y que le muestre al usuario las dos cifras que compiten (material en la última placa y largo de la tira sobrante) para que decida.

**Architecture:** Hoy la grilla de raster es *conservadora*: sobre-representa cada pieza para no colocar nunca dos demasiado cerca. Esa seguridad cuesta 3 mm por lado a 2 mm/px, que se convierten en 6 mm de separación fantasma entre piezas (medido: 16 mm reales cuando se piden 10). Este plan **invierte el papel de la grilla**: pasa a ser un generador *optimista* de candidatos — rápido, admite un poco de más — y la geometría exacta de shapely pasa a ser el árbitro. La grilla conserva su velocidad; shapely devuelve la separación exacta. Encima de eso, el criterio de "mejor layout" deja de mirar sólo el alto de la última placa y pasa a mirar cuánto material queda en ella, y una pasada de recuperación intenta subir a las placas anteriores lo que quedó en la última.

**Tech Stack:** Python 3.13, numpy, scipy, shapely (ya son dependencias). Ninguna dependencia nueva.

## Por qué no NFP, que era la idea original

Se midió sobre el archivo de referencia del usuario (`NESTING 2.ai`, 36 piezas):

- Las piezas tienen entre **257 y 1064 vértices** (mediana 895) después de aplanar las curvas.
- Un no-fit-polygon exacto entre dos piezas no convexas se arma descomponiendo en convexos y uniendo las sumas de Minkowski por pares: **~800.000 sumas para UN solo par**, por cada ángulo. Con 36 piezas × 8 orientaciones es inviable, en Python y fuera de Python.
- En cambio, `shapely.distance()` entre dos de esas piezas cuesta **312 µs**. La geometría exacta es barata como *árbitro*, carísima como *buscador*.

De ahí la arquitectura híbrida. Ya se prototipó y se midió sobre el archivo real:

| | Placa 1 / Placa 2 | Aprov. | Material en placa 2 | Sobrante | Separación real | Violac. | Tiempo |
|---|---|---|---|---|---|---|---|
| Hoy (2 mm/px, Lento) | 29 / 7 | 49.6% | 0.264 m² | 2292 mm | 16.0 mm | 0 | 116 s |
| Híbrido (2 mm/px, Rápido) | 33 / 3 | 52.9% | — | — | 10.0 mm | 0 | 15 s |
| Híbrido (1 mm/px, Rápido) | 33 / 3 | 52.9% | — | — | 10.0 mm | 0 | 74 s |
| **Híbrido + criterio (2 mm/px, Normal)** | **34 / 2** | **53.5%** | **0.075 m²** | **2292 mm** | **10.0 mm** | **0** | **44 s** |
| Híbrido + criterio (2 mm/px, Lento) | 34 / 2 | 53.5% | 0.075 m² | 2292 mm | 10.0 mm | 0 | 167 s |

Tres cosas que salen de esa tabla y condicionan el plan:

1. **El material en la última placa baja 72%** (0.264 → 0.075 m²) y la tira
   sobrante **no se acorta**: sigue en 2292 mm. La compensación que se temía
   entre las dos cifras no aparece en este archivo. Igual hay que mostrar las
   dos (tarea 2), porque en otro archivo puede aparecer.
2. **Con colisión exacta, la resolución deja de comprar densidad**: 1 mm/px da
   exactamente el mismo layout que 2 mm/px y tarda 5 veces más. La grilla pasa
   a ser sólo finura de búsqueda. El valor por omisión de 2.0 se queda como
   está, y la tarea 6 tiene que confirmarlo sobre los archivos del bench.
3. **`Lento` deja de hacer falta en este archivo**: Normal y Lento dan el mismo
   layout, con 4x de diferencia en tiempo.

## Global Constraints

- **`nesting` nunca importa `nesting_app`.** El motor no sabe que existe una interfaz.
- **Todo mensaje de cara al usuario va en español**, con tildes y eñes, y dice qué hacer, no sólo qué falló.
- **TDD sin excepciones:** test que falla, correrlo para verlo fallar, implementación mínima, test que pasa, commit.
- **`geometry/verify.py` es el árbitro final y no se toca.** Todo layout que salga de cualquier tarea de este plan tiene que dar **cero violaciones** contra el verificador exacto. Es la condición de aceptación de todas las tareas, no sólo de las que tocan geometría.
- **`occupied` nunca puede sub-representar el material.** La dilatación de seguridad de 1 píxel en `masks.py` **no se toca**: se probó sacarla apostando a que el supermuestreo x4 alcanzaba, y el barrido adversarial del propio proyecto encontró **27.026 píxeles de material real faltantes**. Es load-bearing.
- **Los tests que ya existen no se rompen.** Los que cambian son sólo los que afirman la forma de `layout_cost` (tarea 1) y los de calibración (tarea 6).
- **La CLI conserva sus códigos de salida:** 0 ok, 1 error de entrada, 2 verificación fallida.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `src/nesting/engine/packer.py` | **Modificar.** `layout_cost` pasa a devolver un objeto con tres campos comparables. Nueva pasada de recuperación entre placas. |
| `src/nesting/engine/exact.py` | **Nuevo.** El árbitro exacto: guarda los polígonos ya colocados y contesta si una pieza entra en una posición, con la separación y el borde reales. Sin numpy, sin grillas: sólo shapely. |
| `src/nesting/engine/raster/masks.py` | **Modificar.** Publicar `INFLACION_MAX_PX` (la sobre-representación garantizada de `occupied`) y ofrecer la holgura optimista. |
| `src/nesting/engine/raster/oracle.py` | **Modificar.** Buscar con la holgura optimista y confirmar los mejores candidatos con el árbitro exacto. |
| `src/nesting/cli.py` | **Modificar.** Desempaquetar el nuevo `layout_cost`; informar las dos cifras. |
| `src/nesting_app/corredor.py` | **Modificar.** Idem, y sumar `material_ultima_placa` al `Resultado`. |
| `src/nesting_app/api.py` | **Modificar.** Exponer el campo nuevo. |
| `src/nesting_app/web/app.js`, `index.html` | **Modificar.** Mostrar las dos cifras juntas. |
| `tests/engine/test_exact.py` | **Nuevo.** El árbitro exacto. |
| `tests/engine/test_recuperacion.py` | **Nuevo.** La pasada de recuperación entre placas. |
| `docs/superpowers/calibracion.md` | **Modificar.** Recalibrar con el motor híbrido. |
| `README.md`, `README.es.md` | **Modificar.** El objetivo declarado cambia. |

---

### Task 1: El criterio mira el material de la última placa

Hoy `layout_cost` devuelve `(placas, alto de la última placa)`. Con eso, en el
archivo de referencia el motor **encontró** layouts de 33/3 y los **descartó**,
porque 3 piezas apiladas llegan a 491 mm de alto y 7 piezas en fila llegan a
308 mm. El desempate premiaba dejar más piezas en la última placa.

**Files:**
- Modify: `src/nesting/engine/packer.py:261-285` (`layout_cost`), `:328`, `:370`, `:424`
- Modify: `src/nesting/cli.py:301`
- Modify: `src/nesting_app/corredor.py:305`
- Test: `tests/engine/test_effort.py:58-75`, `:119`, `:146`, `:179`, `:209`

**Interfaces:**
- Produces: `CostoLayout(placas: int, material_ultima: float, alto_ultima: float)`,
  un `@dataclass(frozen=True, order=True)`, y `layout_cost(result, parts) -> CostoLayout`.
  El orden de los campos ES el orden lexicográfico de comparación, y por eso
  se usa un dataclass con `order=True` en vez de una tupla: los dos lugares
  que hoy hacen `[1]` para sacar el alto pasan a decir `.alto_ultima`, así que
  agregar un campo en el medio no puede volver a significar otra cosa en
  silencio.

- [ ] **Step 1: Write the failing test**

En `tests/engine/test_effort.py`, agregar:

```python
def test_el_costo_prefiere_dejar_menos_material_en_la_ultima_placa():
    """Entre dos layouts de la misma cantidad de placas, gana el que deja
    menos material en la última: es el que está más cerca de no necesitarla.

    Es el caso exacto que el motor encontraba y descartaba sobre
    `NESTING 2.ai`: un layout de 33 piezas en la placa 1 y 3 en la 2
    perdía contra uno de 29 y 7, porque las 3 apiladas llegaban más
    alto que las 7 en fila.
    """
    parts = [rect_part(100.0, 100.0, part_id=i) for i in range(4)]
    # `poco` deja una sola pieza en la placa 1 (la última); `mucho` deja tres.
    poco = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
            Placement(1, 0, Transform(0.0, False, 0.0, 200.0)),
            Placement(2, 0, Transform(0.0, False, 0.0, 400.0)),
            Placement(3, 1, Transform(0.0, False, 0.0, 0.0)),
        ],
        sheets_used=2,
    )
    mucho = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
            Placement(1, 1, Transform(0.0, False, 0.0, 0.0)),
            Placement(2, 1, Transform(0.0, False, 200.0, 0.0)),
            Placement(3, 1, Transform(0.0, False, 400.0, 0.0)),
        ],
        sheets_used=2,
    )
    # `mucho` deja las tres piezas en una fila baja: gana en alto.
    assert layout_cost(mucho, parts).alto_ultima <= layout_cost(poco, parts).alto_ultima
    # Y aun así pierde, porque deja el triple de material en la última placa.
    assert layout_cost(poco, parts) < layout_cost(mucho, parts)


def test_el_alto_sigue_desempatando_con_el_mismo_material():
    """Con el mismo material en la última placa, gana la más compactada:
    la tira sobrante queda en un solo bloque en vez de en pedazos."""
    parts = [rect_part(100.0, 100.0, part_id=i) for i in range(2)]
    baja = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
            Placement(1, 1, Transform(0.0, False, 0.0, 0.0)),
        ],
        sheets_used=2,
    )
    alta = PackResult(
        placements=[
            Placement(0, 0, Transform(0.0, False, 0.0, 0.0)),
            Placement(1, 1, Transform(0.0, False, 0.0, 500.0)),
        ],
        sheets_used=2,
    )
    assert layout_cost(baja, parts).material_ultima == layout_cost(alta, parts).material_ultima
    assert layout_cost(baja, parts) < layout_cost(alta, parts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/engine/test_effort.py -k "material_en_la_ultima or alto_sigue_desempatando" -v`
Expected: FAIL con `AttributeError: 'tuple' object has no attribute 'alto_ultima'`

- [ ] **Step 3: Write minimal implementation**

En `src/nesting/engine/packer.py`, reemplazar `layout_cost` entera:

```python
@dataclass(frozen=True, order=True)
class CostoLayout:
    """Qué tan malo es un layout. Menor es mejor; se compara campo por campo.

    El orden de los campos ES el criterio, y por eso son campos con nombre y
    no una tupla: los dos lugares que informan el sobrante al usuario sacan
    `alto_ultima` por nombre, así que sumar un campo en el medio no puede
    volver a significar otra cosa en silencio.
    """

    placas: int
    """Manda sobre todo lo demás: una placa menos siempre gana."""

    material_ultima: float
    """Área de pieza que queda en la última placa, en mm².

    Es el segundo criterio, y no el alto, porque es el único que mide
    progreso hacia no necesitar esa placa: bajarlo a cero elimina una placa
    entera. El alto no mide eso -- entre un layout que deja 7 piezas en una
    fila de 308 mm y uno que deja 3 apiladas en 491 mm, el alto premia el de
    7 piezas aunque esté más lejos de poder tirar la placa. Sobre
    `NESTING 2.ai` ese desempate hacía que el motor descartara los layouts
    de 33/3 que él mismo encontraba.
    """

    alto_ultima: float
    """Hasta dónde llega el material en la última placa, en mm.

    Desempata entre layouts que dejan el mismo material: con la misma
    cantidad de pieza arriba, la que está más compactada deja la tira libre
    en un solo bloque en vez de en pedazos. `sheet_h - alto_ultima` es el
    "sobrante" que se le muestra al usuario.
    """


def layout_cost(result: PackResult, parts: Sequence[Part]) -> CostoLayout:
    """Qué tan malo es un layout. Menor es mejor."""
    if not result.placements:
        return CostoLayout(0, 0.0, 0.0)

    by_id = {p.id: p for p in parts}
    last_sheet = result.sheets_used - 1
    top = 0.0
    material = 0.0

    for placement in result.placements:
        if placement.sheet != last_sheet:
            continue
        part = by_id[placement.part_id]
        _, _, _, y1 = transformed_bbox(part, placement.transform.angle_deg,
                                       placement.transform.mirror)
        top = max(top, placement.transform.dy + y1)
        material += part.area

    return CostoLayout(result.sheets_used, material, top)
```

En el mismo archivo, `_compact_last_sheet` línea 424 pasa de
`if layout_cost(redone, parts)[1] >= layout_cost(result, parts)[1]:` a:

```python
    if layout_cost(redone, parts).alto_ultima >= layout_cost(result, parts).alto_ultima:
```

(La compactación mueve las mismas piezas dentro de la misma placa, así que
`material_ultima` no cambia: el alto es lo único que puede mejorar, y sigue
siendo lo correcto para comparar acá.)

- [ ] **Step 4: Arreglar los tres consumidores**

`src/nesting/cli.py:301`:

```python
    used_height = layout_cost(result, parts).alto_ultima
```

`src/nesting_app/corredor.py:305`:

```python
    costo = layout_cost(resultado, piezas)
```

y más abajo, en la construcción de `Resultado`:

```python
        sobrante_mm=material.sheet_h - costo.alto_ultima,
```

`tests/engine/test_effort.py:65` pasa de `[0]` a `.placas`, y `:71` de
`sheets, height = layout_cost(result, parts)` a:

```python
    costo = layout_cost(result, parts)
    sheets, height = costo.placas, costo.alto_ultima
```

Las líneas `:146`, `:179` y `:209` que indexan `[1]` pasan a `.alto_ultima`.
La línea `:119` (`layout_cost(normal, parts) <= layout_cost(quick, parts)`)
no se toca: `order=True` la deja funcionando igual.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, misma cantidad de tests que antes más los dos nuevos.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/engine/packer.py src/nesting/cli.py src/nesting_app/corredor.py tests/engine/test_effort.py
git commit -m "El criterio de mejor layout mira el material de la última placa, no su alto

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Mostrar las dos cifras que compiten

El criterio nuevo puede dejar una tira sobrante **más corta** que el criterio
viejo (sobre `NESTING 2.ai`: 2109 mm en vez de 2292 mm) a cambio de dejar
menos material en la última placa. El usuario pidió ver las dos para decidir
por trabajo.

**Files:**
- Modify: `src/nesting_app/corredor.py` (`Resultado`)
- Modify: `src/nesting_app/api.py`
- Modify: `src/nesting_app/web/app.js`, `src/nesting_app/web/index.html`
- Modify: `src/nesting/cli.py`
- Test: `tests/app/test_corredor.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `CostoLayout` de la tarea 1.
- Produces: `Resultado.material_ultima_placa_m2: float`, y en la CLI una línea
  más en el resumen.

- [ ] **Step 1: Write the failing test**

En `tests/app/test_corredor.py`:

```python
def test_el_resultado_informa_el_material_que_queda_en_la_ultima_placa(tmp_path):
    """Las dos cifras que compiten van juntas: cuánto material quedó en la
    última placa y qué tira libre dejó. El criterio nuevo puede acortar la
    tira para bajar el material, así que el usuario tiene que ver las dos."""
    resultado = correr(_params_de_muestra(tmp_path))
    assert resultado.material_ultima_placa_m2 > 0.0
    assert resultado.sobrante_mm > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/app/test_corredor.py -k material_que_queda -v`
Expected: FAIL con `AttributeError: 'Resultado' object has no attribute 'material_ultima_placa_m2'`

- [ ] **Step 3: Write minimal implementation**

En `src/nesting_app/corredor.py`, agregar el campo al dataclass `Resultado`:

```python
    material_ultima_placa_m2: float
    """Cuánta pieza quedó en la última placa, en m².

    Va al lado de `sobrante_mm` porque las dos cifras compiten: el motor
    elige el layout que baja ésta, y eso a veces acorta la tira libre. Ver
    las dos juntas es lo que deja decidir si conviene para este trabajo.
    """
```

y llenarlo en el `return`:

```python
        material_ultima_placa_m2=costo.material_ultima / 1e6,
```

- [ ] **Step 4: Exponer y mostrar**

En `src/nesting_app/api.py`, agregar el campo al payload del resultado
(mismo nombre, `material_ultima_placa_m2`).

En `src/nesting_app/web/index.html`, al lado del nodo que muestra el
sobrante, agregar:

```html
<span class="metrica" id="material-ultima" title="Material que quedó en la última placa"></span>
```

En `src/nesting_app/web/app.js`, donde ya se escribe el sobrante:

```js
  document.getElementById('material-ultima').textContent =
    `${r.material_ultima_placa_m2.toFixed(3)} m² en la última placa`;
```

En `src/nesting/cli.py`, en el resumen que ya imprime, agregar:

```python
    print(
        f"  material en la última placa: {costo.material_ultima / 1e6:.3f} m²"
        f"  ·  tira libre: {material.sheet_h - costo.alto_ultima:.0f} mm"
    )
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/nesting_app src/nesting/cli.py tests
git commit -m "Mostrar el material de la última placa junto al sobrante

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: El árbitro exacto

Un objeto que guarda los polígonos ya colocados en una placa y contesta si
una pieza entra en una posición, midiendo sobre la geometría exacta con la
separación y el borde reales. Es lo que va a corregir los 16 mm.

**Files:**
- Create: `src/nesting/engine/exact.py`
- Test: `tests/engine/test_exact.py`

**Interfaces:**
- Produces:
  - `class ArbitroExacto`
  - `ArbitroExacto(sheet_w: float, sheet_h: float, sep: float, margin: float)`
  - `.entra(part: Part, angle: float, mirror: bool, x: float, y: float) -> bool`
  - `.agregar(part: Part, angle: float, mirror: bool, x: float, y: float) -> None`
  - `.limpiar() -> None`

- [ ] **Step 1: Write the failing test**

Crear `tests/engine/test_exact.py`:

```python
"""El árbitro exacto: la última palabra sobre si una pieza entra.

La grilla de raster sobre-representa cada pieza a propósito (ver
`raster/masks.py`), así que no puede contestar esta pregunta sin regalar
milímetros. Este módulo la contesta sobre los polígonos exactos.
"""

import pytest

from nesting.engine.exact import ArbitroExacto
from nesting.model.part import Part


def cuadrado(lado: float, part_id: int = 0) -> Part:
    return Part(
        id=part_id,
        outer=((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)),
        holes=(),
        entity_ids=(),
    )


def test_una_pieza_sola_entra_si_respeta_el_borde():
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    assert arbitro.entra(cuadrado(100.0), 0.0, False, 10.0, 10.0)


def test_una_pieza_pisada_contra_el_borde_no_entra():
    """El borde es material perdido, no negociable: 9.9 mm no son 10."""
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    assert not arbitro.entra(cuadrado(100.0), 0.0, False, 9.9, 10.0)


def test_la_separacion_se_mide_exacta_ni_un_pelo_menos():
    """A exactamente `sep` entra; un décimo de milímetro menos, no.

    Es la razón de existir del módulo: la grilla a 2 mm/px contesta que no
    entra hasta los 16 mm.
    """
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    arbitro.agregar(cuadrado(100.0, part_id=0), 0.0, False, 10.0, 10.0)
    # La primera ocupa x de 10 a 110. A x=120 quedan exactamente 10 mm.
    assert arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 120.0, 10.0)
    assert not arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 119.9, 10.0)


def test_una_pieza_que_se_sale_por_arriba_no_entra():
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    assert not arbitro.entra(cuadrado(100.0), 0.0, False, 10.0, 895.0)


def test_limpiar_olvida_todo_lo_colocado():
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    arbitro.agregar(cuadrado(100.0, part_id=0), 0.0, False, 10.0, 10.0)
    assert not arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 115.0, 10.0)
    arbitro.limpiar()
    assert arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 115.0, 10.0)


def test_una_pieza_puede_entrar_en_el_agujero_de_otra():
    """Es el caso 'with concave': el hueco interno de una pieza es espacio
    libre real, no material."""
    anillo = Part(
        id=0,
        outer=((0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)),
        holes=((((50.0, 50.0), (350.0, 50.0), (350.0, 350.0), (50.0, 350.0))),),
        entity_ids=(),
    )
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=10.0, margin=10.0)
    arbitro.agregar(anillo, 0.0, False, 10.0, 10.0)
    # El agujero va de 60 a 360 en la placa. Un cuadrado de 100 centrado adentro
    # queda a 90 mm de cada pared: entra con holgura.
    assert arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 170.0, 170.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/engine/test_exact.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'nesting.engine.exact'`

- [ ] **Step 3: Write minimal implementation**

Crear `src/nesting/engine/exact.py`:

```python
"""La última palabra sobre si una pieza entra en una posición.

La grilla de raster (`raster/masks.py`) sobre-representa cada pieza a
propósito: nunca puede decir que hay material donde no lo hay, pero sí dice
que lo hay donde no llega. Esa asimetría es lo que la hace segura, y también
lo que le impide contestar esta pregunta sin regalar milímetros -- medido, a
2 mm/px deja 16 mm entre dos piezas cuando se le piden 10.

Acá se contesta sobre los polígonos exactos. Cuesta ~312 µs por consulta
entre dos piezas de ~900 vértices, así que sirve como árbitro de unos pocos
candidatos, nunca como buscador de posiciones: un barrido de la placa entera
son millones de consultas. Ese reparto de tareas -- la grilla busca, esto
arbitra -- es toda la arquitectura del motor híbrido.
"""

from shapely.geometry import Polygon

from nesting.geometry.verify import placed_polygon
from nesting.model.entities import Transform
from nesting.model.part import Part

EPS = 1e-6
"""Tolerancia contra el ruido de punto flotante.

`verify.py` usa la misma para la misma comparación. Tienen que coincidir: si
el árbitro fuera más permisivo que el verificador, aceptaría layouts que
después el verificador rechaza, y el usuario vería fallar un trabajo que el
motor dio por bueno.
"""


class ArbitroExacto:
    """Los polígonos ya colocados en UNA placa, y si entra uno más."""

    def __init__(self, sheet_w: float, sheet_h: float, sep: float, margin: float) -> None:
        if sep < 0 or margin < 0:
            raise ValueError(
                f"sep y margin tienen que ser >= 0 (se recibió sep={sep!r}, "
                f"margin={margin!r})"
            )
        self._sheet_w = sheet_w
        self._sheet_h = sheet_h
        self._sep = sep
        self._margin = margin
        self._colocados: list[tuple[Polygon, tuple[float, float, float, float]]] = []

    def limpiar(self) -> None:
        """Vaciar la placa, para reusar el árbitro en la siguiente."""
        self._colocados.clear()

    def entra(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> bool:
        """¿La pieza en esa posición respeta borde y separación, exactos?"""
        poly = placed_polygon(part, Transform(angle, mirror, x, y))
        return self._entra_poly(poly)

    def agregar(self, part: Part, angle: float, mirror: bool, x: float, y: float) -> None:
        """Dar por colocada la pieza. No revalida: el llamador ya preguntó."""
        poly = placed_polygon(part, Transform(angle, mirror, x, y))
        self._colocados.append((poly, poly.bounds))

    def _entra_poly(self, poly: Polygon) -> bool:
        minx, miny, maxx, maxy = poly.bounds
        m = self._margin
        if (
            minx < m - EPS
            or miny < m - EPS
            or maxx > self._sheet_w - m + EPS
            or maxy > self._sheet_h - m + EPS
        ):
            return False

        # Prefiltro por caja: `distance` sobre polígonos de ~900 vértices
        # cuesta ~312 µs, y comparar cuatro números cuesta nada. Sin esto,
        # colocar la pieza número 30 pagaría 30 consultas caras, la mayoría
        # contra piezas que están al otro lado de la placa.
        s = self._sep
        for otro, (omin_x, omin_y, omax_x, omax_y) in self._colocados:
            if maxx + s < omin_x or omax_x + s < minx:
                continue
            if maxy + s < omin_y or omax_y + s < miny:
                continue
            if poly.distance(otro) < s - EPS:
                return False
        return True
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/engine/test_exact.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add src/nesting/engine/exact.py tests/engine/test_exact.py
git commit -m "Árbitro de colisión sobre la geometría exacta

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: La grilla pasa a ser optimista y el árbitro decide

Éste es el cambio que elimina los 6 mm de separación fantasma.

**El argumento de corrección, que hay que dejar escrito en el código:**
`occupied` sobre-representa el material exacto en a lo sumo `INFLACION_MAX_PX`
píxeles por lado (1 del `_downsample_any`, 1 de la dilatación de seguridad
de 3×3). Llamemos `e = INFLACION_MAX_PX * resolution` a eso en mm.

- Si la holgura optimista usa radio `r` tal que `r * resolution <= sep - 2e`,
  entonces **toda** posición realmente factible (distancia exacta ≥ `sep`)
  pasa el test optimista: las dos piezas están a ≥ `sep - 2e` medidas entre
  sus `occupied`, que es ≥ `r * resolution`.
- Al revés no vale: el test optimista admite posiciones que violan. Por eso
  el árbitro exacto revisa los candidatos antes de devolver uno.

O sea: el conjunto de candidatos es un **superconjunto** del conjunto factible
real. No se pierde ninguna posición buena, y ninguna mala sobrevive al árbitro.

**Files:**
- Modify: `src/nesting/engine/raster/masks.py`
- Modify: `src/nesting/engine/raster/oracle.py`
- Test: `tests/engine/raster/test_raster_oracle.py`

**Interfaces:**
- Consumes: `ArbitroExacto` de la tarea 3.
- Produces: `masks.INFLACION_MAX_PX: int`, `masks.radio_optimista(sep, resolution) -> int`,
  `PartMasks.holgura_optimista(radio_px) -> np.ndarray`, y `RasterOracle` con
  el comportamiento nuevo (misma interfaz `Oracle`, sin cambios de firma).

- [ ] **Step 1: Write the failing test**

En `tests/engine/raster/test_raster_oracle.py`:

```python
def test_la_separacion_real_es_la_pedida_no_la_inflada():
    """La razón de ser del motor híbrido.

    Antes, la grilla conservadora dejaba 16 mm reales entre dos piezas
    cuando se le pedían 10 a 2 mm/px, porque cada pieza se rasteriza 3 mm
    más grande por lado y las dos pagan. Medido sobre los polígonos
    exactos, no sobre la grilla.
    """
    from nesting.geometry.verify import placed_polygon
    from nesting.model.entities import Transform

    lado = 100.0
    pts = ((0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado))
    material = Material(name="t", sheet_w=1000.0, sheet_h=1000.0, grain_tolerance=180.0)
    config = NestConfig(sep=10.0, margin=10.0, angles=(0.0,), mirror=False,
                        resolution=2.0, effort="rapido")

    oracle = RasterOracle(MaskCache())
    oracle.reset(material.sheet_w, material.sheet_h, config)
    polys = []
    for i in range(2):
        part = Part(id=i, outer=pts, holes=(), entity_ids=())
        spot = oracle.best_placement(part, 0.0, False)
        assert spot is not None
        x, y, _ = spot
        oracle.place(part, 0.0, False, x, y)
        polys.append(placed_polygon(part, Transform(0.0, False, x, y)))

    real = polys[0].distance(polys[1])
    assert real == pytest.approx(10.0, abs=0.51), (
        f"la separación real quedó en {real:.2f} mm y se pidieron 10.00"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/engine/raster/test_raster_oracle.py -k separacion_real -v`
Expected: FAIL con `la separación real quedó en 16.00 mm y se pidieron 10.00`

- [ ] **Step 3: Publicar la inflación en `masks.py`**

Al lado de `SUPERSAMPLE`, agregar:

```python
INFLACION_MAX_PX = 2
"""Cuántos píxeles finales, por lado, puede `occupied` extenderse más allá
del polígono exacto. Es el precio de que nunca sub-represente el material.

Se compone de dos pasos, uno cada uno:

  1. `_downsample_any`: un píxel final se marca si CUALQUIERA de sus
     SUPERSAMPLE**2 subpíxeles está marcado, así que el borde puede
     ganar un píxel final.
  2. La dilatación de seguridad de 3x3 sobre `outer_mask`: exactamente uno
     más, por construcción.

No es una estimación: es la cota de esos dos pasos. Medido sobre un cuadrado
de 100 mm, `occupied` mide 106 mm a 2 mm/px (3 mm por lado = 1.5 px, contra
esta cota de 2 px) y 103 mm a 1 mm/px.

Lo usa `radio_optimista` para saber cuánto puede recortar del halo de
holgura sin perder posiciones factibles. Si algún día cambia el pipeline de
rasterizado, este número tiene que cambiar con él, o el motor híbrido
empieza a descartar posiciones buenas en silencio.
"""


def radio_optimista(sep: float, resolution: float) -> int:
    """Radio de holgura, en píxeles, que NO pierde ninguna posición factible.

    La holgura conservadora usa `ceil(sep / resolution)`, que sumada a la
    inflación de las DOS piezas involucradas exige `sep + 2 * inflación` de
    distancia real. Acá se recorta exactamente esa inflación doble, así el
    conjunto de candidatos pasa a ser un superconjunto del factible real
    -- ver el argumento completo en `RasterOracle.best_placement`.

    Nunca baja de 0: con una separación chica frente a la resolución, el
    recorte se come el halo entero y el candidato queda a cargo del árbitro
    exacto, que es justamente quien sabe decidir.
    """
    holgura_mm = sep - 2 * INFLACION_MAX_PX * resolution
    if holgura_mm <= 0.0:
        return 0
    return math.floor(holgura_mm / resolution)
```

Y agregar el método a `PartMasks`:

```python
    def holgura_optimista(self, radio_px: int) -> np.ndarray:
        """`occupied` dilatado por `radio_px`, para la búsqueda de candidatos.

        Es `clearance` con el radio recortado: admite posiciones de más, que
        el árbitro exacto descarta. Se calcula acá y no se cachea porque
        depende del radio, y el radio depende de la config, no de la pieza.
        """
        if radio_px <= 0:
            return self.occupied.copy()
        return binary_dilation(self.occupied, structure=disk_kernel(radio_px))
```

- [ ] **Step 4: Cablear el oráculo**

En `src/nesting/engine/raster/oracle.py`, agregar al `__init__`:

```python
        self._arbitro: ArbitroExacto | None = None
```

En `reset`, después de crear `self._sheet`:

```python
        self._arbitro = ArbitroExacto(sheet_w, sheet_h, config.sep, config.margin)
        self._radio_optimista = radio_optimista(config.sep, config.resolution)
```

Reemplazar `_search` para que use la holgura optimista y recorra candidatos:

```python
    CANDIDATOS_POR_TANDA = 64
    """Cuántos candidatos se verifican exactamente por vez.

    El árbitro cuesta ~312 µs por consulta contra cada vecino cercano, así
    que verificar la placa entera es imposible; y verificar uno solo deja al
    motor sin salida cuando el mejor candidato de la grilla resulta inválido.
    Se recorren de a tandas, en orden de puntaje, hasta el tope de abajo.
    """

    MAX_CANDIDATOS = 1024
    """Tope duro de candidatos verificados antes de rendirse y caer al
    camino conservador.

    Sin tope, una placa casi llena puede hacer que una sola pieza pague
    cientos de miles de consultas exactas. Con tope, el peor caso es
    acotado y además NO se pierde nada: si ninguno de los candidatos
    optimistas pasó, se reintenta con la holgura conservadora de siempre,
    que no necesita árbitro porque ya es segura por construcción. O sea que
    el motor híbrido nunca coloca menos piezas que el motor viejo.
    """
```

y el cuerpo:

```python
    def _search(self, masks: PartMasks, limit_rows: int) -> tuple[int, int, float] | None:
        pad = masks.pad
        rows = min(max(limit_rows, masks.clearance.shape[0]), self._sheet.shape[0])
        padded = np.pad(self._sheet[:rows], pad, mode="constant", constant_values=False)

        optimista = self._buscar_con(masks, padded, pad,
                                     masks.holgura_optimista(self._radio_optimista),
                                     arbitrar=True)
        if optimista is not None:
            return optimista
        # Red de seguridad: la holgura conservadora no necesita árbitro.
        return self._buscar_con(masks, padded, pad, masks.clearance, arbitrar=False)
```

`_buscar_con` es nuevo: arma `feasible`, arma el puntaje con `best_position`
sobre esa misma holgura, y si `arbitrar` recorre los candidatos en orden de
puntaje de a `CANDIDATOS_POR_TANDA` preguntándole al árbitro, hasta
`MAX_CANDIDATOS`. Si no, devuelve el mejor directamente (comportamiento
viejo).

En `place`, después del `|=` sobre `self._sheet`:

```python
        self._arbitro.agregar(part, angle, mirror, x, y)
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/engine -q`
Expected: PASS. El test nuevo tiene que dar `10.00 mm`.

- [ ] **Step 6: Verificar sobre el archivo real**

Run:
```bash
.venv/bin/nest "/Users/raulo/Downloads/NESTING 2.ai" --material mdf15 --sep 10 --borde 10 --esfuerzo rapido -o /tmp/hibrido.dxf
```
Expected: 2 placas, **33 piezas en la primera y 3 en la segunda**, verificación
sin violaciones, en el orden de 15 s.

- [ ] **Step 7: Commit**

```bash
git add src/nesting/engine/raster tests/engine/raster
git commit -m "La grilla propone y la geometría exacta dispone: separación real, no inflada

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Pasada de recuperación entre placas

Hoy, cuando una pieza no entra en la placa 1 se va a la 2 y **nunca más se
vuelve a intentar**, aunque las piezas que se colocaron después hayan dejado
la placa 1 con otro perfil de huecos. `_compact_last_sheet` sólo reordena la
última placa contra sí misma. Es literalmente lo que el usuario hizo a mano:
agarrar un círculo de la placa 2 y meterlo en la 1.

**Files:**
- Modify: `src/nesting/engine/packer.py`
- Test: `tests/engine/test_recuperacion.py`

**Interfaces:**
- Consumes: `Oracle`, `PackResult`, `CostoLayout`.
- Produces: `_recuperar_de_la_ultima_placa(result, parts, material, config, oracle_factory) -> PackResult`,
  llamada desde `pack` justo antes de `_compact_last_sheet`.

- [ ] **Step 1: Write the failing test**

Crear `tests/engine/test_recuperacion.py`:

```python
"""Lo que quedó en la última placa se reintenta en las anteriores.

El motor coloca de forma golosa y no vuelve atrás: una pieza que no entró
cuando le tocó se va a la placa siguiente aunque las piezas colocadas
DESPUÉS hayan dejado un hueco donde sí entra. Esta pasada cierra eso.
"""

def test_una_pieza_de_la_ultima_placa_vuelve_a_la_primera_si_entra():
    """Escenario armado para que la avaricia falle: una pieza ancha se
    coloca primero y ocupa el centro, una angosta no entra al lado, y
    recién las siguientes dejan libre la franja donde la angosta sí cabe."""
    ...


def test_si_la_ultima_placa_queda_vacia_se_descarta():
    """Recuperar la última pieza de la última placa tiene que bajar el
    conteo de placas, no dejar una placa vacía en el resultado."""
    ...


def test_la_recuperacion_nunca_empeora_el_costo():
    """Propiedad, no ejemplo: sobre varios escenarios al azar, el costo
    después de recuperar es <= al de antes."""
    ...
```

(El escenario concreto de cada test se arma con `rect_part` de distintos
anchos sobre una placa chica; quien implemente esta tarea tiene que
escribirlos completos antes de tocar `packer.py`, y correrlos para verlos
fallar.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/engine/test_recuperacion.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

En `src/nesting/engine/packer.py`:

```python
def _recuperar_de_la_ultima_placa(
    result: PackResult,
    parts: Sequence[Part],
    material: Material,
    config: NestConfig,
    oracle_factory: Callable[[], Oracle],
) -> PackResult:
    """Reintentar en las placas anteriores lo que quedó en la última.

    El motor es goloso y no vuelve atrás: una pieza que no entró cuando le
    tocó se fue a la placa siguiente, aunque las piezas colocadas DESPUÉS
    hayan cambiado el perfil de huecos de la placa que la rechazó. Acá se
    reconstruye cada placa anterior tal cual quedó y se le vuelve a
    preguntar, empezando por las piezas más chicas, que son las que más
    probabilidad tienen de entrar.
    """
    if result.sheets_used < 2:
        return result

    by_id = {p.id: p for p in parts}
    choices = orientations(material, config)
    ultima = result.sheets_used - 1

    en_ultima = [p for p in result.placements if p.sheet == ultima]
    otras = [p for p in result.placements if p.sheet != ultima]
    if not en_ultima:
        return result

    # De la más chica a la más grande: la chica entra en más lugares, y
    # sacarla de la última placa puede dejar a la grande sola y compactable.
    en_ultima.sort(key=lambda p: by_id[p.part_id].area)

    pendientes = list(en_ultima)
    for placa in range(ultima):
        if not pendientes:
            break
        oracle = oracle_factory()
        oracle.reset(material.sheet_w, material.sheet_h, config)
        for p in otras:
            if p.sheet != placa:
                continue
            part = by_id[p.part_id]
            oracle.place(part, p.transform.angle_deg, p.transform.mirror,
                         p.transform.dx, p.transform.dy)

        quedan: list[Placement] = []
        for p in pendientes:
            part = by_id[p.part_id]
            spot = _best_over_orientations(oracle, part, choices)
            if spot is None:
                quedan.append(p)
                continue
            angle, mirror, x, y = spot
            oracle.place(part, angle, mirror, x, y)
            otras.append(Placement(part.id, placa, Transform(angle, mirror, x, y)))
        pendientes = quedan

    if len(pendientes) == len(en_ultima):
        return result   # no se recuperó nada: no tocar nada

    placements = otras + [Placement(p.part_id, ultima, p.transform) for p in pendientes]
    sheets = ultima if not pendientes else result.sheets_used

    sheet_area = material.sheet_w * material.sheet_h
    util = [0.0] * sheets
    for p in placements:
        util[p.sheet] += by_id[p.part_id].area / sheet_area

    return PackResult(
        placements=placements,
        sheets_used=sheets,
        utilization=util,
        total_utilization=sum(util) / sheets if sheets else 0.0,
        seconds=result.seconds,
    )
```

y en `pack`, justo antes de `_compact_last_sheet`:

```python
    best = _recuperar_de_la_ultima_placa(best, parts, material, config, oracle_factory)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/engine -q`
Expected: PASS

- [ ] **Step 5: Verificar sobre el archivo real**

Run: el mismo comando de la tarea 4.
Expected: igual o mejor que 33/3, verificación sin violaciones.

- [ ] **Step 6: Commit**

```bash
git add src/nesting/engine/packer.py tests/engine/test_recuperacion.py
git commit -m "Reintentar en las placas anteriores lo que quedó en la última

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Recalibrar los valores por omisión y contar la verdad

La resolución por omisión (2.0 mm/px) y los `EFFORT_RESTARTS` se calibraron
contra el motor conservador. Con el híbrido, la resolución ya no compra
separación — sólo finura de búsqueda — así que el punto óptimo se corrió. Y
el README promete un objetivo que este plan cambia.

**Files:**
- Modify: `src/nesting/engine/oracle.py` (docstring de `resolution`)
- Modify: `src/nesting/params.py` (`resolucion` por omisión, si la medición lo pide)
- Modify: `docs/superpowers/calibracion.md`
- Modify: `README.md`, `README.es.md`
- Test: `tests/engine/test_effort.py` (los que fijan la calibración)

- [ ] **Step 1: Medir**

Run:
```bash
.venv/bin/python bench/run_bench.py --resoluciones 0.5,1.0,2.0,3.0 --esfuerzos rapido,normal,lento
```
sobre los tres archivos de `bench/files/` más `NESTING 2.ai`. Anotar, por
combinación: placas, material en la última placa, tira sobrante, tiempo,
violaciones.

**Hipótesis a confirmar o refutar, ya medida sobre `NESTING 2.ai`:** con el
motor híbrido, 1 mm/px da el MISMO layout que 2 mm/px y tarda 5x más, porque
la grilla dejó de ser quien define la separación. Si eso se repite en el
bench, `resolucion = 2.0` se queda y hay que reescribir el docstring de
`NestConfig.resolution`, que hoy justifica el valor por un compromiso entre
densidad y tiempo que ya no existe.

- [ ] **Step 2: Fijar los valores por omisión con lo medido**

Actualizar el docstring de `NestConfig.resolution` con la tabla nueva y la
razón del valor elegido, en el mismo estilo que el que está (que cuenta la
medición, no la intuición). Si el óptimo cambió, cambiar
`NestParams.resolucion`.

- [ ] **Step 3: Actualizar los dos README**

La promesa actual es «usar las menos placas posibles y, en la última, dejar
libre la tira más grande posible». Pasa a ser: «usar las menos placas
posibles, dejar la menor cantidad de material posible en la última — que es
lo que acerca a no necesitarla — y, con la misma cantidad, dejarla lo más
compactada posible». Decirlo en los dos idiomas, y agregar que la aplicación
muestra las dos cifras.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nesting docs README.md README.es.md tests
git commit -m "Recalibrar con el motor híbrido y contar el objetivo nuevo

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Lo que este plan NO hace

- **No implementa NFP.** Ver el apartado de arriba: es inviable a estos
  conteos de vértices, y el híbrido consigue el mismo resultado (separación
  exacta) por otro camino. Si algún día las piezas vinieran con pocos
  vértices, valdría la pena revisarlo.
- **No agrega búsqueda local sobre posiciones ya elegidas** (recocido,
  "sacudir y reinsertar"). La pasada de recuperación de la tarea 5 es el
  caso barato y de mayor rinde; una búsqueda local de verdad es otro plan, y
  conviene medir primero cuánto queda sobre la mesa después de las tareas
  1 a 5.
- **No toca el lector de archivos ni el escritor de DXF.**

## El techo, para saber cuándo parar

Sobre `NESTING 2.ai`, con separación 10 mm, las 36 piezas infladas 5 mm ocupan
**3.010 m²**, contra **4.670 m²** de área útil: una sola placa exige empaquetar
al **64.4%**. Es una cota dura — en un layout válido esas piezas infladas son
disjuntas — así que ningún algoritmo la baja. Hoy la placa 1 llega a ~52%; con el híbrido más el criterio nuevo, a 53.5%,
con 34 de las 36 piezas arriba. Si después de este plan el motor queda cerca del 64% y sigue
usando dos placas, el problema ya no es el motor.
