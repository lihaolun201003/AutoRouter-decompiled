"""Step 9-A: regression plus read-only saved geometry lifting; no allocator."""
import sys,json,importlib.util,traceback
from pathlib import Path
from copy import deepcopy
from math import cos,sin,hypot,atan2,fsum,pi
from hashlib import sha256

ROOT=Path(sys.argv[1]).resolve(); SOURCE=Path(sys.argv[2]).resolve();OUT=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(ROOT));OUT.mkdir(parents=True,exist_ok=True)
from src.models import Layer,Point3D,LineSegment2D,ArcSegment2D
from src.multi_attribution import deserialize_plot
from src.geometry import smoothed_route_length,arc_segment_radius
from src.geometry_3d import lift_smoothed_route_to_layer,CosineTransition3D,LineSegment3D,PlanarArcSegment3D

results=[]
for p in sorted((ROOT/'tests').glob('test_*.py')):
    spec=importlib.util.spec_from_file_location(p.stem,p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for name,fn in vars(module).items():
        if name.startswith('test_') and callable(fn):
            try:fn();results.append(dict(file=p.name,test=name,status='PASS'))
            except Exception:results.append(dict(file=p.name,test=name,status='FAIL',error=traceback.format_exc()))
test=dict(passed=sum(r['status']=='PASS' for r in results),failed=sum(r['status']=='FAIL' for r in results),
    historical_count=sum(r['file']!='test_geometry_3d.py' for r in results),new_count=sum(r['file']=='test_geometry_3d.py' for r in results),tests=results)
(OUT/'step_9_a_tests.json').write_text(json.dumps(test,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in test.items() if k!='tests'}),flush=True)
for r in results:
    if r['status']=='FAIL':print(r,flush=True)
if test['failed']:raise SystemExit(1)
path=SOURCE/'outputs/step_8_5_legacy_512_plot_geometry.json';before=sha256(path.read_bytes()).hexdigest()
records=json.loads(path.read_text())['routes']
# Fixed sample choice by saved ID/category, unrelated to multi counts or recovery.
ordinary=sorted((r for r in records if not r['special']),key=lambda r:r['id'])[:3]
special=sorted((r for r in records if r['special']),key=lambda r:r['id'])[:3]
samples=[]
for record in ordinary+special:
    r=deserialize_plot(record);frozen=deepcopy(r)
    # One explicit test coordinate, not a layer pitch or routing assignment.
    l=Layer(id=901,z=2.75);lifted=lift_smoothed_route_to_layer(r,l)
    maxerr=0.
    for a,b in zip(r.segments,lifted.primitives):
        assert (a.start.x,a.start.y)==(b.start.x,b.start.y)
        assert (a.end.x,a.end.y)==(b.end.x,b.end.y)
        assert isinstance(b,LineSegment3D if isinstance(a,LineSegment2D) else PlanarArcSegment3D)
        for t in (0,.125,.25,.5,.75,.875,1):
            if isinstance(a,LineSegment2D):x,y=(1-t)*a.start.x+t*a.end.x,(1-t)*a.start.y+t*a.end.y
            else:
                theta=atan2(a.start.y-a.center.y,a.start.x-a.center.x)+t*a.sweep_rad
                radius=arc_segment_radius(a);x,y=a.center.x+radius*cos(theta),a.center.y+radius*sin(theta)
                assert b.radius==radius and b.sweep_angle==a.sweep_rad
            point=b.point_at(t);maxerr=max(maxerr,hypot(point.x-x,point.y-y));assert point.z==2.75
    assert maxerr<1e-9 and lifted.total_length()==smoothed_route_length(r) and r==frozen
    samples.append(dict(route_id=record['id'],special=record['special'],primitive_count=len(r.segments),
        line_count=sum(isinstance(p,LineSegment3D) for p in lifted.primitives),
        arc_count=sum(isinstance(p,PlanarArcSegment3D) for p in lifted.primitives),
        xy_max_error_mm=maxerr,length_2d_mm=smoothed_route_length(r),length_3d_mm=lifted.total_length(),
        endpoint_xy_exact=True,read_only=True,test_layer_z_mm=2.75))
c=CosineTransition3D(Point3D(0,0,0),Point3D(10,0,1));n=32768
reference=fsum(hypot(10,pi/2*sin(pi*(i+.5)/n)) for i in range(n))/n
assert sha256(path.read_bytes()).hexdigest()==before
data=dict(status='PASS',samples=samples,saved_geometry_sha256=before,saved_geometry_unchanged=True,
    fixture=dict(start=[0,0,0],end=[10,0,1],midpoint=vars(c.point_at(.5)),
    effective_radius_indicator_mm=c.effective_radius_indicator(),length_mm=c.length(),chord_mm=hypot(10,1),
    independent_midpoint_quadrature_mm=reference,quadrature_difference_mm=abs(reference-c.length()),
    endpoint_tangents=[c.tangent_at(0),c.tangent_at(1)]))
(OUT/'step_9_a_geometry_validation.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(data),flush=True)
