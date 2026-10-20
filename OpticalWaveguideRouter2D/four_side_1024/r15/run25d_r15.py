"""R15 five-layer 2.5D runner.

Wraps :mod:`four_side_1024.fsd25d.run25d` so that

* the R15 process profile is applied before any fsd25d import (the transition
  radius and path3d defaults bind at import time),
* the fsd25d baseline schemes point at the **R15** 2D layouts produced in this
  round (``outputs/four_side_1024_v2_r15_v01/planes/V2/{A,B}``) instead of the
  frozen R40 layouts,
* the output goes to ``outputs/four_side_1024_v2_r15_v01/25d/...``.

Example::

    python -m four_side_1024.r15.run25d_r15 --scheme A --layers 5
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


def _routed_counts(root):
    counts = {}
    for label in ('A', 'B'):
        total = 0
        per_plane = {}
        for plane in ('z1', 'z2'):
            path = root / 'planes' / 'V2' / label / plane / 'routes.json'
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding='utf-8'))
            routed = sum(1 for record in payload.get('routes') or []
                         if record.get('status') == 'routed')
            per_plane[plane] = routed
            total += routed
        counts[label] = dict(total=total, per_plane=per_plane)
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scheme', choices=['A', 'B'], required=True)
    parser.add_argument('--layers', type=int, choices=[3, 5], default=5)
    parser.add_argument('--budget', type=int, default=400)
    parser.add_argument('--passes', type=int, default=3)
    parser.add_argument('--flat-probe', type=int, default=12)
    parser.add_argument('--rr-rounds', type=int, default=2)
    parser.add_argument('--rr-targets', type=int, default=64)
    parser.add_argument('--rr-rip', type=int, default=2)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--root', type=Path, default=None)
    args = parser.parse_args(argv)

    profile_r15.apply(verbose=True)
    from ..fslw import config as C
    from ..fsd25d import config25d as CFG
    from ..fsd25d import run25d

    root = Path(args.root) if args.root else Path(profile_r15.R15_ROOT)
    root = root if root.is_absolute() else Path(__file__).resolve().parents[2] / root
    counts = _routed_counts(root)
    print(f'[r15] radius={C.RADIUS_MM} mm; R15 2D baselines: {json.dumps(counts)}')
    for label, scheme in (('A', 'A'), ('B', 'B')):
        entry = CFG.SCHEMES[scheme]
        entry['baseline_root'] = root
        entry['baseline_algorithm'] = label
        entry['baseline_routed'] = counts[label]['total']
        entry['xy_model'] = 'd56' if scheme == 'A' else 'ortho90'
        print(f"[r15] scheme {scheme}: baseline_root={root} "
              f"algorithm={label} routed={counts[label]['total']}")
    out_dir = root / '25d' / f'scheme{args.scheme}' / f'layers{args.layers}'
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    run25d.main([
        '--scheme', args.scheme,
        '--layers', str(args.layers),
        '--budget', str(args.budget),
        '--passes', str(args.passes),
        '--flat-probe', str(args.flat_probe),
        '--rr-rounds', str(args.rr_rounds),
        '--rr-targets', str(args.rr_targets),
        '--rr-rip', str(args.rr_rip),
        '--limit', str(args.limit),
        '--out', str(out_dir),
    ])
    seconds = time.perf_counter() - started
    print(json.dumps(dict(scheme=args.scheme, layers=args.layers,
                          out=str(out_dir), seconds=round(seconds, 1)),
                     ensure_ascii=False))
    return dict(scheme=args.scheme, out_dir=str(out_dir))


if __name__ == '__main__':
    main()
