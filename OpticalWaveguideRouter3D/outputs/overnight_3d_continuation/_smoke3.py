
import sys, traceback
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
from math import pi
from src.geometry_3d import *
from src.path_window_3d import planar_path_model, split_path_interval
L1=LineSegment3D(Point3D(0,0,0),Point3D(20,0,0))
arc=PlanarArcSegment3D(20.,5.,0.,5.,-pi/2,pi/2)
L2=LineSegment3D(Point3D(25,5,0),Point3D(45,5,0))
route=Route3D(7,(L1,arc,L2))
m=planar_path_model(route)
print('offsets',m['offsets'],'lengths',m['lengths'],'total',m['total'])
cuts={0.,m['total'],12.,20.,34.,44.};cuts.update(m['offsets']);o=sorted(cuts)
print('cuts',o)
for x,y in zip(o,o[1:]):
    print((x,y),'->',split_path_interval(m,x,y))
