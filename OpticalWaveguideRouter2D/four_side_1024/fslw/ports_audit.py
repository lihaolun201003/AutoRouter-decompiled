"""Independent audit of the FSLW dual-height real 2x16 MPO port model.

Owner: connectivity (``four_side_1024/fslw/SPEC.md`` §2, §9, §11).

This module is a *deliberately independent* re-derivation of the new interface
model.  It does **not** import ``four_side_1024/fslw/ports.py`` (Lead) and does
not import the previous-round ``four_side_1024/inputs.py``: everything is
derived from

* the immutable connectivity CSVs (``route_id`` / side / connector / row /
  column / channel / relation only), and
* the IEC 61754-7-3:2019 2x16 MPO pitches (same-row 0.25 mm, row-to-row
  0.5 mm) plus the 150 mm board / 16-connectors-per-side / 9 mm connector pitch
  convention of ``fslw/SPEC.md``.

Derivation (FSLW SPEC §2)
-------------------------
* 16 connectors per side, evenly pitched at 9 mm on a 150 mm board:
  ``connector_center(c) = (150 - 15*9)/2 + (c-1)*9 = 7.5 + (c-1)*9`` mm.
* Dual-height assumption: CSV ``row = 1`` lives on plane ``z1 = 0.0 mm`` and
  carries exactly the 512 opposite connections (NS 256 + EW 256);
  CSV ``row = 2`` lives on plane ``z2 = 0.5 mm`` and carries exactly the
  512 adjacent connections (EN/ES/SW/NW 128 each).
* Per plane, each connector contributes its own 16 columns:
  ``along = connector_center + (column - 8.5) * 0.25`` mm.
  A plane therefore has 4 sides x 16 connectors x 16 columns = 1024 real ports,
  used exactly once each by that plane's 512 connections.
* 2D routing coordinate of a port = its edge point with ``z`` dropped:
  N -> (along, 150), S -> (along, 0), E -> (150, along), W -> (0, along).
* Real physical 3D coordinate = (x, y, z) with
  ``z = z1`` for row 1 and ``z = z2`` for row 2; these 2048 coordinates are
  saved independently from the 2D routing coordinates.
* No z transition (via/taper/fanout) is implemented; the two planes are
  independent 2D ``layer=0`` routing problems.  Cross-plane XY projections are
  therefore **not** same-layer conflicts.

Run ``python -m four_side_1024.fslw.ports_audit`` from ``OpticalWaveguideRouter2D``
to rebuild every artifact under
``outputs/four_side_1024_fslw_R40_gap30_abcd/connectivity/``.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ''):  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

__all__ = [
    'BOARD_MM', 'CONNECTORS_PER_SIDE', 'COLUMNS', 'ROWS', 'CHANNELS_PER_CONNECTOR',
    'CONNECTOR_PITCH_MM', 'FIBER_COLUMN_PITCH_MM', 'FIBER_ROW_PITCH_MM',
    'CONNECTOR_ENVELOPE_WIDTH_MM', 'PLANE_Z_MM', 'PLANE_NAME', 'PLANE_ROW',
    'PORT_MODEL', 'MODEL', 'V1_CSV', 'V2_CSV', 'V1_SHA256', 'V2_SHA256',
    'OUTPUT_DIR', 'derive_ports', 'validate_dual_height', 'physical_port_rows',
    'write_physical_ports_csv', 'write_validation_json', 'plot_plane_connectivity',
    'plot_dual_height_schematic', 'compare_with_lead_ports', 'build_all',
]

# ---------------------------------------------------------------------------
# Model constants -- independently derived from IEC 61754-7-3:2019 + SPEC §1/§2
# (NOT imported from fslw/ports.py; cross-checked against fslw/config.py below).
# ---------------------------------------------------------------------------
BOARD_MM = 150.0
SIDES = 'NSEW'
CONNECTORS_PER_SIDE = 16
COLUMNS = 16
ROWS = 2
CHANNELS_PER_CONNECTOR = ROWS * COLUMNS  # 32
CONNECTOR_PITCH_MM = 9.0
FIBER_COLUMN_PITCH_MM = 0.25   # IEC 61754-7-3:2019 same-row pitch
FIBER_ROW_PITCH_MM = 0.50      # IEC 61754-7-3:2019 row-to-row pitch
CONNECTOR_ENVELOPE_WIDTH_MM = 12.59  # provisional MPO housing envelope (round 1)
FIRST_CONNECTOR_CENTER_MM = (BOARD_MM - (CONNECTORS_PER_SIDE - 1) * CONNECTOR_PITCH_MM) / 2.0
PLANE_Z_MM = {1: 0.0, 2: 0.5}  # row -> model z height
PLANE_NAME = {1: 'z1', 2: 'z2'}
PLANE_ROW = {'z1': 1, 'z2': 2}
PORT_MODEL = 'real_2x16_dual_height'
TOL_MM = 1e-9
MATCH_TOL_MM = 1e-6

CODE_DIR = Path(__file__).resolve().parents[2]  # .../OpticalWaveguideRouter2D
OUTPUT_DIR = (CODE_DIR / 'outputs' / 'four_side_1024_fslw_R40_gap30_abcd'
              / 'connectivity')
PREVIOUS_ROUND_ENDPOINTS = (CODE_DIR / 'outputs' / 'four_side_1024_legacy_input_v1'
                            / 'endpoints.json')

# The two input topologies are the frozen CSVs of the previous round (SPEC §0/§1
# of abcd; the FSLW round reuses exactly the same pairing, only the port model
# changes -- SPEC §9 "CSV 原有配对与 route_id 一律不改").
V1_CSV = Path(r'C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v1.csv')
V2_CSV = Path(r'C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v2_symmetric.csv')
V1_SHA256 = '0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b'
V2_SHA256 = '49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e'

EXPECTED = dict(
    connections=1024,
    opposite=512,
    adjacent=512,
    pair_counts={'NS': 256, 'EW': 256, 'EN': 128, 'ES': 128, 'SW': 128, 'NW': 128},
    planes={'z1': 512, 'z2': 512},
    plane_relations={'z1': 'opposite', 'z2': 'adjacent'},
    plane_ports=1024,
    plane_connections=512,
    connectors=64,
    fibers_per_connector=32,
    physical_ports=2048,
)

MODEL = dict(
    port_model=PORT_MODEL,
    interface_standard='IEC 61754-7-3:2019 2x16 MPO',
    board_mm=[BOARD_MM, BOARD_MM],
    sides_per_board=4,
    connectors_per_side=CONNECTORS_PER_SIDE,
    connector_pitch_mm=CONNECTOR_PITCH_MM,
    first_connector_center_mm=FIRST_CONNECTOR_CENTER_MM,
    fiber_column_pitch_mm=FIBER_COLUMN_PITCH_MM,
    fiber_row_pitch_mm=FIBER_ROW_PITCH_MM,
    rows=ROWS,
    columns=COLUMNS,
    channels_per_connector=CHANNELS_PER_CONNECTOR,
    plane_z_mm={str(row): z for row, z in PLANE_Z_MM.items()},
    plane_row=dict(PLANE_ROW),
    plane_rule='CSV row=1 -> z1 (512 opposite); CSV row=2 -> z2 (512 adjacent)',
    along_formula='along = connector_center + (column - 8.5) * 0.25',
    routing_xy_definition='edge point with z dropped (N:(along,150), S:(along,0), '
                          'E:(150,along), W:(0,along))',
    physical_3d_definition='(x, y, z) with z = z1 for row 1, z2 for row 2',
    z_transition='not_implemented',
    layer='0 (independent 2D plane)',
    cross_plane_rule='cross-plane XY projections are NOT same-layer conflicts',
    manufacturing_claim=('simulation under the two-height interface assumption; glass '
                         'thickness and connector mounting direction are not confirmed, '
                         'no z transition implemented, not a claim of manufacturability'),
)

# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------
def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def detect_topology(csv_path, csv_sha256=None) -> str:
    path = Path(csv_path)
    digest = csv_sha256 or sha256_file(path)
    if digest == V1_SHA256:
        return 'V1'
    if digest == V2_SHA256:
        return 'V2'
    name = path.name.lower()
    if 'v2' in name or 'symmetric' in name:
        return 'V2'
    if 'v1' in name:
        return 'V1'
    return 'UNKNOWN'


def connector_number(connector) -> int:
    """'N07' -> 7 (connector index 1..16)."""
    name = str(connector)
    if not name[1:].isdigit():
        raise ValueError(f'ill-formed connector {connector!r}')
    return int(name[1:])


def connector_center_mm(connector) -> float:
    """Centre of a connector along its board edge (evenly pitched 9 mm)."""
    return FIRST_CONNECTOR_CENTER_MM + (connector_number(connector) - 1) * CONNECTOR_PITCH_MM


def port_along_mm(connector, column) -> float:
    """IEC 2x16 column position along the edge: centre + (col - 8.5) * 0.25 mm."""
    return connector_center_mm(connector) + (int(column) - (COLUMNS + 1) / 2.0) * FIBER_COLUMN_PITCH_MM


def plane_of_row(row) -> str:
    return PLANE_NAME[int(row)]


def z_of_row(row) -> float:
    return PLANE_Z_MM[int(row)]


def edge_xy(side, along) -> list:
    """Edge point on the board boundary (z dropped)."""
    if side == 'N':
        return [float(along), BOARD_MM]
    if side == 'S':
        return [float(along), 0.0]
    if side == 'E':
        return [BOARD_MM, float(along)]
    if side == 'W':
        return [0.0, float(along)]
    raise ValueError(f'unknown side {side!r}')


def inward_vector(side) -> list:
    return {'N': [0.0, -1.0], 'S': [0.0, 1.0],
            'E': [-1.0, 0.0], 'W': [1.0, 0.0]}[side]


def endpoint_id(connector, row, column) -> str:
    return f'{connector}:{int(row)}:{int(column)}'


def read_connectivity_csv(path) -> list:
    """Read a frozen connectivity CSV (own parser -- no abcd/inputs import)."""
    raw = Path(path).read_bytes()
    rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    required = ['route_id', 'source_side', 'source_connector', 'source_row',
                'source_column', 'source_channel', 'target_side', 'target_connector',
                'target_row', 'target_column', 'target_channel', 'relation']
    out = []
    for line_number, row in enumerate(rows, start=2):
        missing = [field for field in required if field not in row]
        if missing:
            raise ValueError(f'{path}: missing CSV fields {missing}')
        record = {}
        for field in required:
            value = row[field]
            record[field] = value if field in ('source_side', 'source_connector',
                                               'target_side', 'target_connector',
                                               'relation') else int(value)
        out.append(record)
    return out


def pair_label(side_a, side_b) -> str:
    return ''.join(sorted((str(side_a), str(side_b))))


def _relation_from_sides(side_a, side_b):
    pair = pair_label(side_a, side_b)
    return ('opposite' if pair in ('NS', 'EW') else 'adjacent'), pair


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Counter):
        return _jsonable(dict(obj))
    if isinstance(obj, (set, frozenset)):
        return sorted(_jsonable(v) for v in obj)
    return obj


# ---------------------------------------------------------------------------
# Independent port model derivation
# ---------------------------------------------------------------------------
def physical_port_rows(topology=None, csv_path=None) -> list:
    """All 2048 real 3D physical ports (64 connectors x 32 fibers).

    The 2048 physical ports depend only on the interface model, not on the
    connectivity topology; every row is tagged with the topology for provenance.
    """
    topology = topology or detect_topology(csv_path or V1_CSV)
    rows = []
    for side in SIDES:
        for number in range(1, CONNECTORS_PER_SIDE + 1):
            connector = f'{side}{number:02d}'
            center = connector_center_mm(connector)
            for row in (1, 2):
                z = z_of_row(row)
                for column in range(1, COLUMNS + 1):
                    channel = (row - 1) * COLUMNS + column
                    along = port_along_mm(connector, column)
                    x, y = edge_xy(side, along)
                    inward = inward_vector(side)
                    rows.append(dict(
                        topology=topology,
                        side=side,
                        connector=connector,
                        row=row,
                        column=column,
                        channel=channel,
                        plane=plane_of_row(row),
                        plane_row=row,
                        x_mm=x,
                        y_mm=y,
                        z_mm=z,
                        along_mm=along,
                        connector_center_mm=center,
                        inward_x=inward[0],
                        inward_y=inward[1],
                        port_model=PORT_MODEL,
                    ))
    return rows


def derive_ports(csv_path=None) -> dict:
    """Derive the full dual-height port model + routes for one topology CSV."""
    path = Path(csv_path or V1_CSV)
    raw_rows = read_connectivity_csv(path)
    topology = detect_topology(path)
    sha = sha256_file(path)

    routes, endpoints = [], {}
    for record in raw_rows:
        route = dict(record)
        route['pair'] = pair_label(record['source_side'], record['target_side'])
        route['relation'] = record['relation']
        row = int(record['source_row'])
        route['plane'] = plane_of_row(row)
        route['row'] = row
        route['z_mm'] = z_of_row(row)
        for role in ('source', 'target'):
            connector = str(record[f'{role}_connector'])
            side = str(record[f'{role}_side'])
            row_role = int(record[f'{role}_row'])
            column = int(record[f'{role}_column'])
            channel = int(record[f'{role}_channel'])
            eid = endpoint_id(connector, row_role, column)
            along = port_along_mm(connector, column)
            x, y = edge_xy(side, along)
            endpoints[eid] = dict(
                endpoint_id=eid,
                connector=connector,
                side=side,
                row=row_role,
                column=column,
                channel=channel,
                routing_xy=[x, y],
                inward=inward_vector(side),
                layer=0,
                plane=plane_of_row(row_role),
                z_mm=z_of_row(row_role),
                physical_along_mm=along,
                physical_row_z_mm=z_of_row(row_role),
                physical_xy=[x, y],
                connector_center_mm=connector_center_mm(connector),
                port_model=PORT_MODEL,
            )
            route[f'{role}_endpoint'] = eid
        routes.append(route)

    connectors = []
    for side in SIDES:
        for number in range(1, CONNECTORS_PER_SIDE + 1):
            connector = f'{side}{number:02d}'
            center = connector_center_mm(connector)
            connectors.append(dict(
                connector=connector,
                side=side,
                number=number,
                center_xy=edge_xy(side, center),
                along_center_mm=center,
                columns=COLUMNS,
                rows=ROWS,
                channels=CHANNELS_PER_CONNECTOR,
                envelope_width_mm=CONNECTOR_ENVELOPE_WIDTH_MM,
                fiber_span_mm=(COLUMNS - 1) * FIBER_COLUMN_PITCH_MM,
                port_model=PORT_MODEL,
            ))

    physical_ports = physical_port_rows(topology=topology)
    validation = validate_dual_height(routes, endpoints, connectors, physical_ports,
                                      topology=topology, csv_path=path, csv_sha256=sha)
    return dict(topology=topology, csv_path=str(path.resolve()), csv_sha256=sha,
                routes=routes, endpoints=endpoints, connectors=connectors,
                physical_ports=physical_ports, validation=validation)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _configuration_crosscheck() -> dict:
    """Compare our independent constants with fslw/config.py (Lead) if importable."""
    result = dict(config_module_available=False, mismatches=[])
    try:
        from four_side_1024.fslw import config as lead_config  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - config.py is expected to exist
        result['error'] = f'{type(exc).__name__}: {exc}'
        return result
    result['config_module_available'] = True
    comparisons = {
        'BOARD_MM': (BOARD_MM, getattr(lead_config, 'BOARD_MM', None)),
        'CONNECTORS_PER_SIDE': (CONNECTORS_PER_SIDE,
                                getattr(lead_config, 'CONNECTORS_PER_SIDE', None)),
        'COLUMNS': (COLUMNS, getattr(lead_config, 'COLUMNS', None)),
        'ROWS': (ROWS, getattr(lead_config, 'ROWS', None)),
        'CONNECTOR_PITCH_MM': (CONNECTOR_PITCH_MM,
                               getattr(lead_config, 'CONNECTOR_PITCH_MM', None)),
        'FIBER_COLUMN_PITCH_MM': (FIBER_COLUMN_PITCH_MM,
                                  getattr(lead_config, 'FIBER_COLUMN_PITCH_MM', None)),
        'FIBER_ROW_PITCH_MM': (FIBER_ROW_PITCH_MM,
                               getattr(lead_config, 'FIBER_ROW_PITCH_MM', None)),
        'CONNECTOR_ENVELOPE_WIDTH_MM': (
            CONNECTOR_ENVELOPE_WIDTH_MM,
            getattr(lead_config, 'ENVELOPE_WIDTH_MM', None)),
        'PLANE_Z_MM': (PLANE_Z_MM, getattr(lead_config, 'PLANE_Z_MM', None)),
        'PORT_MODEL': (PORT_MODEL, getattr(lead_config, 'PORT_MODEL', None)),
    }
    for name, (mine, theirs) in comparisons.items():
        if theirs is None or theirs != mine:
            result['mismatches'].append(dict(constant=name, independent=mine, lead=theirs))
    return result


def validate_dual_height(routes, endpoints, connectors, physical_ports,
                         topology=None, csv_path=None, csv_sha256=None) -> dict:
    """Full independent audit of the dual-height port model for one topology."""
    checks, failed = {}, []

    def record(name, passed, **info):
        checks[name] = dict(passed=bool(passed), **info)
        if not passed:
            failed.append(name)

    routes = list(routes)
    connections = len(routes)
    record('connections', connections == EXPECTED['connections'],
           observed=connections, expected=EXPECTED['connections'])

    # ---- CSV identity / relation / row rules ------------------------------
    route_ids = [int(r['route_id']) for r in routes]
    record('route_ids', sorted(route_ids) == list(range(1, EXPECTED['connections'] + 1)),
           unique=len(set(route_ids)), min=min(route_ids), max=max(route_ids))
    same_side, relation_counts, pair_counts = [], Counter(), Counter()
    relation_label_violations, row_rule_violations = [], []
    channel_formula_violations, connector_format_violations = [], []
    role_fields = {}
    for route in routes:
        rid = int(route['route_id'])
        for role in ('source', 'target'):
            connector = str(route[f'{role}_connector'])
            side = str(route[f'{role}_side'])
            row = int(route[f'{role}_row'])
            column = int(route[f'{role}_column'])
            channel = int(route[f'{role}_channel'])
            role_fields[(rid, role)] = (side, connector, row, column, channel)
            if channel != (row - 1) * COLUMNS + column:
                channel_formula_violations.append(dict(route_id=rid, role=role,
                                                       row=row, column=column,
                                                       channel=channel))
            if (connector[:1] != side or not connector[1:].isdigit()
                    or not 1 <= int(connector[1:]) <= CONNECTORS_PER_SIDE
                    or row not in (1, 2) or not 1 <= column <= COLUMNS):
                connector_format_violations.append(dict(route_id=rid, role=role,
                                                        side=side, connector=connector,
                                                        row=row, column=column))
        s_side = role_fields[(rid, 'source')][0]
        t_side = role_fields[(rid, 'target')][0]
        if s_side == t_side:
            same_side.append(rid)
            continue
        relation, pair = _relation_from_sides(s_side, t_side)
        relation_counts[relation] += 1
        pair_counts[pair] += 1
        if str(route['relation']) != relation:
            relation_label_violations.append(dict(route_id=rid,
                                                  declared=route['relation'],
                                                  computed=relation))
        expected_row = 1 if relation == 'opposite' else 2
        s_row = role_fields[(rid, 'source')][2]
        t_row = role_fields[(rid, 'target')][2]
        if not (s_row == t_row == expected_row):
            row_rule_violations.append(dict(route_id=rid, relation=relation,
                                            source_row=s_row, target_row=t_row,
                                            expected_row=expected_row))
    record('different_sides', not same_side, same_side_connections=len(same_side),
           sample=same_side[:5])
    record('relation_counts',
           {k: relation_counts.get(k, 0) for k in ('opposite', 'adjacent')}
           == {k: EXPECTED[k] for k in ('opposite', 'adjacent')},
           observed={**{k: relation_counts.get(k, 0) for k in ('opposite', 'adjacent')},
                     'pairs': {k: pair_counts.get(k, 0) for k in EXPECTED['pair_counts']}},
           expected=dict(opposite=512, adjacent=512))
    record('pair_counts', {k: pair_counts.get(k, 0) for k in EXPECTED['pair_counts']}
           == EXPECTED['pair_counts'],
           observed={k: pair_counts.get(k, 0) for k in EXPECTED['pair_counts']},
           expected=EXPECTED['pair_counts'])
    record('row_rule', not row_rule_violations, violations=len(row_rule_violations),
           sample=row_rule_violations[:5], rule='opposite->row1, adjacent->row2')
    record('relation_label', not relation_label_violations,
           violations=len(relation_label_violations),
           sample=relation_label_violations[:5])
    record('channel_formula', not channel_formula_violations,
           violations=len(channel_formula_violations),
           sample=channel_formula_violations[:5],
           formula='channel = (row-1)*16 + column')
    record('connector_format', not connector_format_violations,
           violations=len(connector_format_violations),
           sample=connector_format_violations[:5])

    # ---- endpoint usage (all 2048 real fibers used once) -------------------
    usage = Counter()
    for route in routes:
        rid = int(route['route_id'])
        for role in ('source', 'target'):
            side, connector, row, column, _channel = role_fields[(rid, role)]
            usage[endpoint_id(connector, row, column)] += 1
    expected_ids = {endpoint_id(f'{side}{number:02d}', row, column)
                    for side in SIDES for number in range(1, CONNECTORS_PER_SIDE + 1)
                    for row in (1, 2) for column in range(1, COLUMNS + 1)}
    record('endpoints_used_once',
           set(usage) == expected_ids and set(usage.values()) == {1},
           distinct=len(usage), expected=len(expected_ids),
           usage_min=min(usage.values()), usage_max=max(usage.values()),
           missing=len(expected_ids - set(usage)),
           extra=len(set(usage) - expected_ids))
    record('endpoints', len(endpoints) == len(expected_ids),
           observed=len(endpoints), expected=len(expected_ids))

    # duplicate connections (unordered endpoint pairs)
    unordered = Counter()
    for route in routes:
        rid = int(route['route_id'])
        a = role_fields[(rid, 'source')]
        b = role_fields[(rid, 'target')]
        unordered[(endpoint_id(a[1], a[2], a[3]), endpoint_id(b[1], b[2], b[3]))
                  if a < b else
                  (endpoint_id(b[1], b[2], b[3]), endpoint_id(a[1], a[2], a[3]))] += 1
    record('no_duplicate_connection', set(unordered.values()) == {1},
           distinct=len(unordered), duplicates=sum(1 for v in unordered.values() if v > 1))

    # ---- per-plane checks --------------------------------------------------
    planes = {}
    for plane, row in PLANE_ROW.items():
        z = z_of_row(row)
        plane_routes = [r for r in routes if int(r['row']) == row]
        plane_relations = Counter(str(r['relation']) for r in plane_routes)
        plane_endpoint_ids = []
        along_errors, xy_errors, inward_errors, height_errors = [], [], [], []
        port_keys = Counter()
        cross_plane_violations = []
        for route in plane_routes:
            rid = int(route['route_id'])
            for role in ('source', 'target'):
                side, connector, role_row, column, channel = role_fields[(rid, role)]
                if role_row != row:
                    cross_plane_violations.append(dict(route_id=rid, role=role,
                                                       row=role_row, plane=plane))
                eid = endpoint_id(connector, role_row, column)
                plane_endpoint_ids.append(eid)
                port_keys[(side, connector, column)] += 1
                along_expected = port_along_mm(connector, column)
                xy_expected = edge_xy(side, along_expected)
                endpoint = endpoints[eid]
                along_errors.append(abs(endpoint['physical_along_mm'] - along_expected))
                xy_errors.append(max(abs(endpoint['routing_xy'][0] - xy_expected[0]),
                                     abs(endpoint['routing_xy'][1] - xy_expected[1])))
                if list(endpoint['inward']) != inward_vector(side):
                    inward_errors.append(eid)
                if (endpoint['plane'] != plane
                        or abs(endpoint['z_mm'] - z) > TOL_MM
                        or abs(endpoint['physical_row_z_mm'] - z) > TOL_MM):
                    height_errors.append(dict(endpoint=eid,
                                              plane=endpoint['plane'],
                                              z_mm=endpoint['z_mm']))
        expected_plane_ports = {(side, f'{side}{number:02d}', column)
                                for side in SIDES
                                for number in range(1, CONNECTORS_PER_SIDE + 1)
                                for column in range(1, COLUMNS + 1)}
        expected_relations = {EXPECTED['plane_relations'][plane]: EXPECTED['plane_connections']}
        records = Counter(str(r['relation']) for r in plane_routes)
        plane_checks = dict(
            connections=len(plane_routes),
            endpoints=len(plane_endpoint_ids),
            distinct_endpoints=len(set(plane_endpoint_ids)),
            port_keys=len(port_keys),
            expected_ports=len(expected_plane_ports),
            ports_missing=len(expected_plane_ports - set(port_keys)),
            ports_duplicated=sum(1 for count in port_keys.values() if count > 1),
            relations={k: records.get(k, 0) for k in ('opposite', 'adjacent')},
            expected_relations=expected_relations,
            row=row,
            z_mm=z,
            along_formula_max_error_mm=max(along_errors) if along_errors else 0.0,
            routing_xy_max_error_mm=max(xy_errors) if xy_errors else 0.0,
            inward_violations=len(inward_errors),
            height_violations=len(height_errors),
            cross_plane_row_violations=len(cross_plane_violations),
            projected_xy_unique=len({tuple(round(v, 9) for v in endpoints[eid]['routing_xy'])
                                     for eid in set(plane_endpoint_ids)}),
        )
        plane_ok = (
            len(plane_routes) == EXPECTED['plane_connections']
            and len(plane_endpoint_ids) == EXPECTED['plane_ports']
            and len(set(plane_endpoint_ids)) == EXPECTED['plane_ports']
            and len(port_keys) == EXPECTED['plane_ports']
            and len(expected_plane_ports - set(port_keys)) == 0
            and all(count == 1 for count in port_keys.values())
            and records.get(EXPECTED['plane_relations'][plane]) == EXPECTED['plane_connections']
            and plane_checks['along_formula_max_error_mm'] <= TOL_MM
            and plane_checks['routing_xy_max_error_mm'] <= TOL_MM
            and not inward_errors and not height_errors and not cross_plane_violations
        )
        planes[plane] = dict(passed=plane_ok, **plane_checks)
        record(f'plane_{plane}', plane_ok, **plane_checks)

    # ---- physical 3D ports -------------------------------------------------
    physical_ports = list(physical_ports)
    port_ids = Counter((p['connector'], p['row'], p['column']) for p in physical_ports)
    expected_port_ids = {(f'{side}{number:02d}', row, column)
                         for side in SIDES for number in range(1, CONNECTORS_PER_SIDE + 1)
                         for row in (1, 2) for column in range(1, COLUMNS + 1)}
    coord_errors, channel_errors, z_errors, bounds_errors = [], [], [], []
    max_coordinate_error = 0.0
    for port in physical_ports:
        side, connector = port['side'], port['connector']
        row, column, channel = port['row'], port['column'], port['channel']
        along = port_along_mm(connector, column)
        x, y = edge_xy(side, along)
        z = z_of_row(row)
        coordinate_error = max(abs(port['along_mm'] - along), abs(port['x_mm'] - x),
                               abs(port['y_mm'] - y))
        max_coordinate_error = max(max_coordinate_error, coordinate_error)
        if coordinate_error > TOL_MM:
            coord_errors.append(port)
        if channel != (row - 1) * COLUMNS + column:
            channel_errors.append(port)
        if abs(port['z_mm'] - z) > TOL_MM or port['plane'] != plane_of_row(row):
            z_errors.append(port)
        if not (0.0 <= port['x_mm'] <= BOARD_MM and 0.0 <= port['y_mm'] <= BOARD_MM):
            bounds_errors.append(port)
    projected = Counter((round(p['x_mm'], 9), round(p['y_mm'], 9)) for p in physical_ports)
    unique_3d = len({(round(p['x_mm'], 9), round(p['y_mm'], 9), round(p['z_mm'], 9))
                     for p in physical_ports})
    record('physical_ports_count', len(physical_ports) == EXPECTED['physical_ports'],
           observed=len(physical_ports), expected=EXPECTED['physical_ports'])
    record('physical_port_identities',
           set(port_ids) == expected_port_ids and set(port_ids.values()) == {1},
           distinct=len(port_ids), expected=len(expected_port_ids),
           duplicates=sum(1 for v in port_ids.values() if v > 1))
    record('physical_coordinates', not coord_errors and not channel_errors
           and not z_errors and not bounds_errors
           and max_coordinate_error <= TOL_MM,
           max_coordinate_error_mm=max_coordinate_error,
           channel_formula_violations=len(channel_errors),
           z_violations=len(z_errors), bounds_violations=len(bounds_errors),
           unique_3d=unique_3d,
           cross_plane_projected_duplicate_ports=sum(1 for v in projected.values() if v > 1),
           projected_xy_distinct=len(projected))
    connector_names = {f'{side}{number:02d}' for side in SIDES
                       for number in range(1, CONNECTORS_PER_SIDE + 1)}
    per_connector_physical = Counter(port['connector'] for port in physical_ports)
    fibers_ok = (set(per_connector_physical) == connector_names
                 and set(per_connector_physical.values()) == {CHANNELS_PER_CONNECTOR})
    record('fibers_per_connector', fibers_ok,
           expected_per_connector=CHANNELS_PER_CONNECTOR,
           connectors_checked=len(per_connector_physical),
           observed_counts=sorted(set(per_connector_physical.values())))
    # channel coverage: every connector uses all 32 channels exactly once overall
    per_connector_channels = defaultdict(Counter)
    for route in routes:
        rid = int(route['route_id'])
        for role in ('source', 'target'):
            side, connector, row, column, channel = role_fields[(rid, role)]
            per_connector_channels[connector][channel] += 1
    coverage_ok = all(sorted(counter) == list(range(1, CHANNELS_PER_CONNECTOR + 1))
                      and set(counter.values()) == {1}
                      for counter in per_connector_channels.values())
    record('channel_coverage', coverage_ok and len(per_connector_channels) == 64,
           connectors_checked=len(per_connector_channels),
           channels_each=CHANNELS_PER_CONNECTOR)

    # ---- pitch / geometry checks ------------------------------------------
    centers = sorted({p['connector_center_mm'] for p in physical_ports})
    center_deltas = [round(centers[i + 1] - centers[i], 12) for i in range(len(centers) - 1)]
    first_center = min(centers)
    last_center = max(centers)
    column_deltas = []
    for side in SIDES:
        for number in range(1, CONNECTORS_PER_SIDE + 1):
            connector = f'{side}{number:02d}'
            alongs = [port_along_mm(connector, column) for column in range(1, COLUMNS + 1)]
            column_deltas.extend(round(alongs[i + 1] - alongs[i], 12)
                                 for i in range(len(alongs) - 1))
    record('column_pitch',
           max(abs(delta - FIBER_COLUMN_PITCH_MM) for delta in column_deltas) <= TOL_MM,
           observed_pitches=sorted(set(column_deltas)),
           expected_mm=FIBER_COLUMN_PITCH_MM,
           max_error_mm=max(abs(delta - FIBER_COLUMN_PITCH_MM) for delta in column_deltas))
    record('connector_pitch',
           max(abs(delta - CONNECTOR_PITCH_MM) for delta in center_deltas) <= TOL_MM
           and abs(first_center - FIRST_CONNECTOR_CENTER_MM) <= TOL_MM,
           observed_pitches=sorted(set(center_deltas)),
           expected_mm=CONNECTOR_PITCH_MM,
           first_center_mm=first_center, last_center_mm=last_center,
           symmetric_margins_mm=[first_center, BOARD_MM - last_center])
    envelope_span = CONNECTOR_ENVELOPE_WIDTH_MM / 2.0 * 2.0  # full envelope width
    record('row_height_separation',
           abs((z_of_row(2) - z_of_row(1)) - FIBER_ROW_PITCH_MM) <= TOL_MM,
           z1_mm=z_of_row(1), z2_mm=z_of_row(2),
           separation_mm=z_of_row(2) - z_of_row(1),
           expected_separation_mm=FIBER_ROW_PITCH_MM)
    mechanical = CONNECTOR_ENVELOPE_WIDTH_MM > CONNECTOR_PITCH_MM
    record('mechanical_envelope_warning', True,
           warning=mechanical,
           envelope_width_mm=CONNECTOR_ENVELOPE_WIDTH_MM,
           connector_pitch_mm=CONNECTOR_PITCH_MM,
           adjacent_envelope_overlap_mm=(CONNECTOR_ENVELOPE_WIDTH_MM
                                         - CONNECTOR_PITCH_MM if mechanical else 0.0),
           envelope_span_mm=envelope_span,
           status=('provisional MPO housing interference at 9 mm pitch unresolved; '
                   'fiber span 3.75 mm < 9 mm pitch but full housing overlaps'),
           note='NOT a port-model failure; retained as a mechanical warning per SPEC')

    config_crosscheck = _configuration_crosscheck()
    if config_crosscheck.get('config_module_available'):
        record('lead_config_constants', not config_crosscheck['mismatches'],
               **config_crosscheck)
    else:
        checks['lead_config_constants'] = dict(passed=None, skipped=True,
                                               **config_crosscheck)

    previous_crosscheck = _previous_round_physical_crosscheck(endpoints)
    if previous_crosscheck.get('available'):
        previous_info = dict(previous_crosscheck)
        previous_passed = bool(previous_info.pop('passed', True))
        record('previous_round_physical_projection', previous_passed, **previous_info)
    else:
        checks['previous_round_physical_projection'] = dict(
            passed=None, skipped=True, **previous_crosscheck)

    warnings = []
    if mechanical:
        warnings.append(
            f'9 mm connector pitch: provisional MPO envelope {CONNECTOR_ENVELOPE_WIDTH_MM} mm '
            f'overlaps neighbour by {CONNECTOR_ENVELOPE_WIDTH_MM - CONNECTOR_PITCH_MM:.2f} mm '
            '- mechanical interference unresolved (fiber span itself is '
            f'{(COLUMNS - 1) * FIBER_COLUMN_PITCH_MM:.2f} mm, fits)')
    warnings.append('two-height interface model is a simulation assumption: glass thickness / '
                    'connector mounting direction unconfirmed, no z transition implemented')
    warnings.append('cross-plane XY projections are NOT same-layer conflicts; '
                    f'{EXPECTED["plane_ports"]} projected (x,y) positions are shared by '
                    'one port on each plane')

    passed = not failed
    return dict(
        passed=passed,
        failed_checks=failed,
        topology=topology,
        csv_path=str(Path(csv_path).resolve()) if csv_path else None,
        csv_sha256=csv_sha256,
        port_model=PORT_MODEL,
        model=dict(MODEL),
        checks=checks,
        planes=planes,
        physical_ports=dict(
            count=len(physical_ports),
            connectors=len({p['connector'] for p in physical_ports}),
            fibers_per_connector=CHANNELS_PER_CONNECTOR,
            per_plane={'z1': sum(1 for p in physical_ports if p['plane'] == 'z1'),
                      'z2': sum(1 for p in physical_ports if p['plane'] == 'z2')},
            unique_3d=unique_3d,
            projected_xy_distinct=len(projected),
            cross_plane_projected_duplicate_ports=sum(1 for v in projected.values() if v > 1),
        ),
        warnings=warnings,
        notes=[
            '2D routing coordinates are the edge projections of the real 3D ports (z dropped)',
            'each plane is an independent 2D problem with layer=0 and 512 connections',
            'no z transition (via/taper/fanout) is implemented in this round',
            'CSV pairing and route_id are unchanged from the frozen connectivity CSVs',
        ],
    )


def _previous_round_physical_crosscheck(endpoints) -> dict:
    """Cross-check our projected port XY against the round-1 physical projection.

    The previous round stored ``physical_projected_xy`` / ``physical_face_u_mm``
    for every endpoint (provisional physical 2x16 projection, row pitch 0.5).
    Those files are read-only history; comparing against them is an independent
    corroboration of the new 0.25 mm-column model, not a derivation source.
    """
    path = PREVIOUS_ROUND_ENDPOINTS
    if not path.exists():
        return dict(available=False, skipped=True, reason=f'{path} not found')
    try:
        previous = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:  # pragma: no cover
        return dict(available=False, skipped=True,
                    reason=f'{type(exc).__name__}: {exc}')
    by_id = {}
    for entry in previous:
        connector = entry.get('connector')
        row = entry.get('row')
        column = entry.get('column')
        if connector is None or row is None or column is None:
            continue
        by_id[(str(connector), int(row), int(column))] = entry
    checked, errors = 0, []
    max_delta = 0.0
    max_u_delta = 0.0
    for eid, endpoint in endpoints.items():
        connector, row, column = eid.split(':')
        key = (connector, int(row), int(column))
        entry = by_id.get(key)
        if entry is None:
            errors.append(dict(endpoint=eid, reason='missing in round-1 endpoints'))
            continue
        projected = entry.get('physical_projected_xy')
        if projected is None:
            errors.append(dict(endpoint=eid, reason='no physical_projected_xy'))
            continue
        checked += 1
        delta = max(abs(projected[0] - endpoint['physical_xy'][0]),
                    abs(projected[1] - endpoint['physical_xy'][1]))
        max_delta = max(max_delta, delta)
        face_u = entry.get('physical_face_u_mm')
        if face_u is not None:
            max_u_delta = max(max_u_delta,
                              abs(float(face_u) - (int(column) - (COLUMNS + 1) / 2.0)
                                  * FIBER_COLUMN_PITCH_MM))
        else:
            errors.append(dict(endpoint=eid, reason='no physical_face_u_mm'))
        if delta > MATCH_TOL_MM:
            errors.append(dict(endpoint=eid, delta_mm=delta))
    passed = (checked == len(endpoints) and not errors
              and max_delta <= MATCH_TOL_MM and max_u_delta <= MATCH_TOL_MM)
    return dict(available=True, passed=passed, checked=checked,
                expected=len(endpoints), max_delta_mm=max_delta,
                max_face_u_delta_mm=max_u_delta, violations=len(errors),
                sample=errors[:5],
                source=str(path), round=1,
                note='round-1 provisional physical projection is independent history; '
                     'it matches the new 0.25 mm-column dual-height XY projection')


# ---------------------------------------------------------------------------
# Artifact writers (JSON / CSV)
# ---------------------------------------------------------------------------
PHYSICAL_PORT_COLUMNS = [
    'topology', 'side', 'connector', 'row', 'column', 'channel', 'plane',
    'x_mm', 'y_mm', 'z_mm', 'along_mm', 'plane_row', 'connector_center_mm',
    'inward_x', 'inward_y', 'port_model',
]


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(data), indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8')
    return path


def write_physical_ports_csv(path, rows):
    """Write the 2048 real 3D physical ports (64 connectors x 32 fibers)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=PHYSICAL_PORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in PHYSICAL_PORT_COLUMNS})
    return path


def write_validation_json(path, state):
    return write_json(path, state['validation'])


# ---------------------------------------------------------------------------
# Comparison against Lead's fslw/ports.py (run in a separate process so this
# audit module never imports it)
# ---------------------------------------------------------------------------
_LEAD_PORTS_SNAPSHOT_SCRIPT = r'''
import json
import sys
from pathlib import Path

from four_side_1024.fslw import ports as P


def endpoint_record(endpoint):
    return dict(
        endpoint_id=endpoint['endpoint_id'],
        connector=endpoint['connector'],
        side=endpoint['side'],
        row=endpoint['row'],
        column=endpoint['column'],
        channel=endpoint['channel'],
        routing_xy=list(endpoint['routing_xy']),
        inward=list(endpoint['inward']),
        layer=endpoint['layer'],
        plane=endpoint['plane'],
        z_mm=endpoint['z_mm'],
        physical_along_mm=endpoint.get('physical_along_mm'),
        physical_face_u_mm=endpoint.get('physical_face_u_mm'),
        physical_face_v_mm=endpoint.get('physical_face_v_mm'),
        port_model=endpoint.get('port_model'),
    )


out_path = Path(sys.argv[1])
payload = {'endpoints': {key: endpoint_record(value)
                         for key, value in P.build_plane_endpoints().items()},
           'connector_records': P.connector_records(),
           'physical_tables': {}, 'planes': {}, 'all_routes': {}}
for topology in ('V1', 'V2'):
    payload['physical_tables'][topology] = P.physical_port_table(topology)
    payload['planes'][topology] = {}
    for plane in ('z1', 'z2'):
        routes, endpoints, _connectors, validation = P.load_plane(topology, plane)
        payload['planes'][topology][plane] = dict(
            validation=validation,
            endpoints={key: endpoint_record(value) for key, value in endpoints.items()},
            routes=[dict(route_id=route['route_id'],
                         row=route.get('row', route['source_row']),
                         source_row=route['source_row'],
                         target_row=route['target_row'],
                         source_endpoint=route['source_endpoint'],
                         target_endpoint=route['target_endpoint'],
                         plane=route['plane'], z_mm=route['z_mm'],
                         pair=route['pair'], relation=route['relation'])
                    for route in routes],
        )
    payload['all_routes'][topology] = [
        dict(route_id=route['route_id'],
             row=route.get('row', route['source_row']), plane=route['plane'],
             z_mm=route['z_mm'], source_endpoint=route['source_endpoint'],
             target_endpoint=route['target_endpoint'], pair=route['pair'],
             relation=route['relation'])
        for route in P.all_routes(topology)]
out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
'''


def lead_ports_snapshot(python_exe=None, timeout=300) -> dict:
    """Run Lead's ``fslw/ports.py`` in a subprocess and serialise its output."""
    import tempfile

    python = str(python_exe or sys.executable)
    with tempfile.TemporaryDirectory(prefix='fslw_ports_snapshot_') as tmp:
        out_path = Path(tmp) / 'lead_ports_snapshot.json'
        completed = subprocess.run(
            [python, '-c', _LEAD_PORTS_SNAPSHOT_SCRIPT, str(out_path)],
            cwd=str(CODE_DIR), capture_output=True, text=True, timeout=timeout)
        if completed.returncode != 0:
            raise RuntimeError(
                'Lead fslw/ports.py snapshot failed: '
                f'{(completed.stderr or completed.stdout or "").strip()[-2000:]}')
        if not out_path.exists():
            raise RuntimeError('Lead fslw/ports.py snapshot wrote no output')
        return json.loads(out_path.read_text(encoding='utf-8'))


def _max_field_delta(left, right, fields):
    deltas = {}
    for field in fields:
        values_left, values_right = left.get(field), right.get(field)
        if values_left is None or values_right is None:
            deltas[field] = None
            continue
        if isinstance(values_left, (list, tuple)):
            deltas[field] = max(abs(float(a) - float(b))
                                for a, b in zip(values_left, values_right))
        else:
            deltas[field] = abs(float(values_left) - float(values_right))
    return deltas


def _module_source_record(path) -> dict:
    """Provenance record for a compared module (path, sha256, mtime)."""
    path = Path(path)
    if not path.exists():
        return dict(path=str(path), exists=False)
    import datetime
    stat = path.stat()
    return dict(path=str(path), exists=True, bytes=stat.st_size,
                sha256=sha256_file(path),
                mtime=datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(
                    sep=' ', timespec='seconds'))


def compare_with_lead_ports(python_exe=None) -> dict:
    """Compare our independent derivation with Lead's ``fslw/ports.py``.

    All 2048 port identities must match exactly (same identity set, same
    routing_xy / plane / z), and both topologies' route tables must agree.
    """
    our_v1 = derive_ports(V1_CSV)
    our_v2 = derive_ports(V2_CSV)
    our_endpoints = our_v1['endpoints']  # the 2048 physical port identities
    snapshot = lead_ports_snapshot(python_exe=python_exe)
    lead_endpoints = snapshot['endpoints']
    comparison = dict(
        lead_ports_available=True,
        lead_ports_source=_module_source_record(CODE_DIR / 'four_side_1024' / 'fslw'
                                                / 'ports.py'),
        our_endpoint_count=len(our_endpoints),
        lead_endpoint_count=len(lead_endpoints),
        endpoint_identity_sets_equal=set(our_endpoints) == set(lead_endpoints),
        missing_in_lead=sorted(set(our_endpoints) - set(lead_endpoints))[:10],
        extra_in_lead=sorted(set(lead_endpoints) - set(our_endpoints))[:10],
        field_mismatches=Counter(),
        max_deltas_mm={},
        topologies={},
        planes={},
        physical_tables={},
        connector_records={},
        code_notes=[],
    )
    # ---- 2048 endpoint identities: coordinates + plane labels -------------
    max_routing = 0.0
    max_along = 0.0
    max_z = 0.0
    plane_violations, label_violations = [], []
    channel_violations = []
    for key in sorted(set(our_endpoints) & set(lead_endpoints)):
        ours, theirs = our_endpoints[key], lead_endpoints[key]
        delta = _max_field_delta(ours, theirs, ['routing_xy'])
        max_routing = max(max_routing, delta['routing_xy'])
        their_along = theirs.get('physical_along_mm')
        if their_along is not None:
            max_along = max(max_along, abs(float(their_along) - ours['physical_along_mm']))
        max_z = max(max_z, abs(float(theirs['z_mm']) - ours['z_mm']))
        if list(theirs['inward']) != list(ours['inward']):
            label_violations.append(dict(endpoint=key, field='inward',
                                         ours=ours['inward'], lead=theirs['inward']))
        if theirs['plane'] != ours['plane'] or plane_of_row(theirs['row']) != theirs['plane']:
            plane_violations.append(dict(endpoint=key, ours=ours['plane'],
                                         lead=theirs['plane'], row=theirs['row']))
        if (int(theirs['row']), int(theirs['column']), int(theirs['channel'])) != (
                int(ours['row']), int(ours['column']), int(ours['channel'])):
            channel_violations.append(dict(endpoint=key))
        if int(theirs['layer']) != 0:
            label_violations.append(dict(endpoint=key, field='layer',
                                         lead=theirs['layer']))
    comparison['max_deltas_mm'].update(
        endpoint_routing_xy=max_routing,
        endpoint_physical_along=max_along,
        endpoint_z=max_z)
    comparison['endpoint_plane_violations'] = len(plane_violations)
    comparison['endpoint_label_violations'] = len(label_violations)
    comparison['endpoint_channel_violations'] = len(channel_violations)
    comparison['field_mismatches']['endpoint_plane'] = len(plane_violations)
    comparison['field_mismatches']['endpoint_label'] = len(label_violations)
    comparison['field_mismatches']['endpoint_channel'] = len(channel_violations)
    comparison['plane_violation_sample'] = plane_violations[:5]

    # ---- per topology: routes / plane assignment / plane validations ------
    for topology, our_state in (('V1', our_v1), ('V2', our_v2)):
        our_routes = {int(route['route_id']): route for route in our_state['routes']}
        lead_routes = {int(route['route_id']): route
                       for route in snapshot['all_routes'][topology]}
        route_ids_equal = set(our_routes) == set(lead_routes)
        route_mismatches = []
        row_plane_violations = []
        for route_id in sorted(set(our_routes) & set(lead_routes)):
            ours, theirs = our_routes[route_id], lead_routes[route_id]
            expected_plane = plane_of_row(int(ours['row']))
            if (int(theirs['row']) != int(ours['row'])
                    or theirs['plane'] != expected_plane
                    or abs(float(theirs['z_mm']) - z_of_row(ours['row'])) > TOL_MM
                    or theirs['source_endpoint'] != ours['source_endpoint']
                    or theirs['target_endpoint'] != ours['target_endpoint']
                    or theirs['pair'] != ours['pair']
                    or theirs['relation'] != ours['relation']):
                route_mismatches.append(dict(route_id=route_id, ours=dict(
                    row=ours['row'], plane=ours['plane'], z_mm=ours['z_mm'],
                    source_endpoint=ours['source_endpoint'],
                    target_endpoint=ours['target_endpoint'],
                    pair=ours['pair'], relation=ours['relation']), lead=theirs))
            if plane_of_row(int(theirs['row'])) != theirs['plane']:
                row_plane_violations.append(route_id)
        plane_entries = {}
        for plane in ('z1', 'z2'):
            lead_plane = snapshot['planes'][topology][plane]
            expected_row = PLANE_ROW[plane]
            lead_validation = lead_plane['validation']
            our_plane_routes = {int(route['route_id']) for route in our_state['routes']
                                if int(route['row']) == expected_row}
            lead_route_ids = {int(route['route_id']) for route in lead_plane['routes']}
            lead_plane_endpoints = lead_plane['endpoints']
            our_plane_endpoints = {key: value for key, value in our_endpoints.items()
                                   if plane_of_row(value['row']) == plane}
            max_plane_routing = 0.0
            plane_endpoint_mismatches = 0
            for key in sorted(set(our_plane_endpoints) & set(lead_plane_endpoints)):
                delta = _max_field_delta(our_plane_endpoints[key],
                                         lead_plane_endpoints[key], ['routing_xy'])
                max_plane_routing = max(max_plane_routing, delta['routing_xy'])
            plane_endpoint_mismatches = len(set(our_plane_endpoints)
                                            ^ set(lead_plane_endpoints))
            plane_entries[plane] = dict(
                lead_validation_passed=bool(lead_validation.get('passed')),
                lead_validation_issues=list(lead_validation.get('issues') or []),
                route_id_sets_equal=our_plane_routes == lead_route_ids,
                our_routes=len(our_plane_routes), lead_routes=len(lead_route_ids),
                endpoint_set_mismatches=plane_endpoint_mismatches,
                max_routing_xy_delta_mm=max_plane_routing,
                expected_row=expected_row,
                z_mm=z_of_row(expected_row),
            )
            comparison['planes'][f'{topology}_{plane}'] = plane_entries[plane]
        comparison['topologies'][topology] = dict(
            route_id_sets_equal=route_ids_equal,
            our_routes=len(our_routes), lead_routes=len(lead_routes),
            route_field_mismatches=len(route_mismatches),
            route_mismatch_sample=route_mismatches[:5],
            row_plane_violations=len(row_plane_violations),
            planes=plane_entries,
        )

        # ---- physical 3D port table --------------------------------------
        our_physical = {(port['connector'], port['row'], port['column']): port
                        for port in our_state['physical_ports']}
        lead_physical = {(port['connector'], int(port['row']), int(port['column'])): port
                         for port in snapshot['physical_tables'][topology]}
        identity_equal = set(our_physical) == set(lead_physical)
        max_phys = 0.0
        phys_plane_violations = 0
        for key in sorted(set(our_physical) & set(lead_physical)):
            ours, theirs = our_physical[key], lead_physical[key]
            max_phys = max(max_phys,
                           abs(float(theirs['x_mm']) - ours['x_mm']),
                           abs(float(theirs['y_mm']) - ours['y_mm']),
                           abs(float(theirs['z_mm']) - ours['z_mm']),
                           abs(float(theirs['along_mm']) - ours['along_mm']))
            if (plane_of_row(int(theirs['row'])) != theirs['plane']
                    or abs(float(theirs['z_mm']) - z_of_row(theirs['row'])) > TOL_MM):
                phys_plane_violations += 1
        comparison['physical_tables'][topology] = dict(
            our_ports=len(our_physical), lead_ports=len(lead_physical),
            identity_sets_equal=identity_equal,
            max_coordinate_delta_mm=max_phys,
            plane_label_violations=phys_plane_violations,
        )

    # ---- connector records ------------------------------------------------
    our_connectors = {c['connector']: c for c in our_v1['connectors']}
    lead_connectors = {c['connector']: c for c in snapshot['connector_records']}
    max_center = 0.0
    for name in sorted(set(our_connectors) & set(lead_connectors)):
        ours, theirs = our_connectors[name], lead_connectors[name]
        max_center = max(max_center,
                         abs(float(theirs['along_center_mm']) - ours['along_center_mm']),
                         abs(float(theirs['center_xy'][0]) - ours['center_xy'][0]),
                         abs(float(theirs['center_xy'][1]) - ours['center_xy'][1]))
    comparison['connector_records'] = dict(
        identity_sets_equal=set(our_connectors) == set(lead_connectors),
        our_connectors=len(our_connectors), lead_connectors=len(lead_connectors),
        max_center_delta_mm=max_center,
    )

    # ---- code-review notes on Lead's validate_plane (non-blocking) -------
    comparison['code_notes'] = [
        'ports.load_plane / ports.all_routes do NOT set route["row"] although SPEC §9 '
        'asks for it; this comparison falls back to route["source_row"].',
        'ports.validate_plane duplicate route_id check compares a list to itself '
        "(sorted(...) != sorted(...)) -> always False; harmless because load_plane "
        'already guarantees 512 unique CSV route ids, but the guard is a no-op.',
        'ports.validate_plane non-finite coordinate check is abs(x - x) > 0 -> always '
        'False; invalid/NaN routing_xy would not be caught by ports.py (our audit '
        'checks coordinates directly).',
        'ports.load_plane skips row-mixing detection for routes whose source row does '
        "not match the plane (continue before the target_row check); our audit checks "
        'both roles.',
    ]

    all_zero = (comparison['max_deltas_mm']['endpoint_routing_xy'] <= MATCH_TOL_MM
                and comparison['max_deltas_mm']['endpoint_physical_along'] <= MATCH_TOL_MM
                and comparison['max_deltas_mm']['endpoint_z'] <= MATCH_TOL_MM)
    endpoint_ok = (comparison['endpoint_identity_sets_equal']
                   and comparison['endpoint_plane_violations'] == 0
                   and comparison['endpoint_label_violations'] == 0
                   and comparison['endpoint_channel_violations'] == 0
                   and all_zero)
    topology_ok = all(
        entry['route_id_sets_equal'] and entry['route_field_mismatches'] == 0
        and entry['row_plane_violations'] == 0
        and all(plane['lead_validation_passed'] and plane['route_id_sets_equal']
                and plane['endpoint_set_mismatches'] == 0
                and plane['max_routing_xy_delta_mm'] <= MATCH_TOL_MM
                for plane in entry['planes'].values())
        for entry in comparison['topologies'].values())
    physical_ok = all(entry['identity_sets_equal']
                      and entry['max_coordinate_delta_mm'] <= MATCH_TOL_MM
                      and entry['plane_label_violations'] == 0
                      for entry in comparison['physical_tables'].values())
    comparison['passed'] = bool(endpoint_ok and topology_ok and physical_ok)
    comparison['summary'] = dict(
        endpoints_compared=len(our_endpoints),
        endpoint_identity_sets_equal=comparison['endpoint_identity_sets_equal'],
        max_routing_xy_delta_mm=comparison['max_deltas_mm']['endpoint_routing_xy'],
        max_physical_along_delta_mm=comparison['max_deltas_mm']['endpoint_physical_along'],
        max_z_delta_mm=comparison['max_deltas_mm']['endpoint_z'],
        endpoint_plane_violations=comparison['endpoint_plane_violations'],
        route_field_mismatches={topology: entry['route_field_mismatches']
                                for topology, entry in comparison['topologies'].items()},
        row_plane_violations={topology: entry['row_plane_violations']
                              for topology, entry in comparison['topologies'].items()},
        physical_table_max_delta_mm={topology: entry['max_coordinate_delta_mm']
                                     for topology, entry in
                                     comparison['physical_tables'].items()},
        passed=comparison['passed'],
    )
    return comparison


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
PAIR_COLORS = {
    'NS': '#3366bb', 'EW': '#b84040', 'EN': '#e3a323',
    'ES': '#00a0a0', 'SW': '#a545b0', 'NW': '#60a735',
}
SIDE_COLORS = {'N': '#3366bb', 'E': '#e3a323', 'S': '#b84040', 'W': '#60a735'}


def _pyplot():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def _draw_connector_ports(ax, side, connector, plane_row):
    """Draw the 16 real ports of one connector on one plane + connector strip."""
    from matplotlib.patches import Rectangle
    center = connector_center_mm(connector)
    span = (COLUMNS - 1) * FIBER_COLUMN_PITCH_MM
    thickness = 0.9
    if side in 'NS':
        y0 = BOARD_MM - thickness if side == 'N' else 0.0
        ax.add_patch(Rectangle((center - span / 2 - 0.15, y0), span + 0.3, thickness,
                               facecolor='#dddddd', edgecolor='#888888', linewidth=0.2,
                               zorder=2))
    else:
        x0 = BOARD_MM - thickness if side == 'E' else 0.0
        ax.add_patch(Rectangle((x0, center - span / 2 - 0.15), thickness, span + 0.3,
                               facecolor='#dddddd', edgecolor='#888888', linewidth=0.2,
                               zorder=2))
    for column in range(1, COLUMNS + 1):
        x, y = edge_xy(side, port_along_mm(connector, column))
        ax.plot([x], [y], marker='s', markersize=1.4, color=SIDE_COLORS[side],
                markeredgewidth=0, zorder=3)


def _draw_connector_labels(ax, side):
    for number in range(1, CONNECTORS_PER_SIDE + 1):
        connector = f'{side}{number:02d}'
        center = connector_center_mm(connector)
        if side == 'N':
            ax.text(center, BOARD_MM + 4.2, connector, ha='center', va='bottom', fontsize=5)
        elif side == 'S':
            ax.text(center, -4.2, connector, ha='center', va='top', fontsize=5)
        elif side == 'E':
            ax.text(BOARD_MM + 5.2, center, connector, ha='left', va='center', fontsize=5)
        else:
            ax.text(-5.2, center, connector, ha='right', va='center', fontsize=5)


def plot_plane_connectivity(state, plane, path):
    """Connection diagram of one independent routing plane (z1 or z2)."""
    plt = _pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    row = PLANE_ROW[plane]
    z = z_of_row(row)
    routes = [route for route in state['routes'] if int(route['row']) == row]
    endpoints = state['endpoints']
    fig, ax = plt.subplots(figsize=(11, 11))
    segments = [[endpoints[route['source_endpoint']]['routing_xy'],
                 endpoints[route['target_endpoint']]['routing_xy']] for route in routes]
    ax.add_collection(LineCollection(segments,
                                     colors=[PAIR_COLORS[route['pair']] for route in routes],
                                     linewidths=.45, alpha=.62, zorder=1))
    ax.add_patch(Rectangle((0, 0), BOARD_MM, BOARD_MM, fill=False, linewidth=1.5, zorder=4))
    for side in SIDES:
        for number in range(1, CONNECTORS_PER_SIDE + 1):
            _draw_connector_ports(ax, side, f'{side}{number:02d}', row)
        _draw_connector_labels(ax, side)
    handles = [Line2D([0], [0], color=color, lw=1.6, label=pair)
               for pair, color in PAIR_COLORS.items()
               if any(route['pair'] == pair for route in routes)]
    ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.05),
              fontsize=7, title='connection pair', title_fontsize=7,
              framealpha=.9, ncol=max(1, len(handles)))
    relation = EXPECTED['plane_relations'][plane]
    title = (f"{state['topology']} · plane {plane} (CSV row {row}, {relation}) | "
             f"{len(routes)}/512 connections | real IEC 61754-7-3 2×16 dual-height | "
             f"z = {z} mm, layer 0\n"
             f"ports on this plane: 1024 (64 connectors × 16 columns), 0.25 mm column pitch | "
             f"2D projection within the plane only\n"
             f"cross-plane XY overlaps are NOT same-layer conflicts (z1 / z2 are 0.5 mm apart); "
             f"simulation coordinates under the two-height assumption")
    ax.set(xlim=(-9, 159), ylim=(-9, 159), aspect='equal', xlabel='x (mm)', ylabel='y (mm)')
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return Path(path)


def plot_dual_height_schematic(path, mechanical_warning=None):
    """Dual-height interface schematic: 2x16 port grid + board cross-section."""
    plt = _pyplot()
    from matplotlib.patches import FancyArrowPatch, Rectangle

    mechanical_warning = mechanical_warning or dict(
        envelope_width_mm=CONNECTOR_ENVELOPE_WIDTH_MM,
        connector_pitch_mm=CONNECTOR_PITCH_MM,
        overlap_mm=CONNECTOR_ENVELOPE_WIDTH_MM - CONNECTOR_PITCH_MM)
    fig, axes = plt.subplots(1, 2, figsize=(17.5, 8.5),
                             gridspec_kw={'width_ratios': [1.0, 1.35]})

    # ---- (a) IEC 2x16 port grid of one connector -------------------------
    ax = axes[0]
    for row in (1, 2):
        z = z_of_row(row)
        color = SIDE_COLORS['N'] if row == 1 else SIDE_COLORS['S']
        for column in range(1, COLUMNS + 1):
            x = (column - (COLUMNS + 1) / 2.0) * FIBER_COLUMN_PITCH_MM
            ax.plot([x], [z], marker='o', markersize=7.5, markerfacecolor=color,
                    markeredgecolor='black', markeredgewidth=0.5, zorder=3)
        ax.text(2.05, z, f"row {row} → plane {'z1' if row == 1 else 'z2'} (z = {z} mm)",
                va='center', fontsize=9, color=color)
    # 0.25 mm column pitch arrow (between columns 8 and 9)
    x_left = (8 - 8.5) * FIBER_COLUMN_PITCH_MM
    x_right = (9 - 8.5) * FIBER_COLUMN_PITCH_MM
    ax.annotate('', xy=(x_right, 0.22), xytext=(x_left, 0.22),
                arrowprops=dict(arrowstyle='<->', color='black', lw=1.2))
    ax.text((x_left + x_right) / 2, 0.255, '0.25 mm\ncolumn pitch', ha='center',
            va='bottom', fontsize=8.5)
    # 0.5 mm row separation arrow
    ax.annotate('', xy=(-1.55, z_of_row(2)), xytext=(-1.55, z_of_row(1)),
                arrowprops=dict(arrowstyle='<->', color='black', lw=1.2))
    ax.text(-1.68, (z_of_row(1) + z_of_row(2)) / 2.0, '0.5 mm\nrow separation\n(z2 − z1)',
            ha='right', va='center', fontsize=8.5)
    ax.set_xlim(-2.6, 3.6)
    ax.set_ylim(-0.32, 0.85)
    ax.set_xlabel('along-edge offset from connector centre (mm)')
    ax.set_ylabel('z (glass-thickness direction, mm)')
    ax.set_title('(a) IEC 61754-7-3:2019 2×16 MPO port grid (one connector)\n'
                 'row 1 → z1 plane (512 opposite connections), '
                 'row 2 → z2 plane (512 adjacent connections)', fontsize=10)
    ax.grid(alpha=.25)
    ax.axhline(0.0, color=SIDE_COLORS['N'], lw=0.8, alpha=.4)
    ax.axhline(0.5, color=SIDE_COLORS['S'], lw=0.8, alpha=.4)
    ax.text(0.02, 0.02, '16 columns × 0.25 mm = 3.75 mm fiber span\n'
                        '32 fibers per connector = 2 rows × 16 columns',
            transform=ax.transAxes, fontsize=8,
            bbox=dict(facecolor='white', edgecolor='#999999', pad=3))

    # ---- (b) board cross-section: two independent routing planes ---------
    ax = axes[1]
    glass_top, glass_bottom = 0.72, -0.22
    ax.add_patch(Rectangle((0, glass_bottom), BOARD_MM, glass_top - glass_bottom,
                           facecolor='#eaf2fa', edgecolor='#7a9bbf', linewidth=1.0,
                           zorder=0))
    ax.text(BOARD_MM / 2, glass_bottom + 0.04, 'glass substrate (thickness not confirmed)',
            ha='center', va='bottom', fontsize=8, color='#456')
    # the two planes
    ax.plot([0, BOARD_MM], [z_of_row(1)] * 2, color=SIDE_COLORS['N'], lw=2.6, zorder=1)
    ax.plot([0, BOARD_MM], [z_of_row(2)] * 2, color=SIDE_COLORS['S'], lw=2.6, zorder=1)
    ax.text(BOARD_MM - 2, z_of_row(1) + 0.05,
            'plane z1 (z = 0.0 mm): 512 opposite connections (NS 256 + EW 256),\n'
            '1024 real ports, independent 2D routing, layer = 0',
            ha='right', va='bottom', fontsize=8.5, color=SIDE_COLORS['N'])
    ax.text(BOARD_MM - 2, z_of_row(2) + 0.06,
            'plane z2 (z = 0.5 mm): 512 adjacent connections (EN/ES/SW/NW 128 each),\n'
            '1024 real ports, independent 2D routing, layer = 0',
            ha='right', va='bottom', fontsize=8.5, color=SIDE_COLORS['S'])
    # connector at the left edge with two rows of fibers entering its plane
    for row, color in ((1, SIDE_COLORS['N']), (2, SIDE_COLORS['S'])):
        z = z_of_row(row)
        ax.add_patch(Rectangle((-8.0, z - 0.075), 8.0, 0.15, facecolor='#bbbbbb',
                               edgecolor='black', linewidth=0.6, zorder=2))
        for offset in [(-1.05 + i * 0.15) for i in range(15)]:
            ax.plot([-0.4, 12.0], [z + offset * 0.12, z + offset * 0.12],
                    color=color, lw=0.35, alpha=0.55, zorder=1)
        ax.annotate('', xy=(3.0, z), xytext=(-0.2, z),
                    arrowprops=dict(arrowstyle='-|>', color=color, lw=1.6), zorder=3)
    ax.text(-8.2, 0.64, 'MPO connector\n(2 rows, one per plane)', ha='right', va='center',
            fontsize=8.5)
    # z dimension arrow
    ax.annotate('', xy=(-4.2, z_of_row(2)), xytext=(-4.2, z_of_row(1)),
                arrowprops=dict(arrowstyle='<->', color='black', lw=1.1))
    ax.text(-4.45, 0.25, '0.5 mm\nz gap (z1→z2)', ha='right', va='center', fontsize=8)
    ax.set_xlim(-19, 158)
    ax.set_ylim(-0.75, 1.35)
    ax.set_xlabel('position along the board edge (mm) — cross-section schematic (z exaggerated)')
    ax.set_ylabel('z (mm)')
    ax.set_title('(b) Two independent 2D routing planes at z1 / z2\n'
                 'no z transition (via / taper / fanout) implemented', fontsize=10)
    ax.grid(alpha=.2, axis='x')
    caveats = (
        'CAVEATS — simulation coordinates under the two-height interface assumption:\n'
        '• no z transition implemented (no via / taper / fanout), 2 profiles only\n'
        '• glass thickness and connector mounting direction are NOT confirmed\n'
        f"• 9 mm connector pitch: provisional MPO housing envelope "
        f"{mechanical_warning['envelope_width_mm']:.2f} mm overlaps neighbours by "
        f"{mechanical_warning['overlap_mm']:.2f} mm — mechanical interference unresolved\n"
        '• cross-plane XY projections are NOT same-layer conflicts\n'
        '• not a claim of manufacturability; see connectivity/README.md'
    )
    ax.text(0.01, 0.985, caveats, transform=ax.transAxes, va='top', ha='left',
            fontsize=8, bbox=dict(facecolor='#fff8e1', edgecolor='#c9a227', pad=4),
            zorder=5)

    fig.suptitle('Dual-height real 2×16 MPO interface model — FSLW R≥40 mm / 30 µm '
                 'experiment convention (simulation only)', fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return Path(path)


# ---------------------------------------------------------------------------
# README + artifact build
# ---------------------------------------------------------------------------
def _fmt_channels(channels):
    channels = sorted(int(channel) for channel in channels)
    if not channels:
        return '-'
    ranges, start, prev = [], channels[0], channels[0]
    for channel in channels[1:]:
        if channel == prev + 1:
            prev = channel
            continue
        ranges.append((start, prev))
        start = prev = channel
    ranges.append((start, prev))
    return ', '.join(f'{a}' if a == b else f'{a}-{b}' for a, b in ranges)


def write_readme(path, states, comparison=None):
    v1, v2 = states['V1'], states['V2']
    v1_validation, v2_validation = v1['validation'], v2['validation']
    lines = []
    lines.append('# FSLW 双高度真实 2×16 MPO 端口模型校验（connectivity / Phase 1）')
    lines.append('')
    lines.append('> **重要声明（本文所有坐标为“双高度接口假设”下的仿真坐标，不是可制造性结论）**')
    lines.append('>')
    lines.append('> - 本模块与产物中的坐标是 **仿真坐标**（two-height interface assumption）：'
                 '`z1 = 0.0 mm`、`z2 = 0.5 mm` 为模型值；')
    lines.append('> - **本轮未实现任何 z 方向过渡**（无 via / taper / fanout）；')
    lines.append('> - **玻璃厚度与接头安装方向尚未确认**；')
    lines.append('> - **9 mm 接头间距下的机械干涉尚未解决**：'
                 f'暂定 MPO 外壳包络 {CONNECTOR_ENVELOPE_WIDTH_MM:.2f} mm > 间距 '
                 f'{CONNECTOR_PITCH_MM:.1f} mm，相邻外壳重叠 '
                 f'{CONNECTOR_ENVELOPE_WIDTH_MM - CONNECTOR_PITCH_MM:.2f} mm'
                 '（光纤跨距仅 3.75 mm 本身不重叠）；')
    lines.append('> - **跨平面的 XY 投影重叠不是同层冲突**：z1 / z2 相距 0.5 mm，'
                 '冲突判定只在同一平面内进行。')
    lines.append('')
    lines.append(f'生成脚本：`four_side_1024/fslw/ports_audit.py`'
                 f'（`python -m four_side_1024.fslw.ports_audit`）；本 README 及全部 JSON/CSV/PNG '
                 f'由该脚本一次运行生成，所有数字均为实测，无手工填写。')
    lines.append('')
    lines.append('## 1. 模型（独立重新推导，不复用 `fslw/ports.py`）')
    lines.append('')
    lines.append('| 项 | 值 |')
    lines.append('|---|---|')
    lines.append(f'| 接口标准 | IEC 61754-7-3:2019 2×16 MPO |')
    lines.append(f'| 同排纤芯列距 | {FIBER_COLUMN_PITCH_MM} mm |')
    lines.append(f'| 两排中心距（z1→z2） | {FIBER_ROW_PITCH_MM} mm |')
    lines.append(f'| 每接头光纤 | 2 排 × 16 列 = {CHANNELS_PER_CONNECTOR} 根 |')
    lines.append(f'| 板面 / 接头数 | {BOARD_MM:g} × {BOARD_MM:g} mm，4 边 × '
                 f'{CONNECTORS_PER_SIDE} = {len(v1["connectors"])} 个接头 |')
    lines.append(f'| 接头中心 | `connector_center = (150 − 15×9)/2 + (c−1)×9 = '
                 f'{FIRST_CONNECTOR_CENTER_MM:g} + (c−1)×9` mm（c = 1..16） |')
    lines.append(f'| 端口沿边坐标 | `along = connector_center + (column − 8.5) × 0.25` mm |')
    lines.append(f'| 平面规则 | CSV `row=1` → `z1={PLANE_Z_MM[1]} mm`（512 对边：NS 256 + EW 256）；'
                 f'`row=2` → `z2={PLANE_Z_MM[2]} mm`（512 邻边：EN/ES/SW/NW 各 128） |')
    lines.append(f'| 每平面端口 | 4 边 × 16 接头 × 16 列 = 1024，恰好各用一次 |')
    lines.append(f'| 2D 布线坐标 | 端口的板边投影（丢弃 z）；层 `layer=0`，平面内独立二维寻路 |')
    lines.append('')
    lines.append('## 2. 校验结果')
    lines.append('')
    for label, state in (('V1', v1), ('V2', v2)):
        validation = state['validation']
        lines.append(f'### {label}（SHA256 `{state["csv_sha256"]}`）')
        lines.append('')
        lines.append(f'- 总体：**{"PASS" if validation["passed"] else "FAIL"}**；'
                     f'failed_checks = {validation["failed_checks"] or "[]"}')
        lines.append(f'- 连接：{validation["checks"]["connections"]["observed"]} 条；'
                     f'relation = {validation["checks"]["relation_counts"]["observed"]}')
        lines.append(f'- 端点：{validation["checks"]["endpoints_used_once"]["distinct"]} 个物理端口'
                     f'（64 接头 × 32 纤芯）各用一次；每个接头覆盖全部 32 通道 = '
                     f'{validation["checks"]["channel_coverage"]["connectors_checked"]}/64')
        for plane in ('z1', 'z2'):
            entry = validation['planes'][plane]
            lines.append(
                f'- 平面 {plane}（row {entry["row"]}, z = {entry["z_mm"]} mm）：'
                f'{entry["connections"]} 条连接、{entry["endpoints"]} 个端点、'
                f'{entry["port_keys"]}/{entry["expected_ports"]} 个端口恰好各一次、'
                f'relation = {entry["relations"]}、along 公式最大误差 '
                f'{entry["along_formula_max_error_mm"]:.1e} mm、routing_xy 最大误差 '
                f'{entry["routing_xy_max_error_mm"]:.1e} mm')
        checks = validation['checks']
        lines.append(f'- 列距 {checks["column_pitch"]["expected_mm"]} mm：实测 '
                     f'{checks["column_pitch"]["observed_pitches"]}；'
                     f'两排 z 间隔 {checks["row_height_separation"]["separation_mm"]} mm')
        lines.append(f'- CSV→端点编号一致性：channel/row/column 违规 '
                     f'{checks["channel_formula"]["violations"]}；同边连接 '
                     f'{checks["different_sides"]["same_side_connections"]}；'
                     f'重复连接 {checks["no_duplicate_connection"]["duplicates"]}')
        previous = checks.get('previous_round_physical_projection', {})
        if previous.get('available'):
            lines.append(f'- 与上一轮历史记录的 `physical_projected_xy` 交叉核对：'
                         f'{previous.get("checked")} 个端点，最大偏差 '
                         f'{previous.get("max_delta_mm")} mm（该历史文件只读，仅作旁证）')
        config_check = checks.get('lead_config_constants', {})
        lines.append(f'- 与 Lead `fslw/config.py` 常量核对：mismatches = '
                     f'{config_check.get("mismatches") or "[]"}')
        lines.append(f'- 机械包络告警：包络 {checks["mechanical_envelope_warning"]["envelope_width_mm"]} mm '
                     f'/ 间距 {checks["mechanical_envelope_warning"]["connector_pitch_mm"]} mm，'
                     f'重叠 {checks["mechanical_envelope_warning"]["adjacent_envelope_overlap_mm"]:.2f} mm'
                     f'（保留告警，非端口模型失败）')
        lines.append('')
    lines.append('## 3. 物理 3D 端口坐标（独立于二维布线坐标保存）')
    lines.append('')
    physical = v1_validation['physical_ports']
    lines.append(f'- `physical_ports_v1.csv` / `physical_ports_v2.csv`：各 '
                 f'{physical["count"]} 行 = {physical["connectors"]} 接头 × '
                 f'{physical["fibers_per_connector"]} 根光纤；列：'
                 f'`{", ".join(PHYSICAL_PORT_COLUMNS)}`。')
    lines.append(f'- 3D 坐标唯一：{physical["unique_3d"]}/2048；z1 平面 {physical["per_plane"]["z1"]} 个、'
                 f'z2 平面 {physical["per_plane"]["z2"]} 个；')
    lines.append(f'- (x, y) 投影只有 {physical["projected_xy_distinct"]} 个不同位置，'
                 f'{physical["cross_plane_projected_duplicate_ports"]} 个端口在 XY 投影上“重合”'
                 f'——这是两个高度平面在同一 XY 上的投影，**不是同层冲突**。')
    lines.append('- 两个拓扑共用同一套 2048 个物理端口（端口几何与拓扑无关），'
                 'V1/V2 CSV 仅在 `topology` 列不同。')
    lines.append('')
    lines.append('## 4. 与 Lead `fslw/ports.py` 的独立对比')
    lines.append('')
    if comparison and comparison.get('lead_ports_available'):
        summary = comparison['summary']
        source = comparison.get('lead_ports_source') or {}
        lines.append(f'- 对比方式：在独立子进程中运行 `fslw/ports.py`，与本文推导逐字段对比'
                     f'（`ports_audit.py` 不在导入期依赖 `ports.py`）。')
        if source.get('exists'):
            lines.append(f'- 被对比的 `ports.py`：SHA256 `{source["sha256"]}`，'
                         f'{source.get("bytes")} bytes，mtime {source.get("mtime")}。')
        lines.append(f'- 2048 个 `(connector,row,column)` 身份集合是否相同：'
                     f'**{summary["endpoint_identity_sets_equal"]}**；'
                     f'routing_xy 最大偏差 **{summary["max_routing_xy_delta_mm"]} mm**；'
                     f'physical_along 最大偏差 {summary["max_physical_along_delta_mm"]} mm；'
                     f'z 最大偏差 {summary["max_z_delta_mm"]} mm。')
        lines.append(f'- 端点 row→plane 不一致数：{summary["endpoint_plane_violations"]}；'
                     f'每个拓扑 route 字段不一致数：{summary["route_field_mismatches"]}；'
                     f'row→plane 不一致 route：{summary["row_plane_violations"]}；'
                     f'物理端口表坐标最大偏差：{summary["physical_table_max_delta_mm"]}。')
        lines.append(f'- 对比结论：**{"PASS — 完全一致" if summary["passed"] else "FAIL"}**'
                     f'（详见 `lead_ports_comparison.json`）。')
        if comparison.get('code_notes'):
            lines.append('- 顺带发现（不阻塞，供 Lead 参考）：')
            for note in comparison['code_notes']:
                lines.append(f'  - {note}')
    else:
        lines.append('- 本次运行未执行或无法执行与 `fslw/ports.py` 的对比：'
                     f'{(comparison or {}).get("error", "comparison skipped")}')
    lines.append('')
    lines.append('## 5. 文件清单')
    lines.append('')
    lines.append('| 文件 | 内容 |')
    lines.append('|---|---|')
    lines.append('| `ports_validation_v1.json` / `ports_validation_v2.json` | '
                 '双高度端口模型逐项校验（本文件第 2 节数字的完整结构化版本） |')
    lines.append('| `physical_ports_v1.csv` / `physical_ports_v2.csv` | 2048 个真实 3D 物理端口坐标 '
                 '(x, y, z1/z2, along, side/connector/row/column/channel) |')
    lines.append('| `plane_connectivity_v1_z1.png` `plane_connectivity_v1_z2.png` '
                 '`plane_connectivity_v2_z1.png` `plane_connectivity_v2_z2.png` | '
                 'V1/V2 × z1/z2 四个平面的连接关系图（每平面 512 条） |')
    lines.append('| `dual_height_schematic.png` | 双高度 2×16 接口剖面示意'
                 '（0.25 mm 列距、0.5 mm 两排间距、z1/z2、无 z 过渡） |')
    lines.append('| `lead_ports_comparison.json` | 与 Lead `fslw/ports.py` 的逐字段对比结果 |')
    lines.append('| `README.md` | 本文件 |')
    lines.append('')
    lines.append('## 6. 重现')
    lines.append('')
    lines.append('```powershell')
    lines.append('cd "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D"')
    lines.append('.\\\\.venv\\\\Scripts\\\\python.exe -m four_side_1024.fslw.ports_audit')
    lines.append('.\\\\.venv\\\\Scripts\\\\python.exe -m pytest four_side_1024\\\\fslw\\\\tests_fslw\\\\test_ports_fslw.py -q')
    lines.append('```')
    lines.append('')
    lines.append('## 7. 已知限制 / 风险')
    lines.append('')
    lines.append('1. **仿真假设**：z1=0.0 mm、z2=0.5 mm 是模型值；玻璃厚度、接头安装方向未确认。')
    lines.append('2. **无 z 过渡**：没有 via/taper/fanout，两个平面在物理上如何连接到同一接头的'
                 '两排光纤仍是一个假设；组合布局中的跨平面连线在真实器件中需要额外结构。')
    lines.append('3. **机械干涉**：9 mm 接头间距与暂定 MPO 外壳包络 12.59 mm 不兼容（相邻重叠 '
                 f'{CONNECTOR_ENVELOPE_WIDTH_MM - CONNECTOR_PITCH_MM:.2f} mm），'
                 '本轮端口模型不解决该问题。')
    lines.append('4. **跨平面投影不是冲突**：z1/z2 的 XY 投影在同一点重合是设计使然，'
                 '不得把跨平面的投影交叉计为同层违规；组合统计必须分开 `same_plane_crossings` '
                 '与 `cross_plane_projected_overlaps`。')
    lines.append('5. **不可与上一轮数字直接比较**：上一轮为 0.175 mm 单层虚拟展开（R=5 mm / '
                 '125 µm 间距），端口模型不同，数据不可直接比。')
    lines.append('')
    path = Path(path)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def build_all(output_dir=OUTPUT_DIR, plots=True, compare=True, python_exe=None):
    """Build every Phase-1 FSLW connectivity artifact (ports model audit)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    states = {'V1': derive_ports(V1_CSV), 'V2': derive_ports(V2_CSV)}
    files = []

    def emit(emitted):
        files.append(str(emitted))
        return emitted

    emit(write_validation_json(out / 'ports_validation_v1.json', states['V1']))
    emit(write_validation_json(out / 'ports_validation_v2.json', states['V2']))
    emit(write_physical_ports_csv(out / 'physical_ports_v1.csv',
                                  states['V1']['physical_ports']))
    emit(write_physical_ports_csv(out / 'physical_ports_v2.csv',
                                  states['V2']['physical_ports']))

    comparison = None
    if compare:
        try:
            comparison = compare_with_lead_ports(python_exe=python_exe)
        except Exception as exc:  # noqa: BLE001 - comparison is auxiliary
            comparison = dict(lead_ports_available=False,
                              error=f'{type(exc).__name__}: {exc}')
        emit(write_json(out / 'lead_ports_comparison.json', comparison))

    if plots:
        for topology in ('V1', 'V2'):
            for plane in ('z1', 'z2'):
                emit(plot_plane_connectivity(
                    states[topology], plane,
                    out / f'plane_connectivity_{topology.lower()}_{plane}.png'))
        emit(plot_dual_height_schematic(out / 'dual_height_schematic.png'))

    emit(write_readme(out / 'README.md', states, comparison))

    summary = dict(
        topology_v1=states['V1']['topology'],
        topology_v2=states['V2']['topology'],
        v1_csv_sha256=states['V1']['csv_sha256'],
        v2_csv_sha256=states['V2']['csv_sha256'],
        v1_validation_passed=states['V1']['validation']['passed'],
        v2_validation_passed=states['V2']['validation']['passed'],
        v1_failed_checks=states['V1']['validation']['failed_checks'],
        v2_failed_checks=states['V2']['validation']['failed_checks'],
        v1_planes={plane: dict(passed=entry['passed'],
                               connections=entry['connections'],
                               endpoints=entry['endpoints'],
                               ports_once=entry['port_keys'] == entry['expected_ports'],
                               relations=entry['relations'])
                   for plane, entry in states['V1']['validation']['planes'].items()},
        v2_planes={plane: dict(passed=entry['passed'],
                               connections=entry['connections'],
                               endpoints=entry['endpoints'],
                               ports_once=entry['port_keys'] == entry['expected_ports'],
                               relations=entry['relations'])
                   for plane, entry in states['V2']['validation']['planes'].items()},
        physical_ports=states['V1']['validation']['physical_ports'],
        lead_ports_comparison=(comparison.get('summary') if comparison else None),
        files=files,
    )
    return dict(states=states, comparison=comparison, files=files, summary=summary)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='Build the FSLW dual-height 2x16 port-model audit artifacts.')
    parser.add_argument('--output-dir', default=str(OUTPUT_DIR))
    parser.add_argument('--no-plots', action='store_true')
    parser.add_argument('--skip-comparison', action='store_true')
    parser.add_argument('--python', default=None, help='python executable for the '
                                                       'fslw/ports.py subprocess')
    args = parser.parse_args(argv)
    result = build_all(Path(args.output_dir), plots=not args.no_plots,
                       compare=not args.skip_comparison, python_exe=args.python)
    print(json.dumps(_jsonable(result['summary']), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
