"""Synthetic tests for the restricted legacy multi-waveguide criterion."""
from copy import deepcopy
from itertools import combinations
from unittest import TestCase
from src.models import Point2D
from src.physical_intersections import PhysicalRouteIntersection as Event
from src.multi_crossing import (
 build_crossing_pair_map as pairmap,build_crossing_graph as graph,
 enumerate_crossing_triangles as triangles,classify_multi_crossing as classify,
 detect_multi_waveguide_crossings as detect,triplet_composition,audit_pair_multiplicity)
raises=TestCase().assertRaises

def event(a,b,x,y):
 return Event(a,b,Point2D(x,y),"cross",crossing_angle_rad=1.0)
def fixture(points=((0,0),(.05,0),(0,.05))):
 return [event(a,b,*p) for (a,b),p in zip(((1,2),(1,3),(2,3)),points)]

def test_multi_detect_two_short():
 r=list(detect(fixture(((0,0),(.1,0),(0,.1)))))[0]
 assert r.classification=="multi_waveguide_crossing" and r.short_side_count==2
def test_multi_only_one_short():
 assert list(detect(fixture(((0,0),(.05,0),(1,1)))))[0].classification=="not_multi_waveguide_crossing"
def test_multi_all_safe():
 assert list(detect(fixture(((0,0),(1,0),(0,1)))))[0].classification=="not_multi_waveguide_crossing"
def test_multi_missing_edge():
 assert list(detect(fixture()[:2]))==[]
def test_multi_eligible():
 r=list(detect(fixture()))[0]
 assert all(p is not None for p in (r.point_ab,r.point_ac,r.point_bc))
 assert r.side_lengths_mm is not None
def test_multi_multiple_cross_outside():
 events=fixture()+[event(1,2,1,1)]
 r=list(detect(events))[0]
 assert r.classification=="outside_legacy_single_cross_assumption"
 assert r.point_ab is r.point_ac is r.point_bc is r.side_lengths_mm is None
def test_multi_spacing_not_pitch():
 events=fixture(((0,0),(.15,0),(0,.15)))
 assert list(detect(events))[0].classification=="not_multi_waveguide_crossing"
 assert list(detect(events,.175))[0].classification=="multi_waveguide_crossing"
def test_multi_boundary():
 r=list(detect(fixture(((0,0),(.125,0),(0,.125)))))[0]
 assert r.classification=="boundary" and r.short_side_count==0 and r.boundary_side_count==2
def test_multi_near_threshold():
 for delta in (-.5e-9,.5e-9):
  r=list(detect(fixture(((0,0),(.125+delta,0),(0,.125+delta)))))[0]
  assert r.classification=="boundary"
def test_multi_direction_order_invariant():
 events=fixture()
 expected=list(detect(events))
 for e in events:e.route_a_id,e.route_b_id=e.route_b_id,e.route_a_id
 assert list(detect(list(reversed(events))))==expected
def test_multi_triplet_once():
 assert [r.route_ids for r in detect(fixture())]==[(1,2,3)]
def test_multi_complete_four_graph():
 events=[event(a,b,a,b) for a,b in combinations(range(4),2)]
 assert list(triangles(graph(pairmap(events))))==list(combinations(range(4),3))
def test_multi_graph_reference():
 edges=[(0,1),(0,2),(1,2),(1,3),(2,3),(0,4),(3,4)]
 expected=[t for t in combinations(range(5),3) if all(p in edges for p in combinations(t,2))]
 events=[event(a,b,a,b) for a,b in edges]
 assert list(triangles(graph(pairmap(events))))==expected
def test_multi_input_unchanged():
 events=fixture();saved=deepcopy(events)
 result=list(detect(events))
 result[0].point_ab.x=99
 assert events==saved
def test_multi_composition():
 assert [triplet_composition((1,2,3),set(range(1,n+1))) for n in range(4)]==[
  "ordinary/ordinary/ordinary","ordinary/ordinary/special","ordinary/special/special","special/special/special"]
def test_multi_empty():
 assert list(detect([]))==[]
def test_multi_multiplicity_audit():
 events=fixture()+[event(1,2,2,2),event(1,3,3,3),event(1,3,4,4)]
 a=audit_pair_multiplicity(pairmap(events))
 assert a["pairs_with_1_cross"]==a["pairs_with_2_crosses"]==a["pairs_with_3_or_more_crosses"]==1
 assert a["pairs_with_multiple_crosses"]==2 and a["max_crosses_per_pair"]==3
def test_multi_boundary_with_two_short():
 r=list(detect(fixture(((0,0),(.0625,0),(.125,0)))))[0]
 assert r.classification=="multi_waveguide_crossing" and r.boundary_side_count==1
def test_multi_non_cross_ignored():
 e=event(1,2,0,0);e.kind="touch"
 assert list(detect([e]))==[]
def test_multi_invalid_spacing():
 for spacing,tol in ((0,1e-9),(.125,-1),(.125,.125),(float("nan"),0)):
  with raises(ValueError):list(detect([],spacing,tol))
