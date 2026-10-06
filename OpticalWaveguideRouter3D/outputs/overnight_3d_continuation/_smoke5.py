
import sys
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
from src.geometry_3d import *
from src.overnight_engine_3d import elevation_structure
L=lambda a,b: LineSegment3D(Point3D(*a),Point3D(*b))
one_rise=Route3D(0,[L((-20,0,0),(0,0,0)),CosineTransition3D(Point3D(0,0,0),Point3D(5,0,1))])
print('one_rise',elevation_structure(one_rise))
two=Route3D(0,[L((-20,0,0),(0,0,0)),CosineTransition3D(Point3D(0,0,0),Point3D(5,0,1)),L((5,0,1),(10,0,1)),CosineTransition3D(Point3D(10,0,1),Point3D(15,0,0))])
print('normal',elevation_structure(two))
planar=Route3D(0,[L((0,0,0),(10,0,0))])
print('planar',elevation_structure(planar))
three=Route3D(0,[L((-20,0,0),(0,0,0)),CosineTransition3D(Point3D(0,0,0),Point3D(5,0,1)),CosineTransition3D(Point3D(5,0,1),Point3D(10,0,2))])
print('two rises',elevation_structure(three))
