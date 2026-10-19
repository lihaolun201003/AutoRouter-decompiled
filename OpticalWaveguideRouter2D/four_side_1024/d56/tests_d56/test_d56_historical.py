"""Historical-artefact regressions for the independent D56 validator.

* 80 routes of ``outputs/four_side_1024_legacy_two_branch_v2`` are D56 geometry
  and must all pass the single-route checks; their independent pair audit must
  reproduce the reference statistics (1141 crossings, identical histogram,
  zero violations).
* 526 routes of ``outputs/four_side_1024_single_layer_v1`` are free F56 curves;
  the D56 checker must flag them (494/526; the remaining 32 are single straight
  axis-aligned segments, which are legal degenerate D56 geometry).
"""
from __future__ import annotations

import json

import pytest

from d56_helpers import LEGACY_80, LEGACY_80_STATS, FREE_526
from four_side_1024.d56 import validate_d56 as V

HISTOGRAM_LABELS = ("0-1", "1-5", "5-10", "10-20", "20-30", "30-45",
                    "45-60", "60-75", "75-90")


# ---------------------------------------------------------------------------
# historical D56 baseline: 80 routes
# ---------------------------------------------------------------------------
def test_80_historical_routes_all_pass_d56(legacy_80):
    assert len(legacy_80) == 80
    short_s = 0
    for item in legacy_80:
        result = V.check_route_primitives(item["primitives"], item["source"],
                                          item["target"])
        assert result["passed"], (item["route_id"], result["errors"])
        assert all(result["checks"].values()), (item["route_id"], result["checks"])
        sweeps = [abs(prim["sweep"]) for prim in item["primitives"]
                  if prim["kind"] == "arc"]
        if any(abs(sweep - 3.141592653589793 * 0.5) > 1e-9 for sweep in sweeps):
            short_s += 1
    assert short_s == 2


def test_80_historical_pair_audit_matches_reference_statistics(legacy_80):
    prepared = [V.prepare_route(item["primitives"], item["route_id"])
                for item in legacy_80]
    audit = V.audit_route_pairs(prepared)
    reference = json.loads(LEGACY_80_STATS.read_text(encoding="utf-8"))
    assert audit["crossing_count"] == reference["crossing_count"] == 1141
    assert audit["crossing_angle_histogram"] == reference["crossing_angle_histogram"]
    assert list(audit["crossing_angle_histogram"]) == list(HISTOGRAM_LABELS)
    assert audit["small_angle_crossing_count"] == reference["small_angle_crossing_count"] == 0
    assert audit["violations"] == []
    assert audit["spacing_violation_pairs"] == 0
    assert audit["overlap_pairs"] == 0
    assert audit["touch_pairs"] == 0
    assert audit["crossing_zone_overlap_pairs"] == 0
    assert audit["min_non_crossing_centerline_mm"] == pytest.approx(0.175, abs=1e-9)


def test_80_historical_dataset_report_passes(legacy_80, dataset):
    records = []
    for item in legacy_80:
        record = dict(item["record"])
        record["_source_endpoint"] = record["source_endpoint"]
        record["_target_endpoint"] = record["target_endpoint"]
        record["_status"] = "routed"
        records.append(record)
    report = V.validate_dataset(records, dataset["endpoints"], expected_route_count=80)
    assert report["passed"] is True, report["errors"]
    assert report["d56_passed_count"] == 80
    assert report["d56_failed_count"] == 0
    assert report["crossing_count"] == 1141


# ---------------------------------------------------------------------------
# historical free-curve experiment: 526 routes must be recognised as F56
# ---------------------------------------------------------------------------
def test_526_free_curves_rejected_as_f56(free_526):
    assert len(free_526) == 526
    rejected = []
    accepted = []
    for item in free_526:
        result = V.check_route_primitives(item["primitives"], item["source"],
                                          item["target"])
        if result["passed"]:
            accepted.append(item)
        else:
            rejected.append((item, result))
    # 494 of the 526 Dubins/free-curve routes are impossible as D56 geometry.
    assert len(rejected) == 494
    assert len(accepted) == 32
    for item, result in rejected:
        assert result["checks"]["d56_arc_family"] is False \
            or result["checks"]["orthogonal_lines"] is False
        assert any(error.startswith("diagonal_line")
                   or error.startswith("short_s")
                   for error in result["errors"])
        # These are real connected curves, not broken primitives: the endpoint
        # and G1 checks pass; only the D56 element restriction rejects them.
        assert result["checks"]["endpoints_fixed"] is True
        assert result["checks"]["inout_directions"] is True
        assert result["checks"]["position_continuity"] is True
        assert result["checks"]["radius_fixed"] is True
        assert result["checks"]["self_intersection_free"] is True
    # The 32 accepted routes are single straight axis-aligned segments, which
    # are legal degenerate D56 routes (zero bends).
    for item in accepted:
        assert len(item["primitives"]) == 1
        assert item["primitives"][0]["kind"] == "line"


def test_526_free_curve_dataset_report_flags_f56(free_526, dataset):
    records = []
    for item in free_526:
        record = dict(item["record"])
        record["_status"] = "routed"
        records.append(record)
    report = V.validate_dataset(records, dataset["endpoints"], audit_pairs=False)
    assert report["passed"] is False
    assert report["d56_failed_count"] == 494
    assert report["d56_passed_count"] == 32
    assert "d56_route_errors:494" in report["errors"]
    assert report["diagonal_line_violations"] >= 494 - 32
    assert report["free_or_short_s_arc_violations"] >= 494 - 32
    assert report["radius_violations"] == 0
    assert report["boundary_violations"] == 0


def test_failed_status_routes_are_counted_not_audited(dataset):
    """status=failed routes are counted and skipped, never silently dropped."""
    from d56_helpers import failed_record, routed_record, build_generated_route_for_row

    row = next(row for row in dataset["rows"] if row["relation"] == "opposite")
    primitives, source, target, _ = build_generated_route_for_row(row, dataset["endpoints"])
    records = [
        routed_record(1, primitives, row["source_endpoint"], row["target_endpoint"]),
        failed_record(2, row["source_endpoint"], row["target_endpoint"]),
        failed_record(3, row["source_endpoint"], row["target_endpoint"]),
    ]
    report = V.validate_dataset(records, dataset["endpoints"], audit_pairs=False)
    assert report["route_count"] == 3
    assert report["routed_count"] == 1
    assert report["failed_status_count"] == 2
    assert report["failed_status_route_ids"] == [2, 3]
    assert report["d56_checked_count"] == 1
    assert report["passed"] is True, report["errors"]
