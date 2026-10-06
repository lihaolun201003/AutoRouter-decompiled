"""Step 14 回归测试：固定保护集合、压力情景、验收规则与带回滚的局部优化。

运行：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -m pytest tests/test_opt2d_step14.py -q
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import LineSegment2D, Point2D  # noqa: E402
from src.opt2d.evaluator import (  # noqa: E402
    BoardEvaluation,
    CrossingEvent,
    Evaluator,
    RouteRecord,
)
from src.opt2d.step14 import (  # noqa: E402
    AcceptanceRule,
    ProtectionSet,
    acceptance_check,
    scenario_max,
    scenario_route_losses,
    select_protection,
)

scipy = pytest.importorskip("scipy", reason="需要 2D 项目 waveguide_calculator 的 scipy 依赖")

from src.opt2d.frozen import frozen_ports_frame  # noqa: E402
from src.opt2d.planner import PlanConfig, Planner  # noqa: E402
from src.opt2d.smoothing import RouteSpec  # noqa: E402
from src.opt2d.step14 import local_optimize  # noqa: E402


# --------------------------------------------------------------------------
# 构造工具：手工 BoardEvaluation（只填验收/保护所需的字段）
# --------------------------------------------------------------------------
def _record(rid: int, loss: float, *, kind: str = "u", crossings: int = 0) -> RouteRecord:
    record = RouteRecord(
        route_id=rid, port1=0, port2=0, index1=0, index2=0,
        sx=0.0, sy=0.0, lx=100.0, ly=0.0, track_y=50.0, radius=5.0, dx=100.0,
        straight_length_mm=100.0, arc_length_mm=0.0, total_length_mm=100.0,
        bend_angles_deg=[], bend_count=0, geometry_kind=kind,
    )
    record.total_loss_db = loss
    record.crossing_events = [
        CrossingEvent(rid, rid + 1, 0.0, 0.0, 30.0, loss / max(1, crossings))
        for _ in range(crossings)
    ]
    return record


def _evaluation(label: str, rows: list[tuple[int, float]], *, kinds=None, crossings=None):
    kinds = kinds or {}
    crossings = crossings or {}
    return BoardEvaluation(
        label=label, channels=256, line_width_mm=0.05, pitch_mm=0.25,
        board_width=150.0, board_height=150.0,
        routes=[_record(rid, loss, kind=kinds.get(rid, "u"), crossings=crossings.get(rid, 0))
                for rid, loss in rows],
        events=[], spacing_events=[], unplaced_ids=[], geometry_issues=[], runtime_s=0.0,
    )


# --------------------------------------------------------------------------
# 压力情景与固定保护集合
# --------------------------------------------------------------------------
def test_scenario_multiplies_only_small_angles():
    evaluator = Evaluator(256, check_spacing=False)
    horizontal = LineSegment2D(Point2D(0.0, 0.0), Point2D(100.0, 0.0))
    half = 10.0 / math.tan(math.radians(10.0))
    shallow = LineSegment2D(Point2D(50.0 - half, -10.0), Point2D(50.0 + half, 10.0))
    specs = [
        RouteSpec(1, 0.0, 0.0, 100.0, 0.0, 50.0, 5.0),
        RouteSpec(2, 50.0 - half, -10.0, 50.0 + half, 10.0, 50.0, 5.0),
    ]
    evaluation = evaluator.evaluate(
        specs, label="scenario", segments={1: [horizontal], 2: [shallow]}, unplaced=[]
    )
    base = scenario_route_losses(evaluation, factor=1.0)
    pressure = scenario_route_losses(evaluation, factor=5.0)
    crossing = evaluation.routes[0].crossing_loss_db
    assert crossing > 0.0
    assert pressure[1] == pytest.approx(base[1] + 4.0 * crossing, abs=1e-12)
    assert scenario_max(evaluation, factor=5.0) >= scenario_max(evaluation, factor=1.0)


def test_protection_set_is_fixed_deduplicated_and_ordered():
    base = _evaluation(
        "base",
        [(1, 9.0), (2, 5.0), (3, 4.0), (4, 3.0), (5, 2.0)],
        kinds={3: "u", 4: "u", 5: "freeform"},
        crossings={3: 30, 4: 20, 5: 40, 2: 25},
    )
    d56 = _evaluation("d56", [(1, 1.0), (2, 8.0), (3, 1.0)])
    protection = select_protection(base, d56, top_u=10)
    assert protection.base_worst == 1       # base 最差
    assert protection.d56_worst == 2        # D56 最差
    # 被穿越最多的 U 型按交叉数降序：3（30）→ 2（25）→ 4（20）→ 1（0）；
    # freeform 路线 5（40 个交叉）不计入 U 型集合。
    assert protection.crossed_u_routes == (3, 2, 4, 1)
    ids = protection.ids()
    assert len(ids) == len(set(ids))
    assert set(ids) == {1, 2, 3, 4}


# --------------------------------------------------------------------------
# 验收规则
# --------------------------------------------------------------------------
def test_acceptance_rejects_protected_route_worsening():
    base = _evaluation("base", [(1, 5.0), (2, 4.0), (3, 3.0)])
    rule = AcceptanceRule(protected_ids=(2,))
    ok = _evaluation("trial", [(1, 4.9), (2, 4.0), (3, 3.0)])
    verdict = acceptance_check(base, ok, rule)
    assert verdict.ok
    worse = _evaluation("trial", [(1, 4.9), (2, 4.01), (3, 3.0)])
    verdict = acceptance_check(base, worse, rule)
    assert not verdict.ok and "protected_worse_2" in verdict.reasons
    assert verdict.detail["protected_delta_db"][2] == pytest.approx(0.01, abs=1e-9)


def test_acceptance_enforces_mean_budget_and_max_not_worse():
    base = _evaluation("base", [(1, 5.0), (2, 4.0)])
    rule = AcceptanceRule(mean_slack_db=0.05, protected_ids=())
    # 平均 +0.05 以内允许；但最大值不允许上升（两个判据相互独立）。
    within = _evaluation("trial", [(1, 4.99), (2, 4.10)])
    assert acceptance_check(base, within, rule).ok
    over_mean = _evaluation("trial", [(1, 4.99), (2, 4.20)])
    verdict = acceptance_check(base, over_mean, rule)
    assert not verdict.ok and "mean_budget_exceeded" in verdict.reasons
    worse_max = _evaluation("trial", [(1, 5.01), (2, 4.10)])
    verdict = acceptance_check(base, worse_max, rule)
    assert not verdict.ok and "max_worse" in verdict.reasons


def test_acceptance_rejects_overlap_geometry_and_radius_change():
    base = _evaluation("base", [(1, 5.0), (2, 4.0)])
    rule = AcceptanceRule(protected_ids=())
    overlapped = _evaluation("trial", [(1, 4.0), (2, 4.0)])
    overlapped.contacts.append(
        __import__("src.opt2d.spacing", fromlist=["ContactEvent"]).ContactEvent(1, 2, "overlap")
    )
    verdict = acceptance_check(base, overlapped, rule)
    assert not verdict.ok and "overlap" in verdict.reasons

    changed = _evaluation("trial", [(1, 4.0), (2, 4.0)])
    for record in changed.routes:
        record.radius = 6.0
    verdict = acceptance_check(base, changed, rule)
    assert not verdict.ok and "radius_changed" in verdict.reasons

    moved = _evaluation("trial", [(1, 4.0), (2, 4.0)])
    moved.routes[0].sx = 1.0
    verdict = acceptance_check(base, moved, rule)
    assert not verdict.ok and "endpoint_changed" in verdict.reasons


# --------------------------------------------------------------------------
# 局部优化：半径冻结、真实回滚与状态指纹
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def frozen_256():
    return frozen_ports_frame(256)


def _small_planner(frozen_256, evaluator, overrides=None):
    settings = dict(
        candidate_limit=2, order_strategy="legacy", radii=(5.0, 6.0),
        radius_policy="adaptive", enable_freeform=True, freeform_shortlist=3,
        position_penalty=0.001,
    )
    settings.update(overrides or {})
    config = PlanConfig(channels=256, **settings)
    return Planner(config, evaluator)


def test_radius_overrides_freeze_every_route(frozen_256):
    """所有配置实际传入 radius_overrides 后，逐路半径必须等于冻结值。"""
    evaluator = Evaluator(256, check_spacing=False)
    planner = _small_planner(frozen_256, evaluator, overrides={"radii": (6.0,)})
    result = planner.plan(frozen_256)
    frozen_radii = {rid: 6.0 for rid in result.routes}
    overridden = _small_planner(
        frozen_256, evaluator, overrides={"radius_overrides": frozen_radii}
    )
    result2 = overridden.plan(frozen_256)
    assert not result2.unplaced
    for route in result2.routes.values():
        assert route.spec.radius == pytest.approx(6.0, abs=1e-12)


def test_local_optimize_keeps_state_when_nothing_accepted(frozen_256):
    """没有任何候选通过验收时：状态必须与优化前逐位一致（含状态指纹）。"""
    evaluator = Evaluator(256, check_spacing=False)
    config = PlanConfig(
        channels=256, candidate_limit=2, order_strategy="legacy",
        radii=(5.0, 6.0), radius_policy="adaptive",
        enable_freeform=True, freeform_shortlist=3, position_penalty=0.001,
    )
    planner = Planner(config, evaluator)
    result = planner.plan(frozen_256)
    evaluation = planner.evaluate_plan(result, "base")
    fingerprint_before = planner.state_fingerprint()

    # 极严的验收：不允许任何平均增量、且把"全体路线"设为保护对象 ——
    # 任何与 base 不同的布局都会因某条保护路线变差而被拒。
    rule = AcceptanceRule(
        mean_slack_db=0.0,
        protected_ids=tuple(sorted(r.route_id for r in evaluation.routes)),
    )
    protection = ProtectionSet(
        base_worst=1, d56_worst=2, crossed_u_routes=tuple(range(3, 13))
    )
    targets = sorted(evaluation.route_index)[:3]
    _, record = local_optimize(
        planner,
        baseline_evaluation=evaluation,
        protection=protection,
        rule=rule,
        baseline_result=result,
        target_routes=targets,
        candidates_per_route=1,
        time_budget_s=180.0,
    )
    assert record.rollback_fingerprint_mismatches == 0
    if record.accepted == 0:
        assert planner.state_fingerprint() == fingerprint_before
    assert record.candidates_tried >= 1


def test_local_optimize_accepts_only_when_rule_and_objective_hold(frozen_256):
    """优化在真实管线上运行：接受项必须同时满足验收与压力情景改善，且无回滚错位。"""
    evaluator = Evaluator(256, check_spacing=False)
    config = PlanConfig(
        channels=256, candidate_limit=3, order_strategy="legacy",
        radii=(5.0, 6.0), radius_policy="adaptive",
        enable_freeform=True, freeform_shortlist=3, position_penalty=0.001,
        small_angle_deg=20.0, small_angle_penalty_db=0.05,
    )
    planner = Planner(config, evaluator)
    result = planner.plan(frozen_256)
    evaluation = planner.evaluate_plan(result, "base")
    protection = select_protection(evaluation, evaluation, top_u=5)
    rule = AcceptanceRule(mean_slack_db=0.05, protected_ids=protection.ids())
    scenario_before = scenario_max(evaluation)
    losses_before = {
        r.route_id: r.total_loss_db for r in evaluation.routes
    }
    optimized, record = local_optimize(
        planner,
        baseline_evaluation=evaluation,
        protection=protection,
        rule=rule,
        baseline_result=result,
        target_routes=sorted(evaluation.route_index)[:6],
        candidates_per_route=2,
        time_budget_s=240.0,
    )
    assert record.rollback_fingerprint_mismatches == 0
    assert record.accepted <= 6
    # 记录与状态自洽：接受为正时情景最大值必须下降且验收仍成立。
    if record.accepted > 0:
        assert scenario_max(optimized) < scenario_before - 1e-9
        verdict = acceptance_check(evaluation, optimized, rule)
        assert verdict.ok
    # 无论接受与否，逐路保护对象都不能变差。
    for rid in protection.ids():
        assert (
            optimized.route_index[rid].total_loss_db
            <= losses_before[rid] + 1e-9
        ), rid
