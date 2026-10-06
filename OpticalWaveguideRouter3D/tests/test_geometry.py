"""二维基础几何的独立测试，不依赖第三方库。"""

from unittest import TestCase

raises = TestCase().assertRaises

from src.geometry import (
    normalize_orthogonal_polyline,
    build_u_route,
    build_z_route,
    build_special_z_route,
    distance,
    intervals_overlap,
    point_on_axis_aligned_segment,
    points_close,
    segment_length,
    segment_orientation,
)
from src.models import Point2D


def test_horizontal_distance():
    assert distance(Point2D(1.0, 2.0), Point2D(5.0, 2.0)) == 4.0


def test_vertical_distance():
    assert distance(Point2D(1.0, 5.0), Point2D(1.0, 2.0)) == 3.0


def test_diagonal_distance():
    assert distance(Point2D(0.0, 0.0), Point2D(3.0, 4.0)) == 5.0


def test_points_close_float_roundoff():
    assert points_close(Point2D(0.1 + 0.2, 1.0), Point2D(0.3, 1.0))


def test_points_close_rejects_difference_in_either_coordinate():
    assert not points_close(Point2D(0.0, 0.0), Point2D(0.01, 0.0))
    assert not points_close(Point2D(0.0, 0.0), Point2D(0.0, 0.01))


def test_points_close_custom_tolerance():
    assert points_close(Point2D(0.0, 0.0), Point2D(0.01, 0.01), tol=0.01)
    assert not points_close(Point2D(0.0, 0.0), Point2D(0.01, 0.01), tol=0.001)


def test_horizontal_orientation():
    assert segment_orientation(Point2D(4.0, 2.0), Point2D(1.0, 2.0)) == "horizontal"


def test_vertical_orientation():
    assert segment_orientation(Point2D(2.0, 1.0), Point2D(2.0, 4.0)) == "vertical"


def test_other_orientation():
    assert segment_orientation(Point2D(0.0, 0.0), Point2D(3.0, 4.0)) == "other"


def test_orientation_tolerance():
    assert segment_orientation(Point2D(0.0, 0.0), Point2D(2.0, 1e-10)) == "horizontal"
    assert segment_orientation(Point2D(0.0, 0.0), Point2D(1e-10, 2.0)) == "vertical"


def test_horizontal_segment_length():
    assert segment_length(Point2D(5.0, 2.0), Point2D(1.0, 2.0)) == 4.0


def test_vertical_segment_length():
    assert segment_length(Point2D(1.0, 5.0), Point2D(1.0, 2.0)) == 3.0


def test_diagonal_segment_length_raises():
    try:
        segment_length(Point2D(0.0, 0.0), Point2D(3.0, 4.0))
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for a diagonal segment")


def test_intervals_overlap():
    assert intervals_overlap(0.0, 3.0, 2.0, 5.0)


def test_intervals_disjoint():
    assert not intervals_overlap(0.0, 1.0, 2.0, 3.0)


def test_intervals_touch():
    assert intervals_overlap(0.0, 1.0, 1.0, 2.0)


def test_intervals_reversed():
    assert intervals_overlap(3.0, 0.0, 5.0, 2.0)
    assert not intervals_overlap(1.0, 0.0, 3.0, 2.0)


def test_intervals_tolerance():
    assert intervals_overlap(0.0, 1.0, 1.0001, 2.0, tol=0.001)
    assert not intervals_overlap(0.0, 1.0, 1.0001, 2.0, tol=0.00001)


def test_point_inside_horizontal_segment():
    assert point_on_axis_aligned_segment(Point2D(2.0, 1.0), Point2D(4.0, 1.0), Point2D(0.0, 1.0))


def test_point_inside_vertical_segment():
    assert point_on_axis_aligned_segment(Point2D(1.0, 2.0), Point2D(1.0, 4.0), Point2D(1.0, 0.0))


def test_point_at_segment_endpoints():
    start, end = Point2D(0.0, 1.0), Point2D(4.0, 1.0)
    assert point_on_axis_aligned_segment(start, start, end)
    assert point_on_axis_aligned_segment(end, start, end)


def test_point_on_extension_outside_segment():
    assert not point_on_axis_aligned_segment(Point2D(5.0, 1.0), Point2D(0.0, 1.0), Point2D(4.0, 1.0))
    assert not point_on_axis_aligned_segment(Point2D(1.0, -1.0), Point2D(1.0, 0.0), Point2D(1.0, 4.0))


def test_point_off_segment_line():
    assert not point_on_axis_aligned_segment(Point2D(2.0, 2.0), Point2D(0.0, 1.0), Point2D(4.0, 1.0))
    assert not point_on_axis_aligned_segment(Point2D(2.0, 2.0), Point2D(1.0, 0.0), Point2D(1.0, 4.0))


def test_point_on_segment_tolerance():
    assert point_on_axis_aligned_segment(Point2D(4.0001, 1.0001), Point2D(0.0, 1.0), Point2D(4.0, 1.0), tol=0.001)


def test_degenerate_segment():
    point = Point2D(2.0, 3.0)
    assert segment_orientation(point, point) == "horizontal"
    assert segment_length(point, point) == 0.0
    assert point_on_axis_aligned_segment(point, point, point)
    assert not point_on_axis_aligned_segment(Point2D(4.0, 3.0), point, point)


def test_point_on_diagonal_segment_raises():
    try:
        point_on_axis_aligned_segment(Point2D(1.0, 1.0), Point2D(0.0, 0.0), Point2D(2.0, 2.0))
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for a diagonal segment")


def test_normalize_duplicates():
    points = [Point2D(0, 0), Point2D(0, 0), Point2D(2, 0), Point2D(2, 0)]
    assert normalize_orthogonal_polyline(points) == [Point2D(0, 0), Point2D(2, 0)]
    assert len(points) == 4


def test_normalize_horizontal():
    assert normalize_orthogonal_polyline(
        [Point2D(3, 0), Point2D(2, 0), Point2D(1, 0), Point2D(0, 0)]
    ) == [Point2D(3, 0), Point2D(0, 0)]


def test_normalize_vertical():
    assert normalize_orthogonal_polyline(
        [Point2D(0, 0), Point2D(0, 1), Point2D(0, 2)]
    ) == [Point2D(0, 0), Point2D(0, 2)]


def test_normalize_corner():
    points = [Point2D(0, 0), Point2D(2, 0), Point2D(2, 3)]
    assert normalize_orthogonal_polyline(points) == points


def test_normalize_diagonal_raises():
    with raises(ValueError):
        normalize_orthogonal_polyline([Point2D(0, 0), Point2D(1, 1)])


def test_normalize_tiny_diagonal_raises():
    with raises(ValueError):
        normalize_orthogonal_polyline([Point2D(0, 0), Point2D(1, 1e-12)])


def test_normalize_empty_and_single():
    assert normalize_orthogonal_polyline([]) == []
    assert normalize_orthogonal_polyline([Point2D(1, 2)]) == [Point2D(1, 2)]


def test_normalize_preserves_reversal():
    points = [Point2D(0, 0), Point2D(3, 0), Point2D(1, 0)]
    assert normalize_orthogonal_polyline(points) == points


def test_u_track_overlap():
    assert build_u_route(Point2D(2, 0), Point2D(0, 3), 2, "left") == [
        Point2D(2, 0), Point2D(2, 3), Point2D(0, 3),
    ]
    assert build_u_route(Point2D(0, 2), Point2D(3, 2), 2, "top") == [
        Point2D(0, 2), Point2D(3, 2),
    ]


def test_u_invalid_side():
    with raises(ValueError):
        build_u_route(Point2D(0, 0), Point2D(0, 3), 2, "invalid")


def test_z_middle_overlap():
    assert build_z_route(Point2D(0, 0), Point2D(3, 4), 0, "horizontal") == [
        Point2D(0, 0), Point2D(3, 0), Point2D(3, 4),
    ]
    assert build_z_route(Point2D(0, 0), Point2D(3, 4), 3, "vertical") == [
        Point2D(0, 0), Point2D(3, 0), Point2D(3, 4),
    ]


def test_z_invalid_orientation():
    with raises(ValueError):
        build_z_route(Point2D(0, 0), Point2D(3, 4), 2, "invalid")


def test_special_z_not_implemented():
    with raises(NotImplementedError):
        build_special_z_route(Point2D(0, 0), Point2D(3, 4))


def test_u_left():
    start, end = Point2D(0, 0), Point2D(0, 4)
    result = build_u_route(start, end, 2, "left")
    assert result == [Point2D(0, 0), Point2D(2, 0), Point2D(2, 4), Point2D(0, 4)]
    assert result[0] is start
    assert result[-1] is end
    for first, second in zip(result, result[1:]):
        assert first != second
        assert segment_orientation(first, second, tol=0.0) != "other"


def test_u_right():
    start, end = Point2D(4, 0), Point2D(4, 4)
    result = build_u_route(start, end, 2, "right")
    assert result == [Point2D(4, 0), Point2D(2, 0), Point2D(2, 4), Point2D(4, 4)]
    assert result[0] is start
    assert result[-1] is end
    for first, second in zip(result, result[1:]):
        assert first != second
        assert segment_orientation(first, second, tol=0.0) != "other"


def test_u_top():
    start, end = Point2D(0, 4), Point2D(4, 4)
    result = build_u_route(start, end, 2, "top")
    assert result == [Point2D(0, 4), Point2D(0, 2), Point2D(4, 2), Point2D(4, 4)]
    assert result[0] is start
    assert result[-1] is end
    for first, second in zip(result, result[1:]):
        assert first != second
        assert segment_orientation(first, second, tol=0.0) != "other"


def test_u_bottom():
    start, end = Point2D(0, 0), Point2D(4, 0)
    result = build_u_route(start, end, 2, "bottom")
    assert result == [Point2D(0, 0), Point2D(0, 2), Point2D(4, 2), Point2D(4, 0)]
    assert result[0] is start
    assert result[-1] is end
    for first, second in zip(result, result[1:]):
        assert first != second
        assert segment_orientation(first, second, tol=0.0) != "other"


def test_z_horizontal():
    start, end = Point2D(0, 0), Point2D(4, 6)
    result = build_z_route(start, end, 3, "horizontal")
    assert result == [Point2D(0, 0), Point2D(0, 3), Point2D(4, 3), Point2D(4, 6)]
    assert result[0] is start
    assert result[-1] is end
    for first, second in zip(result, result[1:]):
        assert first != second
        assert segment_orientation(first, second, tol=0.0) != "other"


def test_z_vertical():
    start, end = Point2D(0, 0), Point2D(6, 4)
    result = build_z_route(start, end, 3, "vertical")
    assert result == [Point2D(0, 0), Point2D(3, 0), Point2D(3, 4), Point2D(6, 4)]
    assert result[0] is start
    assert result[-1] is end
    for first, second in zip(result, result[1:]):
        assert first != second
        assert segment_orientation(first, second, tol=0.0) != "other"


from math import pi, isclose, hypot
from copy import deepcopy
from src.models import Route, Point3D, LineSegment2D, ArcSegment2D, SmoothedRoute2D
from src.geometry import (
    line_segment_length, arc_segment_radius, arc_segment_length,
    validate_arc_segment_2d, validate_smoothed_route_2d,
    smooth_orthogonal_route_2d, smoothed_route_length,
)


def test_analytic_lengths_and_directions():
    for sign in (1,-1):
        a=ArcSegment2D(Point2D(1,0),Point2D(0,sign),Point2D(0,0),sign*pi/2)
        validate_arc_segment_2d(a)
        assert arc_segment_radius(a)==1
        assert isclose(arc_segment_length(a),pi/2)
    assert line_segment_length(LineSegment2D(Point2D(0,0),Point2D(3,4)))==5


def test_invalid_arcs():
    base=ArcSegment2D(Point2D(1,0),Point2D(0,1),Point2D(0,0),pi/2)
    for key,value in (("end",Point2D(0,2)),("sweep_rad",0),("sweep_rad",pi+0.01),
                      ("sweep_rad",float("nan")),("center",Point2D(1,0)),
                      ("sweep_rad",-pi/2),("start",Point2D(float("inf"),0))):
        a=deepcopy(base);setattr(a,key,value)
        with raises(ValueError):
            validate_arc_segment_2d(a)


def test_left_right_smoothing_and_tangents():
    for sign in (1,-1):
        source=Route(42,[Point2D(0,0),Point2D(4,0),Point2D(4,sign*4)])
        before=deepcopy(source)
        result=smooth_orthogonal_route_2d(source,1)
        assert source==before and result.waveguide_id==42
        first,arc,last=result.segments
        assert first.start==source.points[0] and last.end==source.points[-1]
        assert isclose(arc_segment_radius(arc),1)
        assert arc.sweep_rad==sign*pi/2
        # Directed circle tangent: sign(sweep) * rotate90(radius vector).
        for point,line in ((arc.start,first),(arc.end,last)):
            tangent=(-sign*(point.y-arc.center.y),sign*(point.x-arc.center.x))
            vector=(line.end.x-line.start.x,line.end.y-line.start.y)
            length=hypot(*vector)
            assert isclose(tangent[0],vector[0]/length,abs_tol=1e-9)
            assert isclose(tangent[1],vector[1]/length,abs_tol=1e-9)
        assert isclose(smoothed_route_length(result),6+pi/2)
        validate_smoothed_route_2d(result)


def test_u_z_smoothing():
    for points in (build_u_route(Point2D(0,10),Point2D(10,10),3,"top"),
                   build_z_route(Point2D(0,0),Point2D(10,10),5,"horizontal")):
        source=Route(1,points)
        result=smooth_orthogonal_route_2d(source,2)
        assert sum(isinstance(s,ArcSegment2D) for s in result.segments)==2
        assert sum(isinstance(s,LineSegment2D) for s in result.segments)==3
        length=sum(distance(a,b) for a,b in zip(points,points[1:]))
        assert isclose(smoothed_route_length(result),length-8+2*pi)


def test_equal_middle_length_omits_line():
    source=Route(1,[Point2D(0,0),Point2D(0,3),Point2D(2,3),Point2D(2,6)])
    result=smooth_orthogonal_route_2d(source,1)
    assert [type(s) for s in result.segments]==[LineSegment2D,ArcSegment2D,ArcSegment2D,LineSegment2D]
    assert result.segments[1].end==result.segments[2].start
    validate_smoothed_route_2d(result)


def test_equal_outer_length_omits_lines():
    source=Route(1,[Point2D(0,0),Point2D(1,0),Point2D(1,1)])
    result=smooth_orthogonal_route_2d(source,1)
    assert len(result.segments)==1 and isinstance(result.segments[0],ArcSegment2D)
    assert result.segments[0].start==source.points[0]
    assert result.segments[0].end==source.points[-1]


def test_insufficient_lengths():
    for points in ([Point2D(0,0),Point2D(.5,0),Point2D(.5,3)],
                   [Point2D(0,0),Point2D(0,3),Point2D(1,3),Point2D(1,6)]):
        with raises(ValueError):
            smooth_orthogonal_route_2d(Route(1,points),1)


def test_invalid_smoothing_inputs():
    for points in ([Point2D(0,0),Point2D(1,1)],
                   [Point2D(0,0),Point2D(3,0),Point2D(1,0)],
                   [Point2D(0,0),Point2D(0,0)],
                   [None], [Point3D(0,0,0)], [Point2D(0,0)]):
        with raises(ValueError):
            smooth_orthogonal_route_2d(Route(1,points),1)
    for radius in (0,-1,float("inf")):
        with raises(ValueError):
            smooth_orthogonal_route_2d(Route(1,[Point2D(0,0),Point2D(3,0)]),radius)


def test_smoothed_validation_errors():
    for segments in ([LineSegment2D(Point2D(0,0),Point2D(0,0))],
                     [LineSegment2D(Point2D(0,0),Point2D(1,0)),LineSegment2D(Point2D(2,0),Point2D(3,0))],
                     [object()]):
        with raises(ValueError):
            validate_smoothed_route_2d(SmoothedRoute2D(1,segments))


def test_empty_and_collinear_smoothing():
    empty=smooth_orthogonal_route_2d(Route(1,[]),1)
    validate_smoothed_route_2d(empty)
    assert smoothed_route_length(empty)==0
    result=smooth_orthogonal_route_2d(Route(1,[Point2D(0,0),Point2D(1,0),Point2D(3,0)]),1)
    assert result.segments==[LineSegment2D(Point2D(0,0),Point2D(3,0))]


from src.geometry import build_special_z_smoothed_route_2d


def special_z_checks(result, start, end, radius):
    assert result.segments[0].start==start and result.segments[-1].end==end
    validate_smoothed_route_2d(result)
    arcs=[s for s in result.segments if isinstance(s,ArcSegment2D)]
    assert len(arcs)==2
    q=1 if end.y>start.y else -1
    e=1 if end.x>start.x else -1
    assert arcs[0].sweep_rad*(-e*q)>0 and arcs[1].sweep_rad*(e*q)>0
    tangents=[]
    for s in result.segments:
        if isinstance(s,LineSegment2D):
            length=line_segment_length(s)
            v=((s.end.x-s.start.x)/length,(s.end.y-s.start.y)/length)
            tangents.append((v,v))
        else:
            assert isclose(arc_segment_radius(s),radius,abs_tol=1e-9,rel_tol=0)
            assert isclose(distance(s.end,s.center),radius,abs_tol=1e-9,rel_tol=0)
            sign=1 if s.sweep_rad>0 else -1
            tangents.append(tuple((-sign*(p.y-s.center.y)/radius,sign*(p.x-s.center.x)/radius)
                                  for p in (s.start,s.end)))
    for a,b in zip(tangents,tangents[1:]):
        assert all(isclose(x,y,abs_tol=1e-9,rel_tol=0) for x,y in zip(a[1],b[0]))
    assert all(isclose(x,y,abs_tol=1e-9,rel_tol=0) for x,y in zip(tangents[0][0],(0,q)))
    assert all(isclose(x,y,abs_tol=1e-9,rel_tol=0) for x,y in zip(tangents[-1][1],(0,q)))
    assert __import__('math').isfinite(smoothed_route_length(result)) and smoothed_route_length(result)>0


def test_special_z_up_right():
    start,end=Point2D(0,0),Point2D(4,20)
    before=deepcopy((start,end))
    result=build_special_z_smoothed_route_2d(12,start,end,5)
    special_z_checks(result,start,end,5)
    assert result.waveguide_id==12 and (start,end)==before


def test_special_z_up_left():
    start,end=Point2D(0,0),Point2D(-4,20)
    before=deepcopy((start,end))
    result=build_special_z_smoothed_route_2d(12,start,end,5)
    special_z_checks(result,start,end,5)
    assert result.waveguide_id==12 and (start,end)==before


def test_special_z_down_right():
    start,end=Point2D(0,0),Point2D(4,-20)
    before=deepcopy((start,end))
    result=build_special_z_smoothed_route_2d(12,start,end,5)
    special_z_checks(result,start,end,5)
    assert result.waveguide_id==12 and (start,end)==before


def test_special_z_down_left():
    start,end=Point2D(0,0),Point2D(-4,-20)
    before=deepcopy((start,end))
    result=build_special_z_smoothed_route_2d(12,start,end,5)
    special_z_checks(result,start,end,5)
    assert result.waveguide_id==12 and (start,end)==before


def test_special_z_small_and_near_threshold():
    for dx in (1e-8,10-1e-8):
        a,b=Point2D(0,0),Point2D(dx,20)
        special_z_checks(build_special_z_smoothed_route_2d(1,a,b,5),a,b,5)


def test_special_z_invalid_conditions():
    for end,r in ((Point2D(0,20),5),(Point2D(1e-10,20),5),
                  (Point2D(10,20),5),(Point2D(11,20),5),
                  (Point2D(4,1),5),(Point2D(4,0),5),
                  (Point2D(4,20),0),(Point2D(4,20),float("nan"))):
        with raises(ValueError):
            build_special_z_smoothed_route_2d(1,Point2D(0,0),end,r)


def test_special_z_mirror_and_reversal():
    a,b=Point2D(0,0),Point2D(4,20)
    r=build_special_z_smoothed_route_2d(1,a,b,5)
    mirror=build_special_z_smoothed_route_2d(1,Point2D(0,0),Point2D(-4,20),5)
    for s,t in zip(r.segments,mirror.segments):
        assert s.start.x==-t.start.x and s.start.y==t.start.y
        if isinstance(s,ArcSegment2D):
            assert s.sweep_rad==-t.sweep_rad
    reverse=build_special_z_smoothed_route_2d(1,b,a,5)
    for s,t in zip(r.segments,reversed(reverse.segments)):
        assert s.start==t.end and s.end==t.start
        if isinstance(s,ArcSegment2D):
            assert s.center==t.center and s.sweep_rad==-t.sweep_rad
    assert isclose(smoothed_route_length(r),smoothed_route_length(reverse))


def test_special_z_exact_vertical_fit():
    # r=5, dx=2 gives h=3, so vertical separation=6 leaves no lines.
    a,b=Point2D(0,0),Point2D(2,6)
    r=build_special_z_smoothed_route_2d(1,a,b,5)
    assert len(r.segments)==2
    special_z_checks(r,a,b,5)
