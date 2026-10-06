"""二维中心线关系及边界测试，仅使用标准库。"""

from unittest import TestCase

from src.collision import (
    classify_axis_aligned_segment_intersection as classify,
    route_segments, find_route_intersections, find_self_intersections,
)
from src.models import Point2D, Point3D, Route

raises = TestCase().assertRaises


def route(*coordinates: tuple[float, float]) -> Route:
    return Route(1, [Point2D(x, y) for x, y in coordinates])


def test_horizontal_separate():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(2,0), Point2D(0,2), Point2D(2,2)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "none"
        assert result.point == None


def test_vertical_separate():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(0,2), Point2D(2,0), Point2D(2,2)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "none"
        assert result.point == None


def test_cross():
    a1, a2, b1, b2 = [Point2D(0,2), Point2D(4,2), Point2D(2,0), Point2D(2,4)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "cross"
        assert result.point == Point2D(2,2)


def test_endpoint_interior():
    a1, a2, b1, b2 = [Point2D(0,2), Point2D(2,2), Point2D(2,0), Point2D(2,4)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "touch"
        assert result.point == Point2D(2,2)


def test_endpoint_endpoint():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(2,0), Point2D(2,0), Point2D(2,3)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "touch"
        assert result.point == Point2D(2,0)


def test_horizontal_overlap():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(3,0), Point2D(2,0), Point2D(4,0)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "overlap"
        assert result.point == None


def test_vertical_overlap():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(0,3), Point2D(0,2), Point2D(0,4)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "overlap"
        assert result.point == None


def test_identical():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(3,0), Point2D(0,0), Point2D(3,0)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "overlap"
        assert result.point == None


def test_containment():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(5,0), Point2D(1,0), Point2D(3,0)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "overlap"
        assert result.point == None


def test_collinear_touch():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(2,0), Point2D(2,0), Point2D(4,0)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "touch"
        assert result.point == Point2D(2,0)


def test_collinear_gap():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(2,0), Point2D(3,0), Point2D(4,0)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "none"
        assert result.point == None


def test_point_on_line():
    a1, a2, b1, b2 = [Point2D(2,0), Point2D(2,0), Point2D(0,0), Point2D(4,0)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "touch"
        assert result.point == Point2D(2,0)


def test_point_on_vertical():
    a1, a2, b1, b2 = [Point2D(0,2), Point2D(0,2), Point2D(0,0), Point2D(0,4)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "touch"
        assert result.point == Point2D(0,2)


def test_point_off_line():
    a1, a2, b1, b2 = [Point2D(2,1), Point2D(2,1), Point2D(0,0), Point2D(4,0)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "none"
        assert result.point == None


def test_same_points():
    a1, a2, b1, b2 = [Point2D(2,1), Point2D(2,1), Point2D(2,1), Point2D(2,1)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "touch"
        assert result.point == Point2D(2,1)


def test_different_points():
    a1, a2, b1, b2 = [Point2D(2,1), Point2D(2,1), Point2D(3,1), Point2D(3,1)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "none"
        assert result.point == None


def test_orthogonal_disjoint():
    a1, a2, b1, b2 = [Point2D(0,0), Point2D(1,0), Point2D(2,-1), Point2D(2,1)]
    for endpoints in ((a1, a2, b1, b2), (a2, a1, b2, b1), (b1, b2, a1, a2)):
        result = classify(*endpoints)
        assert result.kind == "none"
        assert result.point == None


def test_tolerance():
    assert classify(Point2D(0, 0), Point2D(1, 0), Point2D(1.0001, 0), Point2D(2, 0), tol=0.001).kind == "touch"
    assert classify(Point2D(0, 0), Point2D(1, 0), Point2D(1.0001, 0), Point2D(2, 0), tol=0.00001).kind == "none"
    assert classify(Point2D(0, 0), Point2D(1, 1e-10), Point2D(0.5, -1), Point2D(0.5, 1)).kind == "cross"


def test_invalid_diagonal():
    with raises(ValueError):
        classify(Point2D(0, 0), Point2D(1, 1), Point2D(0, 0), Point2D(1, 0))


def test_invalid_tolerance():
    for tol in (-1, float("nan"), float("inf")):
        with raises(ValueError):
            classify(Point2D(0, 0), Point2D(1, 0), Point2D(0, 0), Point2D(1, 0), tol)


def test_route_none():
    assert find_route_intersections(route((0, 0), (2, 0)), route((0, 2), (2, 2))) == []


def test_route_cross_and_indices():
    results = find_route_intersections(route((0, 0), (0, 2), (4, 2)), route((2, 1), (2, 3)))
    assert len(results) == 1
    result = results[0]
    assert (result.segment_index_a, result.segment_index_b) == (1, 0)
    assert result.kind == "cross"
    assert result.point == Point2D(2, 2)


def test_route_touch():
    results = find_route_intersections(route((0, 0), (2, 0)), route((2, 0), (2, 2)))
    assert len(results) == 1
    assert results[0].kind == "touch"
    assert results[0].point == Point2D(2, 0)


def test_route_overlap():
    results = find_route_intersections(route((0, 0), (3, 0)), route((1, 0), (4, 0)))
    assert len(results) == 1
    assert results[0].kind == "overlap"
    assert results[0].point is None


def test_route_segments():
    source = route((0, 0), (0, 0), (2, 0))
    segments = route_segments(source)
    assert len(segments) == 2
    assert segments[0] == (source.points[0], source.points[1])
    assert segments[1] == (source.points[1], source.points[2])


def test_route_rejects_3d():
    for points in ([Point3D(0, 0, 0)], [Point2D(0, 0), Point3D(1, 0, 0)]):
        with raises(TypeError):
            route_segments(Route(1, points))


def test_short_routes():
    assert route_segments(route()) == []
    assert route_segments(route((0, 0))) == []
    assert find_route_intersections(route(), route((0, 0), (1, 0))) == []
    assert find_self_intersections(route((0, 0))) == []


def test_diagonal_route_rejected_even_against_empty():
    with raises(ValueError):
        find_route_intersections(route((0, 0), (1, 1)), route())


def test_normal_u_z_no_self_intersections():
    assert find_self_intersections(route((0, 0), (2, 0), (2, 4), (0, 4))) == []
    assert find_self_intersections(route((0, 0), (0, 2), (4, 2), (4, 4))) == []


def test_self_cross():
    results = find_self_intersections(route((0, 0), (4, 0), (4, 3), (2, 3), (2, -1)))
    assert len(results) == 1
    assert (results[0].segment_index_a, results[0].segment_index_b) == (0, 3)
    assert results[0].kind == "cross"
    assert results[0].point == Point2D(2, 0)


def test_self_overlap():
    results = find_self_intersections(route((0, 0), (4, 0), (4, 2), (1, 2), (1, 0), (3, 0)))
    assert any(r.segment_index_a == 0 and r.segment_index_b == 4 and r.kind == "overlap" for r in results)


def test_self_nonadjacent_touch():
    results = find_self_intersections(route((0, 0), (2, 0), (2, 2), (0, 2), (0, 0)))
    assert len(results) == 1
    assert results[0].kind == "touch"
    assert (results[0].segment_index_a, results[0].segment_index_b) == (0, 3)


def test_adjacent_reversal_overlap():
    results = find_self_intersections(route((0, 0), (3, 0), (1, 0)))
    assert len(results) == 1
    assert results[0].kind == "overlap"


def test_shared_corner_keeps_distinct_segment_pairs():
    results = find_route_intersections(route((0, 0), (2, 0), (2, 2)), route((1, -1), (1, 0), (3, 0)))
    keys = [(r.segment_index_a, r.segment_index_b) for r in results]
    assert len(keys) == len(set(keys))
    assert len(results) == 3


from copy import deepcopy
from unittest.mock import patch
from collections import Counter
from src.collision import validate_routes_2d


def batch_route(identifier, *coordinates):
    return Route(identifier, [Point2D(x,y) for x,y in coordinates])


def test_batch_empty_single_and_disjoint():
    assert validate_routes_2d([]).valid
    a=batch_route(1,(0,0),(2,0))
    assert validate_routes_2d([a]).valid
    report=validate_routes_2d([a,batch_route(2,(0,3),(2,3))])
    assert report.valid and report.pair_count==1 and report.pairwise_events==[]


def test_batch_cross_allowed_and_recorded():
    report=validate_routes_2d([batch_route(1,(0,2),(4,2)),batch_route(2,(2,0),(2,4))])
    assert report.valid and report.invalid_route_ids==[]
    assert len(report.pairwise_events)==1
    e=report.pairwise_events[0]
    assert (e.route_id_a,e.route_id_b,e.segment_index_a,e.segment_index_b,e.kind,e.point)==(1,2,0,0,"cross",Point2D(2,2))


def test_batch_touch_invalid():
    report=validate_routes_2d([batch_route(1,(0,0),(2,0)),batch_route(2,(2,0),(2,3))])
    assert not report.valid and report.invalid_route_ids==[1,2]
    assert report.pairwise_events[0].kind=="touch"


def test_batch_overlap_invalid():
    report=validate_routes_2d([batch_route(1,(0,0),(3,0)),batch_route(2,(1,0),(4,0))])
    assert not report.valid and report.invalid_route_ids==[1,2]
    assert report.pairwise_events[0].kind=="overlap"


def test_batch_self_cross():
    report=validate_routes_2d([batch_route(7,(0,0),(4,0),(4,3),(2,3),(2,-1))])
    assert not report.valid and report.invalid_route_ids==[7]
    assert any(e.kind=="cross" for e in report.self_events)


def test_batch_self_touch():
    report=validate_routes_2d([batch_route(7,(0,0),(2,0),(2,2),(0,2),(0,0))])
    assert not report.valid and report.invalid_route_ids==[7]
    assert any(e.kind=="touch" for e in report.self_events)


def test_batch_self_overlap():
    report=validate_routes_2d([batch_route(7,(0,0),(4,0),(4,2),(1,2),(1,0),(3,0))])
    assert not report.valid and report.invalid_route_ids==[7]
    assert any(e.kind=="overlap" for e in report.self_events)


def test_batch_pair_once_order_invariance_and_no_mutation():
    routes=[batch_route(1,(0,0),(4,0)),batch_route(2,(1,0),(3,0)),batch_route(3,(2,0),(2,2))]
    before=deepcopy(routes)
    with patch("src.collision.find_route_intersections",wraps=find_route_intersections) as detector:
        report=validate_routes_2d(routes)
        assert detector.call_count==3
    other=validate_routes_2d(list(reversed(routes)))
    assert Counter(e.kind for e in report.pairwise_events)==Counter(e.kind for e in other.pairwise_events)
    assert report.invalid_route_ids==other.invalid_route_ids==[1,2,3]
    assert routes==before


def test_batch_rejects_3d_and_duplicate_ids():
    with raises(TypeError):
        validate_routes_2d([Route(1,[Point3D(0,0,0)])])
    with raises(ValueError):
        validate_routes_2d([batch_route(1,(0,0),(1,0)),batch_route(1,(0,2),(1,2))])


def test_batch_exact_duplicate_event_suppressed():
    from src.collision import RouteIntersection
    event=RouteIntersection(0,0,"cross",Point2D(1,1))
    with patch("src.collision.find_route_intersections",return_value=[event,event]):
        report=validate_routes_2d([batch_route(1,(0,1),(2,1)),batch_route(2,(1,0),(1,2))])
    assert len(report.pairwise_events)==1 and report.valid


# Analytic curve tests: all fixtures are synthetic, independent of the allocator.
from math import pi, cos, sin, sqrt
from src.models import LineSegment2D, ArcSegment2D, SmoothedRoute2D
from src.geometry import smooth_orthogonal_route_2d, build_special_z_smoothed_route_2d
from src.collision import (
    point_on_arc_2d, find_segment_intersections_2d as curves,
    find_smoothed_route_intersections_2d as curve_routes,
    find_smoothed_route_self_intersections_2d as curve_self,
)


def analytic_line(x1,y1,x2,y2):
    return LineSegment2D(Point2D(x1,y1),Point2D(x2,y2))


def analytic_arc(cx=0,cy=0,r=2,angle=0,sweep=pi):
    return ArcSegment2D(
        Point2D(cx+r*cos(angle),cy+r*sin(angle)),
        Point2D(cx+r*cos(angle+sweep),cy+r*sin(angle+sweep)),
        Point2D(cx,cy),sweep,
    )


def expect_events(a,b,kinds,points=None,tol=1e-9):
    events=curves(a,b,tol)
    assert sorted(e.kind for e in events)==sorted(kinds)
    if points is not None:
        assert len(events)==len(points)
        for x,y in points:
            assert any(e.point is not None and
                       abs(e.point.x-x)<=1e-8 and abs(e.point.y-y)<=1e-8 for e in events)
    return events


def test_analytic_line_cross():
    expect_events(analytic_line(0,0,4,4),analytic_line(0,4,4,0),["cross"],[(2,2)])


def test_analytic_line_endpoint():
    expect_events(analytic_line(0,0,2,2),analytic_line(2,2,4,0),["touch"],[(2,2)])


def test_analytic_line_parallel():
    expect_events(analytic_line(0,0,4,4),analytic_line(0,1,4,5),[])


def test_analytic_line_collinear_overlap():
    events=expect_events(analytic_line(0,0,4,4),analytic_line(3,3,1,1),["overlap"])
    assert events[0].point is None


def test_analytic_line_collinear_touch():
    expect_events(analytic_line(0,0,2,2),analytic_line(2,2,4,4),["touch"],[(2,2)])


def test_analytic_line_collinear_disjoint():
    expect_events(analytic_line(0,0,2,2),analytic_line(3,3,4,4),[])


def test_analytic_line_near_parallel_cross():
    expect_events(analytic_line(0,0,1,1e-8),analytic_line(0,1e-8,1,0),
                  ["cross"],[(0.5,5e-9)],tol=1e-12)


def test_analytic_line_near_parallel_disjoint():
    expect_events(analytic_line(0,0,1,1e-8),analytic_line(0,1,1,1+2e-8),[])


def test_analytic_line_arc_two():
    expect_events(analytic_line(-3,1,3,1),analytic_arc(),
                  ["cross","cross"],[(-sqrt(3),1),(sqrt(3),1)])


def test_analytic_line_arc_tangent():
    expect_events(analytic_line(-3,2,3,2),analytic_arc(),["touch"],[(0,2)])


def test_analytic_line_arc_none():
    expect_events(analytic_line(-3,3,3,3),analytic_arc(),[])


def test_analytic_line_arc_sweep_excludes():
    expect_events(analytic_line(-3,-1,3,-1),analytic_arc(),[])


def test_analytic_line_arc_tangent_outside_line():
    expect_events(analytic_line(1,2,3,2),analytic_arc(),[])


def test_analytic_line_arc_endpoint():
    expect_events(analytic_line(2,-1,2,1),analytic_arc(),["touch"],[(2,0)])


def test_analytic_line_arc_line_endpoint():
    expect_events(analytic_line(0,2,0,3),analytic_arc(),["touch"],[(0,2)])


def test_analytic_line_arc_cw():
    expect_events(analytic_line(-3,1,3,1),analytic_arc(angle=pi,sweep=-pi),
                  ["cross","cross"],[(-sqrt(3),1),(sqrt(3),1)])


def test_analytic_line_arc_ccw_quarter():
    expect_events(analytic_line(-3,1,3,1),analytic_arc(sweep=pi/2),["cross"],[(sqrt(3),1)])


def test_analytic_line_arc_mixed_classifications():
    expect_events(analytic_line(-sqrt(3),1,3,1),analytic_arc(),["touch","cross"])


def test_analytic_arc_two_crossings():
    expect_events(analytic_arc(),analytic_arc(cy=1,angle=pi),
                  ["cross","cross"],[(-sqrt(3.75),0.5),(sqrt(3.75),0.5)])


def test_analytic_arc_external_tangent():
    expect_events(analytic_arc(r=1,angle=-pi/2),
                  analytic_arc(cx=2,r=1,angle=pi/2),["touch"],[(1,0)])


def test_analytic_arc_internal_tangent():
    expect_events(analytic_arc(angle=-pi/2),
                  analytic_arc(cx=1,r=1,angle=-pi/2),["touch"],[(2,0)])


def test_analytic_arc_separated():
    expect_events(analytic_arc(),analytic_arc(cx=10),[])


def test_analytic_arc_contained():
    expect_events(analytic_arc(r=4),analytic_arc(cx=1,r=1),[])


def test_analytic_arc_concentric_unequal():
    expect_events(analytic_arc(),analytic_arc(r=1),[])


def test_analytic_arc_identical_overlap():
    events=expect_events(analytic_arc(),analytic_arc(),["overlap"])
    assert events[0].point is None


def test_analytic_arc_partial_overlap():
    expect_events(analytic_arc(),analytic_arc(angle=pi/2),["overlap"])


def test_analytic_arc_reversed_overlap():
    expect_events(analytic_arc(),analytic_arc(angle=pi,sweep=-pi),["overlap"])


def test_analytic_arc_endpoint_only():
    expect_events(analytic_arc(sweep=pi/2),analytic_arc(angle=pi/2,sweep=pi/2),
                  ["touch"],[(0,2)])


def test_analytic_arc_complementary_semicircles():
    expect_events(analytic_arc(),analytic_arc(angle=pi),
                  ["touch","touch"],[(2,0),(-2,0)])


def test_analytic_arc_supporting_intersections_excluded():
    expect_events(analytic_arc(angle=pi),analytic_arc(cy=1),[])


def test_analytic_arc_wrap_overlap():
    expect_events(analytic_arc(angle=7*pi/4,sweep=pi/2),
                  analytic_arc(angle=-pi/8,sweep=pi/4),["overlap"])


def test_analytic_arc_membership_wrap_ccw():
    arc=analytic_arc(angle=7*pi/4,sweep=pi/2)
    assert point_on_arc_2d(Point2D(2,0),arc)
    assert not point_on_arc_2d(Point2D(-2,0),arc)
    assert point_on_arc_2d(arc.start,arc) and point_on_arc_2d(arc.end,arc)


def test_analytic_arc_membership_wrap_cw():
    arc=analytic_arc(angle=pi/4,sweep=-pi/2)
    assert point_on_arc_2d(Point2D(2,0),arc)
    assert not point_on_arc_2d(Point2D(-2,0),arc)


def test_analytic_arc_membership_pi_boundary():
    arc=analytic_arc(angle=3*pi/4,sweep=pi/2)
    assert point_on_arc_2d(Point2D(-2,0),arc)
    assert not point_on_arc_2d(Point2D(2,0),arc)


def test_analytic_arc_membership_radial_tolerance():
    arc=analytic_arc()
    assert point_on_arc_2d(Point2D(0,2+1e-10),arc)
    assert not point_on_arc_2d(Point2D(0,2+1e-6),arc)


def test_analytic_route_adjacent_smoothing():
    smoothed=smooth_orthogonal_route_2d(route((0,0),(0,10),(10,10),(10,20)),2)
    assert curve_self(smoothed)==[]


def test_analytic_route_pair_cross_metadata():
    a=SmoothedRoute2D(71,[analytic_line(-3,1,3,1)])
    b=SmoothedRoute2D(72,[analytic_arc()])
    events=curve_routes(a,b)
    assert len(events)==2
    for e in events:
        assert (e.route_id_a,e.route_id_b,e.segment_index_a,e.segment_index_b)==(71,72,0,0)
        assert (e.segment_type_a,e.segment_type_b)==("LineSegment2D","ArcSegment2D")
        assert e.kind=="cross"


def test_analytic_route_pair_touch():
    a=SmoothedRoute2D(1,[analytic_line(-3,2,3,2)])
    b=SmoothedRoute2D(2,[analytic_arc()])
    assert [e.kind for e in curve_routes(a,b)]==["touch"]


def test_analytic_route_pair_overlap():
    a=SmoothedRoute2D(1,[analytic_arc()])
    b=SmoothedRoute2D(2,[analytic_arc(angle=pi/2)])
    assert [e.kind for e in curve_routes(a,b)]==["overlap"]


def test_analytic_route_no_mutation():
    a=SmoothedRoute2D(1,[analytic_line(-3,1,3,1)])
    b=SmoothedRoute2D(2,[analytic_arc()])
    before=deepcopy((a,b))
    curve_routes(a,b)
    curve_self(a)
    assert (a,b)==before


def test_analytic_route_self_cross():
    r=SmoothedRoute2D(1,[analytic_line(0,0,4,4),analytic_line(4,4,0,4),analytic_line(0,4,4,0)])
    events=curve_self(r)
    assert len(events)==1 and events[0].kind=="cross"
    assert (events[0].segment_index_a,events[0].segment_index_b)==(0,2)


def test_analytic_route_adjacent_overlap_retained():
    r=SmoothedRoute2D(1,[analytic_line(0,0,4,4),analytic_line(4,4,2,2)])
    assert [e.kind for e in curve_self(r)]==["overlap"]


def test_analytic_special_z_smoke():
    r=build_special_z_smoothed_route_2d(9,Point2D(0,0),Point2D(4,20),5)
    assert curve_self(r)==[]
    crossing=SmoothedRoute2D(10,[analytic_line(-1,3,5,3)])
    assert [e.kind for e in curve_routes(r,crossing)]==["cross"]
    for arc in (s for s in r.segments if isinstance(s,ArcSegment2D)):
        angle=atan2_for_test(arc)+arc.sweep_rad/2
        p=Point2D(arc.center.x+5*cos(angle),arc.center.y+5*sin(angle))
        assert point_on_arc_2d(p,arc)


def atan2_for_test(arc):
    from math import atan2
    return atan2(arc.start.y-arc.center.y,arc.start.x-arc.center.x)


def test_analytic_invalid_geometry():
    for bad in (analytic_line(0,0,0,0),analytic_line(0,0,float("inf"),1),
                ArcSegment2D(Point2D(1,0),Point2D(0,2),Point2D(0,0),pi/2)):
        with raises(ValueError):
            curves(bad,analytic_arc())


def test_analytic_invalid_tolerance():
    for tol in (-1,float("nan"),float("inf")):
        with raises(ValueError):
            curves(analytic_arc(),analytic_arc(),tol)


def test_analytic_empty_and_disconnected_routes():
    assert curve_routes(SmoothedRoute2D(1,[]),SmoothedRoute2D(2,[]))==[]
    with raises(ValueError):
        curve_routes(SmoothedRoute2D(1,[]),SmoothedRoute2D(2,[
            analytic_line(0,0,1,0),analytic_line(3,0,4,0)]))


def test_analytic_pair_symmetry():
    a,b=analytic_line(-3,1,3,1),analytic_arc()
    assert curves(a,b)==curves(b,a)
    a,b=analytic_arc(),analytic_arc(cy=1,angle=pi)
    ea,eb=curves(a,b),curves(b,a)
    assert sorted((e.kind,round(e.point.x,8),round(e.point.y,8)) for e in ea)==sorted(
        (e.kind,round(e.point.x,8),round(e.point.y,8)) for e in eb)


def test_analytic_near_tangent_two_resolved_points():
    events=curves(analytic_line(-3,2-1e-6,3,2-1e-6),analytic_arc())
    assert len(events)==2 and all(e.kind=="cross" for e in events)


def test_analytic_adjacent_arcs_keep_second_crossing():
    a=analytic_arc()
    b=analytic_arc(cx=-2,cy=1,r=1,angle=-pi/2)
    events=curve_self(SmoothedRoute2D(5,[a,b]))
    assert len(events)==1 and events[0].kind=="cross"
    assert abs(events[0].point.x+1.2)<1e-9
    assert abs(events[0].point.y-1.6)<1e-9


def test_analytic_nonadjacent_endpoint_retained():
    r=SmoothedRoute2D(1,[analytic_line(0,0,2,0),analytic_line(2,0,2,2),
                         analytic_line(2,2,0,2),analytic_line(0,2,0,0)])
    events=curve_self(r)
    assert len(events)==1 and events[0].kind=="touch"
    assert (events[0].segment_index_a,events[0].segment_index_b)==(0,3)


def test_analytic_coincident_disjoint_arcs():
    expect_events(analytic_arc(sweep=pi/4),analytic_arc(angle=pi,sweep=pi/4),[])


def test_analytic_wrap_line_arc():
    expect_events(analytic_line(1,-3,1,3),
                  analytic_arc(angle=-pi/3,sweep=2*pi/3),
                  ["touch","touch"],[(1,-sqrt(3)),(1,sqrt(3))])


def test_analytic_tangent_roundoff_deduplicated():
    expect_events(analytic_line(-3,2+1e-12,3,2+1e-12),
                  analytic_arc(),["touch"],[(0,2)])


def test_analytic_route_arc_arc_keeps_both_points():
    events=curve_routes(SmoothedRoute2D(11,[analytic_arc()]),
                        SmoothedRoute2D(12,[analytic_arc(cy=1,angle=pi)]))
    assert len(events)==2 and all(e.kind=="cross" for e in events)
    assert all(e.segment_type_a==e.segment_type_b=="ArcSegment2D" for e in events)
