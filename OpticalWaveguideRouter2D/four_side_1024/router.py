"""Bounded four-side candidate search, route scheduling and transactional rerouting."""
import math
import time
from collections import Counter

import numpy as np

from .geometry import fillet_polyline, dubins, length, validate
from .conflicts import ConflictIndex


def candidates(route, endpoints, cfg):
    src = endpoints[route['source_endpoint']]; dst = endpoints[route['target_endpoint']]
    p = np.asarray(src['routing_xy']); q = np.asarray(dst['routing_xy'])
    a = np.asarray(src['inward']); b = np.asarray(dst['inward'])
    radius = cfg['min_radius_mm']
    pools = [[], [], []]
    # General pose-to-pose circular/straight candidates: no two-side legacy pass.
    pools[0].extend(dubins((*p, math.atan2(a[1], a[0])),
                          (*q, math.atan2(-b[1], -b[0])), radius))
    polylines = []
    if route['relation'] == 'adjacent':
        ab = np.column_stack((a, -b))
        u, v = np.linalg.solve(ab, q-p)
        if min(u, v) > 0:
            polylines.append([p, p+a*u, q])
    else:
        # Independent horizontal/vertical lane candidates on all four sides.
        for lane in [75., 37.5, 112.5, 18., 132., 56., 94., 10., 140.]:
            if src['side'] in 'NS':
                polylines.append([p, (p[0], lane), (q[0], lane), q])
            else:
                polylines.append([p, (lane, p[1]), (lane, q[1]), q])
    for lead in [6., 12., 22., 35., 50., 65.]:
        polylines.append([p, p+a*lead, q+b*lead, q])
        for delta in (-18., 18.):
            polylines.append([p, p+a*lead, (p+q)/2 + np.array([delta, -delta]), q+b*lead, q])
    for pts in polylines:
        try:
            pools[1].append(fillet_polyline(pts, radius))
        except ValueError:
            pass
    # Two Dubins legs through an interior pose supply non-Manhattan detours.
    heading = math.atan2(q[1]-p[1], q[0]-p[0])
    for offset in [-24., 24., -45., 45.]:
        mid = (p+q)/2 + offset*np.array([-math.sin(heading), math.cos(heading)])
        if np.min(mid) < 6 or np.max(mid) > 144:
            continue
        left = dubins((*p, math.atan2(a[1], a[0])), (*mid, heading), radius)
        right = dubins((*mid, heading), (*q, math.atan2(-b[1], -b[0])), radius)
        if left and right:
            pools[2].append(min(left, key=length)+min(right, key=length))
    seen = set(); result = []; rejected = Counter()
    for pool in pools:
        pool.sort(key=length)
    # Round-robin keeps short alternatives from eliminating geometric diversity.
    for i in range(max(map(len, pools), default=0)):
        for pool in pools:
            if i >= len(pool):
                continue
            primitives = pool[i]
            key = repr([[s['kind'], np.round(s['p0'], 6).tolist(), np.round(s['p1'], 6).tolist(), round(s.get('sweep', 0), 6)] for s in primitives])
            if key in seen:
                continue
            seen.add(key)
            errors = validate(primitives, p, q, a, -b, board=150., width=cfg['width_mm'], min_radius=radius)
            if errors:
                rejected.update(errors); continue
            result.append(dict(primitives=primitives, length_mm=length(primitives)))
            if len(result) >= cfg['candidates_per_route']:
                return result, dict(rejected)
    return result, dict(rejected)


def route_all(routes, endpoints, cfg, log):
    start = time.perf_counter(); deadline = start+cfg['search_seconds']
    evaluations = 0; pool = {}; generation_failures = {}
    preparer = ConflictIndex(width=cfg['width_mm'], gap=cfg['edge_gap_mm'], sagitta=cfg['sagitta_mm'])
    for i, r in enumerate(routes):
        cs, errors = candidates(r, endpoints, cfg)
        for c in cs:
            c['prepared'] = preparer.prepare(c['primitives'])
        pool[r['route_id']] = cs; generation_failures[r['route_id']] = errors
        if (i+1) % 256 == 0:
            log(f'generated candidates {i+1}/1024, elapsed={time.perf_counter()-start:.2f}s')
    by_id = {r['route_id']: r for r in routes}
    # A chord-density predictor ranks endpoints traversing highly occupied tiles.
    tiles = Counter(); chord_tiles = {}
    for r in routes:
        p = np.array(endpoints[r['source_endpoint']]['routing_xy'])
        q = np.array(endpoints[r['target_endpoint']]['routing_xy'])
        cells = set(map(tuple, np.floor(np.linspace(p, q, 40)/10).astype(int)))
        chord_tiles[r['route_id']] = cells; tiles.update(cells)
    congestion = {k: sum(tiles[c] for c in cs) for k, cs in chord_tiles.items()}
    chord_length = lambda r: np.linalg.norm(np.array(endpoints[r['source_endpoint']]['routing_xy'])-endpoints[r['target_endpoint']]['routing_xy'])
    orders = {'csv': routes,
              'longest': sorted(routes, key=lambda r: -chord_length(r)),
              'congested': sorted(routes, key=lambda r: -congestion[r['route_id']]),
              'opposite_first': sorted(routes, key=lambda r: (r['relation']!='opposite', -chord_length(r)))}
    best = {}; best_fail = {}; experiments = []; best_score = (-1, -float('inf'))
    budget = cfg['candidate_evaluation_budget']
    for strategy in cfg['strategies']:
        if time.perf_counter() >= deadline or evaluations >= budget:
            experiments.append(dict(strategy=strategy, status='not_started_global_budget')); continue
        index = ConflictIndex(width=cfg['width_mm'], gap=cfg['edge_gap_mm'], sagitta=cfg['sagitta_mm'])
        accepted = {}; failed = {}; strategy_start = time.perf_counter()
        # Reserve a fair time share for comparison; all 1024 identities receive a result.
        remaining = len(cfg['strategies'])-cfg['strategies'].index(strategy)
        local_deadline = min(deadline, strategy_start+(deadline-strategy_start)/remaining)

        def attempt(rid, until):
            nonlocal evaluations
            reasons = Counter(); blockers = Counter(); chosen = None; cost = float('inf'); n = 0
            for ci, c in enumerate(pool[rid]):
                if time.perf_counter() >= until or evaluations >= budget:
                    reasons['search_budget_exhausted'] += 1; break
                evaluations += 1; n += 1
                result = index.evaluate(c['prepared'])
                if result['valid']:
                    new_cost = c['length_mm'] + .2*len(result['crossings'])
                    if new_cost < cost:
                        chosen = (ci, c); cost = new_cost
                    # First legal alternative is retained, then bounded local refinement.
                    if n >= 4:
                        break
                else:
                    for key in ('spacing_pairs', 'overlap_pairs', 'touch_pairs', 'crossing_zone_overlap_pairs'):
                        ids = result.get(key, [])
                        if ids:
                            reasons[key] += 1; blockers.update(ids)
                    for key in ('self_intersections', 'self_overlaps', 'self_spacing_violations', 'discontinuities'):
                        if result.get(key): reasons[key] += 1
                    if not any(result.get(k) for k in ('spacing_pairs', 'overlap_pairs', 'touch_pairs', 'crossing_zone_overlap_pairs', 'self_intersections', 'self_overlaps', 'self_spacing_violations', 'discontinuities')):
                        reasons['other_geometric_conflict'] += 1
            if chosen:
                ci, c = chosen
                index.add(rid, c['prepared'])
                return dict(route_id=rid, layer=0, candidate_index=ci, length_mm=c['length_mm'], primitives=c['primitives']), None
            reason = 'no_in_bounds_tangent_candidate' if not pool[rid] else 'no_legal_candidate_within_budget'
            return None, dict(route_id=rid, reason=reason, evaluated=n, rejection_counts=dict(reasons),
                              generation_rejections=generation_failures[rid], blockers=dict(blockers))

        for i, r in enumerate(orders[strategy]):
            rid = r['route_id']; record, failure = attempt(rid, local_deadline)
            if record: accepted[rid] = record
            else: failed[rid] = failure
            if (i+1) % 256 == 0:
                log(f'{strategy}: attempted={i+1}/1024 accepted={len(accepted)} evaluations={evaluations} elapsed={time.perf_counter()-start:.1f}s')
        # Transactional rip-up: preserve original solution unless net route count improves.
        ripped = 0; improved = 0
        for rid, failure in list(failed.items())[:cfg['ripup_routes']]:
            if time.perf_counter() >= local_deadline:
                break
            blockers = [int(k) for k, _ in sorted(failure['blockers'].items(), key=lambda x: -x[1])[:2] if int(k) in accepted]
            if not blockers:
                continue
            old = {k: accepted[k] for k in blockers}
            for k in blockers: index.remove(k)
            replacement, _ = attempt(rid, local_deadline)
            rerouted = {}
            if replacement:
                for k in blockers:
                    rec, _ = attempt(k, local_deadline)
                    if rec: rerouted[k] = rec
            ripped += 1
            if replacement and len(rerouted) == len(blockers):
                accepted.update(rerouted); accepted[rid] = replacement; del failed[rid]; improved += 1
            else:
                if replacement: index.remove(rid)
                for k in rerouted: index.remove(k)
                for k, rec in old.items(): index.add(k, rec['primitives'])
        duration = time.perf_counter()-strategy_start
        score = (len(accepted), -sum(x['length_mm'] for x in accepted.values()))
        experiments.append(dict(strategy=strategy, success=len(accepted), failed=len(failed),
            duration_seconds=duration, ripup_transactions=ripped, ripup_improvements=improved,
            candidate_evaluations_cumulative=evaluations,
            budget_exhausted=time.perf_counter() >= local_deadline))
        log(f'{strategy} complete: {len(accepted)}/1024, {duration:.2f}s, ripup +{improved}')
        if score > best_score:
            best_score = score; best = accepted.copy(); best_fail = failed.copy(); best_strategy = strategy
    assert len(best)+len(best_fail) == 1024
    return best, best_fail, dict(strategies=experiments, best_strategy=best_strategy,
        candidate_evaluations=evaluations, generated_candidates=sum(map(len, pool.values())),
        search_runtime_seconds=time.perf_counter()-start)
