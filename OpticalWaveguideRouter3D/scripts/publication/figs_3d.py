"""三维实验图（Step 9/10/11）。

覆盖：小规模顺序层分配（9-E）、两层对照 vs 三层（9-F）、固定 1024
三层布线与运行分解（Step 10）、以及基于终态几何重绘的 XY 投影、
XZ 侧视与三维总览。

严格边界（与 3d_waveguide_literature_physics_audit_v01.md 一致）：
* 全部指标都是几何/算法指标（中心线 clearance 碰撞对、抬层次数、
  transition 数、几何长度、层使用、运行时间）；
* 没有任何光学损耗数值，图上不出现 dB；
* 204291→138113 表述为"自定义近距 pair 计数下降"，不是制造违规或光学风险。
"""

from __future__ import annotations

from math import cos, pi, sin

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch

import pubdata as D
import pubstyle as S

# 层配色（与 step_11 一致，但换成发布版色板）
LAYER_COLORS = {0: "#9AA5B1", 1: S.PALETTE["blue"], 2: S.PALETTE["vermillion"]}
LAYER_LABELS = {0: "层 0（z=0）", 1: "层 1（z=1 mm）", 2: "层 2（z=2 mm）"}
TRANSITION_COLOR = S.PALETTE["reddish_purple"]


# ---------------------------------------------------------------------------
# 终态几何采样（只读，纯解析）
# ---------------------------------------------------------------------------


def sample_primitive(primitive: dict) -> np.ndarray:
    kind = primitive["type"]
    g = primitive["geometry"]
    if kind == "LineSegment3D":
        return np.array([[g["start"]["x"], g["start"]["y"], g["start"]["z"]],
                         [g["end"]["x"], g["end"]["y"], g["end"]["z"]]])
    if kind == "PlanarArcSegment3D":
        radius = g["radius"]
        cx, cy, z = g["center_x"], g["center_y"], g["z"]
        a0, sweep = g["start_angle"], g["sweep_angle"]
        n = max(8, min(65, int(abs(sweep) / (pi / 64)) + 1))
        angles = a0 + sweep * np.linspace(0, 1, n)
        return np.column_stack([cx + radius * np.cos(angles), cy + radius * np.sin(angles),
                                np.full(n, z)])
    if kind == "CosineTransition3D":
        start, end = g["start"], g["end"]
        n = 25
        t = np.linspace(0, 1, n)
        x = start["x"] + (end["x"] - start["x"]) * t
        y = start["y"] + (end["y"] - start["y"]) * t
        z = start["z"] + (end["z"] - start["z"]) * (1 - np.cos(pi * t)) / 2
        return np.column_stack([x, y, z])
    raise ValueError(kind)


def collect_segments():
    """返回 [(layer_key, points)]；layer_key ∈ {0,1,2,'transition'}。"""
    data = D.step10_final_state()
    items = []
    for route in data["routes"]:
        for primitive in route["geometry"]["primitives"]:
            pts = sample_primitive(primitive)
            if primitive["type"] == "CosineTransition3D":
                items.append(("transition", pts))
            else:
                items.append((int(round(pts[0, 2])), pts))
    return data, items


# ---------------------------------------------------------------------------
# F8-0：9-D 单路线抬层探针
# ---------------------------------------------------------------------------


def fig_probe_9d() -> None:
    summary = D.step9d_probe_summary()
    validation = D.step9d_local_validation()
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.9),
                             gridspec_kw={"width_ratios": [1.0, 1.1]})
    ax = axes[0]
    labels = [" / ".join(str(v) for v in item["target_pair"]) for item in validation]
    old = [item["old_collision_count"] for item in validation]
    new = [item["new_collision_count"] for item in validation]
    x = np.arange(len(labels))
    ax.bar(x - 0.17, old, 0.32, color="#BBBBBB", edgecolor="white", linewidth=0.5,
           label="抬层前（该路线）")
    ax.bar(x + 0.17, new, 0.32, color=S.method("step9e").color, edgecolor="white",
           linewidth=0.5, label="抬层后（该路线）")
    for xi, (o, n) in enumerate(zip(old, new)):
        ax.annotate(f"{o}", (xi - 0.17, o), xytext=(0, 2), textcoords="offset points",
                    ha="center", fontsize=7)
        ax.annotate(f"{n}", (xi + 0.17, n), xytext=(0, 2), textcoords="offset points",
                    ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels([f"路线对 {l}" for l in labels], fontsize=7.5)
    ax.set_ylabel("碰撞邻居数（共 511 个邻居）")
    ax.set_ylim(0, max(old) * 1.38)
    S.style_axis(ax)
    ax.legend(loc="upper center", fontsize=7, ncol=2)
    ax.set_title("(a) 单路线抬层的前后碰撞数", fontsize=S.FONT_SIZE)

    ax2 = axes[1]
    transitions = []
    for item in validation:
        counter = {"COLLISION→CLEAR": 0, "保持不变": 0, "其他": 0}
        for row in item["pair_results"]:
            if row["before_status"] == "COLLISION" and row["after_status"] == "CLEAR":
                counter["COLLISION→CLEAR"] += 1
            elif row["before_status"] == row["after_status"]:
                counter["保持不变"] += 1
            else:
                counter["其他"] += 1
        transitions.append(counter)
    keys = ["COLLISION→CLEAR", "保持不变", "其他"]
    colors = [S.PALETTE["green"], "#CCCCCC", S.PALETTE["orange"]]
    left = np.zeros(len(validation))
    for key, color in zip(keys, colors):
        values = np.array([t[key] for t in transitions])
        ax2.barh(np.arange(len(validation)), values, left=left, height=0.5,
                 color=color, edgecolor="white", linewidth=0.5, label=key)
        left += values
    for yi, item in enumerate(validation):
        ax2.annotate(f"新建碰撞 {len(item['new_collisions_created'])}，"
                     f"消除 {len(item['old_collisions_removed'])}",
                     (0, yi), xytext=(6, 0), textcoords="offset points", va="center",
                     fontsize=7, color="#333333")
    ax2.set_yticks(np.arange(len(validation)))
    ax2.set_yticklabels([f"路线对 {l}" for l in labels], fontsize=7.5)
    ax2.set_xlabel("邻居数（每组校验全部 511 个邻居）")
    ax2.set_xlim(0, 560)
    S.style_axis(ax2, grid_axis="x")
    ax2.legend(loc="upper right", fontsize=7, frameon=True, facecolor="white",
               framealpha=0.92, edgecolor="#CCCCCC")
    ax2.set_title("(b) 邻居对状态变化（零新建碰撞）", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f80_3d_probe_9d",
        note="9-D 单路线抬层探针：3 组真实路线对分别抬层，逐组校验 511 个邻居，零新建碰撞；总运行 %.1f s。" % summary["total_seconds"],
        sources=["outputs/step_9_d_probe_summary.json", "outputs/step_9_d_local_validation.json"],
    )


# ---------------------------------------------------------------------------
# F8-1：层分配（9-E / 9-F）与碰撞对减少
# ---------------------------------------------------------------------------


def fig_layer_assignment() -> None:
    nine_e = D.step9e_summary()
    two = D.step9f_two_layer_summary()
    three = D.step9f_three_layer_summary()

    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 2.9),
                             gridspec_kw={"width_ratios": [1.15, 1.0]})
    ax = axes[0]
    rows = [
        ("9-E 两层（30 目标）", {0: 500, 1: 12, 2: 0}),
        ("9-F 两层（50 目标）", {0: 496, 1: 16, 2: 0}),
        ("9-F 三层（50 目标）", {0: 490, 1: 14, 2: 8}),
    ]
    ypos = np.arange(len(rows))[::-1]
    for y, (label, usage) in zip(ypos, rows):
        left = 0
        for layer in (0, 1, 2):
            count = usage[layer]
            if count == 0:
                continue
            ax.barh(y, count, left=left, height=0.62, color=LAYER_COLORS[layer],
                    edgecolor="white", linewidth=0.5)
            if layer == 0:
                ax.annotate(f"{count}", (left + count / 2, y), ha="center", va="center",
                            fontsize=7.5, color="#333333")
            else:
                offset = 6 if layer == 1 else 20
                ax.annotate(f"{count}", (left + count + offset, y), ha="left", va="center",
                            fontsize=7.5, color=LAYER_COLORS[layer])
            left += count
    ax.set_yticks(ypos)
    ax.set_yticklabels([r[0] for r in rows], fontsize=S.FONT_SIZE_SMALL)
    ax.set_xlabel("路线数（512 条 2D 路线）")
    ax.set_xlim(0, 545)
    ax.set_ylim(-0.95, 2.55)
    S.style_axis(ax, grid_axis="x")
    ax.legend(handles=[Line2D([0], [0], color=LAYER_COLORS[l], lw=6, label=LAYER_LABELS[l])
                       for l in (0, 1, 2)], loc="lower center", bbox_to_anchor=(0.5, 0.0),
              fontsize=7, ncol=3)
    ax.set_title("(a) 层使用（同一 512 布局）", fontsize=S.FONT_SIZE)

    ax2 = axes[1]
    cases = [("9-E 两层", nine_e), ("9-F 两层", two), ("9-F 三层", three)]
    initial = nine_e["initial_collision_pair_count"]
    for index, (label, summary) in enumerate(cases):
        ax2.plot([initial], [index], "o", color="#888888", markersize=5, linestyle="none",
                 label="初始碰撞对" if index == 0 else None)
        ax2.plot([summary["final_collision_pair_count"]], [index], "o",
                 color=S.method("step9f3" if index == 2 else "step9f2").color,
                 markersize=5, linestyle="none",
                 label="最终碰撞对" if index == 0 else None)
        ax2.plot([initial, summary["final_collision_pair_count"]], [index, index],
                 color="#BBBBBB", linewidth=1.0, zorder=0)
        ax2.annotate(f"−{summary['reduction_percent']:.2f}%",
                     (summary["final_collision_pair_count"], index), xytext=(-8, 6),
                     textcoords="offset points", ha="right", fontsize=7.5,
                     color=S.method("step9f3" if index == 2 else "step9f2").color)
    ax2.set_yticks(range(len(cases)))
    ax2.set_yticklabels([c[0] for c in cases], fontsize=S.FONT_SIZE_SMALL)
    ax2.set_xlabel("中心线近距 pair 数（<0.1 mm）")
    ax2.set_xlim(44000, 51000)
    S.style_axis(ax2, grid_axis="x")
    ax2.legend(loc="upper right", fontsize=7, frameon=True, facecolor="white",
               framealpha=0.92, edgecolor="#CCCCCC")
    ax2.set_title("(b) 近距 pair 净减少", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=1.2)
    S.save_figure(
        fig, "f81_3d_layer_assignment",
        note="三维层分配（9-E/9-F，同一 512 布局）：层使用分布与中心线近距 pair 净减少；几何指标，与光学损耗无关。",
        sources=[
            "outputs/step_9_e_sequential_elevation_summary.json",
            "outputs/step_9_f_two_layer_control_summary.json",
            "outputs/step_9_f_three_layer_summary.json",
        ],
    )


# ---------------------------------------------------------------------------
# F8-2：两层 vs 三层对照（9-F）
# ---------------------------------------------------------------------------


def fig_two_vs_three() -> None:
    two = D.step9f_two_layer_summary()
    three = D.step9f_three_layer_summary()
    metrics = [
        ("final_collision_pair_count", "最终近距 pair 数"),
        ("total_extra_length_mm", "额外几何长度 (mm)"),
        ("runtime_seconds", "运行时间 (s)"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(S.FULL_WIDTH, 2.7))
    for index, (ax, (field, label)) in enumerate(zip(axes, metrics)):
        values = [two[field], three[field]]
        bars = ax.bar(["两层", "三层"], values, width=0.5,
                      color=[S.method("step9f2").color, S.method("step9f3").color],
                      edgecolor="white", linewidth=0.5)
        for rect, value in zip(bars, values):
            ax.annotate(f"{value:,.1f}" if field != "runtime_seconds" else f"{value:.1f}",
                        (rect.get_x() + rect.get_width() / 2, value), xytext=(0, 2),
                        textcoords="offset points", ha="center", fontsize=7.5)
        ax.set_ylabel(label)
        ax.set_title(f"({'abc'[index]}) {label.split(' ')[0]}", fontsize=S.FONT_SIZE)
        S.style_axis(ax)
    fig.tight_layout(w_pad=0.9)
    S.save_figure(
        fig, "f82_3d_two_vs_three",
        note="9-F 同一 512 布局、各 50 次 attempt 的两层 vs 三层对照：三层近距 pair 更低，代价是更多额外长度与运行时间。",
        sources=[
            "outputs/step_9_f_two_layer_control_summary.json",
            "outputs/step_9_f_three_layer_summary.json",
        ],
    )


# ---------------------------------------------------------------------------
# F8-3：固定 1024（Step 10）
# ---------------------------------------------------------------------------


def fig_fixed_1024() -> None:
    summary = D.step10_summary()
    runtime = summary["runtime"]
    fig, axes = plt.subplots(1, 3, figsize=(S.FULL_WIDTH, 2.9),
                             gridspec_kw={"width_ratios": [0.9, 1.0, 1.15]})
    ax = axes[0]
    initial = summary["initial_collision_pairs"]
    final = summary["final_collision_pairs"]
    ax.plot([0, 1], [initial, final], color=S.method("step10").color, marker="o",
            markersize=4.5, linewidth=1.2)
    ax.annotate(f"{initial:,}", (0, initial), xytext=(6, 6), textcoords="offset points",
                fontsize=7.5)
    ax.annotate(f"{final:,}", (1, final), xytext=(-6, -12), textcoords="offset points",
                ha="right", fontsize=7.5)
    ax.annotate(f"净减少 {summary['net_collision_reduction']:,}（{summary['reduction_percent']:.2f}%）",
                xy=(0.52, 0.50), xycoords="axes fraction", ha="center", va="center",
                fontsize=7.5, color=S.method("step10").color,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.88,
                          edgecolor="none"))
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["优化前", "优化后"])
    ax.set_xlim(-0.35, 1.35)
    ax.set_ylim(0, initial * 1.16)
    ax.set_ylabel("近距 pair 数（<0.1 mm 中心线）")
    S.style_axis(ax)
    ax.set_title("(a) 1024 通道近距 pair", fontsize=S.FONT_SIZE)

    ax2 = axes[1]
    counts = summary["layer_route_counts"]
    x = np.arange(3)
    bars = ax2.bar(x, [counts["0"], counts["1"], counts["2"]], width=0.55,
                   color=[LAYER_COLORS[0], LAYER_COLORS[1], LAYER_COLORS[2]],
                   edgecolor="white", linewidth=0.5)
    for rect, layer in zip(bars, (0, 1, 2)):
        ax2.annotate(f"{counts[str(layer)]}", (rect.get_x() + rect.get_width() / 2,
                     counts[str(layer)]), xytext=(0, 2), textcoords="offset points",
                     ha="center", fontsize=7.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(["层 0", "层 1", "层 2"])
    ax2.set_ylabel("路线数（共 1024）")
    ax2.set_ylim(0, 970)
    S.style_axis(ax2)
    ax2.set_title("(b) 终态层使用", fontsize=S.FONT_SIZE)

    ax3 = axes[2]
    parts = [
        ("数据集几何", runtime["dataset_geometry_seconds"]),
        ("初始配对扫描", runtime["initial_pair_scan_seconds"]),
        ("层分配", runtime["assignment_seconds"]),
        ("终态校验", runtime["final_validation_seconds"]),
    ]
    left = 0.0
    colors = ["#9AA5B1", S.PALETTE["yellow"], S.method("step10").color, S.PALETTE["green"]]
    for (label, value), color in zip(parts, colors):
        ax3.barh(0, value, left=left, height=0.5, color=color, edgecolor="white", linewidth=0.5,
                 label=f"{label}（{value:.1f} s）")
        left += value
    ax3.annotate(f"总运行 {runtime['total_seconds']:.1f} s\n（约 19.5 分钟）",
                 xy=(0.98, 0.82), xycoords="axes fraction", ha="right", fontsize=7,
                 color="#555555")
    ax3.set_yticks([])
    ax3.set_xlabel("运行时间 (s)")
    ax3.set_xlim(0, left * 1.06)
    S.style_axis(ax3, grid_axis="x")
    ax3.legend(loc="center right", fontsize=6.6, frameon=True, facecolor="white",
               framealpha=0.92, edgecolor="#CCCCCC")
    ax3.set_title("(c) 运行时间分解", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f83_3d_fixed_1024",
        note="固定 1024 通道三层布线（合成实例，300×200 mm）：近距 pair 204291→138113（−32.39%）、终态层使用 849/72/103、运行 1172.7 s。",
        sources=["outputs/step_10_fixed_1024_summary.json、step_10_fixed_1024_initial_stats.json"],
    )


# ---------------------------------------------------------------------------
# F8-4 / F8-5：XY 投影与 XZ 侧视（由终态几何重绘）
# ---------------------------------------------------------------------------


def fig_xy_projection() -> None:
    data, items = collect_segments()
    fig, ax = S.single_axes((S.FULL_WIDTH, 4.1))
    for layer in (0, 1, 2):
        segments = [pts[:, :2] for key, pts in items if key == layer]
        ax.add_collection(LineCollection(
            segments, colors=LAYER_COLORS[layer],
            linewidths=0.22 if layer == 0 else 0.5,
            alpha=0.30 if layer == 0 else 0.85))
    transitions = [pts[:, :2] for key, pts in items if key == "transition"]
    ax.add_collection(LineCollection(transitions, colors=TRANSITION_COLOR, linewidths=0.5,
                                     alpha=0.9, linestyles="dotted"))
    # 板框与端点
    board = data["board"]
    ax.plot([0, board["width_mm"], board["width_mm"], 0, 0],
            [0, 0, board["height_mm"], board["height_mm"], 0],
            color="#333333", linewidth=0.7)
    endpoints = np.array([[r[key]["xyz"][0], r[key]["xyz"][1]]
                          for r in data["routes"] for key in ("source", "destination")])
    ax.scatter(endpoints[:, 0], endpoints[:, 1], s=1.6, color="#333333", alpha=0.5, linewidths=0)
    ax.set_xlim(-6, board["width_mm"] + 6)
    ax.set_ylim(-8, board["height_mm"] + 8)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.legend(handles=[Line2D([0], [0], color=LAYER_COLORS[l], lw=2.2, label=LAYER_LABELS[l])
                       for l in (0, 1, 2)] +
                      [Line2D([0], [0], color=TRANSITION_COLOR, lw=2.2, linestyle=":",
                              label="抬层过渡（余弦）")],
              loc="upper center", ncol=4, fontsize=7, bbox_to_anchor=(0.5, -0.06))
    S.save_figure(
        fig, "f84_3d_xy_projection",
        note="固定 1024 通道终态的 XY 投影（按层着色，含层间抬层过渡的投影迹）：抬层只改 z，不改 XY 平面几何。",
        sources=["outputs/step_10_fixed_1024_final_route_state.json（只读重绘）"],
    )


def fig_xz_side() -> None:
    data, items = collect_segments()
    fig, axes = plt.subplots(1, 2, figsize=(S.FULL_WIDTH, 3.2),
                             gridspec_kw={"width_ratios": [1.5, 1.0]})
    ax = axes[0]
    for key in (0, 1, 2):
        segments = [pts[:, [0, 2]] for ker, pts in items if ker == key]
        ax.add_collection(LineCollection(
            segments, colors=LAYER_COLORS[key], linewidths=0.2 if key == 0 else 0.5,
            alpha=0.18 if key == 0 else 0.85))
    transitions = [pts[:, [0, 2]] for ker, pts in items if ker == "transition"]
    ax.add_collection(LineCollection(transitions, colors=TRANSITION_COLOR, linewidths=0.6,
                                     alpha=0.9))
    ax.set_xlim(0, data["board"]["width_mm"])
    ax.set_ylim(-0.15, 2.35)
    ax.set_yticks([0, 1, 2])
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("z (mm)")
    S.style_axis(ax, grid_axis="x")
    ax.annotate("过渡段集中于少数路线（175 次抬层、350 个过渡）",
                xy=(0.5, 0.93), xycoords="axes fraction", ha="center", fontsize=7,
                color="#555555")
    ax.set_title("(a) XZ 侧视（1024 通道全体投影）", fontsize=S.FONT_SIZE)

    # 示例路线（与 step_11 相同规则）：层 1 = #153、层 2 = #152
    ax2 = axes[1]
    for rid, color, label in ((153, LAYER_COLORS[1], "路径 #153（抬至层 1）"),
                              (152, LAYER_COLORS[2], "路径 #152（抬至层 2）")):
        route = next(r for r in data["routes"] if r["route_id"] == rid)
        pts_all = np.vstack([sample_primitive(p) for p in route["geometry"]["primitives"]])
        # 以过渡段中点为中心取局部
        trans = np.vstack([sample_primitive(p) for p in route["geometry"]["primitives"]
                           if p["type"] == "CosineTransition3D"])
        center = trans[:, 0].mean()
        mask = np.abs(pts_all[:, 0] - center) <= 22
        ax2.plot(np.arange(mask.sum()), pts_all[mask, 2], color=color, linewidth=1.4,
                 label=label)
    ax2.set_xlabel("沿路线采样序号（±22 mm 窗口）")
    ax2.set_ylabel("z (mm)")
    ax2.set_yticks([0, 1, 2])
    ax2.set_ylim(-0.15, 2.35)
    S.style_axis(ax2)
    ax2.legend(loc="upper left", fontsize=7)
    ax2.set_title("(b) 抬层示例侧视", fontsize=S.FONT_SIZE)
    fig.tight_layout(w_pad=1.0)
    S.save_figure(
        fig, "f85_3d_xz_side",
        note="1024 通道终态的 XZ 侧视与抬层示例（#153→层 1、#152→层 2）；终点层段与两段余弦过渡在几何上连续（C0/C1 校验通过）。",
        sources=["outputs/step_10_fixed_1024_final_route_state.json（只读重绘）",
                 "outputs/step_11_visualization_summary.json（示例选择规则）"],
    )


def fig_3d_overview() -> None:
    data, items = collect_segments()
    fig = plt.figure(figsize=(S.FULL_WIDTH, 3.3))
    ax = fig.add_subplot(projection="3d")
    # 低采样：每段最多取少量点，控制文件与渲染规模
    for key in (0, 1, 2):
        for ker, pts in items:
            if ker != key:
                continue
            if len(pts) > 5:
                pts = pts[:: max(1, len(pts) // 3)]
            ax.plot(pts[:, 0], pts[:, 1], pts[:, 2] * 20,
                    color=LAYER_COLORS[key], linewidth=0.25 if key == 0 else 0.6,
                    alpha=0.22 if key == 0 else 0.8)
    transitions = [pts for ker, pts in items if ker == "transition"]
    for pts in transitions[::3]:
        ax.plot(pts[:, 0], pts[:, 1], pts[:, 2] * 20, color=TRANSITION_COLOR,
                linewidth=0.7, alpha=0.9)
    board = data["board"]
    bx = [0, board["width_mm"], board["width_mm"], 0, 0]
    by = [0, 0, board["height_mm"], board["height_mm"], 0]
    ax.plot(bx, by, [0] * 5, color="#333333", linewidth=0.7)
    ax.set_xlim(0, board["width_mm"])
    ax.set_ylim(0, board["height_mm"])
    ax.set_zlim(0, 40)
    ax.set_zticks([0, 20, 40])
    ax.set_zticklabels(["0", "1", "2"])
    ax.set_xlabel("x (mm)", labelpad=-4)
    ax.set_ylabel("y (mm)", labelpad=-4)
    ax.set_zlabel("z (mm)", labelpad=-6)
    ax.view_init(elev=30, azim=-56)
    ax.set_box_aspect((300, 200, 34))
    ax.grid(False)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.fill = False
        axis.pane.set_edgecolor("white")
    S.save_figure(
        fig, "f86_3d_overview",
        note="固定 1024 通道三层布线三维总览（z 为显示放大 ×20，真实层 0/1/2 mm）；全部为几何视图，未计算光学损耗。",
        sources=["outputs/step_10_fixed_1024_final_route_state.json（只读重绘）"],
    )


ALL = [fig_probe_9d, fig_layer_assignment, fig_two_vs_three, fig_fixed_1024,
       fig_xy_projection, fig_xz_side, fig_3d_overview]


def generate() -> None:
    for func in ALL:
        func()
        print(f"  [三维] {func.__name__} 完成", flush=True)
