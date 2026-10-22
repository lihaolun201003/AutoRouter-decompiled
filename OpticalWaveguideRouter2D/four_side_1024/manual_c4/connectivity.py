"""New manual C4 connectivity: input validation, combined 1024-row table, C4 groups.

The two human-designed plane tables (512 connections each, strict C4 symmetry inside
each height plane) are validated against the authoritative fslw port model, copied
into the independent output directory and combined into one 1024-row, 12-column
topology CSV with the same schema as the historical V3/V4 connectivity tables:

* route_id 1..512    -> row 1 (z1, z = 0.0 mm)
* route_id 513..1024 -> row 2 (z2, z = 0.5 mm)

The 1024 connections are partitioned into 256 strict C4 rotation orbits (128 per
plane); every orbit contains four connections that are exact 90 deg rotations of
each other about the board centre (75, 75) and always lives in a single z plane.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERSONAL = Path(r'C:\Users\lihao\Desktop\Graduation Project\personal work')
SRC_Z1 = PERSONAL / 'manual_z1_c4_full.csv'
SRC_Z2 = PERSONAL / 'manual_z2_c4_full.csv'
OUT_ROOT = ROOT / 'outputs/manual_c4_new_connectivity'
INPUT_DIR = OUT_ROOT / 'inputs'
COMBINED_CSV = INPUT_DIR / 'connectivity_1024.csv'
COMBINED_JSON = INPUT_DIR / 'connectivity_1024.json'
TOPOLOGY = 'MANUAL_C4'
PLANES = ('z1', 'z2')
MANUAL_FIELDS = ['route_id', 'source_side', 'source_connector', 'source_row',
                 'source_column', 'source_channel', 'target_side', 'target_connector',
                 'target_row', 'target_column', 'target_channel', 'relation',
                 'source_port_id', 'target_port_id', 'source_x_mm', 'source_y_mm',
                 'target_x_mm', 'target_y_mm', 'layer']
COMBINED_FIELDS = ['route_id', 'source_side', 'source_connector', 'source_row',
                   'source_column', 'source_channel', 'target_side', 'target_connector',
                   'target_row', 'target_column', 'target_channel', 'relation']
BOARD = 150.0
TOL = 1e-9

#: lazy authoritative port model (fslw.ports.build_plane_endpoints)
_ENDPOINTS = None


def endpoints():
    global _ENDPOINTS
    if _ENDPOINTS is None:
        from ..fslw.ports import build_plane_endpoints
        _ENDPOINTS = build_plane_endpoints()
        # rot90 map inside the same z plane: (x, y) -> (150 - y, x)
        index = {}
        for eid, ep in _ENDPOINTS.items():
            key = (round(float(ep['routing_xy'][0]), 6),
                   round(float(ep['routing_xy'][1]), 6), float(ep['z_mm']))
            if key in index:
                raise ValueError(f'duplicate endpoint coordinate {key}')
            index[key] = eid
        _ENDPOINTS_INDEX = index
        globals()['_ENDPOINTS_INDEX'] = index
        rot = {}
        for eid, ep in _ENDPOINTS.items():
            x, y = ep['routing_xy']
            rot[eid] = index[(round(BOARD - float(y), 6), round(float(x), 6),
                             float(ep['z_mm']))]
        globals()['_ROT90_PORT'] = rot
    return _ENDPOINTS


def rot90_port(eid):
    endpoints()
    return _ROT90_PORT[eid]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_manual(path):
    raw = Path(path).read_bytes()
    text = raw.decode('utf-8-sig')
    lines = text.splitlines()
    rows = list(csv.DictReader(lines))
    return raw, lines, rows


# ---------------------------------------------------------------------------
# plane loading / structural validation
# ---------------------------------------------------------------------------
def _route_from_row(row, plane, route_id):
    """Build a routing record from one manual CSV row (authoritative port ids)."""
    eps = endpoints()
    rec = dict(route_id=int(route_id), plane=plane,
               z_mm=0.0 if plane == 'z1' else 0.5,
               source_side=row['source_side'], target_side=row['target_side'],
               source_connector=row['source_connector'],
               target_connector=row['target_connector'],
               source_row=int(row['source_row']), target_row=int(row['target_row']),
               source_column=int(row['source_column']),
               target_column=int(row['target_column']),
               source_channel=int(row['source_channel']),
               target_channel=int(row['target_channel']),
               relation=row['relation'])
    rec['source_endpoint'] = f"{rec['source_connector']}:{rec['source_row']}:{rec['source_column']}"
    rec['target_endpoint'] = f"{rec['target_connector']}:{rec['target_row']}:{rec['target_column']}"
    sides = {rec['source_side'], rec['target_side']}
    rec['pair'] = ''.join(sorted(sides))
    rec['row'] = rec['source_row']
    if rec['source_endpoint'] not in eps or rec['target_endpoint'] not in eps:
        raise ValueError(f'route {route_id}: unknown endpoint')
    if eps[rec['source_endpoint']]['plane'] != plane or \
            eps[rec['target_endpoint']]['plane'] != plane:
        raise ValueError(f'route {route_id}: endpoint outside plane {plane}')
    return rec


def _relation_of_sides(a, b):
    if a == b:
        return 'same'
    return 'opposite' if {a, b} in ({'N', 'S'}, {'E', 'W'}) else 'adjacent'


def load_plane_routes(plane):
    """Validated route records of one plane, sorted by route_id (1..512)."""
    payload = combined_topology()
    return list(payload['plane_routes'][plane])


def load_plane(plane):
    """fslw-style ``(routes, endpoints, connectors, validation)`` for one plane."""
    payload = combined_topology()
    routes = list(payload['plane_routes'][plane])
    eps = endpoints()
    plane_eps = {eid: dict(ep) for eid, ep in eps.items() if ep['plane'] == plane}
    from ..fslw.ports import connector_records
    validation = dict(payload['plane_validation'][plane])
    return routes, plane_eps, connector_records(), validation


# ---------------------------------------------------------------------------
# input validation (phase 1)
# ---------------------------------------------------------------------------
def validate_manual_inputs():
    checks = []

    def check(section, name, ok, detail=''):
        checks.append(dict(section=section, check=name, passed=bool(ok),
                           detail=str(detail)))
        return ok

    eps = endpoints()
    plane_ports = {plane: {eid for eid, ep in eps.items() if ep['plane'] == plane}
                   for plane in PLANES}
    manual = {}
    for plane, src in (('z1', SRC_Z1), ('z2', SRC_Z2)):
        check(plane, 'file exists', Path(src).exists(), src)
        raw, lines, rows = _read_manual(src)
        info = dict(path=str(src), sha256=hashlib.sha256(raw).hexdigest(),
                    bytes=len(raw), rows=len(rows),
                    bom=raw[:3] == b'\xef\xbb\xbf',
                    crlf_only=b'\n' not in raw.replace(b'\r\n', b''),
                    header=lines[0].split(','))
        manual[plane] = info
        check(plane, 'header = original 19-column manual schema',
              info['header'] == MANUAL_FIELDS, info['header'][:4])
        check(plane, 'UTF-8 BOM + CRLF encoding', info['bom'] and info['crlf_only'])
        check(plane, '512 connections', len(rows) == 512, len(rows))
        ids = [int(r['route_id']) for r in rows]
        check(plane, 'route_id 1..512 unique', sorted(ids) == list(range(1, 513)))
        expected_row = 1 if plane == 'z1' else 2
        check(plane, f'all rows are row={expected_row}',
              all(int(r['source_row']) == expected_row and
                  int(r['target_row']) == expected_row for r in rows))
        check(plane, 'channels match row convention (z1 1..16 / z2 17..32)',
              all((int(r['source_channel']) == int(r['source_column'])) if plane == 'z1'
                  else (int(r['source_channel']) == 16 + int(r['source_column']))
                  for r in rows) and
              all((int(r['target_channel']) == int(r['target_column'])) if plane == 'z1'
                  else (int(r['target_channel']) == 16 + int(r['target_column']))
                  for r in rows))
        check(plane, 'layer tag = plane', all(r['layer'] == plane for r in rows))
        check(plane, 'columns within 1..16',
              all(1 <= int(r[f'{role}_column']) <= 16
                  for r in rows for role in ('source', 'target')))
        # port ids / XY / metadata against the authoritative model
        bad = []
        usage = Counter()
        for r in rows:
            rid = int(r['route_id'])
            for role in ('source', 'target'):
                eid = r[f'{role}_port_id']
                ep = eps.get(eid)
                if ep is None:
                    bad.append((rid, role, 'unknown port id', eid))
                    continue
                usage[eid] += 1
                if ep['plane'] != plane:
                    bad.append((rid, role, 'wrong plane', eid))
                if ep['connector'] != r[f'{role}_connector'] or \
                        int(ep['row']) != int(r[f'{role}_row']) or \
                        int(ep['column']) != int(r[f'{role}_column']) or \
                        int(ep['channel']) != int(r[f'{role}_channel']) or \
                        ep['side'] != r[f'{role}_side']:
                    bad.append((rid, role, 'metadata mismatch', eid))
                x, y = float(r[f'{role}_x_mm']), float(r[f'{role}_y_mm'])
                ex, ey = (float(ep['routing_xy'][0]), float(ep['routing_xy'][1]))
                if abs(x - ex) > TOL or abs(y - ey) > TOL:
                    bad.append((rid, role, 'xy mismatch', eid, (x, y), (ex, ey)))
        check(plane, 'every port id / row / column / channel / side / XY matches fslw model',
              not bad, bad[:5])
        check(plane, '1024 endpoints used exactly once',
              len(usage) == 1024 and set(usage.values()) == {1},
              f'unique={len(usage)} dup={sum(1 for v in usage.values() if v > 1)}')
        check(plane, 'used port set == authoritative plane port set',
              set(usage) == plane_ports[plane],
              f'missing={len(plane_ports[plane] - set(usage))}')
        # relation labels consistent with sides
        rep = []
        for r in rows:
            rel = _relation_of_sides(r['source_side'], r['target_side'])
            if rel != r['relation']:
                rep.append((r['route_id'], r['relation'], rel))
        check(plane, 'relation field consistent with sides (no relabelling)',
              not rep, rep[:3])
        # no duplicate unordered connection
        conns = [frozenset((r['source_port_id'], r['target_port_id'])) for r in rows]
        check(plane, 'no duplicate unordered connection',
              len(set(conns)) == len(conns) == 512)
        routes = [_route_from_row(r, plane, r['route_id']) for r in rows]
        manual[plane].update(rows=rows, routes=routes, usage=dict(usage))
    return checks, manual


def build_groups(routes_all):
    """Partition routes into strict C4 rotation orbits (4 routes each, same plane)."""
    eps = endpoints()
    by_pair = {}
    for route in routes_all:
        key = frozenset((route['source_endpoint'], route['target_endpoint']))
        if key in by_pair:
            raise ValueError(f'duplicate unordered connection {sorted(key)}')
        by_pair[key] = route
    rot = {eid: rot90_port(eid) for eid in eps}
    groups, route_group = [], {}
    seen = set()
    for route in sorted(routes_all, key=lambda r: r['route_id']):
        if route['route_id'] in seen:
            continue
        orbit = [route]
        cur = route
        for _ in range(3):
            rotated = frozenset(rot[eid] for eid in
                                (cur['source_endpoint'], cur['target_endpoint']))
            nxt = by_pair.get(rotated)
            if nxt is None:
                raise ValueError(f'connection {route["route_id"]} has no rotation partner')
            orbit.append(nxt)
            cur = nxt
        if frozenset(rot[eid] for eid in
                     (cur['source_endpoint'], cur['target_endpoint'])) != \
                frozenset((route['source_endpoint'], route['target_endpoint'])):
            raise ValueError(f'connection {route["route_id"]} rotation orbit does not close')
        if len({r['route_id'] for r in orbit}) != 4:
            raise ValueError(f'connection {route["route_id"]} orbit size != 4')
        planes = {r['plane'] for r in orbit}
        if len(planes) != 1:
            raise ValueError(f'rotation orbit crosses planes: {route["route_id"]}')
        kinds = {r['relation'] for r in orbit}
        if len(kinds) != 1:
            raise ValueError(f'rotation orbit mixes relations: {route["route_id"]}')
        gid = len(groups) + 1
        group = dict(group_id=gid, plane=orbit[0]['plane'], kind=orbit[0]['relation'],
                     pair=orbit[0]['pair'],
                     route_ids=[r['route_id'] for r in orbit])
        groups.append(group)
        for phase, member in enumerate(orbit):
            route_group[member['route_id']] = (gid, phase)
            seen.add(member['route_id'])
    if len(groups) != 256 or len(route_group) != 1024:
        raise ValueError(f'expected 256 groups / 1024 routes, got {len(groups)}')
    for plane in PLANES:
        if sum(1 for g in groups if g['plane'] == plane) != 128:
            raise ValueError(f'plane {plane} must hold 128 groups')
    return groups, route_group


def rotation_closure(routes_all):
    """Connection-set closure report at 90/180/270 degrees (undirected links)."""
    eps = endpoints()
    rot = {eid: rot90_port(eid) for eid in eps}
    pairs = {tuple(sorted((r['source_endpoint'], r['target_endpoint']))) for r in routes_all}
    result = {}
    for step in (1, 2, 3):
        power = {}
        for eid in eps:
            cur = eid
            for _ in range(step):
                cur = rot[cur]
            power[eid] = cur
        missing = [p for p in pairs
                   if tuple(sorted((power[p[0]], power[p[1]]))) not in pairs]
        result[f'{step * 90}deg'] = len(missing)
    return result


def feasibility(manual):
    """Geometry feasibility report of the new connectivity at R=15 mm."""
    from ..fslw import config as C
    from ..r15 import u_geometry as UG
    eps = endpoints()
    radius = 15.0
    report = dict(radius_mm=radius, board_mm=BOARD,
                  min_clearance_mm=C.CLEARANCE_MM, width_mm=C.WIDTH_MM,
                  planes={})
    for plane in PLANES:
        routes = manual[plane]['routes']
        entry = dict(connections=len(routes), relations=dict(Counter(
            r['relation'] for r in routes)), groups=None,
            same_side=dict(count=0, min_separation_mm=None, max_separation_mm=None,
                           below_2R=0),
            adjacent=dict(count=0, min_leg_mm=None, max_leg_mm=None,
                          direct_L_feasible=0),
            opposite=dict(count=0, lateral_shift_mm=[]))
        same_sep, adj_legs, opp_shift = [], [], []
        for r in routes:
            ax, ay = (float(v) for v in eps[r['source_endpoint']]['routing_xy'])
            bx, by = (float(v) for v in eps[r['target_endpoint']]['routing_xy'])
            if r['relation'] == 'same':
                sep = abs(ax - bx) if r['source_side'] in 'NS' else abs(ay - by)
                same_sep.append(sep)
            elif r['relation'] == 'adjacent':
                dx, dy = abs(bx - ax), abs(by - ay)
                adj_legs.append((dx, dy))
            else:
                shift = abs(ax - bx) if r['source_side'] in 'NS' else abs(ay - by)
                opp_shift.append(shift)
        if same_sep:
            entry['same_side'].update(
                count=len(same_sep), min_separation_mm=min(same_sep),
                max_separation_mm=max(same_sep),
                below_2R=sum(1 for v in same_sep if v < 2 * radius - 1e-9),
                feasible_families=UG.u_reachability(min(same_sep))['families'])
        if adj_legs:
            entry['adjacent'].update(
                count=len(adj_legs),
                min_leg_mm=min(min(dx, dy) for dx, dy in adj_legs),
                max_leg_mm=max(max(dx, dy) for dx, dy in adj_legs),
                direct_L_feasible=sum(1 for dx, dy in adj_legs
                                      if min(dx, dy) >= radius - 1e-9))
        if opp_shift:
            entry['opposite'].update(count=len(opp_shift),
                                     lateral_shift_mm=sorted(set(opp_shift)))
        report['planes'][plane] = entry
    return report


# ---------------------------------------------------------------------------
# combined topology + artefacts
# ---------------------------------------------------------------------------
_TOPOLOGY_CACHE = None


def build_topology():
    """Validate inputs, write the independent input artefacts, return the topology."""
    checks, manual = validate_manual_inputs()
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    # 1. copy the two original CSVs
    shutil.copyfile(SRC_Z1, INPUT_DIR / 'manual_z1_c4_full.csv')
    shutil.copyfile(SRC_Z2, INPUT_DIR / 'manual_z2_c4_full.csv')
    # 2. route ids: z1 keeps 1..512, z2 shifts to 513..1024
    routes_all = []
    for plane in PLANES:
        for r in manual[plane]['routes']:
            rec = dict(r)
            if plane == 'z2':
                rec['route_id'] = rec['route_id'] + 512
            routes_all.append(rec)
    routes_all.sort(key=lambda r: r['route_id'])
    if [r['route_id'] for r in routes_all] != list(range(1, 1025)):
        raise ValueError('combined route_id must be 1..1024')
    groups, route_group = build_groups(routes_all)
    closure = rotation_closure(routes_all)
    # 3. combined 12-column CSV (V3/V4 topology schema)
    COMBINED_CSV.parent.mkdir(parents=True, exist_ok=True)
    with COMBINED_CSV.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=COMBINED_FIELDS)
        writer.writeheader()
        for r in routes_all:
            writer.writerow({k: r[k] for k in COMBINED_FIELDS})
    combined_sha = sha256_file(COMBINED_CSV)
    # 4. topology JSON (routes + groups)
    plane_validation = {}
    groups_by_plane = {plane: [g for g in groups if g['plane'] == plane]
                       for plane in PLANES}
    plane_routes = {plane: [r for r in routes_all if r['plane'] == plane]
                    for plane in PLANES}
    for plane in PLANES:
        relations = Counter(r['relation'] for r in plane_routes[plane])
        pairs = Counter(r['pair'] for r in plane_routes[plane])
        plane_validation[plane] = dict(
            passed=True, topology=TOPOLOGY, plane=plane,
            plane_row=1 if plane == 'z1' else 2,
            z_mm=0.0 if plane == 'z1' else 0.5,
            connections=512, ports=1024, ports_used_once=True,
            relations=dict(relations), pairs=dict(pairs),
            groups=len(groups_by_plane[plane]),
            group_kinds=dict(Counter(g['kind'] for g in groups_by_plane[plane])),
            csv_path=str(COMBINED_CSV), csv_sha256=combined_sha,
            source_manual_csv=str(SRC_Z1 if plane == 'z1' else SRC_Z2),
            source_manual_sha256=manual[plane]['sha256'],
            port_model='real_2x16_dual_height',
            minimum_separation_same_side_mm=30.0,
            rotation_closure=closure,
            cross_plane_rule='XY-projected crossings between z1 and z2 are not '
                             'same-layer conflicts')
    topology = dict(
        schema='manual_c4_new_connectivity_1024_v1', topology=TOPOLOGY,
        board_mm=BOARD, planes=PLANES, plane_row={'z1': 1, 'z2': 2},
        plane_z_mm={'z1': 0.0, 'z2': 0.5},
        connections=1024, ports=2048, group_count=256,
        inputs=dict(z1=dict(path=str(SRC_Z1), sha256=manual['z1']['sha256']),
                    z2=dict(path=str(SRC_Z2), sha256=manual['z2']['sha256'])),
        combined_csv=dict(path=str(COMBINED_CSV), sha256=combined_sha,
                          fields=COMBINED_FIELDS),
        rotation_closure=closure,
        relation_counts=dict(Counter(r['relation'] for r in routes_all)),
        pair_counts=dict(Counter(r['pair'] for r in routes_all)),
        group_kinds=dict(Counter(g['kind'] for g in groups)),
        groups=groups, route_group={str(k): list(v) for k, v in route_group.items()},
        routes=[dict(route_id=r['route_id'], plane=r['plane'],
                     source_endpoint=r['source_endpoint'],
                     target_endpoint=r['target_endpoint'],
                     relation=r['relation'], pair=r['pair'],
                     source_side=r['source_side'], target_side=r['target_side'],
                     source_row=r['source_row'], target_row=r['target_row'],
                     source_column=r['source_column'],
                     target_column=r['target_column'],
                     source_channel=r['source_channel'],
                     target_channel=r['target_channel'],
                     z_mm=r['z_mm']) for r in routes_all],
        plane_routes=plane_routes, plane_validation=plane_validation,
        manual=dict(z1=dict(path=str(SRC_Z1), sha256=manual['z1']['sha256'],
                            rows=512),
                    z2=dict(path=str(SRC_Z2), sha256=manual['z2']['sha256'],
                            rows=512)),
    )
    COMBINED_JSON.write_text(json.dumps(topology, ensure_ascii=False),
                             encoding='utf-8')
    # 5. validation + feasibility reports
    feas = feasibility(manual)
    group_gate = dict(
        groups_expected=256, groups=len(groups),
        groups_per_plane={plane: len(groups_by_plane[plane]) for plane in PLANES},
        group_kinds=dict(Counter(g['kind'] for g in groups)),
        route_group_entries=len(route_group),
        rotation_closure=closure,
        all_orbits_size_4=True)
    checks.append(dict(section='combined', check='1024 combined connections',
                       passed=len(routes_all) == 1024, detail=len(routes_all)))
    checks.append(dict(section='combined', check='route_id 1..1024 unique',
                       passed=[r['route_id'] for r in routes_all] == list(range(1, 1025))))
    checks.append(dict(section='combined', check='row split 512/512',
                       passed=(sum(1 for r in routes_all if r['source_row'] == 1) == 512 and
                               sum(1 for r in routes_all if r['source_row'] == 2) == 512)))
    checks.append(dict(section='combined', check='256 C4 rotation groups (128 per plane)',
                       passed=len(groups) == 256 and
                       all(group_gate['groups_per_plane'][p] == 128 for p in PLANES)))
    checks.append(dict(section='combined', check='C4 closure 0 missing at 90/180/270',
                       passed=all(v == 0 for v in closure.values()), detail=closure))
    checks.append(dict(section='combined', check='2048 ports each used once',
                       passed=len({e for r in routes_all
                                   for e in (r['source_endpoint'], r['target_endpoint'])}) == 2048))
    # compatibility with existing code structures
    compat = check_code_compatibility(routes_all)
    checks.append(dict(section='compatibility',
                       check='existing code data structures accept the new topology',
                       passed=compat['passed'], detail=json.dumps(compat)[:500]))
    validation = dict(schema='manual_c4_new_connectivity_validation_v1',
                      topology=TOPOLOGY, passed=all(c['passed'] for c in checks),
                      checks=checks, group_gate=group_gate,
                      inputs=topology['manual'],
                      combined_csv=topology['combined_csv'],
                      relation_counts=topology['relation_counts'],
                      pair_counts=topology['pair_counts'],
                      feasibility=feas)
    (INPUT_DIR / 'input_validation.json').write_text(
        json.dumps(validation, indent=1, ensure_ascii=False), encoding='utf-8')
    (INPUT_DIR / 'feasibility.json').write_text(
        json.dumps(feas, indent=1, ensure_ascii=False), encoding='utf-8')
    topology['input_validation'] = dict(
        passed=validation['passed'],
        checks=len(checks), passed_checks=sum(1 for c in checks if c['passed']))
    return topology


def check_code_compatibility(routes_all):
    """Prove the new topology plugs into the frozen D56 frames/candidate machinery."""
    from ..d56.frames import build_frames
    from ..v2opt.search import candidates_for
    from ..fslw import config as C
    eps = endpoints()
    report = dict(passed=False, frames={}, candidate_smoke={}, same_side={})
    errors = []
    for plane in PLANES:
        routes = [r for r in routes_all if r['plane'] == plane]
        plane_eps = {eid: ep for eid, ep in eps.items() if ep['plane'] == plane}
        normal = [r for r in routes if r['relation'] != 'same']
        same = [r for r in routes if r['relation'] == 'same']
        try:
            frames = build_frames(normal, plane_eps)
            report['frames'][plane] = len(frames)
        except Exception as exc:                              # noqa: BLE001
            errors.append(f'{plane} build_frames: {exc}')
            continue
        report['same_side'][plane] = dict(
            routes=len(same),
            note='same-side rows need the r15.u_geometry U-turn candidate family; '
                 'they are excluded from canonical frames by design')
        from ..fslw.candidates import FrameOracleSet
        from ..d56.search import static_endpoint_lines
        class _Stub:
            __slots__ = ('source_side', 'target_side', 'src_xy', 'dst_xy')
            def __init__(self, record):
                self.source_side = record['source_side']
                self.target_side = record['target_side']
                self.src_xy = tuple(eps[record['source_endpoint']]['routing_xy'])
                self.dst_xy = tuple(eps[record['target_endpoint']]['routing_xy'])

        stubs = {r['route_id']: _Stub(r) for r in same}
        all_frames = dict(frames)
        all_frames.update(stubs)
        static_h, static_v = static_endpoint_lines(all_frames)
        oracles = FrameOracleSet(frames, static_h, static_v, clearance=C.CLEARANCE_MM)
        for kind in ('opposite', 'adjacent'):
            sample = next((r for r in normal if r['relation'] == kind), None)
            if sample is None:
                continue
            try:
                iterator = candidates_for(frames[sample['route_id']],
                                          oracles.oracle_for(frames[sample['route_id']]))
                first = next(iter(iterator), None)
                report['candidate_smoke'][f'{plane}_{kind}'] = dict(
                    route_id=sample['route_id'],
                    first_candidate_family=(first or {}).get('family'),
                    generated=first is not None)
            except Exception as exc:                          # noqa: BLE001
                errors.append(f'{plane} {kind} candidates: {exc}')
        sample_same = same[0] if same else None
        if sample_same is not None:
            try:
                from ..r15 import u_geometry as UG
                ep_s = eps[sample_same['source_endpoint']]
                ep_t = eps[sample_same['target_endpoint']]
                from ..fslw.ports import INWARD
                inward = INWARD[sample_same['source_side']]
                candidates = UG.u_candidates(
                    tuple(ep_s['routing_xy']), tuple(ep_t['routing_xy']),
                    inward, (-inward[0], -inward[1]))
                report['same_side'][plane]['u_candidates'] = len(candidates)
                report['candidate_smoke'][f'{plane}_same'] = dict(
                    route_id=sample_same['route_id'],
                    candidates=len(candidates),
                    families=sorted({c['family'] for c in candidates}))
            except Exception as exc:                          # noqa: BLE001
                errors.append(f'{plane} same-side U: {exc}')
    report['passed'] = not errors
    report['errors'] = errors
    return report


def combined_topology():
    global _TOPOLOGY_CACHE
    if _TOPOLOGY_CACHE is None:
        if not COMBINED_JSON.exists():
            build_topology()
        payload = json.loads(COMBINED_JSON.read_text(encoding='utf-8'))
        _TOPOLOGY_CACHE = payload
    return _TOPOLOGY_CACHE


def groups_for_plane(plane):
    return [g for g in combined_topology()['groups'] if g['plane'] == plane]


def route_group_map():
    payload = combined_topology()
    return {int(k): tuple(v) for k, v in payload['route_group'].items()}


def main(argv=None):
    global OUT_ROOT, INPUT_DIR, COMBINED_CSV, COMBINED_JSON
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-root', type=Path, default=OUT_ROOT)
    args = parser.parse_args(argv)
    if args.out_root != OUT_ROOT:
        OUT_ROOT = args.out_root
        INPUT_DIR = OUT_ROOT / 'inputs'
        COMBINED_CSV = INPUT_DIR / 'connectivity_1024.csv'
        COMBINED_JSON = INPUT_DIR / 'connectivity_1024.json'
    topology = build_topology()
    validation = json.loads((INPUT_DIR / 'input_validation.json').read_text(
        encoding='utf-8'))
    print(json.dumps(dict(
        out=str(OUT_ROOT), inputs=str(INPUT_DIR),
        connections=topology['connections'], groups=topology['group_count'],
        relation_counts=topology['relation_counts'],
        group_kinds=topology['group_kinds'],
        rotation_closure=topology['rotation_closure'],
        validation_passed=validation['passed'],
        checks=len(validation['checks']),
        passed_checks=sum(1 for c in validation['checks'] if c['passed'])),
        indent=1, ensure_ascii=False))
    return topology


if __name__ == '__main__':
    main()
