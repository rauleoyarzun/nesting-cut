"""El árbitro exacto: la última palabra sobre si una pieza entra.

La grilla de raster sobre-representa cada pieza a propósito (ver
`raster/masks.py`), así que no puede contestar esta pregunta sin regalar
milímetros. Este módulo la contesta sobre los polígonos exactos.
"""

import random

import pytest

from nesting.engine.exact import ArbitroExacto
from nesting.geometry.verify import verify
from nesting.model.entities import Transform
from nesting.model.part import Part, Placement
from nesting.model.sheet import Sheet


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


def test_una_pieza_muy_superpuesta_con_sep_cero_no_entra():
    """`sep=0.0` es un valor legítimo (el CLI lo acepta), y con `distance`
    solo, `0.0 < 0.0 - EPS` es siempre falso -- el árbitro aprobaría
    cualquier superposición, por grande que sea, apenas alguien pidiera
    separación cero. `verify.py` nunca tiene ese agujero porque primero
    mira el área de la intersección; el árbitro tiene que mirar lo mismo."""
    arbitro = ArbitroExacto(sheet_w=1000.0, sheet_h=1000.0, sep=0.0, margin=10.0)
    arbitro.agregar(cuadrado(100.0, part_id=0), 0.0, False, 10.0, 10.0)
    assert not arbitro.entra(cuadrado(100.0, part_id=1), 0.0, False, 10.0, 10.0)


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


# --- propiedad: el árbitro y el verificador tienen que estar de acuerdo -----


def _rectangulo(part_id: int, w: float, h: float) -> Part:
    return Part(part_id, ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), (), (part_id,))


def _par_al_azar(rng: random.Random) -> tuple[Part, Part, float, float]:
    """Dos rectángulos de tamaño al azar y el offset (dx, dy) de b contra a,
    con el offset elegido para caer, a propósito y con certeza, en tres
    regímenes distintos -- no sólo "en algún lugar al azar".

    El régimen "solapadas" es el que importa para el bug histórico: el
    árbitro viejo sólo miraba `distance`, y con `sep=0.0` la comparación
    `distance < 0.0 - EPS` nunca es verdadera sin importar cuánto se pisen
    los polígonos -- así que CUALQUIER par con bounding boxes solapadas,
    a sep=0, hubiera hecho que el árbitro viejo dijera "entra" mientras
    `verify()` reporta un solapamiento real. Sin forzar este régimen, un
    offset puramente uniforme sobre un rango grande podría, por mala suerte,
    no ejercitar solapamiento franco en ninguna de las muestras.
    """
    aw, ah = rng.uniform(20.0, 150.0), rng.uniform(20.0, 150.0)
    bw, bh = rng.uniform(20.0, 150.0), rng.uniform(20.0, 150.0)
    a = _rectangulo(0, aw, ah)
    b = _rectangulo(1, bw, bh)

    regimen = rng.choice(("solapadas", "cerca", "lejos"))
    if regimen == "solapadas":
        dx = rng.uniform(-min(aw, bw) * 0.6, min(aw, bw) * 0.6)
        dy = rng.uniform(-min(ah, bh) * 0.6, min(ah, bh) * 0.6)
    elif regimen == "cerca":
        # Alrededor de donde `aw` termina: la zona donde `sep` decide.
        dx = aw + rng.uniform(-3.0, 13.0)
        dy = rng.uniform(-ah * 0.3, ah * 0.3)
    else:
        dx = aw + bw + rng.uniform(20.0, 200.0)
        dy = rng.uniform(-200.0, 200.0)

    return a, b, dx, dy


def _wh(part: Part) -> tuple[float, float]:
    """El (ancho, alto) de un rectángulo de `_rectangulo`, para el mensaje
    de error -- más legible que volcar los cuatro vértices."""
    xs = [p[0] for p in part.outer]
    ys = [p[1] for p in part.outer]
    return (max(xs) - min(xs), max(ys) - min(ys))


def test_el_arbitro_exacto_coincide_con_el_verificador():
    """Propiedad, no ejemplo: `ArbitroExacto` reimplementa a propósito los
    mismos chequeos de a pares que `verify.py`, sobre una estructura
    distinta -- incremental acá, por lotes allá (ver el docstring del
    módulo). Esa duplicación ya escondió un bug real: el árbitro era más
    permisivo que el verificador en `sep=0` (ver
    `test_una_pieza_muy_superpuesta_con_sep_cero_no_entra`, arriba), y lo
    agarró una persona leyendo el código, no un test. Este barre pares al
    azar -- con semilla fija, para que una falla se pueda reproducir -- y
    pide que, para el mismo par en la misma posición, `arbitro.entra(...)`
    y "`verify()` no devuelve violaciones" sean la misma respuesta.

    Las dos piezas viven bien adentro de una placa grande con margen 0, así
    que lo único que se está comparando es el chequeo de separación/
    solapamiento entre pares, nunca el de borde.
    """
    sheet_w, sheet_h = 2000.0, 2000.0
    margin = 0.0
    base_x, base_y = 500.0, 500.0
    rng = random.Random(20260921)

    comparaciones = 0
    for _ in range(200):
        a, b, dx, dy = _par_al_azar(rng)
        x2, y2 = base_x + dx, base_y + dy

        for sep in (0.0, 5.0, 10.0):
            arbitro = ArbitroExacto(sheet_w, sheet_h, sep=sep, margin=margin)
            arbitro.agregar(a, 0.0, False, base_x, base_y)
            entra_arbitro = arbitro.entra(b, 0.0, False, x2, y2)

            placements = [
                Placement(a.id, 0, Transform(0.0, False, base_x, base_y)),
                Placement(b.id, 0, Transform(0.0, False, x2, y2)),
            ]
            violaciones = verify(
                [a, b],
                placements,
                [Sheet(sheet_w, sheet_h, grain_tolerance=180.0)],
                sep=sep,
                margin=margin,
            )
            sin_violaciones = violaciones == []

            comparaciones += 1
            assert entra_arbitro == sin_violaciones, (
                f"sep={sep}, dx={dx:.2f}, dy={dy:.2f}, "
                f"a={_wh(a)}, b={_wh(b)}: árbitro dijo {entra_arbitro}, "
                f"verify() dijo {sin_violaciones} ({violaciones})"
            )

    # Sin esto la propiedad la cumpliría también un bucle que no itera nada.
    assert comparaciones == 600
