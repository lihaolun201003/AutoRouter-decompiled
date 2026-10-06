"""A/B/C/D 实验编排、消融与产物输出。

方案定义（相同输入、端点、板尺寸、线宽、间距与评价模型）：

``A``  原版 R5 几何（2D 项目 ``plotter_rect`` 的实际输出）。
``B``  统一半径 R6 重新布线：改变半径必须重新布线并核验几何，非法轨道由
       几何可行性检查自动下移到最近的合法轨道（B 是**参数**对照）。
``C``  候选轨道优化：R5 固定，多候选 + 联合评分（含受影响既有路线），
       叠加有界拆线重布。
``D``  局部自适应半径：候选是 (轨道, 半径) 组合，半径取自 R5/R6。

每个方案都输出逐路 CSV、汇总 JSON，并同时给出**解析物理统计**与
**原版统计**（2D 项目 ``calc_index``）两套口径。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .evaluator import BoardEvaluation, Evaluator
from .legacy_bridge import legacy_modules, legacy_ports, run_legacy_rect
from .planner import PlanConfig, Planner
from .source import legacy_bend_frame, specs_from_rect

__all__ = [
    "BoardRun",
    "run_legacy_baseline",
    "run_planner_board",
    "save_board",
    "comparison_table",
    "run_suite",
    "DEFAULT_OUTPUT",
]

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "outputs" / "opt2d"


class BoardRun:
    """一个方案的完整结果：评价 + 原版统计 + 配置记录。"""

    def __init__(
        self,
        label: str,
        channels: int,
        evaluation: BoardEvaluation,
        legacy: dict | None = None,
        config: dict | None = None,
        segments: dict | None = None,
    ) -> None:
        self.label = label
        self.channels = channels
        self.evaluation = evaluation
        self.legacy = legacy or {}
        self.config = config or {}
        self.segments = segments or {}

    def summary(self) -> dict:
        data = self.evaluation.summary()
        data.update({("legacy_" + k): v for k, v in (self.legacy.get("summary") or {}).items()})
        data["config"] = self.config
        return data

    def per_route_frame(self) -> pd.DataFrame:
        legacy_rows = self.legacy.get("per_route") or {}
        rows = []
        for record in self.evaluation.routes:
            extra = legacy_rows.get(record.route_id, {})
            rows.append(
                {
                    "route_id": record.route_id,
                    "port1": record.port1,
                    "port2": record.port2,
                    "index1": record.index1,
                    "index2": record.index2,
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
                    "legacy_length_mm": extra.get("length"),
                    "legacy_crossing_count": extra.get("crossing"),
                    "legacy_loss_db": extra.get("loss_db"),
                }
            )
        frame = pd.DataFrame(rows).sort_values("route_id").reset_index(drop=True)
        return frame


def _legacy_statistics(specs) -> dict:
    """用 2D 项目 ``calc_index`` 计算原版统计（每路 length / crossing / loss）。

    原版 ``calc_index`` 只接受单一弯曲半径；方案 D 的混合半径结果用它统计时
    取最大半径，仅作参考，严格可比的只有统一半径方案（A / B / C）。
    """
    if not specs:
        return {"per_route": {}, "summary": {}}
    radius = max(spec.radius for spec in specs)
    frame = legacy_bend_frame(specs)
    calculator = legacy_modules()["waveguide_calculator"]
    out = calculator.calc_index(
        frame.copy(),
        loss=None,
        line_width=0.05,
        bend_radius=float(radius),
        height=150,
        width=150,
    )
    per_route = {
        int(row.Index): {
            "length": float(row.length),
            "crossing": int(row.crossing),
            "loss_db": -float(row.loss),
        }
        for row in out.itertuples()
    }
    losses = [-float(v) for v in out["loss"]]
    return {
        "per_route": per_route,
        "summary": {
            "mean_loss_db": sum(losses) / len(losses),
            "max_loss_db": max(losses),
            "min_loss_db": min(losses),
            "mean_crossing_count": float(out["crossing"].mean()),
            "max_crossing_count": int(out["crossing"].max()),
            "mean_length_mm": float(out["length"].mean()),
            "bend_radius_used": float(radius),
        },
    }


def run_legacy_baseline(channels: int, radius: float, evaluator: Evaluator, label: str) -> BoardRun:
    """方案 A（以及 B 的 R6 对照）：直接使用 2D 项目原版布线的实际输出。"""
    started = time.perf_counter()
    _, rect = run_legacy_rect(channels, radius)
    specs = specs_from_rect(rect, radius)
    segments, issues, unplaced = evaluator.build(specs)
    evaluation = evaluator.evaluate(
        specs,
        label=label,
        segments=segments,
        issues=issues,
        unplaced=unplaced,
        runtime_s=time.perf_counter() - started,
    )
    legacy = _legacy_statistics(specs)
    return BoardRun(
        label,
        channels,
        evaluation,
        legacy,
        {"kind": "legacy", "radius": radius, "source": "plotter_rect"},
        segments,
    )


def run_planner_board(
    channels: int,
    evaluator: Evaluator,
    label: str,
    *,
    candidate_limit: int,
    order_strategy: str = "legacy",
    radii: tuple[float, ...] = (5.0,),
    radius_policy: str = "fixed",
    position_penalty: float = 0.0,
    refine_rounds: int = 0,
    rip_count: int | None = None,
    progress: bool = False,
    with_legacy: bool = False,
) -> tuple[BoardRun, dict]:
    """方案 B/C/D：opt2d 的候选轨迹/半径布线器 + 可选拆线重布。"""
    started = time.perf_counter()
    ports = legacy_ports(channels)
    config = PlanConfig(
        channels=channels,
        candidate_limit=candidate_limit,
        order_strategy=order_strategy,
        radii=tuple(radii),
        radius_policy=radius_policy,
        position_penalty=position_penalty,
    )
    planner = Planner(config, evaluator)
    result = planner.plan(ports)
    record = {"refine": None}
    if refine_rounds > 0:
        result, evaluation, record["refine"] = planner.refine(
            result,
            label=label,
            rounds=refine_rounds,
            rip_count=rip_count,
            progress=progress,
        )
    else:
        evaluation = planner.evaluate_plan(result, label)
    evaluation.notes["refine"] = record["refine"]
    evaluation.notes["plan_stats"] = result.stats
    evaluation.runtime_s = time.perf_counter() - started
    specs = result.specs()
    legacy = _legacy_statistics(specs) if with_legacy else {"per_route": {}, "summary": {}}
    settings = {
        "kind": "planner",
        "candidate_limit": candidate_limit,
        "order_strategy": order_strategy,
        "radii": list(radii),
        "radius_policy": radius_policy,
        "position_penalty": position_penalty,
        "refine_rounds": refine_rounds,
        "rip_count": rip_count,
        "plan_stats": result.stats,
    }
    return (
        BoardRun(label, channels, evaluation, legacy, settings, result.segments()),
        record,
    )


def save_board(run: BoardRun, out_dir: Path, name: str | None = None) -> Path:
    """写出逐路 CSV 与汇总 JSON。"""
    folder = Path(out_dir) / (name or run.label)
    folder.mkdir(parents=True, exist_ok=True)
    frame = run.per_route_frame()
    frame.to_csv(folder / "per_route.csv", index=False, encoding="utf-8-sig")
    summary = run.summary()
    (folder / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=float), encoding="utf-8"
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
    spacing = pd.DataFrame(
        [
            {
                "route_a": e.route_a,
                "route_b": e.route_b,
                "distance_mm": e.distance_mm,
                "x_mm": e.x,
                "y_mm": e.y,
            }
            for e in run.evaluation.spacing_events
        ]
    )
    if not spacing.empty:
        spacing.to_csv(folder / "spacing_events.csv", index=False, encoding="utf-8-sig")
    return folder


COMPARISON_FIELDS = (
    "label",
    "route_count",
    "unplaced_count",
    "complete_connection",
    "mean_loss_db",
    "p95_loss_db",
    "max_loss_db",
    "worst_route_id",
    "mean_straight_loss_db",
    "mean_bend_loss_db",
    "mean_crossing_loss_db",
    "mean_total_length_mm",
    "sum_total_length_mm",
    "unique_crossing_events",
    "per_route_crossing_events",
    "min_crossing_angle_deg",
    "spacing_violation_count",
    "geometry_issue_count",
    "radius_distribution",
    "runtime_s",
    "stop_reason",
    "legacy_mean_loss_db",
    "legacy_max_loss_db",
    "legacy_mean_crossing_count",
)


def comparison_table(runs: list[BoardRun]) -> pd.DataFrame:
    rows = []
    for run in runs:
        summary = run.summary()
        rows.append({field: summary.get(field) for field in COMPARISON_FIELDS})
    return pd.DataFrame(rows)


def run_suite(
    channels: int,
    out_dir: Path | str = DEFAULT_OUTPUT,
    *,
    evaluator: Evaluator | None = None,
    include_sensitivity: bool = True,
    refine_rounds: int = 3,
    progress: bool = True,
) -> dict:
    """跑完整 A/B/C/D 对照（含消融），返回各次运行的 BoardRun。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    evaluator = evaluator or Evaluator(channels)
    penalty = 0.001 if channels == 256 else 0.01
    runs: dict[str, BoardRun] = {}
    extra: dict[str, dict] = {}

    def note(message: str) -> None:
        if progress:
            print(message, flush=True)

    note("[A] 原版 R5 ...")
    runs["A"] = run_legacy_baseline(channels, 5.0, evaluator, "A-R5-legacy")
    save_board(runs["A"], out_dir, "A")
    note("    mean=%.5f max=%.5f" % (runs["A"].summary()["mean_loss_db"], runs["A"].summary()["max_loss_db"]))

    note("[B] 统一半径 R6 重布线 ...")
    runs["B"], extra["B"] = run_planner_board(
        channels, evaluator, "B-R6", candidate_limit=1, radii=(6.0,), with_legacy=True
    )
    save_board(runs["B"], out_dir, "B")
    note("    mean=%.5f unplaced=%d" % (runs["B"].summary()["mean_loss_db"], runs["B"].summary()["unplaced_count"]))

    note("[C] 候选轨道优化（R5 固定，多候选 + 拆线重布）...")
    runs["C"], extra["C"] = run_planner_board(
        channels,
        evaluator,
        "C-R5-cand",
        candidate_limit=8,
        radii=(5.0,),
        position_penalty=penalty,
        refine_rounds=refine_rounds,
        rip_count=max(1, channels // 20),
        progress=progress,
        with_legacy=True,
    )
    save_board(runs["C"], out_dir, "C")
    note("    mean=%.5f unplaced=%d" % (runs["C"].summary()["mean_loss_db"], runs["C"].summary()["unplaced_count"]))

    note("[D] 自适应半径（R5/R6 联合选择 + 拆线重布）...")
    runs["D"], extra["D"] = run_planner_board(
        channels,
        evaluator,
        "D-R5R6",
        candidate_limit=8,
        radii=(5.0, 6.0),
        radius_policy="adaptive",
        position_penalty=penalty,
        refine_rounds=refine_rounds,
        rip_count=max(1, channels // 20),
        progress=progress,
        with_legacy=True,
    )
    save_board(runs["D"], out_dir, "D")
    note("    mean=%.5f unplaced=%d radii=%s"
         % (runs["D"].summary()["mean_loss_db"], runs["D"].summary()["unplaced_count"],
            runs["D"].summary()["radius_distribution"]))

    table = comparison_table(list(runs.values()))
    table.to_csv(out_dir / "comparison.csv", index=False, encoding="utf-8-sig")
    (out_dir / "comparison.json").write_text(
        json.dumps(
            {key: run.summary() for key, run in runs.items()},
            indent=2,
            ensure_ascii=False,
            default=float,
        ),
        encoding="utf-8",
    )
    if include_sensitivity:
        extra["sensitivity"] = sensitivity_study(channels, evaluator, out_dir, penalty)
    (out_dir / "sensitivity.json").write_text(
        json.dumps(extra.get("sensitivity", {}), indent=2, ensure_ascii=False, default=float),
        encoding="utf-8",
    )
    return {"runs": runs, "table": table, "extra": extra}


def sensitivity_study(channels: int, evaluator: Evaluator, out_dir: Path, penalty: float) -> dict:
    """消融：候选数量、布线顺序、局部重布、位置正则、自适应半径。"""
    results: dict[str, dict] = {}
    save_folder = Path(out_dir) / "sensitivity"
    save_folder.mkdir(parents=True, exist_ok=True)

    def record(name: str, refine_rounds: int = 0, **kwargs):
        run, extra = run_planner_board(
            channels,
            evaluator,
            name,
            refine_rounds=refine_rounds,
            rip_count=max(1, channels // 20) if refine_rounds else None,
            **kwargs,
        )
        summary = run.summary()
        results[name] = {
            key: summary.get(key)
            for key in (
                "mean_loss_db", "p95_loss_db", "max_loss_db", "unplaced_count",
                "unique_crossing_events", "min_crossing_angle_deg",
                "spacing_violation_count", "radius_distribution", "runtime_s",
            )
        }
        results[name]["refine"] = extra.get("refine")
        save_board(run, save_folder, name)
        print("    [消融] %-20s mean=%.5f unplaced=%d" % (
            name, results[name]["mean_loss_db"] or float('nan'),
            results[name]["unplaced_count"]), flush=True)
        return run

    # 候选数量（K）
    for limit in (1, 4, 8, 16):
        record("cand_k%d" % limit, candidate_limit=limit, radii=(5.0,),
               position_penalty=penalty)
    # 布线顺序
    for strategy in ("span", "congestion"):
        record("order_%s" % strategy, candidate_limit=8, order_strategy=strategy,
               radii=(5.0,), position_penalty=penalty)
    # 局部拆线重布（同一配置下开/关）
    record("refine_on", refine_rounds=3, candidate_limit=8, radii=(5.0,),
           position_penalty=penalty)
    # 位置正则（扫描顺序偏移惩罚）
    for value in (0.0, 0.001, 0.01, 0.05):
        record("penalty_%g" % value, candidate_limit=8, radii=(5.0,),
               position_penalty=value)
    # 半径策略
    record("radius_fixed_R6", candidate_limit=8, radii=(6.0,),
           position_penalty=penalty)
    record("radius_adaptive", candidate_limit=8, radii=(5.0, 6.0),
           radius_policy="adaptive", position_penalty=penalty)
    return results
