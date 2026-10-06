"""Fixed 1024 dataset -> analytic 2D -> existing three-layer assignment -> full audit."""
import sys,json,csv,importlib.util,traceback
from pathlib import Path
from collections import Counter
from dataclasses import asdict,is_dataclass
from itertools import combinations
from hashlib import sha256
from time import perf_counter
ROOT=Path(sys.argv[1]).resolve();OUT=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(ROOT));OUT.mkdir(parents=True,exist_ok=True)
from src.fixed_1024_routing import (legacy_waveguides_from_seed,generate_fixed_1024_input,build_fixed_1024_geometry,
    fixed_three_layer_config,run_fixed_1024_assignment,serialize_route3d,deserialize_route3d)
from src.sequential_elevation_3d import RouteView,pair_status
from src.geometry_3d import CosineTransition3D
from src.geometry_3d_diagnostics import analyze_route3d_joins

def encode(x):
    if is_dataclass(x):return asdict(x)
    raise TypeError(type(x).__name__)
def save(name,data): (OUT/name).write_text(json.dumps(data,default=encode,indent=2,allow_nan=False),encoding='utf-8')
tests=[];test_started=perf_counter()
for path in sorted((ROOT/'tests').glob('test_*.py')):
    spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    for name,fn in vars(m).items():
        if name.startswith('test_') and callable(fn):
            try:fn();tests.append(dict(file=path.name,test=name,status='PASS'))
            except Exception:tests.append(dict(file=path.name,test=name,status='FAIL',error=traceback.format_exc()))
test_summary=dict(passed=sum(t['status']=='PASS' for t in tests),failed=sum(t['status']=='FAIL' for t in tests),
    historical_count=sum(t['file']!='test_fixed_1024_routing.py' for t in tests),new_count=sum(t['file']=='test_fixed_1024_routing.py' for t in tests),seconds=perf_counter()-test_started,tests=tests)
save('step_10_tests.json',test_summary);print(json.dumps({k:v for k,v in test_summary.items() if k!='tests'}),flush=True)
if test_summary['failed']:print([t for t in tests if t['status']=='FAIL']);raise SystemExit(1)
if '--tests-only' in sys.argv[3:]:raise SystemExit(0)
started=perf_counter();seedpath=ROOT/'data/fixed_1024_legacy_seed.json';seed=json.loads(seedpath.read_text());seed_hash=sha256(seedpath.read_bytes()).hexdigest()
data=generate_fixed_1024_input(legacy_waveguides_from_seed(seed));data['source_provenance']=seed['source_hashes'];data['seed_sha256']=seed_hash
save('step_10_fixed_1024_input.json',data)
planar,routes,stats=build_fixed_1024_geometry(data);geometry_seconds=perf_counter()-started
initial_length=sum(r.total_length() for r in routes.values())
save('step_10_fixed_1024_initial_geometry.json',dict(routes=[serialize_route3d(r) for _,r in sorted(routes.items())]))
stats.update(initial_total_length_mm=initial_length,dataset_and_geometry_seconds=geometry_seconds,configuration=fixed_three_layer_config())
save('step_10_fixed_1024_initial_stats.json',stats);print('GEOMETRY',json.dumps(stats,default=encode),flush=True)
def progress(row):
    if 'steps' in row:
        step=row.pop('steps')[-1]
        compact={k:v for k,v in step.items() if k not in ('victim_attempts','elevation_geometry')}
        with (OUT/'step_10_progress_steps.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(compact)+'\n')
    save('step_10_progress.json',row)
    if row['phase']=='INITIAL_DONE' or row['phase']=='INITIAL_COLLISIONS' and row['checked']%50000==0 or row['phase']=='TARGET_DONE' and (row['status']=='ELEVATED' or row['step']%50==0):
        print(json.dumps(row),flush=True)
(OUT/'step_10_progress_steps.jsonl').write_text('',encoding='utf-8')
result=run_fixed_1024_assignment(routes,planar,progress=progress)
save('step_10_fixed_1024_attempts.json',result['steps'])
steps=result['steps'];success=[s for s in steps if s['status']=='ELEVATED'];by_id={s['moved_route_id']:s for s in success}
records=[]
for row in data['routes']:
    i=row['route_id'];r=result['routes'][i];s=by_id.get(i);layer=s['target_layer_id'] if s else 0
    records.append(dict(route_id=i,source=row['source'],destination=row['destination'],target_layer=layer,
        state=f'SINGLE_ELEVATION_0_{layer}_0' if layer else 'LAYER_0',geometry=serialize_route3d(r),
        total_length_mm=r.total_length(),extra_length_mm=s['extra_length_mm'] if s else 0.,
        transition_info=[dict(primitive_index=j,run_mm=p.lxy,delta_z_mm=p.delta_z,minimum_radius_mm=p.minimum_curvature_radius()) for j,p in enumerate(r.primitives) if isinstance(p,CosineTransition3D)]))
save('step_10_fixed_1024_final_route_state.json',dict(configuration=fixed_three_layer_config(),board=data['board'],route_count=1024,routes=records))
fields=['step_index','target_pair','status','moved_route_id','target_layer_id','route_collision_count_before','route_collision_count_after','old_collisions_removed','new_collisions_created','net_collision_reduction','global_collision_pairs_before','global_collision_pairs_after','extra_length_mm','elevated_length_mm','transition_count']
with (OUT/'step_10_fixed_1024_steps.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for s in steps:w.writerow({k:json.dumps(s[k]) if isinstance(s.get(k),(tuple,list)) else s.get(k,'') for k in fields})
print('ASSIGNMENT_DONE',result['target_attempts'],result['successful_elevations'],result['final_collision_pair_count'],flush=True)
validation_started=perf_counter()
stored=json.loads((OUT/'step_10_fixed_1024_final_route_state.json').read_text())
reloaded={row['route_id']:deserialize_route3d(row['geometry']) for row in stored['routes']}
assert reloaded==result['routes'] and len(reloaded)==1024
for i,r in reloaded.items():
    r.validate();assert r.start_point==routes[i].start_point and r.end_point==routes[i].end_point
    joins=analyze_route3d_joins(r);assert joins.all_C0 and joins.all_C1_direction
    assert all(p.minimum_curvature_radius()>=5 for p in r.primitives if isinstance(p,CosineTransition3D))
views={i:RouteView.prepare(r) for i,r in reloaded.items()};final=set();unknown=set();checks=0
for a,b in combinations(sorted(reloaded),2):
    status=pair_status(views[a],views[b],.1);checks+=1
    if status=='COLLISION':final.add((a,b))
    elif status!='CLEAR':unknown.add((a,b))
    if checks%100000==0:print('FINAL_VALIDATION',checks,'seconds',perf_counter()-validation_started,flush=True)
assert checks==523776 and final==set(result['final_collision_pairs']) and unknown==set(result['final_unresolved_pairs'])
validation_seconds=perf_counter()-validation_started
save('step_10_fixed_1024_collision_sets.json',dict(initial_collision_pairs=result['initial_collision_pairs'],final_collision_pairs=sorted(final),
    initial_unresolved_pairs=result['initial_unresolved_pairs'],final_unresolved_pairs=sorted(unknown)))
save('step_10_fixed_1024_validation.json',dict(status='PASS',reloaded_route_count=1024,serialized_geometry_equal=True,
    endpoint_invariant=True,all_C0_C1_direction=True,transition_radius_pass=True,full_pair_count=checks,
    full_rebuild_equals_local_update=True,collision_pair_count=len(final),unresolved_pair_count=len(unknown),seconds=validation_seconds))
stats.update(initial_collision_pairs=result['initial_collision_pair_count'],initial_unresolved_pairs=len(result['initial_unresolved_pairs']),initial_pair_scan_seconds=result['initial_pair_scan_seconds'])
save('step_10_fixed_1024_initial_stats.json',stats)
reduction=result['initial_collision_pair_count']-len(final);layer_counts=Counter(row['target_layer'] for row in records)
summary=dict(status='PASS' if reduction>0 and len(records)==1024 else 'NEEDS_REVISION',route_count=1024,pmt_count=128,endpoint_count=2048,board=data['board'],
    configuration=fixed_three_layer_config(),geometry_stats=stats,layer_route_counts={str(k):layer_counts[k] for k in (0,1,2)},
    initial_collision_pairs=result['initial_collision_pair_count'],final_collision_pairs=len(final),net_collision_reduction=reduction,
    reduction_percent=100*reduction/result['initial_collision_pair_count'],successful_elevations=len(success),target_attempts=len(steps),stop_reason=result['stop_reason'],
    both_already_elevated=result['both_already_elevated'],no_improving=result['failed_no_candidate'],second_victim_successes=result['second_victim_successes'],
    old_collisions_removed=sum(len(s['old_collisions_removed']) for s in success),new_collisions_created=sum(len(s['new_collisions_created']) for s in success),
    initial_total_route_length_mm=initial_length,total_route_length_mm=sum(row['total_length_mm'] for row in records),
    total_extra_length_mm=result['total_extra_length_mm'],average_extra_length_per_elevation_mm=result['total_extra_length_mm']/len(success) if success else 0,
    average_extra_length_per_route_mm=result['total_extra_length_mm']/1024,max_extra_length_mm=max((s['extra_length_mm'] for s in success),default=0),transition_count=2*len(success),
    runtime=dict(dataset_geometry_seconds=geometry_seconds,initial_pair_scan_seconds=result['initial_pair_scan_seconds'],assignment_seconds=result['assignment_seconds'],
        final_validation_seconds=validation_seconds,total_seconds=perf_counter()-started),
    final_all_pair_validation_matches=True,baseline_unchanged=True,allocator_modified=False,source_seed_sha256=seed_hash,
    initial_unresolved_pair_count=len(result['initial_unresolved_pairs']),final_unresolved_pair_count=len(unknown),
    candidate_basic_rejections=dict(Counter(reason for s in steps for v in s['victim_attempts'] for r in v['candidates'] for reason in r['basic_reasons'])))
assert sha256(seedpath.read_bytes()).hexdigest()==seed_hash
save('step_10_fixed_1024_summary.json',summary)
print('FINAL_SUMMARY',json.dumps(summary,default=encode),flush=True)
