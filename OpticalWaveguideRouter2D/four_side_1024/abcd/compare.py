"""Comparison assets for the eight ABCD experiments (SPEC §4/§6).

Phase 6 deliverable.  Scans ``outputs/four_side_1024_v1_v2_abcd/V{1,2}_{A,B,C,D}``
and builds the complete ``comparison/`` directory:

* ``all_metrics.csv`` / ``all_metrics.json`` -- one row per experiment with the
  full SPEC §5 metric set (values are taken from each run's ``statistics.json``;
  if a run has no statistics yet, they are recomputed with ``abcd/metrics.py``);
* ``strict_audit_summary.json`` -- authoritative ``audit_strict.json`` verdict
  per experiment (falls back to ``independent_audit.json`` for the historical
  fixture, explicitly labelled);
* ``abcd_layout_compare.png`` / ``abcd_layout_compare_v2.png`` -- the four
  algorithms A/B/C/D of one topology side by side, identical axes limits,
  figure size, line width and side-pair palette; every panel title carries the
  actual routed count of that run;
* ``v1_v2_same_algo_compare.png`` -- 4 rows (algorithm) x 2 columns (V1/V2) so
  the same-algorithm topology effect is directly visible;
* ``metric_bars_*.png`` -- routed count, opposite-vs-adjacent rate, length,
  crossings, runtime, strict violations, regularity and symmetry bars;
* renderers for the Lead-authored ``c_sweep.csv`` / ``c_sweep.json`` and
  ``d_budget_compare.json`` files (tables / bars) whenever they appear;
* a ``rendered`` / ``skipped`` manifest inside ``all_metrics.json`` so missing
  inputs are reported instead of guessed.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.abcd.compare \\
        --root outputs/four_side_1024_v1_v2_abcd
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path

import numpy as np

from ..d56.plots_d56 import (BOARD_MM, DPI, PAIR_ORDER, _board_frame,
                             draw_connectors, pyplot)
from ..outputs import COLORS
from .metrics import (_json_safe, _load_json, _pair_of, _split_records, _status,
                      _derived_config, build_statistics, load_audit)
from .plots import DISPLAY_SAGITTA_MM, load_display_data

SCHEMA = "four_side_1024_abcd_comparison_v1"
TOOL = "four_side_1024.abcd.compare"
EXPERIMENT_ORDER = ("V1_A", "V1_B", "V1_C", "V1_D",
                    "V2_A", "V2_B", "V2_C", "V2_D")
TOPOLOGIES = ("V1", "V2")
ALGORITHMS = ("A", "B", "C", "D")
TOPOLOGY_COLORS = {"V1": "#3366bb", "V2": "#b84040"}
ALGORITHM_COLORS = {"A": "#3366bb", "B": "#e3a323", "C": "#00a0a0",
                    "D": "#a545b0"}
MISSING_COLOR = "#bbbbbb"
RELATION_COLORS = {"opposite": "#b84040", "adjacent": "#00a0a0"}
TOTAL_CONNECTIONS = 1024
LAYOUT_LINEWIDTH = 0.32
LAYOUT_ALPHA = 0.8
LAYOUT_FIGSIZE_ABCD = (16.0, 15.4)
LAYOUT_FIGSIZE_V1V2 = (13.6, 24.0)

#: columns of ``all_metrics.csv`` (flat, fixed order, one row per experiment)
CSV_COLUMNS = (
    "experiment", "topology", "algorithm", "statistics_present",
    "audit_strict_present", "audit_policy", "audit_passed",
    "routed", "unrouted", "routing_rate",
    "opposite_routing_rate", "adjacent_routing_rate",
    "pair_NS_routed", "pair_EW_routed", "pair_EN_routed", "pair_ES_routed",
    "pair_SW_routed", "pair_NW_routed",
    "pair_NS_rate", "pair_EW_rate", "pair_EN_rate", "pair_ES_rate",
    "pair_SW_rate", "pair_NW_rate",
    "mean_length_mm", "max_length_mm", "total_length_mm",
    "mean_bend_count", "total_bends", "mean_turns", "mean_straight_fraction",
    "crossing_count", "crossing_count_recomputed",
    "crossing_count_density_per_mm2", "small_angle_crossing_count",
    "small_angle_5deg_crossing_count", "crossing_grid_peak",
    "spacing_violation_pairs", "overlap_pairs", "touch_pairs",
    "crossing_window_overlap_pairs", "self_intersections", "self_overlaps",
    "radius_violations", "boundary_violations", "diagonal_line_violations",
    "free_arc_violations", "total_violation_count",
    "candidate_evaluations", "candidate_evaluations_source", "pair_checks",
    "runtime_seconds", "runtime_seconds_source", "evals_per_second",
    "peak_memory_mb", "eval_budget", "time_budget_seconds", "budget_exhausted",
    "mean_min_gap_mm", "median_min_gap_mm", "max_min_gap_mm",
    "track_band_score", "track_band_eligible_pairs", "track_band_aligned_pairs",
    "symmetry_rot90_routed_pair_fraction", "symmetry_rot90_shape_match_fraction",
    "symmetry_rot180_routed_pair_fraction", "symmetry_rot180_shape_match_fraction",
    "symmetry_mirror_x_routed_pair_fraction", "symmetry_mirror_x_shape_match_fraction",
    "symmetry_mirror_y_routed_pair_fraction", "symmetry_mirror_y_shape_match_fraction",
    "symmetry_diag_routed_pair_fraction", "symmetry_diag_shape_match_fraction",
    "pareto_routed", "pareto_total_length_mm", "pareto_crossing_count",
    "sensitivity_exact_passed", "sensitivity_exact_crossing_count",
    "sensitivity_exact_spacing_violation_pairs",
    "sensitivity_legacy_passed", "sensitivity_legacy_crossing_count",
    "sensitivity_legacy_spacing_violation_pairs",
    "sensitivity_legacy_violation_pair_count",
    "notes",
)


def _sensitivity_value(statistics, arm, field):
    sensitivity = (statistics or {}).get("sensitivity_audits") or {}
    report = sensitivity.get(arm) or {}
    if field == "passed":
        return report.get("passed")
    return (report.get("values") or {}).get(field)


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def _run_dir(root, experiment):
    return Path(root) / experiment


def _statistics_from_run(run_dir, experiment, recompute_missing=True):
    """Return ``(statistics, info)`` for one run directory."""
    routes_path = run_dir / "routes.json"
    info = {"experiment": experiment, "run_dir": str(run_dir),
            "statistics_present": False, "recomputed": False,
            "routes_present": routes_path.exists()}
    if not routes_path.exists():
        info["error"] = "routes.json missing"
        return None, info
    stats_path = run_dir / "statistics.json"
    if stats_path.exists():
        try:
            statistics = _load_json(stats_path)
            info["statistics_present"] = True
            return statistics, info
        except (OSError, json.JSONDecodeError) as exc:
            info["statistics_error"] = f"{type(exc).__name__}: {exc}"
    if recompute_missing:
        config_path = run_dir / "config.json"
        audit_path = run_dir / "audit_strict.json"
        try:
            statistics = build_statistics(
                routes_path=routes_path,
                config_path=str(config_path) if config_path.exists() else None,
                out_path=stats_path, run_dir=run_dir,
                audit_path=str(audit_path) if audit_path.exists() else None,
                experiment=experiment, quiet=True)
            info["recomputed"] = True
            return statistics, info
        except Exception as exc:  # noqa: BLE001 - report, never fabricate
            info["recompute_error"] = f"{type(exc).__name__}: {exc}"
    return None, info


def _metric_value(statistics, key, default=None):
    if not isinstance(statistics, dict):
        return default
    value = statistics.get(key)
    return default if value is None else value


def _pair_value(statistics, pair, field):
    by_pair = (statistics or {}).get("by_pair") or {}
    entry = by_pair.get(pair) or {}
    return entry.get(field)


def _symmetry_value(statistics, transform, field):
    symmetry = (statistics or {}).get("symmetry") or {}
    entry = symmetry.get(transform) or {}
    return entry.get(field)


def _audit_summary(run_dir):
    """Load the authoritative strict audit (fallback: historical audit)."""
    for name, label in (("audit_strict.json", "audit_strict"),
                        ("independent_audit.json", "independent_audit")):
        path = Path(run_dir) / name
        if not path.exists():
            continue
        try:
            report = load_audit(path, label)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return {"file": str(path), "label": label,
                    "error": f"{type(exc).__name__}: {exc}"}
        values = report.get("values") or {}
        return {
            "file": str(path),
            "label": label,
            "policy": report.get("policy"),
            "passed": report.get("passed"),
            "error_count": report.get("errors"),
            "violation_count": report.get("violations"),
            "routed_count": report.get("routed_count"),
            "candidate_pair_count": report.get("candidate_pair_count"),
            "runtime_seconds": report.get("runtime_seconds"),
            "sha256": report.get("sha256"),
            "crossing_count": values.get("crossing_count"),
            "crossing_pair_count": report.get("crossing_pair_count"),
            "spacing_violation_pairs": values.get("spacing_violation_pairs"),
            "overlap_pairs": values.get("overlap_pairs"),
            "touch_pairs": values.get("touch_pairs"),
            "crossing_window_overlap_pairs": values.get(
                "crossing_window_overlap_pairs"),
            "violation_pair_count": values.get("violation_pair_count"),
            "small_angle_crossing_count": values.get("small_angle_crossing_count"),
            "self_intersections": values.get("self_intersections"),
            "radius_violations": values.get("radius_violations"),
            "boundary_violations": values.get("boundary_violations"),
            "diagonal_line_violations": values.get("diagonal_line_violations"),
            "free_arc_violations": values.get("free_arc_violations"),
        }
    return None


def _experiment_row(experiment, statistics, run_info):
    topology = experiment.split("_")[0]
    algorithm = experiment.split("_")[1] if "_" in experiment else "?"
    row = {
        "experiment": experiment,
        "topology": topology,
        "algorithm": algorithm,
        "statistics_present": bool(run_info.get("statistics_present")),
        "audit_strict_present": bool(run_info.get("audit_strict_present")),
        "audit_policy": _metric_value(statistics, "audit_policy"),
        "audit_passed": _metric_value(statistics, "audit_passed"),
        "routed": _metric_value(statistics, "routed"),
        "unrouted": _metric_value(statistics, "unrouted"),
        "routing_rate": _metric_value(statistics, "routing_rate"),
        "opposite_routing_rate": _metric_value(statistics,
                                               "opposite_routing_rate"),
        "adjacent_routing_rate": _metric_value(statistics,
                                               "adjacent_routing_rate"),
        "mean_length_mm": _metric_value(statistics, "mean_length_mm"),
        "max_length_mm": _metric_value(statistics, "max_length_mm"),
        "total_length_mm": _metric_value(statistics, "total_length_mm"),
        "mean_bend_count": _metric_value(statistics, "mean_bend_count"),
        "total_bends": _metric_value(statistics, "total_bends"),
        "mean_turns": _metric_value(statistics, "mean_turns"),
        "mean_straight_fraction": _metric_value(statistics,
                                                "mean_straight_fraction"),
        "crossing_count": _metric_value(statistics, "crossing_count"),
        "crossing_count_recomputed": _metric_value(statistics,
                                                   "crossing_count_recomputed"),
        "crossing_count_density_per_mm2": _metric_value(
            statistics, "crossing_count_density_per_mm2"),
        "small_angle_crossing_count": _metric_value(
            statistics, "small_angle_crossing_count"),
        "small_angle_5deg_crossing_count": _metric_value(
            statistics, "small_angle_5deg_crossing_count"),
        "crossing_grid_peak": _metric_value(statistics, "crossing_grid_peak"),
        "spacing_violation_pairs": _metric_value(statistics,
                                                 "spacing_violation_pairs"),
        "overlap_pairs": _metric_value(statistics, "overlap_pairs"),
        "touch_pairs": _metric_value(statistics, "touch_pairs"),
        "crossing_window_overlap_pairs": _metric_value(
            statistics, "crossing_window_overlap_pairs"),
        "self_intersections": _metric_value(statistics, "self_intersections"),
        "self_overlaps": _metric_value(statistics, "self_overlaps"),
        "radius_violations": _metric_value(statistics, "radius_violations"),
        "boundary_violations": _metric_value(statistics, "boundary_violations"),
        "diagonal_line_violations": _metric_value(statistics,
                                                  "diagonal_line_violations"),
        "free_arc_violations": _metric_value(statistics, "free_arc_violations"),
        "total_violation_count": _metric_value(statistics,
                                               "total_violation_count"),
        "candidate_evaluations": _metric_value(statistics,
                                               "candidate_evaluations"),
        "candidate_evaluations_source": _metric_value(
            statistics, "candidate_evaluations_source"),
        "pair_checks": _metric_value(statistics, "pair_checks"),
        "runtime_seconds": _metric_value(statistics, "runtime_seconds"),
        "runtime_seconds_source": _metric_value(statistics,
                                                "runtime_seconds_source"),
        "evals_per_second": _metric_value(statistics, "evals_per_second"),
        "peak_memory_mb": _metric_value(statistics, "peak_memory_mb"),
        "eval_budget": _metric_value(statistics, "eval_budget"),
        "time_budget_seconds": _metric_value(statistics,
                                             "time_budget_seconds"),
        "budget_exhausted": _metric_value(statistics, "budget_exhausted"),
        "mean_min_gap_mm": _metric_value(statistics, "mean_min_gap_mm"),
        "median_min_gap_mm": _metric_value(statistics, "median_min_gap_mm"),
        "max_min_gap_mm": _metric_value(statistics, "max_min_gap_mm"),
        "track_band_score": _metric_value(statistics, "track_band_score"),
        "track_band_eligible_pairs": _metric_value(statistics,
                                                   "track_band_eligible_pairs"),
        "track_band_aligned_pairs": _metric_value(statistics,
                                                  "track_band_aligned_pairs"),
        "notes": run_info.get("error") or run_info.get("recompute_error") or "",
    }
    for pair in PAIR_ORDER:
        row[f"pair_{pair}_routed"] = _pair_value(statistics, pair, "success")
        row[f"pair_{pair}_rate"] = _pair_value(statistics, pair, "routing_rate")
    for transform in ("rot90", "rot180", "mirror_x", "mirror_y", "diag"):
        row[f"symmetry_{transform}_routed_pair_fraction"] = _symmetry_value(
            statistics, transform, "routed_pair_fraction")
        row[f"symmetry_{transform}_shape_match_fraction"] = _symmetry_value(
            statistics, transform, "shape_match_fraction")
    row["sensitivity_exact_passed"] = _sensitivity_value(
        statistics, "exact", "passed")
    row["sensitivity_exact_crossing_count"] = _sensitivity_value(
        statistics, "exact", "crossing_count")
    row["sensitivity_exact_spacing_violation_pairs"] = _sensitivity_value(
        statistics, "exact", "spacing_violation_pairs")
    row["sensitivity_legacy_passed"] = _sensitivity_value(
        statistics, "legacy", "passed")
    row["sensitivity_legacy_crossing_count"] = _sensitivity_value(
        statistics, "legacy", "crossing_count")
    row["sensitivity_legacy_spacing_violation_pairs"] = _sensitivity_value(
        statistics, "legacy", "spacing_violation_pairs")
    row["sensitivity_legacy_violation_pair_count"] = _sensitivity_value(
        statistics, "legacy", "violation_pair_count")
    pareto = (statistics or {}).get("pareto") or {}
    row["pareto_routed"] = pareto.get("routed")
    row["pareto_total_length_mm"] = pareto.get("total_length_mm")
    row["pareto_crossing_count"] = pareto.get("crossing_count")
    return row


# ---------------------------------------------------------------------------
# layout panels
# ---------------------------------------------------------------------------
def _pair_legend_handles():
    from matplotlib.lines import Line2D
    return [Line2D([0], [0], color=COLORS[pair], linewidth=2.0, label=pair)
            for pair in PAIR_ORDER]


def _draw_routes_panel(ax, data, title_lines, linewidth=LAYOUT_LINEWIDTH,
                       alpha=LAYOUT_ALPHA, connector_labels=True):
    from matplotlib.collections import LineCollection
    curves = data["curves"]
    meta = data["meta"]
    route_ids = [route_id for route_id in curves if len(curves[route_id]) >= 2]
    segments = [curves[route_id] for route_id in route_ids]
    colours = [COLORS[meta[route_id]["pair"]] for route_id in route_ids]
    if segments:
        ax.add_collection(LineCollection(segments, colors=colours,
                                         linewidths=linewidth, alpha=alpha,
                                         zorder=3))
    _board_frame(ax)
    draw_connectors(ax, data.get("connectors") or [], depth_mm=3.0,
                    label_fontsize=3.6 if connector_labels else 0.0)
    ax.set_title("\n".join(title_lines), fontsize=9.0)
    ax.tick_params(labelsize=6.0)
    return len(route_ids)


def _layout_figure(path, root, experiments, title, figsize, columns,
                   missing_note="missing run"):
    plt = pyplot()
    rows = int(math.ceil(len(experiments) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=figsize, squeeze=False)
    rendered = []
    for index, experiment in enumerate(experiments):
        ax = axes[index // columns][index % columns]
        run_dir = _run_dir(root, experiment)
        data = None
        if (run_dir / "routes.json").exists():
            try:
                data = load_display_data(run_dir / "routes.json",
                                         run_dir=run_dir,
                                         sagitta_mm=DISPLAY_SAGITTA_MM)
            except Exception:  # noqa: BLE001 - report a blank panel
                data = None
        if data is None or not data["routed"]:
            ax.axis("off")
            ax.set_title(f"{experiment}\n{missing_note}", fontsize=9.0,
                         color="#888888")
            continue
        statistics = None
        stats_path = run_dir / "statistics.json"
        if stats_path.exists():
            try:
                statistics = _load_json(stats_path)
            except (OSError, json.JSONDecodeError):
                statistics = None
        routed_count = len(data["routed"])
        crossing_count = _metric_value(statistics, "crossing_count")
        mean_length = _metric_value(statistics, "mean_length_mm")
        lines = [f"{experiment} | {routed_count}/{TOTAL_CONNECTIONS} routed",
                 f"rate {routed_count / TOTAL_CONNECTIONS:.2%}"]
        if crossing_count is not None:
            lines.append(f"crossings {int(crossing_count)}")
        if mean_length is not None:
            lines.append(f"mean len {float(mean_length):.2f} mm")
        _draw_routes_panel(ax, data, lines)
        rendered.append(experiment)
    for index in range(len(experiments), rows * columns):
        axes[index // columns][index % columns].axis("off")
    handles = _pair_legend_handles()
    if handles:
        fig.legend(handles=handles, loc="lower center", ncol=len(handles),
                   fontsize=8.0, framealpha=0.9)
    fig.suptitle(title, fontsize=12.0)
    fig.tight_layout(rect=(0.0, 0.035, 1.0, 0.965))
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "panels": len(experiments),
            "rendered": rendered}


# ---------------------------------------------------------------------------
# bar charts
# ---------------------------------------------------------------------------
def _style_axes(ax, title, ylabel, rotation=0, grid_axis="y"):
    ax.set_title(title, fontsize=10.0)
    ax.set_ylabel(ylabel, fontsize=8.5)
    ax.tick_params(labelsize=7.5)
    ax.grid(True, axis=grid_axis, alpha=0.28, linewidth=0.5)
    for label in ax.get_xticklabels():
        label.set_rotation(rotation)
        label.set_ha("right" if rotation else "center")


def _bar_values(path, rows, key, title, ylabel, value_format="{:.0f}",
                reference=None, reference_label=None, log_scale=False):
    plt = pyplot()
    fig, ax = plt.subplots(figsize=(11.0, 4.8))
    labels = [row["experiment"] for row in rows]
    values = [row.get(key) for row in rows]
    positions = np.arange(len(labels))
    colours = [TOPOLOGY_COLORS.get(row.get("topology"), MISSING_COLOR)
               for row in rows]
    heights = [0.0 if value is None else float(value) for value in values]
    bars = ax.bar(positions, heights, color=colours, width=0.62,
                  edgecolor="#222222", linewidth=0.4)
    for position, bar, value in zip(positions, bars, values):
        if value is None:
            ax.text(position, 0.0, "n/a", ha="center", va="bottom",
                    fontsize=7.5, color="#555555")
        else:
            ax.text(position, bar.get_height(),
                    value_format.format(value), ha="center", va="bottom",
                    fontsize=7.0, rotation=90 if len(labels) > 4 else 0)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=0 if len(labels) <= 6 else 30,
                       ha="center" if len(labels) <= 6 else "right")
    if log_scale and any(value and value > 0 for value in
                         (heights or [])):
        ax.set_yscale("log")
    if reference is not None:
        ax.axhline(reference, color="#333333", linewidth=0.8, linestyle="--",
                   label=reference_label or str(reference))
        ax.legend(fontsize=8.0, loc="best")
    _style_axes(ax, title, ylabel)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "key": key,
            "experiments_with_values": sum(1 for value in values
                                           if value is not None)}


def _grouped_rate_bars(path, rows, title):
    plt = pyplot()
    fig, ax = plt.subplots(figsize=(11.0, 4.8))
    labels = [row["experiment"] for row in rows]
    positions = np.arange(len(labels))
    width = 0.38
    for offset, relation in ((-width / 2.0, "opposite"),
                             (width / 2.0, "adjacent")):
        values = [100.0 * (row.get(f"{relation}_routing_rate") or 0.0)
                  for row in rows]
        ax.bar(positions + offset, values, width=width,
               color=RELATION_COLORS[relation], edgecolor="#222222",
               linewidth=0.4, label=f"{relation} routes (%)")
        for position, value in zip(positions + offset, values):
            ax.text(position, value, f"{value:.1f}", ha="center", va="bottom",
                    fontsize=6.5, rotation=90)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=0 if len(labels) <= 6 else 30,
                       ha="center" if len(labels) <= 6 else "right")
    ax.set_ylim(0.0, 105.0)
    ax.legend(fontsize=8.0, loc="upper right")
    _style_axes(ax, title, "routing rate per relation (%)")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "key": "opposite/adjacent_routing_rate"}


def _regularity_bars(path, rows):
    plt = pyplot()
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 8.4))
    labels = [row["experiment"] for row in rows]
    positions = np.arange(len(labels))
    specs = (
        ("mean_straight_fraction", "mean straight fraction", "{:.3f}"),
        ("track_band_score", "track band score", "{:.3f}"),
        ("mean_min_gap_mm", "mean nearest gap (mm)", "{:.4f}"),
        ("crossing_grid_peak", "5 mm grid peak crossings", "{:.0f}"),
    )
    for ax, (key, label, value_format) in zip(axes.ravel(), specs):
        values = [row.get(key) for row in rows]
        heights = [0.0 if value is None else float(value) for value in values]
        colours = [TOPOLOGY_COLORS.get(row.get("topology"), MISSING_COLOR)
                   for row in rows]
        ax.bar(positions, heights, color=colours, width=0.62,
               edgecolor="#222222", linewidth=0.4)
        for position, value, height in zip(positions, values, heights):
            if value is None:
                ax.text(position, 0.0, "n/a", ha="center", va="bottom",
                        fontsize=6.0, color="#555555")
            else:
                ax.text(position, height, value_format.format(value),
                        ha="center", va="bottom", fontsize=6.0, rotation=90)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=6.5)
        ax.set_title(label, fontsize=9.0)
        ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
        ax.tick_params(labelsize=7.0)
    fig.suptitle("Regularity metrics per experiment", fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "keys": [spec[0] for spec in specs]}


def _symmetry_bars(path, rows):
    plt = pyplot()
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 4.8))
    labels = [row["experiment"] for row in rows]
    positions = np.arange(len(labels))
    specs = (
        ("routed_pair_fraction", "topology-counterpart pairs both routed (%)"),
        ("shape_match_fraction", "both-routed pairs with shape match <= 0.05 mm (%)"),
    )
    for ax, (field, label) in zip(axes, specs):
        values = []
        for row in rows:
            value = row.get(f"symmetry_diag_{field}")
            values.append(None if value is None else 100.0 * value)
        heights = [0.0 if value is None else float(value) for value in values]
        colours = [TOPOLOGY_COLORS.get(row.get("topology"), MISSING_COLOR)
                   for row in rows]
        ax.bar(positions, heights, color=colours, width=0.62,
               edgecolor="#222222", linewidth=0.4)
        for position, value, height in zip(positions, values, heights):
            ax.text(position, height,
                    "n/a" if value is None else f"{value:.1f}",
                    ha="center", va="bottom", fontsize=6.5, rotation=90)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7.0)
        ax.set_title(f"diag symmetry: {label}", fontsize=9.0)
        ax.set_ylim(0.0, 110.0)
        ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    fig.suptitle("Symmetry metrics per experiment (SPEC §5, diag transform)",
                 fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "keys": ["symmetry_diag_routed_pair_fraction",
                                        "symmetry_diag_shape_match_fraction"]}


# ---------------------------------------------------------------------------
# Lead-authored sweep renderers
# ---------------------------------------------------------------------------
def _rows_from_payload(payload):
    """Best-effort extraction of a list of homogeneous dict rows."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    preferred = ("rows", "records", "results", "experiments", "data",
                 "variants", "sweep", "items", "designs", "entries",
                 "comparison", "table")
    for key in preferred:
        value = payload.get(key)
        if isinstance(value, list) and any(isinstance(item, dict) for item in value):
            return [item for item in value if isinstance(item, dict)]
    # dict-of-dicts: {'V1': {...}, 'V2': {...}} or {'design': {...}}
    for key in preferred:
        value = payload.get(key)
        if isinstance(value, dict):
            candidate = []
            for name, item in value.items():
                if isinstance(item, dict):
                    row = dict(item)
                    row.setdefault("name", name)
                    candidate.append(row)
            if candidate:
                return candidate
    scalar = {key: value for key, value in payload.items()
              if not isinstance(value, (dict, list))}
    return [scalar] if scalar else []


def _d_budget_rows(payload):
    """Flatten ``d_budget_compare.json`` into one row per budgeted run."""
    if not isinstance(payload, dict):
        return _rows_from_payload(payload)
    topologies = payload.get("topologies")
    if not isinstance(topologies, dict) or not topologies:
        return _rows_from_payload(payload)
    rows = []
    for topology, block in topologies.items():
        if not isinstance(block, dict):
            continue
        sequential = block.get("sequential") or {}
        equal = sequential.get("equal_budget_evaluations")
        for algorithm, run in (sequential.get("runs") or {}).items():
            if not isinstance(run, dict):
                continue
            rows.append({
                "topology": topology,
                "variant": f"{algorithm} (sequential)",
                "eval_budget": None,
                "evaluations": run.get("evaluations"),
                "routed": run.get("routed"),
                "opposite": run.get("opposite"),
                "adjacent": run.get("adjacent"),
                "runtime_seconds": run.get("runtime_seconds"),
                "note": "equal-budget reference" if run.get("evaluations") == equal
                        else "",
            })
        for key, label in (("d_primary", "D primary (equal/eval-budget)"),
                           ("d_extended", "D extended budget")):
            run = block.get(key)
            if not isinstance(run, dict):
                continue
            rows.append({
                "topology": topology,
                "variant": label,
                "eval_budget": run.get("eval_budget"),
                "evaluations": run.get("evaluations"),
                "routed": run.get("routed"),
                "opposite": run.get("opposite"),
                "adjacent": run.get("adjacent"),
                "runtime_seconds": run.get("runtime_seconds"),
                "note": f"sequential equal-budget = {equal} evaluations",
            })
    return rows


def _table_figure(path, rows, title, max_rows=18, max_cols=10):
    plt = pyplot()
    if not rows:
        fig, ax = plt.subplots(figsize=(10.0, 2.0))
        ax.axis("off")
        ax.text(0.5, 0.5, "no tabular data available yet", ha="center",
                va="center", fontsize=11.0, color="#777777")
        ax.set_title(title, fontsize=11.0)
        fig.savefig(path, dpi=DPI)
        plt.close(fig)
        return {"file": str(path), "rows": 0, "empty": True}
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    columns = columns[:max_cols]
    rows = rows[:max_rows]

    def _format(value):
        if isinstance(value, float):
            if abs(value) >= 1000:
                return f"{value:.1f}"
            if abs(value) < 1e-4 and value != 0:
                return f"{value:.2e}"
            return f"{value:.4g}"
        text = str(value)
        return text if len(text) <= 40 else text[:37] + "..."

    cell_rows = [[_format(row.get(column)) for column in columns]
                 for row in rows]
    fig_height = max(2.2, 0.42 * (len(cell_rows) + 2) + 1.2)
    fig, ax = plt.subplots(figsize=(min(18.0, 1.6 * len(columns) + 3.0),
                                    fig_height))
    ax.axis("off")
    table = ax.table(cellText=cell_rows, colLabels=columns, loc="center",
                     cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(7.5)
    table.scale(1.0, 1.32)
    for (row_index, column_index), cell in table.get_celld().items():
        if row_index == 0:
            cell.set_text_props(fontweight="bold")
            cell.set_facecolor("#d9e2f3")
        elif row_index % 2 == 0:
            cell.set_facecolor("#f3f5f8")
    ax.set_title(title, fontsize=11.0)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return {"file": str(path), "rows": len(cell_rows),
            "columns": columns}


def _find_comparison_input(comparison_dir, root, names):
    """Locate a Lead-authored input file in the usual hand-off locations."""
    candidates = [comparison_dir]
    if root is not None:
        candidates.extend([Path(root), Path(root) / "sweeps",
                           Path(root) / "comparison"])
    for name in names:
        for directory in candidates:
            path = directory / name
            if path.exists():
                return path
    return None


def _render_c_sweep(comparison_dir, rendered, skipped, root=None):
    json_path = _find_comparison_input(comparison_dir, root, ("c_sweep.json",))
    csv_path = _find_comparison_input(comparison_dir, root, ("c_sweep.csv",))
    payload = None
    source = None
    if json_path is not None:
        try:
            payload = _load_json(json_path)
            source = str(json_path)
        except (OSError, json.JSONDecodeError) as exc:
            skipped.append(f"c_sweep.json unreadable: {exc}")
    if payload is None and csv_path is not None:
        try:
            with open(csv_path, newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                payload = [dict(row) for row in reader]
            source = str(csv_path)
        except (OSError, csv.Error) as exc:
            skipped.append(f"c_sweep.csv unreadable: {exc}")
    if payload is None:
        skipped.append("c_sweep.json / c_sweep.csv not written yet")
        return
    rows = _rows_from_payload(payload)
    table_info = _table_figure(comparison_dir / "c_sweep_table.png", rows,
                               f"C sweep ablation ({Path(source).name})")
    table_info["source"] = source
    rendered.append(table_info)
    routed_key = None
    for candidate in ("routed", "success_count", "routed_count", "success",
                      "connections_routed"):
        if rows and candidate in rows[0]:
            routed_key = candidate
            break
    if routed_key:
        bar_rows = []
        for index, row in enumerate(rows):
            name = (row.get("name") or row.get("variant") or
                    row.get("experiment") or row.get("design_name") or
                    row.get("design") or f"variant {index}")
            bar_rows.append({"experiment": str(name),
                             "topology": "V1",
                             routed_key: row.get(routed_key)})
        info = _bar_values(comparison_dir / "c_sweep_bars.png", bar_rows,
                           routed_key, "C sweep: routed count",
                           "routed connections")
        info["source"] = source
        rendered.append(info)
    # mirror the Lead-authored table into comparison/ per SPEC §4
    for source_path, target_name in ((json_path, "c_sweep.json"),
                                     (csv_path, "c_sweep.csv")):
        if source_path is not None and Path(source_path).parent != comparison_dir:
            try:
                (comparison_dir / target_name).write_bytes(
                    Path(source_path).read_bytes())
                rendered.append({"file": str(comparison_dir / target_name),
                                 "copied_from": str(source_path)})
            except OSError:
                skipped.append(f"could not mirror {target_name} into comparison/")
    if csv_path is None and isinstance(payload, list) and rows:
        try:
            with open(comparison_dir / "c_sweep.csv", "w", newline="",
                      encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            rendered.append({"file": str(comparison_dir / "c_sweep.csv"),
                             "derived_from": source})
        except (OSError, csv.Error, IndexError):
            skipped.append("could not derive c_sweep.csv from c_sweep.json")


def _render_d_budget(comparison_dir, rendered, skipped, root=None):
    path = _find_comparison_input(comparison_dir, root,
                                  ("d_budget_compare.json",))
    if path is None:
        skipped.append("d_budget_compare.json not written yet")
        return
    try:
        payload = _load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        skipped.append(f"d_budget_compare.json unreadable: {exc}")
        return
    rows = _d_budget_rows(payload)
    info = _table_figure(comparison_dir / "d_budget_compare.png", rows,
                         "D equal-budget vs extended-budget comparison")
    info["source"] = str(path)
    rendered.append(info)
    if Path(path).parent != comparison_dir:
        try:
            (comparison_dir / "d_budget_compare.json").write_bytes(
                Path(path).read_bytes())
            rendered.append({"file": str(comparison_dir / "d_budget_compare.json"),
                             "copied_from": str(path)})
        except OSError:
            skipped.append("could not mirror d_budget_compare.json into comparison/")
    if rows and any(row.get("routed") is not None for row in rows):
        plt = pyplot()
        fig, axes = plt.subplots(1, 2, figsize=(14.0, 5.0))
        topologies = sorted({str(row.get("topology") or "?") for row in rows})
        for ax, topology in zip(axes, topologies):
            subset = [row for row in rows
                      if str(row.get("topology") or "?") == topology
                      and row.get("routed") is not None]
            labels = [str(row.get("variant") or f"run {index}")
                      for index, row in enumerate(subset)]
            values = [float(row["routed"]) for row in subset]
            positions = np.arange(len(labels))
            colours = [ALGORITHM_COLORS.get(str(row.get("variant") or "")[:1],
                                            "#555555") for row in subset]
            ax.bar(positions, values, color=colours, width=0.62,
                   edgecolor="#222222", linewidth=0.4)
            for position, value in zip(positions, values):
                ax.text(position, value, f"{value:.0f}", ha="center",
                        va="bottom", fontsize=7.0, rotation=90)
            ax.set_xticks(positions)
            ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=7.0)
            ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
            ax.set_title(f"topology {topology}", fontsize=9.5)
            ax.set_ylabel("routed connections", fontsize=8.0)
        fig.suptitle("D budget comparison: routed count per budgeted run "
                     "(same geometry/policy; honest scale)", fontsize=11.0)
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
        bar_path = comparison_dir / "d_budget_compare_bars.png"
        fig.savefig(bar_path, dpi=DPI)
        plt.close(fig)
        rendered.append({"file": str(bar_path),
                         "source": str(path), "topologies": topologies})


def _historical_strict_reference(comparison_dir, root):
    """Optional validator crosscheck of the historical 467 (informational)."""
    path = _find_comparison_input(comparison_dir, root,
                                  ("crosscheck_strict_467.json",))
    if path is None:
        return None
    try:
        payload = _load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    keys = ("schema", "routes_file", "routed_route_count", "compared_pair_count",
            "mismatch_count", "strict_invalid_pairs", "strict_failed_route_count",
            "strict_failed_route_ids", "window_consistency", "runtime_seconds",
            "passed")
    return {"file": str(path),
            **{key: payload.get(key) for key in keys if key in payload}}


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def build_comparison(root, comparison_dir=None, recompute_missing=True,
                     quiet=False):
    root = Path(root)
    comparison_dir = Path(comparison_dir) if comparison_dir else root / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    rows = []
    run_info = {}
    strict_summary = {"schema": SCHEMA, "tool": TOOL,
                      "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                      "root": str(root),
                      "policy_source_order": ["audit_strict.json",
                                              "independent_audit.json"],
                      "experiments": {}, "missing": [], "rendered": [],
                      "skipped": []}
    for experiment in EXPERIMENT_ORDER:
        directory = _run_dir(root, experiment)
        if not (directory / "routes.json").exists():
            strict_summary["missing"].append(experiment)
            run_info[experiment] = {"experiment": experiment,
                                    "run_dir": str(directory),
                                    "routes_present": False,
                                    "error": "routes.json missing"}
            rows.append(_experiment_row(experiment, None, run_info[experiment]))
            continue
        statistics, info = _statistics_from_run(directory, experiment,
                                                recompute_missing)
        audit = _audit_summary(directory)
        info["audit_strict_present"] = bool(
            (directory / "audit_strict.json").exists())
        info["audit_loaded"] = audit is not None
        info["audit_label"] = (audit or {}).get("label")
        run_info[experiment] = info
        strict_summary["experiments"][experiment] = audit
        row = _experiment_row(experiment, statistics, info)
        if info.get("recomputed"):
            row["statistics_present"] = True
        rows.append(row)
        if not quiet:
            print(f"[compare] {experiment}: routed={row.get('routed')} "
                  f"crossings={row.get('crossing_count')} "
                  f"audit={info.get('audit_label')}")

    # ---- all_metrics.csv / .json ------------------------------------------
    csv_path = comparison_dir / "all_metrics.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS),
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key))
                             for key in CSV_COLUMNS})
    json_path = comparison_dir / "all_metrics.json"
    metrics_payload = {
        "schema": SCHEMA,
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "experiment_order": list(EXPERIMENT_ORDER),
        "columns": list(CSV_COLUMNS),
        "experiments": rows,
        "run_info": run_info,
        "notes": [
            "every value comes from the run's statistics.json, which is "
            "recomputed from primitives by abcd/metrics.py; when statistics.json "
            "was missing it has been recomputed here",
            "missing runs are reported in run_info/strict_audit_summary.missing, "
            "never filled with estimated values",
        ],
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(_json_safe(metrics_payload), handle, ensure_ascii=False,
                  indent=1)
        handle.write("\n")

    # ---- strict audit summary --------------------------------------------
    audit_values = [entry for entry in strict_summary["experiments"].values()
                    if isinstance(entry, dict) and entry.get("passed") is not None]
    strict_summary["all_available_passed"] = (
        bool(audit_values) and all(entry.get("passed") for entry in audit_values))
    strict_summary["experiments_with_audit"] = len(audit_values)
    strict_summary["expected_experiments"] = len(EXPERIMENT_ORDER)
    strict_summary["historical_reference"] = _historical_strict_reference(
        comparison_dir, root)
    audit_path = comparison_dir / "strict_audit_summary.json"
    with open(audit_path, "w", encoding="utf-8") as handle:
        json.dump(_json_safe(strict_summary), handle, ensure_ascii=False,
                  indent=1)
        handle.write("\n")

    # ---- layout comparison figures ---------------------------------------
    rendered = []
    skipped = []
    v1 = [f"V1_{algorithm}" for algorithm in ALGORITHMS]
    v2 = [f"V2_{algorithm}" for algorithm in ALGORITHMS]
    if any((_run_dir(root, experiment) / "routes.json").exists()
           for experiment in v1):
        info = _layout_figure(
            comparison_dir / "abcd_layout_compare.png", root, v1,
            "ABCD algorithm comparison on topology V1 (identical axes, "
            "linewidth and side-pair palette)", LAYOUT_FIGSIZE_ABCD, 2)
        rendered.append(info)
    else:
        skipped.append("abcd_layout_compare.png: no V1 run")
    if any((_run_dir(root, experiment) / "routes.json").exists()
           for experiment in v2):
        info = _layout_figure(
            comparison_dir / "abcd_layout_compare_v2.png", root, v2,
            "ABCD algorithm comparison on topology V2 (identical axes, "
            "linewidth and side-pair palette)", LAYOUT_FIGSIZE_ABCD, 2)
        rendered.append(info)
    else:
        skipped.append("abcd_layout_compare_v2.png: no V2 run")
    v1v2_order = [f"{topology}_{algorithm}"
                  for algorithm in ALGORITHMS for topology in TOPOLOGIES]
    if any((_run_dir(root, experiment) / "routes.json").exists()
           for experiment in v1v2_order):
        info = _layout_figure(
            comparison_dir / "v1_v2_same_algo_compare.png", root, v1v2_order,
            "Same algorithm on V1 vs V2 topologies (rows: A/B/C/D, "
            "columns: V1/V2; identical axes, linewidth and palette)",
            LAYOUT_FIGSIZE_V1V2, 2)
        rendered.append(info)
    else:
        skipped.append("v1_v2_same_algo_compare.png: no runs")

    # ---- metric bars ------------------------------------------------------
    if rows:
        rendered.append(_bar_values(
            comparison_dir / "metric_bars_routed.png", rows, "routed",
            "Routed connections per experiment", "routed connections / 1024",
            value_format="{:.0f}", reference=TOTAL_CONNECTIONS,
            reference_label="1024 connections"))
        rendered.append(_grouped_rate_bars(
            comparison_dir / "metric_bars_relation_rate.png", rows,
            "Opposite vs adjacent routing rate per experiment"))
        rendered.append(_bar_values(
            comparison_dir / "metric_bars_length.png", rows, "mean_length_mm",
            "Mean routed length per experiment", "mean length (mm)",
            value_format="{:.2f}"))
        rendered.append(_bar_values(
            comparison_dir / "metric_bars_crossings.png", rows,
            "crossing_count", "Exact 2D crossings per experiment",
            "crossings (count)", value_format="{:.0f}"))
        rendered.append(_bar_values(
            comparison_dir / "metric_bars_runtime.png", rows, "runtime_seconds",
            "Recorded run time per experiment", "runtime (s)",
            value_format="{:.1f}"))
        rendered.append(_bar_values(
            comparison_dir / "metric_bars_strict_violations.png", rows,
            "total_violation_count",
            "Strict-audit violation counters per experiment",
            "violation count", value_format="{:.0f}"))
        rendered.append(_regularity_bars(
            comparison_dir / "metric_bars_regularity.png", rows))
        rendered.append(_symmetry_bars(
            comparison_dir / "metric_bars_symmetry.png", rows))

    # ---- Lead-authored sweep / budget files ------------------------------
    _render_c_sweep(comparison_dir, rendered, skipped, root)
    _render_d_budget(comparison_dir, rendered, skipped, root)

    manifest = {
        "rendered": [entry.get("file") if isinstance(entry, dict) else entry
                     for entry in rendered],
        "skipped": skipped,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    metrics_payload["rendered"] = manifest["rendered"]
    metrics_payload["skipped"] = manifest["skipped"]
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(_json_safe(metrics_payload), handle, ensure_ascii=False,
                  indent=1)
        handle.write("\n")
    strict_summary["rendered"] = manifest["rendered"]
    strict_summary["skipped"] = skipped
    with open(audit_path, "w", encoding="utf-8") as handle:
        json.dump(_json_safe(strict_summary), handle, ensure_ascii=False,
                  indent=1)
        handle.write("\n")
    if not quiet:
        print(f"[compare] wrote {csv_path.name}, {json_path.name}, "
              f"{audit_path.name} and {len(manifest['rendered'])} artefacts in "
              f"{comparison_dir} ({manifest['elapsed_seconds']} s)")
        for item in skipped:
            print(f"[compare] skipped: {item}")
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
        description="Build the ABCD comparison/ directory from the 8 runs.")
    parser.add_argument("--root", default="outputs/four_side_1024_v1_v2_abcd",
                        help="root containing V1_A ... V2_D run directories")
    parser.add_argument("--comparison-out", help="override comparison directory")
    parser.add_argument("--no-recompute", action="store_true",
                        help="do not recompute missing statistics.json files")
    parser.add_argument("--quiet", action="store_true", help="suppress progress")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    result = build_comparison(
        root=args.root, comparison_dir=args.comparison_out,
        recompute_missing=not args.no_recompute, quiet=args.quiet)
    print(json.dumps({
        "comparison_dir": result["comparison_dir"],
        "experiments_with_data": sum(1 for row in result["rows"]
                                     if row.get("routed") is not None),
        "rendered": len(result["rendered"]),
        "skipped": result["skipped"],
        "elapsed_seconds": result["elapsed_seconds"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
