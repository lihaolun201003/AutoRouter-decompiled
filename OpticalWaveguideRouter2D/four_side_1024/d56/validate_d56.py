"""Independent D56 legality validator for the 1024-channel four-side router.

Phase 7a deliverable.  This module re-derives every predicate it needs instead
of delegating the verdict to the router's own checker:

* the D56 single-route checks (orthogonal lines, fixed R=5 arcs, the legacy
  ``theta=acos(1-d/(2R))`` short-S pair, arc/pose consistency, G1 continuity,
  fixed ports, in/out directions, single layer, stroked board bounds,
  self-intersection / self-overlap / self-spacing) are implemented here;
* the inter-route clearance audit (exact centerline distance ``>= clearance``
  except for local windows of width ``clearance/sin(angle)+2*sagitta`` measured
  along *both* curves, rejection of overlap / tangency / overlapping windows,
  and outside-window spacing checks) has the same policy as
  ``four_side_1024/conflicts.py`` but its aggregation is written independently.

Only pure analytic primitives are imported from ``four_side_1024.geometry``:
``intersections`` (exact line/arc intersection coordinates), ``bounds`` (exact
stroked extents) and ``sample`` (chordal sampling, used for reporting only).
``four_side_1024.conflicts`` is never imported.

Command line::

    .venv\\Scripts\\python.exe -m four_side_1024.d56.validate_d56 ^
        --run-dir outputs\\four_side_1024_d56_optimized ^
        --output scratch\\validate_audit.json
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

from ..geometry import bounds as _geometry_bounds
from ..geometry import intersections as _geometry_intersections
from ..inputs import load as _load_inputs

# ---------------------------------------------------------------------------
# SPEC constants (never changed by this module)
# ---------------------------------------------------------------------------
BOARD = 150.0
RADIUS = 5.0
WIDTH = 0.05
EDGE_GAP = 0.125
CLEARANCE = WIDTH + EDGE_GAP  # 0.175 mm centerline clearance
SAGITTA = 0.0005
CROSSING_SMALL_ANGLE_DEG = 10.0

# Tolerances.  Single-route pose tolerances are the SPEC 1e-7 values; line
# orthogonality / radius / quarter-turn use the SPEC 1e-9 values.  Pair-audit
# tolerances follow the numeric conventions of four_side_1024/conflicts.py.
ORTHO_TOL = 1e-9
RADIUS_TOL = 1e-9
QUARTER_TOL = 1e-9
SWEEP_TOL = 1e-9
POSE_TOL = 1e-7
BOUNDS_TOL = 1e-8
INTERSECT_TOL = 1e-8
PAIR_EPS = 1e-8
SINE_TOL = 1e-7
ENDPOINT_TOUCH_TOL = 1e-7
CROSSING_DEDUPE = 1e-6

# ---------------------------------------------------------------------------
# Strict local-crossing-window policy (SPEC four_side_1024/abcd/SPEC.md §2.1).
#
# ``legacy`` sizes the exemption with the straight-line formula
# ``clearance/sin(angle) + 2*sagitta``; ``exact`` exempts a whole intersected
# primitive pair; ``strict`` exempts only the exact minimal near-region of a
# genuine transverse crossing: on each side of the crossing point the arc
# length ``h*`` is solved from the *real* line/arc geometry so that the
# distance to the crossing partner primitive reaches ``clearance``, the exempt
# half width is ``h* + 2*sagitta`` and anything outside the local window must
# keep ``clearance - 1e-7``.
# ---------------------------------------------------------------------------
STRICT_MAX_HALF_WINDOW = 4.0            # mm; longer c-band running is not a crossing
STRICT_LIMIT_TOL = 1e-7                 # violation limit lim = clearance - 1e-7
STRICT_SINE_MIN = math.sin(math.radians(5.0))  # D56 minimum genuine crossing angle
STRICT_SOLVE_TOL = 1e-5                 # required |h - h*| (SPEC §2.1)
STRICT_SEARCH_TOL = 1e-5                # internal bracket width (same as the router index)
STRICT_SAMPLES = 4                      # coarse samples per probe interval
STRICT_GROUP_TOL = 1e-6                 # coincident crossing points are one group
STRICT_WINDOW_HIST_BINS = (
    ("0-0.17", 0.0, 0.17),
    ("0.17-0.25", 0.17, 0.25),
    ("0.25-0.5", 0.25, 0.5),
    ("0.5-1", 0.5, 1.0),
    ("1-2", 1.0, 2.0),
    ("2-4.001", 2.0, STRICT_MAX_HALF_WINDOW + 1e-9),
)

TAU = 2.0 * math.pi

HIST_BINS = (
    ("0-1", 0.0, 1.0),
    ("1-5", 1.0, 5.0),
    ("5-10", 5.0, 10.0),
    ("10-20", 10.0, 20.0),
    ("20-30", 20.0, 30.0),
    ("30-45", 30.0, 45.0),
    ("45-60", 45.0, 60.0),
    ("60-75", 60.0, 75.0),
    ("75-90", 75.0, 90.000001),
)

# Status spellings accepted from saved artefacts.
ROUTED_STATUS = {"routed", "success", "succeeded", "ok", "routed_ok"}
FAILED_STATUS = {"failed", "failure", "fail", "blocked", "rejected"}

SINGLE_CHECK_NAMES = (
    "primitives_parsed",
    "orthogonal_lines",
    "radius_fixed",
    "d56_arc_family",
    "arc_endpoint_consistency",
    "position_continuity",
    "tangent_continuity",
    "endpoints_fixed",
    "inout_directions",
    "layer_zero",
    "board_bounds",
    "self_intersection_free",
    "self_overlap_free",
    "self_spacing_ok",
)


# ---------------------------------------------------------------------------
# Small scalar helpers (plain Python floats; fast for the millions of calls the
# pair audit needs and deliberately not reusing the router's vector code).
# ---------------------------------------------------------------------------
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _norm(v):
    return math.hypot(v[0], v[1])


def _pair(value, what="coordinate"):
    try:
        if len(value) != 2:
            raise ValueError
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError, IndexError):
        raise _PrimitiveError(f"invalid_{what}")
    if not (math.isfinite(x) and math.isfinite(y)):
        raise _PrimitiveError(f"nonfinite_{what}")
    return (x, y)


class _PrimitiveError(Exception):
    """Raised when a JSON primitive cannot be interpreted at all."""


# ---------------------------------------------------------------------------
# Primitive representation.  Lines and circular arcs only; everything is kept
# as plain scalars so the pair audit stays exact and reproducible.
# ---------------------------------------------------------------------------
class _Prim:
    __slots__ = ("kind", "p0", "p1", "center", "radius", "start", "sweep",
                 "length", "bbox", "raw")

    def __init__(self, kind, p0, p1, center=(0.0, 0.0), radius=0.0,
                 start=0.0, sweep=0.0):
        self.kind = kind
        self.p0 = p0
        self.p1 = p1
        self.center = center
        self.radius = radius
        self.start = start
        self.sweep = sweep
        if kind == "line":
            self.length = _dist(p0, p1)
            self.bbox = (min(p0[0], p1[0]), min(p0[1], p1[1]),
                         max(p0[0], p1[0]), max(p0[1], p1[1]))
            self.raw = {"kind": "line", "p0": list(p0), "p1": list(p1), "layer": 0}
        else:
            self.length = abs(sweep) * radius
            self.bbox = _arc_bbox(center, radius, start, sweep)
            self.raw = {"kind": "arc", "p0": list(p0), "p1": list(p1),
                        "center": list(center), "radius": float(radius),
                        "start_angle": float(start), "sweep": float(sweep),
                        "layer": 0}

    # -- construction -------------------------------------------------------
    @classmethod
    def from_raw(cls, raw, index=0):
        if not isinstance(raw, dict):
            raise _PrimitiveError("primitive_not_a_mapping")
        kind = raw.get("kind")
        if "p0" not in raw or "p1" not in raw:
            raise _PrimitiveError("missing_endpoints")
        p0 = _pair(raw["p0"], "p0")
        p1 = _pair(raw["p1"], "p1")
        if kind == "line":
            if _dist(p0, p1) <= PAIR_EPS:
                raise _PrimitiveError("zero_length_line")
            return cls("line", p0, p1)
        if kind != "arc":
            raise _PrimitiveError(f"unknown_kind:{kind}")
        for key in ("center", "radius", "start_angle", "sweep"):
            if key not in raw:
                raise _PrimitiveError(f"missing_{key}")
        center = _pair(raw["center"], "center")
        try:
            radius = float(raw["radius"])
            start = float(raw["start_angle"])
            sweep = float(raw["sweep"])
        except (TypeError, ValueError):
            raise _PrimitiveError("non_numeric_arc_parameters")
        if not (math.isfinite(radius) and math.isfinite(start) and math.isfinite(sweep)):
            raise _PrimitiveError("nonfinite_arc_parameters")
        if radius <= PAIR_EPS:
            raise _PrimitiveError("nonpositive_radius")
        if abs(sweep) <= PAIR_EPS or abs(sweep) > TAU + PAIR_EPS:
            raise _PrimitiveError("invalid_arc_sweep")
        return cls("arc", p0, p1, center, radius, start, sweep)

    # -- analytic parameterisation -----------------------------------------
    def point(self, t):
        if self.kind == "line":
            return (self.p0[0] + t * (self.p1[0] - self.p0[0]),
                    self.p0[1] + t * (self.p1[1] - self.p0[1]))
        angle = self.start + t * self.sweep
        return (self.center[0] + self.radius * math.cos(angle),
                self.center[1] + self.radius * math.sin(angle))

    def tangent(self, t):
        if self.kind == "line":
            return ((self.p1[0] - self.p0[0]) / self.length,
                    (self.p1[1] - self.p0[1]) / self.length)
        angle = self.start + t * self.sweep
        sign = 1.0 if self.sweep > 0 else -1.0
        return (-sign * math.sin(angle), sign * math.cos(angle))

    def parameter(self, point):
        if self.kind == "line":
            d = (self.p1[0] - self.p0[0], self.p1[1] - self.p0[1])
            raw = _dot(_sub(point, self.p0), d) / (self.length * self.length)
        else:
            angle = math.atan2(point[1] - self.center[1], point[0] - self.center[0])
            delta = ((angle - self.start) if self.sweep > 0
                     else (self.start - angle)) % TAU
            # Floating-point noise can displace a start angle by one full turn.
            if TAU - delta < PAIR_EPS:
                delta = 0.0
            raw = delta / abs(self.sweep)
        return 0.0 if raw < 0.0 else (1.0 if raw > 1.0 else raw)

    def contains_angle(self, angle, tol=PAIR_EPS):
        delta = ((angle - self.start) if self.sweep > 0
                 else (self.start - angle)) % TAU
        return delta <= abs(self.sweep) + tol or TAU - delta < tol

    def angular_intervals(self):
        if abs(self.sweep) >= TAU - PAIR_EPS:
            return [(0.0, TAU)]
        lo = (self.start if self.sweep > 0 else self.start + self.sweep) % TAU
        hi = lo + abs(self.sweep)
        return [(lo, hi)] if hi <= TAU else [(lo, TAU), (0.0, hi - TAU)]

    def clip(self, t0, t1):
        t0 = 0.0 if t0 < 0.0 else (1.0 if t0 > 1.0 else t0)
        t1 = 0.0 if t1 < 0.0 else (1.0 if t1 > 1.0 else t1)
        if t1 <= t0:
            raise _PrimitiveError("empty_clip")
        if self.kind == "line":
            return _Prim("line", self.point(t0), self.point(t1))
        return _Prim("arc", self.point(t0), self.point(t1), self.center,
                     self.radius, self.start + t0 * self.sweep,
                     (t1 - t0) * self.sweep)

    def __repr__(self):  # pragma: no cover - debugging aid
        return (f"<{self.kind} p0={self.p0} p1={self.p1} "
                f"len={self.length:.6f}>")


def _arc_contains(angle, start, sweep, tol=PAIR_EPS):
    delta = ((angle - start) if sweep > 0 else (start - angle)) % TAU
    return delta <= abs(sweep) + tol or TAU - delta < tol


def _arc_bbox(center, radius, start, sweep):
    angles = [start, start + sweep]
    for quadrant in (0.0, math.pi / 2.0, math.pi, 1.5 * math.pi):
        if _arc_contains(quadrant, start, sweep):
            angles.append(quadrant)
    xs = [center[0] + radius * math.cos(a) for a in angles]
    ys = [center[1] + radius * math.sin(a) for a in angles]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_overlap(a, b, tol=PAIR_EPS):
    return (a[0] <= b[2] + tol and b[0] <= a[2] + tol
            and a[1] <= b[3] + tol and b[1] <= a[3] + tol)


def _bbox_distance(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


# ---------------------------------------------------------------------------
# Exact minimum distance between two finite centerline primitives.
#
# Predicate policy is the same as the router conflict audit: intersections are
# zero, otherwise the exact minimum of two finite straight/circular pieces is
# the minimum of the four endpoint-to-piece distances and the analytic
# interior-interior extrema (circle points whose radial direction is normal to
# the other piece, and radial pairs for concentric arcs).
# ---------------------------------------------------------------------------
def _point_prim_distance(point, prim):
    """Exact distance from a point to a finite primitive (inlined hot path)."""
    if prim.kind == "line":
        p0 = prim.p0
        ux = prim.p1[0] - p0[0]
        uy = prim.p1[1] - p0[1]
        wx = point[0] - p0[0]
        wy = point[1] - p0[1]
        projection = wx * ux + wy * uy
        if projection <= 0.0:
            return math.hypot(wx, wy)
        denominator = prim.length * prim.length
        if projection >= denominator:
            return math.hypot(point[0] - prim.p1[0], point[1] - prim.p1[1])
        t = projection / denominator
        return math.hypot(point[0] - (p0[0] + t * ux),
                          point[1] - (p0[1] + t * uy))
    center = prim.center
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    if prim.contains_angle(math.atan2(dy, dx)):
        return abs(math.hypot(dx, dy) - prim.radius)
    return min(math.hypot(point[0] - prim.p0[0], point[1] - prim.p0[1]),
               math.hypot(point[0] - prim.p1[0], point[1] - prim.p1[1]))


def _prims_intersect(a, b, tol=INTERSECT_TOL):
    """Fast scalar predicate: do two finite primitives share any point?

    ``True`` also for positive-length collinear/concentric overlap.  This is
    used only as the zero-distance predicate inside ``_exact_distance``; the
    crossing-point enumeration still uses the exact analytic primitive.
    """
    if a.kind == "line" and b.kind == "line":
        ux = a.p1[0] - a.p0[0]
        uy = a.p1[1] - a.p0[1]
        vx = b.p1[0] - b.p0[0]
        vy = b.p1[1] - b.p0[1]
        wx = b.p0[0] - a.p0[0]
        wy = b.p0[1] - a.p0[1]
        denominator = ux * vy - uy * vx
        if abs(denominator) > tol:
            t = (wx * vy - wy * vx) / denominator
            s = (wx * uy - wy * ux) / denominator
            return -tol <= t <= 1.0 + tol and -tol <= s <= 1.0 + tol
        if abs(wx * uy - wy * ux) > tol:
            return False
        norm2 = ux * ux + uy * uy
        if norm2 < 1e-18:
            return False
        s0 = (wx * ux + wy * uy) / norm2
        s1 = ((wx + vx) * ux + (wy + vy) * uy) / norm2
        lo = max(0.0, min(s0, s1))
        hi = min(1.0, max(s0, s1))
        return hi >= lo - tol
    if a.kind == "line" or b.kind == "line":
        line, arc = (a, b) if a.kind == "line" else (b, a)
        ux = (line.p1[0] - line.p0[0]) / line.length
        uy = (line.p1[1] - line.p0[1]) / line.length
        wx = line.p0[0] - arc.center[0]
        wy = line.p0[1] - arc.center[1]
        along = -(wx * ux + wy * uy)
        perpendicular = wx * uy - wy * ux
        height2 = arc.radius * arc.radius - perpendicular * perpendicular
        roundoff = 64.0 * 2.220446049250313e-16 * max(
            1.0, wx * wx + wy * wy, arc.radius * arc.radius)
        if height2 < -roundoff:
            return False
        root = 0.0 if abs(height2) <= roundoff else math.sqrt(height2)
        for raw_t in ((along - root) / line.length, (along + root) / line.length):
            if -tol <= raw_t <= 1.0 + tol:
                t = 0.0 if raw_t < 0.0 else (1.0 if raw_t > 1.0 else raw_t)
                px = line.p0[0] + t * (line.p1[0] - line.p0[0])
                py = line.p0[1] + t * (line.p1[1] - line.p0[1])
                if arc.contains_angle(math.atan2(py - arc.center[1], px - arc.center[0])):
                    return True
        return False
    dx = b.center[0] - a.center[0]
    dy = b.center[1] - a.center[1]
    distance = math.hypot(dx, dy)
    if distance < tol and abs(a.radius - b.radius) < tol:
        for lo, hi in a.angular_intervals():
            for other_lo, other_hi in b.angular_intervals():
                if min(hi, other_hi) - max(lo, other_lo) > tol / max(a.radius, 1.0):
                    return True
        for point in (a.p0, a.p1, b.p0, b.p1):
            angle = math.atan2(point[1] - a.center[1], point[0] - a.center[0])
            if a.contains_angle(angle) and b.contains_angle(angle):
                return True
        return False
    if (distance < tol or distance > a.radius + b.radius + tol
            or distance < abs(a.radius - b.radius) - tol):
        return False
    chord = (a.radius * a.radius - b.radius * b.radius + distance * distance) / (2.0 * distance)
    height2 = a.radius * a.radius - chord * chord
    roundoff = 64.0 * 2.220446049250313e-16 * max(
        1.0, a.radius * a.radius, b.radius * b.radius, distance * distance)
    if abs(height2) <= roundoff:
        height2 = 0.0
    height = math.sqrt(max(0.0, height2))
    ux = dx / distance
    uy = dy / distance
    mx = a.center[0] + chord * ux
    my = a.center[1] + chord * uy
    for sign in (-1.0, 1.0):
        px = mx - sign * height * uy
        py = my + sign * height * ux
        if (a.contains_angle(math.atan2(py - a.center[1], px - a.center[0]))
                and b.contains_angle(math.atan2(py - b.center[1], px - b.center[0]))):
            return True
    return False


def _exact_distance(a, b, bbox_disjoint=None):
    """Exact minimum distance between finite line/arc centerlines (mm).

    ``bbox_disjoint`` lets a caller that already knows the bounding boxes do
    not overlap skip the (more expensive) exact intersection predicate; a
    disjoint box pair cannot produce an intersection because every point of a
    primitive lies inside its own exact bounding box.
    """
    if bbox_disjoint is None:
        bbox_disjoint = not _bbox_overlap(a.bbox, b.bbox, INTERSECT_TOL)
    if not bbox_disjoint and _prims_intersect(a, b):
        return 0.0
    best = min(_point_prim_distance(a.p0, b), _point_prim_distance(a.p1, b),
               _point_prim_distance(b.p0, a), _point_prim_distance(b.p1, a))
    if a.kind == "line" and b.kind == "line":
        return best
    if a.kind == "arc" and b.kind == "line":
        a, b = b, a
    if a.kind == "line":
        # Unit direction projection avoids cancellation on very long lines.
        ux = (a.p1[0] - a.p0[0]) / a.length
        uy = (a.p1[1] - a.p0[1]) / a.length
        for sign in (-1.0, 1.0):
            px = b.center[0] - sign * b.radius * uy
            py = b.center[1] + sign * b.radius * ux
            angle = math.atan2(py - b.center[1], px - b.center[0])
            if not b.contains_angle(angle):
                continue
            raw_t = _dot((px - a.p0[0], py - a.p0[1]), (ux, uy)) / a.length
            if 0.0 <= raw_t <= 1.0:
                best = min(best, _point_prim_distance((px, py), a))
        return best
    # arc / arc
    distance = _dist(a.center, b.center)
    if distance > PAIR_EPS:
        ux = (b.center[0] - a.center[0]) / distance
        uy = (b.center[1] - a.center[1]) / distance
        for sign_a in (-1.0, 1.0):
            px = a.center[0] + sign_a * a.radius * ux
            py = a.center[1] + sign_a * a.radius * uy
            if not a.contains_angle(math.atan2(py - a.center[1], px - a.center[0])):
                continue
            for sign_b in (-1.0, 1.0):
                qx = b.center[0] + sign_b * b.radius * ux
                qy = b.center[1] + sign_b * b.radius * uy
                if b.contains_angle(math.atan2(qy - b.center[1], qx - b.center[0])):
                    best = min(best, math.hypot(px - qx, py - qy))
        return best
    # Concentric arcs: only radial separation can be the minimum and only when
    # the angular ranges overlap.
    for lo, hi in a.angular_intervals():
        for other_lo, other_hi in b.angular_intervals():
            if min(hi, other_hi) - max(lo, other_lo) >= -PAIR_EPS / max(a.radius, 1.0):
                best = min(best, abs(a.radius - b.radius))
                break
        else:
            continue
        break
    return best


# ---------------------------------------------------------------------------
# SINGLE-ROUTE D56 CHECKS
# ---------------------------------------------------------------------------
def _pair_reason(a, b):
    """Return ``None`` if two adjacent non-quarter arcs are a legal short S."""
    theta = abs(a.sweep)
    if not (SWEEP_TOL < theta < math.pi / 2.0 - SWEEP_TOL):
        return "theta_out_of_range"
    if abs(abs(a.sweep) - abs(b.sweep)) > SWEEP_TOL:
        return "unequal_theta"
    if a.sweep * b.sweep > 0.0:
        return "not_opposite_sweep"
    # Displacement measured in the start frame of the pair.
    u = a.tangent(0.0)
    delta = _sub(b.p1, a.p0)
    longitudinal = _dot(delta, u)
    lateral = abs(_cross(u, delta))
    expected_lateral = 2.0 * RADIUS * (1.0 - math.cos(theta))
    expected_longitudinal = 2.0 * RADIUS * math.sin(theta)
    if not (0.0 < lateral < 2.0 * RADIUS):
        return "displacement_out_of_range"
    if abs(lateral - expected_lateral) > POSE_TOL:
        return "lateral_displacement_mismatch"
    if abs(longitudinal - expected_longitudinal) > POSE_TOL:
        return "longitudinal_displacement_mismatch"
    # Original AutoRouter formula theta = acos(1 - d / (2R)); with the exact
    # geometry above this is equivalent to d = 2R(1 - cos(theta)).
    theta_from_d = math.acos(max(-1.0, min(1.0, 1.0 - lateral / (2.0 * RADIUS))))
    if abs(theta - theta_from_d) > POSE_TOL:
        return "theta_displacement_inconsistent"
    return None


def _check_arc_family(prims, errors):
    """Every non-quarter arc must belong to a valid legacy short-S pair.

    The original ``wiring_bend_826`` short-S branch has exactly two arcs of
    radius R with sweeps ``+theta`` / ``-theta`` and (essentially) no straight
    between them.  A lone small arc, three or more arcs in a row, a zero-radius
    replacement or an arbitrary two-arc angle is F56 geometry and is rejected.
    """
    ok = True
    index = 0
    count = len(prims)
    while index < count:
        prim = prims[index]
        if prim.kind != "arc" or abs(abs(prim.sweep) - math.pi / 2.0) <= QUARTER_TOL:
            index += 1
            continue
        other = index + 1
        gap = 0.0
        while other < count and prims[other].kind == "line":
            gap += prims[other].length
            other += 1
        if (other < count and prims[other].kind == "arc"
                and gap <= POSE_TOL):
            reason = _pair_reason(prim, prims[other])
            if reason is None:
                index = other + 1
                continue
            errors.append(f"short_s_pair_invalid:{index}:{other}:{reason}")
        else:
            errors.append(f"short_s_unpaired_arc:{index}:|sweep|={abs(prim.sweep):.12g}")
        ok = False
        index += 1
    return ok


def check_route_primitives(primitives, source=None, target=None, *,
                           width=WIDTH, radius=RADIUS, board=BOARD):
    """Run every D56 single-route check on one ``primitives`` list.

    ``source`` / ``target`` are endpoint dictionaries with ``routing_xy`` and
    ``inward``; when omitted the port-fixity and in/out direction checks are
    reported as not checked (counted separately by the caller).  Returns a dict
    with ``passed``, ``errors`` (stable ``code:detail`` strings), ``checks``
    (per-check booleans), parsed ``prims``/``offsets`` and the exact length.
    """
    errors = []
    checks = {}
    if not isinstance(primitives, (list, tuple)) or not primitives:
        errors.append("empty_geometry")
        return {"passed": False, "errors": errors, "checks": checks,
                "prims": [], "offsets": [], "length_mm": 0.0,
                "bend_count": 0, "n_primitives": 0}

    prims = []
    parse_ok = True
    for index, raw in enumerate(primitives):
        try:
            prims.append(_Prim.from_raw(raw, index))
        except _PrimitiveError as exc:
            parse_ok = False
            errors.append(f"invalid_primitive:{index}:{exc}")
    checks["primitives_parsed"] = parse_ok
    if not parse_ok:
        return {"passed": False, "errors": errors, "checks": checks,
                "prims": prims, "offsets": _offsets(prims),
                "length_mm": sum(p.length for p in prims),
                "bend_count": sum(p.kind == "arc" for p in prims),
                "n_primitives": len(primitives)}

    # 1) only horizontal / vertical straight segments (tol 1e-9)
    ortho_ok = True
    for index, prim in enumerate(prims):
        if prim.kind != "line":
            continue
        dx = abs(prim.p1[0] - prim.p0[0])
        dy = abs(prim.p1[1] - prim.p0[1])
        if min(dx, dy) > ORTHO_TOL:
            ortho_ok = False
            errors.append(f"diagonal_line:{index}")
    checks["orthogonal_lines"] = ortho_ok

    # 2) radius exactly R for every arc (tol 1e-9)
    radius_ok = True
    for index, prim in enumerate(prims):
        if prim.kind == "arc" and abs(prim.radius - radius) > RADIUS_TOL:
            radius_ok = False
            errors.append(f"arc_radius:{index}:{prim.radius:.12g}")
    checks["radius_fixed"] = radius_ok

    # 3) only quarter arcs or legal legacy short-S pairs (no F56 free bends)
    checks["d56_arc_family"] = _check_arc_family(prims, errors)

    # 4a) arc center / radius / start_angle / sweep agree with its endpoints
    arc_consistent = True
    for index, prim in enumerate(prims):
        if prim.kind != "arc":
            continue
        for key, angle in (("p0", prim.start), ("p1", prim.start + prim.sweep)):
            reconstructed = (prim.center[0] + prim.radius * math.cos(angle),
                             prim.center[1] + prim.radius * math.sin(angle))
            if _dist(reconstructed, getattr(prim, key)) > POSE_TOL:
                arc_consistent = False
                errors.append(f"arc_endpoint_inconsistent:{index}:{key}")
    checks["arc_endpoint_consistency"] = arc_consistent

    offsets = _offsets(prims)

    # 4b) position and tangent (G1) continuity
    position_ok = True
    tangent_ok = True
    for index in range(1, len(prims)):
        previous, current = prims[index - 1], prims[index]
        if _dist(previous.p1, current.p0) > POSE_TOL:
            position_ok = False
            errors.append(f"position_discontinuity:{index - 1}:{index}")
        if _dist(previous.tangent(1.0), current.tangent(0.0)) > POSE_TOL:
            tangent_ok = False
            errors.append(f"tangent_discontinuity:{index - 1}:{index}")
    checks["position_continuity"] = position_ok
    checks["tangent_continuity"] = tangent_ok

    # 5) fixed routing ports, 6) in/out directions
    endpoints_checked = False
    if source is not None and target is not None:
        endpoints_checked = True
        endpoints_ok = True
        start_xy = _pair(source["routing_xy"], "source_routing_xy")
        end_xy = _pair(target["routing_xy"], "target_routing_xy")
        if _dist(prims[0].p0, start_xy) > POSE_TOL:
            endpoints_ok = False
            errors.append("start_endpoint_mismatch")
        if _dist(prims[-1].p1, end_xy) > POSE_TOL:
            endpoints_ok = False
            errors.append("end_endpoint_mismatch")
        checks["endpoints_fixed"] = endpoints_ok

        direction_ok = True
        inward = _unit(_pair(source["inward"], "source_inward"))
        target_inward = _unit(_pair(target["inward"], "target_inward"))
        if _dist(prims[0].tangent(0.0), inward) > POSE_TOL:
            direction_ok = False
            errors.append("start_direction_mismatch")
        if _dist(prims[-1].tangent(1.0), (-target_inward[0], -target_inward[1])) > POSE_TOL:
            direction_ok = False
            errors.append("end_direction_mismatch")
        checks["inout_directions"] = direction_ok

    # 7) single routing layer, no z offset
    layer_ok = True
    for index, raw in enumerate(primitives):
        try:
            layer = raw.get("layer", 0)
            z = float(raw.get("z", 0.0))
        except (AttributeError, TypeError, ValueError):
            layer_ok = False
            errors.append(f"invalid_primitive:{index}:layer")
            continue
        if int(layer) != 0:
            layer_ok = False
            errors.append(f"nonzero_layer:{index}:{layer}")
        elif abs(z) > ORTHO_TOL:
            layer_ok = False
            errors.append(f"nonzero_z:{index}:{z:.12g}")
    checks["layer_zero"] = layer_ok

    # 8) stroked (width 0.05) footprint inside [0, 150]^2
    bounds_ok = True
    for index, prim in enumerate(prims):
        try:
            box = _geometry_bounds(prim.raw, width)
        except (ValueError, KeyError, TypeError):
            bounds_ok = False
            errors.append(f"bounds_undefined:{index}")
            continue
        if (box[0] < -BOUNDS_TOL or box[1] < -BOUNDS_TOL
                or box[2] > board + BOUNDS_TOL or box[3] > board + BOUNDS_TOL):
            bounds_ok = False
            errors.append(f"board_out_of_bounds:{index}")
    checks["board_bounds"] = bounds_ok

    # 9) self-intersection / self-overlap (adjacent primitives may only meet at
    #    the shared joint) and non-adjacent centreline spacing.
    self_intersection_ok = True
    self_overlap_ok = True
    for first_index in range(len(prims)):
        first = prims[first_index]
        for second_index in range(first_index + 1, len(prims)):
            second = prims[second_index]
            if not _bbox_overlap(first.bbox, second.bbox, INTERSECT_TOL):
                continue
            try:
                points, overlap = _geometry_intersections(first.raw, second.raw,
                                                          INTERSECT_TOL)
            except (ValueError, KeyError, TypeError, FloatingPointError):
                self_intersection_ok = False
                errors.append(f"self_intersection:{first_index}:{second_index}:predicate_error")
                continue
            if overlap:
                self_overlap_ok = False
                errors.append(f"self_overlap:{first_index}:{second_index}")
            if second_index == first_index + 1:
                for point in points:
                    if _dist(point, first.p1) > POSE_TOL:
                        self_intersection_ok = False
                        errors.append(f"self_intersection:{first_index}:{second_index}")
                        break
            elif points:
                self_intersection_ok = False
                errors.append(f"self_intersection:{first_index}:{second_index}")
    checks["self_intersection_free"] = self_intersection_ok
    checks["self_overlap_free"] = self_overlap_ok

    self_spacing_ok = True
    for first_index in range(len(prims)):
        first = prims[first_index]
        for second_index in range(first_index + 2, len(prims)):
            second = prims[second_index]
            # Same local-order policy as the router conflict index: only pairs
            # separated by more than 2*clearance along the route are checked.
            if offsets[second_index] - (offsets[first_index] + first.length) <= 2.0 * CLEARANCE:
                continue
            if _bbox_distance(first.bbox, second.bbox) >= CLEARANCE - PAIR_EPS:
                continue
            if _exact_distance(first, second) < CLEARANCE - PAIR_EPS:
                self_spacing_ok = False
                errors.append(f"self_spacing:{first_index}:{second_index}")
    checks["self_spacing_ok"] = self_spacing_ok

    return {"passed": not errors, "errors": errors, "checks": checks,
            "prims": prims, "offsets": offsets,
            "length_mm": float(sum(p.length for p in prims)),
            "bend_count": sum(1 for p in prims if p.kind == "arc"),
            "n_primitives": len(prims), "endpoints_checked": endpoints_checked}


def _unit(vector):
    norm = _norm(vector)
    if norm <= PAIR_EPS:
        raise _PrimitiveError("zero_direction")
    return (vector[0] / norm, vector[1] / norm)


def _offsets(prims):
    offsets = []
    total = 0.0
    for prim in prims:
        offsets.append(total)
        total += prim.length
    return offsets


# ---------------------------------------------------------------------------
# INTER-ROUTE EXACT AUDIT (policy of four_side_1024/conflicts.py)
# ---------------------------------------------------------------------------
class _PreparedRoute:
    __slots__ = ("route_id", "prims", "offsets", "length", "bbox")

    def __init__(self, route_id, prims):
        self.route_id = route_id
        self.prims = prims
        self.offsets = _offsets(prims)
        self.length = sum(p.length for p in prims)
        self.bbox = (
            min(p.bbox[0] for p in prims), min(p.bbox[1] for p in prims),
            max(p.bbox[2] for p in prims), max(p.bbox[3] for p in prims),
        )


def prepare_route(primitives, route_id=None):
    """Parse one route's primitives for the pair audit (no legality verdict)."""
    prims = [_Prim.from_raw(raw, index) for index, raw in enumerate(primitives)]
    if not prims:
        raise _PrimitiveError("empty_route")
    return _PreparedRoute(route_id, prims)


def _merge_intervals(intervals, length):
    merged = []
    for lo, hi in sorted(intervals):
        lo = 0.0 if lo < 0.0 else (length if lo > length else lo)
        hi = 0.0 if hi < 0.0 else (length if hi > length else hi)
        if hi <= lo + PAIR_EPS:
            continue
        if merged and lo <= merged[-1][1] + PAIR_EPS:
            previous = merged[-1]
            merged[-1] = (previous[0], max(previous[1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _intervals_overlap(intervals):
    ordered = sorted(intervals)
    return any(ordered[i][1] > ordered[i + 1][0] + PAIR_EPS
               for i in range(len(ordered) - 1))


def _windows_per_primitive(prepared, intervals):
    """Map route arc-length windows to per-primitive local parameter windows."""
    windows = [[] for _ in prepared.prims]
    merged = _merge_intervals(intervals, prepared.length)
    if not merged:
        return windows
    for lo, hi in merged:
        for index, (prim, start) in enumerate(zip(prepared.prims, prepared.offsets)):
            end = start + prim.length
            if hi <= start + PAIR_EPS or lo >= end - PAIR_EPS:
                continue
            local_lo = max(lo, start)
            local_hi = min(hi, end)
            windows[index].append(((local_lo - start) / prim.length,
                                   (local_hi - start) / prim.length))
    return windows


def _complement_windows(windows):
    ordered = sorted(windows)
    kept = []
    cursor = 0.0
    for lo, hi in ordered:
        lo = 0.0 if lo < 0.0 else (1.0 if lo > 1.0 else lo)
        hi = 0.0 if hi < 0.0 else (1.0 if hi > 1.0 else hi)
        if hi <= lo:
            continue
        if lo > cursor + PAIR_EPS:
            kept.append((cursor, lo))
        cursor = max(cursor, hi)
    if 1.0 > cursor + PAIR_EPS:
        kept.append((cursor, 1.0))
    return kept


def _outside_pieces_too_close(prepared, intervals, other, clearance):
    """Cut ``prepared`` by its crossing windows; check kept pieces vs all of ``other``.

    Each kept piece is compared with every primitive of ``other`` after an
    inlined exact-bbox lower-bound prune: a box gap of at least ``clearance``
    certifies the exact distance is legal without evaluating it.  Returns
    ``(violated, distance_mm, (x, y))`` with the nearest approach position.
    """
    if not intervals:
        windows = [[] for _ in prepared.prims]
    else:
        windows = _windows_per_primitive(prepared, intervals)
    other_prims = other.prims
    other_boxes = [prim.bbox for prim in other_prims]
    limit2 = (clearance - PAIR_EPS) * (clearance - PAIR_EPS)
    for index, prim in enumerate(prepared.prims):
        local_windows = windows[index]
        if local_windows:
            pieces = []
            for t0, t1 in _complement_windows(local_windows):
                if (t1 - t0) * prim.length <= PAIR_EPS:
                    continue
                pieces.append(prim.clip(t0, t1))
        else:
            pieces = [prim]
        for piece in pieces:
            piece_box = piece.bbox
            for other_index, other_prim in enumerate(other_prims):
                box = other_boxes[other_index]
                dx = piece_box[0] - box[2]
                candidate = box[0] - piece_box[2]
                if candidate > dx:
                    dx = candidate
                if dx < 0.0:
                    dx = 0.0
                dy = piece_box[1] - box[3]
                candidate = box[1] - piece_box[3]
                if candidate > dy:
                    dy = candidate
                if dy < 0.0:
                    dy = 0.0
                if dx * dx + dy * dy >= limit2:
                    continue
                distance = _exact_distance(piece, other_prim,
                                           bbox_disjoint=(dx > 0.0 or dy > 0.0))
                if distance < clearance - PAIR_EPS:
                    nearest = _nearest_points(piece, other_prim)
                    return True, nearest[0], _midpoint(nearest[1], nearest[2])
    return False, None, None


def _min_primitive_distance(first, second, limit):
    best = None
    for prim_a in first.prims:
        box_a = prim_a.bbox
        for prim_b in second.prims:
            if _bbox_distance(box_a, prim_b.bbox) > limit:
                continue
            distance = _exact_distance(prim_a, prim_b)
            if best is None or distance < best:
                best = distance
    return best


def _midpoint(first, second):
    return ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)


def _nearest_point_on_prim(point, prim):
    """Exact nearest point of a finite primitive to an arbitrary point."""
    if prim.kind == "line":
        p0 = prim.p0
        ux = prim.p1[0] - p0[0]
        uy = prim.p1[1] - p0[1]
        wx = point[0] - p0[0]
        wy = point[1] - p0[1]
        projection = wx * ux + wy * uy
        denominator = prim.length * prim.length
        if projection <= 0.0:
            return prim.p0
        if projection >= denominator:
            return prim.p1
        t = projection / denominator
        return (p0[0] + t * ux, p0[1] + t * uy)
    center = prim.center
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    if prim.contains_angle(math.atan2(dy, dx)):
        norm = math.hypot(dx, dy)
        if norm <= 1e-15:
            return (center[0] + prim.radius, center[1])
        scale = prim.radius / norm
        return (center[0] + dx * scale, center[1] + dy * scale)
    return prim.p0 if _dist(point, prim.p0) <= _dist(point, prim.p1) else prim.p1


def _line_arc_interior_points(line, arc):
    """Best interior line/arc approach candidates as ``(d, on_arc, on_line)``."""
    result = []
    ux = (line.p1[0] - line.p0[0]) / line.length
    uy = (line.p1[1] - line.p0[1]) / line.length
    for sign in (-1.0, 1.0):
        px = arc.center[0] - sign * arc.radius * uy
        py = arc.center[1] + sign * arc.radius * ux
        if not arc.contains_angle(math.atan2(py - arc.center[1], px - arc.center[0])):
            continue
        raw_t = ((px - line.p0[0]) * ux + (py - line.p0[1]) * uy) / line.length
        if not 0.0 <= raw_t <= 1.0:
            continue
        qx = line.p0[0] + raw_t * (line.p1[0] - line.p0[0])
        qy = line.p0[1] + raw_t * (line.p1[1] - line.p0[1])
        result.append((math.hypot(px - qx, py - qy), (px, py), (qx, qy)))
    return result


def _nearest_points(first, second):
    """Exact minimum-distance point pair ``(distance, on_first, on_second)``."""
    if _prims_intersect(first, second):
        points, _ = _geometry_intersections(first.raw, second.raw, INTERSECT_TOL)
        if points:
            point = (float(points[0][0]), float(points[0][1]))
            return 0.0, point, point
        point_a, point_b = first.point(0.5), second.point(0.5)
        return 0.0, point_a, point_b
    candidates = []
    for point in (first.p0, first.p1):
        candidates.append((_dist(point, _nearest_point_on_prim(point, second)),
                           point, _nearest_point_on_prim(point, second)))
    for point in (second.p0, second.p1):
        candidates.append((_dist(_nearest_point_on_prim(point, first), point),
                           _nearest_point_on_prim(point, first), point))
    if first.kind == "line" and second.kind == "arc":
        for distance, on_arc, on_line in _line_arc_interior_points(first, second):
            candidates.append((distance, on_line, on_arc))
    elif first.kind == "arc" and second.kind == "line":
        for distance, on_arc, on_line in _line_arc_interior_points(second, first):
            candidates.append((distance, on_arc, on_line))
    elif first.kind == "arc" and second.kind == "arc":
        dx = second.center[0] - first.center[0]
        dy = second.center[1] - first.center[1]
        centers = math.hypot(dx, dy)
        if centers > PAIR_EPS:
            ux = dx / centers
            uy = dy / centers
            for sign_a in (-1.0, 1.0):
                px = first.center[0] + sign_a * first.radius * ux
                py = first.center[1] + sign_a * first.radius * uy
                if not first.contains_angle(
                        math.atan2(py - first.center[1], px - first.center[0])):
                    continue
                for sign_b in (-1.0, 1.0):
                    qx = second.center[0] + sign_b * second.radius * ux
                    qy = second.center[1] + sign_b * second.radius * uy
                    if second.contains_angle(
                            math.atan2(qy - second.center[1], qx - second.center[0])):
                        candidates.append((math.hypot(px - qx, py - qy),
                                           (px, py), (qx, qy)))
        else:
            for lo, hi in first.angular_intervals():
                for other_lo, other_hi in second.angular_intervals():
                    start = max(lo, other_lo)
                    end = min(hi, other_hi)
                    if end - start <= PAIR_EPS:
                        continue
                    angle = (start + end) / 2.0
                    on_first = (first.center[0] + first.radius * math.cos(angle),
                                first.center[1] + first.radius * math.sin(angle))
                    on_second = (second.center[0] + second.radius * math.cos(angle),
                                 second.center[1] + second.radius * math.sin(angle))
                    candidates.append((abs(first.radius - second.radius),
                                       on_first, on_second))
                    break
    return min(candidates, key=lambda item: item[0])


def _exact_policy_too_close(first, second, exempt_pairs, clearance):
    """Former quick-index policy: a crossing exempts its whole primitive pair.

    Used only for the optional sensitivity comparison (``--compare-exact``);
    the authoritative acceptance policy is the legacy local-window one.
    """
    limit2 = (clearance - PAIR_EPS) * (clearance - PAIR_EPS)
    for index_a, prim_a in enumerate(first.prims):
        box_a = prim_a.bbox
        for index_b, prim_b in enumerate(second.prims):
            if (index_a, index_b) in exempt_pairs:
                continue
            box_b = prim_b.bbox
            dx = box_a[0] - box_b[2]
            candidate = box_b[0] - box_a[2]
            if candidate > dx:
                dx = candidate
            if dx < 0.0:
                dx = 0.0
            dy = box_a[1] - box_b[3]
            candidate = box_b[1] - box_a[3]
            if candidate > dy:
                dy = candidate
            if dy < 0.0:
                dy = 0.0
            if dx * dx + dy * dy >= limit2:
                continue
            distance = _exact_distance(prim_a, prim_b,
                                       bbox_disjoint=(dx > 0.0 or dy > 0.0))
            if distance < clearance - PAIR_EPS:
                nearest = _nearest_points(prim_a, prim_b)
                return True, nearest[0], _midpoint(nearest[1], nearest[2])
    return False, None, None


# ---------------------------------------------------------------------------
# STRICT LOCAL-CROSSING-WINDOW POLICY (SPEC §2.1)
#
# The strict policy keeps the same overlap / tangency / double-crossing /
# overlapping-window rejections but replaces both historical exemptions by the
# exact minimal necessary region of each genuine transverse crossing:
#
# * the crossing point is the unique exact line/arc intersection of one
#   primitive pair (crossings at shared primitive junctions are de-duplicated
#   by position, exactly like the router index);
# * on each side of the crossing the point is followed along the *whole route*
#   (so a window may legitimately cross a primitive junction) and its distance
#   to the crossing partner *primitive* is solved to ``clearance``: ``h*`` is
#   the first arc length where that distance is at least ``clearance``; the
#   exempt half width is ``h* + 2*sagitta``;
# * if a side is still inside the clearance band at ``max_half_window`` the
#   "crossing" is two curves running together, not a crossing, and the pair is
#   rejected as ``crossing_window_excessive`` (a window that is merely clamped
#   by the route end is legal);
# * outside the local windows every primitive pair is checked with the exact
#   centerline distance, against the crossing partner only for the part of the
#   route that the window actually cuts out, with limit ``clearance - 1e-7``;
#   the check is performed in both directions (A outside vs B, B outside vs A).
# ---------------------------------------------------------------------------
def _route_point_at(prepared, s):
    """Point at arc length ``s`` along a whole prepared route (clamped)."""
    length = prepared.length
    if s <= 0.0:
        return prepared.prims[0].point(0.0)
    if s >= length:
        return prepared.prims[-1].point(1.0)
    offsets = prepared.offsets
    lo = 0
    hi = len(offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if offsets[mid] <= s:
            lo = mid
        else:
            hi = mid - 1
    prim = prepared.prims[lo]
    t = (s - offsets[lo]) / prim.length
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return prim.point(t)


def _is_axis_line(prim):
    """``True`` for an axis-aligned straight primitive (D56 legal line)."""
    if prim.kind != "line":
        return False
    return prim.p0[1] == prim.p1[1] or prim.p0[0] == prim.p1[0]


def _strict_band_edge(prepared, s0, direction, partner, guess, target,
                      max_half=STRICT_MAX_HALF_WINDOW):
    """Solve ``h*``: first arc length leaving the ``target`` band around ``partner``.

    Follows the *whole route* from arc length ``s0`` in ``direction`` (+1/-1)
    and returns the smallest ``h >= 0`` with ``dist(route(s0+dir*h), partner)
    >= target`` where ``target = clearance - 1e-7`` is the violation limit.
    ``None`` means the route is still inside the band of ``partner`` at
    ``max_half`` (``crossing_window_excessive``); when the route itself ends
    inside the band the edge is clamped to the route end (a legal crossing close
    to an endpoint) and that clamped value is returned.
    """
    length = prepared.length
    room = s0 if direction < 0.0 else length - s0
    if room <= 1e-12:
        return 0.0
    cap = max_half if room > max_half else room

    def band_distance(h):
        return _point_prim_distance(
            _route_point_at(prepared, s0 + direction * h), partner)

    # Geometric first probe: a straight transverse crossing leaves the band
    # after about limit/sin(angle); curvature can only move the edge further
    # out, which the expansion loop below covers.
    probe = guess * 1.2
    floor = 2.0 * SAGITTA + 1e-6
    if probe < floor:
        probe = floor
    if probe > cap:
        probe = cap
    lo = 0.0
    delta_lo = -target
    hi = None
    delta_hi = None
    while True:
        step = probe / STRICT_SAMPLES
        h = 0.0
        while h < probe - 1e-12:
            h += step
            if h > probe:
                h = probe
            delta = band_distance(h) - target
            if delta >= 0.0:
                hi = h
                delta_hi = delta
                break
            lo = h
            delta_lo = delta
        if hi is not None:
            break
        if probe >= cap - 1e-12:
            if room <= max_half + 1e-12:
                return cap  # the route itself ends inside the band
            return None  # still inside the band after the maximum window
        probe = cap if probe * 1.8 > cap else probe * 1.8
    # Illinois-style false position with a bisection safeguard; converges to
    # |hi - h*| <= STRICT_SEARCH_TOL.
    stalled_at_lo = False
    stalled_at_hi = False
    for _ in range(48):
        span = hi - lo
        if span <= STRICT_SEARCH_TOL:
            break
        denominator = delta_hi - delta_lo
        if denominator <= 1e-15:
            mid = 0.5 * (lo + hi)
        else:
            mid = lo + span * (-delta_lo) / denominator
            if mid <= lo + 0.2 * span or mid >= hi - 0.2 * span:
                mid = 0.5 * (lo + hi)
        delta = band_distance(mid) - target
        if delta >= 0.0:
            hi = mid
            delta_hi = delta
            if stalled_at_hi:
                delta_lo *= 0.5
            stalled_at_hi = True
            stalled_at_lo = False
        else:
            lo = mid
            delta_lo = delta
            if stalled_at_lo:
                delta_hi *= 0.5
            stalled_at_lo = True
            stalled_at_hi = False
    return hi


def _strict_outside_too_close(prepared, other, windows, limit):
    """Exact spacing outside the local windows, against the window's partners.

    ``windows`` is a list of ``(lo, hi, partners)`` entries (one per distinct
    crossing group) in ``prepared`` arc-length coordinates; ``partners`` is the
    set of crossing partner primitive indices of ``other``.  For each partner
    primitive the parts of ``prepared`` outside the windows of the groups that
    involve it are compared with exactly that partner; any approach below
    ``limit`` is a spacing violation.  Non-crossing primitive pairs are already
    fully checked elsewhere, so non-partner primitives are not rechecked.
    """
    offsets = prepared.offsets
    prims = prepared.prims
    length = prepared.length
    by_partner = {}
    for lo, hi, partners in windows:
        if lo < 0.0:
            lo = 0.0
        if hi > length:
            hi = length
        if hi <= lo:
            continue
        for partner_index in partners:
            by_partner.setdefault(partner_index, []).append((lo, hi))
    for partner_index, intervals in by_partner.items():
        theirs = other.prims[partner_index]
        theirs_box = theirs.bbox
        for index, prim in enumerate(prims):
            start = offsets[index]
            end = start + prim.length
            local = []
            for lo, hi in intervals:
                a = lo if lo > start else start
                b = hi if hi < end else end
                if b > a:
                    local.append(((a - start) / prim.length,
                                  (b - start) / prim.length))
            if not local:
                continue
            for t0, t1 in _complement_windows(local):
                if (t1 - t0) * prim.length <= PAIR_EPS:
                    continue
                piece = prim.clip(t0, t1)
                piece_box = piece.bbox
                dx = piece_box[0] - theirs_box[2]
                candidate = theirs_box[0] - piece_box[2]
                if candidate > dx:
                    dx = candidate
                if dx < 0.0:
                    dx = 0.0
                dy = piece_box[1] - theirs_box[3]
                candidate = theirs_box[1] - piece_box[3]
                if candidate > dy:
                    dy = candidate
                if dy < 0.0:
                    dy = 0.0
                if dx * dx + dy * dy >= limit * limit:
                    continue
                distance = _exact_distance(piece, theirs,
                                           bbox_disjoint=(dx > 0.0 or dy > 0.0))
                if distance < limit:
                    nearest = _nearest_points(piece, theirs)
                    return True, distance, _midpoint(nearest[1], nearest[2])
    return False, None, None


def _evaluate_pair_strict(first, second, clearance, sagitta):
    """Strict-policy audit of one route pair (see ``evaluate_pair``)."""
    if _bbox_distance(first.bbox, second.bbox) > clearance + 2.0 * sagitta:
        return None
    limit = clearance - STRICT_LIMIT_TOL
    margin = 2.0 * sagitta
    crossings = []
    overlap = False
    touch = False
    touch_kind = None
    double_cross = False
    overlap_point = None
    touch_point = None
    double_point = None
    spacing_bad = False
    spacing_distance = None
    spacing_point = None

    def note_spacing(prim_a, prim_b, distance):
        nonlocal spacing_bad, spacing_distance, spacing_point
        if spacing_bad:
            return
        spacing_bad = True
        spacing_distance = distance
        nearest = _nearest_points(prim_a, prim_b)
        spacing_point = _midpoint(nearest[1], nearest[2])

    for index_a, prim_a in enumerate(first.prims):
        bbox_a = prim_a.bbox
        for index_b, prim_b in enumerate(second.prims):
            bbox_b = prim_b.bbox
            box_gap = _bbox_distance(bbox_a, bbox_b)
            if not _bbox_overlap(bbox_a, bbox_b, INTERSECT_TOL):
                # bbox-disjoint: no intersection possible, exact distance only.
                if box_gap >= limit:
                    continue
                distance = _exact_distance(prim_a, prim_b, bbox_disjoint=True)
                if distance < limit:
                    note_spacing(prim_a, prim_b, distance)
                continue
            try:
                points, common = _geometry_intersections(
                    prim_a.raw, prim_b.raw, INTERSECT_TOL)
            except (ValueError, KeyError, TypeError, FloatingPointError):
                points, common = [], False
            if common:
                overlap = True
                if points and overlap_point is None:
                    overlap_point = (float(points[0][0]), float(points[0][1]))
                continue
            if len(points) > 1:
                double_cross = True
                if double_point is None:
                    double_point = (float(points[0][0]), float(points[0][1]))
                continue
            if not points:
                if box_gap >= limit:
                    continue
                distance = _exact_distance(prim_a, prim_b,
                                           bbox_disjoint=(box_gap > 0.0))
                if distance < limit:
                    note_spacing(prim_a, prim_b, distance)
                continue
            point = (float(points[0][0]), float(points[0][1]))
            t_a = prim_a.parameter(point)
            t_b = prim_b.parameter(point)
            tangent_a = prim_a.tangent(t_a)
            tangent_b = prim_b.tangent(t_b)
            sine = min(1.0, abs(_cross(tangent_a, tangent_b)))
            sa = first.offsets[index_a] + t_a * prim_a.length
            sb = second.offsets[index_b] + t_b * prim_b.length
            if sine < STRICT_SINE_MIN:
                touch = True
                if touch_kind is None:
                    touch_kind = "tangent_touch"
                if touch_point is None:
                    touch_point = point
                continue
            if min(sa, first.length - sa,
                   sb, second.length - sb) < ENDPOINT_TOUCH_TOL:
                touch = True
                if touch_kind is None:
                    touch_kind = "endpoint_touch"
                if touch_point is None:
                    touch_point = point
                continue
            straight = _is_axis_line(prim_a) and _is_axis_line(prim_b)
            crossings.append({"point": point, "sine": sine, "sa": sa, "sb": sb,
                              "index_a": index_a, "index_b": index_b,
                              "straight": straight})

    result = {"valid": False, "overlap": overlap, "touch": touch,
              "crossing_zone_overlap": False, "spacing": False,
              "double_cross": double_cross,
              "crossing_window_excessive": False,
              "crossings": crossings, "min_distance": None, "violations": []}
    if overlap:
        point = overlap_point if overlap_point is not None else _midpoint(
            first.prims[0].point(0.5), second.prims[0].point(0.5))
        result["violations"].append({"kind": "overlap", "distance_mm": None,
                                     "x": point[0], "y": point[1]})
    if double_cross:
        if double_point is None:
            double_point = _midpoint(first.prims[0].point(0.5),
                                     second.prims[0].point(0.5))
        result["violations"].append({"kind": "double_cross", "distance_mm": 0.0,
                                     "x": double_point[0], "y": double_point[1]})
    if touch:
        if touch_point is None:
            touch_point = _midpoint(first.prims[0].point(0.5),
                                    second.prims[0].point(0.5))
        result["violations"].append({"kind": touch_kind or "touch",
                                     "distance_mm": 0.0,
                                     "x": touch_point[0], "y": touch_point[1]})
    if spacing_bad:
        result["spacing"] = True
        result["violations"].append({"kind": "spacing",
                                     "distance_mm": spacing_distance,
                                     "x": spacing_point[0],
                                     "y": spacing_point[1]})
    if overlap or touch or double_cross:
        return result

    if not crossings:
        result["min_distance"] = _min_primitive_distance(
            first, second, clearance + 2.0 * sagitta)
        result["valid"] = not spacing_bad
        return result

    # ---- group crossings at (numerically) the same point ------------------
    # D56 commonly puts one route's line/arc junction exactly on the other
    # route's primitive; that is one physical crossing with one window.
    groups = []
    for record in crossings:
        point = record["point"]
        for group in groups:
            reference = group[0]["point"]
            if (abs(point[0] - reference[0]) < STRICT_GROUP_TOL
                    and abs(point[1] - reference[1]) < STRICT_GROUP_TOL):
                group.append(record)
                break
        else:
            groups.append([record])

    # ---- exact minimal crossing window per group --------------------------
    windows_a = []
    windows_b = []
    group_points = []
    group_windows = []
    excessive_point = None
    for group in groups:
        reference = group[0]
        sa = reference["sa"]
        sb = reference["sb"]
        ha_left = ha_right = hb_left = hb_right = None
        partners_b = set()
        partners_a = set()
        for record in group:
            partners_b.add(record["index_b"])
            partners_a.add(record["index_a"])
            if record["straight"]:
                # Two axis-aligned straight lines: dist = |delta s| exactly on
                # both curves (sine == 1), so the analytic half width is exact.
                half = clearance + margin
                candidate = (half, half, half, half)
            else:
                guess = limit / (record["sine"] if record["sine"] > 1e-3
                                 else 1e-3)
                partner_b = second.prims[record["index_b"]]
                partner_a = first.prims[record["index_a"]]
                e_left = _strict_band_edge(first, record["sa"], -1.0,
                                           partner_b, guess, limit)
                e_right = _strict_band_edge(first, record["sa"], 1.0,
                                            partner_b, guess, limit)
                f_left = _strict_band_edge(second, record["sb"], -1.0,
                                           partner_a, guess, limit)
                f_right = _strict_band_edge(second, record["sb"], 1.0,
                                            partner_a, guess, limit)
                if (e_left is None or e_right is None
                        or f_left is None or f_right is None):
                    excessive_point = record["point"]
                    break
                candidate = (e_left + margin, e_right + margin,
                             f_left + margin, f_right + margin)
            if ha_left is None or candidate[0] > ha_left:
                ha_left = candidate[0]
            if ha_right is None or candidate[1] > ha_right:
                ha_right = candidate[1]
            if hb_left is None or candidate[2] > hb_left:
                hb_left = candidate[2]
            if hb_right is None or candidate[3] > hb_right:
                hb_right = candidate[3]
        if excessive_point is not None:
            break
        group_windows.append((ha_left, ha_right, hb_left, hb_right))
        windows_a.append((sa - ha_left, sa + ha_right,
                          tuple(sorted(partners_b))))
        windows_b.append((sb - hb_left, sb + hb_right,
                          tuple(sorted(partners_a))))
        group_points.append(reference["point"])
    if excessive_point is not None:
        result["crossing_window_excessive"] = True
        result["violations"].append({"kind": "crossing_window_excessive",
                                     "distance_mm": None,
                                     "x": excessive_point[0],
                                     "y": excessive_point[1]})
        return result

    # Group-level crossing records (one physical crossing / one window each).
    result["crossings"] = []
    for index, group in enumerate(groups):
        reference = group[0]
        ha_left, ha_right, hb_left, hb_right = group_windows[index]
        result["crossings"].append({
            "point": reference["point"],
            "sine": min(1.0, reference["sine"]),
            "sa": reference["sa"],
            "sb": reference["sb"],
            "half_a_left": ha_left,
            "half_a_right": ha_right,
            "half_b_left": hb_left,
            "half_b_right": hb_right,
            "straight": all(record["straight"] for record in group),
            "members": [(record["index_a"], record["index_b"])
                        for record in group],
        })

    # ---- windows of the same route pair must not overlap (different groups) --
    overlap_pair = _overlapping_interval_pair(
        [(lo, hi) for lo, hi, _partners in windows_a]) or \
        _overlapping_interval_pair(
            [(lo, hi) for lo, hi, _partners in windows_b])
    if overlap_pair is not None:
        point = _midpoint(group_points[overlap_pair[0]],
                          group_points[overlap_pair[1]])
        result["crossing_zone_overlap"] = True
        result["violations"].append({"kind": "crossing_window_overlap",
                                     "distance_mm": 0.0,
                                     "x": point[0], "y": point[1]})
        return result

    # ---- exact spacing outside the local windows (both directions) --------
    # Orthogonal straight-line crossings need no outside check: the distance
    # along either curve is exactly |delta s|, so it is >= clearance outside the
    # analytic window by construction (SPEC §2.1 item 6).
    bad = False
    distance = None
    position = None
    if not all(record["straight"] for record in crossings):
        bad, distance, position = _strict_outside_too_close(
            first, second, windows_a, limit)
        if not bad:
            bad, distance, position = _strict_outside_too_close(
                second, first, windows_b, limit)
    result["spacing"] = bool(spacing_bad or bad)
    if bad:
        result["violations"].append({"kind": "spacing",
                                     "distance_mm": distance,
                                     "x": position[0], "y": position[1]})
    result["valid"] = not (overlap or touch or double_cross or spacing_bad or bad)
    return result


def evaluate_pair(first, second, clearance=CLEARANCE, sagitta=SAGITTA,
                  policy="legacy"):
    """Exact audit of one route pair; ``None`` when the pair cannot interact.

    Authoritative ``policy="legacy"`` mirrors ``four_side_1024/conflicts.py``:
    crossings are excused only inside ``clearance/sin(angle)+2*sagitta`` windows
    measured along both curves; overlap, tangency, overlapping windows and any
    outside-window approach below ``clearance`` (minus a 1e-8 numerical swath)
    are violations.

    ``policy="exact"`` is the former quick-index exemption used only for the
    optional sensitivity comparison: a primitive pair that genuinely intersects
    is fully exempt instead of locally windowed.

    ``policy="strict"`` (SPEC four_side_1024/abcd/SPEC.md §2.1) exempts exactly
    the minimal necessary near-region of each genuine transverse crossing,
    solved from the real line/arc geometry (see ``_evaluate_pair_strict``).
    """
    if _bbox_distance(first.bbox, second.bbox) > clearance + 2.0 * sagitta:
        return None
    if policy == "strict":
        return _evaluate_pair_strict(first, second, clearance, sagitta)
    crossings = []
    intersecting_pairs = set()
    overlap = False
    touch = False
    overlap_point = None
    touch_point = None
    for index_a, prim_a in enumerate(first.prims):
        for index_b, prim_b in enumerate(second.prims):
            if not _bbox_overlap(prim_a.bbox, prim_b.bbox, INTERSECT_TOL):
                continue
            try:
                points, common = _geometry_intersections(prim_a.raw, prim_b.raw,
                                                         INTERSECT_TOL)
            except (ValueError, KeyError, TypeError, FloatingPointError):
                points, common = [], False
            if common:
                overlap = True
                if points and overlap_point is None:
                    overlap_point = (float(points[0][0]), float(points[0][1]))
                # Router policy: a positive-length overlap is reported as an
                # overlap only; its endpoint pattern is not re-classified as a
                # tangency (matching conflicts.py, whose overlap branch returns
                # no intersection points).
                continue
            for point in points:
                intersecting_pairs.add((index_a, index_b))
                point = (float(point[0]), float(point[1]))
                if any(_dist(point, item["point"]) < CROSSING_DEDUPE
                       for item in crossings):
                    continue
                t_a = prim_a.parameter(point)
                t_b = prim_b.parameter(point)
                tangent_a = prim_a.tangent(t_a)
                tangent_b = prim_b.tangent(t_b)
                sine = min(1.0, abs(_cross(tangent_a, tangent_b)))
                sa = first.offsets[index_a] + t_a * prim_a.length
                sb = second.offsets[index_b] + t_b * prim_b.length
                is_endpoint = min(sa, first.length - sa,
                                  sb, second.length - sb) < ENDPOINT_TOUCH_TOL
                if sine < SINE_TOL or is_endpoint:
                    touch = True
                    if touch_point is None:
                        touch_point = point
                    continue
                crossings.append({"point": point, "sine": sine, "sa": sa, "sb": sb})
    result = {"valid": False, "overlap": overlap, "touch": touch,
              "crossing_zone_overlap": False, "spacing": False,
              "crossings": crossings, "min_distance": None,
              "violations": []}
    if overlap:
        point = overlap_point if overlap_point is not None else _midpoint(
            first.prims[0].point(0.5), second.prims[0].point(0.5))
        result["violations"].append({"kind": "overlap", "distance_mm": None,
                                     "x": point[0], "y": point[1]})
    if touch:
        point = touch_point if touch_point is not None else crossings[0]["point"]
        result["violations"].append({"kind": "touch", "distance_mm": 0.0,
                                     "x": point[0], "y": point[1]})
    if overlap or touch:
        return result

    if policy == "exact":
        bad, distance, position = _exact_policy_too_close(
            first, second, intersecting_pairs, clearance)
        result["spacing"] = bad
        if bad:
            result["violations"].append({"kind": "spacing",
                                         "distance_mm": distance,
                                         "x": position[0], "y": position[1]})
            result["min_distance"] = distance
        result["valid"] = not (overlap or touch or bad)
        return result

    intervals_a = []
    intervals_b = []
    for crossing in crossings:
        half = clearance / crossing["sine"] + 2.0 * sagitta
        crossing["half"] = half
        intervals_a.append((crossing["sa"] - half, crossing["sa"] + half))
        intervals_b.append((crossing["sb"] - half, crossing["sb"] + half))
    overlap_pair = _overlapping_interval_pair(intervals_a) or \
        _overlapping_interval_pair(intervals_b)
    if overlap_pair is not None:
        result["crossing_zone_overlap"] = True
        first_crossing = crossings[overlap_pair[0]]
        second_crossing = crossings[overlap_pair[1]]
        point = _midpoint(first_crossing["point"], second_crossing["point"])
        result["violations"].append({"kind": "crossing_window_overlap",
                                     "distance_mm": 0.0,
                                     "x": point[0], "y": point[1]})
        return result

    if not crossings:
        result["min_distance"] = _min_primitive_distance(
            first, second, clearance + 2.0 * sagitta)

    # Outside-window A against ALL of B; then, only if B participates in a
    # crossing and A was clean, outside-window B against ALL of A.  This is
    # exactly the router policy (cutting both first would wrongly excuse an
    # outside/inside near miss).
    bad, distance, position = _outside_pieces_too_close(
        first, intervals_a, second, clearance)
    if not bad and crossings:
        bad, distance, position = _outside_pieces_too_close(
            second, intervals_b, first, clearance)
    result["spacing"] = bad
    if bad:
        result["min_distance"] = distance
        result["violations"].append({"kind": "spacing",
                                     "distance_mm": distance,
                                     "x": position[0], "y": position[1]})
    result["valid"] = not (overlap or touch or bad)
    return result


def _overlapping_interval_pair(intervals):
    """Indices of two windows whose arc-length intervals overlap (or None)."""
    if len(intervals) < 2:
        return None
    order = sorted(range(len(intervals)), key=lambda index: intervals[index][0])
    for position in range(len(order) - 1):
        left = order[position]
        right = order[position + 1]
        if intervals[left][1] > intervals[right][0] + PAIR_EPS:
            return left, right
    return None


def _candidate_pairs(prepared, pad):
    """Broad phase: route pairs whose exact bounding boxes are within ``pad``."""
    if len(prepared) < 2:
        return []
    boxes = np.array([[route.bbox[0], route.bbox[1], route.bbox[2], route.bbox[3]]
                      for route in prepared], dtype=float)
    pairs = []
    for index in range(len(prepared) - 1):
        x0, y0, x1, y1 = boxes[index]
        rest = boxes[index + 1:]
        dx = np.maximum(rest[:, 0] - x1, x0 - rest[:, 2])
        np.maximum(dx, 0.0, out=dx)
        dy = np.maximum(rest[:, 1] - y1, y0 - rest[:, 3])
        np.maximum(dy, 0.0, out=dy)
        near = np.flatnonzero(np.hypot(dx, dy) <= pad)
        pairs.extend((index, index + 1 + int(offset)) for offset in near)
    return pairs


def _new_strict_window_stats():
    return {
        "count": 0,
        "sum_half_mm": 0.0,
        "max_half_mm": 0.0,
        "sum_total_mm": 0.0,
        "max_span_mm": 0.0,
        "histogram": OrderedDict((label, 0) for label, _, _ in STRICT_WINDOW_HIST_BINS),
        "by_angle_bin": OrderedDict(
            (label, {"crossings": 0, "sum_half_mm": 0.0, "max_half_mm": 0.0})
            for label, _, _ in HIST_BINS),
    }


def _accumulate_strict_windows(stats, result):
    """Fold one strict pair result's local crossing windows into aggregate stats."""
    for crossing in result.get("crossings") or ():
        halves = (crossing.get("half_a_left"), crossing.get("half_a_right"),
                  crossing.get("half_b_left"), crossing.get("half_b_right"))
        if any(value is None for value in halves):
            continue
        stats["count"] += 1
        for value in halves:
            stats["sum_half_mm"] += value
            if value > stats["max_half_mm"]:
                stats["max_half_mm"] = value
            for label, low, high in STRICT_WINDOW_HIST_BINS:
                if low <= value < high:
                    stats["histogram"][label] += 1
                    break
        span = max(halves[0] + halves[1], halves[2] + halves[3])
        total = halves[0] + halves[1] + halves[2] + halves[3]
        stats["sum_total_mm"] += total
        if span > stats["max_span_mm"]:
            stats["max_span_mm"] = span
        angle = math.degrees(math.asin(min(1.0, crossing["sine"])))
        for label, low, high in HIST_BINS:
            if low <= angle < high:
                bucket = stats["by_angle_bin"][label]
                bucket["crossings"] += 1
                bucket["sum_half_mm"] += sum(halves) / 4.0
                bucket["max_half_mm"] = max(bucket["max_half_mm"], max(halves))
                break


def audit_route_pairs(prepared, clearance=CLEARANCE, sagitta=SAGITTA,
                      policy="legacy"):
    """Exact pairwise audit of prepared routes.

    Returns aggregate counters, every crossing point (with its acute angle),
    every violating pair (with kind, distance and location) and the minimum
    non-crossing centerline distance among the broad-phase candidate pairs.
    The ``strict`` policy additionally reports the local crossing-window
    statistics (count, maximum / mean half width, length histogram, and the
    relation between the crossing angle and the solved window).
    """
    started = time.perf_counter()
    pairs = _candidate_pairs(prepared, clearance + 2.0 * sagitta)
    crossings = []
    violations = []
    crossing_pairs = 0
    min_non_crossing = None
    spacing_pairs = 0
    overlap_pairs = 0
    touch_pairs = 0
    zone_overlap_pairs = 0
    double_cross_pairs = 0
    excessive_pairs = 0
    window_stats = _new_strict_window_stats() if policy == "strict" else None
    for index_a, index_b in pairs:
        first, second = prepared[index_a], prepared[index_b]
        result = evaluate_pair(first, second, clearance, sagitta, policy)
        if result is None:
            continue
        if window_stats is not None:
            _accumulate_strict_windows(window_stats, result)
        if result["valid"]:
            if result["crossings"]:
                crossing_pairs += 1
                for crossing in result["crossings"]:
                    angle = math.degrees(math.asin(min(1.0, crossing["sine"])))
                    crossings.append({
                        "route_a": first.route_id,
                        "route_b": second.route_id,
                        "x": crossing["point"][0],
                        "y": crossing["point"][1],
                        "angle_deg": angle,
                    })
            elif result["min_distance"] is not None:
                if (min_non_crossing is None
                        or result["min_distance"] < min_non_crossing):
                    min_non_crossing = result["min_distance"]
        else:
            kinds = []
            if result["overlap"]:
                kinds.append("overlap")
                overlap_pairs += 1
            if result["touch"]:
                touch_kind = "touch"
                for detail in result.get("violations") or ():
                    if detail.get("kind") in ("tangent_touch", "endpoint_touch"):
                        touch_kind = detail["kind"]
                        break
                kinds.append(touch_kind)
                touch_pairs += 1
            if result.get("double_cross"):
                kinds.append("double_cross")
                double_cross_pairs += 1
            if result["crossing_zone_overlap"]:
                kinds.append("crossing_window_overlap")
                zone_overlap_pairs += 1
            if result.get("crossing_window_excessive"):
                kinds.append("crossing_window_excessive")
                excessive_pairs += 1
            if result["spacing"]:
                kinds.append("spacing")
                spacing_pairs += 1
            details = result.get("violations") or [
                {"kind": kind, "distance_mm": None,
                 "x": first.prims[0].point(0.5)[0],
                 "y": first.prims[0].point(0.5)[1]}
                for kind in kinds]
            for detail in details:
                violations.append({
                    "route_a": first.route_id,
                    "route_b": second.route_id,
                    "kind": detail["kind"],
                    "kinds": list(kinds),
                    "distance_mm": detail.get("distance_mm"),
                    "x": detail.get("x"),
                    "y": detail.get("y"),
                })
    histogram = OrderedDict((label, 0) for label, _, _ in HIST_BINS)
    small_angle = 0
    for crossing in crossings:
        angle = crossing["angle_deg"]
        if angle < CROSSING_SMALL_ANGLE_DEG:
            small_angle += 1
        for label, low, high in HIST_BINS:
            if low <= angle < high:
                histogram[label] += 1
                break
    if window_stats is not None:
        mean_half = (window_stats["sum_half_mm"] / (4.0 * window_stats["count"])
                     if window_stats["count"] else None)
        by_angle = OrderedDict()
        for label, bucket in window_stats["by_angle_bin"].items():
            count = bucket["crossings"]
            by_angle[label] = {
                "crossings": count,
                "mean_half_mm": (bucket["sum_half_mm"] / count) if count else None,
                "max_half_mm": bucket["max_half_mm"] if count else None,
            }
        window_report = {
            "crossing_window_count": window_stats["count"],
            "crossing_window_max_mm": (window_stats["max_half_mm"]
                                       if window_stats["count"] else None),
            "crossing_window_mean_mm": mean_half,
            "crossing_window_max_span_mm": (window_stats["max_span_mm"]
                                             if window_stats["count"] else None),
            "crossing_window_total_length_mean_mm": (
                window_stats["sum_total_mm"] / window_stats["count"]
                if window_stats["count"] else None),
            "crossing_window_half_histogram_mm": dict(window_stats["histogram"]),
            "crossing_window_by_angle_bin": by_angle,
        }
    else:
        window_report = {
            "crossing_window_count": None,
            "crossing_window_max_mm": None,
            "crossing_window_mean_mm": None,
            "crossing_window_max_span_mm": None,
            "crossing_window_total_length_mean_mm": None,
            "crossing_window_half_histogram_mm": None,
            "crossing_window_by_angle_bin": None,
        }
    report = {
        "policy": policy,
        "candidate_pair_count": len(pairs),
        "crossing_count": len(crossings),
        "crossing_pair_count": crossing_pairs,
        "crossings": crossings,
        "crossing_angle_histogram": dict(histogram),
        "small_angle_threshold_deg": CROSSING_SMALL_ANGLE_DEG,
        "small_angle_crossing_count": small_angle,
        "min_non_crossing_centerline_mm": min_non_crossing,
        "violations": violations,
        "violation_pair_count": len({(item["route_a"], item["route_b"])
                                     for item in violations}),
        "spacing_violation_pairs": spacing_pairs,
        "overlap_pairs": overlap_pairs,
        "touch_pairs": touch_pairs,
        "double_cross_pairs": (double_cross_pairs if policy == "strict" else None),
        "crossing_zone_overlap_pairs": zone_overlap_pairs,
        "crossing_window_overlap_pairs": zone_overlap_pairs,
        "crossing_window_excessive_pairs": (excessive_pairs
                                            if policy == "strict" else None),
        "runtime_seconds": time.perf_counter() - started,
    }
    report.update(window_report)
    return report


# ---------------------------------------------------------------------------
# ARTEFACT LOADING
# ---------------------------------------------------------------------------
def _normalise_status(record):
    status = record.get("status")
    if status is None:
        return "routed"
    text = str(status).strip().lower()
    if text in FAILED_STATUS:
        return "failed"
    if text in ROUTED_STATUS:
        return "routed"
    return "unknown"


def _route_endpoint_fields(record):
    source = (record.get("source_endpoint") or record.get("source")
              or record.get("from_endpoint"))
    target = (record.get("target_endpoint") or record.get("target")
              or record.get("to_endpoint"))
    return source, target


def _sibling_endpoint_map(routes_path):
    """Load route-id -> (source_endpoint, target_endpoint) from a sibling routes.json."""
    sibling = routes_path.parent / "routes.json"
    if not sibling.exists() or sibling.resolve() == routes_path.resolve():
        return {}
    try:
        payload = json.loads(sibling.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    records = payload.get("routes") if isinstance(payload, dict) else payload
    mapping = {}
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict) or "route_id" not in record:
                continue
            source, target = _route_endpoint_fields(record)
            if source or target:
                mapping[record["route_id"]] = (source, target)
    return mapping


def _payload_records(payload):
    """Normalise any accepted route payload shape to ``(records, meta)``.

    Accepted shapes: SPEC ``routes.json`` mapping with a ``routes`` list, a plain
    list of records, and checkpoint mappings that split routed/failed entries
    (``accepted``/``failed``, ``routed``/``failed``, ``succeeded``/``failures``).
    """
    if isinstance(payload, list):
        return payload, {}
    if not isinstance(payload, dict):
        raise ValueError("route payload is neither a list nor a mapping")
    if "routes" in payload:
        return payload["routes"], {key: value for key, value in payload.items()
                                   if key != "routes"}
    routed_key = next((key for key in ("accepted", "routed", "succeeded", "success")
                       if isinstance(payload.get(key), (list, dict))), None)
    failed_key = next((key for key in ("failed", "rejected", "failures")
                       if isinstance(payload.get(key), (list, dict))), None)
    if routed_key is None and failed_key is None:
        raise ValueError("payload has no 'routes'/'accepted'/'failed' entry")
    records = []
    for key, default_status in ((routed_key, "routed"), (failed_key, "failed")):
        if key is None:
            continue
        items = payload[key]
        if isinstance(items, dict):
            items = list(items.values())
        for item in items:
            if not isinstance(item, dict):
                continue
            record = dict(item)
            if not record.get("status"):
                record["status"] = default_status
            records.append(record)
    meta = {key: value for key, value in payload.items()
            if key not in (routed_key, failed_key)}
    return records, meta


def load_routes_file(routes_path):
    """Read SPEC or legacy routes JSON and normalise it to a records list.

    Accepted shapes: the SPEC ``routes.json`` mapping with a ``routes`` list,
    a legacy ``routes.json`` list, a legacy ``routes_geometry.json`` mapping
    whose records carry no endpoint identities (resolved from the sibling
    ``routes.json`` by route id), and an engine checkpoint mapping with
    ``accepted``/``failed`` partitions.
    """
    routes_path = Path(routes_path)
    payload = json.loads(routes_path.read_text(encoding="utf-8"))
    records, meta = _payload_records(payload)
    if not isinstance(records, list):
        raise ValueError(f"{routes_path}: 'routes' is not a list")
    sibling = _sibling_endpoint_map(routes_path)
    normalised = []
    for position, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise ValueError(f"{routes_path}: route #{position} is not an object")
        record = dict(raw)
        record.setdefault("route_id", position + 1)
        source, target = _route_endpoint_fields(record)
        if (source is None or target is None) and record["route_id"] in sibling:
            sibling_source, sibling_target = sibling[record["route_id"]]
            source = source if source is not None else sibling_source
            target = target if target is not None else sibling_target
        record["_source_endpoint"] = source
        record["_target_endpoint"] = target
        record["_status"] = _normalise_status(record)
        normalised.append(record)
    return normalised, {"path": str(routes_path), "count": len(normalised),
                        "meta": meta, "sibling_endpoint_map": len(sibling)}


def _default_endpoints():
    _, endpoints, _, _ = _load_inputs()
    return endpoints


# ---------------------------------------------------------------------------
# DATASET VALIDATION
# ---------------------------------------------------------------------------
def validate_dataset(records, endpoints, *, expected_route_count=None,
                     audit_pairs=True, policy="legacy", compare_exact=False,
                     clearance=CLEARANCE, sagitta=SAGITTA,
                     source_description="", run_dir=None):
    """Validate a whole routes dataset (SPEC routes.json or legacy artefact).

    ``policy`` is the pair-audit crossing policy: ``legacy`` (historical
    local-window approximation, authoritative for the historical D56 delivery),
    ``exact`` (whole-primitive-pair exemption, sensitivity only) or ``strict``
    (SPEC four_side_1024/abcd/SPEC.md §2.1 minimal local crossing windows).

    Returns the JSON-serialisable audit report documented in
    ``docs/reports/d56_validation_spec.md``.
    """
    if policy not in ("legacy", "exact", "strict"):
        raise ValueError(f"unknown crossing policy: {policy!r}")
    started = time.perf_counter()
    errors = []
    warnings = []
    route_errors = []
    seen_ids = set()
    route_count = len(records)
    routed_count = 0
    failed_count = 0
    d56_passed = 0
    d56_failed = 0
    endpoint_unchecked = 0
    checks_passed = OrderedDict((name, 0) for name in SINGLE_CHECK_NAMES)
    checks_total = OrderedDict((name, 0) for name in SINGLE_CHECK_NAMES)
    self_intersections = 0
    self_overlaps = 0
    self_spacing = 0
    radius_violations = 0
    boundary_violations = 0
    diagonal_segments = 0
    free_bend_violations = 0
    failed_status_records = []
    prepared = []

    for record in records:
        route_id = record.get("route_id")
        if route_id in seen_ids:
            errors.append(f"duplicate_route_id:{route_id}")
        seen_ids.add(route_id)
        status = record.get("_status", _normalise_status(record))
        if status == "failed":
            failed_count += 1
            failed_status_records.append(route_id)
            continue
        if status == "unknown":
            warnings.append(f"unknown_status:{route_id}:{record.get('status')}")
        routed_count += 1
        primitives = record.get("primitives")
        if not primitives:
            route_errors.append({"route_id": route_id,
                                 "errors": ["missing_primitives"]})
            d56_failed += 1
            continue
        source_id = record.get("_source_endpoint", record.get("source_endpoint"))
        target_id = record.get("_target_endpoint", record.get("target_endpoint"))
        source = endpoints.get(source_id) if source_id is not None else None
        target = endpoints.get(target_id) if target_id is not None else None
        if source is None or target is None:
            endpoint_unchecked += 1
            warnings.append(f"endpoint_mapping_missing:{route_id}:{source_id}:{target_id}")
        result = check_route_primitives(primitives, source, target)
        for name, passed in result["checks"].items():
            checks_total[name] += 1
            if passed:
                checks_passed[name] += 1
        for error in result["errors"]:
            if error.startswith("diagonal_line"):
                diagonal_segments += 1
            elif error.startswith(("arc_radius", "short_s", "d56_arc")):
                free_bend_violations += 1
            elif error.startswith("self_intersection"):
                self_intersections += 1
            elif error.startswith("self_overlap"):
                self_overlaps += 1
            elif error.startswith("self_spacing"):
                self_spacing += 1
            elif error.startswith("board_out_of_bounds"):
                boundary_violations += 1
        if error_is_radius(result["errors"]):
            radius_violations += 1
        if result["passed"]:
            d56_passed += 1
            if audit_pairs:
                try:
                    prepared.append(prepare_route(primitives, route_id))
                except _PrimitiveError as exc:  # pragma: no cover - defensive
                    d56_passed -= 1
                    d56_failed += 1
                    route_errors.append({"route_id": route_id,
                                         "errors": [f"pair_audit_prepare_failed:{exc}"]})
        else:
            d56_failed += 1
            route_errors.append({"route_id": route_id,
                                 "errors": list(result["errors"])})
    if expected_route_count is not None and route_count != expected_route_count:
        errors.append(f"route_count_mismatch:{route_count}!={expected_route_count}")
    if route_errors:
        errors.append(f"d56_route_errors:{len(route_errors)}")
    if failed_count == 0 and route_count and routed_count == route_count:
        warnings.append("no_failed_routes_reported")

    audit = None
    exact_audit = None
    if audit_pairs:
        audit = audit_route_pairs(prepared, clearance, sagitta, policy)
        if audit["violations"]:
            errors.append(f"inter_route_violations:{len(audit['violations'])}")
        audit.pop("crossings", None)
        audit["audited_route_count"] = len(prepared)
        if compare_exact and policy == "legacy":
            exact_audit = audit_route_pairs(prepared, clearance, sagitta, "exact")
            exact_audit.pop("crossings", None)
    checks = {name: checks_passed[name] for name in checks_passed}
    if policy == "strict":
        crossing_window_description = (
            "exact minimal local window: coincident crossing points are grouped; "
            "per crossing side h* solved so the real-geometry distance from the "
            "route point to the group's crossing partner primitive equals "
            "lim = clearance-1e-7 (|h-h*|<=1e-5); exempt half width = "
            "h* + 2*sagitta (group max); max_half_window = 4.0 mm -> "
            "crossing_window_excessive; orthogonal straight-line crossings use "
            "the analytic half = clearance+2*sagitta and need no outside check")
    else:
        crossing_window_description = \
            "clearance/sin(angle)+2*sagitta along BOTH curves"
    policy_block = {
        "board_mm": BOARD,
        "radius_mm": RADIUS,
        "radius_tolerance_mm": RADIUS_TOL,
        "waveguide_width_mm": WIDTH,
        "edge_gap_mm": EDGE_GAP,
        "centerline_clearance_mm": clearance,
        "sagitta_mm": sagitta,
        "orthogonality_tolerance_mm": ORTHO_TOL,
        "pose_tolerance_mm": POSE_TOL,
        "crossing_window": crossing_window_description,
        "crossing_small_angle_deg": CROSSING_SMALL_ANGLE_DEG,
        "crossing_histogram_bins_deg": [label for label, _, _ in HIST_BINS],
        "legend": "D56 = orthogonal lines + radius-5 quarter arcs + legacy short-S theta pairs",
    }
    if policy == "strict":
        policy_block.update({
            "centerline_clearance_limit_mm": clearance - STRICT_LIMIT_TOL,
            "crossing_min_angle_deg": 5.0,
            "crossing_max_half_window_mm": STRICT_MAX_HALF_WINDOW,
            "crossing_solve_tolerance_mm": STRICT_SOLVE_TOL,
            "crossing_group_tolerance_mm": STRICT_GROUP_TOL,
            "crossing_extra_margin_mm": 2.0 * sagitta,
        })
    report = {
        "passed": False,
        "validator": "four_side_1024.d56.validate_d56",
        "policy_used": policy,
        "policy": policy_block,
        "source": {"description": source_description, "run_dir": str(run_dir) if run_dir else None},
        "route_count": route_count,
        "routed_count": routed_count,
        "failed_status_count": failed_count,
        "failed_status_route_ids": failed_status_records,
        "d56_checked_count": routed_count,
        "d56_passed_count": d56_passed,
        "d56_failed_count": d56_failed,
        "endpoint_unchecked_count": endpoint_unchecked,
        "checks": checks,
        "checks_total": dict(checks_total),
        "self_intersections": self_intersections,
        "self_overlaps": self_overlaps,
        "self_spacing_violations": self_spacing,
        "radius_violations": radius_violations,
        "boundary_violations": boundary_violations,
        "diagonal_line_violations": diagonal_segments,
        "free_or_short_s_arc_violations": free_bend_violations,
        "errors": errors,
        "warnings": warnings,
        "route_errors": route_errors,
    }
    if audit is None:
        report.update({
            "pair_audit": "skipped",
            "crossing_count": None,
            "crossing_pair_count": None,
            "crossing_angle_histogram": None,
            "small_angle_threshold_deg": CROSSING_SMALL_ANGLE_DEG,
            "small_angle_crossing_count": None,
            "min_non_crossing_centerline_mm": None,
            "crossing_window_overlap_pairs": None,
            "double_cross_pairs": None,
            "crossing_window_count": None,
            "crossing_window_max_mm": None,
            "crossing_window_mean_mm": None,
            "crossing_window_max_span_mm": None,
            "crossing_window_total_length_mean_mm": None,
            "crossing_window_half_histogram_mm": None,
            "crossing_window_by_angle_bin": None,
            "crossing_window_excessive_pairs": None,
            "violations": [],
        })
    else:
        report.update({
            "pair_audit": "exact_independent",
            "pair_audited_route_count": audit["audited_route_count"],
            "candidate_pair_count": audit["candidate_pair_count"],
            "crossing_count": audit["crossing_count"],
            "crossing_pair_count": audit["crossing_pair_count"],
            "crossing_angle_histogram": audit["crossing_angle_histogram"],
            "small_angle_threshold_deg": audit["small_angle_threshold_deg"],
            "small_angle_crossing_count": audit["small_angle_crossing_count"],
            "min_non_crossing_centerline_mm": audit["min_non_crossing_centerline_mm"],
            "spacing_violation_pairs": audit["spacing_violation_pairs"],
            "overlap_pairs": audit["overlap_pairs"],
            "touch_pairs": audit["touch_pairs"],
            "double_cross_pairs": audit["double_cross_pairs"],
            "crossing_zone_overlap_pairs": audit["crossing_zone_overlap_pairs"],
            "crossing_window_overlap_pairs": audit["crossing_window_overlap_pairs"],
            "crossing_window_excessive_pairs": audit["crossing_window_excessive_pairs"],
            "crossing_window_count": audit["crossing_window_count"],
            "crossing_window_max_mm": audit["crossing_window_max_mm"],
            "crossing_window_mean_mm": audit["crossing_window_mean_mm"],
            "crossing_window_max_span_mm": audit["crossing_window_max_span_mm"],
            "crossing_window_total_length_mean_mm":
                audit["crossing_window_total_length_mean_mm"],
            "crossing_window_half_histogram_mm":
                audit["crossing_window_half_histogram_mm"],
            "crossing_window_by_angle_bin": audit["crossing_window_by_angle_bin"],
            "violation_pair_count": audit["violation_pair_count"],
            "violations": audit["violations"],
            "pair_audit_runtime_seconds": audit["runtime_seconds"],
        })
    if exact_audit is not None:
        report["exact_policy_violations"] = exact_audit["violations"]
        report["exact_policy_violation_count"] = len(exact_audit["violations"])
        report["exact_policy_spacing_violation_pairs"] = \
            exact_audit["spacing_violation_pairs"]
        report["exact_policy_note"] = (
            "sensitivity only: former quick-index semantics exempt a whole "
            "primitive pair when it intersects; the legacy local-window policy "
            "above is the authoritative acceptance criterion")
    report["passed"] = (not errors and d56_failed == 0
                        and endpoint_unchecked == 0)
    report["runtime_seconds"] = time.perf_counter() - started
    report["methods"] = [
        "independent D56 predicate re-implementation (no router validate call)",
        "independent exact line/arc parameterisation and G1 continuity",
        "independent legacy short-S theta-pair reconstruction and verification",
        "geometry.intersections used only as an exact analytic primitive",
        "exact analytic stroked bounds",
        "independent exact primitive distance + crossing-window policy audit",
        "strict policy: independent whole-route h* band-edge solve per crossing side",
        "strict policy: crossing-point grouping, group-partner outside-window exact check",
        "four_side_1024.conflicts never imported",
        "four_side_1024.d56.index (router implementation) never imported",
    ]
    return report


def error_is_radius(errors):
    return any(error.startswith("arc_radius") for error in errors)


# ---------------------------------------------------------------------------
# COMMAND LINE
# ---------------------------------------------------------------------------
def _structural_failure(errors):
    """Minimal report shape for unreadable artefacts (CLI never tracebacks)."""
    return {
        "passed": False,
        "validator": "four_side_1024.d56.validate_d56",
        "errors": list(errors),
        "route_count": 0,
        "routed_count": 0,
        "failed_status_count": 0,
        "d56_checked_count": 0,
        "d56_passed_count": 0,
        "d56_failed_count": 0,
        "checks": {},
        "checks_total": {},
        "violations": [],
        "route_errors": [],
        "crossing_count": None,
        "crossing_pair_count": None,
        "crossing_angle_histogram": None,
        "small_angle_crossing_count": None,
        "min_non_crossing_centerline_mm": None,
        "warnings": [],
    }


def build_report(routes_path=None, run_dir=None, *, audit_pairs=True,
                 expected_route_count=None, policy="legacy",
                 compare_exact=False):
    """Load a saved artefact, attach endpoint identities and validate it."""
    if routes_path is None:
        if run_dir is None:
            raise ValueError("Either routes_path or run_dir is required")
        routes_path = Path(run_dir) / "routes.json"
    routes_path = Path(routes_path)
    if not routes_path.exists():
        return _structural_failure([f"routes_file_missing:{routes_path}"])
    try:
        records, info = load_routes_file(routes_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _structural_failure([f"routes_file_invalid:{routes_path}:{exc}"])
    endpoints = _default_endpoints()
    return validate_dataset(
        records, endpoints,
        expected_route_count=expected_route_count,
        audit_pairs=audit_pairs,
        policy=policy,
        compare_exact=compare_exact,
        source_description=info["path"], run_dir=run_dir)


def _write_crossings_csv(path, routes_path, run_dir):
    """Optional detailed crossing dump (re-runs the audit)."""
    if routes_path is None:
        routes_path = Path(run_dir) / "routes.json"
    records, _ = load_routes_file(routes_path)
    endpoints = _default_endpoints()
    prepared = []
    for record in records:
        if record["_status"] != "routed":
            continue
        source = endpoints.get(record.get("_source_endpoint"))
        target = endpoints.get(record.get("_target_endpoint"))
        result = check_route_primitives(record.get("primitives"), source, target)
        if result["passed"]:
            prepared.append(prepare_route(record["primitives"], record["route_id"]))
    audit = audit_route_pairs(prepared)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("route_a,route_b,x_mm,y_mm,angle_deg\n")
        for crossing in audit["crossings"]:
            handle.write(f"{crossing['route_a']},{crossing['route_b']},"
                         f"{crossing['x']:.9f},{crossing['y']:.9f},"
                         f"{crossing['angle_deg']:.9f}\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Independent D56 geometric validator (SPEC four_side_1024/d56/SPEC.md)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-dir", type=Path,
                       help="run directory containing routes.json "
                            "(e.g. outputs/four_side_1024_d56_optimized)")
    group.add_argument("--routes", type=Path,
                       help="alternate routes JSON (SPEC routes.json, legacy "
                            "routes.json or legacy routes_geometry.json)")
    parser.add_argument("--output", type=Path, default=None,
                        help="write the full JSON report to this path")
    parser.add_argument("--write-crossings", type=Path, default=None,
                        help="optional CSV dump of every exact crossing")
    parser.add_argument("--no-pair-audit", action="store_true",
                        help="only run single-route D56 checks")
    parser.add_argument("--expect-route-count", type=int, default=None,
                        help="require this many route records in the artefact")
    parser.add_argument("--policy", choices=("legacy", "exact", "strict"),
                        default="legacy",
                        help="pair-audit exemption policy: 'legacy' (default, "
                             "historical conflicts.py local-window approximation), "
                             "'exact' (former quick-index whole-primitive-pair "
                             "exemption, sensitivity only) or 'strict' (SPEC "
                             "abcd/SPEC.md §2.1 exact minimal local crossing "
                             "windows, the Phase-2 acceptance policy)")
    parser.add_argument("--compare-exact", action="store_true",
                        help="also compute exact-policy sensitivity violations "
                             "as exact_policy_violations (legacy stays authoritative)")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    expected = args.expect_route_count
    if args.run_dir is not None and expected is None:
        expected = 1024
    report = build_report(routes_path=args.routes,
                          run_dir=args.run_dir,
                          audit_pairs=not args.no_pair_audit,
                          expected_route_count=expected,
                          policy=args.policy,
                          compare_exact=args.compare_exact)
    report["command_runtime_seconds"] = time.perf_counter() - started
    if args.output is not None:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    if args.write_crossings is not None:
        _write_crossings_csv(args.write_crossings, args.routes, args.run_dir)
    summary = {
        "passed": report.get("passed"),
        "route_count": report.get("route_count"),
        "routed_count": report.get("routed_count"),
        "failed_status_count": report.get("failed_status_count"),
        "d56_passed_count": report.get("d56_passed_count"),
        "d56_failed_count": report.get("d56_failed_count"),
        "crossing_count": report.get("crossing_count"),
        "crossing_angle_histogram": report.get("crossing_angle_histogram"),
        "small_angle_crossing_count": report.get("small_angle_crossing_count"),
        "min_non_crossing_centerline_mm": report.get("min_non_crossing_centerline_mm"),
        "policy_used": report.get("policy_used"),
        "spacing_violation_pairs": report.get("spacing_violation_pairs"),
        "overlap_pairs": report.get("overlap_pairs"),
        "touch_pairs": report.get("touch_pairs"),
        "crossing_window_overlap_pairs": report.get("crossing_window_overlap_pairs"),
        "double_cross_pairs": report.get("double_cross_pairs"),
        "crossing_window_excessive_pairs": report.get("crossing_window_excessive_pairs"),
        "crossing_window_count": report.get("crossing_window_count"),
        "crossing_window_max_mm": report.get("crossing_window_max_mm"),
        "crossing_window_mean_mm": report.get("crossing_window_mean_mm"),
        "crossing_window_total_length_mean_mm":
            report.get("crossing_window_total_length_mean_mm"),
        "violations": len(report.get("violations") or []),
        "exact_policy_violation_count": report.get("exact_policy_violation_count"),
        "errors": report.get("errors"),
        "runtime_seconds": report.get("runtime_seconds"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
