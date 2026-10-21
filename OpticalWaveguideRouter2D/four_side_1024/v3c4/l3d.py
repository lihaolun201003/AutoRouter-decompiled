"""Experiment 3 (V3_C4_L3D): group-atomic L2-L5 lift of the failed C4 groups.

Pipeline
--------
1. Load the V3_C4_2D result as the flat-L1 baseline (one row height per plane).
2. Plane-first retry: failed groups are retried in-plane with a larger candidate
   budget (still group-atomic).
3. Layer lift: for the remaining failed groups, the representative 2D path of
   each candidate is lifted with the corrected L1-L5 model
   (``l3d.paths.build_route_l3d``, exploratory ``medium_050`` stack) and the four
   rotation members are generated, checked jointly in the true-XYZ
   ``l3d.world.World`` (same-physical-plane strict 2D + >=0.08 mm true 3D
   clearance) and committed atomically.
4. Integrated acceptance: the saved ``routes_l3d.json`` is re-read and validated
   with the repository validator ``l3d.validate_l3d`` (V3-C4 port identity
   injected) plus a C4 symmetry audit of the 3D group geometries.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import time
from collections import Counter
from pathlib import Path

from .profile import apply as apply_profile

TOL = 1e-6


def _jsonable_args(args):
    return {key: (str(value) if isinstance(value, Path) else value)
            for key, value in vars(args).items()}


# ---------------------------------------------------------------------------
# 3D geometry rotation / reversal
# ---------------------------------------------------------------------------
def _rot_xy(point):
    return [150.0 - float(point[1]), float(point[0])]


def _rot_vec(vector):
    return [-float(vector[1]), float(vector[0])]


def _rotate_part(part, times=1):
    part = dict(part)
    if part['kind'] == 'flat':
        from . import inputs as V3
        part['primitives'] = V3.rotate_primitives(part['primitives'], times)
        return part
    start = list(part['start'])
    direction = list(part['direction'])
    end = list(part['end'])
    for _ in range(int(times) % 4):
        start, direction, end = _rot_xy(start), _rot_vec(direction), _rot_xy(end)
    part['start'], part['direction'], part['end'] = start, direction, end
    return part


def rotate_route(route, times=1):
    """Rotate one L3D route by ``times`` x 90 deg about the board centre."""
    times = int(times) % 4
    if times == 0:
        return copy.deepcopy(route)
    out = dict(route)
    out['parts'] = [_rotate_part(part, times) for part in route['parts']]
    for key in ('source_port', 'target_port'):
        if key in out and 'xy' in out[key]:
            port = dict(out[key])
            port['xy'] = _rot_xy(port['xy'])
            out[key] = port
    for key in ('start_dir', 'end_dir'):
        if key in out and out[key] is not None:
            out[key] = _rot_vec(out[key])
    return out


def _reverse_part(part):
    part = dict(part)
    if part['kind'] == 'flat':
        from . import inputs as V3
        part['primitives'] = V3.reverse_primitives(part['primitives'])
        return part
    new = dict(part)
    new['start'] = list(part['end'])
    new['end'] = list(part['start'])
    new['direction'] = [-float(value) for value in part['direction']]
    new['z0'] = float(part['z1'])
    new['z1'] = float(part['z0'])
    new['dz_mm'] = -float(part['dz_mm'])
    new['from_layer'] = int(part['to_layer'])
    new['to_layer'] = int(part['from_layer'])
    return new


def reverse_route(route):
    out = dict(route)
    out['parts'] = [_reverse_part(part) for part in reversed(route['parts'])]
    out['layer_sequence'] = list(reversed(route['layer_sequence']))
    out['layer_z_sequence'] = list(reversed(route['layer_z_sequence']))
    out['start_z_mm'] = float(route['end_z_mm'])
    out['end_z_mm'] = float(route['start_z_mm'])
    for key_a, key_b in (('source_port', 'target_port'),):
        if key_a in out and key_b in out:
            out[key_a], out[key_b] = out[key_b], out[key_a]
    return out


def route_start_xy(route):
    for part in route['parts']:
        if part['kind'] == 'flat':
            return tuple(float(v) for v in part['primitives'][0]['p0'])
    raise ValueError('route has no flat part')


def route_end_xy(route):
    for part in reversed(route['parts']):
        if part['kind'] == 'flat':
            return tuple(float(v) for v in part['primitives'][-1]['p1'])
    raise ValueError('route has no flat part')


def _close(a, b):
    return abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL


def orient_route_to(route, frame):
    """Orient a rotated route so that it starts at ``frame.src_xy``."""
    start, end = route_start_xy(route), route_end_xy(route)
    if _close(start, frame.src_xy) and _close(end, frame.dst_xy):
        return route
    if _close(end, frame.src_xy) and _close(start, frame.dst_xy):
        return reverse_route(route)
    raise ValueError(f'rotated route does not match frame endpoints '
                     f'{start}->{end} vs {frame.src_xy}->{frame.dst_xy}')


# ---------------------------------------------------------------------------
# C4 3D group assembly / audit
# ---------------------------------------------------------------------------
def rotate_to_member(rep_route, phase, member_frame):
    rotated = rotate_route(rep_route, phase)
    return orient_route_to(rotated, member_frame)


def _flat_key(part):
    out = []
    for primitive in part['primitives']:
        kind = primitive.get('kind')
        if kind == 'line':
            out.append(('L', tuple(round(float(v), 6) for v in primitive['p0']),
                        tuple(round(float(v), 6) for v in primitive['p1']),
                        int(part['layer_id']), round(float(part['z_mm']), 6)))
        else:
            out.append(('A', tuple(round(float(v), 6) for v in primitive['p0']),
                        tuple(round(float(v), 6) for v in primitive['p1']),
                        tuple(round(float(v), 6) for v in primitive['center']),
                        round(float(primitive['radius']), 6),
                        round(float(primitive['start_angle']), 9),
                        round(float(primitive['sweep']), 9),
                        int(part['layer_id']), round(float(part['z_mm']), 6)))
    return tuple(out)


def _transition_key(part):
    return ('T', int(part['from_layer']), int(part['to_layer']),
            round(float(part['z0']), 6), round(float(part['z1']), 6),
            tuple(round(float(v), 6) for v in part['start']),
            tuple(round(float(v), 6) for v in part['direction']),
            tuple(round(float(v), 6) for v in part['end']),
            round(float(part['footprint_mm']), 6), round(float(part['length_mm']), 6))


def route_geometry_key(route):
    return tuple(_flat_key(part) if part['kind'] == 'flat' else _transition_key(part)
                 for part in route['parts'])


def audit_c4_3d(records, groups, log=print):
    """Verify every routed group's four 3D geometries are exact rigid rotations."""
    by_id = {int(record['route_id']): record for record in records}
    errors = []
    complete = 0
    partial = 0
    empty = 0
    for group in groups:
        members = [by_id.get(rid) for rid in group['route_ids']]
        routed = [m for m in members if m and m.get('status') == 'routed']
        if not routed:
            empty += 1
            continue
        if len(routed) != 4:
            partial += 1
            errors.append(dict(group_id=group['group_id'], kind='partial'))
            continue
        complete += 1
        base = members[0]
        for phase in range(1, 4):
            try:
                rotated = rotate_route(base, phase)
                oriented = reverse_route(rotated) if not _close(
                    route_start_xy(rotated), _frame_xy(members[phase])[0]) else rotated
                if route_geometry_key(oriented) != route_geometry_key(members[phase]):
                    errors.append(dict(group_id=group['group_id'], phase=phase,
                                       route_id=members[phase]['route_id'],
                                       kind='rotation_mismatch'))
            except Exception as exc:                       # noqa: BLE001
                errors.append(dict(group_id=group['group_id'], phase=phase,
                                   kind=f'error:{type(exc).__name__}:{exc}'))
    report = dict(complete_groups=complete, partial_groups=partial,
                  empty_groups=empty, errors=errors[:20],
                  error_count=len(errors), passed=(not errors))
    log(f'[validate3d] C4 groups: complete={complete} partial={partial} '
        f'empty={empty} errors={len(errors)} -> '
        f'{"PASS" if report["passed"] else "FAIL"}')
    return report


def _frame_xy(record):
    return (tuple(float(v) for v in record['source_port']['xy']),
            tuple(float(v) for v in record['target_port']['xy']))


# ---------------------------------------------------------------------------
# baseline / flat retry
# ---------------------------------------------------------------------------
def load_c4_2d(root, plane, log=print):
    path = Path(root) / 'c4_2d' / plane / 'routes.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    records = {int(record['route_id']): record for record in payload['routes']}
    routed = {rid: record for rid, record in records.items()
              if record.get('status') == 'routed'}
    log(f'{plane}: loaded C4_2D baseline {len(routed)}/512 from {path}')
    return payload, records, routed


def reconstruct_state(plane, routed_records, failed_records=None, log=print):
    """V3LayoutState holding the flat routed C4_2D routes (for flat retry)."""
    from ..d56.index import prepare
    from ..d56.search import RouteResult
    from .layout import V3LayoutState
    state = V3LayoutState('V3_C4', plane, log=log)
    for rid, record in sorted(routed_records.items()):
        primitives = [dict(p) for p in record['primitives']]
        prepared = prepare(primitives)
        result = RouteResult(rid, None, {}, primitives, prepared,
                             prepared.length, 0, 0, prepared.bend_count)
        state.accepted[rid] = result
        state.index.add(rid, prepared)
        state.oracles.add(rid, prepared)
    for rid, record in (failed_records or {}).items():
        state.failed[rid] = dict(
            route_id=rid,
            reason=record.get('reason') or 'not_attempted',
            evaluated=int(record.get('evaluated') or 0),
            rejection_counts=dict(record.get('rejection_counts') or {}),
            blockers=dict(record.get('blockers') or {}))
    return state


# ---------------------------------------------------------------------------
# group lift
# ---------------------------------------------------------------------------
def _candidate_iterator(state, rep_id, mode='both'):
    from ..d56.frames import RouteFrame
    from ..v2opt import candext
    frame = state.frames[rep_id]
    oracle = state.oracle_for(rep_id)
    if mode in ('d56', 'both'):
        if frame.kind == 'opposite':
            yield from candext.candidates_opposite(frame, oracle)
        else:
            yield from candext.candidates_adjacent(frame, oracle)
    if mode in ('ortho90', 'both'):
        from ..v2opt import ortho90
        generator = ortho90.Ortho90Generator(seed=20261019)
        for candidate in generator.candidates(frame, oracle):
            yield candidate


def _split_sequences(stage='single'):
    from ..l3d import layers
    singles = layers.plan_sequences('single')
    multi = layers.plan_sequences('multi')
    pairs = [seq for seq in multi if len(seq) == 4]
    triples = [seq for seq in multi if len(seq) > 4]
    return singles, pairs, triples


def attempt_group_lift(plane, group, state, world, stack, frames, routes_by_id,
                       budget=40, multi_budget=12, log=print):
    """Try to lift one rotation group atomically; return (records, info) or (None, info)."""
    from ..fslw import config as C
    from ..l3d import common as LC
    from ..l3d import paths as LP
    from ..l3d.world import World

    rep_id = group['route_ids'][0]
    frame = frames[rep_id]
    row_z = stack.interface.z_for_row(plane)
    port_meta = LC.port_meta(plane, frame)
    singles, pairs, triples = _split_sequences()
    sequences = list(singles)
    evaluated = 0
    built = 0
    blockers = set()
    for candidate in _candidate_iterator(state, rep_id):
        if evaluated >= budget:
            break
        evaluated += 1
        world_prims = frame.to_world(candidate['primitives'])
        seq_groups = [('single', singles)]
        if evaluated <= multi_budget:
            seq_groups.append(('pair', pairs[:6]))
        for stage_name, seqs in seq_groups:
            for sequence in seqs:
                z_sequence = stack.z_sequence_for(sequence, row=plane)
                try:
                    route = LP.build_route_l3d(
                        rep_id, plane, world_prims, sequence, z_sequence,
                        port_meta, radius=float(C.RADIUS_MM), variant=0,
                        family=candidate.get('family'),
                        params=candidate.get('params') or {})
                except ValueError:
                    continue
                if route is None:
                    continue
                if World.check_structure(route):
                    continue
                built += 1
                # four rotation members, oriented to the CSV endpoints
                members = [route]
                ok = True
                for phase in range(1, 4):
                    member_frame = frames[group['route_ids'][phase]]
                    try:
                        member = rotate_to_member(route, phase, member_frame)
                    except ValueError:
                        ok = False
                        break
                    if World.check_structure(member):
                        ok = False
                        break
                    members.append(member)
                if not ok:
                    continue
                # (a) each member against the committed 3D world
                violations = []
                for member in members:
                    violations = world.check_route(member, check_self=True)
                    if violations:
                        for violation in violations:
                            for block in violation.get('blockers') or []:
                                blockers.add(int(block))
                        break
                if violations:
                    continue
                # (b) members against each other (rigid rotations -> rep vs R^k)
                temp = World(stack)
                temp.add_route(members[0])
                pair_ok = True
                for member in members[1:]:
                    if temp.check_route(member, check_self=True):
                        pair_ok = False
                        break
                if not pair_ok:
                    continue
                # commit
                schema_records = []
                for phase, member in enumerate(members):
                    member_route_id = int(group['route_ids'][phase])
                    member = dict(member)
                    member['route_id'] = member_route_id
                    member_frame = frames[member_route_id]
                    record = LC.route_to_record(member, member_frame)
                    record['c4_symmetry'] = 'strict_group_lift'
                    schema_records.append(record)
                    world.add_route(member)
                info = dict(evaluated=evaluated, built=built,
                            blocker_routes=sorted(blockers)[:20],
                            layer_sequence=route['layer_sequence'],
                            xy_length_mm=route['xy_length_mm'],
                            length_mm=route['length_mm'],
                            n_transitions=route['n_transitions'])
                return schema_records, info
    return None, dict(evaluated=evaluated, built=built,
                      blocker_routes=sorted(blockers)[:20])


# ---------------------------------------------------------------------------
# main pipeline
# ---------------------------------------------------------------------------
def run(c4_root, out_dir, planes=('z1', 'z2'), stack_name='medium_050',
        flat_retry_budget=1600, candidate_budget=40, multi_budget=12,
        limit_groups=0, log=print):
    apply_profile()
    from ..fslw import config as C
    from ..l3d import common as LC
    from ..l3d import layers
    from ..l3d.world import World
    from . import inputs as V3
    from .c4 import GroupRouter, order_groups

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'run.log'

    def logline(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        with open(log_path, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    started = time.perf_counter()
    stack = layers.build_stack(stack_name)
    stack.write(out_dir / 'layer_stack.json')
    logline(f'V3_C4_L3D stack={stack.name} heights='
            f'{stack.to_dict()["routing_heights_mm"]} provenance={stack.provenance}')

    groups_all, route_group = V3.build_groups()
    frames = {}
    routes_by_id = {}
    for all_plane in ('z1', 'z2'):
        state0 = reconstruct_state(all_plane, {}, log=lambda *_a, **_k: None)
        frames.update(state0.frames)
        routes_by_id.update(state0.route_by_id)
        del state0

    # ------------------------------------------------------------------
    # Phase 1: per-plane baseline + plane-first (flat) group retry
    # ------------------------------------------------------------------
    records3d = {}
    flat_internal = {}
    states = {}
    remaining_by_plane = {}
    flat_retry_info = {}
    for plane in planes:
        _c4_payload, c4_records, routed = load_c4_2d(c4_root, plane, log=logline)
        state = reconstruct_state(plane, routed, log=logline)
        states[plane] = state
        plane_groups = [g for g in groups_all if g['plane'] == plane]
        plane_failed = [g for g in plane_groups
                        if not all(c4_records[rid].get('status') == 'routed'
                                   for rid in g['route_ids'])]
        logline(f'{plane}: baseline routed={len(state.accepted)}/512 '
                f'failed_groups={len(plane_failed)}')
        if plane_failed and flat_retry_budget > 0:
            router = GroupRouter(state, plane_failed, all_groups=plane_groups,
                                 log=logline)
            order = order_groups(plane_failed, router.blocks, mode='easy')
            if limit_groups:
                order = order[:limit_groups]
            _details, summary = router.route_all(order, flat_retry_budget,
                                                checkpoint_every=8)
            flat_retry_info[plane] = dict(
                attempted=len(order), applied_groups=len(router.group_results),
                routed_routes=len(state.accepted), seconds=summary['seconds'])
            logline(f'{plane}: flat retry recovered groups='
                    f'{len(router.group_results)} routed={len(state.accepted)}')
        for rid, result in state.accepted.items():
            frame = state.frames[rid]
            internal = LC.build_flat_record(rid, plane, result.primitives, frame)
            flat_internal[rid] = internal
            records3d[rid] = LC.route_to_record(internal, frame)
        remaining = [g for g in plane_groups
                     if not all(rid in state.accepted for rid in g['route_ids'])]
        if limit_groups:
            remaining = remaining[:limit_groups]
        remaining_by_plane[plane] = remaining

    # ------------------------------------------------------------------
    # Phase 2: ONE shared true-XYZ world for both planes.
    # The z1 interface row (z=0) lifts climb through z=0.5, i.e. they pass
    # through the z2 interface plane; the cross-plane clearance check must
    # therefore see the z2 flat routes as well.
    # ------------------------------------------------------------------
    world = World(stack)
    for _rid, internal in sorted(flat_internal.items()):
        world.add_route(internal)
    logline(f'3D world: {len(world.plan)} flat L1 routes from both planes')

    # ------------------------------------------------------------------
    # Phase 3: group-atomic layer lift against the shared world
    # ------------------------------------------------------------------
    lift_info = {}
    for plane in planes:
        state = states[plane]
        remaining = remaining_by_plane.get(plane) or []
        if not remaining:
            continue
        logline(f'{plane}: lift phase groups={len(remaining)}')
        for group in order_groups(remaining, routes_by_id, mode='easy'):
            schema_records, info = attempt_group_lift(
                plane, group, state, world, stack, state.frames,
                state.route_by_id, budget=candidate_budget,
                multi_budget=multi_budget, log=logline)
            info['group_id'] = group['group_id']
            if schema_records is not None:
                for record in schema_records:
                    records3d[int(record['route_id'])] = record
                info['status'] = 'lifted'
                lift_info.setdefault(plane, []).append(info)
                logline(f'{plane}: LIFTED group {group["group_id"]} '
                        f'layers={info["layer_sequence"]} '
                        f'xy_len={info["xy_length_mm"]:.1f} '
                        f'trans={info["n_transitions"]}')
            else:
                info['status'] = 'failed'
                lift_info.setdefault(plane, []).append(info)
                logline(f'{plane}: lift FAILED group {group["group_id"]} '
                        f'evaluated={info.get("evaluated")} '
                        f'built={info.get("built")}')

    # ------------------------------------------------------------------
    # final records
    # ------------------------------------------------------------------
    records = []
    for rid in range(1, 1025):
        if rid in records3d:
            record = dict(records3d[rid])
            record['status'] = 'routed'
            if 'c4_symmetry' not in record:
                record['c4_symmetry'] = 'strict_group_commit'
            records.append(record)
        else:
            plane = routes_by_id[rid]['plane']
            frame = frames[rid]
            reason = 'unplaceable_in_3d' if plane in planes else 'not_run'
            records.append(LC.failed_record(rid, plane, frame, reason,
                                            baseline_2d=False, stage='c4_l3d'))
    for record in records:
        expected = routes_by_id[int(record['route_id'])]
        record['source_endpoint'] = expected['source_endpoint']
        record['target_endpoint'] = expected['target_endpoint']
    routed_records = [record for record in records if record['status'] == 'routed']
    lifted_records = [record for record in routed_records if record.get('lifted')]
    transitions = sum(int(record['n_transitions']) for record in routed_records)
    layer_counts = Counter()
    for record in routed_records:
        for part in record['parts']:
            if part['kind'] == 'flat':
                layer_counts[str(part['layer_id'])] += 1
    failed_groups = {}
    for group in groups_all:
        if all(rid in records3d for rid in group['route_ids']):
            continue
        failed_groups.setdefault(group['plane'], []).append(dict(
            group_id=group['group_id'], kind=group['kind'],
            route_ids=group['route_ids'], reason='no_legal_lift'))
    routed_groups = sum(1 for group in groups_all
                        if all(rid in records3d for rid in group['route_ids']))
    statistics = dict(
        baseline_routed=sum(1 for record in routed_records
                            if not record.get('lifted')),
        routed=len(routed_records), failed=1024 - len(routed_records),
        lifted=len(lifted_records), transitions=int(transitions),
        total_length_mm=round(sum(float(record['length_mm'])
                                  for record in routed_records), 6),
        per_plane={plane: dict(
            routed=sum(1 for record in routed_records if record['plane'] == plane),
            lifted=sum(1 for record in routed_records
                       if record['plane'] == plane and record.get('lifted')))
            for plane in planes},
        per_layer_flat_parts=dict(layer_counts),
        groups=dict(routed_groups=routed_groups,
                    failed_groups=256 - routed_groups))
    stack_payload = stack.to_dict()
    payload = dict(
        schema='four_side_1024_v2_l3d_routes_v1',
        experiment='V3_C4_L3D: corrected L1-L5 model, group-atomic C4 lift '
                   'of the V3_C4_2D failures',
        scheme='A', scheme_label='A_shortS', xy_model='d56', stage='c4_l3d',
        layer_stack=stack_payload,
        process=LC.process_record(),
        budget=dict(flat_retry_budget=int(flat_retry_budget),
                    candidate_budget=int(candidate_budget),
                    multi_budget=int(multi_budget), stack=stack.name),
        route_count=len(records), routed=len(routed_records),
        failed=len(records) - len(routed_records),
        statistics=statistics,
        router=dict(forced_symmetry=True, group_atomic=True,
                    flat_retry=flat_retry_info, lift=lift_info,
                    failed_groups=failed_groups,
                    seconds=round(time.perf_counter() - started, 2)),
        v3c4=dict(topology='V3_C4', connectivity_csv=str(V3.V3_CSV),
                  connectivity_sha256=V3.EXPECTED_V3_SHA256,
                  rotation_groups=len(groups_all),
                  routed_groups=routed_groups),
        routes=records,
    )
    payload_path = out_dir / 'routes_l3d.json'
    payload_path.write_text(json.dumps(payload, ensure_ascii=False),
                            encoding='utf-8')
    logline(f'written {payload_path} routed={len(routed_records)} '
            f'lifted={len(lifted_records)}')
    # ------------------------------------------------------------------
    # integrated validation: C4 3D symmetry + repository validate_l3d
    # ------------------------------------------------------------------
    c4_report = audit_c4_3d(records, groups_all, log=logline)
    validator_report = validate_payload_with_identity(payload, log=logline)
    passed = bool(c4_report['passed'] and
                  (validator_report.get('geometry_pass')
                   or validator_report.get('exploratory_pass')))
    validation = dict(
        schema='four_side_1024_v3_c4_l3d_experiment_validation_v1',
        experiment='V3_C4_L3D', passed=passed,
        c4_symmetry=c4_report,
        l3d_validator=dict(status=validator_report.get('status'),
                           formal_acceptance=validator_report.get('formal_acceptance'),
                           exploratory_pass=validator_report.get('exploratory_pass'),
                           geometry_pass=validator_report.get('geometry_pass'),
                           exit_code=validator_report.get('exit_code'),
                           counts=validator_report.get('counts'),
                           checks=validator_report.get('checks')),
        validator_full=validator_report)
    (out_dir / 'validation.json').write_text(
        json.dumps(validation, indent=1, ensure_ascii=False), encoding='utf-8')
    checkpoint = dict(
        schema='four_side_1024_v3c4_l3d_checkpoint_v1',
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'),
        stack=stack_payload, routed=len(routed_records),
        lifted=len(lifted_records),
        routed_route_ids=[int(record['route_id']) for record in routed_records],
        failed_route_ids=[int(record['route_id']) for record in records
                          if record['status'] != 'routed'],
        failed_groups=failed_groups)
    (out_dir / 'checkpoint.json').write_text(
        json.dumps(checkpoint, ensure_ascii=False), encoding='utf-8')
    run_summary = dict(
        experiment='V3_C4_L3D', stack=stack.name,
        routed=len(routed_records), failed=len(records) - len(routed_records),
        lifted=len(lifted_records), transitions=int(transitions),
        routed_groups=routed_groups, failed_groups=256 - routed_groups,
        flat_retry=flat_retry_info, seconds=round(time.perf_counter() - started, 2),
        validation_passed=passed, c4_symmetry_passed=c4_report['passed'],
        l3d_validator=dict(status=validator_report.get('status'),
                           exploratory_pass=validator_report.get('exploratory_pass'),
                           geometry_pass=validator_report.get('geometry_pass'),
                           counts=validator_report.get('counts')))
    (out_dir / 'run_summary.json').write_text(
        json.dumps(run_summary, indent=1, ensure_ascii=False), encoding='utf-8')
    logline(f'V3_C4_L3D done routed={len(routed_records)} '
            f'lifted={len(lifted_records)} '
            f'validation={"PASS" if passed else "FAIL"}')
    return run_summary


def validate_payload_with_identity(payload, log=print):
    """Run the repository 3D validator on our payload with V3-C4 port identity."""
    from ..fslw import ports as FSPORTS
    from ..l3d import validate_l3d as V
    from . import inputs as V3
    identity = {'available': True, 'error': None, 'planes': {}}
    for plane in V3.PLANES:
        routes, endpoints, _connectors, _validation = V3.load_plane(plane)
        identity['planes'][plane] = {
            'routes': {int(record['route_id']): record for record in routes},
            'endpoints': endpoints,
        }
    V._PORT_CACHE['identity'] = identity
    V._port_identity = lambda: identity
    log('[validate3d] running l3d.validate_l3d.validate_payload with V3-C4 identity '
        'injected')
    report = V.validate_payload(payload, allow_exploratory=True)
    log(f"[validate3d] validator status={report.get('status')} "
        f"exploratory_pass={report.get('exploratory_pass')} "
        f"geometry_pass={report.get('geometry_pass')} "
        f"counts={report.get('counts')}")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--c4-root', type=Path,
                        default=Path('outputs/four_side_1024_v3_c4_routing'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--stack', default='medium_050')
    parser.add_argument('--flat-retry-budget', type=int, default=1600)
    parser.add_argument('--candidate-budget', type=int, default=40)
    parser.add_argument('--multi-budget', type=int, default=12)
    parser.add_argument('--limit-groups', type=int, default=0)
    parser.add_argument('--planes', default='z1,z2')
    args = parser.parse_args(argv)
    planes = tuple(value.strip() for value in args.planes.split(',') if value.strip())
    c4_root = args.c4_root if args.c4_root.is_absolute() else (
        Path(__file__).resolve().parents[2] / args.c4_root)
    summary = run(c4_root, args.out, planes=planes, stack_name=args.stack,
                  flat_retry_budget=args.flat_retry_budget,
                  candidate_budget=args.candidate_budget,
                  multi_budget=args.multi_budget,
                  limit_groups=args.limit_groups)
    print(json.dumps({key: summary[key] for key in
                      ('routed', 'failed', 'lifted', 'routed_groups',
                       'seconds', 'validation_passed')}, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    main()
