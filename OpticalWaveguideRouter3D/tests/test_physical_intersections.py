"""Physical point and local topology tests, independent of real datasets."""
from copy import deepcopy
from math import pi,cos,sin,isclose
from unittest import TestCase
from src.models import Point2D,LineSegment2D,ArcSegment2D,SmoothedRoute2D
from src.collision import find_smoothed_route_intersections_2d
from src.geometry import build_special_z_smoothed_route_2d
from src.physical_intersections import (
    find_physical_route_intersections_2d as physical,
    consolidate_route_intersections_2d as consolidate,
)
raises=TestCase().assertRaises

def line(a,b):
    return LineSegment2D(Point2D(*a),Point2D(*b))

def route(i,*segments):
    return SmoothedRoute2D(i,list(segments))

def reverse(r):
    return route(r.waveguide_id,*[
        LineSegment2D(s.end,s.start) if isinstance(s,LineSegment2D) else
        ArcSegment2D(s.end,s.start,s.center,-s.sweep_rad)
        for s in reversed(r.segments)])

def special_pair():
    a=build_special_z_smoothed_route_2d(1,Point2D(-2,-10),Point2D(2,10),5)
    b=build_special_z_smoothed_route_2d(2,Point2D(2,-10),Point2D(-2,10),5)
    return a,b

def test_physical_straight_cross():
    e=physical(route(1,line((-2,0),(2,0))),route(2,line((0,-2),(0,2))))
    assert len(e)==1 and e[0].kind=="cross" and e[0].point==Point2D(0,0)
    assert isclose(e[0].crossing_angle_rad,pi/2)

def test_physical_endpoint_touch():
    e=physical(route(1,line((-2,0),(0,0))),route(2,line((0,0),(0,2))))
    assert len(e)==1 and e[0].kind=="touch"

def test_physical_line_arc_join():
    a=route(1,line((-2,0),(0,0)),ArcSegment2D(Point2D(0,0),Point2D(1,1),Point2D(0,1),pi/2))
    b=route(2,line((0,-2),(0,2)))
    raw=find_smoothed_route_intersections_2d(a,b)
    assert len(raw)==2
    e=consolidate(a,b,raw)
    assert len(e)==1 and e[0].kind=="cross" and e[0].raw_event_count==2

def test_physical_arc_arc_join_single_cross():
    a,_=special_pair()
    b=route(2,line((-4,0),(4,0)))
    e=physical(a,b)
    assert len(e)==1 and e[0].kind=="cross" and e[0].raw_event_count==2

def test_physical_both_joins_four_touches():
    a,b=special_pair()
    raw=find_smoothed_route_intersections_2d(a,b)
    assert len(raw)==4 and all(e.kind=="touch" for e in raw)
    e=consolidate(a,b,raw)
    assert len(e)==1 and e[0].kind=="cross" and e[0].raw_event_count==4

def test_physical_true_tangent():
    a=route(1,ArcSegment2D(Point2D(2,0),Point2D(-2,0),Point2D(0,0),pi))
    b=route(2,line((-3,2),(3,2)))
    e=physical(a,b)
    assert len(e)==1 and e[0].kind=="touch"
    assert e[0].crossing_angle_rad<1e-9

def test_physical_reverse_angle_invariant():
    a,b=special_pair()
    before=physical(a,b)[0]
    for ra,rb in ((reverse(a),b),(a,reverse(b)),(reverse(a),reverse(b))):
        after=physical(ra,rb)[0]
        assert after.kind==before.kind
        assert isclose(after.crossing_angle_rad,before.crossing_angle_rad,abs_tol=1e-9)

def test_physical_acute_angle():
    theta=140*pi/180
    e=physical(route(1,line((-2,0),(2,0))),
               route(2,line((-cos(theta),-sin(theta)),(cos(theta),sin(theta)))))[0]
    assert isclose(e.crossing_angle_rad,40*pi/180,abs_tol=1e-12)

def test_physical_no_mutation():
    a,b=special_pair()
    raw=find_smoothed_route_intersections_2d(a,b)
    before=deepcopy((a,b,raw))
    consolidate(a,b,raw)
    assert (a,b,raw)==before

def test_physical_pair_swap():
    a,b=special_pair()
    assert physical(a,b)==physical(b,a)

def test_physical_distinct_pairs_same_coordinate():
    a=route(1,line((-2,0),(2,0)))
    b=route(2,line((0,-2),(0,2)))
    c=route(3,line((-2,-2),(2,2)))
    assert physical(a,b)[0].point==physical(a,c)[0].point
    assert physical(a,b)[0].route_b_id!=physical(a,c)[0].route_b_id
    with raises(ValueError):
        consolidate(a,b,find_smoothed_route_intersections_2d(a,c))

def test_physical_overlap_preserved():
    e=physical(route(1,line((0,0),(3,0))),route(2,line((1,0),(4,0))))
    assert len(e)==1 and e[0].kind=="overlap"
    assert e[0].point is None and e[0].tangent_a is None

def test_physical_reject_nonsmooth_join():
    a=route(1,line((-2,0),(0,0)),line((0,0),(0,2)))
    b=route(2,line((-1,-1),(1,1)))
    with raises(ValueError):
        physical(a,b)

def test_physical_empty():
    assert physical(route(1),route(2))==[]

def test_physical_invalid_tol():
    for tol in (-1,float("nan"),float("inf")):
        with raises(ValueError):
            consolidate(route(1),route(2),[],tol)

def test_physical_two_distinct_points():
    a=route(1,ArcSegment2D(Point2D(2,0),Point2D(-2,0),Point2D(0,0),pi))
    b=route(2,line((-3,1),(3,1)))
    e=physical(a,b)
    assert len(e)==2 and all(x.kind=="cross" for x in e)


def test_physical_coordinate_tolerance_and_order():
    a,b=special_pair()
    raw=find_smoothed_route_intersections_2d(a,b)
    raw[0].point=Point2D(1e-10,0)
    e=consolidate(a,b,raw)
    assert len(e)==1 and e[0].raw_event_count==4
    assert e==consolidate(a,b,list(reversed(raw)))

def test_physical_no_transitive_tolerance_chain():
    a=route(1,line((-2,0),(2,0)))
    b=route(2,line((0,-2),(0,2)))
    original=find_smoothed_route_intersections_2d(a,b)[0]
    raw=[deepcopy(original) for _ in range(3)]
    for e,x in zip(raw,(0,0.75e-9,1.5e-9)):
        e.point=Point2D(x,0)
    e=consolidate(a,b,raw)
    assert len(e)==2
    assert sorted(p.raw_event_count for p in e)==[1,2]

def test_physical_antiparallel_tangent():
    a=route(1,ArcSegment2D(Point2D(2,0),Point2D(-2,0),Point2D(0,0),pi))
    b=route(2,line((3,2),(-3,2)))
    e=physical(a,b)[0]
    assert e.kind=="touch" and e.crossing_angle_rad<1e-9
