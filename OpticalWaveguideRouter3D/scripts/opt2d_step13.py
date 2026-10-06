"""Step 13 入口：修复后的固定端点对照、D0 半径回退与自由弯角 S 形。

用法（在项目根目录，使用带 scipy 的解释器）：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B scripts\\opt2d_step13.py --channels 256 512

只重画图（读取已保存的逐路 CSV）：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B scripts\\opt2d_step13.py --channels 256 --figures-only
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
from src.opt2d.step13 import (  # noqa: E402
    DEFAULT_OUTPUT,
    acceptance_check,
    render_step13,
    run_step13,
    worst_route_tracking,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="opt2d Step 13 固定端点与自由弯角实验")
    parser.add_argument("--channels", type=int, nargs="+", default=[256, 512])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--schemes",
        nargs="+",
        default=["R5U", "D0", "D56", "F5", "F56"],
        help="要运行的固定端点方案",
    )
    parser.add_argument("--figures-only", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    for channels in args.channels:
        if channels not in (256, 512):
            print("error: 只支持 256/512", file=sys.stderr)
            return 2
        print("=== %d 通道：Step 13 ===" % channels, flush=True)
        if args.figures_only:
            runs = _load_runs(output / str(channels))
        else:
            suite = run_step13(
                channels,
                output,
                evaluator=Evaluator(channels),
                schemes=tuple(args.schemes),
            )
            runs = suite["runs"]
            folder = output / str(channels)
            worst_route_tracking(runs).to_csv(
                folder / "worst_route_tracking.csv", index=False, encoding="utf-8-sig"
            )
            (folder / "acceptance.json").write_text(
                json.dumps(acceptance_check(runs), indent=2, ensure_ascii=False, default=float),
                encoding="utf-8",
            )
            print(suite["table"].to_string(index=False), flush=True)
        figures = render_step13(runs, output / str(channels) / "figures", channels)
        print("图表：%s" % ", ".join(f.name for f in figures), flush=True)
    return 0


def _rebuild_segments(row):
    """从逐路 CSV 重建解析几何（供最差路线局部图使用）。"""
    from src.opt2d.freeform import FreeformParams, build_freeform_geometry
    from src.opt2d.smoothing import RouteSpec, build_route_geometry

    if str(row.geometry) == "freeform":
        return build_freeform_geometry(
            FreeformParams(
                route_id=int(row.route_id),
                sx=float(row.sx_mm),
                sy=float(row.sy_mm),
                lx=float(row.lx_mm),
                ly=float(row.ly_mm),
                radius=float(row.radius_mm),
                alpha_deg=float(row.alpha_deg),
                t0_fraction=float(row.t0_fraction),
            )
        )
    spec = RouteSpec(
        route_id=int(row.route_id),
        sx=float(row.sx_mm),
        sy=float(row.sy_mm),
        lx=float(row.lx_mm),
        ly=float(row.ly_mm),
        track_y=float(row.track_y_mm),
        radius=float(row.radius_mm),
    )
    return build_route_geometry(spec)


def _load_runs(folder: Path):
    """从产物重建最小绘图对象（含解析几何）。"""
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
                    bend_angles_deg=[float(row.bend_total_deg)],
                    crossing_events=by_route.get(int(row.route_id), []),
                    geometry_kind=str(row.geometry),
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
        def __init__(self, name, evaluation, segments):
            self.name = name
            self.label = name
            self.channels = 0
            self.evaluation = evaluation
            self.segments = segments

        def summary(self):
            return self.evaluation.summary()

        def endpoint_changes(self):
            return 0

    runs = {}
    for folder_name in sorted(p.name for p in folder.iterdir() if p.is_dir()):
        path = folder / folder_name / "per_route.csv"
        if not path.is_file():
            continue
        frame = pd.read_csv(path)
        events_path = folder / folder_name / "crossing_events.csv"
        events = []
        if events_path.is_file():
            events = [_Event(row) for row in pd.read_csv(events_path).itertuples()]
        segments = {}
        for row in frame.itertuples():
            try:
                segments[int(row.route_id)] = _rebuild_segments(row)
            except Exception:
                continue
        runs[folder_name] = _Run(folder_name, _Evaluation(frame, events), segments)
    return runs


if __name__ == "__main__":
    sys.exit(main())
