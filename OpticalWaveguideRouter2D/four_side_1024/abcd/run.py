"""Unified ABCD experiment runner for the four-side 1024-channel D56 study.

One call = one of the eight fixed experiments (V1_A .. V2_D).  The runner does not
contain any geometry of its own: it loads an immutable connection CSV through
:mod:`four_side_1024.inputs`, builds the D56 canonical frames, schedules the 1024
routes with the selected algorithm and lets the exact ``strict`` single-layer
index decide legality.  Artifacts follow ``abcd/SPEC.md`` §4.
"""
from __future__ import annotations

import argparse
import datetime
import json
import time
from pathlib import Path

from ..d56.frames import build_frames
from ..d56.run import iso_now, route_record, statistics
from ..d56.search import Router, static_congestion
from ..inputs import config as base_config
from ..inputs import load as inputs_load
from . import strategies as S

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DESKTOP = Path(r'C:\Users\lihao\Desktop')

TOPOLOGIES = {
    'V1': DESKTOP / 'optical_1024_multitomulti_connectivity_v1.csv',
    'V2': DESKTOP / 'optical_1024_multitomulti_connectivity_v2_symmetric.csv',
}

EXPERIMENTS = tuple(f'{topology}_{algorithm}'
                    for topology in ('V1', 'V2')
                    for algorithm in S.ALGORITHMS)

DEFAULT_OUT = PROJECT_ROOT / 'outputs/four_side_1024_v1_v2_abcd'

EXPECTED = 1024


def load_topology(path):
    """Load a connectivity CSV through the Phase-1 module when available."""
    try:
        from .connectivity import load_topology as _load
    except Exception:                                   # pragma: no cover
        return inputs_load(path)
    return _load(path)


def router_config(args, policy='strict'):
    cfg = dict(width=base_config()['width_mm'],
               gap=base_config()['edge_gap_mm'],
               sagitta=base_config()['sagitta_mm'],
               min_radius_mm=base_config()['min_radius_mm'],
               min_cross_angle_deg=5.0,
               crossing_policy=policy,
               candidate_budget_per_route=args.candidate_budget,
               no_deep=args.no_deep,
               ripup_routes_per_round=args.ripup_routes)
    return cfg


def _mark_remaining_failed(router, route_ids, reason):
    for route_id in route_ids:
        if route_id in router.accepted or route_id in router.failed:
            continue
        router.failed[route_id] = dict(route_id=route_id, reason=reason,
                                       evaluated=0, rejection_counts={}, blockers={})


def run_sequential(router, order, *, eval_budget=None, deadline=None, log=print):
    """Place routes in ``order`` with hard global evaluation / wall-clock budgets."""
    started = time.perf_counter()
    total = len(order)
    placed = 0
    stop_reason = None
    for index, route_id in enumerate(order):
        if eval_budget is not None and router.index.evaluations >= eval_budget:
            stop_reason = 'eval_budget_exhausted'
            _mark_remaining_failed(router, order[index:], stop_reason)
            break
        if deadline is not None and time.perf_counter() > deadline:
            stop_reason = 'time_budget_exhausted'
            _mark_remaining_failed(router, order[index:], stop_reason)
            break
        if router._try_place(route_id):
            placed += 1
        if (index + 1) % 128 == 0:
            log(f'{router.cfg.get("_strategy_label", "?")}: attempted {index + 1}/{total} '
                f'accepted={len(router.accepted)} evals={router.index.evaluations} '
                f'elapsed={time.perf_counter() - started:.1f}s')
    return dict(attempted=min(len(order), len(router.accepted) + len(router.failed)),
                accepted=len(router.accepted), placed=placed,
                evaluations=router.index.evaluations,
                stop_reason=stop_reason,
                duration_seconds=time.perf_counter() - started)


def budget_wrapper(router, order, args, deadline, log):
    if args.eval_budget:
        budget = int(args.eval_budget)
        source = 'explicit'
    else:
        budget = None
        source = 'unlimited'
    log(f'budget: eval_budget={budget} ({source}) '
        f'time_budget={args.time_budget}s deadline_set={deadline is not None}')
    info = run_sequential(router, order, eval_budget=budget, deadline=deadline, log=log)
    log(f'main pass: {info}')
    return info


def write_run_log(out_dir):
    log_path = out_dir / 'run.log'

    def log(message):
        line = iso_now() + ' ' + message
        print(line, flush=True)
        with log_path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')
    return log


def persist(router, out_dir, experiment, topology, algorithm, csv_path, validation,
            spec, args, extra=None):
    routes = router.routes
    route_by_id = {route['route_id']: route for route in routes}
    stats = statistics(router, route_by_id)
    payload = dict(
        schema='four_side_1024_d56_optimized_routes_v1',
        experiment=experiment, topology=topology, algorithm=algorithm,
        units='mm', layer=0, endpoint_mode='virtual_unfolded',
        csv_path=str(csv_path),
        csv_sha256=validation.get('csv_sha256'),
        config=dict(base_config()),
        algorithm_detail=dict(name=f'ABCD experiment {experiment}',
                       algorithm=algorithm, strategy=spec,
                       crossing_policy='strict', radius_mm=5.0,
                       width_mm=0.05, edge_gap_mm=0.125,
                       min_cross_angle_deg=5.0,
                       candidate_budget_per_route=args.candidate_budget,
                       time_budget_seconds=args.time_budget,
                       eval_budget=args.eval_budget,
                       seed=args.seed,
                       ripup_rounds=args.ripup_rounds),
        statistics=stats,
        routes=[route_record(router, route['route_id'], route_by_id[route['route_id']])
                for route in routes],
    )
    if extra:
        payload['run_info'] = extra
    text = json.dumps(payload, ensure_ascii=False)
    tmp = out_dir / 'routes.json.tmp'
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(out_dir / 'routes.json')
    failed = [dict(route_id=record['route_id'], relation=record['relation'],
                   pair=record['pair'], source_endpoint=record['source_endpoint'],
                   target_endpoint=record['target_endpoint'],
                   reason=record.get('reason'), evaluated=record.get('evaluated', 0),
                   rejection_counts=record.get('rejection_counts', {}),
                   blockers=record.get('blockers', {}))
              for record in payload['routes'] if record['status'] == 'failed']
    (out_dir / 'failed_routes.json').write_text(
        json.dumps(dict(experiment=experiment, failed_routes=failed),
                   ensure_ascii=False), encoding='utf-8')
    return payload


def write_checkpoint(out_dir, experiment, status, router, extra=None):
    record = dict(experiment=experiment, status=status, timestamp=iso_now(),
                  routable_identities=len(router.routes),
                  accepted=len(router.accepted), failed=len(router.failed),
                  evaluations=router.index.evaluations,
                  elapsed_seconds=round(time.perf_counter() - router.start, 3))
    if extra:
        record.update(extra)
    (out_dir / 'CHECKPOINT.json').write_text(
        json.dumps(record, indent=1, ensure_ascii=False), encoding='utf-8')
    return record


def run_experiment(experiment, out_dir=None, csv_path=None, args=None):
    args = args or argparse.Namespace(
        candidate_budget=900, eval_budget=0, time_budget=0.0, seed=20261019,
        ripup_rounds=4, ripup_routes=3, no_deep=False, policy='strict',
        algorithm=None, config_overrides=None)
    if experiment not in EXPERIMENTS:
        raise ValueError(f'unknown experiment {experiment!r}; expected {EXPERIMENTS}')
    topology, algorithm = experiment.split('_')
    csv_path = Path(csv_path or TOPOLOGIES[topology])
    out_dir = Path(out_dir or DEFAULT_OUT / experiment)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = write_run_log(out_dir)
    started = time.perf_counter()
    deadline = (started + args.time_budget) if args.time_budget else None
    log(f'ABCD experiment start: {experiment} topology={topology} '
        f'algorithm={algorithm} csv={csv_path} policy={args.policy} '
        f'seed={args.seed} candidate_budget={args.candidate_budget} '
        f'eval_budget={args.eval_budget} time_budget={args.time_budget}')
    routes, endpoints, connectors, validation = load_topology(csv_path)
    frames = build_frames(routes, endpoints)
    router = Router(frames, routes, cfg=router_config(args, args.policy), log=log)
    spec = None
    main_info = None

    if algorithm in ('A', 'B'):
        spec = S.sequential_strategy(algorithm, within='x_desc')
        router.cfg['_strategy_label'] = spec['name']
        order = _order_from_strategy(router, spec)
        main_info = budget_wrapper(router, order, args, deadline, log)
    elif algorithm == 'C':
        if getattr(args, 'c_design', None):
            design = json.loads(args.c_design)
        else:
            design = dict(start_side=getattr(args, 'c_start', 'N'),
                          direction=getattr(args, 'c_direction', 'cw'),
                          batch=int(getattr(args, 'c_batch', 16)))
        spec = dict(name='C_round_robin', algorithm='C', design=design,
                    within_group='x_desc')
        router.cfg['_strategy_label'] = spec['name']
        order = S.round_robin_order(routes, frames,
                                    start_side=design.get('start_side', 'N'),
                                    direction=design.get('direction', 'cw'),
                                    batch=int(design.get('batch', 16)),
                                    within=design.get('within', 'x_desc'))
        main_info = budget_wrapper(router, order, args, deadline, log)
    elif algorithm == 'D':
        from . import d_lns
        spec = d_lns.describe(args)
        router.cfg['_strategy_label'] = 'D_joint_lns'
        main_info = d_lns.optimise(router, routes, frames, args=args,
                                   deadline=deadline, log=log)
    else:                                                # pragma: no cover
        raise ValueError(algorithm)

    write_checkpoint(out_dir, experiment, 'main_pass', router,
                     extra=dict(main=main_info, strategy=spec))
    persist(router, out_dir, experiment, topology, algorithm, csv_path, validation,
            spec, args, extra=dict(main_pass=main_info, stage='main_pass'))

    ripup_info = None
    if args.ripup_rounds and algorithm != 'D':
        remaining = None
        if deadline is not None:
            remaining = max(1.0, deadline - time.perf_counter())
        ripup_info = router.ripup(max_rounds=args.ripup_rounds,
                                  blockers_per_route=args.ripup_routes,
                                  budget_seconds=remaining)
        log(f'ripup: {ripup_info}')
        write_checkpoint(out_dir, experiment, 'ripup', router,
                         extra=dict(main=main_info, ripup=ripup_info))
        persist(router, out_dir, experiment, topology, algorithm, csv_path,
                validation, spec, args,
                extra=dict(main_pass=main_info, ripup=ripup_info, stage='ripup'))

    removed = router.final_audit()
    log(f'final internal audit removed {len(removed)} route(s)')
    if removed:
        log('removed: ' + json.dumps(removed, ensure_ascii=False))
    payload = persist(router, out_dir, experiment, topology, algorithm, csv_path,
                      validation, spec, args,
                      extra=dict(main_pass=main_info, ripup=ripup_info,
                                 final_audit_removed=removed, stage='final'))
    stats = payload['statistics']
    config_record = dict(
        experiment=experiment, topology=topology, algorithm=algorithm,
        csv_path=str(csv_path), csv_sha256=validation.get('csv_sha256'),
        policy=args.policy, seed=args.seed,
        candidate_budget_per_route=args.candidate_budget,
        eval_budget=args.eval_budget, time_budget_seconds=args.time_budget,
        ripup_rounds=args.ripup_rounds, ripup_routes=args.ripup_routes,
        no_deep=args.no_deep, strategy=spec,
        physics=dict(board_mm=[150.0, 150.0], layer=0, routing_layers=1,
                     width_mm=0.05, edge_gap_mm=0.125,
                     centerline_clearance_mm=0.175, min_radius_mm=5.0,
                     sagitta_mm=0.0005, connector_pitch_mm=9.0,
                     virtual_pitch_mm=0.175, endpoint_mode='virtual_unfolded'),
        budget_used=dict(evaluations=stats['candidate_evaluations'],
                         total_runtime_seconds=stats['total_runtime_seconds']),
        main_pass=main_info, ripup=ripup_info,
    )
    if getattr(args, 'config_overrides', None):
        config_record['overrides'] = args.config_overrides
    (out_dir / 'config.json').write_text(
        json.dumps(config_record, indent=1, ensure_ascii=False), encoding='utf-8')
    final = write_checkpoint(out_dir, experiment, 'complete', router,
                             extra=dict(main=main_info, ripup=ripup_info,
                                        accepted=len(router.accepted)))
    log(f'DONE {experiment}: routed={stats["success_count"]}/{EXPECTED} '
        f'opposite={stats["by_relation"]["opposite"]["success"]} '
        f'adjacent={stats["by_relation"]["adjacent"]["success"]} '
        f'evals={stats["candidate_evaluations"]} '
        f'runtime={stats["total_runtime_seconds"]:.1f}s')
    return dict(experiment=experiment, out_dir=str(out_dir), statistics=stats,
                main_pass=main_info, ripup=ripup_info,
                checkpoint=final, removed=removed)


def _order_from_strategy(router, spec):
    from ..d56.search import build_order
    return build_order(router.routes, router.frames, spec,
                       congestion=router.congestion,
                       index=router.index, oracle=router.oracle)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True, choices=EXPERIMENTS)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--csv', type=Path, default=None,
                        help='override the topology CSV (default: fixed V1/V2 path)')
    parser.add_argument('--policy', default='strict', choices=['strict', 'exact', 'legacy'])
    parser.add_argument('--seed', type=int, default=20261019)
    parser.add_argument('--candidate-budget', type=int, default=900,
                        help='candidate evaluations per route (D56 default 900)')
    parser.add_argument('--eval-budget', type=int, default=0,
                        help='global candidate-evaluation budget (0 = unlimited)')
    parser.add_argument('--time-budget', type=float, default=0.0,
                        help='wall-clock budget in seconds (0 = unlimited)')
    parser.add_argument('--ripup-rounds', type=int, default=4)
    parser.add_argument('--ripup-routes', type=int, default=3)
    parser.add_argument('--no-deep', action='store_true')
    parser.add_argument('--c-design', default='',
                        help='JSON for C design, e.g. {"start_side":"N","direction":"cw","batch":16}')
    parser.add_argument('--c-start', default='N', choices=['N', 'E', 'S', 'W'])
    parser.add_argument('--c-direction', default='cw', choices=['cw', 'ccw'])
    parser.add_argument('--c-batch', type=int, default=16)
    parser.add_argument('--d-pool', type=int, default=48, help='D candidates per identity')
    parser.add_argument('--d-batch', type=int, default=10, help='D LNS batch size')
    parser.add_argument('--d-batch-pool', type=int, default=6,
                        help='D candidate options per identity inside a batch')
    parser.add_argument('--d-restarts', type=int, default=2,
                        help='D global selection restarts')
    parser.add_argument('--d-batches', type=int, default=400,
                        help='D LNS batch attempt budget')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    result = run_experiment(args.experiment, args.out, args.csv, args)
    print(json.dumps(dict(experiment=result['experiment'],
                          routed=result['statistics']['success_count'],
                          by_pair={k: v['success'] for k, v in
                                   result['statistics']['by_pair'].items()},
                          evals=result['statistics']['candidate_evaluations'],
                          runtime=round(result['statistics']['total_runtime_seconds'], 2)),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
