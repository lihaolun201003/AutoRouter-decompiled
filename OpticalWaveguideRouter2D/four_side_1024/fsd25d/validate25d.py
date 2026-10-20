"""Independent 3D validator for the five-layer (2.5D) experiment.

The validator re-derives every geometric predicate from the delivered
``routes_25d.json`` files and never imports the router's own geometry or
clearance code: ``fsd25d.router25d`` / ``fsd25d.world25d`` / ``fsd25d.path3d``
are forbidden (``four_side_1024/fsd25d/SCHEMA_25D.md`` section 5).  Only the
frozen upstream modules are reused:

* ``four_side_1024.fslw.validate_fslw.prepare_route`` /
  ``audit_route_pairs(policy='strict')`` for the per-layer strict 2D pair audit
  (SCHEMA section 4.6) - this also supplies the "actual spatial crossings" count
  and validates the same-layer flat/flat clearance;
* ``four_side_1024.fslw.ports.load_plane('V2', plane)`` for the V2 port / CSV
  identity (SCHEMA section 4.2);
* ``four_side_1024.fslw.config`` and ``fsd25d.config25d`` for the process
  constants.

Checks implemented (SCHEMA_25D.md section 4):

1. structure / continuity of every routed record (``parts`` non-empty, adjacent
   parts and primitives joined in 3D within 1e-6, ``mode`` / ``n_transitions``
   pattern flat / flat-transition-flat-transition-flat, flat part height equals
   the layer stack, declared lengths consistent with the rebuilt geometry);
2. ports: 3D start/end height, XY start/end equals ``port.p`` / ``port.q``,
   start/end tangents equal ``port.start_tangent`` / ``port.end_tangent`` and are
   horizontal, plus port identity against the V2 dual-height CSV port model;
3. XY geometry model: scheme B only axis-aligned lines and exactly 90 deg R=40
   arcs; scheme A the three D56 primitives (orthogonal lines, R=40 arcs and
   valid short-S arc pairs); transition directions axis aligned;
4. curvature: full 3D path rebuilt independently (own S-curve reconstruction
   from ``theta = acos(1 - |dz| / (2R))``, see SCHEMA section 3) and sampled at
   <= 0.02 mm; minimum sampled 3D circumradius must be >= 40 mm (tolerance
   0.1 %, i.e. >= 39.96); analytic checks of every transition formula, every
   flat arc radius and every flat line (zero curvature by construction);
5. true 3D clearance between different routes: flat/flat pairs on the same layer
   are covered by the frozen strict 2D audit (same rule as SCHEMA section 4.5);
   every pair that involves a transition, and flat/flat pairs on different
   layers, are checked with fine 3D polylines (0.02 mm on transitions,
   0.05 mm on flats) plus exact segment/segment refinement, so a sampled
   threshold can never hide a violation.  Legal same-layer 2D crossings are
   therefore exempt only inside the frozen strict windows, which is stricter
   than the +/- 2.5 mm allowance of the schema;
6. per-layer strict 2D audit via the frozen validator (violations must be
   empty) - no 2D pass is ever taken as a 3D pass;
7. board margins: every 3D sample must keep >= half the waveguide width
   (0.025 mm) from the board edge except within 0.5 mm of a route port;
8. self clearance: non-adjacent parts of the same route (3D path parameter
   difference > 1 mm) must keep >= 0.08 mm in true 3D.

Command line::

    .venv\\Scripts\\python.exe -m four_side_1024.fsd25d.validate25d \\
        [--root outputs/four_side_1024_v2_25d_v01] [--only schemeA/layers5]

Outputs (default ``<root>/validation/``)::

    <root>/validation/<scheme>/layers<N>.json   one report per input directory
    <root>/validation/all_validation.json      aggregate of all runs

Numerical tolerances: continuity/pose predicates use 1e-6 mm, the curvature
threshold is the schema's 39.96 mm, the 3D clearance inequality allows the same
1e-7 mm swath as the authoritative frozen strict 2D policy (``clearance - 1e-7``)
and the board margin check absorbs IEEE-754 round-off (1e-9 mm) so geometry that
is intentionally placed exactly on a limit is not failed by floating point.
Sampled clearance uses exact segment/segment refinement of the polylines, so a
0.02 mm transition step can never hide a violation; flat chords are at most
0.05 mm long and their sagitta error is below 8e-6 mm.

The ``_smoke`` debug sample can be validated with::

    python -m four_side_1024.fsd25d.validate25d \\
        --input outputs/four_side_1024_v2_25d_v01/_smoke/routes_25d.json

which writes ``<root>/validation/_smoke/B_layers5.json``.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from ..fslw import config as FSLW
from ..fslw import ports as FSLW_PORTS
from ..fslw import validate_fslw
from . import config25d as CFG

# ---------------------------------------------------------------------------
# Schemas / process constants (SCHEMA_25D.md)
# ---------------------------------------------------------------------------
SCHEMA_RUN = "four_side_1024_v2_25d_validation_v1"
SCHEMA_ALL = "four_side_1024_v2_25d_validation_all_v1"
SCHEMA_ROUTES = "four_side_1024_v2_25d_routes_v1"

BOARD_MM = float(FSLW.BOARD_MM)
WIDTH_MM = float(FSLW.WIDTH_MM)
HALF_WIDTH_MM = WIDTH_MM / 2.0
CLEARANCE_MM = float(FSLW.CLEARANCE_MM)          # 0.080 mm centreline clearance
RADIUS_MM = float(FSLW.RADIUS_MM)                # fixed 40 mm
QUARTER = math.pi / 2.0
MIN_CURVATURE_MM = RADIUS_MM * (1.0 - 1e-3)      # schema: >= 39.96 mm

#: positions closer than this count as "not crossing" for the 2D audit padding.
SAGITTA_MM = float(FSLW.SAGITTA_MM)

# Sampling steps (mm).  The schema requires <= 0.02 on transitions (curvature)
# and <= 0.05 on flats (clearance); we use exactly those values.
FLAT_STEP_MM = 0.05
TRANSITION_STEP_MM = 0.02
CURVATURE_STEP_MM = 0.02

#: True-3D candidate search radius.  A pair of polyline segments can only be
#: closer than CLEARANCE_MM if their midpoints are within
#: CLEARANCE_MM + (max flat half step) + (max transition half step) = 0.125 mm;
#: 0.16 mm leaves a comfortable safety margin.
QUERY_RADIUS_MM = 0.16

#: Same-route pairs with a 3D path parameter difference below this are exempt
#: from the self-clearance rule (SCHEMA section 4.8).
SELF_PATH_SEPARATION_MM = 1.0

#: Board margin and the port-face exemption (SCHEMA section 4.7).
BOARD_MARGIN_MM = HALF_WIDTH_MM                  # 0.025 mm centreline half width
PORT_FACE_EXEMPT_MM = 0.5

#: Numerical tolerances of the two inequality predicates.  ``CLEARANCE_TOL_MM``
#: mirrors the authoritative frozen strict 2D limit (``clearance - 1e-7``): a
#: distance that the frozen strict policy itself accepts as legal must not be
#: re-flagged as a 3D clearance violation.  ``BOARD_MARGIN_TOL_MM`` only absorbs
#: IEEE-754 round-off of geometry that is intentionally placed exactly on the
#: 0.025 mm board margin (e.g. an arc point written as 0.02499999999999858).
CLEARANCE_TOL_MM = 1e-7
BOARD_MARGIN_TOL_MM = 1e-9

# Tolerances.  Delivered primitives are written with full float precision; the
# record-level summary fields are rounded to 1e-6 so their tolerance must be
# looser than the integer continuity tolerances.
POS_TOL_MM = 1e-6
POSE_TOL = 1e-6
LAYER_Z_TOL = 1e-9
ORTHO_TOL = 1e-9
RADIUS_TOL = 1e-9
QUARTER_TOL = 1e-9
SWEEP_TOL = 1e-9
PARAM_TOL = 1e-6
LEN_FIELD_TOL = 1e-3
SCALAR_FIELD_TOL = 1e-9
ARC_ENDPOINT_TOL = 1e-6
TRANSITION_TOL = 1e-6

#: Boards and process numbers embedded in ``process`` must match these.
PROCESS_REFERENCE = {
    "board_mm": [BOARD_MM, BOARD_MM],
    "width_mm": WIDTH_MM,
    "edge_gap_mm": float(FSLW.EDGE_GAP_MM),
    "clearance_mm": CLEARANCE_MM,
    "radius_mm": RADIUS_MM,
    "min_cross_angle_deg": float(FSLW.MIN_CROSS_ANGLE_DEG),
    "crossing_policy": "strict",
}

#: Violation categories reported in the ``counts`` block (SCHEMA section 4).
COUNT_KEYS = (
    "violations",
    "structure_errors",
    "port_errors",
    "xy_model_errors",
    "curvature_violations",
    "clearance_violations",
    "layer_2d_violations",
    "self_clearance_violations",
    "board_violations",
)
VIOLATION_CATEGORIES = COUNT_KEYS[1:]

#: Expected V2 connectivity CSV identity (frozen upstream constant).
EXPECTED_CSV_SHA256 = FSLW_PORTS.EXPECTED_SHA256.get("V2")

#: Number of CSV connections of the V2 topology (1024 total, 512 per plane).
EXPECTED_ROUTE_COUNT = 1024

#: Definition strings embedded in the report so downstream tools cannot
#: misinterpret the two minimum-distance numbers.
MIN_DISTANCE_DEFINITION = (
    "minimum true-3D centreline distance between different routes over all "
    "approaches that are NOT legal same-layer strict-2D crossings; same-layer "
    "flat/flat pairs are audited by the frozen strict 2D policy, all "
    "transition-involved pairs are computed from the independently rebuilt 3D "
    "polylines with exact segment/segment refinement"
)


# ---------------------------------------------------------------------------
# Small numeric helpers
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


def _as_int(value, what):
    if isinstance(value, bool):
        raise _DataError(f"invalid_{what}")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise _DataError(f"invalid_{what}")
    if isinstance(value, float) and not value.is_integer():
        raise _DataError(f"invalid_{what}")
    return number


def _as_pair(value, what):
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


def _unit2(vector):
    norm = math.hypot(vector[0], vector[1])
    if norm <= 0.0:
        raise _DataError("zero_direction")
    return (vector[0] / norm, vector[1] / norm)


def _is_axis_aligned2(vector, tol=ORTHO_TOL):
    return abs(vector[0]) <= tol or abs(vector[1]) <= tol


def _round(value, digits=9):
    if value is None:
        return None
    return round(float(value), digits)


def _fmt(value, digits=6):
    return "n/a" if value is None else f"{value:.{digits}f}"


# ---------------------------------------------------------------------------
# Violation collector
# ---------------------------------------------------------------------------
class _Report:
    """Collects violations by category, with exact counters and capped storage."""

    def __init__(self, max_violations_per_category=200):
        self.counts = {key: 0 for key in VIOLATION_CATEGORIES}
        self.violations = []
        self.kind_counts = OrderedDict()
        self.max_violations = int(max_violations_per_category)
        self._stored = {key: 0 for key in VIOLATION_CATEGORIES}
        self.warnings = []

    def add(self, category, kind, detail=None, route_id=None, other_route=None,
            **extra):
        if category not in self.counts:
            raise KeyError(category)
        self.counts[category] += 1
        key = f"{category}:{kind}"
        self.kind_counts[key] = self.kind_counts.get(key, 0) + 1
        if self._stored[category] >= self.max_violations:
            return
        self._stored[category] += 1
        entry = {"kind": kind, "category": category}
        if route_id is not None:
            entry["route_id"] = route_id
        if other_route is not None:
            entry["other_route"] = other_route
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


# ---------------------------------------------------------------------------
# Independent 3D geometry model
# ---------------------------------------------------------------------------
class _FlatLine:
    """Axis-aligned (not enforced here) straight 2D primitive at one height."""

    kind = "line"
    __slots__ = ("p0", "p1", "length")

    def __init__(self, p0, p1):
        self.p0 = p0
        self.p1 = p1
        self.length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])


class _FlatArc:
    """Circular 2D arc at one height (center/radius/start_angle/sweep)."""

    kind = "arc"
    __slots__ = ("p0", "p1", "center", "radius", "start_angle", "sweep", "length")

    def __init__(self, p0, p1, center, radius, start_angle, sweep):
        self.p0 = p0
        self.p1 = p1
        self.center = center
        self.radius = radius
        self.start_angle = start_angle
        self.sweep = sweep
        self.length = abs(sweep) * radius

    def point(self, t):
        angle = self.start_angle + self.sweep * t
        return (self.center[0] + self.radius * math.cos(angle),
                self.center[1] + self.radius * math.sin(angle))

    def tangent(self, t):
        sign = 1.0 if self.sweep >= 0.0 else -1.0
        angle = self.start_angle + self.sweep * t
        return (-sign * math.sin(angle), sign * math.cos(angle))

    def samples2d(self, step):
        count = max(2, int(math.ceil(self.length / step)) + 1)
        angles = self.start_angle + self.sweep * np.linspace(0.0, 1.0, count)
        return np.column_stack([self.center[0] + self.radius * np.cos(angles),
                                self.center[1] + self.radius * np.sin(angles)])


def _flat_line_samples(prim, step):
    count = max(2, int(math.ceil(prim.length / step)) + 1)
    t = np.linspace(0.0, 1.0, count)
    return np.column_stack([prim.p0[0] + t * (prim.p1[0] - prim.p0[0]),
                            prim.p0[1] + t * (prim.p1[1] - prim.p0[1])])


def _flat_line_tangent(prim, _t):
    return ((prim.p1[0] - prim.p0[0]) / prim.length,
            (prim.p1[1] - prim.p0[1]) / prim.length)


def _primitive_samples2d(prim, step):
    if prim.kind == "line":
        return _flat_line_samples(prim, step)
    return prim.samples2d(step)


def _primitive_tangent(prim, t):
    if prim.kind == "line":
        return _flat_line_tangent(prim, t)
    return prim.tangent(t)


class _FlatPart:
    """One constant-height sub-chain of a route (``kind='flat'``)."""

    kind = "flat"
    __slots__ = ("index", "layer", "z_mm", "primitives", "length", "raw_primitives")

    def __init__(self, index, layer, z_mm, primitives, length, raw_primitives):
        self.index = index
        self.layer = layer
        self.z_mm = z_mm
        self.primitives = primitives
        self.length = length
        self.raw_primitives = raw_primitives

    @property
    def start_xyz(self):
        return (self.primitives[0].p0[0], self.primitives[0].p0[1], self.z_mm)

    @property
    def end_xyz(self):
        return (self.primitives[-1].p1[0], self.primitives[-1].p1[1], self.z_mm)

    def start_tangent3(self):
        tangent = _primitive_tangent(self.primitives[0], 0.0)
        return (tangent[0], tangent[1], 0.0)

    def end_tangent3(self):
        tangent = _primitive_tangent(self.primitives[-1], 1.0)
        return (tangent[0], tangent[1], 0.0)

    def samples(self, step):
        chunks = []
        previous = None
        for prim in self.primitives:
            points = _primitive_samples2d(prim, step)
            if previous is not None and len(points):
                if math.hypot(points[0, 0] - previous[0],
                              points[0, 1] - previous[1]) <= 1e-12:
                    points = points[1:]
            if len(points):
                chunks.append(points)
                previous = (float(points[-1, 0]), float(points[-1, 1]))
        if not chunks:
            return np.zeros((0, 3))
        xy = np.vstack(chunks)
        z = np.full((xy.shape[0], 1), float(self.z_mm))
        return np.hstack([xy, z])


class _TransitionPart:
    """One vertical-plane two-arc S-curve (``kind='transition'``).

    Independent reconstruction from the schema definition::

        theta      = acos(1 - |dz| / (2R))
        footprint  = 2 R sin(theta)
        length     = 2 R theta
        first arc  : u = R sin(phi), w = z0 + sign R (1 - cos(phi)),
                     phi in [0, theta]
        second arc : point reflection of the first arc about
                     M = (footprint/2, z0 + sign |dz| / 2), traversed backwards
        world      : (x, y) = start + direction * u, z = w

    ``theta``/``footprint``/``length`` are recomputed here from ``dz`` and
    ``radius``; the declared JSON values are only compared against them.
    """

    kind = "transition"
    __slots__ = ("index", "start", "end", "direction", "z0", "z1", "dz", "radius",
                 "theta", "footprint", "length", "declared_footprint",
                 "declared_length")

    def __init__(self, index, start, end, direction, z0, z1, dz, radius,
                 declared_footprint, declared_length):
        self.index = index
        self.start = start
        self.end = end
        self.direction = direction
        self.z0 = z0
        self.z1 = z1
        self.dz = dz
        self.radius = radius
        ratio = 1.0 - abs(dz) / (2.0 * radius)
        self.theta = math.acos(max(-1.0, min(1.0, ratio)))
        self.footprint = 2.0 * radius * math.sin(self.theta)
        self.length = 2.0 * radius * self.theta
        self.declared_footprint = declared_footprint
        self.declared_length = declared_length

    @property
    def _sign(self):
        return 1.0 if self.z1 >= self.z0 else -1.0

    @property
    def start_xyz(self):
        return (self.start[0], self.start[1], self.z0)

    @property
    def end_xyz(self):
        return (self.end[0], self.end[1], self.z1)

    def start_tangent3(self):
        return (self.direction[0], self.direction[1], 0.0)

    def end_tangent3(self):
        return (self.direction[0], self.direction[1], 0.0)

    def samples(self, step):
        count = max(2, int(math.ceil(self.length / step)) + 1)
        s = np.linspace(0.0, self.length, count)
        u = np.empty(count, dtype=float)
        w = np.empty(count, dtype=float)
        half = 0.5 * self.length
        first = s <= half + 1e-15
        sign = self._sign
        phi = s[first] / self.radius
        u[first] = self.radius * np.sin(phi)
        w[first] = self.z0 + sign * self.radius * (1.0 - np.cos(phi))
        phi = (self.length - s[~first]) / self.radius
        u[~first] = self.footprint - self.radius * np.sin(phi)
        middle_z = self.z0 + sign * abs(self.dz) / 2.0
        w[~first] = 2.0 * middle_z - (
            self.z0 + sign * self.radius * (1.0 - np.cos(phi)))
        x = self.start[0] + self.direction[0] * u
        y = self.start[1] + self.direction[1] * u
        return np.column_stack([x, y, w])


class _RouteGeom:
    """Parsed 3D geometry of one routed CSV connection."""

    __slots__ = ("route_id", "plane", "mode", "parts", "flat_parts",
                 "transitions", "length_3d", "flat_length", "transition_length",
                 "xy_length", "record")

    def __init__(self, route_id, plane, mode, parts, record):
        self.route_id = route_id
        self.plane = plane
        self.mode = mode
        self.parts = parts
        self.record = record
        self.flat_parts = [part for part in parts if part.kind == "flat"]
        self.transitions = [part for part in parts if part.kind == "transition"]
        self.length_3d = sum(part.length for part in parts)
        self.flat_length = sum(part.length for part in self.flat_parts)
        self.transition_length = sum(part.length for part in self.transitions)
        self.xy_length = self.flat_length + sum(
            part.footprint for part in self.transitions)

    @property
    def start_xyz(self):
        return self.parts[0].start_xyz

    @property
    def end_xyz(self):
        return self.parts[-1].end_xyz

    def start_tangent3(self):
        return self.parts[0].start_tangent3()

    def end_tangent3(self):
        return self.parts[-1].end_tangent3()

    def samples(self, step_flat=FLAT_STEP_MM, step_transition=TRANSITION_STEP_MM):
        """Dense 3D polyline of the whole route (independent reconstruction)."""
        chunks = []
        previous = None
        for part in self.parts:
            if part.kind == "flat":
                points = part.samples(step_flat)
            else:
                points = part.samples(step_transition)
            if previous is not None and len(points):
                if math.hypot(points[0, 0] - previous[0],
                              points[0, 1] - previous[1]) <= 1e-9:
                    points = points[1:]
            if len(points):
                chunks.append(points)
                previous = (float(points[-1, 0]), float(points[-1, 1]),
                            float(points[-1, 2]))
        if not chunks:
            return np.zeros((0, 3))
        return np.vstack(chunks)


# ---------------------------------------------------------------------------
# Vectorised 3D segment / curvature helpers
# ---------------------------------------------------------------------------
def _segments_from_polyline(points):
    """Return ``(a, b, midpoint)`` arrays of a 3D polyline (empty safe)."""
    if len(points) < 2:
        empty = np.zeros((0, 3))
        return empty, empty, empty
    a = points[:-1]
    b = points[1:]
    return a, b, 0.5 * (a + b)


def _segment_segment_closest(p1, q1, p2, q2):
    """Closest points between pairs of 3D segments (Ericson, clamped).

    Returns ``(distance, point_on_first, point_on_second, s, t)`` where ``s`` /
    ``t`` are the fractional positions on the two segments.  Vectorised over the
    first axis; the exact analytic solution is used outside the (numerically
    irrelevant here) parallel-degenerate case.
    """
    d1 = q1 - p1
    d2 = q2 - p2
    r = p1 - p2
    a = np.einsum("ij,ij->i", d1, d1)
    e = np.einsum("ij,ij->i", d2, d2)
    f = np.einsum("ij,ij->i", d2, r)
    c = np.einsum("ij,ij->i", d1, r)
    b = np.einsum("ij,ij->i", d1, d2)
    safe_a = np.where(a > 1e-24, a, 1.0)
    safe_e = np.where(e > 1e-24, e, 1.0)
    denom = a * e - b * b
    parallel = denom <= 1e-18 * safe_a * safe_e
    s_inner = np.where(parallel, 0.0,
                       (b * f - c * e) / np.where(parallel, 1.0, denom))
    s = np.clip(s_inner, 0.0, 1.0)
    t = (b * s + f) / safe_e
    negative = t < 0.0
    positive = t > 1.0
    s = np.where(negative, np.clip(-c / safe_a, 0.0, 1.0),
                 np.where(positive, np.clip((b - c) / safe_a, 0.0, 1.0), s))
    t = np.where(negative, 0.0, np.where(positive, 1.0, np.clip(t, 0.0, 1.0)))
    point_a = p1 + s[:, None] * d1
    point_b = p2 + t[:, None] * d2
    diff = point_a - point_b
    distance = np.sqrt(np.einsum("ij,ij->i", diff, diff))
    return distance, point_a, point_b, s, t


def _polyline_min_curvature(points):
    """Minimum sampled circumradius (mm) of a 3D polyline; ``inf`` if unknown.

    Uses the circumradius of every consecutive point triple, i.e. an
    independent discrete curvature estimate from the 3D sample positions
    (SCHEMA section 4.4).  Triples whose area is numerically zero (straight
    lines) are ignored instead of producing a spurious radius.
    """
    if len(points) < 3:
        return float("inf")
    a = points[:-2]
    b = points[1:-1]
    c = points[2:]
    ab = b - a
    ac = c - a
    cross = np.cross(ab, ac)
    double_area = np.linalg.norm(cross, axis=1)
    length_ab = np.linalg.norm(ab, axis=1)
    length_ac = np.linalg.norm(ac, axis=1)
    length_bc = np.linalg.norm(c - b, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        radius = length_ab * length_ac * length_bc / (2.0 * double_area)
    straight = double_area <= 1e-14
    if np.all(straight):
        return float("inf")
    return float(np.min(radius[~straight]))


# ---------------------------------------------------------------------------
# Payload-level contract (SCHEMA_25D.md section 2)
# ---------------------------------------------------------------------------
def _check_payload(payload, report, expected_scheme=None, expected_layers=None,
                   check_port_csv=True):
    """Validate the top-level contract; returns the parsing context."""
    if not isinstance(payload, dict):
        raise _DataError("payload_not_a_mapping")
    context = {
        "scheme": None,
        "n_layers": None,
        "layers_z": None,
        "interface_layer": None,
        "identity": None,
        "port_csv_checked": False,
    }
    schema = payload.get("schema")
    if schema != SCHEMA_ROUTES:
        report.add("structure_errors", "schema_mismatch",
                   detail=f"{schema!r} != {SCHEMA_ROUTES!r}")
    scheme = payload.get("scheme")
    if scheme not in CFG.SCHEMES:
        report.add("structure_errors", "scheme_invalid", detail=str(scheme))
    elif expected_scheme is not None and scheme != expected_scheme:
        report.add("structure_errors", "scheme_directory_mismatch",
                   detail=f"payload={scheme} directory={expected_scheme}")
    context["scheme"] = scheme if scheme in CFG.SCHEMES else None
    try:
        n_layers = _as_int(payload.get("n_layers"), "n_layers")
    except _DataError as exc:
        report.add("structure_errors", "n_layers_invalid", detail=str(exc))
        n_layers = None
    if n_layers is not None and n_layers not in CFG.LAYER_STACKS:
        report.add("structure_errors", "n_layers_invalid", detail=str(n_layers))
        n_layers = None
    if n_layers is not None and expected_layers is not None and n_layers != int(expected_layers):
        report.add("structure_errors", "n_layers_directory_mismatch",
                   detail=f"payload={n_layers} directory={expected_layers}")
    context["n_layers"] = n_layers
    if n_layers is not None:
        reference = [float(value) for value in CFG.stack(n_layers)]
        declared = payload.get("layers_z_mm")
        try:
            layers_z = [float(value) for value in declared]
        except (TypeError, ValueError):
            layers_z = None
        if layers_z is None or len(layers_z) != len(reference):
            report.add("structure_errors", "layers_z_invalid", detail=str(declared))
            layers_z = reference
        else:
            for index, (value, expected) in enumerate(zip(layers_z, reference)):
                if abs(value - expected) > LAYER_Z_TOL:
                    report.add("structure_errors", "layers_z_mismatch",
                               detail=f"layer {index}: {value} != {expected}")
        context["layers_z"] = layers_z
        interface_reference = dict(CFG.INTERFACE_LAYER[n_layers])
        declared_interface = payload.get("interface_layer")
        interface = {}
        if not isinstance(declared_interface, dict):
            report.add("structure_errors", "interface_layer_invalid",
                       detail=str(declared_interface))
        else:
            for plane in CFG.PLANES:
                try:
                    layer = _as_int(declared_interface.get(plane), f"interface_{plane}")
                except _DataError as exc:
                    report.add("structure_errors", "interface_layer_invalid",
                               detail=f"{plane}: {exc}")
                    layer = interface_reference[plane]
                if layer != interface_reference[plane]:
                    report.add("structure_errors", "interface_layer_mismatch",
                               detail=f"{plane}: {layer} != {interface_reference[plane]}")
                interface[plane] = layer
        if not interface:
            interface = dict(interface_reference)
        context["interface_layer"] = interface
    process = payload.get("process")
    if not isinstance(process, dict):
        report.add("structure_errors", "process_missing", detail=str(process))
    else:
        for key, expected in PROCESS_REFERENCE.items():
            if key not in process:
                report.add("structure_errors", "process_missing_field", detail=key)
                continue
            value = process[key]
            if isinstance(expected, list):
                try:
                    matched = len(value) == len(expected) and all(
                        abs(float(item) - expected[index]) <= SCALAR_FIELD_TOL
                        for index, item in enumerate(value))
                except (TypeError, ValueError):
                    matched = False
            elif isinstance(expected, str):
                matched = str(value) == expected
            else:
                try:
                    matched = abs(float(value) - expected) <= SCALAR_FIELD_TOL
                except (TypeError, ValueError):
                    matched = False
            if not matched:
                report.add("structure_errors", "process_field_mismatch",
                           detail=f"{key}: {value!r} != {expected!r}")
    csv_sha = payload.get("csv_sha256")
    if EXPECTED_CSV_SHA256 is not None:
        if str(csv_sha).lower() != EXPECTED_CSV_SHA256.lower():
            report.add("port_errors", "csv_sha256_mismatch",
                       detail=f"{csv_sha!r} != {EXPECTED_CSV_SHA256!r}")
    routes = payload.get("routes")
    if not isinstance(routes, list):
        raise _DataError("routes_not_a_list")
    if len(routes) != EXPECTED_ROUTE_COUNT:
        report.add("structure_errors", "route_count_mismatch",
                   detail=f"{len(routes)} != {EXPECTED_ROUTE_COUNT}")
    if check_port_csv:
        context["identity"] = _load_v2_identity(report)
        context["port_csv_checked"] = context["identity"] is not None
    return context


def _load_v2_identity(report):
    """Load the frozen V2 port model (route id -> plane/endpoints/ports).

    Returns ``None`` (with a warning, not a violation) when the V2 connectivity
    CSV cannot be read in this environment; the geometric checks do not depend
    on it.
    """
    try:
        routes = {}
        endpoints = {}
        for plane in CFG.PLANES:
            plane_routes, plane_endpoints, _connectors, _validation = (
                FSLW_PORTS.load_plane("V2", plane))
            for record in plane_routes:
                routes[int(record["route_id"])] = {
                    "plane": plane,
                    "pair": record.get("pair"),
                    "relation": record.get("relation"),
                    "source_endpoint": record.get("source_endpoint"),
                    "target_endpoint": record.get("target_endpoint"),
                }
            endpoints.update(plane_endpoints)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report.warn(f"V2 port CSV not available, port identity checks skipped: "
                    f"{type(exc).__name__}: {exc}")
        return None
    if len(routes) != EXPECTED_ROUTE_COUNT:
        report.add("port_errors", "port_csv_route_count",
                   detail=f"{len(routes)} != {EXPECTED_ROUTE_COUNT}")
    return {"routes": routes, "endpoints": endpoints}


# ---------------------------------------------------------------------------
# Route parsing + structure / geometry-model checks
# ---------------------------------------------------------------------------
def _parse_flat_primitive(raw, part_index, primitive_index, scheme, report,
                          route_id):
    """Parse one flat primitive and run the per-primitive geometry checks."""
    if not isinstance(raw, dict):
        raise _DataError("primitive_not_a_mapping")
    kind = raw.get("kind")
    p0 = _as_pair(raw.get("p0"), "p0")
    p1 = _as_pair(raw.get("p1"), "p1")
    where = f"part={part_index} primitive={primitive_index}"
    if kind == "line":
        length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if length <= POS_TOL_MM:
            raise _DataError(f"zero_length_line:{where}")
        if not (abs(p1[0] - p0[0]) <= ORTHO_TOL or abs(p1[1] - p0[1]) <= ORTHO_TOL):
            report.add("xy_model_errors", "diagonal_line", route_id=route_id,
                       detail=where)
        return _FlatLine(p0, p1)
    if kind != "arc":
        report.add("xy_model_errors", "unknown_primitive_kind", route_id=route_id,
                   detail=f"{where} kind={kind!r}")
        raise _DataError(f"unknown_primitive_kind:{where}")
    center = _as_pair(raw.get("center"), "center")
    radius = _as_float(raw.get("radius"), "radius")
    start_angle = _as_float(raw.get("start_angle"), "start_angle")
    sweep = _as_float(raw.get("sweep"), "sweep")
    if radius <= POS_TOL_MM:
        raise _DataError(f"nonpositive_radius:{where}")
    if abs(sweep) <= SWEEP_TOL or abs(sweep) > 2.0 * math.pi + SWEEP_TOL:
        raise _DataError(f"invalid_sweep:{where}")
    primitive = _FlatArc(p0, p1, center, radius, start_angle, sweep)
    # analytic endpoint consistency of the arc description
    for name, angle, endpoint in (("p0", start_angle, p0),
                                  ("p1", start_angle + sweep, p1)):
        reconstructed = (center[0] + radius * math.cos(angle),
                         center[1] + radius * math.sin(angle))
        if math.hypot(reconstructed[0] - endpoint[0],
                      reconstructed[1] - endpoint[1]) > ARC_ENDPOINT_TOL:
            report.add("structure_errors", "arc_endpoint_inconsistent",
                       route_id=route_id, detail=f"{where} {name}")
    # curvature: every flat arc must be an R=40 mm circular arc (SCHEMA 4.4)
    if abs(radius - RADIUS_MM) > RADIUS_TOL:
        report.add("curvature_violations", "flat_arc_radius", route_id=route_id,
                   detail=f"{where} radius={radius!r} != {RADIUS_MM}")
    # XY model per scheme (SCHEMA 4.3)
    if scheme == "B":
        if abs(abs(sweep) - QUARTER) > QUARTER_TOL:
            report.add("xy_model_errors", "non_90_arc", route_id=route_id,
                       detail=f"{where} sweep={math.degrees(sweep):.9f} deg")
    return primitive


def _short_s_pair_ok(first, second):
    """``True`` when two adjacent arcs form a legal D56 short-S pair.

    Same construction as the frozen 2D validator: two R=40 arcs with sweeps
    ``+theta`` / ``-theta`` and no straight between them, lateral displacement
    ``2R(1-cos theta)`` and longitudinal advance ``2R sin theta``.
    """
    theta = abs(first.sweep)
    if not (SWEEP_TOL < theta < QUARTER - SWEEP_TOL):
        return False
    if abs(abs(second.sweep) - theta) > PARAM_TOL:
        return False
    if first.sweep * second.sweep >= 0.0:
        return False
    tangent = first.tangent(0.0)
    delta = (second.p1[0] - first.p0[0], second.p1[1] - first.p0[1])
    longitudinal = tangent[0] * delta[0] + tangent[1] * delta[1]
    lateral = abs(tangent[0] * delta[1] - tangent[1] * delta[0])
    expected_lateral = 2.0 * first.radius * (1.0 - math.cos(theta))
    expected_longitudinal = 2.0 * first.radius * math.sin(theta)
    return (abs(lateral - expected_lateral) <= PARAM_TOL
            and abs(longitudinal - expected_longitudinal) <= PARAM_TOL)


def _check_arc_family(primitives, part_index, report, route_id):
    """Scheme A: every non-quarter arc must belong to a valid short-S pair."""
    index = 0
    count = len(primitives)
    while index < count:
        primitive = primitives[index]
        if (primitive.kind != "arc"
                or abs(abs(primitive.sweep) - QUARTER) <= QUARTER_TOL):
            index += 1
            continue
        other = index + 1
        gap = 0.0
        while other < count and primitives[other].kind == "line":
            gap += primitives[other].length
            other += 1
        if (other < count and primitives[other].kind == "arc"
                and gap <= POSE_TOL
                and _short_s_pair_ok(primitive, primitives[other])):
            index = other + 1
            continue
        report.add("xy_model_errors", "short_s_invalid", route_id=route_id,
                   detail=f"part={part_index} primitive={index} "
                          f"sweep={math.degrees(primitive.sweep):.9f} deg")
        index += 1


def _parse_flat_part(raw, part_index, context, report, route_id):
    """Parse one ``flat`` part (structure + scheme geometry model checks)."""
    if not isinstance(raw, dict):
        raise _DataError("part_not_a_mapping")
    layers_z = context["layers_z"]
    layer = _as_int(raw.get("layer"), "layer")
    if layers_z is not None and not 0 <= layer < len(layers_z):
        report.add("structure_errors", "flat_layer_out_of_range", route_id=route_id,
                   detail=f"part={part_index} layer={layer}")
    z_mm = _as_float(raw.get("z_mm"), "z_mm")
    if layers_z is not None and 0 <= layer < len(layers_z):
        if abs(z_mm - layers_z[layer]) > LAYER_Z_TOL:
            report.add("structure_errors", "flat_z_mismatch", route_id=route_id,
                       detail=f"part={part_index} z={z_mm} layer_z={layers_z[layer]}")
    raw_primitives = raw.get("primitives")
    if not isinstance(raw_primitives, list) or not raw_primitives:
        report.add("structure_errors", "flat_part_empty", route_id=route_id,
                   detail=f"part={part_index}")
        raise _DataError(f"flat_part_empty:part={part_index}")
    primitives = []
    for primitive_index, primitive_raw in enumerate(raw_primitives):
        primitives.append(_parse_flat_primitive(
            primitive_raw, part_index, primitive_index, context["scheme"],
            report, route_id))
    # internal continuity of the primitive chain
    for index in range(1, len(primitives)):
        previous = primitives[index - 1]
        current = primitives[index]
        if math.hypot(previous.p1[0] - current.p0[0],
                      previous.p1[1] - current.p0[1]) > POS_TOL_MM:
            report.add("structure_errors", "primitive_discontinuity",
                       route_id=route_id, detail=f"part={part_index} joint={index}")
    length = sum(primitive.length for primitive in primitives)
    declared = raw.get("length_mm")
    if declared is None:
        report.add("structure_errors", "flat_part_length_missing",
                   route_id=route_id, detail=f"part={part_index}")
    else:
        try:
            declared_length = float(declared)
        except (TypeError, ValueError):
            declared_length = None
        if (declared_length is None
                or abs(declared_length - length) > LEN_FIELD_TOL):
            report.add("structure_errors", "flat_part_length_mismatch",
                       route_id=route_id,
                       detail=f"part={part_index} {declared!r} != {_round(length)}")
    part = _FlatPart(part_index, layer, z_mm, primitives, length, raw_primitives)
    if context["scheme"] == "A":
        _check_arc_family(primitives, part_index, report, route_id)
    return part


def _parse_transition_part(raw, part_index, context, report, route_id):
    """Parse one ``transition`` part and check every analytic S-curve formula."""
    if not isinstance(raw, dict):
        raise _DataError("part_not_a_mapping")
    layers_z = context["layers_z"]
    start = _as_pair(raw.get("start"), "start")
    end = _as_pair(raw.get("end"), "end")
    direction = _as_pair(raw.get("direction"), "direction")
    z0 = _as_float(raw.get("z0_mm"), "z0_mm")
    z1 = _as_float(raw.get("z1_mm"), "z1_mm")
    dz = _as_float(raw.get("dz_mm"), "dz_mm")
    radius = _as_float(raw.get("radius_mm"), "radius_mm")
    declared_footprint = _as_float(raw.get("footprint_mm"), "footprint_mm")
    declared_length = _as_float(raw.get("length_mm"), "length_mm")
    detail = f"part={part_index}"
    norm = math.hypot(direction[0], direction[1])
    if abs(norm - 1.0) > POSE_TOL:
        report.add("structure_errors", "transition_direction_not_unit",
                   route_id=route_id, detail=f"{detail} |direction|={norm}")
        direction = _unit2(direction)
    if not _is_axis_aligned2(direction):
        report.add("xy_model_errors", "transition_direction_not_axis_aligned",
                   route_id=route_id, detail=f"{detail} direction={direction!r}")
    if abs(radius - RADIUS_MM) > RADIUS_TOL:
        report.add("curvature_violations", "transition_radius", route_id=route_id,
                   detail=f"{detail} radius={radius!r}")
    if abs(dz - (z1 - z0)) > TRANSITION_TOL or abs(dz) <= TRANSITION_TOL:
        report.add("structure_errors", "transition_dz_mismatch", route_id=route_id,
                   detail=f"{detail} dz={dz!r} z1-z0={z1 - z0!r}")
    part = _TransitionPart(part_index, start, end, direction, z0, z1, dz, radius,
                           declared_footprint, declared_length)
    # analytic S-curve formula checks (SCHEMA 3 / 4.4)
    if abs(part.footprint - declared_footprint) > TRANSITION_TOL:
        report.add("curvature_violations", "transition_footprint_mismatch",
                   route_id=route_id,
                   detail=f"{detail} declared={declared_footprint!r} "
                          f"rebuilt={_round(part.footprint)}")
    if abs(part.length - declared_length) > TRANSITION_TOL:
        report.add("curvature_violations", "transition_length_mismatch",
                   route_id=route_id,
                   detail=f"{detail} declared={declared_length!r} "
                          f"rebuilt={_round(part.length)}")
    expected_end = (start[0] + direction[0] * part.footprint,
                    start[1] + direction[1] * part.footprint)
    if math.hypot(expected_end[0] - end[0], expected_end[1] - end[1]) > TRANSITION_TOL:
        report.add("structure_errors", "transition_end_mismatch",
                   route_id=route_id, detail=f"{detail} end={end!r}")
    if layers_z is not None:
        for value in (z0, z1):
            if min(abs(value - layer_z) for layer_z in layers_z) > LAYER_Z_TOL:
                report.add("structure_errors", "transition_z_off_stack",
                           route_id=route_id, detail=f"{detail} z={value}")
    return part


def _parse_route(record, context, report):
    """Parse one routed record into a :class:`_RouteGeom` (structure checks)."""
    route_id = _as_int(record.get("route_id"), "route_id")
    plane = record.get("plane")
    if plane not in CFG.PLANES:
        raise _DataError(f"invalid_plane:{plane!r}")
    if context["n_layers"] is None or context["layers_z"] is None:
        raise _DataError("payload_layers_unknown")
    interface_layer = context["interface_layer"][plane]
    interface_z = context["layers_z"][interface_layer]
    # record interface metadata vs the layer stack
    try:
        declared_layer = _as_int(record.get("interface_layer"), "interface_layer")
    except _DataError:
        declared_layer = None
    try:
        declared_z = _as_float(record.get("interface_z_mm"), "interface_z_mm")
    except _DataError:
        declared_z = None
    if declared_layer is not None and declared_layer != interface_layer:
        report.add("structure_errors", "route_interface_layer_mismatch",
                   route_id=route_id,
                   detail=f"{declared_layer} != {interface_layer}")
    if declared_z is not None and abs(declared_z - interface_z) > LAYER_Z_TOL:
        report.add("structure_errors", "route_interface_z_mismatch",
                   route_id=route_id, detail=f"{declared_z} != {interface_z}")
    mode = record.get("mode")
    if mode not in ("flat", "lifted"):
        report.add("structure_errors", "route_mode_invalid", route_id=route_id,
                   detail=str(mode))
    raw_parts = record.get("parts")
    if not isinstance(raw_parts, list) or not raw_parts:
        report.add("structure_errors", "route_parts_empty", route_id=route_id)
        raise _DataError(f"route_parts_empty:{route_id}")
    parts = []
    for part_index, raw_part in enumerate(raw_parts):
        if not isinstance(raw_part, dict):
            raise _DataError(f"part_not_a_mapping:{part_index}")
        kind = raw_part.get("kind")
        if kind == "flat":
            parts.append(_parse_flat_part(raw_part, part_index, context, report,
                                          route_id))
        elif kind == "transition":
            parts.append(_parse_transition_part(raw_part, part_index, context,
                                                report, route_id))
        else:
            report.add("structure_errors", "unknown_part_kind", route_id=route_id,
                       detail=f"part={part_index} kind={kind!r}")
            raise _DataError(f"unknown_part_kind:{kind!r}")
    # mode / part-pattern consistency (SCHEMA 4.1)
    kinds = [part.kind for part in parts]
    declared_transitions = record.get("n_transitions")
    try:
        declared_transitions = _as_int(declared_transitions, "n_transitions")
    except _DataError:
        declared_transitions = None
    actual_transitions = sum(1 for kind in kinds if kind == "transition")
    if declared_transitions is not None and declared_transitions != actual_transitions:
        report.add("structure_errors", "n_transitions_mismatch",
                   route_id=route_id,
                   detail=f"{declared_transitions} != {actual_transitions}")
    lifted_field = record.get("lifted")
    if mode == "flat":
        if kinds != ["flat"] * len(kinds) or actual_transitions != 0:
            report.add("structure_errors", "flat_mode_has_transition",
                       route_id=route_id, detail=str(kinds))
        if lifted_field is not None and bool(lifted_field):
            report.add("structure_errors", "flat_mode_lifted_flag",
                       route_id=route_id)
        if declared_transitions not in (None, 0):
            report.add("structure_errors", "flat_mode_n_transitions",
                       route_id=route_id, detail=str(declared_transitions))
    elif mode == "lifted":
        if kinds != ["flat", "transition", "flat", "transition", "flat"]:
            report.add("structure_errors", "lifted_part_pattern", route_id=route_id,
                       detail=str(kinds))
        if declared_transitions not in (None, 2):
            report.add("structure_errors", "lifted_n_transitions", route_id=route_id,
                       detail=str(declared_transitions))
        if lifted_field is not None and not bool(lifted_field):
            report.add("structure_errors", "lifted_mode_flat_flag",
                       route_id=route_id)
        travel_layer = record.get("travel_layer")
        travel_z = record.get("travel_z_mm")
        try:
            travel_layer = _as_int(travel_layer, "travel_layer")
        except _DataError:
            travel_layer = None
            report.add("structure_errors", "travel_layer_invalid", route_id=route_id,
                       detail=str(record.get("travel_layer")))
        try:
            travel_z = _as_float(travel_z, "travel_z_mm")
        except _DataError:
            travel_z = None
            report.add("structure_errors", "travel_z_invalid", route_id=route_id,
                       detail=str(record.get("travel_z_mm")))
        layers_z = context["layers_z"]
        if travel_layer is not None and not 0 <= travel_layer < len(layers_z):
            report.add("structure_errors", "travel_layer_out_of_range",
                       route_id=route_id, detail=str(travel_layer))
        elif travel_layer is not None:
            if travel_layer == interface_layer:
                report.add("structure_errors", "travel_layer_is_interface",
                           route_id=route_id, detail=str(travel_layer))
            if travel_z is not None and abs(travel_z - layers_z[travel_layer]) > LAYER_Z_TOL:
                report.add("structure_errors", "travel_z_mismatch", route_id=route_id,
                           detail=f"{travel_z} != {layers_z[travel_layer]}")
            if len(parts) == 5 and parts[2].kind == "flat":
                if parts[2].layer != travel_layer:
                    report.add("structure_errors", "travel_flat_layer_mismatch",
                               route_id=route_id,
                               detail=f"{parts[2].layer} != {travel_layer}")
    # 3D continuity between adjacent parts (SCHEMA 4.1)
    for index in range(1, len(parts)):
        previous = parts[index - 1].end_xyz
        current = parts[index].start_xyz
        distance = math.dist(previous, current)
        if distance > POS_TOL_MM:
            report.add("structure_errors", "part_discontinuity", route_id=route_id,
                       detail=f"joint={index} distance={distance:.9g}")
    geom = _RouteGeom(route_id, plane, mode if mode in ("flat", "lifted") else None,
                      parts, record)
    _check_record_fields(geom, record, report, interface_layer, interface_z,
                         context["layers_z"])
    return geom


def _check_record_fields(geom, record, report, interface_layer, interface_z,
                         layers_z):
    """Route-level summary fields must match the rebuilt geometry."""
    route_id = geom.route_id
    z_span = 0.0
    if geom.mode != "flat":
        z_span = _travel_span(record, layers_z)
    expected = {
        "length_mm": (geom.length_3d, LEN_FIELD_TOL),
        "xy_length_mm": (geom.xy_length, LEN_FIELD_TOL),
        "flat_length_mm": (geom.flat_length, LEN_FIELD_TOL),
        "transition_length_mm": (geom.transition_length, LEN_FIELD_TOL),
        "z_span_mm": (z_span, LEN_FIELD_TOL),
    }
    for field, (computed, tolerance) in expected.items():
        declared = record.get(field)
        if declared is None:
            report.add("structure_errors", "record_field_missing",
                       route_id=route_id, detail=field)
            continue
        try:
            declared_value = float(declared)
        except (TypeError, ValueError):
            report.add("structure_errors", "record_field_invalid",
                       route_id=route_id, detail=f"{field}={declared!r}")
            continue
        if computed is not None and abs(declared_value - computed) > tolerance:
            report.add("structure_errors", "record_field_mismatch",
                       route_id=route_id,
                       detail=f"{field}: {declared_value} != {_round(float(computed))}")


def _travel_span(record, layers_z):
    travel_layer = record.get("travel_layer")
    try:
        return abs(layers_z[int(travel_layer)] - layers_z[int(record["interface_layer"])])
    except (TypeError, ValueError, KeyError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Port checks (SCHEMA 4.2) incl. the frozen V2 port identity
# ---------------------------------------------------------------------------
def _check_ports(geom, record, context, report):
    """Port height / XY / tangent checks against ``port`` and the V2 CSV model."""
    route_id = geom.route_id
    plane = geom.plane
    interface_layer = context["interface_layer"][plane]
    interface_z = context["layers_z"][interface_layer]
    port = record.get("port")
    if not isinstance(port, dict):
        report.add("port_errors", "port_missing", route_id=route_id)
        return
    try:
        p = _as_pair(port.get("p"), "port_p")
        q = _as_pair(port.get("q"), "port_q")
        start_tangent = _as_pair(port.get("start_tangent"), "start_tangent")
        end_tangent = _as_pair(port.get("end_tangent"), "end_tangent")
    except _DataError as exc:
        report.add("port_errors", "port_invalid", route_id=route_id, detail=str(exc))
        return
    start = geom.start_xyz
    end = geom.end_xyz
    if math.hypot(start[0] - p[0], start[1] - p[1]) > POSE_TOL:
        report.add("port_errors", "start_xy_mismatch", route_id=route_id,
                   detail=f"({start[0]:.12g},{start[1]:.12g}) vs {p}")
    if math.hypot(end[0] - q[0], end[1] - q[1]) > POSE_TOL:
        report.add("port_errors", "end_xy_mismatch", route_id=route_id,
                   detail=f"({end[0]:.12g},{end[1]:.12g}) vs {q}")
    if abs(start[2] - interface_z) > LAYER_Z_TOL:
        report.add("port_errors", "start_height_mismatch", route_id=route_id,
                   detail=f"z={start[2]!r} != {interface_z!r}")
    if abs(end[2] - interface_z) > LAYER_Z_TOL:
        report.add("port_errors", "end_height_mismatch", route_id=route_id,
                   detail=f"z={end[2]!r} != {interface_z!r}")
    for name, tangent in (("start_tangent", start_tangent),
                          ("end_tangent", end_tangent)):
        norm = math.hypot(tangent[0], tangent[1])
        if abs(norm - 1.0) > POSE_TOL:
            report.add("port_errors", "port_tangent_not_unit", route_id=route_id,
                       detail=f"{name} |t|={norm}")
    geometry_tangent = geom.start_tangent3()
    if abs(geometry_tangent[2]) > LAYER_Z_TOL:
        report.add("port_errors", "start_tangent_not_horizontal",
                   route_id=route_id, detail=str(geometry_tangent))
    if math.hypot(geometry_tangent[0] - start_tangent[0],
                  geometry_tangent[1] - start_tangent[1]) > POSE_TOL:
        report.add("port_errors", "start_tangent_mismatch", route_id=route_id,
                   detail=f"({geometry_tangent[0]:.12g},{geometry_tangent[1]:.12g})"
                          f" vs {start_tangent}")
    geometry_tangent = geom.end_tangent3()
    if abs(geometry_tangent[2]) > LAYER_Z_TOL:
        report.add("port_errors", "end_tangent_not_horizontal",
                   route_id=route_id, detail=str(geometry_tangent))
    if math.hypot(geometry_tangent[0] - end_tangent[0],
                  geometry_tangent[1] - end_tangent[1]) > POSE_TOL:
        report.add("port_errors", "end_tangent_mismatch", route_id=route_id,
                   detail=f"({geometry_tangent[0]:.12g},{geometry_tangent[1]:.12g})"
                          f" vs {end_tangent}")

    identity = context.get("identity")
    if identity is None:
        return
    info = identity["routes"].get(route_id)
    if info is None:
        report.add("port_errors", "route_id_not_in_v2_csv", route_id=route_id)
        return
    if info["plane"] != plane:
        report.add("port_errors", "plane_mismatch_v2_csv", route_id=route_id,
                   detail=f"{plane} != {info['plane']}")
    if record.get("pair") != info["pair"]:
        report.add("port_errors", "pair_mismatch_v2_csv", route_id=route_id,
                   detail=f"{record.get('pair')!r} != {info['pair']!r}")
    if record.get("relation") != info["relation"]:
        report.add("port_errors", "relation_mismatch_v2_csv", route_id=route_id,
                   detail=f"{record.get('relation')!r} != {info['relation']!r}")
    endpoints = identity["endpoints"]
    source = endpoints.get(info["source_endpoint"])
    target = endpoints.get(info["target_endpoint"])
    if source is None or target is None:
        report.add("port_errors", "v2_endpoint_missing", route_id=route_id)
        return
    source_xy = source["routing_xy"]
    target_xy = target["routing_xy"]
    if math.hypot(p[0] - source_xy[0], p[1] - source_xy[1]) > POSE_TOL:
        report.add("port_errors", "start_port_identity", route_id=route_id,
                   detail=f"p={p} source={source_xy}")
    if math.hypot(q[0] - target_xy[0], q[1] - target_xy[1]) > POSE_TOL:
        report.add("port_errors", "end_port_identity", route_id=route_id,
                   detail=f"q={q} target={target_xy}")
    expected_start = source["inward"]
    expected_end = (-target["inward"][0], -target["inward"][1])
    if math.hypot(start_tangent[0] - expected_start[0],
                  start_tangent[1] - expected_start[1]) > POSE_TOL:
        report.add("port_errors", "start_tangent_identity", route_id=route_id,
                   detail=f"{start_tangent} vs {expected_start}")
    if math.hypot(end_tangent[0] - expected_end[0],
                  end_tangent[1] - expected_end[1]) > POSE_TOL:
        report.add("port_errors", "end_tangent_identity", route_id=route_id,
                   detail=f"{end_tangent} vs {expected_end}")


def _check_port_usage(geoms, identity, report):
    """Every V2 port identity may be used by at most one routed connection."""
    if identity is None:
        return
    endpoints = identity["endpoints"]
    usage = {}
    for geom in geoms:
        info = identity["routes"].get(geom.route_id)
        if info is None:
            continue
        for role in ("source_endpoint", "target_endpoint"):
            identity_key = info[role]
            usage[identity_key] = usage.get(identity_key, 0) + 1
            if identity_key not in endpoints:
                report.add("port_errors", "v2_endpoint_missing",
                           route_id=geom.route_id, detail=str(identity_key))
    for identity_key, count in usage.items():
        if count > 1:
            report.add("port_errors", "duplicate_port_use",
                       detail=f"{identity_key} used {count} times")


# ---------------------------------------------------------------------------
# Curvature / board / self-clearance audits
# ---------------------------------------------------------------------------
def _audit_curvature(geom, context, report):
    """Independent sampled 3D curvature estimate of the complete route path."""
    points = geom.samples(CURVATURE_STEP_MM, CURVATURE_STEP_MM)
    min_radius = _polyline_min_curvature(points)
    if min_radius < MIN_CURVATURE_MM:
        report.add("curvature_violations", "min_3d_radius_below_40mm",
                   route_id=geom.route_id,
                   detail=f"min sampled radius {_fmt(min_radius)} mm "
                          f"< {MIN_CURVATURE_MM:.3f}")
    return min_radius


def _audit_board_margin(geom, gap_points, report):
    """Every 3D sample must keep >= 0.025 mm from the board edge, ports exempt."""
    if len(gap_points) == 0:
        return float("inf")
    x = gap_points[:, 0]
    y = gap_points[:, 1]
    edge = np.minimum(np.minimum(x, y),
                      np.minimum(BOARD_MM - x, BOARD_MM - y))
    port = geom.record.get("port") or {}
    exempt = np.zeros(len(gap_points), dtype=bool)
    for key in ("p", "q"):
        try:
            port_xy = _as_pair(port.get(key), f"port_{key}")
        except _DataError:
            continue
        distance = np.hypot(x - port_xy[0], y - port_xy[1])
        exempt |= distance <= PORT_FACE_EXEMPT_MM
    keep = ~exempt
    if not np.any(keep):
        return float("inf")
    kept = edge[keep]
    minimum = float(np.min(kept))
    limit = BOARD_MARGIN_MM - BOARD_MARGIN_TOL_MM
    if minimum < limit:
        bad = int(np.count_nonzero(kept < limit))
        for index in np.flatnonzero(keep & (edge < limit))[:5]:
            report.add("board_violations", "board_edge_clearance",
                       route_id=geom.route_id,
                       detail=f"xy=({x[index]:.9g},{y[index]:.9g}) "
                              f"z={gap_points[index, 2]:.9g} edge={edge[index]:.9g}")
        if bad > 5:
            report.add("board_violations", "board_edge_clearance",
                       route_id=geom.route_id, detail=f"{bad} points below margin")
    return minimum


def _audit_self_clearance(geom, points, report):
    """Same-route non-adjacent (path parameter difference > 1 mm) 3D clearance."""
    if len(points) < 2:
        return float("inf")
    a, b, middle = _segments_from_polyline(points)
    lengths = np.linalg.norm(b - a, axis=1)
    arc_start = _arc_length_schedule(a, lengths)
    arc_end = arc_start + lengths
    tree = cKDTree(middle)
    pairs = tree.query_pairs(QUERY_RADIUS_MM, output_type="ndarray")
    if pairs.size == 0:
        return float("inf")
    first = pairs[:, 0]
    second = pairs[:, 1]
    # Only pairs whose arc-length intervals allow a point pair with a path
    # parameter difference above the exemption can violate.
    span = np.maximum(arc_end[first], arc_end[second]) - np.minimum(
        arc_start[first], arc_start[second])
    candidates = np.flatnonzero(span > SELF_PATH_SEPARATION_MM)
    if candidates.size == 0:
        return float("inf")
    first = first[candidates]
    second = second[candidates]
    distance, point_first, point_second, s_param, t_param = _segment_segment_closest(
        a[first], b[first], a[second], b[second])
    # Path parameter difference of the closest point pair (provably safe test).
    s_first = arc_start[first] + s_param * lengths[first]
    s_second = arc_start[second] + t_param * lengths[second]
    delta = np.abs(s_first - s_second)
    # The whole segment-pair region has a difference above the exemption if its
    # minimal possible difference does; flag when either criterion proves a
    # genuine non-adjacent near approach.
    minimum_possible = np.where(
        arc_start[first] <= arc_start[second],
        arc_start[second] - arc_end[first],
        arc_start[first] - arc_end[second])
    genuine = (delta > SELF_PATH_SEPARATION_MM) | (
        minimum_possible > SELF_PATH_SEPARATION_MM)
    bad = np.flatnonzero(genuine & (distance < CLEARANCE_MM - CLEARANCE_TOL_MM))
    minimum = float(np.min(distance)) if distance.size else float("inf")
    for index in bad[:5]:
        report.add("self_clearance_violations", "self_clearance",
                   route_id=geom.route_id,
                   detail=f"distance={distance[index]:.9g} "
                          f"at ({point_first[index, 0]:.9g},"
                          f"{point_first[index, 1]:.9g},"
                          f"{point_first[index, 2]:.9g})")
    if bad.size > 5:
        report.add("self_clearance_violations", "self_clearance",
                   route_id=geom.route_id, detail=f"{bad.size} violating pairs")
    return minimum


def _arc_length_schedule(points_a, segment_lengths):
    """Cumulative arc length at the start of every segment of a polyline."""
    schedule = np.zeros(len(segment_lengths) + 1, dtype=float)
    if len(segment_lengths):
        np.cumsum(segment_lengths, out=schedule[1:])
    return schedule[:-1]


# ---------------------------------------------------------------------------
# Per-layer strict 2D audit (SCHEMA 4.6)
# ---------------------------------------------------------------------------
def _audit_layers(geoms, report):
    """Strict 2D pair audit of every flat part, per layer, with the frozen code.

    Returns ``(layer_reports, crossings_total, min_non_crossing)`` where
    ``layer_reports`` maps layer -> dict of counters and ``crossings_total`` is
    the number of actual same-layer spatial crossings.
    """
    by_layer = {}
    for geom in geoms:
        for part in geom.flat_parts:
            by_layer.setdefault(part.layer, []).append(
                (f"{geom.route_id}:{part.index}", geom, part))
    layer_reports = OrderedDict()
    crossings_total = 0
    min_non_crossing = None
    for layer in sorted(by_layer):
        entries = by_layer[layer]
        prepared = []
        prepared_ids = set()
        for part_id, _geom, part in entries:
            if part_id in prepared_ids:
                report.add("structure_errors", "duplicate_part_id",
                           detail=part_id)
                continue
            prepared_ids.add(part_id)
            try:
                prepared.append(validate_fslw.prepare_route(
                    part.raw_primitives, route_id=part_id))
            except (ValueError, KeyError, TypeError) as exc:
                report.add("structure_errors", "layer_2d_prepare_failed",
                           detail=f"{part_id}: {type(exc).__name__}: {exc}")
        started = time.perf_counter()
        try:
            result = validate_fslw.audit_route_pairs(prepared, policy="strict")
        except Exception as exc:  # frozen validator must not crash the audit
            report.add("layer_2d_violations", "layer_audit_failed",
                       detail=f"layer={layer} {type(exc).__name__}: {exc}")
            layer_reports[str(layer)] = {
                "parts": len(prepared), "crossings": None, "violations": None,
                "min_non_crossing_centerline_mm": None,
                "runtime_seconds": round(time.perf_counter() - started, 3),
                "audit_failed": True,
            }
            continue
        layer_violations = len(result["violations"])
        for violation in result["violations"]:
            report.add("layer_2d_violations", str(violation.get("kind")),
                       route_id=violation.get("route_a"),
                       other_route=violation.get("route_b"),
                       detail=f"layer={layer} distance="
                              f"{violation.get('distance_mm')} "
                              f"at ({violation.get('x')},{violation.get('y')})")
        crossings = int(result.get("crossing_count") or 0)
        crossings_total += crossings
        layer_min = result.get("min_non_crossing_centerline_mm")
        if layer_min is not None:
            if min_non_crossing is None or layer_min < min_non_crossing:
                min_non_crossing = float(layer_min)
        layer_reports[str(layer)] = {
            "parts": len(prepared),
            "crossings": crossings,
            "crossing_pairs": int(result.get("crossing_pair_count") or 0),
            "violations": layer_violations,
            "min_non_crossing_centerline_mm": _round(layer_min),
            "small_angle_crossings": int(result.get("small_angle_crossing_count") or 0),
            "runtime_seconds": round(time.perf_counter() - started, 3),
        }
    return layer_reports, crossings_total, min_non_crossing


# ---------------------------------------------------------------------------
# True 3D clearance between different routes (SCHEMA 4.5)
# ---------------------------------------------------------------------------
class _SegmentStore:
    """Flat / transition segment arrays of every routed geometry."""

    __slots__ = ("flat_a", "flat_b", "flat_mid", "flat_route", "flat_layer",
                 "trans_a", "trans_b", "trans_mid", "trans_route", "trans_part",
                 "n_flat", "n_trans")

    def __init__(self):
        self.flat_a = []
        self.flat_b = []
        self.flat_route = []
        self.flat_layer = []
        self.trans_a = []
        self.trans_b = []
        self.trans_route = []
        self.trans_part = []
        self.n_flat = 0
        self.n_trans = 0

    def add_flat(self, geom, part):
        points = part.samples(FLAT_STEP_MM)
        a, b, _middle = _segments_from_polyline(points)
        if len(a) == 0:
            return
        self.flat_a.append(a)
        self.flat_b.append(b)
        self.flat_route.append(np.full(len(a), geom.route_id, dtype=np.int64))
        self.flat_layer.append(np.full(len(a), int(part.layer), dtype=np.int32))
        self.n_flat += len(a)

    def add_transition(self, geom, part):
        points = part.samples(TRANSITION_STEP_MM)
        a, b, _middle = _segments_from_polyline(points)
        if len(a) == 0:
            return
        self.trans_a.append(a)
        self.trans_b.append(b)
        self.trans_route.append(np.full(len(a), geom.route_id, dtype=np.int64))
        self.trans_part.append(np.full(len(a), int(part.index), dtype=np.int32))
        self.n_trans += len(a)

    def finalise(self):
        if not self.flat_a:
            empty = np.zeros((0, 3))
            self.flat_a = empty
            self.flat_b = empty
            self.flat_mid = empty
            self.flat_route = np.zeros(0, dtype=np.int64)
            self.flat_layer = np.zeros(0, dtype=np.int32)
        else:
            self.flat_a = np.vstack(self.flat_a)
            self.flat_b = np.vstack(self.flat_b)
            self.flat_mid = 0.5 * (self.flat_a + self.flat_b)
            self.flat_route = np.concatenate(self.flat_route)
            self.flat_layer = np.concatenate(self.flat_layer)
        if not self.trans_a:
            empty = np.zeros((0, 3))
            self.trans_a = empty
            self.trans_b = empty
            self.trans_mid = empty
            self.trans_route = np.zeros(0, dtype=np.int64)
            self.trans_part = np.zeros(0, dtype=np.int32)
        else:
            self.trans_a = np.vstack(self.trans_a)
            self.trans_b = np.vstack(self.trans_b)
            self.trans_mid = 0.5 * (self.trans_a + self.trans_b)
            self.trans_route = np.concatenate(self.trans_route)
            self.trans_part = np.concatenate(self.trans_part)
        return self

    def statistics(self):
        return {
            "flat_segments": int(self.n_flat),
            "transition_segments": int(self.n_trans),
            "flat_length_mm": _round(float(np.sum(
                np.linalg.norm(self.flat_b - self.flat_a, axis=1)))
                if self.n_flat else 0.0),
            "transition_length_mm": _round(float(np.sum(
                np.linalg.norm(self.trans_b - self.trans_a, axis=1)))
                if self.n_trans else 0.0),
        }


def _iter_candidate_pairs(tree, query_points, chunk_size=32768):
    """Yield ``(query_index, tree_index)`` arrays for every neighbour pair."""
    total = len(query_points)
    for start in range(0, total, chunk_size):
        stop = min(total, start + chunk_size)
        neighbours = tree.query_ball_point(query_points[start:stop],
                                           r=QUERY_RADIUS_MM, workers=-1)
        counts = np.fromiter((len(item) for item in neighbours), dtype=np.int64,
                             count=len(neighbours))
        if counts.sum() == 0:
            continue
        query_index = np.repeat(np.arange(start, stop, dtype=np.int64), counts)
        tree_index = np.concatenate([np.asarray(item, dtype=np.int64)
                                     for item in neighbours])
        yield query_index, tree_index


def _audit_3d_pairs(store, geoms, report):
    """True 3D clearance of every transition-involved route pair.

    Flat/flat pairs on the same layer are delegated to the frozen strict 2D
    audit; flat/flat pairs on different layers are separated vertically by at
    least the smallest layer gap (verified analytically).  Everything that
    involves a transition is measured here with fine polylines and exact
    segment/segment distance refinement.
    """
    stats = {
        "min_flat_transition_mm": None,
        "min_transition_transition_mm": None,
        "flat_transition_pairs": 0,
        "transition_transition_pairs": 0,
    }
    if store.n_trans == 0:
        return stats
    # ---- transition vs flat -------------------------------------------------
    if store.n_flat:
        flat_tree = cKDTree(store.flat_mid)
        minimum = float("inf")
        for query_index, flat_index in _iter_candidate_pairs(
                flat_tree, store.trans_mid):
            query_route = store.trans_route[query_index]
            flat_route = store.flat_route[flat_index]
            keep = query_route != flat_route
            if not np.any(keep):
                continue
            query_index = query_index[keep]
            flat_index = flat_index[keep]
            distance, point_a, point_b, _s, _t = _segment_segment_closest(
                store.trans_a[query_index], store.trans_b[query_index],
                store.flat_a[flat_index], store.flat_b[flat_index])
            minimum = min(minimum, float(np.min(distance)))
            bad = np.flatnonzero(distance < CLEARANCE_MM - CLEARANCE_TOL_MM)
            stats["flat_transition_pairs"] += int(bad.size)
            for index in bad[:5]:
                report.add(
                    "clearance_violations", "transition_vs_flat",
                    route_id=int(query_route[index]),
                    other_route=int(flat_route[index]),
                    detail=f"distance={distance[index]:.9g} "
                           f"at ({point_a[index, 0]:.9g},{point_a[index, 1]:.9g},"
                           f"{point_a[index, 2]:.9g}) layer="
                           f"{int(store.flat_layer[flat_index[index]])}")
            if bad.size > 5:
                report.add("clearance_violations", "transition_vs_flat",
                           detail=f"{bad.size} violating segment pairs")
        stats["min_flat_transition_mm"] = (minimum
                                           if math.isfinite(minimum) else None)
    # ---- transition vs transition ------------------------------------------
    if store.n_trans > 1:
        trans_tree = cKDTree(store.trans_mid)
        minimum = float("inf")
        for query_index, other_index in _iter_candidate_pairs(
                trans_tree, store.trans_mid):
            keep = (store.trans_route[query_index] != store.trans_route[other_index])
            # every unordered segment pair is visited twice (once per direction);
            # keeping only query < other makes the audit exact and duplicate free
            keep &= query_index < other_index
            if not np.any(keep):
                continue
            query_index = query_index[keep]
            other_index = other_index[keep]
            distance, point_a, point_b, _s, _t = _segment_segment_closest(
                store.trans_a[query_index], store.trans_b[query_index],
                store.trans_a[other_index], store.trans_b[other_index])
            minimum = min(minimum, float(np.min(distance)))
            bad = np.flatnonzero(distance < CLEARANCE_MM - CLEARANCE_TOL_MM)
            stats["transition_transition_pairs"] += int(bad.size)
            for index in bad[:5]:
                report.add(
                    "clearance_violations", "transition_vs_transition",
                    route_id=int(store.trans_route[query_index[index]]),
                    other_route=int(store.trans_route[other_index[index]]),
                    detail=f"distance={distance[index]:.9g}")
            if bad.size > 5:
                report.add("clearance_violations", "transition_vs_transition",
                           detail=f"{bad.size} violating segment pairs")
        stats["min_transition_transition_mm"] = (minimum
                                                if math.isfinite(minimum) else None)
    return stats


# ---------------------------------------------------------------------------
# Run-level validation
# ---------------------------------------------------------------------------
def _validate_failed_record(record, report):
    """Light structural check of a failed record (SCHEMA section 3)."""
    route_id = record.get("route_id")
    for field in ("route_id", "plane", "status", "reason", "interface_layer",
                  "interface_z_mm", "port"):
        if field not in record:
            report.add("structure_errors", "failed_record_missing_field",
                       route_id=route_id, detail=field)
    reason = record.get("reason")
    if reason not in ("no_2d_candidate", "no_lift_candidate"):
        report.add("structure_errors", "failed_reason_unknown", route_id=route_id,
                   detail=str(reason))
    port = record.get("port")
    if isinstance(port, dict):
        for field in ("p", "q", "start_tangent", "end_tangent"):
            if field not in port:
                report.add("structure_errors", "failed_port_missing_field",
                           route_id=route_id, detail=field)


def _check_statistics(payload, routed_count, lifted_count, transitions,
                      total_length, report):
    """Payload ``statistics`` must agree with the records (warnings only)."""
    statistics = payload.get("statistics")
    if not isinstance(statistics, dict):
        report.warn("payload has no 'statistics' mapping")
        return
    checks = {
        "routed": (routed_count, 0.0),
        "lifted": (lifted_count, 0.0),
        "transitions": (transitions, 0.0),
        "total_length_mm": (total_length, 1e-2),
    }
    for field, (computed, tolerance) in checks.items():
        declared = statistics.get(field)
        if declared is None:
            report.warn(f"statistics.{field} missing")
            continue
        try:
            if abs(float(declared) - float(computed)) > tolerance:
                report.add("structure_errors", "statistics_mismatch",
                           detail=f"{field}: {declared!r} != {_round(computed)}")
        except (TypeError, ValueError):
            report.add("structure_errors", "statistics_invalid", detail=field)


def _check_layer_gaps(layers_z, report):
    """Different layers must be vertically separated by the clearance."""
    gaps = sorted(abs(layers_z[i] - layers_z[j])
                  for i in range(len(layers_z)) for j in range(i + 1, len(layers_z)))
    minimum = gaps[0] if gaps else float("inf")
    if minimum < CLEARANCE_MM - CLEARANCE_TOL_MM:
        report.add("clearance_violations", "layer_gap_below_clearance",
                   detail=f"minimum layer gap {minimum:.9g} mm < {CLEARANCE_MM}")
    return minimum


def _combine_minimum(measured, lower_bounds):
    """Combine measured minima with known lower bounds into one report value."""
    if measured:
        value = min(measured)
        bound = "measured"
    elif lower_bounds:
        value = min(lower_bounds)
        bound = "lower_bound"
    else:
        value = None
        bound = "unknown"
    resolved = (value is not None
                and all(bound_value >= value for bound_value in lower_bounds))
    return value, bound, resolved


def validate_routes_file(routes_path, out_path=None, label=None, root=None,
                         expected_scheme=None, expected_layers=None,
                         check_port_csv=True, max_violations_per_category=200):
    """Validate one ``routes_25d.json`` file; returns the report dictionary.

    The full SCHEMA_25D.md section 4 check list is executed; nothing is imported
    from the 2.5D router modules.
    """
    started = time.perf_counter()
    routes_path = Path(routes_path)
    report = _Report(max_violations_per_category)
    result = {
        "schema": SCHEMA_RUN,
        "label": label,
        "input": str(routes_path),
        "root": str(root) if root is not None else None,
        "scheme": None,
        "n_layers": None,
        "passed": False,
        "failure_reasons": [],
        "routed": 0,
        "failed": 0,
        "total": 0,
        "min_3d_distance_mm": None,
        "min_3d_distance_excluding_crossings_mm": None,
        "min_curvature_radius_mm": None,
        "crossings": {"total": 0, "by_layer": {}},
        "violations": report.violations,
        "violation_kinds": report.kind_counts,
        "counts": None,
        "stats": {},
        "layer_2d": {},
        "warnings": report.warnings,
    }
    try:
        payload = json.loads(routes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.add("structure_errors", "input_unreadable",
                   detail=f"{type(exc).__name__}: {exc}")
        result["counts"] = _finalise_counts(report)
        result["runtime_seconds"] = round(time.perf_counter() - started, 3)
        return result
    try:
        context = _check_payload(payload, report, expected_scheme,
                                 expected_layers, check_port_csv)
    except _DataError as exc:
        report.add("structure_errors", "payload_invalid", detail=str(exc))
        result["counts"] = _finalise_counts(report)
        result["runtime_seconds"] = round(time.perf_counter() - started, 3)
        return result
    result["scheme"] = context["scheme"]
    result["n_layers"] = context["n_layers"]
    result["layers_z_mm"] = context["layers_z"]
    result["interface_layer"] = context["interface_layer"]
    result["process"] = payload.get("process")
    result["csv_sha256"] = payload.get("csv_sha256")
    result["csv_sha256_expected"] = EXPECTED_CSV_SHA256
    result["port_csv_checked"] = bool(context["port_csv_checked"])
    if context["layers_z"] is not None:
        result["stats"]["min_layer_gap_mm"] = _round(
            _check_layer_gaps(context["layers_z"], report))
    routes = payload["routes"]
    routed_records = []
    failed_records = []
    geoms = []
    for record in routes:
        if not isinstance(record, dict):
            report.add("structure_errors", "route_not_a_mapping")
            continue
        if record.get("status") == "routed":
            routed_records.append(record)
        else:
            failed_records.append(record)
            _validate_failed_record(record, report)
    route_ids = []
    for record in routed_records:
        route_ids.append(record.get("route_id"))
    duplicates = {value for value in route_ids if route_ids.count(value) > 1}
    if duplicates:
        report.add("structure_errors", "duplicate_route_id",
                   detail=str(sorted(duplicates)[:10]))
    identity = context["identity"]
    if identity is not None:
        missing_ids = {int(value) for value in route_ids
                       if isinstance(value, (int, float))
                       and int(value) not in identity["routes"]}
        if missing_ids:
            report.add("port_errors", "route_ids_not_in_v2_csv",
                       detail=str(sorted(missing_ids)[:10]))
    min_curvature = float("inf")
    min_board_margin = float("inf")
    min_self_clearance = float("inf")
    store = _SegmentStore()
    for record in routed_records:
        try:
            geom = _parse_route(record, context, report)
        except _DataError as exc:
            report.add("structure_errors", "route_parse_error",
                       route_id=record.get("route_id"), detail=str(exc))
            continue
        _check_ports(geom, record, context, report)
        geoms.append(geom)
        min_curvature = min(min_curvature, _audit_curvature(geom, context, report))
        clearance_points = geom.samples(FLAT_STEP_MM, TRANSITION_STEP_MM)
        min_board_margin = min(min_board_margin,
                               _audit_board_margin(geom, clearance_points, report))
        min_self_clearance = min(min_self_clearance,
                                 _audit_self_clearance(geom, clearance_points,
                                                       report))
        for part in geom.flat_parts:
            store.add_flat(geom, part)
        for part in geom.transitions:
            store.add_transition(geom, part)
    store.finalise()
    _check_port_usage(geoms, identity, report)
    # ---- per-layer strict 2D audit -----------------------------------------
    layer_reports, crossings_total, min_layer_non_crossing = _audit_layers(
        geoms, report)
    # ---- true 3D clearance --------------------------------------------------
    three_d = _audit_3d_pairs(store, geoms, report)
    # ---- aggregate metrics --------------------------------------------------
    required_half_flat = 0.5 * FLAT_STEP_MM
    required_half_transition = 0.5 * TRANSITION_STEP_MM
    lower_flat_transition = QUERY_RADIUS_MM - required_half_flat - required_half_transition
    lower_transition_transition = QUERY_RADIUS_MM - 2.0 * required_half_transition
    lower_layer_2d = CLEARANCE_MM + 2.0 * SAGITTA_MM
    measured = []
    lower_bounds = []
    if min_layer_non_crossing is not None:
        measured.append(float(min_layer_non_crossing))
    else:
        lower_bounds.append(lower_layer_2d)
    if three_d["min_flat_transition_mm"] is not None:
        measured.append(float(three_d["min_flat_transition_mm"]))
    elif store.n_trans and store.n_flat:
        lower_bounds.append(lower_flat_transition)
    if three_d["min_transition_transition_mm"] is not None:
        measured.append(float(three_d["min_transition_transition_mm"]))
    elif store.n_trans > 1:
        lower_bounds.append(lower_transition_transition)
    minimum_distance, minimum_bound, minimum_resolved = _combine_minimum(
        measured, lower_bounds)
    if minimum_distance is not None:
        minimum_distance = float(minimum_distance)
    result["min_3d_distance_mm"] = _round(minimum_distance, 9)
    result["min_3d_distance_excluding_crossings_mm"] = _round(minimum_distance, 9)
    result["min_3d_distance_definition"] = MIN_DISTANCE_DEFINITION
    result["min_3d_distance_is_resolved"] = minimum_resolved
    result["min_3d_distance_including_crossings_mm"] = (
        0.0 if crossings_total > 0 else _round(minimum_distance, 9))
    result["clearance_tolerance_mm"] = CLEARANCE_TOL_MM
    result["board_margin_tolerance_mm"] = BOARD_MARGIN_TOL_MM
    result["min_curvature_radius_mm"] = (
        None if not math.isfinite(min_curvature) else _round(min_curvature, 9))
    result["crossings"] = {
        "total": int(crossings_total),
        "by_layer": {key: int(value.get("crossings") or 0)
                     for key, value in layer_reports.items()},
    }
    result["routed"] = len(routed_records)
    result["failed"] = len(failed_records)
    result["total"] = len(routes)
    result["layer_2d"] = layer_reports
    result["stats"].update({
        "transitions": sum(len(geom.transitions) for geom in geoms),
        "lifted": sum(1 for geom in geoms if geom.mode == "lifted"),
        "flat_routes": sum(1 for geom in geoms if geom.mode == "flat"),
        "flat_parts": sum(len(geom.flat_parts) for geom in geoms),
        "total_length_mm": _round(sum(geom.length_3d for geom in geoms)),
        "total_xy_length_mm": _round(sum(geom.xy_length for geom in geoms)),
        "min_flat_flat_same_layer_mm": _round(min_layer_non_crossing),
        "min_flat_transition_mm": _round(three_d["min_flat_transition_mm"]),
        "min_transition_transition_mm": _round(
            three_d["min_transition_transition_mm"]),
        "min_self_clearance_mm": (
            None if not math.isfinite(min_self_clearance)
            else _round(min_self_clearance)),
        "min_board_margin_mm": (
            None if not math.isfinite(min_board_margin)
            else _round(min_board_margin)),
        "min_3d_distance_bound": minimum_bound,
        "violating_flat_transition_segment_pairs": three_d["flat_transition_pairs"],
        "violating_transition_transition_segment_pairs": (
            three_d["transition_transition_pairs"]),
        "port_csv_checked": bool(context["port_csv_checked"]),
    })
    result["stats"].update(store.statistics())
    _check_statistics(payload, len(routed_records),
                      result["stats"]["lifted"], result["stats"]["transitions"],
                      result["stats"]["total_length_mm"], report)
    # ---- verdict ------------------------------------------------------------
    result["counts"] = _finalise_counts(report)
    reasons = []
    for key in VIOLATION_CATEGORIES:
        if result["counts"][key]:
            reasons.append(f"{key}={result['counts'][key]}")
    if (minimum_distance is not None
            and minimum_distance < CLEARANCE_MM - CLEARANCE_TOL_MM):
        reasons.append(f"min_3d_distance={minimum_distance:.9g} < {CLEARANCE_MM}")
    if result["min_curvature_radius_mm"] is not None and \
            result["min_curvature_radius_mm"] < MIN_CURVATURE_MM:
        reasons.append(f"min_curvature={result['min_curvature_radius_mm']} "
                       f"< {MIN_CURVATURE_MM}")
    if minimum_distance is None and geoms:
        reasons.append("clearance_not_measured")
    result["passed"] = not reasons
    result["failure_reasons"] = reasons
    result["violations"] = report.violations
    result["violation_kinds"] = report.kind_counts
    result["warnings"] = report.warnings
    result["runtime_seconds"] = round(time.perf_counter() - started, 3)
    result["output"] = str(out_path) if out_path is not None else None
    return result


def _finalise_counts(report):
    counts = OrderedDict()
    counts["violations"] = report.total
    for key in VIOLATION_CATEGORIES:
        counts[key] = report.counts[key]
    return counts


# ---------------------------------------------------------------------------
# Input discovery / output writing / CLI
# ---------------------------------------------------------------------------
def _discover_runs(root):
    """Find ``<root>/scheme{A,B}/layers{3,5}/routes_25d.json`` directories."""
    root = Path(root)
    runs = []
    for scheme in ("A", "B"):
        for n_layers in (3, 5):
            path = root / f"scheme{scheme}" / f"layers{n_layers}" / "routes_25d.json"
            if path.exists():
                runs.append({
                    "routes_path": path,
                    "scheme": scheme,
                    "n_layers": n_layers,
                    "label": f"scheme{scheme}/layers{n_layers}",
                    "rel_dir": None,
                })
    return runs


def _input_runs(inputs, root):
    """Turn explicit ``--input`` paths (file or directory) into run descriptors."""
    runs = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            path = path / "routes_25d.json"
        if not path.exists():
            raise FileNotFoundError(f"input routes file not found: {path}")
        path = path.resolve()
        scheme = None
        n_layers = None
        rel_dir = None
        try:
            root_resolved = Path(root).resolve()
            relative = path.relative_to(root_resolved)
            parts = relative.parts
            if (len(parts) == 3 and parts[0].startswith("scheme")
                    and parts[1].startswith("layers")
                    and parts[0][len("scheme"):] in ("A", "B")
                    and parts[1][len("layers"):].isdigit()):
                scheme = parts[0][len("scheme"):]
                n_layers = int(parts[1][len("layers"):])
            elif len(parts) > 1:
                rel_dir = "/".join(parts[:-1])
        except ValueError:
            rel_dir = None
        if scheme is not None and n_layers is not None:
            runs.append({"routes_path": path, "scheme": scheme,
                         "n_layers": n_layers,
                         "label": f"scheme{scheme}/layers{n_layers}",
                         "rel_dir": None})
        else:
            safe = (rel_dir.replace("\\", "_").replace("/", "_")
                    if rel_dir else "input")
            runs.append({"routes_path": path, "scheme": None, "n_layers": None,
                         "label": None, "rel_dir": safe})
    return runs


def _output_path(out_dir, run, scheme, n_layers):
    if run.get("rel_dir") is None:
        return Path(out_dir) / str(scheme) / f"layers{n_layers}.json"
    safe = run["rel_dir"]
    return Path(out_dir) / safe / f"{scheme}_layers{n_layers}.json"


def _label_for(run, scheme, n_layers):
    if run.get("label"):
        return run["label"]
    safe = run.get("rel_dir") or "input"
    return f"{safe}/{scheme}_layers{n_layers}"


def _peek_identity(path):
    """Read only the scheme / n_layers fields of a routes file (for labels)."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    scheme = payload.get("scheme")
    try:
        n_layers = int(payload.get("n_layers"))
    except (TypeError, ValueError):
        n_layers = None
    return scheme, n_layers


def _matches_only(run_label, scheme, n_layers, only):
    if not only:
        return True
    wanted = set()
    for item in only:
        wanted.add(str(item).strip())
        wanted.add(str(item).strip().lstrip("scheme"))
    candidates = {run_label}
    if scheme is not None and n_layers is not None:
        candidates.update({f"scheme{scheme}/layers{n_layers}",
                           f"{scheme}/layers{n_layers}",
                           f"{scheme}{n_layers}",
                           f"scheme{scheme}{n_layers}",
                           f"{scheme}_layers{n_layers}"})
    return bool(candidates & wanted)


def _merge_all_validation(out_dir, results, root):
    """Merge the run results into ``all_validation.json`` (overwrite per label)."""
    all_path = Path(out_dir) / "all_validation.json"
    runs = {}
    if all_path.exists():
        try:
            previous = json.loads(all_path.read_text(encoding="utf-8"))
            if isinstance(previous, dict) and isinstance(previous.get("runs"), dict):
                runs.update(previous["runs"])
        except (OSError, json.JSONDecodeError):
            runs = {}
    for label, result in results.items():
        runs[label] = {
            "input": result.get("input"),
            "output": result.get("output"),
            "scheme": result.get("scheme"),
            "n_layers": result.get("n_layers"),
            "passed": result.get("passed"),
            "routed": result.get("routed"),
            "failed": result.get("failed"),
            "crossings_total": (result.get("crossings") or {}).get("total"),
            "crossings_by_layer": (result.get("crossings") or {}).get("by_layer"),
            "counts": result.get("counts"),
            "min_3d_distance_mm": result.get("min_3d_distance_mm"),
            "min_3d_distance_excluding_crossings_mm": result.get(
                "min_3d_distance_excluding_crossings_mm"),
            "min_curvature_radius_mm": result.get("min_curvature_radius_mm"),
            "violations_count": len(result.get("violations") or []),
            "failure_reasons": result.get("failure_reasons"),
        }
    payload = {
        "schema": SCHEMA_ALL,
        "root": str(root),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runs": OrderedDict(sorted(runs.items())),
        "run_labels": sorted(runs),
        "passed": all(bool(entry.get("passed")) for entry in runs.values())
                  if runs else False,
        "counts_total": {key: sum(int((entry.get("counts") or {}).get(key) or 0)
                                  for entry in runs.values())
                         for key in COUNT_KEYS},
        "min_3d_distance_mm": min(
            (entry.get("min_3d_distance_excluding_crossings_mm")
             for entry in runs.values()
             if entry.get("min_3d_distance_excluding_crossings_mm") is not None),
            default=None),
        "min_curvature_radius_mm": min(
            (entry.get("min_curvature_radius_mm") for entry in runs.values()
             if entry.get("min_curvature_radius_mm") is not None),
            default=None),
    }
    all_path.parent.mkdir(parents=True, exist_ok=True)
    all_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                        encoding="utf-8")
    return all_path


SUMMARY_COLUMNS = (
    ("label", 24), ("routed", 6), ("failed", 6), ("minR_mm", 9),
    ("min3D_mm", 9), ("crossings", 9), ("viol", 5), ("pass", 5), ("sec", 7),
)


def _print_summary(results):
    header = "".join(f"{name:>{width}s} " for name, width in SUMMARY_COLUMNS)
    print(header)
    print("-" * len(header))
    for label, result in results.items():
        counts = result.get("counts") or {}
        row = (
            (label, 24), (result.get("routed"), 6), (result.get("failed"), 6),
            (_fmt(result.get("min_curvature_radius_mm")), 9),
            (_fmt(result.get("min_3d_distance_excluding_crossings_mm")), 9),
            ((result.get("crossings") or {}).get("total"), 9),
            (counts.get("violations"), 5),
            ("PASS" if result.get("passed") else "FAIL", 5),
            (_fmt(result.get("runtime_seconds"), 2), 7),
        )
        print("".join(f"{str(value):>{width}s} " for value, width in row))


def _write_report(path, result):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False),
                    encoding="utf-8")
    return path


def main(argv=None):
    """CLI entry point; returns the process exit code (0 = all selected passed)."""
    parser = argparse.ArgumentParser(
        description=("Independent 3D validator of the 2.5D five-layer experiment "
                     "(SCHEMA_25D.md section 4)."),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--root", type=Path, default=None,
                        help="experiment root (default: the config25d V25D_ROOT)")
    parser.add_argument("--input", action="append", default=None,
                        help="explicit routes_25d.json file or directory "
                             "(repeatable; bypasses --root discovery)")
    parser.add_argument("--out", type=Path, default=None,
                        help="output directory (default: <root>/validation)")
    parser.add_argument("--only", action="append", default=None,
                        help="only validate the given run label, e.g. "
                             "schemeA/layers5 (repeatable)")
    parser.add_argument("--no-port-csv", action="store_true",
                        help="skip the V2 port/CSV identity checks "
                             "(CSV unavailable offline)")
    parser.add_argument("--max-violations", type=int, default=200,
                        help="maximum stored violations per category")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root is not None else Path(CFG.V25D_ROOT)
    out_dir = Path(args.out) if args.out is not None else root / "validation"
    if args.input:
        try:
            runs = _input_runs(args.input, root)
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        runs = _discover_runs(root)
        if not runs:
            print(f"no routes_25d.json files found under {root}", file=sys.stderr)
            return 2
    results = OrderedDict()
    for run in runs:
        routes_path = run["routes_path"]
        scheme, n_layers = run["scheme"], run["n_layers"]
        if scheme is None or n_layers is None:
            scheme, n_layers = _peek_identity(routes_path)
            if scheme is None or n_layers is None:
                print(f"error: cannot infer scheme/n_layers from {routes_path}",
                      file=sys.stderr)
                return 2
        label = _label_for(run, scheme, n_layers)
        if not _matches_only(label, scheme, n_layers, args.only):
            continue
        out_path = _output_path(out_dir, run, scheme, n_layers)
        print(f"validating {label}: {routes_path}")
        result = validate_routes_file(
            routes_path, out_path=out_path, label=label, root=root,
            expected_scheme=scheme, expected_layers=n_layers,
            check_port_csv=not args.no_port_csv,
            max_violations_per_category=args.max_violations)
        _write_report(out_path, result)
        results[label] = result
        print(f"  written {out_path} ({result['runtime_seconds']:.1f} s)")
    if not results:
        print("no runs matched the requested filter", file=sys.stderr)
        return 2
    all_path = _merge_all_validation(out_dir, results, root)
    print()
    _print_summary(results)
    print()
    print(f"aggregate written {all_path}")
    return 0 if all(result["passed"] for result in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
