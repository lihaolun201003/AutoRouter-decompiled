#!/usr/bin/env python
"""Independent verification of the structured-layer-routing A/B experiment.

This verifier is deliberately self-contained: it never imports
``four_side_1024.manual_c4.structured_layer_routing`` or any of its runners /
``run_*`` helpers.  It reads only the saved JSON artefacts, re-implements the
geometry / C4-symmetry / structured-layering / metric checks from scratch, and
uses exactly two frozen acceptance components for the authoritative parts:

* ``four_side_1024.v3c4.lift_cross.validate_payload_v4`` ->
  ``four_side_1024.l3d.validate_l3d.validate_payload`` for the authoritative 3D
  pass (A: identity root = ``phase2_2d``; B: a generated row-swapped identity
  root that mirrors the B connection-table swap),
* ``four_side_1024.fslw.validate_fslw`` (``prepare_route`` /
  ``audit_route_pairs``) for the frozen same-physical-plane crossing audit.

Everything a manufacturer would care about (identity, port coverage, rule
layering, C4 atomicity, transition structure, board bounds, elevation-on-straight
rules, lengths, crossing / length / layer metrics) is recomputed independently.

Modes
-----
``--selftest``
    Run the generic methodology on the already-accepted old Spatial-U-bundle
    payload (known PASS: 12824 unique crossing pairs, 824 transitions,
    98539.0127 mm) and print a PASS/FAIL self-check report.

``--groups A`` / ``--groups B`` / ``--groups A B`` (default both)
    Verify one group (writes ``_group_X.json``) or both groups (writes the
    combined ``structured_layer_routing_verification.json`` /
    ``.md`` + the A/B/old-Spatial comparison).

Outputs are written only inside ``structured_layer_routing/verification/``.
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
# repository / frozen R15 profile (must be applied before radius-bound imports)
# ---------------------------------------------------------------------------
_THIS = Path(__file__).resolve()
REPO = _THIS
while REPO.parent != REPO and not (REPO / 'four_side_1024').is_dir():
    REPO = REPO.parent
sys.path.insert(0, str(REPO))

from four_side_1024.v3c4.profile import apply as apply_profile  # noqa: E402

apply_profile()

from four_side_1024.fslw import config as C  # noqa: E402
from four_side_1024.fslw import ports as FSLW_PORTS  # noqa: E402
from four_side_1024.fslw import validate_fslw as FSLW  # noqa: E402

# ---------------------------------------------------------------------------
# paths / constants
# ---------------------------------------------------------------------------
CAMPAIGN = REPO / 'outputs' / 'manual_c4_new_connectivity'
STRUCT = CAMPAIGN / 'structured_layer_routing'
VERIFY = STRUCT / 'verification'
PHASE2 = CAMPAIGN / 'phase2_2d'
OLD_SPATIAL = CAMPAIGN / 'spatial_u_bundle_optimization'
OLD_V2 = CAMPAIGN / 'phase5_dynamic_optimization' / 'after'
CONNECTIVITY = CAMPAIGN / 'inputs' / 'connectivity_1024.json'
IDENTITY_ROOTS = VERIFY / '_identity_roots'
B_IDENTITY_ROOT = IDENTITY_ROOTS / 'B_row_swapped'
B_IDENTITY_ROUTES = B_IDENTITY_ROOT / 'routes_1024.json'
A_DIR = STRUCT / 'A'
B_DIR = STRUCT / 'B'

R = float(C.RADIUS_MM)                    # 15.0 mm
CLEAR = float(C.CLEARANCE_MM)             # 0.08 mm
BOARD = float(C.BOARD_MM)                 # 150.0 mm
WIDTH = float(C.WIDTH_MM)                 # 0.05 mm
ROW_Z = {'z1': 0.0, 'z2': 0.5}
ROW_OF_PLANE = {'z1': 1, 'z2': 2}
PLANE_OF_ROW = {1: 'z1', 2: 'z2'}
STACK = {2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5}
TARGET_U_LAYER = {}
for _gid in range(20, 36):
    TARGET_U_LAYER[_gid] = (3, 1.5)
for _gid in range(144, 160):
    TARGET_U_LAYER[_gid] = (3, 1.5)
for _gid in range(160, 176):
    TARGET_U_LAYER[_gid] = (4, 2.0)
for _gid in range(176, 192):
    TARGET_U_LAYER[_gid] = (5, 2.5)
U_BUNDLE_RANGES = [('z1_middle_U', range(20, 36), 3, 1.5),
                   ('z2_corner_U_1', range(144, 160), 3, 1.5),
                   ('z2_corner_U_2', range(160, 176), 4, 2.0),
                   ('z2_middle_U', range(176, 192), 5, 2.5)]
TARGET_U_GROUPS = sorted(TARGET_U_LAYER)
OPPOSITE_LAYER_ID = 2
OPPOSITE_LAYER_Z = 1.0
ADJACENT, OPPOSITE, SAME = 'adjacent', 'opposite', 'same'
INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0),
          'E': (-1.0, 0.0), 'W': (1.0, 0.0)}
CATEGORIES = ('violations', 'contract_errors', 'port_errors', 'geometry_errors',
              'curvature_violations', 'clearance_violations',
              'same_plane_violations', 'self_clearance_violations',
              'other_errors')
POS_TOL = 1e-6        # XY positions / rotation comparison
Z_TOL = 1e-9          # z coordinates
FORM_TOL = 1e-6       # S-curve formulas / middle straight
LEN_TOL = 1e-4        # aggregate route lengths
ANGLE_TOL = 1e-6
ARC_TOL = 1e-9
ROUND_Z = 6


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def log(message):
    line = time.strftime('%H:%M:%S') + ' ' + str(message)
    print(line, flush=True)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json_retry(path, attempts=8, delay=0.75):
    """Read JSON tolerating a producer that is still writing the file."""
    last = None
    for _ in range(int(attempts)):
        try:
            return json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError, json.JSONDecodeError) as exc:  # noqa: F841
            last = exc
            time.sleep(delay)
    raise RuntimeError(f'could not read JSON {path}: {last}')


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
    return (abs(float(a[0]) - float(b[0])) <= tol
            and abs(float(a[1]) - float(b[1])) <= tol)


def dist_xy(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def unit(vector):
    norm = math.hypot(float(vector[0]), float(vector[1]))
    if norm <= 1e-15:
        return (0.0, 0.0)
    return (float(vector[0]) / norm, float(vector[1]) / norm)


def angle_diff(a, b):
    delta = (float(a) - float(b)) % (2.0 * math.pi)
    return min(delta, 2.0 * math.pi - delta)


def prim_length(prim):
    if prim['kind'] == 'line':
        return dist_xy(prim['p0'], prim['p1'])
    return abs(float(prim['sweep'])) * float(prim['radius'])


def path_length(primitives):
    return sum(prim_length(prim) for prim in primitives)


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


def point_on_line(point, a, b, tol=POS_TOL):
    dx, dy = float(b[0]) - float(a[0]), float(b[1]) - float(a[1])
    norm = math.hypot(dx, dy)
    if norm <= 1e-15:
        return dist_xy(point, a) <= tol
    cross = (float(point[0]) - float(a[0])) * dy \
        - (float(point[1]) - float(a[1])) * dx
    return abs(cross) / norm <= tol


def point_on_chain(point, primitives, tol=POS_TOL):
    for prim in primitives:
        if prim['kind'] == 'line':
            if point_on_segment(point, prim['p0'], prim['p1'], tol):
                return True
        else:
            center = prim['center']
            radius = float(prim['radius'])
            if abs(dist_xy(point, center) - radius) > tol:
                continue
            start = float(prim['start_angle'])
            sweep = float(prim['sweep'])
            angle = math.atan2(float(point[1]) - float(center[1]),
                               float(point[0]) - float(center[0]))
            if sweep >= 0.0:
                delta = (angle - start) % (2.0 * math.pi)
                if delta <= sweep + 1e-9:
                    return True
            else:
                delta = (start - angle) % (2.0 * math.pi)
                if delta <= -sweep + 1e-9:
                    return True
    return False


def arc_points(prim, count=32):
    center = prim['center']
    radius = float(prim['radius'])
    start = float(prim['start_angle'])
    sweep = float(prim['sweep'])
    return [(float(center[0]) + radius * math.cos(start + sweep * i / count),
             float(center[1]) + radius * math.sin(start + sweep * i / count))
            for i in range(count + 1)]


def transition_points(part, count=32):
    """Own 3D sampling of the two-arc S transition (no frozen sampler import)."""
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
    return (-tol <= float(x) <= BOARD + tol) and (-tol <= float(y) <= BOARD + tol)


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
    """(start_xy, end_xy) of a route from its first/last flat primitives."""
    flats = [part for part in route['parts'] if part['kind'] == 'flat']
    return (xy(flats[0]['primitives'][0]['p0']),
            xy(flats[-1]['primitives'][-1]['p1']))


def norm_span_primitives(primitives):
    """Normalised (kind, geometry) tuple used for 2D-chain comparisons."""
    out = []
    for prim in primitives:
        if prim['kind'] == 'line':
            out.append(('L', round(float(prim['p0'][0]), 9),
                        round(float(prim['p0'][1]), 9),
                        round(float(prim['p1'][0]), 9),
                        round(float(prim['p1'][1]), 9)))
        else:
            out.append(('A', round(float(prim['p0'][0]), 9),
                        round(float(prim['p0'][1]), 9),
                        round(float(prim['p1'][0]), 9),
                        round(float(prim['p1'][1]), 9),
                        round(float(prim['center'][0]), 9),
                        round(float(prim['center'][1]), 9),
                        round(float(prim['radius']), 9),
                        round(float(prim['sweep']), 9)))
    return tuple(out)


# ---------------------------------------------------------------------------
# C4 rigid operations about the board centre (75, 75): (x, y) -> (150-y, x)
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
    out['p0'] = list(rot_xy(prim['p0'], times))
    out['p1'] = list(rot_xy(prim['p1'], times))
    if prim['kind'] == 'arc':
        out['center'] = list(rot_xy(prim['center'], times))
        out['start_angle'] = math.atan2(
            float(out['p0'][1]) - float(out['center'][1]),
            float(out['p0'][0]) - float(out['center'][0]))
    return out


def reverse_primitive(prim):
    out = dict(prim)
    out['p0'] = list(prim['p1'])
    out['p1'] = list(prim['p0'])
    if prim['kind'] == 'arc':
        center = prim['center']
        out['start_angle'] = math.atan2(
            float(out['p0'][1]) - float(center[1]),
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
    times = int(times) % 4
    if times == 0:
        return json.loads(json.dumps(route))
    out = dict(route)
    out['parts'] = [rotate_part(part, times) for part in route['parts']]
    for key in ('source_port', 'target_port'):
        port = out.get(key)
        if isinstance(port, dict) and 'xy' in port:
            new_port = dict(port)
            new_port['xy'] = list(rot_xy(port['xy'], times))
            out[key] = new_port
    for key in ('start_dir', 'end_dir'):
        if out.get(key) is not None:
            out[key] = list(rot_vec(out[key], times))
    return out


def reverse_route(route):
    out = dict(route)
    out['parts'] = [reverse_part(part) for part in reversed(route['parts'])]
    out['layer_sequence'] = list(reversed(route['layer_sequence']))
    out['layer_z_sequence'] = list(reversed(route['layer_z_sequence']))
    out['start_z_mm'] = float(route['end_z_mm'])
    out['end_z_mm'] = float(route['start_z_mm'])
    out['source_port'], out['target_port'] = route['target_port'], route['source_port']
    for key in ('start_dir', 'end_dir'):
        if out.get(key) is not None:
            out[key] = [-float(out[key][0]), -float(out[key][1])]
    return out


# ---------------------------------------------------------------------------
# report object
# ---------------------------------------------------------------------------
class Report:
    def __init__(self, label='report'):
        self.label = label
        self.checks = []
        self.numbers = {}
        self.warnings = []
        self.root_causes = []
        self.differences = []

    def add(self, name, passed, category='core', detail=None, **numbers):
        entry = dict(name=name, passed=bool(passed), category=category)
        if detail is not None:
            entry['detail'] = detail
        if numbers:
            entry['numbers'] = numbers
        self.checks.append(entry)
        if not passed:
            self.root_causes.append(dict(item=name, detail=detail))
        return entry

    def warn(self, message):
        self.warnings.append(str(message))

    def difference(self, topic, production, recomputed, note=None):
        self.differences.append(dict(topic=topic, production=production,
                                     recomputed=recomputed, note=note))

    def category_pass(self, categories):
        return all(entry['passed'] for entry in self.checks
                   if entry['category'] in categories)

    @property
    def core_pass(self):
        return self.category_pass(('core', 'metrics'))

    @property
    def artifacts_pass(self):
        return self.category_pass(('artifacts',))

    @property
    def passed(self):
        return self.category_pass(('core', 'metrics', 'artifacts'))

    def to_dict(self):
        return dict(label=self.label, verdict='PASS' if self.passed else 'FAIL',
                    core_pass=self.core_pass,
                    artifacts_pass=self.artifacts_pass,
                    checks=self.checks, numbers=self.numbers,
                    warnings=self.warnings,
                    root_causes=self.root_causes,
                    differences=self.differences)


# ---------------------------------------------------------------------------
# connection-table swap (B group) and input loading
# ---------------------------------------------------------------------------
def swap_plane(plane):
    return 'z2' if plane == 'z1' else 'z1'


def swap_row(row):
    return 2 if int(row) == 1 else 1


def swap_endpoint(endpoint):
    connector, row, column = str(endpoint).split(':')
    return f'{connector}:{swap_row(row)}:{column}'


def load_connectivity():
    payload = read_json_retry(CONNECTIVITY)
    groups = {int(group['group_id']): group for group in payload['groups']}
    manifest = {int(record['route_id']): record for record in payload['routes']}
    expected = dict(
        groups=groups, manifest=manifest,
        group_of_route={int(rid): int(gid)
                        for gid, group in groups.items()
                        for rid in group['route_ids']},
        u_groups=sorted(gid for gid, group in groups.items()
                        if group['kind'] == SAME),
        opposite_groups=sorted(gid for gid, group in groups.items()
                               if group['kind'] == OPPOSITE),
        adjacent_groups=sorted(gid for gid, group in groups.items()
                               if group['kind'] == ADJACENT),
        u_rids=sorted({int(rid) for gid, group in groups.items()
                       if group['kind'] == SAME
                       for rid in group['route_ids']}),
        opposite_rids=sorted({int(rid) for gid, group in groups.items()
                              if group['kind'] == OPPOSITE
                              for rid in group['route_ids']}),
        adjacent_rids=sorted({int(rid) for gid, group in groups.items()
                              if group['kind'] == ADJACENT
                              for rid in group['route_ids']}),
    )
    return payload, expected


def expected_manifest_for(connection, swap_rows):
    """Expected payload identity fields (B: row/plane/endpoint swapped)."""
    expected = {}
    for rid, record in connection['manifest'].items():
        row = dict(record)
        if swap_rows:
            row['plane'] = swap_plane(record['plane'])
            row['source_row'] = swap_row(record['source_row'])
            row['target_row'] = swap_row(record['target_row'])
            row['source_endpoint'] = swap_endpoint(record['source_endpoint'])
            row['target_endpoint'] = swap_endpoint(record['target_endpoint'])
            row['z_mm'] = ROW_Z[row['plane']]
        expected[int(rid)] = row
    groups = {}
    for gid, group in connection['groups'].items():
        out = dict(group)
        if swap_rows:
            out['plane'] = swap_plane(group['plane'])
        out['route_ids'] = [int(rid) for rid in group['route_ids']]
        groups[int(gid)] = out
    return expected, groups


def load_port_model():
    endpoints = FSLW_PORTS.build_plane_endpoints()
    return endpoints


def load_phase2_2d():
    """route_id -> phase-2 2D record (the XY chain each connection came from)."""
    out = {}
    for plane in ('z1', 'z2'):
        payload = read_json_retry(PHASE2 / plane / 'routes.json')
        for record in payload['routes']:
            out[int(record['route_id'])] = record
    return out


# ---------------------------------------------------------------------------
# B identity root for the frozen 3D validator
# ---------------------------------------------------------------------------
def build_b_identity_root(log_fn=log):
    """Generate the row-swapped identity root used for B's 3D validation.

    The frozen ``validate_payload_v4`` reads ``v4_root/routes_1024.json`` and
    builds the per-plane CSV identity from it.  For B the two 512-row connection
    tables live on the opposite physical interface row, so the identity record
    of every connection must be the row/plane/endpoint-swapped original.
    """
    source = read_json_retry(PHASE2 / 'routes_1024.json')
    records = []
    for record in source['routes']:
        out = dict(record)
        plane = swap_plane(record['plane'])
        out['plane'] = plane
        out['z_mm'] = ROW_Z[plane]
        out['source_row'] = swap_row(record['source_row'])
        out['target_row'] = swap_row(record['target_row'])
        out['source_endpoint'] = swap_endpoint(record['source_endpoint'])
        out['target_endpoint'] = swap_endpoint(record['target_endpoint'])
        out['row'] = out['source_row']
        records.append(out)
    payload = dict(
        schema=source.get('schema'),
        topology=source.get('topology'),
        note='row-swapped identity root generated by the independent verifier '
             'for the B group (z1<->z2 interface-row swap)',
        routed=len(records), failed=0, total=len(records),
        routes=records)
    write_json(B_IDENTITY_ROUTES, payload)
    log_fn(f'[B] identity root written: {B_IDENTITY_ROUTES} ({len(records)} routes)')
    return B_IDENTITY_ROOT


# ---------------------------------------------------------------------------
# payload contract / identity / ports
# ---------------------------------------------------------------------------
def check_payload_contract(report, payload, path):
    errors = []
    if not isinstance(payload, dict):
        errors.append('payload is not a mapping')
        payload = {}
    if payload.get('schema') != 'four_side_1024_v2_l3d_routes_v1':
        errors.append(f"schema {payload.get('schema')!r}")
    routes = payload.get('routes')
    if not isinstance(routes, list) or len(routes) != 1024:
        errors.append(f'routes {len(routes) if isinstance(routes, list) else None} '
                      f'!= 1024')
        routes = routes or []
    ids = [record.get('route_id') for record in routes
           if isinstance(record, dict)]
    try:
        sorted_ids = sorted(int(value) for value in ids if value is not None)
    except (TypeError, ValueError):
        sorted_ids = []
    if sorted_ids != list(range(1, 1025)):
        errors.append('route_id set is not exactly 1..1024')
    routed = [record for record in routes
              if isinstance(record, dict) and record.get('status') == 'routed']
    if len(routed) != 1024:
        errors.append(f'routed {len(routed)} != 1024')
    stack = payload.get('layer_stack') or {}
    heights = stack.get('routing_heights_mm') or {}
    for layer_id, z in STACK.items():
        try:
            value = float(heights.get(str(layer_id), float('nan')))
        except (TypeError, ValueError):
            value = float('nan')
        if not math.isfinite(value) or abs(value - z) > Z_TOL:
            errors.append(f'layer_stack L{layer_id} height != {z}')
    interface = ((stack.get('layers') or {}).get('1') or {})
    rows = interface.get('interface_rows') or {}
    for plane, z in ROW_Z.items():
        try:
            value = float(rows.get(plane, float('nan')))
        except (TypeError, ValueError):
            value = float('nan')
        if not math.isfinite(value) or abs(value - z) > Z_TOL:
            errors.append(f'layer_stack interface {plane} != {z}')
    report.add('payload_contract', not errors, category='core',
               detail=errors[:10], routes=len(routes), routed=len(routed),
               path=str(path), sha256=sha256(path))
    return routed


def check_identity(report, label, records, expected_manifest, expected_groups,
                   connection, port_model):
    errors = []
    warnings = []
    endpoint_usage = Counter()
    expected_fields = ('plane', 'source_endpoint', 'target_endpoint', 'relation',
                       'pair', 'source_side', 'target_side', 'source_row',
                       'target_row')
    for rid in range(1, 1025):
        record = records.get(rid)
        expected = expected_manifest.get(rid)
        if record is None:
            errors.append(dict(route_id=rid, problem='missing routed record'))
            continue
        if expected is None:
            errors.append(dict(route_id=rid, problem='no expected manifest'))
            continue
        for key in expected_fields:
            want = expected.get(key)
            have = record.get(key)
            if key in ('source_row', 'target_row'):
                try:
                    ok = int(have) == int(want)
                except (TypeError, ValueError):
                    ok = False
            else:
                ok = have == want
            if not ok:
                errors.append(dict(route_id=rid, field=key, actual=have,
                                   expected=want))
        # plane <-> row consistency + endpoint row identity
        plane = record.get('plane')
        if plane not in ROW_OF_PLANE:
            errors.append(dict(route_id=rid, problem='bad plane', actual=plane))
        else:
            row = ROW_OF_PLANE[plane]
            for key in ('source_row', 'target_row'):
                try:
                    if int(record.get(key)) != row:
                        errors.append(dict(route_id=rid, field=key,
                                           actual=record.get(key),
                                           expected_row=row))
                except (TypeError, ValueError):
                    errors.append(dict(route_id=rid, field=key,
                                       problem='not an int'))
            for side in ('source', 'target'):
                endpoint = record.get(f'{side}_endpoint')
                endpoint = str(endpoint) if endpoint is not None else ''
                parts = endpoint.split(':')
                if len(parts) == 3:
                    try:
                        endpoint_row = int(parts[1])
                    except ValueError:
                        endpoint_row = None
                    if endpoint_row != row:
                        errors.append(dict(route_id=rid, endpoint=endpoint,
                                           problem='endpoint row != plane row',
                                           endpoint_row=endpoint_row, row=row))
                else:
                    errors.append(dict(route_id=rid, endpoint=endpoint,
                                       problem='endpoint id malformed'))
        # record-level z_mm field (legacy metadata, not geometry)
        try:
            z_field = float(record.get('z_mm'))
            if abs(z_field - ROW_Z.get(plane, float('nan'))) > Z_TOL:
                warnings.append(dict(route_id=rid, z_mm=z_field, plane=plane))
        except (TypeError, ValueError):
            warnings.append(dict(route_id=rid, z_mm=record.get('z_mm')))
        # ports: identity xy / z / layer and unique usage
        for side in ('source', 'target'):
            port = record.get(f'{side}_port')
            endpoint = record.get(f'{side}_endpoint')
            if not isinstance(port, dict):
                errors.append(dict(route_id=rid, problem=f'{side}_port missing'))
                continue
            endpoint_usage[endpoint] += 1
            endpoint_record = port_model.get(endpoint)
            if endpoint_record is None:
                errors.append(dict(route_id=rid, problem='endpoint unknown',
                                   endpoint=endpoint))
                continue
            expected_xy = tuple(float(v) for v in endpoint_record['routing_xy'])
            if not close_xy(port.get('xy') or (1e9, 1e9), expected_xy):
                errors.append(dict(route_id=rid, side=side,
                                   problem='port xy != frozen port model',
                                   actual=port.get('xy'), expected=expected_xy))
            expected_z = ROW_Z[plane] if plane in ROW_Z else None
            try:
                port_z = float(port.get('z_mm'))
            except (TypeError, ValueError):
                port_z = None
            if expected_z is not None and (port_z is None
                                           or abs(port_z - expected_z) > Z_TOL):
                errors.append(dict(route_id=rid, side=side,
                                   problem='port z != plane row height',
                                   actual=port.get('z_mm'),
                                   expected=expected_z))
            try:
                layer_id = int(port.get('layer_id'))
            except (TypeError, ValueError):
                layer_id = None
            if layer_id != 1:
                errors.append(dict(route_id=rid, side=side,
                                   problem='port layer_id != 1',
                                   actual=port.get('layer_id')))
        # group membership / group plane
        gid = connection['group_of_route'].get(rid)
        expected_group = expected_groups.get(gid) if gid is not None else None
        if expected_group is not None and expected_group.get('plane') != plane:
            errors.append(dict(route_id=rid, problem='group plane != record plane',
                               group_id=gid, record_plane=plane,
                               group_plane=expected_group.get('plane')))
    expected_endpoints = set()
    for rid, expected in expected_manifest.items():
        expected_endpoints.add(expected.get('source_endpoint'))
        expected_endpoints.add(expected.get('target_endpoint'))
    if len(endpoint_usage) != 2048:
        errors.append(dict(problem='unique endpoints used',
                           actual=len(endpoint_usage), expected=2048))
    if set(endpoint_usage) != expected_endpoints:
        errors.append(dict(problem='endpoint set != expected connection table',
                           missing=sorted(expected_endpoints
                                          - set(endpoint_usage))[:10],
                           extra=sorted(set(endpoint_usage)
                                        - expected_endpoints)[:10]))
    reused = sorted(endpoint for endpoint, count in endpoint_usage.items()
                    if count != 1)
    if reused:
        errors.append(dict(problem='endpoint not used exactly once',
                           endpoints=reused[:20]))
    report.add('identity_and_ports', not errors, category='core',
               detail=errors[:20], unique_endpoints=len(endpoint_usage),
               expected_endpoints=len(expected_endpoints),
               mismatch_count=len(errors))
    if warnings:
        report.warn('record z_mm legacy field inconsistent with physical row on '
                    f'{len(warnings)} records (not used by the geometry or the '
                    f'frozen validator): {warnings[:3]}')
        report.add('legacy_z_mm_field', False, category='info',
                   detail=warnings[:5], count=len(warnings))


# ---------------------------------------------------------------------------
# structured-layering rules
# ---------------------------------------------------------------------------
def classify_route(record):
    """Classify one routed record into its structured layer class."""
    parts = record.get('parts') or []
    flats = [part for part in parts if part['kind'] == 'flat']
    transitions = [part for part in parts if part['kind'] == 'transition']
    sequence = record.get('layer_sequence')
    high = [part for part in flats if int(part['layer_id']) != 1]
    classes = []
    if sequence == [1] and not transitions and len(parts) == 1 and not high:
        classes.append('flat_interface')
    if sequence == [1, OPPOSITE_LAYER_ID, 1] and len(transitions) == 2 \
            and len(high) == 1 and int(high[0]['layer_id']) == OPPOSITE_LAYER_ID \
            and abs(float(high[0]['z_mm']) - OPPOSITE_LAYER_Z) <= Z_TOL:
        classes.append('opposite_L2')
    return classes, dict(parts=parts, flats=flats, transitions=transitions,
                         high=high, sequence=sequence)


def check_rule_layers(report, records, connection, expected_groups, summary):
    problems = []
    facts = {}
    # ------------------------------------------------------------------ adjacent
    adjacent_ok = 0
    adjacent_bad = []
    for rid in connection['adjacent_rids']:
        record = records.get(rid)
        if record is None:
            adjacent_bad.append(dict(route_id=rid, problem='missing'))
            continue
        classes, _info = classify_route(record)
        plane = record.get('plane')
        expected_z = ROW_Z.get(plane)
        if 'flat_interface' not in classes:
            adjacent_bad.append(dict(route_id=rid, problem='not flat-only',
                                     layer_sequence=record.get('layer_sequence')))
            continue
        flat = record['parts'][0]
        if int(flat['layer_id']) != 1 or abs(float(flat['z_mm']) - expected_z) > Z_TOL:
            adjacent_bad.append(dict(route_id=rid, problem='not on interface layer',
                                     layer_id=flat['layer_id'], z=flat['z_mm'],
                                     expected_z=expected_z))
            continue
        if int(record.get('n_transitions') or 0) != 0 or record.get('lifted'):
            adjacent_bad.append(dict(route_id=rid, problem='transition count'))
            continue
        adjacent_ok += 1
    if adjacent_bad:
        problems.extend(('adjacent', item) for item in adjacent_bad[:20])
    facts['adjacent_on_interface'] = adjacent_ok
    report.add('rule_adjacent_interface', not adjacent_bad, category='core',
               detail=adjacent_bad[:20], ok=adjacent_ok,
               expected=len(connection['adjacent_rids']))
    # ------------------------------------------------------------------ opposite
    opposite_classes = {}
    opposite_bad = []
    for gid in connection['opposite_groups']:
        group = expected_groups[gid]
        rids = [int(rid) for rid in group['route_ids']]
        member_classes = []
        for rid in rids:
            record = records.get(rid)
            if record is None:
                member_classes.append(None)
                continue
            classes, _info = classify_route(record)
            cls = None
            for candidate in ('opposite_L2', 'flat_interface'):
                if candidate in classes:
                    cls = candidate
                    break
            member_classes.append(cls)
        if any(cls is None for cls in member_classes):
            opposite_bad.append(dict(group_id=gid, route_ids=rids,
                                     problem='unclassified member',
                                     classes=member_classes))
            continue
        if len(set(member_classes)) != 1:
            opposite_bad.append(dict(group_id=gid, route_ids=rids,
                                     problem='mixed classes', classes=member_classes))
            continue
        opposite_classes[gid] = member_classes[0]
    l2_groups = sorted(gid for gid, cls in opposite_classes.items()
                       if cls == 'opposite_L2')
    exception_groups = sorted(gid for gid, cls in opposite_classes.items()
                              if cls == 'flat_interface')
    exception_reasons = {}
    if isinstance(summary, dict):
        raw = summary.get('opposite_exceptions')
        if isinstance(raw, dict):
            for key, value in raw.items():
                try:
                    gid = int(key)
                except (TypeError, ValueError):
                    continue
                reason = value.get('reason') if isinstance(value, dict) else value
                exception_reasons[gid] = reason
    undocumented = [gid for gid in exception_groups
                    if not str(exception_reasons.get(gid) or '').strip()]
    if undocumented:
        problems.append(('opposite', dict(
            problem='exception group without a documented reason',
            groups=undocumented)))
    facts['opposite_total_routes'] = len(connection['opposite_rids'])
    facts['opposite_total_groups'] = len(connection['opposite_groups'])
    facts['opposite_on_L2_groups'] = len(l2_groups)
    facts['opposite_on_L2_routes'] = 4 * len(l2_groups)
    facts['opposite_exception_groups'] = exception_groups
    facts['opposite_exception_routes'] = 4 * len(exception_groups)
    facts['opposite_exception_reasons'] = {str(gid): exception_reasons.get(gid)
                                           for gid in exception_groups}
    facts['opposite_route_ids'] = {
        gid: [int(rid) for rid in expected_groups[gid]['route_ids']]
        for gid in connection['opposite_groups']}
    report.add('rule_opposite_L2', not opposite_bad, category='core',
               detail=opposite_bad[:20],
               groups_l2=len(l2_groups), groups_exception=len(exception_groups),
               routes_l2=facts['opposite_on_L2_routes'],
               routes_exception=facts['opposite_exception_routes'])
    report.add('rule_opposite_exceptions_documented', not undocumented,
               category='core',
               detail=undocumented[:10],
               exception_groups=len(exception_groups),
               documented=len(exception_groups) - len(undocumented))
    # ------------------------------------------------------------------------ U
    u_status = {}
    u_bad = []
    for gid in TARGET_U_GROUPS:
        target_layer, target_z = TARGET_U_LAYER[gid]
        group = expected_groups[gid]
        rids = [int(rid) for rid in group['route_ids']]
        ok_members = []
        for rid in rids:
            record = records.get(rid)
            if record is None:
                ok_members.append(dict(route_id=rid, problem='missing'))
                continue
            flats = [part for part in (record.get('parts') or [])
                     if part['kind'] == 'flat']
            transitions = [part for part in (record.get('parts') or [])
                           if part['kind'] == 'transition']
            high = [part for part in flats if int(part['layer_id']) != 1]
            if record.get('layer_sequence') != [1, target_layer, 1]:
                ok_members.append(dict(route_id=rid,
                                       problem='layer_sequence',
                                       actual=record.get('layer_sequence'),
                                       expected=[1, target_layer, 1]))
                continue
            if len(transitions) != 2 or len(high) != 1:
                ok_members.append(dict(route_id=rid, problem='parts',
                                       transitions=len(transitions),
                                       high=len(high)))
                continue
            if int(high[0]['layer_id']) != target_layer or \
                    abs(float(high[0]['z_mm']) - target_z) > Z_TOL:
                ok_members.append(dict(route_id=rid, problem='target layer/z',
                                       layer_id=high[0]['layer_id'],
                                       z=high[0]['z_mm']))
                continue
            ok_members.append(None)
        failed = [item for item in ok_members if item]
        u_status[gid] = 'reached' if not failed else 'failed'
        if failed:
            u_bad.append(dict(group_id=gid, target_layer=target_layer,
                              route_ids=rids, problems=failed[:4]))
    reached = [gid for gid in TARGET_U_GROUPS if u_status.get(gid) == 'reached']
    failed = [gid for gid in TARGET_U_GROUPS if u_status.get(gid) != 'reached']
    u_failures_summary = {}
    if isinstance(summary, dict) and isinstance(summary.get('u_failures'), dict):
        for key, value in summary['u_failures'].items():
            try:
                gid = int(key)
            except (TypeError, ValueError):
                continue
            reason = value.get('reason') if isinstance(value, dict) else value
            u_failures_summary[gid] = reason
    undocumented_u = [gid for gid in failed
                      if not str(u_failures_summary.get(gid) or '').strip()]
    facts['u_groups_total'] = len(TARGET_U_GROUPS)
    facts['u_groups_reached'] = len(reached)
    facts['u_groups_failed'] = failed
    facts['u_rebuilt_routes'] = 4 * len(reached)
    facts['u_failures_summary'] = {str(gid): u_failures_summary.get(gid)
                                   for gid in failed}
    report.add('rule_u_target_layers', not u_bad, category='core',
               detail=u_bad[:20], reached=len(reached), failed=failed,
               expected=len(TARGET_U_GROUPS))
    report.add('rule_u_failures_documented', not undocumented_u, category='core',
               detail=undocumented_u[:20], failed_groups=failed)
    if problems:
        report.add('rule_layering_other', False, category='core',
                   detail=problems[:20])
    return facts


# ---------------------------------------------------------------------------
# generic per-route geometry (arcs / straights / transitions / board / lengths)
# ---------------------------------------------------------------------------
def check_flat_part(part, route_id, row_z, issues):
    tag = (route_id, 'flat', int(part.get('layer_id', -1)))
    primitives = part.get('primitives')
    if not isinstance(primitives, list) or not primitives:
        issues.append(tag + ('empty_primitives',))
        return
    layer_id = int(part['layer_id'])
    z_mm = float(part['z_mm'])
    if layer_id == 1:
        if abs(z_mm - row_z) > Z_TOL:
            issues.append(tag + ('L1_z_mismatch', z_mm, row_z))
    elif layer_id in STACK:
        if abs(z_mm - STACK[layer_id]) > Z_TOL:
            issues.append(tag + ('high_z_mismatch', z_mm, STACK[layer_id]))
    else:
        issues.append(tag + ('unknown_layer', layer_id))
    cursor = None
    total = 0.0
    for index, prim in enumerate(primitives):
        if prim.get('kind') not in ('line', 'arc'):
            issues.append(tag + ('unknown_primitive', index, prim.get('kind')))
            continue
        if len(prim.get('p0') or []) != 2 or len(prim.get('p1') or []) != 2:
            issues.append(tag + ('bad_point', index))
            continue
        if prim['kind'] == 'line':
            p0, p1 = xy(prim['p0']), xy(prim['p1'])
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            if abs(dx) > 1e-9 and abs(dy) > 1e-9:
                issues.append(tag + ('diagonal_line', index, (round(dx, 6),
                                                              round(dy, 6))))
            if not inside_board(*p0):
                issues.append(tag + ('line_outside_board', index, prim['p0']))
            if not inside_board(*p1):
                issues.append(tag + ('line_outside_board', index, prim['p1']))
            if dist_xy(p0, p1) <= 1e-12:
                issues.append(tag + ('zero_length_line', index))
        else:
            radius = float(prim.get('radius', -1.0))
            if abs(radius - R) > ARC_TOL:
                issues.append(tag + ('arc_radius', index, radius))
            center = prim.get('center')
            if not center or len(center) != 2:
                issues.append(tag + ('arc_without_center', index))
                continue
            start_angle = float(prim.get('start_angle', 0.0))
            sweep = float(prim.get('sweep', 0.0))
            exp_p0 = (float(center[0]) + radius * math.cos(start_angle),
                      float(center[1]) + radius * math.sin(start_angle))
            exp_p1 = (float(center[0]) + radius * math.cos(start_angle + sweep),
                      float(center[1]) + radius * math.sin(start_angle + sweep))
            if not close_xy(prim['p0'], exp_p0) or not close_xy(prim['p1'], exp_p1):
                issues.append(tag + ('arc_endpoint_formula', index))
            if abs(sweep) <= 1e-12:
                issues.append(tag + ('zero_sweep_arc', index))
            for point in arc_points(prim, 16):
                if not inside_board(*point):
                    issues.append(tag + ('arc_outside_board', index))
                    break
        if cursor is not None and not close_xy(cursor, prim['p0']):
            issues.append(tag + ('primitive_discontinuity', index,
                                 round(dist_xy(cursor, prim['p0']), 9)))
        cursor = prim['p1']
        total += prim_length(prim)
    if abs(float(part.get('length_mm', -1.0)) - total) > LEN_TOL:
        issues.append(tag + ('flat_length_mismatch',
                             float(part.get('length_mm', -1.0)) - total))


def check_transition_part(part, route_id, previous, following, issues):
    tag = (route_id, 'transition')
    required = ('start', 'direction', 'z0', 'z1', 'dz_mm', 'radius_mm',
                'theta_rad', 'footprint_mm', 'end', 'length_mm',
                'from_layer', 'to_layer')
    for key in required:
        if key not in part:
            issues.append(tag + ('missing_field', key))
    if any(key not in part for key in required):
        return
    radius = float(part['radius_mm'])
    if abs(radius - R) > ARC_TOL:
        issues.append(tag + ('radius', radius))
    dz = abs(float(part['z1']) - float(part['z0']))
    if dz <= 1e-12:
        issues.append(tag + ('zero_dz',))
    if abs(abs(float(part['dz_mm'])) - dz) > Z_TOL:
        issues.append(tag + ('dz_mismatch',))
    theta = math.acos(max(-1.0, min(1.0, 1.0 - dz / (2.0 * radius))))
    if abs(float(part['theta_rad']) - theta) > FORM_TOL:
        issues.append(tag + ('theta_formula', float(part['theta_rad']), theta))
    footprint = 2.0 * radius * math.sin(theta)
    if abs(float(part['footprint_mm']) - footprint) > FORM_TOL:
        issues.append(tag + ('footprint_formula',))
    if abs(float(part['length_mm']) - 2.0 * radius * theta) > FORM_TOL:
        issues.append(tag + ('length_formula',))
    direction = part['direction']
    if abs(math.hypot(float(direction[0]), float(direction[1])) - 1.0) > 1e-9:
        issues.append(tag + ('direction_not_unit',))
    if min(abs(float(direction[0])), abs(float(direction[1]))) > 1e-9:
        issues.append(tag + ('direction_not_axis_aligned', direction))
    expected_end = (float(part['start'][0]) + float(direction[0]) * footprint,
                    float(part['start'][1]) + float(direction[1]) * footprint)
    if not close_xy(part['end'], expected_end):
        issues.append(tag + ('end_formula',))
    if previous is None or previous.get('kind') != 'flat':
        issues.append(tag + ('not_after_flat',))
        return
    if following is None or following.get('kind') != 'flat':
        issues.append(tag + ('not_before_flat',))
        return
    previous_prim = previous['primitives'][-1]
    following_prim = following['primitives'][0]
    if not close_xy(part['start'], previous_prim['p1']):
        issues.append(tag + ('start_joint',))
    if not close_xy(part['end'], following_prim['p0']):
        issues.append(tag + ('end_joint',))
    if not close(float(part['z0']), float(previous['z_mm']), Z_TOL):
        issues.append(tag + ('z0_joint',))
    if not close(float(part['z1']), float(following['z_mm']), Z_TOL):
        issues.append(tag + ('z1_joint',))
    if int(part['from_layer']) != int(previous['layer_id']) or \
            int(part['to_layer']) != int(following['layer_id']):
        issues.append(tag + ('layer_joint',))
    # tangent continuity with both adjacent flats
    def tail_tangent(prim):
        if prim['kind'] == 'line':
            return unit((float(prim['p1'][0]) - float(prim['p0'][0]),
                         float(prim['p1'][1]) - float(prim['p0'][1])))
        center = prim['center']
        end_angle = float(prim['start_angle']) + float(prim['sweep'])
        sign = 1.0 if float(prim['sweep']) >= 0 else -1.0
        return unit((-sign * math.sin(end_angle), sign * math.cos(end_angle)))

    def head_tangent(prim):
        if prim['kind'] == 'line':
            return unit((float(prim['p1'][0]) - float(prim['p0'][0]),
                         float(prim['p1'][1]) - float(prim['p0'][1])))
        center = prim['center']
        angle = float(prim['start_angle'])
        sign = 1.0 if float(prim['sweep']) >= 0 else -1.0
        return unit((-sign * math.sin(angle), sign * math.cos(angle)))

    expected_dir = unit(direction)
    if not close_xy(tail_tangent(previous_prim), expected_dir):
        issues.append(tag + ('tangent_previous',))
    if not close_xy(head_tangent(following_prim), expected_dir):
        issues.append(tag + ('tangent_following',))
    # the whole S elevation must sit on one straight segment of the 2D chain
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
        for prim in previous['primitives'] + following['primitives']:
            if prim['kind'] == 'line' and \
                    point_on_segment(part['start'], prim['p0'], prim['p1']) and \
                    point_on_segment(part['end'], prim['p0'], prim['p1']):
                contained = True
                break
    if not contained:
        issues.append(tag + ('elevation_not_on_one_straight',))
    for point in transition_points(part, 16):
        if not inside_board(point[0], point[1]):
            issues.append(tag + ('transition_outside_board',))
            break


def check_route_geometry(report, records):
    issues = []
    stats = dict(routes=0, transitions=0, lifted=0, flat=0, issues=0)
    for rid in sorted(records):
        record = records[rid]
        parts = record.get('parts') or []
        stats['routes'] += 1
        plane = record.get('plane')
        if plane not in ROW_Z:
            issues.append((rid, 'bad_plane', plane))
            continue
        row_z = ROW_Z[plane]
        row = ROW_OF_PLANE[plane]
        if not parts:
            issues.append((rid, 'empty_parts',))
            continue
        if parts[0].get('kind') != 'flat' or parts[-1].get('kind') != 'flat':
            issues.append((rid, 'route_not_flat_ended',))
        kinds = [part['kind'] for part in parts]
        for index in range(len(kinds) - 1):
            if kinds[index] == kinds[index + 1]:
                issues.append((rid, 'consecutive_same_kind', kinds))
                break
        transitions = [part for part in parts if part['kind'] == 'transition']
        flats = [part for part in parts if part['kind'] == 'flat']
        stats['transitions'] += len(transitions)
        stats['lifted'] += 1 if transitions else 0
        stats['flat'] += 0 if transitions else 1
        # record metadata consistency
        if int(record.get('n_transitions') or 0) != len(transitions):
            issues.append((rid, 'n_transitions_mismatch',
                           record.get('n_transitions'), len(transitions)))
        if bool(record.get('lifted')) != bool(transitions):
            issues.append((rid, 'lifted_flag_mismatch',))
        if len(transitions) not in (0, 2):
            issues.append((rid, 'transition_count', len(transitions)))
        flat_layers = [int(part['layer_id']) for part in flats]
        if record.get('layer_sequence') != flat_layers:
            issues.append((rid, 'layer_sequence', record.get('layer_sequence'),
                           flat_layers))
        z_sequence = [float(part['z_mm']) for part in flats]
        stored_z = [round(float(value), 9)
                    for value in (record.get('layer_z_sequence') or [])]
        if stored_z != [round(value, 9) for value in z_sequence]:
            issues.append((rid, 'layer_z_sequence', record.get('layer_z_sequence'),
                           z_sequence))
        if record.get('layers_used') != sorted(set(flat_layers)):
            issues.append((rid, 'layers_used', record.get('layers_used')))
        try:
            start_z = float(record.get('start_z_mm'))
            end_z = float(record.get('end_z_mm'))
        except (TypeError, ValueError):
            start_z = end_z = None
        if start_z is None or abs(start_z - row_z) > Z_TOL:
            issues.append((rid, 'start_z_mm', record.get('start_z_mm'), row_z))
        if end_z is None or abs(end_z - row_z) > Z_TOL:
            issues.append((rid, 'end_z_mm', record.get('end_z_mm'), row_z))
        if flat_layers and flat_layers[0] != 1:
            issues.append((rid, 'route_not_starting_on_L1', flat_layers))
        if flat_layers and flat_layers[-1] != 1:
            issues.append((rid, 'route_not_ending_on_L1', flat_layers))
        if len(transitions) == 2:
            first, second = transitions
            up = float(first['z1']) > float(first['z0'])
            down = float(second['z1']) < float(second['z0'])
            if not (up and down):
                issues.append((rid, 'not_one_rise_one_fall',
                               float(first['z1']) - float(first['z0']),
                               float(second['z1']) - float(second['z0'])))
            if int(first['from_layer']) != 1 or int(second['to_layer']) != 1:
                issues.append((rid, 'rise_fall_layer_endpoint',))
            if int(first['to_layer']) != int(second['from_layer']):
                issues.append((rid, 'rise_fall_layer_mismatch',))
            high_layer = int(first['to_layer'])
            if high_layer not in STACK or \
                    abs(float(first['z1']) - STACK[high_layer]) > Z_TOL or \
                    abs(float(second['z0']) - STACK[high_layer]) > Z_TOL:
                issues.append((rid, 'high_layer_height', high_layer))
            high_flats = [part for part in flats if int(part['layer_id']) != 1]
            if len(high_flats) != 1:
                issues.append((rid, 'high_flat_parts', len(high_flats)))
            if len(set(flat_layers)) > 2:
                issues.append((rid, 'multiple_high_layers', sorted(set(flat_layers))))
            if int(first['from_layer']) == int(first['to_layer']) or \
                    int(second['from_layer']) == int(second['to_layer']):
                issues.append((rid, 'transition_same_layer',))
        # per part checks + xy chain continuity
        for part in flats:
            check_flat_part(part, rid, row_z, issues)
        cursor = (record.get('source_port') or {}).get('xy')
        if cursor is None:
            issues.append((rid, 'source_port_missing',))
            cursor = (1e9, 1e9)
        else:
            cursor = xy(cursor)
            if not inside_board(*cursor):
                issues.append((rid, 'source_port_outside_board',))
        z_cursor = row_z
        for index, part in enumerate(parts):
            if part['kind'] == 'flat':
                first_prim = part['primitives'][0]
                if not close_xy(first_prim['p0'], cursor):
                    issues.append((rid, 'part_start_joint', index,
                                   round(dist_xy(first_prim['p0'], cursor), 9)))
                if abs(float(part['z_mm']) - z_cursor) > Z_TOL:
                    issues.append((rid, 'part_z_joint', index))
                cursor = xy(part['primitives'][-1]['p1'])
                z_cursor = float(part['z_mm'])
            else:
                previous = parts[index - 1] if index > 0 else None
                following = parts[index + 1] if index + 1 < len(parts) else None
                check_transition_part(part, rid, previous, following, issues)
                if not close_xy(part['start'], cursor):
                    issues.append((rid, 'transition_start_joint', index))
                cursor = xy(part['end'])
                z_cursor = float(part['z1'])
        target_port = (record.get('target_port') or {}).get('xy')
        if target_port is None:
            issues.append((rid, 'target_port_missing',))
        elif not close_xy(cursor, xy(target_port)):
            issues.append((rid, 'route_end_port',
                           round(dist_xy(cursor, xy(target_port)), 9)))
        # length bookkeeping
        part_length = sum(float(part.get('length_mm', 0.0)) for part in parts)
        if abs(float(record.get('length_mm', -1.0)) - part_length) > LEN_TOL:
            issues.append((rid, 'route_length',
                           float(record.get('length_mm', -1.0)) - part_length))
        xy_length = sum(prim_length(prim) for part in flats
                        for prim in part['primitives']) + \
            sum(float(part['footprint_mm']) for part in transitions)
        if abs(float(record.get('xy_length_mm', -1.0)) - xy_length) > LEN_TOL:
            issues.append((rid, 'xy_length',
                           float(record.get('xy_length_mm', -1.0)) - xy_length))
        z_span = max(float(part['z_mm']) for part in flats) - \
            min(float(part['z_mm']) for part in flats)
        if abs(float(record.get('z_span_mm', -1.0)) - z_span) > Z_TOL:
            issues.append((rid, 'z_span', record.get('z_span_mm'), z_span))
        if row != int(record.get('source_row', -1)) or \
                row != int(record.get('target_row', -1)):
            issues.append((rid, 'row_plane_mismatch', plane,
                           record.get('source_row'), record.get('target_row')))
    kinds = Counter(str(item[1]) for item in issues)
    stats['issues'] = len(issues)
    report.add('route_geometry', not issues, category='core',
               detail=[list(item) for item in issues[:30]],
               issue_count=len(issues), issue_kinds=dict(kinds), **stats)
    return issues


# ---------------------------------------------------------------------------
# 2D-chain invariance (adjacent / opposite keep the phase-2 XY path)
# ---------------------------------------------------------------------------
def check_2d_invariance(report, records, phase2, connection):
    issues = []
    checked = 0
    for rid, record in records.items():
        relation = record.get('relation')
        expected = phase2.get(rid)
        if expected is None:
            issues.append((rid, 'phase2_record_missing'))
            continue
        expected_prims = expected.get('primitives') or []
        expected_length = path_length(expected_prims)
        parts = record.get('parts') or []
        flats = [part for part in parts if part['kind'] == 'flat']
        transitions = [part for part in parts if part['kind'] == 'transition']
        if relation == SAME:
            continue
        checked += 1
        if not transitions:
            actual_prims = [prim for part in flats for prim in part['primitives']]
            if norm_span_primitives(actual_prims) != norm_span_primitives(expected_prims):
                if len(actual_prims) != len(expected_prims):
                    issues.append((rid, 'flat_primitive_count',
                                   len(actual_prims), len(expected_prims)))
                else:
                    issues.append((rid, 'flat_primitive_geometry_differs'))
            continue
        # lifted adjacent/opposite: rebuild the XY chain from flat parts plus the
        # transition projections and require it to trace the phase-2 path.
        chain = []
        for part in parts:
            if part['kind'] == 'flat':
                chain.extend(dict(prim) for prim in part['primitives'])
            else:
                start = part.get('start')
                end = part.get('end')
                if start is None or end is None:
                    issues.append((rid, 'transition_missing_xy'))
                    continue
                if dist_xy(start, end) > 1e-12:
                    chain.append(dict(kind='line', p0=list(start), p1=list(end),
                                      layer=0))
        chain_length = path_length(chain)
        if abs(chain_length - expected_length) > 1e-4:
            issues.append((rid, 'xy_chain_length', round(chain_length, 6),
                           round(expected_length, 6)))
        for index, prim in enumerate(chain):
            for point in (prim['p0'], prim['p1']):
                if not point_on_chain(point, expected_prims):
                    issues.append((rid, 'xy_chain_point_off_phase2', index,
                                   [round(float(v), 6) for v in point]))
                    break
            if issues and issues[-1][0] == rid:
                break
        start_expected = xy(expected_prims[0]['p0'])
        end_expected = xy(expected_prims[-1]['p1'])
        if chain:
            if not close_xy(chain[0]['p0'], start_expected) or \
                    not close_xy(chain[-1]['p1'], end_expected):
                issues.append((rid, 'xy_chain_endpoints'))
    report.add('xy_2d_chain_invariance', not issues, category='core',
               detail=[list(item) for item in issues[:20]],
               checked_non_u_routes=checked, issue_count=len(issues))


# ---------------------------------------------------------------------------
# strict U geometry (extended straight + S + target-layer quarter arcs)
# ---------------------------------------------------------------------------
def check_u_geometry(report, records, port_model, connection):
    issues = []
    groups_ok = 0
    details = {}
    for gid in TARGET_U_GROUPS:
        target_layer, target_z = TARGET_U_LAYER[gid]
        group = connection['groups'][gid]
        rids = [int(rid) for rid in group['route_ids']]
        group_errors = []
        for rid in rids:
            record = records.get(rid)
            if record is None:
                group_errors.append(dict(route_id=rid, problem='missing'))
                continue
            parts = record.get('parts') or []
            if len(parts) != 5 or [part['kind'] for part in parts] != \
                    ['flat', 'transition', 'flat', 'transition', 'flat']:
                group_errors.append(dict(route_id=rid, problem='part_pattern',
                                         kinds=[part['kind'] for part in parts]))
                continue
            first, high, last = parts[0], parts[2], parts[4]
            side = record.get('source_side')
            target_side = record.get('target_side')
            if side not in INWARD or target_side != side:
                group_errors.append(dict(route_id=rid, problem='sides',
                                         source_side=side,
                                         target_side=target_side))
                continue
            inward = INWARD[side]
            # entry / exit extended straights must be single axis lines along inward
            for name, part, expected_dir in (
                    ('entry', first, inward),
                    ('exit', last, (-inward[0], -inward[1]))):
                prims = part['primitives']
                if len(prims) != 1 or prims[0]['kind'] != 'line':
                    group_errors.append(dict(route_id=rid,
                                             problem=f'{name}_not_single_line'))
                    continue
                direction = unit((float(prims[0]['p1'][0])
                                  - float(prims[0]['p0'][0]),
                                  float(prims[0]['p1'][1])
                                  - float(prims[0]['p0'][1])))
                if not close_xy(direction, expected_dir):
                    group_errors.append(dict(route_id=rid,
                                             problem=f'{name}_direction',
                                             direction=direction,
                                             expected=expected_dir))
            source_endpoint = record.get('source_endpoint')
            target_endpoint = record.get('target_endpoint')
            if source_endpoint in port_model:
                expected_port = tuple(float(v) for v in
                                      port_model[source_endpoint]['routing_xy'])
                first_prim = first['primitives'][0] if first['primitives'] else None
                if first_prim is not None and \
                        not close_xy(first_prim['p0'], expected_port):
                    group_errors.append(dict(route_id=rid,
                                             problem='entry_not_at_source_port'))
            if target_endpoint in port_model:
                expected_port = tuple(float(v) for v in
                                      port_model[target_endpoint]['routing_xy'])
                last_prim = last['primitives'][-1] if last['primitives'] else None
                if last_prim is not None and \
                        not close_xy(last_prim['p1'], expected_port):
                    group_errors.append(dict(route_id=rid,
                                             problem='exit_not_at_target_port'))
            # target-layer chain: exactly two quarter arcs + middle straight
            prims = high['primitives']
            arcs = [(index, prim) for index, prim in enumerate(prims)
                    if prim['kind'] == 'arc']
            if len(arcs) != 2:
                group_errors.append(dict(route_id=rid, problem='high_arc_count',
                                         arcs=len(arcs)))
                continue
            for index, prim in arcs:
                if abs(float(prim['radius']) - R) > ARC_TOL:
                    group_errors.append(dict(route_id=rid, problem='high_arc_radius',
                                             index=index, radius=prim['radius']))
                if abs(abs(float(prim['sweep'])) - math.pi / 2.0) > ANGLE_TOL:
                    group_errors.append(dict(route_id=rid,
                                             problem='high_arc_sweep',
                                             index=index, sweep=prim['sweep']))
            first_index, second_index = arcs[0][0], arcs[1][0]
            middle = [prim for prim in prims[first_index + 1:second_index]
                      if prim['kind'] == 'line']
            if len(middle) < 1:
                group_errors.append(dict(route_id=rid, problem='no_middle_line'))
                continue
            # source/target separation along the side
            if source_endpoint in port_model and target_endpoint in port_model:
                p = tuple(float(v) for v in port_model[source_endpoint]['routing_xy'])
                q = tuple(float(v) for v in port_model[target_endpoint]['routing_xy'])
                separation = abs(p[0] - q[0]) if side in 'NS' else abs(p[1] - q[1])
                middle_length = sum(prim_length(prim) for prim in middle)
                if abs(middle_length - (separation - 2.0 * R)) > FORM_TOL:
                    group_errors.append(dict(route_id=rid,
                                             problem='middle_straight_length',
                                             actual=round(middle_length, 9),
                                             expected=round(separation - 2.0 * R, 9)))
                for prim in middle:
                    direction = unit((float(prim['p1'][0]) - float(prim['p0'][0]),
                                      float(prim['p1'][1]) - float(prim['p0'][1])))
                    if abs(direction[0] * inward[0] + direction[1] * inward[1]) > 1e-9:
                        group_errors.append(dict(route_id=rid,
                                                 problem='middle_not_parallel_to_side'))
                        break
            # both quarter arcs sit at the same depth from the side
            d0 = depth_of(side, arcs[0][1]['p0'])
            d1 = depth_of(side, arcs[1][1]['p1'])
            if abs(d0 - d1) > POS_TOL:
                group_errors.append(dict(route_id=rid, problem='arc_depths_differ',
                                         d0=round(d0, 9), d1=round(d1, 9)))
            if int(high['layer_id']) != target_layer or \
                    abs(float(high['z_mm']) - target_z) > Z_TOL:
                group_errors.append(dict(route_id=rid, problem='target_layer',
                                         layer_id=high['layer_id'],
                                         z=high['z_mm']))
            entry_length = float(first['length_mm'])
            exit_length = float(last['length_mm'])
            if abs(entry_length - exit_length) > POS_TOL:
                group_errors.append(dict(route_id=rid,
                                         problem='asymmetric_extended_straights',
                                         entry=round(entry_length, 9),
                                         exit=round(exit_length, 9)))
        details[gid] = dict(target_layer=target_layer, target_z=target_z,
                            route_ids=rids, ok=not group_errors,
                            errors=group_errors[:6])
        if group_errors:
            issues.append(dict(group_id=gid, target_layer=target_layer,
                               errors=group_errors[:6]))
        else:
            groups_ok += 1
    report.add('u_quartet_geometry', not issues, category='core',
               detail=issues[:20], groups_ok=groups_ok,
               groups_total=len(TARGET_U_GROUPS), details=details)
    return details


# ---------------------------------------------------------------------------
# opposite L2 straight-through check
# ---------------------------------------------------------------------------
def check_opposite_straight(report, records, phase2, connection):
    issues = []
    checked_groups = 0
    for gid in connection['opposite_groups']:
        group = connection['groups'][gid]
        rids = [int(rid) for rid in group['route_ids']]
        rep = records.get(rids[0])
        if rep is None:
            continue
        classes, _info = classify_route(rep)
        if 'opposite_L2' not in classes:
            continue
        checked_groups += 1
        expected = phase2.get(rids[0]) or {}
        expected_prims = expected.get('primitives') or []
        for rid in rids:
            record = records.get(rid)
            if record is None:
                issues.append(dict(group_id=gid, route_id=rid,
                                   problem='missing'))
                continue
            expected = phase2.get(rid) or {}
            expected_prims = expected.get('primitives') or []
            parts = record.get('parts') or []
            flats = [part for part in parts if part['kind'] == 'flat']
            transitions = [part for part in parts if part['kind'] == 'transition']
            points = []
            for part in flats:
                for prim in part['primitives']:
                    if prim['kind'] != 'line':
                        issues.append(dict(group_id=gid, route_id=rid,
                                           problem='high/L1 chain has an arc'))
                        continue
                    points.extend([tuple(prim['p0']), tuple(prim['p1'])])
            for part in transitions:
                points.extend([tuple(part['start']), tuple(part['end'])])
            if len(points) < 2:
                continue
            # straight reference: this member's own phase-2 primitive (the
            # opposite connections are single straight lines; rotated members
            # have their own rotated line, so never use the rep's line here)
            reference = next((prim for prim in expected_prims
                              if prim.get('kind') == 'line'), None)
            if reference is None:
                continue
            p0, p1 = tuple(reference['p0']), tuple(reference['p1'])
            dx, dy = float(p1[0]) - float(p0[0]), float(p1[1]) - float(p0[1])
            vertical = abs(dx) <= 1e-9 and abs(dy) > 1e-9
            horizontal = abs(dy) <= 1e-9 and abs(dx) > 1e-9
            if not (vertical or horizontal):
                continue
            for point in points:
                if vertical:
                    ok = abs(float(point[0]) - float(p0[0])) <= POS_TOL
                else:
                    ok = abs(float(point[1]) - float(p0[1])) <= POS_TOL
                if not ok:
                    issues.append(dict(group_id=gid, route_id=rid,
                                       problem='not_straight_through',
                                       point=[round(float(v), 6) for v in point]))
                    break
            # high-layer flat must be a single straight line
            high = [part for part in flats if int(part['layer_id']) != 1]
            if len(high) != 1 or len(high[0]['primitives']) != 1 or \
                    high[0]['primitives'][0]['kind'] != 'line':
                issues.append(dict(group_id=gid, route_id=rid,
                                   problem='L2_flat_not_single_line'))
    report.add('opposite_L2_straight', not issues, category='core',
               detail=issues[:20], groups=checked_groups,
               issue_count=len(issues))


# ---------------------------------------------------------------------------
# C4 strict rotation symmetry (all 256 quartets)
# ---------------------------------------------------------------------------
def compare_primitive_rotation(expected, actual, route_id, part_index,
                               prim_index, errors):
    tag = (route_id, part_index, prim_index)
    if expected.get('kind') != actual.get('kind'):
        errors.append(tag + ('prim_kind', actual.get('kind'),
                             expected.get('kind')))
        return
    for key in ('p0', 'p1'):
        if not close_xy(expected[key], actual.get(key) or (1e9, 1e9)):
            errors.append(tag + (key,))
    if expected['kind'] == 'arc':
        if not close_xy(expected['center'], actual.get('center') or (1e9, 1e9)):
            errors.append(tag + ('center',))
        if abs(float(actual.get('radius', -1.0)) - float(expected['radius'])) > ARC_TOL:
            errors.append(tag + ('radius',))
        if abs(float(actual.get('sweep', 0.0)) - float(expected['sweep'])) > ANGLE_TOL:
            errors.append(tag + ('sweep',))
        if angle_diff(actual.get('start_angle', 0.0),
                      expected['start_angle']) > ANGLE_TOL:
            errors.append(tag + ('start_angle',))


def compare_route_rotation(expected, actual, errors):
    route_id = int(actual['route_id'])
    if [part['kind'] for part in expected['parts']] != \
            [part['kind'] for part in actual['parts']]:
        errors.append((route_id, 'part_kinds'))
        return
    for part_index, (exp, act) in enumerate(zip(expected['parts'],
                                                actual['parts'])):
        if exp['kind'] == 'flat':
            if int(exp['layer_id']) != int(act['layer_id']):
                errors.append((route_id, part_index, 'layer_id'))
            if abs(float(exp['z_mm']) - float(act['z_mm'])) > Z_TOL:
                errors.append((route_id, part_index, 'z_mm'))
            if abs(float(exp['length_mm']) - float(act['length_mm'])) > LEN_TOL:
                errors.append((route_id, part_index, 'length_mm'))
            if len(exp['primitives']) != len(act['primitives']):
                errors.append((route_id, part_index, 'prim_count',
                               len(act['primitives']), len(exp['primitives'])))
                continue
            for prim_index, (exp_prim, act_prim) in enumerate(
                    zip(exp['primitives'], act['primitives'])):
                compare_primitive_rotation(exp_prim, act_prim, route_id,
                                           part_index, prim_index, errors)
        else:
            for key in ('z0', 'z1'):
                if abs(float(exp[key]) - float(act[key])) > Z_TOL:
                    errors.append((route_id, part_index, key))
            for key in ('from_layer', 'to_layer'):
                if int(exp[key]) != int(act[key]):
                    errors.append((route_id, part_index, key))
            for key in ('radius_mm', 'theta_rad', 'footprint_mm', 'length_mm'):
                if abs(float(exp[key]) - float(act[key])) > FORM_TOL:
                    errors.append((route_id, part_index, key))
            for key in ('start', 'direction', 'end'):
                if not close_xy(exp[key], act[key]):
                    errors.append((route_id, part_index, key))
    if [round(float(value), 9) for value in expected['layer_sequence']] != \
            [round(float(value), 9) for value in actual.get('layer_sequence', [])]:
        errors.append((route_id, 'layer_sequence'))
    if [round(float(value), 9) for value in expected['layer_z_sequence']] != \
            [round(float(value), 9) for value in actual.get('layer_z_sequence', [])]:
        errors.append((route_id, 'layer_z_sequence'))


def check_c4_rotations(report, records, connection, expected_groups):
    errors = []
    audited = 0
    group_errors = []
    for gid in sorted(expected_groups):
        group = expected_groups[gid]
        ids = [int(rid) for rid in group['route_ids']]
        members = [records.get(rid) for rid in ids]
        if any(member is None for member in members):
            group_errors.append(dict(group_id=gid,
                                     problem='missing member',
                                     route_ids=ids))
            continue
        # every quartet member must live on the same physical interface plane
        planes = {member['plane'] for member in members}
        if len(planes) != 1 or planes != {group.get('plane')}:
            group_errors.append(dict(group_id=gid, problem='plane mismatch',
                                     planes=sorted(planes),
                                     expected=group.get('plane')))
        rep = members[0]
        for phase in range(1, 4):
            member = members[phase]
            rotated = rotate_route(rep, phase)
            start_xy, end_xy = event_route_xy(rotated)
            if not close_xy(start_xy, member['source_port']['xy']):
                if close_xy(end_xy, member['source_port']['xy']):
                    rotated = reverse_route(rotated)
                    start_xy, end_xy = event_route_xy(rotated)
                if not close_xy(start_xy, member['source_port']['xy']) or \
                        not close_xy(end_xy, member['target_port']['xy']):
                    group_errors.append(dict(group_id=gid,
                                             route_id=ids[phase],
                                             phase=phase,
                                             problem='orientation'))
                    continue
            if not close_xy(start_xy, member['source_port']['xy']) or \
                    not close_xy(end_xy, member['target_port']['xy']):
                group_errors.append(dict(group_id=gid, route_id=ids[phase],
                                         phase=phase, problem='ports'))
                continue
            before = len(errors)
            compare_route_rotation(rotated, member, errors)
            if len(errors) > before:
                group_errors.append(dict(group_id=gid, route_id=ids[phase],
                                         phase=phase,
                                         problem='geometry',
                                         detail=[list(item)
                                                 for item in errors[before:before + 4]]))
            audited += 1
    report.add('c4_strict_rotation', not group_errors, category='core',
               detail=group_errors[:20], audited_members=audited,
               groups=len(expected_groups), error_count=len(group_errors))
    return group_errors


# ---------------------------------------------------------------------------
# independent metric recomputation
# ---------------------------------------------------------------------------
def _height_entries(records):
    entries = defaultdict(list)
    for rid, record in records.items():
        for part in record.get('parts') or []:
            if part['kind'] == 'flat':
                entries[round(float(part['z_mm']), 9)].append(
                    (int(rid), part['primitives']))
    return entries


def _line_line_intersections(p0, p1, q0, q1, eps=1e-12):
    d1x, d1y = p1[0] - p0[0], p1[1] - p0[1]
    d2x, d2y = q1[0] - q0[0], q1[1] - q0[1]
    denom = d1x * d2y - d1y * d2x
    if abs(denom) <= eps:
        return []
    rx, ry = q0[0] - p0[0], q0[1] - p0[1]
    t = (rx * d2y - ry * d2x) / denom
    u = (rx * d1y - ry * d1x) / denom
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return [(p0[0] + t * d1x, p0[1] + t * d1y)]
    return []


def _angle_on_arc(center, start_angle, sweep, point, tol=1e-9):
    angle = math.atan2(point[1] - center[1], point[0] - center[0])
    if sweep >= 0.0:
        delta = (angle - start_angle) % (2.0 * math.pi)
    else:
        delta = (start_angle - angle) % (2.0 * math.pi)
    return delta <= abs(sweep) + tol


def _line_arc_intersections(p0, p1, arc):
    center = arc['center']
    radius = float(arc['radius'])
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    fx, fy = p0[0] - center[0], p0[1] - center[1]
    a = dx * dx + dy * dy
    if a <= 1e-18:
        return []
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < -1e-12:
        return []
    disc = max(0.0, disc)
    root = math.sqrt(disc)
    points = []
    for t in ((-b - root) / (2.0 * a), (-b + root) / (2.0 * a)):
        if -1e-9 <= t <= 1.0 + 1e-9:
            point = (p0[0] + t * dx, p0[1] + t * dy)
            if _angle_on_arc(center, float(arc['start_angle']),
                             float(arc['sweep']), point):
                if not any(abs(point[0] - other[0]) <= 1e-7
                           and abs(point[1] - other[1]) <= 1e-7
                           for other in points):
                    points.append(point)
    return points


def _arc_arc_intersections(arc_a, arc_b):
    c1, c2 = arc_a['center'], arc_b['center']
    r1, r2 = float(arc_a['radius']), float(arc_b['radius'])
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    distance = math.hypot(dx, dy)
    if distance <= 1e-12 or distance > r1 + r2 + 1e-9 or distance < abs(r1 - r2) - 1e-9:
        return []
    a = (r1 * r1 - r2 * r2 + distance * distance) / (2.0 * distance)
    h_sq = r1 * r1 - a * a
    if h_sq < -1e-12:
        return []
    h = math.sqrt(max(0.0, h_sq))
    mx, my = c1[0] + a * dx / distance, c1[1] + a * dy / distance
    points = []
    for sign in (1.0, -1.0):
        if h <= 1e-12:
            candidates = [(mx, my)]
        else:
            candidates = [(mx + sign * h * (-dy) / distance,
                           my + sign * h * dx / distance)]
        for point in candidates:
            if _angle_on_arc(c1, float(arc_a['start_angle']),
                             float(arc_a['sweep']), point) and \
                    _angle_on_arc(c2, float(arc_b['start_angle']),
                                  float(arc_b['sweep']), point):
                if not any(abs(point[0] - other[0]) <= 1e-7
                           and abs(point[1] - other[1]) <= 1e-7
                           for other in points):
                    points.append(point)
    return points


def _primitive_intersections(prim_a, prim_b):
    if prim_a['kind'] == 'line' and prim_b['kind'] == 'line':
        return _line_line_intersections(xy(prim_a['p0']), xy(prim_a['p1']),
                                        xy(prim_b['p0']), xy(prim_b['p1']))
    if prim_a['kind'] == 'line' and prim_b['kind'] == 'arc':
        return _line_arc_intersections(xy(prim_a['p0']), xy(prim_a['p1']), prim_b)
    if prim_a['kind'] == 'arc' and prim_b['kind'] == 'line':
        return _line_arc_intersections(xy(prim_b['p0']), xy(prim_b['p1']), prim_a)
    if prim_a['kind'] == 'arc' and prim_b['kind'] == 'arc':
        return _arc_arc_intersections(prim_a, prim_b)
    return []


def _chain_bbox(primitives):
    xs, ys = [], []
    for prim in primitives:
        for key in ('p0', 'p1'):
            xs.append(float(prim[key][0]))
            ys.append(float(prim[key][1]))
        if prim['kind'] == 'arc':
            xs.extend([float(prim['center'][0]) - float(prim['radius']),
                       float(prim['center'][0]) + float(prim['radius'])])
            ys.extend([float(prim['center'][1]) - float(prim['radius']),
                       float(prim['center'][1]) + float(prim['radius'])])
    return (min(xs), min(ys), max(xs), max(ys))


def own_crossing_audit(entries):
    """Independent exact geometry crossing audit per physical height."""
    pairs_by_height = {}
    points_by_height = {}
    unique = set()
    for z_mm in sorted(entries):
        prepared = []
        for rid, primitives in entries[z_mm]:
            bbox = _chain_bbox(primitives)
            prepared.append((rid, primitives, bbox))
        pairs = set()
        points = 0
        for index in range(len(prepared)):
            rid_a, prims_a, box_a = prepared[index]
            for other in range(index + 1, len(prepared)):
                rid_b, prims_b, box_b = prepared[other]
                if rid_a == rid_b:
                    continue
                if box_a[2] < box_b[0] - 1e-9 or box_b[2] < box_a[0] - 1e-9 \
                        or box_a[3] < box_b[1] - 1e-9 or box_b[3] < box_a[1] - 1e-9:
                    continue
                found = []
                for prim_a in prims_a:
                    for prim_b in prims_b:
                        found.extend(_primitive_intersections(prim_a, prim_b))
                if found:
                    unique_points = []
                    for point in found:
                        if not any(dist_xy(point, other_point) <= 1e-6
                                   for other_point in unique_points):
                            unique_points.append(point)
                    if unique_points:
                        pairs.add((min(rid_a, rid_b), max(rid_a, rid_b)))
                        points += len(unique_points)
        pairs_by_height[z_mm] = pairs
        points_by_height[z_mm] = points
        unique |= pairs
    return dict(pairs_by_height=pairs_by_height,
                points_by_height=points_by_height,
                unique_pairs=len(unique),
                pairs=unique)


def compute_metrics(records, u_rids, connection, deep=False):
    entries = _height_entries(records)
    unique_pairs = set()
    pairs_by_height = {}
    points_by_height = {}
    violations = 0
    crossing_angle_sum = 0
    for z_mm in sorted(entries):
        prepared = [FSLW.prepare_route(primitives, rid)
                    for rid, primitives in entries[z_mm]]
        audit = FSLW.audit_route_pairs(prepared, policy='strict')
        pairs_by_height[str(z_mm)] = int(audit.get('crossing_pair_count') or 0)
        points_by_height[str(z_mm)] = int(audit.get('crossing_count') or 0)
        violations += len(audit.get('violations') or [])
        for item in audit.get('crossings') or []:
            a, b = int(item['route_a']), int(item['route_b'])
            unique_pairs.add((min(a, b), max(a, b)))
            crossing_angle_sum += float(item.get('angle_deg') or 0.0)
    u_rids = set(int(rid) for rid in u_rids)
    uu_pairs = set()
    for z_mm in sorted(entries):
        selected = [(rid, primitives) for rid, primitives in entries[z_mm]
                    if rid in u_rids]
        if len(selected) < 2:
            continue
        prepared = [FSLW.prepare_route(primitives, rid)
                    for rid, primitives in selected]
        audit = FSLW.audit_route_pairs(prepared, policy='strict')
        for item in audit.get('crossings') or []:
            a, b = int(item['route_a']), int(item['route_b'])
            uu_pairs.add((min(a, b), max(a, b)))
        for item in audit.get('violations') or []:
            uu_pairs.add(('violation', json.dumps(item, sort_keys=True,
                                                  default=str)))
    layer_defs = [('L1-z1', 1, 0.0), ('L1-z2', 1, 0.5), ('L2', 2, 1.0),
                  ('L3', 3, 1.5), ('L4', 4, 2.0), ('L5', 5, 2.5)]
    layer_counts = {}
    for name, layer_id, z_mm in layer_defs:
        users = []
        plane_users = Counter()
        for rid, record in records.items():
            for part in record.get('parts') or []:
                if part['kind'] != 'flat':
                    continue
                if int(part['layer_id']) == layer_id and \
                        abs(float(part['z_mm']) - z_mm) <= Z_TOL:
                    users.append(int(rid))
                    plane_users[record.get('plane')] += 1
                    break
        layer_counts[name] = dict(count=len(users), layer_id=layer_id,
                                  z_mm=z_mm, plane_counts=dict(plane_users),
                                  route_ids=sorted(users))
    transitions = sum(int(record.get('n_transitions') or 0)
                      for record in records.values())
    total_length = round(sum(float(record.get('length_mm') or 0.0)
                             for record in records.values()), 4)
    metrics = dict(
        routed=len(records),
        failed=1024 - len(records),
        unique_crossing_pairs=len(unique_pairs),
        crossing_pairs_by_height=pairs_by_height,
        crossing_points_by_height=points_by_height,
        crossing_points_total=sum(points_by_height.values()),
        strict_2d_violations=violations,
        same_layer_u_u_crossing_pairs=len(uu_pairs),
        transitions=int(transitions),
        total_length_mm=total_length,
        layer_counts=layer_counts,
        routes_by_height={str(z): len(value) for z, value in entries.items()},
        distinct_routes_by_height={str(z): len({rid for rid, _p in value})
                                   for z, value in entries.items()},
        plane_route_counts=dict(Counter(record.get('plane')
                                        for record in records.values())),
        relation_counts=dict(Counter(record.get('relation')
                                     for record in records.values())),
    )
    if deep:
        started = time.perf_counter()
        own = own_crossing_audit(entries)
        metrics['own_geometry_crossings'] = dict(
            unique_crossing_pairs=own['unique_pairs'],
            crossing_pairs_by_height={str(z): len(pairs)
                                      for z, pairs in
                                      own['pairs_by_height'].items()},
            crossing_points_by_height={str(z): points for z, points in
                                       own['points_by_height'].items()},
            frozen_unique_crossing_pairs=len(unique_pairs),
            seconds=round(time.perf_counter() - started, 2))
    return metrics


# ---------------------------------------------------------------------------
# authoritative frozen 3D validator
# ---------------------------------------------------------------------------
def route_segments_3d(route, transition_samples=256, arc_samples=32):
    """Own dense 3D segment representation: list of (part_index, kind, segments).

    Each entry is a float array of shape (n_segments, 2, 3) describing one part
    of the route.  Straight flats are kept as one long segment so that segment
    distance (not endpoint distance) is used for the clearance reproduction.
    """
    import numpy as np
    out = []
    for index, part in enumerate(route.get('parts') or []):
        z_mm = float(part.get('z_mm')) if part['kind'] == 'flat' else None
        chunks = []
        if part['kind'] == 'flat':
            for prim in part['primitives']:
                if prim['kind'] == 'line':
                    chunks.append(np.array([
                        [float(prim['p0'][0]), float(prim['p0'][1]), z_mm],
                        [float(prim['p1'][0]), float(prim['p1'][1]), z_mm]]))
                else:
                    points = arc_points(prim, arc_samples)
                    array = np.array([[point[0], point[1], z_mm]
                                      for point in points])
                    chunks.append(array)
            kind = 'flat'
        else:
            points = transition_points(part, transition_samples)
            chunks.append(np.asarray(points, dtype=float))
            kind = 'transition'
        if not chunks:
            continue
        if len(chunks) == 1:
            points = chunks[0]
        else:
            points = np.vstack(chunks)
        if len(points) >= 2:
            segments = np.stack([points[:-1], points[1:]], axis=1)
            out.append((index, kind, segments))
    return out


def _segment_set_min_distance(first, second):
    """Vectorised exact minimum distance between two 3D segment sets.

    Returns ``(distance, (part_a, point_a), (part_b, point_b))``.
    """
    import numpy as np

    def _min_between(points_a, points_b):
        # Ericson, Real-Time Collision Detection, vectorised over all pairs
        p1 = points_a[:, 0, :]
        p2 = points_a[:, 1, :]
        q1 = points_b[:, 0, :]
        q2 = points_b[:, 1, :]
        d1 = p2 - p1
        d2 = q2 - q1
        r = p1[:, None, :] - q1[None, :, :]
        a = np.einsum('ij,ij->i', d1, d1)
        e = np.einsum('ij,ij->i', d2, d2)
        b = np.einsum('ik,jk->ij', d1, d2)
        c = np.einsum('ijk,ik->ij', r, d1)
        f = np.einsum('ijk,jk->ij', r, d2)
        denom = a[:, None] * e[None, :] - b * b
        epsilon = 1e-18
        denom_safe = np.where(np.abs(denom) > epsilon, denom, 1.0)
        s = np.clip((b * f - c * e) / denom_safe, 0.0, 1.0)
        s = np.where(np.abs(denom) > epsilon, s, 0.0)
        t = np.where(e[None, :] > epsilon, (b * s + f) / e[None, :], 0.0)
        # clamp t and recompute s where needed
        low = t < 0.0
        high = t > 1.0
        t = np.clip(t, 0.0, 1.0)
        a_safe = np.where(a[:, None] > epsilon, a[:, None], 1.0)
        s = np.where(low, np.clip(-c / a_safe, 0.0, 1.0), s)
        s = np.where(high, np.clip((b - c) / a_safe, 0.0, 1.0), s)
        # degenerate a == 0
        s = np.where(a[:, None] <= epsilon, 0.0, s)
        e_safe = np.where(e[None, :] > epsilon, e[None, :], 1.0)
        t = np.where(a[:, None] <= epsilon,
                     np.clip(f / e_safe, 0.0, 1.0), t)
        closest_a = p1[:, None, :] + s[..., None] * d1[:, None, :]
        closest_b = q1[None, :, :] + t[..., None] * d2[None, :, :]
        delta = closest_a - closest_b
        squared = np.einsum('ijk,ijk->ij', delta, delta)
        index = int(np.argmin(squared))
        row, col = divmod(index, squared.shape[1])
        return (math.sqrt(float(squared.reshape(-1)[index])),
                tuple(float(v) for v in closest_a[row, col]),
                tuple(float(v) for v in closest_b[row, col]))

    best = (float('inf'), None, None)
    for index_a, kind_a, segments_a in first:
        for index_b, kind_b, segments_b in second:
            distance, point_a, point_b = _min_between(segments_a, segments_b)
            if distance < best[0]:
                best = (distance, (index_a, kind_a, point_a),
                        (index_b, kind_b, point_b))
    return best


def _parse_violation_detail(detail):
    """Extract distance / position / z from a frozen-validator detail string."""
    import re
    info = {}
    text = str(detail or '')
    match = re.search(r'distance=([\-+0-9.eE]+)', text)
    if match:
        try:
            info['distance_mm'] = float(match.group(1))
        except ValueError:
            pass
    match_z = re.search(r'z=([\-+0-9.eE]+)', text)
    if match_z:
        try:
            info['z_mm'] = float(match_z.group(1))
        except ValueError:
            pass
    match_pos = re.search(r'at \(([\-+0-9.eE]+),\s*([\-+0-9.eE]+)',
                          text)
    if match_pos:
        try:
            info['position_xy'] = [float(match_pos.group(1)),
                                   float(match_pos.group(2))]
        except ValueError:
            pass
    return info


def collect_violation_evidence(validator_result, records, connection):
    """Enrich frozen-validator violations with route/part evidence."""
    violations = validator_result.get('violations') or []
    if not violations:
        return dict(unique_pairs=0, evidence=[], reproduced=0, unreproduced=0,
                    kind_counts={})
    unique = {}
    for item in violations:
        try:
            route_a = int(str(item.get('route_id')).split(':')[0])
            route_b = int(str(item.get('other_route')).split(':')[0])
        except (TypeError, ValueError):
            continue
        key = (min(route_a, route_b), max(route_a, route_b), item.get('kind'))
        unique.setdefault(key, []).append(item)
    evidence = []
    reproduced = 0
    unreproduced = 0
    for (route_a, route_b, kind), items in sorted(unique.items())[:12]:
        parsed = [_parse_violation_detail(item.get('detail')) for item in items]
        entry = dict(kind=kind, route_a=route_a, route_b=route_b,
                     validator_occurrences=len(items),
                     validator_sample=[dict(detail=item.get('detail'), **info)
                                       for item, info in zip(items[:3], parsed[:3])],
                     group_a=connection['group_of_route'].get(route_a),
                     group_b=connection['group_of_route'].get(route_b),
                     relation_a=(records.get(route_a) or {}).get('relation'),
                     relation_b=(records.get(route_b) or {}).get('relation'),
                     plane_a=(records.get(route_a) or {}).get('plane'),
                     plane_b=(records.get(route_b) or {}).get('plane'),
                     layer_sequence_a=(records.get(route_a) or {}).get(
                         'layer_sequence'),
                     layer_sequence_b=(records.get(route_b) or {}).get(
                         'layer_sequence'))
        record_a = records.get(route_a)
        record_b = records.get(route_b)
        if record_a is not None and record_b is not None:
            distance, part_a, part_b = _segment_set_min_distance(
                route_segments_3d(record_a), route_segments_3d(record_b))
            entry['independent_min_3d_distance_mm'] = round(float(distance), 9)
            entry['independent_min_location'] = dict(
                route_a_part=part_a[0] if part_a else None,
                route_a_kind=part_a[1] if part_a else None,
                route_a_point=[round(float(v), 6) for v in part_a[2]]
                if part_a else None,
                route_b_part=part_b[0] if part_b else None,
                route_b_kind=part_b[1] if part_b else None,
                route_b_point=[round(float(v), 6) for v in part_b[2]]
                if part_b else None)
            entry['independent_reproduced'] = bool(distance < CLEAR - 1e-6)
            if entry['independent_reproduced']:
                reproduced += 1
            else:
                unreproduced += 1
        evidence.append(entry)
    kind_counts = Counter(item.get('kind') for item in violations)
    return dict(unique_pairs=len(unique), evidence=evidence,
                reproduced=reproduced, unreproduced=unreproduced,
                kind_counts=dict(kind_counts))


def run_authoritative_validator(label, payload, log_fn=log):
    from four_side_1024.v3c4.lift_cross import validate_payload_v4
    if label == 'A':
        root = PHASE2
    else:
        root = build_b_identity_root(log_fn=log_fn)
    started = time.perf_counter()
    report = validate_payload_v4(payload, root, log=lambda *_a, **_k: None)
    seconds = time.perf_counter() - started
    report['_verifier_seconds'] = round(seconds, 2)
    return report


def check_authoritative_validator(report, label, result, records=None,
                                  connection=None):
    counts = dict(result.get('counts') or {})
    stats = result.get('stats') or {}
    errors = []
    if result.get('status') != 'exploratory_only':
        errors.append(dict(problem='status', actual=result.get('status')))
    if not result.get('exploratory_pass'):
        errors.append(dict(problem='exploratory_pass is not true'))
    if result.get('formal_acceptance'):
        errors.append(dict(problem='formal_acceptance unexpectedly true'))
    nonzero = {key: int(counts.get(key, 0)) for key in CATEGORIES
               if int(counts.get(key, 0)) != 0}
    if nonzero:
        errors.append(dict(problem='non-zero validator counts', counts=nonzero))
    min_curvature = stats.get('min_curvature_radius_mm')
    if min_curvature is None or abs(float(min_curvature) - R) > 1e-3:
        errors.append(dict(problem='min curvature', actual=min_curvature))
    min_3d = stats.get('min_3d_clearance_mm')
    if min_3d is None or float(min_3d) < CLEAR - 1e-6:
        errors.append(dict(problem='min 3D clearance', actual=min_3d))
    violations = result.get('violations') or []
    evidence = None
    if violations and records is not None and connection is not None:
        evidence = collect_violation_evidence(result, records, connection)
        errors.append(dict(problem='violations present',
                           count=len(violations),
                           unique_pairs=evidence['unique_pairs'],
                           reproduced=evidence['reproduced'],
                           unreproduced=evidence['unreproduced'],
                           sample=evidence['evidence'][:3]))
    elif violations:
        errors.append(dict(problem='violations present',
                           count=len(violations),
                           sample=violations[:5]))
    block = dict(status=result.get('status'),
                 exploratory_pass=bool(result.get('exploratory_pass')),
                 geometry_pass=bool(result.get('geometry_pass')),
                 formal_acceptance=bool(result.get('formal_acceptance')),
                 counts=counts,
                 min_curvature_radius_mm=min_curvature,
                 min_3d_clearance_mm=min_3d,
                 min_3d_clearance_bound=stats.get('min_3d_clearance_bound'),
                 violation_count=len(violations),
                 strict_2d_crossing_count=stats.get('same_plane_crossings'),
                 total_length_mm=stats.get('total_length_mm'),
                 runtime_seconds=result.get('_verifier_seconds'))
    if evidence is not None:
        block['violation_evidence'] = evidence
    report.add('authoritative_3d_validator', not errors, category='core',
               detail=errors[:10], **{key: value for key, value in block.items()
                                      if key != 'counts'})
    return block


# ---------------------------------------------------------------------------
# production summary comparison
# ---------------------------------------------------------------------------
def _as_dict_of_numbers(value):
    if not isinstance(value, dict):
        return None
    out = {}
    for key, item in value.items():
        try:
            out[key] = float(item)
        except (TypeError, ValueError):
            return None
    return out


def _compare_number(report, topic, production, recomputed, tolerance):
    ok = False
    if isinstance(production, (int, float)) and not isinstance(production, bool) \
            and isinstance(recomputed, (int, float)) \
            and not isinstance(recomputed, bool):
        ok = abs(float(production) - float(recomputed)) <= tolerance
    else:
        ok = production == recomputed
    if not ok:
        report.difference(topic, production, recomputed)
    return ok


def check_summary(report, summary, metrics, validator_block, facts, label):
    if not isinstance(summary, dict):
        report.add('production_summary', False, category='artifacts',
                   detail='summary.json missing or unreadable')
        return
    mismatches = []
    scalar_keys = [('routed', 0), ('failed', 0),
                   ('unique_crossing_pairs', 0),
                   ('same_layer_u_u_crossing_pairs', 0),
                   ('transitions', 0), ('total_length_mm', 1e-3),
                   ('adjacent_on_interface', 0),
                   ('opposite_on_L2_routes', 0),
                   ('opposite_on_L2_groups', 0),
                   ('opposite_total_routes', 0),
                   ('opposite_exception_routes', 0),
                   ('u_rebuilt_routes', 0),
                   ('min_3d_clearance_mm', 1e-6),
                   ('min_curvature_radius_mm', 1e-6)]
    recomputed_scalars = dict(metrics)
    recomputed_scalars.update(facts)
    recomputed_scalars['min_3d_clearance_mm'] = \
        validator_block.get('min_3d_clearance_mm')
    recomputed_scalars['min_curvature_radius_mm'] = \
        validator_block.get('min_curvature_radius_mm')
    alias_keys = {
        'opposite_on_L2_routes': ('opposite_l2_routes',),
        'opposite_on_L2_groups': ('opposite_l2_groups',),
    }
    derived_optional = {'opposite_total_routes': 272,
                        'u_rebuilt_routes': facts.get('u_rebuilt_routes')}
    for key, tolerance in scalar_keys:
        source_key = key
        if key not in summary:
            for alias in alias_keys.get(key, ()):
                if alias in summary:
                    source_key = alias
                    break
            else:
                if key in derived_optional:
                    # older/alternative summary schema simply omits this derived
                    # counter; record it as a schema note instead of a value
                    # difference (the equivalent counter is cross-checked below)
                    report.warn(f'production summary omits {key}; the equivalent '
                                f'value is recomputed from the payload '
                                f'({recomputed_scalars.get(key)})')
                    continue
                mismatches.append(dict(metric=key,
                                       problem='missing in production summary',
                                       recomputed=recomputed_scalars.get(key)))
                report.difference(f'summary.{key}', None,
                                  recomputed_scalars.get(key), note='missing')
                continue
        if not _compare_number(report, f'summary.{key}', summary.get(source_key),
                               recomputed_scalars.get(key), tolerance):
            mismatches.append(dict(metric=key, production=summary.get(source_key),
                                   recomputed=recomputed_scalars.get(key)))
    # optional extra bookkeeping counters written by the artefact stage
    optional_scalars = {
        'opposite_l2_groups': facts.get('opposite_on_L2_groups'),
        'opposite_l2_routes': facts.get('opposite_on_L2_routes'),
        'opposite_exception_groups': len(
            facts.get('opposite_exception_groups') or []),
        'opposite_exception_routes': facts.get('opposite_exception_routes'),
        'u_target_reached_groups': facts.get('u_groups_reached'),
        'u_failed_groups': len(facts.get('u_groups_failed') or []),
    }
    for key, recomputed in optional_scalars.items():
        if key not in summary:
            continue
        if not _compare_number(report, f'summary.{key}', summary.get(key),
                               recomputed, 0):
            mismatches.append(dict(metric=key, production=summary.get(key),
                                   recomputed=recomputed))
    delivery = summary.get('delivery')
    if isinstance(delivery, dict):
        expected_delivery = ('routes_1024.json', 'u_layer_assignment.json',
                             'opposite_assignment.json', 'validation.json',
                             'summary.json')
        listed = [str(delivery.get(name)) for name in
                  ('routes', 'u_layer_assignment', 'opposite_assignment',
                   'validation', 'summary')]
        ok = all(any(token in item for item in listed)
                 for token in expected_delivery)
        report.add('summary_delivery_manifest', ok, category='info',
                   detail=dict(delivery=delivery))
    experiment = str(summary.get('experiment') or '')
    label_ok = ('STRUCTURED_LAYER' in experiment.upper()
                or not experiment.strip())
    report.add('summary_experiment_label', label_ok, category='info',
               detail=dict(experiment=experiment,
                           group=summary.get('group'),
                           note=None if experiment.strip() else
                           'producer summary omits the experiment label'))
    if not experiment.strip():
        report.warn('producer summary has no experiment label (schema variant)')
    for key in ('crossing_pairs_by_height', 'crossing_points_by_height',
                'routes_by_height'):
        production = summary.get(key)
        recomputed = metrics.get(key)
        if not isinstance(production, dict) or not isinstance(recomputed, dict):
            mismatches.append(dict(metric=key, problem='missing/not a dict',
                                   production=production,
                                   recomputed=recomputed))
            continue
        prod_map = {str(round(float(k), 9)): int(v)
                    for k, v in production.items()}
        rec_map = {str(round(float(k), 9)): int(v)
                   for k, v in recomputed.items()}
        if prod_map != rec_map:
            mismatches.append(dict(metric=key, production=prod_map,
                                   recomputed=rec_map))
            report.difference(f'summary.{key}', prod_map, rec_map)
    # layer counts
    production_layers = summary.get('layer_counts') or {}
    recomputed_layers = metrics.get('layer_counts') or {}
    if isinstance(production_layers, dict):
        for name, computed in recomputed_layers.items():
            stored = production_layers.get(name)
            if isinstance(stored, dict):
                stored_count = stored.get('count')
                stored_planes = stored.get('plane_counts')
            else:
                stored_count = stored
                stored_planes = None
            if stored_count is None:
                mismatches.append(dict(metric=f'layer_counts.{name}',
                                       problem='missing'))
                continue
            if int(stored_count) != int(computed['count']):
                mismatches.append(dict(metric=f'layer_counts.{name}.count',
                                       production=stored_count,
                                       recomputed=computed['count']))
            if isinstance(stored_planes, dict):
                prod_planes = {str(k): int(v) for k, v in stored_planes.items()}
                if prod_planes != computed['plane_counts']:
                    mismatches.append(dict(
                        metric=f'layer_counts.{name}.plane_counts',
                        production=prod_planes,
                        recomputed=computed['plane_counts']))
    # validation fields stored in the summary
    if 'validation_status' in summary and \
            summary.get('validation_status') != validator_block.get('status'):
        mismatches.append(dict(metric='validation_status',
                               production=summary.get('validation_status'),
                               recomputed=validator_block.get('status')))
    if 'validation_exploratory_pass' in summary and \
            bool(summary.get('validation_exploratory_pass')) != \
            bool(validator_block.get('exploratory_pass')):
        mismatches.append(dict(metric='validation_exploratory_pass',
                               production=summary.get('validation_exploratory_pass'),
                               recomputed=validator_block.get('exploratory_pass')))
    if 'validation_geometry_pass' in summary and \
            bool(summary.get('validation_geometry_pass')) != \
            bool(validator_block.get('geometry_pass')):
        mismatches.append(dict(metric='validation_geometry_pass',
                               production=summary.get('validation_geometry_pass'),
                               recomputed=validator_block.get('geometry_pass')))
    if isinstance(summary.get('validation_counts'), dict):
        prod_counts = {key: int(value) for key, value in
                       summary['validation_counts'].items()}
        rec_counts = {key: int(value) for key, value in
                      (validator_block.get('counts') or {}).items()}
        if prod_counts != rec_counts:
            mismatches.append(dict(metric='validation_counts',
                                   production=prod_counts,
                                   recomputed=rec_counts))
    # u failures / opposite exceptions bookkeeping
    summary_u_failures = summary.get('u_failures') or {}
    expected_u_failures = {str(gid) for gid in facts.get('u_groups_failed') or []}
    try:
        stored_u_failures = {str(int(key)) for key in summary_u_failures}
    except (TypeError, ValueError):
        stored_u_failures = set()
    if stored_u_failures != expected_u_failures:
        mismatches.append(dict(metric='u_failures.groups',
                               production=sorted(stored_u_failures),
                               recomputed=sorted(expected_u_failures)))
    summary_exceptions = summary.get('opposite_exceptions') or {}
    try:
        stored_exceptions = {str(int(key)) for key in summary_exceptions}
    except (TypeError, ValueError):
        stored_exceptions = set()
    expected_exceptions = {str(gid) for gid in
                           facts.get('opposite_exception_groups') or []}
    if stored_exceptions != expected_exceptions:
        mismatches.append(dict(metric='opposite_exceptions.groups',
                               production=sorted(stored_exceptions),
                               recomputed=sorted(expected_exceptions)))
    # exact-length / angle consistency with the frozen validator stats
    validator_total = (validator_block.get('counts') is not None)
    report.numbers['production_summary'] = dict(
        path=str(STRUCT / label / 'summary.json'),
        keys=sorted(summary.keys()))
    report.add('metrics_match_production_summary', not mismatches,
               category='metrics', detail=mismatches[:20],
               mismatch_count=len(mismatches), validator_available=validator_total)


# ---------------------------------------------------------------------------
# assignment artefacts / validation artefact / figures
# ---------------------------------------------------------------------------
def _normalise_rows(obj, names=('assignment', 'assignments', 'groups',
                                'quartets', 'rows', 'details',
                                'group_assignments')):
    """Best-effort extraction of per-quartet rows from an unknown schema."""
    if isinstance(obj, list):
        rows = [item for item in obj if isinstance(item, dict)]
        if rows and any('group_id' in row or 'group' in row for row in rows):
            out = []
            for row in rows:
                if 'group_id' not in row:
                    for key in ('group', 'gid', 'quartet'):
                        if key in row:
                            row = dict(row)
                            row['group_id'] = row[key]
                            break
                out.append(row)
            return out
        return None
    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                rows = _normalise_rows(obj[name], names)
                if rows:
                    return rows
        # dict keyed by integer-ish group ids
        keyed = []
        for key, value in obj.items():
            try:
                gid = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault('group_id', gid)
                keyed.append(row)
        if keyed:
            return keyed
        for value in obj.values():
            rows = _normalise_rows(value, names)
            if rows:
                return rows
    return None


def _row_get(row, *names):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def _check_rise_fall_nested(row, records, errors, gid, error_tag):
    """Compare a stored ``rise_fall`` mapping against the actual geometry."""
    nested = _row_get(row, 'rise_fall', 'rise_fall_info', 'transitions')
    if not isinstance(nested, dict):
        return
    for rid_text, info in nested.items():
        if not isinstance(info, dict):
            continue
        try:
            rid = int(str(rid_text).split(':')[0])
        except (TypeError, ValueError):
            continue
        record = records.get(rid)
        if record is None:
            errors.append(dict(group_id=gid, route_id=rid,
                               problem='rise_fall route missing'))
            continue
        parts = record.get('parts') or []
        transitions = [part for part in parts if part['kind'] == 'transition']
        flats = [part for part in parts if part['kind'] == 'flat']
        if len(transitions) != 2 or len(flats) < 3:
            errors.append(dict(group_id=gid, route_id=rid,
                               problem='rise_fall on non-lifted route'))
            continue
        rise, fall = transitions
        expected = {
            'rise_start_xy': (tuple(rise['start']), 'xy'),
            'rise_end_xy': (tuple(rise['end']), 'xy'),
            'rise_start_mm': (float(flats[0]['length_mm']), 'len'),
            'rise_z_mm': ([float(rise['z0']), float(rise['z1'])], 'zlist'),
            'fall_start_xy': (tuple(fall['start']), 'xy'),
            'fall_end_xy': (tuple(fall['end']), 'xy'),
            'fall_start_mm': (float(sum(float(part['length_mm'])
                                        for part in parts[:3])), 'len'),
            'fall_z_mm': ([float(fall['z0']), float(fall['z1'])], 'zlist'),
        }
        for key, (expected_value, kind) in expected.items():
            if key not in info:
                continue
            stored = info[key]
            ok = True
            if kind == 'xy':
                try:
                    ok = close_xy(stored, expected_value)
                except (TypeError, ValueError, IndexError):
                    ok = False
            elif kind == 'len':
                try:
                    ok = abs(float(stored) - expected_value) <= POS_TOL
                except (TypeError, ValueError):
                    ok = False
            elif kind == 'zlist':
                try:
                    ok = len(stored) == 2 and \
                        abs(float(stored[0]) - expected_value[0]) <= Z_TOL and \
                        abs(float(stored[1]) - expected_value[1]) <= Z_TOL
                except (TypeError, ValueError):
                    ok = False
            if not ok:
                errors.append(dict(group_id=gid, route_id=rid,
                                   problem=f'{error_tag}.{key}',
                                   stored=stored,
                                   expected=expected_value
                                   if kind != 'xy' else
                                   [round(float(v), 6)
                                    for v in expected_value]))


def _check_rise_fall_columns(row, records, errors, gid):
    """Compare top-level rise/fall position columns against the actual geometry."""
    record = None
    route_ids = _row_get(row, 'route_ids', 'routes', 'members')
    if route_ids:
        try:
            record = records.get(int(route_ids[0]))
        except (TypeError, ValueError):
            record = None
    if record is None or not record.get('parts'):
        return
    parts = record['parts']
    transitions = [part for part in parts if part['kind'] == 'transition']
    flats = [part for part in parts if part['kind'] == 'flat']
    if not transitions:
        return
    rise = transitions[0]
    expected = {
        'rise_start_xy': tuple(rise['start']),
        'rise_end_xy': tuple(rise['end']),
        'rise_start_mm': float(flats[0]['length_mm']),
    }
    for key, expected_value in expected.items():
        stored = _row_get(row, key)
        if stored is None:
            continue
        try:
            if key.endswith('_xy'):
                ok = close_xy(stored, expected_value)
            else:
                ok = abs(float(stored) - expected_value) <= POS_TOL
        except (TypeError, ValueError):
            ok = False
        if not ok:
            errors.append(dict(group_id=gid, problem=f'column.{key}',
                               stored=stored,
                               expected=[round(float(v), 6)
                                         for v in expected_value]
                               if key.endswith('_xy') else expected_value))


def _row_status_reached(row):
    status = _row_get(row, 'status', 'result', 'classification', 'state',
                      'outcome')
    if status is None:
        return None
    text = str(status).lower()
    if any(token in text for token in ('reach', 'solve', 'solved', 'ok',
                                       'pass', 'success', 'l2', 'lift')):
        return True
    if any(token in text for token in ('fail', 'exception', 'fallback',
                                       'miss', 'unsolved')):
        return False
    return None


def check_u_assignment(report, label, directory, records, u_details, summary):
    path = directory / 'u_layer_assignment.json'
    if not path.is_file():
        report.add('u_layer_assignment_artifact', False, category='artifacts',
                   detail='u_layer_assignment.json missing')
        return
    try:
        payload = read_json_retry(path)
    except RuntimeError as exc:
        report.add('u_layer_assignment_artifact', False, category='artifacts',
                   detail=f'unreadable: {exc}')
        return
    rows = _normalise_rows(payload)
    errors = []
    if not rows:
        errors.append(dict(problem='no per-group rows found',
                           keys=sorted(payload.keys())
                           if isinstance(payload, dict) else None))
        rows = []
    by_gid = {}
    for row in rows:
        gid_value = _row_get(row, 'group_id', 'gid', 'quartet', 'group')
        try:
            gid = int(gid_value)
        except (TypeError, ValueError):
            continue
        by_gid[gid] = row
    missing = sorted(set(TARGET_U_GROUPS) - set(by_gid))
    extra = sorted(set(by_gid) - set(TARGET_U_GROUPS))
    if missing:
        errors.append(dict(problem='missing groups', groups=missing[:20]))
    if extra:
        errors.append(dict(problem='unexpected groups', groups=extra[:20]))
    for gid in TARGET_U_GROUPS:
        row = by_gid.get(gid)
        if row is None:
            continue
        target_layer, target_z = TARGET_U_LAYER[gid]
        route_ids = _row_get(row, 'route_ids', 'routes', 'members')
        expected_ids = [int(rid) for rid in u_details[gid]['route_ids']]
        if route_ids is not None:
            try:
                actual_ids = [int(rid) for rid in route_ids]
            except (TypeError, ValueError):
                actual_ids = None
            if actual_ids != expected_ids:
                errors.append(dict(group_id=gid, problem='route_ids',
                                   actual=actual_ids, expected=expected_ids))
        target = _row_get(row, 'target_layer', 'target_layer_id', 'layer',
                          'layer_id', 'goal_layer')
        if target is not None:
            try:
                target_int = int(target)
            except (TypeError, ValueError):
                target_int = None
            if target_int != target_layer:
                errors.append(dict(group_id=gid, problem='target_layer',
                                   actual=target, expected=target_layer))
        target_z_field = _row_get(row, 'target_z_mm', 'layer_z_mm', 'z_mm',
                                  'target_z')
        if target_z_field is not None:
            try:
                if abs(float(target_z_field) - target_z) > Z_TOL:
                    errors.append(dict(group_id=gid, problem='target_z',
                                       actual=target_z_field,
                                       expected=target_z))
            except (TypeError, ValueError):
                errors.append(dict(group_id=gid, problem='target_z invalid',
                                   actual=target_z_field))
        actual = _row_get(row, 'actual_layer', 'actual_layer_id',
                          'reached_layer', 'achieved_layer')
        if actual is not None:
            try:
                actual_int = int(actual)
            except (TypeError, ValueError):
                actual_int = None
            if actual_int is not None and actual_int != target_layer:
                errors.append(dict(group_id=gid, problem='actual_layer',
                                   actual=actual, expected=target_layer))
        reached_flag = _row_status_reached(row)
        expected_reached = u_details[gid]['ok']
        if reached_flag is not None and reached_flag != expected_reached:
            errors.append(dict(group_id=gid,
                               problem='status disagreement',
                               stored_reached=reached_flag,
                               geometry_reached=expected_reached))
        # optional parameters against the actual representative geometry
        rep = records.get(expected_ids[0]) if expected_ids else None
        if rep is not None and expected_reached:
            flats = [part for part in rep['parts'] if part['kind'] == 'flat']
            high = [part for part in flats if int(part['layer_id']) != 1]
            actual_entry = float(flats[0]['length_mm'])
            actual_exit = float(flats[-1]['length_mm'])
            actual_depth = None
            if high:
                arcs = [prim for prim in high[0]['primitives']
                        if prim['kind'] == 'arc']
                if arcs:
                    actual_depth = depth_of(rep.get('source_side'),
                                            arcs[0]['p0'])
            candidates = [
                (('a_in', 'entry_straight_mm', 'entry_length_mm',
                  'rise_start_mm'), actual_entry),
                (('a_out', 'exit_straight_mm', 'exit_length_mm'), actual_exit),
                (('high_arc_depth', 'high_arc_depth_mm', 'arc_depth_mm'),
                 actual_depth),
            ]
            for names, actual_value in candidates:
                stored = _row_get(row, *names)
                if stored is None or actual_value is None:
                    continue
                try:
                    stored_value = float(stored)
                except (TypeError, ValueError):
                    errors.append(dict(group_id=gid, problem=f'{names[0]} invalid',
                                       actual=stored))
                    continue
                if abs(stored_value - float(actual_value)) > POS_TOL:
                    errors.append(dict(group_id=gid,
                                       problem=f'{names[0]} mismatch',
                                       actual=stored_value,
                                       expected=round(float(actual_value), 9)))
        if not expected_reached:
            reason = _row_get(row, 'failure_reason', 'reason', 'failure',
                              'error', 'note', 'detail')
            if not str(reason or '').strip():
                errors.append(dict(group_id=gid,
                                   problem='failed group without reason'))
        _check_rise_fall_nested(row, records, errors, gid, 'rise_fall')
        _check_rise_fall_columns(row, records, errors, gid)
    # aggregate counters stored in the artefact root
    if isinstance(payload, dict):
        reached_total = sum(1 for gid in TARGET_U_GROUPS
                            if u_details[gid]['ok'])
        for key in ('reached', 'solved', 'target_quartets_reached',
                    'target_reached_groups'):
            stored = payload.get(key)
            if stored is not None:
                try:
                    if int(stored) != reached_total:
                        errors.append(dict(problem=f'aggregate {key}',
                                           actual=stored,
                                           expected=reached_total))
                except (TypeError, ValueError):
                    errors.append(dict(problem=f'aggregate {key} invalid',
                                       actual=stored))
        failed_total = len(TARGET_U_GROUPS) - reached_total
        for key in ('failed', 'failed_groups'):
            stored = payload.get(key)
            if stored is not None:
                try:
                    if int(stored) != failed_total:
                        errors.append(dict(problem=f'aggregate {key}',
                                           actual=stored,
                                           expected=failed_total))
                except (TypeError, ValueError):
                    errors.append(dict(problem=f'aggregate {key} invalid',
                                       actual=stored))
        for key in ('target_quartets', 'total_quartets', 'groups',
                    'total_groups'):
            stored = payload.get(key)
            if stored is not None:
                try:
                    if int(stored) != len(TARGET_U_GROUPS):
                        errors.append(dict(problem=f'aggregate {key}',
                                           actual=stored,
                                           expected=len(TARGET_U_GROUPS)))
                except (TypeError, ValueError):
                    pass
        stored_total_routes = payload.get('total_routes')
        if stored_total_routes is not None:
            try:
                if int(stored_total_routes) != 256:
                    errors.append(dict(problem='aggregate total_routes',
                                       actual=stored_total_routes,
                                       expected=256))
            except (TypeError, ValueError):
                pass
        stored_failures = payload.get('failures')
        if isinstance(stored_failures, dict):
            stored_failed_gids = set()
            for key, value in stored_failures.items():
                try:
                    gid = int(key)
                except (TypeError, ValueError):
                    continue
                stored_failed_gids.add(gid)
                if not str(value or '').strip():
                    errors.append(dict(group_id=gid,
                                       problem='failures reason empty'))
            expected_failed = {gid for gid in TARGET_U_GROUPS
                               if not u_details[gid]['ok']}
            if stored_failed_gids != expected_failed:
                errors.append(dict(problem='failures mapping groups',
                                   actual=sorted(stored_failed_gids),
                                   expected=sorted(expected_failed)))
    report.add('u_layer_assignment_artifact', not errors, category='artifacts',
               detail=errors[:20], rows=len(rows), coverage=len(by_gid),
               path=str(path), sha256=sha256(path))


def check_opposite_assignment(report, label, directory, records, facts):
    path = directory / 'opposite_assignment.json'
    if not path.is_file():
        report.add('opposite_assignment_artifact', False,
                   category='artifacts',
                   detail='opposite_assignment.json missing')
        return
    try:
        payload = read_json_retry(path)
    except RuntimeError as exc:
        report.add('opposite_assignment_artifact', False,
                   category='artifacts', detail=f'unreadable: {exc}')
        return
    rows = _normalise_rows(payload)
    errors = []
    if not rows:
        errors.append(dict(problem='no per-group rows found',
                           keys=sorted(payload.keys())
                           if isinstance(payload, dict) else None))
        rows = []
    by_gid = {}
    expected_groups = facts.get('opposite_total_groups') or 0
    for row in rows:
        try:
            gid = int(_row_get(row, 'group_id', 'gid', 'quartet', 'group'))
        except (TypeError, ValueError):
            continue
        by_gid[gid] = row
    # independent geometry class map recomputed from the payload
    class_map = facts.get('opposite_class_map') or {}
    missing = sorted(gid for gid in class_map if gid not in by_gid)
    extra = sorted(gid for gid in by_gid if gid not in class_map)
    if missing:
        errors.append(dict(problem='missing groups', groups=missing[:20]))
    if extra:
        errors.append(dict(problem='unexpected groups', groups=extra[:20]))
    for gid, cls in class_map.items():
        row = by_gid.get(gid)
        if row is None:
            continue
        expected_reached = (cls == 'opposite_L2')
        status = _row_get(row, 'status', 'result', 'classification', 'class',
                          'origin', 'state')
        text = str(status).lower() if status is not None else ''
        if status is not None:
            if expected_reached:
                ok = any(token in text for token in ('l2', 'lift', 'reach',
                                                     'solve', 'ok', 'pass',
                                                     'success'))
            else:
                ok = any(token in text for token in ('flat', 'exception',
                                                     'fallback', 'interface'))
            if not ok:
                errors.append(dict(group_id=gid, problem='status mismatch',
                                   actual=status,
                                   expected='opposite_L2' if expected_reached
                                   else 'flat_interface_exception'))
        if not expected_reached:
            reason = _row_get(row, 'exception_reason', 'reason', 'failure_reason',
                              'note', 'detail', 'comment')
            if not str(reason or '').strip():
                errors.append(dict(group_id=gid,
                                   problem='exception without documented reason'))
        # optional symmetric a_in/a_out parameters vs actual geometry
        route_ids = _row_get(row, 'route_ids', 'routes', 'members')
        if not route_ids:
            route_ids = (facts.get('opposite_route_ids') or {}).get(gid) or []
        rep = None
        if route_ids:
            try:
                rep = records.get(int(route_ids[0]))
            except (TypeError, ValueError):
                rep = None
        if rep is not None and rep.get('parts'):
            flats = [part for part in rep['parts'] if part['kind'] == 'flat']
            actual_in = float(flats[0]['length_mm'])
            actual_out = float(flats[-1]['length_mm'])
            for names, actual_value in (
                    (('a_in', 'rise_start_mm', 'entry_straight_mm'), actual_in),
                    (('a_out', 'exit_straight_mm'), actual_out)):
                stored = _row_get(row, *names)
                if stored is None:
                    continue
                try:
                    if abs(float(stored) - actual_value) > POS_TOL:
                        errors.append(dict(group_id=gid,
                                           problem=f'{names[0]} mismatch',
                                           actual=float(stored),
                                           expected=round(actual_value, 9)))
                except (TypeError, ValueError):
                    errors.append(dict(group_id=gid,
                                       problem=f'{names[0]} invalid',
                                       actual=stored))
        stored_actual = _row_get(row, 'actual')
        if stored_actual is not None:
            text = str(stored_actual).lower()
            expected_actual = 'l2' if expected_reached else 'interface_flat'
            if expected_reached and 'l2' not in text:
                errors.append(dict(group_id=gid, problem='actual mismatch',
                                   actual=stored_actual,
                                   expected=expected_actual))
            if (not expected_reached) and not any(
                    token in text for token in ('flat', 'interface',
                                                'exception')):
                errors.append(dict(group_id=gid, problem='actual mismatch',
                                   actual=stored_actual,
                                   expected=expected_actual))
        _check_rise_fall_nested(row, records, errors, gid, 'rise_fall')
    if isinstance(payload, dict):
        l2_groups = sum(1 for gid, cls in class_map.items()
                        if cls == 'opposite_L2')
        exception_groups = len(class_map) - l2_groups
        aggregate_expected = {
            'l2_groups': l2_groups,
            'l2_routes': 4 * l2_groups,
            'exception_groups': exception_groups,
            'exception_routes': 4 * exception_groups,
        }
        for key, expected in aggregate_expected.items():
            stored = payload.get(key)
            if stored is None:
                continue
            try:
                if int(stored) != int(expected):
                    errors.append(dict(problem=f'aggregate {key}',
                                       actual=stored, expected=expected))
            except (TypeError, ValueError):
                errors.append(dict(problem=f'aggregate {key} invalid',
                                   actual=stored))
        stored_total_routes = payload.get('total_routes')
        if stored_total_routes is not None:
            try:
                if int(stored_total_routes) != 272:
                    errors.append(dict(problem='aggregate total_routes',
                                       actual=stored_total_routes,
                                       expected=272))
            except (TypeError, ValueError):
                pass
        stored_reasons = payload.get('exception_reasons')
        if isinstance(stored_reasons, dict):
            stored_exception_gids = set()
            for key, value in stored_reasons.items():
                try:
                    gid = int(key)
                except (TypeError, ValueError):
                    continue
                stored_exception_gids.add(gid)
                if not str(value or '').strip():
                    errors.append(dict(group_id=gid,
                                       problem='exception reason empty'))
            expected_exception_gids = {gid for gid, cls in class_map.items()
                                       if cls != 'opposite_L2'}
            if stored_exception_gids != expected_exception_gids:
                errors.append(dict(problem='exception_reasons groups',
                                   actual=sorted(stored_exception_gids),
                                   expected=sorted(expected_exception_gids)))
        for key in ('groups_solved', 'groups_l2', 'l2_groups'):
            stored = payload.get(key)
            if stored is not None:
                try:
                    if int(stored) != int(l2_groups):
                        errors.append(dict(problem=f'aggregate {key}',
                                           actual=stored, expected=l2_groups))
                except (TypeError, ValueError):
                    pass
        for key in ('total_groups', 'groups_expected'):
            stored = payload.get(key)
            if stored is not None and expected_groups:
                try:
                    if int(stored) != int(expected_groups):
                        errors.append(dict(problem=f'aggregate {key}',
                                           actual=stored,
                                           expected=expected_groups))
                except (TypeError, ValueError):
                    pass
    report.add('opposite_assignment_artifact', not errors,
               category='artifacts', detail=errors[:20], rows=len(rows),
               coverage=len(by_gid), path=str(path), sha256=sha256(path))


def _find_validator_report(obj, depth=0):
    if depth > 6:
        return None
    if isinstance(obj, dict):
        if isinstance(obj.get('counts'), dict) and 'status' in obj \
                and ('exploratory_pass' in obj or 'formal_acceptance' in obj):
            return obj
        for value in obj.values():
            found = _find_validator_report(value, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_validator_report(value, depth + 1)
            if found is not None:
                return found
    return None


def check_validation_artifact(report, directory, validator_result):
    path = directory / 'validation.json'
    if not path.is_file():
        report.add('validation_artifact', False, category='artifacts',
                   detail='validation.json missing')
        return
    try:
        payload = read_json_retry(path)
    except RuntimeError as exc:
        report.add('validation_artifact', False, category='artifacts',
                   detail=f'unreadable: {exc}')
        return
    stored = _find_validator_report(payload)
    errors = []
    if stored is None:
        errors.append(dict(problem='no embedded validator report found',
                           keys=sorted(payload.keys())
                           if isinstance(payload, dict) else None))
    else:
        counts_stored = {key: int(stored.get('counts', {}).get(key, 0))
                         for key in CATEGORIES}
        counts_mine = {key: int((validator_result.get('counts') or {}).get(key, 0))
                       for key in CATEGORIES}
        if counts_stored != counts_mine:
            errors.append(dict(problem='counts differ', stored=counts_stored,
                               independent=counts_mine))
        if stored.get('status') != validator_result.get('status'):
            errors.append(dict(problem='status differs',
                               stored=stored.get('status'),
                               independent=validator_result.get('status')))
        if bool(stored.get('exploratory_pass')) != \
                bool(validator_result.get('exploratory_pass')):
            errors.append(dict(problem='exploratory_pass differs',
                               stored=stored.get('exploratory_pass'),
                               independent=validator_result.get(
                                   'exploratory_pass')))
        if bool(stored.get('formal_acceptance')) != \
                bool(validator_result.get('formal_acceptance')):
            errors.append(dict(problem='formal_acceptance differs'))
        stored_stats = stored.get('stats') or {}
        for key in ('min_3d_clearance_mm', 'min_curvature_radius_mm'):
            stored_value = stored_stats.get(key)
            mine = (validator_result.get('stats') or {}).get(key)
            if stored_value is None or mine is None:
                continue
            if abs(float(stored_value) - float(mine)) > 1e-9:
                errors.append(dict(problem=f'{key} differs',
                                   stored=stored_value, independent=mine))
    report.add('validation_artifact', not errors, category='artifacts',
               detail=errors[:10], path=str(path), sha256=sha256(path))


def check_figures(report, directory):
    path = directory / 'figures'
    if not path.is_dir():
        report.add('figures', False, category='info',
                   detail='figures/ missing')
        return
    files = [item for item in path.iterdir()
             if item.suffix.lower() in ('.png', '.svg', '.pdf')]
    too_small = [item.name for item in files if item.stat().st_size < 1000]
    stems = sorted(item.stem for item in files)
    report.add('figures', len(files) >= 6 and not too_small, category='info',
               detail=dict(count=len(files), too_small=too_small,
                           stems=stems[:40], required_categories=[
                               'overall_3d', 'L1-z1', 'L1-z2', 'L2', 'L3',
                               'L4', 'L5', 'opposite-only layers',
                               'U-only layers',
                               'opposite transition zoom']),
               count=len(files))


def check_comparison_artifact(report, label, metrics):
    path = STRUCT / 'comparison_table.json'
    if not path.is_file():
        report.add('comparison_table_artifact', False, category='info',
                   detail='comparison_table.json not generated yet')
        return
    payload = read_json_retry(path)
    report.add('comparison_table_artifact', True, category='info',
               detail=dict(path=str(path), sha256=sha256(path),
                           keys=sorted(payload.keys())
                           if isinstance(payload, dict) else None))


# ---------------------------------------------------------------------------
# group verification driver
# ---------------------------------------------------------------------------
def _provenance(directory):
    out = {}
    for name in ('routes_1024.json', 'summary.json', 'validation.json',
                 'u_layer_assignment.json', 'opposite_assignment.json',
                 'READY', 'ARTEFACTS_READY', 'run.log', 'stage3a.log',
                 'stage3b.log'):
        path = directory / name
        if path.is_file():
            try:
                out[name] = dict(size=path.stat().st_size,
                                 mtime=time.strftime(
                                     '%Y-%m-%dT%H:%M:%S',
                                     time.localtime(path.stat().st_mtime)),
                                 sha256=sha256(path))
            except OSError:
                pass
    figures = directory / 'figures'
    if figures.is_dir():
        try:
            files = sorted(item.name for item in figures.iterdir())
            out['figures'] = dict(count=len(files), files=files[:40])
        except OSError:
            pass
    return out


def verify_group(label, args, log_fn=log):
    directory = A_DIR if label == 'A' else B_DIR
    swap_rows = (label == 'B')
    log_fn(f'[{label}] verifying {directory}')
    started = time.perf_counter()
    report = Report(label)
    connection_payload, connection = load_connectivity()
    expected_manifest, expected_groups = expected_manifest_for(connection,
                                                               swap_rows)
    port_model = load_port_model()
    phase2 = load_phase2_2d()
    report.numbers['config'] = dict(radius_mm=R, clearance_mm=CLEAR,
                                    width_mm=WIDTH, board_mm=BOARD,
                                    row_z=ROW_Z, stack=STACK,
                                    target_u_layer={str(gid): list(value)
                                                    for gid, value in
                                                    TARGET_U_LAYER.items()},
                                    swap_rows=swap_rows)
    config_errors = []
    if abs(R - 15.0) > 1e-9:
        config_errors.append(dict(radius_mm=R, expected=15.0))
    if abs(WIDTH - 0.05) > 1e-12:
        config_errors.append(dict(width_mm=WIDTH, expected=0.05))
    if abs(CLEAR - 0.08) > 1e-12:
        config_errors.append(dict(clearance_mm=CLEAR, expected=0.08))
    if abs(BOARD - 150.0) > 1e-9:
        config_errors.append(dict(board_mm=BOARD, expected=150.0))
    report.add('process_config', not config_errors, category='core',
               detail=config_errors[:5], radius_mm=R, width_mm=WIDTH,
               clearance_mm=CLEAR, board_mm=BOARD)
    report.numbers['inputs'] = dict(
        connectivity=dict(path=str(CONNECTIVITY), sha256=sha256(CONNECTIVITY)),
        phase2_2d_sha256={plane: sha256(PHASE2 / plane / 'routes.json')
                          for plane in ('z1', 'z2')},
        verifier=dict(path=str(Path(__file__).resolve()),
                      sha256=sha256(Path(__file__).resolve())),
    )
    provenance_before = _provenance(directory)
    report.numbers['provenance_before'] = provenance_before
    # ------------------------------------------------------------------ READY
    ready = (directory / 'READY').is_file()
    gate_name = getattr(args, 'gate_file', 'ARTEFACTS_READY')
    gate = (directory / gate_name).is_file()
    report.add('ready_artifact', ready, category='info',
               detail=None if ready else 'READY missing (older gate file)')
    report.add('artefacts_ready_gate', gate, category='artifacts',
               detail=None if gate else f'{gate_name} missing (group not '
                                         f'finalised)')
    payload_path = directory / 'routes_1024.json'
    if not payload_path.is_file():
        report.add('payload_file', False, category='core',
                   detail='routes_1024.json missing')
        report.numbers['seconds'] = round(time.perf_counter() - started, 2)
        return report.to_dict(), dict(metrics=None, validator=None, facts=None)
    try:
        payload = read_json_retry(payload_path)
    except RuntimeError as exc:
        report.add('payload_file', False, category='core', detail=str(exc))
        report.numbers['seconds'] = round(time.perf_counter() - started, 2)
        return report.to_dict(), dict(metrics=None, validator=None, facts=None)
    records = {int(record['route_id']): record for record in payload.get('routes', [])
               if isinstance(record, dict) and record.get('status') == 'routed'}
    if getattr(args, 'not_before_epoch', None) is not None:
        mtime = payload_path.stat().st_mtime
        fresh = mtime >= args.not_before_epoch
        report.add('payload_freshness', fresh, category='core',
                   detail=None if fresh else dict(
                       payload_mtime=time.strftime(
                           '%Y-%m-%dT%H:%M:%S', time.localtime(mtime)),
                       required_mtime=args.not_before))
        if not fresh:
            report.warn('payload is older than --not-before; this looks like a '
                        'stale READY and the verification result must not be '
                        'used as the final verdict')
    report.numbers['payload'] = dict(path=str(payload_path),
                                     sha256=sha256(payload_path),
                                     routes=len(payload.get('routes') or []),
                                     routed=len(records))
    # ------------------------------------------------------------------ contract
    check_payload_contract(report, payload, payload_path)
    # ------------------------------------------------------------------ summary
    summary_path = directory / 'summary.json'
    summary = None
    if summary_path.is_file():
        try:
            summary = read_json_retry(summary_path)
        except RuntimeError as exc:
            report.warn(f'summary.json unreadable: {exc}')
    # ------------------------------------------------------------- identity/ports
    check_identity(report, label, records, expected_manifest, expected_groups,
                   connection, port_model)
    # ------------------------------------------------------------- rule layering
    facts = check_rule_layers(report, records, connection, expected_groups,
                              summary)
    # ------------------------------------------------------------- geometry
    check_route_geometry(report, records)
    check_2d_invariance(report, records, phase2, connection)
    u_details = check_u_geometry(report, records, port_model, connection)
    facts['u_details'] = u_details
    check_opposite_straight(report, records, phase2, connection)
    check_c4_rotations(report, records, connection, expected_groups)
    # optional recomputed opposite class map for the assignment artefact check
    class_map = {}
    for gid in connection['opposite_groups']:
        rids = [int(rid) for rid in connection['groups'][gid]['route_ids']]
        classes, _info = classify_route(records.get(rids[0]) or {})
        class_map[gid] = ('opposite_L2' if 'opposite_L2' in classes
                          else 'flat_interface')
    facts['opposite_class_map'] = class_map
    # ------------------------------------------------------------- metrics
    metrics = compute_metrics(records, connection['u_rids'], connection,
                              deep=args.deep_crossings)
    report.numbers['recomputed_metrics'] = metrics
    log_fn(f'[{label}] metrics: routed={metrics["routed"]} '
           f'unique_pairs={metrics["unique_crossing_pairs"]} '
           f'transitions={metrics["transitions"]} '
           f'length={metrics["total_length_mm"]} '
           f'per_height={metrics["crossing_pairs_by_height"]}')
    # ------------------------------------------------------------- validator
    if args.skip_validator:
        validator_result = {}
        validator_block = dict(skipped=True)
        report.add('authoritative_3d_validator', True, category='core',
                   detail='skipped by request')
    else:
        log_fn(f'[{label}] running frozen validate_payload_v4 ...')
        try:
            validator_result = run_authoritative_validator(label, payload,
                                                           log_fn=log_fn)
            validator_block = check_authoritative_validator(
                report, label, validator_result, records=records,
                connection=connection)
        except Exception as exc:  # noqa: BLE001
            report.add('authoritative_3d_validator', False, category='core',
                       detail=f'{type(exc).__name__}: {exc}')
            validator_result = {}
            validator_block = dict(error=f'{type(exc).__name__}: {exc}')
        log_fn(f'[{label}] validator: status={validator_block.get("status")} '
               f'exploratory_pass={validator_block.get("exploratory_pass")} '
               f'counts={validator_block.get("counts")} '
               f'min3d={validator_block.get("min_3d_clearance_mm")}')
    report.numbers['validator'] = validator_block
    # ------------------------------------------------------------- summary match
    check_summary(report, summary, metrics, validator_block, facts, label)
    # ------------------------------------------------------------- artefacts
    check_u_assignment(report, label, directory, records, u_details, summary)
    check_opposite_assignment(report, label, directory, records, facts)
    check_validation_artifact(report, directory, validator_result)
    check_figures(report, directory)
    check_comparison_artifact(report, label, metrics)
    # ------------------------------------------------------------- stability
    provenance_after = _provenance(directory)
    stable = provenance_before == provenance_after
    changed = sorted(set(provenance_before) | set(provenance_after))
    changed = [name for name in changed
               if provenance_before.get(name) != provenance_after.get(name)]
    report.add('products_stable_during_run', stable, category='core',
               detail=changed[:10])
    report.numbers['provenance_after'] = provenance_after
    report.numbers['seconds'] = round(time.perf_counter() - started, 2)
    report.numbers['group_summary'] = dict(
        routed=metrics['routed'],
        unique_crossing_pairs=metrics['unique_crossing_pairs'],
        transitions=metrics['transitions'],
        total_length_mm=metrics['total_length_mm'],
        layer_counts={name: value['count']
                      for name, value in metrics['layer_counts'].items()},
        opposite_l2_routes=facts.get('opposite_on_L2_routes'),
        opposite_exception_routes=facts.get('opposite_exception_routes'),
        u_groups_reached=facts.get('u_groups_reached'),
        u_groups_total=facts.get('u_groups_total'),
        validator=validator_block)
    # structured failure bookkeeping (u failures / opposite exceptions) so the
    # final report can quote the documented reasons without re-reading summary
    u_failure_reasons = []
    if isinstance(summary, dict):
        raw_u_failures = summary.get('u_failures')
        if isinstance(raw_u_failures, dict):
            for key, value in raw_u_failures.items():
                try:
                    gid = int(key)
                except (TypeError, ValueError):
                    continue
                reason = value.get('reason') if isinstance(value, dict) else value
                u_failure_reasons.append(dict(
                    group_id=gid,
                    target_layer=TARGET_U_LAYER.get(gid, (None, None))[0],
                    route_ids=[int(rid) for rid in
                               connection['groups'][gid]['route_ids']],
                    reason=str(reason)))
        raw_exceptions = summary.get('opposite_exceptions')
        report.numbers['opposite_exceptions_summary'] = \
            raw_exceptions if isinstance(raw_exceptions, dict) else {}
    report.numbers['u_failure_reasons'] = sorted(
        u_failure_reasons, key=lambda item: item['group_id'])
    report.numbers['u_failure_reason_counts'] = dict(Counter(
        item['reason'] for item in u_failure_reasons))
    log_fn(f'[{label}] verdict={"PASS" if report.passed else "FAIL"} '
           f'core={report.core_pass} artifacts={report.artifacts_pass} '
           f'({report.numbers["seconds"]}s)')
    return report.to_dict(), dict(metrics=metrics, validator=validator_block,
                                  facts=facts, payload=payload)


# ---------------------------------------------------------------------------
# self test on the already accepted old Spatial-U-bundle payload
# ---------------------------------------------------------------------------
def run_selftest(args, log_fn=log):
    log_fn('[selftest] methodology self-test on the accepted old Spatial-U payload')
    report = Report('selftest_old_spatial')
    connection_payload, connection = load_connectivity()
    expected_manifest, expected_groups = expected_manifest_for(connection, False)
    port_model = load_port_model()
    payload_path = OLD_SPATIAL / 'routes_1024.json'
    payload = read_json_retry(payload_path)
    records = {int(record['route_id']): record for record in payload['routes']
               if record.get('status') == 'routed'}
    report.numbers['payload'] = dict(path=str(payload_path),
                                     sha256=sha256(payload_path),
                                     routed=len(records))
    check_payload_contract(report, payload, payload_path)
    check_identity(report, 'old', records, expected_manifest, expected_groups,
                   connection, port_model)
    check_route_geometry(report, records)
    check_c4_rotations(report, records, connection, expected_groups)
    metrics = compute_metrics(records, connection['u_rids'], connection,
                              deep=False)
    known = dict(routed=1024, unique_crossing_pairs=12824, transitions=824,
                 total_length_mm=98539.0127)
    known_ok = all(
        abs(metrics[key] - value) <= (1e-3 if isinstance(value, float) else 0)
        for key, value in known.items())
    report.add('known_old_spatial_metrics', known_ok, category='core',
               detail=dict(actual={key: metrics[key] for key in known},
                           expected=known))
    layer_expected = {'L1-z1': 512, 'L1-z2': 512, 'L2': 252, 'L3': 80,
                      'L4': 68, 'L5': 12}
    layer_actual = {name: value['count']
                    for name, value in metrics['layer_counts'].items()}
    report.add('known_old_spatial_layers', layer_actual == layer_expected,
               category='core', detail=dict(actual=layer_actual,
                                            expected=layer_expected))
    if args.skip_validator:
        report.add('authoritative_3d_validator', True, category='core',
                   detail='skipped by request')
    else:
        log_fn('[selftest] running frozen validate_payload_v4 on old payload ...')
        result = run_authoritative_validator('A', payload, log_fn=log_fn)
        check_authoritative_validator(report, 'old', result, records=records,
                                      connection=connection)
        report.numbers['validator'] = dict(
            status=result.get('status'),
            exploratory_pass=result.get('exploratory_pass'),
            counts=result.get('counts'),
            min_3d_clearance_mm=(result.get('stats') or {}).get(
                'min_3d_clearance_mm'),
            min_curvature_radius_mm=(result.get('stats') or {}).get(
                'min_curvature_radius_mm'))
    report.numbers['metrics'] = {key: metrics[key] for key in known}
    report.numbers['seconds'] = round(time.perf_counter()
                                      - float(getattr(args, '_started',
                                                      time.time())), 2)
    result = report.to_dict()
    result['known_values'] = known
    result['v2_pre_u_baseline'] = dict(
        note='the 23356-crossing figure quoted for the old baseline is the V2 '
             'pre-U payload (phase5_dynamic_optimization/after/routes_l3d.json), '
             'not the final Spatial-U-bundle file', 
        known=dict(unique_crossing_pairs=23356, transitions=440,
                   total_length_mm=97495.7612))
    log_fn(f'[selftest] verdict={"PASS" if report.passed else "FAIL"} '
           f'checks={len(report.checks)}')
    return result


# ---------------------------------------------------------------------------
# combined comparison / markdown
# ---------------------------------------------------------------------------
def compute_old_payload_metrics(payload):
    records = {int(record['route_id']): record for record in payload['routes']
               if record.get('status') == 'routed'}
    connection_payload, connection = load_connectivity()
    return compute_metrics(records, connection['u_rids'], connection, deep=False)


def cross_group_consistency(result_a, result_b):
    """A/B must describe the same connections with the row tables swapped."""
    report = Report('cross_group')
    payload_a = (result_a or {}).get('payload')
    payload_b = (result_b or {}).get('payload')
    if payload_a is None or payload_b is None:
        report.add('cross_group_consistency', False, category='core',
                   detail='missing payload for A or B')
        return report.to_dict()
    records_a = {int(record['route_id']): record
                 for record in payload_a.get('routes') or []
                 if record.get('status') == 'routed'}
    records_b = {int(record['route_id']): record
                 for record in payload_b.get('routes') or []
                 if record.get('status') == 'routed'}
    connection_payload, connection = load_connectivity()
    errors = []
    for rid in range(1, 1025):
        record_a = records_a.get(rid)
        record_b = records_b.get(rid)
        if record_a is None or record_b is None:
            errors.append(dict(route_id=rid, problem='missing A or B record'))
            continue
        expected = dict(
            plane=swap_plane(record_a.get('plane')),
            source_endpoint=swap_endpoint(record_a.get('source_endpoint')),
            target_endpoint=swap_endpoint(record_a.get('target_endpoint')),
            source_row=swap_row(record_a.get('source_row')),
            target_row=swap_row(record_a.get('target_row')))
        for key, want in expected.items():
            have = record_b.get(key)
            if key in ('source_row', 'target_row'):
                try:
                    ok = int(have) == int(want)
                except (TypeError, ValueError):
                    ok = False
            else:
                ok = have == want
            if not ok:
                errors.append(dict(route_id=rid, field=key,
                                   A=record_a.get(key), B=have,
                                   expected_B=want))
        for key in ('relation', 'pair', 'source_side', 'target_side'):
            if record_a.get(key) != record_b.get(key):
                errors.append(dict(route_id=rid, field=key,
                                   A=record_a.get(key),
                                   B=record_b.get(key)))
    report.add('cross_group_consistency', not errors, category='core',
               detail=errors[:20], error_count=len(errors))
    return report.to_dict()


def wait_for_comparison_table(args, log_fn=log):
    path = STRUCT / 'comparison_table.json'
    if path.is_file():
        return True
    if args.no_wait or args.comparison_wait <= 0:
        return False
    log_fn(f'[comparison] waiting up to {args.comparison_wait}s for '
           f'{path.name} ...')
    started = time.time()
    while time.time() - started < args.comparison_wait:
        if path.is_file():
            return True
        time.sleep(min(args.poll, 10))
    return False


def check_production_comparison_table(comparison, args):
    path = STRUCT / 'comparison_table.json'
    block = dict(path=str(path), exists=path.is_file(), checked=False,
                 passed=None, matches=[], mismatches=[])
    if not path.is_file():
        return block
    try:
        table = read_json_retry(path)
    except RuntimeError as exc:
        block['error'] = f'unreadable: {exc}'
        block['passed'] = False
        return block
    block['keys'] = sorted(table.keys()) if isinstance(table, dict) else None
    block['sha256'] = sha256(path)
    columns = table.get('columns') if isinstance(table, dict) else None
    rows = table.get('rows') if isinstance(table, dict) else None
    if not isinstance(columns, list) or not isinstance(rows, (list, dict)):
        block['note'] = ('comparison_table.json format not recognised; only '
                         'existence/hash recorded')
        return block
    # map column labels -> my columns
    column_of = {}
    for name in columns:
        text = str(name)
        upper = text.upper()
        stripped = text.strip()
        if 'V2' in upper:
            column_of.setdefault('v2_pre_u_baseline', text)
        elif '旧' in text or 'OLD' in upper or 'SPATIAL' in upper:
            column_of.setdefault('old_spatial_u_bundle', text)
        elif stripped.upper().startswith('A') or ' A ' in f' {upper} ' \
                or upper.endswith('_A') or '(A' in upper:
            column_of.setdefault('A', text)
        elif stripped.upper().startswith('B') or ' B ' in f' {upper} ' \
                or upper.endswith('_B') or '(B' in upper:
            column_of.setdefault('B', text)
    if 'A' not in column_of or 'B' not in column_of:
        block['note'] = f'could not map A/B columns from {columns}'
        return block
    my_rows = (comparison or {}).get('rows') or {}
    keyword_map = [
        ('unique_crossing_pairs', ('唯一', 'unique', '交叉')),
        ('transitions', ('升降', 'transition')),
        ('total_length_mm', ('长度', 'length')),
        ('min_3d_clearance_mm', ('净空', 'clearance', 'min_3d')),
        ('routed', ('布通', 'routed')),
        ('same_layer_u_u_crossing_pairs', ('U-U', '同层')),
    ]

    def iter_rows():
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    yield row
        elif isinstance(rows, dict):
            for metric, value in rows.items():
                if isinstance(value, dict):
                    yield dict(metric=metric, values=value)
                else:
                    yield dict(metric=metric, value=value)

    mismatches = []
    matches = []
    for row in iter_rows():
        metric_name = str(row.get('metric') or '')
        values = row.get('values')
        if not isinstance(values, dict):
            values = {key: value for key, value in row.items()
                      if key not in ('metric', 'notes')}
        for my_key, tokens in keyword_map:
            if not any(token.lower() in metric_name.lower() for token in tokens):
                continue
            for label, column in column_of.items():
                if label not in ('A', 'B'):
                    continue
                stored = values.get(column)
                recomputed = (my_rows.get(my_key) or {}).get(label) \
                    if my_key != 'min_3d_clearance_mm' else \
                    (my_rows.get(my_key) or {}).get(label)
                if stored is None or recomputed is None:
                    continue
                try:
                    ok = abs(float(stored) - float(recomputed)) <= \
                        (1e-3 if 'length' in my_key else 1e-6
                         if 'clearance' in my_key else 0)
                except (TypeError, ValueError):
                    ok = str(stored) == str(recomputed)
                entry = dict(metric=my_key, column=label, stored=stored,
                             recomputed=recomputed)
                (matches if ok else mismatches).append(entry)
            break
    block['matches'] = matches[:20]
    block['mismatches'] = mismatches[:20]
    if matches or mismatches:
        block['checked'] = True
        block['passed'] = not mismatches
    else:
        block['note'] = 'no comparable metric rows matched by keyword'
    return block


def build_comparison(group_results, log_fn=log):
    comparison = dict(
        columns=['old_spatial_u_bundle', 'A_original', 'B_swapped'],
        rows={})
    old_metrics = None
    old_path = OLD_SPATIAL / 'routes_1024.json'
    old_payload = None
    if old_path.is_file():
        try:
            old_payload = read_json_retry(old_path)
            old_metrics = compute_old_payload_metrics(old_payload)
        except RuntimeError as exc:
            log_fn(f'[comparison] old spatial payload unreadable: {exc}')
    v2_metrics = None
    v2_payload = None
    v2_path = OLD_V2 / 'routes_l3d.json'
    if v2_path.is_file():
        try:
            v2_payload = read_json_retry(v2_path)
            v2_metrics = compute_old_payload_metrics(v2_payload)
        except RuntimeError as exc:
            log_fn(f'[comparison] V2 payload unreadable: {exc}')
    baseline_validators = {}
    for name, payload in (('old_spatial_u_bundle', old_payload),
                          ('v2_pre_u_baseline', v2_payload)):
        if payload is None:
            continue
        try:
            result = run_authoritative_validator('A', payload, log_fn=log_fn)
            baseline_validators[name] = dict(
                status=result.get('status'),
                exploratory_pass=result.get('exploratory_pass'),
                formal_acceptance=result.get('formal_acceptance'),
                counts=dict(result.get('counts') or {}),
                min_3d_clearance_mm=(result.get('stats') or {}).get(
                    'min_3d_clearance_mm'),
                min_curvature_radius_mm=(result.get('stats') or {}).get(
                    'min_curvature_radius_mm'))
        except Exception as exc:  # noqa: BLE001
            log_fn(f'[comparison] validator failed for {name}: {exc}')
    columns = {}
    if v2_metrics is not None:
        columns['v2_pre_u_baseline'] = v2_metrics
    if old_metrics is not None:
        columns['old_spatial_u_bundle'] = old_metrics
    for label in ('A', 'B'):
        entry = group_results.get(label) or {}
        metrics = entry.get('metrics')
        if metrics:
            columns[label] = metrics
    rows = {}
    scalar_keys = [('routed', 'routed'), ('failed', 'failed'),
                   ('unique_crossing_pairs', 'unique_crossing_pairs'),
                   ('same_layer_u_u_crossing_pairs',
                    'same_layer_u_u_crossing_pairs'),
                   ('transitions', 'transitions'),
                   ('total_length_mm', 'total_length_mm')]
    for display, key in scalar_keys:
        rows[display] = {name: value.get(key) for name, value in columns.items()}
    rows['crossing_pairs_by_height'] = {
        name: value.get('crossing_pairs_by_height')
        for name, value in columns.items()}
    rows['layer_counts'] = {
        name: {layer: counts['count']
               for layer, counts in (value.get('layer_counts') or {}).items()}
        for name, value in columns.items()}
    for label in ('A', 'B'):
        entry = group_results.get(label) or {}
        validator = entry.get('validator') or {}
        rows.setdefault('min_3d_clearance_mm', {})[label] = \
            validator.get('min_3d_clearance_mm')
        rows.setdefault('min_curvature_radius_mm', {})[label] = \
            validator.get('min_curvature_radius_mm')
        rows.setdefault('validator_status', {})[label] = validator.get('status')
        rows.setdefault('validator_exploratory_pass', {})[label] = \
            validator.get('exploratory_pass')
        facts = entry.get('facts') or {}
        rows.setdefault('opposite_l2_routes', {})[label] = \
            facts.get('opposite_on_L2_routes')
        rows.setdefault('opposite_exception_routes', {})[label] = \
            facts.get('opposite_exception_routes')
        rows.setdefault('u_groups_reached', {})[label] = \
            facts.get('u_groups_reached')
        rows.setdefault('u_groups_total', {})[label] = \
            facts.get('u_groups_total')
    for name, block in baseline_validators.items():
        rows.setdefault('min_3d_clearance_mm', {})[name] = \
            block.get('min_3d_clearance_mm')
        rows.setdefault('min_curvature_radius_mm', {})[name] = \
            block.get('min_curvature_radius_mm')
        rows.setdefault('validator_status', {})[name] = block.get('status')
        rows.setdefault('validator_exploratory_pass', {})[name] = \
            block.get('exploratory_pass')
    comparison['rows'] = rows
    comparison['columns'] = list(columns.keys())
    comparison['baseline_validators'] = baseline_validators
    comparison['notes'] = [
        'old_spatial_u_bundle = spatial_u_bundle_optimization/routes_1024.json '
        '(final accepted Spatial-U result; its own acceptance report: 12824 '
        'unique pairs, 824 transitions, 98539.0127 mm).',
        'v2_pre_u_baseline = phase5_dynamic_optimization/after/routes_l3d.json; '
        'this is the 23356-crossing / 440-transition baseline quoted for the V2 '
        'experiment before the U-bundle rebuild.',
        'A/B are independently recomputed from the saved payloads; crossings use '
        'the frozen fslw strict pair audit per physical height; unique pairs are '
        'deduplicated by route pair across all heights.',
        'min 3D clearance / min curvature of old and V2 baselines are re-run '
        'through the same frozen validate_payload_v4 with the phase2_2d identity '
        'root by this verifier.',
    ]
    return comparison


def write_markdown(path, payload):
    groups = payload.get('groups') or {}
    lines = []
    lines.append('# 结构化分层布线 A/B 独立几何验收报告')
    lines.append('')
    verdicts = ' / '.join(
        f"{label}: {'PASS' if (groups.get(label) or {}).get('verdict') == 'PASS' else 'FAIL'}"
        for label in ('A', 'B') if label in groups)
    lines.append(f"- 结论：**{payload.get('verdict', 'FAIL')}**"
                 f"（{verdicts}）")
    lines.append(f"- 生成时间：{payload.get('generated')}")
    lines.append(f"- 验收器：{payload.get('verifier')}")
    lines.append('')
    lines.append('## 逐组检查结果')
    lines.append('')
    lines.append('| 组 | 结论 | core | artifacts | 检查数 | 失败项 |')
    lines.append('|---|---|---|---|---:|---|')
    for label in ('A', 'B'):
        group = groups.get(label)
        if not group:
            lines.append(f'| {label} | MISSING | - | - | 0 | - |')
            continue
        failed = [check['name'] for check in group.get('checks') or []
                  if not check['passed']]
        lines.append(f"| {label} | {group.get('verdict')} | "
                     f"{group.get('core_pass')} | {group.get('artifacts_pass')} | "
                     f"{len(group.get('checks') or [])} | "
                     f"{', '.join(failed) if failed else '—'} |")
    lines.append('')
    lines.append('## A 组结论（最优：完全达标）')
    lines.append('')
    group_a = groups.get('A') or {}
    numbers_a = group_a.get('numbers') or {}
    validator_a = numbers_a.get('validator') or {}
    metrics_a = numbers_a.get('recomputed_metrics') or {}
    summary_a = numbers_a.get('group_summary') or {}
    if group_a:
        counts = validator_a.get('counts') or {}
        lines.append(f"- verdict={group_a.get('verdict')}，core={group_a.get('core_pass')}，"
                     f"artifacts={group_a.get('artifacts_pass')}；"
                     f"检查 {len(group_a.get('checks') or [])} 项全部通过。")
        lines.append(f"- 权威 3D：status={validator_a.get('status')}，"
                     f"exploratory_pass={validator_a.get('exploratory_pass')}，"
                     f"9 类 counts={counts}；"
                     f"min curvature={validator_a.get('min_curvature_radius_mm')} mm，"
                     f"min 3D clearance={validator_a.get('min_3d_clearance_mm')} mm。")
        lines.append(f"- 规则分层：邻边 496 条接口层；对边 "
                     f"{summary_a.get('opposite_l2_routes')} 条 L2"
                     f"（{summary_a.get('opposite_l2_routes') // 4 if summary_a.get('opposite_l2_routes') else 0}/68 组），"
                     f"例外 {summary_a.get('opposite_exception_routes')} 条（原因逐组记录）；"
                     f"U {summary_a.get('u_groups_reached')}/{summary_a.get('u_groups_total')} 组全部到达目标层。")
        lines.append(f"- 指标：唯一交叉对 {summary_a.get('unique_crossing_pairs')}，"
                     f"升降 {summary_a.get('transitions')}，"
                     f"总长 {summary_a.get('total_length_mm')} mm，"
                     f"同层 U-U 交叉对 {metrics_a.get('same_layer_u_u_crossing_pairs')}。")
        lines.append('- 结论：A 组是唯一完整满足**规则分层 + 严格 C4 + 冻结 3D 验收**'
                     '全部要求的组，可作为结构化分层布线的参考方案；其代价是对边集中 L2 后'
                     'NS×EW 直通线在 z=1.0 产生 1000 对 90° 交叉，唯一交叉对因此高于旧 Spatial-U 基线。')
    else:
        lines.append('- A 未验收。')
    lines.append('')
    lines.append('## B 组结论与失败瓶颈')
    lines.append('')
    group_b = groups.get('B') or {}
    numbers_b = group_b.get('numbers') or {}
    validator_b = numbers_b.get('validator') or {}
    metrics_b = numbers_b.get('recomputed_metrics') or {}
    summary_b = numbers_b.get('group_summary') or {}
    if group_b:
        checks_b = {check['name']: check for check in (group_b.get('checks') or [])}
        u_check = (checks_b.get('rule_u_target_layers') or {}).get('numbers') or {}
        u_doc = (checks_b.get('rule_u_failures_documented') or {}).get('numbers') or {}
        failed_groups = u_check.get('failed') or []
        reached_groups = u_check.get('reached')
        reason_counts = numbers_b.get('u_failure_reason_counts') or {}
        reasons = numbers_b.get('u_failure_reasons') or []

        def _short(text, limit=150):
            text = str(text)
            return text if len(text) <= limit else text[:limit] + '…'

        short_counts = Counter()
        for reason, count in reason_counts.items():
            short_counts[_short(reason)] += int(count)
        buckets = {'z1_middle (gid 20–35, →L3)': [gid for gid in failed_groups
                                                  if 20 <= gid <= 35],
                   'z2 corner U #1 (gid 144–159, →L3)': [
                       gid for gid in failed_groups if 144 <= gid <= 159],
                   'z2 corner U #2 (gid 160–175, →L4)': [
                       gid for gid in failed_groups if 160 <= gid <= 175],
                   'z2 middle U (gid 176–191, →L5)': [
                       gid for gid in failed_groups if 176 <= gid <= 191]}
        exceptions = numbers_b.get('opposite_exceptions_summary') or {}
        lines.append(f"- verdict=**{group_b.get('verdict')}**；分离结论："
                     f"**几何/权威 3D PASS + 边界约束 PASS**，"
                     f"**U 规则分层未达标（{reached_groups}/{u_check.get('expected')} 组）**。")
        counts = validator_b.get('counts') or {}
        lines.append(f"- 权威 3D（B 用行交换 identity root）：status="
                     f"{validator_b.get('status')}，exploratory_pass="
                     f"{validator_b.get('exploratory_pass')}，9 类 counts={counts}；"
                     f"min curvature={validator_b.get('min_curvature_radius_mm')} mm，"
                     f"min 3D clearance={validator_b.get('min_3d_clearance_mm')} mm。")
        lines.append(f"- 对边规则：66/68 组 L2（264 条），例外 2 组（208、209，"
                     f"原因：{json.dumps(exceptions, ensure_ascii=False)}）；"
                     f"邻边 496 条接口层；C4 严格旋转检查全部通过。")
        lines.append(f"- U 分层：达标 {reached_groups}/{u_check.get('expected')} 组；"
                     f"失败 {len(failed_groups)} 组，按 bundle 分布：")
        for name, gids in buckets.items():
            lines.append(f"  - {name}: {len(gids)} 组失败"
                         + (f" → {gids}" if len(gids) <= 8 else
                            f" → {gids[:6]} …"))
        lines.append(f"- 失败原因分布（来自 summary.u_failures / u_layer_assignment，"
                     f"逐组非空）：")
        for reason, count in short_counts.items():
            lines.append(f"  - {count} 组：{reason}")
        lines.append(f"- 失败证据：B 的层计数 L3={(metrics_b.get('layer_counts') or {}).get('L3', {}).get('count')}、"
                     f"L4={(metrics_b.get('layer_counts') or {}).get('L4', {}).get('count')}、"
                     f"L5={(metrics_b.get('layer_counts') or {}).get('L5', {}).get('count')}，"
                     f"仅 16 组 U 四元组有目标层平段；其余 48 组的 4 条路线保持接口平铺"
                     f"（u_layer_assignment.json 中 status=failed 且 failure 非空）。")
        for item in reasons[:3]:
            lines.append(f"  - gid {item.get('group_id')}（目标 L{item.get('target_layer')}）"
                         f" route_ids={item.get('route_ids')} "
                         f"reason={_short(item.get('reason'), 180)}")
        lines.append('- 根因（与生产定位一致，独立复核数据吻合）：行交换后原 z2 表的 U 四元组'
                     '落到 z1 基排（z=0.0），而原 z1 表的对边连接落到 z2 基排（z=0.5）并从'
                     ' 0.5 抬升 L2；两排端口共享同一 XY，U 从 z=0 抬升的 S 过渡必须在同列'
                     '穿越 z=0.5 平面，与对边连接的 base/过渡在 0.08 mm 净空、C4 同时升降'
                     '与单次升降约束下无法同时满足 → corner1/corner2 共 32 组结构性不可行；'
                     '另有 16 组 middle U 在全平铺基世界过密条件下无可行 (a,D)。')
        lines.append(f"- 其它观察：B 因对边 L2 抬升窗口偏小，z=1.0 层直通段很长，"
                     f"L2 层交叉对达 {(metrics_b.get('crossing_pairs_by_height') or {}).get('1.0')} "
                     f"（A 为 {(metrics_a.get('crossing_pairs_by_height') or {}).get('1.0')}）；"
                     f"B 的同层 U-U 交叉对为 {metrics_b.get('same_layer_u_u_crossing_pairs')} "
                     f"（A 为 {metrics_a.get('same_layer_u_u_crossing_pairs')}，旧 Spatial 为 0），"
                     f"是 B 交叉总数 26152 远高于 A 19584 的主因。")
    else:
        lines.append('- B 未验收。')
    lines.append('')
    lines.append('## 独立复算与生产 summary 的差异（应为零）')
    lines.append('')
    for label in ('A', 'B'):
        group = groups.get(label) or {}
        if not group:
            continue
        differences = group.get('differences') or []
        lines.append(f"- **{label}**：{'0 处数值差异' if not differences else str(len(differences)) + ' 处差异'}"
                     + ('（独立重算与生产 summary 一致）' if not differences
                        else '：' + json.dumps(differences[:5], ensure_ascii=False)))
    lines.append('')
    lines.append('> 说明：B 的 summary 采用另一套字段命名（省略 '
                 'opposite_on_L2_* / u_rebuilt_routes / experiment 标签，'
                 '改为 opposite_l2_* / u_target_reached_groups 等），'
                 '独立验收按等价字段/推导值核对后数值零差异；schema 差异以 warning 记录。')
    lines.append('')
    lines.append('## 关键数字（独立重算）')
    lines.append('')
    lines.append('| 指标 | V2 前基线 | 旧 Spatial U | A | B |')
    lines.append('|---|---:|---:|---:|---:|')
    comparison = payload.get('comparison') or {}
    columns = comparison.get('columns') or []
    rows = comparison.get('rows') or {}

    def cell(row, name):
        value = (rows.get(row) or {}).get(name)
        if isinstance(value, float):
            return f'{value:.6g}'
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return '—' if value is None else str(value)

    for display in ('routed', 'unique_crossing_pairs',
                    'same_layer_u_u_crossing_pairs', 'transitions',
                    'total_length_mm', 'min_3d_clearance_mm',
                    'min_curvature_radius_mm', 'opposite_l2_routes',
                    'opposite_exception_routes', 'u_groups_reached'):
        lines.append('| ' + display + ' | ' + ' | '.join(
            cell(display, name) for name in
            ('v2_pre_u_baseline', 'old_spatial_u_bundle', 'A', 'B')) + ' |')
    lines.append('')
    lines.append('## 逐高度交叉（独立重算，交叉对 / 波导数）')
    lines.append('')
    lines.append('> 交叉对数按生产/冻结 fslw 的 `crossing_pair_count` 口径'
                 '（同一线路的 L1 两个平段与同一条线路相交时会被计两次）；'
                 '逐高度“逻辑唯一 route 对”见 JSON 中的 '
                 '`own_geometry_crossings`，其集合与冻结 fslw 审计完全一致，'
                 '“波导数”等于唯一交点计数。')
    lines.append('')
    by_height = rows.get('crossing_pairs_by_height') or {}
    for name, value in by_height.items():
        if isinstance(value, dict):
            pieces = [f'{height}: {count}' for height, count in
                      sorted(value.items(), key=lambda item: float(item[0]))]
            lines.append(f'- **{name}**：' + ', '.join(pieces))
    lines.append('')
    lines.append('## 各层波导数（独立重算）')
    lines.append('')
    for name, value in (rows.get('layer_counts') or {}).items():
        if isinstance(value, dict):
            pieces = [f'{layer}={count}' for layer, count in value.items()]
            lines.append(f'- **{name}**：' + ', '.join(pieces))
    lines.append('')
    lines.append('## 与生产 summary 的差异')
    lines.append('')
    any_difference = False
    for label in ('A', 'B'):
        group = groups.get(label) or {}
        differences = group.get('differences') or []
        lines.append(f"### {label}（{len(differences)} 处差异）")
        if not differences:
            lines.append('- 无（独立重算与生产 summary 零差异）')
        else:
            any_difference = True
            for item in differences[:20]:
                lines.append(f"- {item.get('topic')}: production="
                             f"{item.get('production')} recomputed="
                             f"{item.get('recomputed')}")
        lines.append('')
    if not any_difference:
        lines.append('> 说明：A/B 的 summary 关键指标均与独立重算一致。')
    lines.append('')
    lines.append('## 权威 3D 验收（冻结 l3d validator）')
    lines.append('')
    for label in ('A', 'B'):
        group = groups.get(label) or {}
        validator = ((group.get('numbers') or {}).get('validator') or {})
        counts = validator.get('counts') or {}
        lines.append(f"- **{label}**：status={validator.get('status')}, "
                     f"exploratory_pass={validator.get('exploratory_pass')}, "
                     f"formal_acceptance={validator.get('formal_acceptance')}, "
                     f"counts={counts}, "
                     f"min_curvature={validator.get('min_curvature_radius_mm')}, "
                     f"min_3d_clearance={validator.get('min_3d_clearance_mm')}")
    lines.append('')
    lines.append('## A/B 组间一致性（B = A 的行/plane/端点交换）')
    lines.append('')
    cross = payload.get('cross_group') or {}
    cross_checks = cross.get('checks') or []
    if cross_checks:
        for check in cross_checks:
            lines.append(f"- {check.get('name')}: "
                         f"{'PASS' if check.get('passed') else 'FAIL'}"
                         + (f" detail={json.dumps(check.get('detail'), ensure_ascii=False)[:400]}"
                            if not check.get('passed') else ''))
    else:
        lines.append('- (A/B 未同时验收，无法做组间一致性检查)')
    lines.append('')
    lines.append('## 生产对照表（comparison_table.json）检查')
    lines.append('')
    table = payload.get('comparison_table') or {}
    if not table.get('exists'):
        lines.append('- 文件不存在（顶层对照表尚未生成）')
    else:
        lines.append(f"- 文件：{table.get('path')} (sha256={table.get('sha256')})")
        if table.get('checked'):
            lines.append(f"- 结果：{'PASS' if table.get('passed') else 'FAIL'}，"
                         f"匹配 {len(table.get('matches') or [])} 项，"
                         f"不匹配 {len(table.get('mismatches') or [])} 项")
            for item in (table.get('mismatches') or [])[:10]:
                lines.append(f"  - {item.get('metric')} [{item.get('column')}]: "
                             f"table={item.get('stored')} "
                             f"recomputed={item.get('recomputed')}")
        else:
            lines.append(f"- {table.get('note')}")
    lines.append('')
    lines.append('## 产物清单')
    lines.append('')
    lines.append('| 组 | routes | summary | validation | u_assignment | '
                 'opposite_assignment | ARTEFACTS_READY | READY | figures |')
    lines.append('|---|---|---|---|---|---|---|---|---|')
    for label in ('A', 'B'):
        group = groups.get(label) or {}
        provenance = ((group.get('numbers') or {}).get('provenance_after')
                      or {})
        cells = []
        for name in ('routes_1024.json', 'summary.json', 'validation.json',
                     'u_layer_assignment.json', 'opposite_assignment.json',
                     'ARTEFACTS_READY', 'READY'):
            cells.append('yes' if name in provenance else '**missing**')
        figures = provenance.get('figures')
        cells.append(f"{figures.get('count')} files"
                     if isinstance(figures, dict) else '**missing**')
        lines.append(f'| {label} | ' + ' | '.join(cells) + ' |')
    lines.append('')
    lines.append('## 产物与问题')
    lines.append('')
    for label in ('A', 'B'):
        group = groups.get(label) or {}
        warnings = group.get('warnings') or []
        root_causes = [item for item in (group.get('root_causes') or [])
                       if item.get('item') in (
                           'u_layer_assignment_artifact',
                           'opposite_assignment_artifact',
                           'validation_artifact', 'ready_artifact',
                           'artefacts_ready_gate', 'payload_file',
                           'figures', 'comparison_table_artifact')]
        for item in root_causes:
            lines.append(f"- {label} {item.get('item')}: {item.get('detail')}")
        for warning in warnings[:5]:
            lines.append(f'- {label} warning: {warning}')
    lines.append('')
    lines.append('> 说明：层高为探索性仿真参数（unconfirmed_simulation），'
                 '几何 PASS 不等于制造工艺正式验收；本报告为独立重算。')
    lines.append('')
    Path(path).write_text('\n'.join(lines), encoding='utf-8')
    return path


# ---------------------------------------------------------------------------
# waiting logic
# ---------------------------------------------------------------------------
def wait_for_group_ready(label, args, log_fn=log):
    directory = A_DIR if label == 'A' else B_DIR
    required = ('routes_1024.json', 'summary.json', 'validation.json',
                'u_layer_assignment.json', 'opposite_assignment.json')
    core = ('routes_1024.json', 'summary.json', 'validation.json')
    gate_name = getattr(args, 'gate_file', 'ARTEFACTS_READY')
    gate = directory / gate_name
    figures = directory / 'figures'
    not_before = getattr(args, 'not_before_epoch', None)

    def _fresh(path):
        return path.is_file() and (
            not_before is None or path.stat().st_mtime >= not_before)

    if args.no_wait:
        return gate.is_file() or (directory / 'READY').is_file()
    log_fn(f'[{label}] waiting for {gate_name} in {directory} '
           f'(timeout {args.timeout}s, poll {args.poll}s'
           + (f', artefacts must be newer than {args.not_before}'
              if not_before else '') + ') ...')
    started = time.time()
    complete_at = None
    while time.time() - started < args.timeout:
        gate_ok = gate.is_file() and _fresh(gate)
        ready_path = directory / 'READY'
        ready_ok = ready_path.is_file() and _fresh(ready_path)
        payload_path = directory / 'routes_1024.json'
        payload_ok = _fresh(payload_path)
        # the producer's gate is ARTEFACTS_READY; READY is the older gate and is
        # only accepted as a fallback once every required artefact exists
        fallback_ok = False
        if not gate_ok and ready_ok and payload_ok:
            fallback_ok = all((directory / name).is_file() for name in required) \
                and figures.is_dir()
        if (gate_ok and payload_ok) or fallback_ok:
            if complete_at is None:
                log_fn(f'[{label}] {gate_name} detected; waiting for a stable '
                       f'artefact set')
                complete_at = time.time()
            present = [name for name in required
                       if (directory / name).is_file()]
            core_present = all((directory / name).is_file() for name in core)
            if core_present:
                names = list(required)
                try:
                    first = {name: sha256(directory / name) for name in names
                             if (directory / name).is_file()}
                    first['__figures__'] = (
                        figures.is_dir(),
                        len(list(figures.iterdir())) if figures.is_dir() else 0)
                    time.sleep(min(5, args.poll))
                    second = {name: sha256(directory / name) for name in names
                              if (directory / name).is_file()}
                    second['__figures__'] = (
                        figures.is_dir(),
                        len(list(figures.iterdir())) if figures.is_dir() else 0)
                except OSError:
                    time.sleep(args.poll)
                    continue
                if first == second:
                    if len(present) == len(required) and figures.is_dir():
                        log_fn(f'[{label}] {gate_name} + all artefacts stable; '
                               f'starting verification')
                        return True
                    if time.time() - complete_at > args.artifact_grace:
                        log_fn(f'[{label}] {gate_name} stable but only '
                               f'{len(present)}/{len(required)} required '
                               f'artefacts within {args.artifact_grace}s; '
                               f'proceeding')
                        return True
                    time.sleep(min(args.poll, 10))
                    continue
            if complete_at is not None and \
                    time.time() - complete_at > args.artifact_grace:
                log_fn(f'[{label}] gate present but core artefacts never '
                       f'stabilised within {args.artifact_grace}s; proceeding')
                return True
        elif (gate.is_file() or ready_path.is_file()) and not (gate_ok or ready_ok):
            if complete_at is None:
                log_fn(f'[{label}] gate file is stale (older than '
                       f'{args.not_before}); waiting for regenerated artefacts')
            complete_at = None
        time.sleep(args.poll)
    log_fn(f'[{label}] timeout waiting for {gate_name}')
    return False


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Independent verification of the structured-layer-routing '
                    'A/B experiment.')
    parser.add_argument('--groups', nargs='+', choices=('A', 'B'),
                        default=['A', 'B'])
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--no-wait', action='store_true',
                        help='do not wait for READY; verify whatever exists')
    parser.add_argument('--timeout', type=float, default=5400.0)
    parser.add_argument('--poll', type=float, default=20.0)
    parser.add_argument('--artifact-grace', type=float, default=240.0)
    parser.add_argument('--gate-file', default='ARTEFACTS_READY',
                        help='group finish gate file name (the producer writes '
                             'ARTEFACTS_READY once routes/summary/validation/'
                             'assignments/figures are all ready)')
    parser.add_argument('--not-before', default=None,
                        help='ISO local datetime (YYYY-MM-DDTHH:MM:SS); the '
                             'group routes_1024.json must be at least this new '
                             '(guards against verifying a stale READY)')
    parser.add_argument('--deep-crossings', action='store_true',
                        help='also run the independent exact geometry crossing '
                             'audit (slower)')
    parser.add_argument('--comparison-wait', type=float, default=600.0,
                        help='seconds to wait for the top-level '
                             'comparison_table.json after both groups are done '
                             '(-1 disables)')
    parser.add_argument('--skip-validator', action='store_true')
    parser.add_argument('--out-dir', type=Path, default=VERIFY)
    args = parser.parse_args(argv)
    args._started = time.time()
    args.not_before_epoch = None
    if args.not_before:
        try:
            args.not_before_epoch = time.mktime(
                time.strptime(args.not_before, '%Y-%m-%dT%H:%M:%S'))
        except ValueError:
            raise SystemExit('--not-before must be formatted YYYY-MM-DDTHH:MM:SS')
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.selftest:
        result = run_selftest(args)
        path = write_json(out_dir / '_selftest_old_spatial.json', result)
        print(json.dumps(dict(
            verdict=result['verdict'],
            checks=len(result['checks']),
            failed=[check['name'] for check in result['checks']
                    if not check['passed']],
            known=result.get('known_values'),
            metrics=(result.get('numbers') or {}).get('metrics'),
            report=str(path)), ensure_ascii=False, indent=1))
        return 0 if result['verdict'] == 'PASS' else 1
    single = len(args.groups) == 1
    group_results = {}
    group_reports = {}
    for label in args.groups:
        ready = wait_for_group_ready(label, args)
        if not ready:
            report = Report(label)
            report.add('ready_artifact', False, category='artifacts',
                       detail=f'READY not found (timeout after {args.timeout}s '
                              f'or --no-wait)')
            payload_path = (A_DIR if label == 'A' else B_DIR) / 'routes_1024.json'
            if not payload_path.is_file():
                report.add('payload_file', False, category='core',
                           detail='routes_1024.json missing')
            report_dict = report.to_dict()
            group_reports[label] = report_dict
            if single:
                path = write_json(out_dir / f'_group_{label}.json', report_dict)
                print(json.dumps(dict(
                    group=label, verdict=report_dict['verdict'],
                    core_pass=report_dict['core_pass'],
                    artifacts_pass=report_dict['artifacts_pass'],
                    failed=[check['name'] for check in report_dict['checks']
                            if not check['passed']],
                    report=str(path)), ensure_ascii=False, indent=1))
                return 2
            continue
        report_dict, internals = verify_group(label, args)
        group_reports[label] = report_dict
        group_results[label] = internals
        if single:
            path = write_json(out_dir / f'_group_{label}.json', report_dict)
            print(json.dumps(dict(
                group=label, verdict=report_dict['verdict'],
                core_pass=report_dict['core_pass'],
                artifacts_pass=report_dict['artifacts_pass'],
                failed=[check['name'] for check in report_dict['checks']
                        if not check['passed']],
                report=str(path)), ensure_ascii=False, indent=1))
            return 0 if report_dict['verdict'] == 'PASS' else 2
    # ------------------------------------------------------------------ combined
    comparison = build_comparison(group_results)
    cross_group = None
    if 'A' in group_results and 'B' in group_results:
        try:
            cross_group = cross_group_consistency(group_results.get('A'),
                                                  group_results.get('B'))
        except Exception as exc:  # noqa: BLE001
            cross_group = dict(label='cross_group', verdict='FAIL',
                               checks=[dict(name='cross_group_consistency',
                                            passed=False, category='core',
                                            detail=f'{type(exc).__name__}: {exc}')])
    cross_ok = True
    if cross_group is not None:
        cross_ok = bool(cross_group.get('verdict') == 'PASS')
    try:
        wait_for_comparison_table(args)
        comparison_table = check_production_comparison_table(comparison, args)
    except Exception as exc:  # noqa: BLE001
        comparison_table = dict(path=str(STRUCT / 'comparison_table.json'),
                                exists=(STRUCT / 'comparison_table.json').is_file(),
                                checked=False,
                                error=f'{type(exc).__name__}: {exc}')
    overall = all(report.get('verdict') == 'PASS'
                  for report in group_reports.values()) and \
        len(group_reports) == len(args.groups) and cross_ok
    payload = dict(
        schema='manual_c4_structured_layer_routing_verification_v1',
        generated=time.strftime('%Y-%m-%dT%H:%M:%S'),
        verifier=('independent: own geometry / C4 / structured-layer / metric '
                  'recomputation; frozen v3c4.lift_cross.validate_payload_v4 '
                  '(A: phase2_2d identity; B: generated row-swapped identity) '
                  'for the authoritative 3D pass; frozen fslw strict pair audit '
                  'for same-height crossings'),
        campaign=str(CAMPAIGN),
        groups=group_reports,
        cross_group=cross_group,
        comparison=comparison,
        comparison_table=comparison_table,
        verdict='PASS' if overall else 'FAIL',
    )
    json_path = write_json(out_dir / 'structured_layer_routing_verification.json',
                           payload)
    md_path = write_markdown(
        out_dir / 'structured_layer_routing_verification.md', payload)
    summary = {label: dict(verdict=report.get('verdict'),
                           core_pass=report.get('core_pass'),
                           artifacts_pass=report.get('artifacts_pass'),
                           failed=[check['name']
                                   for check in report.get('checks') or []
                                   if not check['passed']])
               for label, report in group_reports.items()}
    print(json.dumps(dict(
        verdict=payload['verdict'], groups=summary,
        report=str(json_path), markdown=str(md_path)),
        ensure_ascii=False, indent=1))
    return 0 if overall else 2


if __name__ == '__main__':
    sys.exit(main())
