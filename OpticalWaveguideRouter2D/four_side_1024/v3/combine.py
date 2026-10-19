"""Build the V3-Huang 1024-channel combined (dual-height) artefacts.

Round-3 deliverable for ``four_side_1024/v3/SPEC.md`` §7.  A combined layout is
the pair of independent 2D plane solutions:

* plane **z1** = CSV row 1 (512 connections; same 222 / opposite 196 /
  adjacent 94 at model height 0.0);
* plane **z2** = CSV row 2 (512 connections; same 226 / opposite 188 /
  adjacent 98 at model height 0.5).

Outputs for ``combined/<A>/``:

* ``routes_1024.json`` -- all 1024 identities with plane/z tags, per-plane
  summaries and per-plane + combined statistics;
* ``statistics.json`` -- combined metrics (same-plane crossings kept apart from
  the informational ``cross_plane_projected_overlap``);
* ``planes_summary.json`` -- compact per-plane table + GDS layer documentation;
* ``layer_2d.png``/``.svg`` -- the two planes side by side, identical scale;
* ``overlay_3d.png`` -- height-distinguished 3D view;
* ``routing_1024_two_height.gds`` -- layer 0 = plane z1, layer 1 = plane z2
  (two physical heights of the same single-layer process, NOT a layer stack).

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.v3.combine --root <root> --all
    .venv\\Scripts\\python.exe -m four_side_1024.v3.combine --root <root> \\
        --algorithm B
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from ..fslw.combine import _ensure_plane_vectors, write_combined_gds
from . import config as v3_config
from . import metrics as v3_metrics
from . import plots as v3_plots

SCHEMA = "four_side_1024_v3_combined_routes_v1"
TOOL = "four_side_1024.v3.combine"
PLANE_TOTAL = 512
TOTAL_CONNECTIONS = 1024
PLANE_LAYER = {"z1": 0, "z2": 1}
GDS_TWO_HEIGHT_NOTE = (
    "routing_1024_two_height.gds: layer 0 = plane z1 (row 1, model height 0.0), "
    "layer 1 = plane z2 (row 2, model height 0.5). The two GDS layers represent "
    "two PHYSICAL HEIGHTS of the same single-layer process; they are NOT a "
    "multi-layer waveguide stack, and no z-transition/via/fanout is implemented. "
    "Cross-plane XY projections are not conflicts (SPEC §2).")


def _ensure_plane_statistics(plane_dir, quiet=True):
    statistics_path = plane_dir / "statistics.json"
    if statistics_path.exists():
        try:
            return v3_metrics._load_json(statistics_path)  # noqa: SLF001
        except (OSError, json.JSONDecodeError):
            pass
    return v3_metrics.build_plane_statistics(plane_dir, quiet=quiet)


def _combined_routes_payload(algorithm, plane_context):
    routes = []
    plane_blocks = {}
    for plane in v3_metrics.PLANES:
        context = plane_context[plane]
        statistics = context["statistics"]
        plane_blocks[plane] = {
            "plane": plane,
            "z_mm": (statistics or {}).get("z_mm"),
            "row": (statistics or {}).get("plane_row"),
            "routes_json": str(context["routes_path"]),
            "routed": len(context["routed"]),
            "unrouted": len(context["failed"]),
            "connections_total": PLANE_TOTAL,
            "by_class": (statistics or {}).get("by_class"),
            "by_pair": (statistics or {}).get("by_pair"),
            "path_shapes": (statistics or {}).get("path_shapes", {}).get("counts")
            if statistics else None,
            "u_statistics": (statistics or {}).get("u_statistics"),
            "statistics": statistics,
        }
        for record in context["records"]:
            item = {key: value for key, value in record.items()}
            item["plane"] = plane
            plane_row = (statistics or {}).get("plane_row")
            if item.get("z_mm") is None:
                item["z_mm"] = v3_config.PLANE_Z_MM.get(plane_row)
            routes.append(item)
    routes.sort(key=lambda record: (record.get("route_id") is None,
                                    record.get("route_id")))
    process = dict((plane_context.get("z1") or plane_context.get("z2") or {})
                   .get("process") or v3_config.process_record())
    return {
        "schema": SCHEMA,
        "units": "mm",
        "layer": 0,
        "topology": v3_config.TOPOLOGY,
        "algorithm": algorithm,
        "port_model": v3_config.PORT_MODEL,
        "process": v3_metrics._json_safe(process),  # noqa: SLF001
        "plane_model": {
            "z1": {"row": 1, "z_mm": 0.0,
                   "class_mix": dict(v3_config.EXPECTED["planes"]["z1"]),
                   "connections": PLANE_TOTAL},
            "z2": {"row": 2, "z_mm": 0.5,
                   "class_mix": dict(v3_config.EXPECTED["planes"]["z2"]),
                   "connections": PLANE_TOTAL},
            "z2_minus_z1_mm": 0.5,
            "z_transition": "not_implemented",
            "note": "two independent 2D planes at two glass-thickness heights; "
                    "each plane mixes same/opposite/adjacent connections; "
                    "cross-plane XY projections are not conflicts",
        },
        "plane_summaries": plane_blocks,
        "statistics": {},
        "routes": routes,
    }


def build_combined(root, algorithm, quiet=False):
    """Build ``combined/<A>/`` from the two plane runs."""
    started = time.perf_counter()
    root = Path(root)
    combined_dir = v3_metrics._combined_run_dir(root, algorithm)  # noqa: SLF001
    combined_dir.mkdir(parents=True, exist_ok=True)
    plane_context = {}
    plane_statistics = {}
    missing = []
    for plane in v3_metrics.PLANES:
        plane_dir = v3_metrics._plane_run_dir(root, algorithm, plane)  # noqa: SLF001
        if not (plane_dir / "routes.json").exists():
            missing.append(plane)
            continue
        context = v3_metrics.load_plane_context(plane_dir)
        context["statistics"] = _ensure_plane_statistics(plane_dir)
        plane_context[plane] = context
        plane_statistics[plane] = context["statistics"]
    if missing:
        raise FileNotFoundError(
            f"combined V3_{algorithm}: missing plane run(s) {missing}")
    combined_statistics = v3_metrics.build_combined_statistics(
        combined_dir, root=root, plane_statistics=plane_statistics, quiet=quiet)
    payload = _combined_routes_payload(algorithm, plane_context)
    payload["statistics"] = {
        "z1": plane_statistics["z1"],
        "z2": plane_statistics["z2"],
        "combined": combined_statistics,
    }
    routes_path = combined_dir / "routes_1024.json"
    routes_path.write_text(
        json.dumps(v3_metrics._json_safe(payload),  # noqa: SLF001
                   ensure_ascii=False, indent=1), encoding="utf-8")
    # plane vectors (single-layer GDS/SVG per plane) are viz-owned
    plane_vectors = {}
    for algorithm_plane in v3_metrics.PLANES:
        plane_dir = v3_metrics._plane_run_dir(root, algorithm, algorithm_plane)  # noqa: SLF001
        try:
            plane_vectors[algorithm_plane] = _ensure_plane_vectors(plane_dir)
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            plane_vectors[algorithm_plane] = {
                "error": f"{type(exc).__name__}: {exc}"}
    process = payload["process"]
    gds_info = write_combined_gds(
        combined_dir,
        {plane: plane_context[plane]["routed"] for plane in v3_metrics.PLANES},
        process)
    loaded_combined = v3_plots.load_combined(combined_dir, root=root)
    loaded_combined["statistics"] = combined_statistics
    layer_info = v3_plots.render_layer_2d(
        loaded_combined, combined_dir / "layer_2d.png",
        combined_dir / "layer_2d.svg")
    overlay_info = v3_plots.render_overlay_3d(
        loaded_combined, combined_dir / "overlay_3d.png")
    plane_summary = {}
    for plane in v3_metrics.PLANES:
        statistics = plane_statistics[plane]
        plane_summary[plane] = {
            "plane": plane,
            "row": (statistics or {}).get("plane_row"),
            "z_mm": (statistics or {}).get("z_mm"),
            "run_dir": str(v3_metrics._plane_run_dir(root, algorithm, plane)),  # noqa: SLF001
            "routed": len(plane_context[plane]["routed"]),
            "unrouted": len(plane_context[plane]["failed"]),
            "connections_total": PLANE_TOTAL,
            "routing_rate": len(plane_context[plane]["routed"]) / PLANE_TOTAL,
            "by_class": (statistics or {}).get("by_class"),
            "path_shapes": (statistics or {}).get("path_shapes", {}).get("counts")
            if statistics else None,
            "u_route_count": (statistics or {}).get("u_statistics", {}).get("count")
            if statistics else None,
            "crossing_count": (statistics or {}).get("crossing_count"),
            "mean_length_mm": (statistics or {}).get("mean_length_mm"),
            "audit_passed": (statistics or {}).get("audit_passed"),
            "vector_files": plane_vectors.get(plane),
        }
    planes_summary = {
        "schema": "four_side_1024_v3_planes_summary_v1",
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "topology": v3_config.TOPOLOGY,
        "algorithm": algorithm,
        "process": v3_metrics._json_safe(process),  # noqa: SLF001
        "planes": plane_summary,
        "combined": {
            "routed": combined_statistics["routed"],
            "unrouted": combined_statistics["unrouted"],
            "connections_total": TOTAL_CONNECTIONS,
            "routing_rate": combined_statistics["routing_rate"],
            "same_side_routed": combined_statistics.get(
                "same_side", {}).get("routed"),
            "total_length_mm": combined_statistics.get("total_length_mm"),
            "same_plane_crossings": combined_statistics.get(
                "same_plane_crossings"),
            "cross_plane_projected_overlap_informational": (
                combined_statistics.get("cross_plane_projected_overlap") or {}
            ).get("cross_plane_projected_internal_crossings"),
            "propagation_loss_total_db": (
                combined_statistics.get("propagation_loss") or {}).get("value_db"),
            "u_route_count": (combined_statistics.get("u_statistics") or {}).get(
                "count"),
            "refold_route_count": (combined_statistics.get("refold_statistics")
                                   or {}).get("count"),
        },
        "gds": {
            "combined": gds_info,
            "plane_layer_ownership": {
                "planes/<A>/z1/routing_all.gds": "single layer 0 (plane z1)",
                "planes/<A>/z2/routing_all.gds": "single layer 0 (plane z2)",
                "routing_1024_two_height.gds": GDS_TWO_HEIGHT_NOTE,
            },
        },
        "figures": {
            "layer_2d_png": layer_info,
            "overlay_3d_png": overlay_info,
        },
        "files": {
            "routes_1024_json": str(routes_path),
            "statistics_json": str(combined_dir / "statistics.json"),
        },
        "wall_seconds": time.perf_counter() - started,
    }
    (combined_dir / "planes_summary.json").write_text(
        json.dumps(v3_metrics._json_safe(planes_summary),  # noqa: SLF001
                   ensure_ascii=False, indent=1), encoding="utf-8")
    if not quiet:
        print(json.dumps({
            "combined_dir": str(combined_dir),
            "routed": combined_statistics["routed"],
            "total": TOTAL_CONNECTIONS,
            "by_plane": {plane: len(plane_context[plane]["routed"])
                         for plane in v3_metrics.PLANES},
            "same_side_routed": combined_statistics.get(
                "same_side", {}).get("routed"),
            "same_plane_crossings": combined_statistics.get(
                "same_plane_crossings"),
            "gds_layers": gds_info["layers"],
            "gds_paths_per_layer": gds_info["paths_per_layer"],
            "files": sorted(["routes_1024.json", "statistics.json",
                             "planes_summary.json", "layer_2d.png",
                             "layer_2d.svg", "overlay_3d.png",
                             "routing_1024_two_height.gds"]),
        }, ensure_ascii=False))
    return combined_dir


def build_all(root, quiet=False):
    """Build every combined layout whose two plane runs both exist."""
    root = Path(root)
    built = []
    skipped = []
    for algorithm in v3_metrics.ALGORITHMS:
        planes = [v3_metrics._plane_run_dir(root, algorithm, plane)  # noqa: SLF001
                  for plane in v3_metrics.PLANES]
        if all((plane / "routes.json").exists() for plane in planes):
            built.append(build_combined(root, algorithm, quiet=quiet))
        else:
            skipped.append(f"V3_{algorithm}")
    return {"built": [str(path) for path in built], "skipped": skipped}


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Build the V3-Huang combined dual-height artefacts.")
    parser.add_argument("--root",
                        default=str(getattr(v3_config, "OUTPUT_ROOT",
                                            "outputs/four_side_1024_v3_huang_R40_gap30_abcd")))
    parser.add_argument("--algorithm", choices=list(v3_metrics.ALGORITHMS))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.all:
        result = build_all(args.root, quiet=args.quiet)
        print(json.dumps({"built": result["built"],
                          "skipped": result["skipped"]}, ensure_ascii=False))
        return 0
    if not args.algorithm:
        raise SystemExit("v3.combine: use --all or --algorithm")
    build_combined(args.root, args.algorithm, quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
