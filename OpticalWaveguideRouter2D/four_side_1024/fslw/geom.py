"""R>=40 mm D56 path geometry for the FSLW experiment.

Only the three legacy D56 primitive kinds are produced: axis-aligned straight lines,
fixed-radius quarter-circle corner arcs and the original small-displacement short-S
pair of arcs with ``theta = acos(1 - d/(2R))``.  Nothing here invents F56 free-form
corners, slanted lines or Dubins curves, and the radius is never reduced below
``config.RADIUS_MM``.

A 40 mm radius consumes a 40x40 mm square per turn on a 150x150 mm board, so the
classic D56 templates are re-derived instead of copied: several families that were
trivially available at R=5 mm become geometrically infeasible at R=40 mm, and the
short-S pair becomes a *large* lateral shifter (up to 80 mm of travel).
"""
from __future__ import annotations

import math

from ..geometry import validate
from ..legacy_geometry import _orthogonal_quarters, canonicalize, opposite as legacy_opposite
from . import config as C

TOL = 1e-9


def _rotate(vector, angle):
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (vector[0] * cos_a - vector[1] * sin_a,
            vector[0] * sin_a + vector[1] * cos_a)


def _rot90(vector):
    return (-vector[1], vector[0])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _scale(vector, factor):
    return (vector[0] * factor, vector[1] * factor)


def _unit(vector):
    length = math.hypot(vector[0], vector[1])
    return (vector[0] / length, vector[1] / length)


def line(p0, p1):
    return dict(kind='line', p0=[float(p0[0]), float(p0[1])],
                p1=[float(p1[0]), float(p1[1])], layer=0)


def arc(p0, p1, center, radius, start_angle, sweep):
    return dict(kind='arc', p0=[float(p0[0]), float(p0[1])],
                p1=[float(p1[0]), float(p1[1])],
                center=[float(center[0]), float(center[1])],
                radius=float(radius), start_angle=float(start_angle),
                sweep=float(sweep), layer=0)


def _append_line(result, p0, p1):
    if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 1e-10:
        result.append(line(p0, p1))


def canonical_validate(primitives, p, q, start_dir, end_dir,
                       radius=None, width=None):
    """Validate inside the canonical frame (rigid transforms preserve the board)."""
    radius = C.RADIUS_MM if radius is None else radius
    width = C.WIDTH_MM if width is None else width
    errors = validate(primitives, p, q, start_dir, end_dir,
                      board=C.BOARD_MM, width=width, min_radius=radius)
    return not errors, errors


# --------------------------------------------------------------- short-S pair
def short_s(start, travel, shift, radius=None):
    """Two-arc short-S: travel along ``travel`` while shifting sideways by ``shift``.

    ``shift`` is signed along ``rot90(travel)``.  ``theta = acos(1 - |shift|/(2R))``
    and the arc pair advances ``2R*sin(theta)`` along the travel direction, exactly the
    historical AutoRouter small-displacement S formula.  Returns
    ``(primitives, end_point, end_direction)`` or ``(None, None, None)`` when the
    shift cannot be realised with this radius.
    """
    radius = C.RADIUS_MM if radius is None else float(radius)
    if abs(shift) <= 1e-9:
        return [], tuple(start), tuple(travel)
    if abs(shift) >= 2.0 * radius - 1e-9:
        return None, None, None
    theta = math.acos(1.0 - abs(shift) / (2.0 * radius))
    sign = 1.0 if shift > 0 else -1.0
    u = _unit(travel)
    ccw = sign                                  # +1: left turn, -1: right turn
    center1 = _add(start, _scale(_rot90(u), radius * ccw))
    start_offset = _sub(start, center1)
    phi0 = math.atan2(start_offset[1], start_offset[0])
    sweep1 = ccw * theta
    phi1 = phi0 + sweep1
    end1 = _add(center1, _scale((math.cos(phi1), math.sin(phi1)), radius))
    tangent1 = (-math.sin(phi1) * ccw, math.cos(phi1) * ccw)
    # second arc turns the other way: its centre lies on the opposite normal
    center2 = _add(end1, _scale(_rot90(tangent1), -radius * ccw))
    offset2 = _sub(end1, center2)
    phi2 = math.atan2(offset2[1], offset2[0])
    sweep2 = -ccw * theta
    phi3 = phi2 + sweep2
    end2 = _add(center2, _scale((math.cos(phi3), math.sin(phi3)), radius))
    primitives = [arc(start, end1, center1, radius, phi0, sweep1),
                  arc(end1, end2, center2, radius, phi2, sweep2)]
    return primitives, end2, _unit(travel)


# ----------------------------------------------------------------- staircases
def staircase(vertices, start_dir, end_dir, radius=None, width=None):
    """Legacy orthogonal staircase with fixed-radius quarter arcs, R>=40 checked."""
    radius = C.RADIUS_MM if radius is None else float(radius)
    width = C.WIDTH_MM if width is None else float(width)
    points = [(float(value[0]), float(value[1])) for value in vertices]
    try:
        primitives = _orthogonal_quarters(points, radius)
    except (ValueError, IndexError, ZeroDivisionError):
        return None
    ok, _errors = canonical_validate(primitives, points[0], points[-1],
                                     start_dir, end_dir, radius, width)
    return primitives if ok else None


# ------------------------------------------------------------------ opposite
def opposite_path(p, q, track, radius=None, width=None):
    """Canonical S->N legacy U path (with its short-S branch when dx < 2R)."""
    radius = C.RADIUS_MM if radius is None else float(radius)
    width = C.WIDTH_MM if width is None else float(width)
    try:
        primitives = legacy_opposite(p, q, float(track), radius=radius, width=width)
    except ValueError:
        return None
    ok, _errors = canonical_validate(primitives, p, q, (0.0, 1.0), (0.0, 1.0),
                                     radius, width)
    return primitives if ok else None


def opposite_tracks(dx, radius=None):
    """Feasible transfer-track range for the canonical opposite U/short-S family."""
    radius = C.RADIUS_MM if radius is None else float(radius)
    dx = abs(float(dx))
    if dx < 1e-9:
        return None
    if dx >= 2.0 * radius:
        return radius, C.BOARD_MM - radius
    theta = math.acos(1.0 - dx / (2.0 * radius))
    height = radius * math.sin(theta)
    return height, C.BOARD_MM - height


# ------------------------------------------------------------------- adjacent
def adjacent_l(p, q, radius=None, width=None):
    """Rigid single-L: p up to (p.x, q.y) then straight to q (only if it fits)."""
    radius = C.RADIUS_MM if radius is None else float(radius)
    return staircase([p, (p[0], q[1]), q], (0.0, 1.0), (1.0, 0.0), radius, width)


def adjacent_z3(p, q, y1, x1, radius=None, width=None):
    """Four-segment adjacent staircase [p,(sx,y1),(x1,y1),(x1,qy),q]."""
    radius = C.RADIUS_MM if radius is None else float(radius)
    return staircase([p, (p[0], y1), (x1, y1), (x1, q[1]), q],
                     (0.0, 1.0), (1.0, 0.0), radius, width)


def adjacent_turn_shift(p, q, y0, radius=None, width=None):
    """Quarter turn right at height ``y0``, then a horizontal short-S to ``q.y``.

    From the canonical port ``p=(sx,0)`` travelling +y: straight up to ``y0``, quarter
    arc to ``(sx+R, y0+R)`` travelling +x, then the two-arc short-S shifts the line to
    ``q.y`` while keeping the +x travel, then a straight line into ``q``.
    """
    radius = C.RADIUS_MM if radius is None else float(radius)
    width = C.WIDTH_MM if width is None else float(width)
    sx, qy = p[0], q[1]
    if y0 < -TOL or y0 > C.BOARD_MM - radius + TOL:
        return None
    primitives = []
    _append_line(primitives, (sx, 0.0), (sx, y0))
    center = (sx + radius, y0)
    phi0 = math.atan2(y0 - y0, sx - center[0])          # == pi
    phi1 = phi0 - math.pi / 2.0
    end1 = _add(center, _scale((math.cos(phi1), math.sin(phi1)), radius))
    primitives.append(arc((sx, y0), end1, center, radius, phi0, -math.pi / 2.0))
    shift = qy - end1[1]
    if abs(shift) >= 2.0 * radius - 1e-9:
        return None
    end2 = end1
    if abs(shift) > 1e-9:
        s_primitives, end2, _end_dir = short_s(end1, (1.0, 0.0), shift, radius)
        if s_primitives is None:
            return None
        primitives.extend(s_primitives)
    if end2[0] > C.BOARD_MM + TOL:
        return None
    _append_line(primitives, end2, q)
    ok, _errors = canonical_validate(primitives, p, q, (0.0, 1.0), (1.0, 0.0),
                                     radius, width)
    return primitives if ok else None


def adjacent_shift_turn(p, q, dx_shift, radius=None, width=None):
    """Vertical short-S shifting x, then a quarter turn right into the x=150 edge.

    Needs ``q.y + R <= 150`` (the quarter turn lands on the target row ``q.y``).
    """
    radius = C.RADIUS_MM if radius is None else float(radius)
    width = C.WIDTH_MM if width is None else float(width)
    sx, qy = p[0], q[1]
    if qy < radius - TOL or qy > C.BOARD_MM + TOL:
        return None
    if abs(dx_shift) >= 2.0 * radius - 1e-9:
        return None
    primitives = []
    cursor = (sx, 0.0)
    # travelling +y, rot90(+y) == -x, so an x-shift of +dx is a shift of -dx here
    if abs(dx_shift) > 1e-9:
        s_primitives, end_shift, _end_dir = short_s(cursor, (0.0, 1.0),
                                                    -float(dx_shift), radius)
        if s_primitives is None:
            return None
        primitives.extend(s_primitives)
        cursor = end_shift
    target_y = qy - radius
    if cursor[1] > target_y + TOL:
        return None
    _append_line(primitives, cursor, (cursor[0], target_y))
    turn_start = (cursor[0], target_y)
    center = (cursor[0] + radius, target_y)
    phi0 = math.atan2(target_y - target_y, turn_start[0] - center[0])   # == pi
    phi1 = phi0 - math.pi / 2.0
    end_turn = _add(center, _scale((math.cos(phi1), math.sin(phi1)), radius))
    primitives.append(arc(turn_start, end_turn, center, radius, phi0, -math.pi / 2.0))
    _append_line(primitives, end_turn, q)
    ok, _errors = canonical_validate(primitives, p, q, (0.0, 1.0), (1.0, 0.0),
                                     radius, width)
    return primitives if ok else None


def adjacent_z5(p, q, y1, x1, y2, x2, radius=None, width=None):
    """Five-segment staircase [p,(sx,y1),(x1,y1),(x1,y2),(x2,y2),(x2,qy),q]."""
    radius = C.RADIUS_MM if radius is None else float(radius)
    return staircase([p, (p[0], y1), (x1, y1), (x1, y2), (x2, y2), (x2, q[1]), q],
                     (0.0, 1.0), (1.0, 0.0), radius, width)


def adjacent_left_y(p, q, y1, x_left, radius=None, width=None):
    """C-shaped staircase that turns left first (for sources too close to x=150)."""
    radius = C.RADIUS_MM if radius is None else float(radius)
    return staircase([p, (p[0], y1), (x_left, y1), (x_left, q[1]), q],
                     (0.0, 1.0), (1.0, 0.0), radius, width)
