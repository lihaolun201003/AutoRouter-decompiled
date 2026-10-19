"""Finalise the 8 ABCD experiments: audits, authoritative metrics, plots, GDS/SVG,
comparison assets and the C-sweep / D-budget summary tables."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/four_side_1024_v1_v2_abcd'
EXPERIMENTS = [f'{topology}_{algorithm}' for topology in ('V1', 'V2')
               for algorithm in ('A', 'B', 'C', 'D')]


def step(name):
    print(f'\n==== {name}', flush=True)
    return time.perf_counter()


def run_module(module, arguments):
    """Run a CLI module in a fresh process (gdspy keeps global state otherwise)."""
    completed = subprocess.run([sys.executable, '-m', module, *arguments],
                               cwd=str(ROOT), capture_output=True, text=True)
    if completed.returncode != 0:
        print(f'[warn] {module} {arguments} -> exit {completed.returncode}\n'
              f'{completed.stderr[-1500:]}', flush=True)
    return completed


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    skip_audits = '--skip-audits' in argv
    skip_metrics = '--skip-metrics' in argv
    from four_side_1024.abcd import audit_all, compare, metrics, plots, summarise

    present = [experiment for experiment in EXPERIMENTS
               if (OUT / experiment / 'routes.json').exists()]
    extended = [experiment for experiment in ('V1_D', 'V2_D')
                if (OUT / 'extended' / experiment / 'routes.json').exists()]

    if not skip_audits:
        started = step('independent audits (strict/exact/legacy) for 8 experiments')
        audit_all.main(['--root', str(OUT), '--experiments', ','.join(present)])
        if extended:
            audit_all.main(['--root', str(OUT / 'extended'),
                            '--experiments', ','.join(extended)])
        print(f'audits done in {time.perf_counter() - started:.1f}s', flush=True)

    if not skip_metrics:
        started = step('authoritative metrics')
        for experiment in present:
            metrics.main(['--run-dir', str(OUT / experiment)])
        for experiment in extended:
            metrics.main(['--run-dir', str(OUT / 'extended' / experiment)])
        print(f'metrics done in {time.perf_counter() - started:.1f}s', flush=True)

    started = step('PNG / SVG / GDS artifacts (fresh process per run)')
    for experiment in present:
        run_module('four_side_1024.abcd.export', ['--run-dir', str(OUT / experiment)])
        run_module('four_side_1024.abcd.plots', ['--run-dir', str(OUT / experiment)])
    for experiment in extended:
        run_module('four_side_1024.abcd.export',
                   ['--run-dir', str(OUT / 'extended' / experiment)])
        run_module('four_side_1024.abcd.plots',
                   ['--run-dir', str(OUT / 'extended' / experiment)])
    print(f'artifacts done in {time.perf_counter() - started:.1f}s', flush=True)

    started = step('C sweep + D budget + run summary tables')
    summarise.main(['--root', str(OUT)])
    print(f'tables done in {time.perf_counter() - started:.1f}s', flush=True)

    started = step('comparison assets')
    run_module('four_side_1024.abcd.compare', ['--root', str(OUT)])
    print(f'comparison done in {time.perf_counter() - started:.1f}s', flush=True)

    summary = {}
    for experiment in present:
        path = OUT / experiment / 'statistics.json'
        if path.exists():
            payload = json.loads(path.read_text(encoding='utf-8'))
            summary[experiment] = dict(routed=payload.get('routed'),
                                       rate=payload.get('routing_rate'),
                                       crossings=payload.get('crossing_count'),
                                       audit_passed=payload.get('audit_passed'))
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
