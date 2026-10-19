"""FSLW R=40 mm / 30 µm dual-height figures (SPEC §10).

Round-2 deliverable.  Every full-board figure of every plane and every combined
layout uses the **same** coordinate limits ``[-9, 159]^2`` (150 mm board plus the
connector-label pad), the same 200 dpi, the same figure size and the same
side-pair palette (``four_side_1024.outputs.COLORS``), so the sixteen plane runs
and eight combined layouts are directly comparable by eye.  Palette and framing
are reused from the read-only ``d56/plots_d56.py`` module by import.

Per-plane figures (written into ``planes/<TOPOLOGY>/<ALGO>/<PLANE>/``):
``routing_all.png`` (title states the real routed/512 and the plane z1/z2),
``routing_detail.png``, ``routing_all.svg`` + ``routing_all.gds`` (via the
round-1 exporter, single layer 0), ``crossing_heatmap.png``,
``radius_check.png`` and ``congestion_zoom.png``.

Combined figures (written by ``fslw/combine.py`` into
``combined/<TOPOLOGY>/<ALGO>/``): ``layer_2d.png``/``.svg`` (the two heights
side by side, identical scale), ``overlay_3d.png`` (height-distinguished 3D
view; cross-plane XY projections are explicitly not conflicts).

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.fslw.plots --run-dir \\
        outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V1/B/z1
    .venv\\Scripts\\python.exe -m four_side_1024.fslw.plots --root \\
        outputs/four_side_1024_fslw_R40_gap30_abcd --all
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np

from ..d56.plots_d56 import (BOARD_MM, DPI, PAIR_ORDER, _board_frame,
                             draw_connectors, plot_detail, plot_routes,
                             pyplot, sample_curves)
from ..outputs import COLORS
from . import config as fslw_config
from . import metrics as fslw_metrics

SCHEMA = "four_side_1024_fslw_plots_v1"
TOOL = "four_side_1024.fslw.plots"
PLANE_TOTAL = 512
COMBINED_TOTAL = 1024
DISPLAY_SAGITTA_MM = 0.005
PAIR_LEGEND_FONTSIZE = 7.0
PLANE_COLORS = {"z1": "#1f4e9e", "z2": "#c0392b"}
PLANE_LABELS = {"z1": "z1 (row 1, opposite, z=0.0)",
                "z2": "z2 (row 2, adjacent, z=0.5)"}
DETAIL_HOTSPOTS = 4
DETAIL_HALF_MM = 12.5
CONGESTION_HALF_MM = 12.5


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------
def _experiment_label(process, run_dir, plane):
    experiment = str(process.get("experiment") or run_dir.name)
    if plane and plane in experiment.split("_"):
        return experiment
    return f"{experiment}_{plane}" if plane else experiment


def load_plane(run_dir, statistics=None):
    """Load one plane's routed records, display curves, connectors and stats."""
    run_dir = Path(run_dir)
    routes_path = run_dir / "routes.json"
    if not routes_path.exists():
        raise FileNotFoundError(f"no routes.json under {run_dir}")
    payload, meta, records, routed, failed = fslw_metrics.load_routes(routes_path)
    config_path = run_dir / "config.json"
    config_payload = (fslw_metrics._load_json(config_path)  # noqa: SLF001
                      if config_path.exists() else None)
    process = fslw_metrics.load_process(meta, config_payload, run_dir)
    plane = process.get("plane")
    if plane is None:
        for record in records:
            plane = record.get("plane")
            if plane:
                break
    plane = fslw_metrics._normalise_plane(plane)  # noqa: SLF001
    process["plane"] = plane
    topology = process.get("topology")
    port_bundle = (fslw_metrics.load_plane_ports(topology, plane, process)
                   if topology else None)
    endpoints = (port_bundle or {}).get("endpoints")
    if not endpoints:
        endpoints = fslw_metrics._derive_endpoints(routed, process)  # noqa: SLF001
    connectors = (port_bundle or {}).get("connectors") or []
    curves = sample_curves(routed, DISPLAY_SAGITTA_MM)
    display_meta = {}
    for record in routed:
        display_meta[record["route_id"]] = {
            "pair": record.get("pair") or fslw_metrics._pair_of(record),  # noqa: SLF001
        }
    if statistics is None:
        statistics_path = run_dir / "statistics.json"
        if statistics_path.exists():
            try:
                statistics = fslw_metrics._load_json(statistics_path)  # noqa: SLF001
            except (OSError, json.JSONDecodeError):
                statistics = None
    return {
        "run_dir": run_dir,
        "routes_path": routes_path,
        "config_path": config_path if config_path.exists() else None,
        "payload": payload,
        "meta": meta,
        "records": records,
        "routed": routed,
        "failed": failed,
        "process": process,
        "plane": plane,
        "topology": topology,
        "algorithm": process.get("algorithm"),
        "experiment": _experiment_label(process, run_dir, plane),
        "endpoints": endpoints,
        "connectors": connectors,
        "curves": curves,
        "meta_routes": display_meta,
        "statistics": statistics,
    }


def _crossings_x_mm(audit_or_statistics):
    """Crossing points with ``x_mm``/``y_mm`` keys for the d56 detail helper."""
    if not audit_or_statistics:
        return [], []
    crossings = []
    for item in audit_or_statistics.get("crossings") or []:
        x = item.get("x", item.get("x_mm"))
        y = item.get("y", item.get("y_mm"))
        if x is None or y is None:
            continue
        crossings.append({"x_mm": float(x), "y_mm": float(y),
                          "angle_deg": item.get("angle_deg"),
                          "route_a": item.get("route_a"),
                          "route_b": item.get("route_b")})
    densest = audit_or_statistics.get("densest_crossing_cells") or []
    return crossings, densest


def _plane_title_lines(data):
    statistics = data.get("statistics") or {}
    routed = len(data["routed"])
    rate = routed / PLANE_TOTAL
    plane = data.get("plane") or "?"
    process = data.get("process") or {}
    first = (f"{data['experiment']} | plane {plane} | "
             f"{routed}/{PLANE_TOTAL} routed ({rate:.2%})")
    crossings = statistics.get("crossing_count")
    mean_length = statistics.get("mean_length_mm")
    loss = (statistics.get("propagation_loss") or {}).get("mean_db")
    line_topology = (
        f"topology {data.get('topology')} | algorithm {data.get('algorithm')} | "
        f"150 x 150 mm | single 2D plane (layer 0)")
    line_process = (
        f"R={float(process.get('radius_mm') or fslw_config.RADIUS_MM):g} mm fixed | "
        f"width {float(process.get('width_mm') or fslw_config.WIDTH_MM):g} mm | "
        f"edge gap {float(process.get('edge_gap_mm') or fslw_config.EDGE_GAP_MM):g} mm | "
        f"clearance {float(process.get('clearance_mm') or fslw_config.CLEARANCE_MM):g} mm")
    line_metrics = []
    if crossings is not None:
        line_metrics.append(f"same-plane crossings {int(crossings)}")
    if mean_length is not None:
        line_metrics.append(f"mean length {float(mean_length):.2f} mm")
    if loss is not None:
        line_metrics.append(f"mean propagation loss {float(loss):.3f} dB")
    line_metrics.append("bend/crossing loss unknown_uncalibrated")
    subtitle = "\n".join([line_topology, line_process, " | ".join(line_metrics)])
    return first, subtitle


# ---------------------------------------------------------------------------
# per-plane figures
# ---------------------------------------------------------------------------
def render_routing_all(data, output_path):
    title, subtitle = _plane_title_lines(data)
    info = plot_routes(data["curves"], data["meta_routes"],
                       list(data["curves"].keys()), data["connectors"],
                       output_path, title, subtitle)
    info.update({"kind": "routing_all", "plane": data["plane"],
                 "routed_count": len(data["routed"]), "total": PLANE_TOTAL,
                 "experiment": data["experiment"]})
    return info


def _plane_crossings(data):
    """Crossing list for figures, recomputed at most once per plane run."""
    if data.get("_crossings") is not None:
        return data["_crossings"], data.get("_densest") or []
    statistics = data.get("statistics") or {}
    crossings, densest = _crossings_x_mm(statistics)
    if len(crossings) < int(statistics.get("crossing_count") or 0):
        audit = fslw_metrics.compute_pair_audit(data["routed"], data["process"])
        crossings, densest = _crossings_x_mm(audit)
        data["_pair_audit"] = audit
    data["_crossings"] = crossings
    data["_densest"] = densest
    return crossings, densest


def render_routing_detail(data, output_path):
    crossings, densest = _plane_crossings(data)
    if not crossings:
        return None
    routed = len(data["routed"])
    info = plot_detail(data["curves"], data["meta_routes"], crossings,
                       output_path, routed, PLANE_TOTAL, densest,
                       count=DETAIL_HOTSPOTS, half_mm=DETAIL_HALF_MM)
    info.update({"kind": "routing_detail", "plane": data["plane"],
                 "routed_count": routed, "total": PLANE_TOTAL,
                 "crossing_count": len(crossings)})
    return info


def render_crossing_heatmap(data, output_path):
    plt = pyplot()
    from matplotlib.patches import Rectangle
    crossings, densest = _plane_crossings(data)
    routed = len(data["routed"])
    cells = int(round(BOARD_MM / fslw_metrics.GRID_MM))
    counts = np.zeros((cells, cells), dtype=int)
    for crossing in crossings:
        ix = int(math.floor(crossing["x_mm"] / fslw_metrics.GRID_MM))
        iy = int(math.floor(crossing["y_mm"] / fslw_metrics.GRID_MM))
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
            densest.append({"x_min_mm": int(ix) * fslw_metrics.GRID_MM,
                            "y_min_mm": int(iy) * fslw_metrics.GRID_MM,
                            "count": int(counts[iy, ix])})
    for rank, cell in enumerate(densest[:3], start=1):
        x0, y0 = cell.get("x_min_mm"), cell.get("y_min_mm")
        count = cell.get("count", cell.get("projected_crossings"))
        if x0 is None or y0 is None:
            continue
        ax.add_patch(Rectangle((x0, y0), fslw_metrics.GRID_MM,
                               fslw_metrics.GRID_MM, fill=False,
                               edgecolor="#7CFC00", linewidth=1.4, zorder=4))
        ax.annotate(f"{count} ({int(x0)},{int(y0)})",
                    xy=(x0 + fslw_metrics.GRID_MM / 2.0,
                        y0 + fslw_metrics.GRID_MM / 2.0),
                    ha="center", va="center", fontsize=7, color="white",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#111111",
                              alpha=0.75), zorder=5)
    _board_frame(ax)
    ax.set_title(
        f"{data['experiment']} plane {data['plane']} crossing heatmap | "
        f"{len(crossings)} same-plane crossings | {routed}/{PLANE_TOTAL} routed\n"
        f"crossings are legal 2D crossings counted inside this plane; different "
        f"heights are never compared", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "crossing_heatmap",
            "plane": data["plane"], "crossings": len(crossings),
            "routed_count": routed}


def render_radius_check(data, output_path):
    plt = pyplot()
    process = data["process"]
    radius_target = float(process.get("radius_mm") or fslw_config.RADIUS_MM)
    tolerance = 1e-9
    values = Counter()
    violations = []
    arcs = 0
    for record in data["routed"]:
        for primitive in record.get("primitives") or []:
            if primitive.get("kind") != "arc":
                continue
            arcs += 1
            radius = fslw_metrics._number(primitive.get("radius"))  # noqa: SLF001
            values[fslw_metrics._round(radius, 9)] += 1  # noqa: SLF001
            if radius is None or abs(radius - radius_target) > tolerance:
                violations.append({"route_id": record.get("route_id"),
                                   "radius": radius})
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.2))
    ax = axes[0]
    numeric_values = sorted(value for value in values if value is not None)
    has_none = any(value is None for value in values)
    x_positions = list(numeric_values) + ([radius_target + 1.0] if has_none else [])
    heights = [values[value] for value in numeric_values]
    if has_none:
        heights.append(values[None])
    span = (max(x_positions) - min(x_positions)) if len(x_positions) > 1 else 0.0
    width = max(0.05, span * 0.05) if span > 0 else 0.4
    ax.bar(x_positions, heights, width=width, color="#3366bb",
           edgecolor="#222222", linewidth=0.4)
    if span <= 0:
        ax.set_xlim(radius_target - 1.0, radius_target + 1.0)
    ax.axvline(radius_target, color="#b84040", linewidth=1.0, linestyle="--",
               label=f"required R={radius_target:g} mm")
    ax.set_xlabel("arc radius (mm)")
    ax.set_ylabel("arc count")
    ax.grid(True, axis="y", alpha=0.3, linewidth=0.5)
    ax.legend(fontsize=8.0, loc="upper right")
    ax.set_title(f"arc radius values | {arcs} arcs checked", fontsize=9.5)
    ax = axes[1]
    ax.axis("off")
    ok = arcs - len(violations)
    lines = [
        f"required radius: R = {radius_target:g} mm (fixed_radius_40mm=on)",
        f"tolerance: {tolerance:g} mm",
        f"arcs checked: {arcs}",
        f"arcs at R={radius_target:g}: {ok}",
        f"radius violations: {len(violations)}",
        "",
        f"plane {data['plane']}: {data['experiment']}",
        f"routed {len(data['routed'])}/{PLANE_TOTAL}",
    ]
    if violations:
        lines.append("")
        lines.append("first violations:")
        for item in violations[:8]:
            lines.append(f"  route {item['route_id']}: r={item['radius']}")
    ax.text(0.02, 0.98, "\n".join(lines), ha="left", va="top", fontsize=9.0,
            family="monospace")
    ax.set_title(f"R = {radius_target:g} mm fixed-radius check", fontsize=9.5)
    fig.suptitle(
        f"{data['experiment']} plane {data['plane']} radius verification | "
        f"all arcs must be exactly R={radius_target:g} mm", fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "radius_check",
            "arcs_checked": arcs, "radius_violations": len(violations),
            "radius_values": {str(key): count for key, count in values.items()}}


def render_congestion_zoom(data, output_path):
    """Local route-length density hotspots (5 mm grid) with zoomed panels."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    curves = data["curves"]
    meta = data["meta_routes"]
    cells = fslw_metrics.GRID_MM
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
        cx = (ix + 0.5) * cells
        cy = (iy + 0.5) * cells
        windows.append((cx, cy, float(density[ix, iy])))
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 12.4), squeeze=False)
    for index, (cx, cy, peak) in enumerate(windows):
        ax = axes[index // 2][index % 2]
        x_lo = max(-4.0, cx - CONGESTION_HALF_MM)
        x_hi = min(BOARD_MM + 4.0, cx + CONGESTION_HALF_MM)
        y_lo = max(-4.0, cy - CONGESTION_HALF_MM)
        y_hi = min(BOARD_MM + 4.0, cy + CONGESTION_HALF_MM)
        sub = density[max(0, int((x_lo) / cells)):int(math.ceil(x_hi / cells)),
                      max(0, int((y_lo) / cells)):int(math.ceil(y_hi / cells))]
        if sub.size:
            ax.imshow(sub.T, origin="lower", cmap="YlOrRd", alpha=0.55,
                      extent=(x_lo, x_hi, y_lo, y_hi), interpolation="nearest",
                      aspect="auto")
        ids = [route_id for route_id, points in curves.items()
               if points[:, 0].max() >= x_lo and points[:, 0].min() <= x_hi
               and points[:, 1].max() >= y_lo and points[:, 1].min() <= y_hi]
        segments = [curves[route_id] for route_id in ids]
        colours = [COLORS[meta[route_id]["pair"]] for route_id in ids]
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
        f"{data['experiment']} plane {data['plane']} local congestion | "
        f"{len(data['routed'])}/{PLANE_TOTAL} routed | 5 x 5 mm route-length "
        f"density | max plane crossing-free metric", fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "congestion_zoom",
            "hotspots": [[round(w[0], 3), round(w[1], 3), round(w[2], 3)]
                         for w in windows]}


def _write_svg_and_gds(data):
    """Reuse the round-1 exporter: single layer 0 GDS + <5 MB SVG.

    gdspy>=1.6 registers new cells in the *global* ``gdspy.current_library`` and
    the d56 exporter uses a fixed cell name, so repeated exports inside one
    process (``--all``) need an isolated throwaway current library.
    """
    from ..abcd import export as abcd_export
    import gdspy
    previous = gdspy.current_library
    gdspy.current_library = gdspy.GdsLibrary(name="fslw_scratch_library")
    try:
        summary = abcd_export.export_run(
            routes_path=data["routes_path"], config_path=data["config_path"],
            run_dir=data["run_dir"])
    finally:
        gdspy.current_library = previous
    return {"gds": summary.get("gds"), "svg": summary.get("svg"),
            "verification": summary.get("verification")}


def render_plane(run_dir, statistics=None, with_detail=True,
                 with_heatmap=True, with_radius=True, with_congestion=True,
                 with_svg_gds=True, verbose=False):
    """Render every per-plane figure / vector artefact for one plane run."""
    started = time.perf_counter()
    data = load_plane(run_dir, statistics=statistics)
    run_dir = data["run_dir"]
    files = {}
    files["routing_all_png"] = render_routing_all(
        data, run_dir / "routing_all.png")
    if verbose:
        print(f"[fslw.plots] {run_dir / 'routing_all.png'}")
    if with_detail:
        detail = render_routing_detail(data, run_dir / "routing_detail.png")
        if detail:
            files["routing_detail_png"] = detail
    if with_heatmap:
        files["crossing_heatmap_png"] = render_crossing_heatmap(
            data, run_dir / "crossing_heatmap.png")
    if with_radius:
        files["radius_check_png"] = render_radius_check(
            data, run_dir / "radius_check.png")
    if with_congestion:
        files["congestion_zoom_png"] = render_congestion_zoom(
            data, run_dir / "congestion_zoom.png")
    if with_svg_gds:
        try:
            vector = _write_svg_and_gds(data)
            files["routing_all_gds"] = vector.get("gds")
            files["routing_all_svg"] = vector.get("svg")
            if verbose:
                print(f"[fslw.plots] {run_dir / 'routing_all.gds'} + .svg")
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            files["vector_error"] = f"{type(exc).__name__}: {exc}"
    summary = {
        "schema": SCHEMA,
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scope": "plane",
        "experiment": data["experiment"],
        "topology": data["topology"],
        "algorithm": data["algorithm"],
        "plane": data["plane"],
        "routed_count": len(data["routed"]),
        "total": PLANE_TOTAL,
        "run_dir": str(run_dir),
        "style": {
            "board_mm": BOARD_MM,
            "display_sagitta_mm": DISPLAY_SAGITTA_MM,
            "dpi": DPI,
            "figsize_routing": [11.0, 10.0],
            "coordinate_limits": [-9.0, BOARD_MM + 9.0],
            "palette": "four_side_1024.outputs.COLORS (fixed by side pair)",
            "linewidth": "d56 default policy (0.4 - 0.55)",
        },
        "files": files,
        "wall_seconds": time.perf_counter() - started,
    }
    return fslw_metrics._json_safe(summary)  # noqa: SLF001


# ---------------------------------------------------------------------------
# combined figures (layer_2d / overlay_3d)
# ---------------------------------------------------------------------------
def load_combined(combined_dir, root=None):
    """Load both plane displays for a combined layout."""
    combined_dir = Path(combined_dir)
    if root is None:
        root = combined_dir.parent.parent
    root = Path(root)
    topology = combined_dir.parent.name
    algorithm = combined_dir.name
    planes = {}
    for plane in ("z1", "z2"):
        run_dir = fslw_metrics._plane_run_dir(root, topology, algorithm, plane)  # noqa: SLF001
        if not (run_dir / "routes.json").exists():
            planes[plane] = None
            continue
        planes[plane] = load_plane(run_dir)
    statistics_path = combined_dir / "statistics.json"
    statistics = None
    if statistics_path.exists():
        try:
            statistics = fslw_metrics._load_json(statistics_path)  # noqa: SLF001
        except (OSError, json.JSONDecodeError):
            statistics = None
    return {"combined_dir": combined_dir, "root": root, "topology": topology,
            "algorithm": algorithm, "planes": planes, "statistics": statistics}


def _combined_counts(loaded):
    routed = 0
    per_plane = {}
    for plane in ("z1", "z2"):
        data = loaded["planes"].get(plane)
        count = len(data["routed"]) if data else 0
        per_plane[plane] = count
        routed += count
    return routed, per_plane


def render_layer_2d(loaded, png_path, svg_path=None):
    """Two panels (z1, z2) side by side, identical axes/palette/linewidth."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    topology = loaded["topology"]
    algorithm = loaded["algorithm"]
    routed, per_plane = _combined_counts(loaded)
    fig, axes = plt.subplots(1, 2, figsize=(19.0, 9.2))
    for ax, plane in zip(axes, ("z1", "z2")):
        data = loaded["planes"].get(plane)
        if not data or not data["curves"]:
            ax.axis("off")
            ax.set_title(f"{topology}_{algorithm} plane {plane}\nmissing plane run",
                         fontsize=10.0, color="#888888")
            continue
        route_ids = [route_id for route_id in data["curves"]
                     if len(data["curves"][route_id]) >= 2]
        segments = [data["curves"][route_id] for route_id in route_ids]
        colours = [COLORS[data["meta_routes"][route_id]["pair"]]
                   for route_id in route_ids]
        if segments:
            ax.add_collection(LineCollection(segments, colors=colours,
                                             linewidths=0.34, alpha=0.82,
                                             zorder=3))
        _board_frame(ax)
        draw_connectors(ax, data.get("connectors") or [], depth_mm=3.0,
                        label_fontsize=3.4)
        statistics = data.get("statistics") or {}
        crossings = statistics.get("crossing_count")
        loss = (statistics.get("propagation_loss") or {}).get("mean_db")
        lines = [f"plane {plane}: {per_plane[plane]}/{PLANE_TOTAL} routed "
                 f"({per_plane[plane] / PLANE_TOTAL:.2%})",
                 PLANE_LABELS[plane]]
        if crossings is not None:
            lines.append(f"same-plane crossings {int(crossings)}")
        if loss is not None:
            lines.append(f"mean propagation loss {float(loss):.3f} dB")
        ax.set_title("\n".join(lines), fontsize=9.0)
        ax.tick_params(labelsize=6.5)
    handles = [Line2D([0], [0], color=COLORS[pair], linewidth=2.0, label=pair)
               for pair in PAIR_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=len(PAIR_ORDER),
               fontsize=8.0, framealpha=0.9)
    fig.suptitle(
        f"{topology}_{algorithm} dual-height layout (2D layers) | "
        f"{routed}/{COMBINED_TOTAL} routed combined | identical axes "
        f"[-9,159]^2 / linewidth / palette | z1=row1 plane (z=0.0), "
        f"z2=row2 plane (z=0.5); the two heights are independent 2D problems",
        fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.035, 1.0, 0.95))
    fig.savefig(png_path, dpi=DPI)
    if svg_path is not None:
        fig.savefig(svg_path)
    plt.close(fig)
    return {"file": str(png_path), "svg": str(svg_path) if svg_path else None,
            "kind": "layer_2d", "routed": routed, "per_plane": per_plane}


def render_overlay_3d(loaded, png_path):
    """3D overlay: z1 at 0.0, z2 at 0.5 model units; projections not conflicts."""
    plt = pyplot()
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    topology = loaded["topology"]
    algorithm = loaded["algorithm"]
    routed, per_plane = _combined_counts(loaded)
    fig = plt.figure(figsize=(14.0, 11.0))
    ax = fig.add_subplot(111, projection="3d")
    z_heights = {"z1": 0.0, "z2": 0.5}
    for plane in ("z1", "z2"):
        data = loaded["planes"].get(plane)
        if not data:
            continue
        z = z_heights[plane]
        segments = []
        colours = []
        for route_id, points in data["curves"].items():
            if len(points) < 2:
                continue
            for first, second in zip(points[:-1], points[1:]):
                segments.append([(float(first[0]), float(first[1]), z),
                                 (float(second[0]), float(second[1]), z)])
                colours.append(COLORS[data["meta_routes"][route_id]["pair"]])
        if segments:
            collection = Line3DCollection(segments, colors=colours,
                                          linewidths=0.45, alpha=0.75)
            ax.add_collection3d(collection)
    # board outlines at both model heights
    for z, colour in ((0.0, "#1f4e9e"), (0.5, "#c0392b")):
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
        f"{topology}_{algorithm} dual-height 3D overlay | "
        f"{routed}/{COMBINED_TOTAL} routed combined "
        f"(z1 {per_plane['z1']}/{PLANE_TOTAL}, z2 {per_plane['z2']}/{PLANE_TOTAL})\n"
        f"z1 = row-1 plane at 0.0 (blue), z2 = row-2 plane at 0.5 (red); vertical "
        f"scale exaggerated for display; cross-plane XY projections are NOT "
        f"conflicts (different glass heights, SPEC §2)",
        fontsize=9.0)
    fig.tight_layout()
    fig.savefig(png_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(png_path), "kind": "overlay_3d", "routed": routed,
            "per_plane": per_plane,
            "z_model": {"z1": 0.0, "z2": 0.5,
                        "z2_minus_z1_mm": 0.5,
                        "note": "vertical scale exaggerated for display"}}


def render_combined(combined_dir, root=None, verbose=False):
    """Render layer_2d.png/.svg + overlay_3d.png for one combined layout."""
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
        "topology": loaded["topology"],
        "algorithm": loaded["algorithm"],
        "routed": files["layer_2d_png"]["routed"],
        "total": COMBINED_TOTAL,
        "files": files,
        "wall_seconds": time.perf_counter() - started,
    }
    if verbose:
        print(f"[fslw.plots] {combined_dir / 'layer_2d.png'} + overlay_3d.png")
    return fslw_metrics._json_safe(summary)  # noqa: SLF001


# ---------------------------------------------------------------------------
# cross-run comparison figures (called by fslw/compare.py)
# ---------------------------------------------------------------------------
def render_eight_group_comparison(root, output_path):
    """Eight combined layouts: routed count per plane and combined (honest scale)."""
    plt = pyplot()
    rows = []
    for topology, algorithm, combined_dir in fslw_metrics.iter_combined_runs(root):  # noqa: SLF001
        loaded = load_combined(combined_dir, root=root)
        routed, per_plane = _combined_counts(loaded)
        rows.append({"label": f"{topology}_{algorithm}", "topology": topology,
                     "algorithm": algorithm, "z1": per_plane["z1"],
                     "z2": per_plane["z2"], "combined": routed})
    if not rows:
        return None
    labels = [row["label"] for row in rows]
    positions = np.arange(len(labels))
    width = 0.27
    fig, ax = plt.subplots(figsize=(13.0, 5.2))
    for offset, key, colour, name in (
            (-width, "z1", PLANE_COLORS["z1"], "z1 plane (opposite) /512"),
            (0.0, "z2", PLANE_COLORS["z2"], "z2 plane (adjacent) /512"),
            (width, "combined", "#555555", "combined /1024 (sum of planes)")):
        values = [row[key] for row in rows]
        bars = ax.bar(positions + offset, values, width=width, color=colour,
                      edgecolor="#222222", linewidth=0.4, label=name)
        for position, value in zip(positions + offset, values):
            ax.text(position, value, f"{value}", ha="center", va="bottom",
                    fontsize=6.5, rotation=90)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=0 if len(labels) <= 6 else 30,
                       ha="center" if len(labels) <= 6 else "right", fontsize=8.0)
    ax.set_ylim(0.0, max(COMBINED_TOTAL, max(
        row["combined"] for row in rows)) * 1.18)
    ax.axhline(COMBINED_TOTAL, color="#333333", linewidth=0.8, linestyle="--",
               label="1024 connections")
    ax.legend(fontsize=7.5, loc="upper right")
    ax.set_ylabel("routed connections", fontsize=8.5)
    ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    ax.set_title(
        "Eight combined FSLW layouts: real routed counts at R=40 mm / 30 µm gap\n"
        "z1 and z2 are independent 512-connection 2D problems at two heights; "
        "combined = z1 + z2, no rescaling", fontsize=10.0)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "eight_group_comparison",
            "rows": rows}


def render_sensitivity_comparison(root, output_path):
    """Phase-11 sensitivity matrix O/G/R/N: routed rate per plane and combined."""
    plt = pyplot()
    configurations = [dict(item) for item in fslw_config.SENSITIVITY_CONFIGS]
    rows = []
    for config in configurations:
        name = config["name"]
        edge_gap = _number_or_none(config.get("edge_gap_mm")) or 0.0
        record = {"config": name,
                  "radius_mm": _number_or_none(config.get("radius_mm")),
                  "edge_gap_mm": edge_gap,
                  "clearance_mm": edge_gap + float(getattr(fslw_config,
                                                           "WIDTH_MM", 0.05))}
        for topology, algorithm, plane, run_dir in _sensitivity_runs(root, name):
            if topology == "V1" and algorithm == "B":
                routed = len(fslw_metrics.load_routes(  # noqa: SLF001
                    run_dir / "routes.json")[3])
                record[plane] = routed
        rows.append(record)
    if not any(row.get("z1") is not None or row.get("z2") is not None
               for row in rows):
        return None
    labels = [row["config"] for row in rows]
    positions = np.arange(len(labels))
    width = 0.27
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 5.2))
    ax = axes[0]
    for offset, key, colour, name in (
            (-width, "z1", PLANE_COLORS["z1"], "z1 /512"),
            (0.0, "z2", PLANE_COLORS["z2"], "z2 /512"),
            (width, "combined", "#555555", "combined /1024")):
        values = []
        for row in rows:
            z1 = row.get("z1") or 0
            z2 = row.get("z2") or 0
            if key == "combined":
                values.append(z1 + z2)
            else:
                values.append(row.get(key) or 0)
        ax.bar(positions + offset, values, width=width, color=colour,
               edgecolor="#222222", linewidth=0.4, label=name)
        for position, value in zip(positions + offset, values):
            if value:
                ax.text(position, value, f"{value}", ha="center", va="bottom",
                        fontsize=6.0, rotation=90)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=7.5)
    ax.set_ylabel("routed connections", fontsize=8.5)
    ax.legend(fontsize=7.5, loc="upper right")
    ax.grid(True, axis="y", alpha=0.28, linewidth=0.5)
    ax.set_title("sensitivity: routed counts (V1+B, both planes)", fontsize=9.5)
    ax = axes[1]
    ax.axis("off")
    lines = ["Phase-11 sensitivity matrix (V1 + algorithm B)",
             "",
             f"{'config':<18}{'R(mm)':>8}{'gap(um)':>9}{'clearance':>11}"
             f"{'z1':>6}{'z2':>6}{'combined':>10}"]
    for row in rows:
        z1 = row.get("z1")
        z2 = row.get("z2")
        combined = (z1 or 0) + (z2 or 0) if (z1 is not None
                                             or z2 is not None) else None
        radius = row.get("radius_mm")
        lines.append(
            f"{row['config']:<18}"
            f"{(radius if radius is not None else 0):>8g}"
            f"{(1000 * (row.get('edge_gap_mm') or 0)):>9.0f}"
            f"{(row.get('clearance_mm') or 0):>11.3f}"
            f"{(z1 if z1 is not None else '-'):>6}"
            f"{(z2 if z2 is not None else '-'):>6}"
            f"{(combined if combined is not None else '-'):>10}")
    lines.extend(["", "All four configurations are run in the SAME dual-height",
                  "plane model; the previous-round single-layer virtual-",
                  "unfolded numbers are not a valid baseline (SPEC §7)."])
    ax.text(0.0, 1.0, "\n".join(lines), ha="left", va="top", fontsize=8.5,
            family="monospace")
    ax.set_title("sensitivity matrix table", fontsize=9.5)
    fig.suptitle("FSLW parameter sensitivity O (R5/gap125) vs G (R5/gap30) vs "
                 "R (R40/gap125) vs N (R40/gap30)", fontsize=11.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return {"file": str(output_path), "kind": "sensitivity_comparison",
            "configurations": [row["config"] for row in rows]}


def _sensitivity_runs(root, config_name):
    for entry in fslw_metrics.iter_sensitivity_runs(root):  # noqa: SLF001
        if entry[0] == config_name:
            yield entry[1], entry[2], entry[3], entry[4]


def _number_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser():
    parser = argparse.ArgumentParser(
        description="Render FSLW per-plane and combined figures (SPEC §10).")
    parser.add_argument("--run-dir", help="plane run dir")
    parser.add_argument("--combined-dir", help="combined/<TOPOLOGY>/<ALGO> dir")
    parser.add_argument("--root", help="outputs root (for --all / combined)")
    parser.add_argument("--all", action="store_true",
                        help="render every existing plane and combined run")
    parser.add_argument("--no-detail", action="store_true")
    parser.add_argument("--no-heatmap", action="store_true")
    parser.add_argument("--no-radius", action="store_true")
    parser.add_argument("--no-congestion", action="store_true")
    parser.add_argument("--no-vector", action="store_true",
                        help="skip routing_all.svg/.gds")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    root = Path(args.root) if args.root else None
    results = []
    if args.all:
        if root is None:
            root = Path("outputs/four_side_1024_fslw_R40_gap30_abcd")
        for topology, algorithm, plane, run_dir in fslw_metrics.iter_plane_runs(root):  # noqa: SLF001
            stats = run_dir / "statistics.json"
            statistics = fslw_metrics._load_json(stats) if stats.exists() else None  # noqa: SLF001
            results.append(render_plane(
                run_dir, statistics=statistics,
                with_detail=not args.no_detail,
                with_heatmap=not args.no_heatmap,
                with_radius=not args.no_radius,
                with_congestion=not args.no_congestion,
                with_svg_gds=not args.no_vector, verbose=args.verbose))
        for topology, algorithm, combined_dir in fslw_metrics.iter_combined_runs(root):  # noqa: SLF001
            results.append(render_combined(combined_dir, root=root,
                                           verbose=args.verbose))
        print(json.dumps({"rendered": len(results),
                          "planes": sum(1 for item in results
                                        if item.get("scope") == "plane"),
                          "combined": sum(1 for item in results
                                          if item.get("scope") == "combined")}))
        return 0
    if args.combined_dir:
        if root is None:
            root = Path(args.combined_dir).parent.parent
        result = render_combined(args.combined_dir, root=root,
                                 verbose=args.verbose)
        print(json.dumps({"combined_dir": args.combined_dir,
                          "files": sorted(result.get("files") or {})}))
        return 0
    if not args.run_dir:
        raise SystemExit("fslw.plots: --run-dir, --combined-dir or --all required")
    stats_path = Path(args.run_dir) / "statistics.json"
    statistics = fslw_metrics._load_json(stats_path) if stats_path.exists() else None  # noqa: SLF001
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
