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

