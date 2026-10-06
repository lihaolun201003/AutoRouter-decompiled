"""Step 14 诊断：候选排序强度与保护余量的折衷探测（256）。

在同一个 base（F56 + 冻结半径）上，分别用不同的候选排序强度与保护余量跑
受保护局部优化，用来回答：

1. 把"小角交叉"计入候选排序（``rank_overrides``）能否找到可行改进；
2. 如果保护约束的容差从 0 放宽到 +0.01 dB（**诊断口径，非验收口径**），
   能换来多少压力情景（<20° 交叉损耗 ×5）最大损耗的下降。

输出：``outputs/opt2d_step14/<channels>/probe/``。

用法：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B scripts\\opt2d_step14_probe.py --channels 256
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.opt2d.evaluator import Evaluator  # noqa: E402
from src.opt2d.frozen import frozen_ports_frame  # noqa: E402
from src.opt2d.step14 import (  # noqa: E402
    AcceptanceRule,
    local_optimize,
    scenario_max,
    select_protection,
)

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from opt2d_step14 import run_planner_scheme  # noqa: E402

DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "opt2d_step14"

#: 变体：(名称, 候选排序覆盖, 保护余量 dB)。保护余量 > 0 的是**诊断口径**。
VARIANTS: list[tuple[str, dict, float]] = [
    ("rank_small05_strict", {"small_angle_penalty_db": 0.5}, 0.0),
    ("rank_small20_strict", {"small_angle_penalty_db": 2.0}, 0.0),
    ("strict_slack001", {"small_angle_penalty_db": 0.5}, 0.01),
    ("strict_slack005", {"small_angle_penalty_db": 0.5}, 0.05),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Step 14 诊断探测")
    parser.add_argument("--channels", type=int, nargs="+", default=[256])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--time-budget", type=float, default=300.0)
    parser.add_argument(
        "--variants",
        nargs="+",
        default=[name for name, _, _ in VARIANTS],
        help="要跑的变体名（默认全部）",
    )
    args = parser.parse_args(argv)
    selected = [v for v in VARIANTS if v[0] in set(args.variants)]

    for channels in args.channels:
        out_dir = Path(args.output) / str(channels) / "probe"
        out_dir.mkdir(parents=True, exist_ok=True)
        evaluator = Evaluator(channels)
        ports = frozen_ports_frame(channels)

        print("[%d] 建立 base（F56 + 冻结半径）..." % channels, flush=True)
        f56_run, f56_planner, f56_result = run_planner_scheme(
            "F56", "F56", channels, evaluator, ports
        )
        radii = {r.route_id: r.radius for r in f56_run.evaluation.routes}
        base_run, base_planner, base_result = run_planner_scheme(
            "base", "F56", channels, evaluator, ports,
            overrides={"radius_overrides": radii},
        )
        d56_run, _, _ = run_planner_scheme("D56", "D56", channels, evaluator, ports)
        protection = select_protection(base_run.evaluation, d56_run.evaluation)
        base_eval = base_run.evaluation
        base_scenario = scenario_max(base_eval)
        base_snapshot = base_planner.snapshot()
        print(
            "base: mean=%.4f max=%.4f scenario5_max=%.4f 保护集合=%s"
            % (
                base_eval.summary()["mean_loss_db"],
                base_eval.summary()["max_loss_db"],
                base_scenario,
                list(protection.ids()),
            ),
            flush=True,
        )

        rows = []
        for name, rank, slack in selected:
            print("[%d] 变体 %s（排序=%s, 保护余量=%g）..." % (channels, name, rank, slack), flush=True)
            base_planner.restore(base_snapshot)
            rule = AcceptanceRule(
                mean_slack_db=0.05,
                protected_ids=protection.ids(),
                protected_slack_db=slack,
            )
            optimized, record = local_optimize(
                base_planner,
                baseline_evaluation=base_eval,
                protection=protection,
                rule=rule,
                baseline_result=base_result,
                candidates_per_route=4,
                scenario_top=16,
                time_budget_s=args.time_budget,
                rank_overrides=rank,
                progress=True,
            )
            summary = optimized.summary()
            rows.append(
                {
                    "variant": name,
                    "rank_small_penalty_db": rank.get("small_angle_penalty_db"),
                    "protected_slack_db": slack,
                    "accepted": record.accepted,
                    "candidates_tried": record.candidates_tried,
                    "evaluations": record.evaluations,
                    "runtime_s": record.runtime_s,
                    "rollback_fingerprint_mismatches": record.rollback_fingerprint_mismatches,
                    "mean_loss_db": summary["mean_loss_db"],
                    "max_loss_db": summary["max_loss_db"],
                    "scenario5_max_loss_db": scenario_max(optimized),
                    "scenario_gain_db": base_scenario - scenario_max(optimized),
                    "crossings_under_5_deg": sum(1 for e in optimized.events if e.angle_deg < 5.0),
                    "crossings_under_20_deg": sum(1 for e in optimized.events if e.angle_deg < 20.0),
                    "spacing_violation_count": summary["spacing_violation_count"],
                    "physical_route_touch_count": summary["physical_route_touch_count"],
                    "rejected": json.dumps(record.rejected, ensure_ascii=False),
                }
            )
            pd.DataFrame(record.attempts).to_csv(
                out_dir / ("attempts_%s.csv" % name), index=False, encoding="utf-8-sig"
            )
            print(
                "  -> accepted=%d scenario_max=%.4f (gain %+.4f) mean%+.4f"
                % (
                    record.accepted,
                    scenario_max(optimized),
                    base_scenario - scenario_max(optimized),
                    summary["mean_loss_db"] - base_eval.summary()["mean_loss_db"],
                ),
                flush=True,
            )
        frame = pd.DataFrame(rows)
        frame.to_csv(out_dir / "probe_summary.csv", index=False, encoding="utf-8-sig")
        print(frame.to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
