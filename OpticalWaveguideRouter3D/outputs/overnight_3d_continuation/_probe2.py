
import json,sys
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D'); sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/scripts')
from pathlib import Path
from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, PathWindowTransition3D, PlanarArcSegment3D, LineSegment3D
from src.multi_attribution import deserialize_plot
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families
from src.path_window_3d import planar_path_model, split_path_interval
import overnight_registry as R
root=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
plot=json.loads((root/'outputs/step_8_5_legacy_512_plot_geometry.json').read_text(encoding='utf-8'))
planar={r['id']: lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0)) for r in plot['routes']}
plan=planar[105]
print('planar primitives:')
for i,p in enumerate(plan.primitives):
    extra=''
    if type(p) is PlanarArcSegment3D:
        extra=' src_start=%s src_end=%s'%(p._source_start_xy,p._source_end_xy)
    print(' ',i,type(p).__name__,p.start,'->',p.end,extra)
m=planar_path_model(plan)
print('total',m['total'],'offsets',m['offsets'],'lengths',m['lengths'])
rise=(0.0,7.450941199347076); fall=(256.90702206860186,264.35796326794895)
for label,span in (('rise',rise),('fall',fall)):
    print(label,'span',span)
    for k,u,v in split_path_interval(m,span[0],span[1]):
        print('   piece prim',k,type(m['primitives'][k]).__name__,'u',u,'v',v)
