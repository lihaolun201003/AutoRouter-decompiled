"""Runner for the corrected L1–L5 five-layer physical-model round.

Examples
--------
stage 1 (corrected L1 baseline, both rows of L1 at z=0 / 0.5 mm)::

    python -m four_side_1024.l3d.run_l3d --scheme A --stage baseline
    python -m four_side_1024.l3d.run_l3d --scheme B --stage baseline

stages 2-4 (single lift / multi-layer sequences / local re-layering + R&R)::

    python -m four_side_1024.l3d.run_l3d --scheme A --stage full \
        --stack medium_050 --budget 120 --passes 3 --rr-rounds 1

The R15 process profile is applied before any radius-binding module is imported
(R = 15 mm for planar bends and 3D elevation curves).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import common, layers


def _jsonable_args(args):
    values = {}
    for key, value in vars(args).items():
        values[key] = str(value) if isinstance(value, Path) else value
    return values


def _out_dir(scheme, stage, stack_name):
    if stage == 'baseline':
        return common.L3D_ROOT / 'baseline' / f'scheme{scheme}'
    return common.L3D_ROOT / 'l3d' / f'scheme{scheme}' / f'layers5_{stack_name}'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scheme', choices=['A', 'B'], required=True)
    parser.add_argument('--stage', choices=['baseline', 'single', 'multi', 'full'],
                        default='baseline')
    parser.add_argument('--stack', default='medium_050')
    parser.add_argument('--stack-json', type=Path, default=None,
                        help='custom layer stack JSON (overrides --stack)')
    parser.add_argument('--budget', type=int, default=120,
                        help='2D candidates evaluated per failed route')
    parser.add_argument('--multi-budget', type=int, default=60,
                        help='candidates evaluated in the multi-layer stage')
    parser.add_argument('--passes', type=int, default=3)
    parser.add_argument('--rr-rounds', type=int, default=1)
    parser.add_argument('--rr-targets', type=int, default=48)
    parser.add_argument('--rr-rip', type=int, default=2)
    parser.add_argument('--layer-selection', choices=['best', 'first'], default='best')
    parser.add_argument('--demo-multi', action='store_true',
                        help='demonstration mode: only multi-layer sequences are tried')
    parser.add_argument('--limit', type=int, default=0,
                        help='debug: only attempt the first N failed routes')
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--tag', default='')
    args = parser.parse_args(argv)

    from ..r15 import profile_r15
    profile_r15.apply(verbose=True)
    from ..fslw import config as C

    stack = (layers.load_stack(args.stack_json) if args.stack_json
             else layers.build_stack(args.stack))
    stack_name = getattr(stack, 'name', args.stack)
    out_dir = Path(args.out) if args.out else _out_dir(args.scheme, args.stage,
                                                       stack_name)
    out_dir = out_dir if out_dir.is_absolute() else common.PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'run.log'
    handle = open(log_path, 'a', encoding='utf-8')

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        handle.write(line + '\n')
        handle.flush()

    stack_dir = common.L3D_ROOT / 'layer_stacks'
    stack.write(stack_dir / f'{stack_name}.json')
    log(f'command={_jsonable_args(args)}')
    log(f'R15 profile radius={C.RADIUS_MM} mm')
    log(f'layer stack {stack_name}: {json.dumps(stack.to_dict()["routing_heights_mm"])} '
        f'provenance={stack.provenance} formal_acceptance_allowed='
        f'{stack.formal_acceptance_allowed}')
    started = time.perf_counter()

    if args.stage == 'baseline':
        from .baseline import build_baseline
        payload = build_baseline(args.scheme, stack, log=log)
        summary = dict(
            schema='four_side_1024_v2_l3d_run_summary_v1',
            stage='baseline_l1', scheme=args.scheme, stack=stack_name,
            layer_stack=stack.to_dict(), config=_jsonable_args(args),
            routed=payload['routed'], failed=payload['failed'],
            attempts=0, seconds=round(time.perf_counter() - started, 2))
        result = dict(payload=payload, summary=summary, out_dir=str(out_dir))
    else:
        from .router import Router
        router = Router(args.scheme, stack, log=log,
                        candidate_budget=args.budget,
                        multi_budget=args.multi_budget,
                        layer_selection=args.layer_selection,
                        multi_only=args.demo_multi)
        router.load()
        router.run(passes=args.passes, rr_rounds=args.rr_rounds,
                   rr_targets=args.rr_targets, rr_rip=args.rr_rip,
                   stage=args.stage, limit=args.limit)
        payload = router.routes_payload()
        summary = dict(
            schema='four_side_1024_v2_l3d_run_summary_v1',
            stage=args.stage, scheme=args.scheme, stack=stack_name,
            layer_stack=stack.to_dict(), config=_jsonable_args(args),
            statistics=payload['statistics'], router=payload['router'],
            seconds=round(time.perf_counter() - started, 2))
        result = dict(payload=payload, summary=summary, out_dir=str(out_dir))

    routes_path = common.write_json(out_dir / 'routes_l3d.json', result['payload'])
    summary_path = common.write_json(out_dir / 'run_summary.json', result['summary'])
    log(f'written {routes_path}')
    log(f'written {summary_path}')
    log(f'done in {time.perf_counter() - started:.1f}s')
    print(json.dumps(dict(scheme=args.scheme, stage=args.stage, stack=stack_name,
                          routed=result['payload'].get('routed'),
                          failed=result['payload'].get('failed'),
                          out_file=str(routes_path)),
                     ensure_ascii=False))
    handle.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
