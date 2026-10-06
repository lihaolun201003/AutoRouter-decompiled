"""Step 13 的冻结输入：逐路固定端点与连接身份。

实验可信性的前提是**所有方案使用同一组端点**。本模块从方案 A（原版
``plotter_rect`` 的实际输出）提取每条 ``route_id`` 的起点、终点与连接身份，
作为后续所有方案的冻结输入：

* 端点数值 = A 最终几何的 ``sx/sy/lx/ly``（即原版在端口重排后的实际出线位置）；
* 连接身份 = ``Port1/Port2/index1/index2/dz``。

新方案不允许再用"交换同端口槽位"的方式满足布线条件；端口顺序问题必须通过
轨道选择或候选评分处理。若确实需要对照"可重排端口"模式，必须显式启用并单独命名
（见 :func:`planner.PlanConfig.allow_port_reorder`）。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .legacy_bridge import run_legacy_rect
from .source import specs_from_rect

__all__ = ["FrozenEndpoint", "freeze_from_baseline", "frozen_ports_frame"]


@dataclass(frozen=True)
class FrozenEndpoint:
    """一条连接的冻结输入。"""

    route_id: int
    port1: int
    port2: int
    index1: int
    index2: int
    sx: float
    sy: float
    lx: float
    ly: float


def freeze_from_baseline(channels: int, radius: float = 5.0) -> list[FrozenEndpoint]:
    """从方案 A（原版 R5 的实际几何）提取冻结端点。"""
    _, rect = run_legacy_rect(channels, radius)
    specs = specs_from_rect(rect, radius)
    frozen = [
        FrozenEndpoint(
            route_id=spec.route_id,
            port1=int(spec.port1),
            port2=int(spec.port2),
            index1=int(spec.index1),
            index2=int(spec.index2),
            sx=float(spec.sx),
            sy=float(spec.sy),
            lx=float(spec.lx),
            ly=float(spec.ly),
        )
        for spec in specs
    ]
    return sorted(frozen, key=lambda item: item.route_id)


def frozen_ports_frame(channels: int, radius: float = 5.0) -> pd.DataFrame:
    """把冻结端点写成布线器可直接消费的端口表（``index`` 即 ``route_id``）。"""
    frozen = freeze_from_baseline(channels, radius)
    rows = []
    for item in frozen:
        rows.append(
            {
                "index": item.route_id,
                "Port1": item.port1,
                "Port2": item.port2,
                "index1": item.index1,
                "index2": item.index2,
                "sy": item.sy,
                "ly": item.ly,
                "dz": 0,
                "sx": item.sx,
                "lx": item.lx,
                "dx": abs(item.lx - item.sx),
            }
        )
    return pd.DataFrame(rows).set_index("index")
