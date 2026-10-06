"""统一评价器：解析几何、全部交叉事件、逐路损耗与违规分类。

与 2D 项目里"原版统计"（``waveguide_calculator.calc_index``）并列，本模块给出
**解析物理统计**，两者都保留、都输出，后续所有算法对照都使用同一个解析评价器。

口径（与任务约定一致）：

* 交叉事件全网**只记录一次**（每对路线只测一次，同一对在同一位置的重复几何
  记录合并，同一对在不同位置的交叉点全部保留）；
* 逐路损耗中，一个交叉事件**分别计入两根波导各一次**，不做除以二的处理；
* 损耗 = 直线长度 × 传播损耗系数 + Σ 弧长 × 对应半径的弯曲损耗密度
  + Σ 交叉事件的角度损耗（表为论文图 3-12 数字化近似，角度按原版
  ``int()`` 截断查询）；
* 中心线相交本身**不是**违规：允许的交叉、重合、近并行间距不足分别统计，
  间距阈值是实验假设（见 :mod:`src.opt2d.spacing`）。
"""

from __future__ import annotations

import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from math import degrees, hypot
from typing import Iterable

from ..collision import (
    CurveRouteIntersection,
    find_smoothed_route_self_intersections_2d,
)
from ..models import ArcSegment2D, LineSegment2D, SmoothedRoute2D
from ..physical_intersections import consolidate_route_intersections_2d

from .geometry_audit import AuditIssue, audit_geometry
from .intersections import segment_intersections
from .legacy_bridge import legacy_modules
from .smoothing import RouteSpec, build_route_geometry
from .spacing import ContactEvent, aabb_gap, segment_aabb, spacing_report

__all__ = [
    "LossModel",
    "CrossingEvent",
    "SpacingEvent",
    "RouteRecord",
    "BoardEvaluation",
    "Evaluator",
]

Segment = LineSegment2D | ArcSegment2D


class LossModel:
    """2D 项目论文损耗模型的薄封装（不复制任何数值表）。"""

    def __init__(self, table=None):
        module = legacy_modules()["loss_model"]
        self._module = module
        self.table = table if table is not None else module.load_crossing_table()
        self.propagation_db_per_mm = module.PROPAGATION_LOSS_DB_PER_MM
        self.bend_radii = tuple(module.BEND_TABLE_RADII_MM)

    def straight_loss_db(self, length_mm: float) -> float:
        return self._module.straight_loss_db(length_mm)

    def bend_loss_db(self, radius_mm: float, arc_length_mm: float) -> float:
        return self._module.bend_loss_from_arc_db(radius_mm, arc_length_mm)

    def crossing_loss_db(self, angle_deg: float) -> float:
        return self._module.crossing_loss_db(max(1.0, angle_deg), self.table)

    def bend_loss_90_db(self, radius_mm: float) -> float:
        return self._module.bend_loss_90_db(radius_mm)


@dataclass
class CrossingEvent:
    """全网唯一的交叉事件（两段中心线在非端点处横穿）。"""

    route_a: int
    route_b: int
    x: float
    y: float
    angle_deg: float
    loss_db: float
    raw_event_count: int = 1


@dataclass
class SpacingEvent:
    """近并行间距不足（实验假设阈值的违规记录）。"""

    route_a: int
    route_b: int
    distance_mm: float
    x: float
    y: float


@dataclass
class PhysicalTouch:
    """整条路线合并后的物理接触事件（``raw_event_count`` 为合并了多少个段级事件）。

    与 :class:`SpacingEvent` 相同，一个物理接触在两根波导上各计一次损耗意义上的
    "事件"；但它是**按位置聚类后**的结果，解析段接缝处的重复不会重复计数。
    """

    route_a: int
    route_b: int
    x: float
    y: float
    raw_event_count: int = 1


@dataclass
class RouteRecord:
    """单条路线的几何与损耗明细。"""

    route_id: int
    port1: int | None
    port2: int | None
    index1: int | None
    index2: int | None
    sx: float
    sy: float
    lx: float
    ly: float
    track_y: float
    radius: float
    dx: float
    straight_length_mm: float
    arc_length_mm: float
    total_length_mm: float
    bend_angles_deg: list[float]
    bend_count: int
    geometry_kind: str = "u"
    alpha_deg: float = 0.0
    t0_fraction: float = 0.5
    crossing_events: list[CrossingEvent] = field(default_factory=list)
    straight_loss_db: float = 0.0
    bend_loss_db: float = 0.0
    crossing_loss_db: float = 0.0
    total_loss_db: float = 0.0
    issues: list[AuditIssue] = field(default_factory=list)

    @property
    def crossing_count(self) -> int:
        """逐路计入的交叉事件数（每个事件在本路计一次）。"""
        return len(self.crossing_events)

    @property
    def is_geometrically_valid(self) -> bool:
        return not self.issues


@dataclass
class BoardEvaluation:
    """一个布线的完整评价结果。"""

    label: str
    channels: int
    line_width_mm: float
    pitch_mm: float
    board_width: float
    board_height: float
    routes: list[RouteRecord]
    events: list[CrossingEvent]
    spacing_events: list[SpacingEvent]
    unplaced_ids: list[int]
    geometry_issues: list[AuditIssue]
    runtime_s: float
    stop_reason: str = "completed"
    notes: dict = field(default_factory=dict)
    contacts: list[ContactEvent] = field(default_factory=list)
    physical_touches: list[PhysicalTouch] = field(default_factory=list)

    @property
    def route_index(self) -> dict[int, RouteRecord]:
        return {record.route_id: record for record in self.routes}

    def losses(self) -> list[float]:
        return [record.total_loss_db for record in self.routes]

    def summary(self) -> dict:
        """平均 / P95 / 最大损耗、分解、长度、事件数与半径分布。"""
        losses = self.losses()
        if not losses:
            raise ValueError("no evaluated route")
        ordered = sorted(losses)
        worst = max(self.routes, key=lambda r: (r.total_loss_db, -r.route_id))
        crossing_angles = [event.angle_deg for event in self.events]
        summary = {
            "label": self.label,
            "channels": self.channels,
            "route_count": len(self.routes),
            "expected_routes": self.channels,
            "complete_connection": len(self.unplaced_ids) == 0,
            "unplaced_count": len(self.unplaced_ids),
            "unplaced_ids_sample": self.unplaced_ids[:20],
            "mean_loss_db": statistics.fmean(losses),
            "p95_loss_db": _percentile(ordered, 0.95),
            "max_loss_db": worst.total_loss_db,
            "min_loss_db": ordered[0],
            "std_loss_db": statistics.pstdev(losses),
            "worst_route_id": worst.route_id,
            "mean_straight_loss_db": statistics.fmean(r.straight_loss_db for r in self.routes),
            "mean_bend_loss_db": statistics.fmean(r.bend_loss_db for r in self.routes),
            "mean_crossing_loss_db": statistics.fmean(r.crossing_loss_db for r in self.routes),
            "sum_straight_loss_db": sum(r.straight_loss_db for r in self.routes),
            "sum_bend_loss_db": sum(r.bend_loss_db for r in self.routes),
            "sum_crossing_loss_db": sum(r.crossing_loss_db for r in self.routes),
            "mean_straight_length_mm": statistics.fmean(r.straight_length_mm for r in self.routes),
            "mean_arc_length_mm": statistics.fmean(r.arc_length_mm for r in self.routes),
            "mean_total_length_mm": statistics.fmean(r.total_length_mm for r in self.routes),
            "sum_total_length_mm": sum(r.total_length_mm for r in self.routes),
            "unique_crossing_events": len(self.events),
            "per_route_crossing_events": sum(r.crossing_count for r in self.routes),
            "mean_crossing_count": statistics.fmean(r.crossing_count for r in self.routes),
            "max_crossing_count": max(r.crossing_count for r in self.routes),
            "min_crossing_angle_deg": min(crossing_angles) if crossing_angles else None,
            "mean_crossing_angle_deg": (
                statistics.fmean(crossing_angles) if crossing_angles else None
            ),
            "spacing_violation_count": len(self.spacing_events),
            "spacing_violation_pairs": len(
                {(e.route_a, e.route_b) for e in self.spacing_events}
            ),
            "min_spacing_mm": (
                min(e.distance_mm for e in self.spacing_events) if self.spacing_events else None
            ),
            "contact_touch_count": sum(
                1 for event in self.contacts if event.kind == "touch"
            ),
            # 统计口径统一：接触分"段级 raw"与"整条路线合并后的物理"两套。
            # raw 来自 spacing_report 的逐段对判定（解析段接缝处的重复会重复计数）；
            # physical 来自 pair_events 的位置聚类合并，才是真实接触事件数。
            "raw_segment_touch_count": sum(
                1 for event in self.contacts if event.kind == "touch"
            ),
            "physical_route_touch_count": len(self.physical_touches),
            "raw_segment_cross_count": sum(e.raw_event_count for e in self.events),
            "contact_overlap_count": sum(
                1 for event in self.contacts if event.kind == "overlap"
            ),
            "geometry_issue_count": len(self.geometry_issues),
            "geometry_issue_kinds": dict(Counter(i.kind for i in self.geometry_issues)),
            "radius_distribution": dict(Counter(record.radius for record in self.routes)),
            "bend_count_distribution": dict(
                Counter(record.bend_count for record in self.routes)
            ),
            "runtime_s": self.runtime_s,
            "stop_reason": self.stop_reason,
        }
        summary.update(self.notes)
        return summary


def _percentile(ordered: list[float], fraction: float) -> float:
    """最近秩法分位数（不需要插值假设，对小样本更保守）。"""
    if not ordered:
        raise ValueError("empty sample")
    import math

    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


class Evaluator:
    """在给定线宽、间距与板尺寸下评价一组解析路线。"""

    def __init__(
        self,
        channels: int,
        *,
        line_width: float = 0.05,
        pitch: float | None = None,
        board_width: float = 150.0,
        board_height: float = 150.0,
        tol: float = 1e-9,
        loss_model: LossModel | None = None,
        check_spacing: bool = True,
        spacing_margin_mm: float = 0.0,
    ) -> None:
        self.channels = channels
        self.line_width = line_width
        self.pitch = pitch if pitch is not None else {256: 0.25, 512: 0.125}.get(channels, 0.25)
        self.board_width = board_width
        self.board_height = board_height
        self.tol = tol
        self.loss = loss_model if loss_model is not None else LossModel()
        self.check_spacing = check_spacing
        self.minimum_center_distance = self.line_width + self.pitch + spacing_margin_mm

    # ---- 几何构建 -----------------------------------------------------
    def build(
        self, specs: Iterable[RouteSpec]
    ) -> tuple[dict[int, list[Segment]], list[AuditIssue], list[int]]:
        segments: dict[int, list[Segment]] = {}
        issues: list[AuditIssue] = []
        unplaced: list[int] = []
        for spec in specs:
            try:
                built = build_route_geometry(spec, self.tol)
            except ValueError as exc:
                issues.append(AuditIssue(spec.route_id, "build_failed", str(exc)))
                unplaced.append(spec.route_id)
                continue
            found = audit_geometry(
                spec,
                built,
                board_width=self.board_width,
                board_height=self.board_height,
                tol=self.tol,
            )
            segments[spec.route_id] = built
            issues.extend(found)
        return segments, issues, unplaced

    # ---- 交叉事件 -----------------------------------------------------
    def pair_events(
        self,
        id_a: int,
        id_b: int,
        segments_a: list[Segment],
        segments_b: list[Segment],
        boxes_a=None,
        boxes_b=None,
    ) -> list:
        """一对路线的全部物理事件（AABB 预筛 + 解析求交 + 位置去重）。

        ``boxes_a`` / ``boxes_b`` 可传入预先算好的段包围盒，避免重复计算。
        """
        boxes_a = boxes_a if boxes_a is not None else [segment_aabb(s) for s in segments_a]
        boxes_b = boxes_b if boxes_b is not None else [segment_aabb(s) for s in segments_b]
        raw: list[CurveRouteIntersection] = []
        for i, box_a in enumerate(boxes_a):
            inner = segments_a[i]
            for j, box_b in enumerate(boxes_b):
                if aabb_gap(box_a, box_b) > self.tol:
                    continue
                outer = segments_b[j]
                for event in segment_intersections(inner, outer, self.tol):
                    raw.append(
                        CurveRouteIntersection(
                            id_a,
                            id_b,
                            i,
                            j,
                            type(inner).__name__,
                            type(outer).__name__,
                            event.kind,
                            event.point,
                        )
                    )
        if not raw:
            return []
        return consolidate_route_intersections_2d(
            SmoothedRoute2D(id_a, segments_a),
            SmoothedRoute2D(id_b, segments_b),
            raw,
            self.tol,
            1e-9,
        )

    # ---- 主评价 -------------------------------------------------------
    def evaluate(
        self,
        specs: list[RouteSpec],
        *,
        label: str,
        segments: dict[int, list[Segment]] | None = None,
        issues: list[AuditIssue] | None = None,
        unplaced: list[int] | None = None,
        runtime_s: float | None = None,
        stop_reason: str = "completed",
        notes: dict | None = None,
        progress: bool = False,
    ) -> BoardEvaluation:
        started = time.perf_counter()
        if segments is None:
            segments, issues, unplaced = self.build(specs)
        issues = list(issues or [])
        unplaced = list(unplaced or [])
        specs_by_id = {spec.route_id: spec for spec in specs}
        ids = sorted(segments)

        events: list[CrossingEvent] = []
        physical_touches: list[PhysicalTouch] = []
        per_route_events: dict[int, list[CrossingEvent]] = {rid: [] for rid in ids}
        boxes = {rid: [segment_aabb(s) for s in segments[rid]] for rid in ids}
        route_boxes = {
            rid: (
                min(b.min_x for b in boxes[rid]),
                min(b.min_y for b in boxes[rid]),
                max(b.max_x for b in boxes[rid]),
                max(b.max_y for b in boxes[rid]),
            )
            for rid in ids
        }
        from .spacing import Aabb

        outer_boxes = {
            rid: Aabb(*route_boxes[rid]) for rid in ids
        }
        # 路线级预筛：检查间距时用**间距阈值**，否则用 tol —— 包围盒不相交
        # 但仍可能近并行（间距违规）的路线对不能被跳过。
        reach = (
            max(self.tol, self.minimum_center_distance) if self.check_spacing else self.tol
        )
        for index, id_a in enumerate(ids):
            if progress and index % 64 == 0:
                print("  pair scan %d/%d ..." % (index, len(ids)), flush=True)
            for id_b in ids[index + 1:]:
                if aabb_gap(outer_boxes[id_a], outer_boxes[id_b]) > reach:
                    continue
                for event in self.pair_events(
                    id_a, id_b, segments[id_a], segments[id_b], boxes[id_a], boxes[id_b]
                ):
                    if event.kind == "cross":
                        angle = degrees(event.crossing_angle_rad or 0.0)
                        recorded = CrossingEvent(
                            event.route_a_id,
                            event.route_b_id,
                            event.point.x,
                            event.point.y,
                            angle,
                            self.loss.crossing_loss_db(angle),
                            event.raw_event_count,
                        )
                        events.append(recorded)
                        # 唯一事件分别计入两根波导各一次。
                        per_route_events[id_a].append(recorded)
                        per_route_events[id_b].append(recorded)
                    elif event.kind == "overlap":
                        issues.append(
                            AuditIssue(
                                event.route_a_id,
                                "overlap",
                                "route %d and %d share a common locus"
                                % (event.route_a_id, event.route_b_id),
                            )
                        )
                    elif event.kind == "touch" and event.point is not None:
                        # 物理接触：已按位置聚类，raw_event_count 记录合并了几个段级事件。
                        physical_touches.append(
                            PhysicalTouch(
                                event.route_a_id,
                                event.route_b_id,
                                event.point.x,
                                event.point.y,
                                event.raw_event_count,
                            )
                        )

        # 自交检查（原版 U 型几何不应出现）。
        for rid in ids:
            for event in find_smoothed_route_self_intersections_2d(
                SmoothedRoute2D(rid, segments[rid]), self.tol
            ):
                issues.append(
                    AuditIssue(rid, "self_intersection", "segment pair %d/%d %s"
                               % (event.segment_index_a, event.segment_index_b, event.kind))
                )

        spacing_events: list[SpacingEvent] = []
        contacts: list[ContactEvent] = []
        if self.check_spacing:
            report = spacing_report(segments, self.minimum_center_distance, self.tol)
            contacts = report.contacts
            for violation in report.violations:
                spacing_events.append(
                    SpacingEvent(
                        violation.route_a,
                        violation.route_b,
                        violation.distance_mm,
                        violation.point_a.x,
                        violation.point_a.y,
                    )
                )

        records: list[RouteRecord] = []
        for rid in ids:
            spec = specs_by_id[rid]
            built = segments[rid]
            straight, arc = _lengths(built)
            bend_angles = [
                degrees(abs(s.sweep_rad)) for s in built if isinstance(s, ArcSegment2D)
            ]
            record = RouteRecord(
                route_id=rid,
                port1=spec.port1,
                port2=spec.port2,
                index1=spec.index1,
                index2=spec.index2,
                sx=spec.sx,
                sy=spec.sy,
                lx=spec.lx,
                ly=spec.ly,
                track_y=spec.track_y,
                radius=spec.radius,
                dx=spec.dx,
                straight_length_mm=straight,
                arc_length_mm=arc,
                total_length_mm=straight + arc,
                bend_angles_deg=bend_angles,
                bend_count=len(bend_angles),
                geometry_kind=getattr(spec, "kind", "u"),
                alpha_deg=float(getattr(spec, "alpha_deg", 0.0)),
                t0_fraction=float(getattr(spec, "t0_fraction", 0.5)),
            )
            record.crossing_events = per_route_events[rid]
            record.straight_loss_db = self.loss.straight_loss_db(straight)
            record.bend_loss_db = self.loss.bend_loss_db(spec.radius, arc)
            record.crossing_loss_db = sum(e.loss_db for e in record.crossing_events)
            record.total_loss_db = (
                record.straight_loss_db + record.bend_loss_db + record.crossing_loss_db
            )
            record.issues = [issue for issue in issues if issue.route_id == rid]
            records.append(record)

        return BoardEvaluation(
            label=label,
            channels=self.channels,
            line_width_mm=self.line_width,
            pitch_mm=self.pitch,
            board_width=self.board_width,
            board_height=self.board_height,
            routes=records,
            events=events,
            spacing_events=spacing_events,
            unplaced_ids=unplaced,
            geometry_issues=issues,
            runtime_s=runtime_s if runtime_s is not None else time.perf_counter() - started,
            stop_reason=stop_reason,
            notes=dict(notes or {}),
            contacts=contacts,
            physical_touches=physical_touches,
        )


def _lengths(segments: list[Segment]) -> tuple[float, float]:
    straight = 0.0
    arc = 0.0
    for segment in segments:
        if isinstance(segment, LineSegment2D):
            straight += hypot(segment.end.x - segment.start.x, segment.end.y - segment.start.y)
        else:
            arc += abs(segment.sweep_rad) * hypot(
                segment.start.x - segment.center.x, segment.start.y - segment.center.y
            )
    return straight, arc
