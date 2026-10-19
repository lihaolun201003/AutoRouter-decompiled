"""Dual-height real IEC 61754-7-3:2019 2x16 MPO port model for the FSLW experiment.

The CSV identity/order is never changed.  The 32 channels of every connector are no
longer virtually unfolded into one plane: row 1 of every connector is mounted at height
``z1`` and row 2 at ``z2`` (0.5 mm apart along the glass thickness), and the connections
of each CSV row are routed *within that row's plane* only:

* plane ``z1``: CSV rows with ``row = 1`` (512 opposite-side connections NS/EW),
* plane ``z2``: CSV rows with ``row = 2`` (512 adjacent-side connections EN/ES/SW/NW).

Inside a plane each connector exposes its 16 row fibres at the IEC column pitch
(0.25 mm); the four sides x 16 connectors x 16 columns = 1024 ports are used exactly
once by that plane's 512 connections.
"""
from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

from ..inputs import board_xy
from . import config as C

SIDES = 'NSEW'
INWARD = {'N': (0., -1.), 'S': (0., 1.), 'E': (-1., 0.), 'W': (1., 0.)}
DESKTOP = Path(r'C:\Users\lihao\Desktop')
TOPOLOGY_PATHS = {
    'V1': DESKTOP / 'optical_1024_multitomulti_connectivity_v1.csv',
    'V2': DESKTOP / 'optical_1024_multitomulti_connectivity_v2_symmetric.csv',
}
EXPECTED_SHA256 = {
    'V1': '0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b',
    'V2': '49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e',
}
PLANES = ('z1', 'z2')


def resolve_topology(topology_or_path):
    """Return ``(topology_label, csv_path)``; never generates a new V2 file."""
    text = str(topology_or_path)
    if text.upper() in TOPOLOGY_PATHS:
        label = text.upper()
        path = TOPOLOGY_PATHS[label]
    else:
        path = Path(text)
        label = 'V1' if 'v1' in path.name.lower() else (
            'V2' if 'v2' in path.name.lower() else 'V0')
    if not path.exists():
        raise FileNotFoundError(f'connectivity CSV not found: {path}')
    return label, path


def read_csv(path):
    raw = Path(path).read_bytes()
    rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    return rows, hashlib.sha256(raw).hexdigest()


def connector_records():
    connectors = []
    for side in SIDES:
        for index in range(1, C.CONNECTORS_PER_SIDE + 1):
            name = f'{side}{index:02d}'
            center = 7.5 + (index - 1) * C.CONNECTOR_PITCH_MM
            connectors.append(dict(connector=name, side=side, center_xy=board_xy(side, center),
                                   along_center_mm=center, rows=C.ROWS,
                                   columns=C.COLUMNS,
                                   channels_per_connector=C.ROWS * C.COLUMNS,
                                   envelope_width_mm=C.ENVELOPE_WIDTH_MM,
                                   fiber_column_pitch_mm=C.FIBER_COLUMN_PITCH_MM,
                                   fiber_row_pitch_mm=C.FIBER_ROW_PITCH_MM))
    return connectors


def port_along_mm(connector_index, column):
    center = 7.5 + (connector_index - 1) * C.CONNECTOR_PITCH_MM
    return center + (column - (C.COLUMNS + 1) / 2.0) * C.FIBER_COLUMN_PITCH_MM


def port_key(connector, row, column):
    return f'{connector}:{row}:{column}'


def plane_of_row(row):
    if row == 1:
        return 'z1'
    if row == 2:
        return 'z2'
    raise ValueError(f'only the two IEC rows exist, got row={row}')


def build_plane_endpoints():
    """All 2048 physical port identities: endpoint_id -> routing/plane/physical record."""
    endpoints = {}
    for connector in connector_records():
        side = connector['side']
        index = int(connector['connector'][1:])
        for row in (1, 2):
            z = C.PLANE_Z_MM[row]
            plane = C.PLANE_NAME[row]
            for column in range(1, C.COLUMNS + 1):
                channel = (row - 1) * C.COLUMNS + column
                along = port_along_mm(index, column)
                key = port_key(connector['connector'], row, column)
                endpoints[key] = dict(
                    endpoint_id=key, connector=connector['connector'], side=side,
                    row=row, column=column, channel=channel,
                    routing_xy=board_xy(side, along),
                    inward=list(INWARD[side]),
                    layer=0, plane=plane, z_mm=z,
                    physical_along_mm=along,
                    physical_face_u_mm=(column - (C.COLUMNS + 1) / 2.0) * C.FIBER_COLUMN_PITCH_MM,
                    physical_face_v_mm=(row - 1.5) * C.FIBER_ROW_PITCH_MM,
                    port_model=C.PORT_MODEL,
                )
    return endpoints


def load_plane(topology_or_path, plane):
    """Load one plane: ``(routes, endpoints, connectors, validation)``.

    ``routes`` are exactly the CSV rows whose ``row`` maps to ``plane``; every other
    field (route_id, source/target endpoint txt, pair, relation, row/column/channel)
    is preserved from the CSV.  ``endpoints`` contains only this plane's 1024 ports.
    """
    label, path = resolve_topology(topology_or_path)
    rows, sha = read_csv(path)
    if len(rows) != 1024:
        raise ValueError(f'expected 1024 connections, got {len(rows)}')
    if label in EXPECTED_SHA256 and sha.lower() != EXPECTED_SHA256[label]:
        raise ValueError(f'{label} CSV SHA256 mismatch: {sha}')
    if plane not in PLANES:
        raise ValueError(f'plane must be one of {PLANES}')
    row_number = C.PLANE_ROW[plane]
    all_endpoints = build_plane_endpoints()
    endpoints = {key: value for key, value in all_endpoints.items()
                 if value['plane'] == plane}
    routes = []
    usage = Counter()
    for raw in rows:
        record = dict(raw)
        record['route_id'] = int(record['route_id'])
        for role in ('source', 'target'):
            for field in ('row', 'column', 'channel'):
                record[f'{role}_{field}'] = int(record[f'{role}_{field}'])
            key = port_key(record[f'{role}_connector'], record[f'{role}_row'],
                           record[f'{role}_column'])
            record[f'{role}_endpoint'] = key
        source_side, target_side = record['source_side'], record['target_side']
        if source_side == target_side:
            raise ValueError(f'route {record["route_id"]} connects one side twice')
        pair = ''.join(sorted((source_side, target_side)))
        relation = 'opposite' if pair in ('NS', 'EW') else 'adjacent'
        record['pair'] = pair
        record['relation'] = relation
        record['plane'] = plane_of_row(record['source_row'])
        record['z_mm'] = C.PLANE_Z_MM[record['source_row']]
        record['row'] = record['source_row']
        if record['source_row'] != record['target_row']:
            raise ValueError(f'route {record["route_id"]} mixes rows')
        if record['plane'] != plane:
            continue
        routes.append(record)
        usage[record['source_endpoint']] += 1
        usage[record['target_endpoint']] += 1
    if len(routes) != 512:
        raise ValueError(f'plane {plane} must hold 512 connections, got {len(routes)}')
    validation = validate_plane(routes, endpoints, label, path, sha, plane)
    return routes, endpoints, connector_records(), validation


def validate_plane(routes, endpoints, label, path, sha, plane):
    """Structural checks of the dual-height port model for one plane."""
    expected_row = C.PLANE_ROW[plane]
    issues = []
    if len(routes) != 512:
        issues.append(f'route_count={len(routes)}')
    route_ids = [route['route_id'] for route in routes]
    if len(set(route_ids)) != len(route_ids):
        issues.append('duplicate route_id')
    usage = Counter()
    relations = Counter()
    pairs = Counter()
    rows = Counter()
    for route in routes:
        usage[route['source_endpoint']] += 1
        usage[route['target_endpoint']] += 1
        relations[route['relation']] += 1
        pairs[route['pair']] += 1
        rows[route['source_row']] += 1
        rows[route['target_row']] += 1
        if route['source_row'] != route['target_row']:
            issues.append(f'route {route["route_id"]} mixes rows')
        if route['source_row'] != expected_row:
            issues.append(f'route {route["route_id"]} wrong row')
        if route['source_side'] == route['target_side']:
            issues.append(f'route {route["route_id"]} same side')
    if len(usage) != 1024 or set(usage.values()) != {1}:
        issues.append(f'ports used {len(usage)} unique, counts {set(usage.values())}')
    if set(usage) != set(endpoints):
        issues.append('port identity set mismatch')
    expected_relations = {'z1': {'opposite': 512}, 'z2': {'adjacent': 512}}[plane]
    if dict(relations) != expected_relations:
        issues.append(f'relation counts {dict(relations)} != {expected_relations}')
    # IEC geometry checks
    sides = Counter(endpoint['side'] for endpoint in endpoints.values())
    if dict(sides) != {'N': 256, 'E': 256, 'S': 256, 'W': 256}:
        issues.append(f'side port counts {dict(sides)}')
    for endpoint in endpoints.values():
        x, y = endpoint['routing_xy']
        if not (x == x and y == y and abs(x) < 1e6 and abs(y) < 1e6):
            issues.append('non-finite port coordinate')
        if not (0.0 <= x <= C.BOARD_MM and 0.0 <= y <= C.BOARD_MM):
            issues.append(f'port outside board: {endpoint["endpoint_id"]}')
    validation = dict(
        passed=not issues, issues=issues, topology=label, csv_path=str(path),
        csv_sha256=sha, plane=plane, plane_row=expected_row,
        z_mm=C.PLANE_Z_MM[expected_row], port_model=C.PORT_MODEL,
        connections=len(routes), ports=len(endpoints),
        ports_used_once=True, relations=dict(relations), pairs=dict(pairs),
        rows=dict(rows), side_ports=dict(sides),
        endpoint_mode='real_2x16_dual_height',
        fiber_column_pitch_mm=C.FIBER_COLUMN_PITCH_MM,
        fiber_row_pitch_mm=C.FIBER_ROW_PITCH_MM,
        ports_per_connector=C.COLUMNS,
        connectors=64,
        connector_pitch_mm=C.CONNECTOR_PITCH_MM,
        connector_pitch_status=C.CONNECTOR_PITCH_STATUS,
        cross_plane_rule='XY-projected crossings between z1 and z2 are not same-layer conflicts',
        z_transition=C.Z_TRANSITION,
        manufacturing_claim=C.MANUFACTURING_CLAIM,
    )
    return validation


def physical_port_table(topology_or_path=TOPOLOGY_PATHS['V1']):
    """Independent 3D fibre table: 64 connectors x 2 rows x 16 columns."""
    label, path = resolve_topology(topology_or_path)
    rows, sha = read_csv(path)
    table = []
    for connector in connector_records():
        side = connector['side']
        index = int(connector['connector'][1:])
        for row in (1, 2):
            for column in range(1, C.COLUMNS + 1):
                along = port_along_mm(index, column)
                x, y = board_xy(side, along)
                table.append(dict(
                    topology=label, csv_sha256=sha,
                    side=side, connector=connector['connector'], row=row,
                    column=column, channel=(row - 1) * C.COLUMNS + column,
                    plane=C.PLANE_NAME[row], z_mm=C.PLANE_Z_MM[row],
                    x_mm=x, y_mm=y, along_mm=along,
                    face_u_mm=(column - (C.COLUMNS + 1) / 2.0) * C.FIBER_COLUMN_PITCH_MM,
                    face_v_mm=(row - 1.5) * C.FIBER_ROW_PITCH_MM,
                ))
    return table


def all_routes(topology_or_path):
    """Union of the two planes: all 1024 CSV routes with plane tags."""
    routes = []
    for plane in PLANES:
        plane_routes, _endpoints, _connectors, _validation = load_plane(
            topology_or_path, plane)
        routes.extend(plane_routes)
    if len(routes) != 1024 or len({route['route_id'] for route in routes}) != 1024:
        raise ValueError('the two planes must partition the 1024 CSV identities')
    return routes
