"""Comparison assets for the sixteen FSLW plane runs and eight combined layouts.

Round-2 deliverable for ``four_side_1024/fslw/SPEC.md`` §6/§8/§10.  Scans

* ``planes/<TOPOLOGY>/<ALGO>/<z1|z2>/``   (16 independent 512-connection runs)
* ``combined/<TOPOLOGY>/<ALGO>/``         (8 dual-height 1024-channel layouts)
* ``sensitivity/<CONFIG>/<TOPOLOGY>/<ALGO>/<PLANE>/`` (Phase-11 matrix)

and writes into ``comparison/``:

* ``all_metrics.csv`` / ``all_metrics.json`` -- one row per plane run, combined
  layout and sensitivity run (flat SPEC §6 metric names, authoritative audit
  counters, loss breakdown, quality metrics);
* ``strict_audit_summary.json`` -- merged authoritative strict-audit verdicts
  (with a stale/missing marker instead of guessed numbers);
* ``eight_group_routed.png`` -- the eight combined layouts, z1/z2/combined
  routed counts on one honest scale;
* ``sensitivity_compare.png`` -- the four-config Phase-11 matrix
  (O legacy / G gap-only / R radius-only / N new process);
* ``layer_2d_compare.png`` -- A/B/C/D x (V1 z1, V1 z2, V2 z1, V2 z2) panels,
  identical axes / linewidth / palette, every panel titled with its real
  routed/512;
* ``crossing_heatmap_compare.png`` -- same-plane crossing heatmaps (4x4 panel
  grid) with the real routed count in every title;
* ``radius_check_all.png`` -- R=40 mm verification summary for all plane runs;
* ``metric_bars_*.png`` -- routed count, mean length, crossings, propagation
  loss, runtime, strict violations;
* a ``rendered`` / ``skipped`` manifest so missing runs are reported, not
  estimated.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.fslw.compare --root \\
        outputs/four_side_1024_fslw_R40_gap30_abcd
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path

import numpy as np

from ..d56.plots_d56 import BOARD_MM, DPI, PAIR_ORDER, _board_frame, \
    draw_connectors, pyplot
from ..outputs import COLORS
from . import config as fslw_config
from . import metrics as fslw_metrics
from . import plots as fslw_plots

SCHEMA = "four_side_1024_fslw_comparison_v1"
TOOL = "four_side_1024.fslw.compare"
TOPOLOGIES = ("V1", "V2")
ALGORITHMS = ("A", "B", "C", "D")
PLANES = ("z1", "z2")
PLANE_TOTAL = 512
COMBINED_TOTAL = 1024
TOPOLOGY_COLORS = {"V1": "#3366bb", "V2": "#b84040"}
ALGORITHM_COLORS = {"A": "#3366bb", "B": "#e3a323", "C": "#00a0a0",
                    "D": "#a545b0"}
PLANE_COLORS = fslw_plots.PLANE_COLORS
MISSING_COLOR = "#bbbbbb"
PANEL_LINEWIDTH = 0.3
PANEL_ALPHA = 0.8
LAYER_COMPARE_FIGSIZE = (20.0, 18.6)
LAYER_COMPARE_COLUMNS = 4

CSV_COLUMNS = (
    "role", "scope", "experiment", "config", "design", "topology", "algorithm",
    "plane", "row", "z_mm",
    "connections_total", "routed", "unrouted", "routing_rate",
    "opposite_success", "adjacent_success",
    "pair_NS_routed", "pair_EW_routed", "pair_EN_routed", "pair_ES_routed",
    "pair_SW_routed", "pair_NW_routed",
    "mean_length_mm", "max_length_mm", "total_length_mm",
    "mean_bend_count", "total_bends", "mean_turns",
    "mean_straight_fraction", "horizontal_straight_fraction",
    "vertical_straight_fraction", "mean_arc_fraction",
    "mean_unnecessary_detour_mm", "mean_unnecessary_detour_vs_euclidean_mm",
    "total_unnecessary_detour_vs_euclidean_mm",
    "crossing_count", "crossing_count_recomputed", "crossing_pair_count",
    "small_angle_crossing_count", "crossing_grid_peak",
    "spacing_violation_pairs", "overlap_pairs", "touch_pairs",
    "crossing_window_overlap_pairs", "double_cross_pairs",
    "crossing_window_excessive_pairs", "self_intersections", "self_overlaps",
    "self_spacing_violations", "radius_violations", "boundary_violations",
    "diagonal_line_violations", "free_arc_violations",
    "total_violation_count",
    "mean_min_gap_mm", "min_min_gap_mm", "median_min_gap_mm",
    "route_length_grid_peak_mm",
    "port_region_length_mm_N", "port_region_length_mm_E",
    "port_region_length_mm_S", "port_region_length_mm_W",
    "arcs_total", "min_arc_radius_mm",
    "propagation_loss_mean_db", "propagation_loss_total_db",
    "propagation_loss_max_db", "propagation_loss_p50_db",
    "bend_loss_status", "crossing_loss_status", "total_optical_loss_status",
    "audit_present", "audit_passed", "audit_policy", "audit_routed_count",
    "audit_checked_count", "audit_failed_count", "audit_error_count",
    "candidate_evaluations", "candidate_evaluations_source",
    "runtime_seconds", "runtime_seconds_source", "evals_per_second",
    "peak_memory_mb", "pair_checks", "eval_budget", "time_budget_seconds",
    "budget_exhausted",
    "same_plane_crossings", "cross_plane_projected_internal_crossings",
    "cross_plane_projected_port_coincidences",
    "cross_plane_projected_pair_count", "cross_plane_projected_grid_peak",
    "combined_z1_routed", "combined_z2_routed",
    "symmetry_diag_routed_pair_fraction", "symmetry_diag_shape_match_fraction",
    "notes",
)


# ---------------------------------------------------------------------------
# loading helpers
# ---------------------------------------------------------------------------
def _load_json(path):
    return fslw_metrics._load_json(path)  # noqa: SLF001


def _statistics_path(run_dir):
    return Path(run_dir) / "statistics.json"


def _read_statistics(run_dir, recompute=True):
    path = _statistics_path(run_dir)
    if path.exists():
        try:
            return _load_json(path), {"statistics_present": True,
                                      "recomputed": False, "path": str(path)}
        except (OSError, json.JSONDecodeError) as exc:
            info = {"statistics_present": False, "recomputed": False,
                    "error": f"{type(exc).__name__}: {exc}"}
    else:
        info = {"statistics_present": False, "recomputed": False}
    if not recompute:
        return None, info
    try:
        statistics = fslw_metrics.build_plane_statistics(  # noqa: SLF001
            Path(run_dir), quiet=True)
        return statistics, {"statistics_present": True, "recomputed": True,
                            "path": str(path)}
    except Exception as exc:  # noqa: BLE001 - reported, never fabricated
        info["error"] = f"{type(exc).__name__}: {exc}"
        return None, info


def _read_combined_statistics(combined_dir, root, recompute=True):
    path = _statistics_path(combined_dir)
    if path.exists():
        try:
            return _load_json(path), {"statistics_present": True,
                                      "recomputed": False, "path": str(path)}
        except (OSError, json.JSONDecodeError) as exc:
            info = {"statistics_present": False, "recomputed": False,
                    "error": f"{type(exc).__name__}: {exc}"}
    else:
        info = {"statistics_present": False, "recomputed": False}
    if not recompute:
        return None, info
    # both plane runs must exist; metrics builds if needed
    try:
        statistics = fslw_metrics.build_combined_statistics(  # noqa: SLF001
            combined_dir, root=root, quiet=True)
        return statistics, {"statistics_present": True, "recomputed": True,
                            "path": str(path)}
    except Exception as exc:  # noqa: BLE001 - reported, never fabricated
        info["error"] = f"{type(exc).__name__}: {exc}"
        return None, info


def _plane_audit_info(run_dir):
    path = Path(run_dir) / "audit_strict.json"
    info = {"audit_present": path.exists(), "audit_file": str(path) if
            path.exists() else None}
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
        "audit_crossing_window_count": payload.get("crossing_window_count"),
        "audit_crossing_window_max_mm": payload.get("crossing_window_max_mm"),
        "audit_sha256": fslw_metrics._sha256(path),  # noqa: SLF001
    })
    return info


def _pair_success(statistics, relation):
    entry = ((statistics or {}).get("by_relation") or {}).get(relation) or {}
    return entry.get("success")


def _pair_field(statistics, pair, field):
    entry = ((statistics or {}).get("by_pair") or {}).get(pair) or {}
    return entry.get(field)


def _loss_value(statistics, field):
    return ((statistics or {}).get("propagation_loss") or {}).get(field)


def _breakdown_status(statistics, key):
    block = ((statistics or {}).get("optical_loss_breakdown") or {}).get(key) or {}
    return block.get("status")


def _plane_row(topology, algorithm, plane, statistics, run_info,
               audit_info=None, role="main_plane"):
    audit_info = audit_info or {}
    row = {
        "role": role,
        "scope": "plane",
        "experiment": (statistics or {}).get("experiment")
        or f"{topology}_{algorithm}_{plane}",
        "topology": topology,
        "algorithm": algorithm,
        "plane": plane,
        "row": fslw_config.PLANE_ROW.get(plane),
        "z_mm": fslw_config.PLANE_Z_MM.get(fslw_config.PLANE_ROW.get(plane, 0)),
        "connections_total": (statistics or {}).get("connections_total",
                                                    PLANE_TOTAL),
        "routed": (statistics or {}).get("routed"),
        "unrouted": (statistics or {}).get("unrouted"),
        "routing_rate": (statistics or {}).get("routing_rate"),
        "opposite_success": _pair_success(statistics, "opposite"),
        "adjacent_success": _pair_success(statistics, "adjacent"),
        "mean_length_mm": (statistics or {}).get("mean_length_mm"),
        "max_length_mm": (statistics or {}).get("max_length_mm"),
        "total_length_mm": (statistics or {}).get("total_length_mm"),
        "mean_bend_count": (statistics or {}).get("mean_bend_count"),
        "total_bends": (statistics or {}).get("total_bends"),
        "mean_turns": (statistics or {}).get("mean_turns"),
        "mean_straight_fraction": (statistics or {}).get("mean_straight_fraction"),
        "horizontal_straight_fraction": (statistics or {}).get(
            "horizontal_straight_fraction"),
        "vertical_straight_fraction": (statistics or {}).get(
            "vertical_straight_fraction"),
        "mean_arc_fraction": (statistics or {}).get("mean_arc_fraction"),
        "mean_unnecessary_detour_mm": (statistics or {}).get(
            "mean_unnecessary_detour_mm"),
        "mean_unnecessary_detour_vs_euclidean_mm": (statistics or {}).get(
            "mean_unnecessary_detour_vs_euclidean_mm"),
        "total_unnecessary_detour_vs_euclidean_mm": (statistics or {}).get(
            "total_unnecessary_detour_vs_euclidean_mm"),
        "crossing_count": (statistics or {}).get("crossing_count"),
        "crossing_count_recomputed": (statistics or {}).get(
            "crossing_count_recomputed"),
        "crossing_pair_count": (statistics or {}).get("crossing_pair_count"),
        "small_angle_crossing_count": (statistics or {}).get(
            "small_angle_crossing_count"),
        "crossing_grid_peak": (statistics or {}).get("crossing_grid_peak"),
        "spacing_violation_pairs": (statistics or {}).get(
            "spacing_violation_pairs"),
        "overlap_pairs": (statistics or {}).get("overlap_pairs"),
        "touch_pairs": (statistics or {}).get("touch_pairs"),
        "crossing_window_overlap_pairs": (statistics or {}).get(
            "crossing_window_overlap_pairs"),
        "double_cross_pairs": (statistics or {}).get("double_cross_pairs"),
        "crossing_window_excessive_pairs": (statistics or {}).get(
            "crossing_window_excessive_pairs"),
        "self_intersections": (statistics or {}).get("self_intersections"),
        "self_overlaps": (statistics or {}).get("self_overlaps"),
        "self_spacing_violations": (statistics or {}).get(
            "self_spacing_violations"),
        "radius_violations": (statistics or {}).get("radius_violations"),
        "boundary_violations": (statistics or {}).get("boundary_violations"),
        "diagonal_line_violations": (statistics or {}).get(
            "diagonal_line_violations"),
        "free_arc_violations": (statistics or {}).get("free_arc_violations"),
        "total_violation_count": (statistics or {}).get("total_violation_count"),
        "mean_min_gap_mm": (statistics or {}).get("mean_min_gap_mm"),
        "min_min_gap_mm": (statistics or {}).get("min_min_gap_mm"),
        "median_min_gap_mm": (statistics or {}).get("median_min_gap_mm"),
        "route_length_grid_peak_mm": (statistics or {}).get(
            "route_length_grid_peak_mm"),
        "arcs_total": ((statistics or {}).get("geometry_checks") or {}).get(
            "num_arcs_total"),
        "min_arc_radius_mm": ((statistics or {}).get("geometry_checks") or {}).get(
            "min_arc_radius_mm"),
        "propagation_loss_mean_db": _loss_value(statistics, "mean_db"),
        "propagation_loss_total_db": _loss_value(statistics, "value_db"),
        "propagation_loss_max_db": _loss_value(statistics, "max_db"),
        "propagation_loss_p50_db": (((statistics or {}).get(
            "propagation_loss_detail") or {}).get("percentiles") or {}).get("p50"),
        "bend_loss_status": _breakdown_status(statistics, "bend_loss"),
        "crossing_loss_status": _breakdown_status(statistics, "crossing_loss"),
        "total_optical_loss_status": _breakdown_status(statistics,
                                                       "total_optical_loss"),
        "audit_present": bool(audit_info.get("audit_present")),
        "audit_passed": (statistics or {}).get("audit_passed")
        if (statistics or {}).get("audit_passed") is not None
        else audit_info.get("audit_passed"),
        "audit_policy": (statistics or {}).get("audit_policy")
        or audit_info.get("audit_policy"),
        "audit_routed_count": (statistics or {}).get("audit_routed_count")
        or audit_info.get("audit_routed_count"),
        "audit_checked_count": (statistics or {}).get("audit_checked_count")
        or audit_info.get("audit_checked_count"),
        "audit_failed_count": (statistics or {}).get("audit_failed_count")
        if (statistics or {}).get("audit_failed_count") is not None
        else audit_info.get("audit_failed_count"),
        "audit_error_count": (statistics or {}).get("audit_error_count")
        if (statistics or {}).get("audit_error_count") is not None
        else audit_info.get("audit_error_count"),
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
        "symmetry_diag_routed_pair_fraction": (
            ((statistics or {}).get("symmetry") or {}).get("diag") or {}).get(
                "routed_pair_fraction"),
        "symmetry_diag_shape_match_fraction": (
            ((statistics or {}).get("symmetry") or {}).get("diag") or {}).get(
                "shape_match_fraction"),
        "notes": run_info.get("error") or "",
    }
    for pair in PAIR_ORDER:
        row[f"pair_{pair}_routed"] = _pair_field(statistics, pair, "success")
    for side in "NESW":
        row[f"port_region_length_mm_{side}"] = (
            (statistics or {}).get("port_region_length_mm") or {}).get(side)
    return row


def _combined_row(topology, algorithm, statistics, run_info):
    by_plane = (statistics or {}).get("by_plane") or {}
    projection = (statistics or {}).get("cross_plane_projected_overlap") or {}
    row = {
        "role": "main_combined",
        "scope": "combined",
        "experiment": (statistics or {}).get("experiment")
        or f"{topology}_{algorithm}_combined",
        "topology": topology,
        "algorithm": algorithm,
        "plane": "z1+z2",
        "row": None,
        "z_mm": None,
        "connections_total": (statistics or {}).get("connections_total",
                                                    COMBINED_TOTAL),
        "routed": (statistics or {}).get("routed"),
        "unrouted": (statistics or {}).get("unrouted"),
        "routing_rate": (statistics or {}).get("routing_rate"),
        "opposite_success": _pair_success(statistics, "opposite"),
        "adjacent_success": _pair_success(statistics, "adjacent"),
        "mean_length_mm": (statistics or {}).get("mean_length_mm"),
        "total_length_mm": (statistics or {}).get("total_length_mm"),
        "total_bends": (statistics or {}).get("total_bends"),
        "mean_straight_fraction": (statistics or {}).get("mean_straight_fraction"),
        "total_unnecessary_detour_vs_euclidean_mm": None,
        "crossing_count": (statistics or {}).get("same_plane_crossings"),
        "crossing_count_recomputed": (statistics or {}).get(
            "same_plane_crossings"),
        "small_angle_crossing_count": (statistics or {}).get(
            "small_angle_crossing_count"),
        "total_violation_count": ((statistics or {}).get("violations") or {}).get(
            "same_plane_total"),
        "propagation_loss_total_db": ((statistics or {}).get(
            "propagation_loss") or {}).get("value_db"),
        "propagation_loss_mean_db": ((statistics or {}).get(
            "propagation_loss") or {}).get("mean_db"),
        "bend_loss_status": "unknown_uncalibrated",
        "crossing_loss_status": "unknown_uncalibrated",
        "total_optical_loss_status": _breakdown_status(statistics,
                                                       "total_optical_loss"),
        "same_plane_crossings": (statistics or {}).get("same_plane_crossings"),
        "cross_plane_projected_internal_crossings": projection.get(
            "cross_plane_projected_internal_crossings"),
        "cross_plane_projected_port_coincidences": projection.get(
            "cross_plane_projected_port_coincidences"),
        "cross_plane_projected_pair_count": projection.get(
            "cross_plane_projected_pair_count"),
        "cross_plane_projected_grid_peak": projection.get(
            "cross_plane_projected_grid_peak"),
        "combined_z1_routed": (by_plane.get("z1") or {}).get("routed"),
        "combined_z2_routed": (by_plane.get("z2") or {}).get("routed"),
        "candidate_evaluations": (statistics or {}).get("candidate_evaluations"),
        "runtime_seconds": (statistics or {}).get("runtime_seconds"),
        "audit_present": bool((statistics or {}).get("audit_passed_all_planes")),
        "audit_passed": (statistics or {}).get("audit_passed_all_planes"),
        "notes": run_info.get("error") or "",
    }
    for pair in PAIR_ORDER:
        row[f"pair_{pair}_routed"] = _pair_field(statistics, pair, "success")
    return row


def _sensitivity_rows(root, recompute=True, quiet=True):
    rows = []
    for (config_name, topology, algorithm, plane, run_dir) in \
            fslw_metrics.iter_sensitivity_runs(root):  # noqa: SLF001
        statistics, info = _read_statistics(run_dir, recompute=recompute)
        audit = _plane_audit_info(run_dir)
        row = _plane_row(topology, algorithm, plane, statistics, info, audit,
                         role="sensitivity")
        row["scope"] = "sensitivity_plane"
        row["experiment"] = (statistics or {}).get("experiment") \
            or f"{config_name}_{topology}_{algorithm}_{plane}"
        row["config"] = config_name
        rows.append(row)
    return rows


def _c_sweep_rows(root, recompute=True):
    """C-sweep runs document the frozen C design (role=c_sweep, not official)."""
    rows = []
    for (design, topology, plane, run_dir) in \
            fslw_metrics.iter_c_sweep_runs(root):  # noqa: SLF001
        statistics, info = _read_statistics(run_dir, recompute=recompute)
        audit = _plane_audit_info(run_dir)
        row = _plane_row(topology, "", plane, statistics, info, audit,
                         role="c_sweep")
        row["scope"] = "c_sweep_plane"
        row["experiment"] = (statistics or {}).get("experiment") \
            or f"{design}_{topology}_{plane}"
        row["design"] = design
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------
def _bar_figure(path, labels, series, title, ylabel, reference=None,
                reference_label=None):
    """Grouped bars with one series per colour/label; fixed honest scale."""
    plt = pyplot()
    fig, ax = plt.subplots(figsize=(13.0, 5.2))
    positions = np.arange(len(labels))
    width = 0.8 / max(1, len(series))
    for index, (name, colour, values) in enumerate(series):
        heights = [0.0 if value is None else float(value) for value in values]
        offset = (index - (len(series) - 1) / 2.0) * width
        bars = ax.bar(positions + offset, heights, width=width * 0.92,
                      color=colour, edgecolor="#222222", linewidth=0.35,
                      label=name)
        for position, bar, value in zip(positions + offset, bars, values):
            if value is None:
                ax.text(position, 0.0, "n/a", ha="center", va="bottom",
                        fontsize=6.0, color="#666666")
            else:
                ax.text(position, bar.get_height(), f"{value:g}",
                        ha="center", va="bottom", fontsize=6.0, rotation=90)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=0 if len(labels) <= 6 else 30,
                       ha="center" if len(labels) <= 6 else "right",
                       fontsize=7.5)
    if reference is not None:
        ax.axhline(reference, color="#333333", linewidth=0.8, linestyle="--",
                   label=reference_label or str(reference))
    ax.set_ylabel(ylabel, fontsize=8.5)
    ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    ax.legend(fontsize=7.5, loc="upper right")
    ax.set_title(title, fontsize=10.0)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "kind": "bar", "labels": labels,
            "series": [name for name, _, _ in series]}


def render_eight_group_and_sensitivity(root, comparison_dir):
    rendered = []
    info = fslw_plots.render_eight_group_comparison(
        root, comparison_dir / "eight_group_routed.png")
    if info:
        rendered.append(info)
    info = fslw_plots.render_sensitivity_comparison(
        root, comparison_dir / "sensitivity_compare.png")
    if info:
        rendered.append(info)
    return rendered


def render_metric_bars(rows, comparison_dir):
    rendered = []
    combined = [row for row in rows if row.get("scope") == "combined"
                and row.get("routed") is not None]
    if not combined:
        return rendered
    labels = [f"{row['topology']}_{row['algorithm']}" for row in combined]
    rendered.append(_bar_figure(
        comparison_dir / "metric_bars_routed.png", labels,
        [("combined /1024", "#555555", [row.get("routed") for row in combined]),
         ("z1 /512", PLANE_COLORS["z1"],
          [row.get("combined_z1_routed") for row in combined]),
         ("z2 /512", PLANE_COLORS["z2"],
          [row.get("combined_z2_routed") for row in combined])],
        "Routed connections per combined layout (real counts, no rescaling)",
        "routed connections", reference=COMBINED_TOTAL,
        reference_label="1024 connections"))
    rendered.append(_bar_figure(
        comparison_dir / "metric_bars_length.png", labels,
        [("mean length (mm)", "#3366bb",
          [row.get("mean_length_mm") for row in combined])],
        "Mean routed length per combined layout", "mean length (mm)"))
    rendered.append(_bar_figure(
        comparison_dir / "metric_bars_crossings.png", labels,
        [("same-plane crossings", "#b84040",
          [row.get("same_plane_crossings") for row in combined])],
        "Same-plane crossings per combined layout "
        "(cross-plane projections are informational, never violations)",
        "same-plane crossings"))
    rendered.append(_bar_figure(
        comparison_dir / "metric_bars_loss.png", labels,
        [("mean propagation loss per route (dB)", "#00a0a0",
          [row.get("propagation_loss_mean_db") for row in combined]),
         ("total propagation loss (dB)", "#a545b0",
          [row.get("propagation_loss_total_db") for row in combined])],
        "Propagation-only optical loss (0.05 dB/cm). Bend/crossing loss unknown, "
        "total optical loss not computable", "loss (dB)"))
    rendered.append(_bar_figure(
        comparison_dir / "metric_bars_runtime.png", labels,
        [("runtime (s)", "#666666",
          [row.get("runtime_seconds") for row in combined])],
        "Recorded two-plane runtime per combined layout", "runtime (s)"))
    rendered.append(_bar_figure(
        comparison_dir / "metric_bars_strict_violations.png", labels,
        [("strict violation counters (both planes)", "#b84040",
          [row.get("total_violation_count") for row in combined])],
        "Strict-audit violation counters per combined layout "
        "(authoritative audit_strict.json merged)", "violation count"))
    return rendered


def render_plane_bars(rows, comparison_dir):
    planes = [row for row in rows if row.get("scope") == "plane"
              and row.get("routed") is not None]
    if not planes:
        return []
    labels = [f"{row['topology']}_{row['algorithm']}_{row['plane']}"
              for row in planes]
    colours = [PLANE_COLORS.get(row["plane"], MISSING_COLOR) for row in planes]
    plt = pyplot()
    fig, ax = plt.subplots(figsize=(14.0, 5.2))
    positions = np.arange(len(labels))
    values = [row.get("routed") for row in planes]
    ax.bar(positions, [0 if value is None else value for value in values],
           color=colours, edgecolor="#222222", linewidth=0.35, width=0.72)
    for position, value in zip(positions, values):
        ax.text(position, 0 if value is None else value,
                "n/a" if value is None else f"{value}", ha="center",
                va="bottom", fontsize=6.5, rotation=90)
    ax.axhline(PLANE_TOTAL, color="#333333", linewidth=0.8, linestyle="--",
               label="512 connections per plane")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=7.0)
    ax.set_ylabel("routed connections", fontsize=8.5)
    ax.set_ylim(0.0, PLANE_TOTAL * 1.12)
    ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    ax.legend(fontsize=7.5, loc="upper right")
    ax.set_title("All 16 FSLW plane runs: routed/512 under R=40 mm / 30 µm gap "
                 "(z1 = opposite plane, z2 = adjacent plane)", fontsize=10.0)
    fig.tight_layout()
    path = comparison_dir / "plane_routed_compare.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return [{"file": str(path), "kind": "plane_bars"}]


def render_layer_2d_compare(root, comparison_dir):
    """A/B/C/D x (V1 z1, V1 z2, V2 z1, V2 z2) panels, identical style."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    columns = [("V1", "z1"), ("V1", "z2"), ("V2", "z1"), ("V2", "z2")]
    fig, axes = plt.subplots(len(ALGORITHMS), len(columns),
                             figsize=LAYER_COMPARE_FIGSIZE, squeeze=False)
    rendered_panels = []
    for row_index, algorithm in enumerate(ALGORITHMS):
        for column_index, (topology, plane) in enumerate(columns):
            ax = axes[row_index][column_index]
            run_dir = fslw_metrics._plane_run_dir(root, topology, algorithm, plane)  # noqa: SLF001
            data = None
            if (run_dir / "routes.json").exists():
                try:
                    data = fslw_plots.load_plane(run_dir)
                except Exception:  # noqa: BLE001 - blank panel instead of crash
                    data = None
            if not data or not data["routed"]:
                ax.axis("off")
                ax.set_title(f"{topology}_{algorithm} plane {plane}\nmissing plane run",
                             fontsize=8.5, color="#888888")
                continue
            route_ids = [route_id for route_id in data["curves"]
                         if len(data["curves"][route_id]) >= 2]
            segments = [data["curves"][route_id] for route_id in route_ids]
            colours = [COLORS[data["meta_routes"][route_id]["pair"]]
                       for route_id in route_ids]
            if segments:
                ax.add_collection(LineCollection(segments, colors=colours,
                                                 linewidths=PANEL_LINEWIDTH,
                                                 alpha=PANEL_ALPHA, zorder=3))
            _board_frame(ax)
            draw_connectors(ax, data.get("connectors") or [], depth_mm=3.0,
                            label_fontsize=0.0)
            routed = len(data["routed"])
            statistics = data.get("statistics") or {}
            crossings = statistics.get("crossing_count")
            title = [f"{topology}_{algorithm} plane {plane} | "
                     f"{routed}/{PLANE_TOTAL} routed "
                     f"({routed / PLANE_TOTAL:.1%})"]
            if crossings is not None:
                title.append(f"same-plane crossings {int(crossings)}")
            ax.set_title("\n".join(title), fontsize=8.0)
            ax.tick_params(labelsize=5.5)
            rendered_panels.append(f"{topology}_{algorithm}_{plane}")
    handles = [Line2D([0], [0], color=COLORS[pair], linewidth=2.0, label=pair)
               for pair in PAIR_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=len(PAIR_ORDER),
               fontsize=8.0, framealpha=0.9)
    fig.suptitle(
        "FSLW R=40 mm / 30 µm: all 16 plane runs (rows A/B/C/D, columns "
        "V1-z1, V1-z2, V2-z1, V2-z2) | identical axes [-9,159]^2, linewidth and "
        "side-pair palette | titles state the real routed/512", fontsize=12.0)
    fig.tight_layout(rect=(0.0, 0.03, 1.0, 0.965))
    path = comparison_dir / "layer_2d_compare.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "kind": "layer_2d_compare",
            "panels": rendered_panels}


def render_crossing_heatmap_compare(root, comparison_dir):
    """4x4 same-plane crossing heatmaps from the plane statistics."""
    plt = pyplot()
    cells = int(round(BOARD_MM / fslw_metrics.GRID_MM))
    columns = [("V1", "z1"), ("V1", "z2"), ("V2", "z1"), ("V2", "z2")]
    fig, axes = plt.subplots(len(ALGORITHMS), len(columns),
                             figsize=(25.0, 23.0), squeeze=False)
    rendered_panels = []
    for row_index, algorithm in enumerate(ALGORITHMS):
        for column_index, (topology, plane) in enumerate(columns):
            ax = axes[row_index][column_index]
            run_dir = fslw_metrics._plane_run_dir(root, topology, algorithm, plane)  # noqa: SLF001
            statistics = None
            if (run_dir / "statistics.json").exists():
                try:
                    statistics = _load_json(run_dir / "statistics.json")
                except (OSError, json.JSONDecodeError):
                    statistics = None
            if not statistics:
                ax.axis("off")
                ax.set_title(f"{topology}_{algorithm}_{plane}\nno statistics",
                             fontsize=8.5, color="#888888")
                continue
            crossings = []
            for item in statistics.get("crossing_points_sample") or []:
                crossings.append(item)
            counts = np.zeros((cells, cells))
            for item in crossings:
                ix = min(cells - 1, max(0, int(math.floor(
                    float(item["x_mm"]) / fslw_metrics.GRID_MM))))
                iy = min(cells - 1, max(0, int(math.floor(
                    float(item["y_mm"]) / fslw_metrics.GRID_MM))))
                counts[iy, ix] += 1
            image = ax.imshow(counts, origin="lower",
                              extent=(0.0, BOARD_MM, 0.0, BOARD_MM),
                              cmap="magma", interpolation="nearest")
            fig.colorbar(image, ax=ax, fraction=0.046, pad=0.02)
            _board_frame(ax)
            routed = statistics.get("routed")
            total_crossings = statistics.get("crossing_count")
            ax.set_title(
                f"{topology}_{algorithm} plane {plane} | {routed}/{PLANE_TOTAL} "
                f"routed\nsame-plane crossings {total_crossings} "
                f"(sample shown: {len(crossings)})", fontsize=8.0)
            ax.tick_params(labelsize=5.5)
            rendered_panels.append(f"{topology}_{algorithm}_{plane}")
    fig.suptitle(
        "FSLW R=40 mm / 30 µm: same-plane crossing heatmaps for all 16 plane "
        "runs (5 x 5 mm cells). Different heights are never compared; "
        "cross-plane XY projections are informational only.", fontsize=12.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    path = comparison_dir / "crossing_heatmap_compare.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "kind": "crossing_heatmap_compare",
            "panels": rendered_panels}


def render_radius_check_all(rows, comparison_dir):
    """R=40 mm verification summary across all 16 plane runs."""
    planes = [row for row in rows if row.get("scope") == "plane"
              and row.get("arcs_total") is not None]
    if not planes:
        return None
    plt = pyplot()
    fig, axes = plt.subplots(1, 2, figsize=(15.0, 5.4))
    ax = axes[0]
    labels = [f"{row['topology']}_{row['algorithm']}_{row['plane']}"
              for row in planes]
    positions = np.arange(len(labels))
    arcs = [row.get("arcs_total") or 0 for row in planes]
    violations = [row.get("radius_violations") or 0 for row in planes]
    ax.bar(positions, arcs, color="#3366bb", edgecolor="#222222",
           linewidth=0.35, label="arcs checked")
    ax.bar(positions, violations, color="#b84040", edgecolor="#222222",
           linewidth=0.35, label="radius violations")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=6.5)
    ax.set_ylabel("arc count", fontsize=8.5)
    ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    ax.legend(fontsize=7.5)
    ax.set_title("arcs checked and radius violations per plane run",
                 fontsize=9.5)
    ax = axes[1]
    ax.axis("off")
    target = float(fslw_config.RADIUS_MM)
    lines = [f"required radius R = {target:g} mm (fixed_radius_40mm=True)",
             f"tolerance {1e-9:g} mm", "",
             f"{'plane':<22}{'arcs':>7}{'min r':>9}{'viol':>7}"]
    for row in planes:
        lines.append(
            f"{row['topology'] + '_' + row['algorithm'] + '_' + row['plane']:<22}"
            f"{(row.get('arcs_total') or 0):>7}"
            f"{(row.get('min_arc_radius_mm') if row.get('min_arc_radius_mm') is not None else 0):>9.4f}"
            f"{(row.get('radius_violations') or 0):>7}")
    total_violations = sum(row.get("radius_violations") or 0 for row in planes)
    lines.extend(["", f"total radius violations: {total_violations}",
                  "every arc must be exactly R=40 mm (SPEC §1/§3)"])
    ax.text(0.0, 1.0, "\n".join(lines), ha="left", va="top", fontsize=7.5,
            family="monospace")
    ax.set_title("R = 40 mm verification summary", fontsize=9.5)
    fig.suptitle("FSLW R=40 mm fixed-radius check across the 16 plane runs",
                 fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    path = comparison_dir / "radius_check_all.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "kind": "radius_check_all",
            "total_radius_violations": total_violations,
            "planes": len(planes)}


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def render_c_sweep_designs(rows, comparison_dir):
    """C-sweep design documentation figure (not part of the official 8 groups)."""
    sweep = [row for row in rows if row.get("role") == "c_sweep"
             and row.get("routed") is not None]
    if not sweep:
        return None
    plt = pyplot()
    designs = sorted({row.get("design") for row in sweep if row.get("design")})
    columns = [("V1", "z1"), ("V1", "z2"), ("V2", "z1"), ("V2", "z2")]
    labels = designs
    positions = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(13.0, 5.2))
    width = 0.8 / max(1, len(columns))
    for index, (topology, plane) in enumerate(columns):
        values = []
        for design in designs:
            match = [row for row in sweep
                     if row.get("design") == design
                     and row.get("topology") == topology
                     and row.get("plane") == plane]
            values.append(match[0].get("routed") if match else None)
        heights = [0.0 if value is None else float(value) for value in values]
        offset = (index - (len(columns) - 1) / 2.0) * width
        ax.bar(positions + offset, heights, width=width * 0.92,
               color=PLANE_COLORS[plane] if topology == "V1" else "#8c8c8c",
               edgecolor="#222222", linewidth=0.35,
               label=f"{topology}-{plane}")
        for position, value in zip(positions + offset, values):
            if value is not None:
                ax.text(position, value, f"{value}", ha="center", va="bottom",
                        fontsize=6.0, rotation=90)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=7.5)
    ax.set_ylabel("routed connections /512", fontsize=8.5)
    ax.set_ylim(0.0, PLANE_TOTAL * 1.12)
    ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    ax.legend(fontsize=7.5, loc="upper right")
    ax.set_title("C-sweep design documentation (role=c_sweep; NOT part of the "
                 "eight official combined layouts)", fontsize=10.0)
    fig.tight_layout()
    path = comparison_dir / "c_sweep_designs.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "kind": "c_sweep_designs",
            "designs": designs}


def build_comparison(root, comparison_dir=None, recompute=True, quiet=False):
    root = Path(root)
    comparison_dir = (Path(comparison_dir) if comparison_dir
                      else root / "comparison")
    comparison_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    # The validator owns the canonical comparison/strict_audit_summary.json
    # (task-4); this module writes strict_audit_summary_metrics.json and only
    # references the validator file instead of overwriting it.
    validator_summary = {"file": None, "present": False, "schema": None}
    canonical = comparison_dir / "strict_audit_summary.json"
    if canonical.exists():
        validator_summary["file"] = str(canonical)
        validator_summary["present"] = True
        try:
            payload = _load_json(canonical)
            validator_summary["schema"] = (payload.get("schema")
                                           if isinstance(payload, dict) else None)
        except (OSError, json.JSONDecodeError):
            validator_summary["schema"] = None
    rows = []
    run_info = {}
    strict_summary = {
        "schema": "four_side_1024_fslw_strict_audit_summary_v1",
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "policy": "strict",
        "radius_mm": fslw_config.RADIUS_MM,
        "edge_gap_mm": fslw_config.EDGE_GAP_MM,
        "clearance_mm": fslw_config.CLEARANCE_MM,
        "experiments": {}, "missing_audits": [], "rendered": [], "skipped": [],
        "validator_canonical_summary": validator_summary,
        "note": "this file (strict_audit_summary_metrics.json) is the metrics-side "
                "merge of the per-plane authoritative audit_strict.json files; the "
                "canonical validator sweep summary lives in "
                "comparison/strict_audit_summary.json and is only referenced here",
    }
    # plane runs
    plane_count = 0
    for topology, algorithm, plane, run_dir in fslw_metrics.iter_plane_runs(root):  # noqa: SLF001
        statistics, info = _read_statistics(run_dir, recompute=recompute)
        audit = _plane_audit_info(run_dir)
        row = _plane_row(topology, algorithm, plane, statistics, info, audit)
        rows.append(row)
        plane_count += 1
        run_info[f"{topology}_{algorithm}_{plane}"] = {
            "run_dir": str(run_dir), **info, "audit": audit}
        key = f"planes/{topology}/{algorithm}/{plane}"
        if audit.get("audit_present"):
            strict_summary["experiments"][key] = {
                "file": audit.get("audit_file"),
                "passed": audit.get("audit_passed"),
                "policy": audit.get("audit_policy"),
                "routed_count": audit.get("audit_routed_count"),
                "checked_count": audit.get("audit_checked_count"),
                "failed_count": audit.get("audit_failed_count"),
                "error_count": audit.get("audit_error_count"),
                "crossing_count": audit.get("audit_crossing_count"),
                "spacing_violation_pairs": audit.get(
                    "audit_spacing_violation_pairs"),
                "violation_pair_count": audit.get("audit_violation_pair_count"),
                "runtime_seconds": audit.get("audit_runtime_seconds"),
                "crossing_window_count": audit.get("audit_crossing_window_count"),
                "crossing_window_max_mm": audit.get(
                    "audit_crossing_window_max_mm"),
                "sha256": audit.get("audit_sha256"),
            }
        else:
            strict_summary["missing_audits"].append(key)
        if not quiet and plane_count % 4 == 0:
            print(f"[fslw.compare] plane runs loaded: {plane_count}")
    # combined runs
    combined_count = 0
    for topology, algorithm, combined_dir in fslw_metrics.iter_combined_runs(root):  # noqa: SLF001
        statistics, info = _read_combined_statistics(combined_dir, root,
                                                     recompute=recompute)
        row = _combined_row(topology, algorithm, statistics, info)
        rows.append(row)
        combined_count += 1
        run_info[f"{topology}_{algorithm}_combined"] = {
            "run_dir": str(combined_dir), **info}
    # sensitivity runs
    sensitivity_rows = _sensitivity_rows(root, recompute=recompute, quiet=quiet)
    rows.extend(sensitivity_rows)
    # C-sweep runs (documentation of the frozen C design; role=c_sweep)
    c_sweep_rows = _c_sweep_rows(root, recompute=recompute)
    rows.extend(c_sweep_rows)

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
        "counts": {"plane": plane_count, "combined": combined_count,
                   "sensitivity_plane": len(sensitivity_rows),
                   "c_sweep_plane": len(c_sweep_rows)},
        "experiments": rows,
        "run_info": run_info,
        "role_policy": {
            "main_plane": "the sixteen official plane runs planes/<T>/<A>/<z1|z2>",
            "main_combined": "the eight official dual-height layouts "
                             "combined/<T>/<A> (only these enter the 8-group "
                             "comparison figures)",
            "sensitivity": "Phase-11 matrix; own process block (radius/gap vary), "
                           "never assumed to be R=40",
            "c_sweep": "C-design ablation documentation only; NOT part of the "
                       "eight official combined layouts",
        },
        "loss_policy": {
            "propagation_loss_db_per_cm": fslw_config.PROPAGATION_LOSS_DB_PER_CM,
            "bend_loss": fslw_config.BEND_LOSS,
            "crossing_loss": fslw_config.CROSSING_LOSS,
            "total_optical_loss": "not_computable_missing_calibration",
            "legacy_polymer_model": "NOT used as glass truth; omission flagged",
        },
        "notes": [
            "every number comes from the per-run statistics.json recomputed from "
            "primitives by four_side_1024.fslw.metrics; missing runs are marked, "
            "never guessed",
            "z1 (row 1, 512 opposite) and z2 (row 2, 512 adjacent) are independent "
            "2D problems at two model heights; cross-plane XY projections are "
            "informational only and never violations (SPEC §2)",
            "bend loss and crossing loss are unknown_uncalibrated; only the "
            "propagation arm (0.05 dB/cm) is a computed loss number",
        ],
    }
    # ---- strict audit summary -------------------------------------------
    audited = list(strict_summary["experiments"].values())
    strict_summary["audits_present"] = len(audited)
    strict_summary["audits_expected"] = plane_count
    strict_summary["all_available_passed"] = bool(audited) and all(
        entry.get("passed") for entry in audited)
    audit_path = comparison_dir / "strict_audit_summary_metrics.json"
    with open(audit_path, "w", encoding="utf-8") as handle:
        json.dump(fslw_metrics._json_safe(strict_summary), handle,  # noqa: SLF001
                  ensure_ascii=False, indent=1)
        handle.write("\n")

    # ---- figures ---------------------------------------------------------
    rendered = []
    rendered.extend(render_eight_group_and_sensitivity(root, comparison_dir))
    rendered.extend(render_metric_bars(rows, comparison_dir))
    rendered.extend(render_plane_bars(rows, comparison_dir))
    if plane_count:
        rendered.append(render_layer_2d_compare(root, comparison_dir))
        rendered.append(render_crossing_heatmap_compare(root, comparison_dir))
        radius_info = render_radius_check_all(rows, comparison_dir)
        if radius_info:
            rendered.append(radius_info)
    c_sweep_info = render_c_sweep_designs(rows, comparison_dir)
    if c_sweep_info:
        rendered.append(c_sweep_info)
    skipped = []
    if not combined_count:
        skipped.append("no combined runs yet (need both plane runs per group)")
    if not sensitivity_rows:
        skipped.append("no sensitivity runs yet (Phase-11 matrix)")
    if not c_sweep_rows:
        skipped.append("no c_sweep runs yet (C-design documentation)")

    manifest = {
        "counts": payload["counts"],
        "rendered": [entry.get("file") if isinstance(entry, dict) else entry
                     for entry in rendered],
        "skipped": skipped,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    payload["rendered"] = manifest["rendered"]
    payload["skipped"] = skipped
    payload["elapsed_seconds"] = manifest["elapsed_seconds"]
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(fslw_metrics._json_safe(payload), handle,  # noqa: SLF001
                  ensure_ascii=False, indent=1)
        handle.write("\n")
    strict_summary["rendered"] = manifest["rendered"]
    strict_summary["skipped"] = skipped
    with open(audit_path, "w", encoding="utf-8") as handle:
        json.dump(fslw_metrics._json_safe(strict_summary), handle,  # noqa: SLF001
                  ensure_ascii=False, indent=1)
        handle.write("\n")
    if not quiet:
        print(json.dumps({
            "comparison_dir": str(comparison_dir),
            "plane_runs": plane_count,
            "combined_runs": combined_count,
            "sensitivity_runs": len(sensitivity_rows),
            "c_sweep_runs": len(c_sweep_rows),
            "audits_present": strict_summary["audits_present"],
            "rendered": len(manifest["rendered"]),
            "skipped": skipped,
            "elapsed_seconds": manifest["elapsed_seconds"],
        }, ensure_ascii=False))
    return {
        "comparison_dir": str(comparison_dir),
        "all_metrics_csv": str(csv_path),
        "all_metrics_json": str(json_path),
        "strict_audit_summary": str(audit_path),
        "rows": rows,
        "rendered": manifest["rendered"],
        "skipped": skipped,
        "elapsed_seconds": manifest["elapsed_seconds"],
    }


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Build the FSLW comparison/ directory (16 plane + 8 combined "
                    "+ sensitivity runs).")
    parser.add_argument("--root",
                        default="outputs/four_side_1024_fslw_R40_gap30_abcd")
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
        "sensitivity_rows": sum(1 for row in result["rows"]
                                if row.get("scope") == "sensitivity_plane"),
        "rendered": len(result["rendered"]),
        "skipped": result["skipped"],
        "elapsed_seconds": result["elapsed_seconds"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
