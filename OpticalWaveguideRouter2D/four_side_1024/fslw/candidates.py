"""Candidate D56 path families for R>=40 mm on a 150x150 mm board.

The generator only *proposes* geometry; every candidate is validated locally
(``geom.canonical_validate``) and then, during routing, by the exact single-layer
index.  Ranking uses the same cheap line-occupancy oracle as the previous round; the
oracle never decides legality.

Families
--------
opposite (canonical S -> N, travelling +y)
    ``straight``   dx == 0
    ``U``          legacy transfer-track U (dx >= 2R)
    ``S``          legacy short-S (dx < 2R, theta = acos(1 - dx/(2R)))
adjacent (canonical S -> E, travelling +x)
    ``L``          rigid single corner (only when q.y >= R and 150 - p.x >= R)
    ``Z3``         four-segment staircase (turn, back-turn, final turn)
    ``TURN_S``     quarter turn at the port then a horizontal short-S to q.y
    ``SHIFT_TURN`` vertical short-S then a quarter turn into the target row
    ``Z5``         six-segment staircase for the remaining reachable region
    ``LEFT``       C-shaped staircase that turns left first (sources near x=150)
"""
from __future__ import annotations

import math

import numpy as np

from ..d56.candidates import FrameOracleSet, LineOracle, clearance_tracks  # noqa: F401
from . import config as C
from . import geom

def _board():
    return C.BOARD_MM


def _radius():
    return C.RADIUS_MM


def _clearance():
    return C.CLEARANCE_MM


def _preference_noise(route_id, value, modulo=1000):
    import zlib
    return (zlib.crc32(f'{route_id}:{value:.6f}'.encode()) % modulo) / modulo


def _sample(values, count):
    if len(values) <= count:
        return list(values)
    if count <= 1:
        return [values[0]]
    step = (len(values) - 1) / (count - 1)
    return [values[int(round(i * step))] for i in range(count)]


def _unique(values, digits=6):
    seen = set()
    out = []
    for value in values:
        key = round(float(value), digits)
        if key in seen:
            continue
        seen.add(key)
        out.append(float(value))
    return out


# ------------------------------------------------------------------ opposite
def opposite_candidates(frame, oracle, cfg, deep=False):
    """Yield ranked canonical opposite-side D56 candidates."""
    p, q = np.asarray(frame.p), np.asarray(frame.q)
    sx, tx = float(p[0]), float(q[0])
    adx = abs(tx - sx)
    if adx < 1e-9:
        primitives = geom.staircase([tuple(p), tuple(q)], (0.0, 1.0), (0.0, 1.0))
        if primitives is not None:
            yield dict(family='straight', params={}, primitives=primitives)
        return
    limits = geom.opposite_tracks(adx, C.RADIUS_MM)
    if limits is None:
        return
    lo, hi = limits
    if lo > hi:
        return
    x_lo, x_hi = (sx, tx) if sx <= tx else (tx, sx)
    obstacles = oracle.h_obstacle_ys(x_lo, x_hi) if oracle is not None else []
    tracks = clearance_tracks(obstacles, lo, hi, clearance=C.CLEARANCE_MM, margin=0.0006)
    if not tracks:
        grid = max(1, int((hi - lo) / CLEARANCE) + 1)
        tracks = [lo + (hi - lo) * index / max(1, grid - 1) for index in range(grid)]
    route_id = frame.route_id
    tracks = sorted(tracks, key=lambda value: _preference_noise(route_id, value))
    limit = int(cfg.get('u_candidates_deep' if deep else 'u_candidates_shallow',
                        160 if deep else 22))
    if deep:
        tracks = _sample(tracks, limit) if len(tracks) > limit else tracks
    else:
        tracks = tracks[:limit]
    for track in tracks:
        primitives = geom.opposite_path((sx, 0.0), (tx, C.BOARD_MM), track, C.RADIUS_MM)
        if primitives is not None:
            yield dict(family='S' if adx < 2 * C.RADIUS_MM else 'U',
                       params=dict(track_mm=float(track)), primitives=primitives)


# ------------------------------------------------------------------ adjacent
def _adjacent_ys(frame, oracle, cfg, deep):
    qy = float(frame.qy)
    if deep:
        grid = max(1, int(C.BOARD_MM / max(1e-3, C.CLEARANCE_MM)) + 1)
        values = [index * (C.BOARD_MM / (grid - 1)) for index in range(grid)]
        return _unique(values)
    radius = C.RADIUS_MM
    base = [0.0, qy - radius, qy, radius, C.BOARD_MM - radius,
            (qy + radius) / 2.0, (qy + C.BOARD_MM - radius) / 2.0]
    base += [radius + 0.5, qy - radius - 0.5]
    return _unique([value for value in base
                    if -1e-9 <= value <= C.BOARD_MM + 1e-9])


def _adjacent_xs(frame, oracle, cfg, deep):
    sx = float(frame.p[0])
    if deep:
        grid = max(1, int(C.BOARD_MM / max(1e-3, C.CLEARANCE_MM)) + 1)
        values = [index * (C.BOARD_MM / (grid - 1)) for index in range(grid)]
        return _unique(values)
    radius = C.RADIUS_MM
    base = [radius, sx + radius, sx + 2 * radius, C.BOARD_MM - radius,
            (sx + C.BOARD_MM - radius) / 2.0, radius + 1.0, sx + 3 * radius]
    return _unique([value for value in base
                    if 0.0 <= value <= C.BOARD_MM + 1e-9])


def _adjacent_specs(frame, oracle, cfg, deep):
    """Enumerate (family, params) specifications with cheap feasibility pruning."""
    p = (float(frame.p[0]), 0.0)
    q = (C.BOARD_MM, float(frame.qy))
    sx, qy = p[0], q[1]
    specs = []
    # L: rigid single corner
    primitives_l = geom.adjacent_l(p, q)
    if primitives_l is not None:
        specs.append(('L', {}, primitives_l))
    # TURN_S: quarter turn at height y0 then horizontal short-S into q.y
    radius = C.RADIUS_MM
    y0_values = _adjacent_ys(frame, oracle, cfg, deep)
    y0_values = [value for value in y0_values
                 if -1e-9 <= value <= C.BOARD_MM - radius + 1e-9]
    for y0 in y0_values:
        primitives = geom.adjacent_turn_shift(p, q, y0)
        if primitives is not None:
            specs.append(('TURN_S', dict(y0_mm=float(y0)), primitives))
    # SHIFT_TURN: vertical short-S then quarter turn into q.y
    if qy >= radius - 1e-9:
        for dx in _adjacent_xs(frame, oracle, cfg, deep):
            shift = dx - sx
            if abs(shift) >= 2 * radius - 1e-9:
                continue
            primitives = geom.adjacent_shift_turn(p, q, shift)
            if primitives is not None:
                specs.append(('SHIFT_TURN', dict(dx_shift_mm=float(shift)), primitives))
    # Z3 / Z5 / LEFT staircases on a coarse grid
    ys = _adjacent_ys(frame, oracle, cfg, deep)
    xs = _adjacent_xs(frame, oracle, cfg, deep)
    if deep:
        ys = _sample(ys, 24)
        xs = _sample(xs, 24)
    else:
        ys = _unique(ys)[:8]
        xs = _unique(xs)[:8]
    for y1 in ys:
        for x1 in xs:
            primitives = geom.adjacent_z3(p, q, y1, x1)
            if primitives is not None:
                specs.append(('Z3', dict(y1_mm=float(y1), x1_mm=float(x1)), primitives))
    if deep:
        for y1 in _sample(ys, 5):
            for x1 in _sample(xs, 5):
                for y2 in _sample(ys, 4):
                    for x2 in _sample(xs, 4):
                        primitives = geom.adjacent_z5(p, q, y1, x1, y2, x2)
                        if primitives is not None:
                            specs.append(('Z5', dict(y1_mm=float(y1), x1_mm=float(x1),
                                                     y2_mm=float(y2), x2_mm=float(x2)),
                                          primitives))
    for y1 in _sample(ys, 6):
        for x_left in _sample(xs, 6):
            primitives = geom.adjacent_left_y(p, q, y1, x_left)
            if primitives is not None:
                specs.append(('LEFT', dict(y1_mm=float(y1), x_left_mm=float(x_left)),
                              primitives))
    return specs


def adjacent_candidates(frame, oracle, cfg, deep=False):
    """Yield ranked canonical adjacent-side D56 candidates."""
    specs = _adjacent_specs(frame, oracle, cfg, deep)
    scored = []
    for family, params, primitives in specs:
        score = 0.0
        if oracle is not None:
            for primitive in primitives:
                if primitive['kind'] != 'line':
                    continue
                p0, p1 = primitive['p0'], primitive['p1']
                if abs(p0[1] - p1[1]) < 1e-9:
                    score += oracle.h_parallel(p0[1], min(p0[0], p1[0]),
                                               max(p0[0], p1[0]))
                else:
                    score += oracle.v_parallel(p0[0], min(p0[1], p1[1]),
                                               max(p0[1], p1[1]))
        scored.append((score, family, params, primitives))
    scored.sort(key=lambda item: item[0])
    limit = int(cfg.get('z3_candidates_deep' if deep else 'z3_candidates',
                        160 if deep else 30))
    for _score, family, params, primitives in scored[:limit]:
        yield dict(family=family, params=params, primitives=primitives)


def candidates(frame, oracle, cfg, deep=False):
    if frame.kind == 'opposite':
        yield from opposite_candidates(frame, oracle, cfg, deep=deep)
    elif frame.kind == 'adjacent':
        yield from adjacent_candidates(frame, oracle, cfg, deep=deep)
    else:
        raise ValueError('unknown canonical kind: ' + str(frame.kind))
