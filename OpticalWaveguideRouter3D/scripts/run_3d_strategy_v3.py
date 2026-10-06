"""Step 16 driver: 512 four-way ablation of the two default-off strategy-v3 features.

All groups share one input, one start state (the frozen planar z=0 routes), the
same geometry thresholds (0.1 mm clearance, 5 mm radius), candidate-evaluation
budget 720 and target-attempt bound 50, on strategy C. The group letters here
are this round's feature ablation, NOT the historical A/B/C strategies:

    A_baseline_original      generation_failure_cache=False  window_slack_mm=0.0
    B_generation_cache_only  generation_failure_cache=True   window_slack_mm=0.0
    C_window_slack_only      generation_failure_cache=False  window_slack_mm=1e-5
    D_both_enabled           generation_failure_cache=True   window_slack_mm=1e-5

Every group saves configuration, input/source hashes, environment, decisions,
terminal routes, collision sets, budget curve, ledger, a 130,816-pair full
recheck with saved-state reload and geometry invariants, and per-group stats.
Group A is checked against the revised-C rerun (44,274) with the difference
reported, never adjusted for.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v3.py PROJECT OUTDIR [--size 512] [--only NAME]
"""
import sys, json, csv, hashlib, platform, traceback
from collections import Counter
from copy import deepcopy
from math import fsum
from pathlib import Path
from itertools import combinations
from time import perf_counter


def parse_args(argv):
    args = {'size': 512, 'only': None}
    positional = []
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == '--size': args['size'] = int(argv[index+1]); index += 2
        elif token == '--only': args['only'] = argv[index+1]; index += 2
        else: positional.append(token); index += 1
    if len(positional) != 2: raise SystemExit(__doc__)
    args['project'] = Path(positional[0]).resolve(); args['out'] = Path(positional[1]).resolve()
    return args


ARGS = parse_args(sys.argv)
ROOT = ARGS['project']; OUT = ARGS['out']; SIZE = ARGS['size']
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
LOG = (OUT/f'run_v3_{SIZE}.log').open('a', encoding='utf-8')
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
from src.strategy_v2_3d import (frozen_budget, run_strategy_v2, xy_projection_preserved, route_layer)

CLEARANCE = 0.1
REQUIRED_RADIUS = 5.
PREVIOUS_REVISION = ROOT/'outputs/3d_strategy_v2_rev2/512_c_fixed'
SLACK_MM = 1e-5
GROUPS = [
    dict(name='A_baseline_original', generation_failure_cache=False, window_slack_mm=0.0,
        note='historical behaviour, both new features off'),
    dict(name='B_generation_cache_only', generation_failure_cache=True, window_slack_mm=0.0,
        note='structural generation-failure cache and scheduling skip only'),
    dict(name='C_window_slack_only', generation_failure_cache=False, window_slack_mm=SLACK_MM,
        note='window placement slack only'),
    dict(name='D_both_enabled', generation_failure_cache=True, window_slack_mm=SLACK_MM,
        note='both features'),
]


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
    if SIZE != 512: raise SystemExit('this driver is defined for --size 512 (existing synthetic input only)')
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
    files = sorted((ROOT/'src').glob('*.py')) + [Path(__file__).resolve(),
        ROOT/'scripts/verify_window_slack_v3.py']
    return dict(recorded_hashes={str(p.relative_to(ROOT)): sha256(p) for p in files if p.is_file()},
        note='v3 driver; hashes cover src/, this script and the window-slack probe')


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


def saved_state_audit(state_path, sets_path, planar):
    stored = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in json.loads(state_path.read_text(encoding='utf-8'))['routes']}
    geometry = geometry_audit(planar, stored)
    recheck = full_recheck(stored)
    sets = json.loads(sets_path.read_text())
    pairs = set(map(tuple, sets['final_collision_pairs']))
    unknown = set(map(tuple, sets['final_unresolved_pairs']))
    record = dict(reloaded_route_count=len(stored),
        collision_pair_set_matches_incremental=recheck['pairs'] == pairs,
        unresolved_pair_set_matches_incremental=recheck['unknown'] == unknown,
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


def group_stats(result):
    steps = result['steps']; ledger = result['ledger']
    target_counts = Counter(tuple(s['target_pair']) for s in steps)
    rows = [row for s in steps for v in s['victim_attempts'] for row in v['candidates']]
    self_reasons = Counter(r for row in rows for r in (row.get('basic_reasons') or [])
        if r.startswith('SELF_'))
    other_reasons = Counter(r for row in rows for r in (row.get('basic_reasons') or [])
        if not r.startswith('SELF_'))
    full_reasons = Counter(r for row in rows for r in (row.get('full_reasons') or []))
    generation_failures = Counter(str(v.get('generation_failure'))
        for s in steps for v in s['victim_attempts'] if v.get('generated_count', 0) == 0)
    return dict(
        final_collision_pairs=ledger['final_collision_pair_count'],
        final_unresolved_pairs=ledger['final_unresolved_pair_count'],
        initial_collision_pairs=ledger['initial_collision_pair_count'],
        initial_unresolved_pairs=ledger['initial_unresolved_pair_count'],
        accepted_moves=ledger['accepted_moves'], first_elevations=ledger['first_elevations'],
        relocations=ledger['relocations'],
        final_extra_length_mm=ledger['final_extra_length_mm'],
        step_length_delta_total_mm=ledger['total_step_length_delta_mm'],
        final_transition_count=ledger['final_transition_count'],
        target_attempts=ledger['target_attempts'], unique_targets=len(target_counts),
        repeat_attempts=len(steps)-len(target_counts),
        repeated_targets=[dict(pair=list(p), attempts=c) for p, c in target_counts.most_common(5) if c > 1],
        generation_cache_enabled=ledger['generation_failure_cache_enabled'],
        generation_cache_records=ledger['generation_cache_records'],
        generation_cache_zero_candidate_records=ledger['generation_cache_zero_candidate_records'],
        generation_skip_events=ledger['generation_skip_events'],
        generation_skipped_target_count=ledger['generation_skipped_target_count'],
        generated_candidates=ledger['generated_candidates'],
        candidate_evaluations=ledger['candidate_evaluations'], candidate_budget=ledger['candidate_budget'],
        full_neighbor_checks=ledger['full_neighbor_checks'],
        zero_candidate_victim_attempts=sum(1 for s in steps for v in s['victim_attempts']
            if v.get('generated_count', 0) == 0),
        generation_failure_reasons=dict(generation_failures),
        self_rejection_reasons=dict(self_reasons), other_basic_reasons=dict(other_reasons),
        full_rejection_reasons=dict(full_reasons),
        no_acceptable_move_steps=sum(1 for s in steps if s['status'] in
            ('NO_ACCEPTABLE_MOVE', 'NO_IMPROVING_SINGLE_ELEVATION', 'BOTH_ALREADY_ELEVATED')),
        failed_no_candidates=sum(s['status']=='NO_CANDIDATES_GENERATED' for s in steps),
        budget_used_percent=100*ledger['candidate_evaluations']/ledger['candidate_budget'],
        stop_reason=ledger['stop_reason'],
        timings=dict(initial_pair_scan_seconds=ledger['initial_pair_scan_seconds'],
            assignment_seconds=ledger['assignment_seconds'],
            runtime_seconds=ledger['runtime_seconds']))


def previous_revision_reference():
    ledger = json.loads((PREVIOUS_REVISION/'ledger_C_fixed.json').read_text())
    return dict(ledger_sha256=sha256(PREVIOUS_REVISION/'ledger_C_fixed.json'),
        decisions_sha256=sha256(PREVIOUS_REVISION/'decisions_C_fixed.json'),
        final_routes_sha256=sha256(PREVIOUS_REVISION/'final_routes_C_fixed.json'),
        ledger=dict(final_collision_pair_count=ledger['final_collision_pair_count'],
            accepted_moves=ledger['accepted_moves'], candidate_evaluations=ledger['candidate_evaluations'],
            target_attempts=ledger['target_attempts'], stop_reason=ledger['stop_reason'],
            final_extra_length_mm=ledger['final_extra_length_mm']))


def baseline_comparison(result):
    ref = previous_revision_reference()
    stored = {row['route_id']: row['geometry']
        for row in json.loads((PREVIOUS_REVISION/'final_routes_C_fixed.json').read_text())['routes']}
    # JSON round trip converts tuples (e.g. arc _source_*_xy) exactly as saving would.
    current = {i: json.loads(json.dumps(serialize_route3d(r))) for i, r in result['routes'].items()}
    ledger = result['ledger']
    record = dict(previous=ref['ledger'],
        current=dict(final_collision_pair_count=ledger['final_collision_pair_count'],
            accepted_moves=ledger['accepted_moves'], candidate_evaluations=ledger['candidate_evaluations'],
            target_attempts=ledger['target_attempts'], stop_reason=ledger['stop_reason'],
            final_extra_length_mm=ledger['final_extra_length_mm']))
    record['final_pair_count_matches'] = (
        ledger['final_collision_pair_count'] == ref['ledger']['final_collision_pair_count'])
    record['accepted_moves_matches'] = ledger['accepted_moves'] == ref['ledger']['accepted_moves']
    record['evaluations_match'] = ledger['candidate_evaluations'] == ref['ledger']['candidate_evaluations']
    record['stop_reason_matches'] = ledger['stop_reason'] == ref['ledger']['stop_reason']
    record['terminal_routes_identical'] = stored == current
    record['verdict'] = ('EXACT_MATCH' if all(record[k] for k in
        ('final_pair_count_matches', 'accepted_moves_matches', 'evaluations_match',
         'stop_reason_matches', 'terminal_routes_identical')) else 'DIFFERS')
    return record


def run_group(group, planar, crossings, fingerprints, dataset, inputs):
    global OUT
    folder = OUT/group['name']; folder.mkdir(parents=True, exist_ok=True)
    previous_out = OUT; OUT = folder
    try:
        log(f"group {group['name']}: generation_failure_cache={group['generation_failure_cache']} "
            f"window_slack_mm={group['window_slack_mm']}")
        config = three_layer_config()
        initial_routes = {i: deepcopy(r) for i, r in planar.items()}
        budget = frozen_budget(SIZE)
        save('config.json', dict(scale=SIZE, dataset=dataset, input_files=inputs,
            input_sha256=fingerprints, configuration=config_record(config),
            frozen_budget=dict(budget.__dict__),
            group=group['name'], note=group['note'],
            generation_failure_cache=group['generation_failure_cache'],
            window_slack_mm=group['window_slack_mm'],
            strategy='C', feature_ablation=True,
            historical_strategy_letters='A/B/C in this folder refer to this round\'s feature ablation, '
                                       'not the historical strategies'))
        save('code_version.json', code_version())
        save('environment.json', environment_record())
        save('previous_revision_reference.json', previous_revision_reference())
        def progress(row):
            if row.get('phase') == 'TARGET_DONE':
                log(f"  step {row['step']} {row['status']} collisions={row['collisions']} "
                    f"evaluations={row['candidate_evaluations']} {row['seconds']:.0f}s")
            elif row.get('phase') == 'INITIAL_DONE':
                log(f"  INITIAL_DONE collisions={row['collisions']} uncertain={row['uncertain']}")
        started = perf_counter()
        result = run_strategy_v2(initial_routes, planar, config, strategy='C', scale=SIZE,
            progress=progress, saved_crossings=crossings,
            generation_failure_cache=group['generation_failure_cache'],
            window_slack_mm=group['window_slack_mm'])
        stats = group_stats(result)
        stats['run_seconds_including_io'] = perf_counter()-started
        log(f"group {group['name']}: final={stats['final_collision_pairs']} "
            f"accepted={stats['accepted_moves']} evaluations={stats['candidate_evaluations']} "
            f"skips={stats['generation_skip_events']} stop={stats['stop_reason']}")
        save('decisions.json', result['steps'])
        save('generation_skips.json', result['generation_skips'])
        save('curve.json', result['curve'])
        save('final_routes.json', dict(route_count=SIZE,
            routes=[dict(route_id=i, main_layer=route_layer(r), geometry=serialize_route3d(r))
                for i, r in sorted(result['routes'].items())]))
        save('collision_sets.json', dict(
            initial_collision_pairs=result['initial_collision_pairs'],
            final_collision_pairs=result['final_collision_pairs'],
            initial_unresolved_pairs=result['initial_unresolved_pairs'],
            final_unresolved_pairs=result['final_unresolved_pairs'],
            elevated_route_ids=result['elevated_route_ids'],
            relocated_route_ids=result['relocated_route_ids']))
        save('ledger.json', result['ledger'])
        recheck = saved_state_audit(folder/'final_routes.json', folder/'collision_sets.json', planar)
        (folder/'recheck.json').write_text(json.dumps(recheck, indent=2), encoding='utf-8')
        log(f"group {group['name']}: recheck {recheck['verdict']} "
            f"checks={recheck['checks']} seconds={recheck['recheck_seconds']:.1f}")
        stats['recheck'] = {k: v for k, v in recheck.items() if k != 'geometry'}
        stats['recheck_geometry'] = recheck['geometry']
        if group['name'] == 'A_baseline_original':
            stats['previous_revision_comparison'] = baseline_comparison(result)
            log(f"group {group['name']}: previous-revision comparison "
                f"{stats['previous_revision_comparison']['verdict']}")
        (folder/'summary.json').write_text(json.dumps(dict(
            scale=SIZE, dataset=dataset, group=group, input_sha256=fingerprints,
            configuration=config_record(config), budget=dict(budget.__dict__), stats=stats),
            indent=2), encoding='utf-8')
        return stats
    finally:
        OUT = previous_out


def main():
    log(f'start v3 ablation size={SIZE}')
    planar, crossings, fingerprints, dataset, inputs = load_planar_and_crossings()
    groups = [g for g in GROUPS if ARGS['only'] in (None, g['name'])]
    if not groups: raise SystemExit(f"unknown --only value; choose from {[g['name'] for g in GROUPS]}")
    summaries = {}
    for group in groups:
        summaries[group['name']] = run_group(group, planar, crossings, fingerprints, dataset, inputs)
    comparison_path = OUT/'comparison_groups.csv'
    existing = {}
    if comparison_path.exists():
        for row in csv.DictReader(comparison_path.open(encoding='utf-8-sig')):
            existing[row['group']] = row
    for name, stats in summaries.items():
        existing[name] = dict(group=name,
            final_collision_pairs=stats['final_collision_pairs'],
            final_unresolved_pairs=stats['final_unresolved_pairs'],
            accepted_moves=stats['accepted_moves'], relocations=stats['relocations'],
            final_extra_length_mm=stats['final_extra_length_mm'],
            final_transition_count=stats['final_transition_count'],
            target_attempts=stats['target_attempts'], unique_targets=stats['unique_targets'],
            repeat_attempts=stats['repeat_attempts'],
            generation_skip_events=stats['generation_skip_events'],
            generated_candidates=stats['generated_candidates'],
            candidate_evaluations=stats['candidate_evaluations'],
            full_neighbor_checks=stats['full_neighbor_checks'],
            stop_reason=stats['stop_reason'],
            runtime_seconds=round(stats['timings']['runtime_seconds'], 3))
    with comparison_path.open('w', newline='', encoding='utf-8-sig') as f:
        keys = list(next(iter(existing.values())).keys())
        writer = csv.DictWriter(f, fieldnames=keys); writer.writeheader()
        for name in (g['name'] for g in GROUPS):
            if name in existing: writer.writerow(existing[name])
    all_path = OUT/'summary_all.json'
    all_data = json.loads(all_path.read_text()) if all_path.exists() else {}
    all_data.setdefault('scale', SIZE); all_data['dataset'] = dataset
    all_data['input_sha256'] = fingerprints
    all_data.setdefault('groups', {}).update(summaries)
    all_path.write_text(json.dumps(all_data, indent=2), encoding='utf-8')
    log('ALL DONE ' + json.dumps({k: dict(final=v['final_collision_pairs'],
        accepted=v['accepted_moves'], evals=v['candidate_evaluations'],
        stop=v['stop_reason']) for k, v in summaries.items()}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        log('FAILED\n'+traceback.format_exc())
        raise
