"""Single-route D56 checks: positive legacy geometry and every negative case.

The validator under test is ``four_side_1024/d56/validate_d56.py``; it is
independent of the router's own ``geometry.validate`` / ``ConflictIndex``.
"""
from __future__ import annotations

import copy
import math

import pytest

from d56_helpers import (
    RADIUS,
    arc,
    arc_chain,
    build_legacy_route,
    canonical_row,
    line,
    load_dataset,
    short_s_route,
)
from four_side_1024.d56 import validate_d56 as V


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def check(primitives, source=None, target=None):
    return V.check_route_primitives(primitives, source, target)


def mutation_source(generated_routes):
    """A legal generated route whose first primitive is a straight line."""
    for item in generated_routes:
        if item["primitives"][0]["kind"] == "line":
            return item
    raise AssertionError("no generated route starts with a line")


def integral_route():
    """A two-segment L route that satisfies every D56 check except tangency."""
    primitives = [line((10.0, 0.0), (10.0, 20.0)), line((10.0, 20.0), (30.0, 20.0))]
    source = {"routing_xy": [10.0, 0.0], "inward": [0.0, 1.0]}
    target = {"routing_xy": [30.0, 20.0], "inward": [-1.0, 0.0]}
    return primitives, source, target


# ---------------------------------------------------------------------------
# positive cases
# ---------------------------------------------------------------------------
def test_generated_legacy_routes_pass_all_side_pairs(generated_routes):
    assert len(generated_routes) >= 6
    kinds = {item["meta"]["kind"] for item in generated_routes}
    assert kinds == {"opposite", "adjacent"}
    labelled = {item["label"] for item in generated_routes}
    assert len(labelled) == 6  # one ordered interface per side pair in the CSV
    for item in generated_routes:
        result = check(item["primitives"], item["source"], item["target"])
        assert result["passed"], (item["label"], item["meta"]["variant"], result["errors"])
        assert all(result["checks"].values()), (item["label"], result["checks"])
        assert result["endpoints_checked"] is True
        # The validator must not merely tolerate the geometry: every arc has
        # the fixed D56 radius and every line is axis-aligned.
        for prim in result["prims"]:
            if prim.kind == "arc":
                assert abs(prim.radius - RADIUS) <= 1e-9
        assert result["length_mm"] > 0.0


def test_adjacent_interface_both_legacy_variants_are_legal(dataset):
    """Direct single-L and three-bend adjacent terminals are both legal D56.

    The legacy adapter can offer either terminal template per connection (the
    fixed 5 mm radius does not always fit both); every template that *is*
    produced must pass the independent D56 checks, and no adjacent connection
    may be without any legal legacy template.
    """
    count = 0
    direct_count = 0
    three_bend_count = 0
    for row in dataset["rows"]:
        if row["relation"] != "adjacent":
            continue
        p, q, transform, kind, source, target = canonical_row(row, dataset["endpoints"])
        assert kind == "adjacent"
        variants = []
        try:
            variants.append(build_legacy_route(row, dataset["endpoints"],
                                               track=float(q[1])))
            direct_count += 1
        except ValueError:
            pass  # target closer than R to the board edge: single L cannot fit
        for candidate in (40.0, 110.0, 65.0, 85.0, 25.0, 125.0):
            if abs(candidate - float(q[1])) < 2.0 * RADIUS:
                continue
            try:
                variants.append(build_legacy_route(row, dataset["endpoints"],
                                                   track=candidate))
            except ValueError:
                continue
            three_bend_count += 1
            break
        assert variants, f"no legal legacy adjacent terminal for route {row['route_id']}"
        for primitives, src, dst, meta in variants:
            result = check(primitives, src, dst)
            assert result["passed"], (row["route_id"], meta, result["errors"])
        count += 1
    assert count == 512  # every adjacent CSV connection has a legal template
    assert direct_count == 508
    assert three_bend_count == 480


def test_straight_single_segment_route_is_legal_d56(dataset):
    """A zero-bend straight connection is the legal degenerate D56 case."""
    row = dataset["by_id"][1]
    assert row["pair"] == "NS"
    source = dataset["endpoints"][row["source_endpoint"]]
    target = dataset["endpoints"][row["target_endpoint"]]
    primitives = [line(source["routing_xy"], target["routing_xy"])]
    result = check(primitives, source, target)
    assert result["passed"], result["errors"]
    assert result["bend_count"] == 0
    assert result["length_mm"] == pytest.approx(150.0, abs=1e-9)


def test_axis_aligned_stroke_stays_inside_board(dataset):
    """The waveguides at the extreme virtual ports still clear the board."""
    row = dataset["by_id"][1]
    source = dataset["endpoints"][row["source_endpoint"]]
    target = dataset["endpoints"][row["target_endpoint"]]
    primitives = [line(source["routing_xy"], target["routing_xy"])]
    assert check(primitives, source, target)["checks"]["board_bounds"] is True


# ---------------------------------------------------------------------------
# negative cases (one check at a time)
# ---------------------------------------------------------------------------
def test_diagonal_line_rejected(generated_routes):
    item = mutation_source(generated_routes)
    primitives = copy.deepcopy(item["primitives"])
    index = next(i for i, prim in enumerate(primitives)
                 if prim["kind"] == "line"
                 and abs(prim["p1"][0] - prim["p0"][0]) < 1e-12)
    primitives[index]["p1"][0] += 1e-3  # 0.001 mm lateral drift on a vertical line
    result = check(primitives, item["source"], item["target"])
    assert not result["passed"]
    assert any(error.startswith("diagonal_line:") for error in result["errors"])
    assert result["checks"]["orthogonal_lines"] is False


@pytest.mark.parametrize("bad_radius", [4.9, 5.1, 4.0, 6.0])
def test_wrong_arc_radius_rejected(generated_routes, bad_radius):
    item = next(entry for entry in generated_routes
                if any(prim["kind"] == "arc" for prim in entry["primitives"]))
    primitives = copy.deepcopy(item["primitives"])
    for prim in primitives:
        if prim["kind"] == "arc":
            prim["radius"] = bad_radius
            break
    result = check(primitives, item["source"], item["target"])
    assert not result["passed"]
    assert any(error.startswith("arc_radius:") for error in result["errors"])
    assert result["checks"]["radius_fixed"] is False
    assert result["checks"]["arc_endpoint_consistency"] is False


def test_arbitrary_angle_single_arc_rejected():
    """A free F56 bend (sweep 0.7 rad) is not a D56 90-degree arc."""
    primitives = [line((10.0, 5.0), (10.0, 20.0))]
    chain, end, heading = arc_chain((10.0, 20.0), math.pi / 2.0, [0.7], RADIUS)
    primitives += chain
    result = check(primitives)
    assert not result["passed"]
    assert any(error.startswith("short_s_unpaired_arc:1") for error in result["errors"])
    assert result["checks"]["d56_arc_family"] is False


def test_tangent_discontinuity_rejected():
    primitives, source, target = integral_route()
    result = check(primitives, source, target)
    assert not result["passed"]
    assert "tangent_discontinuity:0:1" in result["errors"]
    assert result["checks"]["tangent_continuity"] is False
    # Everything else about this L is legal, so the failure is isolated.
    assert result["checks"]["orthogonal_lines"] is True
    assert result["checks"]["position_continuity"] is True
    assert result["checks"]["endpoints_fixed"] is True
    assert result["checks"]["inout_directions"] is True


def test_position_discontinuity_rejected():
    primitives = [line((10.0, 0.0), (10.0, 20.0)),
                  line((10.5, 20.0), (10.5, 30.0))]
    source = {"routing_xy": [10.0, 0.0], "inward": [0.0, 1.0]}
    target = {"routing_xy": [10.5, 30.0], "inward": [0.0, -1.0]}
    result = check(primitives, source, target)
    assert not result["passed"]
    assert "position_discontinuity:0:1" in result["errors"]
    assert result["checks"]["position_continuity"] is False
    assert result["checks"]["tangent_continuity"] is True


def test_endpoint_offset_rejected(generated_routes):
    item = mutation_source(generated_routes)
    primitives = copy.deepcopy(item["primitives"])
    primitives[0]["p0"][1] += 1e-2  # 0.01 mm drift at the fixed port
    result = check(primitives, item["source"], item["target"])
    assert not result["passed"]
    assert "start_endpoint_mismatch" in result["errors"]
    assert result["checks"]["endpoints_fixed"] is False


def test_wrong_inout_direction_rejected(generated_routes):
    item = mutation_source(generated_routes)
    source = dict(item["source"])
    source["inward"] = [-value for value in item["source"]["inward"]]
    result = check(item["primitives"], source, item["target"])
    assert not result["passed"]
    assert "start_direction_mismatch" in result["errors"]
    assert result["checks"]["inout_directions"] is False


def test_target_direction_mismatch_rejected(generated_routes):
    item = mutation_source(generated_routes)
    target = dict(item["target"])
    target["inward"] = [-value for value in item["target"]["inward"]]
    result = check(item["primitives"], item["source"], target)
    assert not result["passed"]
    assert "end_direction_mismatch" in result["errors"]


def test_nonzero_layer_rejected(generated_routes):
    item = mutation_source(generated_routes)
    primitives = copy.deepcopy(item["primitives"])
    primitives[0]["layer"] = 1
    result = check(primitives, item["source"], item["target"])
    assert not result["passed"]
    assert "nonzero_layer:0:1" in result["errors"]
    assert result["checks"]["layer_zero"] is False


def test_board_out_of_bounds_rejected():
    primitives = [line((0.01, 0.0), (0.01, 20.0))]
    source = {"routing_xy": [0.01, 0.0], "inward": [0.0, 1.0]}
    target = {"routing_xy": [0.01, 20.0], "inward": [0.0, -1.0]}
    result = check(primitives, source, target)
    assert not result["passed"]
    assert "board_out_of_bounds:0" in result["errors"]
    assert result["checks"]["board_bounds"] is False
    # Only the stroked footprint leaves the board: the centreline is inside.
    assert result["checks"]["orthogonal_lines"] is True
    assert result["checks"]["endpoints_fixed"] is True


def test_self_intersection_rejected():
    primitives = [line((10.0, 10.0), (30.0, 10.0)),
                  line((30.0, 10.0), (30.0, 20.0)),
                  line((30.0, 20.0), (10.0, 20.0)),
                  line((10.0, 20.0), (10.0, 10.0))]
    result = check(primitives)
    assert not result["passed"]
    assert any(error.startswith("self_intersection:") for error in result["errors"])
    assert result["checks"]["self_intersection_free"] is False


def test_self_overlap_rejected():
    primitives = [line((10.0, 10.0), (30.0, 10.0)),
                  line((30.0, 10.0), (20.0, 10.0))]
    result = check(primitives)
    assert not result["passed"]
    assert "self_overlap:0:1" in result["errors"]
    assert result["checks"]["self_overlap_free"] is False


def test_self_spacing_violation_rejected():
    primitives = [line((10.0, 10.0), (40.0, 10.0)),
                  line((40.0, 10.0), (40.0, 10.4)),
                  line((40.0, 10.4), (39.0, 10.4)),
                  line((39.0, 10.4), (39.0, 10.1)),
                  line((39.0, 10.1), (20.0, 10.1))]
    result = check(primitives)
    assert not result["passed"]
    assert "self_spacing:0:4" in result["errors"]
    assert result["checks"]["self_spacing_ok"] is False


def test_empty_geometry_rejected():
    result = check([])
    assert not result["passed"]
    assert result["errors"] == ["empty_geometry"]


def test_zero_length_line_rejected():
    result = check([line((10.0, 10.0), (10.0, 10.0))])
    assert not result["passed"]
    assert result["errors"] == ["invalid_primitive:0:zero_length_line"]


def test_arc_endpoint_inconsistency_rejected():
    primitives, source, target, _ = short_s_route(8.0)
    primitives = copy.deepcopy(primitives)
    primitives[1]["center"][0] += 0.01  # inconsistent with p0/p1
    result = check(primitives, source, target)
    assert not result["passed"]
    assert any(error.startswith("arc_endpoint_inconsistent:")
               for error in result["errors"])


def test_checks_report_counts_and_route_identity(generated_routes):
    item = generated_routes[0]
    result = check(item["primitives"], item["source"], item["target"])
    for name in ("orthogonal_lines", "radius_fixed", "d56_arc_family",
                 "arc_endpoint_consistency", "position_continuity",
                 "tangent_continuity", "endpoints_fixed", "inout_directions",
                 "layer_zero", "board_bounds", "self_intersection_free",
                 "self_overlap_free", "self_spacing_ok"):
        assert name in result["checks"]
