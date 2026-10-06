
import json,sys
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D'); sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/scripts')
from pathlib import Path
from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer
from src.multi_attribution import deserialize_plot
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families
import overnight_registry as R
root=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
plot=json.loads((root/'outputs/step_8_5_legacy_512_plot_geometry.json').read_text(encoding='utf-8'))
planar={r['id']: lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0)) for r in plot['routes']}
cfg=LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],R.CLEARANCE_MM,R.REQUIRED_RADIUS_MM,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
crossings={}
for text in (root/'outputs/step_8_5_legacy_512_physical_events.jsonl').read_text().splitlines():
    e=json.loads(text)
    if e['kind']=='cross':
        crossings.setdefault(tuple(sorted((e['route_a_id'],e['route_b_id']))),[]).append(Point3D(e['point']['x'],e['point']['y'],0))
total=0; bad=0
for target,pts in list(crossings.items())[:60]:
    for moved in target:
        try:
            cands,_=candidate_families(planar[moved],target,pts,cfg,window_slack_mm=R.WINDOW_SLACK_MM,generation_domain='PATH_WINDOWS')
        except ValueError:
            continue
        for c in cands:
            total+=1
            if c.route.start_point!=planar[moved].start_point or c.route.end_point!=planar[moved].end_point:
                bad+=1
print('path-window candidates checked:',total,'with changed endpoints:',bad)
