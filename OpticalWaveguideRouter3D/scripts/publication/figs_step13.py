"""Step 13 图：固定端点六方案主结果、分量分解、最差路线、补修差异、
受约束实验与交叉表敏感性。

主结果与补修数据均取自 outputs/opt2d_step13_fix（最终有效方案）；
旧版 outputs/opt2d_step13 仅用于补修前后差异图（含历史非法几何标注）。
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import pubdata as D
import pubstyle as S

SCHEMES = ["A", "R5U", "D0", "D56", "F5", "F56"]


def _comparison(ch: int):
    return D.step13_comparison(ch, fixed=True).set_index("scheme")


def fig_main() -> None:
    """F6-1：六方案的 mean / P95 / max（256/512）。"""
    metrics = [("mean_loss_db", "平均损耗"), ("p95_loss_db", "P95 损耗"),
               ("max_loss_db", "最大损耗")]
    fig, axes = plt.subplots(1, 3, figsize=(S.FULL_WIDTH, 3.0))
    for index, (ax, (field, label)) in enumerate(zip(axes, metrics)):
        all_values = []
        for ch in (256, 512):
            frame = _comparison(ch)
            all_values.extend([frame.loc[s, field] for s in SCHEMES])
        floor = min(all_values)
        for ch in (256, 512):
            frame = _comparison(ch)
            ys = [frame.loc[scheme, field] for scheme in SCHEMES]
            ax.plot(SCHEMES, ys, color=S.CHANNEL_COLORS[ch], marker=S.CHANNEL_MARKERS[ch],
                    linestyle="-", linewidth=S.LINE_WIDTH, markersize=S.MARKER_SIZE,
                    label=S.CHANNEL_LABELS[ch])
            for scheme, y in zip(SCHEMES, ys):
                dy = 5 if y <= floor + 1e-9 else -11
                ax.annotate(f"{y:.2f}", (scheme, y), xytext=(0, dy), textcoords="offset points",
                            ha="center", fontsize=7)
            span = max(ys) - min(ys)
            ax.set_ylim(min(ys) - span * 0.4, max(ys) + span * 0.3)
        ax.set_xlabel("方案")
        ax.set_ylabel(f"{label} (dB)")
        ax.set_title(f"({'abc'[index]}) {label}", fontsize=S.FONT_SIZE)
        S.style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, -0.035), fontsize=S.FONT_SIZE_SMALL)
    fig.tight_layout(w_pad=0.9)
    S.save_figure(
        fig, "f61_step13_main",
        note="Step 13 补修后六方案逐路损耗（端点冻结、解析物理统计）；F5/F56 为自由弯角几何，D0/D56 使用 R6 优先/自适应半径。",
        sources=["outputs/opt2d_step13_fix/{256,512}/comparison.csv"],
    )


def fig_breakdown() -> None:
    """F6-2：六方案分量分解（256/512 对照，突出交叉升高）。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 3.1))
    for ax, ch in zip(axes, (256, 512)):
        frame = _comparison(ch)
        straight = [frame.loc[s, "mean_straight_loss_db"] for s in SCHEMES]
        bend = [frame.loc[s, "mean_bend_loss_db"] for s in SCHEMES]
        cross = [frame.loc[s, "mean_crossing_loss_db"] for s in SCHEMES]
        total = [frame.loc[s, "mean_loss_db"] for s in SCHEMES]
        x = np.arange(len(SCHEMES))
        ax.bar(x, straight, 0.62, label=S.COMPONENT_STYLE["straight"]["label"],
               color=S.COMPONENT_STYLE["straight"]["color"], edgecolor=S.COMPONENT_STYLE["straight"]["edge"], linewidth=0.5)
        ax.bar(x, bend, 0.62, bottom=straight, label=S.COMPONENT_STYLE["bend"]["label"],
               color=S.COMPONENT_STYLE["bend"]["color"], edgecolor=S.COMPONENT_STYLE["bend"]["edge"], linewidth=0.5)
        ax.bar(x, cross, 0.62, bottom=np.asarray(straight) + np.asarray(bend),
               label=S.COMPONENT_STYLE["crossing"]["label"],
               color=S.COMPONENT_STYLE["crossing"]["color"], edgecolor=S.COMPONENT_STYLE["crossing"]["edge"], linewidth=0.5)
        for xi, t in enumerate(total):
            ax.annotate(f"{t:.3f}", (xi, t), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=7.5)
        ax.set_xticks(x)
        ax.set_xticklabels(SCHEMES)
        ax.set_xlabel("方案")
        ax.set_ylabel("平均逐路损耗 (dB)")
        ax.set_ylim(0, 6.4)
        S.style_axis(ax)
        ax.set_title(f"({'ab'[axes.tolist().index(ax)]}) {ch} 通道", fontsize=S.FONT_SIZE)
    axes[1].legend(loc="upper right", fontsize=S.FONT_SIZE_SMALL)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f62_step13_breakdown",
        note="六方案平均逐路损耗分解；自由弯角（F5/F56）以更高交叉损耗换取更低的弯曲损耗。",
        sources=["outputs/opt2d_step13_fix/{256,512}/comparison.csv"],
    )


def fig_worst_route() -> None:
    """F6-3：最差路线跟踪（256 #44 / 512 #287）的分量与计数。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 3.0))
    for ax, ch in zip(axes, (256, 512)):
        frame = D.step13_worst_tracking(ch).set_index("scheme")
        straight = [frame.loc[s, "straight_loss_db"] for s in SCHEMES]
        bend = [frame.loc[s, "bend_loss_db"] for s in SCHEMES]
        cross = [frame.loc[s, "crossing_loss_db"] for s in SCHEMES]
        total = [frame.loc[s, "total_loss_db"] for s in SCHEMES]
        x = np.arange(len(SCHEMES))
        ax.bar(x, straight, 0.62, label=S.COMPONENT_STYLE["straight"]["label"],
               color=S.COMPONENT_STYLE["straight"]["color"], edgecolor=S.COMPONENT_STYLE["straight"]["edge"], linewidth=0.5)
        ax.bar(x, bend, 0.62, bottom=straight, label=S.COMPONENT_STYLE["bend"]["label"],
               color=S.COMPONENT_STYLE["bend"]["color"], edgecolor=S.COMPONENT_STYLE["bend"]["edge"], linewidth=0.5)
        ax.bar(x, cross, 0.62, bottom=np.asarray(straight) + np.asarray(bend),
               label=S.COMPONENT_STYLE["crossing"]["label"],
               color=S.COMPONENT_STYLE["crossing"]["color"], edgecolor=S.COMPONENT_STYLE["crossing"]["edge"], linewidth=0.5)
        for xi, s in enumerate(SCHEMES):
            row = frame.loc[s]
            ax.annotate(f"{row['total_loss_db']:.3f}", (xi, row["total_loss_db"]),
                        xytext=(0, 3), textcoords="offset points", ha="center", fontsize=7.5)
        route_id = int(frame.loc["A", "worst_route_id_of_A"])
        ax.set_xticks(x)
        ax.set_xticklabels(SCHEMES)
        ax.set_xlabel("方案")
        ax.set_ylabel("最差路线总损耗 (dB)")
        ax.set_ylim(0, max(total) * 1.12)
        S.style_axis(ax)
        ax.set_title(f"({'ab'[axes.tolist().index(ax)]}) {ch} 通道最差路线 #{route_id}", fontsize=S.FONT_SIZE)
    axes[1].legend(loc="upper right", fontsize=S.FONT_SIZE_SMALL)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f63_step13_worst_route",
        note="A 方案最差路线在六方案中的逐路损耗与交叉数/总转角；该路线跨上下两侧，自由弯角将其总转角从 180° 降至 90°。",
        sources=["outputs/opt2d_step13/{256,512}/worst_route_tracking.csv"],
    )


def fig_fix_delta() -> None:
    """F6-4：补修前后差异（256 F56 的 48 条路线；历史非法几何标注）。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 3.0),
                             gridspec_kw={"width_ratios": [1.15, 1.0]})
    ax = axes[0]
    delta = D.step13_fix_per_route_delta(256)
    sub = delta[delta["scheme"] == "F56"]
    changed = sub[sub["changed"] == True]  # noqa: E712
    unchanged = sub[sub["changed"] != True]  # noqa: E712
    ax.scatter(unchanged["old_total_loss_db"], unchanged["new_total_loss_db"], s=8,
               color="#BBBBBB", linewidths=0, label=f"未变化（{len(unchanged)} 条）")
    ax.scatter(changed["old_total_loss_db"], changed["new_total_loss_db"], s=16,
               color=S.method("F56").color, linewidths=0, label=f"重布变化（{len(changed)} 条）")
    lims = [1.0, 5.6]
    ax.plot(lims, lims, color="#666666", linewidth=0.7, linestyle="--", label="y=x")
    ax.set_xlim(*lims)
    ax.set_ylim(*lims)
    ax.set_xlabel("补修前逐路损耗 (dB)")
    ax.set_ylabel("补修后逐路损耗 (dB)")
    S.style_axis(ax, grid_axis="both")
    ax.legend(loc="upper left", fontsize=S.FONT_SIZE_SMALL)
    ax.set_title("(a) 256 通道 F56 补修前后逐路对照", fontsize=S.FONT_SIZE)

    ax2 = axes[1]
    old = D.step13_comparison(256, fixed=False).set_index("scheme")
    new = D.step13_comparison(256, fixed=True).set_index("scheme")
    metrics = [("mean_loss_db", "平均损耗 (dB)"),
               ("unique_crossing_events", "唯一交叉数"),
               ("contact_touch_count", "段级接触 (raw)"),
               ("crossings_under_10deg", "<10° 交叉")]
    ypos = np.arange(len(metrics))[::-1]
    values = [(old.loc["F56", f], new.loc["F56", f]) for f, _ in metrics]
    rel = [(n - o) / o * 100.0 for o, n in values]
    colors = [S.method("F56").color if v >= 0 else "#2F6B2F" for v in rel]
    ax2.barh(ypos, rel, height=0.5, color=colors)
    ax2.axvline(0, color="#444444", linewidth=0.8)
    for y, (o, n), v in zip(ypos, values, rel):
        ax2.annotate(f"{v:+.2f}%", (v, y), xytext=(4 if v >= 0 else -4, 0),
                     textcoords="offset points", va="center",
                     ha="left" if v >= 0 else "right", fontsize=7.5)
        ax2.annotate(f"{o:g} → {n:g}", (v, y), xytext=(0, -13), textcoords="offset points",
                     va="center", ha="center", fontsize=6.8, color="#555555")
    ax2.set_yticks(ypos)
    ax2.set_yticklabels([m[1] for m in metrics], fontsize=S.FONT_SIZE_SMALL)
    ax2.set_xlabel("补修后相对补修前的变化 (%)")
    ax2.set_xlim(-2.2, 1.2)
    ax2.set_ylim(-0.7, len(metrics) - 0.3)
    S.style_axis(ax2, grid_axis="x")
    ax2.set_title("(b) 256 通道 F56 补修前后变化率（#7/#31 重合 152.007 mm）", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=1.2)
    S.save_figure(
        fig, "f64_step13_fix_delta",
        note="Step 13 补修：256 F56 重布历史重合对 #7/#31 后 48 条路线变化；512 补修前后逐项相同（零变化）。",
        sources=[
            "outputs/opt2d_step13_fix/256/per_route_delta.csv",
            "outputs/opt2d_step13/{,fix/}256/comparison.csv",
        ],
    )


def fig_constrained() -> None:
    """F6-5：受约束实验（base/spacing/small/both）的指标权衡。"""
    configs = ["base", "spacing", "small", "both"]
    metrics = [("mean_loss_db", "平均损耗 (dB)", 1.0),
               ("crossings_under_20_deg", "<20° 交叉数", 1.0),
               ("spacing_violation_count", "间距违规 (路线对)", 1.0)]
    fig, axes = plt.subplots(1, 3, figsize=(S.FULL_WIDTH, 2.8))
    for index, (ax, (field, label, _)) in enumerate(zip(axes, metrics)):
        for ch in (256, 512):
            frame = D.step13_constrained(ch).set_index("config")
            ys = [frame.loc[c, field] for c in configs]
            ax.plot(configs, ys, color=S.CHANNEL_COLORS[ch], marker=S.CHANNEL_MARKERS[ch],
                    linewidth=S.LINE_WIDTH, markersize=S.MARKER_SIZE, label=S.CHANNEL_LABELS[ch])
            for cfg, y in zip(configs, ys):
                fmt = f"{y:.3f}" if field == "mean_loss_db" else f"{int(y)}"
                ax.annotate(fmt, (cfg, y), xytext=(0, -11 if index == 0 else 4),
                            textcoords="offset points", ha="center", fontsize=7)
            if field != "mean_loss_db":
                span = max(ys) - min(ys)
                ax.set_ylim(min(ys) - span * 0.35, max(ys) + span * 0.35)
        ax.set_xlabel("配置")
        ax.set_ylabel(label)
        ax.set_title(f"({'abc'[index]}) {label.split(' ')[0]}", fontsize=S.FONT_SIZE)
        S.style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, -0.04), fontsize=S.FONT_SIZE_SMALL)
    fig.tight_layout(w_pad=0.9)
    S.save_figure(
        fig, "f65_step13_constrained",
        note="受约束复算（固定几何、只改评分）：spacing/small/both 降低间距违规与大角交叉，代价是平均损耗略升；512 的代价高于 256。",
        sources=["outputs/opt2d_step13_constrained/{256,512}/constrained_comparison.csv"],
    )


def fig_sensitivity() -> None:
    """F6-6：交叉损耗表压力情景（×1/×2/×5/×10）下的最大损耗。"""
    factors = [1, 2, 5, 10]
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 3.0))
    for ax, ch in zip(axes, (256, 512)):
        frame = D.step13_fix_sensitivity(ch)
        for scheme in SCHEMES:
            sub = frame[frame["scheme"] == scheme].set_index("factor")
            ys = [sub.loc[f, "max_loss_db"] for f in factors]
            style = S.method(scheme)
            ax.plot(factors, ys, color=style.color, marker=style.marker,
                    linewidth=S.LINE_WIDTH, markersize=3.6, label=style.display)
        sub = frame[frame["scheme"] == "F56"].set_index("factor")
        ax.annotate(f"F56 ×10：{sub.loc[10, 'max_loss_db']:.3f} dB",
                    xy=(10, sub.loc[10, "max_loss_db"]), xytext=(-6, 6),
                    textcoords="offset points", ha="right", fontsize=7.5,
                    color=S.method("F56").color)
        ax.set_xticks(factors)
        ax.set_xticklabels([f"×{f}" for f in factors])
        ax.set_xlabel("交叉损耗放大倍数（<20° 区间）")
        ax.set_ylabel("最大逐路损耗 (dB)")
        ax.set_title(f"({'ab'[axes.tolist().index(ax)]}) {ch} 通道", fontsize=S.FONT_SIZE)
        S.style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False,
               bbox_to_anchor=(0.5, -0.16), fontsize=6.6)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f66_step13_sensitivity",
        note="固定几何压力情景：仅放大小角度交叉损耗（×1/×2/×5/×10）后复算，不重新布线；F56 的最大损耗对 ×10 情景最敏感。",
        sources=["outputs/opt2d_step13_fix/{256,512}/sensitivity.csv"],
    )


def fig_penalty_ablation() -> None:
    """F6-7：间距惩罚强度扫描（F5/F56 × 0/0.02/0.05 × 256/512）。"""
    from pubdata import step13_fix_penalty_ablation
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.9))
    penalties = [0.0, 0.02, 0.05]
    for ax, field, label in ((axes[0], "spacing_violation_count", "间距违规 (路线对)"),
                             (axes[1], "mean_loss_db", "平均损耗 (dB)")):
        for scheme in ("F5", "F56"):
            for ch, linestyle, marker_suffix in ((256, "-", ""), (512, "--", "")):
                # 默认（0 dB）行来自 comparison.csv，0.02/0.05 来自 penalty_ablation
                comparison = D.step13_comparison(ch, fixed=True).set_index("scheme")
                values = [comparison.loc[scheme, field]]
                ablation = step13_fix_penalty_ablation(ch, scheme).set_index("spacing_penalty_db")
                for p in (0.02, 0.05):
                    values.append(ablation.loc[p, field])
                style = S.method(scheme)
                ax.plot(penalties, values,
                        color=style.color, linestyle=linestyle,
                        marker=style.marker if ch == 256 else "s",
                        linewidth=S.LINE_WIDTH, markersize=3.6,
                        label=f"{scheme}·{ch}")
        ax.set_xticks(penalties)
        ax.set_xticklabels(["0（默认）", "0.02", "0.05"])
        ax.set_xlabel("间距惩罚强度 (dB/路线对)")
        ax.set_ylabel(label)
        S.style_axis(ax)
    axes[0].legend(loc="upper right", fontsize=6.6, ncol=2)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f67_step13_penalty_ablation",
        note="间距惩罚强度扫描（F5/F56，固定几何评分）：0.02/0.05 dB 显著降低间距违规，平均损耗代价随时间/规模不同。",
        sources=[
            "outputs/opt2d_step13_fix/{256,512}/penalty_ablation_F{5,56}.csv",
            "outputs/opt2d_step13_fix/{256,512}/comparison.csv（默认 0 dB 行）",
        ],
    )


ALL = [fig_main, fig_breakdown, fig_worst_route, fig_fix_delta, fig_constrained,
       fig_sensitivity, fig_penalty_ablation]


def generate() -> None:
    for func in ALL:
        func()
        print(f"  [Step 13] {func.__name__} 完成", flush=True)
