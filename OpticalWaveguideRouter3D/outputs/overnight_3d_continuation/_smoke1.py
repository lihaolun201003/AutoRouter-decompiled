
import sys
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
from src.geometry_3d import LineSegment3D,Point3D,PathWindowTransition3D,PlanarArcSegment3D,Route3D
import src.clearance_3d as C
L=LineSegment3D(Point3D(0,0,0),Point3D(10,0,0))
w=PathWindowTransition3D((L,),0.,1.)
print('box',C._box(w,0.,1.))
print('pe',C._parameter_xy(w,5.,0.,1e-9))
print('chord',C._chord_error(w,0.,1.))
print('mono',C._monotone_axis(w,0),C._monotone_axis(w,1))
r=Route3D(0,(L,w,))
print('self',C.analyze_route3d_self_clearance(r,0.1)['status'])
print('adj',C.analyze_route3d_self_clearance(r,0.1)['adjacent_results'])
print('clear_rr',C.analyze_route3d_clearance(r,r)['status'])
# arc window across a line->arc boundary
arc=PlanarArcSegment3D(10.,0.,0.,5.,3.141592653589793, -1.5707963267948966)
print('arc endpoints',arc.start,arc.end)
w2=PathWindowTransition3D((L,arc),0.,1.)
print('w2 run',w2.planar_run_mm,'kmax',w2.max_curvature(),'R',w2.minimum_curvature_radius())
print('cert pieces',w2.curvature_certificate()['piece_planar_curvatures'])
