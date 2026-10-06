"""publication 数据加载层。

集中管理全部实验数据源（只读）。绘图与制表脚本一律通过本模块取数，
不得在脚本内硬编码实验结果数值。

数据源分四类：
1. 论文复现（OpticalWaveguideRouter2D/results 与 scratch）；
2. Step 12/13/14 二维优化（OpticalWaveguideRouter3D/outputs/opt2d*）；
3. 三维实验 step 9/10/11（outputs/step_*.json/csv）；
4. 论文印刷值（论文表 3-1 与正文数字），来源与引用记录见 PAPER_VALUES。

所有文件路径相对于项目根（OpticalWaveguideRouter3D）。
"""

from __future__ import annotations

import ast
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from pubstyle import PROJECT_ROOT, ROUTER2D_ROOT

OUTPUTS = PROJECT_ROOT / "outputs"
OUT2D = OUTPUTS / "opt2d"
OUT2D13 = OUTPUTS / "opt2d_step13"
OUT2D13C = OUTPUTS / "opt2d_step13_constrained"
OUT2D13F = OUTPUTS / "opt2d_step13_fix"
OUT2D14 = OUTPUTS / "opt2d_step14"

CHANNELS = (256, 512)

# ---------------------------------------------------------------------------
# 论文印刷值（引用记录）
# ---------------------------------------------------------------------------
# 来源：
# * 论文表 3-1（90° 弯曲损耗，p19）与正文"直波导 0.05 dB/cm、90° 交叉 30 个约
#   0.05 dB"：见 OpticalWaveguideRouter2D/docs/loss_model_reconstruction_report.md
#   第 7 节与 OpticalWaveguideRouter2D/results/*_summary.json 的 thesis_* 字段；
# * 256 通道 mean 5.3 / max 6.4 dB（论文 4.2 节）：summary json thesis_mean/max；
# * 512 通道 R5 mean 5.5 / max 6.6 dB（论文 4.1 节）：同上；
# * 512 通道 R4 mean 9.8 / max 11.0 dB（论文 4.3 节）：同上；
# * 最小交叉角 35°（256）/ 14°（512）：论文 4.1/4.2 节，正文引用记录于
#   OpticalWaveguideRouter2D/docs/migration_report.md。
PAPER_VALUES = {
    "bend_90_db": {"2": 7.94, "3": 6.81, "4": 4.59, "5": 2.39, "6": 1.90},
    "cases": {
        "256": {"mean_loss_db": 5.3, "max_loss_db": 6.4, "label": "256 通道（论文 4.2）"},
        "512": {"mean_loss_db": 5.5, "max_loss_db": 6.6, "label": "512 通道 R5（论文 4.1）"},
        "512_R4": {"mean_loss_db": 9.8, "max_loss_db": 11.0, "label": "512 通道 R4（论文 4.3）"},
    },
    "min_crossing_angle_deg": {"256": 35.0, "512": 14.0},
    "straight_loss_db_per_cm": 0.05,
    "crossing_anchor": "90° 时 30 个交叉约 0.05 dB（论文 3.3.2 节）",
}

# ---------------------------------------------------------------------------
# 通用读取
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. 论文复现（2D 项目，只读）
# ---------------------------------------------------------------------------

REPRO_TAGS = {
    "256_R5": ("256", 5.0),
    "512_R5": ("512", 5.0),
    "512_R2": ("512", 2.0),
    "512_R3": ("512", 3.0),
    "512_R4": ("512", 4.0),
}


@lru_cache(maxsize=None)
def repro_route_frame(tag: str) -> pd.DataFrame:
    """逐路损耗明细表（fiberBoard*_loss.xlsx）。64 列中 loss 相关 15 列。"""
    if tag == "256_R5":
        path = ROUTER2D_ROOT / "results" / "fiberBoard256_loss.xlsx"
    elif tag == "512_R5":
        path = ROUTER2D_ROOT / "results" / "fiberBoard512_loss.xlsx"
    else:
        radius = tag.split("_R")[1]
        path = ROUTER2D_ROOT / "results" / f"fiberBoard512_loss_R{radius}.xlsx"
    frame = pd.read_excel(path)
    frame["crossing_angles_list"] = frame["crossing_angles_deg"].apply(
        lambda text: ast.literal_eval(text) if isinstance(text, str) else []
    )
    frame["bend_angles_list"] = frame["bend_angles_deg"].apply(
        lambda text: ast.literal_eval(text) if isinstance(text, str) else []
    )
    return frame


@lru_cache(maxsize=None)
def repro_summary(tag: str) -> dict:
    """复现 summary json。"""
    name = {
        "256_R5": "fiberBoard256_loss_summary.json",
        "512_R5": "fiberBoard512_loss_summary.json",
        "512_R2": "fiberBoard512_loss_R2_summary.json",
        "512_R3": "fiberBoard512_loss_R3_summary.json",
        "512_R4": "fiberBoard512_loss_R4_summary.json",
    }[tag]
    return _read_json(ROUTER2D_ROOT / "results" / name)


def repro_percentile(tag: str, q: float) -> float:
    """逐路总损耗的百分位（本次分析实算，不落盘）。"""
    losses = repro_route_frame(tag)["total_loss_db"].to_numpy()
    return float(np.percentile(losses, q))


def repro_crossing_angles(tag: str) -> np.ndarray:
    """全部逐路交叉角条目（同一物理交叉按逐路各计一次，与损耗累计同口径）。"""
    frame = repro_route_frame(tag)
    return np.concatenate([np.asarray(a, dtype=float) for a in frame["crossing_angles_list"]]) if len(frame) else np.array([])


def repro_legacy_json(tag: str) -> dict:
    """原版字节码（含全 0 占位交叉表）的真实产物：legacy512_R5.json 等。"""
    return _read_json(ROUTER2D_ROOT / "scratch" / "legacy_loss" / f"legacy{tag}.json")


@lru_cache(maxsize=None)
def bend_model_density(radius_mm: float) -> float:
    """从 2D 项目 loss_model.py 读取的弯曲损耗密度（dB/mm），真实模型计算。"""
    if str(ROUTER2D_ROOT) not in sys.path:
        sys.path.insert(0, str(ROUTER2D_ROOT))
    import loss_model  # noqa: PLC0415

    return loss_model.bend_loss_density_db_per_mm(radius_mm)


def bend_model_90_db(radius_mm: float) -> float:
    """复刻的 90° 弯曲损耗（dB），由模型公式计算（非硬编码）。"""
    import math

    return bend_model_density(radius_mm) * radius_mm * math.pi / 2


def crossing_model_table() -> pd.DataFrame:
    """论文图 3-12 数字化交叉损耗表（原始数字化值，每 30 交叉）。"""
    return _read_csv(ROUTER2D_ROOT / "data" / "crossing_loss_from_thesis_fig3_12.csv")


def crossing_sensitivity() -> dict[str, dict]:
    """512 R5 三种交叉口径的固定几何复算（与 loss_model_reconstruction_report §7 一致）。

    返回 {"A": {"mean":..., "max":..., "note":...}, "B": ..., "C": ...}。
    非交叉部分取自主口径（total - 主口径交叉），三种口径共用。
    """
    import numpy as np

    frame = repro_route_frame("512_R5")
    table = crossing_model_table().set_index("angle_deg")["loss_db_per_30_crossings"]
    anchor_scale = 0.05 / float(table.loc[90])
    counts = frame["crossing_count"].to_numpy()
    angle_lists = frame["crossing_angles_list"]

    def per_route(fn):
        return np.array([sum(fn(float(a)) for a in lst) for lst in angle_lists])

    main_cross = per_route(lambda a: float(table.loc[int(a)]) * anchor_scale / 30.0)
    non_crossing = frame["total_loss_db"].to_numpy() - main_cross
    scopes = {
        "A": ("全部按 90°（0.05 dB/30），忽略角度依赖", counts * (0.05 / 30.0)),
        "B": ("图 3-12 数字化 + 90° 锚定（项目主口径）", main_cross),
        "C": ("图 3-12 原始值（不锚定）", per_route(lambda a: float(table.loc[int(a)]) / 30.0)),
    }
    result = {}
    for key, (note, cross) in scopes.items():
        total = non_crossing + cross
        result[key] = {"note": note, "mean": float(total.mean()), "max": float(total.max())}
    return result


# ---------------------------------------------------------------------------
# 2. Step 12：A/B/C/D
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def step12_comparison(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D / str(channels) / "comparison.csv")


@lru_cache(maxsize=None)
def step12_summary(channels: int, scheme: str) -> dict:
    return _read_json(OUT2D / str(channels) / scheme / "summary.json")


@lru_cache(maxsize=None)
def step12_per_route(channels: int, scheme: str) -> pd.DataFrame:
    return _read_csv(OUT2D / str(channels) / scheme / "per_route.csv")


@lru_cache(maxsize=None)
def step12_sensitivity(channels: int) -> dict:
    """消融原始 json（候选数/顺序/惩罚/半径策略）。"""
    return _read_json(OUT2D / str(channels) / "sensitivity.json")


def step12_sensitivity_frame(channels: int) -> pd.DataFrame:
    data = step12_sensitivity(channels)
    frame = pd.DataFrame(data).T
    frame.index.name = "config"
    return frame.reset_index()


@lru_cache(maxsize=None)
def step12_sensitivity_summary(channels: int, config: str) -> dict:
    return _read_json(OUT2D / str(channels) / "sensitivity" / config / "summary.json")


# ---------------------------------------------------------------------------
# 3. Step 13（旧版 / 补修版 / 受约束 / 敏感性）
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def step13_comparison(channels: int, *, fixed: bool = False) -> pd.DataFrame:
    root = OUT2D13F if fixed else OUT2D13
    return _read_csv(root / str(channels) / "comparison.csv")


@lru_cache(maxsize=None)
def step13_acceptance(channels: int, *, fixed: bool = False) -> dict:
    root = OUT2D13F if fixed else OUT2D13
    return _read_json(root / str(channels) / "acceptance.json")


@lru_cache(maxsize=None)
def step13_worst_tracking(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D13 / str(channels) / "worst_route_tracking.csv")


@lru_cache(maxsize=None)
def step13_constrained(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D13C / str(channels) / "constrained_comparison.csv")


@lru_cache(maxsize=None)
def step13_fix_per_route_delta(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D13F / str(channels) / "per_route_delta.csv")


@lru_cache(maxsize=None)
def step13_fix_sensitivity(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D13F / str(channels) / "sensitivity.csv")


@lru_cache(maxsize=None)
def step13_fix_radius_compare(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D13F / str(channels) / "radius_compare.csv")


@lru_cache(maxsize=None)
def step13_fix_penalty_ablation(channels: int, scheme: str) -> pd.DataFrame:
    return _read_csv(OUT2D13F / str(channels) / f"penalty_ablation_{scheme}.csv")


@lru_cache(maxsize=None)
def step13_per_route(channels: int, scheme: str, root: str = "step13") -> pd.DataFrame:
    """root ∈ {step13, fix}；per_route.csv 含解析几何重建所需全部字段。"""
    base = {"step13": OUT2D13, "fix": OUT2D13F}[root]
    return _read_csv(base / str(channels) / scheme / "per_route.csv")


@lru_cache(maxsize=None)
def step13_contact_events(channels: int, scheme: str) -> pd.DataFrame:
    return _read_csv(OUT2D13F / str(channels) / scheme / "contact_events.csv")


# ---------------------------------------------------------------------------
# 4. Step 14（冻结半径、保护、压力情景、诊断）
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def step14_comparison(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / "comparison.csv")


@lru_cache(maxsize=None)
def step14_acceptance(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / "acceptance.csv")


@lru_cache(maxsize=None)
def step14_margins(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / "protection_margins.csv")


@lru_cache(maxsize=None)
def step14_protection_set(channels: int) -> dict:
    return _read_json(OUT2D14 / str(channels) / "protection_set.json")


@lru_cache(maxsize=None)
def step14_protection_routes(channels: int, scheme: str) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / scheme / "protection_routes.csv")


@lru_cache(maxsize=None)
def step14_sensitivity(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / "sensitivity.csv")


@lru_cache(maxsize=None)
def step14_attempts(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / "optimize_attempts_base.csv")


@lru_cache(maxsize=None)
def step14_optimize_record(channels: int) -> dict:
    return _read_json(OUT2D14 / str(channels) / "optimize_record.json")


@lru_cache(maxsize=None)
def step14_radius_freeze(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / "radius_freeze_check.csv")


@lru_cache(maxsize=None)
def step14_references(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / "references.csv")


@lru_cache(maxsize=None)
def step14_per_route(channels: int, scheme: str) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / scheme / "per_route.csv")


@lru_cache(maxsize=None)
def step14_probe_summary(channels: int) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / "probe" / "probe_summary.csv")


@lru_cache(maxsize=None)
def step14_probe_attempts(channels: int, variant: str) -> pd.DataFrame:
    return _read_csv(OUT2D14 / str(channels) / "probe" / f"attempts_{variant}.csv")


# ---------------------------------------------------------------------------
# 5. 三维实验（step 9/10/11）
# ---------------------------------------------------------------------------


def step9e_summary() -> dict:
    return _read_json(OUTPUTS / "step_9_e_sequential_elevation_summary.json")


def step9e_steps() -> pd.DataFrame:
    return _read_csv(OUTPUTS / "step_9_e_sequential_elevation_steps.csv")


def step9f_two_layer_summary() -> dict:
    return _read_json(OUTPUTS / "step_9_f_two_layer_control_summary.json")


def step9f_three_layer_summary() -> dict:
    return _read_json(OUTPUTS / "step_9_f_three_layer_summary.json")


def step9f_comparison() -> dict:
    return _read_json(OUTPUTS / "step_9_f_comparison.json")


def step9f_layer_usage() -> dict:
    return _read_json(OUTPUTS / "step_9_f_layer_usage.json")


def step10_summary() -> dict:
    return _read_json(OUTPUTS / "step_10_fixed_1024_summary.json")


def step9d_probe_summary() -> dict:
    return _read_json(OUTPUTS / "step_9_d_probe_summary.json")


def step9d_local_validation() -> list:
    return _read_json(OUTPUTS / "step_9_d_local_validation.json")


def step10_board_capacity() -> dict:
    return _read_json(OUTPUTS / "step_10_fixed_1024_board_capacity_check.json")


def step11_summary() -> dict:
    return _read_json(OUTPUTS / "step_11_visualization_summary.json")


def step8_5_physical_summary() -> dict:
    return _read_json(OUTPUTS / "step_8_5_legacy_512_physical_summary.json")


def step8_5_loss_summary() -> dict:
    return _read_json(OUTPUTS / "step_8_5_legacy_512_loss_summary.json")


@lru_cache(maxsize=1)
def step10_final_state() -> dict:
    """1024 三维终态（3.4 MB，惰性加载）。"""
    return _read_json(OUTPUTS / "step_10_fixed_1024_final_route_state.json")


@lru_cache(maxsize=1)
def step10_initial_geometry() -> dict:
    """1024 初始几何（2.1 MB，全部 z=0，惰性加载）。"""
    return _read_json(OUTPUTS / "step_10_fixed_1024_initial_geometry.json")


# ---------------------------------------------------------------------------
# 6. 几何重建（复用 src.opt2d 模块，纯解析计算，不运行实验）
# ---------------------------------------------------------------------------

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import ArcSegment2D, LineSegment2D  # noqa: E402
from src.opt2d.freeform import FreeformParams, build_freeform_geometry  # noqa: E402
from src.opt2d.smoothing import RouteSpec, build_route_geometry  # noqa: E402


def rebuild_route_segments(row) -> list:
    """从 per_route.csv 的一行重建解析几何（Line/Arc 序列）。

    只读复用 src.opt2d.smoothing / freeform 的几何构造；失败返回空列表
    （调用方负责统计与报告不一致处）。
    """
    kind = str(row.get("geometry", "u") or "u")
    try:
        if kind == "freeform":
            params = FreeformParams(
                route_id=int(row["route_id"]),
                sx=float(row["sx_mm"]),
                sy=float(row["sy_mm"]),
                lx=float(row["lx_mm"]),
                ly=float(row["ly_mm"]),
                radius=float(row["radius_mm"]),
                alpha_deg=float(row["alpha_deg"] or 0.0),
                t0_fraction=float(row["t0_fraction"] if row["t0_fraction"] == row["t0_fraction"] else 0.5),
            )
            return build_freeform_geometry(params)
        spec = RouteSpec(
            route_id=int(row["route_id"]),
            sx=float(row["sx_mm"]),
            sy=float(row["sy_mm"]),
            lx=float(row["lx_mm"]),
            ly=float(row["ly_mm"]),
            track_y=float(row["track_y_mm"]),
            radius=float(row["radius_mm"]),
        )
        return build_route_geometry(spec)
    except (ValueError, KeyError):
        return []


def segment_polyline(segment, samples: int = 96):
    """把解析线段采样成折线坐标（仅用于绘图）。"""
    from math import atan2, cos, pi, sin

    if isinstance(segment, LineSegment2D):
        return [segment.start.x, segment.end.x], [segment.start.y, segment.end.y]
    start = segment.start
    angle0 = atan2(start.y - segment.center.y, start.x - segment.center.x)
    radius = ((start.x - segment.center.x) ** 2 + (start.y - segment.center.y) ** 2) ** 0.5
    xs, ys = [], []
    count = max(8, int(abs(segment.sweep_rad) / (2 * pi) * samples) + 2)
    for k in range(count + 1):
        angle = angle0 + segment.sweep_rad * k / count
        xs.append(segment.center.x + radius * cos(angle))
        ys.append(segment.center.y + radius * sin(angle))
    return xs, ys


def per_route_crossing_events(channels: int, scheme: str, root: str = "step13") -> pd.DataFrame:
    base = {"step13": OUT2D13, "fix": OUT2D13F}[root]
    return _read_csv(base / str(channels) / scheme / "crossing_events.csv")
