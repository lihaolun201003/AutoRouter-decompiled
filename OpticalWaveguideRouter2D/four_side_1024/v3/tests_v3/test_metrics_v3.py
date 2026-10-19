"""pytest suite for the V3-Huang metrics / shape / GDS / combined pipeline.

Golden checks run against the real V3 plane pilot when it exists under
``outputs/four_side_1024_v3_huang_R40_gap30_abcd/planes/``; unit tests build
synthetic V3 plane runs in ``tmp_path`` so the shape classifier, U depth/track/
nesting/adjacency statistics, failure taxonomy, loss formula, GDS layer contract
and the 1024-channel combined artefact can be verified without the router.

Run from the project root::

    .venv\\Scripts\\python.exe -m pytest four_side_1024/v3/tests_v3 -v
"""
from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
V3_OUTPUTS = ROOT / "outputs" / "four_side_1024_v3_huang_R40_gap30_abcd"
PLANE_TOTAL = 512
COMBINED_TOTAL = 1024
PAIR_ORDER = ("NN", "SS", "EE", "WW", "NS", "EW", "NE", "NW", "ES", "SW")


# ---------------------------------------------------------------------------
# primitive builders (world-mm D56 family, R=40)
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


def _straight(p0, p1):
    return [_line(p0, p1)]


def _l_route(start=(10.0, 10.0), length=60.0, radius=40.0):
    """Vertical up, quarter arc to the right, horizontal (L shape)."""
    x, y = start
    return [
        _line((x, y), (x, y + length)),
        _arc((x + radius, y + length), radius, math.pi, math.pi / 2.0),
        _line((x + radius, y + length + radius),
              (x + radius + 20.0, y + length + radius)),
    ]


def _u_route_width(start=(20.0, 150.0), depth=70.0, width=100.0,
                   radius=40.0):
    """Wide U on the N side: down, quarter turn, track, quarter turn, up."""
    x, y = start
    track_y = y - depth
    return [
        _line((x, y), (x, track_y + radius)),
        _arc((x + radius, track_y + radius), radius, math.pi, math.pi / 2.0),
        _line((x + radius, track_y), (x + width - radius, track_y)),
        _arc((x + width - radius, track_y + radius), radius, -math.pi / 2.0,
             math.pi / 2.0),
        _line((x + width, track_y + radius), (x + width, y)),
    ]


def _hairpin_route(start=(30.0, 150.0), depth=40.0, radius=40.0):
    """Consecutive quarter arcs (no straight between) forming a 180 deg hairpin."""
    x, y = start
    h = y - depth
    return [
        _line((x, y), (x, h)),
        _arc((x + radius, h), radius, math.pi, math.pi / 2.0),
        _arc((x + radius, h), radius, -math.pi / 2.0, math.pi / 2.0),
        _line((x + 2 * radius, h), (x + 2 * radius, y)),
    ]


def _short_s_route(start=(10.0, 20.0), radius=40.0, lateral=40.0):
    """Historical short-S pair: two reverse theta arcs with d = 2R(1-cos theta)."""
    theta = math.acos(max(-1.0, min(1.0, 1.0 - lateral / (2.0 * radius))))
    x, y = start
    # first arc turns left by +theta (heading starts at +x)
    center1 = (x, y + radius)
    arc1 = _arc(center1, radius, -math.pi / 2.0, theta)
    heading = theta                      # tangent after the first arc
    point = arc1["p1"]
    # second arc turns back (-theta): right-hand normal of the heading
    right_normal = (math.sin(heading), -math.cos(heading))
    center2 = (point[0] + right_normal[0] * radius,
               point[1] + right_normal[1] * radius)
    start_angle2 = math.atan2(point[1] - center2[1], point[0] - center2[0])
    arc2 = _arc(center2, radius, start_angle2, -theta)
    return [arc1, arc2]


def _multi_bend_route(start=(10.0, 10.0), radius=40.0):
    """Three quarter arcs in a row (unambiguously multi-bend refold)."""
    x, y = start
    return [
        _line((x, y), (x, y + 40.0)),
        _arc((x + radius, y + 40.0), radius, math.pi, math.pi / 2.0),
        _line((x + radius, y + 40.0 - radius),
              (x + radius + 10.0, y + 40.0 - radius)),
        _arc((x + radius + 10.0, y + 40.0), radius, -math.pi / 2.0,
             math.pi / 2.0),
        _line((x + radius + 10.0 + radius, y + 40.0),
              (x + radius + 10.0 + radius, y + 60.0)),
        _arc((x + radius + 10.0, y + 60.0), radius, 0.0, math.pi / 2.0),
        _line((x + radius + 10.0, y + 60.0 + radius),
              (x + radius - 10.0, y + 60.0 + radius)),
    ]


# ---------------------------------------------------------------------------
# synthetic plane run builders
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def v3_metrics():
    from four_side_1024.v3 import metrics
    return metrics


@pytest.fixture(scope="module")
def v3_plots():
    from four_side_1024.v3 import plots
    return plots


@pytest.fixture(scope="module")
def v3_combine():
    from four_side_1024.v3 import combine
    return combine


@pytest.fixture(scope="module")
def v3_compare():
    from four_side_1024.v3 import compare
    return compare


@pytest.fixture(scope="module")
def v3_ports():
    from four_side_1024.v3 import ports
    return ports


@pytest.fixture(scope="module")
def v3_config():
    from four_side_1024.v3 import config
    return config


def _synthetic_records(plane, v3_ports, v3_config):
    """All 512 identities of one plane with a small synthetic routed subset."""
    routes, endpoints, connectors, validation = v3_ports.load_plane(plane)
    assignments = {}
    u_candidates = []
    l_candidates = []
    for route in routes:
        if route["relation"] == "same" and route["source_side"] == "N":
            x1 = endpoints[route["source_endpoint"]]["routing_xy"][0]
            x2 = endpoints[route["target_endpoint"]]["routing_xy"][0]
            delta = x2 - x1
            if 80.0 <= delta <= 140.0:
                u_candidates.append((route, delta))
        elif route["relation"] == "opposite":
            l_candidates.append(route)
    for route, delta in u_candidates[:3]:
        assignments[route["route_id"]] = ("U", delta)
    for route in l_candidates[:3]:
        assignments[route["route_id"]] = ("L", None)
    records = []
    for route in routes:
        record = {
            "route_id": route["route_id"],
            "plane": plane,
            "z_mm": 0.0 if plane == "z1" else 0.5,
            "relation": route["relation"],
            "pair": route["pair"],
            "source_side": route["source_side"],
            "target_side": route["target_side"],
            "source_row": route["source_row"],
            "target_row": route["target_row"],
            "source_endpoint": route["source_endpoint"],
            "target_endpoint": route["target_endpoint"],
        }
        assignment = assignments.get(route["route_id"])
        if assignment and assignment[0] == "U":
            x1 = endpoints[route["source_endpoint"]]["routing_xy"][0]
            primitives = _u_route_width((x1, 150.0), depth=70.0,
                                        width=assignment[1])
            record.update(status="routed", layer=0, primitives=primitives,
                          length_mm=sum(_primitive_length(p) for p in primitives),
                          bend_count=2,
                          candidate={"family": "SAME_U", "params": {}})
            records.append(record)
            continue
        if assignment and assignment[0] == "L":
            source = endpoints[route["source_endpoint"]]
            primitives = _l_route((source["routing_xy"][0], 20.0))
            record.update(status="routed", layer=0, primitives=primitives,
                          length_mm=sum(_primitive_length(p) for p in primitives),
                          bend_count=1,
                          candidate={"family": "opposite_L", "params": {}})
            records.append(record)
            continue
        record.update(status="failed",
                      reason="no_candidate_generated" if len(records) % 2 else
                             "no_legal_candidate",
                      evaluated=3, rejection_counts={}, blockers={})
        records.append(record)
    return records, endpoints, connectors, validation


def _primitive_length(primitive):
    if primitive["kind"] == "line":
        return math.hypot(primitive["p1"][0] - primitive["p0"][0],
                          primitive["p1"][1] - primitive["p0"][1])
    return abs(primitive["sweep"]) * primitive["radius"]


def _write_plane(root, algorithm, plane, v3_ports, v3_config,
                 process_overrides=None):
    run_dir = Path(root) / "planes" / algorithm / plane
    run_dir.mkdir(parents=True, exist_ok=True)
    process = v3_config.process_record(**(process_overrides or {}))
    records, endpoints, connectors, validation = _synthetic_records(
        plane, v3_ports, v3_config)
    payload = {
        "schema": "four_side_1024_v3_plane_routes_v1",
        "units": "mm",
        "layer": 0,
        "experiment": f"V3_{algorithm}_{plane}",
        "topology": v3_config.TOPOLOGY,
        "algorithm": algorithm,
        "plane": plane,
        "z_mm": 0.0 if plane == "z1" else 0.5,
        "port_model": v3_config.PORT_MODEL,
        "process": process,
        "plane_validation": validation,
        "routes": records,
    }
    (run_dir / "routes.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    config = {
        "experiment": f"V3_{algorithm}_{plane}",
        "topology": v3_config.TOPOLOGY,
        "algorithm": algorithm,
        "plane": plane,
        "z_mm": 0.0 if plane == "z1" else 0.5,
        "port_model": v3_config.PORT_MODEL,
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
        "passed": True, "policy_used": "strict", "policy": "strict",
        "route_count": PLANE_TOTAL, "routed_count": routed_count,
        "d56_checked_count": routed_count, "d56_passed_count": routed_count,
        "d56_failed_count": 0, "crossing_count": 0, "crossing_pair_count": 0,
        "crossing_angle_histogram": {}, "small_angle_crossing_count": 0,
        "spacing_violation_pairs": 0, "overlap_pairs": 0, "touch_pairs": 0,
        "crossing_window_overlap_pairs": 0, "double_cross_pairs": 0,
        "crossing_window_excessive_pairs": 0, "violation_pair_count": 0,
        "violations": [], "errors": [], "warnings": [],
        "same_side_checks": {"passed": True, "hairpin_violations": 0,
                             "tangent_out_violations": 0},
    }
    (Path(run_dir) / "audit_strict.json").write_text(
        json.dumps(audit, indent=1), encoding="utf-8")
    return audit


# ---------------------------------------------------------------------------
# shape classification units (primitives only)
# ---------------------------------------------------------------------------
def test_shape_classifier_families(v3_metrics):
    straight = _straight((10.0, 10.0), (60.0, 10.0))
    assert v3_metrics.classify_route(straight)["shape"] == "straight"
    l_route = _l_route()
    classified = v3_metrics.classify_route(l_route)
    assert classified["shape"] == "L"
    assert classified["subtype"] == "single_quarter"
    u_route = _u_route_width()
    classified = v3_metrics.classify_route(u_route)
    assert classified["shape"] == "U"
    assert classified["subtype"] == "wide_U"
    assert classified["arc_count"] == 2
    hairpin = _hairpin_route()
    classified = v3_metrics.classify_route(hairpin)
    assert classified["shape"] == "U"
    assert classified["hairpin"] is True
    assert classified["subtype"] == "hairpin"
    short_s = _short_s_route()
    classified = v3_metrics.classify_route(short_s)
    assert classified["short_s_pair_count"] == 1, classified
    assert classified["shape"] == "short_S", classified
    multi = _multi_bend_route()
    classified = v3_metrics.classify_route(multi)
    assert classified["shape"] == "multi_bend_refold", classified
    assert classified["arc_count"] >= 2
    # tampered geometry: diagonal line is 'other', never silently accepted as L
    diagonal = [_line((10.0, 10.0), (60.0, 40.0))]
    assert v3_metrics.classify_route(diagonal)["shape"] == "other"


def test_shape_classification_never_uses_relation_label(v3_metrics):
    u_route = _u_route_width()
    record_same = {"route_id": 1, "relation": "same", "pair": "NN",
                   "primitives": u_route}
    record_adjacent = {"route_id": 2, "relation": "adjacent", "pair": "NE",
                       "primitives": u_route}
    first = v3_metrics.classify_route(record_same["primitives"])
    second = v3_metrics.classify_route(record_adjacent["primitives"])
    assert first == second
    assert first["classification_source"] == "saved_primitives"


# ---------------------------------------------------------------------------
# synthetic plane statistics (class counts, shapes, U stats, failures, loss)
# ---------------------------------------------------------------------------
def test_synthetic_plane_statistics(tmp_path, v3_ports, v3_config, v3_metrics):
    root = Path(tmp_path) / "outputs"
    run_dir = _write_plane(root, "B", "z1", v3_ports, v3_config)
    statistics = v3_metrics.build_plane_statistics(run_dir, quiet=True)
    # identity / class contract
    assert statistics["connections_total"] == PLANE_TOTAL
    assert statistics["routed"] + statistics["unrouted"] == PLANE_TOTAL
    expected_plane = v3_config.EXPECTED["planes"]["z1"]
    for relation in ("same", "opposite", "adjacent"):
        assert statistics["by_class"][relation]["total"] == expected_plane[relation]
    assert statistics["same_side"]["total"] == 222
    assert statistics["topology_validation"]["passed"] is True
    # shape block is primitive-derived and sums to routed
    shapes = statistics["path_shapes"]["counts"]
    assert set(shapes) == set(v3_metrics.REQUIRED_SHAPES)
    assert sum(shapes.values()) == statistics["routed"]
    assert statistics["path_shapes"]["routed_total"] == statistics["routed"]
    assert shapes["U"] >= 1
    assert shapes["L"] >= 1
    # U statistics present and consistent with the U shape count
    u_statistics = statistics["u_statistics"]
    assert u_statistics["count"] == sum(
        1 for route in statistics["path_shapes"]["per_route"].values()
        if route["shape"] == "U" and route["relation"] == "same")
    assert u_statistics["depth_mm"]["histogram_5mm"]
    assert u_statistics["nesting"]["max_chain_length"] >= 1
    # failure taxonomy
    taxonomy = statistics["failure_taxonomy"]
    assert taxonomy["total_failed"] == statistics["unrouted"]
    assert set(taxonomy["counts"]) == {
        "no_candidate_generated", "no_legal_candidate", "budget_or_timeout",
        "not_attempted", "other"}
    # propagation loss exact formula
    propagation = statistics["propagation_loss"]
    assert propagation["total_db"] == pytest.approx(
        0.05 * statistics["total_length_mm"] / 10.0)
    assert statistics["optical_loss_breakdown"]["bend_loss"]["status"] == (
        "unknown_uncalibrated")
    assert statistics["optical_loss_breakdown"]["total_optical_loss"]["status"] == (
        "not_computable_missing_calibration")
    # no NaN / inf anywhere in the JSON payload
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


def test_plane_audit_merge_and_stale_guard(tmp_path, v3_ports, v3_config,
                                           v3_metrics):
    root = Path(tmp_path) / "outputs"
    run_dir = _write_plane(root, "A", "z1", v3_ports, v3_config)
    statistics = v3_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["source"]["audit"]["status"] == "missing"
    _write_audit(run_dir, statistics["routed"])
    import os
    import time as _time
    past = _time.time() - 3600
    os.utime(run_dir / "audit_strict.json", (past, past))
    statistics = v3_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["source"]["audit"]["status"] == "stale_ignored"
    newer = _time.time() + 5
    os.utime(run_dir / "audit_strict.json", (newer, newer))
    statistics = v3_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["source"]["audit"]["status"] == "merged"
    assert statistics["audit_passed"] is True
    assert statistics["spacing_violation_pairs_source"].startswith(
        "audit_strict")


def test_failure_taxonomy_classification(v3_metrics):
    failed = [
        {"route_id": 1, "relation": "same", "pair": "NN",
         "reason": "no_candidate_generated"},
        {"route_id": 2, "relation": "same", "pair": "SS",
         "reason": "no_legal_candidate"},
        {"route_id": 3, "relation": "opposite", "pair": "NS",
         "reason": "eval_budget_exhausted"},
        {"route_id": 4, "relation": "adjacent", "pair": "NE",
         "reason": "not_attempted"},
        {"route_id": 5, "relation": "adjacent", "pair": "SW",
         "reason": "weird_reason"},
    ]
    taxonomy = v3_metrics.compute_failure_taxonomy(failed)
    assert taxonomy["total_failed"] == 5
    assert taxonomy["counts"]["no_candidate_generated"] == 1
    assert taxonomy["counts"]["no_legal_candidate"] == 1
    assert taxonomy["counts"]["budget_or_timeout"] == 1
    assert taxonomy["counts"]["not_attempted"] == 1
    assert taxonomy["counts"]["other"] == 1
    assert taxonomy["by_class"]["same"]["no_candidate_generated"] == 1
    assert "no mathematical impossibility is claimed" in (
        taxonomy["honesty_interpretation"]["note"])


def test_shapes_aggregate_and_u_track_json(tmp_path, v3_ports, v3_config,
                                           v3_metrics):
    root = Path(tmp_path) / "outputs"
    _write_plane(root, "B", "z1", v3_ports, v3_config)
    _write_plane(root, "B", "z2", v3_ports, v3_config)
    payload = v3_metrics.build_shapes_statistics(root, quiet=True)
    assert payload["planes_measured"] == 2
    assert payload["aggregate"]["routed"] > 0
    assert (root / "shapes" / "same_side_statistics.json").exists()
    track_path = v3_metrics.build_u_track_statistics(root, quiet=True)
    assert Path(track_path).exists()
    track = json.loads(Path(track_path).read_text(encoding="utf-8"))
    assert track["planes_measured"] == 2
    assert "depth_mm" in track["aggregate"]
    assert "nesting_group_count" in track["aggregate"]


# ---------------------------------------------------------------------------
# GDS layer contracts
# ---------------------------------------------------------------------------
def test_plane_gds_single_layer(tmp_path, v3_ports, v3_config, v3_plots):
    gdspy = pytest.importorskip("gdspy")
    root = Path(tmp_path) / "outputs"
    run_dir = _write_plane(root, "B", "z1", v3_ports, v3_config)
    statistics = v3_metrics = None  # noqa: F841 - keep imports explicit
    from four_side_1024.v3 import metrics as v3_metrics
    statistics = v3_metrics.build_plane_statistics(run_dir, quiet=True)
    summary = v3_plots.render_plane(
        run_dir, statistics=statistics, with_detail=False, with_heatmap=False,
        with_radius=False, with_congestion=False, with_svg_gds=True)
    gds_path = run_dir / "routing_all.gds"
    svg_path = run_dir / "routing_all.svg"
    assert gds_path.exists() and svg_path.exists()
    library = gdspy.GdsLibrary(infile=str(gds_path))
    paths = list(library.top_level()[0].paths)
    layers = sorted({int(layer) for item in paths for layer in item.layers})
    assert layers == [0]
    assert len(paths) == statistics["routed"]
    assert svg_path.stat().st_size < 5 * 1024 * 1024
    ET.parse(svg_path)
    assert summary["routed_count"] == statistics["routed"]


def test_combined_artifacts(tmp_path, v3_ports, v3_config, v3_metrics,
                            v3_combine):
    gdspy = pytest.importorskip("gdspy")
    root = Path(tmp_path) / "outputs"
    _write_plane(root, "B", "z1", v3_ports, v3_config)
    _write_plane(root, "B", "z2", v3_ports, v3_config)
    combined_dir = v3_combine.build_combined(root, "B", quiet=True)
    routes_path = combined_dir / "routes_1024.json"
    payload = json.loads(routes_path.read_text(encoding="utf-8"))
    assert len(payload["routes"]) == COMBINED_TOTAL
    planes = [record.get("plane") for record in payload["routes"]]
    assert planes.count("z1") == PLANE_TOTAL
    assert planes.count("z2") == PLANE_TOTAL
    assert all(record.get("z_mm") in (0.0, 0.5) for record in payload["routes"])
    combined = payload["statistics"]["combined"]
    plane_z1 = payload["statistics"]["z1"]
    plane_z2 = payload["statistics"]["z2"]
    assert combined["routed"] == plane_z1["routed"] + plane_z2["routed"]
    assert combined["same_side"]["routed"] == (
        plane_z1["same_side"]["routed"] + plane_z2["same_side"]["routed"])
    assert "path_shapes" in combined and "u_statistics" in combined
    projection = combined["cross_plane_projected_overlap"]
    assert projection["status"] == "informational_only"
    assert projection["not_a_violation"] is True
    assert combined["violations"]["cross_plane"]["value"] == 0
    assert combined["optical_loss_breakdown"]["bend_loss"]["status"] == (
        "unknown_uncalibrated")
    assert combined["optical_loss_breakdown"]["total_optical_loss"]["status"] == (
        "not_computable_missing_calibration")
    gds_path = combined_dir / "routing_1024_two_height.gds"
    library = gdspy.GdsLibrary(infile=str(gds_path))
    paths = list(library.top_level()[0].paths)
    layers = sorted({int(layer) for item in paths for layer in item.layers})
    assert layers == [0, 1]
    per_layer = {}
    for layer in layers:
        per_layer[layer] = sum(1 for item in paths
                               if any(int(value) == layer for value in item.layers))
    assert per_layer[0] == plane_z1["routed"]
    assert per_layer[1] == plane_z2["routed"]
    for name in ("statistics.json", "planes_summary.json", "layer_2d.png",
                 "layer_2d.svg", "overlay_3d.png"):
        assert (combined_dir / name).exists(), name
    summary = json.loads((combined_dir / "planes_summary.json").read_text(
        encoding="utf-8"))
    gds_note = json.dumps(summary["gds"], ensure_ascii=False)
    assert "layer 0 = plane z1" in gds_note
    assert "layer 1 = plane z2" in gds_note


# ---------------------------------------------------------------------------
# comparison smoke test (one synthetic group)
# ---------------------------------------------------------------------------
def test_compare_pipeline_smoke(tmp_path, v3_ports, v3_config, v3_combine,
                                v3_compare):
    root = Path(tmp_path) / "outputs"
    for plane in ("z1", "z2"):
        _write_plane(root, "B", plane, v3_ports, v3_config)
    v3_combine.build_combined(root, "B", quiet=True)
    result = v3_compare.build_comparison(root, recompute=False, quiet=True)
    comparison = root / "comparison"
    for name in ("all_metrics.csv", "all_metrics.json",
                 "strict_audit_summary_metrics.json", "key_numbers.json",
                 "README.md",
                 "demand_1024_connector.png", "connector_matrix_64x64.png",
                 "connector_matrix_64x64.json", "layouts_z1_abcd.png",
                 "layouts_z2_abcd.png", "combined_layouts_abcd.png",
                 "overlay_3d_abcd.png", "class_routed_compare.png",
                 "algo_routed_rate_compare.png", "refold_routes_only.png",
                 "shape_mix.png", "u_routes_only.png"):
        path = comparison / name
        assert path.exists(), f"missing comparison artefact {name}"
    key_numbers = json.loads((comparison / "key_numbers.json").read_text(
        encoding="utf-8"))
    assert key_numbers["contract"]["connections_total"] == 1024
    assert key_numbers["planes"][0]["routed"] is not None
    assert key_numbers["loss_policy"]["bend_loss"] == "unknown_uncalibrated"
    assert key_numbers["reconciliation"]["planes_checked"] == 2
    payload = json.loads((comparison / "all_metrics.json").read_text(
        encoding="utf-8"))
    scopes = [row["scope"] for row in payload["experiments"]]
    assert scopes.count("plane") == 2
    assert scopes.count("combined") == 1
    for row in payload["experiments"]:
        if row["scope"] == "plane":
            assert row["routed"] is not None
            assert row["shape_U"] is not None
        if row["scope"] == "combined":
            assert row["routed"] == 12  # 6 routed z1 + 6 routed z2 in fixture
    matrix = json.loads((comparison / "connector_matrix_64x64.json").read_text(
        encoding="utf-8"))
    assert matrix["directed_total"] == 1024
    assert matrix["symmetric_total"] == 2048
    assert matrix["diagonal"] == 0


# ---------------------------------------------------------------------------
# golden checks on the real V3 pilot run when it exists
# ---------------------------------------------------------------------------
def _first_real_plane_run():
    if not V3_OUTPUTS.exists():
        return None
    for path in sorted(V3_OUTPUTS.glob("planes/*/*/routes.json")):
        return path.parent
    return None


def test_real_pilot_plane_run():
    run_dir = _first_real_plane_run()
    if run_dir is None:
        pytest.skip("no real V3 plane pilot run yet")
    from four_side_1024.v3 import metrics as v3_metrics

    payload, meta, records, routed, failed = v3_metrics.fm.load_routes(  # noqa: SLF001
        run_dir / "routes.json")
    assert len(records) == PLANE_TOTAL
    statistics = v3_metrics.build_plane_statistics(run_dir, quiet=True)
    assert statistics["routed"] == len(routed)
    assert statistics["routed"] + statistics["unrouted"] == PLANE_TOTAL
    assert sum(statistics["path_shapes"]["counts"].values()) == len(routed)
    assert statistics["topology_validation"]["passed"] is True
    # declared per-route length / propagation must agree with the recomputation
    declared_length = sum(record["length_mm"] for record in routed)
    declared_loss = sum(record.get("propagation_loss_db", 0.0) for record in routed)
    assert statistics["total_length_mm"] == pytest.approx(declared_length,
                                                          abs=1e-6)
    assert statistics["propagation_loss"]["total_db"] == pytest.approx(
        declared_loss, abs=1e-6)
    assert statistics["propagation_loss"]["total_db"] == pytest.approx(
        0.05 * declared_length / 10.0, abs=1e-6)
    # shape classes must cover every routed record with the required family names
    assert set(statistics["path_shapes"]["counts"]) == set(
        v3_metrics.REQUIRED_SHAPES)
    # same-side U numbers are internally consistent
    u_statistics = statistics["u_statistics"]
    u_per_route = sum(1 for route in
                      statistics["path_shapes"]["per_route"].values()
                      if route["shape"] == "U" and route["relation"] == "same")
    assert u_statistics["count"] == u_per_route
    audit_path = run_dir / "audit_strict.json"
    if audit_path.exists() and statistics["source"]["audit"]["status"] == "merged":
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        assert statistics["audit_passed"] == audit.get("passed")
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


def test_cli_metrics_run_dir(tmp_path, v3_ports, v3_config, v3_metrics):
    root = Path(tmp_path) / "outputs"
    run_dir = _write_plane(root, "B", "z1", v3_ports, v3_config)
    exit_code = v3_metrics.main(["--run-dir", str(run_dir), "--quiet"])
    assert exit_code == 0
    assert (run_dir / "statistics.json").exists()
