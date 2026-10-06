"""受约束自由弯角实验：小角交叉限制 vs 间距惩罚的折衷（补修后的提案验证）。

在修复后的同一条自由弯角管线（F56 = 跨侧自由弯角 S 形 + R5/R6 自适应）上比较
四种候选接受口径：

===============  ==========================================================
配置             说明
===============  ==========================================================
``base``         现状（间距与小角都不惩罚）
``spacing``      间距惩罚 0.05 dB/路线对
``small``        <20° 交叉每个额外 0.05 dB（小角交叉限制）
``both``         两者同时启用
===============  ==========================================================

对每个配置报告：平均/最大/P95 损耗、<5°/<10°/<20° 交叉数、间距违规、接触与重合、
以及"保护对象"的逐路损耗 —— D56 的最差路线（256 #44）与 F56 自身的最差路线，
外加**被穿越最多的 U 型路线**（U 型中交叉事件数前 10 名的合计损耗）。

用法：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B scripts\\opt2d_step13_constrained.py --channels 256
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.opt2d.evaluator import Evaluator  # noqa: E402
from src.opt2d.frozen import frozen_ports_frame  # noqa: E402
from src.opt2d.step13 import ANGLE_BINS, angle_histogram  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from opt2d_step13_fix import run_variant  # noqa: E402

DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "opt2d_step13_constrained"

CONFIGS: dict[str, dict] = {
    "base": {},
    "spacing": {"spacing_penalty_db": 0.05},
    "small": {"small_angle_deg": 20.0, "small_angle_penalty_db": 0.05},
    "both": {
        "spacing_penalty_db": 0.05,
        "small_angle_deg": 20.0,
        "small_angle_penalty_db": 0.05,
    },
}


def _run_metrics(run, protected_ids) -> dict:
    evaluation = run.evaluation
    summary = evaluation.summary()
    histogram = angle_histogram(evaluation)
    bins = list(ANGLE_BINS)
    under = {}
    for threshold in (5.0, 10.0, 20.0, 30.0):
        under["crossings_under_%g_deg" % threshold] = sum(
            1 for event in evaluation.events if event.angle_deg < threshold
        )
    index = evaluation.route_index
    protected = {}
    for rid in protected_ids:
        record = index.get(rid)
        protected["route_%d_loss_db" % rid] = None if record is None else record.total_loss_db
    u_routes = sorted(
        (r for r in evaluation.routes if r.geometry_kind == "u"),
        key=lambda r: (-r.crossing_count, r.route_id),
    )[:10]
    protected["top10_crossed_u_sum_loss_db"] = sum(r.total_loss_db for r in u_routes)
    protected["top10_crossed_u_mean_loss_db"] = (
        statistics.fmean(r.total_loss_db for r in u_routes) if u_routes else None
    )
    return {
        "mean_loss_db": summary["mean_loss_db"],
        "p95_loss_db": summary["p95_loss_db"],
        "max_loss_db": summary["max_loss_db"],
        "worst_route_id": summary["worst_route_id"],
        "spacing_violation_count": summary["spacing_violation_count"],
        "contact_touch_count": summary["contact_touch_count"],
        "contact_overlap_count": summary["contact_overlap_count"],
        "geometry_issue_count": summary["geometry_issue_count"],
        "complete_connection": summary["complete_connection"],
        "mean_crossing_loss_db": summary["mean_crossing_loss_db"],
        "mean_bend_loss_db": summary["mean_bend_loss_db"],
        "angle_histogram": json.dumps(histogram),
        "angle_bins": json.dumps(bins),
        **under,
        **protected,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="受约束自由弯角实验")
    parser.add_argument("--channels", type=int, nargs="+", default=[256])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    for channels in args.channels:
        out_dir = Path(args.output) / str(channels)
        out_dir.mkdir(parents=True, exist_ok=True)
        evaluator = Evaluator(channels)
        ports = frozen_ports_frame(channels)
        protected = [44] if channels == 256 else [287]
        rows = []
        runs = {}
        for name, overrides in CONFIGS.items():
            print("[%d] %s ..." % (channels, name), flush=True)
            run = run_variant(
                "F56_%s" % name, "F56", channels, evaluator, ports, overrides=overrides
            )
            runs[name] = run
            rows.append({"config": name, **_run_metrics(run, protected)})
            row = rows[-1]
            print(
                "  mean=%.4f max=%.4f p95=%.4f <20deg=%d spacing=%d touch=%d overlap=%d"
                % (
                    row["mean_loss_db"], row["max_loss_db"], row["p95_loss_db"],
                    row["crossings_under_20_deg"], row["spacing_violation_count"],
                    row["contact_touch_count"], row["contact_overlap_count"],
                ),
                flush=True,
            )
        frame = pd.DataFrame(rows)
        frame.to_csv(out_dir / "constrained_comparison.csv", index=False, encoding="utf-8-sig")
        for name, run in runs.items():
            folder = out_dir / name
            folder.mkdir(parents=True, exist_ok=True)
            from src.opt2d.step13 import per_route_frame

            per_route_frame(run).to_csv(folder / "per_route.csv", index=False, encoding="utf-8-sig")
        print(frame.to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
