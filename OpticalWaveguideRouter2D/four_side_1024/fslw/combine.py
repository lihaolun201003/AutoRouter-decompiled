"""Build the 1024-channel dual-height combined FSLW artefact.

Round-2 deliverable for ``four_side_1024/fslw/SPEC.md`` §2/§8/§10.  A combined
layout is the pair of *independent* 2D plane solutions at two physical heights:

* plane **z1** = CSV row 1 = the 512 opposite connections, model height 0.0;
* plane **z2** = CSV row 2 = the 512 adjacent connections, model height 0.5.

Nothing here decides legality: each plane was validated on its own; the combined
layout only merges statistics and visualises the two heights.  Cross-plane
XY-projected overlaps are informational only and are never violations (SPEC §2).

Outputs for ``combined/<TOPOLOGY>/<ALGO>/``:

* ``routes_1024.json``      -- all 1024 identities with ``plane``/``z_mm`` tags,
                               per-plane summaries and per-plane + combined stats;
* ``statistics.json``       -- combined metrics (same-plane crossings kept apart
                               from ``cross_plane_projected_overlap``);
* ``planes_summary.json``   -- compact per-plane table + GDS layer documentation;
* ``layer_2d.png``/``.svg`` -- the two planes side by side, identical scale;
* ``overlay_3d.png``        -- height-distinguished 3D view;
* ``routing_1024_two_height.gds`` -- **layer 0 = plane z1, layer 1 = plane z2**.
  These are two *physical heights* of the same single-layer process, NOT a
  multi-layer waveguide stack; no z-transition is implemented.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.fslw.combine --root \\
        outputs/four_side_1024_fslw_R40_gap30_abcd --all
    .venv\\Scripts\\python.exe -m four_side_1024.fslw.combine --root \\
        outputs/four_side_1024_fslw_R40_gap30_abcd --topology V1 --algorithm B
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ..d56.plots_d56 import sample_curves
from . import config as fslw_config
from . import metrics as fslw_metrics
from . import plots as fslw_plots

SCHEMA = "four_side_1024_fslw_combined_routes_v1"
TOOL = "four_side_1024.fslw.combine"
GDS_SAGITTA_MM = 0.0005
PLANE_LAYER = {"z1": 0, "z2": 1}
GDS_TWO_HEIGHT_NOTE = (
    "routing_1024_two_height.gds: layer 0 = plane z1 (row 1, model height 0.0), "
    "layer 1 = plane z2 (row 2, model height 0.5). The two GDS layers represent "
    "two PHYSICAL HEIGHTS of the same single-layer process; they are NOT a "
    "multi-layer waveguide stack, and no z-transition/via/fanout is implemented. "
    "Cross-plane XY projections are not conflicts (SPEC §2).")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _plane_dir(root, topology, algorithm, plane):
    return fslw_metrics._plane_run_dir(root, topology, algorithm, plane)  # noqa: SLF001


def _ensure_plane_statistics(plane_dir, quiet=True):
    statistics_path = plane_dir / "statistics.json"
    if statistics_path.exists():
        try:
            return fslw_metrics._load_json(statistics_path)  # noqa: SLF001
        except (OSError, json.JSONDecodeError):
            pass
    return fslw_metrics.build_plane_statistics(plane_dir, quiet=quiet)


def _ensure_plane_vectors(plane_dir):
    """Plane GDS/SVG are viz-owned and may be written by this module too."""
    gds_path = plane_dir / "routing_all.gds"
    svg_path = plane_dir / "routing_all.svg"
    if gds_path.exists() and svg_path.exists():
        return {"gds": str(gds_path), "svg": str(svg_path), "created": False}
    from ..abcd import export as abcd_export
    # gdspy >=1.6 registers every new Cell in the *global* gdspy.current_library;
    # the d56 exporter names its cell 'D56_SINGLE_LAYER', so two plane exports in
    # one process would collide.  Point the global at a throwaway library while
    # the exporter builds its own one (its own library.cells still receives the
    # cell, so write_gds is unaffected).
    import gdspy
    previous = gdspy.current_library
    gdspy.current_library = gdspy.GdsLibrary(name="fslw_scratch_library")
    try:
        summary = abcd_export.export_run(routes_path=plane_dir / "routes.json",
                                         run_dir=plane_dir)
    finally:
        gdspy.current_library = previous
    return {"gds": summary["gds"]["file"], "svg": summary["svg"]["file"],
            "created": True,
            "max_chord_sagitta_mm": summary["verification"]["arc_sagitta"][
                "max_chord_sagitta_mm"]}


def _combined_routes_payload(topology, algorithm, z1, z2, process):
    """Merge both plane route lists into the 1024-identity combined payload."""
    routes = []
    plane_blocks = {}
    for plane, data in (("z1", z1), ("z2", z2)):
        plane_blocks[plane] = {
            "plane": plane,
            "z_mm": fslw_config.PLANE_Z_MM.get(fslw_config.PLANE_ROW[plane]),
            "row": fslw_config.PLANE_ROW[plane],
            "routes_json": str(data["run_dir"] / "routes.json"),
            "routed": len(data["routed"]),
            "unrouted": len(data["failed"]),
            "connections_total": fslw_metrics.CONNECTIONS_PER_PLANE,
            "statistics": data["statistics"],
        }
        for record in data["records"]:
            item = {key: value for key, value in record.items()}
            item["plane"] = plane
            item["z_mm"] = fslw_config.PLANE_Z_MM.get(
                fslw_config.PLANE_ROW[plane])
            item.setdefault("source_row", fslw_config.PLANE_ROW[plane])
            item.setdefault("target_row", fslw_config.PLANE_ROW[plane])
            routes.append(item)
    routes.sort(key=lambda record: (record.get("route_id") is None,
                                    record.get("route_id")))
    return {
        "schema": SCHEMA,
        "units": "mm",
        "layer": 0,
        "topology": topology,
        "algorithm": algorithm,
        "port_model": process.get("port_model")
        or getattr(fslw_config, "PORT_MODEL", "real_2x16_dual_height"),
        "process": fslw_metrics._json_safe(process),  # noqa: SLF001
        "plane_model": {
            "z1": {"row": 1, "z_mm": 0.0,
                   "relations": ["opposite"], "connections": 512},
            "z2": {"row": 2, "z_mm": 0.5,
                   "relations": ["adjacent"], "connections": 512},
            "z2_minus_z1_mm": 0.5,
            "z_transition": "not_implemented",
            "note": "two independent 2D planes at two glass-thickness heights; "
                    "each plane is layer=0 2D, z is model metadata only; "
                    "cross-plane XY projections are not conflicts",
        },
        "plane_summaries": plane_blocks,
        "statistics": {},          # filled by build_combined_artifacts
        "routes": routes,
    }


def write_combined_gds(combined_dir, plane_routes, process, name="routing_1024_two_height.gds"):
    """Write the two-height GDS: layer 0 = z1, layer 1 = z2 (documented)."""
    import gdspy
    combined_dir = Path(combined_dir).resolve()
    path = combined_dir / name
    width = float(process.get("width_mm") or fslw_config.WIDTH_MM)
    sagitta = min(float(process.get("sagitta_mm") or GDS_SAGITTA_MM),
                  GDS_SAGITTA_MM)
    library = gdspy.GdsLibrary(name="FSLW_R40_DUAL_HEIGHT_1024",
                               unit=1e-3, precision=1e-9)
    previous_library = gdspy.current_library
    gdspy.current_library = library
    try:
        cell = library.new_cell("FSLW_TWO_HEIGHT_LAYER0_Z1_LAYER1_Z2")
        counts = {}
        for plane, routed in plane_routes.items():
            layer = PLANE_LAYER[plane]
            curves = sample_curves(routed, sagitta)
            exported = 0
            for record in routed:
                points = curves.get(record.get("route_id"))
                if points is None or len(points) < 2:
                    continue
                cell.add(gdspy.FlexPath(points, width, gdsii_path=True,
                                        layer=layer, datatype=0, ends="flush"))
                exported += 1
            counts[plane] = {"layer": layer, "paths": exported,
                             "routed": len(routed)}
        library.write_gds(str(path))
    finally:
        gdspy.current_library = previous_library
    reread = gdspy.GdsLibrary(infile=str(path))
    tops = reread.top_level()
    paths = list(tops[0].paths) if tops else []
    layers = sorted({int(layer) for item in paths for layer in item.layers})
    datatypes = sorted({int(datatype) for item in paths
                        for datatype in item.datatypes})
    layer_counts = {}
    for layer in layers:
        layer_counts[layer] = sum(
            1 for item in paths if any(int(value) == layer for value in item.layers))
    expected_layers = sorted(PLANE_LAYER.values())
    okay = (layers == expected_layers
            and datatypes == [0]
            and layer_counts.get(0, 0) == counts["z1"]["paths"]
            and layer_counts.get(1, 0) == counts["z2"]["paths"])
    info = {
        "file": str(path),
        "bytes": path.stat().st_size,
        "layer_documentation": GDS_TWO_HEIGHT_NOTE,
        "layers": layers,
        "datatypes": datatypes,
        "paths_per_layer": layer_counts,
        "plane_counts": counts,
        "width_mm": width,
        "arc_chord_sagitta_mm": sagitta,
        "unit_m": 1e-3,
        "precision_m": 1e-9,
        "verified": bool(okay),
        "status": "research dual-height geometry; chordal arcs; not a fabrication release",
    }
    if not okay:
        raise RuntimeError(f"combined GDS verification failed: {info}")
    return info


# ---------------------------------------------------------------------------
# build one combined layout
# ---------------------------------------------------------------------------
def build_combined(root, topology, algorithm, quiet=False):
    """Build ``combined/<TOPOLOGY>/<ALGO>/`` from the two plane runs."""
    started = time.perf_counter()
    root = Path(root)
    combined_dir = fslw_metrics._combined_run_dir(root, topology, algorithm)  # noqa: SLF001
    combined_dir.mkdir(parents=True, exist_ok=True)
    plane_data = {}
    plane_statistics = {}
    missing = []
    for plane in ("z1", "z2"):
        plane_dir = _plane_dir(root, topology, algorithm, plane)
        if not (plane_dir / "routes.json").exists():
            missing.append(plane)
            continue
        loaded = fslw_plots.load_plane(plane_dir)
        loaded["statistics"] = _ensure_plane_statistics(plane_dir)
        plane_statistics[plane] = loaded["statistics"]
        plane_data[plane] = loaded
    if missing:
        raise FileNotFoundError(
            f"combined {topology}_{algorithm}: missing plane run(s) {missing}")
    process = dict(plane_data["z1"]["process"])
    # combined statistics are written by metrics.build_combined_statistics
    combined_statistics = fslw_metrics.build_combined_statistics(
        combined_dir, root=root, plane_statistics=plane_statistics,
        quiet=quiet)
    # merged routes_1024.json
    payload = _combined_routes_payload(topology, algorithm,
                                       plane_data["z1"], plane_data["z2"],
                                       process)
    payload["statistics"] = {
        "z1": plane_statistics["z1"],
        "z2": plane_statistics["z2"],
        "combined": combined_statistics,
    }
    routes_path = combined_dir / "routes_1024.json"
    routes_path.write_text(json.dumps(fslw_metrics._json_safe(payload),  # noqa: SLF001
                                      ensure_ascii=False, indent=1),
                           encoding="utf-8")
    # plane vectors (routing_all.gds/svg are viz-owned per the frozen contract)
    plane_vectors = {}
    for plane in ("z1", "z2"):
        try:
            plane_vectors[plane] = _ensure_plane_vectors(
                _plane_dir(root, topology, algorithm, plane))
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            plane_vectors[plane] = {"error": f"{type(exc).__name__}: {exc}"}
    # combined two-height GDS
    gds_info = write_combined_gds(
        combined_dir,
        {plane: plane_data[plane]["routed"] for plane in ("z1", "z2")},
        process)
    # figures: layer_2d.png/.svg + overlay_3d.png
    loaded_combined = fslw_plots.load_combined(combined_dir, root=root)
    # make sure the freshly written combined statistics is used by the figures
    loaded_combined["statistics"] = combined_statistics
    layer_info = fslw_plots.render_layer_2d(
        loaded_combined, combined_dir / "layer_2d.png",
        combined_dir / "layer_2d.svg")
    overlay_info = fslw_plots.render_overlay_3d(
        loaded_combined, combined_dir / "overlay_3d.png")
    planes_summary = {
        "schema": "four_side_1024_fslw_planes_summary_v1",
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "topology": topology,
        "algorithm": algorithm,
        "process": fslw_metrics._json_safe(process),  # noqa: SLF001
        "planes": {
            plane: {
                "plane": plane,
                "row": fslw_config.PLANE_ROW[plane],
                "z_mm": fslw_config.PLANE_Z_MM.get(
                    fslw_config.PLANE_ROW[plane]),
                "run_dir": str(_plane_dir(root, topology, algorithm, plane)),
                "routed": len(plane_data[plane]["routed"]),
                "unrouted": len(plane_data[plane]["failed"]),
                "connections_total": fslw_metrics.CONNECTIONS_PER_PLANE,
                "routing_rate": (len(plane_data[plane]["routed"])
                                 / fslw_metrics.CONNECTIONS_PER_PLANE),
                "crossing_count": plane_statistics[plane].get("crossing_count"),
                "mean_length_mm": plane_statistics[plane].get("mean_length_mm"),
                "audit_passed": plane_statistics[plane].get("audit_passed"),
                "vector_files": plane_vectors.get(plane),
            }
            for plane in ("z1", "z2")
        },
        "combined": {
            "routed": combined_statistics["routed"],
            "unrouted": combined_statistics["unrouted"],
            "connections_total": fslw_metrics.TOTAL_CONNECTIONS,
            "routing_rate": combined_statistics["routing_rate"],
            "total_length_mm": combined_statistics.get("total_length_mm"),
            "same_plane_crossings": combined_statistics.get(
                "same_plane_crossings"),
            "cross_plane_projected_overlap_informational": (
                combined_statistics.get("cross_plane_projected_overlap") or {}
            ).get("cross_plane_projected_internal_crossings"),
            "propagation_loss_total_db": (combined_statistics.get(
                "propagation_loss") or {}).get("value_db"),
        },
        "gds": {
            "combined": gds_info,
            "plane_layer_ownership": {
                "planes/<T>/<A>/z1/routing_all.gds": "single layer 0 (plane z1)",
                "planes/<T>/<A>/z2/routing_all.gds": "single layer 0 (plane z2)",
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
        json.dumps(fslw_metrics._json_safe(planes_summary),  # noqa: SLF001
                   ensure_ascii=False, indent=1), encoding="utf-8")
    if not quiet:
        print(json.dumps({
            "combined_dir": str(combined_dir),
            "routed": combined_statistics["routed"],
            "total": fslw_metrics.TOTAL_CONNECTIONS,
            "by_plane": {plane: len(plane_data[plane]["routed"])
                         for plane in ("z1", "z2")},
            "same_plane_crossings": combined_statistics.get(
                "same_plane_crossings"),
            "cross_plane_projected_internal": (
                combined_statistics.get("cross_plane_projected_overlap") or {}
            ).get("cross_plane_projected_internal_crossings"),
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
    seen = set()
    for topology in ("V1", "V2"):
        for algorithm in ("A", "B", "C", "D"):
            planes = [_plane_dir(root, topology, algorithm, plane)
                      for plane in ("z1", "z2")]
            if all((plane / "routes.json").exists() for plane in planes):
                built.append(build_combined(root, topology, algorithm,
                                            quiet=quiet))
                seen.add((topology, algorithm))
    for topology in ("V1", "V2"):
        for algorithm in ("A", "B", "C", "D"):
            if (topology, algorithm) not in seen:
                skipped.append(f"{topology}_{algorithm}")
    return {"built": [str(path) for path in built], "skipped": skipped}


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Build the 1024-channel dual-height combined FSLW artefacts.")
    parser.add_argument("--root",
                        default="outputs/four_side_1024_fslw_R40_gap30_abcd")
    parser.add_argument("--topology", choices=["V1", "V2"])
    parser.add_argument("--algorithm", choices=["A", "B", "C", "D"])
    parser.add_argument("--all", action="store_true",
                        help="build every combined layout with both plane runs")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.all:
        result = build_all(args.root, quiet=args.quiet)
        print(json.dumps({"built": result["built"],
                          "skipped": result["skipped"]}, ensure_ascii=False))
        return 0
    if not (args.topology and args.algorithm):
        raise SystemExit("fslw.combine: use --all or --topology/--algorithm")
    build_combined(args.root, args.topology, args.algorithm, quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
