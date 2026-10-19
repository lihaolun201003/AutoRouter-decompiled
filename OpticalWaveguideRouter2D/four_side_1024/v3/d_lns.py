"""Algorithm D for the V3-Huang mixed same/opposite/adjacent planes: global joint candidate selection + LNS.

This is deliberately *not* a re-ordering of A/B/C.  It works in three stages:

1. **Candidate pool** - for every one of the 1024 identities a set of legal D56
   paths is generated once, from an oracle seeded only with the static endpoint
   lines (i.e. independent of the greedy placement order).
2. **Global selection** - the exact ``strict`` single-layer index is used to pick
   the first compatible candidate for each identity in several different global
   orders, keeping the best solution by the layered objective
   (routed count -> crossings -> total length).
3. **LNS / batch rip-up** - a batch of already routed identities plus one or more
   unrouted ones is released *together*, a local conflict relation between their
   candidates is built and the batch is re-solved jointly (max placed count, then
   fewer crossings, then shorter).  A change is committed only when the layered
   objective improves, so previously routed paths can be re-chosen -- including the
   case "A, B, C are routed, D, E fail; re-choosing A, B, C lets D, E route".

Every accepted path is validated by the same exact strict index as A/B/C; no
radius, width, clearance, layer, endpoint or geometry-family rule is relaxed.
"""
from __future__ import annotations

import math
import random
import time

from .candidates import FrameOracleSet, candidates
from ..d56.index import D56Index
from .search import RouteResult, static_endpoint_lines

DEFAULTS = dict(
    pool_size=48,
    batch_max=10,
    batch_pool=6,
    restarts=2,
    lns_shares=(0.5, 0.5),        # fraction of the evaluation budget: restarts / LNS
    seed=20261019,
)


def describe(args):
    from . import config as C
    return dict(name='D_joint_candidate_lns', algorithm='D',
                radius_mm=C.RADIUS_MM, clearance_mm=C.CLEARANCE_MM,
                pool_size=getattr(args, 'd_pool', DEFAULTS['pool_size']),
                batch_max=getattr(args, 'd_batch', DEFAULTS['batch_max']),
                batch_pool=getattr(args, 'd_batch_pool', DEFAULTS['batch_pool']),
                pair_level_compatibility=True,
                joint_multi_route_replacement=True,
                objective=['routed_count', 'crossings', 'total_length'],
                seed=getattr(args, 'seed', DEFAULTS['seed']))


# --------------------------------------------------------------------- pool
def _candidate_key(primitives):
    return tuple((prim['kind'], round(prim['p0'][0], 6), round(prim['p0'][1], 6),
                  round(prim['p1'][0], 6), round(prim['p1'][1], 6))
                 for prim in primitives)


def pool_config():
    from .search import DEFAULT_CFG
    from . import config as C
    return dict(DEFAULT_CFG,
                u_candidates_shallow=36, u_candidates_deep=60, z_candidates=40,
                z3_candidates=60, z3_candidates_deep=90, z3_y_options=24,
                z3_x_options=24, z3_y_options_deep=36, z3_x_options_deep=36,
                z_track_samples=10)


def _extend_pool(router, pool, route_ids, limit=8, cap=160):
    """Append fresh candidates generated against the *current* oracle state.

    This is the "local candidate-set optimisation" of algorithm D: inside an LNS
    batch the released identities get new D56 paths derived from the geometry that
    is actually present now, so the joint re-selection is not limited to the
    initial static pool.
    """
    from .candidates import candidates
    from ..d56.index import prepare as prepare_route
    cfg = pool_config()
    added = 0
    for route_id in route_ids:
        entries = pool.get(route_id)
        if entries is None or len(entries) >= cap:
            continue
        frame = router.frames[route_id]
        oracle = router.oracles.oracle_for(frame)
        seen = {entry.get('_key') for entry in entries}
        extra = 0
        for candidate in candidates(frame, oracle, cfg, deep=True):
            primitives = frame.to_world(candidate['primitives'])
            key = _candidate_key(primitives)
            if key in seen:
                continue
            seen.add(key)
            prepared = prepare_route(primitives)
            entries.append(dict(primitives=primitives, prepared=prepared,
                                family=candidate['family'],
                                params=candidate['params'],
                                length=prepared.length,
                                bend_count=prepared.bend_count, _key=key))
            extra += 1
            added += 1
            if extra >= limit:
                break
    return added


def build_pool(frames, routes, args, log):
    """Generate the fixed candidate pool (per identity) for algorithm D."""
    cfg = pool_config()
    static_h, static_v = static_endpoint_lines(frames)
    oracles = FrameOracleSet(frames, static_h, static_v,
                             clearance=cfg['width'] + cfg['gap'])
    pool_size = int(getattr(args, 'd_pool', DEFAULTS['pool_size']))
    pool = {}
    started = time.perf_counter()
    total = 0
    from ..d56.index import prepare as prepare_route
    for count, route in enumerate(routes, 1):
        route_id = route['route_id']
        frame = frames[route_id]
        oracle = oracles.oracle_for(frame)
        entries = []
        seen = set()
        for candidate in candidates(frame, oracle, cfg,
                                    deep=bool(getattr(args, 'd_pool_deep', False))):
            if len(entries) >= pool_size:
                break
            primitives = frame.to_world(candidate['primitives'])
            key = _candidate_key(primitives)
            if key in seen:
                continue
            seen.add(key)
            prepared = prepare_route(primitives)
            entries.append(dict(primitives=primitives, prepared=prepared,
                                family=candidate['family'], params=candidate['params'],
                                length=prepared.length, bend_count=prepared.bend_count,
                                _key=key))
        pool[route_id] = entries
        total += len(entries)
        if count % 256 == 0:
            log(f'D pool: {count}/{len(routes)} identities, {total} candidates, '
                f'{time.perf_counter() - started:.1f}s')
    log(f'D pool complete: {total} candidates for {len(pool)} identities '
        f'({total / max(1, len(pool)):.1f}/identity) in {time.perf_counter() - started:.1f}s')
    return pool


def _accept(router, route_id, entry, family_label='D_joint'):
    result = RouteResult(route_id, entry['family'], entry['params'],
                         entry['primitives'], entry['prepared'], entry['length'],
                         0, 0, entry['bend_count'])
    _install(router, route_id, result)
    return result


def _remove(router, route_id):
    router.index.remove(route_id)
    try:
        router.oracles.remove(route_id)
    except Exception:
        pass
    router.accepted.pop(route_id, None)


def _install(router, route_id, result):
    router.index.add(route_id, result.prepared)
    router.oracles.add(route_id, result.prepared)
    router.accepted[route_id] = result
    router.failed.pop(route_id, None)


def _solution_of(router):
    return {route_id: result.candidate_index for route_id, result in router.accepted.items()}


def _score(router):
    crossings = sum(result.crossings for result in router.accepted.values())
    length = sum(result.length_mm for result in router.accepted.values())
    return (-len(router.accepted), crossings, length)


def greedy_restart(router, order, pool, args, budget, log, label):
    """Place identities in ``order`` choosing a pool candidate by a global criterion.

    ``d_select='min_cross'`` (default) evaluates up to ``d_probe`` candidates per
    identity and keeps the compatible one with the fewest crossings, then the
    shortest length; ``d_select='first'`` takes the first compatible candidate.
    """
    if router.accepted:
        for route_id in list(router.accepted):
            _remove(router, route_id)
    router.failed.clear()
    started = time.perf_counter()
    placed = 0
    probe = int(getattr(args, 'd_probe', 8))
    select = getattr(args, 'd_select', 'first')
    for count, route_id in enumerate(order, 1):
        if router.index.evaluations >= budget:
            break
        entries = pool[route_id]
        choice = None
        blockers = {}
        evaluated = 0
        best_key = None
        for position, entry in enumerate(entries):
            result = router.index.evaluate(entry['prepared'])
            evaluated += 1
            if result.valid:
                entry['_crossings'] = len(result.crossings)
                if select == 'first':
                    choice = (position, entry)
                    break
                key = (len(result.crossings), entry['length'])
                if best_key is None or key < best_key:
                    best_key = key
                    choice = (position, entry)
                if evaluated >= probe and select != 'first':
                    break
            else:
                for blocker in result.blockers:
                    blockers[blocker] = blockers.get(blocker, 0) + 1
                if evaluated >= probe and select != 'first':
                    break
        if choice is None:
            router.failed[route_id] = dict(route_id=route_id, reason='no_legal_candidate',
                                           evaluated=evaluated,
                                           rejection_counts={}, blockers=blockers)
            continue
        position, entry = choice
        _install(router, route_id, RouteResult(
            route_id, entry['family'], entry['params'], entry['primitives'],
            entry['prepared'], entry['length'], entry.get('_crossings', 0), position,
            entry['bend_count']))
        placed += 1
        if count % 256 == 0:
            log(f'D {label}: {count}/{len(order)} accepted={len(router.accepted)} '
                f'evals={router.index.evaluations} {time.perf_counter() - started:.1f}s')
    log(f'D {label} done: accepted={len(router.accepted)} evals={router.index.evaluations} '
        f'{time.perf_counter() - started:.1f}s')
    return dict(label=label, accepted=len(router.accepted),
                evals=router.index.evaluations,
                seconds=time.perf_counter() - started)


# ---------------------------------------------------------------------- LNS
class _PairChecker:
    """Pair-level compatibility between two prepared candidate routes."""

    __slots__ = ('index', 'checks')

    def __init__(self, width=None, gap=None, sagitta=None):
        from ..d56.index import D56Index
        from . import config as C
        width = C.WIDTH_MM if width is None else width
        gap = C.EDGE_GAP_MM if gap is None else gap
        sagitta = C.SAGITTA_MM if sagitta is None else sagitta
        self.index = D56Index(width=width, gap=gap, sagitta=sagitta,
                              crossing_policy='strict')
        self.checks = 0

    def compatible(self, first, second):
        from ..conflicts import _bbox_distance
        from . import config as C
        if _bbox_distance(first.bounds, second.bounds) >= C.CLEARANCE_MM:
            return True
        self.checks += 1
        index = self.index
        index.clear()
        index.add(1, first)
        result = index.evaluate(second)
        index.clear()
        return result.valid


def _bbox_far(first, second):
    from ..conflicts import _bbox_distance
    from . import config as C
    return _bbox_distance(first.bounds, second.bounds) >= C.CLEARANCE_MM


def solve_batch(router, batch_ids, pool, options, checker, log, random_source=None):
    """Jointly re-select a batch of identities (DFS over their candidate options)."""
    fixed = router.index
    removed = [route_id for route_id in batch_ids if route_id in router.accepted]
    saved = {route_id: router.accepted.pop(route_id) for route_id in removed}
    for route_id in removed:
        fixed.remove(route_id)
        try:
            router.oracles.remove(route_id)
        except Exception:
            pass
    _extend_pool(router, pool,
                 [route_id for route_id in batch_ids if route_id not in router.accepted],
                 limit=int(DEFAULTS.get('fresh_candidates', 8)))
    try:
        candidates_by_route = {}
        crossings_by_candidate = {}
        fixed_valid = {}
        for route_id in batch_ids:
            entries = pool[route_id][:options]
            rows = []
            for position, entry in enumerate(entries):
                result = fixed.evaluate(entry['prepared'])
                if not result.valid:
                    continue
                rows.append(position)
                crossings_by_candidate[(route_id, position)] = len(result.crossings)
            candidates_by_route[route_id] = rows
            fixed_valid[route_id] = True
        # local conflict relation between options of different batch identities
        compat = {}
        for offset, first in enumerate(batch_ids):
            for second in batch_ids[offset + 1:]:
                for position_a in candidates_by_route[first]:
                    entry_a = pool[first][position_a]
                    for position_b in candidates_by_route[second]:
                        entry_b = pool[second][position_b]
                        if _bbox_far(entry_a['prepared'], entry_b['prepared']):
                            continue
                        if checker.compatible(entry_a['prepared'], entry_b['prepared']):
                            continue
                        compat[(first, position_a, second, position_b)] = False
                        compat[(second, position_b, first, position_a)] = False
        order = sorted(batch_ids, key=lambda rid: (len(candidates_by_route[rid]),
                                                   -len(pool[rid][:options])))
        if random_source is not None:
            random_source.shuffle(order)
        best = dict(count=-1, crossings=0, length=0.0, choice={})
        current = {}

        def evaluate_choice():
            count = 0
            crossings = 0
            length = 0.0
            for route_id, position in current.items():
                count += 1
                crossings += crossings_by_candidate[(route_id, position)]
                length += pool[route_id][position]['length']
            return count, crossings, length

        def better(count, crossings, length):
            if count != best['count']:
                return count > best['count']
            if crossings != best['crossings']:
                return crossings < best['crossings']
            return length < best['length'] - 1e-9

        nodes = [0]
        node_limit = 40000

        def dfs(position):
            nodes[0] += 1
            if nodes[0] > node_limit:
                return
            count, crossings, length = evaluate_choice()
            if better(count, crossings, length):
                best.update(count=count, crossings=crossings, length=length,
                            choice=dict(current))
            if position >= len(order):
                return
            route_id = order[position]
            # upper bound: remaining identities cannot beat the best count
            if count + (len(order) - position) < best['count']:
                return
            for candidate_position in candidates_by_route[route_id]:
                entry = pool[route_id][candidate_position]
                conflict = False
                for other_id, other_position in current.items():
                    if compat.get((route_id, candidate_position, other_id,
                                   other_position)) is False:
                        conflict = True
                        break
                if conflict:
                    continue
                current[route_id] = candidate_position
                dfs(position + 1)
                current.pop(route_id, None)
                if nodes[0] > node_limit:
                    return
            dfs(position + 1)

        dfs(0)
    finally:
        for route_id in removed:
            if route_id in router.accepted:
                _remove(router, route_id)
    before_count = len(saved)
    before_crossings = sum(result.crossings for result in saved.values())
    before_length = sum(result.length_mm for result in saved.values())
    old = (before_count, before_crossings, before_length)

    def is_better(candidate, reference):
        if candidate[0] != reference[0]:
            return candidate[0] > reference[0]
        if candidate[1] != reference[1]:
            return candidate[1] < reference[1]
        return candidate[2] < reference[2] - 1e-9

    def revert():
        for route_id in list(best['choice']):
            if route_id in router.accepted:
                _remove(router, route_id)
        for route_id, result in saved.items():
            _install(router, route_id, result)

    def measure(chosen):
        """Exact crossings/length of the committed batch under the full index."""
        crossings = 0
        length = 0.0
        for route_id in chosen:
            result = router.accepted[route_id]
            evaluation = router.index.evaluate(result.prepared, exclude=[route_id])
            result.crossings = len(evaluation.crossings)
            crossings += result.crossings
            length += result.length_mm
        return len(chosen), crossings, length

    heuristic = (best['count'], best['crossings'], best['length'])
    if not is_better(heuristic, old):
        revert()
        return dict(committed=before_count, best_count=best['count'],
                    reverted=True, choice={})
    for route_id, position in best['choice'].items():
        entry = pool[route_id][position]
        _install(router, route_id, RouteResult(
            route_id, entry['family'], entry['params'], entry['primitives'],
            entry['prepared'], entry['length'],
            crossings_by_candidate[(route_id, position)], position,
            entry['bend_count']))
    measured = measure(best['choice'])
    if not is_better(measured, old):
        revert()
        return dict(committed=before_count, best_count=best['count'],
                    reverted=True, choice={})
    for route_id in batch_ids:
        if route_id not in router.accepted:
            router.failed.setdefault(route_id, dict(route_id=route_id,
                                                    reason='no_legal_candidate',
                                                    evaluated=0,
                                                    rejection_counts={}, blockers={}))
    return dict(committed=measured[0], crossings=measured[1],
                length=measured[2], before=old, candidates=saved,
                choice=dict(best['choice']))


def _pick_batch(router, pool, seed_route, batch_max, options):
    """Count-oriented batch: seed + the blockers of its *easiest* candidate."""
    entries = pool[seed_route][:options]
    best_blockers = None
    for entry in entries:
        result = router.index.evaluate(entry['prepared'])
        if result.valid:
            best_blockers = []
            break
        blockers = [rid for rid in result.blockers if rid in router.accepted]
        if best_blockers is None or len(blockers) < len(best_blockers):
            best_blockers = blockers
    if best_blockers is None:
        failure = router.failed.get(seed_route) or {}
        best_blockers = [int(rid) for rid in (failure.get('blockers') or {})
                         if int(rid) in router.accepted]
    batch = [seed_route]
    for route_id in best_blockers:
        if route_id in router.accepted and route_id not in batch:
            batch.append(route_id)
        if len(batch) >= batch_max:
            break
    return batch


def _neighbour_batch(router, seed_route, batch_max):
    """Quality-oriented batch: an accepted route plus its spatial neighbours."""
    result = router.accepted.get(seed_route)
    if result is None:
        return [seed_route]
    counts = {}
    for _index, other_id, _other_index in router.index._nearby_pairs(result.prepared):
        if other_id != seed_route and other_id in router.accepted:
            counts[other_id] = counts.get(other_id, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: -item[1])
    batch = [seed_route]
    for route_id, _count in ranked:
        batch.append(route_id)
        if len(batch) >= batch_max:
            break
    return batch


def optimise(router, routes, frames, args=None, deadline=None, log=print):
    """Run the full D pipeline on ``router`` (mutated in place)."""
    args = args or type('Args', (), {})()
    pool_size = int(getattr(args, 'd_pool', DEFAULTS['pool_size']))
    batch_max = int(getattr(args, 'd_batch', DEFAULTS['batch_max']))
    batch_pool = int(getattr(args, 'd_batch_pool', DEFAULTS['batch_pool']))
    restarts = int(getattr(args, 'd_restarts', DEFAULTS['restarts']))
    seed = int(getattr(args, 'seed', DEFAULTS['seed']))
    budget = int(getattr(args, 'eval_budget', 0) or 0)
    if budget <= 0:
        budget = 800000
    evaluation_start = router.index.evaluations
    started = time.perf_counter()
    log(f'D start: pool_size={pool_size} restarts={restarts} batch_max={batch_max} '
        f'batch_pool={batch_pool} eval_budget={budget} deadline_set={deadline is not None}')
    pool = build_pool(frames, routes, args, log)
    route_by_id = {route['route_id']: route for route in routes}
    route_ids = [route['route_id'] for route in routes]
    rng = random.Random(seed)

    adjacent_first = ['NN', 'SS', 'EE', 'WW',
                      'NE', 'NW', 'ES', 'SW', 'NS', 'EW']
    by_pair = {}
    for route in routes:
        by_pair.setdefault(route['pair'], []).append(route['route_id'])
    order_b = []
    for pair in adjacent_first:
        order_b.extend(sorted(by_pair.get(pair, []),
                              key=lambda rid: (-frames[rid].p[0],)))
    order_random = list(route_ids)
    rng.shuffle(order_random)

    split = int(budget * DEFAULTS['lns_shares'][0])
    restart_budget = evaluation_start + split
    history = []
    best_state = None
    for restart in range(max(1, restarts)):
        if router.index.evaluations >= restart_budget:
            break
        order = order_b if restart == 0 else order_random
        info = greedy_restart(router, order, pool, args, restart_budget, log,
                              f'restart{restart}')
        for route_id in route_ids:
            if route_id not in router.accepted and route_id not in router.failed:
                router.failed[route_id] = dict(route_id=route_id,
                                               reason='eval_budget_exhausted',
                                               evaluated=0, rejection_counts={},
                                               blockers={})
        score = _score(router)
        info['score'] = score
        history.append(info)
        if best_state is None or score < best_state[0]:
            best_state = (score, _solution_of(router))
            log(f'D restart{restart} is the new best: {score}')
    if best_state is not None:
        if router.accepted:
            for route_id in list(router.accepted):
                _remove(router, route_id)
        for route_id, position in best_state[1].items():
            entry = pool[route_id][position]
            _install(router, route_id, RouteResult(
                route_id, entry['family'], entry['params'], entry['primitives'],
                entry['prepared'], entry['length'], entry.get('_crossings', 0),
                position, entry['bend_count']))
        for route_id in route_ids:
            if route_id not in router.accepted:
                router.failed.setdefault(route_id, dict(route_id=route_id,
                                                        reason='no_legal_candidate',
                                                        evaluated=0,
                                                        rejection_counts={}, blockers={}))
    else:
        for route_id in route_ids:
            if route_id not in router.accepted:
                router.failed.setdefault(route_id, dict(route_id=route_id,
                                                        reason='budget_exhausted',
                                                        evaluated=0,
                                                        rejection_counts={}, blockers={}))
    log(f'D after restarts: best={_score(router)} evals={router.index.evaluations}')
    # exact crossings for the restored solution (needed by the LNS objective)
    for route_id in list(router.accepted):
        result = router.accepted[route_id]
        evaluation = router.index.evaluate(result.prepared, exclude=[route_id])
        result.crossings = len(evaluation.crossings)
    baseline_score = _score(router)
    log(f'D baseline score (routed, crossings, length)={baseline_score}')

    checker = _PairChecker()
    batch_size_budget = max(1, int(getattr(args, 'd_batches', 400)))
    attempts = 0
    count_improvements = 0
    quality_improvements = 0
    lns_started = time.perf_counter()
    while attempts < batch_size_budget:
        if router.index.evaluations + checker.checks >= budget:
            log('D LNS: evaluation budget exhausted')
            break
        if deadline is not None and time.perf_counter() > deadline:
            log('D LNS: wall-clock deadline reached')
            break
        attempts += 1
        unrouted = [route_id for route_id in route_ids if route_id not in router.accepted]
        count_mode = bool(unrouted) and (attempts % 3 != 0)
        if count_mode:
            seed_route = unrouted[(attempts // 3) % len(unrouted)]
            batch = _pick_batch(router, pool, seed_route, batch_max, batch_pool)
        else:
            accepted_ids = list(router.accepted)
            if not accepted_ids:
                continue
            seed_route = accepted_ids[rng.randrange(len(accepted_ids))]
            batch = _neighbour_batch(router, seed_route, batch_max)
        if len(batch) < 2:
            continue
        before = sum(1 for route_id in batch if route_id in router.accepted)
        before_metrics = (len(router.accepted),
                          sum(result.crossings for result in router.accepted.values()),
                          sum(result.length_mm for result in router.accepted.values()))
        info = solve_batch(router, batch, pool, batch_pool, checker, log,
                           random_source=rng if attempts % 5 == 0 else None)
        if not info.get('reverted'):
            after_metrics = (len(router.accepted),
                             sum(result.crossings for result in router.accepted.values()),
                             sum(result.length_mm for result in router.accepted.values()))
            if after_metrics[0] > before_metrics[0]:
                count_improvements += 1
            elif after_metrics[0] == before_metrics[0]:
                quality_improvements += 1
        if attempts % 25 == 0:
            log(f'D LNS {attempts}/{batch_size_budget}: accepted={len(router.accepted)} '
                f'batch={len(batch)} evals={router.index.evaluations} '
                f'pairchecks={checker.checks} score={_score(router)} '
                f'elapsed={time.perf_counter() - lns_started:.1f}s')
    final_score = _score(router)
    log(f'D LNS done: attempts={attempts} count_improvements={count_improvements} '
        f'quality_improvements={quality_improvements} accepted={len(router.accepted)} '
        f'score={final_score} evals={router.index.evaluations} '
        f'pairchecks={checker.checks}')
    for route_id in route_ids:
        if route_id not in router.accepted:
            router.failed.setdefault(route_id, dict(route_id=route_id,
                                                    reason='no_legal_candidate',
                                                    evaluated=0,
                                                    rejection_counts={}, blockers={}))
    total_evals = router.index.evaluations - evaluation_start
    return dict(algorithm='D_joint_candidate_lns', attempted=len(route_ids),
                accepted=len(router.accepted),
                evaluations=total_evals, pair_checks=checker.checks,
                restarts=history, baseline_score=list(baseline_score),
                final_score=list(final_score),
                lns_attempts=attempts,
                lns_count_improvements=count_improvements,
                lns_quality_improvements=quality_improvements,
                stop_reason='budget' if (router.index.evaluations + checker.checks) >= budget
                else 'completed',
                duration_seconds=time.perf_counter() - started)
