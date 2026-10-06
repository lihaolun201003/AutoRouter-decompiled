"""Run preserved tests and bounded saved-data single-route experiments."""
import sys,json,importlib.util,traceback
from pathlib import Path
from dataclasses import asdict,is_dataclass
from collections import Counter
from hashlib import sha256
from time import perf_counter
ROOT=Path(sys.argv[1]).resolve();SOURCE=Path(sys.argv[2]).resolve();OUT=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(ROOT));OUT.mkdir(parents=True,exist_ok=True)
from src.models import Layer,Point3D
from src.geometry_3d import lift_smoothed_route_to_layer
from src.layer_assignment_3d import probe_single_route_elevation
from src.multi_attribution import deserialize_plot
from src.collision import find_smoothed_route_intersections_2d
from src.clearance_3d import analyze_route3d_clearance

def encode(x):
    if is_dataclass(x):return asdict(x)
    raise TypeError(type(x).__name__)
def save(name,x): (OUT/name).write_text(json.dumps(x,default=encode,indent=2,allow_nan=False),encoding='utf-8')
started=perf_counter();tests=[]
for path in sorted((ROOT/'tests').glob('test_*.py')):
    spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    if path.stem=='test_layer_assignment_3d':fixtures=m
    for name,fn in vars(m).items():
        if name.startswith('test_') and callable(fn):
            try:fn();tests.append(dict(file=path.name,test=name,status='PASS'))
            except Exception:tests.append(dict(file=path.name,test=name,status='FAIL',error=traceback.format_exc()))
summary=dict(passed=sum(t['status']=='PASS' for t in tests),failed=sum(t['status']=='FAIL' for t in tests),
    historical_count=sum(t['file']!='test_layer_assignment_3d.py' for t in tests),
    new_count=sum(t['file']=='test_layer_assignment_3d.py' for t in tests),seconds=perf_counter()-started,tests=tests)
save('step_9_d_tests.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='tests'}),flush=True)
if summary['failed']:print([t for t in tests if t['status']=='FAIL']);raise SystemExit(1)
if '--tests-only' in sys.argv[4:]:raise SystemExit(0)
c=fixtures.config();a,b,cross=fixtures.fixture()
synthetic=probe_single_route_elevation(b,a,cross,c)
assert synthetic['status']=='ACCEPTED_TARGET_PAIR_ONLY'
save('step_9_d_synthetic.json',synthetic)
plotpath=SOURCE/'outputs/step_8_5_legacy_512_plot_geometry.json'
eventpath=SOURCE/'outputs/step_8_5_legacy_512_physical_events.jsonl'
hashes={str(p):sha256(p.read_bytes()).hexdigest() for p in (plotpath,eventpath)}
routes={r['id']:deserialize_plot(r) for r in json.loads(plotpath.read_text())['routes']}
events=[json.loads(s) for s in eventpath.read_text().splitlines()]
rows=[]
for target in (24,25,26):
    saved=[e for e in events if e['kind']=='cross' and {e['route_a_id'],e['route_b_id']}=={0,target}]
    raw=find_smoothed_route_intersections_2d(routes[0],routes[target])
    assert saved and any(e.kind=='cross' for e in raw)
    points=[Point3D(e['point']['x'],e['point']['y'],0) for e in saved]
    attempts=[]
    for moved,other in ((0,target),(target,0)):
        r=probe_single_route_elevation(lift_smoothed_route_to_layer(routes[moved],Layer(0,0)),
            lift_smoothed_route_to_layer(routes[other],Layer(0,0)),points,c)
        attempts.append(dict(moved_route_id=moved,**r))
        print('pair',target,'moved',moved,r['status'],'candidates',r['candidate_count'],'accepted',r['accepted_count'],flush=True)
    accepted=[r for r in attempts if r['selected']]
    selected=min(accepted,key=lambda r:(r['selected']['rank'],r['moved_route_id'])) if accepted else None
    row=dict(target_pair=[0,target],saved_cross_events=saved,raw_cross_confirmed=True,attempts=attempts,
        success=bool(selected),selected_moved_route_id=selected['moved_route_id'] if selected else None,
        selected=selected['selected'] if selected else None)
    rows.append(row);save('step_9_d_real_pairs.json',rows)
local=[]
for row in rows:
    if not row['selected']:continue
    moved=row['selected_moved_route_id']; elevated=row['selected']['candidate'].route
    original=lift_smoothed_route_to_layer(routes[moved],Layer(0,0)); pairs=[]
    for neighbor in sorted(routes):
        if neighbor==moved:continue
        other=lift_smoothed_route_to_layer(routes[neighbor],Layer(0,0))
        before=analyze_route3d_clearance(original,other,c.clearance_mm)
        after=analyze_route3d_clearance(elevated,other,c.clearance_mm)
        pairs.append(dict(neighbor_id=neighbor,before_status=before['status'],after_status=after['status'],
            before_minimum_mm=before['minimum_distance_mm'],after_minimum_mm=after['minimum_distance_mm']))
    old={p['neighbor_id'] for p in pairs if p['before_status']=='COLLISION'}
    new={p['neighbor_id'] for p in pairs if p['after_status']=='COLLISION'}
    uncertain=[p['neighbor_id'] for p in pairs if p['after_status'] not in ('CLEAR','COLLISION')]
    r=dict(target_pair=row['target_pair'],moved_route_id=moved,checked_neighbor_count=len(pairs),
        old_collision_count=len(old),new_collision_count=len(new),new_collisions_created=sorted(new-old),
        old_collisions_removed=sorted(old-new),uncertain_after=uncertain,
        nonincreasing_collision_count=len(new)<=len(old),strictly_reduced=len(new)<len(old),
        local_acceptance=row['selected']['evaluation']['target_collision_removed'] and len(new)<=len(old) and not uncertain,
        pair_results=pairs)
    local.append(r);save('step_9_d_local_validation.json',local)
    print('LOCAL',json.dumps({k:v for k,v in r.items() if k!='pair_results'}),flush=True)
assert all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
save('step_9_d_probe_summary.json',dict(status='PASS',configuration=c,synthetic_success=True,
    real_pair_count=3,real_success_count=sum(r['success'] for r in rows),input_hashes=hashes,baseline_unchanged=True,
    local_validation_status='SELECTED_CANDIDATES_511_NEIGHBORS',
    local_accepted_count=sum(r['local_acceptance'] for r in local),
    local_new_collisions_created=[r['new_collisions_created'] for r in local],
    local_old_collisions_removed=[r['old_collisions_removed'] for r in local],
    total_seconds=perf_counter()-started))
