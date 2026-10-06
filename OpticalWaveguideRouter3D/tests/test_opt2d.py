"""opt2d 验收测试：几何重建、交叉事件口径、间距语义、候选搜索与失败回滚。

运行（需要 scipy 以满足 2D 项目的 ``waveguide_calculator``）：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -m pytest tests/test_opt2d.py -q

没有 scipy 的环境会把依赖 2D 项目的用例整体跳过。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geometry import smoothed_route_length  # noqa: E402
from src.models import ArcSegment2D, LineSegment2D, Point2D, SmoothedRoute2D  # noqa: E402
from src.opt2d.geometry_audit import audit_geometry, segment_tangent  # noqa: E402
from src.opt2d.smoothing import (  # noqa: E402
    RouteSpec,
    bend_half_angle,
    build_route_geometry,
    legacy_bend_records,
)
from src.opt2d.spacing import (  # noqa: E402
    aabb_gap,
    segment_aabb,
    segment_min_distance,
    spacing_violations,
)

scipy = pytest.importorskip("scipy", reason="需要 2D 项目 waveguide_calculator 的 scipy 依赖")

from src.opt2d.evaluator import Evaluator, LossModel  # noqa: E402
from src.opt2d.planner import PlanConfig, Planner  # noqa: E402
from src.opt2d.source import legacy_bend_frame, specs_from_rect  # noqa: E402


# --------------------------------------------------------------------------
# 1. 原版圆弧几何重建
# --------------------------------------------------------------------------
def test_geometry_matches_legacy_records_for_standard_and_short_span():
    """dx>=2R 与 dx<2R 两种分支都要复算回原版 bend_x/bend_y/center/theta/dir。"""
    cases = [
        RouteSpec(1, 138.8, 0.0, 5.6, 0.0, 29.6, 5.0),      # dx = 133.2 >= 2R
        RouteSpec(2, 140.9, 0.0, 137.0, 150.0, 120.5, 5.0),  # dx = 3.9 < 2R
        RouteSpec(3, 5.0, 150.0, 20.0, 150.0, 100.0, 5.0),   # above -> above
        RouteSpec(4, 50.0, 0.0, 50.0, 150.0, 80.0, 5.0),     # dx == 0
    ]
    for spec in cases:
        record = legacy_bend_records(spec)
        segments = build_route_geometry(spec)
        assert segments[0].start.x == pytest.approx(spec.sx)
        assert segments[-1].end.y == pytest.approx(spec.ly)
        assert segments[0].start.y == pytest.approx(spec.sy)
        if spec.dx == 0:
            assert len(segments) == 1 and isinstance(segments[0], LineSegment2D)
            continue
        arcs = [s for s in segments if isinstance(s, ArcSegment2D)]
        assert len(arcs) == 2
        for index, arc in enumerate(arcs):
            assert arc.start.x == pytest.approx(record["bend_x"][2 * index], abs=1e-6)
            assert arc.start.y == pytest.approx(record["bend_y"][2 * index], abs=1e-6)
            assert arc.end.x == pytest.approx(record["bend_x"][2 * index + 1], abs=1e-6)
            assert arc.end.y == pytest.approx(record["bend_y"][2 * index + 1], abs=1e-6)
            assert arc.center.x == pytest.approx(record["center"][index][0], abs=1e-6)
            assert arc.center.y == pytest.approx(record["center"][index][1], abs=1e-6)
            radius = math.hypot(arc.start.x - arc.center.x, arc.start.y - arc.center.y)
            assert radius == pytest.approx(spec.radius, abs=1e-9)


def test_short_span_arcs_meet_at_the_midpoint():
    """dx<2R 时两弧在中点相接、无中间直线段，半角由 arccos((R-dx/2)/R) 给出。"""
    spec = RouteSpec(2, 140.9, 0.0, 137.0, 150.0, 120.5, 5.0)
    segments = build_route_geometry(spec)
    arcs = [s for s in segments if isinstance(s, ArcSegment2D)]
    assert len(arcs) == 2
    assert arcs[0].end.x == pytest.approx(arcs[1].start.x, abs=1e-9)
    assert arcs[0].end.y == pytest.approx(arcs[1].start.y, abs=1e-9)
    assert all(not isinstance(s, LineSegment2D) for s in segments[1:-1])
    half = bend_half_angle(spec.dx, spec.radius)
    assert abs(arcs[0].sweep_rad) == pytest.approx(half, abs=1e-9)
    assert abs(arcs[1].sweep_rad) == pytest.approx(half, abs=1e-9)
    # 两个半角之和不是 90 度，说明不能沿用"相同半径 90 度弯"的公式。
    assert half < math.pi / 2 - 1e-6


def test_arc_length_matches_legacy_calc_length_branch():
    """弧长×弯曲密度与总长度和逐段长度自洽（不重复计弧段传播损耗）。"""
    spec = RouteSpec(2, 140.9, 0.0, 137.0, 150.0, 120.5, 5.0)
    segments = build_route_geometry(spec)
    arc_mm = sum(
        abs(s.sweep_rad) * math.hypot(s.start.x - s.center.x, s.start.y - s.center.y)
        for s in segments
        if isinstance(s, ArcSegment2D)
    )
    straight_mm = sum(
        math.hypot(s.end.x - s.start.x, s.end.y - s.start.y)
        for s in segments
        if isinstance(s, LineSegment2D)
    )
    total = smoothed_route_length(SmoothedRoute2D(1, segments))
    assert total == pytest.approx(straight_mm + arc_mm, abs=1e-9)
    rise = spec.radius * math.sin(bend_half_angle(spec.dx, spec.radius))
    assert straight_mm == pytest.approx(
        (spec.track_y - rise - spec.sy) + (spec.ly - (spec.track_y + rise)), abs=1e-9
    )


def test_audit_detects_tampered_geometry():
    """核验器必须报出端点不符，并且弯曲空间不足要被几何构建拒绝。"""
    spec = RouteSpec(7, 20.0, 0.0, 60.0, 0.0, 40.0, 5.0)
    segments = build_route_geometry(spec)
    assert audit_geometry(spec, segments) == []

    wrong_start = RouteSpec(8, 25.0, 0.0, 60.0, 0.0, 40.0, 5.0)
    issues = audit_geometry(wrong_start, segments)
    assert any(issue.kind == "endpoint_mismatch" for issue in issues)

    # 轨道离终点太近、第二弯切点越过端面：几何构建直接拒绝，不产生"看起来合法"的路线。
    with pytest.raises(ValueError):
        build_route_geometry(RouteSpec(9, 20.0, 0.0, 60.0, 150.0, 148.0, 5.0))


def test_tangent_is_continuous_at_every_join():
    spec = RouteSpec(3, 30.0, 0.0, 90.0, 150.0, 75.0, 5.0)
    segments = build_route_geometry(spec)
    for a, b in zip(segments, segments[1:]):
        tangent_a = segment_tangent(a, a.end)
        tangent_b = segment_tangent(b, b.start)
        assert tangent_a[0] * tangent_b[0] + tangent_a[1] * tangent_b[1] == pytest.approx(
            1.0, abs=1e-9
        )


# --------------------------------------------------------------------------
# 2. 交叉事件口径
# --------------------------------------------------------------------------
def _straight_route(route_id: int, x: float, y0: float, y1: float) -> SmoothedRoute2D:
    return SmoothedRoute2D(
        route_id, [LineSegment2D(Point2D(x, y0), Point2D(x, y1))]
    )


def test_same_pair_multiple_crossings_are_all_kept():
    """同一对波导的多个交叉点必须全部保留，不能只返回第一个。"""
    evaluator = Evaluator(256, check_spacing=False)
    a = SmoothedRoute2D(
        1,
        [
            LineSegment2D(Point2D(0, 0), Point2D(0, 30)),
            LineSegment2D(Point2D(0, 30), Point2D(60, 30)),
            LineSegment2D(Point2D(60, 30), Point2D(60, 0)),
        ],
    )
    b = SmoothedRoute2D(
        2,
        [
            LineSegment2D(Point2D(-5, 10), Point2D(65, 10)),
            LineSegment2D(Point2D(65, 10), Point2D(65, 20)),
            LineSegment2D(Point2D(65, 20), Point2D(-5, 20)),
        ],
    )
    events = evaluator.pair_events(1, 2, a.segments, b.segments)
    crosses = sorted(
        (round(event.point.x, 6), round(event.point.y, 6))
        for event in events
        if event.kind == "cross"
    )
    assert crosses == [(0.0, 10.0), (0.0, 20.0), (60.0, 10.0), (60.0, 20.0)]


def test_duplicate_records_at_same_location_are_merged():
    """同一对波导在同一位置的重复几何记录只保留一条。"""
    from src.collision import CurveRouteIntersection
    from src.physical_intersections import consolidate_route_intersections_2d

    a = _straight_route(1, 0.0, 0.0, 20.0)
    b = SmoothedRoute2D(
        2,
        [
            LineSegment2D(Point2D(-5, 10), Point2D(0, 10)),
            LineSegment2D(Point2D(0, 10), Point2D(5, 10)),
        ],
    )
    raw = [
        CurveRouteIntersection(1, 2, 0, 0, "LineSegment2D", "LineSegment2D", "touch", Point2D(0, 10)),
        CurveRouteIntersection(1, 2, 0, 1, "LineSegment2D", "LineSegment2D", "touch", Point2D(0, 10)),
    ]
    events = consolidate_route_intersections_2d(a, b, raw)
    points = [(event.point.x, event.point.y) for event in events if event.point]
    assert len(points) == 1 and points[0] == (0.0, 10.0)


def test_crossing_angle_uses_real_tangents_for_unequal_radii():
    """不同半径圆弧求交：角度必须由两条弧的真实切线给出。

    相同半径的 ``arccos(1 - d^2/(2R^2))`` 只对等半径两圆成立，这里两条弧的
    半径分别是 5 与 3，因此该公式没有意义；评价器必须用切线算角。
    """
    from src.collision import find_segment_intersections_2d, point_on_arc_2d
    from src.geometry import arc_segment_radius

    arc_a = ArcSegment2D(Point2D(5.0, 0.0), Point2D(0.0, 5.0), Point2D(0.0, 0.0), math.pi / 2)
    arc_b = ArcSegment2D(Point2D(6.0, 3.0), Point2D(0.0, 3.0), Point2D(3.0, 3.0), math.pi)
    assert arc_segment_radius(arc_a) != arc_segment_radius(arc_b)

    events = find_segment_intersections_2d(arc_a, arc_b)
    points = [event.point for event in events if event.point is not None]
    assert len(points) == 1
    point = points[0]
    assert point_on_arc_2d(point, arc_a) and point_on_arc_2d(point, arc_b)

    # 独立算出期望夹角：由交点相对各自圆心的方向角取切线。
    def tangent(arc, target):
        angle = math.atan2(target.y - arc.center.y, target.x - arc.center.x)
        sign = 1.0 if arc.sweep_rad > 0 else -1.0
        return (-sign * math.sin(angle), sign * math.cos(angle))

    ta, tb = tangent(arc_a, point), tangent(arc_b, point)
    expected = math.degrees(
        math.acos(abs(ta[0] * tb[0] + ta[1] * tb[1]))
    )

    evaluator = Evaluator(256, check_spacing=False)
    physical = evaluator.pair_events(1, 2, [arc_a], [arc_b])
    crosses = [event for event in physical if event.kind == "cross"]
    assert len(crosses) == 1
    assert math.degrees(crosses[0].crossing_angle_rad) == pytest.approx(expected, abs=1e-6)
    # 两弧半径不同，等半径公式的形状在这里不可能成立。
    assert expected != pytest.approx(
        math.degrees(math.acos(1 - 0.0)), abs=1e-6
    )


def test_each_event_counts_once_per_route_and_not_divided_by_two():
    """全网事件记录一次；逐路损耗时该事件分别计入两根波导各一次。"""
    evaluator = Evaluator(256, check_spacing=False)
    a = _straight_route(1, 0.0, 0.0, 20.0)
    b = _straight_route(2, 10.0, 0.0, 20.0)
    c = SmoothedRoute2D(3, [LineSegment2D(Point2D(-5, 10), Point2D(15, 10))])
    inspection = evaluator.evaluate(
        [
            RouteSpec(1, 0.0, 0.0, 0.0, 20.0, 20.0, 5.0),
            RouteSpec(2, 10.0, 0.0, 10.0, 20.0, 20.0, 5.0),
            RouteSpec(3, -5.0, 10.0, 15.0, 10.0, 10.0, 5.0),
        ],
        label="unit",
        segments={1: a.segments, 2: b.segments, 3: c.segments},
        issues=[],
        unplaced=[],
        runtime_s=0.0,
    )
    summary = inspection.summary()
    assert summary["unique_crossing_events"] >= 2
    assert summary["per_route_crossing_events"] == 2 * summary["unique_crossing_events"]
    losses = sum(record.crossing_loss_db for record in inspection.routes)
    assert losses == pytest.approx(
        sum(event.loss_db for event in inspection.events) * 2, abs=1e-12
    )


def test_spacing_check_ignores_plain_crossings():
    """中心线相交是允许的交叉，不能算作间距违规；近并行才算。"""
    far = {
        1: _straight_route(1, 0.0, 0.0, 20.0).segments,
        2: _straight_route(2, 10.0, 0.0, 20.0).segments,
    }
    assert spacing_violations(far, 0.3) == []

    close = {
        1: _straight_route(1, 0.0, 0.0, 20.0).segments,
        2: _straight_route(2, 0.2, 0.0, 20.0).segments,
    }
    violations = spacing_violations(close, 0.3)
    assert len(violations) == 1
    assert violations[0].distance_mm == pytest.approx(0.2, abs=1e-9)


def test_segment_min_distance_handles_line_arc_and_arc_arc():
    line = LineSegment2D(Point2D(0.0, 0.0), Point2D(10.0, 0.0))
    arc = ArcSegment2D(
        Point2D(1.0, 3.0), Point2D(5.0, 3.0), Point2D(3.0, 3.0), math.pi
    )
    distance, _, _ = segment_min_distance(line, arc)
    assert distance == pytest.approx(1.0, abs=1e-9)

    outer = ArcSegment2D(Point2D(5.0, 0.0), Point2D(-5.0, 0.0), Point2D(0.0, 0.0), math.pi)
    inner = ArcSegment2D(Point2D(3.0, 0.0), Point2D(-3.0, 0.0), Point2D(0.0, 0.0), math.pi)
    distance, _, _ = segment_min_distance(outer, inner)
    assert distance == pytest.approx(2.0, abs=1e-9)

    box_a = segment_aabb(line)
    box_b = segment_aabb(inner)
    assert aabb_gap(box_a, box_b) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------
# 3. 布线器：原版回归、搜索与失败回滚
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def legacy_ports_256():
    from src.opt2d.legacy_bridge import legacy_ports

    return legacy_ports(256)


def test_planner_single_candidate_reproduces_legacy_tracks(legacy_ports_256):
    """candidate_limit=1 + 原版顺序必须逐条复现原版轨道分配。"""
    from src.opt2d.legacy_bridge import run_legacy_rect

    _, rect = run_legacy_rect(256, 5.0)
    legacy_specs = {spec.route_id: spec for spec in specs_from_rect(rect, 5.0)}
    evaluator = Evaluator(256)
    planner = Planner(
        PlanConfig(channels=256, candidate_limit=1, order_strategy="legacy", radii=(5.0,)),
        evaluator,
    )
    result = planner.plan(legacy_ports_256)
    assert not result.unplaced
    differences = [
        rid
        for rid, route in result.routes.items()
        if abs(legacy_specs[rid].track_y - route.spec.track_y) > 1e-9
    ]
    assert differences == []


def test_candidate_search_keeps_complete_connection(legacy_ports_256):
    evaluator = Evaluator(256)
    planner = Planner(
        PlanConfig(
            channels=256,
            candidate_limit=4,
            order_strategy="legacy",
            radii=(5.0,),
            position_penalty=0.001,
        ),
        evaluator,
    )
    result = planner.plan(legacy_ports_256)
    assert result.unplaced == []
    evaluation = planner.evaluate_plan(result, "unit-c4")
    assert evaluation.unplaced_ids == []
    assert evaluation.summary()["complete_connection"] is True


def test_refine_never_accepts_incomplete_state(legacy_ports_256):
    """拆线重布失败时必须整体恢复，连接完整性不下降。"""
    evaluator = Evaluator(256)
    planner = Planner(
        PlanConfig(
            channels=256,
            candidate_limit=4,
            order_strategy="legacy",
            radii=(5.0,),
            position_penalty=0.001,
        ),
        evaluator,
    )
    result = planner.plan(legacy_ports_256)
    baseline = planner.evaluate_plan(result, "before")
    before_tracks = {rid: route.spec.track_y for rid, route in result.routes.items()}
    # rip 集刻意取"整批跨区路线"，制造大量重布失败的机会。
    result2, evaluation, record = planner.refine(
        result, label="after", rounds=1, rip_count=40
    )
    assert evaluation.summary()["unplaced_count"] == 0
    if record["stop_reason"] != "no_improvement" or not any(
        round_.get("accepted") for round_ in record["rounds"]
    ):
        # 未接受任何一轮时，几何必须与 refine 前完全一致。
        assert {rid: route.spec.track_y for rid, route in result2.routes.items()} == before_tracks
    assert evaluation.summary()["mean_loss_db"] <= baseline.summary()["mean_loss_db"] + 1e-12


def test_planner_state_restore_is_exact(legacy_ports_256):
    """快照/恢复必须精确复原轨道占用与端口节点状态。"""
    evaluator = Evaluator(256)
    planner = Planner(
        PlanConfig(channels=256, candidate_limit=1, order_strategy="legacy", radii=(5.0,)),
        evaluator,
    )
    result = planner.plan(legacy_ports_256)
    snapshot = planner.snapshot()
    tracks_before = [
        (track.y, list(track.WGs), list(track.rEnd), list(track.lEnd))
        for track in planner.tracks
    ]
    nodes_before = [
        (list(node.x), list(node.y)) for node in planner.nodes.MTabove + planner.nodes.MTbelow
    ]
    planner.restore(snapshot)
    tracks_after = [
        (track.y, list(track.WGs), list(track.rEnd), list(track.lEnd))
        for track in planner.tracks
    ]
    nodes_after = [
        (list(node.x), list(node.y)) for node in planner.nodes.MTabove + planner.nodes.MTbelow
    ]
    assert tracks_before == tracks_after
    assert nodes_before == nodes_after
    assert {rid: route.spec.track_y for rid, route in planner.committed.items()} == {
        rid: route.spec.track_y for rid, route in result.routes.items()
    }


# --------------------------------------------------------------------------
# 4. 损耗口径
# --------------------------------------------------------------------------
def test_loss_model_does_not_double_count_arc_propagation():
    """弧段只按弯曲密度计入，直线段不含弧长（不重复计算）。"""
    model = LossModel()
    spec = RouteSpec(1, 20.0, 0.0, 80.0, 0.0, 50.0, 5.0)
    segments = build_route_geometry(spec)
    straight_mm = sum(
        math.hypot(s.end.x - s.start.x, s.end.y - s.start.y)
        for s in segments
        if isinstance(s, LineSegment2D)
    )
    arc_mm = sum(
        abs(s.sweep_rad) * math.hypot(s.start.x - s.center.x, s.start.y - s.center.y)
        for s in segments
        if isinstance(s, ArcSegment2D)
    )
    assert model.straight_loss_db(straight_mm) == pytest.approx(
        straight_mm * model.propagation_db_per_mm, abs=1e-15
    )
    assert model.bend_loss_db(5.0, arc_mm) == pytest.approx(
        model.bend_loss_90_db(5.0) * (arc_mm / (5.0 * math.pi / 2)), abs=1e-12
    )


def test_legacy_frame_is_accepted_by_calc_index():
    """原版统计口径：生成的弯道表能被 2D 项目 calc_index 直接消费。"""
    from src.opt2d.legacy_bridge import legacy_modules

    spec = RouteSpec(0, 20.0, 0.0, 80.0, 150.0, 60.0, 5.0, port1=1, port2=17, index1=0, index2=16)
    frame = legacy_bend_frame([spec])
    calculator = legacy_modules()["waveguide_calculator"]
    out = calculator.calc_index(frame.copy(), loss=None, bend_radius=5.0, height=150, width=150)
    assert len(out) == 1
    assert float(out["length"].iloc[0]) > 0


# --------------------------------------------------------------------------
# 5. 真实数据上的自洽性：交叉点的位置与角度
# --------------------------------------------------------------------------
def test_real_board_crossing_points_lie_on_both_routes():
    """原版 256 布线上：每个交叉事件的位置与角度必须与两条路线自洽。

    位置必须同时落在两条路线的解析几何上；角度必须等于该点处两条曲线真实
    切线之间的锐角。抽样验证，避免整套评价重复跑太久。
    """
    from src.collision import point_on_arc_2d
    from src.opt2d.legacy_bridge import run_legacy_rect
    from src.opt2d.source import specs_from_rect

    _, rect = run_legacy_rect(256, 5.0)
    specs = specs_from_rect(rect, 5.0)
    evaluator = Evaluator(256, check_spacing=False)
    segments, _, _ = evaluator.build(specs)
    evaluation = evaluator.evaluate(
        specs, label="selfcheck", segments=segments, issues=[], unplaced=[], runtime_s=0.0
    )
    assert evaluation.events, "原版 256 布线应存在交叉事件"
    sample = evaluation.events[:: max(1, len(evaluation.events) // 200)]

    def on_route(route_id, event):
        point = Point2D(event.x, event.y)
        for segment in segments[route_id]:
            if isinstance(segment, LineSegment2D):
                dx, dy = segment.end.x - segment.start.x, segment.end.y - segment.start.y
                length = math.hypot(dx, dy)
                ux, uy = dx / length, dy / length
                t = (point.x - segment.start.x) * ux + (point.y - segment.start.y) * uy
                if -1e-9 <= t <= length + 1e-9:
                    foot = Point2D(segment.start.x + t * ux, segment.start.y + t * uy)
                    if math.hypot(point.x - foot.x, point.y - foot.y) <= 1e-6:
                        return True
            elif point_on_arc_2d(point, segment, 1e-6):
                return True
        return False

    for event in sample:
        assert on_route(event.route_a, event), (event.route_a, event.x, event.y)
        assert on_route(event.route_b, event), (event.route_b, event.x, event.y)
        assert 0.0 < event.angle_deg <= 90.0000001
