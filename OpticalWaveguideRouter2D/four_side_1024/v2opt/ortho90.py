"""Pure orthogonal 90-degree D56 variant: straight lines + exact R=40 quarter arcs only.

Experiment scope (V2 ortho90 round)
------------------------------------
The only geometric change relative to the frozen D56 model is that **every arc must
be exactly a 90-degree quarter circle of radius 40 mm** and **no short-S pair with
theta < 90 degrees is allowed**.  Straight primitives remain axis aligned.  Multiple
quarter arcs and orthogonal lines may form U / Z / multi-bend routes.

Candidate sources
-----------------
* adjacent frames: frozen staircase families (L / Z3 / LEFT / Z5) and the DOWN_LOOP
  family restricted to zero short-S shift, plus ``MULTI`` candidates produced by an
  exact LP over the turn-sign pattern space (line lengths solved so the route reaches
  the required port pose inside the board);
* opposite frames: straight, rigid U (only feasible for dx >= 2R), two-jog Z
  staircases, and the same multi-bend LP family (which proves the small-offset
  opposite connections unreachable in this geometry - see report).

Nothing here changes routing/acceptance: every emitted candidate is checked with
the frozen ``fslw.geom.canonical_validate`` (pose, R=40, board, self-intersection)
and additionally verified to contain only exact 90-degree arcs; the exact strict
D56Index then decides inter-route legality, and the frozen independent validator
``fslw/validate_fslw.py`` audits the final layout.
"""
from __future__ import annotations

import itertools
import math
import random

import numpy as np

from ..fslw import config as C
from ..fslw import geom
from . import candext

R = C.RADIUS_MM
BOARD = C.BOARD_MM
HALF = C.WIDTH_MM / 2.0
QUARTER = math.pi / 2.0
TOL = 1e-6
START_HEADING = (0.0, 1.0)
END_HEADING = {'opposite': (0.0, 1.0), 'adjacent': (1.0, 0.0)}


# ---------------------------------------------------------------------------
# pure-90 geometry checks
# ---------------------------------------------------------------------------
def check_pure90(primitives, radius=R, tol=TOL):
    """True iff every primitive is a straight axis line or an exact 90-degree arc."""
    if not primitives:
        return False
    for primitive in primitives:
        kind = primitive.get('kind')
        if kind == 'line':
            p0, p1 = primitive['p0'], primitive['p1']
            if abs(p0[0] - p1[0]) > tol and abs(p0[1] - p1[1]) > tol:
                return False
        elif kind == 'arc':
            if abs(float(primitive['radius']) - radius) > tol:
                return False
            if abs(abs(float(primitive['sweep'])) - QUARTER) > tol:
                return False
        else:
            return False
    return True


def arc_statistics(primitives):
    """(n_lines, n_arcs, non90_arcs, n_diag_lines) of one primitive chain."""
    n_lines = n_arcs = non90 = diag = 0
    for primitive in primitives or []:
        if primitive.get('kind') == 'line':
            n_lines += 1
            p0, p1 = primitive['p0'], primitive['p1']
            if abs(p0[0] - p1[0]) > TOL and abs(p0[1] - p1[1]) > TOL:
                diag += 1
        elif primitive.get('kind') == 'arc':
            n_arcs += 1
            if abs(abs(float(primitive['sweep'])) - QUARTER) > TOL \
                    or abs(float(primitive['radius']) - R) > TOL:
                non90 += 1
    return dict(lines=n_lines, arcs=n_arcs, non90_arcs=non90, diagonal_lines=diag)


# ---------------------------------------------------------------------------
# exact LP over straight-line lengths for one turn-sign pattern
# ---------------------------------------------------------------------------
def _pattern_affine(turns):
    n_lines = len(turns) + 1
    cur_c = [0.0, 0.0]
    cur_x = [0.0] * n_lines
    cur_y = [0.0] * n_lines
    vector = START_HEADING
    primitives = []
    for index in range(n_lines):
        primitives.append(dict(
            kind='line', heading=vector,
            p0_c=tuple(cur_c), p0_x=list(cur_x), p0_y=list(cur_y),
            p1_c=tuple(cur_c), p1_x=list(cur_x), p1_y=list(cur_y)))
        cur_x[index] += vector[0]
        cur_y[index] += vector[1]
        if index < len(turns):
            sign = turns[index]
            nx, ny = -vector[1], vector[0]
            center_c = (cur_c[0] + sign * R * nx, cur_c[1] + sign * R * ny)
            start_angle = math.atan2(-sign * R * ny, -sign * R * nx)
            sweep = sign * QUARTER
            primitives.append(dict(
                kind='arc', center_c=center_c,
                center_x=list(cur_x), center_y=list(cur_y),
                start_x=list(cur_x), start_y=list(cur_y),
                start_angle=start_angle, sweep=sweep))
            cur_c = [center_c[0] + math.cos(start_angle + sweep) * R,
                     center_c[1] + math.sin(start_angle + sweep) * R]
            c, s = math.cos(sweep), math.sin(sweep)
            vector = (vector[0] * c - vector[1] * s, vector[0] * s + vector[1] * c)
    return primitives, cur_c, list(cur_x), list(cur_y), vector, n_lines


def _push(A, b, coeffs, base, lo, hi):
    A.append([-float(value) for value in coeffs])
    b.append(float(base) - lo)
    A.append([float(value) for value in coeffs])
    b.append(hi - float(base))


def _constraints(turns, p, q):
    primitives, end_c, end_x, end_y, end_heading, n_lines = _pattern_affine(turns)
    target = (q[0] - p[0], q[1] - p[1])
    A_eq = [[end_x[i] for i in range(n_lines)], [end_y[i] for i in range(n_lines)]]
    b_eq = [target[0] - end_c[0], target[1] - end_c[1]]
    A_ub, b_ub = [], []
    for primitive in primitives:
        if primitive['kind'] == 'line':
            horizontal = abs(primitive['heading'][1]) < 1e-12
            for cx, cy, const in (
                    (primitive['p0_x'], primitive['p0_y'], primitive['p0_c']),
                    (primitive['p1_x'], primitive['p1_y'], primitive['p1_c'])):
                if horizontal:
                    _push(A_ub, b_ub, cx, const[0] + p[0], 0.0, BOARD)
                    _push(A_ub, b_ub, cy, const[1] + p[1], HALF, BOARD - HALF)
                else:
                    _push(A_ub, b_ub, cx, const[0] + p[0], HALF, BOARD - HALF)
                    _push(A_ub, b_ub, cy, const[1] + p[1], 0.0, BOARD)
        else:
            angles = [primitive['start_angle'],
                      primitive['start_angle'] + primitive['sweep']]
            start = min(primitive['start_angle'],
                        primitive['start_angle'] + primitive['sweep'])
            end = max(primitive['start_angle'],
                      primitive['start_angle'] + primitive['sweep'])
            for k in range(-4, 13):
                angle = k * QUARTER
                if start + 1e-12 < angle < end - 1e-12:
                    angles.append(angle)
            for angle in angles:
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                for radius in (R - HALF, R + HALF):
                    _push(A_ub, b_ub, primitive['center_x'],
                          primitive['center_c'][0] + p[0] + radius * cos_a,
                          0.0, BOARD)
                    _push(A_ub, b_ub, primitive['center_y'],
                          primitive['center_c'][1] + p[1] + radius * sin_a,
                          0.0, BOARD)
    return A_ub, b_ub, A_eq, b_eq, n_lines, end_c, end_heading


def _moves_from_lengths(turns, lengths):
    moves = []
    for index in range(len(lengths)):
        if lengths[index] > 1e-9:
            moves.append(('L', float(lengths[index])))
        if index < len(turns):
            moves.append(('Q', int(turns[index])))
    return moves


def solve_pattern(turns, p, q, wanted_heading, rng, trials=1):
    """LP-solve one turn pattern; return a validated move list or None."""
    from scipy.optimize import linprog
    A_ub, b_ub, A_eq, b_eq, n_lines, end_c, end_heading = _constraints(turns, p, q)
    if abs(end_heading[0] - wanted_heading[0]) > 1e-9 \
            or abs(end_heading[1] - wanted_heading[1]) > 1e-9:
        return None
    A_ub = np.asarray(A_ub, dtype=float)
    b_ub = np.asarray(b_ub, dtype=float)
    A_eq = np.asarray(A_eq, dtype=float)
    b_eq = np.asarray(b_eq, dtype=float)
    bounds = [(0.0, None)] * n_lines
    for trial in range(trials):
        objective = np.zeros(n_lines) if trial == 0 else \
            np.array([rng.uniform(-1.0, 1.0) for _ in range(n_lines)])
        try:
            result = linprog(objective, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq,
                            b_eq=b_eq, bounds=bounds, method='highs')
        except Exception:  # noqa: BLE001 - solver robustness
            return None
        if not result.success:
            return None
        lengths = [max(0.0, float(value)) for value in result.x]
        moves = _moves_from_lengths(turns, lengths)
        primitives, end, heading = candext.move_path(p, START_HEADING, moves)
        if primitives is None:
            continue
        if abs(end[0] - q[0]) > 1e-6 or abs(end[1] - q[1]) > 1e-6:
            continue
        if abs(heading[0] - wanted_heading[0]) > 1e-9 \
                or abs(heading[1] - wanted_heading[1]) > 1e-9:
            continue
        ok, _errors = geom.canonical_validate(primitives, p, q, START_HEADING,
                                             wanted_heading)
        if ok and check_pure90(primitives):
            return dict(moves=moves, primitives=primitives,
                        params=dict(turns=list(turns),
                                    lengths=[round(value, 6) for value in lengths]))
    return None


def feasibility(turns, p, q, wanted_heading):
    """LP feasibility test only (used for the report's reachability analysis)."""
    from scipy.optimize import linprog
    A_ub, b_ub, A_eq, b_eq, n_lines, _end_c, end_heading = _constraints(turns, p, q)
    if abs(end_heading[0] - wanted_heading[0]) > 1e-9 \
            or abs(end_heading[1] - wanted_heading[1]) > 1e-9:
        return False
    try:
        result = linprog(np.zeros(n_lines),
                         A_ub=np.asarray(A_ub, dtype=float),
                         b_ub=np.asarray(b_ub, dtype=float),
                         A_eq=np.asarray(A_eq, dtype=float),
                         b_eq=np.asarray(b_eq, dtype=float),
                         bounds=[(0.0, None)] * n_lines, method='highs')
    except Exception:  # noqa: BLE001
        return None
    return bool(result.success)


def patterns_for_heading(delta_quarters, max_turns):
    patterns = []
    for n_turns in range(0, max_turns + 1):
        for combo in itertools.product((1, -1), repeat=n_turns):
            if (sum(combo) - delta_quarters) % 4 == 0:
                patterns.append(combo)
    return patterns


# ---------------------------------------------------------------------------
# static coordinate pools (layout independent, deterministic)
# ---------------------------------------------------------------------------
_GRID_STEP = C.CLEARANCE_MM


def _static_pool(structural, limit=260):
    values = [round(_GRID_STEP * k, 6) for k in range(int(BOARD / _GRID_STEP) + 1)]
    values = [value for value in values
              if HALF + 1e-6 <= value <= BOARD - HALF - 1e-6]
    merged = candext._unique_sorted(list(values) + list(structural))  # noqa: SLF001
    return candext._cap(merged, limit)  # noqa: SLF001


def static_pools(frame):
    sx = float(frame.p[0])
    qy = float(frame.qy)
    structural_y = [R, BOARD - R, qy, qy + R, qy - R, qy + 2 * R, qy - 2 * R]
    structural_x = [R, BOARD - R, sx, sx + R, sx - R, sx + 2 * R, sx - 2 * R]
    return (_static_pool(structural_y), _static_pool(structural_x))


# ---------------------------------------------------------------------------
# candidate generator
# ---------------------------------------------------------------------------
class Ortho90Generator:
    """Ranked pure-90 candidate queue (structural families + LP multi-bend)."""

    def __init__(self, cfg=None, seed=20261019):
        self.cfg = dict(cfg or {})
        self.seed = int(seed)
        self._spec_cache = {}
        self._prim_cache = {}

    # -- spec enumeration ---------------------------------------------------
    def specs(self, frame):
        key = frame.route_id
        cached = self._spec_cache.get(key)
        if cached is not None:
            return cached
        if frame.kind == 'adjacent':
            specs = self._adjacent_specs(frame)
        else:
            specs = self._opposite_specs(frame)
        self._spec_cache[key] = specs
        return specs

    def _adjacent_specs(self, frame):
        ys, xs = static_pools(frame)
        specs = []
        # frozen staircase families (pure quarter arcs by construction)
        move_specs = candext._adjacent_specs_moves(frame, None, ys, xs)  # noqa: SLF001
        for spec in move_specs:
            if any(op == 'S' for op, _arg in spec['moves']):
                continue
            spec = dict(spec)
            spec['builder'] = 'moves'
            specs.append(spec)
        builder_specs = candext._adjacent_specs_builders(frame, None, ys, xs)  # noqa: SLF001
        for spec in builder_specs:
            if spec.get('builder') == 'shift_turn':
                continue
            spec = dict(spec)
            specs.append(spec)
        # LP multi-bend family
        specs.extend(self._lp_specs(frame, (1.0, 0.0), -1))
        return specs

    def _opposite_specs(self, frame):
        p = (float(frame.p[0]), 0.0)
        q = (float(frame.q[0]), float(frame.q[1]))
        sx, tx = p[0], q[0]
        adx = abs(tx - sx)
        specs = []
        if adx < 1e-9:
            specs.append(dict(family='straight', builder='straight',
                              moves=[('L', BOARD)], params={}))
        else:
            ys, xs = static_pools(frame)
            if adx >= 2.0 * R - 1e-9:
                limits = geom.opposite_tracks(adx)
                if limits is not None:
                    lo, hi = limits
                    for track in candext._unique_sorted(  # noqa: SLF001
                            [lo + (hi - lo) * k / 24.0 for k in range(25)]):
                        if lo - 1e-9 <= track <= hi + 1e-9:
                            specs.append(dict(family='U', builder='opposite_u',
                                              params=dict(track_mm=float(track))))
            # two-jog staircases (all quarter arcs)
            for y1 in candext._cap(ys, 26):  # noqa: SLF001
                if y1 < R - 1e-9:
                    continue
                for xm in candext._cap(xs, 26):  # noqa: SLF001
                    if abs(xm - sx) < 2.0 * R - 1e-9:
                        continue
                    for y2 in candext._cap(ys, 20):  # noqa: SLF001
                        if abs(y2 - y1) < 2.0 * R - 1e-9:
                            continue
                        if abs(tx - xm) < 2.0 * R - 1e-9:
                            continue
                        specs.append(dict(family='Z', builder='opposite_z',
                                          params=dict(y1_mm=float(y1),
                                                      x_mid_mm=float(xm),
                                                      y2_mm=float(y2))))
        specs.extend(self._lp_specs(frame, (0.0, 1.0), 0))
        return specs

    def _lp_specs(self, frame, wanted_heading, delta):
        """LP multi-bend specs solved exactly for the port pose and board."""
        p = (float(frame.p[0]), 0.0)
        q = (float(frame.q[0]), float(frame.q[1]))
        max_turns = int(self.cfg.get('multi_max_turns', 9 if delta else 10))
        limit = int(self.cfg.get('multi_specs', 600))
        rng = random.Random(self.seed * 1000003 + frame.route_id * 17 + 1)
        patterns = patterns_for_heading(delta, max_turns)
        rng.shuffle(patterns)
        specs = []
        for turns in patterns:
            if len(specs) >= limit:
                break
            solved = solve_pattern(turns, p, q, wanted_heading, rng, trials=1)
            if solved is not None:
                specs.append(dict(family='MULTI', builder='multi',
                                  moves=solved['moves'],
                                  params=solved['params'],
                                  primitives=solved['primitives']))
        if not specs:
            # keep the pattern-based reachability evidence even when infeasible
            self.last_feasible_patterns = 0
        else:
            self.last_feasible_patterns = len(specs)
        return specs

    # -- scoring / ranking --------------------------------------------------
    def _score(self, spec, frame, oracle):
        builder = spec.get('builder')
        if builder == 'multi' or builder == 'moves':
            points = candext.moves_polyline((float(frame.p[0]), 0.0),
                                            START_HEADING, spec['moves'])
            return candext.score_polyline(points, oracle)
        if builder == 'straight':
            points = [(float(frame.p[0]), 0.0),
                      (float(frame.q[0]), float(frame.q[1]))]
            return candext.score_polyline(points, oracle)
        if builder == 'opposite_u':
            track = spec['params']['track_mm']
            points = [(float(frame.p[0]), 0.0),
                      (float(frame.p[0]), track),
                      (float(frame.q[0]), track),
                      (float(frame.q[0]), float(frame.q[1]))]
            return candext.score_polyline(points, oracle)
        if builder == 'opposite_z':
            params = spec['params']
            points = [(float(frame.p[0]), 0.0),
                      (float(frame.p[0]), params['y1_mm']),
                      (params['x_mid_mm'], params['y1_mm']),
                      (params['x_mid_mm'], params['y2_mm']),
                      (float(frame.q[0]), params['y2_mm']),
                      (float(frame.q[0]), float(frame.q[1]))]
            return candext.score_polyline(points, oracle)
        return candext._spec_score(spec, frame, oracle)  # noqa: SLF001

    def _build(self, frame, spec):
        key = id(spec)
        if key in self._prim_cache:
            return self._prim_cache[key]
        p = (float(frame.p[0]), 0.0)
        q = (float(frame.q[0]), float(frame.q[1]))
        wanted = END_HEADING[frame.kind]
        primitives = None
        try:
            builder = spec.get('builder')
            if builder == 'multi':
                primitives = spec.get('primitives')
            elif builder == 'moves':
                primitives, end, heading = candext.move_path(
                    p, START_HEADING, spec['moves'])
                if primitives is not None and (
                        abs(end[0] - q[0]) > 1e-6 or abs(end[1] - q[1]) > 1e-6):
                    primitives = None
            elif builder == 'z3':
                primitives = geom.adjacent_z3(p, q, spec['params']['_y1'],
                                              spec['params']['_x1'])
            elif builder == 'z5':
                primitives = geom.adjacent_z5(p, q, spec['params']['_y1'],
                                              spec['params']['_x1'],
                                              spec['params']['_y2'],
                                              spec['params']['_x2'])
            elif builder == 'straight':
                primitives = [geom.line(p, q)]
            elif builder == 'opposite_u':
                primitives = geom.opposite_path(p, q, spec['params']['track_mm'])
            elif builder == 'opposite_z':
                params = spec['params']
                primitives = geom.staircase(
                    [p, (p[0], params['y1_mm']),
                     (params['x_mid_mm'], params['y1_mm']),
                     (params['x_mid_mm'], params['y2_mm']),
                     (q[0], params['y2_mm']), q],
                    (0.0, 1.0), wanted)
            if primitives is not None:
                ok, _errors = geom.canonical_validate(
                    primitives, p, q, START_HEADING, wanted)
                primitives = primitives if ok else None
            if primitives is not None and not check_pure90(primitives):
                primitives = None
        except (ValueError, IndexError, ZeroDivisionError):
            primitives = None
        self._prim_cache[key] = primitives
        return primitives

    # -- public iterator ----------------------------------------------------
    def candidates(self, frame, oracle):
        specs = self.specs(frame)
        scored = []
        for spec in specs:
            scored.append((self._score(spec, frame, oracle), spec))
        # round-robin over families so one family cannot monopolise the budget
        buckets = {}
        for score, spec in scored:
            buckets.setdefault(spec['family'], []).append((score, spec))
        for family in buckets:
            buckets[family].sort(key=lambda item: item[0])
        names = sorted(buckets)
        seen = set()
        index = 0
        while True:
            emitted = False
            for family in names:
                bucket = buckets[family]
                if index >= len(bucket):
                    continue
                emitted = True
                _score_value, spec = bucket[index]
                primitives = self._build(frame, spec)
                if primitives is None:
                    continue
                signature = candext._dedupe_signature(primitives)  # noqa: SLF001
                if signature in seen:
                    continue
                seen.add(signature)
                yield dict(family=spec['family'],
                           params={key: value for key, value in
                                   (spec.get('params') or {}).items()
                                   if not key.startswith('_')},
                           primitives=primitives)
            if not emitted:
                return
            index += 1
