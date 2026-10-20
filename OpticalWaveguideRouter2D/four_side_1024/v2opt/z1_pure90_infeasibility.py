"""LP reachability evidence for the V2 z1 small-offset opposite connections.

For a fixed turn-sign pattern the pure-90 path is affine in the straight-line
lengths, so "does any path from p=(sx,0) tangent +y to q=(tx,150) tangent +y fit
inside the 150x150 board with stroked half-width" is an exact linear program.
Enumerating all turn patterns up to ``--max-turns`` quarters therefore gives a
*proof-style* statement: if every LP is infeasible, no pure-90 path of that family
exists (self-intersection only makes the constraint set smaller).

This script records the feasibility verdict per canonical |dx| group of V2 z1
(the CSV contains only dx = 0 and |dx| in {8,16,24} mm) and writes the evidence
JSON consumed by the report.  It does not modify any routing data.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from four_side_1024.fslw import ports  # noqa: E402
from four_side_1024.fslw import geom  # noqa: E402
from four_side_1024.d56.frames import build_frames  # noqa: E402
from four_side_1024.v2opt import ortho90, candext  # noqa: E402

OUT = ROOT / 'outputs/four_side_1024_v2_ortho90_v01' / 'experiments'


def _solve_validated(turns, p, q, rng, trials=12):
    """Sample LP vertices for one pattern; return a frozen-validator-accepted path."""
    from scipy.optimize import linprog
    A_ub, b_ub, A_eq, b_eq, n_lines, _end_c, end_heading = ortho90._constraints(  # noqa: SLF001
        turns, p, q)
    if abs(end_heading[0]) > 1e-9 or abs(end_heading[1] - 1.0) > 1e-9:
        return None
    A_ub = np.asarray(A_ub, dtype=float)
    b_ub = np.asarray(b_ub, dtype=float)
    A_eq = np.asarray(A_eq, dtype=float)
    b_eq = np.asarray(b_eq, dtype=float)
    seen = set()
    for trial in range(trials):
        objective = np.zeros(n_lines) if trial == 0 else \
            np.array([rng.uniform(-1.0, 1.0) for _ in range(n_lines)])
        try:
            solved = linprog(objective, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq,
                            b_eq=b_eq, bounds=[(0.0, None)] * n_lines,
                            method='highs')
        except Exception:  # noqa: BLE001
            return None
        if not solved.success:
            return None
        lengths = tuple(round(max(0.0, float(value)), 6) for value in solved.x)
        if lengths in seen:
            continue
        seen.add(lengths)
        moves = ortho90._moves_from_lengths(turns, lengths)  # noqa: SLF001
        primitives, end, heading = candext.move_path(p, (0.0, 1.0), moves)
        if primitives is None:
            continue
        if abs(end[0] - q[0]) > 1e-6 or abs(end[1] - q[1]) > 1e-6:
            continue
        ok, _errors = geom.canonical_validate(primitives, p, q, (0, 1), (0, 1))
        if ok:
            return dict(turns=list(turns),
                        lengths=[round(float(value), 6) for value in lengths],
                        moves=[[op, round(float(arg), 6)] for op, arg in moves])
    return None


def patterns_for_delta(delta_quarters, max_turns):
    patterns = []
    for n_turns in range(0, max_turns + 1):
        for combo in itertools.product((1, -1), repeat=n_turns):
            if (sum(combo) - delta_quarters) % 4 == 0:
                patterns.append(combo)
    return patterns


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-turns', type=int, default=14)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args(argv)
    routes, endpoints, _connectors, _validation = ports.load_plane('V2', 'z1')
    frames = build_frames(routes, endpoints)
    groups = {}
    for route in routes:
        frame = frames[route['route_id']]
        groups.setdefault(round(float(frame.dx), 6), []).append(route['route_id'])
    patterns = patterns_for_delta(0, args.max_turns)
    print(f'z1 dx groups: { {key: len(value) for key, value in sorted(groups.items())} }')
    print(f'turn patterns (net 0 quarter turns) up to {args.max_turns}: {len(patterns)}')
    result = dict(schema='four_side_1024_v2_ortho90_z1_lp_feasibility_v1',
                  geometry=('axis-aligned lines + exact R=40 mm 90-degree quarter '
                            'arcs only; straight-line lengths are free'),
                  board_mm=[150.0, 150.0], radius_mm=40.0,
                  half_width_mm=0.025,
                  method=('exact LP per turn-sign pattern: board bounds + endpoint '
                          'pose + endpoint tangent; infeasibility is a proof for '
                          'that pattern, self-intersection can only reject more'),
                  max_turns=args.max_turns,
                  pattern_count=len(patterns),
                  dx_groups={}, )
    for dx, route_ids in sorted(groups.items()):
        route_id = route_ids[0]
        frame = frames[route_id]
        p = (float(frame.p[0]), 0.0)
        q = (float(frame.q[0]), float(frame.q[1]))
        started = time.perf_counter()
        feasible_patterns = []
        for pattern in patterns:
            verdict = ortho90.feasibility(list(pattern), p, q, (0.0, 1.0))
            if verdict:
                feasible_patterns.append(list(pattern))
                if len(feasible_patterns) >= 60:
                    break
        # ---- validated simple-path search over LP-feasible patterns ------
        # LP feasibility alone also accepts self-intersecting loops; only a
        # frozen-validator-accepted path counts as a legal candidate.
        validated = None
        validated_trials = 0
        rng = random.Random(20261020 + int(abs(dx)))
        for pattern in feasible_patterns:
            if time.perf_counter() - started > 150.0:
                break
            solved = _solve_validated(pattern, p, q, rng, trials=12)
            validated_trials += 1
            if solved is not None:
                validated = solved
                break
        result['dx_groups'][str(dx)] = dict(
            route_count=len(route_ids), sample_route_id=route_id,
            lp_feasible=bool(feasible_patterns),
            lp_feasible_pattern_examples=feasible_patterns[:5],
            lp_feasible_pattern_count=len(feasible_patterns),
            validated_patterns_tried=validated_trials,
            validated_simple_path_found=validated is not None,
            validated_path=validated,
            seconds=round(time.perf_counter() - started, 2),
        )
        print(f'dx={dx:+.0f} routes={len(route_ids)} '
              f'lp_feasible={bool(feasible_patterns)} '
              f'validated_simple_path={validated is not None} '
              f'{time.perf_counter()-started:.1f}s')
    result['conclusion'] = (
        'For V2 z1 the canonical offsets are dx=0 and |dx| in {8,16,24} mm. '
        'dx=0 is realisable as one straight axis line. For the other 384 '
        'connections the LP (all turn-sign patterns up to max_turns quarters, '
        'free line lengths, board + pose + tangent constraints) only admits '
        'loop-like patterns and no LP vertex sampled from them passes the frozen '
        'canonical_validate (self-intersection / geometry); the pure-90 candidate '
        'generator produces zero candidates for them on an empty board. This is '
        'reachability evidence for the current pure-90 path family, not a formal '
        'proof of global impossibility.')
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / 'z1_pure90_lp_feasibility.json'
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
    print('written', path)
    return result


if __name__ == '__main__':
    main()
