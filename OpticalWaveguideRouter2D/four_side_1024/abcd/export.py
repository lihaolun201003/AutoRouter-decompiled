"""Single-layer GDSII + SVG export for one ABCD experiment run (SPEC §6).

Phase 6 deliverable.  Takes an experiment's ``routes.json`` (SPEC §4 schema) and
writes the two vector artefacts required by the deliverable contract:

* ``routing_all.gds`` -- **single layer** (layer 0, datatype 0) GDSII with the
  0.05 mm waveguide width, arcs discretised with chord sagitta <= 0.0005 mm.
  The d56 exporter ``four_side_1024.d56.outputs_d56.export_gds`` is reused by
  import (the d56 package is never modified); it re-reads the written file and
  raises unless the layer set is exactly ``[0]`` and every route produced one
  path.
* ``routing_all.svg`` -- compact hand-built SVG with chord sagitta <= 0.01 mm
  and a hard 5 MB cap, reusing ``four_side_1024.d56.plots_d56.write_svg``.

Extra verifications performed here (beyond the reused exporters):

* chord sagitta recomputed *from the sampled polylines* for every arc (not just
  trusting the sampling parameter);
* SVG parsed as XML and measured; GDS layer set re-asserted as ``[0]``;
* all sampled centrelines inside the stroked board envelope.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.abcd.export --run-dir \\
        outputs/four_side_1024_v1_v2_abcd/V1_B

    # or explicitly:
    .venv\\Scripts\\python.exe -m four_side_1024.abcd.export \\
        --routes outputs/four_side_1024_v1_v2_abcd/V1_B/routes.json \\
        --config outputs/four_side_1024_v1_v2_abcd/V1_B/config.json \\
        --gds-out outputs/four_side_1024_v1_v2_abcd/V1_B/routing_all.gds \\
        --svg-out outputs/four_side_1024_v1_v2_abcd/V1_B/routing_all.svg
"""
from __future__ import annotations

import argparse
import json
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from ..d56.outputs_d56 import export_gds
from ..d56.plots_d56 import sample_curves, write_svg
from .metrics import (_json_safe, _load_json, _pair_of, _sha256, _split_records,
                      _status, _derived_config)

SCHEMA = "four_side_1024_abcd_export_v1"
TOOL = "four_side_1024.abcd.export"
BOARD_MM = 150.0
GDS_SAGITTA_MM = 0.0005
SVG_SAGITTA_MM = 0.01
SVG_MAX_BYTES = 5 * 1024 * 1024
LAYER = 0
WIDTH_MM = 0.05
MIN_RADIUS_MM = 5.0


def _routed_records(routes_payload):
    records, meta = _split_records(routes_payload)
    routed = []
    for record in records:
        if _status(record) != "routed":
            continue
        primitives = record.get("primitives") or []
        if not primitives:
            continue
        item = dict(record)
        if not item.get("pair"):
            item["pair"] = _pair_of(record)
        routed.append(item)
    return routed, meta


def _export_config(config):
    """Subset of the merged configuration consumed by the d56 exporters."""
    return {
        "width_mm": float(config.get("width_mm") or WIDTH_MM),
        "sagitta_mm": min(float(config.get("sagitta_mm") or GDS_SAGITTA_MM),
                          GDS_SAGITTA_MM),
        "min_radius_mm": float(config.get("min_radius_mm") or MIN_RADIUS_MM),
        "board_mm": [float(value) for value in (config.get("board_mm")
                                                or (BOARD_MM, BOARD_MM))],
        "layer": LAYER,
    }


def _arc_sample_count(primitive, sagitta_mm, radius_mm=None):
    """Number of chord segments ``geometry.sample`` uses for one arc."""
    radius = float(radius_mm if radius_mm is not None else primitive["radius"])
    if radius <= 0:
        return 1
    sagitta = min(float(sagitta_mm), radius * 0.5)
    step = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - sagitta / radius)))
    return max(1, int(math.ceil(abs(float(primitive["sweep"])) /
                                max(step, 1e-12))))


def verify_curve_sagitta(routed, curves, sagitta_limit_mm=GDS_SAGITTA_MM,
                         radius_mm=MIN_RADIUS_MM):
    """Independent check: recompute the chord sagitta of every sampled arc."""
    worst = 0.0
    arcs_checked = 0
    mismatch_routes = []
    for record in routed:
        route_id = record.get("route_id")
        points = curves.get(route_id)
        if points is None:
            mismatch_routes.append(route_id)
            continue
        points = np.asarray(points, dtype=float)
        cursor = 0
        route_worst = 0.0
        for primitive in record.get("primitives") or []:
            if primitive.get("kind") == "line":
                count = 2
            else:
                count = _arc_sample_count(primitive, sagitta_limit_mm) + 1
                radius = float(primitive.get("radius") or radius_mm)
                segment = points[cursor:cursor + count]
                arcs_checked += 1
                for first, second in zip(segment[:-1], segment[1:]):
                    chord = float(np.linalg.norm(np.asarray(second) - first))
                    half = 0.5 * chord
                    sagitta = radius - math.sqrt(max(0.0, radius * radius - half * half))
                    if sagitta > route_worst:
                        route_worst = sagitta
            cursor += count - 1
        if cursor + 1 != len(points):
            mismatch_routes.append(route_id)
        worst = max(worst, route_worst)
    ok = bool(arcs_checked) and worst <= sagitta_limit_mm + 1e-12
    return {
        "arcs_checked": arcs_checked,
        "max_chord_sagitta_mm": worst,
        "sagitta_limit_mm": sagitta_limit_mm,
        "verified": ok,
        "polylines_with_unexpected_length": mismatch_routes[:20],
        "unexpected_length_count": len(mismatch_routes),
    }


def verify_stroked_bounds(routed, curves, width_mm, board_mm):
    """Every stroked primitive must stay inside [0, bw] x [0, bh] (SPEC §1.7).

    Uses the exact analytic stroked extents of ``four_side_1024.geometry.bounds``
    (perpendicular half-width for lines, radial offset for arcs); endpoints that
    sit exactly on the board edge are legal, which is why sampled-point bounding
    boxes with an all-round tolerance would be wrong here.
    """
    from ..geometry import bounds as geometry_bounds

    board_width, board_height = float(board_mm[0]), float(board_mm[1])
    worst = None
    offenders = []
    primitives_checked = 0
    for record in routed:
        primitives = record.get("primitives") or []
        route_worst = None
        for primitive in primitives:
            try:
                box = geometry_bounds(primitive, width_mm)
            except (ValueError, KeyError, TypeError):
                continue
            primitives_checked += 1
            excess = max(-box[0], -box[1], box[2] - board_width,
                         box[3] - board_height)
            if route_worst is None or excess > route_worst:
                route_worst = excess
        if route_worst is None:
            continue
        if worst is None or route_worst > worst:
            worst = route_worst
        if route_worst > 1e-6:
            offenders.append({"route_id": record.get("route_id"),
                              "excess_mm": route_worst})
    return {
        "primitives_checked": primitives_checked,
        "max_outside_board_mm": worst,
        "violation_count": len(offenders),
        "violations": offenders[:20],
        "verified": not offenders,
    }


def export_run(routes_path, config_path=None, run_dir=None,
               gds_path=None, svg_path=None, verbose=False):
    """Export one run's ``routing_all.gds`` and ``routing_all.svg``."""
    started = time.perf_counter()
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
    gds_path = Path(gds_path) if gds_path else run_dir / "routing_all.gds"
    svg_path = Path(svg_path) if svg_path else run_dir / "routing_all.svg"
    gds_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    routes_payload = _load_json(routes_path)
    routed, routes_meta = _routed_records(routes_payload)
    if not routed:
        raise SystemExit(f"export: no routed geometry in {routes_path}")
    config_payload = _load_json(config_path) if config_path else None
    config = _derived_config(routes_meta, config_payload, run_dir)
    export_config = _export_config(config)
    width_mm = export_config["width_mm"]
    board_mm = export_config["board_mm"]
    sagitta_mm = export_config["sagitta_mm"]
    messages = []

    def log(message):
        messages.append(str(message))
        if verbose:
            print(message)

    log(f"{len(routed)} routed records loaded from {routes_path.name}")
    curves = sample_curves(routed, sagitta_mm)
    log(f"sampled {len(curves)} centrelines at chord sagitta {sagitta_mm:g} mm")

    # --- GDS (single layer) -------------------------------------------------
    gds_started = time.perf_counter()
    gds_info = export_gds(routed, curves, export_config, gds_path, log)
    gds_info["generation_seconds"] = time.perf_counter() - gds_started
    gds_info["layers_exactly_single"] = list(gds_info.get("layers") or []) == [LAYER]
    if not gds_info["layers_exactly_single"]:
        raise RuntimeError(f"GDS layer verification failed: {gds_info}")
    gds_info["sha256"] = _sha256(gds_path)
    gds_info["routed_records"] = len(routed)
    gds_info["expected_paths"] = len(curves)

    # --- SVG ----------------------------------------------------------------
    svg_started = time.perf_counter()
    svg_info = write_svg(routed, svg_path, sagitta_mm=SVG_SAGITTA_MM,
                         max_bytes=SVG_MAX_BYTES)
    svg_info["generation_seconds"] = time.perf_counter() - svg_started
    svg_info["bytes"] = int(svg_path.stat().st_size)
    svg_info["sha256"] = _sha256(svg_path)
    svg_info["under_5mb"] = svg_info["bytes"] <= SVG_MAX_BYTES
    svg_info["sagitta_within_contract"] = (
        float(svg_info.get("sagitta_mm") or SVG_SAGITTA_MM) <= SVG_SAGITTA_MM + 1e-15)
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
        svg_info["xml_valid"] = True
        svg_info["xml_tag"] = root.tag
        svg_info["xml_path_count"] = len(root.findall(".//{http://www.w3.org/2000/svg}path"))
    except ET.ParseError as exc:
        svg_info["xml_valid"] = False
        svg_info["xml_error"] = str(exc)
    if not (svg_info["xml_valid"] and svg_info["under_5mb"]
            and svg_info["sagitta_within_contract"]):
        raise RuntimeError(f"SVG verification failed: {svg_info}")

    sagitta_check = verify_curve_sagitta(routed, curves, sagitta_mm)
    bounds_check = verify_stroked_bounds(routed, curves, width_mm, board_mm)
    if not sagitta_check["verified"]:
        raise RuntimeError(f"arc sagitta verification failed: {sagitta_check}")
    if not bounds_check["verified"]:
        raise RuntimeError(f"stroked board bounds failed: {bounds_check}")

    summary = _json_safe({
        "schema": SCHEMA,
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "run_dir": str(run_dir),
        "source": {
            "routes_json": str(routes_path),
            "routes_sha256": _sha256(routes_path),
            "routes_schema": routes_meta.get("schema"),
            "config_json": str(config_path) if config_path else None,
            "routed_records": len(routed),
        },
        "config": export_config,
        "gds": gds_info,
        "svg": svg_info,
        "verification": {
            "gds_layers": gds_info.get("layers"),
            "single_layer": gds_info["layers_exactly_single"],
            "gds_paths": gds_info.get("paths"),
            "routed_records": len(routed),
            "arc_sagitta": sagitta_check,
            "stroked_bounds": bounds_check,
            "svg_under_5mb": svg_info["under_5mb"],
            "svg_xml_valid": svg_info["xml_valid"],
        },
        "log": messages,
        "wall_seconds": time.perf_counter() - started,
        "status": ("research virtual_unfolded single-layer geometry, chordal arcs; "
                   "not a fabrication release"),
    })
    return summary


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Export single-layer GDSII + SVG for one ABCD experiment run.")
    parser.add_argument("--routes", help="path to <run>/routes.json")
    parser.add_argument("--config", help="path to <run>/config.json")
    parser.add_argument("--run-dir", help="run directory; infers routes/config/output")
    parser.add_argument("--gds-out", help="override the routing_all.gds path")
    parser.add_argument("--svg-out", help="override the routing_all.svg path")
    parser.add_argument("--verbose", action="store_true", help="echo exporter log")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    run_dir = Path(args.run_dir) if args.run_dir else None
    routes_path = args.routes
    config_path = args.config
    if run_dir is not None:
        routes_path = routes_path or str(run_dir / "routes.json")
        if config_path is None:
            candidate = run_dir / "config.json"
            config_path = str(candidate) if candidate.exists() else None
    if not routes_path:
        raise SystemExit("export: --routes or --run-dir is required")
    run_dir_path = Path(run_dir) if run_dir is not None else Path(routes_path).parent
    summary = export_run(routes_path=routes_path, config_path=config_path,
                         run_dir=run_dir_path, gds_path=args.gds_out,
                         svg_path=args.svg_out, verbose=args.verbose)
    print(json.dumps({
        "gds": summary["gds"]["file"],
        "gds_bytes": summary["gds"]["bytes"],
        "gds_layers": summary["gds"]["layers"],
        "gds_paths": summary["gds"]["paths"],
        "svg": summary["svg"]["file"],
        "svg_bytes": summary["svg"]["bytes"],
        "svg_sagitta_mm": summary["svg"]["sagitta_mm"],
        "max_chord_sagitta_mm": summary["verification"]["arc_sagitta"]["max_chord_sagitta_mm"],
        "single_layer": summary["verification"]["single_layer"],
        "svg_xml_valid": summary["verification"]["svg_xml_valid"],
        "wall_seconds": round(summary["wall_seconds"], 3),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
