"""Read-only Dynamic-D diagnostics; PROJECT-SPECIFIC, never an allocator.

The terminal is the current project's endpoint view, not a proven paper mapping.
States and commit prefix are supplied explicitly. No history is inferred.
"""
from math import isfinite, sqrt
from typing import Mapping, Sequence

from .models import PMT, Point2D, Port, Waveguide
from .router_2d import RoutePreparation, _algorithmic_endpoints, prepare_waveguide_2d

SPACING_MM = 0.125
PITCH_MM = 0.175
RADIUS_MM = 5.0
STATES = frozenset({
    "committed", "pending_for_horizontal_routing",
    "failed_uncommitted", "unsupported",
})
# Current scan directions are separate from route x ordering.
CATEGORY_INFO = {
    "top-U": ("descending", "ascending", "descending"),
    "bottom-U": ("ascending", "ascending", "ascending"),
    "top->bottom Z": ("descending", "descending", "ascending"),
    "bottom->top Z": ("descending", "descending", "descending"),
}


def continuous_hierarchy_diagnostic(distance: float) -> dict:
    """Evaluate only the audited branch s <= D <= r+s; never extend or clamp it."""
    if not isfinite(distance) or not SPACING_MM <= distance <= RADIUS_MM + SPACING_MM:
        return {"status": "OUT_OF_FORMULA_DOMAIN", "D_mm": distance,
                "L_mm": None, "paper_ratio": None, "project_pitch_ratio": None}
    length = RADIUS_MM - sqrt(
        RADIUS_MM ** 2 - (RADIUS_MM + SPACING_MM - distance) ** 2
    )
    return {"status": "OK", "D_mm": distance, "L_mm": length,
            "paper_ratio": length / SPACING_MM,
            "project_pitch_ratio": length / PITCH_MM}


def _endpoint(port: Port) -> dict:
    """Copy endpoint scalars so output shares no mutable input geometry."""
    return {"port_id": port.id, "pmt_id": port.pmt_id,
            "local_id": port.local_id, "x": port.position.x, "y": port.position.y}


def diagnose_dynamic_d(
    waveguide: Waveguide,
    preparation: RoutePreparation,
    algorithmic_endpoints: tuple[Port, Port],
    pmts: Sequence[PMT],
    waveguides: Sequence[Waveguide],
    route_statuses: Mapping[int, str],
    commit_prefix: Sequence[int],
    special_route_ids: frozenset[int],
    *,
    top_y: float = 150.0,
    bottom_y: float = 0.0,
    tol: float = 1e-9,
) -> dict:
    """Report both geometric neighbors using caller-declared temporal state.

    Invalid/incomplete state is reported, never inferred from final assignments.
    Exact distance equality preserves ties; tol is used only for geometric side
    validation and the existing project's endpoint view/span boundary.
    """
    result = {
        "status": "OK", "route_id": waveguide.id,
        "terminal_mapping_status": "CURRENT_PROJECT_ENDPOINT_VIEW",
        "dangerous_side": "UNCONFIRMED",
        "direction_status": "UNCONFIRMED_DIRECTION",
        "category": None, "current_scan_direction": None,
        "terminal_side": None, "xt": None,
        "algorithmic_start_endpoint": None, "algorithmic_end_endpoint": None,
        "start_pmt": None, "end_pmt": None,
        "left": None, "right": None,
        "parameters": {"s_mm": SPACING_MM, "p_mm": PITCH_MM, "r_mm": RADIUS_MM},
        "commit_prefix": tuple(commit_prefix),
    }

    def invalid(status: str, detail: str) -> dict:
        result.update(status=status, detail=detail)
        return result

    if not all(isfinite(v) for v in (top_y, bottom_y, tol)) or tol < 0 or top_y - bottom_y <= 2 * tol:
        return invalid("INVALID_SIDE", "Invalid or overlapping boundary bands.")
    routes = {w.id: w for w in waveguides}
    if len(routes) != len(waveguides) or waveguide.id not in routes or routes[waveguide.id] != waveguide:
        return invalid("AMBIGUOUS", "Current route or unique route catalog is inconsistent.")
    if set(route_statuses) != set(routes) or any(s not in STATES for s in route_statuses.values()):
        return invalid("AMBIGUOUS", "Every route requires one explicit supported state.")
    if (len(set(commit_prefix)) != len(commit_prefix)
            or set(commit_prefix) != {i for i, s in route_statuses.items() if s == "committed"}):
        return invalid("AMBIGUOUS", "Commit prefix must exactly match committed states without duplicates.")
    if waveguide.id in commit_prefix or not set(special_route_ids) <= set(routes):
        return invalid("AMBIGUOUS", "Current route cannot be committed; special IDs must belong to catalog.")

    def side(port: Port) -> str | None:
        if abs(port.position.y - top_y) <= tol:
            return "top"
        if abs(port.position.y - bottom_y) <= tol:
            return "bottom"
        return None

    ports = {}
    pmt_ranges = {}
    for pmt in pmts:
        if pmt.id in pmt_ranges or not pmt.ports:
            return invalid("AMBIGUOUS", "PMT IDs must be unique and PMTs nonempty.")
        pmt_sides = set()
        for port in pmt.ports:
            if port.id in ports or port.pmt_id != pmt.id:
                return invalid("AMBIGUOUS", "Duplicate port or inconsistent PMT ownership.")
            if not isinstance(port.position, Point2D):
                return invalid("MISSING_ENDPOINT", "Every PMT port needs a finite Point2D.")
            if not all(isfinite(v) for v in (port.position.x, port.position.y)):
                return invalid("MISSING_ENDPOINT", "Nonfinite endpoint.")
            ports[port.id] = port
            pmt_sides.add(side(port))
        if None in pmt_sides or len(pmt_sides) != 1:
            return invalid("INVALID_SIDE", "PMT ports must share a single explicit boundary.")
        xs = [p.position.x for p in pmt.ports]
        pmt_ranges[pmt.id] = (next(iter(pmt_sides)), min(xs), max(xs))
    owners = {}
    for w in waveguides:
        for port in (w.start_port, w.end_port):
            if ports.get(port.id) != port or port.id in owners:
                return invalid("AMBIGUOUS", "Each route endpoint must match a unique catalog port.")
            owners[port.id] = w.id
    if set(owners) != set(ports):
        return invalid("AMBIGUOUS", "A PMT endpoint has no explicit route state.")

    side_orders = {}
    for label in ("top", "bottom"):
        ordered = sorted((lo, hi, pid) for pid, (s, lo, hi) in pmt_ranges.items() if s == label)
        if any(a[1] >= b[0] for a, b in zip(ordered, ordered[1:])):
            return invalid("AMBIGUOUS", "Overlapping/touching PMT x ranges do not define strict geometric order.")
        side_orders[label] = [pid for _, _, pid in ordered]

    expected = prepare_waveguide_2d(waveguide, top_y, bottom_y, tol)
    if preparation != expected:
        return invalid("AMBIGUOUS", "Preparation disagrees with endpoint boundaries.")
    expected_endpoints = _algorithmic_endpoints(waveguide, preparation, tol)
    if algorithmic_endpoints != expected_endpoints:
        return invalid("AMBIGUOUS", "Supplied endpoint view differs from current project helper.")
    a, b = expected_endpoints
    category = (f"{side(a)}-U" if preparation.route_type == "u"
                else f"{side(a)}->{side(b)} Z")
    current_scan, paper_order, paper_scan = CATEGORY_INFO[category]
    result.update(
        category=category, current_scan_direction=current_scan,
        current_primary_order="ascending", paper_primary_order=paper_order,
        paper_scan_direction=paper_scan,
        paper_scan_differs=current_scan != paper_scan,
        terminal_side=side(b), xt=b.position.x,
        start_pmt=a.pmt_id, end_pmt=b.pmt_id,
        algorithmic_start_endpoint=_endpoint(a), algorithmic_end_endpoint=_endpoint(b),
    )

    def special(w: Waveguide) -> bool:
        return w.id in special_route_ids or (
            side(w.start_port) != side(w.end_port)
            and abs(w.start_port.position.x - w.end_port.position.x) < 2 * RADIUS_MM - tol
        )

    if special(waveguide):
        result["category"] = "special-Z"
        result["current_scan_direction"] = None
        return invalid("UNSUPPORTED_GEOMETRY_FOR_HIERARCHY_DIAGNOSTIC",
                       "Special geometry has no ordinary horizontal-pending interpretation.")
    if (route_statuses[waveguide.id] == "unsupported"
            or abs(a.position.x - b.position.x) < 2 * RADIUS_MM - tol):
        return invalid("UNSUPPORTED_GEOMETRY", "Current route is not supported ordinary geometry.")
    if route_statuses[waveguide.id] != "pending_for_horizontal_routing":
        return invalid("AMBIGUOUS", "Current ordinary route must be explicitly pending.")
    ordered_ids = side_orders[side(b)]
    index = ordered_ids.index(b.pmt_id)

    def neighbor(neighbor_id: int | None) -> dict:
        out = {"status": "NO_ADJACENT", "neighbor_pmt": neighbor_id,
               "pending_count": 0, "pending_candidates": [],
               "nearest_candidates": [], "nearest_distance": None,
               "unsupported_related_routes": [], "excluded_candidates": [],
               "continuous": None}
        if neighbor_id is None:
            return out
        for port in sorted((p for p in ports.values() if p.pmt_id == neighbor_id), key=lambda p: (p.position.x, p.id)):
            route_id = owners[port.id]
            item = {"route_id": route_id, **_endpoint(port), "route_status": route_statuses[route_id]}
            if special(routes[route_id]) or route_statuses[route_id] == "unsupported":
                out["unsupported_related_routes"].append(item)
            elif route_id == waveguide.id:
                out["excluded_candidates"].append({**item, "exclusion": "CURRENT_ROUTE"})
            elif route_statuses[route_id] == "pending_for_horizontal_routing":
                out["pending_candidates"].append(item)
            else:
                out["excluded_candidates"].append({**item, "exclusion": route_statuses[route_id]})
        candidates = out["pending_candidates"]
        out["pending_count"] = len(candidates)
        if not candidates:
            out["status"] = "NO_PENDING"
            return out
        distance = min(abs(b.position.x - c["x"]) for c in candidates)
        nearest = [c.copy() for c in candidates if abs(b.position.x - c["x"]) == distance]
        out.update(status="TIE_NEAREST" if len(nearest) > 1 else "OK",
                   nearest_distance=distance, nearest_candidates=nearest,
                   continuous=continuous_hierarchy_diagnostic(distance))
        return out

    result["left"] = neighbor(ordered_ids[index - 1] if index > 0 else None)
    result["right"] = neighbor(ordered_ids[index + 1] if index + 1 < len(ordered_ids) else None)
    return result
