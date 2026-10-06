"""解析求交的统一入口：直线段用尺度/垂距/投影三判据的稳健分类。

背景（Step 13 复核发现）：`src.collision.find_segment_intersections_2d` 对
**一般方向**的两条直线会因绝对残差阈值报错；Step 13 的旧兼容路径只在"残差"
错误时退回中点法，并且它用 ``determinant == 0`` 的精确浮点比较判断平行 ——
两条几何上共线、但端点由不同运算路径构造出来的直线（例如两条斜线段同在
``x + y = 149.9`` 上），行列式往往是 1e-17 量级的非零值，于是走到参数解，
把真实的重合（256 通道 F56 的路线 #7 与 #31，重叠 152.007142675 mm）误判成
一个 ``cross`` 点，导致 planner / evaluator / spacing 全部漏掉该几何违规。

本模块的直线分类器只依赖三个几何量：

1. **夹角正弦** ``sin = u x v``（单位方向叉积）。只有 ``|sin| <= 1e-8`` 才进入
   平行族 —— 真实的小角度交叉（本项目实测最小 8.57°）不会落入该阈值；
2. **垂距**：平行族里用另一个线段的两个端点到本线段的垂距判定"共线"还是
   "平行分离"；共线容差取 ``max(tol, scale * 1e-12)``，仅容纳浮点残差
   （实测残差约 4e-14 mm，远小于容差；而真实的 0.001 mm 级偏移会被判为分离，
   交给间距检查而不是重合）；
3. **投影区间**：共线时把另一线段投影到本线段参数轴上求重叠区间 ——
   有正长度重叠是 ``overlap``（几何违规），区间退化为一点是端点接触 ``touch``，
   无重叠则无事件。

非平行分支用参数解求交点，并用"交点必须在两条**有限**线段上"和
"两参数解点的残差 <= max(tol, scale * 1e-7)"双重约束校验；残差超限抛
``ValueError``（宁可报错也不返回不可靠的点）。

直—弧与弧—弧沿用既有实现：它们在轴对齐与圆弧几何上经过既有测试验证，
且圆弧重合有专门的同圆心/同半径分支。planner、evaluator、spacing 全部经由
本入口，分类口径一致。
"""

from __future__ import annotations

from math import hypot, isfinite

from ..collision import SegmentIntersection, find_segment_intersections_2d
from ..models import ArcSegment2D, LineSegment2D, Point2D

__all__ = ["segment_intersections", "tolerant_solves", "PARALLEL_SIN_TOL"]

#: 稳健直线分类器被使用的次数（诊断用；确定性运行下每次相同）。
tolerant_solves = 0

#: 判为"数值平行"的夹角正弦上限（≈1e-8 rad ≈ 6e-7 度）。
#: 真实交叉角比它大 6 个数量级，因此不会把真实小角度交叉吞掉。
PARALLEL_SIN_TOL = 1e-8

#: 平行线判为共线的垂距容差（相对线段尺度）。
#: 浮点残差实测约 4e-14 mm，容差取 scale*1e-12（150 mm 尺度=1.5e-10 mm）。
_COLLINEAR_REL_TOL = 1e-12

#: 求解残差容差（相对线段尺度）：两参数解点之间的允许差，属**数值可解性**判据。
#: 150 mm 尺度=1.5e-5 mm；|sin| >= 1e-8 时参数解误差 <= 2*eps*scale/1e-8 << 该容差。
_INTERSECTION_REL_TOL = 1e-7

#: 有限段边界容差（相对线段尺度），属**几何语义**判据：交点在参数轴上超出
#: 端点多少才算"落在有限段之外"。150 mm 尺度=1.5e-7 mm，比求解残差严格
#: 100 倍；实际生效值再与参数解不确定度取大（见 :func:`_robust_line_line`）。
_EDGE_REL_TOL = 1e-9

#: 双精度机器精度（估计参数解不确定度用）。
_EPS = 2.220446049250313e-16


def _validate_tol(tol: float) -> None:
    if not isfinite(tol) or tol < 0:
        raise ValueError("tol must be finite and nonnegative.")


def _unit(start: Point2D, end: Point2D) -> tuple[float, float, float]:
    dx, dy = end.x - start.x, end.y - start.y
    length = hypot(dx, dy)
    if not isfinite(length) or length == 0:
        raise ValueError("Zero-length analytic line is not supported.")
    return dx / length, dy / length, length


def _endpoint_near(point: Point2D, segment: LineSegment2D, tol: float) -> bool:
    """交点是否落在端点容差内（决定 touch 与 cross）。"""
    return (
        hypot(point.x - segment.start.x, point.y - segment.start.y) <= tol
        or hypot(point.x - segment.end.x, point.y - segment.end.y) <= tol
    )


def _parallel_line_relations(
    a: LineSegment2D,
    b: LineSegment2D,
    ux: float,
    uy: float,
    length_a: float,
    wx: float,
    wy: float,
    scale: float,
    tol: float,
) -> list[SegmentIntersection]:
    """平行族：垂距判共线，投影区间判重合/端点接触/分离。"""
    perp_tol = max(tol, scale * _COLLINEAR_REL_TOL)
    ex, ey = b.end.x - a.start.x, b.end.y - a.start.y
    if max(abs(ux * wy - uy * wx), abs(ux * ey - uy * ex)) > perp_tol:
        return []  # 平行但分离：不是共线，更不是交点
    t0 = wx * ux + wy * uy
    t1 = ex * ux + ey * uy
    lo = max(0.0, min(t0, t1))
    hi = min(length_a, max(t0, t1))
    if hi - lo > tol:
        return [SegmentIntersection("overlap")]
    if lo > hi + tol:
        return []
    t = 0.5 * (lo + hi)
    return [
        SegmentIntersection("touch", Point2D(a.start.x + t * ux, a.start.y + t * uy))
    ]


def _robust_line_line(
    a: LineSegment2D, b: LineSegment2D, tol: float
) -> list[SegmentIntersection]:
    """两条有限直线段的稳健解析分类（cross / touch / overlap / 无交）。"""
    ux, uy, length_a = _unit(a.start, a.end)
    vx, vy, length_b = _unit(b.start, b.end)
    scale = max(length_a, length_b, 1.0)
    wx, wy = b.start.x - a.start.x, b.start.y - a.start.y
    sin_theta = ux * vy - uy * vx
    if abs(sin_theta) <= PARALLEL_SIN_TOL:
        return _parallel_line_relations(
            a, b, ux, uy, length_a, wx, wy, scale, tol
        )
    t = (wx * vy - wy * vx) / sin_theta
    s = (wx * uy - wy * ux) / sin_theta
    if not (isfinite(t) and isfinite(s)):
        raise ValueError("Ill-conditioned line intersection.")
    # 两类容差分开：
    #   残差容差 residual_tol —— 数值可解性（两个参数解点之间的允许差）；
    #   边界容差 edge_tol —— 几何语义（超出有限段多少算"段外"），
    #   并与参数解的不确定度取大：sin 越接近平行阈值，t 的误差 ~ eps*scale/sin
    #   越大，边界判断必须容忍它，否则"在段上/段外"会随舍入抖动。
    residual_tol = max(tol, scale * _INTERSECTION_REL_TOL)
    uncertainty = 4.0 * _EPS * scale / max(abs(sin_theta), PARALLEL_SIN_TOL)
    edge_tol = max(tol, scale * _EDGE_REL_TOL, uncertainty)
    if not (-edge_tol <= t <= length_a + edge_tol and -edge_tol <= s <= length_b + edge_tol):
        return []
    pa = Point2D(a.start.x + t * ux, a.start.y + t * uy)
    pb = Point2D(b.start.x + s * vx, b.start.y + s * vy)
    if hypot(pa.x - pb.x, pa.y - pb.y) > residual_tol:
        raise ValueError("Line intersection residual exceeds tolerance.")
    point = Point2D(0.5 * (pa.x + pb.x), 0.5 * (pa.y + pb.y))
    kind = (
        "touch"
        if _endpoint_near(point, a, tol) or _endpoint_near(point, b, tol)
        else "cross"
    )
    return [SegmentIntersection(kind, point)]


def segment_intersections(
    a: LineSegment2D | ArcSegment2D,
    b: LineSegment2D | ArcSegment2D,
    tol: float = 1e-9,
) -> list[SegmentIntersection]:
    """解析求交（planner / evaluator / spacing 的统一入口）。

    直—直：稳健分类器（尺度 + 垂距 + 投影区间），一般方向的直线不再触发
    绝对残差断言，共线重合稳定判为 ``overlap``；
    直—弧、弧—弧：既有 ``src.collision`` 实现（其行为已经过既有测试锁定）。
    """
    global tolerant_solves
    _validate_tol(tol)
    if isinstance(a, LineSegment2D) and isinstance(b, LineSegment2D):
        tolerant_solves += 1
        return _robust_line_line(a, b, tol)
    return find_segment_intersections_2d(a, b, tol)
