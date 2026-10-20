"""Expanded D56 candidate search for the V2 dual-height optimisation round.

This module does **not** introduce new geometry.  It only searches the existing
D56 primitive set (axis-aligned straight lines, fixed R=40 mm quarter arcs and the
original ``theta = acos(1 - d/(2R))`` two-arc short-S pair) more thoroughly than
the round-3 generator:

* every family is sampled on obstacle-derived clearance tracks instead of a
  coarse 24-point grid, so a candidate can be packed exactly ``0.08 mm`` from a
  placed waveguide;
* additionally, three "loop" families are added that use *the same* primitives
  but a longer orthogonal staircase with one short-S level shift (the previous
  generator only had 3-5 segment shapes and no descending approach);
* the candidate queue is ranked by an occupancy/crossing oracle and interleaved
  per family so that one family cannot monopolise the evaluation budget;
* duplicates are removed by a rounded primitive signature.

Nothing here decides legality: every emitted candidate is still validated by the
frozen strict :class:`four_side_1024.d56.index.D56Index` for the route and by
``four_side_1024.fslw.validate_fslw`` afterwards.
"""
from __future__ import annotations

import math

import numpy as np

from ..d56.candidates import clearance_tracks
from ..fslw import config as C
from ..fslw import geom
from . import config as V

BOARD = C.BOARD_MM
R = C.RADIUS_MM
CLEARANCE = C.CLEARANCE_MM
TAU = 2.0 * math.pi


# ---------------------------------------------------------------------------
# primitive helpers (same three D56 primitive kinds only)
# ---------------------------------------------------------------------------
def _rot90(vector):
    return (-vector[1], vector[0])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _scale(vector, factor):
    return (vector[0] * factor, vector[1] * factor)


def _rotate(vector, angle):
    c, s = math.cos(angle), math.sin(angle)
    return (vector[0] * c - vector[1] * s, vector[0] * s + vector[1] * c)


def _line(p0, p1):
    return geom.line(p0, p1)


def _arc(p0, p1, center, radius, start_angle, sweep):
    return geom.arc(p0, p1, center, radius, start_angle, sweep)


def move_path(p, heading, moves, radius=None):
    """Build the explicit D56 primitives for a move sequence.

    ``moves`` is a list of ``('L', length)`` (straight), ``('Q', +1/-1)``
    (quarter arc left/right) and ``('S', shift)`` (original two-arc short-S;
    ``shift`` positive to the left of the current travel direction).
    Returns ``(primitives, end_point, end_heading)`` or ``(None, None, None)``.
    """
    radius = R if radius is None else float(radius)
    cursor = (float(p[0]), float(p[1]))
    vector = (float(heading[0]), float(heading[1]))
    primitives = []
    for operation, argument in moves:
        if operation == 'L':
            length = float(argument)
            if length < -1e-9:
                return None, None, None
            if length > 1e-9:
                end = _add(cursor, _scale(vector, length))
                primitives.append(_line(cursor, end))
                cursor = end
        elif operation == 'Q':
            sign = 1.0 if argument >= 0 else -1.0
            center = _add(cursor, _scale(_rot90(vector), sign * radius))
            start_angle = math.atan2(cursor[1] - center[1], cursor[0] - center[0])
            sweep = sign * math.pi / 2.0
            end = _add(center, _scale((math.cos(start_angle + sweep),
                                       math.sin(start_angle + sweep)), radius))
            primitives.append(_arc(cursor, end, center, radius, start_angle, sweep))
            cursor = end
            vector = _rotate(vector, sign * math.pi / 2.0)
        elif operation == 'S':
            shift = float(argument)
            if abs(shift) <= 1e-9:
                continue
            primitives_s, end, _end_dir = geom.short_s(cursor, vector, shift, radius)
            if primitives_s is None:
                return None, None, None
            primitives.extend(primitives_s)
            cursor = end
        else:  # pragma: no cover - internal programming error
            raise ValueError('unknown move ' + str(operation))
    return primitives, cursor, vector


def moves_polyline(p, heading, moves):
    """Approximate the move path as orthogonal cursor points (ranking only)."""
    cursor = (float(p[0]), float(p[1]))
    vector = (float(heading[0]), float(heading[1]))
    points = [cursor]
    for operation, argument in moves:
        if operation == 'L':
            length = float(argument)
            if length < -1e-9:
                return None
            cursor = _add(cursor, _scale(vector, length))
            points.append(cursor)
        elif operation == 'Q':
            sign = 1.0 if argument >= 0 else -1.0
            # arc footprint: quarter turn advances R along both directions
            cursor = _add(_add(cursor, _scale(vector, R)),
                          _scale(_rot90(vector), sign * R))
            points.append(cursor)
            vector = _rotate(vector, sign * math.pi / 2.0)
        elif operation == 'S':
            shift = float(argument)
            if abs(shift) <= 1e-9:
                continue
            theta = math.acos(max(-1.0, min(1.0, 1.0 - abs(shift) / (2.0 * R))))
            advance = 2.0 * R * math.sin(theta)
            cursor = _add(cursor, _scale(vector, advance))
            cursor = _add(cursor, _scale(_rot90(vector), shift))
            points.append(cursor)
        else:
            raise ValueError('unknown move ' + str(operation))
    return points


# ---------------------------------------------------------------------------
# oracle scoring (ranking only; never decides legality)
# ---------------------------------------------------------------------------
def _segment_score(oracle, a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    if abs(dy) < 1e-9 and abs(dx) > 1e-9:
        x0, x1 = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
        parallel = oracle.h_parallel(a[1], x0, x1)
        crossing = oracle.h_crossings(a[1], x0, x1)
    elif abs(dx) < 1e-9 and abs(dy) > 1e-9:
        y0, y1 = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
        parallel = oracle.v_parallel(a[0], y0, y1)
        crossing = oracle.v_crossings(a[0], y0, y1)
    else:
        return 0.0
    return (V.SCORE_PARALLEL * parallel + V.SCORE_CROSS * crossing)


def score_polyline(points, oracle):
    if points is None or len(points) < 2:
        return 0.0
    score = 0.0
    for a, b in zip(points[:-1], points[1:]):
        score += _segment_score(oracle, a, b)
    return score


# ---------------------------------------------------------------------------
# coordinate pools (obstacle-derived clearance tracks + structural values)
# ---------------------------------------------------------------------------
def _cap(values, limit):
    if limit is None or len(values) <= limit:
        return list(values)
    if limit <= 1:
        return [values[0]]
    step = (len(values) - 1) / (limit - 1)
    return [values[int(round(i * step))] for i in range(limit)]


def _unique_sorted(values):
    return sorted({round(float(value), 6) for value in values
                   if -1e-9 <= float(value) <= BOARD + 1e-9})


def _clip_inside_board(values):
    """Drop centreline coordinates whose stroked waveguide would cross the board."""
    low = C.WIDTH_MM / 2.0 + 1e-6
    high = BOARD - C.WIDTH_MM / 2.0 - 1e-6
    return [value for value in values if low <= value <= high]


def pools_adjacent(frame, oracle):
    sx = float(frame.p[0])
    qy = float(frame.qy)
    h_obstacles = oracle.h_obstacle_ys(0.0, BOARD)
    v_obstacles = oracle.v_obstacle_xs(0.0, BOARD)
    y_tracks = clearance_tracks(h_obstacles, 0.0, BOARD,
                                clearance=CLEARANCE, margin=0.0006)
    x_tracks = clearance_tracks(v_obstacles, 0.0, BOARD,
                                clearance=CLEARANCE, margin=0.0006)
    structural_y = [R, BOARD - R, qy, qy + R, qy - R, qy + 2 * R, qy - 2 * R,
                    R + 0.5, BOARD - R - 0.5]
    structural_x = [R, BOARD - R, sx, sx + R, sx - R, sx + 2 * R, sx - 2 * R,
                    R + 0.5, BOARD - R - 0.5]
    ys = _unique_sorted(_clip_inside_board(list(y_tracks) + structural_y))
    xs = _unique_sorted(_clip_inside_board(list(x_tracks) + structural_x))
    if V.POOL_LIMIT:
        ys = _cap(ys, V.POOL_LIMIT)
        xs = _cap(xs, V.POOL_LIMIT)
    return ys, xs


# ---------------------------------------------------------------------------
# spec = ('family', params, moves, builder) ; cheap to create, lazy to build
# ---------------------------------------------------------------------------
def _spec(family, params, moves, builder='moves'):
    return dict(family=family, params=params, moves=moves, builder=builder)


def _adjacent_specs_moves(frame, oracle, ys, xs):
    """Move-sequence families: L / TURN_S / DOWN_LOOP (same D56 primitives).

    ``move_path`` semantics: a ``('L', length)`` ends at a tangent point and the
    following ``('Q', sign)`` arc starts there, so a skeleton corner contributes
    ``R`` of straight on each side (first/last corner: one side only).
    """
    sx = float(frame.p[0])
    qy = float(frame.qy)
    specs = []
    # --- L: rigid single corner --------------------------------------------
    if qy >= R - 1e-9 and sx <= BOARD - R + 1e-9:
        specs.append(_spec('L', {}, [('L', qy - R), ('Q', -1),
                                     ('L', BOARD - sx - R)]))
    # --- TURN_S: turn right early then a horizontal level shift ------------
    for y0 in ys:
        if y0 < R - 1e-9 or y0 > BOARD + 1e-9 or sx + R > BOARD + 1e-9:
            continue
        shift = qy - y0
        if abs(shift) >= 2.0 * R - 1e-9:
            continue
        advance = 0.0
        if abs(shift) > 1e-9:
            advance = 2.0 * R * math.sin(
                math.acos(1.0 - abs(shift) / (2.0 * R)))
        line = BOARD - (sx + R) - advance
        if line < -1e-9:
            continue
        moves = [('L', y0 - R), ('Q', -1)]
        if abs(shift) > 1e-9:
            moves.append(('S', shift))
        moves.append(('L', max(0.0, line)))
        specs.append(_spec('TURN_S', dict(y0_mm=float(y0)), moves))
    # --- DOWN_LOOP: left, up, right, down, then approach q travelling +x ---
    #     skeleton [p,(sx,y1),(x_a,y1),(x_a,y2),(x_b,y2),(x_b,y_t),q].
    #     ``y_t`` is the height at which the final left arc lands into q, so it
    #     is allowed to be close to q.y (and may need no S at all).
    loop_ys = _cap([y for y in ys if y >= R - 1e-9], V.LOOP_POOL)
    loop_xs = _cap([x for x in xs if x <= sx - 2.0 * R + 1e-9], V.LOOP_POOL)
    upper_xs = _cap([x for x in xs if x <= BOARD - R + 1e-9], V.LOOP_POOL)
    yt_candidates = [y for y in ys if abs(y - qy) < 2.0 * R - 1e-9
                     and -1e-9 <= y <= BOARD - R + 1e-9]
    # values closest to q.y keep the final short-S advance (and therefore the
    # required terminal straight) small, so rank the pool by distance to q.y
    yt_candidates = sorted(_unique_sorted(yt_candidates + [qy]),
                           key=lambda value: abs(value - qy))
    yt_pool = _unique_sorted(yt_candidates[:V.LOOP_POOL + 2])
    loop_count = 0
    stopped = False
    for y1 in loop_ys:
        for x_a in loop_xs:
            for y2 in loop_ys:
                if y2 < y1 + 2.0 * R - 1e-9:
                    continue
                for x_b in upper_xs:
                    if x_b < x_a + 2.0 * R - 1e-9:
                        continue
                    for y_t in yt_pool:
                        if y_t > y2 - 2.0 * R + 1e-9:
                            continue
                        if loop_count >= V.LOOP_MAX_SPECS:
                            stopped = True
                            break
                        shift = qy - y_t
                        if abs(shift) >= 2.0 * R - 1e-9:
                            continue
                        advance = 0.0
                        if abs(shift) > 1e-9:
                            advance = 2.0 * R * math.sin(
                                math.acos(1.0 - abs(shift) / (2.0 * R)))
                        line = BOARD - (x_b + R) - advance
                        if line < -1e-9:
                            continue
                        moves = [('L', y1 - R), ('Q', 1),
                                 ('L', sx - x_a - 2.0 * R), ('Q', -1),
                                 ('L', y2 - y1 - 2.0 * R), ('Q', -1),
                                 ('L', x_b - x_a - 2.0 * R), ('Q', -1),
                                 ('L', y2 - y_t - 2.0 * R), ('Q', 1)]
                        if abs(shift) > 1e-9:
                            moves.append(('S', shift))
                        moves.append(('L', max(0.0, line)))
                        specs.append(_spec(
                            'DOWN_LOOP',
                            dict(y1_mm=float(y1), x_a_mm=float(x_a),
                                 y2_mm=float(y2), x_b_mm=float(x_b),
                                 y_t_mm=float(y_t)), moves))
                        loop_count += 1
                    if stopped:
                        break
                if stopped:
                    break
            if stopped:
                break
        if stopped:
            break
    return specs


def _adjacent_specs_builders(frame, oracle, ys, xs):
    """Frozen family builders (``fslw.geom``) evaluated on the dense pools."""
    sx = float(frame.p[0])
    qy = float(frame.qy)
    specs = []
    # SHIFT_TURN: vertical short-S then quarter turn (needs qy >= R)
    if qy >= R - 1e-9:
        for dx in xs:
            shift = dx - sx
            if abs(shift) >= 2.0 * R - 1e-9 or abs(shift) < 1e-9:
                continue
            specs.append(_spec('SHIFT_TURN', dict(dx_shift_mm=float(shift)),
                               None, builder='shift_turn',
                               ))
            specs[-1]['params']['_dx'] = float(shift)
    # Z3 / LEFT: turn height + terminal riser
    z3_ys = _cap([y for y in ys if abs(y - qy) >= 2.0 * R - 1e-9], V.Z3_POOL)
    z3_xs = _cap([x for x in xs if abs(x - sx) >= 2.0 * R - 1e-9
                  and x <= BOARD - R + 1e-9], V.Z3_POOL)
    for y1 in z3_ys:
        for x1 in z3_xs:
            family = 'LEFT' if x1 < sx else 'Z3'
            spec = _spec(family, dict(y1_mm=float(y1), x1_mm=float(x1)),
                         None, builder='z3')
            spec['params'].update(dict(_y1=float(y1), _x1=float(x1)))
            specs.append(spec)
    # Z5: two transfer tracks + two risers
    ys5 = _cap(ys, V.Z5_POOL)
    xs5 = _cap([x for x in xs if x <= BOARD - R + 1e-9], V.Z5_POOL)
    for y1 in ys5:
        for x1 in xs5:
            if abs(x1 - sx) < 2.0 * R - 1e-9 or x1 > BOARD - R + 1e-9:
                continue
            for y2 in ys5:
                if abs(y2 - y1) < 2.0 * R - 1e-9 or y2 > BOARD + 1e-9:
                    continue
                for x2 in xs5:
                    if x2 > BOARD - R + 1e-9:
                        continue
                    if abs(x2 - x1) < 2.0 * R - 1e-9:
                        continue
                    if abs(y2 - qy) < 2.0 * R - 1e-9:
                        continue
                    spec = _spec('Z5', dict(y1_mm=float(y1), x1_mm=float(x1),
                                            y2_mm=float(y2), x2_mm=float(x2)),
                                 None, builder='z5')
                    spec['params'].update(dict(_y1=float(y1), _x1=float(x1),
                                               _y2=float(y2), _x2=float(x2)))
                    specs.append(spec)
    return specs


# ---------------------------------------------------------------------------
# lazy builders
# ---------------------------------------------------------------------------
def build_candidate(frame, spec):
    """Return canonical primitives for a spec, or ``None`` if not D56-legal."""
    builder = spec.get('builder', 'moves')
    p = (float(frame.p[0]), 0.0)
    q = (BOARD, float(frame.qy))
    if builder == 'moves':
        primitives, end, heading = move_path(p, (0.0, 1.0), spec['moves'])
        if primitives is None:
            return None
        if math.hypot(end[0] - q[0], end[1] - q[1]) > 1e-6:
            return None
        if abs(heading[0] - 1.0) > 1e-9 or abs(heading[1]) > 1e-9:
            return None
        primitives = list(primitives)
    elif builder == 'z3':
        params = spec['params']
        primitives = geom.adjacent_z3(p, q, params['_y1'], params['_x1'])
    elif builder == 'z5':
        params = spec['params']
        primitives = geom.adjacent_z5(p, q, params['_y1'], params['_x1'],
                                      params['_y2'], params['_x2'])
    elif builder == 'shift_turn':
        primitives = geom.adjacent_shift_turn(p, q, spec['params']['_dx'])
    else:  # pragma: no cover
        raise ValueError('unknown builder ' + str(builder))
    if primitives is None or not primitives:
        return None
    ok, _errors = geom.canonical_validate(primitives, p, q, (0.0, 1.0), (1.0, 0.0))
    if not ok:
        return None
    return primitives


# ---------------------------------------------------------------------------
# adjacent candidate queue
# ---------------------------------------------------------------------------
def _dedupe_signature(primitives):
    parts = []
    for primitive in primitives:
        parts.append((primitive['kind'],
                      round(primitive['p0'][0], 6), round(primitive['p0'][1], 6),
                      round(primitive['p1'][0], 6), round(primitive['p1'][1], 6)))
    return tuple(parts)


def _interleave(buckets, order_key):
    """Round-robin over family buckets sorted internally by rank."""
    lists = [sorted(items, key=order_key) for items in buckets.values()]
    index = 0
    while True:
        emitted = False
        for bucket in lists:
            if index < len(bucket):
                yield bucket[index]
                emitted = True
        if not emitted:
            return
        index += 1


def adjacent_specs(frame, oracle, stats=None):
    """All search specs of one adjacent frame on the current layout's pools."""
    ys, xs = pools_adjacent(frame, oracle)
    specs = _adjacent_specs_moves(frame, oracle, ys, xs) + \
        _adjacent_specs_builders(frame, oracle, ys, xs)
    if V.MAX_SPECS and len(specs) > V.MAX_SPECS:
        # deterministic even subsample, always keeping the rigid L first
        head = specs[:1]
        rest = _cap(specs[1:], V.MAX_SPECS - 1)
        specs = head + rest
    if stats is not None:
        counts = {}
        for spec in specs:
            counts[spec['family']] = counts.get(spec['family'], 0) + 1
        stats['spec_counts'] = counts
        stats['spec_total'] = len(specs)
        stats['pool_y'] = len(ys)
        stats['pool_x'] = len(xs)
    return specs


def _spec_score(spec, frame, oracle):
    if spec['builder'] == 'moves':
        points = moves_polyline((float(frame.p[0]), 0.0), (0.0, 1.0), spec['moves'])
        return score_polyline(points, oracle)
    params = spec['params']
    score = 0.0
    if spec['builder'] == 'z3':
        score += oracle.h_parallel(params['_y1'], 0.0, BOARD) * 0.5
        score += oracle.v_parallel(params['_x1'], 0.0, BOARD) * 0.5
        score += oracle.v_parallel(params['_x1'], min(params['_y1'], frame.qy),
                                   max(params['_y1'], frame.qy))
        score += oracle.h_parallel(frame.qy, params['_x1'], BOARD) * 0.5
    elif spec['builder'] == 'z5':
        score += oracle.h_parallel(params['_y1'], 0.0, BOARD) * 0.5
        score += oracle.h_parallel(params['_y2'], 0.0, BOARD) * 0.5
        score += oracle.v_parallel(params['_x1'], 0.0, BOARD) * 0.5
        score += oracle.v_parallel(params['_x2'], 0.0, BOARD) * 0.5
    elif spec['builder'] == 'shift_turn':
        score += oracle.v_parallel(float(frame.p[0]), 0.0, BOARD) * 0.5
        score += oracle.h_parallel(frame.qy, 0.0, BOARD) * 0.5
    return score


def candidates_from_specs(frame, specs, oracle):
    """Ranked, de-duplicated candidate iterator over a cached spec list."""
    scored = [( _spec_score(spec, frame, oracle), spec) for spec in specs]
    grouped = {}
    for score, spec in scored:
        spec['_score'] = score
        grouped.setdefault(spec['family'], []).append(spec)
    order_key = lambda spec: (spec['_score'], str(spec['params']))
    seen = set()
    for spec in _interleave(grouped, order_key):
        primitives = build_candidate(frame, spec)
        if primitives is None:
            continue
        if V.DEDUPE:
            signature = _dedupe_signature(primitives)
            if signature in seen:
                continue
            seen.add(signature)
        yield dict(family=spec['family'], params=spec['params'],
                   primitives=primitives)


def candidates_adjacent(frame, oracle, stats=None):
    """Ranked, de-duplicated D56 candidate iterator for a canonical adjacent frame."""
    specs = adjacent_specs(frame, oracle, stats=stats)
    yield from candidates_from_specs(frame, specs, oracle)


def candidates_original(frame, oracle, cfg=None, stats=None):
    """The frozen round-2/3 generator (unexpanded caps) - E2 control arm.

    Used by the ablation so that "原预算" really means the historical candidate
    generator and budget, not the expanded queue truncated to 200.
    """
    from ..fslw import candidates as fslw_candidates
    from ..fslw.search import DEFAULT_CFG
    merged = dict(DEFAULT_CFG)
    if cfg:
        merged.update(cfg)
    count = 0
    for candidate in fslw_candidates.candidates(frame, oracle, merged, deep=False):
        count += 1
        yield candidate
    for candidate in fslw_candidates.candidates(frame, oracle, merged, deep=True):
        count += 1
        yield candidate
    if stats is not None:
        stats['spec_total'] = 'original_generator'


def candidates_opposite(frame, oracle, stats=None):
    """Ranked opposite-side candidates: frozen U/S family with denser tracks."""
    from ..fslw import candidates as fslw_candidates
    cfg = dict(u_candidates_shallow=V.OPPOSITE_SHALLOW,
               u_candidates_deep=V.OPPOSITE_DEEP,
               z_candidates=V.OPPOSITE_Z_CANDIDATES,
               z_track_samples=V.OPPOSITE_Z_TRACK_SAMPLES)
    count = 0
    if stats is not None:
        stats['spec_counts'] = {'U/S/Z': V.OPPOSITE_DEEP + V.OPPOSITE_Z_CANDIDATES}
        stats['spec_total'] = V.OPPOSITE_DEEP + V.OPPOSITE_Z_CANDIDATES
    for candidate in fslw_candidates.opposite_candidates(frame, oracle, cfg, deep=False):
        count += 1
        yield candidate
    for candidate in fslw_candidates.opposite_candidates(frame, oracle, cfg, deep=True):
        yield candidate
