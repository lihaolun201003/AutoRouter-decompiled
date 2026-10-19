"""Tests for the independent FSLW R=40 mm / 0.080 mm-clearance validator.

Contract: ``four_side_1024/fslw/SPEC.md`` (fixed radius R=40 mm, waveguide width
0.050 mm, minimum edge gap 0.030 mm -> centreline clearance 0.080 mm, sagitta
0.0005 mm, min crossing angle 5 deg, max half window 4.0 mm, dual-height real
IEC 2x16 port model) and ``four_side_1024/abcd/SPEC.md`` §2.1 for the unchanged
``strict`` local crossing-window math with clearance = 0.080 mm.

Explicit R=40 pitfalls covered: quarter arcs of radius 40 (rejecting 39.999),
short-S pairs with theta up to ~90 deg (lateral shift up to 80 mm), board
bounds around a 40 mm turn, the analytic perpendicular line window at 0.080,
and the 0.0799 / 0.0801 non-crossing spacing boundary.  Router-emitted geometry
(``four_side_1024.fslw.geom``) is fed back into the validator so the two
implementations cannot drift apart silently.
"""
from __future__ import annotations

import json
import math

import pytest

from four_side_1024.fslw import geom as G
from four_side_1024.fslw import validate_fslw as V

RADIUS = 40.0
WIDTH = 0.05
EDGE_GAP = 0.03
CLEARANCE = 0.08
SAGITTA = 0.0005
LIMIT = CLEARANCE - V.STRICT_LIMIT_TOL
MARGIN = 2.0 * SAGITTA


# ---------------------------------------------------------------------------
# primitive / route builders (independent of the router modules)
# ---------------------------------------------------------------------------
def line(p0, p1, layer=0):
    return {"kind": "line", "p0": [float(p0[0]), float(p0[1])],
            "p1": [float(p1[0]), float(p1[1])], "layer": layer}


def arc(center, start, sweep, radius=RADIUS):
    cx, cy = float(center[0]), float(center[1])
    p0 = (cx + radius * math.cos(start), cy + radius * math.sin(start))
    p1 = (cx + radius * math.cos(start + sweep),
          cy + radius * math.sin(start + sweep))
    return {"kind": "arc", "p0": [p0[0], p0[1]], "p1": [p1[0], p1[1]],
            "center": [cx, cy], "radius": float(radius),
            "start_angle": float(start), "sweep": float(sweep), "layer": 0}


def arc_chain(start, heading, sweeps, radius=RADIUS):
    """G1-continuous arc chain (same construction as the router's short S)."""
    primitives = []
    cursor = (float(start[0]), float(start[1]))
    current = float(heading)
    for sweep in sweeps:
        sign = 1.0 if sweep > 0 else -1.0
        center = (cursor[0] - sign * radius * math.sin(current),
                  cursor[1] + sign * radius * math.cos(current))
        start_angle = current - sign * math.pi / 2.0
        end = (center[0] + radius * math.cos(start_angle + sweep),
               center[1] + radius * math.sin(start_angle + sweep))
        primitives.append(arc(center, start_angle, sweep, radius=radius))
        primitives[-1]["p0"] = [cursor[0], cursor[1]]
        primitives[-1]["p1"] = [end[0], end[1]]
        cursor = end
        current += sweep
    return primitives, cursor, current


def short_s_route(displacement, start=(60.0, 40.0), radius=RADIUS):
    """Lead line + two-arc short S + tail line, exactly the historical formula."""
    theta = math.acos(1.0 - abs(displacement) / (2.0 * radius))
    primitives, end, end_dir = arc_chain(start, 0.0, [theta, -theta], radius)
    route = [line((start[0] - 30.0, start[1]), start)] + primitives
    route.append(line(end, (min(end[0] + 20.0, 150.0), end[1])))
    return route, theta, end


def prepare(primitives, route_id=1):
    return V.prepare_route(primitives, route_id)


def pair(first, second, policy="strict"):
    return V.evaluate_pair(prepare(first, 1), prepare(second, 2), policy=policy)


def kinds(result):
    return [detail["kind"] for detail in result["violations"]]


# ---------------------------------------------------------------------------
# (1) fixed R=40 mm quarter arcs
# ---------------------------------------------------------------------------
def test_r40_quarter_arc_route_is_legal():
    route = [
        line((10.0, 0.0), (10.0, 50.0)),
        arc((50.0, 50.0), math.pi, -math.pi / 2.0),
        line((50.0, 90.0), (140.0, 90.0)),
    ]
    result = V.check_route_primitives(route)
    assert result["passed"] is True, result["errors"]
    assert all(abs(prim["radius"] - 40.0) <= 1e-9
               for prim in route if prim["kind"] == "arc")


def test_radius_below_40_is_rejected():
    bad_arc = arc((50.0, 50.0), math.pi, -math.pi / 2.0, radius=39.999)
    result = V.check_route_primitives([bad_arc])
    assert result["passed"] is False
    assert any(error.startswith("arc_radius") for error in result["errors"])


def test_radius_40_arc_with_positive_sweep_is_legal():
    # Left quarter turn at R=40: travel +y, arc from (60,50) to (20,90), then
    # travel -x (tangent continuity holds).
    route = [
        line((60.0, 0.0), (60.0, 50.0)),
        arc((20.0, 50.0), 0.0, math.pi / 2.0),
        line((20.0, 90.0), (2.0, 90.0)),
    ]
    result = V.check_route_primitives(route)
    assert result["passed"] is True, result["errors"]


# ---------------------------------------------------------------------------
# (2) R=40 short-S pair: theta can approach 90 degrees (lateral shift up to 2R)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("displacement", [2.0, 10.0, 25.0, 40.0, 60.0, 70.0, 79.0])
def test_short_s_with_r40_is_legal(displacement):
    route, theta, end = short_s_route(displacement)
    assert abs(2.0 * RADIUS * (1.0 - math.cos(theta))) == pytest.approx(
        displacement, abs=1e-9)
    result = V.check_route_primitives(route)
    assert result["passed"] is True, result["errors"]
    assert math.degrees(theta) < 90.0


def test_short_s_theta_near_90_degrees_is_legal():
    # d = 79.999 mm -> theta = 89.9993 deg; the pair rule must not fall back to
    # a small-angle approximation and must keep the exact 2R(1-cos theta) form.
    route, theta, end = short_s_route(79.999)
    assert math.degrees(theta) > 89.99
    result = V.check_route_primitives(route)
    assert result["passed"] is True, result["errors"]


def test_short_s_wrong_theta_is_rejected():
    route, theta, _end = short_s_route(20.0)
    tampered = [dict(prim) for prim in route]
    second_arc = [index for index, prim in enumerate(tampered)
                  if prim["kind"] == "arc"][1]
    tampered[second_arc]["sweep"] = -abs(tampered[second_arc]["sweep"]) * 0.9
    result = V.check_route_primitives(tampered)
    assert result["passed"] is False


def test_single_non_quarter_arc_is_rejected():
    result = V.check_route_primitives([arc((0.0, 0.0), 0.0, 0.5)])
    assert result["passed"] is False
    assert any("unpaired" in error for error in result["errors"])


# ---------------------------------------------------------------------------
# (3) perpendicular line-line crossing window is analytic at clearance 0.080
# ---------------------------------------------------------------------------
def test_perpendicular_lines_window_is_clearance_plus_margin():
    result = pair([line((-20.0, 0.0), (20.0, 0.0))],
                  [line((0.0, -20.0), (0.0, 20.0))])
    assert result["valid"] is True
    assert len(result["crossings"]) == 1
    crossing = result["crossings"][0]
    for key in ("half_a_left", "half_a_right", "half_b_left", "half_b_right"):
        assert crossing[key] == pytest.approx(CLEARANCE + MARGIN, abs=1e-12)
        assert crossing[key] - MARGIN == pytest.approx(CLEARANCE, abs=1e-6)
    assert crossing["straight"] is True


def test_crossing_does_not_excuse_remote_parallel_approach():
    first = [line((-20.0, 0.0), (20.0, 0.0)),
             line((0.05, 2.0), (0.05, 30.0))]
    second = [line((0.0, -20.0), (0.0, 20.0))]
    result = pair(first, second)
    assert result["valid"] is False
    assert "spacing" in kinds(result)


# ---------------------------------------------------------------------------
# (4) strict minimal-window properties: whole-pair exemption is not enough
# ---------------------------------------------------------------------------
def test_exact_policy_exemption_is_rejected_by_strict_at_008():
    # Single R=40 arc crossing a line once; the arc's route-end part comes
    # within ~0.05 mm of the same line, far outside the local crossing window.
    phi_cross = math.asin(0.75)            # crossing at y = 30 on the circle
    delta = 0.0019
    end_angle = math.pi - phi_cross - delta
    long_arc = [arc((0.0, 0.0), 0.0, end_angle)]
    target_line = [line((-100.0, 30.0), (100.0, 30.0))]
    exact = pair(long_arc, target_line, policy="exact")
    assert exact["valid"] is True and exact["violations"] == []
    strict = pair(long_arc, target_line, policy="strict")
    assert strict["valid"] is False
    assert "spacing" in kinds(strict)
    distance = [d for d in strict["violations"] if d["kind"] == "spacing"][0][
        "distance_mm"]
    assert 0.0 < distance < LIMIT


def test_double_cross_at_r40_is_rejected_by_strict():
    # Line y=30 crosses an R=40 semicircle twice: exact exempts the whole pair,
    # strict reports double_cross.
    semicircle = [arc((0.0, 0.0), 0.0, math.pi)]
    horizontals = [line((-100.0, 30.0), (100.0, 30.0))]
    assert pair(horizontals, semicircle, policy="exact")["valid"] is True
    strict = pair(horizontals, semicircle, policy="strict")
    assert strict["valid"] is False
    assert "double_cross" in kinds(strict)


# ---------------------------------------------------------------------------
# (5) board bounds with a 40 mm turn next to the board edge
# ---------------------------------------------------------------------------
def test_r40_turn_inside_board_is_legal():
    route = [
        line((10.0, 0.0), (10.0, 20.0)),
        arc((50.0, 20.0), math.pi, -math.pi / 2.0),
        line((50.0, 60.0), (140.0, 60.0)),
    ]
    result = V.check_route_primitives(route)
    assert result["passed"] is True, result["errors"]
    assert result["checks"]["board_bounds"] is True


def test_r40_turn_stroke_outside_board_is_rejected():
    # The quarter arc ends at angle 0 (radial +x), so its outer stroke reaches
    # x = 110 + 40 + 0.025 = 150.025 > 150 and the board bound is violated.
    route = [
        line((60.0, 100.0), (110.0, 100.0)),
        arc((110.0, 60.0), math.pi / 2.0, -math.pi / 2.0),
        line((150.0, 60.0), (150.0, 0.0)),
    ]
    result = V.check_route_primitives(route)
    assert result["checks"]["board_bounds"] is False
    assert result["passed"] is False
    assert any(error.startswith("board_out_of_bounds") for error in result["errors"])


# ---------------------------------------------------------------------------
# (6) non-crossing spacing: 0.080 mm boundary (0.0799 rejected / 0.0801 legal)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("offset,valid", [(0.0799, False), (0.0801, True)])
def test_parallel_spacing_boundary_at_008(offset, valid):
    result = pair([line((0.0, 0.0), (50.0, 0.0))],
                  [line((0.0, offset), (50.0, offset))])
    assert result["valid"] is valid
    if valid:
        assert result["min_distance"] == pytest.approx(offset, abs=1e-9)
    else:
        assert "spacing" in kinds(result)
        assert result["min_distance"] == pytest.approx(offset, abs=1e-9)


def test_exactly_008_parallel_spacing_is_legal():
    # many FSLW tracks sit exactly at the 0.080 mm clearance: it is legal
    # (violation threshold is lim = 0.0799999), but a 0.0799 mm gap is not.
    result = pair([line((0.0, 0.0), (50.0, 0.0))],
                  [line((0.0, CLEARANCE), (50.0, CLEARANCE))])
    assert result["valid"] is True
    assert result["min_distance"] == pytest.approx(CLEARANCE, abs=1e-9)


# ---------------------------------------------------------------------------
# (7) single layer and plane metadata
# ---------------------------------------------------------------------------
def test_nonzero_layer_is_rejected():
    result = V.check_route_primitives([line((10.0, 0.0), (10.0, 50.0),
                                            layer=1)])
    assert result["passed"] is False
    assert any(error.startswith("nonzero_layer") for error in result["errors"])


def test_plane_z_metadata_is_not_a_layer():
    # fslw/SPEC.md §2: z is the plane label, primitives stay 2D layer=0.
    prim = line((10.0, 0.0), (10.0, 50.0))
    prim_with_z = dict(prim, z=0.5)
    assert V.check_route_primitives([prim])["passed"] is True
    assert V.check_route_primitives([prim_with_z])["passed"] is True


# ---------------------------------------------------------------------------
# (8) dual-height real IEC 2x16 port model (independent derivation)
# ---------------------------------------------------------------------------
def test_port_model_has_1024_ports_per_plane_on_the_iec_pitch():
    for plane, row in (("z1", 1), ("z2", 2)):
        endpoints = V.build_plane_endpoints(plane)
        assert len(endpoints) == 1024
        assert len({tuple(item["routing_xy"]) for item in endpoints.values()}) == 1024
        assert all(item["row"] == row and item["plane"] == plane
                   for item in endpoints.values())
        assert all(item["layer"] == 0 and item["port_model"] == V.PORT_MODEL
                   for item in endpoints.values())
    z1 = V.build_plane_endpoints("z1")
    # column 1 of connector N01: along = 7.5 + (1-8.5)*0.25 = 5.625
    assert z1["N01:1:1"]["routing_xy"] == pytest.approx([5.625, 150.0])
    assert z1["N01:1:1"]["inward"] == pytest.approx([0.0, -1.0])
    # column pitch is the IEC 0.25 mm
    c1 = z1["N01:1:1"]["routing_xy"]
    c2 = z1["N01:1:2"]["routing_xy"]
    assert abs(c1[0] - c2[0]) == pytest.approx(0.25, abs=1e-12)
    # rows are the same XY projection but different planes
    z2 = V.build_plane_endpoints("z2")
    assert z2["N01:2:1"]["routing_xy"] == pytest.approx(z1["N01:1:1"]["routing_xy"])


def test_plane_detection_from_metadata_records_and_path():
    meta = {"plane": "z2"}
    records = [{"plane": "z2", "source_endpoint": "N01:2:1"}]
    assert V.detect_plane(meta, records) == "z2"
    assert V.detect_plane({}, [{"source_endpoint": "N01:1:1",
                                "target_endpoint": "S01:1:1"}]) == "z1"
    assert V.detect_plane({}, [{"source_endpoint": "N01:2:1"}]) == "z2"


def test_single_route_through_real_ports_passes_endpoint_checks():
    points = V.build_plane_endpoints("z1")
    source = points["S01:1:1"]
    target = points["N01:1:1"]
    x = source["routing_xy"][0]
    route = [line((x, 0.0), (x, 150.0))]
    result = V.check_route_primitives(route, source, target)
    assert result["passed"] is True, result["errors"]
    assert result["endpoints_checked"] is True
    assert result["checks"]["endpoints_fixed"] is True
    assert result["checks"]["inout_directions"] is True


# ---------------------------------------------------------------------------
# (9) router-emitted R=40 geometry must validate (implementation pairing)
# ---------------------------------------------------------------------------
def test_router_short_s_geometry_validates():
    for shift in (5.0, 20.0, 40.0, 70.0, 79.9):
        primitives, end, _direction = G.short_s((20.0, 20.0), (1.0, 0.0), shift)
        assert primitives is not None
        route = ([line((0.0, 20.0), (20.0, 20.0))] + primitives
                 + [line(end, (end[0] + 10.0, end[1]))])
        result = V.check_route_primitives(route)
        assert result["passed"] is True, (shift, result["errors"])


def test_router_adjacent_templates_validate():
    p, q = (20.0, 0.0), (150.0, 60.0)
    for build in (lambda: G.adjacent_l(p, q),
                  lambda: G.adjacent_turn_shift(p, q, 60.0),
                  lambda: G.adjacent_left_y(p, q, 60.0, 40.0)):
        primitives = build()
        if primitives is None:
            continue
        result = V.check_route_primitives(primitives)
        assert result["passed"] is True, result["errors"]


# ---------------------------------------------------------------------------
# (10) determinism, audit report and crosscheck harness
# ---------------------------------------------------------------------------
def test_strict_verdict_is_deterministic():
    first = [line((2.0, 0.0), (2.0, 60.0))]
    second = [arc((0.0, 0.0), 0.0, math.pi / 2.0)]
    one = pair(first, second)
    two = pair(first, second)
    assert one["valid"] == two["valid"]
    assert one["violations"] == two["violations"]
    for left, right in zip(one["crossings"], two["crossings"]):
        for key in ("half_a_left", "half_a_right", "half_b_left",
                    "half_b_right", "sa", "sb", "sine"):
            assert left[key] == right[key]


def test_audit_route_pairs_strict_reports_window_statistics():
    routes = [prepare([line((-20.0, 0.0), (20.0, 0.0))], 1),
              prepare([line((0.0, -20.0), (0.0, 20.0))], 2)]
    audit = V.audit_route_pairs(routes, policy="strict")
    assert audit["policy"] == "strict"
    assert audit["crossing_count"] == 1
    assert audit["crossing_window_count"] == 1
    assert audit["crossing_window_max_mm"] == pytest.approx(
        CLEARANCE + MARGIN, abs=1e-6)
    assert audit["crossing_window_excessive_pairs"] == 0
    assert audit["violations"] == []


def _write_plane_routes_file(path, routes, plane="z1"):
    payload = {
        "schema": "four_side_1024_fslw_plane_routes_v1",
        "plane": plane,
        "layer": 0,
        "port_model": V.PORT_MODEL,
        "routes": routes,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _port_routes(points, pairs):
    records = []
    for route_id, (source_key, target_key) in enumerate(pairs, start=1):
        source = points[source_key]
        target = points[target_key]
        x = source["routing_xy"][0]
        records.append({
            "route_id": route_id, "status": "routed", "plane": "z1",
            "relation": "opposite",
            "source_endpoint": source_key, "target_endpoint": target_key,
            "primitives": [line((x, 0.0), (x, 150.0))],
        })
    return records


def test_build_report_on_synthetic_plane_file(tmp_path):
    points = V.build_plane_endpoints("z1")
    records = _port_routes(points, [("S01:1:1", "N01:1:1"),
                                    ("S02:1:1", "N02:1:1")])
    routes_path = _write_plane_routes_file(tmp_path / "routes.json", records)
    report = V.build_report(routes_path=routes_path, policy="strict")
    assert report["plane"] == "z1"
    assert report["routed_count"] == 2
    assert report["d56_passed_count"] == 2
    assert report["violations"] == []
    assert report["process"]["radius_mm"] == pytest.approx(40.0)
    assert report["process"]["centerline_clearance_mm"] == pytest.approx(0.08)
    assert report["crossing_count"] == 0
    assert report["structure"]["ports_used"] == 4


def test_crosscheck_harness_agrees_on_synthetic_plane_file(tmp_path):
    from four_side_1024.fslw.crosscheck_fslw import crosscheck
    points = V.build_plane_endpoints("z1")
    records = _port_routes(points, [("S01:1:1", "N01:1:1"),
                                    ("S02:1:1", "N02:1:1")])
    # add one horizontal route crossing both verticals, and one overlapping pair
    records.append({
        "route_id": 3, "status": "routed", "plane": "z1",
        "source_endpoint": "W01:1:1", "target_endpoint": "E01:1:1",
        "primitives": [line((0.0, 75.0), (150.0, 75.0))],
    })
    records.append({
        "route_id": 4, "status": "routed", "plane": "z1",
        "source_endpoint": "S01:1:2", "target_endpoint": "N01:1:2",
        "primitives": [line((5.625, 0.0), (5.625, 150.0))],  # duplicate of 1
    })
    routes_path = _write_plane_routes_file(tmp_path / "routes.json", records)
    summary = crosscheck(routes_path)
    assert summary["passed"] is True
    assert summary["mismatch_count"] == 0
    assert summary["compared_pair_count"] >= 3
    assert summary["invalid_both_pairs"] >= 1
    assert summary["process"]["centerline_clearance_mm"] == pytest.approx(0.08)
