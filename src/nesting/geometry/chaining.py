"""Rebuild closed loops out of loose segments.

CorelDRAW exports split every outline into dozens of separate LINE, ARC and
SPLINE entities rather than closed polylines, so this is the normal path, not an
error path. It is also the dirtiest code in the project, which is why it lives
on its own behind a narrow interface.
"""

import math
from collections import Counter
from collections.abc import Sequence

from scipy.spatial import cKDTree

from nesting.model.entities import Point
from nesting.model.part import Contour, OpenChain

MIN_CONTOUR_POINTS = 3
"""Fewer than three distinct points cannot enclose any area."""


class ChainingInvariantError(RuntimeError):
    """`chain_contours` lost track of an input segment, or double-counted one.

    This is a bug in this module, not in the user's drawing: every entity_id
    handed to `chain_contours` must end up in exactly one place (a contour, an
    open chain, or the duplicates count). Rather than silently return
    incomplete geometry to a CNC job, we raise loudly so the bug gets fixed.
    """


def chain_contours(
    segments: Sequence[tuple[tuple[Point, ...], int]],
    tol: float,
) -> tuple[list[Contour], list[OpenChain], tuple[int, ...]]:
    """Join `segments` end to end into closed contours.

    Each input is a flattened polyline paired with the id of the entity it came
    from. Returns the closed contours, the runs that failed to close (this
    includes runs that did close geometrically but collapsed to fewer than
    `MIN_CONTOUR_POINTS` distinct points -- see `_emit`), and the ids of the
    duplicate segments that were discarded.

    Los ids salen en vez de un contador porque el mismo dato sirve para las
    dos cosas: `len(...)` da el aviso de texto, y los ids permiten marcar
    sobre el dibujo cuál entidad se tiró. Devolver solo el numero obligaba a
    recalcular el dedup afuera para averiguarlo, y dos calculos del mismo
    hecho pueden discrepar.

    Before returning, verifies that every input entity_id is accounted for
    exactly once across contours + open chains + duplicates. If not, raises
    `ChainingInvariantError` instead of handing back incomplete geometry.
    """
    input_ids = [entity_id for _, entity_id in segments]
    kept, duplicate_ids = _drop_duplicates(segments, tol)
    if not kept:
        _check_invariant(input_ids, [], [], duplicate_ids)
        return [], [], tuple(duplicate_ids)

    paths = [list(points) for points, _ in kept]
    ids = [entity_id for _, entity_id in kept]

    endpoints = []
    for path in paths:
        endpoints.append(path[0])
        endpoints.append(path[-1])
    tree = cKDTree(endpoints)

    used = [False] * len(paths)
    contours: list[Contour] = []
    open_chains: list[OpenChain] = []

    for seed in range(len(paths)):
        if used[seed]:
            continue
        used[seed] = True
        points = list(paths[seed])
        chain_ids = [ids[seed]]

        if _is_closed(points, tol):
            _emit(points, chain_ids, tol, contours, open_chains)
            continue

        # Walk forward, then reverse and walk forward again, which extends the
        # other end. Two passes are enough because after the reversal the former
        # head is the tail.
        for _ in range(2):
            _extend_forward(points, chain_ids, paths, ids, used, tree, tol)
            if _is_closed(points, tol):
                break
            points.reverse()

        _emit(points, chain_ids, tol, contours, open_chains)

    _check_invariant(input_ids, contours, open_chains, duplicate_ids)
    return contours, open_chains, tuple(duplicate_ids)


def _check_invariant(
    input_ids: Sequence[int],
    contours: list[Contour],
    open_chains: list[OpenChain],
    duplicate_ids: Sequence[int],
) -> None:
    """Every input entity_id must appear exactly once across the outputs.

    This is the accounting safety net for Hallazgo A: no matter what the
    walking/tie-break logic above does, a tramo can never vanish (nor get
    double-counted) between the input and (contours + open_chains +
    duplicates). If it does, that is a programming error in this module, not
    a malformed user file, so we blow up loudly instead of returning geometry
    with a silently missing side.
    """
    accounted: list[int] = list(duplicate_ids)
    for contour in contours:
        accounted.extend(contour.entity_ids)
    for chain in open_chains:
        accounted.extend(chain.entity_ids)

    expected = Counter(input_ids)
    actual = Counter(accounted)
    if expected == actual:
        return

    missing = sorted((expected - actual).elements())
    extra = sorted((actual - expected).elements())
    detail_parts = []
    if missing:
        detail_parts.append(f"tramos perdidos (no aparecen en ninguna salida): {missing}")
    if extra:
        detail_parts.append(f"tramos contados de más (aparecen repetidos): {extra}")
    detail = "; ".join(detail_parts) or "las cantidades no coinciden"
    raise ChainingInvariantError(
        "chain_contours perdió la contabilidad de los tramos de entrada: "
        f"{detail}. Esto es un bug del módulo de encadenado (chaining.py), "
        "no un problema del archivo del usuario."
    )


def _extend_forward(
    points: list[Point],
    chain_ids: list[int],
    paths: list[list[Point]],
    ids: list[int],
    used: list[bool],
    tree: cKDTree,
    tol: float,
) -> None:
    """Keep attaching unused segments to the tail of `points`."""
    while True:
        action = _next_action(points, paths, used, tree, tol)
        if action is None or action[0] == "close":
            return
        _, index, at_tail = action
        used[index] = True
        nxt = list(paths[index])
        if at_tail:
            nxt.reverse()
        points.extend(nxt[1:])
        chain_ids.append(ids[index])


def _next_action(
    points: list[Point],
    paths: list[list[Point]],
    used: list[bool],
    tree: cKDTree,
    tol: float,
) -> tuple[str, int, bool] | tuple[str, None, None] | None:
    """Decide what `_extend_forward` should do next, from the chain's tail.

    Returns `("attach", index, at_tail)` to append that unused segment,
    `("close", None, None)` to stop right here without consuming another
    segment, or `None` when there is nothing left to attach and the chain is
    not closed (it will end up an open chain).

    Hallazgo A2: closing used to short-circuit everything else -- either by
    unconditionally preferring, among the segments touching the tail, the one
    whose far end also lands near the start (Hallazgo original's point 1), or
    by cutting the walk the instant the tail itself drifted within `tol` of
    the start (the old `_is_closed` check in the caller). Both let a single
    stray proximity hit override the geometry: a spurious segment that merely
    happens to pass close to the start point could steal the win from the
    real continuation, and a tight "C" or spiral that legitimately passes
    near its own start mid-route got cut in two.

    Now "stop, the chain is closed" is just one more candidate, and it
    competes on the same turning-angle footing as every "attach segment X"
    candidate: whichever keeps the smoothest heading wins. A "stop here,
    without consuming anything" close that would collapse the ring to fewer
    than MIN_CONTOUR_POINTS distinct points is not offered at all -- it can
    never win, because it is not in the running.

    Hallazgo A3 (this round): "can this candidate close the chain?" and "can
    this candidate continue the chain?" are two different questions, and the
    degeneracy guard above only answers the first one. A segment whose far
    end happens to land near the start is still a legitimate neighbour to
    attach even when the ring it would form *right now* is degenerate --
    attaching it does not itself close anything, it just moves the tail.
    Whether the (possibly longer) ring can close from there is re-decided,
    with the same guard, the next time this function runs, once `points`
    actually reflects the attach (see `can_close` below). The previous
    version disqualified such a candidate from attaching at all, not just
    from closing: when it was the only candidate touching the tail, that
    turned `_next_action` into `None` instead of an attach, so two segments
    that are plainly connected end to end came back as two unrelated
    `OpenChain`s instead of one.

    Determinism: ties in angle between two *attach* candidates are broken by
    the lower segment index (same rule as before). A tie between "close" and
    an attach candidate is broken in favour of closing -- there is no segment
    index to compare, and preferring to finish the shape over greedily
    consuming a same-angle neighbour is the safer default (this is what keeps
    a contour from fusing with another shape that merely touches it at one
    vertex with the same heading, see test_square_with_touching_hole).
    """
    target = points[-1]
    start = points[0]

    candidates: list[tuple[int, bool]] = []
    for endpoint_index in tree.query_ball_point(target, tol):
        index, which_end = divmod(endpoint_index, 2)
        if used[index]:
            continue
        candidates.append((index, which_end == 1))

    gap_to_start = math.dist(target, start)
    can_close = gap_to_start <= tol and _ring_point_count(points, tol) >= MIN_CONTOUR_POINTS

    if not candidates:
        return ("close", None, None) if can_close else None

    arrival = _direction(points[-2], points[-1])

    def turn_from_arrival(attach: Point, next_point: Point) -> float:
        outgoing = _direction(attach, next_point)
        if outgoing is None or arrival is None:
            return math.pi  # degenerate leading edge: least preferred, never wins ties
        return _turn_angle(arrival, outgoing)

    # (angle, tie-break key, action). "close" sorts before any real segment
    # index on an exact tie, since its tie-break key (-1) is lower than any
    # non-negative segment index.
    options: list[tuple[float, int, tuple]] = []
    for index, at_tail in candidates:
        segment = paths[index]
        attach, next_point = (segment[-1], segment[-2]) if at_tail else (segment[0], segment[1])
        angle = turn_from_arrival(attach, next_point)
        options.append((angle, index, ("attach", index, at_tail)))

    if can_close:
        angle = turn_from_arrival(start, points[1])
        options.append((angle, -1, ("close", None, None)))

    options.sort(key=lambda option: (option[0], option[1]))
    return options[0][2]


def _ring_point_count(points: list[Point], tol: float) -> int:
    """How many distinct vertices the ring made from `points` would have.

    Mirrors the trimming `_emit` does when finishing a chain: drop the
    duplicated closing point (if the run is actually closed), then collapse
    consecutive near-duplicates, and count what is left.
    """
    gap = math.dist(points[0], points[-1])
    ring = points[:-1] if gap <= tol and len(points) > 1 else points
    ring = _drop_consecutive_duplicates(ring, tol)
    return len(ring)


def _direction(a: Point, b: Point) -> float | None:
    """Heading from `a` to `b` in radians, or None if the two points coincide."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return None
    return math.atan2(dy, dx)


def _turn_angle(a: float, b: float) -> float:
    """Absolute turning angle between two headings, in [0, pi]."""
    return abs((b - a + math.pi) % (2 * math.pi) - math.pi)


def _emit(
    points: list[Point],
    chain_ids: list[int],
    tol: float,
    contours: list[Contour],
    open_chains: list[OpenChain],
) -> None:
    """Classify a finished run as a closed contour or an open chain.

    A run that geometrically closes but collapses to fewer than
    MIN_CONTOUR_POINTS distinct points (a mini-loop, no enclosed area) used to
    be dropped here in silence -- its entity_ids ended up nowhere: not in a
    Contour, not in an OpenChain, not counted as a duplicate. That is exactly
    the silent tramo loss Hallazgo A1 is about. It is now emitted as an
    OpenChain instead of a Contour, so (a) the accounting invariant in
    chain_contours always balances, and (b) the user actually sees that a bit
    of geometry didn't make it into a real piece, instead of it vanishing.
    """
    gap = math.dist(points[0], points[-1])
    if gap > tol:
        open_chains.append(OpenChain(tuple(points), tuple(chain_ids), gap))
        return

    ring = points[:-1] if gap <= tol and len(points) > 1 else points
    ring = _drop_consecutive_duplicates(ring, tol)
    if len(ring) < MIN_CONTOUR_POINTS:
        open_chains.append(OpenChain(tuple(points), tuple(chain_ids), gap))
        return
    contours.append(Contour(tuple(ring), tuple(chain_ids)))


def _is_closed(points: list[Point], tol: float) -> bool:
    return len(points) > 2 and math.dist(points[0], points[-1]) <= tol


def _drop_consecutive_duplicates(points: list[Point], tol: float) -> list[Point]:
    out: list[Point] = []
    for p in points:
        if not out or math.dist(out[-1], p) > tol:
            out.append(p)
    return out


def _drop_duplicates(
    segments: Sequence[tuple[tuple[Point, ...], int]],
    tol: float,
) -> tuple[list[tuple[tuple[Point, ...], int]], list[int]]:
    """Remove segments that repeat an earlier one, in either direction.

    Corel exports frequently draw the same line twice. For an open run the key
    is built from the two endpoints plus a middle point and the point count,
    snapped to the tolerance grid. To make that key order-independent, the
    point list is first put into a canonical direction (the one whose snapped
    head sorts first) so that a segment and its reversed duplicate pick the
    same physical point as "middle", rather than the middle index landing on
    different points once the list has been flipped.

    A segment that already arrives closed (head == tail, e.g. a circular hole
    exported as one entity) cannot use that scheme: `head <= tail` never
    breaks the tie, so `canonical` is never flipped, and the middle-point
    invariance under reversal only holds when the point count is odd (the
    middle index is only then a fixed point of the reversal). A closed ring
    and its reversed copy would then dodge deduplication whenever they have an
    even number of points, and get cut twice. Closed rings instead get a key
    built from `_ring_shape_key`, the canonical form of the ring's snapped
    points under rotation and reflection (see Hallazgo B there for why that is
    the right symmetry, and why plain `sorted(...)` was wrong).

    Returns the kept segments, plus the entity_id of every segment that was
    discarded (either because it had fewer than 2 points, or because it
    repeated an earlier key) -- the caller needs those ids for the
    bookkeeping invariant in `chain_contours`.
    """
    seen: set[tuple] = set()
    kept: list[tuple[tuple[Point, ...], int]] = []
    duplicate_ids: list[int] = []

    for points, entity_id in segments:
        if len(points) < 2:
            duplicate_ids.append(entity_id)
            continue
        head = _snap(points[0], tol)
        tail = _snap(points[-1], tol)
        if head == tail:
            key = ("ring", _ring_shape_key(points, tol))
        else:
            canonical = points if head <= tail else tuple(reversed(points))
            middle = _snap(canonical[len(canonical) // 2], tol)
            key = ("open", min(head, tail), max(head, tail), middle, len(points))
        if key in seen:
            duplicate_ids.append(entity_id)
            continue
        seen.add(key)
        kept.append((points, entity_id))

    return kept, duplicate_ids


def _ring_shape_key(points: tuple[Point, ...], tol: float) -> tuple[tuple[int, int], ...]:
    """Canonical form of an already-closed ring's snapped points, under the
    dihedral group (rotation + reflection) -- the actual symmetry a ring has.

    Hallazgo B: the previous key, `sorted(snapped points)`, is invariant
    under *any* permutation of the points, not just rotation and reflection.
    That means a square `(0,0)-(10,0)-(10,10)-(0,10)` and a self-intersecting
    bowtie visiting the exact same four corners in a different order,
    `(0,0)-(10,10)-(10,0)-(0,10)`, hash identically and the second gets
    thrown out as a "duplicate" of the first -- a false positive that
    silently discards a legitimate piece.

    The fix: try every rotation of the snapped point sequence and every
    rotation of its reverse, and keep the lexicographically smallest one.
    That is O(n^2) in the number of points in the ring (n rotations, each an
    O(n) comparison/slice), which is fine here because individual rings are
    short -- a handful to a few dozen points, not thousands. If this ever
    turns up as a bottleneck, Booth's algorithm computes the canonical
    rotation in O(n).
    """
    snapped = tuple(_snap(p, tol) for p in points[:-1])  # drop the repeated closing point
    n = len(snapped)
    if n == 0:
        return snapped
    reversed_snapped = tuple(reversed(snapped))
    return min(
        base[i:] + base[:i]
        for base in (snapped, reversed_snapped)
        for i in range(n)
    )


def _snap(p: Point, tol: float) -> tuple[int, int]:
    return (round(p[0] / tol), round(p[1] / tol))
