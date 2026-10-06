
import sys
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
from math import pi, sqrt
from src.geometry_3d import *
import src.clearance_3d as C
from src.path_window_3d import build_path_window_candidate, planar_path_model, path_window_candidates, minimum_path_run_for_curvature
from src.three_layer_assignment_3d import LayerConfiguration
from src.models import Layer

config=LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],0.1,5.0,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
# synthetic planar route: line 20mm, then a 5mm-radius quarter arc, then a line
arc=PlanarArcSegment3D(20.,5.,0.,5.,-pi/2,pi/2)   # from (20,0) to (25,5)
print('arc start/end',arc.start,arc.end)
L1=LineSegment3D(Point3D(0,0,0),Point3D(20,0,0))
L2=LineSegment3D(Point3D(25,5,0),Point3D(45,5,0))
route=Route3D(7,(L1,arc,L2))
model=planar_path_model(route)
print('total planar',model['total'])
cand=build_path_window_candidate(route,(7,8),[Point3D(30,5,0)],config,(12.0,20.0),(34.0,44.0))
print('candidate kind',cand.window_kind,'run',cand.transition_run_mm,'Rmin',cand.minimum_radius_mm)
print('spans',cand.rise_span,cand.fall_span)
print('extra length',cand.extra_length_mm,'elevated',cand.elevated_length_mm)
print('start/end preserved',cand.route.start_point==route.start_point, cand.route.end_point==route.end_point)
print('prims',[type(p).__name__ for p in cand.route.primitives])
from src.strategy_v2_3d import xy_projection_preserved
print('xy preserved',xy_projection_preserved(cand.route,route))
from src.sequential_elevation_3d import RouteView,pair_status
print('self status',C.analyze_route3d_self_clearance(cand.route,0.1)['status'])
from src.geometry_3d_diagnostics import analyze_route3d_joins
j=analyze_route3d_joins(cand.route); print('joins',j.all_C0,j.all_C1_direction)
print('cand min radius vs required',cand.minimum_radius_mm>=5.0)