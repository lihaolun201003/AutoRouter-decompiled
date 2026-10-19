"""Exact inter-route audit policy tests (independent implementation).

Policy must match ``four_side_1024/conflicts.py``: centerline distance at least
0.175 mm except inside local crossing windows of length
``0.175/sin(angle) + 2*0.0005`` on *both* curves; overlap, tangency (sine<1e-7 or
an intersection at a route endpoint), overlapping windows and outside-window
spacing violations are rejected; pure crossings are legal and counted.
"""
from __future__ import annotations

import math

import pytest

from d56_helpers import CLEARANCE, RADIUS, arc, line
from four_side_1024.d56 import validate_d56 as V


def prepare(route_id, primitives):
    return V.prepare_route(primitives, route_id)


def pair(first_primitives, second_primitives):
    return V.evaluate_pair(prepare(1, first_primitives), prepare(2, second_primitives))


# ---------------------------------------------------------------------------
# legal crossings are counted, not rejected
# ---------------------------------------------------------------------------
def test_orthogonal_crossing_allowed_and_measured():
    result = pair([line((-5.0, 0.0), (5.0, 0.0))],
                  [line((0.0, -5.0), (0.0, 5.0))])
    assert result["valid"] is True
    assert len(result["crossings"]) == 1
    assert math.degrees(math.asin(result["crossings"][0]["sine"])) == pytest.approx(90.0)
    # The exemption window is clearance/sin(90) + 2*sagitta = 0.176 mm.
    assert result["crossings"][0]["half"] == pytest.approx(0.176, abs=1e-12)


def test_shallow_crossing_allowed_when_window_is_long_enough():
    angle = math.radians(5.0)
    span = 100.0
    result = pair([line((-span, 0.0), (span, 0.0))],
                  [line((-span, -span * math.tan(angle)),
                        (span, span * math.tan(angle)))])
    assert result["valid"] is True
    assert len(result["crossings"]) == 1
    assert math.degrees(math.asin(result["crossings"][0]["sine"])) == pytest.approx(5.0)


def test_audit_counts_and_angle_histogram():
    routes = [prepare(1, [line((-50.0, 0.0), (50.0, 0.0))]),
              prepare(2, [line((0.0, -50.0), (0.0, 50.0))]),
              prepare(3, [line((1.0, -50.0), (1.0, 50.0))])]
    audit = V.audit_route_pairs(routes)
    assert audit["candidate_pair_count"] == 2  # routes 2 and 3 are 1 mm apart
    assert audit["crossing_count"] == 2
    assert audit["crossing_pair_count"] == 2
    assert audit["crossing_angle_histogram"]["75-90"] == 2
    assert audit["small_angle_crossing_count"] == 0
    assert audit["violations"] == []
    assert audit["spacing_violation_pairs"] == 0


@pytest.mark.parametrize("angle_deg,expected_bin", [
    (0.5, "0-1"), (3.0, "1-5"), (7.0, "5-10"), (15.0, "10-20"),
    (25.0, "20-30"), (40.0, "30-45"), (50.0, "45-60"), (70.0, "60-75"),
    (89.0, "75-90"), (90.0, "75-90"),
])
def test_crossing_angle_histogram_bins(angle_deg, expected_bin):
    angle = math.radians(angle_deg)
    span = 400.0 / max(math.sin(angle), 1e-3)  # keep the far ends well outside
    horizontal = [line((-span, 0.0), (span, 0.0))]
    other = [line((-span, -span * math.tan(angle)),
                  (span, span * math.tan(angle)))] if angle_deg < 90.0 else \
            [line((0.0, -span), (0.0, span))]
    result = pair(horizontal, other)
    assert result["valid"] is True, result
    assert len(result["crossings"]) == 1
    angle_measured = math.degrees(math.asin(result["crossings"][0]["sine"]))
    audit = V.audit_route_pairs([prepare(1, horizontal), prepare(2, other)])
    histogram = audit["crossing_angle_histogram"]
    assert histogram[expected_bin] == 1
    assert sum(histogram.values()) == 1
    assert 0.0 <= angle_measured <= 90.0


# ---------------------------------------------------------------------------
# the local-window exemption is exactly local
# ---------------------------------------------------------------------------
def test_parallel_clearance_boundary():
    legal = pair([line((0.0, 0.0), (10.0, 0.0))],
                 [line((0.0, CLEARANCE), (10.0, CLEARANCE))])
    assert legal["valid"] is True
    assert legal["min_distance"] == pytest.approx(CLEARANCE, abs=1e-9)

    too_close = pair([line((0.0, 0.0), (10.0, 0.0))],
                     [line((0.0, CLEARANCE - 1e-5), (10.0, CLEARANCE - 1e-5))])
    assert too_close["valid"] is False
    assert too_close["spacing"] is True


def test_routes_0_1mm_apart_rejected():
    result = pair([line((0.0, 0.0), (20.0, 0.0))],
                  [line((0.0, 0.1), (20.0, 0.1))])
    assert result["valid"] is False
    assert result["spacing"] is True
    assert result["min_distance"] == pytest.approx(0.1, abs=1e-9)


def test_crossing_does_not_excuse_remote_parallel_violation():
    crossing_route = [line((0.0, -5.0), (0.0, 5.0)),
                      line((0.0, 5.0), (8.0, 5.0)),
                      line((8.0, 5.0), (8.0, 0.1)),
                      line((8.0, 0.1), (12.0, 0.1))]
    result = pair([line((-10.0, 0.0), (10.0, 0.0))], crossing_route)
    assert result["valid"] is False
    assert result["spacing"] is True
    assert len(result["crossings"]) == 1


def test_min_non_crossing_centerline_reported():
    routes = [prepare(1, [line((0.0, 0.0), (10.0, 0.0))]),
              prepare(2, [line((0.0, 0.176), (10.0, 0.176))])]
    audit = V.audit_route_pairs(routes)
    assert audit["crossing_count"] == 0
    assert audit["min_non_crossing_centerline_mm"] == pytest.approx(0.176, abs=1e-9)


# ---------------------------------------------------------------------------
# rejected pathological relations
# ---------------------------------------------------------------------------
def test_overlap_rejected():
    result = pair([line((0.0, 0.0), (10.0, 0.0))],
                  [line((2.0, 0.0), (8.0, 0.0))])
    assert result["valid"] is False
    assert result["overlap"] is True
    assert result["crossings"] == []


def test_intersection_at_route_endpoint_is_touch():
    result = pair([line((-5.0, 0.0), (5.0, 0.0))],
                  [line((0.0, 0.0), (0.0, 5.0))])
    assert result["valid"] is False
    assert result["touch"] is True
    assert result["overlap"] is False


def test_collinear_endpoint_contact_rejected():
    result = pair([line((0.0, 0.0), (5.0, 0.0))],
                  [line((5.0, 0.0), (10.0, 0.0))])
    assert result["valid"] is False
    assert result["touch"] is True


def test_tangential_arc_contact_rejected():
    # Two radius-5 semicircles touching at (5, 0), which is interior to both
    # primitives: only the sine<1e-7 tangency rule can reject this.
    first = [arc((0.0, 0.0), RADIUS, -math.pi / 2.0, math.pi)]
    second = [arc((10.0, 0.0), RADIUS, math.pi - 0.5, 1.0)]
    result = pair(first, second)
    assert result["valid"] is False
    assert result["touch"] is True
    assert result["crossings"] == []


def test_crossing_zone_overlap_rejected():
    """Two near-tangent crossings close together cannot excuse a whole pair."""
    first = [line((-10.0, 4.999), (10.0, 4.999))]
    second = [arc((0.0, 0.0), RADIUS, 0.0, math.pi)]
    result = pair(first, second)
    assert result["valid"] is False
    assert result["crossing_zone_overlap"] is True
    assert len(result["crossings"]) == 2


def test_arc_crossing_curvature_violation_rejected():
    result = pair([line((-10.0, 2.0), (10.0, 2.0))],
                  [arc((0.0, 0.0), RADIUS, 0.0, math.pi)])
    assert len(result["crossings"]) == 2
    expected = math.degrees(math.acos(2.0 / RADIUS))
    for crossing in result["crossings"]:
        assert math.degrees(math.asin(crossing["sine"])) == pytest.approx(expected)
    # The straight-line window is too short for the curved second route.
    assert result["valid"] is False
    assert result["spacing"] is True


# ---------------------------------------------------------------------------
# broad phase
# ---------------------------------------------------------------------------
def test_far_routes_are_not_a_candidate_pair():
    assert pair([line((0.0, 0.0), (1.0, 0.0))],
                [line((100.0, 100.0), (101.0, 100.0))]) is None
    audit = V.audit_route_pairs([prepare(1, [line((0.0, 0.0), (1.0, 0.0))]),
                                 prepare(2, [line((100.0, 100.0), (101.0, 100.0))])])
    assert audit["candidate_pair_count"] == 0
    assert audit["crossing_count"] == 0


def test_violation_list_names_both_routes():
    routes = [prepare(7, [line((0.0, 0.0), (20.0, 0.0))]),
              prepare(9, [line((0.0, 0.1), (20.0, 0.1))])]
    audit = V.audit_route_pairs(routes)
    assert len(audit["violations"]) == 1
    violation = audit["violations"][0]
    assert {violation["route_a"], violation["route_b"]} == {7, 9}
    assert violation["kinds"] == ["spacing"]
    assert violation["kind"] == "spacing"
    assert violation["distance_mm"] == pytest.approx(0.1, abs=1e-9)
    assert violation["x"] == pytest.approx(0.0, abs=1e-9)
    assert violation["y"] == pytest.approx(0.05, abs=1e-9)
    assert violation["x"] is not None and 0.0 <= violation["x"] <= 150.0


def test_violation_kinds_have_positions():
    cases = {
        "overlap": ([line((0.0, 0.0), (10.0, 0.0))],
                    [line((2.0, 0.0), (8.0, 0.0))]),
        "touch": ([line((-5.0, 0.0), (5.0, 0.0))],
                  [line((0.0, 0.0), (0.0, 5.0))]),
        "crossing_window_overlap": (
            [line((-10.0, 4.999), (10.0, 4.999))],
            [arc((0.0, 0.0), RADIUS, 0.0, math.pi)]),
    }
    for expected_kind, (first, second) in cases.items():
        result = pair(first, second)
        assert result["valid"] is False
        assert len(result["violations"]) == 1
        violation = result["violations"][0]
        assert violation["kind"] == expected_kind
        assert math.isfinite(violation["x"])
        assert math.isfinite(violation["y"])
        assert -1.0 <= violation["x"] <= 151.0
        assert -1.0 <= violation["y"] <= 151.0


def test_crossing_window_overlap_alias_present():
    routes = [prepare(1, [line((-10.0, 4.999), (10.0, 4.999))]),
              prepare(2, [arc((0.0, 0.0), RADIUS, 0.0, math.pi)])]
    audit = V.audit_route_pairs(routes)
    assert audit["crossing_zone_overlap_pairs"] == 1
    assert audit["crossing_window_overlap_pairs"] == 1
    assert audit["violations"][0]["kind"] == "crossing_window_overlap"


# ---------------------------------------------------------------------------
# optional "exact" policy sensitivity (former quick-index semantics)
# ---------------------------------------------------------------------------
def test_exact_policy_arc_crossing_is_the_sensitivity_difference():
    """Legacy local windows flag a shallow arc-spacing deficit; exact exempts it."""
    first = prepare(1, [line((-10.0, 2.0), (10.0, 2.0))])
    second = prepare(2, [arc((0.0, 0.0), RADIUS, 0.0, math.pi)])
    legacy = V.evaluate_pair(first, second)
    assert legacy["valid"] is False
    assert [item["kind"] for item in legacy["violations"]] == ["spacing"]
    deficit = CLEARANCE - legacy["violations"][0]["distance_mm"]
    assert 0.0 < deficit < 0.001  # sub-micron-to-micron window shortfall
    exact = V.evaluate_pair(first, second, policy="exact")
    assert exact["valid"] is True
    assert exact["violations"] == []
    legacy_audit = V.audit_route_pairs([first, second])
    exact_audit = V.audit_route_pairs([first, second], policy="exact")
    assert legacy_audit["policy"] == "legacy"
    assert exact_audit["policy"] == "exact"
    assert exact_audit["spacing_violation_pairs"] == 0
    assert legacy_audit["spacing_violation_pairs"] == 1


def test_compare_exact_report_field(legacy_80, dataset):
    """Legacy remains authoritative; exact-policy sensitivity is reported."""
    records = []
    for item in legacy_80:
        record = dict(item["record"])
        record["_status"] = "routed"
        records.append(record)
    report = V.validate_dataset(records, dataset["endpoints"], audit_pairs=True,
                                compare_exact=True)
    assert report["policy_used"] == "legacy"
    assert report["passed"] is True, report["errors"]
    assert report["violations"] == []
    assert "exact_policy_violations" in report
    assert report["exact_policy_violation_count"] == len(report["exact_policy_violations"])
    assert "sensitivity only" in report["exact_policy_note"]
