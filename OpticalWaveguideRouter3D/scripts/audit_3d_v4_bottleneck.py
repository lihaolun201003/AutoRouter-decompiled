"""Step 17 audit: why the 42,909 residual near-distance pairs survive the v3
group-D terminal state, and what limits them.

The audit starts from the SAME saved terminal state as the six v4 budget
experiments (outputs/3d_strategy_v3/512_ablation/D_both_enabled/) and answers
four questions per target side, kept separate instead of merged:

  1. was this side covered by the previous (historical 720-evaluation) budget
     at all?
  2. under the CURRENT candidate-generation rules, is there any legal window?
  3. if windows exist, do the candidates exist and fail basic acceptance?
  4. if basic acceptance passes, does the FULL neighbour acceptance produce no
     strict global decrease?

Hard rules obeyed here:
- the fixed target list, the sampling rules and the random seed are frozen and
  saved BEFORE any candidate is evaluated;
- candidate evaluations performed by this audit are booked in a SEPARATE
  ledger and are never part of any v4 optimisation budget;
- the audit's outcomes are never used to select targets for the performance
  experiments (those use dynamic target selection only);
- "no candidate under the current generation rules" is never reported as
  "geometrically infeasible": the wording is fixed in the output records.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\audit_3d_v4_bottleneck.py PROJECT OUTDIR
        [--seed 20261006] [--basic-cap 400] [--full-cap 25]
"""
import sys, json, csv, random, hashlib
from collections import Counter, defaultdict
from copy import deepcopy
from math import fsum
from pathlib import Path
from itertools import combinations
from time import perf_counter


def parse_args(argv):
    args = {'seed': 20261006, 'basic_cap': 400, 'full_cap': 25}
    positional = []; index = 1
    while index < len(argv):
        token = argv[index]
        if token == '--seed': args['seed'] = int(argv[index+1]); index += 2
        elif token == '--basic-cap': args['basic_cap'] = int(argv[index+1]); index += 2
        elif token == '--full-cap': args['full_cap'] = int(argv[index+1]); index += 2
        else: positional.append(token); index += 1
    if len(positional) != 2: raise SystemExit(__doc__)
    args['project'] = Path(positional[0]).resolve(); args['out'] = Path(positional[1]).resolve()
    return args


ARGS = parse_args(sys.argv)
ROOT = ARGS['project']; OUT = ARGS['out']
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

from src.models import Layer, Point3D
from src.geometry_3d import (lift_smoothed_route_to_layer, CosineTransition3D, LineSegment3D,
    PlanarArcSegment3D)
from src.geometry_3d_diagnostics import minimum_xy_run_for_radius
from src.multi_attribution import deserialize_plot
from src.sequential_elevation_3d import RouteView, pair_status
from src.three_layer_assignment_3d import LayerConfiguration
from src.layer_assignment_3d import elevation_candidates, evaluate_elevation, _locations
from src.fixed_1024_routing import deserialize_route3d
from src.strategy_v2_3d import (route_degrees, route_layer, target_priority, full_acceptance,
    strategy_rank, target_points_for, xy_projection_preserved)
from src.strategy_v4_3d import pair_state_distribution, elevation_structure

SIZE = 512
CLEARANCE = 0.1
REQUIRED_RADIUS = 5.
SLACK_MM = 1e-5
START_STATE = ROOT/'outputs/3d_strategy_v3/512_ablation/D_both_enabled'
SEED = ARGS['seed']
ROUTE_CAP_WITHIN_CATEGORY = 2
ROUTE_CAP_ACROSS_LIST = 4
CATEGORY_SIZES = dict(high_conflict_both_unelevated=20, random_both_unelevated=20,
    single_elevated=10, both_elevated=10)


def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def log(message): print(message, flush=True)


def three_layer_config():
    return LayerConfiguration([Layer(0, 0.), Layer(1, 1.), Layer(2, 2.)], CLEARANCE, REQUIRED_RADIUS,
        'LINE_ONLY_FINITE_WINDOWS', 'EXPERIMENTAL_SYNTHETIC')


def load_planar_and_crossings():
    plotpath = ROOT/'outputs/step_8_5_legacy_512_plot_geometry.json'
    eventpath = ROOT/'outputs/step_8_5_legacy_512_physical_events.jsonl'
    planar = {r['id']: lift_smoothed_route_to_layer(deserialize_plot(r), Layer(0, 0))
        for r in json.loads(plotpath.read_text())['routes']}
    crossings = {}
    for text in eventpath.read_text().splitlines():
        e = json.loads(text)
        if e['kind'] == 'cross':
            crossings.setdefault(tuple(sorted((e['route_a_id'], e['route_b_id']))), []).append(
                Point3D(e['point']['x'], e['point']['y'], 0))
    return planar, crossings


def load_start_state():
    routes = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in json.loads((START_STATE/'final_routes.json').read_text(encoding='utf-8'))['routes']}
    sets = json.loads((START_STATE/'collision_sets.json').read_text(encoding='utf-8'))
    decisions = json.loads((START_STATE/'decisions.json').read_text(encoding='utf-8'))
    return routes, sets, decisions


def full_scan(routes):
    started = perf_counter(); checks = 0
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    pairs = set(); unknown = set()
    for a, b in combinations(sorted(routes), 2):
        status = pair_status(views[a], views[b], CLEARANCE); checks += 1
        if status == 'COLLISION': pairs.add((a, b))
        elif status != 'CLEAR': unknown.add((a, b))
        if checks % 20000 == 0: log(f'  scan {checks} pairs {perf_counter()-started:.1f}s')
    return dict(checks=checks, pairs=pairs, unknown=unknown, seconds=perf_counter()-started)


def covered_by_previous_budget(decisions):
    """(target_pair, moved_route) pairs that actually entered the historical
    evaluation sequence, plus every target that was attempted at all."""
    attempted = set(); victim_attempted = set()
    for step in decisions:
        target = tuple(step['target_pair'])
        attempted.add(target)
        for va in step['victim_attempts']:
            victim_attempted.add((target, va['route_id']))
    return attempted, victim_attempted


def select_targets(pairs, degrees, elevated, seed):
    """Frozen target list. Deterministic given the seed; caps keep the list from
    piling up on a few routes. Categories are filled in this order and the
    cross-list cap is applied cumulatively."""
    unelevated = sorted(p for p in pairs if p[0] not in elevated and p[1] not in elevated)
    high = sorted(unelevated, key=lambda p: target_priority(p, degrees))
    rng = random.Random(seed)
    shuffled = list(unelevated)
    rng.shuffle(shuffled)
    random_order = sorted(shuffled)   # keep the sampled ORDER, then tie-break by pair for determinism
    categories = [
        ('high_conflict_both_unelevated', high,
         'sorted by the v4/v3 target priority (-(degree sum), -max degree, pair); '
         'the 20 highest-ranked pairs, at most 3 per route inside the category'),
        ('random_both_unelevated', random_order,
         f'random.Random({seed}).shuffle over the sorted both-unelevated pair list, then the '
         'first pairs in that sampled order; at most 3 per route inside the category'),
        ('single_elevated', sorted((p for p in pairs
            if (p[0] in elevated) != (p[1] in elevated)), key=lambda p: target_priority(p, degrees)),
         'one route already elevated; same priority order, at most 3 per route inside the category'),
        ('both_elevated', sorted((p for p in pairs
            if p[0] in elevated and p[1] in elevated), key=lambda p: target_priority(p, degrees)),
         'both routes already elevated; same priority order, at most 3 per route inside the category'),
    ]
    rows = []; route_use = Counter(); category_fill = {}
    for name, ordered, rule in categories:
        want = CATEGORY_SIZES[name]; taken = 0; per_route = Counter(); shortfall = None
        for pair in ordered:
            if taken >= want: break
            if per_route[pair[0]] >= ROUTE_CAP_WITHIN_CATEGORY: continue
            if per_route[pair[1]] >= ROUTE_CAP_WITHIN_CATEGORY: continue
            if route_use[pair[0]] >= ROUTE_CAP_ACROSS_LIST: continue
            if route_use[pair[1]] >= ROUTE_CAP_ACROSS_LIST: continue
            rows.append(dict(category=name, pair=list(pair), priority_rank=taken + 1, rule=rule))
            per_route[pair[0]] += 1; per_route[pair[1]] += 1
            route_use[pair[0]] += 1; route_use[pair[1]] += 1
            taken += 1
        if taken < want:
            shortfall = dict(requested=want, selected=taken,
                reason='CAPS_OR_NOT_ENOUGH_PAIRS_IN_THIS_CATEGORY')
        category_fill[name] = dict(requested=want, selected=taken, shortfall=shortfall,
            available_pairs=len(ordered))
    return rows, category_fill


def window_structure(plan_route, pair, points, config):
    """Per-side structural description of generation, using the generator's own
    bounds. Reports the usable rise/fall straight lengths on the frozen planar
    route and the legal window count per elevated layer."""
    record = dict(locations=None, locations_error=None, rise_segments=[], fall_segments=[],
        usable_rise_length_mm=0., usable_fall_length_mm=0.,
        per_layer={}, generated_total=0, zero_candidate_reasons={},
        not_a_geometric_impossibility=('no legal window under the CURRENT generation rules; '
            'this is not a statement that the geometry has no solution'))
    try:
        first, last = _locations(plan_route, points)
        record['locations'] = dict(rise_anchor_primitive=first[0], rise_anchor_parameter=first[1],
            fall_anchor_primitive=last[0], fall_anchor_parameter=last[1])
    except ValueError as ex:
        record['locations_error'] = str(ex)
        first = last = None
    if first is not None:
        for i, p in enumerate(plan_route.primitives):
            if not isinstance(p, LineSegment3D): continue
            length = p.length()
            pad = (max(1e-7, config.clearance_mm) + SLACK_MM)/length
            rise_hi = (first[1] - pad) if i == first[0] else (1 - pad) if i < first[0] else -1.
            rise_lo = pad
            fall_lo = (last[1] + pad) if i == last[0] else pad if i > last[0] else 2.
            fall_hi = 1 - pad
            if rise_hi > rise_lo:
                record['rise_segments'].append(dict(primitive_index=i, length_mm=length,
                    usable_length_mm=(rise_hi - rise_lo)*length))
                record['usable_rise_length_mm'] += (rise_hi - rise_lo)*length
            if fall_hi > fall_lo:
                record['fall_segments'].append(dict(primitive_index=i, length_mm=length,
                    usable_length_mm=(fall_hi - fall_lo)*length))
                record['usable_fall_length_mm'] += (fall_hi - fall_lo)*length
    for layer in config.layers[1:]:
        try:
            family, failure = elevation_candidates(plan_route, pair, points, config,
                target_layer_id=layer.id, window_slack_mm=SLACK_MM)
        except ValueError as ex:
            family, failure = [], str(ex)
        record['per_layer'][str(layer.id)] = dict(generated_count=len(family), failure=failure)
        record['generated_total'] += len(family)
        if not family:
            record['zero_candidate_reasons'][str(layer.id)] = failure
    record['zero_candidate_reason'] = (None if record['generated_total']
        else next(iter(record['zero_candidate_reasons'].values()), 'UNKNOWN'))
    return record


def audit_side(target, moved, routes, plan, config, crossings, degrees, views, pairs, elevated,
               previous_victims):
    """One (target, side) record. Basic evaluations are charged to the audit
    ledger only; full acceptance is capped and the cap is recorded."""
    from src.clearance_3d import analyze_route3d_clearance
    from src.three_layer_assignment_3d import candidate_families
    other = target[1] if moved == target[0] else target[0]
    current = analyze_route3d_clearance(routes[moved], routes[other], config.clearance_mm)
    if current['status'] != 'COLLISION':
        raise AssertionError('audit target side is not colliding in the current layout')
    points = target_points_for(current, crossings.get(target))
    record = dict(target_pair=list(target), moved_route_id=moved, other_route_id=other,
        current_layer=route_layer(routes[moved]), already_elevated=moved in elevated,
        current_conflict_degree=degrees.get(moved, 0),
        previous_budget_covered=(target, moved) in previous_victims,
        current_pair_analysis=dict(status=current['status'],
            minimum_distance_mm=current.get('minimum_distance_mm')))
    record['structure'] = window_structure(plan[moved], target, points, config)
    generated = record['structure']['generated_total']
    record['generated_count'] = generated
    old_neighbors = {b if a == moved else a for a, b in pairs if moved in (a, b)}
    current_length = routes[moved].total_length()
    basic_rows = []; full_rows = []; audit_basic = 0; audit_full = 0
    basic_skipped = 0; full_skipped = 0
    if generated:
        try:
            candidates, failure = candidate_families(plan[moved], target, points, config,
                window_slack_mm=SLACK_MM)
        except ValueError as ex:
            candidates, failure = [], str(ex)
        for index, candidate in enumerate(candidates):
            if audit_basic >= ARGS['basic_cap']:
                basic_skipped = len(candidates) - index; break
            basic = evaluate_elevation(candidate, routes[moved], routes[other], config)
            audit_basic += 1
            row = dict(candidate_index=index, target_layer_id=candidate.layer_to,
                basic_status=basic['status'], basic_reasons=basic['reasons'],
                extra_length_mm=candidate.extra_length_mm)
            basic_rows.append(row)
            if basic['status'] != 'ACCEPTED_TARGET_PAIR_ONLY': continue
            if audit_full >= ARGS['full_cap']:
                full_skipped += 1; continue
            full, after_status = full_acceptance(candidate, moved, plan[moved], current_length,
                views, old_neighbors, config)
            audit_full += 1
            row.update(full)
            full_rows.append(dict(candidate_index=index, status=full['status'],
                reasons=full['full_reasons'], net_collision_reduction=full['net_collision_reduction'],
                after_collision_count=full['after_collision_count'], movement='RELOCATION'
                if moved in elevated else 'FIRST_ELEVATION',
                step_length_delta_mm=full['step_length_delta_mm']))
    basic_accepted = sum(1 for r in basic_rows if r['basic_status'] == 'ACCEPTED_TARGET_PAIR_ONLY')
    full_accepted = [r for r in full_rows if r['status'] == 'ACCEPTED_FULL']
    full_capped = bool(full_skipped)
    if generated == 0:
        outcome = 'NO_LEGAL_WINDOW_UNDER_CURRENT_RULES'
    elif basic_accepted == 0:
        outcome = 'CANDIDATES_EXIST_BASIC_ALL_REJECTED'
    elif full_accepted:
        outcome = 'FULL_ACCEPTED_CANDIDATE_EXISTS'
    elif full_capped:
        outcome = 'BASIC_PASSES_FULL_CHECK_CAPPED'
    else:
        outcome = 'BASIC_PASSES_FULL_NO_NET_GAIN'
    record.update(basic_evaluations=audit_basic, full_checks=audit_full,
        basic_evaluations_skipped_by_cap=basic_skipped, full_checks_skipped_by_cap=full_skipped,
        full_check_capped=full_capped,
        basic_accepted_candidates=basic_accepted, full_accepted_candidates=len(full_accepted),
        basic_rejection_reasons=dict(Counter(r for row in basic_rows for r in row['basic_reasons'])),
        full_rejection_reasons=dict(Counter(r for row in full_rows for r in (row['reasons'] or []))),
        best_full_net_reduction=max((r['net_collision_reduction'] for r in full_rows), default=None),
        outcome=outcome)
    return record, basic_rows, full_rows


def main():
    started = perf_counter()
    config = three_layer_config()
    planar, crossings = load_planar_and_crossings()
    routes, sets, decisions = load_start_state()
    log('audit: full rescan of the common start state ...')
    scan = full_scan(routes)
    pairs = scan['pairs']; unknown = scan['unknown']
    elevated = {i for i, r in routes.items()
        if any(isinstance(p, CosineTransition3D) for p in r.primitives)}
    degrees = route_degrees(pairs)
    state_distribution = pair_state_distribution(pairs, elevated)
    saved_pairs = set(map(tuple, sets['final_collision_pairs']))
    saved_unknown = set(map(tuple, sets['final_unresolved_pairs']))
    recount = dict(checks=scan['checks'], seconds=scan['seconds'],
        recomputed_collision_pairs=len(pairs), saved_collision_pairs=len(saved_pairs),
        collision_set_matches_saved=pairs == saved_pairs,
        recomputed_unresolved_pairs=len(unknown), saved_unresolved_pairs=len(saved_unknown),
        unresolved_set_matches_saved=unknown == saved_unknown,
        elevated_route_count=len(elevated),
        route_state_counts=dict(both_routes_unelevated=state_distribution['both_routes_unelevated'],
            single_route_elevated=state_distribution['single_route_elevated'],
            both_routes_elevated=state_distribution['both_routes_elevated']),
        layer_route_counts={str(k): v for k, v in sorted(Counter(route_layer(r)
            for r in routes.values()).items())},
        geometry_structures_all_single={i: elevation_structure(r)[0] for i, r in routes.items()})
    assert recount['collision_set_matches_saved'] and recount['unresolved_set_matches_saved']
    log('audit: route-state recount ' + json.dumps(recount['route_state_counts']))

    rows, category_fill = select_targets(pairs, degrees, elevated, SEED)
    route_use = Counter(r for row in rows for r in row['pair'])
    target_list = dict(seed=SEED, categories=category_fill, selected_count=len(rows),
        max_routes_in_list=len(route_use), route_use=dict(sorted(route_use.items())),
        max_per_route_in_list=max(route_use.values()), targets=rows)
    (OUT/'target_list.json').write_text(json.dumps(target_list, indent=2), encoding='utf-8')
    (OUT/'sampling_rules.json').write_text(json.dumps(dict(
        seed=SEED, category_sizes=CATEGORY_SIZES,
        route_cap_within_category=ROUTE_CAP_WITHIN_CATEGORY,
        route_cap_across_list=ROUTE_CAP_ACROSS_LIST,
        category_order=['high_conflict_both_unelevated', 'random_both_unelevated',
            'single_elevated', 'both_elevated'],
        frozen_before_any_candidate_evaluation=True,
        audit_outcomes_not_used_for_experiment_targets=True,
        notes=['the fixed list is used by the audit only; the six v4 experiments use dynamic '
               'target selection over all current pairs',
               'category fill order is high-conflict -> random -> single-elevated -> both-elevated, '
               'and the cross-list route cap is applied cumulatively',
               'if a category cannot reach its requested size the shortfall is recorded, not padded']),
        indent=2), encoding='utf-8')
    log(f'audit: fixed target list {len(rows)} targets over {len(route_use)} routes '
        f'(max per route {max(route_use.values())})')

    attempted_targets, previous_victims = covered_by_previous_budget(decisions)
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    side_records = []; basic_rows_all = []; full_rows_all = []
    for row in rows:
        target = tuple(row['pair'])
        sides = []
        for moved in target:
            record, basic_rows, full_rows = audit_side(target, moved, routes, planar, config,
                crossings, degrees, views, pairs, elevated, previous_victims)
            record['category'] = row['category']
            record['target_previously_attempted'] = target in attempted_targets
            side_records.append(record)
            sides.append(record)
            for r in basic_rows:
                basic_rows_all.append(dict(target_pair=list(target), moved_route_id=moved, **r))
            for r in full_rows:
                full_rows_all.append(dict(target_pair=list(target), moved_route_id=moved, **r))
            log(f"  {row['category']} {target} moved={moved} gen={record['generated_count']} "
                f"basic={record['basic_evaluations']} full={record['full_checks']} "
                f"outcome={record['outcome']}")

    primary = {}
    for name in ('NO_LEGAL_WINDOW_UNDER_CURRENT_RULES', 'CANDIDATES_EXIST_BASIC_ALL_REJECTED',
                 'BASIC_PASSES_FULL_NO_NET_GAIN', 'BASIC_PASSES_FULL_CHECK_CAPPED',
                 'FULL_ACCEPTED_CANDIDATE_EXISTS'):
        primary[name] = sum(1 for r in side_records if r['outcome'] == name)
    cross_tab = defaultdict(Counter)
    for r in side_records:
        cross_tab['PREVIOUS_BUDGET_COVERED' if r['previous_budget_covered']
            else 'PREVIOUS_BUDGET_NOT_COVERED'][r['outcome']] += 1
    by_category = {}
    for name in CATEGORY_SIZES:
        subset = [r for r in side_records if r['category'] == name]
        by_category[name] = dict(sides=len(subset),
            generated_candidates=sum(r['generated_count'] for r in subset),
            no_legal_window_sides=sum(1 for r in subset
                if r['outcome'] == 'NO_LEGAL_WINDOW_UNDER_CURRENT_RULES'),
            previous_budget_covered_sides=sum(1 for r in subset if r['previous_budget_covered']),
            full_accepted_sides=sum(1 for r in subset if r['outcome'] == 'FULL_ACCEPTED_CANDIDATE_EXISTS'),
            outcomes=dict(Counter(r['outcome'] for r in subset)))
    generation_reason_counts = Counter(r['structure']['zero_candidate_reason'] for r in side_records
        if r['structure']['zero_candidate_reason'])
    basic_reason_counts = sum((Counter(r['basic_rejection_reasons']) for r in side_records), Counter())
    full_reason_counts = sum((Counter(r['full_rejection_reasons']) for r in side_records), Counter())
    summary = dict(
        seed=SEED, target_count=len(rows), side_count=len(side_records),
        route_diversity=dict(routes_used=len(route_use), max_per_route=max(route_use.values())),
        category_fill=category_fill, outcome_counts=primary,
        previous_budget_cross_tab={k: dict(v) for k, v in cross_tab.items()},
        by_category=by_category,
        generation_failure_reason_counts=dict(generation_reason_counts),
        basic_rejection_reason_counts=dict(basic_reason_counts),
        full_rejection_reason_counts=dict(full_reason_counts),
        zero_generation_means_no_legal_window_under_current_rules_only=True,
        wording=('"no candidate" below always means "no legal window under the current '
                 'generation rules"; it is never "geometrically infeasible".'),
        audit_ledger=dict(basic_evaluations=sum(r['basic_evaluations'] for r in side_records),
            full_neighbor_checks=sum(r['full_checks'] for r in side_records),
            basic_evaluations_skipped_by_cap=sum(r['basic_evaluations_skipped_by_cap']
                for r in side_records),
            full_checks_skipped_by_cap=sum(r['full_checks_skipped_by_cap'] for r in side_records),
            basic_cap_per_side=ARGS['basic_cap'], full_cap_per_side=ARGS['full_cap'],
            excluded_from_optimisation_budgets=True,
            note=('these evaluations are booked separately and are NOT part of any of the six '
                  'appended candidate budgets')),
        seconds=perf_counter() - started)
    (OUT/'side_audit.json').write_text(json.dumps(dict(records=side_records), indent=2),
        encoding='utf-8')
    (OUT/'classification_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (OUT/'audit_ledger.json').write_text(json.dumps(summary['audit_ledger'], indent=2),
        encoding='utf-8')
    (OUT/'recount.json').write_text(json.dumps(recount, indent=2), encoding='utf-8')
    with (OUT/'side_audit.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['target_a', 'target_b', 'category', 'moved_route_id', 'current_layer',
            'already_elevated', 'conflict_degree', 'previous_budget_covered',
            'generated_candidates', 'zero_candidate_reason', 'basic_evaluations',
            'basic_accepted', 'full_checks', 'full_accepted', 'best_full_net_reduction',
            'outcome', 'usable_rise_length_mm', 'usable_fall_length_mm'])
        for r in side_records:
            writer.writerow([r['target_pair'][0], r['target_pair'][1], r['category'],
                r['moved_route_id'], r['current_layer'], r['already_elevated'],
                r['current_conflict_degree'], r['previous_budget_covered'], r['generated_count'],
                r['structure']['zero_candidate_reason'] or '', r['basic_evaluations'],
                r['basic_accepted_candidates'], r['full_checks'], r['full_accepted_candidates'],
                '' if r['best_full_net_reduction'] is None else r['best_full_net_reduction'],
                r['outcome'], round(r['structure']['usable_rise_length_mm'], 6),
                round(r['structure']['usable_fall_length_mm'], 6)])
    (OUT/'input_hashes.json').write_text(json.dumps(dict(
        start_state={f: sha256(START_STATE/f) for f in
            ('final_routes.json', 'collision_sets.json', 'ledger.json', 'decisions.json')},
        script=sha256(Path(__file__).resolve()),
        strategy_v4_3d=sha256(ROOT/'src/strategy_v4_3d.py'),
        audit_script_options=dict(seed=SEED, basic_cap=ARGS['basic_cap'], full_cap=ARGS['full_cap'])),
        indent=2), encoding='utf-8')
    log('audit: ' + json.dumps(dict(outcomes=primary, ledger=summary['audit_ledger'],
        seconds=round(summary['seconds'], 1))))
    log('audit DONE')


if __name__ == '__main__':
    main()
