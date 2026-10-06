
import sys, json
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D'); sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\\scripts')
from pathlib import Path
from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer
from src.multi_attribution import deserialize_plot
from src.three_layer_assignment_3d import LayerConfiguration
from src.path_window_3d import planar_path_model, path_offsets_of_point, minimum_xy_run_for_radius
import overnight_registry as R
root=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
plot=json.loads((root/'outputs/step_8_5_legacy_512_plot_geometry.json').read_text(encoding='utf-8'))
planar={r['id']: lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0)) for r in plot['routes']}
cfg=LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],R.CLEARANCE_MM,R.REQUIRED_RADIUS_MM,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
# reproduce the enumeration for a few routes and report why pairs are invalid
bad=0; examples=[]
for rid in sorted(planar)[:40]:
    route=planar[rid]; model=planar_path_model(route)
    # pick an anchor at 60% of the planar length
    s=model['total']*0.6
    for prim,off,length in zip(model['primitives'],model['offsets'],model['lengths']):
        if s<=off+length:
            anchor=prim.point_at(min(1.,max(0.,(s-off)/length))); break
    offs=path_offsets_of_point(model,anchor)
    if not offs: continue
    first,last=min(offs),max(offs); pad=cfg.clearance_mm+1e-5
    L0=minimum_xy_run_for_radius(1.0,5.0)
    legal=dict(rise=(0.,first-pad),fall=(last+pad,model['total']))
    win=dict(rise=[],fall=[])
    for label,(lo,hi) in legal.items():
        if hi<=lo: continue
        for factor in (1.0,1.5,2.0,3.0):
            L=L0*factor
            if L>hi-lo: continue
            free=(hi-lo)-L
            for frac in (0.0,0.5,1.0):
                st=lo+frac*free
                key=(round(st,9),round(st+L,9))
                if key not in win[label]: win[label].append(key)
    for rise in win['rise']:
        for fall in win['fall']:
            if not (0.<=rise[0]<rise[1]<=fall[0]<fall[1]<=model['total']):
                bad+=1
                if len(examples)<5:
                    examples.append((rid,first,last,model['total'],legal['rise'],legal['fall'],rise,fall))
print('bad pairs',bad)
for e in examples: print(e)
