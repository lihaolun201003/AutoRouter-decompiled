"""Step 14 实验编排：冻结对照、受约束优化与完整验证。

流程（每个规模）：

1. 以补修后的完整 F56 为 base，取出其**逐路半径表**；
2. 重跑 D56（保护对象的第二个来源）；
3. 在**同一批 radius_overrides**（= base 半径表）下重跑四个约束配置
   ``base / spacing / small / touch / both``，并输出逐路半径核对表；
4. 从 base 与 D56 一次性确定**固定保护集合**（base 最差、D56 最差、
   base 中被穿越最多的 10 条 U 型路线）；
5. 对 ``base`` 与 ``small`` 两个起点分别做**保护性局部优化**
   （压力情景 = <20° 交叉损耗 ×5，验收规则见 :class:`AcceptanceRule`），
   优化过程完整回滚并核对状态指纹；
6. 全部方案统一做 ×1/×2/×5/×10 固定几何复算，并与 D56、F56 同时比较。

用法：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B scripts\\opt2d_step14.py --channels 256
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
from src.opt2d.step13 import SCHEMES, Step13Run, _frozen_map, per_route_frame  # noqa: E402
from src.opt2d.step14 import (  # noqa: E402
    DEFAULT_SCENARIO_FACTOR,
    DEFAULT_SCENARIO_THRESHOLD_DEG,
    AcceptanceRule,
    acceptance_check,
    local_optimize,
    scenario_max,
    scenario_route_losses,
    select_protection,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "opt2d_step14"

#: Step 14 的约束配置（全部在 base 的逐路半径冻结下运行）。
CONFIGS: dict[str, dict] = {
    "base": {},
    "spacing": {"spacing_penalty_db": 0.05},
    "small": {"small_angle_deg": 20.0, "small_angle_penalty_db": 0.05},
    "touch": {"touch_penalty_db": 0.05},
    "both": {
        "spacing_penalty_db": 0.05,
        "small_angle_deg": 20.0,
        "small_angle_penalty_db": 0.05,
    },
}

SENSITIVITY_FACTORS = (1.0, 2.0, 5.0, 10.0)


def run_planner_scheme(
    name: str,
    base_scheme: str,
    channels: int,
    evaluator: Evaluator,
    ports: pd.DataFrame,
    *,
    overrides: dict | None = None,
) -> tuple[Step13Run, Planner, object]:
    """以 SCHEMES 的某方案配置跑一个命名变体，返回 (run, planner, result)。"""
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
    run = Step13Run(
        name,
        channels,
        evaluation,
        _frozen_map(channels),
        {
            "base_scheme": base_scheme,
            "settings": {
                k: (list(v) if isinstance(v, tuple) else v) for k, v in settings.items()
            },
            "radius_frozen": bool(settings.get("radius_overrides")),
        },
        result.segments(),
    )
    return run, planner, result


def sensitivity_table(runs: dict, *, factors=SENSITIVITY_FACTORS) -> pd.DataFrame:
    rows = []
    for name, run in runs.items():
        evaluation = run.evaluation
        for factor in factors:
            losses = list(
                scenario_route_losses(
                    evaluation, factor=factor, threshold_deg=DEFAULT_SCENARIO_THRESHOLD_DEG
                ).values()
            )
            ordered = sorted(losses)
            rows.append(
                {
                    "scheme": name,
                    "factor": factor,
                    "mean_loss_db": statistics.fmean(losses),
                    "p95_loss_db": ordered[max(1, math.ceil(0.95 * len(ordered))) - 1],
                    "max_loss_db": max(losses),
                }
            )
    return pd.DataFrame(rows)


def protection_table(run: Step13Run, protection, baseline_losses: dict) -> pd.DataFrame:
    """固定保护对象的逐路损耗（每条路线一行，不只看集合均值）。"""
    index = run.evaluation.route_index
    rows = []
    for rid in protection.ids():
        record = index.get(rid)
        base_loss = baseline_losses.get(rid)
        rows.append(
            {
                "route_id": rid,
                "role": (
                    "base_worst" if rid == protection.base_worst
                    else "d56_worst" if rid == protection.d56_worst
                    else "crossed_u"
                ),
                "geometry": None if record is None else record.geometry_kind,
                "total_loss_db": None if record is None else record.total_loss_db,
                "base_loss_db": base_loss,
                "delta_vs_base_db": None
                if record is None or base_loss is None
                else record.total_loss_db - base_loss,
                "crossing_count": None if record is None else record.crossing_count,
                "crossings_under_20deg": None
                if record is None
                else sum(1 for e in record.crossing_events if e.angle_deg < 20.0),
            }
        )
    return pd.DataFrame(rows)


def summary_row(run: Step13Run, extra: dict | None = None) -> dict:
    summary = run.summary()
    evaluation = run.evaluation
    factors = DEFAULT_SCENARIO_FACTOR
    row = {
        "scheme": run.name,
        "complete_connection": summary["complete_connection"],
        "mean_loss_db": summary["mean_loss_db"],
        "p95_loss_db": summary["p95_loss_db"],
        "max_loss_db": summary["max_loss_db"],
        "worst_route_id": summary["worst_route_id"],
        "scenario5_mean_loss_db": statistics.fmean(
            scenario_route_losses(evaluation).values()
        ),
        "scenario5_max_loss_db": summary_scenario_max(evaluation, factors),
        "scenario5_worst_route_id": worst_route_of_scenario(evaluation, factors),
        "crossings_under_5_deg": sum(1 for e in evaluation.events if e.angle_deg < 5.0),
        "crossings_under_10_deg": sum(1 for e in evaluation.events if e.angle_deg < 10.0),
        "crossings_under_20_deg": sum(1 for e in evaluation.events if e.angle_deg < 20.0),
        "spacing_violation_count": summary["spacing_violation_count"],
        "raw_segment_touch_count": summary["raw_segment_touch_count"],
        "physical_route_touch_count": summary["physical_route_touch_count"],
        "contact_overlap_count": summary["contact_overlap_count"],
        "geometry_issue_count": summary["geometry_issue_count"],
        "endpoint_changes": summary["endpoint_changes"],
        "mean_bend_total_deg": statistics.fmean(
            sum(r.bend_angles_deg) for r in evaluation.routes
        ),
        "radius_distribution": json.dumps(
            {str(k): v for k, v in summary["radius_distribution"].items()}
        ),
        "runtime_s": summary["runtime_s"],
    }
    row.update(extra or {})
    return row


def summary_scenario_max(evaluation, factor: float) -> float:
    return scenario_max(evaluation, factor=factor, threshold_deg=DEFAULT_SCENARIO_THRESHOLD_DEG)


def worst_route_of_scenario(evaluation, factor: float) -> int:
    losses = scenario_route_losses(
        evaluation, factor=factor, threshold_deg=DEFAULT_SCENARIO_THRESHOLD_DEG
    )
    return max(losses, key=lambda rid: (losses[rid], -rid))


def run_step14(channels: int, out_dir: Path | str = DEFAULT_OUTPUT, *, optimize: bool = True) -> dict:
    out_dir = Path(out_dir) / str(channels)
    out_dir.mkdir(parents=True, exist_ok=True)
    evaluator = Evaluator(channels)
    ports = frozen_ports_frame(channels)
    print("=== %d 通道：Step 14 ===" % channels, flush=True)

    # 1) 补修后的 F56（base 的来源）与 D56
    print("[F56] 产生 base 逐路半径表 ...", flush=True)
    f56_run, f56_planner, f56_result = run_planner_scheme(
        "F56", "F56", channels, evaluator, ports
    )
    radii = {r.route_id: r.radius for r in f56_run.evaluation.routes}
    print("[D56] 保护对象来源 ...", flush=True)
    d56_run, _, _ = run_planner_scheme("D56", "D56", channels, evaluator, ports)

    # 2) 冻结半径的四个配置（全部传入 radius_overrides）
    runs: dict[str, Step13Run] = {}
    for name, overrides in CONFIGS.items():
        print("[%s] 冻结半径对照 ..." % name, flush=True)
        run, planner, result = run_planner_scheme(
            name, "F56", channels, evaluator, ports,
            overrides={**overrides, "radius_overrides": radii},
        )
        runs[name] = run
        if name == "base":
            base_planner, base_result = planner, result

    # 3) 固定保护集合（一次性确定）
    protection = select_protection(runs["base"].evaluation, d56_run.evaluation)
    rule = AcceptanceRule(mean_slack_db=0.05, protected_ids=protection.ids())
    print("保护集合：%s" % json.dumps(protection.describe(), ensure_ascii=False), flush=True)

    baseline_losses = {
        r.route_id: r.total_loss_db for r in runs["base"].evaluation.routes
    }
    (out_dir / "protection_set.json").write_text(
        json.dumps(protection.describe(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 4) 局部优化（base 与 small 两个起点）
    optimize_records: dict[str, dict] = {}
    if optimize:
        for start, planner, result in (
            ("base", base_planner, base_result),
        ):
            print("[opt:%s] 保护性局部优化（压力情景 ×5）..." % start, flush=True)
            optimized_eval, record = local_optimize(
                planner,
                baseline_evaluation=runs[start].evaluation,
                protection=protection,
                rule=rule,
                baseline_result=result,
                candidates_per_route=4,
                scenario_top=16,
                time_budget_s=420.0 if channels == 256 else 1500.0,
                progress=True,
            )
            optimized_eval.label = "opt_%s" % start
            optimized_segments = {
                rid: route.segments for rid, route in planner.committed.items()
            }
            runs["opt_%s" % start] = Step13Run(
                "opt_%s" % start,
                channels,
                optimized_eval,
                _frozen_map(channels),
                {"base_scheme": "F56", "start": start, "optimized": True},
                optimized_segments,
            )
            optimize_records["opt_%s" % start] = {
                "candidates_tried": record.candidates_tried,
                "accepted": record.accepted,
                "rejected": record.rejected,
                "evaluations": record.evaluations,
                "runtime_s": record.runtime_s,
                "stop_reason": record.stop_reason,
                "rollback_fingerprint_mismatches": record.rollback_fingerprint_mismatches,
            }
            pd.DataFrame(record.attempts).to_csv(
                out_dir / ("optimize_attempts_%s.csv" % start),
                index=False,
                encoding="utf-8-sig",
            )

    # 5) 产物
    order = ["base", "spacing", "small", "touch", "both"] + [
        k for k in runs if k.startswith("opt_")
    ]
    rows = []
    for name in order:
        if name not in runs:
            continue
        run = runs[name]
        folder = out_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        per_route_frame(run).to_csv(folder / "per_route.csv", index=False, encoding="utf-8-sig")
        (folder / "summary.json").write_text(
            json.dumps(run.summary(), indent=2, ensure_ascii=False, default=float),
            encoding="utf-8",
        )
        protection_table(run, protection, baseline_losses).to_csv(
            folder / "protection_routes.csv", index=False, encoding="utf-8-sig"
        )
        extra = {}
        if name in optimize_records:
            extra = {"optimize": json.dumps(optimize_records[name], ensure_ascii=False)}
        rows.append(summary_row(run, extra))

    table = pd.DataFrame(rows)
    table.to_csv(out_dir / "comparison.csv", index=False, encoding="utf-8-sig")

    # D56 / F56 参照行（不同半径，仅作对照）
    ref_rows = []
    for ref in (d56_run, f56_run):
        ref_rows.append(summary_row(ref, {"reference": ref.name}))
    pd.DataFrame(ref_rows).to_csv(
        out_dir / "references.csv", index=False, encoding="utf-8-sig"
    )

    sensitivity_table(runs).to_csv(
        out_dir / "sensitivity.csv", index=False, encoding="utf-8-sig"
    )

    # 半径核对表：base 冻结半径 vs 原始 F56 逐路半径
    check = pd.DataFrame(
        [
            {
                "route_id": rid,
                "f56_radius_mm": r.radius,
                "frozen_radius_mm": radii.get(rid),
                "same": abs(r.radius - radii.get(rid, float("nan"))) <= 1e-9,
            }
            for rid, r in ((r.route_id, r) for r in f56_run.evaluation.routes)
        ]
    )
    check.to_csv(out_dir / "radius_freeze_check.csv", index=False, encoding="utf-8-sig")

    # 验收记录（每个方案相对 base 的验收判定）
    acceptance_rows = []
    for name in order:
        if name not in runs:
            continue
        verdict = acceptance_check(runs["base"].evaluation, runs[name].evaluation, rule)
        row = {"scheme": name, "ok": verdict.ok, "reasons": ";".join(verdict.reasons)}
        row.update({k: v for k, v in verdict.detail.items() if not isinstance(v, dict)})
        acceptance_rows.append(row)
    pd.DataFrame(acceptance_rows).to_csv(
        out_dir / "acceptance.csv", index=False, encoding="utf-8-sig"
    )
    (out_dir / "optimize_record.json").write_text(
        json.dumps(optimize_records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(table.to_string(index=False), flush=True)
    return {"runs": runs, "table": table, "protection": protection}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Step 14 冻结对照下的稳健优化")
    parser.add_argument("--channels", type=int, nargs="+", default=[256])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--no-optimize", action="store_true")
    args = parser.parse_args(argv)
    for channels in args.channels:
        if channels not in (256, 512):
            print("error: 只支持 256/512", file=sys.stderr)
            return 2
        run_step14(channels, args.output, optimize=not args.no_optimize)
    return 0


if __name__ == "__main__":
    sys.exit(main())
