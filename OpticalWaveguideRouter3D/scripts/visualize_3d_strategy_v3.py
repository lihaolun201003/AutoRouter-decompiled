# -*- coding: utf-8 -*-
"""v3 四组功能消融主实验与真实路线几何绘图（专题报告与总报告各自编号的共用图）。

只读脚本：所有数值一律从已有真实产物 JSON 读取，不做任何路由计算、不修改任何输入。
用法::

    .venv\Scripts\python.exe -B scripts/visualize_3d_strategy_v3.py . outputs/3d_strategy_v3/figures

输出 PNG(300 dpi) + PDF 到 outputs/3d_strategy_v3/figures/，并写 figures_manifest.json，
记录每张图的输入文件绝对路径与 sha256、所选路线 ID、Z 轴放大倍数、排版自检结果。

命名提示：本脚本中的组字母 A/B/C/D 是**本轮功能消融**分组
（A 基线原版 / B 仅结构化生成缓存 / C 仅窗口松弛 / D 两者同时启用），
与历史策略字母 A/B/C 不是同一命名体系。所有图与图注均写明这一点。

排版自检：保存前会检查（1）是否存在缺字（宋体缺 U+2212，出现即为方框）、
（2）是否有文本越出画布、（3）图级注释是否与其它文本重叠；越界会直接报错终止。
"""
from __future__ import annotations

import hashlib
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection  # noqa: E402

sys.dont_write_bytecode = True

# --------------------------------------------------------------------------
# 常量（路径常量集中在此，便于 manifest 记录）
# --------------------------------------------------------------------------

SIMSUN_PATH = Path("C:/Windows/Fonts/simsun.ttc")
ABLATION_DIR = "outputs/3d_strategy_v3/512_ablation"
CROSS_GROUP = "outputs/3d_strategy_v3/512_ablation/cross_group_analysis.json"
LEGACY_PLOT_GEOMETRY = "outputs/step_8_5_legacy_512_plot_geometry.json"
FINAL_ROUTES = "outputs/3d_strategy_v3/512_ablation/D_both_enabled/final_routes.json"
Z_EXAGGERATION = 20  # 图 6(d) 的 Z 轴显示放大倍数

GROUPS = [
    ("A", "A_baseline_original", "基线原版"),
    ("B", "B_generation_cache_only", "仅结构化生成缓存"),
    ("C", "C_window_slack_only", "仅窗口松弛"),
    ("D", "D_both_enabled", "两者同时启用"),
]
GROUP_COLORS = {"A": "#4D4D4D", "B": "#0072B2", "C": "#E69F00", "D": "#D55E00"}
GROUP_STYLES = {"A": "-", "B": "--", "C": "-.", "D": (0, (1.2, 1.2))}
LAYER_COLORS = {0: "#87929c", 1: "#0072B2", 2: "#D55E00", "transition": "#713d88"}
LAYER_LABELS = {0: "层 0（z = 0 mm）", 1: "层 1（z = 1 mm）", 2: "层 2（z = 2 mm）",
                "transition": "余弦过渡段"}
REFERENCE_COLOR = "#8C8C8C"

# 任务描述中给出的期望值：只用于交叉校验与留痕，绝不参与绘图（绘图值全部来自 JSON）。
EXPECTED = {
    "initial_collision_pair_count": 49518,
    "final_collision_pair_count": {"A": 44274, "B": 43750, "C": 43161, "D": 42909},
    "reduction_percent": {"A": 10.59, "B": 11.65, "C": 12.84, "D": 13.35},
    "final_extra_length_mm": {"A": 8.405220, "B": 8.893004, "C": 6.912199, "D": 7.156091},
    "runtime_seconds": {"A": 199.7, "B": 209.8, "C": 374.7, "D": 373.4},
    "candidate_evaluations": {"A": 666, "B": 720, "C": 711, "D": 720},
}

SELFTEST_NOTES: list = []

# --------------------------------------------------------------------------
# 文本排版工具（中文按整字宽计，ASCII 按半宽计，保证不越界、不叠字）
# --------------------------------------------------------------------------


def display_width(text: str, ascii_ratio: float = 0.55) -> float:
    return sum(1.0 if ord(ch) > 0x2000 else ascii_ratio for ch in text)


def wrap_text(text: str, max_cols: float, ascii_ratio: float = 0.55) -> list:
    """按显示宽度折行；ASCII 连续片段（路径、变量名）尽量不拆开。"""
    tokens, buf = [], ""
    for ch in text:
        if ord(ch) > 0x2000 or ch == " ":
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    lines, current, width = [], "", 0.0
    for token in tokens:
        token_width = display_width(token, ascii_ratio)
        if current and width + token_width > max_cols:
            lines.append(current.rstrip())
            current, width = "", 0.0
        if token == " " and not current:
            continue
        current += token
        width += token_width
    if current.strip():
        lines.append(current.rstrip())
    return lines


def wrap_paragraph(text: str, fig_width_in: float, fontsize: float, margin: float = 0.93) -> list:
    max_cols = max(20.0, margin * fig_width_in * 72.0 / fontsize)
    out = []
    for chunk in text.split("\n"):
        out.extend(wrap_text(chunk, max_cols))
    return out


def note_band_top(bottom: float, offset: float = 0.062) -> float:
    return bottom - offset


def add_notes(fig, lines, x: float, top: float, fontsize: float = 9.0,
              color: str = "#333333", line_factor: float = 1.95) -> float:
    """在画布坐标里逐行写图注，返回最后一行的 y（行高由字号与画布高度决定）。"""
    fig_height = fig.get_size_inches()[1]
    step = fontsize * line_factor / (fig_height * 72.0)
    y = top
    for line in lines:
        fig.text(x, y, line, ha="left", va="top", fontsize=fontsize, color=color)
        y -= step
    return y


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def setup_fonts() -> str:
    """注册系统宋体并设为默认字体族；负号用 ASCII 连字符避免缺字。"""
    if not SIMSUN_PATH.exists():
        raise SystemExit("缺少中文字体：%s" % SIMSUN_PATH)
    fm.fontManager.addfont(str(SIMSUN_PATH))
    resolved = fm.findfont(fm.FontProperties(family="SimSun"))
    plt.rcParams.update({
        "font.family": ["SimSun"],
        "font.sans-serif": ["SimSun", "Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "font.serif": ["SimSun", "Times New Roman", "DejaVu Serif"],
        "axes.unicode_minus": False,          # 宋体缺 U+2212，必须用 ASCII 连字符
        "mathtext.fontset": "stix",
        "font.size": 10.5,
        "axes.titlesize": 12.0,
        "axes.labelsize": 11.0,
        "xtick.labelsize": 10.0,
        "ytick.labelsize": 10.0,
        "legend.fontsize": 9.5,
        "figure.dpi": 120,
        "savefig.dpi": 300,
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#333333",
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "grid.alpha": 0.22,
        "grid.linewidth": 0.5,
        "legend.frameon": False,
        "lines.linewidth": 1.6,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    return resolved


def check_no_unicode_minus(fig) -> None:
    """宋体缺 U+2212；任何文本里出现都会渲染成方框，这里直接失败。"""
    for obj in fig.findobj(matplotlib.text.Text):
        value = obj.get_text()
        if "\u2212" in value:
            raise SystemExit("文本含 U+2212 减号（宋体缺字）：%r" % value)


def layout_report(fig, tol: float = 0.004) -> dict:
    """越界检查（硬失败）+ 图级注释与其它文本的重叠检查（报告）。"""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width, height = fig.canvas.get_width_height()
    texts = [t for t in fig.findobj(matplotlib.text.Text) if t.get_text().strip()]
    figure_texts = [t for t in fig.texts if t.get_text().strip()]
    def owner(t):
        ax = getattr(t, "axes", None)
        if ax is None:
            return "figure"
        title = ax.get_title()
        return "%s | %s" % (type(ax).__name__, title[:34] if title else "(无标题)")

    figure_text_set = set(id(t) for t in figure_texts)
    outside = []
    skipped = []
    for t in texts:
        # 只检查真正属于本图的文本：图级注释 + 挂在某个 Axes 上的文本。
        # matplotlib 会为落在视窗外的刻度保留无主的 Text 对象（axes=None、不渲染），
        # 这类对象不参与越界判定，仅记录。
        if id(t) not in figure_text_set and getattr(t, "axes", None) is None:
            skipped.append(t.get_text()[:40])
            continue
        box = t.get_window_extent(renderer=renderer)
        if box.width <= 0 or box.height <= 0:
            continue
        if (box.x0 < -tol * width or box.x1 > width * (1 + tol)
                or box.y0 < -tol * height or box.y1 > height * (1 + tol)):
            outside.append(dict(text=t.get_text()[:70], owner=owner(t),
                                fontsize=round(t.get_fontsize(), 1),
                                bbox=[round(v, 1) for v in (box.x0, box.y0, box.x1, box.y1)],
                                canvas=[width, height]))
    # 带底框的注释（面板内的说明框）最容易压住别的文字，单独纳入重叠检查
    boxed = [t for t in texts if getattr(t, "axes", None) is not None
             and t.get_bbox_patch() is not None]
    overlaps = []
    for ft in list(figure_texts) + boxed:
        fbox = ft.get_window_extent(renderer=renderer)
        for t in texts:
            if t is ft:
                continue
            tbox = t.get_window_extent(renderer=renderer)
            if tbox.width <= 0 or tbox.height <= 0:
                continue
            if fbox.overlaps(tbox):
                ix = min(fbox.x1, tbox.x1) - max(fbox.x0, tbox.x0)
                iy = min(fbox.y1, tbox.y1) - max(fbox.y0, tbox.y0)
                if ix > 2 and iy > 2:
                    overlaps.append(dict(note=ft.get_text()[:45], other=t.get_text()[:45],
                                         overlap_px=[round(ix, 1), round(iy, 1)]))
    return dict(outside_canvas=outside, note_overlaps=overlaps,
                skipped_ownerless_texts=skipped)


def save_figure(fig, out_dir: Path, name: str, files: list, layout_log: list) -> None:
    check_no_unicode_minus(fig)
    report = layout_report(fig)
    report["figure"] = name
    layout_log.append(report)
    if report["outside_canvas"]:
        raise SystemExit("图 %s 有文本越出画布：%s" % (name, json.dumps(report["outside_canvas"],
                                                                  ensure_ascii=False)))
    for ext in ("png", "pdf"):
        target = out_dir / ("%s.%s" % (name, ext))
        fig.savefig(target, dpi=300)
        files.append(target)
    plt.close(fig)


def fmt_count(value) -> str:
    return "{:,.0f}".format(float(value))


# --------------------------------------------------------------------------
# 数据读取
# --------------------------------------------------------------------------


class GroupData:
    def __init__(self, root: Path, letter: str, folder: str, label: str):
        self.letter = letter
        self.folder = folder
        self.label = label
        base = root / ABLATION_DIR / folder
        self.ledger_path = base / "ledger.json"
        self.curve_path = base / "curve.json"
        self.ledger = load_json(self.ledger_path)
        self.curve = load_json(self.curve_path)
        self.evals = [int(p["candidate_evaluations"]) for p in self.curve]
        self.pairs = [int(p["collision_pair_count"]) for p in self.curve]
        self.cache_on = bool(self.ledger["generation_failure_cache_enabled"])
        self.slack_mm = float(self.ledger["window_slack_mm"])
        self.budget_percent = (float(self.ledger["candidate_evaluations"])
                               / float(self.ledger["candidate_budget"]) * 100.0)

    @property
    def flag_text(self) -> str:
        return "缓存%s / 松弛 %g mm" % ("开" if self.cache_on else "关", self.slack_mm)

    @property
    def flag_text_long(self) -> str:
        return "%s = %s，窗口松弛 %g mm" % (self.letter, "结构化生成缓存开" if self.cache_on
                                        else "结构化生成缓存关", self.slack_mm)


def load_groups(root: Path):
    return [GroupData(root, letter, folder, label) for letter, folder, label in GROUPS]


def cross_check(groups) -> list:
    """把读到的真实值与任务描述里的期望值逐项比对并留痕（不参与绘图）。"""
    records = []
    initial = {int(g.ledger["initial_collision_pair_count"]) for g in groups}
    records.append(dict(item="initial_collision_pair_count", source="ledger.json",
                        actual=sorted(initial),
                        expected=EXPECTED["initial_collision_pair_count"],
                        match=initial == {EXPECTED["initial_collision_pair_count"]}))
    tol_map = {
        "final_collision_pair_count": 0.0, "reduction_percent": 5e-3,
        "final_extra_length_mm": 5e-7, "runtime_seconds": 5e-2,
        "candidate_evaluations": 0.0,
    }
    for key, tol in tol_map.items():
        for g in groups:
            actual = float(g.ledger[key])
            expected = float(EXPECTED[key][g.letter])
            records.append(dict(item=key, group=g.letter, source="ledger.json",
                                actual=actual, expected=expected,
                                match=bool(abs(actual - expected) <= tol)))
    for rec in records:
        if not rec["match"]:
            SELFTEST_NOTES.append("期望值不一致：%s" % json.dumps(rec, ensure_ascii=False))
    return records


# --------------------------------------------------------------------------
# 图 1：四组终态近距对
# --------------------------------------------------------------------------


def figure_1(groups, out_dir: Path, files: list, layout_log: list, root: Path):
    letters = [g.letter for g in groups]
    values = [float(g.ledger["final_collision_pair_count"]) for g in groups]
    reductions = [float(g.ledger["net_collision_reduction"]) for g in groups]
    percents = [float(g.ledger["reduction_percent"]) for g in groups]
    initial = float(groups[0].ledger["initial_collision_pair_count"])
    cross_group_path = root / CROSS_GROUP
    metric = load_json(cross_group_path)["metric"]

    fig, ax = plt.subplots(figsize=(11.8, 7.9))
    bottom = 0.315
    fig.subplots_adjust(left=0.088, right=0.985, top=0.775, bottom=bottom)
    width_in = fig.get_size_inches()[0]
    xs = np.arange(len(groups))
    bars = ax.bar(xs, values, width=0.56, color=[GROUP_COLORS[g] for g in letters],
                  edgecolor="white", linewidth=0.8, zorder=3)
    ax.axhline(initial, color="#B2182B", linestyle="--", linewidth=1.5, zorder=2)
    ax.annotate("初态参考线：%s 对（四组共同起点）" % fmt_count(initial),
                xy=(0.55, initial), xytext=(0.55, initial + 700),
                color="#B2182B", fontsize=10.5, va="bottom",
                arrowprops=dict(arrowstyle="-", color="#B2182B", linewidth=0.9))

    for x, bar, value, red, pct, group in zip(xs, bars, values, reductions, percents, groups):
        top = bar.get_height()
        ax.text(x, top + 700, "减少 %s 对（-%.2f%%）" % (fmt_count(red), pct),
                ha="center", va="bottom", fontsize=10.8, color="#B2182B", zorder=4)
        # 数字放在柱内顶部：柱顶到初态参考线之间放不下两行文字
        ax.text(x, top - 900, "%s 对" % fmt_count(value), ha="center", va="top",
                fontsize=13.0, fontweight="bold", zorder=4,
                color="#222222" if group.letter == "C" else "white")

    ax.set_xticks(xs)
    ax.set_xticklabels(["%s %s\n%s" % (g.letter, g.label, g.flag_text) for g in groups],
                       fontsize=10.0)
    ax.set_ylabel("终态近距对数（0.1 mm 净距）")
    ax.set_ylim(0, initial * 1.175)
    ax.set_xlim(-0.62, len(groups) - 0.38)
    ax.grid(axis="y", alpha=0.22, zorder=0)
    ax.set_axisbelow(True)

    fig.text(0.088, 0.973, "v3 四组功能消融主实验：512 路线终态近距对及相对初态的减少量",
             fontsize=14.0, ha="left", va="top")
    y = add_notes(fig, wrap_paragraph(
        "组字母 A/B/C/D 是**本轮功能消融**分组（A 基线原版；B 仅结构化生成缓存；C 仅窗口松弛；"
        "D 两者同时启用），不是历史策略字母 A/B/C，两者不可按字母对应。".replace("**", ""),
        width_in, 10.2), 0.088, 0.922, fontsize=10.2, color="#B2182B")
    y = add_notes(fig, [
        "数据来源（只读）：%s/{A_baseline_original, B_generation_cache_only, C_window_slack_only,"
        % ABLATION_DIR,
        "D_both_enabled}/ledger.json；交叉核对 512_ablation/cross_group_analysis.json。",
        "图中柱值为 ledger.json 的 final_collision_pair_count，减少量/百分比为 net_collision_reduction 与 "
        "reduction_percent，虚线为四组共同初态 initial_collision_pair_count。",
        "指标口径（cross_group_analysis.json 的 metric）：%s" % metric,
        "实现对照：%s。" % "；".join(g.flag_text_long for g in groups),
        "每组仅运行 1 次（单次实测），此处只报告该次运行的确定性计数，不构成统计意义上的普遍结论。",
    ], 0.088, note_band_top(bottom, 0.055), fontsize=9.0)
    fig.text(0.088, y - 0.004, "每根柱上方红色数字即相对初态的减少量与减少百分比。",
             ha="left", va="top", fontsize=9.0, color="#666666")

    inputs = [g.ledger_path for g in groups] + [cross_group_path]
    name = "f1_group_pairs"
    save_figure(fig, out_dir, name, files, layout_log)
    return name, inputs


# --------------------------------------------------------------------------
# 图 2：近距对随实际候选评价次数变化
# --------------------------------------------------------------------------


def figure_2(groups, out_dir: Path, files: list, layout_log: list):
    fig, ax = plt.subplots(figsize=(11.9, 7.9))
    bottom = 0.335
    fig.subplots_adjust(left=0.086, right=0.975, top=0.785, bottom=bottom)
    width_in = fig.get_size_inches()[0]
    budget = float(groups[0].ledger["candidate_budget"])
    initial = float(groups[0].ledger["initial_collision_pair_count"])

    for g in groups:
        ax.step(g.evals, g.pairs, where="post", color=GROUP_COLORS[g.letter],
                linestyle=GROUP_STYLES[g.letter], linewidth=2.0,
                label="%s %s" % (g.letter, g.label), zorder=3)

    end_label_offset = {"A": 240, "B": 240, "C": 240, "D": -240}
    for g in groups:
        x_end, y_end = g.evals[-1], g.pairs[-1]
        ax.plot([x_end], [y_end], marker="o", markersize=6.5, color=GROUP_COLORS[g.letter],
                zorder=5, clip_on=False)
        ax.text(x_end - 11, y_end + end_label_offset[g.letter], g.letter, ha="right",
                va="bottom" if end_label_offset[g.letter] > 0 else "top",
                fontsize=11.5, fontweight="bold", color=GROUP_COLORS[g.letter], zorder=6)

    ax.axvline(budget, color="#B2182B", linestyle="--", linewidth=1.4, zorder=2)
    ax.text(budget - 10, 47930, "共同候选评价预算上限 %d 次" % int(budget),
            ha="right", va="center", fontsize=10.2, color="#B2182B")
    ax.axhline(initial, color="#999999", linestyle=":", linewidth=1.1, zorder=1)
    ax.text(210, initial + 150, "初态 %s 对" % fmt_count(initial), ha="center", va="bottom",
            fontsize=9.8, color="#666666")
    ax.set_xlim(-14, budget + 30)
    ax.set_ylim(42400, 50300)
    ax.set_xticks([0, 100, 200, 300, 400, 500, 600, 700])
    ax.set_xlabel("实际候选评价次数 candidate_evaluations（次）")
    ax.set_ylabel("近距对数 collision_pair_count（0.1 mm 净距）")
    ax.grid(alpha=0.22, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", frameon=True, framealpha=0.94, edgecolor="#DDDDDD")
    ax.text(0.985, 0.615,
            "终态对数与实际评价次数\n"
            + "\n".join("%s  %s 对，实际评价 %d 次" % (g.letter, fmt_count(g.pairs[-1]), g.evals[-1])
                        for g in groups),
            transform=ax.transAxes, ha="right", va="top", fontsize=9.0, color="#333333",
            linespacing=1.45,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#DDDDDD", alpha=0.95))
    ax.text(0.478, 0.035,
            "四组终态：A 44,274 对（666 次）｜B 43,750 对（720 次）｜\n"
            "C 43,161 对（711 次）｜D 42,909 对（720 次）".replace("44,274", fmt_count(groups[0].pairs[-1]))
            .replace("43,750", fmt_count(groups[1].pairs[-1]))
            .replace("43,161", fmt_count(groups[2].pairs[-1]))
            .replace("42,909", fmt_count(groups[3].pairs[-1])),
            transform=ax.transAxes, ha="left", va="bottom", fontsize=9.8, color="#333333")

    # 末端放大插图
    axin = ax.inset_axes([0.045, 0.075, 0.35, 0.33])
    for g in groups:
        xs = [x for x in g.evals if x >= 655]
        ys = [y for x, y in zip(g.evals, g.pairs) if x >= 655]
        axin.step(xs, ys, where="post", color=GROUP_COLORS[g.letter],
                  linestyle=GROUP_STYLES[g.letter], linewidth=1.6, zorder=3)
    axin.axvline(budget, color="#B2182B", linestyle="--", linewidth=1.0, zorder=2)
    axin.set_xlim(650, 730)
    axin.set_ylim(42650, 44800)
    axin.set_xticks([660, 680, 700, 720])
    axin.set_yticks([43000, 43500, 44000, 44500])
    axin.set_title("末端放大（650-730 次）", fontsize=9.5)
    axin.tick_params(labelsize=8.0)
    axin.grid(alpha=0.25)
    axin.set_axisbelow(True)

    # 重合区间由数据逐点比对得出，不手写
    overlap_lines = []
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            a, b = groups[i], groups[j]
            map_a, map_b = dict(zip(a.evals, a.pairs)), dict(zip(b.evals, b.pairs))
            common = [x for x in b.evals if x in map_a]
            if len(common) > 1 and all(map_a[x] == map_b[x] for x in common):
                overlap_lines.append("%s 与 %s 在 0-%d 次评价区间逐点数值相同"
                                     % (a.letter, b.letter, max(common)))

    fig.text(0.086, 0.973, "近距对数随实际候选评价次数变化（512 路线，四组功能消融）",
             fontsize=14.0, ha="left", va="top")
    add_notes(fig, wrap_paragraph(
        "共同上限 %d 次是候选评价预算上限；四组实际评价次数不同：%s。组字母 A/B/C/D 为本轮功能消融分组，"
        "不是历史策略字母 A/B/C。"
        % (int(budget), "、".join("%s %d 次" % (g.letter, g.evals[-1]) for g in groups)),
        width_in, 10.2), 0.086, 0.922, fontsize=10.2, color="#B2182B")
    notes = []
    if overlap_lines:
        notes.append("曲线重合（由 curve.json 逐点比对得出，非人工判断）：%s。" % "；".join(overlap_lines))
    notes += [
        "横轴是实际候选评价次数 candidate_evaluations，不是迭代步号 step；曲线为该文件 "
        "(candidate_evaluations, collision_pair_count) 的阶梯连线（step-post）。",
        "停止原因（ledger.json）：%s。" % "；".join("%s %s" % (g.letter, g.ledger["stop_reason"])
                                              for g in groups),
        "数据来源（只读）：%s/{四组}/curve.json 与同目录 ledger.json。" % ABLATION_DIR,
        "每组仅运行 1 次；横轴推进量的差异来自该次运行中各目标实际消耗的评价次数，不构成效率结论。",
    ]
    add_notes(fig, notes, 0.086, note_band_top(bottom, 0.055), fontsize=9.0)

    name = "f2_pairs_vs_evaluations"
    save_figure(fig, out_dir, name, files, layout_log)
    return name, [g.curve_path for g in groups] + [g.ledger_path for g in groups]


# --------------------------------------------------------------------------
# 图 3：额外长度、运行时间与预算利用
# --------------------------------------------------------------------------


def figure_3(groups, out_dir: Path, files: list, layout_log: list):
    letters = [g.letter for g in groups]
    lengths = [float(g.ledger["final_extra_length_mm"]) for g in groups]
    runtimes = [float(g.ledger["runtime_seconds"]) for g in groups]
    used = [float(g.ledger["candidate_evaluations"]) for g in groups]
    budget = float(groups[0].ledger["candidate_budget"])
    percents = [g.budget_percent for g in groups]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 7.2),
                                   gridspec_kw=dict(width_ratios=[1.34, 1.0], wspace=0.34))
    bottom = 0.30
    fig.subplots_adjust(left=0.078, right=0.945, top=0.760, bottom=bottom)
    width_in = fig.get_size_inches()[0]
    xs = np.arange(len(groups))

    bars = ax1.bar(xs, lengths, width=0.5, color=[GROUP_COLORS[l] for l in letters],
                   edgecolor="white", linewidth=0.8, zorder=3)
    for bar, value in zip(bars, lengths):
        ax1.text(bar.get_x() + bar.get_width() / 2, value + 0.18, "%.3f" % value,
                 ha="center", va="bottom", fontsize=10.4, color="#222222", zorder=4)
    ax1.set_ylim(0, max(lengths) * 1.32)
    ax1.set_ylabel("额外长度 final_extra_length_mm（mm）", color="#222222")
    ax1.set_xticks(xs)
    ax1.set_xticklabels(letters, fontsize=11.5)
    ax1.grid(axis="y", alpha=0.22, zorder=0)
    ax1.set_axisbelow(True)

    ax1b = ax1.twinx()
    ax1b.spines["right"].set_visible(True)
    ax1b.plot(xs, runtimes, color="#7A1FA2", marker="s", markersize=6.5, linewidth=1.9,
              zorder=5, label="运行时间 runtime_seconds（s）")
    for x, value in zip(xs, runtimes):
        ax1b.annotate("%.1f" % value, xy=(x, value), xytext=(0, 11), textcoords="offset points",
                      ha="center", fontsize=10.0, color="#5B1387", zorder=6,
                      bbox=dict(boxstyle="round,pad=0.16", facecolor="white", edgecolor="none",
                                alpha=0.88))
    ax1b.set_ylim(0, max(runtimes) * 1.36)
    ax1b.set_ylabel("运行时间 runtime_seconds（s，单次实测）", color="#7A1FA2")
    ax1b.tick_params(axis="y", colors="#7A1FA2")
    ax1b.spines["top"].set_visible(False)
    ax1b.spines["right"].set_color("#7A1FA2")
    ax1.set_title("（a）额外长度（柱，左轴，mm）与运行时间（折线，右轴，s）", fontsize=11.5)

    bars2 = ax2.bar(xs, percents, width=0.5, color=[GROUP_COLORS[l] for l in letters],
                    edgecolor="white", linewidth=0.8, zorder=3)
    for bar, pct, cnt in zip(bars2, percents, used):
        ax2.text(bar.get_x() + bar.get_width() / 2, pct + 2.6, "%.2f%%" % pct,
                 ha="center", va="bottom", fontsize=10.8, fontweight="bold", zorder=4)
        ax2.text(bar.get_x() + bar.get_width() / 2, pct / 2, "%d/%d" % (int(cnt), int(budget)),
                 ha="center", va="center", fontsize=9.8, color="white", zorder=4)
    ax2.axhline(100.0, color="#B2182B", linestyle="--", linewidth=1.3, zorder=2)
    ax2.text(len(groups) - 0.45, 113.0, "预算上限 100%%（%d 次）" % int(budget), ha="right",
             va="center", fontsize=9.8, color="#B2182B")
    ax2.set_ylim(0, 132)
    ax2.set_xticks(xs)
    ax2.set_xticklabels(letters, fontsize=11.5)
    ax2.set_ylabel("候选评价预算使用率（%）")
    ax2.grid(axis="y", alpha=0.22, zorder=0)
    ax2.set_axisbelow(True)
    ax2.set_title("（b）候选评价预算使用率 candidate_evaluations / candidate_budget",
                  fontsize=11.5)

    fig.text(0.078, 0.968, "四组功能消融的成本记录：额外长度、运行时间与候选评价预算利用",
             fontsize=14.0, ha="left", va="top")
    add_notes(fig, wrap_paragraph(
        "组字母 A/B/C/D 为本轮功能消融分组，不是历史策略字母 A/B/C；每组仅运行 1 次（同一 512 输入、"
        "同一机器、同一进程设置），单次实测不能支持普遍效率结论。", width_in, 10.2),
        0.078, 0.918, fontsize=10.2, color="#B2182B")
    add_notes(fig, [
        "数据来源（只读）：%s/{四组}/ledger.json 的 final_extra_length_mm、runtime_seconds、"
        "candidate_evaluations、candidate_budget。" % ABLATION_DIR,
        "额外长度口径：final_total_length_mm - initial_total_length_mm（四组初态总长相同）；"
        "运行时间含初始配对扫描与分配阶段，未做重复实验，无置信区间。",
        "预算使用率只反映该次运行实际消耗的评价次数：%s。"
        % "；".join("%s %d/%d = %.2f%%" % (g.letter, int(u), int(budget), p)
                   for g, u, p in zip(groups, used, percents)),
        "切勿据此图宣称某个功能组合普遍更快或更省长度：本图只有 4 个单次实测点。",
        "实现对照：%s。" % "；".join(g.flag_text_long for g in groups),
    ], 0.078, note_band_top(bottom, 0.055), fontsize=9.0)

    name = "f3_costs"
    save_figure(fig, out_dir, name, files, layout_log)
    return name, [g.ledger_path for g in groups]


# --------------------------------------------------------------------------
# 图 6：真实路线几何
# --------------------------------------------------------------------------


def sample_primitive(primitive, n_arc: int = 73, n_transition: int = 61) -> np.ndarray:
    from src.geometry_3d import CosineTransition3D, LineSegment3D

    if isinstance(primitive, LineSegment3D):
        points = [primitive.start, primitive.end]
    else:
        n = n_transition if isinstance(primitive, CosineTransition3D) else n_arc
        points = [primitive.point_at(float(t)) for t in np.linspace(0.0, 1.0, n)]
    return np.array([[p.x, p.y, p.z] for p in points], dtype=float)


def classify_primitive(primitive):
    from src.geometry_3d import CosineTransition3D

    if isinstance(primitive, CosineTransition3D):
        return "transition"
    z = primitive.point_at(0.0).z
    if abs(z - round(z)) > 1e-8 or int(round(z)) not in (0, 1, 2):
        raise ValueError("非预期平面高度 z=%r" % z)
    return int(round(z))


def select_route(final_routes_path: Path):
    """挑选过渡段最多的真实被抬升路线；同分时依次比较峰值 z、抬升段长度、route_id。"""
    from src.fixed_1024_routing import deserialize_route3d
    from src.geometry_3d import CosineTransition3D, LineSegment3D, PlanarArcSegment3D

    payload = load_json(final_routes_path)
    candidates = []
    for row in payload["routes"]:
        route = deserialize_route3d(row["geometry"])
        transitions = [p for p in route.primitives if isinstance(p, CosineTransition3D)]
        if not transitions:
            continue
        peak = max(max(p.point_at(0.0).z, p.point_at(1.0).z) for p in route.primitives)
        elevated_length = 0.0
        for p in route.primitives:
            if isinstance(p, (LineSegment3D, PlanarArcSegment3D)) and p.point_at(0.0).z > 0:
                elevated_length += p.length()
        candidates.append(dict(route=route, row=row, transitions=len(transitions),
                               peak=float(peak), elevated_length=float(elevated_length)))
    if not candidates:
        raise SystemExit("final_routes.json 中没有含余弦过渡段的被抬升路线")
    candidates.sort(key=lambda c: (-c["transitions"], -c["peak"], -c["elevated_length"],
                                   c["route"].route_id))
    best = candidates[0]
    selection = dict(
        criterion="在 final_routes.json 全部路线中按（余弦过渡段数最多，峰值 z 最高，"
                  "抬升平面段总长最长，route_id 最小）排序取第一条",
        candidate_count=len(candidates),
        max_transition_count=best["transitions"],
        tied_at_max_transitions=sum(c["transitions"] == best["transitions"] for c in candidates),
        route_id=best["route"].route_id,
        main_layer=best["row"]["main_layer"],
        transition_count=best["transitions"],
        peak_z_mm=best["peak"],
        elevated_planar_length_mm=best["elevated_length"],
        primitive_count=len(best["route"].primitives),
    )
    return best["route"], selection


def figure_6(root: Path, out_dir: Path, files: list, layout_log: list):
    from src.geometry_3d import lift_smoothed_route_to_layer
    from src.models import Layer
    from src.multi_attribution import deserialize_plot

    routes_path = root / FINAL_ROUTES
    legacy_path = root / LEGACY_PLOT_GEOMETRY
    route, selection = select_route(routes_path)

    legacy = load_json(legacy_path)
    records = {int(r["id"]): r for r in legacy["routes"]}
    if route.route_id not in records:
        raise SystemExit("平面参考中缺少 route %d" % route.route_id)
    planar_reference = lift_smoothed_route_to_layer(deserialize_plot(records[route.route_id]),
                                                   Layer(0, 0.0))

    actual_pieces = [(classify_primitive(p), sample_primitive(p)) for p in route.primitives]
    reference_points = np.concatenate([sample_primitive(p) for p in planar_reference.primitives])
    actual_points = np.concatenate([pts for _, pts in actual_pieces])

    def resample(points, count=401):
        deltas = np.linalg.norm(np.diff(points[:, :2], axis=0), axis=1)
        arc = np.concatenate([[0.0], np.cumsum(deltas)])
        targets = np.linspace(0.0, arc[-1], count)
        return np.column_stack([np.interp(targets, arc, points[:, 0]),
                                np.interp(targets, arc, points[:, 1])])

    xy_deviation = float(np.max(np.linalg.norm(resample(actual_points) - resample(reference_points),
                                               axis=1)))
    ledger_d = load_json(root / ABLATION_DIR / "D_both_enabled" / "ledger.json")
    layer_counts = {int(k): int(v) for k, v in ledger_d["layer_route_counts"].items()}
    elevated_y_segment = float(route.primitives[2].length())

    xlim = (10.775 - 7.0, 133.9 + 7.0)
    ylim = (-9.0, 159.0)
    zlim = (-0.06, 2.06)

    fig = plt.figure(figsize=(15.0, 10.9))
    bottom = 0.285
    fig.subplots_adjust(left=0.052, right=0.972, top=0.845, bottom=bottom,
                        wspace=0.175, hspace=0.33)
    width_in = fig.get_size_inches()[0]

    def draw_2d(ax, plane):
        ref = reference_points
        if plane == "xy":
            ax.plot(ref[:, 0], ref[:, 1], color=REFERENCE_COLOR, linewidth=4.6, alpha=0.5,
                    solid_capstyle="round", zorder=1)
            for kind, pts in actual_pieces:
                ax.plot(pts[:, 0], pts[:, 1], color=LAYER_COLORS[kind], linewidth=2.1, zorder=3)
            ax.set_xlabel("x（mm）")
            ax.set_ylabel("y（mm）")
            ax.set_xlim(xlim)
            ax.set_ylim(ylim)
            ax.set_aspect("equal")
        else:
            ax.plot(ref[:, 0], ref[:, 2], color=REFERENCE_COLOR, linewidth=4.6, alpha=0.5,
                    solid_capstyle="round", zorder=1)
            for kind, pts in actual_pieces:
                ax.plot(pts[:, 0], pts[:, 2], color=LAYER_COLORS[kind], linewidth=2.3, zorder=3)
            for z in (1, 2):
                ax.axhline(z, color="#CCCCCC", linestyle=":", linewidth=1.0, zorder=0)
                ax.text(70.0, z + 0.05, "层 %d（z = %d mm）" % (z, z), ha="center", va="bottom",
                        fontsize=9.0, color="#777777",
                        bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none",
                                  alpha=0.85))
            ax.set_xlabel("x（mm）")
            ax.set_ylabel("z（mm，真实值 0 / 1 / 2 mm）")
            ax.set_xlim(xlim)
            ax.set_ylim(-0.28, 2.62)
            ax.set_yticks([0, 1, 2])
        ax.scatter([actual_points[0, 0]],
                   [actual_points[0, 1] if plane == "xy" else actual_points[0, 2]],
                   marker="o", s=46, facecolor="white", edgecolor="#222222", linewidth=1.3,
                   zorder=6)
        ax.scatter([actual_points[-1, 0]],
                   [actual_points[-1, 1] if plane == "xy" else actual_points[-1, 2]],
                   marker="s", s=46, facecolor="#222222", edgecolor="white", linewidth=1.0,
                   zorder=6)
        ax.grid(alpha=0.18, zorder=0)
        ax.set_axisbelow(True)

    ax_xy = fig.add_subplot(2, 2, 1)
    draw_2d(ax_xy, "xy")
    ax_xy.annotate("起点", xy=(actual_points[0, 0], actual_points[0, 1]),
                   xytext=(actual_points[0, 0] - 3.0, actual_points[0, 1] - 9.0),
                   fontsize=10.0, color="#222222")
    ax_xy.annotate("终点", xy=(actual_points[-1, 0], actual_points[-1, 1]),
                   xytext=(actual_points[-1, 0] + 2.5, actual_points[-1, 1] + 4.0),
                   fontsize=10.0, color="#222222")
    ax_xy.text(0.975, 0.975,
               "XY 足迹与平面参考重合\n实测最大偏差 %.2e mm" % xy_deviation,
               transform=ax_xy.transAxes, ha="right", va="top", fontsize=9.4, color="#444444",
               linespacing=1.5,
               bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#CCCCCC",
                         alpha=0.92))
    ax_xy.set_title("（a）XY 投影（俯视，x/y 等比例）", fontsize=12.0)

    ax_xz = fig.add_subplot(2, 2, 2)
    draw_2d(ax_xz, "xz")
    ax_xz.set_title("（b）XZ 侧视投影（沿 y 方向压缩；纵向显示放大以便看清 2 mm 层高，z 刻度为真实值）",
                    fontsize=11.0)
    rise_x = float(route.primitives[1].point_at(0.0).x)
    fall_x = float(route.primitives[-2].point_at(0.0).x)
    ax_xz.annotate("上升过渡段 x = %.3f mm" % rise_x, xy=(rise_x, 2.0),
                   xytext=(rise_x - 6.0, 2.36), ha="right", va="center", fontsize=9.5,
                   color=LAYER_COLORS["transition"],
                   arrowprops=dict(arrowstyle="->", color=LAYER_COLORS["transition"],
                                   linewidth=1.0))
    ax_xz.annotate("下降过渡段 x = %.3f mm" % fall_x, xy=(fall_x, 2.0),
                   xytext=(fall_x + 5.0, 2.36), ha="left", va="center", fontsize=9.5,
                   color=LAYER_COLORS["transition"],
                   arrowprops=dict(arrowstyle="->", color=LAYER_COLORS["transition"],
                                   linewidth=1.0))
    ax_xz.text(72.0, 0.70,
               "层 2 抬升平面段总长 %.1f mm（其中沿 y 的直线段 %.1f mm）；\n"
               "XZ 侧视把整段抬升压缩为 z = 2 mm 的一条水平线"
               % (selection["elevated_planar_length_mm"], elevated_y_segment),
               ha="center", va="center", fontsize=9.4, color="#444444", linespacing=1.5)

    def draw_3d(ax, scale: float):
        ref = reference_points.copy()
        ref[:, 2] *= scale
        ax.add_collection3d(Line3DCollection([ref], colors=REFERENCE_COLOR, linewidths=4.0,
                                             alpha=0.55, linestyles="-"), autolim=False)
        for kind in (0, 1, 2, "transition"):
            arr = [pts.copy() for k, pts in actual_pieces if k == kind]
            if not arr:
                continue
            for a in arr:
                a[:, 2] *= scale
            ax.add_collection3d(Line3DCollection(arr, colors=LAYER_COLORS[kind],
                                                 linewidths=2.4), autolim=False)
        pts = actual_points.copy()
        pts[:, 2] *= scale
        ax.scatter([pts[0, 0]], [pts[0, 1]], [pts[0, 2]], marker="o", s=42, facecolor="white",
                   edgecolor="#222222", linewidth=1.2, depthshade=False)
        ax.scatter([pts[-1, 0]], [pts[-1, 1]], [pts[-1, 2]], marker="s", s=42,
                   facecolor="#222222", edgecolor="white", linewidth=1.0, depthshade=False)
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.set_zlim(zlim[0] * scale, zlim[1] * scale)
        ax.set_xticks([20, 60, 100, 130])
        ax.set_yticks([0, 50, 100, 150])
        ax.set_zticks([0.0, 1.0 * scale, 2.0 * scale])
        ax.set_zticklabels(["0", "1", "2"])
        ax.set_xlabel("x（mm）")
        ax.set_ylabel("y（mm）")
        ax.set_zlabel("z（mm，真实值）" if scale == 1
                      else "z（mm，真实值；显示放大 %d 倍）" % int(scale), labelpad=4)
        ax.set_box_aspect((xlim[1] - xlim[0], ylim[1] - ylim[0], (zlim[1] - zlim[0]) * scale))
        ax.view_init(elev=22, azim=-58)
        ax.tick_params(labelsize=9.0)

    ax_true = fig.add_subplot(2, 2, 3, projection="3d")
    draw_3d(ax_true, 1.0)
    ax_true.set_title("（c）三维视图：真实高度比例（z 与 x/y 同尺度，未放大）", fontsize=12.0)

    ax_exag = fig.add_subplot(2, 2, 4, projection="3d")
    draw_3d(ax_exag, float(Z_EXAGGERATION))
    ax_exag.set_title("（d）三维视图：Z 轴放大 %d 倍（真实层高 0/1/2 mm）" % Z_EXAGGERATION,
                      fontsize=12.0)

    handles = [Line2D([0], [0], color=LAYER_COLORS[k], linewidth=3.0, label=LAYER_LABELS[k])
               for k in (0, 1, 2, "transition")]
    handles += [
        Line2D([0], [0], color=REFERENCE_COLOR, linewidth=4.0, alpha=0.55,
               label="平面参考（Layer(0,0)，未抬升）"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white",
               markeredgecolor="#222222", markersize=8, label="起点"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="#222222",
               markeredgecolor="white", markersize=8, label="终点"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=7, bbox_to_anchor=(0.5, 0.252),
               frameon=False, fontsize=9.8, columnspacing=1.7, handletextpad=0.6)

    fig.text(0.052, 0.975,
             "真实被抬升路线的几何：XY 投影、XZ 侧视、真实比例三维与 Z 轴放大 %d 倍三维"
             % Z_EXAGGERATION, fontsize=14.0, ha="left", va="top")
    add_notes(fig, wrap_paragraph(
        "路线 %d（来自 %s）：%d 段余弦过渡段，峰值 z = %.2f mm，抬升平面段总长 %.3f mm；真实层高为 "
        "0 / 1 / 2 mm。（c）为真实高度比例，（d）为 Z 轴放大 %d 倍示意图，二者在不同子图、标题分别写明，不得混用。"
        % (route.route_id, FINAL_ROUTES, selection["transition_count"], selection["peak_z_mm"],
           selection["elevated_planar_length_mm"], Z_EXAGGERATION), width_in, 10.2),
        0.052, 0.936, fontsize=10.2, color="#B2182B")
    add_notes(fig, [
        "路线选择规则：%s；%d 条被抬升路线中 %d 条并列最多过渡段，选中 route %d。"
        % (selection["criterion"], selection["candidate_count"],
           selection["tied_at_max_transitions"], selection["route_id"]),
        "路线反序列化：src.fixed_1024_routing.deserialize_route3d；平面参考：%s 经 "
        "src.multi_attribution.deserialize_plot + src.geometry_3d.lift_smoothed_route_to_layer，"
        "Layer(0, 0)。" % LEGACY_PLOT_GEOMETRY,
        "抬升只改变 z：实际路线 XY 足迹与平面参考完全重合（按弧长重采样 401 点，实测最大偏差 %.2e mm）。"
        % xy_deviation,
        "数据来源（只读）：%s；D 组终态分层路线数：层 0 %d 条、层 1 %d 条、层 2 %d 条（ledger.json）。"
        % (FINAL_ROUTES, layer_counts[0], layer_counts[1], layer_counts[2]),
    ], 0.052, note_band_top(bottom, 0.089), fontsize=9.2)

    name = "f6_route_geometry"
    save_figure(fig, out_dir, name, files, layout_log)
    return name, [routes_path, legacy_path], selection, xy_deviation


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def main(argv):
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    out_dir = (root / (argv[2] if len(argv) > 2 else "outputs/3d_strategy_v3/figures")).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    out_dir.mkdir(parents=True, exist_ok=True)

    resolved_font = setup_fonts()
    groups = load_groups(root)
    checks = cross_check(groups)

    files: list = []
    layout_log: list = []
    figures_meta = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        name, inputs = figure_1(groups, out_dir, files, layout_log, root)
        figures_meta.append(dict(name=name, title="四组终态近距对（源图 f1_group_pairs）",
                                 inputs=[dict(path=str(p), sha256=sha256_of(p)) for p in inputs]))
        name, inputs = figure_2(groups, out_dir, files, layout_log)
        figures_meta.append(dict(name=name, title="近距对随实际候选评价次数变化（源图 f2_pairs_vs_evaluations）",
                                 inputs=[dict(path=str(p), sha256=sha256_of(p)) for p in inputs]))
        name, inputs = figure_3(groups, out_dir, files, layout_log)
        figures_meta.append(dict(name=name, title="额外长度、运行时间与预算利用（源图 f3_costs）",
                                 inputs=[dict(path=str(p), sha256=sha256_of(p)) for p in inputs]))
        name, inputs, selection, xy_deviation = figure_6(root, out_dir, files, layout_log)
        figures_meta.append(dict(name=name, title="真实路线几何（源图 f6_route_geometry）",
                                 inputs=[dict(path=str(p), sha256=sha256_of(p)) for p in inputs],
                                 route=selection, z_exaggeration=Z_EXAGGERATION,
                                 measured_max_xy_deviation_mm=xy_deviation))
    missing = [str(w.message) for w in caught if "missing from font" in str(w.message)]
    if missing:
        raise SystemExit("存在缺字（中文会变成方框）：%s" % "; ".join(sorted(set(missing))))

    manifest = dict(
        script="scripts/visualize_3d_strategy_v3.py",
        project_root=str(root),
        output_dir=str(out_dir),
        command=".venv\\Scripts\\python.exe -B scripts/visualize_3d_strategy_v3.py . "
                "outputs/3d_strategy_v3/figures",
        figure_files=[str(p) for p in files],
        figures=figures_meta,
        fonts=dict(
            family="SimSun",
            source=str(SIMSUN_PATH),
            resolved=resolved_font,
            registered_with="matplotlib.font_manager.fontManager.addfont",
            axes_unicode_minus=False,
            note="宋体缺 U+2212，所有文本只用 ASCII '-'；脚本检查缺字并在发现时失败。",
        ),
        group_naming=dict(
            letters=["A", "B", "C", "D"],
            meaning={"A": "基线原版", "B": "仅结构化生成缓存", "C": "仅窗口松弛",
                     "D": "两者同时启用"},
            disclaimer="组字母为本轮功能消融分组，不是历史策略字母 A/B/C。",
            per_group_flags={g.letter: dict(generation_failure_cache_enabled=g.cache_on,
                                            window_slack_mm=g.slack_mm) for g in groups},
        ),
        values_read_from_json={
            g.letter: dict(
                final_collision_pair_count=g.ledger["final_collision_pair_count"],
                net_collision_reduction=g.ledger["net_collision_reduction"],
                reduction_percent=g.ledger["reduction_percent"],
                initial_collision_pair_count=g.ledger["initial_collision_pair_count"],
                final_extra_length_mm=g.ledger["final_extra_length_mm"],
                runtime_seconds=g.ledger["runtime_seconds"],
                candidate_evaluations=g.ledger["candidate_evaluations"],
                candidate_budget=g.ledger["candidate_budget"],
                budget_used_percent=g.budget_percent,
                stop_reason=g.ledger["stop_reason"],
            ) for g in groups
        },
        expected_value_checks=checks,
        layout_checks=layout_log,
        warnings=SELFTEST_NOTES,
        z_exaggeration=Z_EXAGGERATION,
        selected_route=figures_meta[-1].get("route"),
        figure6_notes=dict(
            planar_reference="outputs/step_8_5_legacy_512_plot_geometry.json 经 "
                             "src.multi_attribution.deserialize_plot + "
                             "src.geometry_3d.lift_smoothed_route_to_layer，Layer(0, 0)",
            transition_deserialization="src.fixed_1024_routing.deserialize_route3d",
            true_scale_panel="（c）标题写明“真实高度比例”，z 与 x/y 同尺度",
            exaggerated_panel="（d）标题写明“Z 轴放大 %d 倍（真实层高 0/1/2 mm）”" % Z_EXAGGERATION,
        ),
    )
    manifest_path = out_dir / "figures_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print("已写出 %d 个图文件：" % len(files))
    for path in files:
        print("  ", path)
    print("manifest:", manifest_path)
    for report in layout_log:
        if report["note_overlaps"]:
            print("排版提示（%s）：图级注释与其它文本重叠 %d 处" %
                  (report["figure"], len(report["note_overlaps"])))
            for item in report["note_overlaps"]:
                print("   -", json.dumps(item, ensure_ascii=False))
        else:
            print("排版自检（%s）：无越界、无注释重叠。" % report["figure"])
    if SELFTEST_NOTES:
        print("警告：")
        for note in SELFTEST_NOTES:
            print("  -", note)


if __name__ == "__main__":
    main(sys.argv)
