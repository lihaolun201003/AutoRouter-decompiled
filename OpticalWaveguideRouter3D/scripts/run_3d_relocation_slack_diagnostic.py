"""Step 16 diagnostic: fixed-relocation D/E rerun with the candidate-window slack.

Repeats the Step 15 fixed-target diagnostic (outputs/3d_strategy_v2_rev2/
512_de_diagnostic) on exactly the same start state, target list and target
order, adding only window_slack_mm=1e-5 to candidate generation. The static
generation-failure cache stays off, so this round changes one feature only.

    new D = first elevations only, window_slack_mm=1e-5
    new E = relocation allowed,  window_slack_mm=1e-5

Both modes keep the historical rules: replacement candidates are rebuilt from
the frozen planar z=0 route, endpoints and the XY projection are preserved, the
current route is replaced (never stacked), C0/C1 joins and the transition radius
are checked, every current neighbour is re-evaluated, UNRESOLVED is never
treated as CLEAR, and each accepted edit must strictly reduce the global close
pair count. Candidate-evaluation ceiling 720 per mode, basic rejections counted.

Outputs (never overwriting the old diagnostic):
    config.json, code_version.json, environment.json, target_list.json,
    old_diagnostic_reference.json, decisions_{D,E}.json, curve_{D,E}.json,
    final_routes_{D,E}.json, collision_sets_{D,E}.json, ledger_{D,E}.json,
    recheck_{D,E}.json, movement_stats.json, length_ledger.json,
    candidate_correspondence.json, comparison_DE.csv, summary.json, manifest.json

Usage (project root):
    .venv\Scripts\python.exe -B scripts\run_3d_relocation_slack_diagnostic.py PROJECT OUTDIR [--slack 1e-5]
"""
import sys, json, csv, hashlib, platform, traceback
from collections import Counter
from copy import deepcopy
from math import fsum
from pathlib import Path
from itertools import combinations
from time import perf_counter


def parse_args(argv):
    args = {'slack': 1e-5}
    positional = []
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == '--slack': args['slack'] = float(argv[index+1]); index += 2
        else: positional.append(token); index += 1
    if len(positional) != 2: raise SystemExit(__doc__)
    args['project'] = Path(positional[0]).resolve(); args['out'] = Path(positional[1]).resolve()
    return args


ARGS = parse_args(sys.argv)
ROOT = ARGS['project']; OUT = ARGS['out']; SLACK = ARGS['slack']
TASK = 'relocation_slack_diagnostic'
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
LOG = (OUT/f'{TASK}_512.log').open('a', encoding='utf-8')
def log(message):
    text = f'[{perf_counter():.1f}] {message}'
    print(text, flush=True); LOG.write(text+'\n'); LOG.flush()

from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
from src.geometry_3d_diagnostics import analyze_route3d_joins
from src.multi_attribution import deserialize_plot
from src.sequential_elevation_3d import RouteView, pair_status
from src.three_layer_assignment_3d import LayerConfiguration
from src.fixed_1024_routing import serialize_route3d, deserialize_route3d
from src.strategy_v2_3d import (BudgetConfig, run_fixed_target_diagnostic,
    xy_projection_preserved, route_layer, SKIPPED_ELEVATED_STATUSES)

CLEARANCE = 0.1
REQUIRED_RADIUS = 5.
SIZE = 512
SOURCE_V2 = ROOT/'outputs'/'3d_strategy_v2'
START_PATH = SOURCE_V2/'512_three_layer_abc'/'final_routes_B.json'
OLD_DIAG = ROOT/'outputs'/'3d_strategy_v2_rev2'/'512_de_diagnostic'
BUDGET_CEILING = 720


def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def three_layer_config():
    return LayerConfiguration([Layer(0, 0.), Layer(1, 1.), Layer(2, 2.)], CLEARANCE, REQUIRED_RADIUS,
        'LINE_ONLY_FINITE_WINDOWS', 'EXPERIMENTAL_SYNTHETIC')


def config_record(config):
    return dict(layers=[dict(id=l.id, z=l.z) for l in config.layers], clearance_mm=config.clearance_mm,
        required_radius_mm=config.required_radius_mm, transition_policy=config.transition_policy,
        parameter_status=config.parameter_status)


def environment_record():
    return dict(python=sys.version.split()[0], implementation=platform.python_implementation(),
        platform=platform.platform(), executable=sys.executable)


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
    fingerprints = {str(plotpath): sha256(plotpath), str(eventpath): sha256(eventpath)}
    return planar, crossings, fingerprints, 'LEGACY_512_SMOOTHED_P0', [str(plotpath), str(eventpath)]


def save(name, data):
    def encode(x):
        if isinstance(x, tuple): return list(x)
        if type(x).__name__ == 'Layer': return dict(id=x.id, z=x.z)
        raise TypeError(type(x).__name__)
    (OUT/name).write_text(json.dumps(data, default=encode, indent=2, allow_nan=False), encoding='utf-8')


def code_version():
    files = sorted((ROOT/'src').glob('*.py')) + [Path(__file__).resolve()]
    return dict(recorded_hashes={str(p.relative_to(ROOT)): sha256(p) for p in files if p.is_file()},
        note='slack diagnostic driver; hashes cover src/ and this script')


def full_recheck(routes):
    started = perf_counter(); checks = 0
    for r in routes.values(): r.validate()
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    pairs = set(); unknown = set()
    for a, b in combinations(sorted(routes), 2):
        status = pair_status(views[a], views[b], CLEARANCE); checks += 1
        if status == 'COLLISION': pairs.add((a, b))
        elif status != 'CLEAR': unknown.add((a, b))
        if checks % 100000 == 0: log(f'  recheck {checks} pairs {perf_counter()-started:.1f}s')
    assert checks == SIZE*(SIZE-1)//2
    return dict(checks=checks, pairs=pairs, unknown=unknown, seconds=perf_counter()-started)


def geometry_audit(planar, routes):
    endpoints_ok = joins_ok = radius_ok = xy_ok = True; xy_failures = []
    for i, r in routes.items():
        if r.start_point != planar[i].start_point or r.end_point != planar[i].end_point: endpoints_ok = False
        joins = analyze_route3d_joins(r)
        if not (joins.all_C0 and joins.all_C1_direction): joins_ok = False
        for p in r.primitives:
            if isinstance(p, CosineTransition3D) and p.minimum_curvature_radius() < REQUIRED_RADIUS:
                radius_ok = False
        ok, reason = xy_projection_preserved(r, planar[i])
        if not ok: xy_ok = False; xy_failures.append((i, reason))
    return dict(endpoint_invariant=endpoints_ok, joins_C0_C1_direction=joins_ok,
        transition_radius_pass=radius_ok, xy_projection_preserved=xy_ok, xy_failures=xy_failures[:10])


def saved_state_audit(tag, planar):
    stored = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in json.loads((OUT/f'final_routes_{tag}.json').read_text(encoding='utf-8'))['routes']}
    geometry = geometry_audit(planar, stored)
    recheck = full_recheck(stored)
    sets = json.loads((OUT/f'collision_sets_{tag}.json').read_text(encoding='utf-8'))
    pairs = set(map(tuple, sets['final_collision_pairs']))
    unknown = set(map(tuple, sets['final_unresolved_pairs']))
    record = dict(tag=tag, reloaded_route_count=len(stored),
        collision_pair_set_matches_incremental=recheck['pairs'] == pairs,
        unresolved_pair_set_matches_incremental=recheck['unknown'] == unknown,
        rechecked_close_pair_count=len(recheck['pairs']), rechecked_unresolved_pair_count=len(recheck['unknown']),
        geometry=geometry, checks=recheck['checks'], recheck_seconds=recheck['seconds'],
        final_transition_count=sum(isinstance(p, CosineTransition3D) for r in stored.values()
            for p in r.primitives))
    ok = (record['reloaded_route_count'] == SIZE
        and record['collision_pair_set_matches_incremental']
        and record['unresolved_pair_set_matches_incremental']
        and geometry['endpoint_invariant'] and geometry['joins_C0_C1_direction']
        and geometry['transition_radius_pass'] and geometry['xy_projection_preserved'])
    record['verdict'] = 'PASS' if ok else 'FAIL'
    return record


def select_de_targets(routes, planar, elevated):
    """Identical rule to the Step 15 diagnostic: from the frozen start state's
    collision pairs, at most 10 both-elevated pairs then at most 10
    exactly-one-elevated pairs, all in route-id-tuple order. No outcome ranking."""
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    pairs = []
    for a, b in combinations(sorted(routes), 2):
        if pair_status(views[a], views[b], CLEARANCE) == 'COLLISION': pairs.append((a, b))
    both = sorted(p for p in pairs if p[0] in elevated and p[1] in elevated)[:10]
    one = sorted(p for p in pairs if (p[0] in elevated) ^ (p[1] in elevated))[:10]
    return pairs, both, one


def movement_stats(steps):
    """Per movement class counters. Counting rule: a candidate is one
    evaluate_elevation (basic) call, rejections included. A candidate may carry
    several rejection reasons, so 'reason_occurrences' counts reason strings and
    may exceed the number of rejected candidates; 'candidates_with_reason'
    counts each candidate once per reason. The two are reported separately and
    are never added together."""
    out = {}
    for movement in ('FIRST_ELEVATION', 'RELOCATION'):
        attempts = generated_attempts = 0
        generated = basic = basic_passed = full_checks = full_passed = selected = 0
        basic_reason_occ = Counter(); basic_reason_cand = Counter()
        full_reason_occ = Counter(); full_reason_cand = Counter()
        generation_failures = Counter(); skip_statuses = Counter()
        for step in steps:
            for va in step['victim_attempts']:
                if va.get('movement') != movement: continue
                attempts += 1
                if va.get('status') in SKIPPED_ELEVATED_STATUSES:
                    skip_statuses[va['status']] += 1
                    continue
                generated_attempts += 1
                generated += va.get('generated_count', 0)
                if va.get('generated_count', 0) == 0:
                    generation_failures[str(va.get('generation_failure'))] += 1
                if va.get('status') == 'SELECTED': selected += 1
                for row in va['candidates']:
                    basic += 1
                    if row['basic_status'] == 'ACCEPTED_TARGET_PAIR_ONLY':
                        basic_passed += 1
                    else:
                        for reason in (row.get('basic_reasons') or []):
                            basic_reason_occ[reason] += 1
                        for reason in set(row.get('basic_reasons') or []):
                            basic_reason_cand[reason] += 1
                    if row.get('full_reasons') is not None:
                        full_checks += 1
                        if row['status'] == 'ACCEPTED_FULL': full_passed += 1
                        else:
                            for reason in row['full_reasons']:
                                full_reason_occ[reason] += 1
                            for reason in set(row['full_reasons']):
                                full_reason_cand[reason] += 1
        out[movement] = dict(
            victim_attempts_total=attempts,
            victim_attempts_with_generation=generated_attempts,
            victim_attempts_skipped_no_generation=sum(skip_statuses.values()),
            skip_statuses=dict(skip_statuses),
            generated_candidates=generated, basic_evaluations=basic,
            basic_passed=basic_passed, basic_rejected=basic - basic_passed,
            full_acceptance_checks=full_checks, full_acceptance_passed=full_passed,
            accepted_edits=selected,
            generation_failures=dict(generation_failures),
            basic_rejection_reason_occurrences=dict(basic_reason_occ),
            basic_rejection_candidates_with_reason=dict(basic_reason_cand),
            full_rejection_reason_occurrences=dict(full_reason_occ),
            full_rejection_candidates_with_reason=dict(full_reason_cand))
    return out


def step_status_counts(steps):
    return dict(Counter(s['status'] for s in steps))


def length_ledger(result, start_total, planar_total):
    ledger = result['ledger']
    moves = [s for s in result['steps'] if s['status'] in ('ELEVATED', 'RELOCATED')]
    per_step = [dict(step_index=s['step_index'], target_pair=list(s['target_pair']),
        route_id=s['moved_route_id'], movement=s['movement'],
        step_length_delta_mm=s['step_length_delta_mm'],
        route_length_before_mm=s['route_length_before_mm'],
        route_length_after_mm=s['route_length_after_mm'],
        extra_length_vs_planar_mm=s['extra_length_mm_vs_planar']) for s in moves]
    delta_sum = fsum(s['step_length_delta_mm'] for s in moves)
    final_total = ledger['final_total_length_mm']
    return dict(
        start_total_length_mm=start_total, planar_total_length_mm=planar_total,
        final_total_length_mm=final_total,
        delta_vs_diagnostic_start_mm=final_total - start_total,
        delta_vs_diagnostic_start_check_mm=delta_sum,
        delta_vs_diagnostic_start_consistent=abs((final_total - start_total) - delta_sum) < 1e-6,
        start_extra_length_vs_planar_mm=start_total - planar_total,
        final_extra_length_vs_planar_mm=final_total - planar_total,
        accepted_move_count=len(moves),
        negative_step_count=sum(1 for s in per_step if s['step_length_delta_mm'] < 0),
        negative_step_total_mm=fsum(s['step_length_delta_mm'] for s in per_step
            if s['step_length_delta_mm'] < 0),
        first_elevation_step_delta_mm=fsum(s['step_length_delta_mm'] for s in per_step
            if s['movement'] == 'FIRST_ELEVATION'),
        relocation_step_delta_mm=fsum(s['step_length_delta_mm'] for s in per_step
            if s['movement'] == 'RELOCATION'),
        per_step=per_step,
        note='step delta = new route length - previous route length, may be negative; '
             'delta_vs_diagnostic_start = final - start of this diagnostic; '
             'extra_length_vs_planar = terminal geometry - frozen planar z=0 geometry')


def candidate_window_map(decisions):
    """(target, victim) -> list of candidate rows with generation-independent keys.
    Generation always uses the frozen planar route and the frozen anchors, so the
    same task produces the same candidate set in either diagnostic; only the
    window placements may move by at most 2*delta."""
    tasks = {}
    for step in decisions:
        target = tuple(step['target_pair'])
        for va in step['victim_attempts']:
            key = (target, va['route_id'])
            row = tasks.setdefault(key, dict(target=target, moved=va['route_id'],
                generated_count=va.get('generated_count'), generation_failure=va.get('generation_failure'),
                movement=va.get('movement'), windows=[]))
            for item in va['candidates']:
                row['windows'].append(dict(candidate_index=item['candidate_index'],
                    layer=item['target_layer_id'], rise_window=tuple(item['rise_window']),
                    fall_window=tuple(item['fall_window']), basic_status=item['basic_status'],
                    basic_reasons=item.get('basic_reasons') or [],
                    status=item.get('status'), full_reasons=item.get('full_reasons')))
    return tasks


def candidate_correspondence(planar, old_decisions, new_decisions, slack):
    """Per-candidate correspondence between the two E runs (old slack 0, new
    slack 1e-5). Matching is exact on (target, victim, layer, rise primitive,
    fall primitive) and allows |start shift| <= 2*delta with
    delta = slack/length, i.e. the exact window move the generator performs.

    Every recorded SELF_AMBIGUOUS_CLEARANCE row of the old run is included, so
    this block spans ALL movement classes (relocation and first elevation); the
    relocation-only subset is reported by the analysis step. A row is MATCHED
    only when exactly one admissible candidate exists; several admissible
    candidates are recorded as AMBIGUOUS_MULTIPLE_MATCHES instead of silently
    taking the nearest one. The shift is given both as the dimensionless window
    parameter difference and in millimetres (parameter difference x length)."""
    old_tasks = candidate_window_map(old_decisions)
    new_tasks = candidate_window_map(new_decisions)
    transitions = Counter(); unmatched = Counter(); matched_rows = []
    old_ambiguous = []
    for (target, moved), task in sorted(old_tasks.items()):
        for item in task['windows']:
            if 'SELF_AMBIGUOUS_CLEARANCE' in item['basic_reasons']:
                old_ambiguous.append((target, moved, item))
    for target, moved, item in old_ambiguous:
        entry = dict(target=list(target), moved=moved, candidate_index=item['candidate_index'],
            layer=item['layer'], old_rise_window=list(item['rise_window']),
            old_fall_window=list(item['fall_window']), old_status=item['basic_status'])
        new_task = new_tasks.get((target, moved))
        if new_task is None:
            entry['match'] = 'TASK_NOT_PRESENT_IN_NEW_RUN'; unmatched['TASK_NOT_PRESENT_IN_NEW_RUN'] += 1
            matched_rows.append(entry); continue
        ri, ru, rv = item['rise_window']; fi, fu, fv = item['fall_window']
        rise_length = planar[moved].primitives[ri].length()
        fall_length = planar[moved].primitives[fi].length()
        dr = 2*slack/rise_length + 1e-15
        df = 2*slack/fall_length + 1e-15
        hits = []
        for cand in new_task['windows']:
            cri, cru, crv = cand['rise_window']; cfi, cfu, cfv = cand['fall_window']
            if cand['layer'] != item['layer'] or cri != ri or cfi != fi: continue
            if abs((crv-cru)-(rv-ru)) > 1e-12 or abs((cfv-cfu)-(fv-fu)) > 1e-12: continue
            gap_r, gap_f = abs(cru-ru), abs(cfu-fu)
            if gap_r <= dr and gap_f <= df:
                hits.append((cand, gap_r, gap_f))
        if len(hits) > 1:
            entry.update(match='AMBIGUOUS_MULTIPLE_MATCHES', match_count=len(hits),
                match_reason='%d candidates satisfy the window rule; no unique correspondence is claimed'
                             % len(hits))
            unmatched['AMBIGUOUS_MULTIPLE_MATCHES'] += 1
            matched_rows.append(entry); continue
        if not hits:
            entry['match'] = 'NO_CORRESPONDING_WINDOW'; unmatched['NO_CORRESPONDING_WINDOW'] += 1
            matched_rows.append(entry); continue
        cand, gap_r, gap_f = hits[0]
        entry.update(match='MATCHED', match_count=1, new_candidate_index=cand['candidate_index'],
            new_rise_window=list(cand['rise_window']), new_fall_window=list(cand['fall_window']),
            start_shift_param=[gap_r, gap_f],
            start_shift_mm=[gap_r*rise_length, gap_f*fall_length],
            new_basic_status=cand['basic_status'],
            new_basic_reasons=cand['basic_reasons'], new_full_status=cand['status'],
            new_full_reasons=cand['full_reasons'])
        key = f"{item['basic_status']} -> {cand['basic_status']}"
        transitions[key] += 1
        matched_rows.append(entry)
    task_counts = []
    for key in sorted(set(old_tasks) | set(new_tasks)):
        old_task = old_tasks.get(key); new_task = new_tasks.get(key)
        task_counts.append(dict(target=list(key[0]), moved=key[1],
            old_generated=old_task['generated_count'] if old_task else None,
            new_generated=new_task['generated_count'] if new_task else None,
            old_generation_failure=old_task['generation_failure'] if old_task else None,
            new_generation_failure=new_task['generation_failure'] if new_task else None,
            old_candidate_rows=len(old_task['windows']) if old_task else None,
            new_candidate_rows=len(new_task['windows']) if new_task else None))
    return dict(
        scope='ALL movement classes of the old E run (relocation and first elevation); old diagnostic '
              'slack=0 vs this run slack=%.1e. The relocation-only subset (70 of 208 rows) is reported '
              'by scripts/analyze_relocation_slack_diagnostic.py.' % slack,
        match_rule='exact (target, victim, layer, rise primitive, fall primitive, window width); '
                   'start shift <= 2*slack/length; MATCHED requires exactly one admissible candidate',
        old_self_ambiguous_candidates=len(old_ambiguous),
        matched_to_new_candidate=sum(1 for e in matched_rows if e.get('match') == 'MATCHED'),
        unmatched=dict(unmatched),
        old_to_new_basic_status=dict(transitions),
        matched_rows=matched_rows,
        per_task_generation_counts=task_counts,
        note='Correspondence is established per candidate; the overall drop in ambiguous '
             'counts alone is not used as evidence that a specific old candidate was resolved. '
             'A candidate with no matching window in the new run is reported as unmatched.')


def run_mode(mode, start, planar, crossings, targets, budget, config):
    log(f'mode {mode}: start (window_slack_mm={SLACK})')
    def progress(row, mode=mode):
        if row.get('phase') == 'TARGET_DONE':
            log(f"  {mode} target {row['step']} {row['status']} collisions={row['collisions']} "
                f"evaluations={row['candidate_evaluations']} {row['seconds']:.0f}s")
        elif row.get('phase') == 'INITIAL_DONE':
            log(f"  {mode} INITIAL_DONE collisions={row['collisions']} uncertain={row['uncertain']}")
    result = run_fixed_target_diagnostic(start, planar, config, targets=targets, mode=mode,
        scale=SIZE, progress=progress, saved_crossings=crossings, budget=budget,
        window_slack_mm=SLACK)
    ledger = result['ledger']
    log(f"mode {mode}: done final={ledger['final_collision_pair_count']} "
        f"accepted={ledger['accepted_moves']} relocations={ledger['relocations']} "
        f"evaluations={ledger['candidate_evaluations']} stop={ledger['stop_reason']}")
    save(f'decisions_{mode}.json', result['steps'])
    save(f'curve_{mode}.json', result['curve'])
    save(f'final_routes_{mode}.json', dict(route_count=SIZE,
        routes=[dict(route_id=i, main_layer=route_layer(r), geometry=serialize_route3d(r))
            for i, r in sorted(result['routes'].items())]))
    save(f'collision_sets_{mode}.json', dict(
        initial_collision_pairs=result['initial_collision_pairs'],
        final_collision_pairs=result['final_collision_pairs'],
        initial_unresolved_pairs=result['initial_unresolved_pairs'],
        final_unresolved_pairs=result['final_unresolved_pairs'],
        elevated_route_ids=result['elevated_route_ids']))
    save(f'ledger_{mode}.json', ledger)
    return result


def main():
    log(f'start slack relocation diagnostic slack={SLACK}')
    config = three_layer_config()
    planar, crossings, fingerprints, dataset, inputs = load_planar_and_crossings()
    start = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in json.loads(START_PATH.read_text(encoding='utf-8'))['routes']}
    assert len(start) == SIZE
    elevated = {i for i, r in start.items()
        if any(isinstance(p, CosineTransition3D) for p in r.primitives)}
    pairs, both, one = select_de_targets(start, planar, elevated)
    targets = both + one
    old_target_list = json.loads((OLD_DIAG/'target_list.json').read_text(encoding='utf-8'))
    old_targets = [tuple(t) for t in old_target_list['targets']]
    assert old_targets == targets, ('target list mismatch', old_targets, targets)
    log(f'start state reused: {len(pairs)} close pairs, {len(elevated)} elevated routes; '
        f'targets {len(targets)} (both={len(both)} one={len(one)}) equal to the Step 15 list')
    start_total = sum(r.total_length() for r in start.values())
    planar_total = sum(r.total_length() for r in planar.values())
    old_ledgers = {mode: json.loads((OLD_DIAG/f'ledger_{mode}.json').read_text(encoding='utf-8'))
        for mode in ('D', 'E')}
    old_decisions_E = json.loads((OLD_DIAG/'decisions_E.json').read_text(encoding='utf-8'))

    save('config.json', dict(scale=SIZE, task=TASK, dataset=dataset, input_files=inputs,
        input_sha256=fingerprints, configuration=config_record(config),
        window_slack_mm=SLACK, generation_failure_cache=False,
        start_state=str(START_PATH), start_state_sha256=sha256(START_PATH),
        start_pair_scan_collisions=len(pairs), start_elevated_route_count=len(elevated),
        target_selection_rule=old_target_list['rule'],
        target_list_source=str(OLD_DIAG/'target_list.json'),
        target_list_sha256=sha256(OLD_DIAG/'target_list.json'),
        target_list_reproduced_identically=True,
        targets=[list(t) for t in targets], both_elevated_targets=[list(t) for t in both],
        one_elevated_targets=[list(t) for t in one],
        candidate_budget_ceiling=BUDGET_CEILING,
        budget_unit='one evaluate_elevation basic call per candidate row',
        budget_counts_basic_rejections=True,
        notes=['only change against the Step 15 diagnostic is window_slack_mm=%.1e' % SLACK,
               'structural generation-failure cache stays off',
               'D allows first elevations only; E also allows relocation of already-elevated routes',
               'same start, same target list, same order, same geometry and acceptance rules',
               'only window placements move; the 0.1 mm clearance criterion is unchanged']))
    save('code_version.json', code_version())
    save('environment.json', environment_record())
    save('target_list.json', dict(targets=[list(t) for t in targets],
        both_elevated=[list(t) for t in both], one_elevated=[list(t) for t in one],
        rule=old_target_list['rule'], source='reproduced identically from the Step 15 rule',
        step_15_list_sha256=sha256(OLD_DIAG/'target_list.json')))
    save('old_diagnostic_reference.json', dict(directory=str(OLD_DIAG),
        files={name: dict(sha256=sha256(OLD_DIAG/name))
            for name in ('target_list.json', 'ledger_D.json', 'ledger_E.json', 'decisions_D.json',
                         'decisions_E.json', 'final_routes_D.json', 'final_routes_E.json')},
        reuse='old results are read only; nothing in the old directory is modified',
        old_ledgers={mode: {k: old_ledgers[mode][k] for k in
            ('final_collision_pair_count', 'accepted_moves', 'relocations',
             'relocation_victim_attempts', 'relocation_candidate_evaluations', 'candidate_evaluations',
             'step_length_delta_total_mm', 'final_extra_length_vs_planar_mm', 'runtime_seconds',
             'stop_reason')} for mode in ('D', 'E')}))

    budget = BudgetConfig(SIZE, len(targets), BUDGET_CEILING, True, 'fixed-target D/E ceiling (unchanged)')
    results = {}
    for mode in ('D', 'E'):
        results[mode] = run_mode(mode, start, planar, crossings, targets, budget, config)

    movement = {mode: movement_stats(results[mode]['steps']) for mode in ('D', 'E')}
    step_status = {mode: step_status_counts(results[mode]['steps']) for mode in ('D', 'E')}
    lengths = {mode: length_ledger(results[mode], start_total, planar_total) for mode in ('D', 'E')}
    save('movement_stats.json', dict(
        counting_rule='a candidate is one basic evaluate_elevation call, rejections included; '
                      'reason occurrences count reason strings and may exceed the number of rejected '
                      'candidates because one candidate can carry several reasons; '
                      'candidates_with_reason counts each candidate once per reason; the two are never summed',
        modes=movement, step_status=step_status))
    save('length_ledger.json', dict(
        unit='mm', start_state=str(START_PATH),
        note='single-step delta = new route length - current route length and may be negative',
        modes=lengths))

    correspondence = candidate_correspondence(planar, old_decisions_E, results['E']['steps'],
        SLACK)
    save('candidate_correspondence.json', correspondence)
    log('candidate correspondence: old ambiguous=%d matched=%d unmatched=%s transitions=%s' % (
        correspondence['old_self_ambiguous_candidates'], correspondence['matched_to_new_candidate'],
        correspondence['unmatched'], correspondence['old_to_new_basic_status']))

    rechecks = {}
    for mode in ('D', 'E'):
        rechecks[mode] = saved_state_audit(mode, planar)
        save(f'recheck_{mode}.json', rechecks[mode])
        log(f"mode {mode}: recheck {rechecks[mode]['verdict']} checks={rechecks[mode]['checks']} "
            f"seconds={rechecks[mode]['recheck_seconds']:.1f}")

    rows = []
    for mode in ('D', 'E'):
        ledger = results[mode]['ledger']
        old = old_ledgers[mode]
        rows.append(dict(mode=mode, window_slack_mm=SLACK,
            final_collision_pairs=ledger['final_collision_pair_count'],
            old_final_collision_pairs=old['final_collision_pair_count'],
            net_reduction=ledger['net_collision_reduction'],
            accepted_moves=ledger['accepted_moves'], first_elevations=ledger['first_elevations'],
            relocations=ledger['relocations'], old_relocations=old['relocations'],
            relocation_victim_attempts=ledger['relocation_victim_attempts'],
            old_relocation_victim_attempts=old['relocation_victim_attempts'],
            relocation_candidate_evaluations=ledger['relocation_candidate_evaluations'],
            old_relocation_candidate_evaluations=old['relocation_candidate_evaluations'],
            failed_no_movable_route=ledger['failed_no_movable_route'],
            failed_no_candidates=ledger['failed_no_candidates'],
            failed_all_rejected=ledger['failed_all_rejected'],
            candidate_evaluations=ledger['candidate_evaluations'],
            old_candidate_evaluations=old['candidate_evaluations'],
            generated_candidates=ledger['generated_candidates'],
            full_neighbor_checks=ledger['full_neighbor_checks'],
            step_length_delta_total_mm=ledger['step_length_delta_total_mm'],
            final_extra_length_vs_planar_mm=ledger['final_extra_length_vs_planar_mm'],
            runtime_seconds=ledger['runtime_seconds'], stop_reason=ledger['stop_reason'],
            final_unresolved_pairs=ledger['final_unresolved_pair_count']))
    with (OUT/'comparison_DE.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys())); writer.writeheader()
        for row in rows: writer.writerow(row)

    summary = dict(scale=SIZE, task=TASK, dataset=dataset, window_slack_mm=SLACK,
        generation_failure_cache=False, budget_ceiling=BUDGET_CEILING, target_count=len(targets),
        start_state=dict(path=str(START_PATH), sha256=sha256(START_PATH), collisions=len(pairs),
            elevated_routes=len(elevated), total_length_mm=start_total,
            extra_length_vs_planar_mm=start_total-planar_total,
            unresolved_pairs=results['D']['ledger']['initial_unresolved_pair_count']),
        comparison=rows,
        movement_stats=movement, step_status=step_status,
        length_ledger={mode: {k: v for k, v in lengths[mode].items() if k != 'per_step'}
            for mode in ('D', 'E')},
        candidate_correspondence={k: v for k, v in correspondence.items()
            if k not in ('matched_rows', 'per_task_generation_counts')},
        rechecks={mode: {k: v for k, v in rechecks[mode].items() if k != 'geometry'}
            for mode in ('D', 'E')},
        recheck_geometry={mode: rechecks[mode]['geometry'] for mode in ('D', 'E')},
        note='same budget ceiling for both modes; actual candidate counts differ and are reported as measured')
    save('summary.json', summary)
    manifest = {str(p.relative_to(OUT)): dict(sha256=sha256(p), bytes=p.stat().st_size)
        for p in sorted(OUT.glob('*.json')) if p.name != 'manifest.json'}
    manifest.update({str(p.relative_to(OUT)): dict(sha256=sha256(p), bytes=p.stat().st_size)
        for p in sorted(OUT.glob('*.csv'))})
    save('manifest.json', dict(files=manifest, note='hashes of this run only'))
    log('ALL DONE ' + json.dumps(rows))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        log('FAILED\n'+traceback.format_exc())
        raise
