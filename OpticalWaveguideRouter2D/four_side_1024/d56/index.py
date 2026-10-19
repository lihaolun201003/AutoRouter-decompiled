"""Fast exact single-layer conflict index for D56 orthogonal/arc geometry.

Acceptance policy (identical in spirit to ``four_side_1024.conflicts``)
---------------------------------------------------------------------
One clearance ``width + edge_gap = 0.175 mm`` for every route pair.  Only
genuine transverse crossings are exempt, and only inside their local crossing
neighbourhood: overlap, tangential touch, a double crossing of the same pair of
primitives, crossing-window overlap along either route, and any non-crossing
proximity below clearance are all rejected.  Radius (5 mm), waveguide width,
edge gap and the single-layer restriction are untouched.

Documented correction relative to the historical implementation
---------------------------------------------------------------
``conflicts.py`` sizes the crossing window with ``clearance / sin(angle)``.
That is exact for two straight lines but under-sizes the window when a circular
arc takes part, because the arc tangent keeps rotating while the curve moves
away from its partner.  Measured on CSV-native direct-L D56 paths: geometric
distance at the historical window boundary is 0.173936 mm, i.e. the historical
rule rejects a legal crossing by 1.06 um.  This index instead exempts exactly
the primitive pairs that cross transversally (and rejects every non-crossing
pair closer than clearance), which is the faithful implementation of "a
crossing exempts only the local crossing region".  ``LegacyCrossingIndex``
keeps the historical approximation for audit comparison only.

Implementation
--------------
* Broad phase: uniform hash of *primitives* (not routes; a U-shaped D56 route
  spans most of the board so route bounding boxes are useless).
* Narrow phase: axis-aligned line/line pairs use exact closed-form tests;
  arc-involving pairs use the analytic line/arc intersection and minimum
  distance mathematics from ``four_side_1024.conflicts``.
* Crossings are collected per route pair, de-duplicated at shared junctions,
  and must not create overlapping windows on either route.
"""
from __future__ import annotations

import math
import time

from ..conflicts import (_make_primitive, _intersections, _exact_distance,
                         _bbox_distance)

EPS = 1e-8
MIN_ANGLE_DEG_DEFAULT = 5.0


class Prepared:
    """Route primitives plus precomputed arc-length offsets/bounds."""

    __slots__ = ('prims', 'offsets', 'length', 'bounds', 'n_prims', 'kind_counts')

    def __init__(self, prims):
        self.prims = tuple(prims)
        offsets = []
        running = 0.0
        for p in self.prims:
            offsets.append(running)
            running += p.length
        self.offsets = tuple(offsets)
        self.length = running
        self.n_prims = len(self.prims)
        b = [p.bounds for p in self.prims]
        self.bounds = (min(v[0] for v in b), min(v[1] for v in b),
                       max(v[2] for v in b), max(v[3] for v in b))
        self.kind_counts = (sum(1 for p in self.prims if p.kind == 'line'),
                            sum(1 for p in self.prims if p.kind == 'arc'))

    @property
    def bend_count(self):
        return self.kind_counts[1]


def prepare(primitives):
    return Prepared([_make_primitive(p) for p in primitives])


class Evaluation:
    __slots__ = ('valid', 'reason', 'blockers', 'crossings', 'metrics',
                 'min_spacing_mm')

    def __init__(self):
        self.valid = False
        self.reason = None
        self.blockers = []
        self.crossings = []
        self.metrics = {}
        self.min_spacing_mm = None

    def as_dict(self):
        return dict(valid=self.valid, reason=self.reason,
                    blockers=list(self.blockers), crossings=len(self.crossings),
                    metrics=dict(self.metrics), min_spacing_mm=self.min_spacing_mm)


def _line_axis(prim):
    """Return ``('h', y, x0, x1)`` / ``('v', x, y0, y1)`` for axis-aligned lines."""
    p0 = prim.p0
    p1 = prim.p1
    if p0[1] == p1[1]:
        return 'h', p0[1], min(p0[0], p1[0]), max(p0[0], p1[0])
    if p0[0] == p1[0]:
        return 'v', p0[0], min(p0[1], p1[1]), max(p0[1], p1[1])
    return None


class D56Index:
    """Incremental exact conflict index shared by all 1024 single-layer routes."""

    def __init__(self, width=0.05, gap=0.125, sagitta=0.0005, cell=1.5,
                 min_cross_angle_deg=MIN_ANGLE_DEG_DEFAULT, check_outside=None,
                 crossing_policy='exact'):
        if width <= 0 or gap < 0 or sagitta <= 0 or cell <= 0:
            raise ValueError('invalid D56 index configuration')
        if crossing_policy not in ('legacy', 'exact'):
            raise ValueError('crossing_policy must be legacy or exact')
        self.width = float(width)
        self.gap = float(gap)
        self.sagitta = float(sagitta)
        self.clearance = self.width + self.gap
        self.cell = float(cell)
        self.min_sine = math.sin(math.radians(float(min_cross_angle_deg)))
        self.min_angle_deg = float(min_cross_angle_deg)
        self.crossing_policy = crossing_policy
        # With the historical policy the spacing outside the straight-line
        # crossing window has to be verified exactly whenever an arc takes part
        # in the crossing (the window is under-sized for curved primitives).
        self.check_outside = (crossing_policy == 'legacy') if check_outside is None \
            else bool(check_outside)
        self._limit = self.clearance - 1e-7
        self.routes = {}
        self._cells = {}
        self._route_cells = {}
        self.evaluations = 0
        self.index_seconds = 0.0
        self.exact_seconds = 0.0
        self.reasons = {}

    # ------------------------------------------------------------------ index
    def __len__(self):
        return len(self.routes)

    def ids(self):
        return list(self.routes)

    def bounds_of(self, route_id):
        return self.routes[route_id].bounds

    def length_of(self, route_id):
        return self.routes[route_id].length

    def add(self, route_id, prepared):
        if not isinstance(prepared, Prepared):
            prepared = prepare(prepared)
        self.remove(route_id)
        self.routes[route_id] = prepared
        cell = self.cell
        keys = []
        cells = self._cells
        for j, prim in enumerate(prepared.prims):
            x0, y0, x1, y1 = prim.bounds
            cx0 = int(math.floor(x0 / cell))
            cy0 = int(math.floor(y0 / cell))
            cx1 = int(math.floor(x1 / cell))
            cy1 = int(math.floor(y1 / cell))
            for cx in range(cx0, cx1 + 1):
                base = cx * 100000
                for cy in range(cy0, cy1 + 1):
                    key = base + cy
                    bucket = cells.get(key)
                    if bucket is None:
                        cells[key] = [(route_id, j)]
                    else:
                        bucket.append((route_id, j))
                    keys.append(key)
        self._route_cells[route_id] = keys

    def remove(self, route_id):
        prepared = self.routes.pop(route_id, None)
        if prepared is None:
            return None
        cells = self._cells
        for key in self._route_cells.pop(route_id, ()):
            bucket = cells.get(key)
            if bucket is None:
                continue
            if len(bucket) == 1:
                del cells[key]
            else:
                bucket[:] = [entry for entry in bucket if entry[0] != route_id]
                if not bucket:
                    del cells[key]
        return prepared

    def clear(self):
        self.routes.clear()
        self._cells.clear()
        self._route_cells.clear()

    # --------------------------------------------------------------- evaluate
    def _nearby_pairs(self, prepared):
        cell = self.cell
        cells = self._cells
        pad = self.clearance + self.sagitta
        seen = set()
        for i, prim in enumerate(prepared.prims):
            x0, y0, x1, y1 = prim.bounds
            cx0 = int(math.floor((x0 - pad) / cell))
            cy0 = int(math.floor((y0 - pad) / cell))
            cx1 = int(math.floor((x1 + pad) / cell))
            cy1 = int(math.floor((y1 + pad) / cell))
            for cx in range(cx0, cx1 + 1):
                base = cx * 100000
                for cy in range(cy0, cy1 + 1):
                    bucket = cells.get(base + cy)
                    if bucket is None:
                        continue
                    for rid, j in bucket:
                        key = i * 1000000 + rid * 128 + j
                        if key in seen:
                            continue
                        seen.add(key)
                        yield i, rid, j

    def evaluate(self, prepared, exclude=(), stop_on_invalid=True):
        if not isinstance(prepared, Prepared):
            prepared = prepare(prepared)
        self.evaluations += 1
        t0 = time.perf_counter()
        result = Evaluation()
        excluded = set(exclude) if exclude else set()
        routes = self.routes
        limit = self._limit
        min_sine = self.min_sine
        by_route = {}
        arc_routes = set()
        checked = set()
        for i, rid, j in self._nearby_pairs(prepared):
            if rid in excluded:
                continue
            other = routes[rid]
            prim = prepared.prims[i]
            theirs = other.prims[j]
            key = rid * 100000 + i * 128 + j
            if key in checked:
                continue
            checked.add(key)
            if _bbox_distance(prim.bounds, theirs.bounds) >= limit:
                continue
            # ---- fast path: two axis-aligned straight lines -----------------
            if prim.kind == 'line' and theirs.kind == 'line':
                a = _line_axis(prim)
                b = _line_axis(theirs)
                if a is not None and b is not None:
                    if a[0] == b[0]:
                        # parallel: perpendicular offset plus longitudinal gap
                        offset = a[1] - b[1]
                        gap = max(a[2] - b[3], b[2] - a[3], 0.0)
                        if abs(offset) < EPS and gap <= EPS:
                            result.reason = 'overlap'
                            result.blockers.append(rid)
                            if stop_on_invalid:
                                self.index_seconds += time.perf_counter() - t0
                                return result
                            continue
                        distance = math.hypot(offset, gap) if gap > 0 else abs(offset)
                        if distance < limit:
                            result.reason = 'spacing'
                            result.blockers.append(rid)
                            result.min_spacing_mm = distance if result.min_spacing_mm is None \
                                else min(result.min_spacing_mm, distance)
                            if stop_on_invalid:
                                self.index_seconds += time.perf_counter() - t0
                                return result
                        continue
                    # perpendicular
                    if a[0] == 'h':
                        hy, hx0, hx1 = a[1], a[2], a[3]
                        vx, vy0, vy1 = b[1], b[2], b[3]
                    else:
                        hy, hx0, hx1 = b[1], b[2], b[3]
                        vx, vy0, vy1 = a[1], a[2], a[3]
                    if hx0 - EPS <= vx <= hx1 + EPS and vy0 - EPS <= hy <= vy1 + EPS:
                        sa = _line_arclength(prepared, i, vx, hy)
                        sb = _line_arclength(other, j, vx, hy)
                        record = (sa, sb, 1.0, (vx, hy))
                        if min(sa, prepared.length - sa,
                               sb, other.length - sb) < 1e-7:
                            result.reason = 'endpoint_touch'
                            result.blockers.append(rid)
                            if stop_on_invalid:
                                self.index_seconds += time.perf_counter() - t0
                                return result
                            continue
                        by_route.setdefault(rid, []).append(record)
                        continue
                    # no crossing: exact distance between two segments
                    dx = max(hx0 - vx, vx - hx1, 0.0)
                    dy = max(vy0 - hy, hy - vy1, 0.0)
                    distance = math.hypot(dx, dy)
                    if distance < limit:
                        result.reason = 'spacing'
                        result.blockers.append(rid)
                        result.min_spacing_mm = distance if result.min_spacing_mm is None \
                            else min(result.min_spacing_mm, distance)
                        if stop_on_invalid:
                            self.index_seconds += time.perf_counter() - t0
                            return result
                    continue
            # ---- general analytic path -------------------------------------
            points, overlap = _intersections(prim, theirs)
            if overlap:
                result.reason = 'overlap'
                result.blockers.append(rid)
                if stop_on_invalid:
                    self.index_seconds += time.perf_counter() - t0
                    return result
                continue
            if not points:
                distance = _exact_distance(prim, theirs)
                if distance < limit:
                    result.reason = 'spacing'
                    result.blockers.append(rid)
                    result.min_spacing_mm = distance if result.min_spacing_mm is None \
                        else min(result.min_spacing_mm, distance)
                    if stop_on_invalid:
                        self.index_seconds += time.perf_counter() - t0
                        return result
                continue
            if len(points) > 1:
                result.reason = 'double_cross'
                result.blockers.append(rid)
                if stop_on_invalid:
                    self.index_seconds += time.perf_counter() - t0
                    return result
                continue
            point = points[0]
            ta = prim.parameter(point)
            tb = theirs.parameter(point)
            tangent_a = prim.tangent(ta)
            tangent_b = theirs.tangent(tb)
            sine = abs(tangent_a[0] * tangent_b[1] - tangent_a[1] * tangent_b[0])
            sine = min(1.0, sine)
            sa = prepared.offsets[i] + ta * prim.length
            sb = other.offsets[j] + tb * theirs.length
            if sine < min_sine:
                result.reason = 'tangent_touch'
                result.blockers.append(rid)
                if stop_on_invalid:
                    self.index_seconds += time.perf_counter() - t0
                    return result
                continue
            if min(sa, prepared.length - sa, sb, other.length - sb) < 1e-7:
                result.reason = 'endpoint_touch'
                result.blockers.append(rid)
                if stop_on_invalid:
                    self.index_seconds += time.perf_counter() - t0
                    return result
                continue
            if prim.kind == 'arc' or theirs.kind == 'arc':
                arc_routes.add(rid)
            by_route.setdefault(rid, []).append((sa, sb, sine, point))
        self.index_seconds += time.perf_counter() - t0
        # ---- per-route crossing windows -----------------------------------
        t1 = time.perf_counter()
        for rid, crossings in by_route.items():
            other = routes[rid]
            # De-duplicate crossings at shared primitive junctions.
            unique = []
            for record in crossings:
                point = record[3]
                if any(abs(point[0] - u[3][0]) < 1e-6 and abs(point[1] - u[3][1]) < 1e-6
                       for u in unique):
                    continue
                unique.append(record)
            a_intervals = []
            b_intervals = []
            for sa, sb, sine, point in unique:
                half = self.clearance / sine + 2 * self.sagitta
                a_intervals.append((sa - half, sa + half))
                b_intervals.append((sb - half, sb + half))
                result.crossings.append(dict(other=rid, x=point[0], y=point[1],
                                             angle_deg=math.degrees(math.asin(sine))))
            a_intervals.sort()
            for first, second in zip(a_intervals, a_intervals[1:]):
                if second[0] < first[1] - EPS:
                    result.reason = 'crossing_window_overlap'
                    result.blockers.append(rid)
                    if stop_on_invalid:
                        self.exact_seconds += time.perf_counter() - t1
                        return result
                    break
            # Historical policy: an arc-crossing window is under-sized, so the
            # spacing outside the window still has to be verified exactly.
            if self.check_outside and rid in arc_routes:
                distance = self._legacy_outside(prepared, other, a_intervals, b_intervals)
                if distance is not None:
                    result.reason = 'spacing'
                    result.blockers.append(rid)
                    result.min_spacing_mm = distance if result.min_spacing_mm is None \
                        else min(result.min_spacing_mm, distance)
                    if stop_on_invalid:
                        self.exact_seconds += time.perf_counter() - t1
                        return result
        self.exact_seconds += time.perf_counter() - t1
        result.valid = True
        result.metrics['crossings'] = len(result.crossings)
        return result

    def _legacy_outside(self, prepared, other, a_intervals, b_intervals):
        """Exact spacing outside the historical crossing windows, both routes."""
        limit = self._limit
        pieces_a = _clip(prepared, a_intervals)
        for piece, _owner in pieces_a:
            for theirs in other.prims:
                if _bbox_distance(piece.bounds, theirs.bounds) >= limit:
                    continue
                distance = _exact_distance(piece, theirs)
                if distance < limit:
                    return distance
        pieces_b = _clip(other, b_intervals)
        for piece, _owner in pieces_b:
            for prim in prepared.prims:
                if _bbox_distance(piece.bounds, prim.bounds) >= limit:
                    continue
                distance = _exact_distance(piece, prim)
                if distance < limit:
                    return distance
        return None


def _line_arclength(prepared, index, x, y):
    """Arc length of a point on an axis-aligned line primitive."""
    prim = prepared.prims[index]
    p0 = prim.p0
    p1 = prim.p1
    if p0[1] == p1[1]:
        along = abs(x - p0[0])
    else:
        along = abs(y - p0[1])
    return prepared.offsets[index] + along


class LegacyCrossingIndex(D56Index):
    """Audit-only variant using the historical straight-line crossing window."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy = 'legacy_straight_line_crossing_window'

    def evaluate(self, prepared, exclude=(), stop_on_invalid=True):
        if not isinstance(prepared, Prepared):
            prepared = prepare(prepared)
        return _legacy_evaluate(self, prepared, exclude, stop_on_invalid)


def _legacy_evaluate(index, prepared, exclude, stop_on_invalid):
    """Decision equivalent to ``conflicts.ConflictIndex.evaluate`` semantics."""
    result = Evaluation()
    excluded = set(exclude) if exclude else set()
    routes = index.routes
    limit = index._limit
    by_route = {}
    checked = set()
    for i, rid, j in index._nearby_pairs(prepared):
        if rid in excluded:
            continue
        other = routes[rid]
        prim = prepared.prims[i]
        theirs = other.prims[j]
        key = rid * 100000 + i * 128 + j
        if key in checked:
            continue
        checked.add(key)
        if _bbox_distance(prim.bounds, theirs.bounds) >= limit:
            continue
        points, overlap = _intersections(prim, theirs)
        if overlap:
            result.reason = 'overlap'
            result.blockers.append(rid)
            if stop_on_invalid:
                return result
            continue
        if not points:
            distance = _exact_distance(prim, theirs)
            if distance < limit:
                result.reason = 'spacing'
                result.blockers.append(rid)
                result.min_spacing_mm = distance if result.min_spacing_mm is None else \
                    min(result.min_spacing_mm, distance)
                if stop_on_invalid:
                    return result
            continue
        pending = []
        for point in points:
            ta = prim.parameter(point)
            tb = theirs.parameter(point)
            tangent_a = prim.tangent(ta)
            tangent_b = theirs.tangent(tb)
            sine = min(1.0, abs(tangent_a[0] * tangent_b[1] - tangent_a[1] * tangent_b[0]))
            sa = prepared.offsets[i] + ta * prim.length
            sb = other.offsets[j] + tb * theirs.length
            if sine < 1e-7 or min(sa, prepared.length - sa,
                                  sb, other.length - sb) < 1e-7:
                result.reason = 'touch'
                result.blockers.append(rid)
                if stop_on_invalid:
                    return result
                continue
            pending.append((sa, sb, sine, point))
        if pending:
            by_route.setdefault(rid, []).extend(pending)
    for rid, crossings in by_route.items():
        other = routes[rid]
        unique = []
        for record in crossings:
            point = record[3]
            if any(abs(point[0] - u[3][0]) < 1e-6 and abs(point[1] - u[3][1]) < 1e-6
                   for u in unique):
                continue
            unique.append(record)
        a_intervals = []
        b_intervals = []
        for sa, sb, sine, point in unique:
            half = index.clearance / sine + 2 * index.sagitta
            a_intervals.append((sa - half, sa + half))
            b_intervals.append((sb - half, sb + half))
            result.crossings.append(dict(other=rid, x=point[0], y=point[1],
                                         angle_deg=math.degrees(math.asin(sine))))
        a_intervals.sort()
        for first, second in zip(a_intervals, a_intervals[1:]):
            if second[0] < first[1] - EPS:
                result.reason = 'crossing_window_overlap'
                result.blockers.append(rid)
                if stop_on_invalid:
                    return result
        pieces_a = _clip(prepared, a_intervals)
        for piece, _owner in pieces_a:
            for theirs in other.prims:
                if _bbox_distance(piece.bounds, theirs.bounds) >= limit:
                    continue
                distance = _exact_distance(piece, theirs)
                if distance < limit:
                    result.reason = 'spacing'
                    result.blockers.append(rid)
                    result.min_spacing_mm = distance if result.min_spacing_mm is None \
                        else min(result.min_spacing_mm, distance)
                    if stop_on_invalid:
                        return result
        pieces_b = _clip(other, b_intervals)
        for piece, _owner in pieces_b:
            for prim in prepared.prims:
                if _bbox_distance(piece.bounds, prim.bounds) >= limit:
                    continue
                distance = _exact_distance(piece, prim)
                if distance < limit:
                    result.reason = 'spacing'
                    result.blockers.append(rid)
                    result.min_spacing_mm = distance if result.min_spacing_mm is None \
                        else min(result.min_spacing_mm, distance)
                    if stop_on_invalid:
                        return result
    result.valid = True
    return result


def _clip(prepared, intervals):
    if not intervals:
        return [(prim, index) for index, prim in enumerate(prepared.prims)]
    merged = []
    for lo, hi in sorted(intervals):
        lo = max(0.0, lo)
        hi = min(prepared.length, hi)
        if hi <= lo:
            continue
        if merged and lo <= merged[-1][1] + EPS:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    pieces = []
    for index, prim in enumerate(prepared.prims):
        start = prepared.offsets[index]
        end = start + prim.length
        cursor = start
        for lo, hi in merged:
            if hi <= cursor or lo >= end:
                continue
            if lo > cursor + EPS:
                pieces.append((_clip_primitive(prim, cursor, start, lo), index))
            cursor = max(cursor, hi)
            if cursor >= end - EPS:
                break
        if cursor < end - EPS:
            pieces.append((_clip_primitive(prim, cursor, start, end), index))
    return pieces


def _clip_primitive(prim, a, start, b):
    t0 = (a - start) / prim.length
    t1 = (b - start) / prim.length
    if t1 - t0 < 1e-9:
        return prim
    return prim.clip(t0, t1)
