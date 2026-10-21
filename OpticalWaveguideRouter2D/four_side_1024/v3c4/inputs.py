"""V3-C4 topology loader: CSV -> fslw/v2opt-compatible plane records + rotation groups."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from ..fslw import config as C
from ..fslw import ports as FSLW_PORTS
from ..legacy_geometry import transform_primitives

ROOT = Path(__file__).resolve().parents[2]          # .../OpticalWaveguideRouter2D
CONNECTIVITY_DIR = ROOT / 'outputs/four_side_1024_v3_c4_connectivity'
V3_CSV = CONNECTIVITY_DIR / 'optical_1024_multitomulti_connectivity_v3_c4_symmetric.csv'
EXPECTED_V3_SHA256 = 'de7e382d3fbf94033eb323ccc64914739e14bde5793191389341896b717f0430'
ROUTING_ROOT = ROOT / 'outputs/four_side_1024_v3_c4_routing'
TOPOLOGY = 'V3_C4'
PLANES = ('z1', 'z2')

#: rot90 about the board centre (75,75): (x,y) -> (150-y, x)
ROT90 = dict(matrix=[[0.0, -1.0], [1.0, 0.0]], offset=[150.0, 0.0],
             reflected=False, source_side=None, target_side=None, name='rot90')

TOL = 1e-6

ROT90_PORT = {}          # endpoint_id -> rot90(endpoint_id)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv_rows(path=V3_CSV):
    raw = Path(path).read_bytes()
    rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    return rows, hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# port model (authoritative: four_side_1024.fslw.ports.build_plane_endpoints)
# ---------------------------------------------------------------------------
def build_all_endpoints():
    """All 2048 physical ports keyed by fslw endpoint id ('N01:1:1')."""
    endpoints = FSLW_PORTS.build_plane_endpoints()
    coord_index = {}
    for eid, ep in endpoints.items():
        x, y = ep['routing_xy']
        key = (round(float(x), 6), round(float(y), 6), float(ep['z_mm']))
        if key in coord_index:
            raise ValueError(f'duplicate endpoint coordinate {key}')
        coord_index[key] = eid
    return endpoints, coord_index


ENDPOINTS, COORD_INDEX = build_all_endpoints()


def _coord_index_for_plane(plane):
    return {k: v for k, v in COORD_INDEX.items()
            if float(ENDPOINTS[v]['z_mm']) == (C.PLANE_Z_MM[1] if plane == 'z1'
                                              else C.PLANE_Z_MM[2])}


def rot90_endpoint(eid):
    """Rotate one endpoint identity by 90 deg CCW about (75,75)."""
    ep = ENDPOINTS[eid]
    x, y = ep['routing_xy']
    key = (round(150.0 - float(y), 6), round(float(x), 6), float(ep['z_mm']))
    return COORD_INDEX[key]


for _eid in ENDPOINTS:
    ROT90_PORT[_eid] = rot90_endpoint(_eid)


def rot90_connection(conn):
    return frozenset(rot90_endpoint(eid) for eid in conn)


# ---------------------------------------------------------------------------
# plane loading (same record shape as fslw.ports.load_plane)
# ---------------------------------------------------------------------------
def _route_record(raw):
    rec = dict(raw)
    for field in ('route_id', 'source_row', 'source_column', 'source_channel',
                  'target_row', 'target_column', 'target_channel'):
        rec[field] = int(rec[field])
    rec['source_endpoint'] = f"{rec['source_connector']}:{rec['source_row']}:{rec['source_column']}"
    rec['target_endpoint'] = f"{rec['target_connector']}:{rec['target_row']}:{rec['target_column']}"
    sides = {rec['source_side'], rec['target_side']}
    rec['pair'] = ''.join(sorted(sides))
    rec['relation'] = 'opposite' if sides in ({'N', 'S'}, {'E', 'W'}) else 'adjacent'
    rec['plane'] = C.PLANE_NAME[rec['source_row']]
    rec['z_mm'] = C.PLANE_Z_MM[rec['source_row']]
    rec['row'] = rec['source_row']
    return rec


def load_all_routes():
    rows, sha = read_csv_rows()
    if sha != EXPECTED_V3_SHA256:
        raise ValueError(f'V3 connectivity CSV SHA256 mismatch: {sha}')
    routes = [_route_record(row) for row in rows]
    routes.sort(key=lambda r: r['route_id'])
    if len(routes) != 1024 or [r['route_id'] for r in routes] != list(range(1, 1025)):
        raise ValueError('V3 connectivity CSV must contain route_id 1..1024')
    return routes, sha


def load_plane(plane):
    """Return ``(routes, endpoints, connectors, validation)`` for one z plane."""
    if plane not in PLANES:
        raise ValueError(f'plane must be one of {PLANES}')
    routes_all, sha = load_all_routes()
    row_number = C.PLANE_ROW[plane]
    routes = [r for r in routes_all if r['source_row'] == row_number]
    if len(routes) != 512:
        raise ValueError(f'plane {plane} must hold 512 connections')
    endpoints = {eid: ep for eid, ep in ENDPOINTS.items() if ep['plane'] == plane}
    # structural checks (mirror of fslw.ports.validate_plane)
    usage = {}
    pairs, relations, sides = {}, {}, {}
    for r in routes:
        for eid in (r['source_endpoint'], r['target_endpoint']):
            usage[eid] = usage.get(eid, 0) + 1
        pairs[r['pair']] = pairs.get(r['pair'], 0) + 1
        relations[r['relation']] = relations.get(r['relation'], 0) + 1
        sides[r['source_side']] = sides.get(r['source_side'], 0) + 1
    issues = []
    if len(usage) != 1024 or set(usage.values()) != {1}:
        issues.append(f'ports used {len(usage)} unique')
    if set(usage) != set(endpoints):
        issues.append('port identity set mismatch')
    expected = {'z1': {'opposite': 512}, 'z2': {'adjacent': 512}}[plane]
    if relations != expected:
        issues.append(f'relations {relations} != {expected}')
    if any(r['source_row'] != r['target_row'] or r['source_row'] != row_number
           for r in routes):
        issues.append('row mismatch')
    if any(r['source_side'] == r['target_side'] for r in routes):
        issues.append('same-side connection')
    validation = dict(
        passed=not issues, issues=issues, topology=TOPOLOGY, csv_path=str(V3_CSV),
        csv_sha256=sha, plane=plane, plane_row=row_number,
        z_mm=C.PLANE_Z_MM[row_number], port_model=C.PORT_MODEL,
        connections=len(routes), ports=len(endpoints), ports_used_once=True,
        relations=relations, pairs=pairs, side_ports=sides,
        endpoint_mode='real_2x16_dual_height',
        fiber_column_pitch_mm=C.FIBER_COLUMN_PITCH_MM,
        fiber_row_pitch_mm=C.FIBER_ROW_PITCH_MM,
        connector_pitch_mm=C.CONNECTOR_PITCH_MM,
        connector_pitch_status=C.CONNECTOR_PITCH_STATUS,
        cross_plane_rule='XY-projected crossings between z1 and z2 are not same-layer conflicts',
        z_transition=C.Z_TRANSITION, manufacturing_claim=C.MANUFACTURING_CLAIM,
    )
    return routes, endpoints, FSLW_PORTS.connector_records(), validation


# ---------------------------------------------------------------------------
# geometry helpers: rotation / reversal of primitive chains
# ---------------------------------------------------------------------------
def rotate_primitives(primitives, times=1):
    """Rotate a primitive chain by ``times`` x 90 deg CCW about (75,75)."""
    result = primitives
    for _ in range(int(times) % 4):
        result = transform_primitives(result, ROT90, inverse=False)
    return result


def reverse_primitives(primitives):
    """Reverse the traversal direction of a primitive chain."""
    result = []
    for prim in reversed(primitives):
        mapped = dict(prim)
        mapped['p0'] = list(prim['p1'])
        mapped['p1'] = list(prim['p0'])
        if prim.get('kind') == 'arc':
            mapped['start_angle'] = float(prim['start_angle']) + float(prim['sweep'])
            mapped['sweep'] = -float(prim['sweep'])
        result.append(mapped)
    return result


def port_xy(eid):
    return tuple(float(v) for v in ENDPOINTS[eid]['routing_xy'])


def orient_primitives(primitives, source_endpoint, target_endpoint):
    """Return ``(oriented_primitives, reversed)`` matching the CSV route orientation."""
    sx, sy = port_xy(source_endpoint)
    tx, ty = port_xy(target_endpoint)
    p0 = primitives[0]['p0']
    p1 = primitives[-1]['p1']
    forward = (abs(p0[0] - sx) <= TOL and abs(p0[1] - sy) <= TOL
               and abs(p1[0] - tx) <= TOL and abs(p1[1] - ty) <= TOL)
    backward = (abs(p1[0] - sx) <= TOL and abs(p1[1] - sy) <= TOL
                and abs(p0[0] - tx) <= TOL and abs(p0[1] - ty) <= TOL)
    if forward and not backward:
        return primitives, False
    if backward and not forward:
        return reverse_primitives(primitives), True
    raise ValueError(f'rotated geometry does not match route endpoints '
                     f'({p0}->{p1} vs {source_endpoint}->{target_endpoint})')


# ---------------------------------------------------------------------------
# C4 rotation groups
# ---------------------------------------------------------------------------
def build_groups(routes_all=None):
    """Partition the 1024 connections into 256 four-member rotation orbits.

    Returns ``(groups, route_group)`` where every group is::

        dict(group_id, plane, kind, route_ids=[phase0,phase1,phase2,phase3],
             pair='NS', phases=[(route_id, reverse_flag), ...])
    """
    routes_all = routes_all or load_all_routes()[0]
    by_conn = {}
    for route in routes_all:
        conn = frozenset((route['source_endpoint'], route['target_endpoint']))
        if conn in by_conn:
            raise ValueError(f'duplicate unordered connection {sorted(conn)}')
        by_conn[conn] = route
    groups = []
    route_group = {}
    for route in routes_all:
        if route['route_id'] in route_group:
            continue
        orbit = [route]
        cur = route
        for _ in range(3):
            rotated = rot90_connection(
                frozenset((cur['source_endpoint'], cur['target_endpoint'])))
            nxt = by_conn.get(rotated)
            if nxt is None:
                raise ValueError(f'connection {route["route_id"]} has no rotation partner')
            orbit.append(nxt)
            cur = nxt
        if rot90_connection(frozenset((cur['source_endpoint'], cur['target_endpoint']))) != \
                frozenset((route['source_endpoint'], route['target_endpoint'])):
            raise ValueError(f'connection {route["route_id"]} rotation orbit does not close')
        gid = len(groups) + 1
        group = dict(group_id=gid, plane=route['plane'],
                     kind='opposite' if route['relation'] == 'opposite' else 'adjacent',
                     route_ids=[r['route_id'] for r in orbit],
                     pair=route['pair'])
        groups.append(group)
        for phase, member in enumerate(orbit):
            route_group[member['route_id']] = (gid, phase)
    if len(groups) != 256:
        raise ValueError(f'expected 256 rotation groups, got {len(groups)}')
    return groups, route_group


def group_planes(groups):
    planes = {}
    for group in groups:
        planes.setdefault(group['plane'], []).append(group)
    return planes


# ---------------------------------------------------------------------------
# payload helpers
# ---------------------------------------------------------------------------
def build_rot90_map():
    return dict(ROT90_PORT)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(path)
    return path
