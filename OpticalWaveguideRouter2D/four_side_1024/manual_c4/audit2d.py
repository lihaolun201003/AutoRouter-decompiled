"""Independent 2D acceptance for the new manual C4 routing results.

Reuses the frozen authoritative checker ``four_side_1024.fslw.validate_fslw``
(single-route geometry + strict pair audit) and the unchanged C4 rotation audit of
``four_side_1024.v3c4.validate2d``.  Nothing here relaxes a physical constraint:
R = 15 mm, width 0.05 mm, non-exempt centreline clearance 0.08 mm, board 150 mm.
"""
from __future__ import annotations

from collections import Counter

from ..fslw import config as C
from ..fslw import validate_fslw as V
from . import connectivity as CONN


def _endpoint_record(eid):
    ep = CONN.endpoints()[eid]
    return dict(routing_xy=list(ep['routing_xy']), inward=list(ep['inward']),
                side=ep['side'], row=ep['row'], column=ep['column'],
                connector=ep['connector'])


def audit_plane(payload, plane, label='', log=print):
    """Audit one plane payload (``routes.json`` exactly as saved)."""
    records = payload.get('routes') or []
    expected_ids = {r['route_id'] for r in CONN.load_plane(plane)[0]}
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

    prepared = []
    pair_parse_errors = []
    for record in routed:
        try:
            prepared.append(V.prepare_route(record['primitives'],
                                            route_id=int(record['route_id'])))
        except Exception as exc:                              # noqa: BLE001
            pair_parse_errors.append((record.get('route_id'), str(exc)))
    pair_audit = V.audit_route_pairs(prepared, clearance=C.CLEARANCE_MM,
                                     sagitta=C.SAGITTA_MM, policy='strict')
    violations = pair_audit['violations']
    report = dict(
        schema='manual_c4_2d_validation_v1', plane=plane, label=label,
        csv_sha256=payload.get('csv_sha256') or CONN.combined_topology()[
            'combined_csv']['sha256'],
        radius_mm=C.RADIUS_MM, board_mm=C.BOARD_MM,
        clearance_mm=C.CLEARANCE_MM, width_mm=C.WIDTH_MM,
        strict_policy='fslw.validate_fslw strict',
        routed=len(routed), failed=len(failed), total=len(records),
        geometry_errors=geometry_errors[:20],
        geometry_error_count=len(geometry_errors),
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
    log(f'[audit2d] {label or plane}: routed={len(routed)} failed={len(failed)} '
        f'geometry_errors={len(geometry_errors)} strict_violations={len(violations)} '
        f'-> {"PASS" if report["passed"] else "FAIL"}')
    return report


def audit_c4(records, log=print):
    """C4 rotation audit over all 256 groups (reuses the frozen V3 audit code)."""
    from ..v3c4 import validate2d
    groups = CONN.combined_topology()['groups']
    route_group = CONN.route_group_map()
    report = validate2d.audit_c4_groups(records, groups, route_group, log=log)
    report['schema'] = 'manual_c4_c4_symmetry_validation_v1'
    report['groups_total'] = len(groups)
    return report


def audit_full_coverage(records, log=print):
    eps = CONN.endpoints()
    usage = Counter()
    errors = []
    for record in records:
        try:
            usage[record['source_endpoint']] += 1
            usage[record['target_endpoint']] += 1
        except KeyError as exc:
            errors.append(f'missing_field:{exc}')
    if len(records) != 1024:
        errors.append(f'record_count:{len(records)}')
    if set(usage) != set(eps):
        errors.append(f'port_set_mismatch:{len(set(usage))}/{len(eps)}')
    if set(usage.values()) != {1}:
        errors.append('port_used_multiple_times')
    routed = sum(1 for r in records if r.get('status') == 'routed')
    report = dict(schema='manual_c4_coverage_validation_v1',
                  records=len(records), routed=routed,
                  unique_ports=len(usage), port_set_match=(set(usage) == set(eps)),
                  ports_used_once=(set(usage.values()) == {1}),
                  errors=errors, passed=(not errors))
    log(f'[audit2d] full coverage: records={len(records)} routed={routed} '
        f'ports={len(usage)} -> {"PASS" if report["passed"] else "FAIL"}')
    return report


def audit_identity(records, log=print):
    """Every record must carry exactly the connectivity identity of its route_id."""
    topology = CONN.combined_topology()
    expected = {int(r['route_id']): r for r in topology['routes']}
    errors = []
    for record in records:
        rid = int(record['route_id'])
        want = expected.get(rid)
        if want is None:
            errors.append(f'unknown route_id {rid}')
            continue
        for field in ('source_endpoint', 'target_endpoint', 'relation',
                      'source_side', 'target_side', 'source_row', 'target_row'):
            if str(record.get(field)) != str(want.get(field)) and \
                    record.get(field) != want.get(field):
                errors.append(f'route {rid} field {field}: '
                              f'{record.get(field)} != {want.get(field)}')
        if record.get('plane') != want['plane']:
            errors.append(f'route {rid} plane mismatch')
        if record.get('status') == 'routed':
            if record.get('source_endpoint') != want['source_endpoint'] or \
                    record.get('target_endpoint') != want['target_endpoint']:
                errors.append(f'route {rid} endpoint mismatch')
    report = dict(schema='manual_c4_identity_validation_v1',
                  records=len(records), connections=len(expected),
                  errors=errors[:20], error_count=len(errors),
                  passed=(not errors))
    log(f'[audit2d] identity: records={len(records)} errors={len(errors)} '
        f'-> {"PASS" if report["passed"] else "FAIL"}')
    return report


def audit_no_duplicate_geometry(records, log=print):
    """Defensive check: no two routed records inside one plane share a chain.

    Identical XY chains on *different* planes are legitimate (row 1 / row 2 ports
    have the same routing XY and are 0.5 mm apart; cross-plane XY overlap is not
    a same-layer conflict), so the uniqueness key includes the plane.
    """
    import json as _json
    seen = {}
    errors = []
    for record in records:
        if record.get('status') != 'routed':
            continue
        key = (record.get('plane'),
               _json.dumps(record['primitives'], sort_keys=True))
        rid = int(record['route_id'])
        if key in seen:
            errors.append(f'route {rid} duplicates geometry of {seen[key]} '
                          f'in plane {record.get("plane")}')
        seen[key] = rid
    report = dict(schema='manual_c4_geometry_uniqueness_v1',
                  routed=len(seen), errors=errors[:20], error_count=len(errors),
                  passed=(not errors))
    log(f'[audit2d] geometry uniqueness (per plane): unique={len(seen)} '
        f'errors={len(errors)} -> {"PASS" if report["passed"] else "FAIL"}')
    return report
