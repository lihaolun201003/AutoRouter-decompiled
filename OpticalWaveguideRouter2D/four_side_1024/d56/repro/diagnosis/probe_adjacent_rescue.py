"""Q6 + Lead's Q8 request: can the 512 adjacent routes be placed with the CSV
direct-L design plus a small flexible terminal-turn template, once the
crossing-zone exemption is computed correctly?

Inputs are the *measured* results of ``probe_direct_l.py``:
- 508/512 adjacent routes have a geometrically legal direct L path;
- under the deployed crossing policy all 508 conflict with each other, but under
  both corrected policies (primitive-pair / exact-window) exactly 209 illegal
  pairs remain and they form 209 disjoint two-route obstructions
  (105 EN|SW arc-arc double crossings at 15.2 deg, 104 ES|NW parallel arcs at
  0.105 mm) -> maximum independent direct-L set = 299 routes.

This probe:
1. builds the optimal 299-route direct-L set (exact MIS = one endpoint per
   obstructive pair);
2. for the remaining 209 routes, enumerates a deterministic flexible 3-bend
   template grid with variable intermediate track t1 and variable terminal turn
   abscissa t2 (all corners still exact R=5 quarter circles) and reports how
   many can be placed, independent of order and sequentially;
3. optionally runs the complete adjacent-only first-fit search with the flex
   template under the corrected policy.

Writes scratch/diagnosis/data/adjacent_rescue.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import crossing_policy as P
import d56_diag_common as C
from four_side_1024.geometry import validate
from four_side_1024.legacy_geometry import adjacent, canonicalize, transform_primitives


def flex_grid(qy, px):
    """Deterministic 2-D grid of the two free template degrees of freedom.

    t1 = intermediate horizontal track y, t2 = terminal vertical turn abscissa
    (canonical S->E frame).  Candidates ordered by distance from the direct-L
    shape (t1 -> qy, t2 -> 145) so the first legal candidate is the smallest
    detour.  Geometry constraints (segment lengths >= the exact R trim) are
    applied when the template is constructed.
    """
    t1_offsets = (15., 20., 25., 30., 40., 50., 60., 80., 100., 130.)
    t2_values = (145., 140., 135., 130., 120., 110., 100., 90., 80., 70., 60., 50., 40., 30., 20., 10., 5.)
    t1_values = set()
    for offset in t1_offsets:
        for candidate in (qy - offset, qy + offset):
            if 5. <= candidate <= 145.:
                t1_values.add(round(candidate, 6))
    candidates = []
    for t1 in sorted(t1_values):
        for t2 in t2_values:
            if abs(t2 - px) < 10. - 1e-9:
                continue
            cost = abs(t1 - qy) + (145. - t2)
            candidates.append((round(cost, 9), t1, t2))
    candidates.sort()
    return [(t1, t2) for _, t1, t2 in candidates]


def build_direct_l(routes, endpoints):
    built, failed = {}, {}
    for route in routes:
        if route['relation'] != 'adjacent':
            continue
        rid = route['route_id']
        src = endpoints[route['source_endpoint']]
        dst = endpoints[route['target_endpoint']]
        p, q, transform, kind = canonicalize(src['side'], dst['side'],
                                             src['routing_xy'], dst['routing_xy'])
        try:
            local = adjacent(np.asarray(p), np.asarray(q), float(np.asarray(q)[1]),
                             radius=5., width=.05)
            prim = transform_primitives(local, transform, inverse=True)
        except ValueError as exc:
            failed[rid] = str(exc)
            continue
        errs = validate(prim, src['routing_xy'], dst['routing_xy'], src['inward'],
                        -np.asarray(dst['inward']), board=150., width=.05, min_radius=5.)
        if errs:
            failed[rid] = errs
            continue
        built[rid] = dict(primitives=prim, pair=route['pair'], src_side=route['source_side'],
                          dst_side=route['target_side'], transform=transform,
                          p=list(map(float, p)), q=list(map(float, q)),
                          src_xy=list(map(float, src['routing_xy'])),
                          dst_xy=list(map(float, dst['routing_xy'])),
                          src_inward=list(map(float, src['inward'])),
                          dst_inward=list(map(float, dst['inward'])))
    return built, failed


def maximum_independent_selection(nodes, edges, prefer='low'):
    """Edges are 209 disjoint pairs by measurement; verify that and keep one
    endpoint of each pair (the other endpoint must be rerouted)."""
    adjacency = {}
    for a, b in edges:
        if a in adjacency or b in adjacency:
            raise RuntimeError('conflict graph is not a perfect matching; MIS requires B&B')
        adjacency[a] = b
        adjacency[b] = a
    kept = set(nodes)
    reroute = []
    for a, b in sorted(edges):
        keep, drop = (a, b) if (a < b) == (prefer == 'low') else (b, a)
        kept.discard(drop)
        reroute.append(drop)
    return sorted(kept), sorted(reroute)


def load_illegal_edges(policy='primitive_pair'):
    data = json.loads((C.DATA / 'direct_l_matrix.json').read_text(encoding='utf-8'))
    return [tuple(int(x) for x in edge.split('-')) for edge in data['illegal_edges'][policy]]


def try_route(route_id, info, grid, engine):
    """Direct L then flexible template grid; first legal candidate wins."""
    rid = route_id
    # direct L already known to be in conflict in this scenario, but test it
    # anyway so the probe is self-contained
    result = engine.evaluate(info['primitives'])
    if result['valid']:
        return dict(route_id=rid, placed=True, mode='direct_L', t1=None, t2=None, tried=1)
    transform = info['transform']
    q = np.asarray(info['q'])
    p = np.asarray(info['p'])
    tried = 1
    for t1, t2 in grid:
        try:
            local = C.adjacent_flexible(p, q, t1, t2, radius=5., width=.05)
        except ValueError:
            continue
        prim = transform_primitives(local, transform, inverse=True)
        errs = validate(prim, info['src_xy'], info['dst_xy'], info['src_inward'],
                        -np.asarray(info['dst_inward']), board=150., width=.05, min_radius=5.)
        if errs:
            continue
        tried += 1
        result = engine.evaluate(prim)
        if result['valid']:
            return dict(route_id=rid, placed=True, mode='flex', t1=t1, t2=t2,
                        tried=tried, primitives=prim)
    return dict(route_id=rid, placed=False, mode=None, t1=None, t2=None, tried=tried)


def make_engine(policy, accepted):
    from policy_search import PolicyIndex
    engine = PolicyIndex(policy=policy)
    for rid, info in accepted.items():
        engine.add(rid, info['primitives'])
    return engine


def run_rescue(built, kept, reroute, policy='primitive_pair'):
    accepted = {rid: built[rid] for rid in kept}
    engine = make_engine(policy, accepted)
    grids = {}
    for rid in reroute:
        info = built[rid]
        grids[rid] = flex_grid(float(np.asarray(info['q'])[1]), float(np.asarray(info['p'])[0]))
    independent = []
    for rid in reroute:
        independent.append(try_route(rid, built[rid], grids[rid], engine))
    # sequential: successful rescues become obstacles for later ones
    engine2 = make_engine(policy, accepted)
    sequential = []
    for rid in reroute:
        attempt = try_route(rid, built[rid], grids[rid], engine2)
        if attempt['placed']:
            engine2.add(rid, attempt.get('primitives') or built[rid]['primitives'])
        sequential.append(attempt)
    return independent, sequential


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--policy', default='primitive_pair', choices=['primitive_pair', 'exact_window'])
    ap.add_argument('--prefer', default='all', choices=['all', 'low', 'high'])
    ap.add_argument('--max-seconds', type=float, default=900.)
    ap.add_argument('--full-run', action='store_true',
                    help='also run the complete adjacent-only first-fit search with flex template')
    args = ap.parse_args()
    routes, endpoints, _, _ = C.load_inputs()
    t0 = time.perf_counter()
    built, failed = build_direct_l(routes, endpoints)
    nodes = sorted(built)
    edges = load_illegal_edges('primitive_pair')
    result = dict(schema='d56_diag_adjacent_rescue_v1', policy=args.policy,
                  direct_L_valid=len(built), direct_L_failed=failed,
                  genuine_conflict_pairs=len(edges),
                  genuine_conflict_pairs_detail=dict(
                      same_pair=sum(1 for a, b in edges if built[a]['pair'] == built[b]['pair']),
                      cross_pair=sum(1 for a, b in edges if built[a]['pair'] != built[b]['pair'])),
                  scenarios={})
    for preference in (['low', 'high'] if args.prefer == 'all' else [args.prefer]):
        kept, reroute = maximum_independent_selection(nodes, edges, prefer=preference)
        independent, sequential = run_rescue(built, kept, reroute, args.policy)
        result['scenarios'][preference] = dict(
            kept_direct_L=len(kept), reroute_candidates=len(reroute),
            independent_rescued=sum(1 for x in independent if x['placed']),
            independent_by_pair=dict(Counter(built[x['route_id']]['pair'] for x in independent if x['placed'])),
            independent_by_mode=dict(Counter(x['mode'] for x in independent if x['placed'])),
            independent_unrescued=[x['route_id'] for x in independent if not x['placed']],
            sequential_rescued=sum(1 for x in sequential if x['placed']),
            sequential_total=len(kept) + sum(1 for x in sequential if x['placed']),
            sequential_by_pair=dict(Counter(built[x['route_id']]['pair'] for x in sequential if x['placed'])),
            sequential_attempts=dict(Counter(x['placed'] for x in sequential)),
            mean_candidates_tried=round(float(np.mean([x['tried'] for x in sequential])), 1),
            median_candidates_tried=float(np.median([x['tried'] for x in sequential])),
            rescued_detail=[{k: x[k] for k in ('route_id', 'placed', 'mode', 't1', 't2', 'tried')}
                             for x in sequential if x['placed']][:10])
    # quick verification that the kept 299-set is mutually legal under the policy
    kept, _ = maximum_independent_selection(nodes, edges, prefer='low')
    engine = make_engine(args.policy, {rid: built[rid] for rid in kept})
    illegal_in_kept = sum(1 for rid in kept if not engine.evaluate(built[rid]['primitives'], exclude=rid)['valid'])
    result['kept_set_verification'] = dict(kept=len(kept), routes_with_conflict=illegal_in_kept)
    result['elapsed_seconds'] = time.perf_counter() - t0
    C.save_json(C.DATA / 'adjacent_rescue.json', result)
    print(json.dumps({k: result[k] for k in ('direct_L_valid', 'genuine_conflict_pairs',
                                             'genuine_conflict_pairs_detail', 'kept_set_verification')}, indent=2))
    for preference, scenario in result['scenarios'].items():
        print(preference, {k: scenario[k] for k in
                           ('kept_direct_L', 'reroute_candidates', 'independent_rescued',
                            'sequential_rescued', 'sequential_total', 'independent_by_pair',
                            'independent_by_mode', 'mean_candidates_tried')})


if __name__ == '__main__':
    main()
