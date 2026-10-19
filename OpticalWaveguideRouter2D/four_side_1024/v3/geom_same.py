"""Same-side (NN / SS / EE / WW) D56 path families at R = 40 mm.

Canonical frame (see :mod:`four_side_1024.v3.frames`): both ports on the board edge
``y = 0``, start direction +y (inward), end direction -y (back into the edge port).
A same-side path must therefore turn a net 180 degrees inside the board.

Families implemented (axis-aligned lines + quarter arcs of exactly R + the historical
short-S pair only):

``SAME_U``
    rectangle U: up to depth H, across, down.  Requires |dx| >= 2R = 80 mm because the
    two quarter turns consume 2R of the horizontal run.

``SAME_HAIRPIN_A`` (short-S first)
    up, short-S lateral shift, 180-degree hairpin (two consecutive quarter arcs,
    lateral 2R), straight down into the target.  Covers the small-separation cases
    (395 / 448 same-side pairs have |dx| < 80 mm).

``SAME_HAIRPIN_B`` (hairpin first)
    up, 180-degree hairpin, then a short-S while descending, straight down.
    Different footprint, useful for nesting and obstacle avoidance.

Total lateral displacement is ``dx``: the hairpin contributes exactly ``sign*2R`` and
the short-S contributes ``delta = dx - sign*2R`` (|delta| < 2R).  The short-S advance
is ``h = 2R*sin(acos(1 - |delta|/(2R)))``; the vertical parameter ranges below keep
the path inside the board.  Every candidate is validated with the same
``geometry.validate`` used by the router; infeasible parameters return ``None``.
"""
from __future__ import annotations

import math

from ..fslw import config as F
from ..fslw import geom as G

R = F.RADIUS_MM
BOARD = F.BOARD_MM
TOL = 1e-6
START_DIR = (0.0, 1.0)
END_DIR = (0.0, -1.0)
SAME_FAMILIES = ('SAME_U', 'SAME_HAIRPIN_A', 'SAME_HAIRPIN_B')


def _validate(primitives, p, q):
    if primitives is None:
        return None
    ok, _errors = G.canonical_validate(primitives, p, q, START_DIR, END_DIR)
    return primitives if ok else None


def _line(p0, p1):
    if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) <= 1e-9:
        return None
    return G.line(p0, p1)


def _append(result, primitive):
    if primitive is not None:
        result.append(primitive)


def hairpin_plan(dx, sign, radius=None):
    """Return the short-S parameters for a hairpin of ``sign*2R`` or ``None``."""
    radius = R if radius is None else radius
    delta = dx - sign * 2 * radius
    if abs(delta) >= 2 * radius - TOL:
        return None
    theta = math.acos(1.0 - abs(delta) / (2 * radius))
    advance = 2 * radius * math.sin(theta)
    # ascent short-S: positive parameter moves along rot90(+y) = -x, so param = -delta
    # descent short-S (travel -y): positive parameter moves +x, so param = delta
    return dict(sign=sign, delta=delta, advance=advance,
                ascent_param=-delta, descent_param=delta)


def _hairpin(start, sign=1.0, radius=None):
    """180-degree turn from two consecutive quarter arcs (no straight between).

    Starts at ``start`` travelling +y, ends travelling -y at
    ``(start.x + sign*2R, start.y)``.  ``sign=+1`` bulges to +x, ``-1`` to -x.
    """
    radius = R if radius is None else radius
    x0, y0 = start
    if sign >= 0:
        center = (x0 + radius, y0)
        first = G.arc((x0, y0), (x0 + radius, y0 + radius), center, radius,
                      math.pi, -math.pi / 2)
        second = G.arc((x0 + radius, y0 + radius), (x0 + 2 * radius, y0), center,
                       radius, math.pi / 2, -math.pi / 2)
    else:
        center = (x0 - radius, y0)
        first = G.arc((x0, y0), (x0 - radius, y0 + radius), center, radius,
                      0.0, math.pi / 2)
        second = G.arc((x0 - radius, y0 + radius), (x0 - 2 * radius, y0), center,
                       radius, math.pi / 2, math.pi / 2)
    return [first, second], (x0 + sign * 2 * radius, y0)


def same_u(p, q, depth, radius=None):
    """Rectangle U with two quarter arcs at the top corners."""
    radius = R if radius is None else radius
    if depth < radius - TOL or depth > BOARD - radius + TOL:
        return None
    if abs(q[0] - p[0]) < 2 * radius - TOL:
        return None
    vertices = [p, (p[0], depth), (q[0], depth), q]
    return _validate(G.staircase(vertices, START_DIR, END_DIR, radius), p, q)


def same_hairpin_a(p, q, y0=0.0, sign=1.0, extra=0.0, radius=None):
    """Short-S first (ascent), optional straight, hairpin, then a straight descent."""
    radius = R if radius is None else radius
    dx = q[0] - p[0]
    plan = hairpin_plan(dx, sign, radius)
    if plan is None:
        return None
    extra = max(0.0, float(extra))
    if y0 < -TOL or y0 + plan['advance'] + extra > BOARD - radius + TOL:
        return None
    primitives = []
    _append(primitives, _line(p, (p[0], y0)))
    s_primitives, end, _ = G.short_s((p[0], y0), (0.0, 1.0), plan['ascent_param'])
    if s_primitives is None:
        return None
    primitives.extend(s_primitives)
    if extra > TOL:
        _append(primitives, _line(end, (end[0], end[1] + extra)))
        end = (end[0], end[1] + extra)
    hairpin, top = _hairpin(end, sign)
    primitives.extend(hairpin)
    if abs(top[0] - q[0]) > TOL:
        return None
    _append(primitives, _line(top, q))
    return _validate(primitives, p, q)


def same_hairpin_b(p, q, y0=None, sign=1.0, extra=0.0, radius=None):
    """Hairpin first, optional straight, short-S while descending, then straight down."""
    radius = R if radius is None else radius
    dx = q[0] - p[0]
    plan = hairpin_plan(dx, sign, radius)
    if plan is None:
        return None
    extra = max(0.0, float(extra))
    if y0 is None:
        y0 = max(plan['advance'] + extra, radius)
    if y0 < plan['advance'] + extra - TOL or y0 > BOARD - radius + TOL:
        return None
    primitives = []
    _append(primitives, _line(p, (p[0], y0)))
    hairpin, end = _hairpin((p[0], y0), sign)
    primitives.extend(hairpin)
    if extra > TOL:
        _append(primitives, _line(end, (end[0], end[1] - extra)))
        end = (end[0], end[1] - extra)
    if abs(plan['descent_param']) <= TOL:
        _append(primitives, _line(end, q))
    else:
        s_primitives, end2, _ = G.short_s(end, (0.0, -1.0), plan['descent_param'])
        if s_primitives is None:
            return None
        primitives.extend(s_primitives)
        if abs(end2[0] - q[0]) > TOL:
            return None
        _append(primitives, _line(end2, q))
    return _validate(primitives, p, q)


def same_u_depths(deep=False, radius=None):
    radius = R if radius is None else radius
    lo, hi = radius, BOARD - radius
    if deep:
        count = 71
    else:
        count = 33
    step = (hi - lo) / max(1, count - 1)
    return [lo + index * step for index in range(count)]


def family_options(p, q, deep=False):
    """Yield ``(family, params)`` options that are likely feasible (cheap pre-checks)."""
    dx = q[0] - p[0]
    if abs(dx) >= 2 * R - TOL:
        for depth in same_u_depths(deep):
            yield 'SAME_U', dict(depth_mm=float(depth))
    extras = _extra_options(deep)
    for sign in (1.0, -1.0):
        plan = hairpin_plan(dx, sign)
        if plan is None:
            continue
        advance = plan['advance']
        # ascent-first: start at a low y0, short-S rises `advance`, optional straight,
        # then the hairpin bulge R; total top height y0 + advance + extra + R <= 150.
        height_limit = BOARD - R
        for y0 in _y0_options(0.0, max(0.0, height_limit - advance), deep):
            for extra in extras:
                if y0 + advance + extra <= height_limit + TOL:
                    yield ('SAME_HAIRPIN_A',
                           dict(y0_mm=float(y0), sign=float(sign),
                                extra_mm=float(extra)))
        # hairpin-first: hairpin at y0, optional straight down, then the descent
        # short-S consumes `advance` and the final straight ends at the port.
        for y0 in _y0_options(advance, BOARD - R, deep):
            for extra in extras:
                if extra <= y0 - advance + TOL:
                    yield ('SAME_HAIRPIN_B',
                           dict(y0_mm=float(y0), sign=float(sign),
                                extra_mm=float(extra)))


def _extra_options(deep):
    if deep:
        return [0.0, 2.0, 5.0, 10.0, 16.0, 24.0, 34.0, 46.0]
    return [0.0, 5.0, 12.0, 22.0]


def _y0_options(low, high, deep):
    low = max(0.0, low)
    if high < low - TOL:
        return []
    if deep:
        count = 9
        return [low + (high - low) * index / max(1, count - 1) for index in range(count)]
    base = [low, low + 5.0, low + 15.0, (low + high) / 2.0, high]
    return [max(low, min(high, value)) for value in base]


def build_family(family, p, q, **params):
    if family == 'SAME_U':
        return same_u(p, q, params['depth_mm'])
    if family == 'SAME_HAIRPIN_A':
        return same_hairpin_a(p, q, params.get('y0_mm', 0.0), params.get('sign', 1.0),
                              params.get('extra_mm', 0.0))
    if family == 'SAME_HAIRPIN_B':
        return same_hairpin_b(p, q, params.get('y0_mm'), params.get('sign', 1.0),
                              params.get('extra_mm', 0.0))
    raise ValueError(f'unknown same-side family {family!r}')


def geometry_summary(primitives):
    rows = []
    for primitive in primitives or []:
        p0, p1 = primitive['p0'], primitive['p1']
        if primitive['kind'] == 'line':
            rows.append(['line', math.hypot(p1[0] - p0[0], p1[1] - p0[1])])
        else:
            rows.append([f"arc_r{primitive['radius']:.1f}",
                         abs(primitive['sweep']) * primitive['radius']])
    return rows
