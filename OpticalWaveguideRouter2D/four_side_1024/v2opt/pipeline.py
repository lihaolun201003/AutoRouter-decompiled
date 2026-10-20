"""Experiment driver + artefact finalisation of the V2 optimisation round.

Commands
--------
``sweep``   task 5.4: independent single-route insertion tests on a frozen layout
            for the 200/400/800/1600 evaluation-budget ladder.
``e1``      expanded candidate queue, greedy sequential commit, no strengthened R&R.
``e2``      original candidate budget/generator + strengthened R&R (ablation arm 2).
``e3``      expanded candidates + strengthened R&R (ablation arm 3).
``z1opt``   same expansion/R&R treatment applied to the z1 (opposite) plane.
``finalize`` independent strict audit + statistics + combined artefact.

Every experiment writes a geometry checkpoint (real primitives), the plane
``routes.json`` in the frozen fslw schema and a machine-readable summary JSON.
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

from . import config as V
from . import search as S
from . import rr as RR
from .core import (DEFAULT_OUT, LayoutState, best_checkpoint_path,
                   load_layout_from_checkpoint)

HIST_ROOT = Path(__file__).resolve().parents[2] / 'outputs/four_side_1024_fslw_R40_gap30_abcd'
ORTHO90_ROOT = Path(__file__).resolve().parents[2] / 'outputs/four_side_1024_v2_ortho90_v01'


def _log_to(path):
    handle = open(path, 'a', encoding='utf-8')

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        handle.write(line + '\n')
        handle.flush()
    return log, handle


def base_routes_path(topology, plane):
    mapping = {('V2', 'z2'): HIST_ROOT / 'planes/V2/C/z2/routes.json',
               ('V2', 'z1'): HIST_ROOT / 'planes/V2/D/z1/routes.json'}
    return mapping[(topology, plane)]


def experiment_dir(label, plane, root=None):
    return Path(root or DEFAULT_OUT) / 'planes' / 'V2' / label / plane


def _work_dir(root=None):
    path = Path(root or DEFAULT_OUT) / 'work'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _checkpoint_fn(path, log):
    def save(state, round_index):
        state.save_checkpoint(path, tag=f'round{round_index}')
        log(f'checkpoint written {path} routed={len(state.accepted)}')
    return save


def _route_summary(state):
    by_pair = {}
    for route in state.routes:
        pair = route['pair']
        entry = by_pair.setdefault(pair, dict(total=0, routed=0))
        entry['total'] += 1
        if route['route_id'] in state.accepted:
            entry['routed'] += 1
    return dict(routed=len(state.accepted), failed=len(state.failed),
                total=len(state.routes), by_pair=by_pair)


def _write_experiment_artifacts(state, label, plane, summary, detail, strategy):
    out_dir = experiment_dir(label, plane)
    state.write_plane(out_dir, label, detail, strategy, extra=summary)
    summary_path = Path(DEFAULT_OUT) / 'experiments' / f'{label}_{plane}_summary.json'
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                            encoding='utf-8')
    return out_dir, summary_path


# ---------------------------------------------------------------------------
# sweep (task 5.4)
# ---------------------------------------------------------------------------
def run_sweep(args, log):
    state = LayoutState.from_history('V2', args.plane,
                                     base_routes_path('V2', args.plane), log=log)
    pending = [route['route_id'] for route in state.routes
               if route['route_id'] not in state.accepted]
    out = Path(DEFAULT_OUT) / 'candidates_budget'
    out.mkdir(parents=True, exist_ok=True)
    all_summaries = []
    for budget in [int(value) for value in args.budgets.split(',')]:
        results, summary = S.parallel_sweep(
            state, pending, budget, workers=args.workers, log=log)
        summary['found_route_ids'] = [record['route_id'] for record in results
                                      if record['found']]
        summary['by_pair_found'] = {}
        for record in results:
            if record['found']:
                entry = summary['by_pair_found'].setdefault(record['pair'], 0)
                summary['by_pair_found'][record['pair']] = entry + 1
        summary['family_histogram'] = {}
        for record in results:
            if record['found']:
                family = record.get('family')
                summary['family_histogram'][family] = \
                    summary['family_histogram'].get(family, 0) + 1
        (out / f'sweep_budget{budget}.json').write_text(
            json.dumps(dict(summary=summary, routes=results), indent=1,
                       ensure_ascii=False), encoding='utf-8')
        all_summaries.append(summary)
        log(f'sweep budget={budget}: {json.dumps({k: v for k, v in summary.items() if k != "found_route_ids"}, ensure_ascii=False)}')
    (out / 'sweep_summary.json').write_text(
        json.dumps(all_summaries, indent=1, ensure_ascii=False), encoding='utf-8')
    return all_summaries


# ---------------------------------------------------------------------------
# E1: expanded candidates only
# ---------------------------------------------------------------------------
def run_e1(state, args, log, label='E1'):
    budget = int(args.budget or V.BUDGET_LADDER[-1])
    pending = [route['route_id'] for route in state.routes
               if route['route_id'] not in state.accepted]
    checkpoint = best_checkpoint_path(DEFAULT_OUT, state.plane)
    details, summary = S.sequential_commit(
        state, pending, budget=budget,
        deadline=(time.time() + args.time_limit) if args.time_limit else None,
        log=log)
    summary.update(plane=state.plane, label=label, budget=budget,
                   route_summary=_route_summary(state),
                   applied_route_ids=summary['applied_route_ids'])
    state.save_checkpoint(checkpoint, tag=f'{label}_best')
    detail = dict(name=label, algorithm=label, crossing_policy='strict',
                  candidate_budget_per_route=budget, generator='expanded_v2opt',
                  seed=V.SEED, strategy='sequential_commit',
                  route_details=details)
    summary['checkpoint'] = str(checkpoint)
    out_dir, summary_path = _write_experiment_artifacts(
        state, label, state.plane, summary, detail, label)
    log(f'{label} done: routed={len(state.accepted)} -> {out_dir}')
    return state, summary


# ---------------------------------------------------------------------------
# E2/E3: strengthened R&R
# ---------------------------------------------------------------------------
def run_rr(state, args, log, label, budget, use_expanded, sizes, max_rounds,
           time_limit):
    checkpoint = Path(DEFAULT_OUT) / 'checkpoints' / f'{label}_{state.plane}.json'
    initial = len(state.accepted)
    started = time.perf_counter()
    info = RR.ripup_reroute(
        state, budget=budget, use_expanded=use_expanded, sizes=sizes,
        max_rounds=max_rounds, transactions_per_round=args.transactions,
        workers=args.workers, seed=V.SEED + args.seed_offset,
        time_limit=time_limit, log=log,
        checkpoint_fn=_checkpoint_fn(checkpoint, log),
        analysis_budget=min(budget, args.analysis_budget),
        reinsert_budget=min(budget, args.reinsert_budget),
        max_evals_per_transaction=args.max_evals_per_transaction,
        transaction_seconds=args.transaction_seconds)
    info.update(plane=state.plane, label=label, initial_routed=initial,
                final_routed=len(state.accepted),
                route_summary=_route_summary(state),
                seconds=time.perf_counter() - started)
    state.save_checkpoint(checkpoint, tag=f'{label}_best')
    detail = dict(name=label, algorithm=label, crossing_policy='strict',
                  candidate_budget_per_route=budget,
                  generator='expanded_v2opt' if use_expanded else 'original_round3',
                  r_r_sizes=list(sizes), r_r_rounds=max_rounds,
                  r_r_transactions=args.transactions, seed=V.SEED + args.seed_offset,
                  strategy='strengthened_ripup_reroute', ripup=info)
    summary = dict(label=label, plane=state.plane, budget=budget,
                   use_expanded=use_expanded, sizes=list(sizes),
                   max_rounds=max_rounds, initial_routed=initial,
                   final_routed=len(state.accepted), gain=info['total_gain'],
                   history=info['history'], seconds=info['seconds'],
                   checkpoint=str(checkpoint), route_summary=_route_summary(state))
    out_dir, summary_path = _write_experiment_artifacts(
        state, label, state.plane, summary, detail, label)
    log(f'{label} done: {initial} -> {len(state.accepted)} -> {out_dir}')
    return state, summary


def run_e2(args, log):
    state = LayoutState.from_history('V2', 'z2',
                                     base_routes_path('V2', 'z2'), log=log)
    return run_rr(state, args, log, 'E2', budget=200, use_expanded=False,
                  sizes=tuple(args.sizes), max_rounds=args.rounds,
                  time_limit=args.rr_time_limit)


def run_e3(args, log, from_e1=True):
    state = LayoutState.from_history('V2', 'z2',
                                     base_routes_path('V2', 'z2'), log=log)
    if from_e1:
        pending = [route['route_id'] for route in state.routes
                   if route['route_id'] not in state.accepted]
        budget = int(args.budget or V.BUDGET_LADDER[-1])
        details, phase1 = S.sequential_commit(
            state, pending, budget=budget,
            deadline=(time.time() + args.time_limit) if args.time_limit else None,
            log=log)
        phase1['phase'] = 'E3_phase1_expanded_sequential'
        path = Path(DEFAULT_OUT) / 'experiments' / 'E3_phase1_summary.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(summary=phase1, routes=details), indent=1,
                                   ensure_ascii=False), encoding='utf-8')
        state.save_checkpoint(Path(DEFAULT_OUT) / 'checkpoints' / 'E3_phase1_z2.json',
                              tag='E3_phase1')
        log(f'E3 phase1 (expanded sequential): routed={len(state.accepted)}')
    return run_rr(state, args, log, 'E3', budget=int(args.budget),
                  use_expanded=True, sizes=tuple(args.sizes),
                  max_rounds=args.rounds, time_limit=args.rr_time_limit)


def run_z1opt(args, log):
    state = LayoutState.from_history('V2', 'z1',
                                     base_routes_path('V2', 'z1'), log=log)
    pending = [route['route_id'] for route in state.routes
               if route['route_id'] not in state.accepted]
    log(f'z1: pending={len(pending)}')
    details, summary = S.sequential_commit(
        state, pending, budget=int(args.budget),
        deadline=(time.time() + args.time_limit) if args.time_limit else None,
        log=log)
    log(f'z1 E1-like pass: {len(state.accepted)} routed')
    info = RR.ripup_reroute(
        state, budget=int(args.budget), use_expanded=True,
        sizes=tuple(args.sizes), max_rounds=args.rounds,
        transactions_per_round=args.transactions, workers=args.workers,
        seed=V.SEED + args.seed_offset,
        time_limit=args.rr_time_limit, log=log,
        checkpoint_fn=_checkpoint_fn(
            Path(DEFAULT_OUT) / 'checkpoints' / 'z1opt_z1.json', log),
        analysis_budget=min(int(args.budget), args.analysis_budget),
        reinsert_budget=min(int(args.budget), args.reinsert_budget))
    summary = dict(label='Z1OPT', plane='z1', initial=492,
                   final=len(state.accepted), gain=len(state.accepted) - 492,
                   route_summary=_route_summary(state), sequential=summary,
                   ripup=info)
    state.save_checkpoint(Path(DEFAULT_OUT) / 'checkpoints' / 'z1opt_z1.json',
                          tag='z1opt_best')
    detail = dict(name='Z1OPT', algorithm='Z1OPT', crossing_policy='strict',
                  candidate_budget_per_route=int(args.budget),
                  generator='expanded_v2opt', strategy='sequential+R&R', ripup=info)
    out_dir, summary_path = _write_experiment_artifacts(
        state, 'Z1OPT', 'z1', summary, detail, 'Z1OPT')
    log(f'z1opt done: 492 -> {len(state.accepted)} -> {out_dir}')
    return state, summary


def run_continue(args, log):
    """Continue the strengthened R&R from a saved geometry checkpoint (new seed)."""
    from .core import load_layout_from_checkpoint
    checkpoint = Path(args.from_checkpoint)
    if not checkpoint.exists():
        raise FileNotFoundError(checkpoint)
    state = load_layout_from_checkpoint('V2', args.plane, checkpoint, log=log)
    initial = len(state.accepted)
    label = args.label
    info = RR.ripup_reroute(
        state, budget=int(args.budget), use_expanded=True,
        sizes=tuple(args.sizes), max_rounds=args.rounds,
        transactions_per_round=args.transactions, workers=args.workers,
        seed=V.SEED + args.seed_offset, time_limit=args.rr_time_limit, log=log,
        checkpoint_fn=_checkpoint_fn(
            Path(DEFAULT_OUT) / 'checkpoints' / f'{label}_{state.plane}.json', log),
        analysis_budget=min(int(args.budget), args.analysis_budget),
        reinsert_budget=min(int(args.budget), args.reinsert_budget),
        max_evals_per_transaction=args.max_evals_per_transaction,
        transaction_seconds=args.transaction_seconds,
        targets_per_round=args.targets_per_round,
        analysis_targets=args.analysis_targets,
        min_rounds=args.min_rounds,
        zero_gain_rounds_to_stop=args.zero_rounds)
    info.update(plane=state.plane, label=label, initial_routed=initial,
                final_routed=len(state.accepted),
                route_summary=_route_summary(state),
                seconds=info.get('seconds'))
    state.save_checkpoint(Path(DEFAULT_OUT) / 'checkpoints' / f'{label}_{state.plane}.json',
                          tag=f'{label}_best')
    detail = dict(name=label, algorithm=label, crossing_policy='strict',
                  candidate_budget_per_route=int(args.budget),
                  generator='expanded_v2opt', strategy='rr_continuation',
                  continued_from=str(checkpoint), ripup=info)
    summary = dict(label=label, plane=state.plane, budget=int(args.budget),
                   initial_routed=initial, final_routed=len(state.accepted),
                   gain=len(state.accepted) - initial,
                   history=info['history'], seconds=info.get('seconds'),
                   continued_from=str(checkpoint), seed=V.SEED + args.seed_offset,
                   route_summary=_route_summary(state))
    out_dir, _summary_path = _write_experiment_artifacts(
        state, label, state.plane, summary, detail, label)
    log(f'{label} done: {initial} -> {len(state.accepted)} -> {out_dir}')
    return state, summary


def run_ortho90_continue(args, log):
    """Continue the pure-90 experiment from a checkpoint (order-sweep winner).

    Loads the real geometry checkpoint, runs strengthened R&R in pure-90 mode and
    rewrites ``planes/V2/ORTHO90/<plane>`` with the improved layout.
    """
    from .core import load_layout_from_checkpoint
    checkpoint = Path(args.from_checkpoint)
    if not checkpoint.exists():
        raise FileNotFoundError(checkpoint)
    state = load_layout_from_checkpoint('V2', args.plane, checkpoint, log=log)
    initial = len(state.accepted)
    log(f'ortho90 continue {args.plane}: checkpoint={checkpoint.name} '
        f'routed={initial} budget={args.budget}')
    cycles = []
    reinsert_mode = getattr(args, 'reinsert_order', 'shuffle')
    for cycle in range(1, int(getattr(args, 'cycles', 2)) + 1):
        pending = [route['route_id'] for route in state.routes
                   if route['route_id'] not in state.accepted]
        if not pending:
            break
        import random as _random
        rng = _random.Random(V.SEED + args.seed_offset + cycle * 104729)
        if reinsert_mode == 'reverse':
            pending.reverse()
        elif reinsert_mode == 'shuffle':
            rng.shuffle(pending)
        log(f'ortho90 continue {args.plane} cycle {cycle}: re-insertion order='
            f'{reinsert_mode}, pending={len(pending)}')
        before = len(state.accepted)
        _details, seq_summary = S.sequential_commit(
            state, pending, budget=int(args.budget), log=log,
            geometry_mode='ortho90')
        log(f'ortho90 continue {args.plane} cycle {cycle}: re-insertion pass '
            f'{before} -> {len(state.accepted)}')
        info = RR.ripup_reroute(
            state, budget=int(args.budget), use_expanded=True,
            geometry_mode='ortho90', sizes=tuple(args.sizes),
            max_rounds=args.rounds,
            transactions_per_round=args.transactions, workers=args.workers,
            seed=V.SEED + args.seed_offset + cycle * 7919, time_limit=args.rr_time_limit,
            log=log,
            checkpoint_fn=_checkpoint_fn(
                ORTHO90_ROOT / 'checkpoints' / f'ORTHO90_{state.plane}_rr.json', log),
            analysis_budget=min(int(args.budget), args.analysis_budget),
            reinsert_budget=min(int(args.budget), args.reinsert_budget),
            max_evals_per_transaction=args.max_evals_per_transaction,
            transaction_seconds=args.transaction_seconds,
            targets_per_round=args.targets_per_round,
            analysis_targets=args.analysis_targets,
            min_rounds=args.min_rounds, zero_gain_rounds_to_stop=args.zero_rounds,
            escalate_sizes=bool(getattr(args, 'escalate_sizes', False)))
        cycles.append(dict(cycle=cycle, before=before,
                           after=len(state.accepted),
                           reinsertion=seq_summary, ripup=info))
        log(f'ortho90 continue {args.plane} cycle {cycle}: final routed='
            f'{len(state.accepted)} (R&R gain={info["total_gain"]})')
        if len(state.accepted) == before:
            break
    info = cycles[-1]['ripup'] if cycles else dict(total_gain=0, history=[])
    final_checkpoint = ORTHO90_ROOT / 'checkpoints' / f'ORTHO90_{state.plane}.json'
    state.save_checkpoint(final_checkpoint, tag='final_after_order_sweep')
    geometry = _geometry_summary(state)
    lost = _lost_vs_best(state)
    detail = dict(name='ORTHO90', algorithm='ORTHO90', crossing_policy='strict',
                  geometry_mode='ortho90',
                  geometry_rule='lines axis-aligned only; arcs R=40 exactly 90 deg; '
                                'no short-S / no non-90-degree arc',
                  candidate_budget_per_route=int(args.budget),
                  generator='v2opt.ortho90 (structural + exact-LP multi-bend)',
                  strategy='order sweep winner + re-insertion/R&R cycles',
                  continued_from=str(checkpoint), seed=V.SEED + args.seed_offset,
                  cycles=cycles, ripup=info)
    summary = dict(label='ORTHO90', plane=state.plane, budget=int(args.budget),
                   initial_routed=initial, final_routed=len(state.accepted),
                   gain=len(state.accepted) - initial,
                   route_summary=_route_summary(state), geometry=geometry,
                   cycles=cycles, ripup=info, lost_vs_best=lost,
                   continued_from=str(checkpoint), total=len(state.routes))
    out_dir = _ortho90_dir(state.plane)
    state.write_plane(out_dir, 'ORTHO90', detail, 'ORTHO90', extra=summary)
    path = ORTHO90_ROOT / 'experiments' / f'ORTHO90_{state.plane}_rr_summary.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                    encoding='utf-8')
    log(f'ortho90 continue {state.plane}: {initial} -> {len(state.accepted)} -> {out_dir}')
    return state, summary


# ---------------------------------------------------------------------------
# pure orthogonal 90-degree experiment (independent output root)
# ---------------------------------------------------------------------------
def _ortho90_dir(plane):
    return ORTHO90_ROOT / 'planes' / 'V2' / 'ORTHO90' / plane


def _geometry_summary(state):
    """Primitive-kind statistics of the accepted layout (pure-90 audit counts)."""
    from . import ortho90 as O90
    totals = dict(routes=len(state.accepted), lines=0, arcs=0, non90_arcs=0,
                  diagonal_lines=0, total_length_mm=0.0, total_bends=0)
    for route_id, result in state.accepted.items():
        stats = O90.arc_statistics(result.primitives)
        totals['lines'] += stats['lines']
        totals['arcs'] += stats['arcs']
        totals['non90_arcs'] += stats['non90_arcs']
        totals['diagonal_lines'] += stats['diagonal_lines']
        totals['total_length_mm'] += float(result.length_mm)
        totals['total_bends'] += int(result.bends)
    totals['mean_length_mm'] = (totals['total_length_mm'] / totals['routes']
                                if totals['routes'] else None)
    totals['mean_bends'] = (totals['total_bends'] / totals['routes']
                            if totals['routes'] else None)
    return totals


def _lost_vs_best(state):
    """Routes routed by V2-BEST but not by this pure-90 layout + failure reasons."""
    best_dir = DEFAULT_OUT / 'planes' / 'V2' / 'BEST' / state.plane
    best_path = best_dir / 'routes.json'
    if not best_path.exists():
        return None
    best = json.loads(best_path.read_text(encoding='utf-8'))
    best_routed = {record['route_id'] for record in best['routes']
                   if record['status'] == 'routed'}
    lost = sorted(best_routed - set(state.accepted))
    reasons = {}
    no_candidate = 0
    for route_id in lost:
        failure = state.failed.get(route_id) or {}
        reason = failure.get('reason') or 'not_attempted'
        reasons[reason] = reasons.get(reason, 0) + 1
        if reason == 'no_candidate_generated':
            no_candidate += 1
    return dict(best_routed=len(best_routed), lost=len(lost),
                lost_route_ids=lost, lost_failure_reasons=reasons,
                lost_no_candidate=no_candidate,
                lost_no_legal=sum(value for key, value in reasons.items()
                                  if key != 'no_candidate_generated'))


def _run_ortho90_plane(state, order, args, log, label):
    from . import rr as RR
    budget = int(args.budget)
    details, sequential = S.sequential_commit(
        state, order, budget=budget, log=log, geometry_mode='ortho90')
    checkpoint = ORTHO90_ROOT / 'checkpoints' / f'ORTHO90_{state.plane}.json'
    state.save_checkpoint(checkpoint, tag='after_sequential')
    log(f'ortho90 {state.plane}: sequential routed={len(state.accepted)} '
        f'({sequential["seconds"]:.1f}s)')
    ripup = RR.ripup_reroute(
        state, budget=budget, use_expanded=True, geometry_mode='ortho90',
        sizes=tuple(args.sizes), max_rounds=args.rounds,
        transactions_per_round=args.transactions, workers=args.workers,
        seed=V.SEED, time_limit=args.rr_time_limit, log=log,
        checkpoint_fn=_checkpoint_fn(
            ORTHO90_ROOT / 'checkpoints' / f'ORTHO90_{state.plane}_rr.json', log),
        analysis_budget=min(budget, args.analysis_budget),
        reinsert_budget=min(budget, args.reinsert_budget),
        max_evals_per_transaction=args.max_evals_per_transaction,
        transaction_seconds=args.transaction_seconds,
        targets_per_round=args.targets_per_round,
        analysis_targets=args.analysis_targets,
        min_rounds=args.min_rounds, zero_gain_rounds_to_stop=args.zero_rounds)
    state.save_checkpoint(checkpoint, tag='final')
    geometry = _geometry_summary(state)
    lost = _lost_vs_best(state)
    detail = dict(name='ORTHO90', algorithm=label, crossing_policy='strict',
                  geometry_mode='ortho90',
                  geometry_rule='lines axis-aligned only; arcs R=40 exactly 90 deg; '
                                'no short-S / no non-90-degree arc',
                  candidate_budget_per_route=budget,
                  generator='v2opt.ortho90 (structural + exact-LP multi-bend)',
                  strategy='sequential_commit + strengthened R&R',
                  order=sequential.get('order_name') or 'as_given',
                  seed=V.SEED, ripup=ripup)
    summary = dict(label=label, plane=state.plane, budget=budget,
                   initial_routed=0, final_routed=len(state.accepted),
                   route_summary=_route_summary(state), geometry=geometry,
                   sequential=sequential, ripup=ripup,
                   lost_vs_best=lost, checkpoint=str(checkpoint),
                   total=len(state.routes))
    out_dir = _ortho90_dir(state.plane)
    state.write_plane(out_dir, label, detail, 'ORTHO90', extra=summary)
    summary_path = ORTHO90_ROOT / 'experiments' / f'ORTHO90_{state.plane}_summary.json'
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                            encoding='utf-8')
    details_path = ORTHO90_ROOT / 'experiments' / f'ORTHO90_{state.plane}_routes_detail.json'
    details_path.write_text(json.dumps(details, indent=1, ensure_ascii=False),
                            encoding='utf-8')
    log(f'ortho90 {state.plane}: final routed={len(state.accepted)}')
    return state, summary


def run_ortho90(args, log):
    """Fresh pure-90-degree routing of both planes (no short-S, exact quarter arcs)."""
    from ..abcd import strategies as S_abcd
    from ..d56.search import build_order
    ORTHO90_ROOT.mkdir(parents=True, exist_ok=True)
    summaries = {}
    # ---- z2: best known ordering of the historical round (V2-C round robin) ----
    state2 = LayoutState('V2', 'z2', log=log)
    order2 = S_abcd.round_robin_order(state2.routes, state2.frames,
                                      start_side='N', direction='cw',
                                      batch=32, within='x_desc')
    log(f'ortho90 z2: fresh routing, order=V2-C round robin N/cw/32 x_desc, '
        f'routes={len(order2)}, budget={args.budget}')
    state2, summary2 = _run_ortho90_plane(state2, order2, args, log, 'ORTHO90')
    summaries['z2'] = summary2
    # ---- z1: opposite-first sequential order (NS then EW, x desc) ----
    state1 = LayoutState('V2', 'z1', log=log)
    strategy = dict(name='sequential_opposite_first',
                    group_order=['NS', 'EW'], within_group='x_desc')
    order1 = build_order(state1.routes, state1.frames, strategy)
    log(f'ortho90 z1: fresh routing, order=sequential NS/EW x_desc, '
        f'routes={len(order1)}, budget={args.budget}')
    state1, summary1 = _run_ortho90_plane(state1, order1, args, log, 'ORTHO90')
    summaries['z1'] = summary1
    combined = dict(
        schema='four_side_1024_v2_ortho90_experiment_v1',
        label='ORTHO90',
        geometry_rule=('only axis-aligned straight segments and exact R=40 mm '
                       '90-degree quarter arcs; short-S theta<90 pairs forbidden'),
        budget=int(args.budget), rounds=int(args.rounds),
        sizes=[int(value) for value in args.sizes],
        workers=int(args.workers), seed=V.SEED,
        z1=dict(routed=summaries['z1']['final_routed'],
                total=summaries['z1']['total'],
                geometry=summaries['z1']['geometry'],
                lost_vs_best=summaries['z1']['lost_vs_best']),
        z2=dict(routed=summaries['z2']['final_routed'],
                total=summaries['z2']['total'],
                geometry=summaries['z2']['geometry'],
                lost_vs_best=summaries['z2']['lost_vs_best']),
        combined_routed=(summaries['z1']['final_routed']
                         + summaries['z2']['final_routed']),
        best_752=752,
    )
    combined['gap_vs_best'] = combined['combined_routed'] - 752
    path = ORTHO90_ROOT / 'experiments' / 'ORTHO90_combined_summary.json'
    path.write_text(json.dumps(combined, indent=1, ensure_ascii=False),
                    encoding='utf-8')
    log(f'ortho90 done: z1={combined["z1"]["routed"]} '
        f'z2={combined["z2"]["routed"]} total={combined["combined_routed"]}/1024 '
        f'(gap vs 752: {combined["gap_vs_best"]:+d})')
    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['sweep', 'e1', 'e2', 'e3', 'z1opt',
                                            'rrcontinue', 'ortho90',
                                            'ortho90rr'])
    parser.add_argument('--plane', default='z2')
    parser.add_argument('--label', default='E3X')
    parser.add_argument('--from-checkpoint', default='')
    parser.add_argument('--budget', type=int, default=1600)
    parser.add_argument('--budgets', default='200,400,800,1600')
    parser.add_argument('--workers', type=int, default=10)
    parser.add_argument('--time-limit', type=float, default=0.0,
                        help='E1 sequential pass wall-clock limit (0 = none)')
    parser.add_argument('--rr-time-limit', type=float, default=0.0,
                        help='R&R total wall-clock limit (0 = none)')
    parser.add_argument('--rounds', type=int, default=6)
    parser.add_argument('--transactions', type=int, default=64)
    parser.add_argument('--sizes', default='1,2,4,8,12')
    parser.add_argument('--analysis-budget', type=int, default=800)
    parser.add_argument('--reinsert-budget', type=int, default=800)
    parser.add_argument('--max-evals-per-transaction', type=int, default=12000)
    parser.add_argument('--transaction-seconds', type=float, default=90.0)
    parser.add_argument('--seed-offset', type=int, default=0)
    parser.add_argument('--targets-per-round', type=int, default=48)
    parser.add_argument('--analysis-targets', type=int, default=96)
    parser.add_argument('--min-rounds', type=int, default=1)
    parser.add_argument('--zero-rounds', type=int, default=1)
    parser.add_argument('--cycles', type=int, default=2,
                        help='ortho90rr: re-insertion + R&R cycles')
    parser.add_argument('--reinsert-order', default='shuffle',
                        choices=['id', 'reverse', 'shuffle'],
                        help='ortho90rr: order of the re-insertion pass')
    parser.add_argument('--escalate-sizes', action='store_true',
                        help='R&R: escalate rip-up size every round')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.sizes = [int(value) for value in args.sizes.split(',')]
    work = _work_dir()
    log_path = work / f'{args.command}_{time.strftime("%Y%m%d_%H%M%S")}.log'
    log, handle = _log_to(log_path)
    log(f'command={vars(args)}')
    try:
        if args.command == 'sweep':
            run_sweep(args, log)
        elif args.command == 'e1':
            state = LayoutState.from_history(
                'V2', 'z2', base_routes_path('V2', 'z2'), log=log)
            run_e1(state, args, log)
        elif args.command == 'e2':
            run_e2(args, log)
        elif args.command == 'e3':
            run_e3(args, log)
        elif args.command == 'z1opt':
            run_z1opt(args, log)
        elif args.command == 'rrcontinue':
            if not args.from_checkpoint:
                raise SystemExit('rrcontinue needs --from-checkpoint')
            run_continue(args, log)
        elif args.command == 'ortho90':
            run_ortho90(args, log)
        elif args.command == 'ortho90rr':
            if not args.from_checkpoint:
                raise SystemExit('ortho90rr needs --from-checkpoint')
            run_ortho90_continue(args, log)
    except Exception:  # noqa: BLE001 - log the full traceback, then re-raise
        log(traceback.format_exc())
        raise
    finally:
        log(f'log written {log_path}')
        handle.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

