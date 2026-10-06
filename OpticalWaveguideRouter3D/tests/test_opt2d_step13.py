"""Step 13 回归测试：冻结端点、完整快照、间距修复与自由弯角几何。

运行：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -m pytest tests/test_opt2d_step13.py -q

需要 scipy（2D 项目 ``waveguide_calculator``）；没有 scipy 的环境整体跳过。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collision import find_segment_intersections_2d  # noqa: E402
from src.models import ArcSegment2D, LineSegment2D, Point2D  # noqa: E402
from src.opt2d.freeform import (  # noqa: E402
    FreeformParams,
    build_freeform_geometry,
    freeform_candidates,
)
from src.opt2d.geometry_audit import audit_geometry, segment_tangent  # noqa: E402
from src.opt2d.intersections import segment_intersections  # noqa: E402
from src.opt2d.smoothing import RouteSpec  # noqa: E402
from src.opt2d.spacing import (  # noqa: E402
    segment_min_distance,
    spacing_report,
    spacing_violations,
)

scipy = pytest.importorskip("scipy", reason="需要 2D 项目 waveguide_calculator 的 scipy 依赖")

from src.opt2d.evaluator import Evaluator  # noqa: E402
from src.opt2d.frozen import frozen_ports_frame  # noqa: E402
from src.opt2d.planner import Planner, PlanConfig  # noqa: E402


# --------------------------------------------------------------------------
# 1. 间距计算修复
# --------------------------------------------------------------------------
def test_arc_arc_distance_user_counterexample():
    """R1 弧(0,0) 30°→90° 与 R1 弧(2.1,0) 160°→180°：距离 ≈ 0.334005。"""
    a = ArcSegment2D(
        Point2D(math.cos(math.radians(30)), math.sin(math.radians(30))),
        Point2D(0.0, 1.0),
        Point2D(0.0, 0.0),
        math.radians(60),
    )
    b = ArcSegment2D(
        Point2D(2.1 + math.cos(math.radians(160)), math.sin(math.radians(160))),
        Point2D(1.1, 0.0),
        Point2D(2.1, 0.0),
        math.radians(20),
    )
    distance, pa, pb = segment_min_distance(a, b)
    assert distance == pytest.approx(0.334005, abs=1e-5)
    assert distance != pytest.approx(0.1, abs=1e-3)
    # 最近点必须分别落在两条弧上，且距离自洽。
    assert abs(math.hypot(pa.x, pa.y) - 1.0) < 1e-9
    assert abs(math.hypot(pb.x - 2.1, pb.y) - 1.0) < 1e-9
    assert math.hypot(pa.x - pb.x, pa.y - pb.y) == pytest.approx(distance, abs=1e-12)
    # 输入交换对称。
    swapped, pa2, pb2 = segment_min_distance(b, a)
    assert swapped == pytest.approx(distance, abs=1e-12)


def test_segment_distance_is_zero_for_intersecting_curves():
    quarter = ArcSegment2D(Point2D(1.0, 0.0), Point2D(0.0, 1.0), Point2D(0.0, 0.0), math.pi / 2)
    crossing_line = LineSegment2D(Point2D(0.0, 0.5), Point2D(2.0, 0.5))
    assert segment_min_distance(quarter, crossing_line)[0] == 0.0
    assert segment_min_distance(crossing_line, quarter)[0] == 0.0
    tangent_line = LineSegment2D(Point2D(-2.0, 1.0), Point2D(2.0, 1.0))
    assert segment_min_distance(quarter, tangent_line)[0] == 0.0
    overlap_a = LineSegment2D(Point2D(0.0, 0.0), Point2D(5.0, 0.0))
    overlap_b = LineSegment2D(Point2D(2.0, 0.0), Point2D(8.0, 0.0))
    distance, pa, pb = segment_min_distance(overlap_a, overlap_b)
    assert distance == 0.0
    assert seg_point_on(pa, overlap_a) and seg_point_on(pa, overlap_b)


def seg_point_on(point: Point2D, segment: LineSegment2D) -> bool:
    dx, dy = segment.end.x - segment.start.x, segment.end.y - segment.start.y
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    t = (point.x - segment.start.x) * ux + (point.y - segment.start.y) * uy
    if not (-1e-9 <= t <= length + 1e-9):
        return False
    foot = Point2D(segment.start.x + t * ux, segment.start.y + t * uy)
    return math.hypot(point.x - foot.x, point.y - foot.y) <= 1e-9


def test_spacing_report_classifies_cross_touch_and_overlap_explicitly():
    """横穿不计间距；接触与重合必须显式返回，不能被静默忽略。"""
    horizontal = LineSegment2D(Point2D(0.0, 0.0), Point2D(5.0, 0.0))
    parallel_close = LineSegment2D(Point2D(0.0, 0.1), Point2D(5.0, 0.1))
    vertical = LineSegment2D(Point2D(0.0, -1.0), Point2D(0.0, 1.0))
    duplicate = LineSegment2D(Point2D(1.0, 0.0), Point2D(3.0, 0.0))
    report = spacing_report(
        {1: [horizontal], 2: [parallel_close], 3: [vertical], 4: [duplicate]}, 0.3
    )
    # 1-2 与 2-4 都是近并行（0.1 mm）→ 违规
    assert [(v.route_a, v.route_b) for v in report.violations] == [(1, 2), (2, 4)]
    # 1-3 在段 1 的端点处相触：显式记为 touch，且不计入间距违规。
    assert any(
        {c.route_a, c.route_b} == {1, 3} and c.kind == "touch" for c in report.contacts
    )
    assert all({v.route_a, v.route_b} != {1, 3} for v in report.violations)
    # 1-4 重合：显式记录为 overlap（几何违规）
    assert any(
        {c.route_a, c.route_b} == {1, 4} and c.kind == "overlap" for c in report.contacts
    )


# --------------------------------------------------------------------------
# 2. 自由弯角几何
# --------------------------------------------------------------------------
def test_freeform_geometry_preserves_endpoints_tangents_and_radius():
    cases = [
        ("up-right", FreeformParams(1, 20.0, 0.0, 60.0, 150.0, 5.0, -30.0, 0.5)),
        ("up-left", FreeformParams(2, 80.0, 0.0, 55.0, 150.0, 5.0, 45.0, 0.5)),
        ("down-right", FreeformParams(3, 40.0, 150.0, 70.0, 0.0, 5.0, 20.0, 0.5)),
        ("down-left", FreeformParams(4, 70.0, 150.0, 40.0, 0.0, 5.0, -20.0, 0.5)),
        ("R6", FreeformParams(5, 20.0, 0.0, 60.0, 150.0, 6.0, -45.0, 0.5)),
        ("t0=0", FreeformParams(6, 20.0, 0.0, 60.0, 150.0, 5.0, -75.0, 0.0)),
    ]
    for tag, params in cases:
        segments = build_freeform_geometry(params)
        spec = RouteSpec(
            params.route_id, params.sx, params.sy, params.lx, params.ly, 0.0, params.radius
        )
        assert audit_geometry(spec, segments) == [], tag
        assert segments[0].start.x == pytest.approx(params.sx)
        assert segments[0].start.y == pytest.approx(params.sy)
        assert segments[-1].end.x == pytest.approx(params.lx)
        assert segments[-1].end.y == pytest.approx(params.ly)
        start_tangent = segment_tangent(segments[0], segments[0].start)
        end_tangent = segment_tangent(segments[-1], segments[-1].end)
        sigma = 1.0 if params.ly > params.sy else -1.0
        assert start_tangent == pytest.approx((0.0, sigma), abs=1e-9)
        assert end_tangent == pytest.approx((0.0, sigma), abs=1e-9)
        assert len([s for s in segments if isinstance(s, ArcSegment2D)]) == 2
        for segment in segments:
            if isinstance(segment, ArcSegment2D):
                radius = math.hypot(
                    segment.start.x - segment.center.x, segment.start.y - segment.center.y
                )
                assert radius == pytest.approx(params.radius, abs=1e-9)
        # 两段圆弧转角互为相反数，中间斜线长度非负。
        arcs = [s for s in segments if isinstance(s, ArcSegment2D)]
        assert arcs[0].sweep_rad == pytest.approx(-arcs[1].sweep_rad, abs=1e-12)


def test_freeform_zero_lateral_offset_has_no_solution():
    """零水平偏移在本路径族内无解：必须由调用方回退到 U 型。"""
    row = pd.Series({"sx": 70.0, "sy": 0.0, "lx": 70.0, "ly": 150.0}, name=1)
    assert freeform_candidates(row, 5.0) == []
    assert freeform_candidates(row, 6.0) == []
    with pytest.raises(ValueError):
        build_freeform_geometry(FreeformParams(1, 70.0, 0.0, 70.0, 150.0, 5.0, 60.0, 0.5))


def test_freeform_rejects_impossible_combinations():
    # 终点方向与转角符号不匹配 → 中间段长度为负。
    with pytest.raises(ValueError):
        build_freeform_geometry(FreeformParams(1, 20.0, 0.0, 60.0, 150.0, 5.0, 30.0, 0.5))
    # 横向跨度太大而转角太小 → 直线长度不合法。
    with pytest.raises(ValueError):
        build_freeform_geometry(FreeformParams(2, 5.0, 0.0, 205.0, 150.0, 5.0, -10.0, 0.5))


def test_freeform_candidates_cover_both_directions():
    right = pd.Series({"sx": 20.0, "sy": 0.0, "lx": 60.0, "ly": 150.0}, name=1)
    left = pd.Series({"sx": 80.0, "sy": 0.0, "lx": 55.0, "ly": 150.0}, name=2)
    # 终点在右 → 斜线必须向右，转角取负；终点在左则相反。
    right_candidates = freeform_candidates(right, 5.0)
    assert right_candidates and all(c.alpha_deg < 0 for c in right_candidates)
    left_candidates = freeform_candidates(left, 5.0)
    assert left_candidates and all(c.alpha_deg > 0 for c in left_candidates)


def test_tolerant_intersection_handles_general_direction_lines():
    """一般方向直线的求交不应因为绝对残差阈值而失败。"""
    a = LineSegment2D(Point2D(0.0, 0.0), Point2D(120.0, 100.0))
    b = LineSegment2D(Point2D(0.0, 60.0), Point2D(120.0, 40.0))
    events = segment_intersections(a, b)
    assert len(events) == 1 and events[0].point is not None
    point = events[0].point
    assert point.x == pytest.approx(60.0, abs=1e-6)
    assert point.y == pytest.approx(50.0, abs=1e-6)


# --------------------------------------------------------------------------
# 3. 冻结端点与快照完整性
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def frozen_256():
    return frozen_ports_frame(256)


def test_frozen_ports_match_legacy_geometry_endpoints(frozen_256):
    """冻结端点必须逐路等于方案 A 最终几何的 sx/sy/lx/ly。"""
    from src.opt2d.legacy_bridge import run_legacy_rect
    from src.opt2d.source import specs_from_rect

    _, rect = run_legacy_rect(256, 5.0)
    specs = {spec.route_id: spec for spec in specs_from_rect(rect, 5.0)}
    assert len(frozen_256) == len(specs)
    for rid, row in frozen_256.iterrows():
        spec = specs[rid]
        assert row.sx == pytest.approx(spec.sx, abs=1e-12)
        assert row.lx == pytest.approx(spec.lx, abs=1e-12)
        assert row.sy == pytest.approx(spec.sy, abs=1e-12)
        assert row.ly == pytest.approx(spec.ly, abs=1e-12)


def test_planner_keeps_frozen_endpoints(frozen_256):
    """新方案不得通过交换端点满足布线条件。"""
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
    result = planner.plan(frozen_256)
    assert not result.unplaced
    for rid, route in result.routes.items():
        row = frozen_256.loc[rid]
        assert route.spec.sx == pytest.approx(row.sx, abs=1e-12)
        assert route.spec.sy == pytest.approx(row.sy, abs=1e-12)
        assert route.spec.lx == pytest.approx(row.lx, abs=1e-12)
        assert route.spec.ly == pytest.approx(row.ly, abs=1e-12)


def test_snapshot_restore_is_exactly_identical(frozen_256):
    """快照/恢复必须覆盖 RouteSpec、解析段、轨道占用、端口节点、提交顺序与缓存。"""
    evaluator = Evaluator(256)
    planner = Planner(
        PlanConfig(channels=256, candidate_limit=2, order_strategy="legacy", radii=(5.0,)),
        evaluator,
    )
    planner.plan(frozen_256)
    before = planner.state_fingerprint()
    snapshot = planner.snapshot()
    planner.restore(snapshot)
    after = planner.state_fingerprint()
    assert before == after
    assert before["context"] == after["context"]


def test_reroute_uses_frozen_pass_context(frozen_256):
    """重布必须复用冻结的 pass 边界，而不是随已提交集合漂移。"""
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
    result = planner.plan(frozen_256)
    frozen_context = dict(planner._frozen_context)
    assert frozen_context.get("above2below", {}).get("below_line") is not None

    def _explode():
        raise AssertionError("reroute 不得重新计算 pass 边界")

    planner._pass_context = _explode  # type: ignore[assignment]
    victim = [rid for rid in list(result.routes)[:5] if result.routes[rid].spec.sy == 0]
    journal = planner.snapshot()
    kept = [entry for entry in journal.entries if entry[0] not in set(victim)]
    planner.restore(type(journal)(kept, journal.context))
    planner.reroute(victim)  # 只要不抛错就说明用了冻结边界
    assert planner._frozen_context == frozen_context


# --------------------------------------------------------------------------
# 4. D0 与自由弯角方案的行为
# --------------------------------------------------------------------------
def test_d0_prefers_r6_and_falls_back_to_r5(frozen_256):
    evaluator = Evaluator(256)
    planner = Planner(
        PlanConfig(
            channels=256,
            candidate_limit=1,
            order_strategy="legacy",
            radii=(6.0, 5.0),
            radius_policy="fallback",
        ),
        evaluator,
    )
    result = planner.plan(frozen_256)
    assert not result.unplaced
    radii = {route.spec.radius for route in result.routes.values()}
    assert radii <= {5.0, 6.0}
    assert 6.0 in radii  # 优先 R6
    summary = planner.evaluate_plan(result, "D0").summary()
    assert summary["complete_connection"] is True
    assert summary["geometry_issue_count"] == 0


def test_freeform_scheme_keeps_connection_and_endpoints(frozen_256):
    evaluator = Evaluator(256)
    planner = Planner(
        PlanConfig(
            channels=256,
            candidate_limit=2,
            order_strategy="legacy",
            radii=(5.0,),
            enable_freeform=True,
            freeform_shortlist=4,
        ),
        evaluator,
    )
    result = planner.plan(frozen_256)
    assert not result.unplaced
    kinds = {route.spec.kind for route in result.routes.values()}
    assert "freeform" in kinds
    # 同侧连接必须保留 U 型，只有跨侧才允许自由弯角。
    for rid, route in result.routes.items():
        row = frozen_256.loc[rid]
        if route.spec.kind == "freeform":
            assert abs(row.ly - row.sy) > 1e-9
    evaluation = planner.evaluate_plan(result, "F5")
    summary = evaluation.summary()
    assert summary["complete_connection"] is True
    assert summary["geometry_issue_count"] == 0
    assert summary["contact_overlap_count"] == 0
    for rid, route in result.routes.items():
        row = frozen_256.loc[rid]
        assert route.spec.sx == pytest.approx(row.sx, abs=1e-12)
        assert route.spec.lx == pytest.approx(row.lx, abs=1e-12)


def test_freeform_reduces_bend_loss_at_the_cost_of_crossings(frozen_256):
    """自由弯角的主要效应：弯曲损耗显著下降、交叉事件增加 —— 两者都要如实统计。"""
    evaluator = Evaluator(256)
    base = Planner(
        PlanConfig(channels=256, candidate_limit=2, order_strategy="legacy", radii=(5.0,)),
        evaluator,
    )
    base_result = base.plan(frozen_256)
    base_summary = base.evaluate_plan(base_result, "R5U").summary()

    free = Planner(
        PlanConfig(
            channels=256,
            candidate_limit=2,
            order_strategy="legacy",
            radii=(5.0,),
            enable_freeform=True,
            freeform_shortlist=4,
        ),
        evaluator,
    )
    free_result = free.plan(frozen_256)
    free_summary = free.evaluate_plan(free_result, "F5").summary()

    assert free_summary["mean_bend_loss_db"] < base_summary["mean_bend_loss_db"]
    assert free_summary["unique_crossing_events"] >= base_summary["unique_crossing_events"]
    # 最差链路不允许变差（任务规定的接受条件）。
    assert free_summary["max_loss_db"] <= base_summary["max_loss_db"] + 1e-9


def test_crossing_sensitivity_recomputes_small_angle_contributions(frozen_256):
    from src.opt2d.step13 import crossing_sensitivity

    evaluator = Evaluator(256)
    planner = Planner(
        PlanConfig(
            channels=256,
            candidate_limit=2,
            order_strategy="legacy",
            radii=(5.0,),
            enable_freeform=True,
            freeform_shortlist=4,
        ),
        evaluator,
    )
    result = planner.plan(frozen_256)
    evaluation = planner.evaluate_plan(result, "F5")
    sensitivity = crossing_sensitivity(evaluation, factors=(0.5, 1.0, 2.0))
    half = sensitivity["factor_0.5"]["mean_loss_db"]
    double = sensitivity["factor_2"]["mean_loss_db"]
    assert half < double  # 小角度损耗被放大时均值必然上升
    # 系数 1.0 必须与未扰动的解析统计一致。
    assert sensitivity["factor_1"]["mean_loss_db"] == pytest.approx(
        evaluation.summary()["mean_loss_db"], abs=1e-9
    )
