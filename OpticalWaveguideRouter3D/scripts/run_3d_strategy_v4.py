"""Step 17 driver: continued full-layout optimisation of the 512-route 3D layout
from the saved v3 group-D terminal state.

Common start state (identical for all six groups):
    outputs/3d_strategy_v3/512_ablation/D_both_enabled/
    - 512 routes, 42,909 centre-line near-distance pairs, 3 unresolved pairs,
      24 first-elevated routes (21 on layer 1, 3 on layer 2).

Six budget experiments, each starting INDEPENDENTLY from that same terminal
state and never from another group's result:

    N720   no relocation, appended candidate budget  720
    R720   relocation allowed, appended candidate budget  720
    N1440  no relocation, appended candidate budget 1440
    R1440  relocation allowed, appended candidate budget 1440
    N2880  no relocation, appended candidate budget 2880
    R2880  relocation allowed, appended candidate budget 2880

"Appended" means the 720 candidate evaluations that produced the common start
state are NOT part of these budgets. Formal target-attempt bound 200 for every
group; the actual stop reason is recorded instead of assuming the budget is
spent.

Every group saves configuration, input hashes, code version, environment,
decisions, generation/route skip events, budget curve, terminal routes, the
near-distance sets, the length ledger, and a saved-state reload + full
130,816-pair recheck with geometry and length invariants.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v4.py PROJECT OUTDIR [--group N720] [--all]
"""
import sys, json, hashlib, platform, traceback
from collections import Counter
from copy import deepcopy
from math import fsum
from pathlib import Path
from itertools import combinations
from time import perf_counter


def parse_args(argv):
    args = {'groups': None, 'budget': None, 'probe': False}
    positional = []; index = 1
    while index < len(argv):
        token = argv[index]
        if token == '--group':
            args.setdefault('groups', [])
            args['groups'] = (args['groups'] or []) + argv[index+1].split(','); index += 2
        elif token == '--budget':
            args['budget'] = int(argv[index+1]); args['probe'] = True; index += 2
        else:
            positional.append(token); index += 1
    if len(positional) != 2: raise SystemExit(__doc__)
    args['project'] = Path(positional[0]).resolve(); args['out'] = Path(positional[1]).resolve()
    return args


ARGS = parse_args(sys.argv)
ROOT = ARGS['project']; OUT = ARGS['out']
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
from src.geometry_3d_diagnostics import analyze_route3d_joins
from src.multi_attribution import deserialize_plot
from src.sequential_elevation_3d import RouteView, pair_status
from src.three_layer_assignment_3d import LayerConfiguration
from src.fixed_1024_routing import serialize_route3d, deserialize_route3d
from src.strategy_v2_3d import xy_projection_preserved, route_layer
from src.strategy_v4_3d import (run_full_layout_v4, MODES, pair_state_distribution,
    elevation_structure)

SIZE = 512
CLEARANCE = 0.1
REQUIRED_RADIUS = 5.
SLACK_MM = 1e-5
MAX_TARGETS = 200
START_STATE = ROOT/'outputs/3d_strategy_v3/512_ablation/D_both_enabled'
GROUPS = [
    dict(name='N720', mode='N', budget=720),
    dict(name='R720', mode='R', budget=720),
    dict(name='N1440', mode='N', budget=1440),
    dict(name='R1440', mode='R', budget=1440),
    dict(name='N2880', mode='N', budget=2880),
    dict(name='R2880', mode='R', budget=2880),
]
GROUP_BY_NAME = {g['name']: g for g in GROUPS}


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


def code_version():
    files = sorted((ROOT/'src').glob('*.py')) + [Path(__file__).resolve()]
    return dict(recorded_hashes={str(p.relative_to(ROOT)): sha256(p) for p in files if p.is_file()},
        note='v4 driver; hashes cover every src/*.py module and this script')


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


def load_start_state():
    routes = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in json.loads((START_STATE/'final_routes.json').read_text(encoding='utf-8'))['routes']}
    sets = json.loads((START_STATE/'collision_sets.json').read_text(encoding='utf-8'))
    return routes, sets


def full_scan(routes, log_prefix='  scan'):
    started = perf_counter(); checks = 0
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    pairs = set(); unknown = set()
    for a, b in combinations(sorted(routes), 2):
        status = pair_status(views[a], views[b], CLEARANCE); checks += 1
        if status == 'COLLISION': pairs.add((a, b))
        elif status != 'CLEAR': unknown.add((a, b))
        if checks % 20000 == 0:
            print(f'{log_prefix} {checks} pairs {perf_counter()-started:.1f}s', flush=True)
    assert checks == len(routes)*(len(routes)-1)//2
    return dict(checks=checks, pairs=pairs, unknown=unknown, seconds=perf_counter()-started)


def geometry_audit(planar, routes):
    endpoints_ok = joins_ok = radius_ok = xy_ok = structure_ok = True; xy_failures = []
    for i, r in routes.items():
        if r.start_point != planar[i].start_point or r.end_point != planar[i].end_point: endpoints_ok = False
        joins = analyze_route3d_joins(r)
        if not (joins.all_C0 and joins.all_C1_direction): joins_ok = False
        for p in r.primitives:
            if isinstance(p, CosineTransition3D) and p.minimum_curvature_radius() < REQUIRED_RADIUS:
                radius_ok = False
        ok, reason = xy_projection_preserved(r, planar[i])
        if not ok: xy_ok = False; xy_failures.append((i, reason))
        # one elevation structure only, never a stacked second one
        structure, structure_reason = elevation_structure(r)
        if not structure: structure_ok = False; xy_failures.append((i, structure_reason))
    return dict(endpoint_invariant=endpoints_ok, joins_C0_C1_direction=joins_ok,
        transition_radius_pass=radius_ok, xy_projection_preserved=xy_ok,
        single_elevation_structure=structure_ok, xy_failures=xy_failures[:10])


def saved_state_audit(state_path, sets_path, planar, planar_total_length, start_total_length):
    stored = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in json.loads(state_path.read_text(encoding='utf-8'))['routes']}
    geometry = geometry_audit(planar, stored)
    recheck = full_scan(stored, log_prefix='  recheck')
    sets = json.loads(sets_path.read_text(encoding='utf-8'))
    pairs = set(map(tuple, sets['final_collision_pairs']))
    unknown = set(map(tuple, sets['final_unresolved_pairs']))
    final_total = sum(r.total_length() for r in stored.values())
    moved = {i for i, r in stored.items() if any(isinstance(p, CosineTransition3D) for p in r.primitives)}
    step_delta_sum = sets['ledger_step_length_delta_mm']
    record = dict(reloaded_route_count=len(stored),
        collision_pair_set_matches_incremental=recheck['pairs'] == pairs,
        unresolved_pair_set_matches_incremental=recheck['unknown'] == unknown,
        geometry=geometry, checks=recheck['checks'], recheck_seconds=recheck['seconds'],
        final_transition_count=sum(isinstance(p, CosineTransition3D) for r in stored.values()
            for p in r.primitives),
        elevated_route_count=len(moved),
        layer_route_counts={str(k): v for k, v in sorted(Counter(route_layer(r)
            for r in stored.values()).items())},
        length_ledger=dict(
            saved_final_total_length_mm=final_total,
            recorded_final_total_length_mm=sets['ledger_final_total_length_mm'],
            total_length_matches=abs(final_total - sets['ledger_final_total_length_mm']) < 1e-9,
            stage_length_delta_mm=final_total - start_total_length,
            stage_length_delta_matches=abs((final_total - start_total_length)
                - sets['ledger_stage_length_delta_mm']) < 1e-6,
            step_length_delta_sum_mm=step_delta_sum,
            step_delta_sum_matches_stage=abs(step_delta_sum
                - (final_total - start_total_length)) < 1e-6,
            final_extra_length_vs_planar_mm=final_total - planar_total_length,
            recorded_final_extra_length_vs_planar_mm=sets['ledger_final_extra_length_vs_planar_mm'],
            final_extra_length_matches=abs((final_total - planar_total_length)
                - sets['ledger_final_extra_length_vs_planar_mm']) < 1e-6),
        final_pair_state_distribution=pair_state_distribution(pairs, moved))
    ok = (record['reloaded_route_count'] == SIZE
        and record['collision_pair_set_matches_incremental']
        and record['unresolved_pair_set_matches_incremental']
        and geometry['endpoint_invariant'] and geometry['joins_C0_C1_direction']
        and geometry['transition_radius_pass'] and geometry['xy_projection_preserved']
        and geometry['single_elevation_structure']
        and record['length_ledger']['total_length_matches']
        and record['length_ledger']['stage_length_delta_matches']
        and record['length_ledger']['step_delta_sum_matches_stage']
        and record['length_ledger']['final_extra_length_matches'])
    record['verdict'] = 'PASS' if ok else 'FAIL'
    return record


def save(folder, name, data):
    def encode(x):
        if isinstance(x, tuple): return list(x)
        if type(x).__name__ == 'Layer': return dict(id=x.id, z=x.z)
        raise TypeError(type(x).__name__)
    (folder/name).write_text(json.dumps(data, default=encode, indent=2, allow_nan=False), encoding='utf-8')


def run_group(group, planar, planar_total_length, start_routes, start_sets, start_pairs, start_unknown,
              start_total_length, crossings, fingerprints, dataset, inputs):
    name = group['name'] + ('_probe' if ARGS['probe'] else '')
    budget = ARGS['budget'] or group['budget']
    folder = OUT/name; folder.mkdir(parents=True, exist_ok=True)
    logpath = folder/f'run_{name}.log'
    logfile = logpath.open('a', encoding='utf-8')
    def log(message):
        text = f'[{perf_counter():.1f}] {name}: {message}'
        print(text, flush=True); logfile.write(text+'\n'); logfile.flush()
    log(f"start mode={group['mode']} appended_candidate_budget={budget} max_targets={MAX_TARGETS} probe={ARGS['probe']}")
    config = three_layer_config()
    initial_routes = {i: deepcopy(r) for i, r in start_routes.items()}
    save(folder, 'config.json', dict(scale=SIZE, dataset=dataset, input_files=inputs,
        input_sha256=fingerprints,
        start_state_directory=str(START_STATE),
        start_state_files={f: sha256(START_STATE/f) for f in
            ('final_routes.json', 'collision_sets.json', 'ledger.json', 'decisions.json')},
        configuration=config_record(config),
        strategy='v4_full_layout', mode=group['mode'], allow_relocation=group['mode'] == 'R',
        appended_candidate_budget=budget, max_targets=MAX_TARGETS,
        candidate_budget_scope='appended to the common start state; the historical 720 evaluations are excluded',
        generation_failure_cache=True, window_slack_mm=SLACK_MM,
        same_start_for_all_groups=True,
        group=group))
    save(folder, 'code_version.json', code_version())
    save(folder, 'environment.json', environment_record())
    started = perf_counter()
    def progress(row):
        if row.get('phase') == 'TARGET_DONE':
            log(f"step {row['step']} {row['status']} pairs={row['collisions']} "
                f"evals={row['candidate_evaluations']} {row['seconds']:.0f}s")
        elif row.get('phase') == 'INITIAL_DONE':
            log(f"INITIAL_DONE pairs={row['collisions']} unresolved={row['uncertain']}")
    result = run_full_layout_v4(initial_routes, planar, config, mode=group['mode'],
        appended_candidate_budget=budget, max_targets=MAX_TARGETS,
        window_slack_mm=SLACK_MM, generation_failure_cache=True, saved_crossings=crossings,
        initial_pairs=start_pairs, initial_uncertain=start_unknown, progress=progress)
    ledger = result['ledger']
    log(f"done final={ledger['final_collision_pair_count']} moves={ledger['accepted_moves']} "
        f"relocations={ledger['relocations']} evals={ledger['candidate_evaluations']} "
        f"stop={ledger['stop_reason']} seconds={perf_counter()-started:.0f}")
    save(folder, 'decisions.json', result['steps'])
    save(folder, 'generation_skips.json', result['generation_skips'])
    save(folder, 'route_skips.json', result['route_skips'])
    save(folder, 'curve.json', result['curve'])
    save(folder, 'final_routes.json', dict(route_count=SIZE,
        routes=[dict(route_id=i, main_layer=route_layer(r), geometry=serialize_route3d(r))
            for i, r in sorted(result['routes'].items())]))
    save(folder, 'collision_sets.json', dict(
        initial_collision_pairs=result['initial_collision_pairs'],
        final_collision_pairs=result['final_collision_pairs'],
        initial_unresolved_pairs=result['initial_unresolved_pairs'],
        final_unresolved_pairs=result['final_unresolved_pairs'],
        elevated_route_ids=result['elevated_route_ids'],
        relocated_route_ids=result['relocated_route_ids'],
        ledger_step_length_delta_mm=ledger['total_step_length_delta_mm'],
        ledger_stage_length_delta_mm=ledger['stage_length_delta_mm'],
        ledger_final_total_length_mm=ledger['final_total_length_mm'],
        ledger_final_extra_length_vs_planar_mm=ledger['final_extra_length_vs_planar_mm']))
    save(folder, 'ledger.json', ledger)
    recheck = saved_state_audit(folder/'final_routes.json', folder/'collision_sets.json', planar,
        planar_total_length, start_total_length)
    (folder/'recheck.json').write_text(json.dumps(recheck, indent=2), encoding='utf-8')
    log(f"recheck {recheck['verdict']} checks={recheck['checks']} seconds={recheck['recheck_seconds']:.1f}")
    stats = dict(
        mode=group['mode'], appended_candidate_budget=budget, max_targets=MAX_TARGETS,
        initial_collision_pairs=ledger['initial_collision_pair_count'],
        initial_unresolved_pairs=ledger['initial_unresolved_pair_count'],
        final_collision_pairs=ledger['final_collision_pair_count'],
        final_unresolved_pairs=ledger['final_unresolved_pair_count'],
        net_collision_reduction=ledger['net_collision_reduction'],
        initial_pair_state_distribution=ledger['initial_pair_state_distribution'],
        final_pair_state_distribution=ledger['final_pair_state_distribution'],
        accepted_moves=ledger['accepted_moves'], first_elevations=ledger['first_elevations'],
        relocations=ledger['relocations'],
        first_elevation_net_reduction=ledger['first_elevation_net_reduction'],
        relocation_net_reduction=ledger['relocation_net_reduction'],
        total_old_collisions_removed=ledger['total_old_collisions_removed'],
        total_new_collisions_created=ledger['total_new_collisions_created'],
        generated_candidates=ledger['generated_candidates'],
        candidate_evaluations=ledger['candidate_evaluations'],
        full_neighbor_checks=ledger['full_neighbor_checks'],
        full_acceptance_passes=ledger['full_acceptance_passes'],
        executed_moves=ledger['executed_moves'],
        budget_exhausted=ledger['budget_exhausted'], stop_reason=ledger['stop_reason'],
        target_attempts=ledger['target_attempts'],
        generation_skip_events=ledger['generation_skip_events'],
        no_movable_route_skip_events=ledger['no_movable_route_skip_events'],
        relocation_candidate_evaluations=ledger['relocation_candidate_evaluations'],
        first_elevation_candidate_evaluations=ledger['first_elevation_candidate_evaluations'],
        stage_length_delta_mm=ledger['stage_length_delta_mm'],
        final_extra_length_vs_planar_mm=ledger['final_extra_length_vs_planar_mm'],
        start_extra_length_vs_planar_mm=ledger['start_extra_length_vs_planar_mm'],
        step_length_delta_min_mm=ledger['step_length_delta_min_mm'],
        final_transition_count=ledger['final_transition_count'],
        final_elevated_route_count=ledger['final_elevated_route_count'],
        layer_route_counts=ledger['layer_route_counts'],
        basic_rejection_reason_counts=ledger['basic_rejection_reason_counts'],
        full_rejection_reason_counts=ledger['full_rejection_reason_counts'],
        generation_failure_reason_counts=ledger['generation_failure_reason_counts'],
        budget_checkpoints=ledger['budget_checkpoints'],
        timings=dict(initial_pair_scan_seconds=ledger['initial_pair_scan_seconds'],
            assignment_seconds=ledger['assignment_seconds'],
            runtime_seconds=ledger['runtime_seconds']),
        run_seconds_including_io=perf_counter()-started,
        recheck={k: v for k, v in recheck.items() if k != 'geometry'},
        recheck_geometry=recheck['geometry'],
        recheck_length_ledger=recheck['length_ledger'])
    save(folder, 'summary.json', dict(scale=SIZE, dataset=dataset, group=group,
        configuration=config_record(config), stats=stats))
    logfile.close()
    return stats


def main():
    planar, crossings, fingerprints, dataset, inputs = load_planar_and_crossings()
    start_routes, start_sets = load_start_state()
    planar_total_length = sum(r.total_length() for r in planar.values())
    start_total_length = sum(r.total_length() for r in start_routes.values())
    start_unknown = set(map(tuple, start_sets['final_unresolved_pairs']))
    saved_pairs = set(map(tuple, start_sets['final_collision_pairs']))
    start = perf_counter()
    print('full rescan of the common start state ...', flush=True)
    scan = full_scan(start_routes)
    print(f'  scanned {scan["checks"]} pairs in {scan["seconds"]:.1f}s', flush=True)
    moved = {i for i, r in start_routes.items()
        if any(isinstance(p, CosineTransition3D) for p in r.primitives)}
    state = dict(
        start_state_directory=str(START_STATE),
        start_state_files={f: sha256(START_STATE/f) for f in
            ('final_routes.json', 'collision_sets.json', 'ledger.json', 'decisions.json', 'summary.json')},
        route_count=len(start_routes), checks=scan['checks'],
        recomputed_collision_pair_count=len(scan['pairs']),
        saved_collision_pair_count=len(saved_pairs),
        recomputed_pair_set_matches_saved=scan['pairs'] == saved_pairs,
        recomputed_unresolved_pair_count=len(scan['unknown']),
        saved_unresolved_pair_count=len(start_unknown),
        recomputed_unresolved_set_matches_saved=scan['unknown'] == start_unknown,
        elevated_route_count=len(moved),
        layer_route_counts={str(k): v for k, v in sorted(Counter(route_layer(r)
            for r in start_routes.values()).items())},
        pair_state_distribution=pair_state_distribution(scan['pairs'], moved),
        start_total_length_mm=start_total_length, planar_total_length_mm=planar_total_length,
        start_extra_length_vs_planar_mm=start_total_length - planar_total_length,
        scan_seconds=scan['seconds'], total_seconds=perf_counter()-start)
    ok = (state['recomputed_pair_set_matches_saved']
        and state['recomputed_unresolved_set_matches_saved']
        and state['recomputed_collision_pair_count'] == 42909
        and state['elevated_route_count'] == 24
        and state['recomputed_unresolved_pair_count'] == 3)
    state['verdict'] = 'PASS' if ok else 'FAIL'
    wanted_preview = ARGS['groups'] or [g['name'] for g in GROUPS]
    check_name = ('start_state_check.json' if len(wanted_preview) == len(GROUPS)
        else f"start_state_check_{'_'.join(sorted(wanted_preview))}.json")
    (OUT/check_name).write_text(json.dumps(state, indent=2), encoding='utf-8')
    print('start state: ' + json.dumps({k: state[k] for k in
        ('recomputed_collision_pair_count', 'recomputed_unresolved_pair_count',
         'elevated_route_count', 'pair_state_distribution', 'verdict')}), flush=True)
    if not ok: raise SystemExit('START_STATE_CHECK_FAILED')
    wanted = ARGS['groups'] or [g['name'] for g in GROUPS]
    unknown = [n for n in wanted if n not in GROUP_BY_NAME]
    if unknown: raise SystemExit(f'unknown --group {unknown}; choose from {list(GROUP_BY_NAME)}')
    for name in wanted:
        run_group(GROUP_BY_NAME[name], planar, planar_total_length, start_routes, start_sets,
            scan['pairs'], scan['unknown'], start_total_length, crossings, fingerprints, dataset, inputs)
    print('ALL GROUPS DONE ' + ','.join(wanted), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('FAILED\n' + traceback.format_exc(), flush=True)
        raise
