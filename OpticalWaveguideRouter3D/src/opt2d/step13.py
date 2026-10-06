"""Step 13 实验编排：修复后的固定端点对照、D0 半径回退与自由弯角 S 形。

与 Step 12 的关系：

* Step 12 的代码与产物保持原样（`src/opt2d/experiments.py`、`outputs/opt2d/`）；
* 本模块复用 Step 13 修复后的组件：冻结端点（:mod:`src.opt2d.frozen`）、
  完整快照/回滚与冻结 pass 边界（:class:`planner.Planner`）、
  修好的间距计算与接触/重合分类（:mod:`src.opt2d.spacing`）、
  稳健求交封装（:mod:`src.opt2d.intersections`）、
  自由弯角几何（:mod:`src.opt2d.freeform`）。

方案（全部使用**同一组冻结端点** = 方案 A 最终几何的 ``sx/sy/lx/ly``）：

``A``     原版几何本身（端点来源，仅作参照，不参与"重新布线"比较）
``R5U``   固定端点 + U 型 + R5
``D0``    固定端点 + U 型 + 每路优先 R6、几何不可行才回退 R5，单候选、无搜索
``D56``   固定端点 + U 型 + 多候选自适应 R5/R6
``F5``    固定端点 + 跨侧自由弯角 S 形（R5），同侧保留 U 型
``F56``   同上，半径候选 R5/R6
"""

from __future__ import annotations

import json
import math
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .evaluator import BoardEvaluation, Evaluator
from .frozen import frozen_ports_frame
from .legacy_bridge import run_legacy_rect
from .planner import PlanConfig, Planner
from .source import specs_from_rect

__all__ = [
    "SCHEMES",
    "Step13Run",
    "run_legacy_reference",
    "run_scheme",
    "per_route_frame",
    "endpoint_changes",
    "angle_histogram",
    "crossing_sensitivity",
    "run_step13",
    "DEFAULT_OUTPUT",
]

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "outputs" / "opt2d_step13"

ANGLE_BINS: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 90.0)

#: 方案默认参数。``candidate_limit`` 是每个半径的候选名额；
#: ``position_penalty`` 按规模在 :func:`run_step13` 里细化。
SCHEMES: dict[str, dict] = {
    "R5U": dict(
        candidate_limit=8, radii=(5.0,), radius_policy="fixed", enable_freeform=False
    ),
    "D0": dict(
        candidate_limit=1, radii=(6.0, 5.0), radius_policy="fallback", enable_freeform=False
    ),
    "D56": dict(
        candidate_limit=8, radii=(5.0, 6.0), radius_policy="adaptive", enable_freeform=False
    ),
    "F5": dict(
        candidate_limit=8, radii=(5.0,), radius_policy="fixed", enable_freeform=True,
        freeform_shortlist=8,
    ),
    "F56": dict(
        candidate_limit=8, radii=(5.0, 6.0), radius_policy="adaptive", enable_freeform=True,
        freeform_shortlist=8,
    ),
}


@dataclass
class Step13Run:
    """一个方案的结果：评价 + 配置 + 与冻结端点的对照。"""

    name: str
    channels: int
    evaluation: BoardEvaluation
    frozen_endpoints: dict
    config: dict = field(default_factory=dict)
    segments: dict = field(default_factory=dict)

    def summary(self) -> dict:
        data = self.evaluation.summary()
        data["endpoint_changes"] = self.endpoint_changes()
        data["geometry_family"] = dict(
            Counter(record.geometry_kind for record in self.evaluation.routes)
        )
        data["config"] = self.config
        return data

    def endpoint_changes(self) -> int:
        changed = 0
        for record in self.evaluation.routes:
            frozen = self.frozen_endpoints.get(record.route_id)
            if frozen is None:
                changed += 1
                continue
            if (
                abs(record.sx - frozen["sx"]) > 1e-9
                or abs(record.sy - frozen["sy"]) > 1e-9
                or abs(record.lx - frozen["lx"]) > 1e-9
                or abs(record.ly - frozen["ly"]) > 1e-9
            ):
                changed += 1
        return changed


def _frozen_map(channels: int) -> dict:
    frame = frozen_ports_frame(channels)
    return {
        int(rid): {
            "sx": float(row.sx),
            "sy": float(row.sy),
            "lx": float(row.lx),
            "ly": float(row.ly),
        }
        for rid, row in frame.iterrows()
    }


def run_legacy_reference(channels: int, evaluator: Evaluator, radius: float = 5.0) -> Step13Run:
    """方案 A 本身的解析评价（端点来源，仅作参照）。"""
    started = time.perf_counter()
    _, rect = run_legacy_rect(channels, radius)
    specs = specs_from_rect(rect, radius)
    segments, issues, unplaced = evaluator.build(specs)
    evaluation = evaluator.evaluate(
        specs,
        label="A",
        segments=segments,
        issues=issues,
        unplaced=unplaced,
        runtime_s=time.perf_counter() - started,
    )
    return Step13Run(
        "A", channels, evaluation, _frozen_map(channels), {"kind": "legacy"}, segments
    )


def run_scheme(
    name: str,
    channels: int,
    evaluator: Evaluator,
    ports: pd.DataFrame,
    *,
    overrides: dict | None = None,
    progress: bool = False,
) -> tuple[Step13Run, Planner]:
    """按 :data:`SCHEMES` 跑一个方案（冻结端点、不交换端口）。"""
    settings = dict(SCHEMES[name])
    settings.update(overrides or {})
    settings.setdefault("position_penalty", 0.001 if channels == 256 else 0.01)
    config = PlanConfig(channels=channels, order_strategy="legacy", **settings)
    planner = Planner(config, evaluator)
    started = time.perf_counter()
    result = planner.plan(ports)
    evaluation = planner.evaluate_plan(result, name)
    evaluation.runtime_s = time.perf_counter() - started
    evaluation.notes["plan_stats"] = result.stats
    run = Step13Run(
        name,
        channels,
        evaluation,
        _frozen_map(channels),
        {
            "settings": {k: (list(v) if isinstance(v, tuple) else v) for k, v in settings.items()},
            "order_strategy": "legacy",
            "allow_port_reorder": False,
            "plan_stats": result.stats,
        },
        result.segments(),
    )
    if progress:
        summary = evaluation.summary()
        print(
            "  [%s] mean=%.5f max=%.5f unplaced=%d"
            % (name, summary["mean_loss_db"], summary["max_loss_db"], summary["unplaced_count"]),
            flush=True,
        )
    return run, planner


def per_route_frame(run: Step13Run) -> pd.DataFrame:
    """逐路 CSV；含几何族、自由弯角参数、损耗分解与几何合法性。"""
    rows = []
    for record in run.evaluation.routes:
        rows.append(
            {
                "route_id": record.route_id,
                "port1": record.port1,
                "port2": record.port2,
                "index1": record.index1,
                "index2": record.index2,
                "geometry": record.geometry_kind,
                "alpha_deg": record.alpha_deg,
                "t0_fraction": record.t0_fraction,
                "sx_mm": record.sx,
                "sy_mm": record.sy,
                "lx_mm": record.lx,
                "ly_mm": record.ly,
                "track_y_mm": record.track_y,
                "radius_mm": record.radius,
                "dx_mm": record.dx,
                "straight_length_mm": record.straight_length_mm,
                "arc_length_mm": record.arc_length_mm,
                "total_length_mm": record.total_length_mm,
                "bend_count": record.bend_count,
                "bend_total_deg": sum(record.bend_angles_deg),
                "crossing_count": record.crossing_count,
                "min_crossing_angle_deg": (
                    min(e.angle_deg for e in record.crossing_events)
                    if record.crossing_events
                    else None
                ),
                "straight_loss_db": record.straight_loss_db,
                "bend_loss_db": record.bend_loss_db,
                "crossing_loss_db": record.crossing_loss_db,
                "total_loss_db": record.total_loss_db,
                "geometry_valid": record.is_geometrically_valid,
                "geometry_issue_kinds": ";".join(sorted({i.kind for i in record.issues})),
            }
        )
    return pd.DataFrame(rows).sort_values("route_id").reset_index(drop=True)


def angle_histogram(evaluation: BoardEvaluation, bins=ANGLE_BINS) -> list[int]:
    """交叉角分布（``len(bins)-1`` 个区间）。"""
    counts = [0] * (len(bins) - 1)
    for event in evaluation.events:
        for index in range(len(bins) - 1):
            if bins[index] <= event.angle_deg < bins[index + 1] or (
                index == len(bins) - 2 and event.angle_deg == bins[-1]
            ):
                counts[index] += 1
                break
    return counts


def crossing_sensitivity(
    evaluation: BoardEvaluation,
    *,
    threshold_deg: float = 20.0,
    factors: tuple[float, ...] = (0.5, 1.0, 2.0),
) -> dict:
    """小角度交叉损耗的敏感性：把小于阈值的事件损耗乘以系数后重算均值/最大。

    只重算，不重新布线 —— 用来回答"如果数字化交叉表在小角度处偏差 2 倍，
    结论是否还成立"。
    """
    out: dict[str, dict] = {}
    for factor in factors:
        losses = []
        for record in evaluation.routes:
            crossing = sum(
                event.loss_db * (factor if event.angle_deg < threshold_deg else 1.0)
                for event in record.crossing_events
            )
            losses.append(record.straight_loss_db + record.bend_loss_db + crossing)
        ordered = sorted(losses)
        out["factor_%g" % factor] = {
            "mean_loss_db": statistics.fmean(losses),
            "p95_loss_db": ordered[max(1, math.ceil(0.95 * len(ordered))) - 1],
            "max_loss_db": max(losses),
        }
    return out


def _comparison_row(run: Step13Run) -> dict:
    summary = run.summary()
    evaluation = run.evaluation
    return {
        "scheme": run.name,
        "routes": summary["route_count"],
        "unplaced": summary["unplaced_count"],
        "complete_connection": summary["complete_connection"],
        "endpoint_changes": summary["endpoint_changes"],
        "mean_loss_db": summary["mean_loss_db"],
        "p95_loss_db": summary["p95_loss_db"],
        "max_loss_db": summary["max_loss_db"],
        "worst_route_id": summary["worst_route_id"],
        "mean_straight_loss_db": summary["mean_straight_loss_db"],
        "mean_bend_loss_db": summary["mean_bend_loss_db"],
        "mean_crossing_loss_db": summary["mean_crossing_loss_db"],
        "sum_total_length_mm": summary["sum_total_length_mm"],
        "mean_bend_total_deg": statistics.fmean(
            sum(record.bend_angles_deg) for record in evaluation.routes
        ),
        "unique_crossing_events": summary["unique_crossing_events"],
        "min_crossing_angle_deg": summary["min_crossing_angle_deg"],
        "crossings_under_10deg": sum(angle_histogram(evaluation)[:2]),
        "spacing_violation_count": summary["spacing_violation_count"],
        "min_spacing_mm": summary["min_spacing_mm"],
        "contact_touch_count": summary["contact_touch_count"],
        "contact_overlap_count": summary["contact_overlap_count"],
        "geometry_issue_count": summary["geometry_issue_count"],
        "geometry_issue_kinds": json.dumps(summary["geometry_issue_kinds"], ensure_ascii=False),
        "radius_distribution": json.dumps(
            {str(k): v for k, v in summary["radius_distribution"].items()}, ensure_ascii=False
        ),
        "runtime_s": summary["runtime_s"],
    }


def run_step13(
    channels: int,
    out_dir: Path | str = DEFAULT_OUTPUT,
    *,
    evaluator: Evaluator | None = None,
    schemes: tuple[str, ...] = ("R5U", "D0", "D56", "F5", "F56"),
    progress: bool = True,
) -> dict:
    """跑一个规模的完整 Step 13 对照，写出逐路 CSV、汇总 JSON、对照表与敏感性。"""
    out_dir = Path(out_dir) / str(channels)
    out_dir.mkdir(parents=True, exist_ok=True)
    evaluator = evaluator or Evaluator(channels)
    ports = frozen_ports_frame(channels)
    runs: dict[str, Step13Run] = {}

    note = print if progress else (lambda *args, **kwargs: None)
    note("[A] 原版几何（端点来源） ...", flush=True)
    runs["A"] = run_legacy_reference(channels, evaluator)
    for name in schemes:
        note("[%s] 固定端点方案 ..." % name, flush=True)
        run, _ = run_scheme(name, channels, evaluator, ports, progress=progress)
        runs[name] = run

    rows = []
    for name, run in runs.items():
        rows.append(_comparison_row(run))
        folder = out_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        per_route_frame(run).to_csv(
            folder / "per_route.csv", index=False, encoding="utf-8-sig"
        )
        summary = run.summary()
        summary["angle_histogram"] = angle_histogram(run.evaluation)
        summary["angle_histogram_bins"] = list(ANGLE_BINS)
        summary["crossing_sensitivity"] = crossing_sensitivity(run.evaluation)
        (folder / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, default=float),
            encoding="utf-8",
        )
        events = pd.DataFrame(
            [
                {
                    "route_a": e.route_a,
                    "route_b": e.route_b,
                    "x_mm": e.x,
                    "y_mm": e.y,
                    "angle_deg": e.angle_deg,
                    "loss_db": e.loss_db,
                }
                for e in run.evaluation.events
            ]
        )
        if not events.empty:
            events.to_csv(folder / "crossing_events.csv", index=False, encoding="utf-8-sig")

    table = pd.DataFrame(rows)
    table.to_csv(out_dir / "comparison.csv", index=False, encoding="utf-8-sig")
    (out_dir / "comparison.json").write_text(
        json.dumps(
            {name: run.summary() for name, run in runs.items()},
            indent=2,
            ensure_ascii=False,
            default=float,
        ),
        encoding="utf-8",
    )
    return {"runs": runs, "table": table, "ports": ports}


def worst_route_tracking(runs: dict) -> pd.DataFrame:
    """以方案 A 的最差路线为基准，追踪同一条路线在各方案中的损耗。"""
    base = runs.get("A")
    if base is None:
        return pd.DataFrame()
    worst_id = max(
        base.evaluation.routes, key=lambda r: (r.total_loss_db, -r.route_id)
    ).route_id
    rows = []
    for name, run in runs.items():
        record = run.evaluation.route_index.get(worst_id)
        if record is None:
            continue
        rows.append(
            {
                "scheme": name,
                "worst_route_id_of_A": worst_id,
                "total_loss_db": record.total_loss_db,
                "straight_loss_db": record.straight_loss_db,
                "bend_loss_db": record.bend_loss_db,
                "crossing_loss_db": record.crossing_loss_db,
                "crossing_count": record.crossing_count,
                "bend_total_deg": sum(record.bend_angles_deg),
            }
        )
    return pd.DataFrame(rows)


def acceptance_check(runs: dict, baseline: str = "R5U") -> dict:
    """接受判据：平均与最大都不劣化、完整连接、无几何违规、无重合。"""
    base = runs[baseline].summary()
    out = {}
    for name, run in runs.items():
        summary = run.summary()
        out[name] = {
            "complete_connection": summary["complete_connection"],
            "endpoint_changes": summary["endpoint_changes"],
            "geometry_issue_count": summary["geometry_issue_count"],
            "overlap_count": summary["contact_overlap_count"],
            "mean_loss_db": summary["mean_loss_db"],
            "mean_delta_vs_%s" % baseline: summary["mean_loss_db"] - base["mean_loss_db"],
            "max_loss_db": summary["max_loss_db"],
            "max_delta_vs_%s" % baseline: summary["max_loss_db"] - base["max_loss_db"],
            "mean_not_worse": summary["mean_loss_db"] <= base["mean_loss_db"] + 1e-12,
            "max_not_worse": summary["max_loss_db"] <= base["max_loss_db"] + 1e-12,
        }
    return out


def render_step13(runs: dict, out_dir: Path, channels: int) -> list:
    """复用 Step 12 的绘图函数（接口一致），生成对照图与最差路线局部图。"""
    import sys

    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from src.opt2d import report as step_report

    out_dir = Path(out_dir)
    figures = []
    figures.append(
        step_report.plot_loss_distribution(runs, out_dir / "loss_distribution.png", "（%d 通道）" % channels)
    )
    figures.append(
        step_report.plot_loss_breakdown(runs, out_dir / "loss_breakdown.png", "（%d 通道）" % channels)
    )
    figures.append(
        step_report.plot_metric_bars(runs, out_dir / "metric_comparison.png", "（%d 通道）" % channels)
    )
    for key, run in sorted(runs.items()):
        figures.append(step_report.plot_worst_route(run, out_dir / ("worst_route_%s.png" % key)))
    return figures
