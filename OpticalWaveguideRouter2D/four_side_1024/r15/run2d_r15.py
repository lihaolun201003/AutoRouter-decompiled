"""R15 two-dimensional routing runner (scheme A = D56 with Short-S, scheme B = pure orthogonal).

The process profile must be applied **before** importing the routing modules so
that every import-time radius binder (``v2opt.candext.R``, ``v2opt.ortho90.R``,
``fsd25d.config25d.RADIUS_MM``) really uses R = 15 mm.

Examples
--------
sequentially route one plane (order sweep stage)::

    python -m four_side_1024.r15.run2d_r15 --scheme B --plane z2 \
        --order group_swesnw --rr-rounds 0

continue a saved R15 layout with strengthened R&R::

    python -m four_side_1024.r15.run2d_r15 --scheme B --plane z2 \
        --continue-from outputs/.../checkpoints/B_z2_order.json --rr-rounds 6
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import profile_r15


def _jsonable_args(args):
    values = {}
    for key, value in vars(args).items():
        values[key] = str(value) if isinstance(value, Path) else value
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scheme', choices=['A', 'B'], required=True)
    parser.add_argument('--plane', choices=['z1', 'z2'], required=True)
    parser.add_argument('--order', default='group_swesnw')
    parser.add_argument('--budget', type=int, default=1600)
    parser.add_argument('--rr-rounds', type=int, default=0)
    parser.add_argument('--transactions', type=int, default=64)
    parser.add_argument('--sizes', default='1,2,4,8,12')
    parser.add_argument('--analysis-budget', type=int, default=800)
    parser.add_argument('--reinsert-budget', type=int, default=800)
    parser.add_argument('--rr-time-limit', type=float, default=3000.0)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--targets-per-round', type=int, default=48)
    parser.add_argument('--analysis-targets', type=int, default=96)
    parser.add_argument('--min-rounds', type=int, default=2)
    parser.add_argument('--zero-rounds', type=int, default=2)
    parser.add_argument('--continue-from', type=Path, default=None)
    parser.add_argument('--root', type=Path, default=None,
                        help='R15 experiment root (default outputs/four_side_1024_v2_r15_v01)')
    parser.add_argument('--tag', default='')
    parser.add_argument('--limit', type=int, default=0,
                        help='debug: only attempt the first N ordered routes')
    args = parser.parse_args(argv)

    profile_r15.apply(verbose=True)
    from ..fslw import config as C
    from ..v2opt import search as S
    from ..v2opt import rr as RR
    from ..v2opt.core import LayoutState, load_layout_from_checkpoint
    from ..v2opt.config import SEED

    root = Path(args.root) if args.root else Path(profile_r15.R15_ROOT)
    root = root if root.is_absolute() else Path(__file__).resolve().parents[2] / root
    label = 'A' if args.scheme == 'A' else 'B'
    out_dir = root / 'planes' / 'V2' / label / args.plane
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'run.log'

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        with open(log_path, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    started = time.perf_counter()
    log(f'command={_jsonable_args(args)}')
    log(f'profile radius={C.RADIUS_MM} mm fixed={C.FIXED_RADIUS_40MM}')
    geometry_mode = 'ortho90' if args.scheme == 'B' else 'd56'

    if args.continue_from is not None:
        state = load_layout_from_checkpoint('V2', args.plane,
                                            args.continue_from, log=log)
        log(f'continued checkpoint {args.continue_from} routed={len(state.accepted)}')
        order_summary = dict(continued_from=str(args.continue_from))
    else:
        state = LayoutState('V2', args.plane, log=log)
        order = _build_order(args.order, state, log)
        if args.limit > 0:
            order = order[:args.limit]
        log(f'order={args.order} entries={len(order)} scheme={args.scheme}')
        details, order_summary = S.sequential_commit(
            state, order, budget=args.budget, log=log,
            geometry_mode=geometry_mode)
        checkpoint = root / 'checkpoints' / f'{label}_{args.plane}_{args.order}.json'
        state.save_checkpoint(checkpoint, tag=f'{label}_{args.plane}_{args.order}')
        order_summary['checkpoint'] = str(checkpoint)
        log(f'sequential done routed={len(state.accepted)} '
            f'({order_summary.get("seconds", 0):.1f}s)')
    rr_info = None
    if args.rr_rounds > 0:
        sizes = tuple(int(value) for value in args.sizes.split(','))
        rr_info = RR.ripup_reroute(
            state, budget=args.budget, use_expanded=True,
            geometry_mode=geometry_mode, sizes=sizes,
            max_rounds=args.rr_rounds,
            transactions_per_round=args.transactions, workers=args.workers,
            seed=SEED, time_limit=args.rr_time_limit, log=log,
            checkpoint_fn=_checkpoint_fn(root, label, args.plane, log),
            analysis_budget=min(args.budget, args.analysis_budget),
            reinsert_budget=min(args.budget, args.reinsert_budget),
            targets_per_round=args.targets_per_round,
            analysis_targets=args.analysis_targets,
            min_rounds=args.min_rounds,
            zero_gain_rounds_to_stop=args.zero_rounds,
            escalate_sizes=False)
        log(f'R&R done routed={len(state.accepted)}')

    algorithm_detail = dict(
        name=f'R15_{label}', algorithm=label, crossing_policy='strict',
        process_profile=profile_r15.PROFILE_NAME,
        process_profile_note=profile_r15.PROFILE_NOTE,
        radius_mm=float(C.RADIUS_MM), fixed_radius_40mm=False,
        geometry_mode=geometry_mode,
        candidate_budget_per_route=int(args.budget),
        generator=('v2opt.candext (D56: lines + 90-degree arcs + short-S)'
                   if args.scheme == 'A' else
                   'v2opt.ortho90 (axis lines + exact 90-degree arcs only)'),
        strategy=(f'{args.order} sequential commit + strengthened R&R'
                  if args.rr_rounds else f'{args.order} sequential commit'),
        order=args.order, seed=SEED, rr=rr_info,
        scheme=args.scheme)
    summary = dict(
        schema='four_side_1024_v2_r15_2d_plane_run_v1',
        label=label, scheme=args.scheme, plane=args.plane,
        process_profile=profile_r15.PROFILE_NAME, radius_mm=float(C.RADIUS_MM),
        routed=len(state.accepted), total=len(state.routes),
        failed=len(state.routes) - len(state.accepted),
        order_summary=order_summary, rr=rr_info,
        config=_jsonable_args(args),
        seconds=round(time.perf_counter() - started, 2))
    state.write_plane(out_dir, label, algorithm_detail, 'R15', extra=summary)
    (out_dir / 'run_summary.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')
    log(f'written {out_dir} routed={len(state.accepted)}')
    print(json.dumps({key: summary[key] for key in
                      ('label', 'scheme', 'plane', 'routed', 'total', 'seconds')},
                     ensure_ascii=False))
    return summary


def _checkpoint_fn(root, label, plane, log):
    directory = Path(root) / 'checkpoints'
    directory.mkdir(parents=True, exist_ok=True)

    def callback(state, round_index):
        path = directory / f'{label}_{plane}_rr_round{round_index}.json'
        state.save_checkpoint(path, tag=f'{label}_{plane}_rr{round_index}')
        log(f'checkpoint written {path} routed={len(state.accepted)}')
    return callback


def _build_order(name, state, log):
    from ..abcd import strategies as A
    from ..d56.search import build_order
    routes, frames = state.routes, state.frames
    if name == 'ns_ew_xdesc':
        return build_order(routes, frames, dict(
            name='sequential_opposite_first', group_order=['NS', 'EW'],
            within_group='x_desc'))
    if name == 'csv':
        return [route['route_id'] for route in routes]
    if name == 'csv_desc':
        return [route['route_id'] for route in reversed(routes)]
    if name.startswith('group_'):
        group = {'group_ensw': ['EN', 'ES', 'SW', 'NW'],
                 'group_swesnw': ['SW', 'ES', 'NW', 'EN'],
                 'group_nswe': ['NS', 'EW']}.get(name)
        if group is None:
            raise ValueError(name)
        return build_order(routes, frames, dict(name=name, group_order=group,
                                                within_group='x_desc'))
    if name.startswith('round_robin_'):
        parts = name.split('_')
        start, direction = parts[2], parts[3]
        return A.round_robin_order(routes, frames, start_side=start,
                                   direction=direction, batch=32,
                                   within='x_desc')
    if name == 'global_congestion':
        from ..d56.search import static_congestion
        congestion = static_congestion(routes, None, frames)
        return build_order(routes, frames,
                           dict(name='global_dynamic',
                                global_key='congestion_desc'),
                           congestion=congestion)
    raise ValueError('unknown order ' + name)


if __name__ == '__main__':
    main()
