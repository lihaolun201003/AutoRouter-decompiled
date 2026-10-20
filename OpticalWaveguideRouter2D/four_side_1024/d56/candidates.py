"""D56 candidate families: orthogonal staircases with fixed R = 5 mm fillets.

Only three geometric primitives are ever produced, exactly as in the original
AutoRouter D56 model:

* horizontal / vertical straight segments;
* radius-5 mm quarter-circle corner arcs (``legacy_geometry._orthogonal_quarters``);
* the original small-displacement short-S pair of radius-5 mm arcs with
  ``theta = acos(1 - d/(2R))`` (``legacy_geometry.opposite``).

No Dubins curves, no slanted straight segments, no variable radius and no
Bezier/spline approximation exist anywhere in this module.

Families
--------
opposite (canonical S -> N, ``q`` travelling +y)
    ``straight``  dx == 0 : one vertical line
    ``U``         one free transfer track  (classic D56 U / short-S when dx<2R)
    ``Z``         two free transfer tracks + one free vertical jog (4 corners)
adjacent (canonical S -> E, ``q`` travelling +x)
    ``L``         the direct single-corner interface
    ``Z3``        free turn height + terminal riser x, 3 corners
"""
from __future__ import annotations

import math
import zlib
from bisect import bisect_left, bisect_right, insort

import numpy as np

from ..legacy_geometry import opposite as legacy_opposite, _orthogonal_quarters
from ..geometry import validate

R = 5.0
LANE = 0.175
BOARD = 150.0
EPS = 1e-9


# --------------------------------------------------------------------- oracle
class LineOracle:
    """Sorted per-primitive line occupancy used to rank candidates cheaply.

    Only straight segments are stored.  The exact crossing policy is always
    decided by the exact index; the oracle is a *ranking* aid only.
    """

    def __init__(self, clearance=0.175):
        self.clearance = float(clearance)
        self.h = []          # (y, x0, x1, rid)
        self.v = []          # (x, y0, y1, rid)
        self._tol = self.clearance - 1e-9

    def add(self, route_id, prepared):
        for prim in prepared.prims:
            if prim.kind != 'line':
                continue
            p0, p1 = prim.p0, prim.p1
            if p0[1] == p1[1]:
                insort(self.h, (p0[1], min(p0[0], p1[0]), max(p0[0], p1[0]), route_id))
            elif p0[0] == p1[0]:
                insort(self.v, (p0[0], min(p0[1], p1[1]), max(p0[1], p1[1]), route_id))

    def seed_static(self, h_values, v_values):
        """Register geometry that *every* route will add later, at worst case.

        Every route whose endpoint lies on the E/W edges will occupy a
        horizontal segment at that endpoint's along coordinate, and every
        route whose endpoint lies on N/S will occupy a vertical segment at its
        along coordinate.  Those coordinates are already fixed by the CSV.
        Seeding them with full-board extent makes candidate track generation
        conservative with respect to routes that are not placed yet, which is
        exactly the coupling that defeats a purely online greedy search.
        Entries use a negative route id and never count as parallel conflicts.
        """
        for y in h_values:
            insort(self.h, (float(y), 0.0, BOARD, -1))
        for x in v_values:
            insort(self.v, (float(x), 0.0, BOARD, -2))

    def remove(self, route_id):
        self.h = [e for e in self.h if e[3] != route_id]
        self.v = [e for e in self.v if e[3] != route_id]

    def h_parallel(self, y, x0, x1):
        tol = self._tol
        lo = bisect_left(self.h, (y - tol,))
        hi = bisect_right(self.h, (y + tol,))
        count = 0
        for entry in self.h[lo:hi]:
            if entry[3] < 0:
                continue
            if x0 - tol < entry[2] and entry[1] < x1 + tol:
                count += 1
        return count

    def v_parallel(self, x, y0, y1):
        tol = self._tol
        lo = bisect_left(self.v, (x - tol,))
        hi = bisect_right(self.v, (x + tol,))
        count = 0
        for entry in self.v[lo:hi]:
            if entry[3] < 0:
                continue
            if y0 - tol < entry[2] and entry[1] < y1 + tol:
                count += 1
        return count

    def h_crossings(self, y, x0, x1):
        """Number of accepted vertical segments crossing the horizontal span.

        Ranking aid only (used by the ``v2opt`` expanded candidate queue); it
        never takes part in any acceptance decision.
        """
        tol = self._tol
        lo = bisect_left(self.v, (x0 - tol,))
        hi = bisect_right(self.v, (x1 + tol,))
        count = 0
        for entry in self.v[lo:hi]:
            if entry[3] < 0:
                continue
            if entry[1] - tol < y < entry[2] + tol:
                count += 1
        return count

    def v_crossings(self, x, y0, y1):
        """Number of accepted horizontal segments crossing the vertical span.

        Ranking aid only; no acceptance decision depends on it.
        """
        tol = self._tol
        lo = bisect_left(self.h, (y0 - tol,))
        hi = bisect_right(self.h, (y1 + tol,))
        count = 0
        for entry in self.h[lo:hi]:
            if entry[3] < 0:
                continue
            if entry[1] - tol < x < entry[2] + tol:
                count += 1
        return count

    def h_obstacle_ys(self, x0, x1):
        """y coordinates of horizontal segments that interact with x-span."""
        tol = self._tol
        return [e[0] for e in self.h if x0 - tol < e[2] and e[1] < x1 + tol]

    def v_obstacle_xs(self, y0, y1):
        tol = self._tol
        return [e[0] for e in self.v if y0 - tol < e[2] and e[1] < y1 + tol]

    def h_free_lanes(self, y_lo, y_hi, x0, x1):
        k0 = max(0, int(math.ceil((y_lo - 1e-9) / LANE)))
        k1 = max(0, int(math.floor((y_hi + 1e-9) / LANE)))
        for k in range(k0, k1 + 1):
            y = k * LANE
            yield self.h_parallel(y, x0, x1), y


class FrameOracleSet:
    """Six canonical occupancy views of every accepted route.

    The six directed side pairs used by this CSV each have their own rigid
    frame, so a world-space occupancy list cannot serve candidate generation
    (which happens in canonical coordinates).  This keeps one
    :class:`LineOracle` per frame, in that frame's canonical coordinates, and
    is updated whenever a route is added or removed.
    """

    def __init__(self, frames, static_h, static_v, clearance=0.175):
        self.clearance = clearance
        keys = sorted({(f.source_side, f.target_side) for f in frames.values()})
        self.keys = keys
        self.transforms = {}
        self.oracles = {}
        reference = {}
        for frame in frames.values():
            reference.setdefault((frame.source_side, frame.target_side), frame)
        for key in keys:
            frame = reference[key]
            self.transforms[key] = (tuple(map(tuple, frame.matrix)),
                                    tuple(frame.offset))
            oracle = LineOracle(clearance)
            self.oracles[key] = oracle
            self._seed(oracle, key, static_h, static_v)

    # -- coordinate mapping -------------------------------------------------
    def _map(self, key, x, y):
        (m, o) = self.transforms[key]
        return (m[0][0] * x + m[0][1] * y + o[0],
                m[1][0] * x + m[1][1] * y + o[1])

    def _add_line(self, oracle, key, p0, p1):
        a = self._map(key, p0[0], p0[1])
        b = self._map(key, p1[0], p1[1])
        if abs(a[1] - b[1]) < 1e-9:
            insort(oracle.h, (a[1], min(a[0], b[0]), max(a[0], b[0]), -3))
        elif abs(a[0] - b[0]) < 1e-9:
            insort(oracle.v, (a[0], min(a[1], b[1]), max(a[1], b[1]), -3))

    def _seed(self, oracle, key, static_h, static_v):
        for y in static_h:
            self._add_line(oracle, key, (0.0, y), (BOARD, y))
        for x in static_v:
            self._add_line(oracle, key, (x, 0.0), (x, BOARD))

    # -- maintenance --------------------------------------------------------
    def add(self, route_id, prepared):
        for key in self.keys:
            oracle = self.oracles[key]
            for prim in prepared.prims:
                if prim.kind != 'line':
                    continue
                self._map_line_for_route(oracle, key, route_id, prim)

    def _map_line_for_route(self, oracle, key, route_id, prim):
        (m, o) = self.transforms[key]
        p0, p1 = prim.p0, prim.p1
        ax = m[0][0] * p0[0] + m[0][1] * p0[1] + o[0]
        ay = m[1][0] * p0[0] + m[1][1] * p0[1] + o[1]
        bx = m[0][0] * p1[0] + m[0][1] * p1[1] + o[0]
        by = m[1][0] * p1[0] + m[1][1] * p1[1] + o[1]
        if abs(ay - by) < 1e-9:
            insort(oracle.h, (ay, min(ax, bx), max(ax, bx), route_id))
        elif abs(ax - bx) < 1e-9:
            insort(oracle.v, (ax, min(ay, by), max(ay, by), route_id))

    def remove(self, route_id):
        for oracle in self.oracles.values():
            oracle.remove(route_id)

    def oracle_for(self, frame):
        return self.oracles[(frame.source_side, frame.target_side)]


def clearance_tracks(obstacles, lo, hi, clearance=0.175, margin=0.0006):
    """Lane coordinates packed exactly against obstacle clearance bands.

    Returns candidate coordinates at ``clearance + margin`` from every obstacle
    band, spaced by ``clearance`` inside the free gaps.  This keeps the D56
    clearance exactly (never below) while allowing the dense 0.175 mm packing
    the CSV was designed for.
    """
    values = sorted({round(v, 9) for v in obstacles})
    bands = []
    reach = clearance + margin
    for value in values:
        a, b = value - reach, value + reach
        if bands and a <= bands[-1][1]:
            bands[-1] = (bands[-1][0], max(b, bands[-1][1]))
        else:
            bands.append((a, b))
    free = []
    cursor = lo
    for a, b in bands:
        if a > cursor:
            free.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < hi:
        free.append((cursor, hi))
    tracks = []
    for f0, f1 in free:
        if f1 - f0 < -1e-9:
            continue
        start = f0 + margin
        k = 0
        while True:
            value = start + k * clearance
            if value > f1 - margin + 1e-9:
                break
            if lo - 1e-9 <= value <= hi + 1e-9:
                tracks.append(value)
            k += 1
            if k > 4000:
                break
    return tracks


def _preference_noise(route_id, value, modulo=1000):
    return (zlib.crc32(f'{route_id}:{value:.6f}'.encode()) % modulo) / modulo


# ------------------------------------------------------------ path builders
def _build_staircase(vertices, start_dir=(0.0, 1.0), end_dir=(0.0, 1.0)):
    """Canonical D56 orthogonal staircase -> primitives, or ``None``.

    Validation (endpoints, tangent directions, radius >= 5, board bounds,
    self-intersection) is performed in canonical coordinates; the rigid frame
    transform preserves every distance and maps the board square onto itself.
    """
    try:
        primitives = _orthogonal_quarters([np.asarray(v, dtype=float) for v in vertices], R)
    except (ValueError, IndexError, ZeroDivisionError):
        return None
    p = primitives[0]['p0']
    q = primitives[-1]['p1']
    errors = validate(primitives, p, q, start_dir, end_dir,
                      board=BOARD, width=0.05, min_radius=R)
    if errors:
        return None
    return primitives


def _build_opposite_U(frame, track):
    try:
        return legacy_opposite(np.asarray(frame.p), np.asarray(frame.q),
                               float(track), radius=R, width=0.05)
    except ValueError:
        return None


def _sample(values, count):
    if len(values) <= count:
        return list(values)
    step = (len(values) - 1) / (count - 1)
    return [values[int(round(i * step))] for i in range(count)]


# --------------------------------------------------------------- generators
def opposite_candidates(frame, oracle, cfg, deep=False):
    """Yield ranked opposite-side D56 candidates (canonical primitives)."""
    p, q = frame.p, frame.q
    sx, tx = p[0], q[0]
    adx = abs(tx - sx)
    x_lo, x_hi = (sx, tx) if sx <= tx else (tx, sx)
    if adx < 1e-9:
        prim = _build_staircase([p, q])
        if prim is not None:
            yield dict(family='straight', params={}, primitives=prim)
        return
    if adx < 2 * R:
        theta = math.acos(max(-1.0, min(1.0, 1.0 - adx / (2 * R))))
        h = R * math.sin(theta)
        lo, hi = h, BOARD - h
    else:
        lo, hi = R, BOARD - R
    obstacles = oracle.h_obstacle_ys(x_lo, x_hi)
    tracks = clearance_tracks(obstacles, lo, hi)
    route_id = frame.route_id
    tracks.sort(key=lambda y: _preference_noise(route_id, y))
    u_limit = cfg.get('u_candidates_deep' if deep else 'u_candidates_shallow',
                      140 if deep else 18)
    for track in tracks[:u_limit]:
        prim = _build_opposite_U(frame, track)
        if prim is not None:
            yield dict(family='U', params=dict(track_mm=track), primitives=prim)
    if not deep:
        return
    if len(tracks) > u_limit:
        for track in tracks[u_limit:]:
            prim = _build_opposite_U(frame, track)
            if prim is not None:
                yield dict(family='U', params=dict(track_mm=track), primitives=prim)
    # ---- Z family: two transfer tracks and one vertical jog --------------
    mid = 0.5 * (sx + tx)
    x_options = []
    for frac in (0.5, 0.3, 0.7, 0.15, 0.85):
        x = sx + frac * (tx - sx)
        if R + 1e-9 < x < BOARD - R - 1e-9:
            x_options.append(x)
    if not x_options:
        return
    sample = _sample(tracks, cfg.get('z_track_samples', 9))
    z_specs = []
    for i, y1 in enumerate(sample):
        for y2 in sample[i + 1:]:
            if abs(y2 - y1) < 2 * R - 1e-9:
                continue
            for xm in x_options:
                if abs(xm - sx) < 2 * R - 1e-9 or abs(tx - xm) < 2 * R - 1e-9:
                    continue
                score = (oracle.h_parallel(y1, x_lo, x_hi) +
                         oracle.h_parallel(y2, x_lo, x_hi) +
                         oracle.v_parallel(xm, min(y1, y2), max(y1, y2)))
                z_specs.append((score, y1, xm, y2))
    z_specs.sort(key=lambda item: item[0])
    for _score, y1, xm, y2 in z_specs[:cfg.get('z_candidates', 40)]:
        vertices = [p, (sx, y1), (xm, y1), (xm, y2), (tx, y2), q]
        prim = _build_staircase(vertices)
        if prim is not None:
            yield dict(family='Z', params=dict(y1_mm=y1, x_mid_mm=xm, y2_mm=y2),
                       primitives=prim)


def _adjacent_specs(frame, oracle, cfg, deep):
    sx = frame.p[0]
    qy = frame.qy
    obstacles_y = oracle.h_obstacle_ys(0.0, BOARD)
    obstacles_x = oracle.v_obstacle_xs(0.0, BOARD)
    y_pool = clearance_tracks(obstacles_y, R, BOARD - R)
    x_pool = clearance_tracks(obstacles_x, R, BOARD - R)
    if not y_pool or not x_pool:
        return []
    y_limits = cfg.get('z3_y_options_deep' if deep else 'z3_y_options', 30 if deep else 11)
    x_limits = cfg.get('z3_x_options_deep' if deep else 'z3_x_options', 30 if deep else 11)
    y_sample = _sample(y_pool, y_limits)
    x_sample = _sample(x_pool, x_limits)
    extra_y = []
    for delta in (2 * R, 2 * R + 1.75, 2 * R + 8.0, 2 * R + 21.0, 2 * R + 48.0):
        for sign in (-1, 1):
            y = qy + sign * delta
            if R + 1e-9 < y < BOARD - R - 1e-9:
                extra_y.append(y)
    y_sample = list(y_sample) + extra_y
    extra_x = [sx + 2 * R + k for k in (0.0, 2.0, 7.0, 17.0, 33.0, 60.0)]
    extra_x += [BOARD - R, BOARD - R - 2.0, BOARD - R - 9.0]
    x_sample = list(x_sample) + [x for x in extra_x
                                 if R - 1e-9 < x < BOARD - R + 1e-9]
    specs = []
    for y1 in y_sample:
        if abs(y1 - qy) < 2 * R - 1e-9:
            continue
        for x1 in x_sample:
            if abs(x1 - sx) < 2 * R - 1e-9:
                continue
            specs.append((y1, x1))
    return specs


def adjacent_candidates(frame, oracle, cfg, deep=False):
    """Yield ranked adjacent-side D56 candidates (canonical primitives)."""
    p, q = frame.p, frame.q
    sx = p[0]
    qy = frame.qy
    prim = _build_staircase([p, (sx, qy), q], start_dir=(0.0, 1.0), end_dir=(1.0, 0.0))
    if prim is not None:
        yield dict(family='L', params={}, primitives=prim)
    specs = _adjacent_specs(frame, oracle, cfg, deep)
    scored = []
    for y1, x1 in specs:
        score = (oracle.v_parallel(sx, 0.0, y1)
                 + oracle.h_parallel(y1, min(sx, x1), max(sx, x1))
                 + oracle.v_parallel(x1, min(y1, qy), max(y1, qy))
                 + 0.5 * oracle.h_parallel(qy, x1, BOARD))
        scored.append((score, y1, x1))
    scored.sort(key=lambda item: item[0])
    limit = cfg.get('z3_candidates_deep' if deep else 'z3_candidates', 60 if deep else 34)
    for _score, y1, x1 in scored[:limit]:
        vertices = [p, (sx, y1), (x1, y1), (x1, qy), q]
        prim = _build_staircase(vertices, start_dir=(0.0, 1.0), end_dir=(1.0, 0.0))
        if prim is not None:
            yield dict(family='Z3', params=dict(y1_mm=y1, x1_mm=x1), primitives=prim)


def candidates(frame, oracle, cfg, deep=False):
    if frame.kind == 'opposite':
        yield from opposite_candidates(frame, oracle, cfg, deep=deep)
    elif frame.kind == 'adjacent':
        yield from adjacent_candidates(frame, oracle, cfg, deep=deep)
    else:
        raise ValueError('unknown canonical kind: ' + frame.kind)
