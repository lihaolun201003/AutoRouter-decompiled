
# helper: check a route where a logical rise is split into two consecutive
# transition PRIMITIVES sharing one cosine phase (physical fragments > 2)
import sys
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
from math import sin, pi
from src.geometry_3d import *
from src.overnight_engine_3d import elevation_structure, transition_fragment_counts
L=lambda a,b: LineSegment3D(Point3D(*a),Point3D(*b))
# rise split at the half-height parameter: two path windows over consecutive
# halves of one line, phases sqrt(0.5)/... of the same cosine
up1=PathWindowTransition3D((L((0,0,0),(5,0,0)),),0.,0.5)
up2=PathWindowTransition3D((L((5,0,0),(10,0,0)),),0.5,1.0)
mid=L((10,0,1),(12,0,1))
down1=PathWindowTransition3D((L((12,0,0),(17,0,0)),),1.0,0.5)
down2=PathWindowTransition3D((L((17,0,0),(22,0,0)),),0.5,0.0)
route=Route3D(0,[L((-3,0,0),(0,0,0)),up1,up2,mid,down1,down2,L((22,0,0),(25,0,0))])
print('fragmented logical route:',elevation_structure(route))
print('ramps/fragments:',transition_fragment_counts(route))
# a plateau inside a rise must be rejected
pl=Route3D(0,[up1,L((5,0,0),(6,0,0)),up2,mid,down1,down2])
print('plateau in rise:',elevation_structure(pl))