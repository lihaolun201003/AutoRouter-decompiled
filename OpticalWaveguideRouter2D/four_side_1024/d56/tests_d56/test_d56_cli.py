"""Command-line contract of ``four_side_1024.d56.validate_d56``.

Covers ``--run-dir`` (SPEC ``routes.json``), ``--routes`` (legacy artefacts and
``routes_geometry.json``), exit codes, the JSON report keys required by the SPEC
and the failed-route accounting.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from d56_helpers import (
    FREE_526,
    LEGACY_80,
    ROOT,
    build_generated_route_for_row,
    failed_record,
    routed_record,
    spec_routes_payload,
)
from four_side_1024.d56 import validate_d56 as V

MODULE = "four_side_1024.d56.validate_d56"
REQUIRED_KEYS = ("passed", "route_count", "errors", "violations",
                 "crossing_count", "crossing_angle_histogram",
                 "min_non_crossing_centerline_mm", "checks")


def run_cli(*arguments):
    return subprocess.run([sys.executable, "-m", MODULE, *arguments],
                          cwd=str(ROOT), capture_output=True, text=True,
                          timeout=300)


def test_cli_run_dir_with_spec_routes(tmp_path, dataset):
    first_row = dataset["by_id"][1]
    second_row = dataset["by_id"][257]
    first = build_generated_route_for_row(first_row, dataset["endpoints"])
    second = build_generated_route_for_row(second_row, dataset["endpoints"])
    records = [
        routed_record(1, first[0], first_row["source_endpoint"],
                      first_row["target_endpoint"], first_row["relation"]),
        routed_record(257, second[0], second_row["source_endpoint"],
                      second_row["target_endpoint"], second_row["relation"]),
        failed_record(900, first_row["source_endpoint"], first_row["target_endpoint"]),
    ]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "routes.json").write_text(
        json.dumps(spec_routes_payload(records), indent=2), encoding="utf-8")
    output = tmp_path / "validate_audit.json"
    completed = run_cli("--run-dir", str(run_dir), "--expect-route-count", "3",
                        "--output", str(output))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    for key in REQUIRED_KEYS:
        assert key in report
    assert report["passed"] is True, report["errors"]
    assert report["route_count"] == 3
    assert report["routed_count"] == 2
    assert report["failed_status_count"] == 1
    assert report["failed_status_route_ids"] == [900]
    assert report["d56_passed_count"] == 2
    assert report["d56_failed_count"] == 0
    # The two generated routes cross exactly once and are otherwise clear.
    assert report["crossing_count"] == 1
    assert sum(report["crossing_angle_histogram"].values()) == 1
    assert report["violations"] == []
    assert report["pair_audit"] == "exact_independent"


def test_cli_detects_invalid_geometry(tmp_path, dataset):
    row = dataset["by_id"][1]
    bad = [{"kind": "line", "p0": [10.0, 150.0], "p1": [20.0, 140.0], "layer": 0}]
    records = [routed_record(1, bad, row["source_endpoint"], row["target_endpoint"])]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "routes.json").write_text(
        json.dumps(spec_routes_payload(records), indent=2), encoding="utf-8")
    output = tmp_path / "audit.json"
    completed = run_cli("--run-dir", str(run_dir), "--expect-route-count", "1",
                        "--output", str(output))
    assert completed.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["d56_failed_count"] == 1
    assert report["route_errors"][0]["route_id"] == 1
    assert any(error.startswith("diagonal_line") for error in report["route_errors"][0]["errors"])
    assert report["errors"]


def test_cli_routes_mode_accepts_historical_d56(tmp_path):
    output = tmp_path / "legacy80.json"
    completed = run_cli("--routes", str(LEGACY_80), "--no-pair-audit",
                        "--output", str(output))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["d56_passed_count"] == 80
    assert report["crossing_count"] is None
    assert report["pair_audit"] == "skipped"


def test_cli_routes_mode_rejects_free_curves(tmp_path):
    output = tmp_path / "free526.json"
    completed = run_cli("--routes", str(FREE_526), "--no-pair-audit",
                        "--output", str(output))
    assert completed.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["d56_failed_count"] == 494
    assert report["d56_passed_count"] == 32
    assert "d56_route_errors:494" in report["errors"]


def test_cli_routes_mode_accepts_engine_checkpoint(tmp_path, legacy_80, dataset):
    """An engine checkpoint mapping (accepted/failed) is validated directly."""
    accepted = []
    for item in legacy_80:
        record = dict(item["record"])
        record.pop("status", None)
        accepted.append(record)
    all_ids = {row["route_id"] for row in dataset["rows"]}
    routed_ids = {item["route_id"] for item in legacy_80}
    failed = [{"route_id": route_id, "reason": "not_attempted_checkpoint"}
              for route_id in sorted(all_ids - routed_ids)]
    checkpoint = {"accepted": accepted, "failed": failed,
                  "checkpoint": {"note": "test"}}
    path = tmp_path / "routes_checkpoint.json"
    path.write_text(json.dumps(checkpoint), encoding="utf-8")
    output = tmp_path / "checkpoint_audit.json"
    completed = run_cli("--routes", str(path), "--output", str(output))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is True, report["errors"]
    assert report["route_count"] == 1024
    assert report["routed_count"] == 80
    assert report["failed_status_count"] == 944
    assert report["d56_passed_count"] == 80
    assert report["crossing_count"] == 1141


def test_cli_missing_routes_file(tmp_path):
    output = tmp_path / "missing.json"
    completed = run_cli("--run-dir", str(tmp_path / "does_not_exist"),
                        "--output", str(output))
    assert completed.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert any(error.startswith("routes_file_missing") for error in report["errors"])


def test_cli_route_count_mismatch(tmp_path, dataset):
    row = dataset["by_id"][1]
    primitives, _, _, _ = build_generated_route_for_row(row, dataset["endpoints"])
    records = [routed_record(1, primitives, row["source_endpoint"], row["target_endpoint"])]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "routes.json").write_text(
        json.dumps(spec_routes_payload(records)), encoding="utf-8")
    output = tmp_path / "audit.json"
    completed = run_cli("--run-dir", str(run_dir), "--expect-route-count", "1024",
                        "--no-pair-audit", "--output", str(output))
    assert completed.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert any(error.startswith("route_count_mismatch") for error in report["errors"])


def test_report_policy_ancestry_is_documented():
    """The report states the exact D56 policy and its tolerances."""
    report = V.build_report(routes_path=LEGACY_80, audit_pairs=False)
    policy = report["policy"]
    assert policy["radius_mm"] == 5.0
    assert policy["waveguide_width_mm"] == 0.05
    assert policy["edge_gap_mm"] == 0.125
    assert policy["centerline_clearance_mm"] == pytest.approx(0.175)
    assert policy["sagitta_mm"] == pytest.approx(0.0005)
    assert "clearance/sin(angle)+2*sagitta" in policy["crossing_window"]
    methods = " ".join(report["methods"])
    assert "conflicts never imported" in methods
    assert report["policy_used"] == "legacy"


def test_cli_compare_exact_sensitivity(tmp_path):
    """--compare-exact adds the exact-policy sensitivity list, legacy authoritative."""
    output = tmp_path / "compare.json"
    completed = run_cli("--routes", str(LEGACY_80), "--compare-exact",
                        "--output", str(output))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["policy_used"] == "legacy"
    assert report["violations"] == []
    assert report["exact_policy_violation_count"] == len(report["exact_policy_violations"])
    assert report["exact_policy_violation_count"] >= 1
    assert all(item["kind"] == "spacing"
               for item in report["exact_policy_violations"])
    assert "sensitivity only" in report["exact_policy_note"]


def test_cli_policy_exact_mode_is_not_authoritative(tmp_path):
    output = tmp_path / "exact.json"
    completed = run_cli("--routes", str(LEGACY_80), "--policy", "exact",
                        "--output", str(output))
    assert completed.returncode == 1  # exact policy flags window-covered near misses
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["policy_used"] == "exact"
    assert report["violations"]
    assert all(item["kind"] == "spacing" for item in report["violations"])
