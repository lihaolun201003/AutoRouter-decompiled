"""Step 14 图：冻结半径公平对照、固定保护对象、压力情景、接受过程与诊断。

全部数据来自 outputs/opt2d_step14/{256,512}（comparison、acceptance、
protection_margins、protection_routes、optimize_attempts_base、
optimize_record、probe、sensitivity）。

口径提示：
* touch 配置与 base 完全相同（物理接触数为 0，惩罚无作用对象）；
* 严格验收（mean_slack 0.05 dB、逐路保护不劣化、压力情景最大严格下降）
  与放宽余量的诊断（probe）分开呈现；
* 512 的 opt_base 行 runtime_s=0.0 是脚本复制字段，真实优化耗时以
  optimize_record.json 的 762.24 s 为准。
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

import pubdata as D
import pubstyle as S

SCHEMES = ["base", "spacing", "small", "touch", "both", "opt_base"]


def _comparison(ch: int):
    return D.step14_comparison(ch).set_index("scheme")


def fig_main() -> None:
    """F7-1：Step 14 六方案 mean / P95 / max（冻结半径公平对照 + 验收状态）。"""
    metrics = [("mean_loss_db", "平均损耗"), ("p95_loss_db", "P95 损耗"),
               ("max_loss_db", "最大损耗")]
    acceptance = {ch: D.step14_acceptance(ch).set_index("scheme") for ch in (256, 512)}
    short = {"base": "base", "spacing": "spacing", "small": "small",
             "touch": "touch", "both": "both", "opt_base": "opt"}
    ticklabels = [short[s] + ("" if acceptance[512].loc[s, "ok"] else " ×") for s in SCHEMES]
    fig, axes = plt.subplots(1, 3, figsize=(S.FULL_WIDTH, 3.0))
    for index, (ax, (field, label)) in enumerate(zip(axes, metrics)):
        all_values = []
        for ch in (256, 512):
            frame = _comparison(ch)
            all_values.extend([frame.loc[s, field] for s in SCHEMES])
        floor = min(all_values)
        for ch in (256, 512):
            frame = _comparison(ch)
            ys = [frame.loc[s, field] for s in SCHEMES]
            ax.plot(range(len(SCHEMES)), ys, color=S.CHANNEL_COLORS[ch],
                    marker=S.CHANNEL_MARKERS[ch], linewidth=S.LINE_WIDTH,
                    markersize=S.MARKER_SIZE, label=S.CHANNEL_LABELS[ch])
            for xi, y in enumerate(ys):
                dy = 5 if y <= floor + 1e-9 else -11
                ax.annotate(f"{y:.3f}", (xi, y), xytext=(0, dy), textcoords="offset points",
                            ha="center", fontsize=6.8)
            span = max(ys) - min(ys)
            ax.set_ylim(min(ys) - span * 0.45, max(ys) + span * 0.3)
        ax.set_xticks(range(len(SCHEMES)))
        ax.set_xticklabels(ticklabels, fontsize=S.FONT_SIZE_SMALL, rotation=32, ha="right")
        ax.set_xlabel("配置")
        ax.set_ylabel(f"{label} (dB)")
        ax.set_title(f"({'abc'[index]}) {label}", fontsize=S.FONT_SIZE)
        S.style_axis(ax)
    axes[0].annotate("×=未通过严格验收\n（保护对象劣化）\ntouch ≡ base（无接触）", xy=(0.03, 0.03),
                     xycoords="axes fraction", fontsize=6.4, color="#666666",
                     bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.88,
                               edgecolor="none"))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, -0.04), fontsize=S.FONT_SIZE_SMALL)
    fig.tight_layout(w_pad=0.9)
    S.save_figure(
        fig, "f71_step14_main",
        note="Step 14 冻结半径公平对照：六配置的逐路损耗指标与严格验收状态（×为未通过）；touch 与 base 逐项相同（无接触事件）。",
        sources=["outputs/opt2d_step14/{256,512}/comparison.csv、acceptance.csv"],
    )


def fig_scenario() -> None:
    """F7-2：标称与 ×5 压力情景的最大损耗。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 3.1))
    for ax, ch in zip(axes, (256, 512)):
        frame = _comparison(ch)
        nominal = [frame.loc[s, "max_loss_db"] for s in SCHEMES]
        scenario = [frame.loc[s, "scenario5_max_loss_db"] for s in SCHEMES]
        x = np.arange(len(SCHEMES))
        ax.plot(x, nominal, color="#666666", marker="o", linewidth=S.LINE_WIDTH,
                markersize=3.6, label="标称最大损耗")
        ax.plot(x, scenario, color=S.method("opt_base").color, marker="s",
                linewidth=S.LINE_WIDTH, markersize=3.6, label="×5 压力情景最大损耗")
        for xi, (a, b) in enumerate(zip(nominal, scenario)):
            if SCHEMES[xi] in ("base", "opt_base"):
                ax.annotate(f"{a:.3f}", (xi, a), xytext=(0, -11), textcoords="offset points",
                            ha="center", fontsize=7)
                ax.annotate(f"{b:.3f}", (xi, b), xytext=(0, 5), textcoords="offset points",
                            ha="center", fontsize=7, color=S.method("opt_base").color)
        # opt_base 相对 base 的情景变化（0 接受时为"相同"）
        diff = frame.loc["opt_base", "scenario5_max_loss_db"] - frame.loc["base", "scenario5_max_loss_db"]
        if abs(diff) < 1e-9:
            text = "opt_base 与 base 相同（0 接受）"
        elif diff < 0:
            text = f"opt_base 相对 base 下降 {abs(diff):.4f} dB"
        else:
            text = f"opt_base 相对 base 略升 {diff:.4f} dB"
        ax.annotate(text, xy=(0.97, 0.04), xycoords="axes fraction", ha="right", va="bottom",
                    fontsize=6.8, color=S.method("opt_base").color,
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.88,
                              edgecolor="none"))
        ax.set_xticks(x)
        ax.set_xticklabels(["base", "spacing", "small", "touch", "both", "opt"],
                           fontsize=S.FONT_SIZE_SMALL, rotation=32, ha="right")
        ax.set_xlabel("配置")
        ax.set_ylabel("最大逐路损耗 (dB)")
        ax.set_title(f"({'ab'[axes.tolist().index(ax)]}) {ch} 通道", fontsize=S.FONT_SIZE)
        S.style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, -0.12), fontsize=S.FONT_SIZE_SMALL)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f72_step14_scenario5",
        note="×5 压力情景（<20° 交叉损耗 ×5，固定几何复算）：512 的 opt_base 情景最大下降 0.0924 dB；256 的 opt_base 与 base 相同（0 接受）。",
        sources=["outputs/opt2d_step14/{256,512}/comparison.csv、references.csv"],
    )


def fig_small_angle() -> None:
    """F7-3：小角交叉计数（<5°/<10°/<20°）。"""
    fig, axes = plt.subplots(1, 3, figsize=(S.FULL_WIDTH, 2.8))
    fields = [("crossings_under_5_deg", "<5° 交叉数"), ("crossings_under_10_deg", "<10° 交叉数"),
              ("crossings_under_20_deg", "<20° 交叉数")]
    for index, (ax, (field, label)) in enumerate(zip(axes, fields)):
        for ch in (256, 512):
            frame = _comparison(ch)
            ys = [frame.loc[s, field] for s in SCHEMES]
            ax.plot(range(len(SCHEMES)), ys, color=S.CHANNEL_COLORS[ch],
                    marker=S.CHANNEL_MARKERS[ch], linewidth=S.LINE_WIDTH,
                    markersize=S.MARKER_SIZE, label=S.CHANNEL_LABELS[ch])
            for xi, y in enumerate(ys):
                ax.annotate(f"{int(y)}", (xi, y), xytext=(0, -11), textcoords="offset points",
                            ha="center", fontsize=6.8)
            span = max(ys) - min(ys)
            ax.set_ylim(min(ys) - span * 0.35, max(ys) + span * 0.3)
        ax.set_xticks(range(len(SCHEMES)))
        ax.set_xticklabels(["base", "spacing", "small", "touch", "both", "opt"],
                           fontsize=S.FONT_SIZE_SMALL, rotation=32, ha="right")
        ax.set_xlabel("配置")
        ax.set_ylabel(label)
        ax.set_title(f"({'abc'[index]}) {label.split(' ')[0]}", fontsize=S.FONT_SIZE)
        S.style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, -0.10), fontsize=S.FONT_SIZE_SMALL)
    fig.tight_layout(w_pad=0.9)
    S.save_figure(
        fig, "f73_step14_small_angle",
        note="小角度交叉计数（逐路累计口径）：small/both 显著压低 <20° 交叉；spacing 主要压低 <5° 与间距违规。",
        sources=["outputs/opt2d_step14/{256,512}/comparison.csv"],
    )


def fig_protection() -> None:
    """F7-4：固定保护对象（11 条）逐路损耗差值热力图。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 3.6),
                             gridspec_kw={"width_ratios": [1.0, 1.0]})
    for ax, ch in zip(axes, (256, 512)):
        protection = D.step14_protection_set(ch)
        route_ids = protection["all_ids"]
        matrix = np.zeros((len(route_ids), len(SCHEMES)))
        for j, scheme in enumerate(SCHEMES):
            if scheme == "base":
                continue
            frame = D.step14_protection_routes(ch, scheme).set_index("route_id")
            for i, rid in enumerate(route_ids):
                matrix[i, j] = frame.loc[rid, "delta_vs_base_db"]
        vmax = np.abs(matrix).max()
        norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
        im = ax.imshow(matrix, cmap="RdBu_r", norm=norm, aspect="auto")
        for i in range(len(route_ids)):
            for j in range(len(SCHEMES)):
                value = matrix[i, j]
                color = "white" if abs(value) > 0.65 * vmax else "black"
                ax.annotate(f"{value:+.3f}", (j, i), ha="center", va="center",
                            fontsize=6.2, color=color)
        ax.set_yticks(range(len(route_ids)))
        worst = protection["base_worst"]
        labels = [f"#{rid}*" if rid == worst else f"#{rid}" for rid in route_ids]
        ax.set_yticklabels(labels, fontsize=7)
        ax.set_xticks(range(len(SCHEMES)))
        ax.set_xticklabels(SCHEMES, fontsize=7, rotation=30, ha="right")
        ax.set_title(f"({'ab'[axes.tolist().index(ax)]}) {ch} 通道（{len(route_ids)} 条固定对象）",
                     fontsize=S.FONT_SIZE)
    # 颜色条（共享）
    cbar = fig.colorbar(im, ax=axes, fraction=0.03, pad=0.02)
    cbar.set_label("逐路损耗差值 (dB)，正=劣化", fontsize=7)
    cbar.ax.tick_params(labelsize=7)
    S.save_figure(
        fig, "f74_step14_protection_delta",
        note="Step 14 固定保护对象（Step 14 保存的 11 条 ID 集合，*=base 最差路线）在六配置下的逐路损耗差值；spacing/small/both 在部分对象上劣化，opt_base 全部不劣化。",
        sources=[
            "outputs/opt2d_step14/{256,512}/protection_set.json",
            "outputs/opt2d_step14/{256,512}/{scheme}/protection_routes.csv",
        ],
    )


def fig_optimize() -> None:
    """F7-5：opt_base 接受过程与拒绝原因。"""
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 3.2),
                             gridspec_kw={"width_ratios": [1.2, 1.0]})
    ax = axes[0]
    for ch, marker, offset in ((256, "o", -0.02), (512, "s", 0.02)):
        attempts = D.step14_attempts(ch)
        accepted = attempts[attempts["accepted"] == True]  # noqa: E712
        rejected = attempts[attempts["accepted"] != True]  # noqa: E712
        xr = np.arange(len(rejected))
        ax.scatter(xr, rejected["scenario_gain_db"] + offset, s=12, facecolors="none",
                   edgecolors=S.CHANNEL_COLORS[ch], linewidths=0.7, marker=marker,
                   label=f"{S.CHANNEL_LABELS[ch]}：拒绝（{len(rejected)} 次）")
        if len(accepted):
            xa = np.arange(len(rejected), len(rejected) + len(accepted))
            ax.scatter(xa, accepted["scenario_gain_db"] + offset, s=26,
                       color=S.CHANNEL_COLORS[ch], marker=marker, linewidths=0,
                       label=f"{S.CHANNEL_LABELS[ch]}：接受（{len(accepted)} 次）")
        else:
            ax.annotate(f"{S.CHANNEL_LABELS[ch]}：0 次接受", xy=(0.03, 0.13),
                        xycoords="axes fraction", fontsize=7,
                        color=S.CHANNEL_COLORS[ch])
    ax.axhline(0, color="#444444", linewidth=0.7, linestyle="--")
    ax.set_xlabel("候选尝试序号（各规模分别编号）")
    ax.set_ylabel("×5 情景最大损耗的改善量 (dB)")
    ax.set_title("(a) 候选尝试的情景增益与接受结果", fontsize=S.FONT_SIZE)
    S.style_axis(ax)
    ax.legend(loc="upper left", fontsize=6.5)

    ax2 = axes[1]
    reasons: dict[str, list[int]] = {}
    for ch in (256, 512):
        record = D.step14_optimize_record(ch)["opt_base"]
        for reason, count in record["rejected"].items():
            reasons.setdefault(reason, [0, 0])[0 if ch == 256 else 1] += count
    keys = sorted(reasons, key=lambda k: -(reasons[k][0] + reasons[k][1]))[:10]
    reason_names = {
        "scenario_not_improved": "情景无改善",
        "max_worse": "全局最大劣化",
        "mean_budget_exceeded": "均值预算超限",
    }
    ypos = np.arange(len(keys))[::-1]
    for ch, offset in ((256, 0.19), (512, -0.19)):
        vals = [reasons[k][0 if ch == 256 else 1] for k in keys]
        ax2.barh(ypos + offset, vals, height=0.36, color=S.CHANNEL_COLORS[ch],
                 label=S.CHANNEL_LABELS[ch])
    ax2.set_yticks(ypos)
    ax2.set_yticklabels([
        reason_names.get(k, k.replace("protected_worse_", "保护对象 #"))
        for k in keys
    ], fontsize=6.8)
    ax2.set_xlabel("拒绝次数（同一候选可命中多条原因，计数可叠加）", fontsize=7.5)
    ax2.set_title("(b) 拒绝原因分布（Top 10）", fontsize=S.FONT_SIZE)
    S.style_axis(ax2, grid_axis="x")
    ax2.legend(loc="lower right", fontsize=6.8)
    fig.tight_layout(w_pad=0.8)
    S.save_figure(
        fig, "f75_step14_optimize_process",
        note="opt_base 保护性局部优化：512 接受 6 个候选、256 接受 0 个；保护对象（#34 等）劣化与情景无改善是主要拒绝原因。",
        sources=[
            "outputs/opt2d_step14/{256,512}/optimize_attempts_base.csv",
            "outputs/opt2d_step14/{256,512}/optimize_record.json",
        ],
    )


def fig_probe() -> None:
    """F7-6：诊断探针变体（放宽保护余量/加严排序）与严格口径的对照。"""
    fig, ax = S.single_axes("full_short")
    variants = []
    for ch in (256, 512):
        frame = D.step14_probe_summary(ch)
        for _, row in frame.iterrows():
            variants.append((ch, row))
    labels = [f"{row['variant']}（{ch}）" for ch, row in variants]
    ypos = np.arange(len(variants))[::-1]
    for y, (ch, row) in zip(ypos, variants):
        color = S.CHANNEL_COLORS[ch]
        ax.scatter([row["scenario_gain_db"]], [y], s=30, color=color, zorder=3, linewidths=0)
        ax.annotate(f"接受 {int(row['accepted'])}/{int(row['candidates_tried'])}",
                    (row["scenario_gain_db"], y), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=7)
    ax.axvline(0, color="#444444", linewidth=0.8)
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("×5 情景最大损耗改善量 (dB)")
    ax.set_xlim(-0.002, 0.102)
    S.style_axis(ax, grid_axis="x")
    ax.annotate("诊断口径：放宽保护余量或加严候选排序，\n非任务口径；其中 strict_slack001 在 512 上接受 5 次",
                xy=(0.99, 0.62), xycoords="axes fraction", ha="right", fontsize=6.8,
                color="#666666")
    S.save_figure(
        fig, "f76_step14_probe_variants",
        note="opt_base 诊断探针：rank_small*（加严排序）在严格保护下 0–5 次接受，strict_slack*（放宽保护余量）可接受更多候选。",
        sources=["outputs/opt2d_step14/{256,512}/probe/probe_summary.csv"],
    )


def fig_sensitivity() -> None:
    """F7-7：×1/×2/×5/×10 压力情景的最大损耗（六配置）。"""
    factors = [1, 2, 5, 10]
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 3.1))
    for ax, ch in zip(axes, (256, 512)):
        frame = D.step14_sensitivity(ch)
        for scheme in SCHEMES:
            sub = frame[frame["scheme"] == scheme].set_index("factor")
            ys = [sub.loc[f, "max_loss_db"] for f in factors]
            style = S.method(scheme)
            ax.plot(factors, ys, color=style.color, marker=style.marker,
                    linewidth=S.LINE_WIDTH, markersize=3.4,
                    linestyle="--" if scheme == "touch" else "-", label=style.display)
        # 关键标注：base 与 opt_base 在 ×10 的对照
        base10 = frame[(frame["scheme"] == "base") & (frame["factor"] == 10)]["max_loss_db"].iloc[0]
        opt10 = frame[(frame["scheme"] == "opt_base") & (frame["factor"] == 10)]["max_loss_db"].iloc[0]
        diff = opt10 - base10
        if abs(diff) < 1e-9:
            direction = "与 base 相同"
        elif diff < 0:
            direction = "下降"
        else:
            direction = "略升"
        ax.annotate(f"×10：base {base10:.4f} → opt_base {opt10:.4f}\n（{direction} {abs(diff):.4f} dB）",
                    xy=(0.98, 0.04), xycoords="axes fraction", ha="right", va="bottom",
                    fontsize=6.8, color=S.method("opt_base").color,
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.88,
                              edgecolor="none"))
        ax.set_xticks(factors)
        ax.set_xticklabels([f"×{f}" for f in factors])
        ax.set_xlabel("交叉损耗放大倍数（<20° 区间）")
        ax.set_ylabel("最大逐路损耗 (dB)")
        ax.set_title(f"({'ab'[axes.tolist().index(ax)]}) {ch} 通道", fontsize=S.FONT_SIZE)
        S.style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False,
               bbox_to_anchor=(0.5, -0.14), fontsize=6.6)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f77_step14_sensitivity",
        note="Step 14 压力情景（固定几何、仅放大 <20° 交叉损耗）：512 的 opt_base 在 ×10 由 8.4333 升至 8.4996 dB（略恶化），×1–×5 下降；256 的 opt_base 与 base 相同（0 接受）。",
        sources=["outputs/opt2d_step14/{256,512}/sensitivity.csv"],
    )


ALL = [fig_main, fig_scenario, fig_small_angle, fig_protection, fig_optimize, fig_probe, fig_sensitivity]


def generate() -> None:
    for func in ALL:
        func()
        print(f"  [Step 14] {func.__name__} 完成", flush=True)
