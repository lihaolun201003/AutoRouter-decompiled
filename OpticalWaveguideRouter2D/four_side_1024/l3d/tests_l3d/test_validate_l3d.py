"""Unit tests for the independent corrected L1-L5 validator (``l3d/validate_l3d.py``).

The tests build synthetic layer stacks and small route payloads from the frozen V2
port identities and the accepted R15 2D centre-lines (used only as *data*), then
exercise every one of the ten acceptance requirements, including the positive
multi-transition case, the undefined-stack refusal, the same-layer-different-z
case and a curvature violation.

Run from the project root ``OpticalWaveguideRouter2D``::

    .venv\\Scripts\\python.exe -m pytest four_side_1024\\l3d\\tests_l3d -v
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from four_side_1024.l3d import validate_l3d as V

PROJECT_ROOT = Path(__file__).resolve().parents[3]
R15_ROOT = PROJECT_ROOT / "outputs" / "four_side_1024_v2_r15_v01"
R15_PLANE = {"z1": R15_ROOT / "planes/V2/A/z1/routes.json",
             "z2": R15_ROOT / "planes/V2/A/z2/routes.json"}

PLANES = ("z1", "z2")
ROW_Z = {"z1": 0.0, "z2": 0.5}


# ---------------------------------------------------------------------------
# Fixtures: layer stacks, ports, route records
# ---------------------------------------------------------------------------
def make_stack(heights=(1.0, 1.5, 2.0, 2.5), provenance="confirmed",
               allowed=None, physical_z_override=None):
    """Build a layer-stack mapping in the delivered JSON format."""
    allowed_all = allowed or {layer_id: [1, 2, 3, 4, 5]
                              for layer_id in (1, 2, 3, 4, 5)}
    layers = {
        "1": {"layer_id": 1, "layer_type": "interface", "physical_z_mm": None,
              "interface_rows": {"z1": 0.0, "z2": 0.5},
              "allowed_transitions": list(allowed_all[1])},
    }
    for offset, layer_id in enumerate((2, 3, 4, 5)):
        physical_z = heights[offset]
        if physical_z_override and layer_id in physical_z_override:
            physical_z = physical_z_override[layer_id]
        layers[str(layer_id)] = {
            "layer_id": layer_id, "layer_type": "routing",
            "physical_z_mm": physical_z, "interface_rows": {},
            "allowed_transitions": list(allowed_all[layer_id]),
        }
    return {
        "schema": V.STACK_SCHEMA,
        "provenance": provenance,
        "formal_acceptance_allowed": provenance == "confirmed",
        "note": "pytest synthetic stack",
        "interface_layer": 1,
        "layers": layers,
        "routing_heights_mm": {str(layer_id): physical_z
                               for layer_id, physical_z in
                               zip((2, 3, 4, 5), heights)},
    }


@pytest.fixture(scope="session")
def ports_data():
    """Frozen V2 port identity of the two rows (real CSV, used as reference)."""
    ports = V._fslw_ports()
    tables = {}
    for plane in PLANES:
        routes, endpoints, _connectors, _validation = ports.load_plane("V2", plane)
        tables[plane] = {"routes": {int(record["route_id"]): record
                                    for record in routes},
                         "endpoints": endpoints,
                         "by_id": {int(record["route_id"]): record
                                   for record in routes}}
    return tables


@pytest.fixture(scope="session")
def straight_route(ports_data):
    """A V2 CSV z1 route whose 2D path can be a straight line (same x)."""
    for route_id, record in sorted(ports_data["z1"]["routes"].items()):
        endpoints = ports_data["z1"]["endpoints"]
        source = endpoints[record["source_endpoint"]]["routing_xy"]
        target = endpoints[record["target_endpoint"]]["routing_xy"]
        if abs(source[0] - target[0]) < 1e-12 or abs(source[1] - target[1]) < 1e-12:
            return {"route_id": route_id, "record": record,
                    "source": tuple(source), "target": tuple(target),
                    "endpoints": endpoints}
    pytest.skip("V2 CSV has no straight opposite connection")


@pytest.fixture(scope="session")
def r15_flat_routes():
    """Two accepted R15 2D routed centre-lines far from x=5.625 (used as data)."""
    chosen = []
    for plane in PLANES:
        routes_path = R15_PLANE[plane]
        if not routes_path.exists():
            continue
        payload = json.loads(routes_path.read_text(encoding="utf-8"))
        for record in payload["routes"]:
            if record.get("status") != "routed":
                continue
            xs = []
            for primitive in record.get("primitives") or []:
                xs.append(float(primitive["p0"][0]))
                xs.append(float(primitive["p1"][0]))
            if min(xs) > 20.0 and max(xs) < 148.0:
                chosen.append({"plane": plane, "route_id": int(record["route_id"]),
                               "primitives": record["primitives"]})
                break
    return chosen


def port_xy(ports_data, plane, connector, column):
    endpoints = ports_data[plane]["endpoints"]
    row = 1 if plane == "z1" else 2
    return endpoints[f"{connector}:{row}:{column}"]["routing_xy"]


def _split_windows(length, sizes):
    """Cumulative offsets of consecutive flat pieces along a straight path."""
    starts = []
    cursor = 0.0
    for size in sizes:
        starts.append(cursor)
        cursor += size
    starts.append(cursor)
    return starts


def _transition_dict(from_layer, to_layer, z0, z1, start, direction,
                     radius=V.RADIUS_MM):
    dz = z1 - z0
    theta = math.acos(max(-1.0, min(1.0, 1.0 - abs(dz) / (2.0 * radius))))
    footprint = 2.0 * radius * math.sin(theta)
    length = 2.0 * radius * theta
    end = (start[0] + direction[0] * footprint,
           start[1] + direction[1] * footprint)
    return {
        "kind": "transition", "from_layer": from_layer, "to_layer": to_layer,
        "z0": z0, "z1": z1, "dz_mm": dz, "radius_mm": radius,
        "theta_rad": theta, "footprint_mm": footprint,
        "start": [start[0], start[1]],
        "direction": [direction[0], direction[1]],
        "end": [end[0], end[1]], "length_mm": length,
    }


def _flat_dict(layer_id, z_mm, p0, p1, primitives=None):
    if primitives is None:
        primitives = [{"kind": "line", "p0": list(p0), "p1": list(p1)}]
    length = 0.0
    for primitive in primitives:
        if primitive["kind"] == "line":
            length += math.hypot(primitive["p1"][0] - primitive["p0"][0],
                                 primitive["p1"][1] - primitive["p0"][1])
        else:
            length += abs(float(primitive["sweep"])) * float(primitive["radius"])
    return {"kind": "flat", "layer_id": layer_id, "z_mm": z_mm,
            "length_mm": length, "primitives": primitives}


def build_multi_transition_record(straight_route, stack_dict,
                                  mode="staggered"):
    """Build a valid multi-transition route: L1 -> L2 -> L3 -> L1.

    ``mode='staggered'`` keeps a flat between every transition;
    ``mode='back_to_back'`` places the L1->L2 and L2->L3 transitions directly
    adjacent (no flat between them), which must also be legal.
    """
    source = straight_route["source"]
    target = straight_route["target"]
    total = math.hypot(target[0] - source[0], target[1] - source[1])
    direction = ((target[0] - source[0]) / total,
                 (target[1] - source[1]) / total)
    heights = {}
    for layer_id in (2, 3, 4, 5):
        heights[layer_id] = float(stack_dict["layers"][str(layer_id)]["physical_z_mm"])
    z = {1: ROW_Z[straight_route["record"]["plane"]], 2: heights[2],
         3: heights[3], 4: heights[4], 5: heights[5]}

    def point(s):
        return (source[0] + direction[0] * s, source[1] + direction[1] * s)

    def transition(from_layer, to_layer, start_s):
        part = _transition_dict(from_layer, to_layer, z[from_layer],
                                z[to_layer], point(start_s), direction)
        return part, float(part["footprint_mm"])

    parts = []
    head_length = 5.0
    parts.append(_flat_dict(1, z[1], point(0.0), point(head_length)))
    cursor = head_length
    flats = [(1, z[1], 0.0, head_length)]
    if mode == "back_to_back":
        transition_12, fp12 = transition(1, 2, cursor)
        cursor += fp12
        transition_23, fp23 = transition(2, 3, cursor)
        cursor += fp23
        parts.append(transition_12)
        parts.append(transition_23)
        flat_l3_length = 5.0
        parts.append(_flat_dict(3, z[3], point(cursor),
                                point(cursor + flat_l3_length)))
        flats.append((3, z[3], cursor, cursor + flat_l3_length))
        cursor += flat_l3_length
        transition_31, fp31 = transition(3, 1, cursor)
        cursor += fp31
        parts.append(transition_31)
        parts.append(_flat_dict(1, z[1], point(cursor), point(total)))
        flats.append((1, z[1], cursor, total))
    else:
        transition_12, fp12 = transition(1, 2, cursor)
        cursor += fp12
        parts.append(transition_12)
        flat_l2_length = 5.0
        parts.append(_flat_dict(2, z[2], point(cursor),
                                point(cursor + flat_l2_length)))
        flats.append((2, z[2], cursor, cursor + flat_l2_length))
        cursor += flat_l2_length
        transition_23, fp23 = transition(2, 3, cursor)
        cursor += fp23
        parts.append(transition_23)
        flat_l3_length = 5.0
        parts.append(_flat_dict(3, z[3], point(cursor),
                                point(cursor + flat_l3_length)))
        flats.append((3, z[3], cursor, cursor + flat_l3_length))
        cursor += flat_l3_length
        transition_31, fp31 = transition(3, 1, cursor)
        cursor += fp31
        parts.append(transition_31)
        parts.append(_flat_dict(1, z[1], point(cursor), point(total)))
        flats.append((1, z[1], cursor, total))
    flat_length = sum(entry[3] - entry[2] for entry in flats)
    transition_footprint = sum(float(part["footprint_mm"])
                               for part in parts if part["kind"] == "transition")
    transition_length = sum(float(part["length_mm"])
                            for part in parts if part["kind"] == "transition")
    layer_sequence = [1, 2, 3, 1]
    layer_z_sequence = [z[layer_id] for layer_id in layer_sequence]
    record = {
        "route_id": straight_route["route_id"],
        "plane": straight_route["record"]["plane"],
        "source_row": straight_route["record"]["source_row"],
        "target_row": straight_route["record"]["target_row"],
        "start_z_mm": z[1], "end_z_mm": z[1],
        "layer_sequence": layer_sequence,
        "layer_z_sequence": layer_z_sequence,
        "n_transitions": 3, "lifted": True,
        "layers_used": [1, 2, 3],
        "xy_length_mm": flat_length + transition_footprint,
        "length_mm": flat_length + transition_length,
        "z_span_mm": max(layer_z_sequence) - min(layer_z_sequence),
        "parts": parts,
        "source_port": {"xy": list(source), "z_mm": z[1], "layer_id": 1},
        "target_port": {"xy": list(target), "z_mm": z[1], "layer_id": 1},
        "start_dir": [direction[0], direction[1]],
        "end_dir": [direction[0], direction[1]],
        "status": "routed",
        "baseline_2d": False,
        "mode": "lifted",
    }
    return record


def build_flat_record(ports_data, plane, route_id, primitives):
    """Wrap one accepted R15 2D centre-line as a flat L1 route record."""
    record = ports_data[plane]["routes"][int(route_id)]
    endpoints = ports_data[plane]["endpoints"]
    source = endpoints[record["source_endpoint"]]["routing_xy"]
    target = endpoints[record["target_endpoint"]]["routing_xy"]
    z = ROW_Z[plane]
    length = 0.0
    for primitive in primitives:
        if primitive["kind"] == "line":
            length += math.hypot(primitive["p1"][0] - primitive["p0"][0],
                                 primitive["p1"][1] - primitive["p0"][1])
        else:
            length += abs(float(primitive["sweep"])) * float(primitive["radius"])
    start_tangent = (float(primitive_tangent(primitives[0], 0.0)[0]),
                     float(primitive_tangent(primitives[0], 0.0)[1]))
    end_tangent = (float(primitive_tangent(primitives[-1], 1.0)[0]),
                   float(primitive_tangent(primitives[-1], 1.0)[1]))
    return {
        "route_id": int(route_id), "plane": plane,
        "source_row": 1 if plane == "z1" else 2,
        "target_row": 1 if plane == "z1" else 2,
        "start_z_mm": z, "end_z_mm": z,
        "layer_sequence": [1], "layer_z_sequence": [z],
        "n_transitions": 0, "lifted": False, "layers_used": [1],
        "xy_length_mm": length, "length_mm": length, "z_span_mm": 0.0,
        "parts": [_flat_dict(1, z, source, target, primitives)], 
        "source_port": {"xy": [float(source[0]), float(source[1])],
                        "z_mm": z, "layer_id": 1},
        "target_port": {"xy": [float(target[0]), float(target[1])],
                        "z_mm": z, "layer_id": 1},
        "start_dir": [start_tangent[0], start_tangent[1]],
        "end_dir": [end_tangent[0], end_tangent[1]],
        "status": "routed", "baseline_2d": True, "mode": "flat_l1",
    }


def primitive_tangent(primitive, t):
    if primitive["kind"] == "line":
        p0 = primitive["p0"]
        p1 = primitive["p1"]
        length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        return ((p1[0] - p0[0]) / length, (p1[1] - p0[1]) / length)
    sweep = float(primitive["sweep"])
    sign = 1.0 if sweep >= 0 else -1.0
    angle = float(primitive["start_angle"]) + sweep * t
    return (-sign * math.sin(angle), sign * math.cos(angle))


def build_payload(stack_dict, records, extra=None):
    payload = {
        "schema": V.ROUTES_SCHEMA,
        "topology": "V2",
        "csv_sha256": (V._fslw_ports().EXPECTED_SHA256.get("V2")),
        "stage": "pytest",
        "layer_stack": stack_dict,
        "process": {
            "board_mm": [150.0, 150.0], "width_mm": 0.05,
            "edge_gap_mm": 0.03, "clearance_mm": 0.08, "radius_mm": 15.0,
            "min_cross_angle_deg": 5.0, "crossing_policy": "strict",
        },
        "route_count": len(records),
        "routes": records,
    }
    if extra:
        payload.update(extra)
    return payload


def run(payload, **kwargs):
    kwargs.setdefault("run_frozen_2d", False)
    return V.validate_payload(payload, **kwargs)


def violation_kinds(report):
    return {(violation["kind"], violation["category"])
            for violation in report["violations"]}


# ---------------------------------------------------------------------------
# Requirement 1: L1 is the interface layer with both rows
# ---------------------------------------------------------------------------
def test_requirement1_layer_stack_L1_interface():
    stack = V.parse_layer_stack(make_stack())
    assert stack.valid and stack.confirmed and stack.height_defined
    assert stack.z_for_layer(1, "z1") == 0.0
    assert stack.z_for_layer(1, "z2") == 0.5
    assert stack.z_for_layer(2, "z1") == 1.0
    bad_rows = make_stack()
    bad_rows["layers"]["1"]["interface_rows"]["z2"] = 0.6
    stack_bad = V.parse_layer_stack(bad_rows)
    assert not stack_bad.valid
    assert any("L1_row_height_invalid" in error for error in stack_bad.errors)
    bad_type = make_stack()
    bad_type["layers"]["1"]["layer_type"] = "routing"
    assert not V.parse_layer_stack(bad_type).valid


# ---------------------------------------------------------------------------
# Requirement 2: the two rows keep 0.5 mm real 3D distance at identical XY
# ---------------------------------------------------------------------------
def test_requirement2_port_rows_keep_0p5mm(ports_data):
    report = V._Report()
    block = V._check_port_row_model(report)
    assert block["ok"], block
    assert block["pairs_checked"] == 1024
    assert block["min_3d_distance_mm"] == pytest.approx(0.5, abs=1e-12)
    assert report.total == 0, report.violations
    # synthetic identical-XY pair: same column, both rows -> 0.5 mm real distance
    xy = port_xy(ports_data, "z1", "N01", 1)
    xy2 = port_xy(ports_data, "z2", "N01", 1)
    assert xy == xy2
    distance = math.sqrt((xy[0] - xy2[0]) ** 2 + (xy[1] - xy2[1]) ** 2
                         + (0.5 - 0.0) ** 2)
    assert distance == pytest.approx(0.5, abs=1e-12)
    assert distance > V.CLEARANCE_MM


# ---------------------------------------------------------------------------
# Requirement 3: routes start/end on correct L1 ports with the row z
# ---------------------------------------------------------------------------
def test_requirement3_route_ports(straight_route):
    stack = make_stack()
    primitives = [{"kind": "line",
                   "p0": list(straight_route["source"]),
                   "p1": list(straight_route["target"])}]
    record = build_flat_record(
        {"z1": {"routes": {straight_route["route_id"]:
                           straight_route["record"]},
                "endpoints": straight_route["endpoints"]}},
        "z1", straight_route["route_id"], primitives)
    payload = build_payload(stack, [record])
    report = run(payload, allow_exploratory=True)
    assert report["counts"]["port_errors"] == 0, report["violations"]
    assert report["checks"]["route_ports"]["ok"]

    bad = copy.deepcopy(payload)
    bad["routes"][0]["source_port"]["z_mm"] = 0.05
    report_bad = run(bad, allow_exploratory=True)
    assert report_bad["counts"]["port_errors"] > 0

    bad_xy = copy.deepcopy(payload)
    bad_xy["routes"][0]["target_port"]["xy"][0] += 0.3
    report_xy = run(bad_xy, allow_exploratory=True)
    assert report_xy["counts"]["port_errors"] > 0


# ---------------------------------------------------------------------------
# Requirement 4: legal L1 -> Lk transitions (R=15 analytic formulas)
# ---------------------------------------------------------------------------
def test_requirement4_transition_from_interface(straight_route):
    stack = make_stack()
    record = build_multi_transition_record(straight_route, stack,
                                           mode="staggered")
    # drop the L2->L3 and L3->L1 transitions to keep only L1->L2->L1
    payload = build_payload(stack, [record])
    report = run(payload, allow_exploratory=True)
    kinds = violation_kinds(report)
    assert report["counts"]["geometry_errors"] == 0, report["violations"]
    assert report["counts"]["curvature_violations"] == 0, report["violations"]
    assert report["checks"]["transitions"]["interface_transitions"] == 2
    # wrong radius: analytic R=15 rule must fire
    bad = copy.deepcopy(payload)
    for part in bad["routes"][0]["parts"]:
        if part["kind"] == "transition":
            part["radius_mm"] = 40.0
    bad_report = run(bad, allow_exploratory=True)
    assert bad_report["counts"]["curvature_violations"] > 0
    assert any(kind == "transition_radius_not_r15" for kind, _ in
               violation_kinds(bad_report))
    # inconsistent footprint must fire as well
    bad_fp = copy.deepcopy(payload)
    for part in bad_fp["routes"][0]["parts"]:
        if part["kind"] == "transition":
            part["footprint_mm"] *= 0.5
            break
    fp_report = run(bad_fp, allow_exploratory=True)
    assert fp_report["counts"]["curvature_violations"] > 0


# ---------------------------------------------------------------------------
# Requirement 5: intermediate / multiple / back-to-back transitions
# ---------------------------------------------------------------------------
def test_requirement5_multi_transition_and_back_to_back(straight_route):
    stack = make_stack()
    for mode in ("staggered", "back_to_back"):
        record = build_multi_transition_record(straight_route, stack, mode=mode)
        payload = build_payload(stack, [record])
        report = run(payload, allow_exploratory=True)
        assert report["counts"]["geometry_errors"] == 0, (mode, report["violations"])
        assert report["counts"]["curvature_violations"] == 0, mode
        transitions = report["checks"]["transitions"]
        assert transitions["interface_transitions"] == 2, mode
        assert transitions["intermediate_transitions"] == 1, mode
        assert report["stats"]["multi_transition_routes"] == 1
        if mode == "back_to_back":
            assert transitions["back_to_back_transitions"] == 1
    # a transition pair that the stack does not allow must be rejected
    allowed = {1: [1, 2, 4, 5], 2: [1, 2, 4, 5], 3: [1, 3, 4, 5],
               4: [1, 2, 3, 4, 5], 5: [1, 2, 3, 4, 5]}
    stack_restricted = make_stack(allowed=allowed)
    record = build_multi_transition_record(straight_route, stack_restricted)
    report_restricted = run(build_payload(stack_restricted, [record]),
                            allow_exploratory=True)
    assert any(kind == "transition_layer_pair_not_allowed"
               for kind, _category in violation_kinds(report_restricted))
    # declared layer sequence mismatch must be reported as a contract violation
    bad = build_payload(stack, [build_multi_transition_record(straight_route,
                                                              stack)])
    bad["routes"][0]["layer_sequence"] = [1, 2, 1]
    mismatch = run(bad, allow_exploratory=True)
    assert mismatch["counts"]["contract_errors"] > 0


# ---------------------------------------------------------------------------
# Requirement 6: full-path 3D curvature (sampled <= 0.02 mm) + analytic checks
# ---------------------------------------------------------------------------
def test_requirement6_curvature(straight_route):
    stack = make_stack()
    record = build_multi_transition_record(straight_route, stack)
    report = run(build_payload(stack, [record]), allow_exploratory=True)
    minimum = report["stats"]["min_curvature_radius_mm"]
    assert minimum is not None
    assert V.MIN_CURVATURE_MM <= minimum < 15.2
    # sampled circumradius helper: a 15 mm circle gives 15 mm, a straight line inf
    angles = [index * math.pi / 900.0 for index in range(901)]
    import numpy as np
    points = np.array([[15.0 * math.cos(angle), 15.0 * math.sin(angle), 0.0]
                       for angle in angles])
    assert abs(V._polyline_min_curvature(points) - 15.0) < 1e-3
    line = np.column_stack([np.linspace(0.0, 100.0, 500),
                            np.zeros(500), np.zeros(500)])
    assert V._polyline_min_curvature(line) == float("inf")
    # diagonal line -> geometry error (requirement 6 "lines axis aligned")
    report_diag = V._Report()
    V._parse_flat_primitive({"kind": "line", "p0": [0.0, 0.0],
                             "p1": [10.0, 10.0]}, 0, report_diag, 1)
    assert report_diag.counts["geometry_errors"] > 0
    # flat arc with a wrong radius -> curvature violation
    report_arc = V._Report()
    V._parse_flat_primitive(
        {"kind": "arc", "p0": [0.0, 0.0], "p1": [10.0, 10.0],
         "center": [10.0, 0.0], "radius": 10.0,
         "start_angle": math.pi, "sweep": math.pi / 2.0}, 0, report_arc, 1)
    assert report_arc.counts["curvature_violations"] > 0


# ---------------------------------------------------------------------------
# Requirement 7: transitions vs L1 row flats keep true 3D distance (no exemption)
# ---------------------------------------------------------------------------
def _flat_geom(route_id, z_mm, p0, p1, layer_id=1, row="z1"):
    primitive = V._Prim2D("line", p0, p1)
    part = V._FlatPart(0, layer_id, z_mm, [primitive])
    return V._RouteGeom(route_id, row, 1 if row == "z1" else 2,
                        ROW_Z[row], [part])


def _transition_geom(route_id, z0, z1, start, direction, row="z1"):
    part = V._TransitionPart(0, 1, 2, z0, z1, V.RADIUS_MM, start, direction)
    return V._RouteGeom(route_id, row, 1 if row == "z1" else 2,
                        ROW_Z[row], [part])


def test_requirement7_transition_vs_l1_flat_true_3d():
    # transition rises from z=0 at (10, 0.05): its start is only 0.05 mm from the
    # L1 z=0 flat -> true 3D violation (no crossing exemption across z)
    flat = _flat_geom(1, 0.0, (0.0, 0.0), (20.0, 0.0))
    transition = _transition_geom(2, 0.0, 1.0, (10.0, 0.05), (1.0, 0.0))
    report = V._Report()
    block = V._audit_true_3d_clearance([flat, transition], report)
    assert report.counts["clearance_violations"] > 0
    assert block["transition_vs_flat"]["min_mm"] < V.CLEARANCE_MM
    # move it half a millimetre away -> legal
    transition_ok = _transition_geom(2, 0.0, 1.0, (10.0, 0.5), (1.0, 0.0))
    report_ok = V._Report()
    block_ok = V._audit_true_3d_clearance([flat, transition_ok], report_ok)
    assert report_ok.counts["clearance_violations"] == 0
    # no candidate pair inside the clearance query radius means the minimum is
    # above the clearance (the reported value is then a lower bound / None)
    minimum = block_ok["transition_vs_flat"]["min_mm"]
    assert minimum is None or minimum >= V.CLEARANCE_MM


# ---------------------------------------------------------------------------
# Requirement 8: same-plane strict rules vs different-z true 3D rules
# ---------------------------------------------------------------------------
def test_requirement8_same_plane_strict_and_rows():
    # two flat lines crossing on the same physical plane: a legal D56 crossing
    horizontal = _flat_geom(1, 0.0, (-10.0, 0.0), (10.0, 0.0))
    vertical = _flat_geom(2, 0.0, (0.0, -10.0), (0.0, 10.0))
    report = V._Report()
    block = V._audit_same_plane([horizontal, vertical], report)
    assert block["total_violations"] == 0
    assert block["crossings"] > 0
    assert report.counts["same_plane_violations"] == 0
    # two collinear overlapping lines on the same plane: overlap must be rejected
    overlap = _flat_geom(2, 0.0, (-5.0, 0.0), (15.0, 0.0))
    report_overlap = V._Report()
    block_overlap = V._audit_same_plane([horizontal, overlap], report_overlap)
    assert block_overlap["total_violations"] > 0
    # L1 z1 row (z=0) vs L1 z2 row (z=0.5), same layer_id=1, identical XY:
    # the real 3D distance is 0.5 mm -> legal, and they are different planes
    row1 = _flat_geom(3, 0.0, (0.0, 0.0), (20.0, 0.0), row="z1")
    row2 = _flat_geom(4, 0.5, (0.0, 0.0), (20.0, 0.0), row="z2")
    report_rows = V._Report()
    block_cross = V._cross_plane_flat_clearance([row1, row2], report_rows)
    assert block_cross["violations"] == 0
    assert block_cross["min_lower_bound_mm"] == pytest.approx(0.5, abs=1e-9)
    assert report_rows.counts["clearance_violations"] == 0
    assert report_rows.counts["same_plane_violations"] == 0


# ---------------------------------------------------------------------------
# Requirement 9: layer_id is never a z coordinate
# ---------------------------------------------------------------------------
def test_requirement9_layer_id_not_z():
    # (a) same layer_id, different physical z -> two distinct planes, checked in 3D
    row1 = _flat_geom(1, 0.0, (0.0, 0.0), (20.0, 0.0), layer_id=1, row="z1")
    row2 = _flat_geom(2, 0.5, (0.0, 0.0), (20.0, 0.0), layer_id=1, row="z2")
    groups = V._group_flat_parts_by_plane([row1, row2])
    assert len(groups) == 2
    assert all(len(entries) == 1 for entries in groups.values())
    # (b) different layer_ids at close z -> still checked; the stack is rejected
    close_stack = make_stack(physical_z_override={3: 1.05})
    parsed_close = V.parse_layer_stack(close_stack)
    assert not parsed_close.valid
    assert any("physical_planes_too_close" in error
               for error in parsed_close.errors)
    low = _flat_geom(3, 1.0, (0.0, 0.0), (20.0, 0.0), layer_id=2)
    high = _flat_geom(4, 1.05, (0.0, 0.0), (20.0, 0.0), layer_id=3)
    report = V._Report()
    block = V._cross_plane_flat_clearance([low, high], report)
    assert block["violations"] > 0
    assert report.counts["clearance_violations"] > 0
    block_usage = V._layer_id_usage_block([low, high], parsed_close)
    assert len(block_usage["physical_planes"]) == 2
    assert [entry["layer_ids"] for entry in block_usage["physical_planes"]] == [[2], [3]]


# ---------------------------------------------------------------------------
# Requirement 10: formal acceptance refusal while heights are unconfirmed
# ---------------------------------------------------------------------------
def test_requirement10_formal_acceptance_rules(straight_route):
    stack_confirmed = make_stack()
    stack_unconfirmed = make_stack(provenance="unconfirmed_simulation")
    record = build_multi_transition_record(straight_route, stack_confirmed)
    payload_ok = build_payload(stack_confirmed, [record])
    payload_unconfirmed = copy.deepcopy(payload_ok)
    payload_unconfirmed["layer_stack"] = stack_unconfirmed
    # confirmed + good geometry -> formal acceptance, exit 0
    report_confirmed = run(payload_ok)
    assert report_confirmed["formal_acceptance"] is True
    assert report_confirmed["status"] == "confirmed_pass"
    assert report_confirmed["exit_code"] == 0
    # unconfirmed + good geometry -> formal refusal; exploratory only
    report_unconf = run(payload_unconfirmed)
    assert report_unconf["formal_acceptance"] is False
    assert report_unconf["status"] == "exploratory_only"
    assert report_unconf["exploratory_pass"] is True
    assert report_unconf["exit_code"] == 3
    report_allowed = run(payload_unconfirmed, allow_exploratory=True)
    assert report_allowed["formal_acceptance"] is False
    assert report_allowed["exploratory_pass"] is True
    assert report_allowed["exit_code"] == 0
    # undefined L2..L5 heights -> invalid stack, geometry unavailable, exit 2
    undefined = make_stack()
    undefined["layers"]["3"]["physical_z_mm"] = None
    undefined["routing_heights_mm"].pop("3", None)
    undefined_report = run(build_payload(undefined, [record]),
                           allow_exploratory=True)
    assert undefined_report["formal_acceptance"] is False
    assert undefined_report["status"] == "invalid_stack"
    assert undefined_report["geometry_executed"] is False
    assert undefined_report["exit_code"] == 2
    # non-monotonic heights -> invalid stack
    non_monotonic = make_stack(heights=(1.5, 1.0, 2.0, 2.5))
    assert not V.parse_layer_stack(non_monotonic).valid
    # missing L4/L5 -> invalid stack
    missing = make_stack()
    missing["layers"].pop("4")
    missing["layers"].pop("5")
    assert not V.parse_layer_stack(missing).valid
    # confirmed stack but failing geometry -> formal refusal, exit 1
    bad = copy.deepcopy(payload_ok)
    for part in bad["routes"][0]["parts"]:
        if part["kind"] == "transition":
            part["radius_mm"] = 40.0
    bad_report = run(bad)
    assert bad_report["formal_acceptance"] is False
    assert bad_report["geometry_pass"] is False
    assert bad_report["exit_code"] == 1


def test_layer_stack_cli_override(straight_route, tmp_path):
    stack_confirmed = make_stack()
    stack_unconfirmed = make_stack(provenance="unconfirmed_simulation")
    record = build_multi_transition_record(straight_route, stack_confirmed)
    payload = build_payload(stack_unconfirmed, [record])
    stack_path = tmp_path / "stack_confirmed.json"
    stack_path.write_text(json.dumps(stack_confirmed), encoding="utf-8")
    report = V.validate_payload(payload, layer_stack_raw=str(stack_path),
                               run_frozen_2d=False)
    assert report["layer_stack_source"].startswith("cli_file")
    assert report["formal_acceptance"] is True
    assert report["status"] == "confirmed_pass"


# ---------------------------------------------------------------------------
# Cross-cutting: positive end-to-end payload, duplicates, self clearance, CLI
# ---------------------------------------------------------------------------
def test_positive_multi_route_payload(straight_route, r15_flat_routes):
    stack = make_stack()
    records = [build_multi_transition_record(straight_route, stack)]
    # build flat records through the frozen port identity
    ports = V._fslw_ports()
    tables = {}
    for plane in PLANES:
        routes, endpoints, _c, _v = ports.load_plane("V2", plane)
        tables[plane] = {"routes": {int(record["route_id"]): record
                                    for record in routes},
                         "endpoints": endpoints}
    for item in r15_flat_routes:
        if item["route_id"] == straight_route["route_id"]:
            continue
        records.append(build_flat_record(tables, item["plane"],
                                         item["route_id"],
                                         item["primitives"]))
    payload = build_payload(stack, records)
    report = run(payload, run_frozen_2d=True)
    assert report["formal_acceptance"] is True, report["violations"]
    assert report["counts"]["violations"] == 0, report["violations"]
    assert report["status"] == "confirmed_pass"
    assert report["exit_code"] == 0
    assert report["stats"]["lifted"] == 1
    assert report["stats"]["flat_routes"] == len(records) - 1
    assert report["stats"]["transition_count"] == 3
    assert report["stats"]["min_curvature_radius_mm"] >= V.MIN_CURVATURE_MM
    assert report["stats"]["min_3d_clearance_mm"] >= V.CLEARANCE_MM - 1e-7
    assert len(report["items"]) == 10
    assert all(item["status"] == "pass" for item in report["items"]), \
        [item for item in report["items"] if item["status"] != "pass"]


def test_duplicate_route_ids_are_reported(straight_route):
    stack = make_stack()
    primitives = [{"kind": "line",
                   "p0": list(straight_route["source"]),
                   "p1": list(straight_route["target"])}]
    tables = {"z1": {"routes": {straight_route["route_id"]:
                                straight_route["record"]},
                     "endpoints": straight_route["endpoints"]}}
    record = build_flat_record(tables, "z1", straight_route["route_id"],
                               primitives)
    payload = build_payload(stack, [record, copy.deepcopy(record)])
    report = run(payload, allow_exploratory=True)
    assert report["stats"]["duplicate_route_ids"]
    assert report["counts"]["other_errors"] > 0


def test_self_clearance_violation_is_reported():
    first = V._Prim2D("line", (0.0, 0.0), (20.0, 0.0))
    second = V._Prim2D("line", (20.0, 0.05), (0.0, 0.05))
    flat_a = V._FlatPart(0, 1, 0.0, [first])
    flat_b = V._FlatPart(1, 1, 0.05, [second])
    transition = V._TransitionPart(2, 1, 2, 0.0, 0.05, V.RADIUS_MM,
                                   (20.0, 0.0), (-1.0, 0.0))
    geom = V._RouteGeom(1, "z1", 1, 0.0, [flat_a, transition, flat_b])
    report = V._Report()
    value = V._audit_self_clearance(geom, report)
    assert report.counts["self_clearance_violations"] > 0
    assert value < V.CLEARANCE_MM


def test_cli_exit_codes_and_report_file(straight_route, tmp_path):
    stack = make_stack(provenance="unconfirmed_simulation")
    record = build_multi_transition_record(straight_route, stack)
    payload = build_payload(stack, [record])
    routes_path = tmp_path / "routes_l3d.json"
    routes_path.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "report.json"
    code = V.main(["--routes", str(routes_path), "--out", str(out)])
    assert code == 3  # unconfirmed stack: formal refused, exploratory not allowed
    assert out.exists()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema"] == V.REPORT_SCHEMA
    assert report["formal_acceptance"] is False
    assert report["status"] == "exploratory_only"
    code_allowed = V.main(["--routes", str(routes_path),
                           "--allow-exploratory", "--out", str(out),
                           "--skip-frozen-2d"])
    assert code_allowed == 0
    # unreadable routes file -> exit 2 (never a traceback)
    code_missing = V.main(["--routes", str(tmp_path / "missing.json"),
                           "--out", str(out)])
    assert code_missing == 2


# ---------------------------------------------------------------------------
# Curvature sampling robustness (regression: rounded primitive joints)
# ---------------------------------------------------------------------------
def _short_s_pair_primitives(theta=1.0, radius=15.0, joint_rounding=0.0):
    """Two tangent-continuous R15 arcs with opposite curvature (inflection)."""
    first = {"kind": "arc", "p0": [0.0, 0.0],
             "p1": [radius * math.sin(theta),
                    radius * (1.0 - math.cos(theta))],
             "center": [0.0, radius], "radius": radius,
             "start_angle": -math.pi / 2.0, "sweep": theta}
    p1 = first["p1"]
    second = {"kind": "arc",
              "p0": [p1[0] + joint_rounding, p1[1]],
              "p1": [2.0 * radius * math.sin(theta),
                     2.0 * radius * (1.0 - math.cos(theta))],
              "center": [p1[0] + radius * math.sin(theta),
                         p1[1] - radius * math.cos(theta)],
              "radius": radius, "start_angle": math.pi / 2.0 + theta,
              "sweep": -theta}
    return [first, second]


def test_curvature_is_robust_to_rounded_primitive_joints():
    # delivered coordinates are rounded to 1e-9 mm, so a shared joint of two
    # primitives can differ by a few 1e-10 mm; this must NOT be read as curvature
    primitives = _short_s_pair_primitives(joint_rounding=4.2e-10)
    parsed = [V._Prim2D.from_raw(raw) for raw in primitives]
    part = V._FlatPart(0, 1, 0.0, parsed)
    geom = V._RouteGeom(1, "z1", 1, 0.0, [part])
    report = V._Report()
    minimum = V._audit_curvature(geom, report)
    assert report.counts["curvature_violations"] == 0, report.violations
    assert minimum >= V.MIN_CURVATURE_MM
    assert minimum < 15.2
    # the uniform arclength resample must respect the <= 0.02 mm sampling rule
    points = geom.samples3d_uniform(V.CURVATURE_STEP_MM)
    spacing = np.linalg.norm(np.diff(points, axis=0), axis=1)
    assert float(np.max(spacing)) <= V.CURVATURE_STEP_MM + 1e-9


def test_curvature_still_detects_a_sharp_kink():
    primitives = [
        {"kind": "line", "p0": [0.0, 0.0], "p1": [10.0, 0.0]},
        {"kind": "line", "p0": [10.0, 0.0], "p1": [10.0, 10.0]},
    ]
    parsed = [V._Prim2D.from_raw(raw) for raw in primitives]
    part = V._FlatPart(0, 1, 0.0, parsed)
    geom = V._RouteGeom(1, "z1", 1, 0.0, [part])
    report = V._Report()
    V._audit_curvature(geom, report)
    assert report.counts["curvature_violations"] > 0
