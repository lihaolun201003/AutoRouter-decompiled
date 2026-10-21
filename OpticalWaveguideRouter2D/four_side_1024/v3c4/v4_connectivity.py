"""V4-C4 connectivity: same-side re-pairing of the 14 failed V3 adjacent groups.

Rules (from the task):
* keep all 512 opposite V3 connections (row 1);
* keep the 456 successfully routed V3 adjacent connections (row 2);
* replace the 56 connections of the 14 failed adjacent C4 groups by same-side
  connections: on every side the two ports of the group (left corner port and
  right corner port) are paired, the other three sides follow by 90 deg rotation;
* every physical port is used exactly once and the connection set stays strictly
  C4 symmetric at the physical-port level.

The output CSV keeps the V3 route_id ordering; the replaced rows keep their old
route ids.  No V3 file is modified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from .profile import apply as apply_profile

INWARD = {'N': (0.0, -1.0), 'S': (0.0, 1.0),
          'E': (-1.0, 0.0), 'W': (1.0, 0.0)}
CSV_FIELDS = ['route_id', 'source_side', 'source_connector', 'source_row',
              'source_column', 'source_channel', 'target_side', 'target_connector',
              'target_row', 'target_column', 'target_channel', 'relation']
EXPECTED_TYPES = dict(opposite=512, adjacent=456, same=56)
EXPECTED_GROUPS = dict(opposite=128, adjacent=114, same=14)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write_json(path, payload, indent=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def parse_eid(eid):
    connector, row, column = str(eid).split(':')
    return connector, int(row), int(column)


def format_eid(connector, row, column):
    return f'{connector}:{int(row)}:{int(column)}'


def mirror_same_side(eid):
    """Mirror port of the same group on the same board side (left <-> right corner)."""
    connector, row, column = parse_eid(eid)
    side = connector[0]
    index = int(connector[1:])
    return format_eid(f'{side}{17 - index:02d}', row, 17 - column)


def _port_fields(eid):
    connector, row, column = parse_eid(eid)
    return dict(side=connector[0], connector=connector, row=row, column=column,
                channel=(row - 1) * 16 + column)


def build_v4(routing_root=None, v3_csv=None, log=print):
    """Build the V4 connection table, 256 C4 groups and replaced-route mapping."""
    apply_profile()
    from . import inputs as V3

    routing_root = Path(routing_root or V3.ROUTING_ROOT)
    v3_csv = Path(v3_csv or V3.V3_CSV)
    raw = v3_csv.read_bytes()
    if Path(v3_csv) != Path(V3.V3_CSV):
        raise ValueError('build_v4 reuses the frozen V3 CSV via inputs.load_all_routes')
    routes_all, _sha = V3.load_all_routes()
    v3_by_id = {int(route['route_id']): route for route in routes_all}
    if len(v3_by_id) != 1024:
        raise ValueError(f'V3 connection table must have 1024 rows, got {len(v3_by_id)}')
    z2_payload = _read_json(routing_root / 'c4_2d' / 'z2' / 'routes.json')
    z2_routed = {int(record['route_id']) for record in z2_payload['routes']
                 if record.get('status') == 'routed'}
    groups_all, route_group = V3.build_groups()
    failed_groups = [group for group in groups_all if group['plane'] == 'z2'
                     and not all(rid in z2_routed for rid in group['route_ids'])]
    if len(failed_groups) != 14:
        raise ValueError(f'expected 14 failed adjacent groups, got {len(failed_groups)}')

    connections = []
    replaced = []
    for route in routes_all:
        record = dict(route)
        rid = int(route['route_id'])
        if record['relation'] == 'opposite':
            record['original_relation'] = 'opposite'
            connections.append(record)
            continue
        if rid in z2_routed:
            record['original_relation'] = 'adjacent'
            connections.append(record)
            continue
        source_eid = format_eid(route['source_connector'], route['source_row'],
                                route['source_column'])
        old_target = format_eid(route['target_connector'], route['target_row'],
                                route['target_column'])
        new_target = mirror_same_side(source_eid)
        fields = _port_fields(new_target)
        record.update(
            relation='same',
            pair=''.join(sorted((fields['side'], fields['side']))),
            target_side=fields['side'], target_connector=fields['connector'],
            target_row=fields['row'], target_column=fields['column'],
            target_channel=fields['channel'], target_endpoint=new_target,
            original_relation='adjacent', replaced_adjacent_target=old_target)
        connections.append(record)
        replaced.append(dict(route_id=rid,
                             old_adjacent=[source_eid, old_target],
                             new_same_side=[source_eid, new_target],
                             side=fields['side']))
    connections.sort(key=lambda record: int(record['route_id']))
    if len(connections) != 1024:
        raise ValueError(f'expected 1024 connections, got {len(connections)}')
    if len(replaced) != 56:
        raise ValueError(f'expected 56 replaced connections, got {len(replaced)}')

    # ---- C4 groups from the V4 connection set (unordered port pairs) --------
    by_conn = {frozenset((record['source_endpoint'], record['target_endpoint'])):
               record for record in connections}
    if len(by_conn) != 1024:
        raise ValueError('duplicate unordered connections in V4 table')
    assigned = {}
    groups = []
    for record in connections:
        rid = int(record['route_id'])
        if rid in assigned:
            continue
        orbit = [record]
        current = frozenset((record['source_endpoint'], record['target_endpoint']))
        for _step in range(3):
            rotated = frozenset(V3.rot90_endpoint(eid) for eid in current)
            nxt = by_conn.get(rotated)
            if nxt is None:
                raise ValueError(f'route {rid} has no C4 rotation partner')
            orbit.append(nxt)
            current = rotated
        if frozenset(V3.rot90_endpoint(eid) for eid in current) != \
                frozenset((record['source_endpoint'], record['target_endpoint'])):
            raise ValueError(f'route {rid} orbit does not close at 4 members')
        kind = record['relation']
        gid = len(groups) + 1
        groups.append(dict(group_id=gid, kind=kind, plane=record['plane'],
                           route_ids=[int(member['route_id']) for member in orbit]))
        for member in orbit:
            assigned[int(member['route_id'])] = gid
    if len(groups) != 256:
        raise ValueError(f'expected 256 groups, got {len(groups)}')
    log(f'[v4] connections={len(connections)} replaced={len(replaced)} '
        f'groups={len(groups)} kinds={dict(Counter(g["kind"] for g in groups))}')
    return dict(connections=connections, groups=groups, replaced=replaced,
                v3_csv=str(v3_csv), v3_csv_sha256=hashlib.sha256(raw).hexdigest(),
                routing_root=str(routing_root),
                failed_groups_v3=[int(group['group_id']) for group in failed_groups],
                v3_groups=groups_all, v3_route_group=route_group)


def validate_v4(data, log=print):
    """Strict port-usage / relation / row / C4 equations for the V4 table."""
    apply_profile()
    from . import inputs as V3

    errors = []
    connections = data['connections']
    usage = Counter()
    relation_count = Counter()
    pair_count = Counter()
    row_count = Counter()
    for record in connections:
        usage[record['source_endpoint']] += 1
        usage[record['target_endpoint']] += 1
        relation_count[record['relation']] += 1
        pair_count[''.join(sorted((record['source_side'], record['target_side'])))] += 1
        row_count[int(record['source_row'])] += 1
        if int(record['source_row']) != int(record['target_row']):
            errors.append(f'row mismatch route {record["route_id"]}')
        sides = {record['source_side'], record['target_side']}
        if record['relation'] == 'opposite':
            if sides not in ({'N', 'S'}, {'E', 'W'}):
                errors.append(f'opposite side mismatch route {record["route_id"]}')
        elif record['relation'] == 'adjacent':
            if record['source_side'] == record['target_side']:
                errors.append(f'adjacent same side route {record["route_id"]}')
        elif record['relation'] == 'same':
            if record['source_side'] != record['target_side']:
                errors.append(f'same-side mismatch route {record["route_id"]}')
        else:
            errors.append(f'unknown relation route {record["route_id"]}')
    if len(connections) != 1024:
        errors.append(f'connection count {len(connections)}')
    if len(usage) != 2048 or set(usage.values()) != {1}:
        errors.append(f'port usage unique={len(usage)} counts={set(usage.values())}')
    if set(usage) != set(V3.ENDPOINTS):
        errors.append('port identity set mismatch vs V3 interface table')
    if relation_count != Counter(EXPECTED_TYPES):
        errors.append(f'relation counts {dict(relation_count)}')
    expected_pairs = Counter({'NS': 256, 'EW': 256, 'EN': 114, 'ES': 114,
                              'SW': 114, 'NW': 114, 'NN': 14, 'EE': 14,
                              'SS': 14, 'WW': 14})
    if pair_count != expected_pairs:
        errors.append(f'pair counts {dict(pair_count)}')
    if row_count != Counter({1: 512, 2: 512}):
        errors.append(f'row counts {dict(row_count)}')
    def _rot(eid, times):
        from . import inputs as V3
        endpoint = eid
        for _ in range(int(times)):
            endpoint = V3.rot90_endpoint(endpoint)
        return endpoint

    conn_set = {frozenset((record['source_endpoint'], record['target_endpoint']))
                for record in connections}
    if len(conn_set) != 1024:
        errors.append('duplicate unordered connections')
    closure = {}
    for k in (1, 2, 3):
        missing = sum(1 for conn in conn_set
                      if frozenset(_rot(eid, k) for eid in conn)
                      not in conn_set)
        closure[f'{k * 90}deg'] = missing
        if missing:
            errors.append(f'rot{k * 90} closure missing {missing}')
    groups = data['groups']
    kinds = Counter(group['kind'] for group in groups)
    if kinds != Counter(EXPECTED_GROUPS):
        errors.append(f'group kinds {dict(kinds)}')
    if [len(group['route_ids']) for group in groups] != [4] * 256:
        errors.append('group sizes not all 4')
    replaced = data['replaced']
    same_side_counts = Counter(item['side'] for item in replaced)
    if same_side_counts != Counter({'N': 14, 'E': 14, 'S': 14, 'W': 14}):
        errors.append(f'same-side per-side counts {dict(same_side_counts)}')
    for item in replaced:
        if not item['new_same_side'][0].startswith(item['side']) or \
                not item['new_same_side'][1].startswith(item['side']):
            errors.append(f'same-side port not on side: {item["route_id"]}')
    report = dict(
        schema='four_side_1024_v4_connectivity_validation_v1',
        rows=len(connections), ports=len(usage),
        relation_counts=dict(relation_count), pair_counts=dict(pair_count),
        row_counts=dict(row_count), groups=len(groups), group_kinds=dict(kinds),
        same_side_per_side=dict(same_side_counts),
        rotation_closure=closure, errors=errors[:20], error_count=len(errors),
        passed=not errors)
    log(f'[v4] validation: ports={len(usage)} relations={dict(relation_count)} '
        f'closure={closure} same-side/side={dict(same_side_counts)} '
        f'groups={len(groups)} -> {"PASS" if report["passed"] else "FAIL"}')
    return report


def write_csv(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle, lineterminator='\r\n')
        writer.writerow(CSV_FIELDS)
        for record in data['connections']:
            writer.writerow([record['route_id'], record['source_side'],
                             record['source_connector'], record['source_row'],
                             record['source_column'], record['source_channel'],
                             record['target_side'], record['target_connector'],
                             record['target_row'], record['target_column'],
                             record['target_channel'], record['relation']])
    return sha256_file(path)


# ---------------------------------------------------------------------------
# Excel workbook (5 sheets)
# ---------------------------------------------------------------------------
def write_excel(data, validation, csv_sha, path, log=print):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    head_font = Font(bold=True, color='FFFFFF')
    head_fill = PatternFill('solid', fgColor='1F4E78')

    def header(sheet, columns, row=1):
        for index, name in enumerate(columns, 1):
            cell = sheet.cell(row=row, column=index, value=name)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
        sheet.freeze_panes = f'A{row + 1}'

    def widths(sheet, columns):
        for index, name in enumerate(columns, 1):
            sheet.column_dimensions[get_column_letter(index)].width = max(
                10, min(30, len(str(name)) + 4))

    # Sheet 1: 1024 connections
    sheet = workbook.active
    sheet.title = '1024连接总表'
    columns = ['route_id', 'relation', '原V3关系', 'source_side', 'source_connector',
               'source_row', 'source_column', 'source_channel', 'source_endpoint',
               'target_side', 'target_connector', 'target_row', 'target_column',
               'target_channel', 'target_endpoint', 'plane', 'row_z_mm']
    header(sheet, columns)
    widths(sheet, columns)
    for record in data['connections']:
        sheet.append([record['route_id'], record['relation'],
                      record.get('original_relation'),
                      record['source_side'], record['source_connector'],
                      int(record['source_row']), int(record['source_column']),
                      int(record['source_channel']), record['source_endpoint'],
                      record['target_side'], record['target_connector'],
                      int(record['target_row']), int(record['target_column']),
                      int(record['target_channel']), record['target_endpoint'],
                      record['plane'], float(record['z_mm'])])
    sheet.auto_filter.ref = sheet.dimensions

    # Sheet 2: 2048 ports / interface table
    sheet = workbook.create_sheet('四边接口表')
    columns = ['endpoint', 'side', 'connector', 'row', 'column', 'channel',
               'routing_x_mm', 'routing_y_mm', 'row_z_mm', 'peer_endpoint',
               'peer_route_id', 'peer_relation']
    header(sheet, columns)
    widths(sheet, columns)
    from . import inputs as V3
    peer = {}
    for record in data['connections']:
        peer[record['source_endpoint']] = (record['target_endpoint'],
                                           record['route_id'], record['relation'])
        peer[record['target_endpoint']] = (record['source_endpoint'],
                                           record['route_id'], record['relation'])
    for eid in sorted(V3.ENDPOINTS):
        endpoint = V3.ENDPOINTS[eid]
        connector, row, column = parse_eid(eid)
        x, y = endpoint['routing_xy']
        peer_eid, peer_rid, peer_relation = peer[eid]
        sheet.append([eid, connector[0], connector, row, column,
                      (row - 1) * 16 + column, round(x, 6), round(y, 6),
                      float(endpoint['z_mm']), peer_eid, peer_rid, peer_relation])
    sheet.auto_filter.ref = sheet.dimensions

    # Sheet 3: rotation groups (256 x 4)
    sheet = workbook.create_sheet('旋转对称组')
    columns = ['group_id', 'kind', 'plane', 'phase0_route', 'phase1_route',
               'phase2_route', 'phase3_route', 'phase0_connection', 'phase1_connection',
               'phase2_connection', 'phase3_connection']
    header(sheet, columns)
    widths(sheet, columns)
    by_id = {int(record['route_id']): record for record in data['connections']}

    def connection_text(rid):
        record = by_id[rid]
        return f"{record['source_endpoint']}->{record['target_endpoint']}"

    for group in data['groups']:
        ids = [int(rid) for rid in group['route_ids']]
        sheet.append([group['group_id'], group['kind'], group['plane'], *ids,
                      *[connection_text(rid) for rid in ids]])
    sheet.auto_filter.ref = sheet.dimensions

    # Sheet 4: statistics and validation
    sheet = workbook.create_sheet('统计与验证')
    header(sheet, ['项目 item', '值 value'])
    sheet.column_dimensions['A'].width = 36
    sheet.column_dimensions['B'].width = 90
    rows = [
        ('schema', 'four_side_1024_v4_c4_connectivity_v1'),
        ('CSV SHA256', csv_sha),
        ('总连接数', validation['rows']),
        ('物理端口数', validation['ports']),
        ('对边连接数 (512)', validation['relation_counts'].get('opposite', 0)),
        ('邻边连接数 (456)', validation['relation_counts'].get('adjacent', 0)),
        ('同边连接数 (56)', validation['relation_counts'].get('same', 0)),
        ('四元旋转组数', validation['groups']),
        ('组类型分布', json.dumps(validation['group_kinds'], ensure_ascii=False)),
        ('同边连接每边数量', json.dumps(validation['same_side_per_side'],
                                  ensure_ascii=False)),
        ('端口唯一使用', 'PASS' if validation['ports'] == 2048 else 'FAIL'),
        ('旋转闭包 (90/180/270)', json.dumps(validation['rotation_closure'],
                                       ensure_ascii=False)),
        ('自动验收', 'PASS' if validation['passed'] else 'FAIL'),
        ('错误数', validation['error_count']),
        ('生成时间', time.strftime('%Y-%m-%dT%H:%M:%S')),
    ]
    for name, value in rows:
        sheet.append([name, value])
    for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row, min_col=1, max_col=1):
        row[0].font = Font(bold=True)

    # Sheet 5: source / notes / replaced rows
    sheet = workbook.create_sheet('来源与重配对')
    header(sheet, ['项目 item', '内容 content'])
    sheet.column_dimensions['A'].width = 34
    sheet.column_dimensions['B'].width = 110
    notes = [
        ('V3 输入 CSV', data['v3_csv']),
        ('V3 CSV SHA256（未修改）', data['v3_csv_sha256']),
        ('V3 布线结果目录', data['routing_root']),
        ('V3 失败邻边四元组', ','.join(str(v) for v in data['failed_groups_v3'])),
        ('规则', '保留 512 对边 + 456 成功邻边；56 条失败邻边改为同边配对：'
                 '每边两个角部端口互连，其余三边按 90° 旋转生成；2048 端口各用一次；严格端口级 C4'),
        ('route_id 约定', '保持 V3 route_id 1..1024 不变，被重配对的 56 条沿用原 route_id'),
        ('同边 U 形几何', '由 four_side_1024/r15/u_geometry.py 按 R=15mm 生成'
                          '（quarter_pair / half_circle / stadium，最小同边分离 2R=30mm）'),
    ]
    for name, value in notes:
        sheet.append([name, value])
    sheet.append([])
    sheet.append(['被重配对的 56 条（V3 邻边 -> V4 同边）', ''])
    header(sheet, ['route_id', 'side', 'V3 邻边配对', 'V4 同边配对'], row=sheet.max_row + 1 if False else 1)
    # rewrite cleanly: dedicated columns sheet
    sheet = workbook.create_sheet('被重配对行')
    columns = ['route_id', 'side', 'old_source', 'old_target', 'new_source',
               'new_target']
    header(sheet, columns)
    widths(sheet, columns)
    for item in data['replaced']:
        sheet.append([item['route_id'], item['side'], item['old_adjacent'][0],
                      item['old_adjacent'][1], item['new_same_side'][0],
                      item['new_same_side'][1]])
    sheet.auto_filter.ref = sheet.dimensions

    workbook.save(path)
    log(f'[v4] excel written {path}')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routing-root', type=Path, default=None)
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    from . import inputs as V3
    routing_root = args.routing_root or Path(V3.ROUTING_ROOT)
    out_dir = Path(args.out or (repo / 'outputs/four_side_1024_v4_c4_routing'))
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'connectivity.log'
    log_handle = open(log_path, 'a', encoding='utf-8')

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        log_handle.write(line + '\n')
        log_handle.flush()

    data = build_v4(routing_root=routing_root, log=log)
    validation = validate_v4(data, log=log)
    csv_path = out_dir / 'optical_1024_multitomulti_connectivity_v4_c4_symmetric.csv'
    csv_sha = write_csv(data, csv_path)
    excel_path = out_dir / 'optical_1024_multitomulti_connectivity_v4_c4_symmetric.xlsx'
    write_excel(data, validation, csv_sha, excel_path, log=log)
    _write_json(out_dir / 'v4_connectivity_data.json',
                dict(connections=data['connections'], groups=data['groups'],
                     replaced=data['replaced'],
                     v3_csv=data['v3_csv'], v3_csv_sha256=data['v3_csv_sha256'],
                     failed_groups_v3=data['failed_groups_v3'],
                     schema='four_side_1024_v4_c4_connectivity_data_v1'),
                indent=None)
    validation.update(csv_path=str(csv_path), csv_sha256=csv_sha,
                      excel_path=str(excel_path),
                      excel_sha256=sha256_file(excel_path),
                      v3_sources=dict(csv=data['v3_csv'],
                                      sha256=data['v3_csv_sha256'],
                                      routing_root=data['routing_root']))
    _write_json(out_dir / 'validation_connectivity.json', validation, indent=1)
    log_handle.close()
    print(json.dumps({key: validation[key] for key in
                      ('rows', 'ports', 'relation_counts', 'groups',
                       'passed', 'csv_sha256')}, ensure_ascii=False))
    return dict(data=data, validation=validation, csv_path=csv_path,
                excel_path=excel_path)


if __name__ == '__main__':
    main()
