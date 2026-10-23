"""Structured layer routing (A/B) on the Manual-C4 Spatial U-bundle baseline.

Two independent groups
----------------------
* ``A``: original z1 / z2 connection assignment;
* ``B``: the two 512-row connection tables swapped between the physical interface
  rows (z1 <-> z2), then re-routed / re-layered from scratch.

Structured target layering
--------------------------
* 496 adjacent connections  -> stay flat on their interface plane (z = 0 / 0.5);
* 272 opposite connections  -> re-built as straight L2 (z = 1.0) through lines
  with (ideally) unified S-transition windows;
* 256 same-side U routes    -> rebuilt U geometry on the task-assigned layers:
  groups 20-35 and 144-159 -> L3 (1.5), 160-175 -> L4 (2.0), 176-191 -> L5 (2.5).

Everything is C4-group atomic; the 3D acceptance is the frozen
``l3d.validate_payload`` audit.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
OUT_ROOT = CAMPAIGN / 'structured_layer_routing'
BASELINE = CAMPAIGN / 'spatial_u_bundle_optimization/routes_1024.json'
PHASE2 = CAMPAIGN / 'phase2_2d'
WORK = OUT_ROOT / '_work'

RADIUS = 15.0
BOARD = 150.0
WIDTH = 0.05
INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0),
          'E': (-1.0, 0.0), 'W': (1.0, 0.0)}
ADJACENT, OPPOSITE, SAME = 'adjacent', 'opposite', 'same'
TARGET_U_LAYER = {}
for _gid in range(20, 36):
    TARGET_U_LAYER[_gid] = (3, 1.5)
for _gid in range(144, 160):
    TARGET_U_LAYER[_gid] = (3, 1.5)
for _gid in range(160, 176):
    TARGET_U_LAYER[_gid] = (4, 2.0)
for _gid in range(176, 192):
    TARGET_U_LAYER[_gid] = (5, 2.5)
OPPOSITE_LAYER = (2, 1.0)
LAYER_Z = {1: None, 2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5}
LAYER_NAMES = {1: 'L1', 2: 'L2', 3: 'L3', 4: 'L4', 5: 'L5'}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def row_z(row):
    return 0.0 if int(row) == 1 else 0.5


# ---------------------------------------------------------------------------
# connectivity / 2D geometry loading (with optional z1<->z2 row swap)
# ---------------------------------------------------------------------------
class StructuredCampaign:
    def __init__(self, swap_rows=False, campaign_dir=None):
        self.swap_rows = bool(swap_rows)
        self.name = 'B_swapped' if self.swap_rows else 'A_original'
        self.campaign_dir = Path(campaign_dir or CAMPAIGN)
        raw = _read_json(self.campaign_dir / 'inputs/connectivity_1024.json')
        self.source_connectivity = raw
        groups = []
        routes = []
        self._original_plane = {}
        for group in raw['groups']:
            new_group = dict(group)
            if self.swap_rows:
                new_group['plane'] = self._swap_plane(group['plane'])
            new_group['route_ids'] = list(group['route_ids'])
            groups.append(new_group)
        for record in raw['routes']:
            new = dict(record)
            self._original_plane[int(record['route_id'])] = record['plane']
            if self.swap_rows:
                new['plane'] = self._swap_plane(record['plane'])
                new['source_row'] = 2 if int(record['source_row']) == 1 else 1
                new['target_row'] = 2 if int(record['target_row']) == 1 else 1
                new['source_endpoint'] = self._swap_endpoint(record['source_endpoint'])
                new['target_endpoint'] = self._swap_endpoint(record['target_endpoint'])
            routes.append(new)
        self.groups = {int(g['group_id']): g for g in groups}
        self.manifest = {int(r['route_id']): r for r in routes}
        # 2D geometry stays the same XY chain; it is read from the *original*
        # plane file of each connection (2D validity is plane-independent)
        self.plane2d = {}
        for plane in ('z1', 'z2'):
            payload = _read_json(self.campaign_dir / f'phase2_2d/{plane}/routes.json')
            for record in payload['routes']:
                self.plane2d[int(record['route_id'])] = record
        self.target_rids = set(self.manifest)
        self.flat_rids = [rid for rid in self.manifest
                          if self.manifest[rid]['relation'] == ADJACENT]
        self.opposite_rids = [rid for rid in self.manifest
                              if self.manifest[rid]['relation'] == OPPOSITE]
        self.u_rids = [rid for rid in self.manifest
                       if self.manifest[rid]['relation'] == SAME]
        self.opposite_groups = [gid for gid, g in self.groups.items()
                                if g['kind'] == OPPOSITE]
        self.u_groups = [gid for gid, g in self.groups.items()
                         if g['kind'] == SAME]

    @staticmethod
    def _swap_plane(plane):
        return 'z2' if plane == 'z1' else 'z1'

    @staticmethod
    def _swap_endpoint(endpoint):
        connector, row, column = endpoint.split(':')
        return f'{connector}:{2 if int(row) == 1 else 1}:{column}'

    # -- helpers -----------------------------------------------------------
    def record(self, rid):
        return self.manifest[int(rid)]

    def row(self, rid):
        return int(self.manifest[int(rid)]['source_row'])

    def base_z(self, rid):
        return row_z(self.row(rid))

    def primitives_2d(self, rid):
        return [dict(p) for p in self.plane2d[int(rid)]['primitives']]

    def port_xy(self, endpoint):
        from ..v3c4.inputs import ENDPOINTS
        return tuple(float(v) for v in ENDPOINTS[endpoint]['routing_xy'])

    def group_routes(self, gid):
        return [int(rid) for rid in self.groups[int(gid)]['route_ids']]

    def group_kind(self, gid):
        return self.groups[int(gid)]['kind']


# ---------------------------------------------------------------------------
# geometry builders
# ---------------------------------------------------------------------------
def _rotate_member(prims_rep, phase, campaign, rid):
    from ..v3c4 import inputs as V3
    member = campaign.record(rid)
    rotated = V3.rotate_primitives(prims_rep, phase)
    return V3.orient_primitives(rotated, member['source_endpoint'],
                                member['target_endpoint'])


def _enrich_route(campaign, rid, route):
    """Fill the fields the frozen 3D validator expects on every route record."""
    record = campaign.record(rid)
    plane_record = campaign.plane2d[int(rid)]
    base_z = campaign.base_z(rid)
    if not route.get('source_port'):
        route['source_port'] = dict(
            xy=list(campaign.port_xy(record['source_endpoint'])),
            z_mm=base_z, layer_id=1)
    if not route.get('target_port'):
        route['target_port'] = dict(
            xy=list(campaign.port_xy(record['target_endpoint'])),
            z_mm=base_z, layer_id=1)
    route['rotation_group_id'] = plane_record.get('rotation_group_id')
    route['rotation_phase'] = plane_record.get('rotation_phase')
    route['c4_symmetry'] = (plane_record.get('c4_symmetry')
                            or 'strict_group_commit')
    candidate = plane_record.get('candidate')
    if not candidate:
        candidate = dict(family='structured_layered', params={},
                         strategy='MANUAL_C4_STRUCTURED_LAYER', index=0)
    route['candidate'] = candidate
    route['primitives'] = campaign.primitives_2d(rid)
    route['layer'] = 0
    length_mm = float(route.get('length_mm') or 0.0)
    route['length_cm'] = length_mm / 10.0
    route['propagation_loss_db'] = round(0.05 * length_mm / 10.0, 6)
    route['bend_count'] = sum(1 for primitive in route['primitives']
                              if primitive.get('kind') == 'arc')
    return route


def _finish_route(campaign, rid, route):
    identity = dict(campaign.record(rid))
    identity.update(route)
    identity['route_id'] = int(rid)
    identity['status'] = 'routed'
    return _enrich_route(campaign, rid, identity)


def build_flat(campaign, rid):
    """One adjacent connection: flat on its interface plane, no transitions."""
    from ..l3d.world import World
    record = campaign.record(rid)
    route = World.flat_route(int(rid), record['plane'],
                             campaign.primitives_2d(rid),
                             campaign.base_z(rid), layer_id=1,
                             row=campaign.row(rid))
    return _finish_route(campaign, rid, route)


def build_opposite_group(campaign, gid, a_in, a_out, layer=2, layer_z=1.0):
    """One opposite quartet: straight 2D line + early rise / late fall to L2."""
    from ..fsd25d import path3d as P
    from ..v3c4.lift_cross import lift_route, transition_geometry, PORT_MARGIN_MM
    ids = campaign.group_routes(gid)
    prims_rep = campaign.primitives_2d(ids[0])
    total = P.path_length(prims_rep)
    routes = []
    for phase, rid in enumerate(ids):
        base_z = campaign.base_z(rid)
        f = float(transition_geometry(layer_z - base_z)['footprint_mm'])
        if a_in < PORT_MARGIN_MM or a_out < PORT_MARGIN_MM:
            return None
        if phase == 0:
            prims, rise, fall = prims_rep, a_in, total - a_out - f
        else:
            prims, reversed_flag = _rotate_member(prims_rep, phase, campaign, rid)
            rise, fall = ((a_out, total - a_in - f) if reversed_flag
                          else (a_in, total - a_out - f))
        if rise + f > fall - 5.0 or fall + f > total - PORT_MARGIN_MM:
            return None
        route = lift_route(dict(route_id=rid, plane=campaign.record(rid)['plane'],
                                source_endpoint=campaign.record(rid)['source_endpoint'],
                                target_endpoint=campaign.record(rid)['target_endpoint']),
                           campaign.row(rid), layer, layer_z, rise, fall,
                           prims, radius=RADIUS)
        if route is None:
            return None
        routes.append(_finish_route(campaign, rid, route))
    return routes


def build_u_group(campaign, gid, layer, layer_z, bulge, a_in, a_out):
    """One same-side U quartet: extended straights + target-layer arcs."""
    from ..fsd25d import path3d as P
    from ..r15 import u_geometry as UG
    from ..legacy_geometry import transform_primitives
    from ..v3c4.lift_cross import lift_route, transition_geometry, PORT_MARGIN_MM
    ids = campaign.group_routes(gid)
    rep = campaign.record(ids[0])
    p = campaign.port_xy(rep['source_endpoint'])
    q = campaign.port_xy(rep['target_endpoint'])
    side = rep['source_side']
    inward = INWARD[side]
    frame, errors = UG._canonical_frame(p, q, inward, (-inward[0], -inward[1]),
                                        BOARD, WIDTH)
    if frame is None:
        return None
    separation = float(frame['separation_mm'])
    middle = separation - 2.0 * RADIUS
    if middle < -1e-9:
        return None
    base_z = campaign.base_z(ids[0])
    f = float(transition_geometry(layer_z - base_z)['footprint_mm'])
    if a_in < PORT_MARGIN_MM or a_out < PORT_MARGIN_MM:
        return None
    if a_in + f > bulge + 1e-9 or a_out + f > bulge + 1e-9:
        return None
    canonical = UG._quarter_pair(frame['p_canonical'], frame['q_canonical'],
                                 RADIUS, float(bulge), middle)
    prims_rep = transform_primitives(canonical, frame['transform'], inverse=True)
    total = P.path_length(prims_rep)
    fall_start = total - a_out - f
    routes = []
    for phase, rid in enumerate(ids):
        if phase == 0:
            prims, rise, fall = prims_rep, a_in, fall_start
        else:
            prims, reversed_flag = _rotate_member(prims_rep, phase, campaign, rid)
            rise, fall = ((a_out, total - a_in - f) if reversed_flag
                          else (a_in, fall_start))
        route = lift_route(dict(route_id=rid, plane=campaign.record(rid)['plane'],
                                source_endpoint=campaign.record(rid)['source_endpoint'],
                                target_endpoint=campaign.record(rid)['target_endpoint']),
                           campaign.row(rid), layer, layer_z, rise, fall,
                           prims, radius=RADIUS)
        if route is None:
            return None
        routes.append(_finish_route(campaign, rid, route))
    return routes


# ---------------------------------------------------------------------------
# world helpers
# ---------------------------------------------------------------------------
def new_world():
    from ..l3d import layers as LL
    from ..l3d.world import World
    from ..fslw import config as C
    stack = LL.build_stack('medium_050')
    return stack, World(stack, clearance=C.CLEARANCE_MM)


def world_from_routes(routes):
    stack, world = new_world()
    for route in routes:
        world.add_route(route)
    return stack, world


def check_routes(world, routes):
    for route in routes:
        violations = world.check_route(route)
        if violations:
            return violations
    return []


def build_flat_world(campaign, log=print):
    stack, world = new_world()
    for rid in campaign.flat_rids:
        world.add_route(build_flat(campaign, rid))
    log(f'[{campaign.name}] adjacent flat world: {len(world.plan)} routes')
    return world


def build_opposite_single(campaign, gid, phase, a_in, a_out,
                          layer=2, layer_z=1.0):
    """One member of an opposite quartet (phase 0 is the representative)."""
    from ..fsd25d import path3d as P
    from ..v3c4.lift_cross import lift_route, transition_geometry, PORT_MARGIN_MM
    ids = campaign.group_routes(gid)
    rid = ids[phase]
    prims_rep = campaign.primitives_2d(ids[0])
    total = P.path_length(prims_rep)
    record = campaign.record(rid)
    base_z = campaign.base_z(rid)
    f = float(transition_geometry(layer_z - base_z)['footprint_mm'])
    if a_in < PORT_MARGIN_MM or a_out < PORT_MARGIN_MM:
        return None
    if phase == 0:
        prims, rise, fall = prims_rep, a_in, total - a_out - f
    else:
        prims, reversed_flag = _rotate_member(prims_rep, phase, campaign, rid)
        rise, fall = ((a_out, total - a_in - f) if reversed_flag
                      else (a_in, total - a_out - f))
    if rise + f > fall - 5.0 or fall + f > total - PORT_MARGIN_MM:
        return None
    route = lift_route(dict(route_id=rid, plane=record['plane'],
                            source_endpoint=record['source_endpoint'],
                            target_endpoint=record['target_endpoint']),
                       campaign.row(rid), layer, layer_z, rise, fall,
                       prims, radius=RADIUS)
    if route is None:
        return None
    return _finish_route(campaign, rid, route)


def build_opposite_group_fast(campaign, gid, a_in, a_out):
    routes = [build_opposite_single(campaign, gid, phase, a_in, a_out)
              for phase in range(4)]
    if any(route is None for route in routes):
        return None
    return routes


def _opposite_max_a(base_z, layer_z, total=150.0):
    from ..v3c4.lift_cross import transition_geometry
    f = float(transition_geometry(layer_z - base_z)['footprint_mm'])
    return (total - 2.0 * f - 5.0) / 2.0 - 0.1, f


def search_opposite_fast(campaign, flat_routes, log=print,
                         preferred_grid=None, max_asymmetric_attempts=2500):
    """C4-symmetric search: check the representative member only.

    The fixed layout is strict-C4, so after each accepted quartet the world stays
    C4-symmetric and checking one rotated member is equivalent to checking all
    four.  A shared a is tried first (unified transition band); groups that fail
    fall back to an asymmetric (a_in, a_out) search.
    """
    from ..l3d.world import World
    groups = list(campaign.opposite_groups)
    total_expected = len(campaign.opposite_rids)
    grid = preferred_grid
    if grid is None:
        grid = [round(50.0 + 0.8 * step, 2) for step in range(0, 20)]
        grid += [round(1.2 + 0.8 * step, 2) for step in range(0, 62)]
        seen = set()
        ordered = []
        for a in grid:
            if a in seen:
                continue
            seen.add(a)
            ordered.append(a)
        grid = ordered
    best = None
    for a in grid:
        stack, world = world_from_routes(flat_routes)
        accepted = {}
        failures = []
        for gid in groups:
            quartet = build_opposite_group_fast(campaign, gid, a, a)
            if quartet is None:
                failures.append(gid)
                continue
            violations = world.check_route(quartet[0])
            if violations:
                failures.append(gid)
                continue
            for route in quartet:
                world.add_route(route)
                accepted[int(route['route_id'])] = route
        achieved = len(accepted) // 4
        log(f'[{campaign.name}] opposite shared a={a}: {achieved}/{len(groups)}')
        if best is None or len(accepted) > best['route_count']:
            best = dict(a=float(a), routes=accepted,
                        route_count=len(accepted),
                        groups_solved=achieved,
                        groups_expected=len(groups),
                        failures=list(failures))
        if len(accepted) == total_expected:
            break
    # asymmetric fallback for the remaining groups of the best shared-a pass
    stack, world = world_from_routes(flat_routes + list(best['routes'].values()))
    solved_groups = []
    failures = list(best['failures'])
    for gid in failures:
        ids = campaign.group_routes(gid)
        base_z = campaign.base_z(ids[0])
        max_a, f = _opposite_max_a(base_z, 1.0, 150.0)
        pairs = []
        for step in range(0, 70):
            a_in = round(1.2 + 0.6 * step, 2)
            if a_in > max_a:
                break
            for other in range(0, 70):
                a_out = round(1.2 + 0.6 * other, 2)
                if a_out > max_a:
                    break
                if a_in + f > 150.0 - a_out - f - 5.0:
                    continue
                pairs.append((abs(a_in - 50.0) + abs(a_out - 50.0), a_in, a_out))
        pairs.sort()
        accepted = None
        for _, a_in, a_out in pairs[:max_asymmetric_attempts]:
            member = build_opposite_single(campaign, gid, 0, a_in, a_out)
            if member is None or world.check_route(member):
                continue
            quartet = build_opposite_group_fast(campaign, gid, a_in, a_out)
            if quartet is None:
                continue
            accepted = (quartet, a_in, a_out)
            break
        if accepted is None:
            log(f'[{campaign.name}] opposite group {gid}: unsolved (asymmetric)')
            continue
        quartet, a_in, a_out = accepted
        for route in quartet:
            world.add_route(route)
            best['routes'][int(route['route_id'])] = route
        solved_groups.append(gid)
    best['route_count'] = len(best['routes'])
    best['groups_solved'] = best['route_count'] // 4
    log(f'[{campaign.name}] opposite best: shared a={best["a"]}, '
        f'{best["groups_solved"]}/{best["groups_expected"]} groups, '
        f'{best["route_count"]}/{total_expected} routes')
    return best




# ---------------------------------------------------------------------------
# per-group feasibility scan + greedy C4-symmetric assembly (opposite stage)
# ---------------------------------------------------------------------------
def opposite_symmetric_values(base_z, step=0.4, layer_z=1.0, total=150.0):
    max_a, f = _opposite_max_a(base_z, layer_z, total)
    values = []
    a = 1.2
    while a <= max_a + 1e-9:
        values.append(round(a, 2))
        a += step
    return values, f


def solve_opposite_group(campaign, world, gid, symmetric_values, f,
                         max_asym_pairs=1500, max_sym_solutions=400):
    """Feasible (a_in, a_out) pairs for one opposite quartet (rep member only)."""
    feasible = []
    for a in symmetric_values:
        member = build_opposite_single(campaign, gid, 0, a, a)
        if member is None:
            continue
        if not world.check_route(member):
            feasible.append((float(a), float(a)))
            if len(feasible) >= max_sym_solutions:
                break
    if feasible:
        return feasible
    max_a, _ = _opposite_max_a(campaign.base_z(campaign.group_routes(gid)[0]), 1.0)
    pairs = []
    for step_i in range(0, 80):
        a_in = round(1.2 + 0.6 * step_i, 2)
        if a_in > max_a:
            break
        for step_o in range(0, 80):
            a_out = round(1.2 + 0.6 * step_o, 2)
            if a_out > max_a:
                break
            if a_in + f > 150.0 - a_out - f - 5.0:
                continue
            pairs.append((abs(a_in - 50.0) + abs(a_out - 50.0), a_in, a_out))
    pairs.sort()
    for _, a_in, a_out in pairs[:max_asym_pairs]:
        member = build_opposite_single(campaign, gid, 0, a_in, a_out)
        if member is None:
            continue
        if not world.check_route(member):
            feasible.append((float(a_in), float(a_out)))
            if len(feasible) >= 40:
                break
    return feasible


_OPP_STATE = {}


def _init_opposite_worker(campaign_dir, swap_rows):
    from four_side_1024.v3c4.profile import apply
    apply()
    campaign = StructuredCampaign(swap_rows=swap_rows, campaign_dir=campaign_dir)
    flat_routes = [build_flat(campaign, rid) for rid in campaign.flat_rids]
    stack, world = world_from_routes(flat_routes)
    _OPP_STATE.clear()
    _OPP_STATE.update(campaign=campaign, world=world, flat_routes=flat_routes)


def _solve_opposite_task(gid):
    campaign = _OPP_STATE['campaign']
    world = _OPP_STATE['world']
    values, f = opposite_symmetric_values(campaign.base_z(campaign.group_routes(gid)[0]))
    feasible = solve_opposite_group(campaign, world, gid, values, f)
    return int(gid), feasible


def scan_opposite_feasibility(campaign, processes=12):
    import multiprocessing as mp
    tasks = list(campaign.opposite_groups)
    with mp.Pool(processes=processes, initializer=_init_opposite_worker,
                 initargs=(str(campaign.campaign_dir), campaign.swap_rows)) as pool:
        results = pool.map(_solve_opposite_task, tasks, chunksize=1)
    return {int(gid): list(pairs) for gid, pairs in results}


def assemble_opposite_stage(campaign, flat_routes, feasibility, log=print):
    """Pick a shared a where possible, then greedily assemble with per-group fallbacks."""
    groups = list(campaign.opposite_groups)
    # shared-a votes
    votes = Counter()
    for gid in groups:
        for a_in, a_out in feasibility.get(gid, []):
            if abs(a_in - a_out) <= 1e-9:
                votes[round(a_in, 2)] += 1
    shared_top = votes.most_common(10) if votes else []
    log(f'[{campaign.name}] opposite shared-a votes: {shared_top[:6]}')
    best = None
    orders = [list(groups), list(reversed(groups))]
    if shared_top:
        preferred = max(shared_top, key=lambda item: (item[1], -abs(item[0] - 50.0)))[0]
        orders.append(sorted(groups, key=lambda gid: (
            0 if (preferred, preferred) in feasibility.get(gid, []) else 1, gid)))
    for order_index, order in enumerate(orders):
        stack, world = world_from_routes(flat_routes)
        accepted = {}
        params = {}
        exceptions = {}
        for gid in order:
            chosen = feasibility.get(gid, [])
            # prefer a shared-a param if feasible
            shared_pairs = [pair for pair in chosen if abs(pair[0] - pair[1]) <= 1e-9]
            preferred_pairs = sorted(chosen, key=lambda pair: (
                0 if pair in shared_pairs else 1,
                abs(pair[0] - 50.0) + abs(pair[1] - 50.0)))
            solved = None
            for pair in preferred_pairs:
                member = build_opposite_single(campaign, gid, 0, pair[0], pair[1])
                if member is None or world.check_route(member):
                    continue
                quartet = build_opposite_group_fast(campaign, gid, pair[0], pair[1])
                if quartet is None:
                    continue
                solved = (quartet, pair)
                break
            if solved is None:
                exceptions[gid] = 'flat_fallback'
                # legal fallback: keep the quartet as a plain interface flat route
                quartet = [build_flat(campaign, rid) for rid in campaign.group_routes(gid)]
                if check_routes(world, quartet):
                    exceptions[gid] = 'flat_fallback_conflict'
                    continue
                for route in quartet:
                    world.add_route(route)
                continue
            quartet, pair = solved
            for route in quartet:
                world.add_route(route)
                accepted[int(route['route_id'])] = route
            params[gid] = dict(a_in=pair[0], a_out=pair[1])
        score = len(accepted)
        log(f'[{campaign.name}] opposite assemble order#{order_index}: '
            f'{len(accepted) // 4}/{len(groups)} groups, exceptions={len(exceptions)}')
        if best is None or score > best['route_count']:
            best = dict(routes=accepted, params=params, exceptions=exceptions,
                        route_count=score, groups_solved=score // 4,
                        groups_expected=len(groups), order_index=order_index)
        if len(accepted) == len(campaign.opposite_rids):
            break
    if shared_top:
        best['shared_a'] = max(shared_top,
                               key=lambda item: (item[1], -abs(item[0] - 50.0)))[0]
    else:
        best['shared_a'] = None
    return best


def _opposite_group_flat(campaign, gid):
    return [build_flat(campaign, rid) for rid in campaign.group_routes(gid)]


def _insert_opposite_group(campaign, world, gid, feasibility, shared_a,
                           max_precomputed=40, max_dynamic_asym=120):
    """Try to insert one opposite quartet into the current world."""
    pairs = list(feasibility.get(gid, []))
    if shared_a is not None:
        shared = [pair for pair in pairs
                  if abs(pair[0] - shared_a) <= 1e-9 and abs(pair[1] - shared_a) <= 1e-9]
        others = [pair for pair in pairs if pair not in shared]
        others.sort(key=lambda pair: abs(pair[0] - shared_a) + abs(pair[1] - shared_a))
        pairs = shared + others
    for a_in, a_out in pairs[:max_precomputed]:
        member = build_opposite_single(campaign, gid, 0, a_in, a_out)
        if member is None or world.check_route(member):
            continue
        quartet = build_opposite_group_fast(campaign, gid, a_in, a_out)
        if quartet is not None and not check_quartet_internal(quartet):
            return quartet, (a_in, a_out), 'precomputed'
    # dynamic search against the current (grown) world
    ids = campaign.group_routes(gid)
    values, f = opposite_symmetric_values(campaign.base_z(ids[0]))
    dynamic = solve_opposite_group(campaign, world, gid, values, f,
                                   max_asym_pairs=max_dynamic_asym)
    if shared_a is not None:
        dynamic.sort(key=lambda pair: abs(pair[0] - shared_a) + abs(pair[1] - shared_a))
    for a_in, a_out in dynamic[:max_precomputed]:
        member = build_opposite_single(campaign, gid, 0, a_in, a_out)
        if member is None or world.check_route(member):
            continue
        quartet = build_opposite_group_fast(campaign, gid, a_in, a_out)
        if quartet is not None and not check_quartet_internal(quartet):
            return quartet, (a_in, a_out), 'dynamic'
    return None, None, None


def _assemble_opposite_order(campaign, flat_routes, feasibility, order, shared_a,
                             log=print):
    stack, world = world_from_routes(flat_routes)
    accepted = {}
    params = {}
    exceptions = {}
    flat_fallbacks = {}
    for gid in order:
        quartet, pair, origin = _insert_opposite_group(campaign, world, gid,
                                                       feasibility, shared_a)
        if quartet is None:
            flat_quartet = _opposite_group_flat(campaign, gid)
            violations = check_routes(world, flat_quartet)
            if violations:
                exceptions[int(gid)] = 'flat_fallback_conflict'
                continue
            for route in flat_quartet:
                world.add_route(route)
                flat_fallbacks[int(route['route_id'])] = route
            exceptions[int(gid)] = 'flat_fallback'
            continue
        for route in quartet:
            world.add_route(route)
            accepted[int(route['route_id'])] = route
        params[int(gid)] = dict(a_in=float(pair[0]), a_out=float(pair[1]),
                                origin=origin)
    return dict(world=world, routes=accepted, params=params, exceptions=exceptions,
                flat_fallbacks=flat_fallbacks, groups_solved=len(accepted) // 4,
                groups_expected=len(campaign.opposite_groups))


def assemble_opposite_stage2(campaign, flat_routes, feasibility, log=print,
                             n_random_orders=4):
    """Conflict-directed ordering + random restarts for the opposite stage."""
    import random
    groups = list(campaign.opposite_groups)
    votes = Counter()
    for gid in groups:
        for a_in, a_out in feasibility.get(gid, []):
            if abs(a_in - a_out) <= 1e-9:
                votes[round(a_in, 2)] += 1
    shared_top = votes.most_common(10) if votes else []
    shared_a = max(shared_top, key=lambda item: (item[1], -abs(item[0] - 50.0)))[0] \
        if shared_top else None
    log(f'[{campaign.name}] opposite shared-a votes: {shared_top[:6]}, '
        f'shared_a={shared_a}')
    orders = [list(groups), list(reversed(groups))]
    for seed in range(n_random_orders):
        random.seed(seed)
        shuffled = list(groups)
        random.shuffle(shuffled)
        orders.append(shuffled)
    best = None
    seen = set()
    for iteration in range(7):
        if iteration < len(orders):
            order = orders[iteration]
        else:
            if not best or not best['exceptions']:
                break
            order = list(best['exceptions']) + [gid for gid in groups
                                                if gid not in best['exceptions']]
        key = tuple(order)
        if key in seen:
            continue
        seen.add(key)
        result = _assemble_opposite_order(campaign, flat_routes, feasibility,
                                          order, shared_a)
        log(f'[{campaign.name}] opposite order#{iteration}: '
            f'{result["groups_solved"]}/{result["groups_expected"]} groups, '
            f'exceptions={len(result["exceptions"])}')
        if best is None or result['groups_solved'] > best['groups_solved']:
            best = result
            best['order'] = order
        if not best['exceptions']:
            break
    best['shared_a'] = shared_a
    best['votes'] = votes
    log(f'[{campaign.name}] opposite final: {best["groups_solved"]}/'
        f'{best["groups_expected"]} groups, exceptions={best["exceptions"]}')
    return best


def _reserved_l2_lines(campaign):
    from ..l3d.world import World
    routes = {}
    for rid in campaign.opposite_rids:
        record = campaign.record(rid)
        routes[int(rid)] = World.flat_route(int(rid), record['plane'],
                                           campaign.primitives_2d(rid), 1.0,
                                           layer_id=2, row=campaign.row(rid))
    return routes


_RES_STATE = {}


def _init_reserved_worker(campaign_dir, swap_rows):
    from four_side_1024.v3c4.profile import apply
    apply()
    campaign = StructuredCampaign(swap_rows=swap_rows, campaign_dir=campaign_dir)
    flat_routes = [build_flat(campaign, rid) for rid in campaign.flat_rids]
    reserved = _reserved_l2_lines(campaign)
    _RES_STATE.clear()
    _RES_STATE.update(campaign=campaign, flat_routes=flat_routes, reserved=reserved)


def _reserved_task(gid):
    campaign = _RES_STATE['campaign']
    own = {int(rid) for rid in campaign.group_routes(gid)}
    routes = list(_RES_STATE['flat_routes'])
    routes += [route for rid, route in _RES_STATE['reserved'].items()
               if rid not in own]
    stack, world = world_from_routes(routes)
    values, f = opposite_symmetric_values(campaign.base_z(campaign.group_routes(gid)[0]))
    feasible = solve_opposite_group(campaign, world, gid, values, f,
                                    max_asym_pairs=1200)
    return int(gid), feasible


def scan_opposite_feasibility_reserved(campaign, processes=12):
    """Feasibility assuming every other opposite line already sits on L2."""
    import multiprocessing as mp
    tasks = list(campaign.opposite_groups)
    with mp.Pool(processes=processes, initializer=_init_reserved_worker,
                 initargs=(str(campaign.campaign_dir), campaign.swap_rows)) as pool:
        results = pool.map(_reserved_task, tasks, chunksize=1)
    return {int(gid): list(pairs) for gid, pairs in results}


# ---------------------------------------------------------------------------
# same-side U stage: feasibility chains + assembly
# ---------------------------------------------------------------------------
U_BUNDLES = {
    'z1_middle': dict(gids=list(range(20, 36)), layer=3, layer_z=1.5,
                      a_min=11.2, a_pref=11.2),
    'corner1': dict(gids=list(range(144, 160)), layer=3, layer_z=1.5,
                    a_min=1.2, a_pref=6.0),
    'corner2': dict(gids=list(range(160, 176)), layer=4, layer_z=2.0,
                    a_min=1.2, a_pref=6.0),
    'z2_middle': dict(gids=list(range(176, 192)), layer=5, layer_z=2.5,
                      a_min=1.2, a_pref=1.2),
}
BUNDLE_ORDER = ['corner1', 'corner2', 'z2_middle', 'z1_middle']
BUNDLE_LABEL = {'z1_middle': 'z1 四边中间 U -> L3',
                'corner1': 'z2 第一组四角 U -> L3',
                'corner2': 'z2 第二组四角 U -> L4',
                'z2_middle': 'z2 四边中间 U -> L5'}


def group_separation(campaign, gid):
    ids = campaign.group_routes(gid)
    record = campaign.record(ids[0])
    p = campaign.port_xy(record['source_endpoint'])
    q = campaign.port_xy(record['target_endpoint'])
    return abs(p[0] - q[0]) if record['source_side'] in 'NS' else abs(p[1] - q[1])


def bundle_ranks(campaign):
    ranks = {}
    for bundle, spec in U_BUNDLES.items():
        gids = list(spec['gids'])
        gids.sort(key=lambda gid: group_separation(campaign, gid))
        ranks[bundle] = gids
    return ranks


def _depth_chain(candidates, gap=0.5):
    from .spatial_u_bundle import choose_depth_chain
    chain = choose_depth_chain(candidates, gap=gap)
    if chain is None:
        chain = choose_depth_chain(candidates, gap=0.45)
    if chain is None:
        chain = choose_depth_chain(candidates, gap=0.4)
    return chain


def _bundle_feasible(campaign, bundle, feasibility):
    spec = U_BUNDLES[bundle]
    out = {}
    for gid in spec['gids']:
        pairs = [tuple(pair) for pair in feasibility.get(gid, [])
                 if pair[0] >= spec['a_min'] - 1e-9]
        if not pairs:
            pairs = [tuple(pair) for pair in feasibility.get(gid, [])]
        out[int(gid)] = pairs
    return out


def _pick_u_entry(pairs, d_chosen, a_min, a_pref):
    options = [pair for pair in pairs if abs(pair[1] - d_chosen) <= 1e-9]
    if not options:
        return None
    options.sort(key=lambda pair: (abs(pair[0] - a_pref), pair[0]))
    return options[0]


def assemble_u_stage(campaign, base_routes, feasibility, log=print):
    """Greedy C4-symmetric assembly of the 64 U quartets on their target layers."""
    feasibility = {int(key): value for key, value in feasibility.items()}
    world = world_from_routes(base_routes)[1]
    ranks = bundle_ranks(campaign)
    u_routes = {}
    params = {}
    failures = {}
    for bundle in BUNDLE_ORDER:
        spec = U_BUNDLES[bundle]
        feas = _bundle_feasible(campaign, bundle, feasibility)
        unsolved = [gid for gid in ranks[bundle] if not feas[gid]]
        if unsolved:
            for gid in unsolved:
                failures[int(gid)] = 'no feasible (a,D) against the base world'
            log(f'[{campaign.name}] U {bundle}: {len(unsolved)} groups without '
                f'feasible parameters')
        ordered = [gid for gid in ranks[bundle] if feas[gid]]
        d_lists = [sorted({pair[1] for pair in feas[gid]}) for gid in ordered]
        chain = _depth_chain(d_lists) if d_lists else []
        if d_lists and chain is None:
            log(f'[{campaign.name}] U {bundle}: no nested depth chain, '
                f'assigning independently')
            chain = [min(values) for values in d_lists]
        for gid, d_chosen in zip(ordered, chain):
            pairs = feas[gid]
            chosen = _pick_u_entry(pairs, d_chosen, spec['a_min'], spec['a_pref'])
            candidates = [chosen] + sorted(
                [pair for pair in pairs if pair != chosen],
                key=lambda pair: (abs(pair[1] - d_chosen), abs(pair[0] - spec['a_pref'])))
            accepted = None
            for pair in candidates:
                if pair is None:
                    continue
                quartet = build_u_group(campaign, gid, spec['layer'],
                                        spec['layer_z'], pair[1], pair[0], pair[0])
                if quartet is None:
                    continue
                if check_routes(world, quartet):
                    continue
                if check_quartet_internal(quartet):
                    continue
                accepted = (pair, quartet)
                break
            if accepted is None:
                failures[int(gid)] = 'no feasible geometry against the grown world'
                log(f'[{campaign.name}] U group {gid} ({bundle}) FAILED')
                continue
            (a_chosen, d_chosen2), quartet = accepted
            for route in quartet:
                world.add_route(route)
                u_routes[int(route['route_id'])] = route
            params[int(gid)] = dict(bundle=bundle, layer=int(spec['layer']),
                                    layer_z=float(spec['layer_z']),
                                    a_in=float(a_chosen), a_out=float(a_chosen),
                                    high_arc_depth=float(d_chosen2),
                                    route_ids=[int(route['route_id'])
                                               for route in quartet])
        solved = sum(1 for gid in spec['gids'] if gid in params)
        log(f'[{campaign.name}] U {bundle}: {solved}/{len(spec["gids"])} groups on '
            f'L{spec["layer"]}')
    return dict(world=world, routes=u_routes, params=params, failures=failures)


# ---------------------------------------------------------------------------
# payload / metrics / validation
# ---------------------------------------------------------------------------
def build_payload(campaign, u_routes, opposite_routes, log=print):
    """Assemble all 1024 3D records; no original connection is changed."""
    from ..v3c4.profile import apply as _apply
    records = []
    stats = Counter()
    for rid in sorted(campaign.manifest):
        record = campaign.record(rid)
        relation = record['relation']
        if rid in u_routes:
            route = u_routes[rid]
            stats['u_rebuilt'] += 1
        elif rid in opposite_routes:
            route = opposite_routes[rid]
            stats['opposite_l2'] += 1
        else:
            route = build_flat(campaign, rid)
            if relation == OPPOSITE:
                stats['opposite_exception_flat'] += 1
            else:
                stats['adjacent_flat'] += 1
        records.append(route)
    layer_stack = _read_json(CAMPAIGN / 'phase5_dynamic_optimization/after/layer_stack.json')
    payload = dict(
        schema='four_side_1024_v2_l3d_routes_v1',
        experiment=f'MANUAL_C4_STRUCTURED_LAYER_ROUTING_{campaign.name}',
        note=('structured layered routing: adjacent -> interface; opposite -> L2 '
              'straight bundles; U quartets -> task layers L3/L3/L4/L5; every C4 '
              'quartet is rotation-atomic'),
        layer_stack=layer_stack,
        routes=records)
    log(f'[{campaign.name}] payload: {len(records)} routes {dict(stats)}')
    return payload, stats


def payload_metrics(campaign, payload, report=None):
    from ..v3c4.lift_cross import analyze_planes
    records = [record for record in payload['routes']
               if record.get('status') == 'routed']
    entries = {}
    for record in records:
        for part in record.get('parts') or []:
            if part['kind'] != 'flat':
                continue
            entries.setdefault(round(float(part['z_mm']), 6), []).append(
                (int(record['route_id']), part['primitives']))
    crossings, reports, pairs_by_plane = analyze_planes(entries,
                                                        log=lambda *a, **k: None,
                                                        compute_positions=False)
    unique_pairs = set()
    for pairs in pairs_by_plane.values():
        unique_pairs |= pairs
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
                                  plane_counts=dict(plane_users),
                                  route_ids=sorted(users))
    # same-layer U-U crossing pairs
    u_rids = {rid for gid in campaign.u_groups for rid in campaign.group_routes(gid)}
    uu_pairs = set()
    for z, plane_entries in entries.items():
        selected = [(rid, prims) for rid, prims in plane_entries if rid in u_rids]
        if len(selected) < 2:
            continue
        from ..fslw import validate_fslw as V
        prepared = [V.prepare_route(prims, rid) for rid, prims in selected]
        audit = V.audit_route_pairs(prepared, policy='strict')
        for item in audit['crossings']:
            a, b = int(item['route_a']), int(item['route_b'])
            uu_pairs.add((min(a, b), max(a, b)))
        for item in audit['violations']:
            uu_pairs.add(('violation', json.dumps(item, sort_keys=True, default=str)))
    transitions = sum(int(record.get('n_transitions') or 0) for record in records)
    total_length = round(sum(float(record.get('length_mm') or 0.0)
                             for record in records), 4)
    metrics = dict(
        routed=len(records), failed=len(payload['routes']) - len(records),
        unique_crossing_pairs=len(unique_pairs),
        same_layer_u_u_crossing_pairs=len(uu_pairs),
        transitions=int(transitions),
        total_length_mm=total_length,
        layer_counts=layer_counts,
        crossing_pairs_by_height={str(z): value['crossing_pair_count']
                                  for z, value in reports.items()},
        crossing_points_by_height={str(z): value['crossing_count']
                                   for z, value in reports.items()},
        routes_by_height={str(z): len(plane_entries)
                          for z, plane_entries in entries.items()})
    if report is not None:
        stats = report.get('stats') or {}
        metrics.update(validation_status=report.get('status'),
                       validation_exploratory_pass=report.get('exploratory_pass'),
                       validation_geometry_pass=report.get('geometry_pass'),
                       validation_counts=report.get('counts'),
                       validation_violations=len(report.get('violations') or []),
                       min_3d_clearance_mm=stats.get('min_3d_clearance_mm'),
                       min_curvature_radius_mm=stats.get('min_curvature_radius_mm'))
    return metrics


def validate_payload(payload, v4_root=None, log=print):
    from ..v3c4.lift_cross import validate_payload_v4
    return validate_payload_v4(payload, Path(v4_root or PHASE2), log=log)


def check_quartet_internal(quartet):
    """Full 3D clearance check *inside* one C4 quartet (members vs each other)."""
    if not quartet:
        return []
    stack, world = new_world()
    world.add_route(quartet[0])
    violations = []
    for route in quartet[1:]:
        violations.extend(world.check_route(route))
        world.add_route(route)
    return violations


# ---------------------------------------------------------------------------
# full-flat-world strategy: every opposite line temporarily flat at L1
# ---------------------------------------------------------------------------
def full_flat_routes(campaign, log=print):
    """Adjacent flats + every opposite connection flat on its interface plane."""
    from ..l3d.world import World
    routes = {}
    for rid in campaign.flat_rids + campaign.opposite_rids:
        record = campaign.record(rid)
        route = World.flat_route(int(rid), record['plane'],
                                 campaign.primitives_2d(rid),
                                 campaign.base_z(rid), layer_id=1,
                                 row=campaign.row(rid))
        routes[int(rid)] = _finish_route(campaign, rid, route)
    log(f'[{campaign.name}] full flat world: {len(routes)} routes')
    return routes


def check_quartet_vs_world(world, quartet):
    violations = check_routes(world, quartet)
    if violations:
        return violations
    return check_quartet_internal(quartet)


_FF_STATE = {}


def _init_fullflat_worker(campaign_dir, swap_rows):
    from four_side_1024.v3c4.profile import apply
    apply()
    campaign = StructuredCampaign(swap_rows=swap_rows, campaign_dir=campaign_dir)
    _FF_STATE.clear()
    _FF_STATE.update(campaign=campaign, flat_routes=full_flat_routes(campaign,
                                                                    log=lambda *a: None))


def _fullflat_task(gid):
    campaign = _FF_STATE['campaign']
    own = {int(rid) for rid in campaign.group_routes(gid)}
    routes = [route for rid, route in _FF_STATE['flat_routes'].items()
              if rid not in own]
    stack, world = world_from_routes(routes)
    values, f = opposite_symmetric_values(campaign.base_z(campaign.group_routes(gid)[0]))
    feasible = solve_opposite_group(campaign, world, gid, values, f,
                                    max_asym_pairs=2000)
    return int(gid), feasible


def scan_opposite_fullflat(campaign, processes=12):
    import multiprocessing as mp
    tasks = list(campaign.opposite_groups)
    with mp.Pool(processes=processes, initializer=_init_fullflat_worker,
                 initargs=(str(campaign.campaign_dir), campaign.swap_rows)) as pool:
        results = pool.map(_fullflat_task, tasks, chunksize=1)
    return {int(gid): list(pairs) for gid, pairs in results}


def assemble_opposite_fullflat(campaign, feasibility, log=print):
    """Full-flat world; per group remove its reserved flats, lift it or keep it flat."""
    flat_routes = full_flat_routes(campaign, log=log)
    world = world_from_routes(list(flat_routes.values()))[1]
    groups = list(campaign.opposite_groups)
    # order: groups with fewer feasible pairs first (fail early on hard ones)
    groups.sort(key=lambda gid: (len(feasibility.get(gid, [])), gid))
    accepted = {}
    params = {}
    exceptions = {}
    reserved_flat = {}
    for gid in groups:
        own = [int(rid) for rid in campaign.group_routes(gid)]
        stored = {rid: flat_routes[rid] for rid in own}
        for rid in own:
            world.remove_route(rid)
        accepted_quartet = None
        pairs = list(feasibility.get(gid, []))
        pairs.sort(key=lambda pair: (abs(pair[0] - pair[1]), abs(pair[0] - 50.0)))
        candidates = pairs[:80]
        for a_in, a_out in candidates:
            member = build_opposite_single(campaign, gid, 0, a_in, a_out)
            if member is None or world.check_route(member):
                continue
            quartet = build_opposite_group_fast(campaign, gid, a_in, a_out)
            if quartet is None or check_quartet_internal(quartet):
                continue
            accepted_quartet = (quartet, (a_in, a_out))
            break
        if accepted_quartet is None:
            # keep it flat at the interface (part of the original 2D layout)
            for rid in own:
                world.add_route(stored[rid])
                reserved_flat[rid] = stored[rid]
            exceptions[int(gid)] = 'kept_flat_interface'
            continue
        quartet, pair = accepted_quartet
        for route in quartet:
            world.add_route(route)
            accepted[int(route['route_id'])] = route
        params[int(gid)] = dict(a_in=float(pair[0]), a_out=float(pair[1]))
    log(f'[{campaign.name}] opposite full-flat assembly: {len(accepted)//4}/'
        f'{len(groups)} groups lifted to L2, {len(exceptions)} kept flat')
    return dict(world=world, routes=accepted, params=params,
                exceptions=exceptions, flat_routes=reserved_flat,
                groups_solved=len(accepted) // 4,
                groups_expected=len(groups))
