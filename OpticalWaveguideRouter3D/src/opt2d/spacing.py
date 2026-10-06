"""近并行间距检查与线段最小距离（实验工具）。

原版 AutoRouter 只用 ``noCross`` 的端口顺序启发式控制相邻轨道的波导，**没有**
显式的中心线间距规则，也没有制造依据给出"最近可接受间距"。本模块因此把
"中心线最小距离 >= 线宽 + 标称间隔"作为**实验假设**使用：它等于轨道节距，
只能保证不劣于原版轨道栅格的标称值，不代表制造规范。

几何上是精确的：先用轴对齐包围盒（AABB）预筛，再对少量候选做解析最近距离，
弧上的候选点用 :func:`src.collision.point_on_arc_2d` 判定是否真的落在弧段内。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, fsum, hypot, isfinite, pi, sin

from ..collision import point_on_arc_2d
from .intersections import segment_intersections
from ..geometry import arc_segment_radius, line_segment_length
from ..models import ArcSegment2D, LineSegment2D, Point2D

__all__ = [
    "Aabb",
    "segment_aabb",
    "aabb_gap",
    "segment_min_distance",
    "SpacingViolation",
    "ContactEvent",
    "SpacingReport",
    "spacing_report",
    "spacing_violations",
]

Segment = LineSegment2D | ArcSegment2D


@dataclass(frozen=True)
class Aabb:
    min_x: float
    min_y: float
    max_x: float
    max_y: float


def segment_aabb(segment: Segment) -> Aabb:
    """解析包围盒；圆弧只覆盖其真实扫掠范围，不只取整圆外包。"""
    if isinstance(segment, LineSegment2D):
        return Aabb(
            min(segment.start.x, segment.end.x),
            min(segment.start.y, segment.end.y),
            max(segment.start.x, segment.end.x),
            max(segment.start.y, segment.end.y),
        )
    center = segment.center
    start_angle = atan2(segment.start.y - center.y, segment.start.x - center.x)
    sweep = segment.sweep_rad
    end_angle = start_angle + sweep
    lo, hi = min(start_angle, end_angle), max(start_angle, end_angle)
    xs = [segment.start.x, segment.end.x]
    ys = [segment.start.y, segment.end.y]
    radius = arc_segment_radius(segment)
    # 检查四个轴极值方向是否落在扫掠区间内（区间长度 <= 2pi）。
    for k in range(4):
        axis = k * pi / 2
        angle = axis
        while angle < lo:
            angle += 2 * pi
        if angle <= hi:
            xs.append(center.x + radius * cos(axis))
            ys.append(center.y + radius * sin(axis))
    return Aabb(min(xs), min(ys), max(xs), max(ys))


def aabb_gap(a: Aabb, b: Aabb) -> float:
    """两包围盒之间的最小间隙；相交时为 0。"""
    dx = max(0.0, a.min_x - b.max_x, b.min_x - a.max_x)
    dy = max(0.0, a.min_y - b.max_y, b.min_y - a.max_y)
    return hypot(dx, dy)


def _closest_on_line(point: Point2D, line: LineSegment2D) -> Point2D:
    vx, vy = line.end.x - line.start.x, line.end.y - line.start.y
    length = line_segment_length(line)
    ux, uy = vx / length, vy / length
    t = (point.x - line.start.x) * ux + (point.y - line.start.y) * uy
    t = min(length, max(0.0, t))
    return Point2D(line.start.x + t * ux, line.start.y + t * uy)


def _closest_on_arc(point: Point2D, arc: ArcSegment2D, tol: float) -> Point2D:
    """点 ``point`` 到弧段的最近点：投影到圆后按扫掠区间裁剪。"""
    center = arc.center
    radius = arc_segment_radius(arc)
    dx, dy = point.x - center.x, point.y - center.y
    norm = hypot(dx, dy)
    if norm <= tol:
        # 圆心上：距离恒为 R，取起点。
        return arc.start
    projection = Point2D(center.x + dx / norm * radius, center.y + dy / norm * radius)
    if point_on_arc_2d(projection, arc, max(tol, 1e-12)):
        return projection
    a = hypot(point.x - arc.start.x, point.y - arc.start.y)
    b = hypot(point.x - arc.end.x, point.y - arc.end.y)
    return arc.start if a <= b else arc.end


def _line_line_distance(
    a: LineSegment2D, b: LineSegment2D, tol: float
) -> tuple[float, Point2D, Point2D]:
    # 通用线段-线段最近点（本项目的直线均为轴对齐，但这里不依赖该性质）。
    candidates: list[tuple[float, Point2D, Point2D]] = []
    for point, line in ((a.start, b), (a.end, b), (b.start, a), (b.end, a)):
        foot = _closest_on_line(point, line)
        candidates.append((hypot(point.x - foot.x, point.y - foot.y), point, foot))
    events = segment_intersections(a, b, tol)
    if any(e.point is not None for e in events):
        point = next(e.point for e in events if e.point is not None)
        return 0.0, point, point
    if events:  # 重叠：距离为零。
        candidates.append((0.0, a.start, _closest_on_line(a.start, b)))
    best = min(candidates, key=lambda item: item[0])
    return best


def _line_arc_distance(
    line: LineSegment2D, arc: ArcSegment2D, tol: float
) -> tuple[float, Point2D, Point2D]:
    candidates: list[tuple[float, Point2D, Point2D]] = []
    for point in (line.start, line.end):
        foot = _closest_on_arc(point, arc, tol)
        candidates.append((hypot(point.x - foot.x, point.y - foot.y), point, foot))
    for point in (arc.start, arc.end):
        foot = _closest_on_line(point, line)
        candidates.append((hypot(point.x - foot.x, point.y - foot.y), point, foot))
    # 垂足在段内时，圆上最近点。
    radius = arc_segment_radius(arc)
    vx, vy = line.end.x - line.start.x, line.end.y - line.start.y
    length = line_segment_length(line)
    ux, uy = vx / length, vy / length
    t = (arc.center.x - line.start.x) * ux + (arc.center.y - line.start.y) * uy
    if -tol <= t <= length + tol:
        tc = min(length, max(0.0, t))
        foot = Point2D(line.start.x + tc * ux, line.start.y + tc * uy)
        point = _closest_on_arc(foot, arc, tol)
        candidates.append((hypot(foot.x - point.x, foot.y - point.y), foot, point))
    best = min(candidates, key=lambda item: item[0])
    return best


def _arc_arc_distance(
    a: ArcSegment2D, b: ArcSegment2D, tol: float
) -> tuple[float, Point2D, Point2D]:
    """两圆弧的最小距离。

    返回的最近点**必须分别落在各自的弧段上**：候选只有两类 ——
    端点投影到另一条弧，或"圆心连线方向"的极值点对且两点都在各自弧上。
    只算圆心距减半径和会在弧端点缺席时给出过小的值（例如两条分离的短弧）。
    """
    ra, rb = arc_segment_radius(a), arc_segment_radius(b)
    ca, cb = a.center, b.center
    candidates: list[tuple[float, Point2D, Point2D]] = []

    def add(pa: Point2D, pb: Point2D) -> None:
        candidates.append((hypot(pa.x - pb.x, pa.y - pb.y), pa, pb))

    # 1) 端点 -> 另一条弧的最近点（两个方向各两次，输入交换时结果对称）。
    for point, arc in ((a.start, b), (a.end, b), (b.start, a), (b.end, a)):
        foot = _closest_on_arc(point, arc, tol)
        if arc is b:
            add(point, foot)
        else:
            add(foot, point)

    # 2) 圆心连线方向的四个极值点对；两个点都必须落在各自的弧段上才有效。
    #    同向对 (1,1)/(-1,-1) 覆盖"两弧同侧相对"的情形，例如圆心 (0,0) R5 与
    #    圆心 (0.9,0) R6、两弧同为 150°→210°：正确最小距离 0.1 只由同向对
    #    (-1,-1) 给出；只取异向对会漏掉它并回退到更大的端点距离。
    distance_centers = hypot(cb.x - ca.x, cb.y - ca.y)
    if distance_centers > tol:
        ux, uy = (cb.x - ca.x) / distance_centers, (cb.y - ca.y) / distance_centers
        for sign_a, sign_b in ((1.0, -1.0), (-1.0, 1.0), (1.0, 1.0), (-1.0, -1.0)):
            pa = Point2D(ca.x + sign_a * ra * ux, ca.y + sign_a * ra * uy)
            pb = Point2D(cb.x + sign_b * rb * ux, cb.y + sign_b * rb * uy)
            if point_on_arc_2d(pa, a, max(tol, 1e-12)) and point_on_arc_2d(
                pb, b, max(tol, 1e-12)
            ):
                add(pa, pb)

    if not candidates:
        raise ValueError("no distance candidate for arc pair")
    return min(candidates, key=lambda item: item[0])


def _closest_on_segment(point: Point2D, segment: Segment, tol: float) -> Point2D:
    if isinstance(segment, LineSegment2D):
        return _closest_on_line(point, segment)
    return _closest_on_arc(point, segment, tol)


def _point_on_segment(point: Point2D, segment: Segment, tol: float) -> bool:
    if isinstance(segment, LineSegment2D):
        foot = _closest_on_line(point, segment)
        return hypot(point.x - foot.x, point.y - foot.y) <= max(tol, 1e-12)
    return point_on_arc_2d(point, segment, max(tol, 1e-12))


def segment_min_distance(
    a: Segment, b: Segment, tol: float = 1e-9
) -> tuple[float, Point2D, Point2D]:
    """两段解析曲线之间的最小距离与最近点对。

    相交或重合的曲线距离恒为 0（先做解析求交判定）；否则按组合分派到
    直—直、直—弧、弧—弧的解析最近点计算。返回的两个点分别落在 ``a`` 与 ``b``
    上，且两点距离等于返回的距离值。
    """
    if not isfinite(tol) or tol < 0:
        raise ValueError("tol must be finite and nonnegative")
    events = segment_intersections(a, b, tol)
    if events:
        for event in events:
            if event.point is not None:
                return 0.0, event.point, event.point
        # 重合（无离散交点）：在公共轨迹上取一个同时落在两条曲线上的点。
        for point, segment in ((a.start, b), (a.end, b), (b.start, a), (b.end, a)):
            if _point_on_segment(point, segment, tol):
                return 0.0, point, point
        anchor = a.start
        return 0.0, anchor, _closest_on_segment(anchor, b, tol)

    if isinstance(a, LineSegment2D) and isinstance(b, LineSegment2D):
        return _line_line_distance(a, b, tol)
    if isinstance(a, LineSegment2D) and isinstance(b, ArcSegment2D):
        return _line_arc_distance(a, b, tol)
    if isinstance(a, ArcSegment2D) and isinstance(b, LineSegment2D):
        distance, pb, pa = _line_arc_distance(b, a, tol)
        return distance, pa, pb
    return _arc_arc_distance(a, b, tol)  # type: ignore[arg-type]


@dataclass
class SpacingViolation:
    route_a: int
    route_b: int
    distance_mm: float
    point_a: Point2D
    point_b: Point2D


@dataclass
class ContactEvent:
    """两条路线之间的接触/重合记录（与"允许的交叉"分开统计）。

    ``kind`` 为 ``touch``（相切或端点接触，零距离但非横穿）或
    ``overlap``（共用一段轨迹，几何违规）。``point`` 对重合为 ``None``。
    """

    route_a: int
    route_b: int
    kind: str
    point_a: Point2D | None = None
    point_b: Point2D | None = None


@dataclass
class SpacingReport:
    """一次间距检查的完整结果。"""

    violations: list[SpacingViolation]
    contacts: list[ContactEvent]

    def overlaps(self) -> list[ContactEvent]:
        return [event for event in self.contacts if event.kind == "overlap"]

    def touches(self) -> list[ContactEvent]:
        return [event for event in self.contacts if event.kind == "touch"]


def spacing_report(
    routes: dict[int, list[Segment]],
    minimum_center_distance_mm: float,
    tol: float = 1e-9,
) -> SpacingReport:
    """近并行间距、接触与重合三类事件一次算清。

    排除规则是显式的：**横穿（cross）属于允许的交叉**，由评价器的交叉事件系统
    单独记录损耗，因此不计入间距违规；``touch`` 与 ``overlap`` 不会被静默忽略，
    而是分别作为接触与重合事件返回。只有"两条曲线不相交且中心线最小距离小于
    阈值"才计入 :class:`SpacingViolation`。

    ``minimum_center_distance_mm`` 是**实验假设**阈值（线宽 + 标称间隔）。
    AABB 预筛保证只对可能违规的段对做解析计算。
    """
    if not isfinite(minimum_center_distance_mm) or minimum_center_distance_mm <= 0:
        raise ValueError("minimum distance must be positive and finite")
    ids = sorted(routes)
    boxes = {i: [segment_aabb(s) for s in routes[i]] for i in ids}
    violations: list[SpacingViolation] = []
    contacts: list[ContactEvent] = []
    for x, i in enumerate(ids):
        for j in ids[x + 1:]:
            hit: tuple[float, Point2D, Point2D] | None = None
            for index_a, box_a in enumerate(boxes[i]):
                for index_b, box_b in enumerate(boxes[j]):
                    if aabb_gap(box_a, box_b) >= minimum_center_distance_mm - tol:
                        continue
                    inner, outer = routes[i][index_a], routes[j][index_b]
                    events = segment_intersections(inner, outer, tol)
                    if events:
                        for event in events:
                            if event.kind == "cross":
                                continue  # 允许的交叉：由交叉事件系统统计
                            contacts.append(
                                ContactEvent(
                                    i,
                                    j,
                                    event.kind,
                                    event.point,
                                    event.point,
                                )
                            )
                        continue  # 相交/接触/重合都不属于"近并行间距不足"
                    distance, pa, pb = segment_min_distance(inner, outer, tol)
                    if distance < minimum_center_distance_mm - tol:
                        if hit is None or distance < hit[0]:
                            hit = (distance, pa, pb)
            if hit is not None:
                violations.append(SpacingViolation(i, j, hit[0], hit[1], hit[2]))
    return SpacingReport(violations, contacts)


def spacing_violations(
    routes: dict[int, list[Segment]],
    minimum_center_distance_mm: float,
    tol: float = 1e-9,
) -> list[SpacingViolation]:
    """只返回近并行间距不足的便捷入口（兼容 Step 12 的调用方式）。"""
    return spacing_report(routes, minimum_center_distance_mm, tol).violations


def segments_length(segments: list[Segment]) -> tuple[float, float]:
    """返回 (直线长度和, 弧长和)。"""
    straight = fsum(
        line_segment_length(s) for s in segments if isinstance(s, LineSegment2D)
    )
    arc = fsum(
        arc_segment_radius(s) * abs(s.sweep_rad)
        for s in segments
        if isinstance(s, ArcSegment2D)
    )
    return straight, arc
