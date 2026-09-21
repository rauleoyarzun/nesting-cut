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

