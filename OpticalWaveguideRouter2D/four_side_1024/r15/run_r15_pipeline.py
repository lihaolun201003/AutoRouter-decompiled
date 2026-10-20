"""R15 round orchestration (post-2D steps).

The R15 2D routing itself is run per plane with :mod:`four_side_1024.r15.run2d_r15`
(long-running, parallel); once both planes of scheme A and B exist this script
performs the remaining deterministic steps:

    python -m four_side_1024.r15.run_r15_pipeline --step finalize2d
    python -m four_side_1024.r15.run_r15_pipeline --step 25d
    python -m four_side_1024.r15.run_r15_pipeline --step validate
    python -m four_side_1024.r15.run_r15_pipeline --step stats
    python -m four_side_1024.r15.run_r15_pipeline --step plots
    python -m four_side_1024.r15.run_r15_pipeline --step all

All steps apply the R15 process profile before importing any router/validator
module, and write only into ``outputs/four_side_1024_v2_r15_v01/``.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import profile_r15


def _root(args):
    root = Path(args.root) if args.root else Path(profile_r15.R15_ROOT)
    return root if root.is_absolute() else Path(__file__).resolve().parents[2] / root


def step_finalize2d(root, log, labels='A,B'):
    from ..v2opt import finalize
    log(f'finalize 2D root={root} labels={labels}')
    finalize.main(['--root', str(root), '--labels', labels, '--force'])
    return 'finalize2d'


def step_25d(root, log, args):
    from . import run25d_r15
    results = []
    for scheme in ('A', 'B'):
        log(f'25d scheme {scheme}: start')
        argv = ['--scheme', scheme, '--layers', '5',
                '--budget', str(args.budget), '--passes', str(args.passes),
                '--flat-probe', str(args.flat_probe),
                '--rr-rounds', str(args.rr_rounds)]
        if scheme == 'B':
            # scheme B has far fewer failed routes once R=15 is allowed; the
            # same knob set is kept for a fair A/B comparison.
            pass
        run25d_r15.main(argv)
        results.append(scheme)
        log(f'25d scheme {scheme}: done')
    return '25d'


def step_validate(root, log):
    from . import validate_r15
    log(f'validate root={root}')
    validate_r15.main(['--root', str(root)])
    return 'validate'


def step_stats(root, log):
    from . import stats_r15
    log(f'stats root={root}')
    stats_r15.main(['--root', str(root)])
    return 'stats'


def step_plots(root, log):
    from . import plots_r15
    log(f'plots root={root}')
    plots_r15.main(['--root', str(root)])
    return 'plots'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step', required=True,
                        choices=['finalize2d', '25d', 'validate', 'stats',
                                 'plots', 'all'])
    parser.add_argument('--root', type=Path, default=None)
    parser.add_argument('--budget', type=int, default=400)
    parser.add_argument('--passes', type=int, default=3)
    parser.add_argument('--flat-probe', type=int, default=12)
    parser.add_argument('--rr-rounds', type=int, default=2)
    parser.add_argument('--labels', default='A,B',
                        help='labels for finalize2d (default A,B)')
    args = parser.parse_args(argv)
    profile_r15.apply(verbose=True)
    from ..fslw import config as C
    root = _root(args)
    log_path = root / 'work' / 'r15_pipeline.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log_path, 'a', encoding='utf-8')

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        handle.write(line + '\n')
        handle.flush()

    log('=' * 70)
    log(f'command={vars(args)} radius={C.RADIUS_MM}')
    started = time.perf_counter()
    steps = (['finalize2d', '25d', 'validate', 'stats', 'plots']
             if args.step == 'all' else [args.step])
    try:
        for step in steps:
            if step == 'finalize2d':
                step_finalize2d(root, log, args.labels)
            elif step == '25d':
                step_25d(root, log, args)
            elif step == 'validate':
                step_validate(root, log)
            elif step == 'stats':
                step_stats(root, log)
            elif step == 'plots':
                step_plots(root, log)
            log(f'step {step} completed ({time.perf_counter() - started:.1f}s)')
    finally:
        handle.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
