"""9-B regression and point-only numeric curvature / read-only join evidence."""
import sys,json,importlib.util,traceback,ast
from pathlib import Path
from copy import deepcopy
from dataclasses import asdict
from math import pi,isinf

ROOT=Path(sys.argv[1]).resolve();OUT=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(ROOT));OUT.mkdir(parents=True,exist_ok=True)
from src.models import Point3D
from src.geometry_3d import CosineTransition3D,LineSegment3D,Route3D
from src.geometry_3d_diagnostics import analyze_route3d_joins,validate_tangent_join_3d,minimum_xy_run_for_radius

tests=[];curvature_tests=None
for path in sorted((ROOT/'tests').glob('test_*.py')):
    spec=importlib.util.spec_from_file_location(path.stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if path.stem=='test_geometry_3d_curvature':curvature_tests=module
    for name,fn in vars(module).items():
        if name.startswith('test_') and callable(fn):
            try:fn();tests.append(dict(file=path.name,test=name,status='PASS'))
            except Exception:tests.append(dict(file=path.name,test=name,status='FAIL',error=traceback.format_exc()))
summary=dict(passed=sum(t['status']=='PASS' for t in tests),failed=sum(t['status']=='FAIL' for t in tests),
    historical_count=sum(t['file']!='test_geometry_3d_curvature.py' for t in tests),
    new_count=sum(t['file']=='test_geometry_3d_curvature.py' for t in tests),tests=tests)
(OUT/'step_9_b_tests.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='tests'}),flush=True)
if summary['failed']:
    print([t for t in tests if t['status']=='FAIL']);raise SystemExit(1)
c=curvature_tests.curve();before=deepcopy(c)
rows=[]
for t in (0,.1,.25,.5,.75,.9,1):
    numeric=curvature_tests.numeric_curvature(c,t)
    numeric_half=curvature_tests.numeric_curvature(c,t,h=.0005)
    analytic=c.curvature_at(t);radius=c.radius_of_curvature_at(t)
    rows.append(dict(t=t,s_mm=c.lxy*t,analytic_curvature_per_mm=analytic,numeric_curvature_per_mm=numeric,
        numeric_half_step_curvature_per_mm=numeric_half,absolute_error_per_mm=abs(analytic-numeric),
        radius_of_curvature_mm='Infinity' if isinf(radius) else radius))
cases=[]
for label,a in [('line_aligned',curvature_tests.incoming((-2,0,0))),
    ('line_perpendicular',curvature_tests.incoming((0,-2,0))),
    ('line_reversed',curvature_tests.incoming((2,0,0))),
    ('arc_aligned',curvature_tests.good_arc()),('arc_mismatched',curvature_tests.bad_arc())]:
    route=Route3D(10,[a,c]);frozen=deepcopy(route);analysis=analyze_route3d_joins(route)
    assert route==frozen
    cases.append(dict(label=label,**asdict(analysis)))
assert c==before
result=dict(status='PASS',derivation='PROJECT-SPECIFIC TRUE CURVATURE OF CURRENT COSINE MODEL',
    fixture=dict(start=[0,0,0],end=[10,0,1],max_curvature_per_mm=c.max_curvature(),
        minimum_curvature_radius_mm=c.minimum_curvature_radius(),effective_radius_indicator_mm=c.effective_radius_indicator(),
        indicator_to_true_radius_ratio=c.effective_radius_indicator()/c.minimum_curvature_radius(),
        explicit_required_radius_mm=200/pi**2,inverse_minimum_xy_run_mm=minimum_xy_run_for_radius(1,200/pi**2)),
    numeric_method='Point-only 5-point finite differences; h=0.001 and 0.0005; one-sided at endpoints',
    numeric_tolerance_per_mm=2e-7,numeric_rows=rows,max_numeric_error_per_mm=max(r['absolute_error_per_mm'] for r in rows),
    joins=cases,input_read_only=True)
(OUT/'step_9_b_curvature_join_validation.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(result,allow_nan=False),flush=True)
