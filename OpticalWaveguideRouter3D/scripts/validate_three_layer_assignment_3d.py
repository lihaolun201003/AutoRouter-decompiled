"""Same baseline and engine: two-layer control vs three-layer, 50 targets each."""
import sys,json,csv,importlib.util,traceback
from pathlib import Path
from dataclasses import asdict,is_dataclass
from collections import Counter
from hashlib import sha256
from time import perf_counter
ROOT=Path(sys.argv[1]).resolve();SOURCE=Path(sys.argv[2]).resolve();OUT=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(ROOT));OUT.mkdir(parents=True,exist_ok=True)
from src.models import Layer,Point3D
from src.geometry_3d import lift_smoothed_route_to_layer
from src.geometry_3d_diagnostics import minimum_xy_run_for_radius
from src.three_layer_assignment_3d import LayerConfiguration,run_layer_assignment_probe
from src.multi_attribution import deserialize_plot

def encode(x):
    if is_dataclass(x):return asdict(x)
    raise TypeError(type(x).__name__)
def save(name,x):(OUT/name).write_text(json.dumps(x,default=encode,indent=2,allow_nan=False),encoding='utf-8')
started=perf_counter();tests=[]
for path in sorted((ROOT/'tests').glob('test_*.py')):
    spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    for name,fn in vars(m).items():
        if name.startswith('test_') and callable(fn):
            try:fn();tests.append(dict(file=path.name,test=name,status='PASS'))
            except Exception:tests.append(dict(file=path.name,test=name,status='FAIL',error=traceback.format_exc()))
test_summary=dict(passed=sum(t['status']=='PASS' for t in tests),failed=sum(t['status']=='FAIL' for t in tests),
    historical_count=sum(t['file']!='test_three_layer_assignment_3d.py' for t in tests),new_count=sum(t['file']=='test_three_layer_assignment_3d.py' for t in tests),seconds=perf_counter()-started,tests=tests)
save('step_9_f_tests.json',test_summary);print(json.dumps({k:v for k,v in test_summary.items() if k!='tests'}),flush=True)
if test_summary['failed']:print([t for t in tests if t['status']=='FAIL']);raise SystemExit(1)
if '--tests-only' in sys.argv[4:]:raise SystemExit(0)
plotpath=SOURCE/'outputs/step_8_5_legacy_512_plot_geometry.json';eventpath=SOURCE/'outputs/step_8_5_legacy_512_physical_events.jsonl'
hashes={str(p):sha256(p.read_bytes()).hexdigest() for p in (plotpath,eventpath)}
routes={r['id']:lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0)) for r in json.loads(plotpath.read_text())['routes']}
assert len(routes)==512
crossings={}
for text in eventpath.read_text().splitlines():
    e=json.loads(text)
    if e['kind']=='cross':crossings.setdefault(tuple(sorted((e['route_a_id'],e['route_b_id']))),[]).append(Point3D(e['point']['x'],e['point']['y'],0))
summaries={};usage={};initial_sets=[]
for label,n in (('two_layer',2),('three_layer',3)):
    config=LayerConfiguration([Layer(i,float(i)) for i in range(n)],.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
    def progress(row):
        if 'steps' in row:save(f'step_9_f_{label}_attempts.json',row.pop('steps'))
        save('step_9_f_progress.json',dict(experiment=label,**row))
        if row['phase'] in ('INITIAL_DONE','TARGET_DONE'):print(label,json.dumps(row),flush=True)
    result=run_layer_assignment_probe(routes,config,max_targets=50,saved_crossings=crossings,progress=progress)
    assert result['target_attempts']==50
    initial_sets.append(result['initial_collision_pairs'])
    steps=result['steps'];success=[s for s in steps if s['status']=='ELEVATED']
    layer_ids={s['moved_route_id']:s['target_layer_id'] for s in success}
    usage[label]={str(layer):sorted(i for i in routes if layer_ids.get(i,0)==layer) for layer in range(n)}
    save(f'step_9_f_{label}_attempts.json',steps)
    save(f'step_9_f_{label}_collision_sets.json',{k:result[k] for k in ('initial_collision_pairs','final_collision_pairs','initial_unresolved_pairs','final_unresolved_pairs')})
    save(f'step_9_f_{label}_final_route_state.json',dict(configuration=config,elevated_route_ids=result['elevated_route_ids'],
        routes=[dict(route_id=i,layer_state=f'SINGLE_ELEVATION_0_{layer_ids[i]}_0' if i in layer_ids else 'LAYER_0',geometry=r) for i,r in sorted(result['routes'].items())]))
    fields=['step_index','target_pair','status','moved_route_id','target_layer_id','route_collision_count_before','route_collision_count_after','new_collisions_created','old_collisions_removed','net_collision_reduction','global_collision_pairs_before','global_collision_pairs_after','extra_length_mm','elevated_length_mm']
    with (OUT/f'step_9_f_{label}_steps.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for s in steps:w.writerow({k:json.dumps(s[k]) if isinstance(s.get(k),(list,tuple)) else s.get(k,'') for k in fields})
    unique=[];dominant=[];families=[]
    for s in success:
        va=next(v for v in s['victim_attempts'] if v['status']=='SELECTED')
        rows=va['candidates'];improving={layer:[r for r in rows if r.get('target_layer_id')==layer and r.get('status')=='IMPROVING'] for layer in range(1,n)}
        info=dict(target=s['target_pair'],moved=s['moved_route_id'],selected_layer=s['target_layer_id'],
            generated_by_layer={str(l):sum(r['target_layer_id']==l for r in rows) for l in range(1,n)},
            improving_by_layer={str(l):len(v) for l,v in improving.items()},
            best_after_by_layer={str(l):min((r['after_collision_count'] for r in v),default=None) for l,v in improving.items()})
        families.append(info)
        if s['target_layer_id']==2:
            if not improving[1]:unique.append(s['target_pair'])
            if improving[1] and s['route_collision_count_after']<min(r['after_collision_count'] for r in improving[1]):dominant.append(s['target_pair'])
    summary={k:v for k,v in result.items() if k not in ('routes','steps','initial_collision_pairs','final_collision_pairs','initial_unresolved_pairs','final_unresolved_pairs')}
    reduction=result['initial_collision_pair_count']-result['final_collision_pair_count']
    summary.update(configuration=config,input_hashes=hashes,layer_usage_counts={k:len(v) for k,v in usage[label].items()},
        total_collision_reduction=reduction,reduction_percent=100*reduction/result['initial_collision_pair_count'],
        total_new_collisions_created=sum(len(s['new_collisions_created']) for s in success),
        total_old_collisions_removed=sum(len(s['old_collisions_removed']) for s in success),
        average_single_reduction=reduction/len(success) if success else 0,maximum_single_reduction=max((s['net_collision_reduction'] for s in success),default=0),
        layer_two_unique_success_targets=unique,layer_two_unique_success_count=len(unique),
        layer_two_better_after_targets=dominant,layer_family_comparisons=families,
        length_by_layer={str(l):dict(count=sum(s['target_layer_id']==l for s in success),
            extra_length_mm=sum(s['extra_length_mm'] for s in success if s['target_layer_id']==l),
            minimum_xy_run_mm=minimum_xy_run_for_radius(float(l),5)) for l in range(1,n)},
        candidate_basic_rejections=dict(Counter(reason for s in steps for v in s['victim_attempts'] for r in v['candidates'] for reason in r['basic_reasons'])),
        initial_unresolved_pair_count=len(result['initial_unresolved_pairs']),final_unresolved_pair_count=len(result['final_unresolved_pairs']))
    summaries[label]=summary
    save('step_9_f_two_layer_control_summary.json' if n==2 else 'step_9_f_three_layer_summary.json',summary)
    print(label,json.dumps({k:summary[k] for k in ('successful_elevations','final_collision_pair_count','layer_usage_counts','both_already_elevated','total_extra_length_mm','runtime_seconds','layer_two_unique_success_count')}),flush=True)
assert initial_sets[0]==initial_sets[1]
assert all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
save('step_9_f_layer_usage.json',usage)
comparison=dict(status='PASS',same_initial_collision_set=True,target_budget_each=50,baseline_unchanged=True,
    extra_collision_reduction_from_third_layer=summaries['two_layer']['final_collision_pair_count']-summaries['three_layer']['final_collision_pair_count'],
    layer_two_unique_success_definition='Selected victim/current state: Layer 2 improving exists and Layer 1 improving absent',
    experiments=summaries)
save('step_9_f_comparison.json',comparison)
