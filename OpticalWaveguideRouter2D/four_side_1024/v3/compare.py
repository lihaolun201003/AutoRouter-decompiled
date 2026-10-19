"""Comparison assets for the eight V3-Huang plane runs and four combined layouts.

Round-3 deliverable for ``four_side_1024/v3/SPEC.md`` §7/§8.  Scans

* ``planes/<A>/<z1|z2>/``   (8 independent 512-connection plane runs),
* ``combined/<A>/``         (4 dual-height 1024-channel layouts),

and writes into ``comparison/``:

* ``all_metrics.csv`` / ``all_metrics.json`` -- one row per plane run and per
  combined layout with the full Phase-6 metric set (class/pair counts, path
  shapes, U depth/track/nesting/spacing/bundle numbers, failure taxonomy,
  lengths/bends/crossings, propagation loss, strict violation counters merged
  from the authoritative ``audit_strict.json``), ``role`` column included;
* ``strict_audit_summary_metrics.json`` -- metrics-side merge of the per-plane
  authoritative audits; the validator's canonical
  ``comparison/strict_audit_summary.json`` is preserved and only referenced;
* the ten Phase-7 figures (1)-(10):
  1. ``demand_1024_connector.png``            -- 1024 connection demand diagram
  2. ``connector_matrix_64x64.png``           -- 64x64 weighted connector matrix
  3. ``layouts_z1_abcd.png``                  -- z1 A/B/C/D full 2D layouts
  4. ``layouts_z2_abcd.png``                  -- z2 A/B/C/D full 2D layouts
  5. ``combined_layouts_abcd.png``            -- four combined dual-height layouts
  6. ``overlay_3d_abcd.png``                  -- four 3D overlays
  7. ``u_routes_only.png`` / ``refold_routes_only.png`` -- same-side U/refold only
  8. ``nested_u_zoom.png``                    -- local zoom of 10-20 nested U routes
  9. ``class_routed_compare.png``             -- same/opposite/adjacent routed counts
  10. ``algo_routed_rate_compare.png``        -- four-algorithm routed-rate comparison
  plus ``connector_matrix_64x64.json`` with the directed + symmetric matrices.
* a ``rendered`` / ``skipped`` manifest so missing runs are reported, not guessed.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.v3.compare --root <root>
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import time
from collections import Counter
from pathlib import Path

import numpy as np

from ..d56.plots_d56 import BOARD_MM, DPI, _board_frame, draw_connectors, pyplot
from ..fslw.compare import _bar_figure
from . import config as v3_config
from . import metrics as v3_metrics
from . import plots as v3_plots

SCHEMA = "four_side_1024_v3_comparison_v1"
TOOL = "four_side_1024.v3.compare"
PLANE_TOTAL = 512
COMBINED_TOTAL = 1024
CLASS_ORDER = v3_metrics.CLASSES
PAIR_ORDER = v3_metrics.PAIR_ORDER
CLASS_COLORS = v3_plots.CLASS_COLORS
PLANE_COLORS = v3_plots.PLANE_COLORS

CSV_COLUMNS = (
    "role", "scope", "experiment", "algorithm", "plane", "z_mm",
    "connections_total", "routed", "unrouted", "routing_rate",
    # class / pair routed counts
    "same_routed", "same_total", "same_rate",
    "opposite_routed", "opposite_total", "opposite_rate",
    "adjacent_routed", "adjacent_total", "adjacent_rate",
    "pair_NN_routed", "pair_SS_routed", "pair_EE_routed", "pair_WW_routed",
    "pair_NS_routed", "pair_EW_routed",
    "pair_NE_routed", "pair_NW_routed", "pair_ES_routed", "pair_SW_routed",
    # path shapes (from primitives)
    "shape_straight", "shape_short_S", "shape_L", "shape_U",
    "shape_multi_bend_refold", "shape_other", "shape_total",
    "shape_U_same_side_count",
    # U geometry statistics
    "u_route_count", "u_depth_mean_mm", "u_depth_median_mm",
    "u_depth_min_mm", "u_depth_max_mm",
    "u_nesting_group_count", "u_nesting_max_chain_length",
    "u_adjacent_spacing_pairs", "u_adjacent_spacing_min_mm",
    "u_adjacent_spacing_mean_mm", "u_adjacent_spacing_violations",
    "u_bundle_count", "u_bundle_max_size",
    "refold_route_count", "refold_region_grid_peak_mm",
    # standard quality
    "mean_length_mm", "max_length_mm", "total_length_mm", "total_bends",
    "mean_straight_fraction", "mean_unnecessary_detour_mm",
    "mean_unnecessary_detour_vs_euclidean_mm",
    "crossing_count", "crossing_count_recomputed", "crossing_pair_count",
    "small_angle_crossing_count", "crossing_grid_peak",
    "spacing_violation_pairs", "overlap_pairs", "touch_pairs",
    "crossing_window_overlap_pairs", "double_cross_pairs",
    "crossing_window_excessive_pairs", "self_intersections", "self_overlaps",
    "self_spacing_violations", "radius_violations", "boundary_violations",
    "diagonal_line_violations", "free_arc_violations",
    "total_violation_count",
    "mean_min_gap_mm", "min_min_gap_mm", "route_length_grid_peak_mm",
    "propagation_loss_mean_db", "propagation_loss_total_db",
    "propagation_loss_max_db", "propagation_loss_p50_db",
    "bend_loss_status", "crossing_loss_status", "total_optical_loss_status",
    # failure taxonomy
    "failed_no_candidate_generated", "failed_no_legal_candidate",
    "failed_budget_or_timeout", "failed_not_attempted", "failed_other",
    "failure_total",
    # audit / run metadata
    "audit_present", "audit_passed", "audit_policy", "audit_routed_count",
    "audit_checked_count", "audit_failed_count", "audit_error_count",
    "candidate_evaluations", "candidate_evaluations_source",
    "runtime_seconds", "runtime_seconds_source", "evals_per_second",
    "peak_memory_mb", "pair_checks", "eval_budget", "time_budget_seconds",
    "budget_exhausted",
    # combined-only
    "combined_z1_routed", "combined_z2_routed", "same_plane_crossings",
    "cross_plane_projected_internal_crossings",
    "cross_plane_projected_port_coincidences",
    "cross_plane_projected_pair_count", "cross_plane_projected_grid_peak",
    # topology validation
    "topology_validation_passed", "ports_model_mismatch_count",
    # routes.json reconciliation (declared vs recomputed)
    "reconcile_declared_routed_count", "reconcile_declared_total_connections",
    "reconcile_declared_length_sum_mm", "reconcile_declared_bend_count_sum",
    "reconcile_declared_propagation_loss_sum_db",
    "reconcile_recomputed_routed_count", "reconcile_recomputed_total_length_mm",
    "reconcile_recomputed_arc_count_total",
    "reconcile_recomputed_propagation_loss_total_db",
    "reconcile_recomputed_endpoints_checked",
    "reconcile_recomputed_geometry_violations_total",
    "reconcile_length_diff_mm", "reconcile_bend_count_diff",
    "reconcile_propagation_loss_diff_db", "reconcile_routed_count_diff",
    "notes",
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _load_json(path):
    return v3_metrics._load_json(path)  # noqa: SLF001


def _plane_statistics(run_dir, recompute=True):
    path = Path(run_dir) / "statistics.json"
    info = {"statistics_present": path.exists(), "recomputed": False,
            "path": str(path)}
    if path.exists():
        try:
            return _load_json(path), info
        except (OSError, json.JSONDecodeError) as exc:
            info["error"] = f"{type(exc).__name__}: {exc}"
    if not recompute:
        return None, info
    try:
        statistics = v3_metrics.build_plane_statistics(run_dir, quiet=True)
        info["statistics_present"] = True
        info["recomputed"] = True
        return statistics, info
    except Exception as exc:  # noqa: BLE001 - reported, never fabricated
        info["error"] = f"{type(exc).__name__}: {exc}"
        return None, info


def _combined_statistics(combined_dir, root, recompute=True):
    path = Path(combined_dir) / "statistics.json"
    info = {"statistics_present": path.exists(), "recomputed": False,
            "path": str(path)}
    if path.exists():
        try:
            return _load_json(path), info
        except (OSError, json.JSONDecodeError) as exc:
            info["error"] = f"{type(exc).__name__}: {exc}"
    if not recompute:
        return None, info
    try:
        statistics = v3_metrics.build_combined_statistics(
            combined_dir, root=root, quiet=True)
        info["statistics_present"] = True
        info["recomputed"] = True
        return statistics, info
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
        return None, info


def _audit_info(run_dir):
    path = Path(run_dir) / "audit_strict.json"
    info = {"audit_present": path.exists(),
            "audit_file": str(path) if path.exists() else None}
    if not path.exists():
        return info
    try:
        payload = _load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        info["audit_error"] = f"{type(exc).__name__}: {exc}"
        return info
    info.update({
        "audit_passed": payload.get("passed"),
        "audit_policy": payload.get("policy_used") or payload.get("policy"),
        "audit_routed_count": payload.get("routed_count"),
        "audit_checked_count": payload.get("d56_checked_count"),
        "audit_failed_count": payload.get("d56_failed_count"),
        "audit_error_count": len(payload.get("errors") or []),
        "audit_crossing_count": payload.get("crossing_count"),
        "audit_spacing_violation_pairs": payload.get("spacing_violation_pairs"),
        "audit_violation_pair_count": payload.get("violation_pair_count"),
        "audit_runtime_seconds": payload.get("runtime_seconds"),
        "audit_window_count": payload.get("crossing_window_count"),
        "audit_window_max_mm": payload.get("crossing_window_max_mm"),
        "audit_sha256": v3_metrics._sha256(path),  # noqa: SLF001
        "audit_raw": payload,
    })
    return info


def _class_value(statistics, relation, field):
    return (((statistics or {}).get("by_class") or {}).get(relation) or {}).get(
        field)


def _pair_value(statistics, pair, field):
    return (((statistics or {}).get("by_pair") or {}).get(pair) or {}).get(
        field)


def _loss_value(statistics, field):
    return ((statistics or {}).get("propagation_loss") or {}).get(field)


def _breakdown_status(statistics, key):
    block = ((statistics or {}).get("optical_loss_breakdown") or {}).get(key) or {}
    return block.get("status")


def _route_reconciliation(run_dir):
    """Compare routes.json declared numbers against the recomputed statistics."""
    run_dir = Path(run_dir)
    routes_path = run_dir / "routes.json"
    info = {"routes_present": routes_path.exists()}
    if not routes_path.exists():
        return info
    try:
        payload = _load_json(routes_path)
    except (OSError, json.JSONDecodeError) as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
        return info
    records = []
    if isinstance(payload, dict):
        records = payload.get("routes") or []
    routed = [record for record in records
              if record.get("status") == "routed" or record.get("primitives")]
    declared_length = 0.0
    declared_bends = 0
    declared_loss = 0.0
    length_missing = 0
    for record in routed:
        length = v3_metrics._number(record.get("length_mm"))  # noqa: SLF001
        if length is None:
            length_missing += 1
        else:
            declared_length += length
        bends = v3_metrics._number(record.get("bend_count"))  # noqa: SLF001
        if bends is not None:
            declared_bends += int(bends)
        loss = v3_metrics._number(record.get("propagation_loss_db"))  # noqa: SLF001
        if loss is not None:
            declared_loss += loss
    info.update({
        "declared_routed_count": len(routed),
        "declared_total_connections": len(records),
        "declared_length_sum_mm": declared_length,
        "declared_length_missing_count": length_missing,
        "declared_bend_count_sum": declared_bends,
        "declared_propagation_loss_sum_db": declared_loss,
    })
    statistics_path = run_dir / "statistics.json"
    if statistics_path.exists():
        try:
            statistics = _load_json(statistics_path)
        except (OSError, json.JSONDecodeError):
            statistics = None
        if isinstance(statistics, dict):
            info.update({
                "recomputed_routed_count": statistics.get("routed"),
                "recomputed_total_length_mm": statistics.get("total_length_mm"),
                "recomputed_arc_count_total": (
                    (statistics.get("geometry_checks") or {}).get("num_arcs_total")),
                "recomputed_propagation_loss_total_db": (
                    (statistics.get("propagation_loss") or {}).get("value_db")),
                "recomputed_endpoints_checked": (
                    (statistics.get("geometry_checks") or {}).get(
                        "endpoints_checked")),
                "recomputed_geometry_violations_total": sum(
                    int(statistics.get(field) or 0) for field in (
                        "radius_violations", "boundary_violations",
                        "diagonal_line_violations", "free_arc_violations",
                        "self_intersections", "self_overlaps",
                        "self_spacing_violations")),
                "ports_model_mismatch_count": (
                    statistics.get("topology_validation") or {}).get(
                        "ports_model_mismatch_count"),
                "topology_validation_passed": (
                    statistics.get("topology_validation") or {}).get("passed"),
            })
            length = v3_metrics._number(  # noqa: SLF001
                info.get("recomputed_total_length_mm"))
            if length is not None:
                info["length_diff_mm"] = declared_length - length
            declared_bends_value = v3_metrics._number(  # noqa: SLF001
                info.get("declared_bend_count_sum"))
            arc_count = v3_metrics._number(  # noqa: SLF001
                info.get("recomputed_arc_count_total"))
            if declared_bends_value is not None and arc_count is not None:
                info["bend_count_diff"] = declared_bends_value - arc_count
            loss = v3_metrics._number(  # noqa: SLF001
                info.get("recomputed_propagation_loss_total_db"))
            if loss is not None:
                info["propagation_loss_diff_db"] = declared_loss - loss
            routed = statistics.get("routed")
            if isinstance(routed, int):
                info["routed_count_diff"] = (info["declared_routed_count"]
                                             - routed)
    return info


def _plane_row(algorithm, plane, statistics, info, audit=None, reconciliation=None):
    audit = audit or {}
    shapes = ((statistics or {}).get("path_shapes") or {})
    shape_counts = shapes.get("counts") or {}
    u_statistics = (statistics or {}).get("u_statistics") or {}
    u_depth = u_statistics.get("depth_mm") or {}
    nesting = u_statistics.get("nesting") or {}
    adjacent = u_statistics.get("adjacent_spacing") or {}
    bundles = u_statistics.get("bundles") or {}
    refold = (statistics or {}).get("refold_statistics") or {}
    failures = (statistics or {}).get("failure_taxonomy") or {}
    failure_counts = failures.get("counts") or {}
    validation = (statistics or {}).get("topology_validation") or {}
    row = {
        "role": "main_plane",
        "scope": "plane",
        "experiment": (statistics or {}).get("experiment")
        or f"V3_{algorithm}_{plane}",
        "algorithm": algorithm,
        "plane": plane,
        "z_mm": (statistics or {}).get("z_mm"),
        "connections_total": (statistics or {}).get("connections_total",
                                                    PLANE_TOTAL),
        "routed": (statistics or {}).get("routed"),
        "unrouted": (statistics or {}).get("unrouted"),
        "routing_rate": (statistics or {}).get("routing_rate"),
        "same_routed": _class_value(statistics, "same", "success"),
        "same_total": _class_value(statistics, "same", "total"),
        "same_rate": _class_value(statistics, "same", "routing_rate"),
        "opposite_routed": _class_value(statistics, "opposite", "success"),
        "opposite_total": _class_value(statistics, "opposite", "total"),
        "opposite_rate": _class_value(statistics, "opposite", "routing_rate"),
        "adjacent_routed": _class_value(statistics, "adjacent", "success"),
        "adjacent_total": _class_value(statistics, "adjacent", "total"),
        "adjacent_rate": _class_value(statistics, "adjacent", "routing_rate"),
        "shape_straight": shape_counts.get("straight"),
        "shape_short_S": shape_counts.get("short_S"),
        "shape_L": shape_counts.get("L"),
        "shape_U": shape_counts.get("U"),
        "shape_multi_bend_refold": shape_counts.get("multi_bend_refold"),
        "shape_other": shape_counts.get("other"),
        "shape_total": shapes.get("routed_total"),
        "shape_U_same_side_count": u_statistics.get("count"),
        "u_route_count": u_statistics.get("count"),
        "u_depth_mean_mm": u_depth.get("mean"),
        "u_depth_median_mm": u_depth.get("median"),
        "u_depth_min_mm": u_depth.get("min"),
        "u_depth_max_mm": u_depth.get("max"),
        "u_nesting_group_count": nesting.get("group_count"),
        "u_nesting_max_chain_length": nesting.get("max_chain_length"),
        "u_adjacent_spacing_pairs": adjacent.get("pairs_considered"),
        "u_adjacent_spacing_min_mm": adjacent.get("min_gap_mm"),
        "u_adjacent_spacing_mean_mm": adjacent.get("mean_gap_mm"),
        "u_adjacent_spacing_violations": adjacent.get("violation_count"),
        "u_bundle_count": bundles.get("count"),
        "u_bundle_max_size": bundles.get("max_size"),
        "refold_route_count": refold.get("count"),
        "refold_region_grid_peak_mm": refold.get("region_grid_peak_mm"),
        "mean_length_mm": (statistics or {}).get("mean_length_mm"),
        "max_length_mm": (statistics or {}).get("max_length_mm"),
        "total_length_mm": (statistics or {}).get("total_length_mm"),
        "total_bends": (statistics or {}).get("total_bends"),
        "mean_straight_fraction": (statistics or {}).get(
            "mean_straight_fraction"),
        "mean_unnecessary_detour_mm": (statistics or {}).get(
            "mean_unnecessary_detour_mm"),
        "mean_unnecessary_detour_vs_euclidean_mm": (statistics or {}).get(
            "mean_unnecessary_detour_vs_euclidean_mm"),
        "crossing_count": (statistics or {}).get("crossing_count"),
        "crossing_count_recomputed": (statistics or {}).get(
            "crossing_count_recomputed"),
        "crossing_pair_count": (statistics or {}).get("crossing_pair_count"),
        "small_angle_crossing_count": (statistics or {}).get(
            "small_angle_crossing_count"),
        "crossing_grid_peak": (statistics or {}).get("crossing_grid_peak"),
        "mean_min_gap_mm": (statistics or {}).get("mean_min_gap_mm"),
        "min_min_gap_mm": (statistics or {}).get("min_min_gap_mm"),
        "route_length_grid_peak_mm": (statistics or {}).get(
            "route_length_grid_peak_mm"),
        "propagation_loss_mean_db": _loss_value(statistics, "mean_db"),
        "propagation_loss_total_db": _loss_value(statistics, "value_db"),
        "propagation_loss_max_db": _loss_value(statistics, "max_db"),
        "propagation_loss_p50_db": ((statistics or {}).get(
            "propagation_loss_detail") or {}).get("percentiles", {}).get("p50"),
        "bend_loss_status": _breakdown_status(statistics, "bend_loss"),
        "crossing_loss_status": _breakdown_status(statistics, "crossing_loss"),
        "total_optical_loss_status": _breakdown_status(statistics,
                                                       "total_optical_loss"),
        "failed_no_candidate_generated": failure_counts.get(
            "no_candidate_generated"),
        "failed_no_legal_candidate": failure_counts.get("no_legal_candidate"),
        "failed_budget_or_timeout": failure_counts.get("budget_or_timeout"),
        "failed_not_attempted": failure_counts.get("not_attempted"),
        "failed_other": failure_counts.get("other"),
        "failure_total": failures.get("total_failed"),
        "audit_present": bool(audit.get("audit_present")),
        "audit_passed": (statistics or {}).get("audit_passed")
        if (statistics or {}).get("audit_passed") is not None
        else audit.get("audit_passed"),
        "audit_policy": (statistics or {}).get("audit_policy")
        or audit.get("audit_policy"),
        "audit_routed_count": (statistics or {}).get("audit_routed_count")
        or audit.get("audit_routed_count"),
        "audit_checked_count": (statistics or {}).get("audit_checked_count")
        or audit.get("audit_checked_count"),
        "audit_failed_count": (statistics or {}).get("audit_failed_count")
        if (statistics or {}).get("audit_failed_count") is not None
        else audit.get("audit_failed_count"),
        "audit_error_count": (statistics or {}).get("audit_error_count")
        if (statistics or {}).get("audit_error_count") is not None
        else audit.get("audit_error_count"),
        "candidate_evaluations": (statistics or {}).get("candidate_evaluations"),
        "candidate_evaluations_source": (statistics or {}).get(
            "candidate_evaluations_source"),
        "runtime_seconds": (statistics or {}).get("runtime_seconds"),
        "runtime_seconds_source": (statistics or {}).get(
            "runtime_seconds_source"),
        "evals_per_second": (statistics or {}).get("evals_per_second"),
        "peak_memory_mb": (statistics or {}).get("peak_memory_mb"),
        "pair_checks": (statistics or {}).get("pair_checks"),
        "eval_budget": (statistics or {}).get("eval_budget"),
        "time_budget_seconds": (statistics or {}).get("time_budget_seconds"),
        "budget_exhausted": (statistics or {}).get("budget_exhausted"),
        "topology_validation_passed": validation.get("passed"),
        "ports_model_mismatch_count": validation.get(
            "ports_model_mismatch_count"),
        "notes": info.get("error") or "",
    }
    reconciliation = reconciliation or {}
    for key in ("declared_routed_count", "declared_total_connections",
                "declared_length_sum_mm", "declared_bend_count_sum",
                "declared_propagation_loss_sum_db",
                "recomputed_routed_count", "recomputed_total_length_mm",
                "recomputed_arc_count_total",
                "recomputed_propagation_loss_total_db",
                "recomputed_endpoints_checked",
                "recomputed_geometry_violations_total",
                "length_diff_mm", "bend_count_diff", "propagation_loss_diff_db",
                "routed_count_diff"):
        row[f"reconcile_{key}"] = reconciliation.get(key)
    for pair in PAIR_ORDER:
        row[f"pair_{pair}_routed"] = _pair_value(statistics, pair, "success")
    for field in ("spacing_violation_pairs", "overlap_pairs", "touch_pairs",
                  "crossing_window_overlap_pairs", "double_cross_pairs",
                  "crossing_window_excessive_pairs", "self_intersections",
                  "self_overlaps", "self_spacing_violations",
                  "radius_violations", "boundary_violations",
                  "diagonal_line_violations", "free_arc_violations",
                  "total_violation_count"):
        row[field] = (statistics or {}).get(field)
    return row


def _combined_row(algorithm, statistics, info):
    by_class = (statistics or {}).get("by_class") or {}
    by_plane = (statistics or {}).get("planes") or {}
    projection = (statistics or {}).get("cross_plane_projected_overlap") or {}
    shapes = ((statistics or {}).get("path_shapes") or {}).get("counts") or {}
    u_statistics = (statistics or {}).get("u_statistics") or {}
    row = {
        "role": "main_combined",
        "scope": "combined",
        "experiment": (statistics or {}).get("experiment")
        or f"V3_{algorithm}_combined",
        "algorithm": algorithm,
        "plane": "z1+z2",
        "z_mm": None,
        "connections_total": (statistics or {}).get("connections_total",
                                                    COMBINED_TOTAL),
        "routed": (statistics or {}).get("routed"),
        "unrouted": (statistics or {}).get("unrouted"),
        "routing_rate": (statistics or {}).get("routing_rate"),
        "same_routed": (by_class.get("same") or {}).get("success"),
        "same_total": (by_class.get("same") or {}).get("total"),
        "same_rate": (by_class.get("same") or {}).get("routing_rate"),
        "opposite_routed": (by_class.get("opposite") or {}).get("success"),
        "opposite_total": (by_class.get("opposite") or {}).get("total"),
        "opposite_rate": (by_class.get("opposite") or {}).get("routing_rate"),
        "adjacent_routed": (by_class.get("adjacent") or {}).get("success"),
        "adjacent_total": (by_class.get("adjacent") or {}).get("total"),
        "adjacent_rate": (by_class.get("adjacent") or {}).get("routing_rate"),
        "shape_straight": shapes.get("straight"),
        "shape_short_S": shapes.get("short_S"),
        "shape_L": shapes.get("L"),
        "shape_U": shapes.get("U"),
        "shape_multi_bend_refold": shapes.get("multi_bend_refold"),
        "shape_other": shapes.get("other"),
        "shape_total": sum((shapes.get(shape) or 0)
                           for shape in v3_metrics.REQUIRED_SHAPES),
        "u_route_count": u_statistics.get("count"),
        "u_nesting_group_count": u_statistics.get("nesting_group_count"),
        "u_nesting_max_chain_length": u_statistics.get(
            "nesting_max_chain_length"),
        "refold_route_count": (statistics or {}).get("refold_statistics", {}).get(
            "count"),
        "mean_length_mm": (statistics or {}).get("mean_length_mm"),
        "total_length_mm": (statistics or {}).get("total_length_mm"),
        "total_bends": (statistics or {}).get("total_bends"),
        "mean_straight_fraction": ((statistics or {}).get("length") or {}).get(
            "mean_straight_fraction"),
        "mean_unnecessary_detour_mm": ((statistics or {}).get("length") or {}).get(
            "mean_unnecessary_detour_mm"),
        "crossing_count": (statistics or {}).get("same_plane_crossings"),
        "crossing_count_recomputed": (statistics or {}).get(
            "same_plane_crossings"),
        "same_plane_crossings": (statistics or {}).get("same_plane_crossings"),
        "small_angle_crossing_count": (statistics or {}).get(
            "small_angle_crossing_count"),
        "mean_min_gap_mm": (statistics or {}).get("mean_min_gap_mm"),
        "propagation_loss_mean_db": ((statistics or {}).get(
            "propagation_loss") or {}).get("mean_db"),
        "propagation_loss_total_db": ((statistics or {}).get(
            "propagation_loss") or {}).get("value_db"),
        "bend_loss_status": _breakdown_status(statistics, "bend_loss"),
        "crossing_loss_status": _breakdown_status(statistics, "crossing_loss"),
        "total_optical_loss_status": _breakdown_status(
            statistics, "total_optical_loss"),
        "audit_present": bool((statistics or {}).get("audit_passed_all_planes")),
        "audit_passed": (statistics or {}).get("audit_passed_all_planes"),
        "candidate_evaluations": (statistics or {}).get("candidate_evaluations"),
        "runtime_seconds": (statistics or {}).get("runtime_seconds"),
        "combined_z1_routed": (by_plane.get("z1") or {}).get("routed"),
        "combined_z2_routed": (by_plane.get("z2") or {}).get("routed"),
        "cross_plane_projected_internal_crossings": projection.get(
            "cross_plane_projected_internal_crossings"),
        "cross_plane_projected_port_coincidences": projection.get(
            "cross_plane_projected_port_coincidences"),
        "cross_plane_projected_pair_count": projection.get(
            "cross_plane_projected_pair_count"),
        "cross_plane_projected_grid_peak": projection.get(
            "cross_plane_projected_grid_peak"),
        "topology_validation_passed": None,
        "ports_model_mismatch_count": None,
        "notes": info.get("error") or "",
    }
    for pair in PAIR_ORDER:
        row[f"pair_{pair}_routed"] = (((statistics or {}).get("by_pair") or {})
                                      .get(pair) or {}).get("routed")
    for field in ("spacing_violation_pairs", "overlap_pairs", "touch_pairs"):
        by_plane = ((statistics or {}).get("violations") or {}).get(
            "by_plane", {})
        values = [((by_plane.get(plane) or {}).get(field) or 0)
                  for plane in ("z1", "z2")]
        row[field] = sum(values) if values else None
    row["total_violation_count"] = ((statistics or {}).get("violations")
                                    or {}).get("same_plane_total")
    return row


# ---------------------------------------------------------------------------
# strict audit summary
# ---------------------------------------------------------------------------
def _strict_audit_summary(root, plane_audits):
    summary = {
        "schema": "four_side_1024_v3_strict_audit_summary_metrics_v1",
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "policy": "strict",
        "radius_mm": v3_config.RADIUS_MM,
        "edge_gap_mm": v3_config.EDGE_GAP_MM,
        "clearance_mm": v3_config.CLEARANCE_MM,
        "canonical_validator_summary": {
            "file": str(Path(root) / "comparison" / "strict_audit_summary.json"),
            "present": (Path(root) / "comparison" / "strict_audit_summary.json"
                        ).exists(),
            "note": "the validator owns comparison/strict_audit_summary.json; "
                    "this file is the metrics-side merge and never overwrites it",
        },
        "experiments": {},
        "missing_audits": [],
        "all_available_passed": None,
    }
    audited = []
    for key, audit in plane_audits.items():
        if not audit.get("audit_present"):
            summary["missing_audits"].append(key)
            continue
        entry = {
            "file": audit.get("audit_file"),
            "passed": audit.get("audit_passed"),
            "policy": audit.get("audit_policy"),
            "routed_count": audit.get("audit_routed_count"),
            "checked_count": audit.get("audit_checked_count"),
            "failed_count": audit.get("audit_failed_count"),
            "error_count": audit.get("audit_error_count"),
            "crossing_count": audit.get("audit_crossing_count"),
            "spacing_violation_pairs": audit.get("audit_spacing_violation_pairs"),
            "violation_pair_count": audit.get("audit_violation_pair_count"),
            "runtime_seconds": audit.get("audit_runtime_seconds"),
            "crossing_window_count": audit.get("audit_window_count"),
            "crossing_window_max_mm": audit.get("audit_window_max_mm"),
            "sha256": audit.get("audit_sha256"),
        }
        raw = audit.get("audit_raw") or {}
        v3_extras = {}
        for key_name in ("same_side_checks", "hairpin_violations",
                         "tangent_out_violations", "same_side_violations",
                         "structure", "process"):
            if key_name in raw:
                value = raw.get(key_name)
                v3_extras[key_name] = (value if not isinstance(value, (dict, list))
                                       else _summarize_extra(value))
        if v3_extras:
            entry["v3_extras"] = v3_extras
        summary["experiments"][key] = entry
        audited.append(entry)
    summary["audits_present"] = len(audited)
    summary["audits_expected"] = len(plane_audits)
    summary["all_available_passed"] = bool(audited) and all(
        entry.get("passed") for entry in audited)
    summary["total_routed_audited"] = sum(
        int(entry.get("routed_count") or 0) for entry in audited)
    summary["total_violation_pairs"] = sum(
        int(entry.get("violation_pair_count") or 0) for entry in audited)
    return summary


def _summarize_extra(value):
    if isinstance(value, dict):
        return {key: (item if not isinstance(item, (dict, list)) else
                      _summarize_extra(item)) for key, item in value.items()}
    if isinstance(value, list):
        return {"count": len(value), "sample": _summarize_extra(value[:3])}
    return value


# ---------------------------------------------------------------------------
# extra shapes figures (7): refold-only figure
# ---------------------------------------------------------------------------
def render_refold_routes_only(root, output_path):
    plt = pyplot()
    from matplotlib.collections import LineCollection
    runs = list(v3_metrics.iter_plane_runs(root))  # noqa: SLF001
    if not runs:
        return None
    columns = 4
    rows = max(1, math.ceil(len(runs) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(22.0, 5.4 * rows),
                             squeeze=False)
    for index, (algorithm, plane, run_dir) in enumerate(runs):
        context = v3_plots.load_plane(run_dir)
        refold = []
        for record in context["routed"]:
            classification = v3_metrics.classify_route(  # noqa: SLF001
                record.get("primitives") or [],
                float(context["process"].get("radius_mm")
                      or v3_config.RADIUS_MM))
            if classification["shape"] == "multi_bend_refold":
                refold.append(record)
        ax = axes[index // columns][index % columns]
        segments = []
        colours = []
        for record in refold:
            points = v3_metrics._curve_points(record.get("primitives") or [])  # noqa: SLF001
            if len(points) < 2:
                continue
            segments.append(points)
            colours.append(v3_plots.PAIR_COLORS.get(
                v3_metrics._pair_of(record), "#666666"))  # noqa: SLF001
        if segments:
            ax.add_collection(LineCollection(segments, colors=colours,
                                             linewidths=0.7, alpha=0.9,
                                             zorder=3))
        _board_frame(ax)
        ax.tick_params(labelsize=5.5)
        ax.set_title(f"{algorithm}_{plane} refold-only | {len(refold)} multi-bend "
                     f"refold (of {len(context['routed'])} routed)", fontsize=8.0)
    for empty in range(len(runs), rows * columns):
        axes[empty // columns][empty % columns].axis("off")
    fig.suptitle(
        "Phase-7 figure 7b: V3 multi-bend refold routes only (SAVED PRIMITIVES; "
        "all refold routes drawn, colour = side pair). Refold = three or more "
        "quarter arcs, two or more hairpins, or short-S + additional arcs.",
        fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "refold_routes_only"}


# ---------------------------------------------------------------------------
# key numbers + comparison README
# ---------------------------------------------------------------------------
def _key_numbers(root, rows, audit_summary, reconciliation_summary, rendered,
                 skipped):
    planes = [row for row in rows if row.get("scope") == "plane"]
    combined = [row for row in rows if row.get("scope") == "combined"]
    payload = {
        "schema": "four_side_1024_v3_key_numbers_v1",
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "topology": v3_config.TOPOLOGY,
        "contract": {
            "connections_total": 1024,
            "plane_connections": 512,
            "class_counts": dict(v3_config.EXPECTED["relation_counts"]),
            "pair_counts": dict(v3_config.EXPECTED["pair_counts"]),
            "planes": {plane: dict(values) for plane, values in
                       v3_config.EXPECTED["planes"].items()},
            "process": {
                "radius_mm": v3_config.RADIUS_MM,
                "edge_gap_mm": v3_config.EDGE_GAP_MM,
                "clearance_mm": v3_config.CLEARANCE_MM,
                "width_mm": v3_config.WIDTH_MM,
                "propagation_loss_db_per_cm":
                    v3_config.PROPAGATION_LOSS_DB_PER_CM,
            },
        },
        "planes": [],
        "combined": [],
        "audit": {
            "audits_present": audit_summary.get("audits_present"),
            "audits_expected": audit_summary.get("audits_expected"),
            "all_available_passed": audit_summary.get("all_available_passed"),
            "total_routed_audited": audit_summary.get("total_routed_audited"),
            "total_violation_pairs": audit_summary.get("total_violation_pairs"),
            "missing_audits": audit_summary.get("missing_audits"),
            "canonical_validator_summary": audit_summary.get(
                "canonical_validator_summary"),
        },
        "reconciliation": reconciliation_summary,
        "loss_policy": {
            "propagation_computed": True,
            "bend_loss": "unknown_uncalibrated",
            "crossing_loss": "unknown_uncalibrated",
            "total_optical_loss": "not_computable_missing_calibration",
            "legacy_polymer_model_used_as_glass_truth": False,
        },
        "shape_policy": {
            "classified_from": "saved world-mm primitives only",
            "classes": list(v3_metrics.REQUIRED_SHAPES),
            "u_definition": "net-180 same-side U/hairpin paths "
                            "(wide_U / hairpin / hairpin_short_S)",
            "other_definition": "two-quarter step transfers (FSLW opposite U "
                                "family); no step class in the required taxonomy",
        },
        "rendered_figures": rendered,
        "skipped_figures": skipped,
    }
    for row in planes:
        payload["planes"].append({
            "experiment": row.get("experiment"),
            "algorithm": row.get("algorithm"),
            "plane": row.get("plane"),
            "routed": row.get("routed"),
            "connections_total": row.get("connections_total"),
            "routing_rate": row.get("routing_rate"),
            "same_routed": row.get("same_routed"),
            "same_total": row.get("same_total"),
            "opposite_routed": row.get("opposite_routed"),
            "opposite_total": row.get("opposite_total"),
            "adjacent_routed": row.get("adjacent_routed"),
            "adjacent_total": row.get("adjacent_total"),
            "same_side_by_pair": {
                pair: row.get(f"pair_{pair}_routed")
                for pair in v3_metrics.CLASS_PAIRS["same"]},
            "path_shapes": {shape: row.get(f"shape_{shape}")
                            for shape in v3_metrics.REQUIRED_SHAPES},
            "u_route_count": row.get("u_route_count"),
            "u_depth_mean_mm": row.get("u_depth_mean_mm"),
            "u_depth_median_mm": row.get("u_depth_median_mm"),
            "u_nesting_group_count": row.get("u_nesting_group_count"),
            "u_nesting_max_chain_length": row.get("u_nesting_max_chain_length"),
            "u_adjacent_spacing_min_mm": row.get("u_adjacent_spacing_min_mm"),
            "u_adjacent_spacing_violations": row.get(
                "u_adjacent_spacing_violations"),
            "refold_route_count": row.get("refold_route_count"),
            "crossing_count": row.get("crossing_count"),
            "small_angle_crossing_count": row.get("small_angle_crossing_count"),
            "total_violation_count": row.get("total_violation_count"),
            "mean_length_mm": row.get("mean_length_mm"),
            "total_length_mm": row.get("total_length_mm"),
            "propagation_loss_total_db": row.get("propagation_loss_total_db"),
            "audit_passed": row.get("audit_passed"),
            "topology_validation_passed": row.get("topology_validation_passed"),
            "ports_model_mismatch_count": row.get("ports_model_mismatch_count"),
            "declared_vs_recomputed": {
                "routed_count_diff": row.get("reconcile_routed_count_diff"),
                "length_diff_mm": row.get("reconcile_length_diff_mm"),
                "bend_count_diff": row.get("reconcile_bend_count_diff"),
                "propagation_loss_diff_db": row.get(
                    "reconcile_propagation_loss_diff_db"),
            },
            "failure_taxonomy": {
                "no_candidate_generated": row.get(
                    "failed_no_candidate_generated"),
                "no_legal_candidate": row.get("failed_no_legal_candidate"),
                "budget_or_timeout": row.get("failed_budget_or_timeout"),
                "not_attempted": row.get("failed_not_attempted"),
                "other": row.get("failed_other"),
                "total": row.get("failure_total"),
            },
        })
    for row in combined:
        payload["combined"].append({
            "experiment": row.get("experiment"),
            "algorithm": row.get("algorithm"),
            "routed": row.get("routed"),
            "connections_total": row.get("connections_total"),
            "routing_rate": row.get("routing_rate"),
            "z1_routed": row.get("combined_z1_routed"),
            "z2_routed": row.get("combined_z2_routed"),
            "same_routed": row.get("same_routed"),
            "opposite_routed": row.get("opposite_routed"),
            "adjacent_routed": row.get("adjacent_routed"),
            "path_shapes": {shape: row.get(f"shape_{shape}")
                            for shape in v3_metrics.REQUIRED_SHAPES},
            "u_route_count": row.get("u_route_count"),
            "refold_route_count": row.get("refold_route_count"),
            "same_plane_crossings": row.get("same_plane_crossings"),
            "small_angle_crossing_count": row.get("small_angle_crossing_count"),
            "mean_length_mm": row.get("mean_length_mm"),
            "total_length_mm": row.get("total_length_mm"),
            "propagation_loss_total_db": row.get("propagation_loss_total_db"),
            "cross_plane_projected_overlap_informational": {
                "internal_crossings": row.get(
                    "cross_plane_projected_internal_crossings"),
                "port_coincidences": row.get(
                    "cross_plane_projected_port_coincidences"),
                "pair_count": row.get("cross_plane_projected_pair_count"),
                "grid_peak": row.get("cross_plane_projected_grid_peak"),
                "status": "informational_only_not_a_violation",
            },
            "audit_passed_all_planes": row.get("audit_passed"),
        })
    return v3_metrics._json_safe(payload)  # noqa: SLF001


def _comparison_readme(key_numbers):
    lines = [
        "# V3-Huang comparison/ artifacts",
        "",
        "Generated by `four_side_1024.v3.compare` (metrics/plots owner). Every "
        "number in the JSON/CSV files is recomputed from the saved world-mm "
        "primitives of the runs named in `all_metrics.json`; nothing is estimated.",
        "",
        "## Ten Phase-7 figures",
        "",
        "1. `demand_1024_connector.png` -- V3 1024-channel connector-level demand "
        "(class colours, real counts).",
        "2. `connector_matrix_64x64.png` -- 64x64 weighted connector matrix "
        "(`connector_matrix_64x64.json` has both the directed source->target "
        "matrix, sum = 1024, and the symmetric undirected matrix, sum = 2048).",
        "3. `layouts_z1_abcd.png` -- plane z1 A/B/C/D full 2D layouts.",
        "4. `layouts_z2_abcd.png` -- plane z2 A/B/C/D full 2D layouts.",
        "5. `combined_layouts_abcd.png` -- four combined dual-height layouts "
        "(z1 strong + z2 faint; cross-plane XY projections are NOT conflicts).",
        "6. `overlay_3d_abcd.png` -- four 3D dual-height overlays.",
        "7. `u_routes_only.png`, `refold_routes_only.png` -- same-side U/hairpin "
        "routes only and multi-bend refold routes only (every route drawn).",
        "8. `nested_u_zoom.png` -- local zoom with 10-20 nested U routes, real "
        "route ids annotated, ordered by depth.",
        "9. `class_routed_compare.png` -- same/opposite/adjacent routed counts.",
        "10. `algo_routed_rate_compare.png` -- four-algorithm routed-rate "
        "comparison (z1/512, z2/512, combined/1024).",
        "",
        "## Data files",
        "",
        "* `all_metrics.csv` / `all_metrics.json` -- one row per plane run and per "
        "combined layout (`role` column); full Phase-6 metrics plus declared-vs-"
        "recomputed reconciliation and failure taxonomy.",
        "* `strict_audit_summary_metrics.json` -- metrics-side merge of the "
        "per-plane authoritative `audit_strict.json` files (the validator owns "
        "`strict_audit_summary.json`, which is never overwritten here).",
        "* `key_numbers.json` -- headline numbers per run, contract, audit and "
        "reconciliation summaries (machine-readable for the report).",
        "* `connector_matrix_64x64.json` -- directed + symmetric matrices computed "
        "directly from the frozen CSV.",
        "",
        "## Definitions (shape/geometry)",
        "",
        "* **Path shapes are classified from saved primitives only** -- never from "
        "the CSV relation/pair label. Classes: straight / short_S / L / U / "
        "multi_bend_refold / other.",
        "* **U** = net-180-degree same-side U/hairpin path: `wide_U` (two quarter "
        "arcs with straight track), `hairpin` (two consecutive quarter arcs), "
        "`hairpin_short_S` (one hairpin + one historical short-S lateral shift, "
        "the SAME_HAIRPIN_A/B families).",
        "* **other** = two-quarter step transfer (two quarter arcs with opposite "
        "sweeps, net turn 0 deg -- the FSLW opposite-side `U` transfer family); "
        "the required taxonomy has no step class, so it is kept as `other` and "
        "not counted as U.",
        "* U depth = inward distance from the shared board edge to the deepest "
        "point/track; track_count = straight segments parallel to that edge with "
        "length >= 0.5 mm (0 for pure hairpin-family paths).",
        "* U nesting = inner U's along-edge interval contained in the outer U's "
        "interval with a deeper track; adjacent-U spacing = exact minimum "
        "centreline distance between consecutive U tracks with overlapping "
        "intervals (violation threshold = clearance - 1e-7 = 0.0799999 mm).",
        "* refold = three or more quarter arcs, two or more hairpins, or a short-S "
        "combined with additional quarter arcs; refold-region congestion = "
        "refold-only centreline length per 5x5 mm cell.",
        "",
        "## Honesty / loss policy",
        "",
        "* Same-plane crossings and strict-policy violation counters come from the "
        "authoritative `planes/<A>/<z>/audit_strict.json` (stale files ignored); "
        "the recomputed strict kernel agrees with the validator on the smoke runs.",
        "* Only propagation loss is computed (0.05 dB/cm). Bend loss and crossing "
        "loss are `unknown_uncalibrated`; total optical loss is reported as "
        "`not_computable_missing_calibration`, and the legacy polymer estimate is "
        "never used as glass truth.",
        "* z1 (CSV row 1) and z2 (CSV row 2) are independent 2D planes at model "
        "heights 0.0/0.5; cross-plane XY projections are informational only and "
        "never violations (SPEC §2).",
        "* `key_numbers.json` records the declared-vs-recomputed reconciliation: "
        "routed counts, lengths, bend counts and propagation loss are compared "
        "against the router's own `routes.json` values and reported even if "
        "non-zero.",
        "",
        "Regenerate: `python -m four_side_1024.v3.compare --root <root>`.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def build_comparison(root, comparison_dir=None, recompute=True, quiet=False):
    root = Path(root)
    comparison_dir = (Path(comparison_dir) if comparison_dir
                      else root / "comparison")
    comparison_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    rows = []
    run_info = {}
    plane_audits = {}
    reconciliations = {}
    plane_count = 0
    for algorithm, plane, run_dir in v3_metrics.iter_plane_runs(root):  # noqa: SLF001
        statistics, info = _plane_statistics(run_dir, recompute=recompute)
        audit = _audit_info(run_dir)
        reconciliation = _route_reconciliation(run_dir)
        row = _plane_row(algorithm, plane, statistics, info, audit,
                         reconciliation=reconciliation)
        rows.append(row)
        plane_count += 1
        key = f"planes/{algorithm}/{plane}"
        plane_audits[key] = audit
        reconciliations[key] = reconciliation
        run_info[f"V3_{algorithm}_{plane}"] = {
            "run_dir": str(run_dir), **info,
            "audit": {k: v for k, v in audit.items() if k != "audit_raw"},
            "reconciliation": reconciliation}
        if not quiet and plane_count % 4 == 0:
            print(f"[v3.compare] plane runs loaded: {plane_count}")
    combined_count = 0
    for algorithm, combined_dir in v3_metrics.iter_combined_runs(root):  # noqa: SLF001
        statistics, info = _combined_statistics(combined_dir, root,
                                                recompute=recompute)
        rows.append(_combined_row(algorithm, statistics, info))
        combined_count += 1
        run_info[f"V3_{algorithm}_combined"] = {
            "run_dir": str(combined_dir), **info}
    # ---- all_metrics.csv / json ------------------------------------------
    csv_path = comparison_dir / "all_metrics.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS),
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key))
                             for key in CSV_COLUMNS})
    json_path = comparison_dir / "all_metrics.json"
    payload = {
        "schema": SCHEMA,
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "columns": list(CSV_COLUMNS),
        "counts": {"plane": plane_count, "combined": combined_count},
        "experiments": rows,
        "run_info": run_info,
        "reconciliation": reconciliations,
        "reconciliation_summary": {
            "planes_checked": len(reconciliations),
            "zero_length_diff": sum(
                1 for item in reconciliations.values()
                if abs(item.get("length_diff_mm") or 0.0) <= 1e-9),
            "zero_bend_diff": sum(
                1 for item in reconciliations.values()
                if (item.get("bend_count_diff") or 0) == 0),
            "zero_routed_diff": sum(
                1 for item in reconciliations.values()
                if (item.get("routed_count_diff") or 0) == 0),
            "zero_propagation_loss_diff": sum(
                1 for item in reconciliations.values()
                if abs(item.get("propagation_loss_diff_db") or 0.0) <= 1e-9),
            "max_abs_length_diff_mm": max(
                [abs(item.get("length_diff_mm") or 0.0)
                 for item in reconciliations.values()] or [0.0]),
            "max_abs_bend_diff": max(
                [abs(item.get("bend_count_diff") or 0)
                 for item in reconciliations.values()] or [0]),
            "max_abs_propagation_loss_diff_db": max(
                [abs(item.get("propagation_loss_diff_db") or 0.0)
                 for item in reconciliations.values()] or [0.0]),
            "float_tolerance": 1e-9,
            "float_note": "differences of order 1e-14 caused only by floating-"
                          "point summation order are not treated as data "
                          "discrepancies; every per-plane raw difference is "
                          "recorded in `reconciliation`",
            "note": "declared = values written by the router in routes.json; "
                    "recomputed = four_side_1024.v3.metrics measured from the "
                    "saved world-mm primitives; differences are reported, never "
                    "smoothed away",
        },
        "loss_policy": {
            "propagation_loss_db_per_cm": v3_config.PROPAGATION_LOSS_DB_PER_CM,
            "bend_loss": v3_config.BEND_LOSS,
            "crossing_loss": v3_config.CROSSING_LOSS,
            "total_optical_loss": "not_computable_missing_calibration",
            "legacy_polymer_model": "NOT used as glass truth; omission flagged",
        },
        "shape_policy": {
            "classification_source": "saved world-mm primitives only",
            "never_from_relation_label": True,
            "definitions": v3_metrics.SHAPE_DEFINITIONS,
        },
        "notes": [
            "every number comes from the per-run statistics.json recomputed from "
            "primitives by four_side_1024.v3.metrics; missing runs are marked, "
            "never guessed",
            "z1 (CSV row 1) and z2 (CSV row 2) are independent 2D problems at two "
            "model heights; cross-plane XY projections are informational only and "
            "never violations (SPEC §2)",
            "bend loss and crossing loss are unknown_uncalibrated; only propagation "
            "loss is a computed loss number",
            "classification of path shapes never uses the CSV relation/pair label",
        ],
    }
    audit_summary = _strict_audit_summary(root, plane_audits)
    audit_path = comparison_dir / "strict_audit_summary_metrics.json"
    with open(audit_path, "w", encoding="utf-8") as handle:
        json.dump(v3_metrics._json_safe(audit_summary), handle,  # noqa: SLF001
                  ensure_ascii=False, indent=1)
        handle.write("\n")
    # ---- figures ---------------------------------------------------------
    rendered = []
    skipped = []
    try:
        rendered.append(v3_plots.render_demand_diagram(
            comparison_dir / "demand_1024_connector.png"))
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        skipped.append(f"demand_1024_connector.png: {type(exc).__name__}: {exc}")
    try:
        rendered.append(v3_plots.render_connector_matrix(
            comparison_dir / "connector_matrix_64x64.png"))
    except Exception as exc:  # noqa: BLE001
        skipped.append(f"connector_matrix_64x64.png: {type(exc).__name__}: {exc}")
    if plane_count:
        try:
            rendered.append(v3_plots.render_abcd_layouts(
                root, "z1", comparison_dir / "layouts_z1_abcd.png"))
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"layouts_z1_abcd.png: {type(exc).__name__}: {exc}")
        try:
            rendered.append(v3_plots.render_abcd_layouts(
                root, "z2", comparison_dir / "layouts_z2_abcd.png"))
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"layouts_z2_abcd.png: {type(exc).__name__}: {exc}")
    if combined_count:
        try:
            rendered.append(v3_plots.render_combined_layouts(
                root, comparison_dir / "combined_layouts_abcd.png"))
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"combined_layouts_abcd.png: {type(exc).__name__}: {exc}")
        try:
            rendered.append(v3_plots.render_overlay_3d_grid(
                root, comparison_dir / "overlay_3d_abcd.png"))
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"overlay_3d_abcd.png: {type(exc).__name__}: {exc}")
    # shapes figures: figure (7) + (8) live in shapes/, mirrored into comparison/
    shapes_dir = root / "shapes"
    try:
        v3_plots.render_shapes(root, verbose=False)
        for name in ("u_routes_only.png", "refold_routes_only.png",
                     "nested_u_zoom.png", "shape_mix.png",
                     "u_depth_histogram.png", "u_track_occupancy.png"):
            source = shapes_dir / name
            if name == "refold_routes_only.png":
                continue
            if source.exists():
                target = comparison_dir / name
                try:
                    shutil.copyfile(source, target)
                    rendered.append({"file": str(target),
                                     "kind": f"shapes/{name}",
                                     "source": str(source)})
                except OSError:
                    skipped.append(f"could not mirror {name} into comparison/")
    except Exception as exc:  # noqa: BLE001
        skipped.append(f"shapes figures: {type(exc).__name__}: {exc}")
    refold_info = None
    if plane_count:
        try:
            refold_info = render_refold_routes_only(
                root, comparison_dir / "refold_routes_only.png")
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"refold_routes_only.png: {type(exc).__name__}: {exc}")
    else:
        refold_info = None
    if refold_info:
        rendered.append(refold_info)
    try:
        rendered.append(v3_plots.render_class_routed_compare(
            root, comparison_dir / "class_routed_compare.png"))
    except Exception as exc:  # noqa: BLE001
        skipped.append(f"class_routed_compare.png: {type(exc).__name__}: {exc}")
    try:
        rendered.append(v3_plots.render_algo_routed_rate_compare(
            root, comparison_dir / "algo_routed_rate_compare.png"))
    except Exception as exc:  # noqa: BLE001
        skipped.append(f"algo_routed_rate_compare.png: {type(exc).__name__}: {exc}")
    # metric bars (optional extra, consistent with the previous round)
    combined_rows = [row for row in rows if row.get("scope") == "combined"
                     and row.get("routed") is not None]
    if combined_rows:
        labels = [row["experiment"] for row in combined_rows]
        rendered.append(_bar_figure(
            comparison_dir / "metric_bars_combined_routed.png", labels,
            [("z1 plane /512", PLANE_COLORS["z1"],
              [row.get("combined_z1_routed") for row in combined_rows]),
             ("z2 plane /512", PLANE_COLORS["z2"],
              [row.get("combined_z2_routed") for row in combined_rows]),
             ("combined /1024", "#555555",
              [row.get("routed") for row in combined_rows])],
            "V3 combined routed connections per algorithm (real counts, no "
            "rescaling)", "routed connections", reference=COMBINED_TOTAL,
            reference_label="1024 connections"))
        rendered.append(_bar_figure(
            comparison_dir / "metric_bars_same_side.png", labels,
            [("same-side routed", CLASS_COLORS["same"],
              [row.get("same_routed") for row in combined_rows]),
             ("opposite routed", CLASS_COLORS["opposite"],
              [row.get("opposite_routed") for row in combined_rows]),
             ("adjacent routed", CLASS_COLORS["adjacent"],
              [row.get("adjacent_routed") for row in combined_rows])],
            "V3 combined routed connections by connection class (real counts)",
            "routed connections"))
        rendered.append(_bar_figure(
            comparison_dir / "metric_bars_U.png", labels,
            [("same-side U routes", "#b84040",
              [row.get("u_route_count") for row in combined_rows]),
             ("multi-bend refold routes", "#a545b0",
              [row.get("refold_route_count") for row in combined_rows])],
            "V3 combined same-side U and refold route counts (from primitives)",
            "route count"))
    manifest = {
        "counts": payload["counts"],
        "rendered": [entry.get("file") if isinstance(entry, dict) else entry
                     for entry in rendered],
        "skipped": skipped,
        "strict_audit_summary_metrics": str(audit_path),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    payload["rendered"] = manifest["rendered"]
    payload["skipped"] = skipped
    payload["elapsed_seconds"] = manifest["elapsed_seconds"]
    key_payload = _key_numbers(root, rows, audit_summary,
                               payload["reconciliation_summary"],
                               manifest["rendered"], skipped)
    key_path = comparison_dir / "key_numbers.json"
    with open(key_path, "w", encoding="utf-8") as handle:
        json.dump(key_payload, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    readme_path = comparison_dir / "README.md"
    readme_path.write_text(_comparison_readme(key_payload), encoding="utf-8")
    payload["artifacts"] = {
        "all_metrics_csv": str(csv_path),
        "all_metrics_json": str(json_path),
        "strict_audit_summary_metrics": str(audit_path),
        "key_numbers_json": str(key_path),
        "readme": str(readme_path),
        "connector_matrix_json": str(comparison_dir /
                                     "connector_matrix_64x64.json"),
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(v3_metrics._json_safe(payload), handle,  # noqa: SLF001
                  ensure_ascii=False, indent=1)
        handle.write("\n")
    if not quiet:
        print(json.dumps({
            "comparison_dir": str(comparison_dir),
            "plane_runs": plane_count,
            "combined_runs": combined_count,
            "audits_present": audit_summary.get("audits_present"),
            "rendered": len(manifest["rendered"]),
            "skipped": skipped,
            "elapsed_seconds": manifest["elapsed_seconds"],
        }, ensure_ascii=False))
    return {
        "comparison_dir": str(comparison_dir),
        "all_metrics_csv": str(csv_path),
        "all_metrics_json": str(json_path),
        "strict_audit_summary_metrics": str(audit_path),
        "key_numbers_json": str(key_path),
        "rows": rows,
        "rendered": manifest["rendered"],
        "skipped": skipped,
        "elapsed_seconds": manifest["elapsed_seconds"],
    }


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Build the V3-Huang comparison/ directory (8 plane runs + "
                    "4 combined layouts + ten Phase-7 figures).")
    parser.add_argument("--root",
                        default=str(getattr(v3_config, "OUTPUT_ROOT",
                                            "outputs/four_side_1024_v3_huang_R40_gap30_abcd")))
    parser.add_argument("--comparison-out", help="override comparison directory")
    parser.add_argument("--no-recompute", action="store_true",
                        help="do not recompute missing statistics.json files")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    result = build_comparison(root=args.root,
                              comparison_dir=args.comparison_out,
                              recompute=not args.no_recompute,
                              quiet=args.quiet)
    print(json.dumps({
        "comparison_dir": result["comparison_dir"],
        "plane_rows": sum(1 for row in result["rows"]
                          if row.get("scope") == "plane"),
        "combined_rows": sum(1 for row in result["rows"]
                             if row.get("scope") == "combined"),
        "rendered": len(result["rendered"]),
        "skipped": result["skipped"],
        "elapsed_seconds": result["elapsed_seconds"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
