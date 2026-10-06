"""Step 12（A/B/C/D）主结果、分量分解、消融与效率图。

数据来自 outputs/opt2d/{256,512}/comparison.csv、comparison.json、
sensitivity.json 与 sensitivity/*/summary.json。
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import pubdata as D
import pubstyle as S

SCHEMES = ["A", "B", "C", "D"]

# 消融配置的中文显示名与分组（与 sensitivity.json 的键一致）
ABLATION_GROUPS = [
    ("候选数 K", ["cand_k1", "cand_k4", "cand_k8", "cand_k16"]),
    ("布线顺序", ["order_span", "order_congestion"]),
    ("拆线重布", ["refine_on"]),
    ("位置正则 (dB/位)", ["penalty_0", "penalty_0.001", "penalty_0.01", "penalty_0.05"]),
    ("半径策略", ["radius_fixed_R6", "radius_adaptive"]),
]
ABLATION_LABELS = {
    "cand_k1": "K=1", "cand_k4": "K=4", "cand_k8": "K=8（默认）", "cand_k16": "K=16",
    "order_span": "顺序：span", "order_congestion": "顺序：congestion",
    "refine_on": "拆线重布开",
    "penalty_0": "0", "penalty_0.001": "0.001", "penalty_0.01": "0.01", "penalty_0.05": "0.05",
    "radius_fixed_R6": "固定 R6", "radius_adaptive": "自适应 R5/R6",
}


def fig_main() -> None:
    """F5-1：A/B/C/D 的平均、P95、最大损耗（256/512 对照）。"""
    metrics = [("mean_loss_db", "平均损耗 (dB)"), ("p95_loss_db", "P95 损耗 (dB)"),
               ("max_loss_db", "最大损耗 (dB)")]
    fig, axes = plt.subplots(1, 3, figsize=(S.FULL_WIDTH, 2.9))
    for index, (ax, (field, label)) in enumerate(zip(axes, metrics)):
        all_values = []
        for ch in (256, 512):
            frame = D.step12_comparison(ch).set_index("label")
            for scheme in SCHEMES:
                row = frame.loc[[i for i in frame.index if i.startswith(scheme)][0]]
                all_values.append(row[field])
        floor = min(all_values)
        for ch in (256, 512):
            frame = D.step12_comparison(ch).set_index("label")
            ys = []
            for scheme in SCHEMES:
                row = frame.loc[[i for i in frame.index if i.startswith(scheme)][0]]
                ys.append(row[field])
            ax.plot(SCHEMES, ys, color=S.CHANNEL_COLORS[ch], marker=S.CHANNEL_MARKERS[ch],
                    linestyle="-", linewidth=S.LINE_WIDTH, markersize=S.MARKER_SIZE,
                    label=S.CHANNEL_LABELS[ch], clip_on=False)
            for scheme, y in zip(SCHEMES, ys):
                dy = 5 if y <= floor + 1e-9 else -11
                ax.annotate(f"{y:.2f}", (scheme, y), xytext=(0, dy), textcoords="offset points",
                            ha="center", fontsize=7.5)
            span = max(ys) - min(ys)
            ax.set_ylim(min(ys) - span * 0.45, max(ys) + span * 0.28)
        if index == 0:
            # 512 的 B 方案未布通 2 条：在数据点上方明确标注
            frame512 = D.step12_comparison(512).set_index("label")
            row_b = frame512.loc[[i for i in frame512.index if i.startswith("B")][0]]
            ax.annotate(f"512 的 B 未布通 {int(row_b['unplaced_count'])} 条",
                        xy=("B", row_b[field]), xytext=(0, 14), textcoords="offset points",
                        ha="center", fontsize=7.5, color="#B22222",
                        arrowprops=dict(arrowstyle="-", color="#B22222", linewidth=0.6))
        ax.set_xlabel("方案")
        ax.set_ylabel(label)
        ax.set_title(f"({'abc'[index]}) {label.split(' ')[0]}", fontsize=S.FONT_SIZE)
        S.style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, -0.03), fontsize=S.FONT_SIZE_SMALL)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f51_step12_main",
        note="Step 12 方案 A–D 的逐路损耗指标（解析物理统计口径）；512 的 B 方案有 2 条未布通，其指标不作同口径比较。",
        sources=["outputs/opt2d/{256,512}/comparison.csv、comparison.json"],
    )


def fig_breakdown() -> None:
    """F5-2：损耗分量分解（A–D × 256/512）。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.9))
    for ax, ch in zip(axes, (256, 512)):
        frame = D.step12_comparison(ch).set_index("label")
        means, bends, crosses, totals = [], [], [], []
        for scheme in SCHEMES:
            row = frame.loc[[i for i in frame.index if i.startswith(scheme)][0]]
            means.append(row["mean_straight_loss_db"])
            bends.append(row["mean_bend_loss_db"])
            crosses.append(row["mean_crossing_loss_db"])
            totals.append(row["mean_loss_db"])
        x = np.arange(len(SCHEMES))
        ax.bar(x, means, 0.6, label=S.COMPONENT_STYLE["straight"]["label"],
               color=S.COMPONENT_STYLE["straight"]["color"], edgecolor=S.COMPONENT_STYLE["straight"]["edge"], linewidth=0.5)
        ax.bar(x, bends, 0.6, bottom=means, label=S.COMPONENT_STYLE["bend"]["label"],
               color=S.COMPONENT_STYLE["bend"]["color"], edgecolor=S.COMPONENT_STYLE["bend"]["edge"], linewidth=0.5)
        ax.bar(x, crosses, 0.6, bottom=np.asarray(means) + np.asarray(bends),
               label=S.COMPONENT_STYLE["crossing"]["label"],
               color=S.COMPONENT_STYLE["crossing"]["color"], edgecolor=S.COMPONENT_STYLE["crossing"]["edge"], linewidth=0.5)
        for xi, (total, cross) in enumerate(zip(totals, crosses)):
            ax.annotate(f"{total:.3f}", (xi, total), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=S.FONT_SIZE_SMALL)
            if cross > 0.15:  # 交叉分量足够大时单独标出数值
                ax.annotate(f"交叉 {cross:.3f}", (xi, 0.17), rotation=90, ha="center",
                            va="bottom", fontsize=7, color="#2F6B2F")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{s}" for s in SCHEMES])
        ax.set_xlabel("方案")
        ax.set_ylabel("平均逐路损耗 (dB)")
        ax.set_ylim(0, 7.6)
        S.style_axis(ax)
        ax.set_title(f"({'ab'[axes.tolist().index(ax)]}) {ch} 通道", fontsize=S.FONT_SIZE)
    axes[0].legend(loc="upper center", ncol=3, fontsize=8, bbox_to_anchor=(1.05, 1.02))
    fig.tight_layout()
    S.save_figure(
        fig, "f52_step12_loss_breakdown",
        note="A–D 方案平均逐路损耗的直线/弯曲/交叉分解；交叉事件按每根波导各计一次。",
        sources=["outputs/opt2d/{256,512}/comparison.csv"],
    )


def fig_ablation() -> None:
    """F5-3：消融（候选数/顺序/拆线/正则/半径）——平均损耗与运行时间。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 4.0),
                             gridspec_kw={"width_ratios": [1.5, 1.0]})
    ax = axes[0]
    configs, labels, groups = [], [], []
    for group, keys in ABLATION_GROUPS:
        for key in keys:
            configs.append(key)
            labels.append(ABLATION_LABELS[key])
            groups.append(group)
    ypos = np.arange(len(configs))[::-1]
    for ch in (256, 512):
        frame = D.step12_sensitivity_frame(ch).set_index("config")
        xs, unplaced = [], []
        for key in configs:
            row = frame.loc[key]
            xs.append(row["mean_loss_db"])
            unplaced.append(int(row["unplaced_count"]))
        ax.scatter(xs, ypos, s=26, c=[S.CHANNEL_COLORS[ch]] * len(configs),
                   marker=S.CHANNEL_MARKERS[ch], label=S.CHANNEL_LABELS[ch], zorder=3, linewidths=0)
        for x, y, up in zip(xs, ypos, unplaced):
            if up > 0:
                ax.scatter([x], [y], s=110, facecolors="none", edgecolors="#B22222",
                           linewidths=0.9, zorder=2)
        ax.plot(xs, ypos, color="#CCCCCC", linewidth=0.7, zorder=1)
    # 参考线：默认配置（C）的值（256 取 cand_k8 = penalty_0.001 值，512 取 cand_k8）
    for ch in (256, 512):
        frame = D.step12_sensitivity_frame(ch).set_index("config")
        ax.axvline(frame.loc["cand_k8", "mean_loss_db"], color=S.CHANNEL_COLORS[ch],
                   linewidth=0.6, linestyle=":", alpha=0.7)
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=S.FONT_SIZE_SMALL)
    # 分组背景条纹：标签索引 i 对应 y = (n-1) - i
    n = len(configs)
    bounds: dict[str, list[int]] = {}
    for index, group in enumerate(groups):
        bounds.setdefault(group, []).append(index)
    for group, index_list in bounds.items():
        y_top = (n - 1) - min(index_list) + 0.5
        y_bottom = (n - 1) - max(index_list) - 0.5
        for target in (ax,):
            target.axhspan(y_bottom, y_top, color="#F2F2F2", zorder=0)
        ax.annotate(group, xy=(0.985, (y_top + y_bottom) / 2), xycoords=("axes fraction", "data"),
                    ha="right", va="center", fontsize=7, color="#777777",
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=0.6))
    ax.set_xlabel("平均逐路损耗 (dB)")
    ax.set_xlim(4.25, 5.75)
    S.style_axis(ax, grid_axis="x")
    ax.legend(loc="lower center", fontsize=S.FONT_SIZE_SMALL)
    ax.set_title("(a) 消融配置的平均损耗（点=配置，红圈=有未布通）", fontsize=S.FONT_SIZE)

    ax2 = axes[1]
    for ch in (256, 512):
        frame = D.step12_sensitivity_frame(ch).set_index("config")
        xs = [frame.loc[key, "runtime_s"] for key in configs]
        ax2.scatter(xs, ypos, s=26, c=S.CHANNEL_COLORS[ch], marker=S.CHANNEL_MARKERS[ch],
                    label=S.CHANNEL_LABELS[ch], zorder=3, linewidths=0)
        ax2.plot(xs, ypos, color="#CCCCCC", linewidth=0.7, zorder=1)
    ax2.set_yticks(ypos)
    ax2.set_yticklabels([])
    for group, index_list in bounds.items():
        y_top = (n - 1) - min(index_list) + 0.5
        y_bottom = (n - 1) - max(index_list) - 0.5
        ax2.axhspan(y_bottom, y_top, color="#F2F2F2", zorder=0)
    ax2.set_xscale("log")
    ax2.set_xlabel("运行时间 (s，对数轴)")
    S.style_axis(ax2, grid_axis="x")
    ax2.set_title("(b) 运行时间", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=0.6)
    S.save_figure(
        fig, "f53_step12_ablation",
        note="Step 12 消融：候选数 K、布线顺序、拆线重布、位置正则、半径策略；未布通配置的均值不能与完整布通配置同口径比较。",
        sources=["outputs/opt2d/{256,512}/sensitivity.json 与 sensitivity/*/summary.json"],
    )


def fig_efficiency() -> None:
    """F5-4：效率视角——运行时间 vs 平均损耗（主方案 + 消融配置）。"""
    fig, ax = S.single_axes("half")
    configs = [key for _, keys in ABLATION_GROUPS for key in keys]
    for ch in (256, 512):
        # 主方案 A–D
        frame = D.step12_comparison(ch).set_index("label")
        ax.scatter(frame["runtime_s"], frame["mean_loss_db"], s=34,
                   c=S.CHANNEL_COLORS[ch], marker=S.CHANNEL_MARKERS[ch], linewidths=0,
                   zorder=3, label=f"{S.CHANNEL_LABELS[ch]}：主方案")
        # 消融配置
        sens = D.step12_sensitivity_frame(ch).set_index("config")
        ax.scatter(sens.loc[configs, "runtime_s"], sens.loc[configs, "mean_loss_db"], s=14,
                   facecolors="none", edgecolors=S.CHANNEL_COLORS[ch], linewidths=0.7,
                   marker=S.CHANNEL_MARKERS[ch], zorder=3, label=f"{S.CHANNEL_LABELS[ch]}：消融")
        # 标注主方案
        for label in frame.index:
            ax.annotate(label.split("-")[0], (frame.loc[label, "runtime_s"], frame.loc[label, "mean_loss_db"]),
                        xytext=(4, 3), textcoords="offset points", fontsize=7.5)
    ax.set_xscale("log")
    ax.set_xlabel("运行时间 (s，对数轴)")
    ax.set_ylabel("平均逐路损耗 (dB)")
    S.style_axis(ax, grid_axis="both")
    ax.legend(loc="lower left", fontsize=7)
    S.save_figure(
        fig, "f54_step12_efficiency",
        note="运行时间—平均损耗散点：实心为主方案 A–D，空心为消融配置；含未布通配置的损耗不可直接比较。",
        sources=["outputs/opt2d/{256,512}/comparison.csv、sensitivity.json"],
    )


ALL = [fig_main, fig_breakdown, fig_ablation, fig_efficiency]


def generate() -> None:
    for func in ALL:
        func()
        print(f"  [Step 12] {func.__name__} 完成", flush=True)
