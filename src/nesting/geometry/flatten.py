"""Curve -> polyline conversion with a bounded chord error.

This is the only place in the project that introduces geometric approximation,
which is why the tolerance is explicit and guaranteed rather than incidental.
The result feeds the nesting engine and the verifier; the output file is always
written from the exact entities instead.
"""

import math

from nesting.model.entities import Arc, Bezier, Circle, Entity, Line, Point, Polyline

MIN_CIRCLE_SEGMENTS = 8
"""A full circle never gets fewer segments than this, however loose the tolerance."""


def flatten(e: Entity, tolerance: float) -> tuple[Point, ...]:
    """Approximate `e` by a polyline whose deviation is at most `tolerance` mm.

    Both endpoints are always included. A `Circle` is returned as a ring whose
    first point is *not* repeated at the end; a closed `Polyline` does repeat it,
    matching how each one is normally consumed.
    """
    if tolerance <= 0.0:
        raise ValueError(f"la tolerancia debe ser positiva, se recibió {tolerance}")

    match e:
        case Line():
            return (e.start, e.end)

        case Polyline():
            if e.closed and e.points and e.points[0] != e.points[-1]:
                return tuple(e.points) + (e.points[0],)
            return tuple(e.points)

        case Circle():
            count = _segment_count(e.radius, 2 * math.pi, tolerance)
            count = max(count, MIN_CIRCLE_SEGMENTS)
            step = 2 * math.pi / count
            return tuple(
                (e.center[0] + e.radius * math.cos(i * step),
                 e.center[1] + e.radius * math.sin(i * step))
                for i in range(count)
            )

        case Arc():
            sweep = math.radians((e.end_angle - e.start_angle) % 360.0)
            if sweep == 0.0:
                sweep = 2 * math.pi
            count = _segment_count(e.radius, sweep, tolerance)
            # The floor that keeps a full circle from degenerating applies to arcs
            # too, scaled to how much of a circle this one actually sweeps.
            count = max(count, math.ceil(MIN_CIRCLE_SEGMENTS * sweep / (2 * math.pi)))
            start = math.radians(e.start_angle)
            step = sweep / count
            return tuple(
                (e.center[0] + e.radius * math.cos(start + i * step),
                 e.center[1] + e.radius * math.sin(start + i * step))
                for i in range(count + 1)
            )

        case Bezier():
            out: list[Point] = [e.p0]
            _subdivide_bezier(e.p0, e.p1, e.p2, e.p3, tolerance, out, depth=0)
            return tuple(out)

    raise TypeError(f"unsupported entity type: {type(e).__name__}")


def _segment_count(radius: float, sweep: float, tolerance: float) -> int:
    """Segments needed so the sagitta of each one stays within `tolerance`.

    A chord spanning `delta` radians on a circle of radius `r` bulges away from
    the arc by `r * (1 - cos(delta / 2))`. Solving for `delta` gives the widest
    step allowed.
    """
    if radius <= 0.0:
        return 1
    ratio = 1.0 - tolerance / radius
    if ratio <= -1.0:
        return 1
    delta = 2.0 * math.acos(max(-1.0, min(1.0, ratio)))
    if delta <= 0.0:
        return 1
    return max(1, math.ceil(sweep / delta))


MAX_BEZIER_DEPTH = 24
"""Recursion guard. At this depth a segment is 1/16M of the curve; a degenerate
curve that never passes the flatness test stops here instead of overflowing."""


def _subdivide_bezier(
    p0: Point, p1: Point, p2: Point, p3: Point,
    tolerance: float, out: list[Point], depth: int,
) -> None:
    """Append the flattened curve to `out`, excluding `p0` and including `p3`."""
    if depth >= MAX_BEZIER_DEPTH or _is_flat(p0, p1, p2, p3, tolerance):
        out.append(p3)
        return

    # De Casteljau split at t = 0.5.
    p01 = _midpoint(p0, p1)
    p12 = _midpoint(p1, p2)
    p23 = _midpoint(p2, p3)
    p012 = _midpoint(p01, p12)
    p123 = _midpoint(p12, p23)
    mid = _midpoint(p012, p123)

    _subdivide_bezier(p0, p01, p012, mid, tolerance, out, depth + 1)
    _subdivide_bezier(mid, p123, p23, p3, tolerance, out, depth + 1)


def _is_flat(p0: Point, p1: Point, p2: Point, p3: Point, tolerance: float) -> bool:
    """True when both control points lie within `tolerance` of the CHORD p0-p3.

    Distance is measured to the chord *segment*, not to the infinite line through
    it. That distinction is the whole correctness of this test: a control point
    can sit exactly on the line yet far beyond p3 - which happens at cusps - and
    a line-distance test would call that flat while the curve still overshoots.

    Measuring to the segment makes the test genuinely conservative. Distance to a
    convex set is a convex function, so its maximum over the convex hull of the
    control points is attained at one of them; the curve lies inside that hull,
    so bounding the control points bounds the curve.
    """
    return (
        _point_segment_distance(p1, p0, p3) <= tolerance
        and _point_segment_distance(p2, p0, p3) <= tolerance
    )


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length_squared))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def _midpoint(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
