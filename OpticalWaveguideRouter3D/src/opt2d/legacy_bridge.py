"""桥接 OpticalWaveguideRouter2D：复用其原版布线与损耗模型，不修改其文件。

2D 项目是原版 AutoRouter 的精确行为复现，它自己的 README 声明该仓库只作
行为参照。本模块因此只做只读复用：

* ``ensure_legacy_path()`` 把 2D 项目根加入 ``sys.path``；
* :func:`legacy_modules` 导入 ``problem_graph`` / ``wiring_rect_826`` /
  ``waveguide_calculator`` / ``loss_model``；
* :func:`run_legacy_rect` 用原版 ``plotter_rect`` 生成直角布线几何。

路径默认取 ``<毕业设计目录>/OpticalWaveguideRouter2D``（相对本文件推断），
可用环境变量 ``OPT2D_LEGACY_PROJECT`` 覆盖。重复调用是幂等的。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType

__all__ = [
    "legacy_project_root",
    "ensure_legacy_path",
    "legacy_modules",
    "run_legacy_rect",
    "default_pitch",
]

_DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "OpticalWaveguideRouter2D"

#: 原版 ``plotter_rect`` 会写 xlsx/pdf；实验统一写到本目录，绝不覆盖 2D
#: 项目 ``results/`` 里的原版输出。
DEFAULT_SCRATCH = Path(__file__).resolve().parents[2] / "outputs" / "opt2d" / "legacy_scratch"

_REQUIRED = ("problem_graph", "wiring_rect_826", "waveguide_calculator", "loss_model")


def legacy_project_root() -> Path:
    """返回 2D 项目根目录，缺失时抛出 ``FileNotFoundError``。"""
    override = os.environ.get("OPT2D_LEGACY_PROJECT")
    root = Path(override) if override else _DEFAULT_ROOT
    if not (root / "wiring_rect_826.py").is_file():
        raise FileNotFoundError(
            "找不到 OpticalWaveguideRouter2D 项目：%s（可用环境变量 "
            "OPT2D_LEGACY_PROJECT 指定）" % root
        )
    return root


def ensure_legacy_path() -> Path:
    """把 2D 项目根加入 ``sys.path``（幂等），返回该路径。"""
    root = str(legacy_project_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    return Path(root)


def legacy_modules() -> dict[str, ModuleType]:
    """导入并返回 2D 项目的关键模块。"""
    ensure_legacy_path()
    missing = [name for name in _REQUIRED if name not in sys.modules]
    modules: dict[str, ModuleType] = {}
    import importlib

    for name in _REQUIRED:
        modules[name] = importlib.import_module(name)
    del missing  # 仅为可读性：导入失败会自然抛出 ImportError
    return modules


def default_pitch(channels: int) -> float:
    """原版 2D 参数表给出的标称边缘间隔（mm）。"""
    return {256: 0.25, 512: 0.125}.get(channels, 0.25)


def legacy_ports(
    channels: int,
    *,
    input_path: str | Path | None = None,
    save_folder: str | Path | None = None,
    line_width: float = 0.05,
    pitch: float | None = None,
    height: int = 150,
):
    """只运行原版端口排布 ``create_sim_space``，返回端口表。

    候选轨迹布线器只需要端点与端口编号；不跑原版直角布线可以避免产生多余的
    中间文件，也避免半径参数对端口表造成任何影响。
    """
    mods = legacy_modules()
    root = legacy_project_root()
    if input_path is None:
        input_path = root / "data" / ("fiberBoard%d.xlsx" % channels)
    if save_folder is None:
        save_folder = DEFAULT_SCRATCH / ("%d_ports" % channels)
    if pitch is None:
        pitch = default_pitch(channels)
    Path(save_folder).mkdir(parents=True, exist_ok=True)
    return mods["problem_graph"].create_sim_space(
        str(input_path), str(save_folder), line_width, pitch, height=height, N=channels
    )


def run_legacy_rect(
    channels: int,
    radius: float,
    *,
    input_path: str | Path | None = None,
    save_folder: str | Path | None = None,
    line_width: float = 0.05,
    pitch: float | None = None,
    height: int = 150,
    width: int = 150,
):
    """运行原版管线的前两步：``create_sim_space`` -> ``plotter_rect``。

    只做直角布线（``plotter_rect``），不做弯道绘制与 GDS 导出，因为
    ``plotter_bend`` 的圆弧几何由本包的 :mod:`src.opt2d.smoothing`
    以解析 Line/Arc 形式独立重建并核验。

    返回 ``(df_ports, df_rect)`` 两个 DataFrame。
    """
    mods = legacy_modules()
    root = legacy_project_root()
    if input_path is None:
        input_path = root / "data" / ("fiberBoard%d.xlsx" % channels)
    if save_folder is None:
        save_folder = DEFAULT_SCRATCH / ("%d_R%g" % (channels, float(radius)))
    if pitch is None:
        pitch = default_pitch(channels)
    Path(save_folder).mkdir(parents=True, exist_ok=True)
    df_ports = mods["problem_graph"].create_sim_space(
        str(input_path), str(save_folder), line_width, pitch, height=height, N=channels
    )
    df_rect = mods["wiring_rect_826"].plotter_rect(
        df_ports,
        line_width,
        pitch + line_width,
        str(save_folder),
        height=height,
        N=channels,
        r=radius,
    )
    return df_ports, df_rect
