"""Integrated 2D acceptance for V3-C4 routing results.

Reuses the frozen authoritative checker ``four_side_1024.fslw.validate_fslw``
(``check_route_primitives`` for single-route legality + ``audit_route_pairs``
with the R15-round ``policy='strict'``).  The process profile must already be
applied (R = 15 mm) before this module is imported.
"""
from __future__ import annotations

import math
from collections import Counter

from ..fslw import config as C
from ..fslw import validate_fslw as V
from . import inputs as V3


def _endpoint_record(eid):
    ep = V3.ENDPOINTS[eid]
    return dict(routing_xy=list(ep['routing_xy']), inward=list(ep['inward']),
                side=ep['side'], row=ep['row'], column=ep['column'],
                connector=ep['connector'])


def audit_plane(routes_payload, plane, label='', log=print):
    """Audit one saved plane payload (``routes.json``) and return a report dict."""
    records = routes_payload.get('routes') or []
    expected_ids = {r['route_id'] for r in
                    V3.load_plane(plane)[0]}
    routed = [r for r in records if r.get('status') == 'routed']
    failed = [r for r in records if r.get('status') != 'routed']
    errors = []
    ids = {int(r['route_id']) for r in records}
    if len(records) != 512:
        errors.append(f'record_count:{len(records)}')
    if ids != expected_ids:
        errors.append(f'route_id_set_mismatch:{len(ids)}/{len(expected_ids)}')
    if len({int(r['route_id']) for r in routed}) != len(routed):
        errors.append('duplicate_routed_route_id')

    # ---- single-route geometry / port / radius checks
    geometry_errors = []
    lengths = []
    for record in routed:
        rid = int(record['route_id'])
        try:
            source = _endpoint_record(record['source_endpoint'])
            target = _endpoint_record(record['target_endpoint'])
        except KeyError as exc:
            geometry_errors.append((rid, f'unknown_endpoint:{exc}'))
            continue
        result = V.check_route_primitives(
            record['primitives'], source=source, target=target,
            width=C.WIDTH_MM, radius=C.RADIUS_MM, board=C.BOARD_MM,
            clearance=C.CLEARANCE_MM)
        if not result['passed']:
            geometry_errors.append((rid, result['errors'][:4]))
        lengths.append(float(result['length_mm']))

    # ---- pairwise strict audit (frozen validator, R15 round policy)
    prepared = []
    pair_parse_errors = []
    for record in routed:
        try:
            prepared.append(V.prepare_route(record['primitives'],
                                            route_id=int(record['route_id'])))
        except Exception as exc:                            # noqa: BLE001
            pair_parse_errors.append((record.get('route_id'), str(exc)))
    pair_audit = V.audit_route_pairs(prepared, clearance=C.CLEARANCE_MM,
                                     sagitta=C.SAGITTA_MM, policy='strict')
    violations = pair_audit['violations']
    report = dict(
        schema='four_side_1024_v3_c4_2d_validation_v1',
        plane=plane, label=label,
        csv_sha256=routes_payload.get('csv_sha256', ''),
        radius_mm=C.RADIUS_MM, board_mm=C.BOARD_MM,
        clearance_mm=C.CLEARANCE_MM, strict_policy='fslw.validate_fslw strict',
        routed=len(routed), failed=len(failed), total=len(records),
        geometry_errors=geometry_errors[:20], geometry_error_count=len(geometry_errors),
        pair_parse_errors=pair_parse_errors[:20],
        pair_audit=dict(policy=pair_audit['policy'],
                        candidate_pair_count=pair_audit['candidate_pair_count'],
                        crossing_count=pair_audit['crossing_count'],
                        crossing_pair_count=pair_audit['crossing_pair_count'],
                        min_non_crossing_centerline_mm=pair_audit[
                            'min_non_crossing_centerline_mm'],
                        violations=violations[:20],
                        violation_count=pair_audit['violation_pair_count']),
        total_length_mm=round(sum(lengths), 4),
        mean_length_mm=round(sum(lengths) / len(lengths), 4) if lengths else None,
        failed_routes=[dict(route_id=int(r['route_id']),
                            reason=(r.get('reason') or 'not_attempted'))
                       for r in failed],
    )
    report['passed'] = bool(not errors and not geometry_errors
                            and not pair_parse_errors and not violations)
    report['errors'] = errors
    log(f'[validate2d] {label or plane}: routed={len(routed)} failed={len(failed)} '
        f'geometry_errors={len(geometry_errors)} strict_violations={len(violations)} '
        f'-> {"PASS" if report["passed"] else "FAIL"}')
    return report


# ---------------------------------------------------------------------------
# C4 symmetry audit
# ---------------------------------------------------------------------------
def _primitive_key(primitives, digits=6):
    out = []
    for prim in primitives:
        kind = prim.get('kind')
        if kind == 'line':
            out.append(('L', tuple(round(float(v), digits) for v in prim['p0']),
                        tuple(round(float(v), digits) for v in prim['p1'])))
        else:
            out.append(('A', tuple(round(float(v), digits) for v in prim['p0']),
                        tuple(round(float(v), digits) for v in prim['p1']),
                        tuple(round(float(v), digits) for v in prim['center']),
                        round(float(prim['radius']), digits),
                        round(float(prim['start_angle']), digits),
                        round(float(prim['sweep']), digits)))
    return tuple(out)


def audit_c4_groups(records, groups, route_group, log=print):
    """Verify every routed group's four geometries are exact 90 deg rotations."""
    by_id = {int(r['route_id']): r for r in records}
    errors = []
    complete_groups = 0
    partial_groups = 0
    empty_groups = 0
    for group in groups:
        members = [by_id.get(rid) for rid in group['route_ids']]
        routed = [m for m in members if m and m.get('status') == 'routed']
        if len(routed) == 0:
            empty_groups += 1
            continue
        if len(routed) != 4:
            partial_groups += 1
            errors.append(dict(group_id=group['group_id'], kind='partial',
                               routed=[m['route_id'] for m in routed]))
            continue
        complete_groups += 1
        base = members[0]
        base_prims = base['primitives']
        for phase in range(1, 4):
            member = members[phase]
            rotated = V3.rotate_primitives(base_prims, phase)
            oriented, reversed_flag = V3.orient_primitives(
                rotated, member['source_endpoint'], member['target_endpoint'])
            expected = _primitive_key(oriented)
            actual = _primitive_key(member['primitives'])
            if expected != actual:
                mismatched = sum(1 for a, b in zip(expected, actual) if a != b)
                errors.append(dict(group_id=group['group_id'], phase=phase,
                                   route_id=member['route_id'],
                                   kind='rotation_mismatch',
                                   primitives=len(expected),
                                   mismatched=mismatched,
                                   reversed=reversed_flag))
    report = dict(complete_groups=complete_groups,
                  partial_groups=partial_groups, empty_groups=empty_groups,
                  errors=errors[:20], error_count=len(errors),
                  passed=(not errors))
    log(f'[validate2d] C4 groups: complete={complete_groups} partial={partial_groups} '
        f'empty={empty_groups} errors={len(errors)} -> '
        f'{"PASS" if report["passed"] else "FAIL"}')
    return report


# ---------------------------------------------------------------------------
# full-layout (all 1024) checks
# ---------------------------------------------------------------------------
def audit_full_coverage(records, log=print):
    """All 2048 physical ports used exactly once by the 1024 records."""
    usage = Counter()
    errors = []
    for record in records:
        try:
            usage[(record['source_side'], record['source_connector'],
                   int(record['source_row']), int(record['source_column']))] += 1
            usage[(record['target_side'], record['target_connector'],
                   int(record['target_row']), int(record['target_column']))] += 1
        except KeyError as exc:
            errors.append(f'missing_field:{exc}')
    expected = set(V3.ENDPOINTS)
    used_ids = {f'{conn}:{row}:{col}' for (side, conn, row, col) in usage}
    if len(records) != 1024:
        errors.append(f'record_count:{len(records)}')
    if used_ids != expected:
        errors.append(f'port_set_mismatch:{len(used_ids)}/{len(expected)}')
    if set(usage.values()) != {1}:
        errors.append('port_used_multiple_times')
    routed = sum(1 for r in records if r.get('status') == 'routed')
    report = dict(records=len(records), routed=routed,
                  unique_ports=len(used_ids), port_set_match=(used_ids == expected),
                  ports_used_once=(set(usage.values()) == {1}),
                  errors=errors, passed=(not errors))
    log(f'[validate2d] full coverage: records={len(records)} routed={routed} '
        f'ports={len(used_ids)} -> {"PASS" if report["passed"] else "FAIL"}')
    return report
