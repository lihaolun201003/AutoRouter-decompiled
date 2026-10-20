"""Unit tests for the independent 2.5D validator (``fsd25d/validate25d.py``).

The tests exercise the parts of the validator that must be independent of the
router: the S-curve reconstruction, the exact 3D segment/curvature helpers, the
D56 short-S pair predicate, the true-3D clearance audit on hand-built geometry
and (when the smoke artefact exists) the complete smoke validation.

Run from the project root ``OpticalWaveguideRouter2D``::

    .venv\\Scripts\\python.exe -m pytest four_side_1024\\fsd25d\\tests_25d -v
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from four_side_1024.fsd25d import validate25d as V

SMOKE_PATH = (V.CFG.V25D_ROOT / "_smoke" / "routes_25d.json")


# ---------------------------------------------------------------------------
# Vector geometry helpers
# ---------------------------------------------------------------------------
def _circle_points(radius=40.0, step=0.02, center=(10.0, 20.0, 30.0),
                   plane=("x", "y")):
    count = max(3, int(math.ceil(2.0 * math.pi * radius / step)))
    angles = np.linspace(0.0, 2.0 * math.pi, count)
    points = np.zeros((count, 3))
    if plane == ("x", "y"):
        points[:, 0] = center[0] + radius * np.cos(angles)
        points[:, 1] = center[1] + radius * np.sin(angles)
        points[:, 2] = center[2]
    else:  # vertical plane (x, z) - the geometry family used by transitions
        points[:, 0] = center[0] + radius * np.cos(angles)
        points[:, 1] = center[1]
        points[:, 2] = center[2] + radius * np.sin(angles)
    return points


def test_polyline_min_curvature_circle():
    value = V._polyline_min_curvature(_circle_points(radius=40.0))
    assert abs(value - 40.0) < 1e-3
    value = V._polyline_min_curvature(_circle_points(radius=25.0))
    assert abs(value - 25.0) < 1e-3
    # vertical-plane circle: transition arcs live in such planes
    value = V._polyline_min_curvature(
        _circle_points(radius=40.0, plane=("x", "z")))
    assert abs(value - 40.0) < 1e-3


def test_polyline_min_curvature_straight_line():
    points = np.column_stack([np.linspace(0.0, 100.0, 500),
                              np.full(500, 3.0), np.full(500, 0.125)])
    assert V._polyline_min_curvature(points) == float("inf")


def test_segment_segment_closest_perpendicular_crossing():
    p1 = np.array([[0.0, 0.0, 0.0]])
    q1 = np.array([[1.0, 0.0, 0.0]])
    p2 = np.array([[0.5, -1.0, 0.0]])
    q2 = np.array([[0.5, 1.0, 0.0]])
    distance, point_a, point_b, s, t = V._segment_segment_closest(p1, q1, p2, q2)
    assert distance[0] == pytest.approx(0.0, abs=1e-12)
    assert point_a[0] == pytest.approx([0.5, 0.0, 0.0])
    assert s[0] == pytest.approx(0.5)
    assert t[0] == pytest.approx(0.5)


def test_segment_segment_closest_parallel_and_offset():
    p1 = np.array([[0.0, 0.0, 0.0]])
    q1 = np.array([[10.0, 0.0, 0.0]])
    p2 = np.array([[3.0, 0.05, 0.0]])
    q2 = np.array([[12.0, 0.05, 0.0]])
    distance, _p, _q, s, t = V._segment_segment_closest(p1, q1, p2, q2)
    assert distance[0] == pytest.approx(0.05, abs=1e-12)
    assert 0.0 <= s[0] <= 1.0 and 0.0 <= t[0] <= 1.0


def test_segment_segment_closest_endpoint_gap():
    p1 = np.array([[0.0, 0.0, 0.0]])
    q1 = np.array([[1.0, 0.0, 0.0]])
    p2 = np.array([[4.0, 0.0, 0.0]])
    q2 = np.array([[5.0, 0.0, 0.0]])
    distance, _p, _q, _s, _t = V._segment_segment_closest(p1, q1, p2, q2)
    assert distance[0] == pytest.approx(3.0, abs=1e-12)


# ---------------------------------------------------------------------------
# S-curve (transition) reconstruction
# ---------------------------------------------------------------------------
def _transition(z0, z1, radius=40.0, start=(10.0, 20.0), direction=(1.0, 0.0)):
    dz = z1 - z0
    ratio = 1.0 - abs(dz) / (2.0 * radius)
    theta = math.acos(max(-1.0, min(1.0, ratio)))
    footprint = 2.0 * radius * math.sin(theta)
    length = 2.0 * radius * theta
    end = (start[0] + direction[0] * footprint,
           start[1] + direction[1] * footprint)
    declared_footprint = round(footprint, 9)
    declared_length = round(length, 6)
    return V._TransitionPart(0, start, end, direction, z0, z1, dz, radius,
                             declared_footprint, declared_length)


@pytest.mark.parametrize("z0,z1", [(0.5, 0.125), (0.0, 0.125), (0.375, 0.5),
                                   (0.5, 0.25), (0.25, 0.0)])
def test_transition_analytic_formulas(z0, z1):
    part = _transition(z0, z1)
    assert part.theta == pytest.approx(
        math.acos(1.0 - abs(z1 - z0) / 80.0), abs=1e-12)
    assert part.footprint == pytest.approx(80.0 * math.sin(part.theta), abs=1e-12)
    assert part.length == pytest.approx(80.0 * part.theta, abs=1e-12)
    assert part.footprint > 0.0 and part.length > part.footprint
    # start / end poses, horizontal tangents at both ends
    start = part.samples(0.02)
    assert start[0].tolist() == pytest.approx([10.0, 20.0, z0], abs=1e-12)
    assert start[-1].tolist() == pytest.approx(
        [part.end[0], part.end[1], z1], abs=1e-9)
    assert part.start_tangent3() == (1.0, 0.0, 0.0)
    assert part.end_tangent3() == (1.0, 0.0, 0.0)


def test_transition_samples_and_symmetry():
    part = _transition(0.5, 0.125)
    points = part.samples(0.02)
    assert len(points) >= 3
    # the sample step along the whole S-curve must never exceed 0.02 mm
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    assert float(np.max(steps)) <= 0.02 + 1e-12
    # point reflection symmetry about the S-curve midpoint
    middle = 0.5 * (points[0] + points[-1])
    reflected = 0.5 * (points + points[::-1])
    assert np.allclose(reflected, middle, atol=1e-12)
    # both arcs have the fixed radius 40 mm: sampled curvature radius is 40
    radius = V._polyline_min_curvature(np.vstack([points, points[::-1]]))
    assert abs(radius - 40.0) < 1e-3
    # height is monotone between the two layers
    assert np.all(np.diff(points[:, 2]) <= 1e-12)
    assert points[:, 2].min() == pytest.approx(0.125, abs=1e-12)
    assert points[:, 2].max() == pytest.approx(0.5, abs=1e-12)


def test_transition_rising_and_xy_footprint():
    part = _transition(0.0, 0.25, start=(0.0, 0.0), direction=(0.0, -1.0))
    assert part.samples(0.02)[-1].tolist() == pytest.approx(
        [0.0, -part.footprint, 0.25], abs=1e-9)
    assert part._sign == 1.0


# ---------------------------------------------------------------------------
# D56 short-S predicate
# ---------------------------------------------------------------------------
def _short_s_arcs(theta_deg=15.0, radius=40.0):
    theta = math.radians(theta_deg)
    first = V._FlatArc(
        p0=(0.0, 0.0),
        p1=(radius * math.sin(theta), radius * (1.0 - math.cos(theta))),
        center=(0.0, radius),
        radius=radius,
        start_angle=-math.pi / 2.0,
        sweep=theta)
    center2 = (first.p1[0] + radius * math.sin(theta),
               first.p1[1] - radius * math.cos(theta))
    second = V._FlatArc(
        p0=first.p1,
        p1=(2.0 * radius * math.sin(theta), 2.0 * radius * (1.0 - math.cos(theta))),
        center=center2,
        radius=radius,
        start_angle=math.pi / 2.0 + theta,
        sweep=-theta)
    return first, second


def test_short_s_pair_accepts_legal_pair():
    first, second = _short_s_arcs(15.0)
    assert V._short_s_pair_ok(first, second)
    # analytic endpoint consistency of both arcs
    for arc in (first, second):
        for endpoint, angle in ((arc.p0, arc.start_angle),
                               (arc.p1, arc.start_angle + arc.sweep)):
            reconstructed = (arc.center[0] + arc.radius * math.cos(angle),
                             arc.center[1] + arc.radius * math.sin(angle))
            assert math.dist(reconstructed, endpoint) < 1e-9


def test_short_s_pair_rejects_wrong_geometry():
    first, second = _short_s_arcs(15.0)
    wrong_sweep = V._FlatArc(second.p0, second.p1, second.center,
                             second.radius, second.start_angle, second.sweep * 0.5)
    assert not V._short_s_pair_ok(first, wrong_sweep)
    same_sign = V._FlatArc(second.p0, second.p1, second.center,
                           second.radius, second.start_angle, abs(second.sweep))
    assert not V._short_s_pair_ok(first, same_sign)


def test_scheme_b_arc_model_checks_are_strict():
    report = V._Report()
    raw = {"kind": "arc", "p0": [0.0, 0.0], "p1": [40.0, 40.0],
           "center": [0.0, 40.0], "radius": 40.0,
           "start_angle": -math.pi / 2.0, "sweep": math.radians(80.0)}
    V._parse_flat_primitive(raw, 0, 0, "B", report, route_id=1)
    assert report.counts["xy_model_errors"] == 1
    # scheme A accepts the same non-90 arc only as part of a short-S pair
    report_a = V._Report()
    V._parse_flat_primitive(raw, 0, 0, "A", report_a, route_id=1)
    assert report_a.counts["xy_model_errors"] == 0


# ---------------------------------------------------------------------------
# True-3D clearance on hand-built geometry
# ---------------------------------------------------------------------------
def _flat_part(index, layer, z, p0, p1):
    line = V._FlatLine(p0, p1)
    return V._FlatPart(index, layer, z, [line], line.length, [])


def _clearance_store(*parts):
    store = V._SegmentStore()
    for geom_id, part in parts:
        geom = V._RouteGeom(geom_id, "z2", "flat", [part], {})
        if part.kind == "flat":
            store.add_flat(geom, part)
        else:
            store.add_transition(geom, part)
    return store.finalise()


def test_true_3d_clearance_detects_transition_flat_shortfall():
    # flat centreline at z = 0.125 along y = 0.02
    flat = _flat_part(0, 1, 0.125, (0.0, 0.02), (20.0, 0.02))
    # descent from z = 0.5 to z = 0.125 running along y = 0: the S-curve end
    # passes 0.02 mm away from the flat, far below the 0.08 mm clearance
    transition = _transition(0.5, 0.125, start=(5.0, 0.0), direction=(1.0, 0.0))
    store = _clearance_store((1, flat), (2, transition))
    report = V._Report()
    stats = V._audit_3d_pairs(store, [], report)
    assert report.counts["clearance_violations"] > 0
    assert stats["min_flat_transition_mm"] < V.CLEARANCE_MM


def test_true_3d_clearance_accepts_when_separated():
    flat = _flat_part(0, 1, 0.125, (0.0, 0.5), (20.0, 0.5))
    transition = _transition(0.5, 0.125, start=(5.0, 0.0), direction=(1.0, 0.0))
    store = _clearance_store((1, flat), (2, transition))
    report = V._Report()
    V._audit_3d_pairs(store, [], report)
    assert report.counts["clearance_violations"] == 0


# ---------------------------------------------------------------------------
# Complete smoke run (skipped when the artefact is absent)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not SMOKE_PATH.exists(), reason="smoke artefact not present")
def test_smoke_sample_passes():
    result = V.validate_routes_file(SMOKE_PATH, check_port_csv=False)
    assert result["passed"], result["failure_reasons"]
    assert result["counts"]["violations"] == 0
    assert result["routed"] == 272
    assert result["min_curvature_radius_mm"] >= V.MIN_CURVATURE_MM
    assert result["min_3d_distance_excluding_crossings_mm"] >= V.CLEARANCE_MM
    assert result["crossings"]["total"] > 0
    assert sum(result["crossings"]["by_layer"].values()) == result["crossings"]["total"]


@pytest.mark.skipif(not SMOKE_PATH.exists(), reason="smoke artefact not present")
def test_validator_detects_continuity_break(tmp_path):
    payload = json.loads(SMOKE_PATH.read_text(encoding="utf-8"))
    routed = [record for record in payload["routes"]
              if record.get("status") == "routed"]
    lifted = [record for record in routed if record.get("mode") == "lifted"]
    record = (lifted or routed)[0]
    first_part = record["parts"][0]
    first_part["primitives"][0]["p1"][0] += 0.5  # 0.5 mm gap at the part joint
    mutated = tmp_path / "routes_25d.json"
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    result = V.validate_routes_file(mutated, check_port_csv=False)
    assert not result["passed"]
    assert result["counts"]["structure_errors"] > 0


@pytest.mark.skipif(not SMOKE_PATH.exists(), reason="smoke artefact not present")
def test_validator_detects_scheme_b_non_90_arc(tmp_path):
    payload = json.loads(SMOKE_PATH.read_text(encoding="utf-8"))
    routed = [record for record in payload["routes"]
              if record.get("status") == "routed"]
    mutated = False
    for record in routed:
        for part in record.get("parts") or []:
            for primitive in part.get("primitives") or []:
                if primitive.get("kind") == "arc":
                    primitive["sweep"] *= 0.5
                    mutated = True
                    break
            if mutated:
                break
        if mutated:
            break
    assert mutated
    path = tmp_path / "routes_25d.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = V.validate_routes_file(path, check_port_csv=False)
    assert not result["passed"]
    assert result["counts"]["xy_model_errors"] + \
        result["counts"]["structure_errors"] + \
        result["counts"]["curvature_violations"] > 0
