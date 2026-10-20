"""Strengthened rip-up-and-reroute (R&R) for the V2 two-height D56 layout.

Design goals (task 6):

* never lower the verified best-so-far: a transaction is committed only when the
  number of routed connections strictly increases **and** every newly placed
  primitive chain is re-validated against the *current* layout with the frozen
  exact index;
* choose what to rip by measured blocking impact (how many failed routes a placed
  route blocks, recomputed against the current layout - never a stale historical
  statistic);
* test several rip-up group sizes (1/2/4/8/12) with multiple reinsertion orders
  and a fixed random seed;
* roll back completely when a transaction yields no improvement;
* evaluate transactions in parallel over snapshots and merge only
  non-conflicting improvements, with a best checkpoint written after each round.

The worker processes never decide legality; they propose placements.  The
coordinator re-audits every proposed placement before committing it.
"""
from __future__ import annotations

import random
import time

from ..d56.index import prepare
from ..d56.search import RouteResult
from . import config as V
from .core import LayoutState, iso_now


# ---------------------------------------------------------------------------
# blocker analysis (always recomputed against the current layout)
# ---------------------------------------------------------------------------
def analyse_blockers(state, route_ids, budget, use_expanded=True, log=print,
                     adaptive=True, geometry_mode='d56'):
    """Attempt each failed route once and record its *current* blockers.

    ``adaptive`` keeps evaluating the remaining routes with the original budget
    but stops recomputing for routes that timed out badly; blockers of routes
    that already failed with a candidate-budget exhaustion are still refreshed.
    """
    from . import search as S
    records = {}
    started = time.perf_counter()
    for position, route_id in enumerate(route_ids, 1):
        result, failure, stats = S.attempt_route(
            state, route_id, budget=budget, use_expanded=use_expanded,
            geometry_mode=geometry_mode)
        if result is not None:
            # placeable in the current layout -> commit immediately (+1 routed)
            state.add(result)
            records[route_id] = dict(status='routed', family=result.family,
                                     params=result.params, evaluated=stats['evaluated'])
        else:
            state.failed[route_id] = failure
            records[route_id] = dict(status='blocked',
                                     reason=failure['reason'],
                                     evaluated=failure['evaluated'],
                                     rejection_counts=failure['rejection_counts'],
                                     blockers=failure['blockers'])
        if position % 32 == 0:
            log(f'blocker analysis: {position}/{len(route_ids)} '
                f'elapsed={time.perf_counter() - started:.1f}s')
    return records


def _analysis_worker(payload):
    """Worker: attempt one failed route on a frozen layout snapshot."""
    from . import search as S
    dump = payload['dump']
    route_id = payload['route_id']
    state = LayoutState.from_dump(dump, cfg=payload.get('cfg'),
                                  log=lambda *_a, **_k: None)
    result, failure, stats = S.attempt_route(
        state, route_id, budget=payload['budget'],
        use_expanded=payload['use_expanded'],
        geometry_mode=payload.get('geometry_mode', 'd56'))
    if result is not None:
        return dict(route_id=route_id, placed=dict(
            family=result.family, params=result.params,
            primitives=result.primitives), failure=None,
            evaluated=stats['evaluated'])
    return dict(route_id=route_id, placed=None, failure=failure,
                evaluated=stats['evaluated'])


def analyse_blockers_parallel(state, route_ids, budget, use_expanded=True,
                              workers=8, log=print, geometry_mode='d56'):
    """Parallel version of :func:`analyse_blockers` (same semantics).

    Attempts run independently on a frozen snapshot; the coordinator commits each
    successful placement only after re-checking it against the *live* index.
    """
    from multiprocessing import Pool
    if workers <= 1 or len(route_ids) <= 2:
        return analyse_blockers(state, route_ids, budget,
                                use_expanded=use_expanded, log=log,
                                geometry_mode=geometry_mode)
    dump = state.dump()
    tasks = [dict(dump=dump, route_id=route_id, budget=budget,
                  use_expanded=use_expanded, geometry_mode=geometry_mode,
                  cfg=state.cfg)
             for route_id in route_ids]
    started = time.perf_counter()
    results = []
    with Pool(processes=max(1, min(workers, len(tasks)))) as pool:
        for record in pool.imap_unordered(_analysis_worker, tasks):
            results.append(record)
            if len(results) % 32 == 0:
                log(f'parallel blocker analysis: {len(results)}/{len(tasks)} '
                    f'elapsed={time.perf_counter() - started:.1f}s')
    records = {}
    committed = 0
    for record in results:
        route_id = record['route_id']
        if record['placed'] is not None:
            prepared = prepare(record['placed']['primitives'])
            evaluation = state.index.evaluate(prepared)
            if evaluation.valid:
                state.add(RouteResult(
                    route_id, record['placed'].get('family'),
                    record['placed'].get('params') or {},
                    record['placed']['primitives'], prepared, prepared.length,
                    len(evaluation.crossings), 0, prepared.bend_count))
                records[route_id] = dict(status='routed',
                                         family=record['placed'].get('family'),
                                         evaluated=record['evaluated'])
                committed += 1
                continue
            record['failure'] = dict(route_id=route_id,
                                     reason='reanalysis_invalid_current_layout',
                                     evaluated=record['evaluated'],
                                     rejection_counts={}, blockers={})
        failure = record['failure']
        state.failed[route_id] = failure
        records[route_id] = dict(status='blocked', reason=failure['reason'],
                                 evaluated=failure['evaluated'],
                                 rejection_counts=failure['rejection_counts'],
                                 blockers=failure['blockers'])
    log(f'parallel blocker analysis done: {len(results)} routes, '
        f'{committed} placed, elapsed={time.perf_counter() - started:.1f}s')
    return records


def blocker_impact(state):
    """route_id -> (number of failed routes blocked, total blocker hits)."""
    impact = {}
    for failed_id, failure in state.failed.items():
        for key, count in (failure.get('blockers') or {}).items():
            blocker = int(key)
            if blocker not in state.accepted:
                continue
            entry = impact.setdefault(blocker, dict(failed_routes=0, hits=0))
            entry['failed_routes'] += 1
            entry['hits'] += int(count)
    return impact


def _blocker_pairs(state, failed_id, only_applied=True):
    pairs = []
    for key, hit in (state.failed.get(failed_id, {}).get('blockers') or {}).items():
        blocker = int(key)
        if only_applied and blocker not in state.accepted:
            continue
        pairs.append((blocker, int(hit)))
    return pairs


def _weighted_blocker_sets(state, failed_id, count, rng, impact, size):
    """Pick size-``size`` blocker sets for one failed route (impact weighted)."""
    pairs = _blocker_pairs(state, failed_id)
    if len(pairs) < size:
        return
    scored = []
    for blocker, hit in pairs:
        info = impact.get(blocker, dict(failed_routes=1, hits=hit))
        scored.append((hit * (1.0 + info['failed_routes']), blocker))
    scored.sort(key=lambda item: -item[0])
    head_size = max(size * 4, min(len(scored), 10))
    head = [blocker for _score, blocker in scored[:head_size]]
    emitted = set()
    for _ in range(count):
        if len(head) < size:
            break
        chosen = tuple(sorted(rng.sample(head, size)))
        if chosen in emitted:
            continue
        emitted.add(chosen)
    deterministic = tuple(sorted(blocker for _score, blocker in scored[:size]))
    if deterministic not in emitted:
        emitted.add(deterministic)
    for chosen in emitted:
        yield list(chosen)


def build_transactions(state, failed_ids, sizes=(1, 2, 4, 8, 12), per_route=2,
                       seed=V.SEED, extra_pool=None, extras_per_transaction=3):
    """Build rip-up transactions (blocker group + reinsertion order + extras).

    ``extras`` are other failed routes whose blocker set intersects the ripped
    group: they are re-inserted after the target, which lets a transaction gain
    more than one connection and remains profitable even if one ripped route
    cannot be restored (the classical multi-route rip-up/reroute move).
    """
    samples = _order_samples()
    impact = blocker_impact(state)
    rng = random.Random(seed)
    transactions = []
    blocker_sets = {}
    for failed_id in (extra_pool if extra_pool is not None else failed_ids):
        blocker_sets[failed_id] = {int(key) for key in
                                   (state.failed.get(failed_id, {})
                                    .get('blockers') or {})}
    for failed_id in failed_ids:
        for size in sizes:
            for blockers in _weighted_blocker_sets(state, failed_id, per_route,
                                                   rng, impact, size):
                ripped = set(blockers)
                shared = []
                for other, other_blockers in blocker_sets.items():
                    if other == failed_id:
                        continue
                    overlap = len(ripped & other_blockers)
                    if overlap:
                        shared.append((overlap, len(other_blockers), other))
                shared.sort(key=lambda item: (-item[0], item[1]))
                extras = [entry[2] for entry in shared[:extras_per_transaction]]
                transactions.append(dict(
                    target=failed_id, ripped=list(blockers), size=len(blockers),
                    reinsert_order=rng.choice(samples), extras=extras,
                    label=f'{failed_id}/k{len(blockers)}'))
    return transactions


def _order_samples(count=6):
    return ['ripped_first', 'target_first', 'reversed', 'random',
            'congestion_desc', 'congestion_asc'][:count]


def _ordered(ids, mode, rng, state=None):
    ids = list(ids)
    if mode == 'reversed':
        ids.reverse()
    elif mode == 'random':
        rng.shuffle(ids)
    elif mode in ('congestion_desc', 'congestion_asc') and state is not None:
        def blocker_count(route_id):
            return len(state.failure_blockers(route_id))
        ids.sort(key=blocker_count, reverse=(mode == 'congestion_desc'))
    return ids


# ---------------------------------------------------------------------------
# worker: execute one transaction on a private copy of the layout
# ---------------------------------------------------------------------------
def execute_transaction(payload):
    """Multiprocessing worker: run one transaction on a private layout copy."""
    from . import search as S
    dump = payload['dump']
    transaction = payload['transaction']
    budget = int(payload['budget'])
    reinsert_budget = int(payload.get('reinsert_budget', budget))
    max_evals = int(payload.get('max_evals_per_transaction', 12000))
    time_cap = float(payload.get('transaction_seconds', 90.0))
    use_expanded = bool(payload['use_expanded'])
    geometry_mode = payload.get('geometry_mode', 'd56')
    seed = payload['seed']
    started = time.perf_counter()
    state = LayoutState.from_dump(dump, cfg=payload.get('cfg'),
                                  log=lambda *_a, **_k: None)
    spec_cache = {}
    if use_expanded and geometry_mode == 'd56':
        from . import candext
        for route_id in [transaction['target']] + list(transaction['ripped']):
            frame = state.frames[route_id]
            if frame.kind == 'adjacent':
                spec_cache[route_id] = candext.adjacent_specs(
                    frame, state.oracle_for(route_id))
    base_count = len(state.accepted)
    rng = random.Random(seed)
    ripped = [route_id for route_id in transaction['ripped']
              if route_id in state.accepted]
    for route_id in ripped:
        state.remove(route_id)
    placed = {}
    eval_start = state.index.evaluations

    def budget_left():
        return (state.index.evaluations - eval_start < max_evals
                and time.perf_counter() - started < time_cap)

    def try_one(route_id, cap_budget):
        if not budget_left():
            return None
        result, _failure, _stats = S.attempt_route(
            state, route_id, budget=cap_budget,
            spec_cache=spec_cache.get(route_id), use_expanded=use_expanded,
            geometry_mode=geometry_mode)
        if result is not None:
            state.add(result)
            placed[route_id] = result
        return result

    try_one(transaction['target'], budget)
    order = _ordered(ripped, transaction.get('reinsert_order', 'ripped_first'),
                     rng, state)
    failed_reinsert = []
    for route_id in order:
        if route_id in placed:
            continue
        if try_one(route_id, reinsert_budget) is None:
            failed_reinsert.append(route_id)
            if not budget_left():
                break
    # opportunistic extra insertions (other failed routes sharing the ripped set)
    extras_placed = 0
    for route_id in transaction.get('extras') or []:
        if route_id in placed:
            continue
        if not budget_left():
            break
        if try_one(route_id, budget) is not None:
            extras_placed += 1
    final_count = len(state.accepted)
    return dict(transaction=transaction, base_count=base_count,
                final_count=final_count, net_gain=final_count - base_count,
                placed={route_id: dict(family=result.family, params=result.params,
                                       primitives=result.primitives)
                        for route_id, result in placed.items()},
                ripped=ripped, failed_reinsert=failed_reinsert,
                target_placed=transaction['target'] in placed,
                extras_placed=extras_placed,
                evals=state.index.evaluations - eval_start,
                seconds=time.perf_counter() - started)


def _transaction_worker(task):
    payloads = task['payloads']
    started = time.perf_counter()
    results = []
    for payload in payloads:
        try:
            result = execute_transaction(payload)
        except Exception as exc:  # noqa: BLE001 - one bad tx must not kill a round
            result = dict(transaction=payload['transaction'],
                          error=f'{type(exc).__name__}: {exc}',
                          net_gain=-10 ** 9, placed={}, ripped=[])
        result['seconds'] = time.perf_counter() - started
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# coordinator: re-validate and commit
# ---------------------------------------------------------------------------
def commit_result(state, result, log=print):
    """Re-validate one worker result against the live layout and commit it.

    Committed only if the target is placed, every proposed chain is legal in the
    *current* layout, and the routed count strictly increases.  Otherwise every
    change is rolled back exactly.
    """
    placed = result.get('placed') or {}
    target = result['transaction']['target']
    if target not in placed:
        return False
    ripped = list(result['ripped'])
    for route_id in ripped:
        if route_id not in state.accepted:
            return False
    saved_ripped = {route_id: state.accepted[route_id] for route_id in ripped
                    if route_id in state.accepted}
    # Exact rollback snapshot: ``state.add`` pops the route's failure record, so a
    # failed commit must restore the whole failed-status table too, not only the
    # accepted geometry (regression test 4 / task 9.4).
    failed_before = dict(state.failed)
    before = len(state.accepted)
    for route_id in ripped:
        state.remove(route_id)
    order = [target] + [route_id for route_id in placed if route_id != target]
    added = []
    failed = False
    for route_id in order:
        entry = placed[route_id]
        prepared = prepare(entry['primitives'])
        evaluation = state.index.evaluate(prepared)
        if not evaluation.valid:
            failed = True
            break
        state.add(RouteResult(route_id, entry.get('family'),
                              entry.get('params') or {}, entry['primitives'],
                              prepared, prepared.length,
                              len(evaluation.crossings), 0, prepared.bend_count))
        added.append(route_id)
    if failed or len(state.accepted) <= before:
        for route_id in added:
            state.remove(route_id)
        for route_id, saved in saved_ripped.items():
            state.add(saved)
        state.failed = failed_before
        return False
    log(f'  commit {result["transaction"]["label"]}: {before} -> '
        f'{len(state.accepted)} (+{len(state.accepted) - before})')
    return True


def ripup_reroute(state, *, budget, use_expanded=True, sizes=(1, 2, 4, 8, 12),
                  max_rounds=6, transactions_per_round=64, workers=8,
                  seed=V.SEED, time_limit=None, log=print, checkpoint_fn=None,
                  analysis_budget=None, reinsert_budget=None,
                  max_evals_per_transaction=12000, transaction_seconds=90.0,
                  targets_per_round=48, analysis_targets=96, min_rounds=1,
                  zero_gain_rounds_to_stop=1, escalate_sizes=True,
                  extras_per_transaction=3, geometry_mode='d56'):
    """Main strengthened R&R loop; best-so-far never decreases."""
    from multiprocessing import Pool
    analysis_budget = analysis_budget or budget
    reinsert_budget = reinsert_budget or min(budget, 800)
    rng = random.Random(seed)
    started = time.perf_counter()
    history = []
    analysed = set()
    zero_gain_rounds = 0
    initial_routed = len(state.accepted)
    for round_index in range(1, max_rounds + 1):
        if time_limit is not None and time.perf_counter() - started > time_limit:
            log(f'R&R: time limit reached before round {round_index}')
            break
        pending = [route['route_id'] for route in state.routes
                   if route['route_id'] not in state.accepted]
        if not pending:
            break
        # analysis targets: promise-ordered (fewest current blockers first) so the
        # routes that are one rip away from fitting are retried before the hopeless
        fresh_all = [route_id for route_id in pending if route_id not in analysed]
        if len(fresh_all) < 8:
            fresh_all = list(pending)
        blocker_count = {
            route_id: len(state.failed.get(route_id, {}).get('blockers') or {})
            for route_id in fresh_all}
        fresh_all.sort(key=lambda route_id: (blocker_count[route_id], route_id))
        fresh = fresh_all[:analysis_targets]
        log(f'R&R round {round_index}: pending={len(pending)} '
            f'analysing={len(fresh)} budget={analysis_budget} '
            f'routed={len(state.accepted)}')
        analyse_blockers_parallel(state, fresh, analysis_budget,
                                  use_expanded=use_expanded, workers=workers,
                                  log=log, geometry_mode=geometry_mode)
        analysed.update(fresh)
        pending = [route['route_id'] for route in state.routes
                   if route['route_id'] not in state.accepted]
        if not pending:
            break
        failed_with_blockers = [route_id for route_id in pending
                                if state.failure_blockers(route_id)]
        failed_with_blockers.sort(key=lambda route_id: (
            len(state.failure_blockers(route_id)),
            -len(state.failed.get(route_id, {}).get('blockers') or {})))
        targets = failed_with_blockers[:targets_per_round]
        if not targets:
            log('R&R: no failed route with active blockers left')
            break
        if escalate_sizes:
            sizes_round = (sizes[min(round_index - 1, len(sizes) - 1)],)
        else:
            sizes_round = sizes
        transactions = build_transactions(
            state, targets, sizes=sizes_round, per_route=2,
            seed=seed + round_index, extra_pool=pending,
            extras_per_transaction=extras_per_transaction)
        if not transactions:
            break
        rng.shuffle(transactions)
        transactions = transactions[:transactions_per_round]
        dump = state.dump()
        worker_count = max(1, min(workers, len(transactions)))
        buckets = [[] for _ in range(worker_count)]
        for index, transaction in enumerate(transactions):
            buckets[index % worker_count].append(dict(
                dump=dump, transaction=transaction, budget=budget,
                reinsert_budget=reinsert_budget,
                max_evals_per_transaction=max_evals_per_transaction,
                transaction_seconds=transaction_seconds,
                use_expanded=use_expanded, geometry_mode=geometry_mode,
                seed=seed + round_index * 7919 + index, cfg=state.cfg))
        tasks = [dict(payloads=bucket) for bucket in buckets if bucket]
        results = []
        with Pool(processes=len(tasks)) as pool:
            for chunk in pool.imap_unordered(_transaction_worker, tasks):
                results.extend(chunk)
        improving = [result for result in results if result.get('net_gain', -1) > 0]
        improving.sort(key=lambda result: (-result['net_gain'],
                                           -int(result['target_placed']),
                                           result['transaction']['size']))
        committed = 0
        round_gain = 0
        for result in improving:
            before = len(state.accepted)
            if commit_result(state, result, log=log):
                committed += 1
                round_gain += len(state.accepted) - before
                if checkpoint_fn is not None:
                    checkpoint_fn(state, round_index)
        history.append(dict(round=round_index, analysed=len(fresh),
                            transactions=len(transactions),
                            improving_results=len(improving), committed=committed,
                            gain=round_gain, routed=len(state.accepted),
                            seconds=round(time.perf_counter() - started, 2)))
        log(f'R&R round {round_index} done: transactions={len(transactions)} '
            f'improving={len(improving)} committed={committed} '
            f'gain={round_gain} routed={len(state.accepted)} '
            f'elapsed={time.perf_counter() - started:.1f}s')
        if round_gain == 0:
            zero_gain_rounds += 1
        else:
            zero_gain_rounds = 0
        if (round_index >= min_rounds
                and zero_gain_rounds >= zero_gain_rounds_to_stop):
            break
    info = dict(budget=int(budget), reinsert_budget=int(reinsert_budget),
                analysis_budget=int(analysis_budget),
                use_expanded=use_expanded, geometry_mode=geometry_mode,
                sizes=list(sizes),
                rounds=len(history), routed=len(state.accepted),
                initial_routed=initial_routed,
                total_gain=len(state.accepted) - initial_routed,
                history=history, seconds=round(time.perf_counter() - started, 2),
                seed=seed, min_rounds=min_rounds,
                zero_gain_rounds_to_stop=zero_gain_rounds_to_stop)
    return info
