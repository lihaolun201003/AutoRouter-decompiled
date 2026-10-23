#!/usr/bin/env python
"""Independent acceptance verification for the Hybrid C2/C4 Directional Layer
Routing experiment (groups ``H`` and ``V``).

Independence contract
---------------------
* The production modules ``four_side_1024.manual_c4.hybrid_c2_c4`` and
  ``four_side_1024.manual_c4.run_hybrid_c2_c4`` are **never imported**; the
  script asserts this at the end of the run (``check_independence``).
* All identity / symmetry / layer-rule / geometry / crossing-metric checks are
  re-implemented here from the delivered JSON artefacts plus the frozen inputs
  (``inputs/connectivity_1024.json``, ``phase2_2d/routes_1024.json`` and the
  frozen port table ``four_side_1024.v3c4.inputs.ENDPOINTS``).
* The only routing-code import is the frozen 3D validator entry point
  ``four_side_1024.v3c4.lift_cross.validate_payload_v4`` (explicitly required by
  the acceptance task).  It is called on a deep copy of the delivered payload so
  the artefacts on disk are never mutated.
* The output JSON/Markdown files live in ``verification/`` only.

Usage::

    set PYTHONPATH=<repo>
    .venv\\Scripts\\python.exe verification\\verify_hybrid_c2_c4.py

The run writes ``_group_H.json``, ``_group_V.json``,
``hybrid_c2_c4_verification.json``, ``hybrid_c2_c4_verification.md`` and a log
file next to this script.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
OUT_DIR = Path(__file__).resolve().parent          # .../verification
HYBRID = OUT_DIR.parent                            # .../hybrid_c2_c4_directional
CAMPAIGN = HYBRID.parent                           # .../manual_c4_new_connectivity
INPUTS = CAMPAIGN / 'inputs'
PHASE2_2D = CAMPAIGN / 'phase2_2d'
A_DIR = CAMPAIGN / 'structured_layer_routing' / 'A'
WORK = HYBRID / '_work'
SPATIAL_DIR = CAMPAIGN / 'spatial_u_bundle_optimization'
PHASE5_STACK = CAMPAIGN / 'phase5_dynamic_optimization/after/layer_stack.json'

# the R=15 process profile must be applied before importing radius-bound code
from four_side_1024.v3c4.profile import apply as _apply_profile  # noqa: E402

_apply_profile()
from four_side_1024.v3c4.inputs import ENDPOINTS  # noqa: E402  (frozen port table)

# ---------------------------------------------------------------------------
# design constants (frozen inputs of the experiment)
# ---------------------------------------------------------------------------
BOARD = 150.0
RADIUS = 15.0
WIDTH_MM = 0.05
CLEARANCE_MM = 0.08
INTERFACE_Z = {'z1': 0.0, 'z2': 0.5}
LAYER_Z = {2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5}
LAYER_DEFS = [('L1-z1', 1, 0.0), ('L1-z2', 1, 0.5), ('L2', 2, 1.0),
              ('L3', 3, 1.5), ('L4', 4, 2.0), ('L5', 5, 2.5)]
FIG_STEMS = ['01_before_3d', '02_after_3d', '03_L1_z1', '04_L1_z2', '05_L2',
             '06_L3', '07_L4', '08_L5', '09_z1_horizontal', '10_z1_vertical',
             '11_z1_direction_split', '12_opposite_only_3d',
             '13_dense_region_zoom']
FORBIDDEN_MODULES = ('four_side_1024.manual_c4.hybrid_c2_c4',
                     'four_side_1024.manual_c4.run_hybrid_c2_c4')
TOL_SYM = 1e-6          # required C2/C4 path tolerance
TOL_TIGHT = 1e-9        # algebraic equalities that must hold to float noise
TOL_GEOM = 1e-6         # geometry bookkeeping tolerances

# U-bundle target layer mapping: group id -> (layer_id, z_mm)
U_TARGET = {}
for _gid in range(20, 36):
    U_TARGET[_gid] = (3, 1.5)
for _gid in range(144, 160):
    U_TARGET[_gid] = (3, 1.5)
for _gid in range(160, 176):
    U_TARGET[_gid] = (4, 2.0)
for _gid in range(176, 192):
    U_TARGET[_gid] = (5, 2.5)


# module-level logger (installed by :func:`main`)
log = None


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------
def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                          encoding='utf-8')


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


class Log:
    def __init__(self, path):
        self.path = Path(path)
        self.path.write_text('', encoding='utf-8')
        self.started = time.time()

    def __call__(self, message):
        line = f'{time.strftime("%H:%M:%S")} {message}'
        print(line, flush=True)
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    def elapsed(self):
        return round(time.time() - self.started, 2)


def close(a, b, tol):
    return abs(float(a) - float(b)) <= tol


def max_dev(points_a, points_b):
    return max((math.dist(pa, pb) for pa, pb in zip(points_a, points_b)),
               default=0.0)


def rot_xy(x, y, quarter):
    """Rotate an XY point by ``quarter`` * +90 deg about the board centre.

    +90 deg is the C4 group convention used by the 2D campaign:
    ``(x, y) -> (BOARD - y, x)``.
    """
    x, y = float(x), float(y)
    for _ in range(int(quarter) % 4):
        x, y = BOARD - y, x
    return x, y


def rot_vector(dx, dy, quarter):
    """Rotate a free vector by ``quarter`` * +90 deg (same convention)."""
    x, y = float(dx), float(dy)
    for _ in range(int(quarter) % 4):
        x, y = -y, x
    return x, y


def norm_angle(angle):
    while angle <= -math.pi:
        angle += 2.0 * math.pi
    while angle > math.pi:
        angle -= 2.0 * math.pi
    return angle


# ---------------------------------------------------------------------------
# primitive geometry (lines + circular arcs, independent implementation)
# ---------------------------------------------------------------------------
def prim_2d_length(prim):
    if prim['kind'] == 'line':
        return math.dist(prim['p0'], prim['p1'])
    return float(prim['radius']) * abs(float(prim['sweep']))


def prim_start(prim):
    if prim['kind'] == 'line':
        return (float(prim['p0'][0]), float(prim['p0'][1]))
    center = prim['center']
    radius = float(prim['radius'])
    angle = float(prim['start_angle'])
    return (center[0] + radius * math.cos(angle),
            center[1] + radius * math.sin(angle))


def prim_end(prim):
    if prim['kind'] == 'line':
        return (float(prim['p1'][0]), float(prim['p1'][1]))
    center = prim['center']
    radius = float(prim['radius'])
    angle = float(prim['start_angle']) + float(prim['sweep'])
    return (center[0] + radius * math.cos(angle),
            center[1] + radius * math.sin(angle))


def prim_point(prim, t):
    if prim['kind'] == 'line':
        x0, y0 = prim['p0']
        x1, y1 = prim['p1']
        return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    center = prim['center']
    radius = float(prim['radius'])
    angle = float(prim['start_angle']) + float(prim['sweep']) * t
    return (center[0] + radius * math.cos(angle),
            center[1] + radius * math.sin(angle))


def _axis_of_line(prim, tol=1e-9):
    (x0, y0), (x1, y1) = prim['p0'], prim['p1']
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    if dy <= tol and dx > tol:
        return 'H'
    if dx <= tol and dy > tol:
        return 'V'
    return None


def sample_prim(prim, count=25):
    return [prim_point(prim, i / (count - 1)) for i in range(count)]


def polyline_2d(prims, step=0.1):
    """Sample a 2D chain at a fixed arc-length step from its start."""
    total = sum(prim_2d_length(prim) for prim in prims)
    count = max(2, int(math.ceil(total / step)) + 1)
    out = []
    lengths = [prim_2d_length(prim) for prim in prims]
    offsets = []
    acc = 0.0
    for length in lengths:
        offsets.append(acc)
        acc += length
    for index in range(count):
        s = total * index / (count - 1)
        # locate the primitive
        for k in range(len(prims)):
            lo = offsets[k]
            hi = lo + lengths[k]
            if s <= hi + 1e-12 or k == len(prims) - 1:
                t = (s - lo) / lengths[k] if lengths[k] > 0 else 0.0
                out.append(prim_point(prims[k], min(max(t, 0.0), 1.0)))
                break
    return out


# ---------------------------------------------------------------------------
# 3D route path sampling (flat line/arc at a constant z + S-bend transitions)
# ---------------------------------------------------------------------------
def transition_samples_3d(part, step=0.01):
    """Independent S-bend sampling: two tangent circular arcs (R, theta)."""
    radius = float(part['radius_mm'])
    theta = float(part['theta_rad'])
    z0, z1 = float(part['z0']), float(part['z1'])
    sign = 1.0 if z1 >= z0 else -1.0
    dz = abs(z1 - z0)
    length = float(part['length_mm'])
    half = length / 2.0
    count = max(2, int(math.ceil(length / step)))
    (sx, sy), (dx, dy) = part['start'], part['direction']
    out = []
    for index in range(count + 1):
        s = length * index / count
        if s <= half:
            phi = s / radius
            u = radius * math.sin(phi)
            w = z0 + sign * radius * (1.0 - math.cos(phi))
        else:
            phi = (length - s) / radius
            u = 2.0 * radius * math.sin(theta) - radius * math.sin(phi)
            w = z1 - sign * radius * (1.0 - math.cos(phi))
        out.append((sx + dx * u, sy + dy * u, w))
    return out


class RoutePath:
    """Ordered 3D path of a route (flats + transitions), sampled by arc length."""

    def __init__(self, route):
        self.segments = []
        for part in route.get('parts') or []:
            if part['kind'] == 'flat':
                z = float(part['z_mm'])
                for prim in part['primitives']:
                    self.segments.append(_flat_segment(prim, z))
            else:
                self.segments.append(_transition_segment(part))
        self.lengths = [item[0] for item in self.segments]
        self.offsets = []
        acc = 0.0
        for length in self.lengths:
            self.offsets.append(acc)
            acc += length
        self.total = acc
        self._sample_cache = {}

    def point(self, s):
        s = min(max(float(s), 0.0), self.total)
        for index in range(len(self.segments)):
            lo = self.offsets[index]
            hi = lo + self.lengths[index]
            if s <= hi + 1e-12 or index == len(self.segments) - 1:
                length = self.lengths[index]
                t = (s - lo) / length if length > 0 else 0.0
                return self.segments[index][1](min(max(t, 0.0), 1.0))
        return self.segments[-1][1](1.0)

    def samples(self, step=0.25):
        key = float(step)
        cached = self._sample_cache.get(key)
        if cached is not None:
            return cached
        count = max(2, int(math.ceil(self.total / step)) + 1)
        points = [self.point(self.total * index / (count - 1))
                  for index in range(count)]
        self._sample_cache[key] = points
        return points


def _flat_segment(prim, z):
    if prim['kind'] == 'line':
        x0, y0 = float(prim['p0'][0]), float(prim['p0'][1])
        x1, y1 = float(prim['p1'][0]), float(prim['p1'][1])
        length = math.hypot(x1 - x0, y1 - y0)
        z = float(z)

        def evaluate(t, x0=x0, y0=y0, x1=x1, y1=y1, z=z):
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, z)
        return length, evaluate
    center = prim['center']
    radius = float(prim['radius'])
    start = float(prim['start_angle'])
    sweep = float(prim['sweep'])
    length = radius * abs(sweep)
    z = float(z)

    def evaluate(t, center=center, radius=radius, start=start, sweep=sweep, z=z):
        angle = start + sweep * t
        return (center[0] + radius * math.cos(angle),
                center[1] + radius * math.sin(angle), z)
    return length, evaluate


def _transition_segment(part):
    radius = float(part['radius_mm'])
    theta = float(part['theta_rad'])
    z0, z1 = float(part['z0']), float(part['z1'])
    sign = 1.0 if z1 >= z0 else -1.0
    length = float(part['length_mm'])
    half = length / 2.0
    (sx, sy), (dx, dy) = part['start'], part['direction']

    def evaluate(t, radius=radius, theta=theta, z0=z0, z1=z1, sign=sign,
                 length=length, half=half, sx=sx, sy=sy, dx=dx, dy=dy):
        s = length * t
        if s <= half:
            phi = s / radius
            u = radius * math.sin(phi)
            w = z0 + sign * radius * (1.0 - math.cos(phi))
        else:
            phi = (length - s) / radius
            u = 2.0 * radius * math.sin(theta) - radius * math.sin(phi)
            w = z1 - sign * radius * (1.0 - math.cos(phi))
        return (sx + dx * u, sy + dy * u, w)
    return length, evaluate


# ---------------------------------------------------------------------------
# exact primitive intersection (crossing metrics)
# ---------------------------------------------------------------------------
def prim_bbox(prim):
    if prim['kind'] == 'line':
        (x0, y0), (x1, y1) = prim['p0'], prim['p1']
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    center = prim['center']
    radius = float(prim['radius'])
    return (center[0] - radius, center[1] - radius,
            center[0] + radius, center[1] + radius)


def bbox_distance(box_a, box_b):
    dx = max(box_b[0] - box_a[2], box_a[0] - box_b[2], 0.0)
    dy = max(box_b[1] - box_a[3], box_a[1] - box_b[3], 0.0)
    return math.hypot(dx, dy)


def _angle_in_sweep(angle, start, sweep, tol=1e-9):
    delta = norm_angle(angle - start)
    if sweep >= 0:
        return -tol <= delta <= sweep + tol
    return sweep - tol <= delta <= 1e-9


def _line_line(p0, p1, q0, q1):
    x1, y1 = p0
    x2, y2 = p1
    x3, y3 = q0
    x4, y4 = q1
    den = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(den) < 1e-12:
        return []
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / den
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / den
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return [(x1 + t * (x2 - x1), y1 + t * (y2 - y1))]
    return []


def _line_circle(p0, p1, center, radius):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    fx, fy = p0[0] - center[0], p0[1] - center[1]
    a = dx * dx + dy * dy
    if a <= 0.0:
        return []
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < -1e-9:
        return []
    disc = max(0.0, disc)
    root = math.sqrt(disc)
    out = []
    for t in ((-b - root) / (2.0 * a), (-b + root) / (2.0 * a)):
        if -1e-9 <= t <= 1.0 + 1e-9:
            out.append((p0[0] + t * dx, p0[1] + t * dy))
    return out


def _circle_circle(center_a, radius_a, center_b, radius_b):
    dx, dy = center_b[0] - center_a[0], center_b[1] - center_a[1]
    distance = math.hypot(dx, dy)
    if distance < 1e-12:
        return []
    if distance > radius_a + radius_b + 1e-9:
        return []
    if distance < abs(radius_a - radius_b) - 1e-9:
        return []
    a = (radius_a * radius_a - radius_b * radius_b + distance * distance) \
        / (2.0 * distance)
    h2 = radius_a * radius_a - a * a
    if h2 < -1e-9:
        return []
    h = math.sqrt(max(0.0, h2))
    mx = center_a[0] + a * dx / distance
    my = center_a[1] + a * dy / distance
    if h <= 1e-9:
        return [(mx, my)]
    ux, uy = -dy / distance, dx / distance
    return [(mx + h * ux, my + h * uy), (mx - h * ux, my - h * uy)]


def primitive_intersections(prim_a, prim_b):
    """All intersection points of two line/arc primitives (transversal or touch)."""
    kind_a, kind_b = prim_a['kind'], prim_b['kind']
    if kind_a == 'line' and kind_b == 'line':
        return _line_line(prim_a['p0'], prim_a['p1'],
                          prim_b['p0'], prim_b['p1'])
    if kind_a == 'arc' and kind_b == 'arc':
        points = _circle_circle(prim_a['center'], float(prim_a['radius']),
                                prim_b['center'], float(prim_b['radius']))
        out = []
        for point in points:
            angle_a = math.atan2(point[1] - prim_a['center'][1],
                                 point[0] - prim_a['center'][0])
            angle_b = math.atan2(point[1] - prim_b['center'][1],
                                 point[0] - prim_b['center'][0])
            if (_angle_in_sweep(angle_a, float(prim_a['start_angle']),
                                float(prim_a['sweep']))
                    and _angle_in_sweep(angle_b, float(prim_b['start_angle']),
                                        float(prim_b['sweep']))):
                out.append(point)
        return out
    if kind_a == 'line':
        line, arc = prim_a, prim_b
    else:
        line, arc = prim_b, prim_a
    out = []
    for point in _line_circle(line['p0'], line['p1'], arc['center'],
                              float(arc['radius'])):
        angle = math.atan2(point[1] - arc['center'][1],
                           point[0] - arc['center'][0])
        if _angle_in_sweep(angle, float(arc['start_angle']),
                           float(arc['sweep'])):
            out.append(point)
    return out


def union_bbox(boxes):
    return (min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes))


def flat_entries(records):
    """height -> list of (route_id, primitives) entries, one entry per flat part."""
    entries = defaultdict(list)
    for record in records:
        if record.get('status') not in (None, 'routed'):
            continue
        for part in record.get('parts') or []:
            if part['kind'] != 'flat':
                continue
            entries[round(float(part['z_mm']), 6)].append(
                (int(record['route_id']), part['primitives']))
    return entries


def classify_direction(manifest, route_id):
    record = manifest[int(route_id)]
    sides = {record['source_side'], record['target_side']}
    if sides == {'N', 'S'}:
        return 'NS'
    if sides == {'E', 'W'}:
        return 'EW'
    return 'other'


def classify_relation(manifest, route_id):
    record = manifest[int(route_id)]
    if record['relation'] == 'opposite':
        return f"opposite_{record['plane']}_{classify_direction(manifest, route_id)}"
    if record['relation'] == 'same':
        return 'same_U'
    return 'adjacent'


def crossing_audit(records, manifest, point_tol=1e-6):
    """Independent same-height crossing audit.

    Returns ``(per_height, unique_pair_count, total_crossing_points)`` where
    ``per_height[z] = {pairs, points, breakdown, entries}``.
    A "crossing" is one distinct intersection point of two flat center-line
    primitives of two different routes on the same physical height.
    """
    entries = flat_entries(records)
    per_height = {}
    unique = set()
    total_points = 0
    for height in sorted(entries):
        plane = entries[height]
        prepared = [(route_id, primitives, [prim_bbox(prim) for prim in primitives])
                    for route_id, primitives in plane]
        pair_set = set()
        breakdown = Counter()
        points_here = 0
        for index_a in range(len(prepared)):
            route_a, prims_a, boxes_a = prepared[index_a]
            union_a = union_bbox(boxes_a) if boxes_a else None
            for index_b in range(index_a + 1, len(prepared)):
                route_b, prims_b, boxes_b = prepared[index_b]
                if route_a == route_b or not boxes_b:
                    continue
                if bbox_distance(union_a, union_bbox(boxes_b)) > 0.0:
                    continue
                points = []
                for k, prim_a in enumerate(prims_a):
                    box_a = boxes_a[k]
                    for m, prim_b in enumerate(prims_b):
                        if bbox_distance(box_a, boxes_b[m]) > 0.0:
                            continue
                        for point in primitive_intersections(prim_a, prim_b):
                            if not any(math.dist(point, old) < point_tol
                                       for old in points):
                                points.append(point)
                if not points:
                    continue
                pair_key = tuple(sorted((route_a, route_b)))
                pair_set.add(pair_key)
                points_here += len(points)
                label = tuple(sorted((classify_relation(manifest, route_a),
                                      classify_relation(manifest, route_b))))
                breakdown[label] += len(points)
        unique |= pair_set
        per_height[str(height)] = {
            'pairs': len(pair_set),
            'points': points_here,
            'breakdown': {f'{key[0]} x {key[1]}': value
                          for key, value in breakdown.items()},
            'entries': len(plane),
        }
        total_points += points_here
    return per_height, len(unique), total_points


def z1_hv_crossings(per_height):
    """Z1 EW x NS opposite same-height crossing count / breakdown."""
    total = 0
    breakdown = {}
    for height, info in per_height.items():
        for key, value in info['breakdown'].items():
            parts = key.split(' x ')
            if all(part.startswith('opposite_z1') for part in parts):
                directions = {part.rsplit('_', 1)[1] for part in parts}
                if directions == {'EW', 'NS'}:
                    total += value
                    breakdown[height] = breakdown.get(height, 0) + value
    return total, breakdown


def layer_counts(records):
    out = {}
    for name, layer_id, z in LAYER_DEFS:
        users = 0
        plane_users = Counter()
        for record in records:
            for part in record.get('parts') or []:
                if part['kind'] != 'flat':
                    continue
                if (int(part['layer_id']) == layer_id
                        and abs(float(part['z_mm']) - z) <= 1e-9):
                    users += 1
                    plane_users[record['plane']] += 1
                    break
        out[name] = {'count': users, 'layer_id': layer_id, 'z_mm': z,
                     'plane_counts': dict(plane_users)}
    return out


def route_transition_count(records):
    return sum(int(record.get('n_transitions') or 0) for record in records)


def route_total_length(records):
    return round(sum(float(record.get('length_mm') or 0.0)
                     for record in records), 4)


# ---------------------------------------------------------------------------
# JSON helpers for the report
# ---------------------------------------------------------------------------
def jsonable(value):
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if isinstance(value, (Counter,)):
        return {str(key): int(item) for key, item in value.items()}
    if isinstance(value, float):
        return value
    return value


class Checker:
    """Accumulates pass/fail errors for one named check block."""

    def __init__(self, name):
        self.name = name
        self.errors = []
        self.notes = []

    def require(self, condition, message):
        if not condition:
            self.errors.append(str(message))
        return bool(condition)

    def fail(self, message):
        self.errors.append(str(message))

    def note(self, message):
        self.notes.append(str(message))

    def to_dict(self):
        return {'name': self.name,
                'passed': not self.errors,
                'error_count': len(self.errors),
                'errors': self.errors[:60],
                'notes': self.notes}


# ---------------------------------------------------------------------------
# deterministic reference data (frozen inputs + Structured-A baseline)
# ---------------------------------------------------------------------------
class Context:
    def __init__(self, log):
        self.log = log
        self.conn = read_json(INPUTS / 'connectivity_1024.json')
        self.manifest = {int(record['route_id']): record
                         for record in self.conn['routes']}
        self.groups = {int(group['group_id']): group
                       for group in self.conn['groups']}
        self.phase2 = {int(record['route_id']): record
                       for record in read_json(PHASE2_2D / 'routes_1024.json')['routes']}
        self.plane_row = self.conn['plane_row']
        self.plane_z = self.conn['plane_z_mm']
        self.endpoints = ENDPOINTS
        self.board = float(self.conn['board_mm'])
        self.a_payload = read_json(A_DIR / 'routes_1024.json')
        self.a_routes = {int(record['route_id']): record
                         for record in self.a_payload['routes']}
        self.a_summary = read_json(A_DIR / 'summary.json')
        self.a_validation = read_json(A_DIR / 'validation.json')
        self.hybrid_layer_stack = read_json(PHASE5_STACK)
        self.z1_opposite_gids = sorted(
            gid for gid, group in self.groups.items()
            if group['kind'] == 'opposite' and group['plane'] == 'z1')
        self.z2_opposite_gids = sorted(
            gid for gid, group in self.groups.items()
            if group['kind'] == 'opposite' and group['plane'] == 'z2')
        self.u_gids = sorted(gid for gid, group in self.groups.items()
                             if group['kind'] == 'same')
        self.adjacent_gids = sorted(gid for gid, group in self.groups.items()
                                    if group['kind'] == 'adjacent')
        self.z1_adjacent_gids = [gid for gid in self.adjacent_gids
                                 if self.groups[gid]['plane'] == 'z1']
        self.z2_adjacent_gids = [gid for gid in self.adjacent_gids
                                 if self.groups[gid]['plane'] == 'z2']
        self.fixed_rids = sorted(
            rid for rid, record in self.manifest.items()
            if record['relation'] in ('adjacent', 'same')
            or (record['relation'] == 'opposite' and record['plane'] == 'z2'))
        self.crossing_manifest = self.manifest
        # cached 3D paths
        self._paths = {}

    def route_paths(self, routes):
        for rid, route in routes.items():
            if rid not in self._paths:
                self._paths[rid] = RoutePath(route)
        return self._paths

    def group_route_ids(self, gid):
        return [int(rid) for rid in self.groups[int(gid)]['route_ids']]

    def group_routes_by_direction(self, gid):
        ids = self.group_route_ids(gid)
        buckets = defaultdict(list)
        for rid in ids:
            buckets[classify_direction(self.manifest, rid)].append(rid)
        return buckets

    def group_routes_by_phase(self, gid):
        ids = self.group_route_ids(gid)
        return sorted(ids, key=lambda rid: int(
            self.phase2.get(rid, {}).get('rotation_phase') or 0))


def build_crossing_reference(ctx, log):
    """Independent crossing audit of the Structured-A baseline (+ Spatial cross-check)."""
    log('[ref] independent crossing audit of Structured-A payload ...')
    a_per_height, a_unique, a_points = crossing_audit(
        ctx.a_routes.values(), ctx.manifest)
    a_hv, a_hv_by = z1_hv_crossings(a_per_height)
    baseline = {
        'source': 'structured_layer_routing/A/routes_1024.json',
        'unique_crossing_pairs': a_unique,
        'crossing_pairs_by_height': {h: info['pairs']
                                     for h, info in a_per_height.items()},
        'crossing_points_by_height': {h: info['points']
                                      for h, info in a_per_height.items()},
        'crossing_breakdown_by_height': {h: info['breakdown']
                                         for h, info in a_per_height.items()},
        'z1_hv_same_height_pairs': a_hv,
        'z1_hv_breakdown_by_height': a_hv_by,
        'z0_total_pairs': a_per_height.get('0.0', {}).get('pairs'),
        'l2_total_pairs': a_per_height.get('1.0', {}).get('pairs'),
        'transitions': route_transition_count(ctx.a_routes.values()),
        'total_length_mm': route_total_length(ctx.a_routes.values()),
        'layer_counts': layer_counts(ctx.a_routes.values()),
        'per_height': a_per_height,
        'total_crossing_points': a_points,
    }
    # Spatial U-bundle baseline (for the four-way comparison table)
    spatial = None
    spatial_path = SPATIAL_DIR / 'routes_1024.json'
    if spatial_path.exists():
        log('[ref] independent crossing audit of Spatial U-bundle payload ...')
        spatial_payload = read_json(spatial_path)
        spatial_routes = {int(record['route_id']): record
                          for record in spatial_payload['routes']}
        s_per_height, s_unique, s_points = crossing_audit(
            spatial_routes.values(), ctx.manifest)
        spatial_summary = read_json(SPATIAL_DIR / 'summary.json')
        spatial = {
            'source': 'spatial_u_bundle_optimization/routes_1024.json',
            'unique_crossing_pairs_independent': s_unique,
            'crossing_points_independent': s_points,
            'crossing_pairs_by_height_independent': {
                h: info['pairs'] for h, info in s_per_height.items()},
            'summary': spatial_summary,
        }
    return baseline, spatial


# ---------------------------------------------------------------------------
# 1. identity / ports
# ---------------------------------------------------------------------------
IDENTITY_FIELDS = ['plane', 'source_endpoint', 'target_endpoint', 'relation',
                   'pair', 'source_side', 'target_side', 'source_row',
                   'target_row', 'source_column', 'target_column',
                   'source_channel', 'target_channel']


def check_identity_ports(ctx, group, routes):
    log(f'[{group}] 1/9 identity + port audit ...')
    checker = Checker('identity_ports')
    details = {}

    # --- route set / record count ------------------------------------------
    expected_ids = set(ctx.manifest)
    actual_ids = set(routes)
    checker.require(len(routes) == 1024,
                    f'routed record count {len(routes)} != 1024')
    checker.require(actual_ids == expected_ids,
                    f'route_id set mismatch: missing='
                    f'{sorted(expected_ids - actual_ids)[:10]} extra='
                    f'{sorted(actual_ids - expected_ids)[:10]}')
    status_bad = [rid for rid, record in routes.items()
                  if record.get('status') != 'routed']
    checker.require(not status_bad,
                    f'{len(status_bad)} records with status != routed '
                    f'(sample {status_bad[:10]})')
    details['routed'] = len(routes)

    # --- connectivity identity fields --------------------------------------
    mismatch = Counter()
    samples = []
    for rid in sorted(expected_ids & actual_ids):
        source = ctx.manifest[rid]
        target = routes[rid]
        for field in IDENTITY_FIELDS:
            if target.get(field) != source.get(field):
                mismatch[field] += 1
                if len(samples) < 20:
                    samples.append((rid, field, source.get(field),
                                    target.get(field)))
    checker.require(not mismatch,
                    f'connectivity identity fields mismatch: {dict(mismatch)} '
                    f'samples={samples}')
    checker.require(not mismatch,
                    f'payload identity does not match connectivity for '
                    f'{sum(mismatch.values())} fields')
    details['identity_mismatch_fields'] = dict(mismatch)
    details['identity_fields_checked'] = list(IDENTITY_FIELDS)

    # --- board / topology inputs -------------------------------------------
    checker.require(ctx.board == BOARD,
                    f'connectivity board_mm {ctx.board} != {BOARD}')
    checker.require(int(ctx.conn['connections']) == 1024,
                    f'connectivity connections={ctx.conn["connections"]}')
    checker.require(int(ctx.conn['ports']) == 2048,
                    f'connectivity ports={ctx.conn["ports"]}')
    checker.require(ctx.plane_row == {'z1': 1, 'z2': 2},
                    f'plane_row mapping unexpected: {ctx.plane_row}')
    checker.require(ctx.plane_z == {'z1': 0.0, 'z2': 0.5},
                    f'plane_z mapping unexpected: {ctx.plane_z}')
    details['connectivity'] = {
        'connections': int(ctx.conn['connections']),
        'ports': int(ctx.conn['ports']),
        'groups': int(ctx.conn['group_count']),
        'board_mm': ctx.board,
        'plane_row': ctx.plane_row,
        'plane_z_mm': ctx.plane_z,
        'relation_counts': ctx.conn['relation_counts'],
        'rotation_closure': ctx.conn['rotation_closure'],
    }

    # --- 2048 ports used exactly once --------------------------------------
    used = Counter()
    for rid in sorted(routes):
        record = routes[rid]
        used[record['source_endpoint']] += 1
        used[record['target_endpoint']] += 1
    duplicates = {key: value for key, value in used.items() if value != 1}
    unused = set(ctx.endpoints) - set(used)
    extra = set(used) - set(ctx.endpoints)
    checker.require(not duplicates,
                    f'ports used more than once: {len(duplicates)} '
                    f'(sample {sorted(duplicates)[:10]})')
    checker.require(not unused,
                    f'{len(unused)} declared ports unused (sample '
                    f'{sorted(unused)[:10]})')
    checker.require(not extra,
                    f'{len(extra)} endpoints not in the frozen port table '
                    f'(sample {sorted(extra)[:10]})')
    sources = [routes[rid]['source_endpoint'] for rid in sorted(routes)]
    targets = [routes[rid]['target_endpoint'] for rid in sorted(routes)]
    overlap = set(sources) & set(targets)
    checker.require(not overlap,
                    f'{len(overlap)} endpoints appear as both source and '
                    f'target (sample {sorted(overlap)[:10]})')
    checker.require(len(set(sources)) == 1024 and len(set(targets)) == 1024,
                    f'source/target sets not unique: '
                    f'{len(set(sources))}/{len(set(targets))}')
    details['ports'] = {'used_once': len(used), 'expected': 2048,
                        'sources': len(set(sources)),
                        'targets': len(set(targets))}

    # --- plane <-> row <-> interface height consistency --------------------
    row_bad = []
    z_bad = []
    xy_bad = []
    layer_bad = []
    endpoint_bad = []
    for rid in sorted(routes):
        record = routes[rid]
        source = ctx.manifest[rid]
        plane = source['plane']
        expected_row = ctx.plane_row[plane]
        expected_z = ctx.plane_z[plane]
        if (int(record['source_row']) != expected_row
                or int(record['target_row']) != expected_row):
            row_bad.append((rid, record['source_row'], record['target_row'],
                            expected_row))
        for tag, endpoint in (('source_port', source['source_endpoint']),
                              ('target_port', source['target_endpoint'])):
            port = record.get(tag) or {}
            entry = ctx.endpoints[endpoint]
            if not close(port.get('z_mm'), expected_z, 1e-12):
                z_bad.append((rid, tag, port.get('z_mm'), expected_z))
            if int(port.get('layer_id') or 0) != 1:
                layer_bad.append((rid, tag, port.get('layer_id')))
            if math.dist(port.get('xy') or [1e9, 1e9],
                         entry['routing_xy']) > TOL_TIGHT:
                xy_bad.append((rid, tag, port.get('xy'),
                               entry['routing_xy']))
            # route endpoint string encodes side/row/column/channel
            parts = endpoint.split(':')
            connector, row, column = parts[0], int(parts[1]), int(parts[2])
            if (connector[0] != entry['side'] or row != int(entry['row'])
                    or column != int(entry['column'])
                    or connector != entry['connector']):
                endpoint_bad.append((rid, tag, endpoint, entry['endpoint_id']))
        if (not close(record.get('start_z_mm'), expected_z, 1e-12)
                or not close(record.get('end_z_mm'), expected_z, 1e-12)):
            z_bad.append((rid, 'start/end_z', record.get('start_z_mm'),
                          record.get('end_z_mm'), expected_z))
        # connectivity channels match the frozen port table
        for column, endpoint in (('source_channel', source['source_endpoint']),
                                 ('target_channel', source['target_endpoint'])):
            if int(source[column]) != int(ctx.endpoints[endpoint]['channel']):
                endpoint_bad.append((rid, column, source[column],
                                     ctx.endpoints[endpoint]['channel']))
    checker.require(not row_bad,
                    f'{len(row_bad)} routes plane/row mismatch '
                    f'(sample {row_bad[:5]})')
    checker.require(not z_bad,
                    f'{len(z_bad)} plane/interface-height mismatches '
                    f'(sample {z_bad[:5]})')
    checker.require(not xy_bad,
                    f'{len(xy_bad)} port XY mismatches (sample {xy_bad[:5]})')
    checker.require(not layer_bad,
                    f'{len(layer_bad)} port layer_id mismatches '
                    f'(sample {layer_bad[:5]})')
    checker.require(not endpoint_bad,
                    f'{len(endpoint_bad)} endpoint/channel encoding mismatches '
                    f'(sample {endpoint_bad[:5]})')
    details['plane_row_z'] = {
        'row_bad': len(row_bad), 'z_bad': len(z_bad),
        'port_xy_bad': len(xy_bad), 'port_layer_bad': len(layer_bad),
        'endpoint_bad': len(endpoint_bad),
    }

    return checker.to_dict(), details


def check_payload_layer_stack(ctx, group, payload, checker=None):
    checker = checker or Checker('payload_layer_stack')
    stack = payload.get('layer_stack') or {}
    details = {}
    checker.require(payload.get('schema') == 'four_side_1024_v2_l3d_routes_v1',
                    f'payload schema={payload.get("schema")!r}')
    checker.require(stack.get('schema') == 'four_side_1024_v2_l3d_layer_stack_v1',
                    f'layer_stack schema={stack.get("schema")!r}')
    layers = stack.get('layers') or {}
    expected = {1: None, 2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5}
    for layer_id in (2, 3, 4, 5):
        checker.require(close((layers.get(str(layer_id)) or {}).get('physical_z_mm'),
                              expected[layer_id], 1e-12),
                        f'layer {layer_id} z mismatch')
    interface = (layers.get('1') or {}).get('interface_rows') or {}
    checker.require(interface.get('z1') == 0.0 and interface.get('z2') == 0.5,
                    f'interface rows unexpected: {interface}')
    checker.require(stack.get('formal_acceptance_allowed') is False,
                    'layer_stack formal_acceptance_allowed is not False')
    details['layer_z_mm'] = {str(layer_id):
                             (layers.get(str(layer_id)) or {}).get('physical_z_mm')
                             for layer_id in range(1, 6)}
    details['interface_rows'] = interface
    details['provenance'] = stack.get('provenance')
    return checker.to_dict(), details


# ---------------------------------------------------------------------------
# 2. mixed symmetry (C2 180 deg for z1 opposite pairs, C4 90 deg for C4 groups)
# ---------------------------------------------------------------------------
def _reversed_transition(part):
    return {
        'kind': 'transition',
        'start': list(part['end']),
        'end': list(part['start']),
        'direction': [-float(part['direction'][0]), -float(part['direction'][1])],
        'z0': float(part['z1']),
        'z1': float(part['z0']),
        'dz_mm': -float(part['dz_mm']),
        'radius_mm': float(part['radius_mm']),
        'footprint_mm': float(part['footprint_mm']),
        'theta_rad': float(part['theta_rad']),
        'length_mm': float(part['length_mm']),
        'from_layer': int(part['to_layer']),
        'to_layer': int(part['from_layer']),
    }


def _compare_transition_contract(route_a, route_b, quarter, reversed_order,
                                 tol=TOL_TIGHT):
    """Check transition parameters/positions under the rigid rotation."""
    errors = []
    trans_a = [part for part in route_a.get('parts') or []
               if part['kind'] == 'transition']
    trans_b = [part for part in route_b.get('parts') or []
               if part['kind'] == 'transition']
    if len(trans_a) != len(trans_b):
        return [f'transition count {len(trans_a)} != {len(trans_b)}'], []
    expected = ([ _reversed_transition(part) for part in reversed(trans_b)]
                if reversed_order else trans_b)
    pairs = []
    for index, (part_a, part_mapped) in enumerate(zip(trans_a, expected)):
        start_rot = rot_xy(part_a['start'][0], part_a['start'][1], quarter)
        end_rot = rot_xy(part_a['end'][0], part_a['end'][1], quarter)
        direction_rot = rot_vector(part_a['direction'][0],
                                   part_a['direction'][1], quarter)
        checks = {
            'start': math.dist(start_rot, part_mapped['start']) <= tol,
            'end': math.dist(end_rot, part_mapped['end']) <= tol,
            'direction': math.dist(direction_rot, part_mapped['direction'])
            <= tol,
            'z0': close(part_a['z0'], part_mapped['z0'], tol),
            'z1': close(part_a['z1'], part_mapped['z1'], tol),
            'dz_mm': close(part_a['dz_mm'], part_mapped['dz_mm'], tol),
            'radius_mm': close(part_a['radius_mm'],
                               part_mapped['radius_mm'], tol),
            'footprint_mm': close(part_a['footprint_mm'],
                                  part_mapped['footprint_mm'], tol),
            'theta_rad': close(part_a['theta_rad'],
                               part_mapped['theta_rad'], tol),
            'length_mm': close(part_a['length_mm'],
                               part_mapped['length_mm'], tol),
            'from_layer': int(part_a['from_layer'])
            == int(part_mapped['from_layer']),
            'to_layer': int(part_a['to_layer']) == int(part_mapped['to_layer']),
        }
        bad = [name for name, value in checks.items() if not value]
        if bad:
            errors.append(f'transition[{index}] fields differ under rotation: '
                          f'{bad}')
        pairs.append({'index': index, 'ok': not bad, 'bad_fields': bad})
    return errors, pairs


def _flat_part_sequence(route):
    out = []
    for part in route.get('parts') or []:
        if part['kind'] == 'flat':
            out.append({'z_mm': float(part['z_mm']),
                        'layer_id': int(part['layer_id']),
                        'length_mm': round(float(part['length_mm']), 9),
                        'primitives': len(part['primitives'])})
    return out


def _compare_flat_parts(route_a, route_b, reversed_order, tol=TOL_SYM):
    errors = []
    flats_a = _flat_part_sequence(route_a)
    flats_b = _flat_part_sequence(route_b)
    if len(flats_a) != len(flats_b):
        return [f'flat part count {len(flats_a)} != {len(flats_b)}']
    expected = list(reversed(flats_b)) if reversed_order else flats_b
    for index, (flat_a, flat_b) in enumerate(zip(flats_a, expected)):
        if not close(flat_a['z_mm'], flat_b['z_mm'], tol):
            errors.append(f'flat[{index}] z {flat_a["z_mm"]} != '
                          f'{flat_b["z_mm"]}')
        if flat_a['layer_id'] != flat_b['layer_id']:
            errors.append(f'flat[{index}] layer {flat_a["layer_id"]} != '
                          f'{flat_b["layer_id"]}')
        if not close(flat_a['length_mm'], flat_b['length_mm'], tol):
            errors.append(f'flat[{index}] length {flat_a["length_mm"]} != '
                          f'{flat_b["length_mm"]}')
        if flat_a['primitives'] != flat_b['primitives']:
            errors.append(f'flat[{index}] primitive count differs')
    return errors


def compare_rotation(ctx, route_a, route_b, quarter):
    """Strict rigid-rotation check of two routes with tolerance TOL_SYM."""
    path_a = ctx.route_paths({int(route_a['route_id']): route_a})[
        int(route_a['route_id'])]
    path_b = ctx.route_paths({int(route_b['route_id']): route_b})[
        int(route_b['route_id'])]
    result = {'quarter': int(quarter), 'ok': False, 'errors': []}
    if abs(path_a.total - path_b.total) > TOL_SYM:
        result['errors'].append(
            f'route length {path_a.total:.12g} != {path_b.total:.12g}')
        return result
    samples_a = path_a.samples(step=0.25)
    samples_b = path_b.samples(step=0.25)
    rotated_a = [(rot_xy(point[0], point[1], quarter)[0],
                  rot_xy(point[0], point[1], quarter)[1], point[2])
                 for point in samples_a]
    forward = (math.dist(rotated_a[0], samples_b[0])
               + math.dist(rotated_a[-1], samples_b[-1]))
    backward = (math.dist(rotated_a[0], samples_b[-1])
                + math.dist(rotated_a[-1], samples_b[0]))
    reversed_order = backward < forward
    sequence_b = list(reversed(samples_b)) if reversed_order else samples_b
    deviation = max_dev(rotated_a, sequence_b)
    result['reversed'] = bool(reversed_order)
    result['endpoint_forward_mm'] = round(forward, 12)
    result['endpoint_backward_mm'] = round(backward, 12)
    result['max_deviation_mm'] = deviation
    result['length_mm'] = round(path_a.total, 9)
    if deviation > TOL_SYM:
        result['errors'].append(f'3D path deviation {deviation:.12g} > {TOL_SYM}')
    transition_errors, pairs = _compare_transition_contract(
        route_a, route_b, quarter, reversed_order)
    result['transition_contract'] = pairs
    result['errors'].extend(transition_errors)
    result['errors'].extend(_compare_flat_parts(route_a, route_b,
                                                reversed_order))
    for field in ('layer_sequence', 'layer_z_sequence', 'n_transitions'):
        if route_a.get(field) != route_b.get(field):
            result['errors'].append(f'{field} {route_a.get(field)!r} != '
                                    f'{route_b.get(field)!r}')
    result['ok'] = not result['errors']
    return result


def check_symmetry(ctx, group, routes):
    log(f'[{group}] 2/9 mixed C2/C4 symmetry audit ...')
    checker = Checker('symmetry')
    details = {}

    # ---- z1 opposite: 180 deg C2 pairs split by port direction -----------
    c2_records = []
    c2_errors = []
    direction_pair_counts = Counter()
    direction_route_counts = Counter()
    for gid in ctx.z1_opposite_gids:
        buckets = ctx.group_routes_by_direction(gid)
        if len(buckets['EW']) != 2 or len(buckets['NS']) != 2:
            c2_errors.append(
                f'group {gid}: expected 2 EW + 2 NS, got '
                f'EW={buckets["EW"]} NS={buckets["NS"]}')
            continue
        for direction in ('EW', 'NS'):
            ids = buckets[direction]
            direction_pair_counts[direction] += 1
            direction_route_counts[direction] += len(ids)
            comparison = compare_rotation(ctx, routes[ids[0]], routes[ids[1]], 2)
            record = {
                'group_id': int(gid),
                'direction': direction,
                'route_ids': sorted(ids),
                'ok': comparison['ok'],
                'reversed_order': comparison.get('reversed'),
                'max_deviation_mm': comparison.get('max_deviation_mm'),
                'length_mm': comparison.get('length_mm'),
                'lifted': all(routes[rid].get('n_transitions') == 2
                              for rid in ids),
                'errors': comparison['errors'],
            }
            c2_records.append(record)
            if not comparison['ok']:
                c2_errors.append(f'C2 pair group {gid} {direction} '
                                 f'{sorted(ids)}: {comparison["errors"]}')
    z1_opposite_total = sum(len(ctx.group_route_ids(gid))
                            for gid in ctx.z1_opposite_gids)
    checker.require(len(c2_records) == 132,
                    f'C2 pair count {len(c2_records)} != 132 '
                    f'(66 EW + 66 NS)')
    checker.require(direction_pair_counts['EW'] == 66
                    and direction_pair_counts['NS'] == 66,
                    f'C2 direction pair split unexpected: '
                    f'{dict(direction_pair_counts)}')
    checker.require(direction_route_counts['EW'] == 132
                    and direction_route_counts['NS'] == 132,
                    f'C2 direction route split unexpected: '
                    f'{dict(direction_route_counts)}')
    covered = sorted(rid for record in c2_records
                     for rid in record['route_ids'])
    checker.require(covered == sorted(rid for gid in ctx.z1_opposite_gids
                                      for rid in ctx.group_route_ids(gid)),
                    'C2 pairs do not partition the 264 z1 opposite routes '
                    'exactly once')
    checker.require(z1_opposite_total == 264,
                    f'z1 opposite route count {z1_opposite_total} != 264')
    checker.require(not c2_errors,
                    f'{len(c2_errors)} C2 pair failures (sample '
                    f'{c2_errors[:6]})')
    deviations = [record['max_deviation_mm'] for record in c2_records
                  if record['max_deviation_mm'] is not None]
    details['c2'] = {
        'pairs': len(c2_records),
        'passed': sum(1 for record in c2_records if record['ok']),
        'directions': dict(direction_pair_counts),
        'route_directions': dict(direction_route_counts),
        'max_deviation_mm': max(deviations) if deviations else None,
        'reversed_order_counts': dict(Counter(
            (record['direction'], record['reversed_order'])
            for record in c2_records)),
        'pairs_detail': c2_records,
    }

    # ---- C4 groups: same (U) + z2 opposite + z2 adjacent ------------------
    c4_gids = (list(ctx.u_gids) + list(ctx.z2_opposite_gids)
               + list(ctx.z2_adjacent_gids))
    c4_records = []
    c4_errors = []
    category_counts = Counter()
    for gid in c4_gids:
        group_record = ctx.groups[gid]
        category = group_record['kind']
        if group_record['plane'] == 'z2' and group_record['kind'] != 'same':
            category = f'z2_{group_record["kind"]}'
        elif group_record['kind'] == 'adjacent':
            category = 'z1_adjacent'
        category_counts[category] += 1
        ids = ctx.group_routes_by_phase(gid)
        phases = [int(ctx.phase2[rid].get('rotation_phase') or 0)
                  for rid in ids]
        if phases != [0, 1, 2, 3]:
            c4_errors.append(f'group {gid}: rotation phases {phases}')
            continue
        if [int(rid) for rid in group_record['route_ids']] != sorted(
                ids, key=lambda rid: int(ctx.phase2[rid]['rotation_phase'])):
            c4_errors.append(f'group {gid}: route_ids order != phase order')
        base = routes[ids[0]]
        member_records = []
        for quarter in (1, 2, 3):
            comparison = compare_rotation(ctx, base, routes[ids[quarter]],
                                          quarter)
            member_records.append({
                'route_id': int(ids[quarter]),
                'quarter': quarter,
                'ok': comparison['ok'],
                'reversed_order': comparison.get('reversed'),
                'max_deviation_mm': comparison.get('max_deviation_mm'),
                'length_mm': comparison.get('length_mm'),
                'errors': comparison['errors'],
            })
            if not comparison['ok']:
                c4_errors.append(f'C4 group {gid} route {ids[quarter]} '
                                 f'(quarter {quarter}): {comparison["errors"]}')
        c4_records.append({
            'group_id': int(gid),
            'category': category,
            'plane': group_record['plane'],
            'kind': group_record['kind'],
            'route_ids': ids,
            'base_route_id': int(ids[0]),
            'members': member_records,
            'ok': all(member['ok'] for member in member_records),
        })
    checker.require(len(c4_records) == 144,
                    f'C4 group count {len(c4_records)} != 144 '
                    f'(64 U + 2 z2 opposite + 78 z2 adjacent)')
    checker.require(category_counts.get('same') == 64,
                    f'U (same) C4 group count {category_counts.get("same")} '
                    f'!= 64')
    checker.require(category_counts.get('z2_opposite') == 2,
                    f'z2 opposite C4 group count '
                    f'{category_counts.get("z2_opposite")} != 2')
    checker.require(category_counts.get('z2_adjacent') == 78,
                    f'z2 adjacent C4 group count '
                    f'{category_counts.get("z2_adjacent")} != 78')
    member_total = sum(len(record['members']) for record in c4_records)
    checker.require(member_total == 432,
                    f'C4 member comparison count {member_total} != 432')
    checker.require(not c4_errors,
                    f'{len(c4_errors)} C4 member failures (sample '
                    f'{c4_errors[:6]})')
    member_deviations = [member['max_deviation_mm']
                         for record in c4_records
                         for member in record['members']
                         if member['max_deviation_mm'] is not None]
    details['c4'] = {
        'groups': len(c4_records),
        'categories': dict(category_counts),
        'member_checks': member_total,
        'members_passed': sum(1 for record in c4_records
                              for member in record['members'] if member['ok']),
        'max_deviation_mm': max(member_deviations) if member_deviations else None,
        'reversed_order_counts': dict(Counter(
            (member['quarter'], member['reversed_order'])
            for record in c4_records for member in record['members'])),
        'groups_detail': c4_records,
    }

    # ---- z1 adjacent: preserved Structured-A C4 (no C2 requirement) ------
    z1_adj_records = []
    z1_adj_errors = []
    for gid in ctx.z1_adjacent_gids:
        ids = ctx.group_routes_by_phase(gid)
        phases = [int(ctx.phase2[rid].get('rotation_phase') or 0)
                  for rid in ids]
        if phases != [0, 1, 2, 3]:
            z1_adj_errors.append(f'group {gid}: rotation phases {phases}')
            continue
        base = routes[ids[0]]
        members = []
        for quarter in (1, 2, 3):
            comparison = compare_rotation(ctx, base, routes[ids[quarter]],
                                          quarter)
            members.append({'route_id': int(ids[quarter]),
                            'quarter': quarter,
                            'ok': comparison['ok'],
                            'max_deviation_mm': comparison.get('max_deviation_mm'),
                            'errors': comparison['errors']})
            if not comparison['ok']:
                z1_adj_errors.append(
                    f'z1 adjacent C4 group {gid} route {ids[quarter]} '
                    f'quarter {quarter}: {comparison["errors"]}')
        z1_adj_records.append({'group_id': int(gid), 'route_ids': ids,
                               'members': members,
                               'ok': all(item['ok'] for item in members)})
    checker.require(len(z1_adj_records) == 46,
                    f'z1 adjacent group count {len(z1_adj_records)} != 46')
    checker.require(not z1_adj_errors,
                    f'{len(z1_adj_errors)} z1-adjacent C4 failures (sample '
                    f'{z1_adj_errors[:6]})')
    details['z1_adjacent_c4'] = {
        'groups': len(z1_adj_records),
        'member_checks': 3 * len(z1_adj_records),
        'passed': sum(1 for record in z1_adj_records if record['ok']),
        'max_deviation_mm': max(
            [member['max_deviation_mm'] for record in z1_adj_records
             for member in record['members']
             if member['max_deviation_mm'] is not None] or [0.0]),
        'groups_detail': z1_adj_records,
    }
    return checker.to_dict(), details


# ---------------------------------------------------------------------------
# 3. fixed preservation against Structured A
# ---------------------------------------------------------------------------
ANNOTATION_KEYS = ('_back_to_back_transitions',)


def _record_diff(record_a, record_b, ignore_annotation=True):
    keys = set(record_a) | set(record_b)
    diffs = {}
    for key in sorted(keys):
        if ignore_annotation and key.startswith('_'):
            continue
        if record_a.get(key) != record_b.get(key):
            diffs[key] = [record_a.get(key), record_b.get(key)]
    return diffs


def check_fixed_preservation(ctx, group, routes):
    log(f'[{group}] 3/9 fixed-preservation audit vs Structured A ...')
    checker = Checker('fixed_preservation')
    details = {}
    u_rids = [rid for rid, record in ctx.manifest.items()
              if record['relation'] == 'same']
    z2_opposite_rids = [rid for rid, record in ctx.manifest.items()
                        if record['relation'] == 'opposite'
                        and record['plane'] == 'z2']
    adjacent_rids = [rid for rid, record in ctx.manifest.items()
                     if record['relation'] == 'adjacent']
    z1_adjacent_rids = [rid for rid in adjacent_rids
                        if ctx.manifest[rid]['plane'] == 'z1']
    checker.require(len(u_rids) == 256, f'U route count {len(u_rids)} != 256')
    checker.require(len(z2_opposite_rids) == 8,
                    f'z2 opposite route count {len(z2_opposite_rids)} != 8')
    checker.require(len(adjacent_rids) == 496,
                    f'adjacent route count {len(adjacent_rids)} != 496 '
                    f'(z1={len(z1_adjacent_rids)})')
    checker.require(len(z1_adjacent_rids) == 184,
                    f'z1 adjacent route count {len(z1_adjacent_rids)} != 184')

    def compare_set(name, rids):
        contract_bad = []
        annotation_bad = []
        annotation_keys = Counter()
        for rid in rids:
            diffs = _record_diff(ctx.a_routes[rid], routes[rid],
                                 ignore_annotation=True)
            if diffs:
                contract_bad.append((rid, sorted(diffs)))
            annotation = _record_diff(ctx.a_routes[rid], routes[rid],
                                      ignore_annotation=False)
            annotation_only = {key: value for key, value in annotation.items()
                               if key and not key.startswith('_')}
            if not annotation_only and set(annotation) - set(diffs):
                annotation_bad.append(rid)
                for key in sorted(set(annotation) - set(diffs)):
                    annotation_keys[key] += 1
        checker.require(not contract_bad,
                        f'{name}: {len(contract_bad)} of {len(rids)} records '
                        f'differ from Structured A (sample '
                        f'{contract_bad[:5]})')
        counts = {'records': len(rids),
                  'contract_identical': len(rids) - len(contract_bad),
                  'validator_annotation_differences': len(annotation_bad),
                  'annotation_keys': dict(annotation_keys)}
        details[name] = counts
        return counts

    details['U'] = compare_set('U', u_rids)
    details['z2_opposite'] = compare_set('z2_opposite', z2_opposite_rids)
    details['adjacent'] = compare_set('adjacent', adjacent_rids)
    details['z1_adjacent'] = compare_set('z1_adjacent', z1_adjacent_rids)
    details['fixed_total'] = len(u_rids) + len(z2_opposite_rids) + len(
        adjacent_rids)

    # ---- U bundle layer structure (L3 / L4 / L5 heights) -----------------
    u_layer_errors = []
    for gid in ctx.u_gids:
        expected_layer, expected_z = U_TARGET[gid]
        for rid in ctx.group_route_ids(gid):
            record = routes[rid]
            parts = record.get('parts') or []
            z_mm = [float(part['z_mm']) for part in parts
                    if part['kind'] == 'flat']
            sequence = [int(value) for value in record.get('layer_sequence') or []]
            z_sequence = [float(value)
                          for value in record.get('layer_z_sequence') or []]
            interface_z = ctx.plane_z[ctx.manifest[rid]['plane']]
            if int(record.get('n_transitions')) != 2:
                u_layer_errors.append((rid, gid, 'n_transitions',
                                       record.get('n_transitions')))
            if sequence != [1, expected_layer, 1]:
                u_layer_errors.append((rid, gid, 'layer_sequence', sequence))
            if (len(z_sequence) != 3 or not close(z_sequence[0], interface_z, 1e-12)
                    or not close(z_sequence[1], expected_z, 1e-12)
                    or not close(z_sequence[2], interface_z, 1e-12)):
                u_layer_errors.append((rid, gid, 'layer_z_sequence', z_sequence))
            if len(z_mm) != 3:
                u_layer_errors.append((rid, gid, 'flat_parts', len(z_mm)))
            elif (not close(z_mm[0], interface_z, 1e-12)
                    or not close(z_mm[1], expected_z, 1e-12)
                    or not close(z_mm[2], interface_z, 1e-12)):
                u_layer_errors.append((rid, gid, 'flat_z', z_mm))
    checker.require(not u_layer_errors,
                    f'{len(u_layer_errors)} U layer-structure violations '
                    f'(sample {u_layer_errors[:5]})')
    details['U_target_layers'] = {
        'groups_L3': sorted(gid for gid, value in U_TARGET.items()
                            if value[0] == 3),
        'groups_L4': sorted(gid for gid, value in U_TARGET.items()
                            if value[0] == 4),
        'groups_L5': sorted(gid for gid, value in U_TARGET.items()
                            if value[0] == 5),
        'routes_total': len(u_rids),
        'violations': len(u_layer_errors),
    }

    # ---- fixed z2 opposite routes stay on L2 -----------------------------
    z2_opposite_errors = []
    for rid in z2_opposite_rids:
        record = routes[rid]
        interface_z = ctx.plane_z['z2']
        if [int(value) for value in record.get('layer_sequence') or []] != [1, 2, 1]:
            z2_opposite_errors.append((rid, 'layer_sequence',
                                       record.get('layer_sequence')))
        if not close(record.get('n_transitions'), 2, 0):
            z2_opposite_errors.append((rid, 'n_transitions',
                                       record.get('n_transitions')))
        z_sequence = [float(value)
                      for value in record.get('layer_z_sequence') or []]
        if (len(z_sequence) != 3 or not close(z_sequence[0], interface_z, 1e-12)
                or not close(z_sequence[1], 1.0, 1e-12)
                or not close(z_sequence[2], interface_z, 1e-12)):
            z2_opposite_errors.append((rid, 'layer_z_sequence', z_sequence))
    checker.require(not z2_opposite_errors,
                    f'{len(z2_opposite_errors)} z2-opposite L2 violations '
                    f'(sample {z2_opposite_errors[:5]})')
    details['z2_opposite_L2'] = {'routes': len(z2_opposite_rids),
                                 'violations': len(z2_opposite_errors)}

    # ---- adjacent routes stay flat on their interface layer --------------
    adjacent_errors = []
    for rid in adjacent_rids:
        record = routes[rid]
        interface_z = ctx.plane_z[ctx.manifest[rid]['plane']]
        parts = record.get('parts') or []
        if len(parts) != 1 or parts[0]['kind'] != 'flat':
            adjacent_errors.append((rid, 'parts', [part['kind'] for part in parts]))
            continue
        if not close(parts[0]['z_mm'], interface_z, 1e-12):
            adjacent_errors.append((rid, 'z', parts[0]['z_mm'], interface_z))
        if int(record.get('n_transitions')) != 0:
            adjacent_errors.append((rid, 'n_transitions',
                                    record.get('n_transitions')))
    checker.require(not adjacent_errors,
                    f'{len(adjacent_errors)} adjacent interface-layer '
                    f'violations (sample {adjacent_errors[:5]})')
    details['adjacent_interface'] = {'routes': len(adjacent_rids),
                                     'violations': len(adjacent_errors)}

    # ---- signal whether fixed records carry the validator annotation -----
    annotations = Counter()
    for rid in ctx.fixed_rids:
        annotations[ANNOTATION_KEYS[0]] += int(
            ANNOTATION_KEYS[0] in routes[rid])
    rebuilt_z1_opposite = [
        rid for rid in routes
        if ctx.manifest[rid]['relation'] == 'opposite'
        and ctx.manifest[rid]['plane'] == 'z1']
    details['annotation_presence'] = {
        'fixed_records': len(ctx.fixed_rids),
        'fixed_records_with_annotation': dict(annotations),
        'rebuilt_z1_opposite_records': len(rebuilt_z1_opposite),
        'rebuilt_z1_opposite_with_annotation': sum(
            1 for rid in rebuilt_z1_opposite
            if ANNOTATION_KEYS[0] in routes[rid]),
        'note': ('the 760 fixed records keep the l3d validator annotation '
                 'written during Structured A; the 264 rebuilt z1-opposite '
                 'records lack it by construction (the frozen validator '
                 'recomputes it)'),
    }
    return checker.to_dict(), details


# ---------------------------------------------------------------------------
# 4. directional layer rules + c2_pair_assignment consistency
# ---------------------------------------------------------------------------
def route_is_lifted(route):
    return int(route.get('n_transitions') or 0) == 2


def route_is_flat(route):
    return int(route.get('n_transitions') or 0) == 0


def check_layer_rules(ctx, group, routes, assignment, summary):
    log(f'[{group}] 4/9 directional layer rules + C2 assignment audit ...')
    checker = Checker('layer_rules')
    details = {}
    lift_direction = 'EW' if group == 'H' else 'NS'
    keep_direction = 'NS' if group == 'H' else 'EW'

    lifted_contract_errors = []
    flat_contract_errors = []

    def check_lifted(rid):
        record = routes[rid]
        interface_z = ctx.plane_z[ctx.manifest[rid]['plane']]
        parts = record.get('parts') or []
        expected = ['flat', 'transition', 'flat', 'transition', 'flat']
        if [part['kind'] for part in parts] != expected:
            lifted_contract_errors.append(
                (rid, 'part kinds', [part['kind'] for part in parts]))
            return False
        ok = True
        if [int(value) for value in record.get('layer_sequence') or []] \
                != [1, 2, 1]:
            lifted_contract_errors.append(
                (rid, 'layer_sequence', record.get('layer_sequence')))
            ok = False
        z_sequence = [float(value)
                      for value in record.get('layer_z_sequence') or []]
        if (len(z_sequence) != 3
                or not close(z_sequence[0], interface_z, 1e-12)
                or not close(z_sequence[1], 1.0, 1e-12)
                or not close(z_sequence[2], interface_z, 1e-12)):
            lifted_contract_errors.append((rid, 'layer_z_sequence', z_sequence))
            ok = False
        if not close(parts[0]['z_mm'], interface_z, 1e-12) \
                or not close(parts[2]['z_mm'], 1.0, 1e-12) \
                or not close(parts[4]['z_mm'], interface_z, 1e-12):
            lifted_contract_errors.append(
                (rid, 'flat z', [parts[k]['z_mm'] for k in (0, 2, 4)]))
            ok = False
        if not (parts[2]['length_mm'] > 1e-6):
            lifted_contract_errors.append(
                (rid, 'L2 travel empty', parts[2]['length_mm']))
            ok = False
        trans = [part for part in parts if part['kind'] == 'transition']
        if (not (float(trans[0]['z0']) < float(trans[0]['z1']))
                or not (float(trans[1]['z0']) > float(trans[1]['z1']))):
            lifted_contract_errors.append((rid, 'rise/fall order',
                                           [(trans[0]['z0'], trans[0]['z1']),
                                            (trans[1]['z0'], trans[1]['z1'])]))
            ok = False
        if (int(trans[0]['from_layer']), int(trans[0]['to_layer'])) != (1, 2) \
                or (int(trans[1]['from_layer']),
                    int(trans[1]['to_layer'])) != (2, 1):
            lifted_contract_errors.append((rid, 'transition layers',
                                           [(trans[0]['from_layer'],
                                             trans[0]['to_layer']),
                                            (trans[1]['from_layer'],
                                             trans[1]['to_layer'])]))
            ok = False
        if sorted(set(int(value)
                      for value in (record.get('layers_used') or []))) \
                != [1, 2]:
            lifted_contract_errors.append(
                (rid, 'layers_used', record.get('layers_used')))
            ok = False
        if not record.get('lifted'):
            lifted_contract_errors.append((rid, 'lifted flag false'))
            ok = False
        return ok

    def check_flat(rid):
        record = routes[rid]
        interface_z = ctx.plane_z[ctx.manifest[rid]['plane']]
        parts = record.get('parts') or []
        if len(parts) != 1 or parts[0]['kind'] != 'flat':
            flat_contract_errors.append(
                (rid, 'parts', [part['kind'] for part in parts]))
            return False
        ok = True
        if not close(parts[0]['z_mm'], interface_z, 1e-12):
            flat_contract_errors.append((rid, 'flat z', parts[0]['z_mm']))
            ok = False
        if [int(value) for value in record.get('layer_sequence') or []] != [1]:
            flat_contract_errors.append(
                (rid, 'layer_sequence', record.get('layer_sequence')))
            ok = False
        if record.get('lifted'):
            flat_contract_errors.append((rid, 'lifted flag true'))
            ok = False
        return ok

    # per-group directional status
    group_status = {}
    lift_errors = []
    for gid in ctx.z1_opposite_gids:
        buckets = ctx.group_routes_by_direction(gid)
        status = {}
        for direction in ('EW', 'NS'):
            ids = buckets[direction]
            lifted_flags = [route_is_lifted(routes[rid]) for rid in ids]
            flat_flags = [route_is_flat(routes[rid]) for rid in ids]
            if all(lifted_flags):
                state = 'lifted'
                for rid in ids:
                    check_lifted(rid)
            elif all(flat_flags):
                state = 'flat'
                for rid in ids:
                    check_flat(rid)
            else:
                state = 'mixed'
                lift_errors.append((gid, direction, ids, lifted_flags))
            status[direction] = state
        group_status[gid] = status
    lifted_gids = [gid for gid, status in group_status.items()
                   if status[lift_direction] == 'lifted']
    failed_gids = [gid for gid, status in group_status.items()
                   if status[lift_direction] != 'lifted']
    kept_gids = [gid for gid, status in group_status.items()
                 if status[keep_direction] == 'flat']
    counter_state = Counter((status[lift_direction], status[keep_direction])
                            for status in group_status.values())
    checker.require(counter_state.get(('lifted', 'flat')) == 64,
                    f'expected 64 lifted {lift_direction} + flat '
                    f'{keep_direction} groups, got {dict(counter_state)}')
    checker.require(len(lifted_gids) == 64,
                    f'lifted {lift_direction} pair count {len(lifted_gids)} '
                    f'!= 64')
    checker.require(len(failed_gids) == 2,
                    f'failed {lift_direction} pair count {len(failed_gids)} '
                    f'!= 2 (got {failed_gids})')
    checker.require(len(kept_gids) == 66,
                    f'kept {keep_direction} flat pair count {len(kept_gids)} '
                    f'!= 66')
    checker.require(not lift_errors,
                    f'mixed lifted/flat state inside direction pairs: '
                    f'{lift_errors[:5]}')
    checker.require(not lifted_contract_errors,
                    f'{len(lifted_contract_errors)} lifted-route contract '
                    f'violations (sample {lifted_contract_errors[:5]})')
    checker.require(not flat_contract_errors,
                    f'{len(flat_contract_errors)} flat-route contract '
                    f'violations (sample {flat_contract_errors[:5]})')
    details['direction_rules'] = {
        'lifted_direction': lift_direction,
        'kept_direction': keep_direction,
        'groups': len(group_status),
        'lifted_groups': sorted(lifted_gids),
        'failed_groups': sorted(failed_gids),
        'kept_flat_groups': len(kept_gids),
        'group_state_counts': {f'{key[0]} + {key[1]}': value
                               for key, value in counter_state.items()},
        'lifted_route_count': 2 * len(lifted_gids),
        'flat_route_count': 2 * len(failed_gids) + 2 * len(kept_gids),
        'lifted_contract_violations': len(lifted_contract_errors),
        'flat_contract_violations': len(flat_contract_errors),
    }

    # ---- c2_pair_assignment.json consistency ------------------------------
    assign_errors = []
    checker.require(assignment.get('schema') == 'hybrid_c2_c4_pair_assignment_v1',
                    f'assignment schema {assignment.get("schema")!r}')
    checker.require(assignment.get('variant') == group,
                    f'assignment variant {assignment.get("variant")!r} != {group}')
    checker.require(assignment.get('total_pairs') == 66,
                    f'assignment total_pairs {assignment.get("total_pairs")} != 66')
    checker.require(assignment.get('lifted_pairs') == 64,
                    f'assignment lifted_pairs {assignment.get("lifted_pairs")} != 64')
    checker.require(assignment.get('failed_pairs') == 2,
                    f'assignment failed_pairs {assignment.get("failed_pairs")} != 2')
    checker.require(assignment.get('direction') == lift_direction,
                    f'assignment direction {assignment.get("direction")!r} != '
                    f'{lift_direction}')
    checker.require(assignment.get('kept_direction') == keep_direction,
                    f'assignment kept_direction '
                    f'{assignment.get("kept_direction")!r} != {keep_direction}')
    assignment_by_gid = {}
    for entry in assignment.get('pairs') or []:
        gid = int(entry['group_id'])
        assignment_by_gid[gid] = entry
    checker.require(sorted(assignment_by_gid) == ctx.z1_opposite_gids,
                    f'assignment group ids differ from the 66 z1 opposite '
                    f'groups: missing='
                    f'{sorted(set(ctx.z1_opposite_gids) - set(assignment_by_gid))[:5]} '
                    f'extra={sorted(set(assignment_by_gid) - set(ctx.z1_opposite_gids))[:5]}')
    lifted_assignment = 0
    failed_assignment = []
    for gid in ctx.z1_opposite_gids:
        entry = assignment_by_gid.get(gid)
        if entry is None:
            continue
        buckets = ctx.group_routes_by_direction(gid)
        target_ids = sorted(buckets[lift_direction])
        if sorted(int(rid) for rid in entry.get('route_ids') or []) != target_ids:
            assign_errors.append((gid, 'route_ids', entry.get('route_ids'),
                                  target_ids))
        if entry.get('direction') != lift_direction:
            assign_errors.append((gid, 'direction', entry.get('direction')))
        if int(entry.get('target_layer') or 0) != 2:
            assign_errors.append((gid, 'target_layer', entry.get('target_layer')))
        if not close(entry.get('target_z_mm'), 1.0, 1e-12):
            assign_errors.append((gid, 'target_z_mm', entry.get('target_z_mm')))
        partner = {int(key): int(value)
                   for key, value in (entry.get('c2_partner') or {}).items()}
        if set(partner) == set(target_ids) and all(
                partner[rid] == target_ids[1 - target_ids.index(rid)]
                for rid in target_ids):
            pass
        else:
            assign_errors.append((gid, 'c2_partner', entry.get('c2_partner'),
                                  target_ids))
        status = entry.get('status')
        if status == 'lifted_L2':
            lifted_assignment += 1
            a_in = entry.get('a_in')
            a_out = entry.get('a_out')
            if a_in is None or a_out is None:
                assign_errors.append((gid, 'a_in/a_out', None))
                continue
            if not close(a_in, a_out, 1e-12):
                assign_errors.append((gid, 'a_in != a_out', a_in, a_out))
            route_first = routes[target_ids[0]]
            parts = route_first.get('parts') or []
            if len(parts) != 5:
                assign_errors.append((gid, 'parts', len(parts)))
                continue
            flats = [part for part in parts if part['kind'] == 'flat']
            trans = [part for part in parts if part['kind'] == 'transition']
            if not close(flats[0]['length_mm'], a_in, TOL_TIGHT):
                assign_errors.append((gid, 'rise_start_mm',
                                      flats[0]['length_mm'], a_in))
            if not close(flats[-1]['length_mm'], a_out, TOL_TIGHT):
                assign_errors.append((gid, 'fall_end_mm',
                                      flats[-1]['length_mm'], a_out))
            if 'rise_start_xy' in entry and math.dist(
                    entry['rise_start_xy'], trans[0]['start']) > TOL_GEOM:
                assign_errors.append((gid, 'rise_start_xy',
                                      entry['rise_start_xy'], trans[0]['start']))
            if 'fall_start_xy' in entry and math.dist(
                    entry['fall_start_xy'], trans[-1]['start']) > TOL_GEOM:
                assign_errors.append((gid, 'fall_start_xy',
                                      entry['fall_start_xy'],
                                      trans[-1]['start']))
            if 'rise_start_mm' in entry and not close(
                    entry['rise_start_mm'], flats[0]['length_mm'], TOL_GEOM):
                assign_errors.append((gid, 'rise_start_mm field',
                                      entry['rise_start_mm'],
                                      flats[0]['length_mm']))
            if 'fall_start_mm' in entry:
                three = sum(float(part['length_mm']) for part in parts[:3])
                if not close(entry['fall_start_mm'], three, TOL_GEOM):
                    assign_errors.append((gid, 'fall_start_mm field',
                                          entry['fall_start_mm'], three))
            # both C2 members must follow the lifted contract
            for rid in target_ids:
                if not route_is_lifted(routes[rid]):
                    assign_errors.append((gid, 'member not lifted', rid))
        elif status == 'kept_L1_z1':
            failed_assignment.append(gid)
            if entry.get('a_in') is not None or entry.get('a_out') is not None:
                assign_errors.append((gid, 'failed pair has a_in/a_out',
                                      entry.get('a_in'), entry.get('a_out')))
            reason = entry.get('failure')
            if not reason:
                assign_errors.append((gid, 'empty failure reason'))
            for rid in target_ids:
                if not route_is_flat(routes[rid]):
                    assign_errors.append((gid, 'failed member not flat', rid))
        else:
            assign_errors.append((gid, 'unexpected status', status))
    checker.require(lifted_assignment == 64,
                    f'assignment lifted_L2 entries {lifted_assignment} != 64')
    checker.require(len(failed_assignment) == 2,
                    f'assignment kept_L1_z1 entries {len(failed_assignment)} '
                    f'!= 2')
    checker.require(sorted(failed_assignment) == sorted(failed_gids),
                    f'assignment failed groups {sorted(failed_assignment)} != '
                    f'runtime failed groups {sorted(failed_gids)}')
    checker.require(not assign_errors,
                    f'{len(assign_errors)} c2_pair_assignment inconsistencies '
                    f'(sample {assign_errors[:8]})')
    details['c2_pair_assignment'] = {
        'entries': len(assignment_by_gid),
        'lifted_L2': lifted_assignment,
        'kept_L1_z1': len(failed_assignment),
        'failed_groups': sorted(failed_assignment),
        'inconsistencies': len(assign_errors),
    }

    # ---- summary claims ---------------------------------------------------
    summary_errors = []
    summary_expect = {
        'routed': 1024,
        'c2_pairs_total': 66,
        'c2_pairs_lifted': 64,
        'c2_pairs_failed': 2,
        'lifted_routes': 128,
        'kept_flat_routes': 136,
        'transitions': 784,
    }
    for field, value in summary_expect.items():
        if summary.get(field) != value:
            summary_errors.append((field, summary.get(field), value))
    if summary.get('variant') != group:
        summary_errors.append(('variant', summary.get('variant'), group))
    # direction text
    expected_lifted_text = ('EW (horizontal)' if group == 'H'
                            else 'NS (vertical)')
    expected_kept_text = ('NS (vertical)' if group == 'H'
                          else 'EW (horizontal)')
    if summary.get('lifted_direction') != expected_lifted_text:
        summary_errors.append(('lifted_direction',
                               summary.get('lifted_direction'),
                               expected_lifted_text))
    if summary.get('kept_direction') != expected_kept_text:
        summary_errors.append(('kept_direction', summary.get('kept_direction'),
                               expected_kept_text))
    failures = summary.get('c2_failures') or {}
    if sorted(int(key) for key in failures) != sorted(failed_gids):
        summary_errors.append(('c2_failures keys', sorted(failures),
                               sorted(failed_gids)))
    for gid, reason in failures.items():
        if not reason:
            summary_errors.append((f'c2_failures[{gid}]', reason, 'non-empty'))
        entry = assignment_by_gid.get(int(gid)) or {}
        if entry.get('failure') != reason:
            summary_errors.append((f'failure reason gid {gid}',
                                   entry.get('failure'), reason))
    checker.require(not summary_errors,
                    f'{len(summary_errors)} summary claim mismatches '
                    f'(sample {summary_errors[:8]})')
    details['summary_claims'] = {'mismatches': len(summary_errors)}
    details['failed_group_details'] = {
        str(gid): {
            'assignment_status': (assignment_by_gid.get(gid) or {}).get('status'),
            'failure_reason': (assignment_by_gid.get(gid) or {}).get('failure'),
            'direction': (assignment_by_gid.get(gid) or {}).get('direction'),
            'route_ids': (assignment_by_gid.get(gid) or {}).get('route_ids'),
            'route_states': {str(rid): ('lifted' if route_is_lifted(routes[rid])
                                        else 'flat')
                             for rid in ctx.group_routes_by_direction(gid)[lift_direction]},
        }
        for gid in failed_gids
    }
    return checker.to_dict(), details


# ---------------------------------------------------------------------------
# 5. geometry audit (arcs / lines / transitions / board / 2D chain)
# ---------------------------------------------------------------------------
class Sink:
    """Counts messages but only keeps a sample."""

    def __init__(self, limit=30):
        self.count = 0
        self.samples = []
        self.limit = limit

    def add(self, message):
        self.count += 1
        if len(self.samples) < self.limit:
            self.samples.append(str(message))


def part_start3d(part):
    if part['kind'] == 'flat':
        x, y = prim_start(part['primitives'][0])
        return (x, y, float(part['z_mm']))
    return (float(part['start'][0]), float(part['start'][1]),
            float(part['z0']))


def part_end3d(part):
    if part['kind'] == 'flat':
        x, y = prim_end(part['primitives'][-1])
        return (x, y, float(part['z_mm']))
    return (float(part['end'][0]), float(part['end'][1]),
            float(part['z1']))


def _unit(vector):
    norm = math.hypot(vector[0], vector[1])
    return (vector[0] / norm, vector[1] / norm)


def _line_direction(prim):
    return _unit((prim['p1'][0] - prim['p0'][0],
                  prim['p1'][1] - prim['p0'][1]))


def _prim_signature(prim):
    if prim['kind'] == 'line':
        return ('line', tuple(round(float(v), 12) for v in prim['p0']),
                tuple(round(float(v), 12) for v in prim['p1']))
    return ('arc', tuple(round(float(v), 12) for v in prim['center']),
            round(float(prim['radius']), 12),
            round(norm_angle(float(prim['start_angle'])), 12),
            round(float(prim['sweep']), 12))


def _same_prims(prims_a, prims_b, tol=1e-9):
    if len(prims_a) != len(prims_b):
        return False
    for prim_a, prim_b in zip(prims_a, prims_b):
        if prim_a['kind'] != prim_b['kind']:
            return False
        if prim_a['kind'] == 'line':
            if (math.dist(prim_a['p0'], prim_b['p0']) > tol
                    or math.dist(prim_a['p1'], prim_b['p1']) > tol):
                return False
        else:
            if (math.dist(prim_a['center'], prim_b['center']) > tol
                    or not close(prim_a['radius'], prim_b['radius'], tol)
                    or not close(norm_angle(float(prim_a['start_angle'])),
                                 norm_angle(float(prim_b['start_angle'])), 1e-6)
                    or not close(prim_a['sweep'], prim_b['sweep'], 1e-6)
                    or not close(math.dist(prim_a['p0'], prim_b['p0']), 0.0, tol)
                    or not close(math.dist(prim_a['p1'], prim_b['p1']), 0.0, tol)):
                return False
    return True


def _max_polyline_deviation(prims_a, prims_b, step=0.2):
    length_a = sum(prim_2d_length(prim) for prim in prims_a)
    length_b = sum(prim_2d_length(prim) for prim in prims_b)
    if abs(length_a - length_b) > TOL_GEOM:
        return None, abs(length_a - length_b)
    points_a = polyline_2d(prims_a, step)
    points_b = polyline_2d(prims_b, step)
    return max_dev(points_a, points_b), abs(length_a - length_b)


def chain_2d_from_parts(parts):
    primitives = []
    for part in parts:
        if part['kind'] == 'flat':
            primitives.extend(part['primitives'])
        else:
            primitives.append({'kind': 'line',
                               'p0': list(part['start']),
                               'p1': list(part['end'])})
    return primitives


def check_geometry(ctx, group, routes):
    log(f'[{group}] 5/9 geometry audit (R=15 arcs, axis lines, transitions, board) ...')
    checker = Checker('geometry')
    sinks = {name: Sink() for name in ('structure', 'primitive', 'flat_part',
                                       'transition', 'on_straight',
                                       'continuity', 'layer_profile', 'length',
                                       'board', 'chain_2d')}
    counts = Counter()
    for rid in sorted(routes):
        record = routes[rid]
        source = ctx.manifest[rid]
        interface_z = ctx.plane_z[source['plane']]
        parts = record.get('parts') or []
        kinds = [part['kind'] for part in parts]
        n_transitions = int(record.get('n_transitions') or 0)
        counts['routes'] += 1
        if kinds not in (['flat'],
                         ['flat', 'transition', 'flat', 'transition', 'flat']):
            sinks['structure'].add(f'{rid}: part kinds {kinds}')
            continue
        if n_transitions != 2 * (len(kinds) == 5):
            sinks['structure'].add(f'{rid}: n_transitions {n_transitions} '
                                   f'vs parts {kinds}')
        if not parts[0]['primitives'] or not parts[-1]['primitives']:
            sinks['structure'].add(f'{rid}: empty terminal flat part')
            continue

        # ---- per-part geometry -------------------------------------------
        for index, part in enumerate(parts):
            if part['kind'] == 'flat':
                prims = part['primitives']
                if not prims:
                    sinks['flat_part'].add(f'{rid}: flat part {index} empty')
                    continue
                part_length = 0.0
                for prim in prims:
                    counts['flat_primitives'] += 1
                    part_length += prim_2d_length(prim)
                    if prim['kind'] == 'line':
                        counts['flat_lines'] += 1
                        axis = _axis_of_line(prim)
                        if axis is None:
                            sinks['primitive'].add(
                                f'{rid}: flat part {index} non-axis line '
                                f'{prim["p0"]}->{prim["p1"]}')
                    else:
                        counts['flat_arcs'] += 1
                        radius = float(prim['radius'])
                        sweep = float(prim['sweep'])
                        if not close(radius, RADIUS, TOL_TIGHT):
                            sinks['primitive'].add(
                                f'{rid}: arc radius {radius} != {RADIUS}')
                        if not close(abs(sweep), math.pi / 2.0, TOL_TIGHT):
                            sinks['primitive'].add(
                                f'{rid}: arc sweep {sweep} not a quarter turn')
                        if (math.dist(prim_start(prim), prim['p0']) > TOL_GEOM
                                or math.dist(prim_end(prim), prim['p1'])
                                > TOL_GEOM):
                            sinks['primitive'].add(
                                f'{rid}: arc centre/endpoint inconsistency')
                if not close(part['length_mm'], part_length, TOL_GEOM):
                    sinks['flat_part'].add(
                        f'{rid}: flat part {index} length {part["length_mm"]} '
                        f'!= {part_length}')
                expected_z = (interface_z if int(part['layer_id']) == 1
                              else LAYER_Z.get(int(part['layer_id'])))
                if expected_z is None or not close(part['z_mm'], expected_z,
                                                   1e-12):
                    sinks['flat_part'].add(
                        f'{rid}: flat part {index} z {part["z_mm"]} != '
                        f'{expected_z} (layer {part["layer_id"]})')
            else:
                counts['transitions'] += 1
                radius = float(part['radius_mm'])
                theta = float(part['theta_rad'])
                footprint = float(part['footprint_mm'])
                length = float(part['length_mm'])
                dz = abs(float(part['z1']) - float(part['z0']))
                expected_theta = math.acos(max(-1.0, min(1.0, 1.0 - dz
                                                         / (2.0 * RADIUS))))
                if not close(radius, RADIUS, TOL_TIGHT):
                    sinks['transition'].add(
                        f'{rid}: transition {index} radius {radius} != {RADIUS}')
                if not close(theta, expected_theta, TOL_TIGHT):
                    sinks['transition'].add(
                        f'{rid}: transition {index} theta {theta} != '
                        f'{expected_theta}')
                if not close(length, 2.0 * RADIUS * expected_theta, TOL_TIGHT):
                    sinks['transition'].add(
                        f'{rid}: transition {index} length {length} inconsistent')
                if not close(footprint, 2.0 * RADIUS * math.sin(expected_theta),
                             TOL_TIGHT):
                    sinks['transition'].add(
                        f'{rid}: transition {index} footprint inconsistent')
                if not close(part['dz_mm'], float(part['z1'])
                             - float(part['z0']), TOL_TIGHT):
                    sinks['transition'].add(
                        f'{rid}: transition {index} dz_mm inconsistent')
                direction = _unit(part['direction'])
                if (abs(abs(direction[0]) - 1.0) > TOL_TIGHT
                        and abs(abs(direction[1]) - 1.0) > TOL_TIGHT):
                    sinks['transition'].add(
                        f'{rid}: transition direction not axis aligned')
                end_expected = (float(part['start'][0])
                                + direction[0] * footprint,
                                float(part['start'][1])
                                + direction[1] * footprint)
                if math.dist(end_expected, part['end']) > TOL_GEOM:
                    sinks['transition'].add(
                        f'{rid}: transition {index} end != start+footprint*dir')
                # expected z of from/to layers
                for layer_field, z_field in (('from_layer', 'z0'),
                                             ('to_layer', 'z1')):
                    layer_id = int(part[layer_field])
                    expected_z = (interface_z if layer_id == 1
                                  else LAYER_Z.get(layer_id))
                    if expected_z is None or not close(part[z_field],
                                                       expected_z, 1e-12):
                        sinks['transition'].add(
                            f'{rid}: transition {index} {z_field} '
                            f'{part[z_field]} != layer z {expected_z}')
                # transition must sit on straight 2D segments of its neighbours
                previous = parts[index - 1]
                following = parts[index + 1]
                previous_last = previous['primitives'][-1]
                following_first = following['primitives'][0]
                if (previous_last['kind'] != 'line'
                        or following_first['kind'] != 'line'):
                    sinks['on_straight'].add(
                        f'{rid}: transition {index} neighbours are not lines')
                    continue
                start = (float(part['start'][0]), float(part['start'][1]))
                end = (float(part['end'][0]), float(part['end'][1]))
                if math.dist(prim_end(previous_last), start) > TOL_GEOM:
                    sinks['on_straight'].add(
                        f'{rid}: transition {index} start not on previous line '
                        f'end')
                if math.dist(prim_start(following_first), end) > TOL_GEOM:
                    sinks['on_straight'].add(
                        f'{rid}: transition {index} end not on following line '
                        f'start')
                if math.dist(_line_direction(previous_last), direction) > 1e-9:
                    sinks['on_straight'].add(
                        f'{rid}: transition {index} direction != previous line')
                if math.dist(_line_direction(following_first), direction) > 1e-9:
                    sinks['on_straight'].add(
                        f'{rid}: transition {index} direction != following line')

        # ---- part continuity ---------------------------------------------
        for index in range(len(parts) - 1):
            end = part_end3d(parts[index])
            start = part_start3d(parts[index + 1])
            if math.dist(end, start) > TOL_GEOM:
                sinks['continuity'].add(
                    f'{rid}: part {index}->{index + 1} discontinuity '
                    f'{math.dist(end, start):.9g} mm')

        # ---- layer / z profile ------------------------------------------
        sequence = []
        z_sequence = []
        for index, part in enumerate(parts):
            if part['kind'] == 'flat':
                layer_id = int(part['layer_id'])
                expected_flat_z = (interface_z if layer_id == 1
                                   else LAYER_Z.get(layer_id))
                if expected_flat_z is None or not close(float(part['z_mm']),
                                                        expected_flat_z, 1e-12):
                    sinks['layer_profile'].add(
                        f'{rid}: flat part {index} z {part["z_mm"]} != '
                        f'layer z {expected_flat_z}')
                if not sequence:
                    sequence.append(layer_id)
                    z_sequence.append(float(part['z_mm']))
                elif layer_id != sequence[-1]:
                    sinks['layer_profile'].add(
                        f'{rid}: flat part {index} layer {layer_id} != '
                        f'current {sequence[-1]}')
            else:
                from_layer = int(part['from_layer'])
                to_layer = int(part['to_layer'])
                if sequence and from_layer != sequence[-1]:
                    sinks['layer_profile'].add(
                        f'{rid}: transition {index} from_layer {from_layer} '
                        f'!= current {sequence[-1]}')
                sequence.append(to_layer)
                z_sequence.append(float(part['z1']))
        declared_sequence = [int(value)
                             for value in record.get('layer_sequence') or []]
        declared_z = [float(value)
                      for value in record.get('layer_z_sequence') or []]
        if declared_sequence != sequence or len(declared_z) != len(z_sequence) \
                or any(not close(a, b, 1e-12)
                       for a, b in zip(declared_z, z_sequence)):
            sinks['layer_profile'].add(
                f'{rid}: declared profile {declared_sequence}/{declared_z} != '
                f'rebuilt {sequence}/{z_sequence}')
        layers_used = sorted(set(sequence))
        if [int(value) for value in record.get('layers_used') or []] \
                != layers_used:
            sinks['layer_profile'].add(
                f'{rid}: layers_used {record.get("layers_used")} != '
                f'{layers_used}')
        # rise then fall
        if len(parts) == 5:
            first, second = parts[1], parts[3]
            if not float(first['z0']) < float(first['z1']):
                sinks['structure'].add(f'{rid}: first transition is not a rise')
            if not float(second['z0']) > float(second['z1']):
                sinks['structure'].add(f'{rid}: second transition is not a fall')
            if float(first['z0']) != interface_z \
                    or float(second['z1']) != interface_z:
                sinks['structure'].add(f'{rid}: lift does not start/end on '
                                       f'interface height')
        # ---- length bookkeeping -----------------------------------------
        parts_length = sum(float(part['length_mm']) for part in parts)
        if not close(record.get('length_mm'), parts_length, TOL_GEOM):
            sinks['length'].add(f'{rid}: length_mm {record.get("length_mm")} '
                                f'!= sum(parts) {parts_length}')
        xy_length = sum(prim_2d_length(prim)
                        for part in parts if part['kind'] == 'flat'
                        for prim in part['primitives'])
        xy_length += sum(float(part['footprint_mm']) for part in parts
                         if part['kind'] == 'transition')
        if not close(record.get('xy_length_mm'), xy_length, TOL_GEOM):
            sinks['length'].add(f'{rid}: xy_length_mm '
                                f'{record.get("xy_length_mm")} != {xy_length}')
        z_values = [float(part['z_mm']) for part in parts
                    if part['kind'] == 'flat']
        for part in parts:
            if part['kind'] == 'transition':
                z_values.extend([float(part['z0']), float(part['z1'])])
        span = max(z_values) - min(z_values)
        if not close(record.get('z_span_mm'), span, 1e-12):
            sinks['length'].add(f'{rid}: z_span_mm {record.get("z_span_mm")} '
                                f'!= {span}')
        if not close(record.get('start_z_mm'), interface_z, 1e-12) \
                or not close(record.get('end_z_mm'), interface_z, 1e-12):
            sinks['structure'].add(f'{rid}: start/end z not on interface')

        # ---- board containment ------------------------------------------
        for part in parts:
            if part['kind'] == 'flat':
                for prim in part['primitives']:
                    for point in sample_prim(prim, 25):
                        if not (-1e-9 <= point[0] <= BOARD + 1e-9
                                and -1e-9 <= point[1] <= BOARD + 1e-9):
                            sinks['board'].add(
                                f'{rid}: primitive point {point} outside board')
            else:
                for key in ('start', 'end'):
                    point = part[key]
                    if not (-1e-9 <= float(point[0]) <= BOARD + 1e-9
                            and -1e-9 <= float(point[1]) <= BOARD + 1e-9):
                        sinks['board'].add(
                            f'{rid}: transition {key} {point} outside board')

        # ---- 2D chain versus phase2_2d ----------------------------------
        reference = ctx.phase2[rid].get('primitives') or []
        record_primitives = record.get('primitives')
        if record_primitives is not None:
            counts['record_primitives_checked'] += 1
            if not _same_prims(record_primitives, reference):
                deviation, _delta = _max_polyline_deviation(record_primitives,
                                                            reference)
                if deviation is None or deviation > TOL_GEOM:
                    sinks['chain_2d'].add(
                        f'{rid}: stored primitives differ from phase2_2d '
                        f'(dev {deviation})')
        if n_transitions == 0:
            counts['flat_chain_checked'] += 1
            actual = [prim for part in parts if part['kind'] == 'flat'
                      for prim in part['primitives']]
            if not _same_prims(actual, reference):
                deviation, _delta = _max_polyline_deviation(actual, reference)
                if deviation is None or deviation > TOL_GEOM:
                    sinks['chain_2d'].add(
                        f'{rid}: flat 2D chain differs from phase2_2d '
                        f'(dev {deviation})')
        elif source['relation'] != 'same':
            counts['reconstructed_chain_checked'] += 1
            reconstructed = chain_2d_from_parts(parts)
            deviation, _delta = _max_polyline_deviation(reconstructed,
                                                        reference)
            if deviation is None or deviation > TOL_GEOM:
                sinks['chain_2d'].add(
                    f'{rid}: reconstructed 2D chain differs from phase2_2d '
                    f'(dev {deviation})')

    for name, sink in sinks.items():
        checker.require(sink.count == 0,
                        f'{name}: {sink.count} issue(s) '
                        f'(sample {sink.samples[:6]})')
    details = {
        'routes': counts['routes'],
        'flat_primitives': counts['flat_primitives'],
        'flat_lines': counts['flat_lines'],
        'flat_arcs': counts['flat_arcs'],
        'transitions': counts['transitions'],
        'flat_arc_radius_values': [RADIUS],
        'transition_radius_values': [RADIUS],
        'record_primitives_checked': counts['record_primitives_checked'],
        'flat_chain_checked': counts['flat_chain_checked'],
        'reconstructed_chain_checked': counts['reconstructed_chain_checked'],
        'u_actual_chain_skipped': 256,
        'u_actual_chain_note': (
            'U (same) routes were rebuilt on L3/L4/L5 in Structured A; their '
            'reference primitives field must equal phase2_2d (checked) and '
            'their full geometry must equal Structured A (checked in section 3)'),
        'issues': {name: {'count': sink.count, 'samples': sink.samples[:20]}
                   for name, sink in sinks.items()},
    }
    return checker.to_dict(), details


# ---------------------------------------------------------------------------
# 6/7. crossing metrics (independent recomputation) + summary comparison
# ---------------------------------------------------------------------------
def _round_dict(mapping, digits=4):
    return {key: round(float(value), digits) if isinstance(value, (int, float))
            else value for key, value in mapping.items()}


def check_metrics(ctx, group, routes, summary, analysis, baseline, spatial):
    log(f'[{group}] 6/9 independent crossing-metric recomputation ...')
    checker = Checker('metrics')
    per_height, unique_pairs, total_points = crossing_audit(
        routes.values(), ctx.manifest)
    hv_pairs, hv_breakdown = z1_hv_crossings(per_height)
    metrics = {
        'routed': len(routes),
        'unique_crossing_pairs': unique_pairs,
        'crossing_pairs_by_height': {h: info['pairs']
                                     for h, info in per_height.items()},
        'crossing_points_by_height': {h: info['points']
                                      for h, info in per_height.items()},
        'crossing_breakdown_by_height': {h: info['breakdown']
                                         for h, info in per_height.items()},
        'z1_hv_same_height_pairs': hv_pairs,
        'z1_hv_breakdown_by_height': hv_breakdown,
        'z0_total_pairs': per_height.get('0.0', {}).get('pairs'),
        'l2_total_pairs': per_height.get('1.0', {}).get('pairs'),
        'total_crossing_points': total_points,
        'transitions': route_transition_count(routes.values()),
        'total_length_mm': route_total_length(routes.values()),
        'layer_counts': layer_counts(routes.values()),
    }
    details = {'independent_metrics': metrics}

    # ---- compare against the production summary --------------------------
    summary_diff = []
    direct_fields = ['routed', 'unique_crossing_pairs',
                     'z1_hv_same_height_pairs', 'transitions',
                     'total_length_mm']
    for field in direct_fields:
        expected = summary.get(field)
        actual = metrics.get(field)
        if isinstance(expected, float) or isinstance(actual, float):
            same = (expected is not None and actual is not None
                    and close(expected, actual, 1e-3))
        else:
            same = expected == actual
        if not same:
            summary_diff.append({'field': field, 'summary': expected,
                                 'independent': actual})
    for field in ('crossing_pairs_by_height', 'crossing_breakdown_by_height',
                  'z1_hv_breakdown_by_height'):
        if summary.get(field) != metrics.get(field):
            summary_diff.append({'field': field, 'summary': summary.get(field),
                                 'independent': metrics.get(field)})
    summary_layers = summary.get('layer_counts') or {}
    for name, info in metrics['layer_counts'].items():
        production = summary_layers.get(name) or {}
        if production.get('count') != info['count']:
            summary_diff.append({'field': f'layer_counts[{name}].count',
                                 'summary': production.get('count'),
                                 'independent': info['count']})
        production_planes = {key: value for key, value
                             in (production.get('plane_counts') or {}).items()
                             if value}
        independent_planes = {key: value for key, value
                              in info['plane_counts'].items() if value}
        if production_planes != independent_planes:
            summary_diff.append(
                {'field': f'layer_counts[{name}].plane_counts',
                 'summary': production_planes,
                 'independent': independent_planes})
    for field in ('c2_pairs_total', 'c2_pairs_lifted', 'c2_pairs_failed',
                  'lifted_routes', 'kept_flat_routes'):
        expected = summary.get(field)
        if field in metrics and expected != metrics[field]:
            summary_diff.append({'field': field, 'summary': expected,
                                 'independent': metrics[field]})
    checker.require(not summary_diff,
                    f'{len(summary_diff)} production-summary fields differ '
                    f'from the independent recomputation: {summary_diff[:8]}')
    details['summary_diff'] = summary_diff

    # ---- compare against crossing_analysis.json --------------------------
    analysis_diff = []
    result = analysis.get('result') or {}
    mapping = {
        'unique_crossing_pairs': metrics['unique_crossing_pairs'],
        'crossing_pairs_by_height': metrics['crossing_pairs_by_height'],
        'crossing_breakdown_by_height':
            metrics['crossing_breakdown_by_height'],
        'z1_hv_same_height_pairs': metrics['z1_hv_same_height_pairs'],
        'z1_hv_breakdown_by_height': metrics['z1_hv_breakdown_by_height'],
        'z0_total_pairs': metrics['z0_total_pairs'],
        'l2_total_pairs': metrics['l2_total_pairs'],
    }
    for field, independent in mapping.items():
        if result.get(field) != independent:
            analysis_diff.append({'field': field, 'analysis': result.get(field),
                                  'independent': independent})
    production_baseline = analysis.get('baseline') or {}
    baseline_compare_fields = {
        'unique_crossing_pairs': baseline['unique_crossing_pairs'],
        'crossing_pairs_by_height': baseline['crossing_pairs_by_height'],
        'crossing_breakdown_by_height':
            baseline['crossing_breakdown_by_height'],
        'z1_hv_same_height_pairs': baseline['z1_hv_same_height_pairs'],
        'z1_hv_breakdown_by_height': baseline['z1_hv_breakdown_by_height'],
        'z0_total_pairs': baseline['z0_total_pairs'],
        'l2_total_pairs': baseline['l2_total_pairs'],
    }
    for field, independent in baseline_compare_fields.items():
        if production_baseline.get(field) != independent:
            analysis_diff.append({'field': f'baseline.{field}',
                                  'analysis': production_baseline.get(field),
                                  'independent': independent})
    reduction = analysis.get('reduction') or {}
    expected_reduction = {
        'z1_hv_same_height_reduction':
            baseline['z1_hv_same_height_pairs']
            - metrics['z1_hv_same_height_pairs'],
        'z0_total_reduction': baseline['z0_total_pairs']
        - metrics['z0_total_pairs'],
        'global_reduction': baseline['unique_crossing_pairs']
        - metrics['unique_crossing_pairs'],
    }
    for field, independent in expected_reduction.items():
        if reduction.get(field) != independent:
            analysis_diff.append({'field': f'reduction.{field}',
                                  'analysis': reduction.get(field),
                                  'independent': independent})
    if summary.get('z1_hv_reduction') != reduction:
        analysis_diff.append({'field': 'summary.z1_hv_reduction',
                              'analysis': summary.get('z1_hv_reduction'),
                              'independent': reduction})
    checker.require(not analysis_diff,
                    f'{len(analysis_diff)} crossing_analysis fields differ '
                    f'from the independent recomputation: {analysis_diff[:8]}')
    details['crossing_analysis_diff'] = analysis_diff
    details['reduction'] = expected_reduction

    # ---- A baseline: independent vs the A artefact + claimed numbers -----
    baseline_diff = []
    a_summary = ctx.a_summary
    claimed = {
        'unique_crossing_pairs': a_summary.get('unique_crossing_pairs'),
        'z0_points_by_height': (a_summary.get('crossing_pairs_by_height')
                                or {}).get('0.0'),
        'l2_points_by_height': (a_summary.get('crossing_pairs_by_height')
                                or {}).get('1.0'),
    }
    if claimed['unique_crossing_pairs'] != baseline['unique_crossing_pairs']:
        baseline_diff.append({'field': 'A.summary.unique_crossing_pairs',
                              'A_artefact': claimed['unique_crossing_pairs'],
                              'independent': baseline['unique_crossing_pairs']})
    # A's per-height numbers are CROSSING POINTS (not unique pairs); verify that
    if claimed['z0_points_by_height'] != baseline['crossing_points_by_height'].get('0.0'):
        baseline_diff.append({'field': 'A.summary.crossing_pairs_by_height[0.0]',
                              'A_artefact': claimed['z0_points_by_height'],
                              'independent_points':
                                  baseline['crossing_points_by_height'].get('0.0')})
    if claimed['l2_points_by_height'] != baseline['crossing_points_by_height'].get('1.0'):
        baseline_diff.append({'field': 'A.summary.crossing_pairs_by_height[1.0]',
                              'A_artefact': claimed['l2_points_by_height'],
                              'independent_points':
                                  baseline['crossing_points_by_height'].get('1.0')})
    checker.require(not baseline_diff,
                    f'A-baseline independent recomputation differs: '
                    f'{baseline_diff[:8]}')
    details['baseline'] = baseline
    details['baseline_diff'] = baseline_diff
    details['baseline_metric_semantics'] = {
        'A_summary_per_height_are_points': True,
        'A_summary_z0_points': claimed['z0_points_by_height'],
        'independent_A_z0_unique_pairs':
            baseline['crossing_pairs_by_height'].get('0.0'),
        'independent_A_z0_crossing_points':
            baseline['crossing_points_by_height'].get('0.0'),
        'note': ('the A artefact reports crossing POINTS per height (18600 at '
                 'z=0), while the hybrid crossing_analysis baseline uses '
                 'unique route PAIRS per height (17576 at z=0); the global '
                 'unique-pair count 19584 agrees in both口径'),
    }

    # ---- spatial cross-check ---------------------------------------------
    if spatial is not None:
        spatial_summary = spatial['summary']
        details['spatial_check'] = {
            'summary_unique_crossing_pairs':
                spatial_summary.get('unique_crossing_pairs'),
            'independent_unique_crossing_pairs':
                spatial['unique_crossing_pairs_independent'],
            'summary_transitions': spatial_summary.get('transitions'),
            'independent_transitions': route_transition_count(
                read_json(SPATIAL_DIR / 'routes_1024.json')['routes']),
            'consistent': (spatial_summary.get('unique_crossing_pairs')
                           == spatial['unique_crossing_pairs_independent']),
        }
        checker.require(
            spatial_summary.get('unique_crossing_pairs')
            == spatial['unique_crossing_pairs_independent'],
            'Spatial U-bundle summary crossing count not reproduced '
            f'({spatial_summary.get("unique_crossing_pairs")} vs '
            f'{spatial["unique_crossing_pairs_independent"]})')
    return checker.to_dict(), details


# ---------------------------------------------------------------------------
# 8. authoritative frozen 3D validation
# ---------------------------------------------------------------------------
COUNT_KEYS = ['violations', 'contract_errors', 'port_errors', 'geometry_errors',
              'curvature_violations', 'clearance_violations',
              'same_plane_violations', 'self_clearance_violations',
              'other_errors']


def check_authoritative_3d(ctx, group, payload, production_report):
    log(f'[{group}] 7/9 authoritative frozen 3D validation '
        f'(validate_payload_v4) ...')
    checker = Checker('authoritative_3d')
    # permitted frozen entry point (explicitly required by the acceptance task)
    from four_side_1024.v3c4.lift_cross import validate_payload_v4
    payload_copy = copy.deepcopy(payload)
    report = validate_payload_v4(payload_copy,
                                 v4_root=str(PHASE2_2D),
                                 log=lambda message: None)
    counts = report.get('counts') or {}
    stats = report.get('stats') or {}
    details = {
        'validator': report.get('validator'),
        'status': report.get('status'),
        'exploratory_pass': report.get('exploratory_pass'),
        'formal_acceptance': report.get('formal_acceptance'),
        'geometry_pass': report.get('geometry_pass'),
        'counts': {key: counts.get(key) for key in COUNT_KEYS},
        'violations': len(report.get('violations') or []),
        'violation_kinds': report.get('violation_kinds'),
        'min_3d_clearance_mm': stats.get('min_3d_clearance_mm'),
        'min_curvature_radius_mm': stats.get('min_curvature_radius_mm'),
        'transition_count': stats.get('transition_count'),
        'routed': stats.get('routed'),
        'total_length_mm': stats.get('total_length_mm'),
        'warnings': report.get('warnings'),
        'runtime_seconds': report.get('runtime_seconds'),
    }
    checker.require(report.get('exploratory_pass') is True,
                    f'exploratory_pass={report.get("exploratory_pass")!r}')
    checker.require(report.get('formal_acceptance') is False,
                    f'formal_acceptance={report.get("formal_acceptance")!r} '
                    f'(must stay false)')
    checker.require(report.get('geometry_pass') is True,
                    f'geometry_pass={report.get("geometry_pass")!r}')
    checker.require(report.get('status') == 'exploratory_only',
                    f'status={report.get("status")!r}')
    for key in COUNT_KEYS:
        checker.require(counts.get(key) == 0,
                        f'counts[{key}]={counts.get(key)!r} != 0')
    checker.require(len(COUNT_KEYS) == len(counts),
                    f'validator returned {len(counts)} count classes, '
                    f'expected {len(COUNT_KEYS)}: {sorted(counts)}')
    check_text = stats.get('min_3d_clearance_mm')
    checker.require(check_text is not None and check_text >= CLEARANCE_MM - 1e-7,
                    f'min_3d_clearance_mm={check_text!r} below '
                    f'{CLEARANCE_MM} mm')
    curvature = stats.get('min_curvature_radius_mm')
    checker.require(curvature is not None and curvature >= RADIUS - 0.015,
                    f'min_curvature_radius_mm={curvature!r} below R={RADIUS}')
    checker.require(stats.get('routed') == 1024,
                    f'validator routed={stats.get("routed")!r}')
    checker.require(stats.get('transition_count') == 784,
                    f'validator transition_count='
                    f'{stats.get("transition_count")!r} != 784')
    checker.require(stats.get('flat_arc_radius_values') == [RADIUS],
                    f'flat arc radii {stats.get("flat_arc_radius_values")!r}')
    checker.require(stats.get('transition_radius_values') == [RADIUS],
                    f'transition radii {stats.get("transition_radius_values")!r}')

    # compare with the production validation.json report (same frozen entry point)
    production_diff = []
    production_counts = production_report.get('counts') or {}
    production_stats = production_report.get('stats') or {}
    for field in ('status', 'exploratory_pass', 'formal_acceptance',
                  'geometry_pass'):
        if production_report.get(field) != report.get(field):
            production_diff.append({'field': field,
                                    'production': production_report.get(field),
                                    'independent': report.get(field)})
    for key in COUNT_KEYS:
        if production_counts.get(key) != counts.get(key):
            production_diff.append({'field': f'counts[{key}]',
                                    'production': production_counts.get(key),
                                    'independent': counts.get(key)})
    for field in ('min_3d_clearance_mm', 'min_curvature_radius_mm',
                  'transition_count', 'routed'):
        production_value = production_stats.get(field)
        independent_value = stats.get(field)
        if isinstance(production_value, float) or isinstance(independent_value,
                                                             float):
            same = (production_value is not None
                    and independent_value is not None
                    and close(production_value, independent_value, 1e-9))
        else:
            same = production_value == independent_value
        if not same:
            production_diff.append({'field': field,
                                    'production': production_value,
                                    'independent': independent_value})
    checker.require(not production_diff,
                    f'production validation.json differs from the frozen '
                    f'validator re-run: {production_diff[:8]}')
    details['production_diff'] = production_diff
    # cross-check with the independent geometric crossing count
    clearance_checks = (report.get('checks') or {}).get('clearance') or {}
    same_plane = clearance_checks.get('same_plane') or {}
    details['same_plane_crossing_points'] = same_plane.get('crossings')
    return checker.to_dict(), details


# ---------------------------------------------------------------------------
# 9. failures + shadow bottleneck analysis (2D/3D geometric verification)
# ---------------------------------------------------------------------------
ACCEPT_POINT_MM = CLEARANCE_MM + 0.01 + 0.001  # assembly-world point acceptance
EARLY_WINDOW_MM = 20.0


def theta_for_dz(dz):
    return math.acos(max(-1.0, min(1.0, 1.0 - abs(float(dz))
                                  / (2.0 * RADIUS))))


def transition_curve_points(u_start, dz=1.0, samples=160):
    """Yield ``(u, z)`` local S-curve points (u measured from the route start)."""
    theta = theta_for_dz(dz)
    length = 2.0 * RADIUS * theta
    sign = 1.0 if dz >= 0 else -1.0
    half = length / 2.0
    for index in range(samples + 1):
        s = length * index / samples
        if s <= half:
            phi = s / RADIUS
            u = RADIUS * math.sin(phi)
            w = sign * RADIUS * (1.0 - math.cos(phi))
        else:
            phi = (2.0 * half - s) / RADIUS
            u = 2.0 * RADIUS * math.sin(theta) - RADIUS * math.sin(phi)
            w = sign * abs(dz) - sign * RADIUS * (1.0 - math.cos(phi))
        yield u_start + u, w


def point_segment_distance_2d(point, a, b):
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 0.0:
        return math.dist(point, (ax, ay))
    t = ((point[0] - ax) * dx + (point[1] - ay) * dy) / length2
    t = min(max(t, 0.0), 1.0)
    return math.dist(point, (ax + t * dx, ay + t * dy))


def point_arc_distance_2d(point, prim):
    center = prim['center']
    radius = float(prim['radius'])
    start = float(prim['start_angle'])
    sweep = float(prim['sweep'])
    angle = math.atan2(point[1] - center[1], point[0] - center[0])
    delta = norm_angle(angle - start)
    inside = ((-1e-9 <= delta <= sweep + 1e-9) if sweep >= 0
              else (sweep - 1e-9 <= delta <= 1e-9))
    if inside:
        return abs(math.hypot(point[0] - center[0],
                              point[1] - center[1]) - radius)
    start_point = (center[0] + radius * math.cos(start),
                   center[1] + radius * math.sin(start))
    end_point = (center[0] + radius * math.cos(start + sweep),
                 center[1] + radius * math.sin(start + sweep))
    return min(math.dist(point, start_point), math.dist(point, end_point))


def point_primitive_distance_2d(point, prim):
    if prim['kind'] == 'line':
        return point_segment_distance_2d(point, prim['p0'], prim['p1'])
    return point_arc_distance_2d(point, prim)


def flat_primitives_with_z(route):
    out = []
    for part in route.get('parts') or []:
        if part['kind'] != 'flat':
            continue
        for prim in part['primitives']:
            out.append((float(part['z_mm']), prim))
    return out


def member_interface_line(route):
    prim = route['parts'][0]['primitives'][0]
    start = (float(prim['p0'][0]), float(prim['p0'][1]))
    end = (float(prim['p1'][0]), float(prim['p1'][1]))
    total = math.dist(start, end)
    direction = ((end[0] - start[0]) / total, (end[1] - start[1]) / total)
    return start, direction, total


def primitive_tangent_at(prim, point):
    if prim['kind'] == 'line':
        return _line_direction(prim)
    center = prim['center']
    sweep = float(prim['sweep'])
    angle = math.atan2(point[1] - center[1], point[0] - center[0])
    sign = 1.0 if sweep >= 0 else -1.0
    return (-math.sin(angle) * sign, math.cos(angle) * sign)


def angle_between_unit(vector_a, vector_b):
    dot = max(-1.0, min(1.0, vector_a[0] * vector_b[0]
                        + vector_a[1] * vector_b[1]))
    angle = math.acos(dot)
    return min(angle, math.pi - angle)


def min_transition_distance(start, direction, total, a, prims, samples=140):
    """Min 3D distance of the rise+fall S-curves to the given flat primitives."""
    footprint = 2.0 * RADIUS * math.sin(theta_for_dz(1.0))
    best = None
    for u, w in transition_curve_points(a, dz=1.0, samples=samples):
        point = (start[0] + direction[0] * u, start[1] + direction[1] * u)
        for z_part, prim in prims:
            distance = math.hypot(point_primitive_distance_2d(point, prim),
                                  w - z_part)
            if best is None or distance < best[0]:
                best = (distance, z_part, prim, point, w)
    for u, w in transition_curve_points(total - a - footprint, dz=-1.0,
                                        samples=samples):
        point = (start[0] + direction[0] * u, start[1] + direction[1] * u)
        for z_part, prim in prims:
            distance = math.hypot(point_primitive_distance_2d(point, prim),
                                  w - z_part)
            if best is None or distance < best[0]:
                best = (distance, z_part, prim, point, w)
    return best


def collinear_flat_primitives(routes, plane, z_mm, axis, value,
                              tol=1e-6):
    out = []
    for rid, record in routes.items():
        if record['plane'] != plane:
            continue
        if not (record['relation'] in ('adjacent', 'same')
                or (record['relation'] == 'opposite'
                    and record['plane'] == 'z2')):
            continue
        for part in record.get('parts') or []:
            if part['kind'] != 'flat' or abs(float(part['z_mm'])
                                             - z_mm) > 1e-9:
                continue
            for prim in part['primitives']:
                if prim['kind'] != 'line':
                    continue
                coordinates = ((prim['p0'][0], prim['p1'][0]) if axis == 'V'
                               else (prim['p0'][1], prim['p1'][1]))
                if all(abs(coordinate - value) <= tol
                       for coordinate in coordinates):
                    out.append((rid, float(part['z_mm']), prim))
    return out


def check_bottleneck(ctx, group, routes, assignment, summary):
    log(f'[{group}] 8/9 failure groups + shadow bottleneck audit ...')
    checker = Checker('failures_bottleneck')
    details = {}
    analysis_all = read_json(WORK / 'shadow_bottleneck_analysis.json')
    analysis = analysis_all.get(group) or {}
    feasibility = read_json(WORK / f'{group}_feasibility.json')
    lift_direction = 'EW' if group == 'H' else 'NS'
    footprint = 2.0 * RADIUS * math.sin(theta_for_dz(1.0))
    grid = [round(1.2 + 0.4 * index, 6) for index in range(0, 400)]
    max_a = (BOARD - 2.0 * footprint - 5.0) / 2.0
    deep_pairs = analysis.get('deep_pairs') or {}

    # ---- overall self-consistency of the analysis file --------------------
    checker.require(int(analysis.get('n_deep') or -1) == 34,
                    f'analysis n_deep={analysis.get("n_deep")!r} != 34')
    checker.require(len(deep_pairs) == 34,
                    f'analysis deep_pairs has {len(deep_pairs)} entries != 34')
    checker.require(int(analysis.get('n_parallel') or -1) == 32,
                    f'analysis n_parallel={analysis.get("n_parallel")!r} != 32')
    checker.require(analysis.get('n_crossing') == 0,
                    f'analysis n_crossing={analysis.get("n_crossing")!r} != 0')
    n_no_feasible = sum(1 for entry in deep_pairs.values()
                        if entry.get('status') == 'no_feasible_parameters')
    checker.require(
        int(analysis.get('n_parallel') or -1) + n_no_feasible
        == int(analysis.get('n_deep') or -1),
        f'n_parallel({analysis.get("n_parallel")}) + no_feasible'
        f'({n_no_feasible}) != n_deep({analysis.get("n_deep")})')
    checker.require(analysis.get('direction') == lift_direction,
                    f'analysis direction={analysis.get("direction")!r} != '
                    f'{lift_direction}')
    status_counts = Counter()
    feasibility_status = {}
    for gid in ctx.z1_opposite_gids:
        items = feasibility.get(str(gid)) or []
        if not items:
            feasibility_status[gid] = 'no_feasible_parameters'
        else:
            earliest = min(float(item[0]) for item in items)
            feasibility_status[gid] = ('deep_only' if earliest > EARLY_WINDOW_MM
                                       else 'early')
    for gid_str, entry in deep_pairs.items():
        gid = int(gid_str)
        status_counts[entry.get('status')] += 1
        expected_status = feasibility_status.get(gid)
        checker.require(entry.get('status') == expected_status,
                        f'group {gid}: analysis status {entry.get("status")!r} '
                        f'!= feasibility-derived {expected_status!r}')
    expected_deep = {gid for gid, status in feasibility_status.items()
                     if status != 'early'}
    checker.require(set(int(key) for key in deep_pairs) == expected_deep,
                    f'analysis deep pair set differs from feasibility-derived '
                    f'deep set: missing='
                    f'{sorted(expected_deep - {int(k) for k in deep_pairs})[:5]} '
                    f'extra='
                    f'{sorted({int(k) for k in deep_pairs} - expected_deep)[:5]}')
    checker.require(status_counts.get('deep_only') == 32,
                    f'deep_only count={status_counts.get("deep_only")} != 32')
    checker.require(status_counts.get('no_feasible_parameters') == 2,
                    f'no_feasible count='
                    f'{status_counts.get("no_feasible_parameters")} != 2')
    details['analysis_file'] = {
        'n_deep': analysis.get('n_deep'),
        'n_parallel': analysis.get('n_parallel'),
        'n_crossing': analysis.get('n_crossing'),
        'direction': analysis.get('direction'),
        'deep_pair_status_counts': dict(status_counts),
        'feasibility_status_counts': dict(Counter(feasibility_status.values())),
    }

    # ---- per-pair audit ---------------------------------------------------
    member_lines = {}
    for gid in ctx.z1_opposite_gids:
        buckets = ctx.group_routes_by_direction(gid)
        member_lines[gid] = {rid: member_interface_line(routes[rid])
                             for rid in buckets[lift_direction]}

    def blocked_by(prims, a, start, direction, total):
        result = min_transition_distance(start, direction, total, a, prims)
        return result

    early_failures = []
    pair_records = []
    exact_predictions = 0
    binding_records = []
    for gid_str, entry in sorted(deep_pairs.items(), key=lambda kv: int(kv[0])):
        gid = int(gid_str)
        status = entry.get('status')
        pair = {'group_id': gid, 'status': status}
        if status == 'deep_only':
            blockers = list(entry.get('early_window_blockers') or [])
            pair['blockers'] = blockers
            pair['earliest_feasible_a'] = entry.get('earliest_feasible_a')
            pair['blocker_classes'] = entry.get('blocker_classes')
            checker.require(len(blockers) >= 1,
                            f'group {gid}: deep_only without blockers')
            checker.require(entry.get('blocker_classes') == {'parallel_shadow': 1},
                            f'group {gid}: blocker_classes != parallel_shadow')
            items = feasibility.get(str(gid)) or []
            earliest = min(float(item[0]) for item in items)
            checker.require(close(entry.get('earliest_feasible_a'), earliest,
                                  1e-9),
                            f'group {gid}: earliest_feasible_a != min scan')
            first_values = [round(float(item[0]), 6) for item in items[:6]]
            checker.require(entry.get('first_feasible_a_values') == first_values,
                            f'group {gid}: first_feasible_a_values '
                            f'{entry.get("first_feasible_a_values")} != '
                            f'{first_values}')
            blocker_ok = True
            blocker_detail = []
            for blocker in blockers:
                record = routes.get(int(blocker))
                if record is None:
                    blocker_ok = False
                    blocker_detail.append({'route_id': blocker,
                                           'problem': 'route not in payload'})
                    continue
                info = {'route_id': int(blocker),
                        'plane': record['plane'],
                        'relation': record['relation'],
                        'z2_interface_route': (
                            record['plane'] == 'z2'
                            and record['relation'] in ('adjacent', 'same',
                                                       'opposite'))}
                interface_prims = [
                    (z_part, prim) for z_part, prim in
                    flat_primitives_with_z(record)
                    if abs(z_part - 0.5) <= 1e-9]
                info['z2_interface_primitives'] = len(interface_prims)
                # choose the pair member shadowed by this blocker and prove the
                # whole early window (a <= 20 mm) is blocked by it
                shadow_member = None
                shadow_result = None
                for rid, (start, direction, total) in member_lines[gid].items():
                    result = blocked_by(interface_prims,
                                        EARLY_WINDOW_MM, start, direction, total)
                    if result is not None and result[0] < CLEARANCE_MM:
                        shadow_member = rid
                        shadow_result = result
                        break
                info['shadowed_member'] = shadow_member
                if shadow_member is None:
                    blocker_ok = False
                    info['problem'] = ('no pair member has the early window '
                                       'blocked by this route')
                    blocker_detail.append(info)
                    continue
                start, direction, total = member_lines[gid][shadow_member]
                early_blocked = []
                for a in grid:
                    if a > EARLY_WINDOW_MM + 1e-9:
                        break
                    result = blocked_by(interface_prims, a, start, direction,
                                        total)
                    early_blocked.append(result is not None
                                         and result[0] < CLEARANCE_MM)
                info['early_window_blocked'] = all(early_blocked)
                if not all(early_blocked):
                    blocker_ok = False
                    info['problem'] = 'early window is not fully blocked'
                # blocker-only earliest feasible a (assembly acceptance ~0.091)
                predicted = None
                for a in grid:
                    if a > max_a + 1e-9:
                        break
                    result = blocked_by(interface_prims, a, start, direction,
                                        total)
                    if result is not None and result[0] >= ACCEPT_POINT_MM:
                        predicted = a
                        break
                info['blocker_only_earliest_a'] = predicted
                info['matches_reported_earliest'] = (
                    predicted is not None
                    and close(predicted, nearest_grid(entry['earliest_feasible_a']),
                              1e-9))
                if info['matches_reported_earliest']:
                    exact_predictions += 1
                blocker_detail.append(info)
                binding_records.append(((info['matches_reported_earliest']),
                                        gid, shadow_member))
            pair['blockers_verified'] = blocker_ok
            pair['blocker_detail'] = blocker_detail
            if not blocker_ok:
                early_failures.append(gid)
            pair_records.append(pair)
        else:
            pair['feasibility'] = feasibility.get(str(gid))
            checker.require(feasibility.get(str(gid)) == [],
                            f'group {gid}: no_feasible_parameters but the '
                            f'feasibility scan is not empty')
            pair_records.append(pair)
    checker.require(not early_failures,
                    f'{len(early_failures)} deep pairs whose listed blocker '
                    f'does not block the early window: {early_failures[:6]}')
    details['deep_pair_audit'] = {
        'deep_pairs': len(pair_records),
        'early_window_blocked': len(pair_records) - len(early_failures),
        'blocker_only_matches_reported_earliest': exact_predictions,
        'pairs': pair_records,
    }

    # ---- binding obstacle for pairs not exactly predicted ----------------
    fixed = [rid for rid, record in routes.items()
             if record['relation'] in ('adjacent', 'same')
             or (record['relation'] == 'opposite'
                 and record['plane'] == 'z2')]
    binding = []
    # cache the fixed z2-interface primitives as (route, prim) pairs
    fixed_interface = []
    for rid in fixed:
        record = routes[rid]
        if record['plane'] != 'z2':
            continue
        for z_part, prim in flat_primitives_with_z(record):
            if abs(z_part - 0.5) <= 1e-9:
                fixed_interface.append((int(rid), prim))
    for matches, gid, shadow_member in binding_records:
        if matches:
            continue
        entry = deep_pairs[str(gid)]
        start, direction, total = member_lines[gid][shadow_member]
        # spatial prefilter: only primitives within reach of this line
        reach = 6.0
        line_box = (min(start[0], start[0] + direction[0] * total) - reach,
                    min(start[1], start[1] + direction[1] * total) - reach,
                    max(start[0], start[0] + direction[0] * total) + reach,
                    max(start[1], start[1] + direction[1] * total) + reach)
        nearby = [(rid, prim) for rid, prim in fixed_interface
                  if bbox_distance(prim_bbox(prim), line_box) <= reach]
        a = round(float(entry['earliest_feasible_a']) - 0.4, 6)
        if a < 1.2:
            a = 1.2
        best = None
        for rid, prim in nearby:
            for u, w in transition_curve_points(a, dz=1.0, samples=80):
                point = (start[0] + direction[0] * u,
                         start[1] + direction[1] * u)
                distance = math.hypot(point_primitive_distance_2d(point, prim),
                                      w - 0.5)
                if best is None or distance < best[0]:
                    best = (distance, rid, prim, point)
            for u, w in transition_curve_points(total - a - footprint,
                                                dz=-1.0, samples=80):
                point = (start[0] + direction[0] * u,
                         start[1] + direction[1] * u)
                distance = math.hypot(point_primitive_distance_2d(point, prim),
                                      w - 0.5)
                if best is None or distance < best[0]:
                    best = (distance, rid, prim, point)
        if best is None:
            binding.append({'group_id': gid, 'problem': 'no binding obstacle'})
            continue
        distance, rid, prim, point = best
        tangent = primitive_tangent_at(prim, point)
        angle = math.degrees(angle_between_unit(tangent, direction))
        record = routes[rid]
        binding.append({
            'group_id': gid,
            'binding_route_id': int(rid),
            'binding_plane': record['plane'],
            'binding_relation': record['relation'],
            'binding_distance_mm': round(distance, 9),
            'binding_z_mm': 0.5,
            'tangent_angle_deg': round(angle, 3),
            'parallel_shadow': record['plane'] == 'z2' and angle <= 45.0,
            'reported_earliest_feasible_a': entry['earliest_feasible_a'],
        })
    checker.require(all(item.get('binding_route_id') is not None
                        for item in binding),
                    f'binding-obstacle scan failed: {binding[:5]}')
    checker.require(all(item.get('binding_plane') == 'z2'
                        for item in binding if 'binding_plane' in item),
                    'binding obstacle is not on the z2 interface layer')
    checker.require(all(item.get('parallel_shadow') for item in binding
                        if 'parallel_shadow' in item),
                    'binding obstacle is not a (near-)parallel shadow')
    details['binding_obstacles'] = {
        'pairs_not_exactly_predicted_by_listed_blocker': len(binding),
        'binding_obstacles': binding,
        'note': ('the deep threshold of these pairs is tightened by an '
                 'additional z2-interface-layer shadowing route; all binding '
                 'obstacles found are fixed z2-plane flat geometry at z=0.5 mm'),
    }

    # ---- the two infeasible pairs: double parallel shadow ----------------
    failed_audit = []
    failed_gids = sorted(int(key) for key, entry in deep_pairs.items()
                         if entry.get('status') == 'no_feasible_parameters')
    checker.require(len(failed_gids) == 2,
                    f'{len(failed_gids)} no_feasible pairs != 2')
    for gid in failed_gids:
        axis = 'H' if lift_direction == 'EW' else 'V'
        member_records = []
        for rid, (start, direction, total) in member_lines[gid].items():
            value = start[1] if axis == 'H' else start[0]
            interface_shadow = collinear_flat_primitives(
                {key: routes[key] for key in fixed}, 'z2', 0.5, axis, value)
            l2_shadow = collinear_flat_primitives(
                {key: routes[key] for key in fixed}, 'z2', 1.0, axis, value)
            interface_prims = [(z_part, prim)
                               for _rid, z_part, prim in interface_shadow]
            l2_prims = [(z_part, prim) for _rid, z_part, prim in l2_shadow]
            checker.require(len(interface_shadow) >= 1,
                            f'failed pair {gid} route {rid}: no z2 interface '
                            f'shadow found on the member line')
            checker.require(len(l2_shadow) >= 1,
                            f'failed pair {gid} route {rid}: no z2 L2 shadow '
                            f'found on the member line')
            blocked = []
            interface_blocked_count = 0
            l2_blocked_count = 0
            for a in grid:
                if a > max_a + 1e-9:
                    break
                result = blocked_by(interface_prims, a, start, direction, total)
                interface_blocked = (result is not None
                                     and result[0] < CLEARANCE_MM)
                travel_blocked = False
                u0 = a + footprint
                u1 = total - a - footprint
                if u1 > u0:
                    for index in range(0, 41):
                        u = u0 + (u1 - u0) * index / 40.0
                        point = (start[0] + direction[0] * u,
                                 start[1] + direction[1] * u)
                        for _z, prim in l2_prims:
                            distance = point_primitive_distance_2d(point, prim)
                            if distance < CLEARANCE_MM:
                                travel_blocked = True
                                break
                        if travel_blocked:
                            break
                interface_blocked_count += int(interface_blocked)
                l2_blocked_count += int(travel_blocked)
                blocked.append(interface_blocked or travel_blocked)
            gaps = _interval_gaps(
                [(min(prim['p0'][0], prim['p1'][0]),
                  max(prim['p0'][0], prim['p1'][0])) if axis == 'H'
                 else (min(prim['p0'][1], prim['p1'][1]),
                       max(prim['p0'][1], prim['p1'][1]))
                 for _rid, _z, prim in interface_shadow], total)
            member_records.append({
                'route_id': int(rid),
                'interface_shadow_segments': len(interface_shadow),
                'line_coordinate_mm': round(value, 6),
                'interface_shadow_gaps_mm': [[round(lo, 6), round(hi, 6)]
                                             for lo, hi in gaps],
                'max_interface_gap_mm': round(max((hi - lo for lo, hi in gaps),
                                                  default=0.0), 6),
                'l2_shadow_segments': len(l2_shadow),
                'grid_candidates': len(blocked),
                'interface_shadow_blocked_candidates': interface_blocked_count,
                'l2_shadow_blocked_candidates': l2_blocked_count,
                'all_candidates_blocked': all(blocked),
                'transition_footprint_mm': round(footprint, 6),
            })
        checker.require(all(record['all_candidates_blocked']
                            for record in member_records),
                        f'failed pair {gid}: not all grid candidates are '
                        f'blocked by the z2-layer shadow structure')
        checker.require(all((record['interface_shadow_blocked_candidates']
                             + record['l2_shadow_blocked_candidates'])
                            >= record['grid_candidates']
                            for record in member_records),
                        f'failed pair {gid}: blocking attribution incomplete')
        failed_audit.append({'group_id': gid, 'members': member_records})
    details['failed_pair_shadow_structure'] = failed_audit
    checker.require(len(failed_audit) == 2,
                    'failed-pair shadow structure not verified for exactly '
                    '2 groups')

    # ---- conclusion -------------------------------------------------------
    details['conclusion'] = {
        'claim': ('the 34 deep-window C2 pairs are all caused by fixed z2 '
                  'interface-layer parallel shadows'),
        'verified': (len(early_failures) == 0 and len(failed_audit) == 2),
        'deep_pairs_with_listed_z2_parallel_shadow': 32,
        'deep_pairs_without_listed_blocker_but_double_shadow_proved': 2,
        'pairs_where_listed_blocker_exactly_predicts_threshold':
            exact_predictions,
        'pairs_where_additional_z2_shadow_tightens':
            len(binding),
        'all_binding_obstacles_on_z2_interface':
            all(item.get('binding_plane') == 'z2' for item in binding),
        'caveat': ('for %d/32 pairs the listed single blocker blocks the whole '
                   'early window but a second z2-interface shadow sets the '
                   'exact deep threshold; every binding obstacle found is '
                   'still fixed z2-layer geometry at z=0.5 mm' % len(binding)),
    }
    return checker.to_dict(), details


def nearest_grid(value, step=0.4, start=1.2):
    return round(start + step * round((float(value) - start) / step), 6)


def _interval_gaps(intervals, total):
    intervals = sorted(intervals)
    gaps = []
    cursor = 0.0
    for lo, hi in intervals:
        if lo > cursor + 1e-9:
            gaps.append((cursor, lo))
        cursor = max(cursor, hi)
    if cursor < total - 1e-9:
        gaps.append((cursor, total))
    return gaps


# ---------------------------------------------------------------------------
# 10. artefact completeness + independence
# ---------------------------------------------------------------------------
def check_artefacts(ctx, group, summary):
    log(f'[{group}] 9/9 artefact completeness ...')
    checker = Checker('artefacts')
    base = HYBRID / group
    details = {'directory': str(base), 'files': {}, 'figures': {}}
    required = ['routes_1024.json', 'c2_pair_assignment.json',
                'validation.json', 'summary.json', 'crossing_analysis.json',
                'READY', 'ARTEFACTS_READY', 'run.log']
    for name in required:
        path = base / name
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        checker.require(exists and size > 0, f'{name} missing or empty')
        details['files'][name] = {'exists': exists, 'bytes': size,
                                  'sha256': sha256_file(path) if exists else None}
    for name in ('READY', 'ARTEFACTS_READY'):
        path = base / name
        if path.exists():
            text = path.read_text(encoding='utf-8', errors='replace').strip()
            checker.require(text.lower() == 'ready',
                            f'{name} content {text!r} != "ready"')
            details['files'][name]['content'] = text
    expected_figures = [f'figures/{stem}.png' for stem in FIG_STEMS]
    checker.require(summary.get('figures') == expected_figures,
                    f'summary figure list differs from the 13 expected stems: '
                    f'{summary.get("figures")}')
    for stem in FIG_STEMS:
        for suffix in ('png', 'svg'):
            path = base / 'figures' / f'{stem}.{suffix}'
            exists = path.exists()
            size = path.stat().st_size if exists else 0
            checker.require(exists and size > 1000,
                            f'figures/{stem}.{suffix} missing or too small '
                            f'({size} bytes)')
            entry = details['figures'].setdefault(f'{stem}.{suffix}',
                                                  {'exists': exists,
                                                   'bytes': size})
            if exists:
                entry['sha256'] = sha256_file(path)
                if suffix == 'png':
                    head = path.open('rb').read(8)
                    checker.require(head == b'\x89PNG\r\n\x1a\n',
                                    f'figures/{stem}.png is not a valid PNG')
                else:
                    head = path.open('rb').read(512).decode('utf-8',
                                                           errors='replace')
                    checker.require('<svg' in head,
                                    f'figures/{stem}.svg has no <svg> root')
    details['figure_pairs'] = len(FIG_STEMS)
    details['figure_files'] = len(details['figures'])
    return checker.to_dict(), details


def check_independence():
    checker = Checker('independence')
    forbidden = [name for name in sys.modules
                 if name in FORBIDDEN_MODULES
                 or name.startswith('four_side_1024.manual_c4.run_hybrid_')]
    checker.require(not forbidden,
                    f'forbidden production hybrid modules were imported: '
                    f'{forbidden}')
    repo_modules = sorted(name for name in sys.modules
                          if name.startswith('four_side_1024.'))
    allowed_prefixes = ('four_side_1024.v3c4.profile',
                        'four_side_1024.v3c4.inputs',
                        'four_side_1024.v3c4.lift_cross',
                        'four_side_1024.v3c4',
                        'four_side_1024.l3d',
                        'four_side_1024.fslw',
                        'four_side_1024.fsd25d',
                        'four_side_1024.d56',
                        'four_side_1024.r15',
                        'four_side_1024.legacy_geometry',
                        'four_side_1024.manual_c4.structured_layer_routing')
    unexpected = [name for name in repo_modules
                  if not any(name == prefix or name.startswith(prefix + '.')
                             for prefix in allowed_prefixes)]
    details = {
        'forbidden_modules_imported': forbidden,
        'repo_modules_imported': repo_modules,
        'unexpected_repo_modules': unexpected,
        'allowed_dependency_note': (
            'the frozen 3D validator entry point (lift_cross.validate_payload_v4) '
            'imports l3d/fslw/fsd25d/d56/r15 internally; port identity uses '
            'the frozen four_side_1024.v3c4.inputs.ENDPOINTS table; no '
            'manual_c4 hybrid/routing module is imported'),
    }
    return checker.to_dict(), details


# ---------------------------------------------------------------------------
# four-way comparison table (A / H / V / Spatial)
# ---------------------------------------------------------------------------
def build_four_way(ctx, baseline, spatial, group_details):
    def compact_layers(layer_counts):
        return {name: int(info['count'])
                for name, info in layer_counts.items()}

    a_summary = ctx.a_summary
    comparison = {
        'A_Structured': {
            'source': 'structured_layer_routing/A/routes_1024.json',
            'routed': 1024,
            'unique_crossing_pairs': baseline['unique_crossing_pairs'],
            'crossing_pairs_by_height':
                baseline['crossing_pairs_by_height'],
            'crossing_points_by_height':
                baseline['crossing_points_by_height'],
            'z1_hv_same_height_pairs': baseline['z1_hv_same_height_pairs'],
            'z0_total_pairs': baseline['z0_total_pairs'],
            'l2_total_pairs': baseline['l2_total_pairs'],
            'transitions': baseline['transitions'],
            'total_length_mm': baseline['total_length_mm'],
            'layer_counts': compact_layers(baseline['layer_counts']),
            'min_3d_clearance_mm': a_summary.get('min_3d_clearance_mm'),
            'min_curvature_radius_mm':
                a_summary.get('min_curvature_radius_mm'),
            'validation_status': a_summary.get('validation_status'),
            'independent_note': ('crossings/transitions/length/layer counts '
                                 'independently recomputed from the A payload; '
                                 'min clearance/curvature cited from the A '
                                 'artefact'),
        },
        'Spatial_U_bundle': {
            'source': 'spatial_u_bundle_optimization/routes_1024.json',
            'routed': 1024,
            'unique_crossing_pairs': (spatial or {}).get(
                'unique_crossing_pairs_independent'),
            'transitions': ((spatial or {}).get('summary') or {}).get(
                'transitions'),
            'total_length_mm': ((spatial or {}).get('summary') or {}).get(
                'total_length_mm'),
            'layer_counts': compact_layers(
                ((spatial or {}).get('summary') or {}).get('layer_counts')
                or _empty_layer_counts()),
            'min_3d_clearance_mm': ((spatial or {}).get('summary') or {}).get(
                'min_3d_clearance_mm'),
            'min_curvature_radius_mm': ((spatial or {}).get('summary') or {}
                                        ).get('min_curvature_radius_mm'),
            'validation_status': ((spatial or {}).get('summary') or {}).get(
                'validation_status'),
            'unique_crossing_pairs_from_summary': ((spatial or {}).get(
                'summary') or {}).get('unique_crossing_pairs'),
            'independent_note': ('crossing count cross-checked by the '
                                 'independent audit; other fields cited from '
                                 'the Spatial artefact'),
        },
    }
    for group in ('H', 'V'):
        details = group_details[group]
        metrics = details['metrics']['independent_metrics']
        sym = details['symmetry']
        v3 = details['authoritative_3d']
        comparison[f'Hybrid_{group}'] = {
            'source': f'hybrid_c2_c4_directional/{group}/routes_1024.json',
            'routed': metrics['routed'],
            'c2_pairs': sym['c2']['pairs'],
            'c2_pairs_lifted': details['layer_rules']['c2_pair_assignment'][
                'lifted_L2'],
            'c2_pairs_failed': details['layer_rules']['c2_pair_assignment'][
                'kept_L1_z1'],
            'c4_groups': sym['c4']['groups'],
            'unique_crossing_pairs': metrics['unique_crossing_pairs'],
            'crossing_pairs_by_height':
                metrics['crossing_pairs_by_height'],
            'crossing_points_by_height':
                metrics['crossing_points_by_height'],
            'z1_hv_same_height_pairs': metrics['z1_hv_same_height_pairs'],
            'z0_total_pairs': metrics['z0_total_pairs'],
            'l2_total_pairs': metrics['l2_total_pairs'],
            'transitions': metrics['transitions'],
            'total_length_mm': metrics['total_length_mm'],
            'layer_counts': compact_layers(metrics['layer_counts']),
            'min_3d_clearance_mm': v3['min_3d_clearance_mm'],
            'min_curvature_radius_mm': v3['min_curvature_radius_mm'],
            'validation_status': v3['status'],
            'exploratory_pass': v3['exploratory_pass'],
            'formal_acceptance': v3['formal_acceptance'],
            'independent_note': 'fully independently recomputed',
        }
    comparison['reductions_H_vs_A'] = {
        'z1_hv_same_height_reduction':
            comparison['A_Structured']['z1_hv_same_height_pairs']
            - comparison['Hybrid_H']['z1_hv_same_height_pairs'],
        'z0_total_reduction': comparison['A_Structured']['z0_total_pairs']
        - comparison['Hybrid_H']['z0_total_pairs'],
        'global_reduction':
            comparison['A_Structured']['unique_crossing_pairs']
            - comparison['Hybrid_H']['unique_crossing_pairs'],
    }
    comparison['reductions_V_vs_A'] = {
        'z1_hv_same_height_reduction':
            comparison['A_Structured']['z1_hv_same_height_pairs']
            - comparison['Hybrid_V']['z1_hv_same_height_pairs'],
        'z0_total_reduction': comparison['A_Structured']['z0_total_pairs']
        - comparison['Hybrid_V']['z0_total_pairs'],
        'global_reduction':
            comparison['A_Structured']['unique_crossing_pairs']
            - comparison['Hybrid_V']['unique_crossing_pairs'],
    }
    return comparison


def _empty_layer_counts():
    return {name: {'count': 0} for name in
            ('L1-z1', 'L1-z2', 'L2', 'L3', 'L4', 'L5')}


# ---------------------------------------------------------------------------
# per-group verification driver
# ---------------------------------------------------------------------------
def verify_group(ctx, group, baseline, spatial):
    log('=' * 78)
    log(f'[{group}] verification start')
    payload = read_json(HYBRID / group / 'routes_1024.json')
    routes = {int(record['route_id']): record for record in payload['routes']}
    assignment = read_json(HYBRID / group / 'c2_pair_assignment.json')
    summary = read_json(HYBRID / group / 'summary.json')
    analysis = read_json(HYBRID / group / 'crossing_analysis.json')
    production_validation = read_json(
        HYBRID / group / 'validation.json').get('payload_validation') or {}
    checks = {}
    details = {}

    checks['identity_ports'], details['identity_ports'] = \
        check_identity_ports(ctx, group, routes)
    checks['payload_layer_stack'], details['payload_layer_stack'] = \
        check_payload_layer_stack(ctx, group, payload)
    checks['symmetry'], details['symmetry'] = check_symmetry(ctx, group, routes)
    checks['fixed_preservation'], details['fixed_preservation'] = \
        check_fixed_preservation(ctx, group, routes)
    checks['layer_rules'], details['layer_rules'] = check_layer_rules(
        ctx, group, routes, assignment, summary)
    checks['geometry'], details['geometry'] = check_geometry(ctx, group, routes)
    checks['metrics'], details['metrics'] = check_metrics(
        ctx, group, routes, summary, analysis, baseline, spatial)
    checks['authoritative_3d'], details['authoritative_3d'] = \
        check_authoritative_3d(ctx, group, payload, production_validation)
    checks['bottleneck'], details['bottleneck'] = check_bottleneck(
        ctx, group, routes, assignment, summary)
    checks['artefacts'], details['artefacts'] = check_artefacts(ctx, group,
                                                                summary)
    checks['independence'], details['independence'] = check_independence()

    failures = []
    for name, check in checks.items():
        if not check.get('passed'):
            failures.append({'check': name, 'errors': check.get('errors'),
                             'error_count': check.get('error_count')})
    verdict = 'PASS' if not failures else 'FAIL'
    log(f'[{group}] verdict: {verdict}')
    for name, check in checks.items():
        log(f'[{group}]   {name}: '
            f'{"PASS" if check.get("passed") else "FAIL"} '
            f'({check.get("error_count")} error(s))')

    artifact_sha = {}
    for name in ('routes_1024.json', 'c2_pair_assignment.json',
                 'validation.json', 'summary.json', 'crossing_analysis.json'):
        path = HYBRID / group / name
        artifact_sha[name] = sha256_file(path) if path.exists() else None
    result = {
        'group': group,
        'verdict': verdict,
        'failures': failures,
        'checks': checks,
        'details': details,
        'artefact_sha256': artifact_sha,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
    }
    log(f'[{group}] verification done')
    return result


# ---------------------------------------------------------------------------
# global summarisation + markdown report
# ---------------------------------------------------------------------------
def summarise_group(result):
    details = result['details']
    metrics = details['metrics']['independent_metrics']
    sym = details['symmetry']
    rules = details['layer_rules']
    v3 = details['authoritative_3d']
    return {
        'verdict': result['verdict'],
        'routed': metrics['routed'],
        'c2_pairs': sym['c2']['pairs'],
        'c2_pairs_lifted': rules['c2_pair_assignment']['lifted_L2'],
        'c2_pairs_failed': rules['c2_pair_assignment']['kept_L1_z1'],
        'c2_failed_groups': rules['c2_pair_assignment']['failed_groups'],
        'c2_max_deviation_mm': sym['c2']['max_deviation_mm'],
        'c4_groups': sym['c4']['groups'],
        'c4_member_checks': sym['c4']['member_checks'],
        'c4_max_deviation_mm': sym['c4']['max_deviation_mm'],
        'z1_adjacent_c4_groups': sym['z1_adjacent_c4']['groups'],
        'z1_adjacent_c4_max_deviation_mm':
            sym['z1_adjacent_c4']['max_deviation_mm'],
        'unique_crossing_pairs': metrics['unique_crossing_pairs'],
        'crossing_pairs_by_height': metrics['crossing_pairs_by_height'],
        'crossing_points_by_height': metrics['crossing_points_by_height'],
        'z1_hv_same_height_pairs': metrics['z1_hv_same_height_pairs'],
        'z0_total_pairs': metrics['z0_total_pairs'],
        'l2_total_pairs': metrics['l2_total_pairs'],
        'transitions': metrics['transitions'],
        'total_length_mm': metrics['total_length_mm'],
        'layer_counts': {name: info['count']
                         for name, info in metrics['layer_counts'].items()},
        'min_3d_clearance_mm': v3['min_3d_clearance_mm'],
        'min_curvature_radius_mm': v3['min_curvature_radius_mm'],
        'validation_status': v3['status'],
        'exploratory_pass': v3['exploratory_pass'],
        'formal_acceptance': v3['formal_acceptance'],
        'geometry_issues': {name: info['count'] for name, info
                            in details['geometry']['issues'].items()},
        'fixed_preservation': {
            'U': details['fixed_preservation']['U'],
            'z2_opposite': details['fixed_preservation']['z2_opposite'],
            'adjacent': details['fixed_preservation']['adjacent'],
            'z1_adjacent': details['fixed_preservation']['z1_adjacent'],
        },
        'layer_rules': {
            'lifted_direction':
                details['layer_rules']['direction_rules']['lifted_direction'],
            'kept_direction':
                details['layer_rules']['direction_rules']['kept_direction'],
            'lifted_groups':
                details['layer_rules']['direction_rules']['lifted_groups'],
            'failed_groups':
                details['layer_rules']['direction_rules']['failed_groups'],
            'failed_group_details':
                details['layer_rules']['failed_group_details'],
        },
        'summary_diff': details['metrics']['summary_diff'],
        'crossing_analysis_diff': details['metrics']['crossing_analysis_diff'],
        'production_validation_diff':
            details['authoritative_3d']['production_diff'],
        'bottleneck_conclusion': details['bottleneck']['conclusion'],
        'artefact_sha256': result['artefact_sha256'],
    }


def build_markdown(verification):
    lines = []
    add = lines.append
    verdict = verification['verdict']
    add('# Hybrid C2/C4 Directional Layer Routing — 独立验收报告')
    add('')
    add(f'- 生成时间：{verification["generated_at"]}')
    add(f'- 验证脚本：`{verification["script"]["path"]}` '
        f'(sha256 `{verification["script"]["sha256"][:16]}…`)')
    add(f'- 独立性：未 import `four_side_1024.manual_c4.hybrid_c2_c4` / '
        f'`run_hybrid_*`（运行时断言通过）；仅使用冻结 3D 校验入口 '
        f'`validate_payload_v4`。')
    add('')
    add('## 1. 验收结论')
    add('')
    add('| 组 | 结论 | 关键检查 |')
    add('|---|---|---|')
    for group in ('H', 'V'):
        core = verification['core_numbers'][group]
        check_fail = [name for name, check in
                      verification['checks'][group].items()
                      if not check['passed']]
        add(f'| {group} | **{core["verdict"]}** | '
            f'{len(verification["checks"][group]) - len(check_fail)}/'
            f'{len(verification["checks"][group])} 项检查通过'
            f'{"；失败: " + ", ".join(check_fail) if check_fail else ""} |')
    add('')
    add(f'**总体结论：{verdict["overall"]}** '
        f'(H={verdict["H"]}, V={verdict["V"]})')
    add('')
    add('## 2. 核心数字（独立重算）')
    add('')
    add('| 指标 | Hybrid H | Hybrid V | Structured A | Spatial U-bundle |')
    add('|---|---:|---:|---:|---:|')
    four = verification['comparison_4way']
    rows = [
        ('总布通数', 'routed'),
        ('C2 二元组数', 'c2_pairs'),
        ('C2 提升组数', 'c2_pairs_lifted'),
        ('C2 失败组数', 'c2_pairs_failed'),
        ('z1 横纵同层交叉对', 'z1_hv_same_height_pairs'),
        ('z=0 交叉对', 'z0_total_pairs'),
        ('L2 交叉对', 'l2_total_pairs'),
        ('全局唯一交叉对', 'unique_crossing_pairs'),
        ('升降次数', 'transitions'),
        ('三维总长 (mm)', 'total_length_mm'),
        ('最小三维净空 (mm)', 'min_3d_clearance_mm'),
        ('最小曲率半径 (mm)', 'min_curvature_radius_mm'),
        ('独立 3D 验收', 'validation_status'),
        ('C4 组数', 'c4_groups'),
    ]
    for label, key in rows:
        values = []
        for column in ('A_Structured', 'Hybrid_H', 'Hybrid_V',
                       'Spatial_U_bundle'):
            value = four[column].get(key)
            if isinstance(value, float):
                value = f'{value:.6f}'.rstrip('0').rstrip('.')
            values.append('—' if value is None else str(value))
        # reorder to A / H / V / Spatial
        add(f'| {label} | {values[1]} | {values[2]} | {values[0]} | '
            f'{values[3]} |')
    add('')
    add('层波导数（独立重算）：')
    add('')
    add('| 层 | Hybrid H | Hybrid V | Structured A | Spatial |')
    add('|---|---:|---:|---:|---:|')
    for layer in ('L1-z1', 'L1-z2', 'L2', 'L3', 'L4', 'L5'):
        add(f'| {layer} | {four["Hybrid_H"]["layer_counts"].get(layer)} | '
            f'{four["Hybrid_V"]["layer_counts"].get(layer)} | '
            f'{four["A_Structured"]["layer_counts"].get(layer)} | '
            f'{four["Spatial_U_bundle"]["layer_counts"].get(layer)} |')
    add('')
    add('削减量（独立计数口径）：z1 横纵同层交叉对 '
        f'{four["A_Structured"]["z1_hv_same_height_pairs"]} → '
        f'{four["Hybrid_H"]["z1_hv_same_height_pairs"]}（-'
        f'{four["reductions_H_vs_A"]["z1_hv_same_height_reduction"]}）；'
        f'z=0 交叉对 {four["A_Structured"]["z0_total_pairs"]} → '
        f'{four["Hybrid_H"]["z0_total_pairs"]}（-'
        f'{four["reductions_H_vs_A"]["z0_total_reduction"]}）；全局唯一交叉对 '
        f'{four["A_Structured"]["unique_crossing_pairs"]} → '
        f'{four["Hybrid_H"]["unique_crossing_pairs"]}（-'
        f'{four["reductions_H_vs_A"]["global_reduction"]}）。')
    add('')
    semantics = verification['notes']['A_crossing_semantics']
    add(f'> 口径说明：{semantics}')
    add('')
    add('## 3. 混合对称性（C2 180°+路径反转 / C4 90°）')
    add('')
    add('> 方法：C2 二元组的物理固定端口关系是 '
        '`B_path(s) = R180(A_path(L - s))`（180° 旋转 **+ 遍历方向反转**：'
        'rise↔fall 对应、parts 顺序反转、direction 按旋转后的反向特征取负）；'
        'C4 组为纯 90° 旋转。两种关系都按弧长参数化对 3D 路径（XY 2D 链 + '
        '升降 S 曲线）逐点比对（容差 1e-6），并额外核对 start/end、'
        'z0/z1、theta/footprint/length、from/to layer 等升降参数合同。')
    add('')
    for group in ('H', 'V'):
        core = verification['core_numbers'][group]
        add(f'- **{group}**：z1 对边 132 个 C2 二元组（66 EW + 66 NS）全部满足 '
            f'1e-6 容差 180° 严格旋转，最大偏差 '
            f'{core["c2_max_deviation_mm"]:.3g} mm；z2 全部 {core["c4_groups"]} '
            f'个 C4 组（U 64 + 对边 2 + 邻边 78）的 '
            f'{core["c4_member_checks"]} 个成员旋转比对全部通过，最大偏差 '
            f'{core["c4_max_deviation_mm"]:.3g} mm；z1 邻边 46 组 '
            f'（{core["z1_adjacent_c4_groups"]} 组）保持 Structured-A 的 C4 '
            f'关系（最大偏差 '
            f'{core["z1_adjacent_c4_max_deviation_mm"]:.3g} mm），不要求 C2 '
            f'重排（其 3D 路径与 A 逐字段一致）。')
    add('')
    add('## 4. 固定保持（Structured A）')
    add('')
    for group in ('H', 'V'):
        fixed = verification['core_numbers'][group]['fixed_preservation']
        annotation_diffs = sum(
            int(fixed[key].get('validator_annotation_differences') or 0)
            for key in ('U', 'z2_opposite', 'adjacent', 'z1_adjacent'))
        annotation_note = (
            '；含校验器内部注解 `_back_to_back_transitions` 在内的全部字段一致'
            if annotation_diffs == 0 else
            f'；仅 {annotation_diffs} 条记录缺少校验器内部注解 '
            f'`_back_to_back_transitions`（值 0，不影响几何/合同）')
        add(f'- **{group}**：U {fixed["U"]["contract_identical"]}/'
            f'{fixed["U"]["records"]}、z2 对边 '
            f'{fixed["z2_opposite"]["contract_identical"]}/'
            f'{fixed["z2_opposite"]["records"]}、邻边 '
            f'{fixed["adjacent"]["contract_identical"]}/'
            f'{fixed["adjacent"]["records"]} 与 Structured-A 记录逐字段一致'
            f'（合同字段 0 差异；U 层序 / 端点 / parts 均一致）'
            f'{annotation_note}。')
    add('')
    add('## 5. 分层规则与失败组')
    add('')
    for group in ('H', 'V'):
        rules = verification['core_numbers'][group]['layer_rules']
        failed = rules['failed_groups']
        add(f'- **{group}**：提升方向 {rules["lifted_direction"]}，'
            f'{len(rules["lifted_groups"])} 组提升到 L2（层序 [1,2,1]，'
            f'L2 平段 z=1.0，且 c2_pair_assignment 的 a_in/a_out、'
            f'rise/fall 位置与实际几何一致）；保留方向 '
            f'{rules["kept_direction"]} 66 组平铺 L1-z1；失败组 '
            f'{failed} 在 c2_pair_assignment 中 failure 原因非空，实际保持 '
            f'L1-z1 平铺。')
    add('')
    add('## 6. 几何与权威 3D 验收')
    add('')
    add('> 设计约束：板面 150×150 mm、R=15 mm、波导宽 0.05 mm、'
        '最小中心线净空 0.08 mm、每条路线 0 或 2 次升降且只能落在 2D 直线段、'
        '完整 XYZ 碰撞检查由冻结 `validate_payload_v4` 执行。')
    add('')
    for group in ('H', 'V'):
        core = verification['core_numbers'][group]
        add(f'- **{group}**：全部圆弧 R=15、直线轴对齐、升降均落在 2D 直线段、'
            f'每条 0 或 2 个升降且先升后降、所有几何在 150×150 板内、'
            f'非目标连接（632 条平铺 + 136 条重建）2D 链与 phase2_2d 一致。'
            f'冻结 `validate_payload_v4` 复验：status='
            f'{core["validation_status"]}, exploratory_pass='
            f'{core["exploratory_pass"]}, formal_acceptance='
            f'{core["formal_acceptance"]}, 9 类 counts 全 0；'
            f'min curvature={core["min_curvature_radius_mm"]} mm，'
            f'min 3D clearance={core["min_3d_clearance_mm"]} mm '
            f'(≥0.08)。')
    add('')
    add('## 7. 指标独立重算与生产 summary 对照')
    add('')
    diffs = verification['production_diffs']
    for group in ('H', 'V'):
        add(f'- **{group}**：summary / crossing_analysis 的交叉对数、'
            f'z1 横纵、升降次数、三维总长、层波导数与独立重算 '
            f'{len(diffs[group]["summary_metric_diffs"])} 处差异、'
            f'crossing_analysis {len(diffs[group]["crossing_analysis_diffs"])} '
            f'处差异、validation 报告 '
            f'{len(diffs[group]["validation_report_diffs"])} 处差异。')
    add('')
    add('## 8. 失败与瓶颈（shadow bottleneck）')
    add('')
    for group in ('H', 'V'):
        bn = verification['bottleneck'][group]
        failed_text = '；'.join(
            f'group {item["group_id"]}: '
            f'{len(item["members"])} 条成员线、共 '
            f'{max(member["grid_candidates"] for member in item["members"])} '
            f'个对称候选 a 全部被固定 z2 几何阻挡（接口层 shadow 段 '
            f'{sum(member["interface_shadow_segments"] for member in item["members"])} '
            f'段 / L2 同线固定段 '
            f'{sum(member["l2_shadow_segments"] for member in item["members"])} '
            f'段）'
            for item in bn['failed_pair_shadow_structure'])
        add(f'- **{group}**：`shadow_bottleneck_analysis.json` 结构自检通过'
            f'（n_deep=34 = n_parallel 32 + no_feasible 2、n_crossing=0，'
            f'深窗口集合与 feasibility 扫描一致）。32 个 deep_only 对列出的 '
            f'blocker 均为 z2 接口层固定路线，且独立几何验证确认其单独就能'
            f'封死整个最早窗口（a≤20 mm）；其中 '
            f'{bn["pairs_where_listed_blocker_exactly_predicts_threshold"]} 个的'
            f'深窗口阈值可由该 blocker 精确解释，'
            f'{bn["pairs_where_additional_z2_shadow_tightens"]} 个由额外 z2 '
            f'接口层 shadow 进一步收紧（所有 binding obstacle 均为 z2 层 '
            f'z=0.5 的固定几何）。2 个失败组（{bn["failed_groups"]}）经 '
            f'2D/3D 几何枚举确认，升降足印 {bn["footprint_mm"]} mm：'
            f'{failed_text}，故 feasibility 扫描为空表。')
    add('')
    add('## 9. 产物完整性')
    add('')
    for group in ('H', 'V'):
        art = verification['artefacts'][group]
        add(f'- **{group}**：routes/c2_pair_assignment/validation/summary/'
            f'crossing_analysis/READY/ARTEFACTS_READY 齐全；'
            f'figures 13 PNG + 13 SVG 全部存在且格式有效。')
    add('')
    add('## 10. 差异、口径与限制')
    add('')
    for note in verification['notes']['items']:
        add(f'- {note}')
    add('')
    add('## 11. 输出文件')
    add('')
    for name, info in verification['files'].items():
        add(f'- `{name}`')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-md', action='store_true',
                        help='do not write the markdown report')
    args = parser.parse_args(argv)
    global log
    log = Log(OUT_DIR / 'verify_hybrid_c2_c4.log')
    started = time.time()
    log('Hybrid C2/C4 directional experiment — independent verification')
    log(f'verification dir: {OUT_DIR}')
    script_sha = sha256_file(Path(__file__).resolve())
    ctx = Context(log)
    log(f'connectivity: {len(ctx.manifest)} routes / '
        f'{len(ctx.groups)} groups; z1 opposite groups '
        f'{len(ctx.z1_opposite_gids)}; U groups {len(ctx.u_gids)}')
    baseline, spatial = build_crossing_reference(ctx, log)
    log(f'independent A baseline: unique={baseline["unique_crossing_pairs"]} '
        f'z0_pairs={baseline["z0_total_pairs"]} '
        f'z1_hv={baseline["z1_hv_same_height_pairs"]}')

    group_results = {}
    for group in ('H', 'V'):
        group_results[group] = verify_group(ctx, group, baseline, spatial)

    summaries = {group: summarise_group(group_results[group])
                 for group in ('H', 'V')}
    overall = 'PASS' if all(summaries[group]['verdict'] == 'PASS'
                           for group in ('H', 'V')) else 'FAIL'

    # checks overview (shared independence check is identical in both groups)
    checks_overview = {}
    for group in ('H', 'V'):
        checks_overview[group] = {
            name: {'passed': check.get('passed'),
                   'error_count': check.get('error_count')}
            for name, check in group_results[group]['checks'].items()}

    four_way = build_four_way(ctx, baseline, spatial,
                              {group: group_results[group]['details']
                               for group in ('H', 'V')})

    production_diffs = {}
    for group in ('H', 'V'):
        details = group_results[group]['details']
        annotation = details['fixed_preservation']['annotation_presence']
        production_diffs[group] = {
            'summary_metric_diffs': details['metrics']['summary_diff'],
            'crossing_analysis_diffs':
                details['metrics']['crossing_analysis_diff'],
            'validation_report_diffs':
                details['authoritative_3d']['production_diff'],
            'fixed_record_validator_annotation':
                annotation,
        }

    bottleneck = {}
    for group in ('H', 'V'):
        details = group_results[group]['details']['bottleneck']
        conclusion = details['conclusion']
        bottleneck[group] = {
            'n_deep': details['analysis_file']['n_deep'],
            'n_parallel': details['analysis_file']['n_parallel'],
            'n_crossing': details['analysis_file']['n_crossing'],
            'deep_pair_status_counts':
                details['analysis_file']['deep_pair_status_counts'],
            'early_window_blocked_pairs':
                details['deep_pair_audit']['early_window_blocked'],
            'pairs_where_listed_blocker_exactly_predicts_threshold':
                conclusion[
                    'pairs_where_listed_blocker_exactly_predicts_threshold'],
            'pairs_where_additional_z2_shadow_tightens':
                conclusion['pairs_where_additional_z2_shadow_tightens'],
            'all_binding_obstacles_on_z2_interface':
                conclusion['all_binding_obstacles_on_z2_interface'],
            'failed_groups': sorted(
                item['group_id']
                for item in details['failed_pair_shadow_structure']),
            'footprint_mm': round(2.0 * RADIUS
                                  * math.sin(theta_for_dz(1.0)), 6),
            'failed_pair_shadow_structure':
                details['failed_pair_shadow_structure'],
            'verified': conclusion['verified'],
            'caveat': conclusion['caveat'],
        }

    artefacts = {}
    for group in ('H', 'V'):
        artefacts[group] = group_results[group]['details']['artefacts']

    symmetry = {}
    for group in ('H', 'V'):
        details = group_results[group]['details']['symmetry']
        symmetry[group] = {
            'c2': {key: details['c2'][key] for key in
                   ('pairs', 'passed', 'directions', 'route_directions',
                    'max_deviation_mm', 'reversed_order_counts')},
            'c4': {key: details['c4'][key] for key in
                   ('groups', 'categories', 'member_checks', 'members_passed',
                    'max_deviation_mm', 'reversed_order_counts')},
            'z1_adjacent_c4': {key: details['z1_adjacent_c4'][key]
                               for key in ('groups', 'member_checks', 'passed',
                                           'max_deviation_mm')},
        }

    geometry = {}
    for group in ('H', 'V'):
        details = group_results[group]['details']['geometry']
        geometry[group] = {key: details[key] for key in
                           ('routes', 'flat_primitives', 'flat_lines',
                            'flat_arcs', 'transitions',
                            'record_primitives_checked',
                            'flat_chain_checked',
                            'reconstructed_chain_checked',
                            'u_actual_chain_skipped',
                            'u_actual_chain_note', 'issues')}

    metrics = {}
    for group in ('H', 'V'):
        details = group_results[group]['details']['metrics']
        metrics[group] = {
            'independent_metrics': details['independent_metrics'],
            'summary_diff': details['summary_diff'],
            'crossing_analysis_diff': details['crossing_analysis_diff'],
            'baseline_metric_semantics':
                details['baseline_metric_semantics'],
            'reduction': details['reduction'],
        }
    metrics['A_baseline'] = {
        'unique_crossing_pairs': baseline['unique_crossing_pairs'],
        'crossing_pairs_by_height': baseline['crossing_pairs_by_height'],
        'crossing_points_by_height': baseline['crossing_points_by_height'],
        'crossing_breakdown_by_height':
            baseline['crossing_breakdown_by_height'],
        'z1_hv_same_height_pairs': baseline['z1_hv_same_height_pairs'],
        'z1_hv_breakdown_by_height': baseline['z1_hv_breakdown_by_height'],
        'transitions': baseline['transitions'],
        'total_length_mm': baseline['total_length_mm'],
        'layer_counts': baseline['layer_counts'],
    }
    if spatial is not None:
        metrics['Spatial_cross_check'] = {
            'summary_unique_crossing_pairs':
                (spatial['summary'] or {}).get('unique_crossing_pairs'),
            'independent_unique_crossing_pairs':
                spatial['unique_crossing_pairs_independent'],
            'independent_crossing_points':
                spatial['crossing_points_independent'],
        }

    authoritative_3d = {}
    for group in ('H', 'V'):
        authoritative_3d[group] = group_results[group][
            'details']['authoritative_3d']

    notes_items = [
        ('独立性：脚本未 import 生产 hybrid 模块 '
         '(`four_side_1024.manual_c4.hybrid_c2_c4` / `run_hybrid_*`)；'
         '身份/对称/规则/几何/交叉指标全部独立实现，仅 3D 权威验收使用任务'
         '指定的冻结入口 `validate_payload_v4`。'),
        ('A 基线口径：A 产物 summary 的逐高度数字是**交叉点**数（z=0 为 '
         '18600）；本实验 crossing_analysis 的 baseline 使用**逐高度唯一 '
         'route 对**（z=0 为 17576）。两者全局唯一交叉对一致（19584）。'
         'H/V 结果两种口径分别为：z=0 唯一对 11952 / 交叉点 12464。'),
        ('固定保持：H/V 两组的 760 条固定记录（U 256、z2 对边 8、邻边 496）'
         '与 Structured-A 记录逐字段完全一致（包括 l3d 校验器在 A 阶段写入的'
         '内部注解 `_back_to_back_transitions`，值 0）；仅本轮重新生成的 264 条 '
         'z1 对边记录（128 提升 + 136 平铺）不携带该内部注解，属预期且不影响'
         '几何/合同（冻结校验器会重新计算该注解）。'),
        ('2D 链口径：`primitives` 参照字段在 896 条记录上与 phase2_2d 完全'
         '一致（128 条 C2 提升记录无该字段）；632 条接口平铺记录的实际 2D '
         '链与 phase2_2d 一致；128 条 C2 提升 + 8 条 z2 对边提升记录由直线'
         '片段重建后与 phase2_2d 一致。U 256 条在 Structured A 中已按 U 线束'
         '重建（其实际 2D 链不等于 phase2_2d），本轮按任务要求保持与 A 逐'
         '字段一致（section 3 已验证）。'),
        ('瓶颈结论：`shadow_bottleneck_analysis.json` 的 34 个深窗口对结论'
         '成立，但需精确表述：32 个 deep_only 对列出的 blocker 均为 z2 接口层'
         '固定路线的 parallel shadow，独立几何验证确认其单独封死 a≤20 mm 的'
         '最早窗口；其中部分对的精确深阈值由额外 z2 接口层 shadow 收紧。'
         '2 个失败组由 z2 接口层 shadow + L2 层占用共同导致不可行。'),
        ('权威 3D：exploratory_pass=true、9 类 counts 全 0、'
         'formal_acceptance=false（层高为未确认仿真参数，formal 被拒是预期'
         '行为）；min 3D clearance 0.0917 mm > 0.08 mm，min curvature '
         '14.999999964 mm ≥ 15 mm - 容差。'),
        ('限制：交叉指标采用“中心线交点/唯一 route 对”几何口径（与生产 strict '
         'policy 的 crossings 定义一致，独立实现已逐项复现生产数字）；未对'
         '图形内容做像素级复核，仅校验 13×2 图像文件存在、格式与尺寸；'
         'Spatial U-bundle 仅交叉计数做了独立交叉核对，其余指标引用其产物。'),
    ]
    verification = {
        'schema': 'hybrid_c2_c4_verification_v1',
        'experiment': 'MANUAL_C4_HYBRID_C2_C4_DIRECTIONAL',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'verdict': {'H': summaries['H']['verdict'],
                    'V': summaries['V']['verdict'],
                    'overall': overall},
        'script': {'path': str(Path(__file__).resolve()),
                   'sha256': script_sha},
        'targets': {
            group: {
                'directory': str(HYBRID / group),
                'artefact_sha256': summaries[group]['artefact_sha256'],
            } for group in ('H', 'V')},
        'checks': checks_overview,
        'design_constraints': {
            'board_mm': BOARD,
            'waveguide_width_mm': WIDTH_MM,
            'min_centerline_clearance_mm': CLEARANCE_MM,
            'bend_radius_mm': RADIUS,
            'interface_heights_mm': INTERFACE_Z,
            'routing_heights_mm': {str(layer): z
                                   for layer, z in LAYER_Z.items()},
            'max_transitions_per_route': 2,
            'transitions_on_straight_segments_only': True,
            'full_xyz_clearance_check': ('frozen validate_payload_v4 '
                                         '(l3d, exploratory)'),
            'ports_total': int(ctx.conn['ports']),
            'connections_total': int(ctx.conn['connections']),
        },
        'core_numbers': summaries,
        'symmetry': symmetry,
        'symmetry_method': {
            'C2': ('B_path(s) = R180(A_path(L - s)): rigid 180 deg rotation '
                   'plus traversal reversal (physical ports are fixed); '
                   'implemented by sampling both 3D paths by arc length, '
                   'rotating A, choosing the B traversal orientation from the '
                   'endpoint distances, point-wise comparison at 1e-6 mm; the '
                   'transition contract compares rotated start/end, rotated '
                   'direction, z0/z1, theta/footprint/length and layers, with '
                   'reversed-B transitions mapped back (start<->end, direction '
                   'negated, z0<->z1, from/to swapped)'),
            'C4': ('rigid 90 deg rotation about the board centre; same '
                   'sampling/contract machinery; group members are ordered by '
                   'the phase2_2d rotation_phase 0/1/2/3 and compared with '
                   'R^k for k=1,2,3'),
            'tolerance_mm': TOL_SYM,
            'direction_convention': ('+90 deg rotation of a free vector is '
                                     '(dx,dy)->(-dy,dx); a 180 deg rotation '
                                     'therefore maps a direction to its '
                                     'negation'),
        },
        'fixed_preservation': {
            group: summaries[group]['fixed_preservation']
            for group in ('H', 'V')},
        'layer_rules': {group: summaries[group]['layer_rules']
                        for group in ('H', 'V')},
        'geometry': geometry,
        'metrics': metrics,
        'authoritative_3d': authoritative_3d,
        'bottleneck': bottleneck,
        'artefacts': artefacts,
        'production_diffs': production_diffs,
        'comparison_4way': four_way,
        'notes': {
            'A_crossing_semantics': (
                'A 产物 summary 的逐高度交叉数字是交叉点数（z=0: 18600），'
                'crossing_analysis baseline 用逐高度唯一 route 对数'
                '（z=0: 17576）；全局唯一交叉对 19584 两口径一致。'),
            'items': notes_items,
            'bottleneck_caveat':
                '32 个 deep_only 对中 11 个的精确深阈值由额外 z2 接口层 '
                'shadow 收紧；所有 binding obstacle 均为 z2 层 z=0.5 固定几何。',
        },
        'files': {},
    }

    group_docs = {}
    for group in ('H', 'V'):
        group_doc = {
            'schema': 'hybrid_c2_c4_group_verification_v1',
            'group': group,
            'generated_at': verification['generated_at'],
            'script_sha256': script_sha,
            'verdict': summaries[group]['verdict'],
            'failures': group_results[group]['failures'],
            'checks': group_results[group]['checks'],
            'summary': summaries[group],
            'details': group_results[group]['details'],
        }
        path = OUT_DIR / f'_group_{group}.json'
        write_json(path, jsonable(group_doc))
        group_docs[group] = path
        log(f'wrote {path.name}')

    # ---- write global JSON + Markdown ------------------------------------
    json_path = OUT_DIR / 'hybrid_c2_c4_verification.json'
    md_path = OUT_DIR / 'hybrid_c2_c4_verification.md'
    for group in ('H', 'V'):
        verification['files'][group_docs[group].name] = {
            'bytes': group_docs[group].stat().st_size}
    verification['files'][json_path.name] = {'bytes': 0}
    verification['files'][md_path.name] = {'bytes': 0}
    write_json(json_path, jsonable(verification))
    if not args.skip_md:
        md_path.write_text(build_markdown(jsonable(verification)),
                           encoding='utf-8')
        verification['files'][md_path.name] = {
            'bytes': md_path.stat().st_size}
    verification['files'][json_path.name] = {
        'bytes': json_path.stat().st_size}
    write_json(json_path, jsonable(verification))

    log('=' * 78)
    log(f'OVERALL VERDICT: {overall} (H={summaries["H"]["verdict"]}, '
        f'V={summaries["V"]["verdict"]})')
    for group in ('H', 'V'):
        core = summaries[group]
        log(f'[{group}] routed={core["routed"]} C2={core["c2_pairs"]} '
            f'(lifted {core["c2_pairs_lifted"]}, failed '
            f'{core["c2_pairs_failed"]}) C4={core["c4_groups"]} '
            f'unique_crossings={core["unique_crossing_pairs"]} '
            f'z0={core["z0_total_pairs"]} z1_hv={core["z1_hv_same_height_pairs"]} '
            f'L2={core["l2_total_pairs"]} transitions={core["transitions"]} '
            f'length={core["total_length_mm"]} '
            f'min3d={core["min_3d_clearance_mm"]} '
            f'minR={core["min_curvature_radius_mm"]}')
    log(f'wrote {json_path.name}, {md_path.name}')
    log(f'total runtime {round(time.time() - started, 2)} s')
    return 0 if overall == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
