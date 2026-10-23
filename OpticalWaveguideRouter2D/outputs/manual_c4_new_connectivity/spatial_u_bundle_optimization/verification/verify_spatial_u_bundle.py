#!/usr/bin/env python
"""Independent verification of the spatial-grouped U-bundle 3D routing experiment.

This script is intentionally self-contained: it does NOT import the production
modules ``four_side_1024.manual_c4.spatial_u_bundle`` / ``..._run`` / plotting.
It re-implements the geometric / combinatorial checks from the JSON artefacts
and uses only the frozen acceptance code for the authoritative 3D pass
(``four_side_1024.v3c4.lift_cross.validate_payload_v4`` -> ``l3d.validate_l3d``)
and the frozen 2D pair audit (``fslw.validate_fslw``).

Outputs (only inside ``verification/``):
    spatial_u_bundle_verification.json
    spatial_u_bundle_verification.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# frozen R15 profile must be applied before importing radius-bound modules
# ---------------------------------------------------------------------------
_THIS = Path(__file__).resolve()
REPO = _THIS
while REPO.parent != REPO and not (REPO / 'four_side_1024').is_dir():
    REPO = REPO.parent
sys.path.insert(0, str(REPO))

from four_side_1024.v3c4.profile import apply as apply_profile  # noqa: E402

apply_profile()

from four_side_1024.fslw import config as C  # noqa: E402
from four_side_1024.fslw import validate_fslw as V  # noqa: E402

CAMPAIGN = REPO / 'outputs' / 'manual_c4_new_connectivity'
AFTER = CAMPAIGN / 'phase5_dynamic_optimization' / 'after'
PHASE2 = CAMPAIGN / 'phase2_2d'
PROD = CAMPAIGN / 'spatial_u_bundle_optimization'
DEFAULT_OUT = PROD / 'verification'

R = float(C.RADIUS_MM)
CLEAR = float(C.CLEARANCE_MM)
BOARD = float(C.BOARD_MM)
WIDTH = float(C.WIDTH_MM)
SAGITTA = float(C.SAGITTA_MM)
ROW_Z = {'z1': 0.0, 'z2': 0.5}
ROW_OF = {'z1': 1, 'z2': 2}
STACK = {2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5}
ENERGY_TARGET = {**{g: 2 for g in range(20, 36)},
                 **{g: 2 for g in range(144, 160)},
                 **{g: 3 for g in range(160, 176)},
                 **{g: 4 for g in range(176, 192)}}
MOVED_GID = 11
MOVED_RIDS = (12, 231, 232, 29)
CATEGORIES = ('violations', 'contract_errors', 'port_errors', 'geometry_errors',
              'curvature_violations', 'clearance_violations',
              'same_plane_violations', 'self_clearance_violations',
              'other_errors')
INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0), 'E': (-1.0, 0.0), 'W': (1.0, 0.0)}
FIGURE_STEMS = ['01_before_3d', '02_after_3d', '03_L1_z1', '04_L1_z2',
                '05_L2', '06_L3', '07_L4', '08_L5',
                '09_bundle_z1_middle_U', '10_bundle_z2_corner_U_1',
                '11_bundle_z2_corner_U_2', '12_bundle_z2_middle_U']
POS_TOL = 1e-6       # XY continuity / rotation comparison
Z_TOL = 1e-9
FORM_TOL = 1e-6      # theta / footprint / length formulas
LEN_TOL = 1e-4       # aggregate route lengths


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding='utf-8')
    return path


def xy(value):
    return (float(value[0]), float(value[1]))


def close(a, b, tol=POS_TOL):
    return abs(float(a) - float(b)) <= tol


def close_xy(a, b, tol=POS_TOL):
    return abs(float(a[0]) - float(b[0])) <= tol and \
        abs(float(a[1]) - float(b[1])) <= tol


def dist_xy(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def unit(vector):
    norm = math.hypot(float(vector[0]), float(vector[1]))
    return (float(vector[0]) / norm, float(vector[1]) / norm)


def angle_diff(a, b):
    delta = (float(a) - float(b)) % (2.0 * math.pi)
    return min(delta, 2.0 * math.pi - delta)


def prim_length(prim):
    if prim['kind'] == 'line':
        return dist_xy(prim['p0'], prim['p1'])
    return abs(float(prim['sweep'])) * float(prim['radius'])


def point_on_segment(point, a, b, tol=POS_TOL):
    dx, dy = float(b[0]) - float(a[0]), float(b[1]) - float(a[1])
    length2 = dx * dx + dy * dy
    if length2 <= 1e-18:
        return dist_xy(point, a) <= tol
    t = ((float(point[0]) - float(a[0])) * dx
         + (float(point[1]) - float(a[1])) * dy) / length2
    if t < -1e-9 or t > 1.0 + 1e-9:
        return False
    foot = (float(a[0]) + t * dx, float(a[1]) + t * dy)
    return dist_xy(point, foot) <= tol


def arc_points(prim, count=48):
    center = prim['center']
    radius = float(prim['radius'])
    start = float(prim['start_angle'])
    sweep = float(prim['sweep'])
    points = []
    for index in range(count + 1):
        angle = start + sweep * index / count
        points.append((float(center[0]) + radius * math.cos(angle),
                       float(center[1]) + radius * math.sin(angle)))
    return points


def transition_points(part, count=48):
    """Own 3D sampling of the two-arc S curve (no frozen-sampler import)."""
    radius = float(part['radius_mm'])
    theta = float(part['theta_rad'])
    z0, z1 = float(part['z0']), float(part['z1'])
    sign = 1.0 if z1 >= z0 else -1.0
    start = part['start']
    dx, dy = unit(part['direction'])
    h = radius * math.sin(theta)
    points = []
    for index in range(count + 1):
        phi = theta * index / count
        u = radius * math.sin(phi)
        points.append((float(start[0]) + dx * u, float(start[1]) + dy * u,
                       z0 + sign * radius * (1.0 - math.cos(phi))))
    for index in range(count - 1, -1, -1):
        phi = theta * index / count
        u = 2.0 * h - radius * math.sin(phi)
        points.append((float(start[0]) + dx * u, float(start[1]) + dy * u,
                       z1 - sign * radius * (1.0 - math.cos(phi))))
    return points


def inside_board(x, y, tol=1e-6):
    return (-tol <= x <= BOARD + tol) and (-tol <= y <= BOARD + tol)


def depth_of(side, point):
    """Depth from the board side along the inward direction (mm)."""
    x, y = float(point[0]), float(point[1])
    if side == 'N':
        return BOARD - y
    if side == 'S':
        return y
    if side == 'W':
        return x
    return BOARD - x


def event_route_xy(route):
    flat = [part for part in route['parts'] if part['kind'] == 'flat']
    return xy(flat[0]['primitives'][0]['p0']), xy(flat[-1]['primitives'][-1]['p1'])


# ---------------------------------------------------------------------------
# C4 rigid operations: rot90 CCW about (75, 75): (x, y) -> (150 - y, x)
# ---------------------------------------------------------------------------
def rot_xy(point, times=1):
    x, y = float(point[0]), float(point[1])
    for _ in range(int(times) % 4):
        x, y = BOARD - y, x
    return (x, y)


def rot_vec(vector, times=1):
    x, y = float(vector[0]), float(vector[1])
    for _ in range(int(times) % 4):
        x, y = -y, x
    return (x, y)


def rot_primitive(prim, times=1):
    out = dict(prim)
    if prim['kind'] == 'line':
        out['p0'] = list(rot_xy(prim['p0'], times))
        out['p1'] = list(rot_xy(prim['p1'], times))
        return out
    out['p0'] = list(rot_xy(prim['p0'], times))
    out['p1'] = list(rot_xy(prim['p1'], times))
    out['center'] = list(rot_xy(prim['center'], times))
    out['start_angle'] = math.atan2(float(out['p0'][1]) - float(out['center'][1]),
                                    float(out['p0'][0]) - float(out['center'][0]))
    return out


def reverse_primitive(prim):
    out = dict(prim)
    out['p0'] = list(prim['p1'])
    out['p1'] = list(prim['p0'])
    if prim['kind'] == 'arc':
        center = prim['center']
        out['start_angle'] = math.atan2(float(out['p0'][1]) - float(center[1]),
                                        float(out['p0'][0]) - float(center[0]))
        out['sweep'] = -float(prim['sweep'])
    return out


def rotate_part(part, times=1):
    out = dict(part)
    if part['kind'] == 'flat':
        out['primitives'] = [rot_primitive(prim, times)
                             for prim in part['primitives']]
        return out
    out['start'] = list(rot_xy(part['start'], times))
    out['direction'] = list(rot_vec(part['direction'], times))
    out['end'] = list(rot_xy(part['end'], times))
    return out


def reverse_part(part):
    out = dict(part)
    if part['kind'] == 'flat':
        out['primitives'] = [reverse_primitive(prim)
                             for prim in reversed(part['primitives'])]
        return out
    out['start'] = list(part['end'])
    out['end'] = list(part['start'])
    out['direction'] = [-float(part['direction'][0]),
                        -float(part['direction'][1])]
    out['z0'], out['z1'] = float(part['z1']), float(part['z0'])
    out['dz_mm'] = -float(part['dz_mm'])
    out['from_layer'], out['to_layer'] = int(part['to_layer']), int(part['from_layer'])
    return out


def rotate_route(route, times=1):
    out = dict(route)
    out['parts'] = [rotate_part(part, times) for part in route['parts']]
    for key in ('source_port', 'target_port'):
        if isinstance(out.get(key), dict) and 'xy' in out[key]:
            port = dict(out[key])
            port['xy'] = list(rot_xy(port['xy'], times))
            out[key] = port
    return out


def reverse_route(route):
    out = dict(route)
    out['parts'] = [reverse_part(part) for part in reversed(route['parts'])]
    out['layer_sequence'] = list(reversed(route['layer_sequence']))
    out['layer_z_sequence'] = list(reversed(route['layer_z_sequence']))
    out['start_z_mm'] = float(route['end_z_mm'])
    out['end_z_mm'] = float(route['start_z_mm'])
    for key_a, key_b in (('source_port', 'target_port'),):
        if key_a in out and key_b in out:
            out[key_a], out[key_b] = out[key_b], out[key_a]
    return out


# ---------------------------------------------------------------------------
# report object
# ---------------------------------------------------------------------------
class Report:
    def __init__(self):
        self.checks = []
        self.numbers = {}
        self.warnings = []
        self.root_causes = []
        self.production_mismatches = []

    def add(self, name, passed, detail=None, **numbers):
        entry = dict(name=name, passed=bool(passed))
        if detail is not None:
            entry['detail'] = detail
        if numbers:
            entry['numbers'] = numbers
        self.checks.append(entry)
        return entry

    def warn(self, message):
        self.warnings.append(str(message))

    def mismatch(self, topic, production, recomputed):
        self.production_mismatches.append(
            dict(topic=topic, production=production, recomputed=recomputed))

    @property
    def passed(self):
        return all(entry['passed'] for entry in self.checks)


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def load_context():
    ctx = dict()
    ctx['connectivity'] = read_json(CAMPAIGN / 'inputs' / 'connectivity_1024.json')
    ctx['groups'] = {int(g['group_id']): g
                     for g in ctx['connectivity']['groups']}
    ctx['manifest'] = {int(r['route_id']): r
                       for r in ctx['connectivity']['routes']}
    ctx['target_gids'] = sorted(ENERGY_TARGET)
    ctx['target_rids'] = sorted({int(rid) for gid in ENERGY_TARGET
                                 for rid in ctx['groups'][gid]['route_ids']})
    ctx['target_set'] = set(ctx['target_rids'])
    ctx['rid_group'] = {int(rid): gid for gid, group in ctx['groups'].items()
                        for rid in group['route_ids']}
    # canonical endpoint XY: the accepted V2 payload (identity never changes)
    ctx['baseline_payload'] = read_json(AFTER / 'routes_l3d.json')
    ctx['baseline'] = {int(r['route_id']): r
                       for r in ctx['baseline_payload']['routes']
                       if r.get('status') == 'routed'}
    ctx['port_xy'] = {}
    for rid, record in ctx['baseline'].items():
        ctx['port_xy'][record['source_endpoint']] = xy(record['source_port']['xy'])
        ctx['port_xy'][record['target_endpoint']] = xy(record['target_port']['xy'])
    ctx['payloads'] = {}
    for label, name in (('u_only', 'routes_1024_u_only.json'),
                        ('final', 'routes_1024.json')):
        path = PROD / name
        if path.is_file():
            payload = read_json(path)
            ctx['payloads'][label] = dict(
                path=path, payload=payload,
                records={int(r['route_id']): r for r in payload['routes']
                         if r.get('status') == 'routed'})
    ctx['assignment'] = read_json(PROD / 'u_layer_assignment.json') \
        if (PROD / 'u_layer_assignment.json').is_file() else None
    ctx['validation'] = read_json(PROD / 'validation.json') \
        if (PROD / 'validation.json').is_file() else None
    ctx['summary'] = read_json(PROD / 'summary.json') \
        if (PROD / 'summary.json').is_file() else None
    ctx['comparison'] = read_json(PROD / 'comparison_table.json') \
        if (PROD / 'comparison_table.json').is_file() else None
    return ctx


# ---------------------------------------------------------------------------
# 1) payload contract / identity
# ---------------------------------------------------------------------------
def check_payload_contract(report, ctx, label, payload):
    errors = []
    if payload.get('schema') != 'four_side_1024_v2_l3d_routes_v1':
        errors.append(f"schema {payload.get('schema')!r}")
    routes = payload.get('routes') or []
    if len(routes) != 1024:
        errors.append(f'routes {len(routes)} != 1024')
    ids = [int(record['route_id']) for record in routes
           if record.get('route_id') is not None]
    if sorted(ids) != list(range(1, 1025)):
        errors.append('route_id set is not 1..1024')
    routed = [record for record in routes if record.get('status') == 'routed']
    if len(routed) != 1024:
        errors.append(f'routed {len(routed)} != 1024')
    stack = payload.get('layer_stack') or {}
    heights = stack.get('routing_heights_mm') or {}
    for layer_id, z in STACK.items():
        if abs(float(heights.get(str(layer_id), -999.0)) - z) > Z_TOL:
            errors.append(f'stack L{layer_id} != {z}')
    if stack != (ctx['baseline_payload'].get('layer_stack') or {}):
        errors.append('embedded layer_stack differs from V2 baseline')
    report.add(f'{label}_payload_contract', not errors, errors[:10],
               routes=len(routes), routed=len(routed))
    return not errors


def check_identity(report, ctx, label, records):
    errors = []
    endpoints = Counter()
    for rid in range(1, 1025):
        record = records.get(rid)
        if record is None:
            errors.append((rid, 'missing routed record'))
            continue
        manifest = ctx['manifest'].get(rid) or {}
        for key in ('plane', 'source_endpoint', 'target_endpoint', 'relation',
                    'pair', 'source_side', 'target_side', 'source_row',
                    'target_row', 'z_mm'):
            expected = manifest.get(key)
            actual = record.get(key)
            if isinstance(expected, float) or isinstance(actual, float):
                ok = expected is not None and actual is not None and \
                    abs(float(expected) - float(actual)) <= Z_TOL
            else:
                ok = expected == actual
            if not ok:
                errors.append((rid, key, actual, expected))
        for port_key, endpoint_key in (('source_port', 'source_endpoint'),
                                       ('target_port', 'target_endpoint')):
            port = record.get(port_key) or {}
            endpoint = record.get(endpoint_key)
            endpoints[endpoint] += 1
            canonical = ctx['port_xy'].get(endpoint)
            if canonical is None:
                errors.append((rid, port_key, 'unknown endpoint', endpoint))
            elif not close_xy(port.get('xy') or (1e9, 1e9), canonical):
                errors.append((rid, port_key, 'xy', port.get('xy'), canonical))
            if abs(float(port.get('z_mm', 1e9)) - ROW_Z[record['plane']]) > Z_TOL:
                errors.append((rid, port_key, 'z', port.get('z_mm')))
            if int(port.get('layer_id', -1)) != 1:
                errors.append((rid, port_key, 'layer_id', port.get('layer_id')))
    if len(endpoints) != 2048:
        errors.append(('endpoint_count', len(endpoints), 2048))
    reused = [key for key, count in endpoints.items() if count != 1]
    if reused:
        errors.append(('endpoint_usage', reused[:8]))
    report.add(f'{label}_identity', not errors, errors[:12],
               unique_endpoints=len(endpoints), unique_ports_expected=2048)
    return not errors


# ---------------------------------------------------------------------------
# 2) per-route geometry structure
# ---------------------------------------------------------------------------
def check_flat_part(part, route_id, issues):
    path = f"route {route_id} flat part"
    if not isinstance(part.get('primitives'), list) or not part['primitives']:
        issues.append(('empty_flat_part', path))
        return
    total = 0.0
    cursor = None
    for index, prim in enumerate(part['primitives']):
        if prim.get('kind') not in ('line', 'arc'):
            issues.append(('unknown_primitive', path, index, prim.get('kind')))
            continue
        for key in ('p0', 'p1'):
            if len(prim[key]) != 2:
                issues.append(('bad_point', path, index, key))
        if prim['kind'] == 'line':
            dx = float(prim['p1'][0]) - float(prim['p0'][0])
            dy = float(prim['p1'][1]) - float(prim['p0'][1])
            if min(abs(dx), abs(dy)) > 1e-9:
                issues.append(('diagonal_line', path, index, (dx, dy)))
            for point in (prim['p0'], prim['p1']):
                if not inside_board(float(point[0]), float(point[1])):
                    issues.append(('line_outside_board', path, index, point))
        else:
            radius = float(prim.get('radius', -1))
            if abs(radius - R) > 1e-9:
                issues.append(('arc_radius', path, index, radius))
            center = prim.get('center') or [0.0, 0.0]
            if 'center' not in prim:
                issues.append(('arc_without_center', path, index))
            start = float(prim.get('start_angle', 0.0))
            sweep = float(prim.get('sweep', 0.0))
            exp_p0 = (float(center[0]) + radius * math.cos(start),
                      float(center[1]) + radius * math.sin(start))
            exp_p1 = (float(center[0]) + radius * math.cos(start + sweep),
                      float(center[1]) + radius * math.sin(start + sweep))
            if not close_xy(prim['p0'], exp_p0) or not close_xy(prim['p1'], exp_p1):
                issues.append(('arc_endpoint_formula', path, index,
                               dist_xy(prim['p0'], exp_p0),
                               dist_xy(prim['p1'], exp_p1)))
            if abs(sweep) <= 1e-12:
                issues.append(('zero_sweep_arc', path, index))
            for point in arc_points(prim, 16):
                if not inside_board(*point):
                    issues.append(('arc_outside_board', path, index))
                    break
        if cursor is not None and not close_xy(cursor, prim['p0']):
            issues.append(('primitive_discontinuity',
                           f'{path} prim {index}', dist_xy(cursor, prim['p0'])))
        cursor = prim['p1']
        total += prim_length(prim)
    if not close(float(part.get('length_mm', -1.0)), total, FORM_TOL):
        issues.append(('flat_length_mismatch', path,
                       float(part.get('length_mm', -1.0)) - total))


def check_transition_part(part, route_id, previous, following, issues):
    path = f"route {route_id} transition"
    required = ('start', 'direction', 'z0', 'z1', 'dz_mm', 'radius_mm',
                'theta_rad', 'footprint_mm', 'end', 'length_mm',
                'from_layer', 'to_layer')
    for key in required:
        if key not in part:
            issues.append(('missing_transition_field', path, key))
    if any(key not in part for key in required):
        return
    radius = float(part['radius_mm'])
    if abs(radius - R) > 1e-9:
        issues.append(('transition_radius', path, radius))
    dz = abs(float(part['z1']) - float(part['z0']))
    if abs(abs(float(part['dz_mm'])) - dz) > Z_TOL:
        issues.append(('transition_dz_mismatch', path))
    theta = math.acos(max(-1.0, min(1.0, 1.0 - dz / (2.0 * R))))
    if abs(float(part['theta_rad']) - theta) > FORM_TOL:
        issues.append(('transition_theta', path, part['theta_rad'], theta))
    footprint = 2.0 * R * math.sin(theta)
    if abs(float(part['footprint_mm']) - footprint) > FORM_TOL:
        issues.append(('transition_footprint', path, part['footprint_mm']))
    if abs(float(part['length_mm']) - 2.0 * R * theta) > FORM_TOL:
        issues.append(('transition_length', path, part['length_mm']))
    direction = part['direction']
    if abs(math.hypot(float(direction[0]), float(direction[1])) - 1.0) > 1e-9:
        issues.append(('transition_direction_not_unit', path))
    if min(abs(float(direction[0])), abs(float(direction[1]))) > 1e-9:
        issues.append(('transition_direction_not_axis', path))
    expected_end = (float(part['start'][0]) + float(direction[0]) * footprint,
                    float(part['start'][1]) + float(direction[1]) * footprint)
    if not close_xy(part['end'], expected_end):
        issues.append(('transition_end_formula', path))
    if previous is None or previous['kind'] != 'flat':
        issues.append(('transition_not_after_flat', path))
        return
    if following is None or following['kind'] != 'flat':
        issues.append(('transition_not_before_flat', path))
        return
    previous_prim = previous['primitives'][-1]
    if not close_xy(part['start'], previous_prim['p1']):
        issues.append(('transition_start_joint', path,
                       dist_xy(part['start'], previous_prim['p1'])))
    following_prim = following['primitives'][0]
    if not close_xy(part['end'], following_prim['p0']):
        issues.append(('transition_end_joint', path,
                       dist_xy(part['end'], following_prim['p0'])))
    if not close(float(part['z0']), float(previous['z_mm']), Z_TOL):
        issues.append(('transition_z0_joint', path))
    if not close(float(part['z1']), float(following['z_mm']), Z_TOL):
        issues.append(('transition_z1_joint', path))
    # tangent continuity with both adjacent flats
    previous_tangent = None
    if previous_prim['kind'] == 'line':
        previous_tangent = unit((float(previous_prim['p1'][0]) - float(previous_prim['p0'][0]),
                                 float(previous_prim['p1'][1]) - float(previous_prim['p0'][1])))
    else:
        center = previous_prim['center']
        end_angle = float(previous_prim['start_angle']) + float(previous_prim['sweep'])
        sign = 1.0 if float(previous_prim['sweep']) >= 0 else -1.0
        previous_tangent = unit((-sign * math.sin(end_angle),
                                 sign * math.cos(end_angle)))
    if previous_tangent is not None and not close_xy(previous_tangent, unit(direction)):
        issues.append(('transition_tangent_previous', path))
    following_tangent = None
    if following_prim['kind'] == 'line':
        following_tangent = unit((float(following_prim['p1'][0]) - float(following_prim['p0'][0]),
                                  float(following_prim['p1'][1]) - float(following_prim['p0'][1])))
    else:
        center = following_prim['center']
        angle = float(following_prim['start_angle'])
        sign = 1.0 if float(following_prim['sweep']) >= 0 else -1.0
        following_tangent = unit((-sign * math.sin(angle),
                                  sign * math.cos(angle)))
    if following_tangent is not None and not close_xy(following_tangent, unit(direction)):
        issues.append(('transition_tangent_following', path))
    # the S curve must lie entirely on a single straight segment of the 2D path:
    # the straight is split into (previous flat tail line) + (next flat head line)
    contained = False
    if previous_prim['kind'] == 'line' and following_prim['kind'] == 'line':
        prev_dir = unit((float(previous_prim['p1'][0])
                         - float(previous_prim['p0'][0]),
                         float(previous_prim['p1'][1])
                         - float(previous_prim['p0'][1])))
        next_dir = unit((float(following_prim['p1'][0])
                         - float(following_prim['p0'][0]),
                         float(following_prim['p1'][1])
                         - float(following_prim['p0'][1])))
        cross = abs(prev_dir[0] * next_dir[1] - prev_dir[1] * next_dir[0])
        dot = prev_dir[0] * next_dir[0] + prev_dir[1] * next_dir[1]
        if cross <= 1e-6 and dot > 0.0 and \
                point_on_segment(part['start'], previous_prim['p0'],
                                 previous_prim['p1']) and \
                point_on_segment(part['end'], following_prim['p0'],
                                 following_prim['p1']):
            contained = True
    if not contained:
        # alternate form: the whole S lies inside one single line primitive
        for prim in previous['primitives'] + following['primitives']:
            if prim['kind'] == 'line' and \
                    point_on_segment(part['start'], prim['p0'], prim['p1']) and \
                    point_on_segment(part['end'], prim['p0'], prim['p1']):
                contained = True
                break
    if not contained:
        issues.append(('transition_not_on_one_straight', path))
    for point in transition_points(part, 24):
        if not inside_board(point[0], point[1]):
            issues.append(('transition_outside_board', path, point))
            break


def check_route_geometry(report, ctx, label, records):
    issues = []
    stats = dict(routes=0, transitions=0, lifted=0, flat=0)
    for rid in sorted(records):
        record = records[rid]
        parts = record.get('parts') or []
        stats['routes'] += 1
        if not parts:
            issues.append(('empty_parts', rid))
            continue
        if parts[0]['kind'] != 'flat' or parts[-1]['kind'] != 'flat':
            issues.append(('route_not_flat_ended', rid))
        kinds = [part['kind'] for part in parts]
        if any(kinds[index] == kinds[index + 1] for index in range(len(kinds) - 1)):
            issues.append(('consecutive_same_kind_parts', rid, kinds))
        transitions = [part for part in parts if part['kind'] == 'transition']
        flats = [part for part in parts if part['kind'] == 'flat']
        stats['transitions'] += len(transitions)
        stats['lifted'] += 1 if transitions else 0
        stats['flat'] += 0 if transitions else 1
        source_port = record.get('source_port') or {}
        target_port = record.get('target_port') or {}
        row = ROW_OF[record['plane']]
        row_z = ROW_Z[record['plane']]
        # ports / route-level metadata
        if not close(float(record.get('start_z_mm', 1e9)), row_z, Z_TOL) or \
                not close(float(record.get('end_z_mm', 1e9)), row_z, Z_TOL):
            issues.append(('route_start_end_z', rid))
        if int(record.get('n_transitions', -1)) != len(transitions):
            issues.append(('n_transitions_mismatch', rid,
                           record.get('n_transitions'), len(transitions)))
        if bool(record.get('lifted')) != bool(transitions):
            issues.append(('lifted_flag', rid))
        flat_layers = [int(part['layer_id']) for part in flats]
        if record.get('layer_sequence') != flat_layers:
            issues.append(('layer_sequence', rid, record.get('layer_sequence'),
                           flat_layers))
        if record.get('layers_used') != sorted(set(flat_layers)):
            issues.append(('layers_used', rid, record.get('layers_used')))
        z_span = max(float(part['z_mm']) for part in flats) - \
            min(float(part['z_mm']) for part in flats)
        if abs(float(record.get('z_span_mm', -1.0)) - z_span) > Z_TOL:
            issues.append(('z_span', rid, record.get('z_span_mm'), z_span))
        z_sequence = [float(part['z_mm']) for part in flats]
        if [round(value, 9) for value in record.get('layer_z_sequence', [])] != \
                [round(value, 9) for value in z_sequence]:
            issues.append(('layer_z_sequence', rid,
                           record.get('layer_z_sequence'), z_sequence))
        # flat part layer / z model
        for part in flats:
            layer_id = int(part['layer_id'])
            z_mm = float(part['z_mm'])
            if layer_id == 1:
                if abs(z_mm - row_z) > Z_TOL:
                    issues.append(('L1_flat_z', rid, z_mm))
            elif layer_id in STACK:
                if abs(z_mm - STACK[layer_id]) > Z_TOL:
                    issues.append(('high_flat_z', rid, layer_id, z_mm))
            else:
                issues.append(('unknown_layer', rid, layer_id))
            check_flat_part(part, rid, issues)
        # transition / elevation rules
        if len(transitions) not in (0, 2):
            issues.append(('transition_count', rid, len(transitions)))
        if len(transitions) == 2:
            first, second = transitions
            up = float(first['z1']) > float(first['z0'])
            down = float(second['z1']) < float(second['z0'])
            if not (up and down):
                issues.append(('not_one_rise_one_fall', rid))
            if int(first['from_layer']) != 1 or int(second['to_layer']) != 1:
                issues.append(('rise_fall_layer_endpoint', rid))
            if int(first['to_layer']) != int(second['from_layer']):
                issues.append(('rise_fall_layer_mismatch', rid))
            high_layer = int(first['to_layer'])
            if high_layer not in STACK or abs(
                    float(first['z1']) - STACK[high_layer]) > Z_TOL or \
                    abs(float(second['z0']) - STACK[high_layer]) > Z_TOL:
                issues.append(('high_layer_height', rid, high_layer))
            high_flats = [part for part in flats if int(part['layer_id']) != 1]
            if len(high_flats) != 1:
                issues.append(('high_flat_parts', rid, len(high_flats)))
            if len(set(flat_layers)) > 2:
                issues.append(('multiple_high_layers', rid, sorted(set(flat_layers))))
        # XY chain continuity across parts
        cursor = xy(source_port.get('xy') or (1e9, 1e9))
        z_cursor = row_z
        for index, part in enumerate(parts):
            if part['kind'] == 'flat':
                if not close_xy(part['primitives'][0]['p0'], cursor):
                    issues.append(('part_start_joint', rid, index,
                                   dist_xy(part['primitives'][0]['p0'], cursor)))
                if not close(float(part['z_mm']), z_cursor, Z_TOL):
                    issues.append(('part_z_joint', rid, index))
                cursor = xy(part['primitives'][-1]['p1'])
                z_cursor = float(part['z_mm'])
            else:
                previous = parts[index - 1] if index > 0 else None
                following = parts[index + 1] if index + 1 < len(parts) else None
                check_transition_part(part, rid, previous, following, issues)
                cursor = xy(part['end'])
                z_cursor = float(part['z1'])
        if not close_xy(cursor, target_port.get('xy') or (1e9, 1e9)):
            issues.append(('route_end_port', rid, dist_xy(
                cursor, target_port.get('xy') or (1e9, 1e9))))
        # aggregate lengths
        part_length = sum(float(part.get('length_mm', 0.0)) for part in parts)
        if abs(float(record.get('length_mm', -1.0)) - part_length) > LEN_TOL:
            issues.append(('route_length', rid,
                           float(record.get('length_mm', -1.0)) - part_length))
        xy_length = sum(prim_length(prim) for part in flats
                        for prim in part['primitives']) + \
            sum(float(part['footprint_mm']) for part in transitions)
        if abs(float(record.get('xy_length_mm', -1.0)) - xy_length) > LEN_TOL:
            issues.append(('xy_length', rid,
                           float(record.get('xy_length_mm', -1.0)) - xy_length))
    counts = Counter(issue[0] for issue in issues)
    report.add(f'{label}_route_geometry', not issues,
               [list(item) for item in issues[:20]],
               **{**stats, 'issue_count': len(issues),
                  'issue_kinds': dict(counts)})
    return issues


# ---------------------------------------------------------------------------
# 3) target quartet checks: layer / U shape / C4 rotation
# ---------------------------------------------------------------------------
def separation_and_side(ctx, gid):
    ids = [int(rid) for rid in ctx['groups'][gid]['route_ids']]
    rep = ctx['baseline'][ids[0]]
    side = rep['source_side']
    p = ctx['port_xy'][rep['source_endpoint']]
    q = ctx['port_xy'][rep['target_endpoint']]
    separation = abs(p[0] - q[0]) if side in 'NS' else abs(p[1] - q[1])
    return side, float(separation)


def target_route_errors(ctx, gid, rid, record, target_layer):
    errors = []
    ids = [int(value) for value in ctx['groups'][gid]['route_ids']]
    side = record['source_side']          # every member is checked in its own side frame
    _, separation = separation_and_side(ctx, gid)
    target_z = STACK[target_layer]
    row_z = ROW_Z[record['plane']]
    parts = record.get('parts') or []
    flats = [part for part in parts if part['kind'] == 'flat']
    high = [part for part in flats if int(part['layer_id']) != 1]
    if len(high) != 1:
        return [('high_flat_count', len(high))]
    if int(high[0]['layer_id']) != target_layer:
        errors.append(('high_layer', int(high[0]['layer_id']), target_layer))
    if abs(float(high[0]['z_mm']) - target_z) > Z_TOL:
        errors.append(('high_layer_z', float(high[0]['z_mm']), target_z))
    if record.get('layer_sequence') != [1, target_layer, 1]:
        errors.append(('layer_sequence', record.get('layer_sequence')))
    if len(parts) != 5 or [part['kind'] for part in parts] != \
            ['flat', 'transition', 'flat', 'transition', 'flat']:
        errors.append(('parts', [part['kind'] for part in parts]))
        return errors
    # base entry / exit straights
    first, last = parts[0], parts[4]
    for part_name, part in (('first', first), ('last', last)):
        if len(part['primitives']) != 1 or part['primitives'][0]['kind'] != 'line':
            errors.append((f'{part_name}_base_straight', 'not a single line'))
    inward = INWARD[side]
    first_dir = unit((float(first['primitives'][-1]['p1'][0])
                      - float(first['primitives'][-1]['p0'][0]),
                      float(first['primitives'][-1]['p1'][1])
                      - float(first['primitives'][-1]['p0'][1])))
    last_dir = unit((float(last['primitives'][-1]['p1'][0])
                     - float(last['primitives'][-1]['p0'][0]),
                     float(last['primitives'][-1]['p1'][1])
                     - float(last['primitives'][-1]['p0'][1])))
    if not close_xy(first_dir, inward):
        errors.append(('entry_straight_direction', first_dir, inward))
    if not close_xy(last_dir, (-inward[0], -inward[1])):
        errors.append(('exit_straight_direction', last_dir))
    if abs(float(first['primitives'][0]['p0'][0])
           - float(first['primitives'][0]['p0'][0])) > 0:
        pass
    if not close_xy(first['primitives'][0]['p0'], ctx['port_xy'][record['source_endpoint']]):
        errors.append(('entry_straight_starts_at_port',))
    if not close_xy(last['primitives'][-1]['p1'], ctx['port_xy'][record['target_endpoint']]):
        errors.append(('exit_straight_ends_at_port',))
    # main arcs on the target layer: exactly two R15 quarter arcs + middle straight
    high_prims = high[0]['primitives']
    arcs = [(index, prim) for index, prim in enumerate(high_prims)
            if prim['kind'] == 'arc']
    if len(arcs) != 2:
        errors.append(('high_arc_count', len(arcs)))
    else:
        for index, prim in arcs:
            if abs(float(prim['radius']) - R) > 1e-9:
                errors.append(('high_arc_radius', index, prim['radius']))
            if abs(abs(float(prim['sweep'])) - math.pi / 2.0) > 1e-9:
                errors.append(('high_arc_sweep', index, prim['sweep']))
        first_index, second_index = arcs[0][0], arcs[1][0]
        middle = [prim for prim in high_prims[first_index + 1:second_index]
                  if prim['kind'] == 'line']
        middle_length = sum(prim_length(prim) for prim in middle)
        if abs(middle_length - (separation - 2.0 * R)) > FORM_TOL:
            errors.append(('middle_straight', middle_length,
                           separation - 2.0 * R))
        # both arc ends must sit at the same target-layer depth
        d0 = depth_of(side, arcs[0][1]['p0'])
        d1 = depth_of(side, arcs[1][1]['p1'])
        if abs(d0 - d1) > POS_TOL:
            errors.append(('arc_depths_differ', d0, d1))
    return errors


def check_target_quartets(report, ctx, label, records, use_assignment=False):
    errors = []
    reached = []
    details = {}
    assignment_rows = {}
    if use_assignment and ctx.get('assignment'):
        assignment_rows = {int(row['group_id']): row
                           for row in (ctx['assignment'].get('assignment') or [])}
    for gid in ctx['target_gids']:
        ids = [int(rid) for rid in ctx['groups'][gid]['route_ids']]
        target_layer = ENERGY_TARGET[gid]
        group_errors = []
        rebuilt_flags = []
        for rid in ids:
            record = records.get(rid)
            if record is None:
                group_errors.append((rid, 'missing'))
                continue
            rebuilt = record != ctx['baseline'][rid]
            rebuilt_flags.append((rid, rebuilt))
            group_errors.extend((rid,) + tuple(error)
                                for error in target_route_errors(
                                    ctx, gid, rid, record, target_layer))
        rebuilt = all(flag for _rid, flag in rebuilt_flags)
        ok = rebuilt and not group_errors
        if ok:
            reached.append(gid)
        details[gid] = dict(rebuilt=rebuilt, ok=ok, target_layer=target_layer,
                            errors=[list(item) for item in group_errors[:6]])
        if group_errors:
            errors.append(dict(group_id=gid, target_layer=target_layer,
                               rebuilt=rebuilt,
                               errors=[list(item) for item in group_errors[:4]]))
        # assignment-parameter consistency (only for rebuilt groups)
        row = assignment_rows.get(gid)
        if row is not None and rebuilt and not group_errors:
            rep = records[ids[0]]
            flats = [part for part in rep['parts'] if part['kind'] == 'flat']
            high = [part for part in flats if int(part['layer_id']) != 1][0]
            arcs = [prim for prim in high['primitives'] if prim['kind'] == 'arc']
            side_row, _sep = separation_and_side(ctx, gid)
            first_len = float(flats[0]['length_mm'])
            last_len = float(flats[-1]['length_mm'])
            arc_depth = depth_of(side_row, arcs[0]['p0'])
            for name, stored, actual in (
                    ('entry_straight_mm', row.get('entry_straight_mm'), first_len),
                    ('exit_straight_mm', row.get('exit_straight_mm'), last_len),
                    ('high_arc_depth_mm', row.get('high_arc_depth_mm'), arc_depth)):
                if stored is None or abs(float(stored) - float(actual)) > POS_TOL:
                    errors.append(dict(group_id=gid, parameter=name,
                                       stored=stored, actual=actual))
            if row.get('a_in') is not None and row.get('a_out') is not None and \
                    abs(float(row['a_in']) - float(row['a_out'])) > POS_TOL:
                errors.append(dict(group_id=gid, parameter='a_in!=a_out'))
        # assignment status must agree with the independent target-layer test
        if row is not None:
            expected_status = 'target_layer_reached' if ok else 'failed'
            if row.get('status') != expected_status:
                errors.append(dict(group_id=gid, assignment_status=row.get('status'),
                                   independent_status=expected_status))
    detail = dict(target=len(ctx['target_gids']), reached=len(reached),
                  failed=sorted(set(ctx['target_gids']) - set(reached)),
                  problems=errors[:20], details=details)
    if label == 'final':
        # the experiment contract requires 64/64 target quartets on their layer
        passed = (not errors) and len(reached) == len(ctx['target_gids'])
    else:
        # intermediate variant: rebuilt quartets must be geometrically clean;
        # the production u_only stage is allowed to leave some groups on V2 geometry
        passed = not [item for item in errors
                      if isinstance(item, dict) and item.get('rebuilt')]
    report.add(f'{label}_target_quartets', passed, detail,
               reached=len(reached),
               failed=len(ctx['target_gids']) - len(reached))
    return set(reached), details


def compare_primitive(expected, actual, route_id, part_index, prim_index, errors):
    if expected['kind'] != actual.get('kind'):
        errors.append((route_id, part_index, prim_index, 'prim_kind',
                       actual.get('kind'), expected['kind']))
        return
    for key in ('p0', 'p1'):
        if not close_xy(expected[key], actual.get(key) or (1e9, 1e9)):
            errors.append((route_id, part_index, prim_index, key))
    if expected['kind'] == 'arc':
        if not close_xy(expected['center'], actual.get('center') or (1e9, 1e9)):
            errors.append((route_id, part_index, prim_index, 'center'))
        if abs(float(actual.get('radius', -1)) - float(expected['radius'])) > 1e-9:
            errors.append((route_id, part_index, prim_index, 'radius'))
        if abs(float(actual.get('sweep', 0.0)) - float(expected['sweep'])) > 1e-9:
            errors.append((route_id, part_index, prim_index, 'sweep'))
        if angle_diff(actual.get('start_angle', 0.0),
                      expected['start_angle']) > 1e-6:
            errors.append((route_id, part_index, prim_index, 'start_angle'))


def compare_route_with_rotation(expected, actual, errors, label):
    route_id = int(actual['route_id'])
    if [part['kind'] for part in expected['parts']] != \
            [part['kind'] for part in actual['parts']]:
        errors.append((route_id, label, 'part_kinds'))
        return
    for part_index, (exp, act) in enumerate(zip(expected['parts'],
                                                actual['parts'])):
        if exp['kind'] == 'flat':
            if int(exp['layer_id']) != int(act['layer_id']):
                errors.append((route_id, label, part_index, 'layer_id'))
            if abs(float(exp['z_mm']) - float(act['z_mm'])) > Z_TOL:
                errors.append((route_id, label, part_index, 'z_mm'))
            if abs(float(exp['length_mm']) - float(act['length_mm'])) > LEN_TOL:
                errors.append((route_id, label, part_index, 'length_mm'))
            if len(exp['primitives']) != len(act['primitives']):
                errors.append((route_id, label, part_index, 'prim_count'))
                continue
            for prim_index, (exp_prim, act_prim) in enumerate(
                    zip(exp['primitives'], act['primitives'])):
                compare_primitive(exp_prim, act_prim, route_id, part_index,
                                  prim_index, errors)
        else:
            for key in ('z0', 'z1'):
                if abs(float(exp[key]) - float(act[key])) > Z_TOL:
                    errors.append((route_id, label, part_index, key))
            for key in ('from_layer', 'to_layer'):
                if int(exp[key]) != int(act[key]):
                    errors.append((route_id, label, part_index, key))
            for key in ('radius_mm', 'theta_rad', 'footprint_mm', 'length_mm'):
                if abs(float(exp[key]) - float(act[key])) > FORM_TOL:
                    errors.append((route_id, label, part_index, key))
            for key in ('start', 'direction', 'end'):
                if not close_xy(exp[key], act[key]):
                    errors.append((route_id, label, part_index, key))
    for key in ('layer_sequence', 'layer_z_sequence'):
        if [round(float(value), 9) for value in expected[key]] != \
                [round(float(value), 9) for value in actual.get(key, [])]:
            errors.append((route_id, label, key))


def check_c4_rotations(report, ctx, label, records, reached):
    errors = []
    audited = []
    for gid in ctx['target_gids']:
        if reached is not None and gid not in reached:
            continue
        ids = [int(rid) for rid in ctx['groups'][gid]['route_ids']]
        rep = records[ids[0]]
        for phase in range(1, 4):
            member = records[ids[phase]]
            rotated = rotate_route(rep, phase)
            start_xy, _end_xy = event_route_xy(rotated)
            if not close_xy(start_xy, member['source_port']['xy']):
                rotated = reverse_route(rotated)
                start_xy, end_xy = event_route_xy(rotated)
                if not close_xy(start_xy, member['source_port']['xy']) or \
                        not close_xy(end_xy, member['target_port']['xy']):
                    errors.append((gid, ids[phase], 'orientation'))
                    continue
            else:
                _s, end_xy = event_route_xy(rotated)
                if not close_xy(end_xy, member['target_port']['xy']):
                    errors.append((gid, ids[phase], 'orientation_end'))
                    continue
            if not close_xy(rotated['source_port']['xy'],
                            member['source_port']['xy']) or \
                    not close_xy(rotated['target_port']['xy'],
                                 member['target_port']['xy']):
                errors.append((gid, ids[phase], 'ports'))
            compare_route_with_rotation(rotated, member, errors,
                                        f'phase{phase}')
            audited.append((gid, phase))
    report.add(f'{label}_c4_rotation_symmetry', not errors,
               [list(item) for item in errors[:20]],
               audited_groups=len({gid for gid, _p in audited}),
               audited_members=len(audited))
    return not errors


# ---------------------------------------------------------------------------
# 4) V2 invariance / local reroute bookkeeping
# ---------------------------------------------------------------------------
def difference_keys(first, second):
    keys = set(first) | set(second)
    return sorted(key for key in keys if first.get(key) != second.get(key))


def check_baseline_invariance(report, ctx):
    baseline = ctx['baseline']
    target = ctx['target_set']
    moved = set(MOVED_RIDS)
    results = {}
    if 'u_only' in ctx['payloads']:
        records = ctx['payloads']['u_only']['records']
        changed = []
        for rid in sorted(set(baseline) - target):
            if rid not in records or records[rid] != baseline[rid]:
                changed.append(rid)
        results['u_only'] = changed
        report.add('u_only_v2_invariance',
                   not changed,
                   dict(non_target=len(baseline) - len(target),
                        changed=[rid for rid in changed[:20]]),
                   non_target=len(baseline) - len(target),
                   changed=len(changed))
    final_changed, moved_report = [], []
    if 'final' in ctx['payloads']:
        records = ctx['payloads']['final']['records']
        expected_moved = sorted(int(rid) for rid in
                                ctx['groups'][MOVED_GID]['route_ids'])
        if expected_moved != sorted(MOVED_RIDS):
            report.add('group11_route_ids', False,
                       dict(actual=expected_moved, expected=sorted(MOVED_RIDS)))
        for rid in sorted(set(baseline) - target - moved):
            if rid not in records or records[rid] != baseline[rid]:
                final_changed.append(rid)
        for rid in sorted(moved):
            before = baseline.get(rid)
            after = records.get(rid)
            item = dict(route_id=rid)
            if before is None or after is None:
                item['error'] = 'missing route'
                moved_report.append(item)
                continue
            identity_keys = ('plane', 'source_endpoint', 'target_endpoint',
                             'relation', 'pair', 'source_side', 'target_side',
                             'source_row', 'target_row')
            item['identity_unchanged'] = all(
                before.get(key) == after.get(key) for key in identity_keys)
            item['ports_unchanged'] = (
                before['source_port']['xy'] == after['source_port']['xy'] and
                before['target_port']['xy'] == after['target_port']['xy'])
            item['layer_before'] = before.get('layer_sequence')
            item['layer_after'] = after.get('layer_sequence')
            item['z_before'] = before.get('layer_z_sequence')
            item['z_after'] = after.get('layer_z_sequence')
            item['n_transitions'] = after.get('n_transitions')
            high = [part for part in (after.get('parts') or [])
                    if part['kind'] == 'flat' and int(part['layer_id']) != 1]
            item['high_flat_z'] = [float(part['z_mm']) for part in high]
            item['changed_fields'] = difference_keys(before, after)
            item['geometry_ok'] = bool(
                after.get('layer_sequence') == [1, 5, 1] and
                before.get('layer_sequence') == [1, 3, 1] and
                all(abs(float(part['z_mm']) - 2.5) <= Z_TOL for part in high))
            moved_report.append(item)
        report.add('final_v2_invariance',
                   not final_changed,
                   dict(non_target=len(baseline) - len(target) - len(moved),
                        changed=[rid for rid in final_changed[:20]]),
                   non_target=len(baseline) - len(target) - len(moved),
                   changed=len(final_changed))
        geometry_ok = all(item.get('identity_unchanged') and
                          item.get('ports_unchanged') for item in moved_report)
        layers_ok = all(item.get('geometry_ok') for item in moved_report)
        report.add('final_moved_group11',
                   geometry_ok and layers_ok,
                   dict(expected_group= MOVED_GID,
                        route_ids=sorted(MOVED_RIDS),
                        report=moved_report),
                   moved_routes=len(moved_report))
        results['final'] = dict(changed=final_changed, moved=moved_report)
    return results


def check_group11_geometry_context(report, ctx):
    """Document *why* the moved quartet is invalid (if it is)."""
    if 'final' not in ctx['payloads']:
        return
    records = ctx['payloads']['final']['records']
    baseline = ctx['baseline']
    findings = []
    for rid in MOVED_RIDS:
        record = records.get(rid)
        before = baseline.get(rid)
        if record is None or before is None:
            continue
        gaps = []
        for part_index, part in enumerate(record.get('parts') or []):
            if part['kind'] != 'flat':
                continue
            prims = part['primitives']
            for index in range(len(prims) - 1):
                distance = dist_xy(prims[index]['p1'], prims[index + 1]['p0'])
                if distance > POS_TOL:
                    gaps.append(dict(part=part_index, joint=index,
                                     distance_mm=round(distance, 6)))
        findings.append(dict(route_id=rid,
                             old_layer=before.get('layer_sequence'),
                             new_layer=record.get('layer_sequence'),
                             flat_discontinuities=gaps))
    report.add('final_moved_group11_geometry', not any(
        item['flat_discontinuities'] for item in findings),
        dict(note='each flat part must be one continuous sub-chain; a gap equal to '
                  'an old transition footprint indicates the 2D chain was '
                  'assembled from flattened parts of the already-lifted route',
             findings=findings))
    gap_values = [gap['distance_mm'] for item in findings
                  for gap in item['flat_discontinuities']]
    if gap_values:
        report.root_causes.append(dict(
            item='final 版 moved group 11 四元组几何不连续',
            evidence=f'flat part 内 primitive 间距 {sorted(set(gap_values))} mm，'
                     f'等于旧 L3 抬升(dz=1.5) transition 的水平投影长度；'
                     f'说明局部重抬升用的 2D 链由已抬升路线的 flat parts 拼接，'
                     f'丢掉了 transition 的水平段',
            routes=dict(findings=[dict(route_id=item['route_id'],
                                       gaps=item['flat_discontinuities'])
                                  for item in findings])))


# ---------------------------------------------------------------------------
# 5) authoritative validator + independent metrics
# ---------------------------------------------------------------------------
def run_validator(payload):
    from four_side_1024.v3c4.lift_cross import validate_payload_v4
    started = time.perf_counter()
    result = validate_payload_v4(payload, PHASE2, log=lambda *a, **k: None)
    return result, time.perf_counter() - started


def validator_block(result):
    stats = result.get('stats') or {}
    return dict(
        status=result.get('status'),
        exploratory_pass=bool(result.get('exploratory_pass')),
        geometry_pass=bool(result.get('geometry_pass')),
        formal_acceptance=bool(result.get('formal_acceptance')),
        counts=dict(result.get('counts') or {}),
        min_curvature_radius_mm=stats.get('min_curvature_radius_mm'),
        min_3d_clearance_mm=stats.get('min_3d_clearance_mm'),
        violations=len(result.get('violations') or []),
        runtime_seconds=round(result.get('runtime_seconds') or 0.0, 3))


def check_validator(report, ctx, label, payload, expected_pass, skipped=False):
    if skipped:
        report.add(f'{label}_l3d_validator', True, 'skipped', skipped=True)
        return None
    result, seconds = run_validator(payload)
    block = validator_block(result)
    block['wall_seconds'] = round(seconds, 2)
    errors = []
    if not block['exploratory_pass']:
        errors.append('exploratory_pass=false')
    counts = block['counts']
    nonzero = {key: int(counts.get(key, 0)) for key in CATEGORIES
               if int(counts.get(key, 0)) != 0}
    if nonzero:
        errors.append(dict(nonzero_counts=nonzero))
    if not expected_pass:
        errors.append('validator FAIL expected for this variant?')
    if block['formal_acceptance']:
        errors.append('formal_acceptance unexpectedly true')
    if block['status'] != 'exploratory_only':
        errors.append(f"status {block['status']!r}")
    curvature = block['min_curvature_radius_mm']
    if curvature is None or abs(float(curvature) - R) > 1e-3:
        errors.append(dict(min_curvature=curvature))
    if block['min_3d_clearance_mm'] is not None and \
            float(block['min_3d_clearance_mm']) < CLEAR - 1e-6:
        errors.append(dict(min_3d=block['min_3d_clearance_mm']))
    # violations attributed to connection groups
    group_hits = Counter()
    for violation in (result.get('violations') or [])[:400]:
        for key in ('route_id', 'other_route'):
            value = violation.get(key)
            if value is None:
                continue
            try:
                rid = int(str(value).split(':')[0])
            except (TypeError, ValueError):
                continue
            group_id = ctx['rid_group'].get(rid)
            if group_id is not None:
                group_hits[group_id] += 1
    report.add(f'{label}_l3d_validator', not errors, dict(errors=errors,
                                                          group_hits=dict(
                                                              group_hits.most_common(15))),
               **{key: value for key, value in block.items() if key != 'counts'})
    return block


def payload_metrics(records, target_rids):
    entries = defaultdict(list)
    for rid, record in records.items():
        for part in record.get('parts') or []:
            if part['kind'] == 'flat':
                entries[round(float(part['z_mm']), 9)].append(
                    (int(rid), part['primitives']))
    unique_pairs = set()
    pairs_by_height = {}
    points_by_height = {}
    violations = 0
    for z_mm in sorted(entries):
        prepared = [V.prepare_route(primitives, rid)
                    for rid, primitives in entries[z_mm]]
        audit = V.audit_route_pairs(prepared, clearance=CLEAR,
                                    sagitta=SAGITTA, policy='strict')
        pairs_by_height[str(z_mm)] = int(audit.get('crossing_pair_count') or 0)
        points_by_height[str(z_mm)] = int(audit.get('crossing_count') or 0)
        violations += len(audit.get('violations') or [])
        for item in audit.get('crossings') or []:
            first, second = int(item['route_a']), int(item['route_b'])
            unique_pairs.add((min(first, second), max(first, second)))
    uu_pairs = set()
    for z_mm in sorted(entries):
        selected = [(rid, primitives) for rid, primitives in entries[z_mm]
                    if rid in target_rids]
        if len(selected) < 2:
            continue
        prepared = [V.prepare_route(primitives, rid) for rid, primitives in selected]
        audit = V.audit_route_pairs(prepared, clearance=CLEAR,
                                    sagitta=SAGITTA, policy='strict')
        for item in audit.get('crossings') or []:
            first, second = int(item['route_a']), int(item['route_b'])
            uu_pairs.add((min(first, second), max(first, second)))
    layer_defs = [('L1-z1', 1, 0.0), ('L1-z2', 1, 0.5), ('L2', 2, 1.0),
                  ('L3', 3, 1.5), ('L4', 4, 2.0), ('L5', 5, 2.5)]
    layer_counts = {}
    for name, layer_id, z_mm in layer_defs:
        users = []
        for rid, record in records.items():
            for part in record.get('parts') or []:
                if part['kind'] == 'flat' and int(part['layer_id']) == layer_id \
                        and abs(float(part['z_mm']) - z_mm) <= Z_TOL:
                    users.append(int(rid))
                    break
        layer_counts[name] = len(users)
    transitions = sum(int(record.get('n_transitions') or 0)
                      for record in records.values())
    total_length = sum(float(record.get('length_mm') or 0.0)
                       for record in records.values())
    return dict(
        routed=len(records),
        failed=1024 - len(records),
        unique_crossing_pairs=len(unique_pairs),
        unique_crossing_pairs_by_height=pairs_by_height,
        crossing_points_by_height=points_by_height,
        crossing_points_total=sum(points_by_height.values()),
        strict_2d_violations=violations,
        same_layer_u_u_crossing_pairs=len(uu_pairs),
        transitions=int(transitions),
        total_length_mm=round(total_length, 4),
        layer_counts=layer_counts,
        plane_route_counts=dict(Counter(record['plane']
                                        for record in records.values())))


def compare_metric_block(report, label, production, recomputed, keys):
    mismatches = []
    for key, tol in keys:
        if production is None or key not in production:
            continue
        expected = production.get(key)
        actual = recomputed.get(key)
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) \
                and not isinstance(expected, bool):
            ok = abs(float(expected) - float(actual)) <= tol
        else:
            ok = expected == actual
        if not ok:
            mismatches.append(dict(metric=key, production=expected,
                                   recomputed=actual))
    report.add(f'{label}_metrics_match_production', not mismatches,
               mismatches[:20], mismatches=len(mismatches))
    for item in mismatches:
        report.mismatch(f'{label}.{item["metric"]}', item['production'],
                        item['recomputed'])
    return mismatches


def check_metrics(report, ctx, computed):
    """Compare independent metrics with summary.json / comparison_table.json."""
    summary = ctx.get('summary') or {}
    if 'final' in computed:
        compare_metric_block(report, 'final', summary, computed['final'], [
            ('routed', 0), ('failed', 0),
            ('unique_crossing_pairs', 0),
            ('same_layer_u_u_crossing_pairs', 0),
            ('transitions', 0),
            ('total_length_mm', 1e-3),
            ('min_3d_clearance_mm', 1e-6),
            ('baseline_pairs', 0), ('pair_delta', 0),
        ])
        reached = computed['final'].get('target_reached')
        if reached is not None and summary.get('target_quartets_reached') is not None \
                and int(summary['target_quartets_reached']) != int(reached):
            report.mismatch('final.target_quartets_reached',
                            summary.get('target_quartets_reached'), reached)
        layer_counts = computed['final'].get('layer_counts') or {}
        stored = (summary.get('layer_counts') or {})
        stored_counts = {name: (value.get('count') if isinstance(value, dict)
                                else value) for name, value in stored.items()}
        if stored_counts and stored_counts != layer_counts:
            report.mismatch('final.layer_counts', stored_counts, layer_counts)
        moves = summary.get('moved_routes')
        if moves is not None and sorted(int(value) for value in moves) != \
                sorted(MOVED_RIDS):
            report.mismatch('final.moved_routes', moves, sorted(MOVED_RIDS))
        if not summary.get('moved_quartets'):
            report.mismatch('final.moved_quartets', summary.get('moved_quartets'),
                            True)
    comparison = ctx.get('comparison') or {}
    if comparison:
        try:
            columns = comparison['columns']
            column_of = {}
            for index, name in enumerate(columns):
                if 'u-only' in name or '仅修改' in name:
                    column_of['u_only'] = index
                elif '最终' in name or 'final' in name.lower():
                    column_of['final'] = index
                else:
                    column_of['baseline'] = index
            row_lookup = {row['metric']: row for row in comparison['rows']}
            mapping = [
                ('总布通数', 'routed', 0),
                ('唯一交叉线路对（全局去重）', 'unique_crossing_pairs', 0),
                ('同层 U-U 交叉对', 'same_layer_u_u_crossing_pairs', 0),
                ('升降次数', 'transitions', 0),
                ('三维总路径长度 (mm)', 'total_length_mm', 1e-3),
                ('最小三维净空 (mm)', 'min_3d_clearance_mm', 1e-3),
            ]
            mismatches = []
            for metric_name, key, tol in mapping:
                row = row_lookup.get(metric_name)
                if row is None:
                    mismatches.append(dict(metric=metric_name, problem='row missing'))
                    continue
                for variant, index in column_of.items():
                    if variant not in computed:
                        continue
                    stored = row['values'].get(columns[index])
                    actual = computed[variant].get(key)
                    if stored is None or actual is None:
                        continue
                    if isinstance(stored, (int, float)) and not isinstance(stored, bool):
                        ok = abs(float(stored) - float(actual)) <= tol
                    else:
                        ok = stored == actual
                    if not ok:
                        mismatches.append(dict(metric=metric_name,
                                               variant=variant,
                                               production=stored,
                                               recomputed=actual))
            report.add('comparison_table_match', not mismatches,
                       mismatches[:20], mismatches=len(mismatches))
            for item in mismatches:
                report.mismatch(f'comparison.{item.get("variant")}.{item["metric"]}',
                                item.get('production'), item.get('recomputed'))
        except (KeyError, TypeError) as exc:
            report.add('comparison_table_match', False,
                       f'comparison_table unreadable: {type(exc).__name__}: {exc}')


def check_assignment_artifacts(report, ctx, computed):
    assignment = ctx.get('assignment')
    if assignment is None:
        report.add('u_layer_assignment', False, 'missing u_layer_assignment.json')
        return
    errors = []
    if assignment.get('target_quartets') != 64:
        errors.append(dict(target_quartets=assignment.get('target_quartets')))
    rows = assignment.get('assignment') or []
    by_gid = {int(row['group_id']): row for row in rows}
    if set(by_gid) != set(ctx['target_gids']):
        errors.append(dict(coverage=len(by_gid)))
    for gid in ctx['target_gids']:
        row = by_gid.get(gid)
        if row is None:
            errors.append(dict(group_id=gid, problem='missing row'))
            continue
        expected_ids = [int(rid) for rid in ctx['groups'][gid]['route_ids']]
        if [int(rid) for rid in row.get('route_ids') or []] != expected_ids:
            errors.append(dict(group_id=gid, problem='route_ids'))
        if int(row.get('target_layer', -1)) != ENERGY_TARGET[gid]:
            errors.append(dict(group_id=gid, problem='target_layer',
                               stored=row.get('target_layer')))
        if abs(float(row.get('target_z_mm', -1)) - STACK[ENERGY_TARGET[gid]]) > 1e-9:
            errors.append(dict(group_id=gid, problem='target_z'))
    moved = assignment.get('modified_non_u_routes')
    if not moved:
        errors.append(dict(problem='modified_non_u_routes missing / empty'))
    else:
        if int(moved.get('group_id', -1)) != MOVED_GID:
            errors.append(dict(problem='moved group id', stored=moved.get('group_id')))
        if sorted(int(rid) for rid in moved.get('route_ids') or []) != \
                sorted(MOVED_RIDS):
            errors.append(dict(problem='moved route_ids',
                               stored=moved.get('route_ids')))
        if int(moved.get('target_layer', -1)) != 5 or \
                abs(float(moved.get('layer_z_mm', -1)) - 2.5) > 1e-9:
            errors.append(dict(problem='moved layer/z'))
    reached = sum(1 for row in rows
                  if row.get('status') == 'target_layer_reached')
    if int(assignment.get('reached', -1)) != reached:
        errors.append(dict(problem='reached counter',
                           stored=assignment.get('reached'), counted=reached))
    summary = ctx.get('summary') or {}
    if summary.get('target_quartets_reached') is not None and \
            int(summary['target_quartets_reached']) != reached:
        report.mismatch('summary.target_quartets_reached',
                        summary['target_quartets_reached'], reached)
    failed_reasons = {int(row['group_id']): row.get('failure_reason')
                      for row in rows if row.get('status') != 'target_layer_reached'}
    stored_failures = {int(key): value.get('reason')
                       if isinstance(value, dict) else value
                       for key, value in (summary.get('failures') or {}).items()}
    if set(stored_failures) != set(failed_reasons):
        report.mismatch('summary.failure_groups', sorted(stored_failures),
                        sorted(failed_reasons))
    report.add('u_layer_assignment', not errors, errors[:20],
               rows=len(rows), reached=reached,
               failed=sorted(failed_reasons),
               failed_reasons=failed_reasons)


def check_validation_artifact(report, ctx):
    payload = ctx.get('validation')
    if payload is None:
        report.add('validation_artifact', False, 'missing validation.json')
        return
    errors = []
    if payload.get('schema') != 'manual_c4_spatial_u_bundle_validation_v1':
        errors.append(dict(schema=payload.get('schema')))
    for key in ('payload_validation', 'u_only_payload_validation',
                'baseline_payload_validation'):
        if not isinstance(payload.get(key), dict):
            errors.append({key: 'missing'})
    report.add('validation_artifact', not errors, errors[:10],
               final_label=payload.get('final_label'))


def check_figures(report, ctx, mode):
    summary = ctx.get('summary') or {}
    figures = summary.get('figures')
    directory = PROD / 'figures'
    problems = []
    if not directory.is_dir():
        problems.append('figures dir missing')
    present = sorted(path.stem for path in directory.glob('*')
                     if path.suffix in ('.png', '.svg')) if directory.is_dir() else []
    stems = sorted(set(present))
    missing = [stem for stem in FIGURE_STEMS if stem not in stems]
    for stem in FIGURE_STEMS:
        for suffix in ('.png', '.svg'):
            path = directory / f'{stem}{suffix}'
            if not path.is_file():
                continue
            if path.stat().st_size < 1000:
                problems.append(f'{path.name} too small')
    if figures is None:
        problems.append('summary.figures missing (production figure stage failed)')
    else:
        resolved = Path(figures) if isinstance(figures, str) else figures
        if isinstance(resolved, Path) and resolved.is_dir() and \
                resolved.resolve() != directory.resolve():
            problems.append(f'summary.figures points to {resolved}')
    if missing:
        problems.append(dict(missing_stems=missing))
    # exact production error line from run.log (evidence for the root cause)
    figure_log_error = None
    log_path = PROD / 'run.log'
    if log_path.is_file():
        for line in log_path.read_text(encoding='utf-8', errors='replace').splitlines():
            if 'figures failed' in line:
                figure_log_error = line.strip()
    if mode == 'skip':
        report.add('figures', True, 'skipped', missing=len(missing),
                   present=len(stems))
        return
    passed = not problems
    detail = dict(figure_stems_expected=len(FIGURE_STEMS),
                  present_stems=len(stems), missing=missing,
                  summary_figures=figures, figure_log_error=figure_log_error,
                  problems=problems[:10])
    if mode == 'warn' and not passed:
        report.add('figures', True, dict(warning='figure artefacts incomplete',
                                         **detail))
        report.warn('figures: ' + json.dumps(detail, ensure_ascii=False)[:400])
        if missing:
            report.root_causes.append(dict(
                item='图件未生成完整（生产 figure 阶段报错）',
                evidence=f'present={len(stems)}/{len(FIGURE_STEMS)} stems; '
                         f'missing={missing}; summary.figures={figures!r}; '
                         f'run.log: {figure_log_error!r}'))
    else:
        report.add('figures', passed, detail)
        if not passed and missing:
            report.root_causes.append(dict(
                item='图件未生成完整（生产 figure 阶段报错）',
                evidence=f'present={len(stems)}/{len(FIGURE_STEMS)} stems; '
                         f'missing={missing}; summary.figures={figures!r}; '
                         f'run.log: {figure_log_error!r}'))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--figures-mode', choices=('fail', 'warn', 'skip'),
                        default='fail')
    parser.add_argument('--skip-validator', action='store_true')
    parser.add_argument('--baseline-as-candidate', action='store_true',
                        help='self-test: treat the accepted V2 payload as both '
                             'candidate variants (geometry/C4/metrics smoke test)')
    args = parser.parse_args(argv)
    started = time.perf_counter()
    report = Report()
    ctx = load_context()
    if args.baseline_as_candidate:
        ctx['payloads'] = {
            label: dict(path=AFTER / 'routes_l3d.json',
                        payload=ctx['baseline_payload'],
                        records=ctx['baseline'])
            for label in ('u_only', 'final')}
    # input provenance
    inputs = {}
    for name, path in (('connectivity', CAMPAIGN / 'inputs' / 'connectivity_1024.json'),
                       ('baseline_routes', AFTER / 'routes_l3d.json')):
        inputs[name] = dict(path=str(path), sha256=sha256(path))
    inputs['verifier_script'] = dict(path=str(_THIS), sha256=sha256(_THIS))
    for label, entry in ctx['payloads'].items():
        inputs[f'{label}_payload'] = dict(path=str(entry['path']),
                                          sha256=sha256(entry['path']))
    for name in ('u_layer_assignment.json', 'validation.json', 'summary.json',
                 'comparison_table.json'):
        path = PROD / name
        if path.is_file():
            inputs[name] = dict(path=str(path), sha256=sha256(path))
    report.numbers['inputs'] = inputs
    report.numbers['config'] = dict(radius=R, clearance=CLEAR, board=BOARD,
                                    width=WIDTH, stack=STACK,
                                    target_layer=ENERGY_TARGET)
    # 1) contract + identity
    for label, entry in ctx['payloads'].items():
        check_payload_contract(report, ctx, label, entry['payload'])
        check_identity(report, ctx, label, entry['records'])
    if 'u_only' not in ctx['payloads']:
        report.add('u_only_payload_contract', False, 'routes_1024_u_only.json missing')
    if 'final' not in ctx['payloads']:
        report.add('final_payload_contract', False, 'routes_1024.json missing')
    # 2) per-route geometry
    for label, entry in ctx['payloads'].items():
        check_route_geometry(report, ctx, label, entry['records'])
    # 3) target quartets + C4
    reached_by_label = {}
    for label, entry in ctx['payloads'].items():
        reached, details = check_target_quartets(report, ctx, label,
                                                 entry['records'],
                                                 use_assignment=(label == 'final'))
        reached_by_label[label] = reached
        check_c4_rotations(report, ctx, label, entry['records'], reached)
    # 4) V2 invariance / local reroute
    check_baseline_invariance(report, ctx)
    check_group11_geometry_context(report, ctx)
    # 5) validator + metrics
    computed = {}
    computed['baseline'] = payload_metrics(ctx['baseline'], ctx['target_set'])
    for label, entry in ctx['payloads'].items():
        computed[label] = payload_metrics(entry['records'], ctx['target_set'])
        computed[label]['target_reached'] = len(reached_by_label.get(label, ()))
    expected_pass = {'u_only': True, 'final': True}
    validator_blocks = {}
    if not args.skip_validator:
        validator_blocks['baseline'] = check_validator(
            report, ctx, 'baseline', ctx['baseline_payload'], True)
        for label in ('u_only', 'final'):
            if label not in ctx['payloads']:
                continue
            validator_blocks[label] = check_validator(
                report, ctx, label, ctx['payloads'][label]['payload'],
                expected_pass[label])
    # attach validator stats to metrics for the production comparison
    for label in ('baseline', 'u_only', 'final'):
        block = validator_blocks.get(label)
        if block is not None:
            computed[label]['validation_status'] = block['status']
            computed[label]['min_3d_clearance_mm'] = block['min_3d_clearance_mm']
            computed[label]['min_curvature_radius_mm'] = \
                block['min_curvature_radius_mm']
    if 'final' in computed and 'baseline' in computed:
        computed['final']['baseline_pairs'] = \
            computed['baseline']['unique_crossing_pairs']
        computed['final']['pair_delta'] = \
            computed['final']['unique_crossing_pairs'] - \
            computed['baseline']['unique_crossing_pairs']
    check_metrics(report, ctx, computed)
    check_assignment_artifacts(report, ctx, computed)
    check_validation_artifact(report, ctx)
    check_figures(report, ctx, args.figures_mode)
    # products must not change while the verifier is running (otherwise the
    # report does not describe a single consistent artefact set)
    changed_during_run = [name for name, entry in inputs.items()
                          if Path(entry['path']).is_file()
                          and sha256(entry['path']) != entry['sha256']]
    if changed_during_run:
        report.warn('products changed during verification: '
                    + ', '.join(changed_during_run))
    report.add('products_stable_during_run', not changed_during_run,
               changed_during_run)
    # production mismatch list for min3d / counts from validation.json
    production_validation = ctx.get('validation') or {}
    final_validation = production_validation.get('payload_validation') or {}
    final_block = validator_blocks.get('final') or {}
    for key in ('exploratory_pass', 'geometry_pass'):
        if final_validation.get(key) is not None and \
                bool(final_validation.get(key)) != bool(final_block.get(key)):
            report.mismatch(f'final.validation.{key}',
                            final_validation.get(key), final_block.get(key))
    for key, value in (final_validation.get('counts') or {}).items():
        actual = (final_block.get('counts') or {}).get(key)
        if actual is not None and int(value) != int(actual):
            report.mismatch(f'final.validation.counts.{key}', value, actual)
    # numbers block
    report.numbers['baseline'] = computed.get('baseline')
    report.numbers['u_only'] = computed.get('u_only')
    report.numbers['final'] = computed.get('final')
    report.numbers['target_reached'] = {
        label: dict(reached=len(reached_by_label.get(label, ())),
                    failed=sorted(set(ctx['target_gids']) -
                                  set(reached_by_label.get(label, ()))))
        for label in reached_by_label}
    report.numbers['validator'] = validator_blocks
    if 'final' in computed and 'baseline' in computed:
        report.numbers['pair_reduction'] = dict(
            baseline=computed['baseline']['unique_crossing_pairs'],
            u_only=computed.get('u_only', {}).get('unique_crossing_pairs'),
            final=computed.get('final', {}).get('unique_crossing_pairs'),
            delta_final=computed['final']['unique_crossing_pairs'] -
            computed['baseline']['unique_crossing_pairs'])
    report.numbers['production_mismatches'] = report.production_mismatches
    report.numbers['runtime_seconds'] = round(time.perf_counter() - started, 2)
    report.numbers['verdict'] = ('PASS' if report.passed and
                                 not report.production_mismatches else 'FAIL')
    # write results
    out = Path(args.out)
    json_payload = dict(
        schema='manual_c4_spatial_u_bundle_verification_v1',
        generated=time.strftime('%Y-%m-%dT%H:%M:%S'),
        verifier='independent: own geometry/C4/metrics; frozen '
                 'lift_cross.validate_payload_v4 (v4_root=phase2_2d) for the '
                 'authoritative 3D pass',
        campaign=str(CAMPAIGN),
        verdict=report.numbers['verdict'],
        checks=report.checks,
        numbers=report.numbers,
        root_causes=report.root_causes,
        warnings=report.warnings)
    write_json(out / 'spatial_u_bundle_verification.json', json_payload)
    write_markdown(out / 'spatial_u_bundle_verification.md', json_payload)
    summary = dict(verdict=json_payload['verdict'],
                   checks=dict(passed=sum(1 for check in report.checks
                                          if check['passed']),
                               total=len(report.checks)),
                   target_reached=report.numbers.get('target_reached'),
                   mismatches=len(report.production_mismatches))
    print(json.dumps(summary, ensure_ascii=False))
    return json_payload


def write_markdown(path, payload):
    lines = ['# 空间分组式 U 形线束三维布线：独立验收报告', '',
             f"- 结论：**{payload['verdict']}**",
             f"- 生成时间：{payload['generated']}",
             f"- 验收器：{payload['verifier']}", '']
    checks = payload['checks']
    failed = [check for check in checks if not check['passed']]
    lines.append(f"## 检查项（{len(checks) - len(failed)}/{len(checks)} PASS）")
    lines.append('')
    lines.append('| 检查 | 结果 | 说明 |')
    lines.append('|---|---|---|')
    for check in checks:
        detail = check.get('detail')
        text = ''
        if isinstance(detail, dict):
            text = json.dumps(detail, ensure_ascii=False)[:220]
        elif detail is not None:
            text = str(detail)[:220]
        text = text.replace('|', '/').replace('\n', ' ')
        lines.append(f"| {check['name']} | "
                     f"{'PASS' if check['passed'] else '**FAIL**'} | {text} |")
    numbers = payload.get('numbers') or {}
    lines += ['', '## 关键数字', '', '| 指标 | 基线 V2 | u_only | final |',
              '|---|---:|---:|---:|']
    keys = [('布通', 'routed'), ('唯一交叉对（跨高度去重）', 'unique_crossing_pairs'),
            ('同层 U-U 交叉对', 'same_layer_u_u_crossing_pairs'),
            ('升降次数', 'transitions'), ('三维总长度 mm', 'total_length_mm'),
            ('最小三维净空 mm', 'min_3d_clearance_mm'),
            ('最小曲率半径 mm', 'min_curvature_radius_mm'),
            ('目标四元组达标', 'target_reached')]
    for title, key in keys:
        values = []
        for label in ('baseline', 'u_only', 'final'):
            block = numbers.get(label) or {}
            value = block.get('target_reached', 0) if key == 'target_reached' \
                else block.get(key)
            values.append('—' if value is None else str(value))
        lines.append(f'| {title} | ' + ' | '.join(values) + ' |')
    reached = numbers.get('target_reached') or {}
    lines.append('')
    for label, value in reached.items():
        lines.append(f"- {label} 目标四元组：{value['reached']}/64，失败 "
                     f"{value['failed']}")
    if reached.get('u_only', {}).get('failed'):
        lines.append(f"- u_only 失败组 {reached['u_only']['failed']}：生产 run.log "
                     f"记录 'u_only: group ... FAILED'（final 通过 group 11 的 "
                     f"L3→L5 局部重路由后达到 64/64）")
    validator = numbers.get('validator') or {}
    for label in ('u_only', 'final'):
        block = validator.get(label)
        if block:
            lines.append(f"- {label} 独立三维验收：status={block.get('status')}，"
                         f"exploratory_pass={block.get('exploratory_pass')}，"
                         f"formal_acceptance={block.get('formal_acceptance')}，"
                         f"counts={block.get('counts')}")
    pairs = numbers.get('pair_reduction') or {}
    if pairs:
        lines.append(f"- 唯一交叉对：baseline {pairs.get('baseline')} → "
                     f"u_only {pairs.get('u_only')} → final {pairs.get('final')}"
                     f"（final 相对基线 {pairs.get('delta_final'):+d}）")
    final_layer_counts = (numbers.get('final') or {}).get('layer_counts') or {}
    if final_layer_counts:
        lines.append('- final 各层水平波导数（有该层 flat 的路线数）：'
                     + ', '.join(f'{key}={value}' for key, value in
                                 final_layer_counts.items()))
    mismatches = numbers.get('production_mismatches') or []
    lines += ['', '## 与生产数字的差异', '']
    if mismatches:
        for item in mismatches:
            lines.append(f"- `{item['topic']}`：生产 {item['production']!r} / "
                         f"独立重算 {item['recomputed']!r}")
    else:
        lines.append('- 无（独立重算与 summary/comparison_table 一致）')
    root_causes = payload.get('root_causes') or []
    if root_causes:
        lines += ['', '## 根因/证据', '']
        for item in root_causes:
            lines.append(f"- **{item['item']}**：{item['evidence']}")
    warnings = payload.get('warnings') or []
    if warnings:
        lines += ['', '## 警告', '']
        lines += [f'- {warning}' for warning in warnings]
    lines += ['', '> 说明：层高为探索性仿真参数（unconfirmed_simulation），'
                  '几何 PASS 不等于制造工艺正式验收；本报告为独立重算。']
    Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
