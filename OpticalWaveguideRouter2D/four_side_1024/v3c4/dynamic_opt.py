"""V4-C4 3D optimization V2: dynamic layer reassignment / local rescheduling.

Starts from the accepted 0.50 mm layer-spacing result (ablation group B) and
reschedules already-lifted C4 quartets, tries two-quartet joint moves (layer swaps,
interval swaps) and re-tries un-lifted quartets whose local layout changed.

Hard invariants: no 2D reroute (original XY primitives only), fixed L2-L5 heights,
strict C4 atomic groups, R=15 mm, transitions only on straight segments, at most
one climb + one descent per route, the unique same-height crossing pair count
(deduplicated across physical heights) must strictly decrease, and every accepted
layout is checked by the independent 3D validator before it is committed.
"""
from __future__ import annotations

import bisect
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

from .profile import apply as apply_profile

OUT_ROOT_NAME = 'outputs/v4_c4_dynamic_layer_optimization'
B_ROOT_NAME = 'outputs/v4_c4_layer_height_ablation/B_0.50mm'
CACHE_NAME = 'outputs/v4_c4_layer_height_ablation/baseline_crossings.json'
RADIUS_MM = 15.0
MAX_SINGLE_ACTIONS = 24
MAX_JOINT_ACTIONS = 8
MAX_RETRY_ACTIONS = 8
MAX_PLANS_PER_GROUP = 30
MAX_SINGLE_VALIDATIONS = 3
MAX_JOINT_VALIDATIONS = 2
STRICT_TRANSITION_CLEARANCE = 0.09


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write_json(path, payload, indent=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def _sha256(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _segment_segment_distance_3d(a0, a1, b0, b1):
    import numpy as np
    p1 = np.array(a0, dtype=float)
    q1 = np.array(a1, dtype=float)
    p2 = np.array(b0, dtype=float)
    q2 = np.array(b1, dtype=float)
    d1 = q1 - p1
    d2 = q2 - p2
    r = p1 - p2
    a = float(d1 @ d1)
    e = float(d2 @ d2)
    f = float(d2 @ r)
    eps = 1e-12
    if a <= eps and e <= eps:
        return float(np.linalg.norm(p1 - p2))
    if a <= eps:
        s = 0.0
        t = max(0.0, min(1.0, f / e))
    elif e <= eps:
        t = 0.0
        s = max(0.0, min(1.0, -float(d1 @ r) / a))
    else:
        c = float(d1 @ r)
        b = float(d1 @ d2)
        denominator = a * e - b * b
        s = (max(0.0, min(1.0, (b * f - c * e) / denominator))
             if denominator > eps else 0.0)
        t = (b * s + f) / e
        if t < 0.0:
            t = 0.0
            s = max(0.0, min(1.0, -c / a))
        elif t > 1.0:
            t = 1.0
            s = max(0.0, min(1.0, (b - c) / a))
    c1 = p1 + d1 * s
    c2 = p2 + d2 * t
    return float(np.linalg.norm(c1 - c2))


def _polyline_segments(points):
    return [(points[index], points[index + 1])
            for index in range(len(points) - 1)]


class DynamicOptimizer:
    def __init__(self, out_dir=None, b_root=None, cache_path=None, log=print,
                 time_limit=1800.0):
        apply_profile()
        from .lift_cross import CrossingLifter, position_on_route
        from . import lift_cross as LC
        from ..l3d.world import World

        self.LC = LC
        self.position_on_route = staticmethod(position_on_route)
        self.World = World
        self.log = log
        self.time_limit = float(time_limit)
        self.started = time.perf_counter()
        repo = Path(__file__).resolve().parents[2]
        self.out_dir = Path(out_dir or (repo / OUT_ROOT_NAME))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.b_root = Path(b_root or (repo / B_ROOT_NAME))
        cache = Path(cache_path or (repo / CACHE_NAME))
        self.input_hashes = {
            'b_routes_l3d_sha256': _sha256(self.b_root / 'routes_l3d.json'),
            'b_layer_stack_sha256': _sha256(self.b_root / 'layer_stack.json'),
            'b_validation_sha256': _sha256(self.b_root / 'validation.json'),
            'b_summary_sha256': _sha256(self.b_root / 'summary.json'),
            'crossing_cache_sha256': _sha256(cache) if cache.exists() else None,
        }
        self.log(f'[dyn] input hashes: {self.input_hashes}')

        self.lifter = CrossingLifter(out_dir=self.out_dir, log=log)
        self.stack = self.lifter.stack
        self.safe = float(self.lifter.safe_length)
        self.transition_margin = float(self.lifter.transition_margin)
        self.group_by_id = self.lifter.group_by_id
        self.route_group = self.lifter.route_group
        self.routed_records = self.lifter.routed

        payload = _read_json(self.b_root / 'routes_l3d.json')
        self.failed_records = [record for record in payload['routes']
                               if record.get('status') != 'routed']
        self.current_routes = {int(record['route_id']): record
                               for record in payload['routes']
                               if record.get('status') == 'routed'}
        self.routed_ids = sorted(self.current_routes)
        self.lifted = {rid: route for rid, route in self.current_routes.items()
                       if route.get('lifted')}
        self.log(f'[dyn] current layout: routed={len(self.routed_ids)} '
                 f'lifted_routes={len(self.lifted)} '
                 f'lifted_groups={len({self.route_group[rid][0] for rid in self.lifted})}')

        baseline = _read_json(cache)
        self.rep_positions = defaultdict(list)
        for value in baseline['crossings']:
            _z, a, b, _x, _y, s_a, s_b, _angle = value
            self.rep_positions[int(a)].append(float(s_a))
            self.rep_positions[int(b)].append(float(s_b))

        b_after = _read_json(self.b_root / 'crossings_after.json')
        self.pair_set = {tuple(sorted((int(pair[0]), int(pair[1]))))
                         for pair in b_after['remaining_pairs']}
        self.initial_pair_count = len(self.pair_set)
        self.partners = defaultdict(set)
        for first, second in self.pair_set:
            self.partners[first].add(second)
            self.partners[second].add(first)
        self.log(f'[dyn] initial unique crossing pairs={self.initial_pair_count}')
        self.initial_lengths = sum(route['length_mm']
                                   for route in self.current_routes.values())

        self.planes = defaultdict(dict)
        for rid, route in self.current_routes.items():
            self._add_route_to_planes(rid, route)
        self._rebuild_world()

        self.layout_version = 0
        self._transition_cache = []
        self._transition_cache_version = -1
        self.actions = []
        self.rejects = []
        self.stage_records = dict(dynamic_layer_changes=[],
                                  interval_moves=[],
                                  joint_reschedules=[],
                                  failed_retries=[],
                                  recovered_failed_groups=[],
                                  revert_to_flat=[])
        self.changed_bboxes = []
        self.best_pair_count = len(self.pair_set)
        self.recovered_groups = []

    # ------------------------------------------------------------------
    # structures
    # ------------------------------------------------------------------
    def _prepare(self, primitives):
        from ..fslw import validate_fslw as V
        prepared = V.prepare_route(primitives, 0).prims
        return dict(prepared=prepared,
                    bbox=(min(p.bbox[0] for p in prepared),
                          min(p.bbox[1] for p in prepared),
                          max(p.bbox[2] for p in prepared),
                          max(p.bbox[3] for p in prepared)))

    def _route_flat_by_plane(self, route):
        result = defaultdict(list)
        for part in route['parts']:
            if part['kind'] != 'flat':
                continue
            z = round(float(part['z_mm']), 9)
            result[z].extend(dict(primitive) for primitive in part['primitives'])
        return result

    def _add_route_to_planes(self, rid, route):
        for z, prims in self._route_flat_by_plane(route).items():
            self.planes[z][int(rid)] = self._prepare(prims)

    def _remove_route_from_planes(self, rid):
        for z in list(self.planes):
            self.planes[z].pop(int(rid), None)

    def _rebuild_world(self):
        world = self.World(self.stack)
        for rid in self.routed_ids:
            world.add_route(self.current_routes[rid])
        self.lifter.world = world

    def _world_without(self, exclude_ids):
        exclude_ids = set(int(value) for value in exclude_ids)
        world = self.World(self.stack)
        for rid in self.routed_ids:
            if rid in exclude_ids:
                continue
            world.add_route(self.current_routes[rid])
        return world

    def _route_of_group(self, gid):
        return [int(rid) for rid in self.group_by_id[int(gid)]['route_ids']]

    def current_group_layer(self, gid):
        for rid in self._route_of_group(gid):
            route = self.current_routes[rid]
            if not route.get('lifted'):
                continue
            for part in route['parts']:
                if part['kind'] == 'flat' and int(part['layer_id']) != 1:
                    return int(part['layer_id'])
        return 1

    def current_group_interval(self, gid):
        rep = self._route_of_group(gid)[0]
        route = self.current_routes[rep]
        primitives = self.routed_records[rep]['primitives']
        transitions = [part for part in route['parts']
                       if part['kind'] == 'transition']
        if len(transitions) < 2:
            return None
        rise = self.position_on_route(primitives, transitions[0]['start'])
        fall = self.position_on_route(primitives, transitions[-1]['start'])
        return dict(rise_start_mm=round(float(rise), 4),
                    fall_start_mm=round(float(fall), 4),
                    layer_id=self.current_group_layer(gid))

    def group_incidence(self, gid):
        partners = set()
        for rid in self._route_of_group(gid):
            partners |= self.partners.get(rid, set())
        return len(partners)

    # ------------------------------------------------------------------
    # crossing bookkeeping
    # ------------------------------------------------------------------
    @staticmethod
    def _crossing(entry_a, entry_b):
        a_box, b_box = entry_a['bbox'], entry_b['bbox']
        if (a_box[2] + 0.05 < b_box[0] or b_box[2] + 0.05 < a_box[0]
                or a_box[3] + 0.05 < b_box[1] or b_box[3] + 0.05 < a_box[1]):
            return False
        from ..fslw import validate_fslw as V
        for first in entry_a['prepared']:
            for second in entry_b['prepared']:
                if V._prims_intersect(first, second):
                    return True
        return False

    def _pairs_with_group(self, candidate_routes, group_ids):
        group_ids = set(int(rid) for rid in group_ids)
        candidate_entries = defaultdict(dict)
        for rid, route in candidate_routes.items():
            for z, prims in self._route_flat_by_plane(route).items():
                candidate_entries[z][int(rid)] = self._prepare(prims)
        pairs = set()
        for z in set(self.planes) | set(candidate_entries):
            base_others = [(rid, entry) for rid, entry in self.planes.get(z, {}).items()
                           if rid not in group_ids]
            candidates = list(candidate_entries.get(z, {}).items())
            for cand_rid, cand_entry in candidates:
                for other_rid, other_entry in base_others:
                    pair = (min(cand_rid, other_rid), max(cand_rid, other_rid))
                    if pair in pairs:
                        continue
                    if self._crossing(cand_entry, other_entry):
                        pairs.add(pair)
                for other_rid, other_entry in candidates:
                    if other_rid <= cand_rid:
                        continue
                    pair = (min(cand_rid, other_rid), max(cand_rid, other_rid))
                    if pair in pairs:
                        continue
                    if self._crossing(cand_entry, other_entry):
                        pairs.add(pair)
        return pairs

    def _old_pairs_for(self, group_ids):
        pairs = set()
        for rid in set(int(value) for value in group_ids):
            for other in self.partners.get(rid, ()):
                pairs.add((min(rid, other), max(rid, other)))
        return pairs

    # ------------------------------------------------------------------
    # candidate generation (only on original 2D straight segments)
    # ------------------------------------------------------------------
    def generate_plans(self, rep_id, exclude_ids, max_plans=MAX_PLANS_PER_GROUP):
        LC = self.LC
        from ..fsd25d import path3d as P
        record = self.routed_records[int(rep_id)]
        primitives = record['primitives']
        total = P.path_length(primitives)
        positions = sorted(self.rep_positions.get(int(rep_id), []))
        row = self.lifter.row[int(rep_id)]
        base_z = LC.row_z(row)
        plans = []
        for layer_id in (2, 3, 4, 5):
            layer_z = float(self.stack.z_for_layer(layer_id))
            footprint = LC.transition_geometry(layer_z - base_z)['footprint_mm']
            windows = LC._straight_start_windows(primitives, footprint, total)
            if not windows:
                continue
            margin = LC.CROSSING_EXCLUSION_MARGIN_MM
            starts = set()

            def _add(value, low, high):
                if low - 1e-9 <= value <= high + 1e-9:
                    starts.add(round(float(value), 6))

            for lo, hi in windows:
                span = hi - lo
                for fraction in (0.0, 0.5, 1.0):
                    _add(lo + span * fraction, lo, hi)
            for position in positions:
                for low, high in windows:
                    _add(position - footprint - margin, low, high)
                    _add(position + margin, low, high)
            ordered = sorted(starts)
            safe = self.safe

            rise_valid = [start for start in ordered
                          if LC._inside_window(start, windows)
                          and LC._free_zone(start, start + safe, positions, margin)]
            fall_valid = [start for start in ordered
                          if LC._inside_window(start, windows)
                          and start + footprint <= total - LC.PORT_MARGIN_MM + 1e-9
                          and LC._free_zone(start + footprint - safe,
                                            start + footprint, positions, margin)]

            def _cap(values, limit=45):
                if len(values) <= limit:
                    return values
                stride = max(1, len(values) // limit)
                return values[::stride][:limit]

            rise_valid = _cap(rise_valid)
            fall_valid = _cap(fall_valid)
            for rise_start in rise_valid:
                rise_end = rise_start + footprint
                for fall_start in fall_valid:
                    if fall_start < rise_end + LC.MIN_TRAVEL_MM:
                        continue
                    low = rise_start + safe + margin
                    high = fall_start + footprint - safe - margin
                    if high <= low:
                        continue
                    removed = bisect.bisect_left(positions, high) - \
                        bisect.bisect_right(positions, low)
                    if removed <= 0:
                        continue
                    plans.append(dict(layer_id=int(layer_id),
                                      layer_z=float(layer_z),
                                      footprint=float(footprint),
                                      rise_start=float(rise_start),
                                      fall_start=float(fall_start),
                                      removed_crossings=int(removed)))
        plans.sort(key=lambda item: (-item['removed_crossings'], item['layer_id'],
                                     item['rise_start']))
        chosen = []
        seen = set()
        for plan in plans:
            key = (plan['layer_id'], round(plan['rise_start'], 3),
                   round(plan['fall_start'], 3))
            if key in seen:
                continue
            if not self._plan_transition_ok(primitives, plan, base_z, exclude_ids):
                continue
            seen.add(key)
            chosen.append(plan)
            if len(chosen) >= max_plans:
                break
        return chosen

    def _plan_transition_ok(self, primitives, plan, base_z, exclude_ids):
        from ..fsd25d import path3d as P
        point, direction = P.path_point_at(primitives, plan['rise_start'])
        fall_point, fall_direction = P.path_point_at(primitives, plan['fall_start'])
        for start, travel, z0, z1 in (
                (point, direction, base_z, plan['layer_z']),
                (fall_point, fall_direction, plan['layer_z'], base_z)):
            low, high = sorted((float(z0), float(z1)))
            for z_plane in self.planes:
                if not (low + 1e-9 < z_plane < high - 1e-9):
                    continue
                u = self._transition_u_for_z(z_plane, z0, z1,
                                             float(plan['footprint']))
                px = start[0] + travel[0] * u
                py = start[1] + travel[1] * u
                if self._min_distance_to_plane((px, py), z_plane,
                                               exclude_ids) < self.transition_margin:
                    return False
        return True

    @staticmethod
    def _transition_u_for_z(z_target, z0, z1, footprint):
        radius = RADIUS_MM
        low, high = 0.0, float(footprint)

        def z_at(u):
            sign = 1.0 if z1 >= z0 else -1.0
            half = footprint / 2.0
            if u <= half:
                phi = math.asin(max(-1.0, min(1.0, u / radius)))
                return z0 + sign * radius * (1.0 - math.cos(phi))
            u2 = footprint - u
            phi = math.asin(max(-1.0, min(1.0, u2 / radius)))
            return z1 - sign * radius * (1.0 - math.cos(phi))

        for _ in range(40):
            mid = (low + high) / 2.0
            value = z_at(mid)
            if (z1 - z0) >= 0:
                below = value < z_target
            else:
                below = value > z_target
            if below:
                low = mid
            else:
                high = mid
        return (low + high) / 2.0

    def _min_distance_to_plane(self, point, z_plane, exclude_ids):
        exclude_ids = set(int(value) for value in exclude_ids)
        entries = self.planes.get(round(float(z_plane), 9)) or {}
        px, py = float(point[0]), float(point[1])
        best = float('inf')
        for rid, entry in entries.items():
            if rid in exclude_ids:
                continue
            box = entry['bbox']
            if px < box[0] - 0.6 or px > box[2] + 0.6:
                continue
            if py < box[1] - 0.6 or py > box[3] + 0.6:
                continue
            for prim in entry['prepared']:
                distance = self.lifter._point_primitive_distance(px, py, prim)
                if distance < best:
                    best = distance
                    if best <= self.transition_margin:
                        return best
        return best

    # ------------------------------------------------------------------
    # world / strict checks
    # ------------------------------------------------------------------
    @staticmethod
    def _violation_routes(violation):
        ids = set()
        if violation.get('other_route') is not None:
            ids.add(int(violation['other_route']))
        for blocker in violation.get('blockers') or []:
            ids.add(int(blocker) // 1000)
        return ids

    def _transition_entries(self):
        if self._transition_cache_version == self.layout_version:
            return self._transition_cache
        from ..fsd25d import path3d as P
        entries = []
        for rid, route in self.current_routes.items():
            for part in route['parts']:
                if part['kind'] != 'transition':
                    continue
                points = [tuple(sample) for sample in P.transition_samples(part)]
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                entries.append((int(rid),
                                (min(xs), min(ys), max(xs), max(ys)),
                                _polyline_segments(points)))
        self._transition_cache = entries
        self._transition_cache_version = self.layout_version
        return entries

    def _strict_transition_ok(self, candidate_routes, exclude_ids):
        from ..fsd25d import path3d as P
        exclude_ids = set(int(value) for value in exclude_ids)
        other_transitions = [(box, segments)
                             for rid, box, segments in self._transition_entries()
                             if rid not in exclude_ids]
        for route in candidate_routes.values():
            for part in route['parts']:
                if part['kind'] != 'transition':
                    continue
                points = [tuple(sample) for sample in P.transition_samples(part)]
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                box = (min(xs), min(ys), max(xs), max(ys))
                segments = _polyline_segments(points)
                for other_box, other_segments in other_transitions:
                    if (box[2] + 0.3 < other_box[0]
                            or other_box[2] + 0.3 < box[0]
                            or box[3] + 0.3 < other_box[1]
                            or other_box[3] + 0.3 < box[1]):
                        continue
                    for first in segments:
                        for second in other_segments:
                            if _segment_segment_distance_3d(
                                    first[0], first[1], second[0],
                                    second[1]) < STRICT_TRANSITION_CLEARANCE:
                                return False
        return True

    def _candidate_compat(self, candidate_routes, base_world, group_ids):
        """True clearance check against the layout *without* the rescheduled groups."""
        blocking = set()
        for rid in sorted(candidate_routes):
            violations = base_world.check_route(candidate_routes[rid],
                                                check_self=True)
            if violations:
                for violation in violations:
                    blocking |= self._violation_routes(violation)
                if not blocking:
                    blocking.add(-1)
                return blocking
        temp = self.World(self.stack)
        for rid in sorted(candidate_routes):
            violations = temp.check_route(candidate_routes[rid], check_self=True)
            if violations:
                return {-1}
            temp.add_route(candidate_routes[rid])
        if not self._strict_transition_ok(candidate_routes, group_ids):
            return {-1}
        return set()

    # ------------------------------------------------------------------
    # payload / validation
    # ------------------------------------------------------------------
    def build_payload(self, routes_override=None):
        routes = self.current_routes if routes_override is None else routes_override
        records = []
        for rid in sorted(routes):
            record = dict(routes[rid])
            record['route_id'] = int(rid)
            record['status'] = 'routed'
            records.append(record)
        records.extend(dict(record) for record in self.failed_records)
        records.sort(key=lambda item: int(item['route_id']))
        return dict(schema='four_side_1024_v2_l3d_routes_v1',
                    experiment='V4_C4_DYNAMIC_LAYER_OPTIMIZATION',
                    note='XY paths/ports/connections unchanged; dynamic layer '
                         'reassignment of already lifted C4 quartets',
                    layer_stack=self.stack.to_dict(),
                    routes=records)

    def validate_routes(self, routes_override=None):
        from .lift_cross import validate_payload_v4
        payload = self.build_payload(routes_override=routes_override)
        report = validate_payload_v4(payload, self.lifter.v4_root, log=self.log)
        return report, payload

    # ------------------------------------------------------------------
    # candidates
    # ------------------------------------------------------------------
    def build_candidate(self, gid, plan):
        group = self.group_by_id[int(gid)]
        ids = [int(rid) for rid in group['route_ids']]
        if plan is None:
            return {rid: self.lifter.base_routes[rid] for rid in ids}
        return self.lifter.build_group_routes(group, plan)

    def _cheap_delta(self, candidate_routes, group_ids):
        ids = list(candidate_routes)
        new_pairs = self._pairs_with_group(candidate_routes, ids)
        old_pairs = self._old_pairs_for(group_ids)
        candidate_total = len(self.pair_set) - len(old_pairs) + len(new_pairs)
        if candidate_total >= len(self.pair_set):
            return dict(status='no_reduction', current_total=candidate_total)
        return dict(status='ok', new_pairs=new_pairs, old_pairs=old_pairs,
                    delta=len(old_pairs) - len(new_pairs),
                    candidate_total=candidate_total)

    def _evaluate(self, candidate_routes, group_ids, base_world):
        cheap = self._cheap_delta(candidate_routes, group_ids)
        if cheap['status'] != 'ok':
            return cheap
        old_pairs = cheap['old_pairs']
        new_pairs = cheap['new_pairs']
        candidate_total = cheap['candidate_total']
        blocking = self._candidate_compat(candidate_routes, base_world,
                                          group_ids)
        if blocking:
            return dict(status='blocked', blocking=sorted(blocking),
                        old_count=len(old_pairs), new_count=len(new_pairs))
        return dict(status='ok', new_pairs=new_pairs, old_pairs=old_pairs,
                    delta=len(old_pairs) - len(new_pairs),
                    candidate_total=candidate_total)

    def _tentative_ok(self, override):
        report, _payload = self.validate_routes(routes_override=override)
        return bool(report.get('exploratory_pass')), report

    def try_single(self, gid):
        ids = self._route_of_group(gid)
        current_layer = self.current_group_layer(gid)
        base_world = self._world_without(ids)
        current = self.current_group_interval(gid) or {}
        plans = self.generate_plans(ids[0], ids)
        candidates = [dict(plan=None, kind='revert')]
        for plan in plans:
            if (current.get('layer_id') == plan['layer_id']
                    and abs(current.get('rise_start_mm', -999) - plan['rise_start']) < 0.01
                    and abs(current.get('fall_start_mm', -999) - plan['fall_start']) < 0.01):
                continue
            candidates.append(dict(plan=plan, kind='re_lift'))
        cheap_list = []
        rejects = []
        for candidate in candidates:
            routes = self.build_candidate(gid, candidate['plan'])
            if routes is None:
                continue
            cheap = self._cheap_delta(routes, ids)
            if cheap['status'] != 'ok':
                continue
            cheap_list.append(dict(candidate=candidate, routes=routes,
                                   cheap=cheap))
        cheap_list.sort(key=lambda item: -item['cheap']['delta'])
        evaluated = []
        for item in cheap_list[:10]:
            result = self._evaluate(item['routes'], ids, base_world)
            if result['status'] == 'blocked':
                rejects.append(dict(group_id=gid, kind=item['candidate']['kind'],
                                    reason='true_3d_clearance',
                                    blocking=result['blocking']))
                continue
            if result['status'] != 'ok':
                continue
            evaluated.append(dict(candidate=item['candidate'],
                                  routes=item['routes'], result=result))
        evaluated.sort(key=lambda item: -item['result']['delta'])
        validations = 0
        for item in evaluated:
            if validations >= MAX_SINGLE_VALIDATIONS:
                break
            validations += 1
            override = dict(self.current_routes)
            override.update({int(rid): route for rid, route in item['routes'].items()})
            ok, report = self._tentative_ok(override)
            if ok:
                return dict(status='accepted', routes=item['routes'],
                            candidate=item['candidate'], result=item['result'],
                            rejects=rejects)
            rejects.append(dict(group_id=gid, kind=item['candidate']['kind'],
                                reason='validator_reject',
                                violations=(report.get('violations') or [])[:3]))
        return dict(status='rejected', rejects=rejects,
                    best_blocking=(rejects[0].get('blocking') if rejects else []))

    def try_joint(self, gid_a, gid_b):
        ids_a = self._route_of_group(gid_a)
        ids_b = self._route_of_group(gid_b)
        exclude = ids_a + ids_b
        base_world = self._world_without(exclude)
        plans_a = [dict(plan=None, kind='revert')] + [
            dict(plan=plan, kind='re_lift')
            for plan in self.generate_plans(ids_a[0], exclude, max_plans=8)]
        plans_b = [dict(plan=None, kind='revert')] + [
            dict(plan=plan, kind='re_lift')
            for plan in self.generate_plans(ids_b[0], exclude, max_plans=8)]
        cheap_list = []
        routes_cache = {}
        for candidate_a in plans_a:
            routes_a = self.build_candidate(gid_a, candidate_a['plan'])
            if routes_a is None:
                continue
            routes_cache[id(candidate_a)] = routes_a
            for candidate_b in plans_b:
                routes_b = self.build_candidate(gid_b, candidate_b['plan'])
                if routes_b is None:
                    continue
                routes_cache[id(candidate_b)] = routes_b
                combined = dict(routes_a)
                combined.update(routes_b)
                cheap = self._cheap_delta(combined, ids_a + ids_b)
                if cheap['status'] != 'ok':
                    continue
                cheap_list.append(dict(candidate_a=candidate_a,
                                       candidate_b=candidate_b,
                                       routes=combined, cheap=cheap))
        cheap_list.sort(key=lambda item: -item['cheap']['delta'])
        evaluated = []
        for item in cheap_list[:12]:
            result = self._evaluate(item['routes'], ids_a + ids_b, base_world)
            if result['status'] != 'ok':
                continue
            evaluated.append(dict(candidate_a=item['candidate_a'],
                                  candidate_b=item['candidate_b'],
                                  routes=item['routes'], result=result))
        evaluated.sort(key=lambda item: -item['result']['delta'])
        validations = 0
        for item in evaluated:
            if validations >= MAX_JOINT_VALIDATIONS:
                break
            validations += 1
            override = dict(self.current_routes)
            override.update({int(rid): route for rid, route in item['routes'].items()})
            ok, report = self._tentative_ok(override)
            if ok:
                return dict(status='accepted', routes=item['routes'],
                            candidate_a=item['candidate_a'],
                            candidate_b=item['candidate_b'],
                            result=item['result'])
        return dict(status='rejected')

    # ------------------------------------------------------------------
    # commit
    # ------------------------------------------------------------------
    def commit(self, group_ids, candidate_routes, action):
        pair_count_before = len(self.pair_set)
        old_pairs = self._old_pairs_for(group_ids)
        new_pairs = self._pairs_with_group(candidate_routes, list(candidate_routes))
        for rid in group_ids:
            self._remove_route_from_planes(rid)
            self.current_routes.pop(int(rid), None)
        for rid, route in candidate_routes.items():
            self.current_routes[int(rid)] = route
            if route.get('lifted'):
                self.lifted[int(rid)] = route
            else:
                self.lifted.pop(int(rid), None)
            self._add_route_to_planes(int(rid), route)
        for pair in old_pairs:
            self.pair_set.discard(pair)
            first, second = pair
            self.partners[first].discard(second)
            self.partners[second].discard(first)
        for pair in new_pairs:
            self.pair_set.add(pair)
            first, second = pair
            self.partners[first].add(second)
            self.partners[second].add(first)
        self._rebuild_world()
        self.layout_version += 1
        bbox = (1e9, 1e9, -1e9, -1e9)
        for rid in group_ids:
            record = self.routed_records[int(rid)]
            xs = [prim['p0'][0] for prim in record['primitives'] if prim['kind'] == 'line']
            ys = [prim['p0'][1] for prim in record['primitives'] if prim['kind'] == 'line']
            if xs:
                bbox = (min(bbox[0], min(xs)), min(bbox[1], min(ys)),
                        max(bbox[2], max(xs)), max(bbox[3], max(ys)))
        self.changed_bboxes.append(bbox)
        action.update(layer_version=self.layout_version,
                      pair_count_before=int(pair_count_before),
                      pair_count_after=int(len(self.pair_set)),
                      old_pairs=len(old_pairs), new_pairs=len(new_pairs),
                      removed_pairs=sorted(list(old_pairs))[:200],
                      added_pairs=sorted(list(new_pairs))[:200],
                      timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
        self.actions.append(action)
        if len(self.pair_set) < self.best_pair_count:
            self.best_pair_count = len(self.pair_set)
        return action

    # ------------------------------------------------------------------
    # main drive
    # ------------------------------------------------------------------
    def time_left(self):
        return self.time_limit - (time.perf_counter() - self.started)

    def optimize(self):
        log = self.log
        lifted_groups = sorted({self.route_group[rid][0] for rid in self.lifted},
                               key=lambda gid: -self.group_incidence(gid))
        single_actions = 0
        joint_actions = 0
        retry_actions = 0

        # ---- stage 1: single quartet rescheduling ---------------------
        stage1_reserve = max(900.0, 0.40 * self.time_limit)
        for gid in lifted_groups:
            if single_actions >= MAX_SINGLE_ACTIONS or self.time_left() <= stage1_reserve:
                break
            current_layer = self.current_group_layer(gid)
            current_interval = self.current_group_interval(gid) or {}
            result = self.try_single(gid)
            self.rejects.extend(result.get('rejects') or [])
            if result['status'] != 'accepted':
                continue
            plan = result['candidate']['plan']
            interval = None
            if plan is not None:
                interval = dict(rise_start_mm=plan['rise_start'],
                                fall_start_mm=plan['fall_start'])
            if plan is None:
                kind = 'revert_to_flat'
            elif plan['layer_id'] != current_layer:
                kind = 'dynamic_layer_change'
            elif interval is not None and current_interval and (
                    abs(interval['rise_start_mm']
                        - current_interval.get('rise_start_mm', -1)) > 0.01
                    or abs(interval['fall_start_mm']
                           - current_interval.get('fall_start_mm', -1)) > 0.01):
                kind = 'interval_move'
            else:
                kind = 're_lift'
            action = dict(stage='single', kind=kind, group_id=gid,
                          old_layer=current_layer,
                          new_layer=(plan['layer_id'] if plan else 1),
                          old_interval=current_interval, new_interval=interval)
            self.commit(self._route_of_group(gid), result['routes'], action)
            single_actions += 1
            if kind == 'dynamic_layer_change':
                self.stage_records['dynamic_layer_changes'].append(action)
            elif kind == 'interval_move':
                self.stage_records['interval_moves'].append(action)
            elif kind == 'revert_to_flat':
                self.stage_records['revert_to_flat'].append(action)
            log(f'[dyn] single {kind} group {gid} L{current_layer}->'
                f'{action["new_layer"]} pairs {action["pair_count_before"]}->'
                f'{action["pair_count_after"]}')

        # ---- stage 2: two-quartet joint rescheduling -----------------
        failed_groups = []
        for gid in lifted_groups:
            incidence = self.group_incidence(gid)
            if incidence <= 0:
                continue
            blocking_groups = Counter()
            for reject in self.rejects:
                if reject.get('group_id') != gid:
                    continue
                for rid in reject.get('blocking') or []:
                    entry = self.route_group.get(int(rid))
                    if entry and entry[0] != gid:
                        blocking_groups[entry[0]] += 1
            failed_groups.append((incidence, gid, blocking_groups))
        failed_groups.sort(reverse=True)
        joint_tried = set()
        for _incidence, gid, blocking_groups in failed_groups:
            if joint_actions >= MAX_JOINT_ACTIONS or self.time_left() <= 300.0:
                break
            if not any(rid in self.lifted for rid in self._route_of_group(gid)):
                continue
            partners = [partner for partner, _count in blocking_groups.most_common()
                        if partner != gid
                        and any(rid in self.lifted
                                for rid in self._route_of_group(partner))]
            if not partners:
                others = [other for other in lifted_groups
                          if other != gid
                          and any(rid in self.lifted
                                  for rid in self._route_of_group(other))]
                others.sort(key=lambda other: -self.group_incidence(other))
                partners = others[:1]
            for partner in partners[:2]:
                key = tuple(sorted((gid, partner)))
                if key in joint_tried:
                    continue
                joint_tried.add(key)
                result = self.try_joint(gid, partner)
                attempt = dict(group_ids=[gid, partner],
                               status=result['status'],
                               best_delta=(result.get('result') or {}).get('delta'))
                self.stage_records.setdefault('joint_attempts', []).append(attempt)
                if result['status'] != 'accepted':
                    continue
                plan_a = result['candidate_a']['plan']
                plan_b = result['candidate_b']['plan']
                action = dict(stage='joint', kind='joint_reschedule',
                              group_ids=[gid, partner],
                              old_layers=[self.current_group_layer(gid),
                                          self.current_group_layer(partner)],
                              new_layers=[(plan_a['layer_id'] if plan_a else 1),
                                          (plan_b['layer_id'] if plan_b else 1)],
                              old_intervals=[self.current_group_interval(gid),
                                             self.current_group_interval(partner)],
                              new_intervals=[
                                  (dict(rise_start_mm=plan_a['rise_start'],
                                        fall_start_mm=plan_a['fall_start'])
                                   if plan_a else None),
                                  (dict(rise_start_mm=plan_b['rise_start'],
                                        fall_start_mm=plan_b['fall_start'])
                                   if plan_b else None)])
                self.commit(self._route_of_group(gid)
                            + self._route_of_group(partner),
                            result['routes'], action)
                joint_actions += 1
                self.stage_records['joint_reschedules'].append(action)
                log(f'[dyn] joint groups {gid}+{partner} layers '
                    f'{action["old_layers"]}->{action["new_layers"]} pairs '
                    f'{action["pair_count_before"]}->{action["pair_count_after"]}')
                break

        # ---- stage 3: retry previously failed / unlifted quartets ----
        candidates = []
        for group in self.group_by_id.values():
            gid = int(group['group_id'])
            ids = [int(rid) for rid in group['route_ids']]
            if any(rid not in self.current_routes for rid in ids):
                continue
            if any(self.current_routes[rid].get('lifted') for rid in ids):
                continue
            bbox = None
            for rid in ids:
                record = self.routed_records[rid]
                xs = [prim['p0'][0] for prim in record['primitives']
                      if prim['kind'] == 'line']
                ys = [prim['p0'][1] for prim in record['primitives']
                      if prim['kind'] == 'line']
                if not xs:
                    continue
                box = (min(xs), min(ys), max(xs), max(ys))
                bbox = box if bbox is None else (min(bbox[0], box[0]),
                                                min(bbox[1], box[1]),
                                                max(bbox[2], box[2]),
                                                max(bbox[3], box[3]))
            if bbox is None:
                continue
            changed = any(not (bbox[2] + 8 < cb[0] or cb[2] + 8 < bbox[0]
                               or bbox[3] + 8 < cb[1] or cb[3] + 8 < bbox[1])
                          for cb in self.changed_bboxes)
            if not changed and self.changed_bboxes:
                continue
            candidates.append((self.group_incidence(gid), gid))
        candidates.sort(reverse=True)
        for _incidence, gid in candidates:
            if retry_actions >= MAX_RETRY_ACTIONS or self.time_left() <= 30:
                break
            group = self.group_by_id[gid]
            ids = [int(rid) for rid in group['route_ids']]
            if any(self.current_routes[rid].get('lifted') for rid in ids):
                continue
            base_world = self._world_without(ids)
            plans = self.generate_plans(ids[0], ids)
            evaluated = []
            for plan in plans[:16]:
                routes = self.build_candidate(gid, plan)
                if routes is None:
                    continue
                result = self._evaluate(routes, ids, base_world)
                if result['status'] == 'ok':
                    evaluated.append(dict(plan=plan, routes=routes,
                                          result=result))
            evaluated.sort(key=lambda item: -item['result']['delta'])
            accepted = None
            for item in evaluated[:2]:
                override = dict(self.current_routes)
                override.update({int(rid): route
                                 for rid, route in item['routes'].items()})
                ok, _report = self._tentative_ok(override)
                if ok:
                    accepted = item
                    break
            if accepted is None:
                self.stage_records.setdefault('retry_attempts', []).append(
                    dict(group_id=gid, status='rejected',
                         candidates=len(plans)))
                continue
            action = dict(stage='retry', kind='failed_group_retry', group_id=gid,
                          new_layer=accepted['plan']['layer_id'],
                          new_interval=dict(
                              rise_start_mm=accepted['plan']['rise_start'],
                              fall_start_mm=accepted['plan']['fall_start']))
            self.commit(ids, accepted['routes'], action)
            retry_actions += 1
            self.stage_records['failed_retries'].append(action)
            self.stage_records.setdefault('retry_attempts', []).append(
                dict(group_id=gid, status='accepted',
                     layer_id=action['new_layer']))
            self.stage_records['recovered_failed_groups'].append(gid)
            self.recovered_groups.append(gid)
            log(f'[dyn] retry recovered group {gid} -> L{action["new_layer"]} '
                f'pairs {action["pair_count_before"]}->{action["pair_count_after"]}')

        return dict(single_actions=single_actions, joint_actions=joint_actions,
                    retry_actions=retry_actions,
                    pair_count=len(self.pair_set), version=self.layout_version)

    # ------------------------------------------------------------------
    def summary(self, validation=None):
        lifted_groups = sorted({self.route_group[rid][0] for rid in self.lifted})
        transitions = sum(int(route.get('n_transitions') or 0)
                          for route in self.lifted.values())
        length_before = self.initial_lengths
        length_after = sum(route['length_mm']
                           for route in self.current_routes.values())
        validation = validation or {}
        return dict(
            schema='v4_c4_dynamic_layer_optimization_summary_v1',
            routed_before=1020, routed_after=len(self.routed_ids),
            unique_crossing_pairs_before=int(self.initial_pair_count),
            unique_crossing_pairs_after=int(len(self.pair_set)),
            crossing_reduction=int(self.initial_pair_count - len(self.pair_set)),
            crossing_reduction_ratio=round(
                (self.initial_pair_count - len(self.pair_set))
                / max(1, self.initial_pair_count), 6),
            single_group_reschedules=len(self.stage_records['dynamic_layer_changes'])
            + len(self.stage_records['interval_moves'])
            + len(self.stage_records['revert_to_flat']),
            dynamic_layer_changes=len(self.stage_records['dynamic_layer_changes']),
            interval_moves=len(self.stage_records['interval_moves']),
            joint_reschedules=len(self.stage_records['joint_reschedules']),
            recovered_failed_groups=len(self.recovered_groups),
            recovered_group_ids=sorted(set(self.recovered_groups)),
            joint_attempts=len(self.stage_records.get('joint_attempts') or []),
            retry_attempts=len(self.stage_records.get('retry_attempts') or []),
            lifted_groups_after=len(lifted_groups),
            transitions_after=int(transitions),
            length_total_before_mm=round(float(length_before), 4),
            length_total_after_mm=round(float(length_after), 4),
            length_delta_mm=round(float(length_after - length_before), 4),
            validation_status=validation.get('status'),
            validation_pass=bool(validation.get('exploratory_pass')),
            validation_counts=validation.get('counts'),
            layout_version=self.layout_version,
            accepted_actions=len(self.actions),
            rejected_candidates=len(self.rejects),
            input_hashes=self.input_hashes,
            layer_heights_mm={str(int(layer.layer_id)): float(layer.physical_z_mm)
                              for layer in self.stack.routing_layers},
            time_limit_seconds=self.time_limit,
            runtime_seconds=round(time.perf_counter() - self.started, 2),
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
