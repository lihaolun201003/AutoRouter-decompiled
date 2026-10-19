"""Unit tests for the strict local-crossing-window acceptance policy.

Authoritative definition: ``four_side_1024/abcd/SPEC.md`` §2.1
(``crossing_policy='strict'``).  The tests exercise the independent validator
implementation in ``four_side_1024.d56.validate_d56`` (``policy='strict'``) and
prove that the exemption is *only* the exact minimal near-region of a genuine
transverse crossing:

(a) two perpendicular (axis-aligned) lines: analytic half width
    ``clearance + 2*sagitta`` (i.e. ``h* = clearance``), and remote
    sub-clearance approaches outside the window are still rejected;
(b) line-arc and arc-arc crossings: every solved ``h*`` equals dense brute-force
    sampling of the real geometry (1e-4 mm resolution) within 1e-3 mm;
(c) a pair that the historical ``exact`` policy accepts by exempting whole
    intersected primitive pairs (and a double crossing) is rejected by strict;
(d) a shallow crossing whose clearance band is not left within the 4.0 mm
    maximum window is rejected as ``crossing_window_excessive``;
(e) overlap, tangency, endpoint touch and double crossing are still rejected;
(f) coincident crossing points (line/arc junction on the partner) form one
    grouped window instead of a spurious window-overlap violation;
(g) a crossing near a route end clamps the window at the route end (legal, not
    excessive); two local windows that cannot be separated are rejected as
    ``crossing_window_overlap``;
(h) determinism, audit/CLI wiring, and the router-vs-validator crosscheck
    harness (``four_side_1024/abcd/crosscheck_strict.py``) on a synthetic file.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from four_side_1024.d56 import validate_d56 as V

CLEARANCE = V.CLEARANCE
SAGITTA = V.SAGITTA
MARGIN = 2.0 * SAGITTA
LIMIT = CLEARANCE - V.STRICT_LIMIT_TOL
HISTORICAL_ROUTES = (Path(__file__).resolve().parents[3]
                     / "outputs" / "four_side_1024_d56_optimized" / "routes.json")


# ---------------------------------------------------------------------------
# geometry helpers (plain primitives; the validator is exercised directly)
# ---------------------------------------------------------------------------
def line(p0, p1):
    return {"kind": "line", "p0": list(p0), "p1": list(p1), "layer": 0}


def arc(center, radius, start, sweep):
    cx, cy = center
    p0 = (cx + radius * math.cos(start), cy + radius * math.sin(start))
    end = start + sweep
    p1 = (cx + radius * math.cos(end), cy + radius * math.sin(end))
    return {"kind": "arc", "p0": list(p0), "p1": list(p1),
            "center": list(center), "radius": float(radius),
            "start_angle": float(start), "sweep": float(sweep), "layer": 0}


def prepare(primitives, route_id):
    return V.prepare_route(primitives, route_id)


def pair(first, second, policy="strict"):
    return V.evaluate_pair(prepare(first, 1), prepare(second, 2), policy=policy)


def kinds(result):
    return [detail["kind"] for detail in result["violations"]]


def _brute_band_edge(prepared, s_0, direction, partner, step=1e-4):
    """Dense-sampling reference for the solved band edge (``h*``)."""
    limit = CLEARANCE - V.STRICT_LIMIT_TOL
    h = 0.0
    while h < V.STRICT_MAX_HALF_WINDOW:
        point = V._route_point_at(prepared, s_0 + direction * h)
        if V._point_prim_distance(point, partner) >= limit:
            return h
        h += step
    return None


def _check_window_against_brute_force(first, second):
    """Every crossing side must match dense sampling and the limit target."""
    result = pair(first, second)
    assert result["valid"] is True, result["violations"]
    assert len(result["crossings"]) == 1
    crossing = result["crossings"][0]
    first_prepared = prepare(first, 1)
    second_prepared = prepare(second, 2)
    sides = (
        ("half_a_left", first_prepared, crossing["sa"], -1.0,
         second_prepared.prims[0]),
        ("half_a_right", first_prepared, crossing["sa"], 1.0,
         second_prepared.prims[0]),
        ("half_b_left", second_prepared, crossing["sb"], -1.0,
         first_prepared.prims[0]),
        ("half_b_right", second_prepared, crossing["sb"], 1.0,
         first_prepared.prims[0]),
    )
    for name, prepared, s_0, direction, partner in sides:
        half = crossing[name]
        h_star = half - MARGIN
        assert h_star > 0.0
        # (1) the solved h* is where the real distance equals the limit
        point = V._route_point_at(prepared, s_0 + direction * h_star)
        assert V._point_prim_distance(point, partner) == pytest.approx(
            LIMIT, abs=1e-3), name
        # (2) dense brute-force sampling agrees within 1e-3 mm
        brute = _brute_band_edge(prepared, s_0, direction, partner)
        assert brute is not None, name
        assert brute == pytest.approx(h_star, abs=1e-3), name
        # (3) it really is the *first* exit: 1 um earlier the point is inside
        if h_star > 2e-3:
            inside = V._route_point_at(prepared, s_0 + direction * (h_star - 1e-3))
            assert V._point_prim_distance(inside, partner) < LIMIT, name


# ---------------------------------------------------------------------------
# (a) perpendicular lines: analytic window, outside-window spacing enforced
# ---------------------------------------------------------------------------
def test_perpendicular_lines_window_is_analytic_clearance_plus_margin():
    result = pair([line((-5.0, 0.0), (5.0, 0.0))],
                  [line((0.0, -5.0), (0.0, 5.0))])
    assert result["valid"] is True
    assert len(result["crossings"]) == 1
    crossing = result["crossings"][0]
    assert crossing["straight"] is True
    # SPEC §2.1 item 6: two axis-aligned lines -> sine == 1 and the half width is
    # analytic h* + 2*sagitta with h* == clearance exactly.
    for key in ("half_a_left", "half_a_right", "half_b_left", "half_b_right"):
        assert crossing[key] == pytest.approx(CLEARANCE + MARGIN, abs=1e-12)
        assert crossing[key] - MARGIN == pytest.approx(CLEARANCE, abs=1e-6)
    assert math.degrees(math.asin(crossing["sine"])) == pytest.approx(90.0)


def test_remote_parallel_approach_outside_crossing_window_is_rejected():
    # A crosses B at (0,0); a second segment of A runs 0.1 mm from B far away
    # from the crossing.  The crossing window must not excuse it.
    first = [line((-5.0, 0.0), (5.0, 0.0)),
             line((0.1, 0.2), (0.1, 2.0))]
    second = [line((0.0, -5.0), (0.0, 5.0))]
    result = pair(first, second)
    assert result["valid"] is False
    assert "spacing" in kinds(result)
    spacing = [d for d in result["violations"] if d["kind"] == "spacing"][0]
    assert spacing["distance_mm"] == pytest.approx(0.1, abs=1e-9)


# ---------------------------------------------------------------------------
# (b) line-arc / arc-arc windows match dense brute-force sampling
# ---------------------------------------------------------------------------
def test_line_arc_window_matches_dense_sampling():
    quarter_arc = arc((0.0, 0.0), 5.0, 0.0, math.pi / 2.0)
    vertical = line((2.0, 0.0), (2.0, 6.0))
    _check_window_against_brute_force([vertical], [quarter_arc])


def test_arc_arc_window_matches_dense_sampling():
    first_arc = arc((0.0, 0.0), 5.0, 0.0, math.pi / 2.0)
    second_arc = arc((5.0, 0.0), 5.0, math.pi / 2.0, math.pi / 2.0)
    _check_window_against_brute_force([first_arc], [second_arc])


# ---------------------------------------------------------------------------
# (c) the historical whole-primitive-pair exemption is rejected by strict
# ---------------------------------------------------------------------------
def test_exact_policy_exemption_is_rejected_by_strict():
    # A single arc crosses a line once and its far (route-end) part passes
    # 0.15 mm from the same line, outside the local crossing window.  ``exact``
    # exempts the whole intersected primitive pair; strict must reject it.
    alpha = math.radians(154.5)
    long_arc = arc((0.0, 0.0), 5.0, 0.0, alpha)
    line_b = [line((-10.0, 2.0), (10.0, 2.0))]
    exact = pair([long_arc], line_b, policy="exact")
    assert exact["valid"] is True and exact["violations"] == []
    strict = pair([long_arc], line_b, policy="strict")
    assert strict["valid"] is False
    assert "spacing" in kinds(strict)
    distance = [d for d in strict["violations"] if d["kind"] == "spacing"][0][
        "distance_mm"]
    assert 0.10 < distance < LIMIT
    assert distance == pytest.approx(0.1525, abs=2e-3)


def test_double_cross_of_one_primitive_pair_is_rejected():
    # Line y=2 crosses the same semicircular arc twice: ``exact`` exempts the
    # whole primitive pair, strict reports ``double_cross``.
    semicircle = arc((0.0, 0.0), 5.0, 0.0, math.pi)
    horizontals = [line((-10.0, 2.0), (10.0, 2.0))]
    exact = pair(horizontals, [semicircle], policy="exact")
    assert exact["valid"] is True
    strict = pair(horizontals, [semicircle], policy="strict")
    assert strict["valid"] is False
    assert "double_cross" in kinds(strict)


# ---------------------------------------------------------------------------
# (d) shallow crossing with a long sub-clearance run -> crossing_window_excessive
# ---------------------------------------------------------------------------
def test_shallow_crossing_with_long_sub_limit_run_is_excessive():
    # 5.7 deg crossing, then the route turns back and keeps running inside the
    # 0.175 mm band for more than max_half_window = 4 mm, so no minimal local
    # window exists -> strict must reject, exact historically accepts.
    first = [line((-1.0, -0.1), (1.5, 0.15)),   # crosses y=0 at (0,0), 5.7 deg
             line((1.5, 0.15), (6.5, -0.35))]   # crosses y=0 again, then stays low
    second = [line((-20.0, 0.0), (20.0, 0.0))]
    strict = pair(first, second)
    assert strict["valid"] is False
    assert "crossing_window_excessive" in kinds(strict)
    exact = pair(first, second, policy="exact")
    assert exact["valid"] is True


def test_shallow_but_legal_crossing_does_not_trigger_excessive():
    # A 6 degree crossing of two straight lines leaves the band inside the cap.
    angle = math.radians(6.0)
    span = 200.0 / math.sin(angle)
    horizontal = [line((-span, 0.0), (span, 0.0))]
    slanted = [line((-span, -span * math.tan(angle)),
                    (span, span * math.tan(angle)))]
    result = pair(horizontal, slanted)
    assert result["valid"] is True
    assert "crossing_window_excessive" not in kinds(result)
    half = result["crossings"][0]["half_a_left"]
    assert half == pytest.approx(LIMIT / math.sin(angle) + MARGIN, abs=2e-3)


# ---------------------------------------------------------------------------
# (e) pathological relations are still rejected
# ---------------------------------------------------------------------------
def test_overlap_rejected():
    result = pair([line((0.0, 0.0), (10.0, 0.0))],
                  [line((2.0, 0.0), (8.0, 0.0))])
    assert result["valid"] is False
    assert "overlap" in kinds(result)


def test_tangent_touch_rejected():
    first = [arc((0.0, 0.0), 5.0, -math.pi / 2.0, math.pi)]
    second = [arc((10.0, 0.0), 5.0, math.pi - 0.5, 1.0)]
    result = pair(first, second)
    assert result["valid"] is False
    assert "tangent_touch" in kinds(result)


def test_near_parallel_crossing_below_five_degrees_is_tangent_touch():
    angle = math.radians(3.0)
    span = 400.0
    result = pair([line((-span, 0.0), (span, 0.0))],
                  [line((-span, -span * math.tan(angle)),
                        (span, span * math.tan(angle)))])
    assert result["valid"] is False
    assert "tangent_touch" in kinds(result)


def test_endpoint_touch_rejected():
    result = pair([line((-5.0, 0.0), (5.0, 0.0))],
                  [line((0.0, 0.0), (0.0, 5.0))])
    assert result["valid"] is False
    assert "endpoint_touch" in kinds(result)


def test_crossing_window_overlap_rejected():
    # Two crossings 0.1 mm apart: their local windows cannot be separated.
    horizontal = [line((-5.0, 0.0), (5.0, 0.0))]
    verticals = [line((0.0, -5.0), (0.0, 5.0)),
                 line((0.1, -5.0), (0.1, 5.0))]
    result = pair(horizontal, verticals)
    assert result["valid"] is False
    assert "crossing_window_overlap" in kinds(result)
    assert result["crossing_zone_overlap"] is True


# ---------------------------------------------------------------------------
# (f) coincident crossings at a primitive junction are one grouped window
# ---------------------------------------------------------------------------
def test_coincident_crossings_at_a_junction_are_grouped():
    # Route A turns from a straight line into a quarter arc exactly at (5,0);
    # route B's vertical line passes through that same junction, so both of A's
    # primitives intersect B at one physical point -> one grouped window.
    first = [line((0.0, 0.0), (5.0, 0.0)),
             arc((5.0, 5.0), 5.0, -math.pi / 2.0, math.pi / 2.0)]
    second = [line((5.0, -5.0), (5.0, 5.0))]
    result = pair(first, second)
    assert result["valid"] is True, result["violations"]
    assert len(result["crossings"]) == 1
    crossing = result["crossings"][0]
    assert len(crossing["members"]) == 2
    assert crossing["point"] == pytest.approx((5.0, 0.0), abs=1e-12)


# ---------------------------------------------------------------------------
# (g) route-end clamp is legal; non-separable windows are rejected
# ---------------------------------------------------------------------------
def test_window_clamped_at_route_end_is_legal():
    # The arc route ends while it is still inside the clearance band of the
    # vertical line (0.087 mm away): the window is clamped at the route end and
    # this legal near-port crossing is not flagged as excessive.
    alpha = math.radians(67.5)
    arc_route = [arc((0.0, 0.0), 5.0, 0.0, alpha)]
    vertical = [line((2.0, 0.0), (2.0, 6.0))]
    result = pair(arc_route, vertical)
    assert result["valid"] is True, result["violations"]
    assert "crossing_window_excessive" not in kinds(result)
    assert len(result["crossings"]) == 1
    crossing = result["crossings"][0]
    prepared = prepare(arc_route, 1)
    room = prepared.length - crossing["sa"]
    assert 0.0 < room < 0.1
    assert crossing["half_a_right"] == pytest.approx(room + MARGIN, abs=1e-9)


# ---------------------------------------------------------------------------
# (h) determinism, audit wiring, crosscheck harness
# ---------------------------------------------------------------------------
def test_strict_verdict_is_deterministic():
    first = [line((2.0, 0.0), (2.0, 6.0))]
    second = [arc((0.0, 0.0), 5.0, 0.0, math.pi / 2.0)]
    one = pair(first, second)
    two = pair(first, second)
    assert one["valid"] == two["valid"]
    assert one["violations"] == two["violations"]
    for left, right in zip(one["crossings"], two["crossings"]):
        for key in ("half_a_left", "half_a_right",
                    "half_b_left", "half_b_right", "sa", "sb", "sine"):
            assert left[key] == right[key]


def test_audit_route_pairs_strict_reports_window_statistics():
    routes = [prepare([line((-5.0, 0.0), (5.0, 0.0))], 1),
              prepare([line((0.0, -5.0), (0.0, 5.0))], 2)]
    audit = V.audit_route_pairs(routes, policy="strict")
    assert audit["policy"] == "strict"
    assert audit["candidate_pair_count"] == 1
    assert audit["crossing_count"] == 1
    assert audit["crossing_window_count"] == 1
    assert audit["crossing_window_max_mm"] == pytest.approx(
        CLEARANCE + MARGIN, abs=1e-6)
    assert audit["crossing_window_mean_mm"] == pytest.approx(
        CLEARANCE + MARGIN, abs=1e-6)
    assert audit["crossing_window_excessive_pairs"] == 0
    assert audit["double_cross_pairs"] == 0
    assert audit["violations"] == []
    assert audit["crossing_window_half_histogram_mm"] is not None
    assert audit["crossing_window_by_angle_bin"]["75-90"]["crossings"] == 1


def test_validate_dataset_accepts_strict_and_reports_new_fields():
    records = [
        {"route_id": 1,
         "primitives": [line((0.05, 75.0), (149.95, 75.0))]},
        {"route_id": 2,
         "primitives": [line((75.0, 0.05), (75.0, 149.95))]},
    ]
    report = V.validate_dataset(records, {}, policy="strict", audit_pairs=True)
    assert report["policy_used"] == "strict"
    assert report["pair_audit"] == "exact_independent"
    assert report["crossing_count"] == 1
    assert report["crossing_window_count"] == 1
    assert report["crossing_window_max_mm"] == pytest.approx(
        CLEARANCE + MARGIN, abs=1e-6)
    assert report["crossing_window_excessive_pairs"] == 0
    assert report["double_cross_pairs"] == 0
    assert report["violations"] == []
    assert report["policy"]["centerline_clearance_limit_mm"] == pytest.approx(
        LIMIT, abs=0.0)
    assert "lim = clearance-1e-7" in report["policy"]["crossing_window"]
    with pytest.raises(ValueError):
        V.validate_dataset(records, {}, policy="not_a_policy")


def _write_routes_file(path, routes):
    payload = {
        "schema": "four_side_1024_d56_optimized_routes_v1",
        "units": "mm",
        "layer": 0,
        "routes": [
            {"route_id": route_id, "status": "routed", "relation": "opposite",
             "pair": "NS", "source_side": "N", "target_side": "S",
             "layer": 0, "primitives": primitives}
            for route_id, primitives in routes
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_crosscheck_harness_agrees_on_synthetic_routes_file(tmp_path):
    from four_side_1024.abcd.crosscheck_strict import crosscheck
    routes = [
        (1, [line((0.0, 0.0), (10.0, 0.0))]),
        (2, [line((5.0, -5.0), (5.0, 5.0))]),          # legal crossing with route 1
        (3, [line((0.0, 3.0), (10.0, 3.0))]),          # legal, far from 1 and 2
        (4, [line((0.0, 0.0), (10.0, 0.0))]),          # overlap with route 1
    ]
    routes_path = _write_routes_file(tmp_path / "routes.json", routes)
    summary = crosscheck(routes_path)
    assert summary["passed"] is True
    assert summary["mismatch_count"] == 0
    assert summary["compared_pair_count"] >= 3
    assert summary["invalid_both_pairs"] >= 1
    assert 1 in summary["strict_failed_route_ids"]
    assert 4 in summary["strict_failed_route_ids"]
    assert summary["window_consistency"]["count_matches"] is True


@pytest.mark.skipif(not HISTORICAL_ROUTES.exists(),
                    reason="historical D56 deliverable not present")
def test_historical_467_strict_verdict_is_465_of_467():
    """Integration: the delivered 467 must fail strict on exactly one pair.

    Expected: the ``exact`` (historical) policy accepts all 467, the strict
    policy rejects only the route pair (460, 989) as ``crossing_window_overlap``
    (both routes are involved in that single pair).
    """
    strict_report = V.build_report(run_dir=HISTORICAL_ROUTES.parent,
                                   policy="strict")
    assert strict_report["routed_count"] == 467
    assert strict_report["d56_failed_count"] == 0
    invalid_pairs = {(item["route_a"], item["route_b"])
                     for item in strict_report["violations"]}
    assert invalid_pairs == {(460, 989)}
    assert {item["kind"] for item in strict_report["violations"]} == {
        "crossing_window_overlap"}
    failed_routes = sorted({route for pair_ids in invalid_pairs
                            for route in pair_ids})
    assert failed_routes == [460, 989]
    assert strict_report["routed_count"] - len(failed_routes) == 465
    assert strict_report["crossing_window_count"] == 57029
    assert strict_report["crossing_window_max_mm"] == pytest.approx(2.3398,
                                                                    abs=1e-3)
    assert strict_report["crossing_window_total_length_mean_mm"] == pytest.approx(
        0.7948, abs=1e-3)
    assert strict_report["crossing_window_excessive_pairs"] == 0
    exact_report = V.build_report(run_dir=HISTORICAL_ROUTES.parent,
                                  policy="exact")
    assert exact_report["passed"] is True
    assert exact_report["violations"] == []
