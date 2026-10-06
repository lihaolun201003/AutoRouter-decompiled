"""Step 15 revision driver: corrected-C rerun and fixed-target D/E diagnostic.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2_rev2.py PROJECT OUTDIR --task c_fixed --size 512
    .venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2_rev2.py PROJECT OUTDIR --task c_fixed --size 1024
    .venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2_rev2.py PROJECT OUTDIR --task de --size 512

Read-only on every earlier artifact; outputs go only into OUTDIR.
"""
import sys, json, csv, hashlib, traceback
from copy import deepcopy
from math import fsum
from pathlib import Path
from itertools import combinations
from time import perf_counter


def parse_args(argv):
    args = {'task': None, 'size': 512}
    positional = []
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == '--task': args['task'] = argv[index+1]; index += 2
        elif token == '--size': args['size'] = int(argv[index+1]); index += 2
        else: positional.append(token); index += 1
    if len(positional) != 2 or args['task'] not in ('c_fixed', 'de'):
        raise SystemExit(__doc__)
    args['project'] = Path(positional[0]).resolve(); args['out'] = Path(positional[1]).resolve()
    return args


ARGS = parse_args(sys.argv)
ROOT = ARGS['project']; OUT = ARGS['out']; SIZE = ARGS['size']; TASK = ARGS['task']
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
LOG = (OUT/f'{TASK}_{SIZE}.log').open('a', encoding='utf-8')
def log(message):
    text = f'[{perf_counter():.1f}] {message}'
    print(text, flush=True); LOG.write(text+'\n'); LOG.flush()

from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
from src.geometry_3d_diagnostics import analyze_route3d_joins
from src.multi_attribution import deserialize_plot
from src.sequential_elevation_3d import RouteView, pair_status
from src.three_layer_assignment_3d import LayerConfiguration
from src.fixed_1024_routing import (legacy_waveguides_from_seed, generate_fixed_1024_input,
    build_fixed_1024_geometry, serialize_route3d, deserialize_route3d)
from src.strategy_v2_3d import (BudgetConfig, run_strategy_v2, run_fixed_target_diagnostic,
    frozen_budget, xy_projection_preserved, route_layer)
from src.collision import find_smoothed_route_intersections_2d

CLEARANCE = 0.1
REQUIRED_RADIUS = 5.
SOURCE = ROOT/'outputs'/'3d_strategy_v2'


def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def three_layer_config():
    return LayerConfiguration([Layer(0, 0.), Layer(1, 1.), Layer(2, 2.)], CLEARANCE, REQUIRED_RADIUS,
        'LINE_ONLY_FINITE_WINDOWS', 'EXPERIMENTAL_SYNTHETIC')


def config_record(config):
    return dict(layers=[dict(id=l.id, z=l.z) for l in config.layers], clearance_mm=config.clearance_mm,
        required_radius_mm=config.required_radius_mm, transition_policy=config.transition_policy,
        parameter_status=config.parameter_status)


def load_planar_and_crossings():
    if SIZE == 512:
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
    seedpath = ROOT/'data/fixed_1024_legacy_seed.json'
    seed = json.loads(seedpath.read_text())
    data = generate_fixed_1024_input(legacy_waveguides_from_seed(seed))
    planar2d, routes, stats = build_fixed_1024_geometry(data)
    assert len(routes) == 1024 and stats['assignment_status_counts'] == {'assigned': 960, 'unsupported_geometry': 64}
    class PlanarCrossingAnchors:
        def get(self, pair):
            return [Point3D(e.point.x, e.point.y, 0.)
                for e in find_smoothed_route_intersections_2d(planar2d[pair[0]], planar2d[pair[1]])
                if e.kind == 'cross' and e.point is not None]
    return routes, PlanarCrossingAnchors(), {str(seedpath): sha256(seedpath)}, \
        'FIXED_1024_FROM_LEGACY_512_DOUBLE_COVER', [str(seedpath)]


def save(name, data):
    def encode(x):
        if isinstance(x, tuple): return list(x)
        if type(x).__name__ == 'Layer': return dict(id=x.id, z=x.z)
        raise TypeError(type(x).__name__)
    (OUT/name).write_text(json.dumps(data, default=encode, indent=2, allow_nan=False), encoding='utf-8')


def code_version():
    files = sorted((ROOT/'src').glob('*.py')) + [Path(__file__).resolve(),
        ROOT/'scripts/run_3d_strategy_v2.py']
    return dict(recorded_hashes={str(p.relative_to(ROOT)): sha256(p) for p in files if p.is_file()},
        note='revision driver; hashes cover src/, this script and the original driver')


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


def load_saved_state(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return {row['route_id']: deserialize_route3d(row['geometry']) for row in data['routes']}


def saved_state_audit(state, planar, tag):
    stored = load_saved_state(OUT/state)
    geometry = geometry_audit(planar, stored)
    recheck = full_recheck(stored)
    pairs = set(map(tuple, json.loads((OUT/f'collision_sets_{tag}.json').read_text())['final_collision_pairs']))
    unknown = set(map(tuple, json.loads((OUT/f'collision_sets_{tag}.json').read_text())['final_unresolved_pairs']))
    record = dict(collision_pair_set_matches_incremental=recheck['pairs'] == pairs,
        unresolved_pair_set_matches_incremental=recheck['unknown'] == unknown,
        geometry=geometry, checks=recheck['checks'], recheck_seconds=recheck['seconds'],
        reloaded_route_count=len(stored),
        final_transition_count=sum(isinstance(p, CosineTransition3D) for r in stored.values() for p in r.primitives))
    assert (record['collision_pair_set_matches_incremental'] and record['unresolved_pair_set_matches_incremental']
            and geometry['endpoint_invariant'] and geometry['joins_C0_C1_direction']
            and geometry['transition_radius_pass'] and geometry['xy_projection_preserved']), record
    return record


def prior_reference():
    ref = {}
    for strategy in ('A', 'B'):
        folder = SOURCE/f'{SIZE}_three_layer_abc'
        ledger_path = folder/f'ledger_{strategy}.json'
        sets_path = folder/f'collision_sets_{strategy}.json'
        ref[strategy] = dict(ledger=json.loads(ledger_path.read_text(encoding='utf-8')),
            ledger_sha256=sha256(ledger_path), collision_sets_sha256=sha256(sets_path),
            source='previous verified run, reused without re-execution')
    return ref


def run_c_fixed():
    log(f'start c_fixed size={SIZE}')
    config = three_layer_config()
    planar, crossings, fingerprints, dataset, inputs = load_planar_and_crossings()
    initial_routes = {i: deepcopy(r) for i, r in planar.items()}
    budget = frozen_budget(SIZE)
    save('config.json', dict(scale=SIZE, task='c_fixed', dataset=dataset, input_files=inputs,
        input_sha256=fingerprints, configuration=config_record(config),
        budget_unit='one evaluate_elevation basic call per candidate row',
        budget_counts_basic_rejections=True, frozen_budget=dict(budget.__dict__),
        failure_cache_rule='global layout version: any accepted edit invalidates a cached failure',
        second_victim_rule='selected victim attempt priority_index == 1',
        strategy='C', notes=['relocation of already-elevated routes is enabled',
            'failure cache tracks the global layout version (corrected)',
            'A/B results are reused from the previous verified run (not re-executed)']))
    save('code_version.json', code_version())
    save('prior_AB_reference.json', prior_reference())
    def progress(row):
        if row.get('phase') == 'TARGET_DONE':
            log(f'  C step {row["step"]} {row["status"]} collisions={row["collisions"]} '
                f'evaluations={row["candidate_evaluations"]} {row["seconds"]:.0f}s')
        elif row.get('phase') == 'INITIAL_DONE':
            log(f'  C INITIAL_DONE collisions={row["collisions"]} uncertain={row["uncertain"]}')
    result = run_strategy_v2(initial_routes, planar, config, strategy='C', scale=SIZE,
        progress=progress, saved_crossings=crossings)
    ledger = dict(result['ledger'])
    log(f'c_fixed done final={ledger["final_collision_pair_count"]} accepted={ledger["accepted_moves"]} '
        f'relocations={ledger["relocations"]} evaluations={ledger["candidate_evaluations"]} '
        f'stop={ledger["stop_reason"]}')
    save('decisions_C_fixed.json', result['steps'])
    save('curve_C_fixed.json', result['curve'])
    save('final_routes_C_fixed.json', dict(route_count=SIZE,
        routes=[dict(route_id=i, main_layer=route_layer(r), geometry=serialize_route3d(r))
            for i, r in sorted(result['routes'].items())]))
    save('collision_sets_C_fixed.json', dict(
        initial_collision_pairs=result['initial_collision_pairs'],
        final_collision_pairs=result['final_collision_pairs'],
        initial_unresolved_pairs=result['initial_unresolved_pairs'],
        final_unresolved_pairs=result['final_unresolved_pairs'],
        elevated_route_ids=result['elevated_route_ids'],
        relocated_route_ids=result['relocated_route_ids']))
    save('ledger_C_fixed.json', ledger)
    recheck = saved_state_audit('final_routes_C_fixed.json', planar, 'C_fixed')
    save('recheck_C_fixed.json', recheck)
    log(f'c_fixed recheck PASS {recheck}')
    save('summary_C_fixed.json', dict(scale=SIZE, task='c_fixed', configuration=config_record(config),
        budget=dict(budget.__dict__), input_sha256=fingerprints, ledger=ledger, recheck=recheck,
        prior_AB_reference_sha256={s: prior_reference()[s]['ledger_sha256'] for s in ('A', 'B')}))
    log('c_fixed ALL DONE')


def select_de_targets(routes, planar, elevated):
    """Pre-declared deterministic selection: from the frozen start state's
    current collision pairs, sorted by route-id tuple, take at most 10 pairs
    with both routes elevated and at most 10 pairs with exactly one elevated.
    No post-hoc ranking by outcome."""
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    pairs = []
    for a, b in combinations(sorted(routes), 2):
        if pair_status(views[a], views[b], CLEARANCE) == 'COLLISION': pairs.append((a, b))
    both = sorted(p for p in pairs if p[0] in elevated and p[1] in elevated)[:10]
    one = sorted(p for p in pairs if (p[0] in elevated) ^ (p[1] in elevated))[:10]
    return pairs, both, one


def run_de():
    assert SIZE == 512, 'D/E diagnostic is defined on the 512-route B terminal state'
    log('start de diagnostic size=512')
    config = three_layer_config()
    planar, crossings, fingerprints, dataset, inputs = load_planar_and_crossings()
    start_path = SOURCE/'512_three_layer_abc'/'final_routes_B.json'
    start = load_saved_state(start_path)
    assert len(start) == 512
    elevated = {i for i, r in start.items()
        if any(isinstance(p, CosineTransition3D) for p in r.primitives)}
    pairs, both, one = select_de_targets(start, planar, elevated)
    targets = both + one
    log(f'start state: {len(pairs)} colliding pairs, {len(elevated)} elevated routes; '
        f'targets: both-elevated={len(both)} one-elevated={len(one)} total={len(targets)}')
    save('config.json', dict(scale=512, task='de', dataset=dataset, input_files=inputs,
        input_sha256=fingerprints, configuration=config_record(config),
        start_state=str(start_path), start_state_sha256=sha256(start_path),
        start_pair_scan_collisions=len(pairs), start_elevated_route_count=len(elevated),
        target_selection_rule='from frozen start pairs sorted by route-id tuple: at most 10 both-elevated '
                              'pairs, then at most 10 one-elevated pairs; no outcome-based ranking',
        targets=[list(t) for t in targets], both_elevated_targets=[list(t) for t in both],
        one_elevated_targets=[list(t) for t in one],
        candidate_budget_ceiling=720, budget_unit='one evaluate_elevation basic call per candidate row',
        notes=['D allows first elevations only (B rules on the fixed list)',
               'E additionally allows relocation of already-elevated routes',
               'both modes share start, list, order, geometry, acceptance rules and budget ceiling']))
    save('code_version.json', code_version())
    save('target_list.json', dict(targets=[list(t) for t in targets],
        both_elevated=[list(t) for t in both], one_elevated=[list(t) for t in one],
        rule='pre-declared before running D/E'))
    budget = BudgetConfig(512, len(targets), 720, True, 'D/E diagnostic ceiling')
    results = {}
    for mode in ('D', 'E'):
        log(f'mode {mode}: start')
        def progress(row, mode=mode):
            if row.get('phase') == 'TARGET_DONE':
                log(f'  {mode} target {row["step"]} {row["status"]} collisions={row["collisions"]} '
                    f'evaluations={row["candidate_evaluations"]} {row["seconds"]:.0f}s')
        result = run_fixed_target_diagnostic(start, planar, config, targets=targets, mode=mode,
            scale=512, progress=progress, saved_crossings=crossings, budget=budget)
        results[mode] = result
        ledger = result['ledger']
        log(f'mode {mode}: done final={ledger["final_collision_pair_count"]} '
            f'accepted={ledger["accepted_moves"]} relocations={ledger["relocations"]} '
            f'evaluations={ledger["candidate_evaluations"]} stop={ledger["stop_reason"]}')
        save(f'decisions_{mode}.json', result['steps'])
        save(f'curve_{mode}.json', result['curve'])
        save(f'final_routes_{mode}.json', dict(route_count=512,
            routes=[dict(route_id=i, main_layer=route_layer(r), geometry=serialize_route3d(r))
                for i, r in sorted(result['routes'].items())]))
        save(f'collision_sets_{mode}.json', dict(
            initial_collision_pairs=result['initial_collision_pairs'],
            final_collision_pairs=result['final_collision_pairs'],
            initial_unresolved_pairs=result['initial_unresolved_pairs'],
            final_unresolved_pairs=result['final_unresolved_pairs'],
            elevated_route_ids=result['elevated_route_ids']))
        save(f'ledger_{mode}.json', ledger)
        recheck = saved_state_audit(f'final_routes_{mode}.json', planar, mode)
        save(f'recheck_{mode}.json', recheck)
        log(f'mode {mode}: recheck PASS')
    rows = []
    for mode in ('D', 'E'):
        ledger = results[mode]['ledger']
        rows.append(dict(mode=mode, final_collision_pairs=ledger['final_collision_pair_count'],
            net_reduction=ledger['net_collision_reduction'], accepted_moves=ledger['accepted_moves'],
            first_elevations=ledger['first_elevations'], relocations=ledger['relocations'],
            relocation_victim_attempts=ledger['relocation_victim_attempts'],
            relocation_candidate_evaluations=ledger['relocation_candidate_evaluations'],
            failed_no_movable_route=ledger['failed_no_movable_route'],
            failed_no_candidates=ledger['failed_no_candidates'],
            failed_all_rejected=ledger['failed_all_rejected'],
            candidate_evaluations=ledger['candidate_evaluations'],
            step_length_delta_total_mm=ledger['step_length_delta_total_mm'],
            final_extra_length_vs_planar_mm=ledger['final_extra_length_vs_planar_mm'],
            runtime_seconds=ledger['runtime_seconds'], stop_reason=ledger['stop_reason']))
    with (OUT/'comparison_DE.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys())); writer.writeheader()
        for row in rows: writer.writerow(row)
    save('summary_DE.json', dict(scale=512, task='de', budget_ceiling=720,
        target_count=len(targets), start_state=dict(path=str(start_path), sha256=sha256(start_path),
            collisions=len(pairs), elevated_routes=len(elevated)),
        comparison=rows, note='same budget ceiling; actual candidate counts may differ and are reported'))
    log('de ALL DONE ' + json.dumps(rows))


def main():
    if TASK == 'c_fixed': run_c_fixed()
    else: run_de()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        log('FAILED\n'+traceback.format_exc())
        raise
