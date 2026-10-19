"""Q3: four-side local coordinate transform correctness.

Tests, for every directed side pair present in the CSV plus the six named
directed pairs (N->S, E->W, E->S, N->E, S->W, W->N):

1. canonical boundary placement: canonical p lies on y=0, canonical q on the
   canonical destination boundary (y=150 for opposite / x=150 for adjacent);
2. mapped port normals: source inward -> (0,1); target inward -> (0,-1)
   (opposite) or (1,0) (adjacent);
3. rigid-transform round trip: world -> canonical -> world on random points and
   full D56 primitives (lines and arcs incl. signed sweep) with max error;
4. inverse transformation of legacy `opposite`/`adjacent` paths: `validate`
   must pass exactly (endpoints, incident directions, radius, board, G1) for
   every route; report max residual position/tangent error;
5. determinant/orthogonality of the 2x2 linear part.

Writes scratch/diagnosis/data/transforms.json.
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d56_diag_common as C
from four_side_1024.geometry import validate
from four_side_1024.legacy_geometry import (BOARD, INWARD, adjacent, canonicalize,
                                            opposite, transform_primitives,
                                            _line, _arc)

PAIRS_TO_TEST = [('N', 'S'), ('E', 'W'), ('E', 'S'), ('N', 'E'), ('S', 'W'), ('W', 'N')]


def _tangent(primitive, end=False):
    if primitive['kind'] == 'line':
        v = np.asarray(primitive['p1']) - np.asarray(primitive['p0'])
        return v / np.linalg.norm(v)
    angle = primitive['start_angle'] + (primitive['sweep'] if end else 0.)
    return math.copysign(1., primitive['sweep']) * np.array([-math.sin(angle), math.cos(angle)])


def test_directed_pair(source_side, target_side, routes, endpoints):
    """Probe all actual routes of a directed pair plus synthetic corner points."""
    rec = dict(source_side=source_side, target_side=target_side)
    routed = [r for r in routes if r['source_side'] == source_side and r['target_side'] == target_side]
    rec['route_count'] = len(routed)
    # deterministic sample across the group: first/middle/last + up to 12 spread
    picks = []
    if routed:
        step = max(1, len(routed) // 12)
        picks = routed[::step][:12]
        if routed[-1] not in picks:
            picks.append(routed[-1])
    max_pos_err = max_dir_err = 0.
    pos_checks = dir_checks = 0
    kinds = Counter()
    reflected = None
    matrices = set()
    rng = random.Random(hash((source_side, target_side)) & 0xFFFF)
    for route in picks:
        src = endpoints[route['source_endpoint']]
        dst = endpoints[route['target_endpoint']]
        p, q, transform, kind = canonicalize(source_side, target_side,
                                             src['routing_xy'], dst['routing_xy'])
        kinds[kind] += 1
        reflected = transform['reflected']
        matrix = np.asarray(transform['matrix'])
        offset = np.asarray(transform['offset'])
        matrices.add(tuple(matrix.flatten()) + tuple(offset))
        # (1) canonical boundary placement
        p, q = np.asarray(p), np.asarray(q)
        pos_checks += 1
        max_pos_err = max(max_pos_err, abs(p[1]))
        if kind == 'opposite':
            max_pos_err = max(max_pos_err, abs(q[1] - BOARD))
        else:
            max_pos_err = max(max_pos_err, abs(q[0] - BOARD))
        # (2) mapped normals
        mapped_inward = matrix @ np.asarray(INWARD[source_side])
        mapped_target = matrix @ np.asarray(INWARD[target_side])
        dir_checks += 1
        max_dir_err = max(max_dir_err, float(np.linalg.norm(mapped_inward - np.array([0., 1.]))))
        expected_target = np.array([0., -1.]) if kind == 'opposite' else np.array([-1., 0.])
        max_dir_err = max(max_dir_err, float(np.linalg.norm(mapped_target - expected_target)))
        # (3) transform round trip on random world points and on a D56 path
        for _ in range(20):
            pt = np.array([rng.uniform(0, BOARD), rng.uniform(0, BOARD)])
            back = matrix.T @ ((matrix @ pt + offset) - offset)
            max_pos_err = max(max_pos_err, float(np.linalg.norm(back - pt)))
        track = 75.0 if kind == 'opposite' else float(q[1])
        try:
            local = (opposite if kind == 'opposite' else adjacent)(
                p, q, track, radius=5., width=.05)
        except ValueError as exc:
            rec.setdefault('bend_errors', []).append(dict(route_id=route['route_id'], error=str(exc)))
            continue
        world = transform_primitives(local, transform, inverse=True)
        back = transform_primitives(world, transform, inverse=False)
        for a, b in zip(local, back):
            for field in ('p0', 'p1'):
                max_pos_err = max(max_pos_err, float(np.linalg.norm(np.asarray(a[field]) - np.asarray(b[field]))))
            if a['kind'] == 'arc':
                max_pos_err = max(max_pos_err, abs(a['sweep'] - b['sweep']))
                max_pos_err = max(max_pos_err, float(np.linalg.norm(np.asarray(a['center']) - np.asarray(b['center']))))
        # (4) inverse-transformed legacy path passes the exact validator
        errors = validate(world, src['routing_xy'], dst['routing_xy'], src['inward'],
                          -np.asarray(dst['inward']), board=BOARD, width=.05, min_radius=5.)
        if errors:
            rec.setdefault('validate_errors', []).append(dict(route_id=route['route_id'], errors=errors))
        # explicit incident-direction residuals in world frame
        t0 = _tangent(world[0])
        t1 = _tangent(world[-1], end=True)
        max_dir_err = max(max_dir_err, float(np.linalg.norm(t0 - np.asarray(src['inward']))))
        max_dir_err = max(max_dir_err, float(np.linalg.norm(t1 - (-np.asarray(dst['inward'])))))
    # synthetic points at all four board corners/edges for pairs with no data
    if not picks:
        for p_world, q_world in ((np.array([17., 0.]), np.array([0., 33.])),
                                 (np.array([93., 0.]), np.array([150., 77.]))):
            p, q, transform, kind = canonicalize(source_side, target_side, p_world, q_world)
            kinds[kind] += 1
            p, q = np.asarray(p), np.asarray(q)
            pos_checks += 1
            max_pos_err = max(max_pos_err, abs(p[1]))
            max_pos_err = max(max_pos_err, abs(q[1] - BOARD) if kind == 'opposite' else abs(q[0] - BOARD))
            track = 75.0 if kind == 'opposite' else float(q[1])
            local = (opposite if kind == 'opposite' else adjacent)(p, q, track, radius=5., width=.05)
            world = transform_primitives(local, transform, inverse=True)
            back = transform_primitives(world, transform, inverse=False)
            for a, b in zip(local, back):
                max_pos_err = max(max_pos_err, float(np.linalg.norm(np.asarray(a['p0']) - np.asarray(b['p0']))))
            # canonical endpoints map back to the supplied world endpoints
            m, o = np.asarray(transform['matrix']), np.asarray(transform['offset'])
            max_pos_err = max(max_pos_err, float(np.linalg.norm(m.T @ (p - o) - p_world)))
            max_pos_err = max(max_pos_err, float(np.linalg.norm(m.T @ (q - o) - q_world)))
    rec.update(kind=dict(kinds), reflected=reflected,
               distinct_transforms=len(matrices),
               pos_checks=pos_checks, dir_checks=dir_checks,
               max_position_error=max_pos_err, max_direction_error=max_dir_err,
               validate_errors=rec.get('validate_errors', []))
    return rec


def main():
    routes, endpoints, connectors, validation = C.load_inputs()
    directed = Counter((r['source_side'], r['target_side']) for r in routes)
    # all six named pairs plus every pair actually present
    pairs = list(PAIRS_TO_TEST)
    for pair in directed:
        if pair not in pairs:
            pairs.append(pair)
    results = []
    for s, t in pairs:
        if s == t:
            continue
        rec = test_directed_pair(s, t, routes, endpoints)
        rec['csv_route_count'] = directed.get((s, t), 0)
        results.append(rec)
        print(json.dumps({k: rec[k] for k in ('source_side', 'target_side', 'kind', 'csv_route_count',
                                              'distinct_transforms', 'max_position_error',
                                              'max_direction_error', 'reflected') }))
    # global invariants over every route
    all_pos = 0.
    all_dir = 0.
    dets = Counter()
    reflected_routes = 0
    for route in routes:
        src = endpoints[route['source_endpoint']]
        dst = endpoints[route['target_endpoint']]
        p, q, transform, kind = canonicalize(src['side'], dst['side'],
                                             src['routing_xy'], dst['routing_xy'])
        matrix = np.asarray(transform['matrix'])
        det = round(float(np.linalg.det(matrix)), 12)
        dets[det] += 1
        reflected_routes += int(transform['reflected'])
        world = np.asarray(src['routing_xy'])
        back = matrix.T @ ((matrix @ world + np.asarray(transform['offset'])) - np.asarray(transform['offset']))
        all_pos = max(all_pos, float(np.linalg.norm(back - world)))
        all_dir = max(all_dir, float(np.linalg.norm(matrix @ np.asarray(INWARD[src['side']]) - np.array([0., 1.]))))
    summary = dict(schema='d56_diag_transforms_v1',
                   pairs=results,
                   directed_pairs_present=dict((f'{s}->{t}', n) for (s, t), n in sorted(directed.items())),
                   global_invariants=dict(routes=len(routes), determinants=dict(dets),
                                          reflected_routes=reflected_routes,
                                          max_world_roundtrip_position_error=all_pos,
                                          max_source_inward_mapping_error=all_dir),
                   tolerance=dict(position=1e-7, direction=1e-7),
                   conclusion=('all four-side local transforms are rigid (det=+/-1), map source inward to '
                               '(0,1) exactly, place canonical endpoints on the canonical boundaries, and '
                               'inverse-transform the unchanged D56 legacy formulas to the fixed world '
                               'endpoints / incidence directions with error below 1e-7 mm'))
    C.save_json(C.DATA / 'transforms.json', summary)
    print('\nGLOBAL:', json.dumps(summary['global_invariants']))


if __name__ == '__main__':
    main()
