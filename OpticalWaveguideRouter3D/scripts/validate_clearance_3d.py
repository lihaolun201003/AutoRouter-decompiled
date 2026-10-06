"""9-C bounded synthetic and saved-pair audit, never routes or assigns layers."""
import sys,json,importlib.util,traceback
from pathlib import Path
from dataclasses import asdict
from copy import deepcopy
from itertools import combinations
from hashlib import sha256
from time import perf_counter

ROOT=Path(sys.argv[1]).resolve();SOURCE=Path(sys.argv[2]).resolve();OUT=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(ROOT));OUT.mkdir(parents=True,exist_ok=True)
from src.models import Layer,Point3D
from src.geometry_3d import Route3D,lift_smoothed_route_to_layer,CosineTransition3D,PlanarArcSegment3D
from src.clearance_3d import analyze_primitive_clearance,analyze_route3d_clearance,analyze_route3d_self_clearance
from src.multi_attribution import deserialize_plot
from src.collision import find_smoothed_route_intersections_2d

started=perf_counter();tests=[];fixtures=None
for path in sorted((ROOT/'tests').glob('test_*.py')):
    spec=importlib.util.spec_from_file_location(path.stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if path.stem=='test_clearance_3d':fixtures=module
    for name,fn in vars(module).items():
        if name.startswith('test_') and callable(fn):
            try:fn();tests.append(dict(file=path.name,test=name,status='PASS'))
            except Exception:tests.append(dict(file=path.name,test=name,status='FAIL',error=traceback.format_exc()))
summary=dict(passed=sum(t['status']=='PASS' for t in tests),failed=sum(t['status']=='FAIL' for t in tests),
    historical_count=sum(t['file']!='test_clearance_3d.py' for t in tests),
    new_count=sum(t['file']=='test_clearance_3d.py' for t in tests),seconds=perf_counter()-started,tests=tests)
(OUT/'step_9_c_tests.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='tests'}),flush=True)
if summary['failed']:
    print([t for t in tests if t['status']=='FAIL']);raise SystemExit(1)
line=fixtures.line;trans=fixtures.trans;rows=[]
cases=[('layer_clear',*fixtures.fixture(),.5,{}),('layer_collision',*fixtures.fixture(),1.5,{}),
       ('layer_threshold',*fixtures.fixture(),1.,{}),('same_layer_cross',*fixtures.fixture(0),.1,{}),
       ('near_layer',line((0,0,0),(10,0,0)),line((0,.08,.05),(10,.08,.05)),.1,{}),
       ('transition_interior_cross',trans(),line((5,-2,.5),(5,2,.5)),.1,{}),
       ('transition_interior_nonzero',trans(),line((5,-2,.65),(5,2,.65)),.1,{'distance_tol':1e-7}),
       ('not_converged',trans(),line((5,-2,.65),(5,2,.65)),.1,{'max_subdivisions':0}),
       ('transition_arc',trans(),PlanarArcSegment3D(5,1,.5,1,-3.141592653589793/2,3.141592653589793/2),.1,{}),
       ('transition_transition',trans(),CosineTransition3D(Point3D(5,-5,0),Point3D(5,5,1)),.1,{})]
for name,a,b,c,kwargs in cases:
    frozen=deepcopy((a,b));start=perf_counter();r=analyze_primitive_clearance(a,b,c,**kwargs)
    assert (a,b)==frozen
    rows.append(dict(name=name,seconds=perf_counter()-start,**r))
    print(name,r['status'],r['minimum_distance_mm'],r.get('subdivision_count'),flush=True)
reference_d,reference_t=fixtures.independent_transition_line_reference()
r=next(r for r in rows if r['name']=='transition_interior_nonzero')
assert r['lower_bound_mm']<=reference_d<=r['upper_bound_mm']

plotpath=SOURCE/'outputs/step_8_5_legacy_512_plot_geometry.json'
eventpath=SOURCE/'outputs/step_8_5_legacy_512_physical_events.jsonl'
hashes={str(p):sha256(p.read_bytes()).hexdigest() for p in (plotpath,eventpath)}
plot=json.loads(plotpath.read_text())
routes={r['id']:deserialize_plot(r) for r in plot['routes']}
savedpairs=set()
for text in eventpath.read_text().splitlines():
    e=json.loads(text)
    if e['kind']=='cross':savedpairs.add(tuple(sorted((e['route_a_id'],e['route_b_id']))))
selected=[('saved_cross',p) for p in sorted(savedpairs)[:3]]
for pair in combinations(sorted(routes),2):
    if pair not in savedpairs and not find_smoothed_route_intersections_2d(routes[pair[0]],routes[pair[1]]):
        selected.append(('saved_non_cross',pair))
        if sum(label=='saved_non_cross' for label,_ in selected)==3:break
lifted=[]
for label,(a,b) in selected:
    ra,rb=routes[a],routes[b];before=deepcopy((ra,rb))
    raw=find_smoothed_route_intersections_2d(ra,rb)
    # Test plane only, not a layer assignment or a layer pitch decision.
    la=lift_smoothed_route_to_layer(ra,Layer(901,2.75));lb=lift_smoothed_route_to_layer(rb,Layer(901,2.75))
    report=analyze_route3d_clearance(la,lb,.01)
    spatial=report['intersection_status']=='INTERSECTING'
    assert spatial==bool(raw) and (ra,rb)==before
    if label=='saved_cross':assert report['minimum_distance_mm']==0 and report['status']=='COLLISION'
    else:assert report['minimum_distance_mm']>0
    lifted.append(dict(label=label,route_ids=[a,b],raw_2d_intersection_kinds=sorted({e.kind for e in raw}),
        intersection_consistent=True,minimum_distance_mm=report['minimum_distance_mm'],status=report['status'],
        primitive_pair_count=len(report['pair_results']),read_only=True))
assert all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
simple=Route3D(1,[line((-2,0,0),(0,0,0)),trans(),line((10,0,1),(12,0,1))])
crossing=Route3D(2,[line((0,0,0),(2,0,0)),line((2,0,0),(2,2,0)),line((2,2,0),(1,-1,0))])
self_results=[analyze_route3d_self_clearance(r,.1) for r in (simple,crossing)]
result=dict(status='PASS',clearance_source='EXPLICIT_SYNTHETIC_INPUT_NOT_MANUFACTURING_STANDARD',
    synthetic_cases=rows,independent_transition_reference=dict(distance_mm=reference_d,parameter=reference_t),
    lifted_saved_pairs=lifted,self_results=self_results,input_hashes=hashes,source_unchanged=True)
(OUT/'step_9_c_clearance_validation.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(dict(lifted=lifted,independent_reference=result['independent_transition_reference'],self_statuses=[r['status'] for r in self_results])),flush=True)
