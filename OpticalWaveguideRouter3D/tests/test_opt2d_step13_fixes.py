"""Step 13 补修回归测试：直线段稳健分类与间距评分口径。

覆盖任务给定的真实反例（256 F56 的路线 #7 与 #31 斜线段共线重合
152.007142675 mm）、反向线段、交换输入、平移、近乎平行但分离、共线分离、
端点接触，以及弧—弧同向极值候选、间距违规计数单位与 AABB 预筛阈值。

运行：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -m pytest tests/test_opt2d_step13_fixes.py -q
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import ArcSegment2D, LineSegment2D, Point2D  # noqa: E402
from src.opt2d import intersections as ix  # noqa: E402
from src.opt2d.spacing import segment_min_distance, spacing_report  # noqa: E402

scipy = pytest.importorskip("scipy", reason="需要 2D 项目 waveguide_calculator 的 scipy 依赖")

from src.opt2d.evaluator import Evaluator  # noqa: E402
from src.opt2d.planner import PlanConfig, PlannedRoute, Planner  # noqa: E402
from src.opt2d.smoothing import RouteSpec  # noqa: E402

# --------------------------------------------------------------------------
# 真实反例：256 通道 F56 方案路线 #7 与 #31 的斜线段
# 两条斜线同在 x + y = 149.9 上，路线 #7 的斜线段完全包含于 #31 的斜线段，
# 重叠长度 152.007142675 mm；修复前被判为 cross（中点），重合被漏检。
# --------------------------------------------------------------------------
R7_DIAG = LineSegment2D(
    Point2D(128.642640687, 21.257359313), Point2D(21.157359313, 128.742640687)
)
R31_DIAG = LineSegment2D(
    Point2D(137.342640687, 12.557359313), Point2D(12.457359313, 137.442640687)
)
OVERLAP_LENGTH_MM = 152.007142675


def _projection_overlap(a: LineSegment2D, b: LineSegment2D) -> float:
    """b 在 a 上的投影重叠长度（与分类器同一算法，独立复算用于断言）。"""
    dx, dy = a.end.x - a.start.x, a.end.y - a.start.y
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    t0 = (b.start.x - a.start.x) * ux + (b.start.y - a.start.y) * uy
    t1 = (b.end.x - a.start.x) * ux + (b.end.y - a.start.y) * uy
    return min(length, max(t0, t1)) - max(0.0, min(t0, t1))


def test_real_overlap_case_is_classified_as_overlap():
    """真实反例：#7/#31 的共线斜线段必须判为 overlap，而不是 cross。"""
    events = ix.segment_intersections(R7_DIAG, R31_DIAG)
    assert len(events) == 1
    assert events[0].kind == "overlap"
    assert events[0].point is None
    # 用独立投影复算重叠长度：必须等于任务给定的 152.007142675 mm。
    assert _projection_overlap(R31_DIAG, R7_DIAG) == pytest.approx(
        OVERLAP_LENGTH_MM, abs=1e-6
    )


def test_real_overlap_case_covers_robust_path():
    """该调用必须走新增的稳健分类器（覆盖新兜底路径）。"""
    before = ix.tolerant_solves
    ix.segment_intersections(R7_DIAG, R31_DIAG)
    assert ix.tolerant_solves == before + 1


def test_overlap_survives_reversed_and_swapped_inputs():
    """反向线段与交换输入下，重合判定不变。"""
    reversed_b = LineSegment2D(R31_DIAG.end, R31_DIAG.start)
    for a, b in (
        (R7_DIAG, reversed_b),
        (R31_DIAG, R7_DIAG),
        (reversed_b, R7_DIAG),
        (LineSegment2D(R7_DIAG.end, R7_DIAG.start), LineSegment2D(R31_DIAG.end, R31_DIAG.start)),
    ):
        events = ix.segment_intersections(a, b)
        assert len(events) == 1 and events[0].kind == "overlap", (a, b)


def test_overlap_survives_translation():
    """整体平移后仍是重合，重叠长度不变。"""
    shift = (13.7, -42.25)
    moved_a = LineSegment2D(
        Point2D(R7_DIAG.start.x + shift[0], R7_DIAG.start.y + shift[1]),
        Point2D(R7_DIAG.end.x + shift[0], R7_DIAG.end.y + shift[1]),
    )
    moved_b = LineSegment2D(
        Point2D(R31_DIAG.start.x + shift[0], R31_DIAG.start.y + shift[1]),
        Point2D(R31_DIAG.end.x + shift[0], R31_DIAG.end.y + shift[1]),
    )
    events = ix.segment_intersections(moved_a, moved_b)
    assert len(events) == 1 and events[0].kind == "overlap"
    assert _projection_overlap(moved_a, moved_b) == pytest.approx(
        OVERLAP_LENGTH_MM, abs=1e-6
    )


# --------------------------------------------------------------------------
# 不能把"近乎平行"一律判成共线
# --------------------------------------------------------------------------
def test_nearly_parallel_but_separated_is_not_collinear():
    """夹角低于平行阈值、但横向分离 0.05 mm：必须无事件（交给间距检查）。"""
    a = LineSegment2D(Point2D(0.0, 0.0), Point2D(120.0, 0.0))
    tiny = 1e-10
    b = LineSegment2D(
        Point2D(10.0, 0.05), Point2D(10.0 + 100.0 * math.cos(tiny), 0.05 + 100.0 * math.sin(tiny))
    )
    assert ix.segment_intersections(a, b) == []
    distance, _, _ = segment_min_distance(a, b)
    assert distance == pytest.approx(0.05, abs=1e-9)


def test_true_small_angle_crossing_is_preserved():
    """真实的小角度交叉（1e-5 rad）必须保留为 cross，不能吞成共线。"""
    a = LineSegment2D(Point2D(0.0, 0.0), Point2D(100.0, 0.0))
    half_slope = 1e-5 * 100.0 / 2.0  # 斜率 1e-5，在 (50, 0) 与 a 相交
    b = LineSegment2D(Point2D(0.0, -half_slope), Point2D(100.0, half_slope))
    events = ix.segment_intersections(a, b)
    assert len(events) == 1 and events[0].kind == "cross"
    assert events[0].point.x == pytest.approx(50.0, abs=1e-3)
    assert events[0].point.y == pytest.approx(0.0, abs=1e-6)


def test_collinear_but_disjoint_returns_nothing():
    """同一直线上但完全分离的两段：无事件（不是重合，也不是接触）。"""
    a = LineSegment2D(Point2D(0.0, 0.0), Point2D(10.0, 10.0))
    b = LineSegment2D(Point2D(20.0, 20.0), Point2D(30.0, 30.0))
    assert ix.segment_intersections(a, b) == []
    assert ix.segment_intersections(b, a) == []


def test_collinear_endpoint_contact_is_touch():
    """共线且只在端点相触：touch 并给出接触点。"""
    a = LineSegment2D(Point2D(0.0, 0.0), Point2D(10.0, 10.0))
    b = LineSegment2D(Point2D(10.0, 10.0), Point2D(20.0, 20.0))
    events = ix.segment_intersections(a, b)
    assert len(events) == 1 and events[0].kind == "touch"
    assert events[0].point.x == pytest.approx(10.0, abs=1e-9)
    assert events[0].point.y == pytest.approx(10.0, abs=1e-9)


def test_perpendicular_endpoint_contact_is_touch():
    """垂直但只在端点相触：touch，不是 cross。"""
    a = LineSegment2D(Point2D(0.0, 0.0), Point2D(10.0, 0.0))
    b = LineSegment2D(Point2D(10.0, 0.0), Point2D(10.0, 5.0))
    events = ix.segment_intersections(a, b)
    assert len(events) == 1 and events[0].kind == "touch"


def test_endpoint_tolerance_gap_is_not_an_event():
    """明显超出容差的间隙（1e-4 mm）不算接触。"""
    a = LineSegment2D(Point2D(0.0, 0.0), Point2D(10.0, 0.0))
    b = LineSegment2D(Point2D(10.0001, 0.0), Point2D(10.0001, 5.0))
    assert ix.segment_intersections(a, b) == []


def test_intersection_point_lies_on_both_finite_segments():
    """一般方向交叉：交点必须落在两条有限线段上，残差受控。"""
    a = LineSegment2D(Point2D(0.0, 0.0), Point2D(120.0, 100.0))
    b = LineSegment2D(Point2D(0.0, 60.0), Point2D(120.0, 40.0))
    events = ix.segment_intersections(a, b)
    assert len(events) == 1 and events[0].kind == "cross"
    point = events[0].point
    for segment in (a, b):
        dx, dy = segment.end.x - segment.start.x, segment.end.y - segment.start.y
        length = math.hypot(dx, dy)
        t = ((point.x - segment.start.x) * dx + (point.y - segment.start.y) * dy) / length
        assert -1e-9 <= t <= length + 1e-9
        foot = Point2D(segment.start.x + t * dx / length, segment.start.y + t * dy / length)
        assert math.hypot(point.x - foot.x, point.y - foot.y) <= 1e-9


def test_parallel_separated_lines_have_no_event():
    a = LineSegment2D(Point2D(0.0, 0.0), Point2D(50.0, 0.0))
    b = LineSegment2D(Point2D(0.0, 0.3), Point2D(50.0, 0.3))
    assert ix.segment_intersections(a, b) == []


# --------------------------------------------------------------------------
# 弧—弧最近距离：同向极值候选
# --------------------------------------------------------------------------
def _arc(cx, cy, radius, deg0, deg1):
    return ArcSegment2D(
        Point2D(cx + radius * math.cos(math.radians(deg0)), cy + radius * math.sin(math.radians(deg0))),
        Point2D(cx + radius * math.cos(math.radians(deg1)), cy + radius * math.sin(math.radians(deg1))),
        Point2D(cx, cy),
        math.radians(deg1 - deg0),
    )


def test_arc_arc_same_side_extreme_candidate():
    """圆心 (0,0) R5 与 (0.9,0) R6、两弧同为 150°→210°：最小距离 0.1 mm。"""
    a = _arc(0.0, 0.0, 5.0, 150.0, 210.0)
    b = _arc(0.9, 0.0, 6.0, 150.0, 210.0)
    distance, pa, pb = segment_min_distance(a, b)
    assert distance == pytest.approx(0.1, abs=1e-12)
    assert pa.x == pytest.approx(-5.0, abs=1e-9) and pa.y == pytest.approx(0.0, abs=1e-9)
    assert pb.x == pytest.approx(-5.1, abs=1e-9) and pb.y == pytest.approx(0.0, abs=1e-9)
    swapped, _, _ = segment_min_distance(b, a)
    assert swapped == pytest.approx(0.1, abs=1e-12)


def test_arc_arc_previous_counterexample_still_holds():
    """Step 13 原反例（0.334005）不能被新候选改坏。"""
    a = _arc(0.0, 0.0, 1.0, 30.0, 90.0)
    b = _arc(2.1, 0.0, 1.0, 160.0, 180.0)
    distance, pa, pb = segment_min_distance(a, b)
    assert distance == pytest.approx(0.334005, abs=1e-5)
    assert distance != pytest.approx(0.1, abs=1e-3)


# --------------------------------------------------------------------------
# 间距违规计数单位（评分与报告一致：路线对级）
# --------------------------------------------------------------------------
def _straight_route_spec(route_id, x0, y0, x1, y1, radius=5.0):
    return RouteSpec(
        route_id=route_id, sx=x0, sy=y0, lx=x1, ly=y1, track_y=0.5, radius=radius
    )


def test_spacing_violation_count_is_per_route_pair():
    """一条路线被拆成更多解析段，不得增加间距违规次数。"""
    long_line = LineSegment2D(Point2D(0.0, 0.0), Point2D(90.0, 0.0))
    parallel = LineSegment2D(Point2D(0.0, 0.1), Point2D(90.0, 0.1))
    split = [
        LineSegment2D(Point2D(0.0, 0.1), Point2D(30.0, 0.1)),
        LineSegment2D(Point2D(30.0, 0.1), Point2D(60.0, 0.1)),
        LineSegment2D(Point2D(60.0, 0.1), Point2D(90.0, 0.1)),
    ]
    report_whole = spacing_report({1: [long_line], 2: [parallel]}, 0.3)
    report_split = spacing_report({1: [long_line], 2: split}, 0.3)
    assert len(report_whole.violations) == 1
    assert len(report_split.violations) == 1  # 路线对级，不随解析段数增加


def test_planner_pair_metrics_uses_route_pair_unit():
    """planner 候选评分与报告口径一致：间距违规 0/1，不是段对数。"""
    evaluator = Evaluator(256)
    planner = Planner(
        PlanConfig(channels=256, candidate_limit=1, order_strategy="legacy", radii=(5.0,)),
        evaluator,
    )
    route_a = [LineSegment2D(Point2D(0.0, 0.0), Point2D(90.0, 0.0))]
    split_b = [
        LineSegment2D(Point2D(0.0, 0.1), Point2D(30.0, 0.1)),
        LineSegment2D(Point2D(30.0, 0.1), Point2D(60.0, 0.1)),
        LineSegment2D(Point2D(60.0, 0.1), Point2D(90.0, 0.1)),
    ]
    from src.opt2d.spacing import segment_aabb

    metrics = planner._pair_metrics(
        1, route_a, [segment_aabb(s) for s in route_a],
        2, split_b, [segment_aabb(s) for s in split_b],
    )
    assert metrics[3] == 1  # spacing 计数为路线对级


def test_planner_reach_filter_does_not_skip_close_neighbours():
    """路线级 AABB 不相交（间隙 0.2 mm > tol）但间距不足的候选必须被计数。"""
    evaluator = Evaluator(256)  # 阈值 = 0.05 + 0.25 = 0.30 mm
    planner = Planner(
        PlanConfig(channels=256, candidate_limit=1, order_strategy="legacy", radii=(5.0,)),
        evaluator,
    )
    committed_spec = _straight_route_spec(0, 0.0, 0.0, 90.0, 0.0)
    committed_segments = [LineSegment2D(Point2D(0.0, 0.0), Point2D(90.0, 0.0))]
    planner.committed = {0: PlannedRoute(committed_spec, committed_segments, 0.0, 0)}

    from src.opt2d.spacing import Aabb, segment_aabb

    boxes = [segment_aabb(s) for s in committed_segments]
    planner._boxes = {0: boxes}
    planner._route_boxes = {
        0: Aabb(
            min(b.min_x for b in boxes), min(b.min_y for b in boxes),
            max(b.max_x for b in boxes), max(b.max_y for b in boxes),
        )
    }
    # 候选：整体位于右上对角，与已提交直线的 AABB 间隙 0.206 mm（> tol），
    # 但最近距离 0.05 mm（< 阈值）—— 旧预筛（tol）会整对跳过，漏掉违规。
    candidate = RouteSpec(
        route_id=1, sx=90.2, sy=0.05, lx=150.0, ly=0.05, track_y=75.0, radius=5.0
    )
    score, built, _ = planner._score_spec(candidate)
    assert built  # 几何合法，未被拒绝
    from src.opt2d.spacing import Aabb as _Aabb  # noqa: F401

    assert score != float("inf")
    # 直接验证该对指标确实检出了间距违规。
    metrics = planner._pair_metrics(
        1, built, [segment_aabb(s) for s in built], 0, committed_segments, boxes
    )
    assert metrics[3] == 1


def test_small_angle_crossing_limit_counts_only_below_threshold():
    """受约束自由弯角：<20° 的交叉被计数，更陡的交叉不计数。"""
    evaluator = Evaluator(256)
    base = dict(channels=256, candidate_limit=1, order_strategy="legacy", radii=(5.0,))
    off = Planner(PlanConfig(**base), evaluator)
    on = Planner(
        PlanConfig(**base, small_angle_deg=20.0, small_angle_penalty_db=0.05), evaluator
    )
    horizontal = LineSegment2D(Point2D(0.0, 0.0), Point2D(100.0, 0.0))

    def crossed_at(angle_deg):
        # 经过 (50, 0) 的斜线段，与水平线夹角 angle_deg。
        half = 10.0 / math.tan(math.radians(angle_deg))
        return LineSegment2D(Point2D(50.0 - half, -10.0), Point2D(50.0 + half, 10.0))

    def metrics(planner, angle_deg):
        other = crossed_at(angle_deg)
        from src.opt2d.spacing import segment_aabb

        return planner._pair_metrics(
            1, [horizontal], [segment_aabb(horizontal)],
            2, [other], [segment_aabb(other)],
        )

    shallow = metrics(on, 10.0)
    assert shallow[0] > 0.0  # 交叉损耗存在
    assert shallow[4] == 1  # 10° < 20° → 计数一次
    steep = metrics(on, 30.0)
    assert steep[4] == 0  # 30° 不计数
    assert metrics(off, 10.0)[4] == 0  # 关闭时恒为 0


def test_evaluator_detects_cross_route_overlap_after_fix():
    """评价器（含 planner 路径）对重合的硬拒绝依据：真实反例给出 overlap 事件。"""
    from src.opt2d.geometry_audit import AuditIssue

    evaluator = Evaluator(256)
    segments = {7: [R7_DIAG], 31: [R31_DIAG]}
    specs = [
        RouteSpec(7, 128.642640687, 21.257359313, 21.157359313, 128.742640687, 0.5, 6.0),
        RouteSpec(31, 137.342640687, 12.557359313, 12.457359313, 137.442640687, 0.5, 6.0),
    ]
    result = evaluator.evaluate(specs, label="overlap", segments=segments, unplaced=[])
    kinds = [issue.kind for issue in result.geometry_issues]
    assert "overlap" in kinds
    assert result.summary()["contact_overlap_count"] >= 1
