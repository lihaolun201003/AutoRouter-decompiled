"""CLI driver of the five-layer 2.5D experiment.

Usage::

    python -m four_side_1024.fsd25d.run25d --scheme A --layers 5
    python -m four_side_1024.fsd25d.run25d --scheme B --layers 3 --passes 2

Writes (never touching the two accepted 2D output roots)::

    outputs/four_side_1024_v2_25d_v01/scheme{A,B}/layers{3,5}/
        routes_25d.json      full 3D route data (schema v1)
        run_summary.json     configuration, statistics, timings
        run.log              console log
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import config25d as CFG
from . import path3d as P
from .router25d import Router25D


def _log_to(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, 'a', encoding='utf-8')

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        handle.write(line + '\n')
        handle.flush()
    return handle, log


def _jsonable_args(args):
    values = {}
    for key, value in vars(args).items():
        values[key] = str(value) if isinstance(value, Path) else value
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scheme', choices=['A', 'B'], required=True)
    parser.add_argument('--layers', type=int, choices=[3, 5], required=True)
    parser.add_argument('--budget', type=int, default=300,
                        help='candidate evaluations per failed route per pass')
    parser.add_argument('--flat-probe', type=int, default=40,
                        help='first N candidates also tried flat at the interface layer')
    parser.add_argument('--passes', type=int, default=3)
    parser.add_argument('--rr-rounds', type=int, default=2)
    parser.add_argument('--rr-targets', type=int, default=64)
    parser.add_argument('--rr-rip', type=int, default=2)
    parser.add_argument('--limit', type=int, default=0,
                        help='only attempt the first N failed routes (debug)')
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)

    out_dir = Path(args.out) if args.out else CFG.run_dir(args.scheme, args.layers)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'run.log'
    handle, log = _log_to(log_path)
    started = time.perf_counter()
    try:
        log(f'command={_jsonable_args(args)}')
        router = Router25D(args.scheme, args.layers, log=log,
                           candidate_budget=args.budget,
                           flat_probe=args.flat_probe)
        router.load()
        if args.limit > 0:
            router.attemptable = router.attemptable[:args.limit]
            log(f'debug limit: attemptable={len(router.attemptable)}')
        stats = router.run(passes=args.passes, rr_rounds=args.rr_rounds,
                           rr_targets=args.rr_targets, rr_rip=args.rr_rip, log=log)
        payload = router.routes_payload()
        payload['run'] = dict(
            command=_jsonable_args(args), started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                          time.gmtime()),
            seconds=round(time.perf_counter() - started, 2))
        routes_path = P.write_routes_json(out_dir / 'routes_25d.json', payload)
        summary = dict(
            schema='four_side_1024_v2_25d_run_v1',
            scheme=args.scheme, n_layers=args.layers,
            scheme_label=CFG.SCHEMES[args.scheme]['label'],
            baseline_routed=CFG.SCHEMES[args.scheme]['baseline_routed'],
            statistics=payload['statistics'],
            router=payload['router'],
            config=dict(candidate_budget=args.budget,
                        flat_probe=args.flat_probe, passes=args.passes,
                        rr_rounds=args.rr_rounds, rr_targets=args.rr_targets,
                        rr_rip=args.rr_rip, limit=args.limit),
            layers_z_mm=payload['layers_z_mm'],
            interface_layer=payload['interface_layer'],
            routes_file=str(routes_path),
            seconds=round(time.perf_counter() - started, 2))
        summary_path = out_dir / 'run_summary.json'
        summary_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                                encoding='utf-8')
        log(f'written {routes_path} ({routes_path.stat().st_size} bytes)')
        log(f'written {summary_path}')
        print(json.dumps({key: summary[key] for key in
                          ('scheme', 'n_layers', 'baseline_routed')}, ensure_ascii=False))
        print(json.dumps(payload['statistics'], ensure_ascii=False))
        return summary
    finally:
        log('run25d finished')
        handle.close()


if __name__ == '__main__':
    main()
