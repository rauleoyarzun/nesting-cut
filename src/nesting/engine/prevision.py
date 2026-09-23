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
