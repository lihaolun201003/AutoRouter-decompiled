"""V3 plane runner: one call = one plane experiment (A/B/C/D x z1|z2).

Writes JSON/log artifacts only.  Metrics, figures, combined layouts and the
independent validator are owned by the viz / validator and are run on top of the
``routes.json`` produced here (they never change the fixed connection identities).
"""
from __future__ import annotations

import argparse
import datetime
import json
import time
from pathlib import Path

from ..d56.search import build_order as _d56_build_order
from ..fslw.search import static_congestion  # noqa: F401  (compat re-export)
from . import config as C
from . import frames as vframes
from . import ports
from .search import Router

ALGORITHMS = C.ALGORITHMS
PLANES = C.PLANES


def iso_now():
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def router_config(args):
    return dict(width=C.WIDTH_MM, gap=C.EDGE_GAP_MM, sagitta=C.SAGITTA_MM,
                min_radius_mm=C.RADIUS_MM,
                min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
                crossing_policy='strict',
                candidate_budget_per_route=args.candidate_budget,
                no_deep=args.no_deep,
                ripup_routes_per_round=args.ripup_routes,
                same_candidates=args.same_candidates,
                same_candidates_deep=args.same_candidates_deep,
                u_candidates_shallow=args.opposite_candidates,
                u_candidates_deep=args.opposite_candidates_deep,
                z3_candidates=args.adjacent_candidates,
                z3_candidates_deep=args.adjacent_candidates_deep)


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
            relation_counts = {}
            for rid in router.accepted:
                relation = router.frames[rid].relation
                relation_counts[relation] = relation_counts.get(relation, 0) + 1
            log(f'attempted {index + 1}/{len(order)} accepted={len(router.accepted)} '
                f'{relation_counts} evals={router.index.evaluations} '
                f'elapsed={time.perf_counter() - started:.1f}s')
    return dict(attempted=len(order), accepted=len(router.accepted),
                evaluations=router.index.evaluations,
                stop_reason=stop_reason,
                duration_seconds=time.perf_counter() - started)


def strategy_for(algorithm, router, routes, args):
    from . import strategies as S
    if algorithm in ('A', 'B'):
        spec = S.sequential_strategy(algorithm)
        router.cfg['_strategy_label'] = spec['name']
        order = S.build_order(routes, router.frames, spec)
        return spec, order
    if algorithm == 'C':
        spec = S.round_robin_spec(start_side=args.c_start, direction=args.c_direction,
                                  batch=args.c_batch)
        router.cfg['_strategy_label'] = spec['name']
        order = S.round_robin_order(routes, router.frames, spec)
        return spec, order
    raise ValueError('strategy_for only handles A/B/C')


def route_record(router, route, strategy_label):
    route_id = route['route_id']
    result = router.accepted.get(route_id)
    base = dict(
        route_id=route_id, plane=route['plane'], z_mm=route['z_mm'],
        relation=route['relation'], pair=route['pair'],
        source_side=route['source_side'], target_side=route['target_side'],
        source_connector=route['source_connector'],
        target_connector=route['target_connector'],
        source_row=route['source_row'], target_row=route['target_row'],
        source_column=route['source_column'], target_column=route['target_column'],
        source_channel=route['source_channel'], target_channel=route['target_channel'],
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
    by_relation = {relation: dict(success=0, failed=0) for relation in C.RELATIONS}
    by_pair = {pair: dict(success=0, failed=0) for pair in C.EXPECTED['pair_counts']}
    by_side = {side: dict(success=0, failed=0) for side in 'NESW'}
    lengths, bends = [], 0
    crossings = 0
    by_family = {}
    for route in routes:
        route_id = route['route_id']
        if route_id in router.accepted:
            result = router.accepted[route_id]
            by_relation[route['relation']]['success'] += 1
            by_pair[route['pair']]['success'] += 1
            by_side[route['source_side']]['success'] += 1
            by_family[result.family] = by_family.get(result.family, 0) + 1
            lengths.append(result.length_mm)
            bends += result.bends
            crossings += result.crossings
        else:
            by_relation[route['relation']]['failed'] += 1
            by_pair[route['pair']]['failed'] += 1
            by_side[route['source_side']]['failed'] += 1
    total = len(routes)
    total_length = sum(lengths)
    return dict(
        total_connections=total, routed=len(router.accepted),
        failed=len(router.failed), routing_rate=len(router.accepted) / max(1, total),
        by_relation=by_relation, by_pair=by_pair, by_side=by_side,
        by_candidate_family=by_family,
        same_side=dict(total=sum(1 for route in routes if route['relation'] == 'same'),
                       routed=by_relation['same']['success']),
        mean_length_mm=(total_length / len(lengths)) if lengths else None,
        max_length_mm=max(lengths) if lengths else None,
        min_length_mm=min(lengths) if lengths else None,
        total_length_mm=total_length,
        mean_bends=(bends / len(lengths)) if lengths else None,
        total_bends=bends,
        total_propagation_loss_db=C.PROPAGATION_LOSS_DB_PER_CM * total_length / 10.0,
        mean_propagation_loss_db=(C.PROPAGATION_LOSS_DB_PER_CM * total_length / 10.0
                                  / len(lengths)) if lengths else None,
        max_propagation_loss_db=(C.PROPAGATION_LOSS_DB_PER_CM * max(lengths) / 10.0)
        if lengths else None,
        min_propagation_loss_db=(C.PROPAGATION_LOSS_DB_PER_CM * min(lengths) / 10.0)
        if lengths else None,
        bend_loss=dict(status='unknown_uncalibrated'),
        crossing_loss=dict(status='unknown_uncalibrated'),
        crossing_count=crossings,
        candidate_evaluations=router.index.evaluations,
        runtime_seconds=elapsed,
        failure_reasons=_failure_reasons(routes, router),
    )


def _failure_reasons(routes, router):
    counts = {}
    for route in routes:
        if route['route_id'] in router.failed:
            reason = router.failed[route['route_id']].get('reason') or 'unknown'
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def run_plane(plane='z1', algorithm='B', out_dir=None, args=None):
    args = args or argparse.Namespace()
    defaults = dict(candidate_budget=900, eval_budget=0, time_budget=0.0,
                    seed=20261019, ripup_rounds=4, ripup_routes=3, no_deep=False,
                    c_start='N', c_direction='cw', c_batch=16,
                    same_candidates=40, same_candidates_deep=220,
                    opposite_candidates=22, opposite_candidates_deep=160,
                    adjacent_candidates=36, adjacent_candidates_deep=200,
                    d_pool=64, d_batch=12, d_batch_pool=6, d_restarts=3,
                    d_batches=1500, d_probe=8, d_select='first', d_pool_deep=False)
    for key, value in defaults.items():
        if not hasattr(args, key):
            setattr(args, key, value)
    if plane not in PLANES:
        raise ValueError(plane)
    if algorithm not in ALGORITHMS:
        raise ValueError(algorithm)
    out_dir = Path(out_dir or C.OUTPUT_ROOT / 'planes' / algorithm / plane)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'run.log'

    def log(message):
        line = iso_now() + ' ' + message
        print(line, flush=True)
        with log_path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    started = time.perf_counter()
    process = C.process_record()
    log(f'V3 plane run start: plane={plane} algorithm={algorithm} '
        f'radius={C.RADIUS_MM} gap={C.EDGE_GAP_MM} clearance={C.CLEARANCE_MM} '
        f'eval_budget={args.eval_budget} time_budget={args.time_budget} seed={args.seed}')
    routes, endpoints, connectors, validation = ports.load_plane(plane)
    log(f'ports: {validation["connections"]} connections, {validation["ports"]} ports, '
        f'relations={validation["relations"]}, passed={validation["passed"]}')
    if not validation['passed']:
        raise ValueError(f'plane validation failed: {validation["issues"][:5]}')
    frame_map = vframes.build_frames(routes, endpoints)
    log('frames: ' + json.dumps({kind: sum(1 for f in frame_map.values()
                                           if f.kind == kind)
                                 for kind in ('same', 'opposite', 'adjacent')}))
    router = Router(frame_map, routes, cfg=router_config(args), log=log)
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
        main_info = d_lns.optimise(router, routes, frame_map, args=args,
                                   deadline=deadline, log=log)
    removed = router.final_audit()
    log(f'final internal audit removed {len(removed)} route(s)')
    elapsed = time.perf_counter() - started
    statistics = plane_statistics(router, routes, elapsed)
    label = spec.get('name', algorithm) if spec else algorithm
    payload = dict(
        schema='four_side_1024_v3_plane_routes_v1', units='mm', layer=0,
        experiment=f'V3_{algorithm}_{plane}', topology=C.TOPOLOGY,
        algorithm=algorithm, plane=plane, z_mm=C.PLANE_Z_MM[C.PLANE_ROW[plane]],
        port_model=C.PORT_MODEL, endpoint_mode='real_2x16_dual_height',
        csv_sha256=validation['csv_sha256'], csv_sha256_match=validation['csv_sha256_match'],
        xlsx_sha256=validation['xlsx_sha256'],
        process=process,
        algorithm_detail=dict(name=label, algorithm=algorithm, strategy=spec,
                              crossing_policy='strict',
                              candidate_budget_per_route=args.candidate_budget,
                              eval_budget=args.eval_budget,
                              time_budget_seconds=args.time_budget,
                              seed=args.seed, ripup_rounds=args.ripup_rounds),
        plane_validation=validation,
        statistics=statistics,
        routes=[route_record(router, route, label) for route in routes],
    )
    tmp = out_dir / 'routes.json.tmp'
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    tmp.replace(out_dir / 'routes.json')
    failed = [record for record in payload['routes'] if record['status'] == 'failed']
    (out_dir / 'failed_routes.json').write_text(
        json.dumps(dict(experiment=f'V3_{algorithm}_{plane}',
                        failed_routes=failed), ensure_ascii=False),
        encoding='utf-8')
    config_record = dict(
        experiment=f'V3_{algorithm}_{plane}', topology=C.TOPOLOGY,
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
        routed=statistics['routed'], total=statistics['total_connections'],
        evaluations=statistics['candidate_evaluations'],
        elapsed_seconds=round(elapsed, 3)), indent=1, ensure_ascii=False),
        encoding='utf-8')
    log(f'DONE {algorithm}_{plane}: routed={statistics["routed"]}/'
        f'{statistics["total_connections"]} by_relation='
        f'{ {k: v["success"] for k, v in statistics["by_relation"].items()} } '
        f'evals={statistics["candidate_evaluations"]} runtime={elapsed:.1f}s')
    return dict(experiment=f'V3_{algorithm}_{plane}', out_dir=str(out_dir),
                statistics=statistics, removed=removed)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plane', default='z1', choices=PLANES)
    parser.add_argument('--algorithm', default='B', choices=ALGORITHMS)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--seed', type=int, default=20261019)
    parser.add_argument('--candidate-budget', type=int, default=900)
    parser.add_argument('--eval-budget', type=int, default=0)
    parser.add_argument('--time-budget', type=float, default=0.0)
    parser.add_argument('--ripup-rounds', type=int, default=4)
    parser.add_argument('--ripup-routes', type=int, default=3)
    parser.add_argument('--no-deep', action='store_true')
    parser.add_argument('--same-candidates', type=int, default=40)
    parser.add_argument('--same-candidates-deep', type=int, default=220)
    parser.add_argument('--opposite-candidates', type=int, default=22)
    parser.add_argument('--opposite-candidates-deep', type=int, default=160)
    parser.add_argument('--adjacent-candidates', type=int, default=36)
    parser.add_argument('--adjacent-candidates-deep', type=int, default=200)
    parser.add_argument('--c-start', default='N', choices=['N', 'E', 'S', 'W'])
    parser.add_argument('--c-direction', default='cw', choices=['cw', 'ccw'])
    parser.add_argument('--c-batch', type=int, default=16)
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
    result = run_plane(args.plane, args.algorithm, args.out, args)
    print(json.dumps(dict(experiment=result['experiment'],
                          routed=result['statistics']['routed'],
                          total=result['statistics']['total_connections'],
                          by_relation={key: value['success'] for key, value in
                                       result['statistics']['by_relation'].items()},
                          evals=result['statistics']['candidate_evaluations'],
                          runtime=round(result['statistics']['runtime_seconds'], 2)),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
