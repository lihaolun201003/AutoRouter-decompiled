"""Step 15 driver: run three-layer selection strategies A/B/C under the frozen
candidate-evaluation budget, save raw records, then reload and re-check.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2.py PROJECT OUTDIR --size 512
    .venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2.py PROJECT OUTDIR --size 1024

Read-only with respect to every historical artifact: outputs are written only
inside OUTDIR.
"""
import sys,json,csv,hashlib,traceback
from copy import deepcopy
from math import fsum
from pathlib import Path
from collections import Counter
from dataclasses import asdict
from itertools import combinations
from time import perf_counter


def parse_args(argv):
    args={'size':512,'strategies':'A,B,C'}
    positional=[];index=1
    while index<len(argv):
        token=argv[index]
        if token=='--size':args['size']=int(argv[index+1]);index+=2
        elif token=='--strategies':args['strategies']=argv[index+1];index+=2
        else:positional.append(token);index+=1
    if len(positional)!=2:
        raise SystemExit('usage: run_3d_strategy_v2.py PROJECT OUTDIR [--size 512|1024] [--strategies A,B,C]')
    args['project']=Path(positional[0]).resolve();args['out']=Path(positional[1]).resolve()
    return args


ARGS=parse_args(sys.argv)
ROOT=ARGS['project'];OUT=ARGS['out'];SIZE=ARGS['size']
STRATEGIES=[s.strip() for s in ARGS['strategies'].split(',') if s.strip()]
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
LOG=(OUT/f'run_{SIZE}.log').open('a',encoding='utf-8')
def log(message):
    text=f'[{perf_counter():.1f}] {message}'
    print(text,flush=True);LOG.write(text+'\n');LOG.flush()

from src.models import Layer,Point3D
from src.geometry_3d import lift_smoothed_route_to_layer,CosineTransition3D
from src.geometry_3d_diagnostics import analyze_route3d_joins
from src.multi_attribution import deserialize_plot
from src.sequential_elevation_3d import RouteView,pair_status
from src.three_layer_assignment_3d import LayerConfiguration
from src.fixed_1024_routing import (legacy_waveguides_from_seed,generate_fixed_1024_input,
    build_fixed_1024_geometry,serialize_route3d,deserialize_route3d)
from src.strategy_v2_3d import (run_strategy_v2,frozen_budget,xy_projection_preserved,route_layer)
from src.collision import find_smoothed_route_intersections_2d

CLEARANCE=0.1;REQUIRED_RADIUS=5.


def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def three_layer_config():
    return LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],CLEARANCE,REQUIRED_RADIUS,
        'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')


def config_record(config):
    return dict(layers=[dict(id=l.id,z=l.z) for l in config.layers],clearance_mm=config.clearance_mm,
        required_radius_mm=config.required_radius_mm,transition_policy=config.transition_policy,
        parameter_status=config.parameter_status)


def load_inputs():
    """Returns (planar routes, crossings, fingerprints, dataset label, input files)."""
    if SIZE==512:
        plotpath=ROOT/'outputs/step_8_5_legacy_512_plot_geometry.json'
        eventpath=ROOT/'outputs/step_8_5_legacy_512_physical_events.jsonl'
        planar={r['id']:lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0))
            for r in json.loads(plotpath.read_text())['routes']}
        assert len(planar)==512
        crossings={}
        for text in eventpath.read_text().splitlines():
            e=json.loads(text)
            if e['kind']=='cross':
                crossings.setdefault(tuple(sorted((e['route_a_id'],e['route_b_id']))),[]).append(
                    Point3D(e['point']['x'],e['point']['y'],0))
        fingerprints={str(plotpath):sha256(plotpath),str(eventpath):sha256(eventpath)}
        return dict(planar=planar,crossings=crossings,fingerprints=fingerprints,
            dataset='LEGACY_512_SMOOTHED_P0',inputs=[str(plotpath),str(eventpath)])
    seedpath=ROOT/'data/fixed_1024_legacy_seed.json'
    seed=json.loads(seedpath.read_text())
    data=generate_fixed_1024_input(legacy_waveguides_from_seed(seed))
    planar2d,routes,stats=build_fixed_1024_geometry(data)
    assert len(routes)==1024 and stats['assignment_status_counts']=={'assigned':960,'unsupported_geometry':64}
    class PlanarCrossingAnchors:
        def get(self,pair):
            return [Point3D(e.point.x,e.point.y,0.)
                for e in find_smoothed_route_intersections_2d(planar2d[pair[0]],planar2d[pair[1]])
                if e.kind=='cross' and e.point is not None]
    fingerprints={str(seedpath):sha256(seedpath)}
    return dict(planar=routes,crossings=PlanarCrossingAnchors(),fingerprints=fingerprints,
        dataset='FIXED_1024_FROM_LEGACY_512_DOUBLE_COVER',inputs=[str(seedpath)])


def save(name,data):
    def encode(x):
        if isinstance(x,tuple):return list(x)
        if type(x).__name__=='Layer':return dict(id=x.id,z=x.z)
        raise TypeError(type(x).__name__)
    (OUT/name).write_text(json.dumps(data,default=encode,indent=2,allow_nan=False),encoding='utf-8')


def code_version():
    files=sorted((ROOT/'src').glob('*.py'))+[ROOT/'scripts/run_3d_strategy_v2.py']
    record={str(p.relative_to(ROOT)):sha256(p) for p in files if p.is_file()}
    return dict(recorded_hashes=record,git_present=(ROOT/'.git').exists(),
        note='no git repository; source hashes recorded')


def full_recheck(routes):
    """Full pair re-check of one final state, identically to the incremental
    classifier. Read-only."""
    started=perf_counter();checks=0
    for i,r in routes.items():
        r.validate()
    views={i:RouteView.prepare(r) for i,r in routes.items()}
    pairs=set();unknown=set()
    for a,b in combinations(sorted(routes),2):
        status=pair_status(views[a],views[b],CLEARANCE);checks+=1
        if status=='COLLISION':pairs.add((a,b))
        elif status!='CLEAR':unknown.add((a,b))
        if checks%100000==0:log(f'  recheck {checks} pairs {perf_counter()-started:.1f}s')
    expected_checks=SIZE*(SIZE-1)//2
    assert checks==expected_checks,('CHECK_COUNT',checks,expected_checks)
    return dict(checks=checks,pairs=pairs,unknown=unknown,seconds=perf_counter()-started)


def route_geometry_audit(planar,routes):
    endpoints_ok=True;joins_ok=True;radius_ok=True;xy_ok=True;xy_failures=[]
    for i,r in routes.items():
        if r.start_point!=planar[i].start_point or r.end_point!=planar[i].end_point:endpoints_ok=False
        joins=analyze_route3d_joins(r)
        if not (joins.all_C0 and joins.all_C1_direction):joins_ok=False
        for p in r.primitives:
            if isinstance(p,CosineTransition3D) and p.minimum_curvature_radius()<REQUIRED_RADIUS:
                radius_ok=False
        ok,reason=xy_projection_preserved(r,planar[i])
        if not ok:xy_ok=False;xy_failures.append((i,reason))
    return dict(endpoint_invariant=endpoints_ok,joins_C0_C1_direction=joins_ok,
        transition_radius_pass=radius_ok,xy_projection_preserved=xy_ok,xy_failures=xy_failures[:10])


def historical_reference():
    if SIZE==512:
        summary_path=ROOT/'outputs/step_9_f_three_layer_summary.json'
        sets_path=ROOT/'outputs/step_9_f_three_layer_collision_sets.json'
    else:
        summary_path=ROOT/'outputs/step_10_fixed_1024_summary.json'
        sets_path=ROOT/'outputs/step_10_fixed_1024_collision_sets.json'
    if not summary_path.is_file():return None
    reference={'summary_path':str(summary_path),'summary_sha256':sha256(summary_path),
        'summary':json.loads(summary_path.read_text())}
    if sets_path.is_file():
        reference['collision_sets_path']=str(sets_path)
        reference['collision_sets_sha256']=sha256(sets_path)
        reference['collision_sets']=json.loads(sets_path.read_text())
    return reference


def compare_with_history(result,reference):
    if reference is None:return dict(status='HISTORY_NOT_FOUND')
    historical=reference['summary']
    measured_pairs=set(map(tuple,result['final_collision_pairs']))
    measured_unknown=set(map(tuple,result['final_unresolved_pairs']))
    record=dict(status='COMPARED',
        historical_final_pairs=historical.get('final_collision_pair_count',historical.get('final_collision_pairs')),
        measured_final_pairs=len(measured_pairs),
        historical_initial_pairs=historical.get('initial_collision_pair_count',historical.get('initial_collision_pairs')),
        measured_initial_pairs=result['ledger']['initial_collision_pair_count'],
        historical_successful_elevations=historical.get('successful_elevations'),
        measured_accepted_first_elevations=result['ledger']['first_elevations'],
        historical_total_extra_length_mm=historical.get('total_extra_length_mm'),
        measured_total_extra_length_mm=result['ledger']['final_extra_length_mm'],
        historical_runtime_seconds=historical.get('runtime_seconds',historical.get('runtime')),
        measured_runtime_seconds=result['ledger']['runtime_seconds'])
    if 'collision_sets' in reference:
        sets=reference['collision_sets']
        record['historical_final_pair_set_size']=len(sets.get('final_collision_pairs',[]))
        record['final_pair_sets_equal']=set(map(tuple,sets.get('final_collision_pairs',[])))==measured_pairs
        record['historical_unresolved_set_size']=len(sets.get('final_unresolved_pairs',[]))
        record['unresolved_pair_sets_equal']=set(map(tuple,sets.get('final_unresolved_pairs',[])))==measured_unknown
    record['matches_history']=(record['historical_final_pairs']==record['measured_final_pairs'] and
        record['historical_successful_elevations']==record['measured_accepted_first_elevations'])
    return record


def main():
    log(f'start size={SIZE} strategies={STRATEGIES} out={OUT}')
    config=three_layer_config()
    inputs=load_inputs();planar=inputs['planar'];crossings=inputs['crossings']
    initial_routes={i:deepcopy(r) for i,r in planar.items()}
    save('config.json',dict(scale=SIZE,dataset=inputs['dataset'],input_files=inputs['inputs'],
        input_sha256=inputs['fingerprints'],configuration=config_record(config),
        budget_unit='one evaluate_elevation basic call per candidate row',
        budget_counts_basic_rejections=True,frozen_budget=asdict(frozen_budget(SIZE)),
        strategies=STRATEGIES,module='src/strategy_v2_3d.py',
        notes=['A reruns the legacy 9-F decisions inside the shared budget engine',
               'B adds filtered targets, conflict-concentrated priority and both-victim evaluation',
               'C adds relocation of already-elevated routes with dependency-versioned failure cache',
               'candidate budget frozen from saved historical candidate rows before B/C inspection',
               'budget insufficient to fully accept a candidate -> that candidate is not submitted']))
    save('code_version.json',code_version())
    history=historical_reference()
    if history is not None:
        save('historical_reference.json',dict(summary_path=history['summary_path'],
            summary_sha256=history['summary_sha256'],collision_sets_path=history.get('collision_sets_path'),
            collision_sets_sha256=history.get('collision_sets_sha256')))
    summary=dict(scale=SIZE,dataset=inputs['dataset'],configuration=config_record(config),
        budget=asdict(frozen_budget(SIZE)),strategies=STRATEGIES,
        input_sha256=inputs['fingerprints'],
        initial_total_length_mm=sum(r.total_length() for r in initial_routes.values()),
        runs={},historical_reference={'summary_path':history['summary_path'],
        'summary_sha256':history['summary_sha256']} if history else None,historical_A=None)
    rows=[]
    for strategy in STRATEGIES:
        log(f'strategy {strategy}: start')
        started=perf_counter()
        def progress(row,strategy=strategy):
            if row.get('phase')=='TARGET_DONE':
                log(f'  {strategy} step {row["step"]} {row["status"]} collisions={row["collisions"]} '
                    f'evaluations={row["candidate_evaluations"]} {row["seconds"]:.0f}s')
            elif row.get('phase')=='INITIAL_DONE':
                log(f'  {strategy} {row["phase"]} collisions={row["collisions"]} uncertain={row["uncertain"]}')
        result=run_strategy_v2(initial_routes,planar,config,strategy=strategy,scale=SIZE,
            progress=progress,saved_crossings=crossings)
        ledger=dict(result['ledger'])
        log(f'strategy {strategy}: done {perf_counter()-started:.0f}s '
            f'final={ledger["final_collision_pair_count"]} accepted={ledger["accepted_moves"]} '
            f'evaluations={ledger["candidate_evaluations"]} stop={ledger["stop_reason"]}')
        save(f'decisions_{strategy}.json',result['steps'])
        save(f'curve_{strategy}.json',result['curve'])
        save(f'final_routes_{strategy}.json',dict(route_count=SIZE,
            routes=[dict(route_id=i,main_layer=route_layer(r),geometry=serialize_route3d(r))
                for i,r in sorted(result['routes'].items())]))
        save(f'collision_sets_{strategy}.json',dict(
            initial_collision_pairs=result['initial_collision_pairs'],
            final_collision_pairs=result['final_collision_pairs'],
            initial_unresolved_pairs=result['initial_unresolved_pairs'],
            final_unresolved_pairs=result['final_unresolved_pairs'],
            elevated_route_ids=result['elevated_route_ids'],
            relocated_route_ids=result['relocated_route_ids']))
        save(f'ledger_{strategy}.json',ledger)
        # Reload from the saved file and re-run the complete pair re-check.
        stored=json.loads((OUT/f'final_routes_{strategy}.json').read_text())
        reloaded={row['route_id']:deserialize_route3d(row['geometry']) for row in stored['routes']}
        assert len(reloaded)==SIZE
        assert reloaded==result['routes']
        geometry=route_geometry_audit(planar,reloaded)
        recheck=full_recheck(reloaded)
        pairs_match=recheck['pairs']==set(map(tuple,result['final_collision_pairs']))
        unknown_match=recheck['unknown']==set(map(tuple,result['final_unresolved_pairs']))
        final_length=fsum(r.total_length() for r in reloaded.values())
        ledger_consistent=abs(final_length-ledger['final_total_length_mm'])<1e-6
        transition_count=sum(isinstance(p,CosineTransition3D) for r in reloaded.values() for p in r.primitives)
        assert pairs_match and unknown_match and geometry['endpoint_invariant'] and \
            geometry['joins_C0_C1_direction'] and geometry['transition_radius_pass'] and \
            geometry['xy_projection_preserved'] and ledger_consistent, \
            ('RECHECK_FAILED',strategy,pairs_match,unknown_match,geometry)
        assert transition_count==ledger['final_transition_count']
        record=dict(collision_pair_set_matches_incremental=pairs_match,
            unresolved_pair_set_matches_incremental=unknown_match,
            geometry=geometry,recheck_seconds=recheck['seconds'],checks=recheck['checks'],
            final_length_matches_ledger=ledger_consistent,
            reloaded_route_count=SIZE,serialized_geometry_equal=True,
            final_transition_count=transition_count,
            ledger_final_transition_count=ledger['final_transition_count'])
        save(f'recheck_{strategy}.json',record)
        log(f'strategy {strategy}: recheck PASS pairs_match={pairs_match} unknown_match={unknown_match}')
        summary['runs'][strategy]=dict(ledger=ledger,recheck=record)
        if strategy=='A':
            summary['historical_A']=compare_with_history(result,history)
            log('historical A comparison: '+json.dumps(summary['historical_A']))
        rows.append(dict(strategy=strategy,initial_collision_pairs=ledger['initial_collision_pair_count'],
            final_collision_pairs=ledger['final_collision_pair_count'],
            reduction_percent=round(ledger['reduction_percent'],4),
            old_collisions_removed=ledger['total_old_collisions_removed'],
            new_collisions_created=ledger['total_new_collisions_created'],
            unresolved_final=ledger['final_unresolved_pair_count'],
            accepted_moves=ledger['accepted_moves'],first_elevations=ledger['first_elevations'],
            relocations=ledger['relocations'],elevated_route_count=ledger['elevated_route_count'],
            target_attempts=ledger['target_attempts'],
            final_extra_length_mm=round(ledger['final_extra_length_mm'],6),
            total_step_length_delta_mm=round(ledger['total_step_length_delta_mm'],6),
            final_transition_count=ledger['final_transition_count'],
            candidate_evaluations=ledger['candidate_evaluations'],
            generated_candidates=ledger['generated_candidates'],
            full_neighbor_checks=ledger['full_neighbor_checks'],
            candidate_budget=ledger['candidate_budget'],
            stop_reason=ledger['stop_reason'],
            assignment_seconds=round(ledger['assignment_seconds'],3),
            runtime_seconds=round(ledger['runtime_seconds'],3)))
    with (OUT/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0].keys()));writer.writeheader()
        for row in rows:writer.writerow(row)
    summary['comparison']=rows
    save('summary.json',summary)
    log('ALL DONE '+json.dumps(rows))


if __name__=='__main__':
    try:
        main()
    except Exception:
        log('FAILED\n'+traceback.format_exc())
        raise
