"""Group-level (strict C4) router for the new manual connectivity.

The C4 atomic group policy is the unchanged V3/V4 policy
(:class:`four_side_1024.v3c4.c4.GroupRouter`): only the representative connection
of a rotation orbit is searched; the other three paths are its exact 90/180/270 deg
rotations (with traversal reversal when needed); all four are evaluated jointly
and committed atomically.

Two adapters are added for the new topology:

* ``frame`` groups (opposite / adjacent connections) use the frozen candidate
  generators unchanged (:func:`four_side_1024.v2opt.search.candidates_for`);
* ``same`` groups (both ports on one board side - present on both z planes in the
  new manual design) use the existing R15 same-side U-turn geometry
  (:mod:`four_side_1024.r15.u_geometry`, quarter-pair family, radius never shrunk).
"""
from __future__ import annotations

import time
from collections import Counter

from ..v3c4.c4 import GroupRouter, order_groups as _order_groups_frame

#: kind priority used by the "easy" orders (lower = routed earlier)
KIND_RANK = {
    'easy': {'opposite': 0, 'adjacent': 1, 'same': 2},
    'adjacent_first': {'adjacent': 0, 'opposite': 1, 'same': 2},
    'opposite_first': {'opposite': 0, 'adjacent': 1, 'same': 2},
    'same_first': {'same': 0, 'opposite': 1, 'adjacent': 2},
    'same_last': {'opposite': 0, 'adjacent': 1, 'same': 3},
}
#: same-side U bulge ladder: exactly the V4-C4 validated ladder (2 mm steps up to
#: 120 mm plus the three odd shallow values).  The shipped
#: ``r15.u_geometry.u_candidates`` representative ladder only emits four bulges,
#: which cannot nest many same-side U groups along one board edge; the V4 round
#: already solved the same dense-nesting problem with this ladder (the geometry
#: family and the radius audit are unchanged).
BULGE_LADDER = [2.0 * index for index in range(0, 61)] + [1.0, 3.0, 5.0]
INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0),
          'E': (-1.0, 0.0), 'W': (1.0, 0.0)}


def group_difficulty(group, state):
    """Difficulty estimate of one group in the new mixed topology."""
    rep = state.blocks[group['route_ids'][0]]
    eps = state.endpoints if hasattr(state, 'endpoints') else state.state.endpoints
    sx, sy = (float(v) for v in eps[rep['source_endpoint']]['routing_xy'])
    tx, ty = (float(v) for v in eps[rep['target_endpoint']]['routing_xy'])
    dx, dy = abs(tx - sx), abs(ty - sy)
    kind = group['kind']
    if kind == 'opposite':
        # new-design opposite connections are axis aligned (0 lateral shift)
        return dict(dx=dx, dy=dy, d=min(dx, dy))
    if kind == 'adjacent':
        # direct L needs both legs >= R; larger min leg is easier
        return dict(dx=dx, dy=dy, d=min(dx, dy))
    # same-side U: larger separation gives a larger middle straight
    separation = dy if rep['source_side'] in 'NS' else dx
    return dict(dx=dx, dy=dy, d=separation)


def order_groups(groups, state, mode='easy'):
    """Order groups for the sequential C4 commit (mixed relation kinds)."""
    if mode == 'csv':
        return sorted(groups, key=lambda g: g['group_id'])
    if mode == 'frame_easy':
        return _order_groups_frame(groups, state.blocks, mode='easy')
    ranks = KIND_RANK.get(mode)
    if ranks is None:
        raise ValueError(f'unknown group order {mode}')
    metrics = {g['group_id']: group_difficulty(g, state) for g in groups}

    def key(group):
        metric = metrics[group['group_id']]
        kind = group['kind']
        rank = ranks.get(kind, 9)
        if kind == 'opposite':
            difficulty = metric['d']          # 0 shift first
        elif kind == 'adjacent':
            difficulty = -metric['d']         # larger legs first
        else:
            difficulty = -metric['d']         # larger separation first
        return (rank, difficulty, group['group_id'])

    return sorted(groups, key=key)


class ManualGroupRouter(GroupRouter):
    """C4 group router with the same-side U front end added."""

    def __init__(self, state, groups, all_groups=None, log=print):
        super().__init__(state, groups, all_groups=all_groups, log=log)

    # -- same-side U candidates -------------------------------------------
    def same_side_candidates(self, route_ids):
        """Legal R=15 same-side U candidates (dense V4-C4 bulge ladder)."""
        import math

        from ..fslw import config as C
        from ..legacy_geometry import transform_primitives
        from ..r15 import u_geometry as UG

        rep = self.blocks[int(route_ids[0])]
        eps = self.state.endpoints
        p = tuple(float(v) for v in eps[rep['source_endpoint']]['routing_xy'])
        q = tuple(float(v) for v in eps[rep['target_endpoint']]['routing_xy'])
        side = rep['source_side']
        inward = INWARD[side]
        start_dir = inward
        end_dir = (-inward[0], -inward[1])
        frame, _errors = UG._canonical_frame(p, q, start_dir, end_dir,
                                             C.BOARD_MM, C.WIDTH_MM)
        if frame is None:
            return []
        radius = float(C.RADIUS_MM)
        separation = frame['separation_mm']
        if separation < 2.0 * radius - 1e-9:
            return []
        middle = separation - 2.0 * radius
        candidates = []
        for bulge in BULGE_LADDER:
            if bulge < 0.0:
                continue
            canonical = UG._quarter_pair(frame['p_canonical'],
                                         frame['q_canonical'], radius,
                                         float(bulge), middle)
            world = transform_primitives(canonical, frame['transform'],
                                         inverse=True)
            if not UG._validate(world, frame, radius, C.WIDTH_MM):
                continue
            length = 0.0
            for primitive in world:
                if primitive['kind'] == 'line':
                    length += math.dist(primitive['p0'], primitive['p1'])
                else:
                    length += abs(float(primitive['sweep'])) * float(
                        primitive['radius'])
            candidates.append(dict(
                family='U_QUARTER_PAIR', primitives=world,
                params=dict(bulge_mm=float(bulge),
                            middle_straight_mm=float(middle),
                            separation_mm=float(separation),
                            radius_mm=radius),
                length_mm=length, separation_mm=float(separation)))
        return candidates

    # -- one group ---------------------------------------------------------
    def attempt_group(self, group, budget, candidate_iterator=None,
                      sort_key=None, same_candidates=None):
        if group['kind'] == 'same':
            return self._attempt_same_group(group, budget,
                                            candidates=same_candidates)
        return super().attempt_group(group, budget,
                                     candidate_iterator=candidate_iterator,
                                     sort_key=sort_key)

    def _attempt_same_group(self, group, budget, candidates=None):
        from ..d56.index import prepare
        from ..d56.search import RouteResult

        started = time.perf_counter()
        ids = [int(rid) for rid in group['route_ids']]
        if candidates is None:
            try:
                candidates = self.same_side_candidates(ids)
            except ValueError:
                candidates = []
        evaluated = 0
        reasons = Counter()
        families = Counter()
        blockers = Counter()
        for candidate in candidates:
            if evaluated >= budget:
                reasons['candidate_budget_exhausted'] += 1
                break
            evaluated += 1
            raw_family = str(candidate['family'])
            family = raw_family if raw_family.startswith('U_') else 'U_' + raw_family.upper()
            families[family] += 1
            try:
                oriented, prepared = self.build_quad(group, candidate['primitives'])
            except ValueError:
                reasons['quad_orientation'] += 1
                continue
            ok = True
            for rid, prep in zip(ids, prepared):
                evaluation = self.state.index.evaluate(prep)
                if not evaluation.valid:
                    reasons[evaluation.reason or 'invalid'] += 1
                    blockers.update(evaluation.blockers)
                    ok = False
                    break
            if not ok:
                continue
            for rid, prep in zip(ids, prepared):
                self.state.index.add(rid, prep)
            quad_ok = True
            for rid, prep in zip(ids, prepared):
                evaluation = self.state.index.evaluate(prep, exclude=[rid])
                if not evaluation.valid:
                    reasons['quad_' + (evaluation.reason or 'invalid')] += 1
                    quad_ok = False
                    break
            for rid in ids:
                self.state.index.remove(rid)
            if not quad_ok:
                continue
            results = []
            params = dict(candidate.get('params') or {})
            params['radius_mm'] = float(candidate.get('radius_mm', 15.0))
            params['separation_mm'] = float(candidate.get('separation_mm', 0.0))
            for rid, prims, prep in zip(ids, oriented, prepared):
                results.append(RouteResult(
                    rid, family, dict(params), prims, prep, prep.length, 0,
                    evaluated - 1, prep.bend_count))
            stats = dict(evaluated=evaluated, generated=len(candidates),
                         families=dict(families), reasons=dict(reasons),
                         seconds=time.perf_counter() - started)
            return results, None, stats
        failure = dict(group_id=group['group_id'],
                       reason='no_legal_quad' if evaluated else 'no_candidate_generated',
                       evaluated=evaluated, candidate_evaluations=evaluated,
                       rejection_counts=dict(reasons), blockers=dict(blockers),
                       families=dict(families),
                       seconds=time.perf_counter() - started)
        return None, failure, dict(evaluated=evaluated, generated=len(candidates or []),
                                   families=dict(families), reasons=dict(reasons),
                                   seconds=time.perf_counter() - started)

    # -- sequential pass (oracle guard for same-side groups) --------------
    def route_all(self, order, budget, deadline=None, checkpoint_fn=None,
                  checkpoint_every=16, same_candidates_cache=None):
        details = []
        applied = []
        started = time.perf_counter()
        for position, group in enumerate(order, 1):
            if deadline is not None and time.perf_counter() > deadline:
                self.log(f'C4 sequential: time budget exhausted at '
                         f'{position - 1}/{len(order)}')
                break
            if group['kind'] == 'same':
                results, failure, stats = self.attempt_group(
                    group, budget,
                    same_candidates=(same_candidates_cache or {}).get(
                        group['group_id']))
            else:
                results, failure, stats = self.attempt_group(group, budget)
            if results is not None:
                self.commit_group(group, results)
                applied.append(group['group_id'])
                details.append(dict(group_id=group['group_id'], found=True,
                                    kind=group['kind'],
                                    families=stats['families'],
                                    evaluated=stats['evaluated'],
                                    seconds=round(stats['seconds'], 3)))
            else:
                self.fail_group(group, failure)
                details.append(dict(group_id=group['group_id'], found=False,
                                    kind=group['kind'],
                                    reason=failure['reason'],
                                    evaluated=failure['evaluated'],
                                    rejection_counts=failure['rejection_counts'],
                                    blockers=failure['blockers'],
                                    families=failure.get('families'),
                                    seconds=round(failure['seconds'], 3)))
            if checkpoint_fn is not None and position % checkpoint_every == 0:
                checkpoint_fn(self, position)
            if position % 8 == 0:
                self.log(f'C4 sequential: {position}/{len(order)} groups '
                         f'applied={len(applied)} routed_routes='
                         f'{len(self.state.accepted)} '
                         f'elapsed={time.perf_counter() - started:.1f}s')
        summary = dict(budget=int(budget), attempted=len(details),
                       applied_groups=len(applied), applied_group_ids=applied,
                       routed_routes=len(self.state.accepted),
                       seconds=round(time.perf_counter() - started, 2))
        return details, summary

    def prime_same_candidates(self):
        """Pre-generate U candidates per same-side group (deterministic)."""
        cache = {}
        for group in self.all_groups:
            if group['kind'] != 'same':
                continue
            cache[group['group_id']] = self.same_side_candidates(
                group['route_ids'])
        return cache
