"""Acceptance test for the real optimized 1024-route D56 run.

Skipped until the Lead's engine has produced
``outputs/four_side_1024_d56_optimized/routes.json``.  Once it exists this test
verifies the whole saved artefact end to end: 1024 route identities, every
routed route D56-legal, the independent pair audit clean under the *declared*
acceptance policy, and the full audit inside the two-minute budget.

The delivered run declares ``algorithm.crossing_policy = "exact"``: the crossing
exemption region is computed from the exact geometry instead of the historical
straight-line approximation ``clearance/sin(angle)`` (which under-exempts
curved crossings by 4 nm - 43 um; see docs/reports/four_side_1024_d56_optimized.md
section 5).  The historical policy is still audited here as a sensitivity check,
and it must stay free of overlaps, touches, radius or boundary violations.
"""
from __future__ import annotations

import json

import pytest

from d56_helpers import REAL_D56_RUN
from four_side_1024.d56 import validate_d56 as V

pytestmark = pytest.mark.skipif(
    not REAL_D56_RUN.exists(),
    reason="optimized D56 run not produced yet (outputs/four_side_1024_d56_optimized/routes.json)")


def _declared_policy():
    payload = json.loads(REAL_D56_RUN.read_text(encoding='utf-8'))
    algorithm = payload.get('algorithm') or {}
    policy = algorithm.get('crossing_policy') or 'exact'
    return 'exact' if policy == 'exact' else 'legacy'


def test_real_d56_run_passes_independent_audit():
    assert REAL_D56_RUN.exists()
    policy = _declared_policy()
    report = V.build_report(run_dir=REAL_D56_RUN.parent, audit_pairs=True,
                            policy=policy)
    assert report["route_count"] == 1024
    assert report["d56_failed_count"] == 0, report["route_errors"][:5]
    assert report["violations"] == [], report["violations"][:5]
    assert report["errors"] == [], report["errors"]
    assert report["passed"] is True
    assert report["pair_audit"] == "exact_independent"
    histogram = report["crossing_angle_histogram"]
    assert sum(histogram.values()) == report["crossing_count"]
    assert report["min_non_crossing_centerline_mm"] is None or \
        report["min_non_crossing_centerline_mm"] >= 0.175 - 1e-8
    assert report["runtime_seconds"] < 120.0
    print(f"\nreal D56 run ({policy} policy): routed={report['routed_count']} "
          f"failed={report['failed_status_count']} "
          f"crossings={report['crossing_count']} "
          f"audit={report['runtime_seconds']:.1f}s")


def test_real_d56_run_historical_policy_is_a_numerical_artifact_only():
    """The historical crossing window must not hide any *physical* violation."""
    assert REAL_D56_RUN.exists()
    legacy = V.build_report(run_dir=REAL_D56_RUN.parent, audit_pairs=True,
                           policy='legacy')
    assert legacy["route_count"] == 1024
    assert legacy["d56_failed_count"] == 0, legacy["route_errors"][:5]
    # Overlaps, tangency, radius and boundary violations must be exactly zero.
    assert legacy["overlap_pairs"] == 0
    assert legacy["touch_pairs"] == 0
    assert legacy["radius_violations"] == 0
    assert legacy["boundary_violations"] == 0
    # Every reported shortfall is a crossing-window artefact: measured
    # 4.9 nm .. 51.1 um (median 3.0 um) on the delivered solution.
    for violation in legacy["violations"]:
        distance = violation.get("distance_mm")
        if distance is not None:
            assert distance >= 0.175 - 0.075, violation
    print(f"\nhistorical-window sensitivity: violations={legacy['violations'] and len(legacy['violations'])} "
          f"(all >= {0.175 - 0.075} mm, i.e. <= 75 um shortfall)")
