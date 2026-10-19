"""Probe D: mutual compatibility of the CSV-designed direct-L adjacent paths.

The CSV is designed so that adjacent connections can be routed as a direct
single-bend L (original R=5 quarter arc): 508/512 such L paths are exact
geometrically legal on their own.  This probe builds the full 508x508 pairwise
conflict matrix under three crossing policies (deployed, primitive-pair, exact
window), classifies conflicts by segment/corner type, and measures how many
routes a sequential first-fit can place under different orders / policies.

Writes:
  scratch/diagnosis/data/direct_l_matrix.json   (aggregates + classification)
  scratch/diagnosis/data/direct_l_orders.json   (order experiments)
  scratch/diagnosis/data/direct_l_pairs.csv     (per conflicting pair detail)
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import crossing_policy as P
import d56_diag_common as C
from four_side_1024.conflicts import EPS, _bbox_distance, _exact_distance, _kept_primitives, _pieces_too_close
from four_side_1024.legacy_geometry import adjacent, canonicalize, transform_primitives
from four_side_1024.geometry import validate


def build_direct_l(routes, endpoints):
    built = {}
    errors = {}
    components = {}
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
            errors[rid] = dict(error=str(exc), pair=route['pair'],
                               src=route['source_endpoint'], dst=route['target_endpoint'])
            continue
        errs = validate(prim, src['routing_xy'], dst['routing_xy'], src['inward'],
                        -np.asarray(dst['inward']), board=150., width=.05, min_radius=5.)
        if errs:
            errors[rid] = dict(error='validate', detail=errs, pair=route['pair'])
            continue
        built[rid] = prim
        components[rid] = dict(pair=route['pair'], src=route['source_endpoint'],
                               dst=route['target_endpoint'],
                               src_side=route['source_side'], dst_side=route['target_side'],
                               src_xy=list(src['routing_xy']), dst_xy=list(dst['routing_xy']),
                               canon_p=list(map(float, p)), canon_q=list(map(float, q)))
    return built, components, errors


def conflict_location(route_a, route_b, clearance, window_a=None, window_b=None):
    """Approximate location of the first spacing violation plus the primitive
    indices that violate.  Reused for classification only."""
    ia = window_a or []
    outside_a = _kept_primitives(route_a, ia) if ia else route_a.primitives
    best = None
    for i, a in enumerate(outside_a):
        for j, b in enumerate(route_b.primitives):
            if _bbox_distance(a.bounds, b.bounds) >= clearance - EPS:
                continue
            distance = _exact_distance(a, b)
            if distance < clearance - EPS and (best is None or distance < best[2]):
                point = ((a.p0[0] + a.p1[0] + b.p0[0] + b.p1[0]) / 4.,
                         (a.p0[1] + a.p1[1] + b.p0[1] + b.p1[1]) / 4.)
                best = (a.kind, b.kind, distance, point)
    if best:
        return best
    outside_b = _kept_primitives(route_b, window_b) if window_b else route_b.primitives
    for i, a in enumerate(outside_b):
        for j, b in enumerate(route_a.primitives):
            if _bbox_distance(a.bounds, b.bounds) >= clearance - EPS:
                continue
            distance = _exact_distance(a, b)
            if distance < clearance - EPS and (best is None or distance < best[2]):
                point = ((a.p0[0] + a.p1[0] + b.p0[0] + b.p1[0]) / 4.,
                         (a.p0[1] + a.p1[1] + b.p0[1] + b.p1[1]) / 4.)
                best = (a.kind, b.kind, distance, point)
    return best


def orientation(primitive):
    if primitive.kind == 'arc':
        return 'arc'
    if abs(primitive.p1[0] - primitive.p0[0]) < 1e-9:
        return 'vertical'
    if abs(primitive.p1[1] - primitive.p0[1]) < 1e-9:
        return 'horizontal'
    return 'diagonal'


def corner_of(point):
    x, y = point
    return ('S' if y < 75 else 'N') + ('W' if x < 75 else 'E')


def conflict_detail(route_a, route_b, clearance):
    """Return the crossing/window geometry of a deployed-illegal pair."""
    crossings, overlaps = P.collect_crossings(route_a, route_b)
    ia, ib = [], []
    for c in crossings:
        half = clearance / c['sine'] + 2 * P.SAGITTA_DEFAULT
        ia.append((c['sa'] - half, c['sa'] + half))
        ib.append((c['sb'] - half, c['sb'] + half))
    violating = conflict_location(route_a, route_b, clearance, ia, ib)
    return dict(crossings=[dict(sine=c['sine'], angle_deg=float(np.degrees(np.arcsin(min(1., c['sine'])))),
                                point=list(map(float, c['point'])),
                                primitive_pair=(c['i'], c['j'])) for c in crossings],
                violating_kinds=None if not violating else (violating[0], violating[1]),
                violating_distance=None if not violating else violating[2],
                violating_point=None if not violating else list(map(float, violating[3])))


def greedy_mis(nodes, edges):
    """Maximal independent set by repeatedly removing the highest-degree vertex
    (then local endpoint swap improvement).  Deterministic lower bound."""
    adjacency = defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    alive = set(nodes)
    while True:
        candidates = [v for v in alive if adjacency[v] & alive]
        if not candidates:
            break
        v = max(candidates, key=lambda x: (len(adjacency[x] & alive), x))
        alive.discard(v)
    # local improvement: add back a removed vertex if its neighbours in set are gone
    improved = True
    while improved:
        improved = False
        for v in list(set(nodes) - alive):
            if not (adjacency[v] & alive):
                alive.add(v)
                improved = True
    return len(alive)


def mis_or_fallback(nodes, edges):
    try:
        return exact_mis(nodes, edges), 'exact'
    except (RuntimeError, RecursionError):
        return greedy_mis(nodes, edges), 'greedy_fallback'


def exact_mis(nodes, edges):
    """Maximum independent set of a sparse graph via complement = minimum over
    connected components of (|V| - min vertex cover), exact B&B."""
    adjacency = defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    # connected components
    seen = set()
    total = 0
    for start in nodes:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        comp = []
        while stack:
            v = stack.pop()
            comp.append(v)
            for w in adjacency[v]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        total += len(comp) - min_vertex_cover(comp, adjacency)
    return total


def min_vertex_cover(comp, adjacency):
    """Exact minimum vertex cover on a sparse component (branch on an edge)."""
    from functools import lru_cache
    comp = tuple(sorted(comp))
    edge_list = tuple(sorted({tuple(sorted((a, b))) for a in comp for b in adjacency[a] if b in comp}))

    sys.setrecursionlimit(10000)

    def solve(edges, excluded=frozenset()):
        # edges: tuple of (u,v); excluded: vertices already in cover
        edges = tuple((u, v) for (u, v) in edges if u not in excluded and v not in excluded)
        if not edges:
            return len(excluded)
        if len(edges) > 400:
            raise RuntimeError('component too large for exact cover')
        # branch on highest-degree vertex for speed
        deg = Counter()
        for u, v in edges:
            deg[u] += 1
            deg[v] += 1
        u, _ = deg.most_common(1)[0]
        # option 1: put u in cover
        best = solve(edges, excluded | {u})
        # option 2: exclude u -> all neighbours must be in cover
        neighbours = frozenset(v for a, b in edges for uu, v in ((a, b), (b, a)) if uu == u and v not in excluded)
        best = min(best, solve(edges, excluded | neighbours))
        return best

    return solve(edge_list)


def greedy_orders(nodes, conflict_matrix, component_meta, orders):
    """First-fit placement for each order; returns counts and which ids placed."""
    results = {}
    for name, order in orders.items():
        placed = []
        placed_set = set()
        for rid in order:
            conflict = False
            for other in placed:
                if conflict_matrix.get((min(rid, other), max(rid, other)), False):
                    conflict = True
                    break
            if not conflict:
                placed.append(rid)
                placed_set.add(rid)
        results[name] = dict(placed=len(placed), ids=placed,
                             by_pair=dict(Counter(component_meta[rid]['pair'] for rid in placed)))
    return results


def build_orders(nodes, component_meta, conflict_graph_degrees):
    orders = {}
    orders['route_id_asc'] = sorted(nodes)
    orders['route_id_desc'] = sorted(nodes, reverse=True)
    orders['src_coord_asc'] = sorted(nodes, key=lambda r: (component_meta[r]['src_xy'][1],
                                                           component_meta[r]['src_xy'][0]))
    orders['src_coord_desc'] = sorted(nodes, key=lambda r: (-component_meta[r]['src_xy'][1],
                                                            -component_meta[r]['src_xy'][0]))
    orders['dst_coord_asc'] = sorted(nodes, key=lambda r: (component_meta[r]['dst_xy'][1],
                                                           component_meta[r]['dst_xy'][0]))
    orders['pair_then_coord'] = sorted(nodes, key=lambda r: (component_meta[r]['pair'],
                                                             component_meta[r]['src_xy'][1]))
    orders['min_degree_first'] = sorted(nodes, key=lambda r: (conflict_graph_degrees.get(r, 0), r))
    orders['max_degree_last'] = sorted(nodes, key=lambda r: (conflict_graph_degrees.get(r, 0), r))
    for seed in (1, 2, 3, 7, 11, 42):
        order = list(nodes)
        random.Random(seed).shuffle(order)
        orders[f'random_{seed}'] = order
    return orders


def main():
    routes, endpoints, _, _ = C.load_inputs()
    built, components, errors = build_direct_l(routes, endpoints)
    nodes = sorted(built)
    # coarse prefilter for the pair matrix: route bounding boxes
    prepared = {rid: P.prepare(built[rid]) for rid in nodes}
    bounds = {rid: prepared[rid].exact_bounds for rid in nodes}
    pair_rows = []
    matrices = {name: {} for name in P.POLICIES}
    reasons = {name: Counter() for name in P.POLICIES}
    details = {}
    n = len(nodes)
    skipped_improved = 0
    for i in range(n):
        rid_a = nodes[i]
        ba = bounds[rid_a]
        pa = prepared[rid_a]
        for j in range(i + 1, n):
            rid_b = nodes[j]
            bb = bounds[rid_b]
            # broad phase: inflated bbox inclusive of crossing windows etc.
            if (ba[0] > bb[2] + 2.0 or bb[0] > ba[2] + 2.0 or
                    ba[1] > bb[3] + 2.0 or bb[1] > ba[3] + 2.0):
                for name in P.POLICIES:
                    matrices[name][(rid_a, rid_b)] = False
                continue
            pb = prepared[rid_b]
            key = (rid_a, rid_b)
            deployed = P.pair_check_deployed(pa, pb)
            matrices['deployed'][key] = not deployed['valid']
            if not deployed['valid']:
                reasons['deployed'][deployed['reason']] += 1
                details[f'{rid_a}-{rid_b}'] = dict(
                    pair_labels=(components[rid_a]['pair'], components[rid_b]['pair']),
                    **conflict_detail(pa, pb, P.CLEARANCE_DEFAULT))
            if deployed['valid'] and deployed.get('crossings', 0) == 0:
                # no crossing -> no exemption -> all policies decide identically
                matrices['primitive_pair'][key] = matrices['exact_window'][key] = False
                skipped_improved += 1
                continue
            for name in ('primitive_pair', 'exact_window'):
                res = P.POLICIES[name](pa, pb)
                matrices[name][key] = not res['valid']
                if not res['valid']:
                    reasons[name][res['reason']] += 1
    # symmetric sanity: all matrices keyed by sorted id pair
    # verify against the deployed ConflictIndex on a deterministic sample
    from four_side_1024.conflicts import ConflictIndex
    rng = random.Random(5)
    sample = rng.sample(list(matrices['deployed']), min(2000, len(matrices['deployed'])))
    verify_mismatch = 0
    for (a, b) in sample:
        idx = ConflictIndex(width=.05, gap=.125, sagitta=.0005)
        idx.add(b, built[b])
        res = idx.evaluate(built[a])
        if bool(matrices['deployed'][(a, b)]) != (not res['valid']):
            verify_mismatch += 1
    # conflict degree histograms
    degree = {}
    for name in P.POLICIES:
        deg = Counter()
        for rid in nodes:
            deg[sum(1 for (a, b), bad in matrices[name].items() if bad and (a == rid or b == rid))] += 1
        degree[name] = dict(sorted(deg.items()))
    # classification of deployed conflicts
    class_counter = Counter()
    region_counter = Counter()
    pair_combo = Counter()
    angle_hist = Counter()
    for key, det in details.items():
        kinds = det['violating_kinds'] or ('unknown', 'unknown')
        class_counter[(det['crossings'] and 'has_crossing' or 'no_crossing',
                       tuple(sorted(kinds)))] += 1
        if det['violating_point']:
            region_counter[corner_of(det['violating_point'])] += 1
        pair_combo[tuple(sorted(det['pair_labels']))] += 1
        if det['crossings']:
            angle_hist[round(min(c['angle_deg'] for c in det['crossings']))] += 1
        if det['violating_distance'] is not None:
            angle_hist.setdefault('spacing_distance_bins', Counter())[
                round(det['violating_distance'], 3)] += 1
    # genuine conflicts under the best (exact-window) policy: classify too
    genuine = []
    for (a, b), bad in matrices['primitive_pair'].items():
        if not bad:
            continue
        res = P.pair_check_primitive_pair(prepared[a], prepared[b])
        genuine.append(dict(a=a, b=b, reason=res['reason'], angle_deg=res.get('angles'),
                            distance=res.get('distance'),
                            pair_labels=(components[a]['pair'], components[b]['pair']),
                            kinds=res.get('kinds')))
    # ordering experiments for every policy
    orders = build_orders(nodes, components, {rid: sum(
        1 for (a, b), bad in matrices['deployed'].items() if bad and (a == rid or b == rid)) for rid in nodes})
    order_results = {}
    for name in P.POLICIES:
        order_results[name] = greedy_orders(nodes, matrices[name], components, orders)
    # maximum independent set: exact for the sparse primitive-pair graph, greedy
    # lower bound for the exact-window graph (dense-ish; B&B not warranted)
    edges_pp = [k for k, bad in matrices['primitive_pair'].items() if bad]
    mis_pp, mis_pp_method = mis_or_fallback(nodes, edges_pp)
    edges_exact = [k for k, bad in matrices['exact_window'].items() if bad]
    mis_exact, mis_exact_method = greedy_mis(nodes, edges_exact), 'greedy'
    confusion = {}
    names = list(P.POLICIES)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            na, nb = names[a], names[b]
            confusion[f'{na}_vs_{nb}'] = dict(
                both_legal=sum(1 for k in matrices[na] if not matrices[na][k] and not matrices[nb][k]),
                a_legal_b_illegal=sum(1 for k in matrices[na] if not matrices[na][k] and matrices[nb][k]),
                a_illegal_b_legal=sum(1 for k in matrices[na] if matrices[na][k] and not matrices[nb][k]),
                both_illegal=sum(1 for k in matrices[na] if matrices[na][k] and matrices[nb][k]))
    classification = dict(
        class_counts=dict((f'{k[0]}|{k[1]}', v) for k, v in class_counter.items()),
        pair_label_combos=dict((f'{k[0]}|{k[1]}', v) for k, v in pair_combo.items()),
        violating_region=dict(region_counter),
        crossing_angle_deg_hist=dict((str(k), v) for k, v in angle_hist.items()
                                     if not isinstance(v, Counter)),
        spacing_distance_bins=dict((f'{k:.3f}', v) for k, v in
                                   next((v for k, v in angle_hist.items()
                                         if isinstance(v, Counter) and k == 'spacing_distance_bins'),
                                        Counter()).items()),
    )
    summary = dict(
        schema='d56_diag_direct_l_v1',
        adjacent_routes=512, direct_L_geometrically_valid=len(nodes), direct_L_errors=errors,
        pair_count=len(matrices['deployed']),
        policies={name: dict(illegal_pairs=sum(1 for v in matrices[name].values() if v),
                             reason_counts=dict(reasons[name]),
                             conflict_degree_histogram=degree[name],
                             routes_with_any_conflict=sum(
                                 1 for rid in nodes if any(
                                     bad and (a == rid or b == rid)
                                     for (a, b), bad in matrices[name].items())))
                  for name in P.POLICIES},
        illegal_edges={name: [f'{a}-{b}' for (a, b), bad in matrices[name].items() if bad]
                       for name in P.POLICIES},
        deployed_conflict_classification=classification,
        genuine_conflicts_improved=dict(count=len(genuine), reason_counts=dict(Counter(g['reason'] for g in genuine)),
                                        by_pair_label_combo=dict(Counter('|'.join(sorted(g['pair_labels'])) for g in genuine)),
                                        samples=genuine[:20]),
        order_experiments=order_results,
        policy_confusion=confusion,
        maximum_independent_set=dict(primitive_pair_policy=mis_pp, primitive_pair_method=mis_pp_method,
                                    exact_window_policy=mis_exact, exact_window_method=mis_exact_method,
                                    direct_L_routes=len(nodes),
                                    deployed_estimate='greedy only (dense conflict graph)'),
        verification=dict(compared=len(sample), mismatch_vs_ConflictIndex=verify_mismatch),
    )
    C.save_json(C.DATA / 'direct_l_matrix.json', summary)
    with (C.DATA / 'direct_l_pairs.csv').open('w', newline='', encoding='utf-8') as f:
        import csv
        w = csv.writer(f)
        w.writerow(['route_a', 'route_b', 'policy', 'illegal', 'reason'])
        for name in P.POLICIES:
            for (a, b), bad in matrices[name].items():
                if bad:
                    w.writerow([a, b, name, 1, ''])
    print(json.dumps(dict(direct_L=len(nodes), errors=len(errors),
                          policies={name: dict(illegal=summary['policies'][name]['illegal_pairs'],
                                               reasons=summary['policies'][name]['reason_counts'],
                                               with_conflict=summary['policies'][name]['routes_with_any_conflict'])
                                    for name in P.POLICIES},
                          greedy={name: {k: v['placed'] for k, v in order_results[name].items()}
                                  for name in P.POLICIES},
                          mis=summary['maximum_independent_set'],
                          verify=summary['verification']), indent=2))


if __name__ == '__main__':
    main()
