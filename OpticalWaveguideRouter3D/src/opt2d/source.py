"""从原版直角布线表构造评价输入，并生成原版统计所需的弯道表。

* :func:`specs_from_rect` 读取 ``plotter_rect`` 的输出（或 2D 项目写出的
  ``fiberBoard<N>rect.xlsx``），得到 :class:`~src.opt2d.smoothing.RouteSpec`；
* :func:`legacy_bend_frame` 生成 2D 项目 ``waveguide_calculator.calc_index``
  可以直接消费的弯道表（列名与 ``plotter_bend`` 输出一致），用于**原版统计**。
"""

from __future__ import annotations

import ast

import pandas as pd

from .smoothing import RouteSpec, legacy_bend_records

__all__ = ["specs_from_rect", "legacy_bend_frame", "specs_from_bend_frame"]


def _as_list(value):
    if isinstance(value, str):
        return ast.literal_eval(value)
    return list(value)


def specs_from_rect(df_rect: pd.DataFrame, radius: float) -> list[RouteSpec]:
    """把直角布线表转成 ``RouteSpec`` 列表（route_id 取表索引）。"""
    specs: list[RouteSpec] = []
    for row_id, row in df_rect.iterrows():
        inflection_x = _as_list(row["inflection_x"])
        inflection_y = _as_list(row["inflection_y"])
        track = float(row["inflection"])
        sx, lx = float(inflection_x[0]), float(inflection_x[-1])
        sy, ly = float(inflection_y[0]), float(inflection_y[-1])
        specs.append(
            RouteSpec(
                route_id=int(row_id),
                sx=sx,
                sy=sy,
                lx=lx,
                ly=ly,
                track_y=track,
                radius=float(radius),
                port1=int(row["Port1"]) if "Port1" in row else None,
                port2=int(row["Port2"]) if "Port2" in row else None,
                index1=int(row["index1"]) if "index1" in row else None,
                index2=int(row["index2"]) if "index2" in row else None,
            )
        )
    return specs


def specs_from_bend_frame(df_bend: pd.DataFrame, radius: float | None = None) -> list[RouteSpec]:
    """从 ``plotter_bend`` 风格的表（含 ``inflection_x``/``inflection_y``）恢复规格。"""
    specs: list[RouteSpec] = []
    for row_id, row in df_bend.iterrows():
        inflection_x = _as_list(row["inflection_x"])
        inflection_y = _as_list(row["inflection_y"])
        track = float(inflection_y[-2]) if len(inflection_y) > 2 else float(inflection_y[0])
        radius_value = float(radius) if radius is not None else float(row.get("bend_radius", 5.0))
        specs.append(
            RouteSpec(
                route_id=int(row_id),
                sx=float(inflection_x[0]),
                sy=float(inflection_y[0]),
                lx=float(inflection_x[-1]),
                ly=float(inflection_y[-1]),
                track_y=track,
                radius=radius_value,
                port1=int(row["Port1"]) if "Port1" in row else None,
                port2=int(row["Port2"]) if "Port2" in row else None,
                index1=int(row["index1"]) if "index1" in row else None,
                index2=int(row["index2"]) if "index2" in row else None,
            )
        )
    return specs


def legacy_bend_frame(specs: list[RouteSpec]) -> pd.DataFrame:
    """生成原版 ``calc_index`` 需要的弯道表（列与 ``plotter_bend`` 输出一致）。"""
    rows = []
    for spec in specs:
        record = legacy_bend_records(spec)
        rows.append(
            {
                "index": spec.route_id,
                "Port1": spec.port1,
                "Port2": spec.port2,
                "index1": spec.index1,
                "index2": spec.index2,
                "sy": spec.sy,
                "ly": spec.ly,
                "dz": 0,
                "sx": spec.sx,
                "lx": spec.lx,
                "dx": spec.dx,
                "inflection": spec.track_y,
                "inflection_x": str([float(v) for v in (spec.sx, spec.sx, spec.lx, spec.lx)])
                if spec.dx > 1e-12
                else str([float(spec.sx), float(spec.lx)]),
                "inflection_y": str([float(v) for v in (spec.sy, spec.track_y, spec.track_y, spec.ly)])
                if spec.dx > 1e-12
                else str([float(spec.sy), float(spec.ly)]),
                "ln": None,
                "dir": str([tuple(record["dir"][0]), tuple(record["dir"][1])]),
                "bend_x": str([float(v) for v in record["bend_x"]]),
                "bend_y": str([float(v) for v in record["bend_y"]]),
                "center": str([tuple(float(v) for v in c) for c in record["center"]]),
                "theta": str(
                    [
                        (float(record["theta"][0][0]), float(record["theta"][0][1])),
                        (float(record["theta"][1][0]), float(record["theta"][1][1])),
                    ]
                ),
            }
        )
    frame = pd.DataFrame(rows).set_index("index")
    return frame
