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

