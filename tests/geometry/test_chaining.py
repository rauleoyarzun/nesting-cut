import itertools
import math

import pytest

from nesting.geometry import chaining
from nesting.geometry.chaining import ChainingInvariantError, chain_contours

TOL = 0.1


def test_a_single_already_closed_ring_is_a_contour():
    ring = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    contours, open_chains, duplicates = chain_contours([(ring, 0)], TOL)

    assert len(contours) == 1
    assert len(open_chains) == 0
    assert len(duplicates) == 0
    assert contours[0].points[0] != contours[0].points[-1], "no se repite el primer punto"
    assert len(contours[0].points) == 4
    assert contours[0].entity_ids == (0,)


def test_four_separate_sides_become_one_contour():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (10.0, 10.0)), 1),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)

    assert len(contours) == 1
    assert len(open_chains) == 0
    assert len(contours[0].points) == 4
    assert sorted(contours[0].entity_ids) == [0, 1, 2, 3]


def test_sides_in_random_order_and_reversed_still_chain():
    segments = [
        (((10.0, 10.0), (10.0, 0.0)), 2),   # invertido
        (((0.0, 10.0), (0.0, 0.0)), 3),
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((0.0, 10.0), (10.0, 10.0)), 1),   # invertido
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)

    assert len(contours) == 1
    assert len(open_chains) == 0
    assert len(contours[0].points) == 4


def test_endpoints_within_tolerance_are_joined():
    """Corel deja huecos de micras entre tramos; tienen que unirse igual."""
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.02), (10.0, 10.0)), 1),   # arranca 0.02 mm mas arriba
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_gap_larger_than_tolerance_produces_an_open_chain():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (10.0, 10.0)), 1),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 5.0)), 3),      # falta el ultimo tramo
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)

    assert len(contours) == 0
    assert len(open_chains) == 1
    assert math.isclose(open_chains[0].gap, 5.0, abs_tol=1e-9)


def test_two_independent_squares_become_two_contours():
    segments = [
        (((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)), 0),
        (((5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 6.0), (5.0, 5.0)), 1),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)
    assert len(contours) == 2
    assert len(open_chains) == 0


def test_exact_duplicate_segments_are_discarded():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((0.0, 0.0), (10.0, 0.0)), 1),      # duplicado exacto
        (((10.0, 0.0), (10.0, 10.0)), 2),
        (((10.0, 10.0), (0.0, 10.0)), 3),
        (((0.0, 10.0), (0.0, 0.0)), 4),
    ]
    contours, open_chains, duplicates = chain_contours(segments, TOL)

    assert len(duplicates) == 1
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_reversed_duplicate_segments_are_discarded():
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (0.0, 0.0)), 1),      # el mismo, al reves
        (((10.0, 0.0), (10.0, 10.0)), 2),
        (((10.0, 10.0), (0.0, 10.0)), 3),
        (((0.0, 10.0), (0.0, 0.0)), 4),
    ]
    contours, _, duplicates = chain_contours(segments, TOL)
    assert len(duplicates) == 1
    assert len(contours) == 1


def test_chain_can_grow_backwards_from_the_starting_segment():
    """Se arranca por un tramo del medio: hay que extender para los dos lados."""
    segments = [
        (((10.0, 0.0), (10.0, 10.0)), 1),    # este queda primero en la lista
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    contours, open_chains, _ = chain_contours(segments, TOL)
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_degenerate_contours_are_dropped():
    """Un 'contorno' de dos puntos no encierra area: no es una pieza."""
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (0.0, 0.0000001)), 1),
    ]
    contours, _, _ = chain_contours(segments, TOL)
    assert len(contours) == 0


def test_empty_input():
    assert chain_contours([], TOL) == ([], [], ())


def test_entity_ids_are_preserved_for_every_contour():
    segments = [
        (((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)), 7),
        (((5.0, 5.0), (6.0, 5.0)), 8),
        (((6.0, 5.0), (6.0, 6.0)), 9),
        (((6.0, 6.0), (5.0, 6.0)), 10),
        (((5.0, 6.0), (5.0, 5.0)), 11),
    ]
    contours, _, _ = chain_contours(segments, TOL)
    by_size = sorted(contours, key=lambda c: len(c.entity_ids))
    assert by_size[0].entity_ids == (7,)
    assert sorted(by_size[1].entity_ids) == [8, 9, 10, 11]


# --- Hallazgo 1: un vertice compartido no debe fusionar dos contornos -------


def test_two_triangles_touching_at_one_vertex_become_two_contours():
    """Dos triangulos que solo comparten el punto (10, 10) no son un moño.

    `_find_unused_neighbour` tomaba el primer candidato que devolvia el
    KD-tree en ese punto, sin desempate: segun el orden de entrada, podia
    enganchar con el triangulo equivocado y producir un unico contorno de 6
    puntos con forma de moño en vez de los dos triangulos. Medido por el
    revisor: 320 de las 720 permutaciones del orden de los 6 tramos (44%)
    disparaban el bug. Se prueban las 720 para no dejar pasar ningun orden.
    """
    # Triangulo A: (10,10)-(0,10.5)-(20,9.5), casi una linea recta que pasa
    # por (10,10). Triangulo B: (10,10)-(9.5,20)-(10.5,0), tambien casi recto
    # pero perpendicular al anterior. Ambos apenas se doblan en su propio
    # vertice, de forma que seguir el propio triangulo es casi siempre la
    # continuacion mas derecha; el otro triangulo exige un giro mucho mas
    # brusco. Es la geometria de un caso de CAD normal, no un caso adversario
    # (un cruce exacto tipo reloj de arena si es ambiguo por naturaleza).
    segs = {
        0: ((10.0, 10.0), (0.0, 10.5)),
        1: ((0.0, 10.5), (20.0, 9.5)),
        2: ((20.0, 9.5), (10.0, 10.0)),
        3: ((10.0, 10.0), (9.5, 20.0)),
        4: ((9.5, 20.0), (10.5, 0.0)),
        5: ((10.5, 0.0), (10.0, 10.0)),
    }
    triangle_a_ids = frozenset({0, 1, 2})
    triangle_b_ids = frozenset({3, 4, 5})

    for order in itertools.permutations(range(6)):
        segments = [(segs[i], i) for i in order]
        contours, open_chains, duplicates = chain_contours(segments, TOL)

        assert len(duplicates) == 0, order
        assert len(open_chains) == 0, order
        assert len(contours) == 2, order
        assert sorted(len(c.points) for c in contours) == [3, 3], order

        # Los entity_ids de cada contorno resultante son exactamente los de
        # sus propios tramos, sin mezclarse entre los dos triangulos.
        ids_by_contour = {frozenset(c.entity_ids) for c in contours}
        assert ids_by_contour == {triangle_a_ids, triangle_b_ids}, order


def test_square_with_touching_hole_becomes_two_contours():
    """Un agujero cuadrado tangente al borde exterior en un vertice compartido."""
    segments = [
        (((0.0, 0.0), (20.0, 0.0)), 0),
        (((20.0, 0.0), (20.0, 20.0)), 1),
        (((20.0, 20.0), (0.0, 20.0)), 2),
        (((0.0, 20.0), (0.0, 0.0)), 3),
        (((0.0, 0.0), (5.0, 0.0)), 4),
        (((5.0, 0.0), (5.0, 5.0)), 5),
        (((5.0, 5.0), (0.0, 5.0)), 6),
        (((0.0, 5.0), (0.0, 0.0)), 7),
    ]
    contours, open_chains, duplicates = chain_contours(segments, TOL)

    assert len(duplicates) == 0
    assert len(open_chains) == 0
    assert len(contours) == 2
    assert sorted(len(c.points) for c in contours) == [4, 4]

    outer = next(c for c in contours if 0 in c.entity_ids)
    hole = next(c for c in contours if 4 in c.entity_ids)
    assert set(outer.entity_ids) == {0, 1, 2, 3}
    assert set(hole.entity_ids) == {4, 5, 6, 7}


# --- Hallazgo 2: deduplicar anillos ya cerrados -----------------------------


def test_closed_ring_with_even_point_count_dedupes_against_its_reverse():
    """Un anillo cerrado (agujero circular exportado como una sola entidad)
    con cantidad PAR de puntos y su copia invertida son el mismo tramo.

    `head == tail` nunca desempataba `head <= tail`, asi que `canonical`
    nunca se invertia; y el punto medio solo es invariante ante la reversion
    cuando la cantidad de puntos es impar. Con 4 puntos (par) el bug dejaba
    pasar el duplicado, y la pieza se emitia dos veces.
    """
    ring = ((0.0, 0.0), (10.0, 0.0), (5.0, 10.0), (0.0, 0.0))  # 4 puntos: par
    reversed_ring = tuple(reversed(ring))

    contours, open_chains, duplicates = chain_contours(
        [(ring, 0), (reversed_ring, 1)], TOL
    )
    assert len(duplicates) == 1
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_closed_ring_with_odd_point_count_still_dedupes_against_its_reverse():
    """Control de no-regresion: con cantidad impar ya deduplicaba bien."""
    ring = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))  # 5: impar
    reversed_ring = tuple(reversed(ring))

    contours, open_chains, duplicates = chain_contours(
        [(ring, 0), (reversed_ring, 1)], TOL
    )
    assert len(duplicates) == 1
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_closed_ring_dedupes_against_a_rotated_copy():
    """El mismo anillo, arrancando por otro vertice, tambien es un duplicado."""
    ring = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    rotated = ((10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0), (10.0, 0.0))

    contours, open_chains, duplicates = chain_contours(
        [(ring, 0), (rotated, 1)], TOL
    )
    assert len(duplicates) == 1
    assert len(contours) == 1
    assert len(open_chains) == 0


def test_distinct_closed_rings_with_same_point_count_are_not_deduped():
    """No falso positivo: dos anillos distintos con la misma cantidad de
    puntos no deben tratarse como duplicados (perderiamos una pieza real)."""
    ring_a = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0))
    ring_b = ((5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 6.0), (5.0, 5.0))

    contours, open_chains, duplicates = chain_contours(
        [(ring_a, 0), (ring_b, 1)], TOL
    )
    assert len(duplicates) == 0
    assert len(contours) == 2
    assert len(open_chains) == 0


# --- Hallazgo A: contabilidad de tramos y desempate unificado --------------


def _assert_all_ids_accounted_for(segments, tol=TOL):
    """Corre chain_contours y verifica que ningun entity_id de entrada se
    haya perdido ni se haya contado dos veces en la salida.

    chain_contours ya hace este chequeo internamente y explota si no cierra,
    asi que si esta funcion no lanza, ya sabemos que la cuenta esta bien;
    igual la repetimos aca desde afuera, con el conjunto de ids, para dejar
    el contrato de la tarea explicito en el propio test.
    """
    input_ids = [entity_id for _, entity_id in segments]
    contours, open_chains, duplicates = chain_contours(segments, tol)

    accounted = []
    for contour in contours:
        accounted.extend(contour.entity_ids)
    for chain in open_chains:
        accounted.extend(chain.entity_ids)

    assert len(accounted) + len(duplicates) == len(input_ids), (
        "la cantidad de tramos contabilizados no coincide con la entrada"
    )
    assert len(accounted) == len(set(accounted)), "hay ids repetidos en la salida"
    if not duplicates:
        assert sorted(accounted) == sorted(input_ids)

    return contours, open_chains, duplicates


def _bifurcation_with_spurious_return_segments():
    """Un cuadrado real (ids 0-3) mas un tramo espurio (id 4) que, colgado
    del primer vertice, vuelve a pasar a 0.09 mm del punto de arranque.

    Si se lo elige, el tramo espurio cierra un mini-lazo de solo 2 puntos
    (el propio arranque y el primer vertice) que no encierra area: es
    exactamente el escenario del hallazgo critico. La continuacion correcta
    (id 1) tambien esta disponible en el mismo punto, asi que hay una
    bifurcacion real. (0.09 en vez de un valor mas simple como 0.03: mas
    cerca del punto de arranque, `_snap` lo redondea a la misma celda que el
    propio (0, 0) y el tramo espurio queda accidentalmente indistinguible de
    una version acortada del tramo 0 para el deduplicador -- un artefacto de
    la construccion del test, no del bug bajo prueba.)
    """
    return [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (10.0, 10.0)), 1),      # continuacion correcta del cuadrado
        (((10.0, 0.0), (0.09, 0.0)), 4),       # tramo espurio: cierra cerca del arranque
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]


def test_spurious_returning_segment_does_not_steal_the_real_continuation():
    segments = _bifurcation_with_spurious_return_segments()
    contours, open_chains, duplicates = _assert_all_ids_accounted_for(segments)

    assert len(duplicates) == 0
    # El cuadrado real se reconstruye entero, con sus 4 tramos y sin el espurio.
    assert len(contours) == 1
    assert len(contours[0].points) == 4
    assert set(contours[0].entity_ids) == {0, 1, 2, 3}

    # El tramo espurio no desaparece: no cierra nada real, asi que queda
    # reportado como un chain abierto (o degenerado) en vez de perderse.
    assert len(open_chains) == 1
    assert open_chains[0].entity_ids == (4,)


def _tight_c_shape_segments():
    """Una "C" muy cerrada: a mitad de camino, el tramo 2 termina a ~0.054 mm
    del punto de arranque (0, 0), pero el trazado sigue de largo con los
    tramos 3 y 4 antes de terminar abierto, lejos del arranque.

    Con el corte viejo (cortar apenas la cola entra en tolerancia del
    arranque) esto se partia en dos: un "contorno" espurio de 3 puntos y un
    chain abierto separado con el resto. Debe seguir siendo UN solo chain
    abierto con los 5 tramos.
    """
    return [
        (((0.0, 0.0), (5.0, 0.0)), 0),
        (((5.0, 0.0), (5.0, 5.0)), 1),
        (((5.0, 5.0), (0.05, 0.02)), 2),       # pasa cerca del arranque, de paso
        (((0.05, 0.02), (-5.0, 0.02)), 3),
        (((-5.0, 0.02), (-5.0, 5.0)), 4),
    ]


def test_tight_c_shape_passing_near_its_own_start_does_not_split():
    segments = _tight_c_shape_segments()
    contours, open_chains, duplicates = _assert_all_ids_accounted_for(segments)

    assert len(duplicates) == 0
    assert len(contours) == 0, "no debe cerrarse en un contorno espurio a mitad de camino"
    assert len(open_chains) == 1, "debe seguir siendo un solo chain, no partirse en dos"
    assert set(open_chains[0].entity_ids) == {0, 1, 2, 3, 4}


def test_accounting_invariant_holds_across_several_scenarios():
    """El chequeo de contabilidad de ids se cumple en varios escenarios,
    incluidos los dos adversariales de arriba."""
    square = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (10.0, 10.0)), 1),
        (((10.0, 10.0), (0.0, 10.0)), 2),
        (((0.0, 10.0), (0.0, 0.0)), 3),
    ]
    square_with_touching_hole = [
        (((0.0, 0.0), (20.0, 0.0)), 0),
        (((20.0, 0.0), (20.0, 20.0)), 1),
        (((20.0, 20.0), (0.0, 20.0)), 2),
        (((0.0, 20.0), (0.0, 0.0)), 3),
        (((0.0, 0.0), (5.0, 0.0)), 4),
        (((5.0, 0.0), (5.0, 5.0)), 5),
        (((5.0, 5.0), (0.0, 5.0)), 6),
        (((0.0, 5.0), (0.0, 0.0)), 7),
    ]
    with_exact_duplicate = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((0.0, 0.0), (10.0, 0.0)), 1),
        (((10.0, 0.0), (10.0, 10.0)), 2),
        (((10.0, 10.0), (0.0, 10.0)), 3),
        (((0.0, 10.0), (0.0, 0.0)), 4),
    ]

    for scenario in (
        square,
        square_with_touching_hole,
        with_exact_duplicate,
        _bifurcation_with_spurious_return_segments(),
        _tight_c_shape_segments(),
    ):
        _assert_all_ids_accounted_for(scenario)


def test_invariant_checker_raises_on_a_manufactured_mismatch():
    """Prueba directa del propio mecanismo de contabilidad (Hallazgo A1).

    No encontramos ninguna entrada real para chain_contours que dispare
    ChainingInvariantError: cada tramo pasa por used[i] = True exactamente
    una vez antes de terminar en un Contour o un OpenChain, _drop_duplicates
    devuelve explicitamente los ids que descarta, y hasta los "contornos"
    degenerados ahora se emiten como OpenChain en vez de perderse. Con esa
    estructura la cuenta cierra siempre, por construccion.

    Para probar que el propio chequeo si explota cuando algo no cierra (en
    vez de quedarse callado), se llama directo a la funcion interna con una
    entrada armada a mano a la que le falta un id.
    """
    with pytest.raises(ChainingInvariantError, match="tramos perdidos"):
        chaining._check_invariant([0, 1, 2], [], [], [0, 1])  # falta el id 2

    with pytest.raises(ChainingInvariantError, match="contados de más"):
        chaining._check_invariant([0, 1], [], [], [0, 1, 1])  # el id 1 sobra


# --- Hallazgo B: la clave de anillos cerrados es demasiado permisiva -------


def test_square_and_bowtie_with_the_same_four_points_are_not_deduped():
    """El anillo real (`ring_a`) y un moño hecho con exactamente los mismos
    4 puntos pero en otro orden (`ring_b`) no son el mismo tramo: la clave
    vieja, `sorted(puntos)`, es invariante ante *cualquier* permutacion (no
    solo rotacion/reflexion) y los trataba como duplicados, descartando una
    pieza real en silencio."""
    ring_a = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    ring_b = ((0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0), (0.0, 0.0))

    contours, open_chains, duplicates = chain_contours(
        [(ring_a, 0), (ring_b, 1)], TOL
    )
    assert len(duplicates) == 0
    assert len(contours) == 2
    assert len(open_chains) == 0


# --- Hallazgo A3: la guarda anti-degeneracion no debe descalificar la ------
# --- adjuncion normal, solo el cierre ---------------------------------------


def test_degenerate_close_candidate_is_still_a_valid_attachment():
    """Bug de esta ronda: un tramo cuyo extremo lejano cae cerca del arranque
    cerraria un anillo degenerado (menos de MIN_CONTOUR_POINTS puntos) si se
    usara para cerrar, pero eso no lo descalifica como adjuncion normal --
    sigue siendo un vecino fisico legitimo al que hay que engancharse.

    id0 termina en (10, 0); id1 arranca justo ahi, o sea estan conectados.
    El otro extremo de id1, (0.08, 0), cae a 0.08 mm del arranque de id0:
    cerrar ahi formaria un anillo de solo 2 puntos. Antes de este arreglo,
    la guarda sacaba a id1 de la lista de candidatos por completo (no solo
    de la opcion de cerrar), asi que en ese punto no quedaba ninguna opcion
    y `_next_action` devolvia None: los dos tramos, pese a estar fisicamente
    conectados, salian como dos OpenChain separados y sin relacion aparente,
    cada uno con un gap enganoso (la longitud del propio tramo).
    """
    segments = [
        (((0.0, 0.0), (10.0, 0.0)), 0),
        (((10.0, 0.0), (0.08, 0.0)), 1),
    ]
    contours, open_chains, duplicates = chain_contours(segments, TOL)

    assert len(duplicates) == 0
    assert len(contours) == 0
    assert len(open_chains) == 1, "los dos tramos conectados no deben salir por separado"
    assert open_chains[0].entity_ids == (0, 1)
    assert math.isclose(open_chains[0].gap, 0.08, abs_tol=1e-9)


def _pentagon_with_spurious_intermediate_close_segments():
    """Un pentagono real de 5 tramos (ids 0-4) mas un tramo espurio (id 5)
    que, en el tercer vertice del recorrido, cerraria un anillo VALIDO (3
    puntos distintos: los primeros tres vertices del pentagono, v0-v1-v2).

    A diferencia de `_bifurcation_with_spurious_return_segments` (donde el
    cierre espurio es degenerado y queda descalificado antes de competir),
    aca el cierre espurio es perfectamente valido segun la cuenta de puntos
    -- por eso tiene que competir por angulo de giro contra la continuacion
    real (el siguiente lado del pentagono) en vez de ganar por default.
    """
    v = [
        (0.0, 10.0),
        (9.5106, 3.0902),
        (5.8779, -8.0902),
        (-5.8779, -8.0902),
        (-9.5106, 3.0902),
    ]
    segments = [
        ((v[0], v[1]), 0),
        ((v[1], v[2]), 1),
        ((v[2], v[3]), 2),
        ((v[3], v[4]), 3),
        ((v[4], v[0]), 4),
        ((v[2], v[0]), 5),  # espurio: cierra el triangulo valido v0-v1-v2
    ]
    return segments


def test_valid_non_degenerate_close_competes_by_angle_against_real_continuation():
    """Laguna de cobertura: el mecanismo central de Hallazgo A2 -- un cierre
    valido y no degenerado compitiendo por angulo contra una continuacion
    real -- no estaba ejercitado por ningun test.

    Al llegar al tercer vertice (v2), hay dos candidatos: adjuntar id2 (el
    siguiente lado real del pentagono, que sigue el giro suave del poligono)
    o adjuntar id5 (el tramo espurio, que exige un giro mucho mas brusco de
    vuelta hacia v0 y ademas cerraria un anillo valido de 3 puntos ahi
    mismo). Lo correcto es que gane id2 por angulo: el pentagono se
    reconstruye entero y el tramo espurio queda aparte, sin fusionarse.

    Con la preferencia incondicional de cierre (el bug anterior a Hallazgo
    A2: elegir automaticamente cualquier candidato cuyo extremo lejano caiga
    cerca del arranque, sin competir por angulo), los 6 tramos se fusionaban
    en una sola cadena abierta -- confirmado por mutacion manual durante el
    desarrollo de este test.
    """
    segments = _pentagon_with_spurious_intermediate_close_segments()
    contours, open_chains, duplicates = chain_contours(segments, TOL)

    assert len(duplicates) == 0
    assert len(contours) == 1, "el pentagono real se tiene que reconocer como un solo contorno"
    assert len(contours[0].points) == 5
    assert set(contours[0].entity_ids) == {0, 1, 2, 3, 4}

    assert len(open_chains) == 1
    assert open_chains[0].entity_ids == (5,)


def test_already_closed_entity_with_too_few_points_becomes_an_open_chain():
    """Laguna de cobertura (menor): la rama de `_emit` que convierte un
    cierre degenerado en OpenChain solo se ejercitaba a traves del walker
    (Hallazgo A1); nunca con una entidad que YA llega cerrada, con menos de
    MIN_CONTOUR_POINTS puntos distintos -- el caso de una polilinea de "ida y
    vuelta" exportada como una sola entidad: (0,0) -> (5,5) -> (0,0).

    No debe perderse el id, no debe lanzar excepcion, y tiene que salir como
    OpenChain (no como Contour: dos puntos distintos no encierran area).
    """
    segments = [(((0.0, 0.0), (5.0, 5.0), (0.0, 0.0)), 42)]
    contours, open_chains, duplicates = chain_contours(segments, TOL)

    assert len(duplicates) == 0
    assert len(contours) == 0
    assert len(open_chains) == 1
    assert open_chains[0].entity_ids == (42,)


def test_duplicates_are_reported_by_entity_id_not_just_counted():
    """Sin el id no hay forma de mostrarle al usuario CUÁL entidad se tiró.

    El contador solo decía "se descartaron 2"; para marcarlas sobre el dibujo
    hace falta saber cuáles son, y el dedup ya lo sabe -- lo tiraba al salir.
    """
    ring = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    segments = [(ring, 7), (ring, 42), (ring, 99)]

    _, _, duplicates = chain_contours(segments, TOL)

    assert set(duplicates) == {42, 99}, "se queda con la primera, tira el resto"


def test_the_id_reported_is_the_copy_and_never_the_original():
    """Marcar el original en vez de la copia mandaría al usuario al lugar
    correcto pero a culpar a la entidad equivocada. Coinciden en geometría,
    así que el único modo de notar la confusión es por el id."""
    ring = ((0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0), (0.0, 0.0))
    contours, _, duplicates = chain_contours([(ring, 3), (ring, 4)], TOL)

    assert list(duplicates) == [4]
    assert contours[0].entity_ids == (3,)
