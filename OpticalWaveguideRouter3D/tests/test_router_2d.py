"""二维 Router 的编排和输入检查测试。"""

from unittest import TestCase

from src.models import Point2D, Point3D, Port, Route, Waveguide
from src.router_2d import route_waveguide_2d

raises = TestCase().assertRaises


def make_waveguide(
    start: Point2D | Point3D | None, end: Point2D | Point3D | None, waveguide_id: int = 10
) -> Waveguide:
    """构造测试端口；运行时允许二维点，保留现有模型注解不变。"""
    return Waveguide(
        id=waveguide_id,
        start_port=Port(id=1, pmt_id=10, local_id=0, position=start),
        end_port=Port(id=2, pmt_id=20, local_id=0, position=end),
    )


def test_invalid_route_type():
    waveguide = make_waveguide(Point2D(0, 0), Point2D(4, 4))
    with raises(ValueError):
        route_waveguide_2d(waveguide, "invalid", 2, "left")


def test_invalid_u_side():
    waveguide = make_waveguide(Point2D(0, 0), Point2D(0, 4))
    with raises(ValueError):
        route_waveguide_2d(waveguide, "u", 2, "invalid")


def test_missing_u_side():
    with raises(ValueError):
        route_waveguide_2d(make_waveguide(Point2D(0, 0), Point2D(0, 4)), "u", 2)


def test_invalid_z_orientation():
    with raises(ValueError):
        route_waveguide_2d(make_waveguide(Point2D(0, 0), Point2D(4, 4)), "z", 2, "left")


def test_missing_z_orientation():
    with raises(ValueError):
        route_waveguide_2d(make_waveguide(Point2D(0, 0), Point2D(4, 4)), "z", 2)


def test_rejects_3d_start():
    with raises(TypeError):
        route_waveguide_2d(make_waveguide(Point3D(0, 0, 0), Point2D(4, 4)), "z", 2, "vertical")


def test_rejects_3d_end():
    with raises(TypeError):
        route_waveguide_2d(make_waveguide(Point2D(0, 0), Point3D(4, 4, 0)), "z", 2, "vertical")


def test_special_z_not_implemented():
    with raises(NotImplementedError):
        route_waveguide_2d(make_waveguide(Point2D(0, 0), Point2D(4, 4)), "special_z", 2)


def test_same_pmt_pair_preserves_waveguide_ids():
    first = make_waveguide(Point2D(0, 0), Point2D(4, 4), 100)
    second = Waveguide(
        id=101,
        start_port=Port(id=3, pmt_id=10, local_id=1, position=Point2D(0, 1)),
        end_port=Port(id=4, pmt_id=20, local_id=1, position=Point2D(4, 5)),
    )
    first_route = route_waveguide_2d(first, "z", 2, "vertical")
    second_route = route_waveguide_2d(second, "z", 3, "vertical")
    assert first_route.waveguide_id == 100
    assert second_route.waveguide_id == 101
    assert first_route is not second_route


def test_u_left():
    start, end = Point2D(0,0), Point2D(0,4)
    waveguide = make_waveguide(start, end)
    route = route_waveguide_2d(waveguide, "u", 2, "left")
    assert isinstance(route, Route)
    assert route.waveguide_id == waveguide.id
    assert route.points == [Point2D(0,0), Point2D(2,0), Point2D(2,4), Point2D(0,4)]
    assert route.points[0] is start
    assert route.points[-1] is end
    assert waveguide.start_port.position is start
    assert waveguide.end_port.position is end
    for first, second in zip(route.points, route.points[1:]):
        assert first != second
        assert first.x == second.x or first.y == second.y


def test_u_right():
    start, end = Point2D(4,0), Point2D(4,4)
    waveguide = make_waveguide(start, end)
    route = route_waveguide_2d(waveguide, "u", 2, "right")
    assert isinstance(route, Route)
    assert route.waveguide_id == waveguide.id
    assert route.points == [Point2D(4,0), Point2D(2,0), Point2D(2,4), Point2D(4,4)]
    assert route.points[0] is start
    assert route.points[-1] is end
    assert waveguide.start_port.position is start
    assert waveguide.end_port.position is end
    for first, second in zip(route.points, route.points[1:]):
        assert first != second
        assert first.x == second.x or first.y == second.y


def test_u_top():
    start, end = Point2D(0,4), Point2D(4,4)
    waveguide = make_waveguide(start, end)
    route = route_waveguide_2d(waveguide, "u", 2, "top")
    assert isinstance(route, Route)
    assert route.waveguide_id == waveguide.id
    assert route.points == [Point2D(0,4), Point2D(0,2), Point2D(4,2), Point2D(4,4)]
    assert route.points[0] is start
    assert route.points[-1] is end
    assert waveguide.start_port.position is start
    assert waveguide.end_port.position is end
    for first, second in zip(route.points, route.points[1:]):
        assert first != second
        assert first.x == second.x or first.y == second.y


def test_u_bottom():
    start, end = Point2D(0,0), Point2D(4,0)
    waveguide = make_waveguide(start, end)
    route = route_waveguide_2d(waveguide, "u", 2, "bottom")
    assert isinstance(route, Route)
    assert route.waveguide_id == waveguide.id
    assert route.points == [Point2D(0,0), Point2D(0,2), Point2D(4,2), Point2D(4,0)]
    assert route.points[0] is start
    assert route.points[-1] is end
    assert waveguide.start_port.position is start
    assert waveguide.end_port.position is end
    for first, second in zip(route.points, route.points[1:]):
        assert first != second
        assert first.x == second.x or first.y == second.y


def test_z_horizontal():
    start, end = Point2D(0,0), Point2D(4,6)
    waveguide = make_waveguide(start, end)
    route = route_waveguide_2d(waveguide, "z", 3, "horizontal")
    assert isinstance(route, Route)
    assert route.waveguide_id == waveguide.id
    assert route.points == [Point2D(0,0), Point2D(0,3), Point2D(4,3), Point2D(4,6)]
    assert route.points[0] is start
    assert route.points[-1] is end
    assert waveguide.start_port.position is start
    assert waveguide.end_port.position is end
    for first, second in zip(route.points, route.points[1:]):
        assert first != second
        assert first.x == second.x or first.y == second.y


def test_z_vertical():
    start, end = Point2D(0,0), Point2D(6,4)
    waveguide = make_waveguide(start, end)
    route = route_waveguide_2d(waveguide, "z", 3, "vertical")
    assert isinstance(route, Route)
    assert route.waveguide_id == waveguide.id
    assert route.points == [Point2D(0,0), Point2D(3,0), Point2D(3,4), Point2D(6,4)]
    assert route.points[0] is start
    assert route.points[-1] is end
    assert waveguide.start_port.position is start
    assert waveguide.end_port.position is end
    for first, second in zip(route.points, route.points[1:]):
        assert first != second
        assert first.x == second.x or first.y == second.y


from copy import deepcopy
from dataclasses import fields
from unittest.mock import patch
from src.router_2d import RoutePreparation, prepare_waveguide_2d, prepare_waveguides_2d


def test_prepare_top():
    w = make_waveguide(Point2D(1, 10), Point2D(3, 10), 42)
    assert prepare_waveguide_2d(w, 10, -2) == RoutePreparation(42, "u", "top")


def test_prepare_bottom():
    w = make_waveguide(Point2D(1, -2), Point2D(3, -2), 42)
    assert prepare_waveguide_2d(w, 10, -2) == RoutePreparation(42, "u", "bottom")


def test_prepare_down():
    w = make_waveguide(Point2D(1, 10), Point2D(3, -2), 42)
    assert prepare_waveguide_2d(w, 10, -2) == RoutePreparation(42, "z", None)


def test_prepare_up():
    w = make_waveguide(Point2D(1, -2), Point2D(3, 10), 42)
    assert prepare_waveguide_2d(w, 10, -2) == RoutePreparation(42, "z", None)


def test_prepare_tolerance():
    w = make_waveguide(Point2D(1, 10.0001), Point2D(3, -2.0001))
    assert prepare_waveguide_2d(w, 10, -2, tol=0.001).route_type == "z"
    with raises(ValueError):
        prepare_waveguide_2d(w, 10, -2, tol=0.00001)


def test_prepare_missing_positions():
    for start, end in ((None, Point2D(1, 0)), (Point2D(1, 10), None)):
        with raises(TypeError):
            prepare_waveguide_2d(make_waveguide(start, end), 10, 0)


def test_prepare_rejects_3d():
    for start, end in ((Point3D(0, 10, 0), Point2D(1, 0)),
                       (Point2D(0, 10), Point3D(1, 0, 0))):
        with raises(TypeError):
            prepare_waveguide_2d(make_waveguide(start, end), 10, 0)


def test_prepare_off_boundary():
    for start, end in ((Point2D(0, 5), Point2D(1, 0)),
                       (Point2D(0, 10), Point2D(1, 5))):
        with raises(ValueError):
            prepare_waveguide_2d(make_waveguide(start, end), 10, 0)


def test_prepare_invalid_boundaries():
    for top, bottom, tol in ((0, 0, 0), (0, 10, 0), (1, 0, 0.5),
                             (10, 0, -1), (float("nan"), 0, 0),
                             (10, 0, float("inf"))):
        with raises(ValueError):
            prepare_waveguides_2d([], top, bottom, tol)


def test_prepare_nonfinite_point():
    with raises(ValueError):
        prepare_waveguide_2d(make_waveguide(Point2D(float("nan"), 10), Point2D(1, 0)), 10, 0)


def test_prepare_batch_order_and_no_mutation():
    waveguides = [
        make_waveguide(Point2D(1, 10), Point2D(2, 10), 30),
        make_waveguide(Point2D(1, 0), Point2D(2, 0), 10),
        make_waveguide(Point2D(1, 10), Point2D(2, 0), 20),
    ]
    before = deepcopy(waveguides)
    result = prepare_waveguides_2d(waveguides, 10, 0)
    assert [p.waveguide_id for p in result] == [30, 10, 20]
    assert waveguides == before
    assert prepare_waveguides_2d([], 10, 0) == []


def test_prepare_has_no_track_or_geometry_calls():
    assert [f.name for f in fields(RoutePreparation)] == ["waveguide_id", "route_type", "side"]
    with patch("src.router_2d.build_u_route", side_effect=AssertionError("geometry called")), \
         patch("src.router_2d.build_z_route", side_effect=AssertionError("geometry called")), \
         patch("src.router_2d.build_special_z_route", side_effect=AssertionError("special Z called")):
        for y in (0, 10):
            for end_y in (0, 10):
                prepare_waveguide_2d(make_waveguide(Point2D(1, y), Point2D(2, end_y)), 10, 0)


from math import isclose
from src.router_2d import (
    TrackPolicyConfig, build_track_grid_2d, assign_tracks_2d, _algorithmic_endpoints,
)


def alloc_waveguide(identifier, x1, y1, x2, y2, pmt1=1, pmt2=2):
    return Waveguide(identifier, Port(2*identifier, pmt1, None, Point2D(x1, y1)),
                     Port(2*identifier+1, pmt2, None, Point2D(x2, y2)))


def allocate_sample(ws, config):
    return assign_tracks_2d(ws, prepare_waveguides_2d(ws, config.board_height, 0), config)


def test_grid_legacy():
    grid = build_track_grid_2d(TrackPolicyConfig(150, 0.05, 0.125, 5))
    assert len(grid) == 800
    assert isclose(grid[0], 5.025)
    assert isclose(grid[-1], 144.85)
    assert grid[-1] <= 144.975


def test_grid_float_boundary_and_single_track():
    assert len(build_track_grid_2d(TrackPolicyConfig(0.7, 0.1, 0.1, 0))) == 4
    assert build_track_grid_2d(TrackPolicyConfig(3, 1, 0, 1)) == [1.5]


def test_grid_invalid_configs():
    for args in ((0,1,0,0),(10,0,0,0),(10,1,-1,0),(10,1,0,-1),
                 (10,1,0,0,-1),(2,1,0,1),(float("inf"),1,0,0),
                 (10,1,float("nan"),0)):
        with raises(ValueError):
            build_track_grid_2d(TrackPolicyConfig(*args))


def test_algorithmic_u_left_and_tie():
    w = alloc_waveguide(1, 5, 10, 1, 10)
    prep = prepare_waveguide_2d(w,10,0)
    assert _algorithmic_endpoints(w,prep,1e-9)[0] is w.end_port
    w = alloc_waveguide(1, 1, 10, 1+1e-10, 10, 5, 2)
    assert _algorithmic_endpoints(w,prep,1e-9)[0] is w.end_port
    w = Waveguide(1, Port(5,2,None,Point2D(1,10)),Port(3,2,None,Point2D(1,10)))
    assert _algorithmic_endpoints(w,prep,1e-9)[0] is w.end_port


def test_algorithmic_z_lexicographic():
    w = alloc_waveguide(1,1,10,4,0,8,2)
    assert _algorithmic_endpoints(w,prepare_waveguide_2d(w,10,0),1e-9)[0] is w.end_port


def test_allocator_all_groups_and_scanning():
    cfg=TrackPolicyConfig(10,1,0,0)
    ws=[alloc_waveguide(4,0,0,3,10),alloc_waveguide(2,0,0,3,0),
        alloc_waveguide(3,0,10,3,0),alloc_waveguide(1,0,10,3,10)]
    result=allocate_sample(ws,cfg)
    assert [r.waveguide_id for r in result]==[4,2,3,1]
    assert {r.waveguide_id:r.track_index for r in result}=={1:9,2:0,3:8,4:7}


def test_allocator_sort_order_repeatability_and_no_mutation():
    cfg=TrackPolicyConfig(10,1,0,0)
    ws=[alloc_waveguide(4,5,10,1,10),alloc_waveguide(2,1,10,5,10),
        alloc_waveguide(3,0,10,5,10)]
    before=deepcopy(ws)
    first=allocate_sample(ws,cfg)
    other=allocate_sample(list(reversed(ws)),cfg)
    assert {r.waveguide_id:r for r in first}=={r.waveguide_id:r for r in other}
    assert {r.waveguide_id:r.track_index for r in first}=={3:9,2:8,4:7}
    assert ws==before


def test_span_unsupported_equal_and_no_occupancy():
    cfg=TrackPolicyConfig(5,1,0,1)
    ws=[alloc_waveguide(1,0,5,1,5),alloc_waveguide(2,0,5,2,5),
        alloc_waveguide(3,0,5,1,0),alloc_waveguide(4,0,5,2,0)]
    rs=allocate_sample(ws,cfg)
    assert [r.status for r in rs]==["unsupported_u_bend_span","assigned","unsupported_geometry","assigned"]
    assert [r.track_index for r in rs]==[None,2,None,1]
    assert all(r.track_y is None for r in (rs[0],rs[2]))


def test_span_tolerance():
    ws=[alloc_waveguide(1,0,5,2-1e-10,0)]
    assert allocate_sample(ws,TrackPolicyConfig(5,1,0,1))[0].status=="assigned"


def test_exhaustion_and_no_interval_reuse():
    cfg=TrackPolicyConfig(1,1,0,0)
    ws=[alloc_waveguide(1,0,1,1,1),alloc_waveguide(2,10,1,11,1)]
    rs=allocate_sample(ws,cfg)
    assert [r.status for r in rs]==["assigned","no_available_track"]
    assert rs[0].track_index==0 and rs[1].track_index is None
    assert len(rs)==len(ws)


def test_allocator_ids_and_preparation_consistency():
    cfg=TrackPolicyConfig(10,1,0,0)
    w=alloc_waveguide(1,0,10,3,10)
    p=prepare_waveguide_2d(w,10,0)
    for ws,ps in (([w,w],[p]),([w],[p,p]),([w],[]),
                  ([w],[RoutePreparation(2,"u","top")]),
                  ([w],[RoutePreparation(1,"u","bottom")]),
                  ([w],[RoutePreparation(1,"z",None)])):
        with raises(ValueError):
            assign_tracks_2d(ws,ps,cfg)


def test_allocator_rejects_invalid_positions():
    cfg=TrackPolicyConfig(10,1,0,0)
    for pos in (None,Point3D(0,10,0),Point2D(0,5)):
        w=alloc_waveguide(1,0,10,3,10); w.start_port.position=pos
        with raises((TypeError,ValueError)):
            assign_tracks_2d([w],[RoutePreparation(1,"u","top")],cfg)


def test_allocator_does_not_call_geometry_or_route():
    cfg=TrackPolicyConfig(10,1,0,0)
    with patch("src.router_2d.build_u_route",side_effect=AssertionError), \
         patch("src.router_2d.build_z_route",side_effect=AssertionError), \
         patch("src.router_2d.build_special_z_route",side_effect=AssertionError), \
         patch("src.router_2d.route_waveguide_2d",side_effect=AssertionError):
        rs=allocate_sample([alloc_waveguide(1,0,10,3,0)],cfg)
        assert rs[0].status=="assigned"
    assert assign_tracks_2d([],[],cfg)==[]


from src.router_2d import TrackAssignment, generate_assigned_routes_2d


def generation(ws, assignments, preparations=None):
    return generate_assigned_routes_2d(
        ws, prepare_waveguides_2d(ws,10,0) if preparations is None else preparations,
        assignments, top_y=10, bottom_y=0,
    )


def test_generation_templates_direction_and_immutability():
    ws=[alloc_waveguide(3,8,10,2,10),alloc_waveguide(1,8,0,2,0),
        alloc_waveguide(2,8,0,2,10)]
    aa=[TrackAssignment(w.id,"assigned",i,4+i,None) for i,w in enumerate(ws)]
    before=deepcopy((ws,aa))
    routes=generation(ws,list(reversed(aa)))
    assert [r.waveguide_id for r in routes]==[3,1,2]
    for r,w,a in zip(routes,ws,aa):
        assert r.points==[w.start_port.position,Point2D(8,a.track_y),
                          Point2D(2,a.track_y),w.end_port.position]
        assert r.points[0] == w.start_port.position
        assert r.points[-1] == w.end_port.position
    assert (ws,aa)==before


def test_generation_delegates_and_never_calls_collision_or_allocator():
    w=alloc_waveguide(1,0,0,3,10)
    a=TrackAssignment(1,"assigned",0,5,None)
    with patch("src.router_2d.route_waveguide_2d", wraps=route_waveguide_2d) as route_call, \
         patch("src.router_2d.assign_tracks_2d",side_effect=AssertionError), \
         patch("src.router_2d.build_special_z_route",side_effect=AssertionError), \
         patch("src.collision.find_route_intersections",side_effect=AssertionError), \
         patch("src.collision.find_self_intersections",side_effect=AssertionError):
        generation([w],[a])
        route_call.assert_called_once_with(w,"z",5,"horizontal")


def test_generation_normalized_point_count():
    w=alloc_waveguide(1,0,0,3,10)
    result=generation([w],[TrackAssignment(1,"assigned",0,0,None)])
    assert result[0].points==[Point2D(0,0),Point2D(3,0),Point2D(3,10)]


def test_generation_skips_all_failure_statuses():
    ws=[alloc_waveguide(i,0,10,3,0) for i in range(3)]
    statuses=["unsupported_geometry","unsupported_u_bend_span","no_available_track"]
    aa=[TrackAssignment(i,s,None,None,s) for i,s in enumerate(statuses)]
    with patch("src.router_2d.route_waveguide_2d",side_effect=AssertionError):
        assert generation(ws,aa)==[]


def test_generation_missing_or_invalid_track():
    w=alloc_waveguide(1,0,10,3,0)
    for index,y in ((None,5),(0,None),(-1,5),(0,float("nan")),(0,11)):
        with raises(ValueError):
            generation([w],[TrackAssignment(1,"assigned",index,y,None)])


def test_generation_id_validation():
    w=alloc_waveguide(1,0,10,3,0)
    p=RoutePreparation(1,"z",None)
    a=TrackAssignment(1,"assigned",0,5,None)
    for ws,ps,aa in (([w,w],[p],[a]),([w],[p,p],[a]),([w],[p],[a,a]),
                     ([w],[],[a]),([w],[p],[]),
                     ([w],[p],[TrackAssignment(2,"assigned",0,5,None)])):
        with raises(ValueError):
            generation(ws,aa,ps)


def test_generation_rejects_bad_preparation_and_positions():
    w=alloc_waveguide(1,0,10,3,0)
    a=TrackAssignment(1,"assigned",0,5,None)
    with raises(ValueError):
        generation([w],[a],[RoutePreparation(1,"u","top")])
    for pos in (None,Point3D(0,10,0)):
        w.start_port.position=pos
        with raises(ValueError):
            generation([w],[a],[RoutePreparation(1,"z",None)])


def test_generation_invalid_failure_state():
    w=alloc_waveguide(1,0,10,3,0)
    for a in (TrackAssignment(1,"unknown",None,None,None),
              TrackAssignment(1,"unsupported_geometry",0,5,None)):
        with raises(ValueError):
            generation([w],[a])
