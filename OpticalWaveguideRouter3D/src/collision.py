"""二维零宽轴对齐中心线检测，不涉及光学损耗或避让。"""

from dataclasses import dataclass
from math import isfinite

from .models import Point2D, Route


@dataclass
class SegmentIntersection:
    """线段关系；cross/touch 返回点，none/overlap 的 point 为 None。"""

    kind: str
    point: Point2D | None = None


@dataclass
class RouteIntersection:
    """两段的零基索引及其几何关系。"""

    segment_index_a: int
    segment_index_b: int
    kind: str
    point: Point2D | None = None


def _validate_tol(tol: float) -> None:
    if not isfinite(tol) or tol < 0:
        raise ValueError("tol must be finite and nonnegative.")


def _segment(
    start: Point2D, end: Point2D, tol: float
) -> tuple[str, Point2D, Point2D]:
    """容差内偏差用中点坐标对齐，端点顺序不影响结果。"""
    if not isinstance(start, Point2D) or not isinstance(end, Point2D):
        raise TypeError("Segment endpoints must be Point2D.")
    if not all(isfinite(v) for v in (start.x, start.y, end.x, end.y)):
        raise ValueError("Coordinates must be finite.")
    dx, dy = abs(end.x - start.x), abs(end.y - start.y)
    x, y = start.x / 2 + end.x / 2, start.y / 2 + end.y / 2
    if dx <= tol and dy <= tol:
        point = Point2D(x, y)
        return "point", point, point
    if dy <= tol:
        return "horizontal", Point2D(min(start.x, end.x), y), Point2D(max(start.x, end.x), y)
    if dx <= tol:
        return "vertical", Point2D(x, min(start.y, end.y)), Point2D(x, max(start.y, end.y))
    raise ValueError("Segment must be axis-aligned.")


def classify_axis_aligned_segment_intersection(
    a1: Point2D, a2: Point2D, b1: Point2D, b2: Point2D, tol: float = 1e-9
) -> SegmentIntersection:
    """返回 none/cross/touch/overlap，使用非负绝对容差。

    零长度及两坐标跨度均不超过 tol 的段按中点处理。
    容差内间隙或不超过 tol 的共线重叠视为 touch；更长重叠为 overlap。
    容差产生的接触点使用代表坐标，不改变输入点。
    """
    _validate_tol(tol)
    ak, alo, ahi = _segment(a1, a2, tol)
    bk, blo, bhi = _segment(b1, b2, tol)
    if ak == "point" or bk == "point":
        if ak != "point":
            alo, ahi, blo, bhi = blo, bhi, alo, ahi
        xlo, xhi = max(alo.x, blo.x), min(ahi.x, bhi.x)
        ylo, yhi = max(alo.y, blo.y), min(ahi.y, bhi.y)
        if xlo > xhi + tol or ylo > yhi + tol:
            return SegmentIntersection("none")
        return SegmentIntersection("touch", Point2D(
            xlo / 2 + xhi / 2, ylo / 2 + yhi / 2
        ))
    if ak == bk:
        horizontal = ak == "horizontal"
        fixed_a, fixed_b = (alo.y, blo.y) if horizontal else (alo.x, blo.x)
        if abs(fixed_a - fixed_b) > tol:
            return SegmentIntersection("none")
        lo = max(alo.x, blo.x) if horizontal else max(alo.y, blo.y)
        hi = min(ahi.x, bhi.x) if horizontal else min(ahi.y, bhi.y)
        if lo > hi + tol:
            return SegmentIntersection("none")
        if hi - lo > tol:
            return SegmentIntersection("overlap")
        moving, fixed = lo / 2 + hi / 2, fixed_a / 2 + fixed_b / 2
        return SegmentIntersection("touch", Point2D(moving, fixed) if horizontal else Point2D(fixed, moving))
    hlo, hhi, vlo, vhi = (alo, ahi, blo, bhi) if ak == "horizontal" else (blo, bhi, alo, ahi)
    point = Point2D(vlo.x, hlo.y)
    if not (hlo.x - tol <= point.x <= hhi.x + tol and vlo.y - tol <= point.y <= vhi.y + tol):
        return SegmentIntersection("none")
    interior = (
        hlo.x + tol < point.x < hhi.x - tol
        and vlo.y + tol < point.y < vhi.y - tol
    )
    return SegmentIntersection("cross" if interior else "touch", point)


def route_segments(route: Route) -> list[tuple[Point2D, Point2D]]:
    """拆分二维 Route，保留零长度段；少于两点返回空列表，拒绝三维点。"""
    points: list[Point2D] = []
    for point in route.points:
        if not isinstance(point, Point2D):
            raise TypeError("Route must contain only Point2D.")
        points.append(point)
    return list(zip(points, points[1:]))


def find_route_intersections(
    route_a: Route, route_b: Route, tol: float = 1e-9
) -> list[RouteIntersection]:
    """逐段配对检测；每对索引仅返回一次，不合并不同段对的相同交点。"""
    _validate_tol(tol)
    segments_a, segments_b = route_segments(route_a), route_segments(route_b)
    for start, end in segments_a + segments_b:
        _segment(start, end, tol)
    results: list[RouteIntersection] = []
    for i, (a1, a2) in enumerate(segments_a):
        for j, (b1, b2) in enumerate(segments_b):
            relation = classify_axis_aligned_segment_intersection(a1, a2, b1, b2, tol)
            if relation.kind != "none":
                results.append(RouteIntersection(i, j, relation.kind, relation.point))
    return results


def find_self_intersections(route: Route, tol: float = 1e-9) -> list[RouteIntersection]:
    """每个无序段对仅检查一次；忽略相邻段正常接点，保留折返重叠。"""
    _validate_tol(tol)
    segments = route_segments(route)
    for start, end in segments:
        _segment(start, end, tol)
    results: list[RouteIntersection] = []
    for i, (a1, a2) in enumerate(segments):
        for j in range(i + 1, len(segments)):
            relation = classify_axis_aligned_segment_intersection(a1, a2, *segments[j], tol)
            if relation.kind == "none" or (j == i + 1 and relation.kind == "touch"):
                continue
            results.append(RouteIntersection(i, j, relation.kind, relation.point))
    return results


@dataclass
class CollisionEvent:
    """One segment-pair event; equal route IDs denote self-intersection."""

    route_id_a: int
    route_id_b: int
    segment_index_a: int
    segment_index_b: int
    kind: str
    point: Point2D | None


@dataclass
class BatchCollisionReport:
    """Zero-width policy outcome; cross is allowed only between distinct routes."""

    valid: bool
    route_count: int
    pair_count: int
    pairwise_events: list[CollisionEvent]
    self_events: list[CollisionEvent]
    invalid_route_ids: list[int]


def validate_routes_2d(routes: list[Route], tol: float = 1e-9) -> BatchCollisionReport:
    """Record all events without mutation or repair; each unordered pair is tested once.

    Counts derived from events are segment-pair counts, not globally deduplicated
    physical crossing points. Empty batches are valid; duplicate IDs are rejected.
    """
    _validate_tol(tol)
    ids = [r.waveguide_id for r in routes]
    if len(set(ids)) != len(ids):
        raise ValueError("Route waveguide IDs must be unique.")
    pairwise: list[CollisionEvent] = []
    self_events: list[CollisionEvent] = []
    invalid: set[int] = set()
    seen: set[tuple] = set()

    def record(a: int, b: int, relation: RouteIntersection, target: list[CollisionEvent]) -> None:
        point = relation.point
        key = (a, b, relation.segment_index_a, relation.segment_index_b,
               relation.kind, None if point is None else (point.x, point.y))
        if key not in seen:
            seen.add(key)
            target.append(CollisionEvent(a, b, relation.segment_index_a,
                                         relation.segment_index_b, relation.kind, point))
        if a == b or relation.kind in ("touch", "overlap"):
            invalid.update((a, b))

    for route in routes:
        for relation in find_self_intersections(route, tol):
            record(route.waveguide_id, route.waveguide_id, relation, self_events)
    for i, route_a in enumerate(routes):
        for route_b in routes[i + 1:]:
            for relation in find_route_intersections(route_a, route_b, tol):
                record(route_a.waveguide_id, route_b.waveguide_id, relation, pairwise)
    return BatchCollisionReport(
        not invalid, len(routes), len(routes) * (len(routes) - 1) // 2,
        pairwise, self_events, sorted(invalid),
    )


# Analytic zero-width curves. Existing skeleton APIs above remain independent.
from math import atan2, sqrt, tau
from .models import LineSegment2D, ArcSegment2D, SmoothedRoute2D
from .geometry import (
    distance, line_segment_length, arc_segment_radius,
    validate_arc_segment_2d, validate_smoothed_route_2d,
)


@dataclass
class CurveRouteIntersection:
    """One discrete intersection or a common nonzero-length locus."""

    route_id_a: int
    route_id_b: int
    segment_index_a: int
    segment_index_b: int
    segment_type_a: str
    segment_type_b: str
    kind: str
    point: Point2D | None = None


def _curve_validate(segment: LineSegment2D | ArcSegment2D, tol: float) -> None:
    if isinstance(segment, LineSegment2D):
        if line_segment_length(segment) == 0:
            raise ValueError("Zero-length analytic line is not supported.")
    elif isinstance(segment, ArcSegment2D):
        validate_arc_segment_2d(segment, tol)
    else:
        raise TypeError("Expected LineSegment2D or ArcSegment2D.")


def _arc_contains(point: Point2D, arc: ArcSegment2D, tol: float) -> bool:
    radius = arc_segment_radius(arc)
    if abs(distance(point, arc.center) - radius) > tol:
        return False
    if min(distance(point, arc.start), distance(point, arc.end)) <= tol:
        return True
    start = atan2(arc.start.y-arc.center.y, arc.start.x-arc.center.x)
    angle = atan2(point.y-arc.center.y, point.x-arc.center.x)
    delta = ((angle-start) if arc.sweep_rad > 0 else (start-angle)) % tau
    return delta <= abs(arc.sweep_rad) + tol/radius


def point_on_arc_2d(point: Point2D, arc: ArcSegment2D, tol: float = 1e-9) -> bool:
    """Test radial distance and signed finite sweep, including wrapped endpoints."""
    _validate_tol(tol)
    _curve_validate(arc, tol)
    if not isinstance(point, Point2D) or not all(isfinite(v) for v in (point.x, point.y)):
        raise ValueError("Expected finite Point2D.")
    return _arc_contains(point, arc, tol)


def _endpoint(point: Point2D, segment: LineSegment2D | ArcSegment2D, tol: float) -> bool:
    return min(distance(point, segment.start), distance(point, segment.end)) <= tol


def _discrete_events(
    candidates: list[Point2D], a: LineSegment2D | ArcSegment2D,
    b: LineSegment2D | ArcSegment2D, tangent: bool, tol: float,
) -> list[SegmentIntersection]:
    events: list[SegmentIntersection] = []
    for point in candidates:
        if not all(isfinite(v) for v in (point.x, point.y)):
            raise ValueError("Intersection cannot be represented with finite coordinates.")
        if any(distance(point, event.point) <= tol for event in events):
            continue
        kind = "touch" if tangent or _endpoint(point, a, tol) or _endpoint(point, b, tol) else "cross"
        events.append(SegmentIntersection(kind, point))
    return events


def _line_frame(line: LineSegment2D) -> tuple[float, float, float]:
    length = line_segment_length(line)
    return (line.end.x-line.start.x)/length, (line.end.y-line.start.y)/length, length


def _line_line(a: LineSegment2D, b: LineSegment2D, tol: float) -> list[SegmentIntersection]:
    ux, uy, length_a = _line_frame(a)
    vx, vy, length_b = _line_frame(b)
    wx, wy = b.start.x-a.start.x, b.start.y-a.start.y
    determinant = ux*vy-uy*vx
    if determinant == 0:
        if abs(wx*uy-wy*ux) > tol:
            return []
        t0 = wx*ux+wy*uy
        t1 = t0 + length_b*(ux*vx+uy*vy)
        lo, hi = max(0.0, min(t0,t1)), min(length_a, max(t0,t1))
        if lo > hi+tol:
            return []
        if hi-lo > tol:
            return [SegmentIntersection("overlap")]
        t = lo/2+hi/2
        return [SegmentIntersection("touch", Point2D(a.start.x+t*ux, a.start.y+t*uy))]
    # Do not turn a small nonzero angle into parallelism.
    t = (wx*vy-wy*vx)/determinant
    s = (wx*uy-wy*ux)/determinant
    if not all(isfinite(v) for v in (t,s)):
        raise ValueError("Ill-conditioned line intersection.")
    if not (-tol <= t <= length_a+tol and -tol <= s <= length_b+tol):
        return []
    pa = Point2D(a.start.x+t*ux,a.start.y+t*uy)
    pb = Point2D(b.start.x+s*vx,b.start.y+s*vy)
    if distance(pa,pb) > tol:
        raise ValueError("Line intersection residual exceeds tolerance.")
    return _discrete_events([pa],a,b,False,tol)


def _line_arc(line: LineSegment2D, arc: ArcSegment2D, tol: float) -> list[SegmentIntersection]:
    ux, uy, length = _line_frame(line)
    wx, wy = arc.center.x-line.start.x, arc.center.y-line.start.y
    projection = wx*ux+wy*uy
    perpendicular = abs(wx*uy-wy*ux)
    radius = arc_segment_radius(arc)
    if perpendicular > radius+tol:
        return []
    tangent = abs(perpendicular-radius) <= tol
    # Factored radicand avoids subtracting two large squared radii.
    h = 0.0 if tangent else sqrt(max(0.0, radius-perpendicular))*sqrt(radius+perpendicular)
    if not isfinite(h):
        raise ValueError("Circle intersection exceeds numerical range.")
    parameters = [projection] if tangent else [projection-h,projection+h]
    candidates = []
    for t in parameters:
        if -tol <= t <= length+tol:
            p = Point2D(line.start.x+t*ux,line.start.y+t*uy)
            if _arc_contains(p,arc,tol):
                candidates.append(p)
    return _discrete_events(candidates,line,arc,tangent,tol)


def _coincident_arcs(a: ArcSegment2D, b: ArcSegment2D, tol: float) -> list[SegmentIntersection]:
    radius = arc_segment_radius(a)
    def interval(arc: ArcSegment2D) -> tuple[float,float]:
        angle = atan2(arc.start.y-arc.center.y,arc.start.x-arc.center.x)
        lo = (angle+min(0.0,arc.sweep_rad)) % tau
        return lo,lo+abs(arc.sweep_rad)
    alo,ahi = interval(a)
    blo,bhi = interval(b)
    for shift in (-tau,0.0,tau):
        if min(ahi,bhi+shift)-max(alo,blo+shift) > tol/radius:
            return [SegmentIntersection("overlap")]
    points = [p for p in (a.start,a.end,b.start,b.end)
              if _arc_contains(p,a,tol) and _arc_contains(p,b,tol)]
    return _discrete_events(points,a,b,True,tol)


def _arc_arc(a: ArcSegment2D, b: ArcSegment2D, tol: float) -> list[SegmentIntersection]:
    ra,rb = arc_segment_radius(a),arc_segment_radius(b)
    d = distance(a.center,b.center)
    if not isfinite(d):
        raise ValueError("Circle separation exceeds numerical range.")
    if d <= tol and abs(ra-rb) <= tol:
        return _coincident_arcs(a,b,tol)
    if d == 0 or d > ra+rb+tol or d < abs(ra-rb)-tol:
        return []
    # Scale before squaring to avoid overflow.
    scale = max(ra,rb,d)
    ar,br,dr = ra/scale,rb/scale,d/scale
    x = (dr*dr+(ar-br)*(ar+br))/(2*dr)
    h2 = (ar-x)*(ar+x)
    tangent = abs(d-(ra+rb)) <= tol or abs(d-abs(ra-rb)) <= tol
    if h2 < 0 and not tangent:
        raise ValueError("Unreliable circle intersection radicand.")
    h = 0.0 if tangent else scale*sqrt(max(0.0,h2))
    along = scale*x
    ux,uy = (b.center.x-a.center.x)/d,(b.center.y-a.center.y)/d
    base = Point2D(a.center.x+along*ux,a.center.y+along*uy)
    points = [base] if tangent else [
        Point2D(base.x-h*uy,base.y+h*ux),Point2D(base.x+h*uy,base.y-h*ux)]
    candidates = [p for p in points if _arc_contains(p,a,tol) and _arc_contains(p,b,tol)]
    return _discrete_events(candidates,a,b,tangent,tol)


def find_segment_intersections_2d(
    a: LineSegment2D | ArcSegment2D, b: LineSegment2D | ArcSegment2D,
    tol: float = 1e-9,
) -> list[SegmentIntersection]:
    """Analytic finite curves: [] means none; each cross/touch has its own point.

    Overlap has point=None. Absolute length tolerance governs endpoints,
    tangency and coincident loci. No sampling, width or clearance is involved.
    Zero-length lines and invalid arcs raise controlled errors.
    """
    _validate_tol(tol)
    _curve_validate(a,tol)
    _curve_validate(b,tol)
    if isinstance(a,LineSegment2D):
        return _line_line(a,b,tol) if isinstance(b,LineSegment2D) else _line_arc(a,b,tol)
    return _line_arc(b,a,tol) if isinstance(b,LineSegment2D) else _arc_arc(a,b,tol)


def _curve_event(
    a: SmoothedRoute2D, b: SmoothedRoute2D, i: int, j: int,
    event: SegmentIntersection,
) -> CurveRouteIntersection:
    return CurveRouteIntersection(
        a.waveguide_id,b.waveguide_id,i,j,
        type(a.segments[i]).__name__,type(b.segments[j]).__name__,
        event.kind,event.point,
    )


def find_smoothed_route_intersections_2d(
    a: SmoothedRoute2D, b: SmoothedRoute2D, tol: float = 1e-9,
) -> list[CurveRouteIntersection]:
    """Retain each segment-pair event, including two intersections per pair."""
    validate_smoothed_route_2d(a,tol)
    validate_smoothed_route_2d(b,tol)
    return [_curve_event(a,b,i,j,event)
            for i,sa in enumerate(a.segments) for j,sb in enumerate(b.segments)
            for event in find_segment_intersections_2d(sa,sb,tol)]


def find_smoothed_route_self_intersections_2d(
    route: SmoothedRoute2D, tol: float = 1e-9,
) -> list[CurveRouteIntersection]:
    """Ignore only the normal shared adjacent endpoint; retain all other events."""
    validate_smoothed_route_2d(route,tol)
    events = []
    for i,a in enumerate(route.segments):
        for j in range(i+1,len(route.segments)):
            b = route.segments[j]
            for event in find_segment_intersections_2d(a,b,tol):
                if (j == i+1 and event.kind == "touch" and event.point is not None
                        and distance(event.point,a.end) <= tol
                        and distance(event.point,b.start) <= tol):
                    continue
                events.append(_curve_event(route,route,i,j,event))
    return events
