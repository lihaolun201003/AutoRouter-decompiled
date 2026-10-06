"""Figures for one overnight round, rendered from comparison.csv + summary_<round>.json.

Usage (project root):
    .venv\Scripts\python.exe -B scripts\overnight_figures.py PROJECT OUTDIR --round v5

Every plotted number is read from
    OUTDIR/<round>/comparison.csv
    OUTDIR/<round>/summary_<round>.json      (coverage / recheck_geometry / typed rows)
and written as PNG + PDF into OUTDIR/figures/<round>_fN_*.png|.pdf, together with
one manifest JSON per figure that lists the file names, the title and the exact
source columns and source sub-objects that figure used.

The matplotlib style follows the v4 figure conventions (SimSun + the same rcParams
and colour scheme); the style helpers are reproduced here on purpose so that no
heavy project module has to be imported.
"""
import argparse
import csv
import hashlib
import json
import sys
import textwrap
import warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.lines import Line2D

GENERATOR = "scripts/overnight_figures.py"
FONT_CANDIDATES = [Path("C:/Windows/Fonts/simsun.ttc"), Path("C:/Windows/Fonts/msyh.ttc")]
STRATEGY_COLORS = ["#0072B2", "#D55E00", "#009E73", "#5B1387", "#E69F00", "#B2182B"]
MODE_COLOR = {"N": "#0072B2", "R": "#D55E00"}
ACTION_COLORS = {"first": "#0072B2", "relocation": "#D55E00", "return": "#009E73"}
LAYER_CLASSES = ("UU", "UE", "EE")
CLASS_COLORS = {"UU": "#9aa5b1", "UE": "#0072B2", "EE": "#D55E00"}
MODE_LINESTYLE = {"N": "-", "R": "--"}
MODE_MARKER = {"N": "o", "R": "s"}
MANIFEST = []


def parse_args(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("project", help="project root (kept for interface symmetry)")
    ap.add_argument("outdir", help="outputs/overnight_3d_ideas")
    ap.add_argument("--round", required=True, help="round directory name, e.g. v5")
    return ap.parse_args(argv[1:])


ARGS = parse_args(sys.argv)
ROOT = Path(ARGS.project).resolve()
OUT = Path(ARGS.outdir).resolve()
ROUND = ARGS.round
ROUND_DIR = OUT / ROUND
FIGDIR = OUT / "figures"
CSV_PATH = ROUND_DIR / ("comparison.csv")
SUMMARY_PATH = ROUND_DIR / ("summary_%s.json" % ROUND)
def shown(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


CSV_SOURCE = shown(CSV_PATH)
SUMMARY_SOURCE = shown(SUMMARY_PATH)


# --------------------------------------------------------------------- styling
def setup_fonts():
    """Same conventions as outputs/3d_strategy_v4/512_full_layout/figures."""
    resolved = None
    for path in FONT_CANDIDATES:
        if path.exists():
            fm.fontManager.addfont(str(path))
            resolved = path.name
            break
    family = ["SimSun"] if resolved and "simsun" in resolved.lower() else \
        (["Microsoft YaHei"] if resolved else ["DejaVu Sans"])
    plt.rcParams.update({"font.family": family,
        "font.sans-serif": family + ["Microsoft YaHei", "SimSun", "DejaVu Sans"],
        "font.serif": family + ["Times New Roman", "DejaVu Serif"],
        "axes.unicode_minus": False, "mathtext.fontset": "stix", "font.size": 10.5,
        "axes.titlesize": 12.0, "axes.labelsize": 11.0, "xtick.labelsize": 10.0,
        "ytick.labelsize": 10.0, "legend.fontsize": 9.5, "figure.dpi": 120,
        "savefig.dpi": 300, "savefig.facecolor": "white", "figure.facecolor": "white",
        "axes.facecolor": "white", "axes.edgecolor": "#333333", "axes.linewidth": .8,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
        "grid.alpha": .22, "grid.linewidth": .5, "legend.frameon": False,
        "lines.linewidth": 1.7, "pdf.fonttype": 42, "ps.fonttype": 42})
    if resolved is None:
        print("WARNING: no CJK font found, falling back to the matplotlib default",
              flush=True)
    return resolved


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numeric_tick_axis(axis):
    """True only when the tick labels are the default rendering of the tick positions.

    A categorical axis whose labels happen to be numbers (720 / 1440 / 2880 on
    positions 0 / 1 / 2) must keep its labels: replacing them with the formatter
    would print the position instead of the label."""
    labels = [tick.get_text() for tick in axis.get_ticklabels()]
    positions = list(axis.get_majorticklocs())
    if not labels or len(labels) != len(positions):
        return False
    for label, position in zip(labels, positions):
        try:
            value = float(label.replace(",", ""))
        except ValueError:
            return False
        if abs(value - position) > 1e-9 * max(1.0, abs(position)):
            return False
    return True


def wrap_long_texts(fig, width=108):
    """Wrap long figure-level footnotes so 'tight' cannot inflate the canvas."""
    for text in fig.texts:
        value = text.get_text()
        if len(value) > width and "\n" not in value:
            text.set_text("\n".join(textwrap.wrap(value, width=width, break_long_words=True)))


def save(fig, name, *, title, columns, sub_objects, notes, rows_used):
    """Write PNG + PDF + one manifest JSON listing file, title and source fields."""
    from matplotlib.ticker import FuncFormatter
    ascii_formatter = FuncFormatter(lambda value, position: "%g" % value)
    for ax in fig.axes:
        if numeric_tick_axis(ax.xaxis):
            ax.xaxis.set_major_formatter(ascii_formatter)
        if numeric_tick_axis(ax.yaxis):
            ax.yaxis.set_major_formatter(ascii_formatter)
    # SimSun has no U+2212: force ASCII-hyphen tick labels, then replace any
    # remaining minus sign in figure text before rasterising. The font warning
    # raised by the exploratory draw is expected and silenced on purpose.
    wrap_long_texts(fig)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Glyph .* missing from font")
        fig.canvas.draw()
        for text in fig.findobj(matplotlib.text.Text):
            value = text.get_text()
            if "\u2212" in value:
                text.set_text(value.replace("\u2212", "-"))
        png = FIGDIR / (name + ".png")
        pdf = FIGDIR / (name + ".pdf")
        fig.savefig(png, bbox_inches="tight", facecolor="white")
        fig.savefig(pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    manifest = dict(figure=name, title=title,
                    png=str(png), pdf=str(pdf),
                    png_sha256=sha256(png), pdf_sha256=sha256(pdf),
                    source_files=[CSV_SOURCE, SUMMARY_SOURCE],
                    source_columns=list(columns),
                    source_sub_objects=list(sub_objects),
                    rows_used=rows_used, notes=notes, generator=GENERATOR,
                    round=ROUND,
                    generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    (FIGDIR / (name + ".manifest.json")).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    MANIFEST.append(manifest)
    print("  wrote %s.png / %s.pdf (+ manifest)" % (name, name), flush=True)


def fmt_int(value):
    return "n/a" if value is None else ("%s" % format(int(round(value)), ","))


def fmt_num(value, digits=3):
    return "n/a" if value is None else ("%.*f" % (digits, value))


# ------------------------------------------------------------------ data input
def typed(value):
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def load_round():
    for path in (CSV_PATH, SUMMARY_PATH):
        if not path.is_file():
            raise SystemExit("missing %s; run scripts/summarize_overnight.py first" % path)
    payload = json.loads(SUMMARY_PATH.read_text(encoding="utf-8-sig"))
    with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        csv_rows = [{k: typed(v) for k, v in row.items()} for row in reader]
    declared = payload.get("column_order", [])
    if declared and fieldnames != declared:
        raise SystemExit("comparison.csv columns differ from summary_%s.json column_order\n"
                         "  csv: %s\n  json: %s" % (ROUND, fieldnames, declared))
    json_rows = {row.get("group"): row for row in payload.get("rows", [])}
    if set(json_rows) != {row.get("group") for row in csv_rows}:
        raise SystemExit("comparison.csv and summary_%s.json list different groups" % ROUND)
    for row in csv_rows:
        source = json_rows.get(row.get("group"), {})
        row["coverage"] = source.get("coverage")
        row["recheck_geometry"] = source.get("recheck_geometry")
        row["strategy_spec"] = source.get("strategy_spec")
    return payload, csv_rows, fieldnames


def num(row, column):
    value = row.get(column)
    return float(value) if isinstance(value, (int, float)) else None


def integer(row, column):
    value = num(row, column)
    return None if value is None else int(round(value))


def text(row, column):
    value = row.get(column)
    return None if value is None else str(value)


def coverage(row, key):
    block = row.get("coverage") or {}
    value = block.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def strategy_colors(rows):
    names = sorted({text(row, "strategy") or "?" for row in rows})
    return {name: STRATEGY_COLORS[index % len(STRATEGY_COLORS)] for index, name in enumerate(names)}


def group_label(row):
    return "%s\n%s/budget %s" % (row.get("group"), row.get("mode"), row.get("budget"))


def budget_ticks(budgets):
    return [str(int(b)) for b in budgets]


# --------------------------------------------------------------------- figures
def figure_pairs_vs_budget(rows, payload, columns_used):
    main_rows = [r for r in rows if text(r, "start_kind") == "main"]
    challenge_rows = [r for r in rows if text(r, "start_kind") == "challenge"]
    colors = strategy_colors(rows)
    strategies = sorted({text(r, "strategy") or "?" for r in main_rows})
    budgets = sorted({integer(r, "budget") for r in main_rows if integer(r, "budget") is not None})
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 5.0),
                             gridspec_kw=dict(width_ratios=[1.7, 1.0]))
    ax = axes[0]
    start_value = None
    missing = []
    for strategy in strategies:
        for mode in ("N", "R"):
            series = sorted([r for r in main_rows
                             if text(r, "strategy") == strategy and text(r, "mode") == mode],
                            key=lambda r: integer(r, "budget") or 0)
            if not series:
                missing.append("%s/%s" % (strategy, mode))
                continue
            xs = [integer(r, "budget") for r in series]
            ys = [num(r, "final_collision_pairs") for r in series]
            for r in series:
                if start_value is None:
                    start_value = num(r, "initial_collision_pairs")
            ax.plot(xs, ys, color=colors[strategy], linestyle=MODE_LINESTYLE[mode],
                    marker=MODE_MARKER[mode], ms=6.5, mec="black", mew=.6,
                    label="%s / %s（%s）" % (strategy, mode,
                                            "允许重定位" if mode == "R" else "不重定位"))
            for x, y, r in zip(xs, ys, series):
                if y is not None:
                    ax.annotate(fmt_int(y), xy=(x, y), xytext=(0, 7),
                                textcoords="offset points", ha="center", fontsize=8.4,
                                color=colors[strategy])
    if start_value is not None:
        ax.axhline(start_value, color="#B2182B", lw=.9, ls=":")
        ax.annotate("共同起点 %s 对" % fmt_int(start_value), xy=(min(budgets), start_value),
                    xytext=(4, -12), textcoords="offset points", fontsize=8.6, color="#B2182B")
    ax.set_xticks(budgets)
    ax.set_xticklabels(budget_ticks(budgets))
    ax.set_xlabel("追加候选评价预算上限（次）")
    ax.set_ylabel("终态中心线近距对数（对）")
    ax.set_title("（a）main 起点：终态近距对数 vs 预算（每条曲线一个策略×模式）", fontsize=11)
    if not main_rows:
        ax.annotate("main 起点尚无已完成组", xy=(.5, .5), xycoords="axes fraction",
                    ha="center", va="center", color="#666666")
    else:
        ax.legend(loc="best", fontsize=8.6)

    ax2 = axes[1]
    strategies_ch = sorted({text(r, "strategy") or "?" for r in challenge_rows})
    width = .36
    if challenge_rows:
        for index, strategy in enumerate(strategies_ch):
            for offset, mode in ((-.5 * width, "N"), (.5 * width, "R")):
                row = next((r for r in challenge_rows
                            if text(r, "strategy") == strategy and text(r, "mode") == mode), None)
                if row is None:
                    ax2.annotate("未完成", xy=(index + offset, 0), xytext=(0, 4),
                                 textcoords="offset points", ha="center", fontsize=8.2,
                                 rotation=90, color="#999999")
                    continue
                value = num(row, "final_collision_pairs")
                ax2.bar(index + offset, value, width, color=MODE_COLOR[mode],
                        edgecolor="black", linewidth=.5)
                ax2.annotate(fmt_int(value), xy=(index + offset, value), xytext=(0, 3),
                             textcoords="offset points", ha="center", fontsize=8.4, rotation=90)
        ax2.set_xticks(range(len(strategies_ch)))
        ax2.set_xticklabels(["%s\n(challenge 起点)" % s for s in strategies_ch], fontsize=9)
        ax2.set_ylim(0, max(num(r, "final_collision_pairs") or 0 for r in challenge_rows) * 1.22)
    else:
        ax2.annotate("challenge 起点尚无已完成组", xy=(.5, .5), xycoords="axes fraction",
                     ha="center", va="center", color="#666666")
    ax2.set_ylabel("终态中心线近距对数（对）")
    ax2.set_title("（b）challenge 起点：2880 预算下 N 与 R", fontsize=11)
    handles = [Line2D([], [], color=MODE_COLOR["N"], lw=7, label="N：不重定位"),
               Line2D([], [], color=MODE_COLOR["R"], lw=7, label="R：允许重定位")]
    ax2.legend(handles=handles, loc="upper right", fontsize=8.6)
    fig.suptitle("%s 轮终态近距对数与追加评价预算（两种起点状态分开绘制，预算“追加”在起点状态之上）"
                 % ROUND, fontsize=12)
    fig.text(.01, -.06,
             "数据来源：%s 的 %s。起点近距对数取自每行 initial_collision_pairs（同一 start_kind 的组共享同一起点）。"
             "main 与 challenge 是不同的起点状态，只能各自内部比较；(b) 只有 2880 一个预算。%s"
             % (CSV_SOURCE, "、".join(columns_used),
                ("未出现的策略/模式组合：" + "、".join(missing)) if missing else "全部策略×模式组合均已出现。"),
             fontsize=8.6, color="#555555", va="top")
    save(fig, "%s_f1_pairs_vs_budget" % ROUND,
         title="终态近距对数 vs 追加候选评价预算（策略 × N/R 模式 × 两种起点）",
         columns=columns_used, sub_objects=[],
         notes="只使用 comparison.csv 的列；summary_<round>.json 仅用于核对列集合与未完成组名单",
         rows_used=len(rows))


def figure_same_budget_nr(rows, payload, columns_used):
    main_rows = [r for r in rows if text(r, "start_kind") == "main"]
    strategies = sorted({text(r, "strategy") or "?" for r in main_rows})
    budgets = sorted({integer(r, "budget") for r in main_rows if integer(r, "budget") is not None})
    missing_cells = []
    fig, axes = plt.subplots(1, max(1, len(strategies)), figsize=(6.4 * max(1, len(strategies)), 5.0),
                             squeeze=False)
    axes = axes[0]
    width = .36
    pair_notes = []
    for ax, strategy in zip(axes, strategies or ["?"]):
        pairs = []
        for index, budget in enumerate(budgets):
            values = {}
            for offset, mode in ((-.5 * width, "N"), (.5 * width, "R")):
                row = next((r for r in main_rows if text(r, "strategy") == strategy
                            and text(r, "mode") == mode and integer(r, "budget") == budget), None)
                if row is None:
                    missing_cells.append("%s/%s/%s" % (strategy, mode, budget))
                    ax.annotate("未完成", xy=(index + offset, 0), xytext=(0, 3),
                                textcoords="offset points", ha="center", fontsize=8.0,
                                rotation=90, color="#999999")
                    continue
                value = num(row, "final_collision_pairs")
                values[mode] = value
                ax.bar(index + offset, value, width, color=MODE_COLOR[mode],
                       edgecolor="black", linewidth=.5)
                ax.annotate(fmt_int(value), xy=(index + offset, value), xytext=(0, 3),
                            textcoords="offset points", ha="center", fontsize=8.4, rotation=90)
            if "N" in values and "R" in values:
                pairs.append("%s：N %s / R %s（R−N = %s）"
                             % (budget, fmt_int(values["N"]), fmt_int(values["R"]),
                                fmt_int(values["R"] - values["N"])))
        ax.set_xticks(range(len(budgets)))
        ax.set_xticklabels(budget_ticks(budgets))
        ax.set_xlabel("追加预算上限（次）")
        ax.set_ylabel("终态近距对数（对）")
        ax.set_title("策略 %s（同预算内 N vs R）" % strategy, fontsize=11)
        ax.legend(handles=[Line2D([], [], color=MODE_COLOR["N"], lw=7, label="N：不重定位"),
                           Line2D([], [], color=MODE_COLOR["R"], lw=7, label="R：允许重定位")],
                  loc="best", fontsize=8.6)
        pair_notes.extend(pairs)
    fig.suptitle("%s 轮：同一预算上限下 N 与 R 的终态近距对数（不同预算只表示趋势，不做排名）"
                 % ROUND, fontsize=12)
    fig.text(.01, -.06,
             "数据来源：%s 的 %s。只使用 start_kind=main 的组；challenge 起点在 f1(b) 单独绘制。%s%s"
             % (CSV_SOURCE, "、".join(columns_used),
                ("未完成单元：" + "、".join(missing_cells) + "。" if missing_cells
                 else "所有预算×模式单元均已完成。"),
                ("同预算对照：" + "；".join(pair_notes) + "。" if pair_notes
                 else "没有任何预算同时具备 N 与 R 两组，故不给出 R−N 差值。")),
             fontsize=8.6, color="#555555", va="top")
    save(fig, "%s_f2_same_budget_N_vs_R" % ROUND,
         title="同一预算上限下 N 与 R 的终态近距对数对照（按策略分面）",
         columns=columns_used, sub_objects=[],
         notes="缺失的单元画为“未完成”而不是 0，任何一方缺失就不给出 R−N 差值",
         rows_used=len(main_rows))
    return missing_cells


def figure_actions(rows, payload, columns_used):
    ordered = sorted(rows, key=lambda r: (text(r, "strategy") or "", text(r, "mode") or "",
                                          integer(r, "budget") or 0, text(r, "group") or ""))
    xs = np.arange(len(ordered))
    labels = [group_label(r) for r in ordered]
    fig, axes = plt.subplots(1, 2, figsize=(14.4, 5.6))
    series_a = [("first_elevations", "首次抬升", ACTION_COLORS["first"]),
                ("relocations", "重定位", ACTION_COLORS["relocation"]),
                ("returns", "回归平面（RETURN）", ACTION_COLORS["return"])]
    series_b = [("first_elevation_net_reduction", "首次抬升净减少", ACTION_COLORS["first"]),
                ("relocation_net_reduction", "重定位净减少", ACTION_COLORS["relocation"]),
                ("return_net_reduction", "RETURN 净减少", ACTION_COLORS["return"])]
    nulls = []
    for ax, series, ylabel, title in (
            (axes[0], series_a, "动作次数", "（a）执行动作数：首次抬升 / 重定位 / RETURN"),
            (axes[1], series_b, "净减少对数（合计）",
             "（b）净收益拆分：首次抬升 / 重定位 / RETURN")):
        bottom = np.zeros(len(ordered))
        for column, label, color in series:
            heights = np.array([num(r, column) or 0.0 for r in ordered], dtype=float)
            for row, value in zip(ordered, heights):
                if num(row, column) is None:
                    nulls.append("%s:%s" % (row.get("group"), column))
            ax.bar(xs, heights, .62, bottom=bottom, label=label, color=color,
                   edgecolor="black", linewidth=.4)
            for x, (height, base) in enumerate(zip(heights, bottom)):
                if height:
                    ax.annotate(fmt_int(height), xy=(x, base + height / 2), ha="center",
                                va="center", fontsize=7.6, color="white")
            bottom += heights
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=90, fontsize=7.0)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=11)
        ax.legend(loc="upper right", fontsize=8.6)
    fig.suptitle("%s 轮：动作构成与净收益拆分（每个柱子一个已完成组）" % ROUND, fontsize=12)
    fig.text(.01, -.22,
             "数据来源：%s 的 %s。净减少=移除−新增，三次拆分之和等于 total_old_collisions_removed − "
             "total_new_collisions_created。未启用的动作（例如本轮 return_action=false）恒为 0，"
             "这是真实结果，不是缺失值。%s"
             % (CSV_SOURCE, "、".join(columns_used),
                ("值为 null 的列：" + "、".join(sorted(set(nulls)))) if nulls else "无 null 列。"),
             fontsize=8.6, color="#555555", va="top")
    save(fig, "%s_f3_actions_and_reductions" % ROUND,
         title="执行动作数与净收益按 首次抬升 / 重定位 / RETURN 拆分",
         columns=columns_used, sub_objects=[],
         notes="NULL 值按 0 高度绘制并在脚注列出，绝不当作 0 读数",
         rows_used=len(ordered))


def figure_costs(rows, payload, columns_used):
    ordered = sorted(rows, key=lambda r: (text(r, "strategy") or "", text(r, "mode") or "",
                                          integer(r, "budget") or 0, text(r, "group") or ""))
    xs = np.arange(len(ordered))
    labels = [group_label(r) for r in ordered]
    panels = [("stage_length_delta_mm", "阶段长度变化（终态−起点，mm）", "#0072B2"),
              ("final_extra_length_vs_planar_mm", "终态相对冻结平面的额外长度（mm）", "#E69F00"),
              ("final_transition_count", "终态过渡段数量（段）", "#5B1387"),
              ("final_elevated_route_count", "终态已抬升路线数（条）", "#009E73")]
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.6),
                             gridspec_kw=dict(hspace=.62, wspace=.24))
    for ax, (column, title, color) in zip(axes.ravel(), panels):
        values = [num(r, column) for r in ordered]
        drawn = [0.0 if v is None else v for v in values]
        ax.bar(xs, drawn, .62, color=color, edgecolor="black", linewidth=.4)
        for x, (value, raw) in enumerate(zip(drawn, values)):
            if raw is None:
                ax.annotate("null", xy=(x, 0), xytext=(0, 4), textcoords="offset points",
                            ha="center", fontsize=7.0, color="#B2182B", rotation=90)
            else:
                ax.annotate(fmt_num(raw, 3 if "mm" in title else 0), xy=(x, value),
                            xytext=(0, 3 if value >= 0 else -9), textcoords="offset points",
                            ha="center", fontsize=7.0, rotation=90)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=90, fontsize=7.0)
        ax.set_title(title, fontsize=10.5)
        ax.margins(y=.16)
    fig.suptitle("%s 轮：几何代价面板（长度、过渡段、已抬升路线）" % ROUND, fontsize=12)
    fig.text(.01, -.20,
             "数据来源：%s 的 %s。stage_length_delta_mm 与 final_extra_length_vs_planar_mm 是两种口径："
             "前者相对共同起点终态，后者相对冻结平面基准；两者都不与近距对数合并成单一评分。"
             % (CSV_SOURCE, "、".join(columns_used)), fontsize=8.6, color="#555555", va="top")
    save(fig, "%s_f4_costs" % ROUND,
         title="几何代价：阶段长度变化、终态额外长度、过渡段数量、已抬升路线数",
         columns=columns_used, sub_objects=[], notes="null 直接标注为 null，不折成 0",
         rows_used=len(ordered))


def figure_efficiency(rows, payload, columns_used):
    ordered = sorted(rows, key=lambda r: (text(r, "strategy") or "", text(r, "mode") or "",
                                          integer(r, "budget") or 0, text(r, "group") or ""))
    xs = np.arange(len(ordered))
    labels = [group_label(r) for r in ordered]
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 5.4))
    for ax, column, title, color, digits in (
            (axes[0], "evaluations_per_action", "（a）每次执行动作消耗的评价次数", "#0072B2", 2),
            (axes[1], "net_reduction_per_evaluation", "（b）每次评价换来的净减少对数", "#D55E00", 4)):
        values = [num(r, column) for r in ordered]
        drawn = [0.0 if v is None else v for v in values]
        ax.bar(xs, drawn, .62, color=color, edgecolor="black", linewidth=.4)
        for x, (value, raw) in enumerate(zip(drawn, values)):
            if raw is None:
                reason = "无动作" if column == "evaluations_per_action" else "无评价"
                ax.annotate("null\n(%s)" % reason, xy=(x, 0), xytext=(0, 4),
                            textcoords="offset points", ha="center", fontsize=6.8,
                            color="#B2182B", rotation=90)
            else:
                ax.annotate(fmt_num(raw, digits), xy=(x, value), xytext=(0, 3),
                            textcoords="offset points", ha="center", fontsize=7.2, rotation=90)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=90, fontsize=7.0)
        ax.set_title(title, fontsize=11)
        ax.margins(y=.16)
    fig.suptitle("%s 轮：评价效率（效率是比值，不被当作质量评分）" % ROUND, fontsize=12)
    fig.text(.01, -.22,
             "数据来源：%s 的 %s。evaluations_per_action=实际评价次数/执行动作数，"
             "net_reduction_per_evaluation=净减少对数/实际评价次数；两者的分母为 0 时写 null "
             "而不是 0。" % (CSV_SOURCE, "、".join(columns_used)), fontsize=8.6,
             color="#555555", va="top")
    save(fig, "%s_f5_evaluation_efficiency" % ROUND,
         title="评价效率：每次动作的评价次数与每次评价的净减少",
         columns=columns_used, sub_objects=[], notes="分母为 0 的比值保持 null",
         rows_used=len(ordered))


def figure_coverage(rows, payload, columns_used):
    ordered = sorted(rows, key=lambda r: (text(r, "strategy") or "", text(r, "mode") or "",
                                          integer(r, "budget") or 0, text(r, "group") or ""))
    xs = np.arange(len(ordered))
    labels = [group_label(r) for r in ordered]
    unique_series = [("unique_target_pairs", "不同目标对", "#0072B2"),
                     ("unique_target_sides", "不同目标侧", "#D55E00"),
                     ("unique_evaluated_target_sides", "实际评价过的目标侧", "#009E73"),
                     ("unique_routes_attempted", "涉及的不同路线", "#5B1387"),
                     ("unique_routes_evaluated", "评价过的不同路线", "#E69F00"),
                     ("unique_routes_touched_by_a_move", "被执行动作改动的路线", "#B2182B")]
    fig, axes = plt.subplots(1, 2, figsize=(14.4, 5.6))
    ax = axes[0]
    width = .13
    missing_groups = set()
    for index, (key, label, color) in enumerate(unique_series):
        values = [coverage(r, key) for r in ordered]
        for row, value in zip(ordered, values):
            if value is None:
                missing_groups.add(row.get("group"))
        drawn = [0.0 if v is None else v for v in values]
        ax.bar(xs + (index - (len(unique_series) - 1) / 2) * width, drawn, width, label=label,
               color=color, edgecolor="black", linewidth=.3)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=90, fontsize=7.0)
    ax.set_ylabel("计数")
    ax.set_title("（a）覆盖广度：目标对 / 目标侧 / 路线", fontsize=11)
    ax.legend(loc="upper right", fontsize=7.6, ncol=2)
    ax2 = axes[1]
    width2 = .38
    repeated = [coverage(r, "repeated_target_attempts") for r in ordered]
    maxper = [coverage(r, "max_attempts_on_one_route") for r in ordered]
    for row, value in zip(ordered, repeated + maxper):
        if value is None:
            missing_groups.add(row.get("group"))
    ax2.bar(xs - width2 / 2, [0.0 if v is None else v for v in repeated], width2,
            label="重复访问的目标对次数", color="#B2182B", edgecolor="black", linewidth=.3)
    ax2.bar(xs + width2 / 2, [0.0 if v is None else v for v in maxper], width2,
            label="单条路线被访问的最大次数", color="#4D4D4D", edgecolor="black", linewidth=.3)
    for x, (a, b) in enumerate(zip(repeated, maxper)):
        if a is not None:
            ax2.annotate(fmt_int(a), xy=(x - width2 / 2, a), xytext=(0, 3),
                         textcoords="offset points", ha="center", fontsize=7.0, rotation=90)
        if b is not None:
            ax2.annotate(fmt_int(b), xy=(x + width2 / 2, b), xytext=(0, 3),
                         textcoords="offset points", ha="center", fontsize=7.0, rotation=90)
    ax2.set_xticks(xs)
    ax2.set_xticklabels(labels, rotation=90, fontsize=7.0)
    ax2.set_ylabel("次数")
    ax2.set_title("（b）重复访问：同一目标对与同一路线", fontsize=11)
    ax2.legend(loc="upper right", fontsize=8.2)
    fig.suptitle("%s 轮：调度覆盖面板（回答“同一预算被花在哪里”）" % ROUND, fontsize=12)
    fig.text(.01, -.22,
             "数据来源：%s 的 %s，以及 summary_%s.json 行内 coverage 子对象的 "
             "unique_target_pairs、unique_target_sides、unique_evaluated_target_sides、"
             "unique_routes_attempted、unique_routes_evaluated、unique_routes_touched_by_a_move、"
             "repeated_target_attempts、max_attempts_on_one_route。%s"
             % (CSV_SOURCE, "、".join(columns_used), ROUND,
                ("coverage 子对象缺失的组（%d 个，其柱子缺失而不是 0）：%s"
                 % (len(missing_groups), "、".join(sorted(missing_groups))))
                if missing_groups else "所有已完成组的 coverage 子对象都完整。"),
             fontsize=8.6, color="#555555", va="top")
    save(fig, "%s_f6_coverage" % ROUND,
         title="调度覆盖：不同目标对/目标侧/路线与重复访问",
         columns=columns_used,
         sub_objects=["coverage.unique_target_pairs", "coverage.unique_target_sides",
                      "coverage.unique_evaluated_target_sides",
                      "coverage.unique_routes_attempted", "coverage.unique_routes_evaluated",
                      "coverage.unique_routes_touched_by_a_move",
                      "coverage.repeated_target_attempts", "coverage.max_attempts_on_one_route"],
         notes="coverage 只存在于 summary_<round>.json；comparison.csv 提供每一行的键",
         rows_used=len(ordered))


def figure_failures(rows, payload, columns_used):
    ordered = sorted(rows, key=lambda r: (text(r, "strategy") or "", text(r, "mode") or "",
                                          integer(r, "budget") or 0, text(r, "group") or ""))
    xs = np.arange(len(ordered))
    labels = [group_label(r) for r in ordered]
    fig, axes = plt.subplots(1, 3, figsize=(16.0, 5.8))
    ax = axes[0]
    width = .38
    not_evaluated = [num(r, "not_evaluated_candidates") for r in ordered]
    deferred_totals = []
    for row in ordered:
        block = row.get("coverage") or {}
        per_class = block.get("elevation_state_class_deferred") or {}
        total = None
        if isinstance(per_class, dict) and per_class:
            if all(isinstance(per_class.get(c), (int, float)) for c in LAYER_CLASSES):
                total = float(sum(per_class.get(c) for c in LAYER_CLASSES))
        deferred_totals.append(total)
    ax.bar(xs - width / 2, [0.0 if v is None else v for v in not_evaluated], width,
           label="NOT_EVALUATED 候选数", color="#B2182B", edgecolor="black", linewidth=.3)
    ax.bar(xs + width / 2, [0.0 if v is None else v for v in deferred_totals], width,
           label="deferred 前缀无胜出目标数", color="#E69F00", edgecolor="black", linewidth=.3)
    for x, (a, b) in enumerate(zip(not_evaluated, deferred_totals)):
        if a is not None and a:
            ax.annotate(fmt_int(a), xy=(x - width / 2, a), xytext=(0, 3),
                        textcoords="offset points", ha="center", fontsize=7.0, rotation=90)
        if b is not None and b:
            ax.annotate(fmt_int(b), xy=(x + width / 2, b), xytext=(0, 3),
                        textcoords="offset points", ha="center", fontsize=7.0, rotation=90)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=90, fontsize=7.0)
    ax.set_ylabel("计数")
    ax.set_title("（a）未评价候选与 deferred 前缀", fontsize=10.5)
    ax.legend(loc="upper right", fontsize=8.0)

    ax2 = axes[1]
    bottom = np.zeros(len(ordered))
    for color_index, state in enumerate(LAYER_CLASSES):
        heights = []
        for row in ordered:
            block = (row.get("coverage") or {}).get("elevation_state_class_deferred") or {}
            value = block.get(state) if isinstance(block, dict) else None
            heights.append(0.0 if not isinstance(value, (int, float)) else float(value))
        ax2.bar(xs, heights, .62, bottom=bottom, label=state, color=CLASS_COLORS[state],
                edgecolor="black", linewidth=.3)
        for x, (height, base) in enumerate(zip(heights, bottom)):
            if height:
                ax2.annotate(fmt_int(height), xy=(x, base + height / 2), ha="center",
                             va="center", fontsize=7.2, color="white")
        bottom += np.array(heights)
    ax2.set_xticks(xs)
    ax2.set_xticklabels(labels, rotation=90, fontsize=7.0)
    ax2.set_ylabel("deferred 目标数")
    if not any(bottom):
        ax2.set_ylim(0, 1)
        ax2.annotate("全部为 0：本轮没有任何 deferred 前缀目标", xy=(.5, .62),
                     xycoords="axes fraction", ha="center", fontsize=9, color="#666666")
    ax2.set_title("（b）deferred 前缀按抬升状态类（UU/UE/EE）", fontsize=10.5)
    ax2.legend(loc="upper right", fontsize=8.2)

    ax3 = axes[2]
    reasons = Counter(text(r, "stop_reason") or "UNKNOWN" for r in ordered)
    names = sorted(reasons, key=lambda k: (-reasons[k], k))
    ax3.barh(range(len(names)), [reasons[n] for n in names], .6,
             color=["#B2182B" if n.startswith("CANDIDATE_BUDGET") else "#0072B2"
                    for n in names], edgecolor="black", linewidth=.4)
    for y, name in enumerate(names):
        ax3.annotate(str(reasons[name]), xy=(reasons[name], y), xytext=(3, 0),
                     textcoords="offset points", va="center", fontsize=8.6)
        members = [text(r, "group") for r in ordered if (text(r, "stop_reason") or "UNKNOWN") == name]
        shown = "、".join(members[:3]) + ("　等 %d 组" % len(members) if len(members) > 3 else "")
        ax3.annotate(shown, xy=(reasons[name], y), xytext=(24, 0), textcoords="offset points",
                     va="center", fontsize=6.6, color="#666666")
    ax3.set_yticks(range(len(names)))
    ax3.set_yticklabels(names, fontsize=8.6)
    ax3.invert_yaxis()
    ax3.set_xlabel("组数")
    ax3.set_xlim(0, max(reasons.values()) + max(1.4, 0.9 * len(ordered)))
    ax3.set_title("（c）停止原因分布", fontsize=10.5)
    fig.suptitle("%s 轮：未评价、deferred 与停止原因（失败计数不折成成功率）" % ROUND, fontsize=12)
    fig.text(.01, -.10,
             "数据来源：%s 的 %s（not_evaluated_candidates、stop_reason），以及 summary_%s.json 行内 "
             "coverage 子对象的 elevation_state_class_deferred（UU/UE/EE）。NOT_EVALUATED 表示候选"
             "已生成但未获得评价机会（预算或 K 前缀），不是“被拒绝”；deferred 表示前缀评价完但仍有"
             "未评价候选。" % (CSV_SOURCE, "、".join(columns_used), ROUND), fontsize=8.6,
             color="#555555", va="top")
    save(fig, "%s_f7_failures_and_stops" % ROUND,
         title="未评价候选数、deferred 前缀（按 UU/UE/EE）与停止原因分布",
         columns=columns_used,
         sub_objects=["coverage.elevation_state_class_deferred.UU",
                      "coverage.elevation_state_class_deferred.UE",
                      "coverage.elevation_state_class_deferred.EE"],
         notes="NOT_EVALUATED 与拒绝分开记账；deferred 前缀不是 ALL_CANDIDATES_REJECTED",
         rows_used=len(ordered))


def figure_stop_and_details(rows, payload, columns_used):
    """One compact table-like panel: the per-group decision-relevant numbers."""
    ordered = sorted(rows, key=lambda r: (text(r, "strategy") or "", text(r, "mode") or "",
                                          integer(r, "budget") or 0, text(r, "group") or ""))
    columns = ["group", "strategy", "mode", "budget", "start_kind", "control",
               "initial_collision_pairs", "final_collision_pairs", "net_collision_reduction",
               "accepted_moves", "candidate_evaluations", "evaluations_per_action",
               "net_reduction_per_evaluation", "recheck_verdict"]
    cell_text = []
    for row in ordered:
        line = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, float):
                value = fmt_num(value, 4)
            elif isinstance(value, int):
                value = fmt_int(value)
            line.append("null" if value is None else str(value))
        cell_text.append(line)
    fig, ax = plt.subplots(figsize=(max(11.0, 1.05 * len(columns) + 0.55 * len(ordered)), 1.2
                                    + 0.30 * len(ordered)))
    ax.axis("off")
    table = ax.table(cellText=cell_text, colLabels=columns, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(7.6)
    table.scale(1.0, 1.25)
    for (row_index, column_index), cell in table.get_celld().items():
        cell.set_edgecolor("#888888")
        if row_index == 0:
            cell.set_facecolor("#EFEFEF")
            cell.set_text_props(fontweight="bold")
        elif column_index == 0:
            cell.set_facecolor("#F7F7F7")
    ax.set_title("%s 轮逐组汇总表（comparison.csv 的全部已完成组；单位与列名一致）" % ROUND,
                 fontsize=12)
    fig.text(.01, .005,
             "数据来源：%s 的 %s。缺失值为 null；本表不做任何派生计算。"
             % (CSV_SOURCE, "、".join(columns)), fontsize=8.6, color="#555555", va="top")
    save(fig, "%s_f8_group_table" % ROUND,
         title="逐组汇总表（comparison.csv 已完成组的原样读数）",
         columns=columns, sub_objects=[], notes="表格只重排 comparison.csv 的读数，不做派生",
         rows_used=len(ordered))


def main():
    if not ROUND_DIR.is_dir():
        raise SystemExit("round directory missing: %s" % ROUND_DIR)
    resolved_font = setup_fonts()
    payload, rows, fieldnames = load_round()
    FIGDIR.mkdir(parents=True, exist_ok=True)
    print("font: %s" % resolved_font, flush=True)
    print("round=%s completed rows in comparison.csv=%d (groups_expected=%s, not finished=%s)"
          % (ROUND, len(rows), payload.get("groups_expected"),
             payload.get("groups_not_finished")), flush=True)
    if not rows:
        print("no completed group in %s: no figure written" % ROUND, flush=True)
        return 0
    strategies = sorted({text(r, "strategy") or "?" for r in rows})
    print("strategies=%s" % ",".join(strategies), flush=True)
    if payload.get("skipped_groups"):
        print("not plotted (not finished): %s"
              % ",".join(entry["group"] for entry in payload["skipped_groups"]), flush=True)
    figure_pairs_vs_budget(rows, payload, ["budget", "strategy", "mode", "start_kind",
                                           "final_collision_pairs", "initial_collision_pairs"])
    figure_same_budget_nr(rows, payload, ["budget", "strategy", "mode", "start_kind",
                                          "final_collision_pairs"])
    figure_actions(rows, payload, ["group", "strategy", "mode", "budget",
                                   "first_elevations", "relocations", "returns",
                                   "first_elevation_net_reduction", "relocation_net_reduction",
                                   "return_net_reduction", "total_old_collisions_removed",
                                   "total_new_collisions_created"])
    figure_costs(rows, payload, ["group", "strategy", "mode", "budget",
                                 "stage_length_delta_mm", "final_extra_length_vs_planar_mm",
                                 "final_transition_count", "final_elevated_route_count"])
    figure_efficiency(rows, payload, ["group", "strategy", "mode", "budget",
                                      "evaluations_per_action", "net_reduction_per_evaluation",
                                      "candidate_evaluations", "accepted_moves"])
    figure_coverage(rows, payload, ["group", "strategy", "mode", "budget"])
    figure_failures(rows, payload, ["group", "strategy", "mode", "budget",
                                    "not_evaluated_candidates", "stop_reason"])
    figure_stop_and_details(rows, payload, list(fieldnames))
    combined = dict(round=ROUND, generator=GENERATOR, font=resolved_font,
                    generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    inputs=dict(comparison_csv=CSV_SOURCE, summary_json=SUMMARY_SOURCE),
                    rows_used=len(rows),
                    groups_expected=payload.get("groups_expected"),
                    groups_not_finished=payload.get("groups_not_finished"),
                    not_plotted=[e["group"] for e in payload.get("skipped_groups", [])],
                    images=MANIFEST, style_source="outputs/3d_strategy_v4/512_full_layout/figures",
                    no_figure_numbers_embedded=True)
    path = FIGDIR / ("figures_manifest_%s.json" % ROUND)
    path.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote %s" % path, flush=True)
    print("FIGURES DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
