
import json,sys
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D'); sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/scripts')
from copy import deepcopy
from pathlib import Path
from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, PathWindowTransition3D
from src.multi_attribution import deserialize_plot
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families
import overnight_registry as R
root=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
plot=json.loads((root/'outputs/step_8_5_legacy_512_plot_geometry.json').read_text(encoding='utf-8'))
planar={r['id']: lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0)) for r in plot['routes']}
cfg=LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],R.CLEARANCE_MM,R.REQUIRED_RADIUS_MM,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
# use a real step from the G1 run
steps=json.loads((root/'outputs/overnight_3d_continuation/v8/V8_G1_N2880/decisions.json').read_text(encoding='utf-8'))
target=None; moved=None; points=None
for s in steps:
    for va in s['victim_attempts']:
        bad=[e for e in va.get('candidates',[]) if e.get('window_kind')=='PATH_WINDOW_G1' and e.get('basic_status')=='REJECTED' and 'ENDPOINT_CHANGED' in (e.get('basic_reasons') or [])]
        if bad:
            target=tuple(s['target_pair']); moved=va['route_id']; points=None
            # anchors: recompute from the target crossing set
            break
    if target: break
print('target',target,'moved',moved)
# saved crossings for that target
crossings={}
for text in (root/'outputs/step_8_5_legacy_512_physical_events.jsonl').read_text().splitlines():
    e=json.loads(text)
    if e['kind']=='cross':
        crossings.setdefault(tuple(sorted((e['route_a_id'],e['route_b_id']))),[]).append(Point3D(e['point']['x'],e['point']['y'],0))
pts=crossings.get(target,[])
print('anchor points',len(pts))
cands,fail=candidate_families(planar[moved],target,pts,cfg,window_slack_mm=R.WINDOW_SLACK_MM,generation_domain='PATH_WINDOWS')
print('candidates',len(cands),'failures',fail)
plan=planar[moved]
bad=0
for c in cands:
    if c.route.start_point!=plan.start_point or c.route.end_point!=plan.end_point:
        bad+=1
        if bad<=3:
            print('kind',getattr(c,'window_kind',None),'rise',c.rise_window,'fall',c.fall_window)
            print('  start route',c.route.start_point,'planar',plan.start_point)
            print('  end   route',c.route.end_point,'planar',plan.end_point)
            print('  first prim',type(c.route.primitives[0]).__name__, c.route.primitives[0].start)
            print('  last  prim',type(c.route.primitives[-1]).__name__, c.route.primitives[-1].end)
            print('  offsets',c.rise_offsets_mm,c.fall_offsets_mm)
print('candidates with changed endpoints:',bad,'of',len(cands))
