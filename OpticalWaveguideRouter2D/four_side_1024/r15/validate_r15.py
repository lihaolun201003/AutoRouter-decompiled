"""Independent R15 acceptance wrapper for the 2026-10-20 R=15 mm round.

The process requirement of this round is **fixed radius R = 15 mm for every
planar bend and every 3D elevation S-curve**; it supersedes the historical
R = 40 mm convention (``four_side_1024/r15/README_R15.md``).  The historical R40
validator modules stay untouched: this module re-validates the R15 artefacts from
the delivered JSON only and never trusts a saved R40/R15 verdict.

Two validation layers
---------------------

1. **2D planes** (``planes/V2/<A|B>/<z1|z2>/routes.json``, frozen
   ``four_side_1024_fslw_plane_routes_v1`` schema, 512 records per plane):

   * the frozen authoritative strict audit is run with the explicit R15 radius
     override ``fslw.validate_fslw.build_report(routes_path=..., policy='strict',
     expected_route_count=512, radius=15.0, plane=...)``;
   * on top of that, every routed primitive is re-scanned independently here:
     lines axis aligned, circular arcs with ``radius == 15 mm`` exactly (1e-9),
     scheme B only ``|sweep| = pi/2`` arcs, scheme A the D56 families including
     the R=15 short-S rule ``theta = acos(1 - d/(2R))`` with lateral
     ``2R(1-cos theta)`` and longitudinal ``2R sin theta``; primitive continuity,
     x/y endpoints against the V2 port model and process record radius 15
     (``fixed_radius_40mm = false``), V2 CSV SHA256 and route identity.

2. **1024-channel combined** (``combined/V2/<A|B>/routes_1024.json``, frozen
   ``four_side_1024_fslw_combined_routes_v1`` schema): the 1024 records are split
   by their ``plane`` tag into the two 512-route plane problems and each plane is
   audited with ``fslw.validate_fslw.validate_dataset(..., radius=15.0,
   policy='strict')`` (same-plane pair audit; cross-plane XY projections are
   *not* conflicts, exactly as in the frozen SPEC).  The independent primitive
   scan, port identity and process checks are repeated on all 1024 records.

3. **3D 2.5D check** (``25d/scheme<A|B>/layers5/routes_25d.json``): the R15
   profile must be applied before importing ``fsd25d.validate25d`` (that module
   binds ``RADIUS_MM`` / ``MIN_CURVATURE_MM`` at import).  This wrapper calls the
   R15 2.5D validator CLI (it writes ``25d/validation/``) and then independently
   post-checks every transition ``radius_mm == 15`` (and the theta/footprint/
   length formulas at R=15), every flat arc radius, and that the reported
   curvature threshold really is the R15 one (14.985 mm = 15*(1-1e-3)).

Independence: no routing module is imported (``v2opt.*`` / ``fsd25d.router25d``
etc. are never touched); only the frozen validators ``fslw.validate_fslw`` and
``fsd25d.validate25d`` are *run*, and every primitive is re-derived here.

Command line::

    .venv\\Scripts\\python.exe -m four_side_1024.r15.validate_r15
    .venv\\Scripts\\python.exe -m four_side_1024.r15.validate_r15 \\
        [--root outputs/four_side_1024_v2_r15_v01] [--only 2d/A/z1] [--out DIR]

Outputs (default ``<root>/validation/``)::

    validation/2d/<label>/<plane>.json      one report per 2D plane
    validation/2d/<label>/combined.json     one report per 1024-channel combined file
    validation/25d/<label>/layers5.json     one report per 2.5D layer run
    validation/r15_validation_summary.json  aggregate (top-level ``passed`` only
                                            when every expected item exists and
                                            passes, every arc is exactly R15 and
                                            every violation counter is 0)

Missing inputs are reported as *pending* (no crash).  Exit code: 0 iff every
processed item passed, 1 if any processed item failed, 2 if nothing was processed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import OrderedDict
from pathlib import Path

from ..fslw import ports as fslw_ports
from ..fslw import validate_fslw

# ---------------------------------------------------------------------------
# R15 constants / data contract
# ---------------------------------------------------------------------------
R15_RADIUS_MM = 15.0
R15_TOL = 1e-9                  # "arc radius exactly 15 mm"
QUARTER = math.pi / 2.0
QUARTER_TOL = 1e-9              # scheme B: exactly 90 degree arcs
SHORT_S_TOL = 1e-6              # D56 short-S displacement formulas
POSE_TOL = 1e-6                 # endpoint / tangent / continuity tolerance
ORTHO_TOL = 1e-9                # axis alignment of straight primitives
ARC_ENDPOINT_TOL = 1e-6         # centre+radius+angle vs written endpoints
CLEARANCE_MM = float(validate_fslw.CLEARANCE)   # 0.080 mm
WIDTH_MM = float(validate_fslw.WIDTH)           # 0.050 mm
BOARD_MM = float(validate_fslw.BOARD)           # 150 mm
SAGITTA_MM = float(validate_fslw.SAGITTA)       # 0.0005 mm
MIN_CURVATURE_MM = R15_RADIUS_MM * (1.0 - 1e-3)  # 14.985 mm (schema tolerance)
PLANE_Z = {"z1": 0.0, "z2": 0.5}
PLANES = ("z1", "z2")
LABELS = ("A", "B")
EXPECTED_ROUTE_COUNT = 512
EXPECTED_TOTAL = 1024
R15_PROFILE_NAME = "R15_min_radius_15mm"

SCHEMA_PLANE = "four_side_1024_fslw_plane_routes_v1"
SCHEMA_COMBINED = "four_side_1024_fslw_combined_routes_v1"
SCHEMA_25D_ROUTES = "four_side_1024_v2_25d_routes_v1"
SCHEMA_25D_VALIDATION = "four_side_1024_v2_25d_validation_v1"
SCHEMA_ITEM = "four_side_1024_v2_r15_validation_item_v1"
SCHEMA_SUMMARY = "four_side_1024_v2_r15_validation_v1"

EXPECTED_CSV_SHA256 = fslw_ports.EXPECTED_SHA256.get("V2")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_ROOT / "outputs" / "four_side_1024_v2_r15_v01"

#: Violation categories of one item / of the aggregate.
CATEGORIES = (
    "contract_errors",
    "identity_errors",
    "geometry_errors",
    "strict_errors",
    "pair_audit_errors",
    "r15_25d_errors",
    "other_errors",
)

#: Violation kinds that mean "an arc is not exactly R = 15 mm".
RADIUS_KINDS = ("arc_radius_not_r15", "transition_radius_not_r15",
                "flat_arc_radius_not_r15")

MAX_STORED_VIOLATIONS = 200


# ---------------------------------------------------------------------------
# Violation collector
# ---------------------------------------------------------------------------
class _ItemReport:
    """Counts violations per category with capped detail storage."""

    def __init__(self, max_stored=MAX_STORED_VIOLATIONS):
        self.counts = OrderedDict((name, 0) for name in CATEGORIES)
        self.violations = []
        self.warnings = []
        self.max_stored = int(max_stored)
        self._stored = 0

    def add(self, category, kind, detail=None, route_id=None, plane=None,
            primitive=None, **extra):
        if category not in self.counts:
            raise KeyError(category)
        self.counts[category] += 1
        if self._stored >= self.max_stored:
            return
        self._stored += 1
        entry = {"kind": kind, "category": category}
        if route_id is not None:
            entry["route_id"] = route_id
        if plane is not None:
            entry["plane"] = plane
        if primitive is not None:
            entry["primitive"] = primitive
        if detail is not None:
            entry["detail"] = detail
        entry.update(extra)
        self.violations.append(entry)

    def warn(self, message):
        if len(self.warnings) < 100:
            self.warnings.append(str(message))

    @property
    def total(self):
        return sum(self.counts.values())


def _finalise_counts(report):
    counts = OrderedDict()
    counts["violations"] = report.total
    for name in CATEGORIES:
        counts[name] = report.counts[name]
    return counts


# ---------------------------------------------------------------------------
# Small numeric helpers / primitive model
# ---------------------------------------------------------------------------
class _DataError(Exception):
    """Raised when a JSON value cannot be interpreted at all."""


def _as_float(value, what):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise _DataError(f"invalid_{what}")
    if not math.isfinite(number):
        raise _DataError(f"nonfinite_{what}")
    return number


def _as_xy(value, what):
    try:
        if isinstance(value, (str, bytes)) or len(value) != 2:
            raise ValueError
        x = float(value[0])
        y = float(value[1])
    except (TypeError, ValueError, IndexError):
        raise _DataError(f"invalid_{what}")
    if not (math.isfinite(x) and math.isfinite(y)):
        raise _DataError(f"nonfinite_{what}")
    return (x, y)


class _Prim:
    """Parsed line/arc primitive with its own analytic geometry."""

    __slots__ = ("kind", "p0", "p1", "center", "radius", "start_angle", "sweep",
                 "length", "raw")

    def __init__(self, kind, p0, p1, center=None, radius=0.0, start_angle=0.0,
                 sweep=0.0, raw=None):
        self.kind = kind
        self.p0 = p0
        self.p1 = p1
        self.center = center
        self.radius = radius
        self.start_angle = start_angle
        self.sweep = sweep
        self.raw = raw
        self.length = (math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                       if kind == "line" else abs(sweep) * radius)

    def point(self, t):
        if self.kind == "line":
            return (self.p0[0] + (self.p1[0] - self.p0[0]) * t,
                    self.p0[1] + (self.p1[1] - self.p0[1]) * t)
        angle = self.start_angle + self.sweep * t
        return (self.center[0] + self.radius * math.cos(angle),
                self.center[1] + self.radius * math.sin(angle))

    def tangent(self, t):
        if self.kind == "line":
            return ((self.p1[0] - self.p0[0]) / self.length,
                    (self.p1[1] - self.p0[1]) / self.length)
        sign = 1.0 if self.sweep >= 0.0 else -1.0
        angle = self.start_angle + self.sweep * t
        return (-sign * math.sin(angle), sign * math.cos(angle))


def _parse_primitive(raw, index, scheme, report, route_id=None):
    """Parse one flat primitive; returns ``_Prim`` (or ``None`` on hard errors)."""
    where = f"primitive={index}"
    if not isinstance(raw, dict):
        report.add("geometry_errors", "primitive_not_a_mapping",
                   detail=where, route_id=route_id, primitive=index)
        return None
    kind = raw.get("kind")
    try:
        p0 = _as_xy(raw.get("p0"), "p0")
        p1 = _as_xy(raw.get("p1"), "p1")
    except _DataError as exc:
        report.add("geometry_errors", "primitive_endpoints_invalid",
                   detail=f"{where} {exc}", route_id=route_id, primitive=index)
        return None
    layer = raw.get("layer", 0)
    if layer not in (0, 0.0, None):
        report.add("geometry_errors", "primitive_nonzero_layer",
                   detail=f"{where} layer={layer!r}", route_id=route_id,
                   primitive=index)
    if kind == "line":
        prim = _Prim("line", p0, p1, raw=raw)
        if prim.length <= R15_TOL:
            report.add("geometry_errors", "zero_length_line", detail=where,
                       route_id=route_id, primitive=index)
        if not (abs(p1[0] - p0[0]) <= ORTHO_TOL
                or abs(p1[1] - p0[1]) <= ORTHO_TOL):
            report.add("geometry_errors", "diagonal_line",
                       detail=f"{where} p0={p0} p1={p1}", route_id=route_id,
                       primitive=index)
        return prim
    if kind != "arc":
        report.add("geometry_errors", "unknown_primitive_kind",
                   detail=f"{where} kind={kind!r}", route_id=route_id,
                   primitive=index)
        return None
    try:
        center = _as_xy(raw.get("center"), "center")
        radius = _as_float(raw.get("radius"), "radius")
        start_angle = _as_float(raw.get("start_angle"), "start_angle")
        sweep = _as_float(raw.get("sweep"), "sweep")
    except _DataError as exc:
        report.add("geometry_errors", "arc_parameters_invalid",
                   detail=f"{where} {exc}", route_id=route_id, primitive=index)
        return None
    if radius <= R15_TOL:
        report.add("geometry_errors", "arc_radius_not_positive",
                   detail=f"{where} radius={radius!r}", route_id=route_id,
                   primitive=index)
        return None
    if abs(sweep) <= R15_TOL or abs(sweep) > 2.0 * math.pi + R15_TOL:
        report.add("geometry_errors", "arc_sweep_invalid",
                   detail=f"{where} sweep={sweep!r}", route_id=route_id,
                   primitive=index)
        return None
    prim = _Prim("arc", p0, p1, center, radius, start_angle, sweep, raw=raw)
    # independent R15 rule: every circular arc must have radius exactly 15 mm
    if abs(radius - R15_RADIUS_MM) > R15_TOL:
        report.add("geometry_errors", "arc_radius_not_r15",
                   detail=f"{where} radius={radius!r} (expected 15)",
                   route_id=route_id, primitive=index)
    # the analytic arc description must reproduce its written endpoints
    for name, angle, endpoint in (("p0", start_angle, p0),
                                  ("p1", start_angle + sweep, p1)):
        reconstructed = (center[0] + radius * math.cos(angle),
                         center[1] + radius * math.sin(angle))
        if math.hypot(reconstructed[0] - endpoint[0],
                      reconstructed[1] - endpoint[1]) > ARC_ENDPOINT_TOL:
            report.add("geometry_errors", "arc_endpoint_inconsistent",
                       detail=f"{where} {name}", route_id=route_id,
                       primitive=index)
    # scheme rules
    is_quarter = abs(abs(sweep) - QUARTER) <= QUARTER_TOL
    if scheme == "B":
        if not is_quarter:
            report.add("geometry_errors", "non_90_arc_scheme_b",
                       detail=f"{where} sweep={math.degrees(sweep):.9f} deg",
                       route_id=route_id, primitive=index)
    return prim


def _short_s_pair_ok(first, second):
    """D56 short-S pair at the pair's own radius (R15 expected for this round)."""
    theta = abs(first.sweep)
    if not (R15_TOL < theta < QUARTER - R15_TOL):
        return False
    if abs(abs(second.sweep) - theta) > SHORT_S_TOL:
        return False
    if first.sweep * second.sweep >= 0.0:
        return False
    tangent = first.tangent(0.0)
    delta = (second.p1[0] - first.p0[0], second.p1[1] - first.p0[1])
    longitudinal = tangent[0] * delta[0] + tangent[1] * delta[1]
    lateral = abs(tangent[0] * delta[1] - tangent[1] * delta[0])
    expected_lateral = 2.0 * first.radius * (1.0 - math.cos(theta))
    expected_longitudinal = 2.0 * first.radius * math.sin(theta)
    return (abs(lateral - expected_lateral) <= SHORT_S_TOL
            and abs(longitudinal - expected_longitudinal) <= SHORT_S_TOL)


def _check_short_s_family(primitives, report, route_id=None):
    """Scheme A: every non-quarter arc must belong to a valid short-S pair."""
    index = 0
    count = len(primitives)
    pairs = 0
    while index < count:
        prim = primitives[index]
        if (prim is None or prim.kind != "arc"
                or abs(abs(prim.sweep) - QUARTER) <= QUARTER_TOL):
            index += 1
            continue
        other = index + 1
        gap = 0.0
        while other < count and primitives[other] is not None \
                and primitives[other].kind == "line":
            gap += primitives[other].length
            other += 1
        if (other < count and primitives[other] is not None
                and primitives[other].kind == "arc"
                and gap <= POSE_TOL
                and _short_s_pair_ok(prim, primitives[other])):
            pairs += 1
            index = other + 1
            continue
        report.add("geometry_errors", "short_s_invalid",
                   detail=f"primitive={index} "
                          f"sweep={math.degrees(prim.sweep):.9f} deg",
                   route_id=route_id, primitive=index)
        index += 1
    return pairs


def _scan_primitives(primitives, scheme, report, route_id=None):
    """Independently scan a primitive chain (R15 radius/sweep/ortho rules).

    Returns ``(parsed_primitives, geometry_stats)`` where the stats hold the
    independent R15 evidence (arc counts, radius min/max/deviation, quarter-arc
    and short-S counts, line count).
    """
    stats = {
        "lines": 0,
        "arcs": 0,
        "quarter_arcs": 0,
        "short_s_pairs": 0,
        "arc_radius_values": set(),
        "arc_radius_min_mm": None,
        "arc_radius_max_mm": None,
        "arc_radius_deviation_max_mm": 0.0,
        "zero_length_lines": 0,
        "diagonal_lines": 0,
        "primitives": 0,
    }
    if not isinstance(primitives, list) or not primitives:
        report.add("geometry_errors", "missing_primitives", route_id=route_id)
        return [], stats
    parsed = []
    for index, raw in enumerate(primitives):
        stats["primitives"] += 1
        prim = _parse_primitive(raw, index, scheme, report, route_id)
        parsed.append(prim)
        if prim is None:
            continue
        if prim.kind == "line":
            stats["lines"] += 1
            if prim.length <= R15_TOL:
                stats["zero_length_lines"] += 1
            if not (abs(prim.p1[0] - prim.p0[0]) <= ORTHO_TOL
                    or abs(prim.p1[1] - prim.p0[1]) <= ORTHO_TOL):
                stats["diagonal_lines"] += 1
        else:
            stats["arcs"] += 1
            stats["arc_radius_values"].add(round(prim.radius, 9))
            deviation = abs(prim.radius - R15_RADIUS_MM)
            stats["arc_radius_deviation_max_mm"] = max(
                stats["arc_radius_deviation_max_mm"], deviation)
            if stats["arc_radius_min_mm"] is None \
                    or prim.radius < stats["arc_radius_min_mm"]:
                stats["arc_radius_min_mm"] = prim.radius
            if stats["arc_radius_max_mm"] is None \
                    or prim.radius > stats["arc_radius_max_mm"]:
                stats["arc_radius_max_mm"] = prim.radius
            if abs(abs(prim.sweep) - QUARTER) <= QUARTER_TOL:
                stats["quarter_arcs"] += 1
    # position continuity of the chain (independent structure check)
    for index in range(1, len(parsed)):
        previous = parsed[index - 1]
        current = parsed[index]
        if previous is None or current is None:
            continue
        distance = math.hypot(previous.p1[0] - current.p0[0],
                              previous.p1[1] - current.p0[1])
        if distance > POSE_TOL:
            report.add("geometry_errors", "primitive_discontinuity",
                       detail=f"joint={index} distance={distance:.9g}",
                       route_id=route_id, primitive=index)
    if scheme == "A":
        stats["short_s_pairs"] = _check_short_s_family(parsed, report,
                                                       route_id=route_id)
    stats["arc_radius_values"] = sorted(stats["arc_radius_values"])
    return parsed, stats


def _empty_geometry_stats():
    return {
        "lines": 0, "arcs": 0, "quarter_arcs": 0, "short_s_pairs": 0,
        "arc_radius_values": set(), "arc_radius_min_mm": None,
        "arc_radius_max_mm": None, "arc_radius_deviation_max_mm": 0.0,
        "zero_length_lines": 0, "diagonal_lines": 0, "primitives": 0,
    }


def _merge_geometry_stats(total, stats):
    total["lines"] += stats["lines"]
    total["arcs"] += stats["arcs"]
    total["quarter_arcs"] += stats["quarter_arcs"]
    total["short_s_pairs"] += stats["short_s_pairs"]
    total["primitives"] += stats["primitives"]
    total["zero_length_lines"] += stats["zero_length_lines"]
    total["diagonal_lines"] += stats["diagonal_lines"]
    total["arc_radius_values"].update(stats["arc_radius_values"])
    total["arc_radius_deviation_max_mm"] = max(
        total["arc_radius_deviation_max_mm"],
        stats["arc_radius_deviation_max_mm"])
    for key, pick in (("arc_radius_min_mm", min), ("arc_radius_max_mm", max)):
        value = stats[key]
        if value is None:
            continue
        if total[key] is None:
            total[key] = value
        else:
            total[key] = pick(total[key], value)


def _finalise_geometry_stats(stats):
    stats = dict(stats)
    stats["arc_radius_values"] = sorted(stats["arc_radius_values"])
    return stats


# ---------------------------------------------------------------------------
# Frozen V2 identity (ports / CSV)
# ---------------------------------------------------------------------------
_IDENTITY_CACHE = {}


def _load_identity(report=None):
    """Load the frozen V2 port model once: route identity + plane endpoints."""
    if "identity" in _IDENTITY_CACHE:
        return _IDENTITY_CACHE["identity"]
    identity = {"available": False, "error": None,
                "routes": {}, "endpoints": {}, "endpoints_by_plane": {},
                "csv_sha256": None}
    try:
        for plane in PLANES:
            routes, endpoints, _connectors, validation = fslw_ports.load_plane(
                "V2", plane)
            identity["endpoints_by_plane"][plane] = endpoints
            identity["endpoints"].update(endpoints)
            identity["csv_sha256"] = validation.get("csv_sha256")
            for record in routes:
                identity["routes"][int(record["route_id"])] = {
                    "plane": plane,
                    "pair": record.get("pair"),
                    "relation": record.get("relation"),
                    "source_endpoint": record.get("source_endpoint"),
                    "target_endpoint": record.get("target_endpoint"),
                }
        identity["available"] = True
    except (OSError, ValueError, KeyError, TypeError) as exc:
        identity["error"] = f"{type(exc).__name__}: {exc}"
        if report is not None:
            report.add("identity_errors", "v2_port_model_unavailable",
                       detail=identity["error"])
    _IDENTITY_CACHE["identity"] = identity
    return identity


def _tangent_pose(parsed):
    """Start/end point and tangents of a parsed primitive chain."""
    if not parsed or parsed[0] is None or parsed[-1] is None:
        return None
    return {
        "start": parsed[0].p0,
        "end": parsed[-1].p1,
        "start_tangent": parsed[0].tangent(0.0),
        "end_tangent": parsed[-1].tangent(1.0),
    }


def _check_record_identity(record, parsed, identity, plane, report):
    """Port/CSV identity of one routed record (independent of the frozen audit)."""
    route_id = record.get("route_id")
    try:
        route_id = int(route_id)
    except (TypeError, ValueError):
        report.add("identity_errors", "route_id_invalid", plane=plane,
                   detail=repr(record.get("route_id")))
        return
    info = identity["routes"].get(route_id)
    if info is None:
        report.add("identity_errors", "route_id_not_in_v2_csv",
                   route_id=route_id, plane=plane)
        return
    if info["plane"] != plane:
        report.add("identity_errors", "record_plane_mismatch",
                   route_id=route_id, plane=plane,
                   detail=f"{plane} != {info['plane']}")
    if record.get("pair") != info["pair"]:
        report.add("identity_errors", "record_pair_mismatch", route_id=route_id,
                   plane=plane,
                   detail=f"{record.get('pair')!r} != {info['pair']!r}")
    if record.get("relation") != info["relation"]:
        report.add("identity_errors", "record_relation_mismatch",
                   route_id=route_id, plane=plane,
                   detail=f"{record.get('relation')!r} != {info['relation']!r}")
    # static record metadata
    if record.get("plane") != plane:
        report.add("contract_errors", "record_plane_tag", route_id=route_id,
                   plane=plane, detail=f"{record.get('plane')!r}")
    if record.get("layer") not in (0, 0.0, None):
        report.add("contract_errors", "record_layer_not_zero", route_id=route_id,
                   plane=plane, detail=repr(record.get("layer")))
    expected_z = PLANE_Z[plane]
    declared_z = record.get("z_mm")
    if declared_z is not None:
        try:
            if abs(float(declared_z) - expected_z) > 1e-9:
                report.add("contract_errors", "record_z_mismatch",
                           route_id=route_id, plane=plane,
                           detail=f"{declared_z} != {expected_z}")
        except (TypeError, ValueError):
            report.add("contract_errors", "record_z_invalid",
                       route_id=route_id, plane=plane, detail=repr(declared_z))
    endpoints = identity["endpoints"]
    source = endpoints.get(info["source_endpoint"])
    target = endpoints.get(info["target_endpoint"])
    if source is None or target is None:
        report.add("identity_errors", "v2_endpoint_missing",
                   route_id=route_id, plane=plane)
        return
    pose = _tangent_pose(parsed)
    if pose is None:
        return
    for name, actual, expected in (
            ("start_xy", pose["start"], source["routing_xy"]),
            ("end_xy", pose["end"], target["routing_xy"])):
        distance = math.hypot(actual[0] - expected[0], actual[1] - expected[1])
        if distance > POSE_TOL:
            report.add("identity_errors", f"{name}_mismatch", route_id=route_id,
                       plane=plane,
                       detail=f"{actual} vs {tuple(expected)} distance={distance:.9g}")
    expected_start_tangent = tuple(source["inward"])
    expected_end_tangent = (-target["inward"][0], -target["inward"][1])
    for name, actual, expected in (
            ("start_tangent", pose["start_tangent"], expected_start_tangent),
            ("end_tangent", pose["end_tangent"], expected_end_tangent)):
        distance = math.hypot(actual[0] - expected[0], actual[1] - expected[1])
        if distance > POSE_TOL:
            report.add("identity_errors", f"{name}_mismatch", route_id=route_id,
                       plane=plane,
                       detail=f"{actual} vs {expected} distance={distance:.9g}")


class _PortUsage:
    """Counts V2 port identities used by the records of one plane/problem."""

    def __init__(self):
        self.usage = {}

    def add_record(self, record):
        for key in ("source_endpoint", "target_endpoint"):
            endpoint = record.get(key)
            if isinstance(endpoint, str):
                self.usage[endpoint] = self.usage.get(endpoint, 0) + 1

    def check(self, report, plane, expected_ports=EXPECTED_TOTAL):
        if not self.usage:
            return
        if len(self.usage) != expected_ports \
                or set(self.usage.values()) != {1}:
            report.add("identity_errors", "port_usage_invalid", plane=plane,
                       detail=f"{len(self.usage)} ports, counts="
                              f"{sorted(set(self.usage.values()))}")


# ---------------------------------------------------------------------------
# Process record check (radius 15, not 40)
# ---------------------------------------------------------------------------
def _check_process(process, report, where=""):
    """Verify the embedded process config is the R15 profile (radius 15, not 40)."""
    info = {
        "radius_mm": None,
        "fixed_radius_40mm": None,
        "process_profile": None,
        "radius_ok": False,
        "fixed_radius_40mm_ok": False,
        "clearance_mm": None,
        "width_mm": None,
        "board_mm": None,
    }
    if not isinstance(process, dict):
        report.add("contract_errors", "process_missing", detail=where)
        return info
    radius_fields = ("radius_mm", "min_bend_radius_mm", "min_radius_mm",
                     "bend_radius_mm")
    present = [(name, process.get(name)) for name in radius_fields
               if process.get(name) is not None]
    if not present:
        report.add("contract_errors", "process_radius_missing", detail=where)
    else:
        info["radius_mm"] = None
        for name, value in present:
            try:
                radius = float(value)
            except (TypeError, ValueError):
                report.add("contract_errors", "process_radius_invalid",
                           detail=f"{where} {name}={value!r}")
                continue
            if info["radius_mm"] is None:
                info["radius_mm"] = radius
            if abs(radius - R15_RADIUS_MM) > R15_TOL:
                report.add("contract_errors", "process_radius_not_r15",
                           detail=f"{where} {name}={radius!r} (expected 15)")
            # explicit "not the historical 40 mm" evidence
            if abs(radius - 40.0) <= 1e-6:
                report.add("contract_errors", "process_radius_is_r40",
                           detail=f"{where} {name}={radius!r}")
        info["radius_ok"] = all(abs(float(value) - R15_RADIUS_MM) <= R15_TOL
                                for _name, value in present
                                if isinstance(value, (int, float)))
    fixed = process.get("fixed_radius_40mm")
    info["fixed_radius_40mm"] = fixed
    if fixed is None:
        report.add("contract_errors", "process_fixed_radius_flag_missing",
                   detail=where)
    elif bool(fixed):
        report.add("contract_errors", "process_fixed_radius_40mm_true",
                   detail=where)
    else:
        info["fixed_radius_40mm_ok"] = True
    profile = process.get("process_profile")
    info["process_profile"] = profile
    if profile is not None and str(profile) != R15_PROFILE_NAME:
        report.add("contract_errors", "process_profile_mismatch",
                   detail=f"{where} {profile!r} != {R15_PROFILE_NAME!r}")
    clearance = None
    for key in ("min_centerline_clearance_mm", "clearance_mm",
                "centerline_clearance_mm"):
        try:
            clearance = float(process.get(key))
            break
        except (TypeError, ValueError):
            continue
    if clearance is None:
        report.add("contract_errors", "process_clearance_missing", detail=where)
    else:
        info["clearance_mm"] = clearance
        if abs(clearance - CLEARANCE_MM) > 1e-9:
            report.add("contract_errors", "process_clearance_mismatch",
                       detail=f"{where} {clearance} != {CLEARANCE_MM}")
    width = None
    for key in ("waveguide_width_mm", "width_mm"):
        try:
            width = float(process.get(key))
            break
        except (TypeError, ValueError):
            continue
    if width is None:
        report.add("contract_errors", "process_width_missing", detail=where)
    else:
        info["width_mm"] = width
        if abs(width - WIDTH_MM) > 1e-9:
            report.add("contract_errors", "process_width_mismatch",
                       detail=f"{where} {width} != {WIDTH_MM}")
    board = process.get("board_mm")
    if isinstance(board, (list, tuple)) and len(board) == 2:
        try:
            info["board_mm"] = [float(board[0]), float(board[1])]
            if any(abs(float(value) - BOARD_MM) > 1e-9 for value in board):
                report.add("contract_errors", "process_board_mismatch",
                           detail=f"{where} {board}")
        except (TypeError, ValueError):
            report.add("contract_errors", "process_board_invalid", detail=where)
    else:
        report.add("contract_errors", "process_board_missing", detail=where)
    return info


def _check_payload_contract(payload, expected_schema, report,
                            require_csv_sha=True):
    """Schema-level contract shared by plane and combined payloads."""
    info = {"schema": None, "algorithm": None, "topology": None,
            "csv_sha256": None, "csv_sha256_ok": False, "planes": None}
    if not isinstance(payload, dict):
        raise _DataError("payload_not_a_mapping")
    info["schema"] = payload.get("schema")
    if info["schema"] != expected_schema:
        report.add("contract_errors", "schema_mismatch",
                   detail=f"{info['schema']!r} != {expected_schema!r}")
    info["algorithm"] = payload.get("algorithm")
    if payload.get("topology") is not None and payload.get("topology") != "V2":
        report.add("contract_errors", "topology_mismatch",
                   detail=repr(payload.get("topology")))
    info["topology"] = payload.get("topology")
    csv_sha = payload.get("csv_sha256")
    info["csv_sha256"] = csv_sha
    if EXPECTED_CSV_SHA256 is not None and require_csv_sha:
        if csv_sha is None:
            report.add("identity_errors", "csv_sha256_missing")
        elif str(csv_sha).lower() != EXPECTED_CSV_SHA256.lower():
            report.add("identity_errors", "csv_sha256_mismatch",
                       detail=f"{csv_sha!r} != {EXPECTED_CSV_SHA256!r}")
        else:
            info["csv_sha256_ok"] = True
    routes = payload.get("routes")
    if not isinstance(routes, list):
        report.add("contract_errors", "routes_missing")
        raise _DataError("routes_not_a_list")
    return info


# ---------------------------------------------------------------------------
# 2D plane item
# ---------------------------------------------------------------------------
def _strict_2d_block(routes_path, plane, report, run_frozen=True,
                     label=None):
    """Run the frozen authoritative strict 2D audit with the R15 override."""
    block = {
        "enabled": bool(run_frozen),
        "radius_mm": R15_RADIUS_MM,
        "policy": "strict",
        "passed": None,
        "route_count": None,
        "routed_count": None,
        "failed_status_count": None,
        "d56_passed_count": None,
        "d56_failed_count": None,
        "violation_pair_count": 0,
        "violations": 0,
        "crossing_count": None,
        "crossing_pair_count": None,
        "min_non_crossing_centerline_mm": None,
        "errors": [],
        "warnings": [],
        "fixed_radius_40mm": None,
    }
    if not run_frozen:
        return block
    try:
        result = validate_fslw.build_report(
            routes_path=routes_path, policy="strict",
            expected_route_count=EXPECTED_ROUTE_COUNT,
            radius=R15_RADIUS_MM, plane=plane)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report.add("strict_errors", "strict_2d_audit_crashed",
                   detail=f"{type(exc).__name__}: {exc}")
        block["errors"] = [f"crash:{type(exc).__name__}: {exc}"]
        return block
    block.update({
        "passed": bool(result.get("passed")),
        "route_count": result.get("route_count"),
        "routed_count": result.get("routed_count"),
        "failed_status_count": result.get("failed_status_count"),
        "d56_passed_count": result.get("d56_passed_count"),
        "d56_failed_count": result.get("d56_failed_count"),
        "violation_pair_count": int(result.get("violation_pair_count") or 0),
        "violations": len(result.get("violations") or []),
        "crossing_count": result.get("crossing_count"),
        "crossing_pair_count": result.get("crossing_pair_count"),
        "min_non_crossing_centerline_mm": result.get(
            "min_non_crossing_centerline_mm"),
        "errors": list(result.get("errors") or []),
        "warnings": list(result.get("warnings") or []),
        "fixed_radius_40mm": (result.get("process") or {}).get(
            "fixed_radius_40mm"),
    })
    # the frozen report must itself be R15-based
    process = result.get("process") or {}
    if process.get("radius_mm") is not None:
        try:
            if abs(float(process["radius_mm"]) - R15_RADIUS_MM) > R15_TOL:
                report.add("strict_errors", "strict_2d_radius_not_r15",
                           detail=f"{process['radius_mm']!r}")
        except (TypeError, ValueError):
            report.add("strict_errors", "strict_2d_radius_invalid",
                       detail=repr(process.get("radius_mm")))
    if block["fixed_radius_40mm"]:
        report.add("strict_errors", "strict_2d_fixed_radius_40mm",
                   detail="frozen report resolved the R40 process")
    if not block["passed"]:
        for error in block["errors"][:50]:
            report.add("strict_errors", "frozen_2d_audit_error", detail=error)
        for violation in (result.get("violations") or [])[:50]:
            report.add("strict_errors",
                       str(violation.get("kind") or "pair_violation"),
                       route_id=violation.get("route_a"),
                       detail=f"other={violation.get('route_b')} "
                              f"distance={violation.get('distance_mm')}")
    if result.get("route_count") != EXPECTED_ROUTE_COUNT:
        report.add("strict_errors", "strict_2d_route_count",
                   detail=f"{result.get('route_count')} != "
                          f"{EXPECTED_ROUTE_COUNT}")
    if result.get("d56_failed_count"):
        report.add("strict_errors", "strict_2d_d56_failed",
                   detail=str(result.get("d56_failed_count")))
    return block


def validate_plane_2d(routes_path, label, plane, *, identity=None,
                      out_path=None, run_frozen=True):
    """Independently validate one R15 2D plane ``routes.json``; returns the item."""
    started = time.perf_counter()
    routes_path = Path(routes_path)
    report = _ItemReport()
    item = {
        "schema": SCHEMA_ITEM,
        "item": f"2d/{label}/{plane}",
        "kind": "2d_plane",
        "label": label,
        "plane": plane,
        "input": str(routes_path),
        "output": str(out_path) if out_path is not None else None,
        "passed": False,
        "routed": None,
        "failed": None,
        "total": None,
        "counts": None,
        "violations": report.violations,
        "warnings": report.warnings,
        "geometry": None,
        "identity": None,
        "process": None,
        "strict_2d": None,
        "runtime_seconds": None,
    }
    try:
        payload = json.loads(routes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.add("contract_errors", "input_unreadable",
                   detail=f"{type(exc).__name__}: {exc}")
        item["counts"] = _finalise_counts(report)
        item["runtime_seconds"] = round(time.perf_counter() - started, 3)
        return item
    try:
        contract = _check_payload_contract(payload, SCHEMA_PLANE, report)
    except _DataError as exc:
        report.add("contract_errors", "payload_invalid", detail=str(exc))
        item["counts"] = _finalise_counts(report)
        item["runtime_seconds"] = round(time.perf_counter() - started, 3)
        return item
    algorithm = contract.get("algorithm")
    if algorithm is not None and str(algorithm) != label:
        report.add("contract_errors", "algorithm_mismatch",
                   detail=f"{algorithm!r} != {label!r}")
    payload_plane = payload.get("plane")
    if payload_plane is not None and str(payload_plane) != plane:
        report.add("contract_errors", "payload_plane_mismatch",
                   detail=f"{payload_plane!r} != {plane!r}")
    item["process"] = _check_process(payload.get("process"), report,
                                     where=f"{label}/{plane}")
    if identity is None:
        identity = _load_identity(report)
    item["identity"] = {
        "v2_port_model_available": bool(identity.get("available")),
        "v2_error": identity.get("error"),
        "csv_sha256": contract.get("csv_sha256"),
        "csv_sha256_ok": bool(contract.get("csv_sha256_ok")),
        "identity_checked": bool(identity.get("available")),
    }
    routes = payload["routes"]
    if len(routes) != EXPECTED_ROUTE_COUNT:
        report.add("contract_errors", "route_count_mismatch",
                   detail=f"{len(routes)} != {EXPECTED_ROUTE_COUNT}")
    route_ids = []
    routed = failed = 0
    geometry = _empty_geometry_stats()
    port_usage = _PortUsage()
    for record in routes:
        if not isinstance(record, dict):
            report.add("contract_errors", "route_not_a_mapping")
            continue
        route_ids.append(record.get("route_id"))
        port_usage.add_record(record)
        status = record.get("status")
        if status != "routed":
            failed += 1
            continue
        routed += 1
        try:
            primitives = record.get("primitives")
            parsed, stats = _scan_primitives(primitives, label, report,
                                             route_id=record.get("route_id"))
            _merge_geometry_stats(geometry, stats)
            if identity.get("available"):
                _check_record_identity(record, parsed, identity, plane, report)
        except _DataError as exc:
            report.add("geometry_errors", "record_unparseable",
                       route_id=record.get("route_id"), detail=str(exc))
    duplicates = {value for value in route_ids if route_ids.count(value) > 1}
    if duplicates:
        report.add("contract_errors", "duplicate_route_id",
                   detail=str(sorted(duplicates)[:10]))
    if identity.get("available"):
        port_usage.check(report, plane)
    item["routed"] = routed
    item["failed"] = failed
    item["total"] = len(routes)
    item["geometry"] = _finalise_geometry_stats(geometry)
    item["identity"]["ports_used"] = len(port_usage.usage)
    item["identity"]["ports_expected"] = EXPECTED_TOTAL
    if identity.get("available"):
        missing = [route_id for route_id in route_ids
                   if isinstance(route_id, (int, float))
                   and int(route_id) not in identity["routes"]]
        item["identity"]["route_ids_not_in_csv"] = sorted(missing)[:10]
        if missing:
            report.add("identity_errors", "route_ids_not_in_v2_csv",
                       detail=str(sorted(missing)[:10]))
    item["strict_2d"] = _strict_2d_block(routes_path, plane, report,
                                         run_frozen=run_frozen, label=label)
    item["counts"] = _finalise_counts(report)
    item["passed"] = _item_passed(item, report)
    item["violations"] = report.violations
    item["warnings"] = report.warnings
    item["runtime_seconds"] = round(time.perf_counter() - started, 3)
    if out_path is not None:
        _write_json(Path(out_path), item)
    return item


# ---------------------------------------------------------------------------
# 2D combined item (1024 records, same-plane audits only)
# ---------------------------------------------------------------------------
def _audit_combined_plane_records(records, label, plane, routes_path, report):
    """Frozen strict audit of one plane slice of a combined 1024 file."""
    block = {
        "plane": plane,
        "enabled": True,
        "radius_mm": R15_RADIUS_MM,
        "policy": "strict",
        "passed": None,
        "route_count": None,
        "routed_count": None,
        "failed_status_count": None,
        "d56_failed_count": None,
        "violation_pair_count": 0,
        "crossings": None,
        "min_non_crossing_centerline_mm": None,
        "errors": [],
        "warnings": [],
    }
    endpoints = validate_fslw.build_plane_endpoints(plane)
    try:
        result = validate_fslw.validate_dataset(
            records, endpoints,
            expected_route_count=EXPECTED_ROUTE_COUNT,
            audit_pairs=True, policy="strict",
            radius=R15_RADIUS_MM, clearance=CLEARANCE_MM, width=WIDTH_MM,
            board=BOARD_MM, plane=plane,
            source_description=f"{routes_path}[{plane}]",
            run_dir=Path(routes_path).parent)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report.add("pair_audit_errors", "combined_plane_audit_crashed",
                   detail=f"{plane}: {type(exc).__name__}: {exc}")
        block["errors"] = [f"crash:{type(exc).__name__}: {exc}"]
        return block
    block.update({
        "passed": bool(result.get("passed")),
        "route_count": result.get("route_count"),
        "routed_count": result.get("routed_count"),
        "failed_status_count": result.get("failed_status_count"),
        "d56_failed_count": result.get("d56_failed_count"),
        "violation_pair_count": int(result.get("violation_pair_count") or 0),
        "crossings": result.get("crossing_count"),
        "min_non_crossing_centerline_mm": result.get(
            "min_non_crossing_centerline_mm"),
        "errors": list(result.get("errors") or []),
        "warnings": list(result.get("warnings") or []),
    })
    process = result.get("process") or {}
    if process.get("radius_mm") is not None:
        try:
            if abs(float(process["radius_mm"]) - R15_RADIUS_MM) > R15_TOL:
                report.add("pair_audit_errors", "combined_audit_radius_not_r15",
                           detail=f"{plane}: {process['radius_mm']!r}")
        except (TypeError, ValueError):
            report.add("pair_audit_errors", "combined_audit_radius_invalid",
                       detail=f"{plane}: {process.get('radius_mm')!r}")
    if not block["passed"]:
        for error in block["errors"][:50]:
            report.add("pair_audit_errors", "combined_plane_audit_error",
                       detail=f"{plane}: {error}")
        for violation in (result.get("violations") or [])[:50]:
            report.add("pair_audit_errors",
                       str(violation.get("kind") or "pair_violation"),
                       route_id=violation.get("route_a"),
                       detail=f"{plane}: other={violation.get('route_b')} "
                              f"distance={violation.get('distance_mm')}")
    if result.get("route_count") != EXPECTED_ROUTE_COUNT:
        report.add("pair_audit_errors", "combined_plane_route_count",
                   detail=f"{plane}: {result.get('route_count')} != "
                          f"{EXPECTED_ROUTE_COUNT}")
    return block


def validate_combined_2d(routes_path, label, *, identity=None, out_path=None,
                         run_frozen=True):
    """Validate one R15 1024-channel combined file (same-plane audits only)."""
    started = time.perf_counter()
    routes_path = Path(routes_path)
    report = _ItemReport()
    item = {
        "schema": SCHEMA_ITEM,
        "item": f"2d/{label}/combined",
        "kind": "2d_combined",
        "label": label,
        "plane": None,
        "input": str(routes_path),
        "output": str(out_path) if out_path is not None else None,
        "passed": False,
        "routed": None,
        "failed": None,
        "total": None,
        "counts": None,
        "violations": report.violations,
        "warnings": report.warnings,
        "geometry": None,
        "identity": None,
        "process": None,
        "plane_audits": None,
        "cross_plane_policy": ("plane z1 and z2 are separate 2D problems; "
                               "cross-plane XY-projected overlaps are NOT "
                               "conflicts (frozen SPEC section 2)"),
        "runtime_seconds": None,
    }
    try:
        payload = json.loads(routes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.add("contract_errors", "input_unreadable",
                   detail=f"{type(exc).__name__}: {exc}")
        item["counts"] = _finalise_counts(report)
        item["runtime_seconds"] = round(time.perf_counter() - started, 3)
        return item
    try:
        contract = _check_payload_contract(payload, SCHEMA_COMBINED, report,
                                           require_csv_sha=False)
    except _DataError as exc:
        report.add("contract_errors", "payload_invalid", detail=str(exc))
        item["counts"] = _finalise_counts(report)
        item["runtime_seconds"] = round(time.perf_counter() - started, 3)
        return item
    algorithm = contract.get("algorithm")
    if algorithm is not None and str(algorithm) != label:
        report.add("contract_errors", "algorithm_mismatch",
                   detail=f"{algorithm!r} != {label!r}")
    item["process"] = _check_process(payload.get("process"), report,
                                     where=f"{label}/combined")
    if identity is None:
        identity = _load_identity(report)
    item["identity"] = {
        "v2_port_model_available": bool(identity.get("available")),
        "v2_error": identity.get("error"),
        "csv_sha256": contract.get("csv_sha256"),
        "csv_sha256_ok": bool(contract.get("csv_sha256_ok")),
        "csv_sha256_note": ("combined payload has no top-level csv_sha256; "
                            "identity is checked per record against the V2 CSV"),
    }
    routes = payload["routes"]
    if len(routes) != EXPECTED_TOTAL:
        report.add("contract_errors", "combined_route_count_mismatch",
                   detail=f"{len(routes)} != {EXPECTED_TOTAL}")
    # split by plane tag and require a clean 512/512 partition
    by_plane = {plane: [] for plane in PLANES}
    geometry = _empty_geometry_stats()
    routed = failed = 0
    route_ids = []
    port_usage = {plane: _PortUsage() for plane in PLANES}
    for record in routes:
        if not isinstance(record, dict):
            report.add("contract_errors", "route_not_a_mapping")
            continue
        route_ids.append(record.get("route_id"))
        plane = record.get("plane")
        if plane not in PLANES:
            report.add("contract_errors", "record_plane_tag_invalid",
                       route_id=record.get("route_id"), detail=repr(plane))
            continue
        by_plane[plane].append(record)
        port_usage[plane].add_record(record)
        status = record.get("status")
        if status != "routed":
            failed += 1
            continue
        routed += 1
        try:
            parsed, stats = _scan_primitives(record.get("primitives"), label,
                                             report,
                                             route_id=record.get("route_id"))
            _merge_geometry_stats(geometry, stats)
            if identity.get("available"):
                _check_record_identity(record, parsed, identity, plane, report)
        except _DataError as exc:
            report.add("geometry_errors", "record_unparseable",
                       route_id=record.get("route_id"), detail=str(exc))
    for plane in PLANES:
        if len(by_plane[plane]) != EXPECTED_ROUTE_COUNT:
            report.add("contract_errors", "combined_plane_count_mismatch",
                       plane=plane,
                       detail=f"{len(by_plane[plane])} != {EXPECTED_ROUTE_COUNT}")
    duplicates = {value for value in route_ids if route_ids.count(value) > 1}
    if duplicates:
        report.add("contract_errors", "duplicate_route_id",
                   detail=str(sorted(duplicates)[:10]))
    if len({value for value in route_ids if value is not None}) != EXPECTED_TOTAL:
        report.add("contract_errors", "combined_unique_route_ids",
                   detail=str(len({value for value in route_ids
                                   if value is not None})))
    if identity.get("available"):
        for plane in PLANES:
            port_usage[plane].check(report, plane)
            missing = [record.get("route_id") for record in by_plane[plane]
                       if isinstance(record.get("route_id"), (int, float))
                       and int(record["route_id"]) not in identity["routes"]]
            if missing:
                report.add("identity_errors", "route_ids_not_in_v2_csv",
                           plane=plane, detail=str(sorted(missing)[:10]))
    plane_audits = OrderedDict()
    if run_frozen:
        for plane in PLANES:
            if len(by_plane[plane]) != EXPECTED_ROUTE_COUNT:
                plane_audits[plane] = {"plane": plane, "passed": False,
                                       "errors": ["plane_slice_incomplete"]}
                report.add("pair_audit_errors", "plane_slice_incomplete",
                           plane=plane)
                continue
            plane_audits[plane] = _audit_combined_plane_records(
                by_plane[plane], label, plane, routes_path, report)
    else:
        plane_audits = {plane: {"plane": plane, "enabled": False}
                        for plane in PLANES}
    item["routed"] = routed
    item["failed"] = failed
    item["total"] = len(routes)
    item["geometry"] = _finalise_geometry_stats(geometry)
    item["identity"]["route_ids_not_in_csv"] = 0
    item["identity"]["planes"] = {
        plane: {"records": len(by_plane[plane]),
                "ports_used": len(port_usage[plane].usage)}
        for plane in PLANES}
    item["plane_audits"] = plane_audits
    item["counts"] = _finalise_counts(report)
    item["passed"] = _item_passed(item, report)
    item["violations"] = report.violations
    item["warnings"] = report.warnings
    item["runtime_seconds"] = round(time.perf_counter() - started, 3)
    if out_path is not None:
        _write_json(Path(out_path), item)
    return item


# ---------------------------------------------------------------------------
# 2.5D R15 item
# ---------------------------------------------------------------------------
def _import_validate25d():
    """Apply the R15 profile *before* importing the 2.5D validator (import binds R)."""
    from . import profile_r15
    profile_r15.apply()
    from ..fsd25d import validate25d
    return validate25d


def _postcheck_25d_routes(routes_path, report):
    """Independent R15 scan of every 2.5D transition and flat arc."""
    stats = {
        "transitions": 0,
        "lifted": 0,
        "flat_arcs": 0,
        "flat_lines": 0,
        "transition_radius_values": set(),
        "flat_arc_radius_values": set(),
        "arc_radius_deviation_max_mm": 0.0,
        "violations": 0,
        "process_radius_mm": None,
        "scheme": None,
        "n_layers": None,
        "layers_z_mm": None,
    }
    routes_path = Path(routes_path)
    payload = json.loads(routes_path.read_text(encoding="utf-8"))
    stats["scheme"] = payload.get("scheme")
    stats["n_layers"] = payload.get("n_layers")
    stats["layers_z_mm"] = payload.get("layers_z_mm")
    if payload.get("schema") != SCHEMA_25D_ROUTES:
        report.add("r15_25d_errors", "schema_mismatch",
                   detail=f"{payload.get('schema')!r} != {SCHEMA_25D_ROUTES!r}")
    process = payload.get("process")
    if isinstance(process, dict):
        try:
            stats["process_radius_mm"] = float(process.get("radius_mm"))
        except (TypeError, ValueError):
            stats["process_radius_mm"] = None
        if stats["process_radius_mm"] is None \
                or abs(stats["process_radius_mm"] - R15_RADIUS_MM) > R15_TOL:
            report.add("r15_25d_errors", "process_radius_not_r15",
                       detail=repr(process.get("radius_mm")))
    else:
        report.add("r15_25d_errors", "process_missing")
    routes = payload.get("routes") or []
    for record in routes:
        if not isinstance(record, dict) or record.get("status") != "routed":
            continue
        route_id = record.get("route_id")
        for part in record.get("parts") or []:
            kind = part.get("kind") if isinstance(part, dict) else None
            if kind == "transition":
                stats["transitions"] += 1
                try:
                    radius = float(part.get("radius_mm"))
                except (TypeError, ValueError):
                    report.add("r15_25d_errors", "transition_radius_invalid",
                               route_id=route_id, detail=repr(part.get("radius_mm")))
                    stats["violations"] += 1
                    continue
                stats["transition_radius_values"].add(round(radius, 9))
                deviation = abs(radius - R15_RADIUS_MM)
                stats["arc_radius_deviation_max_mm"] = max(
                    stats["arc_radius_deviation_max_mm"], deviation)
                if deviation > R15_TOL:
                    report.add("r15_25d_errors", "transition_radius_not_r15",
                               route_id=route_id,
                               detail=f"radius={radius!r} (expected 15)")
                    stats["violations"] += 1
                # independent theta/footprint/length check at R = 15
                try:
                    z0 = float(part["z0_mm"])
                    z1 = float(part["z1_mm"])
                    dz = abs(z1 - z0)
                    theta = math.acos(max(-1.0, min(1.0,
                                                    1.0 - dz / (2.0 * R15_RADIUS_MM))))
                    footprint = 2.0 * R15_RADIUS_MM * math.sin(theta)
                    length = 2.0 * R15_RADIUS_MM * theta
                    declared_footprint = float(part["footprint_mm"])
                    declared_length = float(part["length_mm"])
                except (KeyError, TypeError, ValueError):
                    report.add("r15_25d_errors", "transition_fields_invalid",
                               route_id=route_id)
                    stats["violations"] += 1
                    continue
                if abs(footprint - declared_footprint) > POSE_TOL:
                    report.add("r15_25d_errors",
                               "transition_footprint_not_r15", route_id=route_id,
                               detail=f"{declared_footprint!r} != {footprint!r}")
                    stats["violations"] += 1
                if abs(length - declared_length) > POSE_TOL:
                    report.add("r15_25d_errors", "transition_length_not_r15",
                               route_id=route_id,
                               detail=f"{declared_length!r} != {length!r}")
                    stats["violations"] += 1
            elif kind == "flat":
                parsed, geo = _scan_primitives(part.get("primitives"),
                                               "A" if payload.get("scheme") == "A"
                                               else "B", report,
                                               route_id=route_id)
                stats["flat_arcs"] += geo["arcs"]
                stats["flat_lines"] += geo["lines"]
                stats["flat_arc_radius_values"].update(geo["arc_radius_values"])
                stats["arc_radius_deviation_max_mm"] = max(
                    stats["arc_radius_deviation_max_mm"],
                    geo["arc_radius_deviation_max_mm"])
                if geo["arc_radius_deviation_max_mm"] > R15_TOL:
                    stats["violations"] += 1
    stats["transition_radius_values"] = sorted(stats["transition_radius_values"])
    stats["flat_arc_radius_values"] = sorted(stats["flat_arc_radius_values"])
    if stats["lifted"] == 0:
        stats["lifted"] = sum(1 for record in routes
                              if isinstance(record, dict)
                              and record.get("mode") == "lifted")
    return stats


def _run_25d_cli(root):
    """Apply R15, import ``fsd25d.validate25d`` and run its CLI exactly once.

    ``fsd25d.validate25d`` binds ``RADIUS_MM`` / ``MIN_CURVATURE_MM`` at import, so
    the R15 profile must be applied first; the import is therefore lazy and never
    happens at this module's import time.
    """
    root = Path(root)
    info = {"module": None, "exit_code": None, "radius_mm": None,
            "min_curvature_mm": None, "error": None, "ran": False}
    try:
        validate25d = _import_validate25d()
    except Exception as exc:  # noqa: BLE001 - report, never crash the CLI
        info["error"] = f"import_failed: {type(exc).__name__}: {exc}"
        return info
    info["module"] = validate25d
    info["radius_mm"] = float(getattr(validate25d, "RADIUS_MM", 0.0))
    info["min_curvature_mm"] = float(getattr(validate25d, "MIN_CURVATURE_MM", 0.0))
    routes_exist = any(
        (root / "25d" / f"scheme{label}" / "layers5"
         / "routes_25d.json").exists()
        for label in LABELS)
    if not routes_exist:
        return info
    info["ran"] = True
    try:
        info["exit_code"] = validate25d.main(["--root", str(root / "25d")])
    except SystemExit as exc:  # pragma: no cover - main returns, does not raise
        info["exit_code"] = int(getattr(exc, "code", 1) or 0)
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"run_failed: {type(exc).__name__}: {exc}"
    return info


def validate_25d_item(root, label, *, out_path=None, cli_info=None):
    """Validate one R15 2.5D layer run through ``fsd25d.validate25d`` + post-checks."""
    started = time.perf_counter()
    root = Path(root)
    routes_path = root / "25d" / f"scheme{label}" / "layers5" / "routes_25d.json"
    validation_dir = root / "25d" / "validation"
    report = _ItemReport()
    item = {
        "schema": SCHEMA_ITEM,
        "item": f"25d/{label}/layers5",
        "kind": "25d",
        "label": label,
        "plane": None,
        "input": str(routes_path),
        "output": str(out_path) if out_path is not None else None,
        "validation_report": str(validation_dir / label / "layers5.json"),
        "passed": False,
        "routed": None,
        "failed": None,
        "total": None,
        "counts": None,
        "violations": report.violations,
        "warnings": report.warnings,
        "geometry": None,
        "curvature": None,
        "crossings": None,
        "postcheck": None,
        "runtime_seconds": None,
    }
    if cli_info is None:
        cli_info = _run_25d_cli(root)
    if cli_info.get("module") is None:
        report.add("r15_25d_errors", "validate25d_import_failed",
                   detail=str(cli_info.get("error")))
        item["counts"] = _finalise_counts(report)
        item["runtime_seconds"] = round(time.perf_counter() - started, 3)
        return item
    constants = {
        "RADIUS_MM": float(cli_info.get("radius_mm") or 0.0),
        "MIN_CURVATURE_MM": float(cli_info.get("min_curvature_mm") or 0.0),
    }
    if abs(constants["RADIUS_MM"] - R15_RADIUS_MM) > R15_TOL:
        report.add("r15_25d_errors", "validate25d_not_r15_profile",
                   detail=f"RADIUS_MM={constants['RADIUS_MM']!r}")
    if abs(constants["MIN_CURVATURE_MM"] - MIN_CURVATURE_MM) > 1e-9:
        report.add("r15_25d_errors", "validate25d_curvature_threshold",
                   detail=f"MIN_CURVATURE_MM={constants['MIN_CURVATURE_MM']!r} "
                          f"(expected {MIN_CURVATURE_MM})")
    item["curvature"] = {
        "validate25d_radius_mm": constants["RADIUS_MM"],
        "min_curvature_threshold_mm": constants["MIN_CURVATURE_MM"],
        "r15_based": (abs(constants["RADIUS_MM"] - R15_RADIUS_MM) <= R15_TOL
                      and abs(constants["MIN_CURVATURE_MM"] - MIN_CURVATURE_MM)
                      <= 1e-9),
    }
    item["validation_exit_code"] = cli_info.get("exit_code")
    if cli_info.get("error"):
        report.add("r15_25d_errors", "validate25d_run_failed",
                   detail=str(cli_info["error"]))
    if not routes_path.exists():
        report.add("r15_25d_errors", "routes_25d_missing",
                   detail=str(routes_path))
        item["counts"] = _finalise_counts(report)
        item["runtime_seconds"] = round(time.perf_counter() - started, 3)
        return item
    report_path = validation_dir / label / "layers5.json"
    validation_report = None
    if report_path.exists():
        try:
            validation_report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            report.add("r15_25d_errors", "validation_report_unreadable",
                       detail=f"{type(exc).__name__}: {exc}")
    else:
        report.add("r15_25d_errors", "validation_report_missing",
                   detail=str(report_path))
    if isinstance(validation_report, dict):
        item["routed"] = validation_report.get("routed")
        item["failed"] = validation_report.get("failed")
        item["total"] = validation_report.get("total")
        item["crossings"] = validation_report.get("crossings")
        item["curvature"]["min_curvature_radius_mm"] = validation_report.get(
            "min_curvature_radius_mm")
        item["curvature"]["min_3d_distance_mm"] = validation_report.get(
            "min_3d_distance_excluding_crossings_mm")
        if validation_report.get("schema") != SCHEMA_25D_VALIDATION:
            report.add("r15_25d_errors", "validation_schema_mismatch",
                       detail=repr(validation_report.get("schema")))
        if not validation_report.get("passed"):
            report.add("r15_25d_errors", "validation_not_passed",
                       detail=str(validation_report.get("failure_reasons")))
        counts = validation_report.get("counts") or {}
        for name, value in counts.items():
            if name != "violations" and value:
                report.add("r15_25d_errors", f"validation_{name}",
                           detail=str(value))
        if counts.get("violations"):
            report.add("r15_25d_errors", "validation_violations",
                       detail=str(counts.get("violations")))
        min_curvature = validation_report.get("min_curvature_radius_mm")
        if min_curvature is None:
            report.add("r15_25d_errors", "curvature_not_measured")
        elif float(min_curvature) < MIN_CURVATURE_MM:
            report.add("r15_25d_errors", "curvature_below_r15_limit",
                       detail=f"{min_curvature} < {MIN_CURVATURE_MM}")
        process = validation_report.get("process")
        if isinstance(process, dict):
            try:
                radius = float(process.get("radius_mm"))
                if abs(radius - R15_RADIUS_MM) > R15_TOL:
                    report.add("r15_25d_errors", "validation_process_radius",
                               detail=repr(process.get("radius_mm")))
            except (TypeError, ValueError):
                report.add("r15_25d_errors", "validation_process_radius_missing")
        else:
            report.add("r15_25d_errors", "validation_process_missing")
    # independent transition / flat-arc R15 post-check
    try:
        postcheck = _postcheck_25d_routes(routes_path, report)
    except (OSError, json.JSONDecodeError, _DataError) as exc:
        report.add("r15_25d_errors", "routes_25d_unreadable",
                   detail=f"{type(exc).__name__}: {exc}")
        postcheck = None
    item["postcheck"] = postcheck
    if postcheck is not None:
        item["geometry"] = {
            "flat_arcs": postcheck["flat_arcs"],
            "flat_lines": postcheck["flat_lines"],
            "transitions": postcheck["transitions"],
            "flat_arc_radius_values": postcheck["flat_arc_radius_values"],
            "transition_radius_values": postcheck["transition_radius_values"],
            "arc_radius_deviation_max_mm": postcheck[
                "arc_radius_deviation_max_mm"],
        }
        if postcheck["transitions"] == 0:
            report.warn("no transitions in this 2.5D run")
        for value_list, what in (
                (postcheck["transition_radius_values"], "transition"),
                (postcheck["flat_arc_radius_values"], "flat arc")):
            for value in value_list:
                if abs(float(value) - R15_RADIUS_MM) > R15_TOL:
                    report.add("r15_25d_errors", f"{what}_radius_not_r15",
                               detail=repr(value))
    item["counts"] = _finalise_counts(report)
    item["passed"] = _item_passed(item, report)
    item["violations"] = report.violations
    item["warnings"] = report.warnings
    item["runtime_seconds"] = round(time.perf_counter() - started, 3)
    if out_path is not None:
        _write_json(Path(out_path), item)
    return item


# ---------------------------------------------------------------------------
# Item verdict / IO / aggregate
# ---------------------------------------------------------------------------
def _item_passed(item, report):
    """An item passes only with zero violations and explicit R15 evidence."""
    if report.total:
        return False
    geometry = item.get("geometry") or {}
    if geometry.get("arc_radius_deviation_max_mm"):
        if float(geometry["arc_radius_deviation_max_mm"]) > R15_TOL:
            return False
    values = set()
    for key in ("arc_radius_values", "flat_arc_radius_values",
                "transition_radius_values"):
        for value in geometry.get(key) or []:
            values.add(float(value))
    if any(abs(value - R15_RADIUS_MM) > R15_TOL for value in values):
        return False
    strict = item.get("strict_2d")
    if isinstance(strict, dict) and strict.get("enabled"):
        if not strict.get("passed"):
            return False
        if strict.get("fixed_radius_40mm"):
            return False
    audits = item.get("plane_audits")
    if isinstance(audits, dict):
        for block in audits.values():
            if isinstance(block, dict) and block.get("enabled", True):
                if not block.get("passed"):
                    return False
    if item.get("kind") == "25d":
        curvature = item.get("curvature") or {}
        if not curvature.get("r15_based"):
            return False
        if curvature.get("min_curvature_radius_mm") is None:
            return False
        if float(curvature["min_curvature_radius_mm"]) < MIN_CURVATURE_MM:
            return False
    process = item.get("process")
    if isinstance(process, dict):
        if not process.get("radius_ok"):
            return False
        if not process.get("fixed_radius_40mm_ok"):
            return False
    return True


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str),
                    encoding="utf-8")
    return path


def _expected_items(root, skip_combined=False, skip_25d=False):
    root = Path(root)
    items = []
    for label in LABELS:
        for plane in PLANES:
            items.append({
                "key": f"2d/{label}/{plane}",
                "kind": "2d_plane",
                "label": label,
                "plane": plane,
                "input": root / "planes" / "V2" / label / plane / "routes.json",
                "out": root / "validation" / "2d" / label / f"{plane}.json",
            })
        if not skip_combined:
            items.append({
                "key": f"2d/{label}/combined",
                "kind": "2d_combined",
                "label": label,
                "plane": None,
                "input": root / "combined" / "V2" / label / "routes_1024.json",
                "out": root / "validation" / "2d" / label / "combined.json",
            })
        if not skip_25d:
            items.append({
                "key": f"25d/{label}/layers5",
                "kind": "25d",
                "label": label,
                "plane": None,
                "input": root / "25d" / f"scheme{label}" / "layers5"
                         / "routes_25d.json",
                "out": root / "validation" / "25d" / label / "layers5.json",
            })
    return items


def _matches_only(key, only):
    if not only:
        return True
    segments = key.split("/")
    for token in only:
        token = str(token).strip()
        if not token:
            continue
        if key == token or key.startswith(token + "/") or token in segments:
            return True
    return False


def _aggregate_counts(items):
    counts = OrderedDict((name, 0) for name in CATEGORIES)
    counts["violations"] = 0
    for item in items:
        item_counts = item.get("counts") or {}
        for name in CATEGORIES:
            counts[name] += int(item_counts.get(name) or 0)
        counts["violations"] += int(item_counts.get("violations") or 0)
    return counts


def _aggregate_geometry(items):
    total = {
        "arc_count": 0,
        "line_count": 0,
        "quarter_arc_count": 0,
        "short_s_pair_count": 0,
        "transition_count": 0,
        "arc_radius_values": set(),
        "arc_radius_deviation_max_mm": 0.0,
        "min_arc_radius_mm": None,
        "max_arc_radius_mm": None,
    }
    for item in items:
        geometry = item.get("geometry") or {}
        total["arc_count"] += int(geometry.get("arcs") or 0) + int(
            geometry.get("flat_arcs") or 0)
        total["line_count"] += int(geometry.get("lines") or 0) + int(
            geometry.get("flat_lines") or 0)
        total["quarter_arc_count"] += int(geometry.get("quarter_arcs") or 0)
        total["short_s_pair_count"] += int(geometry.get("short_s_pairs") or 0)
        total["transition_count"] += int(geometry.get("transitions") or 0)
        for value in geometry.get("arc_radius_values") or []:
            total["arc_radius_values"].add(round(float(value), 9))
        for value in geometry.get("flat_arc_radius_values") or []:
            total["arc_radius_values"].add(round(float(value), 9))
        for value in geometry.get("transition_radius_values") or []:
            total["arc_radius_values"].add(round(float(value), 9))
        total["arc_radius_deviation_max_mm"] = max(
            total["arc_radius_deviation_max_mm"],
            float(geometry.get("arc_radius_deviation_max_mm") or 0.0))
        for key, source_keys, pick in (
                ("min_arc_radius_mm", ("arc_radius_min_mm", "min_arc_radius_mm"),
                 min),
                ("max_arc_radius_mm", ("arc_radius_max_mm", "max_arc_radius_mm"),
                 max)):
            value = None
            for source_key in source_keys:
                if geometry.get(source_key) is not None:
                    value = geometry[source_key]
                    break
            if value is None:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if total[key] is None:
                total[key] = value
            else:
                total[key] = pick(total[key], value)
    # arcs are only fully evidenced when at least one arc was scanned
    radii = sorted(total["arc_radius_values"])
    total["arc_radius_values"] = radii
    total["all_arcs_exactly_r15"] = (
        bool(radii) and all(abs(value - R15_RADIUS_MM) <= R15_TOL
                            for value in radii))
    return total


def _summary_passed(items, pending, counts, geometry):
    if pending or not items:
        return False
    if any(not item.get("passed") for item in items):
        return False
    if any(int(counts.get(name) or 0) for name in CATEGORIES):
        return False
    if not geometry.get("all_arcs_exactly_r15"):
        return False
    return True


def validate_all(root, *, out_dir=None, only=None, skip_combined=False,
                 skip_25d=False, check_port_csv=True, run_frozen=True,
                 write=True):
    """Validate every existing R15 artefact; returns the aggregate summary dict."""
    from . import profile_r15
    started = time.perf_counter()
    root = Path(root)
    out_dir = Path(out_dir) if out_dir is not None else root / "validation"
    expected = [entry for entry in _expected_items(root, skip_combined=skip_combined,
                                                  skip_25d=skip_25d)
                if _matches_only(entry["key"], only)]
    if not check_port_csv:
        _IDENTITY_CACHE.pop("identity", None)
    identity = _load_identity() if check_port_csv else {
        "available": False, "routes": {}, "endpoints": {},
        "endpoints_by_plane": {}, "csv_sha256": None,
        "error": "disabled by --no-port-csv"}
    profile_info = {
        "name": R15_PROFILE_NAME,
        "radius_mm": R15_RADIUS_MM,
        "min_curvature_threshold_mm": MIN_CURVATURE_MM,
        "profile_module": "four_side_1024.r15.profile_r15",
        "profile_applied": None,
        "validate25d_radius_mm": None,
        "validate25d_min_curvature_mm": None,
        "fslw_config_radius_mm": None,
    }
    try:
        profile_r15.apply()
        profile_info["profile_applied"] = True
        from ..fslw import config as fslw_config
        profile_info["fslw_config_radius_mm"] = float(fslw_config.RADIUS_MM)
        if abs(float(fslw_config.RADIUS_MM) - R15_RADIUS_MM) > R15_TOL:
            profile_info["profile_applied"] = False
    except Exception as exc:  # noqa: BLE001
        profile_info["profile_error"] = f"{type(exc).__name__}: {exc}"
    items = OrderedDict()
    pending = []
    # the frozen 2.5D validator CLI is run once (it validates every existing
    # scheme/layers directory and writes 25d/validation/ itself)
    cli_info = None
    if any(entry["kind"] == "25d" for entry in expected) and any(
            Path(entry["input"]).exists() for entry in expected
            if entry["kind"] == "25d"):
        cli_info = _run_25d_cli(root)
        profile_info["validate25d_radius_mm"] = cli_info.get("radius_mm")
        profile_info["validate25d_min_curvature_mm"] = (
            cli_info.get("min_curvature_mm"))
        profile_info["validate25d_ran"] = bool(cli_info.get("ran"))
        profile_info["validate25d_exit_code"] = cli_info.get("exit_code")
        if cli_info.get("error"):
            profile_info["validate25d_error"] = cli_info["error"]
    for entry in expected:
        key = entry["key"]
        input_path = Path(entry["input"])
        out_path = out_dir / Path(entry["out"]).relative_to(root / "validation") \
            if write else None
        if not input_path.exists():
            pending.append({"item": key, "input": str(input_path),
                            "reason": "missing_input"})
            continue
        try:
            if entry["kind"] == "2d_plane":
                item = validate_plane_2d(
                    input_path, entry["label"], entry["plane"],
                    identity=identity, out_path=out_path,
                    run_frozen=run_frozen)
            elif entry["kind"] == "2d_combined":
                item = validate_combined_2d(
                    input_path, entry["label"], identity=identity,
                    out_path=out_path, run_frozen=run_frozen)
            else:
                item = validate_25d_item(
                    root, entry["label"],
                    out_path=out_path, cli_info=cli_info)
            items[key] = item
        except Exception as exc:  # noqa: BLE001 - one bad item never kills the run
            item = {
                "schema": SCHEMA_ITEM, "item": key, "kind": entry["kind"],
                "label": entry["label"], "plane": entry["plane"],
                "input": str(input_path), "passed": False,
                "counts": {name: 0 for name in CATEGORIES},
                "violations": [{"kind": "item_crashed",
                                "category": "other_errors",
                                "detail": f"{type(exc).__name__}: {exc}"}],
                "warnings": [], "runtime_seconds": 0.0,
            }
            item["counts"]["other_errors"] = 1
            item["counts"]["violations"] = 1
            items[key] = item
            if write and out_path is not None:
                _write_json(out_path, item)
    item_list = list(items.values())
    counts = _aggregate_counts(item_list)
    geometry = _aggregate_geometry(item_list)
    passed = _summary_passed(item_list, pending, counts, geometry)
    summary = {
        "schema": SCHEMA_SUMMARY,
        "root": str(root),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "profile": profile_info,
        "items_expected": [entry["key"] for entry in expected],
        "items": OrderedDict((key, _item_digest(item))
                             for key, item in items.items()),
        "pending": pending,
        "passed": passed,
        "counts": counts,
        "geometry": geometry,
        "skipped": {
            "combined": bool(skip_combined),
            "25d": bool(skip_25d),
        },
        "only": list(only or []),
        "runtime_seconds": None,
    }
    summary["runtime_seconds"] = round(time.perf_counter() - started, 3)
    if write:
        _write_json(out_dir / "r15_validation_summary.json", summary)
    _SUMMARY_CACHE["summary"] = summary
    return summary


def _item_digest(item):
    """Compact per-item digest embedded in the aggregate summary."""
    return {
        "kind": item.get("kind"),
        "label": item.get("label"),
        "plane": item.get("plane"),
        "input": item.get("input"),
        "output": item.get("output"),
        "passed": bool(item.get("passed")),
        "routed": item.get("routed"),
        "failed": item.get("failed"),
        "total": item.get("total"),
        "counts": item.get("counts"),
        "geometry": item.get("geometry"),
        "curvature": item.get("curvature"),
        "crossings": item.get("crossings"),
        "strict_2d_passed": (item.get("strict_2d") or {}).get("passed"),
        "runtime_seconds": item.get("runtime_seconds"),
    }


_SUMMARY_CACHE = {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_summary(summary):
    items = summary.get("items") or {}
    header = (f"{'item':22s} {'kind':12s} {'routed':>6s} {'arcs':>6s} "
              f"{'minR_mm':>8s} {'viol':>5s} {'pass':>5s} {'sec':>6s}")
    print(header)
    print("-" * len(header))
    for key, digest in items.items():
        geometry = digest.get("geometry") or {}
        arcs = int(geometry.get("arcs") or 0) + int(geometry.get("flat_arcs") or 0)
        curvature = digest.get("curvature") or {}
        min_r = curvature.get("min_curvature_radius_mm")
        counts = digest.get("counts") or {}
        print(f"{key:22s} {str(digest.get('kind')):12s} "
              f"{str(digest.get('routed')):>6s} {arcs:>6d} "
              f"{('n/a' if min_r is None else f'{float(min_r):.6f}'):>8s} "
              f"{int(counts.get('violations') or 0):>5d} "
              f"{('PASS' if digest.get('passed') else 'FAIL'):>5s} "
              f"{float(digest.get('runtime_seconds') or 0.0):>6.2f}")
    print()
    print(f"items: {len(items)} processed, {len(summary.get('pending') or [])} pending, "
          f"passed={summary.get('passed')}, "
          f"arcs={'all R15' if summary['geometry'].get('all_arcs_exactly_r15') else 'R15 NOT PROVEN'}, "
          f"violations={summary['counts'].get('violations')}")
    geometry = summary.get("geometry") or {}
    print(f"arcs={geometry.get('arc_count')} "
          f"(R values {geometry.get('arc_radius_values')}), "
          f"transitions={geometry.get('transition_count')}, "
          f"arc radius deviation max="
          f"{geometry.get('arc_radius_deviation_max_mm')} mm")
    if summary.get("pending"):
        print("pending: " + ", ".join(str(entry.get("item"))
                                      for entry in summary["pending"]))


def main(argv=None):
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(
        description=("Independent R15 acceptance wrapper for the 2026-10-20 "
                     "R=15 mm round (2D planes + 1024-channel combined + 2.5D)."),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--root", type=Path, default=None,
                        help="R15 experiment root (default: "
                             "outputs/four_side_1024_v2_r15_v01)")
    parser.add_argument("--out", type=Path, default=None,
                        help="output directory (default: <root>/validation)")
    parser.add_argument("--only", action="append", default=None,
                        help="only validate items whose key starts with / contains "
                             "this token, e.g. 2d, 2d/A, 2d/A/z1, 25d/A (repeatable)")
    parser.add_argument("--skip-combined", action="store_true",
                        help="do not expect the combined/V2/<label> 1024 layouts")
    parser.add_argument("--skip-25d", action="store_true",
                        help="do not expect the 25d/scheme<label>/layers5 runs")
    parser.add_argument("--no-port-csv", action="store_true",
                        help="skip V2 port/CSV identity checks")
    parser.add_argument("--skip-frozen", action="store_true",
                        help="only do the independent primitive scan (no frozen "
                             "strict 2D audit); debugging aid")
    parser.add_argument("--dump-summary", action="store_true",
                        help="print the aggregate summary JSON to stdout")
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root is not None else DEFAULT_ROOT
    out_dir = Path(args.out) if args.out is not None else root / "validation"
    print(f"R15 validation root: {root}")
    summary = validate_all(
        root, out_dir=out_dir, only=args.only,
        skip_combined=args.skip_combined, skip_25d=args.skip_25d,
        check_port_csv=not args.no_port_csv,
        run_frozen=not args.skip_frozen, write=True)
    _print_summary(summary)
    print(f"summary written {out_dir / 'r15_validation_summary.json'}")
    if args.dump_summary:
        print(json.dumps(summary, indent=1, ensure_ascii=False, default=str))
    if not summary.get("items"):
        return 2
    return 0 if all(item.get("passed") for item in summary["items"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
