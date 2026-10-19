"""Tests for the independent V3-Huang dual-height validator.

Contract: ``four_side_1024/v3/SPEC.md`` — R=40 mm fixed, waveguide width 0.050,
edge gap 0.030 (centreline clearance 0.080), the unchanged ``strict`` local
crossing-window policy of ``four_side_1024/abcd/SPEC.md`` §2.1 at clearance
0.080, the dual-height real IEC 2x16 port model (row 1 -> z1, row 2 -> z2) and
the new V3 same/opposite/adjacent topology where the relation comes from the
CSV column (never inferred from the row).

Covered: legal / illegal same-side U-hairpin geometry, the 180-degree hairpin
rule (two consecutive same-sign quarter arcs, ``relation='same'`` only),
chained short-S + hairpin same-side families emitted by the router, tampered
radius/theta, non-quarter arcs, diagonal lines, wrong tangents, the 0.0799 /
0.0801 clearance boundaries, the 0.081 analytic line-line window, plane /
port-model structure and relation-from-CSV checks, determinism and the
router-vs-validator crosscheck harness.
"""
from __future__ import annotations

import json
import math

import pytest

from four_side_1024.v3 import validate_v3 as V

RADIUS = 40.0
WIDTH = 0.05
EDGE_GAP = 0.03
CLEARANCE = 0.08
SAGITTA = 0.0005
LIMIT = CLEARANCE - V.STRICT_LIMIT_TOL
MARGIN = 2.0 * SAGITTA


# ---------------------------------------------------------------------------
# primitive builders (independent of the router modules)
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


def same_side_ports(source_xy, target_xy, side="S"):
    inward = {"S": [0.0, 1.0], "N": [0.0, -1.0],
              "E": [-1.0, 0.0], "W": [1.0, 0.0]}[side]
    return ({"routing_xy": list(source_xy), "inward": list(inward), "side": side},
            {"routing_xy": list(target_xy), "inward": list(inward), "side": side})


def hairpin_u_route(p, q, height=60.0):
    """Canonical same-side U: up, two right quarter arcs (hairpin), down."""
    dx = q[0] - p[0]
    assert dx >= 2 * RADIUS - 1e-9
    return [
        line((p[0], 0.0), (p[0], height)),
        arc((p[0] + RADIUS, height), math.pi, -math.pi / 2),
        arc((p[0] + RADIUS, height), math.pi / 2, -math.pi / 2),
        line((p[0] + 2 * RADIUS, height), (q[0], 0.0)),
    ]


def check_same(prims, source=None, target=None):
    if source is None or target is None:
        source, target = same_side_ports((20.0, 0.0), (100.0 + 20.0, 0.0))
    return V.check_route_primitives(prims, source, target, relation="same")


def pair(first, second, policy="strict"):
    return V.evaluate_pair(V.prepare_route(first, 1),
                           V.prepare_route(second, 2), policy=policy)


def kinds(result):
    return [detail["kind"] for detail in result["violations"]]


# ---------------------------------------------------------------------------
# (1) legal same-side U geometry: two quarter arcs = 180-degree hairpin
# ---------------------------------------------------------------------------
def test_same_side_hairpin_u_is_legal():
    source, target = same_side_ports((20.0, 0.0), (100.0, 0.0))
    route = hairpin_u_route((20.0, 0.0), (100.0, 0.0))
    result = V.check_route_primitives(route, source, target, relation="same")
    assert result["passed"] is True, result["errors"]
    assert result["checks"]["d56_arc_family"] is True
    assert result["checks"]["endpoints_fixed"] is True
    assert result["checks"]["inout_directions"] is True


def test_same_side_end_tangent_must_be_outward():
    source, _target = same_side_ports((20.0, 0.0), (100.0, 0.0))
    # wrong target inward vector: the route would have to end travelling +y
    # (into the board) instead of the required outward -y direction.
    target_wrong = {"routing_xy": [100.0, 0.0], "inward": [0.0, -1.0],
                    "side": "S"}
    route = hairpin_u_route((20.0, 0.0), (100.0, 0.0))
    result = V.check_route_primitives(route, source, target_wrong,
                                      relation="same")
    assert result["passed"] is False
    assert any(error.startswith("end_direction_mismatch")
               or error.startswith("same_side_net_turn_invalid")
               for error in result["errors"])


def test_hairpin_rejected_on_non_same_relation():
    source, target = same_side_ports((20.0, 0.0), (100.0, 0.0))
    route = hairpin_u_route((20.0, 0.0), (100.0, 0.0))
    result = V.check_route_primitives(route, source, target,
                                      relation="opposite")
    assert result["passed"] is False
    assert any("hairpin" in error for error in result["errors"])


def test_same_side_net_turn_check_is_explicit():
    source, target = same_side_ports((20.0, 0.0), (100.0, 0.0))
    # route that starts inward but ends with the wrong (inward) tangent
    route = [line((20.0, 0.0), (20.0, 60.0)),
             line((20.0, 60.0), (100.0, 60.0)),
             line((100.0, 60.0), (100.0, 0.0))]
    result = V.check_route_primitives(route, source, target, relation="same")
    assert result["passed"] is False


# ---------------------------------------------------------------------------
# (2) V3 router-emitted same-side families validate (U / hairpin A / hairpin B)
# ---------------------------------------------------------------------------
def test_router_same_side_families_validate():
    from four_side_1024.v3 import geom_same as S
    source, target = same_side_ports((20.0, 0.0), (40.0, 0.0))
    p, q = (20.0, 0.0), (40.0, 0.0)
    built = 0
    for sign in (1.0, -1.0):
        for y0 in (0.0, 10.0, 40.0):
            prims = S.same_hairpin_a(p, q, y0, sign)
            if prims is None:
                continue
            result = V.check_route_primitives(prims, source, target,
                                              relation="same")
            assert result["passed"] is True, (y0, sign, result["errors"])
            built += 1
        for y0 in (None, 60.0):
            prims = S.same_hairpin_b(p, q, y0, sign)
            if prims is None:
                continue
            result = V.check_route_primitives(prims, source, target,
                                              relation="same")
            assert result["passed"] is True, (y0, sign, result["errors"])
            built += 1
    assert built > 0


def test_router_same_side_u_family_validates():
    from four_side_1024.v3 import geom_same as S
    p, q = (20.0, 0.0), (110.0, 0.0)
    source, target = same_side_ports(p, q)
    built = 0
    for depth in S.same_u_depths(deep=False):
        prims = S.same_u(p, q, depth)
        if prims is None:
            continue
        result = V.check_route_primitives(prims, source, target, relation="same")
        assert result["passed"] is True, (depth, result["errors"])
        built += 1
    assert built > 0


# ---------------------------------------------------------------------------
# (3) illegal primitive families
# ---------------------------------------------------------------------------
def test_radius_below_40_rejected():
    route = [line((20.0, 0.0), (20.0, 60.0)),
             arc((60.0, 60.0), math.pi, -math.pi / 2, radius=39.999),
             arc((60.0, 60.0), math.pi / 2, -math.pi / 2, radius=39.999)]
    result = V.check_route_primitives(route)
    assert result["passed"] is False
    assert any(error.startswith("arc_radius") for error in result["errors"])


def test_lone_non_quarter_arc_rejected():
    result = V.check_route_primitives([arc((0.0, 0.0), 0.0, 0.5)])
    assert result["passed"] is False
    assert any("unpaired" in error for error in result["errors"])


def test_three_consecutive_quarter_arcs_rejected():
    route = [
        line((20.0, 0.0), (20.0, 40.0)),
        arc((60.0, 40.0), math.pi, -math.pi / 2),          # -> (60,80)
        arc((60.0, 40.0), math.pi / 2, -math.pi / 2),      # -> (100,40)
        arc((60.0, 0.0), math.pi / 2, -math.pi / 2),       # -> (100,0)
    ]
    result = check_same(route)
    assert result["passed"] is False
    assert any("quarter_arc_run_too_long" in error for error in result["errors"])


def test_mixed_quarter_and_short_arc_pair_rejected():
    route = [arc((0.0, 0.0), math.pi / 2, -math.pi / 2),
             arc((0.0, 0.0), 0.0, 0.5)]
    result = V.check_route_primitives(route)
    assert result["passed"] is False


def test_diagonal_line_rejected():
    route = [line((20.0, 0.0), (21.0, 60.0))]
    result = V.check_route_primitives(route)
    assert result["passed"] is False
    assert any(error.startswith("diagonal_line") for error in result["errors"])


def test_hairpin_with_opposite_sweep_quarter_arcs_rejected():
    route = [line((20.0, 0.0), (20.0, 40.0)),
             arc((60.0, 40.0), math.pi, -math.pi / 2),
             arc((100.0, 40.0), math.pi / 2, math.pi / 2)]
    result = V.check_route_primitives(route, relation="same")
    assert result["passed"] is False
    assert any("quarter_arc_pair_invalid" in error for error in result["errors"])


# ---------------------------------------------------------------------------
# (4) historical short-S pair (theta = acos(1-d/(2R))) at R=40
# ---------------------------------------------------------------------------
def _arc_chain(start, heading, sweeps, radius=RADIUS):
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
        primitive = arc(center, start_angle, sweep, radius)
        primitive["p0"] = [cursor[0], cursor[1]]
        primitive["p1"] = [end[0], end[1]]
        primitives.append(primitive)
        cursor = end
        current += sweep
    return primitives, cursor


@pytest.mark.parametrize("displacement", [2.0, 10.0, 40.0, 70.0, 79.0, 79.9])
def test_short_s_pair_at_r40_is_legal(displacement):
    theta = math.acos(1.0 - displacement / (2.0 * RADIUS))
    prims, end = _arc_chain((100.0, 30.0), math.pi / 2.0, [theta, -theta])
    route = [line((100.0, 0.0), (100.0, 30.0))] + prims
    route.append(line(end, (end[0], end[1] + 30.0)))
    result = V.check_route_primitives(route)
    assert result["passed"] is True, result["errors"]


def test_short_s_tampered_theta_rejected():
    theta = math.acos(1.0 - 20.0 / (2.0 * RADIUS))
    prims, end = _arc_chain((100.0, 30.0), math.pi / 2.0, [theta, -theta])
    prims[1]["sweep"] = -abs(prims[1]["sweep"]) * 0.9
    route = [line((100.0, 0.0), (100.0, 30.0))] + prims
    route.append(line(end, (end[0], end[1] + 30.0)))
    result = V.check_route_primitives(route)
    assert result["passed"] is False


def test_board_bounds_r40_hairpin_stroke():
    # hairpin whose outer stroke reaches x = 20 + 2R + 0.025 > 150
    p = (80.0, 0.0)
    source, target = same_side_ports(p, (80.0 + 80.0, 0.0))
    route = hairpin_u_route(p, (160.0, 0.0))
    result = V.check_route_primitives(route, source, target, relation="same")
    assert result["checks"]["board_bounds"] is False
    assert result["passed"] is False


# ---------------------------------------------------------------------------
# (5) unchanged strict pair policy at clearance 0.080
# ---------------------------------------------------------------------------
def test_perpendicular_lines_window_is_clearance_plus_margin():
    result = pair([line((-20.0, 0.0), (20.0, 0.0))],
                  [line((0.0, -20.0), (0.0, 20.0))])
    assert result["valid"] is True
    crossing = result["crossings"][0]
    for key in ("half_a_left", "half_a_right", "half_b_left", "half_b_right"):
        assert crossing[key] == pytest.approx(CLEARANCE + MARGIN, abs=1e-12)


@pytest.mark.parametrize("offset,valid", [(0.0799, False), (0.0801, True),
                                          (CLEARANCE, True)])
def test_parallel_spacing_boundary_at_008(offset, valid):
    result = pair([line((0.0, 0.0), (50.0, 0.0))],
                  [line((0.0, offset), (50.0, offset))])
    assert result["valid"] is valid
    if not valid:
        assert "spacing" in kinds(result)


def test_nested_hairpin_u_routes_are_strict_legal():
    # two nested same-side U routes, 0.25 mm apart laterally and 40 mm apart
    # vertically -> all centreline distances stay well above clearance 0.080
    first = hairpin_u_route((10.0, 0.0), (90.0, 0.0), height=60.0)
    second = hairpin_u_route((10.25, 0.0), (90.25, 0.0), height=100.0)
    result = pair(first, second)
    assert result["valid"] is True, result["violations"][:3]


def test_double_cross_rejected_by_strict():
    semicircle = [arc((0.0, 0.0), 0.0, math.pi)]
    horizontals = [line((-100.0, 30.0), (100.0, 30.0))]
    assert pair(horizontals, semicircle, policy="exact")["valid"] is True
    strict = pair(horizontals, semicircle, policy="strict")
    assert strict["valid"] is False
    assert "double_cross" in kinds(strict)


# ---------------------------------------------------------------------------
# (6) dual-height port model and V3 topology parser
# ---------------------------------------------------------------------------
def test_port_model_planes_and_pitch():
    for plane, row in (("z1", 1), ("z2", 2)):
        endpoints = V.build_plane_endpoints(plane)
        assert len(endpoints) == 1024
        assert len({tuple(item["routing_xy"]) for item in endpoints.values()}) == 1024
        assert all(item["row"] == row and item["plane"] == plane
                   for item in endpoints.values())
        assert all(item["layer"] == 0 for item in endpoints.values())
    z1 = V.build_plane_endpoints("z1")
    assert z1["N01:1:1"]["routing_xy"] == pytest.approx([5.625, 150.0])
    assert z1["N01:1:1"]["inward"] == pytest.approx([0.0, -1.0])
    c1 = z1["N01:1:1"]["routing_xy"]
    c2 = z1["N01:1:2"]["routing_xy"]
    assert abs(c1[0] - c2[0]) == pytest.approx(0.25, abs=1e-12)


def test_v3_topology_parser_matches_frozen_contract():
    topology, report = V.load_v3_topology()
    assert len(topology) == 1024
    assert report["csv_sha256_match"] is True
    assert report["relation_counts"] == {"same": 448, "opposite": 384,
                                         "adjacent": 192}
    assert report["plane_relation_counts"]["z1"] == {
        "same": 222, "opposite": 196, "adjacent": 94}
    assert report["plane_relation_counts"]["z2"] == {
        "same": 226, "opposite": 188, "adjacent": 98}
    assert report["issues"] == []
    # relation is taken from the CSV column and agrees with the sides
    entry = topology[1]
    assert entry["relation"] == "same"
    assert entry["relation_from_sides"] == "same"
    assert entry["plane"] == "z1"
    assert entry["source_endpoint"].count(":") == 2


# ---------------------------------------------------------------------------
# (7) V3 plane structure checks (512 identities, relation counts, ports)
# ---------------------------------------------------------------------------
def _plane_failed_records(plane):
    topology, _report = V.load_v3_topology()
    records = []
    for route_id in sorted(route_id for route_id, entry in topology.items()
                           if entry["plane"] == plane):
        entry = topology[route_id]
        records.append({
            "route_id": route_id, "status": "failed", "plane": plane,
            "relation": entry["relation"],
            "source_endpoint": entry["source_endpoint"],
            "target_endpoint": entry["target_endpoint"],
            "reason": "no_candidate_generated",
        })
    return records


def test_plane_structure_valid_for_all_failed_plane():
    records = _plane_failed_records("z1")
    report = V.validate_dataset(records, V._default_endpoints("z1"),
                                expected_route_count=512, plane="z1")
    assert report["passed"] is True, report["errors"]
    assert report["structure"]["checked"] is True
    assert report["structure"]["ports_used"] == 1024
    assert report["structure"]["csv_route_ids_match_plane"] is True
    assert report["topology"]["observed_relation_counts"] == {
        "same": 222, "opposite": 196, "adjacent": 94}
    assert report["topology"]["checked"] is True
    assert report["topology"]["csv_sha256_match"] is True


def test_plane_structure_detects_relation_column_tamper():
    records = _plane_failed_records("z2")
    # flip the relation of one record: the CSV column is authoritative
    for record in records:
        if record["relation"] == "same":
            record["relation"] = "opposite"
            break
    report = V.validate_dataset(records, V._default_endpoints("z2"),
                                expected_route_count=512, plane="z2")
    assert report["passed"] is False
    assert report["structure"]["relation_column_mismatches"] >= 1
    assert any("relation" in error for error in report["errors"])


def test_plane_structure_detects_endpoint_tamper():
    records = _plane_failed_records("z1")
    records[0]["source_endpoint"] = "S16:2:16"
    report = V.validate_dataset(records, V._default_endpoints("z1"),
                                expected_route_count=512, plane="z1")
    assert report["passed"] is False
    assert (report["structure"]["endpoint_identity_mismatches"] >= 1
            or report["structure"]["ports_used"] != 1024)


def test_plane_structure_detects_wrong_plane_tag():
    records = _plane_failed_records("z1")
    records[0]["plane"] = "z2"
    report = V.validate_dataset(records, V._default_endpoints("z1"),
                                expected_route_count=512, plane="z1")
    assert report["passed"] is False


# ---------------------------------------------------------------------------
# (8) determinism, audit wiring and crosscheck harness
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


def test_audit_route_pairs_strict_reports_windows():
    routes = [V.prepare_route([line((-20.0, 0.0), (20.0, 0.0))], 1),
              V.prepare_route([line((0.0, -20.0), (0.0, 20.0))], 2)]
    audit = V.audit_route_pairs(routes, policy="strict")
    assert audit["crossing_count"] == 1
    assert audit["crossing_window_count"] == 1
    assert audit["crossing_window_max_mm"] == pytest.approx(
        CLEARANCE + MARGIN, abs=1e-6)
    assert audit["violations"] == []


def _write_plane_routes_file(path, records, plane="z1"):
    payload = {"schema": "four_side_1024_v3_plane_routes_v1", "plane": plane,
               "layer": 0, "port_model": V.PORT_MODEL, "routes": records}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_report_on_synthetic_plane_file(tmp_path):
    endpoints = V.build_plane_endpoints("z1")
    s1 = endpoints["S01:1:1"]; n1 = endpoints["N01:1:1"]
    s2 = endpoints["S01:1:2"]; n2 = endpoints["N01:1:2"]
    records = []
    for route_id, (source, target) in enumerate(
            ((s1, n1), (s2, n2)), start=1):
        x = source["routing_xy"][0]
        records.append({"route_id": route_id, "status": "routed", "plane": "z1",
                        "relation": "opposite",
                        "source_endpoint": source["endpoint_id"],
                        "target_endpoint": target["endpoint_id"],
                        "primitives": [line((x, 0.0), (x, 150.0))]})
    routes_path = _write_plane_routes_file(tmp_path / "routes.json", records)
    report = V.build_report(routes_path=routes_path, policy="strict",
                            topology_checks=False)
    assert report["plane"] == "z1"
    assert report["routed_count"] == 2
    assert report["d56_passed_count"] == 2
    assert report["violations"] == []
    assert report["process"]["radius_mm"] == pytest.approx(40.0)
    assert report["process"]["centerline_clearance_mm"] == pytest.approx(0.08)


def test_crosscheck_harness_agrees_on_synthetic_plane_file(tmp_path):
    from four_side_1024.v3.crosscheck_v3 import crosscheck
    endpoints = V.build_plane_endpoints("z1")
    s1 = endpoints["S01:1:1"]; n1 = endpoints["N01:1:1"]
    s2 = endpoints["S01:1:2"]; n2 = endpoints["N01:1:2"]
    records = []
    for route_id, (source, target) in enumerate(((s1, n1), (s2, n2)), start=1):
        x = source["routing_xy"][0]
        records.append({"route_id": route_id, "status": "routed", "plane": "z1",
                        "relation": "opposite",
                        "source_endpoint": source["endpoint_id"],
                        "target_endpoint": target["endpoint_id"],
                        "primitives": [line((x, 0.0), (x, 150.0))]})
    # crossing horizontal route (legal crossing with both verticals)
    w = endpoints["W01:1:1"]; e = endpoints["E01:1:1"]
    records.append({"route_id": 3, "status": "routed", "plane": "z1",
                    "relation": "opposite",
                    "source_endpoint": w["endpoint_id"],
                    "target_endpoint": e["endpoint_id"],
                    "primitives": [line((0.0, 5.625), (150.0, 5.625))]})
    # duplicate of route 1 -> overlap, invalid on both implementations
    records.append({"route_id": 4, "status": "routed", "plane": "z1",
                    "relation": "opposite",
                    "source_endpoint": s1["endpoint_id"],
                    "target_endpoint": n1["endpoint_id"],
                    "primitives": [line((5.625, 0.0), (5.625, 150.0))]})
    routes_path = _write_plane_routes_file(tmp_path / "routes.json", records)
    summary = crosscheck(routes_path)
    assert summary["passed"] is True
    assert summary["mismatch_count"] == 0
    assert summary["compared_pair_count"] >= 3
    assert summary["invalid_both_pairs"] >= 1
    assert summary["process"]["centerline_clearance_mm"] == pytest.approx(0.08)
