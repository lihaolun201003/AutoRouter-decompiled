"""Plane-level experiment runner for the FSLW R>=40 mm dual-height interface model.

One call = one plane experiment (``<TOPOLOGY>/<ALGORITHM>/<z1|z2>``).  The runner only
writes JSON/log artifacts; PNG/SVG/GDS and the combined 1024-channel layout are built by
``fslw.plots`` / ``fslw.combine`` (viz owner).  Nothing here changes the CSV identity or
the pairings.
"""
from __future__ import annotations

import argparse
import datetime
import json
import time
from pathlib import Path

from ..d56.frames import build_frames
from ..d56.search import build_order
from . import config as C
from . import ports
from .search import Router

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / 'outputs/four_side_1024_fslw_R40_gap30_abcd'
PLANES = ports.PLANES
ALGORITHMS = ('A', 'B', 'C', 'D')
TOPOLOGIES = ('V1', 'V2')


def iso_now():
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def apply_process(radius_mm=None, edge_gap_mm=None, width_mm=None):
    """Runtime override of the process constants (one process = one configuration)."""
    if radius_mm is not None:
        C.RADIUS_MM = float(radius_mm)
    if edge_gap_mm is not None:
        C.EDGE_GAP_MM = float(edge_gap_mm)
    if width_mm is not None:
        C.WIDTH_MM = float(width_mm)
    C.CLEARANCE_MM = C.WIDTH_MM + C.EDGE_GAP_MM
    C.FIXED_RADIUS_40MM = abs(C.RADIUS_MM - 40.0) < 1e-9
    return C.process_record()


def router_config(args):
    return dict(width=C.WIDTH_MM, gap=C.EDGE_GAP_MM, sagitta=C.SAGITTA_MM,
                min_radius_mm=C.RADIUS_MM,
                min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
                crossing_policy='strict',
                candidate_budget_per_route=args.candidate_budget,
                no_deep=args.no_deep,
                ripup_routes_per_round=args.ripup_routes,
                _radius_mm=C.RADIUS_MM)


def _mark_remaining_failed(router, route_ids, reason):
    for route_id in route_ids:
        if route_id in router.accepted or route_id in router.failed:
            continue
        router.failed[route_id] = dict(route_id=route_id, reason=reason,
                                       evaluated=0, rejection_counts={}, blockers={})


def run_sequential(router, order, *, eval_budget=None, deadline=None, log=print):
    started = time.perf_counter()
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
        router._try_place(route_id)
        if (index + 1) % 128 == 0:
            log(f'{(router.cfg.get("_strategy_label") or "?")}: attempted {index + 1}/'
                f'{len(order)} accepted={len(router.accepted)} '
                f'evals={router.index.evaluations} '
                f'elapsed={time.perf_counter() - started:.1f}s')
    return dict(attempted=len(order), accepted=len(router.accepted),
                evaluations=router.index.evaluations,
                stop_reason=stop_reason,
                duration_seconds=time.perf_counter() - started)


def strategy_for(algorithm, router, routes, args):
    from ..abcd import strategies as S
    if algorithm in ('A', 'B'):
        spec = S.sequential_strategy(algorithm, within='x_desc')
        router.cfg['_strategy_label'] = spec['name']
        order = build_order(routes, router.frames, spec,
                            congestion=router.congestion,
                            index=router.index, oracle=router.oracle)
        return spec, order
    if algorithm == 'C':
        design = dict(start_side=args.c_start, direction=args.c_direction,
                      batch=args.c_batch)
        spec = dict(name='C_round_robin', algorithm='C', design=design,
                    within_group='x_desc')
        router.cfg['_strategy_label'] = spec['name']
        order = S.round_robin_order(routes, router.frames,
                                    start_side=design['start_side'],
                                    direction=design['direction'],
                                    batch=design['batch'], within='x_desc')
        return spec, order
    raise ValueError('strategy_for only handles A/B/C')


def route_record(router, route, strategy_label):
    route_id = route['route_id']
    result = router.accepted.get(route_id)
    base = dict(route_id=route_id, plane=route['plane'], z_mm=route['z_mm'],
                relation=route['relation'], pair=route['pair'],
                source_side=route['source_side'], target_side=route['target_side'],
                source_row=route['source_row'], target_row=route['target_row'],
                source_endpoint=route['source_endpoint'],
                target_endpoint=route['target_endpoint'])
    if result is None:
        failure = router.failed.get(route_id, {})
        base.update(status='failed', reason=failure.get('reason', 'not_attempted'),
                    evaluated=failure.get('evaluated', 0),
                    rejection_counts=failure.get('rejection_counts', {}),
                    blockers=failure.get('blockers', {}))
        return base
    return dict(base, status='routed', layer=0, length_mm=result.length_mm,
                length_cm=result.length_mm / 10.0,
                propagation_loss_db=C.PROPAGATION_LOSS_DB_PER_CM * result.length_mm / 10.0,
                bend_count=result.bends, primitives=result.primitives,
                candidate=dict(family=result.family, params=result.params,
                               strategy=strategy_label, index=result.candidate_index))


def plane_statistics(router, routes, elapsed):
    by_pair = {pair: dict(success=0, failed=0)
               for pair in ('NS', 'EW', 'EN', 'ES', 'SW', 'NW')}
    by_relation = {relation: dict(success=0, failed=0)
                   for relation in ('opposite', 'adjacent')}
    lengths = []
    crossings = 0
    bends = 0
    for route in routes:
        route_id = route['route_id']
        if route_id in router.accepted:
            result = router.accepted[route_id]
            by_pair[route['pair']]['success'] += 1
            by_relation[route['relation']]['success'] += 1
            lengths.append(result.length_mm)
            crossings += result.crossings
            bends += result.bends
        else:
            by_pair[route['pair']]['failed'] += 1
            by_relation[route['relation']]['failed'] += 1
    total = len(routes)
    return dict(
        total_connections=total, routed=len(router.accepted),
        failed=len(router.failed), routing_rate=len(router.accepted) / max(1, total),
        by_pair=by_pair, by_relation=by_relation,
        mean_length_mm=(sum(lengths) / len(lengths)) if lengths else None,
        max_length_mm=max(lengths) if lengths else None,
        min_length_mm=min(lengths) if lengths else None,
        total_length_mm=sum(lengths),
        mean_propagation_loss_db=(C.PROPAGATION_LOSS_DB_PER_CM * sum(lengths) / 10.0
                                 / len(lengths)) if lengths else None,
        max_propagation_loss_db=(C.PROPAGATION_LOSS_DB_PER_CM * max(lengths) / 10.0)
        if lengths else None,
        min_propagation_loss_db=(C.PROPAGATION_LOSS_DB_PER_CM * min(lengths) / 10.0)
        if lengths else None,
        total_propagation_loss_db=C.PROPAGATION_LOSS_DB_PER_CM * sum(lengths) / 10.0,
        bend_loss=dict(status='unknown_uncalibrated'),
        crossing_loss=dict(status='unknown_uncalibrated'),
        mean_bends=(bends / len(lengths)) if lengths else None,
        total_bends=bends, crossing_count=crossings,
        candidate_evaluations=router.index.evaluations,
        runtime_seconds=elapsed,
    )


def run_plane(topology='V1', plane='z1', algorithm='B', out_dir=None, args=None):
    args = args or argparse.Namespace()
    defaults = dict(candidate_budget=900, eval_budget=0, time_budget=0.0,
                    seed=20261019, ripup_rounds=4, ripup_routes=3, no_deep=False,
                    c_design='', c_start='E', c_direction='ccw', c_batch=32,
                    d_pool=64, d_batch=12, d_batch_pool=6, d_restarts=3,
                    d_batches=1500, d_probe=8, d_select='first')
    for key, value in defaults.items():
        if not hasattr(args, key):
            setattr(args, key, value)
    if plane not in PLANES:
        raise ValueError(plane)
    if algorithm not in ALGORITHMS:
        raise ValueError(algorithm)
    out_dir = Path(out_dir or DEFAULT_OUT / 'planes' / topology / algorithm / plane)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'run.log'

    def log(message):
        line = iso_now() + ' ' + message
        print(line, flush=True)
        with log_path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    started = time.perf_counter()
    process = C.process_record()
    log(f'FSLW plane run start: topology={topology} plane={plane} '
        f'algorithm={algorithm} radius={C.RADIUS_MM} gap={C.EDGE_GAP_MM} '
        f'clearance={C.CLEARANCE_MM} eval_budget={args.eval_budget} '
        f'time_budget={args.time_budget} seed={args.seed}')
    routes, endpoints, connectors, validation = ports.load_plane(topology, plane)
    log(f'ports: {validation["connections"]} connections, {validation["ports"]} ports, '
        f'row->plane ok={validation["passed"]}')
    frames = build_frames(routes, endpoints)
    router = Router(frames, routes, cfg=router_config(args), log=log)
    deadline = (started + args.time_budget) if args.time_budget else None
    spec = None
    main_info = None
    if algorithm in ('A', 'B', 'C'):
        spec, order = strategy_for(algorithm, router, routes, args)
        main_info = run_sequential(router, order,
                                   eval_budget=(args.eval_budget or None),
                                   deadline=deadline, log=log)
        if args.ripup_rounds:
            remaining = None
            if deadline is not None:
                remaining = max(1.0, deadline - time.perf_counter())
            ripup_info = router.ripup(max_rounds=args.ripup_rounds,
                                      blockers_per_route=args.ripup_routes,
                                      budget_seconds=remaining)
            log(f'ripup: {ripup_info}')
            main_info['ripup'] = ripup_info
    else:
        from . import d_lns
        spec = d_lns.describe(args)
        router.cfg['_strategy_label'] = 'D_joint_lns'
        main_info = d_lns.optimise(router, routes, frames, args=args,
                                   deadline=deadline, log=log)
    removed = router.final_audit()
    log(f'final internal audit removed {len(removed)} route(s)')
    elapsed = time.perf_counter() - started
    stats = plane_statistics(router, routes, elapsed)
    label = spec.get('name', algorithm) if spec else algorithm
    payload = dict(
        schema='four_side_1024_fslw_plane_routes_v1',
        units='mm', layer=0,
        experiment=f'{topology}_{algorithm}_{plane}',
        topology=topology, algorithm=algorithm, plane=plane, z_mm=C.PLANE_Z_MM[
            C.PLANE_ROW[plane]],
        port_model=C.PORT_MODEL, endpoint_mode='real_2x16_dual_height',
        csv_sha256=validation['csv_sha256'], csv_path=validation['csv_path'],
        process=process,
        algorithm_detail=dict(name=label, algorithm=algorithm, strategy=spec,
                              crossing_policy='strict',
                              candidate_budget_per_route=args.candidate_budget,
                              eval_budget=args.eval_budget,
                              time_budget_seconds=args.time_budget,
                              seed=args.seed, ripup_rounds=args.ripup_rounds),
        plane_validation=validation,
        statistics=stats,
        routes=[route_record(router, route, label) for route in routes],
    )
    tmp = out_dir / 'routes.json.tmp'
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    tmp.replace(out_dir / 'routes.json')
    failed = [record for record in payload['routes'] if record['status'] == 'failed']
    (out_dir / 'failed_routes.json').write_text(
        json.dumps(dict(experiment=f'{topology}_{algorithm}_{plane}',
                        failed_routes=failed), ensure_ascii=False),
        encoding='utf-8')
    config_record = dict(
        experiment=f'{topology}_{algorithm}_{plane}', topology=topology,
        algorithm=algorithm, plane=plane, z_mm=C.PLANE_Z_MM[C.PLANE_ROW[plane]],
        port_model=C.PORT_MODEL, process=process, strategy=spec,
        budget=dict(candidate_budget_per_route=args.candidate_budget,
                    eval_budget=args.eval_budget,
                    time_budget_seconds=args.time_budget,
                    ripup_rounds=args.ripup_rounds, seed=args.seed),
        main_pass=main_info, final_audit_removed=removed)
    (out_dir / 'config.json').write_text(
        json.dumps(config_record, indent=1, ensure_ascii=False), encoding='utf-8')
    (out_dir / 'CHECKPOINT.json').write_text(json.dumps(dict(
        experiment=config_record['experiment'], status='complete', timestamp=iso_now(),
        routed=stats['routed'], total=stats['total_connections'],
        evaluations=stats['candidate_evaluations'],
        elapsed_seconds=round(elapsed, 3)), indent=1, ensure_ascii=False),
        encoding='utf-8')
    log(f'DONE {topology}_{algorithm}_{plane}: routed={stats["routed"]}/'
        f'{stats["total_connections"]} evals={stats["candidate_evaluations"]} '
        f'runtime={elapsed:.1f}s')
    return dict(experiment=f'{topology}_{algorithm}_{plane}', out_dir=str(out_dir),
                statistics=stats, removed=removed)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--topology', default='V1', choices=TOPOLOGIES)
    parser.add_argument('--plane', default='z1', choices=PLANES)
    parser.add_argument('--algorithm', default='B', choices=ALGORITHMS)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--radius', type=float, default=C.RADIUS_MM)
    parser.add_argument('--edge-gap', type=float, default=C.EDGE_GAP_MM)
    parser.add_argument('--width', type=float, default=C.WIDTH_MM)
    parser.add_argument('--seed', type=int, default=20261019)
    parser.add_argument('--candidate-budget', type=int, default=900)
    parser.add_argument('--eval-budget', type=int, default=0)
    parser.add_argument('--time-budget', type=float, default=0.0)
    parser.add_argument('--ripup-rounds', type=int, default=4)
    parser.add_argument('--ripup-routes', type=int, default=3)
    parser.add_argument('--no-deep', action='store_true')
    parser.add_argument('--c-start', default='E', choices=['N', 'E', 'S', 'W'])
    parser.add_argument('--c-direction', default='ccw', choices=['cw', 'ccw'])
    parser.add_argument('--c-batch', type=int, default=32)
    parser.add_argument('--d-pool', type=int, default=64)
    parser.add_argument('--d-batch', type=int, default=12)
    parser.add_argument('--d-batch-pool', type=int, default=6)
    parser.add_argument('--d-restarts', type=int, default=3)
    parser.add_argument('--d-batches', type=int, default=1500)
    parser.add_argument('--d-probe', type=int, default=8)
    parser.add_argument('--d-select', default='first')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    apply_process(args.radius, args.edge_gap, args.width)
    result = run_plane(args.topology, args.plane, args.algorithm, args.out, args)
    print(json.dumps(dict(experiment=result['experiment'],
                          routed=result['statistics']['routed'],
                          total=result['statistics']['total_connections'],
                          by_pair={key: value['success'] for key, value in
                                   result['statistics']['by_pair'].items()},
                          evals=result['statistics']['candidate_evaluations'],
                          runtime=round(result['statistics']['runtime_seconds'], 2)),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
