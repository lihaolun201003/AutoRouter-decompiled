"""Sequential D56 routing engine for the FSLW R>=40 mm / 0.08 mm-clearance planes.

Reuses the previous round's proven machinery (exact incremental single-layer index,
canonical frames, pluggable order strategies, transactional rip-up) but plugs in the
R=40 candidate families from :mod:`four_side_1024.fslw.candidates` and the 0.080 mm
centreline clearance from :mod:`four_side_1024.fslw.config`.
"""
from __future__ import annotations

import math
import time
from collections import Counter

from ..d56.index import D56Index, prepare
from ..d56.search import (DEFAULT_CFG as D56_DEFAULT_CFG, RouteResult,
                          build_order, static_congestion, static_endpoint_lines)
from . import config as C
from .candidates import FrameOracleSet, LineOracle, candidates

DEFAULT_CFG = dict(D56_DEFAULT_CFG)
DEFAULT_CFG.update(
    width=C.WIDTH_MM,
    gap=C.EDGE_GAP_MM,
    sagitta=C.SAGITTA_MM,
    min_radius_mm=C.RADIUS_MM,
    min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
    u_candidates_shallow=22,
    u_candidates_deep=160,
    z3_candidates=36,
    z3_candidates_deep=200,
    candidate_budget_per_route=900,
    crossing_policy='strict',
    group_order_legacy=['SW', 'ES', 'NW', 'EN', 'NS', 'EW'],
    group_order_opposite_first=['NS', 'EW', 'EN', 'ES', 'SW', 'NW'],
)


def attempt_route(frame, index, oracle, cfg, budget=None):
    """Try to place one route from the R=40 candidate families."""
    budget = budget or cfg['candidate_budget_per_route']
    reasons = Counter()
    blocker_counts = Counter()
    evaluated = 0
    phases = (False,) if cfg.get('no_deep') else (False, True)
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
                bends = sum(1 for primitive in prepared.prims if primitive.kind == 'arc')
                return RouteResult(frame.route_id, candidate['family'],
                                   candidate['params'], world, prepared,
                                   prepared.length, len(result.crossings),
                                   evaluated - 1, bends), None
            reasons[result.reason or 'invalid'] += 1
            blocker_counts.update(result.blockers)
        if evaluated >= budget:
            break
    failure = dict(route_id=frame.route_id,
                   reason='no_legal_candidate' if evaluated else 'no_candidate_generated',
                   evaluated=evaluated,
                   candidate_evaluations=extra_evaluations(index),
                   rejection_counts=dict(reasons),
                   blockers=dict(blocker_counts))
    return None, failure


def extra_evaluations(index):
    return getattr(index, 'evaluations', 0)


class Router:
    """Sequential plane router (A/B/C) with the exact strict R=40 index."""

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
        if route_ids is None:
            order = build_order(self.routes, self.frames, strategy,
                                congestion=self.congestion, index=self.index,
                                oracle=self.oracle)
        else:
            order = list(route_ids)
        expected = {route['route_id'] for route in self.routes}
        if set(order) != expected or len(order) != len(expected):
            raise ValueError('strategy order must contain every route exactly once')
        for index, route_id in enumerate(order, 1):
            self._try_place(route_id)
            if index % 128 == 0:
                self.log(f'{strategy.get("name", "?")}: attempted {index}/{len(order)} '
                         f'accepted={len(self.accepted)} '
                         f'evals={self.index.evaluations} '
                         f'elapsed={time.perf_counter() - started:.1f}s')
        return dict(strategy=strategy.get('name'), attempted=len(order),
                    accepted=len(self.accepted),
                    evaluations=self.index.evaluations,
                    duration_seconds=time.perf_counter() - started)

    # -- rip-up and reroute ------------------------------------------------
    def ripup(self, max_rounds=6, blockers_per_route=3, budget_seconds=None):
        started = time.perf_counter()
        improvements = 0
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
                saved = {}
                for blocker in blockers:
                    saved[blocker] = self.accepted.pop(blocker)
                    self._remove(blocker)
                success = self._try_place(route_id)
                rerouted = {}
                if success:
                    for blocker in blockers:
                        if self._try_place(blocker):
                            rerouted[blocker] = True
                            continue
                        success = False
                        break
                if success:
                    improvements += 1
                    progress += 1
                    continue
                self.accepted.pop(route_id, None)
                self._remove(route_id)
                for blocker in list(rerouted):
                    self.accepted.pop(blocker, None)
                    self._remove(blocker)
                self.failed.pop(route_id, None)
                for blocker, result in saved.items():
                    self.failed.pop(blocker, None)
                    if blocker in self.accepted:
                        self._remove(blocker)
                    self.accepted[blocker] = result
                    self._add(result)
                if route_id not in self.accepted:
                    self.failed.setdefault(route_id, dict(
                        route_id=route_id, reason='no_legal_candidate', evaluated=0,
                        rejection_counts={}, blockers={}))
            self.log(f'ripup round {round_index + 1}: committed={improvements} '
                     f'progress={progress} accepted={len(self.accepted)} '
                     f'failed={len(self.failed)}')
            if progress == 0:
                break
        return dict(rounds=max_rounds, improvements=improvements,
                    duration_seconds=time.perf_counter() - started)

    def _pick_blockers(self, route_id, limit):
        failure = self.failed.get(route_id) or {}
        counts = failure.get('blockers') or {}
        pairs = [(int(rid), count) for rid, count in counts.items()
                 if int(rid) in self.accepted]
        pairs.sort(key=lambda item: -item[1])
        return [rid for rid, _count in pairs[:limit]]

    # -- audit -------------------------------------------------------------
    def final_audit(self):
        audit = D56Index(width=self.cfg['width'], gap=self.cfg['gap'],
                         sagitta=self.cfg['sagitta'],
                         min_cross_angle_deg=self.cfg['min_cross_angle_deg'],
                         crossing_policy=self.cfg['crossing_policy'])
        for rid, result in self.accepted.items():
            audit.add(rid, result.prepared)
        removed = []
        for rid, result in list(self.accepted.items()):
            evaluation = audit.evaluate(result.prepared, exclude=[rid])
            if not evaluation.valid:
                removed.append(dict(route_id=rid, reason=evaluation.reason,
                                    blockers=list(evaluation.blockers)[:5]))
        for entry in removed:
            self.accepted.pop(entry['route_id'], None)
            self._remove(entry['route_id'])
            self.failed[entry['route_id']] = dict(
                route_id=entry['route_id'], reason='final_audit_removed',
                evaluated=0, rejection_counts={},
                blockers={str(b): 1 for b in entry['blockers']})
        return removed

    def summary(self):
        return dict(accepted=len(self.accepted), failed=len(self.failed),
                    evaluations=self.index.evaluations,
                    elapsed_seconds=time.perf_counter() - self.start)
