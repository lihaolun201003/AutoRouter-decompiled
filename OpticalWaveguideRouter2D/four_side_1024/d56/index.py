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

from ..conflicts import (_make_primitive, _Primitive, _intersections, _exact_distance,
                         _bbox_distance, _point_distance)

EPS = 1e-8
TAU = 2.0 * math.pi
MIN_ANGLE_DEG_DEFAULT = 5.0
# Strict local-crossing-window policy (see four_side_1024/abcd/SPEC.md §2).
STRICT_MAX_HALF_WINDOW = 4.0
STRICT_EDGE_TOL = 1e-5
STRICT_SAMPLES = 4


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
                 crossing_policy='exact', max_half_window=STRICT_MAX_HALF_WINDOW):
        if width <= 0 or gap < 0 or sagitta <= 0 or cell <= 0:
            raise ValueError('invalid D56 index configuration')
        if crossing_policy not in ('legacy', 'exact', 'strict'):
            raise ValueError('crossing_policy must be legacy, exact or strict')
        self.width = float(width)
        self.gap = float(gap)
        self.sagitta = float(sagitta)
        self.clearance = self.width + self.gap
        self.cell = float(cell)
        self.min_sine = math.sin(math.radians(float(min_cross_angle_deg)))
        self.min_angle_deg = float(min_cross_angle_deg)
        self.crossing_policy = crossing_policy
        self.max_half_window = float(max_half_window)
        # With the historical policy the spacing outside the straight-line
        # crossing window has to be verified exactly whenever an arc takes part
        # in the crossing (the window is under-sized for curved primitives).
        self.check_outside = (crossing_policy == 'legacy') if check_outside is None \
            else bool(check_outside)
        self._limit = self.clearance - 1e-7
        self._window_margin = 2.0 * self.sagitta
        self.routes = {}
        self._cells = {}
        self._route_cells = {}
        self.evaluations = 0
        self.index_seconds = 0.0
        self.exact_seconds = 0.0
        self.reasons = {}
        self.window_count = 0
        self.window_total_mm = 0.0
        self.window_max_mm = 0.0

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
        if self.crossing_policy == 'strict':
            return self._evaluate_strict(prepared, exclude, stop_on_invalid)
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

    # ------------------------------------------------ strict crossing windows
    def _window_edge(self, prepared, s0, direction, partner, guess, target):
        """Arc length from ``s0`` to the first point outside the clearance band.

        The window is measured along the *whole route* (:class:`Prepared`), so a
        crossing that happens right at a D56 primitive junction may legally carry
        its local window across that junction.  ``None`` means the curve is still
        inside the band at ``max_half_window``: such a shallow "crossing" is not a
        genuine transverse crossing and is rejected as excessive.  When the route
        itself ends inside the band the window is clamped to the route end.
        """
        length = prepared.length
        room = s0 if direction < 0 else length - s0
        if room <= 1e-12:
            return 0.0
        cap = min(self.max_half_window, room)
        prims = prepared.prims
        offsets = prepared.offsets
        n_prims = prepared.n_prims

        def distance(h):
            s = s0 + direction * h
            if s <= 0.0:
                return _partner_point_distance(prims[0].point(0.0), partner)
            if s >= length:
                return _partner_point_distance(prims[-1].point(1.0), partner)
            lo, hi = 0, n_prims - 1
            while lo < hi:
                mid = (lo + hi + 1) >> 1
                if offsets[mid] <= s:
                    lo = mid
                else:
                    hi = mid - 1
            prim = prims[lo]
            t = (s - offsets[lo]) / prim.length
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            return _partner_point_distance(prim.point(t), partner)

        probe = min(cap, max(guess * 1.2, 2.0 * self.sagitta + 1e-6))
        lo = 0.0
        d_lo = -target
        hi = None
        d_hi = None
        # coarse bracket: three probes, then a growing probe if needed
        while True:
            third = probe / 3.0
            h = 0.0
            while h < probe - 1e-12:
                h = h + third
                if h > probe:
                    h = probe
                d = distance(h) - target
                if d >= 0.0:
                    hi = h
                    d_hi = d
                    break
                lo = h
                d_lo = d
            if hi is not None:
                break
            if probe >= cap - 1e-12:
                if room <= self.max_half_window + 1e-12:
                    return cap          # clamped at the route end
                return None             # never leaves the band within the cap
            probe = min(cap, probe * 1.8)
        stalled_at_hi = False
        stalled_at_lo = False
        for _ in range(32):
            if hi - lo <= STRICT_EDGE_TOL:
                break
            denominator = d_hi - d_lo
            if denominator <= 1e-15:
                mid = 0.5 * (lo + hi)
            else:
                mid = lo + (hi - lo) * (-d_lo) / denominator
                if not (lo + 1e-12 < mid < hi - 1e-12):
                    mid = 0.5 * (lo + hi)
            d = distance(mid) - target
            if d >= 0.0:
                hi = mid
                d_hi = d
                if stalled_at_hi:
                    d_lo *= 0.5
                stalled_at_hi = True
                stalled_at_lo = False
            else:
                lo = mid
                d_lo = d
                if stalled_at_lo:
                    d_hi *= 0.5
                stalled_at_lo = True
                stalled_at_hi = False
        return hi

    def _outside_vs_partners(self, prepared, other, windows):
        """Exact spacing outside the local windows, against each crossing partner.

        ``windows`` is a list of ``(lo, hi, partner_indices)`` in ``prepared``
        arc-length coordinates, one entry per distinct crossing point.  Every
        non-intersecting primitive pair has already been checked exactly by the
        main scan, so only the sub-intervals cut out of a *genuine crossing
        partner* need the outside-window check.
        """
        limit = self._limit
        offsets = prepared.offsets
        prims = prepared.prims
        by_partner = {}
        for lo, hi, partners in windows:
            if hi <= lo:
                continue
            for partner_j in partners:
                by_partner.setdefault(partner_j, []).append((lo, hi))
        for partner_j, intervals in by_partner.items():
            theirs = other.prims[partner_j]
            involved = set()
            for lo, hi in intervals:
                for idx in range(prepared.n_prims):
                    start = offsets[idx]
                    end = start + prims[idx].length
                    if hi > start and lo < end:
                        involved.add(idx)
            for idx in involved:
                prim = prims[idx]
                start = offsets[idx]
                end = start + prim.length
                local = []
                for lo, hi in intervals:
                    a = lo if lo > start else start
                    b = hi if hi < end else end
                    if b > a:
                        local.append((a - start, b - start))
                pieces = _clip_local(prim, local) if local else (prim,)
                for piece in pieces:
                    if _bbox_distance(piece.bounds, theirs.bounds) >= limit:
                        continue
                    distance = _exact_distance(piece, theirs)
                    if distance < limit:
                        return distance, (piece.p0 if piece.kind == 'line'
                                          else piece.point(0.5))
        return None

    def _evaluate_strict(self, prepared, exclude=(), stop_on_invalid=True):
        """Strict policy: only the exact minimal local crossing window is exempt."""
        if not isinstance(prepared, Prepared):
            prepared = prepare(prepared)
        self.evaluations += 1
        t0 = time.perf_counter()
        result = Evaluation()
        excluded = set(exclude) if exclude else set()
        routes = self.routes
        limit = self._limit
        min_sine = self.min_sine
        clearance = self.clearance
        margin = self._window_margin
        by_route = {}
        checked = set()

        def finish():
            return result

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
            if prim.kind == 'line' and theirs.kind == 'line':
                a = _line_axis(prim)
                b = _line_axis(theirs)
                if a is not None and b is not None:
                    if a[0] == b[0]:
                        offset = a[1] - b[1]
                        gap = max(a[2] - b[3], b[2] - a[3], 0.0)
                        if abs(offset) < EPS and gap <= EPS:
                            result.reason = 'overlap'
                            result.blockers.append(rid)
                            self.index_seconds += time.perf_counter() - t0
                            return finish()
                        distance = math.hypot(offset, gap) if gap > 0 else abs(offset)
                        if distance < limit:
                            result.reason = 'spacing'
                            result.blockers.append(rid)
                            result.min_spacing_mm = distance if result.min_spacing_mm is None \
                                else min(result.min_spacing_mm, distance)
                            self.index_seconds += time.perf_counter() - t0
                            return finish()
                        continue
                    if a[0] == 'h':
                        hy, hx0, hx1 = a[1], a[2], a[3]
                        vx, vy0, vy1 = b[1], b[2], b[3]
                    else:
                        hy, hx0, hx1 = b[1], b[2], b[3]
                        vx, vy0, vy1 = a[1], a[2], a[3]
                    if hx0 - EPS <= vx <= hx1 + EPS and vy0 - EPS <= hy <= vy1 + EPS:
                        sa = _line_arclength(prepared, i, vx, hy)
                        sb = _line_arclength(other, j, vx, hy)
                        if min(sa, prepared.length - sa,
                               sb, other.length - sb) < 1e-7:
                            result.reason = 'endpoint_touch'
                            result.blockers.append(rid)
                            self.index_seconds += time.perf_counter() - t0
                            return finish()
                        by_route.setdefault(rid, []).append(
                            dict(i=i, j=j, sa=sa, sb=sb, sine=1.0, point=(vx, hy),
                                 straight=True))
                        continue
                    dx = max(hx0 - vx, vx - hx1, 0.0)
                    dy = max(vy0 - hy, hy - vy1, 0.0)
                    distance = math.hypot(dx, dy)
                    if distance < limit:
                        result.reason = 'spacing'
                        result.blockers.append(rid)
                        result.min_spacing_mm = distance if result.min_spacing_mm is None \
                            else min(result.min_spacing_mm, distance)
                        self.index_seconds += time.perf_counter() - t0
                        return finish()
                    continue
            points, overlap = _intersections(prim, theirs)
            if overlap:
                result.reason = 'overlap'
                result.blockers.append(rid)
                self.index_seconds += time.perf_counter() - t0
                return finish()
            if not points:
                distance = _exact_distance(prim, theirs)
                if distance < limit:
                    result.reason = 'spacing'
                    result.blockers.append(rid)
                    result.min_spacing_mm = distance if result.min_spacing_mm is None \
                        else min(result.min_spacing_mm, distance)
                    self.index_seconds += time.perf_counter() - t0
                    return finish()
                continue
            if len(points) > 1:
                result.reason = 'double_cross'
                result.blockers.append(rid)
                self.index_seconds += time.perf_counter() - t0
                return finish()
            point = points[0]
            ta = prim.parameter(point)
            tb = theirs.parameter(point)
            tangent_a = prim.tangent(ta)
            tangent_b = theirs.tangent(tb)
            sine = min(1.0, abs(tangent_a[0] * tangent_b[1]
                                - tangent_a[1] * tangent_b[0]))
            sa = prepared.offsets[i] + ta * prim.length
            sb = other.offsets[j] + tb * theirs.length
            if sine < min_sine:
                result.reason = 'tangent_touch'
                result.blockers.append(rid)
                self.index_seconds += time.perf_counter() - t0
                return finish()
            if min(sa, prepared.length - sa, sb, other.length - sb) < 1e-7:
                result.reason = 'endpoint_touch'
                result.blockers.append(rid)
                self.index_seconds += time.perf_counter() - t0
                return finish()
            by_route.setdefault(rid, []).append(
                dict(i=i, j=j, sa=sa, sb=sb, sine=sine, point=point, straight=False))
        self.index_seconds += time.perf_counter() - t0
        t1 = time.perf_counter()
        for rid, records in by_route.items():
            other = routes[rid]
            groups = []
            for record in records:
                point = record['point']
                for group in groups:
                    reference = group[0]['point']
                    if abs(point[0] - reference[0]) < 1e-6 \
                            and abs(point[1] - reference[1]) < 1e-6:
                        group.append(record)
                        break
                else:
                    groups.append([record])
            windows_a = []
            windows_b = []
            for group in groups:
                sa = group[0]['sa']
                sb = group[0]['sb']
                ha_l = ha_r = hb_l = hb_r = None
                partners_a = set()
                partners_b = set()
                for record in group:
                    partners_a.add(record['j'])
                    partners_b.add(record['i'])
                    if record['straight']:
                        # two axis-aligned straight lines: window = clearance/sin
                        # is exact on both curves (sine == 1 for orthogonal lines)
                        half = clearance + margin
                        candidate = (half, half, half, half)
                    else:
                        partner_b = other.prims[record['j']]
                        partner_a = prepared.prims[record['i']]
                        guess = limit / max(record['sine'], 1e-3)
                        e_l = self._window_edge(prepared, record['sa'], -1.0,
                                                partner_b, guess, limit)
                        e_r = self._window_edge(prepared, record['sa'], 1.0,
                                                partner_b, guess, limit)
                        f_l = self._window_edge(other, record['sb'], -1.0,
                                                partner_a, guess, limit)
                        f_r = self._window_edge(other, record['sb'], 1.0,
                                                partner_a, guess, limit)
                        if e_l is None or e_r is None or f_l is None or f_r is None:
                            result.reason = 'crossing_window_excessive'
                            result.blockers.append(rid)
                            self.exact_seconds += time.perf_counter() - t1
                            return finish()
                        candidate = (e_l + margin, e_r + margin,
                                     f_l + margin, f_r + margin)
                    if ha_l is None or candidate[0] > ha_l:
                        ha_l = candidate[0]
                    if ha_r is None or candidate[1] > ha_r:
                        ha_r = candidate[1]
                    if hb_l is None or candidate[2] > hb_l:
                        hb_l = candidate[2]
                    if hb_r is None or candidate[3] > hb_r:
                        hb_r = candidate[3]
                windows_a.append((sa - ha_l, sa + ha_r, partners_a))
                windows_b.append((sb - hb_l, sb + hb_r, partners_b))
                self.window_count += 1
                self.window_total_mm += (ha_l + ha_r) + (hb_l + hb_r)
                self.window_max_mm = max(self.window_max_mm,
                                         ha_l, ha_r, hb_l, hb_r)
                result.crossings.append(dict(other=rid, x=group[0]['point'][0],
                                             y=group[0]['point'][1],
                                             angle_deg=math.degrees(
                                                 math.asin(group[0]['sine']))))
            overlap_triggered = False
            for windows in (windows_a, windows_b):
                intervals = sorted((lo, hi) for lo, hi, _partners in windows)
                for first, second in zip(intervals, intervals[1:]):
                    if second[0] < first[1] - EPS:
                        result.reason = 'crossing_window_overlap'
                        result.blockers.append(rid)
                        overlap_triggered = True
                        break
                if overlap_triggered:
                    break
            if overlap_triggered:
                self.exact_seconds += time.perf_counter() - t1
                return finish()
            if not all(record['straight'] for record in records):
                # Orthogonal straight-line crossings need no outside check: an
                # axis-aligned line pair can only cross perpendicularly, the
                # distance along one curve is exactly |s - s0| inside the partner
                # segment, so the local window clearance/sin = clearance is exact
                # and the whole outside region is at >= clearance by construction.
                bad = self._outside_vs_partners(prepared, other, windows_a)
                if bad is not None:
                    result.reason = 'spacing'
                    result.blockers.append(rid)
                    result.min_spacing_mm = bad[0]
                    self.exact_seconds += time.perf_counter() - t1
                    return finish()
                bad = self._outside_vs_partners(other, prepared, windows_b)
                if bad is not None:
                    result.reason = 'spacing'
                    result.blockers.append(rid)
                    result.min_spacing_mm = bad[0]
                    self.exact_seconds += time.perf_counter() - t1
                    return finish()
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


def _clip_local(prim, intervals):
    """Remove local arc-length intervals from one primitive (strict policy)."""
    if not intervals:
        return (prim,)
    length = prim.length
    merged = []
    for lo, hi in sorted(intervals):
        if lo < 0.0:
            lo = 0.0
        if hi > length:
            hi = length
        if hi <= lo:
            continue
        if merged and lo <= merged[-1][1] + 1e-12:
            if hi > merged[-1][1]:
                merged[-1] = (merged[-1][0], hi)
        else:
            merged.append((lo, hi))
    pieces = []
    cursor = 0.0
    for lo, hi in merged:
        if lo > cursor + 1e-12:
            pieces.append(_clip_fast(prim, cursor / length, lo / length))
        if hi > cursor:
            cursor = hi
        if cursor >= length - 1e-12:
            break
    if cursor < length - 1e-12:
        pieces.append(_clip_fast(prim, cursor / length, 1.0))
    return tuple(piece for piece in pieces if piece.length > 1e-12)


def _clip_fast(prim, t0, t1):
    """Fast sub-primitive without re-validating the whole D56 contract."""
    if t0 <= 0.0 and t1 >= 1.0:
        return prim
    if prim.kind == 'line':
        p0 = prim.point(t0)
        p1 = prim.point(t1)
        length = prim.length * (t1 - t0)
        return _Primitive('line', p0, p1,
                          length=length,
                          bounds=(min(p0[0], p1[0]), min(p0[1], p1[1]),
                                  max(p0[0], p1[0]), max(p0[1], p1[1])))
    start = prim.start + t0 * prim.sweep
    sweep = (t1 - t0) * prim.sweep
    p0 = prim.point(t0)
    p1 = prim.point(t1)
    points = [p0, p1]
    for angle in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
        if _arc_contains(angle, start, sweep):
            points.append((prim.center[0] + prim.radius * math.cos(angle),
                           prim.center[1] + prim.radius * math.sin(angle)))
    bounds = (min(pt[0] for pt in points), min(pt[1] for pt in points),
              max(pt[0] for pt in points), max(pt[1] for pt in points))
    return _Primitive('arc', p0, p1, prim.center, prim.radius, start, sweep,
                      abs(sweep) * prim.radius, bounds)


def _arc_contains(angle, start, sweep):
    delta = ((angle - start) if sweep > 0 else (start - angle)) % TAU
    return delta <= abs(sweep) + 1e-9 or TAU - delta < 1e-9


def _partner_point_distance(point, partner):
    """Point-to-primitive distance without the generic dispatch overhead."""
    px, py = point
    if partner.kind == 'line':
        ax, ay = partner.p0
        dx = partner.p1[0] - ax
        dy = partner.p1[1] - ay
        denominator = dx * dx + dy * dy
        t = ((px - ax) * dx + (py - ay) * dy) / denominator
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        qx = ax + t * dx - px
        qy = ay + t * dy - py
        return math.hypot(qx, qy)
    ex = px - partner.center[0]
    ey = py - partner.center[1]
    if _arc_contains(math.atan2(ey, ex), partner.start, partner.sweep):
        radial = math.hypot(ex, ey) - partner.radius
        return -radial if radial < 0.0 else radial
    d0 = math.hypot(px - partner.p0[0], py - partner.p0[1])
    d1 = math.hypot(px - partner.p1[0], py - partner.p1[1])
    return d0 if d0 < d1 else d1


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
