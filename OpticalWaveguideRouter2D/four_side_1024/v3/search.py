"""V3 sequential D56 routing engine (A/B/C) for the mixed same/opposite/adjacent planes.

Reuses the proven FSLW/previous-round machinery (exact incremental strict index,
canonical frames, oracle set, transactional rip-up) and only replaces the candidate
dispatch by :mod:`four_side_1024.v3.candidates` (same-side U/hairpin families added).
"""
from __future__ import annotations

import time
from collections import Counter

from ..d56.index import prepare
from ..d56.search import RouteResult
from ..fslw.search import (DEFAULT_CFG as FSLW_DEFAULT_CFG, Router as FslwRouter,
                           extra_evaluations, static_endpoint_lines)
from . import config as C
from .candidates import FrameOracleSet, LineOracle, candidates  # noqa: F401

DEFAULT_CFG = dict(FSLW_DEFAULT_CFG)
DEFAULT_CFG.update(
    width=C.WIDTH_MM,
    gap=C.EDGE_GAP_MM,
    sagitta=C.SAGITTA_MM,
    min_radius_mm=C.RADIUS_MM,
    min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
    crossing_policy='strict',
    candidate_budget_per_route=900,
    same_candidates=40,
    same_candidates_deep=220,
)


def attempt_route(frame, index, oracle, cfg, budget=None):
    """Try to place one V3 route; returns ``(RouteResult | None, failure dict)``."""
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
                bends = sum(1 for primitive in prepared.prims
                            if primitive.kind == 'arc')
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


class Router(FslwRouter):
    """Sequential V3 plane router; only candidate dispatch / placement differ."""

    def __init__(self, frames, routes, cfg=None, log=print):
        merged = dict(DEFAULT_CFG)
        if cfg:
            merged.update(cfg)
        super().__init__(frames, routes, cfg=merged, log=log)

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
