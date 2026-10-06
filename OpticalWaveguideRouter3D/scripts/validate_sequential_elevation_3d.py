"""Small sequential elevation run; reads saved 512 geometry, never reallocates."""
import sys,json,csv,importlib.util,traceback
from pathlib import Path
from dataclasses import asdict,is_dataclass
from hashlib import sha256
from time import perf_counter
from collections import Counter
ROOT=Path(sys.argv[1]).resolve();SOURCE=Path(sys.argv[2]).resolve();OUT=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(ROOT));OUT.mkdir(parents=True,exist_ok=True)
from src.models import Layer,Point3D
from src.geometry_3d import lift_smoothed_route_to_layer
from src.layer_assignment_3d import LayerConfiguration
from src.multi_attribution import deserialize_plot
from src.sequential_elevation_3d import run_sequential_elevation,RouteView,pair_status
from src.clearance_3d import analyze_route3d_clearance

def encode(x):
    if is_dataclass(x):return asdict(x)
    raise TypeError(type(x).__name__)
def save(name,x): (OUT/name).write_text(json.dumps(x,default=encode,indent=2,allow_nan=False),encoding='utf-8')
started=perf_counter();tests=[]
for path in sorted((ROOT/'tests').glob('test_*.py')):
    spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    for name,fn in vars(m).items():
        if name.startswith('test_') and callable(fn):
            try:fn();tests.append(dict(file=path.name,test=name,status='PASS'))
            except Exception:tests.append(dict(file=path.name,test=name,status='FAIL',error=traceback.format_exc()))
summary=dict(passed=sum(t['status']=='PASS' for t in tests),failed=sum(t['status']=='FAIL' for t in tests),
    historical_count=sum(t['file']!='test_sequential_elevation_3d.py' for t in tests),
    new_count=sum(t['file']=='test_sequential_elevation_3d.py' for t in tests),seconds=perf_counter()-started,tests=tests)
save('step_9_e_tests.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='tests'}),flush=True)
if summary['failed']:print([t for t in tests if t['status']=='FAIL']);raise SystemExit(1)
if '--tests-only' in sys.argv[4:]:raise SystemExit(0)
plotpath=SOURCE/'outputs/step_8_5_legacy_512_plot_geometry.json'
eventpath=SOURCE/'outputs/step_8_5_legacy_512_physical_events.jsonl'
hashes={str(p):sha256(p.read_bytes()).hexdigest() for p in (plotpath,eventpath)}
original={r['id']:deserialize_plot(r) for r in json.loads(plotpath.read_text())['routes']}
routes={i:lift_smoothed_route_to_layer(r,Layer(0,0)) for i,r in original.items()}
assert len(routes)==512
crossings={}
for text in eventpath.read_text().splitlines():
    e=json.loads(text)
    if e['kind']=='cross':
        pair=tuple(sorted((e['route_a_id'],e['route_b_id'])))
        crossings.setdefault(pair,[]).append(Point3D(e['point']['x'],e['point']['y'],0))
config=LayerConfiguration([Layer(0,0),Layer(1,1)],.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
def progress(row):
    if 'steps' in row:save('step_9_e_target_attempts.json',row.pop('steps'))
    save('step_9_e_progress.json',row)
    if row['phase']!='CANDIDATE':print(json.dumps(row),flush=True)
result=run_sequential_elevation(routes,config,max_targets=30,saved_crossings=crossings,progress=progress)
save('step_9_e_target_attempts.json',result['steps'])
save('step_9_e_collision_history.json',result['collision_history'])
save('step_9_e_collision_sets.json',{k:result[k] for k in ('initial_collision_pairs','final_collision_pairs','initial_unresolved_pairs','final_unresolved_pairs')})
save('step_9_e_final_route_state.json',dict(parameter_status='EXPERIMENTAL_SYNTHETIC',configuration=config,
    elevated_route_ids=result['elevated_route_ids'],routes=[dict(route_id=i,layer_state='SINGLE_ELEVATION_0_1_0' if i in result['elevated_route_ids'] else 'LAYER_0',geometry=r) for i,r in sorted(result['routes'].items())]))
fields=['step_index','target_pair','status','moved_route_id','victim_collision_degree_before','route_collision_count_before','route_collision_count_after','old_collisions_removed','new_collisions_created','net_collision_reduction','global_collision_pairs_before','global_collision_pairs_after','extra_length_mm','transition_count','elevated_length_mm']
with (OUT/'step_9_e_sequential_elevation_steps.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for step in result['steps']:w.writerow({k:json.dumps(step[k]) if isinstance(step.get(k),(list,tuple)) else step.get(k,'') for k in fields})
success=[s for s in result['steps'] if s['status']=='ELEVATED']
report={k:v for k,v in result.items() if k not in ('routes','steps','initial_collision_pairs','final_collision_pairs','initial_unresolved_pairs','final_unresolved_pairs')}
reduction=result['initial_collision_pair_count']-result['final_collision_pair_count']
report.update(status='PASS' if len(success)>1 and all(s['net_collision_reduction']>0 for s in success) else 'NEEDS_REVISION',
    configuration=config,input_hashes=hashes,total_collision_reduction=reduction,reduction_percent=100*reduction/result['initial_collision_pair_count'],
    maximum_single_reduction=max((s['net_collision_reduction'] for s in success),default=0),
    average_single_reduction=reduction/len(success) if success else 0,
    total_new_collisions_created=sum(len(s['new_collisions_created']) for s in success),
    first_victim_failed_second_succeeded=sum(s['second_victim_success'] and s['victim_attempts'][0]['status']=='NO_IMPROVING_CANDIDATE' for s in success),
    first_victim_already_elevated_second_succeeded=sum(s['second_victim_success'] and s['victim_attempts'][0]['status']=='ROUTE_ALREADY_ELEVATED' for s in success),
    candidate_rejection_counts=dict(Counter(reason for s in result['steps'] for v in s['victim_attempts'] for row in v['candidates'] for reason in row['basic_reasons'])),
    all_current_neighbor_checks=sum('checked_neighbor_count' in row for s in result['steps'] for v in s['victim_attempts'] for row in v['candidates']),
    initial_unresolved_pair_count=len(result['initial_unresolved_pairs']),final_unresolved_pair_count=len(result['final_unresolved_pairs']))
assert all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
save('step_9_e_sequential_elevation_summary.json',report)
print(json.dumps({k:v for k,v in report.items() if k not in ('configuration','input_hashes','collision_history')},default=encode),flush=True)
