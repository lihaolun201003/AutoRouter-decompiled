"""Incremental exact-conflict engine with a selectable crossing-zone policy.

Provides the same result-dict contract as ``four_side_1024.conflicts.ConflictIndex``
so it can be plugged into the instrumented searcher for controlled experiments:

    engine = PolicyIndex('primitive_pair')
    engine.add(rid, primitives)      # accepted route
    result = engine.evaluate(primitives)   # candidate

Only the crossing exemption arclength changes (see crossing_policy); radius,
width, clearance, overlap/touch/endpoint/crossing rules are unchanged.

For speed the broad phase uses exact route bounding boxes: a candidate/route
pair whose axis-aligned boxes are farther apart than the required clearance can
never violate anything under any policy and is skipped by a vectorised test.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import crossing_policy as P

POLICY_REASON_MAP = {
    'overlap': 'overlap_pairs',
    'touch': 'touch_pairs',
    'multiple_crossings_same_primitives': 'crossing_zone_overlap_pairs',
    'window_overlap_after_correction': 'crossing_zone_overlap_pairs',
    'tangential_or_tight_crossing': 'touch_pairs',
    'spacing': 'spacing_pairs',
    'spacing_no_crossing': 'spacing_pairs',
    'spacing_outside_exact_window': 'spacing_pairs',
}


class PolicyIndex:
    def __init__(self, policy='primitive_pair', clearance=0.175):
        if policy not in P.POLICIES:
            raise ValueError('unknown policy: ' + policy)
        self.policy = policy
        self.fn = P.POLICIES[policy]
        self.clearance = clearance
        self.routes = {}
        self._ids = []
        self._bounds = np.empty((0, 4))
        self.evaluations = 0
        self.checked_pairs = 0

    def __len__(self):
        return len(self.routes)

    def add(self, rid, primitives):
        prepared = P.prepare(primitives)
        self.routes[rid] = prepared
        self._ids.append(rid)
        self._bounds = np.vstack([self._bounds, np.asarray(prepared.exact_bounds, dtype=float).reshape(1, 4)])

    def remove(self, rid):
        if rid not in self.routes:
            return
        del self.routes[rid]
        position = self._ids.index(rid)
        self._ids.pop(position)
        self._bounds = np.delete(self._bounds, position, axis=0)

    def evaluate(self, primitives, exclude=None, stop_on_invalid=True):
        candidate = P.prepare(primitives)
        excluded = set() if exclude is None else (set(exclude) if isinstance(exclude, (list, tuple, set))
                                                  else {exclude})
        result = dict(valid=True, spacing_pairs=[], overlap_pairs=[], touch_pairs=[],
                      crossing_zone_overlap_pairs=[], self_intersections=0, self_overlaps=0,
                      self_spacing_violations=0, discontinuities=candidate.discontinuities,
                      crossings=[], minimum_non_crossing_centerline_mm=None,
                      checked_pairs=0, clearance_mm=self.clearance, layer=0)
        if candidate.discontinuities:
            result['valid'] = False
            if stop_on_invalid:
                return result
        if len(self._ids) == 0:
            return result
        x0, y0, x1, y1 = candidate.exact_bounds
        pad = self.clearance
        dx = np.maximum(self._bounds[:, 0] - x1 - pad, x0 - pad - self._bounds[:, 2])
        dy = np.maximum(self._bounds[:, 1] - y1 - pad, y0 - pad - self._bounds[:, 3])
        near = np.flatnonzero((dx <= 0) & (dy <= 0))
        self.evaluations += 1
        for position in near:
            other_id = self._ids[int(position)]
            if other_id in excluded:
                continue
            other = self.routes[other_id]
            result['checked_pairs'] += 1
            self.checked_pairs += 1
            checked = self.fn(candidate, other)
            if checked['valid']:
                continue
            key = POLICY_REASON_MAP.get(checked['reason'])
            if key is not None:
                result[key].append(other_id)
            if checked.get('distance') is not None:
                old = result['minimum_non_crossing_centerline_mm']
                result['minimum_non_crossing_centerline_mm'] = (
                    checked['distance'] if old is None else min(old, checked['distance']))
            result['valid'] = False
            if stop_on_invalid:
                return result
        return result
