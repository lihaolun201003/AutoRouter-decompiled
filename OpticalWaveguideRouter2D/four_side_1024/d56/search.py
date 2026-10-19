"""Sequential D56 routing with pluggable order strategies and rip-up/reroute.

Only the *order* in which routes are attempted, the *choice among legal D56
candidates* and the *rip-up decisions* are optimised here.  Every accepted
route passes the exact single-layer index in :mod:`four_side_1024.d56.index`;
no radius, width, gap, endpoint, layer or geometry-family rule is relaxed.
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict

from .index import D56Index, prepare
from .candidates import FrameOracleSet, LineOracle, candidates

DEFAULT_CFG = dict(
    width=0.05,
    gap=0.125,
    sagitta=0.0005,
    min_radius_mm=5.0,
    min_cross_angle_deg=5.0,
    u_candidates_shallow=18,
    u_candidates_deep=420,
    z_candidates=64,
    z3_candidates=34,
    z3_candidates_deep=200,
    z3_y_options=11,
    z3_x_options=11,
    z3_y_options_deep=40,
    z3_x_options_deep=40,
    z_track_samples=12,
    candidate_budget_per_route=900,
    deep_after=12,
    crossing_policy='exact',
    group_order_legacy=['SW', 'ES', 'NW', 'EN', 'NS', 'EW'],
    group_order_opposite_first=['NS', 'EW', 'EN', 'ES', 'SW', 'NW'],
)

LEGACY_GROUP_ORDER = ['SW', 'ES', 'NW', 'EN', 'NS', 'EW']
OPPOSITE_FIRST_GROUP_ORDER = ['NS', 'EW', 'EN', 'ES', 'SW', 'NW']


# ----------------------------------------------------------------- ordering
def _chord_length(frame):
    dx = frame.dst_xy[0] - frame.src_xy[0]
    dy = frame.dst_xy[1] - frame.src_xy[1]
    return math.hypot(dx, dy)


def static_endpoint_lines(frames):
    """Coordinates of the geometry every route is *forced* to occupy.

    An endpoint on E/W lies on a horizontal segment, an endpoint on N/S on a
    vertical segment, and those coordinates are fixed by the CSV.  Returning
    them lets candidate generation keep out of the way of routes that have not
    been attempted yet.
    """
    h_values, v_values = set(), set()
    for frame in frames.values():
        if frame.source_side in 'EW':
            h_values.add(frame.src_xy[1])
        else:
            v_values.add(frame.src_xy[0])
        if frame.target_side in 'EW':
            h_values.add(frame.dst_xy[1])
        else:
            v_values.add(frame.dst_xy[0])
    return sorted(h_values), sorted(v_values)


def static_congestion(routes, endpoints, frames, cell=10.0):
    """Chord-count congestion predictor (identical idea to the historical run)."""
    tiles = Counter()
    chords = {}
    for r in routes:
        rid = r['route_id']
        frame = frames[rid]
        p = frame.src_xy
        q = frame.dst_xy
        cells = set()
        for k in range(41):
            t = k / 40.0
            x = p[0] + (q[0] - p[0]) * t
            y = p[1] + (q[1] - p[1]) * t
            cells.add((int(x // cell), int(y // cell)))
        chords[rid] = cells
        tiles.update(cells)
    return {rid: sum(tiles[c] for c in cs) for rid, cs in chords.items()}


def _within_group_key(route, frame, mode, congestion):
    if mode == 'x_desc':
        return (-frame.p[0],)
    if mode == 'x_asc':
        return (frame.p[0],)
    if mode == 'chord_desc':
        return (-_chord_length(frame),)
    if mode == 'chord_asc':
        return (_chord_length(frame),)
    if mode == 'congestion_desc':
        return (-congestion[route['route_id']],)
    if mode == 'csv':
        return (route['route_id'],)
    raise ValueError('unknown within-group order: ' + mode)


def build_order(routes, frames, strategy, congestion=None, index=None, oracle=None):
    """Return the list of route ids in the order dictated by ``strategy``."""
    cfg = strategy
    group_order = cfg.get('group_order') or OPPOSITE_FIRST_GROUP_ORDER
    within = cfg.get('within_group', 'x_desc')
    by_pair = defaultdict(list)
    for route in routes:
        by_pair[route['pair']].append(route)
    order = []
    if cfg.get('name') == 'global_dynamic':
        pool = list(routes)
        key_mode = cfg.get('global_key', 'congestion_desc')
        if key_mode == 'congestion_desc':
            pool.sort(key=lambda r: (-congestion[r['route_id']],
                                     r['relation'] != 'opposite'))
        elif key_mode == 'length_desc':
            pool.sort(key=lambda r: (-_chord_length(frames[r['route_id']]),
                                     r['relation'] != 'opposite'))
        else:
            raise ValueError('unknown global order: ' + key_mode)
        return [r['route_id'] for r in pool]
    dynamic = cfg.get('dynamic_adjacent_order', False)
    remaining = list(group_order)
    while remaining:
        pair = remaining.pop(0)
        if pair in ('NS', 'EW'):
            group = sorted(by_pair.get(pair, []),
                           key=lambda r: _within_group_key(r, frames[r['route_id']], within,
                                                           congestion or {}))
            order.extend(r['route_id'] for r in group)
            continue
        if dynamic and index is not None and oracle is not None:
            # Process the whole adjacent section, choosing the next pair by the
            # congestion it currently faces.
            pool = [pair] + [p for p in remaining if p not in ('NS', 'EW')]
            remaining = [p for p in remaining if p in ('NS', 'EW')]
            while pool:
                scores = []
                for candidate_pair in pool:
                    score = 0
                    for route in by_pair.get(candidate_pair, []):
                        frame = frames[route['route_id']]
                        mid = ((frame.p[0] + frame.q[0]) * 0.5,
                               (frame.p[1] + frame.q[1]) * 0.5)
                        score += oracle.h_parallel(mid[1], 0.0, 150.0)
                        score += oracle.v_parallel(mid[0], 0.0, 150.0)
                    scores.append((score, candidate_pair))
                scores.sort()
                chosen_pair = scores[0][1]
                pool.remove(chosen_pair)
                group = sorted(by_pair.get(chosen_pair, []),
                               key=lambda r: _within_group_key(r, frames[r['route_id']],
                                                               within, congestion or {}))
                order.extend(r['route_id'] for r in group)
            continue
        group = sorted(by_pair.get(pair, []),
                       key=lambda r: _within_group_key(r, frames[r['route_id']], within,
                                                       congestion or {}))
        order.extend(r['route_id'] for r in group)
    return order


# ------------------------------------------------------------------ attempt
class RouteResult:
    __slots__ = ('route_id', 'family', 'params', 'primitives', 'prepared',
                 'length_mm', 'crossings', 'candidate_index', 'bends')

    def __init__(self, route_id, family, params, primitives, prepared,
                 length_mm, crossings, candidate_index, bends):
        self.route_id = route_id
        self.family = family
        self.params = params
        self.primitives = primitives
        self.prepared = prepared
        self.length_mm = length_mm
        self.crossings = crossings
        self.candidate_index = candidate_index
        self.bends = bends


def attempt_route(frame, index, oracle, cfg, budget=None):
    """Try to place one route; returns ``(RouteResult | None, failure dict)``."""
    budget = budget or cfg['candidate_budget_per_route']
    reasons = Counter()
    blocker_counts = Counter()
    evaluated = 0
    index_start = index.evaluations
    phases = (False,) if cfg.get('no_deep', False) else (False, True)
    deep_after = cfg.get('deep_after', 12)
    for deep in phases:
        for candidate in candidates(frame, oracle, cfg, deep=deep):
            if evaluated >= budget:
                reasons['candidate_budget_exhausted'] += 1
                break
            evaluated += 1
            world = frame.to_world(candidate['primitives'])
            prepared = prepare(world)
            result = index.evaluate(prepared)
            if result.valid:
                bends = sum(1 for p in prepared.prims if p.kind == 'arc')
                return RouteResult(frame.route_id, candidate['family'],
                                   candidate['params'], world, prepared,
                                   prepared.length, len(result.crossings),
                                   evaluated - 1, bends), None
            reasons[result.reason or 'invalid'] += 1
            blocker_counts.update(result.blockers)
            if not deep and evaluated >= deep_after and cfg.get('early_deep', False):
                break
        if evaluated >= budget:
            break
    failure = dict(route_id=frame.route_id,
                   reason='no_legal_candidate' if evaluated else 'no_candidate_generated',
                   evaluated=evaluated,
                   candidate_evaluations=index.evaluations - index_start,
                   rejection_counts=dict(reasons),
                   blockers=dict(blocker_counts))
    return None, failure


# ------------------------------------------------------------------- engine
class Router:
    def __init__(self, frames, routes, cfg=None, log=print):
        self.cfg = dict(DEFAULT_CFG)
        if cfg:
            self.cfg.update(cfg)
        self.frames = frames
        self.routes = routes
        self.log = log
        self.index = D56Index(width=self.cfg['width'], gap=self.cfg['gap'],
                              sagitta=self.cfg['sagitta'],
                              min_cross_angle_deg=self.cfg['min_cross_angle_deg'],
                              crossing_policy=self.cfg['crossing_policy'])
        static_h, static_v = static_endpoint_lines(frames)
        self.oracles = FrameOracleSet(frames, static_h, static_v,
                                      clearance=self.cfg['width'] + self.cfg['gap'])
        reference_frame = next(iter(frames.values()))
        self.oracle = self.oracles.oracle_for(reference_frame)
        self.accepted = {}
        self.failed = {}
        self.congestion = static_congestion(routes, None, frames)
        self.start = time.perf_counter()

    # -- index maintenance -------------------------------------------------
    def _add(self, result):
        self.index.add(result.route_id, result.prepared)
        self.oracles.add(result.route_id, result.prepared)

    def _remove(self, route_id):
        self.index.remove(route_id)
        self.oracles.remove(route_id)

    def _try_place(self, route_id):
        frame = self.frames[route_id]
        oracle = self.oracles.oracle_for(frame)
        result, failure = attempt_route(frame, self.index, oracle, self.cfg)
        if result is not None:
            self._add(result)
            self.accepted[route_id] = result
            self.failed.pop(route_id, None)
            return True
        self.failed[route_id] = failure
        return False

    # -- strategy ----------------------------------------------------------
    def run(self, strategy, route_ids=None):
        started = time.perf_counter()
        order = build_order(self.routes, self.frames, strategy,
                            congestion=self.congestion, index=self.index,
                            oracle=self.oracle) if route_ids is None else list(route_ids)
        expected = {route['route_id'] for route in self.routes}
        if set(order) != expected or len(order) != len(expected):
            raise ValueError('strategy order must contain every route exactly once '
                             f'({len(order)} ids, {len(expected)} routes)')
        placed_before = len(self.accepted)
        for n, route_id in enumerate(order, 1):
            self._try_place(route_id)
            if n % 128 == 0:
                self.log(f'{strategy.get("name", "?")}: attempted {n}/{len(order)} '
                         f'accepted={len(self.accepted)} '
                         f'evals={self.index.evaluations} '
                         f'elapsed={time.perf_counter() - started:.1f}s')
        return dict(strategy=strategy.get('name'), attempted=len(order),
                    accepted=len(self.accepted) - placed_before,
                    total_accepted=len(self.accepted),
                    duration_seconds=time.perf_counter() - started)

    # -- rip-up and reroute ------------------------------------------------
    def ripup(self, max_rounds=8, blockers_per_route=3, budget_seconds=None,
              strategy=None):
        """Transactional rip-up/reroute of failed routes.

        A transaction is committed only if the failed route AND every ripped
        blocker end up placed; otherwise every change is rolled back exactly.
        """
        started = time.perf_counter()
        improvements = 0
        transactions = 0
        for round_index in range(max_rounds):
            pending = [rid for rid in self.failed
                       if self.failed[rid].get('reason') != 'no_candidate_generated']
            if not pending:
                break
            pending.sort(key=lambda rid: (len(self.failed[rid].get('blockers', {})),
                                          -self.failed[rid].get('evaluated', 0)))
            progress = 0
            for route_id in pending[:self.cfg.get('ripup_routes_per_round', 64)]:
                if budget_seconds is not None and \
                        time.perf_counter() - started > budget_seconds:
                    break
                blockers = self._pick_blockers(route_id, blockers_per_route)
                if not blockers:
                    continue
                transactions += 1
                saved = {}
                for blocker in blockers:
                    result = self.accepted.pop(blocker)
                    saved[blocker] = result
                    self._remove(blocker)
                success = self._try_place(route_id)
                rerouted = {}
                if success:
                    for blocker in blockers:
                        if self._try_place_keep(blocker, rerouted):
                            continue
                        success = False
                        break
                if success:
                    improvements += 1
                    progress += 1
                    continue
                # rollback
                self.accepted.pop(route_id, None)
                self._remove(route_id)
                for blocker in list(rerouted):
                    self.accepted.pop(blocker, None)
                    self._remove(blocker)
                self.failed.pop(route_id, None)
                for blocker, result in saved.items():
                    self.failed.pop(blocker, None)
                    old = self.accepted.get(blocker)
                    if old is not None:
                        self._remove(blocker)
                    self.accepted[blocker] = result
                    self._add(result)
                if route_id not in self.accepted:
                    # the failed record was overwritten by _try_place; restore
                    self.failed.setdefault(route_id, dict(route_id=route_id,
                                                          reason='no_legal_candidate',
                                                          evaluated=0,
                                                          rejection_counts={},
                                                          blockers={}))
            self.log(f'ripup round {round_index + 1}: committed={improvements} '
                     f'progress={progress} accepted={len(self.accepted)} '
                     f'failed={len(self.failed)} elapsed={time.perf_counter() - started:.1f}s')
            if progress == 0:
                break
        return dict(rounds=max_rounds, transactions=transactions,
                    improvements=improvements,
                    duration_seconds=time.perf_counter() - started)

    def _pick_blockers(self, route_id, limit):
        failure = self.failed.get(route_id) or {}
        counts = failure.get('blockers') or {}
        candidates_list = [(int(rid), count) for rid, count in counts.items()
                           if int(rid) in self.accepted]
        candidates_list.sort(key=lambda item: -item[1])
        return [rid for rid, _count in candidates_list[:limit]]

    def _try_place_keep(self, route_id, rerouted):
        placed = self._try_place(route_id)
        if placed:
            rerouted[route_id] = True
        return placed

    # -- summary -----------------------------------------------------------
    def final_audit(self):
        """Rebuild the index from scratch and drop any route that fails.

        The search index is incremental; this independent re-check guarantees
        that the delivered set is mutually consistent under the exact index
        (the external validator is still the authoritative audit).
        """
        audit = D56Index(width=self.cfg['width'], gap=self.cfg['gap'],
                         sagitta=self.cfg['sagitta'],
                         min_cross_angle_deg=self.cfg['min_cross_angle_deg'],
                         crossing_policy=self.cfg['crossing_policy'])
        for rid in list(self.accepted):
            audit.add(rid, self.accepted[rid].prepared)
        removed = []
        for rid in list(self.accepted):
            result = audit.evaluate(self.accepted[rid].prepared, exclude=[rid])
            if not result.valid:
                removed.append(dict(route_id=rid, reason=result.reason,
                                    blockers=list(result.blockers)[:5]))
        for entry in removed:
            self.accepted.pop(entry['route_id'], None)
            self.failed[entry['route_id']] = dict(
                route_id=entry['route_id'], reason='final_audit_removed',
                evaluated=entry.get('evaluated', 0),
                rejection_counts={'final_audit_' + str(entry['reason']): 1},
                blockers={str(b): 1 for b in entry['blockers']})
        # rebuild the live index without the removed routes
        for entry in removed:
            self._remove(entry['route_id'])
        return removed

    def summary(self, extra=None):
        info = dict(accepted=len(self.accepted), failed=len(self.failed),
                    evaluations=self.index.evaluations,
                    index_seconds=self.index.index_seconds,
                    exact_seconds=self.index.exact_seconds,
                    elapsed_seconds=time.perf_counter() - self.start)
        if extra:
            info.update(extra)
        return info
