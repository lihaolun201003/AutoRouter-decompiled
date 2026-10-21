"""V4-C4 routing experiment: insert the 56 same-side U connections into the V3 layout.

Strategy (2D only, exactly the task constraints):
* start from the accepted V3 964/1024 routes (508 opposite + 456 adjacent);
* the 56 connections of the 14 failed adjacent C4 groups are re-paired as same-side
  U turns (see :mod:`four_side_1024.v3c4.v4_connectivity`); every U is built with
  the existing R15 U-turn geometry module (``four_side_1024/r15/u_geometry.py``,
  quarter-pair family: straight + 90deg arc + middle straight + 90deg arc + straight;
  radius is never reduced);
* one representative U is searched per C4 group, the other three members are exact
  90deg rotations (port-level orientation check), all four are evaluated jointly
  against the frozen exact D56 index and committed atomically;
* if a group cannot be inserted directly, a bounded group-level rip-up & reroute
  removes the measured blocking V3 groups, inserts the same-side group and
  re-inserts the removed groups; a move is kept only if the routed count strictly
  increases;
* optionally the remaining V3 opposite group 53 gets a bounded recovery attempt
  (same framework, frozen candidates + pure-90 + global detour family).

Every result is re-audited by the frozen authoritative 2D checker
(``fslw.validate_fslw``, ``policy='strict'``) plus the C4 rotation audit and the
V4 connectivity identity check before it is saved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

from .profile import apply as apply_profile

ROUTING_ROOT_NAME = 'outputs/four_side_1024_v3_c4_routing'
OUT_ROOT_NAME = 'outputs/four_side_1024_v4_c4_routing'
V4_CSV_NAME = 'optical_1024_multitomulti_connectivity_v4_c4_symmetric.csv'
BULGE_LADDER = [2.0 * index for index in range(0, 61)] + [1.0, 3.0, 5.0]
INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0),
          'E': (-1.0, 0.0), 'W': (1.0, 0.0)}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write_json(path, payload, indent=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class V4Router:
    def __init__(self, routing_root=None, out_dir=None, log=print):
        apply_profile()
        from . import inputs as V3
        from . import v4_connectivity as C
        from . import l3d as L

        self.log = log
        self.routing_root = Path(routing_root or V3.ROUTING_ROOT)
        self.out_dir = Path(out_dir or (Path(__file__).resolve().parents[2]
                                        / OUT_ROOT_NAME))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        data_path = self.out_dir / 'v4_connectivity_data.json'
        if data_path.exists():
            raw = _read_json(data_path)
            self.connections = raw['connections']
            self.groups = raw['groups']
            self.replaced = raw['replaced']
            self.v3_csv = raw['v3_csv']
            self.v3_csv_sha256 = raw['v3_csv_sha256']
            self.failed_groups_v3 = raw['failed_groups_v3']
        else:
            data = C.build_v4(self.routing_root, log=log)
            self.connections, self.groups = data['connections'], data['groups']
            self.replaced = data['replaced']
            self.v3_csv = data['v3_csv']
            self.v3_csv_sha256 = data['v3_csv_sha256']
            self.failed_groups_v3 = data['failed_groups_v3']
        self.connection_by_id = {int(record['route_id']): record
                                 for record in self.connections}
        self.route_group = {}
        for group in self.groups:
            for phase, rid in enumerate(group['route_ids']):
                self.route_group[int(rid)] = (group['group_id'], phase)
        self.group_by_id = {group['group_id']: group for group in self.groups}
        # ---- V3 baseline states -------------------------------------------------
        self.states = {}
        self.v3_records = {}
        for plane in ('z1', 'z2'):
            _payload, records, routed = L.load_c4_2d(self.routing_root, plane,
                                                     log=lambda *a, **k: None)
            failed = {rid: rec for rid, rec in records.items()
                      if rec.get('status') != 'routed'}
            state = L.reconstruct_state(plane, routed, failed_records=failed,
                                        log=lambda *a, **k: None)
            self.states[plane] = state
            self.v3_records[plane] = records
        self.same_results = {}
        self.same_insert_info = []
        self.z1_recovery = None

    # -- generic helpers ---------------------------------------------------
    def _plane_of(self, route_id):
        return 'z1' if int(route_id) <= 512 else 'z2'

    def _record(self, route_id):
        return self.connection_by_id[int(route_id)]

    def _endpoints(self, route_id):
        record = self._record(route_id)
        return record['source_endpoint'], record['target_endpoint']

    def _port_xy(self, endpoint):
        from . import inputs as V3
        return tuple(float(value) for value in V3.ENDPOINTS[endpoint]['routing_xy'])

    # -- same-side U candidates -------------------------------------------
    def u_candidates(self, source_endpoint, target_endpoint, bulges=None):
        """Legal R15 same-side U candidates (world coordinates), exact-radius audit."""
        from ..fslw import config as C
        from ..fslw import geom
        from ..legacy_geometry import transform_primitives
        from ..r15 import u_geometry as UG

        bulges = BULGE_LADDER if bulges is None else bulges
        side = source_endpoint.split(':')[0][0]
        inward = INWARD[side]
        start_dir = inward
        end_dir = (-inward[0], -inward[1])
        p = self._port_xy(source_endpoint)
        q = self._port_xy(target_endpoint)
        frame, _errors = UG._canonical_frame(p, q, start_dir, end_dir,
                                             C.BOARD_MM, C.WIDTH_MM)
        if frame is None:
            return []
        radius = float(C.RADIUS_MM)
        separation = frame['separation_mm']
        if separation < 2.0 * radius - 1e-9:
            return []
        middle = separation - 2.0 * radius
        candidates = []
        for bulge in bulges:
            if bulge < 0.0:
                continue
            canonical = UG._quarter_pair(frame['p_canonical'],
                                         frame['q_canonical'], radius,
                                         float(bulge), middle)
            world = transform_primitives(canonical, frame['transform'], inverse=True)
            if not UG._validate(world, frame, radius, C.WIDTH_MM):
                continue
            length = 0.0
            for primitive in world:
                if primitive['kind'] == 'line':
                    length += math.dist(primitive['p0'], primitive['p1'])
                else:
                    length += abs(float(primitive['sweep'])) * float(
                        primitive['radius'])
            candidates.append(dict(
                family='U_QUARTER_PAIR', primitives=world,
                params=dict(bulge_mm=float(bulge),
                            middle_straight_mm=float(middle),
                            separation_mm=float(separation),
                            radius_mm=radius),
                length_mm=length, separation_mm=float(separation)))
        return candidates

    def rotate_to_member(self, primitives, phase, route_id):
        """Exact 90deg rotation + orientation of a representative path."""
        from . import inputs as V3
        rotated = V3.rotate_primitives(primitives, phase)
        source, target = self._endpoints(route_id)
        oriented, reversed_flag = V3.orient_primitives(rotated, source, target)
        return oriented, reversed_flag

    # -- insertion of the 14 same-side groups ------------------------------
    def insert_same_groups(self, time_limit=None, log=None):
        from ..d56.index import prepare
        from ..d56.search import RouteResult

        log = log or self.log
        state = self.states['z2']
        started = time.perf_counter()
        same_groups = [group for group in self.groups if group['kind'] == 'same']
        same_groups.sort(key=lambda group: group['group_id'])
        inserted = 0
        info = []
        for group in same_groups:
            if time_limit is not None and time.perf_counter() - started > time_limit:
                info.append(dict(group_id=group['group_id'], status='timeout'))
                continue
            ids = [int(rid) for rid in group['route_ids']]
            phase0 = ids[0]
            source, target = self._endpoints(phase0)
            candidates = self.u_candidates(source, target)
            placed = None
            for candidate in candidates:
                prepared = []
                oriented_paths = [candidate['primitives']]
                try:
                    for phase, rid in enumerate(ids[1:], start=1):
                        oriented, _reversed = self.rotate_to_member(
                            candidate['primitives'], phase, rid)
                        oriented_paths.append(oriented)
                    prepared = [prepare(path) for path in oriented_paths]
                except ValueError as exc:            # orientation mismatch
                    continue
                if any(not state.index.evaluate(prep).valid for prep in prepared):
                    continue
                for rid, prep in zip(ids, prepared):
                    state.index.add(rid, prep)
                legal = True
                for rid, prep in zip(ids, prepared):
                    if not state.index.evaluate(prep, exclude=[rid]).valid:
                        legal = False
                        break
                for rid in ids:
                    state.index.remove(rid)
                if not legal:
                    continue
                results = [RouteResult(rid, candidate['family'], dict(candidate['params']),
                                       path, prep, prep.length, 0, index,
                                       prep.bend_count)
                           for index, (rid, path, prep)
                           in enumerate(zip(ids, oriented_paths, prepared))]
                for result in results:
                    state.add(result)
                    self.same_results[result.route_id] = result
                inserted += 1
                info.append(dict(group_id=group['group_id'], status='inserted',
                                 route_ids=ids,
                                 params=dict(candidate['params']),
                                 length_mm=round(float(candidate['length_mm']), 4)))
                placed = candidate
                log(f'[v4] same group {group["group_id"]:3d}: inserted '
                    f'bulge={candidate["params"]["bulge_mm"]:g} '
                    f'routed_routes={len(state.accepted)}')
                break
            if placed is None:
                info.append(dict(group_id=group['group_id'], status='failed',
                                 route_ids=ids,
                                 candidates=len(candidates)))
                log(f'[v4] same group {group["group_id"]:3d}: FAILED '
                    f'(candidates={len(candidates)})')
        self.same_insert_info = info
        log(f'[v4] same-side groups inserted: {inserted}/{len(same_groups)} '
            f'({inserted * 4} routes) in {time.perf_counter() - started:.1f}s')
        return inserted, info

    # -- optional recovery of the remaining V3 opposite group 53 -----------
    def recover_opposite_group(self, time_limit=600.0, log=None):
        from ..d56.index import prepare
        from ..d56.search import RouteResult
        from . import expanded
        from .c4 import GroupRouter
        from . import inputs as V3

        log = log or self.log
        state = self.states['z1']
        z1_groups = [group for group in self.groups if group['plane'] == 'z1']
        failed = [group for group in z1_groups
                  if not all(rid in state.accepted for rid in group['route_ids'])]
        if not failed:
            return dict(status='no_failed_group')
        group = failed[0]
        started = time.perf_counter()
        router = GroupRouter(state, z1_groups, all_groups=z1_groups, log=log)
        rep = int(group['route_ids'][0])
        frame = state.frames[rep]
        oracle = state.oracle_for(rep)
        attempts = []
        # 1) direct insertion with the frozen + pure-90 + detour families
        iterator = expanded.expanded_candidates(frame, oracle, levels=(1, 2, 3))
        results, failure, stats = router.attempt_group(
            group, budget=4000, candidate_iterator=iterator)
        attempts.append(dict(kind='direct', valid=results is not None,
                             evaluated=stats.get('evaluated'),
                             seconds=round(time.perf_counter() - started, 2)))
        if results is not None:
            router.commit_group(group, results)
            return dict(status='recovered', kind='direct', attempts=attempts,
                        routed=len(state.accepted),
                        seconds=round(time.perf_counter() - started, 2))
        router.fail_group(group, failure)
        # 2) bounded group-level rip-up & reroute around the measured blockers
        blockers = [int(rid) for rid in (failure.get('blockers') or {})]
        blocker_groups = []
        impact = Counter()
        for rid in blockers:
            entry = self.route_group.get(rid)
            if entry is None or rid not in state.accepted:
                continue
            impact[entry[0]] += 1
        blocker_groups = [gid for gid, _count in impact.most_common(24)]
        rip_sets = []
        for size in (1, 2, 3, 4, 6, 8, 12, 16):
            if size <= len(blocker_groups):
                rip_sets.append(blocker_groups[:size])
        if len(blocker_groups) <= 4 and blocker_groups:
            rip_sets.append(list(blocker_groups))
        candidates_cache = list(expanded.expanded_candidates(
            frame, oracle, levels=(1, 2, 3)))
        for rip_gids in rip_sets:
            if time.perf_counter() - started > time_limit:
                attempts.append(dict(kind='rip', status='timeout'))
                break
            snapshot = state.snapshot()
            for gid in rip_gids:
                for rid in self.group_by_id[gid]['route_ids']:
                    if rid in state.accepted:
                        state.remove(rid)
            inserted_group = False
            group_results = None
            evaluated_candidates = 0
            for candidate in candidates_cache:
                evaluated_candidates += 1
                if evaluated_candidates > 2500:
                    break
                try:
                    prepared = []
                    paths = [candidate['primitives']]
                    for phase, rid in enumerate(group['route_ids'][1:], start=1):
                        oriented, _r = self.rotate_to_member(
                            candidate['primitives'], phase, rid)
                        paths.append(oriented)
                    prepared = [prepare(path) for path in paths]
                except ValueError:
                    continue
                if any(not state.index.evaluate(prep).valid for prep in prepared):
                    continue
                for rid, prep in zip(group['route_ids'], prepared):
                    state.index.add(rid, prep)
                legal = all(state.index.evaluate(prep, exclude=[rid]).valid
                            for rid, prep in zip(group['route_ids'], prepared))
                for rid in group['route_ids']:
                    state.index.remove(rid)
                if legal:
                    from ..d56.index import prepare as _prepare
                    from ..d56.search import RouteResult
                    group_results = []
                    for phase, (rid, path) in enumerate(zip(group['route_ids'], paths)):
                        prep = prepared[phase]
                        result = RouteResult(rid, candidate['family'],
                                             dict(candidate['params']), path, prep,
                                             prep.length, 0, 0, prep.bend_count)
                        state.add(result)
                        group_results.append(result)
                    inserted_group = True
                    break
            if not inserted_group:
                state.restore(snapshot)
                attempts.append(dict(kind='rip', size=len(rip_gids),
                                     valid=False, ripped=list(rip_gids),
                                     seconds=round(time.perf_counter() - started, 2)))
                continue
            # re-insert ripped groups (frozen candext families)
            reinsert_router = GroupRouter(state, z1_groups, all_groups=z1_groups,
                                          log=lambda *a, **k: None)
            reinserted = 0
            from .c4 import order_groups
            for gid in rip_gids:
                ripped = self.group_by_id[gid]
                if all(rid in state.accepted for rid in ripped['route_ids']):
                    continue
                res, fail, _ = reinsert_router.attempt_group(ripped, 800)
                if res is not None:
                    reinsert_router.commit_group(ripped, res)
                    reinserted += 1
                else:
                    reinsert_router.fail_group(ripped, fail)
            after = len(state.accepted)
            attempts.append(dict(kind='rip', size=len(rip_gids),
                                 valid=True, reinserted=reinserted,
                                 routed_after=after,
                                 ripped=list(rip_gids),
                                 seconds=round(time.perf_counter() - started, 2)))
            log(f'[v4] z1 group {group["group_id"]}: rip size {len(rip_gids)} -> '
                f'routed {after} (reinserted {reinserted}/{len(rip_gids)})')
            if after > 508:
                return dict(status='recovered', kind='rip', attempts=attempts,
                            routed=after, ripped=list(rip_gids),
                            seconds=round(time.perf_counter() - started, 2))
            state.restore(snapshot)
        return dict(status='not_recovered', attempts=attempts,
                    seconds=round(time.perf_counter() - started, 2))

    # -- artefact builders -------------------------------------------------
    def _pair_label(self, record):
        source_side = record['source_side']
        target_side = record['target_side']
        return ''.join(sorted((source_side, target_side)))

    def build_plane_payload(self, plane, algorithm_detail):
        state = self.states[plane]
        ids = range(1, 513) if plane == 'z1' else range(513, 1025)
        records = []
        for rid in ids:
            record = self._record(rid)
            result = state.accepted.get(rid)
            if result is None and rid in self.same_results:
                result = self.same_results[rid]
            base = dict(
                route_id=int(rid), plane=plane,
                z_mm=0.0 if plane == 'z1' else 0.5,
                relation=record['relation'], pair=self._pair_label(record),
                source_side=record['source_side'],
                target_side=record['target_side'],
                source_row=int(record['source_row']),
                target_row=int(record['target_row']),
                source_endpoint=record['source_endpoint'],
                target_endpoint=record['target_endpoint'],
                source_connector=record['source_connector'],
                target_connector=record['target_connector'],
                source_column=int(record['source_column']),
                target_column=int(record['target_column']),
                rotation_group_id=self.route_group[int(rid)][0],
                rotation_phase=self.route_group[int(rid)][1])
            if result is not None:
                key = self.route_group[int(rid)][0]
                base.update(
                    status='routed', primitives=result.primitives,
                    length_mm=round(float(result.length_mm), 4),
                    bend_count=int(result.bends),
                    family=result.family,
                    params=dict(result.params or {}),
                    candidate_index=int(result.candidate_index),
                    crossing_count=int(result.crossings),
                    c4_symmetry='strict_group_commit')
            else:
                failure = state.failed.get(rid) or {}
                base.update(
                    status='failed',
                    reason=failure.get('reason', 'not_attempted'),
                    evaluated=failure.get('evaluated', 0),
                    rejection_counts=dict(failure.get('rejection_counts') or {}),
                    blockers=dict(failure.get('blockers') or {}),
                    c4_symmetry='strict_group_commit')
            records.append(base)
        payload = dict(
            schema='four_side_1024_v4_c4_plane_routes_v1',
            topology='V4_C4', plane=plane,
            forced_symmetry=True,
            csv_sha256=self.v3_csv_sha256,
            v4_csv_sha256=self.v4_csv_sha256 if hasattr(self, 'v4_csv_sha256') else None,
            algorithm=algorithm_detail,
            routes=records)
        return payload

    def build_all(self, algorithm_detail):
        payloads = {plane: self.build_plane_payload(plane, algorithm_detail)
                    for plane in ('z1', 'z2')}
        records = payloads['z1']['routes'] + payloads['z2']['routes']
        records.sort(key=lambda record: int(record['route_id']))
        routed = [record for record in records if record['status'] == 'routed']
        combined = dict(
            schema='four_side_1024_v4_c4_routes_v1',
            topology='V4_C4', forced_symmetry=True,
            weighted_directed_crossing_points=0,
            v4_csv_sha256=getattr(self, 'v4_csv_sha256', None),
            v3_csv_sha256=self.v3_csv_sha256,
            routed=len(routed), failed=len(records) - len(routed),
            rotation_groups=self.groups,
            routes=records)
        return payloads, combined
