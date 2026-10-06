"""Small topology-audit tests, with no real-data dependency."""
from copy import deepcopy
from math import pi,isclose
from unittest import TestCase
from src.models import Point2D,LineSegment2D,ArcSegment2D,SmoothedRoute2D,Route
from src.collision import find_route_intersections
from src.geometry import smooth_orthogonal_route_2d
from src.physical_intersections import find_physical_route_intersections_2d
from src.double_cross_audit import *
raises=TestCase().assertRaises

def event(a,b):
 return dict(route_a_id=a,route_b_id=b,kind="cross",point=dict(x=0,y=0))
def test_double_exactly_two():
 assert len(split_cross_pairs([event(1,2)]*2)["double"])==1
def test_double_single_excluded():
 assert split_cross_pairs([event(1,2)])["double"]=={}
def test_double_higher_explicit():
 r=split_cross_pairs([event(1,2)]*3)
 assert not r["double"] and len(r["higher"])==1
def test_double_route_types():
 assert route_pair_type("topU","bottomU")=="U-U"
 assert route_pair_type("topU","top_to_bottomZ")=="U-Z"
 assert route_pair_type("specialZ","bottom_to_topZ")=="Z-Z"
def test_double_geometry_composition():
 assert [geometry_composition(*x) for x in ((False,False),(False,True),(True,True))]==[
  "ordinary-ordinary","ordinary-special","special-special"]
def test_double_segment_topology():
 assert segment_topology({"LineSegment2D"},{"ArcSegment2D"})=="Arc-Line"
 assert segment_topology({"ArcSegment2D"},{"ArcSegment2D"})=="Arc-Arc"
def test_double_line_progress():
 r=SmoothedRoute2D(1,[LineSegment2D(Point2D(0,0),Point2D(10,0))])
 assert normalized_progress(r,Point2D(2,0),0)==.2
def test_double_arc_progress():
 r=SmoothedRoute2D(1,[ArcSegment2D(Point2D(1,0),Point2D(-1,0),Point2D(0,0),pi)])
 assert isclose(normalized_progress(r,Point2D(0,1),0),.5)
def test_double_reversal_distance_and_progress():
 a=SmoothedRoute2D(1,[LineSegment2D(Point2D(0,0),Point2D(10,0))])
 b=SmoothedRoute2D(1,[LineSegment2D(Point2D(10,0),Point2D(0,0))])
 p,q=Point2D(2,0),Point2D(7,0)
 assert distance(p,q)==distance(q,p)==5
 assert isclose(normalized_progress(a,p,0)+normalized_progress(b,p,0),1)
def test_double_skeleton_actual_comparison():
 a=Route(1,[Point2D(0,10),Point2D(0,5),Point2D(10,5),Point2D(10,10)])
 b=Route(2,[Point2D(2,10),Point2D(2,3),Point2D(8,3),Point2D(8,10)])
 raw=find_route_intersections(a,b)
 smooth=find_physical_route_intersections_2d(smooth_orthogonal_route_2d(a,.5),smooth_orthogonal_route_2d(b,.5))
 assert len(smooth)==2 and all(e.kind=="cross" for e in smooth)
 assert skeleton_comparison(sum(e.kind=="cross" for e in raw))=="skeleton_2_to_smooth_2"
def test_double_skeleton_categories():
 assert [skeleton_comparison(n) for n in (0,1,2,3)]==[
  "skeleton_0_to_smooth_2","skeleton_1_to_smooth_2","skeleton_2_to_smooth_2","other"]
 assert skeleton_comparison(2,1)=="other"
def test_double_track_difference():
 assert track_difference(4,7)==3
 with raises(ValueError):track_difference(4,4)
def test_double_category_ranges():
 r=category_range_overlap({"a":dict(min_index=0,max_index=5),"b":dict(min_index=6,max_index=10),"c":dict(min_index=4,max_index=8)})
 assert not r["a"]["b"] and r["a"]["c"]
def test_double_canonical_order():
 assert (1,2) in split_cross_pairs([event(2,1),event(1,2)])["double"]
def test_double_no_mutation():
 e=[event(2,1),event(1,2)];before=deepcopy(e)
 split_cross_pairs(e)
 assert e==before
