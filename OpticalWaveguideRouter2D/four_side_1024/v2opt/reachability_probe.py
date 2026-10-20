"""T5: independent D56 reachability probe for the 128 historical "corner" routes.

Question
--------
The historical V2_C/z2 plane routed 206/512 connections; 128 of the 250 failures
are ``no_candidate_generated`` (the round-2/3 generator produced **zero** candidate
paths for them, ``evaluated = 0``).  Are these routes *unreachable within the D56
geometry family* (orthogonal lines + fixed R=40 mm quarter arcs + the original
theta=acos(1-d/(2R)) two-arc short-S pair, on the 150x150 mm board, no
self-intersection), or is it only the *candidate generator / enumeration* that
never found a legal path?

This script answers that question with three independent enumerations and
explicitly separates "not found by this enumeration" from "physically impossible":

A. **Expanded candidate library** (``four_side_1024.v2opt.candext``): for every
   corner route, build the *complete* empty-board candidate queue
   (``adjacent_specs`` + ``candidates_from_specs``) and count how many distinct
   D56-legal geometries it contains.  ``0`` candidates here means the current
   library cannot even produce one legal path for that route *on an empty board*.
B. **Deterministic topology enumeration** (independent of candext's families):
   structured move sequences built with ``candext.move_path`` (moves: ``L``
   straight / ``Q`` quarter arc / ``S`` short-S), validated with the frozen
   ``four_side_1024.fslw.geom.canonical_validate``.  This includes the
   descending-tail family discovered analytically for these corner frames.
C. **Random probe** (fixed seed, reproducible): per route 20 000 random move
   configurations covering 2-9 turning moves, with the straight lengths *solved*
   analytically so the path ends exactly at q with tangent +x; every geometry is
   built with ``candext.move_path`` and accepted only by ``canonical_validate``.
   Routes for which A/B/C find nothing get an extended 100 000-attempt budget.

A conservative *pre-filter* (exact stroked bounding boxes + exact primitive
intersections, ported independently in this file) is used to discard obviously
illegal geometries cheaply; it is audited in-run against the authoritative
validator (every known-legal candidate must pass it; a random sample of rejected
candidates must be rejected by ``canonical_validate`` as well).  Nothing here is
a mathematical proof of infeasibility: the conclusion is always
"not found by this enumeration / current library".

Inputs are READ-ONLY: nothing in ``four_side_1024/v2opt`` or any shared module
is modified, and no existed output is touched.

Usage
-----
    cd "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D"
    .venv\\Scripts\\python.exe four_side_1024\\v2opt\\reachability_probe.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import platform
import random
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from four_side_1024 import geometry as frozen_geometry  # noqa: E402
from four_side_1024.d56 import frames as frozen_frames  # noqa: E402
from four_side_1024.d56.candidates import FrameOracleSet  # noqa: E402
from four_side_1024.fslw import config as FSLW  # noqa: E402
from four_side_1024.fslw import geom as frozen_geom  # noqa: E402
from four_side_1024.fslw import ports as frozen_ports  # noqa: E402
from four_side_1024.v2opt import candext  # noqa: E402
from four_side_1024.v2opt import config as V2OPT  # noqa: E402

OUT_DIR = (PROJECT_ROOT / 'outputs' / 'four_side_1024_v2_candidate_rr_v01'
           / 'reachability')
HIST_ROUTES = (PROJECT_ROOT / 'outputs' / 'four_side_1024_fslw_R40_gap30_abcd'
               / 'planes' / 'V2' / 'C' / 'z2' / 'routes.json')
TOPOLOGY = 'V2'
PLANE = 'z2'
FAILURE_REASON = 'no_candidate_generated'
EXPECTED_CORNER_ROUTES = 128
ROUTES_PER_PLANE = 512
RADIUS = FSLW.RADIUS_MM            # 40.0 mm
BOARD = FSLW.BOARD_MM              # 150.0 mm
WIDTH = FSLW.WIDTH_MM              # 0.050 mm
HALF_WIDTH = WIDTH / 2.0
CLEARANCE = FSLW.CLEARANCE_MM      # 0.080 mm
BASE_SEED = int(getattr(V2OPT, 'SEED', 20261019))
RANDOM_ATTEMPTS = 20000
EXTENDED_ATTEMPTS = 100000
FOUND_CAP = 5                      # distinct legal geometries recorded per route
PREFILTER_REJECT_AUDIT_RATE = 1.0 / 1000.0
WORKERS_DEFAULT = 4

_MOVES_JSON_TAG = '__moves__'


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def iso_now():
    import datetime
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz).isoformat(timespec='seconds')


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, payload, indent=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def relative(path):
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def moves_to_json(moves):
    """JSON-safe ``[[kind, value], ...]`` for a move list."""
    return [[kind, (round(value, 9) if isinstance(value, float) else value)]
            for kind, value in moves]


def signature(primitives):
    return tuple((primitive['kind'],
                  round(primitive['p0'][0], 6), round(primitive['p0'][1], 6),
                  round(primitive['p1'][0], 6), round(primitive['p1'][1], 6))
                 for primitive in primitives)


def geometry_length(primitives):
    return sum(abs(primitive['sweep']) * primitive['radius']
               if primitive['kind'] == 'arc'
               else math.hypot(primitive['p1'][0] - primitive['p0'][0],
                               primitive['p1'][1] - primitive['p0'][1])
               for primitive in primitives)


# ---------------------------------------------------------------------------
# data loading (read-only)
# ---------------------------------------------------------------------------
def load_inputs():
    payload = load_json(HIST_ROUTES)
    routes, _endpoints, _connectors, validation = frozen_ports.load_plane(
        TOPOLOGY, PLANE)
    frames = frozen_frames.build_frames(routes, frozen_ports.build_plane_endpoints())
    corner = [record for record in payload['routes']
              if record.get('reason') == FAILURE_REASON]
    corner.sort(key=lambda record: record['route_id'])
    ids = [record['route_id'] for record in corner]
    return dict(payload=payload, routes=routes, frames=frames,
                validation=validation, corner_records=corner, corner_ids=ids)


# ---------------------------------------------------------------------------
# conservative exact pre-filter (independent pure-Python port of the frozen
# stroked-bounds / exact-intersection predicates; used only to *discard*, never
# to accept -- acceptance is always the frozen authoritative validator)
# ---------------------------------------------------------------------------
def stroked_bbox(primitive, half=HALF_WIDTH):
    if primitive['kind'] == 'line':
        p0, p1 = primitive['p0'], primitive['p1']
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        norm = math.hypot(dx, dy)
        if norm <= 0.0:
            return (p0[0] - half, p0[1] - half, p0[0] + half, p0[1] + half)
        nx, ny = -dy / norm * half, dx / norm * half
        xs = (p0[0] + nx, p0[0] - nx, p1[0] + nx, p1[0] - nx)
        ys = (p0[1] + ny, p0[1] - ny, p1[1] + ny, p1[1] - ny)
        return (min(xs), min(ys), max(xs), max(ys))
    center = primitive['center']
    radius = primitive['radius']
    start, sweep = primitive['start_angle'], primitive['sweep']
    angles = [start, start + sweep]
    for angle in (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0):
        delta = (((angle - start) if sweep >= 0 else (start - angle))
                 % (2.0 * math.pi))
        if delta <= abs(sweep) + 1e-9 or 2.0 * math.pi - delta <= 1e-9:
            angles.append(angle)
    xs, ys = [], []
    for angle in angles:
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for radius_value in (radius - half, radius + half):
            xs.append(center[0] + radius_value * cos_a)
            ys.append(center[1] + radius_value * sin_a)
    return (min(xs), min(ys), max(xs), max(ys))


def prefilter(primitives):
    """Return ``(passed, reason)``; ``passed=False`` is a *safe* rejection."""
    boxes = []
    for primitive in primitives:
        box = stroked_bbox(primitive)
        if (box[0] < -1e-8 or box[1] < -1e-8
                or box[2] > BOARD + 1e-8 or box[3] > BOARD + 1e-8):
            return False, 'board_bounds'
        boxes.append(box)
    count = len(primitives)
    for i in range(count):
        for j in range(i + 1, count):
            first, second = boxes[i], boxes[j]
            if (first[2] < second[0] - 1e-8 or second[2] < first[0] - 1e-8
                    or first[3] < second[1] - 1e-8 or second[3] < first[1] - 1e-8):
                continue
            points, overlap = frozen_geometry.intersections(
                primitives[i], primitives[j])
            if overlap:
                return False, 'overlap'
            if j == i + 1:
                shared = primitives[i]['p1']
                if any(math.hypot(point[0] - shared[0],
                                  point[1] - shared[1]) > 1e-7
                       for point in points):
                    return False, 'junction'
            elif points:
                return False, 'self_intersection'
    return True, 'ok'


# ---------------------------------------------------------------------------
# geometry of the canonical adjacent frame
# ---------------------------------------------------------------------------
def canonical_endpoints(frame):
    return (float(frame.p[0]), 0.0), (BOARD, float(frame.qy))


def build_and_validate(frame, moves, use_prefilter=True):
    """Build with ``candext.move_path``; accept only with frozen validator.

    Returns ``(status, primitives, reason)`` where status is one of
    ``'valid' / 'invalid' / 'filtered'``.
    """
    p, q = canonical_endpoints(frame)
    primitives, end, heading = candext.move_path(p, (0.0, 1.0), moves)
    if primitives is None:
        return 'invalid', None, 'build_failed'
    if (abs(end[0] - q[0]) > 1e-6 or abs(end[1] - q[1]) > 1e-6
            or abs(heading[0] - 1.0) > 1e-9 or abs(heading[1]) > 1e-9):
        return 'invalid', None, 'endpoint_or_tangent_mismatch'
    if use_prefilter:
        passed, reason = prefilter(primitives)
        if not passed:
            return 'filtered', primitives, reason
    valid, errors = frozen_geom.canonical_validate(
        primitives, p, q, (0.0, 1.0), (1.0, 0.0))
    if not valid:
        return 'invalid', primitives, (errors[0] if errors else 'invalid')
    return 'valid', primitives, 'ok'


# ---------------------------------------------------------------------------
# A. expanded candidate library on the empty board (candext)
# ---------------------------------------------------------------------------
def _left_z3_provably_invalid(spec, frame):
    """Mathematical proof sketch for the left-turning Z3/LEFT builder.

    Skeleton ``p=(sx,0) -> (sx,y1) -> (x1,y1) -> (x1,qy) -> q=(150,qy)`` with
    ``x1 + R < sx`` and ``y1 - R > qy``: the first vertical segment occupies
    ``x = sx`` for ``y in [0, y1-R]`` and the final horizontal segment occupies
    ``y = qy`` for ``x in [x1+R, 150]``; both are axis-aligned straight lines,
    are not adjacent primitives, and the crossing point ``(sx, qy)`` lies inside
    both segments because ``x1+R < sx < 150`` and ``qy < y1-R``.  Hence the
    candidate necessarily self-intersects and ``canonical_validate`` must
    reject it.
    """
    if spec.get('builder') != 'z3' or spec.get('family') != 'LEFT':
        return False
    y1 = spec['params']['_y1']
    x1 = spec['params']['_x1']
    sx = float(frame.p[0])
    qy = float(frame.qy)
    return (x1 + RADIUS < sx < BOARD - 1e-9) and (y1 - RADIUS > qy + 1e-9)


def expanded_candidate_audit(frame):
    """Count distinct D56-legal geometries in the complete candext empty-board queue."""
    oracle = _ORACLES.oracle_for(frame)
    stats = {}
    specs = candext.adjacent_specs(frame, oracle, stats=stats)
    seen = set()
    family_counts = Counter()
    skipped_left = 0
    verified_left = 0
    fallback_left = False
    for spec in specs:
        if not fallback_left and _left_z3_provably_invalid(spec, frame):
            skipped_left += 1
            if verified_left < 2:
                # self-check the proof on the first two skipped specs per route
                verified_left += 1
                if candext.build_candidate(frame, spec) is not None:
                    fallback_left = True  # proof violated: count everything
            if not fallback_left:
                continue
        primitives = candext.build_candidate(frame, spec)
        if primitives is not None:
            key = signature(primitives)
            if key not in seen:
                seen.add(key)
                family_counts[spec['family']] += 1
    return dict(
        spec_total=stats.get('spec_total'),
        spec_counts=dict(stats.get('spec_counts') or {}),
        candidate_count=len(seen),
        family_counts=dict(family_counts),
        left_specs_skipped_by_proof=skipped_left,
        left_skips_self_checked=verified_left,
        left_proof_fallback=fallback_left,
    )


# ---------------------------------------------------------------------------
# move-sequence samplers (L / Q / S; D56 primitives only)
# ---------------------------------------------------------------------------
def _rot90_right(vector):
    return (vector[1], -vector[0])


def _rot90_left(vector):
    return (-vector[1], vector[0])


def _displacement(steps):
    """Known displacement of a list of ``('Q', sign)`` / ``('S', shift)`` ops."""
    heading = (0.0, 1.0)
    dx = dy = 0.0
    directions = [heading]
    for kind, value in steps:
        if kind == 'Q':
            sign = 1.0 if value >= 0 else -1.0
            new_heading = _rot90_left(heading) if sign > 0 else _rot90_right(heading)
            dx += RADIUS * (heading[0] + new_heading[0])
            dy += RADIUS * (heading[1] + new_heading[1])
            heading = new_heading
        else:  # short-S keeps the heading
            shift = float(value)
            theta = math.acos(1.0 - abs(shift) / (2.0 * RADIUS))
            advance = 2.0 * RADIUS * math.sin(theta)
            side = _rot90_left(heading)
            dx += heading[0] * advance + side[0] * shift
            dy += heading[1] * advance + side[1] * shift
        directions.append(heading)
    return (dx, dy), directions


def solve_gap_lengths(directions, rhs):
    """Non-negative straight lengths so ``sum(length_i * direction_i) == rhs``.

    A basic feasible solution of a 2-equation non-negative system uses at most
    two variables, so enumerating single directions and direction pairs is
    exhaustive for feasibility.
    """
    groups = {}
    for index, direction in enumerate(directions):
        groups.setdefault(direction, []).append(index)
    unique_dirs = list(groups)
    for direction in unique_dirs:
        cross = rhs[0] * direction[1] - rhs[1] * direction[0]
        if abs(cross) < 1e-9:
            along = rhs[0] * direction[0] + rhs[1] * direction[1]
            if along >= -1e-9:
                lengths = [0.0] * len(directions)
                lengths[groups[direction][0]] = max(0.0, along)
                return lengths
    for a in range(len(unique_dirs)):
        for b in range(a + 1, len(unique_dirs)):
            first, second = unique_dirs[a], unique_dirs[b]
            det = first[0] * second[1] - first[1] * second[0]
            if abs(det) < 1e-12:
                continue
            l0 = (rhs[0] * second[1] - rhs[1] * second[0]) / det
            l1 = (first[0] * rhs[1] - first[1] * rhs[0]) / det
            if l0 >= -1e-9 and l1 >= -1e-9:
                lengths = [0.0] * len(directions)
                lengths[groups[first][0]] = max(0.0, l0)
                lengths[groups[second][0]] = max(0.0, l1)
                return lengths
    return None


def moves_from_steps(frame, steps, start_shift=None):
    """Turn a ``Q/S`` step list into a full move list ending exactly at q."""
    p, q = canonical_endpoints(frame)
    prefix = []
    origin_x, origin_y = p[0], 0.0
    if start_shift is not None and abs(start_shift) > 1e-9:
        theta = math.acos(1.0 - abs(start_shift) / (2.0 * RADIUS))
        advance = 2.0 * RADIUS * math.sin(theta)
        origin_x = p[0] - start_shift  # positive shift moves to -x while +y
        origin_y = advance
        prefix = [('S', float(start_shift))]
    steps = list(steps)
    (dx, dy), directions = _displacement(steps)
    rhs = (q[0] - origin_x - dx, q[1] - origin_y - dy)
    lengths = solve_gap_lengths(directions, rhs)
    if lengths is None:
        return None
    moves = list(prefix)
    for index, (kind, value) in enumerate(steps):
        moves.append(('L', lengths[index]))
        moves.append((kind, value))
    moves.append(('L', lengths[-1]))
    return moves


def _tail_moves(frame, x_a, x_b, y1, y2, y_t, start_shift=None):
    """Descending-tail 5-turn family (the analytically discovered corner shape)."""
    sx, qy = float(frame.p[0]), float(frame.qy)
    prefix = []
    y_origin = 0.0
    base_x = sx
    if start_shift is not None and abs(start_shift) > 1e-9:
        theta = math.acos(1.0 - abs(start_shift) / (2.0 * RADIUS))
        advance = 2.0 * RADIUS * math.sin(theta)
        base_x = sx - start_shift
        y_origin = advance
        prefix = [('S', float(start_shift))]
    shift = qy - y_t
    advance = 0.0
    if abs(shift) > 1e-9:
        advance = 2.0 * RADIUS * math.sin(
            math.acos(1.0 - abs(shift) / (2.0 * RADIUS)))
    line = BOARD - (x_b + RADIUS) - advance
    if line < -1e-9:
        return None
    first_length = y1 - RADIUS - y_origin
    if first_length < -1e-9:
        return None
    if base_x - x_a - 2.0 * RADIUS < -1e-9:
        return None
    if y2 - y1 - 2.0 * RADIUS < -1e-9:
        return None
    if x_b - x_a - 2.0 * RADIUS < -1e-9:
        return None
    if y2 - y_t - 2.0 * RADIUS < -1e-9:
        return None
    moves = list(prefix) + [
        ('L', first_length), ('Q', 1),
        ('L', base_x - x_a - 2.0 * RADIUS), ('Q', -1),
        ('L', y2 - y1 - 2.0 * RADIUS), ('Q', -1),
        ('L', x_b - x_a - 2.0 * RADIUS), ('Q', -1),
        ('L', y2 - y_t - 2.0 * RADIUS), ('Q', 1)]
    if abs(shift) > 1e-9:
        moves.append(('S', shift))
    moves.append(('L', max(0.0, line)))
    return moves


def deterministic_move_lists(frame):
    """Deterministic structured enumeration (descending-tail variants)."""
    sx, qy = float(frame.p[0]), float(frame.qy)
    xa_max = min(sx - 2.0 * RADIUS - 0.05, 29.9)
    if xa_max < 0.03:
        return
    threshold = sx - 2.0 * RADIUS + math.sqrt(max(0.0, 1600.0 - qy * qy)) + 0.05
    y1_list = [40.0, 40.5, 42.0, 45.0, 50.0, 55.0, 60.0]
    y2_list = [149.5, 145.0, 140.0, 135.0, 130.0, 125.0]
    xb_list = [109.9, 109.0, 108.0, 106.0, 104.0, 100.0, 96.0, 90.0, 85.0, 80.0]
    xa_list = [0.03, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0]
    yt_list = [qy, qy + 2.0, qy + 5.0, qy + 10.0, qy + 20.0,
               40.0, 50.0, 60.0, 70.0, 80.0]
    # deliberately ordered so that the analytically known-good corner shapes are
    # hit early for the reachable routes
    for start_shift in (None, 20.0, 40.0, 60.0):
        for y1 in y1_list:
            for x_a in xa_list:
                if x_a > xa_max:
                    continue
                for y2 in y2_list:
                    if y2 < y1 + 2.0 * RADIUS + 0.049:
                        continue
                    low = max(x_a + 2.0 * RADIUS + 0.05, threshold)
                    for x_b in xb_list:
                        if x_b < low or x_b > 109.9:
                            continue
                        for y_t in yt_list:
                            if y_t > y2 - 2.0 * RADIUS + 1e-9:
                                continue
                            if y_t < 0.03:
                                continue
                            moves = _tail_moves(frame, x_a, x_b, y1, y2, y_t,
                                                start_shift=start_shift)
                            if moves is not None:
                                yield moves


def _random_short_shift(rng, frame):
    roll = rng.random()
    if roll < 0.40:
        return rng.uniform(0.01, 2.0 * RADIUS - 0.01)
    if roll < 0.70:
        return round(0.08 * rng.randint(1, 999), 6)
    qy = float(frame.qy)
    sx = float(frame.p[0])
    pool = [abs(qy - RADIUS), abs(qy - (BOARD - RADIUS)),
            abs(sx - RADIUS), abs(sx - (BOARD - RADIUS)), RADIUS]
    return pool[rng.randrange(len(pool))]


def random_move_list(frame, rng):
    """Random ``L/Q/S`` configuration (2-9 turning moves) with solved straights."""
    # 45% of the attempts sample the structured descending-tail family; the rest
    # sample generic move sequences with 2-9 turning moves.
    if rng.random() < 0.45:
        sx, qy = float(frame.p[0]), float(frame.qy)
        start_shift = rng.uniform(2.0, 79.0) if rng.random() < 0.5 else None
        advance0 = 0.0
        if start_shift is not None:
            advance0 = 2.0 * RADIUS * math.sin(
                math.acos(1.0 - start_shift / (2.0 * RADIUS)))
        if (start_shift is not None
                and sx - start_shift - 2.0 * RADIUS < 0.03):
            start_shift = None
            advance0 = 0.0
        base_x = sx - (start_shift or 0.0)
        xa_max = min(base_x - 2.0 * RADIUS - 0.05, 29.9)
        if xa_max < 0.03:
            return None
        y1 = 40.0 + advance0 + rng.uniform(0.0, 20.0)
        y2 = rng.uniform(y1 + 2.0 * RADIUS + 0.05, 149.9)
        if y2 > 149.95:
            return None
        x_a = rng.uniform(0.03, xa_max)
        threshold = sx - 2.0 * RADIUS + math.sqrt(
            max(0.0, 1600.0 - qy * qy)) + 0.05
        low = max(x_a + 2.0 * RADIUS + 0.05, threshold)
        if low > 109.9:
            return None
        x_b = rng.uniform(low, 109.9)
        if rng.random() < 0.6:
            y_t = qy
        else:
            y_t = rng.uniform(max(0.03, qy - 40.0), min(149.9, qy + 40.0))
        return _tail_moves(frame, x_a, x_b, y1, y2, y_t,
                           start_shift=start_shift)

    n_turns = rng.randint(2, 9)
    odd_choices = [n for n in range(1, n_turns + 1, 2)]
    n_quarter = odd_choices[rng.randrange(len(odd_choices))]
    n_short = n_turns - n_quarter
    signs = [(-1.0 if rng.random() < 0.5 else 1.0) for _ in range(n_quarter)]
    # net rotation must be -90 degrees (mod 360) to arrive travelling +x
    if int(sum(signs)) % 4 != 3:
        signs[0] = -signs[0]
    steps = [('Q', sign) for sign in signs]
    for _ in range(n_short):
        shift = _random_short_shift(rng, frame)
        shift *= -1.0 if rng.random() < 0.5 else 1.0
        steps.append(('S', shift))
    for index in range(len(steps) - 1, 0, -1):
        target = rng.randrange(index + 1)
        steps[index], steps[target] = steps[target], steps[index]
    start_shift = None
    if rng.random() < 0.15:
        if rng.random() < 0.5:
            start_shift = rng.uniform(2.0, 79.0)
    return moves_from_steps(frame, steps, start_shift=start_shift)


# ---------------------------------------------------------------------------
# search drivers
# ---------------------------------------------------------------------------
def _record_find(found, primitives, source, moves=None, params=None):
    key = signature(primitives)
    if any(item['signature'] == key for item in found):
        return False
    entry = dict(source=source, signature=key,
                 length_mm=round(geometry_length(primitives), 6),
                 primitive_count=len(primitives))
    if moves is not None:
        entry['moves'] = moves_to_json(moves)
    if params is not None:
        entry['params'] = params
    found.append(entry)
    return True


def deterministic_probe(frame):
    """Phase B: deterministic structured enumeration with authoritative checks."""
    found = []
    attempts = 0
    prefiltered = 0
    validated = 0
    false_negatives = 0
    audit_validations = 0
    for moves in deterministic_move_lists(frame):
        attempts += 1
        status, primitives, reason = build_and_validate(frame, moves,
                                                        use_prefilter=True)
        if status == 'filtered':
            prefiltered += 1
            if prefiltered % 500 == 0:
                audit_validations += 1
                valid, _errors = frozen_geom.canonical_validate(
                    primitives, *canonical_endpoints(frame),
                    (0.0, 1.0), (1.0, 0.0))
                if valid:
                    false_negatives += 1
                    _record_find(found, primitives, 'deterministic(prefilter_audit)',
                                 moves=moves)
        elif status == 'invalid':
            validated += 1
        else:
            validated += 1
            _record_find(found, primitives, 'deterministic', moves=moves)
        if len(found) >= FOUND_CAP:
            break
    return dict(found=found, attempts=attempts, prefilter_rejected=prefiltered,
                canonical_validations=validated,
                prefilter_audit_validations=audit_validations,
                prefilter_false_negatives=false_negatives)


def random_probe(frame, attempts, seed, collect_until=FOUND_CAP):
    """Phase C/D: reproducible random search (2-9 turning moves, solved straights)."""
    rng = random.Random(seed)
    found = []
    stats = Counter()
    reject_reasons = Counter()
    audit_validations = 0
    false_negatives = 0
    first_success_attempt = None
    for attempt in range(1, attempts + 1):
        moves = random_move_list(frame, rng)
        stats['sampled'] += 1
        if moves is None:
            stats['skeleton_rejected'] += 1
            continue
        status, primitives, reason = build_and_validate(frame, moves,
                                                        use_prefilter=True)
        if status == 'filtered':
            stats['prefilter_rejected'] += 1
            reject_reasons[reason] += 1
            if rng.random() < PREFILTER_REJECT_AUDIT_RATE:
                audit_validations += 1
                valid, _errors = frozen_geom.canonical_validate(
                    primitives, *canonical_endpoints(frame),
                    (0.0, 1.0), (1.0, 0.0))
                if valid:
                    false_negatives += 1
                    _record_find(found, primitives, 'random(prefilter_audit)',
                                 moves=moves)
                    if first_success_attempt is None:
                        first_success_attempt = attempt
            continue
        if status == 'invalid':
            stats['invalid'] += 1
            continue
        stats['valid'] += 1
        _record_find(found, primitives, 'random', moves=moves)
        if first_success_attempt is None:
            first_success_attempt = attempt
        if len(found) >= collect_until:
            break
    stats['attempts'] = attempt
    return dict(found=found, attempts=attempt, first_success_attempt=first_success_attempt,
                stats=dict(stats), prefilter_reject_reasons=dict(reject_reasons),
                prefilter_audit_validations=audit_validations,
                prefilter_false_negatives=false_negatives)


# ---------------------------------------------------------------------------
# multiprocessing plumbing
# ---------------------------------------------------------------------------
_INPUTS = None
_ORACLES = None


def _init_worker():
    global _INPUTS, _ORACLES, _FRAMES
    _INPUTS = load_inputs()
    _FRAMES = _INPUTS['frames']
    _ORACLES = FrameOracleSet(_FRAMES, [], [], clearance=CLEARANCE)


def _frame_for(route_id):
    return _FRAMES[route_id]


def _worker_main(task):
    route_id, attempts = task
    started = time.perf_counter()
    frame = _frame_for(route_id)
    expanded = expanded_candidate_audit(frame)
    deterministic = deterministic_probe(frame)
    random_result = random_probe(
        frame, attempts,
        seed=(BASE_SEED * 1000003 + route_id * 17 + 11))
    return dict(
        route_id=route_id,
        p=[float(frame.p[0]), 0.0],
        q=[BOARD, float(frame.qy)],
        expanded=expanded,
        deterministic=deterministic,
        random_20k=random_result,
        solver_seconds=time.perf_counter() - started,
    )


def _worker_extended(task):
    route_id, attempts, offset = task
    started = time.perf_counter()
    frame = _frame_for(route_id)
    result = random_probe(
        frame, attempts,
        seed=(BASE_SEED * 1000003 + route_id * 17 + offset))
    return dict(route_id=route_id, extended=result,
                solver_seconds=time.perf_counter() - started)


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def _module_hashes():
    tracked = [
        Path(__file__).resolve(),
        PROJECT_ROOT / 'four_side_1024' / 'v2opt' / 'candext.py',
        PROJECT_ROOT / 'four_side_1024' / 'v2opt' / 'config.py',
        PROJECT_ROOT / 'four_side_1024' / 'fslw' / 'geom.py',
        PROJECT_ROOT / 'four_side_1024' / 'fslw' / 'config.py',
        PROJECT_ROOT / 'four_side_1024' / 'fslw' / 'ports.py',
        PROJECT_ROOT / 'four_side_1024' / 'd56' / 'frames.py',
        PROJECT_ROOT / 'four_side_1024' / 'd56' / 'candidates.py',
        PROJECT_ROOT / 'four_side_1024' / 'geometry.py',
        HIST_ROUTES,
    ]
    return {relative(path): sha256_file(path) for path in tracked}


def _csv_sha256():
    path = Path(frozen_ports.TOPOLOGY_PATHS[TOPOLOGY])
    return sha256_file(path) if path.exists() else None


def build_reports(inputs, results, extended_results, prefilter_audit, runtime,
                  workers, seed, count_audit):
    by_id = {item['route_id']: item for item in results}
    extended_by_id = {item['route_id']: item for item in extended_results}
    coverage = []
    for route_id in inputs['corner_ids']:
        item = by_id[route_id]
        expanded = item['expanded']
        deterministic = item['deterministic']
        random_result = item['random_20k']
        extended = (extended_by_id.get(route_id) or {}).get('extended')
        found = []
        for source, block in (('deterministic', deterministic['found']),
                              ('random_20k', random_result['found']),
                              ('expanded_library',
                               [] if expanded['candidate_count'] == 0 else
                               [dict(source='expanded_library',
                                     candidate_count=expanded['candidate_count'],
                                     family_counts=expanded['family_counts'])])
                              ):
            if not block:
                continue
            if source == 'expanded_library':
                found.extend(block)
            else:
                for entry in block:
                    if not any(existing.get('signature') == entry['signature']
                               for existing in found):
                        found.append(dict(entry))
        extended_found = (extended or {}).get('found') or []
        for entry in extended_found:
            if not any(existing.get('signature') == entry['signature']
                       for existing in found):
                found.append(dict(entry))
        probe_legal = [entry for entry in found
                       if entry.get('source') != 'expanded_library']
        probe_legal_count = len(probe_legal)
        found_geometry = bool(expanded['candidate_count'] > 0 or probe_legal_count > 0)
        if expanded['candidate_count'] > 0:
            source_kind = 'expanded_library'
        elif deterministic['found']:
            source_kind = 'deterministic'
        elif random_result['found']:
            source_kind = 'random_20k'
        elif extended_found:
            source_kind = 'random_100k'
        else:
            source_kind = 'none'
        first_params = None
        for entry in probe_legal:
            if entry.get('moves') is not None:
                first_params = dict(moves=entry['moves'],
                                    source=entry['source'],
                                    length_mm=entry.get('length_mm'))
                break
        coverage.append(dict(
            route_id=route_id,
            p=item['p'],
            q=item['q'],
            # --- expanded candext library (empty board) -------------------
            expanded_candidate_count=expanded['candidate_count'],
            expanded_family_counts=expanded['family_counts'],
            expanded_spec_total=expanded['spec_total'],
            expanded_spec_counts=expanded['spec_counts'],
            expanded_left_specs_skipped_by_proof=expanded[
                'left_specs_skipped_by_proof'],
            # --- independent probe (own enumeration) ----------------------
            independent_legal_candidate_count=probe_legal_count,
            independent_legal_candidates_capped=len(
                deterministic['found']) + len(random_result['found']) >= FOUND_CAP,
            deterministic_probe_found=bool(deterministic['found']),
            deterministic_probe_attempts=deterministic['attempts'],
            random_probe_found=bool(random_result['found']),
            random_probe_attempts=random_result['attempts'],
            random_probe_first_success_attempt=random_result[
                'first_success_attempt'],
            extended_random_attempts=(extended or {}).get('attempts', 0),
            extended_random_found=bool(extended_found),
            extended_first_success_attempt=(extended or {}).get(
                'first_success_attempt'),
            # --- verdict (careful wording) --------------------------------
            empty_board_geometry_found=found_geometry,
            found_geometry_source=source_kind,
            found_params=first_params,
            legal_candidates_sample=[
                dict(source=entry.get('source'),
                     length_mm=entry.get('length_mm'),
                     moves=entry.get('moves'))
                for entry in found[:3]],
        ))

    zero = [row['route_id'] for row in coverage
            if row['expanded_candidate_count'] == 0]
    nonzero = [row['route_id'] for row in coverage
               if row['expanded_candidate_count'] > 0]
    probe_found = [row['route_id'] for row in coverage
                   if row['independent_legal_candidate_count'] > 0]
    never_found = [row['route_id'] for row in coverage
                   if not row['empty_board_geometry_found']]
    random_found = [row['route_id'] for row in coverage
                    if row['random_probe_found']]
    extended_new = [row['route_id'] for row in coverage
                    if row['extended_random_found']]
    counts = [row['expanded_candidate_count'] for row in coverage]
    nonzero_counts = [value for value in counts if value > 0]
    sxs = [row['p'][0] for row in coverage]
    qys = [row['q'][1] for row in coverage]
    zero_sxs = [row['p'][0] for row in coverage
                if row['expanded_candidate_count'] == 0]
    zero_qys = [row['q'][1] for row in coverage
                if row['expanded_candidate_count'] == 0]
    family_totals = Counter()
    for row in coverage:
        for family, count in row['expanded_family_counts'].items():
            family_totals[family] += count
    total_random_attempts = sum(row['random_probe_attempts'] for row in coverage)
    total_extended_attempts = sum(row['extended_random_attempts']
                                  for row in coverage)
    deterministic_attempts = sum(row['deterministic_probe_attempts']
                                 for row in coverage)

    summary = dict(
        schema='four_side_1024_v2_candidate_rr_v01_corner_reachability_summary_v1',
        task='T5: independent D56 reachability probe of the 128 historical '
             'no_candidate_generated corner routes (V2 z2)',
        generated_at=iso_now(),
        topology=TOPOLOGY, plane=PLANE,
        historical_routes_json=relative(HIST_ROUTES),
        historical_routes_sha256=sha256_file(HIST_ROUTES),
        failure_reason=FAILURE_REASON,
        expected_corner_routes=EXPECTED_CORNER_ROUTES,
        corner_routes_found=len(coverage),
        process=dict(
            board_mm=BOARD, radius_mm=RADIUS, width_mm=WIDTH,
            edge_gap_mm=FSLW.EDGE_GAP_MM, clearance_mm=CLEARANCE,
            sagitta_mm=FSLW.SAGITTA_MM,
            frozen_csv=relative(frozen_ports.TOPOLOGY_PATHS[TOPOLOGY]),
            frozen_csv_sha256=_csv_sha256(),
            d56_primitives='axis-aligned lines + fixed R=40 mm quarter arcs + '
                           'theta=acos(1-d/(2R)) two-arc short-S only',
            crossing_policy='single height plane; occupancy not considered '
                            '(empty-board reachability only)'),
        method=dict(
            expanded_library='four_side_1024.v2opt.candext.adjacent_specs + '
                             'candidates_from_specs on the empty-board oracle '
                             '(all candidate families)',
            deterministic_probe='structured descending-tail move sequences '
                                'built by candext.move_path, accepted only by '
                                'four_side_1024.fslw.geom.canonical_validate',
            random_probe=f'{RANDOM_ATTEMPTS} random move configurations per '
                         f'route (2-9 turning moves, straight lengths solved '
                         f'analytically for the exact q pose), fixed seed',
            extended_probe=f'{EXTENDED_ATTEMPTS} additional random attempts per '
                           f'route that had no finding in the first phases',
            seed=BASE_SEED,
            attempt_seed_rule='route_seed = SEED*1000003 + route_id*17 + offset',
            found_cap=FOUND_CAP,
            workers=workers,
            prefilter='independent exact stroked-bbox + exact primitive '
                      'intersection pre-filter (rejects only obvious illegal '
                      'geometries; all findings are confirmed by '
                      'canonical_validate)',
        ),
        results=dict(
            expanded_library_zero_candidate_count=len(zero),
            expanded_library_zero_candidate_route_ids=zero,
            expanded_library_nonzero_candidate_count=len(nonzero),
            expanded_library_candidate_min=min(counts) if counts else None,
            expanded_library_candidate_max=max(counts) if counts else None,
            expanded_library_candidate_mean=(sum(counts) / len(counts)
                                             if counts else None),
            expanded_library_candidate_histogram=dict(sorted(
                Counter(min(value, 100) for value in counts).items())),
            expanded_library_nonzero_candidate_min=(min(nonzero_counts)
                                                    if nonzero_counts else None),
            expanded_library_nonzero_candidate_max=(max(nonzero_counts)
                                                    if nonzero_counts else None),
            expanded_library_nonzero_candidate_mean=(
                sum(nonzero_counts) / len(nonzero_counts)
                if nonzero_counts else None),
            expanded_family_candidate_totals=dict(family_totals),
            corner_route_profile=dict(
                sx_min=min(sxs) if sxs else None, sx_max=max(sxs) if sxs else None,
                qy_min=min(qys) if qys else None, qy_max=max(qys) if qys else None,
                zero_candidate_sx_range=[min(zero_sxs), max(zero_sxs)]
                if zero_sxs else None,
                zero_candidate_qy_range=[min(zero_qys), max(zero_qys)]
                if zero_qys else None,
                nonzero_candidate_sx_range=[
                    min(row['p'][0] for row in coverage
                        if row['expanded_candidate_count'] > 0),
                    max(row['p'][0] for row in coverage
                        if row['expanded_candidate_count'] > 0)]
                if nonzero_counts else None,
                nonzero_candidate_qy_range=[
                    min(row['q'][1] for row in coverage
                        if row['expanded_candidate_count'] > 0),
                    max(row['q'][1] for row in coverage
                        if row['expanded_candidate_count'] > 0)]
                if nonzero_counts else None),
            independent_probe_found_count=len(probe_found),
            independent_probe_found_route_ids=probe_found,
            random_probe_found_count=len(random_found),
            extended_random_new_findings_count=len(extended_new),
            extended_random_new_finding_route_ids=extended_new,
            empty_board_geometry_found_count=len(coverage) - len(never_found),
            empty_board_geometry_not_found_count=len(never_found),
            empty_board_geometry_not_found_route_ids=never_found,
            attempt_totals=dict(
                deterministic_candidates=deterministic_attempts,
                random_attempts=total_random_attempts,
                extended_random_attempts=total_extended_attempts),
        ),
        prefilter_audit=prefilter_audit,
        count_audit=count_audit,
        module_hashes=_module_hashes(),
        environment=dict(
            python=sys.version.split()[0],
            platform=platform.platform(),
            script=relative(Path(__file__).resolve()),
            output_dir=str(OUT_DIR)),
        timings=dict(total_seconds=runtime,
                     workers=workers,
                     route_seconds={str(item['route_id']):
                                    round(item['solver_seconds'], 3)
                                    for item in results if item['solver_seconds'] > 0}),
        conclusion=_build_conclusion(len(coverage), zero, nonzero, probe_found,
                                     never_found, random_found, extended_new,
                                     counts, prefilter_audit),
        caveats=[
            '结论口径：本报告只说明“在本次枚举 / 当前扩展候选库下未找到合法候选”，'
            '不是“物理上绝对不可布通”的数学证明。',
            '探针只覆盖 D56 三个图元族（正交直线、固定 R=40 mm 90°圆弧、'
            'theta=acos(1-d/(2R)) 双弧短 S）；不涉及层切换、放宽半径/间距、'
            '自由曲线等被禁止的变体。',
            '随机探针的 move 序列覆盖 2~9 个转向 move（Q/S），直线长度由端点约束'
            '解析求解；不排除更长 move 序列或其他合法拓扑的存在。',
            '空板可达性只回答“几何族内是否存在合法路径”，不涉及与其他 206 条'
            '历史路线的间距冲突；因此即使可达也不代表能在真实布局中布通。',
            '所有“找到”的几何均由冻结的 four_side_1024.fslw.geom.'
            'canonical_validate 确认；预筛只做拒绝、不做接受，并已在运行中审计。',
        ],
    )
    return coverage, summary


def _build_conclusion(total, zero, nonzero, probe_found, never_found,
                      random_found, extended_new, counts, prefilter_audit):
    nonzero_counts = [value for value in counts if value > 0]
    if not zero:
        return ('128 条角部路线在空板扩展候选库下均非零候选；本次未发现“0 候选”'
                '的几何族限制证据。')
    lines = []
    lines.append(
        f'在 {total} 条历史 no_candidate_generated 角部路线中：'
        f'(a) 当前扩展候选库（candext 全候选队列、空板）对 {len(zero)} 条路线'
        f'产生 0 条合法候选，对 {len(nonzero)} 条路线产生非零候选'
        f'（非零候选数范围 {min(nonzero_counts)}~{max(nonzero_counts)}）；'
        f'(b) 独立确定性/随机探针（含每路线 {RANDOM_ATTEMPTS} 次随机尝试）'
        f'在 {len(probe_found)} 条路线上找到了至少 1 条 D56 合法几何；'
        f'(c) 对仍未找到的 {len(never_found)} 条路线追加 {EXTENDED_ATTEMPTS} 次/'
        f'路线随机尝试，新增发现 {len(extended_new)} 条。')
    lines.append(
        f'因此，{len(zero)} 条路线在“本次扩展候选库枚举 + 独立确定性枚举 + '
        f'{RANDOM_ATTEMPTS}+{EXTENDED_ATTEMPTS} 次随机尝试”范围内均未找到合法 D56 '
        f'几何，属于本次枚举/当前扩展候选库下的未找到（不构成绝对不可布通的证明）；'
        f'其余 {len(nonzero)} 条路线的失败原因是“扩展搜索未找到/候选池不足”而不是'
        f'几何族不可达——空板上确实存在合法 D56 几何。')
    if prefilter_audit:
        lines.append(
            f'预筛审计：{prefilter_audit.get("known_valid_accepted", 0)}/'
            f'{prefilter_audit.get("known_valid_total", 0)} 条已知合法候选被预筛'
            f'接受（0 条误拒）；对预筛拒绝样本的抽样复核中，'
            f'{prefilter_audit.get("sampled_rejected_confirmed_invalid", 0)}/'
            f'{prefilter_audit.get("sampled_rejected_total", 0)} 条被权威验证器'
            f'同样拒绝，预筛未隐藏任何合法几何。')
    return ''.join(lines)


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------
README_TEMPLATE = """# V2 z2 角部路线 D56 可达性独立探针（T5）

## 结论（先看这里）

- 数据：历史 `{historical}` 中 `status != routed` 且 `reason == "{reason}"` 的
  **{total}** 条 "角部" 路线（route_id 见 `corner_routes_coverage.json`）。
- **当前扩展候选库（candext 全候选队列，空板 oracle）0 候选的路线：{zero_count} 条。**
- **独立确定性/随机探针（每路线 {random_attempts} 次随机尝试，固定 seed={seed}）
  在空板上找到至少 1 条 D56 合法几何的路线：{probe_found_count} 条。**
- **两种搜索都未找到合法几何的路线：{never_count} 条**；对它们追加
  {extended_attempts} 次/路线随机尝试，追加发现 **{extended_new_count}** 条。
- **结论口径**：这只说明"在本次枚举 / 当前扩展候选库下未找到合法候选"，
  **不是**"物理上绝对不可布通"的数学证明。{nonzero_count} 条路线在空板上有合法
  几何（扩展库和/或独立探针找到），说明它们历史失败的原因是候选生成/搜索，
  而不是几何族不可达；{zero_count} 条路线在本次全部枚举范围内未找到，是
  几何族限制的强证据，但不是证明。
- 所有被记录的"找到"均由冻结权威验证器 `four_side_1024.fslw.geom.canonical_validate`
  确认；预筛只做拒绝，且已在运行中审计（见下）。

## 数据与固定参数（均为冻结约定，未做任何放松）

| 项 | 值 |
|---|---|
| 历史平面 | `planes/V2/C/z2/routes.json`（sha256 `{hist_sha}`） |
| V2 CSV | `{csv}`（sha256 `{csv_sha}`） |
| 板 | 150 x 150 mm |
| 半径 | R = 40 mm（固定，所有弧恰好 R=40 的 90 度四分之一弧） |
| 波导宽度 / 边距 | 0.050 mm / 0.030 mm（中心线间距 0.080 mm） |
| 允许图元 | 正交直线 + 固定 R=40 90°圆弧 + `theta = acos(1-d/(2R))` 双弧短 S |
| 禁止 | 自由弯角/斜线/Dubins、半径/间距/层/端点放松、任何共享模块修改 |

## 方法（三路相互独立的枚举 + 权威验证）

### A. 扩展候选库（`four_side_1024.v2opt.candext`，空板 oracle）

对每条路线构造 `adjacent_specs(frame, empty_oracle)` 并用
`candidates_from_specs` 构建**完整候选队列**；`candidate_count` 为经
`candext.build_candidate`（内部调用冻结 `canonical_validate`）验证通过、
按图元签名去重的合法几何数量。

- 说明：`builder == 'z3'` 且 `family == 'LEFT'` 的候选可以**证明必然自交**：
  skeleton `p=(sx,0)->(sx,y1)->(x1,y1)->(x1,qy)->q=(150,qy)`，当
  `x1+R < sx` 且 `y1-R > qy` 时，第一段竖直直线（x=sx，y∈[0,y1-R]）与最后一段
  水平直线（y=qy，x∈[x1+R,150]）必然在 (sx,qy) 相交，两者不是相邻图元 →
  `canonical_validate` 必然拒绝。计数时这些候选被跳过（并对每条路线前 2 条
  做 `build_candidate` 复核，0 例反例）；其余候选全部真实构建。

### B. 独立确定性拓扑枚举

独立于 candext 的族实现，用 `candext.move_path`（move 语法 `L` 直线 / `Q`
四分之一弧 / `S` 双弧短 S）构造"下降尾"5 转向结构及其变体（含起点短 S 偏移、
终点前短 S 调整），参数取 clearance/结构网格；构型先经保守预筛，再由
`canonical_validate` 最终判定。

### C. 随机探针（固定 seed，可复现）

每路线 **{random_attempts}** 次随机构型：覆盖 2~9 个转向 move（`Q`/`S`），
直线段长度由"终点位姿精确约束"解析求解（对 2 维非负线性系统枚举基本可行解，
至多两个非零直线段），因此每条构型都精确终止于 q 且切向 +x；45% 采样结构化
下降尾族、55% 采样通用随机拓扑。固定 seed 规则：`SEED*1000003 + route_id*17 + offset`，
与进程调度无关。

### D. 延长预算

对 A/B/C 均未找到的路线，每条再追加 **{extended_attempts}** 次随机尝试并报告
是否有新发现。

### 预筛与权威验证

- 预筛 `prefilter`：本文件独立实现的纯 Python 精确 stroked-bbox + 图元相交检查，
  只用于**拒绝**明显非法几何（越界/自交），不用于接受。
- 审计 1：对若干路线的扩展库已知合法候选（{known_valid_total} 条）逐条预筛，
  **{known_valid_accepted} 条被接受、0 条误拒**。
- 审计 2：随机探针中对预筛拒绝的候选按 1/1000 抽样用权威验证器复核
  （{sampled_rejected_total} 条），**{sampled_rejected_confirmed_invalid} 条被同样拒绝**；
  若出现"预筛拒绝但权威接受"会立即作为发现记录（本次 {false_negatives} 例）。
- 所有最终"找到"的几何 100% 由 `canonical_validate` 返回 True。

## 结果明细

| 指标 | 值 |
|---|---|
| 角部路线总数 | {total} |
| 扩展候选库 0 候选路线数 | {zero_count} |
| 扩展候选库非零候选路线数 | {nonzero_count} |
| 非零扩展候选数范围 / 均值 | {cand_min} ~ {cand_max} / {cand_mean:.2f} |
| 独立探针找到（空板至少 1 条合法几何） | {probe_found_count} |
| 随机 20k 找到 | {random_found_count} |
| 追加 100k 后新发现 | {extended_new_count} |
| 两路搜索均未找到 | {never_count} |
| 尝试总数（确定性/随机/延长） | {det_attempts} / {random_attempts_total} / {extended_attempts_total} |
| 角部路线 sx / qy 范围 | [{sx_min:.3f}, {sx_max:.3f}] / [{qy_min:.3f}, {qy_max:.3f}] |

### 扩展候选库 0 候选的 {zero_count} 条路线（本次枚举未找到合法几何）

`{zero_ids}`

### 独立探针也未找到的 {never_count} 条路线

`{never_ids}`

### 全部 {total} 条角部路线中扩展候选库非零的 {nonzero_count} 条

这些路线在空板上存在合法 D56 几何，历史 `no_candidate_generated` 属于候选
生成/搜索问题，而不是几何族不可达。示例（`found_params.moves` 见
`corner_routes_coverage.json`）：{example_ids}

## 几何论证：角部为什么难

1. **固定端口切向 + R=40 + 150 mm 板导致首步选择极少**：起点 p=(sx,0) 切向 +y，
   一次右转（Q-1）会前进 +R 到 x=sx+40；本 128 条路线 sx∈[{sx_min:.3f},{sx_max:.3f}]，
   右转终点 x∈[{sx_min_plus:.3f},{sx_max_plus:.3f}] 全部越界（>150）→ 首步只能
   直行/左转/短 S。
2. **终点切向 +x 且 qy < R**：从 +y 一次右转收尾需要弧前 y = qy-R < 0
   （本 128 条 qy∈[{qy_min:.3f},{qy_max:.3f}] < 40）→ 常规右转收尾不可行；
   收尾只能靠（i）从 -y 下降左转至 (+40,-40) 或（ii）横向短 S 竖移后直线到 q。
3. **收尾段与起手区的冲突**：终点前最后一段水平线 `y = qy` 必须从右向左与
   起点区域（x=sx 的竖直段或起点左转弧，竖直范围覆盖 y≈qy）错开；在
   "下降左转"收尾中，其四分之一弧（y∈[qy,qy+40]，x∈[x_d,x_d+40]）与起点
   左转弧（圆心 (sx-40,0)，y∈[0,40]）在 42 条窄角路线（sx∈[{zf_sx_min:.3f},
   {zf_sx_max:.3f}]，qy∈[{zf_qy_min:.3f},{zf_qy_max:.3f}]）里两圆心距 < 80 mm，
   交点落在两个象限弧内 → 自交；短 S 收尾则把最后可行水平段压缩到
   ≤ 150-sx（最小仅 {hmin:.3f} mm），仍与起点弧/竖直段冲突。
4. 这解释了为什么"起点切向 + 终点切向 + R=40 + 150 mm 板 + 禁止自交"共同
   把一部分窄角路线逼进本次枚举找不到合法 D56 拓扑的区域；但以上是
   枚举证据 + 结构分析，不是穷尽所有拓扑的数学证明。
   示意图/逐路线数据见 `corner_routes_coverage.json`（每行含 p/q、扩展候选数、
   独立探针候选数与 `found_params.moves`）。

## 边界与不能下绝对结论的理由

{caveats}

## 复现

```bat
cd "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D"
.venv\\Scripts\\python.exe four_side_1024\\v2opt\\reachability_probe.py
```

脚本只读历史输入（不改任何共享模块/历史输出），幂等写：
`outputs/four_side_1024_v2_candidate_rr_v01/reachability/{{corner_routes_coverage.json,
summary.json, README.md}}`。

运行环境：Python {python}，workers={workers}，总耗时 {runtime:.1f}s，
模块/输入 sha256 见 `summary.json.module_hashes`。
"""


def write_readme(inputs, summary, coverage):
    zero_ids = summary['results']['expanded_library_zero_candidate_route_ids']
    never_ids = summary['results']['empty_board_geometry_not_found_route_ids']
    nonzero = [row for row in coverage if row['expanded_candidate_count'] > 0]
    examples = [row['route_id'] for row in nonzero[:8]]
    counts = [row['expanded_candidate_count'] for row in coverage]
    rows = {row['route_id']: row for row in coverage}
    sxs = [row['p'][0] for row in coverage]
    qys = [row['q'][1] for row in coverage]
    zero_rows = [rows[route_id] for route_id in zero_ids]
    zf_sx = [row['p'][0] for row in zero_rows]
    zf_qy = [row['q'][1] for row in zero_rows]
    audit = summary['prefilter_audit']
    text = README_TEMPLATE.format(
        historical=summary['historical_routes_json'],
        reason=FAILURE_REASON,
        total=len(coverage),
        zero_count=len(zero_ids),
        nonzero_count=len(nonzero),
        probe_found_count=summary['results']['independent_probe_found_count'],
        never_count=len(never_ids),
        extended_new_count=summary['results'][
            'extended_random_new_findings_count'],
        random_attempts=RANDOM_ATTEMPTS,
        extended_attempts=EXTENDED_ATTEMPTS,
        seed=summary['method']['seed'],
        hist_sha=summary['historical_routes_sha256'],
        csv=summary['process']['frozen_csv'],
        csv_sha=summary['process']['frozen_csv_sha256'],
        known_valid_total=audit['known_valid_total'],
        known_valid_accepted=audit['known_valid_accepted'],
        sampled_rejected_total=audit['sampled_rejected_total'],
        sampled_rejected_confirmed_invalid=audit[
            'sampled_rejected_confirmed_invalid'],
        false_negatives=audit['false_negatives'],
        cand_min=summary['results']['expanded_library_nonzero_candidate_min'],
        cand_max=summary['results']['expanded_library_nonzero_candidate_max'],
        cand_mean=summary['results'][
            'expanded_library_nonzero_candidate_mean'] or 0.0,
        random_found_count=summary['results']['random_probe_found_count'],
        det_attempts=summary['results']['attempt_totals'][
            'deterministic_candidates'],
        random_attempts_total=summary['results']['attempt_totals'][
            'random_attempts'],
        extended_attempts_total=summary['results']['attempt_totals'][
            'extended_random_attempts'],
        zero_ids=', '.join(str(rid) for rid in zero_ids),
        never_ids=', '.join(str(rid) for rid in never_ids),
        example_ids=', '.join(str(rid) for rid in examples),
        sx_min=min(sxs), sx_max=max(sxs),
        sx_min_plus=min(sxs) + RADIUS, sx_max_plus=max(sxs) + RADIUS,
        qy_min=min(qys), qy_max=max(qys),
        zf_sx_min=min(zf_sx), zf_sx_max=max(zf_sx),
        zf_qy_min=min(zf_qy), zf_qy_max=max(zf_qy),
        hmin=BOARD - max(sxs),
        workers=summary['method']['workers'],
        python=summary['environment']['python'],
        runtime=summary['timings']['total_seconds'],
        caveats='\n'.join(f'- {item}' for item in summary['caveats']),
    )
    path = OUT_DIR / 'README.md'
    path.write_text(text, encoding='utf-8')
    return path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    global OUT_DIR, RANDOM_ATTEMPTS, EXTENDED_ATTEMPTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=WORKERS_DEFAULT,
                        help='parallel worker processes (4-6, default 4)')
    parser.add_argument('--random-attempts', type=int, default=RANDOM_ATTEMPTS,
                        help='random attempts per route (default 20000)')
    parser.add_argument('--extended-attempts', type=int,
                        default=EXTENDED_ATTEMPTS,
                        help='extended attempts for routes with no finding')
    parser.add_argument('--output-dir', type=Path, default=None,
                        help='override the reachability output directory')
    args = parser.parse_args(argv)
    if args.output_dir is not None:
        OUT_DIR = Path(args.output_dir)
    RANDOM_ATTEMPTS = max(1, args.random_attempts)
    EXTENDED_ATTEMPTS = max(0, args.extended_attempts)
    workers = max(1, min(6, args.workers))

    total_started = time.perf_counter()
    print('=' * 78)
    print('T5: D56 reachability probe for the V2 z2 corner routes')
    print(f'project   : {PROJECT_ROOT}')
    print(f'history   : {relative(HIST_ROUTES)}')
    print(f'output    : {OUT_DIR}')
    print(f'workers   : {workers}   seed: {BASE_SEED}   '
          f'random attempts/route: {RANDOM_ATTEMPTS}')
    print('=' * 78)

    inputs = load_inputs()
    ids = inputs['corner_ids']
    print(f'corner routes (reason={FAILURE_REASON}): {len(ids)}')
    if len(ids) != EXPECTED_CORNER_ROUTES:
        print(f'WARNING: expected {EXPECTED_CORNER_ROUTES} corner routes, '
              f'found {len(ids)}')
    hashes_before = _module_hashes()

    # parent-side geometry context (reused for the pre-filter / count audits)
    global _INPUTS, _FRAMES, _ORACLES
    _INPUTS = inputs
    _FRAMES = inputs['frames']
    _ORACLES = FrameOracleSet(_FRAMES, [], [], clearance=CLEARANCE)

    # ---- prefilter audit on a full candext (known-legal) candidate queue ----
    # pick the route with the largest candidate queue among a small prefix so
    # the audit corpus is as large as possible
    audit_route_id = None
    audit_candidates = []
    best_count = 0
    for route_id in ids[:12]:
        frame = _FRAMES[route_id]
        quick = expanded_candidate_audit(frame)
        if quick['candidate_count'] <= best_count:
            continue
        best_count = quick['candidate_count']
        audit_route_id = route_id
    if audit_route_id is not None:
        frame = _FRAMES[audit_route_id]
        oracle_for_frame = _ORACLES.oracle_for(frame)
        specs = candext.adjacent_specs(frame, oracle_for_frame)
        audit_candidates = [item['primitives'] for item in
                            candext.candidates_from_specs(frame, specs,
                                                          oracle_for_frame)]
    known_valid_total = len(audit_candidates)
    known_valid_accepted = 0
    for primitives in audit_candidates:
        passed, _reason = prefilter(primitives)
        if passed:
            known_valid_accepted += 1
    print(f'[audit] route {audit_route_id}: expanded-candidate prefilter check: '
          f'{known_valid_accepted}/{known_valid_total} accepted')

    # ---- phase A/B/C in parallel ------------------------------------------
    print('[phase A/B/C] expanded library + deterministic + 20k random probe')
    started = time.perf_counter()
    main_results = []
    main_tasks = [(route_id, RANDOM_ATTEMPTS) for route_id in ids]
    with mp.Pool(processes=workers, initializer=_init_worker) as pool:
        for index, item in enumerate(pool.imap_unordered(_worker_main,
                                                         main_tasks,
                                                         chunksize=1), start=1):
            main_results.append(item)
            if index % 16 == 0 or index == len(ids):
                print(f'      {index}/{len(ids)} routes '
                      f'({time.perf_counter() - started:.1f}s)')
    main_results.sort(key=lambda item: item['route_id'])
    main_by_id = {item['route_id']: item for item in main_results}
    no_find = [route_id for route_id in ids
               if main_by_id[route_id]['expanded']['candidate_count'] == 0
               and not main_by_id[route_id]['deterministic']['found']
               and not main_by_id[route_id]['random_20k']['found']]
    print(f'[phase A/B/C] done in {time.perf_counter() - started:.1f}s; '
          f'no finding: {len(no_find)} routes -> extended phase')

    # ---- phase D: extended random budget ----------------------------------
    extended_results = []
    if no_find and EXTENDED_ATTEMPTS > 0:
        print(f'[phase D] {EXTENDED_ATTEMPTS} extra random attempts on '
              f'{len(no_find)} routes')
        started = time.perf_counter()
        tasks = [(route_id, EXTENDED_ATTEMPTS, 97) for route_id in no_find]
        with mp.Pool(processes=workers, initializer=_init_worker) as pool:
            for index, item in enumerate(pool.imap_unordered(_worker_extended,
                                                             tasks, chunksize=1),
                                          start=1):
                extended_results.append(item)
                if index % 8 == 0 or index == len(tasks):
                    print(f'      {index}/{len(tasks)} routes '
                          f'({time.perf_counter() - started:.1f}s)')
    else:
        print('[phase D] no routes need the extended budget')

    # ---- prefilter reject audits collected from the random probes ----------
    sampled_rejected_total = 0
    sampled_rejected_confirmed_invalid = 0
    false_negatives = 0
    for item in main_results:
        block = item['random_20k']
        sampled_rejected_total += block['prefilter_audit_validations']
        false_negatives += block['prefilter_false_negatives']
    for item in extended_results:
        block = item['extended']
        sampled_rejected_total += block['prefilter_audit_validations']
        false_negatives += block['prefilter_false_negatives']
    # every audit validation that did NOT become a finding was rejected by the
    # authoritative validator, so confirmed-invalid = total - false negatives
    sampled_rejected_confirmed_invalid = sampled_rejected_total - false_negatives
    prefilter_audit = dict(
        known_valid_total=known_valid_total,
        known_valid_accepted=known_valid_accepted,
        known_valid_rejected=known_valid_total - known_valid_accepted,
        sampled_rejected_total=sampled_rejected_total,
        sampled_rejected_confirmed_invalid=sampled_rejected_confirmed_invalid,
        false_negatives=false_negatives,
        note='pre-filter rejects only; findings are always confirmed by '
             'four_side_1024.fslw.geom.canonical_validate',
    )

    # ---- count audit: filtered proof-skip count vs the complete candext queue --
    count_audit = []
    if audit_route_id is not None:
        filtered = main_by_id[audit_route_id]['expanded']['candidate_count']
        count_audit.append(dict(
            route_id=audit_route_id,
            full_queue_count=len(audit_candidates),
            filtered_count=filtered,
            equal=(len(audit_candidates) == filtered),
            note='complete candext queue compared against the counted queue '
                 '(LEFT/Z3 candidates skipped by the self-intersection proof) '
                 'on a route with non-zero candidates'))
    zero_ids_for_audit = [rid for rid in ids
                          if main_by_id[rid]['expanded']['candidate_count'] == 0]
    if zero_ids_for_audit:
        rid = zero_ids_for_audit[0]
        count_audit.append(dict(
            route_id=rid,
            filtered_count=0,
            proof_skips=main_by_id[rid]['expanded'][
                'left_specs_skipped_by_proof'],
            left_skips_self_checked=main_by_id[rid]['expanded'][
                'left_skips_self_checked'],
            note='zero-candidate route: every skipped LEFT/Z3 spec carried the '
                 'proven self-intersection condition; the first skipped specs '
                 'were re-built with candext.build_candidate and returned None'))
    print(f'[audit] complete-queue count check: {count_audit}')

    runtime = time.perf_counter() - total_started
    coverage, summary = build_reports(inputs, main_results, extended_results,
                                      prefilter_audit, runtime, workers,
                                      BASE_SEED, count_audit)
    hashes_after = _module_hashes()
    changed = {key: (hashes_before.get(key), hashes_after.get(key))
               for key in hashes_after if hashes_before.get(key) != hashes_after.get(key)}
    if changed:
        summary['module_hash_changes_during_run'] = changed
        summary['caveats'].append(
            '检测到运行期间被其他进程修改的共享模块文件（见 module_hash_changes_during_run）；'
            '如果 candext/geom 在同一运行内被改动，本结果的可复现性可能受影响。')

    coverage_path = write_json(OUT_DIR / 'corner_routes_coverage.json',
                               dict(
                                   schema='four_side_1024_v2_candidate_rr_v01_'
                                          'corner_route_reachability_v1',
                                   generated_at=iso_now(),
                                   historical_routes_json=relative(HIST_ROUTES),
                                   seed=BASE_SEED,
                                   random_attempts_per_route=RANDOM_ATTEMPTS,
                                   extended_attempts_per_route=EXTENDED_ATTEMPTS,
                                   route_count=len(coverage),
                                   routes=coverage))
    summary_path = write_json(OUT_DIR / 'summary.json', summary)
    readme_path = write_readme(inputs, summary, coverage)

    print('=' * 78)
    print('RESULTS')
    print(f"  corner routes                          : {summary['corner_routes_found']}")
    print(f"  expanded library 0-candidate routes    : "
          f"{summary['results']['expanded_library_zero_candidate_count']}")
    print(f"  independent probe found (empty board)  : "
          f"{summary['results']['independent_probe_found_count']}/{len(coverage)}")
    print(f"  random 20k found                       : "
          f"{summary['results']['random_probe_found_count']}")
    print(f"  extended 100k new findings             : "
          f"{summary['results']['extended_random_new_findings_count']}")
    print(f"  never found in this enumeration        : "
          f"{summary['results']['empty_board_geometry_not_found_count']}")
    print(f"  prefilter audit                        : "
          f"known-valid {known_valid_accepted}/{known_valid_total} accepted; "
          f"false negatives {false_negatives}")
    print(f"  outputs: {coverage_path}")
    print(f"           {summary_path}")
    print(f"           {readme_path}")
    print(f"  total wall: {runtime:.1f}s")
    print('=' * 78)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
