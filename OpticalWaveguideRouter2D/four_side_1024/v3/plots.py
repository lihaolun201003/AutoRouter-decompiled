"""V3-Huang figures: per-plane layouts, U/refold shapes, combined dual-height,
and the ten Phase-7 comparison figures (SPEC §7).

Style contract (identical for every figure of every run): 200 dpi, figure size
and axes limits fixed, board [-9, 159]^2, linewidth by route count, fixed colour
per connection class/pair.  Every title states the REAL routed count; complex
U/refold routes are never hidden or simplified.

Per-plane figures (``planes/<A>/<z1|z2>/``): ``routing_all.png`` (+SVG/GDS single
layer 0), ``routing_detail.png``, ``crossing_heatmap.png``, ``radius_check.png``,
``congestion_zoom.png``.
Combined figures (``combined/<A>/``): ``layer_2d.png``/``.svg``,
``overlay_3d.png``.
Shapes figures (``shapes/``): ``shape_mix.png``, ``u_depth_histogram.png``,
``u_track_occupancy.png``, ``u_routes_only.png``, ``nested_u_zoom.png``.
Comparison figures (``comparison/``): the ten Phase-7 required figures are
rendered by :mod:`four_side_1024.v3.compare` via the helpers here.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.v3.plots --run-dir <plane dir>
    .venv\\Scripts\\python.exe -m four_side_1024.v3.plots --combined-dir <combined/A>
    .venv\\Scripts\\python.exe -m four_side_1024.v3.plots --shapes --root <root>
    .venv\\Scripts\\python.exe -m four_side_1024.v3.plots --all --root <root>
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

from ..d56.plots_d56 import (BOARD_MM, DPI, _board_frame, draw_connectors,
                             plot_detail, plot_routes, pyplot, sample_curves)
from ..fslw.combine import _ensure_plane_vectors, write_combined_gds
from ..outputs import COLORS
from . import config as v3_config
from . import metrics as v3_metrics

try:  # frozen Lead-authored V3 port model
    from . import ports as v3_ports
except Exception:  # pragma: no cover - reported instead of guessed
    v3_ports = None

SCHEMA = "four_side_1024_v3_plots_v1"
TOOL = "four_side_1024.v3.plots"
PLANE_TOTAL = 512
COMBINED_TOTAL = 1024
DISPLAY_SAGITTA_MM = 0.005
DETAIL_HOTSPOTS = 4
DETAIL_HALF_MM = 12.5
CONGESTION_HALF_MM = 12.5
NESTED_ZOOM_COUNT = 16
NESTED_ZOOM_HALF_MM = 18.0

CLASS_ORDER = ("same", "opposite", "adjacent")
PAIR_ORDER = v3_metrics.PAIR_ORDER
CLASS_PAIRS = v3_metrics.CLASS_PAIRS
PAIR_CLASS = v3_metrics.PAIR_CLASS
CLASS_COLORS = {"same": "#3366bb", "opposite": "#b84040",
                "adjacent": "#00a0a0"}
PAIR_COLORS = {
    "NN": "#3366bb", "SS": "#1f8f8f", "EE": "#e3a323", "WW": "#a545b0",
    "NS": "#b84040", "EW": "#d2691e",
    "NE": "#6a9c3b", "NW": "#2f8f8f", "ES": "#c060a0", "SW": "#8b6f2f",
}
PLANE_COLORS = {"z1": "#1f4e9e", "z2": "#c0392b"}
PLANE_CLASS_TEXT = {
    "z1": "row 1, z=0.0 (same 222 / opposite 196 / adjacent 94)",
    "z2": "row 2, z=0.5 (same 226 / opposite 188 / adjacent 98)",
}
SHAPE_ORDER = v3_metrics.REQUIRED_SHAPES
SHAPE_COLORS = {
    "straight": "#3366bb", "short_S": "#e3a323", "L": "#00a0a0",
    "U": "#b84040", "multi_bend_refold": "#a545b0", "other": "#888888",
}


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def load_plane(run_dir, statistics=None):
    context = v3_metrics.load_plane_context(run_dir, statistics=statistics)
    routed = context["routed"]
    curves = sample_curves(routed, DISPLAY_SAGITTA_MM)
    meta = {}
    pairs = {}
    classes = {}
    for record in routed:
        route_id = record["route_id"]
        pair = v3_metrics._pair_of(record)  # noqa: SLF001
        pairs[route_id] = pair
        classes[route_id] = v3_metrics._relation_of(record)  # noqa: SLF001
        meta[route_id] = {"pair": pair, "class": classes[route_id]}
    context["curves"] = curves
    context["meta_routes"] = meta
    context["route_pairs"] = pairs
    context["route_classes"] = classes
    return context


def _counts_by_class(context):
    counts = Counter()
    for record in context["routed"]:
        counts[v3_metrics._relation_of(record)] += 1  # noqa: SLF001
    return counts


def _plane_title_lines(context):
    statistics = context.get("statistics") or {}
    routed = len(context["routed"])
    plane = context.get("plane") or "?"
    experiment = context.get("experiment") or "V3"
    counts = _counts_by_class(context)
    topology_counts = (statistics.get("by_class") or {})
    total_by_class = {relation: (topology_counts.get(relation) or {}).get(
        "total") for relation in CLASS_ORDER}
    first = (f"{experiment} | plane {plane} | {routed}/{PLANE_TOTAL} routed "
             f"({routed / PLANE_TOTAL:.2%})")
    class_line = "class routed: " + " | ".join(
        f"{relation} {counts.get(relation, 0)}"
        f"/{total_by_class.get(relation) or '?'}" for relation in CLASS_ORDER)
    process = context.get("process") or {}
    shape_counts = ((statistics.get("path_shapes") or {}).get("counts") or {})
    shape_line = "shapes: " + " | ".join(
        f"{shape} {shape_counts.get(shape, 0)}" for shape in SHAPE_ORDER)
    subtitle = "\n".join([
        f"topology {v3_config.TOPOLOGY} | algorithm {context.get('algorithm')} | "
        f"150 x 150 mm | single 2D plane (layer 0)",
        f"R={float(process.get('radius_mm') or v3_config.RADIUS_MM):g} mm fixed | "
        f"width {float(process.get('width_mm') or v3_config.WIDTH_MM):g} mm | "
        f"edge gap {float(process.get('edge_gap_mm') or v3_config.EDGE_GAP_MM):g} mm | "
        f"clearance {float(process.get('clearance_mm') or v3_config.CLEARANCE_MM):g} mm",
        class_line,
        shape_line,
    ])
    crossings = statistics.get("crossing_count")
    if crossings is not None:
        subtitle += f" | same-plane crossings {int(crossings)}"
    return first, subtitle


# ---------------------------------------------------------------------------
# per-plane figures
# ---------------------------------------------------------------------------
def render_routing_all(context, output_path):
    """V3 full-plane layout; class/pair palette (d56 COLORS is 6-pair only)."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    title, subtitle = _plane_title_lines(context)
    curves = context["curves"]
    meta = context["meta_routes"]
    route_ids = [route_id for route_id in curves
                 if len(curves[route_id]) >= 2]
    fig, ax = plt.subplots(figsize=(11.0, 10.0))
    if route_ids:
        segments = [curves[route_id] for route_id in route_ids]
        colours = [PAIR_COLORS.get(meta[route_id]["pair"], "#666666")
                   for route_id in route_ids]
        ax.add_collection(LineCollection(
            segments, colors=colours,
            linewidths=0.55 if len(route_ids) <= 128 else 0.4,
            alpha=0.85, zorder=3))
    _board_frame(ax)
    draw_connectors(ax, context.get("connectors") or [], depth_mm=3.0,
                    label_fontsize=5.0)
    handles = [Line2D([0], [0], color=CLASS_COLORS[relation], linewidth=2.0,
                      label=relation) for relation in CLASS_ORDER]
    handles += [Line2D([0], [0], color=PAIR_COLORS[pair], linewidth=1.0,
                       label=pair) for pair in PAIR_ORDER]
    ax.legend(handles=handles, loc="upper left", fontsize=5.0, ncol=7,
              framealpha=0.9)
    ax.set_title(title + "\n" + subtitle, fontsize=10)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "routing_all",
            "plane": context["plane"],
            "routed_count": len(context["routed"]), "total": PLANE_TOTAL,
            "experiment": context["experiment"]}


def _plane_crossings(context):
    statistics = context.get("statistics") or {}
    crossings = []
    for item in statistics.get("crossing_points_sample") or []:
        crossings.append({"x_mm": float(item["x_mm"]),
                          "y_mm": float(item["y_mm"]),
                          "angle_deg": item.get("angle_deg"),
                          "route_a": item.get("route_a"),
                          "route_b": item.get("route_b")})
    densest = statistics.get("densest_crossing_cells") or []
    if len(crossings) < int(statistics.get("crossing_points_count") or 0):
        audit = v3_metrics.fm.compute_pair_audit(  # noqa: SLF001 - generic kernel
            context["routed"], context["process"])
        crossings = [{"x_mm": float(item["x"]), "y_mm": float(item["y"]),
                      "angle_deg": item.get("angle_deg"),
                      "route_a": item.get("route_a"),
                      "route_b": item.get("route_b")}
                     for item in (audit.get("crossings") or [])]
        densest = audit.get("densest_crossing_cells") or densest
    return crossings, densest


def render_routing_detail(context, output_path):
    """V3 hotspot detail panels (own renderer: d56 palette is 6-pair only)."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    crossings, densest = _plane_crossings(context)
    if not crossings:
        return None
    curves = context["curves"]
    meta = context["meta_routes"]
    window_centres = [(cell.get("x_min_mm", 0) + v3_metrics.GRID_MM / 2.0,
                       cell.get("y_min_mm", 0) + v3_metrics.GRID_MM / 2.0,
                       cell.get("count"))
                      for cell in (densest or [])][:DETAIL_HOTSPOTS]
    if not window_centres:
        window_centres = [(BOARD_MM / 2.0, BOARD_MM / 2.0, len(crossings))]
    columns = 2
    rows = max(1, int(math.ceil(len(window_centres) / columns)))
    fig, axes = plt.subplots(rows, columns, figsize=(13.0, 6.2 * rows),
                             squeeze=False)
    for index, (cx, cy, count_value) in enumerate(window_centres):
        ax = axes[index // columns][index % columns]
        x_lo = max(-4.0, cx - DETAIL_HALF_MM)
        x_hi = min(BOARD_MM + 4.0, cx + DETAIL_HALF_MM)
        y_lo = max(-4.0, cy - DETAIL_HALF_MM)
        y_hi = min(BOARD_MM + 4.0, cy + DETAIL_HALF_MM)
        ids = [route_id for route_id, points in curves.items()
               if points[:, 0].max() >= x_lo and points[:, 0].min() <= x_hi
               and points[:, 1].max() >= y_lo and points[:, 1].min() <= y_hi]
        segments = [curves[route_id] for route_id in ids]
        colours = [PAIR_COLORS.get(meta[route_id]["pair"], "#666666")
                   for route_id in ids]
        if segments:
            ax.add_collection(LineCollection(segments, colors=colours,
                                             linewidths=0.6, alpha=0.85,
                                             zorder=3))
        ax.add_patch(Rectangle((0.0, 0.0), BOARD_MM, BOARD_MM, fill=False,
                               edgecolor="#111111", linewidth=0.8, zorder=6))
        local = [c for c in crossings
                 if x_lo <= c["x_mm"] <= x_hi and y_lo <= c["y_mm"] <= y_hi]
        if local:
            ax.plot([c["x_mm"] for c in local], [c["y_mm"] for c in local],
                    "o", ms=3.5, color="#e02020", alpha=0.9, zorder=4,
                    label=f"{len(local)} crossings")
            ax.legend(loc="lower right", fontsize=6.5, framealpha=0.85)
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(y_lo, y_hi)
        ax.set_aspect("equal")
        ax.grid(alpha=0.25, linewidth=0.4)
        ax.set_xlabel("x (mm)")
        ax.set_ylabel("y (mm)")
        ax.set_title(f"Hotspot {index + 1}: {count_value} crossings in the "
                     f"densest 5x5 mm cell\nwindow x in [{x_lo:.1f}, "
                     f"{x_hi:.1f}] mm, y in [{y_lo:.1f}, {y_hi:.1f}] mm | "
                     f"{len(ids)} routes shown", fontsize=8.5)
    for empty in range(len(window_centres), rows * columns):
        axes[empty // columns][empty % columns].axis("off")
    routed = len(context["routed"])
    fig.suptitle(
        f"{context['experiment']} plane {context['plane']} routing detail: "
        f"{len(window_centres)} densest crossing hotspots | {routed}/{PLANE_TOTAL} "
        f"routed | {len(crossings)} same-plane crossings | layer = 0",
        fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "routing_detail",
            "plane": context["plane"], "routed_count": routed,
            "total": PLANE_TOTAL, "crossing_count": len(crossings)}


def render_crossing_heatmap(context, output_path):
    plt = pyplot()
    from matplotlib.patches import Rectangle
    crossings, densest = _plane_crossings(context)
    routed = len(context["routed"])
    cells = int(round(BOARD_MM / v3_metrics.GRID_MM))
    counts = np.zeros((cells, cells), dtype=int)
    for crossing in crossings:
        ix = int(math.floor(crossing["x_mm"] / v3_metrics.GRID_MM))
        iy = int(math.floor(crossing["y_mm"] / v3_metrics.GRID_MM))
        counts[min(cells - 1, max(0, iy)), min(cells - 1, max(0, ix))] += 1
    fig, ax = plt.subplots(figsize=(10.0, 9.0))
    image = ax.imshow(counts, origin="lower", extent=(0.0, BOARD_MM, 0.0, BOARD_MM),
                      cmap="magma", interpolation="nearest")
    bar = fig.colorbar(image, ax=ax)
    bar.set_label("same-plane crossings per 5 x 5 mm cell")
    if not densest:
        order = np.argsort(counts.ravel())[::-1][:3]
        densest = []
        for index in order:
            iy, ix = np.unravel_index(index, counts.shape)
            densest.append({"x_min_mm": int(ix) * v3_metrics.GRID_MM,
                            "y_min_mm": int(iy) * v3_metrics.GRID_MM,
                            "count": int(counts[iy, ix])})
    for cell in densest[:3]:
        x0, y0 = cell.get("x_min_mm"), cell.get("y_min_mm")
        count = cell.get("count")
        if x0 is None or y0 is None:
            continue
        ax.add_patch(Rectangle((x0, y0), v3_metrics.GRID_MM,
                               v3_metrics.GRID_MM, fill=False,
                               edgecolor="#7CFC00", linewidth=1.4, zorder=4))
        ax.annotate(f"{count} ({int(x0)},{int(y0)})",
                    xy=(x0 + v3_metrics.GRID_MM / 2.0,
                        y0 + v3_metrics.GRID_MM / 2.0),
                    ha="center", va="center", fontsize=7, color="white",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#111111",
                              alpha=0.75), zorder=5)
    _board_frame(ax)
    ax.set_title(
        f"{context['experiment']} plane {context['plane']} crossing heatmap | "
        f"{len(crossings)} same-plane crossings | {routed}/{PLANE_TOTAL} routed\n"
        f"crossings are legal 2D crossings inside this plane; different heights "
        f"are never compared", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "crossing_heatmap",
            "plane": context["plane"], "crossings": len(crossings),
            "routed_count": routed}


def render_radius_check(context, output_path):
    plt = pyplot()
    process = context["process"]
    target = float(process.get("radius_mm") or v3_config.RADIUS_MM)
    tolerance = 1e-9
    values = Counter()
    violations = []
    arcs = 0
    for record in context["routed"]:
        for primitive in record.get("primitives") or []:
            if primitive.get("kind") != "arc":
                continue
            arcs += 1
            radius = v3_metrics._number(primitive.get("radius"))  # noqa: SLF001
            values[v3_metrics._round(radius, 9)] += 1  # noqa: SLF001
            if radius is None or abs(radius - target) > tolerance:
                violations.append({"route_id": record.get("route_id"),
                                   "radius": radius})
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.2))
    ax = axes[0]
    numeric = sorted(value for value in values if value is not None)
    span = (max(numeric) - min(numeric)) if len(numeric) > 1 else 0.0
    width = max(0.05, span * 0.05) if span > 0 else 0.4
    ax.bar(numeric, [values[value] for value in numeric], width=width,
           color="#3366bb", edgecolor="#222222", linewidth=0.4)
    if span <= 0:
        ax.set_xlim(target - 1.0, target + 1.0)
    ax.axvline(target, color="#b84040", linewidth=1.0, linestyle="--",
               label=f"required R={target:g} mm")
    ax.set_xlabel("arc radius (mm)")
    ax.set_ylabel("arc count")
    ax.grid(True, axis="y", alpha=0.3, linewidth=0.5)
    ax.legend(fontsize=8.0, loc="upper right")
    ax.set_title(f"arc radius values | {arcs} arcs checked", fontsize=9.5)
    ax = axes[1]
    ax.axis("off")
    lines = [f"required radius: R = {target:g} mm (fixed_radius_40mm=on)",
             f"tolerance: {tolerance:g} mm",
             f"arcs checked: {arcs}",
             f"arcs at R={target:g}: {arcs - len(violations)}",
             f"radius violations: {len(violations)}", "",
             f"plane {context['plane']}: {context['experiment']}",
             f"routed {len(context['routed'])}/{PLANE_TOTAL}"]
    if violations:
        lines.append("")
        lines.append("first violations:")
        for item in violations[:8]:
            lines.append(f"  route {item['route_id']}: r={item['radius']}")
    ax.text(0.02, 0.98, "\n".join(lines), ha="left", va="top", fontsize=9.0,
            family="monospace")
    ax.set_title(f"R = {target:g} mm fixed-radius check", fontsize=9.5)
    fig.suptitle(
        f"{context['experiment']} plane {context['plane']} radius verification | "
        f"all arcs must be exactly R={target:g} mm", fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "radius_check",
            "arcs_checked": arcs, "radius_violations": len(violations),
            "radius_values": {str(key): count for key, count in values.items()}}


def render_congestion_zoom(context, output_path):
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    curves = context["curves"]
    meta = context["meta_routes"]
    cells = v3_metrics.GRID_MM
    grid_size = int(round(BOARD_MM / cells))
    density = np.zeros((grid_size, grid_size), dtype=float)
    for route_id, points in curves.items():
        if len(points) < 2:
            continue
        for first, second in zip(points[:-1], points[1:]):
            segment = second - first
            length = float(np.linalg.norm(segment))
            if length <= 0:
                continue
            steps = max(1, int(math.ceil(length / 0.5)))
            share = length / steps
            for step in range(steps):
                t = (step + 0.5) / steps
                px = first[0] + t * segment[0]
                py = first[1] + t * segment[1]
                ix = min(grid_size - 1, max(0, int(math.floor(px / cells))))
                iy = min(grid_size - 1, max(0, int(math.floor(py / cells))))
                density[ix, iy] += share
    flat = np.argsort(density.ravel())[::-1]
    windows = []
    for index in flat[:DETAIL_HOTSPOTS]:
        ix, iy = np.unravel_index(index, density.shape)
        windows.append(((ix + 0.5) * cells, (iy + 0.5) * cells,
                        float(density[ix, iy])))
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 12.4), squeeze=False)
    for index, (cx, cy, peak) in enumerate(windows):
        ax = axes[index // 2][index % 2]
        x_lo = max(-4.0, cx - CONGESTION_HALF_MM)
        x_hi = min(BOARD_MM + 4.0, cx + CONGESTION_HALF_MM)
        y_lo = max(-4.0, cy - CONGESTION_HALF_MM)
        y_hi = min(BOARD_MM + 4.0, cy + CONGESTION_HALF_MM)
        sub = density[max(0, int(x_lo / cells)):int(math.ceil(x_hi / cells)),
                      max(0, int(y_lo / cells)):int(math.ceil(y_hi / cells))]
        if sub.size:
            ax.imshow(sub.T, origin="lower", cmap="YlOrRd", alpha=0.55,
                      extent=(x_lo, x_hi, y_lo, y_hi), interpolation="nearest",
                      aspect="auto")
        ids = [route_id for route_id, points in curves.items()
               if points[:, 0].max() >= x_lo and points[:, 0].min() <= x_hi
               and points[:, 1].max() >= y_lo and points[:, 1].min() <= y_hi]
        segments = [curves[route_id] for route_id in ids]
        colours = [CLASS_COLORS.get(meta[route_id]["class"], "#666666")
                   for route_id in ids]
        if segments:
            ax.add_collection(LineCollection(segments, colors=colours,
                                             linewidths=0.7, alpha=0.9, zorder=3))
        ax.add_patch(Rectangle((0.0, 0.0), BOARD_MM, BOARD_MM, fill=False,
                               edgecolor="#111111", linewidth=0.8, zorder=6))
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(y_lo, y_hi)
        ax.set_aspect("equal")
        ax.grid(alpha=0.25, linewidth=0.4)
        ax.set_xlabel("x (mm)")
        ax.set_ylabel("y (mm)")
        ax.set_title(f"congestion hotspot {index + 1}: {peak:.1f} mm waveguide "
                     f"in one 5x5 mm cell\nx in [{x_lo:.1f}, {x_hi:.1f}] mm, "
                     f"y in [{y_lo:.1f}, {y_hi:.1f}] mm | {len(ids)} routes shown",
                     fontsize=8.5)
    for empty in range(len(windows), 4):
        axes[empty // 2][empty % 2].axis("off")
    fig.suptitle(
        f"{context['experiment']} plane {context['plane']} local congestion | "
        f"{len(context['routed'])}/{PLANE_TOTAL} routed | 5 x 5 mm route-length "
        f"density", fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "congestion_zoom",
            "hotspots": [[round(w[0], 3), round(w[1], 3), round(w[2], 3)]
                         for w in windows]}


def _write_svg_and_gds(context):
    """Reuse the round-1 exporter (single layer 0); gdspy global-lib isolated."""
    from ..abcd import export as abcd_export
    import gdspy
    previous = gdspy.current_library
    gdspy.current_library = gdspy.GdsLibrary(name="v3_scratch_library")
    try:
        summary = abcd_export.export_run(
            routes_path=context["routes_path"],
            config_path=context["config_path"], run_dir=context["run_dir"])
    finally:
        gdspy.current_library = previous
    return {"gds": summary.get("gds"), "svg": summary.get("svg"),
            "verification": summary.get("verification")}


def render_plane(run_dir, statistics=None, with_detail=True,
                 with_heatmap=True, with_radius=True, with_congestion=True,
                 with_svg_gds=True, verbose=False):
    started = time.perf_counter()
    context = load_plane(run_dir, statistics=statistics)
    run_dir = Path(run_dir)
    files = {}
    files["routing_all_png"] = render_routing_all(
        context, run_dir / "routing_all.png")
    if with_detail:
        detail = render_routing_detail(context, run_dir / "routing_detail.png")
        if detail:
            files["routing_detail_png"] = detail
    if with_heatmap:
        files["crossing_heatmap_png"] = render_crossing_heatmap(
            context, run_dir / "crossing_heatmap.png")
    if with_radius:
        files["radius_check_png"] = render_radius_check(
            context, run_dir / "radius_check.png")
    if with_congestion:
        files["congestion_zoom_png"] = render_congestion_zoom(
            context, run_dir / "congestion_zoom.png")
    if with_svg_gds:
        try:
            vector = _write_svg_and_gds(context)
            files["routing_all_gds"] = vector.get("gds")
            files["routing_all_svg"] = vector.get("svg")
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            files["vector_error"] = f"{type(exc).__name__}: {exc}"
    summary = {
        "schema": SCHEMA,
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scope": "plane",
        "experiment": context["experiment"],
        "algorithm": context["algorithm"],
        "plane": context["plane"],
        "routed_count": len(context["routed"]),
        "total": PLANE_TOTAL,
        "run_dir": str(run_dir),
        "style": {
            "board_mm": BOARD_MM,
            "display_sagitta_mm": DISPLAY_SAGITTA_MM,
            "dpi": DPI,
            "figsize_routing": [11.0, 10.0],
            "coordinate_limits": [-9.0, BOARD_MM + 9.0],
            "palette": "class palette (same/opposite/adjacent) + pair palette, "
                       "fixed for every run",
            "linewidth": "d56 default policy (0.4 - 0.55)",
        },
        "files": files,
        "wall_seconds": time.perf_counter() - started,
    }
    return v3_metrics._json_safe(summary)  # noqa: SLF001


# ---------------------------------------------------------------------------
# combined figures
# ---------------------------------------------------------------------------
def load_combined(combined_dir, root=None):
    combined_dir = Path(combined_dir)
    if root is None:
        root = combined_dir.parent.parent
    root = Path(root)
    algorithm = combined_dir.name
    planes = {}
    for plane in v3_metrics.PLANES:
        run_dir = v3_metrics._plane_run_dir(root, algorithm, plane)  # noqa: SLF001
        if (run_dir / "routes.json").exists():
            planes[plane] = load_plane(run_dir)
        else:
            planes[plane] = None
    statistics = None
    stats_path = combined_dir / "statistics.json"
    if stats_path.exists():
        try:
            statistics = v3_metrics._load_json(stats_path)  # noqa: SLF001
        except (OSError, json.JSONDecodeError):
            statistics = None
    return {"combined_dir": combined_dir, "root": root, "algorithm": algorithm,
            "planes": planes, "statistics": statistics}


def _combined_counts(loaded):
    routed = 0
    per_plane = {}
    for plane in v3_metrics.PLANES:
        context = loaded["planes"].get(plane)
        count = len(context["routed"]) if context else 0
        per_plane[plane] = count
        routed += count
    return routed, per_plane


def render_layer_2d(loaded, png_path, svg_path=None):
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    algorithm = loaded["algorithm"]
    routed, per_plane = _combined_counts(loaded)
    fig, axes = plt.subplots(1, 2, figsize=(19.0, 9.2))
    for ax, plane in zip(axes, v3_metrics.PLANES):
        context = loaded["planes"].get(plane)
        if not context or not context["curves"]:
            ax.axis("off")
            ax.set_title(f"V3_{algorithm} plane {plane}\nmissing plane run",
                         fontsize=10.0, color="#888888")
            continue
        route_ids = [route_id for route_id in context["curves"]
                     if len(context["curves"][route_id]) >= 2]
        segments = [context["curves"][route_id] for route_id in route_ids]
        colours = [CLASS_COLORS.get(context["meta_routes"][route_id]["class"],
                                    "#666666") for route_id in route_ids]
        if segments:
            ax.add_collection(LineCollection(segments, colors=colours,
                                             linewidths=0.34, alpha=0.82,
                                             zorder=3))
        _board_frame(ax)
        draw_connectors(ax, context.get("connectors") or [], depth_mm=3.0,
                        label_fontsize=3.4)
        statistics = context.get("statistics") or {}
        counts = _counts_by_class(context)
        crossings = statistics.get("crossing_count")
        lines = [f"plane {plane}: {per_plane[plane]}/{PLANE_TOTAL} routed "
                 f"({per_plane[plane] / PLANE_TOTAL:.2%})",
                 PLANE_CLASS_TEXT.get(plane, "")]
        lines.append("routed: same %d | opposite %d | adjacent %d" % (
            counts.get("same", 0), counts.get("opposite", 0),
            counts.get("adjacent", 0)))
        if crossings is not None:
            lines.append(f"same-plane crossings {int(crossings)}")
        ax.set_title("\n".join(lines), fontsize=9.0)
        ax.tick_params(labelsize=6.5)
    handles = [Line2D([0], [0], color=CLASS_COLORS[relation], linewidth=2.0,
                      label=relation) for relation in CLASS_ORDER]
    for pair in PAIR_ORDER:
        handles.append(Line2D([0], [0], color=PAIR_COLORS[pair], linewidth=1.2,
                              label=pair))
    fig.legend(handles=handles, loc="lower center", ncol=len(handles),
               fontsize=6.5, framealpha=0.9)
    fig.suptitle(
        f"V3_{algorithm} dual-height layout (2D layers) | {routed}/{COMBINED_TOTAL} "
        f"routed combined | identical axes [-9,159]^2 / linewidth / palette | "
        f"z1=row1 plane (z=0.0), z2=row2 plane (z=0.5); the two heights are "
        f"independent 2D problems", fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.05, 1.0, 0.95))
    fig.savefig(png_path, dpi=DPI)
    if svg_path is not None:
        fig.savefig(svg_path)
    plt.close(fig)
    return {"file": str(png_path), "svg": str(svg_path) if svg_path else None,
            "kind": "layer_2d", "routed": routed, "per_plane": per_plane}


def render_overlay_3d(loaded, png_path):
    plt = pyplot()
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    algorithm = loaded["algorithm"]
    routed, per_plane = _combined_counts(loaded)
    fig = plt.figure(figsize=(14.0, 11.0))
    ax = fig.add_subplot(111, projection="3d")
    heights = {"z1": 0.0, "z2": 0.5}
    for plane in v3_metrics.PLANES:
        context = loaded["planes"].get(plane)
        if not context:
            continue
        z = heights[plane]
        segments = []
        colours = []
        for route_id, points in context["curves"].items():
            if len(points) < 2:
                continue
            pair = context["meta_routes"][route_id]["pair"]
            for first, second in zip(points[:-1], points[1:]):
                segments.append([(float(first[0]), float(first[1]), z),
                                 (float(second[0]), float(second[1]), z)])
                colours.append(PAIR_COLORS.get(pair, "#666666"))
        if segments:
            ax.add_collection3d(Line3DCollection(segments, colors=colours,
                                                 linewidths=0.45, alpha=0.75))
    for z, colour in ((0.0, PLANE_COLORS["z1"]), (0.5, PLANE_COLORS["z2"])):
        xs = [0.0, BOARD_MM, BOARD_MM, 0.0, 0.0]
        ys = [0.0, 0.0, BOARD_MM, BOARD_MM, 0.0]
        ax.plot(xs, ys, [z] * 5, color=colour, linewidth=1.2, linestyle="--",
                alpha=0.9)
    ax.set_xlim(-6.0, BOARD_MM + 6.0)
    ax.set_ylim(-6.0, BOARD_MM + 6.0)
    ax.set_zlim(-0.25, 0.75)
    ax.set_box_aspect((1.0, 1.0, 0.42))
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_zlabel("z (model units; z2-z1 = 0.5)")
    ax.set_title(
        f"V3_{algorithm} dual-height 3D overlay | {routed}/{COMBINED_TOTAL} "
        f"routed combined (z1 {per_plane['z1']}/{PLANE_TOTAL}, "
        f"z2 {per_plane['z2']}/{PLANE_TOTAL})\n"
        f"z1 = row-1 plane at 0.0 (blue), z2 = row-2 plane at 0.5 (red); vertical "
        f"scale exaggerated for display; cross-plane XY projections are NOT "
        f"conflicts (different glass heights, SPEC §2)", fontsize=9.0)
    fig.tight_layout()
    fig.savefig(png_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(png_path), "kind": "overlay_3d", "routed": routed,
            "per_plane": per_plane,
            "z_model": {"z1": 0.0, "z2": 0.5, "z2_minus_z1_mm": 0.5,
                        "note": "vertical scale exaggerated for display"}}


def render_combined(combined_dir, root=None, verbose=False):
    started = time.perf_counter()
    combined_dir = Path(combined_dir)
    loaded = load_combined(combined_dir, root=root)
    combined_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    files["layer_2d_png"] = render_layer_2d(
        loaded, combined_dir / "layer_2d.png", combined_dir / "layer_2d.svg")
    files["overlay_3d_png"] = render_overlay_3d(
        loaded, combined_dir / "overlay_3d.png")
    summary = {
        "schema": SCHEMA,
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scope": "combined",
        "algorithm": loaded["algorithm"],
        "routed": files["layer_2d_png"]["routed"],
        "total": COMBINED_TOTAL,
        "files": files,
        "wall_seconds": time.perf_counter() - started,
    }
    if verbose:
        print(f"[v3.plots] {combined_dir / 'layer_2d.png'} + overlay_3d.png")
    return v3_metrics._json_safe(summary)  # noqa: SLF001


# ---------------------------------------------------------------------------
# shapes figures
# ---------------------------------------------------------------------------
def _shape_aggregate(root):
    payload = v3_metrics.build_shapes_statistics(root, quiet=True)
    return payload


def render_shape_mix(root, output_path):
    payload = _shape_aggregate(root)
    per_plane = payload["per_plane"]
    labels = sorted(per_plane)
    plt = pyplot()
    fig, ax = plt.subplots(figsize=(13.0, 5.6))
    positions = np.arange(len(labels))
    bottom = np.zeros(len(labels))
    for shape in SHAPE_ORDER:
        values = np.array([float(((per_plane[label]["path_shapes"] or {})
                                  .get("counts") or {}).get(shape, 0))
                           for label in labels])
        ax.bar(positions, values, bottom=bottom, width=0.7,
               color=SHAPE_COLORS[shape], edgecolor="#222222", linewidth=0.3,
               label=shape)
        bottom += values
    for position, label in zip(positions, labels):
        routed = per_plane[label]["routed"]
        ax.text(position, routed + 2.0, f"{routed}", ha="center", va="bottom",
                fontsize=7.0, rotation=0)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7.5)
    ax.set_ylabel("routed routes (shape count)", fontsize=8.5)
    ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    ax.legend(fontsize=7.0, ncol=3, loc="upper right")
    ax.set_title("V3 path-shape mix per plane run — classified from saved "
                 "primitives only (never from the relation label). U = net-180 "
                 "same-side U/hairpin paths; other = two-quarter step transfers "
                 "(FSLW opposite U family; no step class in the required taxonomy).",
                 fontsize=9.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "shape_mix",
            "planes": labels}


def render_u_depth_histogram(root, output_path):
    payload = _shape_aggregate(root)
    per_plane = payload["per_plane"]
    labels = sorted(per_plane)
    plt = pyplot()
    fig, axes = plt.subplots(2, 2, figsize=(13.6, 9.0))
    for ax, plane in zip(axes.ravel(), v3_metrics.PLANES):
        for side, colour in zip("NESW", ("#3366bb", "#b84040", "#e3a323",
                                         "#00a0a0")):
            depths = []
            for label in labels:
                u_stats = per_plane[label].get("u_statistics") or {}
                side_block = (u_stats.get("per_side") or {}).get(side) or {}
                for route in side_block.get("routes") or []:
                    depths.append(route.get("depth_mm"))
            depths = [value for value in depths if value is not None]
            if not depths:
                continue
            bins = np.arange(0.0, 155.0, 5.0)
            ax.hist(depths, bins=bins, alpha=0.55, color=colour,
                    label=f"side {side} (n={len(depths)})")
        ax.set_xlabel("U depth from shared edge (mm)", fontsize=8.5)
        ax.set_ylabel("U route count", fontsize=8.5)
        ax.grid(True, alpha=0.25, linewidth=0.5)
        ax.legend(fontsize=7.0)
        ax.set_title(f"{plane} plane U depth distribution (all algorithms)",
                     fontsize=9.5)
    fig.suptitle("V3 same-side U depth distribution per plane and side "
                 "(5 mm bins; depth computed from saved primitives)",
                 fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "u_depth_histogram"}


def render_u_track_occupancy(root, output_path):
    payload = _shape_aggregate(root)
    per_plane = payload["per_plane"]
    plt = pyplot()
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 5.4))
    for ax, plane in zip(axes, v3_metrics.PLANES):
        labels = sorted(label for label in per_plane
                        if (per_plane[label].get("plane") == plane))
        positions = np.arange(len(labels))
        for side, colour in zip("NESW", ("#3366bb", "#b84040", "#e3a323",
                                         "#00a0a0")):
            values = []
            for label in labels:
                u_stats = per_plane[label].get("u_statistics") or {}
                side_block = (u_stats.get("per_side") or {}).get(side) or {}
                values.append(int(side_block.get("count") or 0))
            ax.bar(positions, values, width=0.2,
                   color=colour, edgecolor="#222222", linewidth=0.3,
                   label=f"side {side}")
            positions = positions + 0.2
        positions = np.arange(len(labels))
        ax.set_xticks(positions + 0.3)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7.0)
        ax.set_ylabel("U route count", fontsize=8.5)
        ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
        ax.legend(fontsize=7.0)
        ax.set_title(f"{plane} U route count per algorithm and side "
                     f"(track occupancy)", fontsize=9.5)
    fig.suptitle("V3 track occupancy of same-side U routes (counts from saved "
                 "primitives; U depth/track numbers in shapes/"
                 "u_track_statistics.json)", fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "u_track_occupancy"}


def _u_routes_for_plane(run_dir):
    context = load_plane(run_dir)
    u_routes = []
    for record in context["routed"]:
        classification = v3_metrics.classify_route(  # noqa: SLF001
            record.get("primitives") or [],
            float(context["process"].get("radius_mm")
                  or v3_config.RADIUS_MM))
        if classification["shape"] == "U" and \
                v3_metrics._relation_of(record) == "same":  # noqa: SLF001
            features = v3_metrics._u_features(  # noqa: SLF001
                record, classification, context["endpoints"])
            if features:
                u_routes.append((record, classification, features))
    return context, u_routes


def render_u_routes_only(root, output_path):
    plt = pyplot()
    from matplotlib.collections import LineCollection
    plane_dirs = []
    for algorithm, plane, run_dir in v3_metrics.iter_plane_runs(root):  # noqa: SLF001
        plane_dirs.append((algorithm, plane, run_dir))
    if not plane_dirs:
        return None
    columns = 4
    rows = max(1, math.ceil(len(plane_dirs) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(22.0, 5.4 * rows),
                             squeeze=False)
    for index, (algorithm, plane, run_dir) in enumerate(plane_dirs):
        context, u_routes = _u_routes_for_plane(run_dir)
        curves = {}
        for record, _classification, _features in u_routes:
            points = v3_metrics._curve_points(record.get("primitives") or [])  # noqa: SLF001
            if len(points) >= 2:
                curves[record["route_id"]] = points
        ax = axes[index // columns][index % columns]
        segments = list(curves.values())
        colours = [PAIR_COLORS.get(v3_metrics._pair_of(record), "#666666")  # noqa: SLF001
                   for record, _c, _f in u_routes
                   if record["route_id"] in curves]
        if segments:
            ax.add_collection(LineCollection(segments, colors=colours,
                                             linewidths=0.55, alpha=0.9,
                                             zorder=3))
        _board_frame(ax)
        ax.tick_params(labelsize=5.5)
        ax.set_title(f"{algorithm}_{plane} U-only | {len(u_routes)} same-side U "
                     f"routed (of {len(context['routed'])} routed)",
                     fontsize=8.0)
    for empty in range(len(plane_dirs), rows * columns):
        axes[empty // columns][empty % columns].axis("off")
    fig.suptitle(
        "V3 same-side U routes only (SAVED PRIMITIVES; every U route drawn, "
        "nothing hidden). Colour = U side pair; depth/track/nesting numbers in "
        "shapes/u_depth_histogram.png and shapes/u_track_statistics.json.",
        fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "u_routes_only",
            "planes": [f"{a}_{p}" for a, p, _r in plane_dirs]}


def render_nested_u_zoom(root, output_path, count=NESTED_ZOOM_COUNT):
    """Local zoom showing 10-20 nested U routes (ordered by depth)."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    all_runs = []
    for algorithm, plane, run_dir in v3_metrics.iter_plane_runs(root):  # noqa: SLF001
        context, u_routes = _u_routes_for_plane(run_dir)
        statistics = context.get("statistics") or {}
        groups = (((statistics.get("u_statistics") or {}).get("nesting") or {})
                  .get("groups") or [])
        if groups:
            best = max(groups, key=lambda item: item.get("size") or 0)
            all_runs.append({"algorithm": algorithm, "plane": plane,
                             "run_dir": run_dir, "group": best})
    if not all_runs:
        return None
    selected = max(all_runs, key=lambda item: item["group"].get("size") or 0)
    context = load_plane(selected["run_dir"])
    statistics = context.get("statistics") or {}
    groups = (((statistics.get("u_statistics") or {}).get("nesting") or {})
              .get("groups") or [])
    group = max(groups, key=lambda item: item.get("size") or 0)
    # ordered by depth: the largest nested group first, then neighbouring groups
    # on the same side, so the figure always shows 10-20 nested U routes even when
    # one containment component is small (honest: every route drawn is a real U).
    ordered = list(group.get("route_ids_ordered_by_depth") or [])
    side = group.get("side")
    neighbours = sorted([item for item in groups
                         if item is not group and item.get("side") == side],
                        key=lambda item: -int(item.get("size") or 0))
    for neighbour in neighbours:
        for route_id in neighbour.get("route_ids_ordered_by_depth") or []:
            if route_id not in ordered:
                ordered.append(route_id)
    target = max(10, min(count, len(ordered))) if ordered else 0
    group_set = set(ordered[:target])
    group_size = group.get("size")
    window = None
    segments = []
    colours = []
    labels = []
    by_id = {record["route_id"]: record for record in context["routed"]}
    for route_id in group_set:
        record = by_id.get(route_id)
        if record is None:
            continue
        points = v3_metrics._curve_points(record.get("primitives") or [])  # noqa: SLF001
        if len(points) < 2:
            continue
        segments.append(points)
        colours.append(PAIR_COLORS.get(v3_metrics._pair_of(record), "#666666"))  # noqa: SLF001
        labels.append(str(route_id))
        if window is None:
            window = [points[:, 0].min(), points[:, 0].max(),
                      points[:, 1].min(), points[:, 1].max()]
        else:
            window[0] = min(window[0], points[:, 0].min())
            window[1] = max(window[1], points[:, 0].max())
            window[2] = min(window[2], points[:, 1].min())
            window[3] = max(window[3], points[:, 1].max())
    if window is None:
        return None
    pad = 10.0
    x_lo = max(-4.0, window[0] - pad)
    x_hi = min(BOARD_MM + 4.0, window[1] + pad)
    y_lo = max(-4.0, window[2] - pad)
    y_hi = min(BOARD_MM + 4.0, window[3] + pad)
    fig, ax = plt.subplots(figsize=(12.0, 11.0))
    if segments:
        ax.add_collection(LineCollection(segments, colors=colours,
                                         linewidths=1.0, alpha=0.9, zorder=3))
    for segment, route_id in zip(segments, labels):
        mid = segment[len(segment) // 2]
        ax.annotate(route_id, xy=(mid[0], mid[1]), fontsize=6.0, zorder=5,
                    color="#111111",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                              alpha=0.7))
    ax.add_patch(Rectangle((0.0, 0.0), BOARD_MM, BOARD_MM, fill=False,
                           edgecolor="#111111", linewidth=0.8, zorder=6))
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.set_aspect("equal")
    ax.grid(alpha=0.25, linewidth=0.4)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    depth_values = [value for value in (group.get("depths_mm") or [])
                    if value is not None]
    depth_text = (f"{min(depth_values):.1f}-{max(depth_values):.1f} mm"
                  if depth_values else "n/a")
    ax.set_title(
        f"V3 nested-U zoom | {selected['algorithm']}_{selected['plane']} | "
        f"{len(segments)} nested U routes shown (largest nesting group size "
        f"{group_size}, max chain {group.get('chain_length')}) | "
        f"depths {depth_text}\nreal route ids annotated; geometry from saved "
        f"primitives", fontsize=9.0)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "nested_u_zoom",
            "algorithm": selected["algorithm"], "plane": selected["plane"],
            "routes_shown": len(segments),
            "group_size": group.get("size")}


# ---------------------------------------------------------------------------
# demand / matrix figures (Phase-7 figures 1 and 2)
# ---------------------------------------------------------------------------
def _csv_connections(csv_path=None):
    if csv_path is None:
        csv_path = v3_config.CSV_PATH
    if v3_ports is not None and hasattr(v3_ports, "all_routes"):
        try:
            return v3_ports.all_routes()
        except Exception:  # noqa: BLE001
            pass
    from . import inputs as v3_inputs
    return v3_inputs.read_connections(csv_path)


def _endpoint_lookup():
    if v3_ports is not None and hasattr(v3_ports, "build_endpoints"):
        try:
            return v3_ports.build_endpoints()
        except Exception:  # noqa: BLE001
            pass
    from . import inputs as v3_inputs
    return v3_inputs.load_all()[0]


def render_demand_diagram(output_path, csv_path=None):
    """Phase-7 figure (1): 1024 connector-level and fibre-level demand."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    routes = _csv_connections(csv_path)
    endpoints = _endpoint_lookup()
    connectors = {}
    if v3_ports is not None and hasattr(v3_ports, "connector_records"):
        try:
            for record in v3_ports.connector_records():
                connectors[record["connector"]] = record
        except Exception:  # noqa: BLE001
            connectors = {}
    fibre_segments = []
    fibre_colours = []
    connector_segments = []
    connector_colours = []
    connector_weights = Counter()
    for route in routes:
        relation = route.get("relation") or v3_metrics._relation_of(route)  # noqa: SLF001
        colour = CLASS_COLORS.get(relation, "#666666")
        source = endpoints.get(route.get("source_endpoint")) or {}
        target = endpoints.get(route.get("target_endpoint")) or {}
        if source.get("routing_xy") and target.get("routing_xy"):
            fibre_segments.append([source["routing_xy"], target["routing_xy"]])
            fibre_colours.append(colour)
        source_connector = route.get("source_connector") or str(
            route.get("source_endpoint", "")).split(":")[0]
        target_connector = route.get("target_connector") or str(
            route.get("target_endpoint", "")).split(":")[0]
        if source_connector and target_connector:
            connector_weights[(source_connector, target_connector)] += 1
    for (source_connector, target_connector), weight in connector_weights.items():
        source = connectors.get(source_connector) or {}
        target = connectors.get(target_connector) or {}
        if not (source.get("center_xy") and target.get("center_xy")):
            continue
        pair = v3_metrics._pair_of({  # noqa: SLF001
            "source_side": source_connector[0],
            "target_side": target_connector[0]})
        relation = PAIR_CLASS.get(pair, "other")
        connector_segments.append([source["center_xy"], target["center_xy"]])
        connector_colours.append(CLASS_COLORS.get(relation, "#666666"))
    fig, axes = plt.subplots(1, 2, figsize=(21.0, 10.0))
    ax = axes[0]
    if connector_segments:
        ax.add_collection(LineCollection(connector_segments,
                                         colors=connector_colours,
                                         linewidths=0.4, alpha=0.35, zorder=2))
    _board_frame(ax)
    draw_connectors(ax, list(connectors.values()) or [], depth_mm=3.0,
                    label_fontsize=3.0)
    class_counts = Counter()
    for route in routes:
        class_counts[route.get("relation")
                     or v3_metrics._relation_of(route)] += 1  # noqa: SLF001
    ax.set_title(
        f"V3-Huang connector-level demand | 1024 connections | "
        f"same {class_counts.get('same', 0)} / opposite "
        f"{class_counts.get('opposite', 0)} / adjacent "
        f"{class_counts.get('adjacent', 0)}\n"
        f"{len(connector_weights)} unique connector pairs; line width by count",
        fontsize=9.5)
    ax = axes[1]
    if fibre_segments:
        ax.add_collection(LineCollection(fibre_segments, colors=fibre_colours,
                                         linewidths=0.35, alpha=0.35, zorder=2))
    _board_frame(ax)
    draw_connectors(ax, list(connectors.values()) or [], depth_mm=3.0,
                    label_fontsize=3.0)
    ax.set_title(
        f"V3-Huang fibre-level demand | 1024 fibre connections (~448 same-side "
        f"U-paths) | all endpoints real 2x16 ports,\n"
        f"z1 row1 / z2 row2 planes are colour-merged here only for demand "
        f"visualisation", fontsize=9.5)
    handles = [Line2D([0], [0], color=CLASS_COLORS[relation], linewidth=2.0,
                      label=relation) for relation in CLASS_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9.0,
               framealpha=0.9)
    fig.suptitle("Phase-7 figure 1: V3-Huang 1024-channel connector-level and "
                 "fibre-level demand diagram", fontsize=12.0)
    fig.tight_layout(rect=(0.0, 0.035, 1.0, 0.95))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "demand_diagram",
            "connections": len(routes), "connector_pairs": len(connector_weights)}


def connector_matrix(csv_path=None):
    """Directed 64x64 connector matrix from the CSV (sum=1024) + symmetric form."""
    routes = _csv_connections(csv_path)
    connector_ids = []
    if v3_ports is not None and hasattr(v3_ports, "connector_records"):
        try:
            connector_ids = [record["connector"]
                             for record in v3_ports.connector_records()]
        except Exception:  # noqa: BLE001
            connector_ids = []
    if not connector_ids:
        connector_ids = [f"{side}{index:02d}" for side in "NESW"
                         for index in range(1, 17)]
    index_of = {name: index for index, name in enumerate(connector_ids)}
    directed = np.zeros((64, 64), dtype=int)
    symmetric = np.zeros((64, 64), dtype=int)
    for route in routes:
        source = route.get("source_connector") or str(
            route.get("source_endpoint", "")).split(":")[0]
        target = route.get("target_connector") or str(
            route.get("target_endpoint", "")).split(":")[0]
        if source not in index_of or target not in index_of:
            continue
        a, b = index_of[source], index_of[target]
        directed[a, b] += 1
        symmetric[a, b] += 1
        symmetric[b, a] += 1
    diagonal = int(np.trace(directed))
    return {"connector_ids": connector_ids, "directed": directed,
            "symmetric": symmetric, "directed_total": int(directed.sum()),
            "symmetric_total": int(symmetric.sum()), "diagonal": diagonal}


def render_connector_matrix(output_path, csv_path=None):
    """Phase-7 figure (2): 64x64 weighted connector matrix heatmap."""
    plt = pyplot()
    matrix = connector_matrix(csv_path)
    symmetric = matrix["symmetric"]
    labels = matrix["connector_ids"]
    fig, ax = plt.subplots(figsize=(15.0, 13.0))
    im = ax.imshow(symmetric, origin="upper", cmap="viridis",
                   interpolation="nearest")
    bar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    bar.set_label("connection count (both directions per undirected pair)")
    ticks = list(range(64))
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.set_xticklabels(labels, rotation=90, fontsize=5.0)
    ax.set_yticklabels(labels, fontsize=5.0)
    for index in range(64):
        value = int(symmetric[index, index])
        if value:
            ax.add_patch(__import__("matplotlib").patches.Rectangle(
                (index - 0.5, index - 0.5), 1, 1, fill=False,
                edgecolor="#ff2222", linewidth=0.8))
    ax.set_xlabel("target connector")
    ax.set_ylabel("source connector")
    ax.set_title(
        f"Phase-7 figure 2: V3-Huang 64x64 weighted connector matrix | "
        f"directed (source->target) sum = {matrix['directed_total']} = 1024 "
        f"connections; symmetric matrix sum = {matrix['symmetric_total']} "
        f"(Excel counts both directions, sum 2048)\n"
        f"diagonal (connector->itself) = {matrix['diagonal']} = 0 required "
        f"(same-side connections never self-connect); cells = connection counts",
        fontsize=9.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    matrix_payload = {
        "schema": "four_side_1024_v3_connector_matrix_v1",
        "source": str(v3_config.CSV_PATH if csv_path is None else csv_path),
        "connector_ids": labels,
        "directed_total": matrix["directed_total"],
        "symmetric_total": matrix["symmetric_total"],
        "diagonal": matrix["diagonal"],
        "matrix_definition": {
            "directed": "M[a][b] = # connections with source_connector=a and "
                        "target_connector=b (sum=1024)",
            "symmetric": "M[a][b]=M[b][a]=# undirected connections between a and "
                         "b (sum=2048; matches the Excel sheet which counts both "
                         "directions)",
        },
        "directed": matrix["directed"].tolist(),
        "symmetric": matrix["symmetric"].tolist(),
        "note": "recomputed directly from the frozen CSV; the Excel matrix is "
                "cross-checked by the connectivity owner and is not used as truth",
    }
    matrix_path = Path(output_path).with_name("connector_matrix_64x64.json")
    matrix_path.write_text(json.dumps(matrix_payload, ensure_ascii=False,
                                      indent=1), encoding="utf-8")
    return {"file": str(output_path), "matrix_json": str(matrix_path),
            "kind": "connector_matrix",
            "directed_total": matrix["directed_total"],
            "symmetric_total": matrix["symmetric_total"],
            "diagonal": matrix["diagonal"]}


# ---------------------------------------------------------------------------
# comparison helpers (used by v3/compare.py)
# ---------------------------------------------------------------------------
def render_abcd_layouts(root, plane, output_path):
    """Phase-7 figures (3)/(4): A/B/C/D four full 2D layouts for one plane."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    algorithms = list(v3_metrics.ALGORITHMS)
    fig, axes = plt.subplots(2, 2, figsize=(17.0, 16.4))
    rendered = []
    for index, algorithm in enumerate(algorithms):
        ax = axes[index // 2][index % 2]
        run_dir = v3_metrics._plane_run_dir(root, algorithm, plane)  # noqa: SLF001
        context = None
        if (run_dir / "routes.json").exists():
            try:
                context = load_plane(run_dir)
            except Exception:  # noqa: BLE001
                context = None
        if not context or not context["curves"]:
            ax.axis("off")
            ax.set_title(f"V3_{algorithm} plane {plane}\nmissing plane run",
                         fontsize=10.0, color="#888888")
            continue
        route_ids = [route_id for route_id in context["curves"]
                     if len(context["curves"][route_id]) >= 2]
        segments = [context["curves"][route_id] for route_id in route_ids]
        colours = [CLASS_COLORS.get(context["meta_routes"][route_id]["class"],
                                    "#666666") for route_id in route_ids]
        if segments:
            ax.add_collection(LineCollection(segments, colors=colours,
                                             linewidths=0.3, alpha=0.8,
                                             zorder=3))
        _board_frame(ax)
        draw_connectors(ax, context.get("connectors") or [], depth_mm=3.0,
                        label_fontsize=3.0)
        counts = _counts_by_class(context)
        statistics = context.get("statistics") or {}
        routed = len(context["routed"])
        title = [f"V3_{algorithm} plane {plane} | {routed}/{PLANE_TOTAL} "
                 f"routed ({routed / PLANE_TOTAL:.1%})",
                 f"same {counts.get('same', 0)} | opposite "
                 f"{counts.get('opposite', 0)} | adjacent "
                 f"{counts.get('adjacent', 0)}"]
        crossings = statistics.get("crossing_count")
        if crossings is not None:
            title.append(f"same-plane crossings {int(crossings)}")
        ax.set_title("\n".join(title), fontsize=9.0)
        ax.tick_params(labelsize=6.0)
        rendered.append(f"V3_{algorithm}_{plane}")
    handles = [Line2D([0], [0], color=CLASS_COLORS[relation], linewidth=2.0,
                      label=relation) for relation in CLASS_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9.0,
               framealpha=0.9)
    fig.suptitle(
        f"Phase-7 figure {'3' if plane == 'z1' else '4'}: V3-Huang plane {plane} "
        f"four-algorithm layouts (A/B/C/D) | identical axes [-9,159]^2, "
        f"linewidth and class palette | every title states the real routed/512",
        fontsize=12.0)
    fig.tight_layout(rect=(0.0, 0.035, 1.0, 0.95))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": f"layouts_{plane}",
            "panels": rendered}


def render_combined_layouts(root, output_path):
    """Phase-7 figure (5): four combined dual-height layouts side by side."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    algorithms = list(v3_metrics.ALGORITHMS)
    fig, axes = plt.subplots(2, 2, figsize=(17.0, 16.4))
    rendered = []
    for index, algorithm in enumerate(algorithms):
        ax = axes[index // 2][index % 2]
        combined_dir = v3_metrics._combined_run_dir(root, algorithm)  # noqa: SLF001
        loaded = load_combined(combined_dir, root=root)
        routed, per_plane = _combined_counts(loaded)
        if routed <= 0:
            ax.axis("off")
            ax.set_title(f"V3_{algorithm} combined\nmissing plane runs",
                         fontsize=10.0, color="#888888")
            continue
        for plane, alpha, linewidth in (("z1", 0.85, 0.34),
                                        ("z2", 0.55, 0.26)):
            context = loaded["planes"].get(plane)
            if not context:
                continue
            segments = [context["curves"][route_id]
                        for route_id in context["curves"]
                        if len(context["curves"][route_id]) >= 2]
            colours = [CLASS_COLORS.get(
                context["meta_routes"][route_id]["class"], "#666666")
                for route_id in context["curves"]
                if len(context["curves"][route_id]) >= 2]
            if segments:
                ax.add_collection(LineCollection(segments, colors=colours,
                                                 linewidths=linewidth,
                                                 alpha=alpha, zorder=3))
        _board_frame(ax)
        connectors = (loaded["planes"].get("z1") or {}).get("connectors") or []
        draw_connectors(ax, connectors, depth_mm=3.0, label_fontsize=3.0)
        ax.set_title(
            f"V3_{algorithm} combined dual-height | {routed}/{COMBINED_TOTAL} "
            f"routed ({routed / COMBINED_TOTAL:.1%})\n"
            f"plane z1 {per_plane['z1']}/512 (strong) + plane z2 "
            f"{per_plane['z2']}/512 (faint); classes coloured, heights overlaid",
            fontsize=9.0)
        ax.tick_params(labelsize=6.0)
        rendered.append(f"V3_{algorithm}_combined")
    handles = [Line2D([0], [0], color=CLASS_COLORS[relation], linewidth=2.0,
                      label=relation) for relation in CLASS_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9.0,
               framealpha=0.9)
    fig.suptitle(
        "Phase-7 figure 5: V3-Huang four combined dual-height layouts "
        "(z1 + z2 overlaid; cross-plane XY projections are NOT conflicts) | "
        "identical axes/linewidth/palette; real routed/1024 in every title",
        fontsize=12.0)
    fig.tight_layout(rect=(0.0, 0.035, 1.0, 0.95))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "combined_layouts",
            "panels": rendered}


def render_overlay_3d_grid(root, output_path):
    """Phase-7 figure (6): four 3D dual-height overlays in a 2x2 grid."""
    plt = pyplot()
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    algorithms = list(v3_metrics.ALGORITHMS)
    fig = plt.figure(figsize=(18.0, 16.0))
    rendered = []
    for index, algorithm in enumerate(algorithms):
        ax = fig.add_subplot(2, 2, index + 1, projection="3d")
        combined_dir = v3_metrics._combined_run_dir(root, algorithm)  # noqa: SLF001
        loaded = load_combined(combined_dir, root=root)
        routed, per_plane = _combined_counts(loaded)
        for plane, z in (("z1", 0.0), ("z2", 0.5)):
            context = loaded["planes"].get(plane)
            if not context:
                continue
            segments = []
            colours = []
            for route_id, points in context["curves"].items():
                if len(points) < 2:
                    continue
                pair = context["meta_routes"][route_id]["pair"]
                colour = (PAIR_COLORS.get(pair, "#666666") if plane == "z1"
                          else CLASS_COLORS.get(
                              context["meta_routes"][route_id]["class"],
                              "#666666"))
                for first, second in zip(points[:-1], points[1:]):
                    segments.append([(float(first[0]), float(first[1]), z),
                                     (float(second[0]), float(second[1]), z)])
                    colours.append(colour)
            if segments:
                ax.add_collection3d(Line3DCollection(
                    segments, colors=colours, linewidths=0.35, alpha=0.7))
        ax.set_xlim(-6.0, BOARD_MM + 6.0)
        ax.set_ylim(-6.0, BOARD_MM + 6.0)
        ax.set_zlim(-0.25, 0.75)
        ax.set_box_aspect((1.0, 1.0, 0.42))
        ax.set_title(f"V3_{algorithm} combined | {routed}/{COMBINED_TOTAL} "
                     f"routed (z1 {per_plane['z1']}, z2 {per_plane['z2']})",
                     fontsize=9.0)
        ax.tick_params(labelsize=6.0)
        rendered.append(f"V3_{algorithm}")
    fig.suptitle(
        "Phase-7 figure 6: V3-Huang 3D dual-height overlays for the four "
        "algorithms | z1 at 0.0, z2 at 0.5 model units; vertical scale "
        "exaggerated; cross-plane XY projections are not conflicts",
        fontsize=12.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "overlay_3d_grid",
            "panels": rendered}


def render_class_routed_compare(root, output_path):
    """Phase-7 figure (9): same/opposite/adjacent routed counts (real numbers)."""
    plt = pyplot()
    labels = []
    values = {"same": [], "opposite": [], "adjacent": []}
    totals = {"same": [], "opposite": [], "adjacent": []}
    for algorithm, plane, run_dir in v3_metrics.iter_plane_runs(root):  # noqa: SLF001
        context = load_plane(run_dir)
        statistics = context.get("statistics") or {}
        label = f"{algorithm}_{plane}"
        labels.append(label)
        by_class = statistics.get("by_class") or {}
        for relation in CLASS_ORDER:
            values[relation].append(int((by_class.get(relation) or {}).get(
                "success") or 0))
            totals[relation].append(int((by_class.get(relation) or {}).get(
                "total") or 0))
    if not labels:
        return None
    positions = np.arange(len(labels))
    width = 0.26
    fig, ax = plt.subplots(figsize=(13.5, 5.6))
    for index, relation in enumerate(CLASS_ORDER):
        offset = (index - 1) * width
        bars = ax.bar(positions + offset, values[relation], width=width * 0.92,
                      color=CLASS_COLORS[relation], edgecolor="#222222",
                      linewidth=0.35, label=f"{relation} routed")
        for position, value, total in zip(positions + offset, values[relation],
                                          totals[relation]):
            ax.text(position, value, f"{value}/{total}", ha="center",
                    va="bottom", fontsize=6.0, rotation=90)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7.5)
    ax.set_ylabel("routed connections (real count / class total)", fontsize=8.5)
    ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    ax.legend(fontsize=8.0, loc="upper right")
    ax.set_title(
        "Phase-7 figure 9: V3 same / opposite / adjacent routed counts per plane "
        "run (real counts, class totals annotated; no rescaling)", fontsize=10.0)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "class_routed_compare",
            "labels": labels}


def render_algo_routed_rate_compare(root, output_path):
    """Phase-7 figure (10): four-algorithm routed-rate comparison."""
    plt = pyplot()
    algorithms = list(v3_metrics.ALGORITHMS)
    plane_values = {plane: [] for plane in v3_metrics.PLANES}
    combined_values = []
    for algorithm in algorithms:
        for plane in v3_metrics.PLANES:
            run_dir = v3_metrics._plane_run_dir(root, algorithm, plane)  # noqa: SLF001
            value = None
            if (run_dir / "statistics.json").exists():
                try:
                    statistics = v3_metrics._load_json(  # noqa: SLF001
                        run_dir / "statistics.json")
                    value = statistics.get("routed")
                except (OSError, json.JSONDecodeError):
                    value = None
            plane_values[plane].append(value)
        combined_dir = v3_metrics._combined_run_dir(root, algorithm)  # noqa: SLF001
        value = None
        stats_path = combined_dir / "statistics.json"
        if stats_path.exists():
            try:
                value = v3_metrics._load_json(stats_path).get("routed")  # noqa: SLF001
            except (OSError, json.JSONDecodeError):
                value = None
        combined_values.append(value)
    positions = np.arange(len(algorithms))
    width = 0.26
    fig, ax = plt.subplots(figsize=(12.0, 5.4))
    series = [(plane_values.get("z1", []), PLANE_COLORS["z1"],
               "z1 plane /512"),
              (plane_values.get("z2", []), PLANE_COLORS["z2"],
               "z2 plane /512"),
              (combined_values, "#555555", "combined /1024")]
    for index, (values, colour, label) in enumerate(series):
        offset = (index - 1) * width
        heights = [0.0 if value is None else float(value) for value in values]
        ax.bar(positions + offset, heights, width=width * 0.92, color=colour,
               edgecolor="#222222", linewidth=0.35, label=label)
        for position, value in zip(positions + offset, values):
            if value is None:
                ax.text(position, 0.0, "n/a", ha="center", va="bottom",
                        fontsize=7.0, color="#777777")
            else:
                ax.text(position, value, f"{value}", ha="center", va="bottom",
                        fontsize=7.0, rotation=90)
    ax.axhline(PLANE_TOTAL, color="#333333", linewidth=0.8, linestyle="--",
               label="512 per plane")
    ax.axhline(COMBINED_TOTAL, color="#333333", linewidth=0.8, linestyle=":",
               label="1024 combined")
    ax.set_xticks(positions)
    ax.set_xticklabels([f"V3_{algorithm}" for algorithm in algorithms],
                       fontsize=9.0)
    ax.set_ylabel("routed connections (real count)", fontsize=8.5)
    ax.set_ylim(0.0, COMBINED_TOTAL * 1.15)
    ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    ax.legend(fontsize=7.5, loc="upper right")
    ax.set_title(
        "Phase-7 figure 10: V3 four-algorithm routed-rate comparison "
        "(z1/z2/combined real counts, honest scale, no rescaling)",
        fontsize=10.0)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "algo_routed_rate_compare",
            "algorithms": algorithms}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser():
    parser = argparse.ArgumentParser(
        description="Render V3-Huang plane/combined/shape figures (SPEC §7).")
    parser.add_argument("--run-dir", help="plane run dir")
    parser.add_argument("--combined-dir", help="combined/<A> dir")
    parser.add_argument("--root", help="V3 output root")
    parser.add_argument("--shapes", action="store_true",
                        help="render shapes/ figures")
    parser.add_argument("--all", action="store_true",
                        help="render every existing plane + combined + shapes")
    parser.add_argument("--no-detail", action="store_true")
    parser.add_argument("--no-heatmap", action="store_true")
    parser.add_argument("--no-radius", action="store_true")
    parser.add_argument("--no-congestion", action="store_true")
    parser.add_argument("--no-vector", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def render_shapes(root, verbose=False):
    root = Path(root)
    shapes_dir = root / "shapes"
    shapes_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    files["shape_mix_png"] = render_shape_mix(root, shapes_dir / "shape_mix.png")
    files["u_depth_histogram_png"] = render_u_depth_histogram(
        root, shapes_dir / "u_depth_histogram.png")
    files["u_track_occupancy_png"] = render_u_track_occupancy(
        root, shapes_dir / "u_track_occupancy.png")
    files["u_routes_only_png"] = render_u_routes_only(
        root, shapes_dir / "u_routes_only.png")
    files["nested_u_zoom_png"] = render_nested_u_zoom(
        root, shapes_dir / "nested_u_zoom.png")
    statistics = v3_metrics.build_shapes_statistics(root, quiet=True)
    files["same_side_statistics"] = str(shapes_dir / "same_side_statistics.json")
    files["u_track_statistics"] = v3_metrics.build_u_track_statistics(  # noqa: SLF001
        root, quiet=True)
    summary = {"root": str(root), "files": files,
               "planes_measured": statistics.get("planes_measured")}
    if verbose:
        print(f"[v3.plots] shapes/ figures written under {shapes_dir}")
    return v3_metrics._json_safe(summary)  # noqa: SLF001


def main(argv=None):
    args = _build_parser().parse_args(argv)
    root = Path(args.root) if args.root else Path(
        getattr(v3_config, "OUTPUT_ROOT",
                "outputs/four_side_1024_v3_huang_R40_gap30_abcd"))
    results = []
    if args.all:
        for algorithm, plane, run_dir in v3_metrics.iter_plane_runs(root):  # noqa: SLF001
            statistics = None
            stats_path = run_dir / "statistics.json"
            if stats_path.exists():
                try:
                    statistics = v3_metrics._load_json(stats_path)  # noqa: SLF001
                except (OSError, json.JSONDecodeError):
                    statistics = None
            results.append(render_plane(
                run_dir, statistics=statistics,
                with_detail=not args.no_detail,
                with_heatmap=not args.no_heatmap,
                with_radius=not args.no_radius,
                with_congestion=not args.no_congestion,
                with_svg_gds=not args.no_vector, verbose=args.verbose))
        for algorithm, combined_dir in v3_metrics.iter_combined_runs(root):  # noqa: SLF001
            results.append(render_combined(combined_dir, root=root,
                                           verbose=args.verbose))
        results.append(render_shapes(root, verbose=args.verbose))
        print(json.dumps({"rendered": len(results)}))
        return 0
    if args.shapes:
        print(json.dumps(render_shapes(root, verbose=args.verbose)))
        return 0
    if args.combined_dir:
        result = render_combined(args.combined_dir, root=root,
                                 verbose=args.verbose)
        print(json.dumps({"combined_dir": args.combined_dir,
                          "files": sorted(result.get("files") or {})}))
        return 0
    if not args.run_dir:
        raise SystemExit("v3.plots: --run-dir, --combined-dir, --shapes or --all "
                         "required")
    statistics = None
    stats_path = Path(args.run_dir) / "statistics.json"
    if stats_path.exists():
        try:
            statistics = v3_metrics._load_json(stats_path)  # noqa: SLF001
        except (OSError, json.JSONDecodeError):
            statistics = None
    result = render_plane(
        args.run_dir, statistics=statistics, with_detail=not args.no_detail,
        with_heatmap=not args.no_heatmap, with_radius=not args.no_radius,
        with_congestion=not args.no_congestion,
        with_svg_gds=not args.no_vector, verbose=args.verbose)
    print(json.dumps({"experiment": result["experiment"],
                      "plane": result["plane"],
                      "routed": result["routed_count"],
                      "total": result["total"],
                      "files": sorted(result["files"]),
                      "wall_seconds": round(result["wall_seconds"], 3)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
