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

