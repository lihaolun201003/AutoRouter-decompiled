"""原版圆弧几何的解析重建（Line/Arc 表示）。

原版 ``wiring_bend_826.plotter_bend`` 不直接输出曲线，而是输出

* ``bend_x`` / ``bend_y``：两个圆弧各自的直线切点（每弯两点，共 4 点）；
* ``center``：圆弧圆心；
* ``theta``：绘图用的弧参数区间；
* ``dir``：每弯的象限方向。

本模块把这些几何**按行进方向**重建成解析的
:class:`~src.models.LineSegment2D` / :class:`~src.models.ArcSegment2D` 序列，
并同时提供 :func:`legacy_bend_records` 用原版公式复算上述四个字段，供逐条核验。

两种几何分支（由水平跨度 ``dx = |lx - sx|`` 与弯曲半径 ``R`` 决定）：

``dx >= 2R``
    标准双 90° 圆角：两个完整四分之一圆弧，中间一段水平直线轨道。

``0 < dx < 2R``
    原版把两个半径 ``R`` 的非完整圆弧在水平中点处直接相接，无中间直线段。
    弧的半角 ``theta = arccos((R - dx/2) / R)``，竖直切点距轨道
    ``R*sin(theta)``。该式由原版 ``bend_x``/``bend_y``/``center``/``theta``
    实测数据反推并在 :mod:`tests.test_opt2d_smoothing` 中逐条锁定。

``dx == 0`` 时原版只输出两点单直线，本模块同样只返回一条直线段。

坐标约定：``sx``/``lx`` 为两端 x，``sy``/``ly`` 为两端 y（板边 0 或 ``height``），
``track_y`` 为该连接的轨道（中间水平段）y。所有长度单位为 mm。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import acos, atan2, cos, hypot, pi, sin

from ..geometry import distance
from ..models import ArcSegment2D, LineSegment2D, Point2D, SmoothedRoute2D

__all__ = [
    "RouteSpec",
    "build_route_geometry",
    "legacy_bend_records",
    "bend_half_angle",
]


def bend_half_angle(dx: float, radius: float) -> float:
    """``dx < 2R`` 时单个圆弧的半角（弧度）；``dx >= 2R`` 时返回 pi/2。"""
    if radius <= 0:
        raise ValueError("radius must be positive")
    if dx >= 2 * radius:
        return pi / 2
    ratio = (radius - dx * 0.5) / radius
    ratio = min(1.0, max(-1.0, ratio))
    return acos(ratio)


@dataclass
class RouteSpec:
    """一条连接的布线输入：两个端点与轨道坐标。

    ``kind`` 区分几何族：``u`` 是原版水平轨道 U 型（默认，Step 12 的全部结果）；
    ``freeform`` 是 Step 13 的自由弯角 S 形（见 :mod:`src.opt2d.freeform`），
    此时 ``alpha_deg`` 与 ``t0_fraction`` 才有意义。
    """

    route_id: int
    sx: float
    sy: float
    lx: float
    ly: float
    track_y: float
    radius: float
    port1: int | None = None
    port2: int | None = None
    index1: int | None = None
    index2: int | None = None
    kind: str = "u"
    alpha_deg: float = 0.0
    t0_fraction: float = 0.5

    @property
    def dx(self) -> float:
        return abs(self.lx - self.sx)

    @property
    def span(self) -> float:
        return self.dx


def _sign(value: float, tol: float) -> float:
    if value > tol:
        return 1.0
    if value < -tol:
        return -1.0
    return 0.0


def _arc_from_endpoints(
    start: Point2D, end: Point2D, center: Point2D, radius: float, tol: float
) -> ArcSegment2D:
    """构造从 ``start`` 到 ``end``、圆心 ``center`` 的最短圆弧（|sweep| <= pi）。"""
    a0 = atan2(start.y - center.y, start.x - center.x)
    a1 = atan2(end.y - center.y, end.x - center.x)
    sweep = a1 - a0
    while sweep <= -pi:
        sweep += 2 * pi
    while sweep > pi:
        sweep -= 2 * pi
    if abs(sweep) <= tol:
        raise ValueError("degenerate arc sweep")
    # 数值上落回精确半径，避免逐点残差影响后续求交与损耗。
    return ArcSegment2D(start, end, center, sweep)


def build_route_geometry(
    spec: RouteSpec, tol: float = 1e-9
) -> list[LineSegment2D | ArcSegment2D]:
    """重建一条连接的原版圆弧几何，返回按行进方向排列的解析线段序列。

    几何严格沿用原版：端点、轨道与半径一一对应，不做任何修正或调参。
    当弯道无法容纳（切点越过端点或跨过轨道）时抛出 ``ValueError``。
    """
    radius = float(spec.radius)
    if radius <= 0:
        raise ValueError("radius must be positive")
    start = Point2D(float(spec.sx), float(spec.sy))
    end = Point2D(float(spec.lx), float(spec.ly))
    track = float(spec.track_y)
    dx = abs(end.x - start.x)
    s = _sign(track - start.y, tol)
    t = _sign(end.y - track, tol)
    v = _sign(end.x - start.x, tol)

    if dx <= tol:
        if abs(start.x - end.x) > tol:
            raise ValueError("degenerate dx with distinct x")
        if abs(start.y - end.y) <= tol:
            raise ValueError("zero-length connection")
        return [LineSegment2D(start, end)]
    if s == 0 or v == 0:
        raise ValueError("track must lie strictly away from the start side")
    if t == 0:
        raise ValueError("track must lie strictly away from the end side")

    segments: list[LineSegment2D | ArcSegment2D] = []

    if dx >= 2 * radius - tol:
        # 标准双 90 度圆角。
        a = Point2D(start.x, track - s * radius)
        b = Point2D(start.x + v * radius, track)
        c = Point2D(end.x - v * radius, track)
        d = Point2D(end.x, track + t * radius)
        center1 = Point2D(start.x + v * radius, track - s * radius)
        center2 = Point2D(end.x - v * radius, track + t * radius)
        if not _between(track - s * radius, start.y, track, tol):
            raise ValueError("start-side straight is shorter than the bend radius")
        if not _between(track + t * radius, track, end.y, tol):
            raise ValueError("end-side straight is shorter than the bend radius")
        if distance(center1, b) > 1e-6 + radius or distance(center2, c) > 1e-6 + radius:
            raise ValueError("inconsistent bend centres")
        if distance(start, a) > tol:
            segments.append(LineSegment2D(start, a))
        segments.append(_arc_from_endpoints(a, b, center1, radius, tol))
        if distance(b, c) > tol:
            segments.append(LineSegment2D(b, c))
        segments.append(_arc_from_endpoints(c, d, center2, radius, tol))
        if distance(d, end) > tol:
            segments.append(LineSegment2D(d, end))
        return segments

    # 0 < dx < 2R：两个非完整圆弧在中点相接。
    theta = bend_half_angle(dx, radius)
    h = radius * sin(theta)
    cx = 0.5 * (start.x + end.x)
    mid = Point2D(cx, track)
    a = Point2D(start.x, track - s * h)
    c = Point2D(end.x, track + t * h)
    if not _between(a.y, start.y, track, tol):
        raise ValueError("start-side straight is shorter than the bend rise")
    if not _between(c.y, track, end.y, tol):
        raise ValueError("end-side straight is shorter than the bend rise")
    center1 = Point2D(start.x + v * radius, a.y)
    center2 = Point2D(end.x - v * radius, c.y)
    if abs(distance(center1, a) - radius) > 1e-6 or abs(distance(center1, mid) - radius) > 1e-6:
        raise ValueError("inconsistent first bend centre")
    if abs(distance(center2, c) - radius) > 1e-6 or abs(distance(center2, mid) - radius) > 1e-6:
        raise ValueError("inconsistent second bend centre")
    if distance(start, a) > tol:
        segments.append(LineSegment2D(start, a))
    segments.append(_arc_from_endpoints(a, mid, center1, radius, tol))
    segments.append(_arc_from_endpoints(mid, c, center2, radius, tol))
    if distance(c, end) > tol:
        segments.append(LineSegment2D(c, end))
    return segments


def _between(value: float, lo: float, hi: float, tol: float) -> bool:
    """``value`` 是否落在 ``lo`` 与 ``hi`` 之间（含端点，允许 tol）。"""
    return min(lo, hi) - tol <= value <= max(lo, hi) + tol


def legacy_bend_records(spec: RouteSpec, tol: float = 1e-9) -> dict:
    """用原版 ``plotter_bend`` 的公式复算 ``bend_x``/``bend_y``/``center``/``theta``/``dir``。

    仅用于核验：与 2D 项目写出的 ``fiberBoard<N>bend.xlsx`` 逐条比对。
    """
    start = Point2D(float(spec.sx), float(spec.sy))
    end = Point2D(float(spec.lx), float(spec.ly))
    track = float(spec.track_y)
    radius = float(spec.radius)
    dx = abs(end.x - start.x)
    s = _sign(track - start.y, tol)
    t = _sign(end.y - track, tol)
    v = _sign(end.x - start.x, tol)
    if dx <= tol:
        return {"bend_x": [], "bend_y": [], "center": [], "theta": [], "dir": []}

    # 原版：dir_in = inflection[i] - inflection[i+1]（= -行进方向），dir_out 为离开方向。
    dirs = [(v, -s), (-v, t)]
    if dx >= 2 * radius:
        bend_x = [start.x, start.x + radius * v, end.x - radius * v, end.x]
        bend_y = [track - radius * s, track, track, track + radius * t]
    else:
        rise = radius * sin(bend_half_angle(dx, radius))
        bend_x = [start.x, start.x + dx * 0.5 * v, end.x - dx * 0.5 * v, end.x]
        bend_y = [track - rise * s, track, track, track + rise * t]
    centers = [
        (bend_x[0] + radius * dirs[0][0], bend_y[0]),
        (bend_x[3] + radius * dirs[1][0], bend_y[3]),
    ]
    # theta 区间：dx>=2R 用 theta_map（整 90 度），0<dx<2R 用 calc_theta（半角）。
    theta_map = {
        (-1.0, -1.0): (0.0, pi / 2),
        (1.0, -1.0): (pi / 2, pi),
        (1.0, 1.0): (pi, pi / 2 * 3),
        (-1.0, 1.0): (pi / 2 * 3, 2 * pi),
    }
    half = bend_half_angle(dx, radius)
    theta_map_s = {
        (-1.0, -1.0): (0.0, half),
        (1.0, -1.0): (pi - half, pi),
        (1.0, 1.0): (pi, pi + half),
        (-1.0, 1.0): (2 * pi - half, 2 * pi),
    }
    table = theta_map_s if dx < 2 * radius else theta_map
    theta = [
        table[(round(dirs[0][0]), round(dirs[0][1]))],
        table[(round(dirs[1][0]), round(dirs[1][1]))],
    ]
    return {
        "bend_x": bend_x,
        "bend_y": bend_y,
        "center": centers,
        "theta": theta,
        "dir": [tuple(dirs[0]), tuple(dirs[1])],
    }


def total_length(segments) -> float:
    """解析总长度（直线 + 弧长）。"""
    from ..geometry import arc_segment_length, line_segment_length

    total = 0.0
    for seg in segments:
        total += (
            line_segment_length(seg)
            if isinstance(seg, LineSegment2D)
            else arc_segment_length(seg)
        )
    return total


def smoothed(spec: RouteSpec, tol: float = 1e-9) -> SmoothedRoute2D:
    """:func:`build_route_geometry` 的 ``SmoothedRoute2D`` 包装。"""
    return SmoothedRoute2D(spec.route_id, build_route_geometry(spec, tol))
