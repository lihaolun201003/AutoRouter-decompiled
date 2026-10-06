"""二维布线优化实验入口：A/B/C/D 对照、消融、逐路 CSV/汇总 JSON 与图表。

用法（在项目根目录，使用带 scipy 的解释器）：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B scripts\\opt2d_run_all.py --channels 256 512

只重画图表（读取已保存的逐路 CSV）：

.. code-block:: text

    python -B scripts\\opt2d_run_all.py --channels 512 --figures-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.opt2d.evaluator import Evaluator  # noqa: E402
from src.opt2d.experiments import DEFAULT_OUTPUT, run_suite  # noqa: E402
from src.opt2d.report import render_all  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="opt2d 二维布线优化实验")
    parser.add_argument("--channels", type=int, nargs="+", default=[256, 512])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--skip-sensitivity", action="store_true",
                        help="跳过消融实验（更快）")
    parser.add_argument("--figures-only", action="store_true",
                        help="不重新布线，只用已保存的结果重画图")
    parser.add_argument("--refine-rounds", type=int, default=3,
                        help="拆线重布的最大轮数（默认 3）")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    for channels in args.channels:
        if channels not in (256, 512):
            print("error: 只支持 256/512", file=sys.stderr)
            return 2
        folder = output / str(channels)
        folder.mkdir(parents=True, exist_ok=True)
        print("=== %d 通道：开始 ===" % channels, flush=True)
        if args.figures_only:
            # 只重画图：用已保存的 per_route.csv 重建轻量对象。
            runs = _load_runs(folder, channels)
        else:
            suite = run_suite(
                channels,
                folder,
                evaluator=Evaluator(channels),
                include_sensitivity=not args.skip_sensitivity,
                refine_rounds=args.refine_rounds,
            )
            runs = suite["runs"]
            suite["table"].to_csv(folder / "comparison.csv", index=False, encoding="utf-8-sig")
        figures = render_all(runs, folder / "figures", channels)
        print("图表：%s" % ", ".join(str(f.name) for f in figures), flush=True)
        print("=== %d 通道：完成 ===" % channels, flush=True)
    return 0


def _load_runs(folder: Path, channels: int) -> dict:
    """从已保存的 CSV/JSON 重建最小的绘图对象（含交叉事件，用于最差路线图）。"""
    from types import SimpleNamespace

    import pandas as pd

    class _Event:
        __slots__ = ("route_a", "route_b", "x", "y", "angle_deg")

        def __init__(self, row):
            self.route_a = int(row.route_a)
            self.route_b = int(row.route_b)
            self.x = float(row.x_mm)
            self.y = float(row.y_mm)
            self.angle_deg = float(row.angle_deg)

    class _Evaluation:
        def __init__(self, frame, events):
            by_route: dict[int, list] = {}
            for event in events:
                by_route.setdefault(event.route_a, []).append(event)
                by_route.setdefault(event.route_b, []).append(event)
            self.events = events
            self.routes = [
                SimpleNamespace(
                    route_id=int(row.route_id),
                    total_loss_db=float(row.total_loss_db),
                    straight_loss_db=float(row.straight_loss_db),
                    bend_loss_db=float(row.bend_loss_db),
                    crossing_loss_db=float(row.crossing_loss_db),
                    crossing_count=int(row.crossing_count),
                    sx=float(row.sx_mm),
                    sy=float(row.sy_mm),
                    lx=float(row.lx_mm),
                    ly=float(row.ly_mm),
                    track_y=float(row.track_y_mm),
                    crossing_events=by_route.get(int(row.route_id), []),
                )
                for row in frame.itertuples()
            ]

        def summary(self):
            import statistics

            values = sorted(r.total_loss_db for r in self.routes)
            return {
                "mean_loss_db": statistics.fmean(values),
                "p95_loss_db": values[max(1, int(0.95 * len(values))) - 1],
                "max_loss_db": max(values),
                "mean_straight_loss_db": statistics.fmean(r.straight_loss_db for r in self.routes),
                "mean_bend_loss_db": statistics.fmean(r.bend_loss_db for r in self.routes),
                "mean_crossing_loss_db": statistics.fmean(r.crossing_loss_db for r in self.routes),
            }

    class _Run:
        def __init__(self, label, evaluation, segments):
            self.label = label
            self.channels = channels
            self.evaluation = evaluation
            self.segments = segments

        def summary(self):
            return self.evaluation.summary()

    runs: dict[str, _Run] = {}
    for key in ("A", "B", "C", "D"):
        path = folder / key / "per_route.csv"
        if not path.is_file():
            continue
        frame = pd.read_csv(path)
        events_path = folder / key / "crossing_events.csv"
        events = []
        if events_path.is_file():
            events = [_Event(row) for row in pd.read_csv(events_path).itertuples()]
        label = key
        summary_path = folder / key / "summary.json"
        if summary_path.is_file():
            label = json.loads(summary_path.read_text(encoding="utf-8")).get("label", key)
        runs[key] = _Run(label, _Evaluation(frame, events), {})
    return runs


if __name__ == "__main__":
    sys.exit(main())
