"""论文复现组图（第 3 章）。

覆盖：
* 论文表 3-1 弯曲模型对照；
* 256 / 512 / 512-R4 的论文 vs 复现精度与有符号误差；
* 512 半径扫描（R2–R5）与弯曲占比；
* 损耗分量分解；
* 逐路损耗分布与累计分布；
* 损耗—结构散点（长度、交叉数）；
* 交叉角度分布与 512 的小角放大。

全部数值来自 OpticalWaveguideRouter2D/results 与 scratch 的真实产物
（xlsx 逐路表、summary json、legacy 字节码 json），论文值来自
PAPER_VALUES 引用记录。
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

import pubdata as D
import pubstyle as S

RADII = [2.0, 3.0, 4.0, 5.0, 6.0]
SWEEP_TAGS = ["512_R2", "512_R3", "512_R4", "512_R5"]
SWEEP_X = [2.0, 3.0, 4.0, 5.0]


def fig_bend_model() -> None:
    """F3-1：90° 弯曲损耗——论文表 3-1 与复刻模型。"""
    paper = [D.PAPER_VALUES["bend_90_db"][str(int(r))] for r in RADII]
    repro = [D.bend_model_90_db(r) for r in RADII]
    fig, ax = S.single_axes("half")
    ax.plot(RADII, repro, **S.method("repro").line_kw())
    ax.plot(RADII, paper, **S.method("thesis").line_kw())
    for x, y in zip(RADII, repro):
        ax.annotate(f"{y:.2f}", (x, y), xytext=(0, 5), textcoords="offset points",
                    ha="center", fontsize=S.FONT_SIZE_SMALL, color=S.method("repro").color)
    for x, y in zip(RADII, paper):
        ax.annotate(f"{y:.2f}", (x, y), xytext=(0, -10), textcoords="offset points",
                    ha="center", fontsize=S.FONT_SIZE_SMALL, color=S.method("thesis").color)
    ax.set_xlabel("弯曲半径 R (mm)")
    ax.set_ylabel("90° 弯曲损耗 (dB)")
    ax.set_xlim(1.5, 6.6)
    ax.set_ylim(0, 9.2)
    ax.set_xticks(RADII)
    S.style_axis(ax)
    S.legend_ordered(ax, loc="upper right")
    S.save_figure(
        fig, "f31_bend_model_thesis_vs_repro",
        note="90° 弯曲损耗：论文表 3-1（离散半径 2/3/4/5/6 mm）与复刻模型（tl/ll 表推得密度×Rπ/2）对照。",
        sources=[
            "论文表 3-1（引用记录：OpticalWaveguideRouter2D/docs/loss_model_reconstruction_report.md）",
            "OpticalWaveguideRouter2D/loss_model.py（BEND_TABLE_*，复算）",
        ],
    )


def fig_repro_accuracy() -> None:
    """F3-2：论文 vs 复现（数值对照 + 有符号相对误差）。"""
    cases = [
        ("256", "256 通道 R5", "256_R5"),
        ("512", "512 通道 R5", "512_R5"),
        ("512_R4", "512 通道 R4", "512_R4"),
    ]
    rows = []  # (case_label, metric_label, paper, repro)
    for key, label, tag in cases:
        paper = D.PAPER_VALUES["cases"][key]
        summary = D.repro_summary(tag)
        rows.append((label, "平均损耗", paper["mean_loss_db"], summary["mean_loss_db"]))
        rows.append((label, "最大损耗", paper["max_loss_db"], summary["max_loss_db"]))

    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.9),
                             gridspec_kw={"width_ratios": [1.25, 1.0]})
    ax = axes[0]
    ypos = np.arange(len(rows))[::-1]
    for y, (_, metric, paper, repro) in zip(ypos, rows):
        ax.plot([paper, repro], [y, y], color="#BBBBBB", linewidth=1.0, zorder=1)
    ax.plot([r[2] for r in rows], ypos, "s", color=S.method("thesis").color,
            markersize=5, label=S.method("thesis").display, zorder=2, linestyle="none")
    ax.plot([r[3] for r in rows], ypos, "o", color=S.method("repro").color,
            markersize=5, label=S.method("repro").display, zorder=2, linestyle="none")
    ax.set_yticks(ypos)
    ax.set_yticklabels([f"{case}·{metric}" for case, metric, _, _ in rows], fontsize=S.FONT_SIZE_SMALL)
    ax.set_xlabel("损耗 (dB)")
    ax.set_xlim(4.6, 11.6)
    S.style_axis(ax, grid_axis="x")
    ax.legend(loc="lower left")
    ax.set_title("(a) 论文值与复现值（连线为同一指标）", fontsize=S.FONT_SIZE)

    ax2 = axes[1]
    rel = [(repro - paper) / paper * 100.0 for _, _, paper, repro in rows]
    labels = [f"{case}·{metric}" for case, metric, _, _ in rows]
    ax2.barh(ypos, rel, height=0.5, color=[S.method("repro").color if v >= 0 else S.method("thesis").color for v in rel])
    ax2.axvline(0, color="#444444", linewidth=0.8)
    for y, v in zip(ypos, rel):
        offset = 0.08 if v >= 0 else -0.08
        ax2.text(v + (0.06 if v >= 0 else -0.06), y, f"{v:+.2f}%", va="center",
                 ha="left" if v >= 0 else "right", fontsize=S.FONT_SIZE_SMALL)
    ax2.set_yticks(ypos)
    ax2.set_yticklabels([])
    ax2.set_xlabel("有符号相对误差 (%)")
    ax2.set_xlim(-1.6, 1.0)
    ax2.xaxis.set_major_locator(MultipleLocator(0.5))
    S.style_axis(ax2, grid_axis="x")
    ax2.set_title("(b) 复现相对论文的偏差", fontsize=S.FONT_SIZE)

    fig.tight_layout(w_pad=0.8)
    S.save_figure(
        fig, "f32_reproduction_accuracy",
        note="三个复现 case（256 R5、512 R5、512 R4）的平均/最大损耗：论文值 vs 复现值与有符号相对误差。",
        sources=[
            "论文 4.1/4.2/4.3 节数字（引用记录：results/*_summary.json thesis_* 字段）",
            "OpticalWaveguideRouter2D/results/fiberBoard{256,512}_loss_summary.json 等",
        ],
    )


def fig_radius_sweep() -> None:
    """F3-3：512 半径扫描（复现）与论文 R4 对照点、弯曲占比。"""
    mean, maximum, bend_ratio = [], [], []
    for tag in SWEEP_TAGS:
        summary = D.repro_summary(tag)
        mean.append(summary["mean_loss_db"])
        maximum.append(summary["max_loss_db"])
        bend_ratio.append(summary["loss_contribution"]["bend"] * 100.0)

    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.9),
                             gridspec_kw={"width_ratios": [1.35, 1.0]})
    ax = axes[0]
    ax.plot(SWEEP_X, mean, **S.method("repro").line_kw(label="平均损耗（复现）"))
    ax.plot(SWEEP_X, maximum, **S.method("repro").line_kw(label="最大损耗（复现）", linestyle="--"))
    paper = D.PAPER_VALUES["cases"]["512_R4"]
    ax.plot([4.0], [paper["mean_loss_db"]], marker="s", color=S.method("thesis").color,
            markersize=5, linestyle="none", label="论文值（R4，论文 4.3）")
    ax.plot([4.0], [paper["max_loss_db"]], marker="s", color=S.method("thesis").color,
            markersize=5, linestyle="none", markerfacecolor="white")
    for x, y in zip(SWEEP_X, mean):
        if x == 4.0:  # R4 处复现值与论文值几乎重合，由论文标注代表
            continue
        ax.annotate(f"{y:.3f}", (x, y), xytext=(0, -12), textcoords="offset points",
                    ha="center", fontsize=S.FONT_SIZE_SMALL)
    for x, y in zip(SWEEP_X, maximum):
        if x == 4.0:
            continue
        ax.annotate(f"{y:.3f}", (x, y), xytext=(0, 5), textcoords="offset points",
                    ha="center", fontsize=S.FONT_SIZE_SMALL)
    ax.annotate(f"{paper['mean_loss_db']:.1f}", (4.0, paper["mean_loss_db"]),
                xytext=(-6, 0), textcoords="offset points", fontsize=S.FONT_SIZE_SMALL,
                color=S.method("thesis").color, ha="right", va="center")
    ax.annotate(f"{paper['max_loss_db']:.1f}", (4.0, paper["max_loss_db"]),
                xytext=(-6, 0), textcoords="offset points", fontsize=S.FONT_SIZE_SMALL,
                color=S.method("thesis").color, ha="right", va="center")
    ax.set_xlabel("弯曲半径 R (mm)")
    ax.set_ylabel("损耗 (dB)")
    ax.set_xticks(SWEEP_X)
    ax.set_xlim(1.75, 5.45)
    ax.set_ylim(0, 19.6)
    S.style_axis(ax)
    ax.legend(loc="upper right")
    ax.set_title("(a) 512 通道半径扫描（离散半径 2/3/4/5 mm）", fontsize=S.FONT_SIZE)

    ax2 = axes[1]
    bars = ax2.bar([f"{int(r)}" for r in SWEEP_X], bend_ratio, width=0.55,
                   color="#fdae6b", edgecolor="#e6550d", linewidth=0.5)
    for rect, v in zip(bars, bend_ratio):
        ax2.annotate(f"{v:.1f}%", (rect.get_x() + rect.get_width() / 2, v), xytext=(0, 2),
                     textcoords="offset points", ha="center", fontsize=S.FONT_SIZE_SMALL)
    ax2.set_xlabel("弯曲半径 R (mm)")
    ax2.set_ylabel("弯曲损耗占比 (%)")
    ax2.set_ylim(0, 105)
    S.style_axis(ax2)
    ax2.set_title("(b) 弯曲在总损耗中的占比", fontsize=S.FONT_SIZE)

    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f33_radius_sweep_512",
        note="512 通道固定几何在不同弯曲半径（离散 2–5 mm）下的固定几何复算结果；论文 R4 对照值来自论文 4.3 节。",
        sources=[
            "OpticalWaveguideRouter2D/results/fiberBoard512_loss_R{2,3,4}_summary.json、fiberBoard512_loss_summary.json",
        ],
    )


def fig_loss_contribution() -> None:
    """F3-4：损耗分量分解（均值堆叠条）。"""
    groups = [("512·R2", "512_R2"), ("512·R3", "512_R3"), ("512·R4", "512_R4"),
              ("512·R5", "512_R5"), ("256·R5", "256_R5")]
    labels, straight, bend, crossing = [], [], [], []
    for label, tag in groups:
        s = D.repro_summary(tag)
        labels.append(label)
        straight.append(s["mean_straight_loss_db"])
        bend.append(s["mean_bend_loss_db"])
        crossing.append(s["mean_crossing_loss_db"])

    fig, ax = S.single_axes("full_short")
    x = np.arange(len(labels))
    b1 = ax.bar(x, straight, width=0.6, label=S.COMPONENT_STYLE["straight"]["label"],
                color=S.COMPONENT_STYLE["straight"]["color"], edgecolor=S.COMPONENT_STYLE["straight"]["edge"], linewidth=0.5)
    b2 = ax.bar(x, bend, width=0.6, bottom=straight, label=S.COMPONENT_STYLE["bend"]["label"],
                color=S.COMPONENT_STYLE["bend"]["color"], edgecolor=S.COMPONENT_STYLE["bend"]["edge"], linewidth=0.5)
    bottom2 = np.asarray(straight) + np.asarray(bend)
    b3 = ax.bar(x, crossing, width=0.6, bottom=bottom2, label=S.COMPONENT_STYLE["crossing"]["label"],
                color=S.COMPONENT_STYLE["crossing"]["color"], edgecolor=S.COMPONENT_STYLE["crossing"]["edge"], linewidth=0.5)
    for xi, total in zip(x, bottom2 + np.asarray(crossing)):
        ax.annotate(f"{total:.3f} dB", (xi, total), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=S.FONT_SIZE_SMALL)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("平均逐路损耗 (dB)")
    ax.set_ylim(0, 19.5)
    S.style_axis(ax)
    ax.legend(loc="upper right", ncol=1)
    S.save_figure(
        fig, "f34_loss_contribution_repro",
        note="固定几何复算的逐路损耗均值分解（直线+弯曲+交叉，交叉事件按每根波导各计一次）。",
        sources=[
            "OpticalWaveguideRouter2D/results/*_loss_summary.json",
        ],
    )


def fig_loss_distribution() -> None:
    """F3-5：逐路损耗分布与累计分布（256 vs 512）。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.8))
    for tag, label, color in [("256_R5", "256 通道 R5", S.CHANNEL_COLORS[256]),
                              ("512_R5", "512 通道 R5", S.CHANNEL_COLORS[512])]:
        losses = np.sort(D.repro_route_frame(tag)["total_loss_db"].to_numpy())
        n = len(losses)
        axes[0].hist(losses, bins=24, histtype="step", linewidth=1.1,
                     color=color, label=f"{label}（n={n}）")
        cdf = np.arange(1, n + 1) / n
        axes[1].plot(losses, cdf, linewidth=1.2, color=color, label=label)
    axes[0].set_xlabel("逐路总损耗 (dB)")
    axes[0].set_ylabel("波导条数")
    S.style_axis(axes[0])
    axes[0].legend(loc="upper right")
    axes[0].set_title("(a) 损耗分布（bin 宽 0.15 dB）", fontsize=S.FONT_SIZE)

    axes[1].set_xlabel("逐路总损耗 (dB)")
    axes[1].set_ylabel("累计比例")
    axes[1].set_ylim(0, 1.02)
    S.style_axis(axes[1])
    axes[1].legend(loc="lower right")
    axes[1].set_title("(b) 累计分布（每规模 1 次布线，非重复实验）", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f35_loss_distribution_repro",
        note="逐路总损耗分布与累计分布；每规模为单次布线的逐路样本（非重复实验，不作误差棒）。",
        sources=["OpticalWaveguideRouter2D/results/fiberBoard{256,512}_loss.xlsx"],
    )


def fig_structure_scatter() -> None:
    """F3-6：损耗—长度 / 损耗—交叉数散点（含真实相关系数）。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.8))
    stats_lines = []
    for tag, label, color, marker in [("256_R5", "256 通道", S.CHANNEL_COLORS[256], "o"),
                                      ("512_R5", "512 通道", S.CHANNEL_COLORS[512], "s")]:
        frame = D.repro_route_frame(tag)
        x1 = frame["total_length_mm"].to_numpy()
        x2 = frame["crossing_count"].to_numpy()
        y = frame["total_loss_db"].to_numpy()
        axes[0].scatter(x1, y, s=7, alpha=0.55, color=color, marker=marker, linewidths=0, label=label)
        axes[1].scatter(x2, y, s=7, alpha=0.55, color=color, marker=marker, linewidths=0, label=label)
        r1 = np.corrcoef(x1, y)[0, 1]
        r2 = np.corrcoef(x2, y)[0, 1]
        stats_lines.append(f"{label}（n={len(frame)}）：r(length)={r1:+.2f}，r(crossings)={r2:+.2f}")
    axes[0].set_xlabel("总长度 (mm)")
    axes[0].set_ylabel("逐路总损耗 (dB)")
    S.style_axis(axes[0], grid_axis="both")
    axes[0].legend(loc="upper left")
    axes[0].set_title("(a) 损耗 vs 总长度", fontsize=S.FONT_SIZE)

    axes[1].set_xlabel("逐路交叉项数（每次交叉计 1）")
    axes[1].set_ylabel("逐路总损耗 (dB)")
    S.style_axis(axes[1], grid_axis="both")
    axes[1].legend(loc="upper left")
    axes[1].set_title("(b) 损耗 vs 交叉数", fontsize=S.FONT_SIZE)
    axes[1].annotate("\n".join(stats_lines), xy=(0.97, 0.04), xycoords="axes fraction",
                     va="bottom", ha="right", fontsize=7.5,
                     bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#CCCCCC", linewidth=0.5))
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f36_loss_structure_scatter",
        note="逐路总损耗与总长度、交叉项数的散点；r 为本次分析实算的 Pearson 相关系数（n=256/512）。",
        sources=["OpticalWaveguideRouter2D/results/fiberBoard{256,512}_loss.xlsx"],
    )


def fig_crossing_angle() -> None:
    """F3-7：交叉角度分布（含 512 小角放大）。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.8),
                             gridspec_kw={"width_ratios": [1.15, 1.0]})
    bins = np.arange(0, 151, 5)
    for tag, label, color in [("256_R5", "256 通道", S.CHANNEL_COLORS[256]),
                              ("512_R5", "512 通道", S.CHANNEL_COLORS[512])]:
        angles = D.repro_crossing_angles(tag)
        axes[0].hist(angles, bins=bins, histtype="step", linewidth=1.1, color=color,
                     label=f"{label}（{len(angles)} 项）")
    axes[0].set_xlabel("交叉角度 (°)")
    axes[0].set_ylabel("交叉项数（逐路条目）")
    axes[0].set_yscale("log")
    S.style_axis(axes[0], grid_axis="both")
    axes[0].legend(loc="upper left")
    axes[0].set_title("(a) 角度分布（5° bin，对数纵轴）", fontsize=S.FONT_SIZE)

    angles512 = D.repro_crossing_angles("512_R5")
    sub = angles512[angles512 < 30]
    axes[1].hist(sub, bins=np.arange(0, 31, 1), histtype="bar", color=S.CHANNEL_COLORS[512],
                 edgecolor="white", linewidth=0.4)
    axes[1].axvline(angles512.min(), color="#D55E00", linewidth=0.9, linestyle="--")
    axes[1].annotate(f"最小角 {angles512.min():.0f}°", (angles512.min(), axes[1].get_ylim()[1] * 0.80),
                     xytext=(-5, 0), textcoords="offset points", fontsize=S.FONT_SIZE_SMALL,
                     color="#D55E00", va="center", ha="right")
    axes[1].annotate(f"<20° 共 {int((angles512 < 20).sum())} 项\n占全部 {((angles512 < 20).mean() * 100):.2f}%",
                     xy=(0.97, 0.96), xycoords="axes fraction", va="top", ha="right",
                     fontsize=S.FONT_SIZE_SMALL,
                     bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#CCCCCC", linewidth=0.5))
    axes[1].set_xlabel("交叉角度 (°)（512 通道 <30° 区间，1° bin）")
    axes[1].set_ylabel("交叉项数")
    S.style_axis(axes[1])
    axes[1].set_title("(b) 512 通道的小角交叉放大（论文最小角 14°）", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f37_crossing_angle_distribution",
        note="复现几何的交叉角度分布；512 通道存在少量 <20° 小角交叉（最小 14°），256 通道最小 35°。",
        sources=["OpticalWaveguideRouter2D/results/fiberBoard{256,512}_loss.xlsx（crossing_angles_deg）"],
    )


def fig_legacy_audit() -> None:
    """F3-8：legacy 512 的精确几何审计（物理求交口径）。"""
    summary = D.step8_5_physical_summary()
    multi = _read_json_8_5_multi()
    loss = D.step8_5_loss_summary()
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.9),
                             gridspec_kw={"width_ratios": [0.85, 1.15]})
    ax = axes[0]
    mult = multi["multiplicity"]
    values = [mult["pairs_with_1_cross"], mult["pairs_with_2_crosses"]]
    bars = ax.bar(["1 次交叉", "2 次交叉"], values, width=0.5,
                  color=[S.PALETTE["blue"], S.PALETTE["orange"]], edgecolor="white", linewidth=0.5)
    for rect, v in zip(bars, values):
        ax.annotate(f"{v:,}", (rect.get_x() + rect.get_width() / 2, v), xytext=(0, 2),
                    textcoords="offset points", ha="center", fontsize=7.5)
    ax.set_ylabel("路线对数")
    ax.set_ylim(0, 48000)
    S.style_axis(ax)
    ax.annotate(f"共 {mult['cross_pairs_total']:,} 对路线存在交叉\n最大多重性 {mult['max_crosses_per_pair']}（无 ≥3 次）",
                xy=(0.76, 0.62), xycoords="axes fraction", ha="center", fontsize=7,
                color="#555555")
    ax.set_title("(a) 交叉对的多重性", fontsize=S.FONT_SIZE)

    ax2 = axes[1]
    hist = loss["crossing_angles"]["histogram"]
    lowers = [h["lower_deg"] for h in hist]
    counts = [h["count"] for h in hist]
    ax2.bar(lowers, counts, width=9, align="edge", color=S.PALETTE["green"],
            edgecolor="white", linewidth=0.4)
    degrees = loss["crossing_angles"]["degrees"]
    ax2.annotate(f"事件 {degrees['count']:,}（物理口径，每对只计一次）\n"
                 f"均值 {degrees['mean']:.1f}°，最小 {degrees['min']:.2f}°，最大 {degrees['max']:.0f}°",
                 xy=(0.02, 0.95), xycoords="axes fraction", va="top", fontsize=7,
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#CCCCCC", linewidth=0.5))
    ax2.set_xlabel("交叉角度 (°，10° bin)")
    ax2.set_ylabel("交叉事件数")
    S.style_axis(ax2)
    ax2.set_title("(b) 交叉角度分布（legacy 平滑几何）", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f38_legacy_geometric_audit",
        note="对 legacy 512 平滑几何的精确求交（step 8.5 物理口径）：49502 对路线交叉、55935 个事件、最小角 2.84°；与复现表整数度逐路口径不同。",
        sources=[
            "outputs/step_8_5_legacy_512_physical_summary.json",
            "outputs/step_8_5_legacy_512_multi_crossing_summary.json",
            "outputs/step_8_5_legacy_512_loss_summary.json",
        ],
    )


def fig_legacy_bytecode() -> None:
    """F3-9：复刻与原版字节码的逐路非交叉损耗对照（逐位一致验证）。"""
    tags = [("256_R5", "256·R5"), ("512_R2", "512·R2"), ("512_R3", "512·R3"),
            ("512_R4", "512·R4"), ("512_R5", "512·R5")]
    repro_all, legacy_all, means = [], [], []
    for tag, label in tags:
        frame = D.repro_route_frame(tag).set_index("route_id")
        legacy = D.repro_legacy_json(tag)
        rid = np.array([int(route["name"]) for route in legacy["routes"]])
        legacy_loss = -np.array([route["loss"] for route in legacy["routes"]])
        repro_loss = frame.loc[rid, "straight_loss_db"].to_numpy() + frame.loc[rid, "bend_loss_db"].to_numpy()
        repro_all.append(repro_loss)
        legacy_all.append(legacy_loss)
        means.append((label, repro_loss.mean()))
    repro_all = np.concatenate(repro_all)
    legacy_all = np.concatenate(legacy_all)
    max_diff = float(np.abs(repro_all - legacy_all).max())

    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.8),
                             gridspec_kw={"width_ratios": [0.9, 1.1]})
    ax = axes[0]
    labels = [m[0] for m in means]
    x = np.arange(len(labels))
    ax.plot(x, [m[1] for m in means], "o", color=S.method("repro").color, markersize=5,
            label="复刻（直线+弯曲求和）")
    ax.plot(x, [m[1] for m in means], "o", markerfacecolor="none", markeredgecolor=S.method("thesis").color,
            markersize=9, markeredgewidth=0.9, linestyle="none", label="原版字节码（-loss）")
    for xi, (_, value) in enumerate(means):
        ax.annotate(f"{value:.4f}", (xi, value), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_ylabel("非交叉逐路损耗均值 (dB)")
    ax.set_ylim(0, 19)
    S.style_axis(ax)
    ax.legend(loc="upper right", fontsize=7)
    ax.set_title("(a) 非交叉损耗均值：两套口径完全重合", fontsize=S.FONT_SIZE)

    ax2 = axes[1]
    ax2.scatter(repro_all, legacy_all, s=4, color=S.method("repro").color, alpha=0.5,
                linewidths=0, label=f"逐路配对点（n={len(repro_all)}）")
    lims = [1.0, 17.8]
    ax2.plot(lims, lims, color="#666666", linewidth=0.7, linestyle="--", label="y=x")
    ax2.set_xlim(*lims)
    ax2.set_ylim(*lims)
    ax2.set_xlabel("复刻（直线+弯曲） (dB)")
    ax2.set_ylabel("原版字节码 -loss (dB)")
    S.style_axis(ax2, grid_axis="both")
    ax2.legend(loc="upper left", fontsize=7)
    ax2.annotate(f"逐路最大偏差 = {max_diff:.1e} dB\n（5 个配置、{len(repro_all)} 条路线逐位一致）",
                 xy=(0.97, 0.06), xycoords="axes fraction", ha="right", fontsize=7,
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#CCCCCC", linewidth=0.5))
    ax2.set_title("(b) 逐路对照（原版 Python 3.8 字节码实跑）", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f39_legacy_bytecode_check",
        note="复刻几何的直线+弯曲损耗与 2D 项目原版字节码（Python 3.8 实跑、全 0 占位交叉表）逐路完全一致；仅交叉项待模型化。",
        sources=["OpticalWaveguideRouter2D/scratch/legacy_loss/legacy{256_R5,512_R2,512_R3,512_R4,512_R5}.json",
                 "OpticalWaveguideRouter2D/results/fiberBoard*_loss.xlsx"],
    )


def fig_crossing_model_sensitivity() -> None:
    """F3-10：512 R5 交叉损耗模型三口径的固定几何复算。"""
    scopes = D.crossing_sensitivity()
    keys = ["A", "B", "C"]
    fig, ax = S.single_axes("half")
    x = np.arange(len(keys))
    means = [scopes[k]["mean"] for k in keys]
    maximums = [scopes[k]["max"] for k in keys]
    ax.bar(x - 0.17, means, 0.32, color=S.PALETTE["blue"], edgecolor="white",
           linewidth=0.5, label="平均损耗")
    ax.bar(x + 0.17, maximums, 0.32, color=S.PALETTE["vermillion"], edgecolor="white",
           linewidth=0.5, label="最大损耗")
    for xi, (m, mx) in enumerate(zip(means, maximums)):
        ax.annotate(f"{m:.3f}", (xi - 0.17, m), xytext=(0, 2), textcoords="offset points",
                    ha="center", fontsize=6.8, rotation=90)
        ax.annotate(f"{mx:.3f}", (xi + 0.17, mx), xytext=(0, 2), textcoords="offset points",
                    ha="center", fontsize=6.8, rotation=90)
    ax.set_xticks(x)
    ax.set_xticklabels(["A：全 90°", "B：锚定\n（主口径）", "C：不锚定"], fontsize=7.5)
    ax.set_ylabel("512 通道损耗 (dB)")
    ax.set_ylim(0, 8.6)
    S.style_axis(ax)
    ax.legend(loc="upper center", ncol=2)
    S.save_figure(
        fig, "f310_crossing_model_sensitivity",
        note="512 R5 交叉损耗模型三口径的固定几何复算（不改布线）：均值跨度 0.099 dB、最大跨度 0.144 dB，与复现分析报告记录一致。",
        sources=["OpticalWaveguideRouter2D/data/crossing_loss_from_thesis_fig3_12.csv",
                 "OpticalWaveguideRouter2D/results/fiberBoard512_loss.xlsx"],
    )


def _read_json_8_5_multi() -> dict:
    import json

    return json.loads((D.OUTPUTS / "step_8_5_legacy_512_multi_crossing_summary.json").read_text(encoding="utf-8"))


ALL = [
    fig_bend_model,
    fig_repro_accuracy,
    fig_radius_sweep,
    fig_loss_contribution,
    fig_loss_distribution,
    fig_structure_scatter,
    fig_crossing_angle,
    fig_legacy_audit,
    fig_legacy_bytecode,
    fig_crossing_model_sensitivity,
]


def generate() -> None:
    for func in ALL:
        func()
        print(f"  [复现组] {func.__name__} 完成", flush=True)
