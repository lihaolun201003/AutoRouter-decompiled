"""Known-loss integration tests; no crossing-loss approximation."""
from math import pi,isclose
from copy import deepcopy
from dataclasses import asdict
from unittest import TestCase
from unittest.mock import patch
from src.models import Point2D,LineSegment2D,ArcSegment2D,SmoothedRoute2D,Route
from src.geometry import smooth_orthogonal_route_2d,build_special_z_smoothed_route_2d
from src.loss_analysis import analyze_route_loss_mm as analyze,crossing_angle_statistics as angles
from src.loss import bend_loss,crossing_loss
from src.physical_intersections import find_physical_route_intersections_2d
raises=TestCase().assertRaises
def line_route():
 return SmoothedRoute2D(1,[LineSegment2D(Point2D(0,0),Point2D(10,0))])
def arc_route(sweep=pi/2):
 from math import cos,sin
 return SmoothedRoute2D(1,[ArcSegment2D(Point2D(5,0),Point2D(5*cos(sweep),5*sin(sweep)),Point2D(0,0),sweep)])
def event(angle):
 return dict(kind="cross",route_a_id=1,route_b_id=2,crossing_angle_rad=angle)
def test_loss_line_length():
 assert analyze(line_route())["line_length_mm"]==10
def test_loss_arc_length():
 assert isclose(analyze(arc_route())["arc_length_mm"],5*pi/2)
def test_loss_mm_conversion():
 assert isclose(analyze(line_route())["propagation_loss_db"],.05)
def test_loss_full_arc_propagation():
 assert isclose(analyze(arc_route())["propagation_loss_db"],5*pi/2/10*.05)
def test_loss_quarter_bend():
 assert isclose(analyze(arc_route())["bend_loss_db"],2.39)
def test_loss_eighth_bend():
 assert isclose(analyze(arc_route(pi/4))["bend_loss_db"],1.195)
def test_loss_cw_ccw():
 assert isclose(analyze(arc_route())["bend_loss_db"],analyze(arc_route(-pi/2))["bend_loss_db"])
def test_loss_ordinary_two_bends():
 r=smooth_orthogonal_route_2d(Route(1,[Point2D(0,0),Point2D(0,20),Point2D(20,20),Point2D(20,40)]),5)
 v=analyze(r)
 assert v["arc_count"]==2 and isclose(v["bend_loss_db"],4.78)
def test_loss_special_sweeps():
 r=build_special_z_smoothed_route_2d(1,Point2D(0,0),Point2D(4,20),5)
 v=analyze(r)
 assert v["arc_count"]==2
 assert isclose(v["bend_loss_db"],2.39*v["total_bend_angle_rad"]/(pi/2))
 assert not isclose(v["bend_loss_db"],4.78)
def test_loss_known_sum():
 v=analyze(arc_route())
 assert v["known_non_crossing_loss_db"]==v["propagation_loss_db"]+v["bend_loss_db"]
def test_loss_crossing_not_called():
 with patch("src.loss.crossing_loss",side_effect=AssertionError) as forbidden:
  analyze(arc_route())
  assert not forbidden.called
 with raises(NotImplementedError):crossing_loss(45)
def test_loss_angle_reversal():
 a=line_route()
 b=SmoothedRoute2D(2,[LineSegment2D(Point2D(5,-2),Point2D(5,2))])
 first=find_physical_route_intersections_2d(a,b)[0]
 rb=SmoothedRoute2D(2,[LineSegment2D(b.segments[0].end,b.segments[0].start)])
 assert isclose(first.crossing_angle_rad,find_physical_route_intersections_2d(a,rb)[0].crossing_angle_rad)
def test_loss_angle_all_counted():
 a=angles([event(i*pi/18) for i in range(10)],[1,2])
 assert a["degrees"]["count"]==10 and sum(h["count"] for h in a["histogram"])==10
 assert sum(a["coarse"].values())==10
def test_loss_no_cross_null():
 a=angles([],[1])
 assert a["per_waveguide"][1]["crossing_angle_mean_deg"] is None
 assert a["per_waveguide"][1]["physical_cross_count"]==0
def test_loss_geometry_unchanged():
 r=arc_route();saved=deepcopy(r)
 analyze(r)
 assert r==saved
def test_loss_unknown_radius_rejected():
 with raises(ValueError):analyze(arc_route(),4)
def test_loss_invalid_angle_rejected():
 for value in (None,-1,float("nan"),pi):
  with raises(ValueError):angles([event(value)],[1,2])
