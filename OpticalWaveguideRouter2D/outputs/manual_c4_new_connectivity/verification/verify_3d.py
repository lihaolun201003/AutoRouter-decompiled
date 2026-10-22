"""Independent (read-only) 3D verification for the manual-C4 campaign stages 3/4/5.

Stages
------
* phase3: ``phase3_initial_lift``  (crossing-avoidance lift, one layer stack)
* phase4: ``phase4_ablation/{A_0.25mm,B_0.50mm,C_0.75mm,D_1.00mm}``
* phase5: ``phase5_dynamic_optimization`` (after/ routes, before/ baseline, actions)

The verifier is independent of the producer code: it re-reads the phase-2 2D
records, the connection manifest and the authoritative port model, and re-derives
every check itself.  The only reused authorities are the frozen
``four_side_1024.fslw.validate_fslw`` (2D strict pair audit) and
``four_side_1024.l3d.validate_l3d`` (true-3D geometry), both driven with the
phase-2 identity of this campaign.

Checks (per layout)
-------------------
1. payload/identity: 1024 records, routed/failed set unchanged vs phase 2;
   endpoint ids / relation / pair / plane match the manifest;
2. XYZ ports: source/target port xy == port model, z == row height (0.0 / 0.5),
   layer_id == 1, declared start/end z match;
3. XY replay: the 3D route's flat parts are exact sub-chains of the phase-2 2D
   primitive chain and every transition projects onto a straight segment;
4. layer model: L1 flats keep their row z; L2-L5 flats use the configured stack
   heights; exactly one high layer per lifted route, <= 1 climb + <= 1 descent;
5. primitive legality: every arc exactly R=15 (flat arcs and S-curve arcs),
   lines axis-aligned, transition theta/footprint/length formulas;
6. C4 in 3D: each complete quartet's four 3D routes are exact 90 deg rigid
   rotations of each other (z unchanged, direction handled);
7. crossing statistics: unique (route_a, route_b) pairs deduplicated across all
   physical heights, reconciled with summary / crossings_after / before numbers;
8. independent l3d.validate_payload with the campaign identity:
   violations/contract/port/curvature/geometry/same_plane/self-clearance all 0,
   exploratory PASS, min curvature >= 15*(1-1e-3), 2048 ports covered;
9. stage extras: phase4 stack heights per config + ablation table reconciliation,
   phase5 before/after monotone reduction + accepted-action bookkeeping +
   unchanged XY.

Usage::

    python verify_3d.py --stage phase3
    python verify_3d.py --stage phase4
    python verify_3d.py --stage phase5
    python verify_3d.py --stage phase3 --dry    # load-only self test, no heavy audit

Writes only into ``outputs/manual_c4_new_connectivity/verification/``.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
CAMPAIGN = HERE.parents[1]
VERIFY_DIR = HERE.parent
sys.path.insert(0, str(REPO))

from four_side_1024.r15 import profile_r15           # noqa: E402

profile_r15.apply()

from four_side_1024.fslw import ports as FPORTS            # noqa: E402
from four_side_1024.fslw import validate_fslw as FSLW      # noqa: E402

WIDTH_MM = 0.05
RADIUS_MM = 15.0
BOARD_MM = 150.0
CLEARANCE_MM = 0.08
SAGITTA_MM = 0.0005
MIN_CURVATURE_MM = RADIUS_MM * (1.0 - 1e-3)
TOL = 1e-6
PLANES = ('z1', 'z2')
ROW_Z = {'z1': 0.0, 'z2': 0.5}
PHASE4_CONFIGS = {
    'A_0.25mm': [0.75, 1.00, 1.25, 1.50],
    'B_0.50mm': [1.00, 1.50, 2.00, 2.50],
    'C_0.75mm': [1.25, 2.00, 2.75, 3.50],
    'D_1.00mm': [1.50, 2.50, 3.50, 4.50],
}
MEDIUM_050 = [1.0, 1.5, 2.0, 2.5]
EXPECTED_BASELINE_PAIRS = 42584


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def close(value_a, value_b, tol=TOL):
    return abs(float(value_a) - float(value_b)) <= tol


def close_xy(point_a, point_b, tol=TOL):
    return (close(point_a[0], point_b[0], tol)
            and close(point_a[1], point_b[1], tol))


def close_vec3(point_a, point_b, tol=TOL):
    return (close(point_a[0], point_b[0], tol)
            and close(point_a[1], point_b[1], tol)
            and close(point_a[2], point_b[2], tol))


class Report:
    def __init__(self, stage):
        self.stage = stage
        self.checks = {}
        self.numbers = {}
        self.failures = []
        self.warnings = []
        self.started = time.time()

    def add(self, key, passed, detail=None, **numbers):
        entry = dict(passed=bool(passed))
        if detail is not None:
            entry['detail'] = detail
        entry.update(numbers)
        self.checks[key] = entry
        if not passed:
            self.failures.append(key)
        return entry

    def add_advisory(self, key, passed, detail=None, **numbers):
        """Record a check that is reported but does not flip the verdict."""
        entry = self.add(key, True, detail, **numbers)
        entry['passed'] = bool(passed)
        entry['advisory'] = True
        return entry

    def warn(self, message):
        self.warnings.append(str(message))

    def final(self):
        return dict(
            schema='manual_c4_3d_independent_verification_v1',
            verifier='pipeline-analyst (read-only independent verifier)',
            stage=self.stage,
            generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
            passed=not self.failures,
            failed_checks=list(self.failures),
            warnings=self.warnings,
            runtime_seconds=round(time.time() - self.started, 2),
            numbers=self.numbers, checks=self.checks)


# ---------------------------------------------------------------------------
# context: campaign identity / port model / 2D baseline
# ---------------------------------------------------------------------------
class Context:
    def __init__(self, routing_dir):
        self.routing_dir = Path(routing_dir)
        self.manifest = load_json(CAMPAIGN / 'inputs' / 'connectivity_1024.json')
        self.manifest_routes = {int(row['route_id']): row
                                for row in self.manifest['routes']}
        self.groups = [dict(g) for g in self.manifest['groups']]
        self.group_by_id = {int(g['group_id']): g for g in self.groups}
        self.route_group = {}
        for group in self.groups:
            for phase, rid in enumerate(group['route_ids']):
                self.route_group[int(rid)] = (int(group['group_id']), phase)
        self.phase2 = load_json(self.routing_dir / 'routes_1024.json')
        self.phase2_records = {int(r['route_id']): r for r in self.phase2['routes']}
        self.routed_ids = {rid for rid, r in self.phase2_records.items()
                           if r.get('status') == 'routed'}
        self.failed_ids = set(self.phase2_records) - self.routed_ids
        self.endpoints = FPORTS.build_plane_endpoints()
        self._check_manifest()

    def _check_manifest(self):
        assert len(self.manifest_routes) == 1024
        assert len(self.groups) == 256
        for rid, record in self.manifest_routes.items():
            assert record['source_endpoint'] in self.endpoints, rid
            assert record['target_endpoint'] in self.endpoints, rid
            assert self.endpoints[record['source_endpoint']]['plane'] == record['plane']
        for rid in self.phase2_records:
            assert rid in self.manifest_routes

    def identity(self):
        identity = {'available': True, 'error': None, 'planes': {}}
        for plane in PLANES:
            routes = {rid: dict(self.manifest_routes[rid])
                      for rid in self.manifest_routes
                      if self.manifest_routes[rid]['plane'] == plane}
            identity['planes'][plane] = {'routes': routes,
                                         'endpoints': self.endpoints}
        return identity


# ---------------------------------------------------------------------------
# independent 2D chain helpers + 90 deg rotation
# ---------------------------------------------------------------------------
def prim2d_length(prim):
    if prim['kind'] == 'line':
        return math.hypot(float(prim['p1'][0]) - float(prim['p0'][0]),
                          float(prim['p1'][1]) - float(prim['p0'][1]))
    return abs(float(prim['radius']) * float(prim['sweep']))


def prim2d_point(prim, distance):
    if prim['kind'] == 'line':
        x0, y0 = float(prim['p0'][0]), float(prim['p0'][1])
        x1, y1 = float(prim['p1'][0]), float(prim['p1'][1])
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= 1e-18:
            return [x0, y0]
        fraction = max(0.0, min(1.0, float(distance) / length))
        return [x0 + (x1 - x0) * fraction, y0 + (y1 - y0) * fraction]
    radius = float(prim['radius'])
    sweep = float(prim['sweep'])
    start = float(prim['start_angle'])
    sign = 1.0 if sweep >= 0 else -1.0
    angle = start + sign * float(distance) / radius
    return [float(prim['center'][0]) + radius * math.cos(angle),
            float(prim['center'][1]) + radius * math.sin(angle)]


def prim2d_tangent(prim, distance):
    if prim['kind'] == 'line':
        x0, y0 = float(prim['p0'][0]), float(prim['p0'][1])
        x1, y1 = float(prim['p1'][0]), float(prim['p1'][1])
        norm = math.hypot(x1 - x0, y1 - y0)
        return [(x1 - x0) / norm, (y1 - y0) / norm]
    radius = float(prim['radius'])
    sweep = float(prim['sweep'])
    sign = 1.0 if sweep >= 0 else -1.0
    angle = float(prim['start_angle']) + sign * float(distance) / radius
    return [-sign * math.sin(angle), sign * math.cos(angle)]


class Chain2D:
    def __init__(self, primitives):
        self.primitives = primitives
        self.lengths = [prim2d_length(p) for p in primitives]
        self.offsets = []
        total = 0.0
        for length in self.lengths:
            self.offsets.append(total)
            total += length
        self.total = total

    def locate(self, distance):
        distance = max(0.0, min(self.total, float(distance)))
        index = bisect.bisect_right(self.offsets, distance) - 1
        if index < 0:
            index = 0
        if index >= len(self.primitives):
            index = len(self.primitives) - 1
        local = distance - self.offsets[index]
        local = max(0.0, min(self.lengths[index], local))
        return index, local

    def point(self, distance):
        index, local = self.locate(distance)
        return prim2d_point(self.primitives[index], local)

    def tangent(self, distance):
        index, local = self.locate(distance)
        return prim2d_tangent(self.primitives[index], local)

    def primitive_at(self, distance):
        return self.locate(distance)[0]


def rot_point(point, times):
    x, y = float(point[0]), float(point[1])
    for _ in range(int(times) % 4):
        x, y = BOARD_MM - y, x
    return [x, y]


def rot_vec(vector, times):
    """Rotate a *direction vector* by 90 deg about the board centre (no offset)."""
    x, y = float(vector[0]), float(vector[1])
    for _ in range(int(times) % 4):
        x, y = -y, x
    return [x, y]


def rot_chain(primitives, times):
    out = []
    for prim in primitives:
        new = dict(prim)
        new['p0'] = rot_point(prim['p0'], times)
        new['p1'] = rot_point(prim['p1'], times)
        if prim['kind'] == 'arc':
            new['center'] = rot_point(prim['center'], times)
            new['start_angle'] = float(prim['start_angle']) + int(times) * math.pi / 2.0
        out.append(new)
    return out


def reverse_chain(primitives):
    out = []
    for prim in reversed(primitives):
        new = dict(prim)
        new['p0'] = list(prim['p1'])
        new['p1'] = list(prim['p0'])
        if prim['kind'] == 'arc':
            new['start_angle'] = float(prim['start_angle']) + float(prim['sweep'])
            new['sweep'] = -float(prim['sweep'])
        out.append(new)
    return out


def prim_close(prim_a, prim_b, tol=TOL):
    if prim_a.get('kind') != prim_b.get('kind'):
        return False, 'kind'
    if not close_xy(prim_a['p0'], prim_b['p0'], tol):
        return False, 'p0'
    if not close_xy(prim_a['p1'], prim_b['p1'], tol):
        return False, 'p1'
    if prim_a['kind'] == 'arc':
        if not close_xy(prim_a['center'], prim_b['center'], tol):
            return False, 'center'
        if abs(float(prim_a['radius']) - float(prim_b['radius'])) > tol:
            return False, 'radius'
        delta = (float(prim_a['start_angle'])
                 - float(prim_b['start_angle'])) % (2.0 * math.pi)
        if min(delta, 2.0 * math.pi - delta) > tol:
            return False, 'start_angle'
        if abs(float(prim_a['sweep']) - float(prim_b['sweep'])) > tol:
            return False, 'sweep'
    return True, ''


def chain_close(chain_a, chain_b, tol=TOL):
    if len(chain_a) != len(chain_b):
        return False, f'primitive_count {len(chain_a)} != {len(chain_b)}'
    for index, (prim_a, prim_b) in enumerate(zip(chain_a, chain_b)):
        same, where = prim_close(prim_a, prim_b, tol)
        if not same:
            return False, f'primitive {index}: {where}'
    return True, ''


# ---------------------------------------------------------------------------
# 3D route helpers (rotation / reversal / comparison)
# ---------------------------------------------------------------------------
def route_xy_chain(route):
    """Flat primitives only, in part order (used for end-point checks)."""
    prims = []
    for part in route['parts']:
        if part['kind'] == 'flat':
            prims.extend(part['primitives'])
    return prims


def rot_route_parts(parts, times):
    out = []
    for part in parts:
        new = dict(part)
        if part['kind'] == 'flat':
            new['primitives'] = rot_chain(part['primitives'], times)
        else:
            new['start'] = rot_point(part['start'], times)
            new['end'] = rot_point(part['end'], times)
            new['direction'] = rot_vec(part['direction'], times)
        out.append(new)
    return out


def reverse_route_parts(parts):
    out = []
    for part in reversed(parts):
        new = dict(part)
        if part['kind'] == 'flat':
            new['primitives'] = reverse_chain(part['primitives'])
        else:
            new['start'] = list(part['end'])
            new['end'] = list(part['start'])
            new['direction'] = [-float(value) for value in part['direction']]
            new['z0'] = float(part['z1'])
            new['z1'] = float(part['z0'])
            new['dz_mm'] = -float(part['dz_mm'])
            new['from_layer'] = int(part['to_layer'])
            new['to_layer'] = int(part['from_layer'])
        out.append(new)
    return out


def route_endpoints_xy(route):
    parts = route['parts']
    first = next(part for part in parts if part['kind'] == 'flat')
    last = next(part for part in reversed(parts) if part['kind'] == 'flat')
    return (list(first['primitives'][0]['p0']),
            list(last['primitives'][-1]['p1']))


def transition_close(part_a, part_b, tol=TOL):
    for key in ('from_layer', 'to_layer'):
        if int(part_a[key]) != int(part_b[key]):
            return False, key
    for key in ('z0', 'z1', 'footprint_mm', 'length_mm', 'radius_mm', 'theta_rad'):
        if abs(float(part_a[key]) - float(part_b[key])) > tol:
            return False, key
    if not close_xy(part_a['start'], part_b['start'], tol):
        return False, 'start'
    if not close_xy(part_a['end'], part_b['end'], tol):
        return False, 'end'
    if not close_xy(part_a['direction'], part_b['direction'], tol):
        return False, 'direction'
    return True, ''


def parts_close(parts_a, parts_b, tol=TOL):
    if len(parts_a) != len(parts_b):
        return False, f'part_count {len(parts_a)} != {len(parts_b)}'
    for index, (part_a, part_b) in enumerate(zip(parts_a, parts_b)):
        if part_a['kind'] != part_b['kind']:
            return False, f'part {index}: kind'
        if part_a['kind'] == 'flat':
            if int(part_a['layer_id']) != int(part_b['layer_id']):
                return False, f'part {index}: layer_id'
            if abs(float(part_a['z_mm']) - float(part_b['z_mm'])) > tol:
                return False, f'part {index}: z_mm'
            same, where = chain_close(part_a['primitives'], part_b['primitives'], tol)
            if not same:
                return False, f'part {index}: {where}'
        else:
            same, where = transition_close(part_a, part_b, tol)
            if not same:
                return False, f'part {index}: {where}'
    return True, ''


# ---------------------------------------------------------------------------
# per-layout verification
# ---------------------------------------------------------------------------
def verify_route_geometry(record, chain2d, stack_heights, row_z):
    """XY replay against the phase-2 primitive chain + layer/z model checks."""
    errors = []
    parts = record.get('parts') or []
    if not parts:
        return ['empty parts'], dict(transitions=0, high_layer=None)
    if parts[0]['kind'] != 'flat' or parts[-1]['kind'] != 'flat':
        errors.append('route must start/end on a flat L1 part')
    distance = 0.0
    expected_z = row_z
    transitions = []
    high_layers = []
    saw_high = False
    for part_index, part in enumerate(parts):
        if part['kind'] == 'flat':
            z_mm = float(part['z_mm'])
            layer_id = int(part['layer_id'])
            if layer_id == 1:
                if abs(z_mm - row_z) > 1e-9:
                    errors.append(f'part {part_index}: L1 z {z_mm} != {row_z}')
            else:
                if layer_id not in stack_heights:
                    errors.append(f'part {part_index}: unknown layer {layer_id}')
                elif abs(z_mm - stack_heights[layer_id]) > 1e-9:
                    errors.append(f'part {part_index}: L{layer_id} z {z_mm} != '
                                  f'{stack_heights[layer_id]}')
                high_layers.append(layer_id)
            if abs(z_mm - expected_z) > 1e-9:
                errors.append(f'part {part_index}: z {z_mm} != previous z {expected_z}')
            for prim in part['primitives']:
                length = prim2d_length(prim)
                point = chain2d.point(distance)
                if not close_xy(prim['p0'], point):
                    errors.append(f'part {part_index}: p0 not on 2D path at s={distance:.6f}')
                # Locate the matching 2D primitive.  At a primitive boundary the
                # arc-length lookup may land on the previous or the next primitive
                # depending on 1e-12 level rounding, so probe both sides.
                candidates = []
                for probe in (distance, distance + 1e-7, distance - 1e-7):
                    index, local = chain2d.locate(probe)
                    if all(index != item[0] for item in candidates):
                        candidates.append((index, local))
                base_index, base_local = None, None
                for index, local in candidates:
                    if chain2d.primitives[index]['kind'] == prim['kind']:
                        base_index, base_local = index, local
                        break
                if base_index is None:
                    base_index, base_local = candidates[0]
                    errors.append(f'part {part_index}: primitive kind {prim["kind"]} '
                                  f'!= 2D {chain2d.primitives[base_index]["kind"]}')
                base = chain2d.primitives[base_index]
                base_local = max(0.0, min(chain2d.lengths[base_index], base_local))
                if prim['kind'] == 'line':
                    dx = abs(float(prim['p1'][0]) - float(prim['p0'][0]))
                    dy = abs(float(prim['p1'][1]) - float(prim['p0'][1]))
                    if min(dx, dy) > 1e-9:
                        errors.append(f'part {part_index}: diagonal line')
                    if base['kind'] != 'line':
                        errors.append(f'part {part_index}: line over 2D arc')
                else:
                    radius = float(prim['radius'])
                    if abs(radius - RADIUS_MM) > 1e-9:
                        errors.append(f'part {part_index}: arc radius {radius}')
                    if base['kind'] == 'arc':
                        if abs(float(base['radius']) - radius) > 1e-9:
                            errors.append(f'part {part_index}: arc radius != 2D')
                        if (abs(float(base['center'][0])
                                - float(prim['center'][0])) > TOL
                                or abs(float(base['center'][1])
                                       - float(prim['center'][1])) > TOL):
                            errors.append(f'part {part_index}: arc center != 2D')
                        sign = 1.0 if float(base['sweep']) >= 0 else -1.0
                        expected_angle = (float(base['start_angle'])
                                          + sign * base_local / float(base['radius']))
                        delta = (float(prim['start_angle'])
                                 - expected_angle) % (2.0 * math.pi)
                        if min(delta, 2.0 * math.pi - delta) > TOL:
                            errors.append(f'part {part_index}: arc start_angle != 2D')
                        if abs(float(prim['sweep']) - float(base['sweep'])) > TOL:
                            errors.append(f'part {part_index}: arc sweep != 2D')
                    else:
                        errors.append(f'part {part_index}: arc over 2D line')
                distance += length
                after = chain2d.point(distance)
                if not close_xy(prim['p1'], after):
                    errors.append(f'part {part_index}: p1 not on 2D path at s={distance:.6f}')
        else:
            footprint = float(part['footprint_mm'])
            direction = [float(part['direction'][0]), float(part['direction'][1])]
            norm = math.hypot(direction[0], direction[1])
            if abs(norm - 1.0) > 1e-9:
                errors.append(f'part {part_index}: direction not unit')
            axis_ok = (abs(direction[0]) <= 1e-9 or abs(direction[1]) <= 1e-9)
            if not axis_ok:
                errors.append(f'part {part_index}: transition direction not axis aligned')
            start = chain2d.point(distance)
            tangent = chain2d.tangent(distance)
            if not close_xy(part['start'], start):
                errors.append(f'part {part_index}: transition start not on 2D path')
            if not close_xy(direction, tangent):
                errors.append(f'part {part_index}: transition direction != 2D tangent')
            end_s = distance + footprint
            index_start = chain2d.primitive_at(distance)
            index_end = chain2d.primitive_at(end_s - 1e-9)
            if index_start != index_end:
                errors.append(f'part {part_index}: transition not on one straight segment')
            elif chain2d.primitives[index_start]['kind'] != 'line':
                errors.append(f'part {part_index}: transition starts on an arc')
            if not close_xy(part['end'], chain2d.point(end_s)):
                errors.append(f'part {part_index}: transition end not on 2D path')
            radius = float(part.get('radius_mm', -1))
            if abs(radius - RADIUS_MM) > 1e-9:
                errors.append(f'part {part_index}: transition radius {radius}')
            dz = abs(float(part['z1']) - float(part['z0']))
            theta = math.acos(max(-1.0, min(1.0, 1.0 - dz / (2.0 * RADIUS_MM))))
            if abs(float(part['theta_rad']) - theta) > 1e-6:
                errors.append(f'part {part_index}: theta formula')
            if abs(float(part['footprint_mm']) - 2.0 * RADIUS_MM * math.sin(theta)) > 1e-6:
                errors.append(f'part {part_index}: footprint formula')
            if abs(float(part['length_mm']) - 2.0 * RADIUS_MM * theta) > 1e-6:
                errors.append(f'part {part_index}: transition length formula')
            if abs(float(part['z0']) - expected_z) > 1e-9:
                errors.append(f'part {part_index}: transition z0 != {expected_z}')
            expected_z = float(part['z1'])
            transitions.append(part)
            if len(transitions) == 1:
                saw_high = True
            distance = end_s
    if abs(distance - chain2d.total) > max(1e-6, 1e-9 * chain2d.total):
        errors.append(f'XY replay length {distance:.9f} != 2D {chain2d.total:.9f}')
    if abs(expected_z - row_z) > 1e-9:
        errors.append(f'route does not end at row z ({expected_z} != {row_z})')
    if len(transitions) not in (0, 2):
        errors.append(f'transition count {len(transitions)} not in (0, 2)')
    if len(transitions) == 2:
        first, second = transitions
        if int(first['from_layer']) != 1 or int(second['to_layer']) != 1:
            errors.append('transition sequence is not L1 -> Lk -> L1')
        if int(first['to_layer']) != int(second['from_layer']):
            errors.append('climb/descent layers differ')
        if abs(float(first['z1']) - float(second['z0'])) > 1e-9:
            errors.append('climb end z != descent start z')
    if high_layers and len(set(high_layers)) != 1:
        errors.append(f'multiple high layers {sorted(set(high_layers))}')
    info = dict(transitions=len(transitions),
                high_layer=(high_layers[0] if high_layers else None),
                high_parts=len(high_layers), saw_high=saw_high,
                xy_length_mm=round(chain2d.total, 6))
    return errors, info


def verify_layout_structure(report, label, payload, context, expected_heights):
    """Identity, port, layers, C4-in-3D and XY-replay checks (no heavy audit)."""
    errors = []
    records = {int(r['route_id']): r for r in payload.get('routes') or []}
    if set(records) != set(range(1, 1025)):
        errors.append(f'record ids incomplete: {len(records)}')
    if payload.get('schema') != 'four_side_1024_v2_l3d_routes_v1':
        errors.append(f'schema {payload.get("schema")!r}')
    routed = {rid: r for rid, r in records.items() if r.get('status') == 'routed'}
    failed = {rid: r for rid, r in records.items() if r.get('status') != 'routed'}
    if set(routed) != context.routed_ids:
        errors.append(f'routed set changed: {len(routed)} vs phase2 '
                      f'{len(context.routed_ids)}')
    if set(failed) != context.failed_ids:
        errors.append(f'failed set changed: {len(failed)} vs phase2 {len(context.failed_ids)}')

    # stack heights from the payload
    stack = payload.get('layer_stack') or {}
    heights = stack.get('routing_heights_mm') or {}
    stack_heights = {}
    for layer_id in (2, 3, 4, 5):
        value = heights.get(str(layer_id))
        if value is None:
            errors.append(f'layer stack missing L{layer_id}')
            continue
        stack_heights[layer_id] = float(value)
    if expected_heights is not None:
        expected = {layer_id: float(expected_heights[index])
                    for index, layer_id in enumerate((2, 3, 4, 5))}
        if stack_heights != expected:
            errors.append(f'layer heights {stack_heights} != expected {expected}')
    if stack.get('provenance') not in (None, 'unconfirmed_simulation'):
        report.warn(f'{label}: layer stack provenance {stack.get("provenance")!r}')

    identity_errors, port_errors, replay_errors = [], [], []
    transitions_total, high_layer_hist = 0, Counter()
    lifted_routes = 0
    for rid in sorted(routed):
        record = routed[rid]
        reference = context.manifest_routes.get(rid)
        if reference is None:
            identity_errors.append(f'{rid}: not in manifest')
            continue
        for key in ('plane', 'source_endpoint', 'target_endpoint', 'relation',
                    'source_row', 'target_row', 'pair', 'source_side', 'target_side'):
            got, expected = record.get(key), reference.get(key)
            if key in ('source_row', 'target_row') and got is not None:
                got = int(got)
            if got != expected:
                identity_errors.append(f'{rid}: {key} {got!r} != {expected!r}')
        plane = str(record.get('plane'))
        row_z = ROW_Z.get(plane)
        if row_z is None:
            identity_errors.append(f'{rid}: plane {plane!r}')
            continue
        source_xy = context.endpoints[reference['source_endpoint']]['routing_xy']
        target_xy = context.endpoints[reference['target_endpoint']]['routing_xy']
        source_port = record.get('source_port') or {}
        target_port = record.get('target_port') or {}
        if not close_xy(source_port.get('xy') or [1e9, 1e9], source_xy):
            port_errors.append(f'{rid}: source_port xy')
        if not close_xy(target_port.get('xy') or [1e9, 1e9], target_xy):
            port_errors.append(f'{rid}: target_port xy')
        for name, port in (('source', source_port), ('target', target_port)):
            if abs(float(port.get('z_mm', 1e9)) - row_z) > 1e-9:
                port_errors.append(f'{rid}: {name}_port z')
            if int(port.get('layer_id', -1)) != 1:
                port_errors.append(f'{rid}: {name}_port layer_id')
        if record.get('start_z_mm') is not None and \
                abs(float(record['start_z_mm']) - row_z) > 1e-9:
            port_errors.append(f'{rid}: start_z_mm')
        if record.get('end_z_mm') is not None and \
                abs(float(record['end_z_mm']) - row_z) > 1e-9:
            port_errors.append(f'{rid}: end_z_mm')

        chain2d = Chain2D(context.phase2_records[rid]['primitives'])
        route_errors, info = verify_route_geometry(
            record, chain2d, stack_heights, row_z)
        transitions_total += info['transitions']
        if info['high_layer'] is not None:
            high_layer_hist[info['high_layer']] += 1
        if record.get('n_transitions') is not None and \
                int(record['n_transitions']) != info['transitions']:
            route_errors.append(f'n_transitions {record["n_transitions"]} '
                                f'!= parts {info["transitions"]}')
        if record.get('lifted') is not None and \
                bool(record['lifted']) != (info['transitions'] > 0):
            route_errors.append('lifted flag mismatch')
        if info['transitions'] > 0:
            lifted_routes += 1
            if info['high_parts'] != 1:
                route_errors.append(f'{info["high_parts"]} high flat parts (expected 1)')
            if len(record.get('layer_sequence') or []) not in (3,):
                route_errors.append(f'layer_sequence {record.get("layer_sequence")}')
        replay_errors.extend(f'{rid}: {message}' for message in route_errors)

    report.numbers[f'{label}_layout'] = dict(
        records=len(records), routed=len(routed), failed=len(failed),
        lifted_routes=lifted_routes, transitions=transitions_total,
        high_layers=dict(high_layer_hist), stack_heights_mm=stack_heights)
    report.add(f'{label}_payload_and_identity', not identity_errors
               and len(records) == 1024, identity_errors[:20],
               routed=len(routed), failed=len(failed))
    report.add(f'{label}_xyz_ports', not port_errors, port_errors[:20],
               routed=len(routed))
    report.add(f'{label}_xy_replay_and_layer_model', not replay_errors,
               replay_errors[:20], lifted_routes=lifted_routes,
               transitions=transitions_total)

    # ---- C4 in 3D: four exact rigid 90 deg rotations --------------------
    rotation_errors = []
    rotation_checked = 0
    reversed_count = 0
    for group in context.groups:
        ids = [int(rid) for rid in group['route_ids']]
        if not all(rid in routed for rid in ids):
            continue
        base = routed[ids[0]]
        for phase in (1, 2, 3):
            member = routed[ids[phase]]
            rotated = rot_route_parts(base['parts'], phase)
            base_start, base_end = route_endpoints_xy(dict(parts=rotated))
            member_start, member_end = route_endpoints_xy(member)
            if close_xy(base_start, member_start) and close_xy(base_end, member_end):
                candidate = rotated
            elif close_xy(base_start, member_end) and close_xy(base_end, member_start):
                candidate = reverse_route_parts(rotated)
                reversed_count += 1
            else:
                rotation_errors.append(f'group {group["group_id"]}: phase {phase} '
                                       f'endpoint frame mismatch')
                continue
            same, where = parts_close(candidate, member['parts'])
            rotation_checked += 1
            if not same:
                rotation_errors.append(f'group {group["group_id"]}: phase {phase} {where}')
    report.add(f'{label}_c4_rotations_3d', not rotation_errors,
               rotation_errors[:20], checks=rotation_checked,
               reversed_routes=reversed_count,
               complete_groups=rotation_checked // 3)
    return dict(routed=routed, payload=payload, stack_heights=stack_heights)


# ---------------------------------------------------------------------------
# independent 3D validator with the campaign identity
# ---------------------------------------------------------------------------
def run_l3d_validator(context, payload):
    from four_side_1024.l3d import validate_l3d as L3V
    identity = context.identity()
    L3V._PORT_CACHE['identity'] = identity
    L3V._port_identity = lambda: identity
    report = L3V.validate_payload(payload, allow_exploratory=True)
    return report


def check_l3d_report(report_entry, validator_report):
    counts = dict(validator_report.get('counts') or {})
    stats = validator_report.get('stats') or {}
    checks = validator_report.get('checks') or {}
    route_ports = checks.get('route_ports') or {}
    bad_counts = {key: value for key, value in counts.items() if int(value or 0) != 0}
    curvature = stats.get('min_curvature_radius_mm')
    min_clearance = stats.get('min_3d_clearance_mm')
    passed = (
        bool(validator_report.get('geometry_pass'))
        and bool(validator_report.get('exploratory_pass'))
        and validator_report.get('status') == 'exploratory_only'
        and not bad_counts
        and not validator_report.get('violations')
        and int(route_ports.get('unique_ports_used') or 0) == 2048
        and bool(route_ports.get('ok'))
        and (curvature is None or float(curvature) >= MIN_CURVATURE_MM)
        and (min_clearance is None
             or float(min_clearance) >= CLEARANCE_MM - 1e-7))
    report_entry(passed, dict(counts=counts, status=validator_report.get('status'),
                              geometry_pass=validator_report.get('geometry_pass'),
                              exploratory_pass=validator_report.get('exploratory_pass'),
                              min_curvature_radius_mm=curvature,
                              min_3d_clearance_mm=min_clearance,
                              unique_ports_used=route_ports.get('unique_ports_used'),
                              violations=len(validator_report.get('violations') or [])))
    return dict(passed=passed, counts=counts,
                min_curvature_radius_mm=curvature,
                min_3d_clearance_mm=min_clearance,
                unique_ports_used=route_ports.get('unique_ports_used'),
                status=validator_report.get('status'))


# ---------------------------------------------------------------------------
# crossing statistics (unique route pairs across all physical heights)
# ---------------------------------------------------------------------------
def crossing_statistics(records):
    entries = defaultdict(list)
    for rid, record in records.items():
        for part in record.get('parts') or []:
            if part['kind'] != 'flat':
                continue
            entries[round(float(part['z_mm']), 9)].append(
                (int(rid), [dict(primitive) for primitive in part['primitives']]))
    points_by_height, pairs_by_height = {}, {}
    unique_pairs = set()
    points_total = 0
    for z_mm in sorted(entries):
        prepared = [FSLW.prepare_route(primitives, route_id=rid)
                    for rid, primitives in entries[z_mm]]
        result = FSLW.audit_route_pairs(prepared, clearance=CLEARANCE_MM,
                                        sagitta=SAGITTA_MM, policy='strict')
        points_by_height[str(z_mm)] = int(result['crossing_count'])
        pairs_by_height[str(z_mm)] = int(result['crossing_pair_count'])
        points_total += int(result['crossing_count'])
        for crossing in result['crossings']:
            first, second = int(crossing['route_a']), int(crossing['route_b'])
            unique_pairs.add((min(first, second), max(first, second)))
        if result['violations']:
            raise RuntimeError(f'strict 2D violations at z={z_mm}: '
                               f'{len(result["violations"])}')
    return dict(points_by_height=points_by_height,
                pairs_by_height=pairs_by_height,
                points_total=points_total,
                unique_pairs=len(unique_pairs),
                unique_pair_list=sorted(unique_pairs))


def check_crossings(report, label, recomputed, summary, crossings_after_path=None):
    errors = []
    summary_pairs = summary.get('remaining_unique_crossing_pairs')
    if summary_pairs is None:
        summary_pairs = summary.get('unique_crossing_pairs_after')
    if summary_pairs is not None and int(summary_pairs) != recomputed['unique_pairs']:
        errors.append(f'summary pairs {summary_pairs} != recomputed '
                      f'{recomputed["unique_pairs"]}')
    if crossings_after_path is not None and Path(crossings_after_path).is_file():
        after = load_json(crossings_after_path)
        remaining = after.get('remaining_pairs')
        if remaining is not None:
            if len(remaining) != recomputed['unique_pairs']:
                errors.append(f'crossings_after remaining_pairs {len(remaining)} '
                              f'!= recomputed {recomputed["unique_pairs"]}')
        if after.get('unique_pair_count') is not None and \
                int(after['unique_pair_count']) != recomputed['unique_pairs']:
            errors.append('crossings_after unique_pair_count mismatch')
        if after.get('pair_count_by_height') and \
                {str(k): int(v) for k, v in after['pair_count_by_height'].items()} != \
                recomputed['pairs_by_height']:
            errors.append('crossings_after pair_count_by_height mismatch')
        if after.get('point_count_by_height') and \
                {str(k): int(v) for k, v in after['point_count_by_height'].items()} != \
                recomputed['points_by_height']:
            errors.append('crossings_after point_count_by_height mismatch')
    if summary.get('crossing_pairs_after') is not None:
        # ``crossing_pairs_after`` is the SUM over physical heights (a pair may be
        # counted at more than one height); the deduplicated count is
        # ``remaining_unique_crossing_pairs``.
        pair_sum = sum(int(value) for value in recomputed['pairs_by_height'].values())
        if int(summary['crossing_pairs_after']) != pair_sum:
            errors.append(f'summary crossing_pairs_after '
                          f'{summary["crossing_pairs_after"]} != recomputed '
                          f'per-height pair sum {pair_sum}')
    if summary.get('crossing_points_after') is not None and \
            int(summary['crossing_points_after']) != recomputed['points_total']:
        errors.append(f'summary crossing_points_after '
                      f'{summary["crossing_points_after"]} != recomputed point total '
                      f'{recomputed["points_total"]}')
    report.numbers[f'{label}_crossings'] = {
        key: value for key, value in recomputed.items() if key != 'unique_pair_list'}
    report.add(f'{label}_crossing_statistics', not errors, errors[:20],
               unique_pairs=recomputed['unique_pairs'],
               points_total=recomputed['points_total'],
               pairs_by_height=recomputed['pairs_by_height'])
    return errors


# ---------------------------------------------------------------------------
# lift-plan / validation-artifact / crossing-baseline reconciliation
# ---------------------------------------------------------------------------
SAFE_TRANSITION_MM = math.sqrt(
    max(0.0, 2.0 * RADIUS_MM * (CLEARANCE_MM + 0.03) - (CLEARANCE_MM + 0.03) ** 2))
EXPECTED_BEFORE_PAIRS_BY_HEIGHT = {'0.0': 29376, '0.5': 13208}
EXPECTED_BEFORE_POINTS_BY_HEIGHT = {'0.0': 30608, '0.5': 14992}


def transition_footprint(dz):
    dz = abs(float(dz))
    if dz <= 0.0:
        return 0.0
    theta = math.acos(max(-1.0, min(1.0, 1.0 - dz / (2.0 * RADIUS_MM))))
    return 2.0 * RADIUS_MM * math.sin(theta)


def position_on_curve(primitives, point):
    """Arc-length position of the closest point of ``point`` on a 2D chain."""
    best_distance = float('inf')
    best_s = 0.0
    offset = 0.0
    px, py = float(point[0]), float(point[1])
    for prim in primitives:
        length = prim2d_length(prim)
        if prim['kind'] == 'line':
            x0, y0 = float(prim['p0'][0]), float(prim['p0'][1])
            x1, y1 = float(prim['p1'][0]), float(prim['p1'][1])
            dx, dy = x1 - x0, y1 - y0
            denominator = dx * dx + dy * dy
            t = 0.0 if denominator <= 1e-18 else (
                (px - x0) * dx + (py - y0) * dy) / denominator
            t = max(0.0, min(1.0, t))
            distance = math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))
            if distance < best_distance:
                best_distance = distance
                best_s = offset + t * length
        else:
            cx, cy = float(prim['center'][0]), float(prim['center'][1])
            radius = float(prim['radius'])
            start = float(prim['start_angle'])
            sweep = float(prim['sweep'])
            angle = math.atan2(py - cy, px - cx)
            if sweep >= 0.0:
                delta = (angle - start) % (2.0 * math.pi)
                inside = delta <= sweep + 1e-9
            else:
                delta = (start - angle) % (2.0 * math.pi)
                inside = delta <= -sweep + 1e-9
            local = min(length, delta * radius) if inside else (
                0.0 if delta > abs(sweep) / 2.0 else length)
            point_angle = start + math.copysign(local / radius, sweep)
            qx = cx + radius * math.cos(point_angle)
            qy = cy + radius * math.sin(point_angle)
            distance = math.hypot(px - qx, py - qy)
            if distance < best_distance:
                best_distance = distance
                best_s = offset + local
        offset += length
    return best_s


def check_lift_plans(report, label, layout_dir, context, payload, stack_heights,
                     summary):
    path = Path(layout_dir) / 'lift_plans.json'
    if not path.is_file():
        report.warn(f'{label}: lift_plans.json missing')
        return
    plans = load_json(path)
    lifted_plans = plans.get('lifted') or []
    reverted_plans = plans.get('reverted') or []
    rejected_plans = plans.get('rejected') or []
    routed = {int(r['route_id']): r for r in payload.get('routes') or []
              if r.get('status') == 'routed'}
    errors = []
    seen_groups = set()
    for plan in lifted_plans:
        gid = int(plan['group_id'])
        seen_groups.add(gid)
        group = context.group_by_id.get(gid)
        if group is None:
            errors.append(f'plan {gid}: unknown group')
            continue
        ids = [int(rid) for rid in plan['route_ids']]
        if ids != [int(rid) for rid in group['route_ids']]:
            errors.append(f'plan {gid}: route_ids differ from manifest group')
        layer_id = int(plan['layer_id'])
        layer_z = float(plan['layer_z_mm'])
        if layer_id not in stack_heights or abs(stack_heights[layer_id] - layer_z) > 1e-9:
            errors.append(f'plan {gid}: layer {layer_id} z {layer_z} != stack')
            continue
        rep = ids[0]
        rep_record = routed.get(rep)
        if rep_record is None:
            errors.append(f'plan {gid}: representative {rep} not routed')
            continue
        rep_prims = context.phase2_records[rep]['primitives']
        rep_row_z = ROW_Z[context.phase2_records[rep]['plane']]
        if abs(float(plan['footprint_mm'])
               - transition_footprint(layer_z - rep_row_z)) > 1e-6:
            errors.append(f'plan {gid}: footprint formula')
        transitions = [part for part in rep_record['parts']
                       if part['kind'] == 'transition']
        if len(transitions) != 2:
            errors.append(f'plan {gid}: representative has {len(transitions)} transitions')
        else:
            rise = position_on_curve(rep_prims, transitions[0]['start'])
            fall = position_on_curve(rep_prims, transitions[1]['start'])
            if abs(rise - float(plan['rise_start_mm'])) > 1e-3:
                errors.append(f'plan {gid}: rise position {rise} != '
                              f'{plan["rise_start_mm"]}')
            if abs(fall - float(plan['fall_start_mm'])) > 1e-3:
                errors.append(f'plan {gid}: fall position {fall} != '
                              f'{plan["fall_start_mm"]}')
        for rid in ids:
            record = routed.get(rid)
            if record is None:
                errors.append(f'plan {gid}: member {rid} not routed')
                continue
            transitions = [part for part in record['parts']
                           if part['kind'] == 'transition']
            high_parts = [part for part in record['parts']
                          if part['kind'] == 'flat' and int(part['layer_id']) != 1]
            if len(transitions) != 2 or len(high_parts) != 1:
                errors.append(f'plan {gid}: member {rid} part structure '
                              f'({len(transitions)} transitions, '
                              f'{len(high_parts)} high parts)')
                continue
            if int(high_parts[0]['layer_id']) != layer_id or \
                    abs(float(high_parts[0]['z_mm']) - layer_z) > 1e-9:
                errors.append(f'plan {gid}: member {rid} high layer/z mismatch')
            # elevated stored span (rep coordinates are per-member stored path)
            member_prims = context.phase2_records[rid]['primitives']
            start_s = position_on_curve(member_prims, high_parts[0]['primitives'][0]['p0'])
            end_s = position_on_curve(member_prims,
                                      high_parts[0]['primitives'][-1]['p1'])
            if start_s > end_s:
                start_s, end_s = end_s, start_s
            low, high = start_s + SAFE_TRANSITION_MM, end_s - SAFE_TRANSITION_MM
            if high <= low:
                low, high = start_s, end_s
            expected_span = plan.get('high_spans_mm', {}).get(str(rid))
            if expected_span:
                first = expected_span[0]
                if (abs(float(first[0]) - low) > 2e-3
                        or abs(float(first[1]) - high) > 2e-3):
                    errors.append(f'plan {gid}: member {rid} high span '
                                  f'{[round(low, 4), round(high, 4)]} != '
                                  f'{first}')
    reverted_errors = []
    for plan in reverted_plans:
        gid = int(plan['group_id'])
        group = context.group_by_id.get(gid)
        if group is None:
            reverted_errors.append(f'reverted {gid}: unknown group')
            continue
        for rid in [int(x) for x in group['route_ids']]:
            record = routed.get(rid)
            if record is None:
                continue
            transitions = sum(1 for part in record['parts']
                              if part['kind'] == 'transition')
            if transitions:
                reverted_errors.append(f'reverted {gid}: route {rid} still has '
                                       f'{transitions} transitions')
    counts_errors = []
    if summary.get('lifted_groups') is not None and \
            int(summary['lifted_groups']) != len(lifted_plans):
        counts_errors.append(f'lifted_groups {summary["lifted_groups"]} != '
                             f'{len(lifted_plans)} plans')
    if summary.get('rejected_groups') is not None and \
            int(summary['rejected_groups']) != len(rejected_plans):
        counts_errors.append(f'rejected_groups {summary["rejected_groups"]} != '
                             f'{len(rejected_plans)} plans')
    reverted_ids = [int(value) for value in summary.get('reverted_group_ids') or []]
    if sorted(reverted_ids) != sorted(int(p['group_id']) for p in reverted_plans):
        counts_errors.append('summary reverted ids != lift_plans reverted')
    if seen_groups & {int(p['group_id']) for p in reverted_plans}:
        counts_errors.append('a group is both lifted and reverted')
    report.numbers[f'{label}_lift_plans'] = dict(
        lifted=len(lifted_plans), rejected=len(rejected_plans),
        reverted=len(reverted_plans))
    report.add(f'{label}_lift_plans_consistent',
               not errors and not reverted_errors and not counts_errors,
               (errors + reverted_errors + counts_errors)[:20],
               lifted=len(lifted_plans), rejected=len(rejected_plans),
               reverted=len(reverted_plans))


def check_validation_artifact(report, label, layout_dir, recomputed):
    path = Path(layout_dir) / 'validation.json'
    if not path.is_file():
        report.warn(f'{label}: validation.json missing')
        return
    stored = load_json(path)
    counts = dict(stored.get('counts') or {})
    errors = []
    if stored.get('status') != 'exploratory_only':
        errors.append(f'status {stored.get("status")!r}')
    if stored.get('exploratory_pass') is not True:
        errors.append('exploratory_pass not True')
    if stored.get('geometry_pass') is not True:
        errors.append('geometry_pass not True')
    if stored.get('formal_acceptance') is True:
        errors.append('formal_acceptance must be refused (unconfirmed stack)')
    if any(int(value or 0) != 0 for value in counts.values()):
        errors.append(f'stored counts not zero: {counts}')
    stored_clearance = (stored.get('stats') or {}).get('min_3d_clearance_mm')
    if recomputed.get('min_3d_clearance_mm') is not None and stored_clearance is not None:
        if abs(float(stored_clearance)
               - float(recomputed['min_3d_clearance_mm'])) > 1e-6:
            errors.append('stored/recomputed min_3d_clearance differ')
    report.add(f'{label}_validation_artifact', not errors, errors[:10],
               status=stored.get('status'),
               min_3d_clearance_mm=stored_clearance)


def check_crossings_before(report, label, layout_dir, summary):
    path = Path(layout_dir) / 'crossings_before.json'
    if not path.is_file():
        report.warn(f'{label}: crossings_before.json missing')
        return
    before = load_json(path)
    errors = []
    if int(before.get('pair_count', -1)) != EXPECTED_BASELINE_PAIRS:
        errors.append(f'crossings_before pair_count {before.get("pair_count")} != '
                      f'{EXPECTED_BASELINE_PAIRS}')
    if int(before.get('count', -1)) != sum(EXPECTED_BEFORE_POINTS_BY_HEIGHT.values()):
        errors.append(f'crossings_before point count {before.get("count")}')
    if summary.get('crossing_pairs_before') is not None and \
            int(summary['crossing_pairs_before']) != EXPECTED_BASELINE_PAIRS:
        errors.append('summary crossing_pairs_before != 42584')
    if summary.get('crossing_pairs_before_by_plane') is not None:
        by_plane = {
            str(key): int(value) for key, value in
            summary['crossing_pairs_before_by_plane'].items()}
        if by_plane != EXPECTED_BEFORE_PAIRS_BY_HEIGHT:
            errors.append(f'summary before-by-plane {by_plane}')
    report.add(f'{label}_crossings_before', not errors, errors[:10],
               pair_count=before.get('pair_count'),
               expected=EXPECTED_BASELINE_PAIRS)


# ---------------------------------------------------------------------------
# stage runners
# ---------------------------------------------------------------------------
def verify_layout(report, label, layout_dir, context, expected_heights,
                  heavy=True, crossings_after=True, summary_filename='summary.json',
                  check_plans=True):
    layout_dir = Path(layout_dir)
    payload_path = layout_dir / 'routes_l3d.json'
    if not payload_path.is_file():
        report.add(f'{label}_files_present', False, f'missing {payload_path}')
        return None
    payload = load_json(payload_path)
    context_payload = verify_layout_structure(
        report, label, payload, context, expected_heights)
    if not heavy:
        report.add(f'{label}_heavy_checks_skipped', True, 'dry run')
        return context_payload
    summary_path = layout_dir / summary_filename
    summary = load_json(summary_path) if summary_path.is_file() else {}
    report.numbers[f'{label}_files'] = dict(
        routes_sha256=sha256(payload_path),
        summary_sha256=sha256(summary_path) if summary_path.is_file() else None,
        summary_exists=summary_path.is_file())

    routed = context_payload['routed']
    recomputed = crossing_statistics(routed)
    check_crossings(report, label, recomputed, summary,
                    (layout_dir / 'crossings_after.json') if crossings_after else None)
    report.numbers[f'{label}_crossing_baseline'] = dict(
        expected=EXPECTED_BASELINE_PAIRS,
        reported_before=summary.get('crossing_pairs_before'),
        after=recomputed['unique_pairs'],
        delta=(int(summary.get('crossing_pairs_before'))
               - recomputed['unique_pairs'])
        if summary.get('crossing_pairs_before') is not None else None)
    if summary.get('crossing_pairs_before') is not None:
        lifted_groups = int(summary.get('lifted_groups') or 0)
        if lifted_groups > 0:
            report.add(f'{label}_crossing_reduction',
                       int(summary['crossing_pairs_before']) > recomputed['unique_pairs'],
                       dict(before=summary['crossing_pairs_before'],
                            after=recomputed['unique_pairs'],
                            lifted_groups=lifted_groups))
        else:
            report.add(f'{label}_crossing_reduction', True,
                       'no lifted groups in this layout -> reduction not required',
                       before=summary.get('crossing_pairs_before'),
                       after=recomputed['unique_pairs'])
    check_crossings_before(report, label, layout_dir, summary)

    validator_report = run_l3d_validator(context, payload)
    outcome = check_l3d_report(
        lambda passed, numbers: report.add(f'{label}_l3d_validator', passed,
                                           **numbers),
        validator_report)
    report.numbers[f'{label}_validation'] = outcome
    check_validation_artifact(report, label, layout_dir, outcome)
    if check_plans:
        check_lift_plans(report, label, layout_dir, context, payload,
                         context_payload['stack_heights'], summary)
    return dict(context_payload, summary=summary, recomputed=recomputed,
                validation=outcome)


def stage_phase3(report, args, context):
    root = Path(args.root or (CAMPAIGN / 'phase3_initial_lift'))
    report.numbers['target'] = str(root)
    result = verify_layout(report, 'phase3', root, context, MEDIUM_050,
                           heavy=not args.dry)
    if args.dry or result is None:
        return
    summary = result['summary']
    recomputed = result['recomputed']
    outcome = result['validation']
    errors = []
    if int(summary.get('routed_after', -1)) != len(context.routed_ids):
        errors.append('routed_after')
    if int(summary.get('routed_before', -1)) != len(context.routed_ids):
        errors.append('routed_before')
    lifted_groups = int(summary.get('lifted_groups') or 0)
    lifted_routes = summary.get('lifted_routes')
    if lifted_routes is not None and int(lifted_routes) != 4 * lifted_groups:
        errors.append('lifted_routes != 4 * lifted_groups')
    if lifted_routes is not None and summary.get('transitions') is not None and \
            int(summary['transitions']) != 2 * int(lifted_routes):
        errors.append('transitions != 2 * lifted_routes')
    if int(summary.get('remaining_unique_crossing_pairs', -1)) != \
            recomputed['unique_pairs']:
        errors.append('remaining_unique_crossing_pairs')
    if int(summary.get('crossing_points_after', -1)) != recomputed['points_total']:
        errors.append('crossing_points_after')
    if int(summary.get('crossing_pair_reduction', -1)) != \
            EXPECTED_BASELINE_PAIRS - recomputed['unique_pairs']:
        errors.append('crossing_pair_reduction')
    if summary.get('validation_status') != 'exploratory_only':
        errors.append('validation_status')
    if outcome.get('min_3d_clearance_mm') is not None and \
            summary.get('min_3d_clearance_mm') is not None and \
            abs(float(outcome['min_3d_clearance_mm'])
                - float(summary['min_3d_clearance_mm'])) > 1e-6:
        errors.append('summary min_3d_clearance != independent validator')
    reverted_ids = [int(value) for value in summary.get('reverted_group_ids') or []]
    repair_rounds = summary.get('repair_rounds')
    if reverted_ids and (repair_rounds is None or int(repair_rounds) < 1):
        errors.append('repair_rounds inconsistent with reverted groups')
    report.add('phase3_summary_consistency', not errors, errors[:10],
               routed=summary.get('routed_after'),
               lifted_groups=lifted_groups,
               lifted_routes=lifted_routes,
               transitions=summary.get('transitions'),
               remaining_unique_pairs=recomputed['unique_pairs'],
               repair_rounds=repair_rounds,
               reverted_groups=len(reverted_ids),
               termination=summary.get('termination'))

    checkpoint_path = root / 'checkpoint.json'
    checkpoint_errors = []
    if checkpoint_path.is_file():
        checkpoint = load_json(checkpoint_path)
        if checkpoint.get('pair_count_after') is not None and \
                int(checkpoint['pair_count_after']) != recomputed['unique_pairs']:
            checkpoint_errors.append('checkpoint pair_count_after')
        checkpoint_groups = checkpoint.get('lifted_groups') or []
        if len(checkpoint_groups) != lifted_groups:
            checkpoint_errors.append(f'checkpoint lifted_groups '
                                     f'{len(checkpoint_groups)} != {lifted_groups}')
        if sorted(int(v) for v in checkpoint.get('reverted_group_ids') or []) != \
                sorted(reverted_ids):
            checkpoint_errors.append('checkpoint reverted ids')
        lifted_route_ids = checkpoint.get('lifted_route_ids') or []
        if lifted_routes is not None and len(lifted_route_ids) != int(lifted_routes):
            checkpoint_errors.append('checkpoint lifted_route_ids count')
        report.add('phase3_checkpoint_consistency', not checkpoint_errors,
                   checkpoint_errors[:10],
                   pair_count_after=checkpoint.get('pair_count_after'),
                   lifted_groups=len(checkpoint_groups))
    else:
        report.warn('phase3: checkpoint.json missing')
    checkpoints_dir = root / 'checkpoints'
    if checkpoints_dir.is_dir():
        step_files = sorted(checkpoints_dir.glob('step_*.json'))
        report.add('phase3_step_checkpoints_present',
                   len(step_files) >= lifted_groups,
                   dict(step_checkpoints=len(step_files),
                        lifted_groups=lifted_groups))


def projected_chain(record):
    """Full XY projection of a 3D route (flat prims + transition projections)."""
    primitives = []
    for part in record.get('parts') or []:
        if part['kind'] == 'flat':
            primitives.extend(dict(prim) for prim in part['primitives'])
        else:
            primitives.append(dict(kind='line', p0=list(part['start']),
                                   p1=list(part['end'])))
    return primitives


def chain_signature(primitives, fractions=(0.0, 0.25, 0.5, 0.75, 1.0)):
    chain = Chain2D(primitives)
    samples = tuple((round(point[0], 6), round(point[1], 6))
                    for point in (chain.point(chain.total * fraction)
                                  for fraction in fractions))
    return samples + (round(chain.total, 6),)


def check_cross_config_invariance(report, context, layouts_payloads):
    """Only the layer stack may differ: topology / quartets / XY must be identical."""
    errors = []
    signatures = defaultdict(dict)
    partition = defaultdict(dict)
    for name, payload in layouts_payloads.items():
        records = {int(r['route_id']): r for r in payload.get('routes') or []}
        for rid, record in records.items():
            if record.get('status') != 'routed':
                continue
            signatures[rid][name] = chain_signature(projected_chain(record))
            partition[rid][name] = (record.get('rotation_group_id'),
                                    record.get('rotation_phase'))
    reference_names = sorted(layouts_payloads)
    for rid in sorted(context.routed_ids):
        reference = signatures[rid].get(reference_names[0])
        if reference is None:
            errors.append(f'{rid}: missing in {reference_names[0]}')
            continue
        phase2_signature = chain_signature(
            context.phase2_records[rid]['primitives'])
        if reference != phase2_signature:
            errors.append(f'{rid}: XY projection differs from phase 2')
        for name in reference_names[1:]:
            if signatures[rid].get(name) != reference:
                errors.append(f'{rid}: XY projection differs between '
                              f'{reference_names[0]} and {name}')
        expected_group = context.route_group.get(rid)
        for name in reference_names:
            got = partition[rid].get(name)
            if got != expected_group:
                errors.append(f'{rid}: quartet identity {got} != manifest '
                              f'{expected_group} in {name}')
    report.numbers['phase4_cross_config'] = dict(
        configs=reference_names,
        routes_with_identical_xy=len(context.routed_ids) - len({
            rid for rid in context.routed_ids
            if len(set(signatures[rid].values())) > 1}),
        quartet_partition_identical=not any(
            len(set(partition[rid].values())) > 1 for rid in context.routed_ids))
    report.add('phase4_cross_config_invariance', not errors, errors[:20],
               configs=len(reference_names),
               routed_routes=len(context.routed_ids))


def stage_phase4(report, args, context):
    root = Path(args.root or (CAMPAIGN / 'phase4_ablation'))
    report.numbers['target'] = str(root)
    layouts = {}
    for name, heights in PHASE4_CONFIGS.items():
        config_dir = root / name
        report.numbers[f'config_{name}'] = dict(dir=str(config_dir),
                                                expected_heights=heights)
        result = verify_layout(report, name, config_dir, context, heights,
                               heavy=not args.dry)
        if result is not None:
            layouts[name] = result
    if args.dry:
        return
    check_cross_config_invariance(
        report, context,
        {name: layouts[name]['payload'] for name in layouts})
    # shared baseline + ablation table reconciliation
    table_path = root / 'ablation_table.json'
    if not table_path.is_file():
        report.warn(f'ablation table missing: {table_path}')
        report.add('ablation_table_consistency', True,
                   'ablation_table.json not present -> skipped')
    else:
        table = load_json(table_path)
        errors = []
        rows = {row.get('name'): row for row in table.get('results') or []}
        for name, heights in PHASE4_CONFIGS.items():
            if name not in layouts:
                continue
            row = rows.get(name)
            if row is None:
                errors.append(f'{name}: missing table row')
                continue
            summary = load_json(root / name / 'summary.json')
            recomputed = report.numbers[f'{name}_crossings']
            if int(row.get('remaining_unique_crossing_pairs', -1)) != \
                    recomputed['unique_pairs']:
                errors.append(f'{name}: table remaining pairs')
            if int(row.get('lifted_groups', -1)) != int(summary.get('lifted_groups', -2)):
                errors.append(f'{name}: table lifted groups')
            if int(row.get('routed', -1)) != len(context.routed_ids):
                errors.append(f'{name}: table routed')
            if row.get('validation_status') != 'exploratory_only':
                errors.append(f'{name}: table validation status')
            if row.get('layer_heights_mm') != heights:
                errors.append(f'{name}: table layer heights')
        report.add('ablation_table_consistency', not errors, errors[:20],
                   configs=len(layouts))
    # identical baseline across configs
    baseline_errors = []
    for name in PHASE4_CONFIGS:
        summary_path = root / name / 'summary.json'
        if not summary_path.is_file():
            continue
        summary = load_json(summary_path)
        if summary.get('crossing_pairs_before') is not None and \
                int(summary['crossing_pairs_before']) != EXPECTED_BASELINE_PAIRS:
            baseline_errors.append(f'{name}: crossing_pairs_before '
                                   f'{summary["crossing_pairs_before"]}')
    report.add('phase4_shared_baseline', not baseline_errors, baseline_errors[:10],
               expected_baseline_pairs=EXPECTED_BASELINE_PAIRS)


def stage_phase5(report, args, context):
    root = Path(args.root or (CAMPAIGN / 'phase5_dynamic_optimization'))
    report.numbers['target'] = str(root)
    after_dir = root / 'after'
    before_dir = root / 'before'
    if not after_dir.is_dir():
        report.add('phase5_files_present', False, f'missing {after_dir}')
        return
    before_result = verify_layout(report, 'phase5_before', before_dir, context,
                                  PHASE4_CONFIGS['B_0.50mm'], heavy=not args.dry,
                                  summary_filename='summary.json')
    after_result = verify_layout(report, 'phase5_after', after_dir, context,
                                 PHASE4_CONFIGS['B_0.50mm'], heavy=not args.dry,
                                 summary_filename='summary.json', check_plans=False)
    if args.dry or after_result is None:
        return
    summary_path = root / 'summary.json'
    summary = load_json(summary_path) if summary_path.is_file() else {}
    report.numbers['phase5_summary'] = {key: summary.get(key) for key in
                                        ('routed_before', 'routed_after',
                                         'unique_crossing_pairs_before',
                                         'unique_crossing_pairs_after',
                                         'crossing_reduction',
                                         'single_group_reschedules',
                                         'joint_reschedules',
                                         'recovered_failed_groups',
                                         'lifted_groups_after',
                                         'transitions_after',
                                         'length_delta_mm',
                                         'validation_status')}
    expected_routed = len(context.routed_ids)
    if summary.get('routed_after') is not None and \
            int(summary['routed_after']) != expected_routed:
        report.add('phase5_summary_routed_after', False,
                   dict(reported=summary['routed_after'], expected=expected_routed))
    else:
        report.add('phase5_summary_routed_after', True,
                   dict(reported=summary.get('routed_after')))
    # ``dynamic_opt.summary`` used to hard-code routed_before=1020 (V4 leftover);
    # the producer has been fixed, so this is now a hard requirement.
    if summary.get('routed_before') is not None and \
            int(summary['routed_before']) != expected_routed:
        report.add('phase5_summary_routed_before', False,
                   dict(reported=summary['routed_before'],
                        expected=expected_routed))
    else:
        report.add('phase5_summary_routed_before', True,
                   dict(reported=summary.get('routed_before')))
    before_cross_summary = report.numbers.get('phase5_before_crossings', {}).get('unique_pairs')
    after_cross_summary = report.numbers.get('phase5_after_crossings', {}).get('unique_pairs')
    crossing_errors = []
    if before_cross_summary is not None and \
            summary.get('unique_crossing_pairs_before') is not None and \
            int(summary['unique_crossing_pairs_before']) != before_cross_summary:
        crossing_errors.append(f'unique_crossing_pairs_before '
                               f'{summary["unique_crossing_pairs_before"]} != '
                               f'{before_cross_summary}')
    if after_cross_summary is not None and \
            summary.get('unique_crossing_pairs_after') is not None and \
            int(summary['unique_crossing_pairs_after']) != after_cross_summary:
        crossing_errors.append(f'unique_crossing_pairs_after '
                               f'{summary["unique_crossing_pairs_after"]} != '
                               f'{after_cross_summary}')
    if summary.get('crossing_reduction') is not None and \
            before_cross_summary is not None and after_cross_summary is not None and \
            int(summary['crossing_reduction']) != before_cross_summary - after_cross_summary:
        crossing_errors.append('crossing_reduction')
    report.add('phase5_summary_crossing_counts', not crossing_errors,
               crossing_errors[:10],
               before=summary.get('unique_crossing_pairs_before'),
               after=summary.get('unique_crossing_pairs_after'))
    # before == phase4 B group
    phase4_b = CAMPAIGN / 'phase4_ablation' / 'B_0.50mm' / 'routes_l3d.json'
    input_hashes_path = root / 'input_hashes.json'
    input_hashes = load_json(input_hashes_path) if input_hashes_path.is_file() else {}
    if phase4_b.is_file() and (before_dir / 'routes_l3d.json').is_file():
        before_sha = sha256(before_dir / 'routes_l3d.json')
        report.add('phase5_before_is_phase4_B',
                   before_sha == sha256(phase4_b),
                   dict(before_sha256=before_sha, phase4_b_sha256=sha256(phase4_b)))
        if input_hashes.get('b_routes_l3d_sha256') is not None:
            report.add('phase5_input_hashes_match',
                       input_hashes['b_routes_l3d_sha256'] == sha256(phase4_b),
                       dict(recorded=input_hashes['b_routes_l3d_sha256'],
                            actual=sha256(phase4_b)))
    # monotone crossing reduction + action bookkeeping
    before_cross = report.numbers.get('phase5_before_crossings', {}).get('unique_pairs')
    after_cross = report.numbers.get('phase5_after_crossings', {}).get('unique_pairs')
    if before_cross is not None and after_cross is not None:
        report.add('phase5_crossing_strictly_decreased', after_cross < before_cross,
                   dict(before=before_cross, after=after_cross,
                        reduction=before_cross - after_cross))
        if summary.get('unique_crossing_pairs_after') is not None and \
                int(summary['unique_crossing_pairs_after']) != after_cross:
            report.add('phase5_summary_pairs_match', False,
                       dict(summary=summary['unique_crossing_pairs_after'],
                            recomputed=after_cross))
        else:
            report.add('phase5_summary_pairs_match', True)
    actions_path = root / 'actions.json'
    if actions_path.is_file():
        action_payload = load_json(actions_path)
        actions = action_payload.get('actions') or []
        errors = []
        for index, action in enumerate(actions):
            before = action.get('pair_count_before')
            after = action.get('pair_count_after')
            if before is None or after is None:
                errors.append(f'action {index}: missing pair counters')
                continue
            if int(after) >= int(before):
                errors.append(f'action {index}: pairs {before} -> {after} not a decrease')
            old_pairs = action.get('old_pairs')
            new_pairs = action.get('new_pairs')
            if old_pairs is not None and new_pairs is not None:
                expected_after = int(before) - int(old_pairs) + int(new_pairs)
                if expected_after != int(after):
                    errors.append(f'action {index}: accounting '
                                  f'{before}-{old_pairs}+{new_pairs} != {after}')
        report.add('phase5_actions_monotone', not errors, errors[:20],
                   actions=len(actions),
                   rejected_total=action_payload.get('rejected_total'))
        if summary.get('accepted_actions') is not None and \
                int(summary['accepted_actions']) != len(actions):
            report.add('phase5_actions_count', False,
                       dict(summary=summary['accepted_actions'], actions=len(actions)))
        else:
            report.add('phase5_actions_count', True)
    else:
        report.warn('phase5: actions.json missing')
    # ---- stage_records bookkeeping --------------------------------------
    stage_path = root / 'stage_records.json'
    if stage_path.is_file():
        stage_records = load_json(stage_path)
        stage_errors = []
        singles = (len(stage_records.get('dynamic_layer_changes') or [])
                   + len(stage_records.get('interval_moves') or [])
                   + len(stage_records.get('revert_to_flat') or []))
        if summary.get('single_group_reschedules') is not None and \
                int(summary['single_group_reschedules']) != singles:
            stage_errors.append(f'single_group_reschedules '
                                f'{summary["single_group_reschedules"]} != {singles}')
        joints = stage_records.get('joint_reschedules') or []
        if summary.get('joint_reschedules') is not None and \
                int(summary['joint_reschedules']) != len(joints):
            stage_errors.append(f'joint_reschedules {summary["joint_reschedules"]} '
                                f'!= {len(joints)}')
        recovered = stage_records.get('recovered_failed_groups') or []
        if summary.get('recovered_failed_groups') is not None and \
                int(summary['recovered_failed_groups']) != len(recovered):
            stage_errors.append(f'recovered_failed_groups '
                                f'{summary["recovered_failed_groups"]} != '
                                f'{len(recovered)}')
        if len(stage_records.get('failed_retries') or []) != len(recovered):
            stage_errors.append('failed_retries != recovered_failed_groups')
        for joint in joints:
            group_ids = [int(value) for value in joint.get('group_ids') or []]
            if len(group_ids) != 2:
                stage_errors.append(f'joint action with {len(group_ids)} groups')
        report.add('phase5_stage_records_consistent', not stage_errors,
                   stage_errors[:20], singles=singles, joints=len(joints),
                   recovered=len(recovered))
    else:
        report.warn('phase5: stage_records.json missing')

    # ---- checkpoint / layer assignments ---------------------------------
    checkpoint_path = root / 'checkpoint.json'
    if checkpoint_path.is_file():
        checkpoint = load_json(checkpoint_path)
        layer_assignments = checkpoint.get('layer_assignments') or []
        checkpoint_errors = []
        if checkpoint.get('unique_crossing_pairs') is not None and after_cross is not None:
            if int(checkpoint['unique_crossing_pairs']) != after_cross:
                checkpoint_errors.append('checkpoint unique_crossing_pairs != after')
        by_group = {int(item['group_id']): item for item in layer_assignments}
        for group in context.groups:
            gid = int(group['group_id'])
            ids = [int(rid) for rid in group['route_ids']]
            if gid not in by_group:
                checkpoint_errors.append(f'group {gid}: missing layer assignment')
                continue
            item = by_group[gid]
            status = item.get('status')
            if status == 'lifted':
                layers = set()
                for rid in ids:
                    record = after_result['routed'].get(rid)
                    if record is None:
                        checkpoint_errors.append(f'group {gid}: member {rid} not routed')
                        continue
                    high = [part for part in record['parts']
                            if part['kind'] == 'flat' and int(part['layer_id']) != 1]
                    if not high:
                        checkpoint_errors.append(f'group {gid}: member {rid} not lifted')
                        continue
                    layers.add(int(high[0]['layer_id']))
                if len(layers) > 1:
                    checkpoint_errors.append(f'group {gid}: mixed layers {sorted(layers)}')
                if item.get('layer_id') is not None and layers and \
                        int(item['layer_id']) not in layers:
                    checkpoint_errors.append(f'group {gid}: assignment layer mismatch')
            elif status == 'flat_l1':
                for rid in ids:
                    record = after_result['routed'].get(rid)
                    if record is None:
                        continue
                    if any(part['kind'] == 'transition' for part in record['parts']):
                        checkpoint_errors.append(f'group {gid}: flat_l1 group has transitions')
        report.add('phase5_checkpoint_consistent', not checkpoint_errors,
                   checkpoint_errors[:20], groups=len(layer_assignments),
                   unique_crossing_pairs=checkpoint.get('unique_crossing_pairs'))
    else:
        report.warn('phase5: checkpoint.json missing')

    # ---- input hashes ----------------------------------------------------
    if input_hashes:
        hash_errors = []
        pairs = dict(b_routes_l3d_sha256='routes_l3d.json',
                     b_layer_stack_sha256='layer_stack.json',
                     b_validation_sha256='validation.json',
                     b_summary_sha256='summary.json')
        phase4_dir = CAMPAIGN / 'phase4_ablation' / 'B_0.50mm'
        for key, name in pairs.items():
            recorded = input_hashes.get(key)
            path = phase4_dir / name
            if recorded is not None and path.is_file():
                if recorded != sha256(path):
                    hash_errors.append(f'{key} mismatch')
        cache_path = CAMPAIGN / 'phase4_ablation' / 'baseline_crossings.json'
        if input_hashes.get('crossing_cache_sha256') is not None and cache_path.is_file():
            if input_hashes['crossing_cache_sha256'] != sha256(cache_path):
                hash_errors.append('crossing_cache_sha256 mismatch')
        report.add('phase5_input_hashes_all_match', not hash_errors,
                   hash_errors[:10])


STAGES = {'phase3': stage_phase3, 'phase4': stage_phase4, 'phase5': stage_phase5}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=sorted(STAGES), required=True)
    parser.add_argument('--root', type=Path, default=None,
                        help='stage output directory (default under the campaign)')
    parser.add_argument('--routing', type=Path,
                        default=CAMPAIGN / 'phase2_2d')
    parser.add_argument('--json', type=Path, default=None)
    parser.add_argument('--md', type=Path, default=None)
    parser.add_argument('--dry', action='store_true',
                        help='load-only self test: no pair audit / 3D validator')
    args = parser.parse_args(argv)
    report = Report(args.stage)
    context = Context(args.routing)
    STAGES[args.stage](report, args, context)
    payload = report.final()
    json_path = args.json or (VERIFY_DIR / f'{args.stage}_verification.json')
    md_path = args.md or (VERIFY_DIR / f'{args.stage}_verification.md')
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                         encoding='utf-8')
    lines = [f'# {args.stage} independent 3D verification', '',
             f"- verdict: **{'PASS' if payload['passed'] else 'FAIL'}**",
             f"- generated: {payload['generated_at']} "
             f"(runtime {payload['runtime_seconds']} s)",
             f"- failed checks: {payload['failed_checks'] or 'none'}",
             f"- warnings: {payload['warnings'] or 'none'}", '',
             '## Checks', '']
    for key, entry in payload['checks'].items():
        if entry.get('advisory'):
            marker = 'PASS' if entry['passed'] else 'WARN'
        else:
            marker = 'PASS' if entry['passed'] else 'FAIL'
        lines.append(f"- {marker} `{key}`")
    numbers = payload.get('numbers') or {}
    if numbers:
        lines += ['', '## Key numbers', '', '```json',
                  json.dumps(numbers, ensure_ascii=False, indent=1), '```']
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(dict(stage=args.stage, passed=payload['passed'],
                          failed=payload['failed_checks'],
                          warnings=payload['warnings'],
                          runtime=payload['runtime_seconds']),
                     ensure_ascii=False))
    return 0 if payload['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
