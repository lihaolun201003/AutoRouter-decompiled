"""二维规则路由编排，仅使用调用者指定的几何模板和轨道坐标。"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .multi_crossing_guard import ExactMultiCrossingGuard
from math import isfinite

from .geometry import build_special_z_route, build_u_route, build_z_route
from .models import Point2D, Port, Route, Waveguide


def route_waveguide_2d(
    waveguide: Waveguide,
    route_type: str,
    coordinate: float,
    orientation_or_side: str | None = None,
) -> Route:
    """生成二维直角骨架；仅接受 Point2D，不执行投影或自动轨道搜索。

    route_type 支持 u、z、special_z。现有模型注解限定 Point3D，
    本入口按二维要求运行时检查并保存 Point2D，暂不修改模型注解。
    """
    if route_type not in ("u", "z", "special_z"):
        raise ValueError("route_type must be u, z or special_z.")
    start = waveguide.start_port.position
    end = waveguide.end_port.position
    if not isinstance(start, Point2D):
        raise TypeError("start_port.position must be Point2D.")
    if not isinstance(end, Point2D):
        raise TypeError("end_port.position must be Point2D.")
    if route_type == "u":
        if orientation_or_side not in ("left", "right", "top", "bottom"):
            raise ValueError("U routing requires side: left, right, top or bottom.")
        points = build_u_route(start, end, coordinate, orientation_or_side)
    elif route_type == "z":
        if orientation_or_side not in ("horizontal", "vertical"):
            raise ValueError("Z routing requires orientation: horizontal or vertical.")
        points = build_z_route(start, end, coordinate, orientation_or_side)
    else:
        points = build_special_z_route(start, end)
    return Route(waveguide_id=waveguide.id, points=points)


@dataclass
class RoutePreparation:
    """Topology only; no track, geometry or special-Z decision."""

    waveguide_id: int
    route_type: str
    side: str | None


def _validate_preparation_boundaries(top_y: float, bottom_y: float, tol: float) -> None:
    if not all(isfinite(v) for v in (top_y, bottom_y, tol)) or tol < 0:
        raise ValueError("Boundaries and tolerance must be finite; tol must be nonnegative.")
    if top_y <= bottom_y or top_y - bottom_y <= 2 * tol:
        raise ValueError("top_y must exceed bottom_y with nonoverlapping tolerance bands.")


def prepare_waveguide_2d(
    waveguide: Waveguide, top_y: float, bottom_y: float, tol: float = 1e-9
) -> RoutePreparation:
    """Classify endpoints on explicit top/bottom boundaries without modifying input."""
    _validate_preparation_boundaries(top_y, bottom_y, tol)
    sides: list[str] = []
    for label, port in (("start", waveguide.start_port), ("end", waveguide.end_port)):
        point = port.position
        if not isinstance(point, Point2D):
            raise TypeError(f"{label} position must be Point2D.")
        if not isfinite(point.x) or not isfinite(point.y):
            raise ValueError(f"{label} position must be finite.")
        if abs(point.y - top_y) <= tol:
            sides.append("top")
        elif abs(point.y - bottom_y) <= tol:
            sides.append("bottom")
        else:
            raise ValueError(f"{label} position is on neither boundary.")
    if sides[0] == sides[1]:
        return RoutePreparation(waveguide.id, "u", sides[0])
    return RoutePreparation(waveguide.id, "z", None)


def prepare_waveguides_2d(
    waveguides: list[Waveguide], top_y: float, bottom_y: float, tol: float = 1e-9
) -> list[RoutePreparation]:
    """Prepare each waveguide in input order, preserving IDs and endpoint data."""
    _validate_preparation_boundaries(top_y, bottom_y, tol)
    return [prepare_waveguide_2d(w, top_y, bottom_y, tol) for w in waveguides]


@dataclass
class TrackAssignment:
    """Assignment outcome only; an assigned track is not a validated Route."""

    waveguide_id: int
    status: str
    track_index: int | None
    track_y: float | None
    reason: str | None


@dataclass
class TrackPolicyConfig:
    """New-project A+G1+S1 policy; board y boundaries are 0 and board_height."""

    board_height: float
    waveguide_width: float
    spacing: float
    bend_radius: float
    tol: float = 1e-9
    # Experimental opt-in; ascending preserves the official A+G1+S1 baseline.
    top_u_primary_order: str = "ascending"


def build_track_grid_2d(config: TrackPolicyConfig) -> list[float]:
    """Return zero-based G1 centerlines, allowing equality at both limits."""
    from math import floor

    h, w, s, r, tol = (
        config.board_height, config.waveguide_width, config.spacing,
        config.bend_radius, config.tol,
    )
    if not all(isfinite(v) for v in (h, w, s, r, tol)):
        raise ValueError("Track configuration values must be finite.")
    if h <= 0 or w <= 0 or s < 0 or r < 0 or tol < 0:
        raise ValueError("Invalid track configuration signs.")
    pitch = w + s
    lower, upper = r + w / 2, h - r - w / 2
    if not all(isfinite(v) for v in (pitch, lower, upper)) or pitch <= 0:
        raise ValueError("Invalid derived track configuration.")
    if lower > upper:
        raise ValueError("No usable track: lower_y exceeds upper_y.")
    quotient = (upper - lower) / pitch
    if not isfinite(quotient):
        raise ValueError("Track count is not finite.")
    nearest = round(quotient)
    # Only repair a near-integer quotient; never extend by a whole track.
    from math import ulp
    epsilon = min(tol / pitch, 8 * ulp(quotient), 0.25)
    if abs(quotient - nearest) <= epsilon:
        quotient = float(nearest)
    count = floor(quotient) + 1
    grid = [lower + i * pitch for i in range(count)]
    if grid[-1] > upper + tol:
        raise ValueError("Computed track exceeds upper boundary.")
    return grid


def _algorithmic_endpoints(
    waveguide: Waveguide, preparation: RoutePreparation, tol: float
) -> tuple[Port, Port]:
    """Allocation-only view; caller validates Point2D positions first."""
    a, b = waveguide.start_port, waveguide.end_port
    if preparation.route_type == "u" and abs(a.position.x - b.position.x) > tol:
        return (a, b) if a.position.x < b.position.x else (b, a)
    return (a, b) if (a.pmt_id, a.id) <= (b.pmt_id, b.id) else (b, a)


def assign_tracks_2d(
    waveguides: list[Waveguide],
    preparations: list[RoutePreparation],
    config: TrackPolicyConfig,
    *, guard: "ExactMultiCrossingGuard | None" = None,
) -> list[TrackAssignment]:
    """Assign exclusive tracks deterministically, returning results in input order.

    This is the project's V0.1 policy, not a full legacy allocator reproduction.
    Invalid batch inputs raise before allocation; unsupported spans are per-item
    outcomes and never consume a track. With guard=None no geometry or collision
    is called. An explicit guard checks temporary curves before committing a track.
    """
    if config.top_u_primary_order not in ("ascending", "descending"):
        raise ValueError("top_u_primary_order must be ascending or descending.")
    grid = build_track_grid_2d(config)
    _validate_preparation_boundaries(config.board_height, 0.0, config.tol)
    waveguide_ids = [w.id for w in waveguides]
    preparation_ids = [p.waveguide_id for p in preparations]
    if len(set(waveguide_ids)) != len(waveguide_ids):
        raise ValueError("Waveguide IDs must be unique.")
    if len(set(preparation_ids)) != len(preparation_ids):
        raise ValueError("Preparation IDs must be unique.")
    if set(waveguide_ids) != set(preparation_ids):
        raise ValueError("Waveguide and preparation IDs must match.")
    by_id = {p.waveguide_id: p for p in preparations}
    ordered = []
    for waveguide in waveguides:
        preparation = by_id[waveguide.id]
        expected = prepare_waveguide_2d(waveguide, config.board_height, 0.0, config.tol)
        if preparation != expected:
            raise ValueError(f"Preparation disagrees with endpoints: {waveguide.id}.")
        a, b = _algorithmic_endpoints(waveguide, preparation, config.tol)
        if preparation.route_type == "u":
            group = 0 if preparation.side == "top" else 1
        else:
            group = 2 if abs(a.position.y - config.board_height) <= config.tol else 3
        primary_x = -a.position.x if group == 0 and config.top_u_primary_order == "descending" else a.position.x
        key = (group, primary_x, b.position.x, a.pmt_id, b.pmt_id, waveguide.id)
        ordered.append((key, waveguide, preparation))
    ordered.sort(key=lambda item: item[0])
    occupancy: list[int | None] = [None] * len(grid)
    results: dict[int, TrackAssignment] = {}
    for key, waveguide, preparation in ordered:
        dx = abs(waveguide.start_port.position.x - waveguide.end_port.position.x)
        if dx < 2 * config.bend_radius - config.tol:
            status = "unsupported_u_bend_span" if preparation.route_type == "u" else "unsupported_geometry"
            results[waveguide.id] = TrackAssignment(
                waveguide.id, status, None, None, "Horizontal span is below 2 * bend_radius."
            )
            continue
        scan = range(len(grid)) if key[0] == 1 else range(len(grid) - 1, -1, -1)
        if guard is None:
            index = next((i for i in scan if occupancy[i] is None), None)
        else:
            from time import perf_counter
            from .geometry import smooth_orthogonal_route_2d
            index = None
            rejected = False
            for i in scan:
                t = perf_counter()
                guard.stats['allocator_base_checks'] += 1
                available = occupancy[i] is None
                guard.timings['allocator_base_checks'] += perf_counter() - t
                if not available:
                    continue
                guard.stats['candidate_attempt_count'] += 1
                t = perf_counter()
                candidate = TrackAssignment(waveguide.id, 'assigned', i, grid[i], None)
                skeleton = generate_assigned_routes_2d([waveguide], [preparation], [candidate],
                    top_y=config.board_height, bottom_y=0.0, tol=config.tol)[0]
                guard.timings['temporary_route_construction'] += perf_counter() - t
                t = perf_counter()
                curve = smooth_orthogonal_route_2d(skeleton, config.bend_radius, config.tol)
                guard.timings['temporary_smoothing'] += perf_counter() - t
                evaluation = guard.evaluate(curve)
                if evaluation.witness is not None:
                    guard.reject(evaluation, i, grid[i])
                    rejected = True
                    continue
                guard.commit(evaluation)
                index = i
                break
            if index is None and rejected:
                guard.exhausted.append(waveguide.id)
        if index is None:
            results[waveguide.id] = TrackAssignment(
                waveguide.id, "no_available_track", None, None, "All tracks are occupied."
            )
        else:
            occupancy[index] = waveguide.id
            results[waveguide.id] = TrackAssignment(
                waveguide.id, "assigned", index, grid[index], None
            )
    return [results[w.id] for w in waveguides]


def generate_assigned_routes_2d(
    waveguides: list[Waveguide],
    preparations: list[RoutePreparation],
    assignments: list[TrackAssignment],
    *,
    top_y: float,
    bottom_y: float,
    tol: float = 1e-9,
) -> list[Route]:
    """Generate only assigned orthogonal skeletons in original input direction.

    Explicit boundaries validate preparation semantics. No allocation, special Z,
    arc generation or collision validation is performed.
    """
    _validate_preparation_boundaries(top_y, bottom_y, tol)
    ids = [w.id for w in waveguides]
    prep_ids = [p.waveguide_id for p in preparations]
    assignment_ids = [a.waveguide_id for a in assignments]
    if any(len(set(values)) != len(values) for values in (ids, prep_ids, assignment_ids)):
        raise ValueError("Waveguide, preparation and assignment IDs must each be unique.")
    if set(ids) != set(prep_ids) or set(ids) != set(assignment_ids):
        raise ValueError("Waveguide, preparation and assignment ID sets must match.")
    preps = {p.waveguide_id: p for p in preparations}
    assigned = {a.waveguide_id: a for a in assignments}
    failures = {"unsupported_geometry", "unsupported_u_bend_span", "no_available_track"}
    # Validate the whole batch before calling geometry.
    for w in waveguides:
        if not isinstance(w.start_port.position, Point2D) or not isinstance(w.end_port.position, Point2D):
            raise ValueError(f"Waveguide {w.id} requires Point2D endpoints.")
        p, a = preps[w.id], assigned[w.id]
        if p != prepare_waveguide_2d(w, top_y, bottom_y, tol):
            raise ValueError(f"Preparation disagrees with endpoints: {w.id}.")
        if a.status == "assigned":
            if type(a.track_index) is not int or a.track_index < 0:
                raise ValueError(f"Assigned waveguide {w.id} requires nonnegative integer track_index.")
            if isinstance(a.track_y, bool) or not isinstance(a.track_y, (int, float)) or not isfinite(a.track_y):
                raise ValueError(f"Assigned waveguide {w.id} requires finite track_y.")
            if not bottom_y - tol <= a.track_y <= top_y + tol:
                raise ValueError(f"Assigned waveguide {w.id} track_y is outside boundaries.")
        elif a.status not in failures:
            raise ValueError(f"Unknown assignment status: {a.status}.")
        elif a.track_index is not None or a.track_y is not None:
            raise ValueError(f"Failed waveguide {w.id} must not carry a track.")
    routes: list[Route] = []
    for w in waveguides:
        p, a = preps[w.id], assigned[w.id]
        if a.status == "assigned":
            routes.append(route_waveguide_2d(
                w, p.route_type, a.track_y,
                p.side if p.route_type == "u" else "horizontal",
            ))
    return routes
