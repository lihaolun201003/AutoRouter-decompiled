"""Recompute the ABCD experiment metric set (SPEC §5) from route primitives.

Phase 6 deliverable for the 1024-channel four-side single-layer experiment
(``four_side_1024/abcd/SPEC.md`` §4/§5).  The router's own ``statistics`` block
inside ``routes.json`` is **never** trusted: every geometric number below is
re-derived from the analytic ``primitives`` (straight lines + fixed-radius
quarter arcs + legacy short-S theta pairs) and, where an independent audit file
exists, the authoritative *violation* counters of
``validate_d56.py`` are merged in (the ``sources`` block records which file was
used for each counter).

What is recomputed here vs. delegated
-------------------------------------
* recomputed from primitives in this module: length, bend count, straight
  fraction, per-side-pair / per-relation counts, board bounds, layer, radius,
  orthogonality, arc-family, endpoint fixity, crossing enumeration, crossing
  angle histogram, 5 mm crossing-grid density, nearest non-crossing centreline
  gap, 0.175 mm track-band regularity, symmetry/Hausdorff shape match;
* single-route violation verdicts are recomputed with the authoritative
  independent predicate of ``four_side_1024/d56/validate_d56.py`` (the validator
  re-derives them from primitives and never consults the router's checker);
* inter-route violation counters are taken from ``audit_strict.json`` when it is
  present because SPEC §2.2 makes that file authoritative.  If it is absent the
  values are recomputed with the same independent validator kernel and clearly
  marked ``source="recomputed_from_primitives"``; missing inputs are reported as
  ``null`` with an explicit ``missing`` note instead of being guessed.

Metric naming follows SPEC §5 exactly.  Two definitions worth stating because
the SPEC leaves them free:

``mean_min_gap_mm``
    For every routed route, the minimum exact centreline distance to any
    *non-crossing* primitive of another routed route (primitive pairs that
    intersect -- i.e. an allowed 2D crossing -- are excluded, otherwise a dense
    crossing pattern would drive every gap to zero); the reported value is the
    mean over routes.  ``median``/``min``/``max`` and the number of routes with
    no non-crossing neighbour are reported next to it.  (See ``_route_gaps``.)

``track_band_score``
    Fraction of axis-parallel line pairs on different routes (overlapping
    projection, separation <= 9 x 0.175 mm) whose perpendicular separation lies
    within 10 % of an integer multiple of the 0.175 mm clearance pitch.
    (See ``_track_band_score``.)

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.abcd.metrics \\
        --routes  outputs/four_side_1024_v1_v2_abcd/V1_B/routes.json \\
        --config  outputs/four_side_1024_v1_v2_abcd/V1_B/config.json \\
        --audit   outputs/four_side_1024_v1_v2_abcd/V1_B/audit_strict.json \\
        --out     outputs/four_side_1024_v1_v2_abcd/V1_B/statistics.json

``--run-dir`` is a convenience that infers ``routes.json``/``config.json``/
``audit_strict.json``/``statistics.json`` from the directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

from .. import inputs as inputs_module
from ..geometry import bounds as geometry_bounds
from ..geometry import length as geometry_length
from ..geometry import sample as geometry_sample

SCHEMA = "four_side_1024_abcd_statistics_v1"
TOOL = "four_side_1024.abcd.metrics"

# ---------------------------------------------------------------------------
# SPEC constants (never changed here)
# ---------------------------------------------------------------------------
BOARD_MM = 150.0
TOTAL_CONNECTIONS = 1024
LAYER = 0
WIDTH_MM = 0.05
EDGE_GAP_MM = 0.125
CLEARANCE_MM = WIDTH_MM + EDGE_GAP_MM  # 0.175 mm centreline clearance
MIN_RADIUS_MM = 5.0
SAGITTA_MM = 0.0005
CROSSING_GRID_MM = 5.0
SMALL_ANGLE_DEG = 10.0
SMALL_ANGLE_5DEG = 5.0
SHAPE_MATCH_MM = 0.05
HIST_BINS = (("0-1", 0.0, 1.0), ("1-5", 1.0, 5.0), ("5-10", 5.0, 10.0),
             ("10-20", 10.0, 20.0), ("20-30", 20.0, 30.0),
             ("30-45", 30.0, 45.0), ("45-60", 45.0, 60.0),
             ("60-75", 60.0, 75.0), ("75-90", 75.0, 90.000001))
PAIR_ORDER = ("NS", "EW", "EN", "ES", "SW", "NW")
RELATION_PAIRS = OrderedDict((("opposite", ("NS", "EW")),
                              ("adjacent", ("EN", "ES", "SW", "NW"))))
PAIR_RELATION = {pair: relation
                 for relation, pairs in RELATION_PAIRS.items() for pair in pairs}
ROUTED_STATUS = {"routed", "success", "succeeded", "ok", "routed_ok"}
FAILED_STATUS = {"failed", "failure", "fail", "blocked", "rejected"}
#: SPEC §5 symmetry metric names -> transform names used by connectivity.py
SYMMETRY_SPEC_NAMES = ("rot90", "rot180", "mirror_x", "mirror_y", "diag")
SYMMETRY_ALIASES = {"diag": ("diag", "diag_main"), "rot90": ("rot90",),
                    "rot180": ("rot180",), "mirror_x": ("mirror_x",),
                    "mirror_y": ("mirror_y",)}

#: fixed set of isometries used by the local fallback when
#: ``four_side_1024.abcd.connectivity.symmetry_maps`` is not installed yet.
FALLBACK_TRANSFORMS = OrderedDict((
    ("identity", (((1.0, 0.0), (0.0, 1.0)), (0.0, 0.0))),
    ("rot90", (((0.0, -1.0), (1.0, 0.0)), (150.0, 0.0))),
    ("rot180", (((-1.0, 0.0), (0.0, -1.0)), (150.0, 150.0))),
    ("rot270", (((0.0, 1.0), (-1.0, 0.0)), (0.0, 150.0))),
    ("mirror_x", (((-1.0, 0.0), (0.0, 1.0)), (150.0, 0.0))),
    ("mirror_y", (((1.0, 0.0), (0.0, -1.0)), (0.0, 150.0))),
    ("diag", (((0.0, 1.0), (1.0, 0.0)), (0.0, 0.0))),
    ("diag_anti", (((0.0, -1.0), (-1.0, 0.0)), (150.0, 150.0))),
))


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def _load_json(path):
    # utf-8-sig tolerates a BOM from hand-edited / Windows-written JSON files
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _sha256(path):
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _number(value):
    """Return ``value`` as float when it is a finite real number else ``None``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value, digits=6):
    number = _number(value)
    return None if number is None else round(number, digits)


def _first(mapping, keys, default=None):
    """First present non-``None`` value among ``keys`` in ``mapping``."""
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _split_records(payload):
    """Normalise a routes payload to ``(records, meta)``."""
    meta = {}
    if isinstance(payload, dict):
        records = payload.get("routes")
        for key in ("schema", "units", "layer", "endpoint_mode", "csv_sha256",
                    "config", "algorithm", "statistics"):
            if key in payload:
                meta[key] = payload[key]
    elif isinstance(payload, list):
        records = payload
    else:
        raise ValueError("routes.json must be a mapping or a list")
    if not isinstance(records, list):
        raise ValueError("routes.json has no 'routes' list")
    return records, meta


def _status(record):
    status = record.get("status")
    if status is None:
        return "routed" if record.get("primitives") else "failed"
    text = str(status).strip().lower()
    if text in FAILED_STATUS:
        return "failed"
    if text in ROUTED_STATUS:
        return "routed"
    return "routed" if record.get("primitives") else "failed"


def _pair_of(record):
    pair = record.get("pair")
    if pair:
        return str(pair)
    source = str(record.get("source_side") or "")
    target = str(record.get("target_side") or "")
    if source and target:
        for candidate in (source + target, source + target[::-1]):
            if candidate in PAIR_RELATION:
                return candidate
    return "UNKNOWN"


def _relation_of(record):
    relation = record.get("relation")
    if relation in RELATION_PAIRS:
        return relation
    return PAIR_RELATION.get(_pair_of(record))


def _derived_config(routes_meta, config_payload, run_dir):
    """Merge config sources (closest wins) and normalise key geometry."""
    merged = {}
    algorithm = None
    if isinstance(routes_meta, dict):
        algorithm = routes_meta.get("algorithm") or routes_meta.get(
            "algorithm_detail")
        for key in ("experiment", "topology", "algorithm", "units", "layer",
                    "endpoint_mode", "csv_sha256", "csv_path"):
            if routes_meta.get(key) is not None:
                merged[key] = routes_meta[key]
    nested_sources = [routes_meta.get("config") if isinstance(routes_meta, dict)
                      else None,
                      algorithm,
                      routes_meta.get("run_info") if isinstance(routes_meta, dict)
                      else None]
    top_sources = [config_payload]
    if isinstance(config_payload, dict):
        top_sources.extend([config_payload.get("physics"),
                            config_payload.get("budget_used"),
                            config_payload.get("run_info"),
                            config_payload.get("overrides")])
    for source in nested_sources + top_sources:
        if isinstance(source, dict):
            merged.update({key: value for key, value in source.items()
                           if value is not None})

    def _as_float(*keys, default=None):
        for key in keys:
            if key in merged and merged[key] is not None:
                number = _number(merged[key])
                if number is not None:
                    return number
        return default

    board = merged.get("board_mm")
    if isinstance(board, (list, tuple)) and len(board) == 2:
        board_wh = (_number(board[0]) or BOARD_MM, _number(board[1]) or BOARD_MM)
    else:
        side = _number(board) or BOARD_MM
        board_wh = (side, side)
    result = {
        "board_mm": board_wh,
        "width_mm": _as_float("width_mm", "waveguide_width_mm", default=WIDTH_MM),
        "edge_gap_mm": _as_float("edge_gap_mm", default=EDGE_GAP_MM),
        "min_radius_mm": _as_float("min_radius_mm", "radius_mm",
                                   default=MIN_RADIUS_MM),
        "sagitta_mm": _as_float("sagitta_mm", default=SAGITTA_MM),
        "virtual_pitch_mm": _as_float("virtual_pitch_mm", default=CLEARANCE_MM),
        "crossing_small_angle_deg": _as_float("crossing_small_angle_deg",
                                              default=SMALL_ANGLE_DEG),
        "crossing_policy": (merged.get("crossing_policy") or merged.get("policy")
                            or merged.get("acceptance_policy")),
        "experiment": _first(merged, ("experiment", "run_id")),
        "topology": _first(merged, ("topology", "topology_name", "connectivity",
                                    "input_topology")),
        "algorithm": _first(merged, ("algorithm", "algorithm_name")),
        "strategy": merged.get("strategy"),
        "seed": _first(merged, ("seed", "random_seed")),
        "eval_budget": _first(merged, ("eval_budget", "candidate_evaluation_budget",
                                       "evaluation_budget", "candidate_budget")),
        "time_budget_seconds": _first(merged, ("time_budget_seconds",
                                               "time_budget", "search_seconds",
                                               "time_limit_seconds")),
        "topology_csv": _first(merged, ("topology_csv", "input_csv", "csv_path",
                                        "connectivity_csv", "input")),
        "run_status": merged.get("run_status"),
        "budget_exhausted": merged.get("budget_exhausted"),
        "raw_config": {key: merged[key] for key in sorted(merged)},
    }
    if result["width_mm"] and result["edge_gap_mm"] is not None:
        result["clearance_mm"] = result["width_mm"] + result["edge_gap_mm"]
    else:
        result["clearance_mm"] = CLEARANCE_MM
    if result["topology"] is None and run_dir is not None:
        match = re.match(r"^(V\d+)", run_dir.name, re.I)
        if match:
            result["topology"] = match.group(1).upper()
    if result["algorithm"] is None and run_dir is not None:
        match = re.match(r"^V\d+_([A-Za-z])", run_dir.name, re.I)
        if match:
            result["algorithm"] = match.group(1).upper()
    if isinstance(result["algorithm"], str) and len(result["algorithm"]) > 1:
        # keep an explicit algorithm label but derive the A/B/C/D tag when the
        # configuration only carries a long strategy name.
        match = re.search(r"\b([ABCD])\b|^([ABCD])[_\s-]", result["algorithm"])
        if match:
            result["algorithm"] = (match.group(1) or match.group(2)).upper()
    if result["experiment"] is None and run_dir is not None:
        result["experiment"] = run_dir.name
    return result


def _endpoint_bundle(config):
    """Load the endpoint / connector table used for port and symmetry checks."""
    path = config.get("topology_csv")
    try:
        if path:
            bundle = inputs_module.load(path=path)
        else:
            bundle = inputs_module.load()
        rows, endpoints, connectors, validation = bundle
        return {"rows": rows, "endpoints": endpoints, "connectors": connectors,
                "validation": validation,
                "source": str(path) if path else "inputs.load() default (V1 CSV)"}
    except Exception as exc:  # noqa: BLE001 - report, never guess
        return {"rows": None, "endpoints": None, "connectors": None,
                "validation": None, "source": None, "error": f"{type(exc).__name__}: {exc}"}


def _validator():
    """Import the authoritative independent D56 validator (read-only use)."""
    from ..d56 import validate_d56  # local import: keeps module import cheap
    return validate_d56


def _validator_supported_policies(validator):
    supported = {"legacy"}
    try:
        consts = validator.evaluate_pair.__code__.co_consts
    except AttributeError:
        return supported
    for const in consts:
        if isinstance(const, str) and const in ("exact", "strict"):
            supported.add(const)
    return supported


def _choose_policy(validator, requested):
    """Return ``(policy, note)`` for the crossing re-evaluation."""
    supported = _validator_supported_policies(validator)
    order = []
    if isinstance(requested, str):
        requested = requested.strip().lower()
        if requested in supported:
            return requested, None
        order.append(requested)
    default = "strict" if "strict" in supported else (
        "exact" if "exact" in supported else "legacy")
    note = None
    if requested:
        note = (f"requested crossing_policy={requested!r} is not implemented by "
                f"validate_d56.py yet; re-evaluated with {default!r}")
    return default, note


# ---------------------------------------------------------------------------
# single-route geometry + violation recomputation
# ---------------------------------------------------------------------------
_ERROR_CATEGORIES = (
    ("radius", ("arc_radius:",)),
    ("boundary", ("board_out_of_bounds:", "bounds_undefined:")),
    ("diagonal_line", ("diagonal_line:",)),
    ("free_arc", ("short_s_unpaired_arc:", "short_s_pair_invalid:")),
    ("self_intersection", ("self_intersection:",)),
    ("self_overlap", ("self_overlap:",)),
    ("self_spacing", ("self_spacing:",)),
    ("layer", ("nonzero_layer:", "nonzero_z:", "invalid_primitive:")),
    ("position_continuity", ("position_discontinuity:",)),
    ("tangent_continuity", ("tangent_discontinuity:",)),
    ("arc_endpoint", ("arc_endpoint_inconsistent:",)),
    ("endpoint_fixity", ("start_endpoint_mismatch", "end_endpoint_mismatch")),
    ("io_direction", ("start_direction_mismatch", "end_direction_mismatch")),
)


def _categorise_error(message):
    for category, prefixes in _ERROR_CATEGORIES:
        for prefix in prefixes:
            if message.startswith(prefix):
                return category
    return "other"


def compute_route_geometry(routed, config, endpoints):
    """Recompute per-route geometry and single-route violation verdicts."""
    validator = _validator()
    width = float(config.get("width_mm") or WIDTH_MM)
    radius = float(config.get("min_radius_mm") or MIN_RADIUS_MM)
    board = config.get("board_mm") or (BOARD_MM, BOARD_MM)
    board_side = float(max(board))
    endpoint_table = endpoints or {}
    lengths = []
    straight_lengths = []
    arcs = []
    lines = []
    reported_lengths = []
    length_mismatches = []
    bend_mismatches = []
    per_route = {}
    routes_without_geometry = 0
    endpoints_checked = 0
    route_error_counts = Counter()
    route_errors_by_category = Counter()
    geometry_error_examples = []
    check_failed_routes = Counter()
    checks_total = Counter()
    route_error_records = {}
    for record in routed:
        primitives = record.get("primitives") or []
        route_id = record.get("route_id")
        if not primitives:
            routes_without_geometry += 1
            continue
        total = geometry_length(primitives)
        line_total = 0.0
        line_count = 0
        arc_count = 0
        for primitive in primitives:
            kind = primitive.get("kind")
            if kind == "line":
                line_count += 1
                line_total += geometry_length([primitive])
            elif kind == "arc":
                arc_count += 1
        lengths.append(total)
        straight_lengths.append(line_total)
        arcs.append(arc_count)
        lines.append(line_count)
        reported = _number(record.get("length_mm"))
        if reported is not None:
            reported_lengths.append(reported)
            if abs(reported - total) > 1e-6:
                length_mismatches.append({"route_id": route_id,
                                          "recomputed_mm": total,
                                          "reported_mm": reported,
                                          "abs_diff_mm": abs(reported - total)})
        reported_bends = _number(record.get("bend_count"))
        if reported_bends is not None and int(reported_bends) != arc_count:
            bend_mismatches.append({"route_id": route_id,
                                    "recomputed": arc_count,
                                    "reported": int(reported_bends)})
        source = endpoint_table.get(record.get("source_endpoint"))
        target = endpoint_table.get(record.get("target_endpoint"))
        try:
            result = validator.check_route_primitives(
                primitives, source=source, target=target,
                width=width, radius=radius, board=board_side)
        except Exception as exc:  # noqa: BLE001 - report, never crash silently
            result = {"passed": False, "errors": [f"validator_error:{exc}"],
                      "checks": {}, "endpoints_checked": False}
        if result.get("endpoints_checked"):
            endpoints_checked += 1
        errors = list(result.get("errors") or [])
        if errors:
            route_error_records[route_id] = errors
            categories = Counter()
            for message in errors:
                category = _categorise_error(message)
                route_error_counts[message.split(":")[0]] += 1
                route_errors_by_category[category] += 1
                categories[category] += 1
            if len(geometry_error_examples) < 20:
                geometry_error_examples.append({"route_id": route_id,
                                                "errors": errors[:8]})
            if "other" in categories:
                route_error_counts["other"] += 0
        for name, passed in (result.get("checks") or {}).items():
            checks_total[name] += 1
            if not passed:
                check_failed_routes[name] += 1
        per_route[route_id] = {
            "length_mm": total,
            "straight_length_mm": line_total,
            "straight_fraction": (line_total / total) if total > 0 else None,
            "arc_count": arc_count,
            "line_count": line_count,
            "endpoint_checked": bool(result.get("endpoints_checked")),
        }

    def _mean(values):
        values = [value for value in values if value is not None]
        return (sum(values) / len(values)) if values else None

    straight_fractions = [item["straight_fraction"] for item in per_route.values()
                          if item["straight_fraction"] is not None]
    total_length = sum(lengths) if lengths else 0.0
    geometry = {
        "routes_with_geometry": len(per_route),
        "routes_without_geometry": routes_without_geometry,
        "length_mm": per_route,
        "mean_length_mm": _mean(lengths),
        "max_length_mm": max(lengths) if lengths else None,
        "min_length_mm": min(lengths) if lengths else None,
        "total_length_mm": total_length,
        "mean_straight_fraction": _mean(straight_fractions),
        "mean_bend_count": _mean(arcs),
        "max_bend_count": max(arcs) if arcs else None,
        "total_bends": int(sum(arcs)),
        "mean_turns": _mean(arcs),
        "total_lines": int(sum(lines)),
        "total_arcs": int(sum(arcs)),
        "mean_line_count": _mean(lines),
        "length_mismatch_count": len(length_mismatches),
        "length_mismatch_routes": length_mismatches[:20],
        "max_length_mismatch_mm": (max(item["abs_diff_mm"] for item in length_mismatches)
                                   if length_mismatches else 0.0),
        "bend_count_mismatch_count": len(bend_mismatches),
        "reported_length_routes": len(reported_lengths),
        "routes_with_geometry_errors": len(route_error_records),
        "geometry_error_counts": dict(sorted(route_error_counts.items())),
        "geometry_error_category_counts": dict(sorted(route_errors_by_category.items())),
        "geometry_error_examples": geometry_error_examples,
        "checks_total": {key: int(value) for key, value in sorted(checks_total.items())},
        "check_failed_routes": {key: int(value) for key, value in sorted(check_failed_routes.items())},
        "endpoints_checked": endpoints_checked,
        "route_errors": route_error_records,
    }
    return geometry


# ---------------------------------------------------------------------------
# crossing enumeration / pair audit (independent validator kernel)
# ---------------------------------------------------------------------------
def compute_pair_audit(routed, config, validator=None):
    """Recompute crossings + pair violations with the independent validator."""
    validator = validator or _validator()
    prepared = []
    skipped = []
    for record in routed:
        primitives = record.get("primitives") or []
        if not primitives:
            skipped.append(record.get("route_id"))
            continue
        try:
            prepared.append(validator.prepare_route(
                primitives, route_id=record.get("route_id")))
        except Exception as exc:  # noqa: BLE001 - report, never crash silently
            skipped.append(record.get("route_id"))
            del exc
    requested = config.get("crossing_policy")
    policy, policy_note = _choose_policy(validator, requested)
    started = time.perf_counter()
    result = validator.audit_route_pairs(prepared, policy=policy)
    elapsed = time.perf_counter() - started
    crossings = result.get("crossings") or []
    histogram = OrderedDict((label, 0) for label, _, _ in HIST_BINS)
    small_angle = 0
    small_angle_5 = 0
    for crossing in crossings:
        angle = float(crossing.get("angle_deg") or 0.0)
        if angle < SMALL_ANGLE_DEG:
            small_angle += 1
        if angle < SMALL_ANGLE_5DEG:
            small_angle_5 += 1
        for label, low, high in HIST_BINS:
            if low <= angle < high:
                histogram[label] += 1
                break
    cells = Counter()
    for crossing in crossings:
        ix = int(math.floor(float(crossing["x"]) / CROSSING_GRID_MM))
        iy = int(math.floor(float(crossing["y"]) / CROSSING_GRID_MM))
        cells[(ix, iy)] += 1
    densest = [{"x_min_mm": ix * CROSSING_GRID_MM,
                "y_min_mm": iy * CROSSING_GRID_MM,
                "count": int(count)} for (ix, iy), count in cells.most_common(10)]
    return {
        "crossing_count": int(result.get("crossing_count") or 0),
        "crossing_pair_count": int(result.get("crossing_pair_count") or 0),
        "crossings": crossings,
        "crossing_angle_histogram": dict(histogram),
        "small_angle_threshold_deg": SMALL_ANGLE_DEG,
        "small_angle_crossing_count": int(small_angle),
        "small_angle_5deg_threshold_deg": SMALL_ANGLE_5DEG,
        "small_angle_5deg_crossing_count": int(small_angle_5),
        "crossing_grid_mm": CROSSING_GRID_MM,
        "crossing_grid_peak": int(densest[0]["count"]) if densest else 0,
        "crossing_grid_peak_cell": ([densest[0]["x_min_mm"], densest[0]["y_min_mm"]]
                                    if densest else None),
        "densest_crossing_cells": densest,
        "candidate_pair_count": int(result.get("candidate_pair_count") or 0),
        "spacing_violation_pairs": int(result.get("spacing_violation_pairs") or 0),
        "overlap_pairs": int(result.get("overlap_pairs") or 0),
        "touch_pairs": int(result.get("touch_pairs") or 0),
        "crossing_window_overlap_pairs": int(
            result.get("crossing_window_overlap_pairs",
                       result.get("crossing_zone_overlap_pairs")) or 0),
        "violation_pair_count": int(result.get("violation_pair_count") or 0),
        "min_non_crossing_centerline_mm": result.get("min_non_crossing_centerline_mm"),
        "violations": result.get("violations") or [],
        "policy_used": policy,
        "policy_requested": requested,
        "policy_note": policy_note,
        "prepared_route_count": len(prepared),
        "skipped_route_ids": skipped,
        "recompute_runtime_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# regularity: nearest non-crossing centreline gap + track bands
# ---------------------------------------------------------------------------
_GAP_PADS = (0.05, 0.18, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 160.0)


def _candidate_pairs(prepared, pad):
    validator = _validator()
    try:
        return validator._candidate_pairs(prepared, pad)  # noqa: SLF001
    except AttributeError:
        pairs = []
        for index in range(len(prepared) - 1):
            x0, y0, x1, y1 = prepared[index].bbox
            for other in range(index + 1, len(prepared)):
                xa, ya, xb, yb = prepared[other].bbox
                dx = max(x0 - xb, xa - x1, 0.0)
                dy = max(y0 - yb, ya - y1, 0.0)
                if math.hypot(dx, dy) <= pad:
                    pairs.append((index, other))
        return pairs


def _pair_min_gap(first, second, cap):
    """Minimum exact centreline distance excluding intersecting prim pairs."""
    validator = _validator()
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
                if validator._prims_intersect(prim_a, prim_b):  # noqa: SLF001
                    continue
                distance = validator._exact_distance(  # noqa: SLF001
                    prim_a, prim_b, bbox_disjoint=(dx > 0.0 or dy > 0.0))
            except Exception:  # noqa: BLE001 - a predicate failure is not a gap
                continue
            if distance < best:
                best = distance
    return best


def _route_gaps(routed, config):
    """Per-route nearest non-crossing centreline distance to another route."""
    validator = _validator()
    prepared = []
    ids = []
    for record in routed:
        primitives = record.get("primitives") or []
        if not primitives:
            continue
        try:
            prepared.append(validator.prepare_route(
                primitives, route_id=record.get("route_id")))
            ids.append(record.get("route_id"))
        except Exception:  # noqa: BLE001 - routes without geometry are skipped
            continue
    count = len(prepared)
    infinite = float("inf")
    best = [infinite] * count
    remaining = set(range(count))
    processed = set()
    for pad in _GAP_PADS:
        if not remaining:
            break
        pairs = _candidate_pairs(prepared, pad)
        fresh = [(first, second) for first, second in pairs
                 if (first, second) not in processed
                 and (first in remaining or second in remaining)]
        processed.update(fresh)
        for first, second in fresh:
            cap = best[first] if best[first] < best[second] else best[second]
            distance = _pair_min_gap(prepared[first], prepared[second], cap)
            if distance < best[first]:
                best[first] = distance
            if distance < best[second]:
                best[second] = distance
        # a route is final once every yet-unseen pair has a bounding-box
        # distance above ``pad``, i.e. its exact distance can only be larger.
        for index in list(remaining):
            if best[index] <= pad:
                remaining.discard(index)
    values = [(route_id, value) for route_id, value in zip(ids, best)
              if value < infinite]
    distances = [value for _, value in values]
    unresolved = [route_id for route_id, value in zip(ids, best) if value == infinite]

    def _mean(items):
        return (sum(items) / len(items)) if items else None

    distances_sorted = sorted(distances)
    median = None
    if distances_sorted:
        middle = len(distances_sorted) // 2
        if len(distances_sorted) % 2:
            median = distances_sorted[middle]
        else:
            median = 0.5 * (distances_sorted[middle - 1] + distances_sorted[middle])
    per_route = {str(route_id): _round(value) for route_id, value in values}
    return {
        "mean_min_gap_mm": _mean(distances),
        "median_min_gap_mm": median,
        "min_min_gap_mm": min(distances) if distances else None,
        "max_min_gap_mm": max(distances) if distances else None,
        "routes_with_min_gap": len(values),
        "unresolved_route_ids": unresolved,
        "per_route_min_gap_mm": per_route,
        "definition": ("per-route minimum exact centreline distance to any "
                       "non-crossing primitive of another routed route; mean over "
                       "routes with at least one non-crossing neighbour"),
    }


def _track_band_score(routed, config):
    """Regularity of parallel line separation at integer multiples of the pitch."""
    validator = _validator()
    pitch = float(config.get("virtual_pitch_mm") or CLEARANCE_MM)
    band_max = 9.0 * pitch
    tolerance = 0.1 * pitch
    prepared = []
    for record in routed:
        primitives = record.get("primitives") or []
        if not primitives:
            continue
        try:
            prepared.append(validator.prepare_route(
                primitives, route_id=record.get("route_id")))
        except Exception:  # noqa: BLE001 - skip unusable geometry
            continue
    lines = []
    for route in prepared:
        entries = []
        for prim in route.prims:
            if prim.kind != "line":
                continue
            dx = prim.p1[0] - prim.p0[0]
            dy = prim.p1[1] - prim.p0[1]
            if abs(dy) <= 1e-9:
                entries.append(("h", prim.p0[1],
                                min(prim.p0[0], prim.p1[0]),
                                max(prim.p0[0], prim.p1[0])))
            elif abs(dx) <= 1e-9:
                entries.append(("v", prim.p0[0],
                                min(prim.p0[1], prim.p1[1]),
                                max(prim.p0[1], prim.p1[1])))
        lines.append(entries)
    eligible = 0
    aligned = 0
    pairs_checked = 0
    for first, second in _candidate_pairs(prepared, band_max):
        pairs_checked += 1
        for orientation_a, coord_a, lo_a, hi_a in lines[first]:
            for orientation_b, coord_b, lo_b, hi_b in lines[second]:
                if orientation_a != orientation_b:
                    continue
                overlap = min(hi_a, hi_b) - max(lo_a, lo_b)
                if overlap <= 0.0:
                    continue
                separation = abs(coord_a - coord_b)
                if separation <= 1e-12 or separation > band_max:
                    continue
                eligible += 1
                multiple = separation / pitch
                if abs(multiple - round(multiple)) * pitch <= tolerance:
                    aligned += 1
    score = (aligned / eligible) if eligible else None
    return {
        "track_band_score": score,
        "track_band_pitch_mm": pitch,
        "track_band_tolerance_mm": tolerance,
        "track_band_max_separation_mm": band_max,
        "track_band_eligible_pairs": eligible,
        "track_band_aligned_pairs": aligned,
        "track_band_route_pairs_checked": pairs_checked,
        "definition": ("fraction of axis-parallel line pairs on different routes "
                       "(overlapping projections, separation <= 9 x pitch) whose "
                       "perpendicular separation is within 10% of an integer "
                       "multiple of the 0.175 mm clearance pitch"),
    }


# ---------------------------------------------------------------------------
# symmetry
# ---------------------------------------------------------------------------
def _build_route_map(routes, endpoints, matrix, offset):
    """Fallback route-map kernel (same rule as abcd/connectivity.py)."""
    endpoint_map = {}
    tol = 1e-6
    coordinate_lookup = {}
    for endpoint_id, endpoint in endpoints.items():
        xy = endpoint.get("routing_xy")
        if not xy:
            continue
        coordinate_lookup[(round(float(xy[0]), 6), round(float(xy[1]), 6))] = endpoint_id
    a, b = matrix[0]
    c, d = matrix[1]
    tx, ty = offset
    for endpoint_id, endpoint in endpoints.items():
        xy = endpoint.get("routing_xy")
        if not xy:
            continue
        x = a * float(xy[0]) + b * float(xy[1]) + tx
        y = c * float(xy[0]) + d * float(xy[1]) + ty
        key = (round(x, 6), round(y, 6))
        mapped = coordinate_lookup.get(key)
        if mapped is None:  # tolerate a 1e-6 snap difference
            for candidate, candidate_id in coordinate_lookup.items():
                if (abs(candidate[0] - x) <= tol and abs(candidate[1] - y) <= tol):
                    mapped = candidate_id
                    break
        if mapped is not None:
            endpoint_map[endpoint_id] = mapped
    identity = {(route.get("source_endpoint"), route.get("target_endpoint")):
                route.get("route_id") for route in routes}
    route_map = {}
    orientation = {"direct": 0, "reversed": 0}
    for route in routes:
        source = endpoint_map.get(route.get("source_endpoint"))
        target = endpoint_map.get(route.get("target_endpoint"))
        mapped = None
        direction = None
        if source is not None and target is not None:
            found = identity.get((source, target))
            if found is not None:
                mapped = found
                direction = "direct"
            else:
                found = identity.get((target, source))
                if found is not None:
                    mapped = found
                    direction = "reversed"
        route_map[route.get("route_id")] = mapped
        if direction:
            orientation[direction] += 1
    mapped_count = sum(1 for value in route_map.values() if value is not None)
    return {
        "route_map": route_map,
        "mapped_route_count": mapped_count,
        "route_map_complete": mapped_count == len(routes),
        "orientation_counts": orientation,
        "fixed_point_count": sum(1 for key, value in route_map.items()
                                 if value is not None and value == key),
    }


def _fallback_symmetry_maps(routes, endpoints):
    transforms = []
    for name, (matrix, offset) in FALLBACK_TRANSFORMS.items():
        entry = {"name": name, "matrix": [list(matrix[0]), list(matrix[1])],
                 "offset": list(offset), "description": "local fallback isometry"}
        entry.update(_build_route_map(routes, endpoints, matrix, offset))
        transforms.append(entry)
    return {"transforms": transforms,
            "source": "four_side_1024.abcd.metrics local fallback",
            "n_routes": len(routes), "n_endpoints": len(endpoints),
            "tolerance_mm": 1e-6}


def _symmetry_maps(routes, endpoints):
    """Prefer ``abcd/connectivity.symmetry_maps`` (owned by teammate connectivity)."""
    try:
        from .connectivity import symmetry_maps  # type: ignore
    except Exception as exc:  # noqa: BLE001 - fall back, but record why
        return _fallback_symmetry_maps(routes, endpoints), \
            f"fallback ({type(exc).__name__}: {exc})"
    try:
        result = symmetry_maps(routes, endpoints)
        if not isinstance(result, dict) or not result.get("transforms"):
            raise ValueError("symmetry_maps returned no transforms")
        result = dict(result)
        result.setdefault("source", "four_side_1024.abcd.connectivity.symmetry_maps")
        return result, None
    except Exception as exc:  # noqa: BLE001 - never let a helper break metrics
        return _fallback_symmetry_maps(routes, endpoints), \
            f"fallback ({type(exc).__name__}: {exc})"


def _transform_primitives(primitives, matrix, offset):
    """Analytically transform a D56 primitive list (isometry, mm)."""
    (a, b), (c, d) = matrix
    tx, ty = offset
    determinant = a * d - b * c
    transformed = []
    for primitive in primitives:
        item = dict(primitive)
        p0 = primitive.get("p0")
        p1 = primitive.get("p1")
        if p0 is not None:
            item["p0"] = [a * p0[0] + b * p0[1] + tx, c * p0[0] + d * p0[1] + ty]
        if p1 is not None:
            item["p1"] = [a * p1[0] + b * p1[1] + tx, c * p1[0] + d * p1[1] + ty]
        if primitive.get("kind") == "arc":
            center = primitive.get("center")
            if center is not None:
                item["center"] = [a * center[0] + b * center[1] + tx,
                                  c * center[0] + d * center[1] + ty]
            angle = float(primitive.get("start_angle") or 0.0)
            cosine, sine = math.cos(angle), math.sin(angle)
            ux = a * cosine + b * sine
            uy = c * cosine + d * sine
            item["start_angle"] = math.atan2(uy, ux)
            sweep = primitive.get("sweep")
            if sweep is not None:
                item["sweep"] = sweep if determinant > 0 else -sweep
        transformed.append(item)
    return transformed


def _reverse_primitives(primitives):
    reversed_items = []
    for primitive in reversed(primitives):
        item = dict(primitive)
        item["p0"] = primitive.get("p1")
        item["p1"] = primitive.get("p0")
        if primitive.get("kind") == "arc":
            start = primitive.get("start_angle")
            sweep = primitive.get("sweep")
            if start is not None and sweep is not None:
                item["start_angle"] = start + sweep
                item["sweep"] = -sweep
        reversed_items.append(item)
    return reversed_items


def _primitive_deviation(first, second):
    """Max primitive-wise mismatch (endpoints, arc centre/radius) in mm."""
    if len(first) != len(second):
        return float("inf")
    worst = 0.0
    for item_a, item_b in zip(first, second):
        if item_a.get("kind") != item_b.get("kind"):
            return float("inf")
        for key in ("p0", "p1"):
            point_a = item_a.get(key)
            point_b = item_b.get(key)
            if point_a is None or point_b is None:
                return float("inf")
            worst = max(worst, math.hypot(point_a[0] - point_b[0],
                                          point_a[1] - point_b[1]))
        if item_a.get("kind") == "arc":
            center_a = item_a.get("center")
            center_b = item_b.get("center")
            if center_a is None or center_b is None:
                return float("inf")
            worst = max(worst, math.hypot(center_a[0] - center_b[0],
                                          center_a[1] - center_b[1]))
            radius_a = _number(item_a.get("radius"))
            radius_b = _number(item_b.get("radius"))
            if radius_a is None or radius_b is None:
                return float("inf")
            worst = max(worst, abs(radius_a - radius_b))
    return worst


def _shape_deviation(primitives_a, primitives_b, matrix, offset):
    """Transform ``b`` and compare with ``a`` in both traversal directions."""
    if not primitives_a or not primitives_b:
        return float("inf")
    transformed = _transform_primitives(primitives_b, matrix, offset)
    direct = _primitive_deviation(transformed, primitives_a)
    reversed_deviation = _primitive_deviation(transformed,
                                              _reverse_primitives(primitives_a))
    return min(direct, reversed_deviation)


def _normalise_transforms(symmetry_result):
    transforms = OrderedDict()
    raw = symmetry_result.get("transforms") or []
    if isinstance(raw, dict):
        raw = list(raw.values())
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        matrix = entry.get("matrix")
        offset = entry.get("offset")
        if name is None or matrix is None or offset is None:
            continue
        try:
            (a, b), (c, d) = matrix
            tx, ty = offset
            matrix = ((float(a), float(b)), (float(c), float(d)))
            offset = (float(tx), float(ty))
        except (TypeError, ValueError):
            continue
        route_map = entry.get("route_map") or {}
        normalised_map = {}
        for key, value in route_map.items():
            try:
                key_int = int(key)
            except (TypeError, ValueError):
                continue
            if value is None:
                normalised_map[key_int] = None
            else:
                try:
                    normalised_map[key_int] = int(value)
                except (TypeError, ValueError):
                    normalised_map[key_int] = None
        transforms[name] = {
            "name": name,
            "matrix": [list(matrix[0]), list(matrix[1])],
            "offset": list(offset),
            "route_map": normalised_map,
            "description": entry.get("description"),
            "mapped_route_count": entry.get("mapped_route_count",
                                            sum(1 for v in normalised_map.values()
                                                if v is not None)),
            "route_map_complete": entry.get("route_map_complete"),
            "fixed_point_count": entry.get("fixed_point_count"),
            "orientation_counts": entry.get("orientation_counts"),
            "topology_invariant": entry.get("topology_invariant"),
            "channel_map_consistent": entry.get("channel_map_consistent"),
            "extra": {key: value for key, value in entry.items()
                      if key not in ("name", "matrix", "offset", "route_map",
                                     "description")},
        }
    return transforms


def _transform_metric(transforms, name, records_by_id, routed_ids):
    entry = transforms.get(name)
    if entry is None:
        for alias in SYMMETRY_ALIASES.get(name, ()):
            if alias in transforms:
                entry = transforms[alias]
                break
    if entry is None:
        return None
    route_map = entry.get("route_map") or {}
    pairs = set()
    for key, value in route_map.items():
        if value is None:
            continue
        pairs.add((min(key, value), max(key, value)))
    routed_pairs = 0
    shape_matches = 0
    shape_checked = 0
    deviation_max = None
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
        deviation = _shape_deviation(primitives_a, primitives_b,
                                     entry["matrix"], entry["offset"])
        if deviation_max is None or deviation > deviation_max:
            deviation_max = deviation
        if deviation <= SHAPE_MATCH_MM:
            shape_matches += 1
    pair_count = len(pairs)
    result = {
        "transform": name,
        "source_name": entry.get("name"),
        "matrix": entry.get("matrix"),
        "offset": entry.get("offset"),
        "description": entry.get("description"),
        "pair_count": pair_count,
        "routed_pair_count": routed_pairs,
        "routed_pair_fraction": (routed_pairs / pair_count) if pair_count else None,
        "shape_checked_pair_count": shape_checked,
        "shape_match_count": shape_matches,
        "shape_match_fraction": (shape_matches / shape_checked) if shape_checked else None,
        "max_shape_deviation_mm": deviation_max,
        "mapped_route_count": entry.get("mapped_route_count"),
        "route_map_complete": entry.get("route_map_complete"),
        "topology_invariant": entry.get("topology_invariant"),
        "fixed_point_count": entry.get("fixed_point_count"),
        "orientation_counts": entry.get("orientation_counts"),
        "definition": {
            "routed_pair_fraction": ("fraction of topology counterpart pairs "
                                     "(unordered, fixed points included) where both "
                                     "routes are routed"),
            "shape_match_fraction": ("fraction of both-routed counterpart pairs whose "
                                     f"transformed path agrees with the other path "
                                     f"within {SHAPE_MATCH_MM} mm primitive-wise "
                                     "(endpoints / arc centre / radius; traversal "
                                     "direction agnostic)"),
        },
    }
    extras = entry.get("extra") or {}
    for key in ("channel_map_consistent", "endpoint_map_complete",
                "connector_map_complete", "connector_pair_multiset_preserved"):
        if key in extras:
            result[key] = extras[key]
    return result


def compute_symmetry(records, endpoints, config):
    if not endpoints:
        return {"available": False,
                "reason": "endpoint table unavailable; symmetry metrics not computed",
                "source": None}
    symmetry_source, fallback_reason = _symmetry_maps(records, endpoints)
    transforms = _normalise_transforms(symmetry_source)
    records_by_id = {record.get("route_id"): record for record in records}
    routed_ids = {record.get("route_id") for record in records
                  if _status(record) == "routed"}
    spec = OrderedDict()
    for name in SYMMETRY_SPEC_NAMES:
        metric = _transform_metric(transforms, name, records_by_id, routed_ids)
        if metric is not None:
            spec[name] = metric
    extras = OrderedDict()
    spec_source_names = {name}
    for spec_name in SYMMETRY_SPEC_NAMES:
        spec_source_names.update(SYMMETRY_ALIASES.get(spec_name, ()))
    for name in transforms:
        if name in spec_source_names:
            continue
        metric = _transform_metric(transforms, name, records_by_id, routed_ids)
        if metric is not None:
            extras[name] = metric
    result = OrderedDict()
    result["available"] = bool(spec)
    result["source"] = symmetry_source.get("source")
    result["fallback_reason"] = fallback_reason
    result["shape_match_threshold_mm"] = SHAPE_MATCH_MM
    result["spec_transform_names"] = list(SYMMETRY_SPEC_NAMES)
    result["n_routes"] = symmetry_source.get("n_routes", len(records))
    result["n_endpoints"] = symmetry_source.get("n_endpoints", len(endpoints))
    for name, metric in spec.items():
        result[name] = metric
    result["extra_transforms"] = extras
    result["all_transforms"] = OrderedDict(
        (name, {key: value for key, value in entry.items()
                if key != "route_map"})
        for name, entry in transforms.items())
    result["note"] = ("routed_pair_fraction / shape_match_fraction follow SPEC §5; "
                      "'diag' == connectivity.py 'diag_main'.  Only transforms that "
                      "preserve the topology-level connection set yield non-trivial "
                      "counterpart pairs - that asymmetry is a topological result, "
                      "not a routing defect.")
    return result


# ---------------------------------------------------------------------------
# authoritative audit merge
# ---------------------------------------------------------------------------
_AUDIT_FIELD_ALIASES = {
    "spacing_violation_pairs": ("spacing_violation_pairs", "spacing_pairs"),
    "overlap_pairs": ("overlap_pairs",),
    "touch_pairs": ("touch_pairs",),
    "crossing_window_overlap_pairs": ("crossing_window_overlap_pairs",
                                      "crossing_zone_overlap_pairs"),
    "violation_pair_count": ("violation_pair_count",),
    "self_intersections": ("self_intersections",),
    "self_overlaps": ("self_overlaps",),
    "radius_violations": ("radius_violations",),
    "boundary_violations": ("boundary_violations",),
    "diagonal_line_violations": ("diagonal_line_violations",),
    "free_arc_violations": ("free_arc_violations",
                            "free_or_short_s_arc_violations"),
    "crossing_count": ("crossing_count",),
    "crossing_angle_histogram": ("crossing_angle_histogram",),
    "small_angle_crossing_count": ("small_angle_crossing_count",),
}


def load_audit(path, label):
    """Load one independent audit JSON and extract the SPEC counters."""
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"audit file {path} is not a JSON object")
    values = {}
    for field, aliases in _AUDIT_FIELD_ALIASES.items():
        for alias in aliases:
            if alias in payload and payload[alias] is not None:
                values[field] = payload[alias]
                break
    report = {
        "file": str(path),
        "label": label,
        "policy": _first(payload, ("policy_used", "policy", "acceptance_policy")),
        "passed": payload.get("passed"),
        "errors": len(payload.get("errors") or []),
        "warnings": len(payload.get("warnings") or []),
        "violations": len(payload.get("violations") or []),
        "candidate_pair_count": _first(payload, ("candidate_pair_count",)),
        "crossing_pair_count": _first(payload, ("crossing_pair_count",)),
        "runtime_seconds": _first(payload, ("runtime_seconds",
                                            "pair_audit_runtime_seconds")),
        "routed_count": _first(payload, ("routed_count",)),
        "route_count": _first(payload, ("route_count",)),
        "min_non_crossing_centerline_mm": _first(
            payload, ("min_non_crossing_centerline_mm",)),
        "values": values,
        "sha256": _sha256(path),
    }
    return report


def _auto_audit_paths(routes_path, run_dir):
    """Default audit candidates: strict first, then the historical audit file."""
    candidates = []
    base = Path(run_dir) if run_dir is not None else Path(routes_path).parent
    for name, label in (("audit_strict.json", "audit_strict"),
                        ("independent_audit.json", "independent_audit")):
        path = base / name
        if path.exists():
            candidates.append((path, label))
    return candidates


def _audit_label(path):
    """Label an audit file by its own name, never by how it was requested."""
    name = Path(path).name.lower()
    if name.startswith("audit_strict") or "strict" in name:
        return "audit_strict"
    if name.startswith("audit_exact") or "exact" in name:
        return "audit_exact"
    if name.startswith("audit_legacy") or "legacy" in name:
        return "audit_legacy"
    if "independent_audit" in name:
        return "independent_audit"
    return Path(path).stem


def _audit_is_stale(audit_path, routes_path, tolerance_seconds=0.5):
    """An audit older than routes.json cannot describe the current solution."""
    try:
        audit_mtime = Path(audit_path).stat().st_mtime
        routes_mtime = Path(routes_path).stat().st_mtime
    except OSError:
        return False
    return audit_mtime < routes_mtime - tolerance_seconds


def _failed_check_count(geometry, check_name):
    """Number of routed routes failing one independent single-route check."""
    if check_name not in (geometry.get("checks_total") or {}):
        return None
    return int((geometry.get("check_failed_routes") or {}).get(check_name, 0))


# ---------------------------------------------------------------------------
# run metadata (candidate evaluations / runtime / budget)
# ---------------------------------------------------------------------------
_EVAL_KEYS = ("candidate_evaluations", "total_candidate_evaluations",
              "evaluations", "eval_count", "evaluated_candidates",
              "candidates_evaluated")
_RUNTIME_KEYS = ("total_runtime_seconds", "runtime_seconds", "wall_clock_seconds",
                 "elapsed_seconds", "search_runtime_seconds",
                 "routing_runtime_seconds", "run_runtime_seconds")
_MEMORY_KEYS = ("peak_memory_mb", "max_rss_mb", "peak_rss_mb", "memory_mb")
_LOG_PATTERN = re.compile(
    r"(?i)\b(total_runtime_seconds|runtime_seconds|wall_clock_seconds|"
    r"elapsed_seconds|candidate_evaluations|peak_memory_mb)\b\s*[=:]\s*"
    r"([0-9]+(?:\.[0-9]+)?)")
_LOG_EVALS_PATTERN = re.compile(r"(?i)\b(?:evals|evaluations)\s*=\s*([0-9]+)")
_LOG_RUNTIME_PATTERN = re.compile(
    r"(?i)\bruntime\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*s")


def _extract_run_metadata(routes_meta, config_payload, run_dir, routed, failed):
    sections = []
    if isinstance(routes_meta.get("statistics"), dict):
        sections.append(("routes_json.statistics", routes_meta["statistics"]))
    algorithm = routes_meta.get("algorithm") or routes_meta.get("algorithm_detail")
    if isinstance(algorithm, dict):
        sections.append(("routes_json.algorithm_detail", algorithm))
    if isinstance(routes_meta.get("run_info"), dict):
        sections.append(("routes_json.run_info", routes_meta["run_info"]))
    if isinstance(config_payload, dict):
        sections.append(("config_json", config_payload))
        for key in ("budget_used", "main_pass", "run_info", "budget"):
            if isinstance(config_payload.get(key), dict):
                sections.append((f"config_json.{key}", config_payload[key]))
    nested = routes_meta.get("config")
    if isinstance(nested, dict):
        sections.append(("routes_json.config", nested))

    def _pick(keys):
        for source_name, section in sections:
            for key in keys:
                if isinstance(section, dict) and section.get(key) is not None:
                    number = _number(section[key])
                    if number is not None:
                        if number.is_integer() and key not in (
                                "runtime_seconds", "total_runtime_seconds",
                                "wall_clock_seconds", "elapsed_seconds",
                                "search_runtime_seconds"):
                            number = int(number)
                        return number, f"{source_name}.{key}"
        return None, None

    evaluations, evaluations_source = _pick(_EVAL_KEYS)
    runtime, runtime_source = _pick(_RUNTIME_KEYS)
    memory, memory_source = _pick(_MEMORY_KEYS)
    pair_checks, pair_checks_source = _pick(("pair_checks", "pair_checks_count"))
    budget, budget_source = _pick(("candidate_evaluation_budget", "eval_budget",
                                   "evaluation_budget", "candidate_budget"))
    time_budget, time_budget_source = _pick(("time_budget_seconds", "time_budget",
                                             "time_limit_seconds"))
    log_values = {}
    log_path = Path(run_dir) / "run.log" if run_dir is not None else None
    if log_path is not None and log_path.exists():
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
            for match in _LOG_PATTERN.finditer(text):
                log_values[match.group(1).lower()] = float(match.group(2))
            eval_matches = _LOG_EVALS_PATTERN.findall(text)
            if eval_matches:
                log_values["candidate_evaluations"] = float(eval_matches[-1])
            runtime_matches = _LOG_RUNTIME_PATTERN.findall(text)
            if runtime_matches:
                log_values["runtime_seconds"] = float(runtime_matches[-1])
        except OSError:
            log_values = {}
    if runtime is None:
        for key in ("total_runtime_seconds", "runtime_seconds",
                    "wall_clock_seconds", "elapsed_seconds"):
            if key in log_values:
                runtime = log_values[key]
                runtime_source = f"run.log:{key}"
                break
    if evaluations is None and "candidate_evaluations" in log_values:
        evaluations = log_values["candidate_evaluations"]
        evaluations_source = "run.log:candidate_evaluations"
    if memory is None and "peak_memory_mb" in log_values:
        memory = log_values["peak_memory_mb"]
        memory_source = "run.log:peak_memory_mb"
    evaluated_sum = 0
    evaluated_routes = 0
    for record in list(routed) + list(failed):
        value = _number(record.get("evaluated"))
        if value is not None:
            evaluated_sum += value
            evaluated_routes += 1
    failed_evaluated_sum = 0
    failed_evaluated_routes = 0
    for record in failed:
        value = _number(record.get("evaluated"))
        if value is not None:
            failed_evaluated_sum += value
            failed_evaluated_routes += 1
    budget_exhausted = _first(routes_meta, ("budget_exhausted",))
    if budget_exhausted is None and isinstance(routes_meta.get("statistics"), dict):
        budget_exhausted = routes_meta["statistics"].get("budget_exhausted")
    if budget_exhausted is None and isinstance(config_payload, dict):
        budget_exhausted = config_payload.get("budget_exhausted")
    result = {
        "candidate_evaluations": evaluations,
        "candidate_evaluations_source": evaluations_source,
        "candidate_evaluations_route_sum": evaluated_sum,
        "candidate_evaluations_route_sum_note": (
            "sum of per-route 'evaluated' counters (successful routes often omit "
            "the counter); independent of the router's self-reported total"),
        "candidate_evaluations_failed_route_sum": failed_evaluated_sum,
        "evaluated_route_records": evaluated_routes,
        "runtime_seconds": runtime,
        "runtime_seconds_source": runtime_source,
        "pair_checks": pair_checks,
        "pair_checks_source": pair_checks_source,
        "peak_memory_mb": memory,
        "peak_memory_mb_source": memory_source,
        "eval_budget": budget,
        "eval_budget_source": budget_source,
        "time_budget_seconds": time_budget,
        "time_budget_seconds_source": time_budget_source,
        "budget_exhausted": budget_exhausted,
        "run_log_values": log_values,
    }
    if evaluations is not None and runtime not in (None, 0):
        result["evals_per_second"] = evaluations / runtime
    elif evaluated_sum and runtime not in (None, 0):
        result["evals_per_second"] = evaluated_sum / runtime
    else:
        result["evals_per_second"] = None
    return result


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def _counts_by(records, key_function):
    counts = OrderedDict()
    for record in records:
        key = key_function(record)
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_statistics(routes_path, config_path=None, out_path=None, audit_path=None,
                     audit_exact_path=None, audit_legacy_path=None,
                     run_dir=None, experiment=None, skip_gaps=False,
                     skip_track_band=False, skip_pair_audit=False,
                     skip_symmetry=False, quiet=False):
    """Recompute the full SPEC §5 statistics for one run and write the JSON."""
    routes_path = Path(routes_path)
    if run_dir is None:
        run_dir = routes_path.parent
    else:
        run_dir = Path(run_dir)
    if config_path is None:
        candidate = run_dir / "config.json"
        config_path = candidate if candidate.exists() else None
    else:
        config_path = Path(config_path)
    if out_path is None:
        out_path = run_dir / "statistics.json"
    else:
        out_path = Path(out_path)
    started = time.perf_counter()
    routes_payload = _load_json(routes_path)
    records, routes_meta = _split_records(routes_payload)
    config_payload = _load_json(config_path) if config_path else None
    config = _derived_config(routes_meta, config_payload, run_dir)
    if experiment is None:
        experiment = config.get("experiment")
    endpoint_bundle = _endpoint_bundle(config)
    endpoints = endpoint_bundle.get("endpoints")
    connectors = endpoint_bundle.get("connectors")

    routed = [record for record in records if _status(record) == "routed"]
    failed = [record for record in records if _status(record) != "routed"]
    routed_ids = {record.get("route_id") for record in routed}
    failed_ids = {record.get("route_id") for record in failed}

    # audit files (primary strict + optional sensitivity arms); an audit that
    # predates the current routes.json is ignored instead of silently merged.
    audit_reports = []
    stale_audits = []
    if audit_path is not None:
        audit_path = Path(audit_path)
        if _audit_is_stale(audit_path, routes_path):
            stale_audits.append(str(audit_path))
        else:
            audit_reports.append(load_audit(audit_path, _audit_label(audit_path)))
    else:
        for path, label in _auto_audit_paths(routes_path, run_dir):
            if _audit_is_stale(path, routes_path):
                stale_audits.append(str(path))
                continue
            audit_reports.append(load_audit(path, label))
    sensitivity = {}
    if audit_exact_path is None and run_dir is not None:
        candidate = Path(run_dir) / "audit_exact.json"
        if candidate.exists():
            audit_exact_path = candidate
    if audit_legacy_path is None and run_dir is not None:
        candidate = Path(run_dir) / "audit_legacy.json"
        if candidate.exists():
            audit_legacy_path = candidate
    if audit_exact_path is not None:
        audit_exact_path = Path(audit_exact_path)
        if _audit_is_stale(audit_exact_path, routes_path):
            stale_audits.append(str(audit_exact_path))
        else:
            sensitivity["exact"] = load_audit(audit_exact_path,
                                              _audit_label(audit_exact_path))
    if audit_legacy_path is not None:
        audit_legacy_path = Path(audit_legacy_path)
        if _audit_is_stale(audit_legacy_path, routes_path):
            stale_audits.append(str(audit_legacy_path))
        else:
            sensitivity["legacy"] = load_audit(audit_legacy_path,
                                               _audit_label(audit_legacy_path))
    primary_audit = audit_reports[0] if audit_reports else None

    # per pair / per relation
    pair_success = Counter()
    pair_total = Counter()
    relation_success = Counter()
    relation_total = Counter()
    for record in records:
        pair = _pair_of(record)
        relation = _relation_of(record)
        if pair in PAIR_RELATION:
            pair_total[pair] += 1
        if relation in RELATION_PAIRS:
            relation_total[relation] += 1
        if _status(record) == "routed":
            if pair in PAIR_RELATION:
                pair_success[pair] += 1
            if relation in RELATION_PAIRS:
                relation_success[relation] += 1
    by_pair = OrderedDict()
    for pair in PAIR_ORDER:
        total = pair_total.get(pair, 0)
        success = pair_success.get(pair, 0)
        by_pair[pair] = {
            "relation": PAIR_RELATION.get(pair),
            "success": success,
            "routed": success,
            "failed": total - success,
            "total": total,
            "routing_rate": (success / total) if total else None,
        }
    by_relation = OrderedDict()
    for relation, pairs in RELATION_PAIRS.items():
        total = relation_total.get(relation, 0)
        success = relation_success.get(relation, 0)
        by_relation[relation] = {
            "pairs": list(pairs),
            "success": success,
            "routed": success,
            "failed": total - success,
            "total": total,
            "routing_rate": (success / total) if total else None,
        }
    failure_reason_counts = Counter()
    for record in failed:
        failure_reason_counts[str(record.get("reason") or "unknown_failure")] += 1
    routed_count = len(routed)
    unrouted_count = len(failed)

    geometry = compute_route_geometry(routed, config, endpoints)

    if skip_pair_audit:
        pair_audit = None
    else:
        pair_audit = compute_pair_audit(routed, config)

    gaps = None if skip_gaps else _route_gaps(routed, config)
    track_band = None if skip_track_band else _track_band_score(routed, config)
    symmetry = None
    if not skip_symmetry:
        symmetry = compute_symmetry(records, endpoints, config)

    # merge authoritative audit counters (SPEC §2.2/§5)
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
        "crossing_window_overlap_pairs": (pair_audit["crossing_window_overlap_pairs"]
                                          if pair_audit else None),
        "violation_pair_count": (pair_audit["violation_pair_count"]
                                 if pair_audit else None),
        "self_intersections": _failed_check_count(geometry,
                                                  "self_intersection_free"),
        "self_overlaps": _failed_check_count(geometry, "self_overlap_free"),
        "radius_violations": _failed_check_count(geometry, "radius_fixed"),
        "boundary_violations": _failed_check_count(geometry, "board_bounds"),
        "diagonal_line_violations": _failed_check_count(geometry,
                                                        "orthogonal_lines"),
        "free_arc_violations": _failed_check_count(geometry, "d56_arc_family"),
    }
    audit_values = primary_audit.get("values", {}) if primary_audit else {}
    merged = OrderedDict()
    sources = OrderedDict()
    audit_fields = ("crossing_count", "crossing_angle_histogram",
                    "small_angle_crossing_count", "spacing_violation_pairs",
                    "overlap_pairs", "touch_pairs",
                    "crossing_window_overlap_pairs", "violation_pair_count",
                    "self_intersections", "self_overlaps", "radius_violations",
                    "boundary_violations", "diagonal_line_violations",
                    "free_arc_violations")
    for field in audit_fields:
        if field in audit_values and audit_values[field] is not None:
            merged[field] = audit_values[field]
            sources[field] = (f"{primary_audit['label']}:{primary_audit['file']}")
        else:
            merged[field] = recomputed.get(field)
            sources[field] = "recomputed_from_primitives"
    crossing_count = merged["crossing_count"]
    small_angle = merged["small_angle_crossing_count"]
    if small_angle is None and pair_audit is not None:
        small_angle = pair_audit["small_angle_crossing_count"]
        sources["small_angle_crossing_count"] = "recomputed_from_primitives"
    histogram = merged.get("crossing_angle_histogram")
    if histogram is None and pair_audit is not None:
        histogram = pair_audit["crossing_angle_histogram"]
        sources["crossing_angle_histogram"] = "recomputed_from_primitives"
    grid_peak = pair_audit["crossing_grid_peak"] if pair_audit else None
    grid_peak_cell = pair_audit["crossing_grid_peak_cell"] if pair_audit else None
    densest_cells = pair_audit["densest_crossing_cells"] if pair_audit else None
    board_width, board_height = config["board_mm"]
    board_area = float(board_width) * float(board_height)
    small_angle_5 = (pair_audit["small_angle_5deg_crossing_count"]
                     if pair_audit else None)
    run_metadata = _extract_run_metadata(routes_meta, config_payload, run_dir,
                                         routed, failed)
    violation_fields = ("spacing_violation_pairs", "overlap_pairs", "touch_pairs",
                        "crossing_window_overlap_pairs", "self_intersections",
                        "self_overlaps", "radius_violations", "boundary_violations",
                        "diagonal_line_violations", "free_arc_violations")
    strict_violation_total = 0
    strict_violation_complete = True
    for field in violation_fields:
        value = merged.get(field)
        if value is None:
            strict_violation_complete = False
            continue
        strict_violation_total += int(value)

    statistics = OrderedDict()
    statistics["schema"] = SCHEMA
    statistics["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    statistics["tool"] = TOOL
    statistics["experiment"] = experiment
    statistics["topology"] = config.get("topology")
    statistics["algorithm"] = config.get("algorithm")
    statistics["strategy"] = config.get("strategy")
    statistics["run_dir"] = str(run_dir)
    statistics["source"] = {
        "routes_json": str(routes_path),
        "routes_sha256": _sha256(routes_path),
        "routes_schema": routes_meta.get("schema"),
        "config_json": str(config_path) if config_path else None,
        "endpoints_source": endpoint_bundle.get("source"),
        "endpoints_error": endpoint_bundle.get("error"),
        "audit_files": [{key: report[key] for key in
                         ("file", "label", "policy", "passed", "sha256")}
                        for report in audit_reports],
        "sensitivity_audit_files": {
            name: {key: report[key] for key in
                   ("file", "label", "policy", "passed", "sha256")}
            for name, report in sensitivity.items()},
        "stale_audits_ignored": stale_audits,
    }
    statistics["total_connections"] = TOTAL_CONNECTIONS
    statistics["connections_in_file"] = len(records)
    statistics["layer"] = LAYER
    statistics["routing_layers"] = 1
    statistics["board_mm"] = [board_width, board_height]
    statistics["width_mm"] = config["width_mm"]
    statistics["edge_gap_mm"] = config["edge_gap_mm"]
    statistics["min_centerline_clearance_mm"] = config["clearance_mm"]
    statistics["min_radius_mm"] = config["min_radius_mm"]
    statistics["sagitta_mm"] = config["sagitta_mm"]
    statistics["endpoint_mode"] = routes_meta.get("endpoint_mode")
    statistics["routed"] = routed_count
    statistics["unrouted"] = unrouted_count
    statistics["routing_rate"] = (routed_count / TOTAL_CONNECTIONS)
    statistics["success_count"] = routed_count
    statistics["failed_count"] = unrouted_count
    statistics["success_rate"] = statistics["routing_rate"]
    statistics["opposite_routing_rate"] = by_relation["opposite"]["routing_rate"]
    statistics["adjacent_routing_rate"] = by_relation["adjacent"]["routing_rate"]
    statistics["by_pair"] = by_pair
    statistics["by_relation"] = by_relation
    statistics["failure_reason_counts"] = dict(sorted(failure_reason_counts.items()))
    statistics["failed_route_ids"] = sorted(failed_ids)
    statistics["routed_route_ids_count"] = len(routed_ids)
    statistics["mean_length_mm"] = geometry["mean_length_mm"]
    statistics["max_length_mm"] = geometry["max_length_mm"]
    statistics["min_length_mm"] = geometry["min_length_mm"]
    statistics["total_length_mm"] = geometry["total_length_mm"]
    statistics["mean_bend_count"] = geometry["mean_bend_count"]
    statistics["max_bend_count"] = geometry["max_bend_count"]
    statistics["total_bends"] = geometry["total_bends"]
    statistics["mean_turns"] = geometry["mean_turns"]
    statistics["mean_straight_fraction"] = geometry["mean_straight_fraction"]
    statistics["crossing_count"] = crossing_count
    statistics["crossing_count_source"] = sources["crossing_count"]
    statistics["crossing_count_recomputed"] = recomputed["crossing_count"]
    statistics["crossing_count_density_per_mm2"] = (
        (crossing_count / board_area)
        if crossing_count is not None and board_area else None)
    statistics["crossing_angle_histogram"] = histogram
    statistics["crossing_angle_histogram_source"] = sources["crossing_angle_histogram"]
    statistics["crossing_histogram_bins_deg"] = [label for label, _, _ in HIST_BINS]
    statistics["crossing_pair_count"] = (
        (primary_audit.get("crossing_pair_count") if primary_audit else None)
        or (pair_audit["crossing_pair_count"] if pair_audit else None))
    statistics["small_angle_threshold_deg"] = SMALL_ANGLE_DEG
    statistics["small_angle_crossing_count"] = small_angle
    statistics["small_angle_crossing_count_source"] = sources.get(
        "small_angle_crossing_count")
    statistics["small_angle_5deg_threshold_deg"] = SMALL_ANGLE_5DEG
    statistics["small_angle_5deg_crossing_count"] = small_angle_5
    statistics["crossing_grid_mm"] = CROSSING_GRID_MM
    statistics["crossing_grid_peak"] = grid_peak
    statistics["crossing_grid_peak_cell"] = grid_peak_cell
    statistics["densest_crossing_cells"] = densest_cells
    statistics["crossing_grid_peak_source"] = ("recomputed_from_primitives"
                                               if pair_audit else None)
    for field in violation_fields:
        statistics[field] = merged.get(field)
        statistics[f"{field}_source"] = sources.get(field)
        statistics[f"{field}_recomputed"] = recomputed.get(field)
    statistics["total_violation_count"] = (strict_violation_total
                                           if strict_violation_complete else None)
    statistics["audit_passed"] = primary_audit.get("passed") if primary_audit else None
    statistics["audit_policy"] = primary_audit.get("policy") if primary_audit else None
    statistics["audit_error_count"] = primary_audit.get("errors") if primary_audit else None
    statistics["audit_warning_count"] = (primary_audit.get("warnings")
                                         if primary_audit else None)
    statistics["audit_violation_count"] = (primary_audit.get("violations")
                                           if primary_audit else None)
    statistics["audit_candidate_pair_count"] = (
        primary_audit.get("candidate_pair_count") if primary_audit else None)
    statistics["audit_runtime_seconds"] = (primary_audit.get("runtime_seconds")
                                           if primary_audit else None)
    statistics["audit_min_non_crossing_centerline_mm"] = (
        primary_audit.get("min_non_crossing_centerline_mm")
        if primary_audit else None)
    statistics["sensitivity_audits"] = OrderedDict(
        (name, report) for name, report in sensitivity.items())
    statistics["candidate_evaluations"] = run_metadata["candidate_evaluations"]
    statistics["candidate_evaluations_source"] = run_metadata[
        "candidate_evaluations_source"]
    statistics["candidate_evaluations_route_sum"] = run_metadata[
        "candidate_evaluations_route_sum"]
    statistics["candidate_evaluations_failed_route_sum"] = run_metadata[
        "candidate_evaluations_failed_route_sum"]
    statistics["runtime_seconds"] = run_metadata["runtime_seconds"]
    statistics["runtime_seconds_source"] = run_metadata["runtime_seconds_source"]
    statistics["evals_per_second"] = run_metadata["evals_per_second"]
    statistics["peak_memory_mb"] = run_metadata["peak_memory_mb"]
    statistics["peak_memory_mb_source"] = run_metadata["peak_memory_mb_source"]
    statistics["pair_checks"] = run_metadata["pair_checks"]
    statistics["pair_checks_source"] = run_metadata["pair_checks_source"]
    statistics["eval_budget"] = run_metadata["eval_budget"]
    statistics["time_budget_seconds"] = run_metadata["time_budget_seconds"]
    statistics["budget_exhausted"] = run_metadata["budget_exhausted"]
    statistics["run_status"] = config.get("run_status")
    statistics["acceptance_policy"] = config.get("crossing_policy")
    statistics["crossing_policy_requested"] = (pair_audit or {}).get(
        "policy_requested")
    statistics["crossing_policy_recompute"] = (pair_audit or {}).get("policy_used")
    statistics["crossing_policy_note"] = (pair_audit or {}).get("policy_note")
    statistics["mean_min_gap_mm"] = (gaps or {}).get("mean_min_gap_mm")
    statistics["median_min_gap_mm"] = (gaps or {}).get("median_min_gap_mm")
    statistics["min_min_gap_mm"] = (gaps or {}).get("min_min_gap_mm")
    statistics["max_min_gap_mm"] = (gaps or {}).get("max_min_gap_mm")
    statistics["mean_min_gap_mm_source"] = ("recomputed_from_primitives"
                                            if gaps else None)
    statistics["routes_with_min_gap"] = (gaps or {}).get("routes_with_min_gap")
    statistics["unresolved_min_gap_route_ids"] = (gaps or {}).get(
        "unresolved_route_ids")
    statistics["per_route_min_gap_mm"] = (gaps or {}).get("per_route_min_gap_mm")
    statistics["track_band_score"] = (track_band or {}).get("track_band_score")
    statistics["track_band_score_source"] = ("recomputed_from_primitives"
                                             if track_band else None)
    for key in ("track_band_pitch_mm", "track_band_tolerance_mm",
                "track_band_max_separation_mm", "track_band_eligible_pairs",
                "track_band_aligned_pairs", "track_band_route_pairs_checked"):
        statistics[key] = (track_band or {}).get(key)
    statistics["symmetry"] = symmetry
    statistics["pareto"] = {
        "routed": routed_count,
        "total_length_mm": geometry["total_length_mm"],
        "crossing_count": crossing_count,
        "mean_length_mm": geometry["mean_length_mm"],
        "small_angle_crossing_count": small_angle,
        "violation_pair_count": merged.get("violation_pair_count"),
        "strict_violation_count": (strict_violation_total
                                   if strict_violation_complete else None),
        "mean_bend_count": geometry["mean_bend_count"],
        "lexicographic_objective": [
            "routed (descending)", "strict_violation_count (ascending)",
            "small_angle_crossing_count (ascending)",
            "crossing_count (ascending)", "total_length_mm (ascending)",
            "mean_bend_count (ascending)"],
    }
    statistics["metric_sources"] = {
        "geometry": "recomputed_from_primitives (four_side_1024.geometry length)",
        "single_route_checks": ("four_side_1024.d56.validate_d56."
                                "check_route_primitives (independent validator)"),
        "crossings": ("four_side_1024.d56.validate_d56.audit_route_pairs with "
                      "crossing_policy=" + str((pair_audit or {}).get("policy_used"))),
        "violations": ("merged from authoritative audit file when present; "
                       "recomputed_from_primitives otherwise"),
        "run_metadata": "routes.json statistics/algorithm, config.json, run.log",
        "symmetry": (symmetry or {}).get("source"),
        "audited_fields": sources,
    }
    statistics["recomputation_runtime_seconds"] = time.perf_counter() - started
    statistics["geometry_checks"] = {key: value for key, value in geometry.items()
                                     if key not in ("length_mm", "route_errors")}
    statistics["route_geometry"] = geometry["length_mm"]
    statistics["route_errors"] = geometry["route_errors"]
    statistics["pair_audit"] = {
        "crossing_pair_count": (pair_audit or {}).get("crossing_pair_count"),
        "candidate_pair_count": (pair_audit or {}).get("candidate_pair_count"),
        "prepared_route_count": (pair_audit or {}).get("prepared_route_count"),
        "skipped_route_ids": (pair_audit or {}).get("skipped_route_ids"),
        "policy_used": (pair_audit or {}).get("policy_used"),
        "runtime_seconds": (pair_audit or {}).get("recompute_runtime_seconds"),
        "violations_sample": (pair_audit or {}).get("violations", [])[:20],
    }
    statistics["notes"] = []
    if stale_audits:
        statistics["notes"].append(
            "ignored audit file(s) older than routes.json (stale solution): "
            + ", ".join(stale_audits))
    if not primary_audit:
        statistics["notes"].append(
            "no audit_strict.json / independent_audit.json found next to routes.json: "
            "violation counters are recomputed with validate_d56 and marked with "
            "source='recomputed_from_primitives'")
    if pair_audit and pair_audit.get("policy_note"):
        statistics["notes"].append(pair_audit["policy_note"])
    if run_metadata["candidate_evaluations"] is None:
        statistics["notes"].append(
            "candidate_evaluations not recorded by the run; reported route-sum only")
    if run_metadata["runtime_seconds"] is None:
        statistics["notes"].append(
            "runtime_seconds not recorded by the run; field left null")
    if run_metadata["peak_memory_mb"] is None:
        statistics["notes"].append(
            "peak_memory_mb not recorded by the run; field left null")
    if symmetry is not None and symmetry.get("fallback_reason"):
        statistics["notes"].append(
            f"symmetry metrics used local fallback: {symmetry['fallback_reason']}")
    statistics["notes"].append(
        "every geometric number in this file is recomputed from route primitives; "
        "the router's embedded routes.json['statistics'] block is not copied")

    statistics = _json_safe(statistics)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(statistics, handle, ensure_ascii=False, indent=1, sort_keys=False)
        handle.write("\n")
    if not quiet:
        summary = {
            "out": str(out_path),
            "experiment": experiment,
            "routed": routed_count,
            "unrouted": unrouted_count,
            "routing_rate": round(statistics["routing_rate"], 6),
            "crossing_count": crossing_count,
            "crossing_count_recomputed": statistics["crossing_count_recomputed"],
            "mean_length_mm": (round(statistics["mean_length_mm"], 6)
                               if statistics["mean_length_mm"] is not None else None),
            "opposite_routing_rate": round(statistics["opposite_routing_rate"], 6),
            "adjacent_routing_rate": round(statistics["adjacent_routing_rate"], 6),
            "spacing_violation_pairs": statistics["spacing_violation_pairs"],
            "audit_policy": statistics["audit_policy"],
            "runtime_seconds": statistics["runtime_seconds"],
            "recomputation_runtime_seconds": round(
                statistics["recomputation_runtime_seconds"], 3),
        }
        print(json.dumps(summary, ensure_ascii=False))
    return statistics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser():
    parser = argparse.ArgumentParser(
        description="Recompute the SPEC §5 ABCD statistics from route primitives.")
    parser.add_argument("--routes", help="path to <run>/routes.json")
    parser.add_argument("--config", help="path to <run>/config.json")
    parser.add_argument("--out", help="output statistics.json path")
    parser.add_argument("--audit", help="authoritative audit_strict.json path "
                                        "(default: auto-detect next to routes.json)")
    parser.add_argument("--audit-exact", dest="audit_exact",
                        help="optional sensitivity audit (exact policy)")
    parser.add_argument("--audit-legacy", dest="audit_legacy",
                        help="optional sensitivity audit (legacy policy)")
    parser.add_argument("--run-dir", help="run directory; infers the paths above")
    parser.add_argument("--experiment", help="experiment label (default: run dir name)")
    parser.add_argument("--skip-gaps", action="store_true",
                        help="skip the nearest-centreline-gap computation")
    parser.add_argument("--skip-track-band", action="store_true",
                        help="skip the track-band regularity computation")
    parser.add_argument("--skip-pair-audit", action="store_true",
                        help="skip the crossing re-enumeration")
    parser.add_argument("--skip-symmetry", action="store_true",
                        help="skip the symmetry metrics")
    parser.add_argument("--quiet", action="store_true", help="suppress the summary")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    run_dir = Path(args.run_dir) if args.run_dir else None
    routes_path = args.routes
    config_path = args.config
    out_path = args.out
    audit_path = args.audit
    if run_dir is not None:
        routes_path = routes_path or str(run_dir / "routes.json")
        if config_path is None:
            candidate = run_dir / "config.json"
            config_path = str(candidate) if candidate.exists() else None
        if out_path is None:
            out_path = str(run_dir / "statistics.json")
        if audit_path is None:
            candidate = run_dir / "audit_strict.json"
            if candidate.exists():
                audit_path = str(candidate)
    if not routes_path:
        raise SystemExit("metrics: --routes or --run-dir is required")
    statistics = build_statistics(
        routes_path=routes_path, config_path=config_path, out_path=out_path,
        audit_path=audit_path, audit_exact_path=args.audit_exact,
        audit_legacy_path=args.audit_legacy, run_dir=run_dir,
        experiment=args.experiment, skip_gaps=args.skip_gaps,
        skip_track_band=args.skip_track_band,
        skip_pair_audit=args.skip_pair_audit,
        skip_symmetry=args.skip_symmetry, quiet=args.quiet)
    return 0 if statistics else 1


if __name__ == "__main__":
    raise SystemExit(main())
