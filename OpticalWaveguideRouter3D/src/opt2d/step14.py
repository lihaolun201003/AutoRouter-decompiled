"""Step 14：冻结对照下的二维稳健优化。

目标：在**冻结的连接身份、端点与半径**下，降低小角交叉带来的损耗风险
（压力情景 = <20° 交叉损耗 ×5），同时**显式保护**固定的一批路线。

组成：

* **压力情景**（:func:`scenario_route_losses` / :func:`scenario_max`）：
  把小于 20° 的交叉事件损耗乘以系数（默认 5）后的逐路与全局损耗。这是
  **实验情景**，用于给"小角度交叉表不可信"这一风险一个可优化的目标，
  不声称代表真实误差范围。
* **固定保护集合**（:class:`ProtectionSet` / :func:`select_protection`）：
  一次性从 base 与 D56 确定（base 最差路线、D56 最差路线、base 中被穿越
  最多的若干条 U 型路线），所有方案比较**同一批** route_id。
* **验收规则**（:class:`AcceptanceRule` / :func:`acceptance_check`）：
  平均损耗允许 base + 0.05 dB；全局最大损耗不超过 base；保护路线逐路不超
  各自 base；完整连接；端点与半径零变化；重合为 0；单路几何合法。
* **局部优化**（:func:`local_optimize`）：从完整合法的 base 出发，逐条移除
  目标路线、枚举其候选、**完整评价整个布局**后按验收规则接受或**完整回滚**
  （回滚后核对状态指纹），并如实记录候选数、接受数、拒绝原因与运行时间。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .evaluator import BoardEvaluation
from .planner import PlanConfig, PlanResult, Planner, PlannerSnapshot

__all__ = [
    "DEFAULT_SCENARIO_FACTOR",
    "DEFAULT_SCENARIO_THRESHOLD_DEG",
    "scenario_route_losses",
    "scenario_max",
    "scenario_worst_route",
    "ProtectionSet",
    "select_protection",
    "AcceptanceRule",
    "AcceptanceResult",
    "acceptance_check",
    "OptimizeRecord",
    "local_optimize",
]

#: 压力情景默认：把 <20° 的交叉损耗整体乘以 5（实验情景，不代表真实误差）。
DEFAULT_SCENARIO_FACTOR = 5.0
DEFAULT_SCENARIO_THRESHOLD_DEG = 20.0


# --------------------------------------------------------------------------
# 压力情景（固定几何复算，不重新布线）
# --------------------------------------------------------------------------
def scenario_route_losses(
    evaluation: BoardEvaluation,
    *,
    factor: float = DEFAULT_SCENARIO_FACTOR,
    threshold_deg: float = DEFAULT_SCENARIO_THRESHOLD_DEG,
) -> dict[int, float]:
    """压力情景下的逐路损耗：<threshold_deg 的交叉损耗乘以 factor。"""
    losses: dict[int, float] = {}
    for record in evaluation.routes:
        crossing = sum(
            event.loss_db * (factor if event.angle_deg < threshold_deg else 1.0)
            for event in record.crossing_events
        )
        losses[record.route_id] = record.straight_loss_db + record.bend_loss_db + crossing
    return losses


def scenario_max(
    evaluation: BoardEvaluation,
    *,
    factor: float = DEFAULT_SCENARIO_FACTOR,
    threshold_deg: float = DEFAULT_SCENARIO_THRESHOLD_DEG,
) -> float:
    """压力情景下的全局最大损耗。"""
    losses = scenario_route_losses(evaluation, factor=factor, threshold_deg=threshold_deg)
    if not losses:
        raise ValueError("no route to evaluate")
    return max(losses.values())


def scenario_worst_route(
    evaluation: BoardEvaluation,
    *,
    factor: float = DEFAULT_SCENARIO_FACTOR,
    threshold_deg: float = DEFAULT_SCENARIO_THRESHOLD_DEG,
) -> int:
    losses = scenario_route_losses(evaluation, factor=factor, threshold_deg=threshold_deg)
    return max(losses, key=lambda rid: (losses[rid], -rid))


# --------------------------------------------------------------------------
# 固定保护集合
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ProtectionSet:
    """一次性确定的固定保护 ID 集合（所有方案比较同一批路线）。"""

    base_worst: int
    d56_worst: int
    crossed_u_routes: tuple[int, ...]

    def ids(self) -> tuple[int, ...]:
        out = [self.base_worst, self.d56_worst]
        for rid in self.crossed_u_routes:
            if rid not in out:
                out.append(rid)
        return tuple(out)

    def describe(self) -> dict:
        return {
            "base_worst": self.base_worst,
            "d56_worst": self.d56_worst,
            "crossed_u_routes": list(self.crossed_u_routes),
            "all_ids": list(self.ids()),
        }


def select_protection(
    base_evaluation: BoardEvaluation,
    d56_evaluation: BoardEvaluation,
    *,
    top_u: int = 10,
) -> ProtectionSet:
    """从 base 与 D56 的完整评价一次性确定保护集合。"""
    base_worst = max(
        base_evaluation.routes, key=lambda r: (r.total_loss_db, -r.route_id)
    ).route_id
    d56_worst = max(
        d56_evaluation.routes, key=lambda r: (r.total_loss_db, -r.route_id)
    ).route_id
    u_routes = sorted(
        (r for r in base_evaluation.routes if r.geometry_kind == "u"),
        key=lambda r: (-r.crossing_count, r.route_id),
    )[:top_u]
    return ProtectionSet(base_worst, d56_worst, tuple(r.route_id for r in u_routes))


# --------------------------------------------------------------------------
# 验收规则
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class AcceptanceRule:
    """标称损耗的验收规则（相对 base）。

    ``protected_slack_db`` 默认 0（任务口径：保护路线逐路标称损耗不超过各自
    base）；把它设为正值只用于**诊断**，用来量化"如果保护约束放松一点，
    能换来多少风险下降"，不作为验收结论。
    """

    mean_slack_db: float = 0.05
    protected_ids: tuple[int, ...] = ()
    protected_slack_db: float = 0.0
    require_max_not_worse: bool = True
    require_complete: bool = True
    require_no_overlap: bool = True
    require_geometry_valid: bool = True
    require_endpoints_frozen: bool = True
    require_radius_frozen: bool = True


@dataclass
class AcceptanceResult:
    ok: bool
    reasons: list[str]
    detail: dict = field(default_factory=dict)


def _route_map(evaluation: BoardEvaluation) -> dict:
    return {record.route_id: record for record in evaluation.routes}


def acceptance_check(
    baseline: BoardEvaluation,
    trial: BoardEvaluation,
    rule: AcceptanceRule,
) -> AcceptanceResult:
    """把验收规则接到实际执行路径：任一不满足即整体拒绝（由调用方完整回滚）。"""
    reasons: list[str] = []
    detail: dict = {}
    base_summary = baseline.summary()
    trial_summary = trial.summary()

    if rule.require_complete and not trial_summary["complete_connection"]:
        reasons.append("incomplete_connection")
    if rule.require_no_overlap and (
        trial_summary["contact_overlap_count"] > 0
        or trial_summary["geometry_issue_kinds"].get("overlap")
    ):
        reasons.append("overlap")
    if rule.require_geometry_valid and trial_summary["geometry_issue_count"] > 0:
        reasons.append("geometry_issue")

    mean_delta = trial_summary["mean_loss_db"] - base_summary["mean_loss_db"]
    detail["mean_delta_db"] = mean_delta
    if mean_delta > rule.mean_slack_db + 1e-12:
        reasons.append("mean_budget_exceeded")

    max_delta = trial_summary["max_loss_db"] - base_summary["max_loss_db"]
    detail["max_delta_db"] = max_delta
    if rule.require_max_not_worse and max_delta > 1e-12:
        reasons.append("max_worse")

    base_routes = _route_map(baseline)
    trial_routes = _route_map(trial)
    if set(base_routes) != set(trial_routes):
        reasons.append("route_set_changed")
    else:
        if rule.require_endpoints_frozen:
            for rid, record in base_routes.items():
                other = trial_routes[rid]
                if (
                    abs(record.sx - other.sx) > 1e-9
                    or abs(record.sy - other.sy) > 1e-9
                    or abs(record.lx - other.lx) > 1e-9
                    or abs(record.ly - other.ly) > 1e-9
                ):
                    reasons.append("endpoint_changed")
                    detail["endpoint_changed_route"] = rid
                    break
        if rule.require_radius_frozen:
            for rid, record in base_routes.items():
                if abs(record.radius - trial_routes[rid].radius) > 1e-9:
                    reasons.append("radius_changed")
                    detail["radius_changed_route"] = rid
                    break
        protected_delta: dict[int, float] = {}
        for rid in rule.protected_ids:
            if rid not in base_routes or rid not in trial_routes:
                reasons.append("protected_route_missing_%d" % rid)
                continue
            delta = trial_routes[rid].total_loss_db - base_routes[rid].total_loss_db
            protected_delta[rid] = delta
            if delta > rule.protected_slack_db + 1e-9:
                reasons.append("protected_worse_%d" % rid)
        detail["protected_delta_db"] = protected_delta

    return AcceptanceResult(not reasons, reasons, detail)


# --------------------------------------------------------------------------
# 局部优化（带完整回滚与状态指纹核对）
# --------------------------------------------------------------------------
@dataclass
class OptimizeRecord:
    """优化过程的完整记录：候选数、接受数、拒绝原因与运行时间。"""

    candidates_tried: int = 0
    accepted: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    attempts: list[dict] = field(default_factory=list)
    evaluations: int = 0
    runtime_s: float = 0.0
    stop_reason: str = "completed"
    rollback_fingerprint_mismatches: int = 0

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1


def _pass_type_of(row) -> str:
    sy, ly = float(row["sy"]), float(row["ly"])
    if sy == 0 and ly == 0:
        return "below"
    if sy != 0 and ly != 0:
        return "above"
    if sy == 0:
        return "below2above"
    return "above2below"


def _default_targets(
    evaluation: BoardEvaluation,
    protection: ProtectionSet,
    *,
    scenario_top: int = 16,
    factor: float = DEFAULT_SCENARIO_FACTOR,
    threshold_deg: float = DEFAULT_SCENARIO_THRESHOLD_DEG,
) -> list[int]:
    """目标路线 = 保护集合 ∪ 压力情景下损耗最高的若干条（按情景损耗降序）。"""
    losses = scenario_route_losses(
        evaluation, factor=factor, threshold_deg=threshold_deg
    )
    ordered = sorted(losses, key=lambda rid: (-losses[rid], rid))
    targets: list[int] = []
    for rid in list(protection.ids()) + ordered[:scenario_top]:
        if rid not in targets:
            targets.append(rid)
    targets.sort(key=lambda rid: (-losses[rid], rid))
    return targets


def local_optimize(
    planner: Planner,
    *,
    baseline_evaluation: BoardEvaluation,
    protection: ProtectionSet,
    rule: AcceptanceRule,
    baseline_result: PlanResult,
    target_routes: list[int] | None = None,
    candidates_per_route: int = 4,
    scenario_top: int = 16,
    max_accepts: int | None = None,
    time_budget_s: float | None = None,
    rank_overrides: dict | None = None,
    factor: float = DEFAULT_SCENARIO_FACTOR,
    threshold_deg: float = DEFAULT_SCENARIO_THRESHOLD_DEG,
    progress: bool = False,
) -> tuple[BoardEvaluation, OptimizeRecord]:
    """从当前（完整合法）状态出发做有界局部重布。

    每次尝试：移除一条目标路线 → 枚举其候选 → 对每个候选（按候选评分顺序）
    **完整评价整个布局** → 若通过 :func:`acceptance_check` 且压力情景的全局
    最大损耗严格下降则接受；否则**完整回滚**并核对状态指纹。

    ``rank_overrides`` 在枚举候选期间临时覆盖 ``planner.config`` 的评分字段
    （例如把 ``small_angle_penalty_db`` 调高），使候选排序偏向"小角交叉少"
    的解 —— 这是任务要求的小规模参数扫描手段，不影响验收口径（验收始终用
    标称量的完整评价）。

    返回 ``(新的完整评价, 记录)``；若始终没有满足约束的改进，状态保持不变。
    """
    started = time.perf_counter()
    record = OptimizeRecord()
    rank_saved: dict = {}
    if rank_overrides:
        for key, value in rank_overrides.items():
            rank_saved[key] = getattr(planner.config, key)
            setattr(planner.config, key, value)
    current_eval = baseline_evaluation
    current_scenario_max = scenario_max(current_eval, factor=factor, threshold_deg=threshold_deg)
    targets = (
        target_routes
        if target_routes is not None
        else _default_targets(
            current_eval, protection, scenario_top=scenario_top,
            factor=factor, threshold_deg=threshold_deg,
        )
    )
    context = dict(planner._frozen_context or {})
    df = planner._df

    for rid in targets:
        if max_accepts is not None and record.accepted >= max_accepts:
            record.stop_reason = "max_accepts"
            break
        if time_budget_s is not None and time.perf_counter() - started > time_budget_s:
            record.stop_reason = "time_budget"
            break
        row = df.loc[rid]
        pass_type = _pass_type_of(row)
        scan_reversed = pass_type in ("above", "below2above")

        before = planner.snapshot()
        before_fingerprint = planner.state_fingerprint()
        removed = PlannerSnapshot(
            [entry for entry in before.entries if entry[0] != rid], before.context
        )
        planner.restore(removed)
        removed_fingerprint = planner.state_fingerprint()

        candidates = planner._candidates(
            row, pass_type, scan_reversed, **context.get(pass_type, {})
        )
        accepted_here = False
        for score, built, spec, track_index in candidates[: max(1, int(candidates_per_route))]:
            if time_budget_s is not None and time.perf_counter() - started > time_budget_s:
                break
            planner._commit(row, track_index, spec, built, score)
            trial_result = PlanResult(
                config=planner.config,
                routes=dict(planner.committed),
                unplaced=list(baseline_result.unplaced),
                runtime_s=0.0,
                stop_reason="trial",
                stats={},
            )
            trial_eval = planner.evaluate_plan(trial_result, "trial")
            record.candidates_tried += 1
            record.evaluations += 1
            verdict = acceptance_check(current_eval, trial_eval, rule)
            trial_scenario_max = scenario_max(trial_eval, factor=factor, threshold_deg=threshold_deg)
            objective = trial_scenario_max < current_scenario_max - 1e-9
            protected_delta = verdict.detail.get("protected_delta_db", {})
            attempt = {
                "route_id": rid,
                "pass_type": pass_type,
                "geometry": spec.kind,
                "radius": spec.radius,
                "alpha_deg": getattr(spec, "alpha_deg", 0.0),
                "t0_fraction": getattr(spec, "t0_fraction", 0.5),
                "scenario_max_db": trial_scenario_max,
                "scenario_gain_db": current_scenario_max - trial_scenario_max,
                "mean_delta_db": trial_eval.summary()["mean_loss_db"]
                - current_eval.summary()["mean_loss_db"],
                "max_delta_db": verdict.detail.get("max_delta_db"),
                "protected_max_delta_db": (
                    max(protected_delta.values()) if protected_delta else None
                ),
                "protected_worst_route": (
                    max(protected_delta, key=lambda k: (protected_delta[k], -k))
                    if protected_delta else None
                ),
                "accepted": bool(verdict.ok and objective),
                "reasons": list(verdict.reasons) + ([] if objective else ["scenario_not_improved"]),
            }
            record.attempts.append(attempt)
            if verdict.ok and objective:
                current_eval = trial_eval
                current_scenario_max = trial_scenario_max
                record.accepted += 1
                accepted_here = True
                if progress:
                    print(
                        "  [accept] route %d %s scenario_max=%.4f (-%.4f) mean%+.4f"
                        % (
                            rid, spec.kind, trial_scenario_max,
                            attempt["scenario_gain_db"], attempt["mean_delta_db"],
                        ),
                        flush=True,
                    )
                break
            for reason in attempt["reasons"]:
                record.reject(reason)
            # 完整回滚到"移除 rid 后"的状态，并与指纹核对。
            planner.restore(removed)
            if planner.state_fingerprint() != removed_fingerprint:
                record.rollback_fingerprint_mismatches += 1
                raise RuntimeError(
                    "rollback fingerprint mismatch at route %d" % rid
                )
        if not accepted_here:
            # 没有候选通过：把该路线恢复为原样（整体回到本路线尝试前的状态）。
            planner.restore(before)
            if planner.state_fingerprint() != before_fingerprint:
                record.rollback_fingerprint_mismatches += 1
                raise RuntimeError("restore fingerprint mismatch at route %d" % rid)
    record.runtime_s = time.perf_counter() - started
    for key, value in rank_saved.items():
        setattr(planner.config, key, value)
    return current_eval, record
