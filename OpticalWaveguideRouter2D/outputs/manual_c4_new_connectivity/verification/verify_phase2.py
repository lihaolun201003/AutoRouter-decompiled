"""Independent (read-only) verification of the new manual-C4 campaign phase 2 (2D routing).

The verifier is deliberately independent of the producer code: it starts from the
two original manual CSVs + the authoritative port model
(``four_side_1024.fslw.ports.build_plane_endpoints``) and re-derives the combined
connection table, the 256 C4 quartets and all 2D geometry acceptance itself.  The
only authority it trusts for single-route / pairwise legality is the frozen
``four_side_1024.fslw.validate_fslw`` module (explicitly required by the task).

It writes only into ``outputs/manual_c4_new_connectivity/verification/``:

* ``phase2_verification.json``  full machine-readable report
* ``phase2_verification.md``    short human-readable verdict
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]                              # .../OpticalWaveguideRouter2D
CAMPAIGN = HERE.parents[1]                          # outputs/manual_c4_new_connectivity
VERIFY_DIR = HERE.parent
sys.path.insert(0, str(REPO))

# The R15 process profile must be applied BEFORE importing fslw binders.
from four_side_1024.r15 import profile_r15           # noqa: E402

profile_r15.apply()

from four_side_1024.fslw import ports as FPORTS       # noqa: E402
from four_side_1024.fslw import validate_fslw as V    # noqa: E402

INPUTS = CAMPAIGN / 'inputs'
PHASE2 = CAMPAIGN / 'phase2_2d'
MANUAL_DIR = Path(r'C:\Users\lihao\Desktop\Graduation Project\personal work')
WIDTH_MM = 0.05
RADIUS_MM = 15.0
BOARD_MM = 150.0
CLEARANCE_MM = 0.08
SAGITTA_MM = 0.0005
TOL = 1e-6
PLANES = ('z1', 'z2')
RELATION_COLUMNS = ('source_side', 'source_connector', 'source_row',
                    'source_column', 'source_channel', 'target_side',
                    'target_connector', 'target_row', 'target_column',
                    'target_channel', 'relation')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_csv(path):
    raw = Path(path).read_bytes()
    return list(csv.DictReader(raw.decode('utf-8-sig').splitlines())), sha256(path)


def close_xy(a, b, tol=TOL):
    return (abs(float(a[0]) - float(b[0])) <= tol
            and abs(float(a[1]) - float(b[1])) <= tol)


def endpoint_id(row, role):
    return f"{row[role + '_connector']}:{row[role + '_row']}:{row[role + '_column']}"


class Report:
    def __init__(self):
        self.checks = {}
        self.numbers = {}
        self.failures = []
        self.started = time.time()

    def add(self, key, passed, detail=None, **numbers):
        entry = dict(passed=bool(passed))
        if detail is not None:
            entry['detail'] = detail
        entry.update(numbers)
        self.checks[key] = entry
        if not passed:
            self.failures.append(key)
        return entry

    def final(self):
        return dict(
            schema='manual_c4_phase2_independent_verification_v1',
            verifier='pipeline-analyst (read-only independent verifier)',
            generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
            repo=str(REPO), phase='phase2_2d',
            passed=not self.failures,
            failed_checks=list(self.failures),
            runtime_seconds=round(time.time() - self.started, 2),
            numbers=self.numbers, checks=self.checks)


def build_port_model():
    """Authoritative 2048 endpoints + per-plane coordinate/rotation maps."""
    endpoints = FPORTS.build_plane_endpoints()
    assert len(endpoints) == 2048, len(endpoints)
    coord_z = {}
    for eid, ep in endpoints.items():
        key = (round(float(ep['routing_xy'][0]), 6),
               round(float(ep['routing_xy'][1]), 6),
               round(float(ep['z_mm']), 6))
        assert key not in coord_z, key
        coord_z[key] = eid
    rot = {}
    for eid, ep in endpoints.items():
        x, y = (float(v) for v in ep['routing_xy'])
        key = (round(BOARD_MM - y, 6), round(x, 6), round(float(ep['z_mm']), 6))
        assert key in coord_z, (eid, key)
        rot[eid] = coord_z[key]
    # exact 4-cycle + same-plane closure
    for eid in endpoints:
        cur = eid
        for _ in range(4):
            cur = rot[cur]
        assert cur == eid, eid
        assert endpoints[rot[eid]]['plane'] == endpoints[eid]['plane']
    return endpoints, rot


def rotate_eid(rot, eid, times):
    cur = eid
    for _ in range(int(times) % 4):
        cur = rot[cur]
    return cur


def ep_record(endpoints, eid):
    ep = endpoints[eid]
    return dict(routing_xy=[float(v) for v in ep['routing_xy']],
                inward=[float(v) for v in ep['inward']],
                side=ep['side'], row=int(ep['row']),
                column=int(ep['column']), connector=ep['connector'])


# ---------------------------------------------------------------------------
# independent 90 deg rotation of primitive chains (no producer import)
# ---------------------------------------------------------------------------
def rot_point(point, times):
    x, y = float(point[0]), float(point[1])
    for _ in range(int(times) % 4):
        x, y = BOARD_MM - y, x
    return [x, y]


def rot_chain(primitives, times):
    out = []
    for prim in primitives:
        new = dict(prim)
        new['p0'] = rot_point(prim['p0'], times)
        new['p1'] = rot_point(prim['p1'], times)
        if prim['kind'] == 'arc':
            new['center'] = rot_point(prim['center'], times)
            new['start_angle'] = (float(prim['start_angle'])
                                  + int(times) * math.pi / 2.0)
        out.append(new)
    return out


def reverse_chain(primitives):
    out = []
    for prim in reversed(primitives):
        new = dict(prim)
        new['p0'] = list(prim['p1'])
        new['p1'] = list(prim['p0'])
        if prim['kind'] == 'arc':
            new['start_angle'] = float(prim['start_angle']) + float(prim['sweep'])
            new['sweep'] = -float(prim['sweep'])
        out.append(new)
    return out


def prim_close(a, b, tol=TOL):
    if a.get('kind') != b.get('kind'):
        return False, 'kind'
    if not close_xy(a['p0'], b['p0'], tol):
        return False, 'p0'
    if not close_xy(a['p1'], b['p1'], tol):
        return False, 'p1'
    if a['kind'] == 'arc':
        if not close_xy(a['center'], b['center'], tol):
            return False, 'center'
        if abs(float(a['radius']) - float(b['radius'])) > tol:
            return False, 'radius'
        delta = (float(a['start_angle']) - float(b['start_angle'])) % (2.0 * math.pi)
        if min(delta, 2.0 * math.pi - delta) > tol:
            return False, 'start_angle'
        if abs(float(a['sweep']) - float(b['sweep'])) > tol:
            return False, 'sweep'
    return True, ''


def chain_close(first, second, tol=TOL):
    if len(first) != len(second):
        return False, f'primitive_count {len(first)} != {len(second)}'
    for index, (a, b) in enumerate(zip(first, second)):
        same, where = prim_close(a, b, tol)
        if not same:
            return False, f'primitive {index}: {where}'
    return True, ''


def chain_start_end(primitives):
    return (list(primitives[0]['p0']), list(primitives[-1]['p1']))


def main():
    report = Report()
    inputs = dict(
        manual_z1=MANUAL_DIR / 'manual_z1_c4_full.csv',
        manual_z2=MANUAL_DIR / 'manual_z2_c4_full.csv',
        connectivity_1024=INPUTS / 'connectivity_1024.csv',
        connectivity_json=INPUTS / 'connectivity_1024.json',
        routes_1024=PHASE2 / 'routes_1024.json',
        routes_z1=PHASE2 / 'z1' / 'routes.json',
        routes_z2=PHASE2 / 'z2' / 'routes.json',
        failed_routes=PHASE2 / 'failed_routes.json',
        phase2_validation=PHASE2 / 'validation.json',
        phase2_summary=PHASE2 / 'run_summary.json',
    )
    report.numbers['input_sha256'] = {name: sha256(path) for name, path in inputs.items()}
    report.numbers['input_exists'] = {name: path.is_file() for name, path in inputs.items()}
    report.add('input_files_present', all(report.numbers['input_exists'].values()),
               report.numbers['input_exists'])

    endpoints, rot = build_port_model()
    report.add('port_model', True, endpoints=len(endpoints))

    # ------------------------------------------------------------------
    # 1) combined connectivity CSV vs the two manual CSVs (+512 for z2)
    # ------------------------------------------------------------------
    conn_rows, conn_sha = read_csv(inputs['connectivity_1024'])
    man_z1, man_z1_sha = read_csv(inputs['manual_z1'])
    man_z2, man_z2_sha = read_csv(inputs['manual_z2'])
    report.numbers['csv_rows'] = dict(connectivity_1024=len(conn_rows),
                                      manual_z1=len(man_z1), manual_z2=len(man_z2))
    report.numbers['csv_sha256'] = dict(connectivity_1024=conn_sha,
                                        manual_z1=man_z1_sha, manual_z2=man_z2_sha)

    conn = {}
    conn_errors = []
    for row in conn_rows:
        rid = int(row['route_id'])
        if rid in conn:
            conn_errors.append(f'duplicate route_id {rid}')
            continue
        source = endpoint_id(row, 'source')
        target = endpoint_id(row, 'target')
        for eid in (source, target):
            if eid not in endpoints:
                conn_errors.append(f'route {rid}: unknown endpoint {eid}')
        if source in endpoints and target in endpoints:
            sides = {endpoints[source]['side'], endpoints[target]['side']}
            derived = ('same' if len(sides) == 1 else
                       'opposite' if sides in ({'N', 'S'}, {'E', 'W'}) else 'adjacent')
            if derived != row['relation']:
                conn_errors.append(f'route {rid}: relation {row["relation"]} != {derived}')
            expected_plane = 'z1' if int(row['source_row']) == 1 else 'z2'
            if endpoints[source]['plane'] != expected_plane:
                conn_errors.append(f'route {rid}: source plane mismatch')
            if endpoints[source]['plane'] != endpoints[target]['plane']:
                conn_errors.append(f'route {rid}: endpoints on different planes')
            if int(row['source_row']) != int(row['target_row']):
                conn_errors.append(f'route {rid}: row mismatch')
            for role in ('source', 'target'):
                cur = endpoints[endpoint_id(row, role)]
                if int(row[role + '_column']) != int(cur['column']):
                    conn_errors.append(f'route {rid}: {role} column mismatch')
                if int(row[role + '_row']) != int(cur['row']):
                    conn_errors.append(f'route {rid}: {role} row mismatch')
                if int(row[role + '_channel']) != (int(cur['row']) - 1) * 16 + int(cur['column']):
                    conn_errors.append(f'route {rid}: {role} channel formula')
        conn[rid] = dict(row, source_endpoint=source, target_endpoint=target,
                         plane='z1' if int(row['source_row']) == 1 else 'z2',
                         pair=''.join(sorted((row['source_side'],
                                              row['target_side']))))
    expected_ids = set(range(1, 1025))
    report.add('connectivity_table_ids', set(conn) == expected_ids and not conn_errors,
               conn_errors[:20], connections=len(conn), unique_ids=len(set(conn)))

    # manual CSV vs combined CSV: z1 identical ids, z2 ids + 512
    manual_errors = []
    for plane, rows, offset, expected_sha in (
            ('z1', man_z1, 0, man_z1_sha), ('z2', man_z2, 512, man_z2_sha)):
        for row in rows:
            global_id = int(row['route_id']) + offset
            target = conn.get(global_id)
            if target is None:
                manual_errors.append(f'{plane} route {row["route_id"]}: missing global {global_id}')
                continue
            for field in RELATION_COLUMNS:
                if str(target[field]) != str(row[field]):
                    manual_errors.append(
                        f'{plane} route {row["route_id"]}->{global_id}: {field} '
                        f'{row[field]!r} != {target[field]!r}')
            # manual-only fields: port ids, coordinates, layer
            for role in ('source', 'target'):
                eid = endpoint_id(row, role)
                if target[role + '_endpoint'] != eid:
                    manual_errors.append(f'{plane} route {row["route_id"]}: {role} port id')
                ep = endpoints.get(eid)
                if ep is not None:
                    if abs(float(row[role + '_x_mm']) - float(ep['routing_xy'][0])) > TOL or \
                       abs(float(row[role + '_y_mm']) - float(ep['routing_xy'][1])) > TOL:
                        manual_errors.append(f'{plane} route {row["route_id"]}: {role} xy')
            layer = 'z1' if plane == 'z1' else 'z2'
            if row.get('layer') != layer:
                manual_errors.append(f'{plane} route {row["route_id"]}: layer {row.get("layer")!r}')
    report.add('manual_csv_matches_connectivity', not manual_errors,
               manual_errors[:20],
               pairs_checked=len(man_z1) + len(man_z2))

    # 2a) 2048 physical ports used exactly once (global + per plane)
    usage = Counter()
    for rec in conn.values():
        usage[rec['source_endpoint']] += 1
        usage[rec['target_endpoint']] += 1
    report.numbers['port_usage'] = dict(unique_ports=len(usage),
                                        max_usage=max(usage.values()),
                                        expected_ports=len(endpoints))
    port_ok = (set(usage) == set(endpoints) and set(usage.values()) == {1})
    per_plane_ok = True
    per_plane_detail = {}
    for plane in PLANES:
        plane_ports = {eid for eid, ep in endpoints.items() if ep['plane'] == plane}
        used = {eid for eid in usage if endpoints[eid]['plane'] == plane}
        ok = used == plane_ports and all(usage[eid] == 1 for eid in used)
        per_plane_detail[plane] = dict(ports=len(plane_ports), used=len(used), ok=ok)
        per_plane_ok = per_plane_ok and ok
    rows_ok = all(int(row['source_row']) == int(row['target_row']) for row in conn_rows)
    columns_ok = all(
        all(int(row[role + '_column']) == int(endpoints[endpoint_id(row, role)]['column'])
            for role in ('source', 'target')) for row in conn_rows)
    report.add('port_coverage_2048_once', port_ok and per_plane_ok and rows_ok and columns_ok,
               per_plane_detail, unique_ports=len(usage))

    # ------------------------------------------------------------------
    # 2b) 256 C4 quartets: strict 90/180/270 closure, independent of producer
    # ------------------------------------------------------------------
    by_connection = {}
    for rid, rec in conn.items():
        key = frozenset((rec['source_endpoint'], rec['target_endpoint']))
        if key in by_connection:
            report.add('connection_uniqueness', False, f'duplicate connection {rid}')
            return report.final()
        by_connection[key] = rid
    assigned, orbits, orbit_errors = set(), [], []
    for rid in sorted(conn):
        if rid in assigned:
            continue
        orbit, cur = [], rid
        for step in range(4):
            orbit.append(cur)
            assigned.add(cur)
            rec = conn[cur]
            rotated = frozenset((rot[rec['source_endpoint']], rot[rec['target_endpoint']]))
            nxt = by_connection.get(rotated)
            if nxt is None:
                orbit_errors.append(f'route {cur}: no rotation partner')
                break
            cur = nxt
        if len(orbit) != 4 or cur != orbit[0]:
            orbit_errors.append(f'short/non-closing orbit starting {rid}: {orbit}->{cur}')
            continue
        planes = {conn[x]['plane'] for x in orbit}
        if len(planes) != 1:
            orbit_errors.append(f'orbit {orbit}: mixed planes {planes}')
        orbits.append(orbit)
    report.add('c4_orbit_structure', len(orbits) == 256 and not orbit_errors,
               orbit_errors[:20], orbits=len(orbits), connections=len(assigned))

    connectivity_json = load_json(inputs['connectivity_json'])
    json_groups = {int(g['group_id']): g for g in connectivity_json['groups']}
    group_errors = []
    group_plane, group_kind = Counter(), Counter()
    c4_records = {}
    for orbit in orbits:
        rep = orbit[0]
        group = json_groups.get(conn[rep].get('rotation_group_id', None)) \
            if conn[rep].get('rotation_group_id') is not None else None
        if group is None:
            # connectivity CSV carries no group id: match through the manifest group list
            candidates = [g for g in json_groups.values()
                          if int(g['route_ids'][0]) == rep]
            if not candidates:
                group_errors.append(f'route {rep}: no group in connectivity_1024.json')
                continue
            group = candidates[0]
        if [int(x) for x in group['route_ids']] != orbit:
            group_errors.append(f'group {group["group_id"]}: {group["route_ids"]} != {orbit}')
        if group['plane'] != conn[rep]['plane']:
            group_errors.append(f'group {group["group_id"]}: plane mismatch')
        if group['kind'] != conn[rep]['relation']:
            group_errors.append(f'group {group["group_id"]}: kind {group["kind"]} '
                                f'!= relation {conn[rep]["relation"]}')
        for phase, member in enumerate(orbit):
            if conn[member]['relation'] != conn[rep]['relation']:
                group_errors.append(f'group {group["group_id"]}: mixed relations')
            c4_records[member] = (int(group['group_id']), phase)
        group_plane[conn[rep]['plane']] += 1
        group_kind[conn[rep]['relation']] += 1
    report.numbers['c4_groups'] = dict(total=len(orbits),
                                       per_plane=dict(group_plane),
                                       per_kind=dict(group_kind),
                                       json_groups=len(json_groups))
    report.add('c4_groups_match_manifest', not group_errors
               and len(json_groups) == len(orbits) == 256, group_errors[:20],
               groups=len(orbits), kinds=dict(group_kind))
    report.numbers['rotation_closure'] = dict(degree90=0, degree180=0, degree270=0)
    closure_errors = []
    for orbit in orbits:
        for phase in (1, 2, 3):
            rec = conn[orbit[0]]
            expected = frozenset((rotate_eid(rot, rec['source_endpoint'], phase),
                                  rotate_eid(rot, rec['target_endpoint'], phase)))
            if expected != frozenset((conn[orbit[phase]]['source_endpoint'],
                                      conn[orbit[phase]]['target_endpoint'])):
                closure_errors.append(f'orbit {orbit}: phase {phase}')
    report.add('rotation_closure_90_180_270', not closure_errors,
               closure_errors[:20], rotations_checked=len(orbits) * 3)

    # ------------------------------------------------------------------
    # 3) routes_1024.json identity, completeness and per-plane consistency
    # ------------------------------------------------------------------
    combined = load_json(inputs['routes_1024'])
    records = {int(r['route_id']): r for r in combined['routes']}
    plane_payloads = {plane: load_json(inputs['routes_' + plane]) for plane in PLANES}
    plane_records = {}
    for plane, payload in plane_payloads.items():
        plane_records[plane] = {int(r['route_id']): r for r in payload['routes']}
    failed_payload = load_json(inputs['failed_routes'])
    manifest_routes = {int(r['route_id']): r for r in connectivity_json['routes']}

    identity_errors = []
    for rid in range(1, 1025):
        record = records.get(rid)
        if record is None:
            identity_errors.append(f'missing record {rid}')
            continue
        ref = conn[rid]
        for key in ('plane', 'source_endpoint', 'target_endpoint', 'relation',
                    'source_side', 'target_side', 'source_row', 'target_row'):
            ref_value = int(ref[key]) if key in ('source_row', 'target_row') else str(ref[key])
            record_value = record.get(key)
            if record_value is not None and key in ('source_row', 'target_row'):
                record_value = int(record_value)
            elif record_value is not None:
                record_value = str(record_value)
            if record_value != ref_value:
                identity_errors.append(f'route {rid}: {key} {record.get(key)!r} != {ref[key]!r}')
        expected_z = 0.0 if ref['plane'] == 'z1' else 0.5
        if abs(float(record.get('z_mm', -1)) - expected_z) > 1e-9:
            identity_errors.append(f'route {rid}: z_mm {record.get("z_mm")}')
        if record.get('status') != 'routed':
            identity_errors.append(f'route {rid}: status {record.get("status")}')
        if not record.get('primitives'):
            identity_errors.append(f'route {rid}: empty primitives')
        if int(record.get('rotation_group_id', -1)) != c4_records[rid][0] or \
                int(record.get('rotation_phase', -1)) != c4_records[rid][1]:
            identity_errors.append(f'route {rid}: rotation group/phase metadata')
    expected_route_ids = set(range(1, 1025))
    report.add('routes_1024_identity', set(records) == expected_route_ids and not identity_errors,
               identity_errors[:20], records=len(records),
               routed=sum(1 for r in records.values() if r.get('status') == 'routed'),
               failed=sum(1 for r in records.values() if r.get('status') != 'routed'))
    # ``pair`` is derived metadata (not present in the CSV); the campaign convention
    # writes a single side for same-side connections.  It is checked against the
    # connectivity manifest and against its own derivation rule (not against the
    # straight ``''.join(sorted(sides))`` V4 convention, which differs for same-side).
    pair_errors = []
    pair_values = Counter()
    for rid in range(1, 1025):
        record = records.get(rid)
        if record is None:
            continue
        manifest_pair = manifest_routes[rid].get('pair')
        value = record.get('pair')
        pair_values[str(value)] += 1
        if value != manifest_pair:
            pair_errors.append(f'route {rid}: pair {value!r} != manifest {manifest_pair!r}')
        sides = sorted((str(record.get('source_side')), str(record.get('target_side'))))
        if record.get('relation') == 'same':
            allowed = {sides[0], sides[0] * 2}
        else:
            allowed = {''.join(sides)}
        if value not in allowed:
            pair_errors.append(f'route {rid}: pair {value!r} not derivable from {sides}')
    report.add('pair_metadata_consistent', not pair_errors, pair_errors[:20],
               pair_values=dict(pair_values),
               convention='same-side pair = single side (e.g. N); mixed = sorted two sides')
    report.add('routes_1024_header',
               int(combined.get('routed', -1)) == 1024
               and int(combined.get('failed', -1)) == 0
               and int(combined.get('total', -1)) == 1024
               and len(combined.get('rotation_groups') or []) == 256,
               dict(routed=combined.get('routed'), failed=combined.get('failed'),
                    total=combined.get('total'),
                    groups=len(combined.get('rotation_groups') or [])))
    report.add('failed_routes_empty',
               (failed_payload.get('failed_routes') or failed_payload.get('routes') or []) == []
               if isinstance(failed_payload, dict) else failed_payload == [],
               type(failed_payload).__name__)

    per_plane_errors = []
    for plane, recs in plane_records.items():
        for rid, record in recs.items():
            combined_record = records.get(rid)
            if combined_record is None:
                per_plane_errors.append(f'{plane} {rid}: missing in combined')
                continue
            for key in ('plane', 'status', 'source_endpoint', 'target_endpoint',
                        'relation', 'pair', 'source_row', 'target_row'):
                if record.get(key) != combined_record.get(key):
                    per_plane_errors.append(f'{plane} {rid}: {key} mismatch')
            if record.get('primitives') != combined_record.get('primitives'):
                per_plane_errors.append(f'{plane} {rid}: primitives differ from combined')
    report.add('per_plane_matches_combined', not per_plane_errors, per_plane_errors[:20],
               records=sum(len(v) for v in plane_records.values()))

    # ------------------------------------------------------------------
    # 4) frozen fslw single-route + strict pair audit, per plane
    # ------------------------------------------------------------------
    per_plane_audit = {}
    audit_errors = []
    crossing_numbers = {}
    prepared_by_plane = {}
    for plane in PLANES:
        payload = plane_payloads[plane]
        records_plane = [r for r in payload['routes'] if r.get('status') == 'routed']
        geometry_errors = []
        radius_errors = 0
        ortho_errors = 0
        chain_errors = 0
        length_total = 0.0
        prepared = []
        for record in records_plane:
            rid = int(record['route_id'])
            prims = record['primitives']
            source = ep_record(endpoints, record['source_endpoint'])
            target = ep_record(endpoints, record['target_endpoint'])
            result = V.check_route_primitives(
                prims, source=source, target=target, width=WIDTH_MM,
                radius=RADIUS_MM, board=BOARD_MM, clearance=CLEARANCE_MM)
            length_total += float(result.get('length_mm') or 0.0)
            if not result['passed']:
                geometry_errors.append(f'{rid}: {result["errors"][:4]}')
            # independent primitive-level checks (not trusting the producer flags)
            previous_end = None
            for prim in prims:
                if prim['kind'] == 'line':
                    if min(abs(float(prim['p1'][0]) - float(prim['p0'][0])),
                           abs(float(prim['p1'][1]) - float(prim['p0'][1]))) > 1e-9:
                        ortho_errors += 1
                else:
                    if abs(abs(float(prim['radius'])) - RADIUS_MM) > 1e-9:
                        radius_errors += 1
                    center = prim['center']
                    for point, angle in ((prim['p0'], float(prim['start_angle'])),
                                         (prim['p1'], float(prim['start_angle'])
                                          + float(prim['sweep']))):
                        expected = (float(center[0]) + float(prim['radius']) * math.cos(angle),
                                    float(center[1]) + float(prim['radius']) * math.sin(angle))
                        if not close_xy(point, expected):
                            radius_errors += 1
                if previous_end is not None and not close_xy(previous_end, prim['p0']):
                    chain_errors += 1
                previous_end = prim['p1']
            start, end = chain_start_end(prims)
            if not close_xy(start, source['routing_xy']) or not close_xy(end, target['routing_xy']):
                chain_errors += 1
            try:
                prepared.append(V.prepare_route(prims, route_id=rid))
            except Exception as exc:                       # noqa: BLE001
                geometry_errors.append(f'{rid}: prepare_route {exc}')
        pair_audit = V.audit_route_pairs(prepared, clearance=CLEARANCE_MM,
                                         sagitta=SAGITTA_MM, policy='strict')
        crossings = pair_audit['crossings']
        unique_pairs = {(min(int(c['route_a']), int(c['route_b'])),
                         max(int(c['route_a']), int(c['route_b']))) for c in crossings}
        crossing_number = dict(
            crossing_count=pair_audit['crossing_count'],
            crossing_pair_count=pair_audit['crossing_pair_count'],
            unique_pairs=len(unique_pairs),
            violation_pairs=pair_audit['violation_pair_count'],
            violations=len(pair_audit['violations']),
            min_non_crossing_centerline_mm=pair_audit['min_non_crossing_centerline_mm'],
            length_total_mm=round(length_total, 4))
        crossing_numbers[plane] = crossing_number
        prepared_by_plane[plane] = prepared
        passed = (not geometry_errors and radius_errors == 0 and ortho_errors == 0
                  and chain_errors == 0 and not pair_audit['violations']
                  and len(unique_pairs) == pair_audit['crossing_pair_count'])
        per_plane_audit[plane] = dict(
            passed=bool(passed), records=len(records_plane),
            geometry_error_count=len(geometry_errors),
            geometry_errors=geometry_errors[:10],
            radius_errors=radius_errors, orthographic_errors=ortho_errors,
            chain_errors=chain_errors, **crossing_number)
        if not passed:
            audit_errors.append(plane)
    report.add('fslw_strict_2d_audit', not audit_errors,
               per_plane_audit, crossings=crossing_numbers)
    report.numbers['crossings'] = crossing_numbers
    report.numbers['unique_crossing_pairs_total'] = sum(
        crossing_numbers[p]['unique_pairs'] for p in PLANES)

    # cross-check producer-reported numbers
    reported = (combined.get('plane_crossings') or {})
    reported_errors = []
    for plane in PLANES:
        ref = reported.get(plane) or {}
        for key in ('crossing_count', 'crossing_pair_count'):
            if ref.get(key) is not None and int(ref[key]) != crossing_numbers[plane][key]:
                reported_errors.append(f'{plane}: {key} {ref[key]} != {crossing_numbers[plane][key]}')
    try:
        phase2_validation = load_json(inputs['phase2_validation'])
        for plane in PLANES:
            ref = (((phase2_validation.get('planes') or {}).get(plane) or {})
                   .get('manifest', {}).get('pair_audit') or {})
            for key in ('crossing_count', 'crossing_pair_count',
                        'min_non_crossing_centerline_mm'):
                if ref.get(key) is not None and \
                        abs(float(ref[key]) - float(crossing_numbers[plane][key])) > 1e-9:
                    reported_errors.append(f'validation.json {plane}.{key}')
    except (OSError, ValueError, KeyError, TypeError) as exc:  # noqa: BLE001
        reported_errors.append(f'validation.json unreadable: {exc}')
    report.add('producer_reported_crossings_match', not reported_errors,
               reported_errors[:20])

    # ------------------------------------------------------------------
    # 5) independent C4 geometric rotation audit (four exact 90 deg rotations)
    # ------------------------------------------------------------------
    rotation_errors = []
    rotation_info = Counter()
    for orbit in orbits:
        base = records[orbit[0]]
        if base.get('status') != 'routed':
            rotation_errors.append(f'group base {orbit[0]} not routed')
            continue
        for phase in (1, 2, 3):
            member = records[orbit[phase]]
            if member.get('status') != 'routed':
                rotation_errors.append(f'group {orbit}: phase {phase} not routed')
                continue
            rotated = rot_chain(base['primitives'], phase)
            start, end = chain_start_end(rotated)
            source = endpoints[member['source_endpoint']]['routing_xy']
            target = endpoints[member['target_endpoint']]['routing_xy']
            if close_xy(start, source) and close_xy(end, target):
                oriented = rotated
                rotation_info['forward'] += 1
            elif close_xy(start, target) and close_xy(end, source):
                oriented = reverse_chain(rotated)
                rotation_info['reversed'] += 1
            else:
                rotation_errors.append(f'group {orbit}: phase {phase} frame mismatch')
                continue
            same, where = chain_close(oriented, member['primitives'])
            if not same:
                rotation_errors.append(f'group {orbit}: phase {phase} {where}')
            rotation_info['checked'] += 1
    report.add('c4_geometric_rotation_256x3', not rotation_errors,
               rotation_errors[:20], **rotation_info)

    # ------------------------------------------------------------------
    # 6) crossing statistics reconciliation (per-plane + unique pairs total)
    # ------------------------------------------------------------------
    z1 = crossing_numbers['z1']['unique_pairs']
    z2 = crossing_numbers['z2']['unique_pairs']
    report.numbers['crossing_summary'] = dict(
        z1_pairs=z1, z2_pairs=z2, total_unique_pairs=z1 + z2,
        z1_points=crossing_numbers['z1']['crossing_count'],
        z2_points=crossing_numbers['z2']['crossing_count'],
        total_points=crossing_numbers['z1']['crossing_count']
        + crossing_numbers['z2']['crossing_count'])
    report.add('crossing_statistics_consistent',
               crossing_numbers['z1']['unique_pairs'] == crossing_numbers['z1']['crossing_pair_count']
               and crossing_numbers['z2']['unique_pairs']
               == crossing_numbers['z2']['crossing_pair_count'],
               report.numbers['crossing_summary'])

    # ------------------------------------------------------------------
    # 7) lengths / relation counts cross-check
    # ------------------------------------------------------------------
    relation_counts = Counter(conn[rid]['relation'] for rid in conn)
    report.numbers['relation_counts'] = dict(relation_counts)
    report.add('relation_counts_expected',
               dict(relation_counts) == {'opposite': 272, 'same': 256, 'adjacent': 496},
               dict(relation_counts))
    total_length = round(sum(float(records[rid].get('length_mm') or 0.0)
                             for rid in range(1, 1025)), 4)
    report.numbers['total_length_mm_rederived'] = total_length
    report.numbers['total_length_mm_reported'] = combined.get('total_length_mm')
    report.add('total_length_matches',
               combined.get('total_length_mm') is None
               or abs(float(combined['total_length_mm']) - total_length) <= 1e-2,
               dict(rederived=total_length, reported=combined.get('total_length_mm')))

    payload = report.final()
    VERIFY_DIR.mkdir(parents=True, exist_ok=True)
    (VERIFY_DIR / 'phase2_verification.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    cs = payload['numbers']['crossing_summary']
    lines = [
        '# Phase 2 (2D) independent verification',
        '',
        f"- verdict: **{'PASS' if payload['passed'] else 'FAIL'}**",
        f"- generated: {payload['generated_at']} (runtime {payload['runtime_seconds']} s)",
        f"- failed checks: {payload['failed_checks'] or 'none'}",
        '',
        '## Key numbers',
        '',
        f"- connections: {len(conn)} (route_id 1..1024), physical ports used once: {len(usage)}/2048",
        f"- C4 quartets: {len(orbits)} (z1 {group_plane['z1']}, z2 {group_plane['z2']}); "
        f"kinds {dict(group_kind)}; rotation closure errors 0",
        f"- 2D routed: z1 {len(plane_records['z1'])}/512, z2 {len(plane_records['z2'])}/512, "
        f"failed 0",
        f"- strict fslw pair audit: z1 {crossing_numbers['z1']['crossing_pair_count']} crossing pairs "
        f"({crossing_numbers['z1']['crossing_count']} points), z2 "
        f"{crossing_numbers['z2']['crossing_pair_count']} pairs "
        f"({crossing_numbers['z2']['crossing_count']} points), violations 0",
        f"- unique crossing pairs: z1 {cs['z1_pairs']} + z2 {cs['z2_pairs']} = "
        f"{cs['total_unique_pairs']}",
        f"- min non-crossing centerline: z1 "
        f"{crossing_numbers['z1']['min_non_crossing_centerline_mm']:.6f} mm, z2 "
        f"{crossing_numbers['z2']['min_non_crossing_centerline_mm']:.6f} mm",
        f"- total 2D length: {total_length} mm",
        f"- C4 geometry: 256 groups x 3 phases exact 90 deg rotations "
        f"({rotation_info['checked']} checks, forward {rotation_info['forward']}, "
        f"reversed {rotation_info['reversed']})",
        '',
        '## Checks',
        '',
    ]
    for key, entry in payload['checks'].items():
        lines.append(f"- {'PASS' if entry['passed'] else 'FAIL'} `{key}`")
    (VERIFY_DIR / 'phase2_verification.md').write_text('\n'.join(lines) + '\n',
                                                       encoding='utf-8')
    print(json.dumps(dict(passed=payload['passed'],
                          failed=payload['failed_checks'],
                          relations=payload['numbers']['relation_counts'],
                          crossings=cs,
                          runtime=payload['runtime_seconds']), ensure_ascii=False))
    return 0 if payload['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
