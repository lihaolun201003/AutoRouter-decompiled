"""不绑定具体单位的二维基础几何函数。"""

from math import hypot, isfinite, pi, cos, sin, fsum

from src.models import Point2D, Route, LineSegment2D, ArcSegment2D, SmoothedRoute2D


def distance(p1: Point2D, p2: Point2D) -> float:
    """返回两点之间的欧氏距离。"""
    return hypot(p2.x - p1.x, p2.y - p1.y)


def points_close(p1: Point2D, p2: Point2D, tol: float = 1e-9) -> bool:
    """逐坐标比较两点，tol 为非负绝对容差。"""
    return abs(p1.x - p2.x) <= tol and abs(p1.y - p2.y) <= tol


def segment_orientation(
    p1: Point2D, p2: Point2D, tol: float = 1e-9
) -> str:
    """按非负绝对容差返回 horizontal、vertical 或 other；退化点优先水平。"""
    if abs(p2.y - p1.y) <= tol:
        return "horizontal"
    if abs(p2.x - p1.x) <= tol:
        return "vertical"
    return "other"


def segment_length(p1: Point2D, p2: Point2D, tol: float = 1e-9) -> float:
    """返回轴对齐线段的欧氏长度；非轴对齐时抛出 ValueError。"""
    if segment_orientation(p1, p2, tol) == "other":
        raise ValueError("Segment must be horizontal or vertical.")
    return distance(p1, p2)


def intervals_overlap(
    a1: float, a2: float, b1: float, b2: float, tol: float = 1e-9
) -> bool:
    """判断闭区间是否重叠，规范化端点顺序并允许非负绝对容差。"""
    a_min, a_max = min(a1, a2), max(a1, a2)
    b_min, b_max = min(b1, b2), max(b1, b2)
    return max(a_min, b_min) <= min(a_max, b_max) + tol


def point_on_axis_aligned_segment(
    point: Point2D, start: Point2D, end: Point2D, tol: float = 1e-9
) -> bool:
    """判断点是否在线段闭范围内；非轴对齐时抛出 ValueError。"""
    orientation = segment_orientation(start, end, tol)
    if orientation == "other":
        raise ValueError("Segment must be horizontal or vertical.")
    if points_close(start, end, tol):
        return points_close(point, start, tol)
    if orientation == "horizontal":
        return abs(point.y - start.y) <= tol and intervals_overlap(
            point.x, point.x, start.x, end.x, tol
        )
    return abs(point.x - start.x) <= tol and intervals_overlap(
        point.y, point.y, start.y, end.y, tol
    )


def normalize_orthogonal_polyline(points: list[Point2D]) -> list[Point2D]:
    """精确校验轴对齐，删除重复点和同向共线中间点，保留折返及原坐标。"""
    result: list[Point2D] = []
    for point in points:
        if result and point == result[-1]:
            continue
        if result and segment_orientation(result[-1], point, tol=0.0) == "other":
            raise ValueError("Polyline must contain only axis-aligned segments.")
        while len(result) >= 2:
            first, middle = result[-2], result[-1]
            horizontal = first.y == middle.y == point.y
            vertical = first.x == middle.x == point.x
            if not (horizontal or vertical):
                break
            if not point_on_axis_aligned_segment(middle, first, point, tol=0.0):
                break
            result.pop()
        result.append(point)
    return result


def build_u_route(
    start: Point2D, end: Point2D, track_coordinate: float, side: str
) -> list[Point2D]:
    """按给定 track 生成 U 型直角骨架；side 指定端点侧，不限制 track 内外方向。"""
    if side in ("left", "right"):
        points = [
            start, Point2D(track_coordinate, start.y),
            Point2D(track_coordinate, end.y), end,
        ]
    elif side in ("top", "bottom"):
        points = [
            start, Point2D(start.x, track_coordinate),
            Point2D(end.x, track_coordinate), end,
        ]
    else:
        raise ValueError("side must be left, right, top or bottom.")
    return normalize_orthogonal_polyline(points)


def build_z_route(
    start: Point2D, end: Point2D, middle_coordinate: float, orientation: str
) -> list[Point2D]:
    """按中间段方向及坐标生成普通 Z 型直角骨架，不选择轨道或圆角化。"""
    if orientation == "horizontal":
        points = [
            start, Point2D(start.x, middle_coordinate),
            Point2D(end.x, middle_coordinate), end,
        ]
    elif orientation == "vertical":
        points = [
            start, Point2D(middle_coordinate, start.y),
            Point2D(middle_coordinate, end.y), end,
        ]
    else:
        raise ValueError("orientation must be horizontal or vertical.")
    return normalize_orthogonal_polyline(points)


def build_special_z_route(start: Point2D, end: Point2D) -> list[Point2D]:
    """特殊 Z 型需要在后续结合 bend radius 和前代规则进一步确认。"""
    raise NotImplementedError(
        "Special Z geometry requires confirmed bend radius and legacy rules."
    )


def _analytic_tol(tol: float) -> None:
    if not isfinite(tol) or tol < 0:
        raise ValueError("Tolerance must be finite and nonnegative.")


def _analytic_point(point: Point2D) -> None:
    if not isinstance(point, Point2D) or not all(isfinite(v) for v in (point.x, point.y)):
        raise ValueError("Expected finite Point2D coordinates.")


def line_segment_length(segment: LineSegment2D) -> float:
    """Return unit-neutral Euclidean line length."""
    _analytic_point(segment.start)
    _analytic_point(segment.end)
    length = distance(segment.start, segment.end)
    if not isfinite(length):
        raise ValueError("Line length is not finite.")
    return length


def arc_segment_radius(segment: ArcSegment2D) -> float:
    """Derive radius from start and center, without storing redundant data."""
    _analytic_point(segment.start)
    _analytic_point(segment.center)
    radius = distance(segment.start, segment.center)
    if not isfinite(radius) or radius <= 0:
        raise ValueError("Arc radius must be finite and positive.")
    return radius


def validate_arc_segment_2d(segment: ArcSegment2D, tol: float = 1e-9) -> None:
    """Validate radius and signed rotation; only 0 < abs(sweep) <= pi is supported."""
    _analytic_tol(tol)
    _analytic_point(segment.end)
    radius = arc_segment_radius(segment)
    sweep = segment.sweep_rad
    if not isfinite(sweep) or not 0 < abs(sweep) <= pi:
        raise ValueError("Arc sweep must satisfy 0 < abs(sweep) <= pi.")
    if abs(distance(segment.end, segment.center) - radius) > tol:
        raise ValueError("Arc endpoint radii disagree.")
    x = segment.start.x - segment.center.x
    y = segment.start.y - segment.center.y
    rotated = Point2D(segment.center.x + x*cos(sweep) - y*sin(sweep),
                      segment.center.y + x*sin(sweep) + y*cos(sweep))
    if distance(rotated, segment.end) > tol:
        raise ValueError("Arc sweep does not reach endpoint.")


def arc_segment_length(segment: ArcSegment2D) -> float:
    """Return analytic arc length r*abs(sweep), after validation."""
    validate_arc_segment_2d(segment)
    return arc_segment_radius(segment) * abs(segment.sweep_rad)


def validate_smoothed_route_2d(route: SmoothedRoute2D, tol: float = 1e-9) -> None:
    """Validate ordered continuity and segment geometry; an empty route is valid."""
    _analytic_tol(tol)
    previous = None
    for segment in route.segments:
        if isinstance(segment, LineSegment2D):
            if line_segment_length(segment) == 0:
                raise ValueError("Zero-length line is not allowed.")
        elif isinstance(segment, ArcSegment2D):
            validate_arc_segment_2d(segment, tol)
        else:
            raise ValueError("Unknown analytic segment type.")
        if previous is not None and distance(previous, segment.start) > tol:
            raise ValueError("Disconnected smoothed route.")
        previous = segment.end


def smoothed_route_length(route: SmoothedRoute2D) -> float:
    """Return total unit-neutral analytic length; no physical unit conversion."""
    validate_smoothed_route_2d(route)
    return fsum(line_segment_length(s) if isinstance(s, LineSegment2D)
                else arc_segment_length(s) for s in route.segments)


def smooth_orthogonal_route_2d(
    route: Route, radius: float, tol: float = 1e-9
) -> SmoothedRoute2D:
    """Round ordinary 90-degree bends without mutation or radius adjustment.

    Empty skeletons yield empty geometry; a single point is rejected because it
    cannot be represented as a nonzero segment. Duplicate points and reversals
    are rejected. Same-direction collinear points are normalized on a copy.
    Length shortages within tol are treated as numerical equality.
    """
    _analytic_tol(tol)
    if not isfinite(radius) or radius <= 0:
        raise ValueError("Radius must be finite and positive.")
    for point in route.points:
        _analytic_point(point)
    if any(a == b for a,b in zip(route.points, route.points[1:])):
        raise ValueError("Duplicate skeleton points.")
    points = normalize_orthogonal_polyline(list(route.points))
    if len(points) == 1:
        raise ValueError("A single-point skeleton has no representable segment.")
    if not points:
        return SmoothedRoute2D(route.waveguide_id, [])
    lengths = [distance(a,b) for a,b in zip(points,points[1:])]
    directions = [((b.x-a.x)/length, (b.y-a.y)/length)
                  for a,b,length in zip(points,points[1:],lengths)]
    for u,v in zip(directions,directions[1:]):
        if abs(u[0]*v[0]+u[1]*v[1]) > 1e-12:
            raise ValueError("180-degree reversal is not supported.")
    for i,length in enumerate(lengths):
        needed = radius * (int(i > 0) + int(i < len(lengths)-1))
        if length < needed - tol:
            raise ValueError("Insufficient segment length for requested radius.")
    segments: list[LineSegment2D | ArcSegment2D] = []
    cursor = points[0]
    for i in range(1,len(points)-1):
        b = points[i]
        u,v = directions[i-1],directions[i]
        start = Point2D(b.x-radius*u[0], b.y-radius*u[1])
        end = Point2D(b.x+radius*v[0], b.y+radius*v[1])
        center = Point2D(start.x+radius*v[0],start.y+radius*v[1])
        if distance(cursor,start) > tol:
            segments.append(LineSegment2D(cursor,start))
        sweep = pi/2 if u[0]*v[1]-u[1]*v[0] > 0 else -pi/2
        segments.append(ArcSegment2D(start,end,center,sweep))
        cursor = end
    if distance(cursor,points[-1]) > tol or not segments:
        segments.append(LineSegment2D(cursor,points[-1]))
    result = SmoothedRoute2D(route.waveguide_id,segments)
    validate_smoothed_route_2d(result,tol)
    return result


def build_special_z_smoothed_route_2d(
    waveguide_id: int, start: Point2D, end: Point2D,
    radius: float, tol: float = 1e-9,
) -> SmoothedRoute2D:
    """Construct the project's restricted symmetric double-arc Z, not legacy replay.

    Endpoints define opposite horizontal boundaries; the join is their midpoint.
    Requires tol < abs(dx) < 2r and enough vertical separation. No track is
    assigned or changed. Endpoint tangents follow travel direction vertically.
    """
    from math import asin, sqrt
    _analytic_tol(tol)
    _analytic_point(start)
    _analytic_point(end)
    if not isfinite(radius) or radius <= 0:
        raise ValueError("Radius must be finite and positive.")
    dx, dy = abs(end.x-start.x), abs(end.y-start.y)
    if not isfinite(dx) or not isfinite(dy):
        raise ValueError("Endpoint separation is not finite.")
    if dx <= tol or dx >= 2*radius:
        raise ValueError("Unsupported horizontal span: require tol < dx < 2r.")
    if dy <= tol:
        raise ValueError("Endpoints must lie on distinct horizontal boundaries.")
    e = 1 if end.x > start.x else -1
    q = 1 if end.y > start.y else -1
    # Half the chord of the two-circle center separation:
    # h^2 = r*dx - dx^2/4. This avoids acos cancellation for small dx.
    h = sqrt(dx) * sqrt(radius-dx/4)
    theta = 2*asin(sqrt(dx/radius)/2)
    if not isfinite(h) or dy/2 < h:
        raise ValueError("Insufficient vertical separation for fixed-radius arcs.")
    midpoint = Point2D(start.x/2+end.x/2, start.y/2+end.y/2)
    lead = dy/2-h
    a = Point2D(start.x, start.y+q*lead)
    b = Point2D(end.x, end.y-q*lead)
    c1 = Point2D(start.x+e*radius,a.y)
    c2 = Point2D(end.x-e*radius,b.y)
    segments: list[LineSegment2D | ArcSegment2D] = []
    if a != start:
        segments.append(LineSegment2D(start,a))
    segments.append(ArcSegment2D(a,midpoint,c1,-e*q*theta))
    segments.append(ArcSegment2D(midpoint,b,c2,e*q*theta))
    if b != end:
        segments.append(LineSegment2D(b,end))
    result = SmoothedRoute2D(waveguide_id,segments)
    validate_smoothed_route_2d(result,tol)
    # Reject numerical loss of geometry instead of silently relaxing tolerance.
    for arc in (s for s in segments if isinstance(s,ArcSegment2D)):
        if abs(arc_segment_radius(arc)-radius) > tol:
            raise ValueError("Requested radius cannot be represented within tolerance.")
    if segments[0].start != start or segments[-1].end != end:
        raise ValueError("Endpoint preservation failed.")
    length = smoothed_route_length(result)
    if not isfinite(length) or length <= 0:
        raise ValueError("Invalid special Z length.")
    return result
