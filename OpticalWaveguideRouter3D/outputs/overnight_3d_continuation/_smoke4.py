
import sys
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
from math import pi
from src.geometry_3d import *
from src.path_window_3d import build_path_window_candidate
from src.three_layer_assignment_3d import LayerConfiguration
from src.models import Layer
from src.geometry_3d_diagnostics import validate_tangent_join_3d
config=LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],0.1,5.0,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
L1=LineSegment3D(Point3D(0,0,0),Point3D(20,0,0))
arc=PlanarArcSegment3D(20.,5.,0.,5.,-pi/2,pi/2)
L2=LineSegment3D(Point3D(25,5,0),Point3D(45,5,0))
route=Route3D(7,(L1,arc,L2))
cand=build_path_window_candidate(route,(7,8),[Point3D(30,5,0)],config,(12.0,20.0),(34.0,44.0))
ps=cand.route.primitives
for i in range(len(ps)-1):
    j=validate_tangent_join_3d(ps[i],ps[i+1])
    print(i,j.status,j.angle_rad,j.detail)
    if j.status!='C0_C1_PASS':
        print('  a',type(ps[i]).__name__,ps[i].end,ps[i].tangent_at(1))
        print('  b',type(ps[i+1]).__name__,ps[i+1].start,ps[i+1].tangent_at(0))
