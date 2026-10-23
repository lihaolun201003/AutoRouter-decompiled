"""Spatial grouped U-bundle 3D routing optimization on the Manual-C4 result.

The 64 C4 quartets whose four members are same-side U turns are re-built with a new
parameterised geometry (no connection / port / constraint change):

    port -> extended base straight -> S rise -> target-layer 90 deg arc ->
    middle straight -> 90 deg arc -> S fall -> extended base straight -> port

The quartet's four members are exact 90 deg rotations of one representative path
(C4 atomic).  Target layer assignment (fixed by the task):

* z1 groups  20- 35 (middle U)      -> L2 (z = 1.0 mm)
* z2 groups 144-159 (corner U #1)   -> L2 (z = 1.0 mm)
* z2 groups 160-175 (corner U #2)   -> L3 (z = 1.5 mm)
* z2 groups 176-191 (middle U)      -> L4 (z = 2.0 mm)

Entry / exit straight lengths and the rise / fall positions are optimisation
variables; the high-layer arc depth is chosen per quartet so that same-bundle U
turns stay nested (outer deeper) and avoid the fixed 768-route layout in full 3D.
The other 768 connections keep their current geometry unchanged (unless a
documented local-reroute stage is enabled for blocking non-U quartets).

This module only builds / searches / validates; plotting lives in
:mod:`four_side_1024.manual_c4.spatial_u_bundle_plots`.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
AFTER_DIR = CAMPAIGN / 'phase5_dynamic_optimization/after'
V2_ROOT = CAMPAIGN / 'phase2_2d'
OUT_DIR = CAMPAIGN / 'spatial_u_bundle_optimization'
WORK_DIR = OUT_DIR / '_work'

RADIUS = 15.0
BOARD = 150.0
WIDTH = 0.05
INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0),
          'E': (-1.0, 0.0), 'W': (1.0, 0.0)}

BUNDLES = {
    'z1_middle_U': dict(groups=list(range(20, 36)), layer=2, layer_z=1.0,
                        name='z1 四边中间 U', side_color='#1f6fd6'),
    'z2_corner_U_1': dict(groups=list(range(144, 160)), layer=2, layer_z=1.0,
                          name='z2 第一组四角 U', side_color='#2f9e44'),
    'z2_corner_U_2': dict(groups=list(range(160, 176)), layer=3, layer_z=1.5,
                          name='z2 第二组四角 U', side_color='#7048e8'),
    'z2_middle_U': dict(groups=list(range(176, 192)), layer=4, layer_z=2.0,
                        name='z2 四边中间 U', side_color='#e03131'),
}
GID_BUNDLE = {gid: name for name, conf in BUNDLES.items() for gid in conf['groups']}
TARGET_GIDS = sorted(GID_BUNDLE)

#: depth-ordering gap between nested same-layer U turns (mm)
NEST_GAP_MM = 0.5
#: preferred rise/fall distances per bundle (entry distance from the port, mm)
A_PREFERENCE = {
    'z1_middle_U': 11.2,     # must start after the paired z2 rise window
    'z2_corner_U_1': 6.0,
    'z2_corner_U_2': 6.0,
    'z2_middle_U': 1.2,      # rises first; z1 middle rises after
}


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------
def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Campaign:
    def __init__(self, after_dir=None):
        after_dir = Path(after_dir or AFTER_DIR)
        self.after_dir = after_dir
        self.connectivity = _read_json(CAMPAIGN / 'inputs/connectivity_1024.json')
        self.groups = {int(g['group_id']): g for g in self.connectivity['groups']}
        self.manifest = {int(r['route_id']): r for r in self.connectivity['routes']}
        payload = _read_json(after_dir / 'routes_l3d.json')
        self.baseline_payload = payload
        self.baseline_records = {int(r['route_id']): r for r in payload['routes']
                                 if r.get('status') == 'routed'}
        self.layer_stack_payload = _read_json(after_dir / 'layer_stack.json')
        self.target_rids = {rid for gid in TARGET_GIDS
                            for rid in self.groups[gid]['route_ids']}

    def record(self, rid):
        return self.manifest[int(rid)]

    def port_xy(self, endpoint):
        from ..v3c4.inputs import ENDPOINTS
        return tuple(float(v) for v in ENDPOINTS[endpoint]['routing_xy'])

    def group_routes(self, gid):
        return [int(rid) for rid in self.groups[int(gid)]['route_ids']]


# ---------------------------------------------------------------------------
# geometry construction
# ---------------------------------------------------------------------------
def build_quartet(campaign, gid, layer, layer_z, bulge, a_in, a_out,
                  radius=RADIUS):
    """Build the four C4-rotated routes of one same-side U quartet."""
    from ..r15 import u_geometry as UG
    from ..legacy_geometry import transform_primitives
    from ..fsd25d import path3d as P
    from ..v3c4.lift_cross import lift_route, transition_geometry, row_z, PORT_MARGIN_MM
    from ..v3c4 import inputs as V3

    ids = campaign.group_routes(gid)
    rep = campaign.record(ids[0])
    p = campaign.port_xy(rep['source_endpoint'])
    q = campaign.port_xy(rep['target_endpoint'])
    side = rep['source_side']
    inward = INWARD[side]
    frame, errors = UG._canonical_frame(p, q, inward, (-inward[0], -inward[1]),
                                        BOARD, WIDTH)
    if frame is None:
        return None, f'canonical frame: {errors}'
    separation = float(frame['separation_mm'])
    middle = separation - 2.0 * radius
    if middle < -1e-9:
        return None, f'separation {separation:.3f} < 2R'
    base_z = row_z(1 if rep['plane'] == 'z1' else 2)
    f = float(transition_geometry(layer_z - base_z, radius)['footprint_mm'])
    if a_in < PORT_MARGIN_MM - 1e-9 or a_out < PORT_MARGIN_MM - 1e-9:
        return None, f'rise/fall below PORT_MARGIN {PORT_MARGIN_MM}'
    if a_in + f > bulge + 1e-9 or a_out + f > bulge + 1e-9:
        return None, 'rise/fall does not fit in the entry/exit straight'
    canonical = UG._quarter_pair(frame['p_canonical'], frame['q_canonical'],
                                 radius, float(bulge), middle)
    prims_rep = transform_primitives(canonical, frame['transform'], inverse=True)
    total = P.path_length(prims_rep)
    fall_start = total - a_out - f
    routes = []
    for phase, rid in enumerate(ids):
        member = campaign.record(rid)
        row = 1 if member['plane'] == 'z1' else 2
        if phase == 0:
            prims, rise, fall = prims_rep, a_in, fall_start
        else:
            rotated = V3.rotate_primitives(prims_rep, phase)
            prims, reversed_flag = V3.orient_primitives(
                rotated, member['source_endpoint'], member['target_endpoint'])
            rise, fall = ((a_out, total - a_in - f) if reversed_flag
                          else (a_in, fall_start))
        record = dict(route_id=rid, plane=member['plane'],
                      source_endpoint=member['source_endpoint'],
                      target_endpoint=member['target_endpoint'])
        route = lift_route(record, row, layer, layer_z, rise, fall, prims,
                           radius=radius)
        if route is None:
            return None, f'lift_route rejected member phase {phase}'
        # carry the manifest identity (endpoints, relation, pair, sides, rows)
        identity = dict(member)
        identity.update(route)
        identity['route_id'] = int(rid)
        identity['status'] = 'routed'
        routes.append(identity)
    return routes, None


def flat_parts(route):
    return [part for part in route['parts'] if part['kind'] == 'flat']


def route_2d_primitives(route):
    """Rebuild the continuous 2D primitive chain from a lifted route.

    Flat parts are copied as-is; every transition contributes its XY projection
    (``start`` -> ``end``) as one straight line, so the chain stays continuous and
    can be rotated / re-lifted again.
    """
    primitives = []
    for part in route['parts']:
        if part['kind'] == 'flat':
            primitives.extend(dict(primitive) for primitive in part['primitives'])
        else:
            start = list(part['start'])
            end = list(part['end'])
            if abs(start[0] - end[0]) > 1e-9 or abs(start[1] - end[1]) > 1e-9:
                primitives.append(dict(kind='line', p0=start, p1=end, layer=0))
    return primitives


# ---------------------------------------------------------------------------
# fixed world helpers
# ---------------------------------------------------------------------------
def fixed_world(campaign, extra_excluded=()):
    from ..l3d import layers as LL
    from ..l3d.world import World
    from ..fslw import config as C
    stack = LL.build_stack('medium_050')
    world = World(stack, clearance=C.CLEARANCE_MM)
    excluded = set(campaign.target_rids) | set(extra_excluded)
    for rid, record in campaign.baseline_records.items():
        if rid in excluded:
            continue
        world.add_route(record)
    return world


def check_routes(world, routes):
    violations = []
    for route in routes:
        violations.extend(world.check_route(route))
        if violations:
            break
    return violations


# ---------------------------------------------------------------------------
# verification helpers
# ---------------------------------------------------------------------------
def verify_candidate(campaign, world, routes):
    """Full candidate checks available before a payload validation."""
    from ..fslw import config as C
    from ..fslw import validate_fslw as V
    from ..v3c4.lift_cross import check_route_primitives
    errors = []
    if routes is None:
        return ['build failed']
    # (a) no conflict in the current world (fixed + accepted layout)
    errors.extend(check_routes(world, routes))
    # (b) route level geometric legality
    for route in routes:
        record = campaign.record(route['route_id'])
        endpoints = campaign.port_xy(record['source_endpoint']), campaign.port_xy(
            record['target_endpoint'])
        source = _endpoint_record(record['source_endpoint'])
        target = _endpoint_record(record['target_endpoint'])
        result = V.check_route_primitives(
            [primitive for part in flat_parts(route)
             for primitive in part['primitives']],
            source=source, target=target, width=C.WIDTH_MM,
            radius=C.RADIUS_MM, board=C.BOARD_MM, clearance=C.CLEARANCE_MM)
        if not result['passed']:
            errors.append((route['route_id'], result['errors'][:4]))
    # (c) transition structure / one rise + one fall / target layer arcs
    for route in routes:
        kinds = [part['kind'] for part in route['parts']]
        flat_count = kinds.count('flat')
        transitions = [part for part in route['parts'] if part['kind'] == 'transition']
        if len(transitions) != 2 or flat_count != 3:
            errors.append((route['route_id'], f'part sequence {kinds}'))
        target_parts = [part for part in flat_parts(route)
                        if int(part['layer_id']) != 1]
        if len(target_parts) != 1:
            errors.append((route['route_id'], 'high flat parts != 1'))
    return errors


def _endpoint_record(eid):
    from ..v3c4.inputs import ENDPOINTS
    ep = ENDPOINTS[eid]
    return dict(routing_xy=list(ep['routing_xy']), inward=list(ep['inward']),
                side=ep['side'], row=ep['row'], column=ep['column'],
                connector=ep['connector'])


# ---------------------------------------------------------------------------
# payload assembly / validation / metrics
# ---------------------------------------------------------------------------
def assemble_payload(campaign, new_routes, experiment='MANUAL_C4_SPATIAL_U_BUNDLE',
                     note=None):
    """Replace the 256 target records with the new geometry; keep the rest as-is."""
    records = []
    for rid in sorted(campaign.baseline_records):
        records.append(new_routes.get(rid, campaign.baseline_records[rid]))
    payload = dict(
        schema='four_side_1024_v2_l3d_routes_v1',
        experiment=experiment,
        note=note or ('every C4 quartet is built from one representative path and '
                      'its 90/180/270 deg rotations; 256 target same-side U routes '
                      'rebuilt, the other 768 routes unchanged'),
        layer_stack=campaign.layer_stack_payload,
        routes=records)
    return payload


def validate_payload(payload, log=print):
    from ..v3c4.lift_cross import validate_payload_v4
    return validate_payload_v4(payload, V2_ROOT, log=log)


def payload_metrics(campaign, payload, report=None):
    """Layer / crossing / length / transition statistics of one payload."""
    from ..v3c4.lift_cross import analyze_planes
    from ..fslw import validate_fslw as V

    records = [record for record in payload['routes']
               if record.get('status') == 'routed']
    # flat entries per physical height (for the crossing audit)
    entries = {}
    for record in records:
        for part in flat_parts(record):
            entries.setdefault(round(float(part['z_mm']), 6), []).append(
                (int(record['route_id']), part['primitives']))
    crossings, reports, pairs_by_plane = analyze_planes(entries, log=lambda *a, **k: None,
                                                        compute_positions=False)
    unique_pairs = set()
    for pairs in pairs_by_plane.values():
        unique_pairs |= pairs
    # same-layer target-U vs target-U crossing pairs (XY crossings of flat parts)
    target_rids = campaign.target_rids
    uu_pairs = set()
    for z, plane_entries in entries.items():
        selected = [(rid, prims) for rid, prims in plane_entries
                    if rid in target_rids]
        if len(selected) < 2:
            continue
        prepared = [V.prepare_route(prims, rid) for rid, prims in selected]
        audit = V.audit_route_pairs(prepared, policy='strict')
        for item in audit['crossings']:
            a, b = int(item['route_a']), int(item['route_b'])
            uu_pairs.add((min(a, b), max(a, b)))
        for item in audit['violations']:
            uu_pairs.add(('violation', item))
    # layer usage counts (routes with a flat part on that layer)
    layer_defs = [('L1-z1', 1, 0.0), ('L1-z2', 1, 0.5), ('L2', 2, 1.0),
                  ('L3', 3, 1.5), ('L4', 4, 2.0), ('L5', 5, 2.5)]
    layer_counts = {}
    layer_counts_plane = {}
    for name, layer_id, z in layer_defs:
        users = []
        plane_users = {'z1': 0, 'z2': 0}
        for record in records:
            for part in flat_parts(record):
                if int(part['layer_id']) == layer_id and abs(
                        float(part['z_mm']) - z) <= 1e-9:
                    users.append(int(record['route_id']))
                    plane_users[record['plane']] += 1
                    break
        layer_counts[name] = dict(count=len(users), layer_id=layer_id,
                                  z_mm=z, plane_counts=plane_users,
                                  route_ids=sorted(users))
        layer_counts_plane[name] = plane_users
    transitions = sum(int(record.get('n_transitions') or 0) for record in records)
    total_length = round(sum(float(record.get('length_mm') or 0.0)
                             for record in records), 4)
    metrics = dict(
        routed=len(records), failed=len(payload['routes']) - len(records),
        unique_crossing_pairs=len(unique_pairs),
        unique_crossing_pairs_by_height={
            str(z): len(pairs) for z, pairs in pairs_by_plane.items()},
        crossing_points_by_height={str(z): value['crossing_count']
                                   for z, value in reports.items()},
        same_layer_u_u_crossing_pairs=len(uu_pairs),
        transitions=int(transitions),
        total_length_mm=total_length,
        layer_counts=layer_counts,
        plane_crossings={str(z): dict(crossing_pair_count=value['crossing_pair_count'],
                                      crossing_count=value['crossing_count'])
                         for z, value in reports.items()},
    )
    if report is not None:
        stats = report.get('stats') or {}
        metrics.update(
            validation_status=report.get('status'),
            validation_exploratory_pass=report.get('exploratory_pass'),
            validation_geometry_pass=report.get('geometry_pass'),
            validation_counts=report.get('counts'),
            min_3d_clearance_mm=stats.get('min_3d_clearance_mm'),
            min_curvature_radius_mm=stats.get('min_curvature_radius_mm'),
            validation_violations=len(report.get('violations') or []))
    return metrics


# ---------------------------------------------------------------------------
# geometry plan assignment (from the feasible search sets)
# ---------------------------------------------------------------------------
def group_separation(campaign, gid):
    rep = campaign.record(campaign.group_routes(gid)[0])
    p = campaign.port_xy(rep['source_endpoint'])
    q = campaign.port_xy(rep['target_endpoint'])
    side = rep['source_side']
    return abs(p[0] - q[0]) if side in 'NS' else abs(p[1] - q[1])


def bundle_rank(campaign, bundle):
    gids = list(BUNDLES[bundle]['groups'])
    return sorted(gids, key=lambda gid: group_separation(campaign, gid))


def choose_depth_chain(candidates, gap=NEST_GAP_MM):
    """Pick one D per rank (inner -> outer) with D increasing by at least ``gap``.

    ``candidates`` is a list (per rank) of sorted feasible D values.
    Returns a list of chosen D values or None.
    """
    ranks = len(candidates)
    # DP from the outermost rank backwards: best_next[i] = list of feasible D
    # values at rank i from which a full chain can be completed.
    reachable = [None] * ranks
    reachable[ranks - 1] = sorted(set(candidates[ranks - 1]))
    for index in range(ranks - 2, -1, -1):
        next_values = reachable[index + 1]
        values = sorted(set(candidates[index]))
        ok = []
        for d in values:
            # need some next >= d + gap
            import bisect
            position = bisect.bisect_left(next_values, d + gap - 1e-9)
            if position < len(next_values):
                ok.append(d)
        reachable[index] = ok
        if not ok:
            return None
    # greedy forward choice: smallest reachable value
    chain = []
    previous = None
    for index in range(ranks):
        values = reachable[index]
        chosen = None
        for d in values:
            if previous is None or d >= previous + gap - 1e-9:
                chosen = d
                break
        if chosen is None:
            return None
        chain.append(chosen)
        previous = chosen
    return chain
