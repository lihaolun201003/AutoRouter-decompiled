"""pytest suite for the ABCD Phase-6 metric / export / figure pipeline.

Golden fixture: the historical D56 run
``outputs/four_side_1024_d56_optimized/`` (467/1024 routed, 57029 crossings,
mean length 149.5618 mm).  Every test checks that ``abcd/metrics.py`` re-derives
the historical numbers **from the analytic primitives** instead of copying the
router's embedded ``routes.json["statistics"]`` block (which claims 59188
crossings -- a stale router self-report).

Run from the project root::

    .venv\\Scripts\\python.exe -m pytest four_side_1024/abcd/tests_abcd -v
"""
from __future__ import annotations

import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = ROOT / "outputs" / "four_side_1024_d56_optimized"
GOLDEN_ROUTES = GOLDEN_DIR / "routes.json"
GOLDEN_STATISTICS = GOLDEN_DIR / "statistics.json"
GOLDEN_AUDIT = GOLDEN_DIR / "independent_audit.json"
CONNECTION_TOTAL = 1024
EXPECTED_PAIR_COUNTS = {"NS": 28, "EW": 25, "EN": 128,
                        "ES": 43, "SW": 115, "NW": 128}


def _walk_numbers(value, path="statistics"):
    """Yield ``(path, number)`` for every int/float found in a JSON structure."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_numbers(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_numbers(item, f"{path}[{index}]")
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path, float(value)


@pytest.fixture(scope="module")
def golden_history():
    if not GOLDEN_STATISTICS.exists():
        pytest.skip("historical golden statistics.json is absent")
    with open(GOLDEN_STATISTICS, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def golden_routes_payload():
    with open(GOLDEN_ROUTES, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def golden_audit():
    with open(GOLDEN_AUDIT, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def metrics_module():
    from four_side_1024.abcd import metrics
    return metrics


@pytest.fixture(scope="module")
def golden_statistics(tmp_path_factory, metrics_module):
    """Recompute the full metric set for the golden fixture once per session."""
    if not GOLDEN_ROUTES.exists():
        pytest.skip("golden routes.json is absent")
    out_dir = tmp_path_factory.mktemp("golden_metrics")
    statistics = metrics_module.build_statistics(
        routes_path=GOLDEN_ROUTES,
        out_path=out_dir / "statistics.json",
        audit_path=None if not GOLDEN_AUDIT.exists() else GOLDEN_AUDIT,
        quiet=True)
    return statistics


# ---------------------------------------------------------------------------
# metric correctness against the historical result
# ---------------------------------------------------------------------------
def test_golden_routing_counts(golden_statistics, golden_history):
    stats = golden_statistics
    assert stats["routed"] == 467
    assert stats["unrouted"] == 557
    assert stats["total_connections"] == CONNECTION_TOTAL
    assert stats["routing_rate"] == pytest.approx(467 / CONNECTION_TOTAL, abs=0)
    assert stats["success_count"] == 467
    assert stats["failed_count"] == 557
    for pair, expected in EXPECTED_PAIR_COUNTS.items():
        assert stats["by_pair"][pair]["success"] == expected, pair
        assert stats["by_pair"][pair]["routed"] == expected, pair
        assert stats["by_pair"][pair]["total"] == golden_history["by_pair"][pair]["total"]
    assert stats["by_relation"]["opposite"]["success"] == 53
    assert stats["by_relation"]["adjacent"]["success"] == 414
    assert stats["opposite_routing_rate"] == pytest.approx(53 / 512)
    assert stats["adjacent_routing_rate"] == pytest.approx(414 / 512)


def test_golden_length_and_bend_stats(golden_statistics, golden_history):
    stats = golden_statistics
    assert stats["mean_length_mm"] == pytest.approx(
        golden_history["mean_length_mm"], rel=1e-9)
    assert stats["mean_length_mm"] == pytest.approx(149.56181186262162, rel=1e-9)
    assert stats["max_length_mm"] == pytest.approx(
        golden_history["max_length_mm"], rel=1e-9)
    assert stats["total_length_mm"] == pytest.approx(
        golden_history["total_length_mm"], rel=1e-9)
    assert stats["mean_bend_count"] == pytest.approx(
        golden_history["mean_bend_count"], rel=1e-12)
    assert stats["total_bends"] == 766
    assert stats["mean_turns"] == pytest.approx(stats["mean_bend_count"])
    assert stats["mean_straight_fraction"] is not None
    assert 0.0 <= stats["mean_straight_fraction"] <= 1.0
    # no route's recomputed length may disagree with the stored analytic length
    assert stats["geometry_checks"]["length_mismatch_count"] == 0


def test_golden_crossings(golden_statistics, golden_history, golden_audit):
    stats = golden_statistics
    audit_value = golden_audit["crossing_count"]
    assert audit_value == 57029
    # merged authoritative value and independent recomputation must agree
    assert stats["crossing_count"] == audit_value
    assert stats["crossing_count_recomputed"] == audit_value
    histogram = stats["crossing_angle_histogram"]
    assert sum(histogram.values()) == audit_value
    assert histogram == golden_history["crossing_angle_histogram"]
    assert stats["small_angle_crossing_count"] == golden_audit[
        "small_angle_crossing_count"] == 9
    assert stats["small_angle_5deg_crossing_count"] == 0
    expected_density = 57029 / (150.0 * 150.0)
    assert stats["crossing_count_density_per_mm2"] == pytest.approx(expected_density)
    # the router's stale self-report must NOT be what metrics.py emits
    router_reported = golden_history["router_reported_statistics"]["crossing_count"]
    assert router_reported == 59188
    assert stats["crossing_count"] == 57029 != router_reported


def test_golden_violation_counters(golden_statistics, golden_audit):
    stats = golden_statistics
    assert stats["audit_passed"] is True
    assert stats["audit_policy"] == "exact"
    for field in ("spacing_violation_pairs", "overlap_pairs", "touch_pairs",
                  "crossing_window_overlap_pairs", "self_intersections",
                  "self_overlaps", "radius_violations", "boundary_violations",
                  "diagonal_line_violations", "free_arc_violations"):
        assert stats[field] == 0, field
        assert stats[f"{field}_recomputed"] == 0, field
    assert stats["total_violation_count"] == 0


def test_required_metric_names_present(golden_statistics):
    required = (
        "routed", "unrouted", "routing_rate", "opposite_routing_rate",
        "adjacent_routing_rate", "mean_length_mm", "max_length_mm",
        "total_length_mm", "mean_bend_count", "total_bends", "crossing_count",
        "crossing_count_density_per_mm2", "crossing_angle_histogram",
        "small_angle_crossing_count", "spacing_violation_pairs",
        "overlap_pairs", "touch_pairs", "crossing_window_overlap_pairs",
        "self_intersections", "radius_violations", "boundary_violations",
        "diagonal_line_violations", "free_arc_violations",
        "candidate_evaluations", "runtime_seconds", "evals_per_second",
        "peak_memory_mb", "mean_straight_fraction", "mean_turns",
        "mean_min_gap_mm", "crossing_grid_peak", "track_band_score",
        "symmetry", "pareto",
    )
    for name in required:
        assert name in golden_statistics, name
    for pair in ("NS", "EW", "EN", "ES", "SW", "NW"):
        assert "routing_rate" in golden_statistics["by_pair"][pair]


def test_no_negative_or_nan_metrics(golden_statistics):
    problems = []
    for path, value in _walk_numbers(golden_statistics):
        if math.isnan(value) or math.isinf(value):
            problems.append(f"{path} is not finite ({value})")
            continue
        if value < 0.0 and "matrix" not in path and "offset" not in path:
            # isometry matrices legitimately contain -1 entries; every other
            # SPEC §5 physical quantity must be non-negative.
            problems.append(f"{path} is negative ({value})")
    assert not problems, "\n".join(problems[:20])


def test_regularity_and_symmetry_metrics(golden_statistics):
    stats = golden_statistics
    assert stats["mean_min_gap_mm"] > 0.17
    assert stats["min_min_gap_mm"] >= 0.175 - 1e-9
    assert 0.0 <= stats["track_band_score"] <= 1.0
    assert stats["track_band_eligible_pairs"] > 0
    assert stats["crossing_grid_peak"] > 0
    assert stats["crossing_grid_peak"] == max(
        cell["count"] for cell in stats["densest_crossing_cells"])
    symmetry = stats["symmetry"]
    assert symmetry["available"] is True
    for name in ("rot90", "rot180", "mirror_x", "mirror_y", "diag"):
        assert name in symmetry, name
        entry = symmetry[name]
        assert "routed_pair_fraction" in entry
        assert "shape_match_fraction" in entry
    diag = symmetry["diag"]
    assert diag["pair_count"] > 0
    assert 0.0 <= diag["routed_pair_fraction"] <= 1.0


def test_metric_sources_recorded(golden_statistics):
    stats = golden_statistics
    sources = stats["metric_sources"]
    assert "audited_fields" in sources
    assert "crossing_count" in sources["audited_fields"]
    assert "independent_audit" in sources["audited_fields"]["crossing_count"]
    assert "independent_audit.json" in stats["crossing_count_source"]
    assert "recomputed from route primitives" in " ".join(stats["notes"])


# ---------------------------------------------------------------------------
# single-layer GDS + SVG export
# ---------------------------------------------------------------------------
def test_export_gds_single_layer_and_svg(tmp_path):
    gdspy = pytest.importorskip("gdspy")
    from four_side_1024.abcd import export

    summary = export.export_run(routes_path=GOLDEN_ROUTES, run_dir=tmp_path)
    gds_path = tmp_path / "routing_all.gds"
    svg_path = tmp_path / "routing_all.svg"
    assert gds_path.exists() and gds_path.stat().st_size > 10_000
    assert svg_path.exists()

    library = gdspy.GdsLibrary(infile=str(gds_path))
    tops = library.top_level()
    assert len(tops) == 1
    paths = list(tops[0].paths)
    layers = sorted({int(layer) for path in paths for layer in path.layers})
    datatypes = sorted({int(dt) for path in paths for dt in path.datatypes})
    assert layers == [0], f"GDS must be single-layer layer 0, got {layers}"
    assert datatypes == [0]
    assert len(paths) == 467
    assert summary["verification"]["single_layer"] is True
    assert summary["verification"]["gds_layers"] == [0]

    # contract: PNG-adjacent SVG < 5 MB, valid XML, sagitta <= 0.01 mm
    assert svg_path.stat().st_size < 5 * 1024 * 1024
    ET.parse(svg_path)  # raises on invalid XML
    assert summary["svg"]["sagitta_mm"] <= 0.01
    assert summary["verification"]["svg_xml_valid"] is True
    assert summary["verification"]["svg_under_5mb"] is True

    # arc discretisation for the GDS obeys sagitta <= 0.0005 mm
    sagitta = summary["verification"]["arc_sagitta"]
    assert sagitta["arcs_checked"] > 0
    assert sagitta["max_chord_sagitta_mm"] <= 0.0005 + 1e-12
    assert sagitta["verified"] is True
    assert summary["verification"]["stroked_bounds"]["verified"] is True


# ---------------------------------------------------------------------------
# figures / comparison pipeline smoke tests
# ---------------------------------------------------------------------------
def test_plot_pipeline_writes_figure(golden_statistics, tmp_path):
    from four_side_1024.abcd import plots

    summary = plots.render_experiment(
        routes_path=GOLDEN_ROUTES, run_dir=tmp_path,
        statistics=golden_statistics, experiment="GOLDEN_467",
        by_pair=False, with_detail=False)
    png = tmp_path / "routing_all.png"
    assert png.exists() and png.stat().st_size > 50_000
    assert summary["routed_count"] == 467
    assert summary["experiment"] == "GOLDEN_467"
    assert summary["files"]["routing_all_png"]["routes"] == 467
    assert summary["style"]["coordinate_limits"] == [-9.0, 159.0]
    assert summary["style"]["dpi"] == 200


def test_comparison_pipeline(tmp_path, golden_statistics):
    from four_side_1024.abcd import compare

    root = tmp_path / "abcd_root"
    experiments = compare.EXPERIMENT_ORDER
    for experiment in experiments:
        directory = root / experiment
        directory.mkdir(parents=True)
        shutil.copyfile(GOLDEN_ROUTES, directory / "routes.json")
        shutil.copyfile(GOLDEN_AUDIT, directory / "audit_strict.json")
        with open(directory / "statistics.json", "w", encoding="utf-8") as handle:
            json.dump(golden_statistics, handle)
    result = compare.build_comparison(root=root, recompute_missing=False,
                                      quiet=True)
    comparison = root / "comparison"
    for name in ("all_metrics.csv", "all_metrics.json",
                 "strict_audit_summary.json", "abcd_layout_compare.png",
                 "abcd_layout_compare_v2.png", "v1_v2_same_algo_compare.png",
                 "metric_bars_routed.png", "metric_bars_relation_rate.png",
                 "metric_bars_length.png", "metric_bars_crossings.png",
                 "metric_bars_runtime.png", "metric_bars_strict_violations.png"):
        path = comparison / name
        assert path.exists(), f"missing comparison artefact {name}"
        if path.suffix == ".png":
            assert path.stat().st_size > 20_000, name
    with open(comparison / "all_metrics.json", "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert len(payload["experiments"]) == len(experiments)
    for row in payload["experiments"]:
        assert row["routed"] == 467
        assert row["crossing_count"] == 57029
        assert row["audit_passed"] is True
    audit_summary = json.loads(
        (comparison / "strict_audit_summary.json").read_text(encoding="utf-8"))
    assert audit_summary["experiments_with_audit"] == len(experiments)
    assert audit_summary["all_available_passed"] is True
    assert len(result["rows"]) == len(experiments)
