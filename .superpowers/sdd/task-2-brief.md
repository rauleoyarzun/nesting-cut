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

