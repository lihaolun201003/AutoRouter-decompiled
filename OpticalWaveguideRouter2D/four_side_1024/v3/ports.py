"""V3 dual-height port loader: row -> plane, mixed relation classes allowed.

Differences from the previous round's ``fslw/ports.py``:

* same-side connections (relation ``same``, pair NN/SS/EE/WW) are legal; only a
  connector connected to itself is rejected (the frozen CSV has none),
* the relation is taken from the CSV column, never inferred from the row number,
* every plane contains all three classes: z1 = 222 same / 196 opposite / 94 adjacent
  and z2 = 226 / 188 / 98 (512 connections, 1024 ports per plane).

The physical interface model (IEC 2x16 MPO, 64 connectors x 32 fibres, row 1 -> z1,
row 2 -> z2, 0.25 mm column pitch, 9 mm provisional connector pitch) is inherited
unchanged from :mod:`four_side_1024.fslw.ports`.
"""
from __future__ import annotations

from collections import Counter

from ..fslw import ports as FSLW_PORTS
from . import config as C
from . import inputs

SIDES = 'NSEW'


def connector_records():
    return FSLW_PORTS.connector_records()


def build_endpoints():
    return FSLW_PORTS.build_plane_endpoints()


def load_plane(plane):
    """Load one V3 plane: ``(routes, endpoints, connectors, validation)``."""
    if plane not in C.PLANES:
        raise ValueError(f'plane must be one of {C.PLANES}')
    all_connections, topology_validation = inputs.load_all()
    row_number = C.PLANE_ROW[plane]
    all_endpoints = build_endpoints()
    endpoints = {key: value for key, value in all_endpoints.items()
                 if value['plane'] == plane}
    routes = []
    issues = []
    for record in all_connections:
        if record['plane'] != plane:
            continue
        if record['source_row'] != row_number or record['target_row'] != row_number:
            issues.append(f'route {record["route_id"]} wrong row for {plane}')
        for role in ('source', 'target'):
            if record[f'{role}_endpoint'] not in endpoints:
                issues.append(f'route {record["route_id"]} {role} port not in {plane}')
        routes.append(record)
    if len(routes) != 512:
        issues.append(f'plane {plane} has {len(routes)} connections, expected 512')
    validation = validate_plane(routes, endpoints, plane, topology_validation)
    validation['issues'] = list(issues) + validation['issues']
    validation['passed'] = not validation['issues']
    return routes, endpoints, connector_records(), validation


def validate_plane(routes, endpoints, plane, topology_validation):
    issues = []
    expected = C.EXPECTED['planes'][plane]
    if len(routes) != expected['total']:
        issues.append(f'route count {len(routes)}')
    route_ids = [record['route_id'] for record in routes]
    if len(set(route_ids)) != len(route_ids):
        issues.append('duplicate route_id')
    usage = Counter()
    relations = Counter()
    pairs = Counter()
    sides = Counter()
    rows = Counter()
    for record in routes:
        if record['plane'] != plane:
            issues.append(f'route {record["route_id"]} plane mismatch')
        if record['source_side'] == record['target_side']:
            if record['source_connector'] == record['target_connector']:
                issues.append(f'route {record["route_id"]} same-side self connection')
        if record['relation'] not in C.RELATIONS:
            issues.append(f'route {record["route_id"]} illegal relation')
        usage[record['source_endpoint']] += 1
        usage[record['target_endpoint']] += 1
        relations[record['relation']] += 1
        pairs[record['pair']] += 1
        sides[record['source_side']] += 1
        rows[record['source_row']] += 1
    if len(usage) != 1024 or set(usage.values()) != {1}:
        issues.append(f'ports used {len(usage)} unique, counts {set(usage.values())}')
    if set(usage) != set(endpoints):
        issues.append('port identity set mismatch')
    for relation in C.RELATIONS:
        if relations[relation] != expected[relation]:
            issues.append(f'relation {relation} {relations[relation]} != {expected[relation]}')
    return dict(
        passed=not issues, issues=issues, topology=C.TOPOLOGY, plane=plane,
        plane_row=C.PLANE_ROW[plane], z_mm=C.PLANE_Z_MM[C.PLANE_ROW[plane]],
        port_model=C.PORT_MODEL, connections=len(routes), ports=len(endpoints),
        ports_used_once=True, relations=dict(relations), pairs=dict(pairs),
        sides=dict(sides), rows=dict(rows),
        expected=expected,
        csv_sha256=topology_validation['csv_sha256'],
        csv_sha256_match=topology_validation['csv_sha256_match'],
        xlsx_sha256=topology_validation['excel']['xlsx_sha256'],
        endpoint_mode='real_2x16_dual_height',
        fiber_column_pitch_mm=C.FIBER_COLUMN_PITCH_MM,
        fiber_row_pitch_mm=C.FIBER_ROW_PITCH_MM,
        connector_pitch_mm=C.CONNECTOR_PITCH_MM,
        connector_pitch_status=C.CONNECTOR_PITCH_STATUS,
        relation_source='CSV relation column (verified against the sides)',
        cross_plane_rule='XY-projected crossings between z1 and z2 are not same-layer conflicts',
        z_transition=C.Z_TRANSITION,
        manufacturing_claim=C.MANUFACTURING_CLAIM,
    )


def all_routes():
    routes = []
    for plane in C.PLANES:
        plane_routes, _endpoints, _connectors, _validation = load_plane(plane)
        routes.extend(plane_routes)
    if len(routes) != 1024 or len({record['route_id'] for record in routes}) != 1024:
        raise ValueError('the two planes must partition the 1024 CSV identities')
    return routes


def physical_port_table():
    """All 2048 physical ports with 3D coordinates and the V3 plane tags."""
    table = []
    for endpoint in build_endpoints().values():
        table.append(dict(
            endpoint_id=endpoint['endpoint_id'], side=endpoint['side'],
            connector=endpoint['connector'], row=endpoint['row'],
            column=endpoint['column'], channel=endpoint['channel'],
            plane=endpoint['plane'], z_mm=endpoint['z_mm'],
            x_mm=endpoint['routing_xy'][0], y_mm=endpoint['routing_xy'][1],
            along_mm=endpoint['physical_along_mm'],
            face_u_mm=endpoint['physical_face_u_mm'],
            face_v_mm=endpoint['physical_face_v_mm'],
        ))
    return table
