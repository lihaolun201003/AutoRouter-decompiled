"""V3-Huang input adapter: frozen CSV (routing) + XLSX (connector-level cross-check).

The CSV is authoritative for the 1024 fixed fibre-level connections; the XLSX is read
only to cross-check the connector topology, the 64x64 relation matrix and the
statistics sheets.  Nothing is regenerated, edited or re-ordered.

Returned connection record fields (all CSV fields are preserved):
    route_id, source_side, source_connector, source_row, source_column,
    source_channel, target_side, target_connector, target_row, target_column,
    target_channel, relation, pair, plane, z_mm, source_endpoint, target_endpoint
"""
from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

import openpyxl

from . import config as C

PAIR_NAME = {('N', 'S'): 'NS', ('E', 'W'): 'EW',
             ('N', 'E'): 'NE', ('E', 'S'): 'ES', ('S', 'W'): 'SW', ('N', 'W'): 'NW'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def relation_of(source_side, target_side):
    """Return same / opposite / adjacent from the two sides alone (validation helper)."""
    if source_side == target_side:
        return 'same'
    pair = frozenset((source_side, target_side))
    if pair in (frozenset('NS'), frozenset('EW')):
        return 'opposite'
    return 'adjacent'


def pair_of(source_side, target_side):
    """Pair label; same-side pairs keep the doubled letter (NN/SS/EE/WW)."""
    if source_side == target_side:
        return source_side * 2
    key = (source_side, target_side)
    if key in PAIR_NAME:
        return PAIR_NAME[key]
    return PAIR_NAME[(target_side, source_side)]


def endpoint_key(connector, row, column):
    return f'{connector}:{int(row)}:{int(column)}'


def read_connections(csv_path=None):
    """Parse and validate the V3 CSV; returns ``(connections, sha256, issues)``."""
    csv_path = Path(csv_path or C.CSV_PATH)
    raw = csv_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    issues = []
    connections = []
    for raw_row in rows:
        record = dict(raw_row)
        record['route_id'] = int(record['route_id'])
        for role in ('source', 'target'):
            for field in ('row', 'column', 'channel'):
                record[f'{role}_{field}'] = int(record[f'{role}_{field}'])
            record[f'{role}_endpoint'] = endpoint_key(
                record[f'{role}_connector'], record[f'{role}_row'],
                record[f'{role}_column'])
        source_side = record['source_side']
        target_side = record['target_side']
        record['relation_csv'] = record.get('relation')
        record['pair'] = pair_of(source_side, target_side)
        record['relation'] = relation_of(source_side, target_side)
        if record['relation_csv'] and record['relation_csv'] != record['relation']:
            issues.append(f'route {record["route_id"]} relation column mismatch '
                          f'({record["relation_csv"]} vs {record["relation"]})')
        record['plane'] = C.PLANE_NAME[record['source_row']]
        record['z_mm'] = C.PLANE_Z_MM[record['source_row']]
        connections.append(record)
    return connections, sha, issues


def validate_connections(connections, sha=None):
    """Full structural validation of the V3 frozen topology; returns a report dict."""
    issues = []
    ids = [record['route_id'] for record in connections]
    if len(connections) != C.EXPECTED['connections']:
        issues.append(f'connection count {len(connections)}')
    if sorted(ids) != list(range(1, len(connections) + 1)):
        issues.append('route_id is not 1..1024 unique')

    relations = Counter(record['relation'] for record in connections)
    pairs = Counter(record['pair'] for record in connections)
    for relation, expected in C.EXPECTED['relation_counts'].items():
        if relations[relation] != expected:
            issues.append(f'relation {relation} = {relations[relation]} != {expected}')
    for pair, expected in C.EXPECTED['pair_counts'].items():
        if pairs[pair] != expected:
            issues.append(f'pair {pair} = {pairs[pair]} != {expected}')

    # relation must come from the sides (CSV 'relation' column is not trusted blindly)
    relation_from_sides = Counter(relation_of(record['source_side'], record['target_side'])
                                  for record in connections)
    if dict(relation_from_sides) != dict(relations):
        issues.append('relation column disagrees with the sides')

    endpoints = Counter()
    connector_fibres = Counter()
    for record in connections:
        for role in ('source', 'target'):
            key = record[f'{role}_endpoint']
            endpoints[key] += 1
            connector_fibres[record[f'{role}_connector']] += 1
            side = record[f'{role}_side']
            if record[f'{role}_connector'][0] != side:
                issues.append(f'route {record["route_id"]} {role} connector/side mismatch')
            expected_channel = (record[f'{role}_row'] - 1) * C.COLUMNS + record[f'{role}_column']
            if record[f'{role}_channel'] != expected_channel:
                issues.append(f'route {record["route_id"]} {role} channel mismatch')
        if record['source_side'] == record['target_side'] and \
                record['source_connector'] == record['target_connector']:
            issues.append(f'route {record["route_id"]} same-side self connection')
        if record['source_row'] != record['target_row']:
            issues.append(f'route {record["route_id"]} mixes rows')
    if len(endpoints) != C.EXPECTED['endpoints'] or set(endpoints.values()) != {1}:
        issues.append(f'endpoint usage: {len(endpoints)} unique, '
                      f'counts {sorted(set(endpoints.values()))}')
    if len(connector_fibres) != C.EXPECTED['connectors'] or \
            set(connector_fibres.values()) != {C.EXPECTED['fibers_per_connector']}:
        issues.append(f'connector fibre usage: {len(connector_fibres)} connectors, '
                      f'counts {sorted(set(connector_fibres.values()))}')

    planes = {}
    for plane in C.PLANES:
        row = C.PLANE_ROW[plane]
        selected = [record for record in connections if record['source_row'] == row]
        plane_relations = Counter(record['relation'] for record in selected)
        expected = C.EXPECTED['planes'][plane]
        planes[plane] = dict(
            total=len(selected), relation_counts=dict(plane_relations),
            pairs=dict(Counter(record['pair'] for record in selected)),
            endpoints=len(selected) * 2,
        )
        if len(selected) != expected['total']:
            issues.append(f'{plane} connections {len(selected)} != {expected["total"]}')
        for relation in C.RELATIONS:
            if plane_relations[relation] != expected[relation]:
                issues.append(f'{plane} {relation} {plane_relations[relation]} != '
                              f'{expected[relation]}')
        if len(selected) * 2 != len({record[f"{role}_endpoint"] for record in selected
                                    for role in ("source", "target")}):
            issues.append(f'{plane} endpoints are not unique')
    report = dict(
        passed=not issues, issues=issues,
        csv_path=str(C.CSV_PATH), csv_sha256=sha,
        csv_sha256_expected=C.EXPECTED_CSV_SHA256,
        csv_sha256_match=(sha == C.EXPECTED_CSV_SHA256) if sha else None,
        connections=len(connections),
        relation_counts=dict(relations), pair_counts=dict(pairs),
        by_side=dict(Counter(record['source_side'] for record in connections)),
        planes=planes,
        connector_fibres=dict(sorted(connector_fibres.items())),
        endpoints_used_once=len(endpoints) == C.EXPECTED['endpoints'] and
                            set(endpoints.values()) == {1},
    )
    return report


# --------------------------------------------------------------------- XLSX
def excel_crosscheck(connections, xlsx_path=None):
    """Cross-check the connector-level XLSX against the CSV (read-only)."""
    xlsx_path = Path(xlsx_path or C.XLSX_PATH)
    sha = sha256(xlsx_path)
    workbook = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    sheets = workbook.sheetnames
    report = dict(xlsx_path=str(xlsx_path), xlsx_sha256=sha,
                  xlsx_sha256_match=(sha == C.EXPECTED_XLSX_SHA256),
                  sheets=list(sheets), checks={}, issues=[])

    def rows_of(name):
        sheet = workbook[name]
        return [list(row) for row in sheet.iter_rows(values_only=True)
                if row and any(cell is not None for cell in row)]

    try:
        # connector-level Port1/Port2 (Sheet1)
        port_rows = rows_of('Sheet1')
        header = port_rows[0]
        ports = [(int(row[0]), int(row[1])) for row in port_rows[1:] if row[0] is not None]
        report['checks']['sheet1'] = dict(header=list(header), pairs=len(ports))
        report['checks']['sheet1']['pass'] = (len(ports) == 1024)
        if len(ports) != 1024:
            report['issues'].append(f'Sheet1 pairs {len(ports)}')

        # interface mapping (64 connectors)
        map_rows = rows_of('接口映射')
        mapping = [row for row in map_rows[1:] if row[0] is not None]
        report['checks']['mapping'] = dict(rows=len(mapping),
                                           header=list(map_rows[0]))
        report['checks']['mapping']['pass'] = len(mapping) == 64
        if len(mapping) != 64:
            report['issues'].append(f'接口映射 rows {len(mapping)}')

        # 64x64 connector matrix
        matrix_rows = rows_of('64x64连接矩阵')
        labels = [str(cell) for cell in matrix_rows[0][1:] if cell is not None]
        matrix = {}
        for row in matrix_rows[1:]:
            if row[0] is None:
                continue
            matrix[str(row[0])] = {label: int(value or 0)
                                   for label, value in zip(labels, row[1:])}
        csv_connector_counts = Counter()
        for record in connections:
            a, b = record['source_connector'], record['target_connector']
            csv_connector_counts[(a, b)] += 1
        matrix_total = sum(sum(values.values()) for values in matrix.values())
        symmetric = all(matrix[a][b] == matrix[b][a]
                        for a in matrix for b in matrix[a])
        mismatches = []
        for (a, b), count in csv_connector_counts.items():
            if matrix.get(a, {}).get(b) != count:
                mismatches.append((a, b, count, matrix.get(a, {}).get(b)))
        report['checks']['matrix'] = dict(
            labels=len(labels), total=matrix_total, symmetric=symmetric,
            csv_total=len(connections), mismatches=len(mismatches),
            sample_mismatches=mismatches[:10],
            pass_=(matrix_total == 2048 and symmetric and not mismatches))
        if matrix_total != 2048:
            report['issues'].append(f'64x64 matrix total {matrix_total} != 2048')
        if not symmetric:
            report['issues'].append('64x64 matrix is not symmetric')
        if mismatches:
            report['issues'].append(f'{len(mismatches)} connector-pair counts differ')

        # fibre-level reference sheet == CSV
        fibre_rows = rows_of('光纤级连接_参考')
        reference = [row for row in fibre_rows[1:] if row[0] is not None]
        csv_sorted = sorted(
            (record['route_id'], record['source_side'], record['source_connector'],
             record['source_row'], record['source_column'], record['source_channel'],
             record['target_side'], record['target_connector'], record['target_row'],
             record['target_column'], record['target_channel'], record['relation_check'])
            for record in connections)
        ref_sorted = sorted(
            (int(row[0]), str(row[1]), str(row[2]), int(row[3]), int(row[4]), int(row[5]),
             str(row[6]), str(row[7]), int(row[8]), int(row[9]), int(row[10]), str(row[11]))
            for row in reference)
        report['checks']['fibre_reference'] = dict(
            rows=len(reference), matches_csv=(ref_sorted == csv_sorted))
        if ref_sorted != csv_sorted:
            report['issues'].append('光纤级连接_参考 sheet differs from the CSV')

        # statistics sheet
        stat_rows = rows_of('连接类别统计')
        report['checks']['statistics'] = dict(header=list(stat_rows[0]),
                                              rows=[[str(cell) for cell in row]
                                                    for row in stat_rows[1:]
                                                    if row[0] is not None])
    finally:
        workbook.close()
    report['passed'] = not report['issues']
    return report


def load_all(csv_path=None, xlsx_path=None):
    """Return ``(connections, validation_report)`` for the frozen V3 topology."""
    connections, sha, _issues = read_connections(csv_path)
    for record in connections:
        record['relation_check'] = record['relation']
    validation = validate_connections(connections, sha)
    validation['excel'] = excel_crosscheck(connections, xlsx_path)
    validation['passed'] = validation['passed'] and validation['excel']['passed']
    validation['topology'] = C.TOPOLOGY
    validation['expected'] = C.EXPECTED
    return connections, validation
