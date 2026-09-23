"""Cuántas placas harían falta para unos rectángulos, armados por estantes.

Es una PREDICCIÓN para ordenar, no un acomodo. La cartera la usa para decidir
qué combinaciones de pares prueba primero (spec de pares y cartera, 4.1): de
las combinaciones que caben en una tanda, primero las que como rectángulos
entran en menos placas, y recién entre ésas, las de menor área de cajas.

Por qué hace falta: ordenadas sólo por área, las doce combinaciones más
chicas de la banqueta alta eran todas imposibles -- tres pares de la caja
mínima, de 1809 mm de largo, no entran en una placa de 2430 de alto útil
por más chicos que sean -- y la que entra quedaba decimotercera.

El armado es a propósito tonto y determinista: estantes llenados en orden,
la caja más alta primero. No mira las formas (un par encastrado deja huecos
que el motor de verdad sí usa), así que puede errar para los dos lados. Lo
único que se le pide es que ordene: que las combinaciones que ni como
rectángulos entran vayan al final.
"""

from collections.abc import Sequence


def _orient(box: tuple[float, float], usable: tuple[float, float],
            can_turn: bool) -> tuple[float, float] | None:
    """La orientación de `box` para el armado, o `None` si no entra de ninguna forma.

    Sin girar, tal cual. Girando, entre (w, h) y (h, w) la que entra en el
    área útil y, si entran las dos, la más baja: la que deja más alto para
    los estantes que siguen.
    """
    usable_w, usable_h = usable
    w, h = box
    options = [(w, h), (h, w)] if can_turn else [(w, h)]
    fitting = [(bw, bh) for bw, bh in options if bw <= usable_w and bh <= usable_h]
    if not fitting:
        return None
    return min(fitting, key=lambda o: o[1])


def predicted_sheets(
    boxes: Sequence[tuple[float, float]],
    usable: tuple[float, float],
    sep: float,
    can_turn: bool,
) -> int:
    """Las placas que usaría un armado por estantes de `boxes` en `usable`.

    `boxes` son (ancho, alto) en mm; `usable`, el ancho y el alto útiles de
    la placa (sin el borde); `sep`, la separación entre cajas y entre
    estantes; `can_turn`, si la corrida permite girar 90°.

    - Cada caja se orienta con `_orient`. Una que no entra de ninguna forma
      cuenta como una placa propia: es una predicción, no levanta error.
    - Se arman de la más alta a la más baja (empates: la más ancha primero,
      después el orden de entrada).
    - Cada caja va al primer estante de la placa en curso donde entra a lo
      ancho (con `sep` desde la anterior). Si no entra en ninguno, abre un
      estante encima del último (con `sep` entre estantes), tan alto como
      ella; si ese estante no entra en el alto útil, abre una placa nueva.
    """
    usable_w, usable_h = usable
    oriented: list[tuple[float, float]] = []
    oversized = 0
    for box in boxes:
        placed = _orient(box, usable, can_turn)
        if placed is None:
            oversized += 1
        else:
            oriented.append(placed)
    # `sorted` es estable: a igual alto y ancho, queda el orden de entrada.
    oriented.sort(key=lambda b: (-b[1], -b[0]))

    sheets = 0
    shelves: list[list[float]] = []  # [ancho usado, alto] de la placa en curso
    top = 0.0  # dónde termina el último estante de la placa en curso
    for w, h in oriented:
        for shelf in shelves:
            if shelf[0] + sep + w <= usable_w:
                shelf[0] += sep + w
                break
        else:
            start = top + sep if shelves else 0.0
            if not shelves or start + h > usable_h:
                sheets += 1
                shelves = []
                start = 0.0
            shelves.append([w, h])
            top = start + h
    return sheets + oversized
