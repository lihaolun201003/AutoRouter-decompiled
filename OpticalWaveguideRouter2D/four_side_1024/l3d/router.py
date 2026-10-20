"""Incremental 3D router for the corrected L1–L5 physical model.

Stages
------
1. baseline (elsewhere): all accepted R15 2D routes are flat L1 routes at their
   true row height (z=0.0 / z=0.5).
2. ``single``: each failed route may climb once to L2..L5 and return to its L1
   row height (all four layer choices are compared, not just the first legal one).
3. ``multi``: additionally allows multiple transitions / arbitrary layer
   sequences (L1→Li→Lj→…→L1) and compares feasible realizations.
4. ``full``: adds a bounded rip-up-and-reroute transaction that may also
   re-layer already accepted routes.

Every candidate is checked against the true-XYZ world (same-physical-plane strict
2D rules; different physical planes require >= 0.08 mm true 3D distance).
"""
from __future__ import annotations

import time
from collections import Counter

from ..d56.frames import build_frames
from ..fslw import config as C
from ..fslw import ports
from ..v2opt import candext
from ..v2opt import ortho90 as O90
from ..v2opt.core import LayoutState
from . import common, layers
from . import paths as LP
from .common import PLANES, ROW_OF_PLANE
from .world import World


def _pass_variants(pass_index, stage):
    if pass_index == 1:
        return (0,)
    if pass_index == 2:
        return (1, 0)
    return (2, 1, 0)


def _score(record):
    return (int(record['n_transitions']), float(record['length_mm']),
            int(max(record['layer_sequence'])), int(record['route_id']))


class Router:
    def __init__(self, scheme, layer_stack, log=print, candidate_budget=120,
                 multi_budget=60, layer_selection='best', flat_probe=8,
                 multi_only=False):
        self.scheme = scheme
        self.stack = layer_stack
        self.log = log
        self.candidate_budget = int(candidate_budget)
        self.multi_budget = int(multi_budget)
        self.layer_selection = layer_selection
        self.flat_probe = int(flat_probe)
        self.multi_only = bool(multi_only)
        self.world = World(layer_stack)
        self.plan = {}
        self.routes = {}
        self.frames = {}
        self.plane_of = {}
        self.plane_state = {}
        self.baseline_ids = set()
        self.attemptable = []
        self.no_candidate = []
        self.stats = {}
        self.last_blockers = []
        self.csv_sha256 = None
        self.ortho_generator = None
        self.rejected = Counter()
        for plane in PLANES:
            plane_routes, _endpoints, _conn, _val = ports.load_plane('V2', plane)
            for record in plane_routes:
                self.plane_of[int(record['route_id'])] = plane

    # ------------------------------------------------------------------
    def load(self):
        for plane in PLANES:
            data = common.load_r15_plane(self.scheme, plane)
            if self.csv_sha256 is None:
                self.csv_sha256 = data['csv_sha256']
            elif self.csv_sha256 != data['csv_sha256']:
                raise ValueError('the two R15 planes disagree on the CSV hash')
            self.routes.update({int(record['route_id']): record
                                for record in data['routes']})
            self.frames.update(data['frames'])
            self.plane_state[plane] = data['state']
            for route_id in sorted(data['routed']):
                record = common.build_flat_record(
                    route_id, plane, data['routed'][route_id],
                    data['frames'][route_id])
                self._accept(record)
                self.baseline_ids.add(route_id)
            for route_id, failed in sorted(data['failed'].items()):
                reason = failed.get('reason') or 'not_attempted'
                if reason == 'no_legal_candidate':
                    self.attemptable.append(route_id)
                else:
                    self.no_candidate.append(route_id)
        self.log(f'{self.scheme}/{self.stack.name}: corrected L1 baseline '
                 f'{len(self.baseline_ids)} flat routes, attemptable failed '
                 f'{len(self.attemptable)}, no-2D-candidate {len(self.no_candidate)}')
        return self

    def _accept(self, record):
        self.world.add_route(record)
        self.plan[int(record['route_id'])] = record

    def _remove(self, route_id):
        route = self.world.remove_route(route_id)
        self.plan.pop(int(route_id), None)
        return route

    # ------------------------------------------------------------------
    def _candidates(self, route_id):
        plane = self.plane_of[int(route_id)]
        frame = self.frames[route_id]
        state = self.plane_state[plane]
        oracle = state.oracle_for(route_id)
        if self.scheme == 'A':
            if frame.kind == 'opposite':
                queue = candext.candidates_opposite(frame, oracle)
            else:
                queue = candext.candidates_adjacent(frame, oracle)
            for candidate in queue:
                yield (candidate['family'], candidate.get('params') or {},
                       frame.to_world(candidate['primitives']))
        else:
            generator = self._ortho_generator()
            for candidate in generator.candidates(frame, oracle):
                yield (candidate['family'], candidate.get('params') or {},
                       frame.to_world(candidate['primitives']))

    def _ortho_generator(self):
        if self.ortho_generator is None:
            self.ortho_generator = O90.Ortho90Generator(seed=20261019)
        return self.ortho_generator

    # ------------------------------------------------------------------
    def _plans(self, stage):
        if stage == 'single':
            return layers.plan_sequences('single')
        if stage == 'multi':
            return layers.plan_sequences('multi')
        return layers.plan_sequences('multi')

    def _build_record(self, route_id, plane, prims, sequence, variant):
        frame = self.frames[route_id]
        z_sequence = self.stack.z_sequence_for(sequence, row=plane)
        route = LP.build_route_l3d(
            route_id, plane, prims, sequence, z_sequence,
            common.port_meta(plane, frame), radius=float(C.RADIUS_MM),
            variant=int(variant))
        if route is None:
            return None, 'transition_placement_infeasible'
        errors = World.check_structure(route)
        if errors:
            return None, 'structure:' + ','.join(errors[:2])
        record = common.route_to_record(route, frame)
        record['mode'] = ('flat_l1' if record['n_transitions'] == 0 else 'lifted')
        return record, None

    def attempt_route(self, route_id, budget=None, stage='single',
                      variants=(0,)):
        route_id = int(route_id)
        budget = self.candidate_budget if budget is None else int(budget)
        plane = self.plane_of[route_id]
        row_z = self.stack.interface.z_for_row(plane)
        selected_plans = self._plans(stage)
        singles = [plan for plan in selected_plans if len(plan) == 3]
        multiples = [plan for plan in selected_plans if len(plan) > 3]
        blockers = set()
        evaluated = 0
        for index, (family, params, prims) in enumerate(self._candidates(route_id)):
            if evaluated >= budget:
                break
            evaluated += 1
            # cheap same-plane probe of the untouched 2D shape at L1
            if index < self.flat_probe:
                evaluation = self.world.check_flat(prims, row_z)
                if evaluation is not None and not evaluation.valid:
                    blockers.update(getattr(evaluation, 'blockers', []) or [])
                elif evaluation is not None and evaluation.valid:
                    flat = World.flat_route(route_id, plane, prims, row_z)
                    flat['family'] = family
                    flat['params'] = params
                    record = common.route_to_record(flat, self.frames[route_id])
                    record['mode'] = 'flat_l1'
                    record['baseline_2d'] = False
                    return record, dict(blockers=list(blockers),
                                        evaluated=evaluated, plans_tried=0)
            feasible = []
            if self.multi_only:
                plans = multiples
            else:
                plans = singles if stage == 'single' else singles
            for sequence in plans:
                for variant in variants:
                    record, error = self._build_record(route_id, plane, prims,
                                                       sequence, variant)
                    if record is None:
                        if error:
                            self.rejected[error.split(':')[0]] += 1
                        continue
                    violations = self.world.check_route(record, check_self=True)
                    if violations:
                        for violation in violations:
                            if violation.get('other_route') is not None:
                                blockers.add(int(violation['other_route']))
                            for blocker in violation.get('blockers') or []:
                                blockers.add(int(blocker))
                        continue
                    record['family'] = family
                    record['params'] = params
                    feasible.append(record)
                    if self.layer_selection == 'first':
                        break
                if feasible and self.layer_selection == 'first':
                    break
            if (not feasible and stage != 'single' and multiples
                    and not self.multi_only):
                if evaluated > self.multi_budget:
                    continue
                for sequence in multiples:
                    for variant in variants:
                        record, error = self._build_record(
                            route_id, plane, prims, sequence, variant)
                        if record is None:
                            continue
                        violations = self.world.check_route(record,
                                                            check_self=True)
                        if violations:
                            continue
                        record['family'] = family
                        record['params'] = params
                        feasible.append(record)
                        if self.layer_selection == 'first':
                            break
                    if feasible and self.layer_selection == 'first':
                        break
            if feasible:
                feasible.sort(key=_score)
                return feasible[0], dict(blockers=list(blockers),
                                         evaluated=evaluated,
                                         feasible_layers=len(feasible))
        self.last_blockers = list(blockers)
        return None, dict(blockers=list(blockers), evaluated=evaluated,
                          feasible_layers=0)

    # ------------------------------------------------------------------
    def run(self, passes=3, rr_rounds=1, rr_targets=48, rr_rip=2,
            stage='full', limit=0):
        started = time.perf_counter()
        pending = list(self.attemptable)
        if limit:
            pending = pending[:int(limit)]
        pass_history = []
        for pass_index in range(1, passes + 1):
            pass_stage = ('single' if stage == 'single'
                          else ('single' if pass_index == 1 else 'multi'))
            variants = _pass_variants(pass_index, pass_stage)
            remaining = []
            placed = 0
            for route_id in pending:
                record, info = self.attempt_route(
                    route_id, budget=self.candidate_budget,
                    stage=pass_stage, variants=variants)
                if record is not None:
                    self._accept(record)
                    placed += 1
                else:
                    remaining.append(route_id)
            pass_history.append(dict(
                pass_index=pass_index, stage=pass_stage,
                variants=list(variants), attempted=len(pending),
                placed=placed, pending=len(remaining),
                routed=len(self.plan),
                seconds=round(time.perf_counter() - started, 2)))
            self.log(f'{self.scheme}/{self.stack.name} pass {pass_index} '
                     f'({pass_stage}): attempted={len(pending)} placed={placed} '
                     f'pending={len(remaining)} routed={len(self.plan)} '
                     f'elapsed={time.perf_counter() - started:.1f}s')
            pending = remaining
            if not pending:
                break
        rr_history = []
        for round_index in range(1, int(rr_rounds) + 1):
            if not pending:
                break
            gain, pending = self._rr_round(pending, targets=rr_targets,
                                           rip=rr_rip)
            rr_history.append(dict(round=round_index, gain=gain,
                                   pending=len(pending),
                                   routed=len(self.plan)))
            self.log(f'{self.scheme}/{self.stack.name} rr round {round_index}: '
                     f'gain={gain} pending={len(pending)} routed={len(self.plan)}')
            if gain == 0:
                break
        self.stats = dict(
            scheme=self.scheme, stack=self.stack.name,
            stage=stage,
            baseline_routed=len(self.baseline_ids),
            final_routed=len(self.plan),
            new_routed=len(self.plan) - len(self.baseline_ids),
            attemptable=len(self.attemptable),
            no_candidate=len(self.no_candidate),
            failed_unplaceable=len(pending),
            flat_added=sum(1 for route in self.plan.values()
                           if int(route['n_transitions']) == 0
                           and int(route['route_id']) not in self.baseline_ids),
            passes=pass_history, rr=rr_history,
            rejected=dict(self.rejected.most_common(20)),
            seconds=round(time.perf_counter() - started, 2))
        return self.stats

    # ------------------------------------------------------------------
    def _rr_round(self, pending, targets, rip):
        gain = 0
        remaining = list(pending)
        original_count = len(self.plan)
        for route_id in list(remaining[:int(targets)]):
            if route_id in self.plan:
                if route_id in remaining:
                    remaining.remove(route_id)
                continue
            record, info = self.attempt_route(route_id,
                                              budget=self.candidate_budget * 2,
                                              stage='multi',
                                              variants=(0, 1, 2))
            if record is not None:
                self._accept(record)
                remaining.remove(route_id)
                gain += 1
                continue
            blockers = [blocker for blocker in info.get('blockers') or []
                        if blocker in self.plan
                        and int(self.plan[blocker]['n_transitions']) > 0]
            if not blockers:
                continue
            ripped_ids = blockers[:int(rip)]
            ripped = {}
            for ripped_id in ripped_ids:
                ripped[ripped_id] = self._remove(ripped_id)
            record, _info = self.attempt_route(route_id,
                                               budget=self.candidate_budget * 2,
                                               stage='multi',
                                               variants=(0, 1, 2))
            if record is not None:
                self._accept(record)
                for ripped_id, ripped_route in ripped.items():
                    if ripped_route is None:
                        continue
                    replaced, _info2 = self.attempt_route(
                        ripped_id, budget=self.candidate_budget,
                        stage='multi', variants=(0, 1, 2))
                    if replaced is not None:
                        self._accept(replaced)
            if len(self.plan) > original_count:
                gain += len(self.plan) - original_count
                original_count = len(self.plan)
                remaining.remove(route_id)
                for ripped_id, ripped_route in ripped.items():
                    if ripped_route is not None and ripped_id not in self.plan:
                        if ripped_id not in remaining:
                            remaining.append(ripped_id)
            else:
                for identifier in [route_id] + ripped_ids:
                    if identifier in self.plan:
                        self._remove(identifier)
                for ripped_id, ripped_route in ripped.items():
                    if ripped_route is not None:
                        self._accept(ripped_route)
        return gain, remaining

    # ------------------------------------------------------------------
    def routes_payload(self):
        records = []
        routed_records = []
        for route_id in sorted(self.routes):
            plane = self.plane_of[route_id]
            frame = self.frames[route_id]
            record = self.plan.get(route_id)
            if record is None:
                reason = ('no_2d_candidate' if route_id in self.no_candidate
                          else 'unplaceable_in_3d')
                records.append(common.failed_record(
                    route_id, plane, frame, reason,
                    baseline_2d=(route_id in self.baseline_ids),
                    stage=self.stats.get('stage', 'full')))
                continue
            record = dict(record)
            record['status'] = 'routed'
            records.append(record)
            routed_records.append(record)
        lifted = [record for record in routed_records if record['lifted']]
        transitions = sum(int(record['n_transitions']) for record in routed_records)
        total_length = sum(float(record['length_mm']) for record in routed_records)
        total_xy = sum(float(record['xy_length_mm']) for record in routed_records)
        layer_counts = Counter()
        plane_flat_parts = Counter()
        plane_flat_lengths = Counter()
        layer_pair = Counter()
        layer_sequence_hist = Counter()
        transitions_hist = Counter()
        layers_used_hist = Counter()
        for record in routed_records:
            transitions_hist[str(int(record['n_transitions']))] += 1
            layer_sequence_hist['->'.join(str(v) for v in record['layer_sequence'])] += 1
            layers_used_hist[','.join(str(v) for v in record['layers_used'])] += 1
            previous_layer = None
            for part in record['parts']:
                if part['kind'] == 'flat':
                    layer_counts[str(part['layer_id'])] += 1
                    key = f'L{part["layer_id"]}@{float(part["z_mm"]):g}'
                    plane_flat_parts[key] += 1
                    plane_flat_lengths[key] += float(part['length_mm'])
                else:
                    layer_pair[f'{part["from_layer"]}->{part["to_layer"]}'] += 1
        statistics = dict(
            baseline_routed=len(self.baseline_ids),
            routed=len(routed_records),
            failed=len(records) - len(routed_records),
            new_routed=len(routed_records) - len(self.baseline_ids),
            lifted=len(lifted),
            transitions=int(transitions),
            total_length_mm=round(total_length, 6),
            mean_length_mm=(round(total_length / len(routed_records), 6)
                            if routed_records else None),
            total_xy_length_mm=round(total_xy, 6),
            per_plane={plane: dict(
                routed=sum(1 for record in routed_records if record['plane'] == plane),
                baseline=sum(1 for record in routed_records
                             if record['plane'] == plane and record['baseline_2d']),
                lifted=sum(1 for record in routed_records
                           if record['plane'] == plane and record['lifted']))
                for plane in PLANES},
            per_layer_flat_parts=dict(layer_counts),
            per_physical_plane_flat_parts=dict(plane_flat_parts),
            per_physical_plane_flat_length_mm={key: round(value, 6)
                                               for key, value in plane_flat_lengths.items()},
            transition_layer_pairs=dict(layer_pair),
            transitions_histogram=dict(transitions_hist),
            layers_used_histogram=dict(layers_used_hist),
            layer_sequence_histogram=dict(layer_sequence_hist),
            failed_no_candidate=len(self.no_candidate),
            failed_unplaceable=len(records) - len(routed_records) - len(self.no_candidate),
            z_span_max_mm=max((record['z_span_mm'] for record in routed_records),
                              default=0.0))
        return dict(
            schema='four_side_1024_v2_l3d_routes_v1',
            experiment=(f'V2 corrected L1-L5 physical model, stage '
                        f'{self.stats.get("stage")}, scheme {self.scheme}'),
            topology='V2', csv_sha256=self.csv_sha256, scheme=self.scheme,
            scheme_label=common.SCHEME_LABEL[self.scheme],
            xy_model=common.SCHEME_XY_MODEL[self.scheme],
            stage=self.stats.get('stage', 'full'),
            layer_stack=self.stack.to_dict(),
            process=common.process_record(),
            budget=dict(candidate_budget=self.candidate_budget,
                        multi_budget=self.multi_budget,
                        layer_selection=self.layer_selection,
                        flat_probe=self.flat_probe),
            route_count=len(records),
            routed=len(routed_records),
            failed=len(records) - len(routed_records),
            statistics=statistics,
            router=self.stats,
            routes=records)
