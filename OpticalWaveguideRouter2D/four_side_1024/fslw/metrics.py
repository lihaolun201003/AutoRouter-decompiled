"""Recompute the FSLW R=40 mm / 30 µm dual-height metric set from primitives.

Round-2 deliverable for ``four_side_1024/fslw/SPEC.md`` (§6 metrics, §8 output
tree, §10 visualisation contract).  Two layers of numbers are produced:

* **plane statistics** (one 512-connection, 1024-port 2D problem per row height):
  ``planes/<TOPOLOGY>/<ALGO>/<z1|z2>/statistics.json``;
* **combined statistics** (the two physical heights side by side):
  ``combined/<TOPOLOGY>/<ALGO>/statistics.json``.

Everything geometric is recomputed from the analytic route ``primitives``; the
router's embedded self-report is never copied.  Authoritative violation
counters are merged from the independent ``audit_strict.json`` written by the
validator (SPEC §4), with a stale-audit mtime guard: an audit older than the
current ``routes.json`` is ignored and flagged instead of silently merged.

Process convention (SPEC §1/§6): R = 40 mm fixed, width 0.050 mm, edge gap
0.030 mm -> centreline clearance 0.080 mm, sagitta 0.0005 mm, propagation loss
**0.05 dB/cm**.  Bend loss and crossing loss are **unknown/uncalibrated** and
are reported as ``{"status": "unknown_uncalibrated", "value": null}`` -- never
invented, and the legacy polymer model is never presented as glass truth.

Metric definitions that the SPEC leaves open (documented here and repeated in
``statistics.json["metric_sources"]``/``["notes"]``):

``unnecessary_detour_mm``
    per routed route ``analytic_length - manhattan_lower_bound`` where the
    bound is ``|x2-x1| + |y2-y1|`` between the fixed endpoints (the minimum
    possible orthogonally-routed length).  Mean/max/total reported; negative
    values are impossible and flagged.
``straight_fraction``
    line length / total length, with the horizontal-only and vertical-only
    fractions reported separately (SPEC §6 "直线长度占比").
``route_length_density``
    sampled centreline length per 5 x 5 mm cell (mm of waveguide per cell);
    its peak and top cells are the local-congestion hotspots.
``port_region_length_mm``
    waveguide length inside the 5 mm band along each board edge (port/coupling
    region), with a per-area density.
``cross_plane_projected_overlap``
    informational only: XY-projected intersections between plane-z1 and
    plane-z2 centrelines, with the guaranteed per-port projection coincidences
    classified separately.  By SPEC §2 it is **never** a violation.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.fslw.metrics --run-dir \\
        outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V1/B/z1
    .venv\\Scripts\\python.exe -m four_side_1024.fslw.metrics --combined-dir \\
        outputs/four_side_1024_fslw_R40_gap30_abcd/combined/V1/B
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as pystatistics
import time
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

from .. import geometry as geom
from ..abcd import metrics as abcd_metrics
from ..d56 import validate_d56 as d56_validator
from . import config as fslw_config

try:  # Lead-authored ports model (frozen API, see round-2 coordination)
    from . import ports as fslw_ports
except Exception:  # pragma: no cover - reported instead of guessed
    fslw_ports = None

SCHEMA_PLANE = "four_side_1024_fslw_plane_statistics_v1"
SCHEMA_COMBINED = "four_side_1024_fslw_combined_statistics_v1"
TOOL = "four_side_1024.fslw.metrics"

#: metric names expected by SPEC §6 (kept as a constant for tests/readers)
PLANE_REQUIRED_METRICS = (
    "routed", "unrouted", "routing_rate", "by_pair", "by_relation",
    "mean_length_mm", "max_length_mm", "min_length_mm", "total_length_mm",
    "mean_bend_count", "total_bends", "mean_straight_fraction",
    "horizontal_straight_fraction", "vertical_straight_fraction",
    "mean_unnecessary_detour_mm", "total_unnecessary_detour_mm",
    "crossing_count", "crossing_angle_histogram",
    "small_angle_crossing_count", "spacing_violation_pairs", "overlap_pairs",
    "touch_pairs", "crossing_window_overlap_pairs", "self_intersections",
    "radius_violations", "boundary_violations", "diagonal_line_violations",
    "free_arc_violations", "propagation_loss", "optical_loss_breakdown",
    "mean_min_gap_mm", "route_length_grid_peak_mm", "crossing_grid_peak",
    "port_region_length_mm", "symmetry", "candidate_evaluations",
    "runtime_seconds", "pareto",
)
COMBINED_REQUIRED_METRICS = (
    "routed", "unrouted", "routing_rate", "by_plane", "by_relation",
    "total_length_mm", "same_plane_crossings", "cross_plane_projected_overlap",
    "propagation_loss", "optical_loss_breakdown", "pareto",
)

PAIR_ORDER = ("NS", "EW", "EN", "ES", "SW", "NW")
RELATION_PAIRS = OrderedDict((("opposite", ("NS", "EW")),
                              ("adjacent", ("EN", "ES", "SW", "NW"))))
PAIR_RELATION = {pair: relation
                 for relation, pairs in RELATION_PAIRS.items() for pair in pairs}
PLANE_ROWS = {"z1": 1, "z2": 2}
PLANE_Z = {"z1": 0.0, "z2": 0.5}
CONNECTIONS_PER_PLANE = 512
TOTAL_CONNECTIONS = 1024
GRID_MM = 5.0
PORT_BAND_MM = 5.0
ROUTED_STATUS = {"routed", "success", "succeeded", "ok", "routed_ok"}
FAILED_STATUS = {"failed", "failure", "fail", "blocked", "rejected"}
ROUTING_DENSITY_SAMPLE_MM = 0.5
PROJECTED_SAGITTA_MM = 0.02
#: same single-route / pair tolerance conventions as d56/abcd SPEC
ORTHO_TOL = 1e-9
RADIUS_TOL = 1e-9
QUARTER_TOL = 1e-9
POSE_TOL = 1e-7
BOUNDS_TOL = 1e-8
PAIR_EPS = 1e-8


# ---------------------------------------------------------------------------
# small helpers (JSON / numbers / statuses)
# ---------------------------------------------------------------------------
def _load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _json_safe(value):
    return abcd_metrics._json_safe(value)


def _sha256(path):
    return abcd_metrics._sha256(path)


def _number(value):
    return abcd_metrics._number(value)


def _round(value, digits=6):
    return abcd_metrics._round(value, digits)


def _first(mapping, keys, default=None):
    return abcd_metrics._first(mapping, keys, default)


def _status(record):
    status = abcd_metrics._status(record)
    return "routed" if status == "routed" else "failed"


def _pair_of(record):
    return abcd_metrics._pair_of(record)


def _relation_of(record):
    return abcd_metrics._relation_of(record)


def _mean(values):
    values = [value for value in values if value is not None]
    return (sum(values) / len(values)) if values else None


def _safe_div(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _percentiles(values, points=(50, 90, 99)):
    if not values:
        return {f"p{point}": None for point in points}
    return {f"p{point}": float(np.percentile(values, point)) for point in points}


def _plane_run_dir(root, topology, algorithm, plane):
    return Path(root) / "planes" / topology / algorithm / plane


def _sensitivity_run_dir(root, config_name, topology, algorithm, plane):
    return Path(root) / "sensitivity" / config_name / topology / algorithm / plane


def _combined_run_dir(root, topology, algorithm):
    return Path(root) / "combined" / topology / algorithm


# ---------------------------------------------------------------------------
# process / configuration resolution
# ---------------------------------------------------------------------------
_PROCESS_ALIASES = {
    "min_radius_mm": ("min_radius_mm", "min_bend_radius_mm", "radius_mm"),
    "radius_mm": ("radius_mm", "min_radius_mm", "min_bend_radius_mm"),
    "width_mm": ("width_mm", "waveguide_width_mm"),
    "edge_gap_mm": ("edge_gap_mm", "min_edge_gap_mm", "gap_mm"),
    "clearance_mm": ("clearance_mm", "min_centerline_clearance_mm",
                     "centerline_clearance_mm"),
    "sagitta_mm": ("sagitta_mm",),
    "propagation_loss_db_per_cm": ("propagation_loss_db_per_cm",
                                   "propagation_loss_db_cm", "loss_db_per_cm"),
    "min_cross_angle_deg": ("min_cross_angle_deg", "crossing_small_angle_deg"),
    "plane": ("plane", "plane_name"),
    "z_mm": ("z_mm", "z_mm_model", "height_mm"),
    "topology": ("topology", "topology_name"),
    "algorithm": ("algorithm", "algorithm_name"),
    "experiment": ("experiment", "run_id", "name"),
    "port_model": ("port_model", "endpoint_mode"),
    "seed": ("seed", "random_seed"),
    "eval_budget": ("eval_budget", "candidate_evaluation_budget"),
    "time_budget_seconds": ("time_budget_seconds", "time_budget",
                            "search_seconds", "time_limit_seconds"),
}


def _flatten_process_sources(routes_meta, config_payload, run_dir):
    merged = {}
    if isinstance(routes_meta, dict):
        for key in ("experiment", "topology", "algorithm", "plane", "z_mm",
                    "port_model", "units", "layer"):
            if routes_meta.get(key) is not None:
                merged[key] = routes_meta[key]
    algorithm = None
    if isinstance(routes_meta, dict):
        algorithm = routes_meta.get("algorithm_detail") or routes_meta.get(
            "algorithm")
    sources = [routes_meta.get("config") if isinstance(routes_meta, dict) else None,
               algorithm,
               routes_meta.get("process") if isinstance(routes_meta, dict) else None,
               routes_meta.get("run_info") if isinstance(routes_meta, dict) else None,
               config_payload]
    if isinstance(config_payload, dict):
        sources.extend([config_payload.get("process"),
                        config_payload.get("physics"),
                        config_payload.get("budget"),
                        config_payload.get("run_info")])
    for source in sources:
        if isinstance(source, dict):
            for key, value in source.items():
                if value is not None and not isinstance(value, (dict, list)):
                    merged[key] = value
    return merged


def load_process(routes_meta=None, config_payload=None, run_dir=None):
    """Resolve the round-2 process parameters (SPEC §1) from artifacts.

    The Lead-authored :mod:`four_side_1024.fslw.config` module is the source of
    truth; artifacts only override it for the Phase-11 sensitivity matrix.
    """
    merged = _flatten_process_sources(routes_meta or {}, config_payload, run_dir)
    process = dict(
        board_mm=[fslw_config.BOARD_MM, fslw_config.BOARD_MM],
        width_mm=fslw_config.WIDTH_MM,
        edge_gap_mm=fslw_config.EDGE_GAP_MM,
        clearance_mm=fslw_config.CLEARANCE_MM,
        min_radius_mm=fslw_config.RADIUS_MM,
        radius_mm=fslw_config.RADIUS_MM,
        fixed_radius_40mm=getattr(fslw_config, "FIXED_RADIUS_40MM", True),
        sagitta_mm=fslw_config.SAGITTA_MM,
        propagation_loss_db_per_cm=fslw_config.PROPAGATION_LOSS_DB_PER_CM,
        min_cross_angle_deg=fslw_config.MIN_CROSS_ANGLE_DEG,
        port_model=getattr(fslw_config, "PORT_MODEL", "real_2x16_dual_height"),
        plane_z_mm=dict(getattr(fslw_config, "PLANE_Z_MM", {1: 0.0, 2: 0.5})),
        plane_row=dict(getattr(fslw_config, "PLANE_ROW", {"z1": 1, "z2": 2})),
        connections_per_plane=CONNECTIONS_PER_PLANE,
        total_connections=TOTAL_CONNECTIONS,
        source="four_side_1024.fslw.config (round-2 convention)",
        overrides={},
    )
    for key, aliases in _PROCESS_ALIASES.items():
        for alias in aliases:
            if alias in merged and merged[alias] is not None:
                value = merged[alias]
                if isinstance(value, str) and key in (
                        "min_radius_mm", "radius_mm", "width_mm", "edge_gap_mm",
                        "clearance_mm", "sagitta_mm",
                        "propagation_loss_db_per_cm"):
                    number = _number(value)
                    if number is None:
                        continue
                    value = number
                process[key] = value
                break
    # derived clearance if only width+gap were overridden (sensitivity runs)
    if "clearance_mm" not in merged:
        width = _number(process.get("width_mm"))
        gap = _number(process.get("edge_gap_mm"))
        if width is not None and gap is not None:
            process["clearance_mm"] = float(width) + float(gap)
    process["radius_mm"] = _number(process.get("min_radius_mm")) or fslw_config.RADIUS_MM
    process["min_radius_mm"] = process["radius_mm"]
    process["sagitta_mm"] = _number(process.get("sagitta_mm")) or fslw_config.SAGITTA_MM
    process["clearance_mm"] = (_number(process.get("clearance_mm"))
                               or fslw_config.CLEARANCE_MM)
    process["width_mm"] = _number(process.get("width_mm")) or fslw_config.WIDTH_MM
    process["edge_gap_mm"] = _number(process.get("edge_gap_mm"))
    process["propagation_loss_db_per_cm"] = (
        _number(process.get("propagation_loss_db_per_cm"))
        or fslw_config.PROPAGATION_LOSS_DB_PER_CM)
    if process["edge_gap_mm"] is None:
        process["edge_gap_mm"] = (process["clearance_mm"] - process["width_mm"])
    process["overrides"] = {
        key: value for key, value in merged.items()
        if key in {alias for aliases in _PROCESS_ALIASES.values()
                   for alias in aliases}}
    process["plane"] = _normalise_plane(process.get("plane"))
    process["z_mm"] = PLANE_Z.get(process["plane"], process.get("z_mm"))
    return process


def _normalise_plane(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("z1", "1", "plane1", "plane_1", "row1"):
        return "z1"
    if text in ("z2", "2", "plane2", "plane_2", "row2"):
        return "z2"
    return None


# ---------------------------------------------------------------------------
# route loading / port table
# ---------------------------------------------------------------------------
def load_routes(routes_path):
    payload = _load_json(routes_path)
    if isinstance(payload, dict):
        records = payload.get("routes") or []
        meta = {key: payload[key] for key in payload
                if key not in ("routes", "failed_routes")}
    elif isinstance(payload, list):
        records = payload
        meta = {}
    else:
        raise ValueError(f"unrecognised routes file {routes_path}")
    if not isinstance(records, list):
        raise ValueError(f"{routes_path}: 'routes' is not a list")
    routed = [record for record in records if _status(record) == "routed"]
    failed = [record for record in records if _status(record) != "routed"]
    return payload, meta, records, routed, failed


def _records_plane(records, meta):
    plane = _normalise_plane((meta or {}).get("plane"))
    if plane is None:
        for record in records:
            plane = _normalise_plane(record.get("plane"))
            if plane:
                break
    for record in records:
        if record.get("plane") is None:
            record["plane"] = plane
        if record.get("z_mm") is None:
            record["z_mm"] = PLANE_Z.get(plane)
    return plane


def load_plane_ports(topology, plane, process=None):
    """Plane endpoint/connector tables via the frozen Lead ``ports`` API."""
    if fslw_ports is None:
        return None
    try:
        routes, endpoints, connectors, validation = fslw_ports.load_plane(
            topology, plane)
        return {"routes": routes, "endpoints": endpoints,
                "connectors": connectors, "validation": validation,
                "source": "four_side_1024.fslw.ports.load_plane"}
    except Exception as exc:  # noqa: BLE001 - report, never guess
        return {"routes": None, "endpoints": None, "connectors": None,
                "validation": None,
                "error": f"{type(exc).__name__}: {exc}"}


def _derive_endpoints(records, process):
    """Fallback endpoint table recovered from routed primitives only."""
    endpoints = {}
    for record in records:
        primitives = record.get("primitives") or []
        if not primitives:
            continue
        source = record.get("source_endpoint")
        target = record.get("target_endpoint")
        plane = record.get("plane") or process.get("plane")
        if source and source not in endpoints:
            endpoints[source] = {"endpoint_id": source,
                                 "routing_xy": [float(v) for v in primitives[0]["p0"]],
                                 "inward": None, "plane": plane,
                                 "z_mm": PLANE_Z.get(plane),
                                 "derived_from_primitive": True}
        if target and target not in endpoints:
            endpoints[target] = {"endpoint_id": target,
                                 "routing_xy": [float(v) for v in primitives[-1]["p1"]],
                                 "inward": None, "plane": plane,
                                 "z_mm": PLANE_Z.get(plane),
                                 "derived_from_primitive": True}
    return endpoints


# ---------------------------------------------------------------------------
# validator kernel (authoritative pair geometry) and staleness guard
# ---------------------------------------------------------------------------
def _pair_kernel():
    """Return ``(module, name)`` providing prepare_route/audit_route_pairs."""
    try:
        from . import validate_fslw as fslw_validator
        if (hasattr(fslw_validator, "prepare_route")
                and hasattr(fslw_validator, "audit_route_pairs")):
            return fslw_validator, "four_side_1024.fslw.validate_fslw"
    except Exception:  # noqa: BLE001 - fall back to the d56 kernel (same math)
        pass
    return d56_validator, "four_side_1024.d56.validate_d56 (parameterised R/gap)"


def _prepare(kernel, primitives, route_id):
    return kernel.prepare_route(primitives, route_id=route_id)


def _candidate_route_pairs(prepared, pad):
    """Broad phase route pairs whose bounding boxes are within ``pad``."""
    if len(prepared) < 2:
        return []
    boxes = np.array([list(route.bbox) for route in prepared], dtype=float)
    pairs = []
    for index in range(len(prepared) - 1):
        x0, y0, x1, y1 = boxes[index]
        rest = boxes[index + 1:]
        dx = np.maximum(rest[:, 0] - x1, x0 - rest[:, 2])
        np.maximum(dx, 0.0, out=dx)
        dy = np.maximum(rest[:, 1] - y1, y0 - rest[:, 3])
        np.maximum(dy, 0.0, out=dy)
        near = np.flatnonzero(np.hypot(dx, dy) <= pad)
        pairs.extend((index, index + 1 + int(offset)) for offset in near)
    return pairs


def _distance_primitives():
    """Exact line/arc distance helpers from the read-only d56 kernel."""
    return d56_validator


def _route_min_gap(first, second, cap):
    kernel = _distance_primitives()
    best = cap
    for prim_a in first.prims:
        box_a = prim_a.bbox
        for prim_b in second.prims:
            box_b = prim_b.bbox
            dx = max(box_a[0] - box_b[2], box_b[0] - box_a[2], 0.0)
            if dx >= best:
                continue
            dy = max(box_a[1] - box_b[3], box_b[1] - box_a[3], 0.0)
            if dy >= best:
                continue
            try:
                if kernel._prims_intersect(prim_a, prim_b):  # noqa: SLF001
                    continue
                distance = kernel._exact_distance(  # noqa: SLF001
                    prim_a, prim_b, bbox_disjoint=(dx > 0.0 or dy > 0.0))
            except Exception:  # noqa: BLE001 - predicate failure is not a gap
                continue
            if distance < best:
                best = distance
    return best


_GAP_PADS = (0.01, 0.08, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 160.0)


def compute_min_gaps(routed, process):
    """Per-route nearest non-crossing centreline distance (same-plane)."""
    prepared = []
    ids = []
    for record in routed:
        primitives = record.get("primitives") or []
        if not primitives:
            continue
        try:
            prepared.append(d56_validator.prepare_route(
                primitives, route_id=record.get("route_id")))
            ids.append(record.get("route_id"))
        except Exception:  # noqa: BLE001 - skip unparsable geometry
            continue
    count = len(prepared)
    infinite = float("inf")
    best = [infinite] * count
    remaining = set(range(count))
    processed = set()
    for pad in _GAP_PADS:
        if not remaining:
            break
        pairs = _candidate_route_pairs(prepared, pad)
        fresh = [(first, second) for first, second in pairs
                 if (first, second) not in processed
                 and (first in remaining or second in remaining)]
        processed.update(fresh)
        for first, second in fresh:
            cap = best[first] if best[first] < best[second] else best[second]
            distance = _route_min_gap(prepared[first], prepared[second], cap)
            if distance < best[first]:
                best[first] = distance
            if distance < best[second]:
                best[second] = distance
        for index in list(remaining):
            if best[index] <= pad:
                remaining.discard(index)
    values = [(route_id, value) for route_id, value in zip(ids, best)
              if value < infinite]
    distances = [value for _, value in values]
    solved = sorted(distances)
    median = None
    if solved:
        middle = len(solved) // 2
        median = (solved[middle] if len(solved) % 2 else
                  0.5 * (solved[middle - 1] + solved[middle]))
    return {
        "mean_min_gap_mm": _mean(distances),
        "median_min_gap_mm": median,
        "min_min_gap_mm": min(distances) if distances else None,
        "max_min_gap_mm": max(distances) if distances else None,
        "routes_with_min_gap": len(values),
        "unresolved_route_ids": [route_id for route_id, value in zip(ids, best)
                                 if value == infinite],
        "per_route_min_gap_mm": {str(route_id): _round(value)
                                 for route_id, value in values},
        "definition": ("per-route minimum exact centreline distance to any "
                       "non-crossing primitive of another routed route in the "
                       "same plane; mean over routes with a neighbour"),
    }


# ---------------------------------------------------------------------------
# crossing / pair-audit recomputation
# ---------------------------------------------------------------------------
_HIST_BINS = (("0-1", 0.0, 1.0), ("1-5", 1.0, 5.0), ("5-10", 5.0, 10.0),
              ("10-20", 10.0, 20.0), ("20-30", 20.0, 30.0),
              ("30-45", 30.0, 45.0), ("45-60", 45.0, 60.0),
              ("60-75", 60.0, 75.0), ("75-90", 75.0, 90.000001))


def _empty_histogram():
    return OrderedDict((label, 0) for label, _, _ in _HIST_BINS)


def compute_pair_audit(routed, process, strict=True):
    """Recompute same-plane crossings and pair violations at 0.08 mm clearance."""
    kernel, kernel_name = _pair_kernel()
    prepared = []
    skipped = []
    for record in routed:
        primitives = record.get("primitives") or []
        if not primitives:
            skipped.append(record.get("route_id"))
            continue
        try:
            prepared.append(_prepare(kernel, primitives, record.get("route_id")))
        except Exception:  # noqa: BLE001 - unparsable geometry is reported
            skipped.append(record.get("route_id"))
    clearance = float(process.get("clearance_mm") or fslw_config.CLEARANCE_MM)
    sagitta = float(process.get("sagitta_mm") or fslw_config.SAGITTA_MM)
    policy = "strict" if strict else "exact"
    started = time.perf_counter()
    try:
        result = kernel.audit_route_pairs(prepared, clearance=clearance,
                                          sagitta=sagitta, policy=policy)
    except TypeError:
        result = kernel.audit_route_pairs(prepared, policy=policy)
    elapsed = time.perf_counter() - started
    crossings = result.get("crossings") or []
    histogram = _empty_histogram()
    small_angle = 0
    small_angle_5 = 0
    cells = Counter()
    for crossing in crossings:
        angle = float(crossing.get("angle_deg") or 0.0)
        if angle < 10.0:
            small_angle += 1
        if angle < 5.0:
            small_angle_5 += 1
        for label, low, high in _HIST_BINS:
            if low <= angle < high:
                histogram[label] += 1
                break
        cells[(int(math.floor(float(crossing["x"]) / GRID_MM)),
               int(math.floor(float(crossing["y"]) / GRID_MM)))] += 1
    densest = [{"x_min_mm": ix * GRID_MM, "y_min_mm": iy * GRID_MM,
                "count": int(count)} for (ix, iy), count in cells.most_common(10)]
    violations = result.get("violations") or []
    result_dict = dict(
        crossing_count=int(result.get("crossing_count") or 0),
        crossing_pair_count=int(result.get("crossing_pair_count") or 0),
        crossings=crossings,
        crossing_angle_histogram=dict(histogram),
        small_angle_threshold_deg=10.0,
        small_angle_crossing_count=int(small_angle),
        small_angle_5deg_threshold_deg=5.0,
        small_angle_5deg_crossing_count=int(small_angle_5),
        crossing_grid_mm=GRID_MM,
        crossing_grid_peak=int(densest[0]["count"]) if densest else 0,
        crossing_grid_peak_cell=([densest[0]["x_min_mm"], densest[0]["y_min_mm"]]
                                 if densest else None),
        densest_crossing_cells=densest,
        candidate_pair_count=int(result.get("candidate_pair_count") or 0),
        spacing_violation_pairs=int(result.get("spacing_violation_pairs") or 0),
        overlap_pairs=int(result.get("overlap_pairs") or 0),
        touch_pairs=int(result.get("touch_pairs") or 0),
        crossing_window_overlap_pairs=int(
            result.get("crossing_window_overlap_pairs",
                       result.get("crossing_zone_overlap_pairs")) or 0),
        double_cross_pairs=int(result.get("double_cross_pairs") or 0),
        crossing_window_excessive_pairs=int(
            result.get("crossing_window_excessive_pairs") or 0),
        violation_pair_count=int(result.get("violation_pair_count") or 0),
        min_non_crossing_centerline_mm=result.get(
            "min_non_crossing_centerline_mm"),
        crossing_window_count=result.get("crossing_window_count"),
        crossing_window_max_mm=result.get("crossing_window_max_mm"),
        crossing_window_mean_mm=result.get("crossing_window_mean_mm"),
        violations=list(violations[:50]),
        violation_pair_count_total=len(violations),
        policy_used=result.get("policy", policy),
        kernel=kernel_name,
        clearance_mm=clearance,
        sagitta_mm=sagitta,
        prepared_route_count=len(prepared),
        skipped_route_ids=skipped,
        recompute_runtime_seconds=elapsed,
    )
    return result_dict


def _audit_path_for(routes_path):
    routes_path = Path(routes_path)
    run_dir = routes_path.parent
    return run_dir / "audit_strict.json"


def _audit_is_stale(audit_path, routes_path, tolerance_seconds=0.5):
    try:
        return (Path(audit_path).stat().st_mtime
                < Path(routes_path).stat().st_mtime - tolerance_seconds)
    except OSError:
        return False


def load_audit(routes_path, explicit_path=None, label=None):
    """Load the authoritative strict audit with a stale-file guard."""
    candidates = []
    if explicit_path is not None:
        candidates.append((Path(explicit_path), label or "audit_strict"))
    else:
        candidates.append((_audit_path_for(routes_path), "audit_strict"))
    for path, derived_label in candidates:
        if not path.exists():
            return None, {"status": "missing", "candidates": [str(path)]}
        if _audit_is_stale(path, routes_path):
            return None, {"status": "stale_ignored", "file": str(path),
                          "note": "audit mtime predates routes.json; not merged"}
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            return None, {"status": "unreadable", "file": str(path),
                          "error": f"{type(exc).__name__}: {exc}"}
        report = _audit_values(payload, path, derived_label)
        return report, {"status": "merged", "file": str(path)}
    return None, {"status": "missing"}


_AUDIT_ALIASES = {
    "crossing_count": ("crossing_count",),
    "crossing_angle_histogram": ("crossing_angle_histogram",),
    "crossing_pair_count": ("crossing_pair_count",),
    "small_angle_crossing_count": ("small_angle_crossing_count",),
    "small_angle_threshold_deg": ("small_angle_threshold_deg",),
    "spacing_violation_pairs": ("spacing_violation_pairs", "spacing_pairs"),
    "overlap_pairs": ("overlap_pairs",),
    "touch_pairs": ("touch_pairs",),
    "crossing_window_overlap_pairs": ("crossing_window_overlap_pairs",
                                      "crossing_zone_overlap_pairs"),
    "double_cross_pairs": ("double_cross_pairs",),
    "crossing_window_excessive_pairs": ("crossing_window_excessive_pairs",),
    "violation_pair_count": ("violation_pair_count",),
    "self_intersections": ("self_intersections",),
    "self_overlaps": ("self_overlaps",),
    "self_spacing_violations": ("self_spacing_violations",),
    "radius_violations": ("radius_violations",),
    "boundary_violations": ("boundary_violations",),
    "diagonal_line_violations": ("diagonal_line_violations",),
    "free_arc_violations": ("free_arc_violations",
                            "free_or_short_s_arc_violations"),
    "layer_violations": ("layer_violations", "nonzero_layer_violations"),
    "min_non_crossing_centerline_mm": ("min_non_crossing_centerline_mm",),
}


def _audit_values(payload, path, label):
    values = OrderedDict()
    for field, aliases in _AUDIT_ALIASES.items():
        for alias in aliases:
            if isinstance(payload, dict) and payload.get(alias) is not None:
                values[field] = payload[alias]
                break
    return {
        "file": str(path),
        "label": label or "audit_strict",
        "policy": _first(payload, ("policy_used", "policy")),
        "passed": payload.get("passed") if isinstance(payload, dict) else None,
        "route_count": _first(payload, ("route_count", "connections")),
        "routed_count": payload.get("routed_count"),
        "checked_count": _first(payload, ("d56_checked_count", "checked_count")),
        "passed_count": _first(payload, ("d56_passed_count", "passed_count")),
        "failed_count": _first(payload, ("d56_failed_count", "failed_count")),
        "error_count": len(payload.get("errors") or [])
        if isinstance(payload, dict) else None,
        "warning_count": len(payload.get("warnings") or [])
        if isinstance(payload, dict) else None,
        "violation_count": len(payload.get("violations") or [])
        if isinstance(payload, dict) else None,
        "candidate_pair_count": _first(payload, ("candidate_pair_count",)),
        "runtime_seconds": _first(payload, ("runtime_seconds",
                                            "pair_audit_runtime_seconds")),
        "crossing_window_count": _first(payload, ("crossing_window_count",)),
        "crossing_window_max_mm": _first(payload, ("crossing_window_max_mm",)),
        "crossing_window_mean_mm": _first(payload, ("crossing_window_mean_mm",)),
        "sha256": _sha256(path),
        "values": values,
    }


# ---------------------------------------------------------------------------
# single-route geometry + violations (independent of the router's checker)
# ---------------------------------------------------------------------------
def _line_orientation(primitive):
    dx = abs(float(primitive["p1"][0]) - float(primitive["p0"][0]))
    dy = abs(float(primitive["p1"][1]) - float(primitive["p0"][1]))
    if dy <= ORTHO_TOL and dx > ORTHO_TOL:
        return "horizontal"
    if dx <= ORTHO_TOL and dy > ORTHO_TOL:
        return "vertical"
    return "diagonal"


def _tangent_at(primitive, end=False):
    if primitive.get("kind") == "line":
        p0 = primitive["p0"]
        p1 = primitive["p1"]
        norm = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if norm == 0.0:
            return None
        return ((p1[0] - p0[0]) / norm, (p1[1] - p0[1]) / norm)
    angle = float(primitive["start_angle"]) + (
        float(primitive["sweep"]) if end else 0.0)
    sign = 1.0 if float(primitive["sweep"]) > 0 else -1.0
    return (-sign * math.sin(angle), sign * math.cos(angle))


def _short_s_pair_valid(first, second, radius):
    """Validate the legacy short-S pair geometry analytically (R-generic)."""
    theta = abs(float(first["sweep"]))
    if not (0.0 < theta < math.pi / 2.0 - 1e-12):
        return False, "theta_out_of_range"
    if abs(abs(float(second["sweep"])) - theta) > 1e-9:
        return False, "unequal_theta"
    if float(first["sweep"]) * float(second["sweep"]) > 0.0:
        return False, "not_opposite_sweep"
    u = _tangent_at(first, end=False)
    if u is None:
        return False, "degenerate_tangent"
    delta = (float(second["p1"][0]) - float(first["p0"][0]),
             float(second["p1"][1]) - float(first["p0"][1]))
    longitudinal = delta[0] * u[0] + delta[1] * u[1]
    lateral = abs(u[0] * delta[1] - u[1] * delta[0])
    expected_lateral = 2.0 * radius * (1.0 - math.cos(theta))
    expected_longitudinal = 2.0 * radius * math.sin(theta)
    if not (0.0 < lateral < 2.0 * radius):
        return False, "displacement_out_of_range"
    if abs(lateral - expected_lateral) > POSE_TOL:
        return False, "lateral_displacement_mismatch"
    if abs(abs(longitudinal) - expected_longitudinal) > POSE_TOL:
        return False, "longitudinal_displacement_mismatch"
    theta_from_d = math.acos(max(-1.0, min(1.0, 1.0 - lateral / (2.0 * radius))))
    if abs(theta_from_d - theta) > 1e-7:
        return False, "theta_mismatch"
    return True, None


def _self_checks(primitives, process, offsets):
    """Self-intersection / self-overlap / self-spacing at the round-2 clearance."""
    clearance = float(process.get("clearance_mm") or fslw_config.CLEARANCE_MM)
    kernel = _distance_primitives()
    try:
        prepared = kernel.prepare_route(primitives)
        prims = prepared.prims
    except Exception:  # noqa: BLE001 - geometry already counted as invalid
        return {"self_intersections": 0, "self_overlaps": 0,
                "self_spacing_violations": 0, "errors": ["unparsable"]}
    self_intersections = 0
    self_overlaps = 0
    for first_index in range(len(prims)):
        first = prims[first_index]
        for second_index in range(first_index + 1, len(prims)):
            second = prims[second_index]
            try:
                points, overlap = kernel._geometry_intersections(  # noqa: SLF001
                    first.raw, second.raw, 1e-8)
            except Exception:  # noqa: BLE001
                continue
            if overlap:
                self_overlaps += 1
            if second_index == first_index + 1:
                for point in points:
                    if math.hypot(point[0] - first.p1[0],
                                  point[1] - first.p1[1]) > POSE_TOL:
                        self_intersections += 1
                        break
            elif points:
                self_intersections += 1
    self_spacing = 0
    for first_index in range(len(prims)):
        first = prims[first_index]
        for second_index in range(first_index + 2, len(prims)):
            second = prims[second_index]
            if (offsets[second_index]
                    - (offsets[first_index] + first.length)) <= 2.0 * clearance:
                continue
            dx = max(first.bbox[0] - second.bbox[2],
                     second.bbox[0] - first.bbox[2], 0.0)
            dy = max(first.bbox[1] - second.bbox[3],
                     second.bbox[1] - first.bbox[3], 0.0)
            if math.hypot(dx, dy) >= clearance - PAIR_EPS:
                continue
            try:
                distance = kernel._exact_distance(  # noqa: SLF001
                    first, second, bbox_disjoint=(dx > 0.0 or dy > 0.0))
            except Exception:  # noqa: BLE001
                continue
            if distance < clearance - PAIR_EPS and not kernel._prims_intersect(  # noqa: SLF001
                    first, second):
                self_spacing += 1
    return {"self_intersections": self_intersections,
            "self_overlaps": self_overlaps,
            "self_spacing_violations": self_spacing, "errors": []}


def compute_route_geometry(routed, process, endpoints):
    """Recompute per-route length/straightness/detour and single-route checks."""
    radius = float(process.get("radius_mm") or fslw_config.RADIUS_MM)
    width = float(process.get("width_mm") or fslw_config.WIDTH_MM)
    board = process.get("board_mm") or [fslw_config.BOARD_MM] * 2
    board_width, board_height = float(board[0]), float(board[1])
    endpoint_table = endpoints or {}
    per_route = {}
    lengths = []
    horizontal_lengths = []
    vertical_lengths = []
    arc_lengths = []
    straight_fractions = []
    horizontal_fractions = []
    vertical_fractions = []
    arc_fractions = []
    turns = []
    detours = []
    detour_ratios = []
    detours_euclidean = []
    detour_entries = []
    manhattan_bounds = []
    euclidean_bounds = []
    radius_values = Counter()
    reported_length_mismatches = []
    violations = Counter()
    failures = []
    routes_without_geometry = 0
    endpoints_checked = 0
    bounds_violations = 0
    for record in routed:
        primitives = record.get("primitives") or []
        route_id = record.get("route_id")
        if not primitives:
            routes_without_geometry += 1
            continue
        total = geom.length(primitives)
        horizontal = vertical = arc_length = 0.0
        arc_count = 0
        route_errors = []
        offsets = []
        running = 0.0
        for primitive in primitives:
            offsets.append(running)
            try:
                length = geom.length([primitive])
            except Exception:  # noqa: BLE001
                length = 0.0
            running += length
            kind = primitive.get("kind")
            if kind == "line":
                orientation = _line_orientation(primitive)
                if orientation == "horizontal":
                    horizontal += length
                elif orientation == "vertical":
                    vertical += length
                else:
                    violations["diagonal_line"] += 1
                    route_errors.append("diagonal_line")
            elif kind == "arc":
                arc_count += 1
                arc_length += length
                radius_value = _number(primitive.get("radius"))
                radius_values[_round(radius_value, 6)] += 1
                if radius_value is None or abs(radius_value - radius) > RADIUS_TOL:
                    violations["radius"] += 1
                    route_errors.append(f"arc_radius:{radius_value}")
            else:
                violations["invalid_primitive"] += 1
                route_errors.append(f"unknown_kind:{kind}")
        # arc family: quarter arcs or paired short-S arcs (R-generic)
        index = 0
        while index < len(primitives):
            primitive = primitives[index]
            if primitive.get("kind") != "arc":
                index += 1
                continue
            sweep = abs(_number(primitive.get("sweep")) or 0.0)
            if abs(sweep - math.pi / 2.0) <= QUARTER_TOL:
                index += 1
                continue
            other = index + 1
            gap = 0.0
            while other < len(primitives) and primitives[other].get("kind") == "line":
                gap += geom.length([primitives[other]])
                other += 1
            if other < len(primitives) and primitives[other].get("kind") == "arc" \
                    and gap <= POSE_TOL:
                valid, reason = _short_s_pair_valid(primitives[index],
                                                    primitives[other], radius)
                if valid:
                    index = other + 1
                    continue
                violations["free_arc"] += 1
                route_errors.append(f"short_s_pair_invalid:{reason}")
            else:
                violations["free_arc"] += 1
                route_errors.append(f"short_s_unpaired_arc:{sweep:.12g}")
            index += 1
        # continuity and arc parameterisation consistency
        for index in range(1, len(primitives)):
            previous = primitives[index - 1]
            current = primitives[index]
            joint = (current["p0"][0] - previous["p1"][0],
                     current["p0"][1] - previous["p1"][1])
            if math.hypot(*joint) > POSE_TOL:
                violations["position_continuity"] += 1
                route_errors.append(f"position_discontinuity:{index - 1}:{index}")
            tangent_previous = _tangent_at(previous, end=True)
            tangent_current = _tangent_at(current, end=False)
            if tangent_previous and tangent_current:
                if math.hypot(tangent_previous[0] - tangent_current[0],
                              tangent_previous[1] - tangent_current[1]) > POSE_TOL:
                    violations["tangent_continuity"] += 1
                    route_errors.append(f"tangent_discontinuity:{index - 1}:{index}")
        for index, primitive in enumerate(primitives):
            if primitive.get("kind") != "arc":
                continue
            center = primitive.get("center")
            radius_value = _number(primitive.get("radius"))
            start = _number(primitive.get("start_angle"))
            sweep = _number(primitive.get("sweep"))
            if None in (center, radius_value, start, sweep):
                continue
            for key, angle in (("p0", start), ("p1", start + sweep)):
                point = (center[0] + radius_value * math.cos(angle),
                         center[1] + radius_value * math.sin(angle))
                actual = primitive.get(key) or [0.0, 0.0]
                if math.hypot(point[0] - actual[0],
                              point[1] - actual[1]) > POSE_TOL:
                    violations["arc_endpoint"] += 1
                    route_errors.append(f"arc_endpoint_inconsistent:{index}:{key}")
        # layer / z (plane is metadata: inside a plane everything is 2D layer 0)
        for index, primitive in enumerate(primitives):
            if int(primitive.get("layer", 0) or 0) != 0:
                violations["layer"] += 1
                route_errors.append(f"nonzero_layer:{index}")
            try:
                z_value = float(primitive.get("z", 0.0) or 0.0)
            except (TypeError, ValueError):
                z_value = 0.0
            if abs(z_value) > ORTHO_TOL:
                violations["nonzero_z"] += 1
                route_errors.append(f"nonzero_z:{index}")
        # stroked board bounds
        for index, primitive in enumerate(primitives):
            try:
                box = geom.bounds(primitive, width)
            except Exception:  # noqa: BLE001
                continue
            if (box[0] < -BOUNDS_TOL or box[1] < -BOUNDS_TOL
                    or box[2] > board_width + BOUNDS_TOL
                    or box[3] > board_height + BOUNDS_TOL):
                bounds_violations += 1
                violations["boundary"] += 1
                route_errors.append(f"board_out_of_bounds:{index}")
        # fixed ports and in/out directions
        source = endpoint_table.get(record.get("source_endpoint"))
        target = endpoint_table.get(record.get("target_endpoint"))
        if source and target and source.get("routing_xy") and target.get("routing_xy"):
            endpoints_checked += 1
            start_xy = source["routing_xy"]
            end_xy = target["routing_xy"]
            if math.hypot(primitives[0]["p0"][0] - start_xy[0],
                          primitives[0]["p0"][1] - start_xy[1]) > POSE_TOL:
                violations["endpoint"] += 1
                route_errors.append("start_endpoint_mismatch")
            if math.hypot(primitives[-1]["p1"][0] - end_xy[0],
                          primitives[-1]["p1"][1] - end_xy[1]) > POSE_TOL:
                violations["endpoint"] += 1
                route_errors.append("end_endpoint_mismatch")
            inward = source.get("inward")
            if inward:
                tangent = _tangent_at(primitives[0], end=False)
                if tangent and math.hypot(tangent[0] - inward[0],
                                          tangent[1] - inward[1]) > POSE_TOL:
                    violations["io_direction"] += 1
                    route_errors.append("start_direction_mismatch")
            target_inward = target.get("inward")
            if target_inward:
                tangent = _tangent_at(primitives[-1], end=True)
                if tangent and math.hypot(tangent[0] + target_inward[0],
                                          tangent[1] + target_inward[1]) > POSE_TOL:
                    violations["io_direction"] += 1
                    route_errors.append("end_direction_mismatch")
            # route plane must agree with its endpoint plane
            for endpoint, endpoint_name in ((source, "source"),
                                            (target, "target")):
                endpoint_plane = _normalise_plane(endpoint.get("plane"))
                route_plane = _normalise_plane(record.get("plane"))
                if endpoint_plane and route_plane and endpoint_plane != route_plane:
                    violations["plane_consistency"] += 1
                    route_errors.append(f"{endpoint_name}_plane_mismatch")
        # self checks
        self_metrics = _self_checks(primitives, process, offsets)
        violations["self_intersection"] += self_metrics["self_intersections"]
        violations["self_overlap"] += self_metrics["self_overlaps"]
        violations["self_spacing"] += self_metrics["self_spacing_violations"]
        reported = _number(record.get("length_mm"))
        if reported is not None and abs(reported - total) > 1e-6:
            reported_length_mismatches.append(
                {"route_id": route_id, "recomputed_mm": total,
                 "reported_mm": reported, "abs_diff_mm": abs(reported - total)})
        manhattan = None
        euclidean = None
        if source and target and source.get("routing_xy") and target.get("routing_xy"):
            manhattan = abs(target["routing_xy"][0] - source["routing_xy"][0]) \
                + abs(target["routing_xy"][1] - source["routing_xy"][1])
            euclidean = math.hypot(target["routing_xy"][0] - source["routing_xy"][0],
                                   target["routing_xy"][1] - source["routing_xy"][1])
            manhattan_bounds.append(manhattan)
            detour = total - manhattan
            detours.append(detour)
            detour_entries.append((route_id, detour, total - euclidean))
            if manhattan > 0:
                detour_ratios.append(detour / manhattan)
            detours_euclidean.append(total - euclidean)
            euclidean_bounds.append(euclidean)
        route_entry = {
            "length_mm": total,
            "horizontal_length_mm": horizontal,
            "vertical_length_mm": vertical,
            "arc_length_mm": arc_length,
            "line_count": sum(1 for p in primitives
                              if p.get("kind") == "line"),
            "arc_count": arc_count,
            "straight_fraction": (horizontal + vertical) / total if total > 0 else None,
            "horizontal_straight_fraction": horizontal / total if total > 0 else None,
            "vertical_straight_fraction": vertical / total if total > 0 else None,
            "arc_fraction": arc_length / total if total > 0 else None,
            "manhattan_lower_bound_mm": manhattan,
            "euclidean_lower_bound_mm": euclidean,
            "unnecessary_detour_mm": (total - manhattan)
            if manhattan is not None else None,
            "unnecessary_detour_vs_euclidean_mm": (total - euclidean)
            if euclidean is not None else None,
            "endpoint_checked": bool(source and target),
            "errors": route_errors,
        }
        per_route[route_id] = route_entry
        if route_errors:
            failures.append({"route_id": route_id,
                             "errors": route_errors[:8]})
        lengths.append(total)
        horizontal_lengths.append(horizontal)
        vertical_lengths.append(vertical)
        arc_lengths.append(arc_length)
        turns.append(arc_count)
        if total > 0:
            straight_fractions.append((horizontal + vertical) / total)
            horizontal_fractions.append(horizontal / total)
            vertical_fractions.append(vertical / total)
            arc_fractions.append(arc_length / total)
    total_length = sum(lengths)
    total_horizontal = sum(horizontal_lengths)
    total_vertical = sum(vertical_lengths)
    total_arc = sum(arc_lengths)
    violations_dict = {
        "radius_violations": int(violations["radius"]),
        "boundary_violations": int(violations["boundary"]),
        "diagonal_line_violations": int(violations["diagonal_line"]),
        "free_arc_violations": int(violations["free_arc"]),
        "self_intersections": int(violations["self_intersection"]),
        "self_overlaps": int(violations["self_overlap"]),
        "self_spacing_violations": int(violations["self_spacing"]),
        "layer_violations": int(violations["layer"]),
        "nonzero_z_violations": int(violations["nonzero_z"]),
        "endpoint_violations": int(violations["endpoint"]),
        "io_direction_violations": int(violations["io_direction"]),
        "continuity_violations": int(violations["position_continuity"]
                                     + violations["tangent_continuity"]),
        "arc_endpoint_violations": int(violations["arc_endpoint"]),
        "invalid_primitive_violations": int(violations["invalid_primitive"]),
        "plane_consistency_violations": int(violations["plane_consistency"]),
        "routes_with_geometry_errors": len(failures),
        "route_errors": failures[:50],
        "geometry_total_routes": len(per_route),
        "routes_without_geometry": routes_without_geometry,
        "endpoints_checked": endpoints_checked,
        "reported_length_mismatch_count": len(reported_length_mismatches),
        "reported_length_mismatches": reported_length_mismatches[:20],
    }
    violations_dict["total_violation_count"] = int(sum(
        violations_dict[key] for key in (
            "radius_violations", "boundary_violations",
            "diagonal_line_violations", "free_arc_violations",
            "self_intersections", "self_overlaps", "self_spacing_violations",
            "layer_violations", "nonzero_z_violations", "endpoint_violations",
            "io_direction_violations", "continuity_violations",
            "arc_endpoint_violations", "invalid_primitive_violations",
            "plane_consistency_violations")))
    geometry = {
        "per_route": per_route,
        "mean_length_mm": _mean(lengths),
        "max_length_mm": max(lengths) if lengths else None,
        "min_length_mm": min(lengths) if lengths else None,
        "total_length_mm": total_length,
        "total_horizontal_line_length_mm": total_horizontal,
        "total_vertical_line_length_mm": total_vertical,
        "total_arc_length_mm": total_arc,
        "mean_straight_fraction": _mean(straight_fractions),
        "mean_horizontal_straight_fraction": _mean(horizontal_fractions),
        "mean_vertical_straight_fraction": _mean(vertical_fractions),
        "mean_arc_fraction": _mean(arc_fractions),
        "mean_bend_count": _mean(turns),
        "max_bend_count": max(turns) if turns else None,
        "total_bends": int(sum(turns)),
        "mean_turns": _mean(turns),
        "mean_unnecessary_detour_mm": _mean(detours),
        "max_unnecessary_detour_mm": max(detours) if detours else None,
        "total_unnecessary_detour_mm": sum(detours),
        "mean_unnecessary_detour_ratio": _mean(detour_ratios),
        "mean_unnecessary_detour_vs_euclidean_mm": _mean(detours_euclidean),
        "min_unnecessary_detour_vs_euclidean_mm": (min(detours_euclidean)
                                                  if detours_euclidean else None),
        "max_unnecessary_detour_vs_euclidean_mm": (max(detours_euclidean)
                                                  if detours_euclidean else None),
        "total_unnecessary_detour_vs_euclidean_mm": sum(detours_euclidean),
        "total_manhattan_lower_bound_mm": sum(manhattan_bounds),
        "total_euclidean_lower_bound_mm": sum(euclidean_bounds),
        "detour_measured_routes": len(detours),
        "routes_below_manhattan_bound": [
            {"route_id": route_id, "detour_vs_manhattan_mm": _round(detour, 6),
             "detour_vs_euclidean_mm": _round(euclidean_detour, 6)}
            for route_id, detour, euclidean_detour in detour_entries
            if detour < -1e-6][:20],
        "routes_below_manhattan_bound_count": sum(
            1 for _, detour, _ in detour_entries if detour < -1e-6),
        "detour_note": (
            "SPEC §6 defines the unnecessary detour against the same-endpoint "
            "Manhattan lower bound.  A 90-degree arc can be shorter than the L1 "
            "bound (arc length R*pi/2 < 2R for the same displacement), so this "
            "quantity may be slightly negative for arc-routed connections; it is "
            "reported as defined and NOT treated as an error.  The additional "
            "unnecessary_detour_vs_euclidean_mm is always >= 0 and is the true "
            "geometric detour length."),
        "arc_radius_values": {str(key): int(value)
                              for key, value in sorted(radius_values.items())},
        "min_arc_radius_mm": min((v for v in radius_values if v is not None),
                                 default=None),
        "num_arcs_total": int(sum(radius_values.values())),
        "violations": violations_dict,
        "radius_violations": violations_dict["radius_violations"],
        "boundary_violations": violations_dict["boundary_violations"],
        "diagonal_line_violations": violations_dict["diagonal_line_violations"],
        "free_arc_violations": violations_dict["free_arc_violations"],
        "self_intersections": violations_dict["self_intersections"],
        "self_overlaps": violations_dict["self_overlaps"],
        "self_spacing_violations": violations_dict["self_spacing_violations"],
        "total_violation_count": violations_dict["total_violation_count"],
        "endpoints_checked": endpoints_checked,
    }
    return geometry


# ---------------------------------------------------------------------------
# propagation loss (SPEC §6/§7): only propagation is computable
# ---------------------------------------------------------------------------
def compute_propagation_loss(lengths_mm, process):
    """Compute ``Lprop_dB = loss_db_per_cm * length_cm`` from analytic lengths."""
    loss_per_cm = float(process.get("propagation_loss_db_per_cm")
                        or fslw_config.PROPAGATION_LOSS_DB_PER_CM)
    lengths_mm = [float(value) for value in lengths_mm if value is not None]
    per_route = [loss_per_cm * (length / 10.0) for length in lengths_mm]
    if not per_route:
        return {
            "formula": "Lprop_dB = propagation_loss_db_per_cm * length_cm",
            "propagation_loss_db_per_cm": loss_per_cm,
            "per_route_db": {},
            "mean_db": None, "max_db": None, "min_db": None, "total_db": None,
            "total_length_cm": None, "histogram": {}, "percentiles": {},
            "status": "no_routed_routes",
        }
    hist_min = 0.0
    hist_max = max(per_route)
    bin_width = 0.1 if hist_max <= 3.0 else 0.25
    bin_count = max(1, int(math.ceil(hist_max / bin_width)))
    edges = [round(index * bin_width, 6) for index in range(bin_count + 1)]
    histogram = OrderedDict()
    for index in range(bin_count):
        low, high = edges[index], edges[index + 1]
        label = f"{low:.2f}-{high:.2f}"
        histogram[label] = sum(1 for value in per_route if low <= value < high
                               or (index == bin_count - 1 and value == high))
    return {
        "formula": "Lprop_dB = propagation_loss_db_per_cm * length_cm",
        "propagation_loss_db_per_cm": loss_per_cm,
        "per_route_db": {},
        "mean_db": _mean(per_route),
        "max_db": max(per_route),
        "min_db": min(per_route),
        "total_db": sum(per_route),
        "total_length_cm": sum(lengths_mm) / 10.0,
        "histogram_bin_width_db": bin_width,
        "histogram": dict(histogram),
        "percentiles": _percentiles(per_route),
        "status": "computed_from_analytic_lengths",
    }


def compute_loss_breakdown(lengths_mm, process):
    """Propagation known; bend/crossing loss explicitly unknown (never invented)."""
    propagation = compute_propagation_loss(lengths_mm, process)
    bend = dict(getattr(fslw_config, "BEND_LOSS", None)
                or {"status": "unknown_uncalibrated"})
    crossing = dict(getattr(fslw_config, "CROSSING_LOSS", None)
                    or {"status": "unknown_uncalibrated"})
    legacy = dict(getattr(fslw_config, "LEGACY_POLYMER_ESTIMATE", None)
                  or {"available": False})
    propagation_block = {
        "status": "computed",
        "value_db": propagation.get("total_db"),
        "mean_db": propagation.get("mean_db"),
        "max_db": propagation.get("max_db"),
        "min_db": propagation.get("min_db"),
        "formula": propagation.get("formula"),
        "db_per_cm": propagation.get("propagation_loss_db_per_cm"),
        "total_length_cm": propagation.get("total_length_cm"),
    }
    return {
        "propagation_loss": propagation_block,
        "bend_loss": dict(bend, value_db=None),
        "crossing_loss": dict(crossing, value_db=None, crossing_count=None),
        "total_optical_loss": {
            "status": "not_computable_missing_calibration",
            "value_db": None,
            "components_known": ["propagation"],
            "components_unknown": ["bend", "crossing"],
            "note": "total optical loss cannot be reported until glass bend loss "
                    "and crossing loss are calibrated; propagation loss alone is "
                    "reported explicitly",
        },
        "legacy_arm": {
            "included": False,
            "legacy_polymer_estimate": legacy,
            "status": "legacy_estimate_omitted",
            "note": "the legacy polymer bend-loss model is NOT presented as glass "
                    "truth and no legacy numbers are embedded here",
        },
        "dispersion_penalty": None,
        "other_losses_note": "no other loss terms are modelled",
    }


# ---------------------------------------------------------------------------
# quality: density / port regions / congestion hotspots
# ---------------------------------------------------------------------------
def _sample_polyline(primitives, sagitta):
    try:
        return np.asarray(geom.sample(primitives, sagitta), dtype=float)
    except Exception:  # noqa: BLE001
        return np.empty((0, 2))


def _segment_band_length(points, side, band, board):
    """Length of a polyline inside the edge band on ``side``."""
    if len(points) < 2:
        return 0.0
    board_x, board_y = board
    if side == "N":
        lo, hi = board_y - band, board_y
        axis, index = "y", 1
    elif side == "S":
        lo, hi = 0.0, band
        axis, index = "y", 1
    elif side == "E":
        lo, hi = board_x - band, board_x
        axis, index = "x", 0
    else:  # W
        lo, hi = 0.0, band
        axis, index = "x", 0
    total = 0.0
    for first, second in zip(points[:-1], points[1:]):
        a = float(first[index])
        b = float(second[index])
        if a > hi and b > hi:
            continue
        if a < lo and b < lo:
            continue
        if a == b:
            if lo <= a <= hi:
                total += float(np.linalg.norm(second - first))
            continue
        t0 = (lo - a) / (b - a)
        t1 = (hi - a) / (b - a)
        t_low, t_high = min(t0, t1), max(t0, t1)
        t_low = max(0.0, t_low)
        t_high = min(1.0, t_high)
        if t_high > t_low:
            total += (t_high - t_low) * float(np.linalg.norm(second - first))
    return total


def compute_quality(routed, process, endpoints, crossings):
    board = process.get("board_mm") or [fslw_config.BOARD_MM] * 2
    board_x, board_y = float(board[0]), float(board[1])
    cells = GRID_MM
    grid_x = max(1, int(math.ceil(board_x / cells)))
    grid_y = max(1, int(math.ceil(board_y / cells)))
    density = np.zeros((grid_x, grid_y), dtype=float)
    port_band = {side: 0.0 for side in "NESW"}
    curves = {}
    total_length = 0.0
    for record in routed:
        primitives = record.get("primitives") or []
        if not primitives:
            continue
        points = _sample_polyline(primitives, 0.01)
        if len(points) < 2:
            continue
        curves[record.get("route_id")] = points
        for side in "NESW":
            port_band[side] += _segment_band_length(points, side, PORT_BAND_MM,
                                                    (board_x, board_y))
        for first, second in zip(points[:-1], points[1:]):
            segment = second - first
            length = float(np.linalg.norm(segment))
            if length <= 0.0:
                continue
            total_length += length
            steps = max(1, int(math.ceil(length / ROUTING_DENSITY_SAMPLE_MM)))
            share = length / steps
            for step in range(steps):
                t = (step + 0.5) / steps
                px = first[0] + t * segment[0]
                py = first[1] + t * segment[1]
                ix = min(grid_x - 1, max(0, int(math.floor(px / cells))))
                iy = min(grid_y - 1, max(0, int(math.floor(py / cells))))
                density[ix, iy] += share
    density_pairs = []
    for ix in range(grid_x):
        for iy in range(grid_y):
            if density[ix, iy] > 0:
                density_pairs.append((float(density[ix, iy]),
                                      ix, iy))
    density_pairs.sort(reverse=True)
    top_density = [{"x_min_mm": ix * cells, "y_min_mm": iy * cells,
                    "length_mm": round(value, 3)}
                   for value, ix, iy in density_pairs[:10]]
    peak = density_pairs[0][0] if density_pairs else 0.0
    peak_cell = ([density_pairs[0][1] * cells, density_pairs[0][2] * cells]
                 if density_pairs else None)
    # per-side / per-connector port usage (routed endpoints only)
    side_stats = {side: {"ports_total": 0, "routed_endpoints": 0,
                         "routed_routes_touching": 0,
                         "port_band_length_mm": round(port_band[side], 3)}
                  for side in "NESW"}
    connector_counts = Counter()
    routed_endpoint_ids = set()
    for record in routed:
        for endpoint_id in (record.get("source_endpoint"),
                            record.get("target_endpoint")):
            if not endpoint_id:
                continue
            routed_endpoint_ids.add(endpoint_id)
            endpoint = (endpoints or {}).get(endpoint_id) or {}
            side = endpoint.get("side") or endpoint_id[0]
            connector = endpoint.get("connector") or endpoint_id.split(":")[0]
            if side in side_stats:
                side_stats[side]["routed_endpoints"] += 1
            connector_counts[connector] += 1
    for endpoint_id in routed_endpoint_ids:
        endpoint = (endpoints or {}).get(endpoint_id) or {}
        side = endpoint.get("side") or endpoint_id[0]
        if side in side_stats:
            side_stats[side]["routed_routes_touching"] += 1
    for side in "NESW":
        side_stats[side]["ports_total"] = 256
        side_stats[side]["routed_endpoint_fraction"] = (
            side_stats[side]["routed_endpoints"] / 256.0)
        side_stats[side]["port_band_density_mm_per_mm2"] = (
            port_band[side] / (band_area(side, board_x, board_y, PORT_BAND_MM))
            if band_area(side, board_x, board_y, PORT_BAND_MM) else None)
    connector_values = list(connector_counts.values())
    connectors_sorted = connector_counts.most_common(10)
    port_region = {
        "band_mm": PORT_BAND_MM,
        "by_side": side_stats,
        "connector_endpoint_counts": dict(sorted(connector_counts.items())),
        "connector_hotspots": [{"connector": connector, "routed_endpoints": count}
                               for connector, count in connectors_sorted],
        "connector_endpoint_count_min": min(connector_values)
        if connector_values else None,
        "connector_endpoint_count_mean": _mean(connector_values),
        "connector_endpoint_count_max": max(connector_values)
        if connector_values else None,
        "definition": ("ports_total = 4 sides x 16 connectors x 16 columns = 256 per "
                       "side; routed_endpoints counts routed route endpoints per side; "
                       "port_band_length_mm is the centreline length inside the 5 mm "
                       "band along each edge"),
    }
    crossing_count = len(crossings or [])
    return {
        "route_length_density": {
            "grid_mm": cells,
            "total_length_mm": total_length,
            "peak_cell_mm": peak,
            "peak_cell": peak_cell,
            "top_cells": top_density,
            "definition": "sampled centreline length per 5 x 5 mm cell (mm per cell)",
        },
        "route_length_grid_peak_mm": peak,
        "route_length_grid_peak_cell": peak_cell,
        "top_density_cells": top_density,
        "congestion_hotspots": top_density[:5],
        "crossing_count_density_per_mm2": (
            crossing_count / (board_x * board_y)),
        "port_region": port_region,
        "port_region_length_mm": {side: round(port_band[side], 3)
                                  for side in "NESW"},
        "sampled_curves": curves,
    }


def band_area(side, board_x, board_y, band):
    return board_x * band if side in ("N", "S") else board_y * band


# ---------------------------------------------------------------------------
# symmetry (per plane; reuses abcd/connectivity semantics on the plane subset)
# ---------------------------------------------------------------------------
def compute_symmetry(records, endpoints, process):
    if not endpoints:
        return {"available": False,
                "reason": "plane endpoint table unavailable (ports.py missing)",
                "source": None}
    transforms = OrderedDict()
    for name, (matrix, offset) in abcd_metrics.FALLBACK_TRANSFORMS.items():
        entry = {"name": name,
                 "matrix": [list(matrix[0]), list(matrix[1])],
                 "offset": list(offset)}
        try:
            entry.update(abcd_metrics._build_route_map(  # noqa: SLF001
                records, endpoints, matrix, offset))
        except Exception as exc:  # noqa: BLE001 - report, never guess
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["route_map"] = {}
        transforms[name] = entry
    records_by_id = {record.get("route_id"): record for record in records}
    routed_ids = {record.get("route_id") for record in records
                  if _status(record) == "routed"}
    spec_names = ("rot90", "rot180", "mirror_x", "mirror_y", "diag")
    spec = OrderedDict()
    for name in spec_names:
        transform = transforms.get(name) or transforms.get(
            "diag_main" if name == "diag" else name)
        if transform is None:
            continue
        route_map = transform.get("route_map") or {}
        pairs = set()
        for key, value in route_map.items():
            if value is None:
                continue
            pairs.add((min(key, value), max(key, value)))
        routed_pairs = 0
        shape_matches = 0
        shape_checked = 0
        for first, second in sorted(pairs):
            if first not in routed_ids or second not in routed_ids:
                continue
            routed_pairs += 1
            primitives_a = (records_by_id.get(first) or {}).get("primitives") or []
            primitives_b = (records_by_id.get(second) or {}).get("primitives") or []
            if first == second:
                primitives_b = primitives_a
            if not primitives_a or not primitives_b:
                continue
            shape_checked += 1
            try:
                deviation = abcd_metrics._shape_deviation(  # noqa: SLF001
                    primitives_a, primitives_b, transform["matrix"],
                    transform["offset"])
            except Exception:  # noqa: BLE001
                continue
            if deviation <= abcd_metrics.SHAPE_MATCH_MM:
                shape_matches += 1
        spec[name] = {
            "transform": name,
            "source_name": transform.get("name"),
            "matrix": transform.get("matrix"),
            "offset": transform.get("offset"),
            "pair_count": len(pairs),
            "routed_pair_count": routed_pairs,
            "routed_pair_fraction": (routed_pairs / len(pairs)) if pairs else None,
            "shape_checked_pair_count": shape_checked,
            "shape_match_count": shape_matches,
            "shape_match_fraction": (shape_matches / shape_checked)
            if shape_checked else None,
            "mapped_route_count": transform.get("mapped_route_count"),
            "route_map_complete": transform.get("route_map_complete"),
            "fixed_point_count": transform.get("fixed_point_count"),
            "orientation_counts": transform.get("orientation_counts"),
            "definition": {
                "routed_pair_fraction": "fraction of topology counterpart pairs "
                                        "(unordered, fixed points included) with "
                                        "both routes routed in this plane",
                "shape_match_fraction": "both-routed pairs whose transformed path "
                                        "agrees primitive-wise within 0.05 mm",
            },
        }
    result = OrderedDict()
    result["available"] = bool(spec)
    result["source"] = ("four_side_1024.abcd.connectivity.symmetry_maps semantics "
                        "(local plane kernel; abcd.metrics transform helpers)")
    result["shape_match_threshold_mm"] = abcd_metrics.SHAPE_MATCH_MM
    result["spec_transform_names"] = list(spec_names)
    result["n_routes"] = len(records)
    result["n_endpoints"] = len(endpoints)
    result["note"] = ("per-plane subset: row1->z1 (opposite) / row2->z2 (adjacent); "
                      "endpoint-level symmetry is a topology property, structurally "
                      "limited on V1 and only partially complete on V2 - this is not "
                      "a routing defect")
    for name, metric in spec.items():
        result[name] = metric
    result["all_transforms"] = OrderedDict(
        (name, {key: value for key, value in entry.items() if key != "route_map"})
        for name, entry in transforms.items())
    return result


# ---------------------------------------------------------------------------
# run metadata
# ---------------------------------------------------------------------------
def _extract_run_metadata(routes_meta, config_payload, run_dir):
    return abcd_metrics._extract_run_metadata(  # noqa: SLF001
        routes_meta, config_payload, run_dir, [], [])


# ---------------------------------------------------------------------------
# plane statistics assembly
# ---------------------------------------------------------------------------
def _resolve_paths(run_dir):
    run_dir = Path(run_dir)
    routes_path = run_dir / "routes.json"
    if not routes_path.exists():
        raise FileNotFoundError(f"no routes.json under {run_dir}")
    config_path = run_dir / "config.json"
    return routes_path, config_path


def build_plane_statistics(run_dir, out_path=None, audit_path=None,
                           config_path=None, skip_pair_audit=False,
                           skip_min_gaps=False, skip_symmetry=False,
                           skip_quality=False, quiet=False):
    """Recompute the full plane statistic set and write ``statistics.json``."""
    started = time.perf_counter()
    run_dir = Path(run_dir)
    routes_path, default_config = _resolve_paths(run_dir)
    if config_path is None:
        config_path = default_config if default_config.exists() else None
    else:
        config_path = Path(config_path)
    if out_path is None:
        out_path = run_dir / "statistics.json"
    else:
        out_path = Path(out_path)
    payload, meta, records, routed, failed = load_routes(routes_path)
    config_payload = _load_json(config_path) if config_path else None
    process = load_process(meta, config_payload, run_dir)
    plane = process.get("plane") or _records_plane(records, meta)
    process["plane"] = plane
    if process.get("z_mm") is None:
        process["z_mm"] = PLANE_Z.get(plane)
    plane_row = process.get("plane_row") or {}
    plane_row = plane_row.get(plane) if isinstance(plane_row, dict) else None
    plane_row = plane_row or PLANE_ROWS.get(plane)

    topology = process.get("topology") or _first(meta, ("topology",))
    algorithm = process.get("algorithm") or _first(meta, ("algorithm",))
    port_bundle = load_plane_ports(topology, plane, process) if topology else None
    endpoints = (port_bundle or {}).get("endpoints")
    derived = False
    if not endpoints:
        endpoints = _derive_endpoints(routed, process)
        derived = True
    connectors = (port_bundle or {}).get("connectors") or []

    by_pair = OrderedDict()
    pair_total = Counter()
    pair_routed = Counter()
    for record in records:
        pair = _pair_of(record)
        if pair in PAIR_RELATION:
            pair_total[pair] += 1
            if _status(record) == "routed":
                pair_routed[pair] += 1
    for pair in PAIR_ORDER:
        if pair not in pair_total:
            continue
        total = pair_total[pair]
        success = pair_routed[pair]
        by_pair[pair] = {"relation": PAIR_RELATION[pair], "success": success,
                         "routed": success, "failed": total - success,
                         "total": total,
                         "routing_rate": (success / total) if total else None}
    by_relation = OrderedDict()
    for relation, pairs in RELATION_PAIRS.items():
        totals = [pair_total[pair] for pair in pairs if pair in pair_total]
        if not totals:
            continue
        total = sum(totals)
        success = sum(pair_routed[pair] for pair in pairs)
        by_relation[relation] = {"pairs": list(pairs), "success": success,
                                 "routed": success, "failed": total - success,
                                 "total": total,
                                 "routing_rate": (success / total) if total else None}
    routed_count = len(routed)
    unrouted_count = len(failed)
    total_connections = int(process.get("connections_per_plane")
                            or CONNECTIONS_PER_PLANE)
    expected_pair_counts = {"NS": 256, "EW": 256, "EN": 128, "ES": 128,
                            "SW": 128, "NW": 128}
    pair_count_check = {pair: {"expected": expected_pair_counts[pair],
                               "actual": pair_total.get(pair, 0),
                               "matches": pair_total.get(pair, 0)
                               == expected_pair_counts[pair]}
                        for pair in PAIR_ORDER
                        if pair in pair_total}
    failure_reasons = Counter(str(record.get("reason") or "unknown_failure")
                              for record in failed)

    geometry = compute_route_geometry(routed, process, endpoints)
    pair_audit = None if skip_pair_audit else compute_pair_audit(routed, process)
    audit_report, audit_meta = load_audit(routes_path, audit_path)
    audit_values = (audit_report or {}).get("values", {}) if audit_report else {}
    violation_fields = ("spacing_violation_pairs", "overlap_pairs", "touch_pairs",
                        "crossing_window_overlap_pairs", "double_cross_pairs",
                        "crossing_window_excessive_pairs", "violation_pair_count",
                        "crossing_count", "crossing_angle_histogram",
                        "small_angle_crossing_count", "self_intersections",
                        "self_overlaps", "self_spacing_violations",
                        "radius_violations", "boundary_violations",
                        "diagonal_line_violations", "free_arc_violations")
    recomputed = {
        "crossing_count": pair_audit["crossing_count"] if pair_audit else None,
        "crossing_angle_histogram": (pair_audit["crossing_angle_histogram"]
                                     if pair_audit else None),
        "small_angle_crossing_count": (pair_audit["small_angle_crossing_count"]
                                       if pair_audit else None),
        "spacing_violation_pairs": (pair_audit["spacing_violation_pairs"]
                                    if pair_audit else None),
        "overlap_pairs": pair_audit["overlap_pairs"] if pair_audit else None,
        "touch_pairs": pair_audit["touch_pairs"] if pair_audit else None,
        "crossing_window_overlap_pairs": (
            pair_audit["crossing_window_overlap_pairs"] if pair_audit else None),
        "double_cross_pairs": (pair_audit["double_cross_pairs"]
                               if pair_audit else None),
        "crossing_window_excessive_pairs": (
            pair_audit["crossing_window_excessive_pairs"] if pair_audit else None),
        "violation_pair_count": (pair_audit["violation_pair_count"]
                                 if pair_audit else None),
        "self_intersections": geometry["self_intersections"],
        "self_overlaps": geometry["self_overlaps"],
        "self_spacing_violations": geometry["self_spacing_violations"],
        "radius_violations": geometry["radius_violations"],
        "boundary_violations": geometry["boundary_violations"],
        "diagonal_line_violations": geometry["diagonal_line_violations"],
        "free_arc_violations": geometry["free_arc_violations"],
    }
    merged = OrderedDict()
    sources = OrderedDict()
    for field in violation_fields:
        if field in audit_values and audit_values[field] is not None:
            merged[field] = audit_values[field]
            sources[field] = f"{audit_report['label']}:{audit_report['file']}"
        else:
            merged[field] = recomputed.get(field)
            sources[field] = ("recomputed_from_primitives" if recomputed.get(field)
                              is not None else None)
    # authoritative crossing count falls back to the recomputation
    crossing_count = merged.get("crossing_count")
    if crossing_count is None:
        crossing_count = recomputed.get("crossing_count")
        sources["crossing_count"] = "recomputed_from_primitives"

    gaps = None if skip_min_gaps else compute_min_gaps(routed, process)
    if skip_quality:
        quality = {
            "route_length_density": {"grid_mm": GRID_MM,
                                     "total_length_mm": None,
                                     "peak_cell_mm": None,
                                     "peak_cell": None, "top_cells": []},
            "route_length_grid_peak_mm": None,
            "route_length_grid_peak_cell": None,
            "top_density_cells": [],
            "congestion_hotspots": [],
            "crossing_count_density_per_mm2": None,
            "port_region": {"band_mm": PORT_BAND_MM,
                            "note": "skipped by caller"},
            "port_region_length_mm": {side: None for side in "NESW"},
            "sampled_curves": {},
        }
    else:
        quality = compute_quality(routed, process, endpoints,
                                  (pair_audit or {}).get("crossings") or [])
    lengths = [entry["length_mm"] for entry in geometry["per_route"].values()]
    loss_breakdown = compute_loss_breakdown(lengths, process)
    propagation_detail = compute_propagation_loss(lengths, process)
    propagation_block = dict(propagation_detail)
    propagation_block["value_db"] = propagation_detail.get("total_db")
    propagation_block["db_per_cm"] = propagation_detail.get(
        "propagation_loss_db_per_cm")
    propagation_block["optical_loss_scope"] = (
        "propagation-only; bend loss and crossing loss are unknown_uncalibrated")
    symmetry = None if skip_symmetry else compute_symmetry(records, endpoints,
                                                           process)
    run_metadata = _extract_run_metadata(meta, config_payload, run_dir)
    crossing_pair_count = (audit_report or {}).get("crossing_pair_count")
    if crossing_pair_count is None and pair_audit is not None:
        crossing_pair_count = pair_audit["crossing_pair_count"]
    crossings_list = (pair_audit or {}).get("crossings") or []
    crossing_points = [{"x_mm": float(item["x"]), "y_mm": float(item["y"]),
                        "angle_deg": item.get("angle_deg"),
                        "route_a": item.get("route_a"),
                        "route_b": item.get("route_b")}
                       for item in crossings_list]
    violation_total = 0
    violation_complete = True
    for field in ("spacing_violation_pairs", "overlap_pairs", "touch_pairs",
                  "crossing_window_overlap_pairs", "double_cross_pairs",
                  "crossing_window_excessive_pairs", "self_intersections",
                  "self_overlaps", "self_spacing_violations",
                  "radius_violations", "boundary_violations",
                  "diagonal_line_violations", "free_arc_violations"):
        value = merged.get(field)
        if value is None:
            violation_complete = False
        else:
            violation_total += int(value)
    board_x, board_y = [float(v) for v in (process.get("board_mm")
                                           or [fslw_config.BOARD_MM] * 2)]
    statistics = OrderedDict()
    statistics["schema"] = SCHEMA_PLANE
    statistics["scope"] = "plane"
    statistics["tool"] = TOOL
    statistics["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    statistics["experiment"] = process.get("experiment") or run_dir.name
    statistics["topology"] = topology
    statistics["algorithm"] = algorithm
    statistics["plane"] = plane
    statistics["plane_row"] = plane_row
    statistics["z_mm"] = process.get("z_mm")
    statistics["port_model"] = process.get("port_model")
    statistics["process"] = _json_safe(process)
    statistics["board_mm"] = [board_x, board_y]
    statistics["layer"] = 0
    statistics["source"] = {
        "routes_json": str(routes_path),
        "routes_sha256": _sha256(routes_path),
        "routes_schema": meta.get("schema"),
        "config_json": str(config_path) if config_path else None,
        "endpoint_source": (port_bundle or {}).get("source")
        or ("derived_from_routed_primitives" if derived else None),
        "endpoint_error": (port_bundle or {}).get("error"),
        "connector_count": len(connectors),
        "audit": audit_meta,
        "audit_sha256": (audit_report or {}).get("sha256"),
    }
    statistics["connections_total"] = total_connections
    statistics["connections_in_file"] = len(records)
    statistics["routed"] = routed_count
    statistics["unrouted"] = unrouted_count
    statistics["routing_rate"] = (routed_count / total_connections)
    statistics["success_count"] = routed_count
    statistics["failed_count"] = unrouted_count
    statistics["by_pair"] = by_pair
    statistics["by_relation"] = by_relation
    statistics["pair_count_check"] = pair_count_check
    statistics["failure_reason_counts"] = dict(sorted(failure_reasons.items()))
    statistics["failed_route_ids"] = sorted(record.get("route_id")
                                            for record in failed)
    statistics["length"] = {
        "mean_length_mm": geometry["mean_length_mm"],
        "max_length_mm": geometry["max_length_mm"],
        "min_length_mm": geometry["min_length_mm"],
        "total_length_mm": geometry["total_length_mm"],
        "total_horizontal_line_length_mm": geometry[
            "total_horizontal_line_length_mm"],
        "total_vertical_line_length_mm": geometry["total_vertical_line_length_mm"],
        "total_arc_length_mm": geometry["total_arc_length_mm"],
    }
    statistics["mean_length_mm"] = geometry["mean_length_mm"]
    statistics["max_length_mm"] = geometry["max_length_mm"]
    statistics["min_length_mm"] = geometry["min_length_mm"]
    statistics["total_length_mm"] = geometry["total_length_mm"]
    statistics["mean_bend_count"] = geometry["mean_bend_count"]
    statistics["max_bend_count"] = geometry["max_bend_count"]
    statistics["total_bends"] = geometry["total_bends"]
    statistics["mean_turns"] = geometry["mean_turns"]
    statistics["mean_straight_fraction"] = geometry["mean_straight_fraction"]
    statistics["horizontal_straight_fraction"] = (
        geometry["total_horizontal_line_length_mm"]
        / geometry["total_length_mm"]) if geometry["total_length_mm"] else None
    statistics["vertical_straight_fraction"] = (
        geometry["total_vertical_line_length_mm"]
        / geometry["total_length_mm"]) if geometry["total_length_mm"] else None
    statistics["mean_horizontal_straight_fraction"] = geometry[
        "mean_horizontal_straight_fraction"]
    statistics["mean_vertical_straight_fraction"] = geometry[
        "mean_vertical_straight_fraction"]
    statistics["mean_arc_fraction"] = geometry["mean_arc_fraction"]
    statistics["mean_unnecessary_detour_mm"] = geometry[
        "mean_unnecessary_detour_mm"]
    statistics["max_unnecessary_detour_mm"] = geometry[
        "max_unnecessary_detour_mm"]
    statistics["total_unnecessary_detour_mm"] = geometry[
        "total_unnecessary_detour_mm"]
    statistics["mean_unnecessary_detour_ratio"] = geometry[
        "mean_unnecessary_detour_ratio"]
    statistics["mean_unnecessary_detour_vs_euclidean_mm"] = geometry[
        "mean_unnecessary_detour_vs_euclidean_mm"]
    statistics["min_unnecessary_detour_vs_euclidean_mm"] = geometry[
        "min_unnecessary_detour_vs_euclidean_mm"]
    statistics["max_unnecessary_detour_vs_euclidean_mm"] = geometry[
        "max_unnecessary_detour_vs_euclidean_mm"]
    statistics["total_unnecessary_detour_vs_euclidean_mm"] = geometry[
        "total_unnecessary_detour_vs_euclidean_mm"]
    statistics["routes_below_manhattan_bound_count"] = geometry[
        "routes_below_manhattan_bound_count"]
    statistics["detour_definition"] = geometry["detour_note"]
    statistics["total_manhattan_lower_bound_mm"] = geometry[
        "total_manhattan_lower_bound_mm"]
    statistics["crossing_count"] = crossing_count
    statistics["crossing_count_source"] = sources.get("crossing_count")
    statistics["crossing_count_recomputed"] = recomputed.get("crossing_count")
    statistics["crossing_pair_count"] = crossing_pair_count
    statistics["crossing_count_density_per_mm2"] = (
        (crossing_count / (board_x * board_y))
        if crossing_count is not None and board_x and board_y else None)
    statistics["crossing_angle_histogram"] = merged.get(
        "crossing_angle_histogram") or recomputed.get("crossing_angle_histogram")
    statistics["crossing_histogram_bins_deg"] = [label for label, _, _ in _HIST_BINS]
    statistics["small_angle_threshold_deg"] = 10.0
    statistics["small_angle_crossing_count"] = merged.get(
        "small_angle_crossing_count")
    if statistics["small_angle_crossing_count"] is None:
        statistics["small_angle_crossing_count"] = recomputed.get(
            "small_angle_crossing_count")
    statistics["small_angle_5deg_threshold_deg"] = 5.0
    statistics["small_angle_5deg_crossing_count"] = (
        pair_audit or {}).get("small_angle_5deg_crossing_count")
    statistics["crossing_points_count"] = len(crossing_points)
    statistics["crossing_points_sample"] = crossing_points[:500]
    statistics["crossing_points_note"] = (
        "full crossing list is not embedded (size); recompute with "
        "four_side_1024.fslw.metrics.compute_pair_audit for figures")
    statistics["crossing_grid_mm"] = GRID_MM
    statistics["crossing_grid_peak"] = (pair_audit or {}).get(
        "crossing_grid_peak")
    statistics["crossing_grid_peak_cell"] = (pair_audit or {}).get(
        "crossing_grid_peak_cell")
    statistics["densest_crossing_cells"] = (pair_audit or {}).get(
        "densest_crossing_cells")
    for field in violation_fields:
        if field in ("crossing_count", "crossing_angle_histogram",
                     "small_angle_crossing_count"):
            continue
        statistics[field] = merged.get(field)
        statistics[f"{field}_source"] = sources.get(field)
        statistics[f"{field}_recomputed"] = recomputed.get(field)
    statistics["total_violation_count"] = (violation_total
                                           if violation_complete else None)
    statistics["audit_passed"] = (audit_report or {}).get("passed")
    statistics["audit_policy"] = (audit_report or {}).get("policy")
    statistics["audit_routed_count"] = (audit_report or {}).get("routed_count")
    statistics["audit_checked_count"] = (audit_report or {}).get("checked_count")
    statistics["audit_passed_count"] = (audit_report or {}).get("passed_count")
    statistics["audit_failed_count"] = (audit_report or {}).get("failed_count")
    statistics["audit_error_count"] = (audit_report or {}).get("error_count")
    statistics["audit_violation_count"] = (audit_report or {}).get(
        "violation_count")
    statistics["audit_candidate_pair_count"] = (audit_report or {}).get(
        "candidate_pair_count")
    statistics["audit_runtime_seconds"] = (audit_report or {}).get(
        "runtime_seconds")
    statistics["audit_crossing_window_count"] = (audit_report or {}).get(
        "crossing_window_count")
    statistics["audit_crossing_window_max_mm"] = (audit_report or {}).get(
        "crossing_window_max_mm")
    statistics["audit_crossing_window_mean_mm"] = (audit_report or {}).get(
        "crossing_window_mean_mm")
    statistics["crossing_window_count"] = (pair_audit or {}).get(
        "crossing_window_count")
    statistics["crossing_window_max_mm"] = (pair_audit or {}).get(
        "crossing_window_max_mm")
    statistics["crossing_window_mean_mm"] = (pair_audit or {}).get(
        "crossing_window_mean_mm")
    statistics["min_non_crossing_centerline_mm"] = (
        (audit_report or {}).get("values", {}).get(
            "min_non_crossing_centerline_mm")
        or (pair_audit or {}).get("min_non_crossing_centerline_mm"))
    statistics["mean_min_gap_mm"] = (gaps or {}).get("mean_min_gap_mm")
    statistics["median_min_gap_mm"] = (gaps or {}).get("median_min_gap_mm")
    statistics["min_min_gap_mm"] = (gaps or {}).get("min_min_gap_mm")
    statistics["max_min_gap_mm"] = (gaps or {}).get("max_min_gap_mm")
    statistics["routes_with_min_gap"] = (gaps or {}).get("routes_with_min_gap")
    statistics["unresolved_min_gap_route_ids"] = (gaps or {}).get(
        "unresolved_route_ids")
    statistics["route_length_density"] = quality["route_length_density"]
    statistics["route_length_grid_peak_mm"] = quality["route_length_grid_peak_mm"]
    statistics["route_length_grid_peak_cell"] = quality[
        "route_length_grid_peak_cell"]
    statistics["top_density_cells"] = quality["top_density_cells"]
    statistics["congestion_hotspots"] = quality["congestion_hotspots"]
    statistics["port_region"] = quality["port_region"]
    statistics["port_region_length_mm"] = quality["port_region_length_mm"]
    statistics["propagation_loss"] = propagation_block
    statistics["propagation_loss_detail"] = propagation_detail
    statistics["optical_loss_breakdown"] = {
        key: value for key, value in loss_breakdown.items()
        if key != "propagation_loss"
    }
    statistics["optical_loss_breakdown"]["propagation_loss"] = (
        loss_breakdown["propagation_loss"])
    statistics["symmetry"] = symmetry
    statistics["candidate_evaluations"] = run_metadata["candidate_evaluations"]
    statistics["candidate_evaluations_source"] = run_metadata[
        "candidate_evaluations_source"]
    statistics["candidate_evaluations_route_sum"] = run_metadata[
        "candidate_evaluations_route_sum"]
    statistics["runtime_seconds"] = run_metadata["runtime_seconds"]
    statistics["runtime_seconds_source"] = run_metadata["runtime_seconds_source"]
    statistics["evals_per_second"] = run_metadata["evals_per_second"]
    statistics["peak_memory_mb"] = run_metadata["peak_memory_mb"]
    statistics["peak_memory_mb_source"] = run_metadata["peak_memory_mb_source"]
    statistics["pair_checks"] = run_metadata["pair_checks"]
    statistics["eval_budget"] = run_metadata["eval_budget"]
    statistics["time_budget_seconds"] = run_metadata["time_budget_seconds"]
    statistics["budget_exhausted"] = run_metadata["budget_exhausted"]
    statistics["seed"] = (config_payload or {}).get("seed")
    statistics["strategy"] = (config_payload or {}).get("strategy")
    statistics["pareto"] = {
        "routed": routed_count,
        "total_length_mm": geometry["total_length_mm"],
        "crossing_count": crossing_count,
        "propagation_loss_total_db": loss_breakdown["propagation_loss"]["value_db"],
        "mean_length_mm": geometry["mean_length_mm"],
        "small_angle_crossing_count": statistics["small_angle_crossing_count"],
        "strict_violation_count": (violation_total if violation_complete else None),
        "lexicographic_objective": [
            "routed (descending)", "strict_violation_count (ascending)",
            "small_angle_crossing_count (ascending)",
            "crossing_count (ascending)", "total_length_mm (ascending)"],
    }
    statistics["geometry_checks"] = {key: value for key, value in geometry.items()
                                     if key not in ("per_route", "route_errors")}
    statistics["route_geometry"] = geometry["per_route"]
    statistics["metric_sources"] = {
        "length": "recomputed_from_primitives (four_side_1024.geometry.length)",
        "straightness/turns/detour": "recomputed_from_primitives",
        "crossings": (f"recomputed with {pair_audit['kernel']} at clearance="
                      f"{(pair_audit or {}).get('clearance_mm')!r} mm"
                      if pair_audit else None),
        "violations": ("authoritative audit_strict.json merged when fresh; "
                       "recomputed_from_primitives otherwise"),
        "propagation_loss": "computed: Lprop_dB = 0.05 dB/cm * length_cm",
        "bend_loss": "unknown_uncalibrated (not invented)",
        "crossing_loss": "unknown_uncalibrated (not invented)",
        "quality": "recomputed_from_primitives (sampled centrelines)",
        "symmetry": (symmetry or {}).get("source"),
        "run_metadata": "routes.json statistics/algorithm + config.json + run.log",
        "audited_fields": sources,
    }
    statistics["notes"] = []
    if audit_meta.get("status") != "merged":
        statistics["notes"].append(
            f"audit_strict.json not merged ({audit_meta.get('status')}); violation "
            "counters recomputed with the independent geometry kernel and marked "
            "with source='recomputed_from_primitives'")
    if audit_meta.get("status") == "stale_ignored":
        statistics["notes"].append(
            "ignored audit file older than routes.json (stale solution)")
    if derived:
        statistics["notes"].append(
            "endpoint table derived from routed primitives only (ports.py "
            "unavailable); endpoint/self checks therefore cover routed routes only")
    if not pair_audit:
        statistics["notes"].append("crossing re-enumeration skipped by caller")
    statistics["notes"].append(
        "process parameters read from four_side_1024.fslw.config and overridden "
        "only by artifact process blocks (Phase-11 sensitivity runs)")
    statistics["notes"].append(
        "bend loss and crossing loss are unknown_uncalibrated; only propagation "
        "loss is reported as a physical loss number")
    statistics["notes"].append(
        "plane is metadata only: all primitives inside a plane are layer=0 2D; "
        "z is 0.0 for z1 and 0.5 for z2 and is never used in plane geometry")
    statistics["recomputation_runtime_seconds"] = time.perf_counter() - started
    statistics = _json_safe(statistics)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(statistics, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    if not quiet:
        print(json.dumps({
            "out": str(out_path),
            "experiment": statistics["experiment"],
            "plane": plane,
            "routed": routed_count,
            "unrouted": unrouted_count,
            "routing_rate": round(statistics["routing_rate"], 6),
            "crossing_count": crossing_count,
            "mean_length_mm": (_round(statistics["mean_length_mm"], 4)
                               if statistics["mean_length_mm"] is not None else None),
            "mean_propagation_loss_db": _round(
                loss_breakdown["propagation_loss"]["mean_db"], 6),
            "audit_passed": statistics["audit_passed"],
            "audit_source": audit_meta.get("status"),
            "recompute_seconds": round(
                statistics["recomputation_runtime_seconds"], 3),
        }, ensure_ascii=False))
    return statistics


# ---------------------------------------------------------------------------
# combined (two-height) statistics
# ---------------------------------------------------------------------------
def _polyline_segments(points):
    if len(points) < 2:
        return np.empty((0, 4))
    return np.column_stack((points[:-1], points[1:])).astype(float)


def _segment_intersection_points(segment, segments, eps=1e-12):
    """Intersection points of one segment against an array of segments.

    Returns ``(points, hit_indices)`` where ``hit_indices`` indexes ``segments``.
    """
    if len(segments) == 0:
        return np.empty((0, 2)), np.empty(0, dtype=int)
    ax, ay = float(segment[0]), float(segment[1])
    bx, by = float(segment[2]), float(segment[3])
    rx, ry = bx - ax, by - ay
    cx = segments[:, 0]
    cy = segments[:, 1]
    dx = segments[:, 2] - cx
    dy = segments[:, 3] - cy
    denominator = rx * dy - ry * dx
    valid = np.abs(denominator) > eps
    if not valid.any():
        return np.empty((0, 2)), np.empty(0, dtype=int)
    qx = cx - ax
    qy = cy - ay
    t = (qx * dy - qy * dx) / np.where(valid, denominator, 1.0)
    u = (qx * ry - qy * rx) / np.where(valid, denominator, 1.0)
    hit = valid & (t >= 0.0) & (t <= 1.0) & (u >= 0.0) & (u <= 1.0)
    if not hit.any():
        return np.empty((0, 2)), np.empty(0, dtype=int)
    hit_indices = np.flatnonzero(hit)
    t_hit = t[hit_indices]
    points = np.column_stack((ax + t_hit * rx, ay + t_hit * ry))
    return points, hit_indices


def compute_cross_plane_projection(z1_routed, z2_routed, process):
    """Informational XY projection of z1 vs z2 (NEVER a violation, SPEC §2).

    Uses a uniform grid over the sampled z2 centrelines so the projection stays
    fast (informational metric only; chordal sampling is stated in the output).
    """
    board_x, board_y = [float(v) for v in (process.get("board_mm")
                                           or [fslw_config.BOARD_MM] * 2)]
    sagitta = float(process.get("projection_sagitta_mm")
                    or PROJECTED_SAGITTA_MM)
    cell_size = 4.0
    grid_x = max(1, int(math.ceil(board_x / cell_size)))
    grid_y = max(1, int(math.ceil(board_y / cell_size)))
    curves = {"z1": {}, "z2": {}}
    for plane, records in (("z1", z1_routed), ("z2", z2_routed)):
        for record in records:
            primitives = record.get("primitives") or []
            if not primitives:
                continue
            points = _sample_polyline(primitives, sagitta)
            if len(points) >= 2:
                curves[plane][record.get("route_id")] = points
    # global z2 segment table with route ownership
    z2_records = []
    z2_segments = []
    z2_owners = []
    for route_id, points in curves["z2"].items():
        segments = _polyline_segments(points)
        for segment in segments:
            z2_records.append(segment)
            z2_segments.append(segment)
            z2_owners.append(route_id)
    z2_segments = np.asarray(z2_segments, dtype=float) if z2_segments else np.empty((0, 4))
    z2_owners = np.asarray(z2_owners, dtype=object)
    grid = {}
    for index, segment in enumerate(z2_segments):
        ix0 = min(grid_x - 1, max(0, int(math.floor(min(segment[0], segment[2]) / cell_size))))
        ix1 = min(grid_x - 1, max(0, int(math.floor(max(segment[0], segment[2]) / cell_size))))
        iy0 = min(grid_y - 1, max(0, int(math.floor(min(segment[1], segment[3]) / cell_size))))
        iy1 = min(grid_y - 1, max(0, int(math.floor(max(segment[1], segment[3]) / cell_size))))
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                grid.setdefault((ix, iy), []).append(index)
    # guaranteed per-port XY projection coincidences (both rows share XY ports)
    port_xy = set()
    for records in (z1_routed, z2_routed):
        for record in records:
            primitives = record.get("primitives") or []
            if primitives:
                for point in (primitives[0]["p0"], primitives[-1]["p1"]):
                    port_xy.add((round(float(point[0]), 6),
                                 round(float(point[1]), 6)))
    seen_points = set()
    hotspot = Counter()
    pair_set = set()
    internal = 0
    port_coincidences = 0
    for z1_id, points in curves["z1"].items():
        z1_segments = _polyline_segments(points)
        for segment in z1_segments:
            ix0 = min(grid_x - 1, max(0, int(math.floor(min(segment[0], segment[2]) / cell_size))))
            ix1 = min(grid_x - 1, max(0, int(math.floor(max(segment[0], segment[2]) / cell_size))))
            iy0 = min(grid_y - 1, max(0, int(math.floor(min(segment[1], segment[3]) / cell_size))))
            iy1 = min(grid_y - 1, max(0, int(math.floor(max(segment[1], segment[3]) / cell_size))))
            candidates = set()
            for ix in range(ix0, ix1 + 1):
                for iy in range(iy0, iy1 + 1):
                    candidates.update(grid.get((ix, iy)) or ())
            if not candidates:
                continue
            candidate_index = np.fromiter(candidates, dtype=int)
            points_hit, hit_local = _segment_intersection_points(
                segment, z2_segments[candidate_index])
            for (px, py), local in zip(points_hit, hit_local):
                z2_id = z2_owners[candidate_index[local]]
                key = (z1_id, z2_id, round(float(px), 6), round(float(py), 6))
                if key in seen_points:
                    continue
                seen_points.add(key)
                pair_set.add((z1_id, z2_id))
                at_port = any(abs(px - x) < 0.05 and abs(py - y) < 0.05
                              for x, y in port_xy)
                if at_port:
                    port_coincidences += 1
                else:
                    internal += 1
                    gx = min(grid_x - 1, max(0, int(math.floor(px / GRID_MM))))
                    gy = min(grid_y - 1, max(0, int(math.floor(py / GRID_MM))))
                    hotspot[(gx, gy)] += 1
    densest = [{"x_min_mm": ix * GRID_MM, "y_min_mm": iy * GRID_MM,
                "projected_crossings": int(count)}
               for (ix, iy), count in hotspot.most_common(10)]
    return {
        "status": "informational_only",
        "not_a_violation": True,
        "note": ("XY projection of the plane-z1 and plane-z2 centrelines.  Per "
                 "SPEC §2 the two rows live at different glass heights; projected "
                 "crossings/overlaps are NOT same-plane conflicts and are never "
                 "counted as violations."),
        "projection_sagitta_mm": sagitta,
        "cross_plane_projected_crossings": internal + port_coincidences,
        "cross_plane_projected_internal_crossings": internal,
        "cross_plane_projected_port_coincidences": port_coincidences,
        "cross_plane_projected_pair_count": len(pair_set),
        "cross_plane_projected_grid_peak": (
            densest[0]["projected_crossings"] if densest else 0),
        "cross_plane_projected_grid_peak_cell": (
            [densest[0]["x_min_mm"], densest[0]["y_min_mm"]] if densest else None),
        "cross_plane_projected_densest_cells": densest,
        "port_projection_note": ("both heights use the same 1024 XY port "
                                 "coordinates, so per-port projection coincidences "
                                 "are guaranteed by the interface model and are "
                                 "classified separately from real projected "
                                 "crossings"),
    }


def _combined_plane_summary(plane_statistics, plane):
    if not plane_statistics:
        return None
    return {
        "plane": plane,
        "z_mm": plane_statistics.get("z_mm"),
        "routed": plane_statistics.get("routed"),
        "unrouted": plane_statistics.get("unrouted"),
        "connections_total": plane_statistics.get("connections_total"),
        "routing_rate": plane_statistics.get("routing_rate"),
        "by_pair": plane_statistics.get("by_pair"),
        "by_relation": plane_statistics.get("by_relation"),
        "mean_length_mm": plane_statistics.get("mean_length_mm"),
        "total_length_mm": plane_statistics.get("total_length_mm"),
        "crossing_count": plane_statistics.get("crossing_count"),
        "propagation_loss": plane_statistics.get("propagation_loss"),
        "audit_passed": plane_statistics.get("audit_passed"),
        "total_violation_count": plane_statistics.get("total_violation_count"),
        "statistics_file": plane_statistics.get("source", {}).get("routes_json")
        if isinstance(plane_statistics.get("source"), dict) else None,
    }


def build_combined_statistics(combined_dir, root=None, out_path=None,
                              plane_statistics=None, skip_projection=False,
                              quiet=False):
    """Merge z1+z2 plane solutions into the 1024-channel combined statistics."""
    started = time.perf_counter()
    combined_dir = Path(combined_dir)
    if root is None:
        # combined/<TOPOLOGY>/<ALGO> -> root
        root = combined_dir.parent.parent
    root = Path(root)
    topology = combined_dir.parent.name
    algorithm = combined_dir.name
    planes = {}
    plane_stats = plane_statistics or {}
    plane_routes = {}
    for plane in ("z1", "z2"):
        plane_dir = _plane_run_dir(root, topology, algorithm, plane)
        routes_path = plane_dir / "routes.json"
        if not routes_path.exists():
            planes[plane] = {"available": False,
                             "run_dir": str(plane_dir),
                             "error": "routes.json missing"}
            continue
        payload, meta, records, routed, failed = load_routes(routes_path)
        plane_routes[plane] = {"payload": payload, "meta": meta,
                               "records": records, "routed": routed,
                               "failed": failed}
        stats = plane_stats.get(plane)
        if stats is None:
            stats_path = plane_dir / "statistics.json"
            if stats_path.exists():
                try:
                    stats = _load_json(stats_path)
                except (OSError, json.JSONDecodeError):
                    stats = None
            if stats is None:
                stats = build_plane_statistics(plane_dir, quiet=True)
            plane_stats[plane] = stats
        planes[plane] = {
            "available": True,
            "run_dir": str(plane_dir),
            "routes_json": str(routes_path),
            "statistics": stats,
            "routed": len(routed),
            "unrouted": len(failed),
        }
    process = load_process(
        plane_routes.get("z1", {}).get("meta") if plane_routes.get("z1")
        else None, None, None)
    # per-plane summaries
    all_routed = []
    for plane in ("z1", "z2"):
        entry = planes.get(plane) or {}
        if entry.get("available"):
            all_routed.append((plane, plane_routes[plane]["routed"]))
    routed_total = sum(len(records) for _, records in all_routed)
    router_reported_total = sum(
        int((plane_routes[plane]["payload"] or {}).get("statistics", {})
            .get("success_count") or 0)
        for plane, _ in all_routed
        if isinstance(plane_routes[plane]["payload"], dict))
    combined = OrderedDict()
    combined["schema"] = SCHEMA_COMBINED
    combined["scope"] = "combined"
    combined["tool"] = TOOL
    combined["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    combined["topology"] = topology
    combined["algorithm"] = algorithm
    combined["experiment"] = f"{topology}_{algorithm}_combined"
    combined["port_model"] = process.get("port_model")
    combined["process"] = _json_safe(process)
    combined["board_mm"] = [fslw_config.BOARD_MM, fslw_config.BOARD_MM]
    combined["z_model"] = {"z1": 0.0, "z2": 0.5,
                           "z2_minus_z1_mm": 0.5,
                           "note": "model heights; no z transition implemented"}
    combined["layer"] = 0
    combined["planes"] = {plane: ({"available": False,
                                   "run_dir": str(planes.get(plane, {}).get(
                                       "run_dir", "")),
                                   "error": planes.get(plane, {}).get("error")}
                                  if not planes.get(plane, {}).get("available")
                                  else _combined_plane_summary(
                                      planes[plane]["statistics"], plane))
                          for plane in ("z1", "z2")}
    combined["connections_total"] = TOTAL_CONNECTIONS
    combined["connections_per_plane"] = CONNECTIONS_PER_PLANE
    combined["routed"] = routed_total
    combined["unrouted"] = TOTAL_CONNECTIONS - routed_total
    combined["routing_rate"] = routed_total / TOTAL_CONNECTIONS
    combined["router_reported_routed_total"] = router_reported_total
    by_plane = OrderedDict()
    for plane in ("z1", "z2"):
        stats = (planes.get(plane) or {}).get("statistics") or {}
        by_plane[plane] = {
            "routed": stats.get("routed"),
            "unrouted": stats.get("unrouted"),
            "connections_total": stats.get("connections_total",
                                           CONNECTIONS_PER_PLANE),
            "routing_rate": stats.get("routing_rate"),
            "z_mm": stats.get("z_mm"),
        }
    combined["by_plane"] = by_plane
    by_relation = OrderedDict()
    for relation, pairs in RELATION_PAIRS.items():
        total = 0
        success = 0
        for plane in ("z1", "z2"):
            stats = (planes.get(plane) or {}).get("statistics") or {}
            for pair in pairs:
                entry = (stats.get("by_pair") or {}).get(pair)
                if entry:
                    total += int(entry.get("total") or 0)
                    success += int(entry.get("success") or 0)
        if total:
            by_relation[relation] = {"pairs": list(pairs), "success": success,
                                     "routed": success, "failed": total - success,
                                     "total": total,
                                     "routing_rate": success / total}
    combined["by_relation"] = by_relation
    by_pair = OrderedDict()
    for pair in PAIR_ORDER:
        total = 0
        success = 0
        for plane in ("z1", "z2"):
            entry = ((planes.get(plane) or {}).get("statistics") or {}).get(
                "by_pair", {}).get(pair)
            if entry:
                total += int(entry.get("total") or 0)
                success += int(entry.get("success") or 0)
        if total:
            by_pair[pair] = {"relation": PAIR_RELATION[pair], "success": success,
                             "routed": success, "failed": total - success,
                             "total": total, "routing_rate": success / total}
    combined["by_pair"] = by_pair
    total_length = 0.0
    total_bends = 0
    length_weighted = 0.0
    route_count_length = 0
    straight_weighted = 0.0
    straight_routes = 0
    detour_total = 0.0
    detour_weighted = 0.0
    same_plane_crossings = 0
    crossing_histogram = {label: 0 for label, _, _ in _HIST_BINS}
    small_angle = 0
    violation_total = 0
    violation_complete = True
    for plane in ("z1", "z2"):
        stats = (planes.get(plane) or {}).get("statistics") or {}
        geometry = stats.get("length") or {}
        length = _number(geometry.get("total_length_mm"))
        if length is not None:
            total_length += length
        total_bends += int(stats.get("total_bends") or 0)
        mean_length = _number(stats.get("mean_length_mm"))
        routed_count = int(stats.get("routed") or 0)
        if mean_length is not None and routed_count:
            length_weighted += mean_length * routed_count
            route_count_length += routed_count
        straight = _number(stats.get("mean_straight_fraction"))
        if straight is not None and routed_count:
            straight_weighted += straight * routed_count
            straight_routes += routed_count
        detour = _number(stats.get("total_unnecessary_detour_mm"))
        if detour is not None:
            detour_total += detour
        mean_detour = _number(stats.get("mean_unnecessary_detour_mm"))
        if mean_detour is not None and routed_count:
            detour_weighted += mean_detour * routed_count
        crossing = _number(stats.get("crossing_count"))
        if crossing is not None:
            same_plane_crossings += int(crossing)
        hist = stats.get("crossing_angle_histogram") or {}
        for label in crossing_histogram:
            crossing_histogram[label] += int(hist.get(label) or 0)
        small = _number(stats.get("small_angle_crossing_count"))
        if small is not None:
            small_angle += int(small)
        for field in ("spacing_violation_pairs", "overlap_pairs", "touch_pairs",
                      "crossing_window_overlap_pairs", "double_cross_pairs",
                      "crossing_window_excessive_pairs", "self_intersections",
                      "self_overlaps", "self_spacing_violations",
                      "radius_violations", "boundary_violations",
                      "diagonal_line_violations", "free_arc_violations"):
            value = stats.get(field)
            if value is None:
                violation_complete = False
            else:
                violation_total += int(value)
    combined["length"] = {
        "mean_length_mm": (length_weighted / route_count_length)
        if route_count_length else None,
        "total_length_mm": total_length,
        "mean_straight_fraction": (straight_weighted / straight_routes)
        if straight_routes else None,
        "total_unnecessary_detour_mm": detour_total,
        "mean_unnecessary_detour_mm": (detour_weighted / route_count_length)
        if route_count_length else None,
        "total_bends": total_bends,
    }
    combined["mean_length_mm"] = (length_weighted / route_count_length) \
        if route_count_length else None
    combined["total_length_mm"] = total_length
    combined["total_bends"] = total_bends
    combined["mean_straight_fraction"] = (straight_weighted / straight_routes) \
        if straight_routes else None
    combined["total_unnecessary_detour_mm"] = detour_total
    combined["same_plane_crossings"] = same_plane_crossings
    combined["same_plane_crossing_angle_histogram"] = crossing_histogram
    combined["small_angle_crossing_count"] = small_angle
    combined["same_plane_crossing_by_plane"] = {
        plane: ((planes.get(plane) or {}).get("statistics") or {}).get(
            "crossing_count") for plane in ("z1", "z2")}
    combined["violations"] = {
        "same_plane_total": violation_total if violation_complete else None,
        "complete": violation_complete,
        "by_plane": {plane: {
            field: ((planes.get(plane) or {}).get("statistics") or {}).get(field)
            for field in ("spacing_violation_pairs", "overlap_pairs",
                          "touch_pairs", "crossing_window_overlap_pairs",
                          "self_intersections", "radius_violations",
                          "boundary_violations")}
            for plane in ("z1", "z2")},
        "cross_plane": {
            "status": "not_a_violation_by_design",
            "note": "SPEC §2: different glass heights; no cross-plane same-layer "
                    "conflict test exists",
            "value": 0,
        },
    }
    propagation_total = 0.0
    propagation_mean_weighted = 0.0
    propagation_routes = 0
    propagation_detail = {}
    for plane in ("z1", "z2"):
        stats = (planes.get(plane) or {}).get("statistics") or {}
        block = stats.get("propagation_loss") or {}
        total = _number(block.get("value_db"))
        mean = _number(block.get("mean_db"))
        routed_count = int(stats.get("routed") or 0)
        if total is not None:
            propagation_total += total
        if mean is not None and routed_count:
            propagation_mean_weighted += mean * routed_count
            propagation_routes += routed_count
        propagation_detail[plane] = block
    combined["propagation_loss"] = {
        "status": "computed",
        "value_db": propagation_total,
        "total_db": propagation_total,
        "mean_db": (propagation_mean_weighted / propagation_routes)
        if propagation_routes else None,
        "total_length_cm": total_length / 10.0,
        "formula": "Lprop_dB = 0.05 dB/cm * length_cm",
        "db_per_cm": float(process.get("propagation_loss_db_per_cm")
                           or fslw_config.PROPAGATION_LOSS_DB_PER_CM),
        "by_plane": propagation_detail,
        "optical_loss_scope": (
            "propagation-only; bend loss and crossing loss are "
            "unknown_uncalibrated"),
    }
    combined["optical_loss_breakdown"] = compute_loss_breakdown(
        [total_length], process)
    combined["optical_loss_breakdown"]["propagation_loss"] = \
        combined["propagation_loss"]
    if not skip_projection and all(
            (planes.get(plane) or {}).get("available") for plane in ("z1", "z2")):
        combined["cross_plane_projected_overlap"] = compute_cross_plane_projection(
            plane_routes["z1"]["routed"], plane_routes["z2"]["routed"], process)
    else:
        combined["cross_plane_projected_overlap"] = {
            "status": "unavailable",
            "note": "both plane runs must exist to compute the XY projection",
        }
    combined["mean_min_gap_mm"] = _mean([
        _number(((planes.get(plane) or {}).get("statistics") or {}).get(
            "mean_min_gap_mm")) for plane in ("z1", "z2")])
    combined["route_length_grid_peak_mm"] = max(
        [_number(((planes.get(plane) or {}).get("statistics") or {}).get(
            "route_length_grid_peak_mm")) or 0.0 for plane in ("z1", "z2")],
        default=0.0)
    combined["symmetry"] = {
        plane: ((planes.get(plane) or {}).get("statistics") or {}).get("symmetry")
        for plane in ("z1", "z2")}
    combined["symmetry_note"] = ("symmetry is analysed per plane (each plane is "
                                 "an independent 2D problem); combined symmetry is "
                                 "not defined for two different heights")
    combined["candidate_evaluations"] = sum(
        int(((planes.get(plane) or {}).get("statistics") or {}).get(
            "candidate_evaluations") or 0) for plane in ("z1", "z2"))
    combined["runtime_seconds"] = sum(
        (_number(((planes.get(plane) or {}).get("statistics") or {}).get(
            "runtime_seconds")) or 0.0) for plane in ("z1", "z2"))
    combined["audit_passed_all_planes"] = all(
        ((planes.get(plane) or {}).get("statistics") or {}).get("audit_passed")
        is True for plane in ("z1", "z2")
        if (planes.get(plane) or {}).get("available"))
    combined["plane_summaries"] = {plane: _combined_plane_summary(
        (planes.get(plane) or {}).get("statistics"), plane)
        for plane in ("z1", "z2")}
    combined["pareto"] = {
        "routed": routed_total,
        "total_length_mm": total_length,
        "same_plane_crossings": same_plane_crossings,
        "propagation_loss_total_db": propagation_total,
        "strict_violation_count": violation_total if violation_complete else None,
        "lexicographic_objective": [
            "routed (descending)", "strict_violation_count (ascending)",
            "same_plane_crossings (ascending)", "total_length_mm (ascending)"],
    }
    combined["metric_sources"] = {
        "per_plane": "planes/<T>/<A>/<PLANE>/statistics.json (recomputed from "
                     "primitives; strict audit merged when fresh)",
        "combined": "merged from the two plane statistics; per-plane crossing "
                    "counts summed as same_plane_crossings",
        "cross_plane_projected_overlap": "sampled XY projection; informational "
                                         "only, never a violation (SPEC §2)",
        "losses": "propagation computed; bend/crossing unknown_uncalibrated",
    }
    combined["notes"] = [
        "combined layout = plane z1 (row 1, 512 opposite connections) + plane z2 "
        "(row 2, 512 adjacent connections) at model heights 0.0/0.5",
        "each plane is an independent 2D problem at layer=0; the two heights are "
        "NOT a waveguide layer stack and no z-transition is implemented",
        "cross-plane XY-projected overlaps are informational only and never "
        "violations (SPEC §2)",
        "bend loss and crossing loss remain unknown_uncalibrated",
    ]
    combined["recomputation_runtime_seconds"] = time.perf_counter() - started
    combined = _json_safe(combined)
    if out_path is None:
        out_path = combined_dir / "statistics.json"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(combined, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    if not quiet:
        projection = combined.get("cross_plane_projected_overlap") or {}
        print(json.dumps({
            "out": str(out_path),
            "experiment": combined["experiment"],
            "routed": routed_total,
            "total": TOTAL_CONNECTIONS,
            "routing_rate": round(combined["routing_rate"], 6),
            "by_plane": {plane: by_plane[plane]["routed"] for plane in by_plane},
            "same_plane_crossings": same_plane_crossings,
            "cross_plane_projected_internal": projection.get(
                "cross_plane_projected_internal_crossings"),
            "total_length_mm": round(total_length, 3),
            "propagation_loss_total_db": _round(propagation_total, 6),
            "recompute_seconds": round(
                combined["recomputation_runtime_seconds"], 3),
        }, ensure_ascii=False))
    return combined


# ---------------------------------------------------------------------------
# plan / discovery helpers shared with plots.py / combine.py / compare.py
# ---------------------------------------------------------------------------
def iter_plane_runs(root):
    """Yield ``(topology, algorithm, plane, run_dir)`` for existing plane runs."""
    root = Path(root)
    planes_root = root / "planes"
    if not planes_root.exists():
        return
    for topology_dir in sorted(planes_root.iterdir()):
        if not topology_dir.is_dir():
            continue
        for algorithm_dir in sorted(topology_dir.iterdir()):
            if not algorithm_dir.is_dir():
                continue
            for plane in ("z1", "z2"):
                run_dir = algorithm_dir / plane
                if (run_dir / "routes.json").exists():
                    yield topology_dir.name, algorithm_dir.name, plane, run_dir


def iter_combined_runs(root):
    root = Path(root)
    combined_root = root / "combined"
    if not combined_root.exists():
        return
    for topology_dir in sorted(combined_root.iterdir()):
        if not topology_dir.is_dir():
            continue
        for algorithm_dir in sorted(topology_dir.iterdir()):
            if algorithm_dir.is_dir():
                yield topology_dir.name, algorithm_dir.name, algorithm_dir


def iter_sensitivity_runs(root):
    root = Path(root)
    sensitivity_root = root / "sensitivity"
    if not sensitivity_root.exists():
        return
    for config_dir in sorted(sensitivity_root.iterdir()):
        if not config_dir.is_dir():
            continue
        for topology_dir in sorted(config_dir.iterdir()):
            if not topology_dir.is_dir():
                continue
            for algorithm_dir in sorted(topology_dir.iterdir()):
                if not algorithm_dir.is_dir():
                    continue
                for plane in ("z1", "z2"):
                    run_dir = algorithm_dir / plane
                    if (run_dir / "routes.json").exists():
                        yield (config_dir.name, topology_dir.name,
                               algorithm_dir.name, plane, run_dir)


def iter_c_sweep_runs(root):
    """Yield ``(design, topology, plane, run_dir)`` for C-sweep plane runs.

    Layout: ``c_sweep/<design>/<topology>/<plane>/``.  C-sweep runs document the
    frozen C design; they are NOT part of the eight official combined layouts.
    """
    root = Path(root)
    sweep_root = root / "c_sweep"
    if not sweep_root.exists():
        return
    for design_dir in sorted(sweep_root.iterdir()):
        if not design_dir.is_dir():
            continue
        for topology_dir in sorted(design_dir.iterdir()):
            if not topology_dir.is_dir():
                continue
            for plane in ("z1", "z2"):
                run_dir = topology_dir / plane
                if (run_dir / "routes.json").exists():
                    yield design_dir.name, topology_dir.name, plane, run_dir
            for algorithm_dir in sorted(topology_dir.iterdir()):
                if not algorithm_dir.is_dir():
                    continue
                for plane in ("z1", "z2"):
                    run_dir = algorithm_dir / plane
                    if (run_dir / "routes.json").exists():
                        yield (design_dir.name, topology_dir.name, plane,
                               run_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser():
    parser = argparse.ArgumentParser(
        description="Recompute FSLW R=40/gap-30 plane or combined statistics.")
    parser.add_argument("--run-dir", help="plane run dir containing routes.json")
    parser.add_argument("--combined-dir", help="combined/<TOPOLOGY>/<ALGO> dir")
    parser.add_argument("--root", help="outputs root (needed with --combined-dir)")
    parser.add_argument("--routes", help="explicit plane routes.json path")
    parser.add_argument("--config", help="explicit plane config.json path")
    parser.add_argument("--audit", help="explicit audit_strict.json path")
    parser.add_argument("--out", help="output statistics.json path")
    parser.add_argument("--skip-pair-audit", action="store_true")
    parser.add_argument("--skip-min-gaps", action="store_true")
    parser.add_argument("--skip-symmetry", action="store_true")
    parser.add_argument("--skip-quality", action="store_true")
    parser.add_argument("--skip-projection", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.combined_dir:
        statistics = build_combined_statistics(
            combined_dir=args.combined_dir, root=args.root, out_path=args.out,
            skip_projection=args.skip_projection, quiet=args.quiet)
        return 0 if statistics else 1
    run_dir = args.run_dir
    routes_path = args.routes
    config_path = args.config
    audit_path = args.audit
    if run_dir and not routes_path:
        routes_path = str(Path(run_dir) / "routes.json")
        if config_path is None:
            candidate = Path(run_dir) / "config.json"
            config_path = str(candidate) if candidate.exists() else None
        if audit_path is None:
            candidate = Path(run_dir) / "audit_strict.json"
            audit_path = str(candidate) if candidate.exists() else None
        if args.out is None:
            args.out = str(Path(run_dir) / "statistics.json")
    if not routes_path:
        raise SystemExit("fslw.metrics: --run-dir/--routes or --combined-dir required")
    statistics = build_plane_statistics(
        Path(routes_path).parent if run_dir is None else run_dir,
        out_path=args.out, audit_path=audit_path, config_path=config_path,
        skip_pair_audit=args.skip_pair_audit, skip_min_gaps=args.skip_min_gaps,
        skip_symmetry=args.skip_symmetry, skip_quality=args.skip_quality,
        quiet=args.quiet)
    return 0 if statistics else 1


if __name__ == "__main__":
    raise SystemExit(main())
