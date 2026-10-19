"""Crossing-zone policy variants used by the Q8 diagnosis (no physics changed).

The deployed ``four_side_1024/conflicts.py`` excises, around every transversal
crossing, a fixed arclength window ``half = clearance/sin(angle) + 2*sagitta`` on
both curves and then requires >= clearance everywhere outside the windows.  That
formula is exact only for straight-line crossings: an arc turns away from the
other curve more slowly than its tangent line, so the true window in which the
two centerlines are closer than clearance is *longer* on the arc.  The deployed
rule therefore flags a small clearance deficit just outside a curved crossing
window - a numerical artifact of the excision formula, not a real spacing
violation.

This module implements two diagnostic policies, both keeping R=5, width=0.05,
clearance=0.175 and the same overlap/touch/endpoint/multiple-crossing rules:

* ``policy_primitive_pair`` (Lead's upper-bound policy): a primitive pair that
  contains exactly one transversal crossing is exempted as a whole; all other
  primitive pairs must satisfy the full clearance rule.  Multiple crossings
  inside one primitive pair, touches, overlaps and route-endpoint hits are
  rejected.
* ``policy_exact_window`` (defensible policy): for each crossing the exemption
  window is computed from the actual curve geometry (bisection on the true
  point-to-primitive distance until clearance is reached), then the deployed
  outside-window audit is applied.  Overlapping windows / multiple crossings in
  the same primitive pair are rejected as in the deployed rule.

Nothing here relaxes the physical limits: only the arclength over which a
crossing is legitimately excused is computed differently.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from four_side_1024.conflicts import (
    EPS, TAU, _bbox_distance, _exact_distance, _intersections, _kept_primitives,
    _make_primitive, _pieces_too_close, _point_distance, PreparedRoute,
)

CLEARANCE_DEFAULT = 0.175
SAGITTA_DEFAULT = 0.0005
# Float tolerance for "distance has reached the required clearance".  The CSV
# design places many parallel lanes at *exactly* 0.175 mm, so a strict `<`
# comparison would treat a mathematically legal knife-edge configuration as a
# violation because of 1e-14 roundoff.  The deployed checker uses required-EPS
# (1e-8); the excursion bisection uses the same tolerance.
CLEARANCE_TOL = 1e-7


def prepare(primitives):
    if isinstance(primitives, PreparedRoute):
        return primitives
    ps = tuple(_make_primitive(p) for p in primitives)
    coords, offsets, offset = [], [], 0.
    discontinuities = 0
    for i, p in enumerate(ps):
        offsets.append(offset)
        offset += p.length
        if i and abs(ps[i - 1].p1[0] - p.p0[0]) + abs(ps[i - 1].p1[1] - p.p0[1]) > 1e-6:
            discontinuities += 1
        if p.kind == 'line':
            points = [p.p0, p.p1]
        else:
            step = 2 * math.acos(max(-1., min(1., 1 - SAGITTA_DEFAULT / p.radius)))
            count = max(1, math.ceil(abs(p.sweep) / step))
            points = [p.point(j / count) for j in range(count + 1)]
        coords.extend(points if not coords else points[1:])
    bounds = (min(p.bounds[0] for p in ps), min(p.bounds[1] for p in ps),
              max(p.bounds[2] for p in ps), max(p.bounds[3] for p in ps))
    return PreparedRoute(ps, tuple(offsets), None, offset, SAGITTA_DEFAULT, bounds,
                         discontinuities=discontinuities)


def collect_crossings(route_a, route_b):
    """Every route-route crossing with primitive indices and local angle."""
    crossings = []
    overlaps = []
    for i, a in enumerate(route_a.primitives):
        for j, b in enumerate(route_b.primitives):
            points, overlap = _intersections(a, b)
            if overlap:
                overlaps.append((i, j))
            for pt in points:
                ta = a.parameter(pt)
                tb = b.parameter(pt)
                tangent_a = a.tangent(ta)
                tangent_b = b.tangent(tb)
                sine = min(1., abs(tangent_a[0] * tangent_b[1] - tangent_a[1] * tangent_b[0]))
                sa = route_a.offsets[i] + ta * a.length
                sb = route_b.offsets[j] + tb * b.length
                is_endpoint = min(sa, route_a.length - sa, sb, route_b.length - sb) < 1e-7
                crossings.append(dict(i=i, j=j, point=pt, sa=sa, sb=sb, sine=sine,
                                      ta=ta, tb=tb, endpoint=is_endpoint))
    return crossings, overlaps


def _analyse_rejections(route_a, route_b, crossings, overlaps, clearance):
    """Common reject rules: overlap, touch, multiple crossings per primitive pair."""
    if overlaps:
        return dict(valid=False, reason='overlap', detail=overlaps)
    for c in crossings:
        if c['sine'] < 1e-7 or c['endpoint']:
            return dict(valid=False, reason='touch',
                        detail=dict(primitive_pair=(c['i'], c['j']), sine=c['sine'],
                                    endpoint=c['endpoint'], point=c['point']))
    per_primitive_pair = {}
    for c in crossings:
        per_primitive_pair.setdefault((c['i'], c['j']), []).append(c)
    for key, items in per_primitive_pair.items():
        if len(items) > 1:
            return dict(valid=False, reason='multiple_crossings_same_primitives',
                        detail=dict(primitive_pair=key, count=len(items),
                                    angles=[math.degrees(math.asin(min(1., x['sine']))) for x in items]))
    return None


def pair_check_deployed(route_a, route_b, clearance=CLEARANCE_DEFAULT):
    """Re-implementation of the deployed per-pair audit (conflicts.ConflictIndex
    semantics) on prepared routes, for fast pairwise matrices."""
    crossings, overlaps = collect_crossings(route_a, route_b)
    reject = _analyse_rejections(route_a, route_b, crossings, overlaps, clearance)
    if reject:
        return reject
    ia, ib = [], []
    for c in crossings:
        half = clearance / c['sine'] + 2 * SAGITTA_DEFAULT
        ia.append((c['sa'] - half, c['sa'] + half))
        ib.append((c['sb'] - half, c['sb'] + half))
    for intervals in (ia, ib):
        ordered = sorted(intervals)
        if any(x[1] > y[0] + EPS for x, y in zip(ordered, ordered[1:])):
            return dict(valid=False, reason='crossing_zone_overlap', detail=None)
    outside_a = _kept_primitives(route_a, ia)
    outside_b = _kept_primitives(route_b, ib)
    bad, distance = _pieces_too_close(outside_a, route_b.primitives, clearance)
    if not bad and crossings:
        bad, distance = _pieces_too_close(outside_b, route_a.primitives, clearance)
    if bad:
        return dict(valid=False, reason='spacing', distance=distance, crossings=len(crossings),
                    angles=[math.degrees(math.asin(min(1., c['sine']))) for c in crossings])
    return dict(valid=True, reason=None, crossings=len(crossings),
                angles=[math.degrees(math.asin(min(1., c['sine']))) for c in crossings],
                min_distance=None)


def pair_check_primitive_pair(route_a, route_b, clearance=CLEARANCE_DEFAULT):
    """Lead's upper-bound policy: whole primitive-pair exemption for a single
    transversal crossing; exact clearance everywhere else."""
    crossings, overlaps = collect_crossings(route_a, route_b)
    reject = _analyse_rejections(route_a, route_b, crossings, overlaps, clearance)
    if reject:
        return reject
    exempt = {(c['i'], c['j']) for c in crossings}
    min_distance = None
    for i, a in enumerate(route_a.primitives):
        for j, b in enumerate(route_b.primitives):
            if (i, j) in exempt:
                continue
            if _bbox_distance(a.bounds, b.bounds) >= clearance - EPS:
                continue
            distance = _exact_distance(a, b)
            if min_distance is None or distance < min_distance:
                min_distance = distance
            if distance < clearance - EPS:
                return dict(valid=False, reason='spacing_no_crossing', distance=distance,
                            crossings=len(crossings), primitive_pair=(i, j),
                            kinds=(a.kind, b.kind),
                            angles=[math.degrees(math.asin(min(1., c['sine']))) for c in crossings])
    return dict(valid=True, reason=None, crossings=len(crossings),
                angles=[math.degrees(math.asin(min(1., c['sine']))) for c in crossings],
                min_distance=min_distance)


def _route_point(route, s):
    """Point at arclength ``s`` on a PreparedRoute (clamped)."""
    s = max(0., min(route.length, s))
    for primitive, offset in zip(route.primitives, route.offsets):
        if s <= offset + primitive.length + 1e-12:
            t = (s - offset) / primitive.length
            return primitive.point(min(1., max(0., t)))
    return route.primitives[-1].point(1.)


def _excursion_route(route, s_cross, partner_primitive, clearance, max_h=10.0):
    """Arclength on the whole route from a crossing until the true distance to
    the crossing partner primitive reaches ``clearance``.

    Returns ``(left, right)`` or ``None`` when clearance is not reached within
    ``max_h`` (tangential / very tight crossing).
    """
    def distance_at(h, direction):
        point = _route_point(route, s_cross + direction * h)
        return _point_distance(point, partner_primitive)

    def bisect(direction):
        available = min(max_h, (s_cross if direction < 0 else route.length - s_cross))
        if available <= 1e-12:
            return None
        target = clearance - CLEARANCE_TOL
        if distance_at(available, direction) < target:
            return None
        lo, hi = 0., available
        for _ in range(60):
            mid = (lo + hi) / 2
            if distance_at(mid, direction) < target:
                lo = mid
            else:
                hi = mid
        return hi

    left = bisect(-1.)
    right = bisect(+1.)
    if left is None or right is None:
        return None
    return left, right


def pair_check_exact_window(route_a, route_b, clearance=CLEARANCE_DEFAULT):
    """Exact-window policy: per crossing, the exemption interval is the true
    arclength in which either curve is closer than clearance to the crossing
    partner primitive; the deployed outside-window audit is then applied."""
    crossings, overlaps = collect_crossings(route_a, route_b)
    reject = _analyse_rejections(route_a, route_b, crossings, overlaps, clearance)
    if reject:
        return reject
    ia, ib = [], []
    exact_windows = []
    for c in crossings:
        partner_b = route_b.primitives[c['j']]
        partner_a = route_a.primitives[c['i']]
        wa = _excursion_route(route_a, c['sa'], partner_b, clearance)
        wb = _excursion_route(route_b, c['sb'], partner_a, clearance)
        if wa is None or wb is None:
            return dict(valid=False, reason='tangential_or_tight_crossing',
                        crossings=len(crossings))
        half_a = max(wa) + 2 * SAGITTA_DEFAULT
        half_b = max(wb) + 2 * SAGITTA_DEFAULT
        ia.append((c['sa'] - half_a, c['sa'] + half_a))
        ib.append((c['sb'] - half_b, c['sb'] + half_b))
        exact_windows.append(dict(half_a=half_a, half_b=half_b))
    for intervals in (ia, ib):
        ordered = sorted(intervals)
        if any(x[1] > y[0] + EPS for x, y in zip(ordered, ordered[1:])):
            return dict(valid=False, reason='window_overlap_after_correction', detail=None)
    outside_a = _kept_primitives(route_a, ia)
    outside_b = _kept_primitives(route_b, ib)
    bad, distance = _pieces_too_close(outside_a, route_b.primitives, clearance)
    if not bad and crossings:
        bad, distance = _pieces_too_close(outside_b, route_a.primitives, clearance)
    if bad:
        return dict(valid=False, reason='spacing_outside_exact_window', distance=distance,
                    crossings=len(crossings))
    return dict(valid=True, reason=None, crossings=len(crossings),
                windows=[round(max(w['half_a'], w['half_b']), 6) for w in exact_windows],
                min_distance=None)


POLICIES = dict(deployed=pair_check_deployed,
                primitive_pair=pair_check_primitive_pair,
                exact_window=pair_check_exact_window)
