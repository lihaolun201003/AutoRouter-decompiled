"""Experiment 1 (V3_FREE_2D): free two-dimensional routing of the V3-C4 CSV.

Uses the frozen R15 2D engine of the previous round unchanged:

* candidates  : ``v2opt.candext`` (D56 lines + R=15 quarter arcs + short-S)
* acceptance  : exact ``d56.index.D56Index`` (same-layer strict rules)
* order/commit: ``v2opt.search.sequential_commit``
* validation  : ``v3c4.validate2d`` -> frozen ``fslw.validate_fslw`` strict audit

Nothing is forced to be rotation symmetric in this experiment; it is the
baseline for experiments 2 and 3.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .profile import apply as apply_profile


def _jsonable_args(args):
    return {key: (str(value) if isinstance(value, Path) else value)
            for key, value in vars(args).items()}


def _leg_size(route):
    """Manhattan leg sizes of the direct interface L (dx, dy) for one route."""
    from . import inputs as V3
    sx, sy = V3.port_xy(route['source_endpoint'])
    tx, ty = V3.port_xy(route['target_endpoint'])
    return abs(tx - sx), abs(ty - sy)


def build_order(name, state, log=print):
    from ..d56.search import build_order as d56_build_order
    from ..abcd import strategies as A
    routes, frames = state.routes, state.frames
    if name == 'csv':
        return [route['route_id'] for route in routes]
    if name == 'csv_desc':
        return [route['route_id'] for route in reversed(routes)]
    if name == 'easy_leg_desc':
        def key(route):
            dx, dy = _leg_size(route)
            return (-min(dx, dy), -max(dx, dy), route['route_id'])
        return [route['route_id'] for route in sorted(routes, key=key)]
    if name == 'easy_leg_asc':
        def key(route):
            dx, dy = _leg_size(route)
            return (min(dx, dy), max(dx, dy), route['route_id'])
        return [route['route_id'] for route in sorted(routes, key=key)]
    if name == 'x_desc':
        return d56_build_order(routes, frames, dict(
            name='sequential_pairs', group_order=['NS', 'EN', 'ES', 'SW', 'NW'],
            within_group='x_desc'))
    if name == 'group_swesnw':
        return d56_build_order(routes, frames, dict(
            name='group_swesnw', group_order=['SW', 'ES', 'NW', 'EN'],
            within_group='x_desc'))
    if name == 'group_ensw':
        return d56_build_order(routes, frames, dict(
            name='group_ensw', group_order=['EN', 'ES', 'SW', 'NW'],
            within_group='x_desc'))
    if name == 'group_nswe':
        return d56_build_order(routes, frames, dict(
            name='group_nswe', group_order=['NS', 'EW', 'EN', 'ES', 'SW', 'NW'],
            within_group='x_desc'))
    if name == 'round_robin_N_cw':
        return A.round_robin_order(routes, frames, start_side='N',
                                   direction='cw', batch=32, within='x_desc')
    if name == 'round_robin_N_ccw':
        return A.round_robin_order(routes, frames, start_side='N',
                                   direction='ccw', batch=32, within='x_desc')
    if name == 'global_congestion':
        from ..d56.search import static_congestion
        congestion = static_congestion(routes, None, frames)
        return d56_build_order(routes, frames,
                               dict(name='global_dynamic',
                                    global_key='congestion_desc'),
                               congestion=congestion)
    raise ValueError(f'unknown order {name}')


def run_plane(plane, order_name, budget, out_dir, retry_passes=0, limit=0,
              cfg=None, log=print, geometry_mode='d56'):
    apply_profile()
    from ..fslw import config as C
    from ..v2opt import search as S
    from .layout import state_for
    from . import inputs as V3
    from . import validate2d

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'run.log'

    def logline(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        with open(log_path, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    started = time.perf_counter()
    logline(f'V3_FREE_2D plane={plane} order={order_name} budget={budget} '
            f'retry_passes={retry_passes} limit={limit}')
    logline(f'radius={C.RADIUS_MM} mm fixed40={C.FIXED_RADIUS_40MM}')

    state = state_for(plane, cfg=cfg, log=logline)
    order = build_order(order_name, state, logline)
    if limit:
        order = order[:limit]
    details, summary = S.sequential_commit(state, order, budget=budget,
                                           log=logline, geometry_mode=geometry_mode)
    logline(f'sequential done routed={len(state.accepted)}/{len(state.routes)} '
            f'({summary["seconds"]:.1f}s)')
    retry_summaries = []
    for pass_index in range(1, retry_passes + 1):
        pending = [route['route_id'] for route in state.routes
                   if route['route_id'] not in state.accepted]
        if not pending:
            break
        _details, retry_summary = S.sequential_commit(
            state, pending, budget=budget, log=logline,
            geometry_mode=geometry_mode)
        retry_summaries.append(retry_summary)
        logline(f'retry pass {pass_index}: routed={len(state.accepted)} '
                f'({retry_summary["seconds"]:.1f}s)')

    checkpoint = out_dir / f'checkpoint_{plane}.json'
    state.save_checkpoint(checkpoint, tag=f'V3_FREE_2D_{plane}_{order_name}')
    algorithm_detail = dict(
        name='V3_FREE_2D', algorithm='FREE_2D',
        process_profile='R15_min_radius_15mm', radius_mm=float(C.RADIUS_MM),
        fixed_radius_40mm=False, geometry_mode=geometry_mode,
        crossing_policy='exact',
        candidate_generator='v2opt.candext (D56 lines + 90 deg arcs + short-S)',
        candidate_budget_per_route=int(budget),
        strategy=f'{order_name} sequential commit',
        order=order_name, seed=None, forced_symmetry=False,
        retry_passes=retry_passes)
    extra = dict(experiment='V3_FREE_2D', plane=plane, order=order_name,
                 budget=int(budget), retry_passes=retry_passes,
                 sequential=summary, retries=retry_summaries,
                 checkpoint=str(checkpoint), forced_symmetry=False,
                 seconds=round(time.perf_counter() - started, 2))
    state.write_plane(out_dir, 'FREE_2D', algorithm_detail, 'V3_FREE_2D', extra=extra)
    payload = json.loads((out_dir / 'routes.json').read_text(encoding='utf-8'))
    report = validate2d.audit_plane(payload, plane, label=f'V3_FREE_2D_{plane}',
                                    log=logline)
    report['experiment'] = 'V3_FREE_2D'
    report['order'] = order_name
    report['budget'] = int(budget)
    report['seconds'] = extra['seconds']
    report['routed'] = len(state.accepted)
    report['failed'] = len(state.routes) - len(state.accepted)
    (out_dir / 'validation.json').write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    run_summary = dict(dict(algorithm_detail), plane=plane,
                       routed=len(state.accepted), total=len(state.routes),
                       failed=len(state.routes) - len(state.accepted),
                       seconds=extra['seconds'], sequential=summary,
                       retries=retry_summaries, validation_passed=report['passed'],
                       checkpoint=str(checkpoint))
    (out_dir / 'run_summary.json').write_text(
        json.dumps(run_summary, indent=1, ensure_ascii=False), encoding='utf-8')
    logline(f'written {out_dir} routed={len(state.accepted)} '
            f'validation={"PASS" if report["passed"] else "FAIL"}')
    return run_summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plane', choices=['z1', 'z2'], required=True)
    parser.add_argument('--order', default='group_swesnw')
    parser.add_argument('--budget', type=int, default=1600)
    parser.add_argument('--retry-passes', type=int, default=0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    summary = run_plane(args.plane, args.order, args.budget, args.out,
                        retry_passes=args.retry_passes, limit=args.limit)
    print(json.dumps({key: summary[key] for key in
                      ('plane', 'routed', 'total', 'seconds', 'validation_passed')},
                     ensure_ascii=False))
    return summary


if __name__ == '__main__':
    main()
