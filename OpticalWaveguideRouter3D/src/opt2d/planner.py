"""候选轨道与自适应半径布线器（方案 C/D）。

从原版"第一个可用轨道"改为**多个可行候选**：

1. 用原版 ``noCross`` 语义（忠实复刻自 ``wiring_rect_826.plotter_rect``）枚举
   当前状态下所有可行轨道；
2. 对候选做解析几何可行性检查（端点、板边界、弯曲空间、切向连接）；
3. 评分含**受影响既有路线的损耗增量**：一个交叉事件给两根波导各加一次损耗，
   因此对全网总损耗的增量是事件损耗的两倍，评分中按此计入，避免"只优化新
   路线、把交叉代价留给别人"；
4. 顺序策略可选：``legacy``（原版顺序）、``span``（跨度优先）、
   ``congestion``（预计拥塞优先）；
5. 支持有界拆线重布：移除高损耗路线后重布，失败则整体恢复；
6. 保留端口连接关系；同端口出线顺序沿用原版 ``_reorder_by_port`` 机制。

半径策略 ``adaptive`` 时，候选是 (轨道, 半径) 组合，首版半径取自
``radii``（默认 5 / 6 mm，二者都有实测弯曲损耗数据）。
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from math import degrees, hypot
from copy import deepcopy
from typing import Iterable

import pandas as pd

from ..geometry import arc_segment_radius
from ..models import ArcSegment2D, LineSegment2D

from .evaluator import Evaluator, LossModel, _lengths
from .freeform import (
    DEFAULT_ALPHAS_DEG,
    DEFAULT_T0_FRACTIONS,
    FreeformParams,
    build_freeform_geometry,
    freeform_candidates,
)
from .geometry_audit import AuditIssue, audit_geometry
from .intersections import segment_intersections
from .smoothing import RouteSpec, build_route_geometry
from .spacing import Aabb, aabb_gap, segment_aabb, segment_min_distance

__all__ = ["PlanConfig", "PlannedRoute", "PlanResult", "Planner", "ORDER_STRATEGIES"]

ORDER_STRATEGIES = ("legacy", "span", "congestion")


@dataclass
class PlanConfig:
    """一次布线的确定性配置。"""

    channels: int
    line_width: float = 0.05
    pitch: float | None = None
    board_height: float = 150.0
    board_width: float = 150.0
    candidate_limit: int = 8
    order_strategy: str = "legacy"
    radius_policy: str = "fixed"
    radii: tuple[float, ...] = (5.0,)
    crossing_weight: float = 2.0
    #: 候选在扫描顺序中的位置惩罚（dB/位）。原版"第一个可用轨道"的保守位置
    #: 会为后续跨区路线留出中间通道；纯损耗评分可能把路线挤向中间，导致后面
    #: 的路线无可行轨道。该正则项越小越激进、越大越接近原版，消融时对照。
    position_penalty: float = 0.0
    #: 半径策略：``fixed`` 只用 ``radii[0]``；``adaptive`` 枚举全部半径按评分选择；
    #: ``fallback`` 按 ``radii`` 顺序取第一个几何可行的半径（D0：优先 R6，
    #: 不可行才退回 R5），每个轨道只取一个候选、不排序。
    #: 控制台端口重排（原版会交换同端口槽位以满足出线顺序）。Step 13 默认关闭，
    #: 因为冻结端点要求逐路保持 A 的 ``sx``/``lx``；开启时必须单独命名与对照。
    allow_port_reorder: bool = False
    #: 自由弯角 S 形路径（Step 13 第三阶段）。仅对跨上下两侧的连接启用，
    #: 候选为"直线引出段 + 圆弧 + 斜向直线 + 圆弧 + 直线引入段"。
    enable_freeform: bool = False
    freeform_alphas_deg: tuple[float, ...] = ()
    freeform_t0_fractions: tuple[float, ...] = ()
    #: 自由弯角候选的预筛名额（按不含交叉的自损耗排序取前若干个再完整评分）。
    freeform_shortlist: int = 6
    #: 间距违规的惩罚（dB/路线对）。默认 0 = 只记录不惩罚；overlap 永远硬拒绝。
    #: 与 ``touch_penalty_db`` **分开配置**：接触（物理级）与近并行间距是两类
    #: 不同风险，混用一个权重无法区分它们的贡献。
    spacing_penalty_db: float = 0.0
    #: 物理接触事件的惩罚（dB/事件）。计数来自 pair_events 的位置聚类合并，
    #: 解析段接缝处的重复不会重复计数（与评价器的 physical_route_touch_count 一致）。
    touch_penalty_db: float = 0.0
    #: 逐路半径冻结：``{route_id: radius}``。给定后该路线只用指定半径（用于
    #: "同一组半径下比较结构差异"的公平对照，例如用 D56 的逐路半径跑自由弯角）。
    radius_overrides: dict | None = None
    #: 小角交叉限制（受约束自由弯角实验）：角度小于 ``small_angle_deg`` 的交叉
    #: 事件每个额外计入 ``small_angle_penalty_db``（dB）。0 = 关闭。
    #: 交叉损耗表在小角度处是数字化近似，该惩罚用于把"不确定的收益"压回去。
    small_angle_deg: float = 0.0
    small_angle_penalty_db: float = 0.0
    tol: float = 1e-9

    def resolved_pitch(self) -> float:
        if self.pitch is not None:
            return self.pitch
        return {256: 0.25, 512: 0.125}.get(self.channels, 0.25)


@dataclass
class PlannedRoute:
    spec: RouteSpec
    segments: list
    score: float
    candidates: int
    issues: list[AuditIssue] = field(default_factory=list)


@dataclass
class PlanResult:
    config: PlanConfig
    routes: dict[int, PlannedRoute]
    unplaced: list[int]
    runtime_s: float
    stop_reason: str
    stats: dict = field(default_factory=dict)

    def specs(self) -> list[RouteSpec]:
        return [self.routes[rid].spec for rid in sorted(self.routes)]

    def segments(self) -> dict[int, list]:
        return {rid: self.routes[rid].segments for rid in sorted(self.routes)}


@dataclass
class _Track:
    y: float
    WGs: list = field(default_factory=list)
    rEnd: list = field(default_factory=lambda: [-1])
    lEnd: list = field(default_factory=lambda: [100])


@dataclass
class _Node:
    x: list = field(default_factory=list)
    y: list = field(default_factory=list)


@dataclass
class PlannerSnapshot:
    """布线器完整状态快照（提交顺序 + 冻结 pass 边界）。"""

    entries: list
    context: dict = field(default_factory=dict)


class Planner:
    """原版四遍结构 + 多候选评分 + 有界拆线重布。"""

    def __init__(self, config: PlanConfig, evaluator: Evaluator):
        self.config = config
        self.evaluator = evaluator
        self.loss: LossModel = evaluator.loss
        self.n = config.channels
        self.height = config.board_height
        self.width = config.board_width
        self.tol = config.tol
        # 原版 plotter_rect 的 ``dist`` 参数是轨道节距（标称间隔 + 线宽），
        # 同时用于 ln_calc 与轨道栅格步长。
        self.track_pitch = config.resolved_pitch() + config.line_width
        self.sn_calc_radius = max(config.radii) if config.radii else 5.0
        self.tracks: list[_Track] = []
        self.nodes = None
        self._boxes: dict[int, list[Aabb]] = {}
        self._route_boxes: dict[int, Aabb] = {}
        self.committed: dict[int, PlannedRoute] = {}
        self._journal: list = []
        self._frozen_context: dict = {}

    # ---- 原版辅助函数（忠实复刻 wiring_rect_826） ---------------------
    def _yy(self) -> list[float]:
        step = int(self.track_pitch * 1000)
        return [
            round(i * 0.001, 3)
            for i in range(
                5 * 1000, (int(self.height) - 5) * 1000, step
            )
        ]

    def _ln_calc(self, lx, ly):
        if self.n == 256:
            offset = 6.5 if ly == self.height else 2
            return max(int(round((lx - offset) % 9, 3) / self.track_pitch) - 6, 4)
        if self.n == 512:
            offset = 4 if ly == self.height else 2
            return max(int(round((lx - offset) % 4.5, 3) / self.track_pitch) - 6, 4)
        raise ValueError("ln_calc only defined for 256/512")

    def _sn_calc(self, idx2, y, is_below=True):
        if idx2 >= len(self.nodes.MTabove):
            return 8
        if is_below:
            for i, it in enumerate(self.nodes.MTbelow[idx2].y):
                if it >= y + self.sn_calc_radius:
                    return i
                if it >= y:
                    return -i
        else:
            for i, it in enumerate(self.nodes.MTabove[idx2].y):
                if it <= y - self.sn_calc_radius:
                    return i
                if it <= y:
                    return -i
        return 8

    def _no_cross(self, lEnd, rEnd, i, wgyset, _type="below", lx=0, ly=0):
        if _type == "below":
            for j in range(1, max(self._ln_calc(lx, ly) - self._sn_calc(lEnd + 1, wgyset[i].y), 4)):
                if (i >= j and wgyset[i - j].WGs and wgyset[i - j].rEnd[-1] < rEnd
                        and wgyset[i - j].lEnd[-1] < lEnd):
                    return False
                if i >= j and len(wgyset[i - j].rEnd) > 2 and wgyset[i - j].rEnd[-2] < lEnd:
                    return False
            for j in range(1, 8):
                if i + j < len(wgyset) and wgyset[i + j].WGs and wgyset[i + j].rEnd[-1] > lEnd:
                    return False
        elif _type == "above2below":
            for j in range(1, max(self._ln_calc(lx, ly) - self._sn_calc(lEnd + 1, wgyset[i].y), 3)):
                if i >= j and wgyset[i - j].WGs and wgyset[i - j].lEnd[-1] < lEnd:
                    return False
            for j in range(1, 6):
                if i + j < len(wgyset) and wgyset[i + j].WGs and wgyset[i + j].rEnd[-1] > lEnd:
                    return False
        elif _type == "above":
            for j in range(1, max(self._ln_calc(lx, ly) - self._sn_calc(lEnd + 1, wgyset[i].y, False), 4)):
                if i + j < len(wgyset) and wgyset[i + j].WGs and wgyset[i + j].rEnd[-1] != rEnd:
                    return False
                if i + j < len(wgyset) and len(wgyset[i + j].rEnd) > 1 and wgyset[i + j].rEnd[-2] > lEnd:
                    return False
            for j in range(1, 8):
                if i >= j and wgyset[i - j].WGs and wgyset[i - j].rEnd[-1] > lEnd:
                    return False
        elif _type == "below2above":
            for j in range(1, 6):
                if i >= j and wgyset[i - j].WGs and wgyset[i - j].rEnd[-1] > lEnd:
                    return False
            for j in range(1, max(self._ln_calc(lx, ly) - self._sn_calc(lEnd + 1, wgyset[i].y, False), 3)):
                if i + j < len(wgyset) and wgyset[i + j].WGs and wgyset[i + j].rEnd[-1] > rEnd:
                    return False
        return True

    def _init_nodes(self, df):
        class _MTset:
            pass

        nodes = _MTset()
        nodes.MTabove = [_Node(x=[], y=[0] * 16) for _ in range(int(self.n / 16))]
        nodes.MTbelow = [_Node(x=[], y=[self.height] * 16) for _ in range(int(self.n / 16))]

        def add_port(row):
            l = int(self.n / 16)
            if row.index1 >= l:
                nodes.MTbelow[int(row.index1 - l)].x.append(row.sx)
            else:
                nodes.MTabove[int(row.index1)].x.append(row.sx)
            if row.index2 >= l:
                nodes.MTbelow[int(row.index2 - l)].x.append(row.lx)
            else:
                nodes.MTabove[int(row.index2)].x.append(row.lx)

        df.apply(add_port, axis=1)
        for mt in nodes.MTabove + nodes.MTbelow:
            mt.x.sort()
        return nodes

    # ---- 几何与评分 ---------------------------------------------------
    def _make_spec(
        self,
        row,
        track_y: float,
        radius: float,
        *,
        kind: str = "u",
        alpha_deg: float = 0.0,
        t0_fraction: float = 0.5,
    ) -> RouteSpec:
        return RouteSpec(
            route_id=int(row.name),
            sx=float(row.sx),
            sy=float(row.sy),
            lx=float(row.lx),
            ly=float(row.ly),
            track_y=float(track_y),
            radius=float(radius),
            port1=int(row.Port1),
            port2=int(row.Port2),
            index1=int(row.index1),
            index2=int(row.index2),
            kind=kind,
            alpha_deg=float(alpha_deg),
            t0_fraction=float(t0_fraction),
        )

    def _spec(self, row, track_y: float, radius: float) -> RouteSpec:
        return self._make_spec(row, track_y, radius)

    def _build_spec(self, spec: RouteSpec):
        """按几何族构造解析段并核验（U 型或自由弯角 S 形）。"""
        if spec.kind == "freeform":
            params = FreeformParams(
                route_id=spec.route_id,
                sx=spec.sx,
                sy=spec.sy,
                lx=spec.lx,
                ly=spec.ly,
                radius=spec.radius,
                alpha_deg=spec.alpha_deg,
                t0_fraction=spec.t0_fraction,
            )
            built = build_freeform_geometry(params, self.tol)
        else:
            built = build_route_geometry(spec, self.tol)
        issues = audit_geometry(
            spec,
            built,
            board_width=self.width,
            board_height=self.height,
            tol=self.tol,
        )
        return built, issues

    def _build(self, spec: RouteSpec):
        return self._build_spec(spec)

    def _candidate_cost(self, row, track_y: float, radius: float) -> float:
        """与既有路线无关的代价：直线 + 弯曲损耗（用于预筛，不做交叉计算）。"""
        return self._spec_cost(self._spec(row, track_y, radius))

    def _spec_cost(self, spec: RouteSpec) -> float:
        try:
            built, issues = self._build_spec(spec)
        except ValueError:
            return float("inf")
        if issues:
            return float("inf")
        straight, arc = _lengths(built)
        return self.loss.straight_loss_db(straight) + self.loss.bend_loss_db(
            spec.radius, arc
        )

    def _pair_metrics(
        self,
        id_a: int,
        segments_a: list,
        boxes_a: list[Aabb],
        id_b: int,
        segments_b: list,
        boxes_b: list[Aabb],
    ) -> tuple[float, int, int, int, int]:
        """一对路线的（交叉损耗、接触数、重合数、间距违规数、小角交叉数）。

        这是候选接受与否的硬性依据：重合直接让候选非法，接触、间距违规与小角
        交叉按配置权重计入评分，避免"仅凭弯曲损耗降低就接受"。

        计数单位与最终报告一致：交叉与接触按**事件**计数（同一条路线的两个
        不同位置是两次事件），间距违规按**路线对**计数（一对路线最多一次，
        与 :func:`src.opt2d.spacing.spacing_report` 的 SpacingViolation 口径相同），
        避免"一条路线被拆成更多解析段就增加惩罚次数"。
        """
        crossing = 0.0
        touch = 0
        overlap = 0
        small_angle = 0
        small_limit = float(self.config.small_angle_deg)
        for event in self.evaluator.pair_events(
            id_a, id_b, segments_a, segments_b, boxes_a, boxes_b
        ):
            if event.kind == "cross":
                angle = degrees(event.crossing_angle_rad or 0.0)
                crossing += self.loss.crossing_loss_db(angle)
                if small_limit > 0.0 and angle < small_limit:
                    small_angle += 1
            elif event.kind == "touch":
                touch += 1
            elif event.kind == "overlap":
                overlap += 1
        threshold = self.evaluator.minimum_center_distance
        spacing = 0
        for index_a, box_a in enumerate(boxes_a):
            if spacing:
                break
            for index_b, box_b in enumerate(boxes_b):
                if aabb_gap(box_a, box_b) >= threshold - self.tol:
                    continue
                inner, outer = segments_a[index_a], segments_b[index_b]
                if segment_intersections(inner, outer, self.tol):
                    continue  # 已由交叉/接触/重合统计覆盖
                distance, _, _ = segment_min_distance(inner, outer, self.tol)
                if distance < threshold - self.tol:
                    spacing = 1  # 路线对级：与报告口径一致
                    break
        return crossing, touch, overlap, spacing, small_angle

    def _score_spec(self, spec: RouteSpec):
        """候选代价：自身损耗 + 对既有路线新增交叉的两倍贡献 + 接触/间距惩罚。"""
        try:
            built, issues = self._build_spec(spec)
        except ValueError:
            return float("inf"), [], None
        if issues:
            return float("inf"), [], None
        straight, arc = _lengths(built)
        own = self.loss.straight_loss_db(straight) + self.loss.bend_loss_db(
            spec.radius, arc
        )
        boxes = [segment_aabb(s) for s in built]
        box = Aabb(
            min(b.min_x for b in boxes),
            min(b.min_y for b in boxes),
            max(b.max_x for b in boxes),
            max(b.max_y for b in boxes),
        )
        crossing = 0.0
        touch_count = 0
        spacing_count = 0
        small_angle = 0
        # 路线级 AABB 预筛必须用**间距阈值**：包围盒不相交（或间隙小于阈值）的
        # 路线对仍可能有近并行间距不足；用 tol 预筛会把这类近邻整个跳过。
        reach = (
            max(self.tol, self.evaluator.minimum_center_distance)
            if self.evaluator.check_spacing
            else self.tol
        )
        for other_id, other in self.committed.items():
            if aabb_gap(box, self._route_boxes[other_id]) > reach:
                continue
            cross, touch, overlap, spacing, small = self._pair_metrics(
                spec.route_id, built, boxes, other_id, other.segments, self._boxes[other_id]
            )
            if overlap:
                return float("inf"), [], None  # 重合是几何违规，硬拒绝
            crossing += cross
            touch_count += touch
            spacing_count += spacing
            small_angle += small
        score = (
            own
            + self.config.crossing_weight * crossing
            + self.config.touch_penalty_db * touch_count
            + self.config.spacing_penalty_db * spacing_count
            + self.config.small_angle_penalty_db * small_angle
        )
        return score, built, spec

    def _score(self, row, track_y: float, radius: float):
        return self._score_spec(self._spec(row, track_y, radius))

    # ---- 顺序策略 -----------------------------------------------------
    def _order(self, rows: pd.DataFrame, pass_type: str) -> pd.DataFrame:
        strategy = self.config.order_strategy
        if strategy == "legacy":
            # 原版：below / above 两遍按 sx 升序，两个跨区遍按 sx 降序。
            ascending = pass_type in ("below", "above")
            return rows.sort_values(by="sx", ascending=ascending)
        if strategy == "span":
            return rows.assign(_span=(rows.sx - rows.lx).abs()).sort_values(
                by=["_span", "sx"], ascending=[False, True]
            )
        if strategy == "congestion":
            density = self._congestion_scores(rows)
            return rows.assign(_cong=rows.index.map(density)).sort_values(
                by=["_cong", "sx"], ascending=[False, True]
            )
        raise ValueError("unknown order strategy %r" % strategy)

    def _congestion_scores(self, rows: pd.DataFrame) -> dict:
        """预计拥塞：该路线水平跨度内其他路线端点的密度（确定性、与顺序无关）。"""
        points = sorted(float(x) for x in pd.concat([rows["sx"], rows["lx"]]))
        scores = {}
        for row_id, row in rows.iterrows():
            lo, hi = sorted((float(row.sx), float(row.lx)))
            span = max(hi - lo, self.track_pitch)
            count = sum(1 for x in points if lo <= x <= hi)
            scores[row_id] = count / span
        return scores

    # ---- 主流程 -------------------------------------------------------
    def plan(self, df_ports: pd.DataFrame) -> PlanResult:
        started = time.perf_counter()
        df = df_ports.copy()
        self._df = df
        self.tracks = [_Track(y=y) for y in self._yy()]
        self.nodes = self._init_nodes(df)
        self.committed = {}
        self._boxes = {}
        self._route_boxes = {}
        self._journal = []
        stats = {"passes": {}}

        below_rows = df[(df["sy"] == 0) & (df["ly"] == 0)]
        above_rows = df[(df["sy"] != 0) & (df["ly"] != 0)]
        below_above_rows = df[(df["sy"] == 0) & (df["ly"] != 0)]
        above_below_rows = df[(df["sy"] != 0) & (df["ly"] == 0)]

        self._run_pass(below_rows, "below", stats)
        self._run_pass(above_rows, "above", stats)
        below_line = max((r.spec.track_y for r in self.committed.values() if r.spec.sy == 0 and r.spec.ly == 0), default=None)
        above_line = min((r.spec.track_y for r in self.committed.values() if r.spec.sy != 0 and r.spec.ly != 0), default=None)
        self._run_pass(below_above_rows, "below2above", stats,
                       above_line=above_line, below_line=None)
        b2a_line = min((r.spec.track_y for r in self.committed.values()
                        if r.spec.sy == 0 and r.spec.ly != 0), default=None)
        self._run_pass(above_below_rows, "above2below", stats,
                       above_line=None, below_line=below_line, b2a_line=b2a_line)

        if self.config.allow_port_reorder:
            # 仅在显式启用时使用原版的同端口槽位交换（会改变逐路端点）。
            self._reorder_ports(below_rows, "below")
            self._reorder_ports(above_rows, "above")
        # 冻结 pass 边界：拆线重布必须复用同一组边界，否则重布会因边界变化而失败。
        self._frozen_context = self._pass_context()

        unplaced = [rid for rid in (int(v) for v in df.index) if rid not in self.committed]
        return PlanResult(
            config=self.config,
            routes=dict(self.committed),
            unplaced=unplaced,
            runtime_s=time.perf_counter() - started,
            stop_reason="completed" if not unplaced else "incomplete",
            stats={"passes": stats, "order_strategy": self.config.order_strategy},
        )

    def _run_pass(self, rows, pass_type, stats, **kwargs):
        if rows.empty:
            return
        ordered = self._order(rows, pass_type)
        scan_reversed = pass_type in ("above", "below2above")
        considered = 0
        chosen_scores = []
        for _, row in ordered.iterrows():
            if int(row.name) in self.committed:
                continue
            candidates = self._candidates(row, pass_type, scan_reversed, **kwargs)
            considered += len(candidates)
            if not candidates:
                continue
            best = candidates[0]
            chosen_scores.append(best[0])
            self._commit(row, best[3], best[2], best[1], best[0])
        stats[pass_type] = {
            "placed": len(chosen_scores),
            "candidates_considered": considered,
            "mean_candidate_cost": (sum(chosen_scores) / len(chosen_scores)) if chosen_scores else None,
        }

    def _track_allowed(self, pass_type, i, idx1, idx2, above_line, below_line) -> bool:
        """原版各 pass 的轨道范围前置条件（逐字复刻）。"""
        w = self.tracks[i]
        if pass_type in ("below", "above"):
            return idx2 >= w.rEnd[-1]
        if pass_type == "below2above":
            if above_line is not None and w.y >= above_line:
                return False
            if idx2 < w.rEnd[-1]:
                return False
            return idx1 != w.rEnd[-1]
        # above2below
        if below_line is not None and w.y < below_line:
            return False
        return idx2 > w.rEnd[-1]

    def _cross_allowed(self, pass_type, row, i, idx1, idx2) -> bool:
        """原版 ``noCross`` 语义的调度（不同 pass 传入的原点坐标不同）。"""
        if pass_type == "below":
            return self._no_cross(idx2, idx1, i, self.tracks, _type="below",
                                  lx=float(row["lx"]), ly=float(row["ly"]))
        if pass_type == "above":
            return self._no_cross(idx2, idx1, i, self.tracks, _type="above",
                                  lx=float(row["lx"]), ly=float(row["ly"]))
        if pass_type == "below2above":
            return self._no_cross(idx2, idx1, i, self.tracks, _type="below2above",
                                  lx=float(row["sx"]), ly=float(row["sy"]))
        return self._no_cross(idx2, idx1, i, self.tracks, _type="above2below",
                              lx=float(row["lx"]), ly=float(row["ly"]))

    def _pass_indices(self, row, pass_type) -> tuple[int, int]:
        if pass_type == "below":
            return int(row["index1"] - self.n / 16), int(row["index2"] - self.n / 16)
        if pass_type == "above":
            return int(row["index1"]), int(row["index2"])
        if pass_type == "below2above":
            return int(row["index1"] - self.n / 16), int(row["index2"])
        return int(row["index1"]), int(row["index2"] - self.n / 16)

    def _candidates(self, row, pass_type, scan_reversed, **kwargs):
        """枚举当前状态下所有可行 (轨道, 半径) 候选，预筛后完整评分。"""
        policy = self.config.radius_policy
        override = None
        if self.config.radius_overrides:
            override = self.config.radius_overrides.get(int(row.name))
        if override is not None:
            radii = (float(override),)
        else:
            radii = (
                self.config.radii
                if policy in ("adaptive", "fallback")
                else self.config.radii[:1]
            )
        idx1, idx2 = self._pass_indices(row, pass_type)
        above_line = kwargs.get("above_line")
        below_line = kwargs.get("below_line")
        order: Iterable[int] = range(len(self.tracks))
        if scan_reversed:
            order = range(len(self.tracks) - 1, -1, -1)
        limit = max(1, int(self.config.candidate_limit))

        if policy == "fallback":
            # D0：按原版扫描顺序找轨道，每个轨道按 radii 优先级取第一个几何可行的
            # 半径（优先 R6，不可行才退回 R5）；只保留扫描顺序，不做评分排序。
            picked: list[tuple[float, int, float]] = []
            for i in order:
                if not self._track_allowed(pass_type, i, idx1, idx2, above_line, below_line):
                    continue
                if not self._cross_allowed(pass_type, row, i, idx1, idx2):
                    continue
                for radius in radii:
                    cost = self._candidate_cost(row, self.tracks[i].y, radius)
                    if cost != float("inf"):
                        picked.append((cost, i, radius))
                        break
                if len(picked) >= limit:
                    break
            scored = []
            for _, index, radius in picked:
                cost, built, spec = self._score(row, self.tracks[index].y, radius)
                if cost == float("inf"):
                    continue
                scored.append((cost, built, spec, index))
            return scored

        feasible: dict[float, list[tuple[float, int]]] = {r: [] for r in radii}
        for i in order:
            if not self._track_allowed(pass_type, i, idx1, idx2, above_line, below_line):
                continue
            if not self._cross_allowed(pass_type, row, i, idx1, idx2):
                continue
            for radius in radii:
                cost = self._candidate_cost(row, self.tracks[i].y, radius)
                if cost == float("inf"):
                    continue
                feasible[radius].append((cost, i))

        # 预筛：每个半径独立按"预筛代价 + 原版扫描顺序"排序，各取前
        # candidate_limit 个。跨区路线的直线长度与轨道无关，代价在数学上相同；
        # 量化到 1e-9 抹掉浮点噪声，使并列候选严格按原版扫描顺序排列，
        # candidate_limit=1 时退化为原版选择。半径之间互不挤占候选名额。
        shortlist: list[tuple[int, int, float]] = []
        for radius in radii:
            lst = feasible[radius]
            lst.sort(
                key=lambda item: (
                    round(item[0], 9),
                    -item[1] if scan_reversed else item[1],
                )
            )
            for rank, (_, index) in enumerate(lst[:limit]):
                shortlist.append((rank, index, radius))

        scored = []
        penalty = float(self.config.position_penalty)
        for rank, index, radius in shortlist:
            cost, built, spec = self._score(row, self.tracks[index].y, radius)
            if cost == float("inf"):
                continue
            scored.append((cost + penalty * rank, built, spec, index))

        # ---- 自由弯角 S 形候选（仅跨上下两侧的连接，Step 13 第三阶段）----
        if self.config.enable_freeform and abs(float(row["ly"]) - float(row["sy"])) > self.tol:
            alphas = self.config.freeform_alphas_deg or DEFAULT_ALPHAS_DEG
            fractions = self.config.freeform_t0_fractions or DEFAULT_T0_FRACTIONS
            free_costs: list[tuple[float, RouteSpec]] = []
            for radius in radii:
                for params in freeform_candidates(row, radius, alphas, fractions):
                    spec = self._make_spec(
                        row,
                        0.0,
                        radius,
                        kind="freeform",
                        alpha_deg=params.alpha_deg,
                        t0_fraction=params.t0_fraction,
                    )
                    cost = self._spec_cost(spec)
                    if cost == float("inf"):
                        continue
                    free_costs.append((cost, spec))
            free_costs.sort(
                key=lambda item: (
                    round(item[0], 9),
                    item[1].radius,
                    item[1].alpha_deg,
                    item[1].t0_fraction,
                )
            )
            for _, spec in free_costs[: max(1, int(self.config.freeform_shortlist))]:
                score, built, scored_spec = self._score_spec(spec)
                if score == float("inf"):
                    continue
                scored.append((score, built, scored_spec, None))

        scored.sort(key=lambda item: (item[0], item[2].track_y))
        return scored

    def _commit(self, row, track_index, spec, built, score: float = 0.0):
        rid = int(row.name)
        self._apply_state(spec, track_index, rid)
        self.committed[rid] = PlannedRoute(spec, built, score, 0)
        self._commit_boxes(rid)
        self._journal.append((rid, track_index, spec, built, score))

    def _apply_state(self, spec, track_index, rid: int) -> None:
        """把一次提交写进轨道占用与端口节点（与原版三行副作用一致）。

        自由弯角 S 形不占用任何水平轨道、也没有水平出线，``noCross`` 的轨道
        启发式对它不适用，因此只参与几何评价（交叉、接触、重合、间距），
        不写轨道占用与端口节点。
        """
        if spec.kind == "freeform":
            return
        w = self.tracks[track_index]
        idx1 = spec.index1
        idx2 = spec.index2
        l = int(self.n / 16)
        if spec.sy == 0 and spec.ly == 0:
            i1, i2 = int(idx1 - l), int(idx2 - l)
            self.nodes.MTbelow[i1].y[self.nodes.MTbelow[i1].x.index(spec.sx)] = w.y
            self.nodes.MTbelow[i2].y[self.nodes.MTbelow[i2].x.index(spec.lx)] = w.y
            w.rEnd.append(i1)
            w.lEnd.append(i2)
        elif spec.sy != 0 and spec.ly != 0:
            self.nodes.MTabove[idx1].y[self.nodes.MTabove[idx1].x.index(spec.sx)] = w.y
            self.nodes.MTabove[idx2].y[self.nodes.MTabove[idx2].x.index(spec.lx)] = w.y
            w.rEnd.append(idx1)
            w.lEnd.append(idx2)
        elif spec.sy == 0 and spec.ly != 0:
            i1 = int(idx1 - l)
            self.nodes.MTbelow[i1].y[self.nodes.MTbelow[i1].x.index(spec.sx)] = w.y
            self.nodes.MTabove[idx2].y[self.nodes.MTabove[idx2].x.index(spec.lx)] = w.y
            w.rEnd.append(i1)
            w.lEnd.append(idx2)
        else:
            i2 = int(idx2 - l)
            self.nodes.MTabove[idx1].y[self.nodes.MTabove[idx1].x.index(spec.sx)] = w.y
            self.nodes.MTbelow[i2].y[self.nodes.MTbelow[i2].x.index(spec.lx)] = w.y
            w.rEnd.append(idx1)
            w.lEnd.append(i2)
        w.WGs.append(rid)

    # ---- 拆线重布 -----------------------------------------------------
    def snapshot(self) -> "PlannerSnapshot":
        """完整状态快照：提交顺序、每路的最终 RouteSpec 与解析段、冻结 pass 边界。

        ``restore`` 会据此精确重建轨道占用、端口节点、几何缓存与提交顺序，
        因此快照/回滚可以逐项比对（见 ``tests/test_opt2d_step13.py``）。
        """
        return PlannerSnapshot(
            entries=list(self._journal),
            context=dict(self._frozen_context),
        )

    def restore(self, snapshot) -> None:
        """从快照重建全部状态，丢弃之后的提交。"""
        if isinstance(snapshot, PlannerSnapshot):
            entries = list(snapshot.entries)
            context = dict(snapshot.context)
        else:  # 兼容旧的"提交列表"快照
            entries = list(snapshot)
            context = dict(self._frozen_context)
        self.tracks = [_Track(y=y) for y in self._yy()]
        self.nodes = self._init_nodes(self._df)
        self.committed = {}
        self._boxes = {}
        self._route_boxes = {}
        self._journal = []
        for rid, track_index, spec, built, score in entries:
            self._apply_state(spec, track_index, rid)
            self.committed[rid] = PlannedRoute(spec, built, score, 0)
            self._commit_boxes(rid)
            self._journal.append((rid, track_index, spec, built, score))
        self._frozen_context = context

    def state_fingerprint(self) -> dict:
        """状态指纹：用于测试"快照-恢复后完整一致"。"""
        return {
            "context": dict(self._frozen_context),
            "journal": [(rid, index, spec, tuple(segments), score)
                        for rid, index, spec, segments, score in self._journal],
            "tracks": [
                (track.y, tuple(track.WGs), tuple(track.rEnd), tuple(track.lEnd))
                for track in self.tracks
            ],
            "nodes_above": [(tuple(n.x), tuple(n.y)) for n in self.nodes.MTabove],
            "nodes_below": [(tuple(n.x), tuple(n.y)) for n in self.nodes.MTbelow],
            "boxes": {rid: tuple(boxes) for rid, boxes in sorted(self._boxes.items())},
            "route_boxes": {rid: box for rid, box in sorted(self._route_boxes.items())},
            "committed": {
                rid: (route.spec, tuple(route.segments), route.score)
                for rid, route in sorted(self.committed.items())
            },
        }

    def reroute(self, route_ids: Iterable[int]) -> list[int]:
        """对指定路线重新走一遍同名 pass；返回仍未布成的路线。

        重布使用**冻结的 pass 边界**（首次布线结束时的 ``above_line`` /
        ``below_line``），避免"重布过程中边界随已提交集合漂移"导致的不稳定。
        """
        wanted = set(int(rid) for rid in route_ids)
        df = self._df
        groups = {
            "below": df[(df["sy"] == 0) & (df["ly"] == 0)],
            "above": df[(df["sy"] != 0) & (df["ly"] != 0)],
            "below2above": df[(df["sy"] == 0) & (df["ly"] != 0)],
            "above2below": df[(df["sy"] != 0) & (df["ly"] == 0)],
        }
        context = self._frozen_context or self._pass_context()
        failed: list[int] = []
        stats: dict = {}
        for pass_type in ("below", "above", "below2above", "above2below"):
            rows = groups[pass_type]
            if rows.empty:
                continue
            subset = rows[[int(v) in wanted for v in rows.index]]
            if subset.empty:
                continue
            self._run_pass(subset, pass_type, stats, **context.get(pass_type, {}))
        for rid in sorted(wanted):
            if rid not in self.committed:
                failed.append(rid)
        return failed

    def _pass_context(self) -> dict:
        """重建各 pass 的边界条件（与原版 pass 间依赖一致）。"""
        below_line = max(
            (r.spec.track_y for r in self.committed.values()
             if r.spec.sy == 0 and r.spec.ly == 0),
            default=None,
        )
        above_line = min(
            (r.spec.track_y for r in self.committed.values()
             if r.spec.sy != 0 and r.spec.ly != 0),
            default=None,
        )
        b2a_line = min(
            (r.spec.track_y for r in self.committed.values()
             if r.spec.sy == 0 and r.spec.ly != 0),
            default=None,
        )
        return {
            "below": {},
            "above": {},
            "below2above": {"above_line": above_line},
            "above2below": {"below_line": below_line, "b2a_line": b2a_line},
        }

    # ---- 评价与拆线重布 -----------------------------------------------
    def evaluate_plan(self, result: PlanResult, label: str) -> object:
        """把布线下场交给统一评价器（解析几何 + 全部交叉事件 + 违规分类）。"""
        issues = [issue for route in result.routes.values() for issue in route.issues]
        return self.evaluator.evaluate(
            result.specs(),
            label=label,
            segments=result.segments(),
            issues=issues,
            unplaced=list(result.unplaced),
            runtime_s=result.runtime_s,
            stop_reason=result.stop_reason,
            notes={"order_strategy": self.config.order_strategy,
                   "candidate_limit": self.config.candidate_limit,
                   "radius_policy": self.config.radius_policy},
        )

    def refine(
        self,
        result: PlanResult,
        *,
        label: str,
        rounds: int = 3,
        rip_count: int | None = None,
        max_seconds: float | None = None,
        progress: bool = False,
    ) -> tuple[PlanResult, object, dict]:
        """有界拆线重布：只重布高损耗路线，**任何重布失败都整体回滚**。

        连接完整性优先：初始解必须完整；一轮里只要有一条路线重布失败就恢复
        原状（先排除失败者重试一次，仍失败则结束该轮），绝不接受带未布通路线
        的"改进"。返回 ``(结果, 评价, 记录)``。
        """
        started = time.perf_counter()
        current = result
        evaluation = self.evaluate_plan(current, label)
        record = {"rounds": [], "stop_reason": "max_rounds", "iterations": 0}
        baseline = (evaluation.summary()["mean_loss_db"], evaluation.summary()["max_loss_db"])
        if rip_count is None:
            rip_count = max(1, len(current.routes) // 20)

        for round_index in range(int(rounds)):
            if max_seconds is not None and time.perf_counter() - started > max_seconds:
                record["stop_reason"] = "time_budget"
                break
            losses = sorted(
                ((r.total_loss_db, r.route_id) for r in evaluation.routes), reverse=True
            )
            rip_ids = [rid for _, rid in losses[:rip_count]]
            for rid in current.unplaced:
                if rid not in rip_ids:
                    rip_ids.append(rid)
            accepted = False
            excluded: list[int] = []
            for attempt in range(2):
                candidate_set = [rid for rid in rip_ids if rid not in set(excluded)]
                if not candidate_set:
                    break
                rollback = self.snapshot()
                if not rollback.entries:
                    break
                kept = [entry for entry in rollback.entries if entry[0] not in set(candidate_set)]
                self.restore(PlannerSnapshot(kept, rollback.context))
                failed = self.reroute(candidate_set)
                if failed:
                    self.restore(rollback)
                    excluded.extend(failed)
                    record["rounds"].append(
                        {
                            "round": round_index,
                            "attempt": attempt,
                            "rip_count": len(candidate_set),
                            "failed": failed[:20],
                            "accepted": False,
                            "reason": "reroute_failed",
                        }
                    )
                    continue
                trial = PlanResult(
                    config=self.config,
                    routes=dict(self.committed),
                    unplaced=list(current.unplaced),
                    runtime_s=time.perf_counter() - started,
                    stop_reason="refined",
                    stats=dict(current.stats),
                )
                trial_eval = self.evaluate_plan(trial, label)
                summary = trial_eval.summary()
                # 接受规则：**平均严格改善** 且 **全局最大损耗不恶化**（各自独立
                # 判据）。不能用 (mean, max) 元组字典序比较代替 —— 字典序会接受
                # "平均略降但最大值上升"的重布，违反任务给定的最差链路约束。
                mean_ok = summary["mean_loss_db"] < baseline[0] - 1e-12
                max_ok = summary["max_loss_db"] <= baseline[1] + 1e-12
                improved = mean_ok and max_ok
                record["rounds"].append(
                    {
                        "round": round_index,
                        "attempt": attempt,
                        "rip_ids": candidate_set[:20],
                        "rip_count": len(candidate_set),
                        "mean_loss_db": summary["mean_loss_db"],
                        "max_loss_db": summary["max_loss_db"],
                        "accepted": bool(improved),
                    }
                )
                if improved:
                    current, evaluation = trial, trial_eval
                    baseline = (summary["mean_loss_db"], summary["max_loss_db"])
                    accepted = True
                    if progress:
                        print(
                            "  refine round %d: accepted mean=%.6f max=%.6f"
                            % (round_index, summary["mean_loss_db"], summary["max_loss_db"]),
                            flush=True,
                        )
                else:
                    self.restore(rollback)
                break
            record["iterations"] += 1
            if not accepted:
                record["stop_reason"] = "no_improvement"
                break
        current.runtime_s = time.perf_counter() - started
        record["runtime_s"] = current.runtime_s
        return current, evaluation, record

    def _reorder_ports(self, rows, pass_type):
        """沿用原版 ``_reorder_by_port`` 的出线顺序约束（逐字复刻其置换逻辑）。

        只有 ``below`` 与 ``above`` 两遍做重排，且各做两步：先按 ``sx``（同一
        Port1 的槽位顺序与轨道顺序单调一致），再按 ``lx``（同一 Port2）。两个
        跨区遍在原版中不重排（``above2below`` 里的调用结果不写回），本实现保持
        一致。交换后重建该路线几何并核验，核验失败则保留交换前的几何。
        """
        if pass_type not in ("below", "above"):
            return
        if rows.empty:
            return
        subset = [rid for rid in (int(v) for v in rows.index) if rid in self.committed]
        if len(subset) < 2:
            return
        prefer_greater = pass_type == "above"
        by_sx = sorted(subset, key=lambda rid: self.committed[rid].spec.sx)
        self._reorder_field(by_sx, "sx", "index1", prefer_greater)
        by_lx = sorted(subset, key=lambda rid: self.committed[rid].spec.lx)
        self._reorder_field(by_lx, "lx", "index2", not prefer_greater)

    def _reorder_field(self, subset, field, index_field, prefer_greater):
        values = [getattr(self.committed[rid].spec, field) for rid in subset]
        indices = [getattr(self.committed[rid].spec, index_field) for rid in subset]
        inflections = [self.committed[rid].spec.track_y for rid in subset]
        temp = list(values)
        i = 0
        while i < len(values):
            for j in reversed(range(i)):
                if indices[i] == indices[j] and (
                    inflections[i] > inflections[j]
                    if prefer_greater
                    else inflections[i] < inflections[j]
                ):
                    values[i], values[j] = values[j], values[i]
                    inflections[i], inflections[j] = inflections[j], inflections[i]
                    i = j
                else:
                    break
            i += 1
        if values == temp:
            return
        # 原版最后一步：把重排后的值按 temp 的顺序映射回行。
        mapped = [temp[values.index(temp[k])] for k in range(len(values))]
        for k, rid in enumerate(subset):
            route = self.committed[rid]
            spec = route.spec
            new_value = mapped[k]
            if abs(new_value - getattr(spec, field)) < self.tol:
                continue
            if field == "sx":
                new_spec = RouteSpec(
                    route_id=spec.route_id, sx=new_value, sy=spec.sy, lx=spec.lx,
                    ly=spec.ly, track_y=spec.track_y, radius=spec.radius,
                    port1=spec.port1, port2=spec.port2, index1=spec.index1,
                    index2=spec.index2,
                )
            else:
                new_spec = RouteSpec(
                    route_id=spec.route_id, sx=spec.sx, sy=spec.sy, lx=new_value,
                    ly=spec.ly, track_y=spec.track_y, radius=spec.radius,
                    port1=spec.port1, port2=spec.port2, index1=spec.index1,
                    index2=spec.index2,
                )
            try:
                built, issues = self._build(new_spec)
            except ValueError:
                continue
            route.spec = new_spec
            route.segments = built
            route.issues = issues
            self._commit_boxes(rid)

    def _refresh_boxes(self):
        for rid, route in self.committed.items():
            boxes = [segment_aabb(s) for s in route.segments]
            self._boxes[rid] = boxes
            self._route_boxes[rid] = Aabb(
                min(b.min_x for b in boxes),
                min(b.min_y for b in boxes),
                max(b.max_x for b in boxes),
                max(b.max_y for b in boxes),
            )

    def _commit_boxes(self, rid):
        route = self.committed[rid]
        boxes = [segment_aabb(s) for s in route.segments]
        self._boxes[rid] = boxes
        self._route_boxes[rid] = Aabb(
            min(b.min_x for b in boxes),
            min(b.min_y for b in boxes),
            max(b.max_x for b in boxes),
            max(b.max_y for b in boxes),
        )
