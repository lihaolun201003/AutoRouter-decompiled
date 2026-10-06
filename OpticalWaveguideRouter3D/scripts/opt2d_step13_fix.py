"""Step 13 补修：用修复后的几何分类与间距口径重新验证、重新布线。

修复内容（见 ``docs/reports/step_13_opt2d_fix_and_reverification.md``）：

* ``src/opt2d/intersections.py``：直线段稳健分类（尺度 + 垂距 + 投影区间），
  真实重合不再被误判为 cross；
* ``src/opt2d/spacing.py``：弧—弧最近距离补齐圆心连线上的同向极值候选；
* ``src/opt2d/{planner,evaluator}.py``：路线级 AABB 预筛改用间距阈值，
  planner 候选评分的间距违规按**路线对**计数（与报告口径一致）；
* ``src/opt2d/planner.py``：拆线重布的接受规则改为"平均严格改善 且 全局最大
  损耗不恶化"（不再用 (mean, max) 字典序）。

本脚本把 Step 13 的全部方案在修复后的同一评价器下重跑一遍（A 只重新评价，
其余方案重新布线），并输出：

``comparison.csv``            完整连接 / 端点变化 / 几何违规 / 重合 / 接触 /
                              间距违规 / 平均与最大损耗 的总表
``acceptance.json``           接受判据（相对 R5U 的平均与最大变化）
``sensitivity.csv``           <20° 交叉损耗 ×1/×2/×5/×10 的固定几何复算
``radius_compare.csv``        D56 与 F56 的逐路半径对照
``per_route_delta.csv``       与 Step 13 旧产物（outputs/opt2d_step13）的逐路差异

用法：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B scripts\\opt2d_step13_fix.py --channels 256 512
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.opt2d.evaluator import Evaluator  # noqa: E402
from src.opt2d.frozen import frozen_ports_frame  # noqa: E402
from src.opt2d.planner import PlanConfig, Planner  # noqa: E402
from src.opt2d.step13 import (  # noqa: E402
    ANGLE_BINS,
    SCHEMES,
    Step13Run,
    _comparison_row,
    _frozen_map,
    angle_histogram,
    per_route_frame,
    run_legacy_reference,
    run_scheme,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "opt2d_step13_fix"
LEGACY_OUTPUT = PROJECT_ROOT / "outputs" / "opt2d_step13"

#: 修复后重跑的基础方案（顺序固定，确定性输出）。
SCHEME_ORDER = ("A", "R5U", "D0", "D56", "F5", "F56")

#: 敏感性因子：<20° 的交叉损耗整体乘以该系数（固定几何复算，不重新布线）。
SENSITIVITY_FACTORS = (1.0, 2.0, 5.0, 10.0)
SENSITIVITY_THRESHOLD_DEG = 20.0


def run_variant(
    name: str,
    base_scheme: str,
    channels: int,
    evaluator: Evaluator,
    ports: pd.DataFrame,
    *,
    overrides: dict | None = None,
) -> Step13Run:
    """以 :data:`SCHEMES` 的某个基础方案跑一个命名变体（可覆盖任意配置）。"""
    settings = dict(SCHEMES[base_scheme])
    settings.update(overrides or {})
    settings.setdefault("position_penalty", 0.001 if channels == 256 else 0.01)
    config = PlanConfig(channels=channels, order_strategy="legacy", **settings)
    planner = Planner(config, evaluator)
    started = time.perf_counter()
    result = planner.plan(ports)
    evaluation = planner.evaluate_plan(result, name)
    evaluation.runtime_s = time.perf_counter() - started
    evaluation.notes["plan_stats"] = result.stats
    return Step13Run(
        name,
        channels,
        evaluation,
        _frozen_map(channels),
        {
            "base_scheme": base_scheme,
            "settings": {
                k: (list(v) if isinstance(v, tuple) else v) for k, v in settings.items()
            },
            "order_strategy": "legacy",
            "allow_port_reorder": False,
            "plan_stats": result.stats,
        },
        result.segments(),
    )


def sensitivity_table(
    runs: dict,
    *,
    factors=SENSITIVITY_FACTORS,
    threshold_deg: float = SENSITIVITY_THRESHOLD_DEG,
) -> pd.DataFrame:
    """<20° 交叉损耗 ×factor 的固定几何复算（只重算，不重新布线）。"""
    rows = []
    for name, run in runs.items():
        base = None
        for factor in factors:
            losses = []
            for record in run.evaluation.routes:
                crossing = sum(
                    event.loss_db * (factor if event.angle_deg < threshold_deg else 1.0)
                    for event in record.crossing_events
                )
                losses.append(record.straight_loss_db + record.bend_loss_db + crossing)
            ordered = sorted(losses)
            row = {
                "scheme": name,
                "factor": factor,
                "mean_loss_db": statistics.fmean(losses),
                "p95_loss_db": ordered[max(1, math.ceil(0.95 * len(ordered))) - 1],
                "max_loss_db": max(losses),
                "sum_loss_db": sum(losses),
                "mean_delta_vs_factor1_db": None,
                "max_delta_vs_factor1_db": None,
            }
            if factor == 1.0:
                base = row
            rows.append(row)
        if base is not None:
            for row in rows:
                if row["scheme"] != name:
                    continue
                row["mean_delta_vs_factor1_db"] = row["mean_loss_db"] - base["mean_loss_db"]
                row["max_delta_vs_factor1_db"] = row["max_loss_db"] - base["max_loss_db"]
    return pd.DataFrame(rows)


def radius_compare(runs: dict, left: str = "D56", right: str = "F56") -> pd.DataFrame:
    """逐路半径对照：结构对照（U 型 vs 自由弯角）必须核对此表。"""
    if left not in runs or right not in runs:
        return pd.DataFrame()
    a_index = runs[left].evaluation.route_index
    b_index = runs[right].evaluation.route_index
    rows = []
    for rid in sorted(set(a_index) | set(b_index)):
        a = a_index.get(rid)
        b = b_index.get(rid)
        rows.append(
            {
                "route_id": rid,
                "radius_%s_mm" % left: None if a is None else a.radius,
                "radius_%s_mm" % right: None if b is None else b.radius,
                "same_radius": None
                if a is None or b is None
                else abs(a.radius - b.radius) <= 1e-9,
                "geometry_%s" % left: None if a is None else a.geometry_kind,
                "geometry_%s" % right: None if b is None else b.geometry_kind,
            }
        )
    return pd.DataFrame(rows)


def per_route_delta(channels: int, runs: dict, old_root: Path = LEGACY_OUTPUT) -> pd.DataFrame:
    """与 Step 13 旧产物的逐路差异（loss / 几何族 / 半径 / 交叉数）。"""
    rows = []
    for name, run in runs.items():
        path = old_root / str(channels) / name / "per_route.csv"
        if not path.is_file():
            continue
        old = pd.read_csv(path).set_index("route_id")
        for record in run.evaluation.routes:
            rid = record.route_id
            old_loss = float(old.loc[rid, "total_loss_db"]) if rid in old.index else None
            rows.append(
                {
                    "scheme": name,
                    "route_id": rid,
                    "old_total_loss_db": old_loss,
                    "new_total_loss_db": record.total_loss_db,
                    "delta_loss_db": None
                    if old_loss is None
                    else record.total_loss_db - old_loss,
                    "old_geometry": None if rid not in old.index else old.loc[rid, "geometry"],
                    "new_geometry": record.geometry_kind,
                    "old_radius_mm": None if rid not in old.index else float(old.loc[rid, "radius_mm"]),
                    "new_radius_mm": record.radius,
                    "old_crossing_count": None
                    if rid not in old.index
                    else int(old.loc[rid, "crossing_count"]),
                    "new_crossing_count": record.crossing_count,
                    "changed": None
                    if old_loss is None
                    else abs(record.total_loss_db - old_loss) > 1e-9
                    or record.geometry_kind != old.loc[rid, "geometry"]
                    or abs(record.radius - float(old.loc[rid, "radius_mm"])) > 1e-9,
                }
            )
    return pd.DataFrame(rows)


def acceptance_check(runs: dict, baseline: str = "R5U") -> dict:
    """接受判据：完整连接、端点零变化、无几何违规、无重合，且平均与最大不劣化。

    平均与最大是**两个独立判据**（不是 (mean, max) 字典序）。
    """
    base = runs[baseline].summary()
    out = {}
    for name, run in runs.items():
        summary = run.summary()
        out[name] = {
            "complete_connection": summary["complete_connection"],
            "endpoint_changes": summary["endpoint_changes"],
            "geometry_issue_count": summary["geometry_issue_count"],
            "overlap_count": summary["contact_overlap_count"],
            "touch_count": summary["contact_touch_count"],
            "spacing_violation_count": summary["spacing_violation_count"],
            "mean_loss_db": summary["mean_loss_db"],
            "mean_delta_vs_%s" % baseline: summary["mean_loss_db"] - base["mean_loss_db"],
            "max_loss_db": summary["max_loss_db"],
            "max_delta_vs_%s" % baseline: summary["max_loss_db"] - base["max_loss_db"],
            "mean_not_worse": summary["mean_loss_db"] <= base["mean_loss_db"] + 1e-12,
            "max_not_worse": summary["max_loss_db"] <= base["max_loss_db"] + 1e-12,
            "no_overlap": summary["contact_overlap_count"] == 0,
        }
    return out


def comparison_table(runs: dict) -> pd.DataFrame:
    """总表：完整连接、端点变化、几何违规、重合、接触、间距违规、平均/最大损耗。"""
    rows = []
    for name in SCHEME_ORDER:
        if name not in runs:
            continue
        rows.append(_comparison_row(runs[name]))
    return pd.DataFrame(rows)


def penalty_ablation(
    channels: int,
    out_dir: Path | str = DEFAULT_OUTPUT,
    *,
    scheme: str = "F56",
    penalties=(0.02, 0.05),
    progress: bool = True,
) -> pd.DataFrame:
    """间距惩罚消融：确认旧报告 7.2 的默认值（576）到底属于哪个方案。

    对指定方案在 ``spacing_penalty_db`` 取不同值时**重新布线**，输出平均/最大
    损耗与违规计数；默认值一列取自直接对照表，供溯源。
    """
    out_dir = Path(out_dir) / str(channels)
    evaluator = Evaluator(channels)
    ports = frozen_ports_frame(channels)
    rows = []
    for penalty in penalties:
        run = run_variant(
            "%s_pen%g" % (scheme, penalty),
            scheme,
            channels,
            evaluator,
            ports,
            overrides={"spacing_penalty_db": penalty},
        )
        summary = run.summary()
        rows.append(
            {
                "scheme": scheme,
                "spacing_penalty_db": penalty,
                "mean_loss_db": summary["mean_loss_db"],
                "max_loss_db": summary["max_loss_db"],
                "spacing_violation_count": summary["spacing_violation_count"],
                "touch_count": summary["contact_touch_count"],
                "overlap_count": summary["contact_overlap_count"],
                "complete_connection": summary["complete_connection"],
            }
        )
        if progress:
            print(
                "  [%s pen=%g] mean=%.4f max=%.4f spacing=%d"
                % (
                    scheme,
                    penalty,
                    summary["mean_loss_db"],
                    summary["max_loss_db"],
                    summary["spacing_violation_count"],
                ),
                flush=True,
            )
    frame = pd.DataFrame(rows)
    frame.to_csv(
        out_dir / ("penalty_ablation_%s.csv" % scheme), index=False, encoding="utf-8-sig"
    )
    return frame


def run_fix_suite(
    channels: int,
    out_dir: Path | str = DEFAULT_OUTPUT,
    *,
    scheme_order=SCHEME_ORDER,
    match_radii: bool = True,
    progress: bool = True,
) -> dict:
    """修复后重跑一个规模的全部方案，并写出对照与敏感性产物。"""
    out_dir = Path(out_dir) / str(channels)
    out_dir.mkdir(parents=True, exist_ok=True)
    evaluator = Evaluator(channels)
    ports = frozen_ports_frame(channels)
    note = print if progress else (lambda *a, **k: None)
    runs: dict[str, Step13Run] = {}

    if "A" in scheme_order:
        note("[A] 原版几何（端点来源，仅重新评价） ...", flush=True)
        runs["A"] = run_legacy_reference(channels, evaluator)
    for name in scheme_order:
        if name == "A":
            continue
        note("[%s] 固定端点方案（修复后重新布线） ..." % name, flush=True)


        run, _ = run_scheme(name, channels, evaluator, ports, progress=progress)
        runs[name] = run

    # 公平结构对照：用 D56 的逐路半径跑自由弯角（若半径分布不同才有意义）。
    if match_radii and "D56" in runs and "F56" in runs:
        d56_radii = {r.route_id: r.radius for r in runs["D56"].evaluation.routes}
        f56_radii = {r.route_id: r.radius for r in runs["F56"].evaluation.routes}
        if any(
            abs(d56_radii.get(rid, 0.0) - f56_radii.get(rid, 0.0)) > 1e-9
            for rid in set(d56_radii) | set(f56_radii)
        ):
            note("[F56eq] 自由弯角 + D56 逐路半径（公平对照） ...", flush=True)
            runs["F56eq"] = run_variant(
                "F56eq",
                "F56",
                channels,
                evaluator,
                ports,
                overrides={"radius_overrides": d56_radii},
            )

    # ---- 产物 ----
    for name, run in runs.items():
        folder = out_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        per_route_frame(run).to_csv(folder / "per_route.csv", index=False, encoding="utf-8-sig")


        summary = run.summary()
        summary["angle_histogram"] = angle_histogram(run.evaluation)
        summary["angle_histogram_bins"] = list(ANGLE_BINS)
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
        contacts = pd.DataFrame(
            [
                {
                    "route_a": c.route_a,
                    "route_b": c.route_b,
                    "kind": c.kind,
                    "x_mm": None if c.point_a is None else c.point_a.x,
                    "y_mm": None if c.point_a is None else c.point_a.y,
                }
                for c in run.evaluation.contacts
            ]
        )
        if not contacts.empty:
            contacts.to_csv(folder / "contact_events.csv", index=False, encoding="utf-8-sig")

    table = comparison_table(runs)
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
    (out_dir / "acceptance.json").write_text(
        json.dumps(acceptance_check(runs), indent=2, ensure_ascii=False, default=float),
        encoding="utf-8",
    )
    sensitivity_table(runs).to_csv(
        out_dir / "sensitivity.csv", index=False, encoding="utf-8-sig"
    )
    radius_compare(runs).to_csv(
        out_dir / "radius_compare.csv", index=False, encoding="utf-8-sig"
    )
    per_route_delta(channels, runs).to_csv(
        out_dir / "per_route_delta.csv", index=False, encoding="utf-8-sig"
    )
    return {"runs": runs, "table": table}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Step 13 补修：重新验证与重新布线")
    parser.add_argument("--channels", type=int, nargs="+", default=[256, 512])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--no-radius-match", action="store_true")
    parser.add_argument(
        "--penalty-ablation",
        action="store_true",
        help="额外跑间距惩罚消融（F5 与 F56 各两档）",
    )
    parser.add_argument(
        "--penalty-only",
        action="store_true",
        help="只跑间距惩罚消融（跳过主对照）",
    )
    args = parser.parse_args(argv)
    for channels in args.channels:
        if channels not in (256, 512):
            print("error: 只支持 256/512", file=sys.stderr)
            return 2
        print("=== %d 通道：Step 13 补修复验 ===" % channels, flush=True)
        if not args.penalty_only:
            suite = run_fix_suite(
                channels,
                args.output,
                match_radii=not args.no_radius_match,
            )
            print(suite["table"].to_string(index=False), flush=True)
        if args.penalty_ablation or args.penalty_only:
            for scheme in ("F5", "F56"):
                print("[%s] 间距惩罚消融 ..." % scheme, flush=True)
                penalty_ablation(channels, args.output, scheme=scheme)
    return 0


if __name__ == "__main__":
    sys.exit(main())
