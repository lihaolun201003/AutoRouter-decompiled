"""实验图表：损耗分布、损耗分解、最差路线局部图与指标对比。"""

from __future__ import annotations

from math import cos, pi, sin
from pathlib import Path

import matplotlib

if matplotlib.get_backend().lower() not in ("agg", "module://matplotlib_inline.backend_inline"):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Windows 上优先使用自带中文字体，避免 CJK 字形缺失。
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans",
]
matplotlib.rcParams["axes.unicode_minus"] = False

from ..models import ArcSegment2D, LineSegment2D  # noqa: E402

__all__ = [
    "segment_polyline",
    "plot_loss_distribution",
    "plot_loss_breakdown",
    "plot_metric_bars",
    "plot_worst_route",
    "render_all",
]

COLORS = {"A": "#444444", "B": "#1f77b4", "C": "#2ca02c", "D": "#d62728"}


def segment_polyline(segment, samples: int = 96):
    """把解析线段采样成折线（只用于绘图）。"""
    if isinstance(segment, LineSegment2D):
        return [segment.start.x, segment.end.x], [segment.start.y, segment.end.y]
    sweep = segment.sweep_rad
    start = segment.start
    angle0 = None
    from math import atan2

    angle0 = atan2(start.y - segment.center.y, start.x - segment.center.x)
    radius = ((start.x - segment.center.x) ** 2 + (start.y - segment.center.y) ** 2) ** 0.5
    xs, ys = [], []
    count = max(8, int(abs(sweep) / (2 * pi) * samples) + 2)
    for k in range(count + 1):
        angle = angle0 + sweep * k / count
        xs.append(segment.center.x + radius * cos(angle))
        ys.append(segment.center.y + radius * sin(angle))
    return xs, ys


def plot_loss_distribution(runs: dict, path: Path, title_suffix: str = "") -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    for key in sorted(runs):
        losses = sorted(record.total_loss_db for record in runs[key].evaluation.routes)
        axes[0].hist(losses, bins=48, histtype="step", linewidth=1.6,
                     label="%s (n=%d)" % (key, len(losses)), color=COLORS.get(key))
        cumulative = [(i + 1) / len(losses) for i in range(len(losses))]
        axes[1].plot(losses, cumulative, linewidth=1.8, label=key, color=COLORS.get(key))
    axes[0].set_xlabel("逐路总损耗 (dB)")
    axes[0].set_ylabel("波导数")
    axes[0].set_title("损耗分布%s" % title_suffix)
    axes[0].legend()
    axes[0].grid(alpha=0.3)
    axes[1].set_xlabel("逐路总损耗 (dB)")
    axes[1].set_ylabel("累计比例")
    axes[1].set_title("损耗累计分布%s" % title_suffix)
    axes[1].legend()
    axes[1].grid(alpha=0.3)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def plot_loss_breakdown(runs: dict, path: Path, title_suffix: str = "") -> Path:
    keys = sorted(runs)
    straight = [runs[k].summary()["mean_straight_loss_db"] for k in keys]
    bend = [runs[k].summary()["mean_bend_loss_db"] for k in keys]
    crossing = [runs[k].summary()["mean_crossing_loss_db"] for k in keys]
    figure, axis = plt.subplots(figsize=(8, 5))
    positions = range(len(keys))
    axis.bar(positions, straight, 0.55, label="直线传播", color="#4c72b0")
    axis.bar(positions, bend, 0.55, bottom=straight, label="弯曲", color="#dd8452")
    axis.bar(positions, crossing, 0.55,
             bottom=[a + b for a, b in zip(straight, bend)], label="交叉", color="#55a868")
    for index, key in enumerate(keys):
        total = straight[index] + bend[index] + crossing[index]
        axis.text(index, total + 0.02, "%.3f" % total, ha="center", fontsize=9)
    axis.set_xticks(list(positions))
    axis.set_xticklabels(keys)
    axis.set_ylabel("平均损耗 (dB)")
    axis.set_title("平均损耗分解（逐路交叉事件按每根波导各计一次）%s" % title_suffix)
    axis.legend()
    axis.grid(alpha=0.3, axis="y")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def plot_metric_bars(runs: dict, path: Path, title_suffix: str = "") -> Path:
    keys = sorted(runs)
    metrics = [
        ("mean_loss_db", "平均损耗 (dB)"),
        ("p95_loss_db", "P95 损耗 (dB)"),
        ("max_loss_db", "最大损耗 (dB)"),
    ]
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    for axis, (field, label) in zip(axes, metrics):
        values = [runs[k].summary()[field] for k in keys]
        axis.bar(range(len(keys)), values, 0.55,
                 color=[COLORS.get(k, "#666") for k in keys])
        for index, value in enumerate(values):
            axis.text(index, value, "%.3f" % value, ha="center", va="bottom", fontsize=9)
        axis.set_xticks(range(len(keys)))
        axis.set_xticklabels(keys)
        axis.set_ylabel(label)
        axis.grid(alpha=0.3, axis="y")
        margin = (max(values) - min(values)) * 0.6 + 0.01
        axis.set_ylim(min(values) - margin, max(values) + margin)
    figure.suptitle("各方案损耗指标对比%s" % title_suffix)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def plot_worst_route(run, path: Path, *, radius_mm: float = 2.0) -> Path:
    """最差路线局部图：红色为最差路线，灰色为与它相交的路线，红点为交叉事件。"""
    evaluation = run.evaluation
    worst = max(evaluation.routes, key=lambda r: (r.total_loss_db, -r.route_id))
    neighbors = sorted({e.route_b if e.route_a == worst.route_id else e.route_a
                        for e in worst.crossing_events})
    figure, axis = plt.subplots(figsize=(9, 9))
    segment_map = run.segments
    for rid in neighbors:
        for segment in segment_map.get(rid, []):
            xs, ys = segment_polyline(segment)
            axis.plot(xs, ys, color="#999999", linewidth=0.5, alpha=0.7)
    for segment in segment_map.get(worst.route_id, []):
        xs, ys = segment_polyline(segment)
        axis.plot(xs, ys, color="#d62728", linewidth=1.4)
    point_x = [worst.sx, worst.lx]
    point_y = [worst.sy, worst.ly]
    axis.plot(point_x, point_y, "ks", markersize=5)
    if worst.crossing_events:
        axis.plot([e.x for e in worst.crossing_events],
                  [e.y for e in worst.crossing_events], "r.", markersize=6)
    axis.set_xlabel("x (mm)")
    axis.set_ylabel("y (mm)")
    radius = radius_mm
    center_x = (worst.sx + worst.lx) / 2
    axis.set_xlim(center_x - 45, center_x + 45)
    axis.set_ylim(worst.track_y - 45, worst.track_y + 45)
    axis.set_title(
        "%s 最差路线 #%d：总损耗 %.3f dB（直线 %.3f + 弯曲 %.3f + 交叉 %.3f），交叉 %d 次"
        % (
            run.label,
            worst.route_id,
            worst.total_loss_db,
            worst.straight_loss_db,
            worst.bend_loss_db,
            worst.crossing_loss_db,
            worst.crossing_count,
        )
    )
    axis.grid(alpha=0.3)
    axis.set_aspect("equal", adjustable="box")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def render_all(runs: dict, out_dir: Path, channels: int) -> list[Path]:
    """生成一个规模的全部图，返回文件列表。"""
    out_dir = Path(out_dir)
    figures = []
    figures.append(plot_loss_distribution(runs, out_dir / "loss_distribution.png",
                                          "（%d 通道）" % channels))
    figures.append(plot_loss_breakdown(runs, out_dir / "loss_breakdown.png",
                                       "（%d 通道）" % channels))
    figures.append(plot_metric_bars(runs, out_dir / "metric_comparison.png",
                                    "（%d 通道）" % channels))
    for key, run in sorted(runs.items()):
        figures.append(
            plot_worst_route(run, out_dir / ("worst_route_%s.png" % key))
        )
    return figures
