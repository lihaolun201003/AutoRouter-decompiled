"""Unit tests for the independent R15 acceptance wrapper (``r15/validate_r15.py``).

The tests build synthetic R15 primitives (radius 15 mm lines/arcs/short-S pairs,
identical in shape to the routing families) and additionally run the complete
plane validation on the real R15 smoke artefacts when they exist.

Run from the project root ``OpticalWaveguideRouter2D``::

    .venv\\Scripts\\python.exe -m pytest four_side_1024\\r15\\tests_r15 -v
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from four_side_1024.r15 import validate_r15 as V

SMOKE_ROOT = V.PROJECT_ROOT / "outputs" / "four_side_1024_v2_r15_v01_smoke"
SMOKE_PLANE = SMOKE_ROOT / "planes" / "V2"


# ---------------------------------------------------------------------------
# Synthetic R15 geometry helpers
# ---------------------------------------------------------------------------
def _line(p0, p1):
    return {"kind": "line", "p0": [float(p0[0]), float(p0[1])],
            "p1": [float(p1[0]), float(p1[1])], "layer": 0}


def _arc(p0, p1, center, radius, start_angle, sweep):
    return {"kind": "arc", "p0": [float(p0[0]), float(p0[1])],
            "p1": [float(p1[0]), float(p1[1])],
            "center": [float(center[0]), float(center[1])],
            "radius": float(radius), "start_angle": float(start_angle),
            "sweep": float(sweep), "layer": 0}


def _quarter_arc(radius, sweep=math.pi / 2.0):
    """A legal quarter arc starting at the origin travelling +x, R=``radius``."""
    return _arc((0.0, 0.0), (radius, radius), (0.0, radius), radius,
                -math.pi / 2.0, sweep)


def _short_s_pair(radius=15.0, theta_deg=20.0):
    """Legal D56 short-S pair at ``radius`` (returns the two arc dicts + end)."""
    theta = math.radians(theta_deg)
    p1 = (radius * math.sin(theta), radius * (1.0 - math.cos(theta)))
    first = _arc((0.0, 0.0), p1, (0.0, radius), radius, -math.pi / 2.0, theta)
    center2 = (p1[0] + radius * math.sin(theta),
               p1[1] - radius * math.cos(theta))
    end = (2.0 * radius * math.sin(theta),
           2.0 * radius * (1.0 - math.cos(theta)))
    second = _arc(p1, end, center2, radius, math.pi / 2.0 + theta, -theta)
    return first, second, end


def _scan(primitives, scheme):
    report = V._ItemReport()
    parsed, stats = V._scan_primitives(primitives, scheme, report, route_id=1)
    return report, parsed, stats


# ---------------------------------------------------------------------------
# Primitive scan: R15 radius / axis / sweep rules
# ---------------------------------------------------------------------------
def test_scan_accepts_legal_r15_ortho90():
    primitives = [_line((-10.0, 0.0), (0.0, 0.0)),
                  _quarter_arc(15.0),
                  _line((15.0, 15.0), (30.0, 15.0))]
    report, parsed, stats = _scan(primitives, "B")
    assert report.total == 0, report.violations
    assert stats["lines"] == 2
    assert stats["arcs"] == 1
    assert stats["quarter_arcs"] == 1
    assert stats["arc_radius_values"] == [15.0]
    assert stats["arc_radius_deviation_max_mm"] == 0.0


def test_scan_accepts_legal_r15_short_s_scheme_a():
    first, second, end = _short_s_pair()
    primitives = [first, second,
                  _line(end, (end[0] + 10.0, end[1]))]
    report, _parsed, stats = _scan(primitives, "A")
    assert report.total == 0, report.violations
    assert stats["short_s_pairs"] == 1
    assert stats["arcs"] == 2
    assert stats["arc_radius_values"] == [15.0]


def test_scan_rejects_r40_arc():
    primitives = [_quarter_arc(40.0)]
    report, _parsed, stats = _scan(primitives, "B")
    kinds = {violation["kind"] for violation in report.violations}
    assert "arc_radius_not_r15" in kinds
    assert report.counts["geometry_errors"] >= 1
    assert stats["arc_radius_values"] == [40.0]
    assert stats["arc_radius_deviation_max_mm"] == pytest.approx(25.0)


def test_scan_rejects_non_90_arc_in_scheme_b():
    primitives = [_arc((0.0, 0.0), (15.0, 10.0), (0.0, 15.0), 15.0,
                       -math.pi / 2.0, math.radians(80.0))]
    report, _parsed, _stats = _scan(primitives, "B")
    kinds = {violation["kind"] for violation in report.violations}
    assert "non_90_arc_scheme_b" in kinds
    # the same arc is not judged by the sweep rule under scheme A
    report_a, _parsed_a, _stats_a = _scan([_line((-5.0, -5.0), (0.0, -5.0)),
                                           *primitives], "A")
    assert "non_90_arc_scheme_b" not in {
        violation["kind"] for violation in report_a.violations}


def test_scan_rejects_diagonal_line():
    report, _parsed, stats = _scan([_line((0.0, 0.0), (10.0, 10.0))], "B")
    kinds = {violation["kind"] for violation in report.violations}
    assert "diagonal_line" in kinds
    assert stats["diagonal_lines"] == 1


def test_scan_rejects_invalid_short_s_pair():
    first, second, _end = _short_s_pair()
    bad_second = dict(second)
    bad_second["sweep"] = second["sweep"] * 0.5
    report, _parsed, _stats = _scan([first, bad_second], "A")
    kinds = {violation["kind"] for violation in report.violations}
    assert "short_s_invalid" in kinds


def test_short_s_pair_formula_uses_own_radius():
    first, second, _end = _short_s_pair(radius=15.0, theta_deg=20.0)
    parsed = [V._parse_primitive(first, 0, "A", V._ItemReport()),
              V._parse_primitive(second, 1, "A", V._ItemReport())]
    assert V._short_s_pair_ok(parsed[0], parsed[1])
    # R15 pair displaced as if it were an R40 pair must not be accepted
    wrong = _short_s_pair(radius=40.0, theta_deg=20.0)
    wrong_first = V._parse_primitive(wrong[0], 0, "A", V._ItemReport())
    wrong_second = V._parse_primitive(wrong[1], 1, "A", V._ItemReport())
    assert abs(wrong_first.radius - V.R15_RADIUS_MM) > V.R15_TOL
    assert V._short_s_pair_ok(parsed[0], wrong_second) is False


def test_primitive_continuity_is_checked():
    primitives = [_line((0.0, 0.0), (10.0, 0.0)),
                  _line((10.5, 0.0), (20.0, 0.0))]  # 0.5 mm gap
    report, _parsed, _stats = _scan(primitives, "B")
    kinds = {violation["kind"] for violation in report.violations}
    assert "primitive_discontinuity" in kinds


# ---------------------------------------------------------------------------
# Process record rules (radius 15, not 40)
# ---------------------------------------------------------------------------
def _process_record(**overrides):
    record = {
        "board_mm": [150.0, 150.0],
        "waveguide_width_mm": 0.05,
        "min_edge_gap_mm": 0.03,
        "min_centerline_clearance_mm": 0.08,
        "min_bend_radius_mm": 15.0,
        "radius_mm": 15.0,
        "fixed_radius_40mm": False,
        "process_profile": V.R15_PROFILE_NAME,
    }
    record.update(overrides)
    return record


def test_process_check_accepts_r15_profile():
    report = V._ItemReport()
    info = V._check_process(_process_record(), report)
    assert report.total == 0, report.violations
    assert info["radius_ok"] is True
    assert info["fixed_radius_40mm_ok"] is True


def test_process_check_rejects_r40_process():
    report = V._ItemReport()
    V._check_process(_process_record(min_bend_radius_mm=40.0, radius_mm=40.0,
                                     fixed_radius_40mm=True), report)
    kinds = {violation["kind"] for violation in report.violations}
    assert "process_radius_not_r15" in kinds
    assert "process_radius_is_r40" in kinds
    assert "process_fixed_radius_40mm_true" in kinds


# ---------------------------------------------------------------------------
# Complete plane validation on the real R15 smoke artefacts
# ---------------------------------------------------------------------------
def _smoke_plane_path(label, plane):
    return SMOKE_PLANE / label / plane / "routes.json"


@pytest.mark.skipif(not _smoke_plane_path("A", "z2").exists(),
                    reason="R15 smoke artefacts not present")
def test_smoke_scheme_a_plane_passes():
    item = V.validate_plane_2d(_smoke_plane_path("A", "z2"), "A", "z2",
                               run_frozen=True)
    assert item["passed"], item["violations"]
    assert item["counts"]["violations"] == 0
    assert item["routed"] > 0
    assert item["geometry"]["arcs"] > 0
    assert item["geometry"]["arc_radius_values"] == [15.0]
    assert item["strict_2d"]["passed"] is True
    assert item["strict_2d"]["fixed_radius_40mm"] is False


@pytest.mark.skipif(not _smoke_plane_path("B", "z2").exists(),
                    reason="R15 smoke artefacts not present")
def test_smoke_scheme_b_plane_passes():
    item = V.validate_plane_2d(_smoke_plane_path("B", "z2"), "B", "z2",
                               run_frozen=True)
    assert item["passed"], item["violations"]
    assert item["counts"]["violations"] == 0
    assert item["geometry"]["arc_radius_values"] == [15.0]
    assert item["strict_2d"]["passed"] is True


@pytest.mark.skipif(not _smoke_plane_path("A", "z2").exists(),
                    reason="R15 smoke artefacts not present")
def test_smoke_plane_with_r40_radius_is_rejected(tmp_path):
    payload = json.loads(_smoke_plane_path("A", "z2").read_text(encoding="utf-8"))
    mutated = False
    for record in payload["routes"]:
        if record.get("status") != "routed":
            continue
        for primitive in record.get("primitives") or []:
            if primitive.get("kind") == "arc":
                primitive["radius"] = 40.0
                mutated = True
                break
        if mutated:
            break
    assert mutated
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    item = V.validate_plane_2d(path, "A", "z2", run_frozen=False)
    assert item["passed"] is False
    kinds = {violation["kind"] for violation in item["violations"]}
    assert "arc_radius_not_r15" in kinds


# ---------------------------------------------------------------------------
# Combined 1024-check (synthetic but schema-true: 512 identities per plane)
# ---------------------------------------------------------------------------
def _build_synthetic_combined(label="B"):
    """Combined payload: z1 entirely failed, z2 with the real smoke routed routes."""
    from four_side_1024.fslw import ports

    plane_routes = {}
    endpoints = {}
    for plane in ("z1", "z2"):
        routes, plane_endpoints, _connectors, _validation = ports.load_plane(
            "V2", plane)
        plane_routes[plane] = routes
        endpoints[plane] = plane_endpoints
    smoke_path = _smoke_plane_path(label, "z2")
    routed = {}
    if smoke_path.exists():
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        routed = {int(record["route_id"]): record
                  for record in smoke["routes"]
                  if record.get("status") == "routed"}
    records = []
    for plane in ("z1", "z2"):
        for csv_record in plane_routes[plane]:
            route_id = int(csv_record["route_id"])
            record = {
                "route_id": route_id,
                "plane": plane,
                "pair": csv_record["pair"],
                "relation": csv_record["relation"],
                "source_endpoint": csv_record["source_endpoint"],
                "target_endpoint": csv_record["target_endpoint"],
                "source_row": csv_record["source_row"],
                "target_row": csv_record["target_row"],
                "layer": 0,
                "z_mm": 0.0 if plane == "z1" else 0.5,
            }
            if plane == "z2" and route_id in routed:
                record.update(status="routed",
                              primitives=routed[route_id]["primitives"])
            else:
                record.update(status="failed", reason="no_2d_candidate")
            records.append(record)
    process = {"min_bend_radius_mm": 15.0, "radius_mm": 15.0,
               "fixed_radius_40mm": False,
               "min_centerline_clearance_mm": 0.08,
               "waveguide_width_mm": 0.05, "board_mm": [150.0, 150.0],
               "process_profile": V.R15_PROFILE_NAME}
    return {
        "schema": V.SCHEMA_COMBINED,
        "topology": "V2",
        "algorithm": label,
        "layer": 0,
        "process": process,
        "routes": records,
    }


@pytest.mark.skipif(not _smoke_plane_path("B", "z2").exists(),
                    reason="R15 smoke artefacts not present")
def test_combined_payload_passes_when_planes_are_legal(tmp_path):
    payload = _build_synthetic_combined("B")
    path = tmp_path / "routes_1024.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    item = V.validate_combined_2d(path, "B", run_frozen=True)
    assert item["passed"], item["violations"]
    assert item["total"] == 1024
    assert item["routed"] > 0
    assert item["plane_audits"]["z1"]["passed"] is True
    assert item["plane_audits"]["z2"]["passed"] is True
    assert item["geometry"]["arc_radius_values"] == [15.0]


# ---------------------------------------------------------------------------
# CLI behaviour: missing inputs are pending, never a crash
# ---------------------------------------------------------------------------
def test_cli_missing_inputs_are_pending(tmp_path):
    root = tmp_path / "empty_r15_root"
    out = tmp_path / "validation"
    code = V.main(["--root", str(root), "--out", str(out),
                   "--skip-combined", "--skip-25d", "--no-port-csv"])
    assert code == 2  # nothing was processed
    summary_path = out / "r15_validation_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["passed"] is False
    assert summary["items"] == {}
    assert len(summary["pending"]) >= 1
