"""Serial strengthened rip-up & reroute for V3-C4 2D layouts.

The frozen multiprocessing R&R of ``v2opt.rr`` rebuilds a ``LayoutState`` from a
dump inside worker processes; those workers re-import the base class and cannot
load the V3 topology.  This module therefore reuses the same R&R primitives
(blocker analysis, transaction builder, transaction executor, commit/revert
coordinator) **in-process**, with ``v2opt.rr.LayoutState`` temporarily bound to
:class:`four_side_1024.v3c4.layout.V3LayoutState`.  Geometry acceptance is still
the unchanged exact ``d56.index``; only the state class differs.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from .profile import apply as apply_profile


def patch_v2opt_state():
    """Bind V3LayoutState into the frozen R&R primitives (in-process only)."""
    from ..v2opt import rr as RR
    from .layout import V3LayoutState
    RR.LayoutState = V3LayoutState
    return RR


def load_checkpoint_state(plane, checkpoint_path, log=print):
    apply_profile()
    from ..d56.index import prepare
    from ..d56.search import RouteResult
    from .layout import V3LayoutState
    state = V3LayoutState('V3_C4', plane, log=log)
    data = json.loads(Path(checkpoint_path).read_text(encoding='utf-8'))
    for entry in data.get('routed') or []:
        route_id = int(entry['route_id'])
        primitives = entry['primitives']
        prepared = prepare(primitives)
        result = RouteResult(route_id, entry.get('family'),
                             entry.get('params') or {}, primitives, prepared,
                             prepared.length, 0, 0, prepared.bend_count)
        state.accepted[route_id] = result
        state.index.add(route_id, prepared)
        state.oracles.add(route_id, prepared)
    for key, failure in (data.get('failed') or {}).items():
        state.failed[int(key)] = dict(failure)
    state.source = dict(checkpoint=str(checkpoint_path), tag=data.get('tag'))
    log(f'{plane}: restored {len(state.accepted)} routed from {checkpoint_path}')
    return state


def ripup_reroute_serial(state, *, budget, sizes=(1, 2, 4, 8), max_rounds=4,
                         transactions_per_round=24, analysis_budget=None,
                         reinsert_budget=None, max_evals_per_transaction=8000,
                         transaction_seconds=60.0, targets_per_round=24,
                         analysis_targets=36, min_rounds=1,
                         zero_gain_rounds_to_stop=1, extras_per_transaction=3,
                         seed=20261019, log=print, checkpoint_fn=None,
                         time_limit=None, use_expanded=True,
                         geometry_mode='d56'):
    RR = patch_v2opt_state()
    from ..fslw import config as _C
    from ..v2opt import config as V
    seed = int(seed if seed is not None else V.SEED)
    analysis_budget = analysis_budget or budget
    reinsert_budget = reinsert_budget or min(budget, 800)
    started = time.perf_counter()
    history = []
    analysed = set()
    zero_gain_rounds = 0
    initial_routed = len(state.accepted)
    if sizes and not isinstance(sizes, (list, tuple)):
        sizes = (sizes,)
    for round_index in range(1, int(max_rounds) + 1):
        if time_limit is not None and time.perf_counter() - started > time_limit:
            log(f'R&R: time limit reached before round {round_index}')
            break
        pending = [route['route_id'] for route in state.routes
                   if route['route_id'] not in state.accepted]
        if not pending:
            break
        fresh_all = [rid for rid in pending if rid not in analysed]
        if len(fresh_all) < 8:
            fresh_all = list(pending)
        blocker_count = {
            rid: len(state.failed.get(rid, {}).get('blockers') or {})
            for rid in fresh_all}
        fresh_all.sort(key=lambda rid: (blocker_count[rid], rid))
        fresh = fresh_all[:int(analysis_targets)]
        log(f'R&R round {round_index}: pending={len(pending)} '
            f'analysing={len(fresh)} budget={analysis_budget} '
            f'routed={len(state.accepted)}')
        RR.analyse_blockers_parallel(state, fresh, analysis_budget,
                                     use_expanded=use_expanded, workers=1,
                                     log=log, geometry_mode=geometry_mode)
        analysed.update(fresh)
        pending = [route['route_id'] for route in state.routes
                   if route['route_id'] not in state.accepted]
        if not pending:
            break
        failed_with_blockers = [rid for rid in pending
                                if state.failure_blockers(rid)]
        failed_with_blockers.sort(key=lambda rid: (
            len(state.failure_blockers(rid)),
            -len(state.failed.get(rid, {}).get('blockers') or {})))
        targets = failed_with_blockers[:int(targets_per_round)]
        if not targets:
            log('R&R: no failed route with active blockers left')
            break
        sizes_round = (sizes[min(round_index - 1, len(sizes) - 1)],)
        transactions = RR.build_transactions(
            state, targets, sizes=sizes_round, per_route=2,
            seed=seed + round_index, extra_pool=pending,
            extras_per_transaction=extras_per_transaction)
        if not transactions:
            break
        rng = random.Random(seed + round_index)
        rng.shuffle(transactions)
        transactions = transactions[:int(transactions_per_round)]
        dump = state.dump()
        payloads = []
        for index, transaction in enumerate(transactions):
            payloads.append(dict(
                dump=dump, transaction=transaction, budget=budget,
                reinsert_budget=reinsert_budget,
                max_evals_per_transaction=max_evals_per_transaction,
                transaction_seconds=transaction_seconds,
                use_expanded=use_expanded, geometry_mode=geometry_mode,
                process_radius_mm=float(_C.RADIUS_MM), seed=seed + round_index * 7919 + index,
                cfg=state.cfg))
        results = []
        for payload in payloads:
            try:
                results.append(RR.execute_transaction(payload))
            except Exception as exc:                       # noqa: BLE001
                results.append(dict(transaction=payload['transaction'],
                                    net_gain=-10 ** 9, placed={}, ripped=[],
                                    error=f'{type(exc).__name__}: {exc}',
                                    target_placed=False))
        improving = [result for result in results if result.get('net_gain', -1) > 0]
        improving.sort(key=lambda result: (-result['net_gain'],
                                           -int(result['target_placed']),
                                           result['transaction']['size']))
        committed = 0
        round_gain = 0
        for result in improving:
            before = len(state.accepted)
            if RR.commit_result(state, result, log=log):
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
        if (round_index >= int(min_rounds)
                and zero_gain_rounds >= int(zero_gain_rounds_to_stop)):
            break
    return dict(budget=int(budget), reinsert_budget=int(reinsert_budget),
                analysis_budget=int(analysis_budget), sizes=list(sizes),
                rounds=len(history), routed=len(state.accepted),
                initial_routed=initial_routed,
                total_gain=len(state.accepted) - initial_routed,
                history=history, seconds=round(time.perf_counter() - started, 2),
                seed=seed)


def improve_plane(plane, checkpoint_path, out_dir, budget=1600,
                  sizes=(1, 2, 4, 8), max_rounds=4, transactions_per_round=24,
                  log=print):
    """Load one FREE_2D checkpoint, run serial R&R, save improved artefacts."""
    apply_profile()
    from ..fslw import config as C
    from . import validate2d

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state = load_checkpoint_state(plane, checkpoint_path, log=log)
    started = time.perf_counter()
    checkpoint_dir = out_dir / 'checkpoints'
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def checkpoint_fn(st, round_index):
        st.save_checkpoint(checkpoint_dir / f'rr_round{round_index}.json',
                           tag=f'FREE_2D_{plane}_rr{round_index}')

    info = ripup_reroute_serial(
        state, budget=budget, sizes=sizes, max_rounds=max_rounds,
        transactions_per_round=transactions_per_round, log=log,
        checkpoint_fn=checkpoint_fn)
    checkpoint = out_dir / 'checkpoint.json'
    state.save_checkpoint(checkpoint, tag=f'FREE_2D_{plane}_RR')
    algorithm_detail = dict(
        name='V3_FREE_2D_RR', algorithm='FREE_2D',
        process_profile='R15_min_radius_15mm', radius_mm=float(C.RADIUS_MM),
        fixed_radius_40mm=False, geometry_mode='d56', crossing_policy='exact',
        candidate_generator='v2opt.candext (D56 lines + 90 deg arcs + short-S)',
        candidate_budget_per_route=int(budget),
        strategy='sequential commit + serial strengthened R&R',
        forced_symmetry=False, rr=info)
    extra = dict(experiment='V3_FREE_2D', plane=plane, budget=int(budget),
                 rr=info, checkpoint=str(checkpoint),
                 forced_symmetry=False,
                 seconds=round(time.perf_counter() - started, 2))
    state.write_plane(out_dir, 'FREE_2D', algorithm_detail, 'V3_FREE_2D_RR',
                      extra=extra)
    payload = json.loads((out_dir / 'routes.json').read_text(encoding='utf-8'))
    report = validate2d.audit_plane(payload, plane,
                                    label=f'V3_FREE_2D_RR_{plane}', log=log)
    report['experiment'] = 'V3_FREE_2D'
    report['rr'] = info
    report['seconds'] = extra['seconds']
    (out_dir / 'validation.json').write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    run_summary = dict(algorithm_detail, plane=plane,
                       routed=len(state.accepted), total=len(state.routes),
                       failed=len(state.routes) - len(state.accepted),
                       seconds=extra['seconds'], rr=info,
                       validation_passed=report['passed'],
                       checkpoint=str(checkpoint))
    (out_dir / 'run_summary.json').write_text(
        json.dumps(run_summary, indent=1, ensure_ascii=False), encoding='utf-8')
    log(f'improved {plane}: routed={len(state.accepted)} '
        f'validation={"PASS" if report["passed"] else "FAIL"}')
    return run_summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plane', choices=['z1', 'z2'], required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--budget', type=int, default=1600)
    parser.add_argument('--sizes', default='1,2,4,8')
    parser.add_argument('--rounds', type=int, default=4)
    parser.add_argument('--transactions', type=int, default=24)
    args = parser.parse_args(argv)
    sizes = tuple(int(value) for value in args.sizes.split(','))
    summary = improve_plane(args.plane, args.checkpoint, args.out,
                            budget=args.budget, sizes=sizes,
                            max_rounds=args.rounds,
                            transactions_per_round=args.transactions)
    print(json.dumps({key: summary[key] for key in
                      ('plane', 'routed', 'total', 'seconds', 'validation_passed')},
                     ensure_ascii=False))
    return summary


if __name__ == '__main__':
    main()
