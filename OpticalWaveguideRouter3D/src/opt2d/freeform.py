"""自由弯角 S 形路径（Step 13 第三阶段）。

只用于**跨上下两侧**的连接（``sy != ly``），几何为

    直线引出段 + 圆弧 + 斜向直线 + 圆弧 + 直线引入段

与原版 U 型的区别是：保留两个圆弧与端口切线方向（出线仍垂直于板边），但把
"中间段必须水平"放开为任意方向，两个圆弧的转角也随之自由（互为相反数，
保证出端切线回到竖直）。半径首版限定在已有实测弯曲损耗数据的 R5 / R6。

几何推导（全部在全局坐标里，`sigma = sign(ly - sy)`、`s = sign(alpha)`）：

* 出线方向 ``u = (0, sigma)``，第一弧转角 ``alpha``（有符号，左转为正），
  中间段方向 ``v1 = (-sigma*sin(alpha), sigma*cos(alpha))``；
* 两段弧各自贡献的横向位移**同向**：
  ``dx_arc = R*sigma*s*(cos(alpha) - 1)``，因此斜线必须把它和端点横向差一起
  消化掉 —— ``L = (2*R*sigma*s*(cos(alpha) - 1) - Dx) / (sigma*sin(alpha))``，
  要求 ``L >= 0``；
* 纵向：``S = t0 + t3 = dy - 2*R*s*sin(alpha) - L*cos(alpha)``，要求 ``S >= 0``，
  再由 ``t0_fraction`` 分成 ``t0`` 与 ``t3``；
* 切点与圆心：``A = P0 + t0*u``，``C1 = A + R*(-sigma*s, 0)``，
  ``A' = A + R*sigma*s*(cos(alpha) - 1, sin(alpha))``，``B = A' + L*v1``，
  ``C2 = B + R*sigma*s*(cos(alpha), sin(alpha))``，``B' = C2 - R*sigma*s*(1, 0)``，
  ``P3 = B' + t3*u``。

由此得到两条硬约束：斜线方向必须指向终点一侧，因此 ``Dx > 0`` 要求
``alpha < 0``、``Dx < 0`` 要求 ``alpha > 0``；**``Dx = 0``（零水平偏移）时
不存在合法解**（两弧横向位移与斜线横向位移同向，无法抵消），此时该连接必须
保留 U 型几何（``dx`` 足够小时原版本身就是"两弧在中点相接"的 S 形）。
构造完成后在 :func:`build_freeform_geometry` 内验证端点、半径与切向连续，
任何不满足都抛出 ``ValueError``，由调用方当作非法候选丢弃。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from math import cos, hypot, radians, sin

from ..models import ArcSegment2D, LineSegment2D, Point2D

__all__ = [
    "FreeformParams",
    "DEFAULT_ALPHAS_DEG",
    "DEFAULT_T0_FRACTIONS",
    "build_freeform_geometry",
    "freeform_candidates",
]

#: 圆弧转角的候选网格（绝对值，正负都会尝试）。
DEFAULT_ALPHAS_DEG: tuple[float, ...] = (5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 75.0)
#: 引出段长度在两段直线之间的分配比例。
DEFAULT_T0_FRACTIONS: tuple[float, ...] = (0.0, 0.5, 1.0)


@dataclass(frozen=True)
class FreeformParams:
    """一条自由弯角候选的完整参数。"""

    route_id: int
    sx: float
    sy: float
    lx: float
    ly: float
    radius: float
    alpha_deg: float
    t0_fraction: float

    def describe(self) -> str:
        return "freeform R%g alpha=%+.1f t0=%.2f" % (
            self.radius,
            self.alpha_deg,
            self.t0_fraction,
        )


def build_freeform_geometry(
    params: FreeformParams, tol: float = 1e-9
) -> list[LineSegment2D | ArcSegment2D]:
    """构造一条自由弯角 S 形路径；非法几何抛出 ``ValueError``。"""
    if abs(params.ly - params.sy) <= tol:
        raise ValueError("freeform geometry is only for cross-side connections")
    if params.radius <= 0:
        raise ValueError("radius must be positive")
    alpha = radians(float(params.alpha_deg))
    if abs(alpha) <= 1e-9:
        raise ValueError("zero angle is the straight-line limit, not a freeform route")
    sin_a, cos_a = sin(alpha), cos(alpha)
    if abs(sin_a) < 1e-12:
        raise ValueError("alpha is too close to 90 degrees to be representable")

    sigma = 1.0 if params.ly > params.sy else -1.0
    s = 1.0 if alpha > 0 else -1.0
    dx = params.lx - params.sx
    dy = sigma * (params.ly - params.sy)  # > 0

    # 端点位移方程（x）：两弧横向位移同向 + 斜线横向位移 = dx。
    numerator = 2.0 * params.radius * sigma * s * (cos_a - 1.0) - dx
    denominator = sigma * sin_a
    if abs(denominator) < 1e-12:
        raise ValueError("degenerate angle denominator")
    length = numerator / denominator
    if length < -tol:
        raise ValueError("negative middle segment length")
    length = max(0.0, length)
    straight_sum = dy - 2.0 * params.radius * s * sin_a - length * cos_a
    if straight_sum < -tol:
        raise ValueError("insufficient straight length for this angle")
    straight_sum = max(0.0, straight_sum)
    fraction = min(1.0, max(0.0, float(params.t0_fraction)))
    t0 = fraction * straight_sum
    t3 = straight_sum - t0

    radius = float(params.radius)
    p0 = Point2D(float(params.sx), float(params.sy))
    p3 = Point2D(float(params.lx), float(params.ly))
    ux, uy = 0.0, sigma
    vx, vy = -sigma * sin_a, sigma * cos_a
    shift_x = radius * sigma * s * (cos_a - 1.0)
    shift_y = radius * sigma * s * sin_a

    a = Point2D(p0.x + t0 * ux, p0.y + t0 * uy)
    c1 = Point2D(a.x - radius * sigma * s, a.y)
    a2 = Point2D(a.x + shift_x, a.y + shift_y)
    b = Point2D(a2.x + length * vx, a2.y + length * vy)
    c2 = Point2D(b.x + radius * sigma * s * cos_a, b.y + radius * sigma * s * sin_a)
    b2 = Point2D(c2.x - radius * sigma * s, c2.y)

    segments: list[LineSegment2D | ArcSegment2D] = []
    if t0 > tol:
        segments.append(LineSegment2D(p0, a))
    segments.append(ArcSegment2D(a, a2, c1, alpha))
    if length > tol:
        segments.append(LineSegment2D(a2, b))
    segments.append(ArcSegment2D(b, b2, c2, -alpha))
    if t3 > tol:
        segments.append(LineSegment2D(b2, p3))

    # ---- 构造后自检：端点、半径、切向连续、中间段长度 ----
    if hypot(segments[0].start.x - p0.x, segments[0].start.y - p0.y) > 1e-6:
        raise ValueError("start point mismatch")
    if hypot(segments[-1].end.x - p3.x, segments[-1].end.y - p3.y) > 1e-6:
        raise ValueError("end point mismatch")
    for segment in segments:
        if isinstance(segment, ArcSegment2D):
            if abs(hypot(segment.start.x - segment.center.x, segment.start.y - segment.center.y) - radius) > 1e-6:
                raise ValueError("arc radius mismatch")
            if abs(hypot(segment.end.x - segment.center.x, segment.end.y - segment.center.y) - radius) > 1e-6:
                raise ValueError("arc radius mismatch at end")
    for first, second in zip(segments, segments[1:]):
        if hypot(first.end.x - second.start.x, first.end.y - second.start.y) > 1e-9:
            raise ValueError("disconnected segments")
    return segments


def freeform_candidates(
    row,
    radius: float,
    alphas_deg: tuple[float, ...] = DEFAULT_ALPHAS_DEG,
    t0_fractions: tuple[float, ...] = DEFAULT_T0_FRACTIONS,
) -> list[FreeformParams]:
    """枚举一条跨侧连接的自由弯角候选（只保留几何合法的）。"""
    route_id = int(row.name) if hasattr(row, "name") else int(row["route_id"])
    candidates: list[FreeformParams] = []
    for magnitude in alphas_deg:
        for sign in (1.0, -1.0):
            for fraction in t0_fractions:
                params = FreeformParams(
                    route_id=route_id,
                    sx=float(row["sx"]),
                    sy=float(row["sy"]),
                    lx=float(row["lx"]),
                    ly=float(row["ly"]),
                    radius=float(radius),
                    alpha_deg=sign * magnitude,
                    t0_fraction=float(fraction),
                )
                try:
                    build_freeform_geometry(params)
                except ValueError:
                    continue
                candidates.append(params)
    return candidates
