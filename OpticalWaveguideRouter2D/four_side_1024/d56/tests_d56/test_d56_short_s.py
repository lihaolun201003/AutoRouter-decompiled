"""Legacy short-S formula: the original ``theta=acos(1-d/(2R))`` pair family.

D56 allows exactly the original AutoRouter small-displacement construction: two
radius-5 arcs with sweeps ``+theta`` / ``-theta`` and (essentially) no straight
between them, where ``theta = acos(1 - d/(2R))`` and ``h = R*sin(theta)``.  A
radius shrunk to ``d/2`` or an arbitrary two-arc angle is not that construction.
"""
from __future__ import annotations

import copy
import math

import pytest

from d56_helpers import RADIUS, arc, arc_chain, line, short_s_route
from four_side_1024.d56 import validate_d56 as V


def check(primitives, source=None, target=None):
    return V.check_route_primitives(primitives, source, target)


def test_original_formula_short_s_accepted():
    for displacement in (3.0, 5.0, 8.0, 9.9):
        primitives, source, target, theta = short_s_route(displacement)
        assert 0.0 < theta < math.pi / 2.0
        result = check(primitives, source, target)
        assert result["passed"], (displacement, result["errors"])
        assert result["checks"]["d56_arc_family"] is True
        assert result["checks"]["radius_fixed"] is True
        assert result["checks"]["tangent_continuity"] is True
        # The short-S pair really is a pair of non-quarter arcs.
        arcs = [prim for prim in primitives if prim["kind"] == "arc"]
        assert len(arcs) == 2
        assert abs(abs(arcs[0]["sweep"]) - theta) <= 1e-12
        assert abs(arcs[0]["sweep"] + arcs[1]["sweep"]) <= 1e-12
        # Displacement relation of the original formula: d = 2R(1-cos theta)
        # and h = R sin(theta) per arc.
        assert 2.0 * RADIUS * (1.0 - math.cos(theta)) == pytest.approx(displacement)
        # The pair itself (lead line -> arc1 -> arc2 -> tail line) displaces by
        # d laterally and 2R sin(theta) longitudinally.
        pair_start = primitives[1]["p0"]
        pair_end = primitives[2]["p1"]
        assert abs(abs(pair_end[0] - pair_start[0]) - displacement) <= 1e-9
        assert abs((pair_end[1] - pair_start[1])
                   - 2.0 * RADIUS * math.sin(theta)) <= 1e-9


def test_legacy_generator_emits_short_s_when_displacement_below_2r(dataset):
    """The accepted legacy constructor itself produces the short-S family."""
    from d56_helpers import build_legacy_route, canonical_row

    found = 0
    for row in dataset["rows"]:
        if row["relation"] != "opposite":
            continue
        p, q, transform, kind, source, target = canonical_row(row, dataset["endpoints"])
        displacement = abs(float(q[0]) - float(p[0]))
        if not (0.5 < displacement < 2.0 * RADIUS):
            continue
        primitives, src, dst, meta = build_legacy_route(row, dataset["endpoints"])
        sweeps = [abs(prim["sweep"]) for prim in primitives if prim["kind"] == "arc"]
        assert any(abs(sweep - math.pi / 2.0) > 1e-9 for sweep in sweeps)
        theta = math.acos(1.0 - displacement / (2.0 * RADIUS))
        assert any(abs(sweep - theta) <= 1e-9 for sweep in sweeps)
        result = check(primitives, src, dst)
        assert result["passed"], (row["route_id"], result["errors"])
        found += 1
        if found >= 5:
            break
    assert found >= 2


def test_historical_short_s_routes_pass(legacy_80):
    short_s = []
    for item in legacy_80:
        sweeps = [abs(prim["sweep"]) for prim in item["primitives"]
                  if prim["kind"] == "arc"]
        if any(abs(sweep - math.pi / 2.0) > 1e-9 for sweep in sweeps):
            short_s.append(item)
    assert len(short_s) == 2  # routes 2 and 19 of the historical baseline
    for item in short_s:
        result = check(item["primitives"], item["source"], item["target"])
        assert result["passed"], (item["route_id"], result["errors"])
        arcs = [prim for prim in item["primitives"] if prim["kind"] == "arc"]
        theta = abs(arcs[0]["sweep"])
        assert 0.0 < theta < math.pi / 2.0
        assert abs(arcs[0]["sweep"] + arcs[1]["sweep"]) <= 1e-12
        assert V._pair_reason(result["prims"][1], result["prims"][2]) is None


def test_forged_radius_shrunk_to_d_over_2_rejected():
    """The classic wrong fix (radius := d/2, two quarter arcs) is not D56."""
    displacement = 8.0
    radius = displacement / 2.0
    chain, end, _ = arc_chain((10.0, 10.0), math.pi / 2.0,
                              [math.pi / 2.0, -math.pi / 2.0], radius)
    primitives = [line((10.0, 5.0), (10.0, 10.0))] + chain + \
                 [line(end, (end[0], end[1] + 30.0))]
    source = {"routing_xy": [10.0, 5.0], "inward": [0.0, 1.0]}
    target = {"routing_xy": [end[0], end[1] + 30.0], "inward": [0.0, -1.0]}
    result = check(primitives, source, target)
    assert not result["passed"]
    assert sum(error.startswith("arc_radius:") for error in result["errors"]) == 2
    assert result["checks"]["radius_fixed"] is False


def test_forged_unequal_theta_pair_rejected():
    chain, end, _ = arc_chain((10.0, 10.0), math.pi / 2.0, [0.6, -0.8], RADIUS)
    primitives = [line((10.0, 5.0), (10.0, 10.0))] + chain + \
                 [line(end, (end[0], end[1] + 30.0))]
    source = {"routing_xy": [10.0, 5.0], "inward": [0.0, 1.0]}
    target = {"routing_xy": [end[0], end[1] + 30.0], "inward": [0.0, -1.0]}
    result = check(primitives, source, target)
    assert not result["passed"]
    assert any("short_s_pair_invalid" in error for error in result["errors"])
    assert result["checks"]["d56_arc_family"] is False


def test_forged_same_sign_pair_rejected():
    chain, end, _ = arc_chain((10.0, 10.0), math.pi / 2.0, [0.7, 0.7], RADIUS)
    primitives = [line((10.0, 5.0), (10.0, 10.0))] + chain
    result = check(primitives)
    assert not result["passed"]
    assert any("short_s_pair_invalid" in error for error in result["errors"])


def test_forged_three_arc_chain_rejected():
    """A short-S pair must stay a pair; a third free arc is F56."""
    chain, end, _ = arc_chain((10.0, 10.0), math.pi / 2.0, [0.7, -0.7, 0.5], RADIUS)
    primitives = [line((10.0, 5.0), (10.0, 10.0))] + chain
    result = check(primitives)
    assert not result["passed"]
    assert any(error.startswith("short_s_unpaired_arc:3") for error in result["errors"])


def test_forged_pair_with_visible_straight_between_arcs_rejected():
    """The original formula has no straight between the two short-S arcs."""
    displacement = 8.0
    theta = math.acos(1.0 - displacement / (2.0 * RADIUS))
    chain, midpoint, heading = arc_chain((10.0, 10.0), math.pi / 2.0, [theta], RADIUS)
    gap = 1.0  # mm of visible straight, not approximately zero
    bridge_end = (midpoint[0] - gap * math.sin(heading),
                  midpoint[1] + gap * math.cos(heading))
    second, end, _ = arc_chain(bridge_end, heading, [-theta], RADIUS)
    primitives = [line((10.0, 5.0), (10.0, 10.0))] + chain + \
                 [line(midpoint, bridge_end)] + second
    result = check(primitives)
    assert not result["passed"]
    assert any(error.startswith("short_s_unpaired_arc:1")
               for error in result["errors"])


def test_arc_pair_formula_displacement_is_checked():
    """The pair predicate verifies the original formula, not just "two arcs"."""
    primitives, source, target, theta = short_s_route(8.0)
    pair = [V._Prim.from_raw(primitives[1]), V._Prim.from_raw(primitives[2])]
    assert V._pair_reason(*pair) is None
    # Tampered second endpoint: individually the arcs stay raw-consistent for
    # this unit call, but the short-S displacement no longer matches.
    tampered = [V._Prim.from_raw(primitives[1]),
                V._Prim.from_raw(primitives[2])]
    raw = copy.deepcopy(primitives[2])
    raw["p1"] = [raw["p1"][0] + 0.2, raw["p1"][1]]
    tampered[1] = V._Prim.from_raw(raw)
    reason = V._pair_reason(*tampered)
    assert reason in ("lateral_displacement_mismatch",
                      "longitudinal_displacement_mismatch",
                      "theta_displacement_inconsistent")
    # Two arcs with theta outside (0, pi/2) are not the small-displacement case.
    chain, end, _ = arc_chain((10.0, 10.0), math.pi / 2.0, [2.0, -2.0], RADIUS)
    prims, _, _ = arc_chain((10.0, 10.0), math.pi / 2.0, [2.0, -2.0], RADIUS)
    reason = V._pair_reason(V._Prim.from_raw(prims[0]), V._Prim.from_raw(prims[1]))
    assert reason == "theta_out_of_range"
    route = [line((10.0, 5.0), (10.0, 10.0))] + chain
    result = check(route)
    assert not result["passed"]
    assert any("theta_out_of_range" in error for error in result["errors"])


def test_short_s_pair_survives_rigid_frames(dataset):
    """Short-S geometry is rotation/reflection invariant (rigid legacy frames)."""
    from d56_helpers import build_legacy_route

    tested = 0
    for row in dataset["rows"]:
        if row["relation"] != "opposite":
            continue
        primitives, source, target, meta = build_legacy_route(
            row, dataset["endpoints"], track=75.0)
        sweeps = [prim["sweep"] for prim in primitives if prim["kind"] == "arc"]
        if len(sweeps) != 2 or abs(abs(sweeps[0]) - math.pi / 2.0) < 1e-9:
            continue
        result = check(primitives, source, target)
        assert result["passed"], (row["route_id"], result["errors"])
        tested += 1
        if tested >= 3:
            break
    assert tested >= 1
