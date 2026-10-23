"""Hybrid C2/C4 directional layer routing.

z1 connections are allowed **C2** symmetry only (180 deg rotation).  The 264 z1
opposite connections are split by port direction into

* 132 horizontal (E<->W), 66 C2 pairs  -> lifted to L2 in variant ``H``;
* 132 vertical   (N<->S), 66 C2 pairs  -> lifted to L2 in variant ``V``.

The other direction stays flat on the z1 interface layer (z=0).  z2 keeps strict
C4: the 256 U connections stay exactly as in the Structured-A result (L3/L4/L5),
the 8 z2 opposite connections stay on L2, and the 496 adjacent connections stay
flat on their interface planes.

The lift construction for one C2 pair:

    port -> base straight -> S rise -> L2 straight -> S fall -> base straight -> port

with ``a_in`` (rise distance) and ``a_out`` (fall distance) shared by the two
C2-rotated members, so the pair remains exactly 180 deg rotation symmetric.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
A_DIR = CAMPAIGN / 'structured_layer_routing/A'
OUT_ROOT = CAMPAIGN / 'hybrid_c2_c4_directional'
WORK = OUT_ROOT / '_work'
A_RECORDS = None


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def direction_of(manifest, rid):
    record = manifest[int(rid)]
    sides = {record['source_side'], record['target_side']}
    if sides == {'N', 'S'}:
        return 'NS'
    if sides == {'E', 'W'}:
        return 'EW'
    return 'other'


class HybridData:
    """Loads the Structured-A result and the z1 C2 pair partition."""

    def __init__(self):
        from . import structured_layer_routing as S
        self.S = S
        self.campaign = S.StructuredCampaign(swap_rows=False)
        self.connectivity = _read_json(CAMPAIGN / 'inputs/connectivity_1024.json')
        self.manifest = {int(r['route_id']): r for r in self.connectivity['routes']}
        self.groups = {int(g['group_id']): g for g in self.connectivity['groups']}
        payload = _read_json(A_DIR / 'routes_1024.json')
        self.a_payload = payload
        self.a_records = {int(r['route_id']): r for r in payload['routes']}
        self.z1_opposite = [rid for rid in self.manifest
                            if self.manifest[rid]['plane'] == 'z1'
                            and self.manifest[rid]['relation'] == 'opposite']
        self.z2_opposite = [rid for rid in self.manifest
                            if self.manifest[rid]['plane'] == 'z2'
                            and self.manifest[rid]['relation'] == 'opposite']
        self.u_rids = [rid for rid in self.manifest
                       if self.manifest[rid]['relation'] == 'same']
        self.z1_opposite_groups = [gid for gid, info in self.groups.items()
                                   if info['kind'] == 'opposite'
                                   and info['plane'] == 'z1']
        self.pairs = []
        for gid in sorted(self.z1_opposite_groups):
            ids = [int(r) for r in self.groups[gid]['route_ids']]
            ew = sorted(rid for rid in ids
                        if direction_of(self.manifest, rid) == 'EW')
            ns = sorted(rid for rid in ids
                        if direction_of(self.manifest, rid) == 'NS')
            if len(ew) != 2 or len(ns) != 2:
                raise ValueError(f'group {gid}: expected 2 EW + 2 NS, got {ew} {ns}')
            self.pairs.append(dict(group_id=int(gid), ew=ew, ns=ns))
        # fixed part of the layout (exactly the Structured-A geometry)
        self.fixed_routes = []
        self.flat_routes = {}
        for rid in self.campaign.flat_rids:
            route = S.build_flat(self.campaign, rid)
            self.flat_routes[int(rid)] = route
            self.fixed_routes.append(route)
        for rid in self.u_rids:
            self.fixed_routes.append(self.a_records[rid])
        for rid in self.z2_opposite:
            self.fixed_routes.append(self.a_records[rid])
        for rid in self.z1_opposite:
            route = S.build_flat(self.campaign, rid)
            self.flat_routes[int(rid)] = route
            self.fixed_routes.append(route)

    def world(self):
        stack, world = self.S.world_from_routes(self.fixed_routes)
        return world


# ---------------------------------------------------------------------------
# C2 lift construction
# ---------------------------------------------------------------------------
def footprint(a_in, a_out, dz=1.0):
    from ..v3c4.lift_cross import transition_geometry
    return float(transition_geometry(dz)['footprint_mm'])


def build_c2_route(data, rid, a_in, a_out, layer=2, layer_z=1.0, total=150.0):
    """Build one lifted route of a C2 pair (rise ``a_in`` / fall ``a_out``)."""
    from ..v3c4.lift_cross import lift_route
    campaign = data.campaign
    f = footprint(a_in, a_out, layer_z)
    fall_start = total - a_out - f
    if a_in + f > fall_start - 5.0:
        return None
    record = campaign.record(rid)
    route = lift_route(dict(route_id=int(rid), plane=record['plane'],
                            source_endpoint=record['source_endpoint'],
                            target_endpoint=record['target_endpoint']),
                       campaign.row(int(rid)), layer, layer_z,
                       a_in, fall_start, campaign.primitives_2d(int(rid)),
                       radius=15.0)
    if route is None:
        return None
    identity = dict(record)
    identity.update(route)
    identity['route_id'] = int(rid)
    identity['status'] = 'routed'
    return identity


def build_c2_pair(data, pair, lift_key, a_in, a_out):
    """Build both members of one C2 pair (lifted); returns list of 2 routes."""
    routes = [build_c2_route(data, rid, a_in, a_out)
              for rid in pair[lift_key]]
    if any(route is None for route in routes):
        return None
    return routes


def check_pair_vs_world(world, pair_routes):
    violations = []
    for route in pair_routes:
        violations.extend(world.check_route(route))
    return violations


# ---------------------------------------------------------------------------
# assembly of one variant
# ---------------------------------------------------------------------------
def assemble_variant(data, feasibility, variant, log=print):
    """Greedy C2-pair lift for variant ``H`` (lift EW) or ``V`` (lift NS)."""
    lift_key = 'ew' if variant == 'H' else 'ns'
    flat_key = 'ns' if variant == 'H' else 'ew'
    world = data.world()
    lifts = {}
    failures = {}
    params = {}
    order = sorted(
        [pair for pair in data.pairs],
        key=lambda pair: (
            min((item[0] for item in feasibility.get(str(pair['group_id']), [])),
                default=999.0),
            pair['group_id']))
    for pair in order:
        gid = pair['group_id']
        candidate_items = list(feasibility.get(str(gid), []))
        if not candidate_items:
            failures[gid] = ('no feasible C2 lift against the fixed world '
                             '(kept on L1-z1)')
            log(f'[{variant}] group {gid}: no feasible parameters, kept flat')
            continue
        own = [int(rid) for rid in pair[lift_key]]
        for rid in own:
            world.remove_route(rid)
        candidate_items.sort(key=lambda item: (item[0] + item[1], item[0]))
        solved = None
        for a_in, a_out, _fall in candidate_items:
            routes = build_c2_pair(data, pair, lift_key, a_in, a_out)
            if routes is None:
                continue
            violations = check_pair_vs_world(world, routes)
            if violations:
                continue
            solved = (routes, (a_in, a_out))
            break
        if solved is None:
            for rid in own:
                world.add_route(data.flat_routes[int(rid)])
            failures[gid] = ('all feasible (a_in, a_out) conflict with already '
                             'lifted pairs; kept on L1-z1')
            log(f'[{variant}] group {gid}: assembly conflict, kept flat')
            continue
        routes, (a_in, a_out) = solved
        for route in routes:
            world.add_route(route)
            lifts[int(route['route_id'])] = route
        params[gid] = dict(group_id=int(gid), lift_key=lift_key,
                           direction='EW' if lift_key == 'ew' else 'NS',
                           a_in=float(a_in), a_out=float(a_out),
                           target_layer=2, target_z_mm=1.0,
                           route_ids=[int(route['route_id']) for route in routes])
    log(f'[{variant}] C2 lifts: {len(lifts)//2}/{len(data.pairs)} pairs, '
        f'failures={len(failures)}')
    return dict(world=world, lifts=lifts, params=params, failures=failures,
                lift_key=lift_key, flat_key=flat_key)


# ---------------------------------------------------------------------------
# payload / validation / metrics
# ---------------------------------------------------------------------------
def build_payload(data, variant, assembly, log=print):
    lifted = assembly['lifts']
    records = []
    for rid in sorted(data.manifest):
        relation = data.manifest[rid]['relation']
        if rid in lifted:
            records.append(lifted[rid])
        elif (relation in ('adjacent', 'same')
              or rid in data.z2_opposite):
            # fixed part of the layout: byte-identical to Structured A
            records.append(data.a_records[rid])
        else:
            # z1 opposite connection that could not be lifted: flat on L1-z1
            records.append(data.flat_routes.get(rid, data.a_records[rid]))
    layer_stack = _read_json(CAMPAIGN / 'phase5_dynamic_optimization/after/layer_stack.json')
    payload = dict(schema='four_side_1024_v2_l3d_routes_v1',
                   experiment=f'MANUAL_C4_HYBRID_C2_C4_DIRECTIONAL_{variant}',
                   note=('hybrid C2/C4 directional layering: z1 opposite split by '
                         'direction into C2 pairs, one direction lifted to L2; z2 '
                         'keeps strict C4 with the fixed Structured-A U bundles'),
                   layer_stack=layer_stack, routes=records)
    log(f'[{variant}] payload: {len(records)} routes, lifted={len(lifted)}')
    return payload


def validate(data, payload, log=print):
    from ..v3c4.lift_cross import validate_payload_v4
    return validate_payload_v4(payload, CAMPAIGN / 'phase2_2d', log=log)


def _flat_entries(records):
    entries = defaultdict(list)
    for record in records:
        for part in record.get('parts') or []:
            if part['kind'] == 'flat':
                entries[round(float(part['z_mm']), 6)].append(
                    (int(record['route_id']), part['primitives']))
    return entries


def classify(manifest, rid, data):
    record = manifest[int(rid)]
    relation = record['relation']
    if relation == 'opposite':
        return f"opposite_{record['plane']}_{direction_of(manifest, rid)}"
    if relation == 'same':
        return 'same_U'
    return 'adjacent'


def audit_height(records, manifest, data):
    from ..fslw import validate_fslw as V
    entries = defaultdict(list)
    for record in records:
        for part in record.get('parts') or []:
            if part['kind'] == 'flat':
                entries[round(float(part['z_mm']), 6)].append(
                    (int(record['route_id']), part['primitives']))
    out = {}
    unique = set()
    for height, plane_entries in entries.items():
        if len(plane_entries) < 2:
            out[str(height)] = dict(pairs=0, breakdown={}, violations=0,
                                    routes=len(plane_entries))
            continue
        prepared = [V.prepare_route(prims, rid) for rid, prims in plane_entries]
        audit = V.audit_route_pairs(prepared, policy='strict')
        pairs = set()
        breakdown = Counter()
        for item in audit['crossings']:
            a, b = int(item['route_a']), int(item['route_b'])
            pairs.add(tuple(sorted((a, b))))
            breakdown[tuple(sorted((classify(manifest, a, data),
                                    classify(manifest, b, data))))] += 1
        unique |= pairs
        out[str(height)] = dict(
            pairs=len(pairs), breakdown={f'{k[0]} x {k[1]}': v
                                         for k, v in breakdown.items()},
            violations=len(audit['violations']), routes=len(plane_entries))
    return out, len(unique)


def metrics(data, variant, payload, report, assembly, runtime, log=print):
    records = [record for record in payload['routes']
               if record.get('status') == 'routed']
    audit, unique = audit_height(records, data.manifest, data)
    # layer counts
    layer_defs = [('L1-z1', 1, 0.0), ('L1-z2', 1, 0.5), ('L2', 2, 1.0),
                  ('L3', 3, 1.5), ('L4', 4, 2.0), ('L5', 5, 2.5)]
    layer_counts = {}
    for name, layer_id, z in layer_defs:
        users = []
        plane_users = Counter()
        for record in records:
            for part in record.get('parts') or []:
                if part['kind'] != 'flat':
                    continue
                if int(part['layer_id']) == layer_id and abs(
                        float(part['z_mm']) - z) <= 1e-9:
                    users.append(int(record['route_id']))
                    plane_users[record['plane']] += 1
                    break
        layer_counts[name] = dict(count=len(users), layer_id=layer_id, z_mm=z,
                                  plane_counts=dict(plane_users))
    # z1 directional statistics
    z1_opp = set(data.z1_opposite)
    hv_pairs = 0
    hv_breakdown = {}
    for height, info in audit.items():
        for key, value in info['breakdown'].items():
            parts = key.split(' x ')
            if all(part.startswith('opposite_z1') for part in parts):
                dirs = {part.rsplit('_', 1)[1] for part in parts}
                if dirs == {'EW', 'NS'}:
                    hv_pairs += value
                    hv_breakdown[height] = hv_breakdown.get(height, 0) + value
    transitions = sum(int(r.get('n_transitions') or 0) for r in records)
    total_length = round(sum(float(r.get('length_mm') or 0.0) for r in records), 4)
    stats = report.get('stats') or {}
    metrics = dict(
        variant=variant,
        routed=len(records),
        c2_pairs_total=len(data.pairs),
        c2_pairs_lifted=len(assembly['params']),
        c2_pairs_failed=len(assembly['failures']),
        c2_failures={str(gid): reason
                     for gid, reason in assembly['failures'].items()},
        lifted_direction='EW (horizontal)' if variant == 'H' else 'NS (vertical)',
        kept_direction='NS (vertical)' if variant == 'H' else 'EW (horizontal)',
        lifted_routes=len(assembly['lifts']),
        kept_flat_routes=len(data.z1_opposite) - len(assembly['lifts']),
        unique_crossing_pairs=unique,
        crossing_pairs_by_height={h: info['pairs'] for h, info in audit.items()},
        crossing_breakdown_by_height={h: info['breakdown']
                                      for h, info in audit.items()},
        z1_hv_same_height_pairs=hv_pairs,
        z1_hv_breakdown_by_height=hv_breakdown,
        transitions=int(transitions),
        total_length_mm=total_length,
        layer_counts=layer_counts,
        validation_status=report.get('status'),
        validation_exploratory_pass=report.get('exploratory_pass'),
        validation_counts=report.get('counts'),
        validation_violations=len(report.get('violations') or []),
        min_3d_clearance_mm=stats.get('min_3d_clearance_mm'),
        min_curvature_radius_mm=stats.get('min_curvature_radius_mm'),
        runtime_seconds=round(runtime, 2),
        u_routes_preserved=sum(1 for rid in data.u_rids
                               if records and any(
                                   int(r['route_id']) == int(rid) for r in records)),
    )
    log(f'[{variant}] routed={metrics["routed"]} pairs_lifted='
        f'{metrics["c2_pairs_lifted"]} unique_crossings={unique} '
        f'z1_HV={hv_pairs} transitions={transitions} '
        f'min3d={metrics["min_3d_clearance_mm"]}')
    return metrics
