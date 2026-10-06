
import sys
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
from math import pi
from src.geometry_3d import *
import src.clearance_3d as C
from src.path_window_3d import build_path_window_candidate
from src.three_layer_assignment_3d import LayerConfiguration
from src.models import Layer
config=LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],0.1,5.0,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
L=lambda a,b: LineSegment3D(Point3D(*a),Point3D(*b))
arc_a=PlanarArcSegment3D(10.,5.,0.,5.,-pi/2,pi)
arc_b=PlanarArcSegment3D(10.,15.,0.,5.,-pi/2,-pi/2)
route=Route3D(11,(L((0,0,0),(10,0,0)),arc_a,arc_b,L((5,15,0),(5,35,0))))
cand=build_path_window_candidate(route,(11,12),[Point3D(5.,25.,0.)],config,(10.2,25.5),(45.,52.))
print('prims',[type(p).__name__ for p in cand.route.primitives])
res=C.analyze_route3d_self_clearance(cand.route,0.1)
import json
row=res['adjacent_results'][2]
print(json.dumps(row,indent=1)[:2500])
a=cand.route.primitives[2]; b=cand.route.primitives[3]
print('a run',a.planar_run_mm,'b run',b.length() if not hasattr(b,'planar_run_mm') else b.planar_run_mm)
print('joint',a.end,b.start)