"""Full 1024-channel four-side single-layer D56 routing experiment driver.

Usage (from ``OpticalWaveguideRouter2D``)::

    .venv\\Scripts\\python.exe -m four_side_1024.d56.run --strategy B ^
        --out outputs\\four_side_1024_d56_optimized

Writes ``routes_checkpoint.json`` (SPEC schema, all 1024 identities), then the
output pipeline turns it into the required artifacts.
"""
from __future__ import annotations

import argparse
import datetime
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from ..inputs import load, DEFAULT_INPUT, config as base_config
from .frames import build_frames
from .search import Router, LEGACY_GROUP_ORDER, OPPOSITE_FIRST_GROUP_ORDER

EXPECTED = 1024

STRATEGIES = {
    'A': dict(name='A_legacy_fixed_order', group_order=LEGACY_GROUP_ORDER,
              within_group='x_desc', dynamic_adjacent_order=False,
              ripup=False, note='original SW->ES->NW->EN->NS->EW order, '
                                'source-x descending inside each pair'),
    'B': dict(name='B_opposite_first', group_order=OPPOSITE_FIRST_GROUP_ORDER,
              within_group='x_desc', dynamic_adjacent_order=False,
              ripup=False, note='NS -> EW -> EN -> ES -> SW -> NW'),
    'C': dict(name='C_opposite_first_dynamic_adjacent',
              group_order=OPPOSITE_FIRST_GROUP_ORDER,
              within_group='congestion_desc', dynamic_adjacent_order=True,
              ripup=False, note='opposite first, adjacent pairs ordered by '
                                'current local congestion'),
    'D': dict(name='D_global_congestion', global_order='congestion_desc',
              group_order=OPPOSITE_FIRST_GROUP_ORDER, within_group='csv',
              dynamic_adjacent_order=False, ripup=False,
              note='all 1024 routes sorted by predicted congestion'),
    'E': dict(name='E_adjacent_first', group_order=['EN', 'ES', 'SW', 'NW', 'NS', 'EW'],
              within_group='congestion_desc', dynamic_adjacent_order=False,
              ripup=False, note='adjacent (rigid L) first, then opposite'),
    'F': dict(name='F_interleaved', group_order=['EN', 'ES', 'SW', 'NW', 'NS', 'EW'],
              within_group='x_desc', dynamic_adjacent_order=False,
              ripup=False, note='adjacent first with source-x order, then opposite'),
}


def iso_now():
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def route_record(router, route_id, route_meta):
    frame = router.frames[route_id]
    result = router.accepted.get(route_id)
    base = dict(route_id=route_id,
                relation=route_meta['relation'],
                pair=route_meta['pair'],
                source_side=frame.source_side,
                target_side=frame.target_side,
                source_endpoint=route_meta['source_endpoint'],
                target_endpoint=route_meta['target_endpoint'])
    if result is None:
        failure = router.failed.get(route_id, {})
        base.update(status='failed', reason=failure.get('reason', 'not_attempted'),
                    evaluated=failure.get('evaluated', 0),
                    rejection_counts=failure.get('rejection_counts', {}),
                    blockers=failure.get('blockers', {}))
        return base
    return dict(base, status='routed', layer=0,
                length_mm=result.length_mm,
                bend_count=result.bends,
                primitives=result.primitives,
                candidate=dict(family=result.family, params=result.params,
                               strategy=strategy_label(router),
                               index=result.candidate_index))


def strategy_label(router):
    return router.cfg.get('_strategy_label', 'unknown')


def statistics(router, route_by_id):
    routes = list(router.accepted) + list(router.failed)
    expected = len(router.routes)
    assert len(routes) == expected, (len(routes), expected)
    assert len(set(routes)) == len(routes), 'duplicate route ids in result'
    by_pair = {pair: dict(success=0, failed=0)
               for pair in ('NS', 'EW', 'EN', 'ES', 'SW', 'NW')}
    by_relation = {rel: dict(success=0, failed=0) for rel in ('opposite', 'adjacent')}
    lengths = []
    crossings = 0
    for rid in router.accepted:
        meta = route_by_id[rid]
        by_pair[meta['pair']]['success'] += 1
        by_relation[meta['relation']]['success'] += 1
        lengths.append(router.accepted[rid].length_mm)
        crossings += router.accepted[rid].crossings
    for rid in router.failed:
        meta = route_by_id[rid]
        by_pair[meta['pair']]['failed'] += 1
        by_relation[meta['relation']]['failed'] += 1
    failure_reasons = Counter(router.failed[rid].get('reason', 'unknown')
                              for rid in router.failed)
    rejection = Counter()
    for rid in router.failed:
        rejection.update(router.failed[rid].get('rejection_counts', {}))
    return dict(success_count=len(router.accepted),
                failed_count=len(router.failed),
                success_rate=len(router.accepted) / EXPECTED,
                total_connections=EXPECTED,
                layer=0, routing_layers=1,
                mean_length_mm=(sum(lengths) / len(lengths)) if lengths else None,
                max_length_mm=max(lengths) if lengths else None,
                total_length_mm=sum(lengths),
                crossing_count=crossings,
                by_pair=by_pair,
                by_relation=by_relation,
                failure_reason_counts=dict(failure_reasons),
                failed_candidate_rejection_counts=dict(rejection),
                candidate_evaluations=router.index.evaluations,
                search_runtime_seconds=router.index.index_seconds +
                router.index.exact_seconds,
                total_runtime_seconds=time.perf_counter() - router.start)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--out', type=Path,
                        default=Path('outputs/four_side_1024_d56_optimized'))
    parser.add_argument('--strategy', default='B', choices=sorted(STRATEGIES))
    parser.add_argument('--seconds', type=float, default=0.0,
                        help='optional wall-clock budget; 0 = no limit')
    parser.add_argument('--ripup', type=int, default=6,
                        help='rip-up rounds after the first pass (0 disables)')
    parser.add_argument('--budget', type=int, default=0,
                        help='candidate evaluation budget per route override')
    parser.add_argument('--crossing-policy', default='exact',
                        choices=['exact', 'legacy'])
    parser.add_argument('--subset', default='all',
                        choices=['all', 'opposite', 'adjacent'])
    parser.add_argument('--tag', default='', help='suffix for the checkpoint file')
    parser.add_argument('--groups', default='',
                        help='override pair order, e.g. SW,ES,NW,EN,NS,EW')
    parser.add_argument('--within', default='',
                        help='override inside-pair order: x_desc|x_asc|chord_desc|'
                             'chord_asc|congestion_desc|csv')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / 'run.log'

    def log(message):
        line = iso_now() + ' ' + message
        if not args.quiet:
            print(line, flush=True)
        with log_path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    log(f'D56 engine start: strategy={args.strategy} subset={args.subset} '
        f'policy={args.crossing_policy} ripup={args.ripup} out={out}')
    routes, endpoints, connectors, validation = load(args.input)
    frames = build_frames(routes, endpoints)
    route_by_id = {r['route_id']: r for r in routes}
    selected = routes
    if args.subset != 'all':
        selected = [r for r in routes if r['relation'] == args.subset]
    spec = dict(STRATEGIES[args.strategy])
    if args.groups:
        spec['group_order'] = [g.strip() for g in args.groups.split(',') if g.strip()]
    if args.within:
        spec['within_group'] = args.within.strip()
    cfg = dict(within_group=spec.get('within_group', 'x_desc'),
               dynamic_adjacent_order=spec.get('dynamic_adjacent_order', False),
               crossing_policy=args.crossing_policy)
    if spec.get('global_order'):
        cfg['global_key'] = spec['global_order']
    if args.budget:
        cfg['candidate_budget_per_route'] = args.budget
    cfg['_strategy_label'] = spec['name']
    router = Router(frames, routes if args.subset == 'all' else selected,
                    cfg=cfg, log=log)
    started = time.perf_counter()
    strategy = dict(name=spec['name'], group_order=spec['group_order'],
                    within_group=spec.get('within_group', 'x_desc'),
                    dynamic_adjacent_order=spec.get('dynamic_adjacent_order', False))
    if spec.get('global_order'):
        strategy['name'] = 'global_dynamic'
        strategy['global_key'] = spec['global_order']
    stats = router.run(strategy)
    log(f'main pass complete: {stats}')
    if args.seconds and time.perf_counter() - started > args.seconds:
        log('wall-clock budget exceeded after main pass')
    ripup_stats = None
    if args.ripup and args.subset == 'all':
        remaining = None
        if args.seconds:
            remaining = max(1.0, args.seconds - (time.perf_counter() - started))
        ripup_stats = router.ripup(max_rounds=args.ripup,
                                   budget_seconds=remaining)
        log(f'ripup complete: {ripup_stats}')
    removed = router.final_audit()
    log(f'final internal audit removed {len(removed)} route(s)')
    stats = statistics(router, route_by_id)
    payload = dict(schema='four_side_1024_d56_optimized_routes_v1',
                   units='mm', layer=0, endpoint_mode='virtual_unfolded',
                   csv_sha256=validation['csv_sha256'],
                   config={k: v for k, v in base_config().items()},
                   algorithm=dict(name='D56 optimized four-side single-layer router',
                                  strategy=spec['name'], strategy_detail=spec,
                                  crossing_policy=args.crossing_policy,
                                  radius_mm=5.0, width_mm=0.05,
                                  edge_gap_mm=0.125,
                                  min_cross_angle_deg=router.cfg['min_cross_angle_deg'],
                                  ripup_rounds=args.ripup, subset=args.subset),
                   statistics=stats,
                   routes=[route_record(router, r['route_id'], route_by_id[r['route_id']])
                           for r in (routes if args.subset == 'all' else selected)])
    for record in payload['routes']:
        if record['status'] == 'routed':
            record['candidate']['strategy'] = spec['name']
    suffix = args.tag or spec['name']
    checkpoint = out / f'routes_checkpoint_{suffix}.json'
    tmp = checkpoint.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    tmp.replace(checkpoint)
    log(f'checkpoint written: {checkpoint} '
        f'accepted={stats["success_count"]}/{EXPECTED} '
        f'evals={stats["candidate_evaluations"]} '
        f'total={time.perf_counter() - started:.1f}s')
    summary = out / f'summary_{suffix}.json'
    summary.write_text(json.dumps(dict(stats=stats, ripup=ripup_stats,
                                       strategy=spec, subset=args.subset,
                                       timestamp=iso_now()), indent=1,
                                  ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(accepted=stats['success_count'],
                          by_pair={k: v['success'] for k, v in stats['by_pair'].items()},
                          by_relation={k: v['success'] for k, v in stats['by_relation'].items()},
                          evals=stats['candidate_evaluations'],
                          runtime=round(stats['total_runtime_seconds'], 2)),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
