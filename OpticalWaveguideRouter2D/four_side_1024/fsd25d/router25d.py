"""Incremental five-layer (2.5D) router built on the two accepted 2D layouts.

Algorithm (identical rules and budget for both schemes):

1. every accepted 2D route is kept unchanged as a *flat* route at its interface
   layer (z1 -> z=0, z2 -> z=0.5);
2. the failed 2D routes that do have XY candidates are attempted in route-id
   order: every candidate is first tried flat (strict 2D rules on its layer),
   then lifted: one smooth S-curve up to a travel layer, the middle of the XY
   path propagates there and a second S-curve returns to the interface height;
3. the lift is legal only when (a) all three flat sub-chains satisfy the strict
   2D rules on their layers, (b) the transition curves keep >= 0.08 mm true 3D
   clearance to everything already placed, and (c) the route keeps 3D
   self-clearance;
4. further passes retry the remaining routes with alternative transition
   placements / layer preferences, then a bounded rip-up-and-reroute pass tries
   to recover routes blocked by previously added lifted routes.
"""
from __future__ import annotations

import json
import time
from collections import Counter

from ..fslw import ports
from ..d56.frames import build_frames
from ..v2opt import candext
from ..v2opt import ortho90 as O90
from ..v2opt.core import LayoutState
from . import config25d as CFG
from . import path3d as P
from .world25d import (ClearanceWorld3D, LayerWorld,
                       self_clearance_violations)

PLANE_OF_ROUTE = {}
for _plane in CFG.PLANES:
    _routes, _endpoints, _conn, _val = ports.load_plane('V2', _plane)
    for _route in _routes:
        PLANE_OF_ROUTE[int(_route['route_id'])] = _plane


def _part_id(route_id, index):
    return int(route_id) * 100 + int(index)


def _pass_variants(pass_index):
    if pass_index == 1:
        return (0,)
    if pass_index == 2:
        return (1, 0)
    return (2, 1, 0)


def _self_check(route):
    return self_clearance_violations(route, CFG.CLEARANCE_MM)


class Router25D:
    def __init__(self, scheme, n_layers, log=print, candidate_budget=300,
                 flat_probe=40):
        if scheme not in CFG.SCHEMES:
            raise ValueError('scheme must be A or B')
        self.scheme = scheme
        self.n_layers = int(n_layers)
        self.log = log
        self.candidate_budget = int(candidate_budget)
        self.flat_probe = int(flat_probe)
        self.z_values = list(CFG.stack(self.n_layers))
        self.interface = {plane: CFG.interface_layer(self.n_layers, plane)
                          for plane in CFG.PLANES}
        self.travel_choices = {
            plane: CFG.travel_layers(self.n_layers, plane) for plane in CFG.PLANES}
        self.layers = LayerWorld()
        self.world = ClearanceWorld3D()
        self.plan = {}
        self.frames = {}
        self.routes = {}
        self.plane_state = {}
        self.ortho_generator = None
        self.baseline_ids = set()
        self.attemptable = []
        self.no_candidate = []
        self.stats = {}
        self.last_blockers = []
        self.csv_sha256 = None

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def load(self):
        for plane in CFG.PLANES:
            data = P.load_2d_plane(self.scheme, plane)
            sha = data['payload'].get('csv_sha256')
            if sha is not None:
                if self.csv_sha256 is None:
                    self.csv_sha256 = sha
                elif self.csv_sha256 != sha:
                    raise ValueError('baseline planes disagree on the V2 CSV hash')
            self.routes.update({int(r['route_id']): r for r in data['routes']})
            self.frames.update(data['frames'])
            routes_path = CFG.baseline_plane_routes(self.scheme, plane)
            self.plane_state[plane] = LayoutState.from_history(
                'V2', plane, routes_path, log=lambda *_a, **_k: None)
            base_layer = self.interface[plane]
            base_z = self.z_values[base_layer]
            for route_id, prims in data['routed'].items():
                route = P.flat_full_route3d(route_id, plane, prims, base_layer, base_z)
                self._accept(route)
                self.baseline_ids.add(route_id)
            failed_records = data['failed']
            for route_id, record in sorted(failed_records.items()):
                reason = record.get('reason') or 'not_attempted'
                if reason == 'no_legal_candidate':
                    self.attemptable.append(route_id)
                else:
                    self.no_candidate.append(route_id)
        self.log(f'{self.scheme}/{self.n_layers}: baseline flat routes '
                 f'{len(self.baseline_ids)}, attemptable failed '
                 f'{len(self.attemptable)}, no-2D-candidate {len(self.no_candidate)}')
        return self

    def _accept(self, route):
        route_id = route['route_id']
        for index, part in enumerate(route['parts']):
            if part['kind'] == 'flat':
                self.layers.add(_part_id(route_id, index), part['primitives'],
                                part['layer'])
        self.world.add_route(route)
        self.plan[route_id] = route

    # ------------------------------------------------------------------
    # candidate generation (reuses the two frozen 2D candidate libraries)
    # ------------------------------------------------------------------
    def _candidates(self, route_id):
        plane = PLANE_OF_ROUTE[route_id]
        frame = self.frames[route_id]
        state = self.plane_state[plane]
        oracle = state.oracle_for(route_id)
        if self.scheme == 'A':
            if frame.kind == 'opposite':
                queue = candext.candidates_opposite(frame, oracle)
            else:
                queue = candext.candidates_adjacent(frame, oracle)
            for candidate in queue:
                yield candidate['family'], candidate.get('params') or {}, \
                    frame.to_world(candidate['primitives'])
        else:
            generator = self._ortho_generator()
            for candidate in generator.candidates(frame, oracle):
                yield candidate['family'], candidate.get('params') or {}, \
                    frame.to_world(candidate['primitives'])

    def _ortho_generator(self):
        if self.ortho_generator is None:
            self.ortho_generator = O90.Ortho90Generator(seed=20261019)
        return self.ortho_generator

    # ------------------------------------------------------------------
    # single route attempt
    # ------------------------------------------------------------------
    def attempt_route(self, route_id, budget=None, variants=(0, 1), flat_probe=None):
        budget = self.candidate_budget if budget is None else int(budget)
        flat_probe = self.flat_probe if flat_probe is None else int(flat_probe)
        plane = PLANE_OF_ROUTE[route_id]
        base_layer = self.interface[plane]
        base_z = self.z_values[base_layer]
        travel_layers = self.travel_choices[plane]
        blockers = set()
        evaluated = 0
        for index, (family, params, prims) in enumerate(self._candidates(route_id)):
            if evaluated >= budget:
                break
            evaluated += 1
            if flat_probe > 0 and index < flat_probe:
                evaluation = self.layers.evaluate(prims, base_layer)
                if evaluation is not None and evaluation.valid:
                    route = P.flat_full_route3d(route_id, plane, prims,
                                                base_layer, base_z)
                    violations = self.world.check_route(route, check_self=True)
                    if not violations:
                        route['family'] = family
                        route['params'] = params
                        route['mode'] = 'flat'
                        return route, dict(blockers=[], evaluated=evaluated)
                elif evaluation is not None:
                    blockers.update(evaluation.blockers)
            for variant in variants:
                for travel_layer in travel_layers:
                    travel_z = self.z_values[travel_layer]
                    route = P.build_route3d(route_id, plane, prims, base_layer,
                                            base_z, travel_layer, travel_z,
                                            variant=variant)
                    if route is None:
                        continue
                    if not self._flat_parts_legal(route, blockers):
                        continue
                    violations = self.world.check_route(route, check_self=False)
                    if violations:
                        for violation in violations:
                            if violation.get('other_route') is not None:
                                blockers.add(violation['other_route'])
                        continue
                    self_violations = _self_check(route)
                    if self_violations:
                        continue
                    route['family'] = family
                    route['params'] = params
                    route['mode'] = 'lifted'
                    route['travel_layer'] = travel_layer
                    route['travel_z_mm'] = travel_z
                    return route, dict(blockers=list(blockers),
                                       evaluated=evaluated)
        self.last_blockers = list(blockers)
        return None, dict(blockers=list(blockers), evaluated=evaluated)

    def _flat_parts_legal(self, route, blockers):
        for part in route['parts']:
            if part['kind'] != 'flat':
                continue
            evaluation = self.layers.evaluate(part['primitives'], part['layer'])
            if evaluation is not None and not evaluation.valid:
                blockers.update(evaluation.blockers)
                return False
        return True

    # ------------------------------------------------------------------
    # routing passes and bounded rip-up-and-reroute
    # ------------------------------------------------------------------
    def run(self, passes=3, rr_rounds=2, rr_targets=64, rr_rip=2, log=None):
        log = log or self.log
        started = time.perf_counter()
        pending = list(self.attemptable)
        pass_history = []
        for pass_index in range(1, passes + 1):
            remaining = []
            placed = 0
            for route_id in pending:
                route, info = self.attempt_route(
                    route_id, variants=_pass_variants(pass_index))
                if route is not None:
                    self._accept(route)
                    placed += 1
                else:
                    remaining.append(route_id)
            pass_history.append(dict(pass_index=pass_index,
                                     attempted=len(pending), placed=placed,
                                     pending=len(remaining),
                                     seconds=round(time.perf_counter() - started, 2)))
            log(f'{self.scheme}/{self.n_layers} pass {pass_index}: attempted='
                f'{len(pending)} placed={placed} pending={len(remaining)} '
                f'routed={len(self.plan)} elapsed='
                f'{time.perf_counter() - started:.1f}s')
            pending = remaining
            if not pending:
                break
        rr_history = []
        for round_index in range(1, rr_rounds + 1):
            if not pending:
                break
            gain, pending = self._rr_round(pending, targets=rr_targets, rip=rr_rip,
                                           log=log)
            rr_history.append(dict(round=round_index, gain=gain,
                                   pending=len(pending),
                                   routed=len(self.plan)))
            log(f'{self.scheme}/{self.n_layers} rr round {round_index}: gain={gain} '
                f'pending={len(pending)} routed={len(self.plan)}')
            if gain == 0:
                break
        self.stats = dict(
            scheme=self.scheme, n_layers=self.n_layers,
            baseline_routed=len(self.baseline_ids),
            final_routed=len(self.plan),
            new_routed=len(self.plan) - len(self.baseline_ids),
            attemptable=len(self.attemptable),
            no_candidate=len(self.no_candidate),
            failed_no_candidate=len(self.no_candidate),
            failed_unplaceable=len(pending),
            passes=pass_history, rr=rr_history,
            seconds=round(time.perf_counter() - started, 2))
        return self.stats

    def _remove(self, route_id):
        route = self.plan.pop(route_id, None)
        if route is None:
            return None
        for index, part in enumerate(route['parts']):
            if part['kind'] == 'flat':
                part_id = _part_id(route_id, index)
                self.layers.index(part['layer']).remove(part_id)
                self.layers.parts.get(part['layer'], {}).pop(part_id, None)
        return route

    def _rebuild_world(self):
        self.world = ClearanceWorld3D()
        for route in self.plan.values():
            self.world.add_route(route)

    def _rr_round(self, pending, targets, rip, log):
        gain = 0
        remaining = list(pending)
        original_count = len(self.plan)
        target_list = list(remaining[:targets])
        for route_id in target_list:
            if route_id in self.plan:
                if route_id in remaining:
                    remaining.remove(route_id)
                continue
            route, info = self.attempt_route(route_id, budget=self.candidate_budget * 2)
            if route is not None:
                self._accept(route)
                remaining.remove(route_id)
                gain += 1
                continue
            blockers = [blocker for blocker in info.get('blockers') or []
                        if blocker in self.plan and self.plan[blocker].get('lifted')]
            if not blockers:
                continue
            ripped_ids = blockers[:rip]
            ripped = {}
            for ripped_id in ripped_ids:
                ripped[ripped_id] = self._remove(ripped_id)
            self._rebuild_world()
            route, _info = self.attempt_route(route_id,
                                              budget=self.candidate_budget * 2,
                                              variants=(0, 1, 2))
            if route is not None:
                self._accept(route)
                for ripped_id, ripped_route in ripped.items():
                    if ripped_route is None:
                        continue
                    replaced, _info2 = self.attempt_route(
                        ripped_id, budget=self.candidate_budget,
                        variants=(0, 1, 2))
                    if replaced is not None:
                        self._accept(replaced)
            if len(self.plan) > original_count:
                gain += len(self.plan) - original_count
                original_count = len(self.plan)
                remaining.remove(route_id)
                # routes lost by the committed transaction go back to the queue
                for ripped_id, ripped_route in ripped.items():
                    if ripped_route is not None and ripped_id not in self.plan:
                        if ripped_id not in remaining:
                            remaining.append(ripped_id)
            else:
                # rollback: remove whatever was placed and restore ripped routes
                for identifier in [route_id] + ripped_ids:
                    if identifier in self.plan:
                        self._remove(identifier)
                for ripped_id, ripped_route in ripped.items():
                    if ripped_route is not None:
                        self._accept(ripped_route)
                self._rebuild_world()
        return gain, remaining

    # ------------------------------------------------------------------
    # output
    # ------------------------------------------------------------------
    def routes_payload(self):
        records = []
        for route_id in sorted(self.routes):
            plane = PLANE_OF_ROUTE[route_id]
            frame = self.frames[route_id]
            start, start_dir, end, end_dir = P.port_pose(frame, plane)
            base_layer = self.interface[plane]
            base_z = self.z_values[base_layer]
            route = self.plan.get(route_id)
            if route is None:
                reason = ('no_2d_candidate' if route_id in self.no_candidate
                          else 'no_lift_candidate')
                records.append(dict(
                    route_id=route_id, plane=plane,
                    pair=self.routes[route_id]['pair'],
                    relation=self.routes[route_id]['relation'],
                    status='failed', reason=reason,
                    baseline_2d=(route_id in self.baseline_ids),
                    interface_layer=base_layer, interface_z_mm=base_z,
                    port=dict(p=[round(start[0], 6), round(start[1], 6)],
                              q=[round(end[0], 6), round(end[1], 6)],
                              start_tangent=[round(start_dir[0], 6),
                                             round(start_dir[1], 6)],
                              end_tangent=[round(end_dir[0], 6),
                                           round(end_dir[1], 6)])))
                continue
            parts = []
            for part in route['parts']:
                if part['kind'] == 'flat':
                    parts.append(dict(kind='flat', layer=int(part['layer']),
                                      z_mm=round(float(part['z_mm']), 9),
                                      length_mm=round(float(part['length_mm']), 6),
                                      primitives=[P.clean_primitive(p)
                                                  for p in part['primitives']]))
                else:
                    parts.append(dict(
                        kind='transition',
                        start=[round(value, 9) for value in part['start']],
                        end=[round(value, 9) for value in part['end']],
                        direction=[round(value, 9) for value in part['direction']],
                        z0_mm=round(float(part['z0']), 9),
                        z1_mm=round(float(part['z1']), 9),
                        dz_mm=round(float(part['dz_mm']), 9),
                        radius_mm=round(float(part['radius_mm']), 9),
                        footprint_mm=round(float(part['footprint_mm']), 9),
                        length_mm=round(float(part['length_mm']), 6)))
            summary = P.summarize_route(route)
            record = dict(
                route_id=route_id, plane=plane,
                pair=self.routes[route_id]['pair'],
                relation=self.routes[route_id]['relation'],
                status='routed',
                baseline_2d=(route_id in self.baseline_ids),
                mode=route.get('mode', 'flat'),
                family=route.get('family'),
                params=route.get('params') or {},
                interface_layer=base_layer, interface_z_mm=base_z,
                port=dict(p=[round(start[0], 6), round(start[1], 6)],
                          q=[round(end[0], 6), round(end[1], 6)],
                          start_tangent=[round(start_dir[0], 6),
                                         round(start_dir[1], 6)],
                          end_tangent=[round(end_dir[0], 6),
                                       round(end_dir[1], 6)]),
                parts=parts)
            record.update(summary)
            records.append(record)
        z_layers = [round(value, 9) for value in self.z_values]
        routed = [record for record in records if record['status'] == 'routed']
        lifted = [record for record in routed if record.get('lifted')]
        transitions = sum(int(record['n_transitions']) for record in routed)
        total_length = sum(float(record['length_mm']) for record in routed)
        total_xy_length = sum(float(record['xy_length_mm']) for record in routed)
        layer_counts = Counter()
        for record in routed:
            for part in record['parts']:
                if part['kind'] == 'flat':
                    layer_counts[part['layer']] += 1
        return dict(
            schema='four_side_1024_v2_25d_routes_v1',
            experiment='V2 five-layer 2.5D',
            topology='V2',
            csv_sha256=self.csv_sha256,
            scheme=self.scheme,
            scheme_label=CFG.SCHEMES[self.scheme]['label'],
            xy_model=CFG.SCHEMES[self.scheme]['xy_model'],
            n_layers=self.n_layers,
            layers_z_mm=z_layers,
            interface_layer={plane: self.interface[plane] for plane in CFG.PLANES},
            process=dict(board_mm=[CFG.BOARD_MM, CFG.BOARD_MM],
                         width_mm=CFG.WIDTH_MM, edge_gap_mm=CFG.EDGE_GAP_MM,
                         clearance_mm=CFG.CLEARANCE_MM,
                         radius_mm=CFG.RADIUS_MM,
                         min_cross_angle_deg=CFG.MIN_CROSS_ANGLE_DEG,
                         crossing_policy=CFG.CROSSING_POLICY),
            budget=dict(candidate_budget=self.candidate_budget,
                        flat_probe=self.flat_probe),
            statistics=dict(
                baseline_routed=len(self.baseline_ids),
                routed=len(routed),
                new_routed=len(routed) - len(self.baseline_ids),
                lifted=len(lifted),
                flat_added=len(routed) - len(self.baseline_ids) - len(lifted),
                transitions=int(transitions),
                total_length_mm=round(total_length, 6),
                mean_length_mm=round(total_length / len(routed), 6) if routed else None,
                total_xy_length_mm=round(total_xy_length, 6),
                per_plane={plane: dict(
                    routed=sum(1 for record in routed
                               if record['plane'] == plane),
                    baseline=sum(1 for record in routed
                                 if record['plane'] == plane
                                 and record['baseline_2d']),
                    lifted=sum(1 for record in routed
                               if record['plane'] == plane and record['lifted']))
                    for plane in CFG.PLANES},
                per_layer_flat_parts={str(layer): int(layer_counts.get(layer, 0))
                                      for layer in range(self.n_layers)},
                failed_no_candidate=len(self.no_candidate),
                failed_unplaceable=self.stats.get('failed_unplaceable')),
            router=self.stats,
            routes=records)
