"""统一科研绘图风格模块（publication）。

集中管理：字体、颜色、方法名称映射、尺寸、线宽、marker、刻度、图例、
DPI 与导出路径。所有 publication 图脚本只通过本模块取样式与保存函数，
不得自行设置字体/颜色。

版面依据：thesis 模板（李昊伦_本科毕业论文_格式模板.docx）
A4 210×297 mm、四边 30 mm → 版心宽 150 mm ≈ 5.91 in。
英文/数字 Times New Roman，中文宋体（SimSun）作为 fallback，
数学公式 mathtext stix（与 Times 兼容）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PUBLICATION_DIR = PROJECT_ROOT / "publication"
FIGURE_DIR = PUBLICATION_DIR / "figures"
TABLE_DIR = PUBLICATION_DIR / "tables"
MANIFEST_DIR = PUBLICATION_DIR / "manifest"

# 2D 复现项目（只读）
ROUTER2D_ROOT = PROJECT_ROOT.parent / "OpticalWaveguideRouter2D"

# ---------------------------------------------------------------------------
# 尺寸（英寸）
# ---------------------------------------------------------------------------

FULL_WIDTH = 5.90  # 版心全宽 150 mm
HALF_WIDTH = 2.87  # 半宽
ONE_THIRD_WIDTH = 1.85

FIG_SIZE = {
    "full": (FULL_WIDTH, 3.4),
    "full_tall": (FULL_WIDTH, 4.2),
    "full_short": (FULL_WIDTH, 2.6),
    "half": (HALF_WIDTH, 2.5),
    "third": (ONE_THIRD_WIDTH, 2.2),
}

# ---------------------------------------------------------------------------
# 字体
# ---------------------------------------------------------------------------

FONT_SIZE = 9.0          # 图内基础字号（pt）；最小 8 pt
FONT_SIZE_SMALL = 8.0
FONT_SIZE_LABEL = 9.0
FONT_SIZE_TICK = 8.5
LINE_WIDTH = 1.1
MARKER_SIZE = 4.0
AXES_LINE_WIDTH = 0.7
GRID_ALPHA = 0.28

CJK_FALLBACK = ["SimSun", "Microsoft YaHei", "SimHei"]


def apply_style() -> None:
    """全局 rcParams：英文/数字 Times New Roman，中文宋体 fallback。"""
    plt.rcParams.update(
        {
            # 只写成族名列表时 matplotlib 才按字符回退：
            # 英文/数字 Times New Roman，中文回退 SimSun（宋体）。
            "font.family": ["Times New Roman", "SimSun", "Microsoft YaHei", "DejaVu Sans"],
            "font.serif": ["Times New Roman", "SimSun", "Microsoft YaHei", "DejaVu Serif"],
            "font.sans-serif": ["Times New Roman", "SimSun", "Microsoft YaHei", "DejaVu Sans"],
            "mathtext.fontset": "stix",
            "axes.unicode_minus": False,
            "font.size": FONT_SIZE,
            "axes.labelsize": FONT_SIZE_LABEL,
            "axes.titlesize": FONT_SIZE,
            "xtick.labelsize": FONT_SIZE_TICK,
            "ytick.labelsize": FONT_SIZE_TICK,
            "legend.fontsize": FONT_SIZE_SMALL,
            "figure.dpi": 120,
            "savefig.dpi": 400,
            "axes.linewidth": AXES_LINE_WIDTH,
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "axes.edgecolor": "#333333",
            "axes.labelcolor": "black",
            "text.color": "black",
            "xtick.color": "#333333",
            "ytick.color": "#333333",
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.major.size": 2.6,
            "ytick.major.size": 2.6,
            "xtick.minor.size": 1.5,
            "ytick.minor.size": 1.5,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
            "figure.autolayout": False,
            "grid.linewidth": 0.5,
            "grid.alpha": GRID_ALPHA,
            "lines.linewidth": LINE_WIDTH,
            "lines.markersize": MARKER_SIZE,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


apply_style()

# ---------------------------------------------------------------------------
# 颜色（Okabe–Ito 色盲友好调色板 + 中性灰）
# ---------------------------------------------------------------------------

PALETTE = {
    "blue": "#0072B2",
    "sky": "#56B4E9",
    "green": "#009E73",
    "yellow": "#F0E442",
    "orange": "#E69F00",
    "vermillion": "#D55E00",
    "reddish_purple": "#CC79A7",
    "gray": "#8C8C8C",
    "dark_gray": "#4D4D4D",
    "black": "#000000",
}

# 分量颜色（全线统一）：直线 / 弯曲 / 交叉
COMPONENT_STYLE = {
    "straight": {"label": "直线传播", "color": "#9ecae1", "edge": "#6baed6"},
    "bend": {"label": "弯曲", "color": "#fdae6b", "edge": "#e6550d"},
    "crossing": {"label": "交叉", "color": "#a1d99b", "edge": "#31a354"},
}

# 每个方案在全部图中使用同一颜色/名称/marker/线型
@dataclass(frozen=True)
class MethodStyle:
    display: str          # 中文显示名
    color: str
    marker: str
    linestyle: str = "-"

    def line_kw(self, **extra):
        kw = dict(
            color=self.color,
            marker=self.marker,
            linestyle=self.linestyle,
            linewidth=LINE_WIDTH,
            markersize=MARKER_SIZE,
            label=self.display,
        )
        kw.update(extra)
        return kw

    def bar_kw(self, **extra):
        kw = dict(color=self.color, edgecolor="white", linewidth=0.5, label=self.display)
        kw.update(extra)
        return kw


METHODS: dict[str, MethodStyle] = {
    # ---- 复现组 ----
    "thesis": MethodStyle("论文值", PALETTE["dark_gray"], "s", "--"),
    "repro": MethodStyle("复现值", PALETTE["blue"], "o", "-"),
    # ---- Step 12 A/B/C/D ----
    "A": MethodStyle("A（原版 R5）", PALETTE["gray"], "o"),
    "B": MethodStyle("B（统一 R6）", PALETTE["orange"], "^"),
    "C": MethodStyle("C（候选优化）", PALETTE["green"], "s"),
    "D": MethodStyle("D（自适应半径）", PALETTE["vermillion"], "D"),
    # ---- Step 13 / 14 六方案（同一方案颜色跨图一致）----
    "R5U": MethodStyle("R5U（固定端点 R5）", PALETTE["blue"], "s"),
    "D0": MethodStyle("D0（优先 R6 回退）", PALETTE["orange"], "^"),
    "D56": MethodStyle("D56（自适应 R5/R6）", PALETTE["reddish_purple"], "v"),
    "F5": MethodStyle("F5（自由弯角 R5）", PALETTE["green"], "D"),
    "F56": MethodStyle("F56（自由弯角 R5/R6）", PALETTE["vermillion"], "P"),
    # ---- Step 14 配置 ----
    "base": MethodStyle("base（无附加惩罚）", PALETTE["gray"], "o"),
    "spacing": MethodStyle("spacing（间距惩罚）", PALETTE["blue"], "s"),
    "small": MethodStyle("small（小角惩罚）", PALETTE["orange"], "^"),
    "touch": MethodStyle("touch（接触惩罚）", PALETTE["reddish_purple"], "v"),
    "both": MethodStyle("both（间距+小角）", PALETTE["green"], "D"),
    "opt_base": MethodStyle("opt_base（保护性优化）", PALETTE["vermillion"], "P"),
    # ---- 三维实验 ----
    "step9e": MethodStyle("9-E 两层 30 目标", PALETTE["blue"], "o"),
    "step9f2": MethodStyle("9-F 两层 50 目标", PALETTE["orange"], "s"),
    "step9f3": MethodStyle("9-F 三层 50 目标", PALETTE["green"], "^"),
    "step10": MethodStyle("10 固定 1024 三层", PALETTE["vermillion"], "D"),
    # ---- 其他 ----
    "reference": MethodStyle("参照", "#666666", "x", "--"),
    "paper": MethodStyle("论文值", PALETTE["dark_gray"], "s", "--"),
    "reproduction": MethodStyle("复现值", PALETTE["blue"], "o", "-"),
}

# Step 13 / 14 六方案统一顺序
SIX_SCHEMES = ["A", "R5U", "D0", "D56", "F5", "F56"]
FOUR_SCHEMES = ["A", "B", "C", "D"]
STEP14_SCHEMES = ["base", "spacing", "small", "touch", "both", "opt_base"]

CHANNEL_COLORS = {256: PALETTE["blue"], 512: PALETTE["vermillion"]}
CHANNEL_MARKERS = {256: "o", 512: "s"}
CHANNEL_LABELS = {256: "256 通道", 512: "512 通道"}


def method(key: str) -> MethodStyle:
    if key not in METHODS:
        # 未登记的方案退回灰色，并在图中保留原名，避免静默错配色。
        return MethodStyle(key, PALETTE["gray"], "o")
    return METHODS[key]


# ---------------------------------------------------------------------------
# 保存与来源记录
# ---------------------------------------------------------------------------

_SAVED: list[dict] = []
_GLYPH_PROBLEMS: list[str] = []


class _GlyphProblemHandler(logging.Handler):
    """收集 matplotlib 的缺字形（dummy symbol）日志，防止豆腐块静默进入成图。"""

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "dummy symbol" in message or "Glyph" in message:
            if message not in _GLYPH_PROBLEMS:
                _GLYPH_PROBLEMS.append(message)


_glyph_handler = _GlyphProblemHandler()
logging.getLogger("matplotlib").addHandler(_glyph_handler)


def glyph_problems() -> list[str]:
    return list(_GLYPH_PROBLEMS)


def new_figure(key: str or tuple, **kwargs):
    """按 FIG_SIZE 键创建 figure。"""
    size = FIG_SIZE[key] if isinstance(key, str) else key
    return plt.figure(figsize=size, **kwargs)


def single_axes(key: str or tuple, **kwargs):
    """创建单子图 figure 并返回 (figure, axes)。"""
    fig = new_figure(key, **kwargs)
    return fig, fig.add_subplot(111)


def style_axis(ax, *, grid_axis: str = "y") -> None:
    ax.grid(True, axis=grid_axis, alpha=GRID_ALPHA, linewidth=0.5)
    ax.set_axisbelow(True)


def save_figure(
    fig,
    name: str,
    *,
    note: str = "",
    sources: list[str] | None = None,
) -> list[Path]:
    """输出 PDF / SVG / PNG（PNG 400 dpi），并登记来源备注。

    ``name`` 为不含扩展名的文件名；``note`` 写入 PNG 元数据，
    ``sources`` 供后续来源台账使用。
    """
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    # 各后端允许的 metadata 键不同：PDF 用 Subject，SVG 用 Description，PNG 用 Description。
    for ext, meta in (("pdf", {"Subject": note}), ("svg", {"Description": note})):
        path = FIGURE_DIR / f"{name}.{ext}"
        fig.savefig(path, bbox_inches="tight", pad_inches=0.02, metadata=meta if note else {})
        outputs.append(path)
    png_path = FIGURE_DIR / f"{name}.png"
    fig.savefig(
        png_path, bbox_inches="tight", pad_inches=0.02, dpi=400,
        metadata={"Description": note} if note else {},
    )
    outputs.append(png_path)
    plt.close(fig)
    _SAVED.append(
        {
            "figure": name,
            "outputs": [str(p.relative_to(PROJECT_ROOT)) for p in outputs],
            "note": note,
            "sources": sources or [],
        }
    )
    return outputs


def saved_figures() -> list[dict]:
    return list(_SAVED)


def reset_registry() -> None:
    _SAVED.clear()


def legend_ordered(ax, order: list[str] | None = None, **kwargs):
    """按给定方案顺序重排图例。"""
    handles, labels = ax.get_legend_handles_labels()
    if order:
        index = {label: i for i, label in enumerate(labels)}
        pairs = sorted(zip(handles, labels), key=lambda p: order.index(p[1]) if p[1] in order else 99)
        handles, labels = [p[0] for p in pairs], [p[1] for p in pairs]
    ax.legend(handles, labels, **kwargs)


def annotate_value(ax, x, y, text, *, dy=0.0, fontsize=FONT_SIZE_SMALL, **kwargs):
    ax.annotate(
        text,
        (x, y),
        xytext=(0, 3 + dy),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=fontsize,
        **kwargs,
    )
