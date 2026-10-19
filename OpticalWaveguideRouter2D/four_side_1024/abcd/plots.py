"""Per-experiment routing figures for the ABCD matrix (SPEC §6).

Phase 6 deliverable.  Every full-board figure of every experiment uses the
**same** coordinate limits ``[-9, 159]^2`` (board plus connector label pad),
the same figure size / dpi / line width, and the same side-pair palette
(``four_side_1024.outputs.COLORS``, as in ``d56/plots_d56.py``).  Palette and
framing are reused from the d56 plotting module by import, so figures of the
eight experiments and of the historical 467 result are directly comparable.

Every title states the **actual routed count / 1024** of that experiment next
to the experiment label, as required by SPEC §6.

Outputs (in the experiment run directory):

* ``routing_all.png``   -- all routed centrelines, coloured by side pair;
* ``routing_detail.png``-- 4 densest crossing hotspots (default on);
* ``by_pair_<PAIR>.png``-- optional per-side-pair figures (``--by-pair``).

The SVG / GDS pair is produced by ``abcd/export.py`` (same geometry, same
sampling contract).  All figures are presentation only: legality is never
decided here.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.abcd.plots --run-dir \\
        outputs/four_side_1024_v1_v2_abcd/V1_B

    # or explicitly, incl. the optional per-pair figures:
    .venv\\Scripts\\python.exe -m four_side_1024.abcd.plots \\
        --routes outputs/four_side_1024_v1_v2_abcd/V1_B/routes.json \\
        --config outputs/four_side_1024_v1_v2_abcd/V1_B/config.json \\
        --by-pair
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from ..d56.plots_d56 import (BOARD_MM, DPI, PAIR_ORDER, draw_connectors,
                             plot_detail, plot_routes, pyplot, sample_curves)
from .metrics import (CROSSING_GRID_MM, TOTAL_CONNECTIONS, _derived_config,
                      _endpoint_bundle, _json_safe, _load_json, _pair_of,
                      _relation_of, _split_records, _status, compute_pair_audit)

SCHEMA = "four_side_1024_abcd_plots_v1"
TOOL = "four_side_1024.abcd.plots"
DISPLAY_SAGITTA_MM = 0.005
DETAIL_HOTSPOTS = 4
DETAIL_HALF_MM = 12.5


def _stats_path(run_dir):
    return Path(run_dir) / "statistics.json"


def _experiment_label(config, run_dir, statistics):
    for candidate in ((statistics or {}).get("experiment"),
                      config.get("experiment"),
                      getattr(run_dir, "name", None)):
        if candidate:
            return str(candidate)
    return "experiment"


def _routed_records(routes_payload):
    records, meta = _split_records(routes_payload)
    routed = []
    for record in records:
        if _status(record) != "routed":
            continue
        if not record.get("primitives"):
            continue
        item = dict(record)
        item.setdefault("pair", _pair_of(record))
        item.setdefault("relation", _relation_of(record))
        routed.append(item)
    return routed, meta


def load_display_data(routes_path, config_path=None, run_dir=None,
                      sagitta_mm=DISPLAY_SAGITTA_MM):
    """Load routed records, sampled display polylines and connector table."""
    routes_path = Path(routes_path)
    if run_dir is None:
        run_dir = routes_path.parent
    else:
        run_dir = Path(run_dir)
    if config_path is None:
        candidate = run_dir / "config.json"
        config_path = candidate if candidate.exists() else None
    routes_payload = _load_json(routes_path)
    routed, routes_meta = _routed_records(routes_payload)
    config_payload = _load_json(config_path) if config_path else None
    config = _derived_config(routes_meta, config_payload, run_dir)
    bundle = _endpoint_bundle(config)
    connectors = bundle.get("connectors") or []
    curves = sample_curves(routed, sagitta_mm)
    meta = {}
    for record in routed:
        meta[record["route_id"]] = {
            "pair": record.get("pair") or _pair_of(record),
            "relation": record.get("relation") or _relation_of(record),
        }
    return {
        "routes_path": routes_path,
        "run_dir": run_dir,
        "config_path": Path(config_path) if config_path else None,
        "routes_payload": routes_payload,
        "routes_meta": routes_meta,
        "config": config,
        "routed": routed,
        "curves": curves,
        "meta": meta,
        "connectors": connectors,
        "endpoints": bundle.get("endpoints"),
        "sagitta_mm": sagitta_mm,
    }


def _statistics_value(statistics, key, default=None):
    if not isinstance(statistics, dict):
        return default
    value = statistics.get(key)
    return default if value is None else value


def _crossings_for_detail(routed, config):
    """Crossing points (``x_mm``/``y_mm`` keys) for the hotspot panels."""
    audit = compute_pair_audit(routed, config)
    crossings = []
    for crossing in audit.get("crossings") or []:
        x = crossing.get("x", crossing.get("x_mm"))
        y = crossing.get("y", crossing.get("y_mm"))
        if x is None or y is None:
            continue
        crossings.append({"x_mm": float(x), "y_mm": float(y),
                          "angle_deg": crossing.get("angle_deg"),
                          "route_a": crossing.get("route_a"),
                          "route_b": crossing.get("route_b")})
    return audit, crossings


def render_experiment(routes_path, config_path=None, run_dir=None,
                      statistics=None, experiment=None, by_pair=False,
                      with_detail=True, display_sagitta_mm=DISPLAY_SAGITTA_MM,
                      statistics_path=None, verbose=False):
    """Render ``routing_all.png`` (+ detail / per-pair figures) for one run."""
    started = time.perf_counter()
    data = load_display_data(routes_path, config_path, run_dir,
                             sagitta_mm=display_sagitta_mm)
    run_dir = data["run_dir"]
    config = data["config"]
    routed = data["routed"]
    curves = data["curves"]
    meta = data["meta"]
    connectors = data["connectors"]
    routes_meta = data["routes_meta"]
    routed_count = len(routed)
    if routed_count == 0:
        raise SystemExit(f"plots: no routed geometry in {routes_path}")
    statistics = statistics if statistics is not None else (
        _load_json(statistics_path or _stats_path(run_dir))
        if Path(statistics_path or _stats_path(run_dir)).exists() else None)
    label = experiment or _experiment_label(config, run_dir, statistics)
    rate = routed_count / TOTAL_CONNECTIONS
    crossing_count = _statistics_value(statistics, "crossing_count")
    mean_length = _statistics_value(statistics, "mean_length_mm")
    topology = config.get("topology") or "?"
    algorithm = config.get("algorithm") or "?"
    pair_counts = {}
    for record in routed:
        pair = record.get("pair") or _pair_of(record)
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
    title = (f"{label} | {routed_count}/{TOTAL_CONNECTIONS} routed "
             f"({rate:.2%})")
    subtitle_parts = [
        f"topology {topology} | algorithm {algorithm}",
        f"150 x 150 mm | single layer 0 | width {config.get('width_mm'):g} mm",
    ]
    if crossing_count is not None:
        subtitle_parts.append(f"crossings {int(crossing_count)}")
    if mean_length is not None:
        subtitle_parts.append(f"mean length {float(mean_length):.2f} mm")
    subtitle_parts.append(
        "pair counts " + ", ".join(f"{pair} {pair_counts.get(pair, 0)}"
                                   for pair in PAIR_ORDER))
    subtitle = "\n".join(subtitle_parts)
    files = {}
    routing_all = run_dir / "routing_all.png"
    info = plot_routes(curves, meta, list(curves.keys()), connectors,
                       routing_all, title, subtitle)
    info.update({"kind": "routing_all", "experiment": label,
                 "routed_count": routed_count, "total": TOTAL_CONNECTIONS})
    files["routing_all_png"] = info
    if verbose:
        print(f"[plots] {routing_all} routes={info['routes']}")

    audit = None
    crossings = []
    if with_detail:
        audit, crossings = _crossings_for_detail(routed, config)
        densest_cells = audit.get("densest_crossing_cells") or []
        if crossings:
            detail_path = run_dir / "routing_detail.png"
            detail_info = plot_detail(curves, meta, crossings, detail_path,
                                      routed_count, TOTAL_CONNECTIONS,
                                      densest_cells)
            detail_info.update({"kind": "routing_detail", "experiment": label,
                                "routed_count": routed_count,
                                "total": TOTAL_CONNECTIONS,
                                "crossing_count": len(crossings)})
            files["routing_detail_png"] = detail_info
            if verbose:
                print(f"[plots] {detail_path} hotspots="
                      f"{detail_info.get('hotspots')}")

    if by_pair:
        for pair in PAIR_ORDER:
            ids = [record["route_id"] for record in routed
                   if (record.get("pair") or _pair_of(record)) == pair]
            if not ids:
                continue
            pair_path = run_dir / f"by_pair_{pair}.png"
            pair_info = plot_routes(
                curves, meta, ids, connectors, pair_path,
                f"{label} | side pair {pair} | {len(ids)}/{TOTAL_CONNECTIONS} routed",
                (f"{routed_count}/{TOTAL_CONNECTIONS} routed in total | "
                 f"150 x 150 mm | layer 0 | fixed palette/limits/linewidth"))
            pair_info.update({"kind": f"by_pair_{pair}", "experiment": label,
                              "pair": pair, "pair_routed_count": len(ids),
                              "routed_count": routed_count,
                              "total": TOTAL_CONNECTIONS})
            files[f"by_pair_{pair}_png"] = pair_info
            if verbose:
                print(f"[plots] {pair_path} routes={pair_info['routes']}")

    summary = _json_safe({
        "schema": SCHEMA,
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "experiment": label,
        "run_dir": str(run_dir),
        "routes_json": str(routes_path),
        "statistics_json": (str(statistics_path) if statistics_path
                            else (str(_stats_path(run_dir))
                                  if _stats_path(run_dir).exists() else None)),
        "statistics_used": statistics is not None,
        "routed_count": routed_count,
        "total": TOTAL_CONNECTIONS,
        "routing_rate": rate,
        "pair_counts": pair_counts,
        "crossing_count": (len(crossings) if crossings else crossing_count),
        "topology": topology,
        "algorithm": algorithm,
        "style": {
            "board_mm": BOARD_MM,
            "display_sagitta_mm": display_sagitta_mm,
            "dpi": DPI,
            "figsize_routing": [11.0, 10.0],
            "coordinate_limits": [-9.0, BOARD_MM + 9.0],
            "palette": "four_side_1024.outputs.COLORS (fixed by side pair)",
            "linewidth": "0.4 - 0.55 (d56 default policy)",
        },
        "files": files,
        "wall_seconds": time.perf_counter() - started,
    })
    return summary


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Render per-experiment routing figures (SPEC §6).")
    parser.add_argument("--routes", help="path to <run>/routes.json")
    parser.add_argument("--config", help="path to <run>/config.json")
    parser.add_argument("--run-dir", help="run directory; infers routes/config/stats")
    parser.add_argument("--stats", help="statistics.json path (default: run dir copy)")
    parser.add_argument("--experiment", help="experiment label override")
    parser.add_argument("--by-pair", action="store_true",
                        help="also render one figure per side pair")
    parser.add_argument("--no-detail", action="store_true",
                        help="skip the hotspot detail figure")
    parser.add_argument("--sagitta", type=float, default=DISPLAY_SAGITTA_MM,
                        help="display chord sagitta in mm (presentation only)")
    parser.add_argument("--verbose", action="store_true", help="echo progress")
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
        raise SystemExit("plots: --routes or --run-dir is required")
    run_dir_path = Path(run_dir) if run_dir is not None else Path(routes_path).parent
    summary = render_experiment(
        routes_path=routes_path, config_path=config_path, run_dir=run_dir_path,
        statistics_path=args.stats, experiment=args.experiment,
        by_pair=args.by_pair, with_detail=not args.no_detail,
        display_sagitta_mm=args.sagitta, verbose=args.verbose)
    print(json.dumps({
        "experiment": summary["experiment"],
        "routed": summary["routed_count"],
        "total": summary["total"],
        "files": sorted(summary["files"]),
        "wall_seconds": round(summary["wall_seconds"], 3),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
