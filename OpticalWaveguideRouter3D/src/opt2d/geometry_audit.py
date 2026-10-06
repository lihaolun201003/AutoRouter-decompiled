"""几何核验：端点、切向连接、半径与板边界。

核验对象是 :mod:`src.opt2d.smoothing` 重建出的解析 Line/Arc 序列。任何
失败项都以数据形式返回，不抛出、不修正几何——由调用方决定是否拒绝该候选。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, pi

from ..geometry import arc_segment_radius
from ..models import ArcSegment2D, LineSegment2D, Point2D

from .smoothing import RouteSpec

__all__ = ["AuditIssue", "segment_tangent", "audit_geometry"]

Segment = LineSegment2D | ArcSegment2D


@dataclass(frozen=True)
class AuditIssue:
    route_id: int
    kind: str
    detail: str


def segment_tangent(segment: Segment, point: Point2D | None = None) -> tuple[float, float]:
    """沿行进方向的单位切向；``point`` 只对圆弧有意义（缺省取起点）。"""
    if isinstance(segment, LineSegment2D):
        dx, dy = segment.end.x - segment.start.x, segment.end.y - segment.start.y
    else:
        anchor = segment.start if point is None else point
        sign = 1.0 if segment.sweep_rad > 0 else -1.0
        dx = -sign * (anchor.y - segment.center.y)
        dy = sign * (anchor.x - segment.center.x)
    norm = hypot(dx, dy)
    if norm == 0:
        raise ValueError("undefined tangent")
    return dx / norm, dy / norm


def _board_extent(segments: list[Segment]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    from .spacing import segment_aabb

    for segment in segments:
        box = segment_aabb(segment)
        xs.extend((box.min_x, box.max_x))
        ys.extend((box.min_y, box.max_y))
    return min(xs), min(ys), max(xs), max(ys)


def audit_geometry(
    spec: RouteSpec,
    segments: list[Segment],
    *,
    board_width: float = 150.0,
    board_height: float = 150.0,
    tol: float = 1e-9,
) -> list[AuditIssue]:
    """核验一条重建路线；返回问题列表（空列表表示通过）。"""
    issues: list[AuditIssue] = []
    rid = spec.route_id
    if not segments:
        return [AuditIssue(rid, "empty_geometry", "no segment reconstructed")]

    first, last = segments[0], segments[-1]
    if hypot(first.start.x - spec.sx, first.start.y - spec.sy) > max(tol, 1e-9):
        issues.append(
            AuditIssue(
                rid,
                "endpoint_mismatch",
                "start %r != spec (%r, %r)" % (first.start, spec.sx, spec.sy),
            )
        )
    if hypot(last.end.x - spec.lx, last.end.y - spec.ly) > max(tol, 1e-9):
        issues.append(
            AuditIssue(
                rid,
                "endpoint_mismatch",
                "end %r != spec (%r, %r)" % (last.end, spec.lx, spec.ly),
            )
        )

    for index, segment in enumerate(segments):
        if isinstance(segment, ArcSegment2D):
            radius = arc_segment_radius(segment)
            if abs(radius - spec.radius) > 1e-6:
                issues.append(
                    AuditIssue(
                        rid,
                        "radius_mismatch",
                        "arc %d radius %.9f != %.9f" % (index, radius, spec.radius),
                    )
                )
            continue

    for index in range(len(segments) - 1):
        a, b = segments[index], segments[index + 1]
        join = a.end
        if hypot(b.start.x - join.x, b.start.y - join.y) > max(tol, 1e-9):
            issues.append(
                AuditIssue(rid, "disconnected", "segment %d -> %d" % (index, index + 1))
            )
            continue
        tangent_a = segment_tangent(a, join)
        tangent_b = segment_tangent(b, join)
        dot = tangent_a[0] * tangent_b[0] + tangent_a[1] * tangent_b[1]
        if dot < 1 - 1e-6:
            issues.append(
                AuditIssue(
                    rid,
                    "tangent_discontinuity",
                    "segment %d -> %d dot=%.9f angle=%.6f deg"
                    % (index, index + 1, dot, _angle_deg(dot)),
                )
            )

    min_x, min_y, max_x, max_y = _board_extent(segments)
    if min_x < -tol or min_y < -tol or max_x > board_width + tol or max_y > board_height + tol:
        issues.append(
            AuditIssue(
                rid,
                "out_of_board",
                "extent [%.4f, %.4f] x [%.4f, %.4f]" % (min_x, min_y, max_x, max_y),
            )
        )
    return issues


def _angle_deg(dot: float) -> float:
    from math import acos, degrees

    return degrees(acos(max(-1.0, min(1.0, dot))))
