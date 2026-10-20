"""Candidate-evaluation engine of the V2 optimisation round.

The engine is deliberately a thin layer over the frozen acceptance machinery:

* candidates come from :mod:`four_side_1024.v2opt.candext` (same D56 primitives);
* the accept/reject decision is the unchanged exact strict
  :class:`four_side_1024.d56.index.D56Index`;
* a route is only accepted when ``index.evaluate`` returns ``valid=True``,
  exactly like the historical router.

On top of that it exposes the two experiment primitives of this round:

* ``sweep_attempt`` / ``parallel_sweep`` - independent single-route insertion
  tests against a frozen base layout (task 5.4, budget ladder 200/400/800/1600);
* ``sequential_commit`` - one greedy pass over pending failed routes that
  commits every legal insertion (E1: expanded candidates, no R&R).
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from ..d56.index import prepare
from ..d56.search import RouteResult
from ..fslw import config as C
from . import candext
from . import config as V
from .core import LayoutState, router_cfg


def candidates_for(frame, oracle, kind_stats=None, cfg=None, use_expanded=True):
    if use_expanded:
        if frame.kind == 'opposite':
            yield from candext.candidates_opposite(frame, oracle, stats=kind_stats)
        elif frame.kind == 'adjacent':
            yield from candext.candidates_adjacent(frame, oracle, stats=kind_stats)
        else:  # pragma: no cover
            raise ValueError('unknown frame kind ' + str(frame.kind))
    else:
        yield from candext.candidates_original(frame, oracle, cfg=cfg, stats=kind_stats)


def ortho90_generator(state):
    """Lazily attached pure-90-degree candidate generator of one layout state."""
    from . import ortho90
    generator = getattr(state, 'ortho90_generator', None)
    if generator is None:
        generator = ortho90.Ortho90Generator(cfg=state.cfg, seed=V.SEED)
        state.ortho90_generator = generator
    return generator


def attempt_route(state, route_id, budget=None, spec_cache=None, collect_stats=True,
                  use_expanded=True, geometry_mode='d56'):
    """Try to place one route from the candidate queue.

    ``geometry_mode='ortho90'`` switches to the pure orthogonal 90-degree
    geometry (straight lines + exact R=40 quarter arcs only, no short-S); the
    accept/reject decision is still the unchanged exact strict ``D56Index``.

    Returns ``(RouteResult | None, failure dict, attempt stats dict)``.  The
    failure record keeps the historical keys (``reason``, ``evaluated``,
    ``rejection_counts``, ``blockers``) so downstream tooling is unchanged.
    """
    budget = V.BUDGET_LADDER[-1] if budget is None else int(budget)
    frame = state.frames[route_id]
    oracle = state.oracle_for(route_id)
    index = state.index
    reasons = Counter()
    blocker_counts = Counter()
    families = Counter()
    evaluated = 0
    generated = 0
    started = time.perf_counter()
    spec_stats = {}
    if geometry_mode == 'ortho90':
        iterator = ortho90_generator(state).candidates(frame, oracle)
    elif use_expanded and spec_cache is not None and frame.kind == 'adjacent':
        iterator = candext.candidates_from_specs(frame, spec_cache, oracle)
    else:
        iterator = candidates_for(frame, oracle, kind_stats=spec_stats,
                                  cfg=state.cfg, use_expanded=use_expanded)
    for candidate in iterator:
        if evaluated >= budget:
            reasons['candidate_budget_exhausted'] += 1
            break
        generated += 1
        world = frame.to_world(candidate['primitives'])
        prepared = prepare(world)
        evaluation = index.evaluate(prepared)
        evaluated += 1
        families[candidate['family']] += 1
        if evaluation.valid:
            result = RouteResult(
                route_id, candidate['family'], candidate['params'], world, prepared,
                prepared.length, len(evaluation.crossings), evaluated - 1,
                prepared.bend_count)
            stats = dict(evaluated=evaluated, generated=generated,
                         seconds=time.perf_counter() - started,
                         families=dict(families), **spec_stats)
            return result, None, stats
        reasons[evaluation.reason or 'invalid'] += 1
        blocker_counts.update(evaluation.blockers)
    failure = dict(route_id=route_id,
                   reason='no_legal_candidate' if evaluated else 'no_candidate_generated',
                   evaluated=evaluated,
                   candidate_evaluations=evaluated,
                   rejection_counts=dict(reasons),
                   blockers=dict(blocker_counts))
    stats = dict(evaluated=evaluated, generated=generated,
                 seconds=time.perf_counter() - started,
                 families=dict(families), **spec_stats)
    return None, failure, stats


# ---------------------------------------------------------------------------
# E0 / task 5.4: independent single-route insertion tests on a frozen layout
# ---------------------------------------------------------------------------
_SWEEP_STATE = {}


def _sweep_worker(task):
    """Multiprocessing worker: load base layout once, test each route separately."""
    topology, plane, history_path, route_ids, budget, cfg, process_radius = task
    from ..r15 import worker_boot
    worker_boot.ensure_profile(process_radius)
    key = (topology, plane, str(history_path), json.dumps(cfg, sort_keys=True))
    state = _SWEEP_STATE.get(key)
    if state is None:
        state = LayoutState.from_history(topology, plane, history_path, cfg=cfg,
                                         log=lambda *_a, **_k: None)
        _SWEEP_STATE[key] = state
    spec_cache = {}
    for route_id in route_ids:
        frame = state.frames[route_id]
        if frame.kind == 'adjacent':
            spec_cache[route_id] = candext.adjacent_specs(
                frame, state.oracle_for(route_id))
    records = []
    for route_id in route_ids:
        result, failure, stats = attempt_route(
            state, route_id, budget=budget,
            spec_cache=spec_cache.get(route_id))
        record = dict(route_id=route_id, pair=state.route_by_id[route_id]['pair'],
                      relation=state.route_by_id[route_id]['relation'],
                      found=result is not None)
        if result is not None:
            record.update(family=result.family, params=result.params,
                          length_mm=result.length_mm,
                          crossings=result.crossings,
                          candidate_index=result.candidate_index)
        else:
            record.update(failure)
        record.update(evaluated=stats['evaluated'], generated=stats['generated'],
                      seconds=round(stats['seconds'], 3),
                      spec_total=stats.get('spec_total'),
                      spec_counts=stats.get('spec_counts'))
        records.append(record)
    return records


def parallel_sweep(state, route_ids, budget, workers=12, cfg=None, log=print,
                   history_path=None):
    """Independent single-route insertion tests, parallel over routes.

    The base layout is frozen: a found route is *not* committed, which is exactly
    the "keep the 206 successful routes unchanged" experiment of task 5.4.
    """
    from multiprocessing import Pool
    cfg = cfg or state.cfg
    history_path = history_path or state.source.get('history')
    if not history_path:
        raise ValueError('parallel_sweep needs the base history routes.json')
    workers = max(1, min(int(workers), len(route_ids)))
    chunks = [[] for _ in range(workers)]
    for position, route_id in enumerate(route_ids):
        chunks[position % workers].append(route_id)
    process_radius = float(C.RADIUS_MM)
    tasks = [(state.topology, state.plane, history_path, chunk, int(budget), cfg,
              process_radius)
             for chunk in chunks if chunk]
    started = time.perf_counter()
    results = []
    with Pool(processes=len(tasks)) as pool:
        for chunk_result in pool.imap_unordered(_sweep_worker, tasks):
            results.extend(chunk_result)
            found = sum(1 for record in results if record['found'])
            log(f'sweep budget={budget}: {len(results)}/{len(route_ids)} routes tested, '
                f'found={found}, elapsed={time.perf_counter() - started:.1f}s')
    results.sort(key=lambda record: record['route_id'])
    summary = dict(budget=int(budget), tested=len(results),
                   found=sum(1 for record in results if record['found']),
                   evaluated=sum(record.get('evaluated') or 0 for record in results),
                   seconds=time.perf_counter() - started,
                   workers=len(tasks))
    return results, summary


# ---------------------------------------------------------------------------
# E1: single greedy pass with the expanded candidate queue
# ---------------------------------------------------------------------------
def sequential_commit(state, route_ids=None, budget=None, deadline=None, log=print,
                      geometry_mode='d56'):
    """Attempt pending failed routes in order and commit every legal placement."""
    budget = V.BUDGET_LADDER[-1] if budget is None else int(budget)
    if route_ids is None:
        route_ids = [route['route_id'] for route in state.routes
                     if route['route_id'] not in state.accepted]
    started = time.perf_counter()
    applied = []
    details = []
    for position, route_id in enumerate(route_ids, 1):
        if deadline is not None and time.perf_counter() > deadline:
            log(f'sequential_commit: time budget exhausted at {position - 1}/'
                f'{len(route_ids)}')
            break
        result, failure, stats = attempt_route(state, route_id, budget=budget,
                                               geometry_mode=geometry_mode)
        if result is not None:
            state.add(result)
            applied.append(route_id)
            details.append(dict(route_id=route_id, found=True,
                                family=result.family, params=result.params,
                                evaluated=stats['evaluated'],
                                seconds=round(stats['seconds'], 3)))
        else:
            details.append(dict(route_id=route_id, found=False,
                                reason=failure['reason'],
                                evaluated=stats['evaluated'],
                                generated=stats['generated'],
                                rejection_counts=failure['rejection_counts'],
                                blockers=failure['blockers'],
                                spec_total=stats.get('spec_total'),
                                seconds=round(stats['seconds'], 3)))
            state.failed[route_id] = failure
        if position % 32 == 0:
            log(f'sequential_commit: {position}/{len(route_ids)} '
                f'applied={len(applied)} routed={len(state.accepted)} '
                f'elapsed={time.perf_counter() - started:.1f}s')
    summary = dict(budget=int(budget), attempted=len(details),
                   applied=len(applied), applied_route_ids=applied,
                   routed=len(state.accepted), seconds=time.perf_counter() - started)
    return details, summary


# ---------------------------------------------------------------------------
# single-process attempt helper (used by R&R)
# ---------------------------------------------------------------------------
def try_insert(state, route_id, budget, spec_cache=None, geometry_mode='d56'):
    result, failure, stats = attempt_route(state, route_id, budget=budget,
                                           spec_cache=spec_cache,
                                           geometry_mode=geometry_mode)
    if result is not None:
        state.add(result)
        return True, None, stats
    state.failed[route_id] = failure
    return False, failure, stats


def build_spec_cache(state):
    cache = {}
    for route_id, frame in state.frames.items():
        if frame.kind == 'adjacent':
            cache[route_id] = candext.adjacent_specs(
                frame, state.oracle_for(route_id))
    return cache
