"""pytest suite for the FSLW R=40 mm / 30 µm metrics + GDS pipeline.

Golden checks run against the real pilot plane run when it exists under
``outputs/four_side_1024_fslw_R40_gap30_abcd/planes/``; the unit tests build
small synthetic plane runs in ``tmp_path`` so the loss formula, detour/quality
math, crossing/spacing recomputation, GDS layer contract and the combined
1024-channel artefact can be verified without the router.

Run from the project root::

    .venv\\Scripts\\python.exe -m pytest four_side_1024/fslw/tests_fslw -v
"""
from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
FSLW_OUTPUTS = ROOT / "outputs" / "four_side_1024_fslw_R40_gap30_abcd"

PLANE_TOTAL = 512
COMBINED_TOTAL = 1024
PAIR_COUNTS = {"z1": {"NS": 256, "EW": 256},
               "z2": {"EN": 128, "ES": 128, "SW": 128, "NW": 128}}
PAIR_ORDER = ("NS", "EW", "EN", "ES", "SW", "NW")


# ---------------------------------------------------------------------------
# synthetic plane fixture builders
# ---------------------------------------------------------------------------
def _line(p0, p1):
    return {"kind": "line", "p0": [float(p0[0]), float(p0[1])],
            "p1": [float(p1[0]), float(p1[1])], "layer": 0}


def _arc(center, radius, start_angle, sweep):
    center = [float(center[0]), float(center[1])]
    p0 = [center[0] + radius * math.cos(start_angle),
          center[1] + radius * math.sin(start_angle)]
    p1 = [center[0] + radius * math.cos(start_angle + sweep),
          center[1] + radius * math.sin(start_angle + sweep)]
    return {"kind": "arc", "p0": p0, "p1": p1, "center": center,
            "radius": float(radius), "start_angle": float(start_angle),
            "sweep": float(sweep), "layer": 0}


def _route_records(plane, routed_geometries=()):
    """512 identities for one plane; only the given route_ids get geometry."""
    geometry_by_id = {route_id: primitives
                      for route_id, primitives in routed_geometries}
    records = []
    pair_order = list(PAIR_COUNTS[plane].items())
    route_id = 1 if plane == "z1" else 513
    for pair, count in pair_order:
        relation = "opposite" if pair in ("NS", "EW") else "adjacent"
        for _ in range(count):
            primitives = geometry_by_id.get(route_id)
            record = {
                "route_id": route_id,
                "relation": relation,
                "pair": pair,
                "source_side": pair[0],
                "target_side": pair[1],
                "source_endpoint": f"DEV-{plane}-S{route_id}",
                "target_endpoint": f"DEV-{plane}-T{route_id}",
                "plane": plane,
                "z_mm": 0.0 if plane == "z1" else 0.5,
            }
            if primitives:
                record.update(status="routed", layer=0,
                              primitives=primitives,
                              length_mm=sum(_length([item])
                                            for item in primitives),
                              bend_count=sum(1 for item in primitives
                                             if item["kind"] == "arc"))
            else:
                record.update(status="failed", reason="synthetic_not_routed",
                              evaluated=0)
            records.append(record)
            route_id += 1
    return records


def _length(primitives):
    total = 0.0
    for primitive in primitives:
        if primitive["kind"] == "line":
            total += math.hypot(primitive["p1"][0] - primitive["p0"][0],
                                primitive["p1"][1] - primitive["p0"][1])
        else:
            total += abs(primitive["sweep"]) * primitive["radius"]
    return total


def _write_plane(run_dir, plane, routed_geometries, process_overrides=None,
                 topology="DEV_SYNTHETIC"):
    from four_side_1024.fslw import config as fslw_config

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    process = fslw_config.process_record(**(process_overrides or {}))
    records = _route_records(plane, routed_geometries)
    payload = {
        "schema": "four_side_1024_d56_optimized_routes_v1",
        "experiment": f"{topology}_{plane}",
        "topology": topology,
        "algorithm": "B",
        "plane": plane,
        "z_mm": 0.0 if plane == "z1" else 0.5,
        "port_model": fslw_config.PORT_MODEL,
        "process": process,
        "units": "mm",
        "layer": 0,
        "routes": records,
    }
    (run_dir / "routes.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    config = {
        "experiment": f"{topology}_B_{plane}",
        "topology": topology,
        "algorithm": "B",
        "plane": plane,
        "z_mm": 0.0 if plane == "z1" else 0.5,
        "port_model": fslw_config.PORT_MODEL,
        "process": process,
        "budget": {"eval_budget": 1000, "time_budget_seconds": 60.0},
        "strategy": {"name": "synthetic"},
        "seed": 20261019,
    }
    (run_dir / "config.json").write_text(
        json.dumps(config, indent=1, ensure_ascii=False), encoding="utf-8")
    return run_dir


def _write_audit(run_dir, routed_count):
    audit = {
        "passed": True,
        "policy_used": "strict",
        "policy": "strict",
        "route_count": PLANE_TOTAL,
        "routed_count": routed_count,
        "d56_checked_count": routed_count,
        "d56_passed_count": routed_count,
        "d56_failed_count": 0,
        "crossing_count": 0,
        "crossing_pair_count": 0,
        "crossing_angle_histogram": {},
        "small_angle_crossing_count": 0,
        "spacing_violation_pairs": 0,
        "overlap_pairs": 0,
        "touch_pairs": 0,
        "crossing_zone_overlap_pairs": 0,
        "crossing_window_overlap_pairs": 0,
        "double_cross_pairs": 0,
        "crossing_window_excessive_pairs": 0,
        "violation_pair_count": 0,
        "violations": [],
        "errors": [],
        "warnings": [],
    }
    (Path(run_dir) / "audit_strict.json").write_text(
        json.dumps(audit, indent=1, ensure_ascii=False), encoding="utf-8")
    return audit


@pytest.fixture(scope="module")
def fslw_metrics():
    from four_side_1024.fslw import metrics
    return metrics


@pytest.fixture(scope="module")
def fslw_plots():
    from four_side_1024.fslw import plots
    return plots


@pytest.fixture(scope="module")
def fslw_combine():
    from four_side_1024.fslw import combine
    return combine


@pytest.fixture(scope="module")
def fslw_compare():
    from four_side_1024.fslw import compare
    return compare


# ---------------------------------------------------------------------------
# propagation-loss formula / unknown-arm presentation (SPEC §6/§7)
# ---------------------------------------------------------------------------
def test_propagation_loss_formula(tmp_path, fslw_metrics):
    geometries = [
        (1, [_line((10, 10), (110, 10))]),             # 100 mm = 10 cm -> 0.5 dB
        (2, [_line((10, 20), (210, 20))]),             # 200 mm = 20 cm -> 1.0 dB
        (3, [_line((10, 30), (60, 30))]),              # 50 mm = 5 cm -> 0.25 dB
    ]
    run_dir = _write_plane(tmp_path / "z1", "z1", geometries)
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    loss = statistics["propagation_loss"]
    assert loss["status"] == "computed_from_analytic_lengths"
    assert loss["formula"] == "Lprop_dB = propagation_loss_db_per_cm * length_cm"
    assert loss["db_per_cm"] == pytest.approx(0.05)
    assert loss["total_length_cm"] == pytest.approx((100 + 200 + 50) / 10.0)
    assert loss["total_db"] == pytest.approx(0.05 * 35.0)
    assert loss["mean_db"] == pytest.approx((0.5 + 1.0 + 0.25) / 3.0)
    assert loss["max_db"] == pytest.approx(1.0)
    assert loss["min_db"] == pytest.approx(0.25)
    assert sum(loss["histogram"].values()) == 3
    breakdown = statistics["optical_loss_breakdown"]
    for arm in ("bend_loss", "crossing_loss"):
        assert breakdown[arm]["status"] == "unknown_uncalibrated"
        assert breakdown[arm]["value_db"] is None
    assert breakdown["total_optical_loss"]["status"] == (
        "not_computable_missing_calibration")
    assert breakdown["total_optical_loss"]["value_db"] is None
    assert "propagation" in breakdown["total_optical_loss"]["components_known"]
    assert set(breakdown["total_optical_loss"]["components_unknown"]) == {
        "bend", "crossing"}
    assert breakdown["legacy_arm"]["included"] is False


def test_propagation_loss_no_routed_routes(tmp_path, fslw_metrics):
    run_dir = _write_plane(tmp_path / "z1", "z1", [])
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["routed"] == 0
    assert statistics["propagation_loss"]["status"] == "no_routed_routes"
    assert statistics["propagation_loss"]["total_db"] is None
    assert statistics["optical_loss_breakdown"]["bend_loss"]["status"] == (
        "unknown_uncalibrated")


# ---------------------------------------------------------------------------
# straightness / turns / detour unit maths
# ---------------------------------------------------------------------------
def test_straight_fraction_horizontal_vertical_split(tmp_path, fslw_metrics):
    geometries = [
        (1, [_line((10, 10), (70, 10)), _line((70, 10), (70, 50))]),
    ]
    run_dir = _write_plane(tmp_path / "z1", "z1", geometries)
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["total_length_mm"] == pytest.approx(100.0)
    assert statistics["mean_straight_fraction"] == pytest.approx(1.0)
    assert statistics["horizontal_straight_fraction"] == pytest.approx(0.6)
    assert statistics["vertical_straight_fraction"] == pytest.approx(0.4)
    assert statistics["mean_horizontal_straight_fraction"] == pytest.approx(0.6)
    assert statistics["mean_vertical_straight_fraction"] == pytest.approx(0.4)
    assert statistics["mean_arc_fraction"] == pytest.approx(0.0)
    assert statistics["mean_bend_count"] == pytest.approx(0.0)
    assert statistics["total_bends"] == 0


def test_turns_and_unnecessary_detour(tmp_path, fslw_metrics):
    geometries = [
        # L path: manhattan == length -> detour 0, euclidean 50 mm lower -> 20 mm
        (1, [_line((10, 10), (40, 10)), _line((40, 10), (40, 50))]),
        # Z path: manhattan 30 mm, length 70 mm -> detour 40 mm
        (2, [_line((10, 60), (10, 80)), _line((10, 80), (40, 80)),
             _line((40, 80), (40, 60))]),
    ]
    run_dir = _write_plane(tmp_path / "z1", "z1", geometries)
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["mean_bend_count"] == pytest.approx(0.0)
    assert statistics["mean_turns"] == pytest.approx(0.0)
    assert statistics["mean_length_mm"] == pytest.approx(70.0)
    detours = statistics["geometry_checks"]
    assert detours["mean_unnecessary_detour_mm"] == pytest.approx(20.0)
    assert detours["total_unnecessary_detour_mm"] == pytest.approx(40.0)
    # euclidean-based detour: route 1: 70-50=20, route 2: 70-30=40 -> mean 30
    assert detours["mean_unnecessary_detour_vs_euclidean_mm"] == pytest.approx(30.0)
    assert detours["routes_below_manhattan_bound_count"] == 0


def test_arc_shorter_than_manhattan_is_documented_not_an_error(tmp_path,
                                                              fslw_metrics):
    # quarter arc R=40 from (10,10) to (50,50): length 20*pi ~ 62.83 mm,
    # Manhattan bound 80 mm -> negative Manhattan-based detour is expected.
    geometries = [(1, [_arc((10, 50), 40.0, -math.pi / 2.0, math.pi / 2.0)])]
    run_dir = _write_plane(tmp_path / "z1", "z1", geometries)
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    geometry = statistics["geometry_checks"]
    assert geometry["routes_below_manhattan_bound_count"] == 1
    assert geometry["mean_unnecessary_detour_mm"] < 0
    assert geometry["mean_unnecessary_detour_vs_euclidean_mm"] >= 0
    assert "may be slightly negative" in geometry["detour_note"]


def test_arc_radius_violation_at_r40(tmp_path, fslw_metrics):
    wrong_radius = [_arc((10, 50), 30.0, -math.pi / 2.0, math.pi / 2.0)]
    right_radius = [_arc((100, 100), 40.0, math.pi, math.pi / 2.0)]
    run_dir = _write_plane(tmp_path / "z1", "z1",
                           [(1, wrong_radius), (2, right_radius)])
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["radius_violations"] == 1
    assert statistics["geometry_checks"]["num_arcs_total"] == 2
    assert statistics["geometry_checks"]["min_arc_radius_mm"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# crossing / spacing recomputation at clearance 0.08 mm
# ---------------------------------------------------------------------------
def test_crossing_recompute_at_008_clearance(tmp_path, fslw_metrics):
    geometries = [
        (1, [_line((10, 75), (140, 75))]),
        (2, [_line((75, 10), (75, 140))]),
    ]
    run_dir = _write_plane(tmp_path / "z1", "z1", geometries)
    payload, meta, records, routed, failed = fslw_metrics.load_routes(
        run_dir / "routes.json")
    process = fslw_metrics.load_process(meta, json.loads(
        (run_dir / "config.json").read_text(encoding="utf-8")), run_dir)
    audit = fslw_metrics.compute_pair_audit(routed, process)
    assert audit["crossing_count"] == 1
    assert audit["crossing_angle_histogram"]["75-90"] == 1
    assert audit["spacing_violation_pairs"] == 0
    assert audit["clearance_mm"] == pytest.approx(0.08)


def test_spacing_violation_threshold_at_008(tmp_path, fslw_metrics):
    # two parallel horizontal lines 0.05 mm apart -> violation at 0.08
    bad = [(1, [_line((10, 75), (140, 75))]),
           (2, [_line((10, 75.05), (140, 75.05))])]
    run_bad = _write_plane(tmp_path / "bad" / "z1", "z1", bad)
    payload, meta, records, routed, failed = fslw_metrics.load_routes(
        run_bad / "routes.json")
    process = fslw_metrics.load_process(meta, json.loads(
        (run_bad / "config.json").read_text(encoding="utf-8")), run_bad)
    audit_bad = fslw_metrics.compute_pair_audit(routed, process)
    assert audit_bad["spacing_violation_pairs"] == 1
    # 0.10 mm apart -> legal at 0.08 clearance
    ok = [(1, [_line((10, 75), (140, 75))]),
          (2, [_line((10, 75.10), (140, 75.10))])]
    run_ok = _write_plane(tmp_path / "ok" / "z1", "z1", ok)
    payload, meta, records, routed, failed = fslw_metrics.load_routes(
        run_ok / "routes.json")
    process = fslw_metrics.load_process(meta, json.loads(
        (run_ok / "config.json").read_text(encoding="utf-8")), run_ok)
    audit_ok = fslw_metrics.compute_pair_audit(routed, process)
    assert audit_ok["spacing_violation_pairs"] == 0


# ---------------------------------------------------------------------------
# full plane statistics contract + audit merge
# ---------------------------------------------------------------------------
def test_plane_statistics_required_fields_and_sources(tmp_path, fslw_metrics):
    geometries = [(route_id, [_line((10, 10 + route_id), (110, 10 + route_id))])
                  for route_id in range(1, 11)]
    run_dir = _write_plane(tmp_path / "z1", "z1", geometries)
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    for name in fslw_metrics.PLANE_REQUIRED_METRICS:
        assert name in statistics, name
    assert statistics["scope"] == "plane"
    assert statistics["plane"] == "z1"
    assert statistics["connections_total"] == PLANE_TOTAL
    assert statistics["routed"] == 10
    assert statistics["unrouted"] == PLANE_TOTAL - 10
    assert statistics["routing_rate"] == pytest.approx(10 / PLANE_TOTAL)
    assert statistics["by_pair"]["NS"]["total"] == 256
    assert statistics["by_pair"]["EW"]["total"] == 256
    assert statistics["mean_length_mm"] == pytest.approx(100.0)
    assert statistics["total_length_mm"] == pytest.approx(1000.0)
    assert statistics["propagation_loss"]["total_db"] == pytest.approx(5.0)
    assert statistics["source"]["audit"]["status"] == "missing"
    assert "audit_strict.json not merged" in " ".join(statistics["notes"])
    assert statistics["spacing_violation_pairs_source"] == (
        "recomputed_from_primitives")
    assert statistics["total_violation_count"] == 0
    assert statistics["pair_count_check"]["NS"]["matches"] is True
    # no NaN / infinite numbers anywhere in the JSON payload
    problems = []

    def walk(value, path="statistics"):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, bool):
            return
        elif isinstance(value, (int, float)):
            if math.isnan(float(value)) or math.isinf(float(value)):
                problems.append(path)

    walk(statistics)
    assert not problems, problems[:10]


def test_plane_audit_merge_and_stale_guard(tmp_path, fslw_metrics):
    geometries = [(1, [_line((10, 10), (110, 10))])]
    run_dir = _write_plane(tmp_path / "z1", "z1", geometries)
    # stale audit (older mtime) must be ignored
    _write_audit(run_dir, routed_count=1)
    routes_path = run_dir / "routes.json"
    import os
    import time as _time
    past = _time.time() - 3600
    os.utime(run_dir / "audit_strict.json", (past, past))
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["source"]["audit"]["status"] == "stale_ignored"
    assert statistics["audit_passed"] is None
    assert any("ignored audit file" in note for note in statistics["notes"])
    # fresh audit is merged as authoritative
    newer = _time.time() + 5
    os.utime(run_dir / "audit_strict.json", (newer, newer))
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["source"]["audit"]["status"] == "merged"
    assert statistics["audit_passed"] is True
    assert statistics["audit_policy"] == "strict"
    assert statistics["spacing_violation_pairs_source"].startswith("audit_strict")


# ---------------------------------------------------------------------------
# GDS layer contracts
# ---------------------------------------------------------------------------
def test_plane_gds_is_single_layer_zero(tmp_path, fslw_plots):
    gdspy = pytest.importorskip("gdspy")
    geometries = [(route_id, [_line((10, 10 + route_id), (110, 10 + route_id))])
                  for route_id in range(1, 6)]
    run_dir = _write_plane(tmp_path / "z1", "z1", geometries)
    summary = fslw_plots.render_plane(
        run_dir, with_detail=False, with_heatmap=False, with_radius=False,
        with_congestion=False, with_svg_gds=True)
    gds_path = run_dir / "routing_all.gds"
    svg_path = run_dir / "routing_all.svg"
    assert gds_path.exists()
    assert svg_path.exists()
    library = gdspy.GdsLibrary(infile=str(gds_path))
    tops = library.top_level()
    paths = list(tops[0].paths) if tops else []
    layers = sorted({int(layer) for item in paths for layer in item.layers})
    assert layers == [0]
    assert len(paths) == 5
    assert svg_path.stat().st_size < 5 * 1024 * 1024
    ET.parse(svg_path)
    assert summary["routed_count"] == 5
    assert summary["total"] == PLANE_TOTAL


def test_combined_gds_layers_z1_z2(tmp_path, fslw_combine):
    gdspy = pytest.importorskip("gdspy")
    root = tmp_path / "outputs"
    z1_geometries = [(route_id, [_line((10, 10 + route_id), (110, 10 + route_id))])
                     for route_id in range(1, 5)]
    z2_geometries = [(route_id, [_line((10, 10 + route_id), (90, 10 + route_id))])
                     for route_id in range(513, 516)]
    _write_plane(root / "planes" / "V1" / "B" / "z1", "z1", z1_geometries)
    _write_plane(root / "planes" / "V1" / "B" / "z2", "z2", z2_geometries)
    combined_dir = fslw_combine.build_combined(root, "V1", "B", quiet=True)
    gds_path = combined_dir / "routing_1024_two_height.gds"
    library = gdspy.GdsLibrary(infile=str(gds_path))
    tops = library.top_level()
    paths = list(tops[0].paths) if tops else []
    layers = sorted({int(layer) for item in paths for layer in item.layers})
    assert layers == [0, 1], (
        "combined GDS must be layer 0 = z1, layer 1 = z2 (two physical heights)")
    per_layer = {}
    for layer in layers:
        per_layer[layer] = sum(
            1 for item in paths if any(int(value) == layer for value in item.layers))
    assert per_layer[0] == 4
    assert per_layer[1] == 3
    routes_path = combined_dir / "routes_1024.json"
    payload = json.loads(routes_path.read_text(encoding="utf-8"))
    assert len(payload["routes"]) == COMBINED_TOTAL
    planes = [record.get("plane") for record in payload["routes"]]
    assert planes.count("z1") == PLANE_TOTAL
    assert planes.count("z2") == PLANE_TOTAL
    assert all(record.get("z_mm") in (0.0, 0.5) for record in payload["routes"])
    combined = payload["statistics"]["combined"]
    assert combined["routed"] == 7
    assert combined["by_plane"]["z1"]["routed"] == 4
    assert combined["by_plane"]["z2"]["routed"] == 3
    assert combined["routing_rate"] == pytest.approx(7 / COMBINED_TOTAL)
    projection = combined["cross_plane_projected_overlap"]
    assert projection["status"] == "informational_only"
    assert projection["not_a_violation"] is True
    assert combined["violations"]["cross_plane"]["value"] == 0
    # combined loss: propagation known, bend/crossing unknown
    assert combined["optical_loss_breakdown"]["bend_loss"]["status"] == (
        "unknown_uncalibrated")
    assert combined["optical_loss_breakdown"]["total_optical_loss"]["status"] == (
        "not_computable_missing_calibration")
    # combined figures exist
    for name in ("layer_2d.png", "layer_2d.svg", "overlay_3d.png",
                 "planes_summary.json", "statistics.json"):
        assert (combined_dir / name).exists(), name
    summary = json.loads((combined_dir / "planes_summary.json").read_text(
        encoding="utf-8"))
    gds_note = json.dumps(summary["gds"], ensure_ascii=False)
    assert "layer 0 = plane z1" in gds_note
    assert "layer 1 = plane z2" in gds_note


# ---------------------------------------------------------------------------
# comparison pipeline smoke test (synthetic 1 group)
# ---------------------------------------------------------------------------
def test_compare_pipeline_smoke(tmp_path, fslw_combine, fslw_compare):
    root = tmp_path / "outputs"
    _write_plane(root / "planes" / "V1" / "B" / "z1", "z1",
                 [(route_id, [_line((10, 10 + route_id), (110, 10 + route_id))])
                  for route_id in range(1, 5)])
    _write_plane(root / "planes" / "V1" / "B" / "z2", "z2",
                 [(route_id, [_line((10, 10 + route_id), (90, 10 + route_id))])
                  for route_id in range(513, 516)])
    fslw_combine.build_combined(root, "V1", "B", quiet=True)
    result = fslw_compare.build_comparison(root, recompute=False, quiet=True)
    comparison = root / "comparison"
    for name in ("all_metrics.csv", "all_metrics.json",
                 "strict_audit_summary_metrics.json", "eight_group_routed.png",
                 "layer_2d_compare.png", "crossing_heatmap_compare.png",
                 "radius_check_all.png", "plane_routed_compare.png",
                 "metric_bars_routed.png"):
        path = comparison / name
        assert path.exists(), name
        if path.suffix == ".png":
            assert path.stat().st_size > 10_000, name
    payload = json.loads((comparison / "all_metrics.json").read_text(
        encoding="utf-8"))
    scopes = [row["scope"] for row in payload["experiments"]]
    assert scopes.count("plane") == 2
    assert scopes.count("combined") == 1
    for row in payload["experiments"]:
        if row["scope"] == "plane":
            assert row["routed"] is not None
        if row["scope"] == "combined":
            assert row["routed"] == 7
            assert row["same_plane_crossings"] is not None


# ---------------------------------------------------------------------------
# golden checks on the real pilot plane run when it exists
# ---------------------------------------------------------------------------
def _first_real_plane_run():
    if not FSLW_OUTPUTS.exists():
        return None
    planes_root = FSLW_OUTPUTS / "planes"
    if not planes_root.exists():
        return None
    for path in sorted(planes_root.glob("*/*/*/routes.json")):
        return path.parent
    return None


def test_real_pilot_plane_run_matches_audit():
    run_dir = _first_real_plane_run()
    if run_dir is None:
        pytest.skip("no real FSLW pilot plane run yet")
    from four_side_1024.fslw import metrics as fslw_metrics

    routes_path = run_dir / "routes.json"
    payload, meta, records, routed, failed = fslw_metrics.load_routes(routes_path)
    assert len(records) == PLANE_TOTAL
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["routed"] == len(routed)
    assert statistics["routed"] + statistics["unrouted"] == PLANE_TOTAL
    assert statistics["connections_total"] == PLANE_TOTAL
    geometry = statistics["length"]
    total_length = geometry["total_length_mm"] or 0.0
    propagation = statistics["propagation_loss"]
    if statistics["routed"]:
        assert propagation["total_length_cm"] == pytest.approx(total_length / 10.0)
        assert propagation["total_db"] == pytest.approx(0.05 * total_length / 10.0)
        assert statistics["optical_loss_breakdown"]["bend_loss"]["status"] == (
            "unknown_uncalibrated")
        assert statistics["optical_loss_breakdown"]["total_optical_loss"][
            "status"] == "not_computable_missing_calibration"
    audit_path = run_dir / "audit_strict.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if statistics["source"]["audit"]["status"] == "merged":
            assert statistics["audit_passed"] == audit.get("passed")
            if statistics["audit_routed_count"] is not None:
                assert statistics["audit_routed_count"] == statistics["routed"]
    # plane must be one of the two model heights
    assert statistics["plane"] in ("z1", "z2")
    assert statistics["z_mm"] == pytest.approx(
        0.0 if statistics["plane"] == "z1" else 0.5)
    # no NaN in the numeric payload
    problems = []

    def walk(value, path="statistics"):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if math.isnan(float(value)) or math.isinf(float(value)):
                problems.append(path)

    walk(statistics)
    assert not problems, problems[:10]


def test_cli_metrics_run_dir(tmp_path, fslw_metrics):
    run_dir = _write_plane(tmp_path / "z1", "z1",
                           [(1, [_line((10, 10), (110, 10))])])
    exit_code = fslw_metrics.main(["--run-dir", str(run_dir), "--quiet"])
    assert exit_code == 0
    statistics_path = run_dir / "statistics.json"
    assert statistics_path.exists()
    payload = json.loads(statistics_path.read_text(encoding="utf-8"))
    assert payload["schema"] == fslw_metrics.SCHEMA_PLANE
    assert payload["routed"] == 1
